"""CARD_CONSOLIDATED_ONLY (F154; TODO 44) and the basis of a printed figure (printed_figures): consolidated first, the
standalone figures kept from the AI. Off by default, and off the prompts and cards are what they were."""

from __future__ import annotations

import pytest

from bse_intel import printed_figures as pf
from bse_intel.dossier import view_as_of
from bse_intel.models import Filing, FinancialMetric, Pass2Output
from bse_intel.pipeline import standalone_figures_removed
from bse_intel.xbrl import XbrlResult

TWO_BASIS = """Acme Industries Limited
Q2 FY27 results press release
Acme reported consolidated PAT of ₹48.43 crore for the quarter.

Standalone Financial Results
(₹ in crore)
Particulars Q2 FY27 Q1 FY27 Q2 FY26 YoY
EBITDA 240.50 200.00 190.00 26.6%
Profit after tax 40.10 20.0 25.0

Consolidated Financial Results
(₹ in crore)
Particulars Q2 FY27 Q1 FY27 Q2 FY26 YoY
EBITDA 286.61 250.00 212.90 34.6%
Profit after tax 46.15 25.2 30.03
"""

CONSOLIDATED_ONLY = """Acme Industries Limited
Consolidated Financial Results
(₹ in crore)
Particulars Q2 FY27 Q1 FY27 Q2 FY26 YoY
EBITDA 286.61 250.00 212.90 34.6%
"""

UNLABELLED = """Acme Industries Limited
(₹ in crore)
Particulars Q2 FY27 Q1 FY27 Q2 FY26 YoY
EBITDA 286.61 250.00 212.90 34.6%
EBITDA 240.50 200.00 190.00 26.6%
"""


# --- the basis of a printed EBITDA ---------------------------------------------------------------------------------

def test_a_two_basis_release_gives_the_card_its_own_basis_not_the_first_row():
    group = pf.printed_ebitda(TWO_BASIS, "Q2FY27", ours=290.0, basis="CONSOLIDATED")
    alone = pf.printed_ebitda(TWO_BASIS, "Q2FY27", ours=250.0, basis="STANDALONE")
    assert (group.value_cr, group.basis) == (286.61, "CONSOLIDATED")
    assert (alone.value_cr, alone.basis) == (240.5, "STANDALONE")
    # no basis given: the first sensible row, as before F154
    assert pf.printed_ebitda(TWO_BASIS, "Q2FY27", ours=290.0).value_cr == 240.5


def test_a_consolidated_only_release_is_taken_for_a_consolidated_card_and_not_for_a_standalone_one():
    assert pf.printed_ebitda(CONSOLIDATED_ONLY, "Q2FY27", 290.0, "CONSOLIDATED").value_cr == 286.61
    assert pf.printed_ebitda(CONSOLIDATED_ONLY, "Q2FY27", 290.0, "STANDALONE") is None


def test_two_unlabelled_values_give_no_printed_ebitda_and_one_value_stands():
    assert pf.printed_ebitda(UNLABELLED, "Q2FY27", 290.0, "CONSOLIDATED") is None
    one = UNLABELLED.rsplit("EBITDA", 1)[0]
    got = pf.printed_ebitda(one, "Q2FY27", 290.0, "CONSOLIDATED")
    assert got is not None and got.value_cr == 286.61 and got.basis is None


def test_a_sentence_names_its_own_basis():
    prose = ("Acme's standalone EBITDA of ₹240.50 crore rose from ₹190 crore in the year-ago quarter. "
             "Consolidated EBITDA was ₹286.61 crore against ₹212.90 crore in the year-ago quarter.")
    assert pf.printed_ebitda(prose, None, 290.0, "CONSOLIDATED").value_cr == 286.61
    assert pf.printed_ebitda(prose, None, 250.0, "STANDALONE").value_cr == 240.5


# --- the headline profit's basis -----------------------------------------------------------------------------------

def test_the_headline_profit_is_the_cards_basis():
    text = ("On a standalone basis, PAT of ₹40.10 crore for the quarter. "
            "On a consolidated basis, Profit after tax of ₹46.15 crore for the quarter.")
    cands = {"pat": 46.15, "pat_owners": 48.43}
    assert pf.choose_profit(cands, text, "CONSOLIDATED")[0] == "pat"
    assert pf.choose_profit(cands, text) == ("pat_owners", None) or pf.choose_profit(cands, text)[0] == "pat_owners"
    # two profits and no basis told: none is the headline; the shareholders' profit stands
    unlabelled = "PAT of ₹40.10 crore for the quarter. Profit after tax of ₹46.15 crore for the half year."
    assert pf.choose_profit(cands, unlabelled, "CONSOLIDATED") == ("pat_owners", None)


# --- what the model sees ---------------------------------------------------------------------------------------------

def _result(basis="CONSOLIDATED") -> XbrlResult:
    return XbrlResult(kind="RESULTS", basis=basis, period="Q2FY27", metrics=[
        FinancialMetric(metric="revenue", period="Q2FY27", value=388.15)])


def test_the_table_header_names_basis_and_period_only_with_the_switch():
    assert _result().table().splitlines()[0] == (
        "Machine-tagged results (XBRL, CONSOLIDATED, ₹ crore unless noted; exact, prefer these over figures read from the PDF):")
    assert _result().table(explicit_basis=True).splitlines()[0].startswith(
        "Machine-tagged results (XBRL, Consolidated, ₹ crore unless noted, quarter ended 30 Sep 2026;")
    assert _result().table(explicit_basis=True).splitlines()[1:] == _result().table().splitlines()[1:]


def test_the_pass2_prompt_is_byte_identical_off_and_says_consolidated_only_on(settings):
    from bse_intel.prompts.engine import PromptEngine

    f = Filing(news_id="c1", scrip_code="999001", company_name="Demo Ltd", headline="Results",
               filed_at="2026-10-22T17:00:00+05:30", filing_date="2026-10-22")
    engine = PromptEngine(settings)
    off = engine.pass2(f, "RESULTS", None, None, "text")
    assert off == engine.pass2(f, "RESULTS", None, None, "text", consolidated_only=False)
    on = engine.pass2(f, "RESULTS", None, None, "text", consolidated_only=True)
    assert on[1] == off[1] and on[0].startswith(off[0])
    assert on[0][len(off[0]):] == (
        "\n\nConsolidated first: state the consolidated (group) figures only. Every figure block above names its basis. Do not quote\n"
        "standalone figures from the filing text, even where the filing prints them beside the consolidated ones, unless the\n"
        "company files standalone results only.")


def test_memory_shows_a_consolidated_filer_no_standalone_only_figure():
    dossier = {"company_name": "Acme", "financial_metrics": [
        {"metric": "revenue", "period": "Q1FY27", "value": 250.0, "unit": "cr", "sources": [
            {"value": 250.0, "as_of": "2026-07-20T00:00:00+05:30", "basis": "CONSOLIDATED", "news_id": "a"}]},
        {"metric": "ebitda", "period": "Q1FY27", "value": 40.0, "unit": "cr", "sources": [
            {"value": 40.0, "as_of": "2026-07-20T00:00:00+05:30", "basis": "STANDALONE", "news_id": "a"}]}]}
    cutoff = "2026-10-22T00:00:00+05:30"
    assert "ebitda" in view_as_of(dossier, cutoff)["metrics"]
    shown = view_as_of(dossier, cutoff, consolidated_only=True)
    assert "ebitda" not in shown["metrics"] and "revenue" in shown["metrics"]


# --- the check after pass 2 --------------------------------------------------------------------------------------------

def _files():
    group = XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period="Q2FY27", metrics=[
        FinancialMetric(metric="revenue", period="Q2FY27", value=388.15),
        FinancialMetric(metric="pat", period="Q2FY27", value=46.15),
        FinancialMetric(metric="pat_owners", period="Q2FY27", value=44.0),
        FinancialMetric(metric="ebitda", period="Q2FY27", value=290.0)])
    alone = XbrlResult(kind="RESULTS", basis="STANDALONE", period="Q2FY27", metrics=[
        FinancialMetric(metric="revenue", period="Q2FY27", value=330.0),
        FinancialMetric(metric="pat", period="Q2FY27", value=40.10),
        FinancialMetric(metric="pat_owners", period="Q2FY27", value=40.10),
        FinancialMetric(metric="ebitda", period="Q2FY27", value=240.5)])
    return group, alone


def _card(**kw) -> Pass2Output:
    card = {"impact_level": "MODERATE", "headline": "Acme Q2 results", "takeaway": "Profit grew.",
            "what_happened": ["Revenue ₹388.15 Cr"], "why_it_matters": [{"text": "One"}],
            "key_numbers": [{"label": "Revenue", "value": "₹388.15 Cr", "change": "+72% YoY"}]}
    card.update(kw)
    return Pass2Output.model_validate({"is_material": True, "event_type": "RESULTS", "timeline_entry": "Q2 results", "card": card})


def test_a_standalone_figure_on_a_consolidated_card_is_removed_and_the_card_kept():
    group, alone = _files()
    out = _card(what_happened=["Revenue ₹388.15 Cr", "EBITDA of ₹240.50 Cr in the quarter"],
                why_it_matters=[{"text": "Net profit to shareholders was ₹40.10 Cr."}, {"text": "Margins held."}],
                key_numbers=[{"label": "Revenue", "value": "₹388.15 Cr", "change": "+72% YoY"},
                             {"label": "Revenue", "value": "₹330.00 Cr", "change": None}],
                takeaway="Profit grew. Standalone revenue was ₹330.00 Cr.")
    notes = standalone_figures_removed(out, group, alone)
    assert len(notes) == 4 and all("standalone figure on a consolidated card" in n for n in notes)
    assert [f.text for f in out.card.what_happened] == ["Revenue ₹388.15 Cr"]
    assert [i.text for i in out.card.why_it_matters] == ["Margins held."]      # the profit in other wording: same group
    assert [k.value for k in out.card.key_numbers] == ["₹388.15 Cr"]
    assert out.card.takeaway == "Profit grew."


def test_consolidated_figures_and_standalone_cards_are_left_alone():
    group, alone = _files()
    out = _card(what_happened=["EBITDA of ₹290.00 Cr", "PAT of ₹46.15 Cr"])
    assert standalone_figures_removed(out, group, alone) == []
    assert len(out.card.what_happened) == 2
    assert standalone_figures_removed(_card(what_happened=["EBITDA ₹240.50 Cr"]), alone, group) == []   # a standalone card
    assert standalone_figures_removed(_card(what_happened=["EBITDA ₹240.50 Cr"]), group, None) == []


def test_the_switch_is_off_by_default(monkeypatch):
    from bse_intel.settings import card_consolidated_only

    monkeypatch.delenv("CARD_CONSOLIDATED_ONLY", raising=False)
    assert card_consolidated_only() is False
    monkeypatch.setenv("CARD_CONSOLIDATED_ONLY", "1")
    assert card_consolidated_only() is True
