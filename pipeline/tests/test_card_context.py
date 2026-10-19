"""The card's event blocks made by code: rating move, case stage, guidance recalled from memory (card_context.py)."""

from bse_intel.card_context import case_stage, guidance_recall, long_term_grade, rating_change


def test_long_term_grades_are_read_past_the_agency_name():
    assert long_term_grade("CARE A- (Negative)") == "A-"
    assert long_term_grade("[ICRA]AA(Stable)") == "AA"
    assert long_term_grade("IND A+/Stable") == "A+"
    assert long_term_grade("CRISIL BBB-/Stable; CRISIL A3") == "BBB-"
    assert long_term_grade("ACUITE A1+") is None        # short-term only
    assert long_term_grade("CARE AA (CE); Stable") == "AA"


def test_rating_change_counts_notches_against_the_last_rating_in_memory():
    before = {"balance_sheet": [{"credit_rating": "CARE A (Stable)", "rating_outlook": "Stable", "as_of": "2026-03-01T10:00"}]}
    after = {"balance_sheet": before["balance_sheet"] + [
        {"credit_rating": "CARE A- (Negative)", "rating_agency": "CARE", "rating_outlook": "Negative", "source_news_id": "n9"}]}
    assert rating_change(before, after, "n9") == {
        "agency": "CARE", "after": "A-", "after_outlook": "Negative", "before": "A", "before_outlook": "Stable",
        "notches": -1, "as_of_before": "2026-03-01"}
    assert rating_change(before, after, "other") is None          # the latest rating is not this filing's
    first = rating_change(None, after, "n9")
    assert first["before"] is None and first["notches"] is None


def test_case_stage_takes_the_furthest_step_the_card_names():
    usfda = case_stage("LITIGATION_REGULATORY", "Demo Pharma gets USFDA warning letter for Unit III", [])
    assert usfda == {"track": "USFDA", "steps": ["Form 483", "Warning letter", "Import alert", "Closed"], "at": 1}
    tax = case_stage("LITIGATION_REGULATORY", "GST demand of ₹42 Cr with penalty; company to appeal", [])
    assert tax["track"] == "CASE" and tax["steps"][tax["at"]] == "Order"     # "to appeal" is not an appeal filed
    filed = case_stage("LITIGATION_REGULATORY", "Company filed an appeal against the ₹42 Cr GST order", [])
    assert filed["steps"][filed["at"]] == "Appeal"
    assert case_stage("ORDER_WIN", "Wins order", []) is None


def test_guidance_recall_keeps_the_companys_own_open_words_that_bear_on_the_event():
    before = {"guidance": [
        {"id": "g1", "statement": "FY27 sales of ₹1,500-1,700 Cr", "metric": "revenue", "status": "OPEN",
         "given_on": "2026-08-12T10:00", "source_type": "CONCALL", "due": "FY27"},
        {"id": "g2", "statement": "Ind-Ra expects revenue growth of 20%", "status": "OPEN", "given_on": "2026-09-01"},
        {"id": "g3", "statement": "Commission Unit 3", "metric": "capacity", "status": "DELIVERED", "given_on": "2026-01-01"},
    ]}
    got = guidance_recall(before, "ORDER_WIN")
    assert [g["id"] for g in got] == ["g1"] and got[0]["given_on"] == "2026-08-12" and got[0]["source_type"] == "CONCALL"
    assert guidance_recall(before, "MANAGEMENT_CHANGE") == []


def test_an_orders_term_spreads_it_over_the_years_it_runs():
    """Monarch's ₹48.10 Cr railway order over 36 months (owner's example, 2026-10-19): a share of a year's revenue a
    year, beside its share of the last quarter and year."""
    from bse_intel.models import Pass2Output
    from bse_intel.signals import _scale, scale_parts, term_years

    assert term_years("within 36 months", "2026-10-19T18:15") == 3.0
    assert term_years("3 years", None) == 3.0
    assert round(term_years("31 March 2028", "2026-10-19T18:15"), 1) == 1.4
    assert term_years(None, "2026-10-19") is None
    out = Pass2Output.model_validate({"is_material": True, "event_type": "ORDER_WIN", "card": {
        "impact_level": "MODERATE", "headline": "Monarch Surveyors wins ₹48 Cr railway order",
        "what_happened": ["Letter of Acceptance for ₹48.10 Cr"],
        "deal_value": {"kind": "ORDER", "amount_cr": 48.1, "stage": "LOA", "execution_by": "36 months"}}})
    before = {"financial_metrics": [{"metric": "revenue", "period": "FY26", "value": 172.0, "unit": "INR_CR"}]}
    scale = scale_parts(before, out, {}, "2026-10-19T18:15")
    assert scale["per_year"] == {"years": 3.0, "pct": 9.3, "label": "FY26 revenue"}
    assert _scale(before, out, {}, "2026-10-19T18:15")[0].text == (
        "₹48.1 Cr order = 28% of FY26 revenue (₹172 Cr); over its 3-year term, 9% of FY26 revenue a year.")
