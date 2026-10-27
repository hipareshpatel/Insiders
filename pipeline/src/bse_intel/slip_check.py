"""The two-source rule for a unit-slip correction (owner, 27 Oct 2026, TODO 102, F200).

``xbrl.fix_scale`` multiplies a results file's amounts by 10^k when the company's other quarters say the file is tagged
in the wrong unit. That is one source (our own memory) judging another (the file). The correction is made only when the
filing's own PDF, read from its text layer (never OCR or AI), prints the corrected figure for the quarter's column on the
file's basis. A PDF that disagrees, or cannot be read, leaves the quarter out of memory (a missing quarter is better than
a wrong one) and the caller records it as held. The check answers True (agrees), False (the PDF prints another figure)
or None (no PDF could be read, or it has no such figure): only False removes what an earlier seed stored from the file;
None leaves memory as it was, so an NSE hiccup never deletes figures.

The PDF is fetched only when a slip is found, so the normal path makes no extra NSE call.
"""
from __future__ import annotations

import logging

from . import pdf_referee
from .nse import SourceBlockedError

log = logging.getLogger(__name__)

_XBRL_ROUNDING = 0.0051   # the file's crore figures are rounded to two decimals


class PdfCheck:
    """Callable ``(result, metric, corrected_crore) -> (agrees, why)``, agrees True / False / None (unsure) reading the quarter's results PDF text layer."""

    def __init__(self, nse, symbol: str = "", pdf_url: str | None = None, pdf_period: str | None = None):
        self.nse, self.symbol = nse, (symbol or "").strip().upper()
        self.pdf_url, self.pdf_period = pdf_url, pdf_period   # a PDF known to be the period's (the filing's own)
        self._sources = None

    @property
    def sources(self):
        if self._sources is None and self.nse is not None:
            self._sources = pdf_referee.Sources(self.nse, ocr=False)
        return self._sources

    def _urls(self, period: str) -> list[str] | str:
        if self.pdf_url and self.pdf_period == period:
            return [self.pdf_url]
        if not self.symbol:
            return "no NSE symbol to find the quarter's PDF"
        listed = self.sources.filings(self.symbol, period)
        if isinstance(listed, str):
            return listed
        return [f.pdf_url for f in listed[:pdf_referee.MAX_CANDIDATES]]

    def __call__(self, result, metric: str, corrected: float) -> tuple[bool, str]:
        if self.sources is None:
            return None, "no NSE client to fetch the PDF"
        period, basis = result.period, result.basis
        metric = "revenue" if metric in ("revenue", "total_income", "interest_earned") else metric
        try:
            urls = self._urls(period)
            if isinstance(urls, str):
                return None, urls
            reasons: list[str] = []
            for url in urls:
                rows, why = self.sources.rows(url)
                if rows is None:
                    reasons.append(why)
                    continue
                got = pdf_referee.figure_for(rows, period, metric, basis)
                if not got["values"]:
                    reasons.append(got["unsure"] or f"no {metric} figure of the {period} column on the {basis} basis")
                    continue
                for value, label, page in got["values"]:
                    tolerance = _XBRL_ROUNDING + _half_unit(rows, metric, page)
                    if abs(value - corrected) <= tolerance:
                        return True, f"PDF p{page} prints {value:g} Cr ({label})"
                shown = ", ".join(f"{v:g}" for v, _, _ in got["values"])
                return False, f"PDF prints {shown} Cr, not the corrected {corrected:g} Cr"
            return None, "; ".join(dict.fromkeys(reasons))[:200] or "no results PDF read"
        except SourceBlockedError:
            raise
        except Exception as exc:   # noqa: BLE001 - an unreadable PDF holds the quarter, it does not stop the run
            return None, f"PDF check failed ({type(exc).__name__})"


def _half_unit(rows, metric: str, page: int) -> float:
    """Half a unit of the decimals the page prints, in crore: the PDF's own rounding."""
    half = 0.0
    for r in rows:
        if r.metric != metric or r.page != page or not r.unit:
            continue
        for fig in r.figures:
            text = repr(float(fig))
            decimals = len(text.split(".")[1].rstrip("0")) if "." in text else 0
            half = max(half, 0.5 * 10 ** -decimals / r.unit)
    return half
