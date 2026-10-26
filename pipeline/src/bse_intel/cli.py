"""Command-line entry point: ``python -m bse_intel <command>``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from . import raw
from .settings import get_settings
from .sinks import make_sink
from .timeutil import now_iso, today_ist, utc_day

# The exit code of a command NSE (or BSE) refused (401/403/429), apart from 2, which argparse and an AI error also
# give: scripts/retry.sh never retries a refusal and skips the job's later NSE steps (survey review, 24 Oct 2026)
REFUSED = 75


def _pipeline(settings, sink):
    from .pipeline import build_pipeline

    return build_pipeline(settings, sink)


def cmd_run(args, settings, sink) -> int:
    from . import pause

    until = pause.paused_until(sink)
    if until:   # the nightly memory jobs are writing memory (pause.py); the work stays queued for the next run
        print(json.dumps({"skipped": f"paused for the nightly memory jobs until {until:%H:%M} IST"}))
        return 0
    stats = _pipeline(settings, sink).run(args.mode, args.time_budget, args.max_backfill_days)
    print(json.dumps(stats.as_dict(), indent=2))
    return 0 if stats.status in ("OK", "PARTIAL") else 1  # a run ending in ERROR fails the workflow


def _cards_changed(sink, written: int) -> None:
    """Stored cards were held, released or rewritten: the homepage snapshot is rebuilt now, not at the next run that
    happens to analyse a filing (a card held here stayed on the homepage and Signals page until then)."""
    if written:
        from .pipeline import publish_snapshot

        publish_snapshot(sink)


def cmd_release_pruned(args, settings, sink) -> int:
    """Held cards whose only faults were points their quote did not carry, published without those points (prune.py)."""
    from . import prune

    report = prune.release(sink, dry_run=args.dry_run)
    _cards_changed(sink, 0 if args.dry_run else report.get("rows_written", 0))
    print(json.dumps({k: v for k, v in report.items() if k != "cards"} | {"cards": report["cards"][:50]}, ensure_ascii=False))
    return 0


def cmd_release_reviewed(args, settings, sink) -> int:
    """Held cards a blind review cleared, published without the whole points it named (prune.release_reviewed)."""
    from pathlib import Path

    from . import prune

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    report = prune.release_reviewed(sink, plan, Path(args.plan).stem, dry_run=args.dry_run)
    _cards_changed(sink, 0 if args.dry_run else report.get("rows_written", 0))
    print(json.dumps(report, ensure_ascii=False))
    return 0


def cmd_pause_ai(args, settings, sink) -> int:
    """No live run starts, and a running one stops between filings, until the pause ends (pause.py)."""
    from . import pause

    print(json.dumps({"paused_until": pause.pause(sink, args.minutes).isoformat(timespec="seconds")}))
    return 0


def cmd_resume_ai(args, settings, sink) -> int:
    from . import pause

    pause.resume(sink)
    print(json.dumps({"paused_until": None}))
    return 0


def cmd_backfill_companies(args, settings, sink) -> int:
    scrips = [s.strip() for s in args.scrips.split(",") if s.strip()]
    stats = _pipeline(settings, sink).backfill_companies(
        scrips, date.fromisoformat(args.date_from or settings.backfill_start),
        date.fromisoformat(args.date_to) if args.date_to else today_ist(), args.time_budget)
    print(json.dumps(stats.as_dict(), indent=2))
    return 0 if stats.status in ("OK", "PARTIAL") else 1


def cmd_sync_to_cloud(args, settings, sink) -> int:
    """Copy the laptop's local data to the deployed platform (see sync.py)."""
    from .sinks.local import LocalSink
    from .sinks.platform import PlatformSink
    from .sync import Sync

    if args.source == "local-sink":
        source = LocalSink(settings)
    else:
        source = PlatformSink(args.source, args.source_token)
    dest = PlatformSink(settings.platform_url or "", settings.ingest_token or "")
    progress = Path(args.progress or (settings.local_dir.parent / "sync_progress.json"))
    result = Sync(source, dest, progress, settings.d1_daily_write_budget).run()
    print(json.dumps(result, indent=2))
    return 0


def cmd_retriage(args, settings, sink) -> int:
    pipeline = _pipeline(settings, sink)
    day_from = date.fromisoformat(args.date_from or settings.backfill_start)
    day_to = date.fromisoformat(args.date_to) if args.date_to else today_ist()
    queued = {scrip: pipeline.retriage_company(scrip, day_from, day_to)
              for scrip in (s.strip() for s in args.scrips.split(",")) if scrip}
    print(json.dumps({"queued": queued, "count": sum(len(v) for v in queued.values())}, indent=2))
    return 0


def cmd_discover(args, settings, sink) -> int:
    pipeline = _pipeline(settings, sink)
    count = pipeline.discover(date.fromisoformat(args.date))
    print(json.dumps({"discovered": count, **pipeline.stats.as_dict()}, indent=2))
    return 0


def cmd_process(args, settings, sink) -> int:
    pipeline = _pipeline(settings, sink)
    only = None
    if args.news_ids:
        text = Path(args.news_ids[1:]).read_text() if args.news_ids.startswith("@") else args.news_ids
        only = {part.strip() for part in text.replace(",", " ").split() if part.strip()}
        print(f"{len(only)} filings only")
    pipeline.process(args.date_from, args.date_to, time.monotonic() + args.time_budget, bulk=args.bulk, only=only)
    print(json.dumps(pipeline.stats.as_dict(), indent=2))
    return 0


def cmd_annual_xbrl_catchup(args, settings, sink) -> int:
    """Annual reports read again once NSE lists their XBRL (annual_catchup.py). Exit 3: another run is going on."""
    from . import annual_catchup

    busy = annual_catchup.wait_for_quiet(settings.log_dir, args.wait * 60)
    if busy:
        print(json.dumps({"skipped": "another run on this machine may be calling NSE or writing", "busy": busy}, indent=2))
        return 3
    scrips = {s.strip() for s in (args.scrips or "").split(",") if s.strip()} or None
    report = annual_catchup.catch_up(_pipeline(settings, sink), time.monotonic() + args.time_budget,
                                     horizon_days=args.days, every_days=args.every, max_companies=args.max_companies,
                                     max_reruns=args.max_reruns, scrips=scrips)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return REFUSED if (report["stopped"] or "").startswith("NSE refused") else 0


def cmd_analyze_pdf(args, settings, sink) -> int:
    """Analyse a local PDF end to end (no BSE access needed): prints the card."""
    from .models import Filing
    from .timeutil import now_ist

    pipeline = _pipeline(settings, sink)
    filed = now_ist()
    filing = Filing(
        news_id=args.news_id or f"local-{int(time.time())}",
        scrip_code=args.scrip, company_name=args.company, headline=args.headline,
        subject=args.headline, category=args.category or "", subcategory=args.subcategory or "",
        filed_at=filed.isoformat(timespec="seconds"), filing_date=filed.date().isoformat(),
        route="FAST_TRACK" if args.event_type else "PASS1", event_type=args.event_type,
    )
    if args.industry:
        sink.execute("companies_upsert", [{"scrip_code": args.scrip, "company_name": args.company,
                                           "industry": args.industry, "updated_at": now_iso()}])
    pipeline.bse.download = lambda url, **_: Path(args.pdf).read_bytes()  # type: ignore[method-assign]  # max_bytes too
    filing.pdf_url = f"file://{Path(args.pdf).resolve()}"
    outcome = pipeline.analyze(filing)
    pipeline._commit([outcome])
    print(json.dumps({"status": outcome.update, "card": outcome.card, "catalysts": outcome.catalysts},
                     indent=2, ensure_ascii=False))
    return 0


def cmd_market_data(args, settings, sink) -> int:
    from .market import enrich

    from . import universe

    updated = enrich(settings, sink, all_companies=args.all)
    coverage = json.loads(sink.kv_get("market:coverage") or "{}")
    print(json.dumps({"companies_updated": updated, "outside_universe": universe.rebuild(settings, sink),
                      "yahoo_missing": coverage.get("missing"), "yahoo_missing_pct": coverage.get("missing_pct"),
                      "missing_sample": [m["scrip_code"] for m in coverage.get("sample", [])[:30]]}))
    return 0


SYNC_COMPANIES_BATCH = 200  # rows per write, so a stopped industry lookup keeps what it found
MAX_LOOKUP_FAILURES = 10    # consecutive header failures before the lookups stop for this run


def _stored_companies(sink) -> dict[str, str | None]:
    """scrip code -> stored industry, for every company already in the database."""
    stored: dict[str, str | None] = {}
    after = ""
    while True:
        page = sink.query("export_companies", [after, 1000])
        if not page:
            return stored
        stored.update({r["scrip_code"]: r.get("industry") for r in page})
        after = page[-1]["scrip_code"]


def cmd_sync_companies(args, settings, sink) -> int:
    if args.source == "nse":
        return _sync_companies_nse(settings, sink)
    import httpx

    from .bse import BseClient, fetch_scrip_list, industry_path
    from .market import size_bucket
    from .prompts.engine import PromptEngine

    log = logging.getLogger("bse_intel.sync_companies")
    engine = PromptEngine(settings)
    buckets = settings.load_toml("market.toml")["size_buckets"]
    stored = _stored_companies(sink)
    written = looked_up = failures = 0
    now = now_iso()
    with BseClient() as client:
        raw.attach(client, sink, "bse", settings)
        rows = fetch_scrip_list(client)
        for at in range(0, len(rows), SYNC_COMPANIES_BATCH):
            batch = rows[at:at + SYNC_COMPANIES_BATCH]
            for row in batch:
                scrip = row["scrip_code"]
                industry = row.get("industry") or (None if args.refresh_industry else stored.get(scrip))
                if not industry and failures < MAX_LOOKUP_FAILURES and looked_up < args.max_lookups:
                    looked_up += 1
                    try:
                        industry = industry_path(client.scrip_header(scrip))
                        failures = 0
                    except (httpx.HTTPError, ValueError) as exc:
                        failures += 1
                        log.warning("industry lookup failed for %s: %s", scrip, exc)
                row["industry"] = industry or stored.get(scrip)
                if row["industry"]:
                    row["sector"] = engine.sector_for(row["industry"]).name
                elif scrip not in stored:
                    row["sector"] = "default"  # new and unclassified; a stored sector is never overwritten
                # BSE's list carries a market cap (₹ Cr) for companies Yahoo cannot price; label it
                # too, or the size filters and the score never see those companies.
                row["size_category"] = size_bucket(row.get("market_cap_cr"), buckets)
                row["updated_at"] = now
            written += sink.execute("companies_upsert", batch)
            if looked_up:
                log.info("sync-companies: %d/%d companies, %d industry lookups", at + len(batch), len(rows), looked_up)
    sink.add_writes(utc_day(), written, now)
    from . import universe

    print(json.dumps({"companies": len(rows), "rows_written": written, "industry_lookups": looked_up,
                      "without_industry": sum(1 for r in rows if not r.get("industry")),
                      "outside_universe": universe.rebuild(settings, sink)}))
    return 0


def _sync_companies_nse(settings, sink) -> int:
    """The company master from NSE's equity list and NSE's own industry fields (company_master.py): new listings
    added under their NSE symbol, matched companies kept on their key. Then the universe file is rebuilt."""
    from . import company_master, universe
    from .nse import NseClient
    from .prompts.engine import PromptEngine

    engine = PromptEngine(settings)
    with NseClient() as client:
        raw.attach(client, sink, "nse", settings)
        report = company_master.sync(settings, sink, client, lambda industry: engine.sector_for(industry).name,
                                     now_iso(), today_ist())
    print(json.dumps({**report.as_dict(), "outside_universe": universe.rebuild(settings, sink)}))
    return 0


def cmd_sync_universe(args, settings, sink) -> int:
    """NSE's equity list joined to the company master by ISIN: the companies whose filings are analysed (universe.py)."""
    from . import universe
    from .nse import NseClient

    with NseClient() as client:
        raw.attach(client, sink, "nse", settings)
        counts = universe.build_nse(settings, sink, client.equity_list())
    print(json.dumps({"min_mcap_cr": settings.universe_min_mcap_cr, **counts}))
    return 0


def _refused_code(report: dict) -> int:
    """REFUSED when NSE refused the session, as pledge-sync and deals-sync answer: these two returned 0, so a refusal
    looked like a good night and scripts/retry.sh could not tell it from one (survey, 24 Oct 2026)."""
    return REFUSED if str(report.get("stopped") or "").startswith("NSE refused") else 0


def cmd_governance_sync(args, settings, sink) -> int:
    """The quarterly governance XBRL of the universe's companies into memory (governance_memory.py), no AI."""
    from . import governance_memory

    pipeline = _pipeline(settings, sink)
    scrips = {s.strip() for s in (args.scrips or "").split(",") if s.strip()} or None
    report = governance_memory.sync(pipeline, time.monotonic() + args.time_budget, pages=args.pages, max_files=args.max_files,
                                    scrips=scrips)
    print(json.dumps(report))
    return _refused_code(report)


def cmd_pledge_sync(args, settings, sink) -> int:
    """Promoter encumbrance events (NSE's SAST Reg 31 feed) into memory (pledges.py, module 42), no AI."""
    from . import pledges

    pipeline = _pipeline(settings, sink)
    scrips = {s.strip() for s in (args.scrips or "").split(",") if s.strip()} or None
    report = pledges.sync(pipeline, time.monotonic() + args.time_budget, days=args.days, scrips=scrips)
    print(json.dumps(report, indent=2))
    return REFUSED if (report["stopped"] or "").startswith("NSE refused") else 0


def cmd_deals_sync(args, settings, sink) -> int:
    """The latest session's bulk and block deals (NSE's large-deals snapshot) into memory (deals.py), no AI."""
    from . import deals

    pipeline = _pipeline(settings, sink)
    scrips = {s.strip() for s in (args.scrips or "").split(",") if s.strip()} or None
    report = deals.sync(pipeline, time.monotonic() + args.time_budget, scrips=scrips)
    print(json.dumps(report, indent=2))
    stopped = report["stopped"] or ""
    # a session read neither time is lost (the snapshot holds one session), so a failed read fails the job for its retry
    return REFUSED if stopped.startswith("NSE refused") else 1 if stopped.startswith("snapshot unreadable") else 0


def cmd_deals_backfill(args, settings, sink) -> int:
    """The last N days of bulk and block deals (NSE's deals history) into memory (deals.py), no AI."""
    from . import deals

    pipeline = _pipeline(settings, sink)
    scrips = {s.strip() for s in (args.scrips or "").split(",") if s.strip()} or None
    report = deals.backfill(pipeline, time.monotonic() + args.time_budget, days=args.days, scrips=scrips)
    print(json.dumps(report, indent=2))
    return REFUSED if (report["stopped"] or "").startswith("NSE refused") else 0


def cmd_insider_sync(args, settings, sink) -> int:
    """Insider trades (NSE's SEBI PIT Regulation 7 filings and their XBRL) into memory (insider.py), no AI."""
    from . import insider

    pipeline = _pipeline(settings, sink)
    scrips = {s.strip() for s in (args.scrips or "").split(",") if s.strip()} or None
    report = insider.sync(pipeline, time.monotonic() + args.time_budget, days=args.days, scrips=scrips)
    print(json.dumps(report, indent=2))
    stopped = report["stopped"] or ""
    return REFUSED if stopped.startswith("NSE refused") else 1 if stopped.startswith("list unreadable") else 0


def cmd_corporate_actions_sync(args, settings, sink) -> int:
    """Splits, bonuses, dividends, rights and buybacks (NSE's corporate-actions feed) into memory (corporate_actions.py)."""
    from . import corporate_actions

    pipeline = _pipeline(settings, sink)
    scrips = {s.strip() for s in (args.scrips or "").split(",") if s.strip()} or None
    report = corporate_actions.sync(pipeline, time.monotonic() + args.time_budget, days=args.days, scrips=scrips)
    print(json.dumps(report, indent=2))
    return REFUSED if (report["stopped"] or "").startswith("NSE refused") else 0


def cmd_refresh_summaries(args, settings, sink) -> int:
    """Each company's stored summary (overdue promises, radar, credibility) rebuilt from its memory, no AI. A rule that
    changes what a summary holds reaches companies not processed since only this way (laptop T11, 2026-10-20: the
    overdue list still showed "Ind-Ra expects ..." after third_party_view)."""
    from .pipeline import _company_memory
    from .timeutil import now_iso

    wanted = {s.strip() for s in (args.scrips or "").split(",") if s.strip()}
    scrips = sorted(wanted or sink.list_dossiers())
    rows, written, missing = [], 0, 0
    for scrip in scrips:
        dossier = sink.get_dossier(scrip)
        if not dossier:
            missing += 1
            continue
        rows.append({"scrip_code": scrip, "company_name": dossier.get("company_name") or scrip, "updated_at": now_iso(),
                     **_company_memory(dossier)})
        if len(rows) >= 100:
            written += sink.execute("companies_upsert", rows) or 0
            rows = []
    if rows:
        written += sink.execute("companies_upsert", rows) or 0
    print(json.dumps({"companies": len(scrips) - missing, "missing": missing, "rows_written": written}))
    return 0


def cmd_refresh_card_blocks(args, settings, sink) -> int:
    """Each stored card's code blocks (results table, size, rating ladder, case stage, earlier guidance, fundamentals)
    rebuilt from memory by today's code, and signal types now off removed; no AI (card_refresh.py)."""
    from . import card_refresh

    scrips = {s.strip() for s in (args.scrips or "").split(",") if s.strip()} or None
    report = card_refresh.run(_pipeline(settings, sink), scrips, dry_run=args.dry_run)
    _cards_changed(sink, 0 if args.dry_run else report.get("changed", 0))
    print(json.dumps(report, indent=2))
    return 0


def cmd_export_held(args, settings, sink) -> int:
    """Every held card as stored (its card_json parsed) to a JSON file, for the live reviews: the public site does not
    serve them (owner, 2026-10-20: held drafts may be exported). No AI."""
    after, held = ["", ""], []
    while True:
        rows = sink.query("export_cards", [after[0], after[1], 100])
        if not rows:
            break
        after = [rows[-1]["filed_at"], rows[-1]["news_id"]]
        for row in rows:
            if row.get("held"):
                held.append({k: row.get(k) for k in ("news_id", "scrip_code", "symbol", "company_name", "filed_at",
                                                    "event_category", "pdf_url")} | {"card_json": json.loads(row["card_json"])})
        if len(rows) < 100:
            break
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(held, fh, ensure_ascii=False, indent=1)
    print(json.dumps({"held": len(held), "out": args.out}))
    return 0


def cmd_critic_export(args, settings, sink) -> int:
    """The shadow critic's stored verdicts (R2 evidence/critic/, critic.py) since a day, to a JSON file, for the daily audit to set
    beside the reviewers' verdicts. Read only; no AI, no D1."""
    from . import critic

    found = critic.export(sink, args.since, args.until)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(found, fh, ensure_ascii=False, indent=1)
    flagged = sum(1 for body in found if any(p["verdict"] not in ("OK", critic.MISSING) for p in body["points"]))
    print(json.dumps({"cards": len(found), "flagged_cards": flagged, "out": args.out}))
    return 0


def cmd_apply_verdicts(args, settings, sink) -> int:
    """The owner's standing WRONG / RIGHT verdicts applied to the stored cards once (cards_apply_verdicts.sql): those
    saved before a verdict acted on its card (O11) never held or released it. No AI; a second run writes nothing."""
    written = sink.execute("cards_apply_verdicts", ["WRONG", "RIGHT"])
    _cards_changed(sink, written)
    print(json.dumps({"cards_written": written}))
    return 0


def cmd_requeue_failed(args, settings, sink) -> int:
    """Filings that used every attempt, set PENDING again with fresh attempts (requeue.py), after a fix. No AI."""
    from datetime import timedelta

    from . import requeue
    from .timeutil import today_ist

    if getattr(args, "needs_review", False):
        # every card the review queue still holds for a fault of its own, held or published and flagged (superseded
        # quarters excluded: a re-run cannot publish them), re-run by today's prompt and checks (owner, 2026-10-22)
        from . import prune

        ids = prune.release(sink, dry_run=True)["rerun_ids"] + [i.strip() for i in (args.ids or "").split(",") if i.strip()]
        print(json.dumps(requeue.requeue_ids(sink, ids, settings.max_attempts, args.dry_run), ensure_ascii=False))
        return 0
    if args.ids:
        ids = [i.strip() for i in args.ids.replace("\n", ",").split(",")]
        print(json.dumps(requeue.requeue_ids(sink, ids, settings.max_attempts, args.dry_run), ensure_ascii=False))
        return 0
    since = args.since or (today_ist() - timedelta(days=args.days)).isoformat()
    print(json.dumps(requeue.requeue(sink, since, settings.max_attempts, args.attempts, args.dry_run), ensure_ascii=False))
    return 0


def cmd_failed_report(args, settings, sink) -> int:
    """Every failed filing since a date, grouped by reason (requeue.report). Reads only; no AI."""
    from . import requeue

    print(json.dumps(requeue.report(sink, args.since or settings.backfill_start), ensure_ascii=False, indent=1))
    return 0


def cmd_seed_calls(args, settings, sink) -> int:
    """Each universe company's last two quarters of call transcripts or presentations into memory (call_seed.py): no
    Gemini, no card, no ledger row; resumable."""
    import time

    from . import call_seed

    pipeline = _pipeline(settings, sink)
    scrips = {s.strip() for s in args.scrips.split(",")} if args.scrips else None
    print(json.dumps(call_seed.run(pipeline, time.monotonic() + args.time_budget, args.restart, scrips, settings.workers)))
    return 0


def cmd_dgtr_sync(args, settings, sink) -> int:
    """DGTR trade-remedy cases into the memory of the companies that applied for or supported them (dgtr.py, module 8),
    no AI. --pages 42 reads every case DGTR lists (a first fill: OCR of a few hundred scanned notices, hours)."""
    from . import dgtr

    pipeline = _pipeline(settings, sink)
    scrips = {s.strip() for s in (args.scrips or "").split(",") if s.strip()} or None
    report = dgtr.sync(pipeline, time.monotonic() + args.time_budget, pages=args.pages, scrips=scrips)
    print(json.dumps(report, indent=2))
    return 0


def cmd_shareholding_sync(args, settings, sink) -> int:
    """Each universe company's quarterly shareholding XBRL into memory (governance_memory.shareholding_sync), no AI."""
    from . import governance_memory

    pipeline = _pipeline(settings, sink)
    report = governance_memory.shareholding_sync(pipeline, time.monotonic() + args.time_budget, days=args.days,
                                                 max_files=args.max_files)
    print(json.dumps(report))
    return _refused_code(report)


SEED_SAVE_EVERY = 10   # seed-memory --universe: companies between saved resume points


def cmd_seed_memory(args, settings, sink) -> int:
    """Financial and ownership history from XBRL, with no AI call (see seed.py). Results and shareholding come from
    NSE (owner, 2026-10-19: everything on NSE); `--source bse` adds BSE's results archive (needs an Indian address)."""
    import contextlib

    from .bse import BseClient
    from .nse import NseClient, SourceBlockedError
    from .seed import SeedStats, seed_results, seed_shareholding

    log = logging.getLogger("bse_intel.seed")
    resume_key, early_key = "seed:universe_last", "seed:universe_early"
    shard = None
    if getattr(args, "shard", None):
        try:
            index, count = (int(x) for x in args.shard.split("/"))
            assert 0 <= index < count
        except (ValueError, AssertionError):
            print("--shard takes I/N with 0 <= I < N, e.g. 0/8")
            return 2
        shard = (index, count)
        resume_key, early_key = f"{resume_key}:{index}of{count}", f"{early_key}:{index}of{count}"
    nse_symbols: dict[str, str] = {}   # company key -> NSE symbol, from the universe file, for rows without one
    if args.universe:
        # Every company in the universe file, in key order, after the last one finished (resumable: the command can
        # be stopped and started again; --restart begins from the first company)
        from . import universe

        nse_universe = universe.load_nse(sink)
        if not nse_universe.built:
            print("No NSE universe file yet: run `sync-companies` (or `sync-universe`) first.")
            return 2
        nse_symbols = {scrip: symbol for symbol, scrip in nse_universe.symbols.items()}
        done_through = "" if args.restart else (sink.kv_get(resume_key) or "")
        everyone = sorted(nse_universe.included)
        if shard:   # every N-th company from the I-th, so each runner gets a like mix of sizes and sectors
            everyone = everyone[shard[0]::shard[1]]
        scrips = [s for s in everyone if s > done_through]
        # Companies reporting now first: results due in the next three weeks, or a filing in the last week, and not
        # seeded yet. They do not move the resume point, which follows the scrip order of the rest.
        today = today_ist()   # IST, as everything else: the runner's date.today() is UTC, a day behind after 18:30 UTC
        try:
            soon = [r["scrip_code"] for r in sink.query("seed_priority", [(today - timedelta(days=7)).isoformat(),
                                                                          (today + timedelta(days=21)).isoformat()])]
        except Exception as exc:  # the order is an optimisation; the seed still covers everyone
            log.warning("seed: no priority list (%s)", exc)
            soon = []
        # seeded out of order on an earlier pass (a --restart walks everyone again)
        early = set() if args.restart else set(json.loads(sink.kv_get(early_key) or "[]"))
        scrips = [s for s in scrips if s not in early]
        priority = [s for s in dict.fromkeys(soon) if s in set(scrips)]
        scrips = priority + [s for s in scrips if s not in set(priority)]
        log.info("seed: %d universe companies to go (after %r), %d reporting now first", len(scrips), done_through, len(priority))
    else:
        names = [s.strip() for s in (args.scrips or "").split(",") if s.strip()]
        if not names:
            print("Name the companies with --scrips, or seed the whole universe with --universe.")
            return 2
        # a company key or an NSE symbol: reseed.yml was run with symbols (SIEMENS, ABB, ...) on 22 Oct 2026, none was a
        # key, and all 14 seeded nothing without a word
        from . import universe

        nse_universe = universe.load_nse(sink)
        nse_symbols = {scrip: symbol for symbol, scrip in nse_universe.symbols.items()}
        scrips, unknown = [], []
        for name in names:
            key = nse_universe.symbols.get(name.upper())
            if key:
                scrips.append(key)
            elif sink.company(name) or name in nse_symbols:
                scrips.append(name)
            else:
                unknown.append(name)
        if unknown:
            print(f"Not a company key or an NSE symbol in the universe: {', '.join(unknown)}")
            return 2
    stats = SeedStats()
    cache_root = settings.text_cache_dir
    # the resume point is saved every SEED_SAVE_EVERY companies and when the loop ends however it ends (one kv write
    # per company before 2026-10-21); a run killed outright seeds at most that many companies again, which replaces
    # their memory entries with the same figures
    last_done, saved = None, done_through if args.universe else None
    priority_set = set(priority) if args.universe else set()
    refused = False
    with (BseClient() if args.source == "bse" else contextlib.nullcontext()) as bse, NseClient() as nse, \
            contextlib.ExitStack() as checkpoint:
        if args.universe:
            checkpoint.callback(lambda: last_done and last_done != saved and sink.kv_set(resume_key, last_done, now_iso()))
        if bse is not None:
            raw.attach(bse, sink, "bse", settings)
            bse.warm_up()
        raw.attach(nse, sink, "nse", settings)
        for scrip in scrips:
            company = sink.company(scrip) or {}
            name = company.get("company_name") or scrip
            symbol = (company.get("symbol") or "").strip() or nse_symbols.get(scrip, "")
            stats.companies += 1
            if not args.shareholding_only:
                try:
                    seed_results(sink, bse, scrip, name, args.since, cache_root, stats, company,
                                 nse=nse, symbol=symbol)
                except SourceBlockedError as exc:
                    stats.failures.append(f"{scrip} results: {exc}"[:200])
                    log.error("NSE refused the session; stopping the seed: %s", exc)
                    refused = True
                    break  # NSE limits by IP: stop, do not press on (a --universe run resumes at this company)
                except Exception as exc:  # one company's archive must not end the run
                    stats.failures.append(f"{scrip} results: {type(exc).__name__}: {exc}"[:200])
                    log.warning("seed %s results failed: %s", scrip, exc)
            if not args.results_only and symbol:
                try:
                    seed_shareholding(sink, nse, scrip, symbol, name, args.since, cache_root, stats, company)
                except SourceBlockedError as exc:
                    stats.failures.append(f"{scrip} shareholding: {exc}"[:200])
                    log.error("NSE refused the session; stopping the shareholding seed: %s", exc)
                    refused = True
                    break  # NSE limits by IP: stop, do not press on
                except Exception as exc:
                    stats.failures.append(f"{scrip} shareholding: {type(exc).__name__}: {exc}"[:200])
                    log.warning("seed %s shareholding failed: %s", scrip, exc)
            elif not args.results_only:
                stats.failures.append(f"{scrip}: no NSE symbol stored")
            log.info("seed: %s", stats.line())
            if args.universe and scrip in priority_set:
                early.add(scrip)   # seeded out of order: kept apart, the resume point stays with the scrip-order walk
                sink.kv_set(early_key, json.dumps(sorted(early)), now_iso())
                continue
            if args.universe:
                last_done = scrip
                if stats.companies % SEED_SAVE_EVERY == 0:
                    sink.kv_set(resume_key, scrip, now_iso())
                    saved = scrip
    print(json.dumps({"companies": stats.companies, "results_files": stats.results_files,
                      "results_periods": stats.results_periods, "shareholding_files": stats.shareholding_files,
                      "shareholding_periods": stats.shareholding_periods, "skipped": stats.skipped,
                      "failures": stats.failures[:20], "refused": refused}, ensure_ascii=False))
    # REFUSED when NSE refused, as the other NSE syncs: it returned 0, the shard wrote no "more" marker and the job
    # record said ok, so the seed chain stopped with nothing to show for it (survey, 24 Oct 2026)
    return REFUSED if refused else 0


def cmd_prune_companies(args, settings, sink) -> int:
    """Company rows that are not on NSE's lists (prune_companies.py): a dry run by default; --apply backs them up to R2
    and removes the ones with no cards. A company with cards is only reported."""
    from . import prune_companies
    from .nse import NseClient

    with NseClient() as client:
        raw.attach(client, sink, "nse", settings)
        equities = client.equity_list()
        sme = client.sme_list()
    report = prune_companies.plan(sink, equities, sme, keep_sme=args.keep_sme, bse_keep_min_mcap=args.bse_keep_min_mcap)
    print(prune_companies.render(report))
    done = None
    if args.apply:
        done = prune_companies.apply(sink, report, today_ist().isoformat())
        print(json.dumps(done, ensure_ascii=False))
    else:
        print("dry run: nothing changed (--apply backs up to R2 backup/prune-companies-<date>.json, then removes)")
    if args.json:
        Path(args.json).write_text(json.dumps({**report, "applied": done}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.csv:
        Path(args.csv).write_text(prune_companies.to_csv(report), encoding="utf-8")
    return 0


def cmd_bse_verify_kept(args, settings, sink) -> int:
    """Read-only (bse_verify_kept.py): BSE's answer for each kept BSE-only company, through the ported adapter."""
    from . import bse_verify_kept, prune_companies
    from .nse import NseClient

    with NseClient() as client:
        equities = client.equity_list()
        sme = client.sme_list()
    every = prune_companies.bse_kept_rows(sink, equities, sme, args.min_mcap)
    kept = every[:args.limit] if args.limit else every
    print(f"kept BSE-only companies: {len(every)}; asking BSE about {len(kept)}", flush=True)
    client, _ = bse_verify_kept.make_client()
    result = bse_verify_kept.verify(client, kept, today_ist(), args.min_mcap)
    print(bse_verify_kept.render(result))
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.csv:
        Path(args.csv).write_text(bse_verify_kept.to_csv(result), encoding="utf-8")
    return 0


MORE_LEFT = 124   # memory-gaps --fill: the time budget ended the run with companies left (as `timeout` exits)


def cmd_memory_gaps(args, settings, sink) -> int:
    """Which universe companies lack exchange-XBRL results quarters in memory (memory_gaps.py); --fill seeds those
    companies' results from NSE (the seed's per-company function) and re-checks. No AI."""
    from . import memory_gaps, universe
    from .nse import NseClient, SourceBlockedError

    log = logging.getLogger("bse_intel.memory_gaps")
    shard = None
    if args.shard:
        try:
            index, count = (int(x) for x in args.shard.split("/"))
            assert 0 <= index < count
        except (ValueError, AssertionError):
            print("--shard takes I/N with 0 <= I < N, e.g. 0/4")
            return 2
        shard = (index, count)
    nse_universe = universe.load_nse(sink)
    if args.scrips:
        scrips = [nse_universe.symbols.get(name.upper()) or name for name in (s.strip() for s in args.scrips.split(",")) if name]
    elif nse_universe.built:
        scrips = sorted(nse_universe.included)
    else:
        print("No NSE universe file yet: run `sync-companies` (or `sync-universe`) first.")
        return 2
    today = date.fromisoformat(args.as_of) if args.as_of else today_ist()
    before = memory_gaps.survey(sink, scrips, today, args.quarters)
    print(memory_gaps.render(before))
    final, outcome, refused = before, None, False
    after = None
    if args.fill:
        from .seed import SeedStats, seed_results

        nse_symbols = {scrip: symbol for symbol, scrip in nse_universe.symbols.items()}
        stats = SeedStats()
        with NseClient() as nse:
            raw.attach(nse, sink, "nse", settings)

            def seed_one(scrip: str, since: str) -> None:
                company = sink.company(scrip) or {}
                symbol = (company.get("symbol") or "").strip() or nse_symbols.get(scrip, "")
                seed_results(sink, None, scrip, company.get("company_name") or scrip, since, settings.text_cache_dir,
                             stats, company, nse=nse, symbol=symbol)
                log.info("memory-gaps fill: %s %s", scrip, stats.line())

            try:
                outcome = memory_gaps.fill(sink, before, seed_one, args.time_budget, args.restart, shard)
            except SourceBlockedError as exc:
                log.error("NSE refused the session; stopping the fill: %s", exc)
                refused = True
                outcome = {"attempted": [], "failed": [f"NSE refused: {exc}"[:200]], "more": False}
        touched = [s for s in scrips if s in set(outcome["attempted"])]
        redone = memory_gaps.survey(sink, touched, today, args.quarters)
        print(f"\nthe {len(touched)} companies the fill tried, before:")
        print(json.dumps(memory_gaps.summarise({s: before["companies"][s] for s in touched})))
        print("after:")
        print(json.dumps(redone["summary"]))
        print(f"fill: {len(outcome['attempted'])} tried, {len(outcome['failed'])} failed, more left: {outcome['more']}")
        for line in outcome["failed"][:20]:
            print(f"  {line}")
        merged = {**before["companies"], **redone["companies"]}   # untouched companies keep their earlier check
        after = {**before, "summary": memory_gaps.summarise(merged), "companies": merged}
        final = after
        print("whole universe after the fill:")
        print(memory_gaps.render(after))
    if args.json:
        body = {"as_of": final["as_of"], "latest_quarter": final["latest_quarter"], "quarters": final["quarters"],
                "before": before["summary"], "after": after["summary"] if after else None, "fill": outcome,
                "gaps": memory_gaps.gap_rows(final)}
        Path(args.json).write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.csv:
        Path(args.csv).write_text(memory_gaps.to_csv(final), encoding="utf-8")
    if refused:
        return REFUSED
    return MORE_LEFT if outcome and outcome["more"] else 0


def cmd_restated_report(args, settings, sink) -> int:
    """Quarters whose restated figure differs from the one first filed, across stored memory (restated_report.py, F167).
    Read only: no NSE, no AI, no write."""
    from . import restated_report, universe

    nse_universe = universe.load_nse(sink)
    if args.scrips:
        scrips = [nse_universe.symbols.get(name.upper()) or name for name in (s.strip() for s in args.scrips.split(",")) if name]
    elif nse_universe.built:
        scrips = sorted(nse_universe.included)
    else:
        print("No NSE universe file yet: run `sync-companies` (or `sync-universe`) first.")
        return 2
    report = restated_report.survey(sink, scrips)
    print(restated_report.render(report))
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


def cmd_memory_recall_export(args, settings, sink) -> int:
    """The sample of recent call transcripts and decks for the memory recall audit, each with its full text, what memory
    holds from it and its card (memory_recall_export.py, TODO row 82). Read only: no NSE, no AI, no write."""
    from . import memory_recall_export as mre

    index = mre.export(sink, Path(args.out), args.limit, args.seed, args.days)
    print(mre.render(index))
    return 0 if index["sampled"] else 1


class PermanentSkip(Exception):
    """A call document that can never be read (not in the ledger, an invitation): it leaves the queue at once."""


def _read_call_document(pipeline, sink, news_id: str, apply: bool, out_dir: Path | None, read_text, paid) -> dict:
    """One transcript or deck through the call-memory reading and its checks (call_memory.py); with `apply` the kept points
    are merged into the dossier's `call_memory` by the three-way write the pipeline uses. Returns the report row. A document
    that can never be read (not in the ledger, an invitation) raises PermanentSkip; any other error is transient. No stored text
    is transient: the pipeline writes the text after it queues the filing, and the write is best effort."""
    from . import call_memory, memory_recall_export as mre
    from .dossier import keep_concurrent_writes
    from .extract import Document

    row: dict = {"news_id": news_id}
    data = read_text(news_id)
    filing = call_memory.find_filing(sink, news_id)
    if filing is None:
        raise PermanentSkip("not in the filings ledger")
    if not data:
        raise RuntimeError("no stored text yet")   # retried; given up after call_queue.MAX_ATTEMPTS
    text, _ = mre.render_text(data)
    doc = Document.from_cache(data)
    blocks = doc.block_text(range(doc.page_count))
    dossier = sink.get_dossier(filing.scrip_code) or {}
    industry = dossier.get("industry") or (sink.company(filing.scrip_code) or {}).get("industry")
    kind = mre.kind_from_text(data, filing.headline)
    if kind == "invitation":
        raise PermanentSkip("an invitation to a call, not a transcript or deck")
    prior = call_memory.prior_points(dossier, news_id, filing.filed_at)
    started = time.monotonic()
    reply = call_memory.read(pipeline.gateway, pipeline.prompts, filing, kind, industry, text, blocks, prior, paid)
    kept, dropped = call_memory.check_points(reply.points, text, blocks, scope=f"{filing.scrip_code}:{news_id}")
    row |= {"symbol": filing.symbol, "company": filing.company_name, "filed_at": filing.filed_at, "kind": kind,
            "model": reply.served_by, "chars": len(text), "prompt_chars": reply.prompt_chars, "pages": doc.page_count,
            "seconds": round(time.monotonic() - started, 1), "asked": len(reply.points), "kept": len(kept),
            "dropped": len(dropped), "counts_by_type": call_memory.counts_by_type(kept),
            "dropped_by_reason": {r: sum(d["reason"] == r for d in dropped) for r in sorted({d["reason"] for d in dropped})},
            "prior_points": len(prior), "reason": reply.reason, "applied": False, "parts": reply.parts,
            "parts_failed": reply.parts_failed, "assembled_quotes": sum(p.quote_assembled for p in kept)}
    if apply and kept:
        merged = json.loads(json.dumps(dossier))
        call_memory.remember(merged, news_id, filing.filed_at, kept)
        fresh = sink.get_dossier(filing.scrip_code)
        held = keep_concurrent_writes(merged, dossier, fresh)
        if held:
            logging.getLogger(__name__).info("%s: memory written meanwhile by another job kept: %s", news_id, ", ".join(held))
        sink.put_dossier(filing.scrip_code, merged)
        row["applied"] = True
    if out_dir is not None:
        (out_dir / f"{mre._folder_name(news_id)}.json").write_text(json.dumps(
            {**row, "points_kept": [p.model_dump(exclude_none=True) for p in kept], "points_dropped": dropped},
            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return row


def _call_memory_pending(args, settings, sink) -> int:
    """`call-memory --pending`: the queue the pipeline fills with MEMORY_CALL_V2 on (call_queue.py), oldest first. A filing
    leaves the queue once its points are written (or the reading has none), or on a permanent failure (no stored text, an
    invitation) with its reason; a transient failure leaves it queued with an attempt counted, given up after
    call_queue.MAX_ATTEMPTS. Stops at the time budget; exit 124 when filings are left."""
    from . import call_memory, call_queue, memory_recall_export as mre
    from .settings import memory_call_v2

    if not memory_call_v2():
        print("MEMORY_CALL_V2 is off: nothing to read")
        return 0
    items = call_queue.pending(sink)
    if args.limit:
        items = items[:args.limit]
    if not items:
        print("call memory queue is empty")
        return 0
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.time_budget
    pipeline = _pipeline(settings, sink)
    paid = call_memory.paid_providers(settings)
    read_text = mre.read_text_from(sink)
    counts = {"done": 0, "gave_up": 0, "retry": 0}
    left = 0
    for n, item in enumerate(items):
        if time.monotonic() >= deadline:
            left = len(items) - n
            break
        news_id = item["news_id"]
        reason = None
        if args.apply:   # the attempt counts before the reading: a run killed mid-reading still counts it
            try:
                if not call_queue.start(sink, item):
                    counts["gave_up"] += 1
                    continue
            except Exception as exc:   # noqa: BLE001 - read it anyway; the state is written after
                log.warning("%s: queue state not saved: %s", news_id, exc)
        try:
            row = _read_call_document(pipeline, sink, news_id, args.apply, out_dir, read_text, paid)
            state = "done"
            if row.get("parts_failed") and int(item.get("attempts", 0)) < call_queue.MAX_ATTEMPTS:
                # some parts unread: the points kept are written, and the whole document is read again (which replaces them)
                state, reason = "retry", f"parts failed: {row['parts_failed']}"
            print(json.dumps({k: row.get(k) for k in ("news_id", "symbol", "kind", "model", "asked", "kept", "dropped")}, ensure_ascii=False))
        except PermanentSkip as exc:   # nothing to read now or later
            state, reason = "gave_up", f"PermanentSkip: {exc}"
        except Exception as exc:   # noqa: BLE001 - one document never stops the rest; a transient failure is retried
            state, reason = "retry", f"{type(exc).__name__}: {exc}"
        if state != "done":
            print(json.dumps({"news_id": news_id, "state": state, "error": reason}, ensure_ascii=False))
        if not args.apply:
            continue   # a measurement run changes no queue state
        try:
            state = call_queue.settle(sink, item, state, reason, count=False)
        except Exception as exc:   # noqa: BLE001 - the points are written; the entry is read again, which replaces them
            log.warning("%s: queue state not saved: %s", news_id, exc)
        counts[state] += 1
        if state == "retry":
            left += 1
    print(json.dumps({"queue": len(items), **counts, "left": left}))
    return MORE_LEFT if left else 0


def cmd_call_memory(args, settings, sink) -> int:
    """The call-memory reading (call_memory.py, TODO 83) of the named transcripts and decks: the stored text and the company's
    memory in, the checked points and every dropped point with its reason out, one file a document and a summary.json. Without
    --apply nothing is written to memory (the measurement run: maintenance, read only); with it the points are merged into
    the dossier's `call_memory` through the same three-way write the pipeline uses. Free providers only.
    `--pending` reads the queue instead of named ids (_call_memory_pending)."""
    from . import call_memory, memory_recall_export as mre

    if getattr(args, "pending", False):
        return _call_memory_pending(args, settings, sink)
    ids = [i.strip() for i in (args.ids or "").replace("\n", ",").split(",") if i.strip()]
    if not ids:
        print("No filings: give --ids news_id,news_id (or --pending)")
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    pipeline = _pipeline(settings, sink)
    paid = call_memory.paid_providers(settings)
    read_text = mre.read_text_from(sink)
    report: list[dict] = []
    for news_id in ids:
        row: dict = {"news_id": news_id}
        try:
            row = _read_call_document(pipeline, sink, news_id, args.apply, out_dir, read_text, paid)
        except Exception as exc:   # noqa: BLE001 - one document never stops the rest
            row["error"] = f"{type(exc).__name__}: {exc}"[:300]
        report.append(row)
        print(json.dumps({k: row.get(k) for k in ("news_id", "symbol", "kind", "model", "asked", "kept", "dropped", "error")}, ensure_ascii=False))
    done = [r for r in report if "error" not in r]
    by_type: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    for r in done:
        for k, v in r["counts_by_type"].items():
            by_type[k] = by_type.get(k, 0) + v
        for k, v in r["dropped_by_reason"].items():
            by_reason[k] = by_reason.get(k, 0) + v
    summary = {"documents": len(ids), "read": len(done), "failed": len(report) - len(done), "applied": sum(bool(r.get("applied")) for r in done),
               "asked": sum(r["asked"] for r in done), "kept": sum(r["kept"] for r in done), "dropped": sum(r["dropped"] for r in done),
               "counts_by_type": dict(sorted(by_type.items())), "dropped_by_reason": dict(sorted(by_reason.items())),
               "by_kind": {k: sum(r["kind"] == k for r in done) for k in ("transcript", "deck")}, "rows": report}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False))
    return 0 if done else 1


def cmd_prediction_units(args, settings, sink) -> int:
    """Stored targets judged in two different units, and per-share units on figures that are not per share (TODO item
    84, prediction_check.py). Read only: no AI, no write; the next merge of each company withdraws the verdicts."""
    from . import prediction_check, universe

    nse_universe = universe.load_nse(sink)
    if args.scrips:
        scrips = [nse_universe.symbols.get(name.upper()) or name for name in (s.strip() for s in args.scrips.split(",")) if name]
    elif nse_universe.built:
        scrips = sorted(nse_universe.included)
    else:
        print("No NSE universe file yet: run `sync-companies` (or `sync-universe`) first.")
        return 2
    report = prediction_check.survey(sink, scrips, {scrip: sym for sym, scrip in nse_universe.symbols.items()})
    print(prediction_check.render(report))
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


def cmd_nse_selfcheck(args, settings, sink) -> int:
    """NSE's own figures in memory against themselves: own file against a later file's comparative column, and Q1+Q2+Q3+Q4
    against the year (nse_selfcheck.py, TODO row 60). Read only: no NSE, no AI, no write."""
    from . import nse_selfcheck, universe

    nse_universe = universe.load_nse(sink)
    if args.scrips:
        scrips = [nse_universe.symbols.get(name.upper()) or name for name in (s.strip() for s in args.scrips.split(",")) if name]
    elif nse_universe.built:
        scrips = sorted(nse_universe.included)
    else:
        print("No NSE universe file yet: run `sync-companies` (or `sync-universe`) first.")
        return 2
    symbols = {scrip: sym for sym, scrip in nse_universe.symbols.items()}
    report = nse_selfcheck.survey(sink, scrips, symbols)
    print(nse_selfcheck.render(report))
    if args.json:
        summary = {k: v for k, v in report.items() if k != "rows"}
        Path(args.json).write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.csv:
        Path(args.csv).write_text(nse_selfcheck.to_csv(report), encoding="utf-8")
    if args.referee_csv:
        Path(args.referee_csv).write_text(nse_selfcheck.referee_csv(report), encoding="utf-8")
    return 0


def cmd_nse_speedtest(args, settings, sink) -> int:
    """Read-only speed test of NSE's listing API and the archive host (nse_speedtest.py, F168). Writes only the --json file;
    nothing to D1, R2 or memory. No AI."""
    from . import nse_speedtest as st, universe
    from .nse import NseClient

    nse_universe = universe.load_nse(sink)
    if not nse_universe.built:
        print("No NSE universe file yet: run `sync-companies` (or `sync-universe`) first.")
        return 2
    symbols = st.pick_symbols([sym for sym, scrip in nse_universe.symbols.items() if scrip in nse_universe.included],
                              args.companies, args.seed)
    with NseClient() as nse:
        report = st.run(nse, symbols, seed=args.seed, per_round=args.files)
    print(st.render(report))
    if args.json:
        st.write_json(report, args.json)
    return 0


def cmd_screener_fill(args, settings, sink) -> int:
    """The one-time fill of quarters memory lacks from screener.in (screener_fill.py, F161): a dry run by default (fetch,
    decide, report; no write), --apply writes by="screener" figures. One request per gap company, at least 3 s apart per
    runner, at most 2 runners. No AI."""
    from . import memory_gaps, screener_fill, universe

    shard = None
    if args.shard:
        try:
            index, count = (int(x) for x in args.shard.split("/"))
            assert 0 <= index < count <= screener_fill.MAX_SHARDS
        except (ValueError, AssertionError):
            print(f"--shard takes I/N with 0 <= I < N <= {screener_fill.MAX_SHARDS}, e.g. 0/2")
            return 2
        shard = (index, count)
    nse_universe = universe.load_nse(sink)
    if args.scrips:
        scrips = [nse_universe.symbols.get(name.upper()) or name for name in (s.strip() for s in args.scrips.split(",")) if name]
    elif nse_universe.built:
        scrips = sorted(nse_universe.included)
    else:
        print("No NSE universe file yet: run `sync-companies` (or `sync-universe`) first.")
        return 2
    today = date.fromisoformat(args.as_of) if args.as_of else today_ist()
    report = memory_gaps.survey(sink, scrips, today, args.quarters)
    print(memory_gaps.render(report))
    by_scrip = {scrip: symbol for symbol, scrip in nse_universe.symbols.items()}
    symbols = {scrip: screener_fill.symbol_of(sink.company(scrip), by_scrip.get(scrip, ""))
               for scrip, r in report["companies"].items() if memory_gaps.has_gap(r)}
    plan = screener_fill.estimate(report, shard[1] if shard else 1)
    print(f"\nplanned: about {plan['requests']} requests, about {plan['seconds'] // 60} minutes at one request per "
          f"{screener_fill.PAUSE_SECONDS:g} s")
    refused = False
    with screener_fill.ScreenerClient() as client:
        try:
            outcome = screener_fill.run(sink, report, symbols, client, args.apply, args.time_budget, args.restart, shard)
        except screener_fill.ScreenerRefused as exc:
            logging.getLogger("bse_intel.screener_fill").error("screener.in refused; stopping: %s", exc)
            refused = True
            outcome = {"apply": args.apply, "more": False, "failed": [f"refused: {exc}"[:200]], "rows": [],
                       "companies_with_gaps": 0, "companies_fetched": 0, "requests_made": client.requests,
                       "companies_skipped_tried": 0, "companies_failed": 0, "companies_with_fills": 0,
                       "fillable": {"revenue": 0, "pat": 0}, "written": 0, "skipped": {}}
    print(screener_fill.render(outcome))
    for line in outcome["failed"][:20]:
        print(f"  {line}")
    if not args.apply:
        print("dry run: nothing changed (--apply writes the figures as by=\"screener\"; no card reads them unless MEMORY_SCREENER=1)")
    if args.json:
        Path(args.json).write_text(json.dumps({k: v for k, v in outcome.items() if k != "rows"} | {"planned": plan, "as_of": report["as_of"]},
                                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.csv:
        Path(args.csv).write_text(screener_fill.to_csv(outcome), encoding="utf-8")
    if refused:
        return REFUSED
    return MORE_LEFT if outcome["more"] else 0


def _universe_companies(sink, scrips_arg: str | None):
    """(scrip, NSE symbol) for the universe (or the ``--scrips`` list: company keys or NSE symbols), in symbol order; None
    when there is no universe file yet. BSE-only companies kept by prune-companies are not in it (the universe code lists
    NSE companies only), so they are not here."""
    from . import screener_download, universe

    nse_universe = universe.load_nse(sink)
    if scrips_arg:
        scrips = [nse_universe.symbols.get(name.upper()) or name for name in (s.strip() for s in scrips_arg.split(",")) if name]
    elif nse_universe.built:
        scrips = sorted(nse_universe.included)
    else:
        return None
    by_scrip = {scrip: symbol for symbol, scrip in nse_universe.symbols.items()}
    return screener_download.symbols_for(sink, scrips, by_scrip)


def cmd_screener_download(args, settings, sink) -> int:
    """The one-time download of every company's screener.in pages, raw and gzipped, into R2 (screener_download.py, F163): two
    pages a company, at least 3.2 s apart per runner, at most 2 runners, no login, a plain browser User-Agent; a 403, 429 or
    503 stops the run (exit 75). Resumable; exit 124 when the time budget ends with companies left. No AI, no NSE, no memory."""
    from . import screener_download as sd

    shard = None
    if args.shard:
        try:
            index, count = (int(x) for x in args.shard.split("/"))
            assert 0 <= index < count <= sd.MAX_SHARDS
        except (ValueError, AssertionError):
            print(f"--shard takes I/N with 0 <= I < N <= {sd.MAX_SHARDS}, e.g. 0/2")
            return 2
        shard = (index, count)
    companies = _universe_companies(sink, args.scrips)
    if companies is None:
        print("No NSE universe file yet: run `sync-companies` (or `sync-universe`) first.")
        return 2
    day = args.day or today_ist().isoformat()
    mine = companies[shard[0]::shard[1]] if shard else companies
    plan = sd.estimate(len(mine), 1)
    whole = sd.estimate(len(companies), 2)
    print(f"screener download {day}: {len(mine)} companies in this shard, about {plan['requests']} requests, about "
          f"{plan['seconds'] / 3600:.1f} hours at one request per {sd.PAUSE_SECONDS:g} s "
          f"(the whole universe: {whole['requests']} requests, about {whole['seconds'] / 3600:.1f} hours on 2 shards)")
    refused = False
    with sd.ScreenerClient() as client:
        try:
            outcome = sd.run(sink, companies, client, day, shard, args.time_budget, args.restart)
        except sd.ScreenerRefused as exc:
            logging.getLogger("bse_intel.screener_download").error("screener.in refused; stopping: %s", exc)
            refused = True
            outcome = None
    if outcome:
        print(sd.render(outcome))
        for line in outcome["failed"][:20]:
            print(f"  {line}")
    if args.json:
        Path(args.json).write_text(json.dumps(outcome or {"refused": True}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if refused:
        return REFUSED
    return MORE_LEFT if outcome["more"] else 0


def cmd_text_backfill(args, settings, sink) -> int:
    """The one-time text backfill (text_backfill.py, F165): the filing text of every stored card that has none in R2, fetched
    from NSE as the pipeline does (its client, headers and 3-5 s pacing; one request a filing) and written through the
    pipeline's own text-cache bytes. At most 2 shards; exit 75 when NSE refuses, 124 when the time budget ends with filings
    left. No AI (local OCR only), no card, memory or filings write."""
    from . import text_backfill as tb
    from .bse import BseClient, SourceBlockedError   # the base class: NSE's refusal and BSE's both
    from .nse import NseClient

    bse = args.source == "bse"
    if bse and args.shard:
        print("--source bse runs on one runner (no --shard)")
        return 2
    shard = None
    if args.shard:
        try:
            index, count = (int(x) for x in args.shard.split("/"))
            assert 0 <= index < count <= tb.MAX_SHARDS
        except (ValueError, AssertionError):
            print(f"--shard takes I/N with 0 <= I < N <= {tb.MAX_SHARDS}, e.g. 0/2")
            return 2
        shard = (index, count)
    rows, counts = tb.cards_lacking_text(sink, None if bse else args.limit)
    if bse:   # only the cards whose file is on BSE; --limit counts those
        rows = tb.bse_rows(rows)[:args.limit] if args.limit else tb.bse_rows(rows)
    mine = len(rows[shard[0]::shard[1]]) if shard else len(rows)
    plan = tb.estimate(mine, 1, not args.no_ocr)
    whole = tb.estimate(len(rows), 2, not args.no_ocr)
    print(f"text backfill: {counts.get('cards', 0)} cards, {counts.get('lacking', 0)} without text "
          f"({counts.get('known_no_text', 0)} known to have none), {len(rows)} to fetch, {mine} in this shard; estimated "
          f"{plan['seconds_each']:g} s a filing, about {plan['seconds'] / 3600:.1f} hours for this shard "
          f"(the whole {len(rows)} on 2 shards: about {whole['seconds'] / 3600:.1f} hours; an assumption, not measured)")
    refused = False
    with (BseClient() if bse else NseClient()) as client:
        try:
            outcome = tb.run(sink, rows, tb.BseFetcher(client) if bse else client, shard, args.time_budget, args.restart,
                             ocr=not args.no_ocr, max_ocr_pages=settings.max_ocr_pages, source=args.source)
        except SourceBlockedError as exc:
            logging.getLogger("bse_intel.text_backfill").error("%s refused the session; stopping: %s",
                                                               args.source.upper(), exc)
            refused = True
            outcome = None
    if outcome:
        print(tb.render(outcome, counts))
    if args.json:
        body = {**(outcome or {"refused": True}), "cards": counts}
        Path(args.json).write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if refused:
        return REFUSED
    return MORE_LEFT if outcome["more"] else 0


def cmd_screener_crosscheck(args, settings, sink) -> int:
    """Read-only cross-check of memory against the stored screener pages (screener_crosscheck.py, F163): no request to
    screener or NSE, no write, no AI. Writes the summary JSON, the CSV of every non-match pair, referee.csv and the markdown."""
    from . import screener_crosscheck as sc

    companies = _universe_companies(sink, args.scrips)
    if companies is None:
        print("No NSE universe file yet: run `sync-companies` (or `sync-universe`) first.")
        return 2
    summary = sc.run(sink, companies, args.day, args.workers, not args.no_referee)
    print(sc.render(summary))
    if args.json:
        Path(args.json).write_text(sc.to_json(summary), encoding="utf-8")
    if args.csv:
        Path(args.csv).write_text(sc.to_csv(summary), encoding="utf-8")
    if args.referee_csv:
        Path(args.referee_csv).write_text(sc.to_referee_csv(summary), encoding="utf-8")
    if args.md:
        Path(args.md).write_text(sc.to_markdown(summary, today_ist().isoformat()), encoding="utf-8")
    return 0


def cmd_pdf_referee(args, settings, sink) -> int:
    """Read-only: the filing PDF as the last referee of the pairs the screener-referee left open (pdf_referee.py). The input
    is the screener-referee CSV (``--csv``); each pair with verdict neither, no_file or screener_matches_official gets its
    period's results PDF from NSE (announcement list, ``NseClient.fetch``), read with the pipeline's own reader. No memory
    write, no card change, no AI. Exit 75 when NSE refused the session, 124 when the time budget ended with pairs left."""
    from . import pdf_referee as pr
    from .nse import NseClient

    path = Path(args.csv)
    if not path.is_file():
        print(f"No screener-referee CSV at {path}.")
        return 2
    rows = pr.load_csv(path.read_text(encoding="utf-8"))
    with NseClient() as nse:
        outcome = pr.run(nse, rows, args.limit, args.time_budget, ocr=not args.no_ocr)
    print(pr.render(outcome))
    if args.json:
        Path(args.json).write_text(pr.to_json(outcome), encoding="utf-8")
    if args.out_csv:
        Path(args.out_csv).write_text(pr.to_csv(outcome), encoding="utf-8")
    if args.md:
        Path(args.md).write_text(pr.to_markdown(outcome, today_ist().isoformat()), encoding="utf-8")
    if outcome["blocked"]:
        return REFUSED
    return 124 if outcome["out_of_time"] else 0


def cmd_screener_referee(args, settings, sink) -> int:
    """Read-only: NSE's own results XBRL as the referee of the screener cross-check (screener_xbrl_referee.py). The
    cross-check is worked out again from R2 and memory (no request), then each disagreeing pair is looked up in the period's
    file (the next period's as a fallback) from NSE: one results list a company, each file once. No memory write, no card
    change, no AI. Exit 75 when NSE refused the session, 124 when the time budget ended with pairs left (--limit is a chosen stop: 0)."""
    from . import screener_crosscheck as sc
    from . import screener_xbrl_referee as sx
    from .nse import NseClient

    companies = _universe_companies(sink, args.scrips)
    if companies is None:
        print("No NSE universe file yet: run `sync-companies` (or `sync-universe`) first.")
        return 2
    summary = sc.run(sink, companies, args.day, args.workers, False)
    with NseClient() as nse:
        outcome = sx.run(nse, summary["rows"], args.limit, args.time_budget)
    print(sx.render(outcome))
    if args.json:
        Path(args.json).write_text(sx.to_json(outcome), encoding="utf-8")
    if args.csv:
        Path(args.csv).write_text(sx.to_csv(outcome), encoding="utf-8")
    if args.md:
        Path(args.md).write_text(sx.to_markdown(outcome, today_ist().isoformat()), encoding="utf-8")
    if outcome["blocked"]:
        return REFUSED
    return 124 if outcome["out_of_time"] else 0


def cmd_label_memory(args, settings, sink) -> int:
    """Label everything already in memory (memory_labels.py, TRACKER F150): no AI, no NSE, no card change. A dry run
    prints the counts per section and label and writes nothing; a real run writes each changed dossier back through the
    safe write (three-way merge) and resumes after the last company it finished."""
    from . import memory_labels

    if args.scrips:
        scrips = [s.strip() for s in args.scrips.split(",") if s.strip()]
    else:
        scrips = sink.list_dossiers()
    cards = memory_labels.load_cards(sink, set(scrips) if args.scrips else None)
    report = memory_labels.label_all(sink, scrips, args.dry_run, cards, args.restart, args.time_budget)
    print(memory_labels.render(report))
    if report["skipped_resumed"]:
        print(f"{report['skipped_resumed']} companies skipped: an earlier run finished them (--restart goes over them again)")
    for line in report["failed"][:20]:
        print(f"  failed: {line}")
    if args.json:
        body = {k: v for k, v in report.items() if k != "had"} | {
            "already_labelled": report["had"], "cards_read": len(cards), "new_totals": memory_labels.totals(report["new"])}
        Path(args.json).write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if report["failed"]:
        return 1
    return MORE_LEFT if report["more"] else 0


def cmd_price_history(args, settings, sink) -> int:
    from datetime import date, timedelta

    from .prices import fill

    start = args.start or (date.fromisoformat(settings.backfill_start) - timedelta(days=400)).isoformat()
    scrips = [s.strip() for s in args.scrips.split(",")] if args.scrips else None
    print(json.dumps(fill(settings, sink, start, scrips)))
    return 0


def cmd_metrics(args, settings, sink) -> int:
    """Print a company's metrics table (metrics.py), worked out by code from the XBRL figures in its memory."""
    from . import metrics

    if args.file:
        dossier = json.loads(Path(args.file).read_text(encoding="utf-8"))
    else:
        dossier = sink.get_dossier(args.scrip)
    if not dossier:
        print(f"no memory for {args.scrip}", file=sys.stderr)
        return 1
    rows = metrics.table(dossier, args.basis)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        print(metrics.render(rows, args.quarters))
        for gap in metrics.missing_lines(dossier):
            print(f"not shown: {gap}")
    return 0


def cmd_post_mortem(args, settings, sink) -> int:
    from .learning import post_mortem

    print(json.dumps(post_mortem(settings, sink, since=args.since)))
    return 0


def cmd_backup(args, settings, sink) -> int:
    """Write every dossier as its own JSON file (text diffs well in git)."""
    out = Path(args.out)
    (out / "memory").mkdir(parents=True, exist_ok=True)
    count = 0
    for scrip in sink.list_dossiers():
        body = sink.get_object(f"memory/{scrip}.json")
        if body is None:
            continue
        data = json.loads(body)
        # encoding: the dossiers are full of rupee signs and Windows writes cp1252 by default,
        # which made every backup on the laptop die on the first one
        (out / "memory" / f"{scrip}.json").write_text(
            json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        count += 1
    (out / "MANIFEST.json").write_text(
        json.dumps({"dossiers": count, "exported_at": now_iso()}, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"dossiers": count, "out": str(out)}))
    return 0


def cmd_missed_jobs(args, settings, sink) -> int:
    """Print the daily workflows GitHub did not start (watchdog.py), one per line, for pipeline.yml to start; with
    --started W, record that W was dispatched (after `gh workflow run` succeeded)."""
    from .watchdog import mark_started, missed

    if getattr(args, "started", None):
        return 0 if mark_started(sink, args.started) else 2
    if getattr(args, "running", None):
        from .watchdog import record_start

        record_start(sink, args.running)
        return 0
    for workflow in missed(sink):
        print(workflow)
    return 0


def cmd_health(args, settings, sink) -> int:
    """Show which AI targets are configured and today's quota usage (no AI calls)."""
    from .ai.gateway import AIGateway

    from datetime import date, timedelta
    usage = sink.usage(utc_day()) + sink.usage((date.fromisoformat(utc_day()) - timedelta(days=1)).isoformat())
    month = sink.usage_month(utc_day()[:7])
    gateway = AIGateway(settings.load_toml("providers.toml"), usage_today=usage, usage_month=month)
    report = {}
    for route, targets in gateway.routes.items():
        report[route] = [
            {"target": t.key, "configured": bool(t.api_key), "spare": t.spare, "weight": t.weight}
            for t in targets
        ]
    print(json.dumps({"ceiling": gateway.ceiling, "routes": report, "health": gateway.health()}, indent=2))
    return 0


def cmd_ai_check(args, settings, sink) -> int:
    """Send one tiny real request to every configured (provider, model) and report each result."""
    import time

    import openai

    from .ai.gateway import AIGateway

    gateway = AIGateway(settings.load_toml("providers.toml"))
    seen, results = set(), []
    for name, route_targets in gateway.routes.items():
        if args.route and name != args.route:
            continue
        for t in route_targets:
            if t.key in seen or (args.provider and t.provider != args.provider):
                continue
            seen.add(t.key)
            row = {"target": t.key}
            if not t.api_key:
                results.append({**row, "result": "SKIPPED", "detail": "no key set"})
                continue
            kwargs = {"model": t.model, "max_tokens": min(t.max_tokens, 400), "temperature": 0,
                      "messages": [{"role": "user", "content": 'Reply with exactly this JSON: {"ok": true}'}]}
            if t.extra_body:
                kwargs["extra_body"] = t.extra_body
            started = time.monotonic()
            try:
                resp = gateway._client(t).chat.completions.create(timeout=min(t.timeout, 120), **kwargs)
                text = (resp.choices[0].message.content or "").strip()
                results.append({**row, "result": "OK", "seconds": round(time.monotonic() - started, 1),
                                "reply": text[-80:], "tokens": getattr(resp.usage, "total_tokens", None)})
            except openai.APIStatusError as exc:
                hint = {401: "key rejected", 403: "key or account not allowed (check plan / activation)",
                        404: "model name not found", 410: "model retired", 429: "rate limited or quota used up"}
                results.append({**row, "result": f"HTTP {exc.status_code}", "detail": hint.get(exc.status_code, ""),
                                "message": str(exc)[:300]})
            except Exception as exc:
                results.append({**row, "result": type(exc).__name__, "message": str(exc)[:300]})
            time.sleep(1)
    for r in results:
        print(f"{r['result']:<10} {r['target']:<55} {r.get('seconds', '')!s:>6}  {r.get('detail') or r.get('reply') or ''}")
        if r.get("message"):
            print(f"{'':<10} {r['message']}")
    return 0 if all(r["result"] in ("OK", "SKIPPED") for r in results) else 1


def cmd_models(args, settings, sink) -> int:
    """Ask each configured provider for its model list and flag configured IDs it no longer serves."""
    from .ai.gateway import AIGateway

    config = settings.load_toml("providers.toml")
    if args.provider:
        # a provider with no route yet (SambaNova, SiliconFlow on 2026-10-20): its own model list, to choose from
        import os

        import openai

        conf = config["providers"][args.provider]
        key = os.environ.get(conf["api_key_env"], "").strip()
        if not key:
            print(json.dumps({args.provider: {"error": f"{conf['api_key_env']} not set"}}))
            return 1
        client = openai.OpenAI(base_url=conf["base_url"], api_key=key, timeout=60)
        try:
            models = sorted(m.id for m in client.models.list())
        except Exception as exc:
            print(json.dumps({args.provider: {"error": f"{type(exc).__name__}: {exc}"[:300]}}))
            return 1
        print(json.dumps({args.provider: [m for m in models if not args.filter or args.filter in m.lower()]}, indent=2))
        return 0
    gateway = AIGateway(config)
    targets: dict[str, dict] = {}
    for route_targets in gateway.routes.values():
        for t in route_targets:
            if t.api_key:
                targets.setdefault(t.provider, {"target": t, "models": set()})["models"].add(t.model)
    report = {}
    for provider, entry in sorted(targets.items()):
        t = entry["target"]
        try:
            # Gemini lists "models/gemini-3.6-flash": every configured Gemini model read as missing (22 Oct)
            available = sorted(m.id.removeprefix("models/") for m in gateway._client(t).models.list())
        except Exception as exc:  # some providers do not serve /models; report and move on
            report[provider] = {"error": f"{type(exc).__name__}: {exc}"[:300], "configured": sorted(entry["models"])}
            continue
        report[provider] = {"configured_missing": sorted(m for m in entry["models"] if m not in available),
                            "configured_ok": sorted(m for m in entry["models"] if m in available),
                            "available": available if args.all else [m for m in available if not args.filter or args.filter in m.lower()]}
    print(json.dumps(report, indent=2))
    return 1 if any(r.get("configured_missing") for r in report.values()) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bse-intel", description=__doc__)
    parser.add_argument("--sink", choices=["local", "platform"], help="override BSE_INTEL_SINK")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="live + backfill run within a time budget")
    p.add_argument("--mode", choices=["live", "backfill", "all"], default="all")
    p.add_argument("--time-budget", type=int, default=2400, help="seconds")
    p.add_argument("--max-backfill-days", type=int, default=5, help="historical days to discover per run")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("release-pruned", help="publish held cards without the points their quote did not carry, no AI")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_release_pruned)
    p = sub.add_parser("release-reviewed", help="publish held cards a blind review cleared, without the points it named")
    p.add_argument("--plan", required=True, help="plan file, e.g. docs/audit/live/release-2026-10-22.json")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_release_reviewed)
    p = sub.add_parser("pause-ai", help="pause the AI pipeline while the nightly memory jobs write (ends by itself)")
    p.add_argument("--minutes", type=int, default=120)
    p.set_defaults(func=cmd_pause_ai)
    p = sub.add_parser("resume-ai", help="end the pause set by pause-ai")
    p.set_defaults(func=cmd_resume_ai)

    p = sub.add_parser("backfill-companies", help="discover and analyse given companies over a range (smoke test)")
    p.add_argument("--scrips", required=True, help="comma-separated BSE scrip codes, e.g. 506525,532776")
    p.add_argument("--from", dest="date_from", help="default BACKFILL_START")
    p.add_argument("--to", dest="date_to", help="default today")
    p.add_argument("--time-budget", type=int, default=6 * 3600)
    p.set_defaults(func=cmd_backfill_companies)

    p = sub.add_parser("sync-to-cloud", help="copy local data (laptop backfill) to the deployed platform")
    p.add_argument("--source", default="http://localhost:5173",
                   help="local Worker URL (default http://localhost:5173), or 'local-sink' for data/local")
    p.add_argument("--source-token", default="dev-local-token", help="INGEST_TOKEN of the local Worker (.dev.vars)")
    p.add_argument("--progress", help="progress file (default data/sync_progress.json)")
    p.set_defaults(func=cmd_sync_to_cloud)

    p = sub.add_parser("retriage", help="queue a company's filings that today's rules no longer drop (after a rule fix)")
    p.add_argument("--scrips", required=True, help="comma-separated BSE scrip codes")
    p.add_argument("--from", dest="date_from", help="default BACKFILL_START")
    p.add_argument("--to", dest="date_to", help="default today")
    p.set_defaults(func=cmd_retriage)

    p = sub.add_parser("discover", help="fetch and triage one day of announcements")
    p.add_argument("--date", required=True)
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("process", help="process queued filings in a date range")
    p.add_argument("--from", dest="date_from", required=True)
    p.add_argument("--to", dest="date_to", required=True)
    p.add_argument("--bulk", action="store_true", help="use the bulk (backfill) AI routes")
    p.add_argument("--time-budget", type=int, default=1800)
    p.add_argument("--news-ids", help="only these filings (comma or whitespace separated, or @file); "
                                      "for re-running an audited sample after a fix")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("annual-xbrl-catchup",
                       help="read annual reports again once NSE lists their XBRL (daily, after the close)")
    p.add_argument("--days", type=int, default=365, help="reports filed in the last N days")
    p.add_argument("--every", type=int, default=7, help="read a company's NSE list at most every N days")
    p.add_argument("--max-companies", type=int, default=150, help="NSE lists read this run")
    p.add_argument("--max-reruns", type=int, default=10, help="annual reports read again this run")
    p.add_argument("--wait", type=int, default=0, help="minutes to wait for another run on this machine to finish")
    p.add_argument("--scrips", help="only these companies (comma-separated scrip codes); default every company")
    p.add_argument("--time-budget", type=int, default=3600)
    p.set_defaults(func=cmd_annual_xbrl_catchup)

    p = sub.add_parser("analyze-pdf", help="analyse a local PDF and print the card")
    p.add_argument("pdf")
    p.add_argument("--scrip", required=True)
    p.add_argument("--company", required=True)
    p.add_argument("--headline", required=True)
    p.add_argument("--category")
    p.add_argument("--subcategory")
    p.add_argument("--industry")
    p.add_argument("--event-type", help="skip Pass 1 and use this event type")
    p.add_argument("--news-id")
    p.set_defaults(func=cmd_analyze_pdf)

    p = sub.add_parser("market-data", help="refresh prices, returns and market caps")
    p.add_argument("--all", action="store_true", help="every company, not only those with cards (laptop, before backfill)")
    p.set_defaults(func=cmd_market_data)
    p = sub.add_parser("price-history", help="store daily prices for point-in-time card footers (laptop, before backfill)")
    p.add_argument("--from", dest="start", help="first day (default: a year before BACKFILL_START)")
    p.add_argument("--scrips", help="comma-separated scrip codes (default: every company)")
    p.set_defaults(func=cmd_price_history)
    p = sub.add_parser("metrics", help="a company's metrics table from its stored XBRL figures, no AI (TODO 22)")
    p.add_argument("--scrip", help="scrip code, read from the sink's memory")
    p.add_argument("--file", help="a dossier JSON file instead of the sink")
    p.add_argument("--basis", choices=["CONSOLIDATED", "STANDALONE"], default="CONSOLIDATED")
    p.add_argument("--quarters", type=int, default=8)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_metrics)
    p = sub.add_parser("post-mortem", help="Loop 1: T+1/T+3/T+5 excess returns after each card")
    p.add_argument("--since", help="revisit cards filed from this date (default: the last 14 days)")
    p.set_defaults(func=cmd_post_mortem)
    p = sub.add_parser("ai-check", help="one tiny real request to every configured AI model, with the result of each")
    p.add_argument("--provider", help="only this provider (groq, nvidia, mistral, zai, cloudflare)")
    p.add_argument("--route", help="only this route's models (e.g. trial_new: the candidates no pipeline step uses)")
    p.set_defaults(func=cmd_ai_check)
    p = sub.add_parser("models", help="list each provider's models and flag configured IDs it no longer serves")
    p.add_argument("--filter", help="only list available models containing this text (e.g. llama, deepseek)")
    p.add_argument("--all", action="store_true", help="list every available model")
    p.add_argument("--provider", help="list this provider's models even when no route uses it yet (sambanova, siliconflow)")
    p.set_defaults(func=cmd_models)
    p = sub.add_parser("sync-companies", help="the company master from NSE's equity list (new listings, names, industry)")
    p.add_argument("--source", choices=("nse", "bse"), default="nse",
                   help="nse (default: online, owner 2026-10-19) or bse (BSE's scrip list; needs an Indian address)")
    p.add_argument("--max-lookups", type=int, default=10_000,
                   help="bse only: most industry lookups this run (one BSE request each, for companies without one)")
    p.add_argument("--refresh-industry", action="store_true", help="bse only: look up every company's industry again")
    p.set_defaults(func=cmd_sync_companies)

    sub.add_parser("sync-universe", help="NSE's equity list joined to the company master: the companies analysed (>= the market-cap floor)"
                   ).set_defaults(func=cmd_sync_universe)
    p = sub.add_parser("governance-sync", help="quarterly governance XBRL into memory (board, SEBI flags, penalties, insider loans), no AI")
    p.add_argument("--pages", type=int, default=1, help="pages of NSE's list (500 rows each) to read back")
    p.add_argument("--scrips", help="only these companies (comma-separated scrip codes), as a measured round does")
    p.add_argument("--max-files", type=int, default=200, help="reports filed this run")
    p.add_argument("--time-budget", type=int, default=1800, help="seconds")
    p.set_defaults(func=cmd_governance_sync)
    p = sub.add_parser("pledge-sync", help="promoter pledge events (NSE SAST Reg 31) into memory, no AI (module 42)")
    p.add_argument("--days", type=int, default=3, help="days of NSE's feed to read (365 for a year)")
    p.add_argument("--scrips", help="only these companies (comma separated)")
    p.add_argument("--time-budget", type=int, default=900)
    p.set_defaults(func=cmd_pledge_sync)
    p = sub.add_parser("deals-sync", help="the latest session's bulk and block deals (NSE) into memory, no AI")
    p.add_argument("--scrips", help="only these companies (comma separated)")
    p.add_argument("--time-budget", type=int, default=300)
    p.set_defaults(func=cmd_deals_sync)
    p = sub.add_parser("deals-backfill", help="past bulk and block deals (NSE's deals history) into memory, no AI")
    p.add_argument("--days", type=int, default=180, help="days back to read, a week at a time")
    p.add_argument("--scrips", help="only these companies (comma separated)")
    p.add_argument("--time-budget", type=int, default=1200)
    p.set_defaults(func=cmd_deals_backfill)
    p = sub.add_parser("insider-sync", help="insider trades (NSE SEBI PIT Reg 7 filings) into memory, no AI")
    p.add_argument("--days", type=int, default=3, help="days of filings to read (180 for six months)")
    p.add_argument("--scrips", help="only these companies (comma separated)")
    p.add_argument("--time-budget", type=int, default=900)
    p.set_defaults(func=cmd_insider_sync)
    p = sub.add_parser("corporate-actions-sync", help="splits, bonuses, dividends, rights, buybacks (NSE) into memory, no AI")
    p.add_argument("--days", type=int, default=30, help="days of ex-dates to read back (2200 for six years)")
    p.add_argument("--scrips", help="only these companies (comma separated)")
    p.add_argument("--time-budget", type=int, default=600)
    p.set_defaults(func=cmd_corporate_actions_sync)
    p = sub.add_parser("refresh-summaries", help="rebuild each company's stored summary from its memory, no AI")
    p.add_argument("--scrips", help="only these companies (comma separated); default every company with memory")
    p.set_defaults(func=cmd_refresh_summaries)
    p = sub.add_parser("export-held", help="every held card to a JSON file, for the live reviews; no AI")
    p.add_argument("--out", default="held.json")
    p.set_defaults(func=cmd_export_held)
    p = sub.add_parser("critic-export", help="the shadow critic's verdicts since a day to a JSON file, for the audit; no AI")
    p.add_argument("--since", required=True, help="critiqued on or after this day (YYYY-MM-DD, IST)")
    p.add_argument("--until", help="and before this day (YYYY-MM-DD)")
    p.add_argument("--out", default="critic.json")
    p.set_defaults(func=cmd_critic_export)
    p = sub.add_parser("apply-verdicts", help="apply the owner's standing Wrong / Right verdicts to the stored cards; no AI")
    p.set_defaults(func=cmd_apply_verdicts)
    p = sub.add_parser("requeue-failed", help="give filings that used every attempt fresh attempts (after a fix); no AI")
    p.add_argument("--since", help="filed on or after this date (YYYY-MM-DD); default --days ago")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--attempts", type=int, help="tries to give back (default all)")
    p.add_argument("--ids", help="instead: these filings (news ids, comma separated), whatever their status, to re-run")
    p.add_argument("--needs-review", action="store_true",
                   help="instead: every card the review queue holds for a fault of its own (held or flagged), plus --ids")
    p.add_argument("--dry-run", action="store_true", help="list what would be requeued, write nothing")
    p.set_defaults(func=cmd_requeue_failed)
    p = sub.add_parser("failed-report", help="every failed filing grouped by reason, with examples; reads only, no AI")
    p.add_argument("--since", help="filed on or after this date (YYYY-MM-DD); default the backfill start")
    p.set_defaults(func=cmd_failed_report)
    p = sub.add_parser("seed-calls", help="last two quarters of call transcripts / presentations into memory; no Gemini, no cards")
    p.add_argument("--scrips", help="only these companies (comma separated)")
    p.add_argument("--restart", action="store_true", help="start again from the largest company")
    p.add_argument("--time-budget", type=int, default=2700, help="seconds")
    p.set_defaults(func=cmd_seed_calls)
    p = sub.add_parser("refresh-card-blocks", help="rebuild every stored card's code blocks from memory, no AI")
    p.add_argument("--scrips", help="only these companies (comma separated); default every card")
    p.add_argument("--dry-run", action="store_true", help="count what would change, write nothing")
    p.set_defaults(func=cmd_refresh_card_blocks)
    p = sub.add_parser("dgtr-sync", help="DGTR anti-dumping / countervailing / safeguard cases into memory, no AI (module 8)")
    p.add_argument("--pages", type=int, default=1, help="list pages per investigation type (15 cases each, ongoing first)")
    p.add_argument("--scrips", help="only these companies (comma separated)")
    p.add_argument("--time-budget", type=int, default=1800)
    p.set_defaults(func=cmd_dgtr_sync)

    p = sub.add_parser("shareholding-sync", help="quarterly shareholding XBRL into memory (promoter, pledge, FII, DII), no AI")
    p.add_argument("--days", type=int, default=10, help="days of NSE's list to read back")
    p.add_argument("--max-files", type=int, default=400, help="patterns filed this run")
    p.add_argument("--time-budget", type=int, default=1800, help="seconds")
    p.set_defaults(func=cmd_shareholding_sync)
    p = sub.add_parser("seed-memory", help="financial and ownership history from NSE's XBRL, no AI (results and shareholding)")
    p.add_argument("--scrips", help="comma-separated company keys (BSE scrip codes, or NSE symbols)")
    p.add_argument("--universe", action="store_true",
                   help="every company in the universe file, resuming after the last one finished (go-live history)")
    p.add_argument("--restart", action="store_true", help="with --universe: start again from the first company")
    p.add_argument("--source", choices=("nse", "bse"), default="nse",
                   help="nse (default) or bse: also read BSE's results archive (needs an Indian address)")
    p.add_argument("--since", default="2020-04-01",
                   help="ignore quarters ending before this date (default: FY21 on, six years as memory keeps)")
    p.add_argument("--shard", help="with --universe: I/N, this runner's share of the companies (each shard keeps its "
                                   "own resume point; N runners on N addresses seed in parallel)")
    p.add_argument("--results-only", action="store_true")
    p.add_argument("--shareholding-only", action="store_true")
    p.set_defaults(func=cmd_seed_memory)

    p = sub.add_parser("nse-speedtest", help="read-only speed test of NSE's listing API and archive host at shrinking pauses (no write, no AI)")
    p.add_argument("--companies", type=int, default=100, help="sample size, drawn by --seed from the universe")
    p.add_argument("--files", type=int, default=80, help="files per download round (each round takes different files)")
    p.add_argument("--seed", type=int, default=26)
    p.add_argument("--json", help="write the whole measurement to this file")
    p.set_defaults(func=cmd_nse_speedtest)

    p = sub.add_parser("restated-report", help="quarters whose restated figure differs from the first filed one, in stored memory (read only, no AI)")
    p.add_argument("--scrips", help="comma-separated company keys or NSE symbols (default: the whole universe)")
    p.add_argument("--json", help="write the counts and every restated figure to this file")
    p.set_defaults(func=cmd_restated_report)

    p = sub.add_parser("memory-recall-export", help="sample recent call transcripts and decks with their full text, memory and card, for the recall audit (read only, no AI)")
    p.add_argument("--out", default="memory-recall", help="folder to write (one subfolder per filing, index.json, README.md)")
    p.add_argument("--limit", type=int, default=20, help="filings in the sample")
    p.add_argument("--seed", type=int, default=26)
    p.add_argument("--days", type=int, default=30, help="cards filed in the last N days")
    p.set_defaults(func=cmd_memory_recall_export)

    p = sub.add_parser("call-memory", help="the call-memory reading of named transcripts and decks (MEMORY_CALL_V2, TODO 83): checked points per document; memory is written only with --apply")
    p.add_argument("--ids", help="news ids, comma separated")
    p.add_argument("--out", default="call-memory", help="folder to write (one <news_id>.json each, summary.json)")
    p.add_argument("--apply", action="store_true", help="also merge the points into each company's memory (call_memory)")
    p.add_argument("--pending", action="store_true", help="read the queue the pipeline fills with MEMORY_CALL_V2 on, oldest first; exit 124 when filings are left")
    p.add_argument("--time-budget", type=int, default=1500, help="seconds; with --pending, no new filing starts after it")
    p.add_argument("--limit", type=int, default=0, help="with --pending, at most this many filings (0 = all)")
    p.set_defaults(func=cmd_call_memory)

    p = sub.add_parser("prediction-units", help="stored targets judged in two different units, and per-share units on other figures (read only, no AI)")
    p.add_argument("--scrips", help="comma-separated company keys or NSE symbols (default: the whole universe)")
    p.add_argument("--json", help="write the report to this file")
    p.set_defaults(func=cmd_prediction_units)

    p = sub.add_parser("nse-selfcheck", help="NSE's own figures in memory against themselves: own file vs later comparative, quarters vs year (read only, no AI)")
    p.add_argument("--scrips", help="comma-separated company keys or NSE symbols (default: the whole universe)")
    p.add_argument("--json", help="write the counts and the worst companies to this file")
    p.add_argument("--csv", help="write every comparison to this CSV file")
    p.add_argument("--referee-csv", help="write the one_quarter_off rows to this CSV, in the shape `pdf-referee --csv` reads (the PDF decides that quarter)")
    p.set_defaults(func=cmd_nse_selfcheck)

    p = sub.add_parser("memory-gaps", help="universe companies lacking exchange-XBRL results quarters in memory; --fill seeds them (no AI)")
    p.add_argument("--scrips", help="comma-separated company keys or NSE symbols (default: the whole universe)")
    p.add_argument("--quarters", type=int, default=8, help="quarters checked, ending at the latest past its filing deadline")
    p.add_argument("--as-of", help="YYYY-MM-DD, instead of today (IST)")
    p.add_argument("--json", help="write the summary and the gap list to this file")
    p.add_argument("--csv", help="write the gap list to this file")
    p.add_argument("--fill", action="store_true", help="seed the results of the companies with gaps from NSE, then re-check")
    p.add_argument("--restart", action="store_true", help="with --fill: try companies an earlier pass already tried")
    p.add_argument("--shard", help="with --fill: I/N, this runner's share of the companies with gaps")
    p.add_argument("--time-budget", type=int, default=17400, help="with --fill: seconds; exit 124 if companies are left")
    p.set_defaults(func=cmd_memory_gaps)

    p = sub.add_parser("screener-fill", help="one-time fill of the quarters memory lacks from screener.in: dry run (default) or --apply (no AI)")
    p.add_argument("--scrips", help="comma-separated company keys or NSE symbols (default: the whole universe)")
    p.add_argument("--quarters", type=int, default=8, help="quarters checked, ending at the latest past its filing deadline")
    p.add_argument("--as-of", help="YYYY-MM-DD, instead of today (IST)")
    p.add_argument("--apply", action="store_true", help="write the fills (by=screener); without it nothing is changed")
    p.add_argument("--shard", help="I/N with N at most 2: this runner's share of the companies with gaps")
    p.add_argument("--restart", action="store_true", help="try companies an earlier run of the same mode already tried")
    p.add_argument("--time-budget", type=int, default=17400, help="seconds; exit 124 if companies are left")
    p.add_argument("--json", help="write the summary to this file")
    p.add_argument("--csv", help="write every proposed fill, with its overlap evidence, to this file")
    p.set_defaults(func=cmd_screener_fill)

    p = sub.add_parser("screener-download", help="one-time download of every company's two screener.in pages, raw, into R2 (no AI, no NSE)")
    p.add_argument("--scrips", help="comma-separated company keys or NSE symbols (default: the whole universe)")
    p.add_argument("--day", help="YYYY-MM-DD the pages are stored under (default today, IST); a page already stored for it is not fetched again")
    p.add_argument("--shard", help="I/N with N at most 2: this runner's share of the companies")
    p.add_argument("--restart", action="store_true", help="ignore this day's list of finished companies (stored pages are still not fetched again)")
    p.add_argument("--time-budget", type=int, default=17400, help="seconds; exit 124 if companies are left")
    p.add_argument("--json", help="write the summary to this file")
    p.set_defaults(func=cmd_screener_download)

    p = sub.add_parser("text-backfill", help="one-time: download the filing text of every stored card with none in R2 (NSE, no AI)")
    p.add_argument("--limit", type=int, help="only the first N cards lacking text (a trial)")
    p.add_argument("--shard", help="I/N with N at most 6: this runner's share of the filings (NSE only)")
    p.add_argument("--source", choices=["nse", "bse"], default="nse",
                   help="bse: only the cards whose file is on BSE (the older ones NSE cannot serve), one runner")
    p.add_argument("--no-ocr", action="store_true", help="skip local OCR: figure and scanned pages keep their text layer only")
    p.add_argument("--restart", action="store_true", help="try filings an earlier run failed on again")
    p.add_argument("--time-budget", type=int, default=17400, help="seconds; exit 124 if filings are left")
    p.add_argument("--json", help="write the summary to this file")
    p.set_defaults(func=cmd_text_backfill)

    p = sub.add_parser("screener-crosscheck", help="read-only: compare memory with the stored screener pages, the official text as referee")
    p.add_argument("--scrips", help="comma-separated company keys or NSE symbols (default: the whole universe)")
    p.add_argument("--day", help="use the pages stored on or before this day (default the newest)")
    p.add_argument("--workers", type=int, default=8, help="companies read at a time")
    p.add_argument("--no-referee", action="store_true", help="skip the look-up in the official text")
    p.add_argument("--json", help="write the summary to this file")
    p.add_argument("--csv", help="write every non-match pair and gap to this file")
    p.add_argument("--referee-csv", help="write the refereed pairs, with the official line and the verdict, to this file")
    p.add_argument("--md", help="write the short markdown report to this file")
    p.set_defaults(func=cmd_screener_crosscheck)

    p = sub.add_parser("screener-referee", help="read-only: NSE's results XBRL as the referee of the screener cross-check's disagreeing pairs")
    p.add_argument("--scrips", help="comma-separated company keys or NSE symbols (default: the whole universe)")
    p.add_argument("--day", help="use the screener pages stored on or before this day (default the newest)")
    p.add_argument("--workers", type=int, default=8, help="companies read at a time for the cross-check (the NSE look-ups are one at a time)")
    p.add_argument("--limit", type=int, help="referee at most this many pairs (a company is finished once started); the rest are not_run")
    p.add_argument("--time-budget", type=int, default=17400, help="seconds; exit 124 if pairs are left")
    p.add_argument("--json", help="write the summary to this file")
    p.add_argument("--csv", help="write every refereed pair, with the official figure and the verdict, to this file")
    p.add_argument("--md", help="write the short markdown summary to this file")
    p.set_defaults(func=cmd_screener_referee)

    p = sub.add_parser("pdf-referee", help="read-only: the filing PDF as the last referee of the pairs the screener-referee left open")
    p.add_argument("--csv", required=True, help="the screener-referee CSV (referee-xbrl.csv)")
    p.add_argument("--limit", type=int, help="referee at most this many pairs (a company is finished once started); the rest are not_run")
    p.add_argument("--time-budget", type=int, default=17400, help="seconds; exit 124 if pairs are left")
    p.add_argument("--no-ocr", action="store_true", help="skip local OCR (figure and scanned pages keep their text layer only)")
    p.add_argument("--json", help="write the summary to this file")
    p.add_argument("--out-csv", help="write every refereed pair, with the PDF's figure and the verdict, to this file")
    p.add_argument("--md", help="write the short markdown summary to this file")
    p.set_defaults(func=cmd_pdf_referee)

    p = sub.add_parser("prune-companies", help="companies not on NSE's lists: dry run (default) or --apply (backup to R2, then remove those with no cards)")
    p.add_argument("--apply", action="store_true", help="back up, then delete; without it nothing is changed")
    p.add_argument("--keep-sme", action="store_true", help="keep NSE Emerge (SME) companies, which the universe does not use")
    p.add_argument("--bse-keep-min-mcap", type=float, default=500.0,
                   help="keep BSE-only companies with a stored market cap of at least this many Cr (default 500; 0 keeps none)")
    p.add_argument("--json", help="write the full report to this file")
    p.add_argument("--csv", help="write the rows (remove / keep) to this file")
    p.set_defaults(func=cmd_prune_companies)

    p = sub.add_parser("bse-verify-kept", help="read-only: ask BSE (ported adapter, paced) about each kept BSE-only company: status, market cap, latest announcement")
    p.add_argument("--min-mcap", type=float, default=500.0, help="the keep line in Cr (as prune-companies --bse-keep-min-mcap)")
    p.add_argument("--limit", type=int, default=0, help="only the first N kept companies (0 = all)")
    p.add_argument("--json", help="write the full result to this file")
    p.add_argument("--csv", help="write one row a company to this file")
    p.set_defaults(func=cmd_bse_verify_kept)

    p = sub.add_parser("label-memory", help="label every item already in memory: file / ai / calc / unknown (no AI; --dry-run counts only)")
    p.add_argument("--scrips", help="comma-separated company keys (default: every stored memory)")
    p.add_argument("--dry-run", action="store_true", help="count per section and label, write nothing")
    p.add_argument("--json", help="write the counts to this file")
    p.add_argument("--restart", action="store_true", help="go over the companies an earlier run finished again")
    p.add_argument("--time-budget", type=int, default=17400, help="seconds; exit 124 if companies are left")
    p.set_defaults(func=cmd_label_memory)

    p = sub.add_parser("backup", help="export dossiers as JSON files")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_backup)

    sub.add_parser("health", help="AI provider configuration and quota usage").set_defaults(func=cmd_health)
    p = sub.add_parser("missed-jobs", help="daily workflows GitHub did not start, for the pipeline to start; no AI")
    p.add_argument("--started", help="record that this workflow file was dispatched today")
    p.add_argument("--running", help="record that this workflow file's run has begun (its first step)")
    p.set_defaults(func=cmd_missed_jobs)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = get_settings()
    if args.sink:
        from dataclasses import replace

        settings = replace(settings, sink=args.sink)
    sink = make_sink(settings)
    from .ai.gateway import AIError
    from .bse import SourceBlockedError

    try:
        code = args.func(args, settings, sink)
    except SourceBlockedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        code = REFUSED
    except AIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        code = 2
    finally:
        _record_writes(sink)
    _record_job(sink, args.command, code)
    return code


def _record_writes(sink) -> None:
    """Every command's D1 writes count toward the day's budget, whichever job made them."""
    from .timeutil import now_iso, utc_day

    try:
        sink.add_uncounted_writes(utc_day(), now_iso())
    except Exception as exc:   # D1 refusing writes (the cap) must not hide the command's own error
        print(f"write count not recorded: {exc}", file=sys.stderr)


# The scheduled jobs (workflows), each recorded when it ends so the System page shows a job that never ran or stopped
# running (owner, 2026-10-20: market-data had never run on GitHub and nobody saw it)
SCHEDULED = {"market-data", "post-mortem", "sync-companies", "refresh-summaries", "governance-sync", "shareholding-sync",
             "pledge-sync", "deals-sync", "deals-backfill", "insider-sync", "corporate-actions-sync", "dgtr-sync", "annual-xbrl-catchup", "backup", "refresh-card-blocks", "seed-memory", "seed-calls"}


def _record_job(sink, command: str, code: int) -> None:
    if command not in SCHEDULED:
        return
    from .timeutil import now_iso

    try:
        now = now_iso()
        sink.kv_set(f"job:{command}", json.dumps({"at": now, "ok": code == 0}), now)
    except Exception as exc:   # the job's own work is done; a missing record only shows it as not run
        print(f"job record not written: {exc}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
