"""Run-level behaviour found in the pre-launch audit: failures stay contained, nothing burns its
attempts twice, live work is never starved, and nothing is analysed without its text."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import timedelta

import pytest
from test_pipeline import PASS2, RESULT_TEXT, _filing, _pdf, build, rows

from bse_intel import pipeline as pipeline_module
from bse_intel.bse import AttachmentError
from bse_intel.timeutil import now_ist


def _results(n, when, scrip_base=999100):
    return [_filing(f"r{i}", "Unaudited Financial Results", when + timedelta(seconds=i), "Result",
                    scrip=str(scrip_base + i), name=f"Demo {i} Ltd") for i in range(n)]


def test_refused_attachment_fails_one_filing_and_three_in_a_row_stop_the_run(settings):
    settings = replace(settings, workers=1)
    now = now_ist() - timedelta(minutes=30)
    filings = _results(5, now)
    pipeline, sink, _ = build(settings, filings, {f.pdf_url: _pdf(RESULT_TEXT) for f in filings},
                              {"deepseek-ai/deepseek-r1": [json.dumps(PASS2)]}, env={"NVIDIA_API_KEY": "n"})
    real = pipeline.bse.download

    def download(url):
        if url.endswith(("r1.pdf", "r2.pdf", "r3.pdf")):
            raise AttachmentError("BSE refused the attachment", refused=True)
        return real(url)

    pipeline.bse.download = download
    stats = pipeline.run("live", time_budget_s=60)
    status = {r["news_id"]: (r["status"], r["attempts"]) for r in rows(sink, "select news_id, status, attempts from filings")}
    assert status["r0"] == ("ANALYZED", 0)          # committed before the block, not thrown away
    assert status["r1"] == ("FAILED", 1) and status["r3"] == ("FAILED", 1)
    assert status["r4"] == ("PENDING", 0)           # left for the next run once BSE is refusing us
    assert stats.status == "ERROR" and stats.stopped_reason == "BSE blocked the request"


def test_a_failing_history_filing_is_tried_once_per_run(settings):
    today = now_ist().date()
    settings = replace(settings, backfill_start=(today - timedelta(days=30)).isoformat(), workers=1)
    old = now_ist().replace(hour=17) - timedelta(days=20)
    history = _filing("old", "Unaudited Financial Results", old, "Result")
    live = _filing("new", "Unaudited Financial Results", now_ist() - timedelta(minutes=5), "Result")
    pipeline, sink, _ = build(settings, [history, live], {live.pdf_url: _pdf(RESULT_TEXT)},
                              {"deepseek-ai/deepseek-r1": [json.dumps(PASS2)], "mistral-large-latest": [json.dumps(PASS2)]},
                              env={"MISTRAL_API_KEY": "m", "NVIDIA_API_KEY": "n"})
    pipeline.discover(old.date())
    pipeline.bse.download = lambda url: (_ for _ in ()).throw(AttachmentError("timed out")) if "old" in url else _pdf(RESULT_TEXT)
    pipeline.run("all", time_budget_s=60, max_backfill_days=40)
    (row,) = rows(sink, "select status, attempts from filings where news_id = 'old'")
    assert row == {"status": "FAILED", "attempts": 1}  # not three attempts in one run
    (card,) = rows(sink, "select memory_complete from cards where news_id = 'new'")
    assert card["memory_complete"] == 0                # its history did not make it in


def test_retryable_failures_at_the_head_of_the_queue_do_not_stop_the_rest(settings, monkeypatch):
    monkeypatch.setattr(pipeline_module, "BATCH", 2)
    settings = replace(settings, workers=1)
    now = now_ist() - timedelta(minutes=30)
    filings = _results(5, now)
    pipeline, sink, _ = build(settings, filings, {f.pdf_url: _pdf(RESULT_TEXT) for f in filings[2:]},
                              {"deepseek-ai/deepseek-r1": [json.dumps(PASS2)], "meta/llama-3.3-70b-instruct": [json.dumps(PASS2)]},
                              env={"NVIDIA_API_KEY": "n"})
    pipeline.discover(now.date())
    sink._db.execute("UPDATE filings SET status = 'FAILED', attempts = 1 WHERE news_id IN ('r0', 'r1')")
    sink._db.commit()
    pipeline._tried.update({"r0", "r1"})  # as if already tried earlier in this run
    pipeline.process(now.date().isoformat(), now.date().isoformat(), time.monotonic() + 30, bulk=False)
    analysed = {r["news_id"] for r in rows(sink, "select news_id from filings where status = 'ANALYZED'")}
    assert analysed == {"r2", "r3", "r4"}


def test_live_filing_of_a_company_with_a_long_backlog_is_not_held_back(settings, monkeypatch):
    monkeypatch.setattr(pipeline_module, "HISTORY_INLINE", 2)
    today = now_ist().date()
    settings = replace(settings, backfill_start=(today - timedelta(days=30)).isoformat(), workers=1)
    old = [_filing(f"old{i}", "Unaudited Financial Results", now_ist().replace(hour=17) - timedelta(days=20 - i), "Result")
           for i in range(3)]
    live = _filing("new", "Unaudited Financial Results", now_ist() - timedelta(minutes=5), "Result")
    seen = []

    def respond(kwargs):
        seen.append(kwargs["messages"][1]["content"].split("Filed: ")[1][:10])
        return json.dumps(PASS2)

    pipeline, sink, _ = build(settings, old + [live], {f.pdf_url: _pdf(RESULT_TEXT) for f in old + [live]},
                              {"deepseek-ai/deepseek-r1": [respond]}, env={"NVIDIA_API_KEY": "n"})
    for f in old:
        pipeline.discover(now_ist().date().fromisoformat(f.filing_date))
    pipeline.run("live", time_budget_s=60)
    assert seen == [today.isoformat()]  # the live filing first; the backlog goes to the backfill
    (card,) = rows(sink, "select memory_complete from cards")
    assert card["memory_complete"] == 0
    assert pipeline._priority == ["999001"]


def test_second_opinion_reply_with_only_a_card_keeps_the_memory(settings):
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-q3", "Unaudited Financial Results for the quarter", now, "Result")
    bad = json.loads(json.dumps(PASS2))
    bad["card"]["why_it_matters"] = [{"text": "Record quarterly revenue for the company", "basis": "FILING"}]
    card_only = {"is_material": True, "card": PASS2["card"]}
    pipeline, sink, _ = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                              {"deepseek-ai/deepseek-r1": [json.dumps(bad)], "mistral-large-latest": [json.dumps(card_only)]},
                              env={"NVIDIA_API_KEY": "n", "MISTRAL_API_KEY": "m"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert outcome.card["card"]["review"]["status"] == "CORRECTED"
    assert {m["period"] for m in sink.get_dossier("999001")["financial_metrics"]} == {"Q2FY27", "Q2FY26"}
    assert outcome.card["event_category"] == "RESULTS"


def test_empty_weekday_is_checked_again_before_the_backfill_moves_on(settings):
    today = now_ist().date()
    start = today - timedelta(days=14)
    while start.weekday() >= 5:
        start -= timedelta(days=1)
    settings = replace(settings, backfill_start=start.isoformat())
    pipeline, sink, _ = build(settings, [], {}, {}, env={})
    pipeline.run("backfill", time_budget_s=30, max_backfill_days=3)
    assert sink.kv_get("backfill:discovered_through") in (None, (start - timedelta(days=1)).isoformat())
    pipeline2, sink2, _ = build(settings, [], {}, {}, env={})
    pipeline2.run("backfill", time_budget_s=30, max_backfill_days=1)
    assert sink2.kv_get("backfill:discovered_through") == start.isoformat()  # accepted on the second look


def test_a_discovery_error_does_not_stop_processing(settings):
    now = now_ist() - timedelta(minutes=30)
    filings = _results(1, now)
    pipeline, sink, _ = build(settings, filings, {f.pdf_url: _pdf(RESULT_TEXT) for f in filings},
                              {"deepseek-ai/deepseek-r1": [json.dumps(PASS2)]}, env={"NVIDIA_API_KEY": "n"})
    pipeline.discover(now.date())
    pipeline.bse.announcements = lambda *a, **k: (_ for _ in ()).throw(ValueError("HTML error page"))
    stats = pipeline.run("live", time_budget_s=60)
    assert stats.analyzed == 1 and stats.discovery_errors >= 1 and stats.status == "PARTIAL"


def test_known_filings_are_not_re_recorded_and_paging_gets_the_known_set(settings):
    now = now_ist() - timedelta(minutes=30)
    filings = [_filing("n-noise", "Closure of Trading Window", now, "Company Update", "Trading Window")] + _results(1, now)
    pipeline, sink, _ = build(settings, filings, {}, {}, env={})
    calls = []
    real = pipeline.bse.announcements
    pipeline.bse.announcements = lambda day, known=None: (calls.append(known), real(day))[1]
    assert pipeline.discover(now.date(), full=False) == 2
    assert pipeline.discover(now.date(), full=False) == 0
    assert calls[1] == {"n-noise", "r0"}
    assert sink.kv_get(f"noise_count:{now.date().isoformat()}") == "1"


@pytest.mark.parametrize("scanned_text", [""])
def test_scanned_document_with_failed_ocr_is_retried_not_judged_on_its_headline(settings, scanned_text):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), 0)
    page.insert_image(page.rect, pixmap=pix)
    pdf = doc.tobytes()
    now = now_ist() - timedelta(minutes=30)
    (f,) = _results(1, now)
    pipeline, sink, _ = build(settings, [f], {f.pdf_url: pdf}, {"pixtral-12b-latest": [RuntimeError("vision down")]},
                              env={"MISTRAL_API_KEY": "m"})
    pipeline.gateway.transcribe_image = lambda png, route="vision": (_ for _ in ()).throw(RuntimeError("vision down"))
    outcome = pipeline._process_one(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}), False, True)
    assert outcome.update["status"] == "FAILED" and "OCR failed" in outcome.update["last_error"]


def test_extracted_text_is_cached_so_reanalysis_never_downloads_again(settings):
    now = now_ist() - timedelta(minutes=30)
    (f,) = _results(1, now)
    pipeline, sink, _ = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                              {"deepseek-ai/deepseek-r1": [json.dumps(PASS2)], "meta/llama-3.3-70b-instruct": [json.dumps(PASS2)]},
                              env={"NVIDIA_API_KEY": "n"})
    filing = f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"})
    pipeline.analyze(filing)
    pipeline.bse.download = lambda url: (_ for _ in ()).throw(AssertionError("downloaded again"))
    outcome = pipeline.analyze(filing)
    assert outcome.update["status"] == "ANALYZED" and list(settings.text_cache_dir.rglob("*.json.gz"))


def test_filings_of_companies_outside_the_universe_go_to_the_noise_file(settings):
    from bse_intel import universe

    settings = replace(settings, universe_min_mcap_cr=100)
    now = now_ist() - timedelta(minutes=30)
    filings = _results(3, now)  # scrips 999100, 999101, 999102
    pipeline, sink, _ = build(settings, filings, {}, {}, env={})
    sink._db.executemany("INSERT INTO companies (scrip_code, company_name, market_cap_cr, watchlist) VALUES (?, ?, ?, ?)",
                         [("999100", "Big", 900.0, 0), ("999101", "Shell", 40.0, 0), ("999102", "Starred", 40.0, 1)])
    sink._db.commit()
    assert universe.build(settings, sink) == 1
    pipeline.discover(now.date())
    queued = {r["news_id"] for r in rows(sink, "select news_id from filings")}
    assert queued == {"r0", "r2"}
    noise = json.loads(sink.get_object(f"noise/{now.date().isoformat()}/000.json"))["rows"]
    assert noise[0][0] == "r1" and "outside universe" in noise[0][7]
