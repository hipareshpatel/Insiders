from __future__ import annotations

import pytest

from bse_intel.dossier import latest_fundamentals
from bse_intel.models import Card
from bse_intel.quant import FormulaError, check, evaluate

FILING = "Commissioned a 50 MW solar-wind hybrid project with a 25-year PPA at a fixed tariff of Rs. 3.25/kWh."


def estimate(**overrides):
    base = {
        "label": "Annual revenue at full utilisation",
        "formula": "capacity_mw * plf * 8760 * 1000 * tariff_inr / 1e7",
        "inputs": [
            {"name": "capacity_mw", "value": 50, "unit": "MW", "source": "filing"},
            {"name": "plf", "value": 0.22, "source": "assumption", "note": "typical hybrid PLF"},
            {"name": "tariff_inr", "value": "₹3.25", "source": "FILING"},
        ],
        "result": 31.3, "unit": "INR_CR",
    }
    base.update(overrides)
    return Card.model_validate({"impact_level": "HIGH", "headline": "Commissions 50 MW hybrid project",
                                "what_happened": ["50 MW"], "quantified_impact": [base]}).quantified_impact


def test_the_kpi_green_example_checks_out():
    result = check(estimate(), FILING)
    (item,) = result.items
    assert item["check"] == "VERIFIED" and abs(item["computed"] - 31.3) < 0.1
    assert result.checked_inputs == 2 and result.unsourced == [] and result.mismatches == 0


def test_wrong_stated_result_is_a_mismatch():
    result = check(estimate(result=62.6), FILING)
    assert result.items[0]["check"] == "MISMATCH" and result.mismatches == 1
    assert "formula gives" in result.items[0]["check_note"]


def test_input_claimed_from_filing_must_be_in_the_filing():
    inputs = [{"name": "capacity_mw", "value": 75, "source": "FILING"}, {"name": "plf", "value": 0.22},
              {"name": "tariff_inr", "value": 3.25, "source": "FILING"}]
    result = check(estimate(inputs=inputs, result=47.0), FILING)
    assert result.unsourced == ["capacity_mw=75"] and result.items[0]["unsourced_inputs"] == ["capacity_mw"]


def test_missing_result_is_filled_from_the_formula():
    (item,) = check(estimate(result=None), FILING).items
    assert item["check"] == "VERIFIED" and abs(item["result"] - 31.317) < 0.01


@pytest.mark.parametrize("formula", [
    "__import__('os').system('x')", "capacity_mw.real", "open('f')", "[1][0]", "capacity_mw ** 50",
    "lambda: 1", "unknown_input * 2", "1 / 0",
])
def test_formula_evaluator_rejects_anything_but_arithmetic(formula):
    with pytest.raises(FormulaError):
        evaluate(formula, {"capacity_mw": 50})


def test_formula_evaluator_supports_plain_arithmetic():
    assert evaluate("max(a, b) - abs(-c) + round(d / 3, 2) * 2 ^ 2", {"a": 1, "b": 4, "c": 1, "d": 10}) == pytest.approx(16.32)
    (item,) = check(estimate(formula="capacity_mw * (2"), FILING).items
    assert item["check"] == "UNCHECKED"


def test_latest_fundamentals_prefers_latest_quarter_and_balance_sheet():
    dossier = {
        "financial_metrics": [
            {"metric": "revenue", "period": "FY26", "value": 1500, "as_of": "2026-05-01"},
            {"metric": "revenue", "period": "Q1FY27", "value": 412, "as_of": "2026-07-21"},
            {"metric": "revenue", "period": "Q2FY27", "value": 456, "as_of": "2026-10-12"},
            {"metric": "gross_debt", "period": "H1FY26", "value": 420, "as_of": "2026-10-12"},
        ],
        "balance_sheet": [{"period": "Sep-2026", "gross_debt_cr": 640, "net_worth_cr": 1210, "as_of": "2026-10-12"}],
    }
    assert latest_fundamentals(dossier) == {
        "revenue": {"period": "Q2FY27", "value": 456},
        "debt": {"period": "Sep-2026", "value": 640},
        "net_worth": {"period": "Sep-2026", "value": 1210},
    }
    assert latest_fundamentals({"financial_metrics": [], "balance_sheet": []}) == {}
