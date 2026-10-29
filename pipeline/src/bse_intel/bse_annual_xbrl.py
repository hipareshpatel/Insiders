"""Annual-report XBRL from BSE for the years NSE does not list (owner, 29 Oct 2026: "go for 100 but ensure to save them so next
run required less 100 files"). No AI, no NSE, no memory write.

NSE lists annual-report XBRL from FY25 only, and before NSE's circular NSE/CML/2026/08 (20 Apr 2026) a company could file it with
BSE alone. BSE's XBRL filings page (bseindia.com/corporates/xbrldetails, category 7 "Annual Reports (Pdf & XBRL)") lists them:

    GET https://api.bseindia.com/BseIndiaAPI/api/GetCorXbrlDetails_ng/w?Flag=7&scripcode=<code>&fromdate=YYYY/MM/DD&todate=YYYY/MM/DD

(the date range is the annual report's own filing date; the answer repeats joined rows, a company's own are those whose
``fld_scripcode`` is its code), and a file is at

    https://www.bseindia.com/XBRLFILES/AnnualReportUploadDocument/<fld_filename>

(measured 29 Oct 2026: 9 of 10 companies sampled among those lacking an NSE file for FY24 or FY25 have it on BSE, 6 also FY23;
Onida FY25 parses with ``xbrl_facts.parse_annual_facts`` as it is). Through the ported adapter (adapters/bse.py: its headers,
pace and stop on 401/403/429). Each file goes in R2 as it came, gzipped, at

    raw/bse-annual-xbrl/<scrip>/<fld_filename>.gz

and its facts as the annual document ``raw/xbrl-facts/<scrip>/annual-<FY>-<basis>.json.gz`` unless one is stored already (the
NSE file stays first). A company's BSE list is kept too (``.../list.json``), and a stored file is read from R2, never asked
again: a later run downloads only what is still missing. A file counts toward the run's file cap (file_cap.py).
"""

from __future__ import annotations

import gzip
import json
import time
from datetime import date

from . import xbrl_facts as xf

PREFIX = "raw/bse-annual-xbrl/"
LIST = "GetCorXbrlDetails_ng/w"
FILE_URL = "https://www.bseindia.com/XBRLFILES/AnnualReportUploadDocument/{name}"
CATEGORY = "7"                      # "Annual Reports (Pdf & XBRL)" (GetCorXbrlDropdown_ng)
# FY24 on: the FY24 report's comparative column is FY23, the oldest year the screener comparison reads (100-file test, run
# 40817278550: 44 of the 100 files were FY21-FY22 reports, never read; a file is about 5 MB, 0.5 MB stored)
FIRST_YEAR_END = date(2024, 3, 31)
LIST_FRESH_DAYS = 7


def list_key(scrip: str) -> str:
    return f"{PREFIX}{scrip}/list.json"


def file_key(scrip: str, name: str) -> str:
    return f"{PREFIX}{scrip}/{name}.gz"


def own_files(rows: list[dict], scrip: str) -> list[dict]:
    """The company's own annual-report XBRL files in the list's answer, once each: {"name", "year_end", "xbrl_date"}."""
    seen, out = set(), []
    for x in rows or []:
        name = (x.get("fld_filename") or "").strip()
        if str(x.get("fld_scripcode")) != str(scrip) or not name.lower().endswith(".xml") or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "year_end": (x.get("enddate") or "")[:10], "xbrl_date": (x.get("xbrldate") or "")[:10]})
    return sorted(out, key=lambda f: (f["year_end"], f["name"]))


def _fy(year_end: str) -> str | None:
    try:
        return xf.fy_of(date.fromisoformat(year_end))
    except ValueError:
        return None


def wanted(files: list[dict], stored: set[str], scrip: str) -> list[dict]:
    """The files, from FY24 on, of a year no annual document is stored for (either basis), judged once for the company's files
    together, so a year's standalone and consolidated files both come in the run that fills it."""
    # a year begun from BSE (one of its files stored) is finished by the next run, though its first document is stored
    begun = {_fy(f["year_end"]) for f in files if file_key(scrip, f["name"]) in stored}
    out = []
    for f in files:
        fy = _fy(f["year_end"])
        if not fy or f["year_end"] < FIRST_YEAR_END.isoformat():
            continue
        if fy in begun:
            if file_key(scrip, f["name"]) not in stored:
                out.append(dict(f, fy=fy))
        elif not any(k.startswith(f"{xf.PREFIX}{scrip}/annual-{fy}-") for k in stored):
            out.append(dict(f, fy=fy))
    return out


def _listing(client, sink, scrip: str, stored: set[str], today: date, totals: dict) -> list[dict]:
    key = list_key(scrip)
    if key in stored and (blob := sink.get_object(key)):
        kept = json.loads(blob)
        if (today - date.fromisoformat(kept.get("asked", "2000-01-01"))).days < LIST_FRESH_DAYS:
            totals["lists_reused"] += 1
            return kept.get("files") or []
    body = client.get(LIST, {"Flag": CATEGORY, "scripcode": scrip, "fromdate": "2020/04/01",
                             "todate": today.strftime("%Y/%m/%d")}, "bse-annual-xbrl-list")
    totals["lists_asked"] += 1
    try:
        rows = (json.loads(body) or {}).get("Table") or []
    except ValueError:
        rows = []
    files = own_files(rows, scrip)
    sink.put_object(key, json.dumps({"asked": today.isoformat(), "files": files}).encode("utf-8"), content_type="application/json")
    return files


def run(sink, companies: list[tuple[str, str]], client, time_budget: float = 17400.0, today: date | None = None,
        clock=time.monotonic) -> dict:
    """For each (scrip, symbol), largest first: its BSE list, then each file of a year we hold no annual document for. Stops on
    the file cap (``more``) or the time budget; a refusal propagates (what is stored stays)."""
    from .nse import FileCapReached
    from .adapters.bse import Missing

    today = today or date.today()
    totals = {"companies": 0, "not_on_bse": 0, "lists_asked": 0, "lists_reused": 0, "companies_with_files": 0,
              "files_listed": 0, "files_wanted": 0, "files_downloaded": 0, "files_from_store": 0, "files_missing": 0,
              "facts_saved": 0, "facts_kept_nse": 0, "not_annual_xbrl": 0, "bytes": 0, "more": False}
    saved: list[dict] = []
    deadline = clock() + time_budget
    for scrip, symbol in companies:
        if not str(scrip).isdigit():
            totals["not_on_bse"] += 1
            continue
        if clock() >= deadline:
            totals["more"] = True
            break
        totals["companies"] += 1
        stored = set(sink.list_objects(f"{xf.PREFIX}{scrip}/")) | set(sink.list_objects(f"{PREFIX}{scrip}/"))
        files = _listing(client, sink, scrip, stored, today, totals)
        totals["files_listed"] += len(files)
        totals["companies_with_files"] += bool(files)
        try:
            for f in wanted(files, stored, scrip):
                totals["files_wanted"] += 1
                key = file_key(scrip, f["name"])
                if key in stored and (blob := sink.get_object(key)):
                    body = gzip.decompress(blob)
                    totals["files_from_store"] += 1
                else:
                    url = FILE_URL.format(name=f["name"])
                    try:
                        body = client.fetch_url(url, {}, "bse-annual-xbrl", file=True)
                    except Missing:
                        totals["files_missing"] += 1
                        continue
                    sink.put_object(key, gzip.compress(body, 9, mtime=0), content_type="application/gzip")
                    stored.add(key)
                    totals["files_downloaded"] += 1
                    totals["bytes"] += len(body)
                doc = xf.parse_annual_facts(body, scrip=scrip, url=FILE_URL.format(name=f["name"]))
                if doc is None:
                    totals["not_annual_xbrl"] += 1
                    continue
                target = xf.annual_key(scrip, doc["fy"], doc["basis"])
                if target in stored:
                    totals["facts_kept_nse"] += 1
                    continue
                xf.save_annual(sink, scrip, doc["fy"], doc["basis"], dict(doc, source="bse"))
                stored.add(target)
                totals["facts_saved"] += 1
                saved.append({"scrip": scrip, "symbol": symbol, "fy": doc["fy"], "basis": doc["basis"], "file": f["name"]})
        except FileCapReached:
            totals["more"] = True
            break
    return {**totals, "saved": saved}


def render(out: dict) -> str:
    keys = ("companies", "not_on_bse", "lists_asked", "lists_reused", "companies_with_files", "files_listed", "files_wanted",
            "files_downloaded", "files_from_store", "files_missing", "facts_saved", "facts_kept_nse", "not_annual_xbrl", "bytes",
            "more")
    return "BSE annual-report XBRL (the years NSE does not list):\n" + "\n".join(f"{k:22s} {out[k]}" for k in keys)
