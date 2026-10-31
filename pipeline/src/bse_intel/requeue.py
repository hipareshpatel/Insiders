"""Give filings that used every attempt another try (owner, 2026-10-20).

A filing that fails three times for a reason of its own (an answer still invalid after repair, a processing error)
stays FAILED and no run picks it up again; busy or exhausted providers, timeouts and refusals never spend an attempt,
so they are not here. After a fix, such a filing would keep no card. ``requeue`` sets it PENDING with ``attempts_left``
tries (all of them by default, from the ``requeue-failed`` command); each night the live run gives the last 7 days'
failed filings one more try, so a filing broken by a bug fixed that day still gets its card. No AI.
"""

from __future__ import annotations

import json

import logging
import re

from .timeutil import now_iso

log = logging.getLogger(__name__)

LIMIT = 500
TOO_LARGE = ("AttachmentTooLarge", "NoTextAttachment: audio only", "NoTextAttachment: a ZIP with no PDF")


def _reason(error: str) -> str:
    """A failure's reason without what differs from filing to filing (links, ids, sizes), so like ones group."""
    text = re.sub(r"https?://\S+", "<url>", error or "(no reason stored)")
    text = re.sub(r"\b(nse|bse)-\d+\b", "<id>", text)
    text = re.sub(r"\d[\d,.]*", "<n>", text)
    return text[:120]


def report(sink, since: str, limit: int = LIMIT) -> dict:
    """Every FAILED filing filed on or after ``since`` (whatever its attempts), grouped by reason, largest group
    first, with up to three examples each (owner, 25 Oct 2026: why do filings fail?). Reads only; no AI."""
    rows = sink.query("filings_failed", [since, 0, limit])
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(_reason(str(row.get("last_error") or "")), []).append(row)
    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    return {"since": since, "failed": len(rows), "capped": len(rows) >= limit,
            "reasons": [{"reason": reason, "count": len(group),
                         "examples": [f"{r['news_id']} {r.get('symbol') or r.get('scrip_code')} {str(r.get('filed_at'))[:10]} "
                                      f"{r.get('event_type') or ''} attempts={r.get('attempts')}" for r in group[:3]]}
                        for reason, group in ordered]}


def waiting(sink, start: str, end: str, max_attempts: int, limit: int = LIMIT) -> dict:
    """The filings of ``start``..``end`` (inclusive) still to be read (PENDING, or FAILED with attempts left), counted by
    filed day and event type, with up to five results filings named (owner, 30 Oct 2026: was every results filing of the
    last days read?). Reads only; the live run's own query (filings_pending), one page."""
    rows = sink.query("filings_pending", [start, end, max_attempts, limit, "", ""])
    by_day: dict[str, dict[str, int]] = {}
    for r in rows:
        day = by_day.setdefault(str(r.get("filed_at"))[:10], {})
        kind = r.get("event_type") or "(not read yet)"
        day[kind] = day.get(kind, 0) + 1
    results = [r for r in rows if r.get("event_type") == "RESULTS" or "result" in str(r.get("subject") or r.get("headline") or "").lower()]
    return {"from": start, "to": end, "waiting": len(rows), "capped": len(rows) >= limit, "by_day": by_day,
            "results_like": len(results),
            "results_examples": [f"{r['news_id']} {r.get('symbol') or r.get('scrip_code')} {str(r.get('filed_at'))[:16]} "
                                 f"{r.get('status')} attempts={r.get('attempts')}" for r in results[:5]]}


def failed(sink, since: str, max_attempts: int, limit: int = LIMIT) -> list[dict]:
    """Filings out of attempts filed on or after ``since``, newest first."""
    return sink.query("filings_failed", [since, max_attempts, limit])


def requeue_ids(sink, news_ids: list[str], max_attempts: int, dry_run: bool = False) -> dict:
    """Named filings, whatever their status, set PENDING with every attempt: a held or stale card re-run after a fix
    (the laptop's T24/T18 lists). A re-run replaces the filing's card and its memory entry."""
    stamp = now_iso()
    updates = [{"news_id": n, "status": "PENDING", "attempts": 0, "updated_at": stamp,
                "last_error": f"requeued {stamp[:10]} by id"} for n in dict.fromkeys(news_ids) if n]
    if updates and not dry_run:
        sink.execute("filings_update", updates)
    return {"requeued": len(updates), "dry_run": dry_run, "filings": [u["news_id"] for u in updates]}


PRIORITY_KEY = "backfill:priority"


def prioritise(sink, scrips: list[str]) -> list[str]:
    """Put the named companies first in the history queue (pipeline._backfill reads ``backfill:priority``): a filing requeued by
    id that is older than the live window would otherwise wait behind every other company's history (31 Oct 2026: Hubtown
    nse-106629168, filed 19 May, requeued after the unit-slip fix, waited behind ~1,500 history filings). Returns the list kept."""
    have = json.loads(sink.kv_get(PRIORITY_KEY) or "[]")
    kept = list(dict.fromkeys([s for s in scrips if s] + list(have)))
    sink.kv_set(PRIORITY_KEY, json.dumps(kept), now_iso())
    return kept


BY_ID_KEY = "requeue:by_id"
BY_ID_MAX = 50   # the list kept between runs; a run reads at most pipeline.REQUEUED_FIRST_MAX of them


def mark_by_id(sink, news_ids: list[str], scrips: list[str]) -> dict:
    """Name the filings requeued by id, and their companies, for the run's short slot after today's filings
    (pipeline._requeued_first). In results season today's filings used every run's whole time, so the history pass where a
    requeue by id waited never started (31 Oct 2026: Hubtown nse-106629168 still wrong six hours after its requeue; run
    41196991535 deferred 20 of the day's filings). The run drops an id once it is no longer pending."""
    have = json.loads(sink.kv_get(BY_ID_KEY) or "{}")
    ids = list(dict.fromkeys([n for n in news_ids if n] + list(have.get("ids", []))))[:BY_ID_MAX]
    companies = list(dict.fromkeys([s for s in scrips if s] + list(have.get("scrips", []))))[:BY_ID_MAX]
    kept = {"ids": ids, "scrips": companies}
    sink.kv_set(BY_ID_KEY, json.dumps(kept), now_iso())
    return kept


def requeue(sink, since: str, max_attempts: int, attempts_left: int | None = None, dry_run: bool = False) -> dict:
    """Set the failed filings since ``since`` PENDING with ``attempts_left`` tries (default all); returns a summary."""
    left = max_attempts if attempts_left is None else max(1, min(attempts_left, max_attempts))
    # a file over the size cap, or with no text in it, stays so: requeued, it only fails the same way again (by id it can be)
    rows = [r for r in failed(sink, since, max_attempts) if not str(r.get("last_error") or "").startswith(TOO_LARGE)]
    stamp = now_iso()
    updates = [{"news_id": r["news_id"], "status": "PENDING", "attempts": max_attempts - left, "updated_at": stamp,
                "last_error": f"requeued {stamp[:10]} after: {r.get('last_error') or ''}"[:500]} for r in rows]
    if updates and not dry_run:
        sink.execute("filings_update", updates)
    return {"since": since, "requeued": len(updates), "attempts_left": left, "dry_run": dry_run,
            "filings": [f"{r['news_id']} {r.get('symbol') or r.get('scrip_code')} {r['filed_at'][:10]}" for r in rows[:50]]}
