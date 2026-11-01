"""Company memory summary for the directory, the Inflection Radar and the overdue-promises panel
(blueprint §13 View 3 and View 4, Module 44).

Written on the company row with each card (and each XBRL shareholding update), from the company's
full dossier, so the website answers "which companies are inflecting" and "which promises are
overdue" with one indexed read instead of opening every dossier. Dates are stored, not verdicts:
a promise becomes overdue, and a trigger leaves the 90-day radar window, as the calendar moves,
without any rewrite.

Inflection triggers (each kind counts once; the radar shows companies with 3 or more in 90 days):
* CAPEX_COMMISSIONED: a capex project on record reached COMPLETED, or a capacity / plant promise
  was delivered.
* VOLUME_STREAK: two or more consecutive months of monthly volume or sales up more than 20% YoY.
* MARGIN_EXPANSION: quarterly EBITDA margin up 150 bps or more on the year-ago quarter.
* DELEVERAGING: gross debt down 15% or more from the previous balance sheet.
* SMART_MONEY: promoter + FII + DII holding up 1 percentage point or more quarter on quarter.
"""

from __future__ import annotations

import re

from .call_summary import summarize_calls
from .dossier import _deal_history, period_kind
from .periods import due_date, prior_year_period
from .quality import roiic
from .scoring import calibration

OPEN = ("OPEN", "ON_TRACK", "DELAYED", "REVISED")
MAX_PROMISES = 15
MAX_TRIGGERS = 12
CAPACITY_WORDS = re.compile(r"commission|capacity|plant|unit|line|facility|brownfield|greenfield|expansion", re.I)
VOLUME_METRICS = ("volume", "sales_volume", "dispatch", "production", "units", "sales")


def _status(g: dict) -> str:
    history = g.get("status_history") or []
    return history[-1]["status"] if history else g.get("status") or "OPEN"


def _day(ts: str | None) -> str | None:
    return ts[:10] if ts else None


def open_promises(dossier: dict) -> list[dict]:
    out = []
    from .dossier import judged_on, third_party_view
    from .periods import due_date

    for g in dossier.get("guidance", []):
        if _status(g) not in OPEN or third_party_view(f"{g.get('statement', '')} {g.get('target') or ''}"):
            continue
        # the deadline is read again from its words: memory written before ranges were read holds the early end
        fy_end = dossier.get("fy_end_month")
        deadline = due_date(g.get("due"), fy_end)
        due_iso = deadline.isoformat() if deadline else g.get("due_date")
        given = _day(g.get("given_on"))
        # overdue only once the period's results are due, not at its end (audit 137, B1; periods.results_due, O12)
        judged = judged_on(g.get("due"), due_iso, fy_end) if due_iso else None
        if judged and given and judged < given:
            due_iso = judged = None   # judged before the day it was said: a misread period (audit 137, B3)
        out.append({"id": g["id"], "statement": g["statement"][:200], "due": g.get("due"),
                    "due_date": due_iso, "overdue_from": judged, "given_on": given,
                    "status": _status(g), "source_news_id": g.get("source_news_id")})
    out.sort(key=lambda p: (p["due_date"] or "9999", p["given_on"] or ""))
    return out[:MAX_PROMISES]


def _metric(dossier: dict, names: tuple[str, ...]) -> dict[str, dict]:
    rows = {}
    for m in dossier.get("financial_metrics", []):
        if m.get("metric") in names and m.get("value") is not None:
            rows.setdefault(m["period"], m)
    return rows


def _margin(dossier: dict) -> dict[str, tuple[float, str]]:
    """Quarterly EBITDA margin (stated, else EBITDA / revenue) with when it became known."""
    stated = _metric(dossier, ("ebitda_margin", "opm", "operating_margin"))
    ebitda = _metric(dossier, ("ebitda", "operating_profit"))
    revenue = _metric(dossier, ("revenue", "revenue_from_operations", "total_revenue", "net_sales"))
    out = {}
    for period in set(stated) | set(ebitda):
        if not period.startswith("Q"):
            continue
        if period in stated:
            out[period] = (float(stated[period]["value"]), stated[period].get("as_of") or "")
        elif period in revenue and revenue[period]["value"]:
            out[period] = (ebitda[period]["value"] / revenue[period]["value"] * 100, ebitda[period].get("as_of") or "")
    return out


def triggers(dossier: dict) -> list[dict]:
    found: list[dict] = []

    for deal in dossier.get("deals", []):
        if deal.get("kind") != "CAPEX":
            continue
        done = [h for h in _deal_history(deal) if h.get("stage") == "COMPLETED"]
        if done:
            found.append({"kind": "CAPEX_COMMISSIONED", "date": _day(done[0]["as_of"]),
                          "text": f"Capex completed ({deal.get('expansion') or deal.get('segment') or 'project'})"})
    for g in dossier.get("guidance", []):
        delivered = [h for h in g.get("status_history", []) if h["status"] == "DELIVERED"]
        if delivered and CAPACITY_WORDS.search(g["statement"]):
            found.append({"kind": "CAPEX_COMMISSIONED", "date": _day(delivered[-1]["as_of"]),
                          "text": f"Delivered: {g['statement'][:100]}"})

    months: dict[str, list[dict]] = {}
    for m in dossier.get("financial_metrics", []):
        if period_kind(m["period"]) == "M" and m.get("yoy_pct") is not None \
                and any(m["metric"].startswith(v) for v in VOLUME_METRICS):
            months.setdefault(m["metric"], []).append(m)
    for metric, rows in months.items():
        rows = sorted(rows, key=lambda r: due_date(r["period"]) or due_date("JAN-2000"))
        streak = 0
        for r in rows:
            streak = streak + 1 if r["yoy_pct"] > 20 else 0
            if streak >= 2:
                found.append({"kind": "VOLUME_STREAK", "date": _day(r.get("as_of")),
                              "text": f"{metric} +{r['yoy_pct']:.0f}% YoY in {r['period']} ({streak} months above 20%)"})

    margins = _margin(dossier)
    for period, (value, as_of) in margins.items():
        before = margins.get(prior_year_period(period) or "")
        if before and (value - before[0]) * 100 >= 150:
            found.append({"kind": "MARGIN_EXPANSION", "date": _day(as_of),
                          "text": f"EBITDA margin {value:.1f}% in {period}, +{(value - before[0]) * 100:.0f} bps YoY"})

    sheets = [s for s in dossier.get("balance_sheet", []) if s.get("gross_debt_cr") is not None]
    for prev, cur in zip(sheets, sheets[1:]):
        if prev["gross_debt_cr"] > 0 and cur["gross_debt_cr"] <= prev["gross_debt_cr"] * 0.85:
            cut = (1 - cur["gross_debt_cr"] / prev["gross_debt_cr"]) * 100
            found.append({"kind": "DELEVERAGING", "date": _day(cur["as_of"]),
                          "text": f"Gross debt down {cut:.0f}% to ₹{cur['gross_debt_cr']:g} Cr"})

    owners = [o for o in dossier.get("ownership", [])]
    for prev, cur in zip(owners, owners[1:]):
        held = [sum(o.get(k) or 0 for k in ("promoter_pct", "fii_pct", "dii_pct")) for o in (prev, cur)]
        if all(held) and held[1] - held[0] >= 1.0:
            found.append({"kind": "SMART_MONEY", "date": _day(cur.get("as_of")),
                          "text": f"Promoter + FII + DII up {held[1] - held[0]:.1f} pp in {cur['period']}"})

    latest: dict[str, dict] = {}
    for t in found:
        if t["date"] and (t["kind"] not in latest or t["date"] > latest[t["kind"]]["date"]):
            latest[t["kind"]] = t
    return sorted(latest.values(), key=lambda t: t["date"], reverse=True)[:MAX_TRIGGERS]


def _latest(dossier: dict, names: tuple[str, ...]) -> dict | None:
    rows = [m for m in _metric(dossier, names).values() if m["period"].startswith("Q") and due_date(m["period"])]
    if not rows:
        return None
    m = max(rows, key=lambda r: due_date(r["period"]))
    return {"period": m["period"], "value": m["value"]}


def _statement_latest(dossier: dict, names: tuple[str, ...]) -> dict | None:
    """The latest quarter's screener row from the stored statements (one source for the site, owner 31 Oct 2026), on the main
    basis: consolidated when present, else standalone. None when there are no statements quarters entries."""
    rows = [e for e in dossier.get("statements") or [] if e.get("table") == "quarters" and e.get("rows") and due_date(e.get("period"))]
    for basis in ("CONSOLIDATED", "STANDALONE"):
        mine = [e for e in rows if e.get("basis") == basis and any(isinstance(e["rows"].get(n), (int, float)) for n in names)]
        if mine:
            e = max(mine, key=lambda r: due_date(r["period"]))
            return {"period": e["period"], "value": next(e["rows"][n] for n in names if isinstance(e["rows"].get(n), (int, float)))}
    return None


def summarize(dossier: dict) -> dict:
    promises = open_promises(dossier)
    found = triggers(dossier)
    sheets = [s for s in dossier.get("balance_sheet", []) if s.get("gross_debt_cr") is not None]
    active_capex = sum(1 for d in dossier.get("deals", [])
                       if d.get("kind") == "CAPEX" and d.get("stage") not in ("COMPLETED", "CANCELLED"))
    summary = {
        "open_promises": promises,
        "triggers": found,
        "active_capex": active_capex,
        "revenue": _statement_latest(dossier, ("Sales", "Revenue"))
        or _latest(dossier, ("revenue", "revenue_from_operations", "total_revenue", "net_sales")),
        "ebitda": _statement_latest(dossier, ("Operating Profit", "Financing Profit")) or _latest(dossier, ("ebitda", "operating_profit")),
        "gross_debt_cr": sheets[-1]["gross_debt_cr"] if sheets else None,
        "calibration": (calibration(dossier) or {}).get("rule"),
        "roiic": roiic(dossier),
        "calls": summarize_calls(dossier),   # earnings calls by quarter, key takeaways only (O13)
    }
    return {
        "memory_summary_json": summary,
        "earliest_open_due": min((p["overdue_from"] for p in promises if p["overdue_from"]), default=None),
        "inflection_last_at": found[0]["date"] if found else None,
    }
