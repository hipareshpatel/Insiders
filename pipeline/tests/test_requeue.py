from __future__ import annotations

from datetime import timedelta

from test_pipeline import RESULT_TEXT, _filing, _pdf, build, rows

from bse_intel import requeue
from bse_intel.timeutil import now_ist


def _failed_filings(settings):
    now = now_ist() - timedelta(minutes=5)
    filings = [_filing(f"f{i}", "Unaudited Financial Results for the quarter", now - timedelta(days=d), "Result",
                       scrip=str(999100 + i)) for i, d in enumerate((0, 3, 20))]
    pipeline, sink, _ = build(settings, filings, {f.pdf_url: _pdf(RESULT_TEXT) for f in filings}, {})
    for f in filings:
        sink._db.execute("INSERT INTO filings (news_id, scrip_code, company_name, headline, filed_at, filing_date,"
                         " status, attempts) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', 0)",
                         (f.news_id, f.scrip_code, f.company_name, f.headline, f.filed_at, f.filing_date))
    sink._db.execute("UPDATE filings SET status = 'FAILED', attempts = 3, last_error = 'ValidationError: x'"
                     " WHERE news_id LIKE 'f%'")
    sink._db.commit()
    return pipeline, sink, now


def test_requeue_gives_failed_filings_fresh_attempts_since_a_date(settings):
    """Owner, 2026-10-20: a filing that used its three attempts was never tried again, even after a fix."""
    pipeline, sink, now = _failed_filings(settings)
    since = (now - timedelta(days=7)).date().isoformat()
    assert {r["news_id"] for r in requeue.failed(sink, since, 3)} == {"f0", "f1"}
    report = requeue.requeue(sink, since, 3, dry_run=True)
    assert report["requeued"] == 2 and rows(sink, "select count(*) n from filings where status = 'FAILED'")[0]["n"] == 3
    report = requeue.requeue(sink, since, 3)
    got = {r["news_id"]: (r["status"], r["attempts"]) for r in rows(sink, "select news_id, status, attempts from filings")}
    assert got == {"f0": ("PENDING", 0), "f1": ("PENDING", 0), "f2": ("FAILED", 3)}
    assert rows(sink, "select last_error from filings where news_id = 'f0'")[0]["last_error"].startswith("requeued ")
    # the queue reads them again
    assert {r["news_id"] for r in sink.pending_filings(since, now.date().isoformat(), 3, 50)} >= {"f0", "f1"}


def test_the_nightly_requeue_gives_one_more_try_once_a_night(settings, monkeypatch):
    from bse_intel import pipeline as mod

    pipeline, sink, now = _failed_filings(settings)
    live_from = now.date() - timedelta(days=7)
    night = now_ist().replace(hour=22, minute=10)
    monkeypatch.setattr(mod, "now_ist", lambda: night)
    pipeline._requeue_failed_nightly(live_from)
    got = {r["news_id"]: (r["status"], r["attempts"]) for r in rows(sink, "select news_id, status, attempts from filings")}
    assert got["f0"] == ("PENDING", 2) and got["f2"] == ("FAILED", 3)
    assert sink.kv_get(mod.REQUEUE_KEY) == night.date().isoformat()
    sink._db.execute("UPDATE filings SET status = 'FAILED', attempts = 3 WHERE news_id = 'f0'")
    sink._db.commit()
    pipeline._requeue_failed_nightly(live_from)   # once a night
    assert rows(sink, "select status from filings where news_id = 'f0'")[0]["status"] == "FAILED"
    monkeypatch.setattr(mod, "now_ist", lambda: night.replace(hour=15))
    sink._db.execute("DELETE FROM kv")
    sink._db.commit()
    pipeline._requeue_failed_nightly(live_from)   # not before 22:00
    assert rows(sink, "select status from filings where news_id = 'f0'")[0]["status"] == "FAILED"


def test_requeue_by_id_reruns_named_filings_whatever_their_status(settings):
    """The laptop's held and stale cards (T24, T18) re-run on production after a fix."""
    pipeline, sink, _ = _failed_filings(settings)
    sink._db.execute("UPDATE filings SET status = 'DONE', attempts = 1 WHERE news_id = 'f2'")
    sink._db.commit()
    report = requeue.requeue_ids(sink, ["f2", "f2", "", "f1"], 3)
    assert report["requeued"] == 2
    got = {r["news_id"]: (r["status"], r["attempts"]) for r in rows(sink, "select news_id, status, attempts from filings")}
    assert got["f2"] == ("PENDING", 0) and got["f1"] == ("PENDING", 0) and got["f0"] == ("FAILED", 3)


def test_a_scheduled_job_records_its_last_run():
    """Owner, 2026-10-20: market-data had never run on GitHub and nothing showed it; each scheduled command records
    when it ended and whether it succeeded (kv job:<command>), and other commands record nothing."""
    import json

    from bse_intel.cli import _record_job

    written = {}

    class Sink:
        def kv_set(self, key, value, updated_at):
            written[key] = json.loads(value)

    _record_job(Sink(), "market-data", 0)
    _record_job(Sink(), "refresh-summaries", 1)
    _record_job(Sink(), "analyze-pdf", 0)
    assert written["job:market-data"]["ok"] is True and written["job:refresh-summaries"]["ok"] is False
    assert "job:analyze-pdf" not in written


def test_failed_report_groups_failures_by_reason_and_the_requeue_skips_files_too_large(settings):
    """Owner, 25 Oct 2026: why do filings fail? And a file over the size cap is not downloaded again for nothing."""
    pipeline, sink, now = _failed_filings(settings)
    sink._db.execute("UPDATE filings SET last_error = 'AttachmentTooLarge: file too large (over 120 MB): "
                     "https://nsearchives.nseindia.com/x.pdf' WHERE news_id = 'f0'")
    sink._db.execute("UPDATE filings SET attempts = 1 WHERE news_id = 'f2'")
    sink._db.commit()
    since = (now - timedelta(days=30)).date().isoformat()
    report = requeue.report(sink, since)
    assert report["failed"] == 3 and report["reasons"][0] == {
        "reason": "ValidationError: x", "count": 2, "examples": report["reasons"][0]["examples"]}
    assert report["reasons"][1]["reason"].startswith("AttachmentTooLarge: file too large (over <n> MB): <url>")
    assert requeue.requeue(sink, since, 3)["requeued"] == 1   # f1 only: f0 is too large, f2 has attempts left
