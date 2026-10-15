"""Financial footer enrichment: price, returns, market cap, size bucket.

Prices come from one bulk yfinance download per batch of BSE tickers
(``{scrip_code}.BO``); market cap is price times shares outstanding, where
the share count is refreshed weekly per ticker. yfinance is unofficial and
rate-limited, so the job is best-effort: anything it cannot fetch keeps its
previous values (the upsert never erases fields).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from .settings import Settings
from .sinks.base import Sink
from .timeutil import now_iso, now_ist, utc_day

log = logging.getLogger(__name__)

TRADING_DAYS = {"ret_1w": 5, "ret_1m": 21, "ret_1y": 250}


def size_bucket(market_cap_cr: float | None, buckets: dict) -> str | None:
    if market_cap_cr is None:
        return None
    for name in ("LARGE", "MID", "SMALL"):
        if market_cap_cr >= buckets[name]:
            return name
    return "MICRO"


def returns(closes: list[float]) -> dict:
    out = {}
    if not closes:
        return out
    last = closes[-1]
    for key, days in TRADING_DAYS.items():
        if len(closes) > days and closes[-1 - days]:
            out[key] = round((last / closes[-1 - days] - 1) * 100, 2)
        elif key == "ret_1y" and len(closes) >= 240 and closes[0]:
            out[key] = round((last / closes[0] - 1) * 100, 2)
    return out


def _stale(updated_at: str | None, days: int) -> bool:
    if not updated_at:
        return True
    try:
        return now_ist() - datetime.fromisoformat(updated_at) > timedelta(days=days)
    except ValueError:
        return True


def enrich(settings: Settings, sink: Sink) -> int:
    import yfinance as yf  # optional dependency: pip install -e ".[market]"

    config = settings.load_toml("market.toml")
    yconf, buckets = config["yfinance"], config["size_buckets"]
    companies = sink.query("companies_for_market", [int(yconf["max_companies"])])
    if not companies:
        log.info("no companies with cards yet; nothing to enrich")
        return 0
    rows, share_lookups, now = [], 0, now_iso()
    for start in range(0, len(companies), int(yconf["batch"])):
        batch = companies[start : start + int(yconf["batch"])]
        tickers = [f"{c['scrip_code']}.BO" for c in batch]
        try:
            data = yf.download(tickers, period="13mo", interval="1d", auto_adjust=False,
                               group_by="ticker", progress=False, threads=True)
        except Exception as exc:
            log.warning("price download failed for batch at %d: %s", start, exc)
            continue
        for company, ticker in zip(batch, tickers):
            try:
                frame = data[ticker] if len(tickers) > 1 else data
                closes = [float(v) for v in frame["Close"].dropna().tolist()]
                price_date = frame["Close"].dropna().index[-1].date().isoformat() if closes else None
            except Exception:
                closes, price_date = [], None
            if not closes:
                continue
            row = {"scrip_code": company["scrip_code"], "last_price": round(closes[-1], 2),
                   "price_date": price_date, "updated_at": now, **returns(closes)}
            shares = company.get("shares_outstanding")
            if _stale(company.get("shares_updated_at"), int(yconf["shares_refresh_days"])) \
                    and share_lookups < int(yconf["max_share_lookups"]):
                share_lookups += 1
                try:
                    looked_up = yf.Ticker(ticker).fast_info.get("shares")
                    if looked_up:
                        shares = float(looked_up)
                        row.update(shares_outstanding=shares, shares_updated_at=now)
                except Exception as exc:
                    log.debug("share count lookup failed for %s: %s", ticker, exc)
                time.sleep(0.4)
            if shares:
                market_cap = round(closes[-1] * shares / 1e7, 2)
                row.update(market_cap_cr=market_cap, size_category=size_bucket(market_cap, buckets))
            rows.append(row)
    written = sink.execute("companies_upsert", rows)
    sink.add_writes(utc_day(), written, now)  # counts toward the daily budget that gates backfill
    log.info("market data: %d companies updated (%d D1 rows written)", len(rows), written)
    return len(rows)
