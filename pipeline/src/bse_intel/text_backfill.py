"""One-time text backfill for the stored cards that have no filing text in R2. No AI; no card, memory or filings write. TRACKER F165, TODO 51.

The text cache (``text/<news_id>.json.gz``, F147) only started on 25 Oct 2026, so about 6,870 of 7,077 stored cards have no
text and an audit cannot re-check them (audit_precision.py: "no text 6872"). Owner, 26 Oct 2026: download the text once, only
for the cards that lack it.

For each such card the filing's attachment is fetched from NSE exactly as the pipeline does (``NseClient.fetch``: its
headers, 3-5 s pacing, retries, the 120 MB cap, a refusal stops the run), read with the pipeline's own ``Document`` (a ZIP's
PDFs merged, F132; cut-short detection; local OCR on pages of figures and scanned pages when RapidOCR is installed, never
the vision route, which is an AI call) and written with the pipeline's own text-cache bytes (``pipeline.text_cache_body``)
to ``text/<news_id>.json.gz``. Only that object is written.

Which cards: one listing of the ``text/`` prefix, not a head request a card. A filing whose ledger row failed for good with
no text (audio only, a ZIP with no PDF, too large) is left out; so is a card with no attachment or one not on NSE (BSE is
off the path). A filing that fails here is kept in kv ``textbackfill:failed:<i>of<n>`` with its reason and not fetched again
by the next run (``--restart`` tries it again); a network failure is not kept, so it is retried. Written objects are skipped
by the listing, so a run that ends on its time budget (exit 124) is started again and resumes. At most 2 shards, so NSE sees
the load of memory-gaps-fill. The next download starts while the current file is read; NSE still sees one request at a
time, at the client's own pace.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from . import pipeline as P
from .bse import AttachmentError, AttachmentTooLarge, SourceBlockedError
from .extract import Document
from .timeutil import now_iso

log = logging.getLogger(__name__)

MAX_SHARDS = 2
FAILED_KEY = "textbackfill:failed"      # + ":<i>of<n>": {news_id: reason} for the filings that will not be tried again
NETWORK_STOP = 3                         # downloads failing on the network in a row stop the run (the pipeline's rule)
FETCH_PAUSE_S = 4.0                      # NseClient's default pause is 3-5 s between requests
# what a ledger row's last_error says when the filing has no text for good (pipeline.NoTextAttachment, AttachmentTooLarge)
KNOWN_NO_TEXT = re.compile(r"audio only|a ZIP with no PDF|over the cap|too large|larger than", re.I)

R_NO_URL = "no attachment (the card has no file)"
R_NOT_NSE = "not an NSE file"
R_404 = "404 (NSE does not serve it)"
R_CUT = "cut short"
R_LARGE = "too large"
R_AUDIO = "ZIP audio only"
R_ZIP = "ZIP with no PDF"
R_UNREADABLE = "unreadable"
R_OCR = "OCR failed"
R_NOTEXT = "no text"
R_NETWORK = "network"


def failure_reason(doc: Document) -> str | None:
    """Why a read document is not worth storing (None when it is): the pipeline's own error strings."""
    err = doc.error or ""
    if err.startswith("audio only"):
        return R_AUDIO
    if err.startswith("a ZIP with no PDF"):
        return R_ZIP
    if err.startswith("cut short"):
        return R_CUT
    if err:
        return R_UNREADABLE
    if not doc.page_count:
        return R_NOTEXT
    return None


def known_no_text(sink) -> set[str]:
    """News ids whose filing failed for good with a no-text reason (the ledger's last_error); best effort."""
    try:
        rows = sink.query("filings_failed", ["2000-01-01", 1, 100000])
    except Exception as exc:  # noqa: BLE001 - the list only saves a download; without it the file is tried and fails with its reason
        log.warning("failed filings not listed: %s", exc)
        return set()
    return {r["news_id"] for r in rows if KNOWN_NO_TEXT.search(r.get("last_error") or "")}


def cards_lacking_text(sink, limit: int | None = None) -> tuple[list[dict], dict]:
    """The stored cards whose text object is missing, as ({news_id, pdf_url, filed_at}, counts). One listing of ``text/``."""
    have = set(sink.list_objects(P.TEXT_PREFIX))
    no_text = known_no_text(sink)
    rows, counts = [], Counter()
    after = ["", ""]
    while True:
        page = sink.query("export_cards", [after[0], after[1], 100])
        if not page:
            break
        after = [page[-1]["filed_at"], page[-1]["news_id"]]
        for r in page:
            counts["cards"] += 1
            nid = r["news_id"]
            if P.text_key(nid) in have:
                counts["with_text"] += 1
            elif nid in no_text:
                counts["known_no_text"] += 1
            else:
                rows.append({"news_id": nid, "pdf_url": r.get("pdf_url") or "", "filed_at": r.get("filed_at") or ""})
        if len(page) < 100:
            break
    counts["lacking"] = len(rows) + counts["known_no_text"]
    return (rows[:limit] if limit else rows), dict(counts)


def estimate(n: int, shards: int = 1, ocr: bool = True) -> dict:
    """Assumption (not measured): one NSE request a filing at the client's 4 s mean pause plus about 2 s to download; the
    reading (and OCR) of one filing overlaps the next download, so a filing takes the longer of the two."""
    per = max(FETCH_PAUSE_S + 2.0, 8.0 if ocr else 1.5)
    return {"filings": n, "seconds_each": per, "seconds": round(n * per / max(1, shards))}


def _fetch(client, url: str, cap: int):
    """('ok', bytes) / ('none', None) / ('error', exception): taken on the download thread, judged on the main one."""
    try:
        data = client.fetch(url, max_bytes=cap)
    except Exception as exc:  # noqa: BLE001 - the main thread decides what each kind of failure means
        return ("error", exc)
    return ("ok", data) if data else ("none", None)


def run(sink, rows: list[dict], client, shard: tuple[int, int] | None = None, time_budget: float = 17400.0,
        restart: bool = False, ocr: bool = True, max_ocr_pages: int = 6, cap: int = P.ATTACHMENT_MAX_BYTES,
        clock=time.monotonic) -> dict:
    """Fetch, read and store the text of this shard's rows. A refusal from NSE propagates (what is stored stays, and the
    failures so far are saved). ``more`` is true when the time budget ended the run with filings left."""
    key = FAILED_KEY + (f":{shard[0]}of{shard[1]}" if shard else ":0of1")
    failed_map = dict(json.loads(sink.kv_get(key) or "{}"))
    before = {} if restart else dict(failed_map)   # --restart tries them again; the list stays until each one is written
    todo = list(rows)
    if shard:
        todo = todo[shard[0]::shard[1]]
    queue = [r for r in todo if r["news_id"] not in before]
    totals = {"filings": len(todo), "skipped_failed_before": len(todo) - len(queue), "fetched": 0, "written": 0,
              "failed": 0, "more": False, "ocr": ocr}
    reasons: Counter = Counter()
    read_seconds = 0.0

    def fail(nid: str, why: str, keep: bool = True) -> None:
        totals["failed"] += 1
        reasons[why] += 1
        if keep:
            failed_map[nid] = why
            sink.kv_set(key, json.dumps(failed_map, sort_keys=True), now_iso())

    ocr_fn = figure_fn = None
    if ocr:
        from .ocr import available as local_ocr_available
        from .ocr import page_reader, recognise
        ocr_fn = page_reader(None)      # local OCR for scanned pages; never the vision route (an AI call)
        figure_fn = recognise if local_ocr_available() else None

    started = clock()
    deadline = started + time_budget
    streak = 0
    pool = ThreadPoolExecutor(max_workers=1)
    futures: dict[int, object] = {}

    def want(i: int) -> None:
        """Start row i's download (when it has an NSE file) so it runs while the row before is read."""
        if i < len(queue) and i not in futures:
            url = queue[i]["pdf_url"]
            futures[i] = pool.submit(_fetch, client, url, cap) if url and "nseindia.com" in url else None

    try:
        for i, row in enumerate(queue):
            if clock() >= deadline:
                totals["more"] = True
                break
            nid, url = row["news_id"], row["pdf_url"]
            if not url:
                fail(nid, R_NO_URL)
                continue
            if "nseindia.com" not in url:
                fail(nid, R_NOT_NSE)
                continue
            want(i)
            want(i + 1)
            kind, payload = futures.pop(i).result()
            totals["fetched"] += 1
            if kind == "error":
                if isinstance(payload, SourceBlockedError):
                    raise payload
                if isinstance(payload, AttachmentTooLarge):
                    streak = 0
                    fail(nid, R_LARGE)
                elif isinstance(payload, AttachmentError):
                    streak += 1
                    fail(nid, R_NETWORK, keep=False)   # tried again by the next run
                    if streak >= NETWORK_STOP:
                        log.error("%d attachment downloads failed on the network in a row; stopping", streak)
                        totals["stopped"] = f"{streak} downloads failed on the network in a row"
                        break
                else:
                    raise payload
                continue
            streak = 0
            if kind == "none":
                fail(nid, R_404)
                continue
            began = clock()
            doc = Document(payload, ocr=ocr_fn, max_ocr_pages=max_ocr_pages, figure_reader=figure_fn)
            try:
                why = failure_reason(doc)
                if why is None:
                    doc.select_text(10_000_000, [])   # reads every page, OCR where the pipeline would, so the cache holds it
                    if doc.ocr_error is not None:     # the pipeline does not cache a reading whose OCR failed
                        why = R_OCR
                if why:
                    fail(nid, why)
                else:
                    sink.put_object(P.text_key(nid), P.text_cache_body(doc), content_type="application/gzip")
                    totals["written"] += 1
                    if failed_map.pop(nid, None) is not None:
                        sink.kv_set(key, json.dumps(failed_map, sort_keys=True), now_iso())
            finally:
                doc.close()
            read_seconds += clock() - began
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    elapsed = clock() - started
    return {**totals, "reasons": dict(reasons), "failed_total": len(failed_map), "elapsed_seconds": round(elapsed, 1),
            "seconds_per_filing": round(elapsed / totals["fetched"], 2) if totals["fetched"] else None,
            "read_seconds_per_written": round(read_seconds / totals["written"], 2) if totals["written"] else None}


def render(outcome: dict, counts: dict | None = None) -> str:
    lines = ["text backfill:"]
    if counts:
        lines += [f"stored cards                 {counts.get('cards', 0)}",
                  f"cards with text already      {counts.get('with_text', 0)}",
                  f"cards without text           {counts.get('lacking', 0)}",
                  f"  known no-text filings      {counts.get('known_no_text', 0)}"]
    lines += [f"filings in this shard        {outcome['filings']}",
              f"failed in an earlier run     {outcome['skipped_failed_before']}",
              f"fetched from NSE             {outcome['fetched']}",
              f"written                      {outcome['written']}",
              f"failed                       {outcome['failed']}",
              f"OCR                          {'on' if outcome.get('ocr') else 'off (figure and scanned pages keep their text layer)'}",
              f"seconds per filing           {outcome.get('seconds_per_filing')}",
              f"reading seconds per written  {outcome.get('read_seconds_per_written')}",
              f"elapsed seconds              {outcome.get('elapsed_seconds')}"]
    for why, n in sorted(outcome["reasons"].items(), key=lambda kv: -kv[1]):
        lines.append(f"  failed: {why:<30} {n}")
    if outcome.get("stopped"):
        lines.append(f"stopped: {outcome['stopped']}")
    return "\n".join(lines)
