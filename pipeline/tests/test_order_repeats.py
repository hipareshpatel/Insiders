"""One order counted once (round-2 re-run): an order's BSE intimation and its press release name the same client and
amount, and a press release listing the orders won since April is no order. Each test is a Magellanic Cloud card."""
from __future__ import annotations

from bse_intel.dossier import is_recap, merge, new_dossier
from bse_intel.models import Filing, Pass2Output
from bse_intel.signals import compute, misfires


def _filing(news_id: str, filed_at: str) -> Filing:
    return Filing(news_id=news_id, scrip_code="538891", company_name="Magellanic Cloud Ltd", headline="h",
                  filed_at=filed_at, filing_date=filed_at[:10])


def _order(amount: float, counterparty: str, stage: str = "LOA") -> Pass2Output:
    return Pass2Output.model_validate({
        "is_material": True, "event_type": "ORDER_WIN", "timeline_entry": "x",
        "card": {"impact_level": "LOW", "headline": f"Provigil wins ₹{amount} Cr order from {counterparty}",
                 "what_happened": ["x"],
                 "deal_value": {"kind": "ORDER", "amount_cr": amount, "stage": stage, "counterparty": counterparty}}})


def _flow(before, out, f):
    return next((s["text"] for s in compute(before, merge(before, out, f, "LOW", "now"), out, f, None)
                 if s["type"] == "ORDER_FLOW"), None)


def test_531d99a4_a_press_release_of_an_order_already_on_record_is_the_same_order():
    """d54e811f (intimation) and 531d99a4 (press release), both 6 Aug: ₹12.13 Cr from Western Railway, Ratlam."""
    d = new_dossier(_filing("n0", "2026-07-01T10:00:00+05:30"))
    d = merge(d, _order(12.76, "GAIL (India) Limited"), _filing("99f1c20d", "2026-07-30T18:00:00+05:30"), "LOW", "now")
    d = merge(d, _order(12.13, "Western Railway, Ratlam Division"), _filing("d54e811f", "2026-08-06T12:00:00+05:30"),
              "LOW", "now")
    repeat, f = _order(12.13, "Western Railway Ratlam Division"), _filing("531d99a4", "2026-08-06T17:00:00+05:30")
    assert _flow(d, repeat, f).startswith("Stage update, not a new order: the ₹12.13 Cr order first reported on 2026-08-06")
    assert len(merge(d, repeat, f, "LOW", "now")["deals"]) == 2

    # a different order from the same client weeks later is a new order
    later = _order(7.92, "Western Railway, Ratlam Division")
    assert _flow(d, later, _filing("969c382d", "2026-08-24T18:00:00+05:30")).startswith("3rd order on record")


def test_7fe943d3_a_recap_of_orders_won_is_no_order():
    """₹111.04 Cr "orders won since April" across railways, PNB, GAIL and DFCCIL, stored as one order, made later
    cards read "17th order, ₹291 Cr" and sized the recap at 62% of a quarter's revenue."""
    recap = "Indian Railways divisions, PNB, GAIL, DFCCIL, MANGA-group technology company, Manappuram Finance"
    assert is_recap("ORDER", recap) and not is_recap("ORDER", "Western Railway, Ratlam Division")
    # one client written with its address or its parent is one order, not a recap
    for one in ("South Central Railway, Secunderabad, Telangana",
                "Ministry of Road Transport and Highways, Government of India",
                "National Highways Authority of India (NHAI), New Delhi"):
        assert not is_recap("ORDER", one), one
    d = new_dossier(_filing("n0", "2026-07-01T10:00:00+05:30"))
    d = merge(d, _order(12.76, "GAIL (India) Limited"), _filing("99f1c20d", "2026-07-30T18:00:00+05:30"), "LOW", "now")
    out, f = _order(111.04, recap), _filing("7fe943d3", "2026-08-19T08:47:00+05:30")
    after = merge(d, out, f, "LOW", "now")
    assert [x["amount_cr"] for x in after["deals"]] == [12.76]
    assert _flow(d, out, f) is None
    assert misfires({"type": "SCALE", "text": "₹111.04 Cr order = 62% of Q1FY27 revenue"}, out)


def test_0f2061e4_memory_written_before_the_fix_counts_each_order_once():
    """Memory already held every railway order twice; ORDER_FLOW counts them once."""
    d = new_dossier(_filing("n0", "2026-07-01T10:00:00+05:30"))
    d["deals"] = [
        {"id": f"d_{i}", "kind": "ORDER", "amount_cr": amt, "stage": "LOA", "counterparty": who, "as_of": when,
         "source_news_id": f"s{i}"}
        for i, (amt, who, when) in enumerate([
            (12.13, "Western Railway, Ratlam Division", "2026-08-06T12:00:00+05:30"),
            (12.13, "Western Railway, Ratlam Division", "2026-08-06T17:00:00+05:30"),
            (3.73, "Dedicated Freight Corridor Corporation of India Limited", "2026-08-13T12:00:00+05:30"),
            (3.73, "Dedicated Freight Corridor Corporation o", "2026-08-13T17:00:00+05:30")])]
    out, f = _order(29.13, "Northern Railway, Moradabad Division"), _filing("2bc2ef91", "2026-10-16T18:00:00+05:30")
    assert _flow(d, out, f) == ("3rd order on record since 2026-08-06 (₹44.99 Cr in total); "
                                "the largest so far (previous high ₹12.13 Cr on 2026-08-06).")


def test_a_deal_size_echoed_with_its_decimal_moved_is_set_back():
    """Anlon (round 4): deal_value ₹153.3 Cr (8.59 Cr shares x ₹17.85), the timeline line "₹1,533 Cr", which memory carried
    into two later cards."""
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import deal_echo_slips

    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "ACQUISITION",
        "timeline_entry": "Board approved a preferential issue of 8.59 Cr shares for ₹1,533 Cr via share swap.",
        "card": {"impact_level": "MODERATE", "headline": "Anlon to buy two firms for ₹1,533 Cr in a share swap",
                 "what_happened": ["Issue of 8.59 Cr shares at ₹17.85 each"],
                 "deal_value": {"kind": "ACQUISITION", "amount_cr": 153.3}}})
    filing = "8,59,00,000 equity shares at Rs 17.85 per share; Apiqo Rs 116.52 Cr and Bizotic Rs 36.78 Cr."
    notes = deal_echo_slips(out, filing)
    assert out.timeline_entry.endswith("for ₹153.3 Cr via share swap.") and "₹153.3 Cr" in out.card.headline
    assert len(notes) == 2
    # an amount the filing itself prints is left alone, however it relates to the deal
    out.timeline_entry = "Total consideration ₹1,533 Cr."
    assert deal_echo_slips(out, filing + " Total consideration Rs 1,533 crore.") == []


def test_a_filing_that_continues_an_intimation_moves_that_deal_on():
    """Ceigall (round 5): an LoI "in continuation to our earlier intimation dated 08th September 2026" was written as a
    second order from the same department, and the order flow counted the one Bihar Lot-4 order twice."""
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import _stated_date, continued_deal

    def out():
        return Pass2Output.model_validate({
            "is_material": True, "event_type": "ORDER_WIN",
            "card": {"impact_level": "LOW", "headline": "Ceigall gets LoI for Bihar stone block", "what_happened": ["LoI"],
                     "deal_value": {"kind": "ORDER", "amount_cr": 28.82, "stage": "LOI"}}})

    view = {"deals": [{"id": "d_ceb282b4", "date": "2026-09-08", "kind": "ORDER", "amount_cr": 28.82, "stage": "OTHER"},
                      {"id": "d_other", "date": "2026-08-26", "kind": "ORDER", "amount_cr": 608.67}]}
    text = "In continuation to our earlier intimation dated 08th September 2026 and in accordance with Regulation 30"
    card = out()
    assert continued_deal(card, view, text) and card.card.deal_value.updates_deal_id == "d_ceb282b4"
    # no date stated, no deal that day, or two deals that day: left as written
    for other in ("Ceigall has received an LoI", "In continuation to our intimation dated 1st August 2026"):
        card = out()
        assert continued_deal(card, view, other) == [] and card.card.deal_value.updates_deal_id is None
    twice = {"deals": view["deals"] + [{"id": "d_twin", "date": "2026-09-08", "kind": "ORDER"}]}
    assert continued_deal(out(), twice, text) == []
    assert str(_stated_date("September 8, 2026")) == str(_stated_date("08.09.2026")) == "2026-09-08"


def test_a_call_transcript_is_never_a_repeat_of_its_results():
    """Owner, 2026-10-19: transcripts get their own card for their forward-looking statements. Round 5's Texmaco Q1
    transcript had been set aside as its results card "in other words"."""
    from bse_intel.models import Filing
    from bse_intel.pipeline import is_transcript

    def filing(headline, subject="Analysts/Institutional Investor Meet/Con. Call Updates"):
        return Filing(news_id="nse-1", scrip_code="533326", company_name="Texmaco Rail & Engineering Limited",
                      headline=headline, subject=subject, filed_at="2026-08-10T10:00:00+05:30", filing_date="2026-08-10")

    assert is_transcript(filing("Texmaco Rail & Engineering Limited has informed the Exchange about Transcript"))
    assert is_transcript(filing("Transcripts of the earnings call for Q1FY27"))
    assert not is_transcript(filing("Texmaco Rail & Engineering Limited has informed the Exchange about Investor Presentation"))
