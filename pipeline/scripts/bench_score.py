"""Score a table-extraction engine against the filings' own XBRL (see bench_manifest.py).

An engine writes, per filing, the rows it read: {news_id: [{"page": n, "label": "...", "cells": ["..."]}]}.
For every figure the XBRL states, this asks three questions, strictest first:

  row+column  a row whose label is that line item carries the figure as its FIRST number - the
              current period, which is the column a card quotes. This is what wrong_column is about.
  row         the right row carries it in some column.
  anywhere    the number appears at all.

Figures are compared at the filing's declared unit (lakh, million, crore, or rupees), within rounding.
Leading serial and note numbers ("1.", "(a)", "14") are not cells: Schedule III puts a note column
between the label and the figures, and a parser that reads it as the first figure is wrong.

    python scripts/bench_score.py BENCH_DIR engine_output.json [--name NAME] [--detail]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LABELS = {
    "revenue": r"revenue from operations|income from operations|net sales|sales / income|revenue \(net\)",
    "other_income": r"other income",
    "total_income": r"total income|total revenue",
    "employee_cost": r"employee",
    "finance_cost": r"finance cost",
    "depreciation": r"depreciation",
    "other_expenses": r"other expenses",
    "total_expenses": r"total expenses|total expenditure",
    "pbt": r"before tax",
    "tax_expense": r"total tax|tax expense|tax \(expense\)|income tax expense",
    "pat": r"profit (?:/ \(loss\) |/\(loss\) |\(loss\) )?for the (?:period|year|quarter)|net profit|profit after tax",
    "eps": r"earnings per share|\beps\b|basic",
    "interest_earned": r"interest earned",
    "interest_expended": r"interest expended",
    "provisions": r"provisions \(other than tax\)|provisions and contingencies",
    "pre_provision_operating_profit": r"operating profit before provisions",
}
SCALES = (1, 10, 100, 1e7, 1e5)  # crore, million, lakh, rupees, thousand -> crore by division
_NUM = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?")


def parse(cell: str) -> float | None:
    raw = cell.strip().replace("−", "-")
    neg = raw.startswith("(") and raw.endswith(")")
    raw = raw.strip("()").replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    return -value if neg else value


def numbers(cells: list[str]) -> list[float]:
    out = []
    for cell in cells:
        for token in _NUM.findall(cell or ""):
            v = parse(token)
            if v is not None:
                out.append(v)
    # serial and note numbers before the figures: small whole numbers that lead the row
    while len(out) > 1 and out[0] == int(out[0]) and 0 < abs(out[0]) <= 40 and "." not in str(cells[0])[:8]:
        out.pop(0)
    return out


def matches(value: float, truth: float, unit) -> bool:
    for scale in ([unit] if unit else []) + [s for s in SCALES if s != unit]:
        crore = value / scale
        if abs(abs(crore) - abs(truth)) <= max(0.011, abs(truth) * 0.0006):
            return True
    return False


def score(manifest: list[dict], output: dict, detail: bool = False) -> dict:
    totals = {"figures": 0, "row+column": 0, "row": 0, "anywhere": 0}
    per_filing = []
    for item in manifest:
        rows = output.get(item["news_id"]) or []
        unit = item.get("declared_unit")
        got = {"row+column": 0, "row": 0, "anywhere": 0}
        misses = []
        for metric, truth in item["truth_crore"].items():
            totals["figures"] += 1
            pattern = re.compile(LABELS.get(metric, metric), re.I)
            labelled = [r for r in rows if pattern.search(r.get("label") or "")]
            first = any((ns := numbers(r.get("cells") or [])) and matches(ns[0], truth, unit) for r in labelled)
            on_row = any(matches(v, truth, unit) for r in labelled for v in numbers(r.get("cells") or []))
            anywhere = on_row or any(matches(v, truth, unit) for r in rows for v in numbers(r.get("cells") or []))
            for key, hit in (("row+column", first), ("row", on_row), ("anywhere", anywhere)):
                got[key] += hit
                totals[key] += hit
            if not first:
                misses.append(f"{metric}={truth:g}" + ("" if on_row else " (row)" if anywhere else " (absent)"))
        per_filing.append({"news_id": item["news_id"][:8], "company": item["company"][:22],
                           "figures": len(item["truth_crore"]), **got, "misses": misses})
    totals["per_filing"] = per_filing
    return totals


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bench")
    ap.add_argument("output")
    ap.add_argument("--name", default="")
    ap.add_argument("--detail", action="store_true")
    args = ap.parse_args()
    manifest = json.loads((Path(args.bench) / "manifest.json").read_text(encoding="utf-8"))
    output = json.loads(Path(args.output).read_text(encoding="utf-8"))
    result = score(manifest, output)
    n = result["figures"]
    print(f"{args.name or Path(args.output).stem}: {n} figures in {len(manifest)} filings")
    for key in ("row+column", "row", "anywhere"):
        print(f"  {key:11} {result[key]:4}  {result[key] / n:6.1%}")
    if args.detail:
        for f in result["per_filing"]:
            print(f"   {f['news_id']} {f['company']:22} {f['row+column']:2}/{f['figures']}  {', '.join(f['misses'])[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
