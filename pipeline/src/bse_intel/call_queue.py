"""The queue of call-memory readings (F180, docs/design/call-memory.md "queued job"): with MEMORY_CALL_V2 on, the 15-minute
pipeline run only notes a transcript or deck here (a few bytes, no AI), and `call-memory --pending` reads them in a job of
its own, so a slow reply (1-5 minutes) never holds the cards.

Stored in the sink's kv table, which has no list or delete, as two sets of keys with one writer each, so no job overwrites
another's entries:
  callmem:q:<day>   written by the pipeline only (an enqueue): {news_id: {"scrip": ..., "filed_at": ..., "at": iso}}
  callmem:s:<day>   written by the queue job only (one at a time, its own concurrency group):
                    {news_id: {"state": "done" | "gave_up" | "retry", "attempts": n, "reason": ..., "at": iso}}
<day> is the UTC day of the enqueue. A filing is pending until its state is done or gave_up for its latest enqueue (a re-run
enqueues again with a later time and so reads again). The job looks back QUEUE_DAYS days.
An enqueue is a read-modify-write of one key under a lock (the run's workers are threads) with a re-read just before the
write. The live pipeline's runs never overlap (concurrency group bse-pipeline), but a maintenance `requeue-failed` can run
beside one; a lost entry is only a reading that waits for `call-memory --ids`.
A state records the enqueue it settles (`for`: that enqueue's `at`), so a re-enqueue made while the job reads is read again.
The job counts an attempt before it reads (a run killed mid-reading still counts one), so one document can never hold the
head of the queue for more than MAX_ATTEMPTS runs.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone



log = logging.getLogger(__name__)

QUEUE_DAYS = 14      # how far back the job looks; an older entry is left unread
BACKLOG_TRIED = "callmem:backlog"   # {news_id: day queued} of every document `enqueue_backlog` queued (~2,000 at most)
MAX_ATTEMPTS = 3     # a transient failure leaves the filing queued; after this many it is given up with the reason
_lock = threading.Lock()


def _stamp() -> str:
    """UTC with microseconds: a re-enqueue is always later than the state that settled the earlier one."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _day(offset: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=offset)).date().isoformat()


def _load(sink, key: str) -> dict:
    try:
        data = json.loads(sink.kv_get(key) or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def enqueue(sink, news_id: str, scrip_code: str, filed_at: str) -> None:
    """Note a filing for the queue job. Cheap; the caller swallows any failure (the card is never held for it)."""
    key = f"callmem:q:{_day()}"
    entry = {"scrip": str(scrip_code), "filed_at": filed_at, "at": _stamp()}
    with _lock:
        items = _load(sink, key)   # read just before the write: keeps what another writer added meanwhile
        items[news_id] = entry
        sink.kv_set(key, json.dumps(items, ensure_ascii=False), _stamp())


def pending(sink, days: int = QUEUE_DAYS) -> list[dict]:
    """The filings still to read, oldest enqueue first: [{news_id, day, scrip, filed_at, at, attempts}]."""
    out = []
    for offset in range(days - 1, -1, -1):
        day = _day(offset)
        queued = _load(sink, f"callmem:q:{day}")
        if not queued:
            continue
        states = _load(sink, f"callmem:s:{day}")
        for news_id, item in queued.items():
            state = states.get(news_id) or {}
            # the state is about this enqueue, not an earlier one
            current = state["for"] == item.get("at") if "for" in state else state.get("at", "") >= item.get("at", "")
            if current and state.get("state") in ("done", "gave_up"):
                continue
            out.append({"news_id": news_id, "day": day, **item, "attempts": int(state.get("attempts", 0)) if current else 0})
    return sorted(out, key=lambda i: i.get("at", ""))


def start(sink, item: dict) -> bool:
    """Count this attempt before the reading (state 'retry', "started, not finished"). False when the filing already had
    MAX_ATTEMPTS (runs killed mid-reading): it is given up instead and not read."""
    if int(item.get("attempts", 0)) >= MAX_ATTEMPTS:
        settle(sink, item, "gave_up", "killed mid-reading too often", count=False)
        return False
    key = f"callmem:s:{item['day']}"
    states = _load(sink, key)
    item["attempts"] = int(item.get("attempts", 0)) + 1
    states[item["news_id"]] = {"state": "retry", "attempts": item["attempts"], "at": _stamp(), "for": item.get("at", ""),
                               "reason": "started, not finished"}
    sink.kv_set(key, json.dumps(states, ensure_ascii=False), _stamp())
    return True


def defer(sink, item: dict, reason: str) -> None:
    """The reading never ran for want of a day's quota (F203): the attempt `start` counted is given back and the filing stays
    queued ('retry'), so a spent quota never uses up a filing's MAX_ATTEMPTS. Only the queue job calls this."""
    key = f"callmem:s:{item['day']}"
    states = _load(sink, key)
    item["attempts"] = max(0, int(item.get("attempts", 0)) - 1)
    states[item["news_id"]] = {"state": "retry", "attempts": item["attempts"], "at": _stamp(), "for": item.get("at", ""),
                               "reason": reason[:200]}
    sink.kv_set(key, json.dumps(states, ensure_ascii=False), _stamp())


def settle(sink, item: dict, state: str, reason: str | None = None, count: bool = True) -> str:
    """Record the outcome of one reading: 'done' or 'gave_up' leave the queue, 'retry' counts an attempt (unless ``count`` is
    false: the attempt was counted when the reading started) and becomes 'gave_up' at MAX_ATTEMPTS. Returns the state stored.
    Only the queue job calls this."""
    key = f"callmem:s:{item['day']}"
    states = _load(sink, key)
    attempts = int(item.get("attempts", 0)) + (1 if state == "retry" and count else 0)
    if state == "retry" and attempts >= MAX_ATTEMPTS:
        state = "gave_up"
    states[item["news_id"]] = {"state": state, "attempts": attempts, "at": _stamp(), "for": item.get("at", ""),
                               **({"reason": reason[:200]} if reason else {})}
    sink.kv_set(key, json.dumps(states, ensure_ascii=False), _stamp())
    item["attempts"] = attempts
    return state


def known_ids(sink, days: int = QUEUE_DAYS) -> set[str]:
    """Every news_id in a queue key of the last `days` days, read or not (the states only settle entries of the queue)."""
    out: set[str] = set()
    for offset in range(days):
        out.update(_load(sink, f"callmem:q:{_day(offset)}"))
    return out


def enqueue_backlog(sink, limit: int) -> list[str]:
    """Old transcripts and decks filed before the queue existed, a few at a time (`call-memory --pending --backlog N`): only when
    the queue is empty (so no entry ages past QUEUE_DAYS unread), newest filed first, at most `limit`. Candidates are the stored
    published CONCALL_PRESENTATION cards (the rule memory_recall_export.candidates and the pipeline's queue step use), minus any
    news_id already in the company's dossier `call_memory`, any in a queue key of the last QUEUE_DAYS days and any the backlog
    queued before (BACKLOG_TRIED, kept for good: an invitation or a document with no text is given up without a memory entry,
    and would otherwise come back every QUEUE_DAYS days). Returns the ids."""
    from .memory_recall_export import EVENT, PAGE

    if limit <= 0 or pending(sink):
        return []
    rows, after = [], ["", ""]
    while True:   # export_cards only pages oldest first: every card is paged once, kept as a few bytes, newest first after
        page = sink.query("export_cards", [after[0], after[1], PAGE])
        if not page:
            break
        after = [page[-1]["filed_at"], page[-1]["news_id"]]
        rows += [(r["filed_at"], r["news_id"], r["scrip_code"]) for r in page if r.get("event_category") == EVENT and not r.get("held")]
        if len(page) < PAGE:
            break
    rows.sort(reverse=True)
    tried = set(_load(sink, BACKLOG_TRIED))
    queued, dossiers, picked = known_ids(sink) | tried, {}, []
    for filed_at, news_id, scrip in rows:
        if len(picked) >= limit:
            break
        if news_id in queued:
            continue
        if scrip not in dossiers:
            dossiers[scrip] = {e.get("news_id") for e in ((sink.get_dossier(scrip) or {}).get("call_memory") or [])}
        if news_id in dossiers[scrip]:
            continue
        enqueue(sink, news_id, scrip, filed_at)
        picked.append(news_id)
    if picked:   # one writer: the queue job (its own concurrency group)
        marks = _load(sink, BACKLOG_TRIED)
        marks.update({n: _day() for n in picked})
        sink.kv_set(BACKLOG_TRIED, json.dumps(marks, ensure_ascii=False), _stamp())
    return picked
