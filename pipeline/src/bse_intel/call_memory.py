"""Call memory v2 (TODO 83, F180, docs/design/call-memory.md): a separate, memory-only AI reading of every earnings-call
transcript and investor deck, whose typed points each carry a page and an exact quote and are checked by code before they
are kept in the dossier's `call_memory`. Behind MEMORY_CALL_V2 (settings.memory_call_v2), default off.

Why it exists (memory recall audit round 1, 26 Oct 2026): one AI reply wrote the card and memory together and memory kept 39%
of what ten call documents said; opening remarks beat the Q&A (Sobha's "much higher than 15% for the whole of FY27" was
clarified in the Q&A as the second half); a call's own definition sat under a statutory name; units slipped (APL Apollo's
"10 lakh tonnes"). Here the model only reads and lists; every rule below is code.

  read(...)           one AI call, free providers only
  check_points(...)   spec section 3: quote, figures, unit, period, page, Q&A supersedes, one fact once, own definitions
  remember(...)       the filing's points into dossier["call_memory"], a re-run replacing them
  prior_points(...)   the company's points from its latest earlier call, for "what changed"
"""
from __future__ import annotations

import logging
import re
from contextlib import nullcontext

from . import gate
from .call_summary import _figures, quarter_of
from .dossier import _hash, _norm, label
from .models import CallMemoryOutput, CallPoint
from .periods import canonical_period
from .timeutil import now_iso

log = logging.getLogger(__name__)

CALL_MEMORY_KEPT = 600   # points a company keeps, newest call first (about eight quarters of 60-75)
PRIOR_POINTS = 40        # the last call's points the model sees, to say what changed
CONTEXT_CHARS = 600      # around a quote, on its page, where its period may be named

_PAGE_MARK = re.compile(r"^(?:-{3}|={5})\s*page\s+(\d+)\s+of\s+\d+[^\n]*$", re.I | re.M)


# ---------------------------------------------------------------- the text by page
def split_pages(text: str) -> list[tuple[int | None, str]]:
    """(page number, page text) for each page marker of the text the model read (extract.select_text's `--- Page 3 of 40 ---`
    or memory_recall_export's `===== PAGE 3 of 40 [text] =====`); a text with no markers is one page of unknown number."""
    marks = list(_PAGE_MARK.finditer(text or ""))
    if not marks:
        return [(None, text or "")]
    return [(int(m[1]), (text[m.end():marks[i + 1].start()] if i + 1 < len(marks) else text[m.end():]).strip())
            for i, m in enumerate(marks)]


# ---------------------------------------------------------------- the reading
def read(gateway, prompts, filing, kind: str, industry: str | None, text: str, blocks: str = "", prior: list[dict] | None = None,
         paid: frozenset[str] | set[str] = frozenset()) -> CallMemoryOutput:
    """One AI call over the document's whole selected text with its page markers. The long-context route, the bulk share, and
    never a paid provider (the daily path costs $0, CLAUDE.md D24). A reply that is not JSON raises; the caller logs it and
    the card stands (the points wait for a re-run of `call-memory --ids`). The model and prompt size ride on the result."""
    system, user = prompts.call_memory(filing, kind, industry, text, prior)
    route = "pass2_long" if gateway.has_route("pass2_long") else "pass2_bulk"
    scope = getattr(gateway, "card_scope", None)
    # not the card's clock: the card is written and its cap spent before this reading
    with (scope(capped=False) if scope else nullcontext()):
        result = gateway.complete_json(route, system, user, CallMemoryOutput, bulk=True,
                                       allow=lambda target: target.provider not in paid)
    out: CallMemoryOutput = result.value
    out.served_by, out.prompt_chars = getattr(result, "model_label", None), len(system) + len(user)
    return out


def paid_providers(settings) -> frozenset[str]:
    """The providers providers.toml marks `paid = true` (DeepSeek): left out of this step, as of the daily annual catch-up."""
    return frozenset(name for name, conf in settings.load_toml("providers.toml").get("providers", {}).items() if conf.get("paid"))


# ---------------------------------------------------------------- the checks
# a scale word right after a figure: "10 lakh tonnes", "Rs 1,200 crore", "15 per cent", "150 bps"
_SCALE_AFTER = re.compile(
    r"^\s*(?:(?:-|–|to)\s*[\d.,]+\s*)?(?:"
    r"(?P<lakh>lakhs?\b|lacs?\b)|(?P<crore>crores?\b|crs?\b)|(?P<million>millions?\b|mn\b|mln\b)|(?P<billion>billions?\b|bn\b|bln\b)|"
    r"(?P<thousand>thousands?\b)|(?P<bps>bps\b|basis points?\b|bp\b)|(?P<percent>%|per ?cent(?:age)?(?: points?)?\b|pct\b|ppts?\b|pps?\b))", re.I)
_UNIT_KINDS = (("lakh", r"LAKHS?|LACS?"), ("crore", r"CRORES?|CRS?"), ("million", r"MILLIONS?|MNS?|MLN"),
               ("billion", r"BILLIONS?|BNS?|BLN"), ("thousand", r"THOUSANDS?"), ("bps", r"BPS|BP"),
               ("percent", r"PERCENT|PERCENTAGE|PCT|PC|PPT|PP|POINTS?"))
_MAGNITUDE = {"lakh": 1e5, "crore": 1e7, "million": 1e6, "billion": 1e9, "thousand": 1e3}
_ANYWHERE = {"lakh": r"\blakhs?\b|\blacs?\b", "crore": r"\bcrores?\b|\bcrs?\b", "million": r"\bmillions?\b|\bmn\b|\bmln\b",
             "billion": r"\bbillions?\b|\bbn\b|\bbln\b", "thousand": r"\bthousands?\b", "bps": r"\bbps\b|\bbasis points?\b|\bbp\b",
             "percent": r"%|\bper ?cent(?:age)?\b|\bpct\b|\bppts?\b|\bpps?\b"}


def _unit_tokens(unit: str | None) -> list[str]:
    # "%" is a unit too: the model writes it as often as PERCENT
    return [t for t in re.split(r"[^A-Z]+", (unit or "").upper().replace("%", " PERCENT ")) if t]


def _unit_kinds(unit: str | None) -> set[str]:
    """The scale words a unit names: LAKH_TONNES {lakh}, INR_CR {crore}, USD_MN {million}, PERCENT {percent}, TONNES {}."""
    return {kind for token in _unit_tokens(unit) for kind, rx in _UNIT_KINDS if re.fullmatch(rx, token)}


def _numbers(text: str) -> list[float]:
    out = []
    for m in gate._CLAIM_NUMBER.finditer(gate._flat(text or "")):
        try:
            out.append(float(m.group(0).replace(",", "").rstrip(".")))
        except ValueError:
            continue
    return out


def _has(value: float, numbers: list[float]) -> bool:
    # the quote's numbers carry no sign: an outflow is "(342.12)", "minus 342" or "-342" (review of F180)
    return any(abs(abs(value) - abs(n)) < 1e-9 for n in numbers)


def figure_issue(point: CallPoint, quote: str) -> str | None:
    """Every figure of the statement, the value and the high end is in the quote (spec 3.2). The statement's period labels
    and dates are not figures (call_summary._figures); the quote's numbers are read whole, so "2000 crore" is not a year."""
    stated = _numbers(quote)
    for value, _, _ in _figures(point.statement or ""):
        if not _has(value, stated):
            return f"figure {value:g} of the statement is not in the quote"
    for name in ("value", "value_high"):
        value = getattr(point, name)
        if value is not None and not _has(value, stated):
            return f"{name} {value:g} is not in the quote"
    return None


def unit_issue(point: CallPoint, quote: str) -> str | None:
    """The unit agrees with the quote's own scale word (spec 3.3): "10 lakh tonnes" with unit TONNES loses a factor of
    100,000, and a crore figure typed as lakh is 100 times off. Also fills `value_base` / `base_unit` (the figure in the base
    unit, so a later comparison is in one unit) or finds the model's own value_base wrong."""
    if point.value is None and point.value_high is None:
        point.value_base, point.base_unit = None, None
        return None
    flat = gate._flat(quote)
    figures = [v for v in (point.value, point.value_high) if v is not None]
    stated: set[str] = set()
    for m in gate._CLAIM_NUMBER.finditer(flat):
        try:
            number = float(m.group(0).replace(",", "").rstrip("."))
        except ValueError:
            continue
        if _has(number, figures) and (word := _SCALE_AFTER.match(flat[m.end():m.end() + 40])):
            stated.add(word.lastgroup)
    named = _unit_kinds(point.unit)
    if stated:
        if not named or not named <= stated:
            return f"the quote says {'/'.join(sorted(stated))}, the unit {point.unit or 'none'} says {'/'.join(sorted(named)) or 'no scale'}"
    elif any(not re.search(_ANYWHERE[kind], flat) for kind in named):
        return f"the unit {point.unit} names a scale the quote does not carry"
    magnitude = [k for k in named if k in _MAGNITUDE]
    if not magnitude:
        point.value_base, point.base_unit = None, None
        return None
    base_unit = "_".join(t for t in _unit_tokens(point.unit) if not any(re.fullmatch(rx, t) for _, rx in _UNIT_KINDS)) or None
    if point.value is not None:
        expected = point.value * _MAGNITUDE[magnitude[0]]
        if point.value_base is not None and abs(point.value_base - expected) > 1e-6 * abs(expected):
            return f"value_base {point.value_base:g} is not {point.value:g} x {_MAGNITUDE[magnitude[0]]:g}"
        point.value_base, point.base_unit = expected, base_unit
    return None


def _fy_forms(year: int) -> str:
    """The ways a fiscal year ending March `year` (2-digit) is written: FY27, FY 2027, FY2026-27, 2026-27, fiscal 27."""
    full = 2000 + year
    return (rf"(?:fy\s*'?\s*(?:20)?{year:02d}\b|fy\s*{full - 1}\s*[-–/]\s*(?:20)?{year:02d}\b|{full - 1}\s*[-–/]\s*(?:20)?{year:02d}\b|"
            rf"fiscal(?: year)?\s*(?:20)?{year:02d}\b)")


def period_named(period: str, haystack: str) -> bool:
    """The period is named in the text (spec 3.4): "H2FY27" as H2FY27, H2 FY27 or "second half" with FY27 near; "FY27" as
    FY27, FY 2027 or 2026-27; any other period (by March 2028, medium term) when every word of it is there."""
    flat = gate._flat(haystack)
    canon = canonical_period(period)
    if m := re.fullmatch(r"(Q[1-4]|H[12]|9M)?FY(\d{2})", canon):
        year, part = int(m[2]), m[1]
        fy = _fy_forms(year)
        if part is None:
            return bool(re.search(fy, flat))
        if re.search(rf"{part.lower()}\s*[-–]?\s*{fy}", flat):
            return True
        words = {"Q1": r"first quarter|1st quarter", "Q2": r"second quarter|2nd quarter", "Q3": r"third quarter|3rd quarter",
                 "Q4": r"fourth quarter|4th quarter|last quarter", "H1": r"first half|1st half|h1", "H2": r"second half|2nd half|h2",
                 "9M": r"nine months|9 months"}[part]
        return bool(re.search(words, flat) and re.search(fy, flat))
    stop = {"by", "in", "the", "of", "end", "till", "until", "h", "q", "a", "an", "to", "for"}
    for token in re.findall(r"[a-z]+|\d+", period.lower()):
        if token in stop:
            continue
        if re.fullmatch(r"20\d{2}", token):
            ok = re.search(rf"\b{token}\b|\b{token[2:]}\b|'{token[2:]}\b", flat)
        elif len(token) >= 3 and token.isalpha():
            ok = re.search(rf"\b{re.escape(token[:3])}[a-z]*\b", flat) if token[:3] in _MONTHS else re.search(rf"\b{re.escape(token)}", flat)
        else:
            ok = re.search(rf"\b{re.escape(token)}\b", flat)
        if not ok:
            return False
    return True


_MONTHS = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"}


def _same_span(a: str | None, b: str | None) -> bool:
    """Two periods one answer can clarify: the same one, or one inside the other (Sobha's "whole of FY27" and the answer's
    H2FY27). FY27 and FY28 guidance on one topic are two points, never one clarifying the other (review of F180); a point
    with no period is clarified by none."""
    if not a or not b:
        return False
    if a == b:
        return True
    year = lambda p: (m[1] if (m := re.fullmatch(r"(?:Q[1-4]|H[12]|9M)?FY(\d{2})", p)) else None)
    return year(a) is not None and year(a) == year(b) and (re.fullmatch(r"FY\d{2}", a) or re.fullmatch(r"FY\d{2}", b)) is not None


def _topic_key(p: CallPoint) -> str:
    return _norm(p.topic or p.metric or (p.statement or "")[:60])


def point_id(scope: str, p: CallPoint) -> str:
    """`cm_` + a hash of the company's filing, the point's type, topic, period and figure: the same fact of a re-run keeps its id."""
    return "cm_" + _hash(scope, p.type or "", _topic_key(p), p.period or "-", f"{p.value}", f"{p.value_high}", p.section or "")


def check_points(points: list[CallPoint], text: str, blocks: str = "", pages: list[tuple[int | None, str]] | None = None,
                 scope: str = "") -> tuple[list[CallPoint], list[dict]]:
    """Each point checked by code (spec section 3); returns (kept, dropped), a dropped one with its reason. `scope` (the
    company and filing) makes the ids; `pages` defaults to the text's own page markers."""
    pages = pages if pages is not None else split_pages(text)
    kept: list[CallPoint] = []
    dropped: list[dict] = []

    def drop(p: CallPoint, reason: str, detail: str = "") -> None:
        dropped.append({"reason": reason, "detail": detail, "point": p.model_dump(exclude_none=True)})

    for original in points:
        p = original.model_copy(deep=True)
        if p.type is None:
            drop(p, "type", "not one of the point types")
            continue
        if not (p.statement or "").strip():
            drop(p, "statement", "no statement")
            continue
        quote = (p.quote or "").strip()
        if not quote or not gate.quote_found(quote, text, blocks):
            drop(p, "quote", "the quote is not in the document" if quote else "no quote")
            continue
        if (issue := figure_issue(p, quote)):
            drop(p, "figure", issue)
            continue
        if (issue := unit_issue(p, quote)):
            drop(p, "unit", issue)
            continue
        # the page the quote is on, whatever the model named (spec 3.5); the page's text also gives the period its context
        # (a quote on several pages, as the same sentence on a slide and in the talk, stays on the page the model named)
        homes = [(n, t) for n, t in pages if gate.quote_found(quote, t)]
        number, page_text = next((h for h in homes if h[0] == p.page), homes[0] if homes else (None, ""))
        if number is not None:
            p.page = number
        if p.page is None and len(pages) == 1:
            p.page = pages[0][0]
        if p.period:
            context = quote
            if page_text:
                flat_page, flat_quote = gate._flat(page_text), gate._flat(quote)
                at = flat_page.find(flat_quote.split("...")[0].strip()[:80])
                if at >= 0:
                    context = flat_page[max(0, at - CONTEXT_CHARS):at + len(flat_quote) + CONTEXT_CHARS]
            if not period_named(p.period, f"{quote} {context}"):
                p.period, p.period_stated = None, False   # never guessed, and never a checkable target
            elif re.fullmatch(r"(?:Q[1-4]|H[12]|9M)?FY\d{2}", canon := canonical_period(p.period)):
                p.period = canon   # "H2 FY27" and "FY2026-27" match one another call to call (review of F180)
        else:
            p.period_stated = False
        p.company_defined = bool((p.definition or "").strip())   # never written to financial_metrics (spec 3.8)
        p.pages = [p.page] if p.page else []
        p.id = point_id(scope, p)
        kept.append(p)

    # one fact once (spec 3.7): the same type, topic, figure and period is one point with several pages
    unique: dict[tuple, CallPoint] = {}
    for p in kept:
        key = (p.type, _topic_key(p), p.value, p.value_high, p.period)
        first = unique.get(key)
        if first is None:
            unique[key] = p
            continue
        first.pages = sorted(set(first.pages) | set(p.pages))
        if p.section == "QA" and first.section != "QA":   # the Q&A's words are the better quote, its id the one kept
            p.pages = first.pages
            unique[key] = p
    merged = [p for p in kept if unique.get((p.type, _topic_key(p), p.value, p.value_high, p.period)) is p]

    # the Q&A clarification wins (spec 3.6): Sobha's opening "whole of FY27" and the answer's second half of FY27
    for answer in (p for p in merged if p.section == "QA" and p.speaker != "ANALYST"):
        for earlier in merged:
            if (earlier is not answer and earlier.section in ("PREPARED", "SLIDE") and earlier.type == answer.type
                    and _topic_key(earlier) == _topic_key(answer) and earlier.superseded_by is None
                    and _same_span(earlier.period, answer.period)
                    and (earlier.period != answer.period or (earlier.value, earlier.value_high) != (answer.value, answer.value_high))):
                earlier.superseded_by = answer.id
    return merged, dropped


# ---------------------------------------------------------------- memory
def _entry(p: CallPoint, news_id: str, date: str, quarter: str | None, at: str) -> dict:
    lab = label("ai", "call", at, ok=True)
    if p.page:
        lab["page"] = p.page
    if p.quote:
        lab["quote"] = p.quote
    row = {"id": p.id, "news_id": news_id, "date": date, "quarter": quarter, **p.model_dump(exclude={"id"}), "lab": lab}
    return {k: v for k, v in row.items() if v is not None and v != []}


def remember(dossier: dict, news_id: str, filed_at: str, kept: list[CallPoint], now: str | None = None) -> None:
    """The filing's checked points into `dossier["call_memory"]`, replacing its earlier ones (a re-run), newest call first, at
    most CALL_MEMORY_KEPT (spec section 4). Mutates the dossier; nothing else in memory changes."""
    at = now or now_iso()
    date, quarter = (filed_at or "")[:10], quarter_of(filed_at or "")
    rest = [e for e in dossier.get("call_memory", []) if e.get("news_id") != news_id]
    scope = f"{dossier.get('scrip_code') or ''}:{news_id}"
    fresh = []
    for p in kept:
        p = p.model_copy()
        p.id = p.id or point_id(scope, p)
        fresh.append(_entry(p, news_id, date, quarter, at))
    dossier["call_memory"] = sorted(fresh + rest, key=lambda e: e.get("date") or "", reverse=True)[:CALL_MEMORY_KEPT]


def prior_points(dossier: dict | None, news_id: str, filed_at: str, limit: int = PRIOR_POINTS) -> list[dict]:
    """The company's points from its latest earlier call (not this filing, dated before it), current ones first, at most
    `limit`, as the model sees them (id, type, topic, statement, period)."""
    day = (filed_at or "")[:10]
    earlier = [e for e in (dossier or {}).get("call_memory", []) if e.get("news_id") != news_id and (e.get("date") or "") < day]
    if not earlier:
        return []
    latest = max(earlier, key=lambda e: e.get("date") or "")["news_id"]
    mine = [e for e in earlier if e["news_id"] == latest]
    mine.sort(key=lambda e: e.get("superseded_by") is not None)
    return [{k: e.get(k) for k in ("id", "type", "topic", "statement", "period")} for e in mine[:limit]]


def find_filing(sink, news_id: str):
    """The ledger's row of a filing as a Filing, or None: the export_filings query seeks the first id after one just below
    this one (no query by id exists, and a new one would be a Worker change)."""
    from .models import Filing

    below = news_id[:-1] + chr(ord(news_id[-1]) - 1) if news_id else news_id
    for row in sink.query("export_filings", ["", below, 50]) or []:
        if row.get("news_id") == news_id:
            return Filing.model_validate(row)
    return None


def counts_by_type(points: list[CallPoint]) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in points:
        out[p.type or "?"] = out.get(p.type or "?", 0) + 1
    return dict(sorted(out.items()))
