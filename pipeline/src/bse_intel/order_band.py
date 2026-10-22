"""An order sized by the filer's own value bands, read from the filing (blind review, 22 Oct 2026).

L&T's order releases give no amount: the title marks the order "(*Large)" and a footnote table defines each band
("Large 2,500 to 5,000" in ₹ Cr). A card said the orders were classed Large "but actual values are much smaller",
which the filing's own table contradicts, and never stated the band. Here the band and its range are read from the
filing, a fact quoting it goes on the card when no fact states it, and a line that sets the value against the band is
dropped. No AI."""

from __future__ import annotations

import re

from .models import Fact, Pass2Output

BANDS = ("Significant", "Large", "Major", "Mega", "Ultra-Mega")
_NUM = r"(\d[\d,]*(?:\.\d+)?)"
_RANGE = re.compile(rf"{_NUM}\s*(?:to|-|–|—)\s*{_NUM}|>\s*{_NUM}|above\s+{_NUM}", re.I)
_MARK = re.compile(r"\(\s*\*\s*(Ultra[- ]Mega|Significant|Large|Major|Mega)\s*\)|\*\s*(Ultra[- ]Mega|Significant|Large|Major|Mega)\b",
                   re.I)
# a sentence that sets the value against the band, or calls it unknown: the filing's own table answers both
_AGAINST = re.compile(r"\b(?:actual\s+values?|much\s+(?:smaller|lower|larger|higher)|smaller\s+than|lower\s+than|below\s+the|"
                      r"above\s+the|value\s+(?:is\s+|was\s+)?(?:not\s+disclosed|undisclosed)|undisclosed)\b", re.I)


def _cr(raw: str) -> float:
    return float(raw.replace(",", ""))


def legend(text: str) -> dict[str, tuple[float, float | None, str]]:
    """{band: (low, high or None, the range as printed)} from the filing's classification table, in either layout:
    names then ranges (L&T's two columns read top to bottom), or each name with its range on the line."""
    at = re.search(r"order\s+classification", text or "", re.I)
    if not at:
        return {}
    block = text[at.end():at.end() + 800]
    names = [m.group(0).replace(" ", "-").title() for m in re.finditer(r"Ultra[- ]Mega|Significant|Large|Major|Mega", block)]
    ranges = [(_cr(m.group(1)), _cr(m.group(2)), m.group(0)) if m.group(1) else (_cr(m.group(3) or m.group(4)), None, m.group(0))
              for m in _RANGE.finditer(block)]
    seen, out = [], {}
    for name in names:
        if name not in seen:
            seen.append(name)
    for name, rng in zip(seen, ranges):
        out[name] = rng
    return out if len(out) >= 2 else {}


def marked_band(text: str) -> str | None:
    """The band the filing marks its order with, "(*Large)" in the title."""
    m = _MARK.search(text or "")
    if not m:
        return None
    return (m.group(1) or m.group(2)).replace(" ", "-").title()


def _range_text(low: float, high: float | None) -> str:
    return f"₹{low:,.0f}-{high:,.0f} Cr" if high else f"above ₹{low:,.0f} Cr"


def apply(out: Pass2Output, text: str) -> list[str]:
    """Put the filing's order band on an order card, and take off lines that set the value against it."""
    card = out.card
    if card is None or out.event_type not in ("ORDER_WIN", "ORDER", None):
        return []
    band = marked_band(text)
    table = legend(text)
    if not band or band not in table:
        return []
    low, high, printed = table[band]
    span = _range_text(low, high)
    notes = []
    kept = [f for f in card.why_it_matters if not _AGAINST.search(f.text or "")]
    if len(kept) < len(card.why_it_matters):
        notes.append(f"dropped {len(card.why_it_matters) - len(kept)} line(s) setting the order value against the filing's '{band}' band")
        card.why_it_matters = kept
    facts = [f for f in card.what_happened if not _AGAINST.search(f.text or "")]
    if facts and len(facts) < len(card.what_happened):
        notes.append("dropped a fact setting the order value against the filing's band")
        card.what_happened = facts
    if card.takeaway and _AGAINST.search(card.takeaway):
        card.takeaway = ""
        notes.append("takeaway set the order value against the filing's band: cleared")
    stated = any(span.split(" Cr")[0].replace("₹", "") in (f.text or "").replace("₹", "") or
                 f"{low:,.0f}" in (f.text or "") for f in card.what_happened)
    if not stated:
        # the range as the filing prints it, so the quote check finds it; the band's name sits in the other column
        card.what_happened.append(Fact(text=f"The company classes the orders as '{band}': **{span}** in its own value bands",
                                       quote=printed))
        notes.append(f"order band stated from the filing: {band} = {span}")
    return notes
