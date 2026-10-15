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
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import partial
from threading import Lock

from .ai.gateway import AIGateway, AllProvidersFailed
from .bse import AttachmentError, BseClient, SourceBlockedError
from .dossier import dossier_as_of, latest_fundamentals, memory_ids, merge, new_dossier, results_snapshot, view_as_of
from .extract import Document
from .grounding import DEFAULT_THRESHOLD, check_card, check_claims
from .models import EVENT_TAGS, Filing, Pass1Result, Pass2Output
from .periods import due_date
from .prompts.engine import PromptEngine
from .quant import QuantCheck
from .quant import check as check_quant
from .rules import RuleBook
from .settings import Settings
from .signals import compute as compute_signals
from .sinks.base import Sink, SinkRejected
from . import universe
from .timeutil import IST, market_session, now_iso, now_ist, today_ist, utc_day

log = logging.getLogger(__name__)

TRANSIENT_WAIT_S = 60
TRANSIENT_RETRIES = 3
BATCH = 40
HISTORY_LIMIT = 200      # one company's filings fetched per page (a year rarely has more)
HISTORY_INLINE = 30      # history analysed ahead of a live filing; a longer backlog goes to the backfill
MAX_ORDER = 20_000       # companies in the cached backfill order
LIVE_DAYS = 7            # an unfinished filing stays in the live window this long
DEADLINE_GRACE_S = 240   # a filing started before the deadline may finish within this
MAX_REFUSALS = 3         # attachment 403s in a row that mean BSE is refusing this network
NOISE_CHUNK = 500        # rows per noise-audit file in R2
NOISE_FIELDS = ("news_id", "scrip_code", "company_name", "headline", "category", "subcategory",
                "filed_at", "reason", "pdf_url")
DONE = ("ANALYZED", "NOT_MATERIAL")


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
    second_opinions: int = 0
    corrected: int = 0
    ocr_pages: int = 0
    d1_rows_written: int = 0
    discovery_errors: int = 0
    outside_universe: int = 0
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


@dataclass
class CardChecks:
    """Everything the automatic checks found on one card."""

    score: float
    checked: int
    ungrounded: list[str]
    quant: QuantCheck
    claims: list[str]
    headline_ungrounded: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        # Blueprint rule: an unmatched ₹ figure in the headline or a failed math check holds the card;
        # so do a low overall match rate and an unsupported "first"/"record" claim.
        return (self.score < DEFAULT_THRESHOLD or self.quant.mismatches > 0 or bool(self.claims)
                or bool(self.headline_ungrounded))

    @property
    def issue_count(self) -> int:
        return len(self.ungrounded) + self.quant.mismatches + len(self.claims)

    def problems(self) -> list[str]:
        out = []
        if self.headline_ungrounded:
            out.append("Headline figures not found in the filing or company memory: " + ", ".join(self.headline_ungrounded))
        if self.ungrounded:
            out.append("Numbers not found in the filing text or company memory: " + ", ".join(self.ungrounded[:10]))
        out += [f"Quantified impact \"{q['label']}\": {q.get('check_note')}" for q in self.quant.items if q.get("check") == "MISMATCH"]
        out += [f"Claim not supported by the sources: \"{c}\"" for c in self.claims]
        return out


def check_card_all(card, view: dict | None, sources: tuple[str, ...]) -> CardChecks:
    """Memory-id hygiene, then the number, math and claim checks."""
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
    return CardChecks(score, checked, ungrounded, quant, check_claims(card, *sources), grounding.headline_ungrounded)


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
        self._blocked: SourceBlockedError | None = None
        self._usage_lock = Lock()
        self._universe: tuple[set[str], float] | None = None

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
        now = now_iso()
        today = today_ist().isoformat()
        key = day.isoformat()
        noise = self._load_noise(key)
        noise_before = len(noise)
        known = self.sink.known_ids(key) | set(noise)
        ledger, catalysts, companies = [], [], {}
        for filing in self.bse.announcements(day, known=None if full else known):
            if filing.news_id in known:
                continue
            known.add(filing.news_id)
            decision = self.rules.classify(filing)
            filing.reason = decision.reason
            if decision.action in ("DROP", "CALENDAR"):
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
        self.stats.days_discovered.append(key)
        log.info("discovered %s: %d new filings (%d queued, %d noise)", day, len(ledger) + new_noise, len(ledger), new_noise)
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
        """Run one job per company in parallel and commit each company's results as it finishes, so
        a timeout or a crash loses at most the filings still in flight."""
        done: dict[str, list[Outcome]] = {}
        if not jobs:
            return done
        with ThreadPoolExecutor(max_workers=max(1, self.settings.workers)) as pool:
            futures = {pool.submit(job): key for key, job in jobs.items()}
            for future in as_completed(futures):
                outcomes = future.result()
                done[futures[future]] = outcomes
                self._commit(outcomes)
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
        return results

    def _halted(self, bulk: bool) -> bool:
        """The analyst route for this phase has hit its quota ceilings: work stays queued."""
        return ("pass2_bulk" if bulk else "pass2") in self._exhausted

    def _process_one(self, filing: Filing, bulk: bool, memory_complete: bool, deadline: float | None = None) -> Outcome:
        pass1 = "pass1_bulk" if bulk else "pass1"
        if filing.route == "PASS1" and pass1 in self._exhausted:
            return self._deferred(filing, "deferred: AI quota ceilings")
        for attempt in range(TRANSIENT_RETRIES + 1):
            try:
                return self.analyze(filing, bulk, memory_complete)
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
            return self._analyze_document(filing, company, industry, doc, bulk, memory_complete)
        finally:
            with self._lock:
                self.stats.ocr_pages += doc.ocr_pages_used
            if doc.ocr_error is None:
                self._cache_text(filing.news_id, doc)
            doc.close()

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
        sector_module = self.prompts.sector_for(industry)
        sector = sector_module.name
        peers = self._peers(sector, event_type, filing)
        system, user = self.prompts.pass2(filing, event_type, industry, view, text, peers)
        route = "pass2_bulk" if bulk else "pass2"
        result = self.gateway.complete_json(route, system, user, Pass2Output)
        out: Pass2Output = result.value
        if not out.is_material or out.card is None:
            with self._lock:
                self.stats.not_material += 1
            return Outcome({"news_id": filing.news_id, "status": "NOT_MATERIAL", "event_type": out.event_type,
                            "reason": "pass2: not material", "updated_at": now})
        sources = (text, filing.headline, filing.subject, json.dumps(view or {}, ensure_ascii=False))
        checks = check_card_all(out.card, view, sources)
        review = None
        if checks.needs_review and self.settings.second_opinion:
            out, result, checks, review = self._second_opinion(route, system, user, out, result, checks, view, sources)
        if filing.route == "FAST_TRACK" and filing.event_type:
            out.event_type = filing.event_type  # rules know the event type better than the model
        elif out.event_type == "OTHER" and event_type != "OTHER":
            out.event_type = event_type  # Pass 2 left it open; Pass 1 had decided
        if out.card is not None and out.event_type != "CONCALL_PRESENTATION":
            out.card.call_read = None  # guidance, tone and transparency describe a call, not other filings
        event_type = out.event_type
        card = out.card
        score, checked, ungrounded, quant, claims = checks.score, checks.checked, checks.ungrounded, checks.quant, checks.claims

        merged = merge(dossier, out, filing, card.impact_level, now)
        merged.update({k: v for k, v in (("industry", industry), ("sector", sector), ("symbol", company.get("symbol") or filing.symbol)) if v})
        # Signals, footer and results table see memory as it stood at this filing, not later facts
        # that a backfill may already have stored.
        before = dossier_as_of(dossier, filing.filed_at, inclusive=False)
        current = dossier_as_of(merged, filing.filed_at)
        signals = compute_signals(before, current, out, filing, company)
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
            "pdf_pages": doc.page_count or None,
            "grounding": {"score": score, "checked": checked, "ungrounded": ungrounded[:10],
                          "math_mismatches": quant.mismatches, "unsupported_claims": claims},
            "review": review,
            "model": result.model_label,
        }
        needs_review = checks.needs_review
        row = {
            "news_id": filing.news_id, "scrip_code": filing.scrip_code,
            "symbol": company.get("symbol") or filing.symbol, "company_name": filing.company_name,
            "filing_date": filing.filing_date, "filed_at": filing.filed_at, "sector": sector,
            "event_category": event_type, "impact_level": card.impact_level, "headline": card.headline,
            "grounding_score": score, "needs_review": int(needs_review),
            "memory_complete": int(memory_complete), "card": card_json, "pdf_url": filing.pdf_url,
            "model": result.model_label, "created_at": now, "market_session": market_session(filing.filed_at),
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
            self.stats.cards_high += card.impact_level == "HIGH"
            self.stats.needs_review += needs_review
        return Outcome(
            update={"news_id": filing.news_id, "status": "ANALYZED", "event_type": event_type,
                    "reason": None, "last_error": None, "updated_at": now},
            card=row,
            catalysts=catalysts,
            company={"scrip_code": filing.scrip_code, "company_name": filing.company_name,
                     "symbol": row["symbol"], "sector": sector, "updated_at": now},
        )

    def _second_opinion(self, route, system, user, out: Pass2Output, result, checks: CardChecks, view, sources):
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
        system2, user2 = self.prompts.verify(system, user, out.model_dump(mode="json"), problems)
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
        checks2 = check_card_all(fixed.card, view, sources)
        if not checks2.needs_review:
            with self._lock:
                self.stats.corrected += 1
            return fixed, second, checks2, {**base, "status": "CORRECTED", "checked_by": second.model_label, "issues": [],
                                            "fixed": problems}
        if checks2.issue_count < checks.issue_count:
            return fixed, second, checks2, {**base, "status": "UNRESOLVED", "checked_by": second.model_label,
                                            "issues": checks2.problems()}
        return out, result, checks, {**base, "status": "UNRESOLVED", "checked_by": second.model_label}

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
                # Read-modify-write under the current UTC day, so a run that crosses midnight does
                # not carry yesterday's total into the new day.
                self.sink.add_writes(utc_day(), self.stats.d1_rows_written, now_iso())
            except Exception:
                log.exception("could not record run")
        log.info("run %s finished: %s %s", run_id, status, json.dumps(self.stats.as_dict()))
        return self.stats

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
