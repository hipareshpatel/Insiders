from __future__ import annotations

import json
import time
from types import SimpleNamespace

from bse_intel import call_seed
from bse_intel.models import Filing


def _f(news_id, headline, filed_at):
    return Filing(news_id=news_id, scrip_code="500001", company_name="Demo Ltd", headline=headline, subject=headline,
                  filed_at=filed_at, filing_date=filed_at[:10])


def test_one_document_a_quarter_a_transcript_first():
    docs = call_seed.pick([
        _f("p2", "Investor Presentation", "2026-10-15T10:00:00+05:30"),
        _f("t2", "Transcript of the earnings call", "2026-10-18T10:00:00+05:30"),
        _f("p1", "Investor Presentation", "2026-08-05T10:00:00+05:30"),
        _f("p0", "Investor Presentation", "2026-05-10T10:00:00+05:30"),
    ])
    assert [d.news_id for d in docs] == ["t2", "p1"]   # this quarter's transcript, last quarter's presentation


def test_the_seed_never_uses_gemini():
    """Owner, 2026-10-20: the seed runs on the free non-Gemini models; the card routes point at memory_seed."""
    t = lambda provider: SimpleNamespace(provider=provider)
    gateway = SimpleNamespace(routes={"memory_seed": [t("zai"), t("openrouter")], "pass2": [t("gemini")],
                                      "pass2_bulk": [t("gemini")], "pass2_long": [t("gemini"), t("deepseek")],
                                      "pass1": [t("mistral"), t("gemini")], "pass1_bulk": [t("gemini")]})
    gateway.set_route = lambda route, targets: gateway.routes.__setitem__(route, list(targets))
    call_seed.use_seed_route(gateway)
    assert all(x.provider != "gemini" for r in gateway.routes.values() for x in r)
    assert [x.provider for x in gateway.routes["pass2_long"]] == ["zai", "openrouter"]


def test_the_seed_writes_memory_not_cards_and_resumes():
    kv, analysed = {}, []
    dossiers = {"500001": {"timeline": [{"news_id": "old"}]}, "500002": {}}
    sink = SimpleNamespace(kv_get=kv.get, kv_set=lambda k, v, at: kv.__setitem__(k, v),
                           get_dossier=lambda s: dossiers.get(s),
                           query=lambda name, args: [{"scrip_code": "500001", "market_cap_cr": 9e4},
                                                     {"scrip_code": "500002", "market_cap_cr": 1e5}] if args[0] == "" else [])
    calls = {"500001": [_f("old", "Transcript of the call", "2026-10-10T10:00:00+05:30")],
             "500002": [_f("new", "Investor Presentation", "2026-10-12T10:00:00+05:30")]}
    pipeline = SimpleNamespace(
        sink=sink, gateway=SimpleNamespace(routes={"memory_seed": []}, set_route=lambda route, targets: None),
        rules=SimpleNamespace(classify=lambda f: SimpleNamespace(event_type="CONCALL_PRESENTATION")),
        _company_announcements=lambda scrip, a, b: calls[scrip],
        analyze=lambda f, bulk, memory_complete: analysed.append((f.news_id, f.route)) or SimpleNamespace(update={"status": "DONE"}))
    import bse_intel.universe as universe
    real = universe.load_nse
    universe.load_nse = lambda s: SimpleNamespace(included={"500001", "500002"})
    try:
        report = call_seed.run(pipeline, time.monotonic() + 30)
        again = call_seed.run(pipeline, time.monotonic() + 30)
    finally:
        universe.load_nse = real
    assert analysed == [("new", "FAST_TRACK")], "the larger company first; a call already in memory is skipped"
    assert report["seeded"] == 1 and report["skipped"] == 1 and report["done"]
    assert json.loads(kv[call_seed.STATE_KEY])["done"] and again == {"done": True, "companies": 0, "seeded": 0}


def test_the_seed_calls_command_builds_its_pipeline(monkeypatch):
    """20 Oct 2026: both of seed-calls' first runs died at once on a NameError (`build_pipeline` not imported in cli)."""
    from bse_intel import cli, pipeline as pipeline_module

    built, ran = [], []
    monkeypatch.setattr(pipeline_module, "build_pipeline", lambda settings, sink: built.append(sink) or "pipeline")
    monkeypatch.setattr(call_seed, "run", lambda p, deadline, restart, scrips, workers: ran.append((p, restart, scrips)) or {})
    args = SimpleNamespace(scrips="500001, 500002", restart=False, time_budget=60)
    assert cli.cmd_seed_calls(args, SimpleNamespace(workers=1), "sink") == 0
    assert built == ["sink"] and ran == [("pipeline", False, {"500001", "500002"})]


def test_the_seed_route_replaces_the_rotation_too():
    """seed-calls run 3 (2026-10-20): the card routes' lists were replaced but their weighted rotations kept, so
    pass2_long still tried Gemini and DeepSeek first and 22 documents failed with no free model tried."""
    from bse_intel.ai.gateway import AIGateway
    from bse_intel.settings import Settings
    from conftest import FakeProvider

    env = {"DEEPSEEK_API_KEY": "k", "ZAI_API_KEY": "k", "OPENROUTER_API_KEY": "k", "GEMINI_API_KEY": "k"}
    gateway = AIGateway(Settings().load_toml("providers.toml"), client_factory=lambda *a: FakeProvider({}), env=env)
    call_seed.use_seed_route(gateway, deepseek_ok=False)
    for _ in range(6):
        tried = [t.provider for t in gateway._ordered("pass2_long")]
        assert "gemini" not in tried and "deepseek" not in tried and tried[0] == "zai", tried


def test_a_run_hands_on_to_the_next_while_companies_are_left(tmp_path):
    """GitHub dropped two of the first four scheduled seed-calls runs (20 Oct 2026): a run that stopped at its budget
    starts the next one, at night only, and never after a run that read no company."""
    left = {"companies": 49, "seeded": 69, "failed": 19, "stopped": True}
    assert call_seed.next_run(left, 18)
    assert not call_seed.next_run(left, 23) and not call_seed.next_run(left, 9)   # the night is over
    assert not call_seed.next_run({**left, "done": True}, 18)
    assert not call_seed.next_run({**left, "stopped": False}, 18)
    assert not call_seed.next_run({**left, "companies": 0}, 18)                    # read nothing: no loop
    out = tmp_path / "report.txt"
    out.write_text("log line\n" + json.dumps(left) + "\n")
    assert call_seed.next_run_from_output(str(out), 18)
    out.write_text("Traceback ...\n")
    assert not call_seed.next_run_from_output(str(out), 18)
