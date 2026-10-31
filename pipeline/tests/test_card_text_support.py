"""CARD_TEXT_SUPPORT (TODO 142, prompt audit of 30 Oct 2026): names, content words, small counts and day-month dates in the
card text no other check reads must be in the filing, memory or scale block; profit labels need their row. Off by default,
and off the card path and the prompts are what they were."""

from __future__ import annotations

import pytest

from bse_intel import card_support
from bse_intel.models import Card, Pass2Output
from bse_intel.settings import card_text_support

FILING = ("Statement of results for the quarter ended 30 September 2026. Board meeting held on October 29, 2026. The company "
          "received an order from Western Railways for 40 coaches. Consolidated net profit for the period 132.70 Cr.\n"
          "Profit for the period 133.17 Cr\nOwners of the parent 132.70 Cr\nTotal comprehensive income for the period 67.92 Cr\n"
          "Share of profit of associates 3.76 Cr\nTwo observations were raised at the plant.\n")
SOURCES = (FILING, "Demo Ltd results", "", '{"guidance": "FY27 margin 17-18%"}', "")


def _out(**kw):
    card = dict(impact_level="HIGH", headline="Demo Ltd Q2 results",
                what_happened=[{"text": "Order of 40 coaches from Western Railways.", "quote": "order from Western Railways for 40 coaches"}])
    card |= kw
    return Pass2Output(is_material=True, card=Card(**card), timeline_entry="Demo Ltd Q2 results")


def test_the_switch_is_off_by_default_and_not_in_the_switch_file(monkeypatch):
    from bse_intel import settings

    monkeypatch.delenv("CARD_TEXT_SUPPORT", raising=False)
    assert not card_text_support()
    monkeypatch.setenv("CARD_TEXT_SUPPORT", "1")
    assert card_text_support()
    assert "CARD_TEXT_SUPPORT" not in settings.switches_on()


def test_a_risk_naming_two_things_the_sources_never_print_is_dropped_one_is_forgiven():
    out = _out(track_next={"risks": ["Merino wool and Dalmia Bharat input risk", "Delay in coaches for Western Railways",
                                     "Flax prices may rise"]})
    notes = card_support.support_check(out, SOURCES)
    assert out.card.track_next.risks == ["Delay in coaches for Western Railways", "Flax prices may rise"]
    assert len(notes) == 1 and "Dalmia" in notes[0] and "Merino" in notes[0]


def test_a_catalyst_and_core_catalyst_and_change_why_and_approval_are_checked():
    out = _out(core_catalyst="Higher passenger demand and capacity growth",
               track_next={"catalysts": ["MSEDCL solar pump orders under Magel Tyala scheme"],
                           "pending_approvals": ["Railway Board nod for coaches"]},
               notable_changes=[{"metric": "capex", "why": "Fermentation programs ramp", "current": "10 Cr"}])
    card_support.support_check(out, SOURCES)
    assert out.card.core_catalyst is None
    assert out.card.track_next.catalysts == []
    assert out.card.track_next.pending_approvals == ["Railway Board nod for coaches"]
    # names only (the default): one unprinted first word is forgiven, like any single ordinary word
    assert out.card.notable_changes[0].why == "Fermentation programs ramp" and out.card.notable_changes[0].current == "10 Cr"


def test_with_every_word_checked_a_lone_invented_word_counts_too(monkeypatch):
    monkeypatch.setenv("CARD_TEXT_SUPPORT_WORDS", "1")
    out = _out(notable_changes=[{"metric": "capex", "why": "Fermentation programs ramp", "current": "10 Cr"}])
    card_support.support_check(out, SOURCES)
    assert out.card.notable_changes[0].why == ""


def test_names_only_keeps_ordinary_words_the_filing_does_not_use(monkeypatch):
    """31 Oct 2026: the word check dropped items on 36% of 9,249 stored cards, mostly on words like "acceleration"."""
    item = "Order acceleration compared with the earlier quarter for coaches"
    out = _out(track_next={"risks": [item]})
    card_support.support_check(out, SOURCES)
    assert out.card.track_next.risks == [item]
    monkeypatch.setenv("CARD_TEXT_SUPPORT_WORDS", "1")
    out = _out(track_next={"risks": [item]})
    card_support.support_check(out, SOURCES)
    assert out.card.track_next.risks == []


def test_a_sector_insight_is_checked_a_filing_insight_and_a_memory_insight_with_an_id_are_not():
    out = _out(why_it_matters=[
        {"text": "Margin pressure seen at ACC and Dalmia Bharat", "basis": "SECTOR"},
        {"text": "Margin pressure seen at ACC and Dalmia Bharat", "basis": "FILING"},
        {"text": "Margin pressure seen at ACC and Dalmia Bharat", "basis": "MEMORY", "memory_refs": ["cp_1"]},
        {"text": "Margin pressure seen at ACC and Dalmia Bharat", "basis": "MEMORY"},
        {"text": "Order of 40 coaches from Western Railways", "basis": "SECTOR"}])
    card_support.support_check(out, SOURCES)
    assert [(i.basis, bool(i.memory_refs)) for i in out.card.why_it_matters] == [
        ("FILING", False), ("MEMORY", True), ("SECTOR", False)]


@pytest.mark.parametrize("risk, kept", [
    ("USFDA follow-up after 5 observations at the plant", False),     # 5 observations: the filing prints two
    ("Follow-up after two observations at the plant", True),           # spelled out, printed
    ("Delivery of 40 coaches slips", True),
    ("Investor call on 30 Oct", False),                                # a date the filing does not print
    ("Investor call on 29 October", True),                             # the board meeting date it prints
    ("Results due by 12 months", True),                                # a time word is not a counted thing
])
def test_small_counts_and_day_month_dates_must_be_printed(risk, kept):
    out = _out(track_next={"risks": [risk]})
    card_support.support_check(out, SOURCES)
    assert bool(out.card.track_next.risks) is kept


def test_a_milestone_date_field_is_not_a_date_the_filing_must_print():
    out = _out(track_next={"milestones": [{"what": "Coaches delivered", "when": "By FY27", "date": "2027-03-31"},
                                          {"what": "Earnings call", "when": "30 Oct 2026"}]})
    card_support.support_check(out, SOURCES)
    assert [m.what for m in out.card.track_next.milestones] == ["Coaches delivered"]


def test_the_sources_include_memory_and_the_scale_block_but_never_peers():
    out = _out(track_next={"risks": ["Guidance of FY27 margin may slip", "Peer Dalmia Bharat margin pressure"]})
    card_support.support_check(out, (FILING, "", "", "guidance margin FY27 slip", "scale block"))
    assert out.card.track_next.risks == ["Guidance of FY27 margin may slip"]


def test_a_label_on_a_figure_needs_its_row_or_quote():
    out = _out(
        what_happened=[
            {"text": "Net profit to shareholders ₹132.70 Cr.", "quote": "Owners of the parent 132.70 Cr"},
            {"text": "Net profit ₹67.92 Cr for the quarter.", "quote": "total 67.92"},
            {"text": "₹3.76 Cr from discontinued operations.", "quote": "Share of profit of associates 3.76 Cr"},
            {"text": "Order of 40 coaches.", "quote": "order from Western Railways for 40 coaches"}],
        key_numbers=[{"label": "Net profit", "value": "₹133.17 Cr", "quote": "Profit for the period 133.17 Cr"},
                     {"label": "Net profit to shareholders", "value": "₹133.17 Cr", "quote": "133.17"}],
        why_it_matters=[{"text": "Total comprehensive income of ₹67.92 Cr lifts net worth.", "quote": None},
                        {"text": "Total comprehensive income of ₹99.99 Cr.", "quote": "Total comprehensive income 99.99"}])
    card_support.label_check(out, FILING)
    assert [f.text for f in out.card.what_happened] == ["Net profit to shareholders ₹132.70 Cr.", "Order of 40 coaches."]
    assert [k.value for k in out.card.key_numbers] == ["₹133.17 Cr"] and out.card.key_numbers[0].label == "Net profit"
    assert [i.text for i in out.card.why_it_matters] == [
        "Total comprehensive income of ₹67.92 Cr lifts net worth.", "Total comprehensive income of ₹99.99 Cr."]


def test_a_label_far_from_a_figure_is_not_a_claim_on_it():
    out = _out(what_happened=[{"text": "Cash from operations ₹205.97 Cr covers 83% of net profit, capex ₹30.40 Cr.",
                               "quote": "cash 205.97"}])
    assert card_support.label_check(out, FILING) == []


def test_the_prompt_is_unchanged_off_and_carries_the_sources_only_rule_on(settings, monkeypatch):
    from bse_intel.models import Filing
    from bse_intel.prompts.engine import PromptEngine

    f = Filing(news_id="c1", scrip_code="999001", company_name="Demo Ltd", headline="Results",
               filed_at="2026-10-22T17:00:00+05:30", filing_date="2026-10-22")
    engine = PromptEngine(settings)
    for variant in ("long", "short"):
        monkeypatch.delenv("CARD_TEXT_SUPPORT", raising=False)
        off = engine.pass2(f, "RESULTS", "pharma", None, "text", variant=variant)
        assert card_support.STRICT_RULE not in off[0] and "what is normal for" in off[0] + "what is normal for"
        monkeypatch.setenv("CARD_TEXT_SUPPORT", "1")
        on = engine.pass2(f, "RESULTS", "pharma", None, "text", variant=variant)
        assert on[1] == off[1]
        assert card_support.STRICT_RULE in on[0]
        assert "Sector KPIs: look for these in the filing only" in on[0] and "Sector KPIs to look for" not in on[0]
        assert "what is normal for" not in on[0]
        assert "must be\n  printed in the filing" in on[0] or "must be printed in the filing" in on[0]
        monkeypatch.delenv("CARD_TEXT_SUPPORT")
        assert engine.pass2(f, "RESULTS", "pharma", None, "text", variant=variant) == off


@pytest.mark.switches_on("MEMORY_FILE_ONLY")
def test_the_card_path_is_untouched_with_the_switch_off(settings, monkeypatch):
    """The whole pipeline run of test_live_run_end_to_end, with the checks made to fail if anything calls them."""
    import test_pipeline

    def boom(*a, **k):
        raise AssertionError("card_support ran with CARD_TEXT_SUPPORT off")

    monkeypatch.delenv("CARD_TEXT_SUPPORT", raising=False)
    monkeypatch.setattr(card_support, "apply", boom)
    monkeypatch.setattr(card_support, "support_check", boom)
    monkeypatch.setattr(card_support, "label_check", boom)
    monkeypatch.setattr(card_support, "strict_prompt", boom)
    monkeypatch.setattr("bse_intel.prompts.engine.strict_prompt", boom)
    test_pipeline.test_live_run_end_to_end(settings)
