"""Orchestration: discovery, triage, analysis, memory.

A run spends its time budget in two phases:

1. Live: discover today's new filings (and yesterday's, early in the morning),
   then process the live window (the last few days) oldest-first, each
   company's short unanalysed history first.
2. Backfill: discover a few more historical days (from BACKFILL_START, oldest
   first, within the D1 daily write budget; this also closes each finished day
   with one full pass), then analyse the history company by company, largest
   market cap first, on the bulk AI routes.

All state lives in the filings ledger, so a run can stop at any point (time
budget, quota ceiling, crash) and the next run resumes where it left off; each
company's results are committed as soon as it finishes. Filings for one company
are processed sequentially in timestamp order; companies run in parallel.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import re
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import partial
from threading import Lock

from .ai.gateway import AIGateway, AllProvidersFailed
from .bse import AttachmentError, BseClient, SourceBlockedError, XbrlLink
from . import duplicates
from .dossier import (dossier_as_of, latest_fundamentals, memory_ids, merge, new_dossier, reported_by, results_snapshot,
                      view_as_of)
from .extract import Document
from . import gate
from .grounding import DEFAULT_THRESHOLD, check_card, check_claims, margin_issues, scale_issues, unit_slips
from .models import EVENT_TAGS, Filing, Pass1Result, Pass2Output
from .periods import (canonical_period, due_date, prior_quarter_period, prior_year_period, quarter_from_index,
                      quarter_index, statement_quarter, statement_year)
from .prompts.engine import PromptEngine
from .quant import QuantCheck
from .quant import check as check_quant
from .rules import RuleBook
from .settings import Settings
from .forensics import text_signals
from .scoring import score as score_card
from .signals import compute as compute_signals
from .prices import PriceStore, point_in_time
from .signals import priced_for
from .sinks.base import Sink, SinkRejected
from . import universe
from . import xbrl as xbrl_fast_path
from .learning import LESSONS_KEEP, LESSONS_KEY
from .quality import asset_turn_signals, warrant_deadlines
from .radar import summarize as memory_summary
from .signals import volume_strip
from .timeutil import IST, market_session, now_iso, now_ist, today_ist, utc_day

log = logging.getLogger(__name__)

TRANSIENT_WAIT_S = 60
TRANSIENT_RETRIES = 3
BUSY_STOP = 4  # filings in a row left queued because every provider was busy: stop the run, rerun later
BATCH = 40
COMMIT_EVERY = 5         # a company's results are saved this often, so a crash loses at most a few
HISTORY_LIMIT = 200      # one company's filings fetched per page (a year rarely has more)
HISTORY_INLINE = 30      # history analysed ahead of a live filing; a longer backlog goes to the backfill
MAX_ORDER = 20_000       # companies in the cached backfill order
PRICED_FIELDS = ("last_price", "price_date", "market_cap_cr", "size_category", "ret_1w", "ret_1m", "ret_1y",
                 "median_turnover_cr", "point_in_time")
LIVE_DAYS = 7            # an unfinished filing stays in the live window this long
DEADLINE_GRACE_S = 240   # a filing started before the deadline may finish within this
MAX_REFUSALS = 3         # attachment 403s in a row that mean BSE is refusing this network
NOISE_CHUNK = 500        # rows per noise-audit file in R2
NOISE_FIELDS = ("news_id", "scrip_code", "company_name", "headline", "category", "subcategory",
                "filed_at", "reason", "pdf_url")
DONE = ("ANALYZED", "NOT_MATERIAL", "DUPLICATE")  # DUPLICATE: a repeat submission (duplicates.py)
LONG_PROMPT_TOKENS = 12_000
SNAPSHOT_KEY = "daily_feed/latest_snapshot.json"
SNAPSHOT_DAYS = 7         # the feed's default range ("Last 7 days")
SNAPSHOT_PAGE = 50        # the feed's page size


@dataclass
class Stats:
    discovered: int = 0
    dropped_rule: int = 0
    pending_new: int = 0
    pass1_rejected: int = 0
    analyzed: int = 0
    not_material: int = 0
    failed: int = 0
    deferred: int = 0
    cards_high: int = 0
    needs_review: int = 0
    signals: int = 0
    second_opinions: int = 0
    corrected: int = 0
    ocr_pages: int = 0
    d1_rows_written: int = 0
    discovery_errors: int = 0
    outside_universe: int = 0
    xbrl: int = 0           # filings whose figures came from their XBRL file
    duplicates: int = 0     # repeat submissions of an earlier filing's text (no AI call)
    days_discovered: list[str] = field(default_factory=list)
    stopped_reason: str | None = None
    last_error: str | None = None
    status: str = ""

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Outcome:
    update: dict
    card: dict | None = None
    catalysts: list[dict] = field(default_factory=list)
    company: dict | None = None
    committed: bool = False


@dataclass
class CardChecks:
    """Everything the automatic checks found on one card."""

    score: float
    checked: int
    ungrounded: list[str]
    quant: QuantCheck
    claims: list[str]
    headline_ungrounded: list[str] = field(default_factory=list)
    amounts_ungrounded: list[str] = field(default_factory=list)
    scale: list[str] = field(default_factory=list)  # figures out of scale or not fitting their margin
    held: list[str] = field(default_factory=list)   # reasons a second model cannot fix: garbled scan, human hold

    @property
    def needs_review(self) -> bool:
        # Blueprint rule: an unmatched ₹ figure in the headline or a failed math check holds the card;
        # so do a low overall match rate, an unsupported "first"/"record" claim and a figure out of scale.
        return self.fixable or bool(self.held)

    @property
    def fixable(self) -> bool:
        return (self.score < DEFAULT_THRESHOLD or self.quant.mismatches > 0 or bool(self.claims)
                or bool(self.headline_ungrounded) or bool(self.scale))

    @property
    def wants_second_opinion(self) -> bool:
        # Blueprint §4: any ungrounded number sends the card to a second provider. Amounts only: a
        # 10x lakh/crore slip in a key number leaves the overall match rate above the review
        # threshold, while an unmatched percentage is usually a derivation the checks cannot follow.
        return self.fixable or bool(self.amounts_ungrounded)

    @property
    def issue_count(self) -> int:
        return len(self.ungrounded) + self.quant.mismatches + len(self.claims) + len(self.scale)

    def problems(self) -> list[str]:
        out = []
        if self.headline_ungrounded:
            out.append("Headline figures not found in the filing or company memory: " + ", ".join(self.headline_ungrounded))
        if self.ungrounded:
            out.append("Numbers not found in the filing text or company memory: " + ", ".join(self.ungrounded[:10]))
        out += [f"Quantified impact \"{q['label']}\": {q.get('check_note')}" for q in self.quant.items if q.get("check") == "MISMATCH"]
        out += [f"Claim not supported by the sources: \"{c}\"" for c in self.claims]
        out += [f"Figures that do not fit (check the statement's unit and column): {s}" for s in self.scale]
        out += list(self.held)
        return out


_PERIOD_TOKEN = re.compile(r"\b(Q[1-4])\s?(FY)\s?'?(\d{2})\b|\b(FY)\s?'?(\d{2})\b")


def relabel_periods(out: Pass2Output, quarter: str | None, year: str | None) -> dict[str, str]:
    """Correct the model's period labels on a results card from the statement itself. Novartis's
    results for the quarter ended 31 Mar 2025 were labelled Q1FY26 (it is Q4FY25), and memory is keyed
    by period. When the model's main quarter differs from the statement's, every quarter label it used
    is shifted by the same offset (its year-ago and previous quarters were off the same way); a single
    wrong annual label is replaced by the statement's year. Returns the mapping applied."""
    labels = [canonical_period(m.period) for m in out.dossier_delta.financial_metrics]
    quarters = {p for p in labels if quarter_index(p) is not None}
    mapping: dict[str, str] = {}
    offset = 0
    if quarter and quarters:
        model_quarter = max(quarters, key=quarter_index)  # a statement's current period is its latest column
        offset = quarter_index(quarter) - quarter_index(model_quarter)
        if offset:
            mapping = {p: quarter_from_index(quarter_index(p) + offset) for p in quarters}
    years = {p for p in labels if re.fullmatch(r"FY\d{2}", p)}
    if year and len(years) == 1 and year not in years:
        mapping[years.pop()] = year
    if not mapping:
        return mapping

    def fix(text: str | None) -> str | None:
        if not text:
            return text
        def swap(m: re.Match) -> str:
            label = f"{m[1]}FY{m[3]}" if m[1] else f"FY{m[5]}"
            if label in mapping:
                return mapping[label]
            if m[1] and offset:  # a quarter the card names but memory does not (the next results)
                return quarter_from_index(quarter_index(label) + offset)
            return m[0]
        return _PERIOD_TOKEN.sub(swap, text)

    for metric in out.dossier_delta.financial_metrics:
        metric.period = mapping.get(canonical_period(metric.period), metric.period)
    card = out.card
    card.headline = fix(card.headline)
    card.takeaway = fix(card.takeaway) or ""
    card.core_catalyst = fix(card.core_catalyst)
    card.what_happened = [fix(t) for t in card.what_happened]
    for insight in card.why_it_matters:
        insight.text = fix(insight.text)
    for key in card.key_numbers:
        key.label, key.value, key.change = fix(key.label), fix(key.value), fix(key.change)
    for change in card.notable_changes:
        change.previous, change.current = fix(change.previous), fix(change.current)
    for kpi in card.track_next.kpis_to_verify:
        kpi.period, kpi.check_in, kpi.kpi = fix(kpi.period), fix(kpi.check_in), fix(kpi.kpi)
    out.timeline_entry = fix(out.timeline_entry) or ""
    log.info("period labels corrected from the statement: %s", mapping)
    return mapping


def _card_texts(out: Pass2Output) -> list[str]:
    card = out.card
    texts = [card.headline, card.takeaway, card.core_catalyst, *card.what_happened, *(i.text for i in card.why_it_matters),
             *(f"{k.value} {k.change or ''}" for k in card.key_numbers),
             *(f"{c.previous or ''} ; {c.current or ''}" for c in card.notable_changes), out.timeline_entry]
    return [t for t in texts if t]


def fix_unit_slips(out: Pass2Output, sources: tuple[str, ...]) -> dict[str, str]:
    """Correct, in code, card amounts that are a statement figure read at the wrong unit (grounding.
    unit_slips): in the card's text, its key numbers and changes, the timeline entry, and the reply's
    ₹ crore metrics for memory. Returns {as written: corrected}."""
    if out.card is None or not sources:
        return {}
    slips = unit_slips(_card_texts(out), sources[0], *sources[1:])
    if not slips:
        return {}
    mapping = {raw: f"{right:,.{places}f}".rstrip("0").rstrip(".") if places else f"{right:,.0f}"
               for raw, _, _, right, places in slips}
    pattern = re.compile(r"(?<![\d.,])(" + "|".join(re.escape(r) for r in sorted(mapping, key=len, reverse=True))
                         + r")(?=\s*(?:cr\b|crores?\b))", re.I)

    def fix(text: str | None) -> str | None:
        return pattern.sub(lambda m: mapping[m.group(1)], text) if text else text

    card = out.card
    card.headline, card.takeaway, card.core_catalyst = fix(card.headline), fix(card.takeaway) or "", fix(card.core_catalyst)
    card.what_happened = [fix(t) for t in card.what_happened]
    for insight in card.why_it_matters:
        insight.text = fix(insight.text)
    for key in card.key_numbers:
        key.value, key.change = fix(key.value), fix(key.change)
    for change in card.notable_changes:
        change.previous, change.current = fix(change.previous), fix(change.current)
    out.timeline_entry = fix(out.timeline_entry) or ""
    for m in out.dossier_delta.financial_metrics:
        if m.value is None or (m.unit or "INR_CR") != "INR_CR":
            continue
        for _, value, decimals, right, _ in slips:
            if abs(abs(float(m.value)) - value) <= 0.5 * 10 ** (-decimals) + 1e-9:
                m.value = right if float(m.value) >= 0 else -right
                break
    log.info("unit slips corrected in code: %s", mapping)
    return mapping


_CHANGE_AMOUNT = re.compile(r"(?<![\w.])(\(?-?\d[\d,]*(?:\.\d+)?\)?)")
_CHANGE_PCT = re.compile(r"([+\-−]?)\s*(\d+(?:\.\d+)?)\s*%")


def _amount(text: str | None) -> float | None:
    m = _CHANGE_AMOUNT.search(re.sub(r"\b(?:Q[1-4]|H[12]|9M)?FY\s?'?\d{2,4}\b|\b(?:19|20)\d{2}\b", " ", text or ""))
    if not m:
        return None
    raw = m.group(1)
    try:
        value = float(raw.strip("-()").replace(",", ""))
    except ValueError:
        return None
    return -value if raw.startswith(("-", "(")) else value


def fix_change_percentages(out: Pass2Output) -> list[str]:
    """A notable change whose % does not follow from its own two figures ("₹494 Cr → ₹418 Cr, +15% YoY",
    a 15% fall) gets the computed % in code. Only amounts on both sides, neither a percentage."""
    fixed = []
    for change in out.card.notable_changes if out.card else []:
        before, after, stated = change.previous or "", change.current or "", change.change or ""
        m = _CHANGE_PCT.search(stated)
        if not m or "%" in before or "%" in after:
            continue
        a, b = _amount(before), _amount(after)
        if a is None or b is None or a == 0:
            continue
        real = (b - a) / abs(a) * 100
        claimed = float(m.group(2)) * (-1 if m.group(1) in ("-", "−") else 1)
        if not m.group(1) and re.search(r"\b(?:down|fell|lower|decline)", stated, re.I):
            claimed = -claimed
        if abs(claimed - real) <= max(1.0, abs(real) * 0.05):
            continue
        new = f"{real:+.1f}%".replace(".0%", "%")
        change.change = stated[:m.start()] + new + stated[m.end():]
        if change.direction in ("positive", "negative") and (real > 0) != (claimed > 0):
            change.direction = "negative" if change.direction == "positive" else "positive"
        fixed.append(f"{change.metric}: {stated} -> {change.change}")
    if fixed:
        log.info("change percentages corrected in code: %s", fixed)
    return fixed


_KEY_METRIC = (("ebitda", re.compile(r"\bebitda\b(?!.*margin)", re.I)),
               ("pbt", re.compile(r"\bpbt\b|profit before tax", re.I)),
               ("pat", re.compile(r"\bpat\b|net profit|profit after tax|net income", re.I)),
               ("eps", re.compile(r"\beps\b|earnings per share", re.I)),
               ("revenue", re.compile(r"revenue|net sales|income from operations|\bsales\b", re.I)))


def xbrl_key_numbers(out: Pass2Output, tagged: "xbrl_fast_path.XbrlResult") -> list[str]:
    """A results card's key numbers for revenue, EBITDA, PBT, PAT and EPS set from the XBRL file: exact
    value and YoY (SML's "revenue -40% YoY" was the fall from the previous quarter; its "EBITDA ₹0.75 Cr"
    was PBT). Only on the card's own basis and quarter. Returns what changed."""
    if out.card is None or tagged.kind != "RESULTS" or not tagged.period:
        return []
    if out.card.basis and tagged.basis and out.card.basis != tagged.basis:
        return []
    now = {m.metric: m for m in tagged.metrics if m.period == tagged.period}
    changed = []
    for key in out.card.key_numbers:
        if "margin" in (key.label or "").lower() or "%" in (key.value or ""):
            continue
        metric = next((name for name, pattern in _KEY_METRIC if pattern.search(key.label or "")), None)
        m = now.get(metric) if metric else None
        if m is None or m.value is None:
            continue
        value = f"₹{m.value:,.2f}" + (" per share" if metric == "eps" else " Cr")
        change = f"{m.yoy_pct:+.1f}% YoY" if m.yoy_pct is not None else key.change
        if (key.value, key.change) != (value, change):
            changed.append(f"{key.label}: {key.value} ({key.change}) -> {value} ({change})")
            key.value, key.change = value, change
    if changed:
        log.info("key numbers set from XBRL: %s", changed)
    return changed


_PCT_LABELLED = re.compile(r"([+\-−]?\d+(?:\.\d+)?)\s*%\s*(?:\(?\s*)(YoY|QoQ|y-o-y|q-o-q|year[- ]on[- ]year|quarter[- ]on[- ]quarter)", re.I)


def period_mixups(out: Pass2Output, tagged: "xbrl_fast_path.XbrlResult | None") -> list[str]:
    """A "% YoY" on the card that is the quarter-on-quarter change of a tagged figure (and no figure's
    YoY), or the reverse: SML's results cards called the fall from Q2 a fall from a year ago."""
    if out.card is None or tagged is None or tagged.kind != "RESULTS":
        return []
    now = [m for m in tagged.metrics if m.period == tagged.period and m.unit != "PCT"]
    yoy = [abs(m.yoy_pct) for m in now if m.yoy_pct is not None]
    qoq = [abs(m.qoq_pct) for m in now if m.qoq_pct is not None]
    issues = []
    for text in _card_texts(out):
        for m in _PCT_LABELLED.finditer(text):
            value, label = abs(float(m.group(1).replace("−", "-"))), m.group(2).lower()
            near = lambda xs: any(abs(x - value) <= 0.6 for x in xs)  # noqa: E731
            is_yoy = label.startswith(("yoy", "y-o-y", "year"))
            if is_yoy and near(qoq) and not near(yoy):
                issues.append(f"\"{m.group(0)}\" is a quarter-on-quarter change, not year-on-year")
            elif not is_yoy and near(yoy) and not near(qoq):
                issues.append(f"\"{m.group(0)}\" is a year-on-year change, not quarter-on-quarter")
    return list(dict.fromkeys(issues))


_RESULTS_STATEMENT = re.compile(r"statement of (?:standalone |consolidated )?(?:un-?)?audited\b.{0,80}?financial results", re.I | re.S)
_TAKEOVER = re.compile(r"open offer|substantial acquisition of shares|\bSAST\b|regulation 3\(1\)|regulation 4\b", re.I)
_PROMOTER_DISCLOSURE = re.compile(r"regulation 29\b|reg\.? ?29\b|regulation 31\b|inter ?se transfer|\bgift(?:ed)?\b", re.I)
_TAX_OR_PENALTY = re.compile(r"\b(?:demand|penalty|show[- ]cause|assessment order|tax order|adjudication|"
                             r"(?:income[- ]tax|GST|CGST|service tax|customs) (?:order|notice|demand|authorit))", re.I)  # "excluding GST" is an order
_REAL_ORDER = re.compile(r"letter of (?:award|intent)|\bLoA\b|\bLoI\b|work order|purchase order|order (?:received|bagged|secured|worth)|"
                         r"contract (?:awarded|worth|valued)|lowest bidder|\bL1\b", re.I)


def event_type_rules(event_type: str, filing: Filing, text: str, tagged) -> str:
    """Event types the model got wrong in the smoke-test audit, settled from the filing itself:
    results statements typed OTHER (board outcomes carrying the results); an open offer typed as a
    rights issue or fundraise (no new shares); a promoter's Reg 29 gift typed M&A; a tax demand or
    penalty typed as an order win."""
    head = f"{filing.headline} {filing.subject} {text[:3000]}"
    if event_type in ("OTHER", "GOVERNANCE", "CORPORATE_ACTION") and (
            (tagged is not None and tagged.kind == "RESULTS") or _RESULTS_STATEMENT.search(text[:20000])):
        return "RESULTS"
    if event_type in ("RIGHTS_ISSUE", "FUNDRAISE") and _TAKEOVER.search(head):
        return "M_AND_A"
    if event_type == "M_AND_A" and _PROMOTER_DISCLOSURE.search(head) and not _TAKEOVER.search(head):
        return "GOVERNANCE"
    if event_type == "ORDER_WIN" and _TAX_OR_PENALTY.search(head) and not _REAL_ORDER.search(head):
        return "LITIGATION_REGULATORY"
    return event_type


def gate_issues(out: Pass2Output, card) -> list[str]:
    """Amounts that cannot be crore, and a fundraise whose size does not follow from its shares and price."""
    issues = [f"{n} Cr is not a crore figure (a rupee amount written in full)" for n in gate.impossible_crore_amounts(_card_texts(out))]
    deal = card.deal_value
    if deal and deal.kind == "FUNDRAISE":
        for action in out.dossier_delta.capital_actions:
            problem = gate.issue_size_mismatch(deal.amount_cr, action.new_shares, action.issue_price)
            if problem:
                issues.append(problem)
    return issues


def apply_deal_guards(out: Pass2Output, filing: Filing, history: list[dict], balance_sheet: list[dict]) -> list[str]:
    """A deal size that is the company's own revenue, net worth or share capital is dropped; a terminated
    or withdrawn deal is marked CANCELLED. Returns what was done."""
    deal = out.card.deal_value if out.card else None
    if deal is None:
        return []
    notes = []
    known = {"financial_metrics": history + [m.model_dump() for m in out.dossier_delta.financial_metrics],
             "balance_sheet": balance_sheet}
    name = gate.deal_is_company_figure(deal.amount_cr, known)
    if name:
        notes.append(f"deal size {deal.amount_cr:g} Cr dropped: it is the company's {name}")
        out.card.deal_value = None
        deal = None
    if deal is not None and deal.stage != "CANCELLED" and gate.is_terminated(filing.headline, filing.subject):
        notes.append("deal marked cancelled: the filing terminates or withdraws it")
        deal.stage = "CANCELLED"
    if notes:
        log.info("deal guards for %s: %s", filing.news_id, notes)
    return notes


def check_card_all(out: Pass2Output, view: dict | None, sources: tuple[str, ...], history: list[dict] | None = None) -> CardChecks:
    """Memory-id hygiene, then the number, math, claim and scale checks (`history`: the dossier's
    stored financial metrics, which the reply's quarterly figures are compared with)."""
    card = out.card
    valid_refs = memory_ids(view)
    for insight in card.why_it_matters:
        insight.memory_refs = [r for r in insight.memory_refs if r in valid_refs]
    if card.deal_value and card.deal_value.updates_deal_id not in valid_refs:
        card.deal_value.updates_deal_id = None  # only a deal the model was shown can be updated
    reconcile_call_read(card, view)
    grounding = check_card(card, *sources)
    quant = check_quant(card.quantified_impact, *sources)
    checked = grounding.checked + quant.checked_inputs
    ungrounded = grounding.ungrounded + quant.unsourced
    score = 1.0 if checked == 0 else round(1 - len(ungrounded) / checked, 3)
    return CardChecks(score, checked, ungrounded, quant, check_claims(card, *sources),
                      grounding.headline_ungrounded, grounding.amounts_ungrounded,
                      scale_issues(out.dossier_delta.financial_metrics, history or [])
                      + margin_issues(out.dossier_delta.financial_metrics, card.key_numbers)
                      + gate_issues(out, card))


def reconcile_call_read(card, view: dict | None) -> None:
    """"Guidance raised / lowered / maintained" needs earlier guidance in memory to compare with."""
    if card.call_read and card.call_read.guidance in ("RAISED", "LOWERED", "MAINTAINED") and not (view or {}).get("guidance"):
        card.call_read.guidance = "NEW"


def _catalyst_id(scrip: str, event_type: str, event_date: str) -> str:
    return hashlib.sha1(f"{scrip}|{event_type}|{event_date}".encode()).hexdigest()[:16]


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        sink: Sink,
        gateway: AIGateway,
        bse: BseClient | None = None,
        prompts: PromptEngine | None = None,
        rules: RuleBook | None = None,
        sleep=time.sleep,
    ):
        self.settings = settings
        self.sink = sink
        self._prices = PriceStore(settings.price_dir) if settings.price_dir and settings.price_dir.is_dir() else None
        self._buckets = settings.load_toml("market.toml")["size_buckets"]
        self.gateway = gateway
        self.bse = bse or BseClient()
        self.prompts = prompts or PromptEngine(settings)
        self.rules = rules or RuleBook.from_config(settings.load_toml("taxonomy.toml"))
        self.stats = Stats()
        self._sleep = sleep
        self._lock = Lock()
        self._usage_flushed: dict[tuple[str, str], dict] = {}
        self._exhausted: set[str] = set()   # AI routes whose quota ceilings were reached this run
        self._tried: set[str] = set()       # filings attempted this run (one attempt each)
        self._priority: list[str] = []      # live companies whose history should be backfilled first
        self._refusals = 0
        self._busy = 0
        self._busy_halt = False
        self._blocked: SourceBlockedError | None = None
        self._usage_lock = Lock()
        self._commit_lock = Lock()  # companies commit from worker threads; the R2 day archive is read-modify-write
        self._universe: tuple[set[str], float] | None = None
        self._examples: dict[tuple[str, str], dict[str, list[dict]]] = {}
        self._learned: dict | None = None   # Loop 1 state: post-mortem queue, lessons, dampened categories
        self._bodies: dict[str, list[tuple[str, str, duplicates.Body]]] = {}  # scrip -> (filed_at, news_id, body) this run
        self._xbrl_links: dict[str, list[XbrlLink]] = {}  # scrip -> its results archive, read once a run
        self._holds = gate.load_holds(settings.config_dir / settings.card_holds_file)  # news_id -> reason
        self._results_quarters: dict[tuple[str, str], str] = {}  # (scrip, quarter) -> the results filing with its card (D20)

    # ------------------------------------------------------------------ writes

    def _exec(self, statement: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        written = self.sink.execute(statement, rows)
        with self._lock:
            self.stats.d1_rows_written += written
        return written

    def _flush_usage(self) -> None:
        """Send usage deltas since the last flush, so a crash loses little."""
        rows, flushed = [], {}
        with self._usage_lock:  # not self._lock: _exec takes that one
            for row in self.gateway.usage_rows(utc_day(), now_iso()):
                key = (row["provider"], row["model"])
                prev = self._usage_flushed.get(key, {})
                delta = dict(row)
                for counter in ("requests", "input_tokens", "output_tokens", "failures", "rate_limited"):
                    delta[counter] = row[counter] - prev.get(counter, 0)
                if any(delta[c] for c in ("requests", "failures", "rate_limited")):
                    rows.append(delta)
                flushed[key] = row
            self._exec("usage_add", rows)
            self._usage_flushed.update(flushed)  # only once the write went through

    # ------------------------------------------------------------------ discovery

    def discover(self, day: date, full: bool = True) -> int:
        """Fetch one day's announcements, triage them by rules, and record what is new.

        Filings the rules drop (about 70% of all filings) are kept for the noise audit as one R2
        file per day, not as ledger rows: a ledger row costs several D1 writes and every row grows
        the database toward its 500 MB free-tier cap. With ``full=False`` paging stops at the first
        page holding nothing new, so the frequent runs over today ask BSE for a page or two.
        Returns how many filings were new.
        """
        key = day.isoformat()
        noise = self._load_noise(key)
        known = self.sink.known_ids(key) | set(noise)
        filings = self.bse.announcements(day, known=None if full else known)
        count = self._record(key, filings, noise, known)
        self.stats.days_discovered.append(key)
        return count

    def discover_company(self, scrip: str, day_from: date, day_to: date) -> int:
        """Discover one company's filings over a date range (the smoke test, a watchlist add)."""
        found, start = 0, day_from
        while start <= day_to:
            end = min(day_to, start + timedelta(days=30))  # a month per request keeps pages short
            by_day: dict[str, list[Filing]] = {}
            for filing in self.bse.announcements(start, end, scrip=scrip):
                by_day.setdefault(filing.filing_date, []).append(filing)
            for key, filings in sorted(by_day.items()):
                noise = self._load_noise(key)
                found += self._record(key, filings, noise, self.sink.known_ids(key) | set(noise))
            start = end + timedelta(days=1)
        return found

    def _record(self, key: str, filings, noise: dict[str, list], known: set[str]) -> int:
        """Triage new filings of one day: noise to the day's R2 file, the rest to the ledger queue."""
        now = now_iso()
        today = today_ist().isoformat()
        noise_before = len(noise)
        ledger, catalysts, companies = [], [], {}
        for filing in filings:
            if filing.news_id in known:
                continue
            known.add(filing.news_id)
            decision = self.rules.classify(filing)
            filing.reason = decision.reason
            if decision.action == "XBRL" and not filing.xbrl_url:
                filing.reason = f"{decision.reason} (no XBRL file)"
            if decision.action in ("DROP", "CALENDAR") or (decision.action == "XBRL" and not filing.xbrl_url):
                self.stats.dropped_rule += 1
                noise[filing.news_id] = _noise_row(filing)
                if decision.catalyst_date and decision.catalyst_date >= today:
                    catalysts.append({
                        "id": _catalyst_id(filing.scrip_code, decision.event_type or "BOARD_MEETING", decision.catalyst_date),
                        "scrip_code": filing.scrip_code, "company_name": filing.company_name, "symbol": filing.symbol,
                        "event_type": decision.event_type or "BOARD_MEETING", "event_date": decision.catalyst_date,
                        "description": filing.headline[:300], "source_news_id": filing.news_id, "created_at": now,
                    })
                continue
            if filing.scrip_code in self._excluded():
                self.stats.outside_universe += 1
                filing.reason = f"outside universe (market cap below ₹{self._universe[1]:g} Cr)"
                noise[filing.news_id] = _noise_row(filing)
                continue
            filing.status, filing.route, filing.event_type = "PENDING", decision.action, decision.event_type
            self.stats.pending_new += 1
            ledger.append(filing.ledger_row(now))
            companies[filing.scrip_code] = {
                "scrip_code": filing.scrip_code, "company_name": filing.company_name,
                "symbol": filing.symbol, "updated_at": now,
            }
        new_noise = len(noise) - noise_before
        self.stats.discovered += len(ledger) + new_noise
        self._exec("companies_seen", list(companies.values()))
        self._exec("filings_discover", ledger)
        self._exec("catalysts_upsert", catalysts)
        if new_noise:
            self._save_noise(key, noise)
        log.info("discovered %s: %d new filings (%d queued, %d noise)", key, len(ledger) + new_noise, len(ledger), new_noise)
        return len(ledger) + new_noise

    def _excluded(self) -> set[str]:
        """Companies outside the investable universe (loaded once per run; see universe.py)."""
        if self._universe is None:
            self._universe = universe.load(self.sink) if self.settings.universe_min_mcap_cr > 0 else (set(), 0.0)
        return self._universe[0]

    def _load_noise(self, day: str) -> dict[str, list]:
        count = self._noise_count(day)
        rows: dict[str, list] = {}
        for i in range((count + NOISE_CHUNK - 1) // NOISE_CHUNK):
            body = self.sink.get_object(_noise_key(day, i))
            for row in (json.loads(body).get("rows", []) if body else []):
                rows[row[0]] = row
        return rows

    def _noise_count(self, day: str) -> int:
        try:
            return int(self.sink.kv_get(f"noise_count:{day}") or 0)
        except ValueError:
            return 0

    def _save_noise(self, day: str, noise: dict[str, list]) -> None:
        """Newest first, in chunks the Worker can parse within its CPU limit. The count goes last, so a
        reader never looks for a chunk that has not been written yet."""
        rows = sorted(noise.values(), key=lambda r: (r[6] or "", r[0]), reverse=True)
        for i, start in enumerate(range(0, len(rows), NOISE_CHUNK)):
            body = {"fields": NOISE_FIELDS, "rows": rows[start:start + NOISE_CHUNK]}
            self.sink.put_object(_noise_key(day, i), json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode())
        self._kv_set(f"noise_count:{day}", str(len(rows)))

    def _discover_safely(self, day: date, full: bool) -> int | None:
        """One day's discovery; a failure (BSE timeout, an error page) is logged and the run goes on."""
        try:
            return self.discover(day, full=full)
        except SourceBlockedError:
            raise
        except Exception as exc:
            log.exception("discovery of %s failed", day)
            with self._lock:
                self.stats.discovery_errors += 1
                self.stats.last_error = f"discovery {day}: {type(exc).__name__}: {exc}"[:300]
            return None

    # ------------------------------------------------------------------ processing

    def process(self, day_from: str, day_to: str, deadline: float, bulk: bool, memory_complete: bool = True,
                history_first: bool = False) -> None:
        """Work the queue for a date window, oldest first, companies in parallel.

        With ``history_first`` (the live window), a company's unanalysed history is processed before
        its new filing, so the live card is written with that company's memory. Companies with
        little history go first, and each company's results are committed as soon as it finishes.
        """
        after = ("", "")
        while time.monotonic() < deadline and not self._halted(bulk):
            rows = self.sink.pending_filings(day_from, day_to, self.settings.max_attempts, BATCH, after)
            if not rows:
                return
            after = (rows[-1]["filed_at"], rows[-1]["news_id"])
            groups: OrderedDict[str, list[Filing]] = OrderedDict()
            for row in rows:
                if row["news_id"] not in self._tried:
                    groups.setdefault(row["scrip_code"], []).append(Filing.model_validate(row))
            if history_first:
                jobs = self._live_jobs(groups, day_from, deadline, bulk, memory_complete)
            else:
                jobs = {s: partial(self._process_group, g, deadline, bulk, memory_complete) for s, g in groups.items()}
            self._run_parallel(jobs)

    def _live_jobs(self, groups: dict[str, list[Filing]], window_start: str, deadline: float, bulk: bool,
                   memory_complete: bool) -> dict:
        """For each live company: its pending history (if short) and then its new filings.

        A company with a long backlog would hold every other live filing up for hours, so its live
        filing is analysed straight away (marked "memory still building") and the company moves to
        the front of the backfill, which then completes its memory company-first.
        """
        history_to = (date.fromisoformat(window_start) - timedelta(days=1)).isoformat()
        through = self.sink.kv_get("backfill:discovered_through") or ""
        plans = []
        for scrip, filings in groups.items():
            rows = self.sink.pending_for_company(scrip, self.settings.backfill_start, history_to,
                                                 self.settings.max_attempts, HISTORY_INLINE + 1)
            history = [f for f in (Filing.model_validate(r) for r in rows) if f.news_id not in self._tried]
            plans.append((len(history), scrip, filings, history))
        plans.sort(key=lambda p: p[0])
        jobs = {}
        for size, scrip, filings, history in plans:
            if size > HISTORY_INLINE:
                self._priority.append(scrip)
                jobs[scrip] = partial(self._process_group, filings, deadline, bulk, False)
            else:
                jobs[scrip] = partial(self._history_then, filings, history, deadline, bulk,
                                      memory_complete or through >= history_to)
        return jobs

    def _history_then(self, filings: list[Filing], history: list[Filing], deadline: float, bulk: bool,
                      discovered: bool) -> list[Outcome]:
        results = self._process_group(history, deadline, bulk=True, memory_complete=True)
        finished = len(results) == len(history) and all(o.update.get("status") in DONE for o in results)
        return results + self._process_group(filings, deadline, bulk, discovered and finished)

    def _run_parallel(self, jobs: dict) -> dict[str, list[Outcome]]:
        """Run one job per company in parallel. Each company commits every COMMIT_EVERY results as
        it goes and the rest when it finishes, so a timeout or a crash loses at most a few filings."""
        done: dict[str, list[Outcome]] = {}
        if not jobs:
            return done
        with ThreadPoolExecutor(max_workers=max(1, self.settings.workers)) as pool:
            futures = {pool.submit(job): key for key, job in jobs.items()}
            for future in as_completed(futures):
                outcomes = future.result()
                done[futures[future]] = outcomes
                self._commit([o for o in outcomes if not o.committed])
        if self._blocked:
            raise self._blocked
        return done

    def _process_group(self, filings: list[Filing], deadline: float, bulk: bool, memory_complete: bool) -> list[Outcome]:
        results = []
        for filing in sorted(filings, key=lambda f: f.filed_at):
            if time.monotonic() >= deadline or self._halted(bulk) or self._blocked:
                break
            with self._lock:
                if filing.news_id in self._tried:  # one attempt per filing per run
                    continue
                self._tried.add(filing.news_id)
            results.append(self._process_one(filing, bulk, memory_complete, deadline))
            unsaved = [o for o in results if not o.committed]
            if len(unsaved) >= COMMIT_EVERY:
                self._commit(unsaved)
                for o in unsaved:
                    o.committed = True
        return results

    def _halted(self, bulk: bool) -> bool:
        """The analyst route for this phase has hit its quota ceilings: work stays queued."""
        return self._busy_halt or ("pass2_bulk" if bulk else "pass2") in self._exhausted

    def _process_one(self, filing: Filing, bulk: bool, memory_complete: bool, deadline: float | None = None) -> Outcome:
        pass1 = "pass1_bulk" if bulk else "pass1"
        if filing.route == "PASS1" and pass1 in self._exhausted:
            return self._deferred(filing, "deferred: AI quota ceilings")
        for attempt in range(TRANSIENT_RETRIES + 1):
            try:
                outcome = self.analyze(filing, bulk, memory_complete)
                with self._lock:
                    self._busy = 0
                return outcome
            except AllProvidersFailed as exc:
                if exc.quota_exhausted:
                    with self._lock:
                        self._exhausted.add(exc.route)
                        self.stats.stopped_reason = f"AI quota ceilings reached ({exc.route}); work stays queued"
                    log.warning("quota ceilings reached on %s; leaving %s queued: %s", exc.route, filing.news_id, exc)
                    return self._deferred(filing, "deferred: AI quota ceilings")
                waited_out = deadline is not None and time.monotonic() + TRANSIENT_WAIT_S >= deadline
                if exc.transient and attempt < TRANSIENT_RETRIES and not waited_out:
                    log.info("all providers busy for %s; waiting %ds", filing.news_id, TRANSIENT_WAIT_S)
                    self._sleep(TRANSIENT_WAIT_S)
                    continue
                if exc.transient:
                    with self._lock:
                        self._busy += 1
                        if self._busy >= BUSY_STOP and not self._busy_halt:
                            self._busy_halt = True
                            self.stats.stopped_reason = (f"every AI provider busy or failing for {self._busy} filings in a row; "
                                                         "work stays queued, rerun later")
                            log.warning("stopping: %s", self.stats.stopped_reason)
                    return self._deferred(filing, "deferred: providers busy")
                return self._failed(filing, exc)
            except AttachmentError as exc:
                if exc.refused:
                    with self._lock:
                        self._refusals += 1
                        if self._refusals >= MAX_REFUSALS and not self._blocked:
                            self._blocked = SourceBlockedError(
                                f"BSE refused {self._refusals} attachment downloads in a row; stopping this run")
                return self._failed(filing, exc)
            except Exception as exc:  # one bad filing must not stop the run
                log.exception("filing %s failed", filing.news_id)
                return self._failed(filing, exc)
        return self._failed(filing, RuntimeError("retries exhausted"))

    def _deferred(self, filing: Filing, reason: str) -> Outcome:
        with self._lock:
            self.stats.deferred += 1
        return Outcome({"news_id": filing.news_id, "status": "PENDING", "updated_at": now_iso(), "last_error": reason})

    def _failed(self, filing: Filing, exc: Exception) -> Outcome:
        with self._lock:
            self.stats.failed += 1
        # The attempt count is sent as a value, not an increment, so a retried write cannot count twice.
        return Outcome({"news_id": filing.news_id, "status": "FAILED", "attempts": filing.attempts + 1,
                        "last_error": f"{type(exc).__name__}: {exc}"[:500], "updated_at": now_iso()})

    def analyze(self, filing: Filing, bulk: bool = False, memory_complete: bool = True) -> Outcome:
        """Run Pass 1 (if needed), extraction, Pass 2, grounding, merge and signals for one filing."""
        company = self.sink.company(filing.scrip_code) or {}
        if filing.route == "XBRL":
            return self._xbrl_memory(filing, company)
        industry = company.get("industry")
        ocr = self.gateway.transcribe_image if self.gateway.has_route("vision") else None
        cached = self._cached_text(filing.news_id)
        if cached is not None:
            doc = Document.from_cache(cached, ocr=ocr, max_ocr_pages=self.settings.max_ocr_pages)
        else:
            pdf = self.bse.download(filing.pdf_url) if filing.pdf_url else None
            self._refusals = 0
            doc = Document(pdf, ocr=ocr, max_ocr_pages=self.settings.max_ocr_pages)
        try:
            repeat = self._duplicate_of(filing, doc)
            if repeat:
                with self._lock:
                    self.stats.duplicates += 1
                return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": filing.event_type,
                                "reason": f"duplicate of {repeat[0]} ({repeat[1]} match)", "updated_at": now_iso()})
            return self._analyze_document(filing, company, industry, doc, bulk, memory_complete)
        finally:
            with self._lock:
                self.stats.ocr_pages += doc.ocr_pages_used
            if doc.ocr_error is None:
                self._cache_text(filing.news_id, doc)
            doc.close()

    def _duplicate_of(self, filing: Filing, doc: Document) -> tuple[str, str] | None:
        """(news_id, "exact" | "near") of an earlier filing by the same company, within
        duplicates.DAYS, that this one repeats (see duplicates.py); None when there is none.
        Filings of this run are registered before they are analysed, so parallel workers cannot both
        analyse one event. Corrections are never duplicates."""
        if duplicates.is_correction(filing.headline, filing.subject):
            return None
        mine = duplicates.body(doc.select_text(duplicates.CHARS))
        if not mine.matchable:
            return None
        since = (datetime.fromisoformat(filing.filed_at) - timedelta(days=duplicates.DAYS)).isoformat()
        earlier = lambda at, news_id: since <= at < filing.filed_at or (at == filing.filed_at and news_id < filing.news_id)
        with self._lock:
            seen = list(self._bodies.get(filing.scrip_code, []))
            self._bodies.setdefault(filing.scrip_code, []).append((filing.filed_at, filing.news_id, mine))
        candidates = [(n, b) for at, n, b in seen if earlier(at, n)]
        known = {n for _, n, _ in seen}
        for row in self.sink.query("filings_recent_company", [filing.scrip_code, since, filing.filed_at, 20]):
            if row["news_id"] in known or row["news_id"] == filing.news_id:
                continue
            cached = self._cached_text(row["news_id"])
            if cached is not None:
                candidates.append((row["news_id"], duplicates.body(Document.from_cache(cached).select_text(duplicates.CHARS))))
        for news_id, theirs in candidates:
            kind = duplicates.match(mine, theirs)
            if kind:
                log.info("%s repeats %s (%s match, same company)", filing.news_id, news_id, kind)
                return news_id, kind
        return None

    def _results_xbrl_url(self, filing: Filing, text: str) -> str | None:
        """The XBRL file for a results filing, from the company's results archive: the statement's
        quarter, consolidated when the company files it (memory keeps one basis), the latest file
        (revision) filed within 45 days of the PDF, else the earliest. Without a stated quarter, the
        file filed within three days of the PDF. Announcement rows carry no XBRL link of their own."""
        with self._lock:
            links = self._xbrl_links.get(filing.scrip_code)
        if links is None:
            try:
                links = self.bse.results_xbrl(filing.scrip_code)
            except Exception as exc:  # XBRL is an extra: the PDF still carries the results
                log.warning("results archive for %s unavailable (%s); using the PDF", filing.scrip_code, exc)
                links = []
            with self._lock:
                self._xbrl_links[filing.scrip_code] = links
        if not links:
            return None
        quarter = statement_quarter(text)
        if quarter:
            links = [link for link in links if link.period == quarter]
        else:
            day = date.fromisoformat(filing.filed_at[:10])
            links = [link for link in links if -1 <= (date.fromisoformat(link.filed_at[:10]) - day).days <= 3]
        if any(link.basis == "CONSOLIDATED" for link in links):
            links = [link for link in links if link.basis == "CONSOLIDATED"]
        day = date.fromisoformat(filing.filed_at[:10])
        timely = [link for link in links if -2 <= (date.fromisoformat(link.filed_at[:10]) - day).days <= 45]
        if timely:
            return max(timely, key=lambda link: link.filed_at).url
        return min(links, key=lambda link: link.filed_at).url if links else None

    def _held_reasons(self, filing: Filing, text: str) -> list[str]:
        """Reasons the card is published as unverified that no second model can fix: a scan whose text layer
        is garbled (its table figures may be wrong), and the human hold list (config/card_holds.txt)."""
        held = []
        if gate.text_is_garbled(text):
            held.append("The filing's text layer is garbled (scan errors inside numbers): figures from its tables may be wrong")
        if filing.news_id in self._holds:
            held.append(f"Held after review: {self._holds[filing.news_id]}")
        return held

    def _same_results_quarter(self, filing: Filing, dossier: dict, quarter: str | None) -> tuple[str, str] | None:
        """(news_id, quarter) of the results filing that already has this company's card for the quarter
        (decision D20: one card per company per results quarter; the others are linked to it). Novartis
        filed one quarter's results as three documents, Ahluwalia as a board outcome and a later meeting
        update. From memory (a RESULTS timeline entry whose filing reported the quarter's figures) and
        from this run's own claims, so parallel workers cannot both take the quarter."""
        if not quarter or quarter_index(quarter) is None:
            return None
        key = (filing.scrip_code, quarter)
        with self._lock:
            claimed = self._results_quarters.get(key)
            if claimed and claimed != filing.news_id:
                return claimed, quarter
            done = {t["news_id"] for t in dossier.get("timeline", [])
                    if t.get("event_type") == "RESULTS" and t.get("date", "") < filing.filed_at and t.get("news_id") != filing.news_id}
            for m in dossier.get("financial_metrics", []):
                if m.get("period") == quarter:
                    owner = next((n for n in done if reported_by(m, n)), None)
                    if owner:
                        return owner, quarter
            self._results_quarters[key] = filing.news_id
        return None

    def _xbrl_comparatives(self, filing: Filing, tagged: "xbrl_fast_path.XbrlResult") -> None:
        """Year-ago and previous-quarter figures for a results file, from those quarters' files in the
        company's results archive (cached by URL). Best effort: a missing file leaves the change out."""
        if tagged.kind != "RESULTS" or not tagged.period or not tagged.period.startswith("Q"):
            return
        with self._lock:
            links = self._xbrl_links.get(filing.scrip_code) or []
        earlier = []
        for period in {prior_year_period(tagged.period), prior_quarter_period(tagged.period)} - {None}:
            same = [link for link in links if link.period == period and link.basis == (tagged.basis or link.basis)]
            if not same:
                continue
            data = self._xbrl_file(max(same, key=lambda link: link.filed_at).url)
            parsed = xbrl_fast_path.parse(data) if data else None
            if parsed:
                earlier.append(parsed)
        if earlier:
            xbrl_fast_path.add_comparatives(tagged, *earlier)

    def _xbrl_file(self, url: str) -> bytes | None:
        """An XBRL file by URL, cached under the text cache's xbrl folder."""
        root = self.settings.text_cache_dir
        path = root / "xbrl" / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".xml.gz") if root else None
        if path and path.exists():
            try:
                return gzip.decompress(path.read_bytes())
            except OSError:
                pass
        try:
            data = self.bse.download(url, max_bytes=8_000_000)
        except AttachmentError:
            return None
        if data and path:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(gzip.compress(data))
            except OSError:
                pass
        return data

    def _xbrl(self, filing: Filing, strict: bool = False) -> "xbrl_fast_path.XbrlResult | None":
        """The filing's XBRL figures (cached beside the text cache). A download problem fails only a
        strict (XBRL-only) filing; results fall back to the PDF."""
        if not filing.xbrl_url:
            return None
        path = self._cache_path(filing.news_id)
        path = path.with_name(path.name.replace(".json.gz", ".xbrl.gz")) if path else None
        data = None
        if path and path.exists():
            try:
                data = gzip.decompress(path.read_bytes())
            except OSError:
                data = None
        if data is None:
            try:
                data = self.bse.download(filing.xbrl_url, max_bytes=8_000_000)
            except AttachmentError:
                if strict:
                    raise
                log.warning("XBRL download failed for %s; using the PDF", filing.news_id)
                return None
            if data and path:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(gzip.compress(data))
                except OSError:
                    pass
        result = xbrl_fast_path.parse(data) if data else None
        if result:
            with self._lock:
                self.stats.xbrl += 1
        return result

    def _xbrl_memory(self, filing: Filing, company: dict) -> Outcome:
        """A shareholding pattern: its XBRL figures go straight into memory; no AI call, no card."""
        now = now_iso()
        tagged = self._xbrl(filing, strict=True)
        if not tagged or tagged.kind != "SHAREHOLDING" or not tagged.ownership:
            return Outcome({"news_id": filing.news_id, "status": "NOT_MATERIAL", "event_type": "SHAREHOLDING",
                            "reason": "xbrl: no shareholding figures in the file", "updated_at": now})
        dossier = self.sink.get_dossier(filing.scrip_code) or new_dossier(filing, company)
        out = Pass2Output(is_material=False, timeline_entry="")
        out.dossier_delta.ownership = tagged.ownership
        merged = merge(dossier, out, filing, None, now)
        self.sink.put_dossier(filing.scrip_code, merged)
        own = tagged.ownership
        return Outcome({"news_id": filing.news_id, "status": "NOT_MATERIAL", "event_type": "SHAREHOLDING",
                        "reason": f"xbrl: shareholding {own.period} saved to memory (promoter {own.promoter_pct}%)"[:300],
                        "updated_at": now},
                       company={"scrip_code": filing.scrip_code, "company_name": filing.company_name,
                                "updated_at": now, **_company_memory(merged)})

    def _cache_path(self, news_id: str):
        root = self.settings.text_cache_dir
        safe = "".join(ch for ch in news_id if ch.isalnum() or ch in "-_")[:80]
        return root / safe[:2] / f"{safe}.json.gz" if root and safe else None

    def _cached_text(self, news_id: str) -> dict | None:
        path = self._cache_path(news_id)
        if not path or not path.exists():
            return None
        try:
            return json.loads(gzip.decompress(path.read_bytes()))
        except Exception:  # a damaged cache file is re-read from BSE
            return None

    def _cache_text(self, news_id: str, doc: Document) -> None:
        path = self._cache_path(news_id)
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(gzip.compress(json.dumps(doc.to_cache(), ensure_ascii=False).encode()))
            tmp.replace(path)  # atomic: an interrupted run never leaves half a file
        except OSError as exc:
            log.warning("text cache write failed for %s: %s", news_id, exc)

    def _analyze_document(self, filing, company, industry, doc: Document, bulk: bool, memory_complete: bool) -> Outcome:
        now = now_iso()
        event_type = filing.event_type or "OTHER"
        if filing.route == "PASS1":
            first_page = doc.first_page_text()
            _ocr_check(doc)
            system, user = self.prompts.pass1(filing, first_page)
            verdict: Pass1Result = self.gateway.complete_json("pass1_bulk" if bulk else "pass1", system, user, Pass1Result).value
            if not verdict.is_material:
                with self._lock:
                    self.stats.pass1_rejected += 1
                return Outcome({"news_id": filing.news_id, "status": "NOT_MATERIAL", "event_type": verdict.event_type,
                                "reason": f"pass1: {verdict.reason}"[:300], "updated_at": now})
            event_type = verdict.event_type

        dossier = self.sink.get_dossier(filing.scrip_code) or new_dossier(filing, company)
        view = view_as_of(dossier, filing.filed_at)
        budget = self.settings.pass2_char_budget * (3 if event_type == "CONCALL_PRESENTATION" else 1)
        text = doc.select_text(budget, self.prompts.keywords(event_type))
        _ocr_check(doc)
        if event_type == "RESULTS" and not filing.xbrl_url:
            filing = filing.model_copy(update={"xbrl_url": self._results_xbrl_url(filing, text)})
        tagged = self._xbrl(filing) if event_type == "RESULTS" else None
        if tagged and (tagged.kind != "RESULTS" or not xbrl_fast_path.confirm(tagged, text)):
            if tagged.kind == "RESULTS":
                log.warning("XBRL figures for %s not found in the PDF in any unit; using the PDF only", filing.news_id)
            tagged = None
        if event_type == "RESULTS" and self.settings.one_card_per_results_quarter:
            earlier = self._same_results_quarter(filing, dossier, tagged.period if tagged else statement_quarter(text))
            if earlier:
                with self._lock:
                    self.stats.duplicates += 1
                return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": "RESULTS",
                                "reason": f"duplicate of {earlier[0]} (same results quarter {earlier[1]}, D20)",
                                "updated_at": now_iso()})
        if tagged:
            self._xbrl_comparatives(filing, tagged)
            text = tagged.table() + "\n\n" + text  # exact figures first; they also ground the card
        sector_module = self.prompts.sector_for(industry)
        sector = sector_module.name
        peers = self._peers(sector, event_type, filing)
        learned = self._learning()
        reaction = learned["queue"].get(filing.news_id)
        system, user = self.prompts.pass2(filing, event_type, industry, view, text, peers,
                                          examples=self._owner_examples(sector, event_type),
                                          lessons=[x["lesson"] for x in learned["lessons"].get(f"{sector}|{event_type}", [])][-3:],
                                          reaction=reaction)
        route = "pass2_bulk" if bulk else "pass2"
        if (len(system) + len(user)) / 4 > LONG_PROMPT_TOKENS and self.gateway.has_route("pass2_long"):
            route = "pass2_long"  # a transcript or presentation: long-context models only
        result = self.gateway.complete_json(route, system, user, Pass2Output)
        out: Pass2Output = result.value
        if not out.is_material or out.card is None:
            with self._lock:
                self.stats.not_material += 1
            return Outcome({"news_id": filing.news_id, "status": "NOT_MATERIAL", "event_type": out.event_type,
                            "reason": "pass2: not material", "updated_at": now})
        if "RESULTS" in (event_type, out.event_type):
            quarter = canonical_period(tagged.period) if tagged and tagged.period else statement_quarter(text)
            relabel_periods(out, quarter, statement_year(text))
        sources = (text, filing.headline, filing.subject, json.dumps(view or {}, ensure_ascii=False))
        history = dossier.get("financial_metrics", [])
        unit_fixes = fix_unit_slips(out, sources)
        change_fixes = fix_change_percentages(out)
        change_fixes += apply_deal_guards(out, filing, history, dossier.get("balance_sheet", []))
        if tagged:
            change_fixes += xbrl_key_numbers(out, tagged)
        checks = check_card_all(out, view, sources, history)
        checks.scale += period_mixups(out, tagged)
        review = None
        if checks.wants_second_opinion and self.settings.second_opinion:
            out, result, checks, review = self._second_opinion(route, system, user, out, result, checks, view, sources, history)
        checks.held += self._held_reasons(filing, text)
        if checks.held and review is None:
            review = {"status": "HELD", "issues": checks.held}
        if filing.route == "FAST_TRACK" and filing.event_type:
            out.event_type = filing.event_type  # rules know the event type better than the model
        elif out.event_type == "OTHER" and event_type != "OTHER":
            out.event_type = event_type  # Pass 2 left it open; Pass 1 had decided
        corrected = event_type_rules(out.event_type, filing, text, tagged)
        if corrected != out.event_type:
            log.info("event type for %s: %s -> %s (rules)", filing.news_id, out.event_type, corrected)
            out.event_type = corrected
        if out.card is not None and out.event_type != "CONCALL_PRESENTATION":
            out.card.call_read = None  # guidance, tone and transparency describe a call, not other filings
        event_type = out.event_type
        card = out.card
        if tagged:
            _apply_xbrl(out, tagged, filing.news_id)
        score, checked, ungrounded, quant, claims = checks.score, checks.checked, checks.ungrounded, checks.quant, checks.claims

        merged = merge(dossier, out, filing, card.impact_level, now)
        merged.update({k: v for k, v in (("industry", industry), ("sector", sector), ("symbol", company.get("symbol") or filing.symbol)) if v})
        # Signals, footer and results table see memory as it stood at this filing, not later facts
        # that a backfill may already have stored.
        before = dossier_as_of(dossier, filing.filed_at, inclusive=False)
        current = dossier_as_of(merged, filing.filed_at)
        # Market data as it stood when the filing came out: the stored daily series (history fill on
        # the laptop), else today's figures, dropped when they are too new for this filing.
        priced = point_in_time(company, filing.filed_at, self._prices, self._buckets) or priced_for(company, filing)
        signals = compute_signals(before, current, out, filing, priced) + text_signals(text, event_type)
        self.sink.put_dossier(filing.scrip_code, merged)

        card_json = {
            "category_tag": EVENT_TAGS.get(event_type, "UPDATE"),
            "event_type": event_type,
            **card.model_dump(),
            "quantified_impact": quant.items,
            "signals": signals,
            "timeline_entry": out.timeline_entry,
            "fundamentals": latest_fundamentals(current, sector_module.footer),
            "results": results_snapshot(current, filing.news_id) if event_type == "RESULTS" else None,
            "volume_strip": volume_strip(current, filing.news_id) if event_type == "MONTHLY_BUSINESS_UPDATE" else None,
            "pdf_pages": doc.page_count or None,
            "grounding": {"score": score, "checked": checked, "ungrounded": ungrounded[:10],
                          "math_mismatches": quant.mismatches, "unsupported_claims": claims,
                          "unit_fixes": unit_fixes or None, "change_fixes": change_fixes or None, "out_of_fit": checks.scale or None},
            "review": review,
            "model": result.model_label,
        }
        needs_review = checks.needs_review
        signals += asset_turn_signals(card_json, sector, sector_module.asset_turn)  # extends card_json["signals"]
        rated = score_card(card_json, event_type, signals, current, priced, needs_review, card.impact_level,
                           dampened=(sector, event_type) in learned["dampen"])
        if reaction:
            self._record_lesson(filing.news_id, sector, event_type, out.lesson, now)
        card_json["score"] = rated.as_dict()
        card_json["model_impact"] = card.impact_level
        if tagged:
            card_json["xbrl"] = {"basis": tagged.basis, "period": tagged.period, "figures": len(tagged.metrics)}
        card_json["priced_at_filing"] = {k: priced[k] for k in PRICED_FIELDS if priced.get(k) is not None} or None
        row = {
            "news_id": filing.news_id, "scrip_code": filing.scrip_code,
            "symbol": company.get("symbol") or filing.symbol, "company_name": filing.company_name,
            "filing_date": filing.filing_date, "filed_at": filing.filed_at, "sector": sector,
            "event_category": event_type, "impact_level": rated.impact, "headline": card.headline,
            "grounding_score": score, "needs_review": int(needs_review),
            "memory_complete": int(memory_complete), "card": card_json, "pdf_url": filing.pdf_url,
            "model": result.model_label, "created_at": now, "market_session": market_session(filing.filed_at),
            "actionability_score": rated.total, "is_actionable_signal": int(rated.actionable),
        }
        catalysts = [
            {
                "id": _catalyst_id(filing.scrip_code, ev.event_type, ev.date), "scrip_code": filing.scrip_code,
                "company_name": filing.company_name, "symbol": row["symbol"], "event_type": ev.event_type,
                "event_date": ev.date, "description": ev.description[:300], "source_news_id": filing.news_id,
                "created_at": now,
            }
            for ev in out.dossier_delta.upcoming_events if ev.date >= filing.filing_date
        ]
        for deadline, text in warrant_deadlines(out, filing):  # module 31: the 18-month warrant clock
            catalysts.append({
                "id": _catalyst_id(filing.scrip_code, "WARRANT_EXPIRY", deadline), "scrip_code": filing.scrip_code,
                "company_name": filing.company_name, "symbol": row["symbol"], "event_type": "WARRANT_EXPIRY",
                "event_date": deadline, "description": text[:300], "source_news_id": filing.news_id, "created_at": now,
            })
        for g in out.dossier_delta.guidance:
            deadline = due_date(g.due)
            if deadline and deadline.isoformat() >= filing.filing_date:
                catalysts.append({
                    "id": _catalyst_id(filing.scrip_code, "GUIDANCE_DUE", deadline.isoformat() + g.statement[:40]),
                    "scrip_code": filing.scrip_code, "company_name": filing.company_name, "symbol": row["symbol"],
                    "event_type": "GUIDANCE_DUE", "event_date": deadline.isoformat(),
                    "description": f"Guidance due ({g.due}): {g.statement}"[:300], "source_news_id": filing.news_id,
                    "created_at": now,
                })
        dated = {c["event_date"] for c in catalysts}
        for m in card.track_next.milestones:
            if m.date and m.date >= filing.filing_date and m.date not in dated:  # skip dates already covered by an event
                catalysts.append({
                    "id": _catalyst_id(filing.scrip_code, "MILESTONE", m.date + m.what[:40]),
                    "scrip_code": filing.scrip_code, "company_name": filing.company_name, "symbol": row["symbol"],
                    "event_type": "MILESTONE", "event_date": m.date, "description": m.what[:300],
                    "source_news_id": filing.news_id, "created_at": now,
                })
        for k in card.track_next.kpis_to_verify:
            check_by = due_date(k.check_in)
            if check_by and check_by.isoformat() >= filing.filing_date:
                catalysts.append({
                    "id": _catalyst_id(filing.scrip_code, "KPI_CHECK", check_by.isoformat() + k.kpi[:40]),
                    "scrip_code": filing.scrip_code, "company_name": filing.company_name, "symbol": row["symbol"],
                    "event_type": "KPI_CHECK", "event_date": check_by.isoformat(),
                    "description": f"Verify: {k.kpi}" + (f" (target {k.target})" if k.target else ""),
                    "source_news_id": filing.news_id, "created_at": now,
                })
        with self._lock:
            self.stats.analyzed += 1
            self.stats.cards_high += rated.impact == "HIGH"
            self.stats.signals += rated.actionable
            self.stats.needs_review += needs_review
        return Outcome(
            update={"news_id": filing.news_id, "status": "ANALYZED", "event_type": event_type,
                    "reason": None, "last_error": None, "updated_at": now},
            card=row,
            catalysts=catalysts,
            company={"scrip_code": filing.scrip_code, "company_name": filing.company_name,
                     "symbol": row["symbol"], "sector": sector, "updated_at": now,
                     **({"credibility_score": rated.credibility} if rated.credibility is not None else {}),
                     **_company_memory(merged)},
        )

    def _second_opinion(self, route, system, user, out: Pass2Output, result, checks: CardChecks, view, sources, history=None):
        """Ask a different provider to correct a card that failed the checks, then check again.

        The better of the two cards is kept. Either way the card is published: a corrected one
        normally, one that still fails with an "Unverified" mark and the problems listed, so a
        material filing is never hidden.
        """
        problems = checks.problems()
        base = {"first_model": result.model_label, "issues": problems}
        left = self.gateway.deadline - time.monotonic() if self.gateway.deadline else None
        if left is not None and left < SECOND_OPINION_MIN_S:
            return out, result, checks, {**base, "status": "UNCHECKED", "note": "skipped: the run was ending"}
        with self._lock:
            self.stats.second_opinions += 1
        hints = [UNIT_HINT] if checks.amounts_ungrounded else []
        system2, user2 = self.prompts.verify(system, user, out.model_dump(mode="json"), problems + hints)
        try:
            second = self.gateway.complete_json(route, system2, user2, Pass2Output, avoid_providers=(result.provider,))
        except Exception as exc:  # the first card is still published, marked unverified
            return out, result, checks, {**base, "status": "UNCHECKED", "note": f"{type(exc).__name__}: {exc}"[:200]}
        if not second.value.is_material or second.value.card is None:
            return out, result, checks, {**base, "status": "UNRESOLVED", "checked_by": second.model_label}
        # Adopt the corrected card only. Memory (dossier delta, timeline, event type) stays from the
        # first reply unless the verifier sent a fuller one: it was asked to fix the card, and a
        # reply with just {"card": ...} must not wipe the quarter's figures from memory.
        fixed = _adopt_card(out, second.value)
        checks2 = check_card_all(fixed, view, sources, history)
        if not checks2.wants_second_opinion:
            with self._lock:
                self.stats.corrected += 1
            return fixed, second, checks2, {**base, "status": "CORRECTED", "checked_by": second.model_label, "issues": [],
                                            "fixed": problems}
        if checks2.issue_count < checks.issue_count:
            return fixed, second, checks2, {**base, "status": "UNRESOLVED", "checked_by": second.model_label,
                                            "issues": checks2.problems()}
        return out, result, checks, {**base, "status": "UNRESOLVED", "checked_by": second.model_label}

    def _learning(self) -> dict:
        """Loop 1 state, read once per run: filings queued for a post-mortem re-analysis (with their
        reaction), lessons learnt per sector and event, and categories whose HIGH cards did not move prices."""
        with self._lock:
            if self._learned is not None:
                return self._learned
        state = {"queue": {}, "lessons": {}, "dampen": set()}
        try:
            state["queue"] = json.loads(self.sink.kv_get("learning:postmortem_queue") or "{}")
            state["lessons"] = json.loads(self.sink.get_object(LESSONS_KEY) or "{}")
            state["dampen"] = {(d.get("sector"), d.get("event_category")) for d in json.loads(self.sink.kv_get("learning:dampen") or "[]")}
        except Exception as exc:  # learning is an extra; a read problem never blocks analysis
            log.warning("learning state unavailable: %s", exc)
        with self._lock:
            self._learned = state
        return state

    def _record_lesson(self, news_id: str, sector: str, event_type: str, lesson: str, now: str) -> None:
        """Store a post-mortem lesson and take the filing off the queue. State changes under the lock;
        the writes after it (sink calls must never run while the lock is held)."""
        state = self._learning()
        with self._lock:
            state["queue"].pop(news_id, None)
            queue = json.dumps(state["queue"])
            lessons = None
            if lesson:
                rows = state["lessons"].setdefault(f"{sector}|{event_type}", [])
                rows.append({"lesson": lesson, "news_id": news_id, "added": now})
                del rows[:-LESSONS_KEEP]
                lessons = json.dumps(state["lessons"], ensure_ascii=False).encode()
        if lessons is not None:
            self.sink.put_object(LESSONS_KEY, lessons)
        try:
            done = json.loads(self.sink.kv_get("learning:postmortem_done") or "[]")
        except ValueError:
            done = []
        self._kv_set("learning:postmortem_done", json.dumps((done + [news_id])[-500:]))
        self._kv_set("learning:postmortem_queue", queue)

    def _owner_examples(self, sector: str, event_type: str) -> dict[str, list[dict]]:
        """The owner's two latest starred cards and latest noise card for this sector and event
        (blueprint Loop 3), read once per run per kind of filing."""
        key = (sector, event_type)
        with self._lock:
            if key in self._examples:
                return self._examples[key]
        try:
            found = {rating: [json.loads(r["card_json_snapshot"]) for r in
                              self.sink.query("feedback_examples", [sector, event_type, rating, limit]) if r.get("card_json_snapshot")]
                     for rating, limit in (("STARRED", 2), ("NOISE", 1))}
        except Exception as exc:  # examples are a refinement; never fail a filing for them
            log.warning("owner examples unavailable: %s", exc)
            found = {"STARRED": [], "NOISE": []}
        with self._lock:
            self._examples[key] = found
        return found

    def _peers(self, sector: str, event_type: str, filing: Filing) -> list[dict]:
        if sector == "default":
            return []
        since = (datetime.fromisoformat(filing.filed_at) - timedelta(days=60)).isoformat(timespec="seconds")
        try:
            return self.sink.peer_cards(sector, event_type, filing.scrip_code, since, filing.filed_at, 5)
        except Exception as exc:
            log.warning("peer lookup failed: %s", exc)
            return []

    def _archive_cards(self, cards: list[dict]) -> None:
        """Keep a per-day JSON copy of every card in R2, so D1 can be rebuilt without re-running AI."""
        by_day: dict[str, list[dict]] = {}
        for card in cards:
            by_day.setdefault(card["filing_date"], []).append(card)
        for day, rows in by_day.items():
            key = f"daily_feed/{day}.json"
            try:
                existing = json.loads(self.sink.get_object(key) or b"[]")
                merged = {c["news_id"]: c for c in existing} | {c["news_id"]: c for c in rows}
                body = json.dumps(sorted(merged.values(), key=lambda c: c["filed_at"]), ensure_ascii=False)
                self.sink.put_object(key, body.encode())
            except Exception as exc:  # the archive is a backup; never fail the run for it
                log.warning("card archive for %s failed: %s", day, exc)

    def _commit(self, outcomes: list[Outcome]) -> None:
        if not outcomes:
            return
        with self._commit_lock:
            self._commit_locked(outcomes)

    def _commit_locked(self, outcomes: list[Outcome]) -> None:
        try:
            self._commit_rows(outcomes)
        except SinkRejected as exc:
            # One bad row must not block the batch (and get its filings analysed again on every
            # run): commit filing by filing, and mark the ones the database refuses as FAILED.
            log.error("batch rejected (%s); committing one filing at a time", exc)
            for outcome in outcomes:
                try:
                    self._commit_rows([outcome])
                except SinkRejected as one:
                    news_id = outcome.update["news_id"]
                    self._exec("filings_update", [{"news_id": news_id, "status": "FAILED", "attempts": self.settings.max_attempts,
                                                   "last_error": f"rejected by the database: {one}"[:500], "updated_at": now_iso()}])
        self._flush_usage()

    def _commit_rows(self, outcomes: list[Outcome]) -> None:
        self._exec("companies_upsert", [o.company for o in outcomes if o.company])
        cards = [o.card for o in outcomes if o.card]
        self._exec("cards_upsert", cards)
        self._archive_cards(cards)
        self._exec("catalysts_upsert", [c for o in outcomes for c in o.catalysts])
        self._exec("filings_update", [o.update for o in outcomes])

    def _kv_set(self, key: str, value: str) -> None:
        written = self.sink.kv_set(key, value, now_iso())
        with self._lock:
            self.stats.d1_rows_written += written or 0

    # ------------------------------------------------------------------ runs

    def _writes_today(self) -> int:
        try:
            return int(self.sink.kv_get(f"d1_writes:{utc_day()}") or 0)
        except ValueError:
            return 0

    def _live_from(self, today: date) -> date:
        """Start of the live window: the last LIVE_DAYS days since the pipeline went live, so a
        filing left unfinished yesterday evening is not pushed behind the whole backfill."""
        since = self.sink.kv_get("live:since")
        if not since:
            since = today.isoformat()
            self._kv_set("live:since", since)
        return max(date.fromisoformat(since), today - timedelta(days=LIVE_DAYS))

    def run(self, mode: str = "all", time_budget_s: int = 2400, max_backfill_days: int = 5) -> Stats:
        started = time.monotonic()
        deadline = started + time_budget_s
        self.gateway.deadline = deadline + DEADLINE_GRACE_S  # a filing started before the deadline may finish
        run_id = f"{now_ist():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
        writes_at_start = self._writes_today()
        run_row = {"run_id": run_id, "mode": mode, "started_at": now_iso(), "status": "RUNNING"}
        self._exec("runs_upsert", [run_row])
        status, error = "OK", None
        try:
            today = today_ist()
            live_from = self._live_from(today) if mode in ("live", "all") else today
            if mode in ("live", "all"):
                days = [today - timedelta(days=1), today] if now_ist().hour < 9 else [today]
                for day in days:
                    self._discover_safely(day, full=False)
                live_deadline = deadline if mode == "live" else started + time_budget_s * 0.6
                backfill_done = self.sink.kv_get("backfill:complete") == "1"
                self.process(live_from.isoformat(), today.isoformat(), live_deadline, bulk=False,
                             memory_complete=backfill_done, history_first=True)
            if mode in ("backfill", "all") and not self._halted(bulk=True):
                self._backfill(today, deadline, writes_at_start, max_backfill_days, live_from - timedelta(days=1))
        except SourceBlockedError as exc:
            status, error = "ERROR", str(exc)
            self.stats.stopped_reason = "BSE blocked the request"
            log.error("%s", exc)
        except Exception as exc:
            status, error = "ERROR", f"{type(exc).__name__}: {exc}"
            log.exception("run failed")
        finally:
            if status == "OK" and (self._exhausted or self.stats.failed or self.stats.discovery_errors):
                status = "PARTIAL"
            self.stats.status = status
            try:
                self._flush_usage()
                self._exec("runs_upsert", [dict(run_row, finished_at=now_iso(), status=status,
                                                stats=self.stats.as_dict(), error=error)])
                self._publish_snapshot()
                # Read-modify-write under the current UTC day, so a run that crosses midnight does
                # not carry yesterday's total into the new day.
                self.sink.add_writes(utc_day(), self.stats.d1_rows_written, now_iso())
            except Exception:
                log.exception("could not record run")
        log.info("run %s finished: %s %s", run_id, status, json.dumps(self.stats.as_dict()))
        return self.stats

    def _publish_snapshot(self) -> None:
        """The homepage's default first page and the top signals, as one R2 object (blueprint §3.3):
        visitors read it instead of D1. Rebuilt when this run wrote cards or the day changed."""
        today = today_ist()
        start = (today - timedelta(days=SNAPSHOT_DAYS)).isoformat()
        try:
            current = json.loads(self.sink.get_object(SNAPSHOT_KEY) or b"{}")
        except Exception:
            current = {}
        if not self.stats.analyzed and current.get("from") == start:
            return
        try:
            cards = self.sink.query("snapshot_feed", [start, SNAPSHOT_PAGE])
            total = (self.sink.query("snapshot_count", [start]) or [{"n": len(cards)}])[0]["n"]
            signals = self.sink.query("snapshot_signals", [(today - timedelta(days=3)).isoformat()])
            body = {"generated_at": now_iso(), "from": start, "limit": SNAPSHOT_PAGE,
                    "feed": {"cards": cards, "total": total}, "signals": signals}
            self.sink.put_object(SNAPSHOT_KEY, json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode())
        except Exception as exc:  # the snapshot is an optimisation; the feed falls back to D1
            log.warning("snapshot not published: %s", exc)

    def _over_budget(self, writes_at_start: int) -> bool:
        budget = self.settings.d1_daily_write_budget
        if writes_at_start + self.stats.d1_rows_written < budget:
            return False
        self.stats.stopped_reason = f"D1 daily write budget ({budget}) reached; backfill paused until tomorrow"
        return True

    def _backfill(self, today: date, deadline: float, writes_at_start: int, max_days: int, history_to: date) -> None:
        """Discover historical days (and close each finished day with a full pass), then analyse the
        history company by company. Live work is never gated; backfill stops at the write budget."""
        start = date.fromisoformat(self.settings.backfill_start)
        if self.sink.kv_get("backfill:start") != start.isoformat():
            self._kv_set("backfill:start", start.isoformat())  # for the System view
        yesterday = today - timedelta(days=1)
        cursor_raw = self.sink.kv_get("backfill:discovered_through")
        cursor = date.fromisoformat(cursor_raw) if cursor_raw else start - timedelta(days=1)
        days = 0
        while cursor < yesterday and days < max_days and time.monotonic() < deadline:
            if self._over_budget(writes_at_start):
                break
            day = cursor + timedelta(days=1)
            found = self._discover_safely(day, full=True)
            if found is None:
                break  # retried on the next run; never skip a day
            if found == 0 and day.weekday() < 5 and not self._known_day(day):
                # A weekday with no filings at all is almost always a bad response: look again on
                # the next run before accepting it (a real holiday passes on the second look).
                if self.sink.kv_get("backfill:empty_day") != day.isoformat():
                    self._kv_set("backfill:empty_day", day.isoformat())
                    self.stats.stopped_reason = f"BSE returned no filings for {day}; checking again next run"
                    break
            cursor = day
            self._kv_set("backfill:discovered_through", cursor.isoformat())
            days += 1
        if history_to < start:
            return
        left = self._backfill_companies(start.isoformat(), history_to.isoformat(), cursor.isoformat(),
                                        deadline, writes_at_start)
        if left == 0 and cursor >= yesterday:
            remaining = self.sink.filings_remaining(start.isoformat(), history_to.isoformat(), self.settings.max_attempts)
            self._kv_set("backfill:complete", "0" if remaining else "1")

    def backfill_companies(self, scrips: list[str], day_from: date, day_to: date, time_budget_s: int) -> Stats:
        """Discover and analyse a few companies end to end (blueprint phase 2, the 5-company smoke
        test): every filing from ``day_from`` to ``day_to``, company by company, in date order."""
        deadline = time.monotonic() + time_budget_s
        self.gateway.deadline = deadline + DEADLINE_GRACE_S
        for scrip in scrips:
            self.discover_company(scrip, day_from, day_to)
        self._priority = list(scrips)
        state = {"built": today_ist().isoformat(), "through": "", "total": len(scrips), "scrips": []}
        self.sink.kv_set("backfill:company_order", json.dumps(state), now_iso())  # only these companies
        self._backfill_companies(day_from.isoformat(), day_to.isoformat(), "", deadline, self._writes_today())
        self._flush_usage()
        self.stats.status = "PARTIAL" if self.stats.failed else "OK"
        return self.stats

    def _known_day(self, day: date) -> bool:
        return self._noise_count(day.isoformat()) > 0 or bool(self.sink.known_ids(day.isoformat()))

    def _backfill_companies(self, day_from: str, day_to: str, through: str, deadline: float,
                            writes_at_start: int) -> int:
        """Analyse history company by company, largest market cap first, each in date order.

        A company's memory is then complete in one go, and the AI quota reaches the companies
        investors follow before the long tail. The order is built once a day (reading the whole
        queue), or again when it has run out and discovery has moved on; the unfinished remainder
        is kept in kv between runs. Companies with a live filing and a long backlog go first.
        Returns how many companies are left.
        """
        raw = self.sink.kv_get("backfill:company_order")
        state = json.loads(raw) if raw else {}
        built = today_ist().isoformat()
        if state.get("built") != built or (not state.get("scrips") and state.get("through") != through):
            rows = self.sink.query("backfill_companies", [day_from, day_to, self.settings.max_attempts, MAX_ORDER])
            state = {"built": built, "through": through, "total": len(rows), "scrips": [r["scrip_code"] for r in rows]}
        priority = list(dict.fromkeys(self._priority + json.loads(self.sink.kv_get("backfill:priority") or "[]")))
        order: list[str] = priority + [s for s in state["scrips"] if s not in set(priority)]
        width = max(1, self.settings.workers) * 2
        while order and time.monotonic() < deadline and not self._halted(bulk=True) and not self._blocked:
            if self._over_budget(writes_at_start):
                break
            batch, order = order[:width], order[width:]
            queues = {s: [f for f in (Filing.model_validate(r) for r in
                                      self.sink.pending_for_company(s, day_from, day_to, self.settings.max_attempts, HISTORY_LIMIT))
                          if f.news_id not in self._tried]
                      for s in batch}
            results = self._run_parallel({s: partial(self._process_group, q, deadline, True, True)
                                          for s, q in queues.items() if q})
            unfinished = []
            for s, q in queues.items():
                done = results.get(s, [])
                cut_short = len(done) < len(q) or any(o.update.get("status") == "PENDING" for o in done)
                if q and (cut_short or len(q) >= HISTORY_LIMIT):
                    unfinished.append(s)  # stopped early, or has more than one page of history
            order = unfinished + order
        self._kv_set("backfill:company_order", json.dumps({**state, "scrips": order}))
        if priority:
            self._kv_set("backfill:priority", json.dumps([s for s in priority if s in set(order)]))
        self._kv_set("backfill:progress", json.dumps({"companies_left": len(order), "companies_total": state.get("total"),
                                                      "built": state["built"], "through": through}))
        return len(order)


def _noise_key(day: str, chunk: int) -> str:
    return f"noise/{day}/{chunk:03d}.json"


def _noise_row(filing: Filing) -> list:
    return [filing.news_id, filing.scrip_code, filing.company_name, filing.headline[:240], filing.category,
            filing.subcategory, filing.filed_at, (filing.reason or "")[:120], filing.pdf_url]


SECOND_OPINION_MIN_S = 300
UNIT_HINT = ("Convert each amount from the unit its table states: ₹ lakh ÷ 100 = ₹ Cr, ₹ million ÷ 10 = ₹ Cr, "
             "₹ thousand ÷ 10,000 = ₹ Cr; remove a figure that matches no source at any unit")


def _adopt_card(first: Pass2Output, second: Pass2Output) -> Pass2Output:
    update: dict = {"card": second.card}
    if second.dossier_delta.model_dump(exclude_defaults=True):
        update["dossier_delta"] = second.dossier_delta
    if second.timeline_entry and not first.timeline_entry:
        update["timeline_entry"] = second.timeline_entry
    return first.model_copy(update=update)


def _ocr_check(doc: Document) -> None:
    """A mostly scanned document whose OCR failed has no text to analyse: retry later rather than
    judge it from the headline alone. A spent vision quota leaves the filing queued for tomorrow."""
    if doc.ocr_error is not None and doc.scanned_ratio >= 0.5:
        if isinstance(doc.ocr_error, AllProvidersFailed):
            raise doc.ocr_error
        raise RuntimeError(f"OCR failed on a scanned document: {doc.ocr_error}")


def build_pipeline(settings: Settings, sink: Sink) -> Pipeline:
    month = utc_day()[:7]
    try:
        usage_today, usage_month = sink.usage(utc_day()), sink.usage_month(month)
    except Exception as exc:
        log.warning("could not load AI usage; starting counters at zero: %s", exc)
        usage_today, usage_month = [], []
    gateway = AIGateway(settings.load_toml("providers.toml"), usage_today=usage_today, usage_month=usage_month)
    return Pipeline(settings, sink, gateway)


__all__ = ["Pipeline", "Stats", "build_pipeline", "IST"]


def _apply_xbrl(out: Pass2Output, tagged: "xbrl_fast_path.XbrlResult", news_id: str) -> None:
    """XBRL figures replace the model's for the same metric and period (and fill the ones it missed).
    A file on another basis than the card's figures (standalone vs consolidated) is left out of memory
    so the two are never mixed."""
    basis = out.card.basis if out.card else None
    if basis and tagged.basis and basis != tagged.basis:
        log.info("XBRL for %s is %s, the card quotes %s figures; memory keeps the card's", news_id, tagged.basis, basis)
        return
    delta = out.dossier_delta
    exact = {(m.metric, m.period): m for m in tagged.metrics}
    delta.financial_metrics = [m for m in delta.financial_metrics if (m.metric, canonical_period(m.period)) not in exact] \
        + list(exact.values())
    if tagged.balance_sheet and not tagged.balance_sheet.is_empty():
        sheet = delta.balance_sheet
        if sheet is None or sheet.is_empty():
            delta.balance_sheet = tagged.balance_sheet
        else:
            for key, value in tagged.balance_sheet.model_dump().items():
                if value is not None:
                    setattr(sheet, key, value)


def _company_memory(dossier: dict) -> dict:
    """Company-row fields drawn from memory: former names (searchable) and the radar summary."""
    names = (dossier.get("identity") or {}).get("former_names") or []
    return {**memory_summary(dossier), **({"former_names_json": json.dumps(names, ensure_ascii=False)} if names else {})}
