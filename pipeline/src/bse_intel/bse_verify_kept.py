"""One-time, read-only check of the kept BSE-only companies (owner, 26 Oct 2026, Option A: "let GitHub Actions run one
time to verify if BSE is responding"; TRACKER F160). Nothing is written anywhere.

For each company that ``prune_companies`` keeps as ``bse_kept`` (a BSE-only equity worth 500 Cr or more by our stored
market cap) it asks BSE, through the ported adapter (``adapters/bse.py``: BSE's own page headers, its 4-6 s pace between
calls, 3 retries on network errors and 5xx, a stop on 401/403/429), two things:

* ``getScripHeaderData/w?Debtflag=&scripcode=<scrip>&seriesid=`` (the stock page's price header): ``Header.Category``
  ("Listed" for TCS, measured 26 Oct 2026) and ``Header.DisplayText`` give the status, ``CurrRate.LTP`` the last price.
* ``StockTrading/w?flag=&quotetype=EQ&scripcode=<scrip>`` (the stock page's trading panel): ``MktCapFull`` in Cr
  ("9,14,652.52" for TCS, measured 26 Oct 2026). ``ComHeader/w`` and ``ComHeadernew/w`` carry neither field.
* ``AnnSubCategoryGetData/w`` with ``strScrip=<scrip>`` over the last 90 days (the endpoint the adapter's ``announcements``
  uses for a day; here filtered by the scrip): rows come newest first, so the newest row's date is the latest announcement.

Each call's status is recorded. A refusal (401/403/429) stops the run (a refusal is not worked round, CLAUDE.md): the
remaining companies are listed as not asked. A refusal's first 300 characters of body go into the result, so the owner can
tell a Cloudflare / Akamai JavaScript challenge page (the only case that counts as a JavaScript requirement) from a plain
403. What BSE writes for a suspended or delisted scrip is not measured (assumption): any status text containing "suspend" or
"delist" is read so; ``Category`` "Listed" with none of those words is "active"; anything else is "unknown" and its raw
text is kept (``status_text``) for the owner to read."""
from __future__ import annotations

import json
import logging
import time
from collections import Counter
from datetime import date, timedelta

from .adapters import bse as adapter
from .timeutil import parse_bse_datetime

log = logging.getLogger(__name__)

WINDOW_DAYS = 90
HEADER_PATH = "getScripHeaderData/w"
TRADING_PATH = "StockTrading/w"
ANN_PATH = "AnnSubCategoryGetData/w"
BODY_CHARS = 300


class RecordingSession:
    """Wraps the adapter's requests session: every call's URL, status, size and time are kept, and the first 300
    characters of a body that is not 200. The wrapped session sends the adapter's headers unchanged."""

    def __init__(self, session):
        self.session, self.log = session, []

    @property
    def headers(self):
        return self.session.headers

    def get(self, url, params=None, timeout=None):
        t = time.time()
        r = self.session.get(url, params=params, timeout=timeout)
        entry = {"path": url.split("/api/")[-1], "scrip": (params or {}).get("scripcode") or (params or {}).get("strScrip"),
                 "status": r.status_code, "bytes": len(r.content), "secs": round(time.time() - t, 2)}
        if r.status_code != 200:
            entry["body_head"] = r.content[:BODY_CHARS].decode("utf-8", errors="replace")
        self.log.append(entry)
        return r

    def close(self):
        self.session.close()


def make_client(sleep=time.sleep):
    """The adapter's client over a recording session; returns (client, session)."""
    import requests
    rec = RecordingSession(requests.Session())
    return adapter.BSEClient(session=rec, sleep=sleep), rec


def status_text(data: dict) -> str:
    """The words BSE shows for the scrip: Header.DisplayText and Header.Category (and Cmpname.Category)."""
    head = data.get("Header") if isinstance(data.get("Header"), dict) else {}
    name = data.get("Cmpname") if isinstance(data.get("Cmpname"), dict) else {}
    parts = [str(x).strip() for x in (head.get("DisplayText"), head.get("Category"), name.get("Category")) if x not in (None, "")]
    return " | ".join(dict.fromkeys(parts))


def parse_status(data: dict) -> str:
    """'suspended' / 'delisted' (those words anywhere in the status text), 'active' (Listed), else 'unknown'."""
    text = status_text(data).lower()
    if "suspend" in text:
        return "suspended"
    if "delist" in text:
        return "delisted"
    if "listed" in text:
        return "active"
    return "unknown"


def parse_mcap_cr(trading: dict) -> float | None:
    """MktCapFull of the trading panel, in Cr, commas dropped ("9,14,652.52" -> 914652.52)."""
    value = trading.get("MktCapFull") if isinstance(trading, dict) else None
    try:
        return float(str(value).replace(",", "")) if value not in (None, "", "-") else None
    except ValueError:
        return None


def latest_announcement(rows: list[dict]) -> date | None:
    best = None
    for row in rows:
        stamp = (parse_bse_datetime(row.get("DissemDT")) or parse_bse_datetime(row.get("NEWS_DT"))
                 or parse_bse_datetime(row.get("DT_TM")))
        if stamp and (best is None or stamp > best):
            best = stamp
    return best.date() if best else None


def verify_one(client, row: dict, today: date, min_mcap: float) -> dict:
    """Three paced calls for one scrip. Raises adapter.Blocked on a refusal (the caller stops)."""
    scrip = row["scrip_code"]
    out = {"scrip_code": scrip, "company_name": row.get("company_name"), "isin": row.get("isin"),
           "stored_market_cap_cr": row.get("market_cap_cr"), "header_status": None, "announcements_status": None,
           "trading_status": None, "scrip_status": "unknown", "status_text": None, "last_price": None,
           "market_cap_cr": None, "latest_announcement": None,
           "announcement_in_90d": False, "error": None}
    try:
        payload = client._payload(HEADER_PATH, {"Debtflag": "", "scripcode": scrip, "seriesid": ""}, "bse_verify_header",
                                  {"scrip": scrip})
        header = payload if isinstance(payload, dict) else {}
        out["header_status"] = 200
        out["scrip_status"] = parse_status(header)
        out["status_text"] = status_text(header) or None
        out["last_price"] = (header.get("CurrRate") or {}).get("LTP") if isinstance(header.get("CurrRate"), dict) else None
    except adapter.Blocked:
        raise
    except (adapter.Failed, AttributeError) as exc:
        out["error"] = f"header: {exc}"[:200]
    try:
        payload = client._payload(TRADING_PATH, {"flag": "", "quotetype": "EQ", "scripcode": scrip}, "bse_verify_trading",
                                  {"scrip": scrip})
        out["trading_status"] = 200
        out["market_cap_cr"] = parse_mcap_cr(payload)
    except adapter.Blocked:
        raise
    except (adapter.Failed, AttributeError) as exc:
        out["error"] = ((out["error"] + "; ") if out["error"] else "") + f"trading: {exc}"[:200]
    try:
        since = today - timedelta(days=WINDOW_DAYS)
        body = client.get(ANN_PATH, {"pageno": 1, "strCat": "-1", "strPrevDate": adapter.ymd(since), "strScrip": scrip,
                                     "strSearch": "P", "strToDate": adapter.ymd(today), "strType": "C", "subcategory": "-1"},
                          "bse_verify_announcements", {"scrip": scrip})
        out["announcements_status"] = 200
        table = json.loads(body.decode("utf-8", errors="replace")).get("Table")
        latest = latest_announcement(table if isinstance(table, list) else [])
        out["latest_announcement"] = latest.isoformat() if latest else None
        out["announcement_in_90d"] = latest is not None and (today - latest).days <= WINDOW_DAYS
    except adapter.Blocked:
        raise
    except (adapter.Failed, ValueError, AttributeError) as exc:
        out["error"] = ((out["error"] + "; ") if out["error"] else "") + f"announcements: {exc}"[:200]
    return out


def verify(client, kept: list[dict], today: date, min_mcap: float) -> dict:
    """Ask BSE about each kept row; stop at the first refusal. ``client`` is the adapter's (its pace applies); the calls
    it made are read from ``client.session.log`` when that is a RecordingSession."""
    results, blocked, not_asked = [], None, []
    for i, row in enumerate(kept):
        try:
            results.append(verify_one(client, row, today, min_mcap))
        except adapter.Blocked as exc:
            blocked = {"scrip_code": row["scrip_code"], "message": str(exc)}
            not_asked = [r["scrip_code"] for r in kept[i:]]
            log.error("bse-verify-kept: refused at %s: %s; stopping", row["scrip_code"], exc)
            break
    calls = list(getattr(client.session, "log", []))
    if blocked:
        refusal = next((c for c in reversed(calls) if c["status"] != 200 and c.get("body_head") is not None), None)
        blocked["status"] = refusal["status"] if refusal else None
        blocked["body_head"] = refusal["body_head"] if refusal else None
    return {"day": today.isoformat(), "min_mcap_cr": min_mcap, "kept": len(kept), "companies": results,
            "blocked": blocked, "not_asked": not_asked, "calls": calls,
            "summary": summarise(results, calls, len(kept), min_mcap)}


def summarise(results: list[dict], calls: list[dict], kept: int, min_mcap: float) -> dict:
    statuses = Counter(str(c["status"]) for c in calls)
    return {"kept": kept, "asked": len(results), "calls_made": len(calls),
            "status_200": statuses.get("200", 0), "status_403": statuses.get("403", 0),
            "status_other": sum(n for k, n in statuses.items() if k not in ("200", "403")),
            "status_codes": dict(statuses),
            "active": sum(r["scrip_status"] == "active" for r in results),
            "suspended": sum(r["scrip_status"] == "suspended" for r in results),
            "delisted": sum(r["scrip_status"] == "delisted" for r in results),
            "unknown_status": sum(r["scrip_status"] == "unknown" for r in results),
            "still_at_or_over_min_mcap": sum((r["market_cap_cr"] or 0) >= min_mcap for r in results),
            "announcement_in_90d": sum(bool(r["announcement_in_90d"]) for r in results),
            "active_and_over_min_and_announced": sum(r["scrip_status"] == "active" and (r["market_cap_cr"] or 0) >= min_mcap
                                                     and bool(r["announcement_in_90d"]) for r in results)}


def render(result: dict) -> str:
    s = result["summary"]
    lines = [f"BSE check of the kept BSE-only companies ({result['day']}): {s['asked']} of {s['kept']} asked, "
             f"{s['calls_made']} calls; status 200 x{s['status_200']}, 403 x{s['status_403']}, other x{s['status_other']} {s['status_codes']}",
             f"active {s['active']}, suspended {s['suspended']}, delisted {s['delisted']}, status not read {s['unknown_status']}; "
             f"still {result['min_mcap_cr']:g} Cr or more by BSE's market cap {s['still_at_or_over_min_mcap']}; "
             f"an announcement in the last {WINDOW_DAYS} days {s['announcement_in_90d']}; all three {s['active_and_over_min_and_announced']}"]
    if result["blocked"]:
        b = result["blocked"]
        lines.append(f"REFUSED at {b['scrip_code']}: {b['message']}; status {b.get('status')}; "
                     f"body starts: {(b.get('body_head') or '')!r}; not asked: {len(result['not_asked'])}")
    return "\n".join(lines)


def to_csv(result: dict) -> str:
    out = ["scrip_code,company_name,isin,stored_market_cap_cr,scrip_status,market_cap_cr,latest_announcement,"
           "announcement_in_90d,status_text,header_http,trading_http,announcements_http,error"]
    for r in result["companies"]:
        name = (r.get("company_name") or "").replace('"', "'")
        out.append(f'{r["scrip_code"]},"{name}",{r.get("isin") or ""},{_v(r["stored_market_cap_cr"])},{r["scrip_status"]},'
                   f'{_v(r["market_cap_cr"])},{r["latest_announcement"] or ""},{int(bool(r["announcement_in_90d"]))},'
                   f'"{(r.get("status_text") or "").replace(chr(34), chr(39))}",{_v(r["header_status"])},{_v(r["trading_status"])},{_v(r["announcements_status"])},"{(r.get("error") or "").replace(chr(34), chr(39))}"')
    return "\n".join(out) + "\n"


def _v(value) -> str:
    return "" if value is None else str(value)
