from datetime import date, timedelta

from bse_intel.prices import PriceStore, point_in_time


def _rows(start: date, closes):
    out, day = [], start
    for c in closes:
        while day.weekday() >= 5:
            day += timedelta(days=1)
        out.append((day.isoformat(), c, 1_000_000.0))
        day += timedelta(days=1)
    return out


def test_as_of_uses_the_close_known_when_the_filing_came_out(tmp_path):
    store = PriceStore(tmp_path)
    rows = _rows(date(2025, 5, 1), [100.0 + i for i in range(40)])
    store.save("500001", rows)
    company = {"scrip_code": "500001", "shares_outstanding": 1e7, "last_price": 900.0, "market_cap_cr": 900.0}
    day = rows[30][0]
    live = point_in_time(company, f"{day}T11:00:00+05:30", PriceStore(tmp_path), {"LARGE": 20000, "MID": 5000, "SMALL": 500})
    assert live["last_price"] == 129.0 and live["price_date"] == rows[29][0]  # the previous close
    assert live["market_cap_cr"] == 129.0 and live["size_category"] == "MICRO" and live["point_in_time"]
    assert live["ret_1w"] == round((129 / 124 - 1) * 100, 2)
    assert live["median_turnover_cr"] > 0
    after = point_in_time(company, f"{day}T17:50:00+05:30", store)
    assert after["last_price"] == 130.0  # after the close, that day's close was known
    assert point_in_time(company, "2024-01-10T11:00:00+05:30", store) is None  # before the series
    assert point_in_time(company, "2026-01-10T11:00:00+05:30", store) is None  # long after it ends
    assert point_in_time({"scrip_code": "999"}, f"{day}T11:00:00+05:30", store) is None
    assert point_in_time(company, f"{day}T11:00:00+05:30", None) is None


def test_yahoo_tries_nse_then_bse_then_scrip_code():
    import types

    import pytest

    from bse_intel import yahoo

    pd = pytest.importorskip("pandas")
    assert yahoo.candidates({"scrip_code": "500325", "symbol": "RELIANCE"}) == ["RELIANCE.NS", "RELIANCE.BO", "500325.BO"]
    assert yahoo.candidates({"scrip_code": "999999", "symbol": None}) == ["999999.BO"]
    # a company added from NSE's list is keyed by its symbol: no scrip-code ticker (owner, 2026-10-19: NSE only)
    assert yahoo.candidates({"scrip_code": "NEWCO", "symbol": "NEWCO"}) == ["NEWCO.NS", "NEWCO.BO"]
    days = pd.to_datetime(["2026-10-01", "2026-10-02"])
    ok = pd.DataFrame({"Close": [10.0, 11.0], "Volume": [1.0, 2.0]}, index=days)
    blank = pd.DataFrame({"Close": [float("nan")] * 2, "Volume": [0.0] * 2}, index=days)
    served = {"RELIANCE.BO": ok, "TCS.NS": ok}   # TCS only on NSE; 500003 nowhere
    asked = []

    def download(tickers, **_):
        asked.append(list(tickers))
        return pd.concat({t: served.get(t, blank) for t in tickers}, axis=1)

    found = yahoo.download(types.SimpleNamespace(download=download),
                           [{"scrip_code": "500325", "symbol": "RELIANCE"}, {"scrip_code": "532540", "symbol": "TCS"},
                            {"scrip_code": "500003", "symbol": "GONE"}], batch=50, period="1mo")
    assert {s: t for s, (t, _) in found.items()} == {"500325": "RELIANCE.BO", "532540": "TCS.NS"}
    assert asked == [["RELIANCE.NS", "TCS.NS", "GONE.NS"], ["RELIANCE.BO", "GONE.BO"], ["500003.BO"]]


def test_a_company_without_a_share_count_gets_its_market_cap_at_the_filing_price(tmp_path):
    """Novartis India (live review 2026-10-20): no share count stored, so the row kept today's ₹4,783 Cr market cap beside
    each filing's own price, and three cards measured deals against it."""
    store = PriceStore(tmp_path)
    rows = _rows(date(2025, 5, 1), [100.0 + i for i in range(40)])
    store.save("500002", rows)
    company = {"scrip_code": "500002", "last_price": 200.0, "market_cap_cr": 2000.0}   # implies 10 crore shares
    live = point_in_time(company, f"{rows[30][0]}T11:00:00+05:30", store)
    assert live["last_price"] == 129.0 and live["market_cap_cr"] == 1290.0
    # nothing to infer the count from: no market cap at all rather than today's
    bare = point_in_time({"scrip_code": "500002", "market_cap_cr": 2000.0}, f"{rows[30][0]}T11:00:00+05:30", store)
    assert bare["market_cap_cr"] is None
