"""Held cards published without the points their quote did not carry (prune.py, pipeline.prune_quote_failures; owner,
2026-10-21: "Needs review · 475"). Measured on the 20 Oct hand review: the hold did not tell good cards from bad (11%
wrong among those pruning releases, 13% among those it keeps)."""

import copy

from bse_intel.models import Pass2Output
from bse_intel.pipeline import prune_quote_failures
from bse_intel.prune import PREFIX, prune_card

CARD = {
    "headline": "Demo Ltd Q2FY27 PAT ₹120 Cr", "event_type": "RESULTS",
    "what_happened": [{"text": "PAT ₹120 Cr", "quote": "Profit 120"}, {"text": "Order book ₹5,000 Cr in the quarter", "quote": "x"}],
    "key_numbers": [{"label": "PAT", "value": "₹120 Cr"}, {"label": "Order book", "value": "₹5,000 Cr"}],
    "notable_changes": [{"metric": "other_income", "current": "₹9 Cr"}],
    "why_it_matters": [{"text": "Margin expanded on lower raw material costs this quarter", "basis": "FILING"}],
    "review": {"status": "UNRESOLVED", "issues": [
        PREFIX + 'key number "Order book" quotes a sentence that is not in the filing',
        PREFIX + 'notable change "other_income" states ₹9 Cr, which its own quote does not',
        PREFIX + 'why it matters "Margin expanded on lower raw material costs this" quotes a sentence that is not in the filing',
        PREFIX + '"Order book ₹5,000 Cr in the quarter" states 5,000, which its own quote does not',
    ]},
}


def test_a_card_held_only_for_its_quotes_is_published_without_those_points():
    card = copy.deepcopy(CARD)
    dropped = prune_card(card)
    assert len(dropped) == 4 and card["review"]["status"] == "PRUNED"
    assert [k["label"] for k in card["key_numbers"]] == ["PAT"]
    assert card["notable_changes"] == [] and card["why_it_matters"] == []
    assert [f["text"] for f in card["what_happened"]] == ["PAT ₹120 Cr"]


def test_any_other_fault_or_the_last_fact_keeps_it_held():
    other = copy.deepcopy(CARD)
    other["review"]["issues"].append("Numbers not found in the filing text or company memory: 7,993")
    assert prune_card(other) is None
    last = copy.deepcopy(CARD)
    last["what_happened"] = last["what_happened"][1:]
    assert prune_card(last) is None
    owner = copy.deepcopy(CARD)
    owner["review"]["held"] = ["Held by the owner (Wrong): check the order book"]
    assert prune_card(owner) is None


def test_a_new_card_is_pruned_the_same_way():
    out = Pass2Output.model_validate({"is_material": True, "card": {
        "impact_level": "MODERATE", "headline": CARD["headline"], "what_happened": CARD["what_happened"],
        "key_numbers": CARD["key_numbers"], "why_it_matters": CARD["why_it_matters"]}})
    problems = [i[len(PREFIX):] for i in CARD["review"]["issues"] if "notable change" not in i]
    assert prune_quote_failures(out, problems) is not None
    assert [k.label for k in out.card.key_numbers] == ["PAT"] and len(out.card.what_happened) == 1
    assert prune_quote_failures(out, ["something else entirely"]) is None


def test_what_keeps_a_card_held_is_counted_by_class():
    from bse_intel.prune import breakdown, fault_classes

    held = copy.deepcopy(CARD)
    held["grounding"] = {"ungrounded": ["7,993"], "math_mismatches": []}
    held["review"]["issues"].append("Numbers not found in the filing text or company memory: 7,993")
    classes = fault_classes(held)
    assert classes[0] == "ungrounded" and "math_mismatches" not in classes
    assert "Numbers not found in the filing text or company memory: N" in classes
    assert 'key number "…" quotes a sentence that is not in the filing' in classes
    other = copy.deepcopy(held)
    other["review"]["issues"][-1] = "Numbers not found in the filing text or company memory: 12.5"
    rows = [({"scrip_code": "1", "symbol": "AAA", "news_id": "n1"}, held), ({"scrip_code": "2", "symbol": "BBB", "news_id": "n2"}, other)]
    top = {b["class"]: b for b in breakdown(rows)}
    assert top["Numbers not found in the filing text or company memory: N"]["cards"] == 2
    assert top["ungrounded"]["examples"] == ["AAA n1", "BBB n2"]
