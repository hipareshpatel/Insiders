"""consistency.py: a card's words against its own results table (wrong-card trace, 25 Oct 2026)."""

from bse_intel.consistency import comparison_conflict, conflicts, direction_conflict, multiple_conflict, turn_conflict

LOSS_NARROWED = {"period": "Q2FY27", "pat": {"value": -1.51, "prev_year": -8.0, "yoy_turn": "LOSS_NARROWED"},
                 "revenue": {"value": 800.0, "yoy_pct": 8.0, "qoq_pct": 2.0}}


def test_a_turn_to_profit_over_a_loss_is_faulted():
    """Sapphire Foods: "PAT turns positive" over a table whose PAT is a ₹1.51 Cr loss."""
    assert "loss of ₹1.51 Cr" in turn_conflict("Sapphire Q2 PAT turns positive; turnaround YoY", LOSS_NARROWED)
    profit = {"pat": {"value": 12.0, "yoy_turn": "LOSS_TO_PROFIT"}}
    assert turn_conflict("returns to profit after a loss", profit) is None
    assert turn_conflict("swings to a loss", {"pat": {"value": 12.0}})
    assert turn_conflict("profit turns positive", {}) is None          # no table: nothing to judge


def test_a_direction_against_both_comparisons_is_faulted():
    table = {"revenue": {"value": 900.0, "yoy_pct": -12.6, "qoq_pct": -3.9}, "pat": {"value": 50.0, "yoy_pct": -1.0}}
    assert direction_conflict("Revenue rises on new orders", table)
    assert direction_conflict("PAT up 1%", table) is None               # flat: no direction faulted
    mixed = {"revenue": {"value": 900.0, "yoy_pct": -12.6, "qoq_pct": 6.0}}
    assert direction_conflict("Revenue rises on new orders", mixed) is None   # could mean the quarter
    assert direction_conflict("Revenue rises 6% QoQ", mixed) is None
    assert direction_conflict("Revenue rises 5% YoY", mixed)             # names the year


def test_a_direction_word_between_two_stated_figures():
    """CRISIL's growth "accelerated" from 25.7% to 20.2%."""
    assert comparison_conflict("Revenue growth accelerated to 20.2% from 25.7% in 9M")
    assert comparison_conflict("Growth slowed to 18% from 22%") is None
    assert comparison_conflict("CASA moderated from 20.55% to 18.96%") is None
    assert comparison_conflict("Margin rose to 21.4% vs 25.1% a year ago")
    assert comparison_conflict("rose to 20% from ₹25 Cr") is None       # not one measure


def test_a_multiple_the_change_does_not_bear_out():
    """LMW: PAT "more than double" at +74%."""
    table = {"pat": {"value": 71.23, "yoy_pct": 74.1}}
    assert multiple_conflict("PAT more than doubled on higher volumes", table)
    assert multiple_conflict("PAT more than doubled", {"pat": {"value": 90.0, "yoy_pct": 120.0}}) is None
    assert multiple_conflict("profit halved", {"pat": {"value": 5.0, "yoy_pct": -50.0}}) is None


def test_conflicts_names_the_headline_and_the_points():
    card = {"headline": "PAT turns positive", "results": LOSS_NARROWED,
            "what_happened": [{"text": "Revenue up 8% YoY"}, {"text": "Growth accelerated to 5% from 9%"}]}
    out = conflicts(card)
    assert out["headline"] and [i for i, _ in out["points"]] == [1]
