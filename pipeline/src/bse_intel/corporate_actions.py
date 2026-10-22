"""Corporate actions from NSE's feed (no AI): splits, bonuses, dividends, rights, buybacks, demergers.

The data chain audit (22 Oct 2026) found no source giving them as data, so EPS history and per-share figures were
compared across a split or bonus as if nothing had changed (TTM EPS summed pre- and post-bonus quarters; Kapston's
year-ago EPS ₹3.48 against ₹2.32 after its 1:2 bonus). NSE lists every company's actions in one feed
(`/api/corporates-corporateActions`, measured 2026-10-22: 1,852 rows for 1 Jan - 21 Oct 2026, 33 face-value splits and
31 bonuses among them; subjects such as "Bonus 1:2", "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/-
Per Share", "Dividend - Rs 2 Per Share").

Each action of a universe company goes into `dossier["corporate_actions"]`: its ex-date, kind and, for a split or a
bonus, `factor`, the number of shares one share became (a 1:2 bonus, one new share for every two held, is 1.5; a split
from ₹10 to ₹2 is 5). The company page divides a per-share figure of a period ending before the ex-date by the factor,
so EPS reads on today's share count. `corporate-actions-sync --days N` reads further back.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from . import nse as nse_api
from . import universe
from .dossier import new_dossier
from .timeutil import today_ist

log = logging.getLogger(__name__)

KEY = "corporate_actions"
MAX_ACTIONS = 80     # kept per company, newest last
LIVE_DAYS = 30       # days read each night (ex-dates are announced weeks ahead; the feed is one request a month)
ENDPOINT = f"{nse_api.SITE}/api/corporates-corporateActions"

_BONUS = re.compile(r"^\s*BONUS\s+(\d+)\s*:\s*(\d+)\s*$", re.I)
_SPLIT = re.compile(r"(?:SPLIT|SUB-?\s*DIVISION).*?FROM\s+R[SE]\.?\s*(\d+(?:\.\d+)?)\s*/?-?.*?TO\s+R[SE]\.?\s*(\d+(?:\.\d+)?)", re.I)
_CONSOLIDATION = re.compile(r"CONSOLIDATION.*?FROM\s+R[SE]\.?\s*(\d+(?:\.\d+)?)\s*/?-?.*?TO\s+R[SE]\.?\s*(\d+(?:\.\d+)?)", re.I)
_DIVIDEND = re.compile(r"\bDIVIDEND\b.*?R[SE]\.?\s*(\d+(?:\.\d+)?)", re.I)


def _day(value) -> str | None:
    text = str(value or "").strip()
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.title() if "%b" in fmt else text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_row(row: dict) -> dict | None:
    """One feed row as an action, or None when it has no symbol or ex-date. `factor` only for an equity split, bonus or
    consolidation (a "Scheme Of Arrangement - Bonus Ncrps" issues preference shares: no equity factor)."""
    symbol, ex = str(row.get("symbol") or "").strip().upper(), _day(row.get("exDate"))
    subject = " ".join(str(row.get("subject") or "").split())
    if not symbol or not ex or not subject:
        return None
    action: dict = {"symbol": symbol, "ex_date": ex, "subject": subject[:160], "kind": "OTHER"}
    if rec := _day(row.get("recDate")):
        action["record_date"] = rec
    upper = subject.upper()
    if m := _BONUS.match(subject):
        new, held = int(m[1]), int(m[2])
        if held:
            action.update(kind="BONUS", factor=round((new + held) / held, 6))
    elif m := _SPLIT.search(subject):
        old, now = float(m[1]), float(m[2])
        if now and old > now:
            action.update(kind="SPLIT", factor=round(old / now, 6))
    elif m := _CONSOLIDATION.search(subject):
        old, now = float(m[1]), float(m[2])
        if old and now > old:
            action.update(kind="CONSOLIDATION", factor=round(old / now, 6))
    elif "BUY BACK" in upper or "BUYBACK" in upper:
        action["kind"] = "BUYBACK"
    elif upper.startswith("RIGHTS"):
        action["kind"] = "RIGHTS"
    elif "DEMERGER" in upper:
        action["kind"] = "DEMERGER"
    elif m := _DIVIDEND.search(subject):
        action.update(kind="DIVIDEND", per_share=float(m[1]))
    return action


def merge(dossier: dict, actions: list[dict]) -> int:
    """Add the actions memory does not hold (by ex-date and subject). Mutates the dossier; returns how many were added."""
    have = dossier.setdefault(KEY, [])
    seen = {(a.get("ex_date"), a.get("subject")) for a in have}
    added = [a for a in actions if (a["ex_date"], a["subject"]) not in seen]
    if added:
        dossier[KEY] = sorted(have + [{k: v for k, v in a.items() if k != "symbol"} for a in added],
                              key=lambda a: a["ex_date"])[-MAX_ACTIONS:]
    return len(added)


def share_factor_after(dossier: dict, period_end: str) -> float:
    """How many of today's shares one share at `period_end` (ISO date) became: the product of the factors of every split,
    bonus or consolidation with an ex-date after it. 1.0 when there was none."""
    factor = 1.0
    for a in dossier.get(KEY) or []:
        if a.get("factor") and a.get("ex_date", "") > period_end:
            factor *= float(a["factor"])
    return factor


def sync(pipeline, deadline: float, days: int = LIVE_DAYS, scrips: set[str] | None = None, end: date | None = None) -> dict:
    """File the actions NSE lists with ex-dates over the last `days` and the next 60 (announced ahead), only `scrips'`
    when given. Returns what it did."""
    report = {"listed": 0, "in_universe": 0, "filed": 0, "companies": 0, "splits_bonuses": 0, "errors": [], "stopped": None}
    nse, sink = pipeline.nse, pipeline.sink
    if nse is None or getattr(pipeline, "_nse_refused", False):
        report["stopped"] = "NSE not asked (off or refused this run)"
        return report
    nse_map = universe.load_nse(sink)
    if not nse_map.built:
        report["stopped"] = "no NSE universe file yet"
        return report
    end = (end or today_ist()) + timedelta(days=60)
    rows: list[dict] = []
    start = end - timedelta(days=days + 60)
    while start <= end and time.monotonic() < deadline:
        stop = min(end, start + timedelta(days=30))
        try:
            data = nse._get(ENDPOINT, {"index": "equities", "from_date": start.strftime("%d-%m-%Y"),
                                       "to_date": stop.strftime("%d-%m-%Y")}).json()
            rows += data if isinstance(data, list) else (data.get("data") or [])
        except nse_api.SourceBlockedError as exc:
            report["stopped"] = f"NSE refused the session: {exc}"
            return report
        except Exception as exc:  # the next run reads the same days again
            report["errors"].append(f"{start}..{stop}: {type(exc).__name__}: {exc}"[:200])
        start = stop + timedelta(days=1)
    by_scrip: dict[str, list[dict]] = {}
    for row in rows:
        report["listed"] += 1
        action = parse_row(row)
        if action is None:
            continue
        scrip = nse_map.symbols.get(action["symbol"])
        if not scrip or scrip not in nse_map.included or (scrips and scrip not in scrips):
            continue
        report["in_universe"] += 1
        by_scrip.setdefault(scrip, []).append(action)
    for scrip, actions in by_scrip.items():
        if time.monotonic() >= deadline:
            report["stopped"] = report["stopped"] or "time budget"
            break
        dossier = sink.get_dossier(scrip)
        if dossier is None:
            company = sink.company(scrip) or {}
            dossier = new_dossier(SimpleNamespace(scrip_code=scrip, company_name=company.get("company_name") or scrip,
                                                  symbol=actions[0]["symbol"]), company)
        added = merge(dossier, actions)
        if added:
            sink.put_dossier(scrip, dossier)
            report["filed"] += added
            report["companies"] += 1
            report["splits_bonuses"] += sum(1 for a in actions if a.get("factor"))
    report["errors"] = report["errors"][:20]
    return report


_KIND_WORDS = {"BONUS": r"\bbonus\b", "SPLIT": r"\bsplit\b|sub-?\s*division", "CONSOLIDATION": r"\bconsolidation\b",
               "BUYBACK": r"buy-?\s*back", "RIGHTS": r"\brights?\s+(?:issue|entitlement)", "DEMERGER": r"\bdemerger\b",
               "DIVIDEND": r"\bdividend\b"}


def card_block(dossier: dict | None, filed_at: str, text: str, price: float | None = None) -> dict | None:
    """A corporate-action card's own block from memory's actions (owner, 22 Oct 2026: ratio, record date, yield): the
    action the card is about, the first one of its kind with an ex-date from the filing day to 120 days after it. A
    dividend's yield is on the price when the filing came out."""
    from datetime import date as _date

    actions = (dossier or {}).get(KEY) or []
    day = filed_at[:10]
    try:
        last = (_date.fromisoformat(day) + timedelta(days=120)).isoformat()
    except ValueError:
        return None
    kinds = [k for k, words in _KIND_WORDS.items() if re.search(words, text or "", re.I)]
    for a in sorted(actions, key=lambda a: a.get("ex_date", "")):
        if a.get("kind") in kinds and day <= a.get("ex_date", "") <= last:
            block = {k: a[k] for k in ("kind", "subject", "ex_date", "record_date", "factor", "per_share") if a.get(k) is not None}
            if a.get("per_share") and price:
                block["yield_pct"] = round(a["per_share"] / price * 100, 2)
            return block
    return None
