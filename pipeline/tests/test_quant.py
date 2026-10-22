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
    snap = results_snapshot(dossier, "n2")
    assert snap.pop("lens") == "company"
    assert [line["key"] for line in snap.pop("lines")] == ["revenue", "ebitda", "ebitda_margin", "pat"]
    assert snap == {
        "period": "Q2FY27", "prev_year_period": "Q2FY26", "prev_quarter_period": "Q1FY27",
        # no year-ago revenue in memory, so the filing's own YoY is used
        "revenue": {"value": 455.6, "prev_quarter": 412.3, "qoq_pct": 10.5, "yoy_pct": 19.6},
        "ebitda": {"value": 67.88, "prev_quarter": 73.39, "qoq_pct": -7.5},
        # Q1 margin was not stated: derived from EBITDA / revenue
        "ebitda_margin": {"value": 14.9, "prev_year": 18.6, "prev_quarter": 17.8, "yoy_bps": -370, "qoq_bps": -290},
        "pat": {"value": 29.4, "prev_year": 36.8, "yoy_pct": -20.1},
    }
    assert results_snapshot(dossier, "other") is None


def test_a_banks_results_table_has_its_own_lines():
    """A bank has no revenue or EBITDA, so its card had no table (owner, 2026-10-19: Punjab & Sind Bank). Net
    interest income is interest earned less interest expended; NPA ratios move in basis points."""
    from bse_intel.dossier import results_snapshot

    def m(metric, period, value, news="n2", unit="INR_CR"):
        return {"metric": metric, "period": period, "value": value, "unit": unit, "source_news_id": news, "as_of": "b"}

    dossier = {"financial_metrics": [
        m("interest_earned", "Q1FY27", 3213.37), m("interest_expended", "Q1FY27", 2100.0),
        m("interest_earned", "Q1FY26", 3000.0, "n1"), m("interest_expended", "Q1FY26", 2000.0, "n1"),
        m("pre_provision_operating_profit", "Q1FY27", 545.48), m("provisions", "Q1FY27", 93.99),
        m("pat", "Q1FY27", 331.51), m("nnpa_pct", "Q1FY27", 0.65, unit="PCT"), m("nnpa_pct", "Q1FY26", 0.91, "n1", "PCT"),
    ]}
    snap = results_snapshot(dossier, "n2")
    assert snap["nii"] == {"value": 1113.37, "prev_year": 1000.0, "yoy_pct": 11.3}
    assert snap["nnpa_pct"] == {"value": 0.65, "prev_year": 0.91, "yoy_bps": -26}
    assert snap["ppop"]["value"] == 545.48 and snap["provisions"]["value"] == 93.99 and "revenue" not in snap
    assert snap["lens"] == "bank"
    assert [line["key"] for line in snap["lines"]] == ["interest_earned", "nii", "ppop", "provisions", "pat", "nnpa_pct"]


def test_the_results_table_takes_the_sectors_own_kpis():
    """Not only banks: a cement maker's table carries its EBITDA a tonne beside the statement lines, with the year-ago
    and previous quarter, from the sector's footer list (sectors.toml)."""
    from bse_intel.dossier import results_snapshot

    def m(metric, period, value, news="n2", unit="INR_CR"):
        return {"metric": metric, "period": period, "value": value, "unit": unit, "source_news_id": news, "as_of": "b"}

    dossier = {"financial_metrics": [
        m("revenue", "Q2FY27", 455.6), m("pat", "Q2FY27", 29.4), m("revenue", "Q2FY26", 380.9, "n1"),
        m("ebitda_per_tonne", "Q2FY27", 812.0, unit="INR"), m("ebitda_per_ton", "Q2FY26", 1010.0, "n1", "INR"),
    ]}
    footer = ({"metric": "ebitda_per_tonne", "label": "EBITDA/t", "format": "inr", "aliases": ["ebitda_per_ton"]},
              {"metric": "ebitda_margin", "label": "EBITDA margin", "format": "pct"})
    snap = results_snapshot(dossier, "n2", footer)
    assert snap["lines"][-1] == {"key": "kpi:ebitda_per_tonne", "label": "EBITDA/t", "unit": "inr"}
    assert snap["kpi:ebitda_per_tonne"] == {"value": 812.0, "prev_year": 1010.0, "yoy_pct": -19.6}
    assert not any(line["key"] == "kpi:ebitda_margin" for line in snap["lines"])   # the statement already has it


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
    # the rate's unit written as a rate (Sagility, live audit 22 Oct 2026: US$ 20 M x 89 stated as ₹1,780 Cr)
    for rate_unit in ("INR/USD", "INR per USD", "INR_PER_USD"):
        rated = QuantifiedImpact.model_validate({
            "label": "Upfront in rupees", "formula": "upfront_usd_m * fx_inr_per_usd", "result": 1780.0, "unit": "INR_CR",
            "inputs": [{"name": "upfront_usd_m", "value": 20.0, "unit": "USD_M", "source": "FILING"},
                       {"name": "fx_inr_per_usd", "value": 89.0, "unit": rate_unit, "source": "ASSUMPTION"}]})
        item = check([rated], "an upfront payment of USD 20.0 M").items[0]
        assert item["check"] == "MISMATCH" and item["computed"] == 178.0, rate_unit
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
    # shapes the unit check leaves to plain arithmetic (each held a true card when it did not, 2026-10-19)
    for formula, inputs, result, unit in (
            ("6000", [{"name": "target", "value": 6000, "unit": "INR_CR", "source": "FILING"}], 6000, "INR_CR"),
            ("a_lakh / 100 / nw * 100", [{"name": "a_lakh", "value": 27529, "unit": "INR_LAKH", "source": "FILING"},
                                         {"name": "nw", "value": 18083, "unit": "INR_CR", "source": "MEMORY"}], 1.52, "PCT")):
        est = QuantifiedImpact.model_validate({"label": "x", "formula": formula, "inputs": inputs, "result": result, "unit": unit})
        assert check([est], "27,529 lakh; net worth 18,083 crore; target 6,000 crore").items[0]["check"] == "VERIFIED"


def test_results_table_edge_cases_insurer_bank_footer_and_missing_history():
    from bse_intel.dossier import results_snapshot

    def m(metric, period, value, news="n2", unit="INR_CR"):
        return {"metric": metric, "period": period, "value": value, "unit": unit, "source_news_id": news, "as_of": "b"}

    insurer = results_snapshot({"financial_metrics": [
        m("gross_premium", "Q2FY27", 6100.0), m("revenue", "Q2FY27", 5200.0), m("incurred_claims", "Q2FY27", 3900.0),
        m("combined_ratio", "Q2FY27", 102.1, unit="PCT"), m("combined_ratio", "Q2FY26", 103.4, "n1", "PCT"), m("pat", "Q2FY27", 690.0),
    ]}, "n2")
    assert insurer["lens"] == "insurer"
    assert [line["label"] for line in insurer["lines"]] == ["Gross premium", "Net premium", "Claims", "Combined ratio", "PAT"]
    assert insurer["combined_ratio"]["yoy_bps"] == -130

    # a bank's footer GNPA is the statement's own gross NPA line: not a second row
    bank_footer = ({"metric": "gnpa", "label": "GNPA", "format": "pct", "aliases": ["gnpa_pct", "gross_npa"]},
                   {"metric": "casa_ratio", "label": "CASA", "format": "pct", "aliases": []})
    bank = results_snapshot({"financial_metrics": [
        m("interest_earned", "Q1FY27", 3213.37), m("pat", "Q1FY27", 331.51), m("gnpa_pct", "Q1FY27", 2.21, unit="PCT"),
        m("casa_ratio", "Q1FY27", 31.0, unit="PCT"),
    ]}, "n2", bank_footer)
    assert [line["key"] for line in bank["lines"]] == ["interest_earned", "pat", "gnpa_pct", "kpi:casa_ratio"]
    assert bank["kpi:casa_ratio"] == {"value": 31.0}          # no history: the value alone, no change
    assert "nii" not in bank                                   # no interest expended: no NII is made up

    # one statement line alone is no table
    assert results_snapshot({"financial_metrics": [m("pat", "Q1FY27", 10.0)]}, "n2") is not None
    assert results_snapshot({"financial_metrics": [m("revenue", "FY26", 10.0)]}, "n2") is None   # no quarter


def test_asset_quality_words():
    from types import SimpleNamespace

    from bse_intel.results_card import asset_quality

    v = lambda x: SimpleNamespace(value=x)
    assert asset_quality({"nnpa_pct": v(0.65), "gnpa_pct": v(2.21)}) == "net NPA 0.65%, gross 2.21%"
    assert asset_quality({"gnpa_pct": v(2.21)}) == "gross NPA 2.21%"
    assert asset_quality({"nnpa_pct": v(0.65)}) == "net NPA 0.65%"
    assert asset_quality({}) is None


def test_a_change_across_a_loss_is_named_not_a_percentage():
    """Prism Johnson Q1FY27 PAT "+2127%" from a small loss (laptop screenshots, T11 2026-10-20)."""
    from bse_intel.dossier import results_snapshot

    def snap(now, before):
        return results_snapshot({"financial_metrics": [
            {"metric": "pat", "period": "Q1FY27", "value": now, "source_news_id": "n2", "as_of": "b"},
            {"metric": "pat", "period": "Q1FY26", "value": before, "source_news_id": "n1", "as_of": "a"}]}, "n2")["pat"]

    assert snap(20.3, -0.91) == {"value": 20.3, "prev_year": -0.91, "yoy_turn": "LOSS_TO_PROFIT"}
    assert snap(-5.0, 12.0)["yoy_turn"] == "PROFIT_TO_LOSS"
    assert snap(-5.0, -12.0)["yoy_turn"] == "LOSS_NARROWED" and snap(-12.0, -5.0)["yoy_turn"] == "LOSS_WIDENED"
    assert snap(29.4, 36.8)["yoy_pct"] == -20.1   # both profits: a percentage as before


def test_an_input_counted_in_millions_is_scaled_before_the_formula_is_held():
    """Jindal Stainless (owner's review, 2026-10-20): 70 million units x ₹6.5 / 1e7 = ₹45.5 Cr was held as 4.55e-05."""
    from bse_intel.models import QuantifiedImpact
    from bse_intel.quant import check

    est = QuantifiedImpact.model_validate({
        "label": "Annual power cost saving", "formula": "annual_units * tariff_inr / 1e7", "result": 45.5, "unit": "INR_CR",
        "inputs": [{"name": "annual_units", "value": 70, "unit": "million units", "source": "FILING"},
                   {"name": "tariff_inr", "value": 6.5, "unit": "INR per unit", "source": "ASSUMPTION"}]})
    (item,) = check([est], "about 70 million units of green power a year").items
    assert item["check"] == "VERIFIED" and item["computed"] == 45.5
    wrong = est.model_copy(update={"result": 455.0})   # a real slip is still caught
    assert check([wrong], "about 70 million units").items[0]["check"] == "MISMATCH"


def test_the_results_table_takes_the_filings_own_year_ago_column():
    """Man Industries (live review 3): Q1FY26 EBITDA was ₹49.11 Cr in last year's own filing and ₹75.80 Cr in this
    filing's regrouped comparative; the table showed +192% for +89%."""
    from bse_intel.dossier import results_snapshot

    def src(news_id, value, basis="CONSOLIDATED"):
        return {"news_id": news_id, "value": value, "as_of": "2026-08-10T10:00:00+05:30", "basis": basis}

    dossier = {"financial_metrics": [
        {"metric": "revenue", "period": "Q1FY27", "value": 1053.13, "sources": [src("n2", 1053.13)]},
        {"metric": "revenue", "period": "Q1FY26", "value": 742.0, "sources": [src("n1", 742.0), src("n2", 742.0)]},
        {"metric": "ebitda", "period": "Q1FY27", "value": 143.4, "sources": [src("n2", 143.4)]},
        {"metric": "ebitda", "period": "Q1FY26", "value": 49.11, "sources": [src("n1", 49.11), src("n2", 75.80)]},
        {"metric": "pat", "period": "Q1FY27", "value": 80.0, "sources": [src("n2", 80.0)]},
    ]}
    snap = results_snapshot(dossier, "n2")
    assert snap["ebitda"]["prev_year"] == 75.80 and snap["ebitda"]["yoy_pct"] == 89.2
    # a comparative on the other basis does not replace the kept one
    dossier["financial_metrics"][3]["sources"][1]["basis"] = "STANDALONE"
    assert results_snapshot(dossier, "n2")["ebitda"]["prev_year"] == 49.11


def test_the_results_table_drops_a_comparative_the_filing_does_not_print():
    """Live review 5 (2026-10-20): Kapston's year-ago EPS ₹3.48 was the figure before its 1:2 bonus (the statement prints
    ₹2.32), so EPS read -20.4% for +19.4%; Bajaj Finance's year-ago revenue was the first-reported ₹20,178.90 Cr, credited
    to this filing, where the statement prints the restated ₹19,990.42 Cr. A comparative the text does not print goes."""
    from bse_intel.dossier import results_snapshot

    def src(news_id, value):
        return {"news_id": news_id, "value": value, "as_of": "2026-10-20T18:00:00+05:30", "basis": "CONSOLIDATED"}

    def dossier():
        return {"financial_metrics": [
            {"metric": "revenue", "period": "Q2FY27", "value": 24546.37, "sources": [src("n2", 24546.37)]},
            {"metric": "revenue", "period": "Q2FY26", "value": 20178.9, "sources": [src("n1", 20178.9), src("n2", 20178.9)]},
            {"metric": "revenue", "period": "Q1FY27", "value": 23165.45, "sources": [src("n1", 23165.45)]},
            {"metric": "pat", "period": "Q2FY27", "value": 8.41, "sources": [src("n2", 8.41)]},
            {"metric": "eps", "period": "Q2FY27", "value": 2.77, "sources": [src("n2", 2.77)]},
            {"metric": "eps", "period": "Q2FY26", "value": 3.48, "sources": [src("n1", 3.48)]},
            {"metric": "eps", "period": "Q1FY27", "value": 2.79, "sources": [src("n1", 2.79)]},
        ]}

    text = ("Revenue from operations 24,546.37 23,165.45 19,990.42 47,711.82\n"
            "Basic EPS (Rs.) 2.77 2.79 2.32 (refer note 6: restated for the bonus issue)")
    snap = results_snapshot(dossier(), "n2", printed=text)
    assert "prev_year" not in snap["revenue"] and "yoy_pct" not in snap["revenue"]
    assert snap["revenue"]["prev_quarter"] == 23165.45 and snap["revenue"]["qoq_pct"] == 6.0
    assert "prev_year" not in snap["eps"] and "yoy_pct" not in snap["eps"] and snap["eps"]["prev_quarter"] == 2.79
    # without the text (the maintenance refresh) the table is as before
    assert results_snapshot(dossier(), "n2")["eps"]["yoy_pct"] == -20.4
    # a statement whose table the text missed keeps its comparatives: nothing of the current quarter is printed
    assert results_snapshot(dossier(), "n2", printed="Outcome of the board meeting held today")["revenue"]["yoy_pct"] == 21.6


def _restated_src(news_id, value):
    return {"news_id": news_id, "value": value, "as_of": "2026-05-25T16:00:00+05:30", "basis": "CONSOLIDATED"}


def _kanoria():
    src = _restated_src
    return {"financial_metrics": [
        {"metric": "revenue", "period": "Q4FY26", "value": 304.39, "sources": [src("n2", 304.39)]},
        {"metric": "revenue", "period": "Q4FY25", "value": 431.42, "sources": [src("n1", 431.42), src("n2", 431.42)]},
        {"metric": "revenue", "period": "Q3FY26", "value": 265.82, "sources": [src("n0", 265.82), src("n2", 265.82)]},
        {"metric": "ebitda", "period": "Q4FY26", "value": 27.1, "sources": [src("n2", 27.1)]},
        {"metric": "ebitda", "period": "Q4FY25", "value": 16.99, "sources": [src("n1", 16.99), src("n2", 16.99)]},
        {"metric": "ebitda", "period": "Q3FY26", "value": 14.2, "sources": [src("n0", 14.2)]},
        {"metric": "ebitda_margin", "period": "Q4FY25", "value": 3.94, "sources": [src("n1", 3.94)]},
        {"metric": "pbt", "period": "Q4FY26", "value": 17.0, "sources": [src("n2", 17.0)]},
        {"metric": "pbt", "period": "Q4FY25", "value": -37.94, "sources": [src("n1", -37.94), src("n2", -37.94)]},
        {"metric": "pbt", "period": "Q3FY26", "value": 5.73, "sources": [src("n0", 5.73)]},
        {"metric": "pat", "period": "Q4FY26", "value": 31.62, "sources": [src("n2", 31.62)]},
        {"metric": "pat", "period": "Q4FY25", "value": -40.11, "sources": [src("n1", -40.11), src("n2", -40.11)]},
        {"metric": "pat", "period": "Q3FY26", "value": 3.55, "sources": [src("n0", 3.55)]},
        {"metric": "exceptional_items", "period": "Q4FY26", "value": 0.0, "sources": [src("n2", 0.0)]},
        {"metric": "exceptional_items", "period": "Q4FY25", "value": -29.44, "sources": [src("n1", -29.44)]},
    ]}


def test_a_restated_column_goes_whole():
    """Review 6 (2026-10-20): Kanoria restated Q4FY25 after APAG moved to discontinued operations (revenue 21,388 lakh,
    memory 431.42 Cr); Star Health's first Ind AS quarter restated Q1FY26 PAT to 43,818 lakh while its reconciliation
    note still prints the previous-GAAP 26,252."""
    from bse_intel.dossier import results_snapshot

    text = ("(Rs. in lakh) Revenue from operations 30,439 26,582 21,388\n"
            "Profit/(loss) before tax 1,700 573 (2,977)\nProfit/(loss) for the period 3,162 355 (3,640)\n"
            "Note 17. Page 38 of 40")   # 17 and 38 used to pass for EBITDA 16.99 and PBT -37.94 at crore scale
    snap = results_snapshot(_kanoria(), "n2", printed=text)
    for key in ("revenue", "ebitda", "ebitda_margin", "pbt", "pat", "exceptional_items"):
        assert "prev_year" not in snap.get(key, {}) and "yoy_pct" not in snap.get(key, {}), key
    # the previous quarter is printed as memory has it, and stays
    assert snap["revenue"]["prev_quarter"] == 265.82 and snap["pat"]["prev_quarter"] == 3.55
    assert snap["ebitda"]["prev_quarter"] == 14.2
    # a restated figure printed elsewhere (a previous-GAAP reconciliation) does not save its column
    text2 = text + "\nNet profit as per previous GAAP 4,011"
    assert "prev_year" not in results_snapshot(_kanoria(), "n2", printed=text2)["pat"]


def test_a_restated_insurer_loses_both_columns():
    """Star Health's first Ind AS quarter (review 6): both comparatives restated, the current figures stored rounded
    (₹4,917.0 Cr, ₹549.7 Cr), and the ratios restated too; the old previous-GAAP PAT 26,252 is in the reconciliation."""
    from bse_intel.dossier import results_snapshot

    src = _restated_src
    m = lambda metric, period, value, *ids: {"metric": metric, "period": period, "value": value,
                                             "sources": [src(i, value) for i in ids]}
    d = {"financial_metrics": [
        m("gross_premium", "Q1FY27", 4210.5, "n2"), m("gross_premium", "Q1FY26", 3476.1, "n1"),
        m("gross_premium", "Q4FY26", 4592.3, "n0"),
        m("revenue", "Q1FY27", 4917.0, "n2"), m("revenue", "Q1FY26", 3938.26, "n1", "n2"),
        m("revenue", "Q4FY26", 4327.15, "n0", "n2"),
        m("pat", "Q1FY27", 549.7, "n2"), m("pat", "Q1FY26", 262.52, "n1", "n2"), m("pat", "Q4FY26", 111.33, "n0", "n2"),
        m("combined_ratio", "Q1FY27", 98.41, "n2"), m("combined_ratio", "Q1FY26", 102.16, "n1"),
        m("combined_ratio", "Q4FY26", 94.73, "n0"),
        m("claims_ratio", "Q1FY27", 70.12, "n2"), m("claims_ratio", "Q1FY26", 69.55, "n1"),
        m("claims_ratio", "Q4FY26", 64.82, "n0"),
    ]}
    text = ("(Rs. in Lakhs)\nNet earned premium\n491,720\n467,110\n433,642\nProfit after tax\n54,973\n(5,540)\n43,818\n"
            "Combined ratio 98.41 88.55 92.00\nClaims ratio 70.12 64.59 68.52\n"
            "Reconciliation with previous GAAP: Net profit as per previous GAAP 26,252")
    snap = results_snapshot(d, "n2", printed=text)
    for key in ("revenue", "pat", "combined_ratio", "claims_ratio", "gross_premium"):
        for slot in ("prev_year", "prev_quarter"):
            assert slot not in snap[key], (key, slot)
    assert snap["revenue"]["value"] == 4917.0 and snap["pat"]["value"] == 549.7


def test_a_statement_that_restates_nothing_keeps_every_comparative():
    """The same table printed as memory has it: nothing goes, however tight the match."""
    from bse_intel.dossier import results_snapshot

    text = ("(Rs. in lakh) Revenue from operations 30,439 26,582 43,142\n"
            "Profit/(loss) before tax 1,700 573 (3,794)\nProfit/(loss) for the period 3,162 355 (4,011)\n"
            "Exceptional items - - (2,944)")
    snap = results_snapshot(_kanoria(), "n2", printed=text)
    assert snap == results_snapshot(_kanoria(), "n2")
    assert snap["revenue"]["prev_year"] == 431.42 and snap["ebitda"]["prev_year"] == 16.99
    assert snap["pbt"]["prev_year"] == -37.94 and snap["pat"]["prev_year"] == -40.11


def test_a_cell_the_ocr_lost_is_no_restatement():
    """UCO Bank's PBT ₹1,247.11 Cr read "1,24,7Ll", Kapston's consolidated year-ago PAT missing from its row (reviews 1
    and 5): a line refused alone needs its row read whole, its other comparative printed beside its current figure."""
    from bse_intel.dossier import results_snapshot

    # UCO's shape: both comparatives of one row garbled
    text = ("(Rs. in lakh) Revenue from operations 30,439 26,582 43,142\n"
            "Profit/(loss) before tax 1,700 57E (379A)\nProfit/(loss) for the period 3,162 355 (4,011)")
    snap = results_snapshot(_kanoria(), "n2", printed=text)
    assert snap["pbt"]["prev_quarter"] == 5.73 and snap["pbt"]["prev_year"] == -37.94
    # Kapston's: the year-ago cell lost, the previous quarter's garbled
    text = ("(Rs. in lakh) Revenue from operations 30,439 26,582 43,142\n"
            "Profit/(loss) before tax 1,700 573 (3,794)\nProfit/(loss) for the period 3,162 3S5\nEPS 2.1")
    snap = results_snapshot(_kanoria(), "n2", printed=text)
    assert snap["pat"]["prev_year"] == -40.11 and snap["pat"]["prev_quarter"] == 3.55
    # a row read whole that prints another figure still loses its comparative (Bajaj Finance's revenue, above)
    text = ("(Rs. in lakh) Revenue from operations 30,439 26,582 43,142\n"
            "Profit/(loss) before tax 1,700 573 (3,794)\nProfit/(loss) for the period 3,162 412 (4,011)")
    snap = results_snapshot(_kanoria(), "n2", printed=text)
    assert "prev_quarter" not in snap["pat"] and snap["pat"]["prev_year"] == -40.11
    assert snap["revenue"]["prev_quarter"] == 265.82   # one line refusing is no restated column


def test_a_derived_ebitda_comparative_needs_its_parts_printed():
    """Jubilant Agri Q1FY27 (check of 2026-10-20): the year-ago EBITDA ₹62.08 Cr was built with memory's other income
    ₹1.90 Cr where the statement prints 59 lakh, so it showed ₹1.31 Cr low (the filing gives ₹63.39 Cr). An EBITDA
    comparative the text does not print stays only when every part memory built it from is printed."""
    from bse_intel.dossier import results_snapshot

    src = _restated_src
    m = lambda metric, period, value: {"metric": metric, "period": period, "value": value, "sources": [src("n2", value)]}
    rows = {"revenue": (523.18, 441.95, 485.2), "ebitda": (67.96, 62.08, 32.53), "pbt": (61.57, 58.21, 26.59),
            "pat": (46.11, 44.13, 19.93), "finance_cost": (1.6, 1.76, 1.56), "depreciation": (5.22, 4.01, 4.85),
            "other_income": (0.83, 1.9, 1.66)}
    d = {"financial_metrics": [m(metric, period, value) for metric, values in rows.items()
                               for period, value in zip(("Q1FY27", "Q1FY26", "Q4FY26"), values)]}
    text = ("(Rs. in lakh)\nRevenue from operations 52,318 48,520 44,195\nOther income 83 166 59\n"
            "Finance costs 160 156 176\nDepreciation 522 485 401\nProfit before tax 6,157 2,659 5,821\n"
            "Profit for the period 4,611 1,993 4,413")
    snap = results_snapshot(d, "n2", printed=text)
    assert "prev_year" not in snap["ebitda"] and "prev_year" not in snap["ebitda_margin"]
    assert snap["ebitda"]["prev_quarter"] == 32.53 and snap["pbt"]["prev_year"] == 58.21
    # memory's parts as printed: the comparative stays
    d["financial_metrics"] = [e if (e["metric"], e["period"]) != ("other_income", "Q1FY26") else m("other_income", "Q1FY26", 0.59)
                              for e in d["financial_metrics"]]
    assert results_snapshot(d, "n2", printed=text)["ebitda"]["prev_year"] == 62.08
    # a text without the statement judges nothing
    assert results_snapshot(d, "n2", printed="Press release: revenue up 18%")["ebitda"]["prev_year"] == 62.08


def test_an_exceptional_charge_that_did_not_recur_is_no_turn():
    """Orient Bell, Jubilant Agri (live review 3): exceptional items "loss to profit" when a ₹1.29 Cr charge did not recur."""
    from bse_intel.dossier import results_snapshot

    m = lambda metric, period, value: {"metric": metric, "period": period, "value": value,
                                       "sources": [{"news_id": "n2", "value": value, "as_of": "2026-08-10T10:00:00+05:30"}]}
    dossier = {"financial_metrics": [m("revenue", "Q1FY27", 203.8), m("revenue", "Q4FY26", 190.0), m("pat", "Q1FY27", 8.3),
                                     m("pat", "Q4FY26", -0.4), m("exceptional_items", "Q1FY27", 0.0),
                                     m("exceptional_items", "Q4FY26", -1.29)]}
    snap = results_snapshot(dossier, "n2")
    assert snap["pat"]["qoq_turn"] == "LOSS_TO_PROFIT"
    assert "qoq_turn" not in snap["exceptional_items"] and "qoq_pct" not in snap["exceptional_items"]
    # the row stays in the snapshot; the table shows it only as the quarter's mover (O15)
    assert [line["key"] for line in snap["lines"]] == ["revenue", "pat"]


def test_a_company_table_shows_five_lines_and_the_one_that_moved_profit():
    """Owner, 2026-10-20 (O15): Revenue, EBITDA, EBITDA margin, PAT and EPS, plus at most one line - the one that moved
    profit most this quarter when that move is significant (a payroll ahead of a new plant's output, a tax credit)."""
    from bse_intel.dossier import results_snapshot

    def m(metric, period, value, news="n2"):
        return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "source_news_id": news, "as_of": "b"}

    def dossier(**now):
        lines = {"revenue": (1100.0, 1000.0), "ebitda": (150.0, 160.0), "pbt": (90.0, 110.0), "pat": (70.0, 85.0),
                 "eps": (7.0, 8.5), "employee_cost": (180.0, 120.0), "raw_material_cost": (550.0, 500.0),
                 "depreciation": (30.0, 29.0), "finance_cost": (12.0, 11.0), "other_income": (6.0, 7.0),
                 "tax_expense": (20.0, 25.0), "exceptional_items": (0.0, 0.0), **now}
        return {"financial_metrics": [x for k, (a, b) in lines.items() for x in (m(k, "Q2FY27", a), m(k, "Q2FY26", b, "n1"))]}

    snap = results_snapshot(dossier(), "n2")
    # payroll +₹60 Cr on sales +10%: ₹48 Cr beyond what sales carry, more than the ₹15 Cr PAT fall; raw material grew
    # with sales (₹550 Cr against ₹550 Cr at this quarter's sales), so it is no mover
    assert snap["lines"] == [{"key": "revenue", "label": "Revenue", "unit": "cr"}, {"key": "ebitda", "label": "EBITDA", "unit": "cr"},
                             {"key": "ebitda_margin", "label": "EBITDA margin", "unit": "pct"},
                             {"key": "employee_cost", "label": "Employee cost", "unit": "cr", "mover": True},
                             {"key": "pat", "label": "PAT", "unit": "cr"}, {"key": "eps", "label": "EPS (₹)", "unit": "inr"}]
    assert snap["employee_cost"] == {"value": 180.0, "prev_year": 120.0, "yoy_pct": 50.0}
    assert snap["pbt"]["value"] == 90.0 and "exceptional_items" in snap   # kept in the snapshot, off the table

    # a tax credit lifting profit while EBITDA fell (Texmaco's shape, round 5)
    snap = results_snapshot(dossier(pat=(120.0, 85.0), employee_cost=(132.0, 120.0), tax_expense=(-30.0, 25.0)), "n2")
    (mover,) = [line for line in snap["lines"] if line.get("mover")]
    assert mover == {"key": "tax_expense", "label": "Tax", "unit": "cr", "mover": True}
    assert snap["tax_expense"] == {"value": -30.0, "prev_year": 25.0}   # no % across a credit
    # an exceptional gain that made the quarter
    snap = results_snapshot(dossier(pat=(140.0, 85.0), employee_cost=(132.0, 120.0), exceptional_items=(60.0, 0.0)), "n2")
    assert [line["key"] for line in snap["lines"] if line.get("mover")] == ["exceptional_items"]

    # no mover: profit barely moved, or no line carried a quarter of the move, or the line is small against sales
    flat = dossier(pat=(86.0, 85.0))
    assert not any(line.get("mover") for line in results_snapshot(flat, "n2")["lines"])
    spread = dossier(pat=(65.0, 85.0), employee_cost=(136.0, 120.0), depreciation=(34.0, 29.0), finance_cost=(16.0, 11.0))
    assert not any(line.get("mover") for line in results_snapshot(spread, "n2")["lines"])   # ₹4-5 Cr each of a ₹20 Cr fall
    small = dossier(revenue=(5500.0, 5000.0), pat=(6.0, 3.0), employee_cost=(132.0, 120.0), raw_material_cost=(2750.0, 2500.0),
                    tax_expense=(1.0, 4.0))
    assert not any(line.get("mover") for line in results_snapshot(small, "n2")["lines"])     # ₹3 Cr at ₹5,500 Cr sales
    # a line moving against profit is not what moved it: payroll fell while profit fell
    against = dossier(employee_cost=(100.0, 120.0), finance_cost=(25.0, 11.0))
    assert [line["key"] for line in results_snapshot(against, "n2")["lines"] if line.get("mover")] == ["finance_cost"]


def test_a_call_card_shows_the_quarter_it_discusses():
    """Design audit fix 10 (2026-10-20): an earnings call or presentation gets the results table of the latest quarter
    in memory, as its results filing gave it, and nothing when that quarter ended long before the call."""
    from bse_intel.dossier import call_results_snapshot, results_snapshot

    dossier = {"financial_metrics": [
        {"metric": "revenue", "period": "Q2FY27", "value": 455.6, "source_news_id": "n2", "as_of": "2026-10-15T16:00:00+05:30"},
        {"metric": "pat", "period": "Q2FY27", "value": 29.4, "source_news_id": "n2", "as_of": "2026-10-15T16:00:00+05:30"},
        {"metric": "pat", "period": "Q2FY26", "value": 36.8, "source_news_id": "n1", "as_of": "2025-10-14T16:00:00+05:30"},
        {"metric": "revenue", "period": "Q1FY27", "value": 412.3, "source_news_id": "n1b", "as_of": "2026-07-20T16:00:00+05:30"},
    ]}
    snap = call_results_snapshot(dossier, "2026-10-17T11:00:00+05:30")
    assert snap["discussed"] is True and snap["period"] == "Q2FY27"
    assert {k: v for k, v in snap.items() if k != "discussed"} == results_snapshot(dossier, "n2")
    assert call_results_snapshot(dossier, "2027-04-20T11:00:00+05:30") is None, "Q2FY27 ended over 120 days before"
    assert call_results_snapshot(dossier, "2026-09-20T11:00:00+05:30")["period"] == "Q1FY27", "not a quarter still open"


def test_the_decision_box_takes_up_to_four_points_from_memory():
    """Owner (2026-10-20): "For the decision" needs 3-4 points from memory, not a run-rate P/E. All made by code from
    what memory held before the filing, nothing from the filing itself."""
    from bse_intel.card_context import memory_context

    before = {
        "guidance": [{"id": "g1", "statement": "FY27 revenue growth guided at 15%", "metric": "revenue", "target": "15%",
                      "due": "FY27", "due_date": "2027-03-31", "given_on": "2026-05-10T10:00:00+05:30", "status": "OPEN"}],
        "financial_metrics": [{"metric": "revenue", "period": "Q1FY27", "value": 1200.5, "yoy_pct": 12.3},
                              {"metric": "pat", "period": "Q1FY27", "value": 150.0}],
        "ownership": [{"period": "Q4FY26", "promoter_pct": 56.4, "fii_pct": 13.9, "as_of": "2026-04-17"},
                      {"period": "Q1FY27", "promoter_pct": 54.7, "fii_pct": 15.8, "as_of": "2026-07-20"}],
        "watchlist": [{"text": "New plant commissioning", "status": "OPEN", "check_in": "Q3FY27", "check_by": "2026-12-31",
                       "created_on": "2026-08-01", "source_news_id": "n0"},
                      {"text": "Order inflow of ₹5,000 Cr in FY27", "status": "OPEN", "check_in": "Q4FY27",
                       "check_by": "2027-03-31", "created_on": "2026-06-01", "source_news_id": "n0"}],
        "operating_notes": [{"text": "Plant 2 running at 55% utilisation", "as_of": "2026-09-01", "source_news_id": "n0"},
                            {"text": "this filing's own note", "as_of": "2026-10-20", "source_news_id": "n9"}],
    }
    points = memory_context(before, "ORDER_WIN", "2026-10-20T10:00:00+05:30", "n9")
    assert [p["label"] for p in points] == ["Management said, May 2026", "Latest quarter, Q1FY27",
                                            "Holding, Q4FY26 → Q1FY27, Jul 2026", "Watching, Jun 2026"]
    # only what bears on the event: an order card watches the order inflow, not the plant; a capex card the plant
    assert points[3]["text"].startswith("Order inflow")
    capex = memory_context(before, "CAPEX", "2026-10-20T10:00:00+05:30", "n9")
    assert any(p["text"].startswith("New plant") for p in capex)
    # on topic but stale: a watch item raised over three quarters ago, a note older than 120 days
    stale = {**before, "watchlist": [{**w, "created_on": "2025-11-01"} for w in before["watchlist"]],
             "operating_notes": [{"text": "Plant 2 running at 55% utilisation", "as_of": "2026-05-01", "source_news_id": "n0"}]}
    assert not [p for p in memory_context(stale, "CAPEX", "2026-10-20", "n9") if p["label"].startswith(("Watching", "From memory"))]
    # an event with no topic (a board meeting notice) gets no watch item or note, only the figures and holdings
    assert [p["label"].split(",")[0] for p in memory_context(before, "OTHER", "2026-10-20", "n9")] == ["Latest quarter", "Holding"]
    assert points[1]["text"] == "revenue ₹1,200.5 Cr (+12.3% YoY), PAT ₹150 Cr"
    assert points[2]["text"] == "Promoters 56.4% → 54.7%; FIIs 13.9% → 15.8%"
    # a results card is the latest quarter itself: the note takes that place
    assert [p["label"] for p in memory_context(before, "RESULTS", "2026-10-20T10:00:00+05:30", "n9")][-1] == "From memory, Sep 2026"
    assert memory_context(None, "RESULTS", "2026-10-20") == []


def test_a_missing_previous_quarter_comes_from_the_half_year():
    """E2E Networks' call card (live, 2026-10-21): memory held Q2FY27 and H1FY27 only, so the table showed no Q1FY27."""
    from bse_intel.dossier import results_snapshot
    dossier = {"financial_metrics": [
        {"metric": "revenue", "period": "Q2FY27", "value": 223.8, "source_news_id": "n2", "as_of": "b"},
        {"metric": "revenue", "period": "H1FY27", "value": 380.5, "source_news_id": "n2", "as_of": "b"},
        {"metric": "pat", "period": "Q2FY27", "value": 72.7, "source_news_id": "n2", "as_of": "b"},
        {"metric": "pat", "period": "H1FY27", "value": 116.6, "source_news_id": "n2", "as_of": "b"},
        {"metric": "eps", "period": "Q2FY27", "value": 3.48, "source_news_id": "n2", "as_of": "b"},
        {"metric": "eps", "period": "H1FY27", "value": 5.6, "source_news_id": "n2", "as_of": "b"},
    ]}
    snap = results_snapshot(dossier, "n2")
    assert snap["revenue"]["prev_quarter"] == 156.7 and snap["revenue"]["qoq_pct"] == 42.8
    assert snap["pat"]["prev_quarter"] == 43.9
    assert "prev_quarter" not in snap.get("eps", {})   # per share: not a sum of quarters
    # shown as worked out, not reported (data chain audit, 22 Oct 2026); and never across two bases
    assert snap["revenue"]["derived"] == ["prev_quarter"] and snap["pat"]["derived"] == ["prev_quarter"]
    mixed = {"financial_metrics": [dict(m, basis="STANDALONE" if m["period"] == "Q2FY27" else "CONSOLIDATED")
                                   for m in dossier["financial_metrics"]]}
    assert "prev_quarter" not in (results_snapshot(mixed, "n2") or {}).get("revenue", {})


def test_a_revenue_yoy_never_rests_on_a_refused_year_ago():
    """Data chain audit A8 (22 Oct 2026): with the year-ago revenue refused (the statement prints another figure), the
    stored XBRL YoY was put back on the row, a change against the very base the table had just refused."""
    from bse_intel.dossier import results_snapshot
    dossier = {"financial_metrics": [
        {"metric": "revenue", "period": "Q2FY27", "value": 1200.0, "yoy_pct": 20.0, "source_news_id": "n2", "as_of": "b"},
        {"metric": "revenue", "period": "Q2FY26", "value": 1000.0, "source_news_id": "n1", "as_of": "a"},
        {"metric": "pat", "period": "Q2FY27", "value": 100.0, "source_news_id": "n2", "as_of": "b"},
        {"metric": "pat", "period": "Q2FY26", "value": 80.0, "source_news_id": "n1", "as_of": "a"},
        {"metric": "pbt", "period": "Q2FY27", "value": 130.0, "source_news_id": "n2", "as_of": "b"},
        {"metric": "pbt", "period": "Q2FY26", "value": 105.0, "source_news_id": "n1", "as_of": "a"},
    ]}
    printed = "Revenue 1,200.00 1,050.00 Profit before tax 130.00 110.00 Profit 100.00 85.00"   # a restated column
    snap = results_snapshot(dossier, "n2", printed=printed)
    assert "prev_year" not in snap["revenue"] and "yoy_pct" not in snap["revenue"]
    alone = {"financial_metrics": [m for m in dossier["financial_metrics"] if m["period"] == "Q2FY27"]
             + [m for m in dossier["financial_metrics"] if m["metric"] != "revenue" and m["period"] == "Q2FY26"]}
    assert results_snapshot(alone, "n2")["revenue"]["yoy_pct"] == 20.0   # no year-ago in memory: the file's own YoY


def test_a_procedural_watch_item_is_not_for_the_decision():
    """Indosolar's results card (live, 2026-10-21) showed "Watching: Shareholders' approval for appointment of ... as cost
    auditor", on topic only through the word "cost"."""
    from bse_intel.card_context import memory_context

    before = {"watchlist": [{"text": "Shareholders' approval for appointment of M/s N Ritesh and Associates as cost auditor "
                                     "for FY2026-27", "status": "OPEN", "created_on": "2026-08-01", "source_news_id": "n0"}]}
    assert memory_context(before, "RESULTS", "2026-10-20", "n9") == []
    assert [p["label"].split(",")[0] for p in memory_context(before, "GOVERNANCE", "2026-10-20", "n9")] == ["Watching"]


def test_the_view_shows_earlier_calls_and_the_balance_sheets_key_lines():
    """Memory now holds the whole balance sheet and each call's checked takeaways (21 Oct 2026); the model sees the
    key balance-sheet lines and the last calls' points with ids it can cite."""
    from bse_intel.dossier import call_point_id, view_as_of

    dossier = {"company_name": "Demo", "financial_metrics": [], "balance_sheet": [
        {"period": "Q2FY27", "as_of": "2026-10-10T18:00:00+05:30", "net_worth_cr": 1000.0, "total_assets_cr": 3000.0,
         "fixed_assets_cr": 900.0, "cwip_cr": 12.0, "source_news_id": "x"}],
        "call_points": [{"news_id": "c2", "date": "2026-08-10", "category": "Guidance", "text": "FY27 volume growth 10-12%"},
                        {"news_id": "c1", "date": "2026-05-10", "category": "Capex", "text": "Plant 2 by Q3FY27"},
                        {"news_id": "c3", "date": "2026-10-25", "category": "Guidance", "text": "after the filing"}]}
    view = view_as_of(dossier, "2026-10-20T10:00:00+05:30")
    assert view["balance_sheet"] == {"period": "Q2FY27", "as_of": "2026-10-10T18:00:00+05:30", "net_worth_cr": 1000.0,
                                     "total_assets_cr": 3000.0}
    calls = view["previous_calls"]
    assert [c["text"] for c in calls] == ["FY27 volume growth 10-12%", "Plant 2 by Q3FY27"]
    assert calls[0]["id"] == call_point_id(dossier["call_points"][0]) and calls[0]["id"].startswith("cp_")


def test_a_comparison_never_crosses_bases():
    """Data chain audit A3 (22 Oct 2026): a group that begins consolidating had its consolidated quarter set against a
    standalone year-ago; memory picks consolidated per metric and period, not to match the current figure."""
    from bse_intel.dossier import results_snapshot
    rows = lambda yb: {"financial_metrics": [
        {"metric": "revenue", "period": "Q2FY27", "value": 1200.0, "basis": "CONSOLIDATED", "source_news_id": "n2", "as_of": "b"},
        {"metric": "revenue", "period": "Q2FY26", "value": 700.0, "basis": yb, "source_news_id": "n1", "as_of": "a"},
        {"metric": "pat", "period": "Q2FY27", "value": 100.0, "basis": "CONSOLIDATED", "source_news_id": "n2", "as_of": "b"},
        {"metric": "pat", "period": "Q2FY26", "value": 60.0, "basis": yb, "source_news_id": "n1", "as_of": "a"},
        {"metric": "pbt", "period": "Q2FY27", "value": 130.0, "basis": "CONSOLIDATED", "source_news_id": "n2", "as_of": "b"}]}
    crossed = results_snapshot(rows("STANDALONE"), "n2")
    assert "prev_year" not in crossed["revenue"] and "yoy_pct" not in crossed["pat"]
    same = results_snapshot(rows("CONSOLIDATED"), "n2")
    assert same["revenue"]["yoy_pct"] == 71.4 and same["pat"]["prev_year"] == 60.0


def test_this_quarters_figure_is_the_tagged_files_over_the_cards_reading():
    """HDFC Life (hourly review, 22 Oct 2026): the card read the standalone PAT ₹508 Cr from the PDF while memory held the
    consolidated file's ₹521.60 Cr and consolidated comparatives, so the table set standalone against consolidated."""
    from bse_intel.dossier import results_snapshot
    dossier = {"financial_metrics": [
        {"metric": "pat", "period": "Q2FY27", "value": 521.6, "source_news_id": "n2", "as_of": "b",
         "sources": [{"news_id": "n2", "as_of": "b", "value": 508.0},
                     {"news_id": "xbrl:res:540777:Q2FY27", "as_of": "b", "value": 521.6, "basis": "CONSOLIDATED"}]},
        {"metric": "pat", "period": "Q1FY27", "value": 611.19, "basis": "CONSOLIDATED", "source_news_id": "n1", "as_of": "a"},
        {"metric": "revenue", "period": "Q2FY27", "value": 20000.0, "basis": "CONSOLIDATED", "source_news_id": "n2", "as_of": "b"},
        {"metric": "pbt", "period": "Q2FY27", "value": 600.0, "basis": "CONSOLIDATED", "source_news_id": "n2", "as_of": "b"}]}
    snap = results_snapshot(dossier, "n2")
    assert snap["pat"]["value"] == 521.6 and snap["pat"]["qoq_pct"] == -14.7


def test_a_call_table_is_the_results_filings_not_the_calls_own_reading():
    """Garware Hi-Tech's Q2FY27 deck (live audit, 22 Oct 2026): memory's only Q2FY27 figures were the deck's own
    (EBITDA ₹189 Cr with other income) and the call card's table set them against the filings' quarters without it.
    The quarter the call discusses comes from memory with the call; its figures only from memory before it."""
    from bse_intel.dossier import call_results_snapshot, dossier_as_of

    def metric(name, period, value, news_id, as_of):
        return {"metric": name, "period": period, "value": value, "unit": "INR_CR", "source_news_id": news_id, "as_of": as_of,
                "sources": [{"news_id": news_id, "as_of": as_of, "value": value}]}

    filed = "2026-10-22T12:18:00+05:30"
    results = [metric("revenue", "Q1FY27", 633.08, "n1", "2026-08-10T18:00:00+05:30"),
               metric("pat", "Q1FY27", 132.65, "n1", "2026-08-10T18:00:00+05:30")]
    deck = [metric("revenue", "Q2FY27", 696.0, "deck", filed), metric("ebitda", "Q2FY27", 189.0, "deck", filed)]
    memory = {"financial_metrics": results + deck}
    current, before = dossier_as_of(memory, filed), dossier_as_of(memory, filed, inclusive=False)
    assert call_results_snapshot(current, filed)["period"] == "Q2FY27"           # the call's own reading, as before
    assert call_results_snapshot(current, filed, before=before) is None          # no results filing of Q2FY27 yet
    # once the results filing is in memory before the call, its figures make the table
    memory["financial_metrics"] += [metric("revenue", "Q2FY27", 695.71, "n2", "2026-10-21T16:00:00+05:30"),
                                    metric("pat", "Q2FY27", 129.4, "n2", "2026-10-21T16:00:00+05:30")]
    current, before = dossier_as_of(memory, filed), dossier_as_of(memory, filed, inclusive=False)
    table = call_results_snapshot(current, filed, before=before)
    assert table["period"] == "Q2FY27" and table["revenue"]["value"] == 695.71 and table["discussed"] is True
