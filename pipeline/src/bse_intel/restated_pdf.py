"""F202 (TODO 104): a restated comparative kept beside the original, read from the later filing's PDF text layer.

NSE's XBRL carries only the current period, so a company that restates an earlier quarter in a later results file shows the
restated figure only in that PDF's comparative columns (360ONE's consolidated Q3FY24 revenue is 647.68 in its own file and
629.79 in the next one). Memory keeps both: the history (``financial_metrics``) keeps the original from the period's own
file, and the dossier's ``restated_figures`` list holds the restated one with its source. Nothing here uses OCR or an AI call:
the columns are read with ``pdf_referee.read_document(ocr=False)`` and ``figure_for``, which proves the column and the basis
from the page's own header, and a figure it cannot prove is not stored.

CARD_YOY_RESTATED (settings) makes a card's YoY use the restated base, saying "vs restated"; the history never changes.

31 Oct 2026 (owner: "growth must use the year-ago figure as the company's later filing restates it, as Screener does"): the
statements (Results page, stock page) read the stored restated figure too (``restated_base``, ``restated_cells``). A restatement
that moves a figure beyond ``BAND`` (a demerger: VEDL's Q2FY26 revenue 39,868 as filed, 16,736 restated; HINDUNILVR's 16,241 and
15,919) is stored only when it equals the figure Screener's stored page shows for that quarter on that basis (``screener_matches``:
within 1 Cr or 0.05%): two sources agreeing, and Screener's own mistakes are not copied, because a PDF figure that differs is not
stored. Three things the reader meets on such PDFs are handled here, each proved from the filing itself: a revenue that is the sum of
sub-lines (``pdf_referee.derive_revenue``; a wider rounding slack, ``DERIVED_SLACK``), a unit a garbled OCR layer lost (taken from
the filing's own XBRL figure for the current quarter, ``prepare_rows``) and thousands separators an OCR layer printed as dots
(VEDL: 16.736 for 16,736; kept only when Screener confirms the figure)."""
from __future__ import annotations

import copy
import logging
import math
import re
from datetime import datetime, timezone

from dataclasses import replace

from . import pdf_referee as pr
from .backup import BackupError, RunBackup
from .dossier import keep_concurrent_writes
from .periods import prior_quarter_period, prior_year_period
from .settings import pdf_reader_options

log = logging.getLogger("bse_intel.restated_pdf")

METRICS = ("revenue", "pat")        # the rows the PDF reader tells apart (EPS is left out: share counts change it)
KEY = "restated_figures"
NOTE = "vs restated"


def decimals_of(value: float) -> int:
    """The decimals a printed crore figure shows (the readers return it as a float): 647.68 is 2, 1259.0 is 0."""
    text = f"{value:.4f}".rstrip("0")
    return max(0, len(text.partition(".")[2]))


DERIVED_SLACK = 2.5      # a revenue summed from rounded sub-lines is off by up to half a unit each (three lines and the total: 2.5)


def differs(original: float, printed: float, slack: float = 0.5) -> bool:
    """Whether the printed comparative differs from the original beyond ``slack`` units of the decimals printed (half a unit by
    default, of the coarser of the two figures' decimals, so 647.68 against 647.7 is rounding, 647.68 against 629.79 is not)."""
    half = slack * 10 ** -min(decimals_of(original), decimals_of(printed))
    return abs(printed - original) > half + 1e-9


BAND = 0.25     # F212: a restatement moves a figure by this share of the original at most (see TRACKER F212)


def _digits(value: float) -> int:
    return len(str(int(abs(value)))) if abs(value) >= 1 else 0


def _power_of_ten(ratio: float) -> bool:
    """Whether ``ratio`` is 10^k for a k other than 0 (within 2% in the exponent: 3250.73 to 3.25 and 4018.96 to 4.018 both
    count, the second lost precision as well)."""
    if ratio <= 0:
        return False
    k = math.log10(ratio)
    return round(k) != 0 and abs(k - round(k)) < 0.01


def _lost_leading_digit(original: float, restated: float) -> bool:
    """1305.01 read as 305.01: the printed original less its first digit."""
    a, b = f"{abs(original):.2f}".rstrip("0").rstrip("."), f"{abs(restated):.2f}".rstrip("0").rstrip(".")
    return len(a) > 2 and b != a and b.lstrip("0") == a[1:].lstrip("0") and abs(original) > abs(restated)


def unreadable(value: float, siblings: list[float], metric: str = "") -> str:
    """F212: why a printed cell cannot be trusted ("" when it can): two cells joined show as a figure with more integer digits
    than any other figure of its row (19438.39 glued to a neighbour is 1943839.0), or, for revenue, as a minus no revenue carries
    (the bracket of the next cell: (14 and 1475.75 read as -141475.75)."""
    if metric == "revenue" and value < 0:
        return "joined cells: a negative revenue"
    others = [abs(s) for s in siblings]
    if others and _digits(value) > max(_digits(o) for o in others):
        return "joined cells: more digits than any figure of its row"
    return ""


def plausible(original: float, restated: float) -> str:
    """F212: why a restated comparative is a reading error and not a restatement ("" when it can be one). A restatement moves
    a figure by a little; a ratio that is a power of ten is a unit slip (the page unit is already applied by ``figure_for``,
    so what is left is a lost thousands separator or another unit in the cell), a sign flip is not a restatement, a first digit
    lost is a misread, and beyond ``BAND`` of the original it is held, not stored."""
    if original == 0:
        return ""
    if (original < 0) != (restated < 0) and restated != 0:
        return "sign flip"
    if _power_of_ten(restated / original):
        return "unit slip (ratio is a power of ten)"
    if _lost_leading_digit(original, restated):
        return "a leading digit lost"
    if abs(restated - original) > BAND * abs(original):
        return f"moves more than {BAND:.0%} of the original"
    return ""


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


SCREENER_ABS, SCREENER_REL = 1.0, 0.0005     # a restated figure equals Screener's within 1 Cr or 0.05% (owner, 31 Oct 2026)
DOT = " [thousands dot]"


def screener_matches(restated: float, theirs: float | None) -> bool:
    """Whether Screener's stored figure for the quarter is the restated one (owner, 31 Oct 2026: a restatement beyond the band is
    accepted only when two sources agree)."""
    return theirs is not None and abs(restated - theirs) <= max(SCREENER_ABS, SCREENER_REL * abs(restated))


class ScreenerStore:
    """The company's stored Screener quarterly page (raw/screener/<day>/<SYMBOL>_<c|s>.html.gz, ``screener_download``), the same
    store ``screener_crosscheck`` and ``screener-rows`` read: ``figure`` is Sales (revenue) or Net Profit (pat) of a quarter on a
    basis, in crore as printed, or None when no page is stored, the page has no such quarter or it is not on that basis. Reads R2 only."""

    def __init__(self, sink):
        self.sink = sink
        self._keys: dict[str, dict[str, str]] | None = None
        self._quarters: dict[tuple[str, str], dict] = {}

    def quarters(self, symbol: str, basis: str) -> dict:
        if (symbol, basis) not in self._quarters:
            from . import screener_crosscheck as sc
            from . import screener_download as sd
            from .screener_fill import parse_page
            if self._keys is None:
                self._keys = sc.stored_pages(self.sink)[0]
            quarters: dict = {}
            key = (self._keys.get(symbol) or {}).get(basis)
            try:
                blob = self.sink.get_object(key) if key else None
                page = parse_page(sd.unpack(blob)) if blob else None
            except Exception:   # noqa: BLE001 - a damaged page is no confirmation
                page = None
            if page and page.get("basis") == basis:
                quarters = page.get("quarters") or {}
            self._quarters[(symbol, basis)] = quarters
        return self._quarters[(symbol, basis)]

    def figure(self, symbol: str, basis: str, metric: str, period: str) -> float | None:
        value = (self.quarters(symbol, basis).get(period) or {}).get(metric)
        return float(value) if isinstance(value, (int, float)) else None


def prepare_rows(rows: list, period: str, basis: str, entries: dict) -> list:
    """The rows of a filing's PDF with two reading faults repaired, each proved by the filing's own current-quarter figure (never
    by the comparative being tested). On a basis row whose columns are proven and whose current-quarter cell is known to memory
    from the filing's XBRL (``entries``: (metric, period) -> memory entry):

    - thousands printed as dots (OCR layer of VEDL's statement: "26,356  24.205  16.736  50,561" for 24,205 and 16,736): in a row
      whose integer cells all have four digits or more and whose other cells all have exactly three decimals, those are thousands.
      The label gets ``DOT``, so the figure is stored only when Screener confirms it (``find``);
    - a unit the layer lost ("(f in Crnre" for "(₹ in Crore"): the row's current-quarter cell over memory's figure is one of the
      units a statement is written in (crore, lakh, million, thousand, billion), exactly one within 0.05%."""
    target = pr.target_column(period)
    out = []
    for r in rows:
        if r.metric not in METRICS or r.basis != basis or r.columns is None or r.aligned is not None or target is None \
                or len(r.figures) != len(r.columns) or [c for c in r.columns if c == target] != [target]:
            out.append(r)
            continue
        index = r.columns.index(target)
        figures, label = list(r.figures), r.label
        if r.odd:
            thousands = [k for k in range(len(figures)) if k not in r.odd and decimals_of(figures[k]) >= 2 and abs(figures[k]) < 1000 and abs(figures[k] * 1000 - round(figures[k] * 1000)) < 1e-6]
            if thousands and all(abs(figures[k]) >= 1000 and float(figures[k]).is_integer() for k in r.odd) \
                    and len(thousands) + len(r.odd) == len(figures):
                figures = [f * 1000 if k in thousands else f for k, f in enumerate(figures)]
                label = r.label[:60 - len(DOT)] + DOT
        row = replace(r, figures=figures, label=label, odd=None if figures != r.figures else r.odd)
        entry = entries.get((r.metric, period))
        known = original_of(entry, basis)
        if row.unit is None and known is not None and known[0] > 0:
            units = {u for u in set(pr._PER_CRORE.values()) if abs(figures[index] / u - known[0]) <= max(0.5, 0.0005 * known[0])}
            if len(units) == 1:
                row = replace(row, unit=float(units.pop()))
        out.append(row)
    return out


def comparatives(rows: list, period: str, basis: str) -> list[dict]:
    """The year-ago and previous-quarter columns a results filing of ``period`` prints, one figure per metric where the
    reader proves the column and the basis: [{metric, period, basis, value}]."""
    out = []
    for target in (prior_year_period(period), prior_quarter_period(period)):
        if not target:
            continue
        for metric in METRICS:
            got = pr.figure_for(rows, target, metric, basis)
            found = pr.revenue_only(got["values"]) if metric == "revenue" else got["values"]
            values = {round(v, 4) for v, _label, _page in found}
            if len(values) == 1:        # none, or two readings that disagree: nothing stored
                value = values.pop()
                sib = next((s for (v, _l, _p), s in zip(got["values"], got.get("siblings") or [])
                            if round(v, 4) == value), [])
                labels = [label for v, label, _p in found if round(v, 4) == value]
                out.append({"metric": metric, "period": target, "basis": basis, "value": value,
                            "joined": unreadable(value, sib, metric),
                            "derived": all(pr.DERIVED_LABEL in label for label in labels),
                            "dotted": any(DOT.strip() in label for label in labels)})
    return out


def find(dossier: dict, rows: list, period: str, basis: str, filing_id: str = "", url: str = "",
         rejected: list | None = None, screener=None) -> list[dict]:
    """Restated figures: the printed comparatives of the filing for ``period`` that differ from the period's original in
    memory. Each record keeps both figures and where each came from. A difference that is a reading error (F212: ``unreadable``,
    ``plausible``) is not stored; it is added to ``rejected`` with its reason when a list is given.

    ``screener(metric, period)`` is Screener's stored figure for a quarter on ``basis`` (``ScreenerStore.figure``) or None. A
    restatement beyond ``BAND`` is stored when it equals that figure (a demerger moves revenue by 40%: both sources agree), and a
    figure read through thousands printed as dots only then; the record says ``confirmed: screener``. Other reading errors (a
    unit slip, a sign flip, a lost digit, joined cells) are never overridden, whatever Screener shows."""
    entries = {(e["metric"], e["period"]): e for e in dossier.get("financial_metrics", [])}
    found = []
    for c in comparatives(prepare_rows(rows, period, basis, entries), period, basis):
        original = original_of(entries.get((c["metric"], c["period"])), basis)
        if original is None or not differs(original[0], c["value"], DERIVED_SLACK if c.get("derived") else 0.5):
            continue
        why = c.get("joined") or plausible(original[0], c["value"])
        theirs = screener(c["metric"], c["period"]) if screener is not None and (why.startswith("moves more than") or c.get("dotted")) else None
        confirmed = screener_matches(c["value"], theirs)
        if why.startswith("moves more than") and confirmed:
            why = ""
        if not why and c.get("dotted") and not confirmed:
            why = "thousands printed as dots, not confirmed by Screener"
        if why:
            if rejected is not None:
                rejected.append({"metric": c["metric"], "period": c["period"], "original": original[0],
                                 "restated": c["value"], "reason": why, **({"screener": theirs} if theirs is not None else {})})
            continue
        found.append({"metric": c["metric"], "period": c["period"], "basis": basis, "unit": "INR_CR",
                      "original": original[0], "original_news_id": original[1],
                      "restated": c["value"], "restated_in": period, "restated_news_id": filing_id, "restated_url": url,
                      "read": "pdf_text", **({"confirmed": "screener", "screener": theirs} if confirmed else {}),
                      **({"derived": True} if c.get("derived") else {})})
    return found


def _unchanged(dossier: dict, comparative: dict, basis: str) -> bool:
    """Whether a printed comparative was checked against memory's original and found the same: only such a figure
    clears an older restatement (a comparative memory holds no original for proves nothing; review of #168)."""
    entry = next((e for e in dossier.get("financial_metrics", [])
                  if (e.get("metric"), e.get("period")) == (comparative["metric"], comparative["period"])), None)
    original = original_of(entry, basis)
    return original is not None and not differs(original[0], comparative["value"], DERIVED_SLACK if comparative.get("derived") else 0.5)


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


def read_company(src, symbol: str, dossier: dict, quarters: int = 6, rejected: list | None = None,
                 screener: ScreenerStore | None = None) -> tuple[list[dict], list[tuple], list[str]]:
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
        misses = []
        for f in listed[:pr.MAX_CANDIDATES]:
            rows, why = src.rows(f.pdf_url)
            if not rows:         # a file with no results row (a notice, an auditor's letter) is not the results: try the next
                misses.append(why or "no results row found")
                continue
            if not any(r.columns and pr.target_column(period) in r.columns for r in rows):
                misses.append(f"no proven column for {period} (the file is another quarter's)")   # the next quarter's results are in the window too
                continue
            theirs = (lambda metric, p, _b=basis: screener.figure(symbol, _b, metric, p)) if screener is not None else None
            mine = find(dossier, rows, period, basis, f.news_id, f.pdf_url, rejected, theirs)
            records += mine
            seen = {(r["metric"], r["period"]) for r in mine}
            entries = {(e["metric"], e["period"]): e for e in dossier.get("financial_metrics", [])}
            cleared += [(c["metric"], c["period"], basis, period) for c in comparatives(prepare_rows(rows, period, basis, entries), period, basis)
                        if (c["metric"], c["period"]) not in seen and _unchanged(dossier, c, basis)]
            misses = []
            break
        if misses:       # the reasons of the files tried, only when none of them was the results (31 Oct 2026 trial)
            reasons.append(f"{period}: {'; '.join(dict.fromkeys(misses))}")
    return records, cleared, reasons


def run(nse, sink, symbols: dict[str, str], quarters: int = 6, limit: int | None = None, dry_run: bool = False,
        resume_after: str | None = None) -> dict:
    """Maintenance pass: for each company (scrip -> NSE symbol) read its latest quarters' PDFs and store what they restate.
    One company's failure is a reason, not a stop; a refusal by NSE stops the pass (it propagates). ``dry_run`` writes
    nothing and lists every restated figure found in ``stats["found"]`` (with both figures and their sources), for review.
    The run's file cap (F213) ends the pass: ``stats["capped"]``, the company it stopped in is ``stopped_at`` (not stored, not
    counted) and ``last_done`` is the last company finished, where the next run resumes (``resume_after``)."""
    from .nse import FileCapReached, SourceBlockedError
    src = pr.Sources(nse, ocr=False)
    backup = None if dry_run else RunBackup(sink, "restated-pdf")   # each dossier is saved to R2 backup/ before its write
    screener = ScreenerStore(sink)
    stats = {"companies": 0, "restated": 0, "stored": 0, "reasons": {}, "found": [], "rejected": [], "capped": False,
             "stopped_at": None, "last_done": None}
    items = list(symbols.items())
    if resume_after:
        items = [(k, v) for k, v in items if k > resume_after]
    for scrip, symbol in items[:limit]:
        dossier = sink.get_dossier(scrip)
        if not dossier:
            continue
        read = copy.deepcopy(dossier)   # the PDFs take minutes: what another writer stores meanwhile is kept (review of #168)
        stats["companies"] += 1
        refused: list[dict] = []
        try:
            with pdf_reader_options():     # the reader as the bench scored it (wrapped header dates, two-digit years, row fixes)
                records, cleared, reasons = read_company(src, symbol, dossier, quarters, refused, screener)
        except FileCapReached:
            stats["companies"] -= 1
            stats["capped"], stats["stopped_at"] = True, scrip
            break
        except SourceBlockedError:
            raise
        except Exception as exc:   # noqa: BLE001
            stats["reasons"][symbol] = [type(exc).__name__]
            stats["last_done"] = scrip
            continue
        finally:
            src.release()
        if reasons:
            stats["reasons"][symbol] = reasons
        stats["restated"] += len(records)
        stats["rejected"] += [{"scrip": scrip, "symbol": symbol, **r} for r in refused]    # reading errors (F212), never stored
        if dry_run:
            stats["found"] += [{"scrip": scrip, "symbol": symbol, **r} for r in records]
            stats["last_done"] = scrip
            continue
        if merge(dossier, records, cleared):
            dossier["restated_checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            keep_concurrent_writes(dossier, read, sink.get_dossier(scrip))
            try:
                backup.dossier(scrip, dossier)
            except BackupError as exc:   # nothing more is written; the stats so far are returned, this company is not done
                stats["error"] = f"{type(exc).__name__}: {exc}"[:300]
                log.error("restated-pdf stopped: %s", exc)
                break
            sink.put_dossier(scrip, dossier)
            stats["stored"] += 1
        stats["last_done"] = scrip
    return stats


# --- the card side ----------------------------------------------------------------------------------------------------

def restated_base(dossier: dict | None, metric: str, period: str, basis: str | None, as_of: str | None = None,
                  positive: bool = True) -> dict | None:
    """The stored restated record of ``metric`` for ``period`` on ``basis``, to use as that period's figure in a growth worked out
    for the quarter ``as_of``: from the filing of ``as_of`` or an earlier one (a restatement a later filing makes is not what
    that quarter's growth was worked against), in crore, and above zero unless ``positive`` is False (a percentage cannot carry a
    base that is not; the statements name a change across a loss). None when there is none."""
    for r in (dossier or {}).get(KEY) or []:
        if (r.get("metric"), r.get("period"), r.get("basis")) != (metric, period, basis) or r.get("unit") != "INR_CR":
            continue
        if not isinstance(r.get("restated"), (int, float)) or (positive and r["restated"] <= 0):
            return None
        if as_of and _later(r.get("restated_in") or "", as_of):
            return None
        return r
    return None


def rebase_entry(dossier: dict | None, entry: dict | None, rows: dict[str, str], period: str, basis: str | None,
                 as_of: str | None = None, positive: bool = True) -> tuple[dict | None, list[str]]:
    """A statements entry (``dossier["statements"]``, quarters table) of ``period`` with the rows named in ``rows`` (row name ->
    metric, e.g. {"Sales": "revenue", "Net Profit": "pat"}) put on the restated figure, with the names of the rows changed. A row
    is changed only when its figure is the original the restatement was made against (within half a crore or 0.05%): the same
    quantity, so the restated figure replaces it and nothing else (a profit to owners is not the total profit the PDF prints). The
    entry gets ``restated`` {row: {"original", "restated", "in"}} for the page's marker. The same entry when nothing changes."""
    if not entry or not (dossier or {}).get(KEY):
        return entry, []
    figures, changed, mark = dict(entry.get("rows") or {}), [], {}
    for row, metric in rows.items():
        r = restated_base(dossier, metric, period, basis, as_of, positive)
        have = figures.get(row)
        if r is None or have is None or abs(have - r["original"]) > max(0.5, 0.0005 * abs(r["original"])):
            continue
        figures[row] = r["restated"]
        mark[row] = {"original": have, "restated": r["restated"], "in": r.get("restated_in")}
        changed.append(row)
    return ({**entry, "rows": figures, "restated": mark}, changed) if changed else (entry, [])


def apply_to_result(tagged, dossier: dict | None) -> int:
    """CARD_YOY_RESTATED: put a results file's YoY on the restated base where memory holds one for the year-ago period on the
    file's own basis, in place; the metric's ``yoy_note`` says "vs restated". A base or a figure that is not above zero is
    left as it was (no percentage can carry it), and so is a restatement from a file later than this one. Returns how many
    changes were rebased."""
    if tagged is None or getattr(tagged, "kind", None) != "RESULTS" or not tagged.period or not (dossier or {}).get(KEY):
        return 0
    basis = tagged.basis
    changed = 0
    for m in tagged.metrics:
        r = restated_base(dossier, m.metric, prior_year_period(m.period) or "", basis, m.period)
        if r is None or m.value is None or m.yoy_pct is None or m.unit != "INR_CR" or m.value <= 0:
            continue
        m.yoy_pct = round((m.value / r["restated"] - 1) * 100, 1)
        m.yoy_note = NOTE
        changed += 1
    return changed
