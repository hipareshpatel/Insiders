"""The accuracy gate (gate.py). Each test is named after the filing whose card it would have caught."""
import json
from pathlib import Path
from datetime import timedelta

import pytest

from bse_intel import gate
from bse_intel.timeutil import now_ist

from test_pipeline import PASS2, RESULT_TEXT, _filing, _pdf, build


def test_garbled_scan_text_is_flagged_clean_text_is_not():
    """Heritage Foods Q4FY25 and eMudhra's QIP monitoring report: "l0,406.47", "99S.08", "(1,9S7)" in the text layer."""
    clean = " ".join(f"{n:,}.{n % 100:02d}" for n in range(1000, 1400))
    assert not gate.text_is_garbled(clean)
    assert not gate.text_is_garbled(clean + " Q3FY25 30th 2nd 5G INE758C01029 L15209TG1992PLC014332")
    garbled = clean + " l0,406.47 99S.08 (1,9S7) 3l.03.2025 763.S2"
    assert gate.text_is_garbled(garbled)
    assert not gate.text_is_garbled(clean + " l0,406.47 99S.08")  # two stray tokens are not a pattern


def test_a_rupee_amount_written_in_full_cannot_be_crore():
    """Shivam Autotech's 299,99,99,852 (rupees) was written "₹2,99,99,99,852 Cr"."""
    assert gate.impossible_crore_amounts(["Raise ₹2,99,99,99,852 Cr via preference shares"]) == ["2,99,99,99,852"]
    assert gate.impossible_crore_amounts(["Revenue ₹18,137 Cr", "market cap ₹20,00,000 Cr"]) == []


def test_a_deal_size_equal_to_company_revenue_or_net_worth_is_not_a_deal():
    dossier = {"financial_metrics": [{"metric": "revenue", "period": "Q3FY25", "value": 951.96}],
               "balance_sheet": [{"period": "Q2FY25", "net_worth_cr": 1357.5}]}
    assert gate.deal_is_company_figure(951.9, dossier) == "revenue Q3FY25"
    assert gate.deal_is_company_figure(1357.5, dossier) == "net worth Q2FY25"
    assert gate.deal_is_company_figure(396.5, dossier) is None


def test_a_terminated_project_is_not_live():
    """Prism Johnson terminated its 24 MW captive wind project with ReNew."""
    assert gate.is_terminated("Prism Johnson terminates 24 MW captive wind power project with ReNew")
    assert gate.is_terminated("Withdrawal of the open offer")
    assert not gate.is_terminated("Prism Johnson wins ₹128 Cr tax refund")


def test_issue_size_must_follow_from_shares_and_price():
    """SML's open offer: 3,762,628 shares at ₹1,554.60 is ₹584.94 Cr, not ₹5,849 Cr or ₹58 Cr."""
    assert gate.issue_size_mismatch(584.94, 3_762_628, 1554.60) is None
    assert "₹5,849" in gate.issue_size_mismatch(5849.4, 3_762_628, 1554.60)
    assert gate.issue_size_mismatch(58.5, 3_762_628, 1554.60)
    assert gate.issue_size_mismatch(None, 3_762_628, 1554.60) is None  # nothing to compare is not a mismatch


def test_hold_list_parses_and_a_typo_stops_the_run(tmp_path):
    path = tmp_path / "card_holds.txt"
    path.write_text("# holds\n\nn-1 | EBITDA is PBT in the source table\nn-2|wrong column\n", encoding="utf-8")
    assert gate.load_holds(path) == {"n-1": "EBITDA is PBT in the source table", "n-2": "wrong column"}
    assert gate.load_holds(tmp_path / "missing.txt") == {}
    path.write_text("n-3 held without a reason\n", encoding="utf-8")
    with pytest.raises(ValueError, match="card_holds.txt:1"):
        gate.load_holds(path)


def test_a_held_card_is_published_marked_for_review_without_asking_a_second_model(settings):
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-hold", "Unaudited Financial Results for the quarter", now, "Result")
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]}, env={"NVIDIA_API_KEY": "n"})
    pipeline._holds = {"n-hold": "EBITDA is PBT in the source table"}
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    body = outcome.card["card"]
    assert len(fake.calls) == 1 and outcome.card["needs_review"] == 1
    assert body["review"] == {"status": "HELD", "issues": ["Held after review: EBITDA is PBT in the source table"]}


def test_a_garbled_scan_marks_the_card_for_review(settings):
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-scan", "Unaudited Financial Results for the quarter", now, "Result")
    noisy = RESULT_TEXT + " " + " ".join(f"{n:,}.{n % 100:02d}" for n in range(1000, 1300)) + " l0,406.47 99S.08 (1,9S7) 763.S2"
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(noisy)},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]}, env={"NVIDIA_API_KEY": "n"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    review = outcome.card["card"]["review"]
    assert outcome.card["needs_review"] == 1 and review["status"] == "HELD" and "garbled" in review["issues"][0]
    assert len(fake.calls) == 1  # a second model cannot repair a scan


NOVARTIS_SPA = (Path(__file__).parent / "fixtures" / "bse_novartis_spa_20260219.txt").read_text(encoding="utf-8")


def test_novartis_instrument_amount_is_not_the_deal_size():
    """Novartis India, 19 Feb 2026: the card said "70.68% stake sold for ₹660 Cr". ₹660.09 Cr (INR 660,09,25,235) is only
    what the seller subscribes to in instruments at Closing, set off against the price; it is in the filing, so the
    number check passed it. The consideration is the buyers' shares x price: ₹1,445.9 Cr."""
    problem = gate.deal_amount_context(660.09, NOVARTIS_SPA)
    assert problem and "not as the deal's consideration" in problem
    assert gate.deal_amount_context(1445.9, NOVARTIS_SPA) is None  # not in the text at all: nothing to say
    assert gate.deal_amount_context(660.09, "The consideration for the acquisition is INR 660,09,25,235.") is None
    assert gate.deal_amount_context(None, NOVARTIS_SPA) is None


def test_the_consideration_is_computed_from_each_buyers_shares_and_price():
    from bse_intel.models import ShareTranche

    tranches = [ShareTranche(party="WaveRise", shares=13_938_382, price_per_share=860.64),
                ShareTranche(party="ChrysCapital", shares=2_547_189, price_per_share=701.25),
                ShareTranche(party="Two Infinity", shares=965_109, price_per_share=701.25)]
    assert gate.tranche_total_cr(tranches, NOVARTIS_SPA) == 1445.89
    assert gate.tranche_total_cr([ShareTranche(shares=13_938_382, price_per_share=900.0)], NOVARTIS_SPA) is None  # a price not in the filing
    assert gate.tranche_total_cr([], NOVARTIS_SPA) is None


def test_a_card_with_the_wrong_deal_size_is_corrected_from_the_tranches(settings):
    from bse_intel.pipeline import apply_deal_guards
    from bse_intel.models import Pass2Output

    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "M_AND_A", "timeline_entry": "SPA signed",
        "card": {"impact_level": "HIGH", "headline": "Novartis AG sells 70.68% of Novartis India for ₹660 Cr", "what_happened": ["x"],
                 "deal_value": {"kind": "ACQUISITION", "amount_cr": 660.09, "stage": "CONTRACT", "tranches": [
                     {"party": "WaveRise", "shares": 13938382, "price_per_share": 860.64},
                     {"party": "ChrysCapital", "shares": 2547189, "price_per_share": 701.25},
                     {"party": "Two Infinity", "shares": 965109, "price_per_share": 701.25}]}}})
    filing = _filing("n-spa", "Disclosure under Regulation 30", now_ist(), "Company Update")
    notes = apply_deal_guards(out, filing, [], [], NOVARTIS_SPA)
    assert out.card.deal_value.amount_cr == 1445.89 and "shares x price" in notes[0]


def test_a_computed_deal_size_is_never_dropped_as_company_revenue():
    """SML Mahindra: shares x price gave ₹554.65 Cr, which sat 0.9% from Q2FY25 revenue of ₹549.71 Cr by chance."""
    assert gate.deal_is_company_figure(554.65, {"financial_metrics": [{"metric": "revenue", "period": "Q2FY25", "value": 549.71}]}) is None
    assert gate.deal_is_company_figure(549.8, {"financial_metrics": [{"metric": "revenue", "period": "Q2FY25", "value": 549.71}]}) == "revenue Q2FY25"


def test_a_quote_is_matched_through_pdf_spacing_and_smart_punctuation():
    text = ("Pursuant  to Regulation 30, the Board\nhas recommended a final dividend of Rs 5 per share\n"
            "for FY25, subject to approval of the members.")
    assert gate.quote_found("the Board has recommended a final dividend of Rs 5 per share", text)
    assert gate.quote_found("the Board has recommended ... subject to approval", text)  # joined passages, in order
    assert not gate.quote_found("the Board has recommended an interim dividend", text)
    assert not gate.quote_found("subject to approval ... the Board has recommended", text)  # out of order
    assert not gate.quote_found("", text) and not gate.quote_found("anything", "")


def test_a_fact_cannot_borrow_a_number_its_quote_does_not_have():
    quote = "Revenue from operations stood at Rs 951.96 crore for the quarter."
    assert gate.numbers_in_quote("Revenue ₹951.96 Cr", quote) == []
    assert gate.numbers_in_quote("Revenue ₹951.96 Cr, PAT ₹49.39 Cr", quote) == ["49.39"]
    assert gate.numbers_in_quote("Revenue ₹95 Cr", quote) == []  # a prefix of the quote's figure: rounding
    assert gate.numbers_in_quote("anything", "") == []


def test_a_fact_whose_quote_is_not_in_the_filing_is_dropped(settings):
    """The audit's largest class was invented facts (147 issues): "fixed-price, no escalation clause",
    "currency risk premium", "NCLT approvals". A fact now carries the filing's sentence, checked in code."""
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import check_quotes

    text = "The Board approved an order worth Rs 396.5 crore from Godrej Properties for residential construction."
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "ORDER_WIN", "timeline_entry": "order win",
        "card": {"impact_level": "MODERATE", "headline": "Order win", "what_happened": [
            {"text": "Order worth **₹396.5 Cr** from Godrej Properties", "quote": "an order worth Rs 396.5 crore from Godrej Properties"},
            {"text": "The contract is fixed-price with no escalation clause", "quote": "The contract is fixed-price with no escalation clause"},
            {"text": "Residential construction project", "quote": None}]}})
    problems, missing, dropped, paraphrased = check_quotes(out, text)
    assert [f.text for f in out.card.what_happened] == ["Order worth **₹396.5 Cr** from Godrej Properties",
                                                        "Residential construction project"]
    assert any("neither its quote nor its figures" in p for p in problems) and missing == ["Residential construction project"]
    assert dropped == ['"The contract is fixed-price with no escalation clause" (neither its quote nor its figures are in the filing)']


def test_a_card_whose_every_quote_fails_is_kept_and_marked(settings):
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import check_quotes

    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "OTHER", "timeline_entry": "x",
        "card": {"impact_level": "LOW", "headline": "Company files an update with the exchange",
                 "what_happened": [{"text": "invented", "quote": "not in the filing"}]}})
    problems, _, _, paraphrased = check_quotes(out, "The filing says something else entirely.")
    assert len(out.card.what_happened) == 1  # never an empty card
    assert any("no fact carries a quote" in p for p in problems)


def test_a_true_fact_composed_from_a_table_is_kept_not_dropped(settings):
    """SML Isuzu's "Q3FY25 PAT ₹0.53 Cr, down 80% YoY and 98% QoQ" is right, but no single sentence says
    it: the figures come from a results table. Dropping it would delete a true fact, so a fact whose
    figures are all in the filing is kept and reported for the second opinion to quote properly."""
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import check_quotes

    text = "Profit for the period 0.53 2.68 21.80 ... Revenue from operations 331.80 386.13 549.71"
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "results",
        "card": {"impact_level": "MODERATE", "headline": "SML Isuzu Q3FY25 revenue falls to ₹331.8 Cr",
                 "what_happened": [{"text": "Q3FY25 revenue ₹331.80 Cr against ₹386.13 Cr a year earlier",
                                    "quote": "Revenue fell to Rs 331.80 crore from Rs 386.13 crore"},
                                   {"text": "An invented ₹9,999 Cr provision", "quote": "no such sentence"}]}})
    problems, _, _, paraphrased = check_quotes(out, text)
    assert [f.text for f in out.card.what_happened] == ["Q3FY25 revenue ₹331.80 Cr against ₹386.13 Cr a year earlier"]
    assert any("is in the filing but its quote is not" in p for p in paraphrased),         "every figure verified, only the wording is the model's: reported, but not a reason to hold"
    assert any("neither its quote nor its figures" in p for p in problems)          # dropped


def test_a_quoted_row_is_read_at_the_filings_own_unit():
    """An Indian statement prints lakh and a card writes crore, so the right reading was reported as a
    figure the quote does not carry - on 2026-10-17 the commonest single reason a card was held back.
    Dividing by the unit the filing declares keeps the check that matters: the ten-times misreading of
    the same row is still refused."""
    row = "Provisions (other than tax) and contingencies 1,653 (454)"
    assert gate.numbers_in_quote("Provisions rose to ₹16.53 Cr in Q3FY25 from ₹-4.54 Cr in Q3FY24", row, 100) == []
    assert gate.numbers_in_quote("Provisions rose to ₹88.40 Cr in Q3FY25", row, 100) == ["88.40"],         "a figure the row does not carry at any unit still shows"

    million = "Finance costs 457.86"
    assert gate.numbers_in_quote("Finance cost ₹45.79 Cr", million, 10) == []
    assert gate.numbers_in_quote("Finance cost ₹458 Cr", million, 10) == ["458"], "the 10x misreading"
    # with no unit declared the old digit rule stands, so nothing is let through that was not before
    assert gate.numbers_in_quote("Finance cost ₹45.79 Cr", million) == ["45.79"]


def test_a_period_label_and_a_percentage_are_not_figures_a_quote_must_carry():
    """A row prints the two amounts, not the year in the label nor the change between them."""
    row = "Revenue from operations 35,627 33,517"
    assert gate.numbers_in_quote("FY25 revenue ₹356.27 Cr grew 6.3% YoY from FY24", row, 100) == []
    assert gate.numbers_in_quote("March 2025 cargo sales were 594 units, down 0.8% YoY",
                                 "Cargo vehicles 594 599") == []
    assert gate.numbers_in_quote("FY25 revenue ₹402 Cr", row, 100) == ["402"], "an invented figure still shows"


def test_the_unit_is_read_from_the_filing_not_from_the_table_put_in_front_of_it():
    """The XBRL table is prepended to the text the model reads and states crore itself, so the filing's
    own "(Rs. in lakhs)" and the table's crore disagreed and no unit was found at all - for every
    filing that has an XBRL file, which is where the conversion was needed most."""
    from bse_intel.grounding import declared_unit

    filing = "Statement of unaudited results (Rs. in lakhs). Provisions and contingencies 1,653 (454)"
    table = "Machine-tagged results (XBRL, STANDALONE, ₹ crore unless noted):\n- pat Q3FY25: 151.63 Cr\n"
    assert declared_unit(filing) == 100
    assert declared_unit(table + "\n\n" + filing) is None, "the two declarations disagree"
    claim = "Provisions rose to ₹16.53 Cr in Q3FY25 from a write-back of ₹4.54 Cr in Q3FY24"
    row = "8. Provisions (other than tax) and Contingencies 1,653 1,391 (454) 5,050 (313) 1,848"
    assert gate.numbers_in_quote(claim, row, declared_unit(filing)) == []
    assert gate.numbers_in_quote(claim, row, declared_unit(table + filing)) == ["16.53", "4.54"], \
        "what the card was held for before the unit came from the document alone"


def test_a_day_of_the_month_is_not_a_figure_the_quote_must_carry():
    assert gate.numbers_in_quote("GNPA stood at 1.58% as of December 31, 2024, up from 1.22%",
                                 "b) % of Gross NPAs 1.58% 1.68% 1.22%") == []


def test_an_amount_written_out_in_full_and_a_change_in_basis_points():
    """Two things a quoted line carries without printing the card's own digits.

    A notice writes the amount in rupees in Indian grouping ("Rs.50,10,05,632") where the card writes
    Rs 50.10 Cr; and a change in a ratio is in basis points, which is a difference between two figures
    the line does print, not a figure of its own."""
    notice = "Show Cause Notice for Tax liability of Rs.50,10,05,632 and penalty of Rs.50,10,05,632"
    assert gate.numbers_in_quote("Tax liability ₹50.10 Cr", notice) == []
    assert gate.numbers_in_quote("Tax liability ₹73.40 Cr", notice) == ["73.40"]
    assert gate.numbers_in_quote("GNPA 1.58%, +36 bps YoY", "b) % of Gross NPAs 1.58% 1.68% 1.22%") == []
    assert gate.numbers_in_quote("Margin 9.78%, up 56 basis points", "ebitda_margin FY25: 9.78 %") == []
