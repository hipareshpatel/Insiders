"""Figures a results card may state, computed in code from the XBRL file (owner, 24 Oct 2026: "should be calculated
using code, not ai").

The model was asked to work out cost shares, margins in basis points and cash conversion itself, which computed.py
then removed as unproduced, so results cards went without them (a rival's Kajaria card gave raw material -178 bps,
cash conversion 103% and inventory -9%; ours gave four lines). Here code works them out and the prompt gets them as a
block: the model chooses which matter and says what the filing gives as their cause.

The rule computed.py keeps for a change holds here too: a year-ago figure counts only when this filing prints it, which
is how a restated, re-based or other-basis comparative (one filled in from memory) is told apart. Each fact carries
its figure and sign, so the pool accepts "fell 178 bps" and not "rose 178 bps".
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from .grounding import SourceIndex
from .periods import prior_year_period

# Cost of goods: materials consumed, goods bought for resale, and the change in inventories of goods
_MATERIALS = ("raw_material_cost", "purchases_stock_in_trade", "inventory_change")
# Balance-sheet lines worth a comparison with the last statement in memory
# Not cash, nor net debt from it: the file's cash is cash and cash equivalents alone, without bank deposits and liquid
# investments, and Kajaria's Q2FY27 read "net debt ₹291.98 Cr" where its release states net cash of ₹635 Cr
_BALANCE = (("inventories_cr", "inventories"), ("receivables_cr", "trade receivables"), ("gross_debt_cr", "borrowings"))

MIN_BPS = 10        # a smaller move of a share or margin is rounding
MAX_TAX = 60        # an effective rate above it (or below zero) is a small or one-off profit, not a rate
LENDER_TEMPLATES = {"BANKING", "NBFC", "GI", "LI"}
_LENDER_LINES = {"interest_earned", "interest_expended", "gnpa_pct", "nnpa_pct", "provisions", "gross_premium",
                 "net_premium", "incurred_claims"}
_ORDER = ("EBITDA margin", "Cost of materials", "Cash flow", "Balance sheet", "Employee cost", "Net profit",
          "Effective tax rate", "Other income")


@dataclass
class Fact:
    text: str
    kind: str = ""      # "pct" or "bps": the figure the pool takes, when the fact has one
    value: float = 0.0
    sign: int = 0       # +1 up, -1 down, 0 a level
    base: str = ""      # "revenue" for a share of revenue: computed.py checks a share against its base
    memory_ref: str = ""  # a point set against memory (guidance, a deal): goes to "Our reading" citing this id


def _cr(value: float) -> str:
    text = f"{abs(value):,.2f}".rstrip("0").rstrip(".")
    return f"{'-' if value < 0 else ''}₹{text} Cr"


def _bps(now: float, then: float) -> tuple[int, int]:
    if not (math.isfinite(now) and math.isfinite(then)):
        return 0, 0
    move = round((now - then) * 100)
    return abs(move), (move > 0) - (move < 0)


def _word(sign: int) -> str:
    return "up" if sign > 0 else "down" if sign < 0 else "unchanged"


def _printed(index: SourceIndex | None, value: float | None) -> bool:
    """This filing prints the figure (in its own unit): the like-for-like test for a comparative."""
    if index is None or value is None or not value:
        return False
    return index.stated_crore(round(abs(value), 2), 2, tolerance=max(0.006, abs(value) * 0.0005))


def results_facts(tagged, filed_text: str, balance_history: list[dict] | None = None) -> list[Fact]:
    """The cost shares, margins, tax rate, other-income share, cash conversion and balance-sheet moves of a results
    file. Nothing for a bank or an insurer (no cost of goods or EBITDA in their files) beyond what applies."""
    if tagged is None or getattr(tagged, "kind", "") != "RESULTS" or not tagged.period:
        return []
    val = {(m.metric, m.period): m.value for m in tagged.metrics if m.value is not None}
    index = SourceIndex(filed_text) if filed_text else None
    now_p, ago_p = tagged.period, prior_year_period(tagged.period) or ""
    out: list[Fact] = []
    # a bank, lender or insurer: no cost of goods, EBITDA, cash conversion or working capital means anything there
    lender = getattr(tagged, "template", "") in LENDER_TEMPLATES or any(m in _LENDER_LINES for m, _ in val)

    def get(metric: str, period: str) -> float | None:
        return val.get((metric, period))

    def like_for_like(*metrics: str) -> bool:
        """Each year-ago input of a comparison is printed in this filing."""
        return all(_printed(index, get(m, ago_p)) for m in metrics if get(m, ago_p))

    revenue, revenue0 = get("revenue", now_p), get("revenue", ago_p)
    # revenue that is not the business: GOCL's ₹4.1 Cr against ₹62.65 Cr of other income gave "net margin 985%"
    token_revenue = bool(revenue) and (get("other_income", now_p) or 0) > 0.5 * revenue

    def share(label: str, part_now: float | None, part_ago: float | None, inputs: tuple[str, ...]) -> None:
        # a zero is the template's filler (a services company's "cost of materials 0.0%"), and a loss is no margin
        if not part_now or part_now < 0 or not revenue or revenue <= 0 or token_revenue:
            return
        level = part_now / revenue * 100
        if level > 100:
            return
        out.append(Fact("", "pct", round(level, 1), base="revenue"))
        before = part_ago / revenue0 * 100 if part_ago and part_ago > 0 and revenue0 and revenue0 > 0 else None
        move, sign = _bps(level, before) if before is not None else (0, 0)
        # a move under 10 bps is rounding, not news ("up 2 bps", "unchanged 0 bps")
        if before is not None and move >= MIN_BPS and like_for_like("revenue", *inputs):
            out.append(Fact("", "pct", round(before, 1), base="revenue"))
            out.append(Fact(f"{label} {now_p}: {level:.1f}% of revenue against {before:.1f}% in {ago_p} "
                            f"({_word(sign)} {move} bps)", "bps", move, sign))
        else:
            out.append(Fact(f"{label} {now_p}: {level:.1f}% of revenue"))

    def total(metrics: tuple[str, ...], period: str) -> float | None:
        parts = [get(m, period) for m in metrics]
        return sum(p for p in parts if p is not None) if parts[0] is not None else None

    if not lender:
        share("Cost of materials and goods", total(_MATERIALS, now_p), total(_MATERIALS, ago_p),
              tuple(m for m in _MATERIALS if get(m, ago_p)))
        share("Employee cost", get("employee_cost", now_p), get("employee_cost", ago_p), ("employee_cost",))
        margin, margin0 = get("ebitda_margin", now_p), get("ebitda_margin", ago_p)
        if margin is not None and margin0 is not None and margin > 0 and margin0 > 0 and like_for_like("revenue", "pbt"):
            move, sign = _bps(margin, margin0)
            if move >= MIN_BPS:
                out.append(Fact("", "pct", round(margin0, 1)))
                out.append(Fact(f"EBITDA margin {now_p}: {margin:.1f}% against {margin0:.1f}% in {ago_p} "
                                f"({_word(sign)} {move} bps)", "bps", move, sign))
        # the shareholders' profit where the file gives it, as the headline does (on-off review: Varmora 3.1% beside a
        # headline whose profit gives 4.0%)
        profit = "pat_owners" if get("pat_owners", now_p) else "pat"
        share("Net profit", get(profit, now_p), get(profit, ago_p), (profit,))

    pbt, pbt0 = get("pbt", now_p), get("pbt", ago_p)

    def ratio(part: float | None, whole: float | None, top: float) -> float | None:
        """part / whole in %, only where it means something: a profit before tax, and a share within 0-top."""
        if part is None or not whole or whole <= 0:
            return None
        value = part / whole * 100
        return value if 0 <= value <= top else None

    # a lender's other income is its fee income, most of its profit, and no sign of quality
    other_now = None if lender else ratio(get("other_income", now_p), pbt, 100)
    if other_now and other_now >= 0.5:
        text = f"Other income {now_p}: {other_now:.1f}% of profit before tax"
        other_then = ratio(get("other_income", ago_p), pbt0, 100)
        if other_then is not None and like_for_like("pbt", "other_income"):
            text += f" against {other_then:.1f}% in {ago_p}"
            out.append(Fact("", "pct", round(other_then, 1)))
        out.append(Fact(text, "pct", round(other_now, 1)))
    tax_now = ratio(get("tax_expense", now_p), pbt, MAX_TAX)
    if tax_now and tax_now >= 0.5:
        text = f"Effective tax rate {now_p}: {tax_now:.1f}%"
        tax_then = ratio(get("tax_expense", ago_p), pbt0, MAX_TAX)
        if tax_then is not None and like_for_like("pbt", "tax_expense"):
            text += f" against {tax_then:.1f}% in {ago_p}"
            out.append(Fact("", "pct", round(tax_then, 1)))
        out.append(Fact(text, "pct", round(tax_now, 1)))

    # Cash flow: filed for six and twelve months only, so the latest such period in the file; not a lender's, whose
    # operating cash flow is its lending
    # only this period's own half or year: the latest one present was the year-ago half where the current one was
    # missing (SRF's Q2FY27 card read H1FY26's cash flow, on-off review 24 Oct 2026)
    own_cash = {"Q2": "H1", "Q4": ""}.get(now_p[:2])
    periods = [p for p in (f"{own_cash}{now_p[2:]}",) if own_cash is not None and get("operating_cash_flow", p) is not None]
    for period in [] if lender else periods:
        cfo, capex, pat = get("operating_cash_flow", period), get("capex", period), get("pat", period)
        parts = [f"cash from operations {_cr(cfo)}"]
        if cfo > 0 and pat and pat > 0:   # a conversion of a negative cash flow says nothing a reader can use
            conversion = cfo / pat * 100
            parts.append(f"{conversion:.0f}% of net profit {_cr(pat)}")
            out.append(Fact("", "pct", round(conversion)))
        # filed as outflows, with either sign; intangibles (capitalised R&D, software) are capex too
        intangible = sum(abs(get(m, period) or 0) for m in ("capex_intangible", "capex_intangible_wip"))
        if capex or intangible:   # a zero is the template's filler
            spend = abs(capex or 0) + intangible
            what = f"capex {_cr(spend)}" + (f" (of which intangible assets {_cr(intangible)})" if intangible else "")
            parts += [what, f"free cash flow {_cr(cfo - spend)}"]
        out.append(Fact(f"Cash flow {period}: " + ", ".join(parts)))

    sheet = getattr(tagged, "balance_sheet", None)
    if sheet is not None and not sheet.is_empty() and not lender:
        parts = []
        for field, word in _BALANCE:
            now_v = getattr(sheet, field, None)
            if not now_v or now_v < 0:   # a zero is the template's filler
                continue
            # the file's own earlier date (March for a half year), like for like by construction; else the latest
            # earlier statement in memory that carries the line, only when this filing prints it
            own = getattr(tagged, "balance_prior", None)
            then = getattr(own, field, None) if own is not None else None
            earlier = {"period": own.period} if then else None
            if not then:
                rows = [s for s in balance_history or [] if s.get(field) and s.get("period") and s.get("period") != sheet.period]
                earlier = rows[-1] if rows and _printed(index, rows[-1][field]) else None
                then = (earlier or {}).get(field)
            if then and then > 0:
                change = (now_v - then) / then * 100
                parts.append(f"{word} {_cr(now_v)} against {_cr(then)} at {earlier['period']} ({change:+.0f}%)")
                out.append(Fact("", "pct", round(abs(change)), (change > 0) - (change < 0)))
            else:
                parts.append(f"{word} {_cr(now_v)}")
        if parts:
            out.append(Fact(f"Balance sheet {sheet.period or now_p}: " + "; ".join(parts)))
    # the lines a reader looks for first lead, so a card that shows only some shows these
    return sorted(out, key=lambda f: next((i for i, lead in enumerate(_ORDER) if f.text.startswith(lead)), len(_ORDER)))


# the year to date a quarter closes: the period guidance for the year is measured against
_TO_DATE = {"Q1": "Q1", "Q2": "H1", "Q3": "9M", "Q4": ""}
_AMOUNT = re.compile(r"([\d,]+(?:\.\d+)?)\s*(\+)?\s*INR_CR", re.I)
_RANGE = re.compile(r"([\d.]+)\s*(?:-|to|–)\s*([\d.]+)\s*%")
_WORDS = {"ebitda": "EBITDA", "revenue": "revenue", "pat": "net profit"}


def guidance_facts(tagged, guidance: list[dict] | None) -> list[Fact]:
    """The year to date against the year's guidance in memory: "H1FY27 EBITDA ₹546.99 Cr is 55% of the FY27 guidance of
    ₹1,000 Cr plus"; "H1FY27 EBITDA margin 19.56%, above the 18-19% guided". Only guidance for this year, read from its
    stored target, and only for a figure the file carries for the year to date."""
    m = re.fullmatch(r"(Q[1-4])(FY\d{2})", (getattr(tagged, "period", None) or "")) if tagged is not None else None
    if not m:
        return []
    to_date = f"{_TO_DATE[m.group(1)]}{m.group(2)}"
    val = {(x.metric, x.period): x.value for x in tagged.metrics if x.value is not None}
    out = []
    for g in guidance or []:
        if (g.get("due") or "").upper() != m.group(2) or not g.get("id"):
            continue
        metric, target = g.get("metric") or "", str(g.get("target") or "")
        given = (g.get("given_on") or "")[:10]
        if metric in _WORDS and (amount := _AMOUNT.search(target)) and (now := val.get((metric, to_date))) is not None:
            goal = float(amount.group(1).replace(",", ""))
            if goal > 0:
                share = now / goal * 100
                plus = " plus" if amount.group(2) else ""
                out.append(Fact(f"{to_date} {_WORDS[metric]} {_cr(now)} is {share:.0f}% of the {m.group(2)} guidance of "
                                f"{_cr(goal)}{plus} (given {given})", "pct", round(share), memory_ref=g["id"]))
        elif metric == "ebitda_margin" and (band := _RANGE.search(target)) \
                and (now := val.get(("ebitda_margin", to_date))) is not None:
            low, high = sorted((float(band.group(1)), float(band.group(2))))
            where = "above" if now > high else "below" if now < low else "within"
            out.append(Fact(f"{to_date} EBITDA margin {now:.2f}%, {where} the {low:g}-{high:g}% guided for {m.group(2)} "
                            f"(given {given})", "pct", round(now, 2), memory_ref=g["id"]))
    return out


def capex_revisions(deals: list[dict] | None, filed_at: str, days: int = 120) -> list[Fact]:
    """A capex plan in memory whose cost changed lately: "Srikalahasti Plant capex ₹340 Cr against ₹210 Cr first
    approved (+62%)". The first and latest amounts of its own history, so no figure is the model's."""
    try:
        since = (datetime.fromisoformat(filed_at) - timedelta(days=days)).isoformat()
    except (TypeError, ValueError):
        return []
    out = []
    for d in deals or []:
        history = [h for h in d.get("history") or [] if h.get("amount_cr")]
        if d.get("kind") != "CAPEX" or not d.get("id") or len(history) < 2 or (history[-1].get("as_of") or "") < since:
            continue
        first, last = history[0]["amount_cr"], history[-1]["amount_cr"]
        if first > 0 and abs(last - first) >= 0.05 * first:
            change = (last - first) / first * 100
            name = d.get("counterparty") or d.get("segment") or "capex plan"
            out.append(Fact(f"{name} capex {_cr(last)} against {_cr(first)} first approved ({change:+.0f}%)", "pct",
                            round(abs(change)), (change > 0) - (change < 0), memory_ref=d["id"]))
    return out


def block(facts: list[Fact]) -> str:
    """The facts as the prompt's block. Empty when there are none."""
    lines = [f"- {f.text}" for f in facts if f.text]
    if not lines:
        return ""
    return ("Computed by the system from this filing's statements and the company's memory (use these figures as "
            "given, never your own; say what moved them only as the filing or memory states it):\n" + "\n".join(lines))
