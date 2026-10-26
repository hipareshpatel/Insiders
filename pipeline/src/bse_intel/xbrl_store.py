"""F191: every results XBRL file downloaded from the exchange is kept in R2 (raw/xbrl/<sha1(url)[:20]>.xml.gz) for
6 months (R2 lifecycle rule xbrl-180d, deploy-web.yml), so a later run, a reload or a referee reads our copy and asks
NSE only for files we do not hold. Best effort: a failure logs a warning and the download goes on. Only the platform
sink has an R2; local and laptop sinks keep their local cache alone. New files stop going in once the store holds
XBRL_STORE_MAX_MB (owner, 26 Oct 2026: 500); reads always work."""

from __future__ import annotations

import atexit
import gzip
import hashlib
import json
import logging
import os
import threading

from .sinks.platform import PlatformSink

log = logging.getLogger(__name__)

PREFIX = "raw/xbrl/"
TOTAL_KEY = PREFIX + "_total.json"   # {"bytes": n}: the gzipped bytes put so far, kept so a run need not list the folder
SAVE_EVERY = 50                      # puts between writes of the total (it is also written when the process exits)
DEFAULT_MAX_MB = 500   # owner, 26 Oct 2026: 500 MB (was 100), room for the whole results history

_lock = threading.Lock()
_state: dict = {"total": None, "unsaved": 0, "puts": 0, "warned": False, "exit_hook": False, "sink": None}


def key(url: str) -> str:
    return f"{PREFIX}{hashlib.sha1(url.encode()).hexdigest()[:20]}.xml.gz"


def enabled(sink) -> bool:
    return isinstance(sink, PlatformSink)


def _max_bytes() -> int:
    try:
        return int(float(os.environ.get("XBRL_STORE_MAX_MB", DEFAULT_MAX_MB)) * 1_000_000)
    except ValueError:
        return DEFAULT_MAX_MB * 1_000_000


def _remote_total(sink) -> int:
    body = sink.get_object(TOTAL_KEY)
    return int(json.loads(body).get("bytes", 0)) if body else 0


def get(sink, url: str) -> bytes | None:
    """Our copy of the file (decompressed), or None when the sink has none or R2 failed."""
    if not enabled(sink):
        return None
    try:
        body = sink.get_object(key(url))
        return gzip.decompress(body) if body else None
    except Exception as exc:  # noqa: BLE001 - R2 is the second layer: the file is downloaded instead
        log.warning("xbrl store read failed for %s: %s", url, exc)
        return None


def put(sink, url: str, data: bytes) -> None:
    """Keep a downloaded file, unless the store is full (the total is read once a process)."""
    if not enabled(sink) or not data:
        return
    try:
        body = gzip.compress(data, mtime=0)   # mtime 0: the same file is the same bytes
        with _lock:
            if _state["total"] is None:
                _state["total"] = _remote_total(sink)
            if _state["total"] >= _max_bytes():
                if not _state["warned"]:
                    _state["warned"] = True
                    log.warning("xbrl store holds %.1f MB, at or over XBRL_STORE_MAX_MB: no new files are kept",
                                _state["total"] / 1e6)
                return
        sink.put_object(key(url), body, content_type="application/gzip")
        with _lock:
            _state["total"] += len(body)
            _state["unsaved"] += len(body)
            _state["puts"] += 1
            _state["sink"] = sink
            if not _state["exit_hook"]:
                _state["exit_hook"] = True
                atexit.register(flush)
            due = _state["puts"] % SAVE_EVERY == 0
        if due:
            flush()
    except Exception as exc:  # noqa: BLE001 - the durable copy is best effort
        log.warning("xbrl store write failed for %s: %s", url, exc)


def flush() -> None:
    """Write the running total: what other runs added meanwhile is read back first, so only this process's bytes are added."""
    with _lock:
        sink, unsaved = _state["sink"], _state["unsaved"]
        if sink is None or not unsaved:
            return
        _state["unsaved"] = 0
    try:
        total = _remote_total(sink) + unsaved
        sink.put_object(TOTAL_KEY, json.dumps({"bytes": total}).encode())
        with _lock:
            _state["total"] = max(_state["total"] or 0, total)
    except Exception as exc:  # noqa: BLE001
        with _lock:
            _state["unsaved"] += unsaved
        log.warning("xbrl store total not saved: %s", exc)


def reset() -> None:
    """For tests: forget the process's bookkeeping."""
    with _lock:
        _state.update(total=None, unsaved=0, puts=0, warned=False, sink=None)
