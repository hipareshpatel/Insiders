"""CARD_TEXT_SUPPORT (TODO 142, prompt audit of 30 Oct 2026): checks on the card text no other check reads, and the
sources-only prompt rule.

Two checks, both run beside ``ground_all_fields`` and both returning change-log notes:

* ``support_check``: a risk, catalyst, milestone, pending approval, the core catalyst, a change's "why" and a SECTOR (or
  memory-less MEMORY) insight may use only names and content words the filing, the memory block or the scale block print
  (never the peer context). An item with two or more such words missing, or with a whole number of 31 or less beside a
  noun ("5 observations") or a day-month date ("30 Oct") the sources do not print, is dropped. The 37 WRONG items of the
  two blind rounds of 30 Oct: Dalmia Bharat, Merino wool, MSEDCL, "5 USFDA observations", an earnings call "30 Oct".
* ``label_check``: a point that names "net profit", "to shareholders", "discontinued" or "total comprehensive income" on a
  figure needs the matching label in its quote or on the filing's own line for that figure.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .gate import _flat, unprinted_names
from .grounding import CRORE_SCALES, _tokens

# --- the words a card may use without a source: generic finance and card vocabulary ----------------------------------
# Hand list (in-sample tuned on 17 blind-reviewed filings). "capacity", "demand", "passengers", "volumes" are deliberately
# NOT here: Grasim-type invented drivers ("capacity growth", "passenger demand") are exactly what the check must catch.
GENERIC_WORDS = frozenset("""
company companies business businesses market markets sector sectors industry industries shareholders shareholder investors
investor management period periods quarter quarters current previous earlier future further continued continue continues
continuing growth margin margins revenue revenues profit profits profitability earnings income results result
performance impact impacts effect effects pressure pressures expected expectation expectations potential possible
likely approval approvals expansion expansions regulatory regulation regulations regulator compliance financial
financials operating operations operational operation higher lower stronger weaker strong weaker sustained
sustainable improved improvement improving declined decline declining increase increased increasing decrease
decreased across through during following related relating between within without against beyond towards toward
remains remain remained should would could including include includes included announced announcement announcements
disclosed disclosure disclosures reported reporting report reports whether because despite however overall
consolidated standalone annual yearly monthly quarterly future outlook guidance target targets execution
monitor monitoring tracking tracked watch ability inability depend dependent dependence dependency
subsequent timely timing delays delay delayed realisation realization conversion transition
priced pricing prices price costs cost-related inflation volatility volatile uncertainty uncertain
adverse adversely positive negative material materially significant significantly substantial substantially
additional addition support supported supporting driven driving drivers driver benefit benefits benefited
upcoming ongoing planned planning proposed proposal proposals pending completion complete completed
approved approvals announced shareholders' stakeholders customers customer clients client
balance sheet statement statements disclosure strength strengthen strengthening position positions
reflecting reflects reflected resulting results leading leads supports indicates indicated indicating
sequential sequentially analysts analyst investors' standalone's
expanding expands expanded offset offsetting offsets steady alongside leverage deleveraging reduction reduced reducing
buildup accumulation aggressive massive severe optimisation burdens deployment freeing absorption absorbed shifts
depressing seasonally seasonal topline though visibility intensity broadly stable guided behind exceeding reached
scaling momentum
""".split())

# words that stay checked whatever else: the invented drivers of the blind rounds ("capacity growth", "passenger demand")
KEEP_CHECKED = frozenset("capacity capacities passenger passengers utilisation utilization volumes volume plants "
                         "subsidiary subsidiaries observations observation scheme schemes".split())
_STEM_SUFFIXES = ("ations", "ation", "ments", "ment", "ities", "ity", "ings", "ing", "ness", "ions", "ion", "ies", "ied",
                  "ed", "es", "ly", "s", "y")
_GENERIC_FILE = Path(__file__).resolve().parents[2] / "config" / "generic_words.txt"
_WORD = re.compile(r"[A-Za-z][A-Za-z]{2,}(?:-[A-Za-z]{2,})*")
_PERIOD_CODE = re.compile(r"^(?:[QH][1-4]?)?FY?\d{2,4}$|^[QH]\d\w*$|^FY\w*$", re.I)
_MIN_MISSING = 2   # an item is dropped at this many unsupported words or names (lenient: one is forgiven)

_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_MONTH_RE = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s.,-]+(?:of\s+)?({_MONTH_RE})\b", re.I)
_MONTH_DAY = re.compile(rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?!\s*(?:cr|crore|lakh|%|bps))", re.I)
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b")
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# a whole number of 31 or less and the noun it counts; money, time and rate words are not counted things
_SMALL_NOUN = re.compile(r"(?<![\w.,/₹$-])(\d{1,2})\s+((?:[A-Za-z][A-Za-z-]+\s+){0,1}[A-Za-z][A-Za-z-]{2,})")
_NOT_COUNTED = re.compile(
    r"^(?:cr|crore|crores|lakh|lakhs|lac|million|mn|billion|bn|thousand|per|percent|bps|basis|times|x|pts|points|pp|"
    r"year|years|yr|yrs|month|months|week|weeks|day|days|hour|hours|quarter|quarters|half|halves|"
    r"fy\w*|q\d\w*|h\d\w*|of|to|in|on|at|and|or|from|by|with|the|a|an|as|for|mw|gw|kw|mt|tonnes?|kg|mwh|"
    r"jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)$", re.I)
_NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
                 10: "ten", 11: "eleven", 12: "twelve"}


def _stem(word: str) -> str:
    word = word.lower()
    for suffix in _STEM_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 5:
            return word[: -len(suffix)]
    return word


def _in(flat: str, word: str) -> bool:
    stem = _stem(word)
    tail = "" if len(stem) >= 5 else r"(?![a-z0-9])"   # a short name ("ACC") is a whole word, not the start of "accounts"
    return re.search(r"(?<![a-z0-9])" + re.escape(stem) + tail, flat) is not None


def _dates(text: str) -> set[tuple[int, int]]:
    """(day, month) of every date a text prints, in any of the usual forms."""
    found: set[tuple[int, int]] = set()
    low = text.lower()
    for m in _DAY_MONTH.finditer(low):
        found.add((int(m.group(1)), _MONTHS.index(m.group(2)[:3]) + 1))
    for m in _MONTH_DAY.finditer(low):
        found.add((int(m.group(2)), _MONTHS.index(m.group(1)[:3]) + 1))
    for m in _NUMERIC_DATE.finditer(low):
        found.add((int(m.group(1)), int(m.group(2))))
    for m in _ISO_DATE.finditer(low):
        found.add((int(m.group(3)), int(m.group(2))))
    return {(d, mo) for d, mo in found if 1 <= d <= 31 and 1 <= mo <= 12}


@lru_cache(maxsize=1)
def generic_stems() -> frozenset[str]:
    """Stems of the hand list plus config/generic_words.txt (words common across stored filings), minus KEEP_CHECKED."""
    stems = {_stem(w) for w in GENERIC_WORDS}
    try:
        stems |= {w.strip() for w in _GENERIC_FILE.read_text().splitlines() if w.strip()}
    except OSError:
        pass
    return frozenset(stems - {_stem(w) for w in KEEP_CHECKED})


class _Sources:
    """The filing, memory and scale block, flattened once; peer context is never in it."""

    def __init__(self, sources: tuple[str, ...]):
        joined = "\n".join(s for s in sources if s)
        self.raw = joined
        self.flat = f" {_flat(joined)} "
        self._dates: set[tuple[int, int]] | None = None

    @property
    def dates(self) -> set[tuple[int, int]]:
        if self._dates is None:
            self._dates = _dates(self.raw)
        return self._dates

    def has_count(self, number: int, noun: str) -> bool:
        stem = re.escape(_stem(noun))
        spelled = _NUMBER_WORDS.get(number)
        head = rf"(?:(?<![\w.,/-]){number}|{spelled})" if spelled else rf"(?<![\w.,/-]){number}"
        return re.search(rf"{head}\s+(?:[\w-]+\s+){{0,2}}{stem}", self.flat) is not None


def unsupported(text: str, src: _Sources) -> tuple[list[str], list[str]]:
    """(missing names and words, missing dates and counts) of a text against the sources."""
    if not text:
        return [], []
    plain = text.replace("**", "")
    _, names = unprinted_names(plain, src.raw)
    missing = {n.lower(): n for n in names}
    for low in [k for k, n in missing.items() if _PERIOD_CODE.match(n) or any(c.isdigit() for c in n) or _in(src.flat, n)]:
        del missing[low]   # a period code, or a capitalised plain word the sources print in another form ("Inventory")
    for m in _WORD.finditer(plain):
        for word in m.group(0).split("-"):
            low = word.lower()
            if len(word) < 6 or _stem(low) in generic_stems() or low in missing:
                continue
            if not _in(src.flat, word):
                missing[low] = word
    bad: list[str] = []
    for d, mo in sorted(_dates(plain)):
        if (d, mo) not in src.dates:
            bad.append(f"{d} {_MONTHS[mo - 1].title()}")
    for m in _SMALL_NOUN.finditer(plain):
        number, noun = int(m.group(1)), m.group(2).split()[-1]
        first = m.group(2).split()[0]
        if not 1 <= number <= 31 or _NOT_COUNTED.match(first) or _NOT_COUNTED.match(noun):
            continue
        if _DAY_MONTH.match(m.group(0)):
            continue   # a date, read above
        if not src.has_count(number, noun):
            bad.append(f"{number} {noun}")
    return sorted(missing.values()), bad


def _rejected(text: str, src: _Sources) -> list[str]:
    """Why an item fails, or []: two or more words or names missing, or any small count or date missing."""
    words, odd = unsupported(text, src)
    if odd or len(words) >= _MIN_MISSING:
        return words + odd
    return []


def support_check(out, sources: tuple[str, ...]) -> list[str]:
    """Drop what the sources do not support. Returns one note per drop, with the missing words, for the change log."""
    card = getattr(out, "card", None)
    if card is None:
        return []
    src = _Sources(sources)
    notes: list[str] = []

    def note(field: str, why: list[str]) -> str:
        return f"{field}: not supported by the filing or memory ({', '.join(why[:6])}), dropped"

    track = card.track_next
    for name in ("pending_approvals", "catalysts", "risks"):
        kept = []
        for item in getattr(track, name):
            why = _rejected(item, src)
            if why:
                notes.append(note(f"track_next.{name}", why))
            else:
                kept.append(item)
        setattr(track, name, kept)
    kept_m = []
    for m in track.milestones:
        why = _rejected(f"{m.what} {m.when or ''}", src)   # the ISO date field is the model's reading of `when`
        if why:
            notes.append(note("track_next.milestones", why))
        else:
            kept_m.append(m)
    track.milestones = kept_m
    if card.core_catalyst:
        why = _rejected(card.core_catalyst, src)
        if why:
            card.core_catalyst = None
            notes.append(note("core_catalyst", why))
    for change in card.notable_changes:
        why = _rejected(change.why, src) if change.why else []
        if why:
            change.why = ""   # the figures stay (checked elsewhere); the unsupported reason goes
            notes.append(note("notable_changes.why", why))
    kept_i = []
    for insight in card.why_it_matters:
        free = insight.basis == "SECTOR" or (insight.basis == "MEMORY" and not insight.memory_refs)
        why = _rejected(insight.text, src) if free else []
        if why:
            notes.append(note(f"why_it_matters[{insight.basis}]", why))
        else:
            kept_i.append(insight)
    if len(kept_i) != len(card.why_it_matters):
        card.why_it_matters = kept_i
    return notes


# --- label check -----------------------------------------------------------------------------------------------------

_CLAIMS = {
    "owners": re.compile(r"\bto (?:its |the )?(?:share|equity)holders\b|\bto (?:the )?owners\b|\bowners of\b|"
                         r"\bprofit attributable\b|\battributable to (?:owners|share|equity)", re.I),
    "net profit": re.compile(r"\bnet profit\b", re.I),
    "discontinued": re.compile(r"\bdiscontinued\b", re.I),
    "tci": re.compile(r"\btotal comprehensive income\b", re.I),
}
_ROW = {
    "owners": re.compile(r"owners|share ?holders|equity holders|attributable|parent|\bpat\b", re.I),
    "net profit": re.compile(r"net profit|profit (?:for|after|/)|\bpat\b|net income|profit\s*\(loss\)|profit and loss", re.I),
    "discontinued": re.compile(r"discontinu", re.I),
    "tci": re.compile(r"comprehensive", re.I),
}


_AFTER_STOP = re.compile(r"[;.]|,\s|\bwith\b|\bwhile\b|\band\b|\bbut\b|\bfrom\b")
_BEFORE_STOP = re.compile(r"[;.,(%]")


def _near_figures(claim: str, term: re.Match) -> list[tuple[float, int]]:
    """The money figure each side of a label in a claim: the one it names ("Net profit to shareholders Q2FY27: Rs 193 Cr",
    "Rs 3.76 Cr from discontinued operations"), within a short clause, never a percentage or a year."""
    found = []
    for v, d, pos, kind, raw in _tokens(claim):
        if kind in ("pct", "bps", "pp", "x") or v < 1 or (d == 0 and 1900 <= v <= 2100):
            continue
        if term.end() <= pos < term.end() + 45 and not _AFTER_STOP.search(claim[term.end():pos]):
            found.append((v, d))
        elif term.start() - 35 <= pos + len(raw) <= term.start() and not _BEFORE_STOP.search(claim[pos + len(raw):term.start()]):
            found.append((v, d))
    return found


class _Lines:
    """The filing's lines with the figures each prints, to find the line a figure sits on."""

    def __init__(self, text: str):
        self.lines = text.split("\n")
        self._vals: list[list[float]] | None = None

    def vals(self) -> list[list[float]]:
        if self._vals is None:
            self._vals = [[v for v, _, _, k, _ in _tokens(line)] if any(c.isdigit() for c in line) else []
                          for line in self.lines]
        return self._vals

    def rows_of(self, value: float, decimals: int) -> list[str]:
        """The line (with the one before it, where a table's label wraps) of each place the figure is printed."""
        tolerance = 0.5 * 10 ** (-decimals) + 1e-9
        found = []
        for i, vals in enumerate(self.vals()):
            if any(abs(v / s - value) <= tolerance for v in vals for s in CRORE_SCALES):
                wrapped = i and sum(c.isalpha() for c in self.lines[i]) < 3   # a table row whose label sits on the line above
                found.append((self.lines[i - 1] + " " if wrapped else "") + self.lines[i])
        return found


def _label_ok(kind: str, claim_figures: list[tuple[float, int]], quote: str, lines: _Lines) -> bool:
    row = _ROW[kind]
    if quote and row.search(quote):
        return True
    for value, decimals in claim_figures:
        if any(row.search(r) for r in lines.rows_of(value, decimals)):
            return True
    return False


def label_check(out, text: str) -> list[str]:
    """A fact, key number or insight that names a profit label on a figure needs that label in its quote or on the
    filing's line for the figure. A key number is dropped; a fact or insight is dropped (a sentence goes whole)."""
    card = getattr(out, "card", None)
    if card is None or not text:
        return []
    lines = _Lines(text)
    notes: list[str] = []

    def failing(claim: str, quote: str | None) -> str | None:
        terms = {k: m for k, rx in _CLAIMS.items() if (m := rx.search(claim))}
        if "owners" in terms and "net profit" in terms:
            del terms["net profit"]   # "net profit to shareholders" is the one claim: the owners' row
        for kind, term in terms.items():
            figures = _near_figures(claim, term)
            if figures and not _label_ok(kind, figures, quote or "", lines):
                return kind
        return None

    kept = []
    for fact in card.what_happened:
        bad = failing(fact.text, fact.quote)
        if bad:
            notes.append(f"what_happened: label '{bad}' not on the figure's quote or line, dropped")
        else:
            kept.append(fact)
    if kept and len(kept) != len(card.what_happened):   # a card keeps at least one fact (the model requires it)
        card.what_happened = kept
    kept_k = []
    for kn in card.key_numbers:
        bad = failing(f"{kn.label} {kn.value} {kn.change or ''}", kn.quote)
        if bad:
            notes.append(f"key_numbers: label '{bad}' not on the figure's quote or line, dropped")
        else:
            kept_k.append(kn)
    card.key_numbers = kept_k
    kept_i = []
    for insight in card.why_it_matters:
        bad = failing(insight.text, insight.quote)
        if bad:
            notes.append(f"why_it_matters: label '{bad}' not on the figure's quote or line, dropped")
        else:
            kept_i.append(insight)
    card.why_it_matters = kept_i
    return notes


def apply(out, sources: tuple[str, ...], text: str) -> list[str]:
    """Both checks, for pipeline.ground: the notes of every drop."""
    return support_check(out, sources) + label_check(out, text)


# --- the prompt variant ------------------------------------------------------------------------------------------------

STRICT_RULE = ("Never use knowledge outside FILING TEXT and COMPANY MEMORY. Every name (company, peer, regulator, scheme, "
               "product, material) and every date you write must appear in them; if the filing does not say, write nothing.")

# (old, new) edits to the rendered pass-2 prompts; every old line must be in both prompts (tests check it)
_EDITS_LONG = (
    ("- Use only facts in FILING TEXT and COMPANY MEMORY. Never invent numbers, dates, names or guidance.\n",
     "- Use only facts in FILING TEXT and COMPANY MEMORY. Never invent numbers, dates, names or guidance.\n"
     f"- {STRICT_RULE}\n"),
    ("and with what is normal for\n  this sector and event type, and list up to 5 changes",
     "and list up to 5 changes"),
)
_EDITS_SHORT = (
    ("- Use only FILING TEXT and COMPANY MEMORY. Never invent a number, date, name, stage or cause. If it is not in the\n  sources, leave it out.",
     "- Use only FILING TEXT and COMPANY MEMORY. Never invent a number, date, name, stage or cause. If it is not in the\n  sources, leave it out.\n"
     f"- {STRICT_RULE}"),
)
_SECTOR_OLD = "Sector KPIs to look for: "
_SECTOR_NEW = ("Sector KPIs: look for these in the filing only, and say nothing about a KPI the filing does not give: ")
_TRACK_OLD_LONG = "milestones: future dates or execution windows a source states (what, when as written,"
_TRACK_NEW_LONG = ("milestones: future dates or execution windows the filing's own words state (a milestone date must be "
                   "printed in the filing; what, when as written,")


def strict_prompt(system: str, short: bool) -> str:
    """The pass-2 system prompt with the sources-only rule (CARD_TEXT_SUPPORT on): the rule, the sector lens read as what to
    look for in the filing, track_next only from the filing's words, no "what is normal for this sector"."""
    # the short prompt carries the long prompt's field rules (notable_changes, track_next) for the filing's event type
    for old, new in (_EDITS_SHORT + _EDITS_LONG[1:] if short else _EDITS_LONG):
        system = system.replace(old, new, 1)
    system = system.replace(_SECTOR_OLD, _SECTOR_NEW, 1)
    if short:
        system = system.replace(
            "track_next: milestones, kpis_to_verify\n  (with metric, period, value, comparison when the target is a number), pending_approvals the filing states, at most\n  one catalyst and one or two risks tied to this filing; empty rather than guessed.",
            "track_next: only items the filing's own words state: milestones (a date must be printed in the filing), kpis_to_verify\n  (with metric, period, value, comparison when the target is a number), pending_approvals the filing states, at most\n  one catalyst and one or two risks tied to this filing; empty rather than guessed.", 1)
    system = system.replace(_TRACK_OLD_LONG, _TRACK_NEW_LONG, 1)
    if not short:
        system = system.replace("- track_next: forward-looking triggers an investor should monitor after this filing.",
                                "- track_next: forward-looking triggers an investor should monitor after this filing, only items the\n  filing's own words state.", 1)
    return system
