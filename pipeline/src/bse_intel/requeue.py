"""Give filings that used every attempt another try (owner, 2026-10-20).

A filing that fails three times for a reason of its own (an answer still invalid after repair, a processing error)
stays FAILED and no run picks it up again; busy or exhausted providers, timeouts and refusals never spend an attempt,
so they are not here. After a fix, such a filing would keep no card. ``requeue`` sets it PENDING with ``attempts_left``
tries (all of them by default, from the ``requeue-failed`` command); each night the live run gives the last 7 days'
failed filings one more try, so a filing broken by a bug fixed that day still gets its card. No AI.
"""

from __future__ import annotations

import logging

from .timeutil import now_iso

log = logging.getLogger(__name__)

LIMIT = 500


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


def requeue(sink, since: str, max_attempts: int, attempts_left: int | None = None, dry_run: bool = False) -> dict:
    """Set the failed filings since ``since`` PENDING with ``attempts_left`` tries (default all); returns a summary."""
    left = max_attempts if attempts_left is None else max(1, min(attempts_left, max_attempts))
    rows = failed(sink, since, max_attempts)
    stamp = now_iso()
    updates = [{"news_id": r["news_id"], "status": "PENDING", "attempts": max_attempts - left, "updated_at": stamp,
                "last_error": f"requeued {stamp[:10]} after: {r.get('last_error') or ''}"[:500]} for r in rows]
    if updates and not dry_run:
        sink.execute("filings_update", updates)
    return {"since": since, "requeued": len(updates), "attempts_left": left, "dry_run": dry_run,
            "filings": [f"{r['news_id']} {r.get('symbol') or r.get('scrip_code')} {r['filed_at'][:10]}" for r in rows[:50]]}
