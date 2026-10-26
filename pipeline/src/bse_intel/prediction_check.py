"""Stored targets judged in two different units (TODO item 84): read only, no AI, no write.

APL Apollo's "10 lakh tonnes" Q2FY27 volume target was marked MET at 963,143 t (memory recall audit, 26 Oct 2026): the
check compared 963,143 with 10. ``dossier.comparable_target`` now converts a target's scale word and leaves a target
50x or more from its figure, or one whose words name another measure, UNCHECKED; this lists the stored verdicts the next merge of each company will withdraw, and
the per-share units on figures that are not per share (``models.FinancialMetric``), so the change is counted first."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .dossier import comparable_target, other_measure
from .models import _PER_OTHER

READ_WORKERS = 8


def check(dossier: dict | None) -> list[dict]:
    rows = []
    for p in (dossier or {}).get("predictions", []):
        if p.get("status") in ("MET", "MISSED") and p.get("actual") is not None \
                and (other_measure(p.get("kpi"), p.get("metric"))
                     or comparable_target(p, {"value": p["actual"], "unit": p.get("actual_unit")}) is None):
            rows.append({"kind": "verdict_withdrawn", "metric": p.get("metric"), "period": p.get("period"),
                         "detail": f"{p.get('status')}: target {p.get('comparison')} {p.get('value')} vs actual {p.get('actual')} "
                                   f"({str(p.get('kpi') or '')[:80]})"})
    for m in (dossier or {}).get("financial_metrics", []):
        if str(m.get("unit") or "").upper() == "INR_PER_SHARE" and _PER_OTHER.search(m.get("metric") or ""):
            rows.append({"kind": "per_share_unit", "metric": m.get("metric"), "period": m.get("period"),
                         "detail": f"{m.get('value')} stored as INR_PER_SHARE"})
    return rows


def survey(sink, scrips: list[str], symbols: dict[str, str] | None = None, workers: int = READ_WORKERS) -> dict:
    def one(scrip: str) -> list[dict]:
        return check(sink.get_dossier(scrip))

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(one, scrips))
    symbols = symbols or {}
    rows = [{"scrip": s, "symbol": symbols.get(s, ""), **r} for s, rs in zip(scrips, results) for r in rs]
    kinds = {k: sum(r["kind"] == k for r in rows) for k in ("verdict_withdrawn", "per_share_unit")}
    return {"companies_checked": len(scrips), "companies_affected": len({r["scrip"] for r in rows}), "by_kind": kinds, "rows": rows}


def render(report: dict) -> str:
    lines = [f"Prediction units: {report['companies_checked']} companies checked, {report['companies_affected']} affected; "
             f"verdicts to withdraw {report['by_kind']['verdict_withdrawn']}, per-share units on other figures "
             f"{report['by_kind']['per_share_unit']}"]
    for r in report["rows"]:
        lines.append(f"  {r['symbol'] or r['scrip']:12} {r['kind']:17} {r['metric']} {r['period']}: {r['detail']}")
    return "\n".join(lines)
