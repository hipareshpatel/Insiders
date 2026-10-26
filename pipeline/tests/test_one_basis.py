"""CARD_ONE_BASIS (live audit of 26 Oct 2026, class "two bases of one figure"): each case is a card of that audit, rebuilt from
its stored figures. Off by default: with the switch off nothing here changes a card."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bse_intel import one_basis
from bse_intel.models import Pass2Output
from bse_intel.settings import card_one_basis


def _out(card: dict) -> Pass2Output:
    return Pass2Output.model_validate({"is_material": True, "event_type": "RESULTS", "timeline_entry": card.pop("timeline", "t"),
                                       "card": {"impact_level": "MODERATE", "basis": "CONSOLIDATED", **card}})


def _rows(**series) -> list[dict]:
    return [{"metric": metric, "period": period, "value": value}
            for metric, by_period in series.items() for period, value in by_period.items()]


# L&T Technology Services, Q2FY27: total profit 548.7 holds a 168.6 gain on a sale (continuing 380.1)
LTTS_ROWS = _rows(pat={"Q2FY27": 548.7, "Q1FY27": 357.1, "Q2FY26": 329.2},
                  pat_owners={"Q2FY27": 548.2, "Q1FY27": 356.6, "Q2FY26": 328.7},
                  pat_continuing={"Q2FY27": 380.1, "Q1FY27": 352.3, "Q2FY26": 329.2})
LTTS_TAGGED = SimpleNamespace(period="Q2FY27", metrics=[])


def _ltts() -> Pass2Output:
    return _out({
        "headline": "L&T Technology Services Q2FY27: revenue ₹3,040.4 Cr, net profit ₹548.7 Cr (+66.7% YoY)",
        "takeaway": "Q2FY27: revenue ₹3,040.4 Cr, net profit ₹548.7 Cr (+66.7% YoY).",
        "what_happened": [{"text": "Net profit Q2FY27: ₹548.7 Cr (+66.7% YoY, +53.7% QoQ).", "quote": "- pat Q2FY27: 548.7 Cr"},
                          {"text": "Revenue from operations Q2FY27: ₹3,040.4 Cr (+3.4% QoQ).", "quote": "- revenue Q2FY27: 3040.4 Cr"}],
        "key_numbers": [{"label": "Net profit", "value": "₹548.70 Cr", "change": "+66.7% YoY"},
                        {"label": "Revenue", "value": "₹3,040.40 Cr", "change": "+3.4% QoQ"},
                        {"label": "EPS", "value": "₹35.78 per share", "change": "+15.3% YoY"}],
        "timeline": "Q2FY27 results (consolidated): revenue ₹3,040.4 Cr, net profit ₹548.7 Cr (+66.7% YoY)."})


def test_switch_is_off_by_default_and_reads_the_environment(monkeypatch):
    monkeypatch.delenv("CARD_ONE_BASIS", raising=False)
    assert card_one_basis() is False
    monkeypatch.setenv("CARD_ONE_BASIS", "1")
    assert card_one_basis() is True


def test_off_nothing_changes(monkeypatch):
    monkeypatch.delenv("CARD_ONE_BASIS", raising=False)
    out = _ltts()
    before = out.model_dump()
    assert one_basis.apply(out, LTTS_TAGGED, LTTS_ROWS) == []
    assert out.model_dump() == before
    card_json = {"basis": "STANDALONE", "results": {"period": "Q2FY27"}}
    assert one_basis.apply_card_json(card_json, {"financial_metrics": []}) == []
    assert card_json["results"] == {"period": "Q2FY27"}


def test_ltts_total_profit_is_labelled_with_the_discontinued_gain_and_the_eps_change_is_out(monkeypatch):
    monkeypatch.setenv("CARD_ONE_BASIS", "1")
    out = _ltts()
    notes = one_basis.apply(out, LTTS_TAGGED, LTTS_ROWS)
    card = out.card
    assert notes
    for text in (card.headline, card.takeaway, card.what_happened[0].text, out.timeline_entry):
        assert "includes ₹168.6 Cr from discontinued operations" in text and "continuing operations ₹380.1 Cr" in text
    assert "discontinued" in card.key_numbers[0].label
    # a line that is not about profit is left alone
    assert card.what_happened[1].text == "Revenue from operations Q2FY27: ₹3,040.4 Cr (+3.4% QoQ)."
    assert card.key_numbers[1].label == "Revenue"
    # continuing EPS against a total-profit comparative: no change is shown
    assert card.key_numbers[2].change is None


def test_a_line_that_already_names_its_basis_is_not_labelled_twice(monkeypatch):
    monkeypatch.setenv("CARD_ONE_BASIS", "1")
    out = _out({"headline": "LTTS net profit ₹548.7 Cr including discontinued operations",
                "what_happened": [{"text": "Profit from continuing operations ₹548.7 Cr.", "quote": None}]})
    assert one_basis.apply(out, LTTS_TAGGED, LTTS_ROWS) == []


def test_aurum_qoq_change_names_the_discontinued_gain_in_its_base(monkeypatch):
    """Aurum PropTech Q2FY27: profit 4.29 (continuing 4.07) against Q1FY27's 45.18, of which 44.51 was a sale gain: "-90.5% QoQ"."""
    monkeypatch.setenv("CARD_ONE_BASIS", "1")
    rows = _rows(pat={"Q2FY27": 4.29, "Q1FY27": 45.18}, pat_owners={"Q2FY27": 4.51, "Q1FY27": 45.57},
                 pat_continuing={"Q2FY27": 4.07, "Q1FY27": 0.67})
    out = _out({"headline": "Aurum Q2FY27: net profit to shareholders ₹4.51 Cr",
                "what_happened": [{"text": "Net profit Q2FY27: ₹4.29 Cr (-90.5% QoQ).", "quote": "- pat Q2FY27: 4.29 Cr, QoQ -90.5%"},
                                  {"text": "Revenue Q2FY27: ₹130.19 Cr (+16.4% QoQ).", "quote": "- revenue"}]})
    one_basis.apply(out, SimpleNamespace(period="Q2FY27", metrics=[]), rows)
    assert "Q1FY27 includes ₹44.51 Cr from discontinued operations" in out.card.what_happened[0].text
    assert out.card.what_happened[1].text == "Revenue Q2FY27: ₹130.19 Cr (+16.4% QoQ)."
    assert out.card.headline == "Aurum Q2FY27: net profit to shareholders ₹4.51 Cr"   # no change stated, own quarter clean


def test_shoppers_stop_non_gaap_figures_carry_their_basis(monkeypatch):
    """Shoppers Stop's call: revenue +7%, PAT ₹6 Cr are the company's non-GAAP; reported is +8.7% and ₹3 Cr."""
    quote = ("While on a non-GAAP consol basis, our revenues grew by 7%, and EBITDA grew by 56%, and as a result, we were able to "
             "turn around PAT from a loss of Rs 7 crores in last year to a profit of Rs 6 crores this year.")
    card = {"headline": "Shoppers Stop Q2 consolidated revenue grows 7% YoY; PAT turns positive to ₹6 Cr",
            "takeaway": "Q2 showed a turnaround.",
            "what_happened": [{"text": "Consolidated revenues grew **7% YoY** while EBITDA rose **56% YoY**.", "quote": quote},
                              {"text": "Store openings guided to 12 from 9-10.", "quote": "we are looking at 12 store openings this year."}],
            "key_numbers": [{"label": "PAT", "value": "₹6 Cr", "change": "Turnaround from ₹7 Cr loss", "quote": quote}]}
    monkeypatch.delenv("CARD_ONE_BASIS", raising=False)
    off = _out(dict(card))
    assert one_basis.apply(off, None, []) == [] and "non-GAAP" not in off.card.what_happened[0].text
    monkeypatch.setenv("CARD_ONE_BASIS", "1")
    out = _out(dict(card))
    notes = one_basis.apply(out, None, [])
    assert notes
    assert "non-GAAP basis" in out.card.what_happened[0].text
    assert "non-GAAP basis" in out.card.headline            # the headline states the same figures: it carries the label too
    assert out.card.what_happened[1].text == "Store openings guided to 12 from 9-10."
    assert "non-GAAP" in out.card.key_numbers[0].label


def test_a_line_already_saying_its_basis_is_not_labelled(monkeypatch):
    monkeypatch.setenv("CARD_ONE_BASIS", "1")
    quote = "On a non-GAAP consol basis revenues grew by 7%."
    out = _out({"headline": "Company results", "what_happened": [{"text": "Revenue grew 7% on the company's non-GAAP basis.", "quote": quote}]})
    assert one_basis.apply(out, None, []) == []


def _tmcv_dossier(basis: str) -> dict:
    return {"financial_metrics": [{"metric": "revenue", "period": "Q2FY27", "value": 25338.0,
                                   "sources": [{"news_id": "nse-1", "value": 25338.0, "basis": basis}]}]}


def _tmcv_card(basis: str) -> dict:
    return {"basis": basis, "event_type": "CONCALL_PRESENTATION", "key_numbers": [],
            "results": {"period": "Q2FY27", "revenue": {"value": 25338.0}, "ebitda": {"value": 1940.0, "prev_year": 17.0},
                        "lines": [{"key": "revenue"}, {"key": "ebitda"}]}}


def test_tmcv_standalone_card_does_not_show_a_consolidated_results_table(monkeypatch):
    monkeypatch.setenv("CARD_ONE_BASIS", "1")
    card = _tmcv_card("STANDALONE")
    notes = one_basis.apply_card_json(card, _tmcv_dossier("CONSOLIDATED"))
    assert card["results"] is None and "consolidated" in notes[0]


def test_a_table_on_the_cards_own_basis_stays(monkeypatch):
    monkeypatch.setenv("CARD_ONE_BASIS", "1")
    card = _tmcv_card("CONSOLIDATED")
    assert one_basis.apply_card_json(card, _tmcv_dossier("CONSOLIDATED")) == []
    assert card["results"] is not None


def test_the_results_pat_line_names_the_discontinued_part_of_a_comparison_period(monkeypatch):
    monkeypatch.setenv("CARD_ONE_BASIS", "1")
    dossier = {"financial_metrics": _rows(pat={"Q2FY27": 4.29, "Q1FY27": 45.18}, pat_continuing={"Q2FY27": 4.07, "Q1FY27": 0.67})}
    card = {"basis": "CONSOLIDATED", "event_type": "RESULTS", "key_numbers": [],
            "results": {"period": "Q2FY27", "lines": [{"key": "revenue"}, {"key": "pat", "label": "PAT"}]}}
    one_basis.apply_card_json(card, dossier)
    assert "Q1FY27 includes ₹44.51 Cr from discontinued operations" in card["results"]["lines"][1]["note"]


def test_lumax_presentation_ebitda_is_labelled_beside_the_filing_table(monkeypatch):
    """Lumax Auto's deck says EBITDA ₹228.2 Cr, 14.7%; the results table (the statement's own lines) says 209.49 Cr, 13.47%."""
    monkeypatch.setenv("CARD_ONE_BASIS", "1")
    card = {"basis": "CONSOLIDATED", "event_type": "CONCALL_PRESENTATION",
            "key_numbers": [{"label": "EBITDA", "value": "₹228.2 Cr"}, {"label": "EBITDA margin", "value": "14.7%"},
                            {"label": "Revenue", "value": "₹1,555.5 Cr"}],
            "results": {"period": "Q2FY27", "ebitda": {"value": 209.49}, "ebitda_margin": {"value": 13.47}, "lines": []}}
    one_basis.apply_card_json(card, {"financial_metrics": []})
    labels = [k["label"] for k in card["key_numbers"]]
    assert "presentation's own definition; results table ₹209.49 Cr" in labels[0]
    assert "results table 13.47%" in labels[1]
    assert labels[2] == "Revenue"


def test_a_presentation_ebitda_within_three_percent_of_the_table_is_left(monkeypatch):
    monkeypatch.setenv("CARD_ONE_BASIS", "1")
    card = {"basis": "CONSOLIDATED", "event_type": "CONCALL_PRESENTATION", "key_numbers": [{"label": "EBITDA", "value": "₹210 Cr"}],
            "results": {"period": "Q2FY27", "ebitda": {"value": 209.49}, "lines": []}}
    assert one_basis.apply_card_json(card, {"financial_metrics": []}) == []
    assert card["key_numbers"][0]["label"] == "EBITDA"


@pytest.mark.parametrize("value", [None, "", "x"])
def test_no_table_no_work(monkeypatch, value):
    monkeypatch.setenv("CARD_ONE_BASIS", "1")
    assert one_basis.apply_card_json({"basis": "STANDALONE", "results": value}, {}) == []
