"""CARD_GROUNDED_FIGURES: three right figures our own code damaged, found by the live audit of 26 Oct 2026."""

from __future__ import annotations

from pathlib import Path

from bse_intel import event_xbrl as ex
from bse_intel import gate
from bse_intel.dossier import results_snapshot
from bse_intel.models import Card, Filing, Pass2Output
from bse_intel.pipeline import apply_deal_guards

FIX = Path(__file__).parent / "fixtures"


def _order_in_crore():
    """DSSL's event file gave the order's amount as 137.15 (crore), the field the reader takes as rupees."""
    raw = (FIX / "nse_event_railtel_order_20261018.xml").read_bytes().replace(b">1675200000<", b">137.15<")
    f = ex.parse(raw, "dssl")
    return ex.Match(ex.EventFile("1", "DSSL", "para-b", "Bagging/Receiving of orders/contracts", None, "x", None, None, "Original", None),
                    f, "content")


def _order_card():
    return Card.model_validate({"impact_level": "LOW", "headline": "DSSL wins a Supreme Court order", "what_happened": ["x"],
                                "deal_value": {"kind": "ORDER", "amount_cr": 137.15}})


def test_an_order_amount_in_crore_is_not_put_on_the_deal_as_zero(monkeypatch):
    monkeypatch.delenv("CARD_GROUNDED_FIGURES", raising=False)
    (order,) = ex.orders([_order_in_crore()])
    assert order.amount_cr == 0.0                       # off: what it was
    card = _order_card()
    ex.apply_orders(card, [order])
    assert card.deal_value.amount_cr == 0.0
    monkeypatch.setenv("CARD_GROUNDED_FIGURES", "1")
    assert ex.orders([_order_in_crore()]) == []         # on: no figure rather than a wrong one
    card = _order_card()
    ex.apply_orders(card, ex.orders([_order_in_crore()]))
    assert card.deal_value.amount_cr == 137.15


OMAXE_ROW = ("Withdrawal/cancellation or suspension of Not Applicable \nlicence/ approval by the regulatory or \n"
             "licensing authority, with reasons for such impact (monetary or otherwise) along \nwith corrective actions taken "
             "by the listed \nentity pursuant to the \nwithdrawal, \ncancellation or suspension of the key \nlicense/ approval")
OMAXE_TEXT = "Omaxe Limited has received RERA Registration Certificate in one of its projects.\n" + OMAXE_ROW


def _omaxe():
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "LITIGATION_REGULATORY", "timeline_entry": "RERA registration",
        "card": {"impact_level": "LOW", "headline": "Omaxe receives RERA approval", "what_happened": ["x"],
                 "deal_value": {"kind": "OTHER", "amount_cr": None, "stage": "CANCELLED"}}})
    filing = Filing(news_id="nse-106820971", scrip_code="532880", company_name="Omaxe", headline=OMAXE_ROW, subject="",
                    filed_at="2026-10-17T12:21:27+05:30", filing_date="2026-10-17")
    return out, filing


def test_the_template_withdrawal_row_does_not_cancel_a_deal(monkeypatch):
    monkeypatch.delenv("CARD_GROUNDED_FIGURES", raising=False)
    out, filing = _omaxe()
    apply_deal_guards(out, filing, [], [], OMAXE_TEXT)
    assert out.card.deal_value.stage == "CANCELLED"     # off: what it was
    monkeypatch.setenv("CARD_GROUNDED_FIGURES", "1")
    out, filing = _omaxe()
    apply_deal_guards(out, filing, [], [], OMAXE_TEXT)
    assert out.card.deal_value.stage != "CANCELLED"


def test_a_real_withdrawal_still_cancels(monkeypatch):
    monkeypatch.setenv("CARD_GROUNDED_FIGURES", "1")
    assert gate.is_terminated("The Board has withdrawn the proposed acquisition") is True
    assert gate.is_terminated(OMAXE_TEXT) is False


def _emmvee():
    def kpi(period, value, unit, news):
        src = {"news_id": news, "as_of": "2026-10-14T19:00:00+05:30", "value": value, "unit": unit, "basis": "CONSOLIDATED"}
        return {"metric": "order_book", "period": period, "value": value, "unit": unit, "as_of": src["as_of"],
                "source_news_id": news, "sources": [src]}

    def row(metric, value):
        src = {"news_id": "nse-1", "as_of": "2026-10-14T19:00:00+05:30", "value": value, "unit": "INR_CR", "basis": "CONSOLIDATED"}
        return {"metric": metric, "period": "Q2FY27", "value": value, "unit": "INR_CR", "as_of": src["as_of"],
                "source_news_id": "nse-1", "sources": [src]}

    return {"financial_metrics": [row("revenue", 1576.38), row("ebitda", 556.88), row("pbt", 500.0), row("pat", 382.05),
                                  kpi("Q2FY27", 10404.0, "MW", "nse-1"), kpi("Q1FY27", 9.9, "GW", "nse-0")]}


FOOTER = [{"metric": "order_book", "label": "Order book", "format": "cr", "aliases": ["order_book_cr", "orderbook"]}]


def test_an_order_book_in_megawatts_is_not_shown_as_crore_with_a_change(monkeypatch):
    monkeypatch.delenv("CARD_GROUNDED_FIGURES", raising=False)
    off = results_snapshot(_emmvee(), "nse-1", FOOTER)
    assert off["kpi:order_book"]["qoq_pct"] == 104990.9           # off: what it was
    monkeypatch.setenv("CARD_GROUNDED_FIGURES", "1")
    on = results_snapshot(_emmvee(), "nse-1", FOOTER)
    assert "kpi:order_book" not in on and all(line["key"] != "kpi:order_book" for line in on["lines"])
    assert on["revenue"]["value"] == 1576.38


def test_a_kpi_in_its_promised_unit_keeps_its_figure_but_not_a_base_in_another_unit(monkeypatch):
    monkeypatch.setenv("CARD_GROUNDED_FIGURES", "1")
    d = _emmvee()
    d["financial_metrics"][-2]["unit"] = "INR_CR"
    d["financial_metrics"][-2]["sources"][0]["unit"] = "INR_CR"
    row = results_snapshot(d, "nse-1", FOOTER)["kpi:order_book"]
    assert row == {"value": 10404.0}
