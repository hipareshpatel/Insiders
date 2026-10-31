"""Two screener-rows runs compared row by row (TODO 149, owner 31 Oct 2026: a weekly check, so a rule that breaks when NSE
changes its files is seen within a week). Reads the two rows.csv files the runs upload; no network, no write but the report.

A pair is the same (table, company, basis, period, row) in both runs. It *broke* when it was exact before and is not now
(apart, or no figure: a reader that stopped reading shows here too); it *mended* the other way. The report counts both by
table and row, with examples, and gives each run's exact share of compared pairs from FY23 (the owner's cut-off). Pairs only
one run has (a new company, a new quarter) are counted apart, never as broken or mended.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter, defaultdict

FROM_FY = 23
EXAMPLES = 5


def _rows(text: str) -> dict[tuple, dict]:
    return {(r["table"], r["company"], r["basis"], r["period"], r["row"]): r for r in csv.DictReader(io.StringIO(text))}


def _fy(period: str) -> int | None:
    m = re.search(r"FY(\d\d)", period or "")
    return int(m[1]) if m else None


def exact_shares(rows: dict[tuple, dict]) -> dict[str, tuple[int, int]]:
    """table -> (exact, compared) over the pairs from FY23 that have a figure on both sides."""
    out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for (table, *_), r in rows.items():
        fy = _fy(r["period"])
        if fy is None or fy < FROM_FY or r["status"] not in ("ok", "apart"):
            continue
        out[table][1] += 1
        out[table][0] += r["status"] == "ok"
    return {t: (v[0], v[1]) for t, v in out.items()}


def compare(prev_csv: str, curr_csv: str) -> dict:
    prev, curr = _rows(prev_csv), _rows(curr_csv)
    broke, mended = Counter(), Counter()
    examples: dict[tuple, list] = defaultdict(list)
    for key, r in curr.items():
        before = prev.get(key)
        if before is None:
            continue
        was, now = before["status"] == "ok", r["status"] == "ok"
        if was == now:
            continue
        cls = (key[0], key[4])
        (broke if was else mended)[cls] += 1
        if was and len(examples[cls]) < EXAMPLES:
            examples[cls].append(f"{key[1]} {key[2][:4].lower()} {key[3]}: {before['ours']} -> {r['ours'] or r['status']} "
                                 f"(screener {r['screener']})")
    return {"broke": broke, "mended": mended, "examples": examples, "new_pairs": len(curr.keys() - prev.keys()),
            "gone_pairs": len(prev.keys() - curr.keys()), "shares": (exact_shares(prev), exact_shares(curr))}


def worse_classes(result: dict, min_net: int = 5) -> list[tuple[tuple, int, int]]:
    """(table, row), broken, mended for every class that lost at least ``min_net`` exact pairs net: what the weekly check flags."""
    out = []
    for cls, n in result["broke"].items():
        net = n - result["mended"].get(cls, 0)
        if net >= min_net:
            out.append((cls, n, result["mended"].get(cls, 0)))
    return sorted(out, key=lambda x: x[2] - x[1])


def render(result: dict, prev_name: str = "previous run", curr_name: str = "this run") -> str:
    before, after = result["shares"]
    lines = [f"# Screener rows: {curr_name} against {prev_name}", "",
             f"Exact share from FY{FROM_FY} (pairs with a figure on both sides):", "",
             "| Table | Before | Now |", "|---|---|---|"]
    for table in ("quarters", "annual", "balance", "cash_flow"):
        b, a = before.get(table, (0, 0)), after.get(table, (0, 0))
        fmt = lambda x: f"{x[0] / x[1] * 100:.1f}% of {x[1]}" if x[1] else "-"
        lines.append(f"| {table} | {fmt(b)} | {fmt(a)} |")
    total_b, total_m = sum(result["broke"].values()), sum(result["mended"].values())
    lines += ["", f"Pairs broken {total_b}, mended {total_m}; new pairs {result['new_pairs']}, gone {result['gone_pairs']}.", ""]
    flagged = worse_classes(result)
    lines.append("**Classes that lost 5 or more exact pairs net:** " + ("none." if not flagged else ""))
    for (table, row), b, m in flagged:
        lines.append(f"- {table}: {row}: broke {b}, mended {m}. e.g. " + "; ".join(result["examples"][(table, row)]))
    lines += ["", "| Class | Broke | Mended |", "|---|---|---|"]
    for cls in sorted(set(result["broke"]) | set(result["mended"]), key=lambda c: -(result["broke"][c] + result["mended"][c]))[:30]:
        lines.append(f"| {cls[0]}: {cls[1]} | {result['broke'][cls]} | {result['mended'][cls]} |")
    return "\n".join(lines) + "\n"
