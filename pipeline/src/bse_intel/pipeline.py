"""Orchestration: discovery, triage, analysis, memory.

A run spends its time budget in two phases:

1. Live: discover today's filings (and yesterday's, early in the morning),
   then process the live queue oldest-first.
2. Backfill: discover a few more historical days (from BACKFILL_START,
   oldest first, within the D1 daily write budget), then process the
   historical queue oldest-first on the bulk AI routes.

All state lives in the filings ledger, so a run can stop at any point (time
budget, quota ceiling, crash) and the next run resumes where it left off.
Filings for one company are processed sequentially in timestamp order;
different companies run in parallel.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from threading import Lock

from .ai.gateway import AIGateway, AllProvidersFailed
from .bse import BseClient, SourceBlockedError
from .dossier import latest_fundamentals, memory_ids, merge, new_dossier, results_snapshot, view_as_of
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
from .sinks.base import Sink
from .timeutil import IST, now_iso, now_ist, today_ist, utc_day

log = logging.getLogger(__name__)

TRANSIENT_WAIT_S = 60
TRANSIENT_RETRIES = 3
BATCH = 40
HISTORY_LIMIT = 200      # one company's filings fetched per page (a year rarely has more)
MAX_ORDER = 20_000       # companies in the cached backfill order


class QuotaExhausted(RuntimeError):
    pass


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
    days_discovered: list[str] = field(default_factory=list)
    stopped_reason: str | None = None

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

    @property
    def needs_review(self) -> bool:
        return self.score < DEFAULT_THRESHOLD or self.quant.mismatches > 0 or bool(self.claims)

    @property
    def issue_count(self) -> int:
        return len(self.ungrounded) + self.quant.mismatches + len(self.claims)

    def problems(self) -> list[str]:
        out = []
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
    return CardChecks(score, checked, ungrounded, quant, check_claims(card, *sources))


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
        self._quota_hit = False

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
        rows = []
        for row in self.gateway.usage_rows(utc_day(), now_iso()):
            key = (row["provider"], row["model"])
            prev = self._usage_flushed.get(key, {})
            delta = dict(row)
            for counter in ("requests", "input_tokens", "output_tokens", "failures", "rate_limited"):
                delta[counter] = row[counter] - prev.get(counter, 0)
            if any(delta[c] for c in ("requests", "failures", "rate_limited")):
                rows.append(delta)
            self._usage_flushed[key] = row
        self._exec("usage_add", rows)

    # ------------------------------------------------------------------ discovery

    def discover(self, day: date, keep_noise: bool = True) -> int:
        """Fetch one day's announcements, triage by rules, and enqueue them.

        Backfill days pass ``keep_noise=False``: filings the rules drop are counted but not
        written to the ledger. They are about 70% of all filings and each ledger row costs
        several D1 writes, so this cuts backfill discovery from weeks of write budget to days.
        """
        now = now_iso()
        today = today_ist().isoformat()
        ledger, catalysts, companies = [], [], {}
        dropped = 0
        for filing in self.bse.announcements(day):
            decision = self.rules.classify(filing)
            filing.reason = decision.reason
            if decision.action in ("DROP", "CALENDAR"):
                filing.status, filing.route = "DROPPED_RULE", "NONE"
                self.stats.dropped_rule += 1
                dropped += 1
                if decision.catalyst_date and decision.catalyst_date >= today:
                    catalysts.append({
                        "id": _catalyst_id(filing.scrip_code, decision.event_type or "BOARD_MEETING", decision.catalyst_date),
                        "scrip_code": filing.scrip_code, "company_name": filing.company_name, "symbol": filing.symbol,
                        "event_type": decision.event_type or "BOARD_MEETING", "event_date": decision.catalyst_date,
                        "description": filing.headline[:300], "source_news_id": filing.news_id, "created_at": now,
                    })
            else:
                filing.status = "PENDING"
                filing.route = decision.action
                filing.event_type = decision.event_type
                self.stats.pending_new += 1
                companies[filing.scrip_code] = {
                    "scrip_code": filing.scrip_code, "company_name": filing.company_name,
                    "symbol": filing.symbol, "updated_at": now,
                }
            if keep_noise or filing.status == "PENDING":
                ledger.append(filing.ledger_row(now))
        self.stats.discovered += len(ledger) + (0 if keep_noise else dropped)
        self._exec("companies_seen", list(companies.values()))
        self._exec("filings_discover", ledger)
        self._exec("catalysts_upsert", catalysts)
        if not keep_noise:
            self.sink.kv_set(f"noise_count:{day.isoformat()}", str(dropped), now)
        self.stats.days_discovered.append(day.isoformat())
        queued = sum(1 for r in ledger if r["status"] == "PENDING")
        log.info("discovered %s: %d filings (%d queued, %d noise)", day, queued + dropped, queued, dropped)
        return queued + dropped

    # ------------------------------------------------------------------ processing

    def process(self, day_from: str, day_to: str, deadline: float, bulk: bool, memory_complete: bool = True,
                history_first: bool = False) -> None:
        """Work the queue for a date window, oldest first, companies in parallel.

        With ``history_first`` (the live window), a company's unanalysed history is processed
        before its new filing, so the live card is written with that company's memory.
        """
        seen: set[str] = set()
        discovered_through = (self.sink.kv_get("backfill:discovered_through") or "") if history_first else ""
        while time.monotonic() < deadline and not self._quota_hit:
            rows = self.sink.pending_filings(day_from, day_to, self.settings.max_attempts, BATCH)
            rows = [r for r in rows if r["news_id"] not in seen]
            if not rows:
                return
            seen.update(r["news_id"] for r in rows)
            groups: OrderedDict[str, list[Filing]] = OrderedDict()
            for row in rows:
                groups.setdefault(row["scrip_code"], []).append(Filing.model_validate(row))
            outcomes: list[Outcome] = []
            with ThreadPoolExecutor(max_workers=max(1, self.settings.workers)) as pool:
                if history_first:
                    futures = [pool.submit(self._history_then, group, day_from, discovered_through, deadline, bulk, memory_complete)
                               for group in groups.values()]
                else:
                    futures = [pool.submit(self._process_group, group, deadline, bulk, memory_complete) for group in groups.values()]
                for future in futures:
                    outcomes.extend(future.result())
            self._commit(outcomes)

    def _history_then(self, filings: list[Filing], window_start: str, discovered_through: str, deadline: float,
                      bulk: bool, memory_complete: bool) -> list[Outcome]:
        """Pull a company's unanalysed history forward, then analyse its new filings."""
        history_to = (date.fromisoformat(window_start) - timedelta(days=1)).isoformat()
        rows = self.sink.pending_for_company(filings[0].scrip_code, self.settings.backfill_start, history_to,
                                             self.settings.max_attempts, HISTORY_LIMIT)
        history = [Filing.model_validate(r) for r in rows]
        results = self._process_group(history, deadline, bulk=True, memory_complete=True)
        finished = len(results) == len(history) and all(o.update.get("status") != "PENDING" for o in results)
        complete = memory_complete or (finished and len(rows) < HISTORY_LIMIT and discovered_through >= history_to)
        return results + self._process_group(filings, deadline, bulk, complete)

    def _process_group(self, filings: list[Filing], deadline: float, bulk: bool, memory_complete: bool) -> list[Outcome]:
        results = []
        for filing in sorted(filings, key=lambda f: f.filed_at):
            if time.monotonic() >= deadline or self._quota_hit:
                break
            results.append(self._process_one(filing, bulk, memory_complete))
        return results

    def _process_one(self, filing: Filing, bulk: bool, memory_complete: bool) -> Outcome:
        for attempt in range(TRANSIENT_RETRIES + 1):
            try:
                return self.analyze(filing, bulk, memory_complete)
            except AllProvidersFailed as exc:
                if exc.quota_exhausted:
                    self._quota_hit = True
                    with self._lock:
                        self.stats.deferred += 1
                        self.stats.stopped_reason = "AI quota ceilings reached; work stays queued"
                    log.warning("quota ceilings reached; leaving %s queued: %s", filing.news_id, exc)
                    return Outcome({"news_id": filing.news_id, "status": "PENDING", "updated_at": now_iso(),
                                    "last_error": "deferred: AI quota ceilings"})
                if exc.transient and attempt < TRANSIENT_RETRIES:
                    log.info("all providers busy for %s; waiting %ds", filing.news_id, TRANSIENT_WAIT_S)
                    self._sleep(TRANSIENT_WAIT_S)
                    continue
                if exc.transient:
                    with self._lock:
                        self.stats.deferred += 1
                    return Outcome({"news_id": filing.news_id, "status": "PENDING", "updated_at": now_iso(),
                                    "last_error": "deferred: providers busy"})
                return self._failed(filing, exc)
            except SourceBlockedError:
                raise
            except Exception as exc:  # one bad filing must not stop the run
                log.exception("filing %s failed", filing.news_id)
                return self._failed(filing, exc)
        return self._failed(filing, RuntimeError("retries exhausted"))

    def _failed(self, filing: Filing, exc: Exception) -> Outcome:
        with self._lock:
            self.stats.failed += 1
        return Outcome({"news_id": filing.news_id, "status": "FAILED", "attempt_inc": 1,
                        "last_error": f"{type(exc).__name__}: {exc}"[:500], "updated_at": now_iso()})

    def analyze(self, filing: Filing, bulk: bool = False, memory_complete: bool = True) -> Outcome:
        """Run Pass 1 (if needed), extraction, Pass 2, grounding, merge and signals for one filing."""
        company = self.sink.company(filing.scrip_code) or {}
        industry = company.get("industry")
        pdf = self.bse.download(filing.pdf_url) if filing.pdf_url else None
        ocr = self.gateway.transcribe_image if self.gateway.has_route("vision") else None
        doc = Document(pdf, ocr=ocr, max_ocr_pages=self.settings.max_ocr_pages)
        try:
            return self._analyze_document(filing, company, industry, doc, bulk, memory_complete)
        finally:
            with self._lock:
                self.stats.ocr_pages += doc.ocr_pages_used
            doc.close()

    def _analyze_document(self, filing, company, industry, doc: Document, bulk: bool, memory_complete: bool) -> Outcome:
        now = now_iso()
        event_type = filing.event_type or "OTHER"
        if filing.route == "PASS1":
            system, user = self.prompts.pass1(filing, doc.first_page_text())
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
        event_type = out.event_type
        card = out.card
        score, checked, ungrounded, quant, claims = checks.score, checks.checked, checks.ungrounded, checks.quant, checks.claims

        merged = merge(dossier, out, filing, card.impact_level, now)
        merged.update({k: v for k, v in (("industry", industry), ("sector", sector), ("symbol", company.get("symbol") or filing.symbol)) if v})
        signals = compute_signals(dossier, merged, out, filing, company)
        self.sink.put_dossier(filing.scrip_code, merged)

        card_json = {
            "category_tag": EVENT_TAGS.get(event_type, "UPDATE"),
            "event_type": event_type,
            **card.model_dump(),
            "quantified_impact": quant.items,
            "signals": signals,
            "timeline_entry": out.timeline_entry,
            "fundamentals": latest_fundamentals(merged, sector_module.footer),
            "results": results_snapshot(merged, filing.news_id) if event_type == "RESULTS" else None,
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
            "model": result.model_label, "created_at": now,
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
        with self._lock:
            self.stats.second_opinions += 1
        system2, user2 = self.prompts.verify(system, user, out.model_dump(mode="json"), problems)
        try:
            second = self.gateway.complete_json(route, system2, user2, Pass2Output, avoid_providers=(result.provider,))
        except AllProvidersFailed as exc:
            return out, result, checks, {**base, "status": "UNCHECKED", "note": str(exc)[:200]}
        fixed: Pass2Output = second.value
        if not fixed.is_material or fixed.card is None:
            return out, result, checks, {**base, "status": "UNRESOLVED", "checked_by": second.model_label}
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
        self._exec("companies_upsert", [o.company for o in outcomes if o.company])
        cards = [o.card for o in outcomes if o.card]
        self._exec("cards_upsert", cards)
        self._archive_cards(cards)
        self._exec("catalysts_upsert", [c for o in outcomes for c in o.catalysts])
        self._exec("filings_update", [o.update for o in outcomes])
        self._flush_usage()

    # ------------------------------------------------------------------ runs

    def _writes_today(self) -> int:
        try:
            return int(self.sink.kv_get(f"d1_writes:{utc_day()}") or 0)
        except ValueError:
            return 0

    def run(self, mode: str = "all", time_budget_s: int = 2400, max_backfill_days: int = 5) -> Stats:
        started = time.monotonic()
        deadline = started + time_budget_s
        run_id = f"{now_ist():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
        writes_at_start = self._writes_today()
        run_row = {"run_id": run_id, "mode": mode, "started_at": now_iso(), "status": "RUNNING"}
        self._exec("runs_upsert", [run_row])
        status, error = "OK", None
        try:
            today = today_ist()
            if mode in ("live", "all"):
                days = [today - timedelta(days=1), today] if now_ist().hour < 9 else [today]
                for day in days:
                    self.discover(day)
                live_deadline = deadline if mode == "live" else started + time_budget_s * 0.6
                backfill_done = self.sink.kv_get("backfill:complete") == "1"
                self.process(days[0].isoformat(), today.isoformat(), live_deadline, bulk=False,
                             memory_complete=backfill_done, history_first=not backfill_done)
            if mode in ("backfill", "all") and not self._quota_hit:
                self._backfill(today, deadline, writes_at_start, max_backfill_days)
        except SourceBlockedError as exc:
            status, error = "ERROR", str(exc)
            self.stats.stopped_reason = "BSE blocked the request"
            log.error("%s", exc)
        except Exception as exc:
            status, error = "ERROR", f"{type(exc).__name__}: {exc}"
            log.exception("run failed")
        finally:
            if status == "OK" and (self._quota_hit or self.stats.failed):
                status = "PARTIAL"
            try:
                self._flush_usage()
                self.sink.kv_set(f"d1_writes:{utc_day()}", str(writes_at_start + self.stats.d1_rows_written), now_iso())
                self._exec("runs_upsert", [dict(run_row, finished_at=now_iso(), status=status,
                                                stats=self.stats.as_dict(), error=error)])
            except Exception:
                log.exception("could not record run")
        log.info("run %s finished: %s %s", run_id, status, json.dumps(self.stats.as_dict()))
        return self.stats

    def _backfill(self, today: date, deadline: float, writes_at_start: int, max_days: int) -> None:
        start = date.fromisoformat(self.settings.backfill_start)
        yesterday = today - timedelta(days=1)
        cursor_raw = self.sink.kv_get("backfill:discovered_through")
        cursor = date.fromisoformat(cursor_raw) if cursor_raw else start - timedelta(days=1)
        budget = self.settings.d1_daily_write_budget
        days = 0
        while cursor < yesterday and days < max_days and time.monotonic() < deadline:
            if writes_at_start + self.stats.d1_rows_written >= budget:
                self.stats.stopped_reason = f"D1 daily write budget ({budget}) reached; backfill discovery paused"
                break
            cursor += timedelta(days=1)
            self.discover(cursor, keep_noise=False)
            self.sink.kv_set("backfill:discovered_through", cursor.isoformat(), now_iso())
            days += 1
        self._backfill_companies(start.isoformat(), yesterday.isoformat(), cursor.isoformat(), deadline)
        if cursor >= yesterday and not self.sink.pending_filings(start.isoformat(), yesterday.isoformat(),
                                                                 self.settings.max_attempts, 1):
            self.sink.kv_set("backfill:complete", "1", now_iso())


    def _backfill_companies(self, day_from: str, day_to: str, through: str, deadline: float) -> None:
        """Analyse history company by company, largest market cap first, each in date order.

        A company's memory is then complete in one go, and the AI quota reaches the companies
        investors follow before the long tail. The order is computed at most once a day (or when
        discovery has moved on) and the unfinished remainder is kept in kv between runs.
        """
        raw = self.sink.kv_get("backfill:company_order")
        state = json.loads(raw) if raw else {}
        built = today_ist().isoformat()
        if not state.get("scrips") or state.get("built") != built or state.get("through") != through:
            rows = self.sink.query("backfill_companies", [day_from, day_to, self.settings.max_attempts, MAX_ORDER])
            state = {"built": built, "through": through, "scrips": [r["scrip_code"] for r in rows]}
        order: list[str] = state["scrips"]
        width = max(1, self.settings.workers) * 2
        tried: set[str] = set()  # a filing that fails is retried on a later run, not straight away
        while order and time.monotonic() < deadline and not self._quota_hit:
            batch, order = order[:width], order[width:]
            queues = {s: [f for f in (Filing.model_validate(r) for r in
                                      self.sink.pending_for_company(s, day_from, day_to, self.settings.max_attempts, HISTORY_LIMIT))
                          if f.news_id not in tried]
                      for s in batch}
            tried.update(f.news_id for q in queues.values() for f in q)
            outcomes: list[Outcome] = []
            with ThreadPoolExecutor(max_workers=max(1, self.settings.workers)) as pool:
                futures = {s: pool.submit(self._process_group, q, deadline, True, True) for s, q in queues.items() if q}
                results = {s: f.result() for s, f in futures.items()}
            unfinished = []
            for s, q in queues.items():
                done = results.get(s, [])
                outcomes.extend(done)
                cut_short = len(done) < len(q) or any(o.update.get("status") == "PENDING" for o in done)
                if q and (cut_short or len(q) >= HISTORY_LIMIT):
                    unfinished.append(s)  # stopped early, or has more than one page of history
            self._commit(outcomes)
            order = unfinished + order
        self.sink.kv_set("backfill:company_order", json.dumps({**state, "scrips": order}), now_iso())


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
