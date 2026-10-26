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

Each ``quarter_sum_gap`` also gets a ``cause`` (``classify``): ``derived_line`` (a line our code computes whose inputs sum
correctly, so the gap is in the derivation), ``one_quarter_off`` (the year-to-date chain Q1+Q2=H1, H1+Q3=9M, 9M+Q4=FY breaks
first at one quarter, or the same gap sits on two or more lines of the company and year), ``restructuring_suspect`` (five
or more flow lines over 2% together: a merger, demerger or restatement of the year) or ``other``. Memory does store H1 and 9M
(every results file's year-to-date contexts are labelled H1FYxx / 9MFYxx / FYxx by ``xbrl.period_label`` and kept by
``dossier.KEEP_PERIODS``), but only for companies whose year ends in March.

Only exchange-file sources are used; a card's figure (a model reading a PDF) is never one side of a check."""
from __future__ import annotations

import csv
import io
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from .dossier import FLOW_METRICS, XBRL_SOURCE
from .year_check import ROUND_CR, ROUND_PCT, SUM_METRICS, close   # shared with the MEMORY_YEAR_CHECK hold (F177)

READ_WORKERS = 8
MERGER_LINES = 3    # this many lines of a quarter differing together in one later file
SCALES = (10, 100, 1000)
SCALE_TOL = 0.02
CLASSES = ("rounding", "restated", "scale_suspect", "wrong_quarter_suspect", "quarter_sum_gap")
MERGER_NOTE = "possible merger, discontinued operation or accounting change"
CSV_FIELDS = ("scrip", "symbol", "metric", "period", "own_value", "later_value", "class", "cause", "quarter", "ytd_links",
              "source_ids", "basis", "diff_pct", "note")
CAUSES = ("derived_line", "one_quarter_off", "restructuring_suspect", "other")
RESTRUCTURE_LINES = 5   # this many flow lines of one year over RESTRUCTURE_PCT together
RESTRUCTURE_PCT = 2.0
LINKS = ("Q1+Q2=H1", "H1+Q3=9M", "9M+Q4=FY")
LINK_QUARTER = ("Q1|Q2", "Q3", "Q4")   # the first broken link names the quarter that is off (the first cannot tell Q1 from Q2)
# lines our code computes and what they come from (xbrl._results builds ebitda; a row's own ``calc`` label overrides)
DERIVED_INPUTS = {
    "ebitda": ("pbt", "finance_cost", "depreciation", "other_income", "exceptional_items"),
    "total_expenses": ("cost_of_materials", "purchases_stock_in_trade", "inventory_change", "employee_cost", "finance_cost",
                       "depreciation", "other_expenses"),
    "other_expenses": (),
}


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


def _ytd_value(by: dict, metric: str, label: str, own_quarter: str, bases: set) -> float | None:
    """A year-to-date figure (H1FY27, 9MFY27, FY27) from the file of the quarter it closes (the Q2 file for H1), else the
    figure memory holds; only an exchange figure in crore on the row's basis."""
    entry = by.get((metric, label))
    if entry is None or (entry.get("unit") or "INR_CR") != "INR_CR":
        return None
    srcs = [x for x in _sources(entry) if is_exchange(x) and x.get("value") is not None]
    src = next((x for x in srcs if str(x.get("news_id") or "").endswith(f":{own_quarter}")), None) or _value_source(entry)
    if src is None or not is_exchange(src) or src.get("value") is None:
        return None
    basis = src.get("basis") or entry.get("basis")
    return None if basis and bases and basis not in bases else src["value"]


def ytd_chain(by: dict, metric: str, fy: str, quarters: list[float], bases: set) -> list[str]:
    """The three links Q1+Q2 against H1 (Q2 file), H1+Q3 against 9M (Q3 file), 9M+Q4 against FY (Q4 file): each ``ok``,
    ``broken`` or ``missing`` (the year-to-date figure is not in memory). A link's left side is the stored year-to-date
    figure of the link before, else the quarters' running sum."""
    ytd = [_ytd_value(by, metric, f"H1{fy}", f"Q2{fy}", bases), _ytd_value(by, metric, f"9M{fy}", f"Q3{fy}", bases),
           _ytd_value(by, metric, fy, f"Q4{fy}", bases)]
    out, running = [], quarters[0]
    for i, right in enumerate(ytd):
        left = running + quarters[i + 1]
        out.append("missing" if right is None else "ok" if close(left, right) else "broken")
        running = right if right is not None else left
    return out


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
        links = ytd_chain(by, metric, period, [p["value"] for p in parts], bases)
        first = next((i for i, v in enumerate(links) if v != "ok"), None)   # a missing link earlier leaves a later break unnamed
        broken = first if first is not None and links[first] == "broken" else None
        calc = [s for s in srcs if (s.get("lab") or {}).get("by") == "calc"]
        inputs = sorted({str(x).split(":")[0] for s in calc for x in ((s.get("lab") or {}).get("from") or [])} - {metric})
        rows.append({"metric": metric, "period": period, "own_value": full["value"], "later_value": round(total, 2),
                     "ytd_links": ",".join(links), "quarter": LINK_QUARTER[broken] if broken is not None and not ok else "",
                     "calc": bool(calc), "calc_inputs": inputs, "q_values": [p["value"] for p in parts],
                     "class": "rounding" if ok else "quarter_sum_gap",
                     "source_ids": " | ".join(str(s.get("news_id")) for s in srcs),
                     "basis": next(iter(bases), ""), "diff_pct": _pct(total, full["value"]),
                     "note": "" if ok else f"quarters sum to {total:.2f}, year {full['value']:.2f}, gap {gap:+.2f} Cr"})
    return rows


def _f(x) -> float | None:
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def _year_row(r: dict) -> bool:
    p = str(r.get("period") or "")
    return p.startswith("FY") and len(p) == 4


def _gap(r: dict) -> float:
    return (_f(r.get("later_value")) or 0.0) - (_f(r.get("own_value")) or 0.0)


def _same_gap(a: float, b: float) -> bool:
    return a * b > 0 and abs(a - b) <= max(0.015, 0.005 * max(abs(a), abs(b)))


def classify(rows: list[dict]) -> list[dict]:
    """Set ``cause`` (and a note) on every ``quarter_sum_gap`` row, in place; works on rows from stored dossiers and on the
    CSV's rows alike. Per company, year and basis, in this order: (1) a derived line (``calc`` label, or ebitda /
    total_expenses / other_expenses) whose inputs all sum to their years: ``derived_line``, the gap is in the derivation;
    (2) the year-to-date chain names a quarter: ``one_quarter_off``; (3) five or more flow lines over 2% together:
    ``restructuring_suspect``; (4) the same gap on two or more lines: ``one_quarter_off`` (the quarter from those lines'
    chains, else not named); (5) a derived line whose inputs could not be checked: ``derived_line``; else ``other``. A
    derived line whose own inputs also have a gap inherits theirs and falls through (2) to (4)."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        if _year_row(r):
            groups.setdefault((r.get("scrip"), r.get("period"), r.get("basis") or ""), []).append(r)
    for group in groups.values():
        gaps = [r for r in group if r.get("class") == "quarter_sum_gap"]
        if not gaps:
            continue
        status = {r["metric"]: r.get("class") for r in group}
        wide = [r for r in group if (_f(r.get("diff_pct")) or 0) > RESTRUCTURE_PCT]
        for r in gaps:
            metric, gap = r["metric"], _gap(r)
            inputs = [m for m in (r.get("calc_inputs") or DERIVED_INPUTS.get(metric, ())) if m != metric]
            derived = metric in DERIVED_INPUTS or bool(r.get("calc"))
            seen = [m for m in inputs if m in status]
            bad = [m for m in seen if status[m] == "quarter_sum_gap"]
            input_state = "unchecked" if not seen else "broken" if bad else "ok"
            peers = [g for g in gaps if g is not r and _same_gap(gap, _gap(g))]
            note = ""
            if derived and input_state == "ok":
                cause, note = "derived_line", f"derived line: its inputs ({', '.join(seen)}) sum to their years, so the gap is in the derivation"
            elif r.get("quarter"):
                cause, note = "one_quarter_off", f"the year-to-date chain first breaks at {r['quarter']}"
            elif len(wide) >= RESTRUCTURE_LINES:
                cause, note = "restructuring_suspect", (f"{len(wide)} flow lines of {r['period']} are over {RESTRUCTURE_PCT:g}% off together: "
                                                        "a merger, demerger or restatement of the year, not of the quarters")
            elif peers:
                named = Counter(g["quarter"] for g in peers if g.get("quarter"))
                if named:
                    r["quarter"] = named.most_common(1)[0][0]
                cause, note = "one_quarter_off", f"the same gap {gap:+.2f} Cr sits on {len(peers) + 1} lines" + (
                    f"; the chain of {peers[0]['metric']} names {r['quarter']}" if r.get("quarter") else ": one quarter, not named")
            elif derived and input_state == "unchecked":
                cause, note = "derived_line", "derived line; its inputs are not in the checks"
            else:
                cause = "other"
            if bad and cause != "derived_line":
                note = (note + "; " if note else "") + f"derived line inheriting the gap of its inputs ({', '.join(bad)})"
            r["cause"] = cause
            if note:
                r["note"] = f"{r.get('note') or ''}; {note}".strip("; ")
    return rows


REFEREE_FIELDS = ("verdict", "scrip", "symbol", "metric", "period", "basis", "memory_value", "screener_value", "official_value", "note")


def referee_rows(rows: list[dict]) -> list[dict]:
    """The ``one_quarter_off`` rows with a named quarter, in the shape ``pdf_referee.load_csv`` reads: one row per company,
    quarter and metric, verdict ``neither`` (open). ``memory_value`` is the stored quarter; ``screener_value`` carries the
    figure the year implies for that quarter (the year less the other three), so a PDF figure equal to it means the year was
    right (the referee prints that as ``pdf_matches_screener``). The first-link case (Q1 or Q2) gives both quarters."""
    out, seen = [], set()
    for r in rows:
        values = r.get("q_values")
        if r.get("cause") != "one_quarter_off" or not r.get("quarter") or not values or not r.get("symbol"):
            continue
        for q in r["quarter"].split("|"):
            i = int(q[1]) - 1
            key = (r["scrip"], r["metric"], f"{q}{r['period']}", r.get("basis"))
            if key in seen:
                continue
            seen.add(key)
            implied = _f(r["own_value"]) - (sum(values) - values[i])
            out.append({"verdict": "neither", "scrip": r["scrip"], "symbol": r["symbol"], "metric": r["metric"],
                        "period": f"{q}{r['period']}", "basis": r.get("basis") or "", "memory_value": values[i],
                        "screener_value": round(implied, 2), "official_value": "",
                        "note": f"self-check: {r['period']} year {r['own_value']}, quarters sum to {r['later_value']}"})
    return out


def referee_csv(report: dict) -> str:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=REFEREE_FIELDS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(referee_rows(report["rows"]))
    return out.getvalue()


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
    classify(rows)
    counts = {c: 0 for c in CLASSES}
    worst: dict[str, Counter] = {}
    for r in rows:
        counts[r["class"]] += 1
        if r["class"] != "rounding":
            worst.setdefault(r["scrip"], Counter())[r["class"]] += 1
    by_cause = Counter(r["cause"] for r in rows if r.get("cause"))
    year = [r for r in rows if r.get("ytd_links")]
    links = {name: Counter(r["ytd_links"].split(",")[i] for r in year) for i, name in enumerate(LINKS)}
    broken_first = Counter(r["quarter"] for r in rows if r.get("class") == "quarter_sum_gap" and r.get("quarter"))
    ranked = sorted(worst.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
    return {"companies_checked": len(scrips), "rows_checked": len(rows), "by_class": counts,
            "by_cause": {c: by_cause.get(c, 0) for c in CAUSES},
            "ytd_links": {n: dict(c) for n, c in links.items()}, "first_broken_link_names": dict(broken_first),
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
    if report.get("by_cause"):
        lines.append("quarter_sum_gap rows by cause:")
        lines += [f"  {c:22} {n}" for c, n in report["by_cause"].items()]
        lines.append("year-to-date links over every year check (H1 / 9M / FY as memory holds them from the Q2 / Q3 / Q4 file):")
        lines += [f"  {n:10} {dict(c)}" for n, c in report["ytd_links"].items()]
        lines.append(f"  first broken link names (gap rows): {report['first_broken_link_names']}")
    lines.append("worst companies (differences other than rounding):")
    for w in report["worst_companies"][:examples]:
        lines.append(f"  {w['scrip']} {w['symbol']}: {w['differences']} {w['by_class']}")
    lines.append("(only exchange-file figures are compared; EPS, balance-sheet and ratio lines are not summed)")
    return "\n".join(lines)
