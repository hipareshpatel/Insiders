"""The investable universe (blueprint §15 phase 3): which companies' filings are analysed.

Companies with a known market cap below ``UNIVERSE_MIN_MCAP_CR`` (default ₹100 Cr) are left out
unless the owner starred them; companies without a market cap yet stay in. The excluded list is
built after each market-data or company sync (one scan of the companies table) and published to
R2 as ``meta/universe.json``, so a pipeline run reads one small object instead of the table.
Filings of excluded companies go to the day's noise file with the reason, so nothing is silently lost.

Since 2026-10-18 the source is NSE (owner): the universe is every company on NSE's main-board equity list that
is in our company master (joined by ISIN) with a market cap of at least the floor. ``build_nse`` writes the same
file with the ISIN and symbol maps NSE discovery needs to put a filing on our company key; companies NSE lists
that the master does not have are named in it (``nse_only``) and their filings set aside with that reason.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from .settings import Settings
from .sinks.base import Sink
from .timeutil import now_iso

log = logging.getLogger(__name__)

UNIVERSE_KEY = "meta/universe.json"
PAGE = 1000


def build(settings: Settings, sink: Sink) -> int:
    floor = settings.universe_min_mcap_cr
    rows = sink.query("companies_outside_universe", [floor]) if floor > 0 else []
    body = {"min_mcap_cr": floor, "excluded": sorted(r["scrip_code"] for r in rows), "built_at": now_iso()}
    sink.put_object(UNIVERSE_KEY, json.dumps(body, separators=(",", ":")).encode())
    log.info("universe: %d companies below ₹%g Cr excluded", len(rows), floor)
    return len(rows)


def _companies(sink: Sink) -> list[dict]:
    rows: list[dict] = []
    after = ""
    while True:
        page = sink.query("companies_universe", [after, PAGE])
        if not page:
            return rows
        rows += page
        after = page[-1]["scrip_code"]


def select(equities, companies: list[dict], floor: float) -> dict:
    """The universe file's body from NSE's equity list and our company rows (pure; ``build_nse`` adds the I/O).

    A company is in when NSE lists it (matched by ISIN, else by symbol), and its market cap is at least ``floor``,
    or it is on the owner's watchlist, or it has no market cap yet (a new listing stays in until it is priced)."""
    by_isin = {(c.get("isin") or "").strip().upper(): c for c in companies if c.get("isin")}
    by_symbol = {(c.get("symbol") or "").strip().upper(): c for c in companies if c.get("symbol")}
    isins: dict[str, str] = {}
    symbols: dict[str, str] = {}
    included, excluded, unpriced, nse_only = [], [], [], []
    for eq in equities:
        company = by_isin.get(eq.isin) or by_symbol.get(eq.symbol)
        if company is None:
            nse_only.append(eq.symbol)
            continue
        scrip = company["scrip_code"]
        isins[eq.isin] = scrip
        symbols[eq.symbol] = scrip
        mcap = company.get("market_cap_cr")
        if mcap is None:
            unpriced.append(scrip)
            included.append(scrip)
        elif mcap >= floor or company.get("watchlist"):
            included.append(scrip)
        else:
            excluded.append(scrip)
    return {"source": "nse", "min_mcap_cr": floor, "included": sorted(included), "excluded": sorted(excluded),
            "unpriced": sorted(unpriced), "nse_only": sorted(nse_only), "isins": isins, "symbols": symbols,
            "counts": {"nse_listed": len(equities), "matched": len(symbols), "included": len(included),
                       "below_floor": len(excluded), "unpriced": len(unpriced), "nse_only": len(nse_only)}}


def build_nse(settings: Settings, sink: Sink, equities) -> dict:
    """Write the NSE universe file; returns its counts."""
    body = select(equities, _companies(sink), settings.universe_min_mcap_cr)
    body["built_at"] = now_iso()
    sink.put_object(UNIVERSE_KEY, json.dumps(body, separators=(",", ":")).encode())
    log.info("universe (NSE): %s", body["counts"])
    return body["counts"]


def rebuild(settings: Settings, sink: Sink) -> int:
    """Rebuild the universe file for the discovery source after a company or market-data sync; returns how many
    companies are left out. On NSE this reads NSE's equity list (one request)."""
    if settings.discovery_source != "nse":
        return build(settings, sink)
    from .nse import NseClient

    with NseClient() as client:
        counts = build_nse(settings, sink, client.equity_list())
    return counts["below_floor"] + counts["nse_only"]


def _read(sink: Sink) -> dict:
    try:
        body = sink.get_object(UNIVERSE_KEY)
    except Exception as exc:  # no universe file is the same as no filter
        log.warning("universe file unreadable: %s", exc)
        return {}
    return json.loads(body) if body else {}


def load(sink: Sink) -> tuple[set[str], float]:
    data = _read(sink)
    return set(data.get("excluded", [])), float(data.get("min_mcap_cr", 0))


@dataclass
class NseUniverse:
    """What NSE discovery needs from the universe file: our company key for an NSE row, and back."""

    isins: dict[str, str] = field(default_factory=dict)
    symbols: dict[str, str] = field(default_factory=dict)
    included: set[str] = field(default_factory=set)
    built: bool = False

    def scrip_for(self, isin: str | None, symbol: str | None) -> str | None:
        return self.isins.get((isin or "").upper()) or self.symbols.get((symbol or "").upper())

    def symbol_for(self, scrip: str) -> str | None:
        return next((s for s, c in self.symbols.items() if c == scrip), None)


def load_nse(sink: Sink) -> NseUniverse:
    data = _read(sink)
    if data.get("source") != "nse":
        return NseUniverse()
    return NseUniverse(dict(data.get("isins", {})), dict(data.get("symbols", {})), set(data.get("included", [])), True)
