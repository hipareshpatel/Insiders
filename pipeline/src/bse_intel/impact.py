"""Clear events that make a card HIGH impact whatever its score (owner, 2026-10-20).

The 0-100 score needs several pillars at once to reach 70, so 3 of 850 live cards were HIGH and the site's
high-impact views stayed empty (design audit, 2026-10-20). A card is also HIGH when one of these events is in its
code-made blocks or signals, each read from the filing's own figures or from memory, never from the model's words:

- results: PAT up or down 30% or more YoY, a loss turned to profit or back, or EBITDA margin moving 300 bps or more;
- an order worth 10% or more of a year's revenue (a year's share when it runs over several years);
- an acquisition or sale worth 5% or more of market cap; a raise of 11% or more of it (about 10% dilution);
- a credit rating moved by a notch or more, or its outlook changed (a reaffirmation is not);
- a USFDA warning letter or import alert;
- an auditor's qualified, adverse or disclaimer opinion, or the auditor resigning; a promoter pledge invoked;
- the MD, CEO or CFO leaving;
- a promise in memory delivered or missed, on the filing whose figures settle it.
A penalty or demand against net worth is not here yet: a case's amount is not stored.
"""

from __future__ import annotations

import re

PAT_PCT, MARGIN_BPS = 30, 300
ORDER_PCT, DEAL_PCT, RAISE_PCT = 10, 5, 11
_TURNS = {"LOSS_TO_PROFIT": "loss to profit", "PROFIT_TO_LOSS": "profit to loss"}
_INVOKED = re.compile(r"\binvo(?:ked|cation)\b", re.I)
# a modified opinion or the auditor leaving; an emphasis of matter carried in memory is not (it made a company
# secretary's resignation HIGH in the first measurement)
_AUDIT_SERIOUS = re.compile(r"\b(?:qualified|adverse|disclaimer)\b|\bresign", re.I)
# a promise is settled by the figures a filing reports: results, a call, a business update, a commissioning. A
# "deadline passed" from memory on any other filing is not news of the filing (a promoter's encumbrance declaration
# was HIGH on an FY25 margin target)
_SETTLES = {"RESULTS", "CONCALL_PRESENTATION", "MONTHLY_BUSINESS_UPDATE", "CAPEX", "ANNUAL_REPORT"}


def high_reasons(card: dict, event_type: str, signals: list[dict], top_exit: bool = False) -> list[str]:
    """Why the card is HIGH impact by these rules; empty when none applies."""
    out: list[str] = []
    results = card.get("results") or {}
    pat = results.get("pat") or {}
    if pat.get("yoy_turn") in _TURNS:
        out.append(f"PAT turned from {_TURNS[pat['yoy_turn']]} YoY")
    elif pat.get("yoy_pct") is not None and abs(pat["yoy_pct"]) >= PAT_PCT:
        out.append(f"PAT {pat['yoy_pct']:+.0f}% YoY")
    margin = (results.get("ebitda_margin") or {}).get("yoy_bps")
    if margin is not None and abs(margin) >= MARGIN_BPS:
        out.append(f"EBITDA margin {margin:+.0f} bps YoY")

    scale = card.get("scale") or {}
    against = {a.get("label", ""): a.get("pct") for a in scale.get("against") or [] if a.get("pct") is not None}
    noun = scale.get("noun")
    if noun == "order":
        year = (scale.get("per_year") or {}).get("pct")
        if year is None:
            year = next((p for label, p in against.items() if label.startswith("FY")), None)
        if year is not None and year >= ORDER_PCT:
            out.append(f"Order {year:.0f}% of a year's revenue")
    cap = against.get("market cap")
    if cap is not None:
        if noun == "raise" and cap >= RAISE_PCT:
            out.append(f"Raise {cap:.0f}% of market cap")
        elif noun in ("deal", "sale", "capex") and cap >= DEAL_PCT:
            out.append(f"Deal {cap:.0f}% of market cap")

    rating = card.get("rating_change") or {}
    if rating.get("before"):
        if rating.get("notches"):
            out.append(f"Rating moved {abs(rating['notches'])} notch{'es' if abs(rating['notches']) > 1 else ''}")
        elif rating.get("before_outlook") and rating.get("after_outlook") \
                and rating["before_outlook"].lower() != rating["after_outlook"].lower():
            out.append(f"Rating outlook {rating['before_outlook']} to {rating['after_outlook']}")

    case = card.get("case_stage") or {}
    reached = set(case.get("reached") or []) | ({case["steps"][case["at"]]} if case.get("steps") and case.get("at") is not None
                                                else set())
    for step in ("Warning letter", "Import alert"):
        if case.get("track") == "USFDA" and step in reached:
            out.append(f"USFDA {step.lower()}")

    for s in signals or []:
        kind = s.get("type")
        if kind == "AUDIT_FLAG" and _AUDIT_SERIOUS.search(s.get("text") or ""):
            out.append("Auditor's opinion modified or auditor resigned")
        elif kind == "PLEDGE" and _INVOKED.search(s.get("text") or ""):
            out.append("Promoter pledge invoked")
        elif kind in ("PROMISE_DELIVERED", "GUIDANCE_BREACH") and event_type in _SETTLES \
                and not (s.get("text") or "").startswith("Deadline passed"):
            out.append("Promise delivered" if kind == "PROMISE_DELIVERED" else "Promise broken")
    if event_type == "MANAGEMENT_CHANGE" and top_exit:
        out.append("MD, CEO or CFO leaving")
    return list(dict.fromkeys(out))
