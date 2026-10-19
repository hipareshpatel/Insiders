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
    assert usfda == {"track": "USFDA", "steps": ["Form 483", "Warning letter", "Import alert", "Closed"], "at": 1,
                     "reached": [1]}
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


def test_rating_change_compares_only_with_the_same_agency():
    """A company rated CRISIL AA and ICRA AA- has two opinions, not a downgrade between them."""
    before = {"balance_sheet": [{"credit_rating": "CRISIL AA/Stable", "as_of": "2026-01-01"}]}
    after = {"balance_sheet": [{"credit_rating": "[ICRA]AA-(Stable)", "rating_agency": "ICRA", "source_news_id": "n1"}]}
    got = rating_change(before, after, "n1")
    assert got["after"] == "AA-" and got["before"] is None and got["notches"] is None
    before["balance_sheet"].append({"credit_rating": "ICRA A+ (Positive)", "as_of": "2026-03-01"})
    assert rating_change(before, after, "n1")["notches"] == 1           # A+ -> AA-: one notch up, same agency
    unknown = {"balance_sheet": [{"credit_rating": "BBB", "source_news_id": "n2"}]}
    assert rating_change(before, unknown, "n2")["before"] == "A+"         # agency unknown: the last rating on record


def test_long_term_grades_edge_cases():
    assert long_term_grade("CARE BB; Stable; ISSUER NOT COOPERATING") == "BB"
    assert long_term_grade("CRISIL AAA(SO)") == "AAA"
    assert long_term_grade("CARE D") == "D"
    assert long_term_grade("Withdrawn") is None
    assert long_term_grade("") is None and long_term_grade(None) is None


def test_case_stage_needs_a_case_and_reads_its_words_strictly():
    assert case_stage("GOVERNANCE", "Notice of the 32nd Annual General Meeting", []) is None       # no regulator
    assert case_stage("GOVERNANCE", "SEBI show cause notice to the managing director", [])["at"] == 0
    in_order = case_stage("LITIGATION_REGULATORY", "Company moves court in order to protect its patent", [])
    assert in_order is None                                                                       # no stage named
    dismissed = case_stage("LITIGATION_REGULATORY", "Tribunal dismissed the company's appeal against the GST demand", [])
    assert dismissed["steps"][dismissed["at"]] == "Order"       # dismissed is not "resolved"; the demand stands
    eir = case_stage("LITIGATION_REGULATORY", "USFDA issues EIR for Unit II after zero observations", [])
    assert eir["track"] == "USFDA" and eir["steps"][eir["at"]] == "Closed"
    assert case_stage("LITIGATION_REGULATORY", "Receives USFDA approval for generic tablets", []) is None


def test_guidance_recall_skips_overdue_old_and_part_word_matches():
    before = {"guidance": [
        {"id": "old", "statement": "Revenue of ₹500 Cr", "status": "OPEN", "given_on": "2024-01-01", "due_date": "2027-03-31"},
        {"id": "late", "statement": "FY26 revenue of ₹900 Cr", "status": "OPEN", "given_on": "2026-02-01", "due_date": "2026-03-31"},
        {"id": "patent", "statement": "Two patents to be filed", "status": "OPEN", "given_on": "2026-08-01"},
        {"id": "ok", "statement": "FY27 PAT margin of 12%", "status": "ON_TRACK", "given_on": "2026-08-01", "due_date": "2027-03-31"},
    ]}
    assert [g["id"] for g in guidance_recall(before, "RESULTS", "2026-10-19T10:00")] == ["ok"]
    assert [g["id"] for g in guidance_recall(before, "RESULTS", None)] == ["ok", "late"]   # no date: no age rules


def test_order_terms_in_ranges_and_short_terms():
    from bse_intel.signals import term_years

    assert term_years("18 to 21 months", None) == 1.75      # the longer end of a range
    assert term_years("within 6 months of the LOA", None) == 0.5
    assert term_years("FY28", "2026-10-19") and round(term_years("FY28", "2026-10-19"), 1) == 1.4
    assert term_years("by 2025", "2026-10-19") is None       # already past
    assert term_years("as per the schedule", "2026-10-19") is None



def test_case_steps_are_marked_each_on_its_own():
    """Dabur (laptop re-check, 2026-10-19): the import alert came in June, the warning letter in July. The card is about
    the warning letter, and the import alert is marked as reached too, not left ahead of the company."""
    got = case_stage("LITIGATION_REGULATORY", "Dabur gets USFDA warning letter for its Baddi unit",
                     ["The letter follows the June import alert on the unit"], ["Exports from the unit already stopped"])
    assert got["steps"][got["at"]] == "Warning letter" and got["reached"] == [1, 2]


def test_a_rating_reads_its_earlier_grade_from_the_filing_when_memory_has_none():
    """Hind Copper's ICRA upgrade: memory had no earlier rating; the filing says "from [ICRA]AA+ (Stable)"."""
    from bse_intel.card_context import grade_before_in_text

    text = ("ICRA has upgraded the Long-term rating to [ICRA]AAA (Stable) from [ICRA]AA+ (Stable) for the "
            "Rs. 2,100 crore facilities; the short-term rating is reaffirmed at [ICRA]A1+.")
    assert grade_before_in_text(text) == "AA+"
    after = {"balance_sheet": [{"credit_rating": "[ICRA]AAA (Stable)", "rating_agency": "ICRA", "source_news_id": "n1"}]}
    got = rating_change(None, after, "n1", text)
    assert (got["before"], got["after"], got["notches"], got["as_of_before"]) == ("AA+", "AAA", 1, None)
    assert grade_before_in_text("Rating reaffirmed at CARE A-") is None          # no "from": no earlier grade
    assert grade_before_in_text("revised from short-term A1 to A1+") is None     # short-term only


def test_guidance_recall_needs_a_target_or_a_deadline():
    before = {"guidance": [{"id": "x", "statement": "RoA improved on lower credit costs", "status": "OPEN", "given_on": "2026-08-01"}]}
    assert guidance_recall(before, "RESULTS", "2026-10-19") == []
