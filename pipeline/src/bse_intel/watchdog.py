"""Daily jobs GitHub did not start (21 Oct 2026: market-data's 06:05 and nightly's 06:10 IST slots never fired; GitHub
drops scheduled runs when it is busy, as it did to seed-calls on 20 Oct). The pipeline runs every 15 minutes; after
each run it asks which daily job has no run recorded since its slot (kv job:<command>, written by every scheduled
command) once the slot is GRACE behind, and its workflow starts that job, at most once a day per job. A job is marked
started only after its dispatch went through (`mark_started`): marked first, a failed dispatch was not tried again
that day (survey, 24 Oct 2026)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

GRACE = timedelta(minutes=45)

# workflow file -> (the command whose job record shows it ran, its slot in UTC, the UTC weekdays it runs; Monday = 0,
# and how long after the slot it is taken as missed). The nightly's record is its last step, so its grace is longer than
# the job may run (timeout 100 min): at 45 minutes a nightly still going was started again, pausing the AI pipeline for
# another 75 minutes and running every step twice (survey, 24 Oct 2026).
DAILY = {
    "market-data.yml": ("market-data", (0, 35), (1, 2, 3, 4, 5), GRACE),      # 06:05 IST Tuesday to Saturday
    "nightly.yml": ("refresh-summaries", (0, 40), (0, 1, 2, 3, 4, 5, 6), timedelta(minutes=110)),   # 06:10 IST
}
# A job that records its start (`job-started <workflow>`, the nightly's first step) is not missed while it may still be
# running: GitHub often starts a scheduled run 15-60 minutes late, past a grace counted from the slot (survey review)
RUN_LIMIT = timedelta(minutes=110)
STARTED_KEY = "started:{}"


def missed(sink, now: datetime | None = None) -> list[str]:
    """Workflow files to start now: not run since today's slot, and not started yet today (`mark_started`)."""
    now = now or datetime.now(timezone.utc)
    due = []
    for workflow, (command, (hour, minute), weekdays, grace) in DAILY.items():
        slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now.weekday() not in weekdays or now < slot + grace:
            continue
        mark = f"watchdog:{workflow}"
        if sink.kv_get(mark) == slot.date().isoformat():
            continue   # already started today; its job record lands when it ends
        last = _ran_at(sink.kv_get(f"job:{command}"))
        if last is not None and last >= slot:
            continue
        started = _ran_at(sink.kv_get(STARTED_KEY.format(workflow)))
        if started is not None and started >= slot and now < started + RUN_LIMIT:
            continue   # started today and may still be running
        due.append(workflow)
    return due


def mark_started(sink, workflow: str, now: datetime | None = None) -> bool:
    """Record that today's missed run of ``workflow`` was dispatched, so a later pipeline run does not start it again."""
    if workflow not in DAILY:
        return False
    now = now or datetime.now(timezone.utc)
    hour, minute = DAILY[workflow][1]
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    sink.kv_set(f"watchdog:{workflow}", slot.date().isoformat(), now.isoformat(timespec="seconds"))
    return True


def _ran_at(raw: str | None) -> datetime | None:
    try:
        at = datetime.fromisoformat(json.loads(raw)["at"]) if raw else None
    except (ValueError, KeyError, TypeError):
        return None
    return at.astimezone(timezone.utc) if at and at.tzinfo else None


def record_start(sink, workflow: str, now: datetime | None = None) -> None:
    """The workflow's run has begun (its first step), so `missed` leaves it alone while it may still be running."""
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    sink.kv_set(STARTED_KEY.format(workflow), json.dumps({"at": stamp}), stamp)
