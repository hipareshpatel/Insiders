"""The shadow meaning critic (critic.py): parsing, the off-switch, quota, no card mutation, storage. No model is called."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import replace
from datetime import timedelta

from conftest import FakeProvider, gateway_config
from test_pipeline import PASS2, RESULT_TEXT, _filing, _pdf, build, rows

from bse_intel import critic
from bse_intel.ai.gateway import AIGateway
from bse_intel.sinks.local import LocalSink
from bse_intel.timeutil import now_ist

CARD = {
    "headline": "Demo Cement Q2 revenue up 32% YoY to ₹120 Cr",
    "takeaway": "Revenue up a third on volumes",
    "what_happened": [{"text": "Revenue ₹120 Cr vs ₹90.9 Cr", "quote": "Revenue from operations 12,000.00 9,090.91"},
                      {"text": "PAT ₹15 Cr", "quote": None}],
    "why_it_matters": [{"text": "Beats guidance", "basis": "MEMORY", "memory_refs": ["g1"], "quote": None}],
    "call_takeaways": [{"text": "Capex of ₹500 Cr planned", "quote": "capex", "verified": False}],
}
VIEW = {"guidance": [{"id": "g1", "statement": "Revenue of ₹110 Cr in Q2", "given_on": "2026-07-20"}]}
FILING = "Statement of results (Rs. in lakhs). Revenue from operations 12,000.00 9,090.91. Net profit 1,500.00."
REPLY = {"points": [{"id": "headline", "verdict": "OK"},
                    {"id": "what_happened.0", "verdict": "ok", "reason": ""},
                    {"id": "what_happened.1", "verdict": "invented", "reason": "PAT not in excerpt", "corrected": None},
                    {"id": "why_it_matters.0", "verdict": "unsupported cause", "reason": "memory gives ₹110 Cr guidance"},
                    {"id": "bogus", "verdict": "MAYBE"}]}
PROVIDERS = {name: {"base_url": f"https://{name}.invalid/v1", "api_key_env": f"{name.upper()}_KEY"}
             for name in ("gemini", "mistral", "groq")}
ENV = {"GEMINI_KEY": "g", "MISTRAL_KEY": "m", "GROQ_KEY": "q"}
ROUTE = {"critic": [{"provider": "gemini", "model": "gemini-3.1-flash-lite", "max_share": 0.6, "limits": {"rpd": 100}},
                    {"provider": "mistral", "model": "mistral-small-2603", "max_share": 0.5},
                    {"provider": "groq", "model": "openai/gpt-oss-20b", "max_share": 0.75}]}


def job(news_id="n1", writer="openrouter/nvidia/nemotron-3.5-super-vl:free"):
    return critic.build_job(news_id, CARD, writer, FILING, VIEW, "2026-10-20T10:00:00+05:30", "RESULTS")


class RecordingSink:
    def __init__(self):
        self.objects, self.executed = {}, []

    def put_object(self, key, body, content_type="application/json"):
        self.objects[key] = body

    def get_object(self, key):
        return self.objects.get(key)

    def list_objects(self, prefix):
        return [k for k in self.objects if k.startswith(prefix)]

    def execute(self, statement, rows):
        self.executed.append(statement)
        return 0


def gateway(script, usage_today=None, env=ENV):
    fake = FakeProvider(script)
    return AIGateway(gateway_config(ROUTE, PROVIDERS), client_factory=lambda *a: fake, env=env,
                     usage_today=usage_today), fake


def test_the_reply_is_read_leniently_and_every_point_gets_a_verdict():
    reply = critic.CriticReply.model_validate(REPLY)
    assert [(p.id, p.verdict) for p in reply.points] == [
        ("headline", "OK"), ("what_happened.0", "OK"), ("what_happened.1", "INVENTED"),
        ("why_it_matters.0", "UNSUPPORTED_CAUSE")]   # an unknown verdict is dropped, not guessed
    body = critic.record(job(), reply, "gemini/gemini-3.1-flash-lite", 2.0)
    verdicts = {p["id"]: p["verdict"] for p in body["points"]}
    # the unverified call takeaway is not on the face, so it is not judged; the takeaway the reply left out is MISSING
    assert verdicts == {"headline": "OK", "takeaway": critic.MISSING, "what_happened.0": "OK",
                        "what_happened.1": "INVENTED", "why_it_matters.0": "UNSUPPORTED_CAUSE"}
    assert body["counts"] == {"OK": 2, critic.MISSING: 1, "INVENTED": 1, "UNSUPPORTED_CAUSE": 1}
    assert body["mode"] == "shadow"


def test_the_job_carries_the_window_around_each_quote_and_the_memory_it_cites():
    points = {p["id"]: p for p in job()["points"]}
    assert "12,000.00 9,090.91" in points["what_happened.0"]["excerpt"]
    assert points["what_happened.1"]["excerpt"] is None
    assert points["why_it_matters.0"]["memory"][0]["id"] == "g1"
    text = critic.render(job())
    assert "POINT why_it_matters.0" in text and "MEMORY g1 (guidance)" in text and "(none given)" in text
    long = "x " * 5000 + FILING + " y" * 5000
    assert len(critic.excerpt(long, "Revenue from operations 12,000.00")) < 1400


def test_a_card_is_never_changed_and_no_database_row_is_written():
    card = copy.deepcopy(CARD)
    gw, fake = gateway({"gemini-3.1-flash-lite": [REPLY]})
    sink = RecordingSink()
    counts = critic.run([critic.build_job("n1", card, "zai/glm-4.5-flash", FILING, VIEW)], gw, sink, "sys", None, 8)
    assert card == CARD and sink.executed == []
    assert list(sink.objects) == ["evidence/critic/n1.json"] and critic.key("n1") == "evidence/critic/n1.json"
    stored = json.loads(sink.objects["evidence/critic/n1.json"])
    assert stored["critic"] == "gemini/gemini-3.1-flash-lite" and stored["writer"] == "zai/glm-4.5-flash"
    assert counts["cards"] == 1 and counts["flagged_points"] == 2 and counts["flagged_cards"] == 1
    assert counts["by_verdict"]["INVENTED"] == 1


def test_the_critic_is_never_of_the_writers_family():
    assert critic.family("gemini/gemini-3.6-flash") == critic.family("gemini/gemini-3.1-flash-lite") == "gemini"
    assert critic.family("openrouter/nvidia/nemotron-3.5-super-vl:free") == "nemotron"
    assert critic.family("groq/openai/gpt-oss-20b") == "gpt-oss"
    gw, fake = gateway({"mistral-small-2603": [REPLY]})
    critic.run([job(writer="gemini/gemini-3.6-flash")], gw, RecordingSink(), "sys", None, 8)
    assert [c["model"] for c in fake.calls] == ["mistral-small-2603"]


def test_spare_quota_only_a_model_past_its_share_is_skipped_and_the_run_stops_asking():
    used = [{"provider": "gemini", "model": "gemini-3.1-flash-lite", "requests": 60}]   # 60 of 95: past 60%
    gw, fake = gateway({"gemini-3.1-flash-lite": [REPLY]}, usage_today=used, env={"GEMINI_KEY": "g"})
    sink = RecordingSink()
    counts = critic.run([job("n1"), job("n2")], gw, sink, "sys", None, 8)
    assert fake.calls == [] and sink.objects == {}
    assert counts["stopped"] == "quota used" and counts["not_reached"] == 2 and counts["cards"] == 0


def test_at_most_max_cards_a_run_and_never_past_the_runs_time():
    gw, fake = gateway({"gemini-3.1-flash-lite": [REPLY]})
    counts = critic.run([job("n1"), job("n2"), job("n3")], gw, RecordingSink(), "sys", None, 2)
    assert counts["cards"] == 2 and counts["not_reached"] == 1 and len(fake.calls) == 2
    gw, fake = gateway({"gemini-3.1-flash-lite": [REPLY]})
    counts = critic.run([job("n1")], gw, RecordingSink(), "sys", deadline=100.0, max_cards=8, clock=lambda: 90.0)
    assert fake.calls == [] and counts["stopped"] == "run time used"


def test_a_failing_critic_never_raises_and_stops_after_two_failures():
    gw, fake = gateway({"gemini-3.1-flash-lite": ["not json"], "mistral-small-2603": ["nope"],
                        "openai/gpt-oss-20b": ["{}"]})
    counts = critic.run([job("n1"), job("n2"), job("n3")], gw, RecordingSink(), "sys", None, 8)
    assert counts["failed"] == 2 and counts["stopped"] == "critic calls failing" and counts["cards"] == 0


def test_verdicts_are_stored_under_a_prefix_the_worker_and_sync_allow():
    from pathlib import Path

    from bse_intel import sync

    assert critic.key("n/../1 x") == "evidence/critic/n1x.json"
    assert any(critic.PREFIX.startswith(p) for p in sync.OBJECT_PREFIXES)
    worker = (Path(__file__).resolve().parents[2] / "web" / "worker" / "internal.ts").read_text()
    allowed = re.search(r"const OBJECT_PREFIXES = \[([^\]]*)\]", worker).group(1)
    assert any(critic.PREFIX.startswith(p) for p in re.findall(r'"([^"]+)"', allowed))


def test_export_lists_verdicts_since_a_day():
    sink = RecordingSink()
    for news_id, at in (("old", "2026-10-19T23:00:00+05:30"), ("new", "2026-10-21T09:00:00+05:30")):
        sink.put_object(critic.key(news_id), json.dumps({"news_id": news_id, "critiqued_at": at, "points": []}).encode())
    assert [b["news_id"] for b in critic.export(sink, "2026-10-20")] == ["new"]
    assert [b["news_id"] for b in critic.export(sink, "2026-10-19", "2026-10-20")] == ["old"]


def _live(settings, on: bool):
    settings = replace(settings, critic=on)
    now = now_ist() - timedelta(minutes=30)
    filing = _filing("n-res", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    script = {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)],
              "gemini-3.1-flash-lite": [{"points": [{"id": "headline", "verdict": "OVERSTATED", "reason": "x"}]}]}
    pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf(RESULT_TEXT)}, script,
                                 env={"GROQ_API_KEY": "g", "OPENROUTER_API_KEY": "o", "GEMINI_API_KEY": "k",
                                      # the writer of another family than the critic's, now that it is a spare
                                      "ONLY_MODEL": "openrouter:nvidia/nemotron-3.5-super-vl:free"})
    stats = pipeline.run("live", time_budget_s=120)
    return stats, sink, fake


def test_a_live_run_stores_the_verdicts_after_the_card_and_leaves_the_card_as_written(settings):
    stats, sink, fake = _live(settings, True)
    (card,) = rows(sink, "select card_json, held, needs_review, headline from cards")
    stored = json.loads(sink.get_object("evidence/critic/n-res.json"))
    assert stored["writer"].startswith("openrouter/") and stored["critic"] == "gemini/gemini-3.1-flash-lite"
    assert stored["points"][0]["verdict"] == "OVERSTATED"
    assert "critic" not in json.loads(card["card_json"]) and card["held"] == 0   # shadow: the card is not touched
    assert stats.critic["cards"] == 1 and stats.critic["by_verdict"]["OVERSTATED"] == 1
    (run,) = rows(sink, "select stats_json from pipeline_runs")
    assert json.loads(run["stats_json"])["critic"]["cards"] == 1
    usage = {r["model"]: r["requests"] for r in rows(sink, "select * from provider_usage")}
    # the critic call and the blind vote (plan change 6), each counted on the model's own day
    assert usage.get("gemini-3.1-flash-lite") == 2


def test_critic_off_switch(settings, tmp_path):
    stats, sink, fake = _live(settings, False)
    assert "gemini-3.1-flash-lite" not in [c["model"] for c in fake.calls]
    assert sink.list_objects("evidence/critic/") == [] and stats.critic == {}
    assert len(rows(sink, "select news_id from cards")) == 1


def test_the_critic_route_uses_no_card_writer_and_no_paid_or_shared_allowance(settings):
    config = settings.load_toml("providers.toml")
    writers = {(e["provider"], e["model"]) for name, route in config["routes"].items() if name.startswith("pass2")
               for e in route}
    entries = config["routes"]["critic"]
    assert entries and all(e.get("max_share") and 0 < e["max_share"] < 1 for e in entries)
    for e in entries:
        assert (e["provider"], e["model"]) not in writers
        assert not config["providers"][e["provider"]].get("paid")
        assert e["provider"] != "openrouter"   # one daily allowance shared with a writer
    assert critic.ROUTE == "critic" and LocalSink   # the sink the pipeline stores verdicts through


def test_the_blind_vote_compares_enums_and_takes_the_conservative_side():
    """Plan change 6 (shadow): a vote from the filing's opening alone; where it differs, the lower impact and the less
    advanced deal stage; event type is only flagged."""
    from bse_intel.critic import VoteReply, card_enums, compare_votes

    card = {"event_type": "M_AND_A", "impact_level": "HIGH", "tone": "POSITIVE", "deal_value": {"stage": "COMPLETED"}}
    enums = card_enums(card)
    assert enums == {"event_type": "M_AND_A", "impact_level": "HIGH", "tone": "POSITIVE", "deal_stage": "COMPLETED"}
    votes = compare_votes(enums, VoteReply.model_validate({"event_type": "m and a", "impact_level": "moderate",
                                                           "tone": "POSITIVE", "deal_stage": "board approved"}))
    assert votes["event_type"]["agree"] and votes["tone"]["agree"]
    assert votes["impact_level"] == {"card": "HIGH", "vote": "MODERATE", "agree": False, "conservative": "MODERATE"}
    assert votes["deal_stage"]["conservative"] == "BOARD_APPROVED"
    other = compare_votes({"event_type": "RESULTS"}, VoteReply.model_validate({"event_type": "OTHER"}))
    assert other["event_type"]["conservative"] is None
