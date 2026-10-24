"""Code computes, the model describes (audit round 2, 2026-10-18).

Round 2 found the same share of wrong cards on companies the pipeline had never read (36%) as round 1 had on the
smoke-test ten (33%), most of them a change, margin or ratio the model worked out itself: a year-ago figure from
before a demerger (SKF India +27% against a base that no longer exists), standalone set against consolidated
(eMudhra, Magellanic), an EPS before a share split (Adani Power), arithmetic and direction slips ("margin improved
from 12.83% to 11.78%"). Checking each such figure after the fact had not moved the rate, so the rule is now
structural: a percentage, a basis-point move or a multiple on the card stands only if code produced it or the
filing prints it. Anything else is removed, not checked.

Code produces: the margins and changes in the XBRL files (results, annual report); a change between two tagged
figures of the same metric, only when its base figure is printed in this filing - which is how a restated,
re-based or other-basis comparative is told apart, since the filing prints its own like-for-like comparative and
not the old one; the shares in the scale block; ownership from the shareholding XBRL. The filing prints: any
percentage, basis-point figure or multiple in the document's own text (not the tables put in front of it).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .grounding import SourceIndex
from .periods import prior_quarter_period, prior_year_period

# A figure that is computed rather than read: a percentage, a basis-point or percentage-point move, a multiple
_FIGURE = re.compile(r"(?<![\w.])([+\-−]?)\s?(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
                     r"(%|per\s?cent\b|bps\b|basis points?\b|pp\b|percentage points?\b|x\b|times\b)", re.I)
# A table row's columns count too: "Gross NPA % 1.30 1.45 2.78" lost all but its last column to the old "(?!\s*\d)",
# and RBL's card had its NPA ratios stripped to "Gross NPA improved to (vs 1.45% ...)" (round 4)
_BARE = re.compile(r"(?<![\w.,])(\d{1,3}\.\d{2,})(?!\s*(?:%|per\s?cent)|\d|,\d)")
_UP = re.compile(r"\b(?:up|rose|rise|rising|grew|grow|growth|increase[sd]?|higher|gain(?:ed|s)?|jump(?:ed|s)?|"
                 r"improv\w*|expand\w*|surg\w*|climb\w*|widen\w*)\b", re.I)
_DOWN = re.compile(r"\b(?:down|fell|fall|falling|declin\w*|lower|drop\w*|decrease[sd]?|contract\w*|shr[iau]nk\w*|"
                   r"slip\w*|slump\w*|narrow\w*|eas(?:ed|ing))\b", re.I)


def _kind(word: str) -> str:
    w = word.lower().replace(" ", "")
    if w in ("bps",) or w.startswith("basispoint"):
        return "bps"
    if w == "pp" or w.startswith("percentagepoint"):
        return "pp"
    if w in ("x", "times"):
        return "x"
    return "pct"


@dataclass
class Pool:
    """Figures a card may state: (value, sign) per kind; sign 0 when the source does not say."""
    pct: list[tuple[float, int]] = field(default_factory=list)
    bps: list[tuple[float, int]] = field(default_factory=list)
    x: list[float] = field(default_factory=list)
    # figures the filing prints with two or more decimals and no % sign: a voting result's 97.0846, a stake's 17.12
    # under a "% of shares" header (round-2 re-run: removed as unproduced, leaving "** ** of votes")
    bare: list[float] = field(default_factory=list)
    # the scale block's shares, by base: [(22.6, "market cap"), (150.6, "net worth")], and the shares the filing
    # itself prints with their base ("x% of net worth" in a Reg 30 note)
    shares: list[tuple[float, str]] = field(default_factory=list)

    def add_shares(self, text: str) -> None:
        for m in re.finditer(r"(\d+(?:\.\d+)?)%" + _BASE.pattern, text or "", re.I):
            self.shares.append((float(m.group(1)), _base(m.group(2))))

    def share_of(self, base: str, value: float, decimals: int) -> bool:
        tolerance, step = 0.5 * 10 ** -decimals + 1e-9, 10 ** -decimals
        return any(b == base and (abs(v - value) <= tolerance or 0 <= v - value < step) for v, b in self.shares)

    def add_bare(self, text: str) -> None:
        self.bare += [float(m.group(1)) for m in _BARE.finditer(text or "")]

    def add_printed(self, text: str) -> None:
        for m in _FIGURE.finditer(text or ""):
            value = float(m.group(2).replace(",", ""))
            kind = _kind(m.group(3))
            if kind == "x":
                self.x.append(value)
            elif kind == "pp":
                self.pct.append((value, 0))
                self.bps.append((value * 100, 0))
            else:
                getattr(self, kind).append((value, 0))

    def has(self, kind: str, value: float, decimals: int, sign: int) -> bool:
        tolerance, step = 0.5 * 10 ** -decimals + 1e-9, 10 ** -decimals
        if kind == "x":
            return any(abs(v - value) <= tolerance or 0 <= v - value < step for v in self.x)
        if kind == "pp":
            kind, value, tolerance, step = "bps", value * 100, tolerance * 100, step * 100
        for v, s in getattr(self, kind):
            if sign and s and sign != s:
                continue  # "fell 7%" is not a rise of 7%
            a = abs(v)
            if abs(a - value) <= tolerance or 0 <= a - value < step:
                return True
        # a share the filing prints without its % sign, matched only to two decimals: an invented whole or
        # one-decimal percentage would land on an unrelated table figure too often
        return kind == "pct" and decimals >= 2 and value <= 100 \
            and any(abs(b - value) <= tolerance or 0 <= b - value < step for b in self.bare)


def _base_printed(index: SourceIndex | None, base: float, metric: str = "") -> bool:
    if not index or base <= 0:
        return False
    if index.stated_crore(round(base, 2), 2, tolerance=max(0.006, base * 0.0005)):
        return True
    # EBITDA is code's own sum of the file's lines, and a release prints its own by its own definition: Kajaria's
    # Q2FY26 EBITDA is ₹213.45 Cr from the file and ₹212.90 Cr in the release, and the card lost a right "+34.3% YoY"
    # (owner, 24 Oct 2026). Within half a percent the change moves by less than its rounding
    return metric in _DERIVED and index.stated_crore(round(base, 2), 2, tolerance=base * 0.005)


_DERIVED = {"ebitda"}


def build_pool(filed_text: str, tagged=None, annual_table: str = "", history: list[dict] | None = None,
               scale: str = "", ownership: dict | None = None, facts: list | None = None) -> Pool:
    pool = Pool()
    for fact in facts or []:   # computed in code from the filing's statements, with their direction (facts.py)
        if fact.kind in ("pct", "bps"):
            getattr(pool, fact.kind).append((fact.value, fact.sign))
        if fact.base:
            pool.shares.append((fact.value, fact.base))
    pool.add_printed(filed_text)
    pool.add_bare(filed_text)
    printed = Pool()   # the filing's own text alone: where a like-for-like base margin must be printed
    printed.add_printed(filed_text)
    pool.add_printed(annual_table)   # the annual report's own tagged figures
    pool.add_printed(scale)          # shares of revenue, net worth and market cap computed in code
    pool.add_shares(scale)
    pool.add_shares(filed_text)
    pool.add_printed(json.dumps(ownership or {}))
    index = SourceIndex(filed_text) if filed_text else None
    tagged_metrics = list(getattr(tagged, "metrics", None) or [])
    xbrl_history = [m for m in history or [] if str(m.get("value_news_id") or m.get("source_news_id") or "").startswith("xbrl:")]
    by_key: dict[tuple[str, str], float] = {}
    for m in xbrl_history:
        if m.get("value") is not None:
            by_key[(m["metric"], m["period"])] = m["value"]
    for m in tagged_metrics:
        if m.value is not None:
            by_key[(m.metric, m.period)] = m.value
    for m in tagged_metrics:
        if m.value is None:
            continue
        if m.unit == "PCT":
            pool.pct.append((m.value, 0))   # a margin the file states or code derived from its figures
            for prior in (prior_year_period(m.period), prior_quarter_period(m.period)):
                base = by_key.get((m.metric, prior or ""))
                # only a base margin the filing prints itself: `base` always comes from by_key, so testing it against
                # by_key let a pre-demerger or other-basis margin through
                if base is not None and printed.has("pct", base, 2, 0):
                    diff = (m.value - base) * 100
                    pool.bps.append((abs(diff), 1 if diff > 0 else -1))
            continue
        for prior, stated in ((prior_year_period(m.period), m.yoy_pct), (prior_quarter_period(m.period), m.qoq_pct)):
            base = by_key.get((m.metric, prior or ""))
            if base is None and stated is not None and stated != -100:
                base = m.value / (1 + stated / 100)
            # only a like-for-like base: the filing prints its own comparative, not a pre-restatement or other-basis one
            if base is None or base <= 0 or m.value < 0 or not _base_printed(index, base, m.metric):
                continue
            change = (m.value - base) / base * 100
            pool.pct.append((abs(change), 1 if change > 0 else -1))
    return pool


def _figures(text: str):
    for m in _FIGURE.finditer(text or ""):
        raw = m.group(2).replace(",", "")
        value = float(raw)
        kind = _kind(m.group(3))
        before = text[max(0, m.start() - 30):m.start()]
        sign = -1 if m.group(1) in ("-", "−") else 1 if m.group(1) == "+" else 0
        if not sign:
            ups, downs = list(_UP.finditer(before)), list(_DOWN.finditer(before))
            last_up = ups[-1].end() if ups else -1
            last_down = downs[-1].end() if downs else -1
            sign = 0 if last_up == last_down else (1 if last_up > last_down else -1)
        yield m, kind, value, len(raw.partition(".")[2]), sign


_BASE = re.compile(r"\s*(?:of|to)\s+(?:the\s+)?(?:company'?s\s+|its\s+)?(market cap(?:italisation)?|net worth|"
                   r"(?:\w+\s+){0,2}revenue)", re.I)


def _base(phrase: str) -> str:
    phrase = phrase.lower()
    return "market cap" if phrase.startswith("market cap") else "net worth" if phrase == "net worth" else "revenue"


def unproduced(text: str, pool: Pool) -> list[str]:
    """The computed figures in `text` that code did not produce and the filing does not print. A share of market
    cap, net worth or revenue must be the one code worked out for that base: Adani Power's "₹1,00,000 Cr limit is
    22.6% of net worth" passed on the 22.6% code had worked out for market cap (round-2 re-run)."""
    out = []
    for m, kind, value, decimals, sign in _figures(text):
        if not pool.has(kind, value, decimals, sign):
            out.append(m.group(0).strip())
            continue
        said = _BASE.match(text, m.end())
        if kind == "pct" and said and pool.shares and not pool.share_of(_base(said.group(1)), value, decimals):
            out.append(m.group(0).strip())
    return out


# The phrase a removed figure sits in: "up 10% YoY", "(+12.3% QoQ)", "a 15% rise"
_PHRASE = (r"\s*\(?\s*(?:(?:up|down|rose|fell|grew|declined|jumped|slipped|gained|dropped|increased|decreased|surged|"
           r"improved|contracted|expanded|by|of|a|an)\s+)*(?:by\s+)?{fig}(?:\s*(?:YoY|QoQ|y-?o-?y|q-?o-?q|year-on-year|"
           r"quarter-on-quarter|sequentially|rise|fall|increase|decrease|growth|decline|jump|drop))*\s*\)?")


def _strip(text: str, figures: list[str]) -> str:
    for fig in figures:
        text = re.sub(_PHRASE.format(fig=re.escape(fig)), " ", text, count=1, flags=re.I)
        # "(+12.3% YoY, -7.0% QoQ)" less its first change took the "(" with it and left "₹11.36 Cr, -7.0% QoQ)"
        # (Shivam Autotech Q3FY25, live review 2, 2026-10-20): the bracket of the change that stays goes back
        if text.count(")") > text.count("("):
            text = re.sub(r"\s+,\s*([^()]*\))", r" (\1", text, count=1)
        elif text.count("(") > text.count(")"):   # and its mirror: "(+3.7% YoY, +3.2% QoQ)" less the second
            open_at = text.rfind("(")
            tail = re.fullmatch(r"(\([^()]*?)[\s,]*([.;]?)\s*", text[open_at:])
            if tail:
                text = f"{text[:open_at]}{tail.group(1)}){tail.group(2)}"
    text = re.sub(r"\*\*\s*\*\*", " ", text)   # the bold a removed figure sat in
    text = re.sub(r"\s+([,;.)])", r"\1", re.sub(r"\(\s*\)", "", text))
    text = re.sub(r"\b(revenue|sales|profit|PAT|EBITDA|PBT|income|margin|EPS)\s+to\s+(₹|Rs|INR|\d)", r"\1 at \2", text)
    text = re.sub(r"[,;]\s*[,;]", ",", text)
    return re.sub(r"\s{2,}", " ", text).strip(" ,;")


# A word left without its object once a figure is removed: "increase stake to via open market", "Only of votes
# cast", "approved ₹150 Cr NCD issuance, of net worth", "holds but can vote" (round-2 re-run)
# A range left without its upper end ("7-9 bps" less "9 bps": "a 7- margin boost", "a 7 to further expansion", PNB call,
# 23 Oct 2026) and a share left without its figure ("represents under 1% of market cap" less "1%", Atul) are broken too.
_DANGLING = re.compile(r"\b(?:to|of|at|about|over|only|by|holds?|than|nearly|around|approximately|under|below|above|"
                       r"almost|just|roughly)\s+"
                       r"(?=(?:via|of|in|and|from|against|votes?|with|but|while|the\s+(?:highest|lowest))\b)"
                       r"|(?:^|[,;]\s*)of\b[^,;]*|\b(?:to|of|at|about|over|by|than)\s*(?=[,;.:)]|$)"
                       r"|\b(?:represents?|equals?|accounts?\s+for)\s+of\b[^,;.]*"
                       r"|\b(?:is|was)\s+of\s+(?:FY\d{2}\s+)?(?:revenue|sales|profit|PAT|EBITDA|net\s+worth|market\s+cap)\b[^,;.]*"
                       r"|(?<![\d.,])\d+(?:\.\d+)?\*{0,2}\s*[-–]\*{0,2}\s+(?=(?-i:[a-z]))"
                       r"|(?<![\d.,])\d+(?:\.\d+)?\*{0,2}\s+to\s+(?=further\b)", re.I)


def broken(text: str) -> bool:
    return bool(_DANGLING.search(text or ""))


def _repair(text: str) -> str:
    """A headline keeps its subject: the dangling word goes, and so does a clause left as "of net worth"."""
    for _ in range(3):   # "represents under of market cap": the dangling "under" first, then "represents of ..."
        if not broken(text):
            break
        text = re.sub(r"\s{2,}", " ", _DANGLING.sub(" ", text)).strip(" ,;")
    return text


def _clauses(text: str, pool: Pool) -> tuple[str, list[str]]:
    """Drop the clauses of a headline-like text that carry an unproduced figure; strip it from the first clause."""
    removed = unproduced(text, pool)
    if not removed:
        return text, []
    parts = re.split(r"(;\s+|,\s+(?=[A-Z₹a-z]))", text)
    kept = []
    for i in range(0, len(parts), 2):
        part = parts[i]
        bad = unproduced(part, pool)
        if not bad:
            kept.append(part)
        elif not kept:
            stripped = _strip(part, bad)
            kept.append(_repair(stripped) if broken(stripped) else stripped)
    return "; ".join(p for p in kept if p.strip()), removed


# "slipped to 15.0% from 13.0%", "rose from ₹50 Cr to ₹42 Cr": a verb against the two levels it names
_LEVEL = r"[₹]?\s?(\d[\d,]*(?:\.\d+)?)\s*(%|Cr\b|crore\b)"
_PAIR = re.compile(r"(?P<verb>" + _UP.pattern + "|" + _DOWN.pattern + r")(?P<mid>[^.;]{0,40}?)\b(?:to\s+" + _LEVEL + r"[^.;]{0,25}?\bfrom\s+" + _LEVEL
                   + r"|from\s+" + _LEVEL + r"[^.;]{0,25}?\bto\s+" + _LEVEL + r")", re.I)


def fix_direction(text: str | None) -> tuple[str | None, list[str]]:
    """The verb of a move whose two levels say the opposite becomes "moved": the figures are right (code or the
    filing produced both), the word is not (SKF India's "margin slipped to 15.0% from 13.0%", round-2 re-run)."""
    if not text:
        return text, []
    notes = []

    def one(m: re.Match) -> str:
        verb = m.group("verb")
        up, down = _UP.fullmatch(verb), _DOWN.fullmatch(verb)
        if not (up or down):
            return m.group(0)
        g = m.groups()
        if g[2] is not None:  # "to X from Y"
            new, unit_new, old, unit_old = float(g[2].replace(",", "")), g[3], float(g[4].replace(",", "")), g[5]
        else:                 # "from Y to X"
            old, unit_old, new, unit_new = float(g[6].replace(",", "")), g[7], float(g[8].replace(",", "")), g[9]
        if unit_new.lower()[:2] != unit_old.lower()[:2] or new == old or bool(up) == (new > old):
            return m.group(0)
        notes.append(f"'{verb}' for a move from {old:g} to {new:g}")
        return "moved" + m.group(0)[len(verb):]

    return _PAIR.sub(one, text), notes


def enforce(out, pool: Pool) -> list[str]:
    """Remove from the card every computed figure code did not produce. Returns what was removed."""
    card = out.card
    if card is None:
        return []
    notes: list[str] = []
    for name in ("headline", "takeaway", "core_catalyst"):
        setattr(card, name, (lambda r: (notes.extend(r[1]), r[0])[1])(fix_direction(getattr(card, name, None))))
    for item in [*card.what_happened, *card.why_it_matters]:
        if getattr(item, "text", None):
            item.text, moved = fix_direction(item.text)
            notes += moved
    out.timeline_entry, moved = fix_direction(out.timeline_entry)
    notes += moved
    for name in ("headline", "takeaway", "core_catalyst"):
        value = getattr(card, name, None)
        if isinstance(value, str) and value:
            new, removed = _clauses(value, pool)
            if removed:
                setattr(card, name, new or value)
                notes.append(f"{name}: removed {', '.join(removed)}")
    if out.timeline_entry:
        new, removed = _clauses(out.timeline_entry, pool)
        if removed:
            out.timeline_entry = new or out.timeline_entry
            notes.append(f"timeline: removed {', '.join(removed)}")
    for key in list(card.key_numbers):
        if unproduced(key.value or "", pool):
            card.key_numbers.remove(key)
            notes.append(f"key number {key.label!r} dropped: {key.value}")
        elif key.change and unproduced(key.change, pool):
            notes.append(f"key number {key.label!r}: change {key.change} removed")
            key.change = None
    for change in card.notable_changes or []:
        if change.change and unproduced(change.change, pool):
            notes.append(f"notable change {change.metric!r}: change {change.change} removed")
            change.change = None
    kept_insights = []
    for insight in card.why_it_matters:
        bad = unproduced(insight.text or "", pool)
        if bad:
            notes.append(f"point dropped ({', '.join(bad)}): {(insight.text or '')[:60]}")
        else:
            kept_insights.append(insight)
    card.why_it_matters = kept_insights
    facts = []
    for fact in card.what_happened:
        text = fact.text if hasattr(fact, "text") else str(fact)
        bad = unproduced(text, pool)
        if not bad:
            facts.append(fact)
            continue
        stripped = _strip(text, bad)
        if len(stripped) >= 25 and not unproduced(stripped, pool) and not broken(stripped):
            if hasattr(fact, "text"):
                fact.text = stripped
            else:
                fact = stripped
            facts.append(fact)
            notes.append(f"fact: removed {', '.join(bad)}")
        else:
            notes.append(f"fact dropped ({', '.join(bad)}): {text[:60]}")
    if facts:
        card.what_happened = facts
    return notes
