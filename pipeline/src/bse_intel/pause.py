"""The AI pipeline's pause for the nightly memory jobs (owner, 2026-10-21: "we may need to have pause of AI pipeline in
night slot to update such info regularly"). A live run reads a company's memory, spends minutes on the AI, then writes
the memory back whole; a memory job writing the same company in between is overwritten. So the nightly job sets
kv `pause:ai` to a time, a live run does not start while it is ahead, and a running one stops between filings (the
work stays queued). The pause ends by itself at that time if the nightly job dies before `resume-ai`."""

from __future__ import annotations

from datetime import datetime, timedelta

from .timeutil import now_ist

PAUSE_KEY = "pause:ai"


def paused_until(sink, now: datetime | None = None) -> datetime | None:
    """When the pause ends, or None when there is none."""
    raw = sink.kv_get(PAUSE_KEY)
    if not raw:
        return None
    try:
        until = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return until if until > (now or now_ist()) else None


def pause(sink, minutes: int) -> datetime:
    now = now_ist()
    until = (now + timedelta(minutes=minutes)).replace(microsecond=0)
    sink.kv_set(PAUSE_KEY, until.isoformat(timespec="seconds"), now.isoformat(timespec="seconds"))
    return until


def resume(sink) -> None:
    now = now_ist().isoformat(timespec="seconds")
    sink.kv_set(PAUSE_KEY, "", now)
