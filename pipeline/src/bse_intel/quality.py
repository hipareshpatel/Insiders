"""Earnings-quality, balance-sheet and rating forensics (blueprint §9, deterministic modules).

Each check reads memory as it stood at the filing (``after`` from ``dossier_as_of``) and fires only
on figures this filing reported, so a backfilled card is never judged on later numbers. The detailed
P&L lines these checks need (other income, cost lines, taxes, exceptional items) come reliably from
the XBRL fast path; where a filing's figures lack a line, the check stays silent.

* M15 LOW_QUALITY_BEAT: other income a large share of PBT, or profit up while core EBITDA is not.
* M16 MARGIN_MIX: a margin move split into gross margin (spread, pricing, mix) and fixed-cost
  absorption (operating leverage).
* M17 JAWS: employee cost running ahead of revenue; read as pre-launch hiring when a plant is due.
* M18 LOW_CASH_TAX: current tax under 10% of PBT for three quarters running.
* M21 Q4_TRUE_UP: a Q4 margin more than 400 bps below the year's first three quarters.
* M22 RECURRING_ONE_OFFS: exceptional items in 3 or more of the last 8 quarters.
* M27 DEBT_CASH_PARADOX: debt above 2.5x EBITDA beside large cash: check the cash is free.
* M29 DISTRESS: interest cover under 1.5x, or negative net worth.
* M31 warrant clock: see ``warrant_deadlines`` (catalysts 18 months after an allotment).
* M38 RATING_LIQUIDITY: a short-term rating downgrade, a negative outlook, or Issuer Not Cooperating.
* M46 FESTIVE_SEASON: October and November volumes read together (Diwali moves between them).
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from . import business_line
from .periods import due_date, prior_quarter_period, prior_year_period

ALIASES = {
    "revenue": ("revenue", "revenue_from_operations", "net_sales", "total_revenue", "sales"),
    "other_income": ("other_income",),
    "pbt": ("pbt", "profit_before_tax"),
    "pat": ("pat", "net_profit", "profit_after_tax"),
    "ebitda": ("ebitda", "operating_profit"),
    "raw_material": ("raw_material_cost", "cost_of_materials_consumed"),
    "purchases": ("purchases_stock_in_trade",),
    "inventory_change": ("inventory_change",),
    "employee": ("employee_cost", "employee_benefit_expense", "employee_expenses"),
    "other_expenses": ("other_expenses",),
    "finance": ("finance_cost", "finance_costs", "interest_cost"),
    "depreciation": ("depreciation", "depreciation_and_amortisation"),
    "current_tax": ("current_tax",),
    "exceptional": ("exceptional_items",),
}
SHORT_TERM_LADDER = ["A1+", "A1", "A2+", "A2", "A3+", "A3", "A4+", "A4", "D"]
FESTIVE_METRICS = ("sales_volume", "volumes", "total_sales", "sales_units", "units_sold", "dispatches", "despatches")


def _table(after: dict) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for m in after.get("financial_metrics", []):
        if m.get("value") is None or (m.get("unit") or "INR_CR") not in ("INR_CR",):
            continue
        for key, names in ALIASES.items():
            if m["metric"] in names:
                out.setdefault((key, m["period"]), float(m["value"]))
    return out


def _latest_quarter(after: dict, news_id: str) -> str | None:
    from .dossier import reported_by

    mine = [m["period"] for m in after.get("financial_metrics", [])
            if reported_by(m, news_id) and m["period"].startswith("Q") and due_date(m["period"])]
    return max(mine, key=due_date) if mine else None


def _pct(now: float | None, before: float | None) -> float | None:
    if now is None or before is None or before <= 0:
        return None
    return (now / before - 1) * 100


def _signal(kind: str, severity: str, text: str) -> dict:
    return {"type": kind, "severity": severity, "text": text, "ref": None}


def _quarters_back(period: str, n: int) -> list[str]:
    out, p = [], period
    for _ in range(n):
        out.append(p)
        p = prior_quarter_period(p) or ""
        if not p:
            break
    return out


LENDERS = {"banks", "nbfc", "insurance"}


def quality_signals(after: dict, news_id: str) -> list[dict]:
    t = _table(after)
    q = _latest_quarter(after, news_id)
    if not q:
        return []
    get = lambda key, p=q: t.get((key, p))  # noqa: E731
    ya = prior_year_period(q)
    out: list[dict] = []

    # M15: other income share of PBT; profit up while core EBITDA is not
    oi, pbt = get("other_income"), get("pbt")
    lender = after.get("sector") in LENDERS  # a bank's or NBFC's other income is fees and treasury: core business
    if not lender and oi is not None and pbt and pbt > 0 and oi / pbt >= 0.4:
        out.append(_signal("LOW_QUALITY_BEAT", "WARNING", f"Other income ₹{oi:g} Cr is {oi / pbt * 100:.0f}% of PBT ({q})."))
    pat_g, ebitda_g = _pct(get("pat"), get("pat", ya)), _pct(get("ebitda"), get("ebitda", ya))
    if pat_g is not None and ebitda_g is not None and pat_g >= 15 and ebitda_g <= 0:
        out.append(_signal("LOW_QUALITY_BEAT", "WARNING",
                           f"PAT up {pat_g:.0f}% YoY but core EBITDA {ebitda_g:+.0f}% ({q}): the profit came from below the operating line."))

    # M16: margin move = gross margin + fixed-cost absorption
    def ratios(p):
        rev = get("revenue", p)
        if not rev:
            return None
        materials = [get(k, p) for k in ("raw_material", "purchases", "inventory_change")]
        fixed = [get(k, p) for k in ("employee", "other_expenses")]
        if materials[0] is None or any(v is None for v in fixed):
            return None
        return 1 - sum(v or 0 for v in materials) / rev, sum(fixed) / rev
    now_r, old_r = ratios(q), ratios(ya) if ya else None
    if now_r and old_r:
        gross_bps, fixed_bps = (now_r[0] - old_r[0]) * 1e4, (old_r[1] - now_r[1]) * 1e4
        if abs(gross_bps) + abs(fixed_bps) >= 150:
            out.append(_signal("MARGIN_MIX", "POSITIVE" if gross_bps + fixed_bps > 0 else "WARNING",
                               f"Margin vs a year ago ({q}): gross margin {gross_bps:+.0f} bps (spread, pricing, mix), "
                               f"fixed-cost absorption {fixed_bps:+.0f} bps (operating leverage)."))

    # M17: employee cost outrunning revenue
    emp_g, rev_g = _pct(get("employee"), get("employee", ya)), _pct(get("revenue"), get("revenue", ya))
    if emp_g is not None and rev_g is not None and emp_g > 20 and emp_g - rev_g >= 10:
        launching = any(d.get("kind") == "CAPEX" and d.get("stage") not in ("COMPLETED", "CANCELLED") for d in after.get("deals", []))
        out.append(_signal("JAWS", "INFO" if launching else "WARNING",
                           f"Employee cost up {emp_g:.0f}% YoY vs revenue {rev_g:+.0f}% ({q})"
                           + ("; a project is under way, so this may be hiring ahead of launch." if launching else ".")))

    # M18: low cash tax for three quarters
    recent = _quarters_back(q, 3)
    rates = [(get("current_tax", p), get("pbt", p)) for p in recent]
    if len(rates) == 3 and all(c is not None and b and b > 0 for c, b in rates) and all(c / b < 0.10 for c, b in rates):
        out.append(_signal("LOW_CASH_TAX", "INFO", f"Current tax under 10% of PBT for three quarters to {q}: "
                           "check for a tax holiday or carried-forward losses, and when the rate steps up."))

    # M21: Q4 audit true-up
    if q.startswith("Q4"):
        fy = q[2:]
        def margin(p):
            r = ratios(p)
            if r:
                return r[0]
            e, rev = get("ebitda", p), get("revenue", p)
            return e / rev if e is not None and rev else None
        first = [margin(f"Q{i}{fy}") for i in (1, 2, 3)]
        m4 = margin(q)
        if m4 is not None and all(m is not None for m in first):
            drop = (sum(first) / 3 - m4) * 1e4
            if drop > 400:
                out.append(_signal("Q4_TRUE_UP", "WARNING", f"Q4 margin {drop:.0f} bps below the average of Q1–Q3 ({fy}): "
                                   "the audited quarter may be correcting the reviewed ones."))

    # M22: recurring "one-offs"
    # Charges only (stored negative: Heritage's -23.48 Cr impairment; a gain is positive, Ahluwalia's +194.97 Cr): a
    # one-off gain is not a running cost, and ITC's ₹405.88 Cr remeasurement gain was counted as one (live review 3)
    hits = [p for p in _quarters_back(q, 8) if (get("exceptional", p) or 0) < 0]
    if len(hits) >= 3:
        out.append(_signal("RECURRING_ONE_OFFS", "WARNING",
                           f"Exceptional charges in {len(hits)} of the last 8 quarters ({', '.join(reversed(hits))}): treat them as a running cost."))

    # M27 and M29 from the balance sheet and interest cover
    sheets = after.get("balance_sheet", [])
    sheet = sheets[-1] if sheets else {}
    ttm = [get("ebitda", p) for p in _quarters_back(q, 4)]
    if len(ttm) == 4 and all(v is not None for v in ttm) and sum(ttm) > 0:
        debt, cash = sheet.get("gross_debt_cr"), sheet.get("cash_cr")
        if debt and cash and debt / sum(ttm) > 2.5 and cash >= 0.3 * debt:
            out.append(_signal("DEBT_CASH_PARADOX", "INFO", f"Debt ₹{debt:g} Cr is {debt / sum(ttm):.1f}x TTM EBITDA while cash is ₹{cash:g} Cr: "
                               "check whether the cash is margin money or otherwise not free."))
    fin, ebitda, dep = get("finance"), get("ebitda"), get("depreciation")
    # A lender's finance cost is its cost of funds, not a debt burden: HUDCO's own filing marks interest cover "Not
    # Applicable", and its card warned that "operating profit barely covers interest" at 39% capital adequacy (round 4)
    if fin and fin > 0 and ebitda is not None and not lender:
        cover = (ebitda - (dep or 0)) / fin
        if cover < 1.5:
            # One sentence used to serve every cover below 1.5x, so a negative one read "operating profit
            # barely covers interest" at -0.3x and even -0.0x, which is the opposite of what it says (audit
            # round 1). The measure is named too: a company's own Interest Service Coverage Ratio is defined
            # differently and a card that contradicts the filing's stated ratio reads as an error.
            if cover <= 0:
                said = "operating profit does not cover interest at all"
            elif cover < 1:
                said = "operating profit covers only part of the interest"
            else:
                said = "operating profit barely covers interest"
            shown = f"{cover:+.2f}" if abs(cover) < 0.05 else f"{cover:.1f}"
            out.append(_signal("DISTRESS", "WARNING",
                               f"EBIT/interest {shown}x ({q}): {said}."))
    if sheet.get("net_worth_cr") is not None and sheet["net_worth_cr"] <= 0 and sheet.get("source_news_id") == news_id:
        out.append(_signal("DISTRESS", "WARNING", f"Negative net worth (₹{sheet['net_worth_cr']:g} Cr): read it as a debt-service story, not on P/E."))
    return out


def _short_term(rating: str | None) -> str | None:
    if not rating:
        return None
    m = re.search(r"(?<![A-Z0-9+])(A[1-4]\+?|D)(?![\w+])", re.sub(r"(A[1-4])\s+\+", r"\1+", rating.upper()))
    return m[1] if m and m[1] in SHORT_TERM_LADDER else None


def rating_signals(before: dict | None, after: dict, news_id: str) -> list[dict]:
    """M38: the short-term rating ladder, negative outlooks and Issuer Not Cooperating."""
    sheets = [s for s in after.get("balance_sheet", []) if s.get("credit_rating")]
    if not sheets or sheets[-1].get("source_news_id") != news_id:
        return []
    now = sheets[-1]
    prev = next((s for s in reversed((before or {}).get("balance_sheet", [])) if s.get("credit_rating")), None)
    out = []
    text = f"{now.get('credit_rating')} {now.get('rating_outlook') or ''}".lower()
    if "not cooperating" in text or re.search(r"\binc\b", text):
        out.append(_signal("RATING_LIQUIDITY", "WARNING", "Rated 'Issuer Not Cooperating': the company stopped sharing information with the agency."))
    a, b = _short_term(now.get("credit_rating")), _short_term(prev.get("credit_rating")) if prev else None
    if a and b and SHORT_TERM_LADDER.index(a) > SHORT_TERM_LADDER.index(b):
        out.append(_signal("RATING_LIQUIDITY", "WARNING", f"Short-term rating cut {b} → {a}: near-term liquidity is weaker."))
    if "negative" in (now.get("rating_outlook") or "").lower() and "negative" not in ((prev or {}).get("rating_outlook") or "").lower():
        out.append(_signal("RATING_LIQUIDITY", "WARNING", "Rating outlook revised to Negative."))
    return out


def festive_signals(after: dict, news_id: str) -> list[dict]:
    """M46: October and November volumes together, since Diwali moves between them."""
    from .dossier import reported_by

    out = []
    for m in after.get("financial_metrics", []):
        if m["metric"] not in FESTIVE_METRICS or not reported_by(m, news_id) or not m["period"].startswith("NOV-"):
            continue
        year = int(m["period"][4:])
        series = {e["period"]: e["value"] for e in after.get("financial_metrics", [])
                  if e["metric"] == m["metric"] and (not business_line.enabled() or e.get("line") == m.get("line"))}
        now = [series.get(f"OCT-{year}"), series.get(f"NOV-{year}")]
        last = [series.get(f"OCT-{year - 1}"), series.get(f"NOV-{year - 1}")]
        if all(v is not None for v in now + last) and sum(last):
            g = (sum(now) / sum(last) - 1) * 100
            out.append(_signal("FESTIVE_SEASON", "POSITIVE" if g >= 0 else "WARNING",
                               f"October + November together {g:+.0f}% YoY: the fair read of the festive season, wherever Diwali fell."))
    return out


def warrant_deadlines(output, filing) -> list[tuple[str, str]]:
    """M31: preferential warrants must be converted (the remaining 75% paid) within 18 months.
    Returns (date, description) catalysts for an allotment or approval of warrants."""
    out = []
    for action in output.dossier_delta.capital_actions:
        if "warrant" not in (action.instrument or "").lower():
            continue
        start = date.fromisoformat(filing.filing_date)
        deadline = start + timedelta(days=548)
        size = f" ₹{action.amount_cr:g} Cr" if action.amount_cr else ""
        price = f" at ₹{action.issue_price:g}" if action.issue_price else ""
        out.append((deadline.isoformat(), f"18-month warrant conversion deadline (issued {start.isoformat()}{size}{price}): "
                    "the remaining 75% is due, or the warrants lapse."))
    return out


REVENUE_WORDS = re.compile(r"revenue|sales|turnover|top[- ]?line", re.I)


def asset_turn_signals(card: dict, sector_name: str, band: tuple[float, float] | None) -> list[dict]:
    """M2: revenue a capex is guided to bring, against the sector's normal asset turns. Above 1.5x the
    top of the band, the guidance is ambitious for the machinery (or the work is outsourced)."""
    deal = card.get("deal_value") or {}
    capex = deal.get("amount_cr")
    if not band or deal.get("kind") != "CAPEX" or not capex or capex <= 0:
        return []
    guided = [q for q in card.get("quantified_impact") or []
              if q.get("unit") == "INR_CR" and q.get("result") and REVENUE_WORDS.search(q.get("label") or "")
              and q.get("check") != "MISMATCH"]
    if not guided:
        return []
    revenue = max(q["result"] for q in guided)
    turns = revenue / capex
    lo, hi = band
    if turns > hi * 1.5:
        return [_signal("ASSET_TURN", "WARNING", f"₹{revenue:g} Cr of revenue from ₹{capex:g} Cr of capex is {turns:.1f}x asset turns, "
                        f"against {lo:g}-{hi:g}x normal for {sector_name.replace('_', ' ')}: ambitious, or the making is outsourced.")]
    if turns < lo * 0.5:
        return [_signal("ASSET_TURN", "INFO", f"₹{revenue:g} Cr of revenue from ₹{capex:g} Cr of capex is only {turns:.1f}x asset turns "
                        f"(normal {lo:g}-{hi:g}x): conservative guidance, or a long gestation.")]
    return []


ROIIC_SINCE = "2024-12-31"          # blueprint M35: capital and EBITDA added since January 2025
COMPOUNDER_PCT, DILUTER_PCT = 20.0, 8.0


def _sheet_date(sheet: dict):
    return due_date(sheet.get("period")) or (date.fromisoformat(sheet["as_of"][:10]) if sheet.get("as_of") else None)


def _capital(sheet: dict) -> float | None:
    """Invested capital: net worth + gross debt - cash (cash only when stated)."""
    if sheet.get("net_worth_cr") is None or sheet.get("gross_debt_cr") is None:
        return None
    return sheet["net_worth_cr"] + sheet["gross_debt_cr"] - (sheet.get("cash_cr") or 0)


def roiic(dossier: dict, since: str = ROIIC_SINCE) -> dict | None:
    """M35: annual EBITDA added per rupee of capital added since January 2025.

    EBITDA is compared like for like: trailing four quarters when both ends have them, else the
    same fiscal quarter a whole number of years apart, annualised. Capital is net worth + gross
    debt - cash from the balance sheets closest to each end. Needs at least a year between ends.
    """
    t = _table(dossier)
    start = date.fromisoformat(since)
    quarters = sorted({p for (k, p) in t if k == "ebitda" and p.startswith("Q") and due_date(p)}, key=due_date)
    if not quarters:
        return None
    latest = quarters[-1]
    base = None
    for p in quarters:
        span = (due_date(latest) - due_date(p)).days
        if due_date(p) >= start and span >= 360 and p[:2] == latest[:2]:
            base = p
            break
    if not base:
        return None

    def run_rate(q: str) -> tuple[float, str]:
        ttm = [t.get(("ebitda", p)) for p in _quarters_back(q, 4)]
        if len(ttm) == 4 and all(v is not None for v in ttm):
            return sum(ttm), "TTM"
        return t[("ebitda", q)] * 4, "annualised quarter"

    (now, how_now), (then, how_then) = run_rate(latest), run_rate(base)
    if how_now != how_then:
        now, then, how_now = t[("ebitda", latest)] * 4, t[("ebitda", base)] * 4, "annualised quarter"
    sheets = [(d, c) for s in dossier.get("balance_sheet", []) if (d := _sheet_date(s)) and (c := _capital(s)) is not None]
    if len(sheets) < 2:
        return None
    first = min(sheets, key=lambda x: abs((x[0] - due_date(base)).days))
    last = max(sheets, key=lambda x: x[0])
    added_capital, added_ebitda = last[1] - first[1], now - then
    out = {"from": base, "to": latest, "basis": how_now, "ebitda_added_cr": round(added_ebitda, 1),
           "capital_added_cr": round(added_capital, 1), "capital_from": first[0].isoformat(), "capital_to": last[0].isoformat()}
    if last[0] <= first[0] or abs(added_capital) < 1:
        out.update(pct=None, verdict="SELF_FUNDED" if added_ebitda > 0 else None)
        return out
    pct = added_ebitda / added_capital * 100 if added_capital > 0 else None
    out["pct"] = round(pct, 1) if pct is not None else None
    if added_capital <= 0:
        out["verdict"] = "SELF_FUNDED" if added_ebitda > 0 else None
    elif pct >= COMPOUNDER_PCT:
        out["verdict"] = "COMPOUNDER"
    elif pct < DILUTER_PCT:
        out["verdict"] = "DILUTER"
    else:
        out["verdict"] = None
    return out


def roiic_signals(after: dict, news_id: str) -> list[dict]:
    """M35 on the card that brings a new quarter or balance sheet."""
    r = roiic(after)
    if not r or not r.get("verdict") or _latest_quarter(after, news_id) != r["to"]:
        return []
    text = (f"Since {r['from']}: EBITDA run-rate {r['ebitda_added_cr']:+g} Cr on {r['capital_added_cr']:+g} Cr of capital added"
            + (f", ROIIC {r['pct']:.0f}%" if r.get("pct") is not None else "") + ".")
    if r["verdict"] == "COMPOUNDER":
        return [_signal("CAPITAL_COMPOUNDER", "POSITIVE", text)]
    if r["verdict"] == "DILUTER":
        return [_signal("CAPITAL_DILUTER", "WARNING", text + " Capital is growing faster than the earnings it buys.")]
    return [_signal("CAPITAL_COMPOUNDER", "POSITIVE", text + " Growth funded from internal accruals.")]
