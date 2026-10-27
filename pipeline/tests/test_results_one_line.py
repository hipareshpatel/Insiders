"""CARD_RESULTS_ONE_LINE (F206; live audit of 26 Oct 2026, class "two bases in the results block"): each case is a card of that
audit, rebuilt from its stored figures. Off by default: with the switch off nothing here changes a table or a card."""

from __future__ import annotations

import copy

import pytest

from bse_intel import results_one_line
from bse_intel.dossier import results_snapshot
from bse_intel.settings import card_results_one_line

NID = "nse-1"


def _src(news_id, value, by, basis="CONSOLIDATED"):
    return {"news_id": news_id, "as_of": "2026-10-26T10:00:00", "value": value, "unit": "INR_CR", "basis": basis,
            "lab": {"by": by, "doc": "results", "basis": basis}}


def _m(metric, period, sources, value=None, basis="CONSOLIDATED"):
    """A memory entry the shape live memory has (a figure with every source that stated it)."""
    srcs = [_src(n, v, by, basis) for n, v, by in sources]
    return {"metric": metric, "period": period, "value": srcs[0]["value"] if value is None else value, "unit": "INR_CR",
            "as_of": "2026-10-26T10:00:00", "source_news_id": srcs[0]["news_id"], "sources": srcs}


def _dossier(rows):
    return {"financial_metrics": rows}


@pytest.fixture(autouse=True)
def _off(monkeypatch):
    monkeypatch.delenv("CARD_RESULTS_ONE_LINE", raising=False)


def _on(monkeypatch):
    monkeypatch.setenv("CARD_RESULTS_ONE_LINE", "1")


def _x(period):
    return f"xbrl:res:1:{period}"


# Five Star, Q2FY27 (card nse-106828629, the slides): the card's own reading of total income, 875.0, is stored as `revenue`
# beside the file's revenue 858.48 (nse-106828630) and its total income 875.03; the comparatives are the file's
def _fivestar(total_comparatives=True):
    rows = [_m("revenue", "Q2FY27", [(NID, 875.0, "ai"), ("nse-2", 858.48, "file")], value=858.48, basis="STANDALONE"),
            _m("total_income", "Q2FY27", [("nse-2", 875.03, "file")], basis="STANDALONE"),
            _m("pat", "Q2FY27", [("nse-2", 299.32, "file")], basis="STANDALONE"),
            _m("revenue", "Q2FY26", [(_x("Q2FY26"), 799.44, "file")], basis="STANDALONE"),
            _m("revenue", "Q1FY27", [(_x("Q1FY27"), 828.98, "file")], basis="STANDALONE"),
            _m("pat", "Q2FY26", [(_x("Q2FY26"), 286.0, "file")], basis="STANDALONE"),
            _m("pat", "Q1FY27", [(_x("Q1FY27"), 290.0, "file")], basis="STANDALONE")]
    if total_comparatives:
        rows += [_m("total_income", "Q2FY26", [(_x("Q2FY26"), 806.5, "file")], basis="STANDALONE"),
                 _m("total_income", "Q1FY27", [(_x("Q1FY27"), 838.74, "file")], basis="STANDALONE")]
    return _dossier(rows)


def test_switch_is_off_by_default_and_reads_the_environment(monkeypatch):
    assert card_results_one_line() is False
    _on(monkeypatch)
    assert card_results_one_line() is True


def test_off_the_table_and_the_card_are_unchanged():
    table = results_snapshot(_fivestar(), NID)
    assert table["revenue"]["yoy_pct"] == 9.5 and results_one_line.NOTES_KEY not in table   # the live card's wrong +9.5%
    card = {"headline": "Acme: revenue ₹1,153 Cr", "key_numbers": [{"label": "EBITDA", "value": "₹189 Cr"}],
            "results": {"revenue": {"value": 1131.87}, "ebitda": {"value": 169.47}, "one_line": ["x"],
                        "lines": [{"key": "revenue", "label": "Revenue"}, {"key": "ebitda", "label": "EBITDA"}]}}
    before = copy.deepcopy(card)
    assert results_one_line.apply_card_json(card) == [] and card == before


def test_fivestar_card_time_total_income_takes_total_income_comparatives(monkeypatch):
    _on(monkeypatch)
    table = results_snapshot(_fivestar(), NID)
    row = table["revenue"]
    assert row["value"] == 875.0
    assert row["prev_year"] == 806.5 and row["yoy_pct"] == 8.5 and row["prev_quarter"] == 838.74 and row["qoq_pct"] == 4.3
    assert next(s for s in table["lines"] if s["key"] == "revenue")["label"] == "Total income"
    assert any("total income" in n for n in table["one_line"])
    assert table["pat"]["yoy_pct"] == 4.7   # the other rows are untouched
    card = {"results": table}
    logged = list(table["one_line"])
    assert results_one_line.apply_card_json(card) == logged and "one_line" not in card["results"]


def test_fivestar_without_total_income_comparatives_has_no_change(monkeypatch):
    _on(monkeypatch)
    table = results_snapshot(_fivestar(total_comparatives=False), NID)
    row = table["revenue"]
    assert row["value"] == 875.0
    assert "prev_year" not in row and "yoy_pct" not in row and "prev_quarter" not in row and "qoq_pct" not in row
    assert len(table["one_line"]) == 3


def test_a_revenue_row_on_one_line_is_left_as_it_was(monkeypatch):
    rows = [_m("revenue", "Q2FY27", [("nse-2", 900.0, "file")]), _m("pat", "Q2FY27", [("nse-2", 90.0, "file")]),
            _m("revenue", "Q2FY26", [(_x("Q2FY26"), 800.0, "file")]), _m("revenue", "Q1FY27", [(_x("Q1FY27"), 850.0, "file")]),
            _m("total_income", "Q2FY26", [(_x("Q2FY26"), 810.0, "file")])]
    off = results_snapshot(_dossier(rows), NID)
    _on(monkeypatch)
    assert results_snapshot(_dossier(rows), NID) == off


# Garware Hi-Tech, Q2FY27 (card nse-106824515): this quarter's EBITDA 169.47 is the file's, worked out by code (a calc source),
# the comparatives memory shows are the company's stated 133.0 and 192 beside the file's own 119.44 and 172.0
def _grw(prior_file=True):
    def base(p, stated, file, margin_stated, margin_file, revenue):
        ebitda = [("nse-c", stated, "unknown")] + ([(_x(p), file, "calc")] if prior_file else [])
        margin = [("nse-c", margin_stated, "unknown")] + ([(_x(p), margin_file, "calc")] if prior_file else [])
        return [_m("ebitda", p, ebitda, value=stated), _m("ebitda_margin", p, margin, value=margin_stated),
                _m("revenue", p, [(_x(p), revenue, "file")])]
    return _dossier([
        _m("revenue", "Q2FY27", [(NID, 695.53, "unknown"), (_x("Q2FY27"), 695.53, "file")]), _m("pat", "Q2FY27", [(NID, 129.0, "unknown")]),
        _m("ebitda", "Q2FY27", [(NID, 189.0, "unknown"), (_x("Q2FY27"), 169.47, "calc")], value=169.47),
        _m("ebitda_margin", "Q2FY27", [(_x("Q2FY27"), 24.37, "calc")])]
        + base("Q2FY26", 133.0, 119.44, 23.4, 20.97, 569.69) + base("Q1FY27", 192.0, 172.0, 30.3, 27.17, 633.08))


def test_grwrhitech_off_shows_the_mixed_bases():
    row = results_snapshot(_grw(), NID)["ebitda"]
    assert row["prev_year"] == 133.0 and row["yoy_pct"] == 27.4   # the audit's +27.4% on the company's 133.0


def test_grwrhitech_comparatives_are_the_files_own_or_dropped(monkeypatch):
    _on(monkeypatch)
    table = results_snapshot(_grw(), NID)
    row, margin = table["ebitda"], table["ebitda_margin"]
    assert row["value"] == 169.47 and row["prev_year"] == 119.44 and row["yoy_pct"] == 41.9
    assert row["prev_quarter"] == 172.0 and row["qoq_pct"] == -1.5
    assert margin["prev_year"] == 20.97 and margin["yoy_bps"] == round((24.37 - 20.97) * 100)
    assert margin["prev_quarter"] == 27.17 and margin["qoq_bps"] == round((24.37 - 27.17) * 100)
    assert any("another footing" in n for n in table["one_line"])
    bare = results_snapshot(_grw(prior_file=False), NID)   # no file figure for the comparatives: no change at all
    assert "prev_year" not in bare["ebitda"] and "yoy_pct" not in bare["ebitda"] and "prev_quarter" not in bare["ebitda"]
    assert "prev_year" not in bare["ebitda_margin"] and "qoq_bps" not in bare["ebitda_margin"]


def test_an_ebitda_row_whose_comparatives_are_the_files_own_is_left_alone(monkeypatch):
    rows = _grw()
    for e in rows["financial_metrics"]:
        if e["metric"] in ("ebitda", "ebitda_margin") and e["period"] != "Q2FY27":
            e["value"] = e["sources"][-1]["value"]
    off = results_snapshot(rows, NID)
    _on(monkeypatch)
    assert results_snapshot(rows, NID) == off


LINES = [{"key": "revenue", "label": "Revenue"}, {"key": "ebitda", "label": "EBITDA"}]


# LMW: the headline states the CFO's spoken revenue, the block the statement's
def test_lmw_headline_revenue_on_another_basis_is_labelled(monkeypatch):
    _on(monkeypatch)
    card = {"headline": "LMW Q2FY27: revenue rises 30% to ₹1,153 Cr, orders strong",
            "key_numbers": [{"label": "Revenue", "value": "₹1,153 Cr", "change": "+30% YoY"}],
            "results": {"revenue": {"value": 1131.87}, "lines": LINES}}
    notes = results_one_line.apply_card_json(card)
    assert card["headline"].endswith("(company-reported; results table ₹1,131.87 Cr)")
    assert card["key_numbers"][0]["label"] == "Revenue (company-reported; results table ₹1,131.87 Cr)"
    assert len(notes) == 2 and notes[0].startswith("key_numbers") and notes[1].startswith("headline")
    # run again: a labelled headline and key number are left alone
    assert results_one_line.apply_card_json(card) == []


def test_a_headline_on_the_blocks_figure_is_not_touched(monkeypatch):
    _on(monkeypatch)
    card = {"headline": "LMW Q2FY27: revenue ₹1,131.87 Cr", "key_numbers": [{"label": "Revenue", "value": "₹1,131.87 Cr"}],
            "results": {"revenue": {"value": 1131.87}, "lines": LINES}}
    before = copy.deepcopy(card)
    assert results_one_line.apply_card_json(card) == [] and card == before


# HFCL, Lumax, Tata Consumer, Ather: two EBITDA figures (ours worked out, the company's printed), neither named
def test_two_ebitda_key_numbers_are_each_named(monkeypatch):
    _on(monkeypatch)
    card = {"headline": "Acme Q2FY27: net profit up", "key_numbers": [
        {"label": "EBITDA", "value": "₹189 Cr", "change": "+42% YoY"}, {"label": "EBITDA", "value": "₹169.47 Cr"},
        {"label": "Net profit", "value": "₹129 Cr"}],
        "results": {"ebitda": {"value": 169.47}, "revenue": {"value": 695.3}, "lines": LINES}}
    results_one_line.apply_card_json(card)
    assert card["key_numbers"][0]["label"] == "EBITDA (company-reported; results table ₹169.47 Cr)"
    assert card["key_numbers"][1]["label"] == "EBITDA (calculated from the statement)"
    assert card["key_numbers"][2]["label"] == "Net profit"


def test_a_lone_ebitda_on_the_blocks_figure_stays_plain(monkeypatch):
    _on(monkeypatch)
    card = {"key_numbers": [{"label": "EBITDA", "value": "₹169.5 Cr"}], "results": {"ebitda": {"value": 169.47}, "lines": LINES}}
    assert results_one_line.apply_card_json(card) == [] and card["key_numbers"][0]["label"] == "EBITDA"


def test_a_total_income_figure_is_not_compared_with_a_revenue_row_and_the_reverse(monkeypatch):
    _on(monkeypatch)
    card = {"headline": "Acme: total income ₹875 Cr", "key_numbers": [{"label": "Total income", "value": "₹875 Cr"}],
            "results": {"revenue": {"value": 858.48}, "lines": LINES}}
    before = copy.deepcopy(card)
    assert results_one_line.apply_card_json(card) == [] and card == before
    card["results"]["lines"] = [{"key": "revenue", "label": "Total income"}]   # a total-income row: revenue is not its figure
    card["headline"], card["key_numbers"] = "Acme: revenue ₹858.48 Cr", [{"label": "Revenue", "value": "₹858.48 Cr"}]
    card["results"]["revenue"]["value"] = 875.0
    before = copy.deepcopy(card)
    assert results_one_line.apply_card_json(card) == [] and card == before


def test_a_row_the_table_does_not_show_is_not_cited(monkeypatch):
    _on(monkeypatch)
    card = {"headline": "Bank: revenue ₹900 Cr", "key_numbers": [{"label": "Revenue", "value": "₹900 Cr"}],
            "results": {"revenue": {"value": 1131.87}, "lines": [{"key": "interest_earned", "label": "Interest earned"}]}}
    before = copy.deepcopy(card)
    assert results_one_line.apply_card_json(card) == [] and card == before


def test_the_headline_figure_is_the_amount_not_the_change(monkeypatch):
    _on(monkeypatch)
    card = {"headline": "Acme: revenue up ₹50 Cr to ₹1,131.87 Cr, margin steady", "results": {"revenue": {"value": 1131.87}, "lines": LINES}}
    assert results_one_line.apply_card_json(card) == [] and "company-reported" not in card["headline"]


def test_a_small_gap_is_not_labelled(monkeypatch):
    _on(monkeypatch)
    card = {"headline": "Acme: revenue ₹10 Cr", "key_numbers": [{"label": "Revenue", "value": "₹10 Cr"}],
            "results": {"revenue": {"value": 10.4}, "lines": LINES}}
    assert results_one_line.apply_card_json(card) == []


def test_a_refresh_logs_the_notes_and_leaves_no_stray_key(monkeypatch):
    from test_card_refresh import FILED, _card, _dossier

    from bse_intel import card_refresh
    from bse_intel.models import Filing

    filing = Filing(news_id="n1", scrip_code="500001", company_name="Demo Rail Ltd", headline="h", subject="",
                    filed_at=FILED, filing_date=FILED[:10])
    card = {**_card(), "headline": "Demo Rail: revenue ₹1,153 Cr",
            "results": {"revenue": {"value": 1131.87}, "lines": LINES, "one_line": ["n"]}}
    new, changed = card_refresh.refresh(copy.deepcopy(card), _dossier(), filing, None)
    assert new["results"]["one_line"] == ["n"] and "company-reported" not in new["headline"]   # off: nothing
    _on(monkeypatch)
    new, changed = card_refresh.refresh(copy.deepcopy(card), _dossier(), filing, None)
    assert "one_line" not in new["results"] and new["headline"].endswith("(company-reported; results table ₹1,131.87 Cr)")
    assert new["grounding"]["one_line"][0] == "n" and "headline" in changed and "grounding" in changed


# Five Star at card time: three shapes of memory (live memory with its labels and sources taken away, as the card saw it)
def _untag(rows):
    for e in rows["financial_metrics"]:
        for s in e["sources"]:
            if s["lab"]["by"] == "file" and not s["news_id"].startswith("xbrl:"):
                s["lab"] = {"by": "unknown"}
    return rows


def _five(shape):
    rows = _untag(_fivestar())
    revenue = next(e for e in rows["financial_metrics"] if e["metric"] == "revenue" and e["period"] == "Q2FY27")
    revenue["value"] = 875.0
    if shape == "B":   # no total income anywhere
        rows["financial_metrics"] = [e for e in rows["financial_metrics"] if e["metric"] != "total_income"]
    if shape == "C":   # revenue has only the card's own AI reading
        revenue["sources"] = [s for s in revenue["sources"] if s["news_id"] == NID]
    return rows


@pytest.mark.parametrize("shape", ["A", "C"])
def test_fivestar_card_time_untagged_total_income_is_total_income(monkeypatch, shape):
    off = results_snapshot(_five(shape), NID)["revenue"]
    assert off["yoy_pct"] == 9.5   # the wrong figure of the audit
    _on(monkeypatch)
    row = results_snapshot(_five(shape), NID)["revenue"]
    assert row["prev_year"] == 806.5 and row["yoy_pct"] == 8.5 and row["prev_quarter"] == 838.74 and row["qoq_pct"] == 4.3


def test_fivestar_card_time_without_total_income_holds_the_changes_back(monkeypatch):
    _on(monkeypatch)
    table = results_snapshot(_five("B"), NID)
    assert table["revenue"] == {"value": 875.0} and len(table["one_line"]) == 2


def test_a_figure_the_file_states_as_revenue_is_left_alone(monkeypatch):
    rows = _fivestar()   # the file's 858.48 is revenue from operations
    next(e for e in rows["financial_metrics"] if e["metric"] == "revenue" and e["period"] == "Q2FY27")["value"] = 858.48
    off = dict(results_snapshot(rows, "nse-2")["revenue"])
    _on(monkeypatch)
    assert results_snapshot(rows, "nse-2")["revenue"] == off


def test_each_headline_figure_is_bound_to_its_own_metric_word(monkeypatch):
    _on(monkeypatch)
    block = {"revenue": {"value": 696.0}, "ebitda": {"value": 189.0}, "lines": LINES}

    def headline(text):
        card = {"headline": text, "results": copy.deepcopy(block)}
        results_one_line.apply_card_json(card)
        return card["headline"]

    assert headline("Garware: EBITDA margin 27.2% on revenue of ₹696 Cr") == "Garware: EBITDA margin 27.2% on revenue of ₹696 Cr"
    assert headline("Acme: revenue up ₹50 Cr to ₹696 Cr, EBITDA ₹189 Cr") == "Acme: revenue up ₹50 Cr to ₹696 Cr, EBITDA ₹189 Cr"
    assert headline("Acme: EBITDA ₹169 Cr, revenue ₹696 Cr").endswith("(company-reported; results table ₹189 Cr)")
    # a figure of another metric is not the revenue's, however near the word "Revenue" is
    for text in ("Acme: Revenue up 22% and PAT ₹129 Cr", "Acme: Revenue rises 22% as PAT jumps to ₹129 Cr",
                 "Acme: Revenue up 22%, net profit ₹129 Cr", "Acme: Revenue 22% higher with EBITDA margin ₹27 Cr"):
        assert headline(text) == text


def test_a_basis_word_counts_only_near_the_figure_and_a_company_name_is_no_basis(monkeypatch):
    _on(monkeypatch)
    block = {"revenue": {"value": 1131.87}, "lines": LINES}

    def headline(text):
        card = {"headline": text, "results": copy.deepcopy(block)}
        results_one_line.apply_card_json(card)
        return card["headline"]

    # "Company" in a name does not say what the figure is; "statement" far from it does not either
    assert headline("Tata Consumer Company: revenue ₹1,153 Cr").endswith("(company-reported; results table ₹1,131.87 Cr)")
    far = "Acme Q2FY27 results: net profit per the filing up 12%, margin steady, orders strong, revenue ₹1,153 Cr"
    assert headline(far).endswith("(company-reported; results table ₹1,131.87 Cr)")
    # but a basis word beside the figure leaves it alone
    near = "Acme: revenue ₹1,153 Cr as reported"
    assert headline(near) == near
