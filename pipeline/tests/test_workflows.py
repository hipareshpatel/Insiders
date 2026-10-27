"""Workflow rules that broke quietly before (27 Oct 2026): exports committed to a parked branch nobody read, and the
shadow critic's export running every morning while the critic is off (D41)."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_no_workflow_names_the_parked_branch():
    for wf in WORKFLOWS.glob("*.yml"):
        assert "gracious-goodall" not in wf.read_text(encoding="utf-8"), wf.name


def test_an_export_is_committed_only_to_a_branch_the_owner_named_and_is_always_kept_as_an_artifact():
    for name in ("audit-export.yml", "maintenance.yml"):
        text = _text(name)
        steps = re.split(r"\n\s+- (?=name:|uses:)", text)
        commits = [s for s in steps if s.startswith("name: Commit the export")]
        assert commits, name
        for step in commits:
            assert re.search(r"^\s*if: .*vars\.AUDIT_BRANCH != ''", step, re.M), name   # the step's own condition
        uploads = [s for s in steps if s.startswith("uses: actions/upload-artifact") and "audit-export/" in s]
        assert uploads and all("AUDIT_BRANCH" not in s for s in uploads), name   # kept whatever the branch setting


def test_the_critic_export_runs_only_with_the_critic_on():
    step = next(s for s in re.split(r"\n\s+- (?=name:|uses:)", _text("audit-export.yml"))
                if s.startswith("name: The shadow critic's verdicts"))
    assert "if: vars.CRITIC == '1'" in step


def test_every_job_that_marks_the_file_cap_also_reads_it():
    """CLAUDE.md: a new or changed NSE/BSE download path is first tested on 100 files (file_cap). The seed, gap-fill,
    text-backfill and PDF-download jobs left the marker but never read the cap (27 Oct 2026)."""
    text = _text("maintenance.yml")
    jobs = re.split(r"\n  (?=[a-z][a-z0-9-]*:\n)", text.split("\njobs:\n", 1)[1])
    marked = [j for j in jobs if "FILE_CAP_MARKER_DIR:" in j]
    assert len(marked) >= 6
    for job in marked:
        assert "FILE_CAP: ${{ inputs.file_cap || '0' }}" in job, job.split(":", 1)[0]
