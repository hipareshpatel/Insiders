"""Daily jobs GitHub did not start are started by the pipeline (21 Oct 2026: market-data and nightly never fired)."""

import json
from datetime import datetime, timezone

from bse_intel.watchdog import mark_started, missed


class Kv:
    def __init__(self, **kv):
        self.kv = dict(kv)

    def kv_get(self, key):
        return self.kv.get(key)

    def kv_set(self, key, value, updated_at):
        self.kv[key] = value
        return 1


def at(day, hour, minute):
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


def test_a_daily_job_with_no_run_since_its_slot_is_started_once_after_the_grace():
    sink = Kv(**{"job:market-data": json.dumps({"at": "2026-10-20T06:28:27+05:30", "ok": True})})
    assert missed(sink, at(21, 1, 0)) == []                                # Wednesday 06:30 IST: still within the grace
    assert missed(sink, at(21, 1, 30)) == ["market-data.yml"]              # the nightly may still be running
    assert missed(sink, at(21, 2, 31)) == ["market-data.yml", "nightly.yml"]   # past its 100-minute timeout
    assert missed(sink, at(21, 2, 40)) == ["market-data.yml", "nightly.yml"]   # dispatch failed: asked again
    for workflow in ("market-data.yml", "nightly.yml"):
        assert mark_started(sink, workflow, at(21, 2, 41))
    assert missed(sink, at(21, 2, 45)) == []                               # started once today, not again
    assert not mark_started(sink, "unknown.yml")
    # tomorrow, after both ran on time
    sink.kv["job:market-data"] = json.dumps({"at": "2026-10-22T06:07:00+05:30", "ok": True})
    sink.kv["job:refresh-summaries"] = json.dumps({"at": "2026-10-22T06:20:00+05:30", "ok": True})
    assert missed(sink, at(22, 2, 0)) == []


def test_market_data_is_not_due_on_sunday_or_monday_utc():
    sink = Kv(**{"job:refresh-summaries": json.dumps({"at": "2026-10-25T06:20:00+05:30", "ok": True})})
    assert missed(sink, at(25, 2, 0)) == []        # Sunday: no market data for Saturday's session
    assert missed(sink, at(26, 2, 31)) == ["nightly.yml"]  # Monday UTC (no close since Friday's job ran on Saturday)
