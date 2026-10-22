"""Corporate actions from NSE's feed (data chain audit, 22 Oct 2026): rows as NSE serves them (measured that day)."""

from bse_intel.corporate_actions import merge, parse_row, share_factor_after


def _row(subject, ex="12-Jun-2026", symbol="CUB"):
    return {"symbol": symbol, "exDate": ex, "recDate": ex, "subject": subject, "comp": "X", "series": "EQ"}


def test_splits_bonuses_and_dividends_are_read():
    assert parse_row(_row("Bonus 1:3"))["factor"] == round(4 / 3, 6)              # one new share for every three held
    assert parse_row(_row("Bonus 4:1"))["factor"] == 5.0
    split = parse_row(_row("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share"))
    assert split["kind"] == "SPLIT" and split["factor"] == 10.0
    assert parse_row(_row("Face Value Split (Sub-Division) - From Rs 5/- Per Share To Rs 2/- Per Share"))["factor"] == 2.5
    dividend = parse_row(_row("Interim Dividend - Rs 2.50 Per Share"))
    assert dividend["kind"] == "DIVIDEND" and dividend["per_share"] == 2.5 and "factor" not in dividend
    ncrps = parse_row(_row("Scheme Of Arrangement - Bonus Ncrps 46:1"))     # preference shares: no equity factor
    assert "factor" not in ncrps
    assert parse_row(_row("Buy Back"))["kind"] == "BUYBACK" and parse_row(_row("Rights 1:5 @ Premium Rs 90/-"))["kind"] == "RIGHTS"
    assert parse_row({"symbol": "", "exDate": "x", "subject": "Bonus 1:1"}) is None
    assert parse_row(_row("Bonus 1:1"))["ex_date"] == "2026-06-12"


def test_per_share_figures_before_an_action_are_put_on_todays_share_count():
    d: dict = {}
    actions = [parse_row(_row("Bonus 1:1", "29-May-2026", "LICI")),
               parse_row(_row("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share", "04-Sep-2026", "LICI")),
               parse_row(_row("Dividend - Rs 10 Per Share", "20-Jul-2026", "LICI"))]
    assert merge(d, actions) == 3 and merge(d, actions) == 0                      # the same row twice is one action
    assert share_factor_after(d, "2026-03-31") == 10.0                            # before both: x2 then x5
    assert share_factor_after(d, "2026-06-30") == 5.0                             # after the bonus, before the split
    assert share_factor_after(d, "2026-09-30") == 1.0


def test_a_corporate_action_card_gets_its_ratio_dates_and_yield():
    from bse_intel.corporate_actions import card_block

    d: dict = {}
    merge(d, [parse_row(_row("Bonus 1:1", "29-May-2026", "LICI")), parse_row(_row("Dividend - Rs 10 Per Share", "20-Jul-2026", "LICI"))])
    bonus = card_block(d, "2026-05-02T18:00:00+05:30", "LIC board approves 1:1 bonus issue", 900.0)
    assert bonus["kind"] == "BONUS" and bonus["factor"] == 2.0 and bonus["ex_date"] == "2026-05-29"
    dividend = card_block(d, "2026-07-01T18:00:00+05:30", "Board declares final dividend of ₹10 a share", 800.0)
    assert dividend["per_share"] == 10.0 and dividend["yield_pct"] == 1.25
    assert card_block(d, "2026-01-01T18:00:00+05:30", "bonus issue", 900.0) is None       # ex-date over 120 days on
    assert card_block(d, "2026-05-02T18:00:00+05:30", "board meeting outcome", 900.0) is None   # no kind named
