"""Returns over the trading-day windows the card shows (1W, 1M, 3M) and the 1Y the scoring reads."""

from bse_intel.market import returns


def test_three_month_return_is_63_trading_days_back():
    closes = [100.0] * 200 + [120.0]
    out = returns(closes)
    assert out["ret_1w"] == out["ret_1m"] == out["ret_3m"] == 20.0
    assert "ret_1y" not in out   # 201 closes: short of a year
    assert "ret_3m" not in returns([100.0] * 50)
