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
        return False


def _base_printed(index: SourceIndex | None, base: float) -> bool:
    return bool(index) and base > 0 and index.stated_crore(round(base, 2), 2, tolerance=max(0.006, base * 0.0005))


def build_pool(filed_text: str, tagged=None, annual_table: str = "", history: list[dict] | None = None,
               scale: str = "", ownership: dict | None = None) -> Pool:
    pool = Pool()
    pool.add_printed(filed_text)
    printed = Pool()   # the filing's own text alone: where a like-for-like base margin must be printed
    printed.add_printed(filed_text)
    pool.add_printed(annual_table)   # the annual report's own tagged figures
    pool.add_printed(scale)          # shares of revenue, net worth and market cap computed in code
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
            if base is None or base <= 0 or m.value < 0 or not _base_printed(index, base):
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


def unproduced(text: str, pool: Pool) -> list[str]:
    """The computed figures in `text` that code did not produce and the filing does not print."""
    return [m.group(0).strip() for m, kind, value, decimals, sign in _figures(text)
            if not pool.has(kind, value, decimals, sign)]


# The phrase a removed figure sits in: "up 10% YoY", "(+12.3% QoQ)", "a 15% rise"
_PHRASE = (r"\s*\(?\s*(?:(?:up|down|rose|fell|grew|declined|jumped|slipped|gained|dropped|increased|decreased|surged|"
           r"improved|contracted|expanded|by|of|a|an)\s+)*(?:by\s+)?{fig}(?:\s*(?:YoY|QoQ|y-?o-?y|q-?o-?q|year-on-year|"
           r"quarter-on-quarter|sequentially|rise|fall|increase|decrease|growth|decline|jump|drop))*\s*\)?")


def _strip(text: str, figures: list[str]) -> str:
    for fig in figures:
        text = re.sub(_PHRASE.format(fig=re.escape(fig)), " ", text, count=1, flags=re.I)
    text = re.sub(r"\s+([,;.)])", r"\1", re.sub(r"\(\s*\)", "", text))
    text = re.sub(r"\b(revenue|sales|profit|PAT|EBITDA|PBT|income|margin|EPS)\s+to\s+(₹|Rs|INR|\d)", r"\1 at \2", text)
    text = re.sub(r"[,;]\s*[,;]", ",", text)
    return re.sub(r"\s{2,}", " ", text).strip(" ,;")


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
            kept.append(_strip(part, bad))
    return "; ".join(p for p in kept if p.strip()), removed


def enforce(out, pool: Pool) -> list[str]:
    """Remove from the card every computed figure code did not produce. Returns what was removed."""
    card = out.card
    if card is None:
        return []
    notes: list[str] = []
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
        if len(stripped) >= 25 and not unproduced(stripped, pool):
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
