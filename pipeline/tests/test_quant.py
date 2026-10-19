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


def test_formula_inputs_match_whatever_their_case():
    """SML Q3FY25: input "q3fy25_ebitda", formula "Q3FY25_EBITDA * 4" was left "Not checked"."""
    assert evaluate("Q3FY25_EBITDA * 4", {"q3fy25_ebitda": 0.75}) == pytest.approx(3.0)
    assert evaluate("Capacity_MW * 2", {"capacity_mw": 50, "Capacity_MW": 60}) == pytest.approx(120)  # exact name wins


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


def test_results_snapshot_for_the_results_table():
    from bse_intel.dossier import results_snapshot

    dossier = {"financial_metrics": [
        {"metric": "revenue", "period": "Q2FY27", "value": 455.6, "yoy_pct": 19.6, "source_news_id": "n2", "as_of": "b"},
        {"metric": "ebitda_margin", "period": "Q2FY27", "value": 14.9, "unit": "PCT", "source_news_id": "n2", "as_of": "b"},
        {"metric": "ebitda_margin", "period": "Q2FY26", "value": 18.6, "unit": "PCT", "source_news_id": "n2", "as_of": "b"},
        {"metric": "pat", "period": "Q2FY27", "value": 29.4, "source_news_id": "n2", "as_of": "b"},
        {"metric": "pat", "period": "Q2FY26", "value": 36.8, "source_news_id": "n1", "as_of": "a"},
        {"metric": "revenue", "period": "H1FY27", "value": 867.9, "source_news_id": "n2", "as_of": "b"},
        {"metric": "revenue", "period": "Q1FY27", "value": 412.3, "source_news_id": "n1", "as_of": "a"},
        {"metric": "ebitda", "period": "Q1FY27", "value": 73.39, "source_news_id": "n1", "as_of": "a"},
        {"metric": "ebitda", "period": "Q2FY27", "value": 67.88, "source_news_id": "n2", "as_of": "b"},
    ]}
    assert results_snapshot(dossier, "n2") == {
        "period": "Q2FY27", "prev_year_period": "Q2FY26", "prev_quarter_period": "Q1FY27",
        # no year-ago revenue in memory, so the filing's own YoY is used
        "revenue": {"value": 455.6, "prev_quarter": 412.3, "qoq_pct": 10.5, "yoy_pct": 19.6},
        "ebitda": {"value": 67.88, "prev_quarter": 73.39, "qoq_pct": -7.5},
        # Q1 margin was not stated: derived from EBITDA / revenue
        "ebitda_margin": {"value": 14.9, "prev_year": 18.6, "prev_quarter": 17.8, "yoy_bps": -370, "qoq_bps": -290},
        "pat": {"value": 29.4, "prev_year": 36.8, "yoy_pct": -20.1},
    }
    assert results_snapshot(dossier, "other") is None


def test_card_tone_and_takeaway_defaults():
    card = Card.model_validate({"impact_level": "HIGH", "tone": "bullish", "headline": "Wins ₹450 Cr order",
                                "what_happened": ["Order"], "why_it_matters": ["Equal to 30% of FY26 revenue"]})
    assert card.tone == "POSITIVE" and card.takeaway == "Equal to 30% of FY26 revenue"
    assert Card.model_validate({"impact_level": "LOW", "headline": "Routine update here", "what_happened": ["x"],
                                "tone": "whatever"}).tone == "NEUTRAL"


def test_an_estimate_may_build_on_an_earlier_verified_one():
    """Shivam's "exposure as a share of the FY25 loss" took the total exposure (₹50.1 Cr tax + ₹50.1 Cr penalty)
    as its input and that input was reported as unsourced (loop round 3a, 2026-10-17)."""
    filing = "Show cause notice for tax of Rs.50,10,05,632 and an equal penalty. Net loss for FY25 Rs. 48.04 crore."
    card = Card.model_validate({"impact_level": "HIGH", "headline": "GST demand", "what_happened": ["demand"],
                                "quantified_impact": [
        {"label": "Total exposure", "formula": "tax_cr + penalty_cr", "result": 100.2, "unit": "INR_CR", "inputs": [
            {"name": "tax_cr", "value": 50.1, "source": "FILING"}, {"name": "penalty_cr", "value": 50.1, "source": "FILING"}]},
        {"label": "Exposure against the loss", "formula": "total_cr / loss_cr", "result": 2.09, "unit": "X", "inputs": [
            {"name": "total_cr", "value": 100.2, "source": "FILING"}, {"name": "loss_cr", "value": 48.04, "source": "FILING"}]},
        {"label": "An invented input", "formula": "x * 2", "result": 251.0, "unit": "INR_CR", "inputs": [
            {"name": "x", "value": 125.5, "source": "FILING"}]}]})
    result = check(card.quantified_impact, filing)
    assert [i["check"] for i in result.items] == ["VERIFIED", "VERIFIED", "VERIFIED"]
    assert result.unsourced == ["x=125.5"]


def test_a_formula_over_mixed_units_is_checked_in_the_result_unit():
    """Texmaco (round 5 arm B): USD 135M at ₹85 stated as ₹11,475 Cr, VERIFIED because 135 x 85 = 11,475. In ₹ crore it
    is ₹1,147.5 Cr."""
    from bse_intel.models import QuantifiedImpact
    from bse_intel.quant import check

    def est(result):
        return QuantifiedImpact.model_validate({
            "label": "Order in rupees", "formula": "order_usd * fx", "result": result, "unit": "INR_CR",
            "inputs": [{"name": "order_usd", "value": 135, "unit": "USD_M", "source": "FILING"},
                       {"name": "fx", "value": 85, "unit": "INR", "source": "ASSUMPTION"}]})

    text = "Letter of award for locomotives worth USD 135 million."
    wrong, right = check([est(11475)], text).items[0], check([est(1147.5)], text).items[0]
    assert wrong["check"] == "MISMATCH" and right["check"] == "VERIFIED" and right["computed"] == 1147.5
    # same units on both sides: nothing changes (₹ crore over ₹ crore, as a share)
    share = QuantifiedImpact.model_validate({
        "label": "Share", "formula": "a / b * 100", "result": 25, "unit": "PCT",
        "inputs": [{"name": "a", "value": 250, "unit": "INR_CR", "source": "FILING"},
                   {"name": "b", "value": 1000, "unit": "INR_CR", "source": "FILING"}]})
    assert check([share], "orders of Rs 250 crore against revenue of Rs 1,000 crore").items[0]["check"] == "VERIFIED"
    # a formula that converts itself is checked as written (the plain product already in ₹ crore)
    own = QuantifiedImpact.model_validate({
        "label": "Order in rupees", "formula": "order_usd * 1000000 * fx / 10000000", "result": 1147.5, "unit": "INR_CR",
        "inputs": [{"name": "order_usd", "value": 135, "unit": "USD_M", "source": "FILING"},
                   {"name": "fx", "value": 85, "unit": "INR", "source": "ASSUMPTION"}]})
    assert check([own], text).items[0]["check"] == "VERIFIED"
