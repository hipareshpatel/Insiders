"""F202 (TODO 104): a restated comparative kept beside the original, read from the later filing's PDF text layer.

NSE's XBRL carries only the current period, so a company that restates an earlier quarter in a later results file shows the
restated figure only in that PDF's comparative columns (360ONE's consolidated Q3FY24 revenue is 647.68 in its own file and
629.79 in the next one). Memory keeps both: the history (``financial_metrics``) keeps the original from the period's own
file, and the dossier's ``restated_figures`` list holds the restated one with its source. Nothing here uses OCR or an AI call:
the columns are read with ``pdf_referee.read_document(ocr=False)`` and ``figure_for``, which proves the column and the basis
from the page's own header, and a figure it cannot prove is not stored.

CARD_YOY_RESTATED (settings) makes a card's YoY use the restated base, saying "vs restated"; the history never changes."""
from __future__ import annotations

import copy
import logging
import re
from datetime import datetime, timezone

from . import pdf_referee as pr
from .dossier import keep_concurrent_writes
from .periods import prior_quarter_period, prior_year_period

log = logging.getLogger("bse_intel.restated_pdf")

METRICS = ("revenue", "pat")        # the rows the PDF reader tells apart (EPS is left out: share counts change it)
KEY = "restated_figures"
NOTE = "vs restated"


def decimals_of(value: float) -> int:
    """The decimals a printed crore figure shows (the readers return it as a float): 647.68 is 2, 1259.0 is 0."""
    text = f"{value:.4f}".rstrip("0")
    return max(0, len(text.partition(".")[2]))


def differs(original: float, printed: float) -> bool:
    """Whether the printed comparative differs from the original beyond half a unit of the decimals printed (the coarser of
    the two figures' decimals, so 647.68 against 647.7 is rounding, 647.68 against 629.79 is not)."""
    half = 0.5 * 10 ** -min(decimals_of(original), decimals_of(printed))
    return abs(printed - original) > half + 1e-9


def chosen_basis(entries: list[dict]) -> str | None:
    """The basis a company's memory is stated on: consolidated when any of its sources is."""
    bases = {s.get("basis") for e in entries for s in (e.get("sources") or [e])} - {None}
    return "CONSOLIDATED" if "CONSOLIDATED" in bases else next(iter(sorted(bases)), None)


def original_of(entry: dict | None, basis: str | None) -> tuple[float, str] | None:
    """(value, news_id) of the figure from the period's own file: the earliest exchange source that is not a later file's
    comparative column, on the basis. None when memory holds none (the period's own file was never read)."""
    if not entry or entry.get("unit", "INR_CR") != "INR_CR":
        return None
    sources = entry.get("sources") or [{**entry, "news_id": entry.get("source_news_id")}]
    own = [s for s in sorted(sources, key=lambda s: s.get("as_of") or "")
           if not s.get("restated_from") and s.get("value") is not None and s.get("basis") in (None, basis)
           and str(s.get("news_id", "")).startswith("xbrl:")]
    return (float(own[0]["value"]), str(own[0]["news_id"])) if own else None


def comparatives(rows: list, period: str, basis: str) -> list[dict]:
    """The year-ago and previous-quarter columns a results filing of ``period`` prints, one figure per metric where the
    reader proves the column and the basis: [{metric, period, basis, value}]."""
    out = []
    for target in (prior_year_period(period), prior_quarter_period(period)):
        if not target:
            continue
        for metric in METRICS:
            got = pr.figure_for(rows, target, metric, basis)
            values = {round(v, 4) for v, _label, _page in got["values"]}
            if len(values) == 1:        # none, or two readings that disagree: nothing stored
                out.append({"metric": metric, "period": target, "basis": basis, "value": values.pop()})
    return out


def find(dossier: dict, rows: list, period: str, basis: str, filing_id: str = "", url: str = "") -> list[dict]:
    """Restated figures: the printed comparatives of the filing for ``period`` that differ from the period's original in
    memory. Each record keeps both figures and where each came from."""
    entries = {(e["metric"], e["period"]): e for e in dossier.get("financial_metrics", [])}
    found = []
    for c in comparatives(rows, period, basis):
        original = original_of(entries.get((c["metric"], c["period"])), basis)
        if original is None or not differs(original[0], c["value"]):
            continue
        found.append({"metric": c["metric"], "period": c["period"], "basis": basis, "unit": "INR_CR",
                      "original": original[0], "original_news_id": original[1],
                      "restated": c["value"], "restated_in": period, "restated_news_id": filing_id, "restated_url": url,
                      "read": "pdf_text"})
    return found


def _unchanged(dossier: dict, comparative: dict, basis: str) -> bool:
    """Whether a printed comparative was checked against memory's original and found the same: only such a figure
    clears an older restatement (a comparative memory holds no original for proves nothing; review of #168)."""
    entry = next((e for e in dossier.get("financial_metrics", [])
                  if (e.get("metric"), e.get("period")) == (comparative["metric"], comparative["period"])), None)
    original = original_of(entry, basis)
    return original is not None and not differs(original[0], comparative["value"])


def _key(period: str) -> tuple[int, int]:
    m = re.fullmatch(r"Q([1-4])FY(\d{2})", period or "")
    return (int(m.group(2)), int(m.group(1))) if m else (0, 0)


def _later(a: str, b: str) -> bool:
    return _key(a) > _key(b)


def merge(dossier: dict, records: list[dict], cleared: list[tuple] = ()) -> int:
    """Store ``records`` in the dossier's ``restated_figures`` (the latest filing's reading of a period wins); ``cleared``
    are (metric, period, basis, filing period) the later filing printed unchanged, which drops an older restatement.
    Returns how many records changed."""
    keep = {(r["metric"], r["period"], r["basis"]): r for r in dossier.get(KEY, [])}
    changed = 0
    for r in records:
        k = (r["metric"], r["period"], r["basis"])
        old = keep.get(k)
        if old and _later(old["restated_in"], r["restated_in"]):
            continue
        if old != r:
            keep[k], changed = r, changed + 1
    for metric, period, basis, filed in cleared:
        k = (metric, period, basis)
        if k in keep and _later(filed, keep[k]["restated_in"]):
            del keep[k]
            changed += 1
    if keep:
        dossier[KEY] = sorted(keep.values(), key=lambda r: (_key(r["period"]), r["metric"], r["basis"]))
    else:
        dossier.pop(KEY, None)
    return changed


def read_company(src, symbol: str, dossier: dict, quarters: int = 6) -> tuple[list[dict], list[tuple], list[str]]:
    """Read the results PDFs of a company's latest ``quarters`` quarters in memory and return (restated records, unchanged
    comparatives, reasons a quarter was not read). Text layer only: ``src`` is a ``pdf_referee.Sources`` made with ocr=False."""
    metrics = [e for e in dossier.get("financial_metrics", [])
               if e.get("metric") in METRICS and str(e.get("period", "")).startswith("Q")]
    basis = chosen_basis(metrics)
    if not basis:
        return [], [], ["no basis in memory"]
    periods = sorted({e["period"] for e in metrics}, key=_key, reverse=True)[:quarters]
    records, cleared, reasons = [], [], []
    for period in periods:
        listed = src.filings(symbol, period)
        if isinstance(listed, str):
            reasons.append(f"{period}: {listed}")
            continue
        for f in listed[:pr.MAX_CANDIDATES]:
            rows, why = src.rows(f.pdf_url)
            if rows is None:
                reasons.append(f"{period}: {why}")
                continue
            mine = find(dossier, rows, period, basis, f.news_id, f.pdf_url)
            records += mine
            seen = {(r["metric"], r["period"]) for r in mine}
            cleared += [(c["metric"], c["period"], basis, period) for c in comparatives(rows, period, basis)
                        if (c["metric"], c["period"]) not in seen and _unchanged(dossier, c, basis)]
            break
    return records, cleared, reasons


def run(nse, sink, symbols: dict[str, str], quarters: int = 6, limit: int | None = None, dry_run: bool = False) -> dict:
    """Maintenance pass: for each company (scrip -> NSE symbol) read its latest quarters' PDFs and store what they restate.
    One company's failure is a reason, not a stop; a refusal by NSE stops the pass (it propagates). ``dry_run`` writes
    nothing and lists every restated figure found in ``stats["found"]`` (with both figures and their sources), for review."""
    from .nse import SourceBlockedError
    src = pr.Sources(nse, ocr=False)
    stats = {"companies": 0, "restated": 0, "stored": 0, "reasons": {}, "found": []}
    for scrip, symbol in list(symbols.items())[:limit]:
        dossier = sink.get_dossier(scrip)
        if not dossier:
            continue
        read = copy.deepcopy(dossier)   # the PDFs take minutes: what another writer stores meanwhile is kept (review of #168)
        stats["companies"] += 1
        try:
            records, cleared, reasons = read_company(src, symbol, dossier, quarters)
        except SourceBlockedError:
            raise
        except Exception as exc:   # noqa: BLE001
            stats["reasons"][symbol] = [type(exc).__name__]
            continue
        finally:
            src.release()
        if reasons:
            stats["reasons"][symbol] = reasons
        stats["restated"] += len(records)
        if dry_run:
            stats["found"] += [{"scrip": scrip, "symbol": symbol, **r} for r in records]
            continue
        if merge(dossier, records, cleared):
            dossier["restated_checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            keep_concurrent_writes(dossier, read, sink.get_dossier(scrip))
            sink.put_dossier(scrip, dossier)
            stats["stored"] += 1
    return stats


# --- the card side ----------------------------------------------------------------------------------------------------

def apply_to_result(tagged, dossier: dict | None) -> int:
    """CARD_YOY_RESTATED: put a results file's YoY on the restated base where memory holds one for the year-ago period on the
    file's own basis, in place; the metric's ``yoy_note`` says "vs restated". A base or a figure that is not above zero is
    left as it was (no percentage can carry it), and so is a restatement from a file later than this one. Returns how many
    changes were rebased."""
    if tagged is None or getattr(tagged, "kind", None) != "RESULTS" or not tagged.period or not (dossier or {}).get(KEY):
        return 0
    basis = tagged.basis
    stored = {(r["metric"], r["period"]): r for r in dossier[KEY] if r.get("basis") == basis and r.get("unit") == "INR_CR"}
    changed = 0
    for m in tagged.metrics:
        r = stored.get((m.metric, prior_year_period(m.period) or ""))
        if r is None or m.value is None or m.yoy_pct is None or m.unit != "INR_CR" or _later(r["restated_in"], m.period):
            continue
        if r["restated"] <= 0 or m.value <= 0:
            continue
        m.yoy_pct = round((m.value / r["restated"] - 1) * 100, 1)
        m.yoy_note = NOTE
        changed += 1
    return changed
