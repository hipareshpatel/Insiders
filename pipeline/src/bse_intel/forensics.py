"""Deterministic checks on the filing text itself (blueprint §5.2 and §9), added to a card's signals.

* Board-meeting duration: outcome letters state when the meeting "commenced at" and "concluded
  at". A routine meeting lasts 1-3 hours; six or more before approving results or a restructuring
  is flagged as a prolonged deliberation.
* SEBI Reg 30 Schedule III: Para A events are deemed material whatever their size; a Para B event
  (product launch, capacity addition, order) is disclosed only when the company expects it to
  cross the materiality threshold (the lower of 2% of turnover, 2% of net worth or 5% of average
  3-year profit), so a Para B filing without figures still says management expects that much.
"""

from __future__ import annotations

import re

_TIME = r"(\d{1,2})[:.](\d{2})\s*(a\.?m\.?|p\.?m\.?|hrs?\.?|hours)?"
_COMMENCED = re.compile(r"(?:commenced|started|began)\s+(?:at\s+)?" + _TIME, re.I)
_CONCLUDED = re.compile(r"(?:concluded|ended|closed)\s+(?:at\s+)?" + _TIME, re.I)
_PARA_B = re.compile(r"(?:para(?:graph)?|part)\s*[-–]?\s*B\b(?:\s+of)?(?:\s+part\s+a)?\s+of\s+schedule\s+iii", re.I)
_PARA_A = re.compile(r"(?:para(?:graph)?|part)\s*[-–]?\s*A\b(?:\s+of)?(?:\s+part\s+a)?\s+of\s+schedule\s+iii", re.I)
PROLONGED_HOURS = 6.0
# Times that belong to a board meeting, not to a postal ballot's or an AGM's e-voting window: Torrent's postal-ballot
# result ("e-voting commenced at 9:00 a.m. ... ended at 5:00 p.m.") was flagged as an 8-hour board meeting (round 4)
_BOARD_MEETING = re.compile(r"meeting of the board|board meeting|board of directors(?: of the company)? (?:at its|in its) meeting", re.I)
_VOTING = re.compile(r"postal ballot|e-?voting|remote voting|voting period|scrutini[sz]er", re.I)
# What the company says when it expects no material impact: then it is not telling the market it crossed the threshold
_NO_IMPACT = re.compile(r"\bno\s+(?:major|material|significant|adverse)?\s*(?:financial\s+|material\s+)?impact|"
                        r"\bnot\s+(?:likely\s+to\s+)?(?:have|be|having)\s+(?:a\s+|any\s+)?(?:material|significant)|"
                        r"\bimmaterial\b|\bnot\s+material\b|\bwill\s+not\s+be\s+sustained", re.I)


def _minutes(match: re.Match) -> int | None:
    hour, minute, suffix = int(match.group(1)), int(match.group(2)), (match.group(3) or "").lower().replace(".", "")
    if hour > 23 or minute > 59:
        return None
    if suffix.startswith("pm") and hour < 12:
        hour += 12
    if suffix.startswith("am") and hour == 12:
        hour = 0
    return hour * 60 + minute


def board_meeting_hours(text: str) -> float | None:
    if not _BOARD_MEETING.search(text) or _VOTING.search(text):
        return None
    start, end = _COMMENCED.search(text), _CONCLUDED.search(text)
    if not start or not end:
        return None
    a, b = _minutes(start), _minutes(end)
    if a is None or b is None:
        return None
    if b < a:
        b += 24 * 60  # concluded after midnight
    hours = (b - a) / 60
    return hours if 0 < hours < 20 else None


def text_signals(text: str, event_type: str) -> list[dict]:
    out: list[dict] = []
    hours = board_meeting_hours(text or "")
    if hours is not None and hours >= PROLONGED_HOURS:
        out.append({"type": "BOARD_DELIBERATION", "severity": "WARNING", "ref": None,
                    "text": f"The board meeting ran {hours:.1f} hours before this outcome (a routine one takes 1-3); "
                            "prolonged deliberation often precedes difficult results or restructuring."})
    if _PARA_B.search(text or "") and not _NO_IMPACT.search(text or "") and event_type in ("CAPEX", "ORDER_WIN", "PRODUCT_LAUNCH", "OTHER", "LITIGATION_REGULATORY"):
        out.append({"type": "REG30_THRESHOLD", "severity": "INFO", "ref": None,
                    "text": "Filed under Reg 30 Schedule III Para B, which applies only above SEBI's materiality threshold "
                            "(the lower of 2% of turnover, 2% of net worth or 5% of 3-year average profit): management "
                            "expects at least that much impact even where the filing gives no figure."})
    return out
