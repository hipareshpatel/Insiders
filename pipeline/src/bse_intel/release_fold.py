"""Press releases waiting to join their quarter's results card (TODO 135, RESULTS_PRESS_RELEASE).

One kv key, ``relfold:pending``: {results_news_id: [{"news_id", "date", "text"}]}. The pipeline adds an entry when it folds a
release into a quarter's card; ``event_catchup.release_catch_up`` reads it, re-makes the card with the text, and clears the
entry only once that card is re-made, so a run that ends early loses nothing and the next run applies it. The kv table has no
delete, so a cleared entry is removed from the one value."""
from __future__ import annotations

import json
import threading

from .timeutil import now_iso

KEY = "relfold:pending"
DONE_KEY = "relfold:done"   # the releases already folded in or given up on: a requeued release is not added again
MAX_TRIES = 3              # re-runs of one card that did not end ANALYZED before its releases are given up (review, 30 Oct 2026)
MAX_CHARS = 12_000         # all of a card's release text together
MAX_DONE = 2_000
_lock = threading.Lock()


def pending(sink) -> dict[str, list[dict]]:
    try:
        data = json.loads(sink.kv_get(KEY) or "{}")
    except ValueError:
        return {}
    return {k: v for k, v in data.items() if v} if isinstance(data, dict) else {}


def _done(sink) -> list[str]:
    try:
        data = json.loads(sink.kv_get(DONE_KEY) or "[]")
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def add(sink, results_id: str, entry: dict) -> None:
    with _lock:
        if entry["news_id"] in _done(sink):
            return
        data = pending(sink)
        kept = data.setdefault(results_id, [])
        if all(e["news_id"] != entry["news_id"] for e in kept):
            kept.append(entry)
        sink.kv_set(KEY, json.dumps(data, ensure_ascii=False), now_iso())


def clear(sink, results_ids) -> None:
    """The cards' releases settled: off the pending list and onto the done list."""
    with _lock:
        data = pending(sink)
        settled = [e["news_id"] for i in results_ids for e in data.pop(i, [])]
        sink.kv_set(KEY, json.dumps(data, ensure_ascii=False), now_iso())
        if settled:
            done = [n for n in _done(sink) if n not in settled] + settled
            sink.kv_set(DONE_KEY, json.dumps(done[-MAX_DONE:]), now_iso())


def tried(sink, results_ids) -> list[str]:
    """One more re-run that did not end ANALYZED, for each card; the cards at MAX_TRIES are returned (to be cleared)."""
    with _lock:
        data = pending(sink)
        out = []
        for i in results_ids:
            for e in data.get(i, []):
                e["tries"] = int(e.get("tries") or 0) + 1
            if any(int(e.get("tries") or 0) >= MAX_TRIES for e in data.get(i, [])):
                out.append(i)
        sink.kv_set(KEY, json.dumps(data, ensure_ascii=False), now_iso())
    return out
