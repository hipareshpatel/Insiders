"""Clear events make a card HIGH whatever its score (owner, 2026-10-20); misfires from the first measurement stay out."""

from bse_intel.impact import high_reasons


def test_results_moves_orders_deals_and_ratings_are_high():
    assert high_reasons({"results": {"pat": {"yoy_pct": -48.0}}}, "RESULTS", []) == ["PAT -48% YoY"]
    assert high_reasons({"results": {"pat": {"yoy_turn": "LOSS_TO_PROFIT"}}}, "RESULTS", []) == ["PAT turned from loss to profit YoY"]
    assert high_reasons({"results": {"ebitda_margin": {"yoy_bps": 730}}}, "RESULTS", []) == ["EBITDA margin +730 bps YoY"]
    assert not high_reasons({"results": {"pat": {"yoy_pct": 12.0}, "ebitda_margin": {"yoy_bps": -120}}}, "RESULTS", [])
    order = {"scale": {"noun": "order", "against": [{"label": "FY26 revenue", "pct": 14.0}]}}
    assert high_reasons(order, "ORDER_WIN", []) == ["Order 14% of a year's revenue"]
    spread = {"scale": {"noun": "order", "against": [{"label": "FY26 revenue", "pct": 27.0}], "per_year": {"pct": 9.0}}}
    assert not high_reasons(spread, "ORDER_WIN", [])   # 27% over three years is 9% a year
    deal = {"scale": {"noun": "deal", "against": [{"label": "market cap", "pct": 6.0}]}}
    assert high_reasons(deal, "M_AND_A", []) == ["Deal 6% of market cap"]
    raise_ = {"scale": {"noun": "raise", "against": [{"label": "market cap", "pct": 6.0}]}}
    assert not high_reasons(raise_, "FUNDRAISE", [])   # about 6% dilution
    assert high_reasons({"rating_change": {"before": "AA", "after": "AA+", "notches": 1}}, "DEBT_RATINGS", []) == ["Rating moved 1 notch"]
    reaffirmed = {"rating_change": {"before": "A", "after": "A", "notches": 0, "before_outlook": "Stable", "after_outlook": "Stable"}}
    assert not high_reasons(reaffirmed, "DEBT_RATINGS", [])
    case = {"case_stage": {"track": "USFDA", "steps": ["Form 483", "Warning letter", "Import alert", "Closed"], "at": 1, "reached": ["Warning letter"]}}
    assert high_reasons(case, "LITIGATION_REGULATORY", []) == ["USFDA warning letter"]


def test_memory_items_on_an_unrelated_filing_are_not_high():
    emphasis = [{"type": "AUDIT_FLAG", "text": "Emphasis of matter in the audit report: export receivables"}]
    assert not high_reasons({}, "MANAGEMENT_CHANGE", emphasis)
    assert high_reasons({}, "RESULTS", [{"type": "AUDIT_FLAG", "text": "Auditor's opinion: qualified"}])
    lapsed = [{"type": "GUIDANCE_BREACH", "text": "Deadline passed: \"8.5%-9% margin\" was due FY25"}]
    assert not high_reasons({}, "GOVERNANCE", lapsed) and not high_reasons({}, "RESULTS", lapsed)
    missed = [{"type": "GUIDANCE_BREACH", "text": "Missed: \"Milk sales to grow at 7-8%\" (guided 2025-05-21)"}]
    assert high_reasons({}, "CONCALL_PRESENTATION", missed) == ["Promise broken"]
    assert not high_reasons({}, "M_AND_A", missed)
    assert high_reasons({}, "MANAGEMENT_CHANGE", [], top_exit=True) == ["MD, CEO or CFO leaving"]
