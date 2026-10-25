"""CARD_TWO_PARTS (F152; TODO 21): every line of a card sorted into part 1 ("From the filing, checked") or part 2
("Our reading, AI") by code, and a part 2 line that fails the existing checks hidden alone instead of the card held.
Off by default, and off the card is what it was."""

from __future__ import annotations

import copy
import json
from datetime import timedelta

from test_pipeline import PASS2, RESULT_TEXT, _filing, _pdf, build

from bse_intel import two_parts
from bse_intel.timeutil import now_ist

BAD_QUANT = {
    "label": "Annualised interest on new debt", "formula": "new_debt * rate",
    "inputs": [{"name": "new_debt", "value": 1500, "source": "FILING"}, {"name": "rate", "value": 0.09}],
    "result": 300, "unit": "INR_CR",
}


def _run(settings, reply, monkeypatch, switch):
    if switch is None:
        monkeypatch.delenv("CARD_TWO_PARTS", raising=False)
    else:
        monkeypatch.setenv("CARD_TWO_PARTS", switch)
    f = _filing("n-q", "Unaudited Financial Results for the quarter", now_ist() - timedelta(minutes=10), "Result")
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(reply)] * 4},
                                 env={"OPENROUTER_API_KEY": "o"})
    return pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))


def test_off_the_card_json_is_what_it_was(settings, monkeypatch):
    unset = _run(settings, PASS2, monkeypatch, None).card["card"]
    off = _run(settings, PASS2, monkeypatch, "0").card["card"]
    on = _run(settings, PASS2, monkeypatch, "1").card["card"]
    assert "parts" not in unset and "parts" not in off
    assert json.dumps(unset, sort_keys=True) == json.dumps(off, sort_keys=True)
    # on adds only the `parts` block when nothing fails a part 2 check
    assert on["parts"]["v"] == 1 and on["parts"]["hidden"] == []
    assert json.dumps({k: v for k, v in on.items() if k != "parts"}, sort_keys=True) == json.dumps(unset, sort_keys=True)


def test_a_part_2_estimate_that_fails_is_hidden_and_the_card_is_not_held(settings, monkeypatch):
    bad = copy.deepcopy(PASS2)
    bad["card"]["quantified_impact"] = [BAD_QUANT]
    held = _run(settings, bad, monkeypatch, "0")
    assert held.card["needs_review"] == 1 and held.card["card"]["review"]["status"] == "UNRESOLVED"
    on = _run(settings, bad, monkeypatch, "1")
    body = on.card["card"]
    assert on.card["held"] == 0 and (body.get("review") or {}).get("status") != "UNRESOLVED"
    assert body["quantified_impact"] == []
    (gone,) = body["parts"]["hidden"]
    assert gone["field"] == "quantified_impact" and "arithmetic" in gone["why"]


def test_a_part_2_point_with_a_figure_the_filing_never_states_is_hidden(settings, monkeypatch):
    bad = copy.deepcopy(PASS2)
    bad["card"]["why_it_matters"] = [{"text": "Capacity of 777 MTPA would lift revenue to ₹4,321 Cr", "basis": "FILING"},
                                     {"text": "Beats the run-rate implied by guidance", "basis": "MEMORY"}]
    body = _run(settings, bad, monkeypatch, "1").card["card"]
    assert [i["text"] for i in body["why_it_matters"]] == ["Beats the run-rate implied by guidance"]
    assert any(h["field"] == "why_it_matters" and "4,321" in h["text"] for h in body["parts"]["hidden"])
    assert body["parts"]["part2"]["why_it_matters"] == [0]


def test_the_mapping_is_a_code_rule():
    text = "Revenue from operations 12,000.00 9,090.91. Net profit 1,500.00."
    card = {
        "headline": "H", "takeaway": "T", "core_catalyst": "C",
        "what_happened": [{"text": "a", "quote": "Revenue from operations 12,000.00"}, {"text": "b", "quote": "not in the filing"},
                         {"text": "c", "quote": None}, "plain string"],
        "key_numbers": [{"label": "Rev", "value": "120", "quote": "Net profit 1,500.00"}, {"label": "X", "value": "1"}],
        "quantified_impact": [
            {"label": "ok", "check": "VERIFIED", "unsourced_inputs": [], "inputs": [{"source": "FILING"}, {"source": "MEMORY"}]},
            {"label": "assumed", "check": "VERIFIED", "unsourced_inputs": [], "inputs": [{"source": "FILING"}, {"source": "ASSUMPTION"}]},
            {"label": "bad", "check": "MISMATCH", "unsourced_inputs": [], "inputs": [{"source": "FILING"}]}],
        "why_it_matters": [{"text": "w"}], "notable_changes": [{"metric": "m"}], "missing_disclosures": ["x"],
        "call_takeaways": [{"text": "v", "verified": True}, {"text": "u", "verified": False}],
        "track_next": {"risks": ["r"]}, "results": {"period": "Q2FY27"}, "scale": {"amount_cr": 1}, "signals": [{"type": "S"}],
        "memory_context": [{"label": "l", "text": "t"}], "deal_value": None, "rating_change": {"after": "AA"},
    }
    parts = two_parts.split_card(card, text, "", [{"field": "why_it_matters", "text": "gone", "why": "figure not found: 9"}])
    p1, p2 = parts["part1"], parts["part2"]
    assert p1["headline"] and p1["what_happened"] == [0] and p1["key_numbers"] == [0] and p1["quantified_impact"] == [0]
    assert p1["blocks"] == ["results", "scale", "rating_change"]
    assert p2["what_happened"] == [1, 2, 3] and p2["key_numbers"] == [1] and p2["quantified_impact"] == [1, 2]
    assert p2["takeaway"] and p2["core_catalyst"] and p2["why_it_matters"] == [0] and p2["notable_changes"] == [0]
    assert p2["missing_disclosures"] == [0] and p2["call_takeaways"] == [0] and p2["track_next"]
    assert p2["blocks"] == ["signals", "memory_context"] and parts["hidden"][0]["text"] == "gone"


def test_the_last_fact_is_never_hidden(settings, monkeypatch):
    bad = copy.deepcopy(PASS2)
    bad["card"]["what_happened"] = [{"text": "Capacity of 777 MTPA and revenue of ₹4,321 Cr", "quote": None}]
    body = _run(settings, bad, monkeypatch, "1").card["card"]
    assert len(body["what_happened"]) == 1
