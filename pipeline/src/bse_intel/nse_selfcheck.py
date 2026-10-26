"""NSE's own figures in memory checked against themselves, read only (no download, no AI, no write). TODO row 60.

(a) Own file against a later file: a quarter's figure from its own results file against the same quarter as printed in a
later file's comparative column. Memory keeps them as separate ``sources`` of one metric entry; a later file's column carries
``restated_from`` (``dossier._metric_entry``, F167). Classes: ``rounding``; ``restated`` (the note says "possible merger,
discontinued operation or accounting change" when three or more lines of that quarter differ together in one later file);
``scale_suspect`` (a single-line jump at an exact x10 / x100 / x1000 ratio); ``wrong_quarter_suspect`` (the own file's figure
equals a different quarter's figure in the same later file).

(b) Quarters against the year: Q1+Q2+Q3+Q4 against FY, flow metrics only (EPS, balances and ratios are left out), only
where all five figures are exchange-file figures (label ``by`` file or calc, or an ``xbrl:`` news id) in crore on one
basis. Class ``rounding`` or ``quarter_sum_gap`` with its size.

Only exchange-file sources are used; a card's figure (a model reading a PDF) is never one side of a check."""
from __future__ import annotations

import csv
import io
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from .dossier import FLOW_METRICS, XBRL_SOURCE

READ_WORKERS = 8
ROUND_PCT = 0.5     # within 0.5% ...
ROUND_CR = 1.0      # ... or 1 crore
MERGER_LINES = 3    # this many lines of a quarter differing together in one later file
SCALES = (10, 100, 1000)
SCALE_TOL = 0.02
CLASSES = ("rounding", "restated", "scale_suspect", "wrong_quarter_suspect", "quarter_sum_gap")
MERGER_NOTE = "possible merger, discontinued operation or accounting change"
CSV_FIELDS = ("scrip", "symbol", "metric", "period", "own_value", "later_value", "class", "source_ids", "basis", "diff_pct", "note")
SUM_METRICS = FLOW_METRICS - {"operating_cash_flow"}   # a cash flow is not stated quarter by quarter, so the sum check skips it


def _sources(entry: dict) -> list[dict]:
    return entry.get("sources") or [{
        "news_id": entry.get("source_news_id"), "as_of": entry.get("as_of"), "value": entry.get("value"),
        "unit": entry.get("unit"), "basis": entry.get("basis"), "lab": entry.get("lab"),
        "restated_from": entry.get("restated_from")}]


def is_exchange(source: dict) -> bool:
    """A figure the exchange's own file gave: the label says file or calc, or the id is a synthetic xbrl one."""
    return (source.get("lab") or {}).get("by") in ("file", "calc") or str(source.get("news_id") or "").startswith(XBRL_SOURCE)


def _same_basis(a: str | None, b: str | None) -> bool:
    return a is None or b is None or a == b


def close(a: float, b: float, unit: str | None = "INR_CR") -> bool:
    """Equal within rounding: 0.5% of the larger figure, or 1 crore when the figures are in crore."""
    tol = max(abs(a), abs(b)) * ROUND_PCT / 100
    if (unit or "INR_CR") == "INR_CR":
        tol = max(tol, ROUND_CR)
    return abs(a - b) <= max(tol, 1e-9)


def _scale(own: float, later: float) -> int | None:
    if not own or not later:
        return None
    ratio = max(abs(own), abs(later)) / min(abs(own), abs(later))
    return next((s for s in SCALES if abs(ratio - s) <= s * SCALE_TOL), None)


def _pct(a: float, b: float) -> float:
    return round(abs(a - b) / abs(b) * 100, 1) if b else 0.0


def _wrong_quarter(by: dict, metric: str, period: str, own: float, later_id: str, unit: str | None) -> str | None:
    """The other quarter whose figure in the same later file equals the own file's figure for this one."""
    if not own:
        return None
    for (m, p), other in by.items():
        if m != metric or p == period:
            continue
        for s in _sources(other):
            if s.get("news_id") == later_id and s.get("value") is not None and close(own, s["value"], unit):
                return p
    return None


def own_against_later(entries: list[dict]) -> list[dict]:
    """(a) for one company: a row for every quarter flow figure that has its own file and a later file's comparative."""
    by = {(e.get("metric"), e.get("period")): e for e in entries
          if e.get("metric") in FLOW_METRICS and str(e.get("period", "")).startswith("Q")}
    pairs = []   # (entry, own source, later source)
    for e in by.values():
        src = sorted((s for s in _sources(e) if is_exchange(s) and s.get("value") is not None), key=lambda s: s.get("as_of") or "")
        own = next((s for s in src if not s.get("restated_from")), None)
        laters = [s for s in src if s.get("restated_from") and own is not None and _same_basis(own.get("basis"), s.get("basis"))]
        if own is not None and laters:
            pairs.append((e, own, laters[-1]))
    differing: Counter = Counter()   # (period, later file's id) -> lines that differ
    for e, own, later in pairs:
        if not close(own["value"], later["value"], e.get("unit")):
            differing[(e["period"], later["news_id"])] += 1
    rows = []
    for e, own, later in pairs:
        metric, period = e["metric"], e["period"]
        a, b = own["value"], later["value"]
        cls, note = "rounding", ""
        if not close(a, b, e.get("unit")):
            n = differing[(period, later["news_id"])]
            other = _wrong_quarter(by, metric, period, a, later["news_id"], e.get("unit"))
            scale = _scale(a, b)
            if other:
                cls, note = "wrong_quarter_suspect", f"own figure equals {other} in the later file"
            elif scale and n == 1:
                cls, note = "scale_suspect", f"x{scale} between the two files"
            else:
                cls = "restated"
                if n >= MERGER_LINES:
                    note = f"{n} lines of {period} differ: {MERGER_NOTE}"
        rows.append({"metric": metric, "period": period, "own_value": a, "later_value": b, "class": cls,
                     "source_ids": f"{own['news_id']} | {later['news_id']}", "basis": own.get("basis") or later.get("basis") or "",
                     "diff_pct": _pct(a, b), "note": note})
    return rows


def _value_source(entry: dict) -> dict | None:
    srcs = _sources(entry)
    chosen = entry.get("value_news_id")
    return next((s for s in srcs if s.get("news_id") == chosen), None) or (srcs[-1] if srcs else None)


def quarters_against_year(entries: list[dict]) -> list[dict]:
    """(b) for one company: Q1+Q2+Q3+Q4 against FY for each flow metric whose five figures are exchange figures in crore on
    one basis."""
    by = {(e.get("metric"), e.get("period")): e for e in entries if e.get("metric") in SUM_METRICS}
    rows = []
    for (metric, period), full in by.items():
        if not (str(period).startswith("FY") and len(period) == 4):
            continue
        parts = [by.get((metric, f"Q{i}{period}")) for i in (1, 2, 3, 4)]
        if any(p is None for p in parts):
            continue
        members = [full] + parts
        srcs = [_value_source(m) for m in members]
        if any(s is None or not is_exchange(s) or s.get("value") is None or (m.get("unit") or "INR_CR") != "INR_CR"
               for m, s in zip(members, srcs)):
            continue
        bases = {s.get("basis") or m.get("basis") for m, s in zip(members, srcs)} - {None}
        if len(bases) > 1:
            continue
        total = sum(m["value"] for m in parts)
        gap = total - full["value"]
        ok = close(total, full["value"])
        rows.append({"metric": metric, "period": period, "own_value": full["value"], "later_value": round(total, 2),
                     "class": "rounding" if ok else "quarter_sum_gap",
                     "source_ids": " | ".join(str(s.get("news_id")) for s in srcs),
                     "basis": next(iter(bases), ""), "diff_pct": _pct(total, full["value"]),
                     "note": "" if ok else f"quarters sum to {total:.2f}, year {full['value']:.2f}, gap {gap:+.2f} Cr"})
    return rows


def check(dossier: dict | None) -> list[dict]:
    entries = (dossier or {}).get("financial_metrics", [])
    return own_against_later(entries) + quarters_against_year(entries)


def survey(sink, scrips: list[str], symbols: dict[str, str] | None = None, workers: int = READ_WORKERS) -> dict:
    def one(scrip: str) -> list[dict]:
        return check(sink.get_dossier(scrip))

    if workers <= 1 or len(scrips) <= 1:
        results = [one(s) for s in scrips]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, scrips))
    symbols = symbols or {}
    rows = [{"scrip": scrip, "symbol": symbols.get(scrip, ""), **r} for scrip, rs in zip(scrips, results) for r in rs]
    counts = {c: 0 for c in CLASSES}
    worst: dict[str, Counter] = {}
    for r in rows:
        counts[r["class"]] += 1
        if r["class"] != "rounding":
            worst.setdefault(r["scrip"], Counter())[r["class"]] += 1
    ranked = sorted(worst.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
    return {"companies_checked": len(scrips), "rows_checked": len(rows), "by_class": counts,
            "worst_companies": [{"scrip": s, "symbol": symbols.get(s, ""), "differences": sum(c.values()), "by_class": dict(c)}
                                for s, c in ranked[:25]],
            "rows": rows}


def to_csv(report: dict) -> str:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=CSV_FIELDS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(report["rows"])
    return out.getvalue()


def render(report: dict, examples: int = 15) -> str:
    lines = [f"NSE self-check: {report['rows_checked']} comparisons across {report['companies_checked']} companies",
             "rows per class ((a) own file against a later file's comparative; quarter_sum_gap is (b) quarters against the year):"]
    lines += [f"  {c:22} {n}" for c, n in report["by_class"].items()]
    lines.append("worst companies (differences other than rounding):")
    for w in report["worst_companies"][:examples]:
        lines.append(f"  {w['scrip']} {w['symbol']}: {w['differences']} {w['by_class']}")
    lines.append("(only exchange-file figures are compared; EPS, balance-sheet and ratio lines are not summed)")
    return "\n".join(lines)
