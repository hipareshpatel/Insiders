"""F167: restated figures in memory, read only (no AI, no write).

A company often restates an earlier quarter in a later results file (the comparative columns: after a merger, a discontinued
business, an accounting change). Memory keeps the quarter's own file and the later file's comparative as sources of one
entry (``dossier._metric_entry``): ``value`` is the latest, ``first_filed`` the figure as first filed, ``restated`` true
when they differ beyond rounding. This counts those quarters across memory by the size of the change, with examples, and
how many later quarters' stored YoY was worked from the first-filed base where a restated one exists.

Old memory has restated values only after the seed-memory reload (the field is written at merge time)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .dossier import FLOW_METRICS
from .periods import prior_year_period

BUCKETS = ((1, "under 1%"), (5, "1-5%"), (20, "5-20%"), (float("inf"), "over 20%"))
READ_WORKERS = 8


def bucket(pct: float) -> str:
    return next(label for limit, label in BUCKETS if pct < limit)


def check(dossier: dict | None) -> dict:
    """One company's restated quarters and the YoY bases of the quarters after them."""
    out = {"quarters": 0, "restated": [], "yoy_first_base": 0, "yoy_restated_base": 0}
    entries = {(e["metric"], e["period"]): e for e in (dossier or {}).get("financial_metrics", [])
               if e.get("metric") in FLOW_METRICS and str(e.get("period", "")).startswith("Q")}
    out["quarters"] = len(entries)
    for (metric, period), e in entries.items():
        if e.get("restated") and e.get("first_filed"):
            pct = abs(e["value"] - e["first_filed"]) / abs(e["first_filed"]) * 100
            out["restated"].append({"metric": metric, "period": period, "first_filed": e["first_filed"],
                                    "restated": e["value"], "change_pct": round(pct, 1), "in": e.get("restated_in")})
    for (metric, period), e in entries.items():
        base = entries.get((metric, prior_year_period(period) or ""))
        if not (base and base.get("restated") and base.get("first_filed")) or e.get("yoy_pct") is None or not e.get("value"):
            continue
        if e["yoy_pct"] == -100:
            continue
        implied = e["value"] / (1 + e["yoy_pct"] / 100)
        if abs(implied - base["first_filed"]) < abs(implied - base["value"]):
            out["yoy_first_base"] += 1
        else:
            out["yoy_restated_base"] += 1
    return out


def survey(sink, scrips: list[str], workers: int = READ_WORKERS) -> dict:
    def one(scrip: str) -> dict:
        return check(sink.get_dossier(scrip))

    if workers <= 1 or len(scrips) <= 1:
        results = [one(s) for s in scrips]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, scrips))
    companies = dict(zip(scrips, results))
    sizes: dict[str, int] = {label: 0 for _, label in BUCKETS}
    rows = []
    for scrip, r in companies.items():
        for row in r["restated"]:
            sizes[bucket(row["change_pct"])] += 1
            rows.append({"scrip": scrip, **row})
    rows.sort(key=lambda r: -r["change_pct"])
    return {"companies_checked": len(scrips),
            "companies_with_restated": sum(1 for r in companies.values() if r["restated"]),
            "quarter_figures": sum(r["quarters"] for r in companies.values()),
            "restated_figures": len(rows), "by_size": sizes,
            "yoy_first_filed_base": sum(r["yoy_first_base"] for r in companies.values()),
            "yoy_restated_base": sum(r["yoy_restated_base"] for r in companies.values()),
            "rows": rows}


def render(report: dict, examples: int = 15) -> str:
    lines = [f"restated figures in memory: {report['restated_figures']} of {report['quarter_figures']} quarter flow figures, "
             f"{report['companies_with_restated']} of {report['companies_checked']} companies",
             "by size of the change from first filed:"]
    lines += [f"  {label:10} {n}" for label, n in report["by_size"].items()]
    lines.append(f"stored YoY worked from the first-filed base where a restated one exists: {report['yoy_first_filed_base']}; "
                 f"from the restated base: {report['yoy_restated_base']}")
    lines.append("(old memory gets restated values only after the seed-memory reload; cards' own year-ago figures come from "
                 "their file's comparative columns, so they are not in these counts)")
    lines.append("largest changes:")
    for r in report["rows"][:examples]:
        lines.append(f"  {r['scrip']} {r['metric']} {r['period']}: first filed {r['first_filed']:g}, restated {r['restated']:g} "
                     f"({r['change_pct']:+g}%, in {r['in']})")
    return "\n".join(lines)
