"""The AI pipeline's nightly pause (pause.py; owner, 2026-10-21: pause the AI pipeline in a night slot so the memory
jobs can write): no live run starts while it holds, a running one stops between filings, and it ends by itself."""

import json
from threading import Lock
from types import SimpleNamespace

from bse_intel import pause
from bse_intel.pipeline import Pipeline
from bse_intel.sinks.local import LocalSink


def test_pause_holds_until_its_time_and_resume_ends_it(settings):
    sink = LocalSink(settings)
    assert pause.paused_until(sink) is None
    until = pause.pause(sink, 90)
    assert pause.paused_until(sink) == until
    assert pause.paused_until(sink, now=until) is None        # ends by itself if the nightly job dies
    pause.resume(sink)
    assert pause.paused_until(sink) is None


def test_a_live_run_does_not_start_while_paused(settings, capsys):
    from bse_intel.cli import cmd_run

    sink = LocalSink(settings)
    pause.pause(sink, 30)
    assert cmd_run(SimpleNamespace(mode="all", time_budget=60, max_backfill_days=1), settings, sink) == 0
    assert "paused" in json.loads(capsys.readouterr().out)["skipped"]


def test_a_running_pipeline_stops_between_filings(settings):
    sink = LocalSink(settings)
    run = SimpleNamespace(_lock=Lock(), _paused=False, _pause_checked=float("-inf"), sink=sink,
                          stats=SimpleNamespace(stopped_reason=None))
    assert Pipeline._pause_now(run) is False
    pause.pause(sink, 30)
    assert Pipeline._pause_now(run) is False                  # looked up at most once a minute
    run._pause_checked = float("-inf")
    assert Pipeline._pause_now(run) is True and "nightly memory jobs" in run.stats.stopped_reason
