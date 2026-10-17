"""Score a table-extraction engine against the filings' own XBRL (see bench_manifest.py).

An engine writes, per filing, the rows it read: {news_id: [{"page": n, "label": "...", "cells": ["..."]}]}.
For every figure the XBRL states AND the PDF prints, this asks three questions, strictest first:

  row+column  a row whose label is that line item carries the figure as its FIRST number - the
              current period, which is the column a card quotes. This is what wrong_column is about.
  row         the right row carries it in some column.
  anywhere    the number appears at all, at the filing's unit.

Revised after an independent audit (2026-10-17, data/bench/reports/scorer-audit.md), which found the
first version misjudged in six ways. 33 of 228 figures were never printed in their PDF (an XBRL total of
rows printed separately, PBT before the share of associates, a press release in place of a statement):
they are marked `unprinted` in the manifest and not scored. A space inside a label ("Other expe nses")
blocked a match, which put pdfplumber at 44% when it places 63%. Label patterns missed banks' "Operating
expenses", "Profit/(Loss) for the period" and "Revenue from Operation". A sub-row ("Income") under its
heading ("Income from operations") and one- or two-letter slips in a text layer ("Tax exoense") are now
read. The tolerance accepted 4.1 for an EPS of 4.11 and tried every unit, so a figure could match at the
wrong scale, and compared absolute values, so a lost minus sign passed. Now: only the filing's unit, EPS
at face value to two decimals, the sign must agree on profit lines (not on a deducted cost, which is often
printed in brackets), and an amount must agree to the last digit printed. --loose restores the old
matching; with it this reproduces the audit's own re-scoring exactly (text-sorted 157/195, plumber-text
151, find-tables 28).

    python scripts/bench_score.py BENCH_DIR engine_output.json [--name NAME] [--detail] [--all] [--loose]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LABELS = {
    "revenue": r"revenue from operation|income from operations|net sales|sales / income|revenue \(net\)",
    "other_income": r"other income",
    "total_income": r"total income|total revenue",
    "employee_cost": r"employee",
    "finance_cost": r"finance cost",
    "depreciation": r"depreciation",
    "other_expenses": r"other expenses|^\W*\d*\W*operating expenses",   # banks: "5. Operating expenses (i)+(ii)"
    "total_expenses": r"total expenses|total expenditure",
    "pbt": r"before tax",
    "tax_expense": r"total tax|tax expense|tax \(expense\)|income tax expense",
    "pat": (r"profit (?:/ \(loss\) |/\(loss\) |\(loss\) )?for the (?:period|year|quarter)"
            r"|profit\s*/\s*\(loss\)\s*for the (?:period|year|quarter)|net profit|profit after tax|\bpat\b"),
    "eps": r"earnings? per (?:equity )?share|\beps\b|basic",
    "interest_earned": r"interest earned",
    "interest_expended": r"interest expended",
    "provisions": r"provisions \(other than tax\)|provisions and contingencies",
    "pre_provision_operating_profit": r"operating profit before provisions",
}
# The key phrase of each line item, for one- or two-letter slips in a text layer ("Tax exoense").
PHRASES = {"revenue": "revenue from operations", "other_income": "other income", "total_income": "total income",
           "employee_cost": "employee benefits", "finance_cost": "finance costs", "depreciation": "depreciation",
           "other_expenses": "other expenses", "total_expenses": "total expenses", "pbt": "before tax",
           "tax_expense": "tax expense", "pat": "for the period", "eps": "earnings per share"}
LOOSE_SCALES = (1, 10, 100, 1e7, 1e5)
# Lines where the sign is the information: a lost minus turns a loss into a profit.
SIGNED = {"pat", "pbt", "eps", "pre_provision_operating_profit"}
_NUM = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?")
_SQUEEZE = re.compile(r"[\s\x00-\x1f]+")


def parse(cell: str) -> tuple[float, int] | None:
    """A printed figure as (value, decimals printed); brackets mean negative."""
    raw = cell.strip().replace("−", "-")
    neg = raw.startswith("(") and raw.endswith(")")
    raw = raw.strip("()").replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    return (-value if neg else value), len(raw.partition(".")[2])


def figures(cells: list[str]) -> list[tuple[float, int]]:
    out = []
    for cell in cells:
        for token in _NUM.findall(cell or ""):
            v = parse(token)
            if v is not None:
                out.append(v)
    # serial and note numbers before the figures: small whole numbers that lead the row
    while len(out) > 1 and out[0][1] == 0 and 0 < abs(out[0][0]) <= 40 and "." not in str(cells[0])[:8]:
        out.pop(0)
    return out


def numbers(cells: list[str]) -> list[float]:
    return [v for v, _ in figures(cells)]


def matches(value: float, truth: float, unit, metric: str = "", decimals: int = 2, loose: bool = False) -> bool:
    if loose:
        return any(abs(abs(value / s) - abs(truth)) <= max(0.011, abs(truth) * 0.0006)
                   for s in ([unit] if unit else []) + [s for s in LOOSE_SCALES if s != unit])
    scale = 1 if metric == "eps" else (unit or 1)
    if metric not in SIGNED:
        # a deducted cost is often printed in brackets ("Less: Finance costs (41.84)"): a convention, not a sign
        value, truth = abs(value), abs(truth)
    if metric == "eps":
        return abs(value - truth) <= 0.0051   # per-share figures are printed to two decimals
    # agree to the last digit printed: "2,060" in million is 206.0 crore against an XBRL 206.07
    return abs(value / scale - truth) <= max(10 ** -decimals / scale + 1e-9, 0.006)


def _lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _trigrams(s: str) -> set[str]:
    return {s[i:i + 3] for i in range(len(s) - 2)}


_PHRASE_GRAMS: dict[str, set[str]] = {}


def _near(label: str, phrase: str, k: int = 2) -> bool:
    s, n = " ".join(label.lower().split()), len(phrase)
    if n < 9:
        return False
    # A window within k edits of the phrase keeps at least (trigrams - 3k) of its trigrams intact (the
    # q-gram lemma), so a label sharing fewer cannot match: a lossless filter that skips nearly every row.
    grams = _PHRASE_GRAMS.setdefault(phrase, _trigrams(phrase))
    if len(grams & _trigrams(s)) < len(grams) - 3 * k:
        return False
    return any(_lev(s[i:i + m], phrase) <= k for m in (n - 1, n, n + 1) for i in range(max(1, len(s) - m + 1)))


_COMPILED: dict[str, tuple[re.Pattern, re.Pattern]] = {}


def label_is(metric: str, label: str, heading: str = "") -> bool:
    if metric not in _COMPILED:
        pattern = LABELS.get(metric, metric)
        _COMPILED[metric] = (re.compile(pattern, re.I), re.compile(pattern.replace(" ", ""), re.I))
    plain, squeezed = _COMPILED[metric]
    for candidate in [label] + ([f"{heading} {label}"] if heading and re.search(r"[A-Za-z]{3}", label) else []):
        if plain.search(candidate) or squeezed.search(_SQUEEZE.sub("", candidate)):
            return True
        if metric in PHRASES and _near(candidate, PHRASES[metric]):
            return True
    return False


def score(manifest: list[dict], output: dict, loose: bool = False) -> dict:
    totals = {"figures": 0, "row+column": 0, "row": 0, "anywhere": 0}
    per_filing = []
    for item in manifest:
        rows = output.get(item["news_id"]) or []
        unit = item.get("unit_checked", item.get("declared_unit"))
        headings, last = [], ""
        for i, r in enumerate(rows):   # the label-only row just above, on the same page
            headings.append(last if i and rows[i - 1].get("page") == r.get("page") else "")
            if not numbers(r.get("cells") or []) and (r.get("label") or "").strip():
                last = r["label"]
        got = {"row+column": 0, "row": 0, "anywhere": 0}
        misses = []
        skip = item.get("unprinted") or {}
        for metric, truth in item["truth_crore"].items():
            if metric in skip:
                continue
            totals["figures"] += 1

            def hit(v, metric=metric, truth=truth):
                return matches(v[0], truth, unit, metric, v[1], loose)
            labelled = [r for r, h in zip(rows, headings)
                        if r.get("cells") and label_is(metric, r.get("label") or "", h)]
            first = any((fs := figures(r.get("cells") or [])) and hit(fs[0]) for r in labelled)
            on_row = first or any(hit(v) for r in labelled for v in figures(r.get("cells") or []))
            anywhere = on_row or any(hit(v) for r in rows for v in figures(r.get("cells") or []))
            for key, h in (("row+column", first), ("row", on_row), ("anywhere", anywhere)):
                got[key] += h
                totals[key] += h
            if not first:
                misses.append(f"{metric}={truth:g}" + (" (on its row, later column)" if on_row else
                                                        " (on another row)" if anywhere else " (not read)"))
        per_filing.append({"news_id": item["news_id"][:8], "company": item["company"][:22],
                           "figures": len(item["truth_crore"]) - len(skip), **got, "misses": misses})
    totals["per_filing"] = per_filing
    return totals


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bench")
    ap.add_argument("output")
    ap.add_argument("--name", default="")
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--all", action="store_true", help="count filings the output does not cover as misses")
    ap.add_argument("--loose", action="store_true", help="the matching before the audit, to reproduce old numbers")
    args = ap.parse_args()
    manifest = json.loads((Path(args.bench) / "manifest.json").read_text(encoding="utf-8"))
    output = json.loads(Path(args.output).read_text(encoding="utf-8"))
    # Score what the engine covers, and say so: counting a filing it never ran on as zero made RapidOCR
    # look like 9% when it had read the three scanned filings it was given.
    covered = [m for m in manifest if m["news_id"] in output]
    scored = manifest if args.all else covered
    result = score(scored, output, loose=args.loose)
    n = result["figures"]
    print(f"{args.name or Path(args.output).stem}: {n} printed figures in {len(scored)} filings"
          + (f" (covers {len(covered)} of {len(manifest)} - partial)" if len(covered) < len(manifest) else "")
          + (" [loose matching]" if args.loose else ""))
    for key in ("row+column", "row", "anywhere"):
        print(f"  {key:11} {result[key]:4}  {result[key] / max(1, n):6.1%}")
    if args.detail:
        for f in result["per_filing"]:
            print(f"   {f['news_id']} {f['company']:22} {f['row+column']:2}/{f['figures']}  {', '.join(f['misses'])[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
