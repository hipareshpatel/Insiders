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
    assert gate.numbers_in_quote("Revenue ₹952 Cr", quote) == []  # rounded to the card's last digit
    # a prefix of the quote's figure used to pass as a "rounding": ₹95 Cr is a tenth of ₹951.96 Cr
    assert gate.numbers_in_quote("Revenue ₹95 Cr", quote) == ["95"]
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
    assert dropped == ['"The contract is fixed-price with no escalation clause" (neither its quote nor its figures are in '
                       'the filing; quoted: "The contract is fixed-price with no escalation clause")']


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


def test_a_written_date_is_not_a_figure_a_quote_must_carry():
    """"Order received on 16.12.2025" was held as stating 16.12: the year was taken off as a period label and
    the day and month were left as an amount with two decimals (SML Mahindra's ROC order, 2026-10-18)."""
    quote = "The order was received by the Company on 16th December, 2025; there is no financial impact."
    assert gate.numbers_in_quote("Order received on 16.12.2025; no financial impact on the company", quote) == []
    assert gate.numbers_in_quote("Hearing on 05/01/26 and 07-02-2026", "The hearing is listed for January.") == []
    assert gate.numbers_in_quote("Penalty of ₹16.12 Cr", quote) == ["16.12"], "an amount is still a figure"


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


def test_a_sibling_row_answers_for_a_sentence_but_not_for_a_labelled_figure():
    """A sentence reports the row it quotes and leans on others around it, so a figure from a sibling
    row of the same table is reported rather than held. A key number names one line and states its
    figure, so there the row itself has to carry it - which is what keeps "Rs 458 Cr" quoting a row of
    457.86 million a failure even though 4,583 million is printed a few rows below."""
    text = ("Statement of unaudited results (Rs. in lakhs) Revenue from operations 35,627 33,517 "
            "Other income 1,200 900 Profit for the period 10,090 8,520")
    quote = "Revenue from operations 35,627 33,517"
    missing = gate.numbers_in_quote("FY25 revenue ₹356.27 Cr and PAT ₹100.90 Cr", quote, 100)
    assert missing == ["100.90"], "the profit row is not in the revenue row"
    assert gate.figures_in_same_block(missing, quote, text, 100) == ([], ["100.90"]), \
        "but it is in the same table, so it is reported, not held"

    far = " filler" * 900 + " Exceptional items 9,999 0"
    assert gate.figures_in_same_block(["99.99"], quote, text + far, 100) == (["99.99"], []), \
        "a figure a thousand words away is not a sibling row"


def test_results_figures_that_do_not_add_up_are_reported():
    """A statement adds up by construction, so a reading of it that does not has misread a line - and
    that needs no second document to see. The three identities held on all 737 checks of 277 known-good
    XBRL files; these are the misreadings they exist for."""
    from bse_intel.models import FinancialMetric

    def figures(**kw):
        return [FinancialMetric(metric=k, period="Q2FY27", value=v, unit="INR_CR") for k, v in kw.items()]

    right = figures(revenue=1821.70, other_income=9.20, total_income=1830.90, total_expenses=1700.10,
                    pbt=130.80, tax_expense=30.10, pat=100.70)
    assert gate.statement_footing(right) == []
    # rounding: each printed line is rounded on its own
    assert gate.statement_footing(figures(revenue=331.80, other_income=0.41, total_income=332.20)) == []
    # a lakh read as crore on one line
    slip = figures(revenue=1821.70, other_income=920.0, total_income=1830.90)
    assert gate.statement_footing(slip) and "other income 920.00" in gate.statement_footing(slip)[0]
    # last year's column read for one line
    column = figures(pbt=130.80, tax_expense=30.10, pat=88.40)
    assert gate.statement_footing(column) and "PAT is given as 88.40" in gate.statement_footing(column)[0]
    # an exceptional item, either sign convention
    assert gate.statement_footing(figures(total_income=500.0, total_expenses=420.0, exceptional_items=30.0, pbt=50.0)) == []
    assert gate.statement_footing(figures(total_income=500.0, total_expenses=420.0, exceptional_items=-30.0, pbt=50.0)) == []
    # discontinued operations: PAT for the period includes them, the identity is on the continuing part
    assert gate.statement_footing(figures(pbt=-2.0, tax_expense=0.24, pat_continuing=-2.24, pat=91.81)) == []
    # names a reply may use
    assert gate.statement_footing([FinancialMetric(metric="profit_before_tax", period="FY25", value=10.0),
                                   FinancialMetric(metric="tax", period="FY25", value=2.0),
                                   FinancialMetric(metric="net_profit", period="FY25", value=9.0)])


def test_a_quote_from_a_two_column_page_is_found_in_its_block_reading():
    """SML's share purchase disclosure is a table: the label cell "Significant terms of the agreement (in
    brief)" beside a paragraph cell. Read line by line, the label's words land inside the paragraph's
    sentence, so the sentence the model quoted was "not in the filing" (loop rounds 3a-3b, 2026-10-17). Read
    block by block, the cell is whole. Nothing is skipped to make a quote fit: it is still one reading's own
    words, contiguous."""
    import pymupdf

    from bse_intel.extract import Document

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_textbox(pymupdf.Rect(60, 100, 200, 160), "5. Significant terms of the agreement (in brief).", fontsize=10)
    page.insert_textbox(pymupdf.Rect(230, 100, 540, 200),
                        "The sale of all of SPA 1 Sale Shares from the Seller 1 to the Purchaser under the SPA 1 is "
                        "for an aggregate consideration of Rs. 4,135,498,900/-, subject to adjustments.", fontsize=10)
    doc = Document(pdf.tobytes())
    lines, blocks = doc.select_text(10_000), doc.block_text(doc.selected)
    quote = ("The sale of all of SPA 1 Sale Shares from the Seller 1 to the Purchaser under the SPA 1 is for an "
             "aggregate consideration of Rs. 4,135,498,900/-")
    assert not gate.quote_found(quote, lines), "the line reading runs the two cells together"
    assert gate.quote_found(quote, lines, blocks)
    assert not gate.quote_found("The sale of all of SPA 1 Sale Shares to the Purchaser", lines, blocks), \
        "words left out of the cell are still not the filing's words"
    assert Document.from_cache(doc.to_cache()).block_text([0]) == blocks


def test_a_quote_may_leave_words_out_with_an_elision_mark():
    text = "Direct SPA - The Acquirers have entered into a SPA dated February 19, 2026 with the Seller for a total consideration of INR 1445 Cr."
    assert gate.quote_found("Direct SPA - The Acquirers have entered into a SPA [...] total consideration of INR 1445 Cr", text)
    assert gate.quote_found("The Acquirers have entered into a SPA … with the Seller", text)
    assert not gate.quote_found("The Acquirers have entered into a SPA [...] with the Buyer", text)
    assert not gate.quote_found("[...]", text)


def test_a_quote_with_a_word_dropped_is_the_filings_sentence_unless_the_word_turns_it():
    """Novartis's quote "...Twenty Eight Thousand Fifty Six" of the PDF's "...Twenty Eight Thousand and Fifty
    Six", and SML's "Lakhs" for "Lakh", held their cards out of the feed as quotes "not in the filing" with
    every figure right (loop round 3a). At least nine words in ten in order in one place is the filing's own
    sentence - but not when the word that differs is "not", "subject" or "only"."""
    text = ("The Maximum Consideration, i.e., total funding requirement for the Open Offer, assuming full acceptance "
            "of the Offer, is INR 584,93,81,488.80 (Indian Rupees Five Hundred Eighty Four Crore Ninety Three Lakh "
            "Eighty One Thousand Four Hundred Eighty Eight only). The Board has not approved the proposed merger "
            "of the two subsidiaries with the Company at its meeting held today.")
    near = gate.quote_near("aggregating to a total consideration of up to INR 584,93,81,488.80 (Indian Rupees Five "
                           "Hundred Eighty Four Crore Ninety Three Lakhs Eighty One Thousand Four Hundred Eighty Eight",
                           text)
    assert near is None, "the opening words are not the filing's: no place to anchor"
    near = gate.quote_near("is INR 584,93,81,488.80 (Indian Rupees Five Hundred Eighty Four Crore Ninety Three Lakhs "
                           "Eighty One Thousand Four Hundred Eighty Eight only)", text)
    assert near and "584,93,81,488.80" in near and "lakh eighty" in near
    assert gate.quote_near("The Board has approved the proposed merger of the two subsidiaries with the Company at "
                           "its meeting held today.", text) is None, "a dropped 'not' turns the sentence round"
    assert gate.quote_near("Board has not approved", text) is None, "too short to judge by"

    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import check_quoted_numbers

    card = Pass2Output.model_validate({
        "is_material": True, "event_type": "M_AND_A", "timeline_entry": "Open offer",
        "card": {"impact_level": "HIGH", "headline": "Open offer",
                 "what_happened": [{"text": "Open offer made", "quote": "total funding requirement for the Open Offer"}],
                 "key_numbers": [{"label": "Maximum consideration", "value": "₹584.94 Cr", "quote":
                                  "is INR 584,93,81,488.80 (Indian Rupees Five Hundred Eighty Four Crore Ninety Three "
                                  "Lakhs Eighty One Thousand Four Hundred Eighty Eight only)"}]}})
    problems, _, style = check_quoted_numbers(card, text)
    assert problems == [] and style == ['key number "Maximum consideration" quotes the filing with small differences']
    card.card.key_numbers[0].value = "₹585.94 Cr"
    assert "585.94" in check_quoted_numbers(card, text)[0][0], "the figure still answers to that one sentence"


def test_what_may_differ_in_a_near_quote_is_wording_not_figures():
    text = ("Pursuant to the approval, 92,72,997 equity shares of face value Rs. 2 each were allotted to the holders "
            "of the compulsorily convertible debentures on conversion at a price of Rs. 26.96 per share.")
    assert gate.quote_near("Pursuant to the approval, 9272997 equity shares of face value ₹ 2 each were allotted to "
                           "the holders of the debentures on conversion", text), "the same number, a rupee sign"
    assert gate.quote_near("Pursuant to the approval, 92,72,997 equity shares of face value Rs. 2 each were allotted to "
                           "the holders of the compulsorily convertible debentures on conversion at a price of "
                           "Rs. 29.96 per share.", text) is None, "a figure that differs is not wording"
    assert gate.quote_near("Pursuant to the approval, 92,72,997 equity shares were allotted at a price of Rs. 26.96 "
                           "per share.", text) is None, "too much of the sentence left out without a mark"


def test_a_figure_from_a_sibling_row_must_be_at_the_right_unit():
    """Jubilant's FY25 card wrote "exceptional items of ₹3,595 Cr" from a statement in ₹ million, where (3,595)
    is ₹359.5 Cr. The sibling-row rule matched the digits 3,595 and let the ten-times figure pass as "from
    another row of the same table" (loop round 3c, 2026-10-18)."""
    text = ("(₹ in million) Particulars FY25 FY24\nProfit for the year 8,363 727\nExceptional items (3,595) 1,689\n"
            "Total comprehensive income 8,101 690")
    claim = "FY25 PAT rose to ₹836.3 Cr due to exceptional items of ₹3,595 Cr"
    still, siblings = gate.figures_in_same_block(["3,595"], "Profit for the year 8,363 727", text, 10, claim)
    assert still == ["3,595"] and siblings == []
    right = "FY25 PAT rose to ₹836.3 Cr due to exceptional items of ₹359.5 Cr"
    assert gate.figures_in_same_block(["359.5"], "Profit for the year 8,363 727", text, 10, right) == ([], ["359.5"])


def test_a_card_amount_is_compared_in_crore_whatever_digits_it_shares():
    """The same digits used to pass whatever the unit: Novartis's FY25 cards wrote employee cost ₹187.2 Cr and
    operating cash flow ₹745.7 Cr from a statement in ₹ million (₹18.72 Cr, ₹74.57 Cr), CSB's gross NPA ₹45,817 Cr
    from one in lakh (₹458.17 Cr), and each passed its own quote (loop rounds 2a-3c, 2026-10-18)."""
    assert gate.numbers_in_quote("₹187.2 Cr (Mar-2025)", "Employee Benefits Expense 187.2 229.6", 10) == ["187.2"]
    assert gate.numbers_in_quote("₹18.72 Cr (Mar-2025)", "Employee Benefits Expense 187.2 229.6", 10) == []
    assert gate.numbers_in_quote("₹45,817 Cr", "a) Gross NPAs 45,817 45,212 27,873", 100) == ["45,817"]
    # the XBRL table's balance-sheet line names its unit: "net_debt_cr 1348.6" is crore, whatever the filing's
    line = "balance sheet Q4FY25: gross_debt_cr 2436.9, cash_cr 1088.3, net_debt_cr 1348.6, net_worth_cr 6254.9"
    assert gate.numbers_in_quote("₹1,348.6 Cr net debt (Q4FY25)", line, 10) == []
    assert gate.numbers_in_quote("₹134.86 Cr net debt (Q4FY25)", line, 10) == ["134.86"]
    # a figure without a unit is compared as printed
    assert gate.numbers_in_quote("₹52.99 per share", "Basic EPS 52.99 4.87", 10) == []


def test_a_hold_is_kept_on_the_card_when_a_second_opinion_ran(settings):
    """The second opinion's review block replaced the hold reasons, so an owner's hold or a garbled scan left no trace
    on a card that also went to a second model (audit of discard paths, 2026-10-18)."""
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-hold2", "Unaudited Financial Results for the quarter", now, "Result")
    bad = json.loads(json.dumps(PASS2))
    bad["card"]["what_happened"] = ["Revenue ₹120 Cr vs ₹90.9 Cr a year ago", "PAT ₹17.5 Cr"]  # PAT was ₹15 Cr
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(bad)], "glm-4.5-flash": [json.dumps(bad)]},
                                 env={"NVIDIA_API_KEY": "n", "ZAI_API_KEY": "z"})
    pipeline._holds = {"n-hold2": "EBITDA is PBT in the source table"}
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    review = outcome.card["card"]["review"]
    assert review["status"] in ("UNRESOLVED", "CORRECTED") and len(fake.calls) == 2
    assert review["held"] == ["Held after review: EBITDA is PBT in the source table"]


def test_a_quote_is_read_as_printed_rounded_truncated_or_in_its_own_currency():
    """Right cards held in the re-run of the held cards (2026-10-18), and the misreadings that must still fail."""
    # a presentation rounds what the XBRL file states exactly (Jubilant's tagged ₹2,122.50 Cr)
    assert gate.numbers_in_quote("Revenue: ₹2,122.50 Cr +17% YoY", "Revenue 1,822 1,966 2,123 17% 5,306 5,990 13%") == []
    assert gate.numbers_in_quote("₹23.4 Cr", "Revenue from operations 23 2,83,791.74", 100) == ["23.4"], "a note number is no rounding"
    # a card cuts at its last digit: "₹554 Cr" of ₹554.65 Cr, "₹79 Cr" of 796 million
    assert gate.numbers_in_quote("The block is worth ₹554 Cr", "aggregate consideration of Rs. 554.65 crore") == []
    assert gate.numbers_in_quote("Dividend payout of ₹79 Cr", "a dividend amounting to 796 million") == []
    assert gate.numbers_in_quote("The block is worth ₹553 Cr", "aggregate consideration of Rs. 554.65 crore") == ["553"]
    assert gate.numbers_in_quote("₹458 Cr", "Revenue 457.86 million") == ["458"], "the ten-times misreading still fails"
    # OCR's decimal comma, a press release's spaced thousands, and an amount in euros
    assert gate.numbers_in_quote("Contract Work carried ₹950 Cr", "a) Contract Work 95028,10 100816.13", 100) == []
    assert gate.numbers_in_quote("debt free with ₹188.6 Cr cash", "cash and cash equivalents of INR 1 885.6 million") == []
    assert gate.numbers_in_quote("Cryptas has EUR 9.7 million revenue", "out of EUR 9.7 trust will be around EUR 1.8") == []


def test_a_quote_is_read_in_the_unit_its_own_page_declares():
    """An annual report or a deck declares several units, so the document as a whole has none, while the page a
    quote comes from does: SML's FY26 revenue "2,83,791.74" under "(₹ in lakhs)", Heritage's EBITDA "739" under
    "(Rs. In Mn.)" (2026-10-18)."""
    text = ("--- Page 3 of 9 ---\nStandalone statement (₹ in lakhs)\nRevenue from operations 23 2,83,791.74 2,39,899.28\n"
            "--- Page 4 of 9 ---\nNotes (₹ in crore)\nContingent liabilities 12.5\n"
            "--- Page 5 of 9 ---\nQ1 FY26 Performance (Rs. In Mn.)\nEBITDA 739 836 (21)%")
    revenue = "Revenue from operations 23 2,83,791.74 2,39,899.28"
    assert gate.quote_unit(revenue, text, None) == 100
    assert gate.numbers_in_quote("FY26 revenue was ₹2,838 Cr", revenue, gate.quote_unit(revenue, text, None)) == []
    assert gate.numbers_in_quote("FY26 revenue was ₹2,838 Cr", revenue, None) == ["2,838"], "without it, held"
    assert gate.quote_unit("EBITDA 739 836 (21)%", text, None) == 10
    assert gate.numbers_in_quote("EBITDA fell 21% to ₹73.9 Cr", "EBITDA 739 836 (21)%", 10) == []
    assert gate.quote_unit("Contingent liabilities 12.5", text, 100) == 1
    assert gate.quote_unit("a sentence not in the text at all", text, 100) == 100


def test_a_figure_a_fact_compares_with_may_come_from_memory():
    """"5.1% of the ₹7,794 Cr order book" quoting Ahluwalia's order letter, "₹19.88 Cr vs -₹0.44 Cr YoY" quoting the
    XBRL line: the comparison is the company's known figure, in memory or the scale block. A figure the fact does
    not mark as its comparison stays its quote's to carry, since a wrong period's figure is in memory too."""
    memory = '{"metrics": {"ebitda": ["Q3FY25: -0.44 INR_CR", "Q2FY26: 845.89 INR_CR"]}}\n- order book ₹7,794 Cr (Sep-2025)'
    assert gate.compared_figures(["7,794"], "Share of order book: 5.1% of ₹7,794 Cr", memory, "") == ["7,794"]
    assert gate.compared_figures(["0.44"], "EBITDA: ₹19.88 Cr vs -₹0.44 Cr YoY", memory, "") == ["0.44"]
    assert gate.compared_figures(["845.89"], "Revenue of ₹845.89 Cr in Q3FY26", memory, "") == []
    assert gate.compared_figures(["7,795"], "5.1% of ₹7,795 Cr", memory, "") == [], "not memory's figure"
    # or the filing states it to two decimals: Shivam's loss "narrowed from ₹50.19 Cr"
    assert gate.compared_figures(["50.19"], "PAT: -₹48.04 Cr loss narrowed from ₹50.19 Cr", "",
                                 "a loss of Rs. 5,019.20 lakhs in the previous year", 100) == ["50.19"]


BANDHAN_Q2FY27 = """Particulars September June YoY QoQ
30,2026 30, 2025 30, 2026 (%) (%)
Loans & Advances (On book + PTC) 140,041 155,555 158,335 13.1% 1.8%
Total Deposits 158,075 164,886 172,689 9.2% 4.7%
CASA Deposits 44,211 48,479 46,131 4.3% (4.8)%
Retail to Total Deposits (%) 70.93% 73.96% 72.66%
CASA Ratio (%) 27.97% 29.40% 26.71%
"""


def test_bandhan_the_latest_column_comes_from_the_tables_own_changes():
    """36024ce2: garbled headers; the card read the first column (September 2025) as September 2026 and called a
    13.1% rise in advances a 13.1% fall. The YoY and QoQ columns show the third column is the latest."""
    latest, stale = gate.table_columns(BANDHAN_Q2FY27)
    assert {158335.0, 172689.0, 46131.0, 26.71} <= latest and {140041.0, 158075.0, 27.97} <= stale
    problems = gate.stale_columns(["Loans & advances fell 13.1% YoY to ₹1,40,041 Cr; CASA ratio 27.97%"], BANDHAN_Q2FY27)
    assert len(problems) == 2 and "1,40,041" in problems[0]
    # the right reading, with its year-ago comparison, raises nothing
    assert gate.stale_columns(["Advances rose 13.1% to ₹1,58,335 Cr from ₹1,40,041 Cr; CASA ratio 26.71%"],
                              BANDHAN_Q2FY27) == []


def test_bandhan_memory_refuses_the_year_old_column():
    from bse_intel.trust import Checker

    check = Checker(BANDHAN_Q2FY27, {"market_cap_cr": 27000}, {})
    assert check.printed_crore(158335) and not check.printed_crore(140041)
