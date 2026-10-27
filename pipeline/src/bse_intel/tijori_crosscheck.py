"""Read-only cross-check of memory's exchange-file figures against the stored Tijori pages. No request, no write, no AI.
TRACKER F189, TODO 92.

Same shape as ``screener_crosscheck`` (F163), and it reuses that module's helpers (the lender line rule F186, the unit-slip
test, the alternative official lines): for every company, each quarter and each financial year is compared on memory's basis
with the exchange file's figure only (``metrics._figures``: ``xbrl:`` sources):

- revenue: Tijori's ``Net Sales`` (quarterly, ``qt_c`` / ``qt_s``) or ``Sales`` (annual, ``pl_c_s`` / ``pl_s_s``) against our
  ``revenue``; a lender's revenue against our ``revenue``, else ``interest_earned`` (F186: a bank's file has no revenue line);
- pat: ``Net Profit`` against our ``pat``;
- eps: ``EPS`` (the ``Quarterly Ratios`` section's sub-row, per quarter; the annual tables have no EPS row, so years are not
  compared on EPS) against our ``eps`` or ``basic_eps``.

Tijori prints 2 to 4 decimals, so the tolerance is tight, not screener's ₹1 Cr: money within 0.011 Cr or 0.05%, EPS within
0.011. Classes (one per pair):

- ``match``: within the tolerance;
- ``sign``: ours is the figure with the opposite sign (Apar Industries Q1FY27: EPS -116.37 in memory, 116.3679 on Tijori);
- ``wrong_quarter``: ours differs but equals (at least ₹5 Cr) Tijori's figure for another quarter or year of the same line;
- ``scale``: the ratio is 10, 100 or 1000 (or the inverse) within 3%;
- ``naming``: Tijori's figure equals another official line of ours (total income, owners' profit ...);
- ``lender_definition``: a lender's revenue or profit differs (different definitions);
- ``eps_adjusted``: an EPS mismatch (not a sign, wrong-quarter or scale one, and not a lead) whose tijori / ours ratio (same
  sign) is within 2% of another EPS pair's ratio of the same company (tijori's EPS is adjusted for later share changes, ours
  is as filed); an EPS ratio of 10, 100 or 1000 (or the inverse) within 3% is ``scale``, never an adjustment;
- ``mismatch``: anything else.

Row names (measured 26 Oct 2026 on ABB, Apar and Dolphin Offshore, none a lender): ``Net Sales``, ``Net Profit`` and the
``Quarterly Ratios`` > ``EPS`` row (formula ``adj_eps_abs``, an adjusted EPS) in the quarterly sections; ``Sales`` and
``Net Profit`` in the annual ones (``Net Sales`` in the detailed ``pl_*_d``). NOT confirmed: the top line of a bank, NBFC or
insurer (no lender sample yet). It is configurable: ``TIJORI_LENDER_REVENUE_LINES`` (comma-separated row names, tried in
order) replaces ``LENDER_REVENUE_LINES``; the row each lender actually used, and the row names of a lender where none fitted,
are in the summary (``lender_lines_used``, ``lender_rows_unmatched``) so the names can be confirmed from the first run.

Columns: "Jun 2026" is Q1FY27 (the Indian year runs April to March, as ``screener_fill.period_of``); the sections' own
``skip_report_dates`` are left out (ABB's Mar and Jun 2024, whose values are 0, not results); the annual tables are read only on
their March columns (``FY26`` = Mar 2026; ABB's December years are not compared) and the trailing TTM column ("Jun 2026"
beside a ``table_footer`` "TTM Values as of Jun 2026") is not a year.

The strongest leads: a pair where Tijori and the stored screener page BOTH disagree with memory and agree with each other
(``lead`` in the CSV, its own section of the report). Tijori probably shares a data vendor with screener, so two copies of one
vendor's figure are one source, not two; the leads say where to look first, not who is right (the two-source rule: only an
exchange file or the filing corrects memory). The output is a summary, a CSV of every non-match pair and a short markdown
report; the job uploads them as an artifact and commits nothing.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from . import line_map
from . import screener_crosscheck as sc
from .memory_gaps import main_basis
from .metrics import CONSOLIDATED, STANDALONE, _figures, is_lender
from .periods import quarter_index
from .screener_download import PREFIX as SCREENER_PREFIX  # noqa: F401
from .screener_fill import parse_full, period_of, year_of
from .tijori import PREFIX, unpack

MONEY_ABS, MONEY_REL = 0.011, 0.0005
EPS_ABS = 0.011
MIN_SHIFT_VALUE = sc.MIN_SHIFT_VALUE
CLASSES = ("match", "sign", "wrong_quarter", "scale", "naming", "lender_definition", "eps_adjusted", "mismatch")
EPS_FACTOR_TOLERANCE = 0.02   # tijori's adjusted EPS over ours: the same factor within 2% across a company's periods
WORKERS = 8

# the row names (see the module docstring for what was measured and what was not)
REVENUE_LINES = line_map.tijori_rows("revenue")
LENDER_REVENUE_LINES = line_map.tijori_rows("revenue", lender=True)
PROFIT_LINES = line_map.tijori_rows("pat")
EPS_LINES = line_map.tijori_rows("eps")


def _lines(env: str, default: tuple[str, ...]) -> tuple[str, ...]:
    configured = tuple(x.strip() for x in os.environ.get(env, "").split(",") if x.strip())
    return configured or default


CSV_HEADER = ("scrip,symbol,sector,basis,period,metric,class,memory_value,tijori_value,screener_value,lead,"
              "memory_source_id,memory_filed,note").split(",")


# --- the page -----------------------------------------------------------------------------------------------------

def _row(section: dict, names: tuple[str, ...]) -> tuple[str, list] | None:
    """(row name, values) of the first of ``names`` found among a section's rows or their sub-rows (case-insensitive)."""
    wanted = [n.lower() for n in names]
    rows = [(r.get("name") or "", r) for r in section.get("data") or []]
    rows += [(s.get("name") or "", s) for r in section.get("data") or [] for s in (r.get("sub_section") or [])
             if isinstance(s, dict)]
    for want in wanted:
        for name, row in rows:
            if name.lower() == want and isinstance(row.get("value"), list):
                return name, row["value"]
    return None


def _number(value) -> float | None:
    return round(float(value), 4) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _month_year(column: str) -> tuple[str, str] | None:
    m = re.fullmatch(r"\s*([A-Za-z]{3})\w*\s+(\d{4})\s*", column or "")
    return (m[1].lower(), m[2]) if m else None


def _last_is_ttm(columns: list, footer: str) -> bool:
    """The footer marks a TTM AND the last column is the TTM one: it repeats the previous column's year, or is not a fiscal
    year-end of the series (another month than the column before it, which is how "Jun 2026" follows "Mar 2026"). A last
    column that is a regular year-end of the series is a real year, even when its date is the footer's "as of" date."""
    if "ttm" not in footer.lower():
        return False
    last, before = _month_year(columns[-1]), _month_year(columns[-2])
    if not last or not before:
        return False
    if last[1] == before[1]:
        return True
    return last[0] != before[0]


def parse_section(section: dict | None, kind: str, lender: bool) -> tuple[dict[str, dict], dict]:
    """One section (``qt_c`` ... or ``pl_c_s`` ...) as ``{period: {"revenue", "pat", "eps"}}`` and the row names used
    (``{"revenue": name, "pat": name, "eps": name}``). ``kind`` is ``quarter`` or ``year``. Columns in
    ``skip_report_dates`` are left out; on a year table only March columns count and the first of a repeated date wins (the
    trailing TTM column repeats the latest quarter's date)."""
    if not isinstance(section, dict):
        return {}, {}
    revenue = _row(section, _lines("TIJORI_LENDER_REVENUE_LINES", LENDER_REVENUE_LINES) if lender
                   else _lines("TIJORI_REVENUE_LINES", REVENUE_LINES))
    profit = _row(section, PROFIT_LINES)
    eps = _row(section, EPS_LINES) if kind == "quarter" else None
    skip = set(section.get("skip_report_dates") or [])
    columns = list(section.get("report_dates") or [])
    if kind == "year" and len(columns) > 1 and _last_is_ttm(columns, str(section.get("table_footer") or "")):
        columns = columns[:-1]
    out: dict[str, dict] = {}
    for i, column in enumerate(columns):
        if column in skip:
            continue
        period = period_of(column) if kind == "quarter" else year_of(column)
        if not period or period in out:
            continue
        pick = lambda row: _number(row[1][i]) if row and i < len(row[1]) else None   # noqa: E731
        out[period] = {"revenue": pick(revenue), "pat": pick(profit), "eps": pick(eps)}
    return out, {"revenue": revenue[0] if revenue else None, "pat": profit[0] if profit else None,
                 "eps": eps[0] if eps else None}


def parse_tables(tables: dict, basis: str, lender: bool = False) -> dict | None:
    """``{"basis", "quarters", "annual", "lines"}`` for a basis, from the stored ``fin_tables_data``; None without the
    quarterly section."""
    suffix = "c" if basis == CONSOLIDATED else "s"
    quarters, lines = parse_section((tables or {}).get(f"qt_{suffix}"), "quarter", lender)
    if not quarters:
        return None
    annual, _ = parse_section((tables or {}).get(f"pl_{suffix}_s"), "year", lender)
    return {"basis": basis, "quarters": quarters, "annual": annual, "lines": lines}


# --- one pair -----------------------------------------------------------------------------------------------------

def close(ours: float, theirs: float, metric: str) -> bool:
    """Within the tolerance: money 0.011 Cr or 0.05%, EPS 0.011."""
    if metric == "eps":
        return abs(ours - theirs) <= EPS_ABS
    return abs(ours - theirs) <= max(MONEY_ABS, MONEY_REL * abs(ours))


def classify(ours: float, theirs: float, metric: str, shifted_to: str | None, lender: bool, named: str | None = None) -> str:
    if close(ours, theirs, metric):
        return "match"
    if close(ours, -theirs, metric) and abs(theirs) > EPS_ABS:
        return "sign"
    if shifted_to:
        return "wrong_quarter"
    if metric != "eps" and sc._is_scale(ours, theirs):
        return "scale"
    if named:
        return "naming"
    if lender and metric in ("revenue", "pat"):
        return "lender_definition"
    return "mismatch"


def compare_company(dossier: dict, tables: dict | None, scrip: str = "", symbol: str = "",
                    screener_pages: dict[str, dict] | None = None) -> dict:
    """Pairs for one company. ``tables`` is the stored ``fin_tables_data``; ``screener_pages`` (basis -> parse_full's
    result) is optional and only adds each pair's screener value and the ``lead`` flag. Pure."""
    basis = main_basis(dossier) if dossier else None
    out = {"scrip": scrip, "symbol": symbol, "basis": basis, "sector": (dossier or {}).get("sector")
           or (dossier or {}).get("industry") or "unknown", "pairs": [], "skipped": None, "lines": {}, "lender": False,
           "rows_seen": []}
    if not basis:
        out["skipped"] = "no memory basis"
        return out
    lender = is_lender(dossier, basis)
    out["lender"] = lender
    page = parse_tables(tables or {}, basis, lender)
    if not page:
        out["skipped"] = "no tijori table on memory's basis"
        return out
    out["lines"] = page["lines"]
    if lender and not page["lines"].get("revenue"):   # a lender's top line is unconfirmed: say which rows there were
        section = tables.get("qt_c" if basis == CONSOLIDATED else "qt_s") or {}
        out["rows_seen"] = [r.get("name") for r in section.get("data") or [] if r.get("name")][:15]
    figures, _ = _figures(dossier, basis)
    screener_pairs = {}
    if screener_pages and screener_pages.get(basis):
        screener_pairs = {(p["period"], p["metric"]): p for p in
                          sc.compare_company(dossier, screener_pages, scrip, symbol)["pairs"] if p["class"] != "match"}
    for kind, table in (("quarter", page["quarters"]), ("year", page["annual"])):
        for period, row in table.items():
            for metric in ("revenue", "pat", "eps"):
                theirs = row.get(metric)
                entry = sc._ours(figures, lender, metric, period)
                if theirs is None or entry is None:
                    continue
                ours = entry["value"]
                shifted = []
                if metric != "eps" and abs(ours) >= MIN_SHIFT_VALUE and not close(ours, theirs, metric):
                    shifted = [other for other, other_row in table.items()
                               if other != period and other_row.get(metric) is not None
                               and not close(other_row[metric], theirs, metric) and close(ours, other_row[metric], metric)]
                named = next((label for label, alt in sc.alternatives(figures, metric, period, lender)
                              if close(alt, theirs, metric) and abs(alt - ours) > 1e-9), None)
                cls = classify(ours, theirs, metric, shifted[0] if shifted else None, lender, named)
                note = ""
                if shifted:
                    note = f"memory {period} = tijori's {', '.join(shifted)}"
                    if len(shifted) > 1:
                        note += f" (chance risk: {len(shifted)} columns match)"
                elif cls == "naming":
                    note = f"tijori {page['lines'].get(metric)} = our {named}"
                elif cls == "sign":
                    note = "ours has the opposite sign"
                pair = {"period": period, "metric": metric, "memory_value": ours, "tijori_value": theirs, "class": cls,
                        "screener_value": None, "lead": False, "shifted": shifted, "memory_source_id": sc._value_source(entry),
                        "memory_filed": entry.get("as_of") or "", "note": note}
                other = screener_pairs.get((period, metric))
                if other is not None:
                    pair["screener_value"] = other["screener_value"]
                    if cls != "match" and sc._close(theirs, other["screener_value"], metric):
                        pair["lead"] = True
                        pair["note"] = (pair["note"] + "; " if pair["note"] else "") + "screener agrees with tijori"
                out["pairs"].append(pair)
    mark_eps_adjusted(out["pairs"])
    return out


def mark_eps_adjusted(pairs: list[dict]) -> None:
    """Re-class EPS mismatches. A ratio (tijori / ours, same sign) within 3% of 10, 100 or 1000 or their inverses is a
    ``scale`` slip, never an adjustment. Of the rest, a gap is ``eps_adjusted`` (a share-change adjustment) only when at least
    two EPS gaps of the company share the factor within 2%; one gap alone, even near 1, stays a mismatch. A lead (screener
    agrees with tijori) is never re-classed."""
    ratios = {}
    for i, p in enumerate(pairs):
        if p["metric"] == "eps" and p["class"] == "mismatch" and not p.get("lead") and p["memory_value"] and p["tijori_value"]:
            ratio = p["tijori_value"] / p["memory_value"]
            if ratio > 0:
                ratios[i] = ratio
    scaled = {i for i in ratios if sc._is_scale(pairs[i]["memory_value"], pairs[i]["tijori_value"])}
    for i in scaled:
        pairs[i]["class"] = "scale"
        pairs[i]["note"] = (pairs[i]["note"] + "; " if pairs[i]["note"] else "") + f"tijori / ours = {ratios[i]:.4g} (EPS scale slip)"
    for i, ratio in ratios.items():
        if i in scaled:
            continue
        if any(j != i and j not in scaled and abs(other - ratio) <= EPS_FACTOR_TOLERANCE * ratio for j, other in ratios.items()):
            pairs[i]["class"] = "eps_adjusted"
            pairs[i]["note"] = (pairs[i]["note"] + "; " if pairs[i]["note"] else "") + f"tijori / ours = {ratio:.4g} (adjusted EPS)"


# --- the stored pages ---------------------------------------------------------------------------------------------

def stored_tables(sink, day: str | None = None) -> tuple[dict[str, str], str | None]:
    """symbol -> object key, from ``raw/tijori/<day>/`` (the newest day stored when ``day`` is None; a company missing from that
    day takes its page from the newest earlier day), and the newest day found."""
    found: dict[str, tuple[str, str]] = {}
    for key in sink.list_objects(PREFIX):
        m = re.fullmatch(re.escape(PREFIX) + r"(\d{4}-\d{2}-\d{2})/(.+)\.json\.gz", key)
        if not m or (day and m[1] > day):
            continue
        if m[2] not in found or m[1] > found[m[2]][0]:
            found[m[2]] = (m[1], key)
    newest = max((d for d, _ in found.values()), default=None)
    return {sym: key for sym, (_, key) in found.items()}, newest


def run(sink, companies: list[tuple[str, str]], day: str | None = None, workers: int = WORKERS,
        use_screener: bool = True) -> dict:
    """The cross-check over ``companies`` ((scrip, symbol) pairs): reads each dossier, its stored Tijori tables and, when
    ``use_screener``, its stored screener pages (the newest day)."""
    keys, newest = stored_tables(sink, day)
    screener_keys, _ = sc.stored_pages(sink) if use_screener else ({}, None)

    def one(item: tuple[str, str]) -> dict:
        scrip, symbol = item
        dossier = sink.get_dossier(scrip)
        blob = sink.get_object(keys[symbol]) if symbol in keys else None
        tables = json.loads(unpack(blob)) if blob else None
        pages = {}
        for basis, key in (screener_keys.get(symbol) or {}).items():
            raw = sink.get_object(key)
            parsed = parse_full(sc.unpack(raw)) if raw else None
            if parsed:
                pages[basis] = parsed
        result = compare_company(dossier or {}, tables, scrip, symbol, pages)
        if tables is None:
            result["skipped"] = "no stored page"
        return result

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(one, companies))
    return summarise(results, newest)


def summarise(results: list[dict], pages_day: str | None = None) -> dict:
    by_class = {c: 0 for c in CLASSES}
    by_metric: dict[str, dict[str, int]] = {}
    by_sector: dict[str, dict[str, int]] = {}
    skipped: dict[str, int] = {}
    lines_used: dict[str, int] = {}
    lender_lines: dict[str, int] = {}
    lender_unmatched: dict[str, int] = {}
    worst, rows = [], []
    for r in results:
        if r["skipped"]:
            skipped[r["skipped"]] = skipped.get(r["skipped"], 0) + 1
        if r.get("lender"):
            if r["lines"].get("revenue"):
                lender_lines[r["lines"]["revenue"]] = lender_lines.get(r["lines"]["revenue"], 0) + 1
            for name in r.get("rows_seen") or []:
                lender_unmatched[name] = lender_unmatched.get(name, 0) + 1
        for metric, name in (r.get("lines") or {}).items():
            if name:
                lines_used[f"{metric}: {name}"] = lines_used.get(f"{metric}: {name}", 0) + 1
        base = {"scrip": r["scrip"], "symbol": r["symbol"], "sector": r["sector"], "basis": r["basis"]}
        bad = 0
        for p in r["pairs"]:
            by_class[p["class"]] += 1
            by_metric.setdefault(p["metric"], {c: 0 for c in CLASSES})[p["class"]] += 1
            by_sector.setdefault(r["sector"], {c: 0 for c in CLASSES})[p["class"]] += 1
            if p["class"] != "match":
                rows.append({**base, **p})
                if p["class"] in ("mismatch", "scale", "wrong_quarter", "sign"):
                    bad += 1
        if bad:
            worst.append({"scrip": r["scrip"], "symbol": r["symbol"], "sector": r["sector"], "wrong_pairs": bad,
                          "pairs": len(r["pairs"])})
    worst.sort(key=lambda w: (-w["wrong_pairs"], w["symbol"]))
    leads = [r for r in rows if r.get("lead")]
    total = sum(by_class.values())
    return {"pages_day": pages_day, "companies": len(results), "companies_compared": sum(1 for r in results if not r["skipped"]),
            "skipped": skipped, "pairs": total, "matches": by_class["match"], "differences": total - by_class["match"],
            "by_class": by_class, "by_metric": by_metric, "by_sector": by_sector, "lines_used": lines_used,
            "lender_lines_used": lender_lines, "lender_rows_unmatched": dict(sorted(lender_unmatched.items(), key=lambda kv: -kv[1])[:30]),
            "leads": len(leads), "worst_companies": worst[:25], "rows": rows}


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


def to_json(summary: dict) -> str:
    return json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False, indent=1) + "\n"


def render(summary: dict) -> str:
    c = summary["by_class"]
    lines = [f"tijori cross-check (pages of {summary['pages_day']}, read only):",
             f"companies                    {summary['companies']}",
             f"compared                     {summary['companies_compared']}",
             f"pairs compared               {summary['pairs']}"]
    lines += [f"  {name:26}{c[name]}" for name in CLASSES]
    lines += [f"leads (tijori and screener agree, memory differs)  {summary['leads']}"]
    if summary["skipped"]:
        lines.append("companies skipped: " + ", ".join(f"{k} {v}" for k, v in sorted(summary["skipped"].items())))
    return "\n".join(lines)


def _table(rows: list[dict], limit: int = 20) -> list[str]:
    out = ["| Symbol | Period | Metric | Ours | Tijori | Screener | Class | Note |", "|---|---|---|---|---|---|---|---|"]
    out += [f"| {r['symbol']} | {r['period']} | {r['metric']} | {_cell(r['memory_value'])} | {_cell(r['tijori_value'])} | "
            f"{_cell(r.get('screener_value'))} | {r['class']} | {r.get('note', '')} |" for r in rows[:limit]]
    return out + [""]


def to_markdown(summary: dict, date: str) -> str:
    """The short report, filled from the summary; the owner's reading is written by hand after it. It leads with the leads
    (tijori and screener agree, memory differs), then the sign and wrong_quarter pairs."""
    c = summary["by_class"]
    total = summary["pairs"] or 1
    rows = summary["rows"]
    out = [f"# Tijori cross-check, {date}", "",
           f"Read only: memory's exchange-file figures against the Tijori pages downloaded on {summary['pages_day']} (F189, "
           f"TODO 92). {summary['companies_compared']} of {summary['companies']} companies compared, {summary['pairs']} pairs "
           f"(quarters and years; revenue, profit, EPS), {c['match']} within the tolerance (0.011 Cr or 0.05% for money, 0.011 "
           f"for EPS), {summary['differences']} differences. Tijori copies the exchange filings and probably shares a vendor "
           f"with screener: a comparison only, never a correction on its own.", "",
           "## Leads: tijori and screener both differ from memory and agree with each other", "",
           f"{summary['leads']} pairs.", ""] + _table([r for r in rows if r.get("lead")], 30)
    out += ["## Sign differences", "", f"{c['sign']} pairs.", ""] + _table([r for r in rows if r["class"] == "sign"])
    out += ["## wrong_quarter", "", f"{c['wrong_quarter']} pairs.", ""] + _table([r for r in rows if r["class"] == "wrong_quarter"])
    out += ["## Counts by class", "", "| Class | Pairs | Share |", "|---|---|---|"]
    out += [f"| {name} | {c[name]} | {100 * c[name] / total:.1f}% |" for name in CLASSES]
    out += [""]
    if summary["skipped"]:
        out += ["Companies not compared: " + ", ".join(f"{k} {n}" for k, n in sorted(summary["skipped"].items())) + ".", ""]
    out += ["## Row names used", "", "| Row | Companies |", "|---|---|"]
    out += [f"| {k} | {n} |" for k, n in sorted(summary["lines_used"].items())]
    out += ["", "Lenders' revenue row (not confirmed before the first run): " + (
        ", ".join(f"{k} {n}" for k, n in sorted(summary["lender_lines_used"].items())) or "none found") + ".", ""]
    if summary["lender_rows_unmatched"]:
        out += ["Rows seen on lenders where no revenue row fitted: " + ", ".join(
            f"{k} ({n})" for k, n in summary["lender_rows_unmatched"].items()) + ".", ""]
    out += ["## By metric", "", "| Metric | " + " | ".join(CLASSES) + " |", "|---|" + "---|" * len(CLASSES)]
    out += [f"| {m} | " + " | ".join(str(row[k]) for k in CLASSES) + " |" for m, row in sorted(summary["by_metric"].items())]
    out += ["", "## Worst companies", "", "| Symbol | Sector | Wrong pairs | Pairs |", "|---|---|---|---|"]
    out += [f"| {w['symbol']} | {w['sector']} | {w['wrong_pairs']} | {w['pairs']} |" for w in summary["worst_companies"][:15]]
    out += ["", "Every non-match pair, with both values and memory's source id and filed date, is in the CSV artifact.", "",
            "## Reading (to be written)", "", "- Classes found, and which are Tijori's (not ours):", "- Fixes, one class each:", ""]
    return "\n".join(out)
