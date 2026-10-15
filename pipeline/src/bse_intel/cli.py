"""Command-line entry point: ``python -m bse_intel <command>``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

from .settings import get_settings
from .sinks import make_sink
from .timeutil import now_iso, utc_day


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


def cmd_discover(args, settings, sink) -> int:
    pipeline = _pipeline(settings, sink)
    count = pipeline.discover(date.fromisoformat(args.date))
    print(json.dumps({"discovered": count, **pipeline.stats.as_dict()}, indent=2))
    return 0


def cmd_process(args, settings, sink) -> int:
    pipeline = _pipeline(settings, sink)
    pipeline.process(args.date_from, args.date_to, time.monotonic() + args.time_budget, bulk=args.bulk)
    print(json.dumps(pipeline.stats.as_dict(), indent=2))
    return 0


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
    print(json.dumps({"companies_updated": updated, "outside_universe": universe.build(settings, sink),
                      "yahoo_missing": coverage.get("missing"), "yahoo_missing_pct": coverage.get("missing_pct"),
                      "missing_sample": [m["scrip_code"] for m in coverage.get("sample", [])[:30]]}))
    return 0


def cmd_sync_companies(args, settings, sink) -> int:
    from .bse import BseClient, fetch_scrip_list
    from .prompts.engine import PromptEngine

    engine = PromptEngine(settings)
    with BseClient() as client:
        rows = fetch_scrip_list(client)
    now = now_iso()
    for row in rows:
        row["sector"] = engine.sector_for(row.get("industry")).name
        row["updated_at"] = now
    written = sink.execute("companies_upsert", rows)
    sink.add_writes(utc_day(), written, now)
    from . import universe

    print(json.dumps({"companies": len(rows), "rows_written": written, "outside_universe": universe.build(settings, sink)}))
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
        (out / "memory" / f"{scrip}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
        count += 1
    (out / "MANIFEST.json").write_text(json.dumps({"dossiers": count, "exported_at": now_iso()}, indent=1) + "\n")
    print(json.dumps({"dossiers": count, "out": str(out)}))
    return 0


def cmd_health(args, settings, sink) -> int:
    """Show which AI targets are configured and today's quota usage (no AI calls)."""
    from .ai.gateway import AIGateway

    usage = sink.usage(utc_day())
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
    for route_targets in gateway.routes.values():
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

    gateway = AIGateway(settings.load_toml("providers.toml"))
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

    p = sub.add_parser("discover", help="fetch and triage one day of announcements")
    p.add_argument("--date", required=True)
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("process", help="process queued filings in a date range")
    p.add_argument("--from", dest="date_from", required=True)
    p.add_argument("--to", dest="date_to", required=True)
    p.add_argument("--bulk", action="store_true", help="use the bulk (backfill) AI routes")
    p.add_argument("--time-budget", type=int, default=1800)
    p.set_defaults(func=cmd_process)

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
    p.set_defaults(func=cmd_ai_check)
    p = sub.add_parser("models", help="list each provider's models and flag configured IDs it no longer serves")
    p.add_argument("--filter", help="only list available models containing this text (e.g. llama, deepseek)")
    p.add_argument("--all", action="store_true", help="list every available model")
    p.set_defaults(func=cmd_models)
    sub.add_parser("sync-companies", help="load BSE's active equity scrip list").set_defaults(func=cmd_sync_companies)

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
        return args.func(args, settings, sink)
    except (AIError, SourceBlockedError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
