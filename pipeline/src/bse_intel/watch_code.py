"""CARD_WATCH_VERDICT (F205, TODO 106): code decides a memory watch's MET / MISSED / NOT DUE from memory, never from text.

Four live cards of 26 Oct 2026 carried a verdict the filing contradicts: MAHABANK "KPI check missed: GNPA ratio" with 1.25%
against a target at or below 1.45% (the target's direction was ignored); SAKAR "oncology revenue missed" on a FY27 target
(its period was not yet due); APL Apollo's card said 9.63 lakh t "meets the watchlist target" for a 10 lakh t watch that is
MISSED (AI text against the code verdict); Unimech's "Q1FY27 revenue to surpass Q4FY26" was a breach "with no delivery on
record" while memory holds 107.62 Cr against 81.8 Cr.

Four independent reviews of the first design (target and evidence both read from free text) kept finding wrong verdicts: another
metric's figure, a prior-year figure read as the actual, a rate target against a period total, $ against Rs, unknown period words.
So the evidence text is not read at all. A verdict is given only when
  1. the watch maps to ONE stored metric (its own words name it, no other word qualifies it) and ONE period (Q, H, 9M or FY),
  2. the target is one figure in Rs / % / tonnes with one direction word from a closed list,
  3. memory holds that metric for that exact period, on the basis the watch names, in the same kind of unit, and the period has ended.
The actual is memory's figure. Everything else gets None and the existing rules stand. A watch whose period ends after the
filing's date is NOT_DUE whatever else is known."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .periods import canonical_period, due_date

MET, MISSED, NOT_DUE = "MET", "MISSED", "NOT_DUE"

# ------------------------------------------------------------------ periods
_PERIOD = r"(?:(?:Q[1-4]|H[12]|9M)\s*[-–]?\s*FY\s*'?\d{2,4}(?:\s*[-–/]\s*\d{2,4})?|FY\s*'?\d{2,4}(?:\s*[-–/]\s*\d{2,4})?)"
_PERIOD_TOKEN = re.compile(rf"\b{_PERIOD}\b", re.I)
_CANON = re.compile(r"(?:Q[1-4]|H[12]|9M)FY\d\d|FY\d\d")


def period_labels(*texts: str | None) -> list[str]:
    """Canonical quarter / half / 9M / year labels named in the texts, in order (duplicates kept out)."""
    out: list[str] = []
    for text in texts:
        for m in _PERIOD_TOKEN.finditer(text or ""):
            label = canonical_period(m.group(0))
            if _CANON.fullmatch(label) and label not in out:
                out.append(label)
    return out


# ------------------------------------------------------------------ the target
_NUM = r"(?<![\w.,])-?\d[\d,]*(?:\.\d+)?"


def _spaced(text: str) -> str:
    """"Rs100" and "INR100" as "Rs 100": the figure is not part of the mark."""
    return re.sub(r"\b(rs\.?|inr)(?=\d)", r"\1 ", text or "", flags=re.I)
_DIRECTION = re.compile(
    r"<=|≤|=<|>=|≥|=>|\bor\s+(?:above|more|higher|greater)\b|\bor\s+(?:below|less|lower)\b|\bnot\s+(?:to\s+)?exceed(?:ing)?\b|\b(?:not|no)\s+more\s+than\b|\b(?:not|no)\s+less\s+than\b|"
    r"\bat\s+or\s+below\b|\bat\s+or\s+above\b|\bat\s+most\b|\bat\s+least\b|"
    r"\bbelow\b|\bunder\b|\babove\b|\bover\b|\bmore\s+than\b|\bexceed(?:ing|s)?\b|<|>", re.I)
# word -> (comparison, strict): below / under / above / over / more than / exceed* are strict, the rest include the figure
_OPS = {"<=": ("<=", False), "≤": ("<=", False), "=<": ("<=", False), ">=": (">=", False), "≥": (">=", False), "=>": (">=", False),
        "not exceed": ("<=", False), "not exceeding": ("<=", False), "not to exceed": ("<=", False),
        "not more than": ("<=", False), "no more than": ("<=", False), "not less than": (">=", False), "no less than": (">=", False),
        "or above": (">=", False), "or more": (">=", False), "or higher": (">=", False), "or greater": (">=", False),
        "or below": ("<=", False), "or less": ("<=", False), "or lower": ("<=", False), "at or below": ("<=", False), "at or above": (">=", False), "at most": ("<=", False), "at least": (">=", False),
        "below": ("<", True), "under": ("<", True), "<": ("<", True), "above": (">", True), "over": (">", True),
        "more than": (">", True), "exceed": (">", True), "exceeds": (">", True), "exceeding": (">", True), ">": (">", True)}
_BAD_CURRENCY = re.compile(r"[$€£¥]|\b(?:us\$|usd|eur|gbp|jpy|aed|sgd|dollars?|euros?|pounds?|yen)\b", re.I)
_RATE = re.compile(r"\bper\b|/\s*(?:month|day|year|yr|annum|qtr|quarter|t|tonne|ton)\b|\ba\s+(?:month|day|year|quarter)\b|"
                   r"\brun[- ]?rate\b|\bannuali[sz]ed\b|\b(?:monthly|daily|yearly|weekly|quarterly|annual)\s+(?:run|rate)\b|"
                   r"\b(?:monthly|daily|yearly|weekly)\b|\bmtpa\b|\bp\.?a\.?\b", re.I)
_DELTA = re.compile(r"\bfrom\b|\bby\s*(?:₹|rs\.?|inr)?\s*\d|\d\s*(?:%|[a-z]+)?\s+over\b|\bup\s+to\b|\bbetween\b|\band\b|"
                    r"\b(?:growth|grow\w*|yoy|qoq|cagr|increase\w*|decrease\w*|reduc\w*|improv\w*|expan\w*|ramp\w*|"
                    r"cumulative|ytd|aggregate|total\s+of)\b", re.I)
_NEGATION = re.compile(r"\b(?:not|never|no|without|neither|nor|unless|except|cannot)\b|n't", re.I)
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_DATE = re.compile(rf"\d{{1,2}}[-/.]\d{{1,2}}[-/.]\d{{2,4}}|\d{{1,2}}\s+{_MONTH},?\s+\d{{4}}|{_MONTH}\s+\d{{4}}", re.I)
_CALENDAR = re.compile(r"\b(?:by|in|till|until|before|during|for)\s+(?:the\s+)?(?:calendar\s+|financial\s+|fiscal\s+)?(?:year\s+|cy\s*|fy\s*)?'?(?:19|20)\d{2}\b", re.I)
_FILLER = frozenset(
    "by in for of the be is to a an at on ceiling floor target level ratio pct percent percentage cent figure quarter quarterly "
    "reported company companys total from operations consolidated standalone basis kpi check results result approximately approx "
    "around about nearly roughly near and or end year annual full".split())
_UNIT_WORDS = frozenset("cr crore crores lakh lakhs lac lacs mn mln million bn billion thousand k rs inr t ton tons tonne tonnes".split())


def _unit(before: str, after: str) -> tuple[str, float, int] | None:
    """(kind, factor to the base unit, characters of ``after`` it uses) of the figure between ``before`` and ``after``: a
    percentage, a rupee amount (rupees; a crore word, or a Rs / ₹ / INR mark, is needed) or a mass in tonnes. None for
    anything else (counts, bps, a bare number, another currency)."""
    from .dossier import _SCALE_WORDS

    cur = bool(re.search(r"(?:₹|\brs\.?|\binr)\s*$", before, re.I))
    m = re.match(r"\s*(?:%|per\s*cent\b|percent\b)", after, re.I)
    if m:
        return None if cur else ("pct", 1.0, m.end())
    lead = len(after) - len(after.lstrip())
    scale, used = None, 0
    for pattern, size in _SCALE_WORDS:
        s = pattern.match(after.lstrip())
        if s:
            scale, used = size, lead + s.end()
            break
    rest = after[used:]
    m = re.match(r"\s*(?:tonnes?|tons?|t)\b(?![\w/])", rest, re.I)
    if m and not cur:
        return "mass", scale or 1.0, used + m.end()
    if scale is not None and (cur or scale == 1e7):
        return "inr", scale, used
    return None


@dataclass(frozen=True)
class Target:
    op: str          # "<=", "<", ">=", ">"
    goal: float      # in the base unit of its kind
    kind: str        # "pct", "inr", "mass"
    strict: bool = False
    bare: bool = False   # no direction word was given


def parse_target(target: str | None, text: str = "") -> Target | None:
    """One direction word from the closed list and ONE figure in Rs / % / tonnes, nothing else (the watch's own words may repeat).
    Rate targets (per month, run-rate), another currency, growth / delta / from-to / between, a negation outside the list, a
    second figure, a count or bps give None."""
    t = _spaced(target).strip()
    if not t or _BAD_CURRENCY.search(t):
        return None
    t = re.sub(r"\bper\s*cent\b", "%", t, flags=re.I)
    if _RATE.search(t):
        return None
    hits = list(_DIRECTION.finditer(t))
    if len(hits) > 1:
        return None
    # no direction word: a bare figure ("10 lakh tons"); judge() reads it as "at least" for the measures that only grow
    op = _OPS.get(re.sub(r"\s+", " ", hits[0].group(0).lower())) if hits else (">=", False)
    rest = t[:hits[0].start()] + " " + t[hits[0].end():] if hits else t
    for pattern in (_DATE, _CALENDAR, _PERIOD_TOKEN):
        rest = pattern.sub(" ", rest)
    if op is None or _DELTA.search(rest) or _NEGATION.search(rest):
        return None
    figures = list(re.finditer(_NUM, rest))
    if len(figures) != 1:
        return None
    f = figures[0]
    unit = _unit(rest[:f.start()], rest[f.end():])
    if unit is None:
        return None
    kind, factor, used = unit
    left = (rest[:f.start()] + " " + rest[f.end() + used:]).lower()
    left = re.sub(r"₹|\brs\.?|\binr\b|%", " ", left)
    allowed = _FILLER | _UNIT_WORDS | set(re.findall(r"[a-z]+", (text or "").lower()))
    if any(w not in allowed for w in re.findall(r"[a-z]+", left)):
        return None
    value = float(f.group(0).replace(",", ""))
    return Target(op[0], value if kind == "pct" else value * factor, kind, strict=op[1], bare=not hits)


# ------------------------------------------------------------------ the metric
@dataclass(frozen=True)
class _Spec:
    key: str
    rx: re.Pattern
    names: tuple[str, ...]      # memory metric names this watch may be judged on; () = any name with "volume"
    kind: str                   # the unit kind the stored figure must have


def _rx(p: str) -> re.Pattern:
    return re.compile(p, re.I)


_SPECS = (
    _Spec("gnpa", _rx(r"\bgnpas?\b|\bgross\s+(?:non[- ]?performing\s+assets?|npas?)\b"), ("gnpa_pct", "gnpa"), "pct"),
    _Spec("nnpa", _rx(r"\bnnpas?\b|\bnet\s+(?:non[- ]?performing\s+assets?|npas?)\b"), ("nnpa_pct", "nnpa"), "pct"),
    _Spec("roa", _rx(r"\broa\b|\breturn\s+on\s+assets?\b"), ("roa_pct", "roa"), "pct"),
    _Spec("combined", _rx(r"\bcombined\s+ratio\b"), ("combined_ratio",), "pct"),
    _Spec("claims", _rx(r"\bclaims?\s+ratio\b"), ("claims_ratio",), "pct"),
    _Spec("ebitda_margin", _rx(r"\b(?:ebitda|operating)\s+margins?\b|\bopm\b"), ("ebitda_margin",), "pct"),
    _Spec("ebitda", _rx(r"\bebitda\b(?!\s+margin)"), ("ebitda",), "inr"),
    _Spec("pat", _rx(r"\bpat\b|\bnet\s+profit\b|\bprofit\s+after\s+tax\b"), ("pat",), "inr"),
    _Spec("pbt", _rx(r"\bpbt\b|\bprofit\s+before\s+tax\b"), ("pbt",), "inr"),
    _Spec("revenue", _rx(r"\brevenues?\b|\bnet\s+sales\b|\bsales\b(?!\s+volume)"), ("revenue",), "inr"),
    _Spec("nii", _rx(r"\bnii\b|\bnet\s+interest\s+income\b"), ("nii",), "inr"),
    _Spec("volume", _rx(r"\b(?:sales\s+)?volumes?\b"), (), "mass"),
)
_STORED = {"PCT": ("pct", 1.0), "%": ("pct", 1.0), "PERCENT": ("pct", 1.0), "PERCENTAGE": ("pct", 1.0),
           "INR_CR": ("inr", 1e7), "CR": ("inr", 1e7), "INR_LAKH": ("inr", 1e5), "LAKH": ("inr", 1e5), "INR_MN": ("inr", 1e6),
           "INR_M": ("inr", 1e6), "INR_BN": ("inr", 1e9), "TONNES": ("mass", 1.0), "MT": ("mass", 1.0), "TONNE": ("mass", 1.0), "TONS": ("mass", 1.0),
           "LAKH_TONNES": ("mass", 1e5), "LAKH_TONS": ("mass", 1e5)}
_BASIS = re.compile(r"\b(standalone|consolidated)\b", re.I)


def _strip_for_leftover(text: str, spec: _Spec) -> list[str]:
    from .dossier import _SCALE_WORDS  # noqa: F401  (unit words are in _UNIT_WORDS)

    s = spec.rx.sub(" ", text or "")
    s = re.sub(r"\bper\s*cent\b", " ", s, flags=re.I)
    for pattern in (_DATE, _CALENDAR, _PERIOD_TOKEN, _DIRECTION):
        s = pattern.sub(" ", s)
    s = re.sub(_NUM, " ", s)
    return re.findall(r"[a-z]+", re.sub(r"[₹%]", " ", s.lower()))


def map_metric(w: dict) -> _Spec | None:
    """The one stored metric the watch is about: its own words name exactly one metric of the table and no other word qualifies
    it ("oncology revenue", "EBITDA per tonne", "gross margin", "segment EBITDA" are none). A metric the model tagged on the
    watch must agree."""
    text = w.get("text") or ""
    found = [s for s in _SPECS if s.rx.search(text)]
    if len(found) != 1:
        return None
    spec = found[0]
    if any(word not in _FILLER | _UNIT_WORDS for word in _strip_for_leftover(text, spec)):
        return None
    tagged = (w.get("metric") or "").strip().lower()
    if tagged and not (tagged in spec.names or (not spec.names and "volume" in tagged and "growth" not in tagged)):
        return None
    return spec


def _sources_of(e: dict) -> list[dict]:
    from .dossier import _sources

    return _sources(e)


def _src_basis(s: dict, e: dict) -> str | None:
    return s.get("basis") or (s.get("lab") or {}).get("basis") or e.get("basis") or (e.get("lab") or {}).get("basis") or None


def _entry_basis(e: dict) -> str | None:
    """The row's one basis from its sources; None when they are unlabelled or disagree."""
    bases = {_src_basis(s, e) for s in _sources_of(e)}
    return next(iter(bases)) if len(bases) == 1 else None


def _sources_agree(e: dict) -> bool:
    """Every source of the row states the same figure within 2% and in one unit (a calculated EBITDA margin of 3.39% beside the
    company's stated 6.0% is no figure to judge a target by)."""
    src = [s for s in _sources_of(e) if s.get("value") is not None]
    if len({str(s.get("unit") or e.get("unit") or "").upper() for s in src}) > 1:
        return False
    top = max((abs(float(s["value"])) for s in src), default=0)
    return all(abs(float(s["value"]) - float(src[0]["value"])) <= 0.02 * top for s in src)


def _memory_row(spec: _Spec, period: str, metrics: list[dict], text: str) -> dict | None:
    """Memory's figure for the metric and exact period, on the basis the watch names; None when absent, ambiguous (two metric
    names fit), not marked ok, when its sources disagree, or when they sit on different bases (or the watch names a basis that is
    not every source's)."""
    rows = [e for e in metrics if e.get("period") == period and e.get("value") is not None and (e.get("lab") or {}).get("ok") is not False
            and (e.get("metric") in spec.names if spec.names else ("volume" in (e.get("metric") or "") and "growth" not in (e.get("metric") or "")))]
    if not rows or len({str(e.get("unit")).upper() for e in rows}) != 1:
        return None
    row = rows[0]
    # two names of one measure (gnpa and gnpa_pct) may both hold the period: they must say the same
    if any(not _sources_agree(e) or abs(float(e["value"]) - float(row["value"])) > 0.02 * max(abs(float(e["value"])), abs(float(row["value"]))) for e in rows):
        return None
    wanted = {b.upper() for b in _BASIS.findall(text)}
    if len(wanted) > 1:
        return None
    have = {(_src_basis(s, row) or "").upper() for s in _sources_of(row)}
    if len(have - {""}) > 1 or (wanted and have != wanted):
        return None
    return row


# ------------------------------------------------------------------ the verdict
@dataclass(frozen=True)
class Judged:
    verdict: str
    spec: _Spec
    target: Target
    period: str
    actual: float


def _latest_end(metrics: list[dict]):
    ends = [due_date(m["period"]) for m in metrics if m.get("value") is not None and m.get("period")]
    return max((e for e in ends if e), default=None)


def _filed(filed_at: str):
    try:
        return date.fromisoformat((filed_at or "")[:10])
    except ValueError:
        return None


def not_due(w: dict, filed_at: str) -> bool | None:
    """True when any period the watch names ends after the filing's own date (a FY27 target on a Q2FY27 card): no figure for it
    can exist. None when the watch names no period or date at all."""
    when = _filed(filed_at)
    labels = period_labels(w.get("period"), w.get("check_in"), w.get("target"), w.get("text"))
    ends = [due_date(label) for label in labels]
    if not ends:
        ends = [due_date(w.get("check_in")) or due_date((w.get("check_by") or "")[:10])]
    ends = [e for e in ends if e]
    if not ends or when is None:
        return None
    return any(e > when for e in ends)


_GROWS = frozenset({"revenue", "ebitda", "pat", "pbt", "nii", "volume"})


def _decimals(value) -> int:
    text = repr(float(value))
    return len(text.split(".")[1].rstrip("0")) if "." in text and "e" not in text else 0


def judge(w: dict, metrics: list[dict], filed_at: str) -> Judged | None:
    """MET / MISSED from memory's figure for the watch's one metric and one period, against the target's one figure and
    direction; None whenever a step is not certain."""
    if w.get("kind") != "KPI":
        return None
    labels = period_labels(w.get("period"), w.get("check_in"), w.get("target"), w.get("text"))
    if len(labels) != 1:
        return None
    period = labels[0]
    end, when, latest = due_date(period), _filed(filed_at), _latest_end(metrics)
    if end is None or when is None or end > when or latest is None or end > latest:
        return None
    spec = map_metric(w)
    target = parse_target(w.get("target"), w.get("text") or "") if spec else None
    if spec is None or target is None or target.kind != spec.kind:
        return None
    row = _memory_row(spec, period, metrics, w.get("text") or "")
    stored = _STORED.get(str(row.get("unit") or "INR_CR").upper()) if row else None
    if not stored or stored[0] != target.kind:
        return None
    actual = float(row["value"]) * stored[1]
    if target.kind != "pct" and target.goal and actual and not (1 / 50 < abs(actual) / abs(target.goal) < 50):
        return None   # F179's 50x rule: another unit
    if target.bare and spec.key not in _GROWS:
        return None   # a ratio or a count with no direction word could be a ceiling
    step = 0.5 * 10 ** -_decimals(row["value"]) * stored[1]
    if target.strict and abs(actual - target.goal) <= step:
        return None   # equal at the figure's own precision: strict "below 1.45%" with 1.45 is not decided by rounding
    hit = {"<=": actual <= target.goal, "<": actual < target.goal, ">=": actual >= target.goal, ">": actual > target.goal}[target.op]
    return Judged(MET if hit else MISSED, spec, target, period, actual)


def watch_code_verdict(w: dict, evidence: str | None, metrics: list[dict], news_id: str, filed_at: str) -> str | None:
    """MET / MISSED / NOT_DUE for a KPI watch item, else None (the existing rules and the model's verdict stand). The evidence
    text and the filing's id are not read: the actual is memory's figure."""
    if w.get("kind") != "KPI":
        return None
    if (w.get("created_on") or "") >= filed_at:
        return None   # a watch made by this filing or later is not answered by it
    if not_due(w, filed_at):
        return NOT_DUE
    j = judge(w, metrics, filed_at)
    return j.verdict if j else None


# ------------------------------------------------------------------ guidance that compares two periods
_REL_PERIOD = r"(?:Q[1-4]|H[12]|9M)\s*FY\s*'?\d{2,4}|FY\s*'?\d{2,4}"
# the exact shape "<period A> <metric> to (surpass|exceed|be above|be higher than) <period B> [<metric>]"
_RELATIVE = re.compile(rf"^\s*(?P<a>{_REL_PERIOD})\s+(?P<m1>[A-Za-z][A-Za-z &/]*?)\s+to\s+(?:surpass|exceed|be\s+above|be\s+higher\s+than)\s+"
                       rf"(?P<b>{_REL_PERIOD})(?:\s+(?P<m2>[A-Za-z][A-Za-z &/]*?))?\s*\.?\s*$", re.I)


def _name(metric: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (metric or "").lower())


def _kind(label: str) -> str:
    return "Q" if label.startswith("Q") else "H" if label.startswith("H") else "9M" if label.startswith("9M") else "Y"


def relative_guidance_verdict(g: dict, metrics: list[dict]) -> str | None:
    """MET / MISSED for a guidance of exactly the shape "Q1FY27 revenue to surpass Q4FY26 revenue", from memory's two figures of
    the guidance's own metric, same kind of period, same basis (a figure of unknown basis only beside one of unknown basis);
    anything else is None."""
    statement = g.get("statement") or ""
    m = _RELATIVE.match(statement)
    if not m or _NEGATION.search(statement):
        return None
    name = _name(m.group("m1"))
    if _name(m.group("m2")) not in ("", name) or name != _name(g.get("metric")) or "growth" in name:
        return None
    a, b = canonical_period(m.group("a")), canonical_period(m.group("b"))
    if a == b or not (_CANON.fullmatch(a) and _CANON.fullmatch(b)) or _kind(a) != _kind(b):
        return None
    rows = {e["period"]: e for e in metrics if _name(e.get("metric")) == name and e.get("value") is not None and e["period"] in (a, b)
            and (e.get("lab") or {}).get("ok") is not False}
    if len(rows) != 2 or str(rows[a].get("unit")).upper() != str(rows[b].get("unit")).upper():
        return None
    if (_entry_basis(rows[a]) or "").upper() != (_entry_basis(rows[b]) or "").upper():
        return None
    return MET if rows[a]["value"] > rows[b]["value"] else MISSED


# ------------------------------------------------------------------ the sentence cut
_NEG = r"(?:not|never|n't|fail(?:s|ed)?\s+to|unable\s+to|yet\s+to|cannot|without)"
_NEG_BEFORE = re.compile(rf"\b{_NEG}\s+(?:\w+\s+){{0,2}}$", re.I)
_NOUN = r"(?:target|ceiling|cap|limit|floor|minimum|goal|threshold|guidance)"
_OBJ = rf"(?:the|its|our|their)\s+(?:\S+\s+){{0,4}}?{_NOUN}\b"
# a claim is a verb that takes the target itself as its object ("met the 10 lakh t target"), never "achieved 9.63 lakh t against ..."
_ACT = re.compile(rf"\b(?P<v>met|meets?|beat|beats|achieved|achieves|exceed|exceeded|exceeds|surpass|surpassed|surpasses)\s+{_OBJ}", re.I)
_PASS = re.compile(rf"\b{_NOUN}\s+(?:is|was|has\s+been|remains|remained|stays|stayed)\s+(?P<neg>not\s+|never\s+)?"
                   r"(?P<v>met|achieved|beaten|exceeded|surpassed|missed|unmet)\b", re.I)
_MISS_ACT = re.compile(rf"\b(?:missed|misses|(?:fell|falls|fall)\s+short\s+of|short\s+of)\s+{_OBJ}", re.I)
_SIDE = re.compile(r"\b(below|under|above|over)\s+(?:the\s+|its\s+|our\s+)?(?:[^,;]{0,25}?\s)?" + _NOUN + r"\b", re.I)
_MEETS = {"met", "meet", "meets", "beat", "beats", "achieved", "achieves", "beaten"}
_BEYOND = {"exceed", "exceeded", "exceeds", "surpass", "surpassed", "surpasses"}
_FORWARD = re.compile(r"\b(?:expects?|expected|will|would|aims?|aiming|plans?|targets?\s+to|likely|should|to\s+meet|to\s+achieve|"
                      r"next\s+(?:quarter|year)|going\s+forward|guid(?:es|ed|ance)\s+for)\b", re.I)
_OTHER_TIME = re.compile(r"\b(?:last\s+(?:year|quarter)|a\s+(?:year|quarter)\s+(?:ago|earlier)|year[- ]ago|prior|previous|earlier|"
                         r"yoy|qoq|y-o-y|q-o-q)\b", re.I)
_ABBREV = re.compile(r"(?:\bRs|\bapprox|\bNo|\bvs|\bInc|\bLtd|\bPvt|\bCo|\bCorp|\bDr|\bMr|\bMrs|\bMs|\bi\.e|\be\.g|\bSt)\.$", re.I)


def _figures(clause: str) -> set[tuple[str, float]]:
    out = set()
    clause = _spaced(clause)
    for m in re.finditer(_NUM, clause):
        unit = _unit(clause[:m.start()], clause[m.end():])
        if unit:
            value = float(m.group(0).replace(",", ""))
            out.add((unit[0], value if unit[0] == "pct" else value * unit[1]))
    return out


def _has_target_figure(clause: str, j: Judged) -> bool:
    return any(k == j.target.kind and abs(v - j.target.goal) <= 1e-9 + 1e-6 * abs(j.target.goal) for k, v in _figures(clause))


def _claim(clause: str, j: Judged) -> str | None:
    """What the clause says about the target, only in clear words and the way the target runs: MET (met / meets / beat /
    achieved the target; exceeded / surpassed a floor; below a ceiling; above a floor), MISSED (missed / fell short of / did not
    meet the target; exceeded a ceiling; above a ceiling; below a floor), or None (no clear claim, or two)."""
    ceiling = j.target.op in ("<=", "<")
    claims: set[str] = set()

    def flipped(m: re.Match) -> bool:
        return bool(_NEG_BEFORE.search(clause[:m.start()]))

    def of(word: str, negated: bool) -> str | None:
        word = word.lower()
        says = MET if word in _MEETS else (MISSED if ceiling else MET) if word in _BEYOND else MISSED if word in ("missed", "unmet") else None
        return None if says is None else ({MET: MISSED, MISSED: MET}[says] if negated else says)

    for m in _ACT.finditer(clause):
        if (c := of(m.group("v"), flipped(m))):
            claims.add(c)
    for m in _PASS.finditer(clause):
        if (c := of(m.group("v"), bool(m.group("neg")))):
            claims.add(c)
    for m in _MISS_ACT.finditer(clause):
        claims.add(MET if flipped(m) else MISSED)
    for m in _SIDE.finditer(clause):
        below = m.group(1).lower() in ("below", "under")
        says = MET if below == ceiling else MISSED
        claims.add({MET: MISSED, MISSED: MET}[says] if flipped(m) else says)
    return claims.pop() if len(claims) == 1 else None


def _clause_contradicts(clause: str, j: Judged) -> bool:
    if _FORWARD.search(clause) or _OTHER_TIME.search(clause) or not j.spec.rx.search(clause) or not _has_target_figure(clause, j):
        return False
    named = period_labels(clause)
    if any(label != j.period for label in named):
        return False   # "met the 10 lakh t target for FY25": another period's sentence is true
    claim = _claim(clause, j)
    return claim is not None and claim != j.verdict


def _merge(pieces: list[str]) -> list[str]:
    out: list[str] = []
    for p in pieces:
        if out and _ABBREV.search(out[-1]):
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def _sentences(text: str) -> list[str]:
    return _merge(re.split(r"(?<=[.;])\s+", text))


def _clauses(sentence: str) -> list[str]:
    pieces = [re.sub(r"^(?:and|but)\s+", "", c.strip(), flags=re.I) for c in _merge(re.split(r"(?<=[,;])\s+|\s+(?:and|but)\s+", sentence))]
    return [c for c in pieces if c]


def contradicting(sentence: str, j: Judged) -> bool:
    """Some clause of the sentence names this metric and its target figure, looks back, and states the opposite of the code's
    verdict in clear words."""
    return any(_clause_contradicts(c, j) for c in _clauses(sentence or ""))


_DANGLING = re.compile(r"(?:which|who|whom|whose|while|whereas|although|though|that|because|since|when|where|as)\b", re.I)


def _cut(sentence: str, j: Judged) -> tuple[str | None, str | None]:
    """(what is left of the sentence, the cut text): only the contradicting clause when the rest stands alone (three words or
    more) and no kept clause hangs on a cut one ("..., which management called a milestone"), else the whole sentence.
    (sentence, None) when nothing is contradicted."""
    clauses = _clauses(sentence)
    bad = [c for c in clauses if _clause_contradicts(c, j)]
    if not bad:
        return sentence, None
    rest = sentence
    for c in bad:
        rest = rest.replace(c, "", 1)
    edge = r"(?:[\s,;]|\band\b|\bbut\b)+"
    rest = re.sub(rf"^{edge}|{edge}$", "", re.sub(r"\s{2,}", " ", rest), flags=re.I).strip()
    hangs = any(c not in bad and _DANGLING.match(c) and i > 0 and clauses[i - 1] in bad for i, c in enumerate(clauses))
    if len(rest.split()) < 3 or _DANGLING.match(rest) or hangs:
        return None, sentence
    rest = rest[0].upper() + rest[1:]
    return (rest + "." if sentence.rstrip().endswith(".") and not rest.endswith(".") else rest), " ".join(bad)


def verdicts_for(before: dict | None, after: dict, output, filing) -> dict[str, tuple[dict, Judged]]:
    """{watch id: (watch, Judged)} for the watch updates of this filing that code decides MET or MISSED from memory."""
    watch = {w["id"]: w for w in (before or {}).get("watchlist", []) if w.get("created_on", "") < filing.filed_at}
    out: dict[str, tuple[dict, Judged]] = {}
    for u in output.dossier_delta.watch_updates:
        w = watch.get(u.watch_id)
        if w and not not_due(w, filing.filed_at) and (j := judge(w, after.get("financial_metrics", []), filing.filed_at)):
            out[w["id"]] = (w, j)
    return out


def drop_contradicting(card, verdicts: dict[str, tuple[dict, Judged]]) -> list[str]:
    """Cut what the takeaway or a why-it-matters point says against a code verdict (the clause, or the sentence when the rest
    cannot stand alone); returns the change-log notes. A point left empty goes; a headline is only noted. A text nothing is
    cut from is returned as it was."""
    notes: list[str] = []
    for w, j in verdicts.values():
        def keep(text: str | None, where: str) -> str | None:
            if not text:
                return text
            parts, changed = [], False
            for s in _sentences(text):
                left, cut = _cut(s, j)
                if cut is not None:
                    changed = True
                    notes.append(f"{where}: cut \"{cut[:80]}\" (code says the watch \"{w['text'][:50]}\" is {j.verdict.lower()})")
                if left:
                    parts.append(left)
            return " ".join(parts) if changed else text
        card.takeaway = keep(card.takeaway, "takeaway") or ""
        for i in card.why_it_matters:
            i.text = keep(i.text, "why_it_matters") or ""
        if contradicting(card.headline or "", j):
            notes.append(f"headline: \"{card.headline[:80]}\" says the opposite of the code verdict ({j.verdict.lower()}) on \"{w['text'][:50]}\"")
    card.why_it_matters = [i for i in card.why_it_matters if (i.text or "").strip()]
    return notes
