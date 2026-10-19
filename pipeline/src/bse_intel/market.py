"""Financial footer enrichment: price, returns, market cap, size bucket.

Prices come from bulk yfinance downloads by ticker (``SYMBOL.BO``, then ``SYMBOL.NS``, then
``SCRIP.BO``; see yahoo.py); market cap is price times shares outstanding, where
the share count is refreshed weekly per ticker. yfinance is unofficial and
rate-limited, so the job is best-effort: anything it cannot fetch keeps its
previous values (the upsert never erases fields).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta

from .settings import Settings
from . import yahoo
from .technicals import rank_rs
from .technicals import tags as price_tags
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


def median_turnover_cr(frame, days: int) -> float | None:
    """Median daily traded value (close x volume) over the last ``days`` sessions, in ₹ crore."""
    try:
        traded = (frame["Close"] * frame["Volume"]).dropna().tail(days)
        return round(float(traded.median()) / 1e7, 3) if len(traded) else None
    except Exception:
        return None


def _stale(updated_at: str | None, days: int) -> bool:
    if not updated_at:
        return True
    try:
        return now_ist() - datetime.fromisoformat(updated_at) > timedelta(days=days)
    except ValueError:
        return True


def enrich(settings: Settings, sink: Sink, all_companies: bool = False) -> int:
    import yfinance as yf  # optional dependency: pip install -e ".[market]"

    config = settings.load_toml("market.toml")
    yconf, buckets = config["yfinance"], config["size_buckets"]
    companies = (sink.query("companies_for_market_all", [20000]) if all_companies
                 else sink.query("companies_for_market", [int(yconf["max_companies"])]))
    max_lookups = len(companies) if all_companies else int(yconf["max_share_lookups"])
    if not companies:
        log.info("no companies with cards yet; nothing to enrich")
        return 0
    rows, share_lookups, now, charts = [], 0, now_iso(), 0
    missing: list[dict] = []  # companies Yahoo has no price for (decides whether a second source is needed)
    found = yahoo.download(yf, companies, int(yconf["batch"]), period="13mo")
    for company in companies:
        ticker, frame = found.get(str(company["scrip_code"]), (None, None))
        try:
            closes = [float(v) for v in frame["Close"].dropna().tolist()]
            price_date = frame["Close"].dropna().index[-1].date().isoformat() if closes else None
        except Exception:
            closes, price_date = [], None
        if not closes:
            missing.append({"scrip_code": company["scrip_code"], "symbol": company.get("symbol"), "why": "no price on Yahoo"})
            continue
        row = {"scrip_code": company["scrip_code"], "last_price": round(closes[-1], 2),
               "price_date": price_date, "updated_at": now, **returns(closes)}
        charts += write_chart(sink, str(company["scrip_code"]), frame, price_date, company.get("price_date"))
        try:
            ohlcv = frame[["High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
            row["_tech"] = {**price_tags(*(ohlcv[c].astype(float).tolist() for c in ("High", "Low", "Close", "Volume"))),
                            "as_of": price_date}
        except Exception:
            pass
        turnover = median_turnover_cr(frame, int(yconf.get("turnover_days", 30)))
        if turnover is not None:
            row["median_turnover_cr"] = turnover
        shares = company.get("shares_outstanding")
        if _stale(company.get("shares_updated_at"), int(yconf["shares_refresh_days"])) \
                and share_lookups < max_lookups:
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
    techs = [r["_tech"] for r in rows if "_tech" in r]
    rank_rs(techs)  # relative strength as a percentile among the companies priced in this run
    for r in rows:
        tech = r.pop("_tech", None)
        if tech and len(tech) > 1:
            r["technicals_json"] = json.dumps(tech)
    coverage = {"date": now, "companies": len(companies), "priced": len(rows), "missing": len(missing),
                "missing_pct": round(len(missing) / len(companies) * 100, 1), "sample": missing[:200]}
    sink.kv_set("market:coverage", json.dumps(coverage), now)
    if missing:
        log.warning("Yahoo had no price for %d of %d companies (%.1f%%); see kv market:coverage",
                    len(missing), len(companies), coverage["missing_pct"])
    written = sink.execute("companies_upsert", rows)
    sink.add_writes(utc_day(), written, now)  # counts toward the daily budget that gates backfill
    log.info("market data: %d companies updated (%d D1 rows written, %d price charts)", len(rows), written, charts)
    return len(rows)


CHART_SESSIONS = 260   # a year of trading days


def chart_series(frame, sessions: int = CHART_SESSIONS) -> dict | None:
    """A year of daily closes for the company page's price chart: {"d": [ISO dates], "c": [closes]}, oldest first."""
    try:
        closes = frame["Close"].dropna().tail(sessions)
    except Exception:
        return None
    if len(closes) < 5:
        return None
    return {"d": [ix.date().isoformat() for ix in closes.index], "c": [round(float(v), 2) for v in closes.tolist()]}


def write_chart(sink: Sink, scrip: str, frame, price_date: str | None, stored_date: str | None) -> int:
    """`chart/<scrip>.json` in R2 for the company page, written only when the price moved on a day (the job runs
    more than once a day). Returns 1 when written. A failure is logged and never stops the prices themselves."""
    if not price_date or price_date == stored_date:
        return 0
    series = chart_series(frame)
    if series is None:
        return 0
    try:
        sink.put_object(f"chart/{scrip}.json", json.dumps({**series, "as_of": price_date}, separators=(",", ":")).encode())
        return 1
    except Exception as exc:
        log.warning("price chart for %s not written: %s", scrip, exc)
        return 0
