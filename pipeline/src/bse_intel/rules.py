"""Stage 1a: deterministic triage from BSE metadata (no AI, no PDF download)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from .models import Filing

Action = Literal["DROP", "XBRL", "CALENDAR", "TIMELINE", "FAST_TRACK", "PASS1"]


@dataclass(frozen=True)
class Rule:
    action: Action
    reason: str
    event_type: str | None
    categories: tuple[str, ...] = ()
    subcategories: tuple[str, ...] = ()
    headline: tuple[re.Pattern, ...] = ()
    exclude: tuple[re.Pattern, ...] = ()

    def matches(self, filing: Filing, text: str) -> bool:
        if any(p.search(text) for p in self.exclude):
            return False
        category = filing.category.lower()
        subcategory = filing.subcategory.lower()
        return (
            any(c in category for c in self.categories if category)
            or any(s in subcategory for s in self.subcategories if subcategory)
            or any(p.search(text) for p in self.headline)
        )


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    event_type: str | None = None
    catalyst_date: str | None = None


@dataclass
class RuleBook:
    rules: list[Rule] = field(default_factory=list)

    @classmethod
    def from_config(cls, config: dict) -> "RuleBook":
        def compile_all(patterns):
            return tuple(re.compile(p, re.I) for p in patterns or ())

        rules: list[Rule] = []
        veto = compile_all((config.get("material_veto") or {}).get("headline"))
        for section, action in (("drop", "DROP"), ("xbrl_only", "XBRL"), ("calendar", "CALENDAR"), ("timeline", "TIMELINE"),
                                ("fast_track", "FAST_TRACK")):
            for entry in config.get(section, []):
                rules.append(Rule(
                    action=action,
                    reason=entry.get("reason") or f"{action.lower()}: {entry.get('event_type', '')}".strip(),
                    event_type=entry.get("event_type"),
                    categories=tuple(c.lower() for c in entry.get("categories", ())),
                    subcategories=tuple(s.lower() for s in entry.get("subcategories", ())),
                    headline=compile_all(entry.get("headline")),
                    exclude=compile_all(entry.get("exclude_headline")) + (veto if action == "DROP" and entry.get("material_veto", True) else ()),
                ))
        return cls(rules)

    def classify(self, filing: Filing) -> Decision:
        text = f"{filing.headline} {filing.subject}"
        for rule in self.rules:
            if rule.matches(filing, text):
                catalyst = extract_date(text, filing.filing_date) if rule.action == "CALENDAR" else None
                return Decision(rule.action, rule.reason, rule.event_type, catalyst)
        return Decision("PASS1", "no rule matched")


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_DMY = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")
# "21 October 2026", and NSE's "21-Oct-2026" (deep audit A-05: 26 of 27 record dates of 14-21 Oct never reached the
# calendar)
_D_MON_Y = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?(?:\s+|-)([A-Za-z]{3,9})(?:[,.]?\s+|-)(\d{4})\b")
_MON_D_Y = re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b")


def extract_date(text: str, not_before: str) -> str | None:
    """First plausible calendar date in ``text`` on/after ``not_before`` (Indian D/M/Y order)."""
    floor = date.fromisoformat(not_before)
    candidates: list[date] = []
    for d, m, y in _DMY.findall(text):
        candidates.append(_safe_date(int(y), int(m), int(d)))
    for d, mon, y in _D_MON_Y.findall(text):
        if mon[:3].lower() in _MONTHS:
            candidates.append(_safe_date(int(y), _MONTHS[mon[:3].lower()], int(d)))
    for mon, d, y in _MON_D_Y.findall(text):
        if mon[:3].lower() in _MONTHS:
            candidates.append(_safe_date(int(y), _MONTHS[mon[:3].lower()], int(d)))
    valid = [c for c in candidates if c and floor <= c <= date(floor.year + 1, floor.month, min(floor.day, 28))]
    return min(valid).isoformat() if valid else None


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None
