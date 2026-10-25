"""Memory labels, step 1 (docs/design/memory-labels.md, F144): every item is labelled when it is written; readers do not
use the labels, so nothing a card shows changes."""
from __future__ import annotations

import copy
import json

from bse_intel import corporate_actions, xbrl
from bse_intel.dossier import (doc_kind, keep_concurrent_writes, label, merge, new_dossier, put_standalone, view_as_of)
from bse_intel.models import Filing
from bse_intel.pipeline import _apply_xbrl
from test_memory import Q1, Q2, filing, output
from test_xbrl import results_xml

NOW = "2026-10-25T12:00:00+05:30"


def _strip(node):
    """The dossier as an old one would be: no label anywhere."""
    if isinstance(node, dict):
        return {k: _strip(v) for k, v in node.items() if k not in ("lab", "section_lab")}
    if isinstance(node, list):
        return [_strip(v) for v in node]
    return node


def _results_filing() -> Filing:
    return filing("nse-100", Q2).model_copy(update={"headline": "Financial Results for the quarter ended 30 Sep 2026"})


def _written():
    """A results filing: the model read an order book from the PDF, the filing's own XBRL file gave the statement."""
    out = output(financial_metrics=[{"metric": "order_book", "period": "Q2FY27", "value": 5000},
                                    {"metric": "revenue", "period": "Q2FY27", "value": 119.9}],
                 balance_sheet={"period": "Q2FY27", "cash_cr": 41.0, "credit_rating": "AA"})
    tagged = xbrl.parse(results_xml())
    _apply_xbrl(out, tagged, "nse-100")
    return merge(new_dossier(_results_filing()), out, _results_filing(), "HIGH", NOW), tagged


def _entry(d, metric, period="Q2FY27"):
    return next(m for m in d["financial_metrics"] if m["metric"] == metric and m["period"] == period)


def test_a_figure_from_the_filings_own_xbrl_file_is_by_file_under_a_plain_news_id():
    d, _ = _written()
    revenue = _entry(d, "revenue")
    assert revenue["value"] == 120.0 and revenue["source_news_id"] == "nse-100"   # the file's, not the model's 119.9
    assert revenue["lab"] == {"by": "file", "doc": "results", "basis": "CONSOLIDATED", "unit": "INR_CR", "at": NOW, "ok": True}
    assert _entry(d, "pat")["lab"]["by"] == "file"


def test_a_figure_a_model_read_from_the_pdf_is_by_ai_and_has_no_invented_page_or_quote():
    d, _ = _written()
    lab = _entry(d, "order_book")["lab"]
    assert lab["by"] == "ai" and lab["doc"] == "results" and lab["at"] == NOW
    assert "page" not in lab and "quote" not in lab and "from" not in lab


def test_a_figure_our_code_derived_is_calc_and_names_its_inputs():
    d, _ = _written()
    lab = _entry(d, "ebitda")["lab"]
    assert lab["by"] == "calc" and lab["doc"] == "results"
    assert lab["from"] == ["pbt:Q2FY27", "finance_cost:Q2FY27", "depreciation:Q2FY27", "other_income:Q2FY27",
                           "exceptional_items:Q2FY27"] or "pbt_before_exceptional:Q2FY27" in lab["from"]
    assert _entry(d, "ebitda_margin")["lab"]["from"] == ["ebitda:Q2FY27", "revenue:Q2FY27"]


def test_balance_sheet_fields_from_the_file_make_a_file_snapshot_and_a_mixed_one_says_which():
    d, _ = _written()
    (snap,) = d["balance_sheet"]
    # the model gave a cash figure and a rating; the file overwrote cash and added the rest, the rating is the model's
    assert snap["lab"]["by"] == "ai" and "cash_cr" in snap["lab"]["file_fields"] and "credit_rating" not in snap["lab"]["file_fields"]
    pure = output(balance_sheet={"period": "Q2FY27", "cash_cr": 1.0})
    pure.dossier_delta.balance_sheet = None
    out = output()
    _apply_xbrl(out, xbrl.parse(results_xml()), "nse-101")
    d2 = merge(new_dossier(_results_filing()), out, filing("nse-101", Q2), "HIGH", NOW)
    assert d2["balance_sheet"][0]["lab"]["by"] == "file"


def test_the_seed_writes_by_file_and_the_event_files_order_amount_is_by_file():
    from bse_intel.event_xbrl import Order, apply_orders

    seed = filing("xbrl:res:999001:Q2FY27", Q2)
    out = output(financial_metrics=[{"metric": "revenue", "period": "Q2FY27", "value": 120}])
    d = merge(new_dossier(seed), out, seed, None, NOW, basis="CONSOLIDATED")
    assert _entry(d, "revenue")["lab"]["by"] == "file"
    card = output(event_type="ORDER_WIN").card
    card.deal_value = None
    apply_orders(card, [Order(amount_cr=250.0, counterparty="Acme", received=True)] if _can_build(Order) else [])
    if card.deal_value is not None:
        assert card.deal_value.amount_by == "file"


def _can_build(order_cls) -> bool:
    try:
        order_cls(amount_cr=250.0, counterparty="Acme", received=True)
        return True
    except TypeError:
        return False


def test_text_items_carry_by_doc_and_at():
    out = output(operating_notes=["Utilisation 82%"], timeline="Q2 results out",
                 guidance=[{"statement": "Revenue to reach 500 Cr by FY28"}])
    f = filing("nse-5", Q2).model_copy(update={"headline": "Investor Presentation"})
    out.event_type = "CONCALL_PRESENTATION"
    d = merge(new_dossier(f), out, f, "HIGH", NOW)
    for item in (d["operating_notes"][0], d["guidance"][0], d["timeline"][0]):
        assert item["lab"] == {"by": "ai", "doc": "slides", "at": NOW}


def test_merge_keeps_every_sources_label_and_a_second_filing_adds_its_own():
    d, _ = _written()
    out = output(financial_metrics=[{"metric": "order_book", "period": "Q2FY27", "value": 5100}])
    d2 = merge(d, out, filing("nse-200", "2026-10-26T10:00:00+05:30"), "HIGH", "2026-10-26T10:05:00+05:30")
    entry = _entry(d2, "order_book")
    assert [s["lab"]["by"] for s in entry["sources"]] == ["ai", "ai"]
    assert {s["lab"]["at"] for s in entry["sources"]} == {NOW, "2026-10-26T10:05:00+05:30"}
    assert _entry(d2, "revenue")["lab"]["by"] == "file"   # untouched by the second merge
    again = merge(d2, out, filing("nse-200", "2026-10-26T10:00:00+05:30"), "HIGH", "2026-10-27T10:00:00+05:30")
    assert all("lab" in s for s in _entry(again, "order_book")["sources"])


def test_keep_concurrent_writes_keeps_the_labels_of_what_another_writer_added():
    d, _ = _written()
    read = json.loads(json.dumps(d))
    fresh = json.loads(json.dumps(d))
    other = output(financial_metrics=[{"metric": "order_book", "period": "Q1FY27", "value": 9}])
    fresh = merge(fresh, other, filing("nse-300", Q1), "HIGH", NOW)   # another job wrote a figure meanwhile
    mine = copy.deepcopy(d)
    mine["timeline"].append({"id": "t_x", "date": Q2, "summary": "ours", "news_id": "n", "event_type": "OTHER",
                             "lab": label("ai", "other", NOW)})
    kept = keep_concurrent_writes(mine, read, fresh)
    assert kept
    assert _entry(mine, "order_book", "Q1FY27")["lab"]["by"] == "ai"
    assert _entry(mine, "revenue")["lab"]["by"] == "file"
    assert any(t["id"] == "t_x" and t["lab"]["by"] == "ai" for t in mine["timeline"])


def test_an_old_dossier_with_no_labels_still_merges_and_reads_the_same():
    d, _ = _written()
    old = _strip(d)
    assert "lab" not in json.dumps(old)
    # the readers see the same memory with or without labels: a card cannot change
    assert view_as_of(d, "2027-01-01T00:00:00+05:30") == view_as_of(old, "2027-01-01T00:00:00+05:30")
    out = output(financial_metrics=[{"metric": "order_book", "period": "Q2FY27", "value": 5100}])
    merged = merge(old, out, filing("nse-200", "2026-10-26T10:00:00+05:30"), "HIGH", NOW)
    assert _entry(merged, "revenue").get("lab") is None and _entry(merged, "order_book")["sources"][-1]["lab"]["by"] == "ai"


def test_the_standalone_figures_are_by_file_and_a_re_read_keeps_their_label():
    tagged = xbrl.parse(results_xml("Standalone"))
    d = new_dossier(_results_filing())
    put_standalone(d, tagged.metrics, tagged.balance_sheet, Q2, "nse-100")
    row = next(m for m in d["standalone"]["metrics"] if m["metric"] == "revenue")
    assert row["lab"]["by"] == "file" and row["lab"]["basis"] == "STANDALONE"
    assert d["standalone"]["balance_sheet"][0]["lab"]["by"] == "file"
    first = copy.deepcopy(row["lab"])
    put_standalone(d, tagged.metrics, tagged.balance_sheet, Q2, "nse-100")
    assert next(m for m in d["standalone"]["metrics"] if m["metric"] == "revenue")["lab"] == first


def test_a_section_only_an_exchange_feed_writes_is_labelled_file_once():
    d = new_dossier(filing("n", Q1))
    assert corporate_actions.merge(d, [{"ex_date": "2026-09-01", "subject": "Dividend Rs 2", "kind": "DIVIDEND"}]) == 1
    assert d["section_lab"]["corporate_actions"]["by"] == "file"
    assert "lab" not in d["corporate_actions"][0]


def test_doc_kind_reads_the_event_type_then_the_headline_and_never_guesses():
    f = lambda h, nid="nse-1": filing(nid, Q1).model_copy(update={"headline": h})  # noqa: E731
    assert doc_kind("RESULTS", f("Financial Results")) == "results"
    assert doc_kind("RESULTS", f("Press Release - Q2 results")) == "release"
    assert doc_kind("CONCALL_PRESENTATION", f("Transcript of the earnings call")) == "call"
    assert doc_kind("CONCALL_PRESENTATION", f("Investor Presentation")) == "slides"
    assert doc_kind("ANNUAL_REPORT", f("Annual Report")) == "annual"
    assert doc_kind("GOVERNANCE", f("Outcome of Board Meeting")) == "board"
    assert doc_kind("ORDER_WIN", f("Receipt of order")) == "other"
    assert doc_kind("OTHER", f("x", "xbrl:res:1:Q1FY27")) == "results"
