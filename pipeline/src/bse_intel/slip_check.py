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
from .settings import slip_check_numfirst

log = logging.getLogger(__name__)

_XBRL_ROUNDING = 0.0051   # the file's crore figures are rounded to two decimals
# The numbers-first reader first (switch SLIP_CHECK_NUMFIRST, owner 29 Oct 2026, step 1): it reads scans too and has given no
# wrong figure on the two answer keys; where it gives no answer the text-layer reader below decides, as before
_NUMFIRST_METRICS = {"revenue": "revenue", "interest_earned": "revenue", "total_income": "total_income", "pbt": "pbt",
                     "pat": "pat"}


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

    def numbers_first(self, period: str, basis: str, metric: str, corrected: float) -> tuple[bool, str] | None:
        """The check by the numbers-first reader: True / False when it proves the period's figure on the basis, None to leave
        the decision to the text-layer reader (no answer, no PDF, a metric it does not read)."""
        name = _NUMFIRST_METRICS.get(metric)
        if name is None:
            return None
        from . import pdf_numbers_first as nf
        urls = self._urls(period)
        if isinstance(urls, str):
            return None
        refused: tuple[bool, str] | None = None
        for url in urls:
            data, why = self.sources.payload(url)
            if not data:
                # the text-layer reader, if it decides, must not download the file again (review of eb2474a)
                self.sources.docs.setdefault(url, (None, why or "NSE serves no file (404)"))
                continue
            if url not in self.sources.docs:     # the text-layer reader, if it decides, reads these bytes: no second download
                try:
                    self.sources.docs[url] = pdf_referee.read_document(data, ocr=self.sources.ocr)
                except Exception as exc:   # noqa: BLE001
                    self.sources.docs[url] = (None, f"unreadable ({type(exc).__name__})")
            got = nf.reading_from_tables(nf.analyse(data, ocr_garbled=True), period, name, basis)
            if got.status != "ok":
                continue
            if abs(got.value - corrected) <= _XBRL_ROUNDING + got.tol:
                return True, f"PDF p{got.page} prints {got.value:g} Cr ({got.label}; numbers-first)"
            # a False removes stored figures: a later candidate (the right filing, a restated one) may still prove it
            refused = refused or (False, f"PDF prints {got.value:g} Cr, not the corrected {corrected:g} Cr (numbers-first)")
        return refused

    def __call__(self, result, metric: str, corrected: float) -> tuple[bool, str]:
        if self.sources is None:
            return None, "no NSE client to fetch the PDF"
        period, basis = result.period, result.basis
        if slip_check_numfirst():
            try:
                proved = self.numbers_first(period, basis, metric, corrected)
            except SourceBlockedError:
                raise
            except Exception as exc:   # noqa: BLE001 - the text-layer reader still decides
                log.warning("slip check: numbers-first failed (%s); the text-layer reader decides", type(exc).__name__)
                proved = None
            if proved is not None:
                return proved
        top_line = metric == "revenue"   # revenue from operations: a "Total income" line is not it
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
                if top_line:
                    got["values"] = pdf_referee.revenue_only(got["values"])
                if not got["values"]:
                    reasons.append(got["unsure"] or f"no {metric} figure of the {period} column on the {basis} basis")
                    continue
                agree = [abs(value - corrected) <= _XBRL_ROUNDING + _half_unit(rows, metric, page)
                         for value, _label, page in got["values"]]
                shown = ", ".join(f"{v:g}" for v, _, _ in got["values"])
                if all(agree):
                    value, label, page = got["values"][0]
                    return True, f"PDF p{page} prints {value:g} Cr ({label})"
                if any(agree):   # proven rows that disagree with each other (a segment line beside the total): no proof
                    return None, f"PDF rows disagree ({shown} Cr)"
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
