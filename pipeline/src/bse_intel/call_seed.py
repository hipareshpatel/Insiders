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

from .bse import SourceBlockedError
from .nse import FileCapReached
from .models import Filing
from .timeutil import now_iso, today_ist

log = logging.getLogger(__name__)

STATE_KEY = "seed_calls:state"
SAVE_EVERY = 10
SPEND_KEY = "seed_calls:deepseek_tokens"   # DeepSeek tokens (in + out) the seed has used, over every night
DEEPSEEK = "deepseek:deepseek-flash"
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


def deepseek_budget() -> int:
    """The DeepSeek tokens the seed may use in all (owner, 2026-10-20: a $20 prepaid balance); 0 = DeepSeek off."""
    import os

    return int(os.environ.get("SEED_DEEPSEEK_MAX_TOKENS", "40000000"))


def use_seed_route(gateway, deepseek_ok: bool = True) -> None:
    """The card routes for this process only: the seed route's models, Gemini nowhere (pass 1 included); DeepSeek out
    once its token budget is spent."""
    if SEED_ROUTE not in gateway.routes:
        raise RuntimeError(f"providers.toml has no [[routes.{SEED_ROUTE}]]")
    seed = [t for t in gateway.routes[SEED_ROUTE] if deepseek_ok or t.provider != "deepseek"]
    for route in CARD_ROUTES:
        gateway.set_route(route, seed)
    for route in ("pass1", "pass1_bulk"):
        if route in gateway.routes:
            gateway.set_route(route, [t for t in gateway.routes[route] if t.provider != "gemini"])


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


def _seed_company(pipeline, company: dict, start, end, deadline: float) -> dict:
    """One company's call documents into memory; returns its counts and whether the deadline stopped it."""
    sink, scrip = pipeline.sink, company["scrip_code"]
    counts = {"seeded": 0, "skipped": 0, "no_call": 0, "failed": 0, "stopped": False, "refused": False}
    try:
        found = [f for f in pipeline._company_announcements(scrip, start, end)
                 if pipeline.rules.classify(f).event_type == "CONCALL_PRESENTATION"]
    except SourceBlockedError as exc:
        # NSE refused the session: the seed stops and the company is not finished (it was marked finished with nothing
        # read, and so was every company after it, while the workers kept asking NSE: survey, 24 Oct 2026)
        log.warning("call seed: NSE refused (%s); stopping", exc)
        counts["refused"] = counts["stopped"] = True
        return counts
    except Exception as exc:   # one company's list failing never stops the seed
        log.warning("call seed: %s announcements not read: %s", scrip, exc)
        counts["failed"] += 1
        counts["unread"] = True   # not finished: a later run reads its list again
        return counts
    docs = pick(found)
    if not docs:
        counts["no_call"] += 1
    dossier = sink.get_dossier(scrip)
    for filing in docs:
        if time.monotonic() > deadline:
            counts["stopped"] = True
            break
        if _seeded(dossier, filing.news_id):
            counts["skipped"] += 1
            continue
        filing.event_type, filing.route = "CONCALL_PRESENTATION", "FAST_TRACK"   # as the rule book routes calls
        try:
            outcome = pipeline.analyze(filing, bulk=True, memory_complete=True)   # memory written; card dropped
            counts["seeded" if outcome.update.get("status") not in ("FAILED", "PENDING") else "failed"] += 1
        except FileCapReached as exc:   # the run's file cap (F213): this company is not finished; the next run resumes at it
            log.warning("call seed: %s; stopping, the rest waits for the next run", exc)
            counts["capped"] = counts["stopped"] = True
            break
        except SourceBlockedError as exc:
            log.warning("call seed: NSE refused %s (%s); stopping", filing.news_id, exc)
            counts["refused"] = counts["stopped"] = True
            break
        except Exception as exc:
            log.warning("call seed: %s %s not read: %s", scrip, filing.news_id, exc)
            counts["failed"] += 1
        dossier = sink.get_dossier(scrip)
    return counts


def run(pipeline, deadline: float, restart: bool = False, scrips: set[str] | None = None, workers: int = 1) -> dict:
    """Companies in parallel (`workers`; the gateway still holds each model to its own limits: Z.AI's free model to one
    request at a time), each company's documents in date order."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock

    sink = pipeline.sink
    state = {} if restart else json.loads(sink.kv_get(STATE_KEY) or "{}")
    if state.get("done") and not scrips:
        return {"done": True, "companies": 0, "seeded": 0}
    spent = int(sink.kv_get(SPEND_KEY) or 0)
    use_seed_route(pipeline.gateway, deepseek_ok=spent < deepseek_budget())
    finished = set(state.get("finished", [])) if not scrips else set()
    order = [c for c in companies(pipeline) if (not scrips or c["scrip_code"] in scrips) and c["scrip_code"] not in finished]
    start, end = today_ist() - timedelta(days=WINDOW_DAYS), today_ist()
    report = {"companies": 0, "seeded": 0, "skipped": 0, "no_call": 0, "failed": 0, "stopped": False}
    lock = Lock()

    def one(company: dict) -> None:
        if time.monotonic() > deadline or report.get("refused") or report.get("capped"):
            with lock:
                report["stopped"] = True
            return
        counts = _seed_company(pipeline, company, start, end, deadline)
        with lock:
            report["companies"] += 1
            for k in ("seeded", "skipped", "no_call", "failed"):
                report[k] += counts[k]
            if counts["refused"]:
                report["refused"] = True
            if counts.get("capped"):
                report["capped"] = True
            if counts["stopped"]:
                report["stopped"] = True
                return
            if counts.get("unread"):
                report["unread"] = report.get("unread", 0) + 1
                return
            finished.add(company["scrip_code"])
            if not scrips and len(finished) % SAVE_EVERY == 0:   # one D1 write per ten companies, not per company
                sink.kv_set(STATE_KEY, json.dumps({"finished": sorted(finished)}), now_iso())

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(pool.map(one, order))
    usage = getattr(pipeline.gateway, "usage", {}).get(DEEPSEEK)
    used = (usage.input_tokens + usage.output_tokens) if usage else 0
    if used:
        sink.kv_set(SPEND_KEY, str(spent + used), now_iso())
    report["deepseek_tokens"] = {"this_run": used, "all": spent + used, "budget": deepseek_budget()}
    if hasattr(pipeline, "_flush_usage"):
        pipeline._flush_usage()   # the System page shows the seed's requests and tokens by model
    # done only once every company's list was read: one whose list failed is read again by the next run
    if not scrips and not report["stopped"] and not report.get("unread"):
        sink.kv_set(STATE_KEY, json.dumps({"finished": sorted(finished), "done": True}), now_iso())
        report["done"] = True
    elif not scrips:
        sink.kv_set(STATE_KEY, json.dumps({"finished": sorted(finished)}), now_iso())   # where the next run goes on
    log.info("call seed: %s", json.dumps(report))
    return report


NIGHT_UTC_HOURS = range(16, 23)   # a run may start the next one until 22:59 UTC (04:29 IST); the schedule ends at 23:45


def next_run(report: dict, utc_hour: int) -> bool:
    """Whether a seed-calls run starts the next one (seed-calls.yml): it stopped at its budget with companies left and
    read at least one company (a run that reads none would only start another like it), and the night lasts. GitHub
    dropped two of the first four scheduled runs (20 Oct 2026), so each run hands on to the next; the schedule stays as
    the backstop."""
    # a run NSE refused does not start another at once: the schedule tries again later
    more = (bool(report.get("stopped")) and not report.get("done") and not report.get("refused")
            and not report.get("capped") and report.get("companies", 0) > 0)
    return more and utc_hour in NIGHT_UTC_HOURS


def next_run_from_output(path: str, utc_hour: int) -> bool:
    """next_run on the command's printed report: the last line of its output that is a JSON object."""
    lines = [line for line in open(path, encoding="utf-8").read().splitlines() if line.startswith("{")]
    try:
        return next_run(json.loads(lines[-1]), utc_hour) if lines else False
    except ValueError:
        return False
