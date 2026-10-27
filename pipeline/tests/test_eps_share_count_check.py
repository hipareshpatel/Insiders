"""EPS share-count check (F211, TODO 79, eps_adjust.share_check, switch EPS_SHARE_COUNT_CHECK)."""

import pytest

from bse_intel import eps_adjust
from bse_intel.dossier import _eps_on_one_basis

BONUS = {"corporate_actions": [{"ex_date": "2024-10-28", "kind": "BONUS", "factor": 2.0, "subject": "BONUS"}]}


def _entries(counts, **extra):
    rows = []
    for p, n in counts.items():   # profit 1000, so n is the implied share count
        rows += [{"metric": "pat", "period": p, "value": 1000.0, "unit": "INR_CR"},
                 {"metric": "eps", "period": p, "value": round(1000 / n, 4), "unit": "INR", "yoy_pct": None}]
    return {"financial_metrics": rows, **extra}, rows


def test_a_2x_bonus_on_record_and_in_the_share_count_is_confirmed_and_adjusted():
    c = eps_adjust.share_check(BONUS, "Q2FY26", "Q2FY25", 1000 / 1353, 1000 / 676, 1000, 1000)
    assert c.status == "confirmed"
    assert c.eps_as_filed == pytest.approx(1000 / 676)
    assert c.eps_today == pytest.approx(1000 / 1352)
    assert c.note == "adjusted for bonus 1:1 on 2024-10-28"


def test_a_5x_jump_with_no_corporate_action_is_marked_not_confirmed_and_not_adjusted():
    c = eps_adjust.share_check({}, "Q4FY26", "Q4FY25", 2.0, 10.0, 100, 100)
    assert c.status == "not_confirmed" and c.eps_today is None and c.eps_as_filed == 10.0
    assert "possible split or bonus, not confirmed" in c.note


def test_a_recorded_action_the_share_count_did_not_follow_is_not_confirmed():
    c = eps_adjust.share_check(BONUS, "Q2FY26", "Q2FY25", 10.0, 7.0, 1000, 1000)   # ratio 0.7, record says x2
    assert c.status == "not_confirmed" and c.eps_today is None


def test_no_change_in_the_share_count_is_none():
    assert eps_adjust.share_check({}, "Q2FY26", "Q2FY25", 5.0, 5.0, 100, 100).status == "none"
    assert eps_adjust.share_check(BONUS, "Q2FY26", "Q2FY25", 5.0, 5.0, 100, 100).status == "none"   # file already restated
    assert eps_adjust.share_check({}, "Q2FY26", "Q2FY25", None, 5.0).status == "none"


def test_memory_entries_carry_both_figures_only_when_the_switch_is_on(monkeypatch):
    dossier, rows = _entries({"Q2FY25": 676, "Q2FY26": 1353}, **BONUS)
    latest = next(r for r in rows if r["metric"] == "eps" and r["period"] == "Q2FY26")
    latest["yoy_pct"] = -50.0
    eps = [r for r in rows if r["metric"] == "eps"]
    monkeypatch.delenv("EPS_SHARE_ADJUST", raising=False)
    monkeypatch.delenv("EPS_SHARE_COUNT_CHECK", raising=False)
    assert _eps_on_one_basis(dossier, eps, rows) is eps   # off: the entries as they are
    monkeypatch.setenv("EPS_SHARE_COUNT_CHECK", "1")
    out = {e["period"]: e for e in _eps_on_one_basis(dossier, eps, rows)}["Q2FY26"]
    assert out["eps_share_status"] == "confirmed" and out["eps_prior_as_filed"] == pytest.approx(1000 / 676, abs=1e-3)
    assert out["eps_prior_today"] == pytest.approx(1000 / 1352, abs=1e-3) and abs(out["yoy_pct"]) < 0.5
    bare, rows = _entries({"Q2FY25": 200, "Q2FY26": 1000})   # 5x, no record
    latest = next(r for r in rows if r["metric"] == "eps" and r["period"] == "Q2FY26")
    latest["yoy_pct"] = -80.0
    out = {e["period"]: e for e in _eps_on_one_basis(bare, [r for r in rows if r["metric"] == "eps"], rows)}["Q2FY26"]
    assert out["eps_share_status"] == "not_confirmed" and out["yoy_pct"] is None and "not confirmed" in out["eps_note"]
