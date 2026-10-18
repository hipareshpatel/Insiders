"""Cards read again once their event XBRL lands late (PLAN 18 part 3; event_xbrl.py).

A live filing of an event filed with XBRL waits up to event_xbrl.WAIT_MINUTES for its file, then is read from the PDF.
The file follows the PDF by a median of 8 minutes, but 21% come later than an hour and the longest measured took 92
hours (docs/SOURCES.md "Event XBRL"), so a card made from the PDF alone records the app ids of every file of the
company's it was checked against (`card_json.event_xbrl.checked`). This step, at the end of a live run, looks at the
cards of the last event_xbrl.AFTER days made without a file and, when NSE now lists a file of that company of the same
event (or any event, for a filing under a generic subject) that the card was not checked against, puts the filing back
in the queue: the re-run joins the file if the PDF confirms it, and replaces the card.

The lists are the run's own (Pipeline._event_files: one request per type for the days not read yet), so the step adds
few NSE calls. The card stays in the feed until its re-run replaces it; only a re-run that ends without a card has the
old one deleted, as annual_catchup.py does.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from types import SimpleNamespace

from . import event_xbrl
from . import nse as nse_api
from .timeutil import now_iso, today_ist

log = logging.getLogger(__name__)

MAX_CARDS = 500
MAX_RERUNS = 10   # cards read again per run


def new_files(row: dict, files: list) -> list:
    """The company's files in the card's window, of its event, that it was not checked against."""
    try:
        checked = set(json.loads(row.get("checked") or "[]"))
    except (TypeError, ValueError):
        checked = set()
    near = event_xbrl.candidates(files, (row.get("symbol") or "").strip().upper(), datetime.fromisoformat(row["filed_at"]))
    mine = event_xbrl.family(row.get("subject"))
    return [f for f in near if f.app_id not in checked and (f.family == mine or event_xbrl.generic(row.get("subject")))]


def catch_up(pipeline, deadline: float, max_reruns: int = MAX_RERUNS) -> dict:
    """Re-queue and read again the cards whose event XBRL has landed since they were made. Returns what it did."""
    report = {"cards": 0, "rerun": {}, "stopped": None}
    if pipeline.nse is None or getattr(pipeline, "_nse_refused", False):
        report["stopped"] = "NSE not asked (off or refused this run)"
        return report
    since = (today_ist() - event_xbrl.AFTER).isoformat()
    rows = pipeline.sink.query("event_cards_without_xbrl", [since, MAX_CARDS])
    report["cards"] = len(rows)
    due = []
    for row in rows:
        if len(due) >= max_reruns or time.monotonic() >= deadline:
            break
        try:
            files = pipeline._event_files(SimpleNamespace(filed_at=row["filed_at"]))
        except nse_api.SourceBlockedError as exc:
            report["stopped"] = f"NSE refused the session: {exc}"
            return report
        except Exception as exc:  # the catch-up is an extra; the next run looks again
            report["stopped"] = f"{type(exc).__name__}: {exc}"[:200]
            break
        if new_files(row, files):
            due.append(row)
    if not due:
        return report
    from .pipeline import DEADLINE_GRACE_S

    ids = [r["news_id"] for r in due]
    pipeline._exec("filings_update", [{"news_id": i, "status": "PENDING", "attempts": 0, "updated_at": now_iso()} for i in ids])
    log.info("event XBRL landed for %d cards made from the PDF; reading them again: %s", len(ids), ", ".join(ids))
    pipeline.gateway.deadline = deadline + DEADLINE_GRACE_S
    with pipeline._lock:
        pipeline._tried.difference_update(ids)
    days = [r["filing_date"] for r in due]
    outcomes = {o.update["news_id"]: o for o in pipeline.process(min(days), max(days), deadline, bulk=False, only=set(ids))}
    cardless = [i for i in ids if i in outcomes and not outcomes[i].card
                and outcomes[i].update.get("status") in ("NOT_MATERIAL", "DUPLICATE")]
    if cardless:
        pipeline._exec("cards_delete", [{"news_id": i} for i in cardless])
    report["rerun"] = {i: (outcomes[i].update.get("status") if i in outcomes else "left in the queue") for i in ids}
    return report


RESULTS_DAYS = 10        # results cards looked at again for this long (a revision can come days later)
MAX_RESULTS_COMPANIES = 60   # companies' results lists read per run (one NSE request each)


def results_due(row: dict, links: list) -> bool:
    """Whether a results card should be read again: it was made from the PDF alone and its quarter's file is now
    listed (filed from two days before the card to 45 days after, as Pipeline._results_xbrl_url takes it), or it was
    made from a file that a later one (a revision) has replaced for the same quarter and basis."""
    if row.get("xbrl_url"):
        same = [l for l in links if l.period == row.get("period") and l.basis == (row.get("basis") or l.basis)]
        return bool(same) and max(same, key=lambda l: l.filed_at).url != row["xbrl_url"]
    day = datetime.fromisoformat(row["filed_at"]).date()
    from datetime import date as _date

    return any(-2 <= (_date.fromisoformat(l.filed_at[:10]) - day).days <= 45 for l in links)


def results_catch_up(pipeline, deadline: float, max_reruns: int = MAX_RERUNS) -> dict:
    """Read again the NSE results cards whose XBRL has landed, or been revised, since they were made."""
    report = {"cards": 0, "rerun": {}, "stopped": None}
    if pipeline.nse is None or getattr(pipeline, "_nse_refused", False):
        report["stopped"] = "NSE not asked (off or refused this run)"
        return report
    since = (today_ist() - __import__("datetime").timedelta(days=RESULTS_DAYS)).isoformat()
    rows = pipeline.sink.query("results_cards_recent", [since, MAX_CARDS])
    report["cards"] = len(rows)
    due, companies = [], 0
    for row in rows:
        if len(due) >= max_reruns or companies >= MAX_RESULTS_COMPANIES or time.monotonic() >= deadline:
            break
        companies += 1
        probe = SimpleNamespace(scrip_code=row["scrip_code"], symbol=row.get("symbol"), news_id=row["news_id"])
        links = pipeline._results_links(probe)
        if getattr(pipeline, "_nse_refused", False):
            report["stopped"] = "NSE refused the session"
            return report
        if results_due(row, links):
            due.append(row)
    if not due:
        return report
    from .pipeline import DEADLINE_GRACE_S

    ids = [r["news_id"] for r in due]
    pipeline._exec("filings_update", [{"news_id": i, "status": "PENDING", "attempts": 0, "updated_at": now_iso()} for i in ids])
    log.info("results XBRL landed or revised for %d cards; reading them again: %s", len(ids), ", ".join(ids))
    pipeline.gateway.deadline = deadline + DEADLINE_GRACE_S
    with pipeline._lock:
        pipeline._tried.difference_update(ids)
        for r in due:
            pipeline._results_quarters = {k: v for k, v in pipeline._results_quarters.items() if v != r["news_id"]}
    days = [r["filing_date"] for r in due]
    outcomes = {o.update["news_id"]: o for o in pipeline.process(min(days), max(days), deadline, bulk=False, only=set(ids))}
    report["rerun"] = {i: (outcomes[i].update.get("status") if i in outcomes else "left in the queue") for i in ids}
    return report
