"""A card is priced only on a close near its filing day (data chain audit A7, 22 Oct 2026)."""
from __future__ import annotations

from bse_intel.models import Filing
from bse_intel.signals import priced_for


def _filing(day: str) -> Filing:
    return Filing(news_id="n1", scrip_code="500001", company_name="Demo Ltd", headline="h", subject="",
                  filed_at=f"{day}T10:00:00+05:30", filing_date=day)


ROW = {"scrip_code": "500001", "last_price": 120.0, "market_cap_cr": 900.0, "ret_1m": 4.2}


def test_close_from_the_filing_week_is_kept():
    assert priced_for({**ROW, "price_date": "2026-10-20"}, _filing("2026-10-22"))["last_price"] == 120.0


def test_close_a_failing_feed_left_behind_is_dropped():
    """Yahoo stopped for the ticker in August: an October card must not show August's close as its price."""
    row = priced_for({**ROW, "price_date": "2026-08-14"}, _filing("2026-10-22"))
    assert "last_price" not in row and "market_cap_cr" not in row and "ret_1m" not in row


def test_close_long_after_an_old_filing_is_dropped():
    assert "last_price" not in priced_for({**ROW, "price_date": "2026-10-21"}, _filing("2026-05-04"))


def test_no_price_date_is_no_price():
    assert "last_price" not in priced_for(ROW, _filing("2026-10-22"))
