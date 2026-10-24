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


def test_an_ebitda_its_own_filings_tell_two_ways_has_no_changes():
    """Shree Cement Q2FY27: the statement's EBITDA with other income (₹1,128.74 Cr) and the press release's without it
    (₹1,016 Cr), beside XBRL comparatives without it: the card said +15.9% YoY for -2.1% (daily audit, 23 Oct 2026)."""
    from bse_intel.dossier import results_snapshot

    def m(metric, period, value, *sources):
        srcs = [{"news_id": n, "as_of": "2026-10-23T12:00:00+05:30", "value": v, "unit": "INR_CR"} for n, v in sources]
        return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "as_of": "2026-10-23T12:00:00+05:30",
                "source_news_id": sources[0][0] if sources else "xbrl:res:500387:" + period, "sources": srcs}

    rows = [m(k, p, v) for p, vals in {"Q2FY26": (4761.07, 973.96, 309.82, 60.0), "Q1FY27": (6233.13, 1272.2, 531.12, 70.0)}.items()
            for k, v in zip(("revenue", "ebitda", "pat", "eps"), vals)]
    rows += [m("revenue", "Q2FY27", 5896.51, ("nse-1", 5896.51)), m("pat", "Q2FY27", 263.46, ("nse-1", 263.46)),
             m("eps", "Q2FY27", 72.56, ("nse-1", 72.56))]
    two = m("ebitda", "Q2FY27", 1128.74, ("nse-1", 1128.74), ("nse-2", 1016.0))
    snap = results_snapshot({"financial_metrics": rows + [two]}, "nse-1")
    assert snap["ebitda"] == {"value": 1128.74} and "yoy_pct" in snap["revenue"]
    one = m("ebitda", "Q2FY27", 1016.0, ("nse-1", 1016.0))
    assert "yoy_pct" in results_snapshot({"financial_metrics": rows + [one]}, "nse-1")["ebitda"]   # one reading keeps its changes


def test_keep_concurrent_writes_is_a_three_way_merge():
    from bse_intel.dossier import keep_concurrent_writes

    read = {"pledges": None, "governance": {"auditor": "A", "quarters": []}, "guidance": [1],
            "financial_metrics": [{"metric": "revenue", "period": "Q1FY27", "value": 1, "as_of": "a"}]}
    mine = {"pledges": None, "governance": {"auditor": "B", "quarters": []}, "guidance": [1, 2],
            "financial_metrics": [{"metric": "revenue", "period": "Q1FY27", "value": 1, "as_of": "a"},
                                  {"metric": "revenue", "period": "Q2FY27", "value": 2, "as_of": "b"}]}
    theirs = {"pledges": {"events": [1]}, "governance": {"auditor": "A", "quarters": [{"q": 1}]}, "guidance": [1],
              "financial_metrics": [{"metric": "revenue", "period": "Q1FY27", "value": 1, "as_of": "a"},
                                    {"metric": "pat", "period": "Q1FY27", "value": 9, "as_of": "c"},
                                    {"metric": "revenue", "period": "Q2FY27", "value": 99, "as_of": "c"}],
              "insider_trades": {"filings": ["x"]}}
    kept = keep_concurrent_writes(mine, read, theirs)
    assert mine["pledges"] == {"events": [1]} and mine["insider_trades"] == {"filings": ["x"]}   # only theirs changed
    assert mine["governance"] == {"auditor": "B", "quarters": [{"q": 1}]}                       # merged a level down
    assert mine["guidance"] == [1, 2]                                                            # only mine changed
    figures = {(m["metric"], m["period"]): m["value"] for m in mine["financial_metrics"]}
    assert figures == {("revenue", "Q1FY27"): 1, ("revenue", "Q2FY27"): 2, ("pat", "Q1FY27"): 9}   # mine wins a clash
    assert "pledges" in kept and "governance.quarters" in kept
    assert keep_concurrent_writes(mine, read, read) == [] and keep_concurrent_writes(mine, read, None) == []
