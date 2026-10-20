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
        sink=sink, gateway=SimpleNamespace(routes={"memory_seed": []}),
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
