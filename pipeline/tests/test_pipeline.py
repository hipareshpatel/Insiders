"""End to end: discovery -> rules -> Pass 1 -> PDF -> Pass 2 -> memory -> cards -> alerts,
against the LocalSink (real SQLite running the same SQL files as D1)."""

from __future__ import annotations

import pytest

import json
import time
from datetime import timedelta

import pymupdf
from conftest import FakeProvider, api_error, openai

from bse_intel.ai.gateway import AIGateway
from bse_intel.dossier import new_dossier
from bse_intel.models import Filing
from bse_intel.pipeline import Pipeline
from bse_intel.sinks.local import LocalSink
from bse_intel.timeutil import now_ist


def _pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(36, 36, 560, 800), text, fontsize=9)
    return doc.tobytes()


class FakeBse:
    def __init__(self, filings: list[Filing], pdfs: dict[str, bytes]):
        self.filings = filings
        self.pdfs = pdfs

    def announcements(self, day, day_to=None, known=None, scrip=""):
        self.pages = getattr(self, "pages", 0) + 1
        last = (day_to or day).isoformat()
        for f in self.filings:
            if day.isoformat() <= f.filing_date <= last and (not scrip or f.scrip_code == scrip):
                yield f.model_copy()

    def download(self, url, max_bytes=None):
        return self.pdfs.get(url)

    def results_xbrl(self, scrip_code):
        return getattr(self, "archive", {}).get(scrip_code, [])


def _filing(news_id, headline, when, category="", subcategory="", scrip="999001", name="Demo Cement Ltd"):
    return Filing(news_id=news_id, scrip_code=scrip, company_name=name, headline=headline, subject=headline,
                  category=category, subcategory=subcategory, filed_at=when.isoformat(timespec="seconds"),
                  filing_date=when.date().isoformat(), pdf_url=f"https://bse.invalid/{news_id}.pdf", symbol="DEMOCEM")


RESULT_TEXT = ("Statement of unaudited financial results for the quarter ended 30.09.2026 (Rs. in lakhs). "
               "Revenue from operations 12,000.00 9,090.91. Net profit 1,500.00. Trade receivables 4,000.")

PASS2 = {
    "is_material": True, "event_type": "RESULTS",
    "card": {
        "impact_level": "HIGH",
        "headline": "Demo Cement Q2 revenue up 32% YoY to ₹120 Cr; PAT ₹15 Cr",
        "what_happened": ["Revenue ₹120 Cr vs ₹90.9 Cr a year ago", "PAT ₹15 Cr"],
        "why_it_matters": [{"text": "Beats the run-rate implied by guidance", "basis": "MEMORY", "memory_refs": ["g_nonexistent"]}],
        "missing_disclosures": ["No volume or realisation data"],
        "notable_changes": [{"metric": "revenue", "previous": "₹90.9 Cr", "current": "₹120 Cr", "change": "+32%", "direction": "positive"}],
    },
    "timeline_entry": "Q2FY27 revenue ₹120 Cr (+32% YoY), PAT ₹15 Cr.",
    "dossier_delta": {
        "financial_metrics": [{"metric": "revenue", "period": "Q2FY27", "value": 120, "yoy_pct": 32},
                              {"metric": "revenue", "period": "Q2FY26", "value": 90.91}],
        "upcoming_events": [{"event_type": "AGM", "date": "2027-08-20", "description": "AGM"}],
        "guidance": [{"statement": "Commission 2 MTPA grinding unit", "due": "Q4FY27", "source_type": "PRESS"}],
    },
}


TRIAL_WRITERS = ("minimax/minimax-m3.1-flash:free", "google/gemma-4-31b-it:free")


def build(settings, filings, pdfs, script, env=None):
    sink = LocalSink(settings)
    fake = FakeProvider(script)
    config = settings.load_toml("providers.toml")
    # The writers on trial in an audit round (round 7: MiniMax, Gemma) are measured there, not here: these tests script
    # the regular writers, and a share for an unscripted model would make the weighted rotation call it
    for route in config["routes"].values():
        route[:] = [e for e in route if e["model"] not in TRIAL_WRITERS]
    gateway = AIGateway(config, client_factory=lambda *a: fake,
                        env=env if env is not None else {"GROQ_API_KEY": "g", "NVIDIA_API_KEY": "n", "OPENROUTER_API_KEY": "o"})
    pipeline = Pipeline(settings, sink, gateway, bse=FakeBse(filings, pdfs), sleep=lambda s: None)
    return pipeline, sink, fake


def rows(sink, sql, *params):
    return [dict(r) for r in sink._db.execute(sql, params).fetchall()]


@pytest.mark.switches_on("MEMORY_FILE_ONLY")
def test_live_run_end_to_end(settings):
    now = now_ist() - timedelta(minutes=30)
    filings = [
        _filing("n-noise", "Closure of Trading Window", now, "Company Update", "Trading Window"),
        _filing("n-res", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result"),
        _filing("n-amb", "Disclosure under Regulation 30", now + timedelta(minutes=1), "Company Update"),
    ]
    pdfs = {f.pdf_url: _pdf(RESULT_TEXT if f.news_id == "n-res" else "Clarification on news item. No impact.") for f in filings}
    script = {
        "openai/gpt-oss-20b": [{"is_material": False, "event_type": "OTHER", "reason": "routine clarification"}],
        "nvidia/nemotron-3.5-super-vl:free": ["<think>checking memory</think>" + json.dumps(PASS2)],
    }
    pipeline, sink, fake = build(settings, filings, pdfs, script)
    stats = pipeline.run("live", time_budget_s=60)

    status = {r["news_id"]: r["status"] for r in rows(sink, "select news_id, status from filings")}
    assert status == {"n-res": "ANALYZED", "n-amb": "NOT_MATERIAL"}
    assert stats.analyzed == 1 and stats.pass1_rejected == 1 and stats.dropped_rule == 1
    # Rule-dropped noise lives in R2 (one file per day), not in the D1 ledger.
    noise = json.loads(sink.get_object(f"noise/{now.date().isoformat()}/000.json"))
    assert [r[0] for r in noise["rows"]] == ["n-noise"] and noise["fields"][0] == "news_id"
    assert sink.kv_get(f"noise_count:{now.date().isoformat()}") == "1"
    (queued,) = rows(sink, "select subject, symbol from filings where news_id = 'n-res'")
    assert queued["subject"].startswith("Unaudited") and queued["symbol"] == "DEMOCEM"

    (card,) = rows(sink, "select * from cards")
    body = json.loads(card["card_json"])
    # Impact comes from the deterministic score (blueprint §11); the model's call is kept beside it.
    assert card["event_category"] == "RESULTS" and card["needs_review"] == 0
    assert card["impact_level"] == json.loads(card["card_json"])["score"]["impact"] and json.loads(card["card_json"])["model_impact"] == "HIGH"
    assert body["category_tag"] == "RESULTS" and body["model"] == "openrouter/nvidia/nemotron-3.5-super-vl:free"
    assert body["why_it_matters"][0]["memory_refs"] == []  # hallucinated memory id removed
    assert body["grounding"]["score"] >= 0.7
    assert body["notable_changes"][0]["direction"] == "POSITIVE"
    # the model's own reply, kept in the object store (R2 online) beside the card, not in D1 (ai-quality plan item 8)
    import gzip

    assert body["grounding"]["evidence"] == "evidence/n-res.json.gz"
    evidence = json.loads(gzip.decompress(sink.get_object("evidence/n-res.json.gz")))
    (reply,) = evidence["replies"]
    assert evidence["news_id"] == "n-res" and reply["role"] == "writer"
    assert reply["model"] == "openrouter/nvidia/nemotron-3.5-super-vl:free" and "<think>checking memory" in reply["raw"]
    assert "Demo Cement Q2 revenue up 32% YoY" in reply["raw"] and reply["chars"] == len(reply["raw"])

    dossier = sink.get_dossier("999001")
    # a card's reading of its statement figures stays on the card (MEMORY_FILE_ONLY, owner 30 Oct 2026): memory waits for the file
    assert dossier["financial_metrics"] == []
    assert dossier["guidance"][0]["source_news_id"] == "n-res"
    assert dossier["timeline"][0]["summary"].startswith("Q2FY27 revenue")

    archived = json.loads(sink.get_object(f"daily_feed/{now.date().isoformat()}.json"))
    assert [c["news_id"] for c in archived] == ["n-res"]

    events = {r["event_type"] for r in rows(sink, "select event_type from catalysts")}
    assert events == {"AGM", "GUIDANCE_DUE"}
    (company,) = rows(sink, "select card_count, sector, memory_summary_json, earliest_open_due from companies")
    assert company["card_count"] == 1
    # the radar summary rides on the company row: the open promise and its due date
    assert company["earliest_open_due"] == "2027-03-31"
    assert json.loads(company["memory_summary_json"])["open_promises"][0]["statement"].startswith("Commission 2 MTPA")

    (run,) = rows(sink, "select status, stats_json from pipeline_runs")
    assert run["status"] == "OK" and json.loads(run["stats_json"])["analyzed"] == 1
    usage = {(r["provider"], r["model"]): r["requests"] for r in rows(sink, "select * from provider_usage")}
    assert usage == {("groq", "openai/gpt-oss-20b"): 1, ("openrouter", "nvidia/nemotron-3.5-super-vl:free"): 1}

    # A second run is idempotent: nothing is re-analysed or re-sent.
    pipeline2, sink2, fake2 = build(settings, filings, pdfs, script)
    pipeline2.run("live", time_budget_s=60)
    assert fake2.calls == []


def test_quota_ceiling_defers_work_instead_of_failing(settings):
    from dataclasses import replace

    settings = replace(settings, workers=1)  # deterministic call count
    now = now_ist() - timedelta(minutes=5)
    filings = [_filing(f"n{i}", "Unaudited Financial Results for the quarter", now + timedelta(seconds=i), "Result",
                       scrip=str(999000 + i)) for i in range(3)]
    pdfs = {f.pdf_url: _pdf(RESULT_TEXT) for f in filings}
    # Only Nemotron (through OpenRouter) is configured for Pass 2, and it reports its daily quota spent. No NVIDIA key:
    # NVIDIA's own models are spare writers since 22 Oct.
    err = api_error(openai.RateLimitError, 429, "You exceeded your current quota for the day")
    script = {"nvidia/nemotron-3.5-super-vl:free": [err]}
    pipeline, sink, fake = build(settings, filings, pdfs, script, env={"OPENROUTER_API_KEY": "o"})
    pipeline.discover(now.date())
    pipeline.process("2000-01-01", "2100-01-01", time.monotonic() + 30, bulk=False)
    status = {r["news_id"]: (r["status"], r["attempts"]) for r in rows(sink, "select news_id, status, attempts from filings")}
    assert all(s == ("PENDING", 0) for s in status.values()), status  # nothing failed, nothing dropped
    assert pipeline.stats.deferred >= 1 and "quota" in pipeline.stats.stopped_reason
    assert pipeline.stats.failed == 0
    # one try, then the ceiling stops the run instead of hammering the provider
    assert [c["model"] for c in fake.calls] == ["nvidia/nemotron-3.5-super-vl:free"]


def test_backfill_walks_days_in_order_and_marks_complete(settings):
    from dataclasses import replace

    today = now_ist().date()
    start = today - timedelta(days=3)
    settings = replace(settings, backfill_start=start.isoformat())
    filings = [_filing(f"h{i}", "Unaudited Financial Results", now_ist().replace(year=d.year, month=d.month, day=d.day, hour=17) ,
                       "Result") for i, d in enumerate(start + timedelta(days=k) for k in range(3))]
    pdfs = {f.pdf_url: _pdf(RESULT_TEXT) for f in filings}
    seen_order = []

    def respond(kwargs):
        text = kwargs["messages"][1]["content"]
        seen_order.append(text.split("Filed: ")[1][:10])
        return json.dumps(PASS2)

    pipeline, sink, fake = build(settings, filings, pdfs, {"glm-4.5-flash": [respond]},
                                           env={"ZAI_API_KEY": "z"})
    pipeline.run("backfill", time_budget_s=60, max_backfill_days=10)
    assert seen_order == sorted(seen_order) and len(seen_order) == 3
    assert sink.kv_get("backfill:discovered_through") == (today - timedelta(days=1)).isoformat()
    assert sink.kv_get("backfill:complete") == "1"
    timeline = sink.get_dossier("999001")["timeline"]
    assert [t["news_id"] for t in timeline] == ["h0", "h1", "h2"]


def test_backfill_discovers_no_further_day_while_history_waits_to_be_read(settings, monkeypatch):
    """21 Oct 2026: one run discovered 2,737 filings (7,234 D1 rows) of history while the analysis was weeks behind.
    Discovery waits while BACKLOG_MAX history filings are still to read; the live window is not gated."""
    from dataclasses import replace

    from bse_intel import pipeline as pipeline_mod

    today = now_ist().date()
    start = today - timedelta(days=4)
    settings = replace(settings, backfill_start=start.isoformat())
    filings = [_filing(f"h{i}", "Unaudited Financial Results", now_ist().replace(year=d.year, month=d.month, day=d.day, hour=17),
                       "Result") for i, d in enumerate(start + timedelta(days=k) for k in range(4))]
    pipeline, sink, _ = build(settings, filings, {}, {})
    monkeypatch.setattr(pipeline_mod, "BACKLOG_MAX", 1)
    monkeypatch.setattr(pipeline, "_backfill_companies", lambda *a, **k: 1)   # no analysis: the first day stays pending
    pipeline._backfill(today, time.monotonic() + 60, 0, 10, today - timedelta(days=1))
    assert sink.kv_get("backfill:discovered_through") == start.isoformat()     # one day, then the backlog is full
    pipeline._backfill(today, time.monotonic() + 60, 0, 10, today - timedelta(days=1))
    assert sink.kv_get("backfill:discovered_through") == start.isoformat()
    assert "backfill discovery paused" in (pipeline.stats.stopped_reason or "")
    sink.execute("filings_update", [{"news_id": "h0", "status": "ANALYZED", "attempts": 1, "updated_at": "t"}])
    pipeline._backfill(today, time.monotonic() + 60, 0, 10, today - timedelta(days=1))
    assert sink.kv_get("backfill:discovered_through") == (start + timedelta(days=1)).isoformat()


def test_retriage_queues_what_a_narrowed_rule_no_longer_drops(settings):
    """Discovery skips a filing already in its day's noise file, so the 12 annual reports the old "AGM notice"
    rule had taken stayed there after the rule was narrowed (F57). Retriage reads them again from BSE, with
    today's rules; what is still noise stays, and a second pass changes nothing."""
    from bse_intel.pipeline import _noise_row

    when = now_ist().replace(year=2025, month=7, day=15, hour=18, minute=0, second=0, microsecond=0)
    day = when.date().isoformat()
    report = _filing("n-ar", "Notice of the 33rd Annual General Meeting and Annual Report for the Financial Year 2024-25",
                     when, "AGM/EGM", "Reg. 34 (1) Annual Report")
    window = _filing("n-tw", "Closure of Trading Window", when, "Company Update", "Trading Window")
    other = _filing("n-oth", "Notice of the 33rd Annual General Meeting and Annual Report", when, "AGM/EGM",
                    "Reg. 34 (1) Annual Report", scrip="999002", name="Other Ltd")
    pipeline, sink, _ = build(settings, [report, window, other], {}, {})
    old = {f.news_id: _noise_row(f.model_copy(update={"reason": reason}))
           for f, reason in ((report, "AGM notice"), (window, "trading window"), (other, "AGM notice"))}
    pipeline._save_noise(day, old)

    assert pipeline.retriage_company("999001", when.date(), when.date()) == ["n-ar"]
    (queued,) = rows(sink, "select news_id, status, route, event_type, symbol from filings")
    assert queued == {"news_id": "n-ar", "status": "PENDING", "route": "FAST_TRACK", "event_type": "ANNUAL_REPORT",
                      "symbol": "DEMOCEM"}
    assert sorted(pipeline._load_noise(day)) == ["n-oth", "n-tw"]  # another company's filing is left for its own run
    assert pipeline.retriage_company("999001", when.date(), when.date()) == []


@pytest.mark.switches_off("CARD_TWO_PARTS")   # the behaviour before the switch; the switch has its own tests
def test_card_with_wrong_math_is_held_for_review(settings):
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-q", "Unaudited Financial Results for the quarter", now, "Result")
    bad = json.loads(json.dumps(PASS2))
    bad["card"]["quantified_impact"] = [{
        "label": "Annualised interest on new debt", "formula": "new_debt * rate",
        "inputs": [{"name": "new_debt", "value": 1500, "source": "FILING"}, {"name": "rate", "value": 0.09}],
        "result": 300, "unit": "INR_CR",
    }]
    # the second opinion (here the same provider's other model, the only one configured) repeats the mistake
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(bad)]},
                                 env={"OPENROUTER_API_KEY": "o"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    body = outcome.card["card"]
    (q,) = body["quantified_impact"]
    assert q["check"] == "MISMATCH" and q["computed"] == 135.0
    assert outcome.card["needs_review"] == 1  # still published, marked unverified
    assert body["review"]["status"] == "UNRESOLVED" and "formula gives 135" in body["review"]["issues"][0]
    assert "revenue" not in (body["fundamentals"] or {})   # a held card's own figures are not memory's (owner, 25 Oct)
    assert body["pdf_pages"] == 1
    # held: neither its figures nor its line go into memory (owner, 25 Oct 2026, reversing T5 of 20 Oct); with no
    # exchange file to keep, memory is left as it was, and nothing is written before the card's row
    assert sink.get_dossier(f.scrip_code) is None
    pipeline._commit([outcome])
    memory = sink.get_dossier(f.scrip_code) or {}
    assert outcome.card["held"] == 1 and not any(e.get("news_id") == "n-q" for e in memory.get("timeline", []))
    assert not any(m.get("source_news_id") == "n-q" or m.get("value_news_id") == "n-q"
                   for m in memory.get("financial_metrics", []))


def test_backfill_goes_company_by_company_largest_first(settings):
    """Backfill finishes one company's history (in date order) before the next, largest market cap
    first, and does not store the noise rows of backfilled days."""
    from dataclasses import replace

    today = now_ist().date()
    start = today - timedelta(days=3)
    settings = replace(settings, backfill_start=start.isoformat(), workers=1)
    at = lambda k: now_ist().replace(year=(start + timedelta(days=k)).year, month=(start + timedelta(days=k)).month,  # noqa: E731
                                     day=(start + timedelta(days=k)).day, hour=17)
    filings = [
        _filing("tiny0", "Unaudited Financial Results", at(0), "Result", scrip="999008", name="Demo Tiny Ltd"),
        _filing("big1", "Unaudited Financial Results", at(1), "Result"),
        _filing("tiny1", "Unaudited Financial Results", at(1), "Result", scrip="999008", name="Demo Tiny Ltd"),
        _filing("big2", "Unaudited Financial Results", at(2), "Result"),
        _filing("noise", "Closure of Trading Window", at(2), "Company Update", "Trading Window"),
    ]
    pdfs = {f.pdf_url: _pdf(RESULT_TEXT) for f in filings}
    order = []

    def respond(kwargs):
        order.append(kwargs["messages"][1]["content"].split("Company: ")[1].split(" (")[0])
        return json.dumps(PASS2)

    pipeline, sink, _ = build(settings, filings, pdfs, {"glm-4.5-flash": [respond]}, env={"ZAI_API_KEY": "z"})
    sink._db.executemany("INSERT INTO companies (scrip_code, company_name, market_cap_cr) VALUES (?, ?, ?)",
                         [("999001", "Demo Cement Ltd", 4851.0), ("999008", "Demo Tiny Ltd", 20.0)])
    pipeline.run("backfill", time_budget_s=60, max_backfill_days=10)
    assert order == ["Demo Cement Ltd", "Demo Cement Ltd", "Demo Tiny Ltd", "Demo Tiny Ltd"]
    assert [d["news_id"] for d in (sink.get_dossier("999008") or {}).get("timeline", [])] == ["tiny0", "tiny1"]
    assert not rows(sink, "SELECT news_id FROM filings WHERE news_id = 'noise'")  # counted, not stored
    assert sink.kv_get(f"noise_count:{(start + timedelta(days=2)).isoformat()}") == "1"
    assert sink.kv_get("backfill:complete") == "1"


def test_live_filing_waits_for_its_company_history(settings):
    """A live filing from a company whose history is still queued gets that history first."""
    from dataclasses import replace

    today = now_ist().date()
    settings = replace(settings, backfill_start=(today - timedelta(days=30)).isoformat(), workers=1)
    old = now_ist().replace(hour=17) - timedelta(days=20)
    history = _filing("old", "Unaudited Financial Results", old, "Result")
    live = _filing("new", "Unaudited Financial Results", now_ist() - timedelta(minutes=5), "Result")
    seen = []

    def respond(kwargs):
        seen.append(kwargs["messages"][1]["content"].split("Filed: ")[1][:10])
        return json.dumps(PASS2)

    pipeline, sink, _ = build(settings, [history, live], {f.pdf_url: _pdf(RESULT_TEXT) for f in (history, live)},
                              {"glm-4.5-flash": [respond], "nvidia/nemotron-3.5-super-vl:free": [respond]},
                              env={"ZAI_API_KEY": "z", "NVIDIA_API_KEY": "n", "OPENROUTER_API_KEY": "o"})
    pipeline.discover(old.date())  # as an earlier backfill run would have
    sink.kv_set("backfill:discovered_through", (today - timedelta(days=1)).isoformat(), "now")
    pipeline.run("live", time_budget_s=60)
    assert seen == [old.date().isoformat(), today.isoformat()]  # history first, then the live filing
    cards = {r["news_id"]: r for r in rows(sink, "SELECT news_id, memory_complete FROM cards")}
    assert cards["new"]["memory_complete"] == 1


@pytest.mark.switches_off("CARD_TWO_PARTS")   # the behaviour before the switch; the switch has its own tests
def test_second_opinion_from_another_provider_corrects_the_card(settings):
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-q2", "Unaudited Financial Results for the quarter", now, "Result")
    bad = json.loads(json.dumps(PASS2))
    bad["card"]["what_happened"] = ["Revenue ₹120 Cr vs ₹90.9 Cr a year ago", "PAT ₹17.5 Cr"]  # PAT was ₹15 Cr
    bad["card"]["why_it_matters"] = [{"text": "Record quarterly revenue for the company", "basis": "FILING"}]
    good = json.loads(json.dumps(PASS2))
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"glm-4.5-flash": [json.dumps(bad)], "nvidia/nemotron-3.5-super-vl:free": [json.dumps(good)]},
                                 env={"NVIDIA_API_KEY": "n", "OPENROUTER_API_KEY": "o", "ZAI_API_KEY": "z"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    first, second = fake.calls
    assert first["model"] == "glm-4.5-flash" and second["model"] == "nvidia/nemotron-3.5-super-vl:free"
    verify_prompt = second["messages"][1]["content"]
    assert "DRAFT REPLY" in verify_prompt and "17.5" in verify_prompt and 'Claim not supported by the sources: "Record quarterly revenue' in verify_prompt
    body = outcome.card["card"]
    assert outcome.card["needs_review"] == 0 and body["what_happened"][1]["text"] == "PAT ₹15 Cr"
    assert body["review"]["status"] == "CORRECTED" and body["review"]["checked_by"] == "openrouter/nvidia/nemotron-3.5-super-vl:free"
    assert body["model"] == "openrouter/nvidia/nemotron-3.5-super-vl:free" and len(body["review"]["fixed"]) == 2


@pytest.mark.switches_off("CARD_TWO_PARTS")   # the behaviour before the switch; the switch has its own tests
def test_one_unmatched_amount_gets_a_second_opinion_even_above_the_review_threshold(settings):
    """Ahluwalia's card had EBITDA ₹756 Cr for ₹75.6 Cr (a lakh table): 76% of its numbers matched,
    above the review threshold, so it went out unchecked. Any unmatched amount now asks a second provider."""
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-q3", "Unaudited Financial Results for the quarter", now, "Result")
    bad = json.loads(json.dumps(PASS2))
    bad["card"]["what_happened"] = ["Revenue ₹120 Cr vs ₹90.9 Cr a year ago", "PAT ₹16.5 Cr"]  # PAT was ₹15 Cr
    good = json.loads(json.dumps(PASS2))
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"glm-4.5-flash": [json.dumps(bad)], "nvidia/nemotron-3.5-super-vl:free": [json.dumps(good)]},
                                 env={"NVIDIA_API_KEY": "n", "OPENROUTER_API_KEY": "o", "ZAI_API_KEY": "z"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert len(fake.calls) == 2
    assert "₹ lakh ÷ 100 = ₹ Cr" in fake.calls[1]["messages"][1]["content"]
    body = outcome.card["card"]
    assert body["review"]["status"] == "CORRECTED" and body["what_happened"][1]["text"] == "PAT ₹15 Cr"


def test_a_lakh_figure_read_at_the_wrong_scale_is_corrected_without_a_second_model(settings):
    """"PAT ₹150 Cr" from "Net profit 1,500.00" under "(Rs. in lakhs)": only ₹15 Cr fits, so code
    corrects the card and memory, and no second provider is asked."""
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-q4", "Unaudited Financial Results for the quarter", now, "Result")
    bad = json.loads(json.dumps(PASS2))
    bad["card"]["what_happened"] = ["Revenue ₹120 Cr vs ₹90.9 Cr a year ago", "PAT ₹150 Cr"]
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(bad)]}, env={"NVIDIA_API_KEY": "n", "OPENROUTER_API_KEY": "o"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    body = outcome.card["card"]
    assert len(fake.calls) == 1 and body["review"] is None
    assert body["what_happened"][1]["text"] == "PAT ₹15 Cr" and body["grounding"]["unit_fixes"] == {"150": "15"}


def test_one_card_per_company_per_results_quarter(settings):
    """Decision D20: Novartis filed one quarter's results as three documents and got three cards. The
    first gets the card; a later document of the same quarter is linked to it, with no AI call."""
    from dataclasses import replace

    settings = replace(settings, one_card_per_results_quarter=True, workers=1)
    now = now_ist() - timedelta(hours=3)
    first = _filing("q-1", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    again = _filing("q-2", "Outcome of Board Meeting - results", now + timedelta(hours=1), "Board Meeting")
    pipeline, sink, fake = build(settings, [first, again], {f.pdf_url: _pdf(RESULT_TEXT) for f in (first, again)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)]})
    one = pipeline.analyze(first.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    pipeline._results_quarters.clear()  # a later run: only memory knows the quarter has its card
    two = pipeline.analyze(again.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert one.card is not None and len(fake.calls) == 1
    assert two.update["status"] == "DUPLICATE" and two.update["reason"] == "duplicate of q-1 (same results quarter Q2FY27, D20)"


def test_an_earlier_results_filing_read_after_the_later_one_takes_the_quarter_and_leaves_one_card(settings):
    """Sunteck's Q1FY27 statement (18:07) was read again after its press release (18:48) had the quarter's card, and
    Sun Pharma's Q4FY26 outcome, filed twice, likewise: D20 only looked at filings filed before the one read, so both
    copies kept a card (2026-10-20). The earlier filing now takes the quarter and the later one becomes its duplicate,
    committed together, with its facts out of memory."""
    from dataclasses import replace

    settings = replace(settings, one_card_per_results_quarter=True, workers=1, second_opinion=False)
    now = now_ist() - timedelta(hours=3)
    first = _filing("q-1", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    later = _filing("q-2", "Press release on the results", now + timedelta(minutes=41), "Result")
    pipeline, sink, fake = build(settings, [first, later], {f.pdf_url: _pdf(RESULT_TEXT) for f in (first, later)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)] * 2, "glm-4.5-flash": [json.dumps(PASS2)] * 2})
    pipeline._commit([pipeline.analyze(later.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))])
    pipeline._results_quarters.clear()  # a later run: only memory knows the quarter has its card
    outcomes = pipeline._process_group([first.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"})],
                                       time.monotonic() + 600, False, True)
    pipeline._commit(outcomes)
    assert [(o.update["news_id"], o.update["status"]) for o in outcomes] == [("q-1", "ANALYZED"), ("q-2", "DUPLICATE")]
    assert outcomes[1].update["reason"] == "duplicate of q-1 (same results quarter Q2FY27, D20)"
    assert [r[0] for r in sink._db.execute("SELECT news_id FROM cards")] == ["q-1"]
    assert "q-2" not in {t["news_id"] for t in sink.get_dossier("999001")["timeline"]}
    # and the later copy read again is the duplicate of the earlier one, as before
    pipeline._results_quarters.clear()
    again = pipeline.analyze(later.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert again.update["status"] == "DUPLICATE" and again.update["reason"] == "duplicate of q-1 (same results quarter Q2FY27, D20)"


def test_a_later_results_filing_owns_a_quarter_only_when_it_is_its_own(settings, monkeypatch):
    """The next quarter's results report this quarter as their comparative: re-reading Q2's statement must not take
    Q3's card away. A later card that is held owns nothing, and no later card is replaced by a card that is held."""
    from bse_intel.pipeline import Outcome

    pipeline, sink, _ = build(settings, [], {}, {})
    monkeypatch.setattr(pipeline, "_card_held", lambda n: n == "q-held")
    f = _filing("q-2", "Unaudited Financial Results", now_ist() - timedelta(days=90))
    later = (now_ist() - timedelta(days=1)).isoformat(timespec="seconds")
    metric = lambda period, n: {"metric": "revenue", "period": period, "value": 1.0, "unit": "INR_CR", "as_of": later,  # noqa: E731
                                "source_news_id": n, "sources": [{"news_id": n, "as_of": later, "value": 1.0, "unit": "INR_CR"}]}
    dossier = {"timeline": [{"news_id": n, "date": later, "event_type": "RESULTS"} for n in ("q-next", "q-held")],
               "financial_metrics": [metric("Q2FY27", "q-next"), metric("Q3FY27", "q-next"), metric("Q2FY27", "q-held")]}
    assert pipeline._same_results_quarter(f, dossier, "Q2FY27") is None and "q-2" not in pipeline._superseding
    dossier["financial_metrics"].append(metric("Q2FY27", "q-copy"))
    dossier["timeline"].append({"news_id": "q-copy", "date": later, "event_type": "RESULTS"})
    pipeline._results_quarters.clear()
    assert pipeline._same_results_quarter(f, dossier, "Q2FY27") is None
    assert pipeline._superseding["q-2"] == (["q-copy"], "Q2FY27")
    held = Outcome({"news_id": "q-2", "status": "ANALYZED"}, card={"held": 1})
    assert pipeline._supersede(f, held) == [] and "q-2" not in pipeline._superseding


def test_a_consolidated_file_takes_the_quarter_from_a_standalone_card_and_never_the_other_way(settings):
    """Owner, 30 Oct 2026: "if consolidated results available, use it only, if not available, use standalone. Make a rule to
    avoid two cards". A company that files its standalone results first and its consolidated ones in a later filing gets
    one card, the consolidated one: the standalone card becomes its duplicate once the consolidated card is published."""
    pipeline, sink, _ = build(settings, [], {}, {})
    f = _filing("q-cons", "Consolidated Unaudited Financial Results", now_ist() - timedelta(hours=1))
    earlier = (now_ist() - timedelta(hours=2)).isoformat(timespec="seconds")

    def metric(n, basis):
        return {"metric": "revenue", "period": "Q2FY27", "value": 1.0, "unit": "INR_CR", "as_of": earlier, "basis": basis,
                "source_news_id": n, "sources": [{"news_id": n, "as_of": earlier, "value": 1.0, "unit": "INR_CR", "basis": basis}]}

    dossier = {"timeline": [{"news_id": "q-sa", "date": earlier, "event_type": "RESULTS"}],
               "financial_metrics": [metric("q-sa", "STANDALONE")]}
    assert pipeline._same_results_quarter(f, dossier, "Q2FY27", basis="CONSOLIDATED") is None
    assert pipeline._superseding["q-cons"] == (["q-sa"], "Q2FY27")
    # a standalone file never takes the quarter from a standalone or consolidated card
    pipeline._results_quarters.clear(), pipeline._superseding.clear()
    sa = _filing("q-sa2", "Standalone Unaudited Financial Results", now_ist() - timedelta(minutes=30))
    assert pipeline._same_results_quarter(sa, dossier, "Q2FY27", basis="STANDALONE") == ("q-sa", "Q2FY27")
    dossier["financial_metrics"] = [metric("q-c1", "CONSOLIDATED")]
    dossier["timeline"] = [{"news_id": "q-c1", "date": earlier, "event_type": "RESULTS"}]
    pipeline._results_quarters.clear()
    assert pipeline._same_results_quarter(sa, dossier, "Q2FY27", basis="STANDALONE") == ("q-c1", "Q2FY27")
    # and a consolidated card is never taken by another consolidated file (the first keeps it, as before)
    pipeline._results_quarters.clear()
    assert pipeline._same_results_quarter(f, dossier, "Q2FY27", basis="CONSOLIDATED") == ("q-c1", "Q2FY27")
    # in one run: a standalone claim gives way to a consolidated file of the same quarter
    pipeline._results_quarters.clear(), pipeline._superseding.clear()
    empty = {"timeline": [], "financial_metrics": []}
    assert pipeline._same_results_quarter(sa, empty, "Q2FY27", basis="STANDALONE") is None
    assert pipeline._same_results_quarter(f, empty, "Q2FY27", basis="CONSOLIDATED") is None
    assert pipeline._superseding["q-cons"] == (["q-sa2"], "Q2FY27")


def test_a_press_release_naming_no_quarter_is_the_duplicate_of_the_results_card_before_it(settings):
    """28-29 Oct 2026: 13 companies had two results cards for Q2FY27, the statement's and a press release's minutes later
    (eClerx 18:58 and 19:09): "Q2 FY27" is no "quarter ended", so D20 had no quarter and never ran. Within three days of
    a results card a results filing that names no quarter takes that card's quarter."""
    from dataclasses import replace

    from bse_intel.pipeline import companion_quarter

    settings = replace(settings, one_card_per_results_quarter=True, workers=1)
    now = now_ist() - timedelta(hours=3)
    first = _filing("q-1", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    release = _filing("q-pr", "Press Release", now + timedelta(minutes=11), "Result")
    text = "Press release. eClerx Q2 FY27 revenue rose 17.1% YoY; profit grew 9.8% QoQ. " * 3
    pipeline, sink, fake = build(settings, [first, release], {first.pdf_url: _pdf(RESULT_TEXT), release.pdf_url: _pdf(text)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)] * 2})
    pipeline._commit([pipeline.analyze(first.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))])
    pipeline._results_quarters.clear()   # a later run: only memory knows the quarter has its card
    assert companion_quarter(release, sink.get_dossier(first.scrip_code)) == "Q2FY27"
    two = pipeline.analyze(release.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert two.update["status"] == "DUPLICATE" and two.update["reason"] == "duplicate of q-1 (same results quarter Q2FY27, D20)"
    assert len(fake.calls) == 1, "no AI call for the duplicate"
    # a week later the same words are a new filing, not a companion
    late = _filing("q-late", "Press Release", now + timedelta(days=8), "Result")
    assert companion_quarter(late, sink.get_dossier(first.scrip_code)) is None


def test_a_board_outcome_typed_as_a_corporate_action_still_takes_part_in_d20(settings):
    """Kapston filed its Q2FY27 board outcome (results and a 5:1 stock split) twice, four minutes apart (O3, 2026-10-20).
    The copy typed CORPORATE_ACTION was made RESULTS only after pass 2, so it skipped the quarter's claim and the
    results XBRL, and the feed had two results cards for one quarter. The statement in the filing now decides first."""
    from dataclasses import replace

    from bse_intel.pipeline import carries_results

    assert carries_results("CORPORATE_ACTION", RESULT_TEXT) and not carries_results("ORDER_WIN", RESULT_TEXT)
    assert not carries_results("CORPORATE_ACTION", "Board approved a 5:1 split of each equity share of Rs. 5.")
    settings = replace(settings, one_card_per_results_quarter=True, workers=1)
    now = now_ist() - timedelta(hours=3)
    first = _filing("k-1", "Outcome of Board Meeting", now, "Board Meeting")
    again = _filing("k-2", "Outcome of Board Meeting - stock split", now + timedelta(minutes=4), "Board Meeting")
    split = RESULT_TEXT + " The Board approved the sub-division of each equity share of Rs. 5 into 5 shares of Rs. 1."
    pipeline, sink, fake = build(settings, [first, again], {first.pdf_url: _pdf(RESULT_TEXT), again.pdf_url: _pdf(split)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)]})
    one = pipeline.analyze(first.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    pipeline._results_quarters.clear()  # a later run: only memory knows the quarter has its card
    two = pipeline.analyze(again.model_copy(update={"route": "FAST_TRACK", "event_type": "CORPORATE_ACTION"}))
    assert one.card is not None and len(fake.calls) == 1
    assert two.update["status"] == "DUPLICATE" and two.update["reason"] == "duplicate of k-1 (same results quarter Q2FY27, D20)"


@pytest.mark.switches_off("CARD_TWO_PARTS")   # the behaviour before the switch; the switch has its own tests
def test_a_card_the_second_opinion_cannot_fix_is_held_back(settings):
    """A card that failed its checks, went to a second provider and still failed used to be published with
    an "Unverified" mark, so that a material filing was never hidden. On the rebuild that was 117 of 456
    cards, and a flagged card was judged WRONG 52% of the time against 21% for a clean one (audit round 1),
    so for a feed meant to run unattended the trade was the wrong way round. The row is still written in
    full - the digest, the audit export and the review queue read it - but held keeps it out of the feed."""
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-held", "Unaudited Financial Results for the quarter", now, "Result")
    bad = json.loads(json.dumps(PASS2))
    bad["card"]["what_happened"] = ["Revenue ₹120 Cr vs ₹90.9 Cr a year ago", "PAT ₹17.5 Cr"]  # PAT was ₹15 Cr
    bad["card"]["why_it_matters"] = [{"text": "Record quarterly revenue for the company", "basis": "FILING"}]
    # both providers return the same wrong card, so the second opinion resolves nothing
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(bad)],
                                  "glm-4.5-flash": [json.dumps(bad)]},
                                 env={"NVIDIA_API_KEY": "n", "OPENROUTER_API_KEY": "o", "ZAI_API_KEY": "z"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert outcome.card is not None, "the row is still written, so the defect can be seen"
    assert outcome.card["card"]["review"]["status"] == "UNRESOLVED"
    assert outcome.card["held"] == 1
    assert outcome.card["needs_review"] == 1, "a held card is always one for review (audit, 2026-10-18)"


def test_a_fast_track_repeat_is_dropped_before_pass_2(settings):
    """FAST_TRACK skips pass 1, and with it the question of whether the event is already in the feed: 134
    of the 175 duplicate pairs measured on the rebuild had a fast-track later card, so about a quarter of
    pass 2 calls went on events already covered. A deterministic check on BSE's own headline cannot stand
    in - word overlap against the timeline caught 4 of 128, and the best same-domain variant caught 27
    while wrongly dropping 13 real cards - so one small call asks, and code confirms the answer."""
    now = now_ist() - timedelta(minutes=10)
    earlier = (now - timedelta(days=3)).date().isoformat()   # relative: a fixed date fell out of the window (2026-10-20)
    f = _filing("n-deck", "Investor presentation for the quarter ended September 30, 2026", now, "Company Update")
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"ministral-8b-2512": [json.dumps({"duplicate_of": earlier, "why": "deck for those results"})]},
                                 env={"MISTRAL_API_KEY": "m"})
    dossier = new_dossier(f)
    dossier["timeline"] = [{"id": "t1", "news_id": "n-results", "date": f"{earlier}T18:00:00+05:30",
                            "event_type": "RESULTS", "summary": "Q2FY27 results: revenue up 22.6%", "tier": "TIMELINE"}]
    sink.put_dossier(f.scrip_code, dossier)

    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "CONCALL_PRESENTATION"}))
    assert outcome.update["status"] == "DUPLICATE"
    assert "n-results" in outcome.update["reason"] and "before pass 2" in outcome.update["reason"]
    assert outcome.card is None, "no card is written for a repeat"
    # and the expensive call never happened: only the cheap repeat check was made
    assert len(fake.calls) == 1, [c["model"] for c in fake.calls]
    # with the document's opening, not BSE's boilerplate headline alone: from the headline it took a ₹1.73 Cr
    # GST notice for FY22 to repeat a ₹2.64 Cr one for FY20 (re-run of the held cards, 2026-10-18)
    asked = fake.calls[0]["messages"][1]["content"]
    assert "OPENING OF THE DOCUMENT" in asked and "Revenue from operations 12,000.00" in asked


def test_a_fast_track_filing_that_is_not_a_repeat_goes_on_to_pass_2(settings):
    """The other half of the gate: an invented date, or none, must drop nothing."""
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-new", "Unaudited Financial Results for the quarter", now, "Result")
    pipeline, sink, fake = build(
        settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
        {"ministral-8b-2512": [json.dumps({"duplicate_of": "2026-01-01", "why": "nothing on that date"})],
         "nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)],
         "glm-4.5-flash": [json.dumps(PASS2)]},
        env={"MISTRAL_API_KEY": "m", "NVIDIA_API_KEY": "n", "OPENROUTER_API_KEY": "o", "ZAI_API_KEY": "z"})
    dossier = new_dossier(f)
    dossier["timeline"] = [{"id": "t1", "news_id": "n-other", "date": "2026-10-10T18:00:00+05:30",
                            "event_type": "GOVERNANCE", "summary": "Board meeting outcome", "tier": "TIMELINE"}]
    sink.put_dossier(f.scrip_code, dossier)

    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert outcome.update["status"] == "ANALYZED" and outcome.card is not None


def test_a_corrected_card_is_itself_corrected_and_checked(settings):
    """The deterministic fixers used to run on the first card only.

    So a card adopted from the second provider was published having had none of them - no unit slip
    corrected, no deal size recomputed, no exact XBRL value - on exactly the cards that had already
    failed once. Worse, the record stored beside it described the card that had been thrown away: on
    2026-10-17 Novartis FY25 was published at the right Rs 356.27 Cr with a note beside it saying it
    had been changed to Rs 83.88 Cr, which was the discarded card's figure.
    """
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-q2", "Unaudited Financial Results for the quarter", now, "Result")
    bad = json.loads(json.dumps(PASS2))
    bad["card"]["why_it_matters"] = [{"text": "Record quarterly revenue for the company", "basis": "FILING"}]
    # The second provider fixes the claim but reads the statement's lakhs as crore, a slip the code knows
    second = json.loads(json.dumps(PASS2))
    second["card"]["what_happened"] = ["Revenue ₹12,000 Cr vs ₹90.9 Cr a year ago", "PAT ₹15 Cr"]
    second["card"]["headline"] = "Demo Cement Q2 revenue ₹12,000 Cr"
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(bad)],
                                  "glm-4.5-flash": [json.dumps(second)]},
                                 env={"NVIDIA_API_KEY": "n", "OPENROUTER_API_KEY": "o", "ZAI_API_KEY": "z"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    body = outcome.card["card"]
    assert body["model"] == "zai/glm-4.5-flash", "the second provider's card was the one published"
    assert "₹120 Cr" in body["headline"] and "12,000" not in body["headline"], \
        "the adopted card went through the unit fixer too"
    assert body["grounding"]["unit_fixes"] == {"12,000": "120"}, \
        "the record beside the card describes the card that was published"


def test_a_change_the_filing_prints_is_never_recomputed():
    """Greenply's MDF revenue "+39.6% YoY" (the deck prints it) became -70.2%: the card set the quarter against the full
    year, and the fixer recomputed the change from those two figures (held-card audit, 22 Oct 2026)."""
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import fix_change_percentages

    source = "MDF revenue Q2FY27 300.4, FY26 1,008.2 (Rs in crore). MDF revenue grew 39.6% YoY."
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "Q2 results",
        "card": {"impact_level": "MODERATE", "headline": "Greenply Q2", "what_happened": ["MDF grew"],
                 "notable_changes": [{"metric": "mdf_revenue", "previous": "₹1,008.2 Cr", "current": "₹300.4 Cr",
                                      "change": "+39.6% YoY", "direction": "POSITIVE"}]}})
    assert fix_change_percentages(out, (source,)) == []
    assert out.card.notable_changes[0].change == "+39.6% YoY"
    # a % the filing does not print is still recomputed from its two figures
    out.card.notable_changes[0].change = "+45% YoY"
    assert fix_change_percentages(out, (source,)) == ["mdf_revenue: +45% YoY -> -70.2% YoY"]


def test_a_change_of_more_than_a_thousand_percent_is_read_whole():
    """Jubilant's FY25 net profit rose from Rs 72.7 Cr to Rs 836.3 Cr, which the model wrote as
    "+1,050%". The pattern could not read the thousands separator, so it took the change for 50%,
    decided the model was wrong by a factor of twenty and spliced its own figure into the middle of
    the old one: the card recorded "+1,+1050.3%". A turnaround off a small base writes it this way
    every time."""
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import fix_change_percentages

    source = "Net profit for the year 836.3 against 72.7 in the previous year (Rs in crore)"
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "FY25 results",
        "card": {"impact_level": "HIGH", "headline": "FY25 results", "what_happened": ["Profit up sharply"],
                 "notable_changes": [{"metric": "net_profit", "previous": "₹72.7 Cr", "current": "₹836.3 Cr",
                                      "change": "+1,050%", "direction": "POSITIVE"}]}})
    assert fix_change_percentages(out, (source,)) == [], "1,050% is right: 72.7 -> 836.3 is +1,050.3%"
    assert out.card.notable_changes[0].change == "+1,050%"

    out.card.notable_changes[0].change = "+2,400%"      # wrong by far more than the tolerance
    assert fix_change_percentages(out, (source,)) == ["net_profit: +2,400% -> +1050.3%"]
    assert out.card.notable_changes[0].change == "+1050.3%", "the whole number is replaced, not its tail"


def test_a_card_is_not_held_back_only_for_how_it_quoted_the_filing(settings):
    """Every figure of the fact was found in the document; only the sentence around them is the
    model's own wording. Three of Prism Johnson's segment facts were held that way on 2026-10-17,
    each one checked and right. That is worth recording, not worth keeping the card out of the feed."""
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-q2", "Unaudited Financial Results for the quarter", now, "Result")
    card = json.loads(json.dumps(PASS2))
    card["card"]["what_happened"] = [
        {"text": "Revenue ₹120 Cr vs ₹90.9 Cr a year ago",
         "quote": "Revenue rose to Rs 120 crore from Rs 90.9 crore"},   # a paraphrase, figures verified
        {"text": "PAT ₹15 Cr", "quote": "Net profit 1,500.00"}]
    card["card"]["why_it_matters"] = [{"text": "Scale is building", "basis": "FILING",
                                       "quote": "Net profit 1,500.00"}]
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(card)],
                                  "glm-4.5-flash": [json.dumps(card)]},
                                 env={"NVIDIA_API_KEY": "n", "OPENROUTER_API_KEY": "o", "ZAI_API_KEY": "z"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    body = outcome.card["card"]
    assert body["grounding"]["quotes_paraphrased"], "the wording is still reported"
    assert outcome.card["held"] == 0, "but the card reaches the feed"
    # nor is a second provider asked: it was given no issue to fix, and 30 of the 31 cards sent for wording alone
    # came back unresolved (re-run of the held cards, 2026-10-18)
    assert len(fake.calls) == 1 and body.get("review") is None, [c["model"] for c in fake.calls]


def test_a_site_that_does_not_answer_costs_no_attempts_and_stops_the_run(settings):
    """On 2026-10-17 the local web server had exited and a run marked all twenty filings it touched as
    failed in thirty seconds. A filing past its attempt limit is never retried, so in a backfill that is
    silent loss. Now the filing is left as it was, and the run stops after a few in a row."""
    from bse_intel import pipeline as pl
    from bse_intel.sinks.base import SinkUnavailable

    now = now_ist() - timedelta(minutes=10)
    filings = [_filing(f"n-{i}", "Unaudited Financial Results", now, "Result") for i in range(5)]
    pipeline, sink, fake = build(settings, filings, {}, {}, env={})

    def down(*_a, **_k):
        raise SinkUnavailable("the platform API did not answer (ConnectError)")

    pipeline.analyze = down
    outcomes = [pipeline._process_one(f, bulk=True, memory_complete=True) for f in filings[:pl.MAX_UNREACHABLE]]
    assert all(o.update["status"] == "PENDING" and "attempts" not in o.update for o in outcomes), \
        "left as it was: no attempt spent"
    assert pipeline._blocked is not None and "did not answer" in str(pipeline._blocked)


def test_a_results_reading_that_does_not_add_up_goes_to_a_second_provider(settings):
    """With no XBRL behind a results filing the model's reading is all there is, so it has to add up.
    PBT 20 less tax 5 is 15; a reply giving PAT as 17.5 has misread a line, and the second provider is
    told exactly where the gap is."""
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-q2", "Unaudited Financial Results for the quarter", now, "Result")
    bad = json.loads(json.dumps(PASS2))
    bad["dossier_delta"]["financial_metrics"] += [
        {"metric": "pbt", "period": "Q2FY27", "value": 20}, {"metric": "tax_expense", "period": "Q2FY27", "value": 5},
        {"metric": "pat", "period": "Q2FY27", "value": 17.5}]
    good = json.loads(json.dumps(bad))
    good["dossier_delta"]["financial_metrics"][-1]["value"] = 15
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"glm-4.5-flash": [json.dumps(bad)], "nvidia/nemotron-3.5-super-vl:free": [json.dumps(good)]},
                                 env={"NVIDIA_API_KEY": "n", "OPENROUTER_API_KEY": "o", "ZAI_API_KEY": "z"})
    pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert len(fake.calls) == 2, "the figures that did not add up sent the card to a second provider"
    assert "PBT 20.00 - tax 5.00 = 15.00 Cr, but PAT is given as 17.50 Cr" in fake.calls[1]["messages"][1]["content"]


def test_a_text_layer_in_a_broken_or_shifted_font_is_ocrd_not_trusted():
    """32 pages in 4 of 929 cached filings had a text layer long enough to pass for a text page and
    unreadable: Jubilant's statements in a font whose glyphs map to the wrong letters, a takeover
    disclosure in one that shifts every letter three places. None was OCR'd; the model got the garbage."""
    import pymupdf

    from bse_intel.extract import Document, cache_needs_ocr, text_unreadable

    broken = "ŝŶ ŵŝůůŝŽŶͿ zĞĂƌ ŶĚĞĚ ϯϬ ^ĞƉƚĞŵďĞƌ ϯϬ :ƵŶĞ ϯϬ " * 6           # "in million) Year Ended 30"
    shifted = (chr(20) + " FRPSDQ VHFUHWDU " + chr(25) + chr(19) + "#JPDLO" + chr(17) + "FRP 6HQW ") * 12
    assert text_unreadable(broken) and text_unreadable(shifted)
    # what must still be read as it is
    spaces = chr(3).join("Year Ended 31 December Revenue from operations Other income Total income".split()) * 5
    bullets = (chr(7) + " Details of concentration of purchases and sales with trading houses. ") * 8
    ligatures = "Notes forming part of the ﬁnancial statements for the year ended 31 March 2025 " * 6
    assert not any(text_unreadable(t) for t in (spaces, bullets, ligatures))

    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "placeholder")
    doc = Document(pdf.tobytes(), ocr=lambda png: "OCR READ: Revenue from operations 1,234.56")
    doc._digital[0] = broken
    assert doc.page_text(0).startswith("OCR READ"), "an unreadable page goes to OCR like a scanned one"

    assert cache_needs_ocr({"digital": [broken], "ocr": {}})
    assert not cache_needs_ocr({"digital": [broken], "ocr": {"0": "read"}}), "already OCR'd: no re-read"
    assert not cache_needs_ocr({"digital": [ligatures], "ocr": {}})
    # Read again once, not on every run: a page the run never OCR'd (no vision route, the OCR cap, a page the
    # analysis did not reach) stays unread, and the entry written after the re-read says it was checked.
    unread = Document(pdf.tobytes())
    unread._digital[0] = broken
    assert not cache_needs_ocr(unread.to_cache())
    assert not cache_needs_ocr(Document.from_cache(unread.to_cache()).to_cache())
    assert cache_needs_ocr(Document.from_cache({"v": 2, "digital": [broken], "ocr": {}}).to_cache()), \
        "an entry from before the check, kept as a fallback, is still read again later"


def test_a_held_card_does_not_own_its_results_quarter_and_a_not_material_claim_is_given_back(settings):
    """D20 let the first document decide the quarter: in 17 of 43 quarters its card was held and the statement
    itself was marked a duplicate of it, so nothing was published; in 2 a notice typed RESULTS claimed the
    quarter before pass 2, was found not material, and kept it (funnel over the smoke-test companies,
    2026-10-18)."""
    from dataclasses import replace

    settings = replace(settings, one_card_per_results_quarter=True, workers=1,
                       second_opinion=False)
    now = now_ist() - timedelta(hours=3)
    first = _filing("q-1", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    again = _filing("q-2", "Outcome of Board Meeting - results", now + timedelta(hours=1), "Board Meeting")
    pipeline, sink, fake = build(settings, [first, again], {f.pdf_url: _pdf(RESULT_TEXT) for f in (first, again)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2), json.dumps(PASS2)],
                                  "glm-4.5-flash": [json.dumps(PASS2)]})
    one = pipeline.analyze(first.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    pipeline._commit([one])
    sink._db.execute("UPDATE cards SET held = 1 WHERE news_id = 'q-1'")
    pipeline._results_quarters.clear()  # a later run: only memory knows the quarter
    two = pipeline.analyze(again.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert two.card is not None, "the owner's card is held: this document may make the quarter's card"

    # a claim made before pass 2 is given back when the claimant ends without a card
    pipeline._results_quarters[("999001", "Q2FY27")] = "notice-1"
    pipeline._release_claims("notice-1", "NOT_MATERIAL")
    assert ("999001", "Q2FY27") not in pipeline._results_quarters


def test_a_board_meeting_notice_does_not_take_the_results_quarter(settings):
    """Ahluwalia's notice of the meeting that would consider Q3FY25 was typed RESULTS, read "for the quarter ended
    31st December, 2024" as its quarter and claimed it; the statement filed three weeks later was then marked a D20
    duplicate of the notice, and the quarter had no results card (re-run of the held cards, 2026-10-18)."""
    from dataclasses import replace

    from bse_intel.pipeline import results_quarter

    notice_text = ("The meeting of the Board of Directors will be held on Thursday, November 12, 2026 to consider "
                   "the Unaudited Financial Results for the quarter and half year ended 30th September, 2026.")
    assert results_quarter(None, notice_text) is None
    assert results_quarter(None, RESULT_TEXT) == "Q2FY27"

    settings = replace(settings, one_card_per_results_quarter=True, workers=1, second_opinion=False)
    now = now_ist() - timedelta(hours=3)
    notice = _filing("q-0", "Board meeting on 12 November 2026", now - timedelta(days=20), "Board Meeting")
    first = _filing("q-1", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    card = {"is_material": True, "event_type": "RESULTS", "timeline_entry": "Board meets on 12 November 2026 on Q2 results.",
            "card": {"impact_level": "LOW", "headline": "Demo Cement board meets on 12 November 2026 on Q2 results",
                     "what_happened": [{"text": "Board meets on 12 November 2026", "quote": notice_text}]}}

    def reply(kwargs):  # the notice's card, or the statement's
        return json.dumps(card if "November 12" in kwargs["messages"][1]["content"] else PASS2)

    pipeline, sink, fake = build(settings, [notice, first], {notice.pdf_url: _pdf(notice_text), first.pdf_url: _pdf(RESULT_TEXT)},
                                 {model: [reply] * 2 for model in ("nvidia/nemotron-3.5-super-vl:free", "glm-4.5-flash")})
    pipeline._commit([pipeline.analyze(notice.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))])
    assert ("999001", "Q2FY27") not in pipeline._results_quarters
    two = pipeline.analyze(first.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert two.card is not None, two.update


def test_scanned_pages_the_old_ocr_cap_left_unread_are_read_again_once_under_a_higher_cap():
    """The cap went from 6 pages to 20 with local OCR: a long scan cached under 6 had pages 7 on never read,
    and a cached document has no PDF to read them from, so nothing marked the entry stale."""
    from bse_intel.extract import Document, cache_needs_ocr

    scan = {"v": 2, "digital": [""] * 9, "has_image": [True] * 9, "ocr": {str(i): "read" for i in range(6)},
            "unreadable_checked": True}
    assert cache_needs_ocr(scan, max_ocr_pages=20), "written before the cap was recorded: cap 6, pages 6-8 unread"
    assert not cache_needs_ocr(scan, max_ocr_pages=6)
    assert not cache_needs_ocr(scan), "no OCR on this run: nothing to gain"
    assert not cache_needs_ocr({**scan, "ocr_cap": 20}, max_ocr_pages=20), "read once under today's cap"
    assert not cache_needs_ocr({**scan, "ocr": {str(i): "read" for i in range(9)}}, max_ocr_pages=20)
    # kept as the fallback when the exchange refuses the PDF, it keeps its old cap and is still read again later
    assert cache_needs_ocr(Document.from_cache(scan).to_cache(), max_ocr_pages=20)
    assert Document(None, max_ocr_pages=20).to_cache()["ocr_cap"] == 20


def test_a_card_held_in_this_run_gives_back_its_quarter_at_once(settings, monkeypatch):
    """Within one run the owner's claim and its new card decide too: a held owner kept its claim (it is ANALYZED),
    and its new card was not yet committed when the next document asked, so the statement was again a duplicate."""
    from bse_intel.pipeline import Outcome

    pipeline, sink, _ = build(settings, [], {}, {})
    owner = _filing("q-own", "Outcome of Board Meeting", now_ist())
    pipeline._results_quarters[("999001", "Q2FY27")] = "q-own"
    monkeypatch.setattr(pipeline, "_attempt", lambda *a, **k: Outcome({"news_id": "q-own", "status": "ANALYZED"}, card={"held": 1}))
    pipeline._process_one(owner, False, True)
    assert ("999001", "Q2FY27") not in pipeline._results_quarters
    assert pipeline._card_held("q-own"), "known held before its card is committed"


def test_pass_2_says_why_a_filing_is_not_material(settings):
    """Pass 2's verdict was stored as a bare "pass2: not material", so the 70 filings it set aside in the smoke test
    could not be reviewed without reading each PDF; pass 1's reason was always kept (audit, 2026-10-18)."""
    now = now_ist() - timedelta(minutes=10)
    # (a schedule of investor meetings, this test's first filing, now goes to memory before pass 2: memory_only)
    f = _filing("n-nm", "Change in registered office address", now, "Company Update")
    reply = {"is_material": False, "event_type": "OTHER", "timeline_entry": "",
             "reason": "A new office address; no new information about the business"}
    pipeline, sink, _ = build(settings, [f], {f.pdf_url: _pdf("The registered office moves to Plot 12, Sector 5 from 12 November.")},
                              {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(reply)], "glm-4.5-flash": [json.dumps(reply)]})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "OTHER"}))
    assert outcome.update["status"] == "NOT_MATERIAL"
    assert outcome.update["reason"] == "pass2: not material: A new office address; no new information about the business"


def test_a_filing_read_again_as_not_material_takes_its_facts_out_of_memory(settings):
    """Kanoria's AGM presentation was analysed once and wrote a balance sheet ten times too large into memory; read
    again it was not material, and its facts stayed for good, grounding later cards (audit, 2026-10-18)."""
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-again", "Unaudited Financial Results for the quarter", now, "Result")
    not_material = {"is_material": False, "event_type": "RESULTS", "timeline_entry": "", "reason": "a duplicate copy"}
    pipeline, sink, _ = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                              {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)], "glm-4.5-flash": [json.dumps(PASS2)]})
    first = pipeline._process_one(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}), False, True)
    pipeline._commit([first])
    from bse_intel.dossier import _sources

    # the card's guidance stands for its facts (its statement figures no longer enter memory: MEMORY_FILE_ONLY, owner 30 Oct 2026)
    sources = lambda: {s["news_id"] for m in sink.get_dossier("999001")["financial_metrics"] for s in _sources(m)} | {  # noqa: E731
        g["source_news_id"] for g in sink.get_dossier("999001")["guidance"]}
    assert "n-again" in sources()
    pipeline, sink, _ = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},   # the same store, read again
                              {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(not_material)],
                               "glm-4.5-flash": [json.dumps(not_material)]})
    again = pipeline._process_one(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}), False, True)
    assert again.update["status"] == "NOT_MATERIAL" and "n-again" not in sources()


def test_every_attachment_may_be_as_large_as_an_annual_report():
    """519552's FY26 annual report (F57) and NHPC's FY26 results PDF were both skipped at a 30 MB cap; every
    filing now gets the same 120 MB (owner, 25 Oct 2026)."""
    from bse_intel.pipeline import ATTACHMENT_MAX_BYTES, _attachment_cap

    when = now_ist()
    report = _filing("n-ar", "34th Annual Report for FY 2025-26", when, "Company Update", "Reg. 34 (1) Annual Report")
    assert ATTACHMENT_MAX_BYTES == 120_000_000
    for kind in ("ANNUAL_REPORT", "RESULTS", "OTHER"):
        assert _attachment_cap(report.model_copy(update={"event_type": kind})) == ATTACHMENT_MAX_BYTES


def test_an_annual_report_inside_an_agm_notice_takes_the_annual_report_path(settings):
    """Max Financial (round 5): NSE's headline named only the meeting; the 389 pages behind it were the annual report,
    and pass 1 set them aside as a routine AGM notice."""
    now = now_ist() - timedelta(minutes=30)
    agm = _filing("n-agm", "Annual General Meeting of the Company to be held on Wednesday, August 19, 2026", now,
                  "AGM/EGM", "Shareholders meeting")
    doc = pymupdf.open()
    for i in range(64):
        page = doc.new_page()
        text = ("Sub: Notice of the 38th Annual General Meeting and Annual Report for the FY 2025-26" if i == 0 else
                f"Directors' Report and financial statements, page {i + 1}. Revenue from operations 12,000.00.")
        page.insert_textbox(pymupdf.Rect(36, 36, 560, 800), text, fontsize=9)
    card = {**PASS2, "event_type": "ANNUAL_REPORT", "card": {**PASS2["card"], "headline": "Demo Cement FY26 annual report"}}
    script = {"openai/gpt-oss-20b": [{"is_material": False, "event_type": "OTHER", "reason": "AGM notice"}],
              "nvidia/nemotron-3.5-super-vl:free": [json.dumps(card)] * 3}
    pipeline, sink, fake = build(settings, [agm], {agm.pdf_url: doc.tobytes()}, script)
    pipeline.run("live", time_budget_s=60)
    (row,) = rows(sink, "select status, event_type, reason from filings where news_id = 'n-agm'")
    assert not (row["reason"] or "").startswith("pass1"), row
    assert all(c["model"] != "openai/gpt-oss-20b" for c in fake.calls)


def test_packed_filings_stay_queued_when_every_writer_is_out_of_quota(settings):
    """With Nemotron 3 Super off the card routes (round 6), a pack that finds every Gemini model at its daily limit and
    no other writer free leaves its filings queued with no attempt spent; they are written after Gemini's reset."""
    from dataclasses import replace

    from bse_intel.ai.gateway import _day_function

    settings = replace(settings, pass2_pack=2, pass2_pack_wait_s=1)
    now = now_ist() - timedelta(minutes=30)
    filings = [_filing(f"q{i}", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result",
                       scrip=f"99900{i}") for i in range(2)]
    pacific = _day_function("America/Los_Angeles")()
    usage = [{"day": pacific, "provider": "gemini", "model": m, "requests": 500}
             for m in ("gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-3-flash-preview", "gemini-3.5-flash-lite")]
    # Gemma 4 on the same key is a free spare writer too (owner, 24 Oct 2026): at its own day's limit here
    usage += [{"day": pacific, "provider": "gemini", "model": m, "requests": 1000} for m in ("gemma-4-31b-it", "gemma-4-26b-a4b-it")]
    fake = FakeProvider({})
    gateway = AIGateway(settings.load_toml("providers.toml"), usage_today=usage, client_factory=lambda *a: fake,
                        env={"GEMINI_API_KEY": "g"})
    sink = LocalSink(settings)
    pipeline = Pipeline(settings, sink, gateway, bse=FakeBse(filings, {f.pdf_url: _pdf(RESULT_TEXT) for f in filings}),
                        sleep=lambda s: None)
    pipeline.run("live", time_budget_s=60)
    states = {r["news_id"]: (r["status"], r["attempts"]) for r in rows(sink, "select news_id, status, attempts from filings")}
    assert states == {"q0": ("PENDING", 0), "q1": ("PENDING", 0)} and fake.calls == []
    assert all("quota" in (r["last_error"] or "") for r in rows(sink, "select last_error from filings"))


def test_pass2_routing_keeps_live_and_backfill_apart_and_packs_long_filings(settings):
    """ai-quality plan item 1: live and backfill filings go to separate packs (the backfill one marked bulk, so the
    gateway keeps Flash's live reserve), long filings are packed with long ones only, and one too large for a pack, or
    any filing with packing off, goes to its route alone as before."""
    from dataclasses import replace

    from bse_intel.pipeline import LONG_PACK_MAX_CHARS, LONG_PROMPT_TOKENS

    env = {"GEMINI_API_KEY": "g", "ZAI_API_KEY": "z", "OPENROUTER_API_KEY": "o"}
    pipeline, _, _ = build(replace(settings, pass2_pack=6, pass2_pack_wait_s=1), [], {}, {}, env=env)
    short, long = 30_000, LONG_PROMPT_TOKENS * 4 + 1_000
    for bulk, fallback in ((False, "pass2"), (True, "pass2_bulk")):
        route, packer = pipeline._pass2_writer(bulk, short)
        assert route == fallback and packer.bulk is bulk and packer.size == 6 and packer.route == "pass2_packed"
        route, packer = pipeline._pass2_writer(bulk, long)
        assert route == "pass2_long" and packer.bulk is bulk and packer.size == 3
        assert packer is not pipeline._pass2_writer(bulk, short)[1] and packer.max_chars == LONG_PACK_MAX_CHARS
        assert pipeline._pass2_writer(bulk, LONG_PACK_MAX_CHARS + 1) == ("pass2_long", None)
    assert pipeline._pass2_writer(False, long)[1] is not pipeline._pass2_writer(True, long)[1]
    off, _, _ = build(settings, [], {}, {}, env=env)
    assert off._pass2_writer(False, short) == ("pass2", None) and off._pass2_writer(True, long) == ("pass2_long", None)
    # backfill packs wait longer than live ones (owner, 22 Oct): no reader waits for a backfill card
    waits, _, _ = build(replace(settings, pass2_pack=6, pass2_pack_wait_s=60, pass2_pack_wait_bulk_s=180), [], {}, {}, env=env)
    assert {bulk: waits._pass2_writer(bulk, n)[1].wait_s for bulk in (False, True) for n in (short, long)} == {False: 60, True: 180}


def test_backfill_on_the_configured_routes_leaves_flash_to_live_filings(settings):
    """With each Flash model at 3 of its 19 requests at 15:00 IST, a backfill request skips all five and the pack goes
    to Flash-Lite, then to pass2_bulk's GLM; a live request still starts with Flash. After 21:00 backfill may use them."""
    from datetime import datetime

    from bse_intel.ai.gateway import _day_function

    pacific = _day_function("America/Los_Angeles")()
    usage = [{"day": pacific, "provider": "gemini", "model": m, "requests": 3}
             for m in ("gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-3-flash-preview")]
    gateway = AIGateway(settings.load_toml("providers.toml"), usage_today=usage, client_factory=lambda *a: None,
                        env={"GEMINI_API_KEY": "g"})
    gateway.local_now = lambda: datetime(2026, 10, 21, 15, 0)
    packed = gateway.routes["pass2_packed"]
    assert [t.model for t in packed if not gateway.reserved_for_live(t)] == ["gemini-3.5-flash-lite"]
    assert all(gateway._skip(t, 1000, 2000) is None for t in packed)                  # live: every model as before
    assert all(gateway._skip(t, 1000, 2000, bulk=True) for t in packed[:-1])
    gateway.local_now = lambda: datetime(2026, 10, 21, 21, 30)
    assert not any(gateway.reserved_for_live(t) for t in packed)


def test_an_order_repeat_needs_a_card_in_the_feed_for_the_order(settings, monkeypatch):
    """A press release repeating an order is a duplicate only when the order's own filing has a card in the feed:
    published this run, or a card row that is not held (MCLOUD's ₹7.64 Cr LOA had no card of its own)."""
    from bse_intel.pipeline import Outcome

    pipeline, sink, _ = build(settings, [], {}, {})
    monkeypatch.setattr(pipeline, "_attempt", lambda f, *a, **k: Outcome({"news_id": f.news_id, "status": "ANALYZED"}, card={"held": 0}))
    pipeline._process_one(_filing("o-1", "Receipt of order", now_ist()), False, True)
    assert pipeline._card_shown("o-1"), "published this run, before its card is committed"
    assert not pipeline._card_shown("o-none"), "no card at all"
    monkeypatch.setattr(pipeline, "_attempt", lambda f, *a, **k: Outcome({"news_id": f.news_id, "status": "ANALYZED"}, card={"held": 1}))
    pipeline._process_one(_filing("o-2", "Receipt of order", now_ist()), False, True)
    assert not pipeline._card_shown("o-2"), "a held card is not in the feed"


def test_a_board_outcome_whose_letter_submits_the_results_is_the_results_filing():
    """Atul's outcome put its buyback first and its statement at character 34,452, the XBRL filed separately."""
    from bse_intel.pipeline import carries_results

    letter = ("Sub: Outcome of the Board meeting\n1. Financial results\nPursuant to Regulation 30 and 33(1) ..., we are "
              "submitting the following as Annexure A for the second quarter | six months ended on September 30, 2026:\n"
              "a) unaudited standalone and consolidated financial results.\n2. Buy-back of shares ... excluding transaction "
              "costs viz. brokerage, public announcement publication fees, filing fees ...")
    assert carries_results("CORPORATE_ACTION", letter + " x" * 20000)
    assert not carries_results("ORDER_WIN", letter)                         # only the types the rule corrects
    newspaper = "Please find enclosed copies of the newspaper advertisement of the unaudited financial results for Q2."
    assert not carries_results("OTHER", newspaper)
    notice = "We enclose the notice of the Board meeting to consider the unaudited financial results for the quarter."
    assert not carries_results("OTHER", notice)


def test_the_critic_reads_the_filing_on_a_card_with_warrants(settings):
    """The warrant-deadline loop reused the name `text`, so on a card with warrants the shadow critic was handed the
    deadline sentence instead of the filing and judged every point without its excerpt (survey, 24 Oct 2026)."""
    from dataclasses import replace

    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-warr", "Outcome of Board Meeting - allotment of warrants", now, "Company Update")
    filing_text = ("The Board allotted 10,00,000 convertible warrants on a preferential basis at Rs 120 each, "
                   "aggregating Rs 12 crore, with 25% received on allotment.")
    reply = {
        "is_material": True, "event_type": "FUNDRAISE",
        "card": {"impact_level": "MODERATE", "headline": "Demo Cement allots 10 lakh warrants at ₹120 for ₹12 Cr",
                 "what_happened": [{"text": "10 lakh warrants allotted at ₹120 each, ₹12 Cr",
                                    "quote": "aggregating Rs 12 crore, with 25% received on allotment."}],
                 "why_it_matters": [{"text": "Promoters add capital", "basis": "FILING"}]},
        "dossier_delta": {"capital_actions": [{"instrument": "Convertible warrants", "new_shares": 1000000,
                                               "issue_price": 120, "amount_cr": 12}]},
    }
    pipeline, sink, fake = build(replace(settings, critic=True), [f], {f.pdf_url: _pdf(filing_text)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(reply)] * 2},
                                 env={"OPENROUTER_API_KEY": "o"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "FUNDRAISE"}))
    assert any(c["event_type"] == "WARRANT_EXPIRY" for c in outcome.catalysts)
    job = outcome.critic
    assert job is not None and "convertible warrants" in job["opening"].lower()
    assert "18-month warrant conversion deadline" not in job["opening"]


@pytest.mark.switches_on("MEMORY_FILE_ONLY")
def test_memory_a_job_writes_while_the_card_is_being_written_is_kept(settings):
    """A live card reads its company's memory, spends minutes on the AI and writes the memory back whole: a pledge event
    (or deals, insider trades, a seed's figures) stored meanwhile by a memory job outside the nightly pause was lost."""
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-race", "Unaudited Financial Results for the quarter", now, "Result")
    holder = {}

    def reply_after_a_job_wrote(kwargs):
        sink = holder["sink"]
        stored = sink.get_dossier("999001")
        stored["pledges"] = {"events": [{"seq_id": "p1", "event": "PLEDGE", "pct": 4.0, "as_of": now.isoformat()}]}
        stored["financial_metrics"] = stored.get("financial_metrics", []) + [
            {"metric": "revenue", "period": "Q1FY27", "value": 110.0, "as_of": now.isoformat(), "source_news_id": "xbrl:seed"}]
        sink.put_dossier("999001", stored)
        return json.dumps(PASS2)

    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [reply_after_a_job_wrote]},
                                 env={"OPENROUTER_API_KEY": "o"})
    holder["sink"] = sink
    sink.put_dossier("999001", new_dossier(f))
    pipeline._commit([pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))])
    memory = sink.get_dossier("999001")
    assert memory["pledges"]["events"][0]["seq_id"] == "p1"                     # the job's part, kept
    periods = {m["period"] for m in memory["financial_metrics"]}
    assert periods == {"Q1FY27"}   # its figure kept; the card's own revenue stays off memory (MEMORY_FILE_ONLY, owner 30 Oct 2026)
    assert [g["source_news_id"] for g in memory["guidance"]] == ["n-race"]       # the card's other facts reach memory
    assert any(t.get("news_id") == "n-race" for t in memory["timeline"])        # and the card's own line


def test_a_filing_whose_own_write_keeps_failing_spends_an_attempt_in_the_end(settings, monkeypatch):
    """A timeout or 5xx is the site's (no attempt spent), but a filing whose own write fails run after run while the site
    answers others would spend its AI calls every 15 minutes for ever: after MAX_DEFERRALS runs it spends one."""
    from bse_intel.pipeline import MAX_DEFERRALS
    from bse_intel.sinks.base import SinkUnavailable

    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-slow", "Order win", now, "Company Update")
    pipeline, sink, fake = build(settings, [f], {}, {})

    def unavailable(*a, **k):
        raise SinkUnavailable("the platform API answered 500 through every retry")

    monkeypatch.setattr(pipeline, "analyze", unavailable)
    first = pipeline._attempt(f, bulk=False, memory_complete=True)
    assert first.update["status"] == "PENDING" and first.update["last_error"].startswith("deferred 1x: the platform")
    pipeline._unreachable = 0   # another filing was written meanwhile: the site is up
    worn = f.model_copy(update={"last_error": f"deferred {MAX_DEFERRALS}x: the platform did not answer (500)"})
    assert pipeline._attempt(worn, bulk=False, memory_complete=True).update["status"] == "FAILED"
    # the site down for everyone (the filing before also failed): no attempt spent however many times
    pipeline._unreachable = 1
    assert pipeline._attempt(worn, bulk=False, memory_complete=True).update["status"] == "PENDING"


def test_a_cards_memory_is_written_with_its_row_and_not_before(settings):
    """Owner, 25 Oct 2026 (architecture audit): memory went to the store before the card's row, so a run cut short, or
    a row the database refused, left memory with no card. Now it waits for the commit; meanwhile the company's later
    filings in the run read it from the pending store."""
    from bse_intel.sinks.base import SinkRejected

    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-mem", "Unaudited Financial Results for the quarter", now, "Result")
    pipeline, sink, _ = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                              {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)]}, env={"OPENROUTER_API_KEY": "o"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert outcome.card is not None and sink.get_dossier(f.scrip_code) is None          # nothing before the row
    pending = pipeline._memory(f.scrip_code)                                              # the next filing sees it
    assert any(g.get("source_news_id") == "n-mem" for g in pending["guidance"])   # (figures stay off memory: MEMORY_FILE_ONLY)

    def refuse(outcomes):
        raise SinkRejected("row too large")
    real, pipeline._commit_rows = pipeline._commit_rows, refuse
    pipeline._commit([outcome])                                                           # the database refuses it
    assert sink.get_dossier(f.scrip_code) is None and not pipeline._pending_memory        # so memory is not written
    pipeline._commit_rows = real

    again = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    pipeline._commit([again])
    memory = sink.get_dossier(f.scrip_code)
    assert any(g.get("source_news_id") == "n-mem" for g in memory["guidance"])


def test_card_writing_cap_defers_without_waiting_or_an_attempt(settings):
    """F149 (TODO 35): a filing that used its card-writing time is deferred at once: no 60 s waits, no attempt spent."""
    from dataclasses import replace

    settings = replace(settings, workers=1)
    now = now_ist() - timedelta(minutes=5)
    f = _filing("n-cap", "Unaudited Financial Results for the quarter", now, "Result")
    pdfs = {f.pdf_url: _pdf(RESULT_TEXT)}
    pipeline, sink, fake = build(settings, [f], pdfs, {"nvidia/nemotron-3.5-super-vl:free": [PASS2]})
    sleeps = []
    pipeline._sleep = sleeps.append
    gw = pipeline.gateway
    start = gw.start_cap

    def start_and_run_out(seconds=None):   # the clock: this filing's cap is already spent when its pass 2 begins
        start(seconds)
        if gw._cap.state and gw._cap.state["deadline"] is not None:
            gw._cap.state["deadline"] = time.monotonic() - 1

    gw.start_cap = start_and_run_out
    pipeline.discover(now.date())
    pipeline.process("2000-01-01", "2100-01-01", time.monotonic() + 30, bulk=False)
    (row,) = rows(sink, "select status, attempts, last_error from filings where news_id = 'n-cap'")
    assert row["status"] == "PENDING" and row["attempts"] == 0
    assert row["last_error"] == "deferred 1x: card-writing cap reached (360 s)"
    assert sleeps == [] and pipeline.stats.deferred == 1 and pipeline.stats.failed == 0
    assert fake.calls == []   # not one pass-2 model was called


def test_under_the_card_writing_cap_a_filing_is_written_as_before(settings):
    now = now_ist() - timedelta(minutes=5)
    f = _filing("n-ok", "Unaudited Financial Results for the quarter", now, "Result")
    pdfs = {f.pdf_url: _pdf(RESULT_TEXT)}
    pipeline, sink, fake = build(settings, [f], pdfs, {"nvidia/nemotron-3.5-super-vl:free": [PASS2]})
    pipeline.discover(now.date())
    pipeline.process("2000-01-01", "2100-01-01", time.monotonic() + 30, bulk=False)
    (row,) = rows(sink, "select status from filings where news_id = 'n-ok'")
    assert row["status"] == "ANALYZED"


def test_after_three_cap_deferrals_the_cap_is_lifted_and_the_filing_is_written(settings, caplog):
    """The cap only delays a card: the 4th run has no cap, reaches the slow model and the filing is ANALYZED."""
    import logging

    from bse_intel.pipeline import MAX_CAP_DEFERRALS

    now = now_ist() - timedelta(minutes=5)
    f = _filing("n-lift", "Unaudited Financial Results for the quarter", now, "Result")
    pdfs = {f.pdf_url: _pdf(RESULT_TEXT)}
    pipeline, sink, fake = build(settings, [f], pdfs, {"nvidia/nemotron-3.5-super-vl:free": [PASS2]})
    gw = pipeline.gateway
    real_start = gw.start_cap

    def spent(seconds=None):   # a cap that would already be spent if it were ever started
        real_start(seconds)
        if gw._cap.state and gw._cap.state["deadline"] is not None:
            gw._cap.state["deadline"] = time.monotonic() - 1

    gw.start_cap = spent
    pipeline.discover(now.date())
    worn = f.model_copy(update={"last_error": f"deferred {MAX_CAP_DEFERRALS}x: card-writing cap reached (360 s)"})
    # the third deferral's own run still stops at the cap (2 earlier deferrals)
    two = f.model_copy(update={"last_error": "deferred 2x: card-writing cap reached (360 s)"})
    first = pipeline._attempt(two, bulk=False, memory_complete=True)
    assert first.update["status"] == "PENDING" and first.update["last_error"].startswith("deferred 3x: card-writing cap")
    assert fake.calls == []
    with caplog.at_level(logging.INFO, logger="bse_intel.pipeline"):
        outcome = pipeline._attempt(worn, bulk=False, memory_complete=True)
    assert outcome.update["status"] != "FAILED" and outcome.update["status"] != "PENDING", outcome.update
    assert any(c["model"] == "nvidia/nemotron-3.5-super-vl:free" for c in fake.calls)
    assert sum("cap lifted for n-lift after 3 deferrals" in r.message for r in caplog.records) == 1


def test_a_deck_or_transcript_filed_under_a_results_heading_is_read_as_one():
    """Coal India's investor presentation (COALINDIA_29102026183725_Presentation.pdf) was filed as a financial result
    update and took a second results card for H1FY27; its results statement (…_Result.pdf) is the results filing."""
    from bse_intel.pipeline import is_deck_or_transcript

    def f(name, headline="Financial Result Updates"):
        return _filing("d", headline, now_ist()).model_copy(update={"pdf_url": f"https://nsearchives.invalid/{name}"})

    assert is_deck_or_transcript(f("COALINDIA_29102026183725_Presentation.pdf"))
    assert is_deck_or_transcript(f("GATEWAY_28102026140102_Investor_Presentations_Oct26.pdf"))
    assert is_deck_or_transcript(f("Infosys_28102026173824_SE_filing_Earnings_call_transcript.pdf", "Analysts Meet"))
    assert not is_deck_or_transcript(f("COALINDIA_29102026181236_Result.pdf"))
    assert not is_deck_or_transcript(f("ABC_Results_and_Presentation.pdf", "Financial Results"))
    assert not is_deck_or_transcript(f("XYZ_outcome.pdf", "Outcome of board meeting and investor presentation"))
    assert not is_deck_or_transcript(f("ROUTE_28102026000940_Upload_.pdf"))
    # the headline alone never makes a deck (blind review): a results filing over a generic file name stays results
    assert not is_deck_or_transcript(f("ABC_28102026_Upload.pdf", "Outcome of Board Meeting - Results and Investor Presentation"))
    assert not is_deck_or_transcript(f("XYZ_FinancialResultsandPresentation.pdf"))


def test_d20_finds_a_cards_quarter_from_its_timeline_when_memory_holds_none_of_its_figures(settings, monkeypatch):
    """TODO 133: with MEMORY_FILE_ONLY a card read from the PDF leaves no figures in memory, so D20 finds the quarter's card
    through the quarter its own timeline entry names."""
    from dataclasses import replace

    monkeypatch.setenv("MEMORY_FILE_ONLY", "1")
    settings = replace(settings, one_card_per_results_quarter=True, workers=1)
    now = now_ist() - timedelta(hours=3)
    first = _filing("q-1", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    again = _filing("q-2", "Outcome of Board Meeting - results", now + timedelta(hours=1), "Board Meeting")
    pipeline, sink, fake = build(settings, [first, again], {f.pdf_url: _pdf(RESULT_TEXT) for f in (first, again)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)]})
    pipeline._commit([pipeline.analyze(first.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))])
    d = sink.get_dossier(first.scrip_code)
    assert not [m for m in d["financial_metrics"] if m["period"] == "Q2FY27" and m["metric"] == "revenue"], "no AI figure kept"
    assert any(t.get("news_id") == "q-1" and t.get("quarter") == "Q2FY27" for t in d["timeline"])
    pipeline._results_quarters.clear()   # a later run: only memory knows the quarter has its card
    two = pipeline.analyze(again.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert two.update["status"] == "DUPLICATE" and "q-1" in two.update["reason"]
