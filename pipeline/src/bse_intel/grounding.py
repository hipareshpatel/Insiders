"""Numeric grounding check: are the card's numbers actually in the sources?

LLMs occasionally invent or mis-copy figures. Every number on a card is
checked against the filing text and the memory view, allowing for:

* unit conversion (₹ lakh / million / thousand / rupees -> ₹ crore and back),
* display rounding (``₹1.2 Cr`` matches ``123.45`` lakh),
* derived percentages (a YoY % computed from two source figures).

Cards with a low score are stored with ``needs_review``.

``check_claims`` does the same for words rather than numbers: a card that calls
something the "first", "maiden" or a "record" needs the filing or memory to say
so, and loses outright when the filing describes a repeat ("second set of
orders"). Memory only covers the platform's own filings, so the absence of an
earlier order there never makes an order the first.
"""

from __future__ import annotations

import bisect
import itertools
import math
import re
from dataclasses import dataclass, field

from .models import Card
from .periods import quarter_index

_NUMBER = re.compile(r"(?<![A-Za-z\d.])[-+]?\(?\d[\d,]*(?:\.\d+)?\)?")
# Period labels and dates are not figures: "Q2FY27", "Q2 FY 2026-27", "H1FY27", "FY26", 30-09-2026,
# and years (but "2050.45" is a figure).
_IGNORE = re.compile(
    r"(?<![A-Za-z])(?:Q[1-4]|H[12]|9M)?\s*FY\s*'?\d{2,4}(?:\s*-\s*\d{2,4})?\b|\b(?:Q[1-4]|H[12]|9M)\b"
    r"|(?<![\d.,])(?:19|20)\d{2}(?![\d]|[.,]\d)|\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b",
    re.I,
)
# A bare 19xx or 20xx in a source, set aside above as a year. SML's April-August cargo sales were 2052 units, and
# "2,052" on the card, which no one writes for a year, was held as not in the filing (2026-10-18).
_YEAR_TOKEN = re.compile(r"(?<![\d.,])(?:19|20)\d{2}(?![\d]|[.,]\d)")
# and a currency glued to the word before it when a figure follows: eMudhra's "total revenue ofRs.309.08 million" kept
# its ₹30.9 Cr card figure "not found" (held-card analysis, 2026-10-20)
_CURRENCY = re.compile(r"(?:₹|\b(?:rs\.?|inr|usd|cad|eur|gbp)|(?<=[a-z])(?:rs\.|inr)(?=\s?\d)|us\$|\$)\s*", re.I)
_UNIT = re.compile(r"\s*(%|per\s*cent\b|percent\b|basis\s+points?\b|bps?\b|pp\b|percentage\s+points?\b|x\b|times\b)", re.I)
_QUANTITY = re.compile(r"\s*(?:cr\b|crores?\b|lakhs?\b|lacs?\b|mn\b|million\b|bn\b|billion\b|mw\b|gw\b|kw\b|tpd\b|mtpa\b"
                       r"|mt\b|tonnes?\b|tons?\b|units?\b|vehicles?\b|beds?\b|stores?\b|kl\b|mld\b|sq\.?\s*ft\b)", re.I)
SCALES = (1, 10, 100, 1000, 1e4, 1e5, 1e7, 0.1, 0.01, 0.001)  # unit conversions between ₹ crore, lakh, million, rupees
# A ₹ crore figure on the card can only come from crore, million, lakh, thousand or rupees in the
# source. The wider SCALES let "₹3,000 Cr" match any bare 3 or 300 in the text (a page number).
CRORE_SCALES = (1, 10, 100, 1e4, 1e7)
# A statement's declared unit: "(INR in Lakhs)", "(Rs. in lakh)", "(₹ in million)", "Amount in ₹ '000",
# and a header line of its own whose currency sign the PDF text mangled. Novartis's statements read
# "('l in million)", '"in million)', "c, in million)", "{f in million)", "(fin million)", "/fin million)".
_DECLARED_UNIT = re.compile(
    # "(Rs. In Mn.)" heads Heritage's investor decks (2026-10-18)
    # "₹ Cr" heads Mahindra Holidays' deck beside one "AUR (₹ Lakh)": read as lakh alone, the unit fixer cut every crore
    # figure 100x (daily audit, 21 Oct 2026)
    r"(?:₹|\brs\.?|\binr|\brupees?)\s*(?:in\s*)?(?:(lakhs?|lacs?|crores?|crs?|millions?|mn|mm|billions?|bn|thousands?)(?![a-z])|('?000)s?(?![\d,a-z]))"
    r"|\bin\s*(?:₹|rs\.?|inr|rupees?)\s*(?:(lakhs?|lacs?|crores?|crs?|millions?|mn|billions?|bn|thousands?)(?![a-z])|('?000)s?(?![\d,a-z]))"
    # "(INR Million)" read as "CINR Million )" (AGI Infra's rating letter, round 4): the bracket fused to the currency
    r"|inr\s*(millions?|billions?|lakhs?|crores?)(?![a-z])"
    # the rupee sign mangled and glued to the word, with no "in": "(XLakhs)", "( Ė Crores)". Not after a
    # figure, where a unit belongs to that figure alone ("12,345.67 (lakhs)").
    r"|(?<![\d.,]\s)(?<![\d.,])\([ \t]*[^\s()\w]?[A-Za-z']{0,2}[^\s()\w]?[ \t]*(lakhs?|lacs?|crores?|millions?)[ \t]*\)"
    r"|^[ \t]*[(\[{/\"'`]?[ \t]*[^\s()]{0,3}[ \t]*in[ \t]*(lakhs?|lacs?|crores?|millions?|thousands?)\.?[ \t]*\)"
    r"|mount[ \t]+(?:in|ln|1n|111)[ \t]+(lakhs?|lacs?|crores?|millions?|thousands?)[ \t]+of\b",
    re.I | re.M)  # Jubilant's rupee sign arrives as a Tibetan letter: "(ཪ in million)"; Heritage's
# scanned headers as "(,\mount in millions of Z unless otherwise stated)" and "(Amount 111 millions oft"
# SML writes the currency out ("(Rupees in Crores, except share data)") and some filers write thousands
# as "(Rs. 000)" without the apostrophe; neither was read, so those statements had no unit at all.
_PER_CRORE = {"lakh": 100, "lac": 100, "million": 10, "mn": 10, "mm": 10, "thousand": 10_000, "'000": 10_000, "000": 10_000,
              "crore": 1, "cr": 1, "billion": 0.01, "bn": 0.01}   # "(Rs billion)": RBL's business update, round 4 (100x as crore)
UNIT_NAMES = {100: "₹ lakh", 10: "₹ million", 10_000: "₹ thousand", 0.01: "₹ billion"}
_CRORE_AFTER = re.compile(r"\s*(?:crs?\b|crores?\b)", re.I)
# The unit written right after a source figure ("INR 5445 Million", "Rs. 2,025 lakhs"), as figures
# per ₹ crore. Kanoria's RPT notice (Apr 2025) mixes million, lakh and crore, so no single declared
# unit exists; "5445 Million" was still written as "₹5,445 Cr".
# The amount spelt out in brackets may come between ("INR 3 (Three) Million": Excelsoft, round 4, carded as ₹3 Cr)
_MONEY_AFTER = re.compile(r"\s*(?:\([A-Za-z][A-Za-z ,-]{0,60}\)\s*)?(lakhs?|lacs?|crores?|crs?|millions?|mn|billions?|bn|thousands?)(?![a-z])",
                          re.I)
_PER_CRORE_WORD = {"lakh": 100, "lac": 100, "crore": 1, "cr": 1, "million": 10, "mn": 10,
                   "billion": 0.01, "bn": 0.01, "thousand": 10_000}


def _money_unit(clean: str, end: int) -> float | None:
    m = _MONEY_AFTER.match(clean, end)
    if not m:
        return None
    word = m.group(1).lower()
    return _PER_CRORE_WORD.get(word if word in _PER_CRORE_WORD else word[:-1])


def explicit_units(text: str | None) -> set[float]:
    """The money units written after figures in a text, as figures per ₹ crore."""
    clean = _clean(text or "")
    return {u for m in _NUMBER.finditer(clean) if (u := _money_unit(clean, m.end())) is not None}


def _near(values: list[float], target: float, tolerance: float) -> bool:
    i = bisect.bisect_left(values, target - tolerance)
    return i < len(values) and values[i] <= target + tolerance
DEFAULT_THRESHOLD = 0.7
NEAR = 300  # characters: two source figures this close can be compared with each other


@dataclass
class GroundingResult:
    score: float
    checked: int
    ungrounded: list[str]
    headline_ungrounded: list[str] = field(default_factory=list)  # ₹ amounts in the headline not found
    amounts_ungrounded: list[str] = field(default_factory=list)  # amounts anywhere on the card not found

    @property
    def ok(self) -> bool:
        return self.score >= DEFAULT_THRESHOLD and not self.headline_ungrounded


def _clean(text: str) -> str:
    """Text with currency marks and period labels blanked out, positions kept."""
    text = _CURRENCY.sub(lambda m: " " * len(m.group(0)), text.replace("**", "  "))
    return _IGNORE.sub(lambda m: " " * len(m.group(0)), text)


def _tokens(text: str) -> list[tuple[float, int, int, str, str]]:
    """(value, decimals, position, kind, raw) for each figure; kind is pct, bps, pp, x, qty or plain."""
    clean = _clean(text)
    out = []
    for match in _NUMBER.finditer(clean):
        cleaned = match.group(0).replace(",", "").strip("+").strip("()")
        try:
            value = abs(float(cleaned))
        except ValueError:
            continue
        decimals = len(cleaned.split(".")[1]) if "." in cleaned else 0
        unit = _UNIT.match(clean, match.end())
        word = unit.group(1).lower() if unit else ""
        if word.startswith(("pp", "percentage")):
            kind = "pp"
        elif word in ("%", "percent") or word.startswith("per"):
            kind = "pct"
        elif word.startswith(("bp", "basis")):
            kind = "bps"
        elif word in ("x", "times"):
            kind = "x"
        else:
            kind = "qty" if _QUANTITY.match(clean, match.end()) else "plain"
        out.append((value, decimals, match.start(), kind, match.group(0).strip("+")))
    return out


def declared_unit(text: str | None) -> int | None:
    """Source figures per ₹ crore when a filing declares its statements in one unit other than crore
    ("(INR in Lakhs)" -> 100). None when it declares no unit or several, or declares crore (as the
    XBRL table on top does): then bare figures may match at any scale. Amounts written with their
    own unit ("INR 300 Crores" in a note) are read in that unit whatever this returns."""
    text = text or ""
    words = {next(g for g in m.groups() if g).lower().rstrip("s") for m in _DECLARED_UNIT.finditer(text)}
    units = {_PER_CRORE[w] for w in words}
    if len(units) != 1 or 1 in units:
        return None
    return units.pop()


def unit_before(text: str, pos: int) -> float | None:
    """The unit declared last before `pos` on its own page (crore included), as figures per ₹ crore; None when the
    page declares none before it. An annual report or a deck declares several units, so the document as a whole
    has none (`declared_unit`), while the table a quote comes from does: SML's FY26 report gave revenue as
    "2,83,791.74" under "(₹ in lakhs)" and the card's right "₹2,838 Cr" was held as not in its quote (2026-10-18)."""
    page = max(text.rfind("--- Page", 0, pos), pos - 8000, 0)
    last = None
    for m in _DECLARED_UNIT.finditer(text, page, pos):
        last = m
    if last is None:
        return None
    return _PER_CRORE.get(next(g for g in last.groups() if g).lower().rstrip("s"))


def _crore_positions(text: str) -> set[int]:
    """Start positions (as in _tokens) of figures written in ₹ crore ("₹2,863 Cr", "(28.6) crore")."""
    clean = _clean(text)
    return {m.start() for m in _NUMBER.finditer(clean) if _CRORE_AFTER.match(clean, m.end())}


def _numbers(text: str) -> list[tuple[float, int]]:
    return [(v, d) for v, d, _, _, _ in _tokens(text)]


# Amounts the number pattern reads wrong or not at all (held-card audit, 22 Oct 2026):
# "INR 2,993,59,08,147.6" and "Rs. 92,00,00,000/-", rupees in any grouping, ₹ 2,993.59 Cr and ₹92 Cr even where the
# document declares lakh; "Rs 2 lakh crore", ₹2,00,000 Cr; "Rs.1, 27,000" with a stray space after a comma (a comma group
# or decimals must follow, so "Regulations 30, 33, 51" stays three numbers); and a space as the separator, "2 642.81",
# "INR 1 885.6 million" and a bank's "3 83 509.48" (decimals required, so two table cells never merge).
_RUPEES = re.compile(r"(?:₹|\brs\.?|\binr)\s*(\d[\d,]{8,}(?:\.\d+)?)(?:\s*/-)?(?!\s*(?:\.\d|[\d,]|lakh|lac|crore|cr\b|mn\b|million|bn\b|billion|thousand))", re.I)
_LAKH_CRORE = re.compile(r"(?<![\d.,])(\d+(?:\.\d+)?)\s*lakh\s+crores?\b", re.I)
_SPACED = re.compile(r"(?<![\d.,])(?<!\d )(\d{1,3}, \d{2,3}(?:(?:,\d{2,3})+(?:\.\d+)?|\.\d+)|\d{1,3}(?: \d{2})* \d{3}\.\d+)(?![\d,])")


# a scan's OCR text layer with letters for digits (held-card audit, 22 Oct 2026, 23 figures): Godawari's "3,35,loo"
# shares, DCM's "5O.77%", SSWL's "t500.85 Cr" and "l424.ll Cr" (the rupee sign read as t or l), Ola's "(7B5)"
_OCR_TOKEN = re.compile(r"(?<![\w.,])([tlfz]?)([\dOolIS](?:[\d,.OolISB]*[\dOolISB])?)(?![\w])")
_OCR_DIGITS = str.maketrans("OolISB", "001158")


def _ocr_readings(text: str) -> list[tuple[float, int]]:
    """(value, end position) of each number-like token with letters in it, read with the letters as digits."""
    out = []
    for m in _OCR_TOKEN.finditer(text):
        prefix, core = m.group(1), m.group(2)
        if not re.search(r"[OolISB]", core) and not prefix:
            continue
        if sum(ch.isdigit() for ch in core) < 2:
            continue
        # a leading l or I is the rupee sign as often as a 1: "I24.75 crores" is ₹24.75 Cr, "l424.ll" ₹1,424.11 Cr
        if core[0] in "lI" and len(core) > 1:
            bodies = [core[1:], "1" + core[1:]]
        elif prefix == "l":
            bodies = [core, "1" + core]
        else:
            bodies = [core]
        for body in bodies:
            try:
                out.append((float(body.translate(_OCR_DIGITS).replace(",", "")), m.end()))
            except ValueError:
                pass
    return out


def _other_readings(text: str) -> list[tuple[float | None, float]]:
    out: list[tuple[float | None, float]] = []
    clean_ocr = _clean(text)
    out += [(_money_unit(clean_ocr, end), value) for value, end in _ocr_readings(text) if value > 0]
    for m in _RUPEES.finditer(text):
        value = float(m.group(1).replace(",", ""))
        if value >= 1e7:
            out.append((1e7, value))
    out += [(1, float(m.group(1)) * 1e5) for m in _LAKH_CRORE.finditer(text)]
    clean = _clean(text)
    for m in _SPACED.finditer(clean):
        value = float(m.group(1).replace(",", "").replace(" ", ""))
        out.append((_money_unit(clean, m.end()), value))
    return out


class SourceIndex:
    def __init__(self, *texts: str):
        self.points = [(v, i, pos) for i, text in enumerate(texts) for v, _, pos, _, _ in _tokens(text or "") if v > 0]
        self.values = sorted({v for v, _, _ in self.points}
                             | {v for text in texts for m in _SPACED.finditer(_clean(text or ""))
                                if (v := float(m.group(1).replace(",", "").replace(" ", "")))}
                             | {v for text in texts for v, _ in _ocr_readings(text or "") if v > 0})
        self._pairs: list[tuple[float, float]] | None = None
        by_unit: dict[float | None, set[float]] = {}
        for text in texts:
            clean = _clean(text or "")
            for m in _NUMBER.finditer(clean):
                try:
                    value = abs(float(m.group(0).replace(",", "").strip("+").strip("()")))
                except ValueError:
                    continue
                if value > 0:
                    by_unit.setdefault(_money_unit(clean, m.end()), set()).add(value)
            for unit, value in _other_readings(text or ""):
                by_unit.setdefault(unit, set()).add(value)
        plain = by_unit.pop(None, set())
        # A figure written once with its unit ("INR 3,000 million") is that amount wherever it recurs bare.
        self._plain = sorted(plain - set().union(*by_unit.values()))
        self._by_unit = {unit: sorted(values) for unit, values in by_unit.items()}

    def stated_crore(self, value: float, decimals: int, plain_scales=CRORE_SCALES, tolerance: float | None = None) -> bool:
        """A ₹ crore figure on the card. A source figure written with a unit matches only at that
        unit's scale ("5445 Million" grounds ₹544.5 Cr, never ₹5,445 Cr); a bare figure (a table
        under "(INR in Lakhs)") at ``plain_scales``. `tolerance`, in crore, replaces the rounding of
        `decimals` for a figure known only that closely (one rebuilt from a rounded percentage)."""
        rounding = (tolerance if tolerance is not None else 0.5 * 10 ** (-decimals)) + 1e-9
        for per_crore, values in self._by_unit.items():
            if _near(values, value * per_crore, rounding * per_crore + abs(value * per_crore) * 1e-6):
                return True
        if any(_near(self._plain, value * s, rounding * s + abs(value * s) * 1e-6) for s in plain_scales):
            return True
        # the card carries the XBRL's decimals and the filing prints the crore figure rounded: Adani Ports' deck
        # "10,738" for ₹10,737.58 Cr, ICICI's call "₹14,755 crore" for ₹14,755.06 Cr (held-card audit, 22 Oct 2026)
        if tolerance is None and decimals and value >= 1000:
            whole = [v for v in (*self._by_unit.get(1, ()), *(self._plain if 1 in plain_scales else ())) if v == int(v)]
            return any(abs(v - value) <= 0.5 + 1e-9 for v in whole)
        return False

    def _has_near(self, target: float, tolerance: float) -> bool:
        i = bisect.bisect_left(self.values, target - tolerance)
        return i < len(self.values) and self.values[i] <= target + tolerance

    def stated(self, value: float, decimals: int, scales=SCALES) -> bool:
        """A source figure s matches when s / scale rounds to the card's value."""
        rounding = 0.5 * 10 ** (-decimals) + 1e-9
        return any(self._has_near(value * s, rounding * s + abs(value * s) * 1e-6) for s in scales)

    def pairs(self) -> list[tuple[float, float]]:
        """Pairs of figures that sit close together in the same source, as a table row or a sentence
        compares them (this year against last year)."""
        if self._pairs is None:
            pts = sorted(self.points, key=lambda p: (p[1], p[2]))
            pairs = set()
            for k, (a, ia, pa) in enumerate(pts):
                for b, ib, pb in pts[k + 1:k + 7]:  # the next few figures: a row's columns, a sentence's "vs"
                    if ib != ia or pb - pa > NEAR:
                        break
                    if a != b and 0.5 <= a / b <= 2:
                        pairs.add((a, b))
            self._pairs = sorted(pairs)
        return self._pairs

    def grounded(self, value: float, decimals: int, is_percent: bool = False, kind: str | None = None) -> bool:
        kind = kind or ("pct" if is_percent else "plain")
        if kind == "plain" and value <= 31 and decimals == 0:
            return True  # small counts (days, months, a board of 7) are not worth checking
        if kind in ("pct", "x"):
            # stated as is, or as a fraction (0.25 for 25%), or the change between two nearby figures
            if self.stated(value, decimals, scales=(1, 0.01) if kind == "pct" else (1,)):
                return True
            return kind == "pct" and self._derived_change(value, decimals)
        if kind in ("bps", "pp"):
            if self.stated(value, decimals, scales=(1,)):
                return True  # the filing states the change itself ("up 40bps")
            points = value / 100 if kind == "bps" else value
            return self.derivable_difference(points, 0.5 * 10 ** (-decimals) * (0.01 if kind == "bps" else 1) + 0.01)
        return self.stated(value, decimals)

    def derivable_difference(self, diff: float, tolerance: float) -> bool:
        """Is diff ~= a - b for two nearby percentage-sized source figures (a change in a margin)?"""
        return any(abs(abs(a - b) - diff) <= tolerance for a, b in self.pairs() if a <= 100 and b <= 100)

    def _derived_change(self, pct: float, decimals: int) -> bool:
        tolerance = max(0.5 * 10 ** (-decimals), 0.05)
        return any(abs(abs(a - b) / b * 100 - pct) <= tolerance or abs(abs(a - b) / a * 100 - pct) <= tolerance
                   for a, b in self.pairs())


_ORDINAL_NOUNS = (r"half|quarter|phase|tranche|interim|instal+ment|day|week|month|year|stage|leg|batch|round|cycle"
                  r"|call|meeting|lot|part|time\s+limit|unit|plant\s+phase|line\s+item|schedule|annexure")
_FIRST_CLAIM = re.compile(
    rf"\bfor\s+the\s+first\s+time\b|\b(?:first(?:[- ]ever)?|maiden|debut|inaugural)\b(?!\s+(?:{_ORDINAL_NOUNS})\b)",
    re.I,
)
# Evidence uses the same exclusions as a claim: "the first quarter" says nothing about a maiden order.
_FIRST_EVIDENCE = _FIRST_CLAIM
_REPEAT = re.compile(
    r"\b(?:second|third|fourth|fifth|repeat|follow[- ]on|another|further|additional|subsequent)\s+"
    r"(?:set\s+of\s+|batch\s+of\s+|tranche\s+of\s+|round\s+of\s+)?"
    r"(?:orders?|contracts?|awards?|lois?|loas?|work\s+orders?|purchase\s+orders?|development\s+orders?)\b",
    re.I,
)
_RECORD_CLAIM = re.compile(
    r"\brecord\b(?!\s+date)|\ball[- ]time\b|\b(?:highest|lowest|best|worst|largest|biggest|strongest)[- ]ever\b", re.I,
)
_ON_RECORD = re.compile(r"\b(?:on|of)\s+record\b|\brecord\s+date\b|\btrack\s+record\b|\brecord(?:ed|s|ing)\b", re.I)


def _snippet(text: str, match: re.Match) -> str:
    start = max(0, text.rfind(" ", 0, max(0, match.start() - 25)) + 1)
    end = text.find(" ", min(len(text), match.end() + 25))
    return text[start:end if end != -1 else len(text)].strip(" ,.;")


_STOP = frozenset("the a an of its their to from for in on with and by at as this that is was ever".split())


def _subject_words(text: str, end: int) -> list[str]:
    """The first few content words after a claim ("first order from Safran" -> order, safran)."""
    words = re.findall(r"[A-Za-z][A-Za-z&-]{2,}", text[end:end + 60])
    return [w.lower() for w in words if w.lower() not in _STOP][:3]


def _supported(family: re.Pattern, source: str, subject: list[str], window: int = 80) -> bool:
    """Does the source use a word of this family near one of the claim's subject words?"""
    for m in family.finditer(source):
        nearby = source[max(0, m.start() - window): m.end() + window].lower()
        if not subject or any(w in nearby for w in subject):
            return True
    return False


def check_claims(card: Card, *sources: str) -> list[str]:
    """Superlative and "first" claims on the card that the sources do not support."""
    source = _ON_RECORD.sub(" ", " ".join(sources))  # "take the above on record" is not a record
    # A repeat counts only when the filing itself describes one (sources[0]); a past order in memory
    # does not undo a filing that calls this one the first of its kind.
    is_repeat = bool(_REPEAT.search(sources[0] if sources else ""))
    texts = [t.replace("**", "") for t in (card.headline, card.takeaway, *(f.text for f in card.what_happened),
                                            *(i.text for i in card.why_it_matters))]
    unsupported: list[str] = []
    for text in texts:
        for m in _FIRST_CLAIM.finditer(text):
            after = text[m.end():].lstrip()
            if not m.group(0).lower().startswith("for") and (not after[:1].isalpha() or re.match(r"(?:of|two|three|few)\b", after, re.I)):
                continue  # "larger than the first (₹142 Cr)", "the first of three": a reference, not a claim
            if m.group(0).lower().startswith("for"):
                ok = bool(re.search(r"\bfirst\s+time\b", source, re.I))
            else:
                ok = _supported(_FIRST_EVIDENCE, source, _subject_words(text, m.end()))
            if is_repeat or not ok:
                unsupported.append(_snippet(text, m))
        masked = _ON_RECORD.sub(lambda x: " " * len(x.group(0)), text)
        for m in _RECORD_CLAIM.finditer(masked):
            if not _supported(_RECORD_CLAIM, source, _subject_words(masked, m.end())):
                unsupported.append(_snippet(text, m))
    return list(dict.fromkeys(unsupported))[:5]


def _side(text: str | None) -> tuple[float, bool, float] | None:
    """The first figure of a notable change's previous or current, signed, as (value, is a percentage, half
    its last printed digit); money is in crore when a unit is written after it ("₹19.78 lakh" is 0.1978)."""
    clean = _clean((text or "").replace("−", "-"))
    for m in _NUMBER.finditer(clean):
        raw = m.group(0)
        digits = raw.replace(",", "").strip("+-()")
        try:
            value = float(digits)
        except ValueError:
            continue
        negative = raw.startswith(("-", "(")) or clean[:m.start()].rstrip().endswith(("-", "("))
        is_pct = bool(re.match(r"\s*(?:%|per\s*cent)", clean[m.end():], re.I))
        unit = (None if is_pct else _money_unit(clean, m.end())) or 1
        half = 0.5 * 10 ** -len(digits.partition(".")[2]) / unit
        return (-value if negative else value) / unit, is_pct, half
    return None


def change_follows(previous: str | None, current: str | None, value: float, decimals: int, kind: str) -> bool:
    """A notable change's figure computed from its own previous and current: the difference, the change in
    per cent (on a loss too: a loss of 224.4 narrowing to 23.2 is "-89.7%"), the multiple, or between two
    percentages the change in points. Kanoria's net debt "+₹246.77 Cr" (₹34.96 Cr to ₹281.73 Cr) was held as
    a figure the filing does not print, though it is the line's own subtraction (loop round 3a, 2026-10-17).
    Signs are read loosely - a card writes a loss as "-₹6.38 Cr", "₹-6.38 Cr" or "₹6.38 Cr loss" - so the
    difference is tried both as written and between the sizes. Both sides are themselves rounded, so their
    rounding is carried through the arithmetic: a change worked out from the unrounded figures is not
    refused for a digit the card's previous and current do not show (the owner, 2026-10-18)."""
    before, after = _side(previous), _side(current)
    if not before or not after or not before[0]:
        return False
    (p, p_pct, dp), (c, c_pct, dc) = before, after
    half = 0.5 * 10 ** (-decimals)
    if kind == "pct":
        slack = 100 * (abs(c) + dc) / max(abs(p) - dp, 1e-9) * (dc / max(abs(c), 1e-9) + dp / abs(p)) if c else 0.0
        changes = [(c - p) / abs(p) * 100, (abs(c) - abs(p)) / abs(p) * 100]
        if p_pct and c_pct:
            changes.append(c - p)
            slack = max(slack, dc + dp)
        return any(abs(abs(x) - value) <= max(half, 0.05) + slack for x in changes)
    if kind in ("bps", "pp"):
        points, slack = abs(c - p), dc + dp
        if kind == "bps":
            points, slack = points * 100, slack * 100
        return p_pct and c_pct and abs(points - value) <= half + slack + 1e-9
    if kind == "x":
        if not c:
            return False
        ratios = (abs(c / p), abs(p / c))
        return any(abs(r - value) <= max(half, 0.02 * value) + r * (dc / abs(c) + dp / abs(p)) for r in ratios)
    if p_pct or c_pct:
        return False
    return any(abs(d - value) <= half + dc + dp + 1e-9 for d in (abs(c - p), abs(abs(c) - abs(p)), abs(c) + abs(p)))


def change_derived(previous: str | None, current: str | None, change: str | None) -> bool:
    """Every figure a notable change's `change` states follows from its own previous and current."""
    tokens = [t for t in _tokens(change or "") if not (t[3] == "plain" and t[0] <= 31 and t[1] == 0)]
    return bool(tokens) and all(change_follows(previous, current, v, d, kind) for v, d, _, kind, _ in tokens)


def check_card(card: Card, *sources: str, derived=()) -> GroundingResult:
    """Every figure on the card against the sources. A figure derived on the card (a share, a change,
    a multiple) passes when it follows from another figure on the same line and a source figure, and a
    notable change's change when it follows from its own previous and current (change_follows); any other
    derivation belongs in quantified_impact, where its formula is checked. `derived` are figures code has
    computed from the filing's own (a deal's shares x price, an impact's verified result), in crore.

    A ₹ crore figure must match a source figure at the unit written beside it ("INR 5445 Million"
    is ₹544.5 Cr, never ₹5,445 Cr). A bare figure (a table) matches at the filing's declared unit
    when it declares one ("(INR in Lakhs)": ₹28.63 Cr = 2,863), otherwise at any scale; the other
    sources (headline, memory) are already in crore when the filing declares a unit."""
    computed = " ; ".join(f"{v:.2f}" for v in derived if v is not None)
    index = SourceIndex(*sources, computed)
    unit = declared_unit(sources[0]) if sources else None
    filing_index = SourceIndex(sources[0] if sources else "")
    other_index = SourceIndex(*sources[1:], computed)
    year_like = {int(m.group(0)) for text in sources for m in _YEAR_TOKEN.finditer(text or "")}
    filing_scales, other_scales = ((unit,), (1,)) if unit else (CRORE_SCALES, CRORE_SCALES)
    texts = [("headline", card.headline), ("takeaway", card.takeaway), *(("fact", f.text) for f in card.what_happened),
             *(("insight", i.text) for i in card.why_it_matters)]
    # each point's own quote, which the quote checks find in the filing: a figure that is a sum or difference of its
    # figures is grounded through it (`quote_sum`)
    quote_of = {2 + k: f.quote for k, f in enumerate(card.what_happened)}
    quote_of |= {2 + len(card.what_happened) + k: i.quote for k, i in enumerate(card.why_it_matters)}
    if card.deal_value and card.deal_value.amount_cr:
        texts.append(("deal", f"{card.deal_value.amount_cr:g} Cr"))
    quote_of |= {len(texts) + k: kn.quote for k, kn in enumerate(card.key_numbers)}
    texts += [("key", f"{k.value} {k.change or ''}") for k in card.key_numbers]
    sides: dict[int, tuple[str | None, str | None, int]] = {}   # a change line: its previous, current, and where its change starts
    for c in card.notable_changes:
        head = f"{c.previous or ''} ; {c.current or ''} ; "
        sides[len(texts)] = (c.previous, c.current, len(head))
        quote_of[len(texts)] = c.quote
        texts.append(("change", head + (c.change or "")))
    track = card.track_next
    texts += [("track", f"{k.kpi} {k.target or ''}") for k in track.kpis_to_verify]
    # a figure one point grounds through its own quote's sum stands wherever the card repeats it (the headline, the
    # takeaway): Kernex's ₹660 Cr of limits headed the card as well as its key number
    summed = set()
    for n, quote in quote_of.items():
        if quote and n < len(texts):
            crore_here = _crore_positions(texts[n][1] or "")
            summed |= {(kind, round(value, decimals)) for value, decimals, pos, kind, _ in _tokens(texts[n][1] or "")
                       if quote_sum(value, decimals, kind, pos in crore_here, quote, unit)}
    checked, ungrounded, headline_bad, amounts_bad = 0, [], [], []
    for n, (where, text) in enumerate(texts):
        tokens = _tokens(text or "")
        line_amounts = [v for v, d, _, kind, _ in tokens if kind in ("plain", "qty") and v > 31 and index.stated(v, d)]
        line_pcts = [v for v, _, _, kind, _ in tokens if kind == "pct"]
        crore_at = _crore_positions(text or "")
        for value, decimals, pos, kind, raw in tokens:
            if value == 0 or (kind == "plain" and value <= 31 and decimals == 0):
                continue
            checked += 1
            if n in sides and pos >= sides[n][2] and change_follows(sides[n][0], sides[n][1], value, decimals, kind):
                continue
            if pos in crore_at:
                if (filing_index.stated_crore(value, decimals, filing_scales)
                        or other_index.stated_crore(value, decimals, other_scales)):
                    continue
            elif index.grounded(value, decimals, kind=kind) or _from_line(value, decimals, kind, line_amounts, line_pcts, index):
                continue
            if (kind, round(value, decimals)) in summed:
                continue
            if "," in raw and not decimals and kind in ("plain", "qty") and int(value) in year_like:
                continue  # "2,052 units" is the table's 2052, which the sources set aside as a year
            label = raw.strip("()-") + {"pct": "%", "bps": " bps", "pp": " pp", "x": "x"}.get(kind, "")
            ungrounded.append(label)
            if where == "headline" and kind in ("plain", "qty"):
                headline_bad.append(label)
            if kind in ("plain", "qty") and (value > 31 or pos in crore_at):
                amounts_bad.append(label)
    if checked == 0:
        return GroundingResult(1.0, 0, [])
    return GroundingResult(round(1 - len(ungrounded) / checked, 3), checked, ungrounded, headline_bad, amounts_bad)


def quote_sum(value: float, decimals: int, kind: str, crore: bool, quote: str, unit: float | None = None) -> bool:
    """A card figure that is the sum of two to four figures of its own quote, or the difference of two (held-card audit,
    22 Oct 2026: 111 of 233 false holds were such sums, "₹400 Cr + ₹390 Cr of guarantees = ₹790 Cr", "borrowings 7,877 +
    11,820 lakh = ₹196.97 Cr"). Only the point's quote, which the quote checks find in the filing, lends its figures: any
    two figures of the whole filing summed to a random fake 56% of the time (F93), the quote's 0.3% (6 of 2,330). Each
    part is read at its own unit ("Rs. 38.65 million + Rs 90.18 million" is ₹12.88 Cr, never Zydus's ₹128.83 Cr), a
    bare part at the filing's declared unit, else as crore; a percentage only from percentages."""
    clean = _clean(quote)
    if kind in ("pp", "bps"):
        # a margin's change: the difference of two of the quote's percentages (Nestlé's "24.12 %" and "21.59 %", +2.53 pts)
        pcts = [v for v, _, _, k, _ in _tokens(quote) if k == "pct"][:12]
        points = value / 100 if kind == "bps" else value
        tolerance = 0.5 * 10 ** (-decimals) * (0.01 if kind == "bps" else 1) + 1e-9
        return any(abs(abs(a - b) - points) <= tolerance for a, b in itertools.combinations(pcts, 2))
    parts = []
    for v, _, pos, k, raw in _tokens(quote):
        if v <= 0 or (k == "pct") != (kind == "pct") or k in ("bps", "pp", "x"):
            continue
        if crore and k != "pct":
            end = pos + len(raw)
            own = _money_unit(clean, end)
            # a bare part: the unit the quote itself declares before it (Kernex's "Amount (Rs. In Crore) 125.00 ..."),
            # else the filing's
            declared = None
            for m in _DECLARED_UNIT.finditer(quote, 0, pos):
                declared = _PER_CRORE.get(next(g for g in m.groups() if g).lower().rstrip("s"))
            v = v / (own if own is not None else declared or unit or 1)
        parts.append(v)
    parts = parts[:12]
    tolerance = 0.5 * 10 ** (-decimals) + 1e-9
    for r in (2, 3, 4):
        for combo in itertools.combinations(parts, r):
            if abs(sum(combo) - value) <= tolerance or (r == 2 and abs(abs(combo[0] - combo[1]) - value) <= tolerance):
                return True
    return False


def _from_line(value: float, decimals: int, kind: str, amounts: list[float], pcts: list[float], index: SourceIndex) -> bool:
    """"₹80 Cr LoI, 18% of FY26 sales": 18% = 80 / a source figure. "Up 150 bps to 14.9%": a source
    margin 150 bps away from 14.9. "2.1x its revenue": a line amount over a source figure."""
    tolerance = 0.5 * 10 ** (-decimals) + 1e-9
    candidates = [b for b in index.values if b > 1]
    if kind == "pct":
        return any(abs(a / b * 100 - value) <= max(tolerance, 0.05) or abs((a - b) / b * 100 - value) <= max(tolerance, 0.05)
                   for a in amounts for b in candidates)
    if kind == "x":
        return any(abs(a / b - value) <= max(tolerance, 0.05) for a in amounts for b in candidates)
    if kind in ("bps", "pp"):
        points = value / 100 if kind == "bps" else value
        return any(abs(abs(a - b) - points) <= (0.01 if kind == "bps" else tolerance) + 1e-6
                   for a in pcts for b in index.values if b <= 100)
    return False


SCALE_METRICS = ("revenue", "ebitda", "pbt", "pat")
SCALE_JUMP = 5  # a quarterly figure this many times the company's recent quarters is a unit slip, not news
_PROFIT_LABELS = {"ebitda": "EBITDA", "pbt": "PBT", "pat": "PAT", "revenue": "Revenue"}


def scale_issues(metrics: list, history: list[dict]) -> list[str]:
    """Quarterly figures out of scale, a lakh/million table read as crore (Ahluwalia's "PAT ₹495 Cr" for
    ₹49.5 Cr) or the reverse. Two rules: a profit line above the same quarter's revenue and total
    income; a figure more than SCALE_JUMP times the company's largest of its last four quarters in
    memory, or a revenue below a fifth of its smallest. `metrics` are the reply's FinancialMetrics,
    `history` the dossier's stored ones."""
    now: dict[str, dict[str, float]] = {}
    for m in metrics:
        if m.metric in SCALE_METRICS and m.value is not None and quarter_index(m.period) is not None:
            now.setdefault(m.period, {})[m.metric] = float(m.value)
    totals = {m.period: float(m.value) for m in metrics if m.metric == "total_income" and m.value is not None}
    # what lifts a profit above revenue for real (held-card audit, 22 Oct 2026: 14 of the 16 "above revenue" and
    # "over 5x" holds were real): Jaykay's ₹181.83 Cr exceptional gain, Hester's loan-waiver gain, DLF's other income
    # and JV share, Kiri's tax credit. Not for EBITDA, which leaves them out (Hester's ₹111.81 Cr with its exceptional
    # gain inside was a true hold).
    extra: dict[str, float] = {}
    for m in metrics:
        if m.value is None:
            continue
        if m.metric in ("exceptional_items", "other_income", "share_associates"):
            extra[m.period] = extra.get(m.period, 0.0) + abs(float(m.value))
        elif m.metric == "tax_expense" and float(m.value) < 0:
            extra[m.period] = extra.get(m.period, 0.0) - float(m.value)
    issues = []
    for period, values in now.items():
        top = max(values.get("revenue") or 0, totals.get(period) or 0)
        for metric in ("ebitda", "pbt", "pat"):
            value = values.get(metric)
            if value is not None and metric != "ebitda":
                value -= extra.get(period, 0.0)
            # a profit only: a loss beyond revenue is what a distressed or pre-revenue company reports (Supreme Infra's
            # finance cost alone was 2.5x its revenue, SPARC, McNally - all held for it, needs-review sweep 2026-10-20),
            # and a loss read at the wrong unit is still caught by the jump against the company's own quarters below
            if value is not None and top >= 1 and value > top * 1.02:
                issues.append(f"{_PROFIT_LABELS[metric]} {period} ₹{values[metric]:,.2f} Cr is above revenue ₹{top:,.2f} Cr")
        here = quarter_index(period)
        for metric, value in values.items():
            past = sorted(((quarter_index(h["period"]), abs(float(h["value"]))) for h in history
                           if h.get("metric") == metric and h.get("value") is not None
                           and quarter_index(str(h.get("period"))) is not None and quarter_index(h["period"]) < here),
                          reverse=True)[:4]
            sizes = [v for _, v in past if v >= 1]
            if len(sizes) < 2:
                continue
            label = _PROFIT_LABELS[metric]
            beyond = abs(value) - (extra.get(period, 0.0) if metric in ("pbt", "pat") else 0.0)
            if beyond > SCALE_JUMP * max(sizes):
                issues.append(f"{label} {period} ₹{value:,.2f} Cr is over {SCALE_JUMP}x the company's recent quarters "
                              f"(at most ₹{max(sizes):,.2f} Cr)")
            elif metric == "revenue" and abs(value) < min(sizes) / SCALE_JUMP:
                issues.append(f"{label} {period} ₹{value:,.2f} Cr is under a fifth of the company's recent quarters "
                              f"(at least ₹{min(sizes):,.2f} Cr)")
    return issues


_MARGINS = {"ebitda_margin": "ebitda", "ebitda_margin_pct": "ebitda", "pat_margin": "pat", "pat_margin_pct": "pat",
            "net_margin": "pat", "net_profit_margin": "pat", "pbt_margin": "pbt", "pbt_margin_pct": "pbt"}
MARGIN_TOLERANCE_PP = 1.0
_KEY_AMOUNT = re.compile(r"(-?\(?[\d,]+(?:\.\d+)?\)?)\s*(?:crs?\b|crores?\b)", re.I)
_KEY_PCT = re.compile(r"(-?[\d.]+)\s*%")


def _key_figures(key_numbers: list) -> dict[str, float]:
    """revenue / ebitda / pat and their margins as the card's key numbers state them."""
    out: dict[str, float] = {}
    for k in key_numbers:
        label = (k.label or "").lower()
        base = "ebitda" if "ebitda" in label else "pat" if re.search(r"\bpat\b|net profit|profit after tax", label) \
            else "pbt" if re.search(r"\bpbt\b|profit before tax", label) \
            else "revenue" if re.search(r"revenue|sales|income from operations", label) else None
        if not base:
            continue
        if "margin" in label:
            m = _KEY_PCT.search(k.value or "")
            if m:
                out.setdefault(f"{base}_margin", float(m.group(1)))
        else:
            m = _KEY_AMOUNT.search(k.value or "")
            if m:
                raw = m.group(1).replace(",", "")
                negative = raw.startswith("-") or raw.startswith("(")
                out.setdefault(base, -float(raw.strip("-()")) if negative else float(raw.strip("-()")))
    return out


def margin_issues(metrics: list, key_numbers: list = ()) -> list[str]:
    """A stated margin that does not fit the same period's figures (Ahluwalia: EBITDA "₹756 Cr" on
    ₹952 Cr revenue "at a 7.9% margin"; 756 / 952 is 79%). From the reply's quarterly metrics, and
    from the card's key numbers for its own figures."""
    sets: list[tuple[str, dict[str, float]]] = []
    by_period: dict[str, dict[str, float]] = {}
    for m in metrics:
        if m.value is not None:
            by_period.setdefault(m.period, {})[m.metric] = float(m.value)
    sets += sorted(by_period.items())
    if key_numbers:
        sets.append(("key numbers", _key_figures(key_numbers)))
    issues = []
    for period, values in sets:
        revenue = values.get("revenue")
        if not revenue or revenue <= 0:
            continue
        for name, base in _MARGINS.items():
            margin, amount = values.get(name), values.get(base)
            if name not in values or amount is None:
                continue
            implied = amount / revenue * 100
            # a company's own margin on total income (Adani Power's 43% = 8,369 / 19,322, GMR's 25%; held-card audit)
            on_total = amount / values["total_income"] * 100 if (values.get("total_income") or 0) > 0 else None
            if abs(implied - margin) > MARGIN_TOLERANCE_PP and (on_total is None or abs(on_total - margin) > MARGIN_TOLERANCE_PP):
                issue = (f"{base.upper()} ₹{amount:,.2f} Cr on revenue ₹{revenue:,.2f} Cr is a {implied:.1f}% margin, "
                         f"not the stated {margin:g}% ({period})")
                if issue not in issues:
                    issues.append(issue)
    return issues


# A card amount written in ₹ crore that matches no source but matches one statement figure read at a
# wrong unit: the slips a model makes with a lakh or million table (7,560.12 lakh written "₹756 Cr",
# 205.10 million written "₹205 Cr"). Only for a filing that declares a single unit, where the right
# reading is not in doubt.
def _near_amount(index: SourceIndex, target: float) -> bool:
    """A source figure within 0.5% of target, years (1990–2100) aside."""
    lo, hi = target * 0.995, target * 1.005
    i = bisect.bisect_left(index.values, lo)
    return any(not (1990 <= v <= 2100 and v == int(v)) for v in index.values[i:bisect.bisect_right(index.values, hi)])


_LABEL_STOP = {"from", "with", "were", "this", "that", "year", "quarter", "rupees", "crore", "crores", "lakh", "lakhs",
               "million", "total", "rose", "fell", "grew", "about", "nearly", "over", "under", "against", "versus"}


def _copied_from_its_row(filing: str, raw: str, before: str, after: str = "") -> bool:
    """The card's figure is printed digit for digit on a line of the filing that carries the words the card
    puts around it ("exceptional items of ₹3,595 Cr", "₹6,715 Cr gain from SOFIE sale"): the model copied
    that row's number and kept "Cr"."""
    near = re.findall(r"[a-z]{4,}", before.lower())[-6:] + re.findall(r"[a-z]{4,}", after.lower())[:6]
    words = {w for w in near if w not in _LABEL_STOP}
    digits = raw.replace(",", "").strip("()+-")
    if not words or len(digits.replace(".", "")) < 3:
        return False
    pattern = re.compile(rf"(?<![\d.]){re.escape(digits)}(?![\d]|\.\d)")
    lines = filing.splitlines()
    for i, line in enumerate(lines):
        if not pattern.search(re.sub(r"(?<=\d),(?=\d)", "", line)):
            continue
        # the row it is on, or in prose the sentence it ends ("...sale of investment in SOFIE ... aggregating to
        # ₹ 6,715 million."): up to three lines back, stopping at a sentence's end or at a table row
        context = [line]
        for prev in reversed(lines[max(0, i - 3):i]):
            if len(_NUMBER.findall(prev)) >= 2 or prev.rstrip().endswith(".") or len(_NUMBER.findall(line)) >= 2:
                break
            context.append(prev)
        if words & set(re.findall(r"[a-z]{4,}", " ".join(context).lower())):
            return True
    return False


# A rupee amount written out in full, with no unit after it: "Rs 11,10,59,061", "Rs. 1,165,179,600" (round 4)
_WHOLE_RUPEES = re.compile(r"(?:₹|\brs\.?|\binr)\s*(\d{1,3}(?:,\d{2,3}){2,}(?:\.\d+)?|\d{7,}(?:\.\d+)?)(?!\s*[,.]?\d)"
                           r"(?!\s*(?:/-\s*)?(?:lakhs?|lacs?|crores?|cr\b|millions?|mn\b|billions?|bn\b|thousands?))", re.I)


def whole_rupee_crores(filing: str) -> list[float]:
    """The filing's amounts written in whole rupees, in ₹ crore."""
    out = []
    for m in _WHOLE_RUPEES.finditer(filing or ""):
        try:
            rupees = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if rupees >= 1e5:
            out.append(rupees / 1e7)
    return out


_UNIT_WORD = re.compile(r"(?<![a-z])(lakhs?|lacs?|millions?|mn|billions?|bn|thousands?)(?![a-z])", re.I)


class _ReadAtUnit:
    """Whether a card's crore figure is already the right reading of a figure the filing prints at that figure's own unit.

    The unit fixer turned right figures wrong (held-card audit, 22 Oct 2026): Newgen's employee cost ₹190.10 Cr (19,010 in
    ₹ lakh) became ₹19,010 Cr, Tinna Rubber's EBITDA ₹30.18 Cr (3,018 lakh) ₹301.8 Cr, Sudarshan's ₹247 Cr (a slide "In ₹
    Cr") ₹24.7 Cr because another slide was in ₹ Mn, Heritage's ₹62.11 Cr (621.1 million) ₹6,211 Cr, Jaykay's ₹262.66 Cr
    ₹2.63 Cr. Each time the corrected figure fitted the filing at one unit while the card's own fitted it at the unit its
    page declares. A unit is the one declared last before the figure on its page (`unit_before`); on a page that declares
    none (or whose header the OCR garbled, Tinna's "fRl. in lakh"), any unit the document writes anywhere."""

    def __init__(self, filing: str):
        self.filing = filing or ""
        self._tokens = None

    def _prepare(self) -> None:
        raw = self.filing
        text = _clean(raw)   # figures from the cleaned text, unit headers from the raw one: _clean keeps positions
        self.pages = [m.start() for m in re.finditer(r"--- Page", raw)]
        self.decls = [(m.start(), _PER_CRORE.get(next(g for g in m.groups() if g).lower().rstrip("s")))
                      for m in _DECLARED_UNIT.finditer(raw)]
        self.decl_pos = [p for p, _ in self.decls]
        words = {w.lower().rstrip("s") for w in _UNIT_WORD.findall(raw)}
        # only a document of one unit says which unit an undeclared page is in: Goodyear's annual report writes lakh,
        # million, thousand and billion, and its "15,287" (lakh) read as million fitted the card's wrong ₹1,528.7 Cr
        units = {_PER_CRORE_WORD[w] for w in words if w in _PER_CRORE_WORD} - {1}
        self.document = units if len(units) == 1 else set()
        # (figure, its own unit or None, position); a figure's own unit word wins over its page's: Jaykay's corrigendum
        # "Rs. 26,265.71 Lakh was inadvertently mentioned as Rs. 262.66 Lakh" on a page declared in million
        self._tokens = []
        for m in _NUMBER.finditer(text):
            try:
                value = abs(float(m.group(0).replace(",", "").strip("+").strip("()")))
            except ValueError:
                continue
            if value >= 1:
                self._tokens.append((value, _money_unit(text, m.end()), m.start()))
        # a decimal point the text layer turned into a space: Heritage's "7,480 10" is 7,480.10 (₹ million)
        for m in re.finditer(r"(?<![\d.,])(\d[\d,]*) (\d{2})(?![\d.,])", text):
            self._tokens.append((float(m.group(1).replace(",", "") + "." + m.group(2)), None, m.start()))

    def _unit_at(self, pos: int) -> float | None:
        i = bisect.bisect_left(self.decl_pos, pos) - 1
        if i < 0:
            return None
        start, unit = self.decls[i]
        page = self.pages[bisect.bisect_right(self.pages, pos) - 1] if self.pages and self.pages[0] <= pos else 0
        return unit if start >= max(page, pos - 8000) else None

    def __call__(self, value: float, decimals: int) -> bool:
        if self._tokens is None:
            self._prepare()
        tolerance = min(0.5 * 10 ** (-decimals), 0.002 * value) + 1e-9
        for figure, own, pos in self._tokens:
            page_unit = self._unit_at(pos)
            units = {own} if own is not None else {page_unit} if page_unit is not None else self.document
            for unit in units:
                if unit and abs(figure / unit - value) <= tolerance:
                    return True
        return False


def unit_slips(texts: list[str], filing: str, *others: str) -> list[tuple[str, float, int, float, int]]:
    """(raw, value, decimals, corrected, corrected_decimals) for each card amount to correct.

    Three readings, in order: a figure the filing writes with its own unit ("INR 3 (Three) Million" carded "₹3 Cr",
    Excelsoft), whatever unit the tables declare; an amount written out in whole rupees ("Rs 11,10,59,061" carded "₹1.11
    Cr", Nestle; "Rs. 1,165,179,600" as "₹1,165 Cr", Anlon); and a table figure in the declared unit read a power of
    ten off ("(Rs billion) 1,562.8" carded "₹15,628 Cr", RBL). A card figure the filing states in crore is never touched."""
    unit = declared_unit(filing)
    # a foreign-currency amount is no rupee figure at any unit: it is held, never "corrected" (foreign_as_rupees)
    filing = _FOREIGN.sub(" ", filing or "")
    filing_index, other_index = SourceIndex(filing), SourceIndex(*others)
    whole = whole_rupee_crores(filing)
    if not unit and not whole and not any(u != 1 for u in filing_index._by_unit):
        return []
    slips: dict[str, tuple[str, float, int, float, int]] = {}
    read_right = _ReadAtUnit(filing)
    for text in texts:
        crore_at = _crore_positions(text or "")
        for value, decimals, pos, kind, raw in _tokens(text or ""):
            if pos not in crore_at or value < 1 or raw in slips:
                continue
            tolerance = 0.5 * 10 ** (-decimals) + 1e-9
            if other_index.stated_crore(value, decimals, (1,)) or _near_amount(other_index, value) \
                    or _near(filing_index._by_unit.get(1, []), value, tolerance):
                continue   # memory, the scale block or the filing itself writes this many crore
            if read_right(value, decimals):
                continue   # already the right reading of a figure at its own page's unit: never "corrected"
            # 1. a figure with its own unit, whatever unit the tables declare
            fits = [(round(value / u, 2), 2) for u, values in filing_index._by_unit.items()
                    if u != 1 and _near(values, value, tolerance)]
            if len(fits) == 1:
                slips[raw] = (raw, value, decimals, *fits[0])
                continue
            # a bare table figure counts in the table's declared unit, never as crore when another unit is declared
            if filing_index.stated_crore(value, decimals, (unit,) if unit else CRORE_SCALES):
                continue
            # 2. a whole-rupee amount, a power of ten off
            tolerance = 0.5 * 10 ** (-decimals) + 1e-9
            fits = sorted({(round(c, 2), 2) for c in whole for k in (-3, -2, -1, 1, 2, 3)
                           if abs(value - c * 10 ** k) <= max(tolerance, 0.002 * c * 10 ** k)})
            if len(fits) == 1:
                slips[raw] = (raw, value, decimals, *fits[0])
                continue
            if not unit or value < 10:
                continue   # a small bare figure is ambiguous against a table's unit
            if (_near_amount(filing_index, value * unit) or _near_amount(other_index, value)) \
                    and not _copied_from_its_row(filing, raw, (text or "")[:pos], (text or "")[pos + len(raw):]):
                # within 0.5% of a real figure: a rounding or a derivation ("₹955 Cr" beside ₹951.96 Cr), not a
                # slip - unless the card copied a row's own digits under that row's own name. On a long statement
                # some figure sits within 0.5% by chance: Jubilant's "exceptional items of ₹3,595 Cr" is the
                # row "Exceptional items (3,595)" in ₹ million, and a 35,9xx elsewhere kept it uncorrected.
                continue
            # 3. the declared unit read a power of ten off: the table figure is value * 10**k in that unit's terms
            fits = []
            for k in (-4, -3, -2, -1, 1, 2, 3, 4):
                right = value * 10 ** k
                right_decimals = max(0, decimals - k)
                if filing_index.stated_crore(right, right_decimals, (unit,)):
                    fits.append((round(right, min(right_decimals, 2)), min(right_decimals, 2)))
            if len(fits) == 1:
                slips[raw] = (raw, value, decimals, *fits[0])
    return list(slips.values())


# An amount the filing writes in another currency ("NGN 90 million", "USD 350 mn", "EUR 15.37 lakh"). Anlon's card gave a
# Nigerian subsidiary's NGN 90 million as "₹90 million" (round 4): no rupee unit can correct that, so the card is held.
_FOREIGN = re.compile(r"(?:\b(?:USD|US\$|NGN|EUR|GBP|AED|SGD|JPY|CHF|CAD|AUD|SAR|QAR|KES|ZAR)|[$€£¥₦])\s*"
                      r"(\d[\d,]*(?:\.\d+)?)\s*(millions?|mn|billions?|bn|lakhs?|crores?|thousands?)?", re.I)


def foreign_amounts(text: str | None) -> list[tuple[float, str]]:
    """(number as written, currency) for each amount the text writes in a currency other than the rupee."""
    out = []
    for m in _FOREIGN.finditer(text or ""):
        try:
            out.append((float(m.group(1).replace(",", "")), m.group(0).split()[0][:4]))
        except ValueError:
            continue
    return out


def foreign_as_rupees(texts: list[str], filing: str) -> list[str]:
    """Card amounts in ₹ that are the filing's foreign-currency figure with the currency swapped, when the filing writes
    that number in no rupee amount at all."""
    foreign = foreign_amounts(filing)
    if not foreign:
        return []
    rupee_numbers = {round(v, 2) for v, _ in _numbers(_FOREIGN.sub(" ", filing))}
    problems = []
    for text in texts:
        for m in re.finditer(r"₹\s*(\d[\d,]*(?:\.\d+)?)", text or ""):
            value = float(m.group(1).replace(",", ""))
            hit = next((cur for v, cur in foreign if abs(v - value) < 1e-9), None)
            if hit and round(value, 2) not in rupee_numbers:
                problems.append(f"₹{m.group(1)} is the filing's {hit} figure, not a rupee amount")
    return sorted(set(problems))
