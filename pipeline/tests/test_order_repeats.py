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
