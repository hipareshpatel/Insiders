"""What the model is fed (AI-quality plan 2026-10-21, item 2): memory's figures with their basis and restatements,
the periods the filing prints withheld from memory, same-event marks, and each page's heading and unit."""
from __future__ import annotations

import json

from bse_intel.dossier import mark_same_event, merge, new_dossier, view_as_of
from bse_intel.extract import Document, page_header
from bse_intel.models import DealValue, Filing, Pass2Output
from bse_intel.periods import printed_periods
from bse_intel.results_card import history_from_view

Q1 = "2026-07-20T17:00:00+05:30"
Q2 = "2026-10-20T17:00:00+05:30"


def filing(news_id: str, filed_at: str) -> Filing:
    return Filing(news_id=news_id, scrip_code="999001", company_name="Demo Cement Ltd", headline="h",
                  filed_at=filed_at, filing_date=filed_at[:10])


def output(**delta) -> Pass2Output:
    return Pass2Output.model_validate({
        "is_material": True, "event_type": delta.pop("event_type", "RESULTS"),
        "card": {"impact_level": "HIGH", "headline": "Demo Cement results", "what_happened": ["Revenue ₹120 Cr"]},
        "timeline_entry": delta.pop("timeline", "Q2 results"), "dossier_delta": delta,
    })


def file_merge(*args, **kw):
    """set-up: with MEMORY_FILE_ONLY (owner, 30 Oct 2026) statement figures enter memory only as the exchange file's"""
    return merge(*args, by="file", **kw)


def metrics(*rows):
    return [{"metric": m, "period": p, "value": v} for m, p, v in rows]


def demo() -> dict:
    """Consolidated revenue for three quarters, a standalone-only revenue quarter, and Q1FY26 restated in Q1FY27."""
    d = new_dossier(filing("n0", "2025-08-01T17:00:00+05:30"))
    d = file_merge(d, output(financial_metrics=metrics(("revenue", "Q4FY25", 90.0))), filing("n00", "2025-05-10T17:00:00+05:30"),
              "HIGH", "now", basis="STANDALONE")
    d = file_merge(d, output(financial_metrics=metrics(("revenue", "Q1FY26", 100.0), ("pat", "Q1FY26", 9.0))),
              filing("n0", "2025-08-01T17:00:00+05:30"), "HIGH", "now", basis="CONSOLIDATED")
    d = file_merge(d, output(financial_metrics=metrics(("revenue", "Q2FY26", 104.0))),
              filing("n1", "2025-11-01T17:00:00+05:30"), "HIGH", "now", basis="CONSOLIDATED")
    d = file_merge(d, output(financial_metrics=metrics(("revenue", "Q1FY27", 110.0), ("revenue", "Q1FY26", 96.5))),
              filing("n2", Q1), "HIGH", "now", basis="CONSOLIDATED")
    return d


def test_memory_figures_carry_their_basis_and_restatement_and_one_basis_only():
    view = view_as_of(demo(), Q2)
    # Before: ["Q4FY25: 90 INR_CR", "Q1FY26: 96.5 INR_CR", "Q2FY26: 104 INR_CR", "Q1FY27: 110 INR_CR"] - a standalone
    # quarter among consolidated ones, and nothing to say Q1FY26 was 100 as first reported.
    assert view["metrics_basis"] == "consolidated"   # said once when every metric shares it
    assert view["metrics"]["revenue"] == [
        "Q1FY26: 96.5 INR_CR restated 2026-07-20, first reported 100", "Q2FY26: 104 INR_CR", "Q1FY27: 110 INR_CR"]
    # code still reads the figures from the lines
    assert {(h["period"], h["value"]) for h in history_from_view(view) if h["metric"] == "revenue"} == {
        ("Q1FY26", 96.5), ("Q2FY26", 104.0), ("Q1FY27", 110.0)}


def test_mixed_bases_tag_each_line():
    d = new_dossier(filing("n0", Q1))
    d = file_merge(d, output(financial_metrics=metrics(("pat", "Q4FY26", 5.0))), filing("a", "2026-05-10T17:00:00+05:30"),
              "HIGH", "now", basis="STANDALONE")
    d = file_merge(d, output(financial_metrics=metrics(("pat", "Q1FY27", 6.0))), filing("b", Q1), "HIGH", "now")
    d = file_merge(d, output(financial_metrics=metrics(("revenue", "Q1FY27", 60.0))), filing("c", Q1), "HIGH", "now",
              basis="CONSOLIDATED")
    view = view_as_of(d, Q2)
    assert "metrics_basis" not in view
    assert view["metrics"] == {"pat": ["Q4FY26: 5 INR_CR standalone", "Q1FY27: 6 INR_CR"],
                               "revenue": ["basis: consolidated", "Q1FY27: 60 INR_CR"]}


STATEMENT = ("Statement of Consolidated Unaudited Financial Results for the quarter and six months ended "
             "30 September 2026 (₹ in lakh)\nQuarter ended 30.09.2026 30.06.2026 30.09.2025 Six months ended "
             "Year ended 31 March 2026\nRevenue from operations 12,000 11,000 10,400")


def test_printed_periods_follow_the_statement_layout():
    assert printed_periods(STATEMENT, Q2) == {"Q2FY27", "Q1FY27", "Q2FY26", "H1FY27", "H1FY26", "FY26"}
    q4 = "Audited results for the quarter and year ended 31st March, 2026"
    assert printed_periods(q4, "2026-05-10") == {"Q4FY26", "Q3FY26", "Q4FY25", "FY26", "FY25"}
    assert printed_periods("Intimation of a board meeting", Q2) == set()


def test_periods_the_filing_prints_are_withheld_from_memory():
    """Kanoria / Star Health / Man Industries: memory's year-ago figure set against the filing's restated column."""
    view = view_as_of(demo(), Q2, printed=printed_periods(STATEMENT, Q2))
    assert view["metrics"]["revenue"] == ["Q1FY26: 96.5 INR_CR restated 2026-07-20, first reported 100"]
    assert "pat" in view["metrics"]   # Q1FY26 is not a column of a Q2 statement
    assert view["notes"][0].startswith("this filing prints Q2FY26, Q1FY27: memory's figures for these periods are withheld")
    assert list(view)[:3] == ["company", "metrics_basis", "notes"]   # read first


def _deal_dossier() -> dict:
    d = new_dossier(filing("n0", Q1))
    order = output(event_type="ORDER_WIN", timeline="Order of ₹608.67 Cr from Bharat Electronics Limited")
    order.card.deal_value = DealValue(kind="ORDER", amount_cr=608.67, counterparty="Bharat Electronics Limited")
    d = merge(d, order, filing("o1", "2026-10-15T17:00:00+05:30"), "HIGH", "now")
    old = output(event_type="ORDER_WIN", timeline="Order of ₹608.67 Cr from Bharat Electronics Limited")
    old.card.deal_value = DealValue(kind="ORDER", amount_cr=608.67, counterparty="Bharat Electronics Limited")
    return merge(d, old, filing("o0", "2026-08-01T17:00:00+05:30"), "HIGH", "now")


def test_same_counterparty_and_amount_days_before_is_marked_the_same_event():
    """Aarti / BEL: the press release after the exchange intimation was told as a second order."""
    text = "Press release: the Company has received an order from Bharat Electronics Ltd worth Rs. 60,867 lakh."
    view = view_as_of(_deal_dossier(), Q2, filing_text=text)
    marks = {d["date"]: d.get("same_event") for d in view["deals"]}
    assert marks == {"2026-10-15": True, "2026-08-01": None}   # 5 days before: marked; 80 days before: history
    assert [t.get("same_event") for t in view["recent_timeline"]] == [None, True]
    assert view["notes"][-1].startswith("items with same_event")
    # another client, or another amount: no mark
    assert mark_same_event(view_as_of(_deal_dossier(), Q2), "Order from Hindustan Aeronautics worth ₹608.67 Cr", Q2) == 1
    assert mark_same_event(view_as_of(_deal_dossier(), Q2), "Bharat Electronics order of ₹120 Cr", Q2) == 0
    assert "same_event" not in json.dumps(view_as_of(_deal_dossier(), Q2))   # code's view is unmarked


def test_page_header_names_heading_unit_and_scope():
    lic = "Demand order under GST\nThe Company has received an order demanding INR 99,09,87,896 including interest."
    assert page_header(lic) == ' · "Demand order under GST" · amounts in whole rupees (Indian digit grouping), not lakh or crore'
    seg = "Cyient Ltd\n12\nDET segment\n(₹ in lakh)\nRevenue 1,234.5 1,100.2"
    assert page_header(seg, {"cyient ltd"}) == ' · "DET segment" · scope: segment · amounts in ₹ lakh'
    mixed = "Notes\n(₹ in lakh) table one\n(₹ in crore) table two"
    assert page_header(mixed).endswith("units vary on this page: read each table's own header")


def test_select_text_heads_each_page_only_when_asked():
    pages = ["ACME LTD\nOutcome of board meeting\nThe board approved the results.",
             "ACME LTD\nSegment information\n(Rs. in Lakhs)\nSegment revenue 1,234.56 1,111.11",
             "ACME LTD\nStatement of results\n(₹ in crore)\nRevenue 12.3 11.1"]
    doc = Document.from_cache({"digital": pages, "has_image": [False] * 3})
    plain = doc.select_text(10_000)
    assert "--- Page 2 of 3 ---\n" in plain
    headed = doc.select_text(10_000, headers=True)
    assert '--- Page 2 of 3 · "Segment information" · scope: segment · amounts in ₹ lakh ---' in headed
    assert '--- Page 3 of 3 · "Statement of results" · amounts in ₹ crore ---' in headed
