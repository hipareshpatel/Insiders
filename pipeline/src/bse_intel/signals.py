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
from datetime import date, timedelta

from . import eps_adjust
from .dossier import approval_granted, watch_verdict, deal_state, is_recap, reported_by, same_deal
from .models import Filing, Pass2Output
from .periods import due_date, prior_year_period, results_due
from .settings import card_guidance_dated, card_watch_verdict

STRAIN_GAP_PP = 15.0      # receivable/inventory growth minus revenue growth, percentage points
MAX_OVERDUE_SIGNALS = 2
# A period's guidance is judged on its results, filed up to 45 days after a quarter and 60 after the year
# (``periods.results_due``); a deadline that is a date is judged on the day
RESULTS_SILENT_DAYS = 120   # no results this long after a deadline: the promise is judged without them

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


def compute(before: dict | None, after: dict, output: Pass2Output, filing: Filing, company: dict | None,
            every: bool = False) -> list[dict]:
    """Signals from memory as it stood at the filing: ``before`` excludes the filing, ``after`` includes
    it, and neither may hold later facts (pass them through ``dossier_as_of``). ``company`` carries market
    data as of the filing when a stored series has it (``prices.point_in_time``); today's prices are
    used only for recent filings."""
    company = priced_for(company, filing)
    from .dossier import with_year_hold
    before, after = with_year_hold(before), with_year_hold(after)   # MEMORY_YEAR_CHECK (item 76, F181): a held year figure triggers no signal, no verdict
    signals: list[Signal] = []
    signals += _promises(before, after, output, filing)
    signals += _dilution(after, output, company)
    signals += _scale(before, output, company, filing.filed_at)
    signals += _order_flow(before, output, filing)
    signals += _pledges(after, filing)
    signals += _trade_remedies(after, filing, output.event_type)
    strain = _working_capital(after, filing)
    signals += strain
    signals += _metric_shifts(after, filing, skip={"trade_receivables", "receivables", "debtors", "inventories", "inventory"} if strain else set())
    signals += _predictions(after, filing)
    signals += _ownership(after, filing)
    signals += _auditor(after, filing)
    signals += _volumes(after, filing)
    from .quality import festive_signals, quality_signals, rating_signals, roiic_signals

    found = [asdict(s) for s in signals] + quality_signals(after, filing.news_id) \
        + rating_signals(before, after, filing.news_id) + festive_signals(after, filing.news_id) + roiic_signals(after, filing.news_id)
    return found if every else [s for s in found if not misfires(s, output)]   # every: a signal's own logic, in tests


# Signal types turned off until each is checked against round 2's cards (audit round 2, signals_audit.md): each of
# these contradicted the card it sat on, and a card with fewer points beats one with wrong points. Off the card and,
# since scoring reads only what compute() returns, out of the score.
SIGNALS_OFF = {
    "DILUTION": "missed warrants beside equity (Magellanic), counted non-convertible preference shares and a demerger "
                "entitlement as new shares (Kanoria, HEG), read a promoter's holding as the share count",
    "MARGIN_MIX": "compared quarters on different bases (SKF India +1251 bps against a pre-demerger year) and cost lines "
                  "filed differently (moves of 3,000 bps)",
    "CAPITAL_COMPOUNDER": "called negative capital added 'growth funded from internal accruals' (deconsolidation, unit slips)",
    "METRIC_SHIFT": "mostly noise: tax and inventory lines, moves of 300% or more, another period than the card's, a crore "
                    "figure against a percentage",
    "PREDICTION_RESOLVED": "judged a consolidated actual against a standalone target (eMudhra) and on a wrong memory figure",
    # audit round 4 (2026-10-19), blind agents
    "CAPITAL_DILUTER": "an EBITDA run-rate 'down ₹27.3 Cr' where the filing shows EBITDA up 1-3% YoY (Sterling Tools, twice), "
                       "a run-rate the reviewer could not reproduce (Torrent): standalone and consolidated quarters mixed",
    "JAWS": "'employee cost up 250% YoY vs revenue +181%' where memory gives +16.6% and +21.3% (Cyient): bases mixed",
}


def misfires(signal: dict, output: Pass2Output) -> bool:
    kind, text = signal.get("type"), signal.get("text") or ""
    if kind in SIGNALS_OFF:
        return True
    # "met" on an approval, a concern or a KPI: it fired on the arrival of an unrelated order or a disclosure (Adani
    # Power's GVK approvals, Shivam's "net worth turning positive: met" at -₹40.68 Cr)
    if kind == "WATCH_RESOLVED" and re.search(r"\bmet\b", text, re.I):
        return True
    if kind == "SCALE":
        event = output.event_type
        deal_kind = output.card.deal_value.kind if output.card and output.card.deal_value else None
        # a rating action's bank limits are no fundraise (Lehar), and in M&A the company may be the target
        if event in ("DEBT_RATINGS", "M_AND_A", "GOVERNANCE") or (deal_kind == "FUNDRAISE" and event not in ("FUNDRAISE", "RIGHTS_ISSUE")):
            return True
        # a recap of orders already on record is no order to size (Magellanic's ₹111.04 Cr "= 62% of revenue")
        deal = output.card.deal_value if output.card else None
        if deal is not None and is_recap(deal.kind, deal.counterparty):
            return True
    return False


def _predictions(after: dict, filing: Filing) -> list[Signal]:
    """Loop 2: a number management or the analyst predicted, now checked against the actual."""
    out = []
    held = {(h["metric"], h["period"]) for h in after.get("year_held", [])}   # MEMORY_YEAR_CHECK (item 76, F181); empty when off
    for p in after.get("predictions", []):
        if p.get("resolved_by") != filing.news_id or p.get("status") not in ("MET", "MISSED"):
            continue   # UNCHECKED: the target and the figure are not in one unit (item 84), no verdict to signal
        if (p["metric"], p["period"]) in held:
            continue   # a verdict stored before the figure was held is no signal either
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
PRICE_LAG_DAYS = 7   # a close this much older than the filing is a feed that stopped (Yahoo failing for the ticker)


def priced_for(company: dict | None, filing: Filing) -> dict:
    """The company row without its price and market cap when that price is not the filing's: a May card must not
    compare an issue price with October's close, nor an October card with a close from August that a failing feed
    left in place (data chain audit A7, 22 Oct 2026). A week covers a weekend with the longest exchange holidays."""
    company = dict(company or {})
    price_date = company.get("price_date")
    try:
        gap = (date.fromisoformat(str(price_date)[:10]) - date.fromisoformat(filing.filing_date)).days
        stale = gap > PRICE_STALE_DAYS or gap < -PRICE_LAG_DAYS
    except (TypeError, ValueError):
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
    dated = card_guidance_dated()   # F172: a verdict only from a dated target for this filing's period and metric
    if dated:
        from .guidance_dated import said_on, why_no_verdict, why_no_watch_verdict
    known = {g["id"]: g for g in (before or {}).get("guidance", []) if g.get("given_on", "") < filing.filed_at}
    for update in output.dossier_delta.promise_updates:
        g = known.get(update.guidance_id)
        if not g:
            continue
        when = g.get("given_on", "")[:10]
        if dated and update.status in ("DELIVERED", "DELAYED", "MISSED"):
            why = why_no_verdict(g, after.get("financial_metrics", []), filing.news_id)
            if why:
                out.append(Signal("WATCH_RESOLVED", "INFO", said_on(g, why), g["id"]))
                continue
        if card_watch_verdict() and update.status in ("DELIVERED", "DELAYED", "MISSED"):   # F205: two periods of one metric
            from .watch_code import relative_guidance_verdict
            if relative_guidance_verdict(g, after.get("financial_metrics", [])) == "MET":
                update = update.model_copy(update={"status": "DELIVERED"})
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
        if w["kind"] == "APPROVAL" and update.status == "MET" and not approval_granted(update.evidence):
            continue  # "Approval met" with evidence that it is still pending
        code = None
        if card_watch_verdict():   # F205: code reads the target's direction, period and unit
            from .watch_code import NOT_DUE, watch_code_verdict
            code = watch_code_verdict(w, update.evidence, after.get("financial_metrics", []), filing.news_id, filing.filed_at)
            if code == NOT_DUE and update.status in ("MET", "MISSED"):
                continue  # a verdict claimed for a later period than this filing's is not judged
        status = watch_verdict(w, update.status, update.evidence, filing.filed_at)
        if status == "PENDING":
            continue  # no news, another item's news, or an earlier quarter's figure
        if code in ("MET", "MISSED"):
            status = code
        if dated and status in ("MET", "MISSED"):
            why = why_no_watch_verdict(w, after.get("financial_metrics", []), filing.news_id)
            if why:
                out.append(Signal("WATCH_RESOLVED", "INFO", said_on(w, why), w["id"]))
                continue
        severity = {"MET": "POSITIVE", "MISSED": "WARNING"}.get(status, "INFO")
        label = {"KPI": "KPI check", "APPROVAL": "Approval", "CONCERN": "Concern"}.get(w["kind"], "Watch item")
        out.append(Signal("WATCH_RESOLVED", severity,
                          f"{label} {status.lower()}: \"{w['text']}\" (flagged {w['created_on'][:10]})."
                          + (f" {update.evidence}" if update.evidence else ""), w["id"]))
    touched = {u.guidance_id for u in output.dossier_delta.promise_updates}
    today = filing.filed_at[:10]
    # Flagged once, on the first filing after the deadline: Ahluwalia's FY25 revenue guidance was
    # "Deadline passed" on five cards in a row.
    last = max((t.get("date", "")[:10] for t in (before or {}).get("timeline", []) if t.get("date", "") < filing.filed_at), default="")
    # The latest period whose results memory holds: guidance due at a period's end is pending until that period's
    # results are in, whatever the date (Jindal Stainless's H1FY27 EBITDA/tonne "Deadline passed" on a card filed before
    # its Q2 results, owner's review 2026-10-20); a company that has not reported long after is flagged all the same
    reported = max((str(e) for e in (due_date(m.get("period")) for m in after.get("financial_metrics", [])
                                     if m.get("metric") in ("revenue", "pat", "interest_earned")) if e), default="")
    long_after = (date.fromisoformat(today) - timedelta(days=RESULTS_SILENT_DAYS)).isoformat()
    overdue = [
        g for g in after.get("guidance", [])
        if g.get("due_date") and _judged_on(g) < today
        and (not _period_due(g) or reported >= g["due_date"] or g["due_date"] < long_after)
        and g.get("status") in ("OPEN", "ON_TRACK")
        and g["id"] not in touched and g.get("given_on", "") < filing.filed_at and not (last and last > _judged_on(g))
    ]
    for g in sorted(overdue, key=lambda g: g["due_date"])[:MAX_OVERDUE_SIGNALS]:
        why = why_no_verdict(g, after.get("financial_metrics", []), filing.news_id) if dated else None
        if why:
            out.append(Signal("WATCH_RESOLVED", "INFO", said_on(g, why), g["id"]))
            continue
        if card_watch_verdict():   # F205: memory's own two figures settle "Q1FY27 revenue to surpass Q4FY26"
            from .watch_code import relative_guidance_verdict
            verdict = relative_guidance_verdict(g, after.get("financial_metrics", []))
            if verdict == "MET":
                out.append(Signal("PROMISE_DELIVERED", "POSITIVE",
                                  f"\"{g['statement']}\" (guided {g.get('given_on', '')[:10]}): memory's figures show it met.", g["id"]))
                continue
            if verdict == "MISSED":
                out.append(Signal("GUIDANCE_BREACH", "WARNING", f"Missed: \"{g['statement']}\" (memory's figures).", g["id"]))
                continue
        out.append(Signal("GUIDANCE_BREACH", "WARNING",
                          f"Deadline passed: \"{g['statement']}\" was due {g['due']}, with no delivery on record.",
                          g["id"]))
    return out


def _judged_on(g: dict) -> str:
    """The first day a guidance item can be called missed: its period's end plus the results window when it is due
    for a reporting period ("H1FY27" -> 14 Nov, not 30 Sep: Jindal Stainless, owner 2026-10-20, O12), else its date."""
    judged = results_due(g.get("due"))
    return judged.isoformat() if judged else g.get("due_date") or ""


def _period_due(g: dict) -> bool:
    end = due_date(g.get("due"))
    return end is not None and _judged_on(g) > end.isoformat()


def _latest_net_worth(dossier: dict) -> float | None:
    for snap in reversed(dossier.get("balance_sheet", [])):
        if snap.get("net_worth_cr"):
            return snap["net_worth_cr"]
    return None


# Capital actions that issue no new shares: a dividend's "issue price" or an open offer's share count
# is not dilution (Mahindra's open offer read as "26% more shares"; a ₹18 dividend "99% below" the close).
_NOT_AN_ISSUE = re.compile(r"dividend|open offer|buy-?back|authori[sz]ed|split|sub-?division|consolidation|"
                           r"offer for sale|\bofs\b|bonus|reduction", re.I)


def _dilution(after: dict, output: Pass2Output, company: dict | None) -> list[Signal]:
    out: list[Signal] = []
    company = company or {}
    for action in output.dossier_delta.capital_actions:
        if _NOT_AN_ISSUE.search(action.instrument or ""):
            continue
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


_SCALE_NOUN = {"ORDER": "order", "FUNDRAISE": "raise", "CAPEX": "capex", "ACQUISITION": "deal", "DIVESTMENT": "sale",
               "CONVERSION": "conversion"}
# Debentures, bonds, loans or preference shares converted into equity; "convertible" (an instrument still to be
# issued for cash) and warrants (whose conversion brings in the unpaid 75%) are not.
_DEBT_INSTRUMENT = r"\b(?:(?:o|c|oc)cds?|ocrps?|ccps|debentures?|fccbs?|bonds?|loans?|notes|preference shares?|unsecured)\b"
# A new FCCB or bond issue states its terms ("conversion price Rs 512", "conversion premium"): still a raise.
_CONVERSION = r"conver(?:t|ts|ted|ting|sion)\b(?!\s+(?:price|premium|ratio|option|right|terms?|period|date)s?\b)"
_DEBT_CONVERTED = re.compile(rf"{_CONVERSION}.{{0,40}}{_DEBT_INSTRUMENT}|{_DEBT_INSTRUMENT}.{{0,40}}{_CONVERSION}", re.I)


def scale_parts(before: dict | None, output: Pass2Output, company: dict | None, filed_at: str | None = None) -> dict | None:
    """The deal's size against the company, as figures: {amount_cr, noun, gst, against: [{pct, label, base_cr}],
    per_year}. `per_year` spreads an order over its execution term against a year's revenue (Monarch's ₹48 Cr railway
    order over 36 months is 9% of a year's sales a year, not 49% at once; owner's example, 2026-10-19)."""
    deal = output.card.deal_value if output.card is not None else None
    if deal is None or not deal.amount_cr or deal.amount_cr <= 0:
        return None
    deal_kind = deal.kind
    # A fundraise is money reaching the company. On an M_AND_A filing it is not: an open offer or a block
    # of shares bought from existing holders moves money between shareholders, and the company receives
    # nothing, so "x Cr raise = n% of net worth" is simply false (audit round 1: Novartis India's 552.5 Cr
    # open offer and M&M's 554.65 Cr purchase of SML Isuzu both read that way). The size against the
    # target's market cap still says something, so that line stays and only the raise reading goes.
    shareholder_money = deal_kind == "FUNDRAISE" and output.event_type == "M_AND_A"
    if shareholder_money:
        deal_kind = "ACQUISITION"
    # Debt turned into shares brings no new cash either: Shivam Autotech's 250 OCDs converted into equity read
    # "₹25 Cr raise = 74% of net worth" (audit round 1). Its size against market cap stays, as a conversion.
    elif deal_kind == "FUNDRAISE" and _DEBT_CONVERTED.search(
            " ".join([output.card.headline] + [a.instrument or "" for a in output.dossier_delta.capital_actions])):
        deal_kind = "CONVERSION"
    amount, against = deal.amount_cr, []
    if deal_kind in ("ORDER", "CAPEX", "OTHER"):
        # a capex plan runs for years: one quarter's revenue made ITC's ₹20,000 Cr plan "84%" (live review 3)
        for period_kind in (("Q", "FY") if deal_kind == "ORDER" else ("FY",)):
            latest = _latest_revenue(before, period_kind)
            if latest:
                against.append({"pct": amount / latest[1] * 100, "label": f"{latest[0]} revenue", "base_cr": latest[1]})
    market_cap = (company or {}).get("market_cap_cr")
    if deal_kind in ("FUNDRAISE", "ACQUISITION", "DIVESTMENT", "CAPEX", "CONVERSION") and market_cap:
        against.append({"pct": amount / market_cap * 100, "label": "market cap", "base_cr": market_cap})
    net_worth = _latest_net_worth(before or {})
    if deal_kind in ("FUNDRAISE", "ACQUISITION") and net_worth and not shareholder_money:
        against.append({"pct": amount / net_worth * 100, "label": "net worth", "base_cr": net_worth})
    if not against:
        return None
    per_year = None
    years = term_years(deal.execution_by, filed_at)
    year_revenue = _latest_revenue(before, "FY")
    if deal_kind == "ORDER" and years and years >= 1.5 and year_revenue:
        per_year = {"years": round(years, 1), "pct": round(amount / years / year_revenue[1] * 100, 1),
                    "label": f"{year_revenue[0]} revenue"}
    return {"amount_cr": amount, "noun": _SCALE_NOUN.get(deal_kind, "deal"), "against": against, "per_year": per_year,
            "gst": bool(deal.includes_gst and deal_kind == "ORDER")}


# a bare financial year or quarter ("FY29", "FY 2029", "during the financial year 2026-27", "Q2 2027") names when the
# order is executed, not when a term that starts today ends (hourly review 23 Oct 2026)
_EXECUTED_IN = re.compile(r"(?:(?:during|in)\s+)?(?:the\s+)?(?:fy\s*'?\d{2,4}(?:-\d{2,4})?|financial\s+year\s+\d{4}(?:-\d{2,4})?"
                          r"|q[1-4]\s*(?:fy\s*)?'?\d{2,4}(?:-\d{2,4})?)")


def term_years(execution_by: str | None, filed_at: str | None) -> float | None:
    """An execution term in years: "36 months", "within 3 years", or a date or period after the filing."""
    if not execution_by:
        return None
    text = execution_by.lower()
    if _EXECUTED_IN.fullmatch(text.strip(" .")):
        return None   # the period it is executed in, not a term from today: Welspun's "FY29" order read "over its 2.4-year term"
    if m := re.search(r"(\d+(?:\.\d+)?)\s*(months?|years?)", text):
        n = float(m[1])
        return n / 12 if m[2].startswith("month") else n
    end = due_date(execution_by)
    if end and filed_at:
        try:
            start = date.fromisoformat(filed_at[:10])
        except ValueError:
            return None
        return (end - start).days / 365.25 if end > start else None
    return None


def _share(pct: float) -> str:
    """A share in whole percent, and under 1% with a decimal: GRP's ₹2.6 Cr solar plant read "0% of FY26 revenue, 0% of
    market cap" for 0.48% and 0.27% (live review 5, 2026-10-20)."""
    return f"{pct:.1f}%" if abs(pct) < 1 else f"{pct:.0f}%"


def _scale(before: dict | None, output: Pass2Output, company: dict | None, filed_at: str | None = None) -> list[Signal]:
    scale = scale_parts(before, output, company, filed_at)
    if scale is None:
        return []
    parts = [f"{_share(a['pct'])} of {a['label']} ({_cr(a['base_cr'])})" for a in scale["against"]]
    gst = "; the value includes GST, revenue does not" if scale["gst"] else ""
    term = scale["per_year"]
    spread = f"; over its {term['years']:g}-year term, {_share(term['pct'])} of {term['label']} a year" if term else ""
    return [Signal("SCALE", "INFO", f"{_cr(scale['amount_cr'])} {scale['noun']} = " + ", ".join(parts) + spread + gst + ".")]


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _pledges(after: dict | None, filing: Filing) -> list[Signal]:
    """Module 42: a promoter pledge invoked, encumbrance rising, or released in full, from NSE's SAST Reg 31 feed in
    memory (pledges.py). `after` is memory as of the filing, so a card sees only the events known then."""
    from .pledges import signals as pledge_signals

    return [Signal("PLEDGE", severity, text) for severity, text in pledge_signals(after, filing.filed_at)]


# A DGTR step is news about the company's business, not about whatever it filed next: it sat on ITC's AGM speech, an
# acquisition's closing and an amalgamation in the same week (live review 3). It goes on the cards where a holder
# weighs the business - results, the call, the annual report - since the last results (120 days).
_TRADE_REMEDY_EVENTS = {"RESULTS", "CONCALL_PRESENTATION", "ANNUAL_REPORT"}


def _trade_remedies(after: dict | None, filing: Filing, event_type: str | None = None) -> list[Signal]:
    """Module 8: a DGTR step (initiation, finding, duty notified, termination) since the last results on a case the
    company applied for or supported (dgtr.py), from memory as of the filing, on results-family cards."""
    from .dgtr import signals as dgtr_signals

    if event_type not in _TRADE_REMEDY_EVENTS:
        return []
    return [Signal("TRADE_REMEDY", severity, text) for severity, text in dgtr_signals(after, filing.filed_at, days=120)]


def _order_flow(before: dict | None, output: Pass2Output, filing: Filing) -> list[Signal]:
    deal = output.card.deal_value if output.card is not None else None
    if deal is None or deal.kind != "ORDER" or is_recap(deal.kind, deal.counterparty):
        return []
    earlier, seen = [], []
    for d in (before or {}).get("deals", []):
        st = deal_state(d, filing.filed_at) if d.get("kind") == "ORDER" else None
        if st is None or is_recap(d.get("kind"), d.get("counterparty")) or st.get("stage") == "CANCELLED":
            continue   # a cancelled tender is no order on record (Ceigall's ₹330.84 Cr Delhi PWD bid, round 5 arm B)
        # memory written before same_deal() holds a press release's order beside its intimation's
        if same_deal(seen, "ORDER", d.get("amount_cr"), d.get("counterparty"), d["as_of"], d.get("source_news_id", "")):
            continue
        seen.append(d)
        earlier.append((d, st))
    updated = next(((d, st) for d, st in earlier if d["id"] == deal.updates_deal_id), None) if deal.updates_deal_id else None
    if updated is None:
        repeat = same_deal([d for d, _ in earlier], "ORDER", deal.amount_cr, deal.counterparty, filing.filed_at,
                           filing.news_id)
        updated = next(((d, st) for d, st in earlier if repeat is not None and d["id"] == repeat["id"]), None)
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
    if prev and prev.get("value") and prev["value"] > 0 and (entry.get("value") or 0) >= 0:  # no % off a negative base
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


PROFIT_LINES = {"pat", "pbt", "ebitda", "ebit", "net_profit", "eps", "operating_profit"}


def _change(entry: dict, base: dict) -> tuple[float, str] | None:
    if base.get("value") in (None, 0) or entry.get("value") is None:
        return None
    if entry.get("unit") == "PCT":
        diff = entry["value"] - base["value"]
        return (diff / SHIFT_PP, f"{abs(diff) * 100:.0f} bps") if abs(diff) >= SHIFT_PP else None
    # A percentage off a loss, a write-back or a negative base means nothing: "PAT up 413% vs Q4FY26" was a swing
    # from a ₹19.76 Cr loss, "EBITDA up 4618%" from -₹0.44 Cr (audit round 2). A profit line that crosses zero is
    # said in words; anything else is not a shift worth a percentage.
    if base["value"] < 0 or entry["value"] < 0:
        if entry.get("metric") in PROFIT_LINES and (base["value"] < 0) != (entry["value"] < 0):
            return (3.0 if entry["value"] > 0 else -3.0, "TURN")
        return None
    pct = (entry["value"] - base["value"]) / abs(base["value"]) * 100
    return (pct / SHIFT_PCT, f"{abs(pct):.0f}%") if abs(pct) >= SHIFT_PCT else None


def _period_kind(period: str) -> str:
    p = period.upper()
    for kind in ("9M", "Q", "H"):
        if p.startswith(kind):
            return kind
    return "FY" if p.startswith("FY") else "M"


_NO_EPS = {"eps", "basic_eps", "diluted_eps", "eps_total", "eps_continuing"}


def _metric_shifts(after: dict, filing: Filing, skip: set[str]) -> list[Signal]:
    by_metric: dict[str, list[dict]] = {}
    for m in after.get("financial_metrics", []):
        by_metric.setdefault(m["metric"], []).append(m)
    found: list[tuple[float, Signal]] = []
    for m in _own_latest(after, filing.news_id):
        if m["metric"] in skip or m["metric"] in _NO_EPS:
            continue   # owner rule 26 Oct 2026: no EPS on cards or stock pages (no "EPS up 35%" signal; memory keeps it)
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
        if m["metric"] == "eps" and eps_adjust.enabled():
            # EPS_SHARE_ADJUST (F153): older EPS on today's share count; a comparison with no basis is not made
            same_kind = _eps_bases(same_kind, m, after, by_metric)
        prev_year = prior_year_period(m["period"])
        base = next((e for e in same_kind if e["period"] == prev_year), None)
        if base:
            comparisons.append(("YoY", base))
        elif m.get("yoy_pct") is not None and m.get("unit") != "PCT" and m["yoy_pct"] > -100 and m["value"] > 0 \
                and not (m["metric"] == "eps" and eps_adjust.enabled() and prev_year
                         and eps_adjust.factor_between(after, prev_year, m["period"]) != 1):
            comparisons.append(("YoY", {"value": m["value"] / (1 + m["yoy_pct"] / 100), "unit": m.get("unit")}))
        if kind in ("Q", "M") and same_kind:
            latest = max(same_kind, key=lambda e: due_date(e["period"]))
            if latest["period"] != prev_year:
                comparisons.append(("vs " + latest["period"], latest))
        best = None
        for label, base_entry in comparisons:
            result = _change(m, base_entry)
            if result and (best is None or abs(result[0]) > abs(best[0])):
                best = (result[0], result[1], label, base_entry)
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
        unit = {"INR_CR": " Cr", "PCT": "%"}.get(m.get("unit"), f" {m.get('unit', '')}".rstrip())
        shown = lambda v: f"{v:,.2f}".rstrip("0").rstrip(".")  # noqa: E731
        value = shown(m["value"])
        if best[1] == "TURN":
            text = (f"{name} turned to a {'profit' if rising else 'loss'} of {shown(abs(m['value']))}{unit} ({m['period']}) "
                    f"from a {'loss' if rising else 'profit'} of {shown(abs(best[3]['value']))}{unit} {best[2]}.")
        else:
            text = f"{name} {'up' if rising else 'down'} {best[1]} {best[2]} to {value}{unit} ({m['period']})."
        reversal = _reversal(by_metric[m["metric"]], m)
        if reversal:
            text += f" {reversal}"
        found.append((abs(best[0]), Signal("METRIC_SHIFT", severity, text, m["metric"])))
    found.sort(key=lambda item: -item[0])
    return [s for _, s in found[:MAX_SHIFT_SIGNALS]]


def _eps_bases(older: list[dict], current: dict, after: dict, by_metric: dict) -> list[dict]:
    """The earlier EPS entries a shift is measured against, on the current period's share count (eps_adjust.py,
    EPS_SHARE_ADJUST): adjusted for a split or bonus between, and left out where the share count changed with no record."""
    profit = {}
    for name in ("pat", "pat_owners"):   # the owners' profit wins where memory has it
        for e in by_metric.get(name, []):
            if e.get("value") is not None:
                profit[e["period"]] = e["value"]
    out = []
    for e in older:
        result = eps_adjust.compare(after, current["period"], e["period"], current["value"], e.get("value"),
                                    profit.get(current["period"]), profit.get(e["period"]))
        if result.kind == "same":
            out.append(e)
        elif result.kind == "adjusted":
            out.append({**e, "value": result.eps_old})
    return out


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


_ORDER_BOOK = ("order_book", "order_book_outstanding", "unexecuted_order_book")


def stated_net_debt(snap: dict) -> float | None:
    """A balance sheet's net debt as a filing stated it. Not one from the results XBRL: that was borrowings less cash and
    cash equivalents alone, without bank deposits and liquid investments (Kajaria Q2FY27: "net debt ₹291.98 Cr" for a
    stated net cash of ₹635 Cr), and snapshots in memory still carry it."""
    if str(snap.get("source_news_id") or "").startswith("xbrl:"):
        return None
    return snap.get("net_debt_cr")


def scale_block(dossier: dict | None, company: dict | None, text: str, unit: int | None = None, top: int = 4) -> str:
    """The proportions for the Pass 2 prompt, computed in code (owner's note, 2026-10-16: the model must
    not work out shares of revenue or market cap; the audit found "41% of FY25 revenue" where it was 7.3%
    and "3.6x FY25 revenue" where the filing said 84% of turnover).

    Gives the company's denominators and, for each large ₹ crore amount written in the filing, its share
    of them. `unit` is the filing's declared unit (grounding.declared_unit), so a lakh table's bare
    figures are not read as crore."""
    from .grounding import UNIT_NAMES, _crore_positions, _tokens  # local: grounding imports nothing from here
    from .scoring import ttm_revenue

    company = company or {}
    lines: list[str] = []
    denominators: list[tuple[str, float]] = []
    market_cap = company.get("market_cap_cr")
    if market_cap:
        denominators.append(("market cap", float(market_cap)))
        lines.append(f"- market cap {_cr(float(market_cap))}" + (f" ({company['price_date']})" if company.get("price_date") else ""))
    ttm = ttm_revenue(dossier)
    # Each share names its revenue: "19.5% of revenue" (twelve months) was written "19.5% of Q1FY27 revenue" when it
    # was 72.7% of that quarter (round 5, 2026-10-19, Ceigall; also Protean, Max Financial)
    if ttm:
        denominators.append(("trailing-12-month revenue", ttm[0]))
        lines.append(f"- trailing-12-month revenue {_cr(ttm[0])} ({ttm[1]})")
    quarter = _latest_revenue(dossier, "Q")
    if quarter:
        denominators.append((f"{quarter[0]} quarter revenue", quarter[1]))
        lines.append(f"- latest quarter revenue {_cr(quarter[1])} ({quarter[0]})")
    net_worth = _latest_net_worth(dossier or {})
    if net_worth:
        denominators.append(("net worth", net_worth))
        lines.append(f"- net worth {_cr(net_worth)}")
    for snap in reversed((dossier or {}).get("balance_sheet", [])):
        debt = stated_net_debt(snap)
        if debt is not None or snap.get("gross_debt_cr") is not None:
            if debt is not None and debt < 0:
                lines.append(f"- net cash {_cr(-debt)} ({snap.get('period', 'latest')})")
            else:
                lines.append(f"- {'net' if debt is not None else 'gross'} debt "
                             f"{_cr(debt if debt is not None else snap['gross_debt_cr'])} ({snap.get('period', 'latest')})")
            break
    book = [m for m in (dossier or {}).get("financial_metrics", []) if m.get("metric") in _ORDER_BOOK and m.get("value")]
    if book:
        latest = max(book, key=lambda m: due_date(m["period"]) or date.min)
        denominators.append(("order book", float(latest["value"])))
        lines.append(f"- order book {_cr(float(latest['value']))} ({latest['period']})")
    if not lines:
        return "Not known for this company yet: give no proportions of revenue, market cap or net worth."

    # ₹ crore amounts the filing itself writes, largest first, with their share of each denominator
    crore_at = _crore_positions(text or "")
    amounts = sorted({round(value, 2) for value, _, pos, kind, _ in _tokens(text or "")
                      if pos in crore_at and kind in ("plain", "qty") and value >= 1}, reverse=True)[:top]
    if amounts and denominators:
        lines.append("Amounts written in this filing, in proportion:")
        for amount in amounts:
            shares = ", ".join(f"{amount / base * 100:.1f}% of {name}" for name, base in denominators if base > 0)
            lines.append(f"- {_cr(amount)} = {shares}")
    elif unit:
        lines.append(f"The statement is in {UNIT_NAMES.get(unit, 'a stated unit')}: divide by "
                     f"{unit:,} for ₹ crore before comparing anything.")
    return "\n".join(lines)
