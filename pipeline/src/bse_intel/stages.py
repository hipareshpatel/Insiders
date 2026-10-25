"""Where one filing's time went: a per-thread stage timer (filings run in parallel threads, _run_parallel).

`start()` opens a filing's timer on the calling thread, `stage(name)` adds the seconds spent inside it, `finish()`
returns the totals. Outside a filing `stage` does nothing, so callers need no checks. Times are exclusive: a stage
opened inside another (OCR while the text is read for pass 1) pauses the outer one, so the stages add up to the
filing's total. The same stage inside itself (a retry wrapper, a nested call) is counted once."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager

_local = threading.local()


def start() -> dict[str, float]:
    _local.times, _local.stack = {}, []
    return _local.times


def finish() -> dict[str, float]:
    times = getattr(_local, "times", None) or {}
    _local.times, _local.stack = None, []
    return times


@contextmanager
def stage(name: str):
    times = getattr(_local, "times", None)
    if times is None or any(open_name == name for open_name, _ in _local.stack):
        yield
        return
    stack = _local.stack
    now = time.monotonic()
    if stack:   # pause the stage this one runs inside
        outer = stack[-1]
        times[outer[0]] = times.get(outer[0], 0.0) + now - outer[1]
    stack.append([name, now])
    try:
        yield
    finally:
        now = time.monotonic()
        _, began = stack.pop()
        times[name] = times.get(name, 0.0) + now - began
        if stack:
            stack[-1][1] = now


def add(name: str, seconds: float) -> None:
    """Seconds measured by the caller (a wait inside a call), taken out of the stage they were spent in."""
    times = getattr(_local, "times", None)
    if times is None or seconds <= 0:
        return
    times[name] = times.get(name, 0.0) + seconds
    if _local.stack:
        outer = _local.stack[-1][0]
        times[outer] = times.get(outer, 0.0) - seconds


def count(name: str) -> None:
    """One more of something (an OCR'd page); kept beside the seconds under the same dict."""
    times = getattr(_local, "times", None)
    if times is not None:
        times[name] = times.get(name, 0.0) + 1
