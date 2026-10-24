"""scripts/daily_audit/rates.py: the audit's rates with 95% intervals, pooled over days (code survey, 24 Oct 2026)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "daily_audit" / "rates.py"
_spec = importlib.util.spec_from_file_location("audit_rates", _PATH)
rates = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rates)


def test_one_days_wrong_share_has_a_wide_interval():
    low, high = rates.wilson(15, 65)            # 24 Oct: 15 WRONG of 65
    assert 0.14 < low < 0.16 and 0.34 < high < 0.36
    low, high = rates.wilson(9, 60)             # 23 Oct's 15%: the two days' intervals overlap
    assert high > 0.15 * 1.5 and rates.wilson(0, 0) == (0.0, 0.0)


def test_days_are_pooled_and_short_and_long_kept_apart(tmp_path):
    rows = lambda verdicts, variant: [{"verdict": v, "prompt_variant": variant} for v in verdicts]  # noqa: E731
    (tmp_path / "2026-10-23-audit.json").write_text(json.dumps(rows(["RIGHT", "WRONG"], "short")))
    (tmp_path / "2026-10-24-audit.json").write_text(json.dumps(
        rows(["MINOR", "RIGHT"], "long") + [{"verdict": "WRONG", "prompt_variant": "long", "pruned_points_true": 3,
                                              "pruned_points_false": 1}]))
    days = rates.load(tmp_path)
    assert list(days) == ["2026-10-23", "2026-10-24"]
    pooled = rates.summary([r for d in days.values() for r in d])
    assert pooled["n"] == 5 and pooled["counts"]["WRONG"] == 2 and pooled["pruned"] == (3, 1)
    assert pooled["variants"]["short"]["WRONG"] == 1 and sum(pooled["variants"]["long"].values()) == 3
    text = rates.report(days, window=2)
    assert "(pooled)" in text and "| all | 5 |" in text
