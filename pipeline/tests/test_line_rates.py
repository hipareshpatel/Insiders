"""scripts/daily_audit/line_rates.py: per-line accuracy against the card WRONG rate (TODO 17, 25 Oct 2026)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "daily_audit" / "line_rates.py"
_spec = importlib.util.spec_from_file_location("line_rates", _PATH)
lr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lr)


def test_needed_accuracy_and_affordable_lines_are_inverses():
    n = 13
    p = 1 - lr.lines_needed(n)
    assert 0.0039 < p < 0.0040                       # about 99.6% a line for 13 lines
    assert abs(lr.max_lines(p) - n) < 1e-9
    assert abs((1 - p) ** n - 0.95) < 1e-9


def test_card_counts_and_parts():
    card = {"headline": "h", "takeaway": "t", "what_happened": [1, 2], "key_numbers": [1], "why_it_matters": [1],
            "track_next": {"risks": [1, 2], "milestones": []}, "results": {"revenue": {"value": 5}, "pat": {"value": None}}}
    c = lr.card_counts(card)
    assert c["results_rows"] == 1 and c["track_next"] == 2
    assert lr.parts(c) == (8, 4, 4)                  # facts: headline + 2 + 1; interpretation: takeaway + 1 + 2 track items


def test_wrong_points_are_sorted_to_parts():
    assert lr.point_part("headline: 'HDFC Bank PAT ...'") == "headline"
    assert lr.point_part("event_type CORPORATE_ACTION / tone POSITIVE") == "metadata"
    assert lr.point_part("Card as a whole: a duplicate") == "whole_card"
    assert lr.point_part("Total deposits grew 18% YoY") == "prose line"
