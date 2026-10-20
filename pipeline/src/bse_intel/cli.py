"""Command-line entry point: ``python -m bse_intel <command>``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

from . import raw
from .settings import get_settings
from .sinks import make_sink
from .timeutil import now_iso, today_ist, utc_day


def _pipeline(settings, sink):
    from .pipeline import build_pipeline

    return build_pipeline(settings, sink)


def cmd_run(args, settings, sink) -> int:
    stats = _pipeline(settings, sink).run(args.mode, args.time_budget, args.max_backfill_days)
    print(json.dumps(stats.as_dict(), indent=2))
    return 0 if stats.status in ("OK", "PARTIAL") else 1  # a run ending in ERROR fails the workflow


def cmd_backfill_companies(args, settings, sink) -> int:
    scrips = [s.strip() for s in args.scrips.split(",") if s.strip()]
    stats = _pipeline(settings, sink).backfill_companies(
        scrips, date.fromisoformat(args.date_from or settings.backfill_start),
        date.fromisoformat(args.date_to) if args.date_to else date.today(), args.time_budget)
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
    day_to = date.fromisoformat(args.date_to) if args.date_to else date.today()
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
    return 2 if (report["stopped"] or "").startswith("NSE refused") else 0


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
    pipeline.bse.download = lambda url: Path(args.pdf).read_bytes()  # type: ignore[method-assign]
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


def cmd_governance_sync(args, settings, sink) -> int:
    """The quarterly governance XBRL of the universe's companies into memory (governance_memory.py), no AI."""
    from . import governance_memory

    pipeline = _pipeline(settings, sink)
    scrips = {s.strip() for s in (args.scrips or "").split(",") if s.strip()} or None
    report = governance_memory.sync(pipeline, time.monotonic() + args.time_budget, pages=args.pages, max_files=args.max_files,
                                    scrips=scrips)
    print(json.dumps(report))
    return 0


def cmd_pledge_sync(args, settings, sink) -> int:
    """Promoter encumbrance events (NSE's SAST Reg 31 feed) into memory (pledges.py, module 42), no AI."""
    from . import pledges

    pipeline = _pipeline(settings, sink)
    scrips = {s.strip() for s in (args.scrips or "").split(",") if s.strip()} or None
    report = pledges.sync(pipeline, time.monotonic() + args.time_budget, days=args.days, scrips=scrips)
    print(json.dumps(report, indent=2))
    return 2 if (report["stopped"] or "").startswith("NSE refused") else 0


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
    print(json.dumps(card_refresh.run(_pipeline(settings, sink), scrips, dry_run=args.dry_run), indent=2))
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


def cmd_requeue_failed(args, settings, sink) -> int:
    """Filings that used every attempt, set PENDING again with fresh attempts (requeue.py), after a fix. No AI."""
    from datetime import timedelta

    from . import requeue
    from .timeutil import today_ist

    if args.ids:
        ids = [i.strip() for i in args.ids.replace("\n", ",").split(",")]
        print(json.dumps(requeue.requeue_ids(sink, ids, settings.max_attempts, args.dry_run), ensure_ascii=False))
        return 0
    since = args.since or (today_ist() - timedelta(days=args.days)).isoformat()
    print(json.dumps(requeue.requeue(sink, since, settings.max_attempts, args.attempts, args.dry_run), ensure_ascii=False))
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
    return 0


def cmd_seed_memory(args, settings, sink) -> int:
    """Financial and ownership history from XBRL, with no AI call (see seed.py). Results and shareholding come from
    NSE (owner, 2026-10-19: everything on NSE); `--source bse` adds BSE's results archive (needs an Indian address)."""
    import contextlib

    from .bse import BseClient
    from .nse import NseClient, SourceBlockedError
    from .seed import SeedStats, seed_results, seed_shareholding

    log = logging.getLogger("bse_intel.seed")
    resume_key = "seed:universe_last"
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
        scrips = [s for s in sorted(nse_universe.included) if s > done_through]
        log.info("seed: %d universe companies to go (after %r)", len(scrips), done_through)
    else:
        scrips = [s.strip() for s in (args.scrips or "").split(",") if s.strip()]
        if not scrips:
            print("Name the companies with --scrips, or seed the whole universe with --universe.")
            return 2
    stats = SeedStats()
    cache_root = settings.text_cache_dir
    with (BseClient() if args.source == "bse" else contextlib.nullcontext()) as bse, NseClient() as nse:
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
                    break  # NSE limits by IP: stop, do not press on
                except Exception as exc:
                    stats.failures.append(f"{scrip} shareholding: {type(exc).__name__}: {exc}"[:200])
                    log.warning("seed %s shareholding failed: %s", scrip, exc)
            elif not args.results_only:
                stats.failures.append(f"{scrip}: no NSE symbol stored")
            log.info("seed: %s", stats.line())
            if args.universe:
                sink.kv_set(resume_key, scrip, now_iso())
    print(json.dumps({"companies": stats.companies, "results_files": stats.results_files,
                      "results_periods": stats.results_periods, "shareholding_files": stats.shareholding_files,
                      "shareholding_periods": stats.shareholding_periods, "skipped": stats.skipped,
                      "failures": stats.failures[:20]}, ensure_ascii=False))
    return 0


def cmd_price_history(args, settings, sink) -> int:
    from datetime import date, timedelta

    from .prices import fill

    start = args.start or (date.fromisoformat(settings.backfill_start) - timedelta(days=400)).isoformat()
    scrips = [s.strip() for s in args.scrips.split(",")] if args.scrips else None
    print(json.dumps(fill(settings, sink, start, scrips)))
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
            available = sorted(m.id for m in gateway._client(t).models.list())
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
    p = sub.add_parser("refresh-summaries", help="rebuild each company's stored summary from its memory, no AI")
    p.add_argument("--scrips", help="only these companies (comma separated); default every company with memory")
    p.set_defaults(func=cmd_refresh_summaries)
    p = sub.add_parser("export-held", help="every held card to a JSON file, for the live reviews; no AI")
    p.add_argument("--out", default="held.json")
    p.set_defaults(func=cmd_export_held)
    p = sub.add_parser("requeue-failed", help="give filings that used every attempt fresh attempts (after a fix); no AI")
    p.add_argument("--since", help="filed on or after this date (YYYY-MM-DD); default --days ago")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--attempts", type=int, help="tries to give back (default all)")
    p.add_argument("--ids", help="instead: these filings (news ids, comma separated), whatever their status, to re-run")
    p.add_argument("--dry-run", action="store_true", help="list what would be requeued, write nothing")
    p.set_defaults(func=cmd_requeue_failed)
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
    p.add_argument("--since", default="2023-01-01", help="ignore quarters filed before this date")
    p.add_argument("--results-only", action="store_true")
    p.add_argument("--shareholding-only", action="store_true")
    p.set_defaults(func=cmd_seed_memory)

    p = sub.add_parser("backup", help="export dossiers as JSON files")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_backup)

    sub.add_parser("health", help="AI provider configuration and quota usage").set_defaults(func=cmd_health)

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
    except (AIError, SourceBlockedError) as exc:
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
             "pledge-sync", "dgtr-sync", "annual-xbrl-catchup", "backup", "refresh-card-blocks", "seed-memory", "seed-calls"}


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
