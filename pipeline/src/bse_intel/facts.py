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

from dataclasses import dataclass

from .grounding import SourceIndex
from .periods import prior_year_period

# Cost of goods: materials consumed, goods bought for resale, and the change in inventories of goods
_MATERIALS = ("raw_material_cost", "purchases_stock_in_trade", "inventory_change")
# Balance-sheet lines worth a comparison with the last statement in memory
_BALANCE = (("inventories_cr", "inventories"), ("receivables_cr", "trade receivables"), ("cash_cr", "cash and bank"),
            ("gross_debt_cr", "borrowings"))


@dataclass
class Fact:
    text: str
    kind: str = ""      # "pct" or "bps": the figure the pool takes, when the fact has one
    value: float = 0.0
    sign: int = 0       # +1 up, -1 down, 0 a level


def _cr(value: float) -> str:
    text = f"{abs(value):,.2f}".rstrip("0").rstrip(".")
    return f"{'-' if value < 0 else ''}₹{text} Cr"


def _bps(now: float, then: float) -> tuple[int, int]:
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

    def get(metric: str, period: str) -> float | None:
        return val.get((metric, period))

    def like_for_like(*metrics: str) -> bool:
        """Each year-ago input of a comparison is printed in this filing."""
        return all(_printed(index, get(m, ago_p)) for m in metrics if get(m, ago_p))

    revenue, revenue0 = get("revenue", now_p), get("revenue", ago_p)

    def share(label: str, part_now: float | None, part_ago: float | None, inputs: tuple[str, ...]) -> None:
        if part_now is None or not revenue or revenue <= 0:
            return
        level = part_now / revenue * 100
        out.append(Fact("", "pct", round(level, 1)))
        if part_ago is not None and revenue0 and revenue0 > 0 and like_for_like("revenue", *inputs):
            before = part_ago / revenue0 * 100
            move, sign = _bps(level, before)
            out.append(Fact("", "pct", round(before, 1)))
            out.append(Fact(f"{label} {now_p}: {level:.1f}% of revenue against {before:.1f}% in {ago_p} "
                            f"({_word(sign)} {move} bps)", "bps", move, sign))
        else:
            out.append(Fact(f"{label} {now_p}: {level:.1f}% of revenue"))

    def total(metrics: tuple[str, ...], period: str) -> float | None:
        parts = [get(m, period) for m in metrics]
        return sum(p for p in parts if p is not None) if parts[0] is not None else None

    share("Cost of materials and goods", total(_MATERIALS, now_p), total(_MATERIALS, ago_p),
          tuple(m for m in _MATERIALS if get(m, ago_p)))
    share("Employee cost", get("employee_cost", now_p), get("employee_cost", ago_p), ("employee_cost",))

    margin, margin0 = get("ebitda_margin", now_p), get("ebitda_margin", ago_p)
    if margin is not None and margin0 is not None and like_for_like("revenue", "pbt"):
        move, sign = _bps(margin, margin0)
        out.append(Fact("", "pct", round(margin0, 1)))
        out.append(Fact(f"EBITDA margin {now_p}: {margin:.1f}% against {margin0:.1f}% in {ago_p} ({_word(sign)} {move} bps)",
                        "bps", move, sign))
    share("Net profit", get("pat", now_p), get("pat", ago_p), ("pat",))

    pbt, pbt0 = get("pbt", now_p), get("pbt", ago_p)
    other, other0 = get("other_income", now_p), get("other_income", ago_p)
    if pbt and pbt > 0 and other is not None and other > 0:
        level = other / pbt * 100
        text = f"Other income {now_p}: {level:.1f}% of profit before tax"
        if pbt0 and pbt0 > 0 and other0 is not None and like_for_like("pbt", "other_income"):
            text += f" against {other0 / pbt0 * 100:.1f}% in {ago_p}"
            out.append(Fact("", "pct", round(other0 / pbt0 * 100, 1)))
        out.append(Fact(text, "pct", round(level, 1)))
    tax, tax0 = get("tax_expense", now_p), get("tax_expense", ago_p)
    if pbt and pbt > 0 and tax is not None:
        text = f"Effective tax rate {now_p}: {tax / pbt * 100:.1f}%"
        if pbt0 and pbt0 > 0 and tax0 is not None and like_for_like("pbt", "tax_expense"):
            text += f" against {tax0 / pbt0 * 100:.1f}% in {ago_p}"
            out.append(Fact("", "pct", round(tax0 / pbt0 * 100, 1)))
        out.append(Fact(text, "pct", round(tax / pbt * 100, 1)))

    # Cash flow: filed for six and twelve months only, so the latest such period in the file
    for period in sorted({p for m, p in val if m == "operating_cash_flow" and p[:2] in ("H1", "FY", "H2")},
                         key=lambda p: (p[-2:], p.startswith("FY")), reverse=True)[:1]:
        cfo, capex, pat = get("operating_cash_flow", period), get("capex", period), get("pat", period)
        parts = [f"cash from operations {_cr(cfo)}"]
        if pat and pat > 0:
            conversion = cfo / pat * 100
            parts.append(f"{conversion:.0f}% of net profit {_cr(pat)}")
            out.append(Fact("", "pct", round(conversion)))
        if capex is not None:
            spend = abs(capex)   # filed as an outflow, with either sign
            parts += [f"capex {_cr(spend)}", f"free cash flow {_cr(cfo - spend)}"]
        out.append(Fact(f"Cash flow {period}: " + ", ".join(parts)))

    sheet = getattr(tagged, "balance_sheet", None)
    if sheet is not None and not sheet.is_empty():
        earlier = next((s for s in reversed(balance_history or []) if s.get("period") and s.get("period") != sheet.period), None)
        parts = []
        for field, word in _BALANCE:
            now_v = getattr(sheet, field, None)
            if now_v is None:
                continue
            then = (earlier or {}).get(field)
            if then and then > 0 and _printed(index, then):
                change = (now_v - then) / then * 100
                parts.append(f"{word} {_cr(now_v)} against {_cr(then)} at {earlier['period']} ({change:+.0f}%)")
                out.append(Fact("", "pct", round(abs(change)), (change > 0) - (change < 0)))
            else:
                parts.append(f"{word} {_cr(now_v)}")
        cash, debt = sheet.cash_cr, sheet.gross_debt_cr
        if cash is not None and debt is not None:
            parts.append(f"net cash {_cr(cash - debt)}" if cash >= debt else f"net debt {_cr(debt - cash)}")
        if parts:
            out.append(Fact(f"Balance sheet {sheet.period or now_p}: " + "; ".join(parts)))
    return out


def block(facts: list[Fact]) -> str:
    """The facts as the prompt's block. Empty when there are none."""
    lines = [f"- {f.text}" for f in facts if f.text]
    if not lines:
        return ""
    return ("Computed by the system from this filing's statements (use these figures as given, never your own; say "
            "what moved them only as the filing or memory states it):\n" + "\n".join(lines))
