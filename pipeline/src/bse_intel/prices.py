"""Point-in-time prices for the history fill (the laptop's daily price series).

A card for a June 2025 filing must be scored with June 2025's price, market cap and returns, not
today's. Before the backfill, ``price-history`` stores each company's daily close and volume since
a year before ``BACKFILL_START`` as one small gzip JSON file per scrip under ``data/prices``. During
analysis, ``as_of`` rebuilds the company's footer as it stood when the filing came out.

Splits and bonuses: Yahoo's ``Close`` is already adjusted for them (``Adj Close`` additionally for
dividends), so ``close x today's share count`` is the market cap of the day without a separate
adjustment table. Share issues in between (rights, QIPs, warrants) are not reflected: the cap is
approximate in proportion to those.

When a company has no stored series (the nightly runner keeps none), cards fall back to the
current market data and drop it when stale (``signals.priced_for``).
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import statistics
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from . import yahoo
from .market import TRADING_DAYS, size_bucket
from .timeutil import IST

log = logging.getLogger(__name__)

TURNOVER_SESSIONS = 30
MAX_GAP_DAYS = 7  # a series ending more than this before the filing does not describe it


class PriceStore:
    def __init__(self, root: Path | None):
        self.root = root
        self._memo: dict[str, dict | None] = {}

    def _path(self, scrip: str) -> Path:
        return self.root / f"{scrip}.json.gz"

    def load(self, scrip: str) -> dict | None:
        if not self.root:
            return None
        scrip = str(scrip)
        if scrip not in self._memo:
            try:
                self._memo[scrip] = json.loads(gzip.decompress(self._path(scrip).read_bytes()))
            except (OSError, ValueError):
                self._memo[scrip] = None
        return self._memo[scrip]

    def save(self, scrip: str, rows: list[tuple[str, float, float]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        data = {"d": [r[0] for r in rows], "c": [round(r[1], 4) for r in rows], "v": [round(r[2]) for r in rows]}
        fd, tmp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        with os.fdopen(fd, "wb") as fh:
            fh.write(gzip.compress(json.dumps(data, separators=(",", ":")).encode()))
        os.replace(tmp, self._path(scrip))
        self._memo[str(scrip)] = data

    def as_of(self, company: dict, filed_at: str, buckets: dict | None = None) -> dict | None:
        """Price fields of the company row as known when the filing came out: the last close before
        it (the same day's close counts for a filing after 15:30 IST)."""
        data = self.load(company.get("scrip_code", ""))
        if not data or not data["d"]:
            return None
        dt = datetime.fromisoformat(filed_at).astimezone(IST)
        cutoff = dt.date() if dt.hour * 60 + dt.minute > 15 * 60 + 30 else dt.date() - timedelta(days=1)
        last = None
        for i, d in enumerate(data["d"]):
            if d > cutoff.isoformat():
                break
            last = i
        if last is None or (cutoff - date.fromisoformat(data["d"][last])).days > MAX_GAP_DAYS:
            return None
        closes = data["c"][: last + 1]
        out = {"last_price": round(closes[-1], 2), "price_date": data["d"][last], "point_in_time": True}
        for key, days in TRADING_DAYS.items():
            if len(closes) > days and closes[-1 - days]:
                out[key] = round((closes[-1] / closes[-1 - days] - 1) * 100, 2)
        volumes = data["v"][: last + 1]
        traded = [c * v for c, v in zip(closes[-TURNOVER_SESSIONS:], volumes[-TURNOVER_SESSIONS:]) if v]
        if traded:
            out["median_turnover_cr"] = round(statistics.median(traded) / 1e7, 3)
        shares = company.get("shares_outstanding")
        if shares:
            out["market_cap_cr"] = round(closes[-1] * float(shares) / 1e7, 2)
            if buckets:
                out["size_category"] = size_bucket(out["market_cap_cr"], buckets)
        return out


def point_in_time(company: dict, filed_at: str, store: PriceStore | None, buckets: dict | None = None) -> dict | None:
    """The company row with its price fields as of the filing, or None when no stored series covers it."""
    if not store:
        return None
    priced = store.as_of(company, filed_at, buckets)
    return {**company, **priced} if priced else None


def fill(settings, sink, start: str, scrips: list[str] | None = None) -> dict:
    """Download daily close and volume since ``start`` for every company (or the given scrips)."""
    import yfinance as yf  # optional dependency: pip install -e ".[market]"

    store = PriceStore(settings.price_dir)
    if not store.root:
        raise RuntimeError("PRICE_DIR is off; nothing to fill")
    companies = sink.query("companies_for_market_all", [20000])
    if scrips:
        known = {str(c["scrip_code"]): c for c in companies}
        companies = [known.get(s, {"scrip_code": s}) for s in scrips]
    batch = int(settings.load_toml("market.toml")["yfinance"]["batch"])
    stats = {"companies": len(companies), "stored": 0, "empty": 0}
    found = yahoo.download(yf, companies, batch, start=start)
    for company in companies:
        scrip = str(company["scrip_code"])
        try:
            frame = found[scrip][1]
            rows = [(idx.date().isoformat(), float(c), float(v or 0))
                    for idx, c, v in zip(frame.index, frame["Close"], frame["Volume"])]
        except Exception:
            rows = []
        if rows:
            store.save(scrip, rows)
            stats["stored"] += 1
        else:
            stats["empty"] += 1
    log.info("price history: %d of %d companies stored", stats["stored"], stats["companies"])
    return stats
