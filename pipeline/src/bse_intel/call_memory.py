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
import time
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
_WORDS = re.compile(r"[A-Za-z]{3,}")   # a quote needs at least one word of three letters
CONTEXT_CHARS = 600      # around a quote, on its page, where its period may be named
# One request reads this much of the document (whole pages); a longer one is read in parts. The first measured run's
# 6,000-token replies were too short for a whole document's points; Gemini Flash's 32,000-token reply is not (run 2, 26 Oct)
PART_CHARS = 60_000


def part_chars() -> int:
    """PART_CHARS, or CALL_MEMORY_PART_CHARS for a measured test run (maintenance `call-memory`, part_chars input; owner,
    30 Oct 2026: test smaller parts on one locked model). Scheduled runs never set it."""
    import os

    try:
        return max(2_000, int(os.environ["CALL_MEMORY_PART_CHARS"])) if os.environ.get("CALL_MEMORY_PART_CHARS") else PART_CHARS
    except ValueError:
        return PART_CHARS
RETRY_WAIT_S = 20.0      # the shortest wait before a failed part is asked again (run 5, F180)
# F203 (27 Oct 2026): about half the documents of the measured runs 6-8 failed on free-provider capacity (5xx, 429, "paced").
# A part that failed only for capacity is asked again, up to MAX_PART_ATTEMPTS in all, after these waits: the gateway pauses a
# model 60 s after its first 429, 300 s after the second (ai.gateway.RATE_PAUSES), so the waits clear those pauses.
MAX_PART_ATTEMPTS = 4
RETRY_WAITS = (65.0, 130.0, 305.0)
DEFAULT_GAP_S = 12.0     # seconds between two requests when providers.toml gives the route no per-minute limit
# what one provider's failure says (the gateway's outcome details): a server error, a timeout or an overload is worth another
# try; a refusal of the request itself (400, 401, 403, 404) would answer the same. A 429 or "circuit open" says neither.
_SERVER_ERROR = re.compile(r"\b(?:http|status|code|error)[ :=]*5\d\d\b|\b5\d\d\s+(?:internal|bad gateway|service|gateway|server)|"
                          r"internal ?server|server error|time[sd]? ?out|overload|service unavailable|bad gateway|"
                          r"connection (?:reset|error|aborted)", re.I)
_REFUSAL = re.compile(r"\b(?:http|status|code|error)[ :=]*(?:400|401|403|404)\b|\b(?:400|401|403|404)\s+(?:bad request|unauthori|"
                      r"forbidden|not found|invalid)|bad request|model\b.{0,40}\bnot found|not found.{0,20}\bmodel|unauthori[sz]ed|forbidden|invalid api key", re.I)

# a failure of capacity, not of content: a 429, "paced", a busy slot, a cooling model, an open circuit, a 5xx or a timeout
_CAPACITY = re.compile(r"429|rate.?limit|paced|busy|circuit|cooling|cooldown|quota|server ?error|\b(?:HTTP|status|error)\W{0,3}5\d\d\b|"
                       r"\b50[234]\b|time[sd]? ?out|overload|service unavailable|temporarily unavailable|bad gateway|"
                       r"connection ?(?:error|reset|refused|aborted|closed)", re.I)


class CallReadFailed(RuntimeError):
    """Every part of a document failed. `capacity` is true when each failure was one of capacity (worth a later retry) and
    false when one was of content (no JSON, a reply the schema refuses: the same document would answer the same)."""

    def __init__(self, message: str, capacity: bool):
        super().__init__(message)
        self.capacity = capacity


class DayQuotaExhausted(RuntimeError):
    """Every free model of the route is at its daily ceiling: the caller stops and leaves the rest queued for tomorrow."""


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
def parts(text: str, limit: int = PART_CHARS) -> list[str]:
    """The document in parts of whole pages, each at most `limit` characters (a longer page is a part of its own), every part
    keeping its page markers; a text with no markers is cut at line ends."""
    marks = list(_PAGE_MARK.finditer(text or ""))
    if not marks:
        chunks, cur = [], ""
        for line in (text or "").splitlines(keepends=True):
            if cur and len(cur) + len(line) > limit:
                chunks.append(cur)
                cur = ""
            cur += line
        return [c for c in chunks + [cur] if c.strip()] or [""]
    pages = [text[m.start():(marks[i + 1].start() if i + 1 < len(marks) else len(text))] for i, m in enumerate(marks)]
    head = text[:marks[0].start()]
    out, cur = [], head
    for page in pages:
        if cur.strip() and len(cur) + len(page) > limit:
            out.append(cur)
            cur = ""
        cur += page
    return out + ([cur] if cur.strip() else [])


def read(gateway, prompts, filing, kind: str, industry: str | None, text: str, blocks: str = "", prior: list[dict] | None = None,
         paid: frozenset[str] | set[str] = frozenset(), gap_s: float = 0.0, retry_until: float | None = None) -> CallMemoryOutput:
    """The document read in parts of whole pages (PART_CHARS), one AI call each, on the call_memory route (free models with
    their own quota, not the cards' Gemini Flash days) and never a paid provider (the daily path costs $0, CLAUDE.md D24).
    A part whose reply is not JSON is skipped and counted; if every part fails it raises, the caller logs it and the card
    stands (the points wait for a re-run of `call-memory --ids`). The models and prompt size ride on the result.
    Pacing (F203): `gap_s` seconds between two requests (pace_gap_s); a part that failed for capacity only is asked again after
    RETRY_WAITS, MAX_PART_ATTEMPTS in all, never past `retry_until` (a time.monotonic() value); a part that failed for content
    is not. Every model at its daily ceiling raises DayQuotaExhausted; every part failed raises CallReadFailed."""
    route = next((r for r in ("call_memory", "pass2_long", "pass2_bulk") if gateway.has_route(r)), "pass2_bulk")
    scope = getattr(gateway, "card_scope", None)
    chunks = parts(text, part_chars())
    points: dict[int, list] = {}
    models, chars, reasons, errors = [], 0, [], {}
    news_id = getattr(filing, "news_id", "?")

    def attempt(i: int, chunk: str) -> None:
        system, user = prompts.call_memory(filing, kind, industry, chunk, prior, part=(i, len(chunks)))
        nonlocal chars
        chars += len(system) + len(user)
        try:
            # not the card's clock: the card is written and its cap spent before this reading
            with (scope(capped=False) if scope else nullcontext()):
                result = gateway.complete_json(route, system, user, CallMemoryOutput, bulk=True,
                                               allow=lambda target: target.provider not in paid)
        except Exception as exc:   # noqa: BLE001 - one part's failure leaves the others
            errors[i] = exc
            log.warning("%s: call memory part %d of %d failed: %s", news_id, i, len(chunks), exc)
            return
        errors.pop(i, None)
        points[i] = list(result.value.points)
        models.append(getattr(result, "model_label", None) or "?")
        if result.value.reason:
            reasons.append(result.value.reason)

    def day_quota() -> None:
        # every model at its daily ceiling: nothing was asked, tomorrow's quota is the wait (F203)
        spent = [exc for exc in errors.values() if getattr(exc, "quota_exhausted", False)]
        if spent:
            raise DayQuotaExhausted(f"{news_id}: {spent[-1]}")

    for i, chunk in enumerate(chunks, 1):
        if i > 1 and gap_s:
            time.sleep(gap_s)
        attempt(i, chunk)
        day_quota()
    attempts = 1
    # run 5: every model of the route answered server errors for 5 of 10 documents; runs 6-8 (F203): 429s and "paced" too.
    # Parts that failed for capacity are asked again after a wait that clears the gateway's pause; content failures are not
    while attempts < MAX_PART_ATTEMPTS:
        redo = [i for i, exc in sorted(errors.items()) if capacity_error(exc)]
        if not redo:
            break
        wait = max(RETRY_WAITS[min(attempts - 1, len(RETRY_WAITS) - 1)], RETRY_WAIT_S)
        if retry_until is not None and time.monotonic() + wait > retry_until:
            log.info("%s: call memory leaves parts %s for a later run (no time for the wait)", news_id, redo)
            break
        attempts += 1
        log.info("%s: call memory asks parts %s again (attempt %d of %d) after %.0f s", news_id, redo, attempts, MAX_PART_ATTEMPTS, wait)
        time.sleep(wait)
        for n, i in enumerate(redo):
            if n and gap_s:
                time.sleep(gap_s)
            attempt(i, chunks[i - 1])
        day_quota()
    failed = sorted(errors)
    if len(failed) == len(chunks):
        raise CallReadFailed(f"every part of the call-memory reading failed ({len(chunks)}, {attempts} attempt"
                             f"{'s' if attempts > 1 else ''}): {errors[failed[-1]]}",
                             capacity=all(capacity_error(errors[i]) for i in failed))
    all_points = [pt for i in sorted(points) for pt in points[i]]
    out = CallMemoryOutput(points=[], reason="; ".join(reasons)[:300] or None)
    out.points = all_points
    out.attempts = attempts
    out.served_by = ", ".join(sorted(set(models)))
    out.prompt_chars = chars
    out.parts, out.parts_failed = len(chunks), failed
    out.parts_failed_capacity = [i for i in failed if capacity_error(errors[i])]
    return out


def capacity_error(exc: BaseException) -> bool:
    """A failure of capacity only (F203): every model that was tried answered a 429, "paced", a busy slot, a cooling pause, a
    5xx or a timeout, and none refused the request (400, 401, 403, 404) or failed on content (no JSON, a reply the schema
    refuses). Read from the gateway's per-model outcomes (those at a daily ceiling or unavailable say nothing either way).
    Not the card's cap, and not a day's quota (that is DayQuotaExhausted)."""
    if getattr(exc, "capped", False) or getattr(exc, "quota_exhausted", False):
        return False
    outcomes = getattr(exc, "outcomes", None)
    details = [str(o[-1]) for o in outcomes if o[1] in ("failed", "transient")] if outcomes else [str(exc)]
    return bool(details) and all(_CAPACITY.search(d) for d in details) and not any(_REFUSAL.search(d) for d in details)


def pace_gap_s(settings) -> float:
    """Seconds to leave between two requests of the call_memory route (F203): a minute over the lowest per-minute request limit
    of its models (rpm 5 on Gemini Flash: 12 s), so one document's parts and the next document never ask a model faster than
    its window; DEFAULT_GAP_S when providers.toml states none. Never more than a minute."""
    try:
        targets = settings.load_toml("providers.toml").get("routes", {}).get("call_memory", [])
        rpms = [int(t["limits"]["rpm"]) for t in targets if (t.get("limits") or {}).get("rpm")]
    except Exception:   # noqa: BLE001 - a missing file or an odd entry: the default
        rpms = []
    return min(60.0, 60.0 / min(rpms)) if rpms else DEFAULT_GAP_S


def provider_error(exc: BaseException) -> bool:
    """A failure worth one more try: some provider of the route answered a server error (5xx), timed out or was overloaded,
    and none refused the request itself (400, 401, 403, 404). Read from the gateway's per-model outcomes when it gives them
    (a 429 beside a 5xx still retries; "circuit open" alone does not). Not the card's cap or a spent quota, and not a reply
    that merely holds no points (that is no exception)."""
    if getattr(exc, "capped", False) or getattr(exc, "quota_exhausted", False):
        return False
    outcomes = getattr(exc, "outcomes", None)
    details = [str(o[-1]) for o in outcomes] if outcomes else [str(exc)]
    return any(_SERVER_ERROR.search(d) for d in details) and not any(_REFUSAL.search(d) for d in details)


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


_WORD_NUMBERS = {w: float(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen twenty".split())} | {w: float(i) for i, w in enumerate(
    "zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth".split())} | {
    "thirty": 30.0, "forty": 40.0, "fifty": 50.0, "hundred": 100.0, "half": 0.5, "double": 2.0, "twice": 2.0}


def _numbers(text: str) -> list[float]:
    # "Three more analogs", "our fourth design center": a figure in words is the quote's figure (first measured run, F180)
    out = [v for w, v in _WORD_NUMBERS.items() if re.search(rf"\b{w}\b", (text or "").lower())]
    for m in gate._CLAIM_NUMBER.finditer(gate._flat(text or "")):
        try:
            out.append(float(m.group(0).replace(",", "").rstrip(".")))
        except ValueError:
            continue
    return out


def _has(value: float, numbers: list[float]) -> bool:
    # the quote's numbers carry no sign: an outflow is "(342.12)", "minus 342" or "-342" (review of F180)
    return any(abs(abs(value) - abs(n)) < 1e-9 for n in numbers)


def figure_issue(point: CallPoint, quote: str, context: str = "") -> str | None:
    """Every figure of the statement, the value and the high end is in the quote or beside it on its page (``context``: the
    CONTEXT_CHARS around the quote, a slide's whole page). The statement's period labels and dates are not figures
    (call_summary._figures); the numbers are read whole, so "2000 crore" is not a year. Changed after the third measured run
    (independent comparison, 26 Oct 2026): the quote alone dropped 99 true points of 107 (APL Apollo's "8 Mn Ton by FY28"
    under the slide heading "Capacity Expansion Plan By FY28", Eris's +100 bps margin levers, Sobha's Chandivali INR 1,000 cr
    in the next sentence of the answer) for 4 it rightly stopped."""
    stated = _numbers(f"{quote} {context}")
    for value, _, _ in _figures(point.statement or ""):
        if not _has(value, stated):
            return f"figure {value:g} of the statement is not in the quote"
    for name in ("value", "value_high"):
        value = getattr(point, name)
        if value is not None and not _has(value, stated):
            return f"{name} {value:g} is not in the quote"
    return None


def unit_issue(point: CallPoint, quote: str, context: str = "") -> str | None:
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
    # a scale the unit names may stand beside the quote on its page ("Rs in lakh" above a table row); a number followed by a
    # scale word (above) is read in the quote only (review of the third run: 31 true table rows dropped for this)
    elif any(not re.search(_ANYWHERE[kind], f"{flat} {gate._flat(context)}") for kind in named):
        return f"the unit {point.unit} names a scale the quote does not carry"
    magnitude = [k for k in named if k in _MAGNITUDE]
    if not magnitude:
        point.value_base, point.base_unit = None, None
        return None
    base_unit = "_".join(t for t in _unit_tokens(point.unit) if not any(re.fullmatch(rx, t) for _, rx in _UNIT_KINDS)) or None
    if point.value is not None:
        # the code works the base figure out; the model's own value_base is not a reason to drop (third measured run: Sobha's
        # "12 million square feet" was dropped for a model value_base of 1e6)
        point.value_base, point.base_unit = point.value * _MAGNITUDE[magnitude[0]], base_unit
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


def _on_page(quote: str, page: str) -> bool:
    """Every word (of 2+ letters) and every figure of the quote is on the page."""
    flat = gate._flat(page)
    words = re.findall(r"[a-z][a-z0-9]+", gate._flat(quote))
    figures = _numbers(quote)
    on_page = _numbers(page)
    return bool(words or figures) and all(re.search(rf"\b{re.escape(w)}", flat) for w in words) \
        and all(_has(f, on_page) for f in figures)


def _words(text: str) -> list[str]:
    return [w.rstrip(".,") for w in re.findall(r"[a-z0-9][a-z0-9.,%]*", gate._flat(text))]


def _near_pages(pages: list[tuple[int | None, str]], cited: int | None) -> list[tuple[int | None, str]]:
    """The cited page, the page before and the one after (a slide's printed number is not its PDF page). With no cited page,
    or a text with no page markers, none: a quote is then accepted only whole."""
    if cited is None:
        return []
    return [(n, t) for n, t in pages if n is not None and abs(n - cited) <= 1]


def _quote_on_near_pages(quote: str, p_page: int | None, pages: list[tuple[int | None, str]], slide: bool):
    """(page number, page text, mode) where the quote stands as the page's own words, line breaks and spacing aside, on the
    cited page or the one before or after ("page"; a slide's printed number is not its PDF page), or, on a slide's cited page
    only, with every word and figure on the page ("slide"). Else None. Words joined across a column split, or from two
    sentences, are never one quote (review of F180: it let a question and a later answer join)."""
    near = sorted(_near_pages(pages, p_page), key=lambda h: (h[0] != p_page, h[0] or 0))
    bare = quote.rstrip(" .,;:")
    for n, t in near:
        if gate.quote_found(bare, t):
            return n, t, "page"
        if slide and n == p_page and _on_page(quote, t):
            return n, t, "slide"
    return None


# ---------------------------------------------------------------- period of a table's column, speaker of a quote
# (blind review of 240 kept points, 30 Oct 2026: 6 of 10 wrong points had a figure under the wrong column header, 2 an
# analyst's words taken as management's.) Both checks only drop when the page or the transcript lets code tell; else keep.
_HEADER = re.compile(
    r"(?<![\w'])(?:(?:Q[1-4]|H[12]|9M)\s*[-]?\s*)?(?:FY|CY)\s*['’]?\s*(?:20)?\d{2}(?:\s*[-–/]\s*(?:20)?\d{2})?(?!\d)"
    r"|(?<!\w)LTM\s+[A-Za-z]{3,9}\s*['’]?\s*(?:20)?\d{2}(?!\d)", re.I)
_CELL = re.compile(r"(?<![\w.])[₹$]?\(?-?\d[\d,]*(?:\.\d+)?(?:\s?[-–]\s?\d[\d,]*(?:\.\d+)?)?\)?\s?(?:%|x|X)?\*?(?!\w)|(?<!\S)[-–—](?!\S)")


def _tokens(page: str) -> list[tuple]:
    """A page's text layer as ("H", period key), ("N", [figures]) and ("X", words) in reading order, line by line; a word
    breaks a row of figures, a "-" is a cell (a nil)."""
    items: list[tuple] = []
    for line in page.splitlines():
        line = line.strip()
        if not line:
            continue
        at = 0
        for m in re.finditer(f"(?:{_HEADER.pattern})|(?:{_CELL.pattern})", line, re.I):
            if re.search(r"[A-Za-z]{2,}", line[at:m.start()]):
                items.append(("X", line[at:m.start()]))
            at = m.end()
            if _HEADER.fullmatch(m.group(0).strip()):
                items.append(("H", canonical_period(m.group(0))))
            else:
                items.append(("N", [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", m.group(0))]))
        if re.search(r"[A-Za-z]{2,}", line[at:]):
            items.append(("X", line[at:]))
    return items


def _column_verdict(point: CallPoint, page: str) -> str | None:
    """`point`'s figure sits in column j of its row of figures; its period is column i of the period headers over (or under)
    that row. j != i on every place the figure stands: the issue ("period"); else None. No headers, a header row and a row
    of figures of different lengths, a period or figure that is not found once: None (spec: keep when the page cannot tell)."""
    if point.value is None or not point.period:
        return None
    want = canonical_period(point.period)
    items = _tokens(page)
    spots = []
    for k, it in enumerate(items):
        if it[0] == "N" and any(abs(abs(point.value) - abs(v)) < 1e-9 for v in it[1]):
            a = b = k
            while a > 0 and items[a - 1][0] == "N":
                a -= 1
            while b + 1 < len(items) and items[b + 1][0] == "N":
                b += 1
            spots.append((a, b, k - a))
    if not spots:
        return None
    detail = []
    for a, b, col in spots:
        n, verdicts = b - a + 1, []
        heads = []   # the header row before the figures (nearest), and the one right after them
        k = a - 1
        while k >= 0 and items[k][0] != "H":
            k -= 1
        if k >= 0:
            j = k
            while j > 0 and items[j - 1][0] == "H":
                j -= 1
            heads.append([h[1] for h in items[j:k + 1]])
        if b + 1 < len(items) and items[b + 1][0] == "H":
            j = b + 1
            while j + 1 < len(items) and items[j + 1][0] == "H":
                j += 1
            heads.append([h[1] for h in items[b + 1:j + 1]])
        for h in heads:
            if len(h) < n or n < 3 or h.count(want) != 1:
                verdicts.append(None)
            elif len(h) > n:   # a header with no figure under it (Waaree's CY2026 over 4 figures): counted from the right
                verdicts.append(len(h) - 1 - h.index(want) == n - 1 - col)
            else:
                verdicts.append(h.index(want) == col)
        if not verdicts or any(v is not False for v in verdicts):
            return None
        detail.append(f"column {col + 1} of {n}, {want} is column {heads[0].index(want) + 1} of {len(heads[0])}")
    return f"the figure {point.value:g} stands in " + "; ".join(detail)


_TURN = re.compile(r"^[ \t]*((?:Mr\.?\s+|Ms\.?\s+|Dr\.?\s+)?[A-Z][A-Za-z.'’-]*(?:[ \t]+[A-Za-z.'’-]+){0,4}?):(?![\w/])[ \t]*", re.M)
_TITLE = re.compile(r"^(?:mr|ms|mrs|dr|shri|smt|ca)\.?\s+", re.I)
_INTRO = re.compile(r"(?:question|line)\s+(?:is\s+)?(?:from|of)\s+(?:the\s+line\s+of\s+)?(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?)?\s*"
                    r"([A-Z][\w.'’-]+(?:\s+[A-Z][\w.'’-]+){0,3}?)\s+(?:from|of|with|at|-|–)\s", re.M)


def _who(name: str) -> str:
    return _TITLE.sub("", " ".join(name.lower().split())).strip(". ")


def turns(text: str) -> list[tuple[str, str]]:
    """(speaker, words) for each "Name:" line of a transcript (page markers left out). Empty when the text has none."""
    clean = _PAGE_MARK.sub("", text or "")
    marks = list(_TURN.finditer(clean))
    return [(_who(m[1]), clean[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(clean)])
            for i, m in enumerate(marks)]


def analysts_of(text: str) -> set[str]:
    """The names the moderator introduces for a question ("the next question is from the line of Kevin Shah from Aditya Birla
    Capital"), less anyone who also spoke before the first question: a name on both sides (Nuvoco's CFO and a Dolat analyst
    are both "Shravan Shah") is never told apart, so it is not an analyst here."""
    clean = _PAGE_MARK.sub("", text or "")
    found = list(_INTRO.finditer(clean))
    if not found:
        return set()
    before = {_who(m[1]) for m in _TURN.finditer(clean[:found[0].start()])}
    return {_who(m[1]) for m in found} - before


def _stems(point: CallPoint) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]{4,}", f"{point.topic or ''} {point.metric or ''}".lower().replace("_", " "))}


def _speaker_issue(point: CallPoint, text: str, pages=None) -> str | None:
    """The quote is only inside an analyst's turn (KEI: "in the interview today morning you mentioned that volume for FY27 will
    be somewhere around 10%", an analyst's question taken as management's guidance, blind review of 30 Oct 2026) and no
    management turn states the same figure beside the same topic: the issue ("speaker"). Turns that cannot be told apart
    (no "Name:" lines, no analyst introduced by the moderator, the quote in no turn or in a management turn): None."""
    quote = (point.quote or "").strip()
    sections = turns(text)
    analysts = analysts_of(text)
    if not quote or not sections or not analysts:
        return None
    pieces = [gate._flat(q) for q in gate._ELISION.split(quote) if len(q.split()) >= 3] or [gate._flat(quote)]
    at = [k for k, (_, words) in enumerate(sections) if all(piece in gate._flat(words) for piece in pieces)]
    if not at:
        return None
    mine = [sections[k][0] for k in at]
    if any(who not in analysts for who in mine):
        # management's own turn that never says the figure, straight after an analyst's turn that does: the figure is the
        # analyst's ("you mentioned volume around 10%", the answer "16% to 17%"; KEI)
        k = at[0]
        if (len(at) == 1 and point.value is not None and k > 0 and sections[k - 1][0] in analysts
                and len(quote.split()) >= 8 and not _has(point.value, _numbers(sections[k][1])) and _has(point.value, _numbers(sections[k - 1][1]))):
            return f"the figure {point.value:g} is in the question of {sections[k - 1][0]}, an analyst, not in the answer"
        return None
    if point.value is not None:
        stems = _stems(point)
        for who, words in sections:
            if who in analysts or who == "moderator":
                continue
            flat = gate._flat(words)
            for m in re.finditer(r"(?<![\w.])\d[\d,]*(?:\.\d+)?", flat):
                try:
                    figure = float(m.group(0).replace(",", "").rstrip("."))
                except ValueError:
                    continue
                if abs(abs(point.value) - figure) < 1e-9 and (not stems or any(
                        st in flat[max(0, m.start() - 200):m.end() + 200] for st in stems)):
                    return None
    return f"the quote is in the turn of {mine[0]}, an analyst, and no management turn gives the figure"


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
        if not quote:
            drop(p, "quote", "no quote")
            continue
        elsewhere, mode = None, None
        if not gate.quote_found(quote, text, blocks):
            # a slide's words are laid out in boxes: "39.7% ROCE in H1FY27" is on APL Apollo's slide as a figure above its
            # label, never as one line. On a slide, every word and figure of the quote on the named page is enough; the
            # point says its quote was assembled (first measured run, F180). A page set in two columns is read straight
            # across and the model may name the slide's printed number, not the PDF page (run 5): the cited page, the one
            # before and the one after are tried for the quote whole. A quote that is on none of them is dropped.
            elsewhere = _quote_on_near_pages(quote, p.page, pages, p.section == "SLIDE")
            if elsewhere is None:
                drop(p, "quote", "the quote is not in the document")
                continue
            elsewhere, mode = elsewhere[:2], elsewhere[2]
            p.quote_assembled = mode == "slide"
        # the page the quote is on, whatever the model named (spec 3.5); the page's text also gives the figures and the period
        # their context (a quote on several pages, as the same sentence on a slide and in the talk, stays on the page the
        # model named)
        homes = [(n, t) for n, t in pages if gate.quote_found(quote, t)]
        number, page_text = next((h for h in homes if h[0] == p.page), homes[0] if homes else (elsewhere or (None, "")))
        if not page_text and p.quote_assembled:
            page_text = next((t for n, t in pages if n == p.page), "")
        if number is not None:
            p.page = number
        if p.page is None and len(pages) == 1:
            p.page = pages[0][0]
        context = ""
        if page_text:
            flat_page, flat_quote = gate._flat(page_text), gate._flat(quote)
            at = flat_page.find(flat_quote.split("...")[0].strip()[:80])
            if p.quote_assembled:
                context = flat_page   # a slide's figures sit in boxes around its words: the whole slide
            elif at >= 0:
                context = flat_page[max(0, at - CONTEXT_CHARS):at + len(flat_quote) + CONTEXT_CHARS]
        if not _WORDS.search(quote):
            # "64% 19%" or "37.3%" alone says nothing of what the figures are: APL Apollo's 64% was put on housing where the
            # slide says commercial (review of the third run)
            drop(p, "quote", "the quote has no words, only figures")
            continue
        if (issue := figure_issue(p, quote, context)):
            drop(p, "figure", issue)
            continue
        p.figure_beside_quote = figure_issue(p, quote) is not None   # kept, but the quote alone does not carry every figure
        if (issue := unit_issue(p, quote, context)):
            drop(p, "unit", issue)
            continue
        if p.period:
            if not period_named(p.period, f"{quote} {context or quote}"):
                p.period, p.period_stated = None, False   # never guessed, and never a checkable target
            elif re.fullmatch(r"(?:Q[1-4]|H[12]|9M)?FY\d{2}", canon := canonical_period(p.period)):
                p.period = canon   # "H2 FY27" and "FY2026-27" match one another call to call (review of F180)
        else:
            p.period_stated = False
        if p.period and page_text and (issue := _column_verdict(p, page_text)):
            drop(p, "period", issue)
            continue
        if p.section != "SLIDE" and (issue := _speaker_issue(p, text, pages)):
            drop(p, "speaker", issue)
            continue
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
