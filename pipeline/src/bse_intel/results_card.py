"""A results card built by code from the filing's XBRL; the model adds a line or two (owner's PLAN 18 part 4: "code
builds the numbers (table, changes, margins); the AI adds 1-2 lines").

Results cards were the weakest card in rounds 3 and 4 (blind agents: 3 of 7 and 7 of 14 published WRONG) against about
one in eight for every other kind: a year-on-year change taken from the previous quarter, a margin "expanded" when it
fell, a stock build read as a drawdown, profit growth put on lower tax when tax rose. Every one is a figure, a change or
a direction the XBRL file states exactly. So when a results card has its file, code writes its headline, the facts (each
quoting its line of the machine-tagged table that leads the filing's text), the key numbers with their changes and the
timeline line; the model's takeaway and at most two points of why it matters are kept (and checked by the direction
guard); its notable changes, core catalyst and computed impacts are left out.
"""

from __future__ import annotations

import re

from .models import Fact, KeyNumber

MAX_WHY = 2
_LEGAL = re.compile(r"\s+(?:limited|ltd\.?|corporation of india limited)$", re.I)


def _short_name(name: str | None) -> str:
    name = " ".join((name or "").split())
    return _LEGAL.sub("", name).strip() or name


def _cr(value: float) -> str:
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"₹{text} Cr"


def _pct(value: float | None) -> str | None:
    return None if value is None else f"{value:+.1f}%"


def _changes(m) -> str:
    parts = [f"{p} YoY" for p in (_pct(m.yoy_pct),) if p] + [f"{p} QoQ" for p in (_pct(m.qoq_pct),) if p]
    return ", ".join(parts)


def _line(m) -> str:
    """The table line for this metric exactly as `XbrlResult.table()` writes it (the quote a fact carries)."""
    unit = " ₹/share" if m.unit == "INR" else " %" if m.unit == "PCT" else " Cr"
    change = "".join(f", {label} {v:+.1f}%" for label, v in (("YoY", m.yoy_pct), ("QoQ", m.qoq_pct)) if v is not None)
    return f"- {m.metric} {m.period}: {m.value:g}{unit}{change}"


_LABELS = (("revenue", "Revenue from operations"), ("interest_earned", "Interest earned"),
           ("pre_provision_operating_profit", "Operating profit before provisions"), ("ebitda", "EBITDA"),
           ("provisions", "Provisions"), ("pat", "Net profit"), ("eps", "EPS"))


def build(out, tagged, company_name: str | None) -> list[str]:
    """Put the file's figures on a results card. Returns what was replaced (empty when the file cannot carry it)."""
    card = getattr(out, "card", None)
    if card is None or tagged is None or getattr(tagged, "kind", None) != "RESULTS" or not tagged.period:
        return []
    now = {m.metric: m for m in tagged.metrics if m.period == tagged.period and m.value is not None}
    top = now.get("revenue") or now.get("interest_earned") or now.get("total_income")
    profit = now.get("pat")
    if top is None or profit is None:
        return []
    name = _short_name(company_name)
    basis = (tagged.basis or "").lower()
    period = tagged.period
    top_word = "revenue" if top.metric == "revenue" else "interest earned" if top.metric == "interest_earned" else "total income"

    def phrase(m, word: str) -> str:
        change = f" ({_pct(m.yoy_pct)} YoY)" if m.yoy_pct is not None else ""
        return f"{word} {_cr(m.value)}{change}"

    headline = f"{name} {period}: {phrase(top, top_word)}, {phrase(profit, 'net profit')}"
    if len(headline) > 110:
        headline = f"{name} {period}: {phrase(profit, 'net profit')}"
    facts, keys = [], []
    for metric, label in _LABELS:
        m = now.get(metric)
        if m is None or (metric == "provisions" and "interest_earned" not in now):
            continue
        value = f"₹{m.value:,.2f} a share" if metric == "eps" else _cr(m.value)
        changes = _changes(m)
        text = f"{label} {period}: {value}" + (f" ({changes})" if changes else "")
        if metric == "ebitda" and now.get("ebitda_margin") is not None:
            text += f"; margin {now['ebitda_margin'].value:.1f}%"
        facts.append(Fact(text=text + ".", quote=_line(m)))
        keys.append(KeyNumber(label=label, value=value, change=(f"{_pct(m.yoy_pct)} YoY" if m.yoy_pct is not None else None),
                              quote=_line(m)))
    margin = now.get("ebitda_margin")
    if margin is not None:
        keys.append(KeyNumber(label="EBITDA margin", value=f"{margin.value:.1f}%", change=None, quote=_line(margin)))
    replaced = ["headline", "what_happened", "key_numbers", "timeline"]
    card.headline = headline
    card.what_happened = facts[:4] or card.what_happened
    card.key_numbers = keys[:6]
    if basis in ("consolidated", "standalone"):
        card.basis = basis.upper()
    if card.notable_changes:
        replaced.append(f"notable changes ({len(card.notable_changes)}) left out")
    card.notable_changes = []
    if card.core_catalyst:
        replaced.append("core catalyst left out")
    card.core_catalyst = None
    if card.quantified_impact:
        replaced.append(f"computed impacts ({len(card.quantified_impact)}) left out")
    card.quantified_impact = []
    card.why_it_matters = card.why_it_matters[:MAX_WHY]
    out.timeline_entry = f"{period} results ({basis or 'basis not stated'}): {phrase(top, top_word)}, {phrase(profit, 'net profit')}."
    return [f"results card from the XBRL file: {', '.join(replaced)}"]
