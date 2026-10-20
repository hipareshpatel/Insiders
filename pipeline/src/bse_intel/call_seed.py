"""Seed each company's memory from its latest earnings calls and investor presentations (owner, 2026-10-20).

The backfill reaches a company's calls only when it walks that company's history, so most dossiers held little of
what management said: guidance, segment notes, capex plans, targets. This reads, for every universe company, the
transcript (else the presentation) of the last quarter and of the current one from NSE, and puts what they say into
memory through the regular analysis, with its checks. No card is published and no ledger row is written: the
backfill later analyses the same filing in its turn, and memory then replaces this filing's entry.

No Gemini (owner): the card routes are pointed at the `memory_seed` route (free Z.AI and OpenRouter models). Z.AI
allows one request at a time per key, which the live runs share, so the schedule puts this at night. Resumable: the
last company finished is kept in kv, and a company whose call is already in its timeline is skipped.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import timedelta

from .models import Filing
from .timeutil import now_iso, today_ist

log = logging.getLogger(__name__)

STATE_KEY = "seed_calls:state"
WINDOW_DAYS = 200     # the last quarter's calls (filed July-August for June) and the current quarter's
PER_COMPANY = 2       # one document per quarter: the transcript, else the presentation
SEED_ROUTE = "memory_seed"
CARD_ROUTES = ("pass2", "pass2_bulk", "pass2_long")
_TRANSCRIPT = ("transcript", "conference call", "earnings call", "concall", "con call")


def pick(filings: list[Filing], limit: int = PER_COMPANY) -> list[Filing]:
    """At most one document a month-pair (a quarter's call season), newest first; a transcript beats a presentation
    of the same season, since it carries what management said, not only the slides."""
    def is_transcript(f: Filing) -> bool:
        text = f"{f.headline} {f.subject}".lower()
        return any(w in text for w in _TRANSCRIPT)

    seasons: dict[str, Filing] = {}
    for f in sorted(filings, key=lambda f: f.filed_at, reverse=True):
        month = int(f.filed_at[5:7])
        season = f"{f.filed_at[:4]}-{(month - 1) // 3}"   # calls for a quarter come in the quarter after it
        held = seasons.get(season)
        if held is None or (is_transcript(f) and not is_transcript(held)):
            seasons[season] = f
    return sorted(seasons.values(), key=lambda f: f.filed_at, reverse=True)[:limit]


def _seeded(dossier: dict | None, news_id: str) -> bool:
    return any(t.get("news_id") == news_id for t in (dossier or {}).get("timeline", []))


def use_seed_route(gateway) -> None:
    """The card routes for this process only: the seed route's models, Gemini nowhere (pass 1 included)."""
    if SEED_ROUTE not in gateway.routes:
        raise RuntimeError(f"providers.toml has no [[routes.{SEED_ROUTE}]]")
    for route in CARD_ROUTES:
        gateway.routes[route] = list(gateway.routes[SEED_ROUTE])
    for route in ("pass1", "pass1_bulk"):
        if route in gateway.routes:
            gateway.routes[route] = [t for t in gateway.routes[route] if t.provider != "gemini"]


def companies(pipeline) -> list[dict]:
    """The universe, largest market cap first."""
    from . import universe

    included = universe.load_nse(pipeline.sink).included
    rows, after = [], ""
    while True:
        page = pipeline.sink.query("companies_universe", [after, 500])
        if not page:
            break
        rows += [r for r in page if r["scrip_code"] in included]
        after = page[-1]["scrip_code"]
        if len(page) < 500:
            break
    return sorted(rows, key=lambda r: -(r.get("market_cap_cr") or 0))


def run(pipeline, deadline: float, restart: bool = False, scrips: set[str] | None = None) -> dict:
    sink = pipeline.sink
    state = {} if restart else json.loads(sink.kv_get(STATE_KEY) or "{}")
    if state.get("done") and not scrips:
        return {"done": True, "companies": 0, "seeded": 0}
    use_seed_route(pipeline.gateway)
    order = [c for c in companies(pipeline) if not scrips or c["scrip_code"] in scrips]
    finished = set(state.get("finished", [])) if not scrips else set()
    start, end = today_ist() - timedelta(days=WINDOW_DAYS), today_ist()
    report = {"companies": 0, "seeded": 0, "skipped": 0, "no_call": 0, "failed": 0, "stopped": False}
    for company in order:
        scrip = company["scrip_code"]
        if scrip in finished:
            continue
        if time.monotonic() > deadline:
            report["stopped"] = True
            break
        report["companies"] += 1
        try:
            found = [f for f in pipeline._company_announcements(scrip, start, end)
                     if pipeline.rules.classify(f).event_type == "CONCALL_PRESENTATION"]
        except Exception as exc:   # one company's list failing never stops the seed
            log.warning("call seed: %s announcements not read: %s", scrip, exc)
            report["failed"] += 1
            continue
        docs = pick(found)
        if not docs:
            report["no_call"] += 1
        dossier = sink.get_dossier(scrip)
        for filing in docs:
            if time.monotonic() > deadline:
                report["stopped"] = True
                break
            if _seeded(dossier, filing.news_id):
                report["skipped"] += 1
                continue
            filing.event_type, filing.route = "CONCALL_PRESENTATION", "FAST_TRACK"   # as the rule book routes calls
            try:
                outcome = pipeline.analyze(filing, bulk=True, memory_complete=True)   # memory written; card dropped
                report["seeded" if outcome.update.get("status") not in ("FAILED", "PENDING") else "failed"] += 1
            except Exception as exc:
                log.warning("call seed: %s %s not read: %s", scrip, filing.news_id, exc)
                report["failed"] += 1
            dossier = sink.get_dossier(scrip)
        if report["stopped"]:
            break
        finished.add(scrip)
        if not scrips:
            sink.kv_set(STATE_KEY, json.dumps({"finished": sorted(finished)}), now_iso())
    if not scrips and not report["stopped"]:
        sink.kv_set(STATE_KEY, json.dumps({"finished": sorted(finished), "done": True}), now_iso())
        report["done"] = True
    log.info("call seed: %s", json.dumps(report))
    return report
