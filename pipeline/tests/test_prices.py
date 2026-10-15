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
