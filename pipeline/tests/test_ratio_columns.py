"""CARD_RATIO_COLUMNS (blind audit 1 Nov 2026, VIMTALABS nse-106836191): the deck's margin row has no change cells, so laid by
position on the amount row's header its 35.3% (Q2FY26) was taken for Q1FY27 (36.4%). The rows are the live card's quotes."""

import copy

from bse_intel import ratio_columns as R

AMOUNT = "EBIDTA 408 411 -0.8% 369 10.5% 819 723 13.2%"
RATIO = "EBIDTA (%) 35.5% 36.4% 35.3% 36.0% 35.5%"
CARD = {"headline": "Vimta Labs Q2FY27 revenue ₹112 Cr; EBITDA margin 35.5%",
        "what_happened": [{"text": "**EBITDA** for Q2FY27 was **₹40.8 Cr**, with a margin of **35.5%**.", "quote": AMOUNT}],
        "why_it_matters": [{"text": "EBITDA margin of 35.5% in Q2FY27 is higher than the 35.3% in Q1FY27, showing margin expansion.",
                            "quote": RATIO},
                           {"text": "The company's strong EBITDA margin of 35.5% is above the sector's.", "quote": ""}],
        "notable_changes": [{"previous": "35.3% (Q1FY27)", "current": "35.5% (Q2FY27)", "quote": RATIO}]}


def on(monkeypatch):
    monkeypatch.setenv("CARD_RATIO_COLUMNS", "1")


def test_the_amount_rows_own_changes_read_its_columns():
    assert R.comparison_columns(AMOUNT) == (1, 2)          # 408/411 = -0.7% (QoQ), 408/369 = +10.6% (YoY)
    assert R.comparison_columns("Revenue 100 90 80 70") is None   # no change cells: the order cannot be read


def test_a_shifted_comparison_is_dropped_and_a_previous_value_corrected(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    notes = R.apply_card_json(card)
    assert len(notes) == 2
    assert [i["text"][:20] for i in card["why_it_matters"]] == ["The company's strong"]
    assert card["notable_changes"][0]["previous"] == "36.4% (Q1FY27)"
    assert card["what_happened"] == CARD["what_happened"]


def test_the_right_column_and_a_year_ago_comparison_are_kept(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    card["why_it_matters"][0]["text"] = "EBITDA margin of 35.5% is below the 36.4% in Q1FY27."
    card["notable_changes"][0]["previous"] = "35.3% (Q2FY26)"          # the year-ago column, named as such
    assert R.apply_card_json(card) == []


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("CARD_RATIO_COLUMNS", raising=False)
    monkeypatch.delenv("REPO_VARS", raising=False)
    monkeypatch.setenv("BSE_INTEL_SWITCHES", "/no/such/file.toml")
    card = copy.deepcopy(CARD)
    assert R.apply_card_json(card) == [] and card == CARD
