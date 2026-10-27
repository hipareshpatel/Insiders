"""CARD_RESULTS_ONE_LINE (F206; live audit of 26 Oct 2026, class "two bases in the results block"): each case is a card of that
audit, rebuilt from its stored figures. Off by default: with the switch off nothing here changes a table or a card."""

from __future__ import annotations

import copy

import pytest

from bse_intel import results_one_line
from bse_intel.dossier import results_snapshot
from bse_intel.settings import card_results_one_line

NID = "nse-1"
TAGGED = {"by": "file", "doc": "results"}
STATED = {"by": "ai", "doc": "call"}


def _m(metric, period, value, news_id=NID, lab=None):
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "as_of": "2026-10-26T10:00:00",
            "source_news_id": news_id, "basis": "CONSOLIDATED", **({"lab": lab} if lab else {})}


def _dossier(rows):
    return {"financial_metrics": rows}


@pytest.fixture(autouse=True)
def _off(monkeypatch):
    monkeypatch.delenv("CARD_RESULTS_ONE_LINE", raising=False)


def _on(monkeypatch):
    monkeypatch.setenv("CARD_RESULTS_ONE_LINE", "1")


# Five Star, Q2FY27: total income 875.0 against comparatives that are revenue from operations
FIVESTAR = _dossier([
    _m("total_revenue", "Q2FY27", 875.0, lab=TAGGED), _m("pat", "Q2FY27", 299.32, lab=TAGGED),
    _m("revenue", "Q2FY26", 799.44, "xbrl:res:1:Q2FY26", TAGGED), _m("revenue", "Q1FY27", 828.98, "xbrl:res:1:Q1FY27", TAGGED),
    _m("pat", "Q2FY26", 286.0, "xbrl:res:1:Q2FY26", TAGGED), _m("pat", "Q1FY27", 290.0, "xbrl:res:1:Q1FY27", TAGGED)])


def test_switch_is_off_by_default_and_reads_the_environment(monkeypatch):
    assert card_results_one_line() is False
    _on(monkeypatch)
    assert card_results_one_line() is True


def test_off_the_table_and_the_card_are_unchanged():
    table = results_snapshot(FIVESTAR, NID)
    assert table["revenue"]["yoy_pct"] == 9.5 and results_one_line.NOTES_KEY not in table   # the live card's wrong +9.5%
    card = {"headline": "Acme: revenue ₹1,153 Cr", "key_numbers": [{"label": "EBITDA", "value": "₹189 Cr"}],
            "results": {"revenue": {"value": 1131.87}, "ebitda": {"value": 169.47}, "one_line": ["x"]}}
    before = copy.deepcopy(card)
    assert results_one_line.apply_card_json(card) == [] and card == before


def test_fivestar_total_income_with_no_total_income_comparatives_has_no_change(monkeypatch):
    _on(monkeypatch)
    table = results_snapshot(FIVESTAR, NID)
    row = table["revenue"]
    assert row["value"] == 875.0
    assert "prev_year" not in row and "yoy_pct" not in row and "prev_quarter" not in row and "qoq_pct" not in row
    assert next(s for s in table["lines"] if s["key"] == "revenue")["label"] == "Total income"
    assert len(table["one_line"]) == 3 and "total income" in table["one_line"][0]
    assert table["pat"]["yoy_pct"] == 4.7   # the other rows are untouched
    card = {"results": table}
    logged = list(table["one_line"])
    assert results_one_line.apply_card_json(card) == logged
    assert "one_line" not in card["results"]   # the notes moved to the change log


def test_fivestar_comparatives_are_recomputed_from_total_income_when_the_tagged_data_has_it(monkeypatch):
    _on(monkeypatch)
    rows = copy.deepcopy(FIVESTAR["financial_metrics"]) + [
        _m("total_income", "Q2FY26", 810.2, "xbrl:res:1:Q2FY26", TAGGED), _m("total_income", "Q1FY27", 841.4, "xbrl:res:1:Q1FY27", TAGGED)]
    row = results_snapshot(_dossier(rows), NID)["revenue"]
    assert row["prev_year"] == 810.2 and row["yoy_pct"] == 8.0   # the true +8% / +4% of the audit
    assert row["prev_quarter"] == 841.4 and row["qoq_pct"] == 4.0


def test_a_revenue_row_on_one_line_is_left_as_it_was(monkeypatch):
    rows = [_m("revenue", "Q2FY27", 900.0, lab=TAGGED), _m("pat", "Q2FY27", 90.0, lab=TAGGED),
            _m("revenue", "Q2FY26", 800.0, "xbrl:res:1:Q2FY26", TAGGED), _m("revenue", "Q1FY27", 850.0, "xbrl:res:1:Q1FY27", TAGGED)]
    off = results_snapshot(_dossier(rows), NID)
    _on(monkeypatch)
    assert results_snapshot(_dossier(rows), NID) == off


# Gravita, Q2FY27: this quarter's EBITDA worked out from the file (169.47), the comparatives the company's own (133.0, 192)
def _grw(parts_prior=True):
    rows = [_m("revenue", "Q2FY27", 695.3, lab=TAGGED), _m("pat", "Q2FY27", 129.0, lab=TAGGED),
            _m("ebitda", "Q2FY27", 169.47, lab=TAGGED), _m("ebitda_margin", "Q2FY27", 24.37, lab=TAGGED),
            _m("revenue", "Q2FY26", 568.0, "xbrl:res:2:Q2FY26", TAGGED), _m("revenue", "Q1FY27", 633.0, "xbrl:res:2:Q1FY27", TAGGED),
            _m("ebitda", "Q2FY26", 133.0, "call-1", STATED), _m("ebitda", "Q1FY27", 192.0, "call-2", STATED),
            _m("ebitda_margin", "Q2FY26", 23.4, "call-1", STATED), _m("ebitda_margin", "Q1FY27", 30.3, "call-2", STATED)]
    if parts_prior:   # the tagged parts of Q2FY26: 110 + 12 + 16 - 4 = 134.0
        rows += [_m("pbt", "Q2FY26", 110.0, "xbrl:res:2:Q2FY26", TAGGED), _m("finance_cost", "Q2FY26", 12.0, "xbrl:res:2:Q2FY26", TAGGED),
                 _m("depreciation", "Q2FY26", 16.0, "xbrl:res:2:Q2FY26", TAGGED), _m("other_income", "Q2FY26", 4.0, "xbrl:res:2:Q2FY26", TAGGED)]
    return _dossier(rows)


def test_grwrhitech_off_shows_the_mixed_bases(monkeypatch):
    row = results_snapshot(_grw(), NID)["ebitda"]
    assert row["prev_year"] == 133.0 and row["yoy_pct"] == 27.4   # the audit's +27.4% on the company's 133.0


def test_grwrhitech_comparatives_are_worked_out_the_same_way_or_dropped(monkeypatch):
    _on(monkeypatch)
    table = results_snapshot(_grw(), NID)
    row, margin = table["ebitda"], table["ebitda_margin"]
    assert row["value"] == 169.47 and row["prev_year"] == 134.0 and row["yoy_pct"] == 26.5   # worked out from the tagged parts
    assert "prev_quarter" not in row and "qoq_pct" not in row                                # no tagged parts for Q1FY27
    assert margin["prev_year"] == round(134.0 / 568.0 * 100, 2) and "prev_quarter" not in margin and "qoq_bps" not in margin
    assert margin["yoy_bps"] == round((24.37 - margin["prev_year"]) * 100)
    assert any("stated figure" in n for n in table["one_line"])
    bare = results_snapshot(_grw(parts_prior=False), NID)
    assert "prev_year" not in bare["ebitda"] and "yoy_pct" not in bare["ebitda"] and "prev_year" not in bare["ebitda_margin"]


# LMW: the headline states the CFO's spoken revenue, the block the statement's
def test_lmw_headline_revenue_on_another_basis_is_labelled(monkeypatch):
    _on(monkeypatch)
    card = {"headline": "LMW Q2FY27: revenue rises 30% to ₹1,153 Cr, orders strong",
            "key_numbers": [{"label": "Revenue", "value": "₹1,153 Cr", "change": "+30% YoY"}],
            "results": {"revenue": {"value": 1131.87}, "lines": [{"key": "revenue", "label": "Revenue"}]}}
    notes = results_one_line.apply_card_json(card)
    assert card["headline"].endswith("(company-reported; results table ₹1,131.87 Cr)")
    assert card["key_numbers"][0]["label"] == "Revenue (company-reported; results table ₹1,131.87 Cr)"
    assert len(notes) == 2 and notes[0].startswith("key_numbers") and notes[1].startswith("headline")
    # run again: a labelled headline and key number are left alone
    assert results_one_line.apply_card_json(card) == []


def test_a_headline_on_the_blocks_figure_is_not_touched(monkeypatch):
    _on(monkeypatch)
    card = {"headline": "LMW Q2FY27: revenue ₹1,131.87 Cr", "key_numbers": [{"label": "Revenue", "value": "₹1,131.87 Cr"}],
            "results": {"revenue": {"value": 1131.87}}}
    before = copy.deepcopy(card)
    assert results_one_line.apply_card_json(card) == [] and card == before


# HFCL, Lumax, Tata Consumer, Ather: two EBITDA figures (ours worked out, the company's printed), neither named
def test_two_ebitda_key_numbers_are_each_named(monkeypatch):
    _on(monkeypatch)
    card = {"headline": "Acme Q2FY27: net profit up", "key_numbers": [
        {"label": "EBITDA", "value": "₹189 Cr", "change": "+42% YoY"}, {"label": "EBITDA", "value": "₹169.47 Cr"},
        {"label": "Net profit", "value": "₹129 Cr"}],
        "results": {"ebitda": {"value": 169.47}, "revenue": {"value": 695.3}}}
    results_one_line.apply_card_json(card)
    assert card["key_numbers"][0]["label"] == "EBITDA (company-reported; results table ₹169.47 Cr)"
    assert card["key_numbers"][1]["label"] == "EBITDA (calculated from the statement)"
    assert card["key_numbers"][2]["label"] == "Net profit"


def test_a_lone_ebitda_on_the_blocks_figure_stays_plain(monkeypatch):
    _on(monkeypatch)
    card = {"key_numbers": [{"label": "EBITDA", "value": "₹169.5 Cr"}], "results": {"ebitda": {"value": 169.47}}}
    assert results_one_line.apply_card_json(card) == [] and card["key_numbers"][0]["label"] == "EBITDA"
