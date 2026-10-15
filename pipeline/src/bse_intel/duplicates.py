"""Repeat submissions of one filing.

BSE asks for one submission per applicable subcategory, so one event can arrive several times: SML
Mahindra's CEO change on 21 Mar 2025 came five times in eight minutes; a results PDF can arrive as
"Financial Results" and again as "Outcome of Board Meeting". Analysing each repeat spends quota and
puts identical cards in the feed.

Many filings reuse one template with new numbers (a corrected results statement, monthly business
updates, order wins, ratings, allotments), so similar wording is not enough. A later filing is a
duplicate of an earlier one by the same company only when

* its body (the text without whitespace and covering-letter lines) is exactly the same, or
* the bodies are near-identical (word 5-gram Jaccard >= NEAR) and hold exactly the same numbers.

Anything titled as a correction (corrigendum, revised, rectified, ...) is never a duplicate.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

DAYS = 3
NEAR = 0.9
MIN_WORDS = 40   # a body this short (a bare covering letter, an empty scan) is never matched
CHARS = 60_000

CORRECTION = re.compile(r"\b(?:corrigend\w*|revis\w*|rectif\w*|correct(?:ed|ion|ions)?|errat\w*|amend\w*|modif\w*|"
                        r"addend\w*|restat\w*|supersed\w*)\b", re.I)
# Covering-letter lines differ between submissions of one document (subject, date, scrip codes, the
# exchange's address) and say nothing about the event.
_COVER = re.compile(
    r"^\s*(?:to\b|dear\b|sub\b|subject\b|ref\b|reference\b|re\s*:|scrip\b|security\s+(?:code|id)\b|symbol\b|"
    r"stock\s+code\b|isin\b|date[d]?\b|place\b|encl\w*|yours\b|thank\w*|"
    r"for\s+and\s+on\s+behalf\b|for\s+[a-z0-9&.,'()\s-]{2,80}\b(?:ltd|limited)\.?\s*$|"
    r"company\s+secretary\b|compliance\s+officer\b|"
    r"(?:the\s+)?(?:general\s+)?manager\b|(?:the\s+)?secretary\b|(?:dept|department)\s+of\s+corporate\b|"
    r"listing\s+(?:department|centre|compliance)\b|corporate\s+relationship\b|bse\s+limited\b|"
    r"national\s+stock\s+exchange\b|phiroze\b|dalal\s+street\b|exchange\s+plaza\b|bandra\b|mumbai\b|"
    r"(?:cin|din|membership\s+no)\b)", re.I)
_PIN = re.compile(r"\b4000\d\d\b")
_WORD = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass(frozen=True)
class Body:
    text: str                 # normalised body: lower-case words joined by single spaces
    words: int
    shingles: frozenset[int]
    numbers: Counter

    @property
    def matchable(self) -> bool:
        return self.words >= MIN_WORDS


def body(text: str | None) -> Body:
    """The part of a filing that carries the event: covering-letter lines and whitespace removed."""
    lines = [line for line in (text or "").splitlines()
             if line.strip() and not _COVER.match(line) and not _PIN.search(line)]
    words = _WORD.findall(" ".join(lines).lower())
    normalised = " ".join(words)
    shingles = frozenset(hash(" ".join(words[i:i + 5])) for i in range(len(words) - 4))
    numbers = Counter(n.replace(",", "") for n in _NUMBER.findall(normalised))
    return Body(normalised, len(words), shingles, numbers)


def is_correction(*titles: str | None) -> bool:
    return bool(CORRECTION.search(" ".join(t for t in titles if t)))


def match(new: Body, old: Body) -> str | None:
    """"exact" or "near" when ``new`` repeats ``old``, else None."""
    if not (new.matchable and old.matchable):
        return None
    if new.text == old.text:
        return "exact"
    if new.numbers != old.numbers:
        return None
    union = len(new.shingles | old.shingles)
    if union and len(new.shingles & old.shingles) / union >= NEAR:
        return "near"
    return None
