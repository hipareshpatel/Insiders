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


LETTER = RESULT_TEXT + (" The Board of Directors at its meeting held today considered and approved the statement of"
                        " unaudited financial results for the quarter, together with the limited review report of the"
                        " statutory auditors, and took note of the compliance certificate placed before it. The meeting"
                        " commenced at 11:00 a.m. and concluded at 1:15 p.m. Kindly take the same on record.")


@pytest.mark.parametrize("workers", [1, 3])
def test_repeat_submissions_of_one_event_are_marked_duplicate(settings, workers):
    """SML Mahindra filed one CEO change five times in eight minutes, once per BSE subcategory. Only the
    first is analysed; a revised filing and another company's identical text are not duplicates."""
    settings = replace(settings, workers=workers)
    now = now_ist() - timedelta(minutes=30)
    filings = [_filing("d1", "Outcome of Board Meeting", now, "Result"),
               _filing("d2", "Unaudited Financial Results", now + timedelta(minutes=2), "Result"),
               _filing("d3", "Financial Results for the quarter", now + timedelta(minutes=5), "Result"),
               _filing("d4", "Revised Financial Results", now + timedelta(minutes=9), "Result"),
               _filing("e1", "Unaudited Financial Results", now + timedelta(minutes=3), "Result", scrip="999002",
                       name="Other Ltd")]
    pipeline, sink, fake = build(settings, filings, {f.pdf_url: _pdf(LETTER) for f in filings},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)] * 5}, env={"NVIDIA_API_KEY": "n"})
    pipeline.run("live", time_budget_s=60)
    status = {r["news_id"]: (r["status"], r["reason"]) for r in rows(sink, "select news_id, status, reason from filings")}
    same = sorted(n for n in ("d1", "d2", "d3") if status[n][0] == "DUPLICATE")
    assert len(same) == 2, status  # one of the three is analysed, whichever a worker reached first
    original = ({"d1", "d2", "d3"} - set(same)).pop()
    assert status[original][0] == "ANALYZED" and all(status[n][1] == f"duplicate of {original} (exact match)" for n in same)
    assert status["d4"][0] == "ANALYZED" and status["e1"][0] == "ANALYZED"
    assert len(fake.calls) == 3 and pipeline.stats.duplicates == 2
    assert {r["news_id"] for r in rows(sink, "select news_id from cards")} == {original, "d4", "e1"}


def test_a_refiling_that_changes_any_figure_is_not_a_duplicate(settings):
    """A corrected statement filed without "revised" in its title is mostly the same text, but new news."""
    settings = replace(settings, workers=1)
    now = now_ist() - timedelta(minutes=30)
    filings = [_filing("f1", "Unaudited Financial Results", now, "Result"),
               _filing("f2", "Financial Results for the quarter", now + timedelta(minutes=40), "Result")]
    corrected = LETTER.replace("Net profit 1,500.00", "Net profit 1,350.00")
    assert corrected != LETTER
    pdfs = {filings[0].pdf_url: _pdf(LETTER), filings[1].pdf_url: _pdf(corrected)}
    pipeline, sink, fake = build(settings, filings, pdfs, {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)] * 2},
                                 env={"NVIDIA_API_KEY": "n"})
    pipeline.run("live", time_budget_s=60)
    status = {r["news_id"]: r["status"] for r in rows(sink, "select news_id, status from filings")}
    assert status == {"f1": "ANALYZED", "f2": "ANALYZED"} and len(fake.calls) == 2


def test_a_later_run_finds_the_duplicate_through_the_text_cache(settings):
    settings = replace(settings, workers=1)
    now = now_ist() - timedelta(minutes=30)
    first = [_filing("c1", "Outcome of Board Meeting", now, "Result")]
    pipeline, sink, _ = build(settings, first, {first[0].pdf_url: _pdf(LETTER)},
                              {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]}, env={"NVIDIA_API_KEY": "n"})
    pipeline.run("live", time_budget_s=60)
    later = first + [_filing("c2", "Raising of Funds", now + timedelta(minutes=26), "Result")]
    pipeline2, _, fake2 = build(settings, later, {f.pdf_url: _pdf(LETTER) for f in later},
                                {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]}, env={"NVIDIA_API_KEY": "n"})
    pipeline2.run("live", time_budget_s=60)
    status = {r["news_id"]: (r["status"], r["reason"]) for r in rows(sink, "select news_id, status, reason from filings")}
    assert status["c2"] == ("DUPLICATE", "duplicate of c1 (exact match)") and fake2.calls == []


MONTHLY = ("SML Mahindra Limited sales and production for the month of {month} 2025. Particulars: Cargo vehicles"
           " sales {cargo} units against {cargo_ly} units in the same month last year. Passenger vehicles sales"
           " {pax} units against {pax_ly} units. Total sales {total} units, production {prod} units. The figures are"
           " provisional and subject to audit. This is for your information and records.")
CORRECTED = LETTER.replace("12,000.00", "12,400.00").replace("1,500.00", "1,620.00")


def test_template_filings_with_new_numbers_are_never_duplicates(settings):
    """A corrected results statement a day later (not titled revised, two figures changed) and two
    monthly updates in the same words are near-identical text, but hold new numbers: both analysed."""
    settings = replace(settings, workers=1)
    now = now_ist() - timedelta(days=2)
    jan = MONTHLY.format(month="January", cargo=812, cargo_ly=905, pax=213, pax_ly=240, total=1025, prod=1100)
    feb = MONTHLY.format(month="February", cargo=1004, cargo_ly=905, pax=284, pax_ly=240, total=1288, prod=1350)
    filings = [_filing("o1", "Financial Results", now, "Result"),
               _filing("o2", "Outcome of Board Meeting", now + timedelta(days=1), "Result"),
               _filing("m1", "Monthly Business Update", now, "Company Update", scrip="999003"),
               _filing("m2", "Monthly Business Update", now + timedelta(hours=20), "Company Update", scrip="999003")]
    pdfs = {"https://bse.invalid/o1.pdf": _pdf(LETTER), "https://bse.invalid/o2.pdf": _pdf(CORRECTED),
            "https://bse.invalid/m1.pdf": _pdf(jan), "https://bse.invalid/m2.pdf": _pdf(feb)}
    pipeline, sink, _ = build(settings, filings, pdfs, {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)] * 4,
                                                        "openai/gpt-oss-20b": [json.dumps({"is_material": True, "event_type": "MONTHLY_UPDATE"})] * 2},
                              env={"NVIDIA_API_KEY": "n", "GROQ_API_KEY": "g"})
    pipeline.backfill_companies(["999001", "999003"], now.date() - timedelta(days=1), now.date() + timedelta(days=2), 60)
    status = {r["news_id"]: r["status"] for r in rows(sink, "select news_id, status from filings")}
    assert "DUPLICATE" not in status.values(), status
    assert pipeline.stats.duplicates == 0


def test_duplicate_rule_exact_near_and_corrections():
    from bse_intel import duplicates

    cover_a = "To, BSE Limited\nPhiroze Jeejeebhoy Towers, Dalal Street, Mumbai 400001\nSub: Financial Results\nDear Sir,\n"
    cover_b = "To, The Listing Department\nBSE Limited\nSub: Outcome of Board Meeting held on 13.02.2025\nDear Sir/Madam,\n"
    sign = "\nYours faithfully,\nFor Demo Cement Ltd\nCompany Secretary\nDate: 13.02.2025"
    original = duplicates.body(cover_a + LETTER + sign)
    assert duplicates.match(duplicates.body(cover_b + LETTER + "\nThanking you,\nCompliance Officer"), original) == "exact"
    notes = (" The results were reviewed by the audit committee and approved by the board. The statutory auditors"
             " carried out a limited review and issued an unmodified conclusion. Figures of the previous periods are"
             " regrouped wherever necessary to make them comparable. The company operates in a single segment, namely"
             " manufacture and sale of cement, and the chief operating decision maker reviews performance as a whole."
             " The results are also available on the website of the company and of the stock exchange where the"
             " shares of the company are listed. The board places on record its appreciation for the support of all"
             " stakeholders during the quarter under review.")
    long_original = duplicates.body(cover_a + LETTER + notes + sign)
    reworded = duplicates.body(cover_b + LETTER + notes.replace("during the quarter under review", "during the quarter"))
    assert duplicates.match(reworded, long_original) == "near"   # a few words differ, every number is the same
    assert duplicates.match(duplicates.body(CORRECTED), original) is None  # same words, new figures
    jan = MONTHLY.format(month="January", cargo=812, cargo_ly=905, pax=213, pax_ly=240, total=1025, prod=1100)
    feb = MONTHLY.format(month="February", cargo=1004, cargo_ly=905, pax=284, pax_ly=240, total=1288, prod=1350)
    assert duplicates.match(duplicates.body(feb), duplicates.body(jan)) is None
    assert duplicates.match(duplicates.body("Please find attached."), duplicates.body("Please find attached.")) is None
    for title in ("Corrigendum to Financial Results", "Revised Outcome of Board Meeting", "Correction in Results",
                  "Rectified statement", "Amendment to the notice"):
        assert duplicates.is_correction(title), title
    assert not duplicates.is_correction("Financial Results", "Outcome of Board Meeting")


def test_refused_attachment_fails_one_filing_and_three_in_a_row_stop_the_run(settings):
    settings = replace(settings, workers=1)
    now = now_ist() - timedelta(minutes=30)
    filings = _results(5, now)
    pipeline, sink, _ = build(settings, filings, {f.pdf_url: _pdf(RESULT_TEXT) for f in filings},
                              {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]}, env={"NVIDIA_API_KEY": "n"})
    real = pipeline.bse.download

    def download(url, max_bytes=None):
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
                              {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)], "glm-4.5-flash": [json.dumps(PASS2)]},
                              env={"ZAI_API_KEY": "z", "NVIDIA_API_KEY": "n"})
    pipeline.discover(old.date())
    pipeline.bse.download = lambda url, max_bytes=None: (_ for _ in ()).throw(AttachmentError("timed out")) if "old" in url else _pdf(RESULT_TEXT)
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
                              {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]},
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
                              {"nvidia/nemotron-3-super-120b-a12b": [respond]}, env={"NVIDIA_API_KEY": "n"})
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
                              {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(bad)], "glm-4.5-flash": [json.dumps(card_only)]},
                              env={"NVIDIA_API_KEY": "n", "ZAI_API_KEY": "z"})
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
                              {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]}, env={"NVIDIA_API_KEY": "n"})
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
                              env={"ZAI_API_KEY": "z"})
    pipeline.gateway.transcribe_image = lambda png, route="vision": (_ for _ in ()).throw(RuntimeError("vision down"))
    outcome = pipeline._process_one(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}), False, True)
    assert outcome.update["status"] == "FAILED" and "OCR failed" in outcome.update["last_error"]


def test_extracted_text_is_cached_so_reanalysis_never_downloads_again(settings):
    now = now_ist() - timedelta(minutes=30)
    (f,) = _results(1, now)
    pipeline, sink, _ = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                              {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]},
                              env={"NVIDIA_API_KEY": "n"})
    filing = f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"})
    pipeline.analyze(filing)
    pipeline.bse.download = lambda url, max_bytes=None: (_ for _ in ()).throw(AssertionError("downloaded again"))
    outcome = pipeline.analyze(filing)
    assert outcome.update["status"] == "ANALYZED" and list(settings.text_cache_dir.rglob("*.json.gz"))


def test_a_text_cache_entry_from_before_reading_order_is_read_again_once(settings):
    import gzip

    now = now_ist() - timedelta(minutes=30)
    (f,) = _results(1, now)
    pipeline, sink, _ = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                              {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)] * 3},
                              env={"NVIDIA_API_KEY": "n"})
    filing = f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"})
    path = pipeline._cache_path(f.news_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    stale = {"v": 1, "error": None, "digital": ["stale text, file order"], "has_image": [False], "ocr": {}}
    path.write_bytes(gzip.compress(json.dumps(stale).encode()))
    download = pipeline.bse.download
    pipeline.bse.download = lambda url, **kw: (_ for _ in ()).throw(AttachmentError("refused"))
    pipeline.analyze(filing)  # BSE refuses: the old text is used, and stays marked old
    assert pipeline._cached_text(f.news_id)["v"] == 1
    pipeline.bse.download = download
    pipeline.analyze(filing)  # read again from the PDF and stored as current
    cached = pipeline._cached_text(f.news_id)
    assert cached["v"] == 2 and "stale text" not in " ".join(cached["digital"])
    pipeline.bse.download = lambda url, **kw: (_ for _ in ()).throw(AssertionError("downloaded again"))
    assert pipeline.analyze(filing).update["status"] == "ANALYZED"

    # An entry from before pages were also read block by block, kept as the fallback when BSE refuses the
    # PDF, must still say it has no block reading - or it would count as current and never be read again.
    no_blocks = {k: v for k, v in pipeline._cached_text(f.news_id).items() if k != "blocks"}
    path.write_bytes(gzip.compress(json.dumps(no_blocks).encode()))
    pipeline.bse.download = lambda url, **kw: (_ for _ in ()).throw(AttachmentError("refused"))
    pipeline.analyze(filing)
    assert "blocks" not in pipeline._cached_text(f.news_id)
    pipeline.bse.download = download
    pipeline.analyze(filing)
    assert "blocks" in pipeline._cached_text(f.news_id)


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


def test_smoke_test_backfill_covers_only_the_given_companies_in_date_order(settings):
    today = now_ist().date()
    settings = replace(settings, backfill_start=(today - timedelta(days=60)).isoformat(), workers=1)
    at = lambda d: now_ist().replace(hour=17) - timedelta(days=d)  # noqa: E731
    filings = [_filing("a1", "Unaudited Financial Results", at(50), "Result", scrip="506525", name="Kanoria"),
               _filing("a2", "Unaudited Financial Results", at(10), "Result", scrip="506525", name="Kanoria"),
               _filing("b1", "Unaudited Financial Results", at(20), "Result", scrip="999999", name="Other")]
    seen = []

    def respond(kwargs):
        seen.append(kwargs["messages"][1]["content"].split("Filed: ")[1][:10])
        return json.dumps(PASS2)

    pipeline, sink, _ = build(settings, filings, {f.pdf_url: _pdf(RESULT_TEXT) for f in filings},
                              {"glm-4.5-flash": [respond]}, env={"ZAI_API_KEY": "z"})
    stats = pipeline.backfill_companies(["506525"], today - timedelta(days=60), today, 60)
    assert seen == [at(50).date().isoformat(), at(10).date().isoformat()] and stats.status == "OK"
    assert {r["news_id"] for r in rows(sink, "select news_id from cards")} == {"a1", "a2"}


def test_a_long_company_history_is_saved_every_few_filings(settings, monkeypatch):
    today = now_ist().date()
    settings = replace(settings, backfill_start=(today - timedelta(days=60)).isoformat(), workers=1)
    at = lambda d: now_ist().replace(hour=17) - timedelta(days=d)  # noqa: E731
    filings = [_filing(f"k{i}", "Unaudited Financial Results", at(40 - i), "Result", scrip="506525", name="Kanoria")
               for i in range(12)]
    pipeline, sink, _ = build(settings, filings, {f.pdf_url: _pdf(RESULT_TEXT) for f in filings},
                              {"glm-4.5-flash": [json.dumps(PASS2)] * 12}, env={"ZAI_API_KEY": "z"})
    saved = []
    commit = pipeline._commit
    monkeypatch.setattr(pipeline, "_commit", lambda outcomes: (saved.append(len(outcomes)), commit(outcomes)))
    pipeline.backfill_companies(["506525"], today - timedelta(days=60), today, 60)
    assert [n for n in saved if n] == [5, 5, 2]
    assert len(rows(sink, "select news_id from cards")) == 12


def test_sync_to_cloud_copies_cards_state_and_objects_and_resumes(settings, tmp_path):
    from bse_intel.sinks.local import LocalSink
    from bse_intel.sync import Sync

    now = now_ist() - timedelta(minutes=30)
    filings = _results(3, now)
    pipeline, source, _ = build(settings, filings, {f.pdf_url: _pdf(RESULT_TEXT) for f in filings},
                                {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]},
                                env={"NVIDIA_API_KEY": "n"})
    pipeline.run("live", time_budget_s=60)
    held = rows(source, "select news_id from cards")[0]["news_id"]
    source._db.execute("UPDATE cards SET held = 1 WHERE news_id = ?", [held])
    source._db.commit()
    dest = LocalSink(replace(settings, local_dir=tmp_path / "cloud"))
    progress = tmp_path / "progress.json"
    first = Sync(source, dest, progress, write_budget=10).run()  # budget hit almost at once
    assert not first["complete"]
    second = Sync(source, dest, progress, write_budget=10_000_000).run()
    assert second["complete"]
    copied = {r["news_id"] for r in rows(dest, "select news_id from cards")}
    assert copied == {r["news_id"] for r in rows(source, "select news_id from cards")} and len(copied) == 3
    assert dest.get_dossier("999100") == source.get_dossier("999100")
    assert dest.kv_get("live:since") == source.kv_get("live:since")
    assert {r["news_id"] for r in rows(dest, "select news_id from cards where held = 1")} == {held}  # a held card stays out of the cloud feed


def test_run_publishes_the_homepage_snapshot(settings):
    now = now_ist() - timedelta(minutes=30)
    filings = _results(2, now)
    pipeline, sink, _ = build(settings, filings, {f.pdf_url: _pdf(RESULT_TEXT) for f in filings},
                              {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]},
                              env={"NVIDIA_API_KEY": "n"})
    pipeline.run("live", time_budget_s=60)
    snap = json.loads(sink.get_object("daily_feed/latest_snapshot.json"))
    assert snap["limit"] == 50 and snap["feed"]["total"] == 2 and len(snap["feed"]["cards"]) == 2
    assert {"card_json", "actionability_score", "market_cap_cr"} <= set(snap["feed"]["cards"][0])
    # A held card stays off the homepage as it does in the live feed: the snapshot queries had no held = 0
    # (audit of discard paths, 2026-10-18).
    sink._db.execute("UPDATE cards SET held = 1, is_actionable_signal = 1 WHERE news_id = ?", (filings[0].news_id,))
    start = (now.date() - timedelta(days=7)).isoformat()
    assert [c["news_id"] for c in sink.query("snapshot_feed", [start, 50])] == [filings[1].news_id]
    assert sink.query("snapshot_count", [start])[0]["n"] == 1
    assert filings[0].news_id not in [c["news_id"] for c in sink.query("snapshot_signals", [start])]


def test_owner_starred_and_noise_cards_are_shown_to_the_analyst(settings):
    now = now_ist() - timedelta(minutes=30)
    (f,) = _results(1, now)
    prompts = []

    def respond(kwargs):
        prompts.append(kwargs["messages"][1]["content"])
        return json.dumps(PASS2)

    pipeline, sink, _ = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                              {"nvidia/nemotron-3-super-120b-a12b": [respond]}, env={"NVIDIA_API_KEY": "n"})
    starred = {"headline": "Starred example headline", "what_happened": ["fact"], "why_it_matters": [{"text": "why"}]}
    sink._db.execute("INSERT INTO card_feedback (news_id, scrip_code, sector, event_category, rating, card_json_snapshot, created_at)"
                     " VALUES ('x1', '1', 'default', 'RESULTS', 'STARRED', ?, '2026-01-01')", [json.dumps(starred)])
    sink._db.commit()
    pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    assert "OWNER'S STARRED CARDS" in prompts[0] and "Starred example headline" in prompts[0]


def test_an_unreadable_attachment_fails_before_any_card_and_an_announcement_without_one_is_its_headline(settings):
    """With no text and no XBRL the card was written from the headline and its quote checks crashed on the empty
    text (check_quotes returned three values for four), so the filing ended FAILED with a ValueError and, after
    three runs, for good (audit of discard paths, 2026-10-18). Now an unreadable attachment fails with that reason
    before any model is asked; an exchange's clarification request, which has no attachment, is read from its
    headline and subject."""
    now = now_ist() - timedelta(minutes=30)
    (f,) = _results(1, now)
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: b"PK\x03\x04 not a pdf"},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]})
    outcome = pipeline._process_one(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}), False, True)
    assert outcome.update["status"] == "FAILED" and "no readable text in the attachment" in outcome.update["last_error"]
    assert fake.calls == []

    headline = "The Exchange has sought clarification from Demo Cement Ltd with reference to a media report on a plant shutdown"
    text_only = f.model_copy(update={"news_id": "n-clar", "pdf_url": None, "headline": headline, "subject": headline,
                                     "route": "FAST_TRACK", "event_type": "OTHER"})
    reply = {"is_material": True, "event_type": "OTHER", "timeline_entry": "Exchange sought clarification",
             "card": {"impact_level": "LOW", "headline": "Exchange seeks clarification from Demo Cement on plant report",
                      "what_happened": [{"text": "The exchange sought a clarification on a media report",
                                         "quote": "has sought clarification from Demo Cement Ltd with reference to a media report"}]}}
    pipeline, sink, fake = build(settings, [text_only], {}, {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(reply)]})
    outcome = pipeline._process_one(text_only, False, True)
    assert outcome.update["status"] == "ANALYZED"


def test_a_held_card_is_not_shown_to_the_analyst_as_peer_context(settings):
    """A card held because its figures could not be verified must not shape another company's card."""
    from bse_intel.sinks.local import LocalSink

    sink = LocalSink(settings)
    for news_id, held in (("peer-ok", 0), ("peer-held", 1)):
        sink._db.execute(
            "INSERT INTO cards (news_id, scrip_code, company_name, filing_date, filed_at, sector, event_category,"
            " impact_level, headline, card_json, created_at, held) VALUES (?, '111', 'Peer', '2026-10-01',"
            " '2026-10-01T10:00:00+05:30', 'cement', 'RESULTS', 'HIGH', ?, '{}', '2026-10-01', ?)",
            [news_id, f"headline {news_id}", held])
    sink._db.commit()
    peers = sink.peer_cards("cement", "RESULTS", "222", "2026-09-01", "2026-10-15")
    assert [p["headline"] for p in peers] == ["headline peer-ok"]
