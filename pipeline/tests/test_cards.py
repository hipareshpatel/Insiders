"""Card quality checks, using wording from real BSE filings (public disclosures).

Each case comes from a published card that went wrong or right: a generic headline,
an order called the "first" when the filing says "second", Indian digit grouping,
₹ million figures, GST-inclusive order values and repeat orders.
"""

from __future__ import annotations

import os

import pytest

from bse_intel.dossier import merge, new_dossier, view_as_of
from bse_intel.grounding import check_card, check_claims
from bse_intel.models import Card, Filing, Pass2Output
from bse_intel.pipeline import reconcile_call_read
from bse_intel.signals import compute


def card(**fields) -> Card:
    return Card.model_validate({"impact_level": "MODERATE", "what_happened": ["x"], **fields})


def filing(news_id: str, filed_at: str) -> Filing:
    return Filing(news_id=news_id, scrip_code="999007", company_name="Demo Infra Ltd", headline="h",
                  filed_at=filed_at, filing_date=filed_at[:10])


def order(amount, *, gst=None, headline="Demo Infra wins wind EPC order", **deal) -> Pass2Output:
    return Pass2Output.model_validate({
        "is_material": True, "event_type": "ORDER_WIN", "timeline_entry": headline,
        "card": {"impact_level": "MODERATE", "headline": headline, "what_happened": ["x"],
                 "deal_value": {"kind": "ORDER", "amount_cr": amount, "includes_gst": gst, "stage": "LOI", **deal}},
    })


@pytest.mark.parametrize("headline", [
    "Tata Technologies posts a key update",
    "Mangalore Refinery And Petrochemicals posts a key update",
    "Demo Ltd announces business update",
])
def test_generic_headlines_are_rejected(headline):
    with pytest.raises(ValueError, match="generic"):
        card(headline=headline)


def test_specific_headlines_pass():
    assert card(headline="Om Power wins ₹102 Cr Gujarat order, nearly its last quarter sales").headline
    assert card(headline="Board approves update to the dividend distribution policy").headline


PTC = ("Aerolloy Technologies Limited, a wholly owned subsidiary of PTC Industries Limited, today announced that it has "
       "been selected by Safran Aircraft Engines for the development and manufacture of critical Titanium cast components. "
       "This represents the second set of orders received by Aerolloy Technologies from Safran Aircraft Engines for "
       "titanium castings under the LEAP engine programme. We kindly request you to take the above on record.")


def test_first_order_claim_loses_to_the_filing_saying_second():
    c = card(headline="PTC Industries unit wins Safran order for LEAP engine titanium parts",
             why_it_matters=["This is the company's first order from Safran on record, adding to aerospace wins."])
    assert check_claims(c, PTC) == ["This is the company's first order from Safran on record"]


def test_record_claims_need_matching_wording_in_the_sources():
    landmark = ("The Company recorded its highest-ever quarterly and half-yearly Total Revenue from Operations on a "
                "proforma basis. We request you to take the same on record.")
    ok = card(headline="Landmark Cars posts record quarterly revenue of ₹1,943 Cr",
              what_happened=["Highest-ever quarterly proforma revenue of **₹1,943 Cr** in the first half"])
    assert check_claims(ok, landmark) == []
    bad = card(headline="Landmark Cars Q2 proforma revenue rose 17.3% YoY to ₹1,943 Cr",
               why_it_matters=["Record EBITDA margin as well"])
    assert check_claims(bad, landmark) == ["Record EBITDA margin as well"]  # "on record" is not a record


def test_first_as_a_reference_is_not_a_claim():
    c = card(headline="Demo Infra arm bags ₹207 Cr wind EPC work order",
             why_it_matters=["Second wind EPC order since May and larger than the first (₹142 Cr).",
                             "The first of three phases is due in March."])
    assert check_claims(c, "Work order for EPC works for a 70 MW wind project.") == []


def test_an_unrelated_first_does_not_excuse_a_first_claim():
    mrpl = "The Board has declared the first interim dividend of Rs 3 per equity share (30%)."
    c = card(headline="MRPL Q2 PAT tripled to ₹1,901 Cr; first interim dividend of ₹3",
             why_it_matters=["It also secured its first-ever international credit rating."])
    assert check_claims(c, mrpl) == ["It also secured its first-ever international credit rating"]
    fitch = "Fitch has assigned the company its first international credit rating of BBB- (Stable)."
    assert check_claims(c, mrpl, fitch) == []


def test_grounding_reads_indian_digit_grouping_and_millions():
    cubex = ("Raising of funds aggregating up to Rs. 75,00,00,000 by issuing up to 50,00,000 Convertible Warrants "
             "at an issue price of Rs. 150/- per security, including a premium of Rs. 140/-.")
    c = card(headline="Cubex Tubings approves ₹75 Cr warrant issue at ₹150 per share",
             what_happened=["Approved **50 lakh** convertible warrants at **₹150** each to raise **₹75 Cr**"],
             deal_value={"kind": "FUNDRAISE", "amount_cr": 75, "stage": "BOARD_APPROVED"})
    assert check_card(c, cubex).ungrounded == []

    tatatech = ("Total Company Operating Revenue stood at ₹16,988 million, up +28.4% YoY. Operating EBITDA at ₹2,733 "
                "million, up +31.5% YoY. EBITDA margin up +40bps YoY at 16.1%. Net Income was at ₹1,714 million vs. "
                "₹1,655 million in Q2 FY26.")
    c = card(headline="Tata Technologies Q2 revenue rose 28.4% YoY to ₹1,699 Cr; margin up 40 bps to 16.1%",
             what_happened=["Net income rose only **3.6%** to ₹171 Cr while EBITDA grew 31.5% to ₹273 Cr"])
    result = check_card(c, tatatech)
    assert result.ungrounded == [] and result.checked >= 6


def test_scale_signal_flags_gst_inclusive_order_values():
    d = new_dossier(filing("n1", "2026-08-10T17:00:00+05:30"))
    d["financial_metrics"] = [
        {"metric": "revenue", "period": "Q1FY27", "value": 122.0, "unit": "INR_CR", "as_of": "2026-08-10T17:00:00+05:30"},
        {"metric": "revenue", "period": "FY26", "value": 440.0, "unit": "INR_CR", "as_of": "2026-05-20T17:00:00+05:30"},
    ]
    out = order("₹101.56 Cr", gst="including", headline="Demo Power wins ₹102 Cr underground cabling LOA")
    f = filing("n2", "2026-10-14T18:30:00+05:30")
    signals = compute(d, merge(d, out, f, "HIGH", "now"), out, f, {"market_cap_cr": 563})
    scale = next(s for s in signals if s["type"] == "SCALE")
    assert scale["text"] == ("₹101.56 Cr order = 83% of Q1FY27 revenue (₹122 Cr), 23% of FY26 revenue (₹440 Cr); "
                             "the value includes GST, revenue does not.")


def test_order_flow_counts_repeat_orders_and_the_largest():
    d = new_dossier(filing("n0", "2026-05-01T10:00:00+05:30"))
    for news_id, when, amount in (("n1", "2026-05-15T18:00:00+05:30", 142), ("n2", "2026-08-02T18:00:00+05:30", 207.47)):
        out = order(amount)
        d = merge(d, out, filing(news_id, when), "MODERATE", "now")
    assert [x["amount_cr"] for x in d["deals"]] == [142, 207.47]
    view = view_as_of(d, "2026-10-14T00:00:00+05:30")
    assert view["deals"][-1] == {"id": d["deals"][-1]["id"], "date": "2026-08-02", "kind": "ORDER", "amount_cr": 207.47, "stage": "LOI"}

    out = order(228, segment="wind EPC")
    f = filing("n3", "2026-10-14T18:00:00+05:30")
    after = merge(d, out, f, "MODERATE", "now")
    flow = next(s for s in compute(d, after, out, f, None) if s["type"] == "ORDER_FLOW")
    assert flow["text"] == ("3rd order on record since 2026-05-15 (₹577.47 Cr in total); "
                            "the largest so far (previous high ₹207.47 Cr on 2026-08-02).")
    assert len(merge(after, out, f, "MODERATE", "now")["deals"]) == 3  # re-analysis replaces, never duplicates


def test_no_order_flow_signal_without_earlier_orders():
    d = new_dossier(filing("n0", "2026-05-01T10:00:00+05:30"))
    out = order(228)
    f = filing("n1", "2026-10-14T18:00:00+05:30")
    assert not [s for s in compute(d, merge(d, out, f, "MODERATE", "now"), out, f, None) if s["type"] == "ORDER_FLOW"]


def test_call_read_guidance_needs_earlier_guidance_in_memory():
    c = card(headline="Demo Finance keeps FY27 credit growth guidance at 11-12%",
             call_read={"guidance": "same as last call", "management_tone": "confident", "transparency": "moderate"})
    assert (c.call_read.guidance, c.call_read.management_tone, c.call_read.transparency) == ("MAINTAINED", "OPTIMISTIC", "MEDIUM")
    reconcile_call_read(c, {"metrics": {}})
    assert c.call_read.guidance == "NEW"
    c.call_read.guidance = "LOWERED"
    reconcile_call_read(c, {"guidance": [{"id": "g_1", "statement": "FY27 PAT growth 30-35%"}]})
    assert c.call_read.guidance == "LOWERED"


def test_card_extras_are_normalised():
    c = card(headline="Demo Infra arm wins ₹186 Cr wind EPC LOI", themes=["Renewables", "renewables", "Infra / EPC", "Power"],
             basis="consolidated", deal_value={"kind": "contract", "amount_cr": "186", "stage": "Letter of Intent"})
    assert c.themes == ["Renewables", "Infra / EPC"] and c.basis == "CONSOLIDATED"
    assert (c.deal_value.kind, c.deal_value.stage) == ("ORDER", "LOI")
    assert card(headline="Routine update for the quarter", deal_value={}, call_read={}).deal_value is None
    # an optional block with missing or odd fields never sinks the card
    partial = card(headline="Demo Infra wins ₹50 Cr road order", deal_value={"amount_cr": "50"}, call_read={"story": "rocket"})
    assert (partial.deal_value.kind, partial.deal_value.amount_cr, partial.call_read.story) == ("OTHER", 50.0, None)


def test_a_later_stage_updates_the_deal_instead_of_adding_one():
    """LOI first, formal contract later: one order with a stage history, never two orders."""
    d = new_dossier(filing("n0", "2026-05-01T10:00:00+05:30"))
    d = merge(d, order(142), filing("n1", "2026-05-15T18:00:00+05:30"), "MODERATE", "now")
    loi = order(228, segment="wind EPC")
    d = merge(d, loi, filing("n2", "2026-08-02T18:00:00+05:30"), "MODERATE", "now")
    loi_id = d["deals"][-1]["id"]

    contract = order(228, stage="CONTRACT", updates_deal_id=loi_id, execution_by="30 June 2027")
    f3 = filing("n3", "2026-10-14T18:00:00+05:30")
    after = merge(d, contract, f3, "MODERATE", "now")
    assert len(after["deals"]) == 2
    updated = next(x for x in after["deals"] if x["id"] == loi_id)
    assert (updated["stage"], updated["execution_by"], len(updated["history"])) == ("CONTRACT", "30 June 2027", 2)
    flow = next(s for s in compute(d, after, contract, f3, None) if s["type"] == "ORDER_FLOW")
    assert flow["text"] == "Stage update, not a new order: the ₹228 Cr order first reported on 2026-08-02 moves from LOI to contract."

    # memory before the contract still shows the LOI; re-analysing the contract filing is idempotent
    assert view_as_of(after, "2026-09-01T00:00:00+05:30")["deals"][-1]["stage"] == "LOI"
    again = merge(after, contract, f3, "MODERATE", "now")
    assert len(next(x for x in again["deals"] if x["id"] == loi_id)["history"]) == 2
    # forgetting the contract filing (e.g. it is re-analysed as not material) reverts the stage
    from bse_intel.dossier import _forget
    _forget(again, "n3")
    assert next(x for x in again["deals"] if x["id"] == loi_id)["stage"] == "LOI"


def test_analyst_concerns_and_operating_notes_are_remembered():
    d = new_dossier(filing("n0", "2026-05-01T10:00:00+05:30"))
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "CONCALL_PRESENTATION", "timeline_entry": "Q2 call",
        "card": {"impact_level": "MODERATE", "headline": "Demo Infra guides 18-20% revenue growth for FY27", "what_happened": ["x"]},
        "dossier_delta": {
            "analyst_concerns": [{"concern": "Receivable days rose to 140", "management_response": "Expects 110 days by Q4FY27"}],
            "operating_notes": ["Order book ₹2,450 Cr, executable over 24 months", "", "Steel prices up 8% QoQ"],
        },
    })
    d = merge(d, out, filing("n1", "2026-10-14T18:00:00+05:30"), "MODERATE", "now")
    (concern,) = [w for w in d["watchlist"] if w["kind"] == "CONCERN"]
    assert (concern["text"], concern["response"], concern["status"]) == ("Receivable days rose to 140", "Expects 110 days by Q4FY27", "OPEN")
    view = view_as_of(d, "2026-10-15T00:00:00+05:30")
    assert view["watchlist"][-1]["management_said"] == "Expects 110 days by Q4FY27"
    assert view["operating_notes"] == ["2026-10-14: Order book ₹2,450 Cr, executable over 24 months", "2026-10-14: Steel prices up 8% QoQ"]
    assert view_as_of(d, "2026-10-14T00:00:00+05:30") is None or "operating_notes" not in view_as_of(d, "2026-10-14T00:00:00+05:30")


def test_boilerplate_is_stripped_before_the_ai_reads_a_filing():
    from bse_intel.extract import strip_boilerplate
    letter = "\n".join([
        "To,", "BSE Limited", "Phiroze Jeejeebhoy Towers, Dalal Street,", "Mumbai - 400 001", "Scrip Code: 544290",
        "Sub: Bagging / Receiving of order / contract", "Dear Sir/Madam,",
        "Suyog Urja Limited has received a Letter of Intent for a 100 MW wind project of Rs. 228.00 Crores (excluding GST).",
        "For the reasons above, the board approved a merger with Demo Holdings Limited",
        "We request you to take the above on record.", "Thanking you,", "Yours faithfully,", "For Enviro Infra Engineers Limited",
        "Digitally signed by A Person", "Date: 2026.10.14 18:57:07 +05'30'", "Company Secretary & Compliance Officer",
        "CIN: L37003DL2009PLC191418", "email : ho@eiepl.in, website : www.eiel.in",
    ])
    assert strip_boilerplate(letter).splitlines() == [
        "Scrip Code: 544290", "Sub: Bagging / Receiving of order / contract",
        "Suyog Urja Limited has received a Letter of Intent for a 100 MW wind project of Rs. 228.00 Crores (excluding GST).",
        "For the reasons above, the board approved a merger with Demo Holdings Limited",
    ]


def test_control_characters_used_as_spaces_become_spaces():
    """Jubilant Pharmova's statements: "Revenue\\x03from\\x03operations", "(ཪ\\x03in\\x03million)"."""
    from bse_intel.extract import _clean
    from bse_intel.grounding import declared_unit

    text = _clean("Page 4\n(ཪ\x03in\x03million)\nRevenue\x03from\x03operations\n18,137\x03\x03\x0317,422")
    assert "\x03" not in text and "Revenue from operations" in text
    assert declared_unit(text) == 10


def test_boilerplate_keeps_factual_lines_that_mention_din_office_or_exchange():
    from bse_intel.extract import strip_boilerplate

    text = "\n".join([
        "BSE Limited",
        "Mr. Ravi Kumar (DIN: 01234567) has been appointed as Managing Director for five years.",
        "Shifting of the Registered Office: from Mumbai to Pune with effect from 1 November 2026.",
        "The NCDs will be listed on BSE Limited.",
        "DIN: 07654321",
        "Registered Office: 12 MG Road, Pune",
    ])
    kept = strip_boilerplate(text).splitlines()
    assert kept == [
        "Mr. Ravi Kumar (DIN: 01234567) has been appointed as Managing Director for five years.",
        "Shifting of the Registered Office: from Mumbai to Pune with effect from 1 November 2026.",
        "The NCDs will be listed on BSE Limited.",
    ]


RESULTS_TEXT = ("Statement of standalone unaudited results for the quarter ended 30.09.2026 (Rs. in lakhs). "
                "Revenue from operations 45,612.40 41,208.75 38,964.10 86,821.15 79,402.33 1,62,410.88. "
                "Other income 612.30 588.10 401.25 1,200.40 802.10 1,950.66. Total expenses 39,874.22 36,410.90 "
                "34,120.55 76,285.12 70,112.40 1,43,880.20. Profit before tax 6,350.48 5,385.95 5,244.80 "
                "11,736.43 10,092.03 20,481.34. Net profit 4,752.11 4,030.66 3,925.37 8,782.77 7,552.40 15,327.61. "
                "EPS 12.45 10.56 10.28 23.01 19.79 40.15.")


def test_invented_figures_on_a_realistic_results_statement_are_caught():
    invented = card(headline="Demo Ltd Q2 revenue up 26% to ₹640 Cr; PAT ₹71 Cr",
                    what_happened=["EBITDA rose 37% to ₹95 Cr", "Margin expanded 260 bps to 19.4%", "Order book at ₹2,340 Cr"])
    result = check_card(invented, RESULTS_TEXT)
    assert not result.ok and len(result.ungrounded) >= 5, result
    assert result.headline_ungrounded  # an invented headline amount alone holds the card


def test_true_figures_and_ratios_of_grounded_figures_pass():
    good = card(headline="Demo Ltd Q2 revenue up 17.1% YoY to ₹456 Cr; PAT ₹47.5 Cr",
                what_happened=["Revenue ₹456.1 Cr vs ₹389.6 Cr a year ago", "Net profit up 21.1% YoY to ₹47.5 Cr"])
    result = check_card(good, RESULTS_TEXT)
    assert result.ungrounded == [], result
    order = card(headline="Demo Ltd wins ₹80 Cr LoI, 18% of FY26 sales",
                 what_happened=["LoI worth **₹80 Cr** from NHAI"])
    memory = '{"metrics":{"revenue":["FY26: 444.4 INR_CR"]}}'
    assert check_card(order, "Letter of Intent for Rs. 80 crore from NHAI", memory).ungrounded == []


def test_lakh_figures_copied_as_crore_are_caught():
    """Kanoria Q3FY25: "(INR in Lakhs)" with a loss of 2,863 written as "₹2,863 Cr". Matching at any
    scale let it pass; with a declared unit, crore figures must match at that unit's scale."""
    from bse_intel.grounding import declared_unit

    assert declared_unit(RESULTS_TEXT) == 100
    assert declared_unit("Statement (INRin Lakhs) Revenue 34,752") == 100
    assert declared_unit("(Rs. in million) Revenue 3,475") == 10
    assert declared_unit("(Rs. in lakhs) and a ₹50 crore order") == 100  # "50 crore" carries its own unit
    assert check_card(card(headline="Demo Ltd wins ₹50 Cr order"), "(Rs. in lakhs) and a ₹50 crore order").ungrounded == []
    assert declared_unit("Revenue 12,345.67 (lakhs)") is None
    assert declared_unit("XBRL (₹ crore unless noted)\nStatement (Rs. in lakhs)") is None  # two declared units
    copied = card(headline="Demo Ltd Q2 revenue ₹45,612 Cr; PAT ₹4,752 Cr", what_happened=["Revenue ₹45,612 Cr"])
    result = check_card(copied, RESULTS_TEXT)
    assert "45,612" in result.headline_ungrounded and "4,752" in result.headline_ungrounded
    tenfold = card(headline="Demo Ltd Q2 PAT ₹475.2 Cr")  # read as ₹ million
    assert check_card(tenfold, RESULTS_TEXT).headline_ungrounded == ["475.2"]
    memory = '{"metrics":{"revenue":["FY26: 1,624.1 INR_CR"]}}'  # memory is already in crore
    assert check_card(card(headline="FY26 revenue was ₹1,624.1 Cr"), RESULTS_TEXT, memory).ungrounded == []


RPT_NOTICE = ("Kanoria Chemicals: approval of material related party transactions. Proposed maximum amount of"
              " transactions INR. 5445 \nMillion (equivalent EURO 60.21 Million). Remuneration of the Whole Time"
              " Director up to Rs. 180 lakhs per annum. Authorised capital of Rs. 25 crore.")


def test_a_figure_is_read_in_the_unit_written_beside_it():
    """Kanoria's RPT notice (Apr 2025) mixes million, lakh and crore, so no unit is declared for the
    whole filing; "INR 5445 Million" was carried as "₹5,445 Cr" and passed at any scale."""
    from bse_intel.grounding import declared_unit

    assert declared_unit(RPT_NOTICE) is None
    wrong = card(headline="Kanoria seeks approval for RPTs worth ₹5,445 Cr", what_happened=["WTD pay up to ₹180 Cr"])
    result = check_card(wrong, RPT_NOTICE)
    assert result.headline_ungrounded == ["5,445"] and "180" in result.ungrounded
    right = card(headline="Kanoria seeks approval for RPTs worth ₹544.5 Cr",
                 what_happened=["WTD pay up to ₹1.8 Cr a year", "Authorised capital ₹25 Cr"])
    assert check_card(right, RPT_NOTICE).ungrounded == []
    assert check_card(card(headline="RPTs of ₹545 Cr"), RPT_NOTICE).ungrounded == []  # rounded is fine


@pytest.mark.parametrize("header", ["('l in million)", '"in million)', "c, in million)", "{f in million)",
                                    "(fin million)", "/fin million)", "(' in million)", "(ཪ in million)"])
def test_a_statement_header_with_a_mangled_currency_sign_still_declares_its_unit(header):
    """Novartis India's statements, as the PDF text renders their "(₹ in million)" headers."""
    from bse_intel.grounding import declared_unit

    text = f"Novartis India Limited\n{header}\nSTATEMENT OF PROFIT AND LOSS\nRevenue from Operations\n875.5\n838.8"
    assert declared_unit(text) == 10
    wrong = check_card(card(headline="Novartis India Q1FY26 revenue rose 4% to ₹875.5 Cr"), text)
    assert wrong.headline_ungrounded == ["875.5"]
    assert check_card(card(headline="Novartis India Q1FY26 revenue rose 4% to ₹87.55 Cr"), text).ungrounded == []


def test_prose_ending_in_a_unit_is_not_a_header():
    from bse_intel.grounding import declared_unit

    assert declared_unit("payable within 30 days in lakhs)\nRevenue 875.5") is None


def test_a_bare_figure_takes_the_unit_it_has_elsewhere():
    """Novartis's RPT notice: "INR 3,000 million only (INR 300 Crores Only)", with 3,000 also bare in a table."""
    notice = "Maximum value INR 3,000 million only (INR 300 Crores Only).\nTable\nPharma imports 3,000\n"
    assert check_card(card(headline="RPT worth ₹3,000 Cr"), notice).headline_ungrounded == ["3,000"]
    assert check_card(card(headline="RPT worth ₹300 Cr"), notice).ungrounded == []


def test_a_crore_figure_is_not_grounded_by_a_stray_small_number():
    """Novartis's postal-ballot result: "₹3,000 Cr" passed because "3" (a list item) matched at x0.001."""
    text = "Resolution 3 passed with 98.72% votes in favour. Item 300 of the agenda. Page 1 of 4."
    assert check_card(card(headline="RPT of ₹3,000 Cr approved"), text).headline_ungrounded == ["3,000"]


def test_pass2_prompt_warns_when_units_are_mixed(settings):
    from bse_intel.prompts.engine import PromptEngine

    f = Filing(news_id="u2", scrip_code="506525", company_name="Kanoria Chemicals", headline="Notice",
               filed_at="2025-04-09T17:00:00+05:30", filing_date="2025-04-09")
    _, user = PromptEngine(settings).pass2(f, "GOVERNANCE", None, None, RPT_NOTICE)
    assert "more than one unit" in user and "10 million" in user


def test_pass2_prompt_names_a_non_crore_unit(settings):
    from bse_intel.prompts.engine import PromptEngine

    f = Filing(news_id="u1", scrip_code="999001", company_name="Demo Ltd", headline="Results",
               filed_at="2026-10-13T17:43:02+05:30", filing_date="2026-10-13")
    _, user = PromptEngine(settings).pass2(f, "RESULTS", None, None, RESULTS_TEXT)
    assert "UNITS: this filing states its amounts in ₹ lakh" in user and "divide the filing's figures by 100" in user
    _, user = PromptEngine(settings).pass2(f, "RESULTS", None, None, "Revenue Rs. 456 crore")
    assert "UNITS:" not in user


def test_results_period_labels_follow_the_statement():
    """Novartis India, results for the quarter and year ended 31 Mar 2025: the model wrote Q1FY26."""
    from bse_intel.periods import statement_quarter, statement_year
    from bse_intel.pipeline import relabel_periods

    text = "STATEMENT OF AUDITED FINANCIAL RESULTS FOR THE QUARTER AND YEAR ENDED 31ST MARCH, 2025 (in million)"
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "Q1FY26 revenue ₹83.9 Cr.",
        "card": {"impact_level": "LOW", "headline": "Novartis India Q1FY26 revenue up 3.3% to ₹83.9 Cr",
                 "what_happened": ["Q1FY26 revenue ₹83.9 Cr vs ₹81.2 Cr in Q1FY25; FY26 PAT ₹100.9 Cr"],
                 "track_next": {"kpis_to_verify": [{"kpi": "Revenue growth", "check_in": "Q2FY26 results",
                                                    "period": "Q2FY26", "metric": "revenue"}]}},
        "dossier_delta": {"financial_metrics": [
            {"metric": "revenue", "period": "Q1FY26", "value": 83.9}, {"metric": "revenue", "period": "Q1 FY25", "value": 81.2},
            {"metric": "revenue", "period": "Q4FY25", "value": 93.0}, {"metric": "pat", "period": "FY26", "value": 100.9}]},
    })
    mapping = relabel_periods(out, statement_quarter(text), statement_year(text))
    assert mapping == {"Q1FY26": "Q4FY25", "Q1FY25": "Q4FY24", "Q4FY25": "Q3FY25", "FY26": "FY25"}
    assert [m.period for m in out.dossier_delta.financial_metrics] == ["Q4FY25", "Q4FY24", "Q3FY25", "FY25"]
    assert out.card.headline.startswith("Novartis India Q4FY25 revenue")
    assert out.card.what_happened[0].text == "Q4FY25 revenue ₹83.9 Cr vs ₹81.2 Cr in Q4FY24; FY25 PAT ₹100.9 Cr"
    assert out.card.track_next.kpis_to_verify[0].period == "Q1FY26" and out.timeline_entry.startswith("Q4FY25")
    # a correctly labelled card is left alone
    ok = Pass2Output.model_validate({"is_material": True, "card": {"impact_level": "LOW", "headline": "Q4FY25 revenue ₹93 Cr",
                                     "what_happened": ["x"]}, "dossier_delta": {"financial_metrics": [
                                         {"metric": "revenue", "period": "Q4FY25", "value": 93.0}]}})
    assert relabel_periods(ok, "Q4FY25", "FY25") == {}


def test_claims_track_record_bold_and_repeat_only_in_the_filing():
    from bse_intel.grounding import check_claims

    c = card(headline="Company wins **maiden** international order from Airbus",
             what_happened=["Strong track record in aerostructures"])
    filing = "We are pleased to announce receipt of our maiden international order from Airbus."
    memory = '{"recent_timeline":[{"summary":"further order from HAL"}]}'
    assert check_claims(c, filing, memory) == []  # a repeat in memory does not undo the filing's own claim
    first_quarter = card(headline="Maiden order from Airbus", what_happened=["x"])
    assert check_claims(first_quarter, "Results for the first quarter. Order from Airbus received.") != []


def test_copied_placeholders_and_null_shapes_do_not_become_answers():
    from bse_intel.models import Pass2Output

    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "ORDER_WIN", "timeline_entry": None, "dossier_delta": None,
        "card": {"impact_level": "HIGH", "headline": "Demo Infra wins ₹186 Cr wind EPC LoI", "takeaway": None,
                 "what_happened": ["LoI worth ₹186 Cr"], "key_numbers": [{"label": "Order", "value": 186}, {"bad": 1}],
                 "track_next": None, "tone": "POSITIVE | NEGATIVE | MIXED | NEUTRAL",
                 "deal_value": {"kind": "ORDER", "amount_cr": 186, "stage": "Board approval",
                                "progress": "40 MW of 60 MW commissioned or null", "counterparty": "string"}},
    })
    card = out.card
    assert card.tone == "NEUTRAL" and card.key_numbers[0].value == "186" and len(card.key_numbers) == 1
    assert card.deal_value.progress is None and card.deal_value.counterparty is None
    assert card.deal_value.stage == "BOARD_APPROVED"
    assert out.timeline_entry == card.headline
    with pytest.raises(Exception):
        Pass2Output.model_validate({"is_material": True, "card": {"impact_level": "HIGH | MODERATE | LOW",
                                                                 "headline": "Demo wins order", "what_happened": ["x"]}})


def test_board_meeting_duration_and_reg30_para_b_clues():
    from bse_intel.forensics import board_meeting_hours, text_signals

    letter = "The meeting of the Board commenced at 2:30 p.m. and concluded at 11:45 p.m. The Board approved the results."
    assert board_meeting_hours(letter) == 9.25
    assert [s["type"] for s in text_signals(letter, "RESULTS")] == ["BOARD_DELIBERATION"]
    assert text_signals("commenced at 11:00 a.m. and concluded at 12:30 p.m.", "RESULTS") == []
    launch = "Disclosure under Regulation 30 read with Para B of Part A of Schedule III: launch of Triacetin."
    assert [s["type"] for s in text_signals(launch, "PRODUCT_LAUNCH")] == ["REG30_THRESHOLD"]


def test_scanned_amount_in_millions_header_declares_the_unit():
    r"""Heritage Foods' FY25 statements are scanned: "(,\mount in millions of Z unless otherwise stated)",
    "(Amount 111 millions oft unlc:-s othenv1se statcu)". PAT 205.10 is ₹20.5 Cr, not "₹205 Cr"."""
    from bse_intel.grounding import check_card, declared_unit

    text = (r"(,\mount in millions of Z unless otherwise stated)" "\nProfit for Che period/year 205.10 412.92\n"
            "(Amount 111 millions oft unlc:-s othenv1se statcu)\nBorrowing limit from Rs.500 Crores to Rs.800 Crores")
    assert declared_unit(text) == 10
    assert check_card(card(headline="Heritage PAT ₹205 Cr", what_happened=["PAT ₹205 Cr"]), text).headline_ungrounded == ["205"]
    assert not check_card(card(headline="Heritage PAT ₹20.51 Cr", what_happened=["Borrowing limit raised to ₹800 Cr"]), text).ungrounded


def test_scale_check_flags_a_lakh_table_read_as_crore():
    """Ahluwalia Q3FY25: PAT "₹495 Cr" and EBITDA "₹756 Cr" on ₹952 Cr revenue (they were ₹49.4 Cr
    and ₹84.4 Cr); its recent quarters made ₹40–60 Cr of profit."""
    from bse_intel.grounding import scale_issues
    from bse_intel.models import FinancialMetric

    history = [{"metric": "pat", "period": p, "value": v} for p, v in (("Q1FY25", 41.2), ("Q2FY25", 55.7), ("Q3FY24", 60.1))]
    now = [FinancialMetric(metric="revenue", period="Q3FY25", value=952), FinancialMetric(metric="ebitda", period="Q3FY25", value=756),
           FinancialMetric(metric="pat", period="Q3FY25", value=495)]
    issues = scale_issues(now, history)
    assert any(i.startswith("PAT Q3FY25 ₹495.00 Cr is over 5x") for i in issues)
    assert not any(i.startswith("EBITDA") for i in issues)  # below revenue, and no EBITDA history
    assert scale_issues([FinancialMetric(metric="pat", period="Q3FY25", value=960)],
                        []) == []  # no revenue, no history: nothing to compare with
    assert scale_issues(now[:1] + [FinancialMetric(metric="pat", period="Q3FY25", value=1200)], []) == [
        "PAT Q3FY25 ₹1,200.00 Cr is above revenue ₹952.00 Cr"]
    assert scale_issues([FinancialMetric(metric="pat", period="Q3FY25", value=49.39)], history) == []


LAKH_STATEMENT = ("Statement of unaudited standalone financial results for the quarter ended 31.12.2024 (₹ in Lakhs)\n"
                  "Revenue from operations 95,196.00 1,02,642.00\nFinance costs 1,455.10 1,230.00\n"
                  "Profit for the period 4,939.22 7,071.00\nOther comprehensive income 955.40\n")


def _results_reply(what_happened, metrics, key_numbers=()):
    return Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": what_happened[0],
        "card": {"impact_level": "MODERATE", "headline": "Ahluwalia Q3FY25 revenue ₹951.96 Cr", "what_happened": what_happened,
                 "key_numbers": list(key_numbers)},
        "dossier_delta": {"financial_metrics": metrics}})


def test_unit_slips_are_corrected_in_code_when_one_reading_fits():
    """Ahluwalia's lakh table read as tenths of a crore: PAT "₹493.92 Cr" (4,939.22 lakh = ₹49.39 Cr),
    finance cost "₹145.51 Cr"; the right reading is the only one that fits, so code corrects it."""
    from bse_intel.pipeline import fix_unit_slips

    out = _results_reply(["Revenue ₹951.96 Cr, PAT ₹493.92 Cr", "Finance cost ₹145.51 Cr; PAT was ₹4,939 Cr? no"],
                         [{"metric": "pat", "period": "Q3FY25", "value": 493.92},
                          {"metric": "revenue", "period": "Q3FY25", "value": 951.96}],
                         [{"label": "PAT", "value": "₹493.92 Cr", "change": "-30% YoY"}])
    fixed = fix_unit_slips(out, (LAKH_STATEMENT, "", ""))
    assert fixed == {"493.92": "49.39", "145.51": "14.55", "4,939": "49.39"}
    assert out.card.what_happened[0].text == "Revenue ₹951.96 Cr, PAT ₹49.39 Cr"
    assert out.card.key_numbers[0].value == "₹49.39 Cr" and out.timeline_entry == "Revenue ₹951.96 Cr, PAT ₹49.39 Cr"
    assert {m.metric: m.value for m in out.dossier_delta.financial_metrics} == {"pat": 49.39, "revenue": 951.96}


def test_unit_slips_need_a_declared_unit_and_a_single_fit():
    from bse_intel.grounding import unit_slips

    assert unit_slips(["PAT ₹493.92 Cr"], LAKH_STATEMENT.replace("(₹ in Lakhs)", "")) == []  # no declared unit
    assert unit_slips(["Order book ₹2,400 Cr"], LAKH_STATEMENT) == []  # fits no statement figure: left to the checks
    assert unit_slips(["Revenue ₹951.96 Cr"], LAKH_STATEMENT) == []  # already right
    # "₹955 Cr" is within 0.5% of the ₹951.96 Cr revenue: a rounding, though 955.40 lakh would also "fit"
    assert unit_slips(["Revenue about ₹955 Cr"], LAKH_STATEMENT) == []


def test_margin_that_does_not_fit_its_figures_is_flagged():
    """Ahluwalia's card: EBITDA "₹756 Cr" on ₹952 Cr revenue "at a 7.9% margin" (756 / 952 is 79%)."""
    from bse_intel.grounding import margin_issues
    from bse_intel.models import FinancialMetric, KeyNumber

    metrics = [FinancialMetric(metric="revenue", period="Q3FY25", value=952), FinancialMetric(metric="ebitda", period="Q3FY25", value=756),
               FinancialMetric(metric="ebitda_margin", period="Q3FY25", value=7.9)]
    assert margin_issues(metrics) == ["EBITDA ₹756.00 Cr on revenue ₹952.00 Cr is a 79.4% margin, not the stated 7.9% (Q3FY25)"]
    keys = [KeyNumber(label="Revenue", value="₹952 Cr"), KeyNumber(label="EBITDA", value="₹756 Cr"),
            KeyNumber(label="EBITDA Margin", value="7.9%")]
    assert margin_issues([], keys) == ["EBITDA ₹756.00 Cr on revenue ₹952.00 Cr is a 79.4% margin, not the stated 7.9% (key numbers)"]
    metrics[1] = FinancialMetric(metric="ebitda", period="Q3FY25", value=75.6)
    assert margin_issues(metrics) == []


def test_no_dilution_signal_for_dividends_open_offers_or_authorised_capital():
    """Smoke test: "Dividend: issue price ₹18.00 is 99.0% below the last close"; "Open Offer: 26.0% more
    shares"; "Authorised Share Capital Increase: 46.7% more shares"."""
    from bse_intel.signals import _dilution

    def actions(*instruments):
        return Pass2Output.model_validate({"is_material": False, "event_type": "OTHER", "timeline_entry": "x",
                                           "dossier_delta": {"capital_actions": [
                                               {"instrument": i, "new_shares": 3_762_628, "issue_price": 18} for i in instruments]}})
    company = {"shares_outstanding": 14_471_646, "last_price": 1836.35}
    assert _dilution({}, actions("Dividend", "Open Offer", "Authorised Share Capital Increase"), company) == []
    assert [s.type for s in _dilution({}, actions("QIP"), company)] == ["DILUTION"]


def test_the_scale_block_gives_the_model_proportions_it_must_not_compute():
    """Owner's note, 2026-10-16: the model works out no share of revenue or market cap. The audit found
    "₹500 Cr is 41% of FY25 revenue" where it was 7.3%, and "3.6x FY25 revenue" where the filing said 84%
    of turnover. Code computes every proportion and the prompt carries them."""
    from bse_intel.signals import scale_block

    dossier = {"financial_metrics": [{"metric": "revenue", "period": p, "value": v, "unit": "INR_CR"}
                                     for p, v in (("Q1FY26", 1000), ("Q2FY26", 1100), ("Q3FY26", 1200), ("Q4FY26", 1300))]
               + [{"metric": "order_book", "period": "Q4FY26", "value": 25194, "unit": "INR_CR"}],
               "balance_sheet": [{"period": "Q4FY26", "net_worth_cr": 2000.0, "net_debt_cr": -304.24}]}
    block = scale_block(dossier, {"market_cap_cr": 3779.0}, "The order is valued at Rs. 396.5 crore.", None)
    assert "revenue ₹4,600 Cr (TTM to Q4FY26)" in block and "market cap ₹3,779 Cr" in block
    assert "net cash ₹304.24 Cr" in block and "order book ₹25,194 Cr" in block     # not "net debt ₹-304.24 Cr"
    assert "₹396.5 Cr = 10.5% of market cap, 8.6% of revenue, 19.8% of net worth, 1.6% of order book" in block
    assert "give no proportions" in scale_block({}, {}, "Rs. 396.5 crore", None)   # nothing known: say so


def test_pass2_system_prompt_is_one_shared_prefix_across_events_and_sectors(settings):
    """Prefix caching bills a repeated prompt at 2% (D24), but only for the bytes before the first
    difference. Every part that varies — the triaged event type, its focus, the sector lens, the schema's
    event_type — therefore belongs at the end: two calls that share nothing else must still share most of
    the system prompt."""
    from bse_intel.prompts.engine import PromptEngine

    engine = PromptEngine(settings)
    f = Filing(news_id="p1", scrip_code="999001", company_name="Demo Ltd", headline="Results",
               filed_at="2026-10-13T17:43:02+05:30", filing_date="2026-10-13")
    a, _ = engine.pass2(f, "RESULTS", "Refineries", None, "text")
    b, _ = engine.pass2(f, "ORDER_WIN", "Construction", None, "text")
    shared = os.path.commonprefix([a, b])
    assert len(shared) > 0.6 * len(a), f"only {len(shared)} of {len(a)} chars shared"
    # the rules the two calls share must sit inside that prefix, not after the first difference
    assert "event_type: as triaged" in shared


def test_a_change_is_recomputed_only_from_figures_the_filing_states():
    """Audit round 1: Kanoria's annual report said finance costs of 457.86 million (₹45.79 Cr); the card read
    it as "₹458 Cr", and the fixer dutifully computed "+965.1% YoY" from it, turning a unit slip into a
    confident nonsense. A side that is not in the filing now leaves the change alone."""
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import fix_change_percentages

    def card(previous: str, current: str, change: str):
        return Pass2Output.model_validate({
            "is_material": True, "event_type": "RESULTS", "timeline_entry": "FY25 results",
            "card": {"impact_level": "MODERATE", "headline": "Kanoria FY25 results",
                     "what_happened": ["Finance costs rose"], "key_numbers": [],
                     "notable_changes": [{"metric": "Finance Costs", "previous": previous, "current": current,
                                          "change": change, "direction": "negative"}]}})

    filing = ("Finance costs 457.86 million against 430.20 million in the previous year. "
              "Revenue from operations 15,367 million against 14,751 million.")
    # "₹458 Cr" is the 457.86 million figure misread, so no % may be computed from it
    out = card("₹43 Cr (FY24)", "₹458 Cr (FY25)", "+6.5% YoY")
    assert fix_change_percentages(out, (filing,)) == []
    assert out.card.notable_changes[0].change == "+6.5% YoY"

    # both sides stated in the filing: the arithmetic is still corrected in code
    out = card("₹1,475.10 Cr (FY24)", "₹1,536.70 Cr (FY25)", "-12% YoY")
    assert fix_change_percentages(out, (filing,))
    assert out.card.notable_changes[0].change == "+4.2% YoY"
    assert out.card.notable_changes[0].direction == "POSITIVE"


def test_an_open_offer_is_not_a_raise_against_the_target():
    """Audit round 1: Novartis India's 552.5 Cr open offer and M&M's 554.65 Cr purchase of SML Isuzu were
    typed FUNDRAISE, so the card read "552.5 Cr raise = n% of net worth" for money that never reaches the
    company - it passes between shareholders. The size against market cap still says something and stays."""
    from bse_intel.models import Pass2Output

    def out(event_type):
        return Pass2Output.model_validate({
            "is_material": True, "event_type": event_type, "timeline_entry": "open offer",
            "card": {"impact_level": "HIGH", "headline": "Open offer for 26% at Rs 860.64",
                     "what_happened": ["Open offer for 26%"], "key_numbers": [],
                     "deal_value": {"kind": "FUNDRAISE", "amount_cr": 552.5}}})

    f = filing("n_oo", "2026-10-14T18:00:00+05:30")
    d = new_dossier(f)
    d["balance_sheet"] = [{"period": "Q1FY27", "net_worth_cr": 300.0, "as_of": "2026-08-01T00:00:00+05:30",
                           "source_news_id": "old"}]
    company = {"market_cap_cr": 2000, "price_date": "2026-10-14"}

    scale = [s for s in compute(d, d, out("M_AND_A"), f, company) if s["type"] == "SCALE"]
    assert scale, "the size against market cap should still be reported"
    assert "raise" not in scale[0]["text"] and "deal" in scale[0]["text"]
    assert "net worth" not in scale[0]["text"]

    # a real fundraise is unchanged: the company does receive the money
    raised = [s for s in compute(d, d, out("FUNDRAISE"), f, company) if s["type"] == "SCALE"]
    assert raised and "raise" in raised[0]["text"]


@pytest.mark.parametrize("headline,instrument,converted", [
    # Audit round 1: debt turned into shares brings no cash, yet read "₹25 Cr raise = 74% of net worth"
    ("Shivam Autotech converts 250 OCDs into 92,72,997 equity shares for India Credit Opportunities Fund II", "", True),
    ("Shivam Autotech to convert ₹25 Cr OCDs into 92.73 lakh equity shares at pre-determined price", "", True),
    ("Board approves allotment of 9.3 lakh shares", "Conversion of unsecured loan into equity", True),
    ("Board approves allotment of 9.3 lakh shares", "CCDs converted to equity", True),
    # still money reaching the company
    ("Demo Tubes raises ₹500 Cr through compulsorily convertible debentures", "CCD", False),
    ("Demo Tubes allots 40 lakh shares on conversion of warrants, receiving the balance 75%", "Warrant conversion", False),
    ("Demo Tubes approves ₹75 Cr preferential issue of convertible warrants", "", False),
    # a new issue stating its conversion terms is still a raise
    ("Demo Tubes issues USD 50 mn FCCBs at a conversion price of ₹512", "FCCBs", False),
    ("Demo Tubes raises ₹300 Cr in bonds with a conversion premium of 20%", "", False),
])
def test_debt_converted_into_shares_is_not_a_raise(headline, instrument, converted):
    from bse_intel.models import Pass2Output

    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "FUNDRAISE", "timeline_entry": headline,
        "card": {"impact_level": "MODERATE", "headline": headline, "what_happened": [headline], "key_numbers": [],
                 "deal_value": {"kind": "FUNDRAISE", "amount_cr": 25.0}},
        "dossier_delta": {"capital_actions": [{"instrument": instrument, "new_shares": 9272997}] if instrument else []}})
    f = filing("n_ocd", "2025-02-20T18:00:00+05:30")
    d = new_dossier(f)
    d["balance_sheet"] = [{"period": "Q3FY25", "net_worth_cr": 33.92, "as_of": "2025-02-01T00:00:00+05:30",
                           "source_news_id": "old"}]
    scale = [s["text"] for s in compute(d, d, out, f, {"market_cap_cr": 400, "price_date": "2025-02-20"})
             if s["type"] == "SCALE"]
    assert scale
    if converted:
        assert scale[0].startswith("₹25 Cr conversion = 6% of market cap") and "net worth" not in scale[0], scale
    else:
        assert "₹25 Cr raise" in scale[0] and "net worth" in scale[0], scale


def test_a_round_figure_grounds_against_an_unrelated_line_in_range():
    """The weakness that let Kanoria's annual-report cards carry every 10x slip and still pass grounding.

    A card figure is matched against every number in the document at every legitimate unit scale, with no
    regard to where it sits, and a whole crore figure carries a +/-0.5 Cr tolerance, which becomes +/-5 at
    the million scale. In a short filing that is harmless, because nothing unrelated is in range. In a
    563,458-character annual report declared in million it is not: invented whole-crore figures were
    accepted 40% of the time, against 8% at one decimal and 3% at two. So the check is weakest exactly
    where cards state round numbers, which is most headline figures.

    Pinned so a fix can be measured. The fix is to anchor a fact's figures to its own quote's
    neighbourhood, which every fact now carries, instead of to the whole document.
    """
    from bse_intel.grounding import SourceIndex

    # a short filing with its unit stated: the 10x misreading is correctly refused
    index = SourceIndex("Finance costs for the year were 457.86 million against 430.20 million.")
    assert index.stated_crore(45.79, 2)        # the right reading, in crore
    assert not index.stated_crore(458.0, 0)    # 458 Cr would need 4,580 million, which is not there

    # the hole: the figure is absent, but an unrelated line sits within tolerance at the same scale
    unrelated = SourceIndex("Property, plant and equipment 4,583 million. Trade receivables 1,204 million.")
    assert unrelated.stated_crore(458.0, 0), "documents today behaviour, not what it should be"
    assert not unrelated.stated_crore(458.31, 2)   # two decimals do not slip through the same way


def test_a_headline_number_answers_to_its_own_quote_not_the_whole_filing():
    """The fix for the pinned 40% baseline. key_numbers, notable_changes and why_it_matters state the
    figures a reader acts on and carried no quote, so their numbers were only looked for in the whole
    filing - where a round one lands on an unrelated line within its own rounding. Inside one sentence
    there is nothing to land on. The check is unit-aware, because the card writes crore where the filing
    writes million: 45.79 Cr is the right reading of 457.86 million and must pass, 458 Cr is the 10x
    misreading and must not, even though 4,583 million appears further down the page."""
    from bse_intel.grounding import declared_unit
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import check_quoted_numbers

    filing = ("Statement of profit and loss (Rs. in million). "
              "Finance costs for the year were 457.86 against 430.20. "
              "Property, plant and equipment stood at 4,583.")
    unit = declared_unit(filing)
    assert unit == 10

    def card(value, quote):
        return Pass2Output.model_validate({
            "is_material": True, "event_type": "RESULTS", "timeline_entry": "FY25 results",
            "card": {"impact_level": "MODERATE", "headline": "FY25 results",
                     "what_happened": [{"text": "Finance costs reported", "quote": "Finance costs for the year"}],
                     "key_numbers": [{"label": "Finance cost", "value": value, "quote": quote}]}})

    good = card("₹45.79 Cr", "Finance costs for the year were 457.86 against 430.20")
    assert check_quoted_numbers(good, filing, unit) == ([], [], [])

    # the 10x misreading: 4,583 million is in the filing and rounds to 458 Cr, but not in this sentence
    bad = card("₹458 Cr", "Finance costs for the year were 457.86 against 430.20")
    problems, unquoted, _ = check_quoted_numbers(bad, filing, unit)
    assert problems and "458" in problems[0] and "its own quote does not" in problems[0]
    assert unquoted == []

    # a quote that is not in the filing at all is its own problem
    invented = card("₹45.79 Cr", "Finance costs rose sharply during the year under review")
    problems, _, _ = check_quoted_numbers(invented, filing)
    assert problems and "not in the filing" in problems[0]

    # and a figure with no quote is reported, not failed, while the models learn the field
    none_given = card("₹45.79 Cr", None)
    problems, unquoted, _ = check_quoted_numbers(none_given, filing)
    assert problems == [] and unquoted == ["key number: Finance cost"]


def test_a_unit_written_the_ways_indian_statements_write_it():
    """Read on 929 cached filings, these were the declarations the pattern missed: the currency spelled
    out (SML's "(Rupees in Crores, except share data)"), thousands as "(Rs. 000)", and a rupee sign the
    PDF mangled and glued to the word ("(XLakhs)"). Five filings changed, each for the better - two
    rating letters now read in million, as their tables say, and a BRSR that mixes lakh and crore no
    longer claims to be all lakh."""
    from bse_intel.grounding import declared_unit

    assert declared_unit("(Rupees in Lakhs, except per share data)") == 100
    assert declared_unit("(Rupees in Crores, except share data)") is None   # crore: nothing to convert
    assert declared_unit("(Rs. 000)") == declared_unit("(₹ 000s)") == 10_000
    assert declared_unit("Net Worth (XLakhs)") == 100
    assert declared_unit("Turnover (in Rs. Lakhs) 3,792 ... Revenue from operations in Rupees Crores 38.1") is None, \
        "two units declared: no single one applies"
    # and what must still not read as a declaration
    assert declared_unit("Revenue 12,345.67 (lakhs)") is None      # belongs to that one figure
    assert declared_unit("Rs. 000,123 was paid") is None
    assert declared_unit("purchase of 5 lakhs shares at Rs 10") is None


def test_a_change_computed_from_its_own_line_is_checked_by_arithmetic_not_looked_up():
    """Loop rounds 3a-3b (2026-10-17): Kanoria's net debt "+₹246.77 Cr" (₹34.96 Cr to ₹281.73 Cr), its textile
    loss "+₹0.50 Cr" (-₹6.38 Cr to -₹5.88 Cr) and Jubilant's Generics loss "narrowed -89.7%" were held as
    figures the filing does not print - each is the line's own subtraction. A wrong one still is not."""
    from bse_intel.grounding import change_derived, change_follows
    from bse_intel.pipeline import check_quoted_numbers

    assert change_derived("₹34.96 Cr (Mar-2025)", "₹281.73 Cr (Sep-2025)", "+₹246.77 Cr")
    assert change_derived("-₹6.38 Cr (Q2FY25)", "-₹5.88 Cr (Q2FY26)", "+₹0.50 Cr")
    assert change_derived("-₹224.4 Cr (FY24)", "-₹23.2 Cr (FY25)", "loss narrowed-89.7%")
    assert change_derived("₹11.28 Cr (H1FY25)", "-₹4.18 Cr (H1FY26)", "-62.9%")
    assert change_derived("22.99% (Q3FY24)", "21.08% (Q3FY25)", "-191 bps")
    assert change_derived("₹19.78 lakh (June 2025)", "₹50.1 Cr tax plus ₹50.1 Cr penalty", "about 250x larger")
    assert not change_derived("27.9% (Q3FY25)", "45.7% (Q3FY26)", "+178 bps"), "1,780 bps: the model's slip"
    assert not change_derived("₹12.11 Cr (Q3FY25)", "₹8.53 Cr (Q3FY26)", "-30.0% YoY"), "-29.6%, not -30.0%"
    assert not change_derived("₹4.54 Cr write-back", "₹16.53 Cr charge", "swing to charge"), "no figure to follow"
    assert not change_follows("Nil", "₹5 Cr", 5, 0, "plain")
    # the sides are rounded too: a change worked out from the unrounded figures is not refused for it
    assert change_derived("₹0.4 Cr (Q3FY25)", "₹1.0 Cr (Q3FY26)", "+172% YoY")
    assert change_derived("-₹224 Cr (FY24)", "-₹23 Cr (FY25)", "-89.7%")

    filing = "Net debt stood at Rs. 28,173 lakh as at 30 September 2025 against Rs. 3,496 lakh in March 2025 (Rs. in lakh)."
    held = Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "Q2FY26 results",
        "card": {"impact_level": "MODERATE", "headline": "Q2FY26 results",
                 "what_happened": [{"text": "Net debt rose", "quote": "Net debt stood at Rs. 28,173 lakh"}],
                 "notable_changes": [{"metric": "net_debt", "previous": "₹34.96 Cr (Mar-2025)",
                                      "current": "₹281.73 Cr (Sep-2025)", "change": "+₹246.77 Cr",
                                      "quote": "Net debt stood at Rs. 28,173 lakh as at 30 September 2025"}]}})
    assert check_quoted_numbers(held, filing, 100)[0] == []
    assert "246.77" not in check_card(held.card, filing).ungrounded
    held.card.notable_changes[0].change = "+₹264.77 Cr"           # a slip in the subtraction is still caught
    assert "264.77" in check_card(held.card, filing).ungrounded


def test_figures_code_computed_from_the_filing_are_grounded():
    """SML's deal of ₹554.65 Cr is 85,33,053 shares at ₹650, both read from the filing by the deal guard, and
    was held as a number the filing does not print (loop round 3b, 2026-10-17)."""
    from bse_intel.pipeline import check_card_all

    filing = ("Share purchase agreements for 63,62,306 equity shares from Sumitomo Corporation and 21,70,747 equity "
              "shares from Isuzu Motors Limited at a price of Rs. 650 per share.")
    card = Pass2Output.model_validate({
        "is_material": True, "event_type": "M_AND_A", "timeline_entry": "SPA signed",
        "card": {"impact_level": "HIGH", "headline": "Mahindra to buy 58.96% of SML for ₹554.65 Cr",
                 "what_happened": [{"text": "SPAs signed", "quote": "Share purchase agreements"}],
                 "deal_value": {"kind": "ACQUISITION", "amount_cr": 554.65, "tranches": [
                     {"party": "M&M from Sumitomo", "shares": 6362306, "price_per_share": 650},
                     {"party": "M&M from Isuzu", "shares": 2170747, "price_per_share": 650}]}}})
    found = check_card_all(card, None, (filing,))
    assert "554.65" not in found.ungrounded and "58.96%" in found.ungrounded
    card.card.deal_value.tranches = []
    assert "554.65" in check_card_all(card, None, (filing,)).ungrounded, "without the shares it is not derived"


def test_a_figure_rounded_to_the_cards_own_last_digit_is_the_quotes_figure():
    """Only a prefix used to count as a rounding ("95" of "951.96"), and a unit the quote writes itself was not
    read: Novartis's note "₹ 16.8 million (Gratuity by 14.2 million ...)" given as ₹1.68 Cr and ₹1.42 Cr, and
    Jubilant's finance cost "52.7 Cr" given as ₹53 Cr, were held as figures their quotes do not carry
    (12 of 766 quoted items in loop rounds 2a-3b; the owner's question, 2026-10-18: 1.09 lakh written as 1.1
    lakh must not hold a card). The unit still has to be right."""
    from bse_intel.gate import numbers_in_quote

    assert numbers_in_quote("₹1.1 lakh", "a demand of Rs. 1.09 lakh") == []
    assert numbers_in_quote("₹952 Cr", "Revenue from operations 951.96") == []
    assert numbers_in_quote("₹53 Cr (Q4FY25)", "finance_cost Q4FY25: 52.7 Cr, QoQ -5.2%", 10) == []
    assert numbers_in_quote("₹1.68 Cr (gratuity ₹1.42 Cr, leave ₹0.26 Cr)",
                            "increase in the provision by ₹ 16.8 million (Gratuity by 14.2 million and leave 2.6 million)") == []
    assert numbers_in_quote("₹53.0 per share", "Basic EPS 52.99", 100) == []
    # the wrong unit, or more precision than the quote has, is still a figure the quote does not carry
    assert numbers_in_quote("₹458 Cr", "Finance costs 457.86", 10) == ["458"]
    assert numbers_in_quote("₹110 Cr", "a demand of Rs. 109.4 lakh") == ["110"]
    assert numbers_in_quote("₹1.09 lakh", "a demand of Rs. 1.1 lakh") == ["1.09"]


def test_a_row_copied_digit_for_digit_is_a_slip_whatever_happens_to_sit_near_the_right_reading():
    """Jubilant's FY25 card: "exceptional items of ₹3,595 Cr" from the row "Exceptional items (3,595)" of a
    statement in ₹ million (₹359.5 Cr). An unrelated 35,9xx elsewhere sat within 0.5% of 35,950, so the fixer
    took the card's figure for a rounding and left it (loop round 3c, 2026-10-18)."""
    from bse_intel.grounding import unit_slips

    million = ("Statement of audited consolidated financial results (₹ in million)\n"
               "Revenue from operations 19,288 72,345\nExceptional items (3,595) 1,689\n"
               "Total assets of the segment 35,912 33,004\n")
    assert unit_slips(["FY25 PAT rose due to exceptional items of ₹3,595 Cr"], million) == \
        [("3,595", 3595.0, 0, 359.5, 1)]
    # in prose the sentence the figure ends, its naming words on the lines before it
    note = million + ("a) Net income pursuant to sale of investment in SOFIE (including waiver fee and\n"
                      "accelerated share payment) aggregating to ₹ 6,715 million.\nTotal assets 67,190 67,000\n")
    assert ("6,715", 6715.0, 0, 671.5, 1) in unit_slips(["Mainly driven by ₹6,715 Cr gain from SOFIE sale"], note)
    # a figure near a real one, copied from a row with another name, is still left alone (Ahluwalia's "₹955 Cr")
    assert unit_slips(["Revenue about ₹955 Cr"], LAKH_STATEMENT) == []


def test_a_figure_the_prompt_gave_the_model_is_grounded():
    """Pass 2 is given the company's market cap, revenue, net worth and debt to measure an event against (the
    scale block), and grounding did not look there: Shivam's "12.8% of its ₹391.58 Cr market cap" was held as a
    figure the filing does not print. 40 of the 77 cards held only for an unfound amount were like this
    (funnel, 2026-10-18)."""
    from bse_intel.pipeline import check_card_all
    from bse_intel.signals import scale_block

    filing = "The Company has received an order worth Rs. 50.10 crore from Tata Motors Limited."
    card = Pass2Output.model_validate({
        "is_material": True, "event_type": "ORDER_WIN", "timeline_entry": "Order win",
        "card": {"impact_level": "MODERATE", "headline": "Shivam wins ₹50.10 Cr order from Tata Motors",
                 "what_happened": [{"text": "Order worth ₹50.10 Cr", "quote": "an order worth Rs. 50.10 crore"}],
                 "why_it_matters": [{"text": "The order is 12.8% of the ₹391.58 Cr market cap", "basis": "FILING"}]}})
    scale = scale_block({}, {"market_cap_cr": 391.58}, filing)
    assert "391.58" in check_card_all(card, None, (filing, "", "", "{}")).ungrounded
    assert "391.58" not in check_card_all(card, None, (filing, "", "", "{}", scale)).ungrounded


def test_a_change_between_whole_crore_figures_is_corrected_too():
    """The change fixer asks for both sides in the filing before it trusts its own arithmetic, and asked at two
    decimals whatever the card wrote: "₹494 Cr → ₹418 Cr, +15% YoY" against a statement of 49,412 and 41,804
    lakh was never corrected, since 494.00 is not 494.12 (audit of discard paths, 2026-10-18)."""
    from bse_intel.pipeline import fix_change_percentages

    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "Q3 results",
        "card": {"impact_level": "MODERATE", "headline": "Q3 revenue ₹418 Cr", "what_happened": ["Revenue ₹418 Cr"],
                 "notable_changes": [{"metric": "revenue", "previous": "₹494 Cr (Q3FY24)", "current": "₹418 Cr (Q3FY25)",
                                      "change": "+15% YoY", "direction": "POSITIVE"}]}})
    statement = "Statement of results (₹ in Lakhs)\nRevenue from operations 41,804.10 49,412.30"
    assert fix_change_percentages(out, (statement,)) == ["revenue: +15% YoY -> -15.4% YoY"]
    assert out.card.notable_changes[0].direction == "NEGATIVE"


def test_a_sentences_figure_from_far_down_the_filing_is_reported_when_stated_to_two_decimals():
    """CSB's "provisions rose to ₹16.53 Cr (from a negative ₹4.54 Cr)" quoted the XBRL line, and the year-ago
    figure is the statement's (454) lakh far down the page: a right card held (loop round 3c). A figure written
    to two decimals and found at its unit is 3% chance at worst (the 40/8/3 baseline above), so it is reported;
    a whole number, or one at the wrong unit, still holds."""
    from bse_intel.pipeline import check_quotes

    xbrl = "provisions Q3FY25: 16.53 Cr, YoY swing\n"
    filing = xbrl + ("x " * 1500) + "\nStatement (₹ in Lakhs)\nProvisions (other than tax) and Contingencies 1,653 1,391 (454)"

    def card(text):
        return Pass2Output.model_validate({
            "is_material": True, "event_type": "RESULTS", "timeline_entry": "Q3 results",
            "card": {"impact_level": "MODERATE", "headline": "CSB Q3 results",
                     "what_happened": [{"text": text, "quote": "provisions Q3FY25: 16.53 Cr"}]}})

    right = card("Provisions rose to ₹16.53 Cr from a negative ₹4.54 Cr a year ago")
    problems, _, _, style = check_quotes(right, filing, unit=100)
    assert problems == [] and any("4.54" in s and "elsewhere in the filing" in s for s in style)
    assert check_quotes(card("Provisions rose to ₹16.53 Cr from a negative ₹45.40 Cr a year ago"), filing, unit=100)[0], \
        "ten times the filing's figure is not stated anywhere"
    assert check_quotes(card("Provisions rose to ₹16.53 Cr from ₹5 Cr a year ago"), filing, unit=100)[0] == [], \
        "a whole number of 31 or less is never checked (unchanged)"
