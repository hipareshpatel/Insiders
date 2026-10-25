"""Module 42: promoter pledges, event by event, from NSE's SAST Regulation 31 encumbrance disclosures (no AI).

NSE lists every company's encumbrance disclosures in one feed (`/api/corporate-pledgedata-sast3132`, measured
2026-10-18 and 2026-10-19, docs/SOURCES.md): one row per promoter event with the shares encumbered before it, the
event (creation, release, invocation) and its shares, the shares encumbered after it, the promoter's holding, the
lender and the filing. Each % is of the company's total share capital.

At the end of a live run this step reads the last few days of the feed, and for the companies in the universe files
each event not yet in memory under `dossier["pledges"]["events"]`, dated by its broadcast time so a card sees only the
events known when its filing came out (`dossier_as_of`). No card is made; `signals.py` turns the events into a
"pledge" line on the company's next card: a pledge invoked, encumbrance rising, or released in full.
`pledge-sync --days N` reads further back.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from . import nse as nse_api
from . import universe
from .dossier import new_dossier, section_label
from .timeutil import IST, iso_ist, now_iso, today_ist

log = logging.getLogger(__name__)

MAX_EVENTS = 60        # events kept per company, newest last
LIVE_DAYS = 3          # days of the feed read each live run (the feed is one request for the whole market)
_EVENT = {"CREATION": "CREATED", "CREATE": "CREATED", "RELEASE": "RELEASED", "INVOCATION": "INVOKED", "INVOKE": "INVOKED"}


def _num(value) -> float | None:
    text = str(value if value is not None else "").replace(",", "").strip()
    try:
        return float(text) if text and text not in ("-", "NA", "N.A.") else None
    except ValueError:
        return None


def _day(value) -> str | None:
    text = str(value or "").strip()
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.title() if "%b" in fmt else text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _when(value) -> str | None:
    text = str(value or "").strip()
    try:
        return iso_ist(datetime.strptime(text.title(), "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST))
    except ValueError:
        day = _day(text)
        return f"{day}T00:00:00+05:30" if day else None


def parse_row(row: dict) -> dict | None:
    """One feed row as a memory event, or None when it lacks what an event needs (a symbol, a time, an event)."""
    symbol = str(row.get("symbol") or "").strip().upper()
    when = _when(row.get("broadcastdate")) or _when(row.get("sysTime"))
    kind = re.sub(r"[^A-Z]", "", str(row.get("eventDetailsType") or "").upper())
    if not symbol or not when or not kind:
        return None
    return {
        "seq_id": str(row.get("seqId") or "").strip() or None,
        "symbol": symbol,
        "promoter": " ".join(str(row.get("promoterName") or "").split())[:120] or None,
        "event": _EVENT.get(kind, kind),
        "type": " ".join(str(row.get("eventDetailsTypeEncumb") or "").split())[:40] or None,   # Pledge, NDU, lien...
        "event_on": _day(row.get("eventDetailsFromDate")) or _day(str(row.get("eventDate") or "").split(" - ")[0]),
        "shares": _num(row.get("eventDetailsHolding")),
        "pct": _num(row.get("eventDetailsPerc")),
        "before_pct": _num(row.get("encumbPerc")),
        "after_shares": _num(row.get("postEventHolding")),
        "after_pct": _num(row.get("postEventHoldingPerc")),
        "promoter_pct": _num(row.get("preeventHoldingPerc")),
        "lender": " ".join(str(row.get("eventDetailsEntity") or "").split())[:160] or None,
        "reported_on": _day(row.get("reportingDate")),
        "as_of": when,
        "attachment": str(row.get("attachment") or "").strip() or None,
    }


def _key(e: dict) -> tuple:
    """One event once: by NSE's sequence id, else by what it says (a refiled disclosure keeps its facts)."""
    return ("seq", e["seq_id"]) if e.get("seq_id") else ("facts", e.get("promoter"), e.get("event"), e.get("event_on"), e.get("shares"))


def merge(dossier: dict, events: list[dict]) -> int:
    """Events into memory, each once, oldest first. Returns how many were new."""
    box = dossier.setdefault("pledges", {"events": []})
    known = {_key(e) for e in box.get("events", [])}
    new = []
    for e in events:   # an event once, also within one batch (the same row in two overlapping windows)
        if _key(e) not in known:
            known.add(_key(e))
            new.append(e)
    if new:
        box["events"] = sorted(box.get("events", []) + new, key=lambda e: (e["as_of"], e.get("seq_id") or ""))[-MAX_EVENTS:]
        now = summary(dossier)
        # the company page shows this as it stands; cards read the events as of their filing instead
        box["summary"] = {"encumbered_pct": now["encumbered_pct"], "promoters": now["promoters"], "as_of": box["events"][-1]["as_of"]}
        section_label(dossier, "pledges", now_iso())   # NSE's SAST Reg 31 feed (memory label: file)
    return len(new)


def promoter_key(name: str | None) -> str:
    """One promoter however the filing spells it: "VEDANTA LIMITED" and "Vedanta Ltd." are one holder (Hindustan Zinc's
    two rows read as 107% of the company, 2026-10-19)."""
    text = re.sub(r"[^A-Z0-9 ]", " ", (name or "").upper())
    text = re.sub(r"\b(?:LTD|LIMITED|PVT|PRIVATE|THE|MR|MRS|MS|DR|SHRI|SMT)\b", " ", text)
    return " ".join(text.split())


def _group_figure(e: dict) -> bool:
    """A row whose encumbered figure is above the promoter's own holding states the whole group's (Advent Hotels: 67.71%
    encumbered on a promoter holding 2.99%), so it cannot be added up promoter by promoter."""
    own = e.get("promoter_pct")
    return own is not None and any(v is not None and v > own + 0.05 for v in (e.get("before_pct"), e.get("after_pct")))


def encumbered(events: list[dict]) -> dict[str, float]:
    """Each promoter's encumbered share of the company after their latest event, % of total share capital. An
    invocation's "after" figure is what the promoter still holds, not what stays encumbered (the SAST Reg 31 form:
    invocation = holding less the shares invoked), so it is left to the encumbered figure before it."""
    out: dict[str, float] = {}
    for e in sorted(events, key=lambda e: (e["as_of"], e.get("seq_id") or "")):
        if not e.get("promoter") or _group_figure(e):
            continue
        key = promoter_key(e["promoter"])
        if e.get("event") == "INVOKED":
            if e.get("before_pct") is not None and e.get("pct") is not None:
                out[key] = max(0.0, e["before_pct"] - e["pct"])
        elif e.get("after_pct") is not None:
            out[key] = e["after_pct"]
    return out


def summary(dossier: dict | None) -> dict | None:
    """What memory knows of promoter encumbrance: the total disclosed (None when a filer gave group figures that
    cannot be added up), the promoters and the latest event."""
    events = ((dossier or {}).get("pledges") or {}).get("events") or []
    if not events:
        return None
    per = encumbered(events)
    grouped = any(_group_figure(e) for e in events)
    return {"encumbered_pct": None if grouped else round(sum(per.values()), 2), "promoters": len(per), "last": events[-1],
            "invoked": [e for e in events if e.get("event") == "INVOKED"]}


def signals(dossier: dict | None, filed_at: str, days: int = 90) -> list[tuple[str, str]]:
    """(severity, text) lines for a card filed at `filed_at`, from the events memory held then (`dossier` is already
    `dossier_as_of` the filing): an invocation in the last `days`, encumbrance up by a point or more over them, or
    released in full. Each % is of the company's total share capital."""
    events = ((dossier or {}).get("pledges") or {}).get("events") or []
    if not events:
        return []
    try:
        since = (date.fromisoformat(filed_at[:10]) - timedelta(days=days)).isoformat()
    except ValueError:
        return []
    recent = [e for e in events if (e.get("event_on") or e["as_of"][:10]) >= since]
    if not recent:
        return []
    out: list[tuple[str, str]] = []
    invoked = [e for e in recent if e.get("event") == "INVOKED"]
    if invoked:
        e = invoked[-1]
        size = f"{e['pct']:.2f}% of the company" if e.get("pct") is not None else "shares"
        out.append(("WARNING", f"Pledge invoked: {e.get('lender') or 'a lender'} took {size} pledged by "
                               f"{e.get('promoter') or 'a promoter'} ({e.get('event_on') or e['as_of'][:10]})."))
    if any(_group_figure(e) for e in recent):
        return out   # group figures on a promoter's row: the totals cannot be compared (the invocation still stands)
    before = encumbered([e for e in events if (e.get("event_on") or e["as_of"][:10]) < since])
    now = encumbered(events)
    # a promoter with no event before the window starts at what its first event says was encumbered before it
    first: dict[str, float] = {}
    for e in sorted(recent, key=lambda e: (e["as_of"], e.get("seq_id") or "")):
        key = promoter_key(e.get("promoter"))
        if key and key not in first and e.get("before_pct") is not None:
            first[key] = e["before_pct"]
    start = sum(before.get(p, first.get(p, 0.0)) for p in now)
    end = sum(now.values())
    word = "encumbered (pledges and other encumbrances)" if any(not str(e.get("type") or "").lower().startswith("pledge")
                                                                 for e in recent) else "pledged"
    if end - start >= 1.0:
        out.append(("WARNING", f"Promoter shares {word} up from {start:.2f}% to {end:.2f}% of the company in {days} days "
                               f"({len(recent)} disclosure{'s' if len(recent) > 1 else ''})."))
    elif start >= 0.5 and end < 0.05 and not invoked:
        noun = "pledges" if word == "pledged" else "encumbrances"
        out.append(("POSITIVE", f"Promoter {noun} released in full: {start:.2f}% of the company {days} days ago, none now."))
    return out


def sync(pipeline, deadline: float, days: int = LIVE_DAYS, scrips: set[str] | None = None, end: date | None = None) -> dict:
    """File the encumbrance events NSE listed over the last `days` (only `scrips`' when given). Returns what it did."""
    report = {"listed": 0, "in_universe": 0, "filed": 0, "companies": 0, "errors": [], "stopped": None}
    nse, sink = pipeline.nse, pipeline.sink
    if nse is None or getattr(pipeline, "_nse_refused", False):
        report["stopped"] = "NSE not asked (off or refused this run)"
        return report
    nse_map = universe.load_nse(sink)
    if not nse_map.built:
        report["stopped"] = "no NSE universe file yet"
        return report
    end = end or today_ist()
    rows: list[dict] = []
    # the feed is asked a month at a time, so a long backfill is not one huge answer
    start = end - timedelta(days=days)
    while start <= end and time.monotonic() < deadline:
        stop = min(end, start + timedelta(days=30))
        try:
            rows += nse.encumbrances(start, stop)
        except nse_api.SourceBlockedError as exc:
            report["stopped"] = f"NSE refused the session: {exc}"
            return report
        except Exception as exc:  # the next run reads the same days again
            report["errors"].append(f"{start}..{stop}: {type(exc).__name__}: {exc}"[:200])
        start = stop + timedelta(days=1)
    by_scrip: dict[str, list[dict]] = {}
    for row in rows:
        report["listed"] += 1
        event = parse_row(row)
        if event is None:
            report["errors"].append(f"unreadable row: {str(row)[:120]}")
            continue
        scrip = nse_map.symbols.get(event["symbol"])
        if not scrip or scrip not in nse_map.included or (scrips and scrip not in scrips):
            continue
        report["in_universe"] += 1
        by_scrip.setdefault(scrip, []).append(event)
    for scrip, events in by_scrip.items():
        if time.monotonic() >= deadline:
            report["stopped"] = report["stopped"] or "time budget"
            break
        dossier = sink.get_dossier(scrip)
        if dossier is None:   # memory starts here, as governance_memory.sync does
            company = sink.company(scrip) or {}
            dossier = new_dossier(SimpleNamespace(scrip_code=scrip, company_name=company.get("company_name") or scrip,
                                                  symbol=events[0]["symbol"]), company)
        added = merge(dossier, events)
        if added:
            sink.put_dossier(scrip, dossier)
            report["filed"] += added
            report["companies"] += 1
    report["errors"] = report["errors"][:20]
    return report
