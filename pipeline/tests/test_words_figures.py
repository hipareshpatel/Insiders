"""CARD_WORDS_MATCH_FIGURES (blind audit 1 Nov 2026, "arithmetic in words"): a comparison word the card's own figures
contradict is dropped from a list or softened in the headline."""

import copy

from bse_intel import words_figures as W

CARD = {
    "headline": "Acme Q2FY27 revenue growth accelerated to 12%; PAT doubled to ₹50 Cr",
    "takeaway": "Revenue growth of 12% outpaced costs.",
    "what_happened": [{"text": "**Revenue** rose 12% YoY to ₹1,120 Cr."},
                      {"text": "Revenue growth of 12% far outpaced the industry's 18%."},
                      {"text": "EBITDA doubled YoY to ₹200 Cr."}],
    "results": {"period": "Q2FY27",
                "revenue": {"value": 1120.0, "prev_quarter": 1100.0, "yoy_pct": 12.0, "qoq_pct": 1.8},
                "ebitda": {"value": 200.0, "yoy_pct": 105.0, "qoq_pct": 10.0},
                "pat": {"value": 50.0, "yoy_pct": 40.0, "qoq_pct": 5.0}},
}
# memory: Q1FY27 revenue 1,100 against Q1FY26 900 = +22.2% YoY, so +12% this quarter is a slowdown
MEMORY = {"financial_metrics": [{"metric": "revenue", "period": "Q1FY27", "value": 1100.0},
                                {"metric": "revenue", "period": "Q1FY26", "value": 900.0}]}


def on(monkeypatch):
    monkeypatch.setenv("CARD_WORDS_MATCH_FIGURES", "1")


def test_contradicted_words_are_softened_or_dropped(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    notes = W.apply_card_json(card, MEMORY)
    assert card["headline"] == "Acme Q2FY27 revenue growth rose to 12%; PAT rose to ₹50 Cr"
    texts = [i["text"] for i in card["what_happened"]]
    assert "Revenue growth of 12% far outpaced the industry's 18%." not in texts   # 12 is not above 18
    assert "EBITDA doubled YoY to ₹200 Cr." in texts                              # +105% YoY: doubled is right
    assert "**Revenue** rose 12% YoY to ₹1,120 Cr." in texts
    assert len(notes) == 3


def test_words_the_figures_support_stay(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    card["results"]["pat"]["yoy_pct"] = 110.0
    card["results"]["revenue"]["yoy_pct"] = 30.0      # above last quarter's +22.2%: accelerated
    card["what_happened"][1]["text"] = "Revenue growth of 30% far outpaced the industry's 18%."
    assert W.apply_card_json(card, MEMORY) == []


def test_no_figure_no_judgement(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    assert W.apply_card_json(dict(card, results=None)) == []
    card["headline"] = "Acme revenue growth accelerated to 12%"
    card["what_happened"], card["takeaway"] = [], ""
    assert W.apply_card_json(card, None) == []   # no previous quarter's YoY without memory
    card = copy.deepcopy(CARD)
    card["headline"] = "Acme order book doubled to ₹5,000 Cr"   # no order book in the table
    card["what_happened"], card["takeaway"] = [], ""
    assert W.apply_card_json(card, MEMORY) == []


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("CARD_WORDS_MATCH_FIGURES", raising=False)
    monkeypatch.delenv("REPO_VARS", raising=False)
    monkeypatch.setenv("BSE_INTEL_SWITCHES", "/no/such/file.toml")
    card = copy.deepcopy(CARD)
    assert W.apply_card_json(card, MEMORY) == [] and card == CARD
