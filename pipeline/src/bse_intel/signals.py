"""Institutional alpha signals, computed deterministically.

The model extracts facts; these checks do the arithmetic, so a signal can
never be a plausible-sounding guess:

* PROMISE_DELIVERED / GUIDANCE_BREACH: guidance from memory that this filing
  delivered on, missed or delayed, plus open guidance whose deadline passed.
* WATCH_RESOLVED: a "track next" item from an earlier card (KPI to verify,
  pending approval) that this filing resolved.
* DILUTION: equity dilution, discount to market, and price-to-book of an
  issue, from the shares and prices the filing states.
* WORKING_CAPITAL_STRAIN: receivables or inventory growing much faster than
  revenue over the same year-on-year period.
* SCALE: an order, fundraise, capex plan or acquisition put in proportion:
  against the last quarter's and last year's revenue, market cap or net worth.
* ORDER_FLOW: where an order sits among the company's earlier orders on record
  (how many since when, the total, and whether it is the largest).
* METRIC_SHIFT: a generic scan over *every* metric this filing reported,
  whatever its name: large year-on-year or sequential moves, and trend
  reversals, ranked by size. Open-ended judgement on top of this comes from
  the analyst model's ``notable_changes``.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date

from .dossier import deal_state, reported_by
from .models import Filing, Pass2Output
from .periods import due_date, prior_year_period

STRAIN_GAP_PP = 15.0      # receivable/inventory growth minus revenue growth, percentage points
MAX_OVERDUE_SIGNALS = 2

REVENUE = ("revenue", "revenue_from_operations", "total_revenue", "net_sales", "sales", "total_income")
WORKING_CAPITAL = {
    "trade_receivables": "Receivables",
    "receivables": "Receivables",
    "debtors": "Receivables",
    "inventories": "Inventory",
    "inventory": "Inventory",
}


@dataclass
class Signal:
    type: str        # PROMISE_DELIVERED | GUIDANCE_BREACH | WATCH_RESOLVED | DILUTION | SCALE | ORDER_FLOW | WORKING_CAPITAL_STRAIN | METRIC_SHIFT
    severity: str    # POSITIVE | WARNING | INFO
    text: str
    ref: str | None = None


def compute(before: dict | None, after: dict, output: Pass2Output, filing: Filing, company: dict | None) -> list[dict]:
    """Signals from memory as it stood at the filing: ``before`` excludes the filing, ``after`` includes
    it, and neither may hold later facts (pass them through ``dossier_as_of``). ``company`` carries market
    data as of the filing when a stored series has it (``prices.point_in_time``); today's prices are
    used only for recent filings."""
    company = priced_for(company, filing)
    signals: list[Signal] = []
    signals += _promises(before, after, output, filing)
    signals += _dilution(after, output, company)
    signals += _scale(before, output, company)
    signals += _order_flow(before, output, filing)
    strain = _working_capital(after, filing)
    signals += strain
    signals += _metric_shifts(after, filing, skip={"trade_receivables", "receivables", "debtors", "inventories", "inventory"} if strain else set())
    signals += _predictions(after, filing)
    signals += _ownership(after, filing)
    signals += _auditor(after, filing)
    signals += _volumes(after, filing)
    from .quality import festive_signals, quality_signals, rating_signals, roiic_signals

    return [asdict(s) for s in signals] + quality_signals(after, filing.news_id) \
        + rating_signals(before, after, filing.news_id) + festive_signals(after, filing.news_id) + roiic_signals(after, filing.news_id)


def _predictions(after: dict, filing: Filing) -> list[Signal]:
    """Loop 2: a number management or the analyst predicted, now checked against the actual."""
    out = []
    for p in after.get("predictions", []):
        if p.get("resolved_by") != filing.news_id:
            continue
        met = p["status"] == "MET"
        out.append(Signal("PREDICTION_RESOLVED", "POSITIVE" if met else "WARNING",
                          f"{'Met' if met else 'Missed'}: \"{p['kpi']}\" ({metric_label(p['metric'])} {p['period']} target "
                          f"{p['comparison']} {p['value']:g}; actual {p['actual']:g}, set {p['created_on'][:10]}).", p["id"]))
    return out


def _ownership(after: dict, filing: Filing) -> list[Signal]:
    """Blueprint module 47: smart money accumulating vs retail distribution, and pledges."""
    rows = after.get("ownership", [])
    if len(rows) < 2 or rows[-1].get("source_news_id") != filing.news_id:
        return []
    now, prev = rows[-1], rows[-2]
    out = []
    def inst(r):
        return sum(r.get(k) or 0 for k in ("promoter_pct", "fii_pct", "dii_pct"))
    d_inst = inst(now) - inst(prev)
    holders = (now.get("retail_holders"), prev.get("retail_holders"))
    d_retail = (holders[0] / holders[1] - 1) * 100 if all(holders) else None
    if d_inst >= 1 and d_retail is not None and d_retail <= -5:
        out.append(Signal("OWNERSHIP_SHIFT", "POSITIVE", f"Smart money accumulating: promoter + FII + DII up {d_inst:.1f} pp "
                          f"to {inst(now):.1f}% ({now['period']}) while small shareholders fell {abs(d_retail):.0f}%."))
    elif d_inst <= -2 and d_retail is not None and d_retail >= 25:
        out.append(Signal("OWNERSHIP_SHIFT", "WARNING", f"Retail distribution: promoter + institutions down {abs(d_inst):.1f} pp "
                          f"while small shareholders rose {d_retail:.0f}% ({now['period']})."))
    if (now.get("pledge_pct") or 0) - (prev.get("pledge_pct") or 0) >= 5:
        out.append(Signal("OWNERSHIP_SHIFT", "WARNING", f"Promoter pledge up to {now['pledge_pct']:g}% from {prev.get('pledge_pct') or 0:g}%."))
    return out


def _auditor(after: dict, filing: Filing) -> list[Signal]:
    """Blueprint module 39: the auditor opinion ladder and mid-term resignations."""
    a = (after.get("governance") or {}).get("auditor")
    if not a or a.get("source_news_id") != filing.news_id:
        return []
    if a.get("opinion") in ("QUALIFIED", "ADVERSE", "DISCLAIMER"):
        return [Signal("AUDIT_FLAG", "WARNING", f"Auditor's opinion: {a['opinion'].lower().replace('_', ' ')}"
                       + (f" ({a['note']})" if a.get("note") else "") + ".")]
    if a.get("change") and "resign" in a["change"].lower():
        return [Signal("AUDIT_FLAG", "WARNING", f"Auditor {a.get('name') or ''} resigned mid-term.".replace("  ", " "))]
    if a.get("opinion") == "EMPHASIS_OF_MATTER":
        return [Signal("AUDIT_FLAG", "INFO", "Emphasis of matter in the audit report" + (f": {a['note']}" if a.get("note") else "") + ".")]
    return []


VOLUME_METRICS = ("sales_volume", "volumes", "total_sales", "sales_units", "units_sold", "dispatches", "production", "despatches")


def volume_strip(after: dict, news_id: str, months: int = 6) -> dict | None:
    """The card's monthly strip: the main volume metric this filing reported, over the last months
    memory holds (as of the filing), each with its YoY change."""
    from .dossier import period_kind

    own = [m for m in _own_latest(after, news_id) if period_kind(m["period"]) == "M"]
    if not own:
        return None
    main = next((m for m in own if m["metric"] in VOLUME_METRICS), own[0])
    rows = sorted((e for e in after.get("financial_metrics", []) if e["metric"] == main["metric"]
                   and period_kind(e["period"]) == "M" and due_date(e["period"]) and e.get("value") is not None),
                  key=lambda e: due_date(e["period"]))
    end = due_date(main["period"])
    rows = [e for e in rows if due_date(e["period"]) <= end][-months:]
    if len(rows) < 2:
        return None
    return {"metric": main["metric"], "unit": main.get("unit"),
            "months": [{"period": e["period"], "value": e["value"], "yoy_pct": e.get("yoy_pct")} for e in rows]}


def _volumes(after: dict, filing: Filing) -> list[Signal]:
    """Monthly updates: a growth streak (Gate 2) and, on a quarter's third month, the quarter's
    volume against the same quarter last year (blueprint module 45: an earnings preview)."""
    from .dossier import period_kind

    own = [m for m in _own_latest(after, filing.news_id) if m["metric"] in VOLUME_METRICS and period_kind(m["period"]) == "M"]
    if not own:
        return []
    out = []
    m = own[0]
    series = {e["period"]: e["value"] for e in after.get("financial_metrics", []) if e["metric"] == m["metric"] and period_kind(e["period"]) == "M"}
    def month(label: str, back: int) -> str | None:
        end = due_date(label)
        if not end:
            return None
        y, mo = end.year, end.month - back
        while mo <= 0:
            mo += 12
            y -= 1
        return f"{['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'][mo - 1]}-{y}"
    def yoy(label: str) -> float | None:
        prev = month(label, 12)
        if label in series and prev in series and series[prev]:
            return (series[label] / series[prev] - 1) * 100
        return None
    streak = 0
    for back in range(0, 6):
        g = yoy(month(m["period"], back) or "")
        if g is None or g <= 25:
            break
        streak += 1
    if streak >= 2:
        out.append(Signal("VOLUME_STREAK", "POSITIVE", f"{metric_label(m['metric'])} up more than 25% YoY for {streak} months running "
                          f"(latest {yoy(m['period']):+.0f}%, {m['period']})."))
    end = due_date(m["period"])
    if end and end.month in (3, 6, 9, 12):
        months = [month(m["period"], k) for k in (0, 1, 2)]
        last_year = [month(m["period"], k + 12) for k in (0, 1, 2)]
        if all(x in series for x in months + last_year) and sum(series[x] for x in last_year):
            total, base = sum(series[x] for x in months), sum(series[x] for x in last_year)
            out.append(Signal("QUARTER_PREVIEW", "POSITIVE" if total >= base else "WARNING",
                              f"Quarter to {m['period']}: {metric_label(m['metric'])} {total:,.0f} vs {base:,.0f} a year ago "
                              f"({(total / base - 1) * 100:+.1f}%), ahead of the quarterly results."))
    return out


PRICE_STALE_DAYS = 10


def priced_for(company: dict | None, filing: Filing) -> dict:
    """The company row without today's price and market cap when the filing is older than that price:
    a May card must not compare an issue price with October's close."""
    company = dict(company or {})
    price_date = company.get("price_date")
    try:
        stale = not price_date or (date.fromisoformat(str(price_date)[:10]) - date.fromisoformat(filing.filing_date)).days > PRICE_STALE_DAYS
    except ValueError:
        stale = True
    if stale:
        for key in ("last_price", "market_cap_cr", "ret_1w", "ret_1m", "ret_1y", "median_turnover_cr"):
            company.pop(key, None)
    return company


def _own_latest(after: dict, news_id: str) -> list[dict]:
    """The figures this filing reported for its own latest period of each kind (Q2FY27, not the
    Q1FY27 and Q2FY26 comparatives printed beside it)."""
    mine = [m for m in after.get("financial_metrics", []) if reported_by(m, news_id) and due_date(m["period"])]
    latest: dict[str, object] = {}
    for m in mine:
        kind, end = _period_kind(m["period"]), due_date(m["period"])
        if kind not in latest or end > latest[kind]:
            latest[kind] = end
    return [m for m in mine if due_date(m["period"]) == latest[_period_kind(m["period"])]]


def _promises(before: dict | None, after: dict, output: Pass2Output, filing: Filing) -> list[Signal]:
    out: list[Signal] = []
    known = {g["id"]: g for g in (before or {}).get("guidance", []) if g.get("given_on", "") < filing.filed_at}
    for update in output.dossier_delta.promise_updates:
        g = known.get(update.guidance_id)
        if not g:
            continue
        when = g.get("given_on", "")[:10]
        if update.status == "DELIVERED":
            out.append(Signal("PROMISE_DELIVERED", "POSITIVE",
                              f"\"{g['statement']}\" (guided {when}). {update.evidence}".strip(), g["id"]))
        elif update.status in ("MISSED", "DELAYED", "WITHDRAWN"):
            out.append(Signal("GUIDANCE_BREACH", "WARNING",
                              f"{update.status.capitalize()}: \"{g['statement']}\" (guided {when}). {update.evidence}".strip(), g["id"]))
    watch = {w["id"]: w for w in (before or {}).get("watchlist", []) if w.get("created_on", "") < filing.filed_at}
    for update in output.dossier_delta.watch_updates:
        w = watch.get(update.watch_id)
        if not w or update.status == "PENDING":
            continue
        severity = {"MET": "POSITIVE", "MISSED": "WARNING"}.get(update.status, "INFO")
        label = "KPI check" if w["kind"] == "KPI" else "Approval"
        out.append(Signal("WATCH_RESOLVED", severity,
                          f"{label} {update.status.lower()}: \"{w['text']}\" (flagged {w['created_on'][:10]})."
                          + (f" {update.evidence}" if update.evidence else ""), w["id"]))
    touched = {u.guidance_id for u in output.dossier_delta.promise_updates}
    today = filing.filed_at[:10]
    overdue = [
        g for g in after.get("guidance", [])
        if g.get("due_date") and g["due_date"] < today and g.get("status") in ("OPEN", "ON_TRACK")
        and g["id"] not in touched and g.get("given_on", "") < filing.filed_at
    ]
    for g in sorted(overdue, key=lambda g: g["due_date"])[:MAX_OVERDUE_SIGNALS]:
        out.append(Signal("GUIDANCE_BREACH", "WARNING",
                          f"Deadline passed: \"{g['statement']}\" was due {g['due']}, with no delivery on record.",
                          g["id"]))
    return out


def _latest_net_worth(dossier: dict) -> float | None:
    for snap in reversed(dossier.get("balance_sheet", [])):
        if snap.get("net_worth_cr"):
            return snap["net_worth_cr"]
    return None


def _dilution(after: dict, output: Pass2Output, company: dict | None) -> list[Signal]:
    out: list[Signal] = []
    company = company or {}
    for action in output.dossier_delta.capital_actions:
        existing = action.existing_shares or company.get("shares_outstanding")
        parts = []
        dilution = None
        ratio = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?::|for(?: every)?|/)\s*(\d+(?:\.\d+)?)\s*", action.ratio or "")
        if not action.new_shares and ratio and float(ratio[2]) > 0:
            # a rights entitlement fixes the dilution without the share count: 19:25 -> +76% shares, 43.2% post-money
            new, held = float(ratio[1]), float(ratio[2])
            dilution = new / (new + held) * 100
            parts.append(f"{action.ratio.strip()} entitlement: {new / held * 100:.1f}% more shares ({dilution:.1f}% post-money dilution)")
        elif action.new_shares and existing:
            # Post-money: the new holders' share of the enlarged equity.
            dilution = action.new_shares / (existing + action.new_shares) * 100
            parts.append(f"{action.new_shares / existing * 100:.1f}% more shares ({dilution:.1f}% post-money dilution; "
                         f"{action.new_shares:,.0f} new on {existing:,.0f})")
        price = company.get("last_price")
        if action.issue_price and price:
            discount = (price - action.issue_price) / price * 100
            parts.append(f"issue price ₹{action.issue_price:,.2f} is {abs(discount):.1f}% "
                         f"{'below' if discount >= 0 else 'above'} the last close ₹{price:,.2f}")
        net_worth = _latest_net_worth(after)
        if action.issue_price and net_worth and existing:
            bvps = net_worth * 1e7 / existing
            if bvps > 0:
                parts.append(f"{action.issue_price / bvps:.2f}x book value per share (₹{bvps:,.2f})")
        if not parts:
            continue
        severity = "WARNING" if (dilution or 0) >= 10 else "INFO"
        out.append(Signal("DILUTION", severity, f"{action.instrument}: " + "; ".join(parts) + "."))
    return out


def _latest_revenue(dossier: dict | None, kind: str) -> tuple[str, float] | None:
    """(period, value) of the latest quarterly ("Q") or full-year ("FY") revenue on record."""
    best = None
    for m in (dossier or {}).get("financial_metrics", []):
        period = m.get("period", "")
        if m.get("metric") not in REVENUE or not m.get("value") or (m.get("unit") or "INR_CR") != "INR_CR":
            continue
        if (kind == "Q" and not period.startswith("Q")) or (kind == "FY" and not period.startswith("FY")):
            continue
        end = due_date(period)
        if end and (best is None or end > best[0]):
            best = (end, period, m["value"])
    return (best[1], best[2]) if best else None


def _cr(value: float) -> str:
    """₹ crore as filings write it: whole crores from ₹1,000 Cr, otherwise up to two decimals."""
    if value >= 1000:
        return f"₹{value:,.0f} Cr"
    return "₹" + f"{value:,.2f}".rstrip("0").rstrip(".") + " Cr"


_SCALE_NOUN = {"ORDER": "order", "FUNDRAISE": "raise", "CAPEX": "capex", "ACQUISITION": "deal", "DIVESTMENT": "sale"}


def _scale(before: dict | None, output: Pass2Output, company: dict | None) -> list[Signal]:
    deal = output.card.deal_value if output.card is not None else None
    if deal is None or not deal.amount_cr or deal.amount_cr <= 0:
        return []
    amount, parts = deal.amount_cr, []
    if deal.kind in ("ORDER", "CAPEX", "OTHER"):
        for kind in ("Q", "FY"):
            latest = _latest_revenue(before, kind)
            if latest:
                parts.append(f"{amount / latest[1] * 100:.0f}% of {latest[0]} revenue ({_cr(latest[1])})")
    market_cap = (company or {}).get("market_cap_cr")
    if deal.kind in ("FUNDRAISE", "ACQUISITION", "DIVESTMENT", "CAPEX") and market_cap:
        parts.append(f"{amount / market_cap * 100:.0f}% of market cap ({_cr(market_cap)})")
    net_worth = _latest_net_worth(before or {})
    if deal.kind in ("FUNDRAISE", "ACQUISITION") and net_worth:
        parts.append(f"{amount / net_worth * 100:.0f}% of net worth ({_cr(net_worth)})")
    if not parts:
        return []
    noun = _SCALE_NOUN.get(deal.kind, "deal")
    gst = "; the value includes GST, revenue does not" if deal.includes_gst and deal.kind == "ORDER" else ""
    return [Signal("SCALE", "INFO", f"{_cr(amount)} {noun} = " + ", ".join(parts) + gst + ".")]


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _order_flow(before: dict | None, output: Pass2Output, filing: Filing) -> list[Signal]:
    deal = output.card.deal_value if output.card is not None else None
    if deal is None or deal.kind != "ORDER":
        return []
    earlier = [(d, deal_state(d, filing.filed_at)) for d in (before or {}).get("deals", []) if d.get("kind") == "ORDER"]
    earlier = [(d, st) for d, st in earlier if st is not None]
    updated = next(((d, st) for d, st in earlier if d["id"] == deal.updates_deal_id), None) if deal.updates_deal_id else None
    if updated is not None:
        d, st = updated
        size = f"{_cr(st['amount_cr'])} " if st.get("amount_cr") else ""
        return [Signal("ORDER_FLOW", "INFO",
                       f"Stage update, not a new order: the {size}order first reported on {d['as_of'][:10]} "
                       f"moves from {_stage(st['stage'])} to {_stage(deal.stage)}.")]
    prior = [(d, st) for d, st in earlier if st.get("amount_cr")]
    if not deal.amount_cr or not prior:
        return []  # no earlier order on record; that does not make this one the first
    since = min(d["as_of"] for d, _ in prior)[:10]
    largest_deal, largest = max(prior, key=lambda p: p[1]["amount_cr"])
    total = sum(st["amount_cr"] for _, st in prior) + deal.amount_cr
    text = f"{_ordinal(len(prior) + 1)} order on record since {since} ({_cr(total)} in total); "
    if deal.amount_cr > largest["amount_cr"]:
        text += f"the largest so far (previous high {_cr(largest['amount_cr'])} on {largest_deal['as_of'][:10]})."
    else:
        text += f"smaller than the {_cr(largest['amount_cr'])} order of {largest_deal['as_of'][:10]}."
    return [Signal("ORDER_FLOW", "INFO", text)]


def _stage(stage: str | None) -> str:
    return {"LOI": "LOI", "LOA": "LOA", "MOU": "MoU"}.get(stage or "", (stage or "unknown stage").replace("_", " ").lower())


def _growth(metrics: dict, name: str, period: str) -> float | None:
    entry = metrics.get((name, period))
    if not entry:
        return None
    if entry.get("yoy_pct") is not None:
        return entry["yoy_pct"]
    prev_period = prior_year_period(period)
    prev = metrics.get((name, prev_period)) if prev_period else None
    if prev and prev.get("value"):
        return (entry["value"] - prev["value"]) / abs(prev["value"]) * 100
    return None


def _working_capital(after: dict, filing: Filing) -> list[Signal]:
    fresh = _own_latest(after, filing.news_id)
    if not fresh:
        return []
    metrics = {(m["metric"], m["period"]): m for m in after.get("financial_metrics", [])}
    out: list[Signal] = []
    for period in sorted({m["period"] for m in fresh}):
        revenue_growth = next((g for name in REVENUE if (g := _growth(metrics, name, period)) is not None), None)
        if revenue_growth is None:
            continue
        reported = set()
        for name, label in WORKING_CAPITAL.items():
            if label in reported:
                continue
            growth = _growth(metrics, name, period)
            if growth is None or growth <= 0 or growth - revenue_growth < STRAIN_GAP_PP:
                continue
            reported.add(label)
            out.append(Signal(
                "WORKING_CAPITAL_STRAIN", "WARNING",
                f"{label} up {growth:.0f}% YoY vs revenue {revenue_growth:+.0f}% ({period}).",
            ))
    return out


# Direction in which a move is good for shareholders; unknown metrics are neutral.
HIGHER_IS_BETTER = {
    "revenue", "revenue_from_operations", "total_revenue", "net_sales", "sales", "ebitda", "ebitda_margin",
    "ebit", "pbt", "pat", "net_profit", "eps", "operating_cash_flow", "order_book", "order_inflow",
    "nim", "casa", "casa_ratio", "pcr", "crar", "roe", "roa", "volumes", "aum", "disbursements",
    "ebitda_per_tonne", "realisation_per_tonne", "net_worth", "cash_and_equivalents", "gross_margin",
    "pat_margin", "arpu", "occupancy", "vnb_margin", "solvency_ratio", "exports", "export_revenue",
    "domestic_sales", "market_share", "advances", "deposits", "gwp", "ape", "vnb", "capacity_utilisation",
}
LOWER_IS_BETTER = {
    "gross_debt", "net_debt", "debt", "finance_cost", "finance_costs", "interest_cost", "gnpa", "nnpa",
    "credit_cost", "trade_receivables", "receivables", "debtors", "inventories", "inventory",
    "cost_of_funds", "combined_ratio", "attrition", "pledged_shares", "promoter_pledge", "debt_to_equity",
    "power_and_fuel_cost", "raw_material_cost", "employee_cost",
}
ACRONYMS = {"ebitda", "ebit", "pat", "pbt", "eps", "nim", "gnpa", "nnpa", "casa", "aum", "arpu", "pcr", "crar", "roe", "roa", "gwp", "ape", "vnb"}


def metric_label(metric: str) -> str:
    words = [w.upper() if w in ACRONYMS else w for w in metric.split("_")]
    text = " ".join(words)
    return text[0].upper() + text[1:] if text else text


SHIFT_PCT = 30.0          # absolute-value metrics: flag moves of 30% or more
SHIFT_PP = 2.0            # percentage metrics (margins, ratios): flag moves of 200 bps or more
MAX_SHIFT_SIGNALS = 3


def _change(entry: dict, base: dict) -> tuple[float, str] | None:
    if base.get("value") in (None, 0) or entry.get("value") is None:
        return None
    if entry.get("unit") == "PCT":
        diff = entry["value"] - base["value"]
        return (diff / SHIFT_PP, f"{abs(diff) * 100:.0f} bps") if abs(diff) >= SHIFT_PP else None
    pct = (entry["value"] - base["value"]) / abs(base["value"]) * 100
    return (pct / SHIFT_PCT, f"{abs(pct):.0f}%") if abs(pct) >= SHIFT_PCT else None


def _period_kind(period: str) -> str:
    p = period.upper()
    for kind in ("9M", "Q", "H"):
        if p.startswith(kind):
            return kind
    return "FY" if p.startswith("FY") else "M"


def _metric_shifts(after: dict, filing: Filing, skip: set[str]) -> list[Signal]:
    by_metric: dict[str, list[dict]] = {}
    for m in after.get("financial_metrics", []):
        by_metric.setdefault(m["metric"], []).append(m)
    found: list[tuple[float, Signal]] = []
    for m in _own_latest(after, filing.news_id):
        if m["metric"] in skip:
            continue
        end = due_date(m["period"])
        if end is None:
            continue
        kind = _period_kind(m["period"])
        same_kind = [
            e for e in by_metric[m["metric"]]
            if e["period"] != m["period"] and _period_kind(e["period"]) == kind
            and e.get("as_of", "") <= m["as_of"] and (pe := due_date(e["period"])) and pe < end
        ]
        comparisons = []
        prev_year = prior_year_period(m["period"])
        base = next((e for e in same_kind if e["period"] == prev_year), None)
        if base:
            comparisons.append(("YoY", base))
        elif m.get("yoy_pct") is not None and m.get("unit") != "PCT" and m["yoy_pct"] > -100:
            comparisons.append(("YoY", {"value": m["value"] / (1 + m["yoy_pct"] / 100), "unit": m.get("unit")}))
        if kind in ("Q", "M") and same_kind:
            latest = max(same_kind, key=lambda e: due_date(e["period"]))
            if latest["period"] != prev_year:
                comparisons.append(("vs " + latest["period"], latest))
        best = None
        for label, base_entry in comparisons:
            result = _change(m, base_entry)
            if result and (best is None or abs(result[0]) > abs(best[0])):
                best = (result[0], f"{result[1]} {label}")
        if best is None:
            continue
        rising = best[0] > 0
        name = metric_label(m["metric"])
        if m["metric"] in HIGHER_IS_BETTER:
            severity = "POSITIVE" if rising else "WARNING"
        elif m["metric"] in LOWER_IS_BETTER:
            severity = "WARNING" if rising else "POSITIVE"
        else:
            severity = "INFO"
        value = f"{m['value']:,.2f}".rstrip("0").rstrip(".")
        unit = {"INR_CR": " Cr", "PCT": "%"}.get(m.get("unit"), f" {m.get('unit', '')}".rstrip())
        text = f"{name} {'up' if rising else 'down'} {best[1]} to {value}{unit} ({m['period']})."
        reversal = _reversal(by_metric[m["metric"]], m)
        if reversal:
            text += f" {reversal}"
        found.append((abs(best[0]), Signal("METRIC_SHIFT", severity, text, m["metric"])))
    found.sort(key=lambda item: -item[0])
    return [s for _, s in found[:MAX_SHIFT_SIGNALS]]


def _reversal(entries: list[dict], current: dict) -> str | None:
    """'Breaks a run of N periods of YoY growth' when the YoY sign flips after 2+ periods."""
    kind, end = _period_kind(current["period"]), due_date(current["period"])
    history = sorted(
        (e for e in entries if e is not current and e.get("yoy_pct") is not None
         and _period_kind(e["period"]) == kind and (pe := due_date(e["period"])) and end and pe < end),
        key=lambda e: due_date(e["period"]),
    )
    if current.get("yoy_pct") is None or len(history) < 2:
        return None
    last = history[-3:]
    signs = {e["yoy_pct"] > 0 for e in last}
    if len(signs) == 1 and (current["yoy_pct"] > 0) not in signs:
        return f"Breaks a run of {len(last)} periods of YoY {'growth' if True in signs else 'decline'}."
    return None
