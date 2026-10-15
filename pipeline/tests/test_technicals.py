from bse_intel.technicals import clenow, rank_rs, rs_score, rvol, stage2, tags, vcp


def test_stage2_needs_rising_averages_near_the_high():
    rising = [100 * 1.002 ** i for i in range(260)]
    assert stage2(rising) is True
    falling = list(reversed(rising))
    assert stage2(falling) is False
    assert stage2(rising[:100]) is None


def test_vcp_detects_a_tight_base_after_wide_swings():
    closes = [100.0] * 80
    highs = [104.0] * 60 + [100.6] * 20  # 4% daily range, then 0.6%
    lows = [96.0] * 60 + [99.6] * 20
    assert vcp(highs, lows, closes) is True
    assert vcp([104.0] * 80, [96.0] * 80, closes) is False


def test_rs_percentile_rvol_and_clenow():
    strong = [100 * 1.003 ** i for i in range(260)]
    weak = [100 * 0.999 ** i for i in range(260)]
    rows = [{"rs_raw": rs_score(strong)}, {"rs_raw": rs_score(weak)}, {"other": 1}]
    rank_rs(rows)
    assert rows[0]["rs_pct"] == 99 and rows[1]["rs_pct"] == 0 and "rs_raw" not in rows[0]
    assert rvol([1000.0] * 50 + [3000.0]) == 3.0
    assert clenow(strong) > 100 and clenow(weak) < 0
    t = tags(strong, strong, strong, [1000.0] * 260)
    assert t["stage2"] is True and "rs_raw" in t
