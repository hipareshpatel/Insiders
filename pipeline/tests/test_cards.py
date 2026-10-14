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
    assert view["deals"][-1] == {"date": "2026-08-02", "kind": "ORDER", "amount_cr": 207.47, "stage": "LOI"}

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
