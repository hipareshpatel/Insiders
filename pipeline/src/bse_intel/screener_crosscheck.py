"""Read-only cross-check of memory's exchange-file figures against the stored screener.in pages. No request, no write, no AI.
TRACKER F163, TODO 50.

For every company, each quarter (and each financial year of screener's annual profit and loss section) is compared on
memory's basis with the exchange file's figure only (``metrics._figures``: ``xbrl:`` sources):

- revenue: screener's Sales against our ``revenue`` (a lender: its Revenue against our ``revenue``, revenue from operations,
  else ``interest_earned``: a bank's file has no revenue line. Interest earned first compared an NBFC's interest income with
  screener's revenue from operations: Aadhar Housing Q2FY25 672.56 against 764.27, RattanIndia 1.91 against 1,921.49, both
  in memory; screener-referee run 40288810286, checked on the 25 Oct backup),
- pat: Net Profit against our ``pat`` (a lender's profit is a different definition, so a difference is not a mismatch),
- eps: EPS in Rs against our ``eps`` (or ``basic_eps``), where both have it.
- the six other lines of screener's quarterly table (27 Oct 2026, quarters only; ``six_pairs``): Operating Profit against
  our ``ebitda``, Other Income against ``other_income``, Interest against ``finance_cost``, Depreciation against
  ``depreciation``, Profit before tax against ``pbt``, Tax % against our tax over ``pbt`` (``tax_expense``, else
  ``current_tax`` + ``deferred_tax``). Screener prints whole crore, so a money line is a match within ₹0.5 Cr (or 0.5%) and
  Tax % within one percentage point. A lender page (Revenue / Financing Profit layout) is not read for Operating Profit and
  Interest: its table is a different one. A gap is named only when one of screener's own rules (docs/bench/screener-rules.md
  rows 1 and 4) closes it and the gap is more than twice the tolerance: ``exceptional_in_other_income`` (screener's Other
  Income holds the exceptional items; an item of at least ₹5 Cr and a quarter of our other income); anything else is ``mismatch``. These lines are counted apart (``six_pairs``, ``six_by_class``), never in ``pairs`` or ``by_class``;
  the XBRL, explain and PDF referees read revenue, profit and EPS only and pass these rows through unread.

Each pair gets one class:

- ``match``: within ₹1 Cr or 0.5% (screener rounds to whole crore); EPS within 0.06 or 0.5%;
- ``wrong_quarter``: ours differs from screener's column for the period but equals (exactly, within rounding; at least
  ₹5 Cr) screener's figure for another quarter or year of the same line, any column, a year-ago comparative stored as
  current included: a figure saved under the wrong period in memory (or a mislabelled column on screener). Both labels are
  in the note, and the chance risk when several columns match. Memory's own period checks, no screener needed, are
  ``memory_period_suspect`` rows: the same value stored for two quarters (copy-forward), a source filed before its quarter
  ended, a quarter whose source file is labelled for another quarter (the file's own start and end dates are not stored);
- ``scale``: the ratio is 10, 100 or 1000 (or the inverse) within 3%: a unit slip;
- ``naming``: screener equals another official line of the same filing that memory holds (screener's Sales is our
  ``total_income``, its profit our ``pat_owners``, ``pat_continuing`` or ``pat_group``, revenue net of excise, ...): the
  line is recorded in the note; tried before anything is called a lender definition, a steady difference or a mismatch;
- ``lender_definition``: a bank, NBFC or insurer's profit or income differs (screener's definition is not the exchange's);
- ``steady_line_difference``: revenue only, four or more unmatched quarters of a company differ by a near-constant amount or
  ratio: a definition difference (an excise line included or left out), not a wrong figure;
- ``mismatch``: anything else.

Quarters one side has and the other lacks are counted as gaps (``screener_only``, ``memory_only``), memory's only inside
the span of quarters screener shows. Referee (owner, 26 Oct 2026: the official filing decides who is wrong): each ``wrong_quarter``, ``scale`` and ``mismatch`` pair
is looked up in the quarter's results filing text (the R2 text cache, ``text/<news_id>.json.gz``; nothing is downloaded) and
both values are searched for at the printed unit (crore, lakh, million): verdict ``ours_matches_official``,
``screener_matches_official``, ``both_match``, ``neither`` or ``no_official_text``. The output is a summary (counts by class and sector, worst companies), a CSV of every
non-match pair and a short markdown report; the job uploads them as an artifact and commits nothing.
"""

from __future__ import annotations

import csv
import io
import json
import re
import statistics
from concurrent.futures import ThreadPoolExecutor

from . import line_map
from .dossier import _norm
from .memory_gaps import main_basis, quarter_end
from .metrics import CONSOLIDATED, STANDALONE, _figures, _value_source, is_lender
from .periods import quarter_index
from .screener_referee import referee, text_of
from .screener_download import PREFIX, unpack
from .screener_fill import parse_full

MONEY_ABS, MONEY_REL = 1.0, 0.005
EPS_ABS, EPS_REL = 0.06, 0.005
SCALE_FACTORS = (10.0, 100.0, 1000.0)
SCALE_TOLERANCE = 0.03
MIN_SHIFT_VALUE = 5.0     # a wrong-quarter match needs a figure this big (₹ Cr): small ones match by chance
SHIFT_ABS, SHIFT_REL = 1.0, 0.001
REFEREED = ("wrong_quarter", "scale", "mismatch")
SUSPECT_KINDS = ("copy_forward", "filed_before_quarter_end", "source_label_differs")
STEADY_MIN = 4
STEADY_RATIO_SPREAD = 0.02       # relative spread of theirs/ours
STEADY_DIFF_SPREAD = (2.0, 0.05)  # max spread of the difference: ₹2 Cr or 5% of its median

VIEW = "matches_screener_view:"   # a class prefix: screener's own treatment of our figure closes the gap (never stored)
CLASSES = ("match", "wrong_quarter", "scale", "naming", "lender_definition", "steady_line_difference",
           VIEW + "excise", VIEW + "share_adjust", "mismatch")
# the six other lines: our metric names (Tax % is a ratio of two of ours)
SIX_METRICS = ("ebitda", "other_income", "finance_cost", "depreciation", "pbt", "tax_pct")
SIX_LENDER_SKIP = ("ebitda", "finance_cost")      # a lender page's Operating Profit and Interest are not these lines
SIX_ABS, SIX_REL = 0.5, 0.005                      # screener prints whole crore: half a crore, or 0.5%
TAX_PCT_ABS = 1.0                                  # screener prints whole percent
SIX_EXPLAINED = (VIEW + "exceptional_in_other_income",)
SIX_CLASSES = ("match", *SIX_EXPLAINED, "mismatch")
GAP_CLASSES = ("screener_only", "memory_only")
WORKERS = 8

CSV_HEADER = ("scrip,symbol,sector,basis,period,metric,class,memory_value,screener_value,memory_source_id,"
              "memory_filed,note").split(",")

# our metric names for each compared line; a lender's revenue line is its revenue from operations, a bank's interest earned
_OURS = {k: line_map.crosscheck_ours(k) for k in ("revenue", "pat", "eps")}
_LENDER_OURS = {k: line_map.crosscheck_ours(k, lender=True) for k in ("revenue", "pat", "eps")}


_SCREENER_LINE = {"revenue": "Sales", "pat": "Net Profit", "eps": "EPS"}


# --- one pair -----------------------------------------------------------------------------------------------------

def _close(ours: float, theirs: float, metric: str) -> bool:
    absolute, relative = (EPS_ABS, EPS_REL) if metric == "eps" else (MONEY_ABS, MONEY_REL)
    return abs(ours - theirs) <= max(absolute, relative * abs(ours))


def _apart(ours: float, theirs: float, metric: str) -> bool:
    """More than twice the match tolerance: a rule credited with a gap this wide did not match by chance."""
    absolute, relative = (EPS_ABS, EPS_REL) if metric == "eps" else (MONEY_ABS, MONEY_REL)
    return abs(ours - theirs) > 2 * max(absolute, relative * abs(theirs)) + 1e-9


def _is_scale(ours: float, theirs: float) -> bool:
    if not ours or not theirs or (ours > 0) != (theirs > 0):
        return False
    ratio = abs(theirs / ours)
    return any(abs(ratio - f) <= SCALE_TOLERANCE * f or abs(ratio - 1 / f) <= SCALE_TOLERANCE / f for f in SCALE_FACTORS)


def _neighbours(period: str) -> list[str]:
    """The quarter before and after, or the year before and after."""
    if m := re.fullmatch(r"FY(\d{2})", period):
        y = int(m[1])
        return [f"FY{y - 1:02d}", f"FY{y + 1:02d}"]
    idx = quarter_index(period)
    if idx is None:
        return []
    out = []
    for i in (idx - 1, idx + 1):
        year, q = divmod(i - 1, 4)
        out.append(f"Q{q + 1}FY{year:02d}")
    return out


def classify(ours: float, theirs: float, metric: str, shifted_to: str | None, lender: bool,
             named: str | None = None) -> str:
    """One pair's class, before the company-level steady-line rule: ``shifted_to`` names a neighbouring column whose
    value ours equals; ``named`` an alternative official line of ours that screener's value equals."""
    if _close(ours, theirs, metric):
        return "match"
    if shifted_to:
        return "wrong_quarter"
    if metric != "eps" and _is_scale(ours, theirs):
        return "scale"
    if named:
        return "naming"
    if lender and metric in ("revenue", "pat"):
        return "lender_definition"
    return "mismatch"


def _steady(pairs: list[dict]) -> bool:
    """Four or more unmatched revenue quarters of one company whose difference or ratio hardly moves."""
    usable = [p for p in pairs if p["memory_value"] and p["screener_value"]]
    if len(usable) < STEADY_MIN:
        return False
    ratios = [p["screener_value"] / p["memory_value"] for p in usable]
    if statistics.mean(ratios) and (max(ratios) - min(ratios)) <= STEADY_RATIO_SPREAD * abs(statistics.mean(ratios)):
        return True
    diffs = [p["memory_value"] - p["screener_value"] for p in usable]
    median = abs(statistics.median(diffs))
    return (max(diffs) - min(diffs)) <= max(STEADY_DIFF_SPREAD[0], STEADY_DIFF_SPREAD[1] * median)


# --- the screener view of our figures ----------------------------------------------------------------------------

def screener_view(dossier: dict | None, figures: dict, period: str, today: str | None = None) -> dict[str, tuple[float, str]]:
    """Our figures of one period as screener's documented rules print them: ``{metric: (value, rule)}``, only for a metric a
    rule changes. Pure: nothing is stored or shown on a card (memory keeps the company's own figures).

    - ``revenue``: revenue less excise duty (rule ``excise``; screener's Sales is net of it, rules row 1);
    - ``other_income``: other income plus the exceptional items (``exceptional_in_other_income``, rules row 4);
    - ``eps``: EPS divided by the factor of a share split or bonus after the period (``share_adjust``, rules row 7);
    - ``exceptional_after_tax``: the exceptional items less their share of the tax, tax x exceptional / pbt (screener's
      support article 42), the whole item when that tax exceeds it. Shown for the record: no compared line reads it yet.
    """
    def v(name: str) -> float | None:
        return _value(figures, name, period)

    out: dict[str, tuple[float, str]] = {}
    excise, exceptional = v("excise_duty"), v("exceptional_items")
    if excise:
        if v("revenue") is not None:   # not Operating Profit: ours (PBT + interest + depreciation - other income) never held it
            out["revenue"] = (v("revenue") - excise, "excise")
    # a small exceptional item beside a few crore of gap would "explain" it by chance (blind review, 27 Oct 2026: other income
    # 10 against 7.2 with exceptional -3): the item must be at least 5 Cr and a quarter of our other income
    if exceptional and v("other_income") is not None and abs(exceptional) >= max(5.0, 0.25 * abs(v("other_income"))):
        out["other_income"] = (v("other_income") + exceptional, "exceptional_in_other_income")
    if exceptional:
        pbt, tax = v("pbt"), v("tax_expense")
        if tax is None and v("current_tax") is not None and v("deferred_tax") is not None:
            tax = v("current_tax") + v("deferred_tax")
        if pbt and tax is not None:
            on_exceptional = tax * exceptional / pbt
            out["exceptional_after_tax"] = (exceptional if abs(on_exceptional) > abs(exceptional)
                                            else exceptional - on_exceptional, "exceptional_after_tax")
    if v("eps") is not None and dossier:
        from .screener_explain import share_factor   # screener_explain imports this module
        from .timeutil import today_ist
        factor, actions = share_factor(dossier, period, today or today_ist().isoformat())
        if actions and abs(factor - 1) > 1e-9:
            out["eps"] = (v("eps") / factor, "share_adjust")
    return out


# --- the six other lines -----------------------------------------------------------------------------------------

def _six_close(ours: float, theirs: float, metric: str) -> bool:
    if metric == "tax_pct":
        return abs(ours - theirs) <= TAX_PCT_ABS + 1e-9
    return abs(ours - theirs) <= max(SIX_ABS + 1e-9, SIX_REL * abs(ours))


def _six_apart(ours: float, theirs: float, metric: str) -> bool:
    """An explanation counts only for a gap of more than twice the tolerance (screener_explain.apart's rule): within it, a
    second line can match by chance."""
    tol = TAX_PCT_ABS if metric == "tax_pct" else max(SIX_ABS, SIX_REL * abs(theirs))
    return abs(ours - theirs) > 2 * tol + 1e-9


def classify_six(metric: str, ours: float, theirs: float, figures: dict, period: str,
                 view: dict | None = None) -> tuple[str, str]:
    """(class, note) of one pair of the six lines: a match, a gap one of screener's own rules closes, or a mismatch."""
    if _six_close(ours, theirs, metric):
        return "match", ""
    if not _six_apart(ours, theirs, metric):
        return "mismatch", ""
    view = view or {}
    if metric in view and _six_close(view[metric][0], theirs, metric):
        rule = view[metric][1]
        return VIEW + rule, f"screener's view of our figure: {ours:g} -> {view[metric][0]:g} ({rule})"
    return "mismatch", ""


def _our_tax_pct(figures: dict, period: str) -> tuple[float, dict] | None:
    """Our tax over our profit before tax, in percent: the tax total, else current plus deferred tax (both must be there)."""
    pbt = figures.get(("pbt", period))
    if not pbt or not pbt.get("value"):
        return None
    tax = _value(figures, "tax_expense", period)
    if tax is None:
        current, deferred = _value(figures, "current_tax", period), _value(figures, "deferred_tax", period)
        if current is None or deferred is None:
            return None
        tax = current + deferred
    return tax / pbt["value"] * 100, pbt


def six_pairs(figures: dict, quarters: dict[str, dict], lender: bool, lender_layout: bool,
              dossier: dict | None = None) -> list[dict]:
    """The pairs of the six other lines, quarters only."""
    out: list[dict] = []
    for period, row in quarters.items():
        for metric in SIX_METRICS:
            theirs = row.get(metric)
            if theirs is None or (metric in SIX_LENDER_SKIP and (lender or lender_layout)):
                continue
            if metric == "tax_pct":
                got = _our_tax_pct(figures, period)
                if got is None:
                    continue
                ours, entry = got
            else:
                entry = figures.get((_norm(metric), period))
                if not entry or entry.get("value") is None:
                    continue
                ours = entry["value"]
            cls, note = classify_six(metric, ours, theirs, figures, period, screener_view(dossier, figures, period))
            out.append({"period": period, "metric": metric, "memory_value": ours, "screener_value": theirs, "class": cls,
                        "shifted": [], "memory_source_id": _value_source(entry), "memory_filed": entry.get("as_of") or "",
                        "note": note})
    return out


# --- one company --------------------------------------------------------------------------------------------------

def _ours(figures: dict, lender: bool, metric: str, period: str) -> dict | None:
    for name in (_LENDER_OURS if lender else _OURS)[metric]:
        entry = figures.get((_norm(name), period))
        if entry and entry.get("value") is not None:
            # a lender template's interest earned of 0 beside no revenue is the template's filler (ICICI Prudential AMC's
            # NBFC-template file tags InterestEarned 0, its revenue is revenue from operations): "not found", never a 0
            # revenue (Tijori referee, 26 Oct 2026, F196)
            if lender and metric == "revenue" and name == "interest_earned" and not entry["value"]:
                continue
            return entry
    return None


def _value(figures: dict, name: str, period: str) -> float | None:
    entry = figures.get((_norm(name), period))
    return entry["value"] if entry and entry.get("value") is not None else None


def alternatives(figures: dict, metric: str, period: str, lender: bool) -> list[tuple[str, float]]:
    """The other official lines memory holds for this company-quarter that screener's figure may be: (label, value)."""
    def v(name: str) -> float | None:
        return _value(figures, name, period)

    out: list[tuple[str, float | None]] = []
    if metric == "revenue":
        out += [("total_income", v("total_income"))]
        if lender:
            out.append(("interest_earned", v("interest_earned")))
        if v("revenue") is not None and v("excise_duty") is not None:
            out.append(("revenue less excise_duty", v("revenue") - v("excise_duty")))
        if v("revenue") is not None and v("other_income") is not None:
            out.append(("revenue + other_income", v("revenue") + v("other_income")))
        if v("interest_earned") is not None and v("other_income") is not None:
            out.append(("interest_earned + other_income", v("interest_earned") + v("other_income")))
    elif metric == "pat":
        out += [("pat_owners", v("pat_owners")), ("pat_continuing", v("pat_continuing")), ("pat_group", v("pat_group"))]
        if v("pat_continuing") is not None and v("pat_discontinued") is not None:
            out.append(("pat_continuing + pat_discontinued", v("pat_continuing") + v("pat_discontinued")))
        if v("pat") is not None and v("pat_minority") is not None:
            out.append(("pat less pat_minority", v("pat") - v("pat_minority")))
    elif metric == "eps":
        out += [("basic_eps", v("basic_eps")), ("diluted_eps", v("diluted_eps")), ("eps", v("eps"))]
    return [(label, value) for label, value in out if value is not None]


def memory_suspects(figures: dict) -> list[dict]:
    """Quarters whose period label memory itself puts in doubt, with no screener involved (``figures`` is
    ``metrics._figures``' exchange-file figures on one basis):

    - ``copy_forward``: the same value (at least ₹5 Cr, to the paise) stored for two different quarters of a line;
    - ``filed_before_quarter_end``: a source filed before the quarter it carries ended (impossible);
    - ``source_label_differs``: the figure of a quarter comes from a results file the seed labelled for another quarter
      (``xbrl:res:<scrip>:<period>``; the file's own start and end dates are not stored, so this is the label's check).
    """
    out: list[dict] = []
    seen: dict[tuple[str, float], list[str]] = {}
    for (metric, period), entry in sorted(figures.items(), key=lambda kv: kv[0][1]):
        if not quarter_index(period) or entry.get("value") is None or metric not in ("revenue", "pat", "interest_earned"):
            continue
        if abs(entry["value"]) >= MIN_SHIFT_VALUE:
            seen.setdefault((metric, round(entry["value"], 2)), []).append(period)

    def row(metric: str, period: str, entry: dict, kind: str, reason: str) -> dict:
        return {"period": period, "metric": metric, "kind": kind, "memory_value": entry["value"], "screener_value": None,
                "class": "memory_period_suspect", "memory_source_id": _value_source(entry),
                "memory_filed": entry.get("as_of") or "", "note": f"{kind}: {reason}"}

    for (metric, _), periods in seen.items():
        if len(periods) > 1:
            for period in periods:
                out.append(row(metric, period, figures[(metric, period)], "copy_forward",
                               "same value stored for " + ", ".join(p for p in periods if p != period)))
    for (metric, period), entry in sorted(figures.items(), key=lambda kv: kv[0][1]):
        end = quarter_end(period) if quarter_index(period) else None
        if end is None or entry.get("value") is None:
            continue
        for src in entry.get("sources") or [{"news_id": _value_source(entry), "as_of": entry.get("as_of")}]:
            news_id, filed = str(src.get("news_id") or ""), str(src.get("as_of") or "")[:10]
            if not news_id.startswith("xbrl:"):
                continue
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", filed) and filed < end.isoformat():
                out.append(row(metric, period, entry, "filed_before_quarter_end", f"filed {filed}, quarter ends {end}"))
                break
        label = re.fullmatch(r"xbrl:res(?:-sa)?:[^:]*:(Q[1-4]FY\d{2})", _value_source(entry))
        if label and label[1] != period and metric in ("revenue", "pat", "interest_earned"):
            out.append(row(metric, period, entry, "source_label_differs", f"source file is labelled {label[1]}"))
    return out


def compare_company(dossier: dict, pages: dict[str, dict], scrip: str = "", symbol: str = "") -> dict:
    """Pairs and gaps for one company. ``pages`` maps a basis to parse_full's result. Pure."""
    basis = main_basis(dossier) if dossier else None
    out = {"scrip": scrip, "symbol": symbol, "basis": basis, "sector": (dossier or {}).get("sector")
           or (dossier or {}).get("industry") or "unknown", "pairs": [], "six_pairs": [], "gaps": [], "suspects": [], "skipped": None}
    if not basis:
        out["skipped"] = "no memory basis"
        return out
    out["suspects"] = memory_suspects(_figures(dossier, basis)[0])
    page = pages.get(basis)
    if not page or page.get("basis") != basis:
        out["skipped"] = "no stored page on memory's basis"
        return out
    lender = is_lender(dossier, basis)
    figures, _ = _figures(dossier, basis)
    columns = {"quarter": page["quarters"], "year": page.get("annual") or {}}
    pairs: list[dict] = []
    for kind, table in columns.items():
        for period, theirs_row in table.items():
            for metric in ("revenue", "pat", "eps"):
                theirs = theirs_row.get(metric)
                entry = _ours(figures, lender, metric, period)
                if theirs is None or entry is None:
                    continue
                shifted = []   # every other column of the same line that ours equals
                if metric != "eps" and abs(entry["value"]) >= MIN_SHIFT_VALUE and not _close(entry["value"], theirs, metric):
                    for other, other_row in table.items():
                        other_theirs = other_row.get(metric)
                        if other != period and other_theirs is not None and not _close(other_theirs, theirs, metric) \
                                and abs(entry["value"] - other_theirs) <= max(SHIFT_ABS, SHIFT_REL * abs(entry["value"])):
                            shifted.append(other)
                shifted_to = shifted[0] if shifted else None
                named = next((label for label, alt in alternatives(figures, metric, period, lender)
                              if _close(alt, theirs, metric) and abs(alt - entry["value"]) > 1e-9), None)
                note = ""
                if shifted:
                    note = f"memory {period} = screener's {', '.join(shifted)}"
                    if len(shifted) > 1:
                        note += f" (chance risk: {len(shifted)} columns match)"
                cls = classify(entry["value"], theirs, metric, shifted_to, lender, named)
                if cls == "mismatch" and metric in ("revenue", "eps"):   # the existing "naming" (revenue less excise) keeps its place
                    got = screener_view(dossier, figures, period).get(metric)
                    if got and _close(got[0], theirs, metric) and _apart(entry["value"], theirs, metric):
                        cls, note = VIEW + got[1], f"screener's view of our figure: {entry['value']:g} -> {got[0]:g} ({got[1]})"
                if cls == "naming":
                    note = f"screener {_SCREENER_LINE[metric]} = our {named}"
                pairs.append({"period": period, "metric": metric, "memory_value": entry["value"], "screener_value": theirs,
                              "class": cls, "shifted": shifted, "memory_source_id": _value_source(entry),
                              "memory_filed": entry.get("as_of") or "", "note": note})
    unmatched = [p for p in pairs if p["metric"] == "revenue" and p["class"] == "mismatch"]
    if _steady(unmatched):
        for p in unmatched:
            p["class"] = "steady_line_difference"
            p["note"] = "near-constant difference or ratio across quarters"
    out["pairs"] = pairs
    out["six_pairs"] = six_pairs(figures, page["quarters"], lender, bool(page.get("lender_layout")), dossier)
    # gaps: a quarter of the span screener shows, one side has and the other lacks
    ours_quarters = {p for (m, p) in figures if m in ("revenue", "interest_earned", "pat") and quarter_index(p)}
    theirs_quarters = {p for p, row in page["quarters"].items() if row.get("revenue") is not None or row.get("pat") is not None}
    if theirs_quarters:
        lo, hi = min(map(quarter_index, theirs_quarters)), max(map(quarter_index, theirs_quarters))
        out["gaps"] += [{"period": p, "class": "screener_only"} for p in sorted(theirs_quarters - ours_quarters, key=quarter_index)]
        out["gaps"] += [{"period": p, "class": "memory_only"} for p in sorted(ours_quarters - theirs_quarters, key=quarter_index)
                        if lo <= quarter_index(p) <= hi]
    return out


# --- the stored pages ---------------------------------------------------------------------------------------------

def stored_pages(sink, day: str | None = None) -> tuple[dict[str, dict[str, str]], str | None]:
    """symbol -> {basis: object key}, from ``raw/screener/<day>/`` (the newest day stored when ``day`` is None; a company
    missing from that day takes its page from the newest earlier day)."""
    keys = [k for k in sink.list_objects(PREFIX) if k.endswith(".html.gz")]
    found: dict[str, dict[str, tuple[str, str]]] = {}
    for key in keys:
        m = re.fullmatch(re.escape(PREFIX) + r"(\d{4}-\d{2}-\d{2})/(.+)_([cs])\.html\.gz", key)
        if not m or (day and m[1] > day):
            continue
        basis = CONSOLIDATED if m[3] == "c" else STANDALONE
        current = found.setdefault(m[2], {}).get(basis)
        if current is None or m[1] > current[0]:
            found[m[2]][basis] = (m[1], key)
    newest = max((d for by in found.values() for d, _ in by.values()), default=None)
    return {sym: {b: k for b, (_, k) in by.items()} for sym, by in found.items()}, newest


def official_texts(sink, scrip: str, cache: dict | None = None):
    """(periods -> news ids of the company's results cards, a getter of a filing's text from the R2 text cache). The list
    comes from the query ``results_cards_company``; a Worker without it gives none, and every pair is then
    ``no_official_text``. Texts are read from the cache only: nothing is downloaded."""
    from .pipeline import text_key

    by_period: dict[str, list[str]] = {}
    try:
        for r in sink.query("results_cards_company", [scrip]):
            if r.get("period"):
                by_period.setdefault(r["period"], []).append(r["news_id"])
    except Exception:   # noqa: BLE001 - an older Worker refuses an unknown query
        pass
    cache = {} if cache is None else cache

    def text(news_id: str) -> str | None:
        if news_id not in cache:
            try:
                body = sink.get_object(text_key(news_id))
                cache[news_id] = text_of(body) if body else None
            except Exception:   # noqa: BLE001 - a damaged or missing cache file is no text
                cache[news_id] = None
        return cache[news_id]

    return by_period, text


def attach_referee(result: dict, by_period: dict[str, list[str]], text) -> None:
    """The verdict on each wrong_quarter, scale and mismatch pair of a company, from the official text of the quarter (a
    year: its Q4 filing; a wrong_quarter: also the filing of the quarter ours equals)."""
    for pair in result["pairs"]:   # the six other lines are not in "pairs": the text search is for revenue, profit and EPS
        if pair["class"] not in REFEREED:
            continue
        wanted = [pair["period"]] + list(pair.get("shifted") or [])[:1]
        wanted = [f"Q4{p}" if p.startswith("FY") else p for p in wanted]
        texts = [t for p in wanted for nid in by_period.get(p, []) if (t := text(nid))]
        pair.update({k: v for k, v in referee(pair, texts).items() if k in ("verdict", "snippet")})


def run(sink, companies: list[tuple[str, str]], day: str | None = None, workers: int = WORKERS,
        use_referee: bool = True) -> dict:
    """The cross-check over ``companies`` ((scrip, symbol) pairs): reads each dossier, its stored pages and, for the
    pairs to referee, the cached official text."""
    pages_by_symbol, newest = stored_pages(sink, day)

    def one(item: tuple[str, str]) -> dict:
        scrip, symbol = item
        dossier = sink.get_dossier(scrip)
        pages = {}
        for basis, key in (pages_by_symbol.get(symbol) or {}).items():
            blob = sink.get_object(key)
            parsed = parse_full(unpack(blob)) if blob else None
            if parsed:
                pages[basis] = parsed
        result = compare_company(dossier or {}, pages, scrip, symbol)
        if not pages_by_symbol.get(symbol):
            result["skipped"] = "no stored page"
        if use_referee and any(p["class"] in REFEREED for p in result["pairs"]):
            attach_referee(result, *official_texts(sink, scrip))
        return result

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(one, companies))
    return summarise(results, newest)


def summarise(results: list[dict], pages_day: str | None = None) -> dict:
    by_class = {c: 0 for c in CLASSES}
    by_metric: dict[str, dict[str, int]] = {}
    by_sector: dict[str, dict[str, int]] = {}
    gaps = {c: 0 for c in GAP_CLASSES}
    suspects = {k: 0 for k in SUSPECT_KINDS}
    verdicts: dict[str, int] = {}
    naming: dict[str, int] = {}
    skipped: dict[str, int] = {}
    worst = []
    rows = []
    six_by_class: dict[str, dict[str, int]] = {}
    for r in results:
        if r["skipped"]:
            skipped[r["skipped"]] = skipped.get(r["skipped"], 0) + 1
        base = {"scrip": r["scrip"], "symbol": r["symbol"], "sector": r["sector"], "basis": r["basis"]}
        bad = 0
        for p in r["pairs"]:
            by_class[p["class"]] += 1
            by_metric.setdefault(p["metric"], {c: 0 for c in CLASSES})[p["class"]] += 1
            by_sector.setdefault(r["sector"], {c: 0 for c in CLASSES})[p["class"]] += 1
            if p.get("verdict"):
                verdicts[p["verdict"]] = verdicts.get(p["verdict"], 0) + 1
            if p["class"] == "naming":
                naming[p["note"]] = naming.get(p["note"], 0) + 1
            if p["class"] != "match":
                rows.append({**base, **p})
                if p["class"] in ("mismatch", "scale", "wrong_quarter"):
                    bad += 1
        for p in r.get("six_pairs", []):
            six_by_class.setdefault(p["metric"], {c: 0 for c in SIX_CLASSES})[p["class"]] += 1
            if p["class"] != "match":
                rows.append({**base, **p})
        for s in r.get("suspects", []):
            suspects[s["kind"]] += 1
            rows.append({**base, **s})
        for g in r["gaps"]:
            gaps[g["class"]] += 1
            rows.append({**base, "period": g["period"], "metric": "", "class": g["class"], "memory_value": None,
                         "screener_value": None, "memory_source_id": "", "memory_filed": "", "note": ""})
        if bad or r.get("suspects"):
            worst.append({"scrip": r["scrip"], "symbol": r["symbol"], "sector": r["sector"],
                          "wrong_pairs": bad + len(r.get("suspects", [])), "pairs": len(r["pairs"])})
    worst.sort(key=lambda w: (-w["wrong_pairs"], w["symbol"]))
    total = sum(by_class.values())
    return {"pages_day": pages_day, "companies": len(results), "companies_compared": sum(1 for r in results if not r["skipped"]),
            "skipped": skipped, "pairs": total, "by_class": by_class, "by_metric": by_metric, "by_sector": by_sector,
            "six_pairs": sum(sum(row.values()) for row in six_by_class.values()), "six_by_class": six_by_class,
            "gaps": gaps, "memory_period_suspect": suspects, "verdicts": verdicts, "naming": naming,
            "worst_companies": worst[:25], "rows": rows}


# --- the output ---------------------------------------------------------------------------------------------------

def _cell(v) -> str:
    return "" if v is None else f"{v:g}" if isinstance(v, float) else str(v)


def to_csv(summary: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for r in summary["rows"]:
        writer.writerow([_cell(r.get(k)) for k in CSV_HEADER])
    return buffer.getvalue()


REFEREE_HEADER = ("scrip,symbol,period,metric,class,ours,screener,verdict,official_hits").split(",")


def to_referee_csv(summary: dict) -> str:
    """referee.csv: every refereed pair, with the official line each value was found on and the verdict; the
    ``no_official_text`` ones are the list a later step fetches."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(REFEREE_HEADER)
    for r in summary["rows"]:
        if r.get("verdict"):
            writer.writerow([_cell(r["scrip"]), _cell(r["symbol"]), r["period"], r["metric"], r["class"],
                             _cell(r["memory_value"]), _cell(r["screener_value"]), r["verdict"], r.get("snippet", "")])
    return buffer.getvalue()


def to_json(summary: dict) -> str:
    return json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False, indent=1) + "\n"


def render(summary: dict) -> str:
    c, g = summary["by_class"], summary["gaps"]
    lines = [f"screener cross-check (pages of {summary['pages_day']}, read only):",
             f"companies                    {summary['companies']}",
             f"compared                     {summary['companies_compared']}",
             f"pairs compared               {summary['pairs']}"]
    lines += [f"  {name:26}{c[name]}" for name in CLASSES]
    if summary.get("six_by_class"):
        lines += [f"six other lines, pairs       {summary['six_pairs']}"]
        for metric, row in sorted(summary["six_by_class"].items()):
            lines += [f"  {metric:16}" + "  ".join(f"{k} {n}" for k, n in row.items() if n)]
    lines += [f"memory_period_suspect        {sum(summary['memory_period_suspect'].values())}"]
    lines += [f"  {k:26}{v}" for k, v in summary["memory_period_suspect"].items()]
    lines += ["referee verdicts:"] + [f"  {k:34}{v}" for k, v in sorted(summary["verdicts"].items())]
    lines += [f"quarters screener only       {g['screener_only']}", f"quarters memory only         {g['memory_only']}"]
    if summary["skipped"]:
        lines.append("companies skipped: " + ", ".join(f"{k} {v}" for k, v in sorted(summary["skipped"].items())))
    return "\n".join(lines)


def _table(rows: list[dict], limit: int = 15) -> list[str]:
    out = ["| Symbol | Period | Metric | Ours | Screener | Verdict | Note |", "|---|---|---|---|---|---|---|"]
    out += [f"| {r['symbol']} | {r['period']} | {r['metric']} | {_cell(r['memory_value'])} | {_cell(r['screener_value'])} | "
            f"{r.get('verdict', '')} | {r.get('note', '')} |" for r in rows[:limit]]
    return out + [""]


def to_markdown(summary: dict, date: str) -> str:
    """The short report, filled from the summary (``docs/audit/screener-crosscheck-<date>.md``); the owner's reading and
    the class fixes are written by hand after it. It leads with what is wrong with us, then screener's errors, then
    naming."""
    c, g, v = summary["by_class"], summary["gaps"], summary["verdicts"]
    total = summary["pairs"] or 1
    rows = summary["rows"]
    wrong_quarter = [r for r in rows if r["class"] == "wrong_quarter"]
    suspect = [r for r in rows if r["class"] == "memory_period_suspect"]
    ours_wrong = [r for r in rows if r.get("verdict") == "screener_matches_official"]
    screener_wrong = [r for r in rows if r.get("verdict") == "ours_matches_official"]
    out = [f"# Screener cross-check, {date}", "",
           f"Read only: memory's exchange-file figures against the screener.in pages downloaded on {summary['pages_day']} "
           f"(F163, TODO 50), the official filing as referee where the cached text allows. {summary['companies_compared']} of "
           f"{summary['companies']} companies compared, {summary['pairs']} pairs (quarters and years; revenue, profit, EPS).", "",
           "## What is wrong with us", "",
           f"- Official filing agrees with screener, not with us: {len(ours_wrong)} pairs.",
           f"- wrong_quarter (our figure equals screener's figure for another period): {c['wrong_quarter']} pairs.",
           f"- memory_period_suspect (memory's own period checks): {sum(summary['memory_period_suspect'].values())} "
           + "(" + ", ".join(f"{k} {n}" for k, n in summary["memory_period_suspect"].items()) + ").", "",
           "### Official filing agrees with screener", ""] + _table(ours_wrong)
    out += ["### wrong_quarter", ""] + _table(wrong_quarter)
    says = {k: n for k, n in v.items() if k.startswith("official_says_")}
    if says:
        out += ["Where the official text says the figure belongs: " + ", ".join(f"{k[14:]} {n}" for k, n in sorted(says.items())) + ".", ""]
    out += ["### memory_period_suspect", "", "| Symbol | Period | Metric | Value | Reason |", "|---|---|---|---|---|"]
    out += [f"| {r['symbol']} | {r['period']} | {r['metric']} | {_cell(r['memory_value'])} | {r['note']} |" for r in suspect[:15]]
    out += ["", "## Screener errors (the official filing agrees with us)", "",
            f"{len(screener_wrong)} pairs.", ""] + _table(screener_wrong)
    out += ["## Naming (screener equals another official line of ours)", "", f"{c['naming']} pairs.", ""]
    out += [f"- {note}: {n}" for note, n in sorted(summary["naming"].items(), key=lambda kv: -kv[1])[:15]] + [""]
    out += ["## Not settled", "", f"- both_match (two different lines): {v.get('both_match', 0)}",
            f"- neither: {v.get('neither', 0)}",
            f"- no_official_text: {v.get('no_official_text', 0)} (listed in referee.csv, for a later step to fetch)", "",
            "## Counts by class", "", "| Class | Pairs | Share |", "|---|---|---|"]
    out += [f"| {name} | {c[name]} | {100 * c[name] / total:.1f}% |" for name in CLASSES]
    out += ["", f"Quarters on screener that memory lacks: {g['screener_only']}. Quarters in memory that screener lacks "
                f"(inside screener's span): {g['memory_only']}.", ""]
    if summary["skipped"]:
        out += ["Companies not compared: " + ", ".join(f"{k} {n}" for k, n in sorted(summary["skipped"].items())) + ".", ""]
    out += ["## By metric", "", "| Metric | " + " | ".join(CLASSES) + " |", "|---|" + "---|" * len(CLASSES)]
    out += [f"| {m} | " + " | ".join(str(row[k]) for k in CLASSES) + " |" for m, row in sorted(summary["by_metric"].items())]
    if summary.get("six_by_class"):
        out += ["", "## The six other lines (quarters; Operating Profit, Other Income, Interest, Depreciation, Profit before tax, "
                    "Tax %)", "", f"{summary['six_pairs']} pairs, counted apart from the table above. Explained: screener's "
                    "own rules close the gap (docs/bench/screener-rules.md).", "",
                "| Metric | " + " | ".join(SIX_CLASSES) + " |", "|---|" + "---|" * len(SIX_CLASSES)]
        out += [f"| {m} | " + " | ".join(str(row[k]) for k in SIX_CLASSES) + " |"
                for m, row in sorted(summary["six_by_class"].items())]
    out += ["", "## Sectors with the most unexplained pairs (mismatch, scale, wrong_quarter)", "",
            "| Sector | Pairs | Wrong |", "|---|---|---|"]
    sectors = sorted(summary["by_sector"].items(),
                     key=lambda kv: -(kv[1]["mismatch"] + kv[1]["scale"] + kv[1]["wrong_quarter"]))[:10]
    out += [f"| {s} | {sum(row.values())} | {row['mismatch'] + row['scale'] + row['wrong_quarter']} |" for s, row in sectors]
    out += ["", "## Worst companies", "", "| Symbol | Sector | Wrong pairs | Pairs |", "|---|---|---|---|"]
    out += [f"| {w['symbol']} | {w['sector']} | {w['wrong_pairs']} | {w['pairs']} |" for w in summary["worst_companies"][:15]]
    out += ["", "Every non-match pair, with both values, memory's source id and filed date, is in the CSV artifact; the "
                "refereed pairs, with the official line, in referee.csv.", "",
            "## Reading (to be written)", "", "- Classes found, and which are screener's (not ours):", "- Fixes, one class each:", ""]
    return "\n".join(out)
