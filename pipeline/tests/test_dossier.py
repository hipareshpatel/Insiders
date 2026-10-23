"""Deals in memory: an order told again is not a new card (dossier.repeated_order)."""


def test_a_press_release_of_an_order_already_on_record_is_a_repeat():
    from bse_intel.dossier import repeated_order
    from bse_intel.models import DealValue

    on_record = [{"id": "d_31c72c9f", "kind": "ORDER", "amount_cr": 3.16, "stage": "LOA", "as_of": "2026-10-23T09:37:00+05:30",
                  "source_news_id": "nse-106825823", "counterparty": "Dedicated Freight Corridor Corporation of India Limited"}]
    press = DealValue(kind="ORDER", amount_cr=3.16, stage="LOA", counterparty="DFCCIL - Dedicated Freight Corridor Corporation")
    same = DealValue(kind="ORDER", amount_cr=3.16, stage="LOA", counterparty="Dedicated Freight Corridor Corporation of India")
    assert repeated_order(on_record, same, "2026-10-23T09:49:00+05:30", "nse-106825832")["id"] == "d_31c72c9f"
    assert repeated_order(on_record, press, "2026-10-23T09:49:00+05:30", "nse-106825832") is None   # another client key
    later = DealValue(kind="ORDER", amount_cr=3.16, stage="CONTRACT", counterparty="Dedicated Freight Corridor Corporation of India")
    assert repeated_order(on_record, later, "2026-11-02T10:00:00+05:30", "nse-2") is None             # the next stage is news
    bigger = DealValue(kind="ORDER", amount_cr=9.5, stage="LOA", counterparty="Dedicated Freight Corridor Corporation of India")
    assert repeated_order(on_record, bigger, "2026-10-24T10:00:00+05:30", "nse-3") is None              # another order
    assert repeated_order(on_record, same, "2026-10-23T09:37:00+05:30", "nse-106825823") is None        # its own re-run
    linked = DealValue(kind="ORDER", amount_cr=3.16, stage="LOA", updates_deal_id="d_31c72c9f")
    assert repeated_order(on_record, linked, "2026-10-23T09:49:00+05:30", "nse-106825832")["id"] == "d_31c72c9f"
    months_later = DealValue(kind="ORDER", amount_cr=3.16, stage="LOA", updates_deal_id="d_31c72c9f")
    assert repeated_order(on_record, months_later, "2027-03-17T10:00:00+05:30", "nse-4") is None      # news about the order
    staged = [{**on_record[0], "history": [
        {"stage": "LOI", "amount_cr": 3.16, "as_of": "2026-10-01T10:00:00+05:30", "source_news_id": "nse-1"},
        {"stage": "LOA", "amount_cr": 3.16, "as_of": "2026-10-23T09:37:00+05:30", "source_news_id": "nse-106825823"}]}]
    assert repeated_order(staged, same, "2026-10-23T09:49:00+05:30", "nse-106825832")["repeats"] == "nse-106825823"


def test_a_call_figure_on_another_definition_is_not_stored_as_the_line():
    from bse_intel.dossier import other_definition

    memory = {("revenue", "Q2FY26"): {"value": 740.38}, ("revenue", "Q1FY27"): {"value": 506.17},
              ("pat", "Q2FY26"): {"value": 402.99}, ("pat", "Q1FY27"): {"value": 349.38}}
    # Godrej Properties' deck: Total Income ₹2,575 Cr, +38% YoY and +93% QoQ, beside revenue from operations
    assert other_definition(memory, ("revenue", "Q2FY27"), 2575.0, "INR_CR", 38.0, 93.0)
    assert not other_definition(memory, ("pat", "Q2FY27"), 154.0, "INR_CR", -62.0, -56.0)   # follows: kept
    assert not other_definition(memory, ("revenue", "Q2FY27"), 2575.0, "INR_CR", None, None)  # nothing stated
    assert not other_definition(memory, ("revenue", "Q2FY27"), 2575.0, "INR_CR", 38.0, 409.0)  # one change follows
    assert not other_definition({}, ("revenue", "Q2FY27"), 2575.0, "INR_CR", 38.0, 93.0)       # no comparatives
