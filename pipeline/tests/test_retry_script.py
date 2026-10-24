"""scripts/retry.sh: a fast failure is tried once more, a refusal (exit 75, cli.REFUSED) never, and a refusal skips the
job's later NSE steps instead of asking NSE again (survey, 24 Oct 2026)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "retry.sh"


def _run(tmp_path: Path, *command: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "RUNNER_TEMP": str(tmp_path), "RETRY_WAIT_S": "0"}
    return subprocess.run(["bash", str(SCRIPT), *command], capture_output=True, text=True, env=env, timeout=30)


def _counting(tmp_path: Path, name: str, code: int) -> list[str]:
    """A command that counts its runs in a file and exits with ``code``; its last word is the CLI command ``name``."""
    counter = tmp_path / f"{name}.count"
    return ["bash", "-c", f'echo x >> "{counter}"; exit {code}', "sh", name]


def _runs(tmp_path: Path, name: str) -> int:
    counter = tmp_path / f"{name}.count"
    return len(counter.read_text().split()) if counter.exists() else 0


def test_a_fast_failure_is_tried_once_more(tmp_path):
    assert _run(tmp_path, *_counting(tmp_path, "refresh-summaries", 1)).returncode == 1
    assert _runs(tmp_path, "refresh-summaries") == 2
    assert not (tmp_path / "source-refused").exists()


def test_a_refusal_is_not_retried_and_skips_the_jobs_later_nse_steps(tmp_path):
    assert _run(tmp_path, *_counting(tmp_path, "governance-sync", 75)).returncode == 75
    assert _runs(tmp_path, "governance-sync") == 1
    assert (tmp_path / "source-refused").exists()
    skipped = _run(tmp_path, *_counting(tmp_path, "pledge-sync", 0))
    assert skipped.returncode == 75 and _runs(tmp_path, "pledge-sync") == 0 and "skipped" in skipped.stdout
    # a step that does not ask NSE still runs
    assert _run(tmp_path, *_counting(tmp_path, "refresh-summaries", 0)).returncode == 0
    assert _runs(tmp_path, "refresh-summaries") == 1


def test_exit_2_is_a_usage_or_ai_error_retried_like_any_fast_failure(tmp_path):
    """argparse and an AI error exit 2: an AI step (annual-xbrl-catchup) that met a passing outage was retried, and must
    not be taken for a refusal that skips the job's NSE steps."""
    assert _run(tmp_path, *_counting(tmp_path, "annual-xbrl-catchup", 2)).returncode == 2
    assert _runs(tmp_path, "annual-xbrl-catchup") == 2
    assert not (tmp_path / "source-refused").exists()


def test_off_a_runner_a_refusal_is_not_remembered(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "RUNNER_TEMP"} | {"RETRY_WAIT_S": "0"}
    done = subprocess.run(["bash", str(SCRIPT), *_counting(tmp_path, "pledge-sync", 75)], capture_output=True, text=True,
                          env=env, timeout=30)
    assert done.returncode == 75 and not Path("/tmp/source-refused").exists()
