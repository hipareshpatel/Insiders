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

    def announcements(self, day, day_to=None):
        for f in self.filings:
            if f.filing_date == day.isoformat():
                yield f.model_copy()

    def download(self, url):
        return self.pdfs.get(url)


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
        "llama-3.1-8b-instant": [{"is_material": False, "event_type": "OTHER", "reason": "routine clarification"}],
        "deepseek-ai/deepseek-r1": ["<think>checking memory</think>" + json.dumps(PASS2)],
    }
    pipeline, sink, fake = build(settings, filings, pdfs, script)
    stats = pipeline.run("live", time_budget_s=60)

    status = {r["news_id"]: r["status"] for r in rows(sink, "select news_id, status from filings")}
    assert status == {"n-noise": "DROPPED_RULE", "n-res": "ANALYZED", "n-amb": "NOT_MATERIAL"}
    assert stats.analyzed == 1 and stats.pass1_rejected == 1 and stats.dropped_rule == 1

    (card,) = rows(sink, "select * from cards")
    body = json.loads(card["card_json"])
    assert card["impact_level"] == "HIGH" and card["event_category"] == "RESULTS" and card["needs_review"] == 0
    assert body["category_tag"] == "RESULTS" and body["model"] == "nvidia/deepseek-ai/deepseek-r1"
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
    (company,) = rows(sink, "select card_count, sector from companies")
    assert company["card_count"] == 1

    (run,) = rows(sink, "select status, stats_json from pipeline_runs")
    assert run["status"] == "OK" and json.loads(run["stats_json"])["analyzed"] == 1
    usage = {(r["provider"], r["model"]): r["requests"] for r in rows(sink, "select * from provider_usage")}
    assert usage == {("groq", "llama-3.1-8b-instant"): 1, ("nvidia", "deepseek-ai/deepseek-r1"): 1}

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
    # Only NVIDIA is configured for Pass 2, and both of its models report their daily quota spent.
    err = api_error(openai.RateLimitError, 429, "You exceeded your current quota for the day")
    script = {"deepseek-ai/deepseek-r1": [err], "meta/llama-3.3-70b-instruct": [err]}
    pipeline, sink, fake = build(settings, filings, pdfs, script, env={"NVIDIA_API_KEY": "n"})
    pipeline.discover(now.date())
    pipeline.process("2000-01-01", "2100-01-01", time.monotonic() + 30, bulk=False)
    status = {r["news_id"]: (r["status"], r["attempts"]) for r in rows(sink, "select news_id, status, attempts from filings")}
    assert all(s == ("PENDING", 0) for s in status.values()), status  # nothing failed, nothing dropped
    assert pipeline.stats.deferred >= 1 and "quota" in pipeline.stats.stopped_reason
    assert pipeline.stats.failed == 0
    # one try per model, then the ceiling stops the run instead of hammering the provider
    assert sorted(c["model"] for c in fake.calls) == ["deepseek-ai/deepseek-r1", "meta/llama-3.3-70b-instruct"]


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

    pipeline, sink, fake = build(settings, filings, pdfs, {"mistral-large-latest": [respond]},
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
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                           {"deepseek-ai/deepseek-r1": [json.dumps(bad)]}, env={"NVIDIA_API_KEY": "n"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    body = outcome.card["card"]
    (q,) = body["quantified_impact"]
    assert q["check"] == "MISMATCH" and q["computed"] == 135.0
    assert outcome.card["needs_review"] == 1
    assert body["fundamentals"]["revenue"] == {"period": "Q2FY27", "value": 120.0}
    assert body["pdf_pages"] == 1
