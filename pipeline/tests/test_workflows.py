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
        for step in re.split(r"\n\s+- (?=name:|uses:)", text):
            if step.startswith("name: Commit the export"):
                assert "vars.AUDIT_BRANCH != ''" in step, name
        assert "name: Collect" in text and "audit-export/" in text, name


def test_the_critic_export_runs_only_with_the_critic_on():
    step = next(s for s in re.split(r"\n\s+- (?=name:|uses:)", _text("audit-export.yml"))
                if s.startswith("name: The shadow critic's verdicts"))
    assert "if: vars.CRITIC == '1'" in step
