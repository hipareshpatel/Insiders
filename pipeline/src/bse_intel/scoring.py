"""The 4-gate signal funnel and the 0–100 actionability score (blueprint §11), computed by code.

The model writes the card; this module decides how much it matters, from figures the platform
holds (memory as of the filing, the company's market data, the automatic checks). Every point is
explained in ``reasons`` so the score can be audited on the card.

Pillars (max): economic magnitude vs scale 30, margin and operating leverage 25, balance sheet and
funding 20, management credibility 15, disclosure completeness and price timing 10; forensic
penalties up to -50, and any Gate 4 veto caps the score at 35. Impact: >= 70 HIGH, 40–69
MODERATE, < 40 LOW. A card is a Top Signal when it scores >= 70, passes Gate 4 and at least two
of Gates 1–3.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date

from .periods import due_date

REVENUE = ("revenue", "revenue_from_operations", "total_revenue", "net_sales", "sales")
HIGH, MODERATE = 70, 40
DELIVERED = {"DELIVERED"}
BROKEN = {"MISSED", "DELAYED", "WITHDRAWN"}
# Module 5: capacity added at a site already running ("its existing GIDC Ankleshwar site").
BROWNFIELD = re.compile(r"\bexisting (?:[\w&.-]+ ){0,3}(?:site|plant|facility|unit|complex|premises|campus)\b|brownfield|debottleneck")
T2T_GROUPS = {"T", "XT", "Z", "ZP", "TS", "MT"}  # module 50: trade-to-trade and restricted groups


@dataclass
class Score:
    total: int
    impact: str
    actionable: bool
    pillars: dict[str, int]
    gates: dict[str, bool]
    vetoes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    credibility: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def credibility(dossier: dict | None) -> tuple[float | None, int, int]:
    """Delivered / (delivered + broken) promises in memory, as a percentage, with the counts."""
    delivered = broken = 0
    for g in (dossier or {}).get("guidance", []):
        status = g.get("status")
        delivered += status in DELIVERED
        broken += status in BROKEN
    for p in (dossier or {}).get("predictions", []):  # Loop 2: numeric targets checked against results
        delivered += p.get("status") == "MET"
        broken += p.get("status") == "MISSED"
    total = delivered + broken
    return (round(delivered / total * 100, 1) if total else None), delivered, total


def calibration(dossier: dict | None, cutoff: str = "~") -> dict | None:
    """Loop 2 (blueprint §12.2): how this management's numbers and dates turn out, as a rule the
    analyst applies to new guidance. Uses only targets and promises resolved before ``cutoff``.

    * delivery ratio: actual / target for numeric targets checked against results (">=" targets
      only, where more is better), averaged;
    * slippage: how many months late dated promises were delivered or declared delayed.
    """
    d = dossier or {}
    ratios = [p["actual"] / p["value"] for p in d.get("predictions", [])
              if p.get("status") in ("MET", "MISSED") and p.get("comparison") == ">=" and p.get("value")
              and p.get("actual") is not None and (p.get("resolved_on") or "") < cutoff and p["value"] > 0]
    late: list[float] = []
    for g in d.get("guidance", []):
        due = g.get("due_date")
        history = [h for h in g.get("status_history", []) if h["as_of"] < cutoff]
        if not due or not history:
            continue
        settled = next((h for h in history if h["status"] in ("DELIVERED", "DELAYED", "MISSED")), None)
        if settled:
            months = (date.fromisoformat(settled["as_of"][:10]) - date.fromisoformat(due)).days / 30.4
            late.append(max(months, 0.0) if settled["status"] == "DELIVERED" else max(months, 3.0))
    if not ratios and not late:
        return None
    parts = []
    out: dict = {}
    if ratios:
        ratio = sum(ratios) / len(ratios)
        out.update(delivery_ratio=round(ratio, 2), targets_checked=len(ratios))
        word = "beats" if ratio >= 1.05 else "falls short of" if ratio < 0.95 else "meets"
        parts.append(f"Management {word} its numeric targets: {ratio:.2f}x of target on average ({len(ratios)} checked)")
    if late:
        avg = sum(late) / len(late)
        out.update(avg_months_late=round(avg, 1), dated_promises=len(late))
        parts.append("dated promises land on time" if avg < 1 else
                     f"dated promises land about {avg:.0f} month{'s' if round(avg) != 1 else ''} late on average ({len(late)} resolved)")
    out["rule"] = "; ".join(parts) + "." + (" Apply that discount to new guidance." if out.get("delivery_ratio", 1) < 0.95 or out.get("avg_months_late", 0) >= 3 else "")
    return out


def ttm_revenue(dossier: dict | None) -> tuple[float, str] | None:
    """Trailing revenue: the last four quarters when memory has them, else the latest year, else the
    latest quarter x 4."""
    rows = [m for m in (dossier or {}).get("financial_metrics", [])
            if m.get("metric") in REVENUE and m.get("value") and (m.get("unit") or "INR_CR") == "INR_CR" and due_date(m["period"])]
    quarters = sorted((m for m in rows if m["period"].startswith("Q")), key=lambda m: due_date(m["period"]))
    by_period = {m["period"]: m["value"] for m in quarters}
    if len(by_period) >= 4:
        last4 = sorted(by_period.items(), key=lambda kv: due_date(kv[0]))[-4:]
        return sum(v for _, v in last4), f"TTM to {last4[-1][0]}"
    years = sorted((m for m in rows if m["period"].startswith("FY")), key=lambda m: due_date(m["period"]))
    if years:
        return years[-1]["value"], years[-1]["period"]
    if quarters:
        return quarters[-1]["value"] * 4, f"{quarters[-1]['period']} x 4"
    return None


def _net_worth(dossier: dict | None) -> float | None:
    for snap in reversed((dossier or {}).get("balance_sheet", [])):
        if snap.get("net_worth_cr") is not None:
            return snap["net_worth_cr"]
    return None


def _band(ratio_pct: float) -> int:
    """Pillar 1 points for a catalyst's size as a share of the company's scale."""
    if ratio_pct >= 25:
        return min(30, 25 + int((ratio_pct - 25) / 10))
    if ratio_pct >= 15:
        return 15 + int((ratio_pct - 15) * 0.9)
    if ratio_pct >= 5:
        return 5 + int(ratio_pct - 5)
    return int(ratio_pct * 0.8)


def score(card: dict, event_type: str, signals: list[dict], dossier: dict | None, company: dict | None,
          needs_review: bool, model_impact: str, dampened: bool = False) -> Score:
    company = company or {}
    reasons: list[str] = []
    vetoes: list[str] = []
    pillars = {"magnitude": 0, "margin": 0, "balance_sheet": 12, "credibility": 8, "disclosure": 0, "penalty": 0}
    kinds = {s["type"] for s in signals}
    texts = " ".join([card.get("headline", ""), *card.get("what_happened", [])]).lower()

    # --- Pillar 1 / Gate 1: economic magnitude relative to the company's scale
    deal = card.get("deal_value") or {}
    amount = deal.get("amount_cr")
    ttm = ttm_revenue(dossier)
    market_cap = company.get("market_cap_cr")
    ratios: list[tuple[float, str]] = []
    if amount and amount > 0:
        if deal.get("kind") in ("ORDER", "CAPEX", "OTHER") and ttm:
            ratios.append((amount / ttm[0] * 100, f"{amount:g} Cr is {amount / ttm[0] * 100:.0f}% of {ttm[1]} revenue"))
        if deal.get("kind") in ("ACQUISITION", "DIVESTMENT", "FUNDRAISE", "CAPEX") and market_cap:
            ratios.append((amount / market_cap * 100, f"{amount / market_cap * 100:.0f}% of market cap"))
    for q in card.get("quantified_impact") or []:
        if q.get("check") == "VERIFIED" and q.get("unit") == "INR_CR" and q.get("result") and ttm:
            ratios.append((abs(q["result"]) / ttm[0] * 100, f"\"{q['label']}\" is {abs(q['result']) / ttm[0] * 100:.0f}% of revenue"))
    gate1 = False
    if ratios:
        best = max(ratios)
        pillars["magnitude"] = _band(best[0])
        gate1 = best[0] >= 15
        reasons.append(f"Size: {best[1]}")
    else:
        # no figure to put in proportion: the analyst's impact call stands in, conservatively
        pillars["magnitude"] = {"HIGH": 18, "MODERATE": 10}.get(model_impact, 3)
        reasons.append("Size: no stated amount to compare with revenue or market cap; using the analyst's impact call")

    # --- Pillar 2 / Gate 2: margin, operating leverage, trend inflection, promises delivered
    results = card.get("results") or {}
    rev_yoy = (results.get("revenue") or {}).get("yoy_pct")
    margin_bps = (results.get("ebitda_margin") or {}).get("yoy_bps")
    pat = results.get("pat") or {}
    gate2 = False
    if margin_bps is not None:
        if margin_bps >= 300:
            pillars["margin"] = 22
        elif margin_bps >= 100:
            pillars["margin"] = 10 + int((margin_bps - 100) / 22)
        else:
            pillars["margin"] = max(0, 5 + int(margin_bps / 50))
        reasons.append(f"Margin {margin_bps:+.0f} bps YoY")
    turnaround = pat.get("value") is not None and pat.get("prev_year") is not None and pat["prev_year"] < 0 < pat["value"]
    if (rev_yoy is not None and rev_yoy >= 20 and (margin_bps or 0) >= 150) or turnaround:
        gate2 = True
        pillars["margin"] = max(pillars["margin"], 20)
        reasons.append("Earnings inflection" + (" (loss to profit)" if turnaround else f" (revenue {rev_yoy:+.0f}% YoY)"))
    if "PROMISE_DELIVERED" in kinds:
        gate2 = True
        reasons.append("Delivers a promise in memory")
    if "VOLUME_STREAK" in kinds:
        gate2 = True
        pillars["margin"] = max(pillars["margin"], 15)
        reasons.append("Multi-month volume streak above 25% YoY")
    shifts = [s for s in signals if s["type"] == "METRIC_SHIFT" and s["severity"] == "POSITIVE"]
    if event_type == "MONTHLY_BUSINESS_UPDATE" and shifts:
        pillars["margin"] = max(pillars["margin"], 14)
    if deal.get("expansion") == "BROWNFIELD" or BROWNFIELD.search(texts):
        pillars["margin"] = max(pillars["margin"], 20)
        reasons.append("Brownfield addition at an existing site")
    if pillars["margin"] == 0:
        pillars["margin"] = 5

    # --- Pillar 3: balance sheet and funding quality
    net_worth = _net_worth(dossier)
    dilution = max((_post_money(s["text"]) for s in signals if s["type"] == "DILUTION"), default=0.0)
    if net_worth is not None and net_worth <= 0:
        pillars["balance_sheet"] = 3
        reasons.append("Negative net worth")
    elif dilution > 30:
        pillars["balance_sheet"] = 4
        reasons.append(f"Heavy dilution ({dilution:.0f}% post-money)")
    elif any(w in texts for w in ("grant", "subsidy", "internal accruals", "debt-free", "debt free")):
        pillars["balance_sheet"] = 18
        reasons.append("Funded from accruals or non-dilutive support")

    # --- Pillar 4: management execution credibility
    cred, delivered, total = credibility(dossier)
    if "PROMISE_DELIVERED" in kinds:
        pillars["credibility"] = 15
    elif cred is not None:
        pillars["credibility"] = 13 if cred >= 80 else 8 if cred >= 50 else 3
        reasons.append(f"Credibility {delivered}/{total} promises delivered")
    if "GUIDANCE_BREACH" in kinds:
        pillars["credibility"] = min(pillars["credibility"], 4)

    # --- Pillar 5 / Gate 3: disclosure completeness and price timing
    grounding = card.get("grounding") or {}
    if not grounding.get("ungrounded") and not card.get("missing_disclosures"):
        pillars["disclosure"] += 5
    ret_1m, ret_1w = company.get("ret_1m"), company.get("ret_1w")
    if ret_1m is not None and -10 <= ret_1m <= 12:
        pillars["disclosure"] += 5
    turnover = company.get("median_turnover_cr")
    trade_to_trade = (company.get("bse_group") or "").upper() in T2T_GROUPS
    gate3 = (ret_1m is not None and ret_1m <= 15 and (ret_1w is None or ret_1w <= 10)
             and (turnover is None or turnover >= 0.5) and not trade_to_trade)
    if trade_to_trade:
        reasons.append(f"Trade-to-trade (BSE group {company['bse_group']}): tight circuits, hard to exit")
    if turnover is not None and turnover < 0.5:
        reasons.append(f"Thin liquidity (₹{turnover:.2f} Cr a day)")

    # --- Penalties and Gate 4 vetoes
    if "WORKING_CAPITAL_STRAIN" in kinds:
        pillars["penalty"] -= 20
        vetoes.append("Working capital strain")
    if needs_review:
        vetoes.append("Unverified figures or failed math check")
    rating = " ".join(str(s.get("credit_rating") or "") for s in (dossier or {}).get("balance_sheet", [])[-1:]).lower()
    if ("not cooperating" in rating or " inc" in f" {rating}") and "Credit rating: issuer not cooperating" not in vetoes:
        vetoes.append("Credit rating: issuer not cooperating")
    if any(s["type"] == "ORDER_FLOW" and "not a new order" in s["text"].lower() for s in signals):
        vetoes.append("Stage update of an order already counted")
    if any(s["type"] == "AUDIT_FLAG" and s["severity"] == "WARNING" for s in signals):
        vetoes.append("Auditor qualification or mid-term resignation")
    if any(s["type"] == "OWNERSHIP_SHIFT" and s["severity"] == "WARNING" for s in signals):
        pillars["penalty"] -= 10
    # earnings-quality forensics (quality.py): each counts once
    for kind, points, why in (("LOW_QUALITY_BEAT", 10, "Profit driven by other income"), ("Q4_TRUE_UP", 10, "Q4 audit true-up"),
                              ("RECURRING_ONE_OFFS", 5, "Recurring exceptional items"), ("DISTRESS", 15, "Weak interest cover or negative net worth")):
        if any(s["type"] == kind and s["severity"] == "WARNING" for s in signals):
            pillars["penalty"] -= points
            reasons.append(f"Penalty: {why}")
    if any(s["type"] == "RATING_LIQUIDITY" and "not cooperating" in s["text"].lower() for s in signals) \
            and "Credit rating: issuer not cooperating" not in vetoes:
        vetoes.append("Credit rating: issuer not cooperating")

    if dampened:  # Loop 1: HIGH cards of this sector and event have not moved prices
        pillars["penalty"] -= 5
        reasons.append("Calibration: high-impact cards of this kind have not moved prices so far (-5)")
    total_points = sum(pillars.values())
    if vetoes:
        total_points = min(total_points, 35)
    total_points = max(0, min(100, total_points))
    gates = {"magnitude": gate1, "inflection": gate2, "price": gate3, "clean": not vetoes}
    impact = "HIGH" if total_points >= HIGH else "MODERATE" if total_points >= MODERATE else "LOW"
    actionable = total_points >= HIGH and gates["clean"] and sum((gate1, gate2, gate3)) >= 2
    return Score(total_points, impact, actionable, pillars, gates, vetoes, reasons, cred)


def _post_money(text: str) -> float:
    m = re.search(r"([\d.]+)% post-money", text)
    return float(m.group(1)) if m else 0.0
