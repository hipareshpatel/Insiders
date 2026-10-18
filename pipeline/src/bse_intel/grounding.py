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
_CURRENCY = re.compile(r"(?:₹|\b(?:rs\.?|inr|usd|cad|eur|gbp)|us\$|\$)\s*", re.I)
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
    r"(?:₹|\brs\.?|\binr|\brupees?)\s*(?:in\s*)?(?:(lakhs?|lacs?|crores?|millions?|mn|thousands?)(?![a-z])|('?000)s?(?![\d,a-z]))"
    r"|\bin\s*(?:₹|rs\.?|inr|rupees?)\s*(?:(lakhs?|lacs?|crores?|millions?|mn|thousands?)(?![a-z])|('?000)s?(?![\d,a-z]))"
    # the rupee sign mangled and glued to the word, with no "in": "(XLakhs)", "( Ė Crores)". Not after a
    # figure, where a unit belongs to that figure alone ("12,345.67 (lakhs)").
    r"|(?<![\d.,]\s)(?<![\d.,])\([ \t]*[^\s()\w]?[A-Za-z']{0,2}[^\s()\w]?[ \t]*(lakhs?|lacs?|crores?|millions?)[ \t]*\)"
    r"|^[ \t]*[(\[{/\"'`]?[ \t]*[^\s()]{0,3}[ \t]*in[ \t]*(lakhs?|lacs?|crores?|millions?|thousands?)\.?[ \t]*\)"
    r"|mount[ \t]+(?:in|ln|1n|111)[ \t]+(lakhs?|lacs?|crores?|millions?|thousands?)[ \t]+of\b",
    re.I | re.M)  # Jubilant's rupee sign arrives as a Tibetan letter: "(ཪ in million)"; Heritage's
# scanned headers as "(,\mount in millions of Z unless otherwise stated)" and "(Amount 111 millions oft"
# SML writes the currency out ("(Rupees in Crores, except share data)") and some filers write thousands
# as "(Rs. 000)" without the apostrophe; neither was read, so those statements had no unit at all.
_PER_CRORE = {"lakh": 100, "lac": 100, "million": 10, "mn": 10, "thousand": 10_000, "'000": 10_000, "000": 10_000,
              "crore": 1}
UNIT_NAMES = {100: "₹ lakh", 10: "₹ million", 10_000: "₹ thousand"}
_CRORE_AFTER = re.compile(r"\s*(?:cr\b|crores?\b)", re.I)
# The unit written right after a source figure ("INR 5445 Million", "Rs. 2,025 lakhs"), as figures
# per ₹ crore. Kanoria's RPT notice (Apr 2025) mixes million, lakh and crore, so no single declared
# unit exists; "5445 Million" was still written as "₹5,445 Cr".
_MONEY_AFTER = re.compile(r"\s*(lakhs?|lacs?|crores?|cr|millions?|mn|billions?|bn|thousands?)(?![a-z])", re.I)
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


class SourceIndex:
    def __init__(self, *texts: str):
        self.points = [(v, i, pos) for i, text in enumerate(texts) for v, _, pos, _, _ in _tokens(text or "") if v > 0]
        self.values = sorted({v for v, _, _ in self.points})
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
        return any(_near(self._plain, value * s, rounding * s + abs(value * s) * 1e-6) for s in plain_scales)

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
    if card.deal_value and card.deal_value.amount_cr:
        texts.append(("deal", f"{card.deal_value.amount_cr:g} Cr"))
    texts += [("key", f"{k.value} {k.change or ''}") for k in card.key_numbers]
    sides: dict[int, tuple[str | None, str | None, int]] = {}   # a change line: its previous, current, and where its change starts
    for c in card.notable_changes:
        head = f"{c.previous or ''} ; {c.current or ''} ; "
        sides[len(texts)] = (c.previous, c.current, len(head))
        texts.append(("change", head + (c.change or "")))
    track = card.track_next
    texts += [("track", f"{k.kpi} {k.target or ''}") for k in track.kpis_to_verify]
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
    issues = []
    for period, values in now.items():
        top = max(values.get("revenue") or 0, totals.get(period) or 0)
        for metric in ("ebitda", "pbt", "pat"):
            value = values.get(metric)
            if value is not None and top >= 1 and abs(value) > top * 1.02:
                issues.append(f"{_PROFIT_LABELS[metric]} {period} ₹{value:,.2f} Cr is above revenue ₹{top:,.2f} Cr")
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
            if abs(value) > SCALE_JUMP * max(sizes):
                issues.append(f"{label} {period} ₹{value:,.2f} Cr is over {SCALE_JUMP}x the company's recent quarters "
                              f"(at most ₹{max(sizes):,.2f} Cr)")
            elif metric == "revenue" and abs(value) < min(sizes) / SCALE_JUMP:
                issues.append(f"{label} {period} ₹{value:,.2f} Cr is under a fifth of the company's recent quarters "
                              f"(at least ₹{min(sizes):,.2f} Cr)")
    return issues


_MARGINS = {"ebitda_margin": "ebitda", "ebitda_margin_pct": "ebitda", "pat_margin": "pat", "pat_margin_pct": "pat",
            "net_margin": "pat", "net_profit_margin": "pat", "pbt_margin": "pbt", "pbt_margin_pct": "pbt"}
MARGIN_TOLERANCE_PP = 1.0
_KEY_AMOUNT = re.compile(r"(-?\(?[\d,]+(?:\.\d+)?\)?)\s*(?:cr\b|crores?\b)", re.I)
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
            if abs(implied - margin) > MARGIN_TOLERANCE_PP:
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


def unit_slips(texts: list[str], filing: str, *others: str) -> list[tuple[str, float, int, float, int]]:
    """(raw, value, decimals, corrected, corrected_decimals) for each card amount to correct."""
    unit = declared_unit(filing)
    filing_index, other_index = SourceIndex(filing), SourceIndex(*others)
    if not unit and not any(u != 1 for u in filing_index._by_unit):
        return []
    slips: dict[str, tuple[str, float, int, float, int]] = {}
    for text in texts:
        crore_at = _crore_positions(text or "")
        for value, decimals, pos, kind, raw in _tokens(text or ""):
            if pos not in crore_at or value < 10 or raw in slips:
                continue
            if filing_index.stated_crore(value, decimals, (unit,) if unit else CRORE_SCALES)                     or other_index.stated_crore(value, decimals, (1,)):
                continue
            if not unit:
                # No table unit, but figures written with their own ("INR 14,077 million" in a rating
                # report, written "₹14,077 Cr"): the card copied the number and kept "Cr".
                fits = [(round(value / u, 2), 2) for u, values in filing_index._by_unit.items()
                        if u != 1 and _near(values, value, 0.5 * 10 ** (-decimals) + 1e-9)]
                if len(fits) == 1 and not _near_amount(other_index, value):
                    slips[raw] = (raw, value, decimals, *fits[0])
                continue
            if (_near_amount(filing_index, value * unit) or _near_amount(other_index, value)) \
                    and not _copied_from_its_row(filing, raw, (text or "")[:pos], (text or "")[pos + len(raw):]):
                # within 0.5% of a real figure: a rounding or a derivation ("₹955 Cr" beside ₹951.96 Cr), not a
                # slip - unless the card copied a row's own digits under that row's own name. On a long statement
                # some figure sits within 0.5% by chance: Jubilant's "exceptional items of ₹3,595 Cr" is the
                # row "Exceptional items (3,595)" in ₹ million, and a 35,9xx elsewhere kept it uncorrected.
                continue
            fits = []
            for wrong in (s for s in CRORE_SCALES if s != unit):  # the model divided by `wrong`, not by `unit`
                factor = unit / wrong                               # its figure is the true one times this
                shift = round(math.log10(factor))
                right, right_decimals = value / factor, max(0, decimals + shift)
                if filing_index.stated_crore(right, right_decimals, (unit,)):
                    fits.append((round(right, min(right_decimals, 2)), min(right_decimals, 2)))
            if len(fits) == 1:
                slips[raw] = (raw, value, decimals, *fits[0])
    return list(slips.values())
