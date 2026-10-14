"""Orchestration: discovery, triage, analysis, memory, distribution.

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
from .dossier import latest_fundamentals, memory_ids, merge, new_dossier, view_as_of
from .extract import Document
from .grounding import DEFAULT_THRESHOLD, check_card
from .models import EVENT_TAGS, Filing, Pass1Result, Pass2Output
from .periods import due_date
from .prompts.engine import PromptEngine
from .quant import check as check_quant
from .rules import RuleBook
from .settings import Settings
from .signals import compute as compute_signals
from .sinks.base import Sink
from .telegram import TelegramNotifier
from .timeutil import IST, now_iso, now_ist, today_ist, utc_day

log = logging.getLogger(__name__)

TRANSIENT_WAIT_S = 60
TRANSIENT_RETRIES = 3
NOTIFY_MAX_AGE = timedelta(hours=18)
BATCH = 40


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
    notified: int = 0
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
    notify: bool = False


def _catalyst_id(scrip: str, event_type: str, event_date: str) -> str:
    return hashlib.sha1(f"{scrip}|{event_type}|{event_date}".encode()).hexdigest()[:16]


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        sink: Sink,
        gateway: AIGateway,
        bse: BseClient | None = None,
        notifier: TelegramNotifier | None = None,
        prompts: PromptEngine | None = None,
        rules: RuleBook | None = None,
        sleep=time.sleep,
    ):
        self.settings = settings
        self.sink = sink
        self.gateway = gateway
        self.bse = bse or BseClient()
        self.notifier = notifier or TelegramNotifier(None, None, settings.site_url)
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

    def discover(self, day: date) -> int:
        """Fetch one day's announcements, triage by rules, and enqueue them."""
        now = now_iso()
        ledger, catalysts, companies = [], [], {}
        for filing in self.bse.announcements(day):
            decision = self.rules.classify(filing)
            filing.reason = decision.reason
            if decision.action in ("DROP", "CALENDAR"):
                filing.status, filing.route = "DROPPED_RULE", "NONE"
                self.stats.dropped_rule += 1
                if decision.catalyst_date:
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
            ledger.append(filing.ledger_row(now))
        self.stats.discovered += len(ledger)
        self._exec("companies_seen", list(companies.values()))
        self._exec("filings_discover", ledger)
        self._exec("catalysts_upsert", catalysts)
        self.stats.days_discovered.append(day.isoformat())
        log.info("discovered %s: %d filings (%d queued)", day, len(ledger), sum(1 for r in ledger if r["status"] == "PENDING"))
        return len(ledger)

    # ------------------------------------------------------------------ processing

    def process(self, day_from: str, day_to: str, deadline: float, bulk: bool, memory_complete: bool = True) -> None:
        seen: set[str] = set()
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
                futures = [pool.submit(self._process_group, group, deadline, bulk, memory_complete) for group in groups.values()]
                for future in futures:
                    outcomes.extend(future.result())
            self._commit(outcomes)

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
        sector = self.prompts.sector_for(industry).name
        peers = self._peers(sector, event_type, filing)
        system, user = self.prompts.pass2(filing, event_type, industry, view, text, peers)
        result = self.gateway.complete_json("pass2_bulk" if bulk else "pass2", system, user, Pass2Output)
        out: Pass2Output = result.value
        if not out.is_material or out.card is None:
            with self._lock:
                self.stats.not_material += 1
            return Outcome({"news_id": filing.news_id, "status": "NOT_MATERIAL", "event_type": out.event_type,
                            "reason": "pass2: not material", "updated_at": now})
        if filing.route == "FAST_TRACK" and filing.event_type:
            out.event_type = filing.event_type  # rules know the event type better than the model
        event_type = out.event_type

        card = out.card
        valid_refs = memory_ids(view)
        for insight in card.why_it_matters:
            insight.memory_refs = [r for r in insight.memory_refs if r in valid_refs]
        sources = (text, filing.headline, filing.subject, json.dumps(view or {}, ensure_ascii=False))
        grounding = check_card(card, *sources)
        quant = check_quant(card.quantified_impact, *sources)
        checked = grounding.checked + quant.checked_inputs
        ungrounded = grounding.ungrounded + quant.unsourced
        score = 1.0 if checked == 0 else round(1 - len(ungrounded) / checked, 3)

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
            "fundamentals": latest_fundamentals(merged),
            "pdf_pages": doc.page_count or None,
            "grounding": {"score": score, "checked": checked, "ungrounded": ungrounded[:10],
                          "math_mismatches": quant.mismatches},
            "model": result.model_label,
        }
        needs_review = score < DEFAULT_THRESHOLD or quant.mismatches > 0
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
        filed = datetime.fromisoformat(filing.filed_at)
        fresh = now_ist() - filed <= NOTIFY_MAX_AGE
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
            notify=card.impact_level == "HIGH" and not needs_review and not bulk and fresh,
        )

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
        for o in outcomes:
            if o.notify and o.card and self.notifier.send(o.card, o.card["card"]):
                self.stats.notified += 1

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
                             memory_complete=backfill_done)
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
            self.discover(cursor)
            self.sink.kv_set("backfill:discovered_through", cursor.isoformat(), now_iso())
            days += 1
        self.process(start.isoformat(), yesterday.isoformat(), deadline, bulk=True, memory_complete=True)
        if cursor >= yesterday and not self.sink.pending_filings(start.isoformat(), yesterday.isoformat(),
                                                                 self.settings.max_attempts, 1):
            self.sink.kv_set("backfill:complete", "1", now_iso())


def build_pipeline(settings: Settings, sink: Sink) -> Pipeline:
    month = utc_day()[:7]
    try:
        usage_today, usage_month = sink.usage(utc_day()), sink.usage_month(month)
    except Exception as exc:
        log.warning("could not load AI usage; starting counters at zero: %s", exc)
        usage_today, usage_month = [], []
    gateway = AIGateway(settings.load_toml("providers.toml"), usage_today=usage_today, usage_month=usage_month)
    notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id, settings.site_url)
    return Pipeline(settings, sink, gateway, notifier=notifier)


__all__ = ["Pipeline", "Stats", "build_pipeline", "IST"]
