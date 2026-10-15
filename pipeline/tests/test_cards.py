"""Card quality checks, using wording from real BSE filings (public disclosures).

Each case comes from a published card that went wrong or right: a generic headline,
an order called the "first" when the filing says "second", Indian digit grouping,
₹ million figures, GST-inclusive order values and repeat orders.
"""

from __future__ import annotations

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
    assert out.card.what_happened[0] == "Q4FY25 revenue ₹83.9 Cr vs ₹81.2 Cr in Q4FY24; FY25 PAT ₹100.9 Cr"
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
