"""Daily jobs GitHub did not start (21 Oct 2026: market-data's 06:05 and nightly's 06:10 IST slots never fired; GitHub
drops scheduled runs when it is busy, as it did to seed-calls on 20 Oct). The pipeline runs every 15 minutes; after
each run it asks which daily job has no run recorded since its slot (kv job:<command>, written by every scheduled
command) once the slot is GRACE behind, and its workflow starts that job, at most once a day per job."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

GRACE = timedelta(minutes=45)

# workflow file -> (the command whose job record shows it ran, its slot in UTC, the UTC weekdays it runs; Monday = 0)
DAILY = {
    "market-data.yml": ("market-data", (0, 35), (1, 2, 3, 4, 5)),      # 06:05 IST Tuesday to Saturday
    "nightly.yml": ("refresh-summaries", (0, 40), (0, 1, 2, 3, 4, 5, 6)),   # 06:10 IST; summaries are its last step
}


def missed(sink, now: datetime | None = None) -> list[str]:
    """Workflow files to start now, each marked so a later run the same day does not start it again."""
    now = now or datetime.now(timezone.utc)
    due = []
    for workflow, (command, (hour, minute), weekdays) in DAILY.items():
        slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now.weekday() not in weekdays or now < slot + GRACE:
            continue
        mark = f"watchdog:{workflow}"
        if sink.kv_get(mark) == slot.date().isoformat():
            continue   # already started today; its job record lands when it ends
        last = _ran_at(sink.kv_get(f"job:{command}"))
        if last is not None and last >= slot:
            continue
        sink.kv_set(mark, slot.date().isoformat(), now.isoformat(timespec="seconds"))
        due.append(workflow)
    return due


def _ran_at(raw: str | None) -> datetime | None:
    try:
        at = datetime.fromisoformat(json.loads(raw)["at"]) if raw else None
    except (ValueError, KeyError, TypeError):
        return None
    return at.astimezone(timezone.utc) if at and at.tzinfo else None
