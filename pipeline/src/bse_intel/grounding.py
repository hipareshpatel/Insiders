"""Numeric grounding check: are the card's numbers actually in the sources?

LLMs occasionally invent or mis-copy figures. Every number on a card is
checked against the filing text and the memory view, allowing for:

* unit conversion (₹ lakh / million / thousand / rupees -> ₹ crore and back),
* display rounding (``₹1.2 Cr`` matches ``123.45`` lakh),
* derived percentages (a YoY % computed from two source figures).

Cards with a low score are stored with ``needs_review``.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

from .models import Card

_NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\(?\d[\d,]*(?:\.\d+)?\)?")
_IGNORE = re.compile(
    r"\b(?:FY|Q[1-4]|H[12]|9M)\s*'?\d{2,4}\b|\b(?:19|20)\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    re.I,
)
_UNIT = re.compile(r"\s*(%|bps?\b|pp\b|percentage points?)", re.I)
SCALES = (1, 10, 100, 1000, 1e4, 1e5, 1e7, 0.1, 0.01, 0.001)
DEFAULT_THRESHOLD = 0.7


@dataclass
class GroundingResult:
    score: float
    checked: int
    ungrounded: list[str]

    @property
    def ok(self) -> bool:
        return self.score >= DEFAULT_THRESHOLD


def _numbers(text: str) -> list[tuple[float, int]]:
    """(value, decimals) for each number in text, skipping years and period labels."""
    text = _IGNORE.sub(" ", text)
    out = []
    for raw in _NUMBER.findall(text):
        cleaned = raw.replace(",", "").strip("+").strip("()")
        try:
            value = float(cleaned)
        except ValueError:
            continue
        decimals = len(cleaned.split(".")[1]) if "." in cleaned else 0
        out.append((abs(value), decimals))
    return out


class SourceIndex:
    def __init__(self, *texts: str):
        values = {v for text in texts for v, _ in _numbers(text) if v > 0}
        self.values = sorted(values)

    def _has_near(self, target: float, tolerance: float) -> bool:
        i = bisect.bisect_left(self.values, target - tolerance)
        return i < len(self.values) and self.values[i] <= target + tolerance

    def grounded(self, value: float, decimals: int, is_percent: bool) -> bool:
        if value <= 31 and decimals == 0 and not is_percent:
            return True  # small counts (units, days, months) are not worth checking
        rounding = 0.5 * 10 ** (-decimals) + 1e-9
        for scale in SCALES:
            # card shows `value` in its unit; a source figure s matches if s / scale rounds to value
            if self._has_near(value * scale, rounding * scale + abs(value * scale) * 1e-6):
                return True
        if is_percent:
            # a percentage change between two figures, or a change in percentage points
            return self._derivable_percent(value, decimals) or self.derivable_difference(value, 0.5 * 10 ** (-decimals) + 0.05)
        return False

    def derivable_difference(self, diff: float, tolerance: float) -> bool:
        """Is diff ~= a - b for two source figures (e.g. bps = change in a margin)?"""
        return any(self._has_near(a - diff, tolerance) or self._has_near(a + diff, tolerance)
                   for a in self.values if a <= 1000)

    def _derivable_percent(self, pct: float, decimals: int) -> bool:
        """Is pct ~= (a - b) / b * 100 for two source figures a, b (either sign)?"""
        tolerance = max(0.5 * 10 ** (-decimals), 0.05)
        values = self.values
        if len(values) > 4000:
            values = values[:: len(values) // 4000 + 1]
        for b in values:
            if b < 1:
                continue
            for factor in (1 + pct / 100, 1 - pct / 100):
                if factor <= 0:
                    continue
                target = b * factor
                slack = b * tolerance / 100
                if self._has_near(target, slack) and abs(target - b) > 1e-9:
                    return True
        return False


def check_card(card: Card, *sources: str) -> GroundingResult:
    index = SourceIndex(*sources)
    texts = [card.headline, *card.what_happened]
    texts += [f"{k.value} {k.change or ''}" for k in card.key_numbers]
    texts += [f"{c.previous or ''} {c.current or ''} {c.change or ''}" for c in card.notable_changes]
    checked, ungrounded = 0, []
    for text in texts:
        stripped = _IGNORE.sub(" ", text)
        for match in _NUMBER.finditer(stripped):
            raw = match.group(0)
            cleaned = raw.replace(",", "").strip("+").strip("()")
            try:
                value = abs(float(cleaned))
            except ValueError:
                continue
            decimals = len(cleaned.split(".")[1]) if "." in cleaned else 0
            unit = _UNIT.match(stripped, match.end())
            unit_text = unit.group(1).lower() if unit else ""
            is_bps = unit_text.startswith("bp")
            is_points = unit_text.startswith(("pp", "percentage point"))
            is_percent = unit_text == "%" or is_bps or is_points
            if value == 0:
                continue
            checked += 1
            if is_bps and index.derivable_difference(value / 100, 0.01):
                continue
            if is_points and index.derivable_difference(value, 0.5 * 10 ** (-decimals) + 0.01):
                continue
            if not index.grounded(value, decimals, is_percent):
                ungrounded.append(raw + (" bps" if is_bps else " pp" if is_points else "%" if is_percent else ""))
    if checked == 0:
        return GroundingResult(1.0, 0, [])
    return GroundingResult(round(1 - len(ungrounded) / checked, 3), checked, ungrounded)
