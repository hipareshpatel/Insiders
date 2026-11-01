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


# memory's figures for Vimta Labs (consolidated, crore): EBITDA Q2FY27 40.8, Q1FY27 41.1, Q2FY26 36.9; revenue so that the margins
# are the deck's 36.4% (Q1FY27) and 35.3% (Q2FY26). The deck prints ₹ million, a tenth of memory's crore.
def _m(metric, period, value):
    return {"metric": metric, "period": period, "value": value, "basis": "CONSOLIDATED"}


MEMORY = {"financial_metrics": [_m("ebitda", "Q2FY27", 40.8), _m("ebitda", "Q1FY27", 41.1), _m("ebitda", "Q2FY26", 36.9),
                                _m("revenue", "Q2FY27", 114.93), _m("revenue", "Q1FY27", 112.91), _m("revenue", "Q2FY26", 104.53)]}


def on(monkeypatch):
    monkeypatch.setenv("CARD_RATIO_COLUMNS", "1")


def test_the_amount_rows_own_changes_read_its_columns():
    assert R.comparison_columns(AMOUNT) == (1, 2)          # 408/411 = -0.7% (QoQ), 408/369 = +10.6% (YoY)
    assert R.comparison_columns("Revenue 100 90 80 70") is None   # no change cells: the order cannot be read


def test_a_shifted_comparison_is_dropped_and_a_previous_value_corrected(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    notes = R.apply_card_json(card, MEMORY)
    assert len(notes) == 2
    assert [i["text"][:20] for i in card["why_it_matters"]] == ["The company's strong"]
    assert card["notable_changes"][0]["previous"] == "36.4% (Q1FY27)"
    assert card["what_happened"] == CARD["what_happened"]


def test_the_right_column_and_a_year_ago_comparison_are_kept(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    card["why_it_matters"][0]["text"] = "EBITDA margin of 35.5% is below the 36.4% in Q1FY27."
    card["notable_changes"][0]["previous"] = "35.3% (Q2FY26)"          # the year-ago column, named as such
    assert R.apply_card_json(card, MEMORY) == []


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("CARD_RATIO_COLUMNS", raising=False)
    monkeypatch.delenv("REPO_VARS", raising=False)
    monkeypatch.setenv("BSE_INTEL_SWITCHES", "/no/such/file.toml")
    card = copy.deepcopy(CARD)
    assert R.apply_card_json(card) == [] and card == CARD


def test_an_unreadable_amount_row_keeps_the_line(monkeypatch):
    """Lead's review of #341: one change cell cannot place the columns; the right line must stay."""
    on(monkeypatch)
    card = {"headline": "Acme Q2FY27 results",
            "what_happened": [{"text": "EBITDA ₹40.8 Cr.", "quote": "EBIDTA 408 411 -0.8% 369 819 723"}],
            "why_it_matters": [{"text": "EBITDA margin 35.5% vs 36.4% in Q1FY27.", "quote": "EBIDTA (%) 35.5% 36.4% 35.3% 36.0% 35.5%"}]}
    assert R.apply_card_json(card) == [] and len(card["why_it_matters"]) == 1


def test_the_comparison_word_nearest_the_figure_decides(monkeypatch):
    """Lead's review of #341: "35.5% vs 35.3% YoY; QoQ margin eased" is a year-ago comparison, and right."""
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    card["why_it_matters"] = [{"text": "EBITDA margin 35.5% vs 35.3% YoY; QoQ margin eased.", "quote": RATIO}]
    card["notable_changes"] = []
    assert R.apply_card_json(card) == [] and len(card["why_it_matters"]) == 1


def test_bps_and_nm_rows_are_left_alone(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    card["why_it_matters"] = [{"text": "Margin up 20 bps vs Q1FY27.", "quote": "EBIDTA margin 35.5% 36.4% (90)bps 35.3% 20bps"},
                              {"text": "Margin vs Q1FY27 not meaningful.", "quote": "EBIDTA (%) 35.5% NM 35.3%"}]
    card["notable_changes"] = []
    assert R.apply_card_json(card) == [] and len(card["why_it_matters"]) == 2



# --- blind review of release check 41318733817: most decks print the year-ago column first --------------------------------------

def test_without_memory_nothing_changes(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    assert R.apply_card_json(card) == [] and card == CARD


# YASHO Q2FY27-like: Q2FY27, Q2FY26, YoY, Q1FY27, QoQ; the card's "18.2% in Q2 FY26" is right, the run made it 24.2%
Y_AMOUNT = "EBITDA 2,100 1,820 15.4% 2,420 -13.2%"
Y_RATIO = "EBITDA Margin (%) 21.0% 18.2% 24.2%"
Y_MEMORY = {"financial_metrics": [_m("ebitda", "Q2FY27", 210.0), _m("ebitda", "Q2FY26", 182.0), _m("ebitda", "Q1FY27", 242.0),
                                  _m("revenue", "Q2FY26", 1000.0), _m("revenue", "Q1FY27", 1000.0)]}


def _yasho(previous, text):
    return {"headline": "Yasho Q2FY27 results", "basis": "CONSOLIDATED",
            "what_happened": [{"text": "EBITDA ₹210 Cr.", "quote": Y_AMOUNT}],
            "why_it_matters": [{"text": text, "quote": Y_RATIO}],
            "notable_changes": [{"previous": previous, "current": "21.0% (Q2FY27)", "quote": Y_RATIO}]}


def test_yasho_a_deck_with_the_year_ago_column_first_is_read_right(monkeypatch):
    on(monkeypatch)
    right = _yasho("18.2% (Q2FY26)", "EBITDA margin of 21.0% expanded compared to 18.2% in Q2 FY26 but moderated from 24.2% in Q1 FY27.")
    assert R.apply_card_json(right, Y_MEMORY) == []                       # main made it 24.2% (Q2FY26)
    wrong = _yasho("24.2% (Q2FY26)", "EBITDA margin of 21.0% is above the 24.2% of a year ago.")
    R.apply_card_json(wrong, Y_MEMORY)
    assert wrong["notable_changes"][0]["previous"] == "18.2% (Q2FY26)"
    # memory on the other basis does not tell the columns apart
    other = copy.deepcopy(Y_MEMORY)
    for e in other["financial_metrics"]:
        e["basis"] = "STANDALONE"
    still = _yasho("24.2% (Q2FY26)", "x")
    assert R.apply_card_json(still, other) == [] and still["notable_changes"][0]["previous"] == "24.2% (Q2FY26)"


def test_mpsltd_a_cell_that_is_not_memorys_margin_is_never_taken(monkeypatch):
    # MPSLTD-like: the ratio row carries its own change cell (2.14%), so the position lands on it; memory's margin says no
    on(monkeypatch)
    amount = "EBITDA 120 100 20.0% 110 9.1%"
    ratio = "EBITDA Margin 32.9% 30.76% 2.14%"
    memory = {"financial_metrics": [_m("ebitda", "Q4FY26", 12.0), _m("ebitda", "Q4FY25", 10.0), _m("ebitda", "Q3FY26", 11.0),
                                    _m("revenue", "Q4FY25", 32.51), _m("revenue", "Q3FY26", 35.0)]}
    card = {"headline": "MPS Q4FY26 results", "basis": "CONSOLIDATED", "results": {"period": "Q4FY26"},
            "what_happened": [{"text": "EBITDA ₹12 Cr.", "quote": amount}],
            "notable_changes": [{"previous": "30.76% (Q4FY25)", "current": "32.9% (Q4FY26)", "quote": ratio}]}
    assert R.apply_card_json(card, memory) == [] and card["notable_changes"][0]["previous"] == "30.76% (Q4FY25)"
