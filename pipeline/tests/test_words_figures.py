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
    "basis": "CONSOLIDATED",
    "results": {"period": "Q2FY27",
                "revenue": {"value": 1120.0, "prev_quarter": 1100.0, "yoy_pct": 12.0, "qoq_pct": 1.8},
                "ebitda": {"value": 200.0, "yoy_pct": 105.0, "qoq_pct": 10.0},
                "pat": {"value": 50.0, "yoy_pct": 40.0, "qoq_pct": 5.0}},
}
# memory: Q1FY27 revenue 1,100 against Q1FY26 900 = +22.2% YoY, so +12% this quarter is a slowdown
MEMORY = {"financial_metrics": [{"metric": "revenue", "period": "Q1FY27", "value": 1100.0, "basis": "CONSOLIDATED"},
                                {"metric": "revenue", "period": "Q1FY26", "value": 900.0, "basis": "CONSOLIDATED"}]}


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


def test_list_items_keep_their_facts_with_the_word_softened(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    card["what_happened"].append({"text": "PAT doubled to ₹50 Cr on lower costs."})
    W.apply_card_json(card, MEMORY)
    assert {"text": "PAT rose to ₹50 Cr on lower costs."} in card["what_happened"]


def test_memory_on_the_other_basis_is_not_read(monkeypatch):
    """Lead's review of #326: a standalone previous quarter must not judge a consolidated card's pace."""
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    card["what_happened"], card["takeaway"] = [], ""
    card["headline"] = "Acme Q2FY27 revenue growth accelerated to 12%"
    standalone = {"financial_metrics": [dict(m, basis="STANDALONE") for m in MEMORY["financial_metrics"]]}
    assert W.apply_card_json(card, standalone) == []
    assert W.apply_card_json(dict(copy.deepcopy(card), basis=None), MEMORY) == []   # no basis: memory is not read


def test_a_fall_on_either_side_of_an_outpacing_is_not_judged(monkeypatch):
    """Lead's review of #326: the figures carry no sign."""
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    card["headline"], card["takeaway"] = "", ""
    card["what_happened"] = [{"text": "Volumes fell 5%, outperforming the industry's 10% decline."},
                             {"text": "Volumes fell 5%, outperforming the industry, down 10%."}]
    assert W.apply_card_json(card, MEMORY) == []


def test_a_pace_word_about_something_else_is_not_judged(monkeypatch):
    """Lead's review of #326: "slowing demand" is not revenue's growth slowing."""
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    card["headline"], card["takeaway"] = "", ""
    card["results"]["revenue"]["yoy_pct"] = 30.0   # above last quarter's +22.2%: a bound "slowed" would be contradicted
    card["what_happened"] = [{"text": "Revenue grew 30% YoY despite slowing demand in exports."}]
    assert W.apply_card_json(card, MEMORY) == []
    card["what_happened"] = [{"text": "Revenue growth slowed to 30% YoY."}]
    assert len(W.apply_card_json(card, MEMORY)) == 1


def _judged(monkeypatch, headline, **row):
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    card["takeaway"], card["what_happened"] = "", []
    card["headline"] = headline
    card["results"]["revenue"].update(row)
    return card, W.apply_card_json(card, MEMORY)


def test_another_period_is_not_judged_against_the_quarter_row(monkeypatch):
    card, notes = _judged(monkeypatch, "FY26 revenue doubled", yoy_pct=40.0)
    assert notes == [] and card["headline"] == "FY26 revenue doubled"


def test_the_column_named_nearest_the_word_is_the_one_judged(monkeypatch):
    card, notes = _judged(monkeypatch, "Revenue doubled QoQ", qoq_pct=110.0, yoy_pct=20.0)
    assert notes == [] and card["headline"] == "Revenue doubled QoQ"
    card, notes = _judged(monkeypatch, "Revenue doubled", qoq_pct=110.0, yoy_pct=None)
    assert notes == []
    card, notes = _judged(monkeypatch, "Revenue doubled", qoq_pct=110.0, yoy_pct=20.0)   # no column named: YoY alone
    assert len(notes) == 1


def test_the_metric_is_the_noun_directly_before_the_word(monkeypatch):
    card, notes = _judged(monkeypatch, "Provisions tripled while PAT rose 10%")
    card["results"]["pat"]["yoy_pct"] = 10.0
    assert W.apply_card_json(card, MEMORY) == [] and notes == []
    card, notes = _judged(monkeypatch, "PAT is down as provisions tripled")
    assert notes == []
    card, notes = _judged(monkeypatch, "Revenue and content investment doubled")
    assert notes == []


def test_a_modifier_is_softened_with_its_word(monkeypatch):
    card, _ = _judged(monkeypatch, "PAT nearly doubled to ₹50 Cr")
    assert card["headline"] == "PAT rose to ₹50 Cr"
    card, _ = _judged(monkeypatch, "Revenue more than doubled to ₹50 Cr", yoy_pct=40.0)
    assert card["headline"] == "Revenue rose to ₹50 Cr"


def test_a_sentence_naming_the_quarter_and_its_comparison_is_judged(monkeypatch):
    """Lead's review of #337: the commonest card sentence names both quarters and must still be judged."""
    on(monkeypatch)
    card = {"headline": "", "takeaway": "", "basis": "CONSOLIDATED",
            "what_happened": [{"text": "Revenue doubled YoY to ₹200 Cr in Q2FY27 from ₹100 Cr in Q2FY26."}],
            "results": {"period": "Q2FY27", "revenue": {"value": 200.0, "yoy_pct": 20.0, "qoq_pct": 5.0}}}
    notes = W.apply_card_json(card, None)
    assert len(notes) == 1 and card["what_happened"][0]["text"].startswith("Revenue rose YoY")
    card["what_happened"] = [{"text": "Revenue doubled YoY to ₹200 Cr in Q2FY27 from ₹100 Cr in Q1FY27."}]
    assert len(W.apply_card_json(card, None)) == 1          # the previous quarter is a comparison too
    card["what_happened"] = [{"text": "FY26 revenue doubled to ₹800 Cr."}]
    assert W.apply_card_json(card, None) == []              # a year is still another period


def test_a_phrase_across_two_spaces_is_softened(monkeypatch):
    on(monkeypatch)
    card = {"headline": "PAT nearly  doubled to ₹50 Cr", "takeaway": "",
            "results": {"period": "Q2FY27", "pat": {"value": 50.0, "yoy_pct": 40.0}}}
    W.apply_card_json(card, None)
    assert card["headline"] == "PAT rose to ₹50 Cr"
