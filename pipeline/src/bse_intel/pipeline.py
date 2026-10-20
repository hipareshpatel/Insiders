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
from .dossier import (add_timeline_entry, dossier_as_of, forget_filing, latest_fundamentals, memory_ids, merge, own_former_name,
                      new_dossier, reported_by, results_snapshot, similar_timeline_entry, timeline_entry_dated, view_as_of)
from .extract import CACHE_VERSION, FIGURE_PAGE_AMOUNTS, Document, amounts, cache_needs_ocr
from .ocr import available as local_ocr_available
from .ocr import page_reader, recognise
from . import raw
from . import gate
from .grounding import (DEFAULT_THRESHOLD, SourceIndex, _tokens, change_derived, check_card, check_claims,
                        declared_unit, foreign_as_rupees, margin_issues, scale_issues, unit_slips)
from .models import EVENT_TAGS, Filing, Pass1Result, Pass2Output, RepeatVerdict, TimelineVerdict
from .periods import (canonical_period, due_date, prior_quarter_period, prior_year_period, quarter_from_index,
                      quarter_index, statement_quarter, statement_year)
from .prompts.engine import PromptEngine
from .quant import QuantCheck
from .quant import check as check_quant
from .rules import RuleBook
from .settings import Settings
from .forensics import text_signals
from .scoring import score as score_card
from .signals import compute as compute_signals, scale_block, scale_parts
from .card_context import case_stage, guidance_recall, rating_change, rating_word_mismatch
from .prices import PriceStore, point_in_time
from .signals import priced_for
from .sinks.base import Sink, SinkRejected, SinkUnavailable
from . import universe
from . import annual_xbrl
from . import directions
from . import results_card
from . import event_xbrl
from . import computed
from . import trust
from . import nse as nse_api
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
REQUEUE_AFTER_HOUR, REQUEUE_KEY = 22, "failed:requeued_on"   # the nightly extra try for failed filings
LIVE_DAYS = 7            # an unfinished filing stays in the live window this long
DEADLINE_GRACE_S = 240   # a filing started before the deadline may finish within this
MAX_REFUSALS = 3         # attachment 403s in a row that mean BSE is refusing this network
MAX_NETWORK_FAILURES = 5  # attachment downloads failing on the network in a row that mean the source is down
MAX_DEFERRALS = 3        # runs one attachment may fail on the network, alone, before it spends an attempt
MAX_UNREACHABLE = 3      # filings in a row the platform did not answer for: the site is down, stop
NOISE_CHUNK = 500        # rows per noise-audit file in R2
NOISE_FIELDS = ("news_id", "scrip_code", "company_name", "headline", "category", "subcategory",
                "filed_at", "reason", "pdf_url")
DONE = ("ANALYZED", "NOT_MATERIAL", "DUPLICATE")  # DUPLICATE: a repeat submission (duplicates.py)
LONG_PROMPT_TOKENS = 12_000
SNAPSHOT_KEY = "daily_feed/latest_snapshot.json"
SNAPSHOT_DAYS = 7         # the feed's default range ("Last 7 days")
SNAPSHOT_PAGE = 50        # the feed's page size


_DEFERRED = re.compile(r"^deferred (\d+)x: attachment download failed")


def _deferrals(last_error: str | None) -> int:
    """How many runs in a row this filing's attachment has failed on the network, from the ledger's note."""
    m = _DEFERRED.match(last_error or "")
    return int(m.group(1)) if m else 0


class EventXbrlPending(Exception):
    """A live filing's event XBRL has not reached NSE yet; the filing stays queued without spending an attempt."""


@dataclass
class Stats:
    discovered: int = 0
    dropped_rule: int = 0
    pending_new: int = 0
    pass1_rejected: int = 0
    timeline_only: int = 0  # routine filings given a timeline line and no card (D22)
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
    quotes: list[str] = field(default_factory=list)  # facts whose figures their own quote does not carry
    # A fact whose figures are all in the filing but whose quote is a paraphrase of it. Worth recording,
    # and worth a second provider's try at quoting properly, but on its own it is not a reason to keep a
    # card out of the feed: nothing it says has been found wrong. Three of Prism Johnson's segment facts
    # were held this way on 2026-10-17 with every figure verified.
    quote_style: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)   # reasons a second model cannot fix: garbled scan, human hold
    form: list[str] = field(default_factory=list)   # the card's shape: a headline that does not say what happened

    @property
    def needs_review(self) -> bool:
        # Blueprint rule: an unmatched ₹ figure in the headline or a failed math check holds the card;
        # so do a low overall match rate, an unsupported "first"/"record" claim and a figure out of scale.
        return self.fixable or bool(self.held)

    @property
    def fixable(self) -> bool:
        return (self.score < DEFAULT_THRESHOLD or self.quant.mismatches > 0 or bool(self.claims)
                or bool(self.headline_ungrounded) or bool(self.scale) or bool(self.quotes) or bool(self.form))

    @property
    def only_style(self) -> bool:
        """Nothing found wrong with the card beyond how it quoted the filing."""
        return bool(self.quote_style) and not self.fixable and not self.amounts_ungrounded

    @property
    def wants_second_opinion(self) -> bool:
        # Blueprint §4: any ungrounded number sends the card to a second provider. Amounts only: a
        # 10x lakh/crore slip in a key number leaves the overall match rate above the review
        # threshold, while an unmatched percentage is usually a derivation the checks cannot follow.
        # How a fact quoted the filing is not a reason on its own: the second provider was given no issue to
        # fix, and 30 of the 31 cards sent for their wording alone came back unresolved (2026-10-18).
        return self.fixable or bool(self.amounts_ungrounded)

    @property
    def issue_count(self) -> int:
        return (len(self.ungrounded) + self.quant.mismatches + len(self.claims) + len(self.scale) + len(self.quotes)
                + len(self.form))

    def problems(self) -> list[str]:
        out = []
        if self.headline_ungrounded:
            out.append("Headline figures not found in the filing or company memory: " + ", ".join(self.headline_ungrounded))
        if self.ungrounded:
            out.append("Numbers not found in the filing text or company memory: " + ", ".join(self.ungrounded[:10]))
        out += [f"Quantified impact \"{q['label']}\": {q.get('check_note')}" for q in self.quant.items if q.get("check") == "MISMATCH"]
        out += [f"Claim not supported by the sources: \"{c}\"" for c in self.claims]
        out += [f"Figures that do not fit (check the statement's unit and column): {s}" for s in self.scale]
        out += self.form
        out += [f"Give each fact the filing's own sentence as its quote: {q}" for q in self.quotes]
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
    for fact in card.what_happened:
        fact.text = fix(fact.text) or fact.text
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
    texts = [card.headline, card.takeaway, card.core_catalyst, *(f.text for f in card.what_happened), *(i.text for i in card.why_it_matters),
             *(f"{k.value} {k.change or ''}" for k in card.key_numbers),
             *(f"{c.previous or ''} ; {c.current or ''}" for c in card.notable_changes), out.timeline_entry]
    return [t for t in texts if t]


_FOREIGN_CRORE = re.compile(r"\b(USD|US\$|EUR|GBP|THB|AED|SAR|JPY|SGD|NGN|CHF|AUD|CAD|OMR|QAR|KWD)\s*([\d,]+(?:\.\d+)?)\s*(cr\b|crores?\b)",
                            re.I)


_COUNT_CRORE = re.compile(r"(?<![\d.,])(\d[\d,]*(?:\.\d+)?)\s*(cr\b|crores?\b)(\s+(?:equity\s+)?(?:votes|shares))", re.I)


def fix_foreign_crore(out: Pass2Output, text: str) -> list[str]:
    """A foreign amount written in crore that is the filing's figure read at another size: Clean Max's "Thai Baht
    1,250,000" (12.5 lakh, 0.125 crore) on its card as "THB 1.25 Cr" (round 6, 2026-10-19). The crore figure is kept
    when the filing has the amount at that size; when it has it ten or a hundred times smaller, it is set right."""
    card = out.card
    if card is None or not text:
        return []
    figures = [v for v, _, _, _, _ in _tokens(text) if v >= 1000]
    fixes: dict[str, str] = {}
    joined = " ".join(_card_texts(out))
    # (prefix, figure, unit, rest) for a foreign amount, and for a count of votes or shares: Ambuja's 2,254,107,305
    # votes written "2,254.11 Cr" and 418,004 written "4.18 Cr" (round 6)
    found = [(m.group(1) + " ", m.group(2), m.group(3), "", m.group(0)) for m in _FOREIGN_CRORE.finditer(joined)]
    found += [("", m.group(1), m.group(2), m.group(3), m.group(0)) for m in _COUNT_CRORE.finditer(joined)]
    for prefix, figure, unit, rest, whole in found:
        written = float(figure.replace(",", ""))
        if not written or any(abs(f / 1e7 - written) <= 0.005 * written + 1e-9 for f in figures):
            continue                                         # the filing has it at that size
        if re.search(rf"(?<![\d.,]){re.escape(figure)}\s*(?:cr\b|crores?\b)", text, re.I):
            continue                                         # the filing writes it in crore too ("USD 2 crore")
        for scale in (1e6, 1e5, 1e8, 1e9):                   # read as million or lakh, or ten or a hundred times small
            right = next((f / 1e7 for f in figures if abs(f / scale - written) <= 0.005 * written + 1e-9), None)
            if right is not None:
                fixes[whole] = f"{prefix}{right:,.4f}".rstrip("0").rstrip(".") + f" {unit}{rest}"
                break
    if not fixes:
        return []
    pattern = re.compile("|".join(re.escape(k) for k in sorted(fixes, key=len, reverse=True)))

    def fix(value):
        return pattern.sub(lambda x: fixes[x.group(0)], value) if value else value

    card.headline, card.takeaway, card.core_catalyst = fix(card.headline), fix(card.takeaway) or "", fix(card.core_catalyst)
    for fact in card.what_happened:
        fact.text = fix(fact.text) or fact.text
    for insight in card.why_it_matters:
        insight.text = fix(insight.text)
    for key in card.key_numbers:
        key.value, key.change = fix(key.value), fix(key.change)
    out.timeline_entry = fix(out.timeline_entry) or ""
    return [f"foreign amount set right: {k} -> {v}" for k, v in fixes.items()]


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
    for fact in card.what_happened:
        fact.text = fix(fact.text) or fact.text
    for insight in card.why_it_matters:
        insight.text = fix(insight.text)
    for key in card.key_numbers:
        key.value, key.change = fix(key.value), fix(key.change)
    for change in card.notable_changes:
        change.previous, change.current = fix(change.previous), fix(change.current)
    out.timeline_entry = fix(out.timeline_entry) or ""
    deal = card.deal_value
    if deal is not None and deal.amount_cr:
        # the deal size field too: Excelsoft's text was corrected to ₹0.3 Cr while its deal stayed ₹3 Cr (round 4)
        for _, value, decimals, right, _ in slips:
            if abs(float(deal.amount_cr) - value) <= 0.5 * 10 ** (-decimals) + 1e-9:
                deal.amount_cr = right
                break
    for m in out.dossier_delta.financial_metrics:
        if m.value is None or (m.unit or "INR_CR") != "INR_CR":
            continue
        for _, value, decimals, right, _ in slips:
            if abs(abs(float(m.value)) - value) <= 0.5 * 10 ** (-decimals) + 1e-9:
                m.value = right if float(m.value) >= 0 else -right
                break
    log.info("unit slips corrected in code: %s", mapping)
    return mapping


_MILLION_COUNT = re.compile(r"(?<![\d.,])(\d+(?:\.\d+)?)\s*(?:M|mn|million)\b(?=(?:\s+[\w-]+){0,2}?\s+"
                            r"(?:shares|warrants|options|units|securities)\b)", re.I)
_PRINTED_COUNT = re.compile(r"(?<![\d.,])\d{1,3}(?:,\d{2,3})+(?![\d,])|(?<![\d.,])\d{6,}(?![\d.,])")


def fix_count_millions(out: Pass2Output, sources: tuple[str, ...]) -> list[str]:
    """Share and warrant counts the filing prints in Indian grouping and the card writes as millions one place off:
    10,80,27,500 shares is 108.0 million, not "10.8M" (Adani Power's SAST disclosure; Magellanic's 12,67,00,000
    warrants as "12.67 million", round-2 re-run). A count is corrected only when the filing prints ten times it and
    not the count itself."""
    if out.card is None or not sources:
        return []
    printed = {int(m.group(0).replace(",", "")) for s in sources for m in _PRINTED_COUNT.finditer(s or "")}
    if not printed:
        return []

    def near(target: float, step: float) -> bool:
        return any(abs(p - target) <= step / 2 for p in printed)

    notes: list[str] = []

    def fix(text: str | None) -> str | None:
        if not text:
            return text

        def one(m: re.Match) -> str:
            raw = m.group(1)
            places = len(raw.partition(".")[2])
            value, step = float(raw), 10 ** (6 - places)
            if near(value * 1e6, step) or not near(value * 1e7, step * 10):
                return m.group(0)
            right = f"{value * 10:.{max(places - 1, 0)}f}"
            notes.append(f"count {raw} million read as {right} million (printed in crore)")
            return m.group(0).replace(raw, right, 1)

        return _MILLION_COUNT.sub(one, text)

    card = out.card
    card.headline, card.takeaway, card.core_catalyst = fix(card.headline), fix(card.takeaway) or "", fix(card.core_catalyst)
    for fact in card.what_happened:
        fact.text = fix(fact.text) or fact.text
    for insight in card.why_it_matters:
        insight.text = fix(insight.text)
    for key in card.key_numbers:
        key.value = fix(key.value)
    track = card.track_next
    if track is not None:
        track.risks = [fix(r) for r in track.risks]
        track.catalysts = [fix(c) for c in track.catalysts]
    out.timeline_entry = fix(out.timeline_entry) or ""
    return notes


_CHANGE_AMOUNT = re.compile(r"(?<![\w.])(\(?-?\d[\d,]*(?:\.\d+)?\)?)")
# The thousands separator is part of the number: a turnaround off a small base is written "+1,050%",
# and without the comma the pattern read it as 50%, decided the model was wrong by a factor of
# twenty, and spliced its correction into the middle, leaving "+1,+1050.3%" on the card.
_CHANGE_PCT = re.compile(r"([+\-−]?)\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*%")


def _without_periods(text: str | None) -> str:
    return re.sub(r"\b(?:Q[1-4]|H[12]|9M)?FY\s?'?\d{2,4}\b|\b(?:19|20)\d{2}\b", " ", text or "")


def _amount(text: str | None) -> float | None:
    plain = re.sub(r"[-−]\s*(?:₹|rs\.?|inr)\s*", "-", _without_periods(text), flags=re.I)  # "-₹14.22 Cr" is negative
    m = _CHANGE_AMOUNT.search(plain)
    if not m:
        return None
    raw = m.group(1)
    try:
        value = float(raw.strip("-()").replace(",", ""))
    except ValueError:
        return None
    return -value if raw.startswith(("-", "(")) else value


def _decimals_of(text: str | None) -> int:
    """How many decimals the amount `_amount` reads from this text was written with."""
    m = _CHANGE_AMOUNT.search(_without_periods(text))
    return len(m.group(1).strip("-()").partition(".")[2]) if m else 2


def fix_change_percentages(out: Pass2Output, sources: tuple[str, ...] = ()) -> list[str]:
    """A notable change whose % does not follow from its own two figures ("₹494 Cr → ₹418 Cr, +15% YoY",
    a 15% fall) gets the computed % in code. Only amounts on both sides, neither a percentage, and only
    when the filing states both: computing from a figure the model misread turns a small unit slip into a
    confident nonsense ("₹43 Cr → ₹458 Cr, +965%" where the statement said 457.86 million, audit round 1)."""
    fixed = []
    index = SourceIndex(*sources) if sources else None
    for change in out.card.notable_changes if out.card else []:
        before, after, stated = change.previous or "", change.current or "", change.change or ""
        m = _CHANGE_PCT.search(stated)
        if not m or "%" in before or "%" in after:
            continue
        a, b = _amount(before), _amount(after)
        if a is None or b is None or a == 0:
            continue
        if a < 0 or b < 0:
            # A percentage across a loss or a sign change means nothing: Britannia's inventory change "+894.4%" from
            # ₹1.43 Cr to -₹14.22 Cr, CSB's provisions "+1713%" off a write-back (audit round 2). Said in words.
            words = ("loss narrowed" if abs(b) < abs(a) else "loss widened") if a < 0 and b < 0 else \
                ("turned positive" if b > 0 else "turned negative")
            change.change = (stated[:m.start()] + words + stated[m.end():]).strip()
            fixed.append(f"{change.metric}: {stated} -> {change.change}")
            continue
        # each side at the precision the card wrote it: "₹494 Cr" is the statement's 49,412 lakh; asked at two
        # decimals it never matched, so a whole-crore change was never corrected (audit, 2026-10-18)
        if index and not all(index.stated_crore(abs(v), _decimals_of(t)) for v, t in ((a, before), (b, after))):
            continue  # one side is not in the filing, so the % computed from it would be worse
        real = (b - a) / abs(a) * 100
        claimed = float(m.group(2).replace(",", "")) * (-1 if m.group(1) in ("-", "−") else 1)
        if not m.group(1) and re.search(r"\b(?:down|fell|lower|decline)", stated, re.I):
            claimed = -claimed
        if abs(claimed - real) <= max(1.0, abs(real) * 0.05):
            continue
        new = f"{real:+.1f}%".replace(".0%", "%")
        change.change = stated[:m.start()] + new + stated[m.end():]
        # the model writes the direction in capitals, so compare without case or the flip never fires
        if (change.direction or "").lower() in ("positive", "negative") and (real > 0) != (claimed > 0):
            flipped = "NEGATIVE" if change.direction.lower() == "positive" else "POSITIVE"
            change.direction = flipped if change.direction.isupper() else flipped.lower()
        fixed.append(f"{change.metric}: {stated} -> {change.change}")
    if fixed:
        log.info("change percentages corrected in code: %s", fixed)
    return fixed


# The owners' share first: "net profit to shareholders" matched `pat` and was set to the group's profit, minorities
# included (Sunteck 62.83 for the owners' 63.75, ITC 4,508.79 for 4,394.13; live review 3, 2026-10-20)
_KEY_METRIC = (("pat_owners", re.compile(r"\b(?:to|for)\s+(?:the\s+)?(?:share|equity\s*)holders|attributable\s+to\s+(?:the\s+)?"
                                         r"(?:owners|equity|shareholders)|owners\s+of\s+(?:the\s+)?(?:parent|company)", re.I)),
               ("ebitda", re.compile(r"\bebitda\b(?!.*margin)", re.I)),
               ("pbt", re.compile(r"\bpbt\b|profit before tax", re.I)),
               ("pat", re.compile(r"\bpat\b|net profit|profit after tax|net income", re.I)),
               ("eps", re.compile(r"\beps\b|earnings per share", re.I)),
               ("revenue", re.compile(r"revenue|net sales|income from operations|\bsales\b", re.I)))


_LABEL_PERIOD = re.compile(r"\b(9M|H[12]|Q[1-4]|FY)\s*(?:FY)?\s*(\d{4}|\d{2})?\b", re.I)
# A figure the company defines for itself, which no XBRL fact is: left as the model read it
_QUALIFIED_LABEL = re.compile(r"\b(?:normali[sz]ed|adjusted|underlying|core|recurring|pro[- ]?forma|"
                              r"excluding|ex[- ]exceptional|before exceptional|cash)\b", re.I)


def _label_period(label: str, default: str, available: dict) -> str | None:
    """Which period a key number's label is about, or None when the file cannot answer for it.

    "FY25 revenue" is the year, "Q4 EBITDA" the quarter of whichever year the file reports, and a bare
    "revenue" is whatever `default` says the card is about.
    """
    m = _LABEL_PERIOD.search(label)
    if not m:
        return default
    kind, year = m.group(1).upper(), m.group(2)
    if year:
        fy = f"FY{year[-2:]}"
    else:
        fy = default[-4:] if default[-4:].startswith("FY") else None
        if fy is None:
            return default
    period = fy if kind == "FY" else f"{kind}{fy}"
    return period if period in available else None


def xbrl_key_numbers(out: Pass2Output, tagged: "xbrl_fast_path.XbrlResult",
                     sources: tuple[str, ...] = ()) -> list[str]:
    """A results card's key numbers for revenue, EBITDA, PBT, PAT and EPS set from the XBRL file: exact
    value and YoY (SML's "revenue -40% YoY" was the fall from the previous quarter; its "EBITDA ₹0.75 Cr"
    was PBT). Only on the card's own basis and quarter. Returns what changed."""
    if out.card is None or tagged.kind != "RESULTS" or not tagged.period:
        return []
    if out.card.basis and tagged.basis and out.card.basis != tagged.basis:
        return []
    by_period: dict[str, dict] = {}
    for m in tagged.metrics:
        by_period.setdefault(m.period, {})[m.metric] = m
    # Which period the card is about, where it says so. A results file for Q4 carries the quarter and
    # the year, and a label with no period of its own ("Revenue") means whichever the card is about:
    # Jubilant's FY25 card had its Rs 7,234.5 Cr for the year replaced by the quarter's Rs 1,928.80 Cr
    # because the file was filed for the quarter.
    card_period = _label_period(f"{out.card.headline or ''} {out.timeline_entry or ''}",
                                tagged.period, by_period) or tagged.period
    now = by_period.get(tagged.period, {})
    # The table is prepended to the filing text the model reads, so it usually arrives inside `sources`
    # too. Take it out: a comparative checked against the very table it came from would always verify,
    # and the guard below would silently do nothing.
    table = tagged.table()
    index = SourceIndex(*(s.replace(table, " ") for s in sources)) if sources else None
    changed: list[str] = []
    unverified: list[str] = []
    for key in out.card.key_numbers:
        if "margin" in (key.label or "").lower() or "%" in (key.value or ""):
            continue
        metric = next((name for name, pattern in _KEY_METRIC if pattern.search(key.label or "")), None)
        if metric == "pat" and re.search(r"\bdiscontinued\b", key.label or "", re.I):
            continue  # the discontinued business's own result, which is not the file's PAT
        if metric == "pat" and re.search(r"\bcontinuing\b", key.label or "", re.I):
            # "PAT (Continuing)" is profit from continuing operations, not the total: Siemens' ₹343 Cr became the
            # ₹2,143 Cr that includes the demerged business's gain, and -18.7% YoY became +406% (round 4, 2026-10-19)
            metric = "pat_continuing"
        if metric and _QUALIFIED_LABEL.search(key.label or ""):
            continue  # "Normalised PAT" is not the file's PAT: Jubilant's ₹86 Cr became the reported ₹55.80 Cr
        # The label usually names its own period ("FY25 revenue", "Q4 EBITDA") and it is often not the
        # quarter the file was filed for: a results file for Q4 also carries the full year. Overwriting
        # by metric alone put the quarter's figure under the year's label - SML's FY25 revenue went from
        # Rs 453.98 Cr to Rs 107.84 Cr, a fifth of itself, with the year's YoY left beside it. So the
        # label's period picks the fact, and a period the file does not carry is left to the model.
        wanted = _label_period(key.label or "", card_period, by_period)
        if wanted is None:
            continue
        m = by_period.get(wanted, {}).get(metric) if metric else None
        if m is None or m.value is None:
            continue
        group = by_period.get(wanted, {}).get("pat")
        if metric == "pat_owners" and m.value == 0 and group is not None and group.value:
            continue   # a zero the file carries for the owners' share beside a real profit is a filler (Orient Bell)
        value = f"₹{m.value:,.2f}" + (" per share" if metric == "eps" else " Cr")
        # The value is one tagged fact and is trusted; the YoY needs a second one, and a wrong period
        # match produced headline reversals in audit round 1 (Kanoria Q1FY27 revenue +129% rewritten to
        # +1.5%). Accept it only when the year-ago figure it implies is in the filing as well.
        change = key.change
        if m.yoy_pct is not None and m.yoy_pct != -100:
            # The year-ago figure itself where the earlier quarter's file gave it (add_comparatives). Rebuilt
            # from the YoY, it is only as exact as a YoY rounded to a tenth of a point: Jubilant's Q4 revenue
            # of ₹1,928.8 Cr puts it ₹0.9 Cr out, and asked at two decimals the right YoY was refused - "XBRL
            # year-ago not in the filing" on most results cards (audit of discard paths, 2026-10-18).
            year_ago = by_period.get(prior_year_period(wanted) or "", {}).get(metric) if metric else None
            if year_ago is not None and year_ago.value is not None:
                prior = year_ago.value
            else:
                prior = m.value / (1 + m.yoy_pct / 100)
                slack = abs(m.value) * 0.0005 / (1 + m.yoy_pct / 100) ** 2   # half a tenth of a point
            if index is None or (index.stated_crore(round(abs(prior), 2), 2) if year_ago is not None and year_ago.value
                                 is not None else index.stated_crore(abs(prior), 2, tolerance=slack + 0.005)):
                change = f"{m.yoy_pct:+.1f}% YoY"
            elif key.change:
                unverified.append(f"{key.label}: XBRL year-ago ₹{prior:,.2f} Cr is not in the filing")
        # A value and the change beside it have to be about the same period. Where the figure is
        # replaced by a materially different one and the file's own YoY could not be verified, the
        # model's change belonged to the figure that has just gone: Shivam's Rs 453.98 Cr for the year
        # became the quarter's Rs 107.84 Cr with "-3.3% YoY", which was the year's fall. Say nothing
        # rather than pair a figure with a change that is not its own.
        if change is key.change and _amount(key.value) is not None                 and abs((_amount(key.value) or 0) - m.value) > max(0.01, abs(m.value) * 0.005):
            change = None
        if (key.value, key.change) != (value, change):
            changed.append(f"{key.label}: {key.value} ({key.change}) -> {value} ({change})")
            key.value, key.change = value, change
            # and its quote is the file's line: the press release's "Revenue for the quarter was INR 1,749.5
            # million" held eMudhra's tagged ₹172.88 Cr as stating a figure its own quote does not (2026-10-18)
            line = next((l[2:] for l in table.splitlines() if l.startswith(f"- {m.metric} {m.period}: ")), None)
            if line:
                key.quote = line
    if changed:
        log.info("key numbers set from XBRL: %s", changed)
    if unverified:
        log.info("XBRL YoY left alone, comparative not in the filing: %s", unverified)
    return changed


_PCT_LABELLED = re.compile(r"([+\-−]?\d+(?:\.\d+)?)\s*%\s*(?:\(?\s*)(YoY|QoQ|y-o-y|q-o-q|year[- ]on[- ]year|quarter[- ]on[- ]quarter)", re.I)


_PERIOD_WORDS = re.compile(r"\b(?:nine[- ]months?|first[- ]half|second[- ]half|full[- ]year)\b", re.I)
_PERIOD_WORD_LABELS = {"nine ": "9M", "nine-": "9M", "first": "H1", "secon": "H2", "full ": "FY", "full-": "FY"}

# A period a memory insight names, and how memory writes it: "July 2025", "Jul-25", "AUG-2025"; "Q1FY26", "H1 FY26";
# "FY25", "FY 2024-25".
_MONTH_NAMES = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_INSIGHT_PERIOD = re.compile(
    # a two-digit year only after a dash or apostrophe: "March 31, 2025" is not March 2031
    r"\b(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:[\s'’-]*(?P<my>(?:19|20)\d{2})|\s*[-'’]\s*(?P<my2>\d{2}))\b"
    r"|\b(?P<q>Q[1-4]|H[12]|9M)\s*FY\s*'?(?P<qy>\d{2}(?:\d{2})?)\b"
    r"|(?<![\w-])FY\s*'?(?P<fy>\d{2}(?:\d{2})?)(?:\s*[-–/]\s*(?P<fy2>\d{2}(?:\d{2})?))?\b", re.I)
# A figure in an insight. A percentage, a range of them ("1.5-1.8%"), a ratio ("0.5x") and basis points are not amounts.
_INSIGHT_FIGURE = re.compile(r"(?<![\w.,])(?>\d[\d,]*(?:\.\d+)?)"
                             r"(?!\s*(?:[-–]\s*\d[\d.,]*\s*)?(?:%|per\s*cent|bps|pp\b|x\b|times\b))", re.I)
# What may stand between a figure and the period written after it: "₹1,019.8 Cr in Q2FY25", "842 units (Aug-2025)"
_FIGURE_TO_PERIOD = re.compile(r"\s*(?:cr|crores?|lakhs?|mn|million|bn|units?|mt|mtpa|tonnes?)?\.?\s*\)?\s*"
                               r"(?:in|for|at|during|as of|as at|of)?\s*\(?\s*", re.I)


def _period_keys(text: str) -> list[tuple[int, int, str, str]]:
    """(start, end, kind, key) of each period named: kind M (a month), Q (a quarter, half or nine months), FY."""
    out = []
    for m in _INSIGHT_PERIOD.finditer(text):
        if m.group("mon"):
            year = m.group("my") or "20" + m.group("my2")
            out.append((m.start(), m.end(), "M", f"{year}-{_MONTH_NAMES.index(m.group('mon').lower()) + 1:02d}"))
        elif m.group("q"):
            out.append((m.start(), m.end(), "Q", f"{m.group('q').upper()}FY{m.group('qy')[-2:]}"))
        else:
            out.append((m.start(), m.end(), "FY", f"FY{(m.group('fy2') or m.group('fy'))[-2:]}"))
    return out


def _memory_series(view: dict) -> dict[tuple[str, str], dict[tuple[str, str], float]]:
    """Memory's metric series, {(name, unit): {(kind, period): value}}, from the view's "PERIOD: value UNIT" lines.
    A span of months ("APR-AUG-2025") is left out: it is not the month it ends in."""
    series: dict[tuple[str, str], dict[tuple[str, str], float]] = {}
    for name, lines in ((view or {}).get("metrics") or {}).items():
        for line in lines if isinstance(lines, list) else []:
            label, _, rest = str(line).partition(":")
            label = label.strip()
            keys = _period_keys(label)
            value = re.match(r"\s*(-?\d[\d,]*(?:\.\d+)?)\s*([A-Z_]*)", rest)
            if len(keys) == 1 and value and keys[0][:2] == (0, len(label)):
                series.setdefault((name, value.group(2)), {})[keys[0][2:]] = float(value.group(1).replace(",", ""))
    return series


# The unit an insight writes after a figure, as memory names it; a money figure is compared in crore
_FIGURE_UNIT = re.compile(r"\s*(?:(?P<cr>cr\b|crores?)|(?P<lakh>lakhs?|lacs?)|(?P<mn>mn\b|millions?)|(?P<bn>bn\b|billions?)"
                          r"|(?P<units>units?\b|vehicles?\b|nos\b))", re.I)
_TO_CRORE = {"cr": 1, "lakh": 0.01, "mn": 0.1, "bn": 100}


_APPROVAL_STOP = {"approval", "approvals", "pending", "required", "requirement", "regulatory", "shareholder", "shareholders",
                  "statutory", "other", "from", "with", "under", "subject", "receipt", "necessary", "applicable", "authority",
                  "authorities", "relevant", "including", "such", "deal", "transaction", "company"}


def call_changes(out: Pass2Output, event_type: str, filing_text: str) -> list[str]:
    """On a call or presentation card, a change whose figures the call itself does not state is dropped. Its "previous"
    came from memory on another basis: Electrosteel's margin of 4.14% (memory, without other income) against the call's
    9.5% (with it), Texmaco's consolidated computed margin against management's standalone one, Ceigall's standalone
    EBITDA set beside consolidated revenue (round 5 arm B, 2026-10-19). Memory's own comparisons are made by code
    (results_card.memory_points)."""
    card = out.card
    if card is None or "CONCALL_PRESENTATION" not in (event_type, out.event_type) or not card.notable_changes:
        return []
    index = SourceIndex(filing_text or "")
    kept, dropped = [], []
    for change in card.notable_changes:
        figures = [(v, d) for v, d, _, _, _ in _tokens(f"{change.previous or ''} {change.current or ''}") if v >= 1]
        if figures and not all(index.stated(v, d) for v, d in figures):
            dropped.append(change.metric)
        else:
            kept.append(change)
    card.notable_changes = kept
    return [f"call card: change dropped, its figures are not all in the call: {m}" for m in dropped]


def stale_approvals(out: Pass2Output, view: dict | None, filing_text: str) -> list[str]:
    """A pending approval copied from memory's watchlist that this filing does not mention. The rule (pass2.md) is "only
    when the filing states them"; round 5's agents found Persistent's BaFin approval listed as pending after the offer
    document it approved was out, and NLC's watchlist items on a card about something else (2026-10-19). Only an item
    that reads as a watchlist entry, none of whose own words the filing prints, is dropped."""
    card = out.card
    if card is None or not view or not card.track_next.pending_approvals:
        return []
    from .dossier import _timeline_words
    watched = [_timeline_words(w.get("text", "")) for w in view.get("watchlist", [])]
    body = " ".join(re.findall(r"[a-z0-9]+", (filing_text or "").lower()))
    kept, dropped = [], []
    for item in card.track_next.pending_approvals:
        mine = _timeline_words(item)
        own = {w for w in mine if w not in _APPROVAL_STOP}
        copied = any(mine and w and len(mine & w) / len(mine | w) >= 0.5 for w in watched)
        if copied and own and not any(re.search(rf"\b{re.escape(w)}\b", body) for w in own):
            dropped.append(item)
        else:
            kept.append(item)
    card.track_next.pending_approvals = kept
    return [f"pending approval from memory's watchlist, not in this filing, dropped: {d[:80]}" for d in dropped]


def misdated_memory_insights(out: Pass2Output, view: dict | None, filing_text: str = "") -> list[str]:
    """Memory insights that put a figure memory holds under another period: SML's August card said "July 2025,
    when sales were 842 units", and memory has 842 as August's - a right card published with a wrong point, since
    a memory insight is checked only for its figures being somewhere in memory (re-run of the held cards,
    2026-10-18). The insight is dropped and the card kept.

    Only a clear case counts, measured on the 332 cards with memory insights (9 of 10 first catches were wrong):
    the figure is in one of memory's metric series under another period of the same kind, and not under the one
    the insight names; the insight ties it to that period tightly ("₹1,019.8 Cr in Q2FY25", or the period just
    before it with no other figure between); and the filing does not print it, since memory does not yet hold
    the figures of the filing being read. A timeline sentence is too loose to judge by."""
    card = out.card
    if card is None or not view:
        return []
    series = _memory_series(view)
    if not series:
        return []
    printed = [v for v, _, _, _, _ in _tokens(filing_text or "")]
    dropped, kept = [], []
    for insight in card.why_it_matters:
        reason = None
        if insight.basis in ("MEMORY", "BALANCE_SHEET"):
            text = insight.text or ""
            periods = _period_keys(text)
            figures = [f for f in _INSIGHT_FIGURE.finditer(text) if not any(s <= f.start() < e for s, e, _, _ in periods)]
            for i, fig in enumerate(figures):
                written = fig.group(0).rstrip(",")
                raw = written.replace(",", "")
                value, decimals = float(raw), len(raw.partition(".")[2])
                if (value < 32 or ("," not in written and 1990 <= value <= 2100)) and not decimals:
                    continue  # a day, a count, a year
                tolerance = 0.5 * 10 ** -decimals + 1e-9
                unit = _FIGURE_UNIT.match(text, fig.end())
                word = next((k for k, v in unit.groupdict().items() if v), None) if unit else None
                money = word in _TO_CRORE or text[max(0, fig.start() - 3):fig.start()].strip().endswith(("₹", "Rs", "Rs."))
                scales = (1, 10, 100, 1e7) if money else (1,)   # a crore figure printed in million, lakh or rupees
                if any(abs(v - value * s) <= tolerance * s for v in printed for s in scales):
                    continue  # the filing prints it
                if money:
                    value, tolerance = value * _TO_CRORE.get(word or "cr", 1), tolerance * _TO_CRORE.get(word or "cr", 1)
                wanted = ("INR_CR",) if money else ("UNITS",) if word == "units" else None
                after = [p for p in periods if p[0] >= fig.end() and _FIGURE_TO_PERIOD.fullmatch(text[fig.end():p[0]])]
                floor = figures[i - 1].end() if i else 0
                before = [p for p in periods if p[0] >= floor and p[1] <= fig.start() and fig.start() - p[1] <= 40]
                named = after[0] if after else (before[-1] if before else None)
                if named is None:
                    continue
                kind, period = named[2], named[3]
                elsewhere = []
                for (name, series_unit), values in series.items():
                    if (series_unit not in wanted) if wanted else series_unit in ("PCT", "X", "BPS"):
                        continue  # "₹3.98 Cr" is not a 3.98% margin
                    held = [key for (k, key), v in values.items() if k == kind and abs(abs(v) - value) <= tolerance]
                    if period in held:
                        break  # some metric holds it under the period named: another's same value is chance
                    elsewhere += [(key, name) for key in held]
                else:
                    if elsewhere:
                        reason = f"{written} is {elsewhere[0][0]}'s {elsewhere[0][1]} in memory, not {period}'s"
                        break
        if reason:
            dropped.append(f'memory insight dropped ("{(insight.text or "")[:60]}"): {reason}')
        else:
            kept.append(insight)
    if dropped:
        card.why_it_matters = kept
    return dropped


def period_mixups(out: Pass2Output, tagged: "xbrl_fast_path.XbrlResult | None") -> list[str]:
    """A "% YoY" on the card that is the quarter-on-quarter change of a tagged figure (and no figure's
    YoY), or the reverse: SML's results cards called the fall from Q2 a fall from a year ago.

    Each change is compared with the changes of the period it is about, and only those: the period named
    just before it in its own sentence, else its key number's label, else the period the card's headline
    and timeline entry name (as xbrl_key_numbers reads them, d6e7c14). Comparing with the latest quarter
    alone held Jubilant's FY25 revenue "+7.9% YoY" as a quarter-on-quarter change; comparing with every
    period's would let a quarter's figure pass with the year's change (loop rounds 3a-3b, 2026-10-17)."""
    if out.card is None or tagged is None or tagged.kind != "RESULTS":
        return []
    by_period: dict[str, list] = {}
    for m in tagged.metrics:
        if m.unit != "PCT":
            by_period.setdefault(m.period, []).append(m)
    known = {(m.metric, m.period): m.value for m in tagged.metrics if m.value is not None}

    def changes(period: str) -> tuple[list[float], list[float]]:
        metrics = by_period.get(period) or []
        yoy = [abs(m.yoy_pct) for m in metrics if m.yoy_pct is not None]
        qoq = [abs(m.qoq_pct) for m in metrics if m.qoq_pct is not None]
        # XBRL gives no change on a loss (xbrl._change), but a card may: Shivam's FY25 loss of 48.04
        # against 50.2 was "+4.3% YoY (less negative)".
        for m in metrics:
            before = known.get((m.metric, prior_year_period(m.period) or ""))
            if m.yoy_pct is None and m.value is not None and before:
                yoy += [abs((m.value - before) / abs(before) * 100), abs((abs(m.value) / abs(before) - 1) * 100)]
        return yoy, qoq

    card = out.card
    about = _label_period(f"{card.headline or ''} {out.timeline_entry or ''}", tagged.period, by_period) or tagged.period
    items = [(t, about) for t in (card.headline, card.takeaway, card.core_catalyst, *(f.text for f in card.what_happened),
                                  *(i.text for i in card.why_it_matters), out.timeline_entry) if t]
    items += [(f"{k.value} {k.change or ''}", _label_period(k.label or "", about, by_period)) for k in card.key_numbers]
    items += [(f"{c.previous or ''} ; {c.current or ''}", about) for c in card.notable_changes]
    issues = []
    for text, default in items:
        # periods in words, written over in place so positions hold: "Nine-month revenue ... down 3.2% YoY"
        text = _PERIOD_WORDS.sub(lambda w: _PERIOD_WORD_LABELS[w.group(0).lower()[:5]].ljust(len(w.group(0))), text)
        for m in _PCT_LABELLED.finditer(text):
            # the period named just before the change, and just after it: "the 12.3% YoY growth in H1FY26"
            before = list(_LABEL_PERIOD.finditer(text[:m.start()]))
            after = _LABEL_PERIOD.search(text[m.end():m.end() + 30])
            named = [p.group(0) for p in (before[-1] if before else None, after) if p]
            periods = {_label_period(p, about, by_period) for p in named} if named else {default}
            periods.discard(None)  # a period the file does not carry: nothing to compare the change with
            if not periods:
                continue
            yoy = [x for p in periods for x in changes(p)[0]]
            qoq = [x for p in periods for x in changes(p)[1]]
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


def results_quarter(tagged, text: str, filed_on: str | None = None) -> str | None:
    """The quarter whose results a filing carries, for D20: from its XBRL, or from a statement of results or a
    page of figures in its text. The notice of the board meeting that will consider the results names the quarter
    too ("for the quarter and nine months ended 31st December, 2024") but prints no figure, and claimed Ahluwalia's
    Q3FY25 from the statement filed three weeks later (re-run of the held cards, 2026-10-18)."""
    if tagged is not None and tagged.period:
        return tagged.period
    if _RESULTS_STATEMENT.search(text[:20000]) or amounts(text) >= FIGURE_PAGE_AMOUNTS:
        return statement_quarter(text, filed_on)
    return None


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
    if event_type == "CAPEX" and _RESUMED.search(head) and not _NEW_CAPACITY.search(head):
        return "OTHER"
    # live review 3 (2026-10-20): an ESG score typed DEBT_RATINGS, a vendor listing typed LITIGATION_REGULATORY, an
    # investment in a captive power company typed PRODUCT_LAUNCH
    if event_type == "DEBT_RATINGS" and _ESG.search(head) and not _CREDIT_RATING.search(head):
        return "OTHER"
    if event_type == "LITIGATION_REGULATORY" and _VENDOR.search(head) and not _CASE_WORDS.search(head):
        return "OTHER"
    if event_type == "PRODUCT_LAUNCH" and _CAPTIVE_POWER.search(head):
        return "M_AND_A"
    return event_type


_ESG = re.compile(r"\besg\b|sustainability\s+(?:rating|score)|environmental,?\s+social", re.I)
_CREDIT_RATING = re.compile(r"\b(?:crisil|icra|care\s*(?:ratings|edge)?|ind-?ra|india\s+ratings|acuit[eé]|brickwork|infomerics)\b"
                            r"[^.]{0,80}\b(?:A{1,3}[+-]?|BB+[+-]?|A1\+?|D)\b", re.I)
_VENDOR = re.compile(r"\b(?:approved|registered|empanel\w*|enlist\w*|listed)\s+(?:as\s+(?:an?\s+)?)?(?:vendor|supplier|bidder)"
                     r"|\bvendor\s+(?:registration|listing|approval|code)", re.I)
_CASE_WORDS = re.compile(r"\b(?:penalt|show[- ]cause|demand|order\s+passed|court|tribunal|nclt|notice|summons|fine[ds]?\b|levied)", re.I)
_CAPTIVE_POWER = re.compile(r"\bcaptive\b[^.]{0,60}\b(?:power|solar|wind|energy|renewable)|(?:power|solar|wind|energy)\b[^.]{0,40}"
                            r"\b(?:spv|special purpose vehicle)\b[^.]{0,60}\b(?:invest\w*|acqui\w*|stake|shares)", re.I)
_DEMERGER = re.compile(r"\bde-?merg\w*|\bscheme\s+of\s+arrangement\b[^.]{0,80}\bspin", re.I)


# A unit back in service after an outage, repair or flood is not capacity added: NHPC's Teesta-V unit resuming came by
# the "commencement of commercial production" rule as CAPEX, and the card said it "boosts generation capacity" (live
# review 1, 2026-10-20). Words of a new plant or added capacity keep it CAPEX.
_RESUMED = re.compile(r"\b(resum(?:ed|es|ption|ing)|restor(?:ed|ation|es)|re-?start(?:ed)?|back (?:in|into) (?:service|operation)"
                      r"|after (?:the )?(?:outage|shutdown|shut-down|breakdown|flood|repair|maintenance))\b", re.I)
_NEW_CAPACITY = re.compile(r"\b(new|additional|greenfield|brownfield|expansion|expanded|capacity addition|added capacity"
                           r"|debottleneck\w*)\b", re.I)


# A headline says who did what: "WaveRise" (the acquirer's name from the exchange's subject line) was Novartis India's
# whole headline for a change of control (live review, 2026-10-20). Four words is the shortest that does.
HEADLINE_MIN_WORDS = 4


def headline_form(out: Pass2Output) -> list[str]:
    """A headline too short to say what happened, as a problem for the second provider to rewrite."""
    headline = ((out.card.headline if out.card else "") or "").replace("**", "").strip()
    if out.card is not None and len(headline.split()) < HEADLINE_MIN_WORDS:
        return [f'Headline "{headline}" does not say what happened: write who did what, with the main figure']
    return []


# A director or KMP appointed or re-appointed, in a card's own headline. A board outcome carrying only that came as
# OTHER and escaped D30 (CSB Bank re-appointing its MD & CEO, live review 2026-10-20); as MANAGEMENT_CHANGE it gets
# no card unless the MD, CEO or CFO is leaving (`top_exit`).
APPOINTMENT = re.compile(
    r"\b(re-?appoint\w*|appoint\w*|re-?designat\w*)\b.{0,100}\b(director|managing director|\bmd\b|chief executive|"
    r"\bceo\b|chief financial|\bcfo\b|company secretary|compliance officer|key managerial|\bkmp\b|chairman|chairperson)"
    r"|\b(director|managing director|\bmd\b|\bceo\b|\bcfo\b|company secretary|chairman|chairperson)\b.{0,60}"
    r"\b(re-?appoint\w*|appoint\w*)\b", re.I)


def check_quotes(out: Pass2Output, text: str, news_id: str = "", unit: int | None = None, reading: str = "",
                 memory: str = "") -> tuple[list[str], list[str], list[str], list[str]]:
    """Every what_happened fact carries the filing's own sentence, checked in code.

    A fact whose quote is not in the filing is dropped **only when its figures are not in the filing
    either**: that is the invented claim the audit found most of ("EBITDA rose 31.8% to ₹287 Cr",
    "will cease to be a subsidiary"). A fact built from a table, whose figures are all there but whose
    quote is a composition rather than one row ("PAT ₹0.53 Cr, down 80% YoY and 98% QoQ"), is true and
    is kept, reported for the second opinion to quote properly. A fact with no quote at all is only
    reported: until every model fills the field, holding those cards would send all of them to a second
    provider for nothing. Returns (problems, facts with no quote, facts dropped) so the card records all
    three: a dropped fact that was true is a defect the audit must be able to see."""
    card = out.card
    if card is None or not text:
        return [], [], [], []
    index = SourceIndex(text)
    # What the statement says its figures are in - a card writes crore. It must come from the document
    # alone: the XBRL table is put in front of the text and says crore itself, which leaves the two
    # declarations disagreeing, so reading it from `text` returned nothing for every filing that has an
    # XBRL file and the conversion never ran where it was needed most.
    unit = unit if unit is not None else declared_unit(text)
    problems, missing_quote, dropped, kept, paraphrased = [], [], [], [], []
    for fact in card.what_happened:
        label = fact.text.replace("**", "")[:60]
        if not fact.quote:
            missing_quote.append(label)
            kept.append(fact)
            continue
        quote = fact.quote
        if not gate.quote_found(quote, text, reading):
            # A word dropped or changed in the quote: the filing's sentence it copies is what its figures
            # answer to. A fact with no large figure ("re-appointed for 5 years") used to be dropped here.
            near = gate.quote_near(quote, text, reading)
            if near is not None:
                paraphrased.append(f'"{label}" quotes the filing with small differences')
                quote = near
            else:
                # Its figures decide - every amount at the declared unit, percentage, multiple, date and rating -
                # or with none, its names: 50 of the 60 facts dropped here in audit round 2 were true, and the
                # old test looked only at amounts above 31 (dropped_facts.md)
                source = f"{text}\n{reading}" if reading else text
                checked, unprinted = gate.unprinted_anchors(fact.text, source, unit, None if reading else index)
                what = "figures"
                if not checked:
                    checked, unprinted = gate.unprinted_names(fact.text, source)
                    what = "names"
                if checked and not unprinted:
                    paraphrased.append(f'"{label}" is in the filing but its quote is not the filing\'s own words '
                                       f"(its {what} are)")
                    kept.append(fact)
                else:
                    why = f"; not found: {', '.join(unprinted[:4])}" if unprinted else ""
                    # in full, with its quote: 60 characters left 3 of round 2's 60 drops impossible to judge
                    dropped.append(f'"{fact.text.replace("**", "")}" (neither its quote nor its figures are in '
                                   f'the filing{why}; quoted: "{(fact.quote or "")[:300]}")')
                continue
        claim = fact.text.replace("**", "")
        missing = gate.numbers_in_quote(claim, quote, gate.quote_unit(quote, text, unit))
        missing, siblings = gate.figures_in_same_block(missing, quote, text, unit, claim)
        if siblings:
            paraphrased.append(f'"{label}" also states {", ".join(siblings[:4])}, from another row of '
                               "the same table")
        precise = gate.stated_precisely(missing, claim, text, unit)
        if precise:
            missing = [m for m in missing if m not in precise]
            paraphrased.append(f'"{label}" also states {", ".join(precise[:4])}, from elsewhere in the filing')
        compared = gate.compared_figures(missing, claim, memory, text, unit)
        if compared:
            missing = [m for m in missing if m not in compared]
            paraphrased.append(f'"{label}" compares with {", ".join(compared[:4])}, from memory or the filing')
        if missing:
            problems.append(f'"{label}" states {", ".join(missing[:4])}, which its own quote does not')
        kept.append(fact)
    if kept:
        card.what_happened = kept
    elif dropped:  # a card needs one fact: keep them all, marked, rather than publishing nothing
        problems.append("no fact carries a quote found in the filing")
        dropped = []
    if dropped:
        log.info("facts dropped from %s (%s): %s", news_id or "?", out.event_type, dropped)
    return problems + [f"dropped: {d}" for d in dropped], missing_quote, dropped, paraphrased


def check_quoted_numbers(out: Pass2Output, text: str, unit: int | None = None, reading: str = "",
                         memory: str = "") -> tuple[list[str], list[str], list[str]]:
    """Each figure on a card checked against the sentence that card says it came from.

    `what_happened` has carried a quote since D23 and is checked this way already. The fields that state
    the headline numbers - key_numbers, notable_changes, why_it_matters - had none, so their figures were
    only ever looked for in the whole filing, and on a long one that is weak: an invented whole-crore
    figure is accepted 40% of the time against 8% at one decimal and 3% at two (test_cards.py), because a
    round number lands on an unrelated line within its own rounding. Inside a single sentence there is
    nothing to land on.

    The comparison is unit-aware rather than digit-by-digit, because the card writes crore and the filing
    often writes million or lakh: "₹45.79 Cr" is the right reading of "457.86 million" and must pass,
    while "₹458 Cr" is the 10x misreading and must not. Returns (problems, items with no quote).
    """
    card = out.card
    if card is None or not text:
        return [], [], []
    problems, unquoted, elsewhere = [], [], []
    for kind, label, claim, quote, siblings_count in _quoted_claims(card):
        if not quote:
            unquoted.append(f"{kind}: {label}")
            continue
        if not gate.quote_found(quote, text, reading):
            # A word dropped or changed is the model's wording, not a figure of its own: the sentence it
            # copies is found and the card's figures are checked against that (gate.quote_near).
            near = gate.quote_near(quote, text, reading)
            if near is None:
                near = _table_line_quoted(quote, text)
            if near is None and kind != "why it matters":
                near = _row_quoted(quote, claim, text, unit)
            # Not for a "why it matters" sentence: it reads a table's figures into a claim (a period, a group), and two of
            # the three wrong figures the rules let through were such sentences (independent check, 2026-10-20)
            if near is None and kind != "why it matters" and gate.quote_scattered(quote, text, reading):
                # a table cell quoted unwrapped: its figures are the page's (exact tokens, in the page's order), and the
                # card's figures must be among the quote's own, not merely near it (0.0702% from the next row, 2026-10-20)
                near = quote
            if near is None:
                problems.append(f'{kind} "{label}" quotes a sentence that is not in the filing')
                continue
            elsewhere.append(f'{kind} "{label}" quotes the filing with small differences')
            quote = near
        # The same comparison `what_happened` gets, and for the same reasons: the quoted row is read at
        # the unit the filing declares, so "16.53 Cr" passes against a row reading 1,653 in lakhs while
        # the ten-times misreading does not, and a period label or a day of the month is not a figure.
        # These three fields had their own copy of the rule and it had fallen behind: on 2026-10-17 it
        # was reporting figures that were right thirteen times in twenty filings.
        missing = gate.numbers_in_quote(claim, quote, gate.quote_unit(quote, text, unit))
        siblings: list[str] = []
        if siblings_count:
            missing, siblings = gate.figures_in_same_block(missing, quote, text, unit, claim)
            precise = gate.stated_precisely(missing, claim, text, unit)   # a sentence, not a key number's row
            if precise:
                missing = [m for m in missing if m not in precise]
                elsewhere.append(f'{kind} "{label}" also states {", ".join(dict.fromkeys(precise))[:60]}, '
                                 "from elsewhere in the filing")
        # A figure it sets its own against - the order book, last year's loss - is the company's known figure,
        # for a key number as for a sentence: its own figure is still the one its row must carry.
        compared = gate.compared_figures(missing, claim, memory, text, unit)
        if compared:
            missing = [m for m in missing if m not in compared]
            elsewhere.append(f'{kind} "{label}" compares with {", ".join(dict.fromkeys(compared))[:60]}, '
                             "from memory or the filing")
        if siblings:
            elsewhere.append(f'{kind} "{label}" also states {", ".join(dict.fromkeys(siblings))[:60]}, '
                             "from another row of the same table")
        if missing:
            problems.append(f'{kind} "{label}" states {", ".join(dict.fromkeys(missing))[:90]}, '
                            "which its own quote does not")
    return problems, unquoted, elsewhere


# A line of the machine-tagged XBRL table as `XbrlResult.table` writes it, and the changes a model adds after it
_TABLE_LINE = re.compile(r"^\s*-?\s*([a-z_]+ (?:Q[1-4]|H[12]|9M)?FY\d{2}: -?[\d.,]+ ?(?:Cr|%|₹/share))\s*(.*)$")
_ADDED_CHANGES = re.compile(r"^(?:,\s*(?:YoY|QoQ)\s*[+-]?[\d.]+\s*%)+\s*$")


def _table_line_quoted(quote: str, text: str) -> str | None:
    """The XBRL table's own line when a quote is that line with a YoY / QoQ change added after it, else None.

    The table prints a computed line such as EBITDA with no change beside it, and the model quotes the line with
    the change it worked out ("- ebitda Q2FY26: 23.88 Cr, QoQ -12.3%"). Novartis India's Q2FY26 card was held
    for that alone with every figure right (live review, 2026-10-20). The figure still answers to the line;
    a change is checked against the filing elsewhere (grounding), so only a change may follow it."""
    m = _TABLE_LINE.match(quote or "")
    if not m or not _ADDED_CHANGES.match(m.group(2) or ","):
        return None
    line = m.group(1)
    return line if gate.quote_found(line, text) else None


def _row_quoted(quote: str, claim: str, text: str, unit: float | None) -> str | None:
    """The filing's line a key number's quote was built from, when the quote itself is not in the filing: a line that
    carries the key number's figures (at the filing's unit) and either sits whole inside the quote or shares a run of
    four words with it.

    A table's row reaches the text as fragments or with its wrapped cells interleaved, and the model quotes the row as
    it reads it: Novartis India's "Acquirer 2: 25,47,189 10.32% 10.32%" is "Acquirer 2:" and "25,47,189 10.32% 10.32%"
    on two lines, Magellanic's objects table puts "150.00 24 Months" on the line of the row's first words. Four right
    cards were held this way (live reviews 1-2, 2026-10-20). The figure still has to be on the one line."""
    flat_quote = gate._flat(quote or "")
    words = flat_quote.split()
    runs = {" ".join(words[i:i + 4]) for i in range(len(words) - 3)}
    for line in (text or "").splitlines():
        flat_line = gate._flat(line)
        tokens = flat_line.split()
        if len(tokens) < 2 or not any(ch.isdigit() for ch in flat_line):
            continue
        inside = flat_line in flat_quote
        shared = any(" ".join(tokens[i:i + 4]) in runs for i in range(len(tokens) - 3))
        # the row's figures in the quote's order: "PPA Realisation 5.93 5.53" for the row's "5.53 5.93" made FY26 a
        # Q1FY26 (independent check, 2026-10-20); a row's order is its columns' periods
        quoted = [w for w in gate._norm(words)[0] if gate._has_digit(w)]
        in_line = [w for w in gate._norm(tokens)[0] if gate._has_digit(w)]
        if (inside or shared) and gate._in_order([w for w in quoted if w in in_line], in_line) \
                and not gate.numbers_in_quote(claim, line, gate.quote_unit(line, text, unit)):
            return line
    return None


def _quoted_claims(card) -> list[tuple[str, str, str, str | None, bool]]:
    """(field, label, the text whose figures are checked, the quote, whether a sibling row may answer).

    A key number and a notable change name one line of the statement and state its figure, so that
    figure has to be in that line: this is where an invented whole-crore number is caught, and where
    "Rs 458 Cr" quoting a row of 457.86 million has to fail even though 4,583 million is printed a few
    rows below. A sentence is different - it reports the row it quotes and leans on others around it -
    so there a figure from a sibling row of the same table is reported rather than held.
    """
    out = []
    for key in card.key_numbers:
        out.append(("key number", key.label or "", f"{key.value or ''} {key.change or ''}", key.quote, False))
    for change in card.notable_changes or []:
        # Only what this period is: a change quotes the line it is reporting, and the figure it is
        # measured against belongs to an earlier filing or to memory, which is where it is checked.
        # Asking for both put "finance_cost Rs 0.11 Cr (Q2FY26) -> Rs 0.98 Cr (Q3FY26)" against a quote
        # reading "finance_cost Q3FY26: 0.98 Cr" and reported the 0.11 as missing.
        # Nor is its change, when the change is the line's own arithmetic: "+₹246.77 Cr" from ₹34.96 Cr
        # to ₹281.73 Cr is not a figure any row prints (grounding.change_derived).
        derived = change_derived(change.previous, change.current, change.change)
        out.append(("notable change", change.metric or "",
                    f"{change.current or ''} {'' if derived else change.change or ''}", change.quote, False))
    for insight in card.why_it_matters:
        if insight.basis == "FILING":  # a point resting on memory is checked against memory, not the filing
            out.append(("why it matters", (insight.text or "")[:48], insight.text or "", insight.quote, True))
    return out


def gate_issues(out: Pass2Output, card, sources: tuple[str, ...] = ()) -> list[str]:
    """Amounts that cannot be crore, and a fundraise whose size does not follow from its shares and price."""
    issues = [f"{n} Cr is not a crore figure (a rupee amount written in full)" for n in gate.impossible_crore_amounts(_card_texts(out))]
    deal = card.deal_value
    if deal and deal.amount_cr and sources:
        problem = gate.deal_amount_context(deal.amount_cr, sources[0])
        if problem:
            issues.append(problem)
    if deal and deal.kind == "FUNDRAISE":
        for action in out.dossier_delta.capital_actions:
            problem = gate.issue_size_mismatch(deal.amount_cr, action.new_shares, action.issue_price)
            if problem:
                issues.append(problem)
    return issues


_RUPEE_CRORE = re.compile(r"₹\s*(\d[\d,]*(?:\.\d+)?)\s*(?=cr\b|crores?\b)", re.I)


_MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
_CONTINUES = re.compile(r"(?:in\s+continuation\s+(?:to|of)|further\s+to|with\s+reference\s+to|in\s+furtherance\s+(?:to|of))\s+"
                        r"(?:our|the\s+company'?s)\s+(?:earlier\s+|previous\s+)?(?:intimation|letter|disclosure|announcement)s?"
                        r"\s+dated\s+([^;\n]{6,30})", re.I)
_DAY_MONTH_YEAR = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?[\s.\-/]+([a-z]{3,9}|\d{1,2})[\s.,\-/]+(\d{4})", re.I)
_MONTH_DAY_YEAR = re.compile(r"([a-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.I)


def _stated_date(text: str) -> date | None:
    """A date as Indian filings write it: "08th September 2026", "8 Sep, 2026", "08.09.2026", "September 8, 2026"."""
    for rx, order in ((_DAY_MONTH_YEAR, (0, 1, 2)), (_MONTH_DAY_YEAR, (1, 0, 2))):
        m = rx.search(text)
        if not m:
            continue
        day, month, year = (m.group(i + 1) for i in order)
        month = int(month) if month.isdigit() else _MONTHS.get(month[:3].lower())
        try:
            return date(int(year), month, int(day)) if month else None
        except ValueError:
            return None
    return None


def continued_deal(out: Pass2Output, view: dict | None, text: str) -> list[str]:
    """A filing "in continuation to our earlier intimation dated 08th September 2026" moves the deal of that date on:
    when memory holds exactly one deal of the same kind from that day and the writer left it as a new one, it becomes
    that deal's next stage. Round 5 (2026-10-19): Ceigall's LoI for the Bihar Lot-4 order was told as a second order
    from the department, and the order flow counted the one order twice."""
    deal = out.card.deal_value if out.card else None
    if deal is None or deal.updates_deal_id or not view:
        return []
    m = _CONTINUES.search(text or "")
    when = _stated_date(m.group(1)) if m else None
    if when is None:
        return []
    same_day = [d for d in view.get("deals", []) if d.get("id") and d.get("kind") == deal.kind
                and str(d.get("date") or d.get("as_of") or "")[:10] == when.isoformat()]
    if len(same_day) != 1:
        return []
    deal.updates_deal_id = same_day[0]["id"]
    return [f"deal is the next stage of {same_day[0]['id']} ({when.isoformat()}): the filing continues that intimation"]


def deal_echo_slips(out: Pass2Output, text: str) -> list[str]:
    """A card amount that is its own deal size times 10 or 100 (or divided), printed nowhere in the filing, is the deal
    size with its decimal moved: Anlon's ₹153.3 Cr share swap was "₹1,533 Cr" in the timeline line, which memory then
    carried into two later cards (round 4). Set to the deal size. Returns what changed."""
    deal = out.card.deal_value if out.card else None
    if deal is None or not deal.amount_cr or deal.amount_cr <= 0:
        return []
    index = SourceIndex(text or "")
    notes: list[str] = []

    def fix(value_text: str | None) -> str | None:
        if not value_text:
            return value_text

        def swap(m: re.Match) -> str:
            raw = m.group(1)
            value = float(raw.replace(",", ""))
            decimals = len(raw.split(".")[1]) if "." in raw else 0
            for k in (10, 100, 0.1, 0.01):
                if abs(value - deal.amount_cr * k) <= max(0.006 * value, 0.05) and abs(value - deal.amount_cr) > 0.01 * deal.amount_cr                         and not index.stated_crore(value, decimals, (1, 10, 100, 10_000, 1e7)):
                    right = f"{deal.amount_cr:,.2f}".rstrip("0").rstrip(".")
                    notes.append(f"₹{raw} Cr -> ₹{right} Cr (the card's own deal size, decimal moved)")
                    return m.group(0).replace(raw, right)
            return m.group(0)

        return _RUPEE_CRORE.sub(swap, value_text)

    card = out.card
    card.headline, card.takeaway, card.core_catalyst = fix(card.headline), fix(card.takeaway) or "", fix(card.core_catalyst)
    for fact in card.what_happened:
        fact.text = fix(fact.text) or fact.text
    for insight in card.why_it_matters:
        insight.text = fix(insight.text)
    for key in card.key_numbers:
        key.value = fix(key.value)
    out.timeline_entry = fix(out.timeline_entry) or out.timeline_entry
    return notes


_HOLDERS = re.compile(r"\b(?:share|stock|unit|equity)\s*holders?\b|\bshareholders?\b|\bpromoters?\b|\bmembers\b", re.I)


def apply_deal_guards(out: Pass2Output, filing: Filing, history: list[dict], balance_sheet: list[dict],
                      text: str = "") -> list[str]:
    """A deal size that is the company's own revenue, net worth or share capital is dropped; a terminated
    or withdrawn deal is marked CANCELLED. Returns what was done."""
    deal = out.card.deal_value if out.card else None
    if deal is None:
        return []
    # A rating covers the company's borrowing lines: "₹2,100 Cr of facilities" is not a deal it made, and read as one
    # it was set against revenue and then held as an amount from an instruments clause (Hind Copper's ICRA upgrade,
    # laptop re-check 2026-10-19)
    if out.event_type == "DEBT_RATINGS":
        out.card.deal_value = None
        log.info("deal guards for %s: a rating's facilities are not a deal (₹%s Cr dropped)", filing.news_id, deal.amount_cr)
        return [f"deal value dropped: a rating card's ₹{deal.amount_cr} Cr is the rated facilities, not a deal"]
    notes = []
    known = {"financial_metrics": history + [m.model_dump() for m in out.dossier_delta.financial_metrics],
             "balance_sheet": balance_sheet}
    computed = gate.tranche_total_cr(deal.tranches, text)
    if computed and (not deal.amount_cr or abs(deal.amount_cr - computed) > 0.03 * computed):
        notes.append(f"deal size set to ₹{computed:,.2f} Cr from the buyers' shares x price (the model gave {deal.amount_cr})")
        deal.amount_cr = computed
    name = None if computed else gate.deal_is_company_figure(deal.amount_cr, known)  # shares x price is exact
    if name:
        notes.append(f"deal size {deal.amount_cr:g} Cr dropped: it is the company's {name}")
        out.card.deal_value = None
        deal = None
    # the filing's own text must also say so: Orient Bell's ₹1.07 Cr power investment was marked cancelled from the
    # exchange's subject line alone (live review 3)
    if deal is not None and deal.stage != "CANCELLED" and gate.is_terminated(filing.headline, filing.subject) \
            and (not text or gate.is_terminated(text[:20000])):
        notes.append("deal marked cancelled: the filing terminates or withdraws it")
        deal.stage = "CANCELLED"
    if deal is not None and deal.stage == "CANCELLED" and text and not gate.is_terminated(text[:20000]):
        notes.append("deal not cancelled: the filing's text terminates nothing")
        deal.stage = "OTHER"
    if deal is not None and text:
        stage = gate.supported_stage(deal.stage, text[:40000])
        if stage != deal.stage:
            notes.append(f"deal stage {deal.stage} -> {stage}: the filing's text does not say so")
            deal.stage = stage
    # a company's own capex has no shareholders on the other side: Heritage's ₹250 Cr dairy capex showed "Existing
    # shareholders of Heritage Novandie Foods" as its counterparty (design audit, 2026-10-20)
    if deal is not None and deal.kind == "CAPEX" and deal.counterparty and _HOLDERS.search(deal.counterparty):
        notes.append(f"capex counterparty dropped: {deal.counterparty!r} are holders, not a party to the capex")
        deal.counterparty = None
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
    quant = check_quant(card.quantified_impact, *sources)
    # Figures code computed from the filing's own: an impact verified from sourced inputs, and a deal's
    # size from its buyers' shares x price (apply_deal_guards). SML's ₹554.65 Cr - 85,33,053 shares at ₹650
    # - was held as a number the filing does not print (loop round 3b, 2026-10-17).
    derived = [i["computed"] for i in quant.items
               if i.get("check") == "VERIFIED" and not i.get("unsourced_inputs") and i.get("computed") is not None]
    if card.deal_value and card.deal_value.tranches and sources:
        derived.append(gate.tranche_total_cr(card.deal_value.tranches, sources[0]))
    grounding = check_card(card, *sources, derived=derived)
    checked = grounding.checked + quant.checked_inputs
    ungrounded = grounding.ungrounded + quant.unsourced
    score = 1.0 if checked == 0 else round(1 - len(ungrounded) / checked, 3)
    return CardChecks(score, checked, ungrounded, quant, check_claims(card, *sources),
                      grounding.headline_ungrounded, grounding.amounts_ungrounded,
                      scale_issues(out.dossier_delta.financial_metrics, history or [])
                      + margin_issues(out.dossier_delta.financial_metrics, card.key_numbers)
                      + gate_issues(out, card, sources))


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
        nse: "nse_api.NseClient | None" = None,
    ):
        self.settings = settings
        self.sink = sink
        self._prices = PriceStore(settings.price_dir) if settings.price_dir and settings.price_dir.is_dir() else None
        self._buckets = settings.load_toml("market.toml")["size_buckets"]
        self.gateway = gateway
        # BSE is a backup source only (owner, 2026-10-19: everything on NSE): its client is made the first time
        # something asks for it (DISCOVERY_SOURCE=bse, a BSE attachment), so an NSE run never calls BSE at all
        self._bse = bse
        # NSE discovery and attachments, and annual reports' XBRL (annual_xbrl). None with BSE discovery reads annual
        # reports from the PDF alone, as tests do.
        self.nse = nse
        self._nse_universe: universe.NseUniverse | None = None
        if nse is not None:
            raw.attach(nse, sink, "nse", settings)
        self._annual_lists: dict[str, tuple[list, str]] = {}   # symbol -> NSE's annual-report XBRL list and when it was read
        self._event_days: dict[str, list] = {}   # IST day -> NSE's event XBRL files broadcast that day (this run)
        self._packer = None
        if settings.pass2_pack > 1 and gateway.has_route("pass2_packed"):
            from .ai.packer import Packer

            self._packer = Packer(gateway, size=settings.pass2_pack, wait_s=settings.pass2_pack_wait_s)
        self._nse_refused = False                  # NSE refused the address: no more calls this run
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
        self._network_failures = 0   # attachment downloads that failed on the network in a row (no attempt spent)
        self._unreachable = 0
        self._busy = 0
        self._busy_halt = False
        self._blocked: SourceBlockedError | None = None
        self._usage_lock = Lock()
        self._commit_lock = Lock()  # companies commit from worker threads; the R2 day archive is read-modify-write
        self._universe: tuple[set[str], float] | None = None
        self._examples: dict[tuple[str, str], dict[str, list[dict]]] = {}
        self._learned: dict | None = None   # Loop 1 state: post-mortem queue, lessons, dampened categories
        self._bodies: dict[str, list[tuple[str, str, duplicates.Body]]] = {}  # scrip -> (filed_at, news_id, body) this run
        self._held_this_run: set[str] = set()   # news_ids whose card this run held (D20: not the quarter's card)
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
        if self._on_nse():
            filings = self.nse.announcements(day, scrip_for=self._nse_map().scrip_for)
        else:
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
            for filing in self._company_announcements(scrip, start, end):
                by_day.setdefault(filing.filing_date, []).append(filing)
            for key, filings in sorted(by_day.items()):
                noise = self._load_noise(key)
                found += self._record(key, filings, noise, self.sink.known_ids(key) | set(noise))
            start = end + timedelta(days=1)
        return found

    def retriage_company(self, scrip: str, day_from: date, day_to: date) -> list[str]:
        """Apply today's rules to one company's filings that an earlier rule left in the noise file.

        Discovery skips a filing already in its day's noise file, so narrowing a drop or date rule never reached
        the filings it had dropped (the "AGM notice" rule took 12 annual reports filed with their notice, F57).
        The rows are fetched again from BSE, for the subject and symbol the noise row does not keep; each one
        today's rules no longer drop leaves the noise file and is queued. Returns their news ids."""
        queued: list[str] = []
        start = day_from
        while start <= day_to:
            end = min(day_to, start + timedelta(days=30))
            by_day: dict[str, list[Filing]] = {}
            for filing in self._company_announcements(scrip, start, end):
                by_day.setdefault(filing.filing_date, []).append(filing)
            for key, filings in sorted(by_day.items()):
                noise = self._load_noise(key)
                freed = [f for f in filings if f.news_id in noise and not _still_noise(self.rules.classify(f), f, noise[f.news_id])]
                if not freed:
                    continue
                for filing in freed:
                    del noise[filing.news_id]
                self._save_noise(key, noise)
                self._record(key, freed, noise, self.sink.known_ids(key))
                queued += [f.news_id for f in freed]
            start = end + timedelta(days=1)
        return queued

    @property
    def bse(self) -> BseClient:
        if self._bse is None:
            self._bse = BseClient()
            raw.attach(self._bse, self.sink, "bse", self.settings)
        return self._bse

    @bse.setter
    def bse(self, client: BseClient) -> None:
        self._bse = client

    def _on_nse(self) -> bool:
        return self.settings.discovery_source == "nse"

    def _nse_map(self) -> universe.NseUniverse:
        """NSE row -> our company key, from the universe file (loaded once per run). Without the file NSE discovery
        cannot tell our companies apart, so it stops and says how to build it."""
        if self._nse_universe is None:
            if self.nse is None:
                raise RuntimeError("NSE discovery needs an NSE client")
            self._nse_universe = universe.load_nse(self.sink)
            if not self._nse_universe.built:
                raise RuntimeError("no NSE universe file yet: run `python -m bse_intel sync-universe` first")
        return self._nse_universe

    def _company_announcements(self, scrip: str, start: date, end: date) -> list[Filing]:
        """One company's filings over a range, from the discovery source."""
        if not self._on_nse():
            return list(self.bse.announcements(start, end, scrip=scrip))
        nse_map = self._nse_map()
        symbol = nse_map.symbol_for(scrip)
        if not symbol:
            log.warning("%s is not on NSE's list in the universe file; nothing to discover", scrip)
            return []
        return self.nse.announcements(start, end, symbol=symbol, scrip_for=nse_map.scrip_for)

    def _attachment(self, url: str, max_bytes: int) -> bytes | None:
        """A filing's attachment from whichever exchange serves it."""
        if self.nse is not None and "nseindia.com" in url:
            return self.nse.fetch(url, max_bytes=max_bytes)
        return self.bse.download(url, max_bytes=max_bytes)

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
            if filing.scrip_code.startswith("NSE:"):
                # Listed on NSE but not in our company master (no market cap to place it against the floor).
                self.stats.outside_universe += 1
                filing.reason = "not in the company master (listed on NSE only)"
                noise[filing.news_id] = _noise_row(filing)
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
                history_first: bool = False, only: set[str] | None = None) -> list[Outcome]:
        """Work the queue for a date window, oldest first, companies in parallel.

        With ``history_first`` (the live window), a company's unanalysed history is processed before
        its new filing, so the live card is written with that company's memory. Companies with
        little history go first, and each company's results are committed as soon as it finishes.

        With ``only``, nothing outside that set of news ids is analysed. That is how a measured round
        is run: the same filings whose cards an audit called wrong, re-read after a fix, so the before
        and after are the same documents rather than two different samples. Returns the outcomes, committed.
        """
        after, done = ("", ""), []
        while time.monotonic() < deadline and not self._halted(bulk):
            rows = self.sink.pending_filings(day_from, day_to, self.settings.max_attempts, BATCH, after)
            if not rows:
                return done
            after = (rows[-1]["filed_at"], rows[-1]["news_id"])
            groups: OrderedDict[str, list[Filing]] = OrderedDict()
            for row in rows:
                if only is not None and row["news_id"] not in only:
                    continue
                if row["news_id"] not in self._tried:
                    groups.setdefault(row["scrip_code"], []).append(Filing.model_validate(row))
            if history_first:
                jobs = self._live_jobs(groups, day_from, deadline, bulk, memory_complete)
            else:
                jobs = {s: partial(self._process_group, g, deadline, bulk, memory_complete) for s, g in groups.items()}
            done += [o for outcomes in self._run_parallel(jobs).values() for o in outcomes]
        return done

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
        outcome = self._attempt(filing, bulk, memory_complete, deadline)
        status = outcome.update.get("status")
        held = bool(outcome.card and outcome.card.get("held"))
        if held:
            with self._lock:
                self._held_this_run.add(filing.news_id)
        if status != "ANALYZED" or held:
            # a held card is no more the quarter's card in this run than in memory (_same_results_quarter)
            self._release_claims(filing.news_id, status)
        # Only a verdict that the filing has no card of its own; the XBRL shareholding path and the timeline tier
        # write memory and report NOT_MATERIAL too.
        if status in ("NOT_MATERIAL", "DUPLICATE") and str(outcome.update.get("reason", "")).startswith(
                ("pass1:", "pass2:", "duplicate of")):
            self._forget_in_memory(filing)
        return outcome

    def _forget_in_memory(self, filing: Filing) -> None:
        """What an earlier analysis of this filing put in memory, taken out now that it ends without a card."""
        try:
            dossier = self.sink.get_dossier(filing.scrip_code)
            if dossier and forget_filing(dossier, filing.news_id):
                self.sink.put_dossier(filing.scrip_code, dossier)
                log.info("memory: %s's facts taken out; it now ends without a card", filing.news_id)
        except Exception as exc:  # memory hygiene must not fail the filing; a later run tries again
            log.warning("could not take %s's facts out of memory: %s", filing.news_id, exc)

    def _release_claims(self, news_id: str, status: str | None) -> None:
        """What a filing claimed at the start of its analysis, given back when it ends without a card.

        A results filing claims its quarter before pass 2 (D20), so two workers cannot both take it. Prism's
        trading-window notice and Ahluwalia's board-meeting intimation, typed RESULTS by pass 1, claimed the
        quarter, were then found not material, and kept it: the real statements filed after them were marked
        duplicates of a notice and the quarter had no card (funnel, 2026-10-18). A filing that failed or was
        deferred also gives back its text, so a copy of it later in the run is analysed rather than marked
        a duplicate of a filing that may never get a card."""
        with self._lock:
            for key in [k for k, owner in self._results_quarters.items() if owner == news_id]:
                del self._results_quarters[key]
            if status in ("FAILED", "PENDING"):
                for scrip, bodies in self._bodies.items():
                    self._bodies[scrip] = [b for b in bodies if b[1] != news_id]

    def _attempt(self, filing: Filing, bulk: bool, memory_complete: bool, deadline: float | None = None) -> Outcome:
        pass1 = "pass1_bulk" if bulk else "pass1"
        if filing.route == "PASS1" and pass1 in self._exhausted:
            return self._deferred(filing, "deferred: AI quota ceilings")
        for attempt in range(TRANSIENT_RETRIES + 1):
            try:
                outcome = self.analyze(filing, bulk, memory_complete)
                with self._lock:
                    self._busy = 0
                    self._unreachable = 0
                return outcome
            except SinkUnavailable as exc:
                # The site is not there. Leave the filing exactly as it was rather than spend one of its
                # attempts, and stop the run after a few: every further filing would fail the same way.
                with self._lock:
                    self._unreachable += 1
                    if self._unreachable >= MAX_UNREACHABLE and not self._blocked:
                        self._blocked = SourceBlockedError(
                            f"the platform API did not answer for {self._unreachable} filings in a row; "
                            f"stopping this run with the work still queued. Is the web server running? ({exc})")
                        self.stats.stopped_reason = str(self._blocked)[:300]
                        log.error("stopping: %s", self._blocked)
                return self._deferred(filing, "deferred: the platform did not answer")
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
            except EventXbrlPending as exc:
                return self._deferred(filing, f"deferred: {exc}")
            except SourceBlockedError as exc:
                # NSE answered 401, 403 or 429 (or BSE refused): stop the run politely; the work stays queued and no
                # filing's attempt is spent (owner, 2026-10-18)
                with self._lock:
                    if not self._blocked:
                        self._blocked = exc
                        self.stats.stopped_reason = f"source refused the session: {exc}"[:300]
                        log.error("stopping: %s", exc)
                return self._deferred(filing, "deferred: the source refused the session")
            except AttachmentError as exc:
                if not exc.refused:
                    # A network failure or a server error: the file is tried again on a later run and the filing's
                    # attempts are not spent on it (owner, 2026-10-18). Several in a row stop the run.
                    with self._lock:
                        self._network_failures += 1
                        isolated = self._network_failures == 1
                        if self._network_failures >= MAX_NETWORK_FAILURES and not self._blocked:
                            self._blocked = SourceBlockedError(
                                f"{self._network_failures} attachment downloads failed on the network in a row; "
                                "stopping this run with the work still queued")
                            self.stats.stopped_reason = str(self._blocked)[:300]
                    times = _deferrals(filing.last_error) + 1
                    if isolated and times > MAX_DEFERRALS:
                        # This one file has failed on several runs while the downloads around it worked: a broken
                        # file, not an outage. It now spends an attempt, so it is not fetched forever (2026-10-19).
                        return self._failed(filing, exc)
                    return self._deferred(filing, f"deferred {times}x: attachment download failed ({exc})"[:300])
                if exc.refused:
                    with self._lock:
                        self._refusals += 1
                        if self._refusals >= MAX_REFUSALS and not self._blocked:
                            self._blocked = SourceBlockedError(
                                f"BSE refused {self._refusals} attachment downloads in a row; stopping this run")
                            self.stats.stopped_reason = str(self._blocked)[:300]
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
        ocr = page_reader(self.gateway.transcribe_image if self.gateway.has_route("vision") else None)
        # Pages of figures are read by local OCR first, the text layer putting back the nils it drops
        # (extract.figure_page); never by the vision route, which costs quota and swaps digits.
        figures = recognise if local_ocr_available() else None
        cached = self._cached_text(filing.news_id)
        doc = None
        # A page whose text layer is unreadable and was never OCR'd is read again from the PDF, once, so
        # it can be: the cache would otherwise hand the same garbage to the model on every re-run. So is
        # an entry written before figure pages went to local OCR.
        current = (cached is not None and cached.get("v", 1) >= CACHE_VERSION
                   and not cache_needs_ocr(cached, local_ocr=figures is not None,
                                       max_ocr_pages=self.settings.max_ocr_pages if ocr else None)
                   and "blocks" in cached  # written before pages were also read block by block
                   # Nothing was read (too large at the cap then, or not there): there is no text to lose by
                   # asking again, and 519552's annual report, skipped at 30 MB, would stay empty for good.
                   and bool(cached.get("digital")))
        if cached is not None and (current or not filing.pdf_url):
            doc = Document.from_cache(cached, ocr=ocr, max_ocr_pages=self.settings.max_ocr_pages)
        elif cached is not None:
            # Written before the text layer was read in reading order: read the PDF again, keeping the
            # pages already OCR'd; if BSE will not serve it now, the old text is still better than none.
            try:
                pdf = self._attachment(filing.pdf_url, _attachment_cap(filing))
                self._refusals = self._network_failures = 0
                doc = Document(pdf, ocr=ocr, max_ocr_pages=self.settings.max_ocr_pages, figure_reader=figures)
                doc.keep_ocr(cached)
            except AttachmentError:
                doc = Document.from_cache(cached, ocr=ocr, max_ocr_pages=self.settings.max_ocr_pages)
        if doc is None:
            pdf = self._attachment(filing.pdf_url, _attachment_cap(filing)) if filing.pdf_url else None
            self._refusals = self._network_failures = 0
            doc = Document(pdf, ocr=ocr, max_ocr_pages=self.settings.max_ocr_pages, figure_reader=figures)
        try:
            repeat = self._duplicate_of(filing, doc)
            if repeat:
                with self._lock:
                    self.stats.duplicates += 1
                return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": filing.event_type,
                                "reason": f"duplicate of {repeat[0]} ({repeat[1]} match)", "updated_at": now_iso()})
            if filing.route == "TIMELINE":
                return self._timeline_flow(filing, company, industry, doc, bulk, memory_complete)
            return self._analyze_document(filing, company, industry, doc, bulk, memory_complete)
        finally:
            with self._lock:
                self.stats.ocr_pages += doc.ocr_pages_used + doc.figure_pages_used
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
        mine = duplicates.body(doc.select_text(duplicates.CHARS, figures=False))
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
                candidates.append((row["news_id"], duplicates.body(Document.from_cache(cached).select_text(duplicates.CHARS, figures=False))))
        for news_id, theirs in candidates:
            kind = duplicates.match(mine, theirs)
            if kind:
                log.info("%s repeats %s (%s match, same company)", filing.news_id, news_id, kind)
                return news_id, kind
        return None

    def _results_links(self, filing: Filing) -> list[XbrlLink]:
        """The company's results XBRL files as quarter links, read once a run: NSE's integrated filing (and its
        older results list) for an NSE filing, BSE's results archive otherwise. NSE's rows are the latest file per
        quarter and basis, a revision before its original (nse.parse_integrated_rows)."""
        with self._lock:
            links = self._xbrl_links.get(filing.scrip_code)
        if links is not None:
            return links
        try:
            if self.nse is not None and filing.news_id.startswith(nse_api.NEWS_ID_PREFIX) and filing.symbol:
                with self._lock:
                    if self._nse_refused:
                        return []
                links = nse_api.results_links(self.nse.financial_results(filing.symbol))
            else:
                links = self.bse.results_xbrl(filing.scrip_code)
        except nse_api.SourceBlockedError as exc:
            log.error("NSE refused the session; results are read from their PDF for the rest of this run: %s", exc)
            with self._lock:
                self._nse_refused = True
            return []
        except Exception as exc:  # XBRL is an extra: the PDF still carries the results
            log.warning("results XBRL list for %s unavailable (%s); using the PDF", filing.scrip_code, exc)
            links = []
        with self._lock:
            self._xbrl_links[filing.scrip_code] = links
        return links

    def _results_xbrl_url(self, filing: Filing, text: str) -> str | None:
        """The XBRL file for a results filing, from the company's results archive: the statement's
        quarter, consolidated when the company files it (memory keeps one basis), the latest file
        (revision) filed within 45 days of the PDF, else the earliest. Without a stated quarter, the
        file filed within three days of the PDF. Announcement rows carry no XBRL link of their own."""
        links = self._results_links(filing)
        if not links:
            return None
        quarter = statement_quarter(text, filing.filed_at)
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

    def _standalone_bank_ratios(self, filing: Filing, tagged) -> None:
        """A bank's consolidated file carries no gross NPA, net NPA or RoA (0 fillers, T2 2026-10-20): the same
        quarter's standalone file gives them. Best effort: the card goes on without them if it cannot be read."""
        links = [link for link in self._results_links(filing)
                 if link.period == tagged.period and link.basis == "STANDALONE"]
        if not links:
            return
        link = max(links, key=lambda link: link.filed_at)
        try:
            standalone = xbrl_fast_path.parse(self._attachment(link.url, 8_000_000))
        except Exception as exc:  # an extra: the consolidated card stands without the ratios
            log.warning("standalone bank file for %s unavailable (%s)", filing.news_id, exc)
            return
        xbrl_fast_path.add_bank_ratios(tagged, standalone)

    def _timeline_flow(self, filing: Filing, company: dict, industry, doc: Document, bulk: bool, memory_complete: bool) -> Outcome:
        """A routine filing (dividend recommendation, voting result, a nil pledge declaration) gets one dated line in
        the company's timeline and no card (D22). A cheap model writes the line and asks for a full card when the
        filing is consequential; the same event filed again is recorded once."""
        now = now_iso()
        first = doc.select_text(6000, [])
        _ocr_check(doc)
        system, user = self.prompts.timeline(filing, first)
        verdict: TimelineVerdict = self.gateway.complete_json("pass1_bulk" if bulk else "pass1", system, user, TimelineVerdict).value
        if verdict.needs_card or not verdict.entry.strip():
            filing = filing.model_copy(update={"route": "FAST_TRACK", "event_type": verdict.event_type if verdict.event_type != "OTHER" else filing.event_type})
            return self._analyze_document(filing, company, industry, doc, bulk, memory_complete)
        event_type = verdict.event_type if verdict.event_type != "OTHER" else (filing.event_type or "OTHER")
        dossier = self.sink.get_dossier(filing.scrip_code) or new_dossier(filing, company)
        repeat = similar_timeline_entry(dossier, filing, verdict.entry)
        if repeat:
            with self._lock:
                self.stats.duplicates += 1
            return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": event_type,
                            "reason": f"duplicate of {repeat['news_id']} (same timeline event)", "updated_at": now})
        merged = add_timeline_entry(dossier, filing, event_type, verdict.entry, now)
        self.sink.put_dossier(filing.scrip_code, merged)
        with self._lock:
            self.stats.timeline_only += 1
        return Outcome({"news_id": filing.news_id, "status": "NOT_MATERIAL", "event_type": event_type,
                        "reason": f"timeline only: {verdict.entry}"[:300], "updated_at": now},
                       company={"scrip_code": filing.scrip_code, "company_name": filing.company_name,
                                "updated_at": now, **_company_memory(merged)})

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
        done = {t["news_id"] for t in dossier.get("timeline", [])
                if t.get("event_type") == "RESULTS" and t.get("date", "") < filing.filed_at and t.get("news_id") != filing.news_id}
        owners = list(dict.fromkeys(n for m in dossier.get("financial_metrics", []) if m.get("period") == quarter
                                    for n in done if reported_by(m, n)))
        # An owner whose card is held out of the feed is not the quarter's card: another document of the quarter
        # may make the one that is published. 17 of the 43 quarters with D20 duplicates had their only card held
        # while the statement itself was marked a duplicate of it (funnel, 2026-10-18).
        owners = [n for n in owners if not self._card_held(n)]
        with self._lock:
            claimed = self._results_quarters.get(key)
            if claimed and claimed != filing.news_id:
                return claimed, quarter
            if owners:
                return owners[0], quarter
            self._results_quarters[key] = filing.news_id
        return None

    def _card_held(self, news_id: str) -> bool:
        # this run's own verdict first: its card may not be committed yet, and a re-run deleted the old one
        with self._lock:
            if news_id in self._held_this_run:
                return True
        rows = self.sink.query("card_held", [news_id]) or []
        return bool(rows and rows[0].get("held"))

    def _xbrl_comparatives(self, filing: Filing, tagged: "xbrl_fast_path.XbrlResult", history=()) -> None:
        """Year-ago and previous-quarter figures for a results file, from those quarters' files in the
        company's results archive (cached by URL). Best effort: a missing file leaves the change out. An
        earlier file tagged in the wrong unit is put right first, or every change against it is off by
        that power of ten (Jubilant's FY25 revenue "+979%")."""
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
                xbrl_fast_path.fix_scale(parsed, [*history, *tagged.metrics], filing.scrip_code)
                earlier.append(parsed)
        if earlier:
            xbrl_fast_path.add_comparatives(tagged, *earlier)

    def _xbrl_file(self, url: str, client=None, max_bytes: int = 8_000_000) -> bytes | None:
        """An XBRL file by URL, cached under the text cache's xbrl folder (as seed.py keeps NSE's)."""
        root = self.settings.text_cache_dir
        path = root / "xbrl" / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".xml.gz") if root else None
        if path and path.exists():
            try:
                return gzip.decompress(path.read_bytes())
            except OSError:
                pass
        try:
            client = client or self.bse
            # an event XBRL file comes as a zip of the XML and its PDF on some rows (event_xbrl.xml_of)
            fetch = client.fetch if url.lower().endswith(".zip") and hasattr(client, "fetch") else client.download
            data = fetch(url, max_bytes=max_bytes)
        except AttachmentError:
            return None
        if data and path:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(gzip.compress(data))
            except OSError:
                pass
        return data

    def _event_files(self, filing: Filing) -> list:
        """NSE's event XBRL files broadcast in the window around a filing, read once a run for each day (one request
        per type for the days not read yet)."""
        filed = datetime.fromisoformat(filing.filed_at)
        first = (filed - event_xbrl.BEFORE).date()
        last = min((filed + event_xbrl.AFTER).date(), today_ist())
        days = [first + timedelta(days=n) for n in range((last - first).days + 1)]
        with self._lock:
            missing = [d for d in days if d.isoformat() not in self._event_days]
        if missing:
            got: dict[str, list] = {d.isoformat(): [] for d in missing}
            for kind in event_xbrl.KINDS:
                for f in self.nse.event_xbrl(kind, missing[0], missing[-1]):
                    got.setdefault(f.broadcast_at.date().isoformat(), []).append(f)
            with self._lock:
                for day, files in got.items():
                    self._event_days.setdefault(day, files)
        with self._lock:
            return [f for d in days for f in self._event_days.get(d.isoformat(), [])]

    def _event_xbrl(self, filing: Filing, doc: Document) -> tuple[list, list[str] | None]:
        """The filing's event XBRL from NSE (event_xbrl.py): its matches, and the app ids of the company's files looked
        at (None when NSE was not asked: not an NSE filing, not an event filed with XBRL, refused or failing).

        Raises EventXbrlPending for a live filing of an event that is filed with XBRL (orders, litigation, actions,
        director changes...) when no file has come yet and the PDF is younger than event_xbrl.WAIT_MINUTES: it stays
        queued without spending an attempt, since the file follows the PDF by a median of 8 minutes."""
        if self.nse is None or not filing.news_id.startswith(nse_api.NEWS_ID_PREFIX) or not filing.symbol:
            return [], None
        mine = event_xbrl.family(filing.subject)
        if not mine and not event_xbrl.generic(filing.subject):
            return [], None
        with self._lock:
            if self._nse_refused:
                return [], None
        cache: dict[str, object] = {}

        def read(file):
            if file.app_id not in cache:
                data = self._xbrl_file(file.xbrl_url, self.nse) if file.xbrl_url else None
                cache[file.app_id] = event_xbrl.parse(data, file.app_id) if data else None
            return cache[file.app_id]

        try:
            matches, checked = event_xbrl.match(filing, self._event_files(filing), read, doc.layer_text() or "")
        except nse_api.SourceBlockedError as exc:
            log.error("NSE refused the session; events are read from their PDF for the rest of this run: %s", exc)
            with self._lock:
                self._nse_refused = True
            return [], None
        except Exception as exc:  # the XBRL is an extra: the PDF still carries the event
            log.warning("event XBRL for %s unavailable (%s: %s); using the PDF", filing.news_id, type(exc).__name__, exc)
            return [], None
        if not matches and mine:
            age = now_ist() - datetime.fromisoformat(filing.filed_at)
            if age < timedelta(minutes=event_xbrl.WAIT_MINUTES):
                raise EventXbrlPending(f"waiting for its event XBRL ({age.total_seconds() / 60:.0f} min after the PDF)")
        if matches:
            log.info("event XBRL for %s: %s", filing.news_id, ", ".join(f"{m.file.app_id} ({m.how})" for m in matches))
        return matches, checked

    def _annual_report_xbrl(self, filing: Filing, company: dict,
                            doc: Document) -> tuple[list[annual_xbrl.AnnualReport], str | None]:
        """The annual report's own XBRL from NSE (annual_xbrl), for the year the report closes: consolidated first,
        then standalone. Empty - the report read from its PDF alone, as before - when the company is not on NSE,
        has not filed the year's file yet, or the file's figures are not in the PDF at any unit.

        Also returns when NSE's list was read, if every file it lists for the year was looked at; None when NSE
        was off, refused or failing. The catch-up (annual_catchup.py) reads the report again for a file broadcast
        after that time, and for any file of the year when there is none."""
        symbol = (company.get("symbol") or filing.symbol or "").strip().upper()
        if self.nse is None or not symbol:
            return [], None
        with self._lock:
            cached, refused = self._annual_lists.get(symbol), self._nse_refused
        if refused:
            return [], None
        try:
            if cached is None:
                cached = (self.nse.annual_reports(symbol), now_iso())
                with self._lock:
                    self._annual_lists[symbol] = cached
            listing, read_at = cached
            year = annual_xbrl.report_year(filing.headline, filing.subject, filing.filed_at)
            reports = []
            for row in annual_xbrl.pick(listing, year):
                data = self._xbrl_file(row.xbrl_url, self.nse, max_bytes=nse_api.ANNUAL_REPORT_MAX_BYTES)
                parsed = annual_xbrl.parse(data) if data else None
                if parsed and parsed.period_end.year == year and parsed.period_end.isoformat() < filing.filed_at[:10]:
                    reports.append(parsed)
        except nse_api.SourceBlockedError as exc:
            log.error("NSE refused the session; annual reports are read from their PDF for the rest of this run: %s", exc)
            with self._lock:
                self._nse_refused = True
            return [], None
        except Exception as exc:  # the XBRL is an extra: the PDF still carries the report
            log.warning("annual-report XBRL for %s unavailable (%s: %s); using the PDF", filing.news_id, type(exc).__name__, exc)
            return [], None
        if reports and not annual_xbrl.confirm(reports[0], doc.layer_text()):
            log.warning("annual-report XBRL for %s (%s %s): its figures are not in the PDF at any unit; using the PDF only",
                        filing.news_id, symbol, reports[0].fy)
            return [], read_at
        return reports, read_at

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
                data = self._attachment(filing.xbrl_url, 8_000_000)   # NSE's archive for an NSE file
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
        # Before any model call: a live filing waiting for its file stays queued at no cost (EventXbrlPending)
        events, events_checked = self._event_xbrl(filing, doc)
        # Before pass 1, not after it: the gatekeeper is shown what this company has already filed, so it
        # can name an event arriving again as a different document (the document rules cannot see those).
        dossier = self.sink.get_dossier(filing.scrip_code) or new_dossier(filing, company)
        if filing.route == "PASS1" and doc.page_count >= ANNUAL_REPORT_MIN_PAGES and doc.kind() == "ANNUAL_REPORT":
            # NSE's headline can name only the meeting ("Annual General Meeting ... to be held on ..."), with the annual
            # report inside: Max Financial's 389 pages, whose auditor flagged a pending SEBI show-cause notice, were
            # turned away by pass 1 as a routine AGM notice (round 5 recall review, 2026-10-19)
            log.info("%s is an annual report by its own pages (%d); the annual-report path, not pass 1", filing.news_id,
                     doc.page_count)
            filing = filing.model_copy(update={"route": "FAST_TRACK", "event_type": "ANNUAL_REPORT"})
            event_type = "ANNUAL_REPORT"
        if filing.route == "PASS1":
            first_page = doc.first_page_text()
            _ocr_check(doc)
            recent = [t for t in dossier.get("timeline", []) if str(t.get("date", "")) < filing.filed_at][-8:]
            system, user = self.prompts.pass1(filing, first_page, recent)
            verdict: Pass1Result = self.gateway.complete_json("pass1_bulk" if bulk else "pass1", system, user, Pass1Result).value
            if not verdict.is_material:
                with self._lock:
                    self.stats.pass1_rejected += 1
                return Outcome({"news_id": filing.news_id, "status": "NOT_MATERIAL", "event_type": verdict.event_type,
                                "reason": f"pass1: {verdict.reason}"[:300], "updated_at": now})
            repeat = timeline_entry_dated(dossier, filing, verdict.duplicate_of)
            if repeat:  # confirmed in code: the entry it named is on file and near in time
                with self._lock:
                    self.stats.duplicates += 1
                log.info("pass 1 calls %s a repeat of %s (%s), so pass 2 is not spent on it",
                         filing.news_id, repeat.get("news_id"), str(repeat.get("date", ""))[:10])
                return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": verdict.event_type,
                                "reason": f"duplicate of {repeat.get('news_id')} (same event, another document; "
                                          f"pass 1 named {verdict.duplicate_of})"[:300], "updated_at": now})
            event_type = verdict.event_type
            if verdict.timeline_only:
                return self._timeline_flow(filing.model_copy(update={"event_type": event_type}), company, industry, doc, bulk,
                                           memory_complete)

        # The fast-track route skips pass 1, and with it the question of whether this event is already
        # in the feed - 134 of the 175 duplicate pairs measured on the rebuild had a fast-track later
        # card. A deterministic check on BSE's own headline cannot stand in for it: word overlap against
        # the timeline caught 4 of 128, and the best same-domain variant caught 27 while wrongly dropping
        # 13 real cards, because the headline BSE puts on a filing is boilerplate. So ask, in one small
        # call on the free routes, and confirm the answer in code before dropping anything.
        # Only the event types that were measured to arrive twice, which is the same list the
        # one-card rule uses: a monthly update or another order win recurs in nearly the same words and
        # must never be dropped, and results have their own one-card-per-quarter rule. This keeps the
        # extra call off most filings - free-tier requests were what tripped the breaker, so spending one
        # everywhere would trade a paid call for the scarcer thing.
        if filing.route != "PASS1" and event_type in ONE_EVENT_ONE_CARD and not is_transcript(filing):
            # Only entries close enough to be the same event: with nothing within the window there is
            # nothing to repeat, so the call is not made at all. Most filings never reach it.
            since = (datetime.fromisoformat(filing.filed_at) - timedelta(days=REPEAT_DAYS)).isoformat()
            recent = [t for t in dossier.get("timeline", [])
                      if since <= str(t.get("date", "")) < filing.filed_at][-8:]
            if recent:
                repeat = self._repeat_check(filing, recent, dossier, bulk, doc.first_page_text(2000))
                if repeat:
                    with self._lock:
                        self.stats.duplicates += 1
                    return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": event_type,
                                    "reason": f"duplicate of {repeat.get('news_id')} (same event, another "
                                              f"document; checked before pass 2)"[:300], "updated_at": now})
        view = view_as_of(dossier, filing.filed_at)
        # A transcript or an annual report runs to 100-400 pages: the auditor's report and the notes need room
        budget = self.settings.pass2_char_budget * (3 if event_type in ("CONCALL_PRESENTATION", "ANNUAL_REPORT") else 1)
        text = doc.select_text(budget, self.prompts.keywords(event_type))
        # The same pages read block by block, where a cell or a column stays whole: a quote of a two-column
        # page is the filing's own words if either reading has it (gate.quote_found).
        blocks = doc.block_text(doc.selected)
        _ocr_check(doc)
        if event_type == "RESULTS" and not filing.xbrl_url:
            filing = filing.model_copy(update={"xbrl_url": self._results_xbrl_url(filing, text)})
            if not filing.xbrl_url and filing.news_id.startswith(nse_api.NEWS_ID_PREFIX) and self.nse is not None \
                    and not self._nse_refused:
                age = now_ist() - datetime.fromisoformat(filing.filed_at)
                if age < timedelta(minutes=RESULTS_XBRL_WAIT_MINUTES):
                    # NSE's integrated-filing XBRL followed the outcome by 5 min to 2 h 40 min (measured 2026-10-18)
                    with self._lock:
                        self._xbrl_links.pop(filing.scrip_code, None)   # read the list afresh next time
                    raise EventXbrlPending(f"waiting for its results XBRL ({age.total_seconds() / 60:.0f} min after the PDF)")
        tagged = self._xbrl(filing) if event_type == "RESULTS" else None
        if xbrl_fast_path.needs_standalone_bank_ratios(tagged):
            self._standalone_bank_ratios(filing, tagged)
        if tagged and (tagged.kind != "RESULTS" or not xbrl_fast_path.confirm(tagged, text)):
            known = (dossier_as_of(dossier, filing.filed_at, inclusive=False) or {}).get("financial_metrics")
            if tagged.kind == "RESULTS" and results_card.agrees_with_memory(tagged, known):
                # The statement is not in the text read (Ceigall Q1FY27, round 5 arm B: its pages missing or garbled),
                # but the file's own earlier quarters are memory's: right company, scale and basis. Without it the model
                # wrote Q1FY26's profit as Q1FY27's and a fall where profit rose 24%.
                log.info("XBRL figures for %s not in the PDF text, but its earlier quarters match memory; using the file",
                         filing.news_id)
            else:
                if tagged.kind == "RESULTS":
                    log.warning("XBRL figures for %s not found in the PDF in any unit; using the PDF only", filing.news_id)
                tagged = None
        events_table = event_xbrl.table(events)
        if not text.strip() and not tagged and not events:
            if filing.pdf_url:
                # The attachment is there but nothing could be read from it (a 404, over 30 MB, corrupt or
                # password-protected): a card from the headline alone cannot be checked against anything, and
                # its checks crashed on the empty text. Failed, so a later run tries the file again.
                raise RuntimeError(f"no readable text in the attachment ({doc.error or 'empty'})")
            # No attachment by design - an exchange's clarification request is its headline and subject - so
            # those are the filing's own words, and what its quotes answer to.
            text = "\n".join(t for t in (filing.headline, filing.subject) if t)
        if event_type == "RESULTS" and self.settings.one_card_per_results_quarter:
            earlier = self._same_results_quarter(filing, dossier, results_quarter(tagged, text, filing.filed_at))
            if earlier:
                with self._lock:
                    self.stats.duplicates += 1
                return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": "RESULTS",
                                "reason": f"duplicate of {earlier[0]} (same results quarter {earlier[1]}, D20)",
                                "updated_at": now_iso()})
        filed_text = text  # the document alone, before the XBRL table goes in front of it
        if tagged:
            # A file tagged in the wrong unit, told by the company's quarters in memory (xbrl.fix_scale):
            # confirm() above accepts the figures at any unit, so it cannot.
            history = dossier.get("financial_metrics") or []
            xbrl_fast_path.fix_scale(tagged, history, filing.news_id)
            xbrl_fast_path.settle_pbt(tagged, filed_text)
            self._xbrl_comparatives(filing, tagged, history)
            text = tagged.table() + "\n\n" + text  # exact figures first; they also ground the card
        # An annual report's statements as the company tagged them, in crore and on a named basis, where the PDF
        # prints lakh or million with standalone and consolidated side by side (12 of 31 cards held, round 3d).
        # Its lines are the filing's own figures, so a card may quote them as it quotes the results table.
        annual, annual_checked = self._annual_report_xbrl(filing, company, doc) if event_type == "ANNUAL_REPORT" else ([], None)
        if annual:
            text = annual_xbrl.table(annual) + "\n\n" + text
        # The event's own structured filing: amounts, parties, dates and stage as exact fields (PLAN 18 part 3)
        if events_table:
            text = events_table + "\n\n" + text
        sector_module = self.prompts.sector_for(industry)
        sector = sector_module.name
        peers = self._peers(sector, event_type, filing)
        learned = self._learning()
        reaction = learned["queue"].get(filing.news_id)
        # The proportions the model may use, computed here from memory as it stood before this filing.
        scale = scale_block(dossier_as_of(dossier, filing.filed_at, inclusive=False), company, text, declared_unit(text))
        system, user = self.prompts.pass2(filing, event_type, industry, view, text, peers, scale=scale,
                                          examples=self._owner_examples(sector, event_type),
                                          lessons=[x["lesson"] for x in learned["lessons"].get(f"{sector}|{event_type}", [])][-3:],
                                          reaction=reaction)
        route = "pass2_bulk" if bulk else "pass2"
        if (len(system) + len(user)) / 4 > LONG_PROMPT_TOKENS and self.gateway.has_route("pass2_long"):
            route = "pass2_long"  # a transcript or presentation: long-context models only
        if self._packer is not None and route in ("pass2", "pass2_bulk"):
            result = self._packer.complete(route, system, user, Pass2Output, filing.news_id)   # several filings, one Gemini call
        else:
            result = self.gateway.complete_json(route, system, user, Pass2Output)
        out: Pass2Output = result.value
        if not out.is_material or out.card is None:
            with self._lock:
                self.stats.not_material += 1
            return Outcome({"news_id": filing.news_id, "status": "NOT_MATERIAL", "event_type": out.event_type,
                            "reason": f"pass2: not material{': ' + out.reason if out.reason else ''}"[:300],
                            "updated_at": now})
        if out.event_type in ONE_EVENT_ONE_CARD and out.timeline_entry and not is_transcript(filing):
            repeat = similar_timeline_entry(dossier, filing, out.timeline_entry)
            if repeat:  # the same event filed again in other words (BSE takes one submission per subcategory)
                with self._lock:
                    self.stats.duplicates += 1
                return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": out.event_type,
                                "reason": f"duplicate of {repeat['news_id']} (same event, in other words)", "updated_at": now})
        if "RESULTS" in (event_type, out.event_type):
            quarter = canonical_period(tagged.period) if tagged and tagged.period else statement_quarter(text, filing.filed_at)
            relabel_periods(out, quarter, statement_year(text))
        # The scale block too: the market cap, revenue, net worth and debt the prompt gave the model to measure
        # the event against. Not checked against it, a card that used them was held as stating figures the
        # filing does not print - 40 of the 77 cards held only for an unfound amount (funnel, 2026-10-18).
        sources = (text, filing.headline, filing.subject, json.dumps(view or {}, ensure_ascii=False), scale)
        history = dossier.get("financial_metrics", [])
        event_orders = event_xbrl.orders(events)
        # Code computes, the model describes (audit round 2): the changes, margins and ratios a card may state
        produced = computed.build_pool(filed_text, tagged, "\n".join(x for x in (annual_xbrl.table(annual) if annual else "",
                                                                                  events_table) if x), history, scale,
                                       (view or {}).get("ownership"))
        def ground(candidate: Pass2Output):
            """Correct a card where the filing can settle it, then check what is left.

            Every card goes through this, including one a second provider wrote. It used to run on the
            first card only, so a corrected card was published having had none of it: no exact XBRL
            values, no deal size recomputed from shares x price, no unit slips fixed - on exactly the
            cards that had already failed once. The record stored beside the card described the card
            that had been thrown away (2026-10-17: Novartis FY25 was published at the right Rs 356.27 Cr
            with a note saying it had been changed to Rs 83.88 Cr, which was the discarded card).
            """
            # a results card with its XBRL file: code writes the figures, the model's words are cut to a line or two
            built = (results_card.build(candidate, tagged, filing.company_name,
                                        results_card.history_from_view(view), filed_text)
                     if tagged and "RESULTS" in (event_type, candidate.event_type) else [])
            units = fix_unit_slips(candidate, sources)
            foreign_fixes = fix_foreign_crore(candidate, filed_text)
            counts = fix_count_millions(candidate, sources)
            changes = built + fix_change_percentages(candidate, sources) + counts + foreign_fixes
            changes += apply_deal_guards(candidate, filing, history, dossier.get("balance_sheet", []), text)
            changes += deal_echo_slips(candidate, filed_text)
            changes += continued_deal(candidate, view, filed_text)
            changes += event_xbrl.apply_orders(candidate.card, event_orders)   # the file's figures have the last word
            changes += misdated_memory_insights(candidate, view, filed_text)
            changes += stale_approvals(candidate, view, filed_text)
            changes += call_changes(candidate, event_type, filed_text)
            if tagged:
                # against the document alone: `sources` starts with the XBRL table, so checking the
                # table's own comparative against it would always succeed and the guard would do nothing
                changes += xbrl_key_numbers(candidate, tagged, (filed_text,))
            changes += computed.enforce(candidate, produced)
            changes += directions.guard(candidate, tagged)   # tax, inventory, EPS, credit cost: the file decides
            found = check_card_all(candidate, view, sources, history)
            found.scale += period_mixups(candidate, tagged)
            found.scale += gate.stale_columns(_card_texts(candidate), filed_text)
            found.scale += foreign_as_rupees(_card_texts(candidate), filed_text)
            found.form += headline_form(candidate)
            if candidate.card is not None and "DEBT_RATINGS" in (event_type, candidate.event_type):
                sheet = candidate.dossier_delta.balance_sheet
                words = " ".join([candidate.card.headline or "", *(f.text for f in candidate.card.what_happened[:2])])
                found.claims += rating_word_mismatch(words, getattr(sheet, "credit_rating", None),
                                                     getattr(sheet, "rating_agency", None), dossier, filed_text)
            if not tagged and "RESULTS" in (event_type, candidate.event_type):
                # With no XBRL the reading of the statement is all there is, so it has to add up: 27 of
                # 68 results cards had no XBRL behind them. Reported for the second provider to fix, with
                # the exact gap; never corrected here, since a sum cannot say which line is wrong.
                found.scale += gate.statement_footing(candidate.dossier_delta.financial_metrics)
            known = f"{sources[3]}\n{scale}"   # memory and the scale block: the figures a fact may compare with
            quote_problems, missing, dropped, paraphrased = check_quotes(
                candidate, text, filing.news_id, declared_unit(filed_text), blocks, known)
            found.quotes += quote_problems
            found.quote_style += paraphrased
            # The headline numbers answer to their own sentence too, not to the whole filing.
            number_problems, unquoted, elsewhere = check_quoted_numbers(
                candidate, text, declared_unit(filed_text), blocks, known)
            found.quotes += number_problems
            found.quote_style += elsewhere
            return found, units, changes, missing + unquoted, dropped

        checks, unit_fixes, change_fixes, quotes_missing, quotes_dropped = ground(out)
        review = None
        if checks.wants_second_opinion and self.settings.second_opinion:
            out, result, checks, review, fixes = self._second_opinion(
                route, system, user, out, result, checks, ground)
            if fixes is not None:
                unit_fixes, change_fixes, quotes_missing, quotes_dropped = fixes
        checks.held += self._held_reasons(filing, text)
        if checks.held and review is None:
            review = {"status": "HELD", "issues": checks.held}
        elif checks.held:
            # A second opinion's block replaced these, so a garbled scan or an owner's hold left no trace on the
            # card (CSB 3649405a; audit of discard paths, 2026-10-18). Kept beside its verdict.
            review = {**review, "held": list(checks.held)}
        if filing.route == "FAST_TRACK" and filing.event_type:
            out.event_type = filing.event_type  # rules know the event type better than the model
        elif out.event_type == "OTHER" and event_type != "OTHER":
            out.event_type = event_type  # Pass 2 left it open; Pass 1 had decided
        corrected = event_type_rules(out.event_type, filing, text, tagged)
        if corrected == "OTHER" and out.card is not None and APPOINTMENT.search(out.card.headline or ""):
            corrected = "MANAGEMENT_CHANGE"   # a board outcome that only (re)appoints a director or KMP (D30)
        if corrected != out.event_type:
            log.info("event type for %s: %s -> %s (rules)", filing.news_id, out.event_type, corrected)
            out.event_type = corrected
        deal = out.card.deal_value if out.card is not None else None
        if deal is not None and deal.kind == "ACQUISITION" and _DEMERGER.search(f"{filing.headline} {filing.subject} {out.card.headline}"):
            deal.kind = "OTHER"   # a demerger moves a business out; it is not an acquisition (live review 3)
        if out.card is not None and out.event_type != "CONCALL_PRESENTATION":
            out.card.call_read = None  # guidance, tone and transparency describe a call, not other filings
        event_type = out.event_type
        if event_type in NO_CARD_EVENTS and not top_exit(f"{filing.headline} {filing.subject} {doc.first_page_text(3000)}"):
            # director and KMP changes get no card (owner, 2026-10-18), except the MD, CEO or CFO leaving (2026-10-19);
            # the rule book drops most before any model call
            with self._lock:
                self.stats.not_material += 1
            return Outcome({"news_id": filing.news_id, "status": "NOT_MATERIAL", "event_type": event_type,
                            "reason": "pass2: director / KMP change (no card)", "updated_at": now})
        card = out.card
        # Memory takes only figures confirmed at the filing's unit and the company's scale (audit round 2); the
        # card keeps what it read. XBRL figures go into both, unfiltered.
        remembered, _ = trust.for_memory(out, filed_text, company, dossier)
        if tagged:
            _apply_xbrl(out, tagged, filing.news_id)
            _apply_xbrl(remembered, tagged, filing.news_id)
        score, checked, ungrounded, quant, claims = checks.score, checks.checked, checks.ungrounded, checks.quant, checks.claims

        merged = merge(dossier, remembered, filing, card.impact_level, now)
        merged.update({k: v for k, v in (("industry", industry), ("sector", sector), ("symbol", company.get("symbol") or filing.symbol)) if v})
        # Signals, footer and results table see memory as it stood at this filing, not later facts
        # that a backfill may already have stored.
        before = dossier_as_of(dossier, filing.filed_at, inclusive=False)
        current = dossier_as_of(merged, filing.filed_at)
        # Market data as it stood when the filing came out: the stored daily series (history fill on
        # the laptop), else today's figures, dropped when they are too new for this filing.
        priced = point_in_time(company, filing.filed_at, self._prices, self._buckets) or priced_for(company, filing)
        signals = compute_signals(before, current, out, filing, priced) + text_signals(text, event_type)
        if (review or {}).get("status") == "UNRESOLVED" and not checks.only_style:
            # a held card's line stays out of the company's story: Heritage's held Q2FY27 board outcome and its
            # published press release made two Q2FY27 results lines with different figures (T5, 2026-10-20).
            # Its figures stay: they are the statement's own and passed memory's checks.
            merged["timeline"] = [e for e in merged.get("timeline", []) if e.get("news_id") != filing.news_id]
        self.sink.put_dossier(filing.scrip_code, merged)

        card_json = {
            "category_tag": EVENT_TAGS.get(event_type, "UPDATE"),
            "event_type": event_type,
            **card.model_dump(),
            "quantified_impact": quant.items,
            "signals": signals,
            "timeline_entry": out.timeline_entry,
            "fundamentals": latest_fundamentals(current, sector_module.footer),
            "results": results_snapshot(current, filing.news_id, sector_module.footer) if event_type == "RESULTS" else None,
            "volume_strip": volume_strip(current, filing.news_id) if event_type == "MONTHLY_BUSINESS_UPDATE" else None,
            # the event's own block on the card's face, made by code (card_context.py, signals.scale_parts)
            "scale": scale_parts(before, out, priced, filing.filed_at),
            "rating_change": rating_change(before, current, filing.news_id, text) if event_type == "DEBT_RATINGS" else None,
            "case_stage": case_stage(event_type, card.headline, [f.text for f in card.what_happened],
                                     [w.text for w in card.why_it_matters]),
            "guidance_recall": guidance_recall(before, event_type, filing.filed_at),
            # what pass 2 said about earlier promises, kept so a status in memory can be traced to its reply (T5)
            "promise_updates": [u.model_dump() for u in out.dossier_delta.promise_updates] or None,
            "pdf_pages": doc.page_count or None,
            "grounding": {"score": score, "checked": checked, "ungrounded": ungrounded[:10],
                          "math_mismatches": quant.mismatches, "unsupported_claims": claims,
                          "unit_fixes": unit_fixes or None, "change_fixes": change_fixes or None,
                          "quotes_missing": quotes_missing or None, "quotes_dropped": quotes_dropped or None,
                          "quotes_paraphrased": checks.quote_style or None, "out_of_fit": checks.scale or None},
            "review": review,
            "model": result.model_label,
            "pack": result.pack,
        }
        needs_review = checks.needs_review
        # A card the checks faulted, that a second provider was asked to correct and that still
        # fails, is kept out of the feed rather than published with an "Unverified" mark. On the
        # rebuild that was 117 of 456 cards, and a flagged card was judged WRONG 52% of the time
        # against 21% for a clean one (audit round 1), so for a feed meant to run unattended the
        # old trade was the wrong way round. The row is still written in full for the digest, the
        # audit export and the review queue.
        # ...unless all that is left is how the card quoted the filing. Its figures were each found in
        # the document; only the sentence around them is the model's wording. Prism Johnson's three
        # segment facts were held that way on 2026-10-17 with every figure verified.
        held = (review or {}).get("status") == "UNRESOLVED" and not checks.only_style
        # A held card is one for review whatever made it so: a card held only for an unfound amount had
        # needs_review = 0, so it escaped the review count and the scoring veto (76 of 118 held cards in the
        # smoke-test funnel, 2026-10-18).
        needs_review = needs_review or held
        signals += asset_turn_signals(card_json, sector, sector_module.asset_turn)  # extends card_json["signals"]
        rated = score_card(card_json, event_type, signals, current, priced, needs_review, card.impact_level,
                           dampened=(sector, event_type) in learned["dampen"])
        if reaction:
            self._record_lesson(filing.news_id, sector, event_type, out.lesson, now)
        card_json["score"] = rated.as_dict()
        card_json["model_impact"] = card.impact_level
        if tagged:
            card_json["xbrl"] = {"basis": tagged.basis, "period": tagged.period, "figures": len(tagged.metrics),
                                 "url": filing.xbrl_url}
        elif event_type == "RESULTS" and filing.news_id.startswith(nse_api.NEWS_ID_PREFIX):
            # made from the PDF alone: the files listed then, so the catch-up re-reads it only for a new one
            card_json["xbrl_seen"] = [link.url for link in self._results_links(filing)]
        if annual:
            card_json["annual_xbrl"] = {"bases": [r.basis for r in annual], "period": annual[0].fy,
                                        "figures": sum(r.figures() for r in annual)}
        if annual_checked:
            card_json["annual_xbrl_checked"] = annual_checked  # NSE's list as of then: annual_catchup.py
        if events_checked is not None:
            # the files read with the card, and every file of the company's looked at then: event_catchup.py
            card_json["event_xbrl"] = event_xbrl.summary(events, events_checked)
        card_json["priced_at_filing"] = {k: priced[k] for k in PRICED_FIELDS if priced.get(k) is not None} or None
        row = {
            "news_id": filing.news_id, "scrip_code": filing.scrip_code,
            "symbol": company.get("symbol") or filing.symbol, "company_name": filing.company_name,
            "filing_date": filing.filing_date, "filed_at": filing.filed_at, "sector": sector,
            "event_category": event_type, "impact_level": rated.impact, "headline": card.headline,
            "grounding_score": score, "needs_review": int(needs_review), "held": int(held),
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

    def _repeat_check(self, filing, recent: list[dict], dossier: dict, bulk: bool, opening: str = "") -> dict | None:
        """One cheap call: is this filing an event the feed already has? The model only points at an
        entry; `timeline_entry_dated` then checks the entry is really on file and near in time, so a
        date it invents drops nothing. A failure here is never fatal - the filing goes on to pass 2.
        It is shown the opening of the document: from BSE's boilerplate headline alone it took a ₹1.73 Cr GST
        notice for FY22 to repeat a ₹2.64 Cr one for FY20, and a completed acquisition to repeat its signing."""
        system, user = self.prompts.repeat(filing, recent, opening)
        try:
            said = self.gateway.complete_json("pass1_bulk" if bulk else "pass1", system, user, RepeatVerdict).value
        except Exception as exc:
            log.info("repeat check skipped for %s: %s", filing.news_id, type(exc).__name__)
            return None
        entry = timeline_entry_dated(dossier, filing, said.duplicate_of)
        if entry:
            log.info("repeat check: %s repeats %s (%s) - %s; pass 2 not spent on it", filing.news_id,
                     entry.get("news_id"), str(entry.get("date", ""))[:10], said.why[:60])
        return entry

    def _second_opinion(self, route, system, user, out: Pass2Output, result, checks: CardChecks, ground):
        """Ask a different provider to correct a card that failed the checks, then check again.

        The better of the two cards is kept. Either way the card is published: a corrected one
        normally, one that still fails with an "Unverified" mark and the problems listed, so a
        material filing is never hidden. `ground` corrects and checks a candidate card; the adopted
        one goes through it too, and the fixes it reports are the ones recorded beside the card.
        Returns the fixes, or None when the first card is kept and its own still stand.
        """
        problems = checks.problems()
        base = {"first_model": result.model_label, "issues": problems}
        left = self.gateway.deadline - time.monotonic() if self.gateway.deadline else None
        if left is not None and left < SECOND_OPINION_MIN_S:
            return out, result, checks, {**base, "status": "UNCHECKED", "note": "skipped: the run was ending"}, None
        with self._lock:
            self.stats.second_opinions += 1
        hints = [UNIT_HINT] if checks.amounts_ungrounded else []
        system2, user2 = self.prompts.verify(system, user, out.model_dump(mode="json"), problems + hints)
        try:
            second = self.gateway.complete_json(route, system2, user2, Pass2Output, avoid_providers=(result.provider,))
        except Exception as exc:  # the first card is still published, marked unverified
            return out, result, checks, {**base, "status": "UNCHECKED", "note": f"{type(exc).__name__}: {exc}"[:200]}, None
        if not second.value.is_material or second.value.card is None:
            return out, result, checks, {**base, "status": "UNRESOLVED", "checked_by": second.model_label}, None
        # Adopt the corrected card only. Memory (dossier delta, timeline, event type) stays from the
        # first reply unless the verifier sent a fuller one: it was asked to fix the card, and a
        # reply with just {"card": ...} must not wipe the quarter's figures from memory.
        fixed = _adopt_card(out, second.value)
        checks2, *fixes2 = ground(fixed)
        if not checks2.wants_second_opinion:
            with self._lock:
                self.stats.corrected += 1
            return fixed, second, checks2, {**base, "status": "CORRECTED", "checked_by": second.model_label, "issues": [],
                                            "fixed": problems}, fixes2
        if checks2.issue_count < checks.issue_count:
            return fixed, second, checks2, {**base, "status": "UNRESOLVED", "checked_by": second.model_label,
                                            "issues": checks2.problems()}, fixes2
        return out, result, checks, {**base, "status": "UNRESOLVED", "checked_by": second.model_label}, None

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
        # A filing read again that now ends without a card leaves none behind: cards_upsert replaces a card but never
        # removes one, so NHPC's restored unit (now not material) and LTM's partnership kept their old cards on the
        # site after a re-run (live review, 2026-10-20). On a first reading there is no card and nothing is written.
        self._exec("cards_delete", [{"news_id": o.update["news_id"]} for o in outcomes if not o.card
                                    and o.update.get("status") in ("NOT_MATERIAL", "DUPLICATE")])
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
        """Start of the live window: always the last LIVE_DAYS days. It used to start no earlier than the day the
        pipeline went live, so on 20 Oct 2026 the results filed 15-19 Oct were left to the backfill, which walks
        each company from April (owner, 2026-10-20). ``live:since`` is still recorded, for the record only."""
        if not self.sink.kv_get("live:since"):
            self._kv_set("live:since", today.isoformat())
        return today - timedelta(days=LIVE_DAYS)

    def _discover_window(self, live_from: date, today: date, days: int = 2) -> None:
        """Discover the live window's earlier days that no run has read in full, newest first, ``days`` a run.
        The live runs read only today (and yesterday before 09:00); a day before go-live, or one the runs
        missed, would otherwise wait for the backfill's discovery, which walks forward from April."""
        raw = self.sink.kv_get("live:window_from")
        done = date.fromisoformat(raw) if raw else today
        day = min(done, today) - timedelta(days=1)
        while days > 0 and day >= live_from:
            if self._discover_safely(day, full=True) is None:
                return
            self._kv_set("live:window_from", day.isoformat())
            day -= timedelta(days=1)
            days -= 1

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
                self._discover_window(live_from, today)
                self._requeue_failed_nightly(live_from)
                live_deadline = deadline if mode == "live" else started + time_budget_s * 0.6
                backfill_done = self.sink.kv_get("backfill:complete") == "1"
                # today's filings first, then the rest of the window, so a catch-up never holds today's news
                for day_from, day_to in ((today, today), (live_from, today - timedelta(days=1))):
                    self.process(day_from.isoformat(), day_to.isoformat(), live_deadline, bulk=False,
                                 memory_complete=backfill_done, history_first=True)
                if self._on_nse() and time.monotonic() < live_deadline:
                    from . import event_catchup   # cards made before their event XBRL landed

                    caught = event_catchup.catch_up(self, live_deadline)
                    if caught["rerun"] or caught["stopped"]:
                        log.info("event XBRL catch-up: %s", json.dumps(caught))
                    caught = event_catchup.results_catch_up(self, live_deadline)
                    if caught["rerun"] or caught["stopped"]:
                        log.info("results XBRL catch-up: %s", json.dumps(caught))
                    if time.monotonic() < live_deadline:
                        from . import governance_memory   # quarterly governance reports into memory, no card

                        synced = governance_memory.sync(self, live_deadline)
                        if synced["filed"] or synced["stopped"] or synced["errors"]:
                            log.info("governance memory: %s", json.dumps(synced))
                        synced = governance_memory.shareholding_sync(self, live_deadline)
                        if synced["filed"] or synced["stopped"] or synced["errors"] or synced["refused"]:
                            log.info("shareholding memory: %s", json.dumps(synced))
                        from . import pledges   # promoter encumbrance events into memory (module 42), no card

                        synced = pledges.sync(self, live_deadline)
                        if synced["filed"] or synced["stopped"] or synced["errors"]:
                            log.info("pledge memory: %s", json.dumps(synced))
                    if time.monotonic() < live_deadline and self._dgtr_due():
                        self._dgtr_sync(live_deadline)
                    if time.monotonic() < live_deadline and self._annual_catchup_due():
                        self._annual_catchup(live_deadline)
            if mode in ("backfill", "all") and not self._halted(bulk=True):
                self._backfill(today, deadline, writes_at_start, max_backfill_days, live_from - timedelta(days=1))
        except SourceBlockedError as exc:
            status, error = "ERROR", str(exc)
            self.stats.stopped_reason = self.stats.stopped_reason or "the source refused the session; work stays queued"
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

    def _annual_catchup_due(self) -> bool:
        """The daily annual-report catch-up's slot: after 18:30 IST, once a day, with NSE's annual-report XBRL on."""
        now = now_ist()
        return (self.nse is not None and self.settings.nse_annual_xbrl
                and (now.hour, now.minute) >= ANNUAL_CATCHUP_AFTER
                and self.sink.kv_get(ANNUAL_CATCHUP_KEY) != now.date().isoformat())

    def _requeue_failed_nightly(self, live_from: date) -> None:
        """Once a night (after 22:00 IST): the live window's filings that used every attempt get one more try, so a
        filing that failed on a bug fixed that day still gets its card (requeue.py)."""
        now = now_ist()
        if now.hour < REQUEUE_AFTER_HOUR or self.sink.kv_get(REQUEUE_KEY) == now.date().isoformat():
            return
        from . import requeue

        try:
            report = requeue.requeue(self.sink, live_from.isoformat(), self.settings.max_attempts, attempts_left=1)
        except Exception:   # a Worker without the query yet: try again next run
            log.exception("nightly requeue of failed filings failed")
            return
        self._kv_set(REQUEUE_KEY, now.date().isoformat())
        if report["requeued"]:
            log.info("nightly requeue: %d failed filings get one more try", report["requeued"])

    def _dgtr_due(self) -> bool:
        """DGTR's case lists once a day (module 8): its cases move in weeks, and its server is slow (NSE_DGTR=0 off)."""
        import os

        return (self.nse is not None and os.environ.get("NSE_DGTR", "1") != "0"
                and self.sink.kv_get(DGTR_SYNC_KEY) != today_ist().isoformat())

    def _dgtr_sync(self, deadline: float) -> None:
        from . import dgtr

        report = dgtr.sync(self, deadline)
        if report["linked"] or report["stopped"] or report["errors"]:
            log.info("trade remedies: %s", json.dumps(report, ensure_ascii=False))
        if not report["stopped"] and report["cases"]:
            self._kv_set(DGTR_SYNC_KEY, today_ist().isoformat())

    def _annual_catchup(self, deadline: float) -> None:
        """Annual reports read again once NSE lists their XBRL (annual_catchup.py), as part of an evening run. The
        day is marked done once every company due has had its list read, so a run cut short leaves the rest to the
        next run that evening."""
        from . import annual_catchup

        report = annual_catchup.catch_up(self, deadline, record_writes=False)
        if report["rerun"] or report["stopped"] or report["errors"]:
            log.info("annual-report XBRL catch-up: %s", json.dumps(report, ensure_ascii=False))
        if not report["stopped"] and report["lists_read"] >= min(report["companies_due"], annual_catchup.MAX_COMPANIES):
            self._kv_set(ANNUAL_CATCHUP_KEY, today_ist().isoformat())

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


def _still_noise(decision, filing: Filing, row: list) -> bool:
    """Whether a filing in the noise file stays there under today's rules: dropped or a date, a shareholding
    pattern with no XBRL file, or outside the investable universe (a market-cap test, not a rule)."""
    return (decision.action in ("DROP", "CALENDAR") or (decision.action == "XBRL" and not filing.xbrl_url)
            or str(row[7] or "").startswith("outside universe"))


# An annual report runs to 300 pages and often past 30 MB: 519552's FY26 report was skipped at that cap and,
# with no text, called not material (F57). Every other kind of filing stays under it.
ATTACHMENT_MAX_BYTES = 30_000_000
ANNUAL_REPORT_MAX_BYTES = 120_000_000
ANNUAL_REPORT_MIN_PAGES = 60   # as Document.kind() reads a directors' report: an AGM notice alone runs to 10-30 pages


def _attachment_cap(filing: Filing) -> int:
    return ANNUAL_REPORT_MAX_BYTES if filing.event_type == "ANNUAL_REPORT" else ATTACHMENT_MAX_BYTES


SECOND_OPINION_MIN_S = 300
# The same event filed in other words is one card (D22). BSE asks for one submission per applicable
# subcategory, so one event arrives as several different documents - a results PDF and its concall deck,
# a rights-issue letter of offer and its covering intimation, an NCD approval under two subcategories, a
# SAST disclosure and the company's own. duplicates.py cannot see these: it compares documents, and these
# documents differ. Measured on the rebuild, 123 of 456 cards repeated an event already in the feed, so
# every type that showed duplicates is listed here. Left out on purpose: ORDER_WIN,
# MONTHLY_BUSINESS_UPDATE, CAPEX, PRODUCT_LAUNCH and CORPORATE_ACTION recur with new numbers in nearly
# the same words, and RESULTS has its own one-card-per-quarter rule (D20).
REPEAT_DAYS = 10  # the window the fast-track repeat check looks back over, as similar_timeline_entry
ANNUAL_CATCHUP_AFTER = (18, 30)   # IST: the annual-report catch-up runs inside the first run after the close
ANNUAL_CATCHUP_KEY = "annual_catchup:last_day"
DGTR_SYNC_KEY = "dgtr_sync:last_day"
NO_CARD_EVENTS = ("MANAGEMENT_CHANGE",)
# The MD, CEO or CFO leaving keeps a card (owner, 2026-10-19, D30 amended); the same words as the rule book's D30 rule.
# "Not liable to retire by rotation" in an appointment letter is not an exit.
_EXIT = r"(resign\w*|cessation|ceas(e|es|ed|ing)\b|step(s|ped|ping)?\s+down|removal|removed|retire(s|d|ment)?\b(?!\s+by\s+rotation)|superannuat\w*|demise|passed away)"
_ROLE = r"(managing director|\bmd\b|chief executive|\bceo\b|chief financial|\bcfo\b)"
TOP_EXIT = re.compile(rf"{_EXIT}.{{0,120}}{_ROLE}|{_ROLE}.{{0,120}}{_EXIT}", re.I | re.S)


_TRANSCRIPT = re.compile(r"\btranscripts?\b", re.I)


def is_transcript(filing) -> bool:
    """A call transcript always gets its own card (owner, 2026-10-19: "big yes", for its forward-looking statements):
    never a repeat of its results card or of the deck. Round 5: Texmaco's Q1 transcript (an order book of ₹9,923 Cr, a
    South Africa order, a plan to double revenue by 2030) was set aside as the results card "in other words". An exact
    refiling of the same transcript is still one document to duplicates.py."""
    return bool(_TRANSCRIPT.search(f"{filing.headline or ''} {filing.subject or ''}"))


def top_exit(text: str | None) -> bool:
    """Whether the text says the MD, CEO or CFO is leaving (resigning, ceasing, stepping down, removed, retiring)."""
    return bool(TOP_EXIT.search(text or ""))
RESULTS_XBRL_WAIT_MINUTES = 180   # a live NSE results filing waits this long for its XBRL (measured: 5 min - 2 h 40 min)   # owner, 2026-10-18: no cards for director / KMP changes
ONE_EVENT_ONE_CARD = ("MANAGEMENT_CHANGE", "GOVERNANCE", "LITIGATION_REGULATORY", "FUNDRAISE",
                      "RIGHTS_ISSUE", "M_AND_A", "DEBT_RATINGS", "CONCALL_PRESENTATION", "ANNUAL_REPORT")
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
        # the day before too: a provider whose quota day is Pacific (Gemini) is still on it until 07:00-08:00 UTC
        before = (date.fromisoformat(utc_day()) - timedelta(days=1)).isoformat()
        usage_today, usage_month = sink.usage(utc_day()) + sink.usage(before), sink.usage_month(month)
    except Exception as exc:
        log.warning("could not load AI usage; starting counters at zero: %s", exc)
        usage_today, usage_month = [], []
    gateway = AIGateway(settings.load_toml("providers.toml"), usage_today=usage_today, usage_month=usage_month)
    on_nse = settings.discovery_source == "nse"
    return Pipeline(settings, sink, gateway, nse=nse_api.NseClient() if (on_nse or settings.nse_annual_xbrl) else None)


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
    names = [n for n in (dossier.get("identity") or {}).get("former_names") or [] if own_former_name(n, dossier)]
    return {**memory_summary(dossier), **({"former_names_json": json.dumps(names, ensure_ascii=False)} if names else {})}
