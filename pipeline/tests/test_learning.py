from datetime import date, timedelta

from bse_intel import learning


def _sessions(start: date, n: int):
    out, day = [], start
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def test_day_zero_follows_the_1530_rule():
    days = [date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 15)]  # 14th a holiday
    assert learning.day_zero("2026-10-13T11:00:00+05:30", days) == 1
    assert learning.day_zero("2026-10-13T15:41:00+05:30", days) == 2  # after the close: next session
    assert learning.day_zero("2026-10-11T10:00:00+05:30", days) == 0  # Sunday
    assert learning.day_zero("2026-10-15T17:50:00+05:30", days) is None  # not traded yet


def test_reaction_measures_excess_return_and_volume_multiple():
    days = _sessions(date(2026, 7, 1), 70)
    filed = days[60]
    stock = [(d, 100.0, 1000.0) for d in days[:60]]
    stock += [(days[60], 110.0, 5000.0), (days[61], 112.0, 4000.0), (days[62], 115.0, 3000.0)]
    bench = {d: 1000.0 for d in days}
    bench[days[62]] = 1010.0
    rx = learning.reaction(f"{filed.isoformat()}T10:30:00+05:30", stock, bench, "^NSEI")
    assert rx["day0"] == filed.isoformat() and rx["base_date"] == days[59].isoformat()
    assert rx["t1"] == {"date": filed.isoformat(), "return_pct": 10.0, "excess_pct": 10.0, "rvol": 5.0}
    assert rx["t3"]["return_pct"] == 15.0 and rx["t3"]["excess_pct"] == 14.0 and rx["t3"]["rvol"] == 4.0
    assert "t5" not in rx and rx["complete"] == 0
    assert learning.missed_alpha("MODERATE", rx) and not learning.missed_alpha("HIGH", rx)
    rx_after = learning.reaction(f"{filed.isoformat()}T16:00:00+05:30", stock, bench)
    assert rx_after["day0"] == days[61].isoformat() and rx_after["t1"]["return_pct"] == round((112 / 110 - 1) * 100, 2)


def test_post_mortem_writes_reactions_and_flags(settings, monkeypatch):
    import sys
    import types

    import pytest

    from bse_intel.sinks.local import LocalSink

    pd = pytest.importorskip("pandas")

    days = _sessions(date(2026, 8, 1), 60)
    filed = days[50]
    sink = LocalSink(settings)
    card = {"news_id": "N1", "scrip_code": "500001", "symbol": "ABC", "company_name": "Abc", "filing_date": filed.isoformat(),
            "filed_at": f"{filed.isoformat()}T11:00:00+05:30", "sector": "GENERAL", "event_category": "ORDER_WIN",
            "impact_level": "LOW", "headline": "h", "card": {}, "created_at": "x"}
    sink.execute("cards_upsert", [card])

    def frame(closes, vols):
        return pd.DataFrame({"Close": closes, "Volume": vols}, index=pd.to_datetime(days))

    stock = frame([100.0] * 50 + [112.0] * 10, [1000.0] * 50 + [4000.0] * 10)
    index = frame([1000.0] * 60, [0.0] * 60)

    def download(tickers, **_):
        return index if tickers == "^NSEI" else (stock if tickers == ["500001.BO"] else pd.DataFrame())

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(download=download))
    monkeypatch.setattr(learning, "now_ist", lambda: pd.Timestamp(days[-1]).to_pydatetime().replace(tzinfo=learning.IST))
    stats = learning.post_mortem(settings, sink, since=days[0].isoformat())
    assert stats["updated"] == 1 and stats["complete"] == 1 and stats["missed_alpha"] == 1
    assert stats["benchmark"] == "^NSEI"
    rows = sink.query("cards_awaiting_reaction", ["", "9999", "", "", 10])
    assert rows == []  # complete: not revisited
    assert '"N1"' in sink.kv_get("learning:missed_alpha")
    assert learning.post_mortem(settings, sink, since=days[0].isoformat())["cards"] == 0


def test_market_data_records_which_companies_yahoo_lacks(settings, monkeypatch):
    import json
    import sys
    import types

    import pytest

    from bse_intel.market import enrich
    from bse_intel.sinks.local import LocalSink

    pd = pytest.importorskip("pandas")
    sink = LocalSink(settings)
    sink.execute("companies_upsert", [{"scrip_code": s, "company_name": s, "updated_at": "x"} for s in ("500001", "500002")])
    days = pd.to_datetime([d.isoformat() for d in _sessions(date(2026, 9, 1), 30)])
    priced = pd.DataFrame({"Close": [100.0] * 30, "Volume": [1000.0] * 30}, index=days)
    empty = pd.DataFrame({"Close": [float("nan")] * 30, "Volume": [0.0] * 30}, index=days)
    frame = pd.concat({"500001.BO": priced, "500002.BO": empty}, axis=1)
    yf = types.SimpleNamespace(download=lambda *a, **k: frame,
                               Ticker=lambda t: types.SimpleNamespace(fast_info={"shares": 1e7}))
    monkeypatch.setitem(sys.modules, "yfinance", yf)
    monkeypatch.setattr("bse_intel.market.time.sleep", lambda s: None)
    assert enrich(settings, sink, all_companies=True) == 1
    coverage = json.loads(sink.kv_get("market:coverage"))
    assert coverage["companies"] == 2 and coverage["missing"] == 1 and coverage["missing_pct"] == 50.0
    assert coverage["sample"][0]["scrip_code"] == "500002"
