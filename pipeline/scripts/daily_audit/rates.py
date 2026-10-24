"""The daily audit's rates with their uncertainty, pooled over days (no AI, no network).

One day's audit is 60-75 cards: a WRONG share of 23% then has a 95% interval of about +/-10 points, so a day-to-day
move from 15% to 23% is within noise and one day cannot say whether a fix worked (code survey, 24 Oct 2026). This
prints each day, then the last WINDOW days pooled, with Wilson 95% intervals, short against long prompt, and the
pruned points the reviewers found true. A fix is judged by its on/off over stored cards; the audit rate is judged
over pooled days, and a change is real only when the intervals of the two periods do not overlap.

    python -I scripts/daily_audit/rates.py [--dir ../docs/audit/live] [--window 3] [--since 2026-10-21]
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

VERDICTS = ("RIGHT", "MINOR", "WRONG")
Z = 1.96


def wilson(hits: int, n: int) -> tuple[float, float]:
    """The 95% Wilson interval of hits/n, as fractions."""
    if n == 0:
        return 0.0, 0.0
    p = hits / n
    centre = (p + Z * Z / (2 * n)) / (1 + Z * Z / n)
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / (1 + Z * Z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def rate(hits: int, n: int) -> str:
    low, high = wilson(hits, n)
    return f"{hits / n:.0%} ({low:.0%}-{high:.0%})" if n else "-"


def load(folder: Path, since: str = "") -> dict[str, list[dict]]:
    """Each day's verdicts by date, from <date>-audit.json."""
    days = {}
    for path in sorted(folder.glob("*-audit.json")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})-audit\.json$", path.name)
        if not m or m.group(1) < since:
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        days[m.group(1)] = [r for r in rows if str(r.get("verdict", "")).upper() in VERDICTS]
    return days


def summary(rows: list[dict]) -> dict:
    counts = Counter(str(r["verdict"]).upper() for r in rows)
    variants = {v: Counter(str(r["verdict"]).upper() for r in rows if r.get("prompt_variant") == v) for v in ("short", "long")}
    pruned_true = sum(int(r.get("pruned_points_true") or 0) if not isinstance(r.get("pruned_points_true"), list)
                      else len(r["pruned_points_true"]) for r in rows)
    pruned_false = sum(int(r.get("pruned_points_false") or 0) if not isinstance(r.get("pruned_points_false"), list)
                       else len(r["pruned_points_false"]) for r in rows)
    return {"n": len(rows), "counts": counts, "variants": variants, "pruned": (pruned_true, pruned_false)}


def line(label: str, s: dict) -> str:
    n, c = s["n"], s["counts"]
    short, long_ = s["variants"]["short"], s["variants"]["long"]
    pt, pf = s["pruned"]
    return (f"| {label} | {n} | {rate(c['RIGHT'], n)} | {rate(c['RIGHT'] + c['MINOR'], n)} | {rate(c['WRONG'], n)} | "
            f"{rate(short['WRONG'], sum(short.values()))} | {rate(long_['WRONG'], sum(long_.values()))} | "
            f"{f'{pt} of {pt + pf}' if pt + pf else '-'} |")


def report(days: dict[str, list[dict]], window: int) -> str:
    out = ["| Days | Cards | Right | Right or minor | WRONG | WRONG, short prompt | WRONG, long prompt | Pruned points true |",
           "|---|---|---|---|---|---|---|---|"]
    names = list(days)
    for day in names:
        out.append(line(day, summary(days[day])))
    for end in range(window, len(names) + 1, window) if len(names) >= window else ():
        span = names[end - window:end]
        out.append(line(f"{span[0]} to {span[-1]} (pooled)", summary([r for d in span for r in days[d]])))
    if names:
        out.append(line("all", summary([r for d in names for r in days[d]])))
    total = sum(len(v) for v in days.values())
    if total:
        low, high = wilson(round(total * 0.05), total)
        out += ["", f"With {total} cards, a true 5% WRONG rate would read anywhere in {low:.0%}-{high:.0%}: the go-live bar "
                    "(WRONG <= 5%) is shown met only when the pooled WRONG interval's top is at or below 5%."]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parents[3] / "docs" / "audit" / "live"))
    ap.add_argument("--window", type=int, default=3, help="days pooled together")
    ap.add_argument("--since", default="", help="first day (YYYY-MM-DD)")
    args = ap.parse_args()
    print(report(load(Path(args.dir), args.since), args.window))


if __name__ == "__main__":
    main()
