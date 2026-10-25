"""CARD_EBITDA_PROFIT_V2 (F151; TODO 11, 14, 15): the company's printed EBITDA first and ours beneath it, labelled
calculated; one profit line on a card. Everything off by default, and off the output is what it was."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bse_intel import printed_figures, results_card, xbrl
from bse_intel.dossier import results_snapshot
from bse_intel.models import FinancialMetric, Pass2Output
from bse_intel.xbrl import XbrlResult

FIX = Path(__file__).parent / "fixtures"

RELEASE = """Acme Industries Limited
Q2 FY27 results
Acme reported PAT of ₹48.43 crore for the quarter, up 55.7%.
(₹ in crore)
Particulars Q2 FY27 Q1 FY27 Q2 FY26 YoY
Revenue from operations 388.15 251.2 225.3 72.3%
EBITDA 286.61 250.00 212.90 34.6%
EBITDA margin 28.6% 26.1% 24.0%
Profit after tax 46.15 25.2 30.03
"""


def _card():
    return Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "Q2 results",
        "card": {"impact_level": "MODERATE", "headline": "Acme Q2 results", "takeaway": "Margins held.",
                 "what_happened": ["Revenue rose"], "why_it_matters": [{"text": "One"}],
                 "key_numbers": [{"label": "Revenue", "value": "₹388 Cr", "change": "+72% YoY"}]}})


def _tagged(owners: float | None = 48.43, ebitda: float = 290.0, bank: bool = False) -> XbrlResult:
    p = "Q2FY27"
    rows = [FinancialMetric(metric="revenue", period=p, value=388.15, yoy_pct=72.3),
            FinancialMetric(metric="pat", period=p, value=46.15, yoy_pct=53.7),
            FinancialMetric(metric="other_income", period=p, value=12.4)]
    if not bank:
        rows += [FinancialMetric(metric="ebitda", period=p, value=ebitda, yoy_pct=36.2),
                 FinancialMetric(metric="ebitda_margin", period=p, value=ebitda / 388.15 * 100, unit="PCT")]
    else:
        rows += [FinancialMetric(metric="interest_earned", period=p, value=3213.37)]
    if owners is not None:
        rows.append(FinancialMetric(metric="pat_owners", period=p, value=owners, yoy_pct=55.7))
    return XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period=p, metrics=rows)


# --- the company's printed EBITDA, read from the text ---------------------------------------------------------------

def test_a_printed_row_gives_its_name_value_and_the_year_ago_only_when_its_own_change_proves_it():
    got = printed_figures.printed_ebitda(RELEASE, "Q2FY27", ours=290.0)
    assert (got.name, got.value_cr, got.prev_year_cr, got.yoy_pct()) == ("EBITDA", 286.61, 212.9, 34.6)
    assert got.quote == "EBITDA 286.61 250.00 212.90 34.6%"
    # without a change printed beside the row, no column can be told as the year-ago one
    bare = RELEASE.replace(" 34.6%", "").replace(" YoY", "").replace(" 72.3%", "")
    got = printed_figures.printed_ebitda(bare, "Q2FY27", ours=290.0)
    assert got.value_cr == 286.61 and got.prev_year_cr is None and got.yoy_pct() is None


def test_a_printed_sentence_gives_the_year_ago_only_when_it_says_year_ago():
    text = "Adjusted EBITDA of ₹286.61 crore, up 34.6% YoY from ₹212.90 crore in Q2 FY26, on revenue of ₹388 crore."
    got = printed_figures.printed_ebitda(text, "Q2FY27", ours=290.0)
    assert (got.name, got.value_cr, got.prev_year_cr, got.yoy_pct()) == ("Adjusted EBITDA", 286.61, 212.9, 34.6)
    sequential = "EBITDA of ₹286.61 crore, up from ₹250.00 crore in the previous quarter."
    got = printed_figures.printed_ebitda(sequential, "Q2FY27", ours=290.0)
    assert got.value_cr == 286.61 and got.prev_year_cr is None


def test_nothing_printed_nothing_shown():
    assert printed_figures.printed_ebitda("Revenue 388.15 | PAT 46.15\nEBITDA margin 28.6%", "Q2FY27", 290.0) is None
    assert printed_figures.printed_ebitda("", "Q2FY27", 290.0) is None
    # the table the code itself puts in front of a filing is not the company's figure
    assert printed_figures.printed_ebitda("- ebitda Q2FY27: 286.61 Cr, YoY +36.2%", "Q2FY27", 290.0) is None


def test_a_figure_that_cannot_be_read_with_certainty_is_not_shown():
    million = RELEASE.replace("(₹ in crore)", "(₹ in million)")
    assert printed_figures.printed_ebitda(million, "Q2FY27", ours=290.0) is None          # converting is not printing
    assert printed_figures.printed_ebitda(RELEASE, "Q2FY27", ours=29.0) is None            # 10x from ours: a unit slip
    other_quarter = RELEASE.replace("Particulars Q2 FY27 Q1 FY27 Q2 FY26", "Particulars Q1 FY27 Q4 FY26 Q1 FY26")
    assert printed_figures.printed_ebitda(other_quarter, "Q2FY27", ours=290.0) is None     # first column is not the quarter


def test_the_headline_profit_is_the_one_the_opening_names():
    cands = {"pat": 46.15, "pat_owners": 48.43}
    assert printed_figures.choose_profit(cands, RELEASE) == ("pat_owners", "PAT")
    other = RELEASE.replace("₹48.43 crore", "₹46.15 crore")
    assert printed_figures.choose_profit(cands, other) == ("pat", "PAT")
    # a headline that is neither file line (an adjusted profit) is not ours to show: the shareholders' profit
    adjusted = RELEASE.replace("PAT of ₹48.43 crore", "Adjusted PAT of ₹51.00 crore")
    assert printed_figures.choose_profit(cands, adjusted) == ("pat_owners", None)
    assert printed_figures.choose_profit(cands, None) == ("pat_owners", None)
    assert printed_figures.choose_profit({"pat": 46.15}, None) == ("pat", None)


# --- the card ----------------------------------------------------------------------------------------------------

def test_off_the_card_is_what_it_was_even_with_a_release_that_prints_ebitda(monkeypatch):
    monkeypatch.delenv("CARD_EBITDA_PROFIT_V2", raising=False)
    a, b = _card(), _card()
    results_card.build(a, _tagged(), "Acme Industries Limited", text=RELEASE)
    results_card.build(b, _tagged(), "Acme Industries Limited", text=RELEASE, v2=False)
    assert a.card.model_dump_json() == b.card.model_dump_json()
    assert [k.label for k in a.card.key_numbers][:3] == ["Revenue from operations", "EBITDA", "Net profit"]
    texts = " ".join(f.text for f in a.card.what_happened)
    assert "calculated" not in texts and "Filing" not in texts
    assert "Net profit to shareholders" in texts and "Net profit Q2FY27" in texts   # both lines, as today


def test_printed_ebitda_leads_and_ours_follows_labelled_calculated(monkeypatch):
    monkeypatch.setenv("CARD_EBITDA_PROFIT_V2", "1")
    out = _card()
    results_card.build(out, _tagged(), "Acme Industries Limited", text=RELEASE)
    facts = out.card.what_happened
    texts = [f.text for f in facts]
    filing = next(t for t in texts if "(Filing)" in t)
    ours = next(t for t in texts if "Operating EBITDA (calculated)" in t)
    assert texts.index(filing) < texts.index(ours)
    assert filing == "EBITDA Q2FY27 (Filing): ₹286.61 Cr (+34.6% YoY, against ₹212.9 Cr a year earlier)."
    assert "leaves out other income ₹12.4 Cr" in ours and "+36.2% YoY" in ours          # ours against ours
    quote = next(f.quote for f in facts if "(Filing)" in f.text)
    assert quote in RELEASE
    labels = [k.label for k in out.card.key_numbers]
    assert labels.index("EBITDA (Filing)") < labels.index("Operating EBITDA (calculated)")
    assert "Operating EBITDA margin (calculated)" in labels and "EBITDA margin" not in labels
    filing_key = next(k for k in out.card.key_numbers if k.label == "EBITDA (Filing)")
    assert filing_key.value == "₹286.61 Cr" and filing_key.change == "+34.6% YoY"


def test_no_printed_ebitda_ours_alone_and_labelled(monkeypatch):
    monkeypatch.setenv("CARD_EBITDA_PROFIT_V2", "1")
    out = _card()
    results_card.build(out, _tagged(), "Acme Industries Limited", text="Acme results. Revenue ₹388 crore.")
    texts = " ".join(f.text for f in out.card.what_happened)
    assert "(Filing)" not in texts and "Operating EBITDA (calculated) Q2FY27: ₹290 Cr" in texts
    assert [k.label for k in out.card.key_numbers if "EBITDA" in k.label] == [
        "Operating EBITDA (calculated)", "Operating EBITDA margin (calculated)"]


def test_a_bank_has_no_ebitda_of_either_kind(monkeypatch):
    monkeypatch.setenv("CARD_EBITDA_PROFIT_V2", "1")
    out = _card()
    results_card.build(out, _tagged(bank=True), "Some Bank Limited", text=RELEASE)
    texts = " ".join(f.text for f in out.card.what_happened) + " ".join(k.label for k in out.card.key_numbers)
    assert "EBITDA" not in texts


def test_one_profit_line_the_one_the_release_headlines(monkeypatch):
    monkeypatch.setenv("CARD_EBITDA_PROFIT_V2", "1")
    out = _card()
    results_card.build(out, _tagged(), "Acme Industries Limited", text=RELEASE)   # release headlines ₹48.43 Cr as PAT
    card = out.card
    texts = " ".join([card.headline, card.takeaway or "", out.timeline_entry or "", *(f.text for f in card.what_happened)])
    assert card.headline == "Acme Industries Q2FY27: revenue ₹388.15 Cr (+72.3% YoY), PAT ₹48.43 Cr"   # no YoY: the release prints no year-ago
    assert "46.15" not in texts and "net profit" not in texts.lower()
    profit_keys = [k for k in card.key_numbers if "profit" in k.label.lower() or k.label == "PAT"]
    assert [(k.label, k.value) for k in profit_keys] == [("PAT", "₹48.43 Cr")]


def test_one_profit_line_without_a_release_is_the_shareholders_profit(monkeypatch):
    monkeypatch.setenv("CARD_EBITDA_PROFIT_V2", "1")
    out = _card()
    results_card.build(out, _tagged(), "Acme Industries Limited", text="")
    card = out.card
    assert card.headline == ("Acme Industries Q2FY27: revenue ₹388.15 Cr (+72.3% YoY), net profit to shareholders ₹48.43 Cr "
                             "(+55.7% YoY)")
    assert [k.label for k in card.key_numbers if "profit" in k.label.lower()] == ["Net profit to shareholders"]
    assert "46.15" not in " ".join(f.text for f in card.what_happened)
    # a company with no separate owners' line has the one it has
    out = _card()
    results_card.build(out, _tagged(owners=None), "Acme Industries Limited", text="")
    assert [k.label for k in out.card.key_numbers if "profit" in k.label.lower()] == ["Net profit"]


def test_a_computed_line_on_the_other_profit_figure_is_left_out(monkeypatch):
    from bse_intel.facts import Fact

    monkeypatch.setenv("CARD_EBITDA_PROFIT_V2", "1")
    facts = [Fact(text="Cash flow H1FY27: cash from operations ₹131.42 Cr, 178% of net profit ₹46.15 Cr"),
             Fact(text="Dividend payout 12% of profit ₹48.43 Cr"), Fact(text="Cost of materials Q2FY27: 40.1% of revenue")]
    out = _card()
    results_card.build(out, _tagged(), "Acme Industries Limited", text="", facts=facts)
    texts = " ".join(f.text for f in out.card.what_happened)
    assert "178%" not in texts and "Dividend payout" in texts and "Cost of materials" in texts


# --- the results table ------------------------------------------------------------------------------------------------

def _dossier():
    def m(metric, period, value, news="n2", **kw):
        return {"metric": metric, "period": period, "value": value, "source_news_id": news, "as_of": "b", **kw}
    return {"financial_metrics": [
        m("revenue", "Q2FY27", 388.15), m("revenue", "Q2FY26", 225.3, "n1"), m("revenue", "Q1FY27", 251.2, "n1"),
        m("ebitda", "Q2FY27", 290.0), m("ebitda", "Q2FY26", 213.45, "n1"), m("ebitda", "Q1FY27", 250.0, "n1"),
        m("other_income", "Q2FY27", 12.4),
        m("pat", "Q2FY27", 46.15), m("pat", "Q2FY26", 30.03, "n1"), m("pat", "Q1FY27", 25.2, "n1"),
        m("pat_owners", "Q2FY27", 48.43), m("pat_owners", "Q2FY26", 31.1, "n1"), m("pat_owners", "Q1FY27", 26.0, "n1"),
    ]}


def test_the_table_off_is_unchanged_and_on_has_both_ebitda_rows(monkeypatch):
    monkeypatch.delenv("CARD_EBITDA_PROFIT_V2", raising=False)
    off = results_snapshot(_dossier(), "n2", printed=RELEASE)
    assert [x["key"] for x in off["lines"]] == ["revenue", "ebitda", "ebitda_margin", "pat"]
    assert "ebitda_filing" not in off and off["pat"]["value"] == 46.15
    assert all("note" not in x for x in off["lines"])

    monkeypatch.setenv("CARD_EBITDA_PROFIT_V2", "1")
    on = results_snapshot(_dossier(), "n2", printed=RELEASE)
    specs = {x["key"]: x for x in on["lines"]}
    assert [x["key"] for x in on["lines"]] == ["revenue", "ebitda_filing", "ebitda", "ebitda_margin", "pat"]
    assert specs["ebitda_filing"]["label"] == "EBITDA (Filing)"
    assert on["ebitda_filing"] == {"value": 286.61, "prev_year": 212.9, "yoy_pct": 34.6}   # theirs against their own year-ago
    assert specs["ebitda"]["label"] == "Operating EBITDA (calculated)"
    assert specs["ebitda"]["note"] == "leaves out other income ₹12.4 Cr"
    assert on["ebitda"]["prev_year"] == 213.45 and on["ebitda"]["yoy_pct"] == 35.9          # ours against ours
    # one profit line, the release's headline (the shareholders' ₹48.43 Cr, called PAT by the company)
    assert specs["pat"]["label"] == "PAT" and on["pat"]["value"] == 48.43 and on["pat"]["prev_year"] == 31.1


def test_the_table_with_no_release_has_ours_alone_and_the_shareholders_profit(monkeypatch):
    monkeypatch.setenv("CARD_EBITDA_PROFIT_V2", "1")
    on = results_snapshot(_dossier(), "n2")
    assert [x["key"] for x in on["lines"]] == ["revenue", "ebitda", "ebitda_margin", "pat"]
    assert {x["key"]: x["label"] for x in on["lines"]}["pat"] == "Net profit to shareholders"
    assert on["pat"]["value"] == 48.43


def test_a_refresh_without_the_text_keeps_the_printed_row_the_stored_table_had(monkeypatch):
    monkeypatch.setenv("CARD_EBITDA_PROFIT_V2", "1")
    stored = results_snapshot(_dossier(), "n2", printed=RELEASE)
    again = results_snapshot(_dossier(), "n2", like=stored)
    assert again["ebitda_filing"] == stored["ebitda_filing"]
    assert [x["key"] for x in again["lines"]] == ["revenue", "ebitda_filing", "ebitda", "ebitda_margin", "pat"]
    assert json.dumps(again, sort_keys=True) == json.dumps(stored, sort_keys=True)


def test_a_banks_table_has_no_ebitda_rows(monkeypatch):
    monkeypatch.setenv("CARD_EBITDA_PROFIT_V2", "1")

    def m(metric, period, value, news="n2"):
        return {"metric": metric, "period": period, "value": value, "source_news_id": news, "as_of": "b"}
    dossier = {"financial_metrics": [m("interest_earned", "Q1FY27", 3213.37), m("interest_expended", "Q1FY27", 2100.0),
                                     m("pat", "Q1FY27", 151.63), m("pbt", "Q1FY27", 200.0), m("eps", "Q1FY27", 9.1)]}
    snap = results_snapshot(dossier, "n2", printed=RELEASE)
    assert snap is None or all("ebitda" not in x["key"] for x in snap["lines"])


def test_the_key_number_guard_keeps_the_headlined_profit_under_the_companys_own_label(monkeypatch):
    """xbrl_key_numbers sets a "PAT" key number from the file's `pat` line: with the company's own name on the
    shareholders' profit it must keep that line's figure, or the card shows the second profit figure again."""
    from bse_intel import pipeline as P

    monkeypatch.setenv("CARD_EBITDA_PROFIT_V2", "1")
    out, tagged = _card(), _tagged()
    results_card.build(out, tagged, "Acme Industries Limited", text=RELEASE)
    P.xbrl_key_numbers(out, tagged, (RELEASE,))
    assert {k.label: k.value for k in out.card.key_numbers}["PAT"] == "₹48.43 Cr"
    assert next(k for k in out.card.key_numbers if k.label == "EBITDA (Filing)").value == "₹286.61 Cr"   # not ours
