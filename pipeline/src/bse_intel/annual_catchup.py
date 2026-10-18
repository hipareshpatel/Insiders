"""Annual reports read again once their XBRL reaches NSE (F57).

A report is read the day its PDF is filed, but the company's annual-report XBRL reaches NSE weeks to months later
(Kanoria FY25: the PDF on 2 Sep 2025, the XBRL on 22 Dec 2025; eMudhra 2.5 months, Heritage 6 weeks), so on the
daily path the card is made from the PDF alone. This step finds the annual-report cards made without the table,
reads NSE's list for each company and, when it lists a file for the report's year that the card was not read
with, puts the filing back in the queue and reads it again. A file counts as new when it was broadcast after the
pipeline last read the list in full for the card (`card_json.annual_xbrl_checked`), or at all when it never did
(NSE off, refused or failing then; cards made before the stamp). A file whose figures are not in the PDF is
refused again on the re-run, and the card's new stamp keeps it from being tried a third time.

It is a command of its own, `annual-xbrl-catchup`, run once a day after the close (PLAN, phase 5), not part of
`run`:
* NSE limits by IP address. The check is one list request per company with a card waiting, a few hundred from
  September to December, and `run` fires every 15-30 minutes and already calls NSE for every annual report it
  reads. Once a day keeps the calls few and apart; a refusal here does not cost `run` its annual-report tables.
* The files arrive weeks to months late, so checking more than daily gains nothing.
* Each re-run is a whole annual report on the long-context route (3x the page budget), which would compete with
  live filings for `run`'s time budget and its free quotas. After the close the live queue is quiet.

It starts only when nothing else on this laptop is calling NSE or writing to the database: no other bse_intel
command or pipeline script among the running processes, and no log in data/logs written in the last ten minutes
(scripts/laptop.ps1 logs every command there). Re-runs go on the backfill routes with every paid provider left
out (`paid = true` in providers.toml), so the step costs nothing even where the DeepSeek key is loaded (D24).

The card stays in the feed until its re-run replaces it: a re-run left in the queue (quota, time) keeps the old
card, and the queue reads it later. Only a re-run that ends without a card (not material, a duplicate) has its
old card deleted. The reset is otherwise scripts/rerun.py's: status PENDING, attempts 0, the error cleared.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import annual_xbrl
from . import nse as nse_api
from .timeutil import now_iso, today_ist, utc_day

log = logging.getLogger(__name__)

NEXT_LOOK_KEY = "annual_xbrl:next_look"   # kv: symbol -> the day its list is read again
HORIZON_DAYS = 365       # a report filed longer ago than this is not looked at again: the next one is due
EVERY_DAYS = 7           # a company's list is read at most this often
EMPTY_EVERY_DAYS = 28    # ... and this often while NSE lists no file of any year for it (most are not on NSE)
MAX_COMPANIES = 150      # lists read per run: about ten minutes at NSE's 3-5 s pace
MAX_RERUNS = 10          # annual reports read again per run
MAX_CARDS = 5000
QUIET_MINUTES = 10       # a log written this recently is a run still going, or one that has just stopped calling NSE
OWN_LOG = "annual-xbrl-catchup-"
# Another pipeline command or script: `python -m bse_intel ...`, `python scripts/rerun.py`
_PIPELINE_CMD = re.compile(r"bse_intel|bse-intel|scripts[\\/][\w.-]+\.py", re.I)


def other_runs(log_dir: Path, processes=None, now: float | None = None) -> list[str]:
    """What else on this machine may be calling NSE or writing to the database now: another bse_intel command or
    pipeline script among the running processes, or a log in `log_dir` written in the last QUIET_MINUTES.
    Empty when the slot is free."""
    busy = []
    mine = {os.getpid(), os.getppid()}   # a venv's python.exe starts the real interpreter as its child
    for pid, command in (processes or _python_processes)():
        if pid not in mine and _PIPELINE_CMD.search(command):
            busy.append(f"process {pid}: {command[:200]}")
    now = time.time() if now is None else now
    if log_dir.is_dir():
        for path in sorted(log_dir.glob("*.log")):
            if path.name.startswith(OWN_LOG):
                continue
            age = now - path.stat().st_mtime
            if age < QUIET_MINUTES * 60:
                busy.append(f"log {path.name} written {age / 60:.0f} min ago")
    return busy


def _python_processes() -> list[tuple[int, str]]:
    """(pid, command line) of each python process: /proc on Linux, CIM through PowerShell on Windows. Empty when
    they cannot be listed; the log check still applies."""
    if sys.platform == "win32":
        script = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                  "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("could not list running processes (%s); going by the logs alone", exc)
            return []
        rows = (line.partition("\t") for line in out.splitlines())
        return [(int(pid), command.strip()) for pid, _, command in rows if pid.strip().isdigit()]
    found = []
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
        except OSError:
            continue
        if "python" in command:
            found.append((int(entry.name), command))
    return found


def wait_for_quiet(log_dir: Path, wait_s: float, sleep=time.sleep, check=None) -> list[str]:
    """Wait up to `wait_s` for the slot to be free. Returns what is still running (empty: go ahead)."""
    end = time.monotonic() + wait_s
    while True:
        busy = (check or other_runs)(log_dir)
        if not busy or time.monotonic() >= end:
            return busy
        log.info("waiting for the slot: %s", busy[0])
        sleep(60)


def _instant(text: str) -> datetime:
    return datetime.fromisoformat(text)


def new_files(card: dict, listing: list) -> list:
    """The files NSE lists for the card's report year that the card was not read with."""
    files = annual_xbrl.pick(listing, annual_xbrl.report_year(card.get("headline") or "", card.get("subject") or "",
                                                              card["filed_at"]))
    checked = card.get("checked")
    if not checked:
        return files
    return [f for f in files if f.filed_at and _instant(f.filed_at) > _instant(checked)]


def _free_routes_only(pipeline) -> list[str]:
    """Leave every paid provider out of this run's routes: the step runs every day (CLAUDE.md, D24)."""
    paid = [name for name, conf in pipeline.settings.load_toml("providers.toml").get("providers", {}).items()
            if conf.get("paid")]
    for name in paid:
        pipeline.gateway.disabled_providers[name] = "paid; the daily annual-report catch-up uses free routes only"
    return paid


def _verdict(outcome) -> str:
    if outcome is None:
        return "left in the queue (time budget)"
    status = outcome.update.get("status")
    if status == "ANALYZED" and outcome.card:
        table = "with the table" if outcome.card["card"].get("annual_xbrl") else "without the table"
        return f"{'held' if outcome.card.get('held') else 'published'} {table}"
    if status in ("NOT_MATERIAL", "DUPLICATE"):
        return f"no card now ({status.lower()}: {outcome.update.get('reason') or ''})".strip()
    return f"{status.lower()}: {outcome.update.get('last_error') or ''}"[:200]


def catch_up(pipeline, deadline: float, horizon_days: int = HORIZON_DAYS, every_days: int = EVERY_DAYS,
             max_companies: int = MAX_COMPANIES, max_reruns: int = MAX_RERUNS) -> dict:
    """Read NSE's list for the companies whose annual-report cards lack the table, and read again the reports
    whose year now has a file. Returns what was looked at and what each re-run made."""
    from .pipeline import DEADLINE_GRACE_S

    report = {"cards": 0, "companies": 0, "companies_due": 0, "lists_read": 0, "errors": [],
              "rerun": {}, "stopped": None}
    sink, nse = pipeline.sink, pipeline.nse
    if nse is None:
        report["stopped"] = "NSE_ANNUAL_XBRL is off"
        return report
    report["paid_left_out"] = _free_routes_only(pipeline)
    today = today_ist()
    rows = sink.query("annual_cards_without_xbrl", [(today - timedelta(days=horizon_days)).isoformat(), MAX_CARDS])
    by_symbol: dict[str, list[dict]] = {}
    for row in rows:
        by_symbol.setdefault(row["symbol"].strip().upper(), []).append(row)
    next_look = {s: d for s, d in json.loads(sink.kv_get(NEXT_LOOK_KEY) or "{}").items() if d > today.isoformat()}
    due = sorted((s for s in by_symbol if s not in next_look), key=lambda s: by_symbol[s][0]["filed_at"])
    report.update(cards=len(rows), companies=len(by_symbol), companies_due=len(due))

    rerun: list[dict] = []
    for symbol in due[:max_companies]:
        if len(rerun) >= max_reruns or time.monotonic() >= deadline:
            break
        try:
            listing = nse.annual_reports(symbol)
        except nse_api.SourceBlockedError as exc:
            report["stopped"] = f"NSE refused the session: {exc}"
            break
        except Exception as exc:  # one company's list must not end the step
            report["errors"].append(f"{symbol}: {type(exc).__name__}: {exc}"[:200])
            continue
        report["lists_read"] += 1
        with pipeline._lock:
            pipeline._annual_lists[symbol] = (listing, now_iso())   # the re-run reads the same list
        found = [row for row in by_symbol[symbol] if new_files(row, listing)]
        taken = found[:max_reruns - len(rerun)]
        rerun += taken
        if len(taken) == len(found):   # otherwise it stays due for the next run
            wait = every_days if listing else max(every_days, EMPTY_EVERY_DAYS)
            next_look[symbol] = (today + timedelta(days=wait)).isoformat()
    if report["stopped"]:
        # NSE is refusing: a re-run now would read the PDF alone again. Those companies stay due.
        rerun_symbols = {r["symbol"].strip().upper() for r in rerun}
        next_look = {s: d for s, d in next_look.items() if s not in rerun_symbols}
        rerun = []
    pipeline._kv_set(NEXT_LOOK_KEY, json.dumps(dict(sorted(next_look.items())), separators=(",", ":")))

    if rerun:
        ids = [r["news_id"] for r in rerun]
        pipeline._exec("filings_update", [{"news_id": i, "status": "PENDING", "attempts": 0, "updated_at": now_iso()}
                                          for i in ids])
        log.info("annual-report XBRL now listed for %d cards; reading them again: %s", len(ids), ", ".join(ids))
        pipeline.gateway.deadline = deadline + DEADLINE_GRACE_S
        days = [r["filing_date"] for r in rerun]
        outcomes = {o.update["news_id"]: o for o in pipeline.process(min(days), max(days), deadline, bulk=True,
                                                                     only=set(ids))}
        cardless = [i for i in ids if i in outcomes and not outcomes[i].card
                    and outcomes[i].update.get("status") in ("NOT_MATERIAL", "DUPLICATE")]
        pipeline._exec("cards_delete", [{"news_id": i} for i in cardless])
        report["rerun"] = {i: _verdict(outcomes.get(i)) for i in ids}
        report["stats"] = pipeline.stats.as_dict()
    sink.add_writes(utc_day(), pipeline.stats.d1_rows_written, now_iso())
    return report
