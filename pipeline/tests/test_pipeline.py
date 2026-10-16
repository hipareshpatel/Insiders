"""End to end: discovery -> rules -> Pass 1 -> PDF -> Pass 2 -> memory -> cards -> alerts,
against the LocalSink (real SQLite running the same SQL files as D1)."""

from __future__ import annotations

import json
import time
from datetime import timedelta

import pymupdf
from conftest import FakeProvider, api_error, openai

from bse_intel.ai.gateway import AIGateway
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


def build(settings, filings, pdfs, script, env=None):
    sink = LocalSink(settings)
    fake = FakeProvider(script)
    config = settings.load_toml("providers.toml")
    gateway = AIGateway(config, client_factory=lambda *a: fake,
                        env=env if env is not None else {"GROQ_API_KEY": "g", "NVIDIA_API_KEY": "n", "MISTRAL_API_KEY": "m"})
    pipeline = Pipeline(settings, sink, gateway, bse=FakeBse(filings, pdfs), sleep=lambda s: None)
    return pipeline, sink, fake


def rows(sink, sql, *params):
    return [dict(r) for r in sink._db.execute(sql, params).fetchall()]


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
        "nvidia/nemotron-3-super-120b-a12b": ["<think>checking memory</think>" + json.dumps(PASS2)],
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
    assert body["category_tag"] == "RESULTS" and body["model"] == "nvidia/nvidia/nemotron-3-super-120b-a12b"
    assert body["why_it_matters"][0]["memory_refs"] == []  # hallucinated memory id removed
    assert body["grounding"]["score"] >= 0.7
    assert body["notable_changes"][0]["direction"] == "POSITIVE"

    dossier = sink.get_dossier("999001")
    assert {m["period"] for m in dossier["financial_metrics"]} == {"Q2FY27", "Q2FY26"}
    assert all(m["source_news_id"] == "n-res" for m in dossier["financial_metrics"])
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
    assert usage == {("groq", "openai/gpt-oss-20b"): 1, ("nvidia", "nvidia/nemotron-3-super-120b-a12b"): 1}

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
    # Only NVIDIA is configured for Pass 2, and its model reports its daily quota spent.
    err = api_error(openai.RateLimitError, 429, "You exceeded your current quota for the day")
    script = {"nvidia/nemotron-3-super-120b-a12b": [err]}
    pipeline, sink, fake = build(settings, filings, pdfs, script, env={"NVIDIA_API_KEY": "n"})
    pipeline.discover(now.date())
    pipeline.process("2000-01-01", "2100-01-01", time.monotonic() + 30, bulk=False)
    status = {r["news_id"]: (r["status"], r["attempts"]) for r in rows(sink, "select news_id, status, attempts from filings")}
    assert all(s == ("PENDING", 0) for s in status.values()), status  # nothing failed, nothing dropped
    assert pipeline.stats.deferred >= 1 and "quota" in pipeline.stats.stopped_reason
    assert pipeline.stats.failed == 0
    # one try, then the ceiling stops the run instead of hammering the provider
    assert [c["model"] for c in fake.calls] == ["nvidia/nemotron-3-super-120b-a12b"]


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

    pipeline, sink, fake = build(settings, filings, pdfs, {"ministral-14b-2512": [respond]},
                                           env={"MISTRAL_API_KEY": "m"})
    pipeline.run("backfill", time_budget_s=60, max_backfill_days=10)
    assert seen_order == sorted(seen_order) and len(seen_order) == 3
    assert sink.kv_get("backfill:discovered_through") == (today - timedelta(days=1)).isoformat()
    assert sink.kv_get("backfill:complete") == "1"
    timeline = sink.get_dossier("999001")["timeline"]
    assert [t["news_id"] for t in timeline] == ["h0", "h1", "h2"]


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
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(bad)]},
                                 env={"NVIDIA_API_KEY": "n"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    body = outcome.card["card"]
    (q,) = body["quantified_impact"]
    assert q["check"] == "MISMATCH" and q["computed"] == 135.0
    assert outcome.card["needs_review"] == 1  # still published, marked unverified
    assert body["review"]["status"] == "UNRESOLVED" and "formula gives 135" in body["review"]["issues"][0]
    assert body["fundamentals"]["revenue"] == {"period": "Q2FY27", "value": 120.0}
    assert body["pdf_pages"] == 1


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

    pipeline, sink, _ = build(settings, filings, pdfs, {"ministral-14b-2512": [respond]}, env={"MISTRAL_API_KEY": "m"})
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
                              {"ministral-14b-2512": [respond], "nvidia/nemotron-3-super-120b-a12b": [respond]},
                              env={"MISTRAL_API_KEY": "m", "NVIDIA_API_KEY": "n"})
    pipeline.discover(old.date())  # as an earlier backfill run would have
    sink.kv_set("backfill:discovered_through", (today - timedelta(days=1)).isoformat(), "now")
    pipeline.run("live", time_budget_s=60)
    assert seen == [old.date().isoformat(), today.isoformat()]  # history first, then the live filing
    cards = {r["news_id"]: r for r in rows(sink, "SELECT news_id, memory_complete FROM cards")}
    assert cards["new"]["memory_complete"] == 1


def test_second_opinion_from_another_provider_corrects_the_card(settings):
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-q2", "Unaudited Financial Results for the quarter", now, "Result")
    bad = json.loads(json.dumps(PASS2))
    bad["card"]["what_happened"] = ["Revenue ₹120 Cr vs ₹90.9 Cr a year ago", "PAT ₹17.5 Cr"]  # PAT was ₹15 Cr
    bad["card"]["why_it_matters"] = [{"text": "Record quarterly revenue for the company", "basis": "FILING"}]
    good = json.loads(json.dumps(PASS2))
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(bad)], "ministral-14b-2512": [json.dumps(good)]},
                                 env={"NVIDIA_API_KEY": "n", "MISTRAL_API_KEY": "m"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    first, second = fake.calls
    assert first["model"] == "nvidia/nemotron-3-super-120b-a12b" and second["model"] == "ministral-14b-2512"
    verify_prompt = second["messages"][1]["content"]
    assert "DRAFT REPLY" in verify_prompt and "17.5" in verify_prompt and 'Claim not supported by the sources: "Record quarterly revenue' in verify_prompt
    body = outcome.card["card"]
    assert outcome.card["needs_review"] == 0 and body["what_happened"][1] == "PAT ₹15 Cr"
    assert body["review"]["status"] == "CORRECTED" and body["review"]["checked_by"] == "mistral/ministral-14b-2512"
    assert body["model"] == "mistral/ministral-14b-2512" and len(body["review"]["fixed"]) == 2


def test_one_unmatched_amount_gets_a_second_opinion_even_above_the_review_threshold(settings):
    """Ahluwalia's card had EBITDA ₹756 Cr for ₹75.6 Cr (a lakh table): 76% of its numbers matched,
    above the review threshold, so it went out unchecked. Any unmatched amount now asks a second provider."""
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-q3", "Unaudited Financial Results for the quarter", now, "Result")
    bad = json.loads(json.dumps(PASS2))
    bad["card"]["what_happened"] = ["Revenue ₹120 Cr vs ₹90.9 Cr a year ago", "PAT ₹16.5 Cr"]  # PAT was ₹15 Cr
    good = json.loads(json.dumps(PASS2))
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(bad)], "ministral-14b-2512": [json.dumps(good)]},
                                 env={"NVIDIA_API_KEY": "n", "MISTRAL_API_KEY": "m"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert len(fake.calls) == 2
    assert "₹ lakh ÷ 100 = ₹ Cr" in fake.calls[1]["messages"][1]["content"]
    body = outcome.card["card"]
    assert body["review"]["status"] == "CORRECTED" and body["what_happened"][1] == "PAT ₹15 Cr"


def test_a_lakh_figure_read_at_the_wrong_scale_is_corrected_without_a_second_model(settings):
    """"PAT ₹150 Cr" from "Net profit 1,500.00" under "(Rs. in lakhs)": only ₹15 Cr fits, so code
    corrects the card and memory, and no second provider is asked."""
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-q4", "Unaudited Financial Results for the quarter", now, "Result")
    bad = json.loads(json.dumps(PASS2))
    bad["card"]["what_happened"] = ["Revenue ₹120 Cr vs ₹90.9 Cr a year ago", "PAT ₹150 Cr"]
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(bad)]}, env={"NVIDIA_API_KEY": "n"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    body = outcome.card["card"]
    assert len(fake.calls) == 1 and body["review"] is None
    assert body["what_happened"][1] == "PAT ₹15 Cr" and body["grounding"]["unit_fixes"] == {"150": "15"}


def test_one_card_per_company_per_results_quarter(settings):
    """Decision D20: Novartis filed one quarter's results as three documents and got three cards. The
    first gets the card; a later document of the same quarter is linked to it, with no AI call."""
    from dataclasses import replace

    settings = replace(settings, one_card_per_results_quarter=True, workers=1)
    now = now_ist() - timedelta(hours=3)
    first = _filing("q-1", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    again = _filing("q-2", "Outcome of Board Meeting - results", now + timedelta(hours=1), "Board Meeting")
    pipeline, sink, fake = build(settings, [first, again], {f.pdf_url: _pdf(RESULT_TEXT) for f in (first, again)},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]})
    one = pipeline.analyze(first.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    pipeline._results_quarters.clear()  # a later run: only memory knows the quarter has its card
    two = pipeline.analyze(again.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert one.card is not None and len(fake.calls) == 1
    assert two.update["status"] == "DUPLICATE" and two.update["reason"] == "duplicate of q-1 (same results quarter Q2FY27, D20)"
