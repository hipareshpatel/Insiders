"""UNIT_SLIP_XBRL_GUARD (1 Nov 2026): a figure in the exchange's XBRL file is never overruled by the PDF's tables."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from bse_intel import settings, xbrl_facts
from bse_intel.grounding import unit_slips
from bse_intel.pipeline import fix_unit_slips
from test_cards import HUBTOWN_LAKH, LAKH_STATEMENT, _results_reply

CARD = ["Finance costs of ₹8,483 Cr"]   # the PDF's lakh table reads it as 8,483 lakh = ₹84.83 Cr


def _doc(*crore: float) -> dict:
    return {"units": {"INR": "MONEY", "SH": "SHARES"}, "contexts": {},
            "facts": [["FinanceCosts", "c", "INR", c * xbrl_facts.CRORE, None] for c in crore] + [["Shares", "c", "SH", 5e7, None]]}


def _facts(*crore: float) -> list[float]:
    return xbrl_facts.Facts(_doc(*crore)).money_crore()


def test_money_crore_reads_money_facts_only_and_never_raises():
    assert _facts(408.47, 134.92) == [408.47, 134.92]
    assert xbrl_facts.money_crore(b"not xml at all") == [] and xbrl_facts.money_crore(None) == []


def test_guard_leaves_a_figure_the_xbrl_file_states():
    # Hubtown's shape: the PDF's lakh table reads the card's right figure as a slip; the file states the figure
    assert unit_slips(CARD, HUBTOWN_LAKH) == [("8,483", 8483.0, 0, 84.83, 2)]                    # unchanged without the guard
    assert unit_slips(CARD, HUBTOWN_LAKH, xbrl_crore=_facts(8483.0)) == []                        # the file's figure stands
    assert unit_slips(CARD, HUBTOWN_LAKH, xbrl_crore=_facts(8483.4)) == []                        # within the card figure's own rounding
    out = _results_reply(["Revenue ₹951.96 Cr, PAT ₹493.92 Cr"], [], [])
    assert fix_unit_slips(out, (LAKH_STATEMENT, "", ""), _facts(493.92)) == {}
    assert out.card.what_happened[0].text == "Revenue ₹951.96 Cr, PAT ₹493.92 Cr"


def test_a_real_slip_is_still_corrected_with_the_guard_on():
    # no fact equals the card's figure, so it is a slip
    assert unit_slips(CARD, HUBTOWN_LAKH, xbrl_crore=_facts(84.83, 643.51)) == [("8,483", 8483.0, 0, 84.83, 2)]
    out = _results_reply(["Revenue ₹951.96 Cr, PAT ₹493.92 Cr"], [], [])
    assert fix_unit_slips(out, (LAKH_STATEMENT, "", ""), _facts(49.39)) == {"493.92": "49.39"}


def test_the_switch_is_off_by_default(monkeypatch):
    monkeypatch.delenv("UNIT_SLIP_XBRL_GUARD", raising=False)
    assert settings.unit_slip_xbrl_guard() is False
    monkeypatch.setenv("UNIT_SLIP_XBRL_GUARD", "1")
    assert settings.unit_slip_xbrl_guard() is True


def test_release_check_lists_the_corrections_the_guard_would_leave(monkeypatch):
    spec = importlib.util.spec_from_file_location("release_check_unit", Path(__file__).resolve().parents[1] / "scripts" / "release_check.py")
    rc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rc)
    monkeypatch.setattr(rc.xbrl_facts, "money_crore", lambda *a, **k: _facts(8483.0))
    card = {"xbrl": {"url": "u"}, "grounding": {"unit_fixes": {"8,483": "84.83", "12.5": "1.25"}}}
    rec = rc.check_unit_slip_guard(card, b"x", {"news_id": "n", "scrip_code": "1"})
    assert rc.changed_by_diff(rec["diff"])
    assert any("8,483 Cr kept" in line for line in rec["on_lines"])
    assert "UNIT FIX 12.5 Cr -> 1.25 Cr" in rec["on_lines"]   # not an XBRL fact: still corrected
