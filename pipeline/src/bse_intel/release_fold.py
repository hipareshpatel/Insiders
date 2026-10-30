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
_lock = threading.Lock()


def pending(sink) -> dict[str, list[dict]]:
    try:
        data = json.loads(sink.kv_get(KEY) or "{}")
    except ValueError:
        return {}
    return {k: v for k, v in data.items() if v} if isinstance(data, dict) else {}


def add(sink, results_id: str, entry: dict) -> None:
    with _lock:
        data = pending(sink)
        kept = data.setdefault(results_id, [])
        if all(e["news_id"] != entry["news_id"] for e in kept):
            kept.append(entry)
        sink.kv_set(KEY, json.dumps(data, ensure_ascii=False), now_iso())


def clear(sink, results_ids) -> None:
    with _lock:
        data = pending(sink)
        for i in results_ids:
            data.pop(i, None)
        sink.kv_set(KEY, json.dumps(data, ensure_ascii=False), now_iso())
