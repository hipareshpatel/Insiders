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
import os
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

from .ai.gateway import CEILING, TRANSIENT, AIGateway, AllProvidersFailed
from .bse import AttachmentError, AttachmentTooLarge, BseClient, SourceBlockedError, XbrlLink
from . import business_line
from . import duplicates
from . import requeue
from .dossier import (add_timeline_entry, dossier_as_of, forget_filing, keep_concurrent_writes, latest_fundamentals, memory_ids, merge,
                      own_former_name,
                      new_dossier, put_standalone, with_year_hold, repeated_order, reported_by, results_snapshot, call_results_snapshot, similar_timeline_entry, timeline_entry_dated, view_as_of)
from .extract import CACHE_VERSION, FIGURE_PAGE_AMOUNTS, Document, amounts, cache_needs_ocr
from .ocr import available as local_ocr_available
from .ocr import page_reader, recognise
from . import raw
from . import stages
from . import order_band
from . import call_memory, call_queue, release_fold, card_support, gate, two_parts
from .currency import CODES as CURRENCY_CODES
from .grounding import (DEFAULT_THRESHOLD, ground_all_fields, SourceIndex, _tokens, change_derived, check_card, check_claims,
                        declared_unit, foreign_as_rupees, margin_issues, scale_issues, unit_slips)
from .models import EVENT_TAGS, DossierDelta, Filing, MemoryOutput, Pass1Result, Pass2Output, RepeatVerdict, TimelineVerdict
from .periods import (canonical_period, due_date, prior_quarter_period, prior_year_period, quarter_from_index,
                      printed_periods, quarter_index, statement_quarter, statement_year)
from .prompts.engine import PromptEngine
from .quant import QuantCheck
from .quant import check as check_quant
from .rules import RuleBook
from .settings import Settings, card_consolidated_only, card_ebitda_profit_v2, card_fact_sheet, card_footer_plausible, card_ground_all_fields, card_text_support, card_two_parts, card_watch_verdict, card_yoy_restated, card_other_issuer, d1_plan, memory_call_v2, results_needs_statement, results_press_release, unit_fix_scale_guard, unit_slip_xbrl_guard, d20_dropped_file_period
from .forensics import text_signals
from .scoring import score as score_card
from .signals import compute as compute_signals, scale_block, scale_parts
from .card_context import case_stage, guidance_recall, memory_context, rating_change, rating_word_mismatch
from .call_summary import remember_call_points, card_takeaways, check_ai_takeaways
from .prices import PriceStore, point_in_time
from .signals import priced_for
from .sinks.platform import PlatformSink
from .sinks.base import Sink, SinkRejected, SinkUnavailable
from . import universe
from . import eps_adjust, no_eps, restated_pdf
from . import annual_xbrl, fact_sheet
from . import xbrl_facts, xbrl_store
from . import statements
from . import directions
from . import results_card
from . import comparative_memory, event_repeats, footer_plausible, guided_actual, one_basis, ratio_columns, results_one_line, words_figures, year_ago_label
from . import event_xbrl
from . import computed
from . import facts as code_facts
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
HISTORY_INLINE = 5       # history analysed ahead of a live filing; a longer backlog goes to the backfill (30 until
                         # 21 Oct 2026: with the backfill weeks behind, 23 filings a run went to history and 1 to today's
                         # 27 waiting filings; deep audit E11)
MAX_ORDER = 20_000       # companies in the cached backfill order
BACKLOG_MAX = 1_500      # history filings waiting to be read before backfill discovers another day
PRICED_FIELDS = ("last_price", "price_date", "market_cap_cr", "size_category", "ret_1w", "ret_1m", "ret_3m", "ret_1y",
                 "median_turnover_cr", "point_in_time")
# Cloudflare Workers Paid (owner, 22 Oct 2026): 50M rows written a month included, no daily cap; the day's share of
# the month (D1_DAILY_WRITE_CAP, else by D1_PLAN: settings.d1_plan) is where the window's earlier days and the
# catch-ups wait; the free tier's 100,000 with D1_PLAN=free. An empty value takes the plan's.
D1_FREE_DAILY_WRITES, D1_NEAR_CAP = int(os.environ.get("D1_DAILY_WRITE_CAP") or d1_plan()[1]), 0.95
REQUEUE_AFTER_HOUR, REQUEUE_KEY = 22, "failed:requeued_on"   # the nightly extra try for failed filings
LIVE_DAYS = 7            # an unfinished filing stays in the live window this long
SLICE_S = 180            # older work between two looks for today's new filings (one run, owner 27 Oct 2026)
BACKFILL_SLICE_S = 600   # the backfill's slices: its filings share Gemini requests (packs wait up to 180 s), and a
                         # slice end sends the open packs part-full; shorter slices would spend more free requests
DEADLINE_GRACE_S = 240   # a filing started before the deadline may finish within this
RESULTS_QUARTER_DAYS = 100   # a results PDF comes at most this long after its quarter ends (SEBI: 45 days, 60 for Q4; slack for revisions)
REQUEUED_FIRST_S = 180    # the slot after today's filings for filings requeued by id (requeue.mark_by_id, 31 Oct 2026)
REQUEUED_FIRST_MAX = 6    # filings a run gives that slot
RESULTS_CATCH_UP_S = 600  # the results XBRL catch-up's own window when the live share is used up (30 Oct 2026)
PAUSE_CHECK_S = 60       # how often a running pipeline looks for the nightly pause (pause.py)
RETURNING_PER_RUN = 5   # companies back in the universe whose set-aside filings one run looks up again
MAX_REFUSALS = 3         # attachment 403s in a row that mean BSE is refusing this network
MAX_NETWORK_FAILURES = 5  # attachment downloads failing on the network in a row that mean the source is down
MAX_DEFERRALS = 3        # runs one attachment may fail on the network, alone, before it spends an attempt
# runs a filing waits for the better writers' daily quota, or for busy ones, before it spends an attempt: about a day at a
# run every 30-40 minutes, so it outlasts Gemini's daily reset (owner, 25 Oct 2026: 28 filings failed on AI capacity,
# most after three 15-minute waits against a once-a-day reset)
MAX_QUOTA_DEFERRALS = 40
# runs a filing may stop at its card-writing cap (PASS2_CAP_S, TODO 35) before the cap is lifted for it: the next run
# writes it with no cap, as before F149. The cap only delays a card, it never loses one or spends an attempt.
MAX_CAP_DEFERRALS = 3
MAX_UNREACHABLE = 3      # filings in a row the platform did not answer for: the site is down, stop
SAME_FILE_MIN_BYTES = 1_000   # a file smaller than this (a stub, an error page) is never matched as the same file
NOISE_CHUNK = 500        # rows per noise-audit file in R2
NOISE_FIELDS = ("news_id", "scrip_code", "company_name", "headline", "category", "subcategory",
                "filed_at", "reason", "pdf_url")
DONE = ("ANALYZED", "NOT_MATERIAL", "DUPLICATE")  # DUPLICATE: a repeat submission (duplicates.py)
LONG_PROMPT_TOKENS = 12_000
# Long filings are packed with other long filings only (ai-quality plan item 1): at most this many characters a pack,
# so the pack plus its 60 K reply stays inside Gemini's 250 K tokens a minute (~3 characters a token). A filing larger
# than this goes to `pass2_long` on its own, as before.
LONG_PACK_MAX_CHARS = 450_000
# The model's own reply, kept beside the card for audits (ai-quality plan item 8): R2, not D1, one object a filing.
EVIDENCE_PREFIX = "evidence/"
EVIDENCE_MAX_CHARS = 60_000   # per reply; a packed answer is already cut to 20 K


def evidence_key(news_id: str) -> str | None:
    """Where a card's evidence is kept: evidence/{news_id}.json.gz (the id cut to safe characters)."""
    safe = "".join(ch for ch in news_id if ch.isalnum() or ch in "-_")[:120]
    return f"{EVIDENCE_PREFIX}{safe}.json.gz" if safe else None
TEXT_PREFIX = "text/"   # F147: each filing's extracted text, kept 6 months (R2 lifecycle rule, deploy-web.yml)


def text_key(news_id: str) -> str:
    """Where a filing's text is kept in R2: text/{news_id}.json.gz (the id cut to the same safe characters as the local file)."""
    safe = "".join(ch for ch in news_id if ch.isalnum() or ch in "-_")[:80]
    return f"{TEXT_PREFIX}{safe}.json.gz"


def text_cache_body(doc: Document) -> bytes:
    """The bytes of a filing's text-cache entry (local file and R2 object alike). mtime 0: the same text always compresses
    to the same bytes, so an unchanged entry is not sent again. Shared with text_backfill.py (F165), so a backfilled
    object has exactly the pipeline's shape."""
    return gzip.compress(json.dumps(doc.to_cache(), ensure_ascii=False).encode(), mtime=0)


SNAPSHOT_KEY = "daily_feed/latest_snapshot.json"
SNAPSHOT_DAYS = 7         # the feed's default range ("Last 7 days")
SNAPSHOT_PAGE = 50        # the feed's page size


_DEFERRED = re.compile(r"^deferred (\d+)x: (?:attachment download failed|the better writers are at their day|"
                       r"the platform did not answer|AI busy|card-writing cap reached)")


_CAP_DEFERRED = re.compile(r"^deferred (\d+)x: card-writing cap reached")


def _cap_deferrals(last_error: str | None) -> int:
    """How many runs in a row this filing stopped at its card-writing cap, from the ledger's note."""
    m = _CAP_DEFERRED.match(last_error or "")
    return int(m.group(1)) if m else 0


def _deferrals(last_error: str | None) -> int:
    """How many runs in a row this filing's attachment has failed on the network, from the ledger's note."""
    m = _DEFERRED.match(last_error or "")
    return int(m.group(1)) if m else 0


class EventXbrlPending(Exception):
    """A live filing's event XBRL has not reached NSE yet; the filing stays queued without spending an attempt."""


class AttachmentNotYet(Exception):
    """NSE lists the filing but its file is not there yet (a 404): it waits, without spending an attempt, up to
    ATTACHMENT_WAIT after the filing (owner, 25 Oct 2026: CGCL's press release was given up after three tries in about
    two hours and downloads fine later)."""


class NoTextAttachment(Exception):
    """The attachment holds nothing to read (a call's audio, a ZIP without a PDF): failed once, not retried."""


ATTACHMENT_WAIT = timedelta(hours=24)
MEMORY_SYNC_KEY = "memory_syncs:last"
MEMORY_SYNC_EVERY = timedelta(minutes=55)


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
    memory_only: int = 0    # older backfill filings read into memory with no card (settings.backfill_cards_from)
    slip_held: list[str] = field(default_factory=list)   # unit slips the filing's PDF text layer did not confirm: figures held out (F200)
    attachment_changed: int = 0  # known filings the exchange now serves with another file, queued again
    days_discovered: list[str] = field(default_factory=list)
    critic: dict = field(default_factory=dict)   # the shadow critic's counts this run (critic.py); empty when it did not run
    sweep: dict = field(default_factory=dict)    # the end-of-day sweep of held cards (sweep.py); empty outside its slot
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
    critic: dict | None = None   # a live published card's points for the shadow critic (critic.py); never written to D1


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
    def only_quotes(self) -> bool:
        """Every fault is a point whose quote does not carry it: none of the card's figures was found wrong or missing,
        no claim, scale, sum or headline failed. Such a card is published without those points (prune_quote_failures)."""
        return (bool(self.quotes) and self.score >= DEFAULT_THRESHOLD and self.quant.mismatches == 0 and not self.claims
                and not self.headline_ungrounded and not self.scale and not self.form and not self.amounts_ungrounded
                and not self.held)

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
    # a half-year, nine-month or year file's period is no quarter: nothing to shift by (MODIS, 24 Oct 2026, crashed)
    if quarter and quarters and quarter_index(quarter) is not None:
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


_FOREIGN_CRORE = re.compile(r"\b(" + "|".join(CURRENCY_CODES) + r"|US\$)\s*([\d,]+(?:\.\d+)?)\s*(cr\b|crores?\b)",
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


SCALE_BAND = 3.0   # UNIT_FIX_SCALE_GUARD: within this factor of one of the company's own quarter figures is "its scale"


def scale_crore(dossier: dict | None, periods: int = 2) -> list[float]:
    """The company's own money figures of its latest quarters in memory, both bases (revenue, total income, EBITDA, PBT, PAT):
    the scale a card amount is checked against by UNIT_FIX_SCALE_GUARD."""
    metrics = ("revenue", "total_income", "ebitda", "pbt", "pat", "pat_owners")
    d = dossier or {}
    rows = [m for m in list(d.get("financial_metrics") or []) + list((d.get("standalone") or {}).get("metrics") or [])
            if isinstance(m, dict) and m.get("metric") in metrics and isinstance(m.get("value"), (int, float))
            and re.fullmatch(r"Q[1-4]FY\d{2}", str(m.get("period") or ""))]
    latest = sorted({m["period"] for m in rows}, key=lambda p: quarter_index(p) or -1)[-periods:]
    return [abs(m["value"]) for m in rows if m["period"] in latest and abs(m["value"]) >= 1]


def _at_scale(value: float, scale: list[float]) -> bool:
    return any(s / SCALE_BAND <= abs(value) <= s * SCALE_BAND for s in scale)


def fix_unit_slips(out: Pass2Output, sources: tuple[str, ...], xbrl_crore=(), scale=()) -> dict[str, str]:
    """Correct, in code, card amounts that are a statement figure read at the wrong unit (grounding.
    unit_slips): in the card's text, its key numbers and changes, the timeline entry, and the reply's
    ₹ crore metrics for memory. Returns {as written: corrected}.

    `scale` (UNIT_FIX_SCALE_GUARD, CDSL nse-106838164): the company's own quarter figures; a correction that takes a figure at
    their scale (within 3x) to one that is not is no correction ("₹272 Cr" standalone revenue made ₹2.72 Cr beside a ₹394 Cr
    consolidated quarter)."""
    if out.card is None or not sources:
        return {}
    slips = unit_slips(_card_texts(out), sources[0], *sources[1:], xbrl_crore=xbrl_crore)
    if scale:
        kept = [s for s in slips if not (_at_scale(s[1], list(scale)) and not _at_scale(s[3], list(scale)))]
        for raw, value, _, right, _ in slips:
            if (raw, value) not in {(k[0], k[1]) for k in kept}:
                log.info("unit fix %s -> %s refused: %s is the company's own scale (UNIT_FIX_SCALE_GUARD)", raw, right, raw)
        slips = kept
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
        # a change the filing itself prints stands: Greenply's MDF revenue "+39.6% YoY" became -70.2% because the card's
        # two figures were the quarter and the year (held-card audit, 22 Oct 2026); the figures were the slip, not the %
        if any(re.search(rf"(?<![\d.,]){re.escape(m.group(2))}\s*%", src or "") for src in sources):
            continue
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
    """A results card's key numbers for revenue, EBITDA, PBT and PAT set from the XBRL file: exact
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
        if "margin" in (key.label or "").lower() or "%" in (key.value or "") or "(filing)" in (key.label or "").lower():
            continue   # "(Filing)": the company's own printed EBITDA (F151), not the file's line
        metric = next((name for name, pattern in _KEY_METRIC if pattern.search(key.label or "")), None)
        if metric == "pat" and re.match(r"-\s*pat_owners\b", key.quote or "") and card_ebitda_profit_v2():
            metric = "pat_owners"   # F151: the company's own name ("PAT") on the shareholders' profit line it headlines
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
        value = f"₹{m.value:,.2f} Cr"
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


_FILING_YOY = r"\s*%\s*(?:yoy\b|y-o-y|year[- ]on[- ]year|over (?:the )?(?:same|corresponding) (?:quarter|period))"
_FILING_QOQ = r"\s*%\s*(?:qoq\b|q-o-q|quarter[- ]on[- ]quarter|sequential)"


def _filing_labels(raw: str, filing: str, yoy: bool) -> bool:
    """The filing itself writes this change with this label: "a growth of 5.9% YoY" (Bandhan Bank, 2026-10-20)."""
    number = re.escape(raw.lstrip("+-−"))
    return bool(filing) and re.search(rf"(?<![\d.]){number}{_FILING_YOY if yoy else _FILING_QOQ}", filing, re.I) is not None


_BASIS_LINES = ("revenue", "ebitda", "pbt", "pat", "total_income", "interest_earned", "nii")
_BASIS_LABEL = {"ebitda": "EBITDA", "pbt": "PBT", "pat": "PAT", "nii": "NII", "total_income": "total income",
                "interest_earned": "interest earned"}


def basis_mixups(out: Pass2Output, tagged, standalone) -> list[str]:
    """A crore figure on a consolidated card that is the standalone file's figure for that line, not the consolidated
    one: Ceigall's EBITDA ₹121 Cr and margin beside consolidated revenue (independent review, 2026-10-21; owner: "not
    using consolidated numbers where those are there or mixing them with standalone"). Judged only where the two files
    differ by more than 1% for the quarter, at the figure's own decimals: at 3% HDFC Life's standalone PAT ₹508 Cr passed
    as consolidated (₹521.60 Cr, 2.6% apart; hourly review, 22 Oct 2026)."""
    if out.card is None or tagged is None or standalone is None or tagged.basis != "CONSOLIDATED":
        return []
    from .grounding import _tokens

    own = {m.metric: m.value for m in tagged.metrics if m.period == tagged.period and m.value is not None}
    other = {m.metric: m.value for m in standalone.metrics if m.period == tagged.period and m.value is not None}
    pairs = [(name, own[name], other[name]) for name in _BASIS_LINES if name in own and name in other
             and own[name] and abs(other[name] - own[name]) > 0.01 * abs(own[name])]
    if not pairs:
        return []
    found = []
    for text in _card_texts(out):
        clean = text.replace("**", "")
        for value, decimals, pos, kind, raw in _tokens(clean):
            if kind == "pct" or not re.match(r"\s*(?:cr\b|crores?\b)", clean[pos + len(raw):pos + len(raw) + 8], re.I):
                continue
            for name, consolidated, alone in pairs:
                if round(abs(alone), decimals) == round(abs(value), decimals) != round(abs(consolidated), decimals):
                    found.append(f'"{raw} Cr" is the standalone {_BASIS_LABEL.get(name, name)} '
                                 f"({alone:,.2f} Cr); this card is consolidated ({consolidated:,.2f} Cr): use the "
                                 "consolidated figure")
    return list(dict.fromkeys(found))[:4]


_PROFIT_GROUP = ("pat", "pat_owners")


def _standalone_hits(text: str, lines: list[tuple[tuple[str, ...], list[float], list[float]]]) -> list[tuple[str, str]]:
    """(figure as written, line) for each crore figure in `text` that equals a standalone value of a line (to the
    figure's own decimals) and none of the consolidated values of the same line group."""
    from .grounding import _tokens

    clean = text.replace("**", "")
    found = []
    for value, decimals, pos, kind, raw in _tokens(clean):
        if kind == "pct" or not re.match(r"\s*(?:cr\b|crores?\b)", clean[pos + len(raw):pos + len(raw) + 8], re.I):
            continue
        for names, consolidated, alone in lines:
            if any(round(abs(a), decimals) == round(abs(value), decimals) for a in alone) \
                    and not any(round(abs(c), decimals) == round(abs(value), decimals) for c in consolidated):
                found.append((raw, names[0]))
    return found


def standalone_figures_removed(out: Pass2Output, tagged, standalone) -> list[str]:
    """CARD_CONSOLIDATED_ONLY (F154; owner, 25 Oct 2026: consolidated first, standalone kept from the AI). On a
    consolidated card, a revenue / EBITDA / PBT / profit figure in the model's words that is the standalone file's value
    for that line and period but not the consolidated one is taken out: a fact, point, key number or change that states
    it is hidden, a sentence of the takeaway, catalyst, headline or timeline line that states it is cut (kept as it is when
    nothing would be left, for the number checks to judge). The profit lines are one group: the standalone PAT written
    as "profit to shareholders", or the reverse, is caught too. The card is not held. Returns what was removed."""
    if out.card is None or tagged is None or standalone is None or tagged.basis != "CONSOLIDATED":
        return []
    own = {m.metric: m.value for m in tagged.metrics if m.period == tagged.period and m.value is not None}
    other = {m.metric: m.value for m in standalone.metrics if m.period == tagged.period and m.value is not None}
    lines = []
    for names in [(n,) for n in _BASIS_LINES if n not in _PROFIT_GROUP] + [_PROFIT_GROUP]:
        differing = [other[n] for n in names if n in other and n in own and own[n]
                     and abs(other[n] - own[n]) > 0.01 * abs(own[n])]
        if differing:
            lines.append((names, [own[n] for n in names if n in own], differing))
    if not lines:
        return []
    notes: list[str] = []

    def hits(text, where: str) -> bool:
        found = _standalone_hits(str(text or ""), lines)
        for raw, name in found[:1]:
            notes.append(f'{where}: standalone figure on a consolidated card: "{raw} Cr" ({_BASIS_LABEL.get(name, name)}) removed')
        return bool(found)

    def clean(text: str | None, where: str) -> str | None:
        if not text or not hits(text, where):
            return text
        parts = re.split(r"(?<=[.;])\s+", text)
        kept = [x for x in parts if not _standalone_hits(x, lines)]
        return " ".join(kept) if kept else text

    card = out.card
    card.headline = clean(card.headline, "headline") or card.headline
    card.takeaway = clean(card.takeaway, "takeaway") or card.takeaway
    card.core_catalyst = clean(card.core_catalyst, "core_catalyst")
    card.what_happened = [f for f in card.what_happened if not hits(f.text, "what_happened")] or card.what_happened
    card.why_it_matters = [i for i in card.why_it_matters if not hits(i.text, "why_it_matters")]
    card.key_numbers = [k for k in card.key_numbers if not hits(f"{k.value} {k.change or ''}", "key_numbers")]
    card.notable_changes = [c for c in card.notable_changes if not hits(f"{c.previous or ''} ; {c.current or ''}", "notable_changes")]
    out.timeline_entry = clean(out.timeline_entry, "timeline") or out.timeline_entry
    for note in notes:
        log.info("%s", note)
    return notes


def period_mixups(out: Pass2Output, tagged: "xbrl_fast_path.XbrlResult | None", filing: str = "") -> list[str]:
    """A "% YoY" on the card that is the quarter-on-quarter change of a tagged figure (and no figure's
    YoY), or the reverse: SML's results cards called the fall from Q2 a fall from a year ago.

    Each change is compared with the changes of the period it is about, and only those: the period named
    just before it in its own sentence, else its key number's label, else the period the card's headline
    and timeline entry name (as xbrl_key_numbers reads them, d6e7c14). Comparing with the latest quarter
    alone held Jubilant's FY25 revenue "+7.9% YoY" as a quarter-on-quarter change; comparing with every
    period's would let a quarter's figure pass with the year's change (loop rounds 3a-3b, 2026-10-17).

    A change the filing itself writes with the same label is the company's own and is never flagged: Bandhan Bank's
    release says NII "representing a growth of 5.9% YoY", and its card was held because the tagged file's QoQ change
    was also near 5.9 (needs-review sweep, 2026-10-20)."""
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
            if _filing_labels(m.group(1), filing, is_yoy):
                continue
            if is_yoy and near(qoq) and not near(yoy):
                issues.append(f"\"{m.group(0)}\" is a quarter-on-quarter change, not year-on-year")
            elif not is_yoy and near(yoy) and not near(qoq):
                issues.append(f"\"{m.group(0)}\" is a year-on-year change, not quarter-on-quarter")
    return list(dict.fromkeys(issues))


# the headline of a company's press, media, investor or earnings release (RESULTS_PRESS_RELEASE)
_PRESS_RELEASE = re.compile(r"\b(?:press|media|investor|earnings|results)\s+release\b", re.I)
RELEASE_TEXT_CHARS = 12000   # how much of a release is added to its results card's text
_RESULTS_STATEMENT = re.compile(r"statement of (?:standalone |consolidated )?(?:un-?)?audited\b.{0,80}?financial results", re.I | re.S)
# A board outcome whose covering letter submits the results, the statement itself far down the file: Atul's outcome put
# the buyback's terms first and its statement at character 34,452, with the XBRL filed separately, so it was a
# CORPORATE_ACTION card that left out a 37% fall in profit (hourly review 23 Oct 2026). Read on the letter's first page
# only; a newspaper extract of the results or a notice of the meeting that will consider them is not the results.
_RESULTS_COVER = re.compile(r"\b(?:submit\w*|enclos\w*|attach\w*|furnish\w*)\b[^.]{0,160}?\b(?:un-?)?audited\b[^.]{0,80}?"
                            r"\bfinancial\s+results\b", re.I | re.S)
_RESULTS_COVER_NOT = re.compile(r"newspaper|advertis\w*|publication|published|extract|to\s+consider|will\s+be\s+considered|"
                                r"trading\s+window", re.I)
_TAKEOVER = re.compile(r"open offer|substantial acquisition of shares|\bSAST\b|regulation 3\(1\)|regulation 4\b", re.I)
_PROMOTER_DISCLOSURE = re.compile(r"regulation 29\b|reg\.? ?29\b|regulation 31\b|inter ?se transfer|\bgift(?:ed)?\b", re.I)
# A demand is a tax or duty raised on the company, not "demand for" its products: L&T's order release (21 Oct 2026, "the
# growing demand for ...") was typed LITIGATION_REGULATORY, and "awarded an EPC order" was not read as an order.
_TAX_OR_PENALTY = re.compile(r"\b(?:demand\s+(?:notice|order|of\b|raised|confirmed|for\s+(?:Rs|INR|₹))|(?:raised|received)\s+a\s+demand|"
                             r"challeng\w*\s+(?:the\s+)?(?:said\s+)?demand|"
                             r"(?:tax|duty)\s+demand|penalty|show[- ]cause|assessment order|tax order|adjudication|"
                             r"(?:income[- ]tax|GST|CGST|service tax|customs) (?:order|notice|demand|authorit))", re.I)  # "excluding GST" is an order
_REAL_ORDER = re.compile(r"letter of (?:award|intent)|\bLoA\b|\bLoI\b|work order|purchase order|order (?:received|bagged|secured|worth)|"
                         r"contract (?:awarded|worth|valued)|lowest bidder|\bL1\b|\bwins?\b[^.\n]{0,40}\borders\b|"
                         r"\b(?:wins?|secures?|bags?|receives?)\b[^.\n]{0,40}\border\s+(?:worth|from|for|valued)\b|"
                         r"\bawarded\s+(?:an?\s+|the\s+)?(?:[\w&-]+\s+){0,3}(?:order|contract)s?\b", re.I)


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


COMPANION_DAYS = 3


def companion_quarter(filing: Filing, dossier: dict) -> str | None:
    """The quarter of the company's results card filed in the COMPANION_DAYS before this results filing, when this one
    names no quarter a statement would ("quarter ended 30 September 2026"): a press release or an investor update says
    "Q2 FY27", and with no quarter D20 never ran, so 13 companies had two results cards for Q2FY27 on 28-29 Oct 2026
    (eClerx's statement at 18:58 and its press release at 19:09, Zensar, Acme Solar, Laurus...). The quarter is the
    latest one memory holds from that card's own filing."""
    try:
        at = datetime.fromisoformat(filing.filed_at)
    except (TypeError, ValueError):
        return None
    metrics = dossier.get("financial_metrics", [])
    for t in sorted(dossier.get("timeline", []), key=lambda t: str(t.get("date") or ""), reverse=True):
        if t.get("event_type") != "RESULTS" or t.get("news_id") == filing.news_id:
            continue
        try:
            when = datetime.fromisoformat(str(t.get("date")))
            if when > at or at - when > timedelta(days=COMPANION_DAYS):
                continue
        except (TypeError, ValueError):   # an unreadable or naive date is no companion
            continue
        if t.get("quarter"):
            return t["quarter"]   # the card named its own quarter (TODO 133)
        periods = [m["period"] for m in metrics if reported_by(m, t["news_id"]) and re.fullmatch(r"Q[1-4]FY\d{2}", str(m["period"]))]
        if periods:
            return max(periods, key=lambda p: quarter_index(p) or -1)
    return None


def merged_priority(read: list[str], now: list[str], order: list[str]) -> list[str]:
    """The history queue's priority list written back at the end of a backfill pass: the companies added since it was read (a
    requeue by id meanwhile) first, then those read at the start that still have history left."""
    left = set(order)
    return [s for s in now if s not in set(read)] + [s for s in read if s in left]


_RESULTS_FOR = re.compile(r"financial\s+results\s+(?:of\s+the\s+bank\s+|of\s+the\s+company\s+)?for\s+the\s+"
                          r"(?:quarter|half[\s-]*year|period|nine\s+months|year|financial\s+year)", re.I)
LACKS_RESULTS_MIN_CHARS = 1500   # a filing with less text than this (a scan OCR did not read) is never retyped


def lacks_results(text: str) -> bool:
    """A filing's text with enough words to judge, and none of what a results filing carries: the statement's heading
    (`_RESULTS_STATEMENT`), a covering letter submitting the results (`results_cover`), or "financial results for the quarter"
    (TMB nse-106836238, a note on a ₹304 Cr ECL provision typed RESULTS, took the results path and became a second card)."""
    t = text or ""
    if len(t.strip()) < LACKS_RESULTS_MIN_CHARS:
        return False
    head = t[:40000]
    return not (_RESULTS_STATEMENT.search(head) or results_cover(t) or _RESULTS_FOR.search(head))


def carries_results(event_type: str, text: str, tagged=None) -> bool:
    """A filing typed OTHER, GOVERNANCE or CORPORATE_ACTION that carries the company's results statement (a board
    outcome with the results and a stock split): it is the results filing, before pass 2 as after it."""
    return event_type in ("OTHER", "GOVERNANCE", "CORPORATE_ACTION") and (
        (tagged is not None and tagged.kind == "RESULTS") or bool(_RESULTS_STATEMENT.search(text[:20000]))
        or results_cover(text))


_DECK_NAME = re.compile(r"presentation|investor[_\s-]*(?:ppt|deck)|(?<![a-z])ppt(?![a-z])|transcript|earnings[_\s-]*call", re.I)
_RESULTS_NAME = re.compile(r"result|outcome", re.I)   # anywhere in the file name, glued or not ("FinancialResultsandPresentation")


def is_deck_or_transcript(filing: Filing) -> bool:
    """An investor presentation or a call transcript by its own file name (COALINDIA_29102026183725_Presentation.pdf), never
    by the headline alone: "Outcome of Board Meeting - Results and Investor Presentation" over a generic file name is the
    results filing (blind review, 30 Oct 2026). A file name that also says result or outcome stays results."""
    name = (filing.pdf_url or "").rsplit("/", 1)[-1]
    return bool(_DECK_NAME.search(name)) and not _RESULTS_NAME.search(name)


def results_cover(text: str) -> bool:
    """The covering letter submits the company's results (`_RESULTS_COVER`), on its first page."""
    head = (text or "")[:4000]
    for m in _RESULTS_COVER.finditer(head):
        # the words around the sentence decide, not a buyback's "publication fees" further down the letter
        if not _RESULTS_COVER_NOT.search(head[max(0, m.start() - 150):m.end() + 40]):
            return True
    return False


def event_type_rules(event_type: str, filing: Filing, text: str, tagged) -> str:
    """Event types the model got wrong in the smoke-test audit, settled from the filing itself:
    results statements typed OTHER (board outcomes carrying the results); an open offer typed as a
    rights issue or fundraise (no new shares); a promoter's Reg 29 gift typed M&A; a tax demand or
    penalty typed as an order win."""
    head = f"{filing.headline} {filing.subject} {text[:3000]}"
    if carries_results(event_type, text, tagged):
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


# A listed subsidiary's results passed on by its parent (Reg 30(9)): Vedanta's letter enclosing Hindustan Zinc's Q2FY27
# results became Vedanta's results card, HZL's revenue against Vedanta's own year-ago (-62%), and HZL's figures went into
# Vedanta's memory (owner, 2026-10-20). The covering letter names the subsidiary before the word "results".
_SUBSIDIARY_RESULTS = re.compile(
    r"(?P<name>[A-Z][A-Za-z0-9&.,'\- ]{2,80}?\b(?:Limited|Ltd\.?))\s*(?:\(\s*[“\"']?[^)]{1,20}?[”\"']?\s*\))?\s*,?\s*"
    r"(?:is\s+)?(?:a|an|the|our)\s+(?:material\s+)?(?:(?:wholly[- ]owned|listed|step[- ]down|unlisted)\s+)?subsidiar(?:y|ies)\b"
    r"[^;]{0,400}?\bresults\b", re.S)   # "submitted: 1. Unaudited ... results": a list number is no sentence end


# A filing that only schedules a call or links its audio, or only declares a dividend, goes to memory as a dated line
# and gets no card (owner, 2026-10-20: "Amagi schedules Q2FY27 earnings call for Nov 6", "Hexaware declares 2nd interim
# dividend"; 17 call-logistics and 6 dividend cards in the week). NSE's headlines are generic ("Analysts/Institutional
# Investor Meet/Con. Call Updates", "Corporate Action-Dividend"), so the rule book's headline rules never saw the words;
# the filing's first page decides. A transcript, a deck (more than a few pages) or results keep their card.
_CALL = re.compile(r"(?:earnings|conference|con\.?|investors?|analysts?)\s*(?:call|meet)|analysts?\s*(?:/|and|&)\s*"
                   r"(?:institutional\s+)?investors?\s+meet", re.I)
_CALL_LOGISTICS = re.compile(r"\bschedul\w*|\bintimat\w*|\bwill\s+(?:be\s+)?(?:held|host\w*|organi[sz]\w*|participat\w*)|"
                             r"\baudio\b|\brecording\b|web\s*-?\s*link|\bre-?schedul\w*|\bpostpone\w*|\bdial[- ]?in\b", re.I)
_DIVIDEND = re.compile(r"\bdividends?\b", re.I)
_DIVIDEND_ONLY_NOT = re.compile(r"buy-?back|\bbonus\b|\bsplit\b|sub-?division|rights\s+issue|fund\s*rais|"
                                r"financial\s+results|results\s+for\s+the\s+(?:quarter|year|half)|\bbonds?\b|debentures?|"
                                r"\bncds?\b|borrow\w*|capex|capital\s+expenditure|acqui\w*|merger|amalgamat\w*|"
                                r"\binvest\w*|preferential|preference\s+shares?|\bncrps\b|\bqip\b|warrants?|"
                                r"change\s+(?:of|in)\s+(?:the\s+)?name|name\s+change|auditors?\b|\bagm\s+(?:date|on)|"
                                r"annual\s+general\s+meeting\s+(?:of|on|will)", re.I)


# A change of name or symbol goes to memory too (owner, 2026-10-20: "ICICI Prudential Life to change name to ICICI Life
# Insurance and symbol to ICICILIFE" needs no card): the timeline keeps it, and the company master takes the new name.
_NAME_CHANGE = re.compile(r"change\s+(?:of|in)\s+(?:the\s+)?(?:name|symbol)|name\s+change|new\s+(?:name|symbol)|"
                          r"(?:name|symbol)\s+(?:of\s+the\s+company\s+)?(?:has\s+been\s+|is\s+|will\s+be\s+)?changed", re.I)
_NAME_CHANGE_NOT = re.compile(r"merger|amalgamat\w*|de-?merg\w*|scheme\s+of\s+arrangement|acqui\w*|financial\s+results|"
                              r"buy-?back|\bbonus\b|rights\s+issue|preferential|fund\s*rais", re.I)


# A fine, penalty or tax demand and nothing else, below the governance rule's floor (5% of annual profit, at least ₹1 lakh: owner, 2026-10-19):
# Rashi Peripherals' ₹1.68 lakh NSE fine for Reg 17(1A) came as a card (owner, 2026-10-20), because the quarterly
# governance report applies that floor and a standalone fine letter did not; "Schneider Electric Infra appellate
# authority upholds ₹0.05 Cr transitional ITC demand and penalty" the same. A ban, suspension, freeze, inspection or
# fraud keeps its card whatever the amount.
_FINE = re.compile(r"\bfines?\b|\bpenalt(?:y|ies)\b|\bdemand\b", re.I)   # a small tax demand too (Schneider ₹0.05 Cr)
_FINE_SEVERE = re.compile(r"debar\w*|suspen\w*|\bban(?:ned)?\b|restrain\w*|cancel\w*|revo(?:k|c)\w*|attach\w*|freez\w*|"
                          r"prosecut\w*|fraud|arrest\w*|insolvency|usfda|warning\s+letter|import\s+alert|"
                          r"search\s+and\s+seizure|\braid\b|licen[cs]e", re.I)


# an amount with its digits ("Rs, " is no amount: governance_xbrl's pattern took it as ₹0), in any unit filings use
_AMOUNT = re.compile(r"(?:\brs\.?|\binr\b|₹|\brupees\b)\s*(\d[\d,]*(?:\.\d+)?)\s*(?:/-)?\s*"
                     r"(crores?|cr\b\.?|lakhs?|lacs?|million|mn\b)?", re.I)


def _amount_rupees(m: re.Match) -> float:
    value = float(m.group(1).replace(",", "") or 0)
    unit = (m.group(2) or "").lower()
    return value * (1e7 if unit.startswith("cr") else 1e5 if unit.startswith(("lakh", "lac")) else 1e6 if unit.startswith(("million", "mn")) else 1)


def small_fine(first_page: str, annual_profit_cr: float | None) -> bool:
    """A fine and nothing more, every amount on the page below governance_xbrl's floor for this company."""
    from .governance_xbrl import MATERIAL_SHARE_OF_PROFIT, MINOR_PENALTY_RUPEES

    page = " ".join((first_page or "").split())
    if not _FINE.search(page) or _FINE_SEVERE.search(page):
        return False
    # an amount with no unit of its own is in the unit the page's table declares ("(in Rs. crores)": Jubilant's ₹22.10 Cr
    # demand read as ₹22.10): the largest unit the page names, so a doubt keeps the card
    implied = 1e7 if re.search(r"\bcrores?\b|\bcr\b", page, re.I) else 1e5 if re.search(r"\blakhs?\b|\blacs?\b", page, re.I) else None
    found = list(_AMOUNT.finditer(page))
    if implied is None and any(not m.group(2) and "." in m.group(1) for m in found):
        return False   # "Rs. 42.41" on a page that names no unit (Jubilant Pharmova's demand): a doubt keeps the card
    amounts = [_amount_rupees(m) * (implied or 1 if not m.group(2) else 1) for m in found]
    if not amounts:
        return False   # a fine with no stated amount is raised (as the governance rule does)
    floor = max(MINOR_PENALTY_RUPEES, (annual_profit_cr or 0) * 1e7 * MATERIAL_SHARE_OF_PROFIT)
    return max(amounts) < floor


def annual_profit_cr(dossier: dict | None) -> float | None:
    """The last full year's profit memory holds (the latest FYxx PAT), for the materiality floors."""
    years = [m for m in (with_year_hold(dossier) or {}).get("financial_metrics", []) if m.get("metric") in ("pat", "pat_owners")
             and re.fullmatch(r"FY\d{2}", str(m.get("period") or "")) and isinstance(m.get("value"), (int, float))]
    return max(years, key=lambda m: m["period"])["value"] if years else None


def memory_only(filing: Filing, first_page: str, pages: int, profit_cr: float | None = None) -> str | None:
    """Why this filing gets a timeline line and no card ("call logistics", "dividend", "name change", "small fine"), or
    None. `profit_cr` is the company's annual profit, for the fine floor."""
    page = " ".join((first_page or "").split())
    if pages <= 4 and small_fine(page, profit_cr):
        return "small fine"
    if pages <= 4 and _NAME_CHANGE.search(f"{filing.headline} {filing.subject} {page}") and not _NAME_CHANGE_NOT.search(page):
        return "name change"
    if pages <= 3 and not is_transcript(filing) and not _TRANSCRIPT.search(_TRANSCRIPT_LATER.sub(" ", page)) and _CALL.search(page) \
            and _CALL_LOGISTICS.search(page):
        return "call logistics"
    if pages <= 4 and _DIVIDEND.search(f"{filing.headline} {filing.subject} {page}") and not _DIVIDEND_ONLY_NOT.search(page) \
            and not _RESULTS_STATEMENT.search(page):
        return "dividend"
    return None


def subsidiary_results(filing: Filing, text: str) -> str | None:
    """The subsidiary whose results this filing passes on, when its covering letter says so; None for the company's
    own results."""
    m = _SUBSIDIARY_RESULTS.search(" ".join((text or "")[:6000].split()))
    if not m:
        return None
    # the company's own words before the name ("we hereby inform that Hindustan Zinc Limited") are not its name
    tail = re.search(r"((?:[A-Z][\w&.'\-]*\s+){0,8}(?:Limited|Ltd\.?))$", m.group("name").strip(" ,"))
    name = (tail.group(1) if tail else m.group("name")).strip(" ,.")
    own = re.sub(r"\W+|limited|ltd", "", (filing.company_name or "").lower())
    return None if own and own in re.sub(r"\W+|limited|ltd", "", name.lower()) else name


# Another company's results filed by the listed one, named in the statement's heading or the covering letter but not
# called a subsidiary (CARD_OTHER_ISSUER, blind audit 1 Nov 2026): HEG Advanced Materials (formerly HEG Limited) filed the
# results of HEG Limited (formerly HEG Graphite Limited), the demerged graphite company, and the card headlined them as its
# own. A former name is no proof: here the other company took it. The name the heading prints is read with its own
# "(formerly ...)" clause; a company that was formerly something the listed company never was is another company.
_COMPANY = r"[A-Z][A-Za-z0-9&.'\-]*(?:\s+(?:[A-Z][A-Za-z0-9&.'\-]*|of|and|&))*?\s+(?i:Limited|Ltd\.?)"
_ISSUER_NAMED = re.compile(rf"(?P<name>{_COMPANY})(?:\s*\(\s*(?i:formerly|earlier)\s+(?i:known\s+as\s+)?(?P<former>{_COMPANY})\s*\))?")
_RESULTS_OF = re.compile(rf"\b(?i:results)\s+of\s+(?P<name>{_COMPANY})(?:\s*\(\s*(?i:formerly|earlier)\s+(?i:known\s+as\s+)?"
                         rf"(?P<former>{_COMPANY})\s*\))?")
_COMPANY_FILLER = re.compile(r"\b(?:the|limited|ltd|private|pvt|company|co)\b|[^a-z0-9]+")


def _bare_company(name: str | None) -> str:
    return _COMPANY_FILLER.sub("", (name or "").lower())


_NAME_STOP = {"the", "limited", "ltd", "private", "pvt", "and", "of", "company", "co"}
_EXCHANGE = re.compile(r"\b(?:stock\s+exchange|nse|bse|cse|nseindia|bseindia|exchange)\b|^(?:national|bombay|calcutta)\b", re.I)


def _name_words(s: str) -> list[str]:
    """Words of a name for a fuzzy compare: case, "&"/"and", punctuation, Limited/Ltd/Private and ise/ize ignored."""
    s = re.sub(r"[^a-z0-9]+", " ", (s or "").lower().replace("&", " and "))
    return [re.sub(r"is(e[sd]?|ing|ation)\b", r"iz\1", w) for w in s.split() if w not in _NAME_STOP]


def _edit_within(a: str, b: str, limit: int) -> bool:
    if abs(len(a) - len(b)) > limit:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] <= limit


def _name_present(name: str | None, head: str) -> bool:
    """Whether a company's name (fuzzily: all its distinctive words, or its squashed name within 2 edits for OCR garble)
    appears in the text."""
    words, hw = _name_words(name or ""), _name_words(head)
    if not words:
        return False
    if set(words) <= set(hw):
        return True
    bare = "".join(words)
    limit = 2 if len(bare) >= 8 else 1 if len(bare) >= 5 else 0
    for k in range(max(1, len(words) - 1), len(words) + 2):
        for i in range(len(hw) - k + 1):
            if _edit_within("".join(hw[i:i + k]), bare, limit):
                return True
    return False


def other_issuer_results(filing: Filing, text: str, former_names: list[str] | None = None) -> str | None:
    """The company whose results this filing carries when it is not the listed company (CARD_OTHER_ISSUER), else None.
    Read from the name printed just above each results statement heading and from "results of <name>" in the covering
    letter. Any heading in the listed company's own name means its own results. A name the listed company once had counts
    as its own unless that heading names a former name the listed company never had (HEG Limited, formerly HEG Graphite)."""
    own = _bare_company(filing.company_name)
    if not own:
        return None
    formers = {_bare_company(n if isinstance(n, str) else (n or {}).get("name")) for n in former_names or []} - {""}
    flat = " ".join((text or "")[:40000].split())

    formerly: set[str] = set()   # non-own names printed with a "(formerly ...)" clause

    def owner(m: re.Match) -> tuple[str, bool]:
        """(the issuer's name, whether it is the listed company)."""
        tail = re.search(rf"({_COMPANY})$", m.group("name"))   # the last company name, not the words before it
        name = (tail.group(1) if tail else m.group("name")).strip(" ,.")
        name = re.sub(r"^(?:\S+[.:;]\s+)+(?=[A-Z])", "", name)   # "Board. HEG LIMITED": a sentence's end is no part of it
        bare, former = _bare_company(name), _bare_company(m.group("former"))
        if former and bare != own and not (bare in formers and (former == own or former in formers)):
            formerly.add(name)
        if bare == own or (len(own) >= 4 and own in bare):
            return name, True
        if bare in formers and (not former or former == own or former in formers):
            return name, True    # a filing from before the rename
        return name, False

    named = [owner(m) for m in _RESULTS_OF.finditer(flat[:6000])]   # the covering letter's own spelling first
    for h in _RESULTS_STATEMENT.finditer(flat):
        window = flat[max(0, h.start() - 400):h.start()]
        found = list(_ISSUER_NAMED.finditer(window))
        if found:
            named.append(owner(found[-1]))
    named = [(n, o) for n, o in named if not _EXCHANGE.search(n)]   # the exchange the letter is addressed to is no issuer
    if not named or any(is_own for _, is_own in named):
        return None
    # Hold only when the listed company's own name, or a former one, is nowhere in the letter's first 6,000 characters
    # (false holds: name fragments, OCR garble, letterhead prefixes, spellings, former names).
    # Exception (HEGAM): a name printed with "(formerly ...)" that is not the listed company's, in "results of <name>" or
    # a statement heading, is positive evidence by itself: the own name in the letterhead does not clear it, and that
    # name being one of the listed company's former names is just what happened there (the other company took it).
    strong = {_bare_company(n) for n, o in named if n in formerly}
    head = flat[:6000]
    own_names = [filing.company_name] + [n for n in former_names or [] if _bare_company(n if isinstance(n, str) else (n or {}).get("name")) not in strong]
    if strong:
        return next(n for n, _ in named if _bare_company(n) in strong)
    if not any(_name_present(n if isinstance(n, str) else (n or {}).get("name"), head) for n in own_names):
        return named[0][0]
    return None


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


# The model checking itself in the card's words: "above Q4FY26's ₹805 Cr? No, below; it is the second-highest" (SBI Life,
# needs-review sweep 2026-10-20). A reader gets the conclusion, not the working.
_WORKING = re.compile(r"\?\s*(?:no|yes)\b\s*[,;.]|\b(?:wait|hmm)\s*[,.]|\bactually,?\s+no\b|\blet me (?:check|recompute|re-?check)\b", re.I)


# A figure taken out with its words left round it: "holds ** ** stake", "passed with over votes in favour", "margin moved to
# 11.06% from in Q1FY26", "₹150 Cr NCD issuance, of net worth" - 28 sentences on 18 stored cards, all blanks (needs-review
# sweep, 2026-10-20), most from a second opinion told to remove a figure no source carries. A label's bold next to its value
# ("rating:** **76") is not one.
_BLANK = re.compile(r"(?:^|\s)\*\*\s+\*\*(?=[\s,.;]|$)"
                    r"|\b(?:with|only|over)\s+(?:over\s+)?(?:of|votes?)\b|\bto\s+via\b|\bfrom\s+in\s+(?:Q[1-4]|H[12]|FY)"
                    r"|,\s+of\s+(?:its\s+)?(?:FY\d{2}\s+|TTM\s+|annual\s+)?(?:revenue|net worth|turnover|market cap\w*|sales)\b", re.I)


def working_text(out: Pass2Output) -> list[str]:
    """Sentences that show the model's working, or a figure's blank, as problems for the second provider to rewrite."""
    texts = _card_texts(out) if out.card is not None else []
    found = [f'"{t[:80]}" shows its working: state the conclusion only' for t in texts if _WORKING.search(t)]
    found += [f'"{t[:80]}" has a figure missing from it: state the figure or rewrite the sentence without it'
              for t in texts if _BLANK.search(t)]
    return found[:3]


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
        # Not done: reading a figure from another verified quote on the card. Tried 2026-10-20 and audited: of 20 figures
        # it accepted, an independent check found 4 wrong (₹ million read as crore, another year's derived EBITDA, figures
        # only in the card's own notes) - 20%, far above the gate. A figure answers to its own quote.
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


_QUOTE_POINT = re.compile(r'^(key number|notable change|why it matters) "(.*)" (?:quotes a sentence|states )', re.S)
_QUOTE_FACT = re.compile(r'^"(.*)" states .*, which its own quote does not$', re.S)


def prune_quote_failures(out: Pass2Output, problems: list[str], moved: list[str] | None = None) -> list[str] | None:
    """Take off the face, in place, the points whose quote does not carry them (owner, 2026-10-21: "Needs review · 475":
    cards held while nothing on them was found wrong). The 20 Oct hand review read 108 cards held only this way: 77
    right, 20 minor, 11 wrong (10%), against 23% of the published cards reviewed on 21 Oct; the point goes, the rest of
    the card is published. Returns what was dropped, or None when a problem names no point that can go (the last fact,
    or a problem of another form): then the card stays held. Each point taken off is added to ``moved`` as text: the
    card shows it behind the tap "Facts the checks could not quote", not deleted (owner, 24 Oct 2026: the daily audits
    found 32 of 34 pruned points true)."""
    card = out.card
    if card is None:
        return None
    dropped: list[str] = []
    taken: list[str] = []
    for problem in problems:
        if problem.startswith("dropped: "):
            continue   # already out of the card (check_quotes)
        point, fact = _QUOTE_POINT.match(problem), _QUOTE_FACT.match(problem)
        if point:
            kind, label = point.group(1), point.group(2)
            if kind == "key number":
                kept = [k for k in card.key_numbers if (k.label or "") != label]
                taken += [_point_text(k.label, k.value, k.change) for k in card.key_numbers if k not in kept]
                hit, card.key_numbers = len(kept) < len(card.key_numbers), kept
            elif kind == "notable change":
                kept = [c for c in card.notable_changes or [] if (c.metric or "") != label]
                taken += [_point_text(c.metric, " → ".join(x for x in (c.previous, c.current) if x), c.change)
                          for c in card.notable_changes or [] if c not in kept]
                hit, card.notable_changes = len(kept) < len(card.notable_changes or []), kept
            else:
                kept = [i for i in card.why_it_matters if (i.text or "")[:48] != label]
                taken += [i.text for i in card.why_it_matters if i not in kept and i.text]
                hit, card.why_it_matters = len(kept) < len(card.why_it_matters), kept
        elif fact:
            kept = [f for f in card.what_happened if f.text.replace("**", "")[:60] != fact.group(1)]
            hit = 0 < len(kept) < len(card.what_happened)   # never the card's last fact
            if hit:
                taken += [f.text for f in card.what_happened if f not in kept]
                card.what_happened = kept
        else:
            return None
        if not hit:
            return None
        dropped.append(problem)
    if moved is not None:
        moved += [t for t in dict.fromkeys(taken) if t]
    return dropped


def _point_text(label: str | None, value: str | None, change: str | None) -> str:
    """A key number or notable change as one line for the card's "could not quote" list."""
    text = ": ".join(x for x in (label, value) if x)
    return f"{text} ({change})" if change else text


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


_CRORE_OF = {"million": 0.1, "millions": 0.1, "mn": 0.1, "billion": 100.0, "billions": 100.0, "bn": 100.0,
             "lakh": 0.01, "lakhs": 0.01, "crore": 1.0, "crores": 1.0, "thousand": 1e-4, "thousands": 1e-4}


def foreign_deal_amount(amount_cr: float | None, text: str) -> str | None:
    """The filing's foreign-currency amount a deal's ₹ crore figure is, when the filing writes no rupee amount of that
    size: "USD 138 million" as amount_cr 13.8 (or 138). None when the amount is a rupee figure the filing states."""
    from .grounding import _FOREIGN, _tokens

    if not amount_cr or not text:
        return None
    close = lambda a, b: abs(a - b) <= 0.005 * max(abs(a), abs(b)) + 1e-9
    hit = None
    for m in _FOREIGN.finditer(text):
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        scale = _CRORE_OF.get((m.group(2) or "").lower())
        if any(close(amount_cr, value * f) for f in {1.0, scale or 1.0}):
            hit = " ".join(m.group(0).split())
            break
    if hit is None:
        return None
    rupees = [v for v, *_ in _tokens(_FOREIGN.sub(" ", text))]
    if any(close(amount_cr, v * f) for v in rupees for f in (1.0, 1e-7, 0.01, 0.1, 100.0)):
        return None   # the filing also writes it in rupees ("USD 12 mn (₹100 Cr)" style): a real ₹ figure
    return hit


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
    foreign = foreign_deal_amount(deal.amount_cr, text)
    if foreign:
        # "USD 138 million" stored as ₹13.8 Cr: every proportion of it (of revenue, of market cap) ~85x small (data
        # chain audit A4, 22 Oct 2026). No ₹ size then: the card's facts keep the amount in its own currency.
        notes.append(f"deal size ₹{deal.amount_cr:g} Cr dropped: it is the filing's {foreign}, not a rupee amount")
        deal.amount_cr = None
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
    # a fundraise's or merger's terms are figures on the card's face: each kept only when the filing states it
    if deal is not None and text and any(getattr(deal, f, None) is not None for f in ("issue_price", "discount_pct", "new_shares", "swap_ratio")):
        from .grounding import SourceIndex

        index = SourceIndex(text[:60000])
        for field, decimals in (("issue_price", 2), ("discount_pct", 2), ("new_shares", 0)):
            value = getattr(deal, field, None)
            if value is not None and not index.stated(float(value), decimals, (1,)):
                notes.append(f"deal {field} {value:g} dropped: not stated in the filing")
                setattr(deal, field, None)
        ratio = deal.swap_ratio
        if ratio and not all(index.stated(float(n), 2, (1,)) for n in re.findall(r"\d+(?:\.\d+)?", ratio)):
            notes.append(f"deal swap ratio {ratio!r} dropped: its numbers are not in the filing")
            deal.swap_ratio = None
    # a target or seller is a name on the card's face: kept only when the filing names it (a model's guess at who
    # sells is worse than none)
    for field in ("target", "seller"):
        named = getattr(deal, field, None) if deal is not None else None
        if named and text and not _named_in(named, text):
            notes.append(f"deal {field} dropped: {named!r} is not named in the filing")
            setattr(deal, field, None)
    if notes:
        log.info("deal guards for %s: %s", filing.news_id, notes)
    return notes


_NAME_WORDS = re.compile(r"[A-Za-z0-9&]{3,}")
_NAME_FILLER = {"the", "and", "limited", "ltd", "private", "pvt", "company", "india", "its", "from", "with"}


def _named_in(name: str, text: str) -> bool:
    """Whether the filing names this party: every distinctive word of the name is in the text (case and
    punctuation aside), so "JKJTL" or "REC Power Development and Consultancy Limited" passes and an invented party does not."""
    words = [w.lower() for w in _NAME_WORDS.findall(name) if w.lower() not in _NAME_FILLER]
    if not words:
        return True
    hay = re.sub(r"[^a-z0-9&]+", " ", text.lower())
    return all(re.search(rf"\b{re.escape(w)}\b", hay) for w in words)


def derived_figures(card, quant, sources: tuple[str, ...]) -> list[float]:
    """Figures code computed from the filing's own: an impact verified from sourced inputs, and a deal's
    size from its buyers' shares x price (apply_deal_guards). SML's ₹554.65 Cr - 85,33,053 shares at ₹650
    - was held as a number the filing does not print (loop round 3b, 2026-10-17)."""
    derived = [i["computed"] for i in quant.items
               if i.get("check") == "VERIFIED" and not i.get("unsourced_inputs") and i.get("computed") is not None]
    if card.deal_value and card.deal_value.tranches and sources:
        derived.append(gate.tranche_total_cr(card.deal_value.tranches, sources[0]))
    return derived


GROWN_ORDER = 1.25   # a stage move (LOI -> work order) keeps the order's value; more than a quarter bigger is another order


def grown_order(deal, view: dict | None) -> bool:
    """An order said to move an earlier order on, but more than a quarter bigger than it: a new order (OSWALPUMPS nse-106836003,
    audit of 1 Nov 2026: a Rs 235.92 Cr order for an additional 10,000 pumps linked to May's Rs 162.06 Cr one as its work order,
    so the card said "stage update, not a new order" and memory's May order became Rs 235.92 Cr). A smaller amount stays
    (part of an LOI converted)."""
    if deal is None or deal.kind != "ORDER" or not deal.updates_deal_id or not deal.amount_cr:
        return False
    earlier = next((d for d in (view or {}).get("deals", []) if d.get("id") == deal.updates_deal_id), None)
    base = (earlier or {}).get("amount_cr")
    return isinstance(base, (int, float)) and base > 0 and deal.amount_cr > GROWN_ORDER * base


def check_card_all(out: Pass2Output, view: dict | None, sources: tuple[str, ...], history: list[dict] | None = None) -> CardChecks:
    """Memory-id hygiene, then the number, math, claim and scale checks (`history`: the dossier's
    stored financial metrics, which the reply's quarterly figures are compared with)."""
    card = out.card
    valid_refs = memory_ids(view)
    for insight in card.why_it_matters:
        insight.memory_refs = [r for r in insight.memory_refs if r in valid_refs]
    if card.deal_value and card.deal_value.updates_deal_id not in valid_refs:
        card.deal_value.updates_deal_id = None  # only a deal the model was shown can be updated
    if card.deal_value and grown_order(card.deal_value, view):
        card.deal_value.updates_deal_id = None  # a bigger order is a new one, not the earlier order's next stage
    reconcile_call_read(card, view)
    quant = check_quant(card.quantified_impact, *sources)
    derived = derived_figures(card, quant, sources)
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
        gateway.pass2_cap_s = settings.pass2_cap_s   # one filing's card-writing time (TODO 35)
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
        # One packer per (backfill?, long?): live and backfill filings never share a request, so a backfill pack can be
        # kept off the best writers' live reserve (gateway `live_reserve`), and long filings are packed only with each
        # other, a few to a request (ai-quality plan item 1: long ones fell to the weakest writer one request each).
        self._packers: dict = {}   # (bulk, long) -> Packer
        if settings.pass2_pack > 1 and gateway.has_route("pass2_packed"):
            from .ai.packer import Packer

            for bulk in (False, True):
                wait_s = settings.pass2_pack_wait_bulk_s if bulk else settings.pass2_pack_wait_s
                self._packers[(bulk, False)] = Packer(gateway, size=settings.pass2_pack, wait_s=wait_s, bulk=bulk)
                if settings.pass2_pack_long > 1:
                    self._packers[(bulk, True)] = Packer(gateway, size=min(settings.pass2_pack_long, settings.pass2_pack),
                                                         wait_s=wait_s, max_chars=LONG_PACK_MAX_CHARS,
                                                         bulk=bulk)
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
        self._slice_end: float | None = None   # the current slice's end (_in_slices, _fresh): no filing starts past it
        self._pause_checked = float("-inf")   # monotonic time of the last look at the nightly pause (pause.py); -inf, not 0: a fresh runner's clock starts near 0
        self._paused = False
        self._blocked: SourceBlockedError | None = None
        self._usage_lock = Lock()
        self._commit_lock = Lock()  # companies commit from worker threads; the R2 day archive is read-modify-write
        self._universe: tuple[set[str], float] | None = None
        self._examples: dict[tuple[str, str], dict[str, list[dict]]] = {}
        self._learned: dict | None = None   # Loop 1 state: post-mortem queue, lessons, dampened categories
        self._files: dict[str, list[tuple[str, str, str]]] = {}   # scrip -> (filed_at, news_id, sha256 of the file) this run
        self._bodies: dict[str, list[tuple[str, str, duplicates.Body]]] = {}  # scrip -> (filed_at, news_id, body) this run
        self._held_this_run: set[str] = set()   # news_ids whose card this run held (D20: not the quarter's card)
        self._shown_this_run: set[str] = set()  # news_ids whose card this run published (repeated_order)
        self._xbrl_links: dict[str, list[XbrlLink]] = {}  # scrip -> its results archive, read once a run
        self._results_quarter_basis: dict[tuple[str, str], str | None] = {}  # the basis of this run's quarter claims
        self._holds = gate.load_holds(settings.config_dir / settings.card_holds_file)  # news_id -> reason
        self._results_quarters: dict[tuple[str, str], str] = {}  # (scrip, quarter) -> the results filing with its card (D20)
        self._superseding: dict[str, tuple[list[str], str]] = {}  # news_id -> later filings with its quarter's card (D20)
        self._critic_jobs: list[dict] = []   # live cards committed this run, for the shadow critic (critic.py)
        # A card's memory waits for its card row (owner, 25 Oct 2026, after the architecture audit): written to the store
        # only once the batch holding the card is committed, so a run cut short or a rejected row leaves no memory
        # without its card. Until then the company's later filings in this run read it from here (one company's
        # filings run in order in one job). {scrip: [(news_id, memory, memory as read)]}
        self._pending_memory: dict[str, list[tuple[str, dict, dict]]] = {}

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
        sources = self.sink.known_sources(key)
        known = set(sources) | set(noise)
        if self._on_nse():
            filings = self.nse.announcements(day, scrip_for=self._nse_map().scrip_for)
        else:
            filings = self.bse.announcements(day, known=None if full else known)
        count = self._record(key, filings, noise, known, sources)
        if key not in self.stats.days_discovered:   # today is looked at again after each slice: listed once
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
                sources = self.sink.known_sources(key)
                found += self._record(key, filings, noise, set(sources) | set(noise), sources)
            start = end + timedelta(days=1)
        return found

    def retriage_returning(self, today: date, deadline: float, max_companies: int = RETURNING_PER_RUN) -> int:
        """Companies back in the universe (universe.RETURNING_KEY, written at each rebuild): the filings they made
        while out were set aside as "outside universe"; queue them now (owner, 22 Oct 2026). A few companies a run;
        one is struck off the list once read, and one whose lookup fails stays for the next run. Returns how many
        filings were queued."""
        raw = self.sink.kv_get(universe.RETURNING_KEY)
        waiting: dict[str, str] = json.loads(raw) if raw else {}
        if not waiting:
            return 0
        earliest = self.settings.backfill_start
        queued = 0
        for scrip in sorted(waiting)[:max_companies]:
            if time.monotonic() >= deadline:
                break
            since = max(waiting[scrip] or earliest, earliest)   # "" = out since before the backfill's start
            try:
                ids = self.retriage_company(scrip, date.fromisoformat(since), today, returning=True)
            except Exception as exc:  # noqa: BLE001 - one company's lookup must not fail the run; tried again next run
                log.warning("re-entry retriage %s failed: %s", scrip, exc)
                continue
            queued += len(ids)
            log.info("%s back in the universe (out since %s): %d set-aside filings queued", scrip, since, len(ids))
            del waiting[scrip]
        self._kv_set(universe.RETURNING_KEY, json.dumps(waiting))
        return queued

    def retriage_company(self, scrip: str, day_from: date, day_to: date, returning: bool = False) -> list[str]:
        """Apply today's rules to one company's filings that an earlier rule left in the noise file.

        Discovery skips a filing already in its day's noise file, so narrowing a drop or date rule never reached
        the filings it had dropped (the "AGM notice" rule took 12 annual reports filed with their notice, F57).
        The rows are fetched again from BSE, for the subject and symbol the noise row does not keep; each one
        today's rules no longer drop leaves the noise file and is queued. ``returning``: the company is back in the
        universe, so its rows set aside as outside it are freed too. Returns their news ids."""
        queued: list[str] = []
        start = day_from
        while start <= day_to:
            end = min(day_to, start + timedelta(days=30))
            by_day: dict[str, list[Filing]] = {}
            for filing in self._company_announcements(scrip, start, end):
                by_day.setdefault(filing.filing_date, []).append(filing)
            for key, filings in sorted(by_day.items()):
                noise = self._load_noise(key)
                freed = [f for f in filings if f.news_id in noise
                         and not _still_noise(self.rules.classify(f), f, noise[f.news_id], returning)]
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

    def _attachment(self, url: str, max_bytes: int, document: bool = False) -> bytes | None:
        """A filing's attachment from whichever exchange serves it. A file over the cap raises AttachmentTooLarge for
        the filing's own document (it fails once, with that reason, and is not retried); any other file is None."""
        try:
            if self.nse is not None and "nseindia.com" in url:
                return self.nse.fetch(url, max_bytes=max_bytes)
            return self.bse.download(url, max_bytes=max_bytes)
        except AttachmentTooLarge:
            if document:
                raise
            return None

    def _record(self, key: str, filings, noise: dict[str, list], known: set[str],
                sources: dict[str, str | None] | None = None) -> int:
        """Triage new filings of one day: noise to the day's R2 file, the rest to the ledger queue.

        A filing already known is skipped and costs no write, unless the ledger holds it (``sources``: news id ->
        stored attachment) and the exchange now serves another file under it: then it is sent again and
        filings_discover.sql queues it to be read again. Assumption, not measured: an exchange may replace an
        announcement's attachment under the same id; a revision filed as a new announcement is a new filing."""
        now = now_iso()
        today = today_ist().isoformat()
        noise_before = len(noise)
        ledger, catalysts, companies = [], [], {}
        changed, added = [], []
        for filing in filings:
            if filing.news_id in known:
                if sources and filing.news_id in sources and not sources[filing.news_id] and filing.pdf_url:
                    # listed first without a file, which NSE added later: read again with it (owner, 25 Oct 2026; its
                    # card, if any, came from the title alone)
                    sources[filing.news_id] = filing.pdf_url
                    filing.status = "PENDING"
                    added.append(filing.ledger_row(now))
                    continue
                if sources and filing.news_id in sources and _attachment_changed(sources[filing.news_id], filing.pdf_url):
                    sources[filing.news_id] = filing.pdf_url   # once per run, however often the day is read
                    filing.status = "PENDING"
                    changed.append(filing.ledger_row(now))
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
        if added:
            self.stats.attachment_changed += len(added)
            self._exec("filings_discover", added)
            log.info("discovered %s: %d known filings whose file NSE added later, queued again", key, len(added))
        if changed:
            self.stats.attachment_changed += len(changed)
            # counted only until a day's count shows NSE does not vary an unchanged filing's link (a systematic
            # difference would queue a whole day's filings again): ATTACHMENT_REQUEUE=1 turns the re-read on
            if os.environ.get("ATTACHMENT_REQUEUE") == "1":
                self._exec("filings_discover", changed)
                log.info("discovered %s: %d known filings with another attachment, queued again", key, len(changed))
            else:
                log.info("discovered %s: %d known filings with another attachment (counted, not queued)", key, len(changed))
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
        while not self._stop_starting(deadline) and not self._halted(bulk):
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
        finished = ({o.update["news_id"] for o in results} >= {f.news_id for f in history}
                    and all(o.update.get("status") in DONE for o in results))  # results may hold superseded filings (D20)
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
            if self._stop_starting(deadline) or self._halted(bulk) or self._blocked:
                break
            with self._lock:
                if filing.news_id in self._tried:  # one attempt per filing per run
                    continue
                self._tried.add(filing.news_id)
            outcome = self._process_one(filing, bulk, memory_complete, deadline)
            results += [outcome, *self._supersede(filing, outcome)]  # committed together: never a quarter with no card
            unsaved = [o for o in results if not o.committed]
            if len(unsaved) >= COMMIT_EVERY:
                self._commit(unsaved)
                for o in unsaved:
                    o.committed = True
        return results

    def _stop_starting(self, deadline: float) -> bool:
        """No new filing (or batch, or history day) is started past the deadline or the current slice's end. A filing
        already started keeps the run's deadline for its own retries and pack waits: before 27 Oct 2026 evening the slice
        end was passed down as the deadline, so in the last minute of every slice a busy provider was not waited for
        and the deferral counted toward BUSY_STOP."""
        return time.monotonic() >= min(deadline, self._slice_end or deadline)

    def _halted(self, bulk: bool) -> bool:
        """The analyst route for this phase has hit its quota ceilings, or the nightly memory jobs paused the AI
        pipeline (pause.py): work stays queued."""
        return self._busy_halt or ("pass2_bulk" if bulk else "pass2") in self._exhausted or self._pause_now()

    def _pause_now(self) -> bool:
        """The nightly pause, looked up at most once a minute (one kv read)."""
        from . import pause

        with self._lock:
            if self._paused or time.monotonic() - self._pause_checked < PAUSE_CHECK_S:
                return self._paused
            self._pause_checked = time.monotonic()
        try:
            until = pause.paused_until(self.sink)
        except Exception:  # noqa: BLE001 - a failed look is no pause
            return False
        if until:
            with self._lock:
                self._paused = True
                self.stats.stopped_reason = self.stats.stopped_reason or \
                    f"paused for the nightly memory jobs until {until:%H:%M} IST; work stays queued"
        return bool(until)

    def _process_one(self, filing: Filing, bulk: bool, memory_complete: bool, deadline: float | None = None) -> Outcome:
        began = time.monotonic()
        stages.start()
        try:
            outcome = self._attempt(filing, bulk, memory_complete, deadline)
        finally:
            _log_timing(filing, time.monotonic() - began, stages.finish(), locals().get("outcome"))
        status = outcome.update.get("status")
        held = bool(outcome.card and outcome.card.get("held"))
        if held:
            with self._lock:
                self._held_this_run.add(filing.news_id)
        elif status == "ANALYZED" and outcome.card:
            with self._lock:
                self._shown_this_run.add(filing.news_id)
        if status != "ANALYZED" or held:
            # a held card is no more the quarter's card in this run than in memory (_same_results_quarter)
            self._release_claims(filing.news_id, status)
        # Only a verdict that the filing has no card of its own; the XBRL shareholding path and the timeline tier
        # write memory and report NOT_MATERIAL too.
        if status in ("NOT_MATERIAL", "DUPLICATE") and str(outcome.update.get("reason", "")).startswith(
                ("pass1:", "pass2:", "duplicate of")):
            self._forget_in_memory(filing)
        return outcome

    def _forget_pending(self, scrip: str, news_ids) -> bool:
        """The same filings taken out of memory still waiting for its card rows (_pending_memory)."""
        changed = False
        with self._lock:
            for _, merged, _ in self._pending_memory.get(scrip, []):
                changed = any([forget_filing(merged, n) for n in news_ids]) or changed
        return changed

    def _forget_in_memory(self, filing: Filing) -> None:
        """What an earlier analysis of this filing put in memory, taken out now that it ends without a card."""
        self._forget_pending(filing.scrip_code, (filing.news_id,))
        try:
            with stages.stage("sink_read"):
                dossier = self.sink.get_dossier(filing.scrip_code)
            if dossier and forget_filing(dossier, filing.news_id):
                with stages.stage("memory_write"):
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
                for scrip, files in self._files.items():
                    self._files[scrip] = [f for f in files if f[1] != news_id]

    def _attempt(self, filing: Filing, bulk: bool, memory_complete: bool, deadline: float | None = None) -> Outcome:
        pass1 = "pass1_bulk" if bulk else "pass1"
        if filing.route == "PASS1" and pass1 in self._exhausted:
            return self._deferred(filing, "deferred: AI quota ceilings")
        for attempt in range(TRANSIENT_RETRIES + 1):
            try:
                lifted = _cap_deferrals(filing.last_error) >= MAX_CAP_DEFERRALS
                if lifted and attempt == 0:
                    log.info("cap lifted for %s after %d deferrals", filing.news_id, MAX_CAP_DEFERRALS)
                # the filing's card-writing cap starts at its pass 2 and ends here; lifted: no cap at all
                with self.gateway.card_scope(capped=not lifted):
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
                    isolated = self._unreachable == 1   # the filing before it was written: the site is up
                    if self._unreachable >= MAX_UNREACHABLE and not self._blocked:
                        self._blocked = SourceBlockedError(
                            f"the platform API did not answer for {self._unreachable} filings in a row; "
                            f"stopping this run with the work still queued. Is the web server running? ({exc})")
                        self.stats.stopped_reason = str(self._blocked)[:300]
                        log.error("stopping: %s", self._blocked)
                # A filing whose own write fails run after run while the site answers others (a memory too large to
                # write in time) would spend its AI calls every 15 minutes for ever: after MAX_DEFERRALS such runs it
                # spends an attempt (survey review, 24 Oct 2026). A site that is down spends none.
                times = _deferrals(filing.last_error) + 1
                if isolated and times > MAX_DEFERRALS:
                    return self._failed(filing, exc)
                return self._deferred(filing, f"deferred {times}x: the platform did not answer ({exc})"[:300])
            except AllProvidersFailed as exc:
                if exc.capped:
                    # The filing used its card-writing time (F149). Defer now: no 60 s waits, no attempt spent. After
                    # MAX_CAP_DEFERRALS such runs the cap is lifted for it (see `lifted` above), so a card is delayed
                    # at most three runs and never lost to the cap.
                    times = _cap_deferrals(filing.last_error) + 1
                    return self._deferred(filing, f"deferred {times}x: card-writing cap reached ({exc.capped_s:.0f} s)")
                if exc.quota_exhausted:
                    with self._lock:
                        self._exhausted.add(exc.route)
                        self.stats.stopped_reason = f"AI quota ceilings reached ({exc.route}); work stays queued"
                    log.warning("quota ceilings reached on %s; leaving %s queued: %s", exc.route, filing.news_id, exc)
                    return self._deferred(filing, "deferred: AI quota ceilings")
                waited_out = deadline is not None and time.monotonic() + TRANSIENT_WAIT_S >= deadline
                if exc.transient and attempt < TRANSIENT_RETRIES and not waited_out:
                    log.info("all providers busy for %s; waiting %ds", filing.news_id, TRANSIENT_WAIT_S)
                    with stages.stage("retry_wait"):
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
                # A spare writer failed while the better ones were at their day or kept for live filings: the failure
                # is the morning's quota, not the filing (21 Oct: 12 filings a run spent an attempt this way before
                # Gemini's 12:30 IST reset). It waits for them a few runs before it spends an attempt.
                times = _deferrals(filing.last_error) + 1
                kinds = {kind for _, kind, _ in exc.outcomes}
                if CEILING in kinds and times <= MAX_QUOTA_DEFERRALS:
                    return self._deferred(filing, f"deferred {times}x: the better writers are at their day ({exc})"[:300])
                # a writer busy or rate-limited beside one that failed: the capacity, not the filing (gemma 429s, Z.AI's
                # concurrency limit; 25 Oct 2026 report)
                if TRANSIENT in kinds and times <= MAX_QUOTA_DEFERRALS:
                    return self._deferred(filing, f"deferred {times}x: AI busy ({exc})"[:300])
                return self._failed(filing, exc)
            except EventXbrlPending as exc:
                return self._deferred(filing, f"deferred: {exc}")
            except (AttachmentTooLarge, NoTextAttachment) as exc:
                # the same file stays too large, or without text, on every run: fail once with the reason
                return self._failed(filing, exc, final=True)
            except AttachmentNotYet as exc:
                return self._deferred(filing, f"deferred: {exc}"[:300])
            except nse_api.FileCapReached as exc:
                # the run's file cap (F213, owner rule 100 files a run): stop the run, leave this filing and the rest
                # queued; no attempt is spent and nothing is marked failed. The next run goes on.
                with self._lock:
                    if not self._blocked:
                        self._blocked = exc
                        self.stats.stopped_reason = "file cap reached: the rest waits for the next run"
                        log.warning("stopping: %s", exc)
                # an earlier "deferred Nx: ..." note keeps its count and reason (_deferrals, _cap_deferrals read them)
                return self._deferred(filing, filing.last_error if _DEFERRED.match(filing.last_error or "")
                                      else "deferred: file cap reached")
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
                return self._failed(filing, exc, where=_crash_site(exc))
        return self._failed(filing, RuntimeError("retries exhausted"))

    def _deferred(self, filing: Filing, reason: str) -> Outcome:
        with self._lock:
            self.stats.deferred += 1
        log.info("deferred %s: %s", filing.news_id, reason)
        return Outcome({"news_id": filing.news_id, "status": "PENDING", "updated_at": now_iso(), "last_error": reason})

    def _failed(self, filing: Filing, exc: Exception, final: bool = False, where: str = "") -> Outcome:
        with self._lock:
            self.stats.failed += 1
        # The attempt count is sent as a value, not an increment, so a retried write cannot count twice.
        attempts = max(filing.attempts + 1, self.settings.max_attempts) if final else filing.attempts + 1
        return Outcome({"news_id": filing.news_id, "status": "FAILED", "attempts": attempts,
                        "last_error": (f"{type(exc).__name__}: {exc}"[:440] + (f" [at {where}]" if where else ""))[:500],
                        "updated_at": now_iso()})

    def analyze(self, filing: Filing, bulk: bool = False, memory_complete: bool = True) -> Outcome:
        """Run Pass 1 (if needed), extraction, Pass 2, grounding, merge and signals for one filing."""
        with stages.stage("sink_read"):
            company = self.sink.company(filing.scrip_code) or {}
        if filing.route == "XBRL":
            return self._xbrl_memory(filing, company)
        industry = company.get("industry")
        ocr = _ocr_timed(page_reader(self.gateway.transcribe_image if self.gateway.has_route("vision") else None))
        ocr_cap = self.settings.max_ocr_pages
        if filing.event_type == "CONCALL_PRESENTATION" and local_ocr_available():
            # owner 26 Oct 2026: a scanned call transcript or deck is read whole (up to CALL_OCR_PAGES), so memory sees all
            # of it; the pages past the usual cap go to local OCR only, never the vision route (an AI call)
            ocr_cap, ocr = max(ocr_cap, CALL_OCR_PAGES), _call_ocr(ocr, recognise, ocr_cap)
        # Pages of figures are read by local OCR first, the text layer putting back the nils it drops
        # (extract.figure_page); never by the vision route, which costs quota and swaps digits.
        figures = _ocr_timed(recognise if local_ocr_available() else None)
        cached = self._cached_text(filing.news_id)
        doc = None
        # A page whose text layer is unreadable and was never OCR'd is read again from the PDF, once, so
        # it can be: the cache would otherwise hand the same garbage to the model on every re-run. So is
        # an entry written before figure pages went to local OCR.
        current = (cached is not None and cached.get("v", 1) >= CACHE_VERSION
                   and not cache_needs_ocr(cached, local_ocr=figures is not None,
                                       max_ocr_pages=ocr_cap if ocr else None)
                   and "blocks" in cached  # written before pages were also read block by block
                   # Nothing was read (too large at the cap then, or not there): there is no text to lose by
                   # asking again, and 519552's annual report, skipped at 30 MB, would stay empty for good.
                   and bool(cached.get("digital")))
        if cached is not None and (current or not filing.pdf_url):
            doc = Document.from_cache(cached, ocr=ocr, max_ocr_pages=ocr_cap)
        elif cached is not None:
            # Written before the text layer was read in reading order: read the PDF again, keeping the
            # pages already OCR'd; if BSE will not serve it now, the old text is still better than none.
            try:
                with stages.stage("download"):
                    pdf = self._attachment(filing.pdf_url, _attachment_cap(filing), document=True)
                self._refusals = self._network_failures = 0
                with stages.stage("read"):
                    doc = Document(pdf, ocr=ocr, max_ocr_pages=ocr_cap, figure_reader=figures)
                doc.keep_ocr(cached)
            except (AttachmentError, AttachmentTooLarge):
                doc = Document.from_cache(cached, ocr=ocr, max_ocr_pages=ocr_cap)
        if doc is None:
            with stages.stage("download"):
                pdf = self._attachment(filing.pdf_url, _attachment_cap(filing), document=True) if filing.pdf_url else None
            self._refusals = self._network_failures = 0
            if filing.pdf_url and not pdf:   # a 404, or an empty file (XTRANET's of 23 Oct is still 0 bytes)
                _attachment_missing(filing)
            # before any page is read (OCR is lazy, 70-129 s on three filings that then ended as repeats)
            same = self._same_file(filing, pdf) if pdf else None
            if same:
                with self._lock:
                    self.stats.duplicates += 1
                return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": filing.event_type,
                                "reason": f"duplicate of {same} (same file)", "updated_at": now_iso()})
            with stages.stage("read"):
                doc = Document(pdf, ocr=ocr, max_ocr_pages=ocr_cap, figure_reader=figures)
        try:
            repeat = self._duplicate_of(filing, doc)
            if repeat:
                with self._lock:
                    self.stats.duplicates += 1
                return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": filing.event_type,
                                "reason": f"duplicate of {repeat[0]} ({repeat[1]} match)", "updated_at": now_iso()})
            why = None
            if filing.route != "TIMELINE":
                first = doc.select_text(6000, [])   # the first pages: an amount often sits on the order's second page
                profit = annual_profit_cr(self._memory(filing.scrip_code)) if _FINE.search(first) else None
                why = memory_only(filing, first, doc.page_count, profit)
            if why:
                log.info("%s: %s, a timeline line and no card", filing.news_id, why)
                filing = filing.model_copy(update={"route": "TIMELINE"})
            if filing.route == "TIMELINE":
                return self._timeline_flow(filing, company, industry, doc, bulk, memory_complete)
            return self._analyze_document(filing, company, industry, doc, bulk, memory_complete)
        finally:
            with self._lock:
                self.stats.ocr_pages += doc.ocr_pages_used + doc.figure_pages_used
            if doc.ocr_error is None:
                self._cache_text(filing.news_id, doc)
            doc.close()

    @stages.timed("dup_check")
    def _same_file(self, filing: Filing, pdf: bytes) -> str | None:
        """The news id of another filing by the same company, within duplicates.DAYS either side, whose downloaded file
        has exactly these bytes (sha256); None when there is none. Checked before the pages are read, so a repeat costs
        no OCR. Only identical bytes count: a repeat in other words is _duplicate_of's. Only OTHER news ids are compared,
        so a filing read again on purpose (a requeue, the re-read when its PDF arrives) never repeats itself. Like
        _duplicate_of: this run's filings are registered at once (parallel workers), earlier runs' only once finished
        (the text cache keeps each file's hash), and a correction is never a repeat."""
        if len(pdf) < SAME_FILE_MIN_BYTES:
            return None
        digest = hashlib.sha256(pdf).hexdigest()
        filed = datetime.fromisoformat(filing.filed_at)
        since = (filed - timedelta(days=duplicates.DAYS)).isoformat()
        until = (filed + timedelta(days=duplicates.DAYS)).isoformat()
        with self._lock:
            seen = list(self._files.get(filing.scrip_code, []))
            self._files.setdefault(filing.scrip_code, []).append((filing.filed_at, filing.news_id, digest))
        if duplicates.is_correction(filing.headline, filing.subject):
            return None
        for at, news_id, theirs in seen:
            if theirs == digest and news_id != filing.news_id and since <= at < until:
                log.info("%s is the same file as %s (same company, sha256)", filing.news_id, news_id)
                return news_id
        known = {n for _, n, _ in seen}
        for row in self.sink.query("filings_recent_company", [filing.scrip_code, since, until, 40]):
            if row["news_id"] in known or row["news_id"] == filing.news_id:
                continue
            cached = self._cached_text(row["news_id"])
            if cached is not None and cached.get("sha256") == digest:
                log.info("%s is the same file as %s (same company, sha256)", filing.news_id, row["news_id"])
                return row["news_id"]
        return None

    @stages.timed("dup_check")
    def _duplicate_of(self, filing: Filing, doc: Document) -> tuple[str, str] | None:
        """(news_id, "exact" | "near") of another filing by the same company, within duplicates.DAYS either side,
        that this one repeats (see duplicates.py); None when there is none. A later filing counts once it is done:
        NSE can list the original after its repeat, or a failed original is retried after the repeat got its card
        (Panache's results, 23 Oct 2026, filed twice six minutes apart, two cards). Filings of this run are
        registered before they are analysed, so parallel workers cannot both analyse one event. Corrections are
        never duplicates."""
        if duplicates.is_correction(filing.headline, filing.subject):
            return None
        mine = duplicates.body(doc.select_text(duplicates.CHARS, figures=False))
        if not mine.matchable:
            return None
        filed = datetime.fromisoformat(filing.filed_at)
        since = (filed - timedelta(days=duplicates.DAYS)).isoformat()
        until = (filed + timedelta(days=duplicates.DAYS)).isoformat()
        with self._lock:
            seen = list(self._bodies.get(filing.scrip_code, []))
            self._bodies.setdefault(filing.scrip_code, []).append((filing.filed_at, filing.news_id, mine))
        candidates = [(n, b) for at, n, b in seen if since <= at < until and n != filing.news_id]
        known = {n for _, n, _ in seen}
        for row in self.sink.query("filings_recent_company", [filing.scrip_code, since, until, 40]):
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

    @stages.timed("xbrl")
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
        link = self._results_xbrl_link(filing, text)
        return link.url if link else None

    def _results_xbrl_link(self, filing: Filing, text: str):
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
            return max(timely, key=lambda link: link.filed_at)
        # never a quarter that ended more than RESULTS_QUARTER_DAYS before the PDF, nor after it: QUESS's Q2FY27 card of 30 Oct 2026
        # (nse-106837502) took its Q1FY27 file of 29 Jul (a quarter ended 122 days before), so the whole card, table and headline,
        # was the earlier quarter's (blind check of the fact-sheet cards, 31 Oct). A same-quarter file filed weeks before a
        # re-filed or corrected PDF is still taken (review of the first fix).
        from .memory_gaps import quarter_end

        def plausible(link) -> bool:
            end = quarter_end(link.period) if link.period else None
            return end is None or 0 <= (day - end).days <= RESULTS_QUARTER_DAYS
        links = [link for link in links if plausible(link)]
        return min(links, key=lambda link: link.filed_at) if links else None

    @stages.timed("xbrl")
    def _standalone_file(self, filing: Filing, tagged):
        """The standalone results file for the consolidated file's quarter, parsed; None when NSE lists none or it
        cannot be read (best effort: the card goes on without it)."""
        links = [link for link in self._results_links(filing)
                 if link.period == tagged.period and link.basis == "STANDALONE"]
        if not links:
            return None
        link = max(links, key=lambda link: link.filed_at)
        try:
            data = xbrl_store.get(self.sink, link.url)   # our copy first, a download kept like the consolidated file (F191)
            if not data:
                with stages.stage("xbrl"):
                    data = self._attachment(link.url, 8_000_000)
                xbrl_store.put(self.sink, link.url, data)
                xbrl_facts.keep(self.sink, data, filing.scrip_code, link.url)
            result = xbrl_fast_path.parse(data, filing.news_id)
            if result is not None and result.kind == "RESULTS":
                result.raw, result.url = data, link.url   # its screener-rule statements, for the company page's standalone view
            return result
        except nse_api.FileCapReached:
            raise   # the run's file cap (F213): the filing waits for the next run, not a card without its extra
        except Exception as exc:  # an extra: the consolidated card stands without it
            log.warning("standalone results file for %s unavailable (%s)", filing.news_id, exc)
            return None

    def _standalone_bank_ratios(self, filing: Filing, tagged, standalone=None) -> None:
        """A bank's consolidated file carries no gross NPA, net NPA or RoA (0 fillers, T2 2026-10-20): the same
        quarter's standalone file gives them. Best effort: the card goes on without them if it cannot be read."""
        standalone = standalone or self._standalone_file(filing, tagged)
        if standalone is not None:
            xbrl_fast_path.add_bank_ratios(tagged, standalone)

    def _timeline_flow(self, filing: Filing, company: dict, industry, doc: Document, bulk: bool, memory_complete: bool) -> Outcome:
        """A routine filing (dividend recommendation, voting result, a nil pledge declaration) gets one dated line in
        the company's timeline and no card (D22). A cheap model writes the line and asks for a full card when the
        filing is consequential; the same event filed again is recorded once."""
        now = now_iso()
        first = doc.select_text(6000, [])
        _ocr_check(doc)
        system, user = self.prompts.timeline(filing, first)
        with stages.stage("pass1"):
            verdict: TimelineVerdict = self.gateway.complete_json("pass1_bulk" if bulk else "pass1", system, user, TimelineVerdict).value
        if verdict.needs_card or not verdict.entry.strip():
            filing = filing.model_copy(update={"route": "FAST_TRACK", "event_type": verdict.event_type if verdict.event_type != "OTHER" else filing.event_type})
            return self._analyze_document(filing, company, industry, doc, bulk, memory_complete)
        event_type = verdict.event_type if verdict.event_type != "OTHER" else (filing.event_type or "OTHER")
        with stages.stage("sink_read"):
            dossier = self.sink.get_dossier(filing.scrip_code) or new_dossier(filing, company)
        repeat = similar_timeline_entry(dossier, filing, verdict.entry)
        if repeat:
            with self._lock:
                self.stats.duplicates += 1
            return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": event_type,
                            "reason": f"duplicate of {repeat['news_id']} (same timeline event)", "updated_at": now})
        merged = add_timeline_entry(dossier, filing, event_type, verdict.entry, now)
        with stages.stage("memory_write"):
            self.sink.put_dossier(filing.scrip_code, merged)
        with self._lock:
            self.stats.timeline_only += 1
        return Outcome({"news_id": filing.news_id, "status": "NOT_MATERIAL", "event_type": event_type,
                        "reason": f"timeline only: {verdict.entry}"[:300], "updated_at": now},
                       company={"scrip_code": filing.scrip_code, "company_name": filing.company_name,
                                "updated_at": now, **_company_memory(merged)})

    def _held_reasons(self, filing: Filing, text: str, xbrl_backed: bool = False) -> list[str]:
        """Reasons the card is published as unverified that no second model can fix: a scan whose text layer
        is garbled (its table figures may be wrong) unless the card's figures are its XBRL file's, and the human hold
        list (config/card_holds.txt)."""
        held = []
        if gate.text_is_garbled(text) and not xbrl_backed:
            held.append("The filing's text layer is garbled (scan errors inside numbers): figures from its tables may be wrong")
        if filing.news_id in self._holds:
            held.append(f"Held after review: {self._holds[filing.news_id]}")
        return held

    def _same_results_quarter(self, filing: Filing, dossier: dict, quarter: str | None,
                              basis: str | None = None, claim: bool = True) -> tuple[str, str] | None:
        """(news_id, quarter) of the results filing that already has this company's card for the quarter
        (decision D20: one card per company per results quarter; the others are linked to it). Novartis
        filed one quarter's results as three documents, Ahluwalia as a board outcome and a later meeting
        update. From memory (a RESULTS timeline entry whose filing reported the quarter's figures) and
        from this run's own claims, so parallel workers cannot both take the quarter."""
        if not quarter or quarter_index(quarter) is None:
            return None
        key = (filing.scrip_code, quarter)
        dates = {t["news_id"]: t.get("date", "") for t in dossier.get("timeline", [])
                 if t.get("event_type") == "RESULTS" and t.get("news_id") != filing.news_id}
        metrics = dossier.get("financial_metrics", [])
        # the quarter a results card's own timeline entry names (TODO 133): it finds the card when memory holds none of its
        # figures (MEMORY_FILE_ONLY keeps a PDF-only card's figures on the card)
        named = {t["news_id"]: t.get("quarter") for t in dossier.get("timeline", [])
                 if t.get("event_type") == "RESULTS" and t.get("news_id") in dates and t.get("quarter")}
        # a card that names its own quarter owns that one alone, never the comparatives its figures cover (blind review)
        owners = list(dict.fromkeys([n for m in metrics if m.get("period") == quarter for n in dates if reported_by(m, n)
                                     and named.get(n, quarter) == quarter]
                                    + [n for n, q in named.items() if q == quarter]))
        # A results filing filed after this one also reports this quarter as its comparative: it owns the quarter only
        # when it is its own latest quarter, the quarter of its results (Sunteck's Q1FY27 filings report Q4FY26 too).
        later = [n for n in owners if dates[n] >= filing.filed_at
                 and (named.get(n) == quarter if named.get(n) else
                      max((quarter_index(m["period"]) or -1 for m in metrics if reported_by(m, n)), default=-1)
                      == quarter_index(quarter))]
        owners = [n for n in owners if dates[n] < filing.filed_at]
        # An owner whose card is held out of the feed is not the quarter's card: another document of the quarter
        # may make the one that is published. 17 of the 43 quarters with D20 duplicates had their only card held
        # while the statement itself was marked a duplicate of it (funnel, 2026-10-18).
        owners = [n for n in owners if not self._card_held(n)]
        later = [n for n in later if not self._card_held(n)]
        # Consolidated first (owner, 30 Oct 2026: "if consolidated results available, use it only, if not available, use
        # standalone"): a consolidated file of the quarter takes it from a standalone-only card filed before it, which
        # becomes its duplicate once this card is published (_supersede); a standalone file never takes it from either
        named_basis = {t["news_id"]: t.get("basis") for t in dossier.get("timeline", []) if t.get("news_id") in dates}
        standalone_owners = [n for n in owners if basis == "CONSOLIDATED" and (_standalone_only(metrics, quarter, n)
                                                                             or named_basis.get(n) == "STANDALONE")]
        with self._lock:
            claimed = self._results_quarters.get(key)
            if claimed and claimed != filing.news_id:
                if not (basis == "CONSOLIDATED" and self._results_quarter_basis.get(key) == "STANDALONE"):
                    return claimed, quarter
                standalone_owners.append(claimed)
            if owners and set(owners) - set(standalone_owners):
                return owners[0], quarter
            if not claim:
                return None   # only looking for an earlier card (D20_DROPPED_FILE_PERIOD): never takes the quarter
            self._results_quarters[key] = filing.news_id
            self._results_quarter_basis[key] = basis
            if standalone_owners:
                self._superseding[filing.news_id] = (list(dict.fromkeys(standalone_owners + later)), quarter)
                return None
            if later:
                # A later document of the quarter got the card first: this one was retried after a failure or requeued
                # by id once the later one had its card, and both stayed on the feed (Sunteck Q1FY27: the statement
                # re-run after the press release; Sun Pharma Q4FY26: one outcome filed twice; 2026-10-20). The earlier
                # filing - the statement, not the press release that follows it - takes the quarter, and the later
                # one becomes its duplicate once this card is published (_supersede).
                self._superseding[filing.news_id] = (later, quarter)
        return None

    def _fold_release(self, filing: Filing, results_id: str, text: str, tagged, doc) -> bool:
        """RESULTS_PRESS_RELEASE (TODO 135): a press or investor release of a quarter whose results card exists is no second card,
        but its words are not lost: the text waits here for the card's re-run (event_catchup.release_catch_up adds it to that
        card's text) and the release is queued for call memory, which reads it like a deck. False (nothing kept, today's
        duplicate) with the switch off, for a filing that is not a release, or for one that carries a statement or a file."""
        if not results_press_release() or tagged or not _PRESS_RELEASE.search(f"{filing.headline or ''} {filing.subject or ''}") \
                or _RESULTS_STATEMENT.search(text[:20000]) or not text.strip():
            return False
        release_fold.add(self.sink, results_id, {"news_id": filing.news_id, "date": str(filing.filing_date)[:10],
                                                 "text": text[:RELEASE_TEXT_CHARS]})
        log.info("%s is a results press release; its text joins the card of %s (TODO 135)", filing.news_id, results_id)
        self._call_memory_step(filing, None, {}, text, "")
        return True

    def _supersede(self, filing: Filing, outcome: Outcome) -> list[Outcome]:
        """The later documents of a results quarter that had its card, made duplicates of this earlier filing (D20).
        Only once this filing's card is published: a quarter never loses its only card to a failed or held one."""
        with self._lock:
            later, quarter = self._superseding.pop(filing.news_id, ((), ""))
        if not later or outcome.update.get("status") != "ANALYZED" or not outcome.card or outcome.card.get("held"):
            return []
        self._forget_pending(filing.scrip_code, later)
        dossier = self.sink.get_dossier(filing.scrip_code)
        if dossier and any([forget_filing(dossier, n) for n in later]):
            with stages.stage("memory_write"):
                self.sink.put_dossier(filing.scrip_code, dossier)
        log.info("%s takes results quarter %s from %s (D20)", filing.news_id, quarter, ", ".join(later))
        return [Outcome({"news_id": n, "status": "DUPLICATE", "event_type": "RESULTS",
                         "reason": f"duplicate of {filing.news_id} (same results quarter {quarter}, D20)",
                         "updated_at": now_iso()}) for n in later]

    @stages.timed("sink_read")
    def _card_shown(self, news_id: str) -> bool:
        """Whether a filing has a card in the feed: published this run, or a card row that is not held."""
        with self._lock:
            if news_id in self._shown_this_run:
                return True
            if news_id in self._held_this_run:
                return False
        rows = self.sink.query("card_held", [news_id]) or []
        return bool(rows) and not rows[0].get("held")

    @stages.timed("sink_read")
    def _card_held(self, news_id: str) -> bool:
        # this run's own verdict first: its card may not be committed yet, and a re-run deleted the old one
        with self._lock:
            if news_id in self._held_this_run:
                return True
        rows = self.sink.query("card_held", [news_id]) or []
        return bool(rows and rows[0].get("held"))

    @stages.timed("xbrl")
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
            url = max(same, key=lambda link: link.filed_at).url
            # an NSE file through NSE's client, with its pacing and refusal handling (deep audit A-07, 2026-10-21)
            data = self._xbrl_file(url, self.nse if self.nse is not None and "nseindia" in url else None)
            parsed = xbrl_fast_path.parse(data, filing.news_id) if data else None
            if parsed:
                xbrl_fast_path.fix_scale(parsed, [*history, *tagged.metrics], filing.scrip_code,
                                         verify=self._slip_check(filing))
                if parsed.slip_held:   # the comparative's unit is unconfirmed: no change is stated against it (F200)
                    self._note_slip_held(filing, parsed)
                    continue
                xbrl_fast_path.drop_long_year(parsed, [*history, *tagged.metrics], filing.scrip_code)
                earlier.append(parsed)
        if earlier:
            xbrl_fast_path.add_comparatives(tagged, *earlier)

    def _slip_check(self, filing: Filing, period: str | None = None, pdf_url: str | None = None):
        """The PDF text-layer check of a unit slip (slip_check.PdfCheck, F200); fetches nothing until a slip is found."""
        from .slip_check import PdfCheck
        return PdfCheck(self.nse, filing.symbol or "", pdf_url, period)

    def _note_slip_held(self, filing: Filing, tagged) -> None:
        """A detected unit slip the filing's PDF did not confirm: counted and listed for the run's summary (F200)."""
        with self._lock:
            self.stats.slip_held.append(f"{filing.news_id} {tagged.period}: {tagged.slip_held}")

    def _xbrl_file(self, url: str, client=None, max_bytes: int = 8_000_000) -> bytes | None:
        """An XBRL file by URL, cached under the text cache's xbrl folder (as seed.py keeps NSE's)."""
        root = self.settings.text_cache_dir
        path = root / "xbrl" / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".xml.gz") if root else None
        if path and path.exists():
            try:
                return gzip.decompress(path.read_bytes())
            except OSError:
                pass
        data = xbrl_store.get(self.sink, url)   # our copy in R2 (F191) before asking the exchange
        if data:
            self._xbrl_local_put(path, data)
            return data
        try:
            client = client or self.bse
            # an event XBRL file comes as a zip of the XML and its PDF on some rows (event_xbrl.xml_of)
            fetch = client.fetch if url.lower().endswith(".zip") and hasattr(client, "fetch") else client.download
            data = fetch(url, max_bytes=max_bytes)
        except (AttachmentError, AttachmentTooLarge):
            return None
        if data:
            self._xbrl_local_put(path, data)
            xbrl_store.put(self.sink, url, data)
        return data

    @staticmethod
    def _xbrl_local_put(path, data: bytes) -> None:
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(data))
        except OSError:
            pass

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

    @stages.timed("xbrl")
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
        except nse_api.FileCapReached:
            raise   # the run's file cap (F213): the filing waits for the next run, not a card read without its XBRL
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

    @stages.timed("xbrl")
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
        except nse_api.FileCapReached:
            raise   # the run's file cap (F213): the filing waits for the next run
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
            # our copy in R2 first, and a fresh download kept there (F191): the filing's own file was the one results XBRL
            # the live path fetched without keeping (audit of the live write path, 30 Oct 2026)
            data = xbrl_store.get(self.sink, filing.xbrl_url)
            if data and path:
                self._xbrl_local_put(path, data)
        if data is None:
            try:
                with stages.stage("xbrl"):
                    data = self._attachment(filing.xbrl_url, 8_000_000)   # NSE's archive for an NSE file
            except AttachmentError:
                if strict:
                    raise
                log.warning("XBRL download failed for %s; using the PDF", filing.news_id)
                return None
            if data:
                xbrl_store.put(self.sink, filing.xbrl_url, data)
                xbrl_facts.keep(self.sink, data, filing.scrip_code, filing.xbrl_url)   # even if the card sets the file aside
            if data and path:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(gzip.compress(data))
                except OSError:
                    pass
        result = xbrl_fast_path.parse(data, filing.news_id) if data else None
        if result:
            if result.kind == "RESULTS":
                result.raw = data   # for its screener-rule statements at the memory write; goes with the result, never kept
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
        merged = merge(dossier, out, filing, None, now, by="file")   # the shareholding file's own figures (memory label)
        with stages.stage("memory_write"):
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

    def _durable_text(self) -> bool:
        """True when texts also live in the platform's R2 (F147); local and laptop sinks keep the local cache alone."""
        return isinstance(getattr(self.sink, "read_through", self.sink), PlatformSink) and self.settings.text_cache_dir is not None

    def _cached_text(self, news_id: str) -> dict | None:
        path = self._cache_path(news_id)
        if not path:
            return None
        if path.exists():
            try:
                return json.loads(gzip.decompress(path.read_bytes()))
            except Exception:  # a damaged cache file is re-read from the source (and from R2 below)
                pass
        if not self._durable_text():
            return None
        # Not on this runner (the GitHub cache keeps 8 days): the durable copy in R2, kept 6 months (F147). A miss is
        # remembered for the run: the repeat checks look up to 40 recent filings a filing, most with no text at all.
        misses = self.__dict__.setdefault("_text_misses", set())
        if news_id in misses:
            return None
        try:
            body = self.sink.get_object(text_key(news_id))
            if not body:
                misses.add(news_id)
                return None
            entry = json.loads(gzip.decompress(body))
        except Exception as exc:  # R2 is the second layer: a miss or a failure re-reads the filing
            log.warning("durable text read failed for %s: %s", news_id, exc)
            return None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(body)
            tmp.replace(path)
        except OSError as exc:
            log.warning("text cache write failed for %s: %s", news_id, exc)
        return entry

    @stages.timed("card_write")
    def _save_evidence(self, filing: Filing, first, final, now: str) -> str | None:
        """The model's own reply for this card, in the object store under evidence/{news_id}.json.gz (R2 online, so
        no D1 row): a reviewer's WRONG can then be told apart as the model's reading or a code block without a re-run
        (ai-quality plan item 8). The writer's reply and, when a second provider's card was adopted, that one too,
        each cut to EVIDENCE_MAX_CHARS. A re-run replaces it. Saving never fails the filing."""
        key = evidence_key(filing.news_id)
        if not self.settings.save_evidence or not key:
            return None
        replies = [("writer", first)] + ([("second_opinion", final)] if final is not first else [])
        body = {"news_id": filing.news_id, "scrip_code": filing.scrip_code, "filed_at": filing.filed_at, "saved_at": now,
                "replies": [{"role": role, "model": r.model_label, "pack": r.pack, "latency_s": r.latency_s,
                             "chars": len(r.raw_text or ""), "raw": (r.raw_text or "")[:EVIDENCE_MAX_CHARS]}
                            for role, r in replies]}
        try:
            self.sink.put_object(key, gzip.compress(json.dumps(body, ensure_ascii=False).encode()),
                                 content_type="application/gzip")
            return key
        except Exception as exc:  # evidence is for audits; the card goes on without it
            log.warning("evidence not saved for %s: %s", filing.news_id, exc)
            return None

    @stages.timed("card_write")
    def _cache_text(self, news_id: str, doc: Document) -> None:
        path = self._cache_path(news_id)
        if not path:
            return
        body = text_cache_body(doc)
        try:
            unchanged = path.exists() and path.read_bytes() == body
        except OSError:
            unchanged = False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(body)
            tmp.replace(path)  # atomic: an interrupted run never leaves half a file
        except OSError as exc:
            log.warning("text cache write failed for %s: %s", news_id, exc)
        if unchanged or not self._durable_text():
            return
        try:
            self.sink.put_object(text_key(news_id), body, content_type="application/gzip")
        except Exception as exc:  # the durable copy is best effort: the filing goes on without it
            log.warning("durable text not saved for %s: %s", news_id, exc)

    def _analyze_document(self, filing, company, industry, doc: Document, bulk: bool, memory_complete: bool) -> Outcome:
        now = now_iso()
        event_type = filing.event_type or "OTHER"
        # Before any model call: a live filing waiting for its file stays queued at no cost (EventXbrlPending)
        events, events_checked = self._event_xbrl(filing, doc)
        # Before pass 1, not after it: the gatekeeper is shown what this company has already filed, so it
        # can name an event arriving again as a different document (the document rules cannot see those).
        dossier = self._memory(filing.scrip_code) or new_dossier(filing, company)
        read = json.loads(json.dumps(dossier))   # memory as read, for keep_concurrent_writes when it is written back
        if filing.route == "PASS1" and doc.page_count >= ANNUAL_REPORT_MIN_PAGES and doc.kind() == "ANNUAL_REPORT":
            # NSE's headline can name only the meeting ("Annual General Meeting ... to be held on ..."), with the annual
            # report inside: Max Financial's 389 pages, whose auditor flagged a pending SEBI show-cause notice, were
            # turned away by pass 1 as a routine AGM notice (round 5 recall review, 2026-10-19)
            log.info("%s is an annual report by its own pages (%d); the annual-report path, not pass 1", filing.news_id,
                     doc.page_count)
            filing = filing.model_copy(update={"route": "FAST_TRACK", "event_type": "ANNUAL_REPORT"})
            event_type = "ANNUAL_REPORT"
        if filing.route == "PASS1":
            # the route was set at discovery; a filing re-queued after a rule change takes today's rules (the noise
            # review of 2026-10-21 moved press releases, shareholder letters and monthly volumes past pass 1)
            now_rule = self.rules.classify(filing)
            if now_rule.action == "FAST_TRACK":
                filing = filing.model_copy(update={"route": "FAST_TRACK", "event_type": now_rule.event_type or filing.event_type})
                event_type = filing.event_type or "OTHER"
        if event_type == "RESULTS" and is_deck_or_transcript(filing):
            # an investor presentation or call transcript filed under a results heading is no results filing: Coal India's
            # deck (nse-106835008, 29 Oct 2026) took a second results card for H1FY27 beside the statement's, and its AI
            # figures went into memory as the quarter's. It is read as a deck: no D20 quarter, no results table
            log.info("%s is a deck or transcript filed as results; read as CONCALL_PRESENTATION", filing.news_id)
            filing = filing.model_copy(update={"event_type": "CONCALL_PRESENTATION"})
            event_type = "CONCALL_PRESENTATION"
        if filing.route == "PASS1":
            first_page = doc.first_page_text()
            _ocr_check(doc)
            recent = [t for t in dossier.get("timeline", []) if str(t.get("date", "")) < filing.filed_at][-8:]
            system, user = self.prompts.pass1(filing, first_page, recent)
            with stages.stage("pass1"):
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
        memory_only = self._memory_only(filing, bulk)
        if filing.route != "PASS1" and event_type in ONE_EVENT_ONE_CARD and not is_transcript(filing) and not memory_only:
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
        # A transcript or an annual report runs to 100-400 pages: the auditor's report and the notes need room
        budget = self.settings.pass2_char_budget * (3 if event_type in ("CONCALL_PRESENTATION", "ANNUAL_REPORT") else 1)
        # each page headed with its heading and its own unit (``headers``): LIC's GST notice mixed rupees and lakh, and a
        # Cyient segment slide's target was read as the company's (live reviews, 2026-10-20)
        text = doc.select_text(budget, self.prompts.keywords(event_type), headers=True)
        # The same pages read block by block, where a cell or a column stays whole: a quote of a two-column
        # page is the filing's own words if either reading has it (gate.quote_found).
        blocks = doc.block_text(doc.selected)
        _ocr_check(doc)
        if carries_results(event_type, text):
            # Settled here, not only after pass 2 (event_type_rules), so the results XBRL and D20 see it too: Kapston
            # filed its Q2FY27 outcome (results and a 5:1 split) twice, four minutes apart; the copy typed
            # CORPORATE_ACTION skipped the quarter's claim and its XBRL and became a second results card (O3, 2026-10-20)
            log.info("%s carries a results statement: %s -> RESULTS before pass 2", filing.news_id, event_type)
            event_type = "RESULTS"
        elif event_type == "RESULTS" and results_needs_statement() and lacks_results(doc.select_text(10_000_000, [])):
            # a note about the results is no results filing (RESULTS_NEEDS_STATEMENT, off until measured)
            log.info("%s is typed RESULTS but carries no results statement; read as OTHER", filing.news_id)
            filing = filing.model_copy(update={"event_type": "OTHER"})
            event_type = "OTHER"
        subsidiary = subsidiary_results(filing, text) if event_type == "RESULTS" else None
        other_issuer = None
        if event_type == "RESULTS" and not subsidiary and card_other_issuer():
            # another company's results, not called a subsidiary (HEGAM nse-106837190): the same path as a subsidiary's
            other_issuer = subsidiary = other_issuer_results(filing, text, (dossier.get("identity") or {}).get("former_names"))
        if subsidiary:
            # its figures are another company's: no results path (XBRL, table, quarter claim) and none into memory
            log.info("%s passes on %s's results: an update, not the company's own results", filing.news_id, subsidiary)
            event_type = "OTHER"
        if event_type == "RESULTS" and not filing.xbrl_url:
            link = self._results_xbrl_link(filing, text)
            filing = filing.model_copy(update={"xbrl_url": link.url if link else None})
            # The statement carries consolidated results but NSE lists only the standalone file so far: wait for the
            # consolidated one, as for a missing file. A card on the standalone file mixed the two bases on 13 of 52
            # results cards (owner, 2026-10-21: "not using consolidated numbers where those are there")
            standalone_only = bool(link and link.basis == "STANDALONE" and CONSOLIDATED_STATEMENT.search(text))
            if (not filing.xbrl_url or standalone_only) and filing.news_id.startswith(nse_api.NEWS_ID_PREFIX) \
                    and self.nse is not None and not self._nse_refused:
                age = now_ist() - datetime.fromisoformat(filing.filed_at)
                if age < timedelta(minutes=RESULTS_XBRL_WAIT_MINUTES):
                    # NSE's integrated-filing XBRL followed the outcome by 5 min to 2 h 40 min (measured 2026-10-18)
                    with self._lock:
                        self._xbrl_links.pop(filing.scrip_code, None)   # read the list afresh next time
                    what = "its consolidated results XBRL" if standalone_only else "its results XBRL"
                    raise EventXbrlPending(f"waiting for {what} ({age.total_seconds() / 60:.0f} min after the PDF)")
        tagged = self._xbrl(filing) if event_type == "RESULTS" else None
        dropped_period = None   # the quarter of a results file set aside below (its figures are not in the text): D20 only
        # the same quarter's standalone file beside a consolidated one: its figures are what a mixed card copies
        standalone_file = self._standalone_file(filing, tagged) if tagged and tagged.basis == "CONSOLIDATED" else None
        if xbrl_fast_path.needs_standalone_bank_ratios(tagged):
            self._standalone_bank_ratios(filing, tagged, standalone_file)
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
                    dropped_period = tagged.period
                tagged = None
        events_table = event_xbrl.table(events)
        if not text.strip() and not tagged and not events:
            if filing.pdf_url:
                # The attachment is there but nothing could be read from it (corrupt or password-protected; a 404,
                # a file over the cap and a ZIP with no PDF are told apart before this): a card from the headline
                # alone cannot be checked against anything. Failed, so a later run tries the file again.
                if doc.error and doc.error.startswith(("audio only", "a ZIP with no PDF")):
                    raise NoTextAttachment(doc.error)
                if doc.error and doc.error.startswith("cut short"):
                    _attachment_missing(filing, f"cut short on NSE ({doc.error[11:]})")
                raise RuntimeError(f"no readable text in the attachment ({doc.error or 'empty'})")
            # No attachment by design - an exchange's clarification request is its headline and subject - so
            # those are the filing's own words, and what its quotes answer to.
            text = "\n".join(t for t in (filing.headline, filing.subject) if t)
        results_q = None   # the quarter this results filing is the card of (D20), named on its timeline entry (TODO 133)
        if event_type == "RESULTS" and self.settings.one_card_per_results_quarter:
            quarter = results_quarter(tagged, text, filing.filed_at)
            from_dropped = False
            if quarter is None and dropped_period and d20_dropped_file_period():
                # TMB nse-106836238: an ECL note typed RESULTS found the bank's Q2FY27 file by quarter, the file's figures were
                # not in the note so it was set aside, the note had no quarter and published as a second Q2FY27 results card.
                # The file's quarter still names the quarter it would claim; used only to find an earlier card of it.
                quarter, from_dropped = dropped_period, True
            if quarter is None and not tagged and not _RESULTS_STATEMENT.search(text[:20000]) and amounts(text) < FIGURE_PAGE_AMOUNTS:
                # no statement, no file, few figures: a press release or an update, never a new quarter's statement
                quarter = companion_quarter(filing, dossier)
            # a set-aside file's quarter only defers to an earlier card; it never takes the quarter from the real statement
            earlier = self._same_results_quarter(filing, dossier, quarter, basis=getattr(tagged, "basis", None),
                                                 claim=not from_dropped)
            # stamped only when the quarter is the file's or a statement's own, never a text guess (blind review)
            results_q = quarter if (tagged or _RESULTS_STATEMENT.search(text[:20000])) else None
            if earlier:
                with self._lock:
                    self.stats.duplicates += 1
                folded = self._fold_release(filing, earlier[0], text, tagged, doc)
                return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": "RESULTS",
                                "reason": (f"press release folded into the card of {earlier[0]} (same results quarter {earlier[1]}, D20)"
                                           if folded else f"duplicate of {earlier[0]} (same results quarter {earlier[1]}, D20)"),
                                "updated_at": now_iso()})
        filed_text = text  # the document alone, before the XBRL table goes in front of it
        if tagged:
            # A file tagged in the wrong unit, told by the company's quarters in memory (xbrl.fix_scale):
            # confirm() above accepts the figures at any unit, so it cannot.
            history = dossier.get("financial_metrics") or []
            # Two sources (F200): a slip is corrected only where the filing's own PDF text layer prints the corrected figure;
            # otherwise the file's figures are left out (no card figures, nothing for memory) and the filing is flagged.
            xbrl_fast_path.fix_scale(tagged, history, filing.news_id,
                                     verify=self._slip_check(filing, tagged.period, filing.pdf_url))
            if tagged.slip_held:
                self._note_slip_held(filing, tagged)
                tagged = None
        if tagged:
            xbrl_fast_path.drop_long_year(tagged, history, filing.news_id)   # an 18-month "year" dated as twelve
            xbrl_fast_path.settle_pbt(tagged, filed_text)
            self._xbrl_comparatives(filing, tagged, history)
            eps_adjust.adjust_result(tagged, dossier)   # EPS_SHARE_ADJUST (F153): EPS changes on one share count
            eps_adjust.base_check_result(tagged, dossier)   # EPS_BASE_CHECK (F208): a change the profit does not carry is not kept
            if card_yoy_restated():
                restated_pdf.apply_to_result(tagged, dossier)   # CARD_YOY_RESTATED (F202): YoY on the restated year-ago figure
            text = tagged.table(explicit_basis=card_consolidated_only()) + "\n\n" + text  # exact figures first; they also ground the card
        # An annual report's statements as the company tagged them, in crore and on a named basis, where the PDF
        # prints lakh or million with standalone and consolidated side by side (12 of 31 cards held, round 3d).
        # Its lines are the filing's own figures, so a card may quote them as it quotes the results table.
        annual, annual_checked = self._annual_report_xbrl(filing, company, doc) if event_type == "ANNUAL_REPORT" else ([], None)
        if annual:
            text = annual_xbrl.table(annual) + "\n\n" + text
        # The event's own structured filing: amounts, parties, dates and stage as exact fields (PLAN 18 part 3)
        if events_table:
            text = events_table + "\n\n" + text
        if event_type == "RESULTS":
            # kept until the card is re-made (event_catchup.release_catch_up then clears it)
            releases = release_fold.pending(self.sink).get(filing.news_id, []) if results_press_release() else []
            if releases:
                # RESULTS_PRESS_RELEASE: the company's release of this quarter, for its words only; the figures stay the file's
                text += ("\n\nCompany press release filed with these results (use it only for management commentary, one-offs, "
                         "segment notes, order wins and guidance; the results figures come from the exchange file above):\n"
                         + "\n\n".join(r["text"] for r in releases)[:release_fold.MAX_CHARS])
        # Memory as the model sees it: the periods this filing prints withheld (its own columns win, restated or not)
        # and the items that are probably this same event marked. Code reads memory's figures from `full_view`.
        printed = set()
        if event_type in ("RESULTS", "ANNUAL_REPORT") or (
                event_type == "CONCALL_PRESENTATION" and not is_transcript(filing)):   # a call prints no columns
            printed = printed_periods(filed_text, filing.filed_at) | {
                canonical_period(m.period) for m in (tagged.metrics if tagged else []) if m.period}
        # CARD_CONSOLIDATED_ONLY (F154): a consolidated filer's card is stated on the consolidated basis alone
        consolidated_only = bool(card_consolidated_only() and event_type == "RESULTS" and tagged and tagged.basis == "CONSOLIDATED")
        # METRIC_BUSINESS_LINE: the memory the model is given holds the filing's own line's operating figures (the headline names it)
        line_now = business_line.detect(f"{filing.headline} {filing.subject}", dossier) if business_line.enabled() else None
        full_view = view_as_of(dossier, filing.filed_at, line=line_now)
        view = view_as_of(dossier, filing.filed_at, printed=printed, filing_text=text, consolidated_only=consolidated_only,
                          line=line_now)
        sector_module = self.prompts.sector_for(industry)
        sector = sector_module.name
        peers = self._peers(sector, event_type, filing)
        learned = self._learning()
        reaction = learned["queue"].get(filing.news_id)
        # The proportions the model may use, computed here from memory as it stood before this filing.
        scale = scale_block(dossier_as_of(dossier, filing.filed_at, inclusive=False), company, text, declared_unit(text))
        if memory_only:
            return self._memory_flow(filing, company, industry, event_type, dossier, read, view, text, filed_text, tagged,
                                     standalone_file, scale, events, now, blocks)
        variant = prompt_variant(filing.news_id, bulk, self.settings.prompt_short_share)
        # The cost shares, margins, tax rate and cash conversion a results card may state, computed here (facts.py)
        before_filing = dossier_as_of(dossier, filing.filed_at, inclusive=False) or {}
        found_facts = (code_facts.results_facts(tagged, filed_text, before_filing.get("balance_sheet"))
                       + code_facts.guidance_facts(tagged, before_filing.get("guidance"))
                       + code_facts.capex_revisions(before_filing.get("deals"), filing.filed_at)) \
            if tagged and event_type == "RESULTS" and self.settings.results_facts else []
        if found_facts:
            # in front of the text, as the XBRL table is: the model reads them as the filing's own figures, and a
            # card line quoting one is found (results_card.build puts them on a rich card)
            text = code_facts.block(found_facts, "Consolidated" if consolidated_only else None) + "\n\n" + text
        # CARD_FACT_SHEET (off: nothing): the quarter's figures from the exchange file by screener's rules, as the card's results
        # figures; None (the card is made as before) when the file is not a corporate filer's results, or on any failure
        results_sheet = (fact_sheet.for_filing(dossier, getattr(tagged, "raw", None), filing.scrip_code, filing.xbrl_url or "",
                                               filing.news_id, filing.filed_at, now)
                       if card_fact_sheet() and event_type == "RESULTS" and tagged else None)
        if results_sheet:
            text = fact_sheet.block(results_sheet) + "\n\n" + text
        system, user = self.prompts.pass2(filing, event_type, industry, view, text, peers, scale=scale,
                                          examples=self._owner_examples(sector, event_type),
                                          lessons=[x["lesson"] for x in learned["lessons"].get(f"{sector}|{event_type}", [])][-3:],
                                          reaction=reaction, variant=variant,
                                          consolidated_only=consolidated_only or bool(
                                              card_consolidated_only() and event_type == "RESULTS" and not tagged))
        route, packer = self._pass2_writer(bulk, len(system) + len(user))
        with stages.stage("pass2"):
            if packer is not None:
                result = packer.complete(route, system, user, Pass2Output, filing.news_id)   # several filings, one Gemini call
            else:
                self.gateway.start_cap()   # one filing's card-writing time starts here (packed filings: after the pack)
                result = self.gateway.complete_json(route, system, user, Pass2Output, bulk=bulk)
        out: Pass2Output = result.value
        if not out.is_material or out.card is None:
            with self._lock:
                self.stats.not_material += 1
            return Outcome({"news_id": filing.news_id, "status": "NOT_MATERIAL", "event_type": out.event_type,
                            "reason": f"pass2: not material{': ' + out.reason if out.reason else ''}"[:300],
                            "updated_at": now})
        if out.event_type in (*ONE_EVENT_ONE_CARD, *REPEAT_BY_WORDS) and out.timeline_entry and not is_transcript(filing):
            repeat = similar_timeline_entry(dossier, filing, out.timeline_entry)
            if repeat:  # the same event filed again in other words (BSE takes one submission per subcategory)
                with self._lock:
                    self.stats.duplicates += 1
                return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": out.event_type,
                                "reason": f"duplicate of {repeat['news_id']} (same event, in other words)", "updated_at": now})
        known = repeated_order(dossier.get("deals", []), out.card.deal_value, filing.filed_at, filing.news_id) \
            if out.event_type == "ORDER_WIN" else None
        if known and self._card_shown(str(known.get("repeats") or "")):
            # the same order at the same stage, told again (a press release beside its intimation); when the first
            # filing has no card in the feed (MCLOUD's ₹7.64 Cr LOA, census 23 Oct), this one is the order's card
            with self._lock:
                self.stats.duplicates += 1
            return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": out.event_type,
                            "reason": f"duplicate of {known.get('repeats')} (same order {known.get('id')}, "
                                      f"same stage {known.get('stage')})"[:300], "updated_at": now})
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
                                       (view or {}).get("ownership"), found_facts)
        two_hidden: dict[int, list[dict]] = {}   # CARD_TWO_PARTS: what part 2 hid, by candidate card
        @stages.timed("checks")
        def ground(candidate: Pass2Output):
            """Correct a card where the filing can settle it, then check what is left.

            Every card goes through this, including one a second provider wrote. It used to run on the
            first card only, so a corrected card was published having had none of it: no exact XBRL
            values, no deal size recomputed from shares x price, no unit slips fixed - on exactly the
            cards that had already failed once. The record stored beside the card described the card
            that had been thrown away (2026-10-17: Novartis FY25 was published at the right Rs 356.27 Cr
            with a note saying it had been changed to Rs 83.88 Cr, which was the discarded card).
            """
            # CARD_FACT_SHEET: a results amount or change the model writes that the exchange file's sheet contradicts is taken out first
            sheet_cuts = fact_sheet.removed(candidate, results_sheet)
            # a results card with its XBRL file: code writes the figures, the model's words are cut to a line or two
            built = (results_card.build(candidate, tagged, filing.company_name,
                                        results_card.history_from_view(full_view), filed_text, found_facts,
                                        self.settings.results_rich)
                     if tagged and "RESULTS" in (event_type, candidate.event_type) else [])
            # UNIT_SLIP_XBRL_GUARD: the file's own money facts reach the unit fixer only, never the grounding sources
            guard = (xbrl_facts.money_crore(getattr(tagged, "raw", None), filing.scrip_code, filing.xbrl_url or "")
                     if tagged and unit_slip_xbrl_guard() else ())
            units = fix_unit_slips(candidate, sources, guard, scale_crore(dossier) if unit_fix_scale_guard() else ())
            foreign_fixes = fix_foreign_crore(candidate, filed_text)
            counts = fix_count_millions(candidate, sources)
            changes = sheet_cuts + built + fix_change_percentages(candidate, sources) + counts + foreign_fixes
            changes += apply_deal_guards(candidate, filing, history, dossier.get("balance_sheet", []), text)
            changes += deal_echo_slips(candidate, filed_text)
            changes += continued_deal(candidate, view, filed_text)
            changes += order_band.apply(candidate, filed_text)
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
            changes += directions.multiple_guard(candidate)   # "more than double" for +74%: the amounts decide
            # owner rule 26 Oct 2026: no EPS on new cards; last of the text edits, so nothing written above slips past it
            changes += no_eps.drop_eps(candidate)
            if card_two_parts() and candidate.card is not None:
                # part 2 lines that fail the checks are hidden one by one, before the whole-card checks (F152)
                two_hidden[id(candidate)] = two_parts.hide_part2(
                    candidate.card, sources, text=text, reading=blocks, known=f"{sources[3]}\n{scale}",
                    unit=declared_unit(filed_text))
            if consolidated_only:
                changes += standalone_figures_removed(candidate, tagged, standalone_file)
            changes += one_basis.apply(candidate, tagged, history)   # CARD_ONE_BASIS: one basis a figure (off: nothing)
            if card_ground_all_fields():   # CARD_GROUND_ALL_FIELDS: figures in the fields the check never read (off: nothing)
                # with the same computed figures the main check forgives (review of F204: else true sums were dropped)
                derived = (derived_figures(candidate.card, check_quant(candidate.card.quantified_impact, *sources), sources)
                           if candidate.card is not None else [])
                changes += ground_all_fields(candidate, sources, derived)
            if card_text_support():   # CARD_TEXT_SUPPORT: names, words, small counts, dates and labels the sources do not print (off: nothing)
                changes += card_support.apply(candidate, sources, filed_text)   # labels against the document alone, not our XBRL table's own labels
            found = check_card_all(candidate, view, sources, history)
            found.scale += period_mixups(candidate, tagged, filed_text)
            found.scale += basis_mixups(candidate, tagged, standalone_file)
            found.scale += gate.stale_columns(_card_texts(candidate), filed_text)
            found.scale += foreign_as_rupees(_card_texts(candidate), filed_text)
            found.form += headline_form(candidate) + working_text(candidate)
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
        first_reply = result
        review = None
        if checks.wants_second_opinion and self.settings.second_opinion:
            out, result, checks, review, fixes = self._second_opinion(
                route, system, user, out, result, checks, ground, bulk)
            if fixes is not None:
                unit_fixes, change_fixes, quotes_missing, quotes_dropped = fixes
        # a card whose figures are its own XBRL file's, every amount grounded: the garbled text layer cannot have
        # given it a wrong figure (held-card audit, 22 Oct 2026: 15 such holds, all false)
        checks.held += self._held_reasons(filing, text, xbrl_backed=bool(tagged) and not checks.amounts_ungrounded)
        # a checks.held reason only publishes the card as unverified; these take it out of the feed (held), its facts kept
        hide: list[str] = []
        if other_issuer:
            hide.append(f"The results in this filing are {other_issuer}'s, not {filing.company_name}'s own (CARD_OTHER_ISSUER)")
        if out.card is not None and not tagged and (out.event_type or event_type) == "RESULTS":
            # a PDF-read results card whose earlier quarters contradict memory read its columns out of order (MASKINVEST)
            wrong = comparative_memory.contradictions(
                [out.card.headline or "", out.card.takeaway or "", out.timeline_entry or ""]
                + [f.text for f in out.card.what_happened] + [f"{k.label} {k.value} {k.change or ''}" for k in out.card.key_numbers],
                dossier)
            if wrong:
                hide.append("Earlier quarters contradict memory, columns read out of order: " + "; ".join(wrong[:3])
                            + " (CARD_COMPARATIVE_MATCHES_MEMORY)")
        if out.card is not None and (repeat := event_repeats.match(
                out.event_type or event_type, filing.filed_at, f"{out.card.headline or ''} {out.timeline_entry or ''}",
                filing.company_name, dossier.get("timeline"), filing.news_id)):
            # the same order or deal from a second document (S2): this card's facts stay stored, the first card is the event's
            hide.append(f"Repeat of {repeat[0]}: {repeat[1]} (CARD_EVENT_REPEAT)")
        checks.held += hide
        unchecked: list[str] = []
        if checks.only_quotes:
            # the points whose quote does not carry them leave the face, behind a tap; the card is published, not held
            pruned = prune_quote_failures(out, checks.quotes, unchecked)
            if pruned is not None:
                checks.quotes = []
                review = {**(review or {}), "status": "PRUNED", "pruned": pruned}
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
        if subsidiary:
            # the enclosed statement is the subsidiary's: not this company's results (the rules above would read the
            # statement and make it RESULTS), and its figures are not this company's quarter
            corrected = "OTHER" if corrected == "RESULTS" else corrected
            out.dossier_delta.financial_metrics = []
            out.dossier_delta.balance_sheet = None
        if corrected != out.event_type:
            log.info("event type for %s: %s -> %s (rules)", filing.news_id, out.event_type, corrected)
            out.event_type = corrected
        deal = out.card.deal_value if out.card is not None else None
        if deal is not None and deal.kind == "ACQUISITION" and _DEMERGER.search(f"{filing.headline} {filing.subject} {out.card.headline}"):
            deal.kind = "OTHER"   # a demerger moves a business out; it is not an acquisition (live review 3)
        if out.card is not None and out.event_type != "CONCALL_PRESENTATION":
            out.card.call_read = None  # guidance, tone and transparency describe a call, not other filings
            out.card.call_takeaways = []
        # each call takeaway checked on its own: a failed one goes to the AI reading and never holds the card
        takeaway_notes = (check_ai_takeaways(out.card, text, blocks, view, declared_unit(filed_text))
                          if out.card is not None and out.event_type == "CONCALL_PRESENTATION" else [])
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
        # A held card's own reading stays out of memory: its figures, notes, deals and guidance did not pass the checks.
        # Only the exchange file's figures are kept (owner, 25 Oct 2026, reversing T5 of 20 Oct, which kept a held card's
        # figures as "the statement's own")
        held_now = (review or {}).get("status") == "UNRESOLVED" and not checks.only_style
        if held_now:
            remembered = out.model_copy(deep=True)
            remembered.dossier_delta = DossierDelta()
        if tagged:
            _apply_xbrl(out, tagged, filing.news_id)
            _apply_xbrl(remembered, tagged, filing.news_id)
        # METRIC_BUSINESS_LINE: each operating figure names the business line it is about (code from the headline, else the model's)
        business_line.assign(remembered.dossier_delta.financial_metrics, filing, dossier)
        score, checked, ungrounded, quant, claims = checks.score, checks.checked, checks.ungrounded, checks.quant, checks.claims

        merged = merge(dossier, remembered, filing, card.impact_level, now,
                       fy_end_month=getattr(tagged, "fy_end_month", None) if tagged else None)
        if results_q:
            for t in merged.get("timeline", []):
                if t.get("news_id") == filing.news_id and t.get("event_type") == "RESULTS":
                    t["quarter"] = results_q
                    if getattr(tagged, "basis", None):
                        t["basis"] = tagged.basis
        if standalone_file is not None and standalone_file.kind == "RESULTS":
            # the same quarter's standalone figures, for the company page's standalone view (never the card's)
            put_standalone(merged, standalone_file.memory_metrics(), standalone_file.balance_sheet, filing.filed_at, filing.news_id)
            if getattr(standalone_file, "raw", None):
                # the standalone statements by the same rules (screener_view's standalone recipes); the card never reads them
                statements.from_file(self.sink, merged, standalone_file.raw, filing.scrip_code, standalone_file.url,
                                     filing.news_id, filing.filed_at, now)
        merged.update({k: v for k, v in (("industry", industry), ("sector", sector), ("symbol", company.get("symbol") or filing.symbol)) if v})
        raw_xbrl = getattr(tagged, "raw", None) if tagged else None
        if raw_xbrl:
            # the same file's rows by screener's rules, kept beside the figures (owner, 30 Oct 2026); never fails the filing
            statements.from_file(self.sink, merged, raw_xbrl, filing.scrip_code, filing.xbrl_url or "", filing.news_id,
                                 filing.filed_at, now)
        if event_type == "CONCALL_PRESENTATION" and not held_now:
            # the call's checked takeaways, kept for the company page's quarterly summary (owner, 2026-10-21: the
            # summary was built from the few items memory happened to keep, not the call's analysis)
            remember_call_points(merged, filing.news_id, filing.filed_at, card.call_takeaways)
            self._call_memory_step(filing, industry, merged, text, blocks)
        # Signals, footer and results table see memory as it stood at this filing, not later facts
        # that a backfill may already have stored.
        before = dossier_as_of(dossier, filing.filed_at, inclusive=False)
        current = dossier_as_of(merged, filing.filed_at)
        # Market data as it stood when the filing came out: the stored daily series (history fill on
        # the laptop), else today's figures, dropped when they are too new for this filing.
        priced = point_in_time(company, filing.filed_at, self._prices, self._buckets) or priced_for(company, filing)
        watch_cuts: list[str] = []
        if card_watch_verdict() and out.card is not None:   # F205: a sentence against the code's watch verdict is cut
            from . import watch_code
            watch_cuts = watch_code.drop_contradicting(out.card, watch_code.verdicts_for(before, current, out, filing))
        signals = compute_signals(before, current, out, filing, priced) + text_signals(text, event_type)
        if (review or {}).get("status") == "UNRESOLVED" and not checks.only_style:
            # a held card's line stays out of the company's story: Heritage's held Q2FY27 board outcome and its
            # published press release made two Q2FY27 results lines with different figures (T5, 2026-10-20).
            # Its figures stay: they are the statement's own and passed memory's checks.
            merged["timeline"] = [e for e in merged.get("timeline", []) if e.get("news_id") != filing.news_id]
        # written with the card's row, not before it (_write_memory, which also keeps what other jobs stored meanwhile)
        with self._lock:
            self._pending_memory.setdefault(filing.scrip_code, []).append((filing.news_id, merged, read))

        card_json = {
            "category_tag": EVENT_TAGS.get(event_type, "UPDATE"),
            "event_type": event_type,
            **card.model_dump(),
            "quantified_impact": quant.items,
            "signals": signals,
            "timeline_entry": out.timeline_entry,
            "fundamentals": latest_fundamentals(current, sector_module.footer),
            "results": (results_snapshot(current, filing.news_id, sector_module.footer, printed=filed_text)
                        if event_type == "RESULTS"
                        else call_results_snapshot(current, filing.filed_at, sector_module.footer, before)
                        if event_type == "CONCALL_PRESENTATION" else None),
            "volume_strip": volume_strip(current, filing.news_id) if event_type == "MONTHLY_BUSINESS_UPDATE" else None,
            # the key takeaways memory took from this call, by heading (call_summary.py)
            "call_memory": (card_takeaways(current, filing.news_id, filing.filed_at)
                               if event_type == "CONCALL_PRESENTATION" else None),
            # the event's own block on the card's face, made by code (card_context.py, signals.scale_parts)
            "scale": scale_parts(before, out, priced, filing.filed_at),
            "rating_change": rating_change(before, current, filing.news_id, text) if event_type == "DEBT_RATINGS" else None,
            "case_stage": case_stage(event_type, card.headline, [f.text for f in card.what_happened],
                                     [w.text for w in card.why_it_matters]),
            "guidance_recall": guidance_recall(before, event_type, filing.filed_at),
            "memory_context": memory_context(before, event_type, filing.filed_at, filing.news_id),
            # what pass 2 said about earlier promises, kept so a status in memory can be traced to its reply (T5)
            "promise_updates": [u.model_dump() for u in out.dossier_delta.promise_updates] or None,
            "pdf_pages": doc.page_count or None,
            "grounding": {"score": score, "checked": checked, "ungrounded": ungrounded[:10],
                          "math_mismatches": quant.mismatches, "unsupported_claims": claims,
                          "unit_fixes": unit_fixes or None, "change_fixes": change_fixes or None,
                          "quotes_missing": quotes_missing or None, "quotes_dropped": quotes_dropped or None,
                          "quotes_paraphrased": checks.quote_style or None, "out_of_fit": checks.scale or None,
                          "call_takeaways_unverified": takeaway_notes or None,
                          **({"watch_verdict_cut": watch_cuts} if watch_cuts else {})},
            "review": review,
            "model": result.model_label,
            "pack": result.pack,
        }
        evidence = self._save_evidence(filing, first_reply, result, now)
        if evidence:
            card_json["grounding"]["evidence"] = evidence
        card_json["grounding"]["prompt_variant"] = variant
        # set by code only, never read from the model's reply: the points the prune took off the face (shown behind
        # "Facts the checks could not quote"); a model's own "unchecked" key is overwritten here
        card_json["unchecked"] = unchecked or None
        needs_review = checks.needs_review
        # a call card's quarter figure the company's own XBRL contradicts is dropped, and a headline or point repeating it
        # sends the card to review (Bajaj Consumer, daily audit 21 Oct 2026: a transcript slip over the filed figures)
        conflicts = results_card.call_figure_conflicts(card_json.get("results"), card_json.get("key_numbers") or [])
        if conflicts:
            slipped = {c["value"] for c in conflicts}
            card_json["key_numbers"] = [k for k in card_json["key_numbers"] if k.get("value") not in slipped]
            card_json["grounding"]["call_figure_conflicts"] = conflicts
            face = [card_json.get("headline") or ""] + [p.get("text") or "" for p in card_json.get("what_happened") or []]
            if any(v in line for v in slipped for line in face):
                needs_review = True
        # the table and the key numbers read against the card's stated basis (CARD_ONE_BASIS; off: nothing)
        if one_basis_notes := one_basis.apply_card_json(card_json, current):
            card_json.setdefault("grounding", {})["one_basis"] = one_basis_notes
        # each results row on one statement line, a figure on another basis labelled (CARD_RESULTS_ONE_LINE; off: nothing)
        if one_line_notes := results_one_line.apply_card_json(card_json):
            card_json.setdefault("grounding", {})["one_line"] = one_line_notes
        # a profit figure that is not the table's reported profit is labelled with it (CARD_ADJUSTED_PROFIT_LABEL; off: nothing)
        if profit_notes := results_one_line.profit_label_card_json(card_json):
            card_json.setdefault("grounding", {})["profit_label"] = profit_notes
        # a comparison word its own figures contradict is dropped or softened (CARD_WORDS_MATCH_FIGURES; off: nothing)
        if words_notes := words_figures.apply_card_json(card_json, current):
            card_json.setdefault("grounding", {})["words_figures"] = words_notes
        # a year-ago label one year too old is put right (CARD_YEAR_AGO_LABEL; off: nothing)
        if year_notes := year_ago_label.apply_card_json(card_json):
            card_json.setdefault("grounding", {})["year_ago_label"] = year_notes
        # a ratio comparison read from a shifted column is corrected or dropped (CARD_RATIO_COLUMNS; off: nothing)
        if ratio_notes := ratio_columns.apply_card_json(card_json):
            card_json.setdefault("grounding", {})["ratio_columns"] = ratio_notes
        # a figure only memory's guidance holds, stated as an actual, is dropped (CARD_GUIDED_NOT_ACTUAL; off: nothing)
        if guided_notes := guided_actual.apply_card_json(card_json, current):
            card_json.setdefault("grounding", {})["guided_not_actual"] = guided_notes
        # the results table's rows are the exchange file's sheet (CARD_FACT_SHEET; off or no sheet: nothing); the card keeps what changed
        if results_sheet:
            card_json.setdefault("grounding", {})["fact_sheet"] = {
                "period": results_sheet["period"], "basis": results_sheet["basis"], "source_news_id": results_sheet.get("source_news_id"),
                "table_changed": fact_sheet.apply_to_results(card_json.get("results"), results_sheet) or None}
        # a footer figure that cannot be right is left off the card (CARD_FOOTER_PLAUSIBLE; off: nothing); the card keeps why
        if card_footer_plausible() and (footer_notes := footer_plausible.card_notes(card_json)):
            card_json.setdefault("grounding", {})["footer_hidden"] = footer_notes
        # A card the checks faulted, that a second provider was asked to correct and that still
        # fails, is kept out of the feed rather than published with an "Unverified" mark. On the
        # rebuild that was 117 of 456 cards, and a flagged card was judged WRONG 52% of the time
        # against 21% for a clean one (audit round 1), so for a feed meant to run unattended the
        # old trade was the wrong way round. The row is still written in full for the digest, the
        # audit export and the review queue.
        # ...unless all that is left is how the card quoted the filing. Its figures were each found in
        # the document; only the sentence around them is the model's wording. Prism Johnson's three
        # segment facts were held that way on 2026-10-17 with every figure verified.
        if card_two_parts():
            # every line sorted into part 1 or part 2 by code, after every edit above (indexes point at the final lists)
            card_json["parts"] = two_parts.split_card(card_json, text, blocks, two_hidden.get(id(out)))
        held = (review or {}).get("status") == "UNRESOLVED" and not checks.only_style
        held = held or bool(hide)   # another company's results, a repeat, columns out of order: out of the feed (switches above)
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
            card_json["annual_checks"] = annual_xbrl.card_block(annual)
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
        # not `text`: that name holds the filing's text, which the critic reads below
        for deadline, note in warrant_deadlines(out, filing):  # module 31: the 18-month warrant clock
            catalysts.append({
                "id": _catalyst_id(filing.scrip_code, "WARRANT_EXPIRY", deadline), "scrip_code": filing.scrip_code,
                "company_name": filing.company_name, "symbol": row["symbol"], "event_type": "WARRANT_EXPIRY",
                "event_date": deadline, "description": note[:300], "source_news_id": filing.news_id, "created_at": now,
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
        critic_job = None
        if self.settings.critic and not bulk and not held:
            from . import critic   # live published cards only: a snapshot, so the critic can never touch the card

            critic_job = critic.build_job(filing.news_id, card_json, result.model_label, text, view, filing.filed_at,
                                          event_type)
        return Outcome(
            critic=critic_job,
            update={"news_id": filing.news_id, "status": "ANALYZED", "event_type": event_type,
                    "reason": None, "last_error": None, "updated_at": now},
            card=row,
            catalysts=catalysts,
            company={"scrip_code": filing.scrip_code, "company_name": filing.company_name,
                     "symbol": row["symbol"], "sector": sector, "updated_at": now,
                     **({"credibility_score": rated.credibility} if rated.credibility is not None else {}),
                     **_company_memory(merged)},
        )

    def _memory_only(self, filing: Filing, bulk: bool) -> bool:
        """An older backfill filing with no card yet is read into memory only (settings.backfill_cards_from)."""
        cut = self.settings.backfill_cards_from
        if not bulk or not cut or filing.filed_at[:10] >= cut:
            return False
        # a filing that already has a card keeps getting one: a re-read never leaves a card's filing without it
        return not (self._card_shown(filing.news_id) or self._card_held(filing.news_id))

    def _memory_flow(self, filing: Filing, company: dict, industry, event_type: str, dossier: dict, read: dict,
                     view: dict | None, text: str, filed_text: str, tagged, standalone_file, scale: str, events: list,
                     now: str, blocks: str = "") -> Outcome:
        """An older backfill filing into memory with no card (owner, 24 Oct 2026): one slimmer AI reading of the memory
        delta, the deal and what to track (prompts.memory, MemoryOutput), then the same event-type rules, deal guards,
        memory trust checks, XBRL figures and merge a card's memory gets. Nothing is written to the cards table."""
        system, user = self.prompts.memory(filing, event_type, industry, view, text, scale=scale)
        route, packer = self._pass2_writer(True, len(system) + len(user))
        with stages.stage("pass2"):
            if packer is not None:
                result = packer.complete(route, system, user, MemoryOutput, filing.news_id)
            else:
                self.gateway.start_cap()
                result = self.gateway.complete_json(route, system, user, MemoryOutput, bulk=True)
        out: MemoryOutput = result.value
        if not out.is_material:
            with self._lock:
                self.stats.not_material += 1
            return Outcome({"news_id": filing.news_id, "status": "NOT_MATERIAL", "event_type": out.event_type,
                            "reason": f"memory: not material{': ' + out.reason if out.reason else ''}"[:300],
                            "updated_at": now})
        if out.event_type in (*ONE_EVENT_ONE_CARD, *REPEAT_BY_WORDS) and not is_transcript(filing):
            repeat = similar_timeline_entry(dossier, filing, out.timeline_entry)
            if repeat:
                with self._lock:
                    self.stats.duplicates += 1
                return Outcome({"news_id": filing.news_id, "status": "DUPLICATE", "event_type": out.event_type,
                                "reason": f"duplicate of {repeat['news_id']} (same event, in other words)", "updated_at": now})
        if filing.route == "FAST_TRACK" and filing.event_type:
            out.event_type = filing.event_type   # rules know the event type better than the model
        elif out.event_type == "OTHER" and event_type != "OTHER":
            out.event_type = event_type
        out.event_type = event_type_rules(out.event_type, filing, text, tagged)
        history = dossier.get("financial_metrics", [])
        apply_deal_guards(out, filing, history, dossier.get("balance_sheet", []), text)
        event_xbrl.apply_orders(out.card, event_xbrl.orders(events))   # the event file's figures have the last word
        remembered, _ = trust.for_memory(out, filed_text, company, dossier)
        if tagged:
            _apply_xbrl(remembered, tagged, filing.news_id)
        business_line.assign(remembered.dossier_delta.financial_metrics, filing, dossier)   # METRIC_BUSINESS_LINE
        merged = merge(dossier, remembered, filing, None, now,
                       fy_end_month=getattr(tagged, "fy_end_month", None) if tagged else None)
        if standalone_file is not None and standalone_file.kind == "RESULTS":
            put_standalone(merged, standalone_file.memory_metrics(), standalone_file.balance_sheet, filing.filed_at, filing.news_id)
            if getattr(standalone_file, "raw", None):
                # the standalone statements by the same rules (screener_view's standalone recipes); the card never reads them
                statements.from_file(self.sink, merged, standalone_file.raw, filing.scrip_code, standalone_file.url,
                                     filing.news_id, filing.filed_at, now)
        sector = self.prompts.sector_for(industry).name
        merged.update({k: v for k, v in (("industry", industry), ("sector", sector),
                                         ("symbol", company.get("symbol") or filing.symbol)) if v})
        if getattr(tagged, "raw", None):
            statements.from_file(self.sink, merged, tagged.raw, filing.scrip_code, filing.xbrl_url or "", filing.news_id,
                                 filing.filed_at, now)
        if event_type == "CONCALL_PRESENTATION":
            self._call_memory_step(filing, industry, merged, text, blocks)
        kept = keep_concurrent_writes(merged, read, self.sink.get_dossier(filing.scrip_code))
        if kept:
            log.info("%s: memory written meanwhile by another job kept: %s", filing.news_id, ", ".join(kept))
        with stages.stage("memory_write"):
            self.sink.put_dossier(filing.scrip_code, merged)
        self._save_evidence(filing, result, result, now)
        symbol = company.get("symbol") or filing.symbol
        catalysts = [
            {"id": _catalyst_id(filing.scrip_code, ev.event_type, ev.date), "scrip_code": filing.scrip_code,
             "company_name": filing.company_name, "symbol": symbol, "event_type": ev.event_type, "event_date": ev.date,
             "description": ev.description[:300], "source_news_id": filing.news_id, "created_at": now}
            for ev in out.dossier_delta.upcoming_events if ev.date >= filing.filing_date
        ]
        with self._lock:
            self.stats.memory_only += 1
        return Outcome(
            update={"news_id": filing.news_id, "status": "ANALYZED", "event_type": out.event_type,
                    "reason": f"memory only: a backfill filing before {self.settings.backfill_cards_from}, no card",
                    "last_error": None, "updated_at": now},
            catalysts=catalysts,
            company={"scrip_code": filing.scrip_code, "company_name": filing.company_name, "symbol": symbol,
                     "sector": sector, "updated_at": now, **_company_memory(merged)},
        )

    def _repeat_check(self, filing, recent: list[dict], dossier: dict, bulk: bool, opening: str = "") -> dict | None:
        """One cheap call: is this filing an event the feed already has? The model only points at an
        entry; `timeline_entry_dated` then checks the entry is really on file and near in time, so a
        date it invents drops nothing. A failure here is never fatal - the filing goes on to pass 2.
        It is shown the opening of the document: from BSE's boilerplate headline alone it took a ₹1.73 Cr GST
        notice for FY22 to repeat a ₹2.64 Cr one for FY20, and a completed acquisition to repeat its signing."""
        system, user = self.prompts.repeat(filing, recent, opening)
        try:
            with stages.stage("pass1"):
                said = self.gateway.complete_json("pass1_bulk" if bulk else "pass1", system, user, RepeatVerdict).value
        except Exception as exc:
            log.info("repeat check skipped for %s: %s", filing.news_id, type(exc).__name__)
            return None
        entry = timeline_entry_dated(dossier, filing, said.duplicate_of)
        if entry:
            log.info("repeat check: %s repeats %s (%s) - %s; pass 2 not spent on it", filing.news_id,
                     entry.get("news_id"), str(entry.get("date", ""))[:10], said.why[:60])
        return entry

    def _call_memory_step(self, filing: Filing, industry, merged: dict, text: str, blocks: str) -> None:
        """MEMORY_CALL_V2 (F180): the call or deck's own memory reading (call_memory.py), its checked points into
        ``merged["call_memory"]`` just before the memory write. Off, or any failure, leaves memory and the card as they were:
        the points wait for a re-run of `call-memory --ids`. On, it only queues the filing (call_queue.py); the reading is the
        job `call-memory --pending`."""
        if not memory_call_v2():
            return
        try:
            # the reading itself is a queued job (call-memory --pending, call-memory.yml): a slow reply never holds the cards
            call_queue.enqueue(self.sink, filing.news_id, filing.scrip_code, filing.filed_at)
        except Exception as exc:   # noqa: BLE001 - the card goes on; `call-memory --ids` reads it later
            log.warning("%s: call memory not queued, the card stands: %s", filing.news_id, exc)

    def _pass2_writer(self, bulk: bool, prompt_chars: int):
        """(route, packer or None) for one filing's pass 2. A live filing and a backfill one never share a pack, and a
        long one (a transcript, presentation or annual report) is packed with other long ones only; one too large for
        a pack goes to `pass2_long` alone. Packed or not, the fallback route and its order are the same as before."""
        route = "pass2_bulk" if bulk else "pass2"
        long = prompt_chars / 4 > LONG_PROMPT_TOKENS and self.gateway.has_route("pass2_long")
        if long:
            route = "pass2_long"  # long-context models only
        packer = self._packers.get((bulk, long))
        if long and prompt_chars > LONG_PACK_MAX_CHARS:
            packer = None
        return route, packer

    def _second_opinion(self, route, system, user, out: Pass2Output, result, checks: CardChecks, ground,
                        bulk: bool = False):
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
            with stages.stage("pass2"):
                self.gateway.start_cap()   # keeps the first start when this filing's first card began one
                second = self.gateway.complete_json(route, system2, user2, Pass2Output, avoid_providers=(result.provider, result.model_label),
                                                    bulk=bulk)
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

    @stages.timed("sink_read")
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

    @stages.timed("sink_read")
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

    @stages.timed("sink_read")
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

    @stages.timed("sink_read")
    def _memory(self, scrip: str) -> dict | None:
        """A company's memory as this run knows it: its latest card's memory not yet written, else the store's."""
        with self._lock:
            pending = self._pending_memory.get(scrip)
            if pending:
                return json.loads(json.dumps(pending[-1][1]))
        return self.sink.get_dossier(scrip)

    def _write_memory(self, outcomes: list[Outcome]) -> None:
        """The memory of committed cards, in the order they were made, each merged with what other jobs stored meanwhile."""
        committed = {o.update.get("news_id") for o in outcomes}
        with self._lock:
            ready = []
            for scrip, entries in list(self._pending_memory.items()):
                ready += [(scrip, e) for e in entries if e[0] in committed]
                rest = [e for e in entries if e[0] not in committed]
                if rest:
                    self._pending_memory[scrip] = rest
                else:
                    del self._pending_memory[scrip]
        for scrip, (news_id, merged, read) in ready:
            kept = keep_concurrent_writes(merged, read, self.sink.get_dossier(scrip))
            if kept:
                log.info("%s: memory written meanwhile by another job kept: %s", news_id, ", ".join(kept))
            with stages.stage("memory_write"):
                self.sink.put_dossier(scrip, merged)

    def _drop_memory(self, news_id: str) -> None:
        """A card the database refused leaves no memory either."""
        with self._lock:
            for scrip, entries in list(self._pending_memory.items()):
                rest = [e for e in entries if e[0] != news_id]
                if rest:
                    self._pending_memory[scrip] = rest
                else:
                    del self._pending_memory[scrip]

    def _commit(self, outcomes: list[Outcome]) -> None:
        if not outcomes:
            return
        with self._commit_lock:
            self._commit_locked(outcomes)
            # the shadow critic sees only what was committed, and only a card still published (not held since, D20)
            self._critic_jobs += [o.critic for o in outcomes if o.critic and o.card and not o.card.get("held")]

    def _commit_locked(self, outcomes: list[Outcome]) -> None:
        try:
            self._commit_rows(outcomes)
            self._write_memory(outcomes)
        except SinkRejected as exc:
            # One bad row must not block the batch (and get its filings analysed again on every
            # run): commit filing by filing, and mark the ones the database refuses as FAILED.
            log.error("batch rejected (%s); committing one filing at a time", exc)
            for outcome in outcomes:
                try:
                    self._commit_rows([outcome])
                    self._write_memory([outcome])
                except SinkRejected as one:
                    news_id = outcome.update["news_id"]
                    self._drop_memory(news_id)
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

    def _fresh(self, today: date, deadline: float, memory_complete: bool) -> None:
        """Today's new filings: looked for again (one NSE call; yesterday's too before 09:00 IST) and made into cards before
        any older work goes on. The run's whole deadline: today's filings are never cut short for older work. Today's own
        queue is worked in slices of SLICE_S with a look for new filings before each, so a busy day does not hide a
        filing broadcast mid-run (27 Oct 2026: today's queue took the whole first single run and NSE was asked twice in
        40 minutes). Out of AI quota, new filings are still recorded (no AI) and wait for the next run; ``process``
        stops on the quota itself."""
        days = [today - timedelta(days=1), today] if now_ist().hour < 9 else [today]
        while not self._blocked:
            for day in days:
                self._discover_safely(day, full=False)
            if time.monotonic() >= deadline:
                return   # the run's time is up: the filings just found wait for the next run
            end = min(deadline, time.monotonic() + SLICE_S)
            self._slice(lambda: self.process(today.isoformat(), today.isoformat(), deadline, bulk=False,
                                             memory_complete=memory_complete, history_first=True), end)
            now = time.monotonic()
            if now < end or now >= deadline or self._halted(bulk=False):
                return   # today's queue is empty for now, the run's time is up or the route is out of quota

    def _requeued_first(self, history_to: date, deadline: float) -> int:
        """Filings requeued by id (``requeue:by_id``) that are older than the live window, read in a slot of at most
        REQUEUED_FIRST_S right after today's filings, REQUEUED_FIRST_MAX a run. In results season today's filings used every
        run's whole time and the history pass, where such a filing waited, never started (31 Oct 2026: Hubtown nse-106629168,
        a wrong live card, still not re-run six hours after its requeue). Ids no longer pending are dropped from the list;
        one deferred stays for the next run. Returns how many filings were read."""
        raw = self.sink.kv_get(requeue.BY_ID_KEY)
        if not raw or self._blocked or self._halted(bulk=True):
            return 0
        try:
            marked = json.loads(raw)
        except ValueError:
            marked = {}
        ids = list(marked.get("ids") or [])
        if not ids:
            return 0
        start, wanted = self.settings.backfill_start, set(ids)

        def queues() -> dict[str, list[Filing]]:
            out = {}
            for scrip in marked.get("scrips") or []:
                rows = self.sink.pending_for_company(scrip, start, history_to.isoformat(), self.settings.max_attempts, HISTORY_LIMIT)
                q = [f for f in (Filing.model_validate(r) for r in rows) if f.news_id in wanted]
                if q:
                    out[scrip] = q
            return out

        before, todo, n = queues(), {}, 0
        for scrip, q in before.items():
            q = [f for f in q if f.news_id not in self._tried][:max(0, REQUEUED_FIRST_MAX - n)]
            if q:
                todo[scrip], n = q, n + len(q)
        done, after = 0, before
        if todo:
            end = min(deadline, time.monotonic() + REQUEUED_FIRST_S)
            results: dict = {}
            self._slice(lambda: results.update(self._run_parallel(
                {s: partial(self._process_group, q, deadline, True, True) for s, q in todo.items()})), end)
            done = sum(len(v) for v in results.values())
            log.info("requeued by id, read first: %d of %s", done, ", ".join(f.news_id for q in todo.values() for f in q))
            after = queues()
        # an id still pending stays (deferred, or past this run's share); one no longer pending (read, or inside the live
        # window, which the live pass reads) is dropped
        pending = {f.news_id for q in after.values() for f in q}
        left = [i for i in ids if i in pending]
        if left != ids:
            self._kv_set(requeue.BY_ID_KEY, json.dumps({"ids": left, "scrips": [s for s in marked.get("scrips") or [] if s in after]}))
        return done

    def _in_slices(self, step, until: float, fresh, slice_s: float | None = None) -> None:
        """Older work in slices (SLICE_S unless given), today's new filings looked for between them. A slice that ends
        before its own deadline had nothing left to do (or the route is out of quota), so the step is finished for this
        run. With no today to look for (a backfill-only run) the step runs in one piece."""
        if fresh is None:
            step()
            return
        while time.monotonic() < until and not self._blocked:
            end = min(until, time.monotonic() + (slice_s or SLICE_S))
            self._slice(step, end)
            more = time.monotonic() >= end
            fresh()
            if not more:
                return

    def _slice(self, step, end: float) -> None:
        """One slice of a step: no filing starts past ``end``; a filing started keeps the run's deadline."""
        outer, self._slice_end = self._slice_end, end
        try:
            step()
        finally:
            self._slice_end = outer

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
            backfill_done = self.sink.kv_get("backfill:complete") == "1"
            # one run for every filing (owner, 27 Oct 2026: "one run instead of two"; it replaces pipeline-today.yml):
            # today's new filings first, then the older work in slices, today looked for again after each slice, so a
            # filing broadcast during the run waits minutes for its card, not the whole run
            fresh = partial(self._fresh, today, deadline, backfill_done) if mode in ("live", "all") else None
            if fresh:
                days = [today - timedelta(days=1), today] if now_ist().hour < 9 else [today]
                for day in days:
                    self._discover_safely(day, full=False)
                # the window's earlier days cost ~2,000 ledger writes each: under the daily write budget, like the
                # backfill, so today's filings keep the free tier's headroom (20 Oct: 80,013 writes by 11:30 IST)
                if writes_at_start + self.stats.d1_rows_written < self.settings.d1_daily_write_budget:
                    self._discover_window(live_from, today)
                self._requeue_failed_nightly(live_from)
                self._sweep_held()
                if self._on_nse():
                    self.retriage_returning(today, started + time_budget_s * 0.2)
                fresh()
                if mode == "all":
                    self._requeued_first(live_from - timedelta(days=1), deadline)
                live_deadline = deadline if mode == "live" else started + time_budget_s * 0.6
                # Near the day's share of the plan's writes (D1_DAILY_WRITE_CAP) the window's earlier days, the
                # catch-ups and the memory syncs wait for the reset (05:30 IST) and the run only turns today's filings
                # into cards (20 Oct 2026: 91,080 by 20:30 IST, ~400 writes a run on the window's backlog)
                near_cap = writes_at_start + self.stats.d1_rows_written >= D1_FREE_DAILY_WRITES * D1_NEAR_CAP
                if not near_cap and live_from < today:
                    earlier = (live_from.isoformat(), (today - timedelta(days=1)).isoformat())
                    self._in_slices(lambda: self.process(*earlier, live_deadline, bulk=False, memory_complete=backfill_done,
                                                         history_first=True), live_deadline, fresh)
                near_cap = writes_at_start + self.stats.d1_rows_written >= D1_FREE_DAILY_WRITES * D1_NEAR_CAP
                if near_cap:
                    log.warning("D1 writes near the free tier's daily %d: earlier days, catch-ups and memory syncs "
                                "skipped this run", D1_FREE_DAILY_WRITES)
                if self._on_nse() and not near_cap:
                    from . import event_catchup   # cards made before their event XBRL landed

                    # its own window (30 Oct 2026: on a results-heavy day today's filings used the whole live share, so
                    # this never ran and 20 of 46 results cards stayed without their table and memory without the
                    # quarter); the run's full budget still bounds it
                    caught = event_catchup.results_catch_up(
                        self, min(deadline, max(live_deadline, time.monotonic() + RESULTS_CATCH_UP_S)))
                    log.info("results XBRL catch-up: %s", json.dumps(caught))
                    if results_press_release():   # RESULTS_PRESS_RELEASE (TODO 135)
                        log.info("press releases joined to their results cards: %s",
                                 json.dumps(event_catchup.release_catch_up(self, min(deadline, live_deadline + RESULTS_CATCH_UP_S))))
                    fresh()
                if self._on_nse() and time.monotonic() < live_deadline and not near_cap:
                    caught = event_catchup.catch_up(self, live_deadline)
                    if caught["rerun"] or caught["stopped"]:
                        log.info("event XBRL catch-up: %s", json.dumps(caught))
                    fresh()
                    # at most hourly: the three sweeps took ~17 of a run's 24 live minutes and mostly filed nothing (25 Oct
                    # 2026: shareholding "filed": 5 of 1,069 companies looked at)
                    if time.monotonic() < live_deadline and self._memory_syncs_due():
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
                        fresh()
                    if time.monotonic() < live_deadline and self._dgtr_due():
                        self._dgtr_sync(live_deadline)
                    if time.monotonic() < live_deadline and self._annual_catchup_due():
                        self._annual_catchup(live_deadline)
                        fresh()
                # its own slot of at most CRITIC_MAX_S from the run's time, before the backfill: inside the live part it
                # got none whenever the live filings used their share (21 Oct 05:33 IST: 6 cards queued, 0 judged)
                self._run_critic(deadline)
            if mode in ("backfill", "all") and not self._halted(bulk=True):
                history_to = live_from - timedelta(days=1)
                days = [max_backfill_days]   # history days are discovered in the first slice only, as in one call before

                def backfill() -> None:
                    self._backfill(today, deadline, writes_at_start, days[0], history_to)
                    days[0] = 0

                self._in_slices(backfill, deadline, fresh, BACKFILL_SLICE_S)
        except nse_api.FileCapReached as exc:
            self.stats.stopped_reason = self.stats.stopped_reason or "file cap reached: the rest waits for the next run"
            log.warning("%s", exc)   # the cap is a planned stop, not an error: the status stays as it was
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

    def _run_critic(self, deadline: float) -> None:
        """The shadow critic over this run's committed live cards (critic.py), after the live part and before the
        backfill, at most CRITIC_MAX_S seconds. It writes no D1 row and changes no card; it never fails the run."""
        jobs, self._critic_jobs = self._critic_jobs, []
        if not jobs or not self.settings.critic or not self.gateway.has_route("critic"):
            return
        from . import critic

        deadline = min(deadline, time.monotonic() + self.settings.critic_max_s)
        saved = self.gateway.deadline
        self.gateway.deadline = deadline   # no request outlives the critic's time
        try:
            system = (self.settings.config_dir / "prompts" / "critic.md").read_text()
            vote_path = self.settings.config_dir / "prompts" / "critic_vote.md"
            vote_system = vote_path.read_text() if vote_path.exists() else ""
            self.stats.critic = critic.run(jobs, self.gateway, self.sink, system, deadline, self.settings.critic_max,
                                           self.stats.critic or None, vote_system=vote_system)
            log.info("shadow critic: %s", json.dumps(self.stats.critic))
        except Exception:
            log.exception("shadow critic failed")
        finally:
            self.gateway.deadline = saved
            self._flush_usage()

    def _sweep_held(self) -> None:
        """Once a day before Gemini's reset: held live-window cards with a writer's error read again (sweep.py)."""
        from . import sweep

        try:
            if sweep.due(self.sink):
                self.stats.sweep = sweep.run(self.sink, LIVE_DAYS, self.settings.max_attempts)
        except Exception:  # the sweep never stops a run
            log.exception("end-of-day sweep failed")

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

    def _memory_syncs_due(self) -> bool:
        """The governance, shareholding and pledge sweeps at most once in MEMORY_SYNC_EVERY (they mostly file nothing)."""
        last = self.sink.kv_get(MEMORY_SYNC_KEY)
        now = now_ist()
        try:
            if last and now - datetime.fromisoformat(last) < MEMORY_SYNC_EVERY:
                return False
        except ValueError:
            pass
        self._kv_set(MEMORY_SYNC_KEY, now.isoformat(timespec="seconds"))
        return True

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
        publish_snapshot(self.sink, force=bool(self.stats.analyzed))

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
        # Discovery stays a few days ahead of the analysis, not weeks: a day of history is about 250 filings and 5
        # rows written each, and discovering 5 days a run while the companies' queues wait spent the day's free D1
        # writes on filings nobody read yet (21 Oct 2026: one run discovered 2,737 filings, 7,234 rows, with
        # analysis weeks behind). The live window is never gated.
        while cursor < yesterday and days < max_days and not self._stop_starting(deadline):
            if self._over_budget(writes_at_start):
                break
            backlog = self.sink.backlog(start.isoformat(), history_to.isoformat(), BACKLOG_MAX)
            if backlog is not None and backlog >= BACKLOG_MAX:
                self.stats.stopped_reason = self.stats.stopped_reason or \
                    f"backfill discovery paused: {backlog}+ history filings still to read"
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
        state = {"built": today_ist().isoformat(), "through": "", "total": 0, "scrips": []}   # they count as `extra`
        self.sink.kv_set("backfill:company_order", json.dumps(state), now_iso())  # only these companies
        self._backfill_companies(day_from.isoformat(), day_to.isoformat(), "", deadline, self._writes_today())
        self._flush_usage()
        self.stats.status = "PARTIAL" if self.stats.failed else "OK"
        return self.stats

    def _known_day(self, day: date) -> bool:
        return self._noise_count(day.isoformat()) > 0 or bool(self.sink.known_ids(day.isoformat()))

    def _note_pace(self, through: str) -> None:
        raw = self.sink.kv_get("backfill:pace")
        pace = json.loads(raw) if raw else []
        nxt = _pace_entry(pace, today_ist().isoformat(), through)
        if nxt is not pace:
            self._kv_set("backfill:pace", json.dumps(nxt))

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
        # a company pulled forward by a live filing that was not on the morning's list is added work: counted in the
        # total, or "companies left" grew past it (System page, 22 Oct: 1,583 left of 1,577)
        extra = list(state.get("extra", []))
        extra += [s for s in priority if s not in set(state["scrips"]) and s not in set(extra)]
        state["extra"] = extra
        order: list[str] = priority + [s for s in state["scrips"] if s not in set(priority)]
        width = max(1, self.settings.workers) * 2
        while order and not self._stop_starting(deadline) and not self._halted(bulk=True) and not self._blocked:
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
        # read the key again before writing it: a requeue by id during this run put its companies there (requeue.prioritise), and
        # writing back the list read at the start would lose them (review of #298)
        kept = merged_priority(priority, json.loads(self.sink.kv_get("backfill:priority") or "[]"), order)
        if priority or kept:
            self._kv_set("backfill:priority", json.dumps(kept))
        total = (state.get("total") or 0) + len(state["extra"])
        self._kv_set("backfill:progress", json.dumps({"companies_left": len(order), "companies_total": total,
                                                      "built": state["built"], "through": through}))
        self._note_pace(through)
        return len(order)


PACE_DAYS = 8   # how many mornings of the discovery cursor the System page's estimate of the finish is based on


def _pace_entry(pace: list, today: str, through: str) -> list:
    """The cursor's first position each IST day, the last PACE_DAYS of them (System page: when the backfill ends)."""
    if not through or (pace and pace[-1][0] == today):
        return pace
    return (pace + [[today, through]])[-PACE_DAYS:]


def prompt_variant(news_id: str, bulk: bool, share: float) -> str:
    """Which pass-2 prompt writes this filing: the short one on `share` of live filings, picked by a hash of the news
    id (the same filing always gets the same one), the long one for the backfill and the rest (deep audit B1)."""
    if bulk or share <= 0:
        return "long"
    return "short" if int(hashlib.sha1(news_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < share else "long"


def _file_name(url: str | None) -> str:
    return (url or "").split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]


def _attachment_changed(stored: str | None, current: str | None) -> bool:
    """Whether an exchange now serves another file under a known filing: the file name, not the URL, since BSE moves
    an attachment from AttachLive/ to AttachHis/ under the same name. No attachment on either side is no change."""
    return bool(stored and current) and _file_name(stored) != _file_name(current)


def _noise_key(day: str, chunk: int) -> str:
    return f"noise/{day}/{chunk:03d}.json"


def _noise_row(filing: Filing) -> list:
    return [filing.news_id, filing.scrip_code, filing.company_name, filing.headline[:240], filing.category,
            filing.subcategory, filing.filed_at, (filing.reason or "")[:120], filing.pdf_url]


def _still_noise(decision, filing: Filing, row: list, returning: bool = False) -> bool:
    """Whether a filing in the noise file stays there under today's rules: dropped or a date, a shareholding
    pattern with no XBRL file, or outside the investable universe (a market-cap test, not a rule) unless the
    company is back in it (``returning``)."""
    return (decision.action in ("DROP", "CALENDAR") or (decision.action == "XBRL" and not filing.xbrl_url)
            or (not returning and str(row[7] or "").startswith("outside universe")))


# One cap for every attachment. An annual report runs to 300 pages and often past 30 MB (519552's FY26 report was
# skipped at that cap and called not material, F57), and so can a full-year results filing: NHPC's FY26 results PDF
# (nse-106633606) was skipped at 30 MB on 25 Oct 2026 and failed as "no readable text" (owner: 120 MB for all).
ATTACHMENT_MAX_BYTES = 120_000_000
def _standalone_only(metrics: list[dict], quarter: str, news_id: str) -> bool:
    """Whether every figure ``news_id`` gave memory for ``quarter`` is on the standalone basis (a standalone results card)."""
    bases = [s.get("basis") or m.get("basis") for m in metrics if m.get("period") == quarter
             for s in (m.get("sources") or [m]) if (s.get("news_id") or s.get("source_news_id")) == news_id]
    return bool(bases) and all(b == "STANDALONE" for b in bases)


ANNUAL_REPORT_MIN_PAGES = 60   # as Document.kind() reads a directors' report: an AGM notice alone runs to 10-30 pages


def _crash_site(exc: BaseException) -> str:
    """The innermost frame of our own code a crash came from, as "file.py:line in function" (owner, 25 Oct 2026: four
    crashes were stored with their message alone, so their lines had to be guessed)."""
    site = ""
    tb = exc.__traceback__
    while tb is not None:
        code = tb.tb_frame.f_code
        if "bse_intel" in code.co_filename:
            site = f"{code.co_filename.rsplit('/', 1)[-1]}:{tb.tb_lineno} in {code.co_name}"
        tb = tb.tb_next
    return site


def _attachment_missing(filing: Filing, why: str = "") -> None:
    """A listed file NSE does not serve (404), serves empty or serves cut short: wait for it within ATTACHMENT_WAIT of
    the filing, then fail for good with the reason."""
    try:
        age = now_ist() - datetime.fromisoformat(filing.filed_at)
    except (TypeError, ValueError):
        age = ATTACHMENT_WAIT
    if age < ATTACHMENT_WAIT:
        raise AttachmentNotYet(f"the file is {why or 'not on NSE yet, or empty'} ({filing.pdf_url})")
    raise NoTextAttachment(f"the file was {why or 'missing or empty on NSE'} {int(age.total_seconds() // 3600)} h after "
                           f"the filing ({filing.pdf_url})")


def _log_timing(filing: Filing, total: float, times: dict, outcome: "Outcome | None") -> None:
    """One line per filing: where its seconds went and how it ended. Never raises."""
    try:
        # stage times are exclusive (stages.stage): OCR inside the reading or a prompt's text, the packed wait inside
        # pass 2, each counted once
        order = ("download", "xbrl", "read", "ocr", "pass1", "pack_wait", "pass2", "dup_check", "checks", "sink_read",
                 "card_write", "retry_wait", "memory_write")
        parts = [f"{k} {times[k]:.0f}s" + (f" ({times.get('ocr_pages', 0):.0f} pages)" if k == "ocr" else "")
                 for k in order if times.get(k, 0.0) >= 0.5]
        other = total - sum(times.get(k, 0.0) for k in order)
        if other >= 0.5:
            parts.append(f"other {other:.0f}s")
        update = outcome.update if outcome is not None else {}
        status = update.get("status") or "ERROR"
        end = status
        if status in ("PENDING", "FAILED"):
            end += f": {str(update.get('last_error') or '')[:200]}"
        elif status == "ANALYZED":
            end += " card" if outcome.card else ""
        log.info("timing %s (%s, filed %s): %.0fs = %s -> %s", filing.news_id, filing.symbol or filing.company_name,
                 (filing.filed_at or "")[:10], total, ", ".join(parts) or "no stage over 0.5s", end)
    except Exception:  # noqa: BLE001 - a log line must never fail a filing
        pass


def _ocr_timed(read):
    """An OCR function whose pages and seconds go into the filing's timing line (OCR is lazy: it runs when a page's
    text is first wanted, inside the reading, pass 1's prompt or pass 2's)."""
    if read is None:
        return None

    def timed(png: bytes) -> str:
        stages.count("ocr_pages")
        with stages.stage("ocr"):
            return read(png)

    return timed


CALL_OCR_PAGES = 60   # owner 26 Oct 2026: scanned call transcripts and decks are read whole (local OCR, about 5 s a page)


def _call_ocr(full, local, first: int):
    """The OCR of a call transcript or deck: the usual reader (local OCR, the vision route when it reads nothing) for the
    first ``first`` pages it is asked for, local OCR alone after that, so a long scanned document costs no AI call."""
    if full is None or local is None:
        return full
    asked = [0]

    def read(png: bytes) -> str:
        asked[0] += 1
        return full(png) if asked[0] <= first else local(png)

    return read


def _attachment_cap(filing: Filing) -> int:
    return ATTACHMENT_MAX_BYTES


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
# A transcript the letter only promises is not in it: Shriram Finance's audio-link letter ("The transcript of the
# aforementioned call will be uploaded in due course") became a card (daily audit, 24 Oct 2026)
_TRANSCRIPT_LATER = re.compile(r"[^.]*\btranscripts?\b[^.]*?(?:\b(?:will|shall)\s+be\s+(?:uploaded|made\s+available|hosted|"
                               r"shared|placed|published|submitted|disseminated)|\bin\s+due\s+course)[^.]*\.?", re.I)


def is_transcript(filing) -> bool:
    """A call transcript always gets its own card (owner, 2026-10-19: "big yes", for its forward-looking statements):
    never a repeat of its results card or of the deck. Round 5: Texmaco's Q1 transcript (an order book of ₹9,923 Cr, a
    South Africa order, a plan to double revenue by 2030) was set aside as the results card "in other words". An exact
    refiling of the same transcript is still one document to duplicates.py."""
    return bool(_TRANSCRIPT.search(f"{filing.headline or ''} {filing.subject or ''}"))


def top_exit(text: str | None) -> bool:
    """Whether the text says the MD, CEO or CFO is leaving (resigning, ceasing, stepping down, removed, retiring)."""
    return bool(TOP_EXIT.search(text or ""))
# A results statement headed as the group's: "Statement of Consolidated Unaudited Financial Results", "Consolidated
# Statement of Profit and Loss", "Unaudited Consolidated Financial Results for the quarter"
CONSOLIDATED_STATEMENT = re.compile(r"\bconsolidated\s+(?:un-?audited\s+|audited\s+)?(?:financial\s+results|statement\s+of\s+"
                                    r"profit|results\s+for\s+the)|statement\s+of\s+consolidated\s+(?:un-?audited\s+|audited\s+)?"
                                    r"(?:financial\s+)?results", re.I)
RESULTS_XBRL_WAIT_MINUTES = 180   # a live NSE results filing waits this long for its XBRL (measured: 5 min - 2 h 40 min)   # owner, 2026-10-18: no cards for director / KMP changes
ONE_EVENT_ONE_CARD = ("MANAGEMENT_CHANGE", "GOVERNANCE", "LITIGATION_REGULATORY", "FUNDRAISE",
                      "RIGHTS_ISSUE", "M_AND_A", "DEBT_RATINGS", "CONCALL_PRESENTATION", "ANNUAL_REPORT")
# Types whose repeats only the word check after pass 2 catches (no extra model call before it). OTHER, measured over
# the last 600 live cards (22 Oct 2026): of 51 OTHER cards, the 0.5 word overlap marks 3 as repeats (EIEL's ₹228 Cr
# LOI typed OTHER a day after its order-win card, Urban Company's media release after its shareholders' letter, SRF's
# results press release) and no distinct one (the nearest, SMC's warrants against its NCDs, scores 0.23)
REPEAT_BY_WORDS = ("OTHER",)
UNIT_HINT = ("Convert each amount from the unit its table states: ₹ lakh ÷ 100 = ₹ Cr, ₹ million ÷ 10 = ₹ Cr, "
             "₹ thousand ÷ 10,000 = ₹ Cr; remove a figure that matches no source at any unit, rewriting its sentence "
             "so no blank is left (not \"holds ** ** stake\" or \"passed with over votes\")")


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


def publish_snapshot(sink: Sink, force: bool = True) -> bool:
    """Write the homepage's snapshot (the default feed page and the top signals) to R2. Without ``force`` it is rebuilt
    only when the day changed. A command that holds, releases or rewrites stored cards (apply-verdicts, release-pruned,
    release-reviewed, refresh-card-blocks) forces it: a card it held stayed on the homepage and the Signals page until a
    later run happened to analyse something (survey, 24 Oct 2026). True when written."""
    today = today_ist()
    start = (today - timedelta(days=SNAPSHOT_DAYS)).isoformat()
    if not force:
        try:
            current = json.loads(sink.get_object(SNAPSHOT_KEY) or b"{}")
        except Exception:
            current = {}
        if current.get("from") == start:
            return False
    try:
        cards = sink.query("snapshot_feed", [start, SNAPSHOT_PAGE])
        total = (sink.query("snapshot_count", [start]) or [{"n": len(cards)}])[0]["n"]
        # the same window as the feed and the Signals page ask for (it was 3 days, so the page showed none from days 4-7)
        signals = sink.query("snapshot_signals", [start])
        body = {"generated_at": now_iso(), "from": start, "limit": SNAPSHOT_PAGE,
                "feed": {"cards": cards, "total": total}, "signals": signals, "signals_from": start}
        sink.put_object(SNAPSHOT_KEY, json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode())
        return True
    except Exception as exc:  # the snapshot is an optimisation; the feed falls back to D1
        log.warning("snapshot not published: %s", exc)
        return False


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
        + list(exact.values()) + list(getattr(tagged, "memory_extra", None) or [])   # F166: stored, never shown
    if tagged.balance_sheet and not tagged.balance_sheet.is_empty():
        sheet = delta.balance_sheet
        if sheet is None or sheet.is_empty():
            delta.balance_sheet = tagged.balance_sheet.model_copy(deep=True)
            delta.balance_sheet.file_fields = [k for k, v in tagged.balance_sheet.model_dump().items() if v is not None]
        else:
            for key, value in tagged.balance_sheet.model_dump().items():
                if value is not None:
                    setattr(sheet, key, value)
                    sheet.file_fields = [*(sheet.file_fields or []), key]   # memory label: this field is the file's


def _company_memory(dossier: dict) -> dict:
    """Company-row fields drawn from memory: former names (searchable) and the radar summary."""
    names = [n for n in (dossier.get("identity") or {}).get("former_names") or [] if own_former_name(n, dossier)]
    # sent even when empty: a name memory no longer holds (or that a check now refuses: Vedanta's auditor) leaves the
    # company row with the summary that drops it (companies_upsert.sql)
    return {**memory_summary(dossier), "former_names_json": json.dumps(names, ensure_ascii=False)}
