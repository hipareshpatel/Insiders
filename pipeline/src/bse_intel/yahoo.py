"""Yahoo Finance tickers for the companies, and one batched download with fallbacks.

The platform reads NSE only (owner, 2026-10-19), so each company is tried on its NSE listing first
(``RELIANCE.NS``), then on BSE by symbol (``RELIANCE.BO``, the same company and share count), then by its
BSE scrip code (``500325.BO``) when its key is one; each round downloads only the companies still missing.
A company added from NSE's list has its NSE symbol as its key, so it has no scrip-code ticker.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)


def candidates(company: dict) -> list[str]:
    scrip = str(company["scrip_code"])
    symbol = re.sub(r"[^A-Z0-9&-]", "", str(company.get("symbol") or "").upper())
    out = [f"{symbol}.NS", f"{symbol}.BO"] if symbol and not symbol.isdigit() else []
    return out + ([f"{scrip}.BO"] if scrip.isdigit() else [])


def _frame(data, ticker: str, single: bool):
    try:
        try:
            frame = data[ticker]
        except KeyError:
            if not single:
                return None
            frame = data
        frame = frame.dropna(subset=["Close"])
        return frame if len(frame) else None
    except Exception:
        return None


def download(yf, companies: list[dict], batch: int, **kwargs) -> dict[str, tuple[str, object]]:
    """{scrip_code: (ticker, daily frame)} for every company Yahoo has prices for."""
    found: dict[str, tuple[str, object]] = {}
    tries = {str(c["scrip_code"]): candidates(c) for c in companies}
    for round_ in range(max(len(t) for t in tries.values()) if tries else 0):
        todo = [(s, t[round_]) for s, t in tries.items() if s not in found and round_ < len(t)]
        for at in range(0, len(todo), batch):
            chunk = todo[at:at + batch]
            tickers = [t for _, t in chunk]
            try:
                data = yf.download(tickers, interval="1d", auto_adjust=False, group_by="ticker",
                                   progress=False, threads=True, **kwargs)
            except Exception as exc:
                log.warning("Yahoo download failed for %d tickers: %s", len(tickers), exc)
                continue
            for scrip, ticker in chunk:
                frame = _frame(data, ticker, len(tickers) == 1)
                if frame is not None:
                    found[scrip] = (ticker, frame)
        log.info("Yahoo round %d: %d of %d companies priced", round_ + 1, len(found), len(tries))
    return found
