"""The 0-100 actionability score and the 4 gates, on situations from the blueprint's case studies."""

from bse_intel.scoring import credibility, score, ttm_revenue

Q = lambda p, v: {"metric": "revenue", "period": p, "value": v, "unit": "INR_CR", "as_of": "2026-01-01"}  # noqa: E731


def test_ttm_revenue_prefers_four_quarters_then_the_year():
    d = {"financial_metrics": [Q("Q2FY26", 90), Q("Q3FY26", 95), Q("Q4FY26", 100), Q("Q1FY27", 110)]}
    assert ttm_revenue(d) == (395, "TTM to Q1FY27")
    assert ttm_revenue({"financial_metrics": [Q("FY26", 400), Q("Q1FY27", 110)]}) == (400, "FY26")


def test_large_order_for_a_small_company_with_a_clean_record_is_a_top_signal():
    dossier = {"financial_metrics": [Q("Q2FY26", 30), Q("Q3FY26", 30), Q("Q4FY26", 30), Q("Q1FY27", 30)],
               "guidance": [{"status": "DELIVERED"}, {"status": "DELIVERED"}, {"status": "DELIVERED"}, {"status": "MISSED"}],
               "balance_sheet": [{"net_worth_cr": 80}]}
    card = {"headline": "Demo Infra wins ₹40 Cr order", "what_happened": ["Order at its existing plant"],
            "deal_value": {"kind": "ORDER", "amount_cr": 40}, "grounding": {"ungrounded": []}, "missing_disclosures": []}
    signals = [{"type": "PROMISE_DELIVERED", "severity": "POSITIVE", "text": "x"}]
    company = {"market_cap_cr": 400, "ret_1m": 3.0, "ret_1w": 1.0, "median_turnover_cr": 2.0}
    s = score(card, "ORDER_WIN", signals, dossier, company, needs_review=False, model_impact="HIGH")
    assert s.gates == {"magnitude": True, "inflection": True, "price": True, "clean": True}
    assert s.total >= 70 and s.impact == "HIGH" and s.actionable
    assert credibility(dossier) == (75.0, 3, 4)
    # module 50: the same card on a trade-to-trade stock fails the price gate (hard to exit)
    t2t = score(card, "ORDER_WIN", signals, dossier, {**company, "bse_group": "XT"}, needs_review=False, model_impact="HIGH")
    assert t2t.gates["price"] is False and any("Trade-to-trade" in r for r in t2t.reasons)
    # earnings-quality penalties count once each
    weak = score(card, "ORDER_WIN", signals + [{"type": "DISTRESS", "severity": "WARNING", "text": "x"},
                                                {"type": "DISTRESS", "severity": "WARNING", "text": "y"}],
                 dossier, company, needs_review=False, model_impact="HIGH")
    assert weak.pillars["penalty"] == -15 and weak.total == s.total - 15


def test_distressed_rights_issue_and_vetoes_cap_the_score():
    dossier = {"balance_sheet": [{"net_worth_cr": -61.67}]}
    card = {"headline": "Shivam Autotech sets ₹120 Cr rights issue", "what_happened": ["x"],
            "deal_value": {"kind": "FUNDRAISE", "amount_cr": 120}, "grounding": {"ungrounded": ["7"]}}
    signals = [{"type": "DILUTION", "severity": "WARNING", "text": "Rights: 76.0% more shares (43.2% post-money dilution; ...)"}]
    s = score(card, "RIGHTS_ISSUE", signals, dossier, {"market_cap_cr": 223, "ret_1m": -3.8}, needs_review=True, model_impact="MODERATE")
    assert s.pillars["balance_sheet"] == 3 and not s.gates["clean"] and s.total <= 35 and not s.actionable
    assert s.impact == "LOW"


def test_stage_update_of_a_known_order_is_vetoed():
    signals = [{"type": "ORDER_FLOW", "severity": "INFO", "text": "Stage update, not a new order: LOI to LOA."}]
    s = score({"headline": "h", "what_happened": [], "deal_value": {"kind": "ORDER", "amount_cr": 50}}, "ORDER_WIN",
              signals, None, {}, needs_review=False, model_impact="HIGH")
    assert "Stage update of an order already counted" in s.vetoes and s.total <= 35
