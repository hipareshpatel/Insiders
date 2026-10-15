"""Loop 1 (blueprint §12.1): how the market actually reacted to each card.

A nightly job, after market data, measures the stock's close-to-close return from the session
before the filing to T+1, T+2, T+3 and T+5, less the benchmark index over the same sessions, and
the volume multiple against the 50-session median before the filing. The result is written to
``cards.post_event_return_json``; a card stays open until T+5 is known.

15:30 IST rule: a filing disseminated before 15:30 on a trading day reacts that day (Day 0 is that
session); one after 15:30, or on a weekend or holiday, reacts on the next session. Holidays need no
calendar here: Day 0 is the first session in the price data that qualifies. T+k is the close of the
k-th session counting Day 0 as the first, measured from the close before Day 0.

From the reactions:
* Missed alpha: a LOW or MODERATE card followed by a T+1 or T+2 excess return of +8% or more on
  3x the usual volume is flagged on the card and listed in kv ``learning:missed_alpha``.
* False-positive dampener: a (sector, event category) whose HIGH cards (10 or more) average a T+3
  excess return within ±1% on under 1.2x volume is listed in kv ``learning:dampen``.
"""

from __future__ import annotations

import json
import logging
import statistics
from datetime import date, datetime, timedelta

from .settings import Settings
from .sinks.base import Sink
from .timeutil import IST, now_iso, now_ist, utc_day

log = logging.getLogger(__name__)

HORIZONS = (1, 2, 3, 5)
VOLUME_BASE_SESSIONS = 50
MISSED_ALPHA_EXCESS, MISSED_ALPHA_RVOL = 8.0, 3.0
DAMPEN_MIN_CARDS, DAMPEN_BAND, DAMPEN_RVOL = 10, 1.0, 1.2
OPEN_DAYS = 14          # the nightly job revisits cards this many days back
PAGE = 500
MISSED_KEEP = 100
MAX_RERUNS = 5            # missed-alpha filings re-analysed with their reaction per night (AI cost)
LESSONS_KEY = "learning/sector_rules.json"   # R2: {"sector|EVENT": [{lesson, news_id, added}]}
LESSONS_KEEP = 5


def day_zero(filed_at: str, sessions: list[date]) -> int | None:
    """Index of the first session that can react to the filing (15:30 IST rule)."""
    dt = datetime.fromisoformat(filed_at).astimezone(IST)
    same_day = dt.hour * 60 + dt.minute <= 15 * 60 + 30
    for i, day in enumerate(sessions):
        if day > dt.date() or (same_day and day == dt.date()):
            return i
    return None


def reaction(filed_at: str, stock: list[tuple[date, float, float]], bench: dict[date, float],
             benchmark: str | None = None) -> dict | None:
    """Price reaction from daily (date, close, volume) rows; ``bench`` maps date to index close."""
    stock = [row for row in stock if row[1]]
    sessions = [row[0] for row in stock]
    i = day_zero(filed_at, sessions)
    if i is None or i == 0:
        return None
    base_day, base = sessions[i - 1], stock[i - 1][1]
    history = [row[2] for row in stock[max(0, i - VOLUME_BASE_SESSIONS):i] if row[2]]
    usual = statistics.median(history) if history else None
    out: dict = {"day0": sessions[i].isoformat(), "base_date": base_day.isoformat(), "benchmark": benchmark}
    for k in HORIZONS:
        j = i + k - 1
        if j >= len(stock):
            continue
        ret = (stock[j][1] / base - 1) * 100
        entry = {"date": sessions[j].isoformat(), "return_pct": round(ret, 2)}
        if bench.get(sessions[j]) and bench.get(base_day):
            bench_ret = (bench[sessions[j]] / bench[base_day] - 1) * 100
            entry["excess_pct"] = round(ret - bench_ret, 2)
        if usual:
            window = [row[2] for row in stock[i:j + 1]]
            entry["rvol"] = round(sum(window) / len(window) / usual, 2)
        out[f"t{k}"] = entry
    out["complete"] = 1 if f"t{HORIZONS[-1]}" in out else 0
    return out


def missed_alpha(impact: str | None, rx: dict) -> bool:
    if impact not in ("LOW", "MODERATE"):
        return False
    for k in ("t1", "t2"):
        entry = rx.get(k) or {}
        if (entry.get("excess_pct") or 0) >= MISSED_ALPHA_EXCESS and (entry.get("rvol") or 0) >= MISSED_ALPHA_RVOL:
            return True
    return False


def _series(frame) -> list[tuple[date, float, float]]:
    try:
        frame = frame.dropna(subset=["Close"])
        return [(idx.date(), float(c), float(v or 0)) for idx, c, v in zip(frame.index, frame["Close"], frame["Volume"])]
    except Exception:
        return []


def _benchmark(yf, tickers: list[str], start: date) -> tuple[str | None, dict[date, float]]:
    for ticker in tickers:
        try:
            frame = yf.download(ticker, start=start.isoformat(), interval="1d", auto_adjust=False, progress=False)
            closes = frame["Close"].dropna()
            if hasattr(closes, "columns"):  # newer yfinance returns one column per ticker
                closes = closes.iloc[:, 0]
            if len(closes):
                return ticker, {idx.date(): float(v) for idx, v in closes.items()}
        except Exception as exc:
            log.debug("benchmark %s unavailable: %s", ticker, exc)
    log.warning("no benchmark index could be fetched; reactions are raw returns only")
    return None, {}


def post_mortem(settings: Settings, sink: Sink, since: str | None = None) -> dict:
    import yfinance as yf  # optional dependency: pip install -e ".[market]"

    conf = settings.load_toml("market.toml").get("learning", {})
    start = since or (now_ist().date() - timedelta(days=OPEN_DAYS)).isoformat()
    until = now_iso()
    cards, after = [], ("", "")
    while True:
        page = sink.query("cards_awaiting_reaction", [start, until, after[0], after[1], PAGE])
        cards += page
        if len(page) < PAGE:
            break
        after = (page[-1]["filed_at"], page[-1]["news_id"])
    stats = {"cards": len(cards), "updated": 0, "complete": 0, "missed_alpha": 0, "requeued": 0, "benchmark": None}
    if not cards:
        sink.kv_set("learning:dampen", json.dumps(dampen(sink)), now_iso())
        return stats
    first = min(datetime.fromisoformat(c["filed_at"]).date() for c in cards)
    history_start = first - timedelta(days=VOLUME_BASE_SESSIONS * 7 // 5 + 14)
    ticker, bench = _benchmark(yf, list(conf.get("benchmarks", ["^NSEI"])), history_start)
    stats["benchmark"] = ticker
    by_scrip: dict[str, list[dict]] = {}
    for card in cards:
        by_scrip.setdefault(str(card["scrip_code"]), []).append(card)
    scrips, batch = sorted(by_scrip), int(conf.get("batch", 100))
    updates, missed = [], []
    for at in range(0, len(scrips), batch):
        chunk = scrips[at:at + batch]
        tickers = [f"{s}.BO" for s in chunk]
        try:
            data = yf.download(tickers, start=history_start.isoformat(), interval="1d", auto_adjust=False,
                               group_by="ticker", progress=False, threads=True)
        except Exception as exc:
            log.warning("price download failed for batch at %d: %s", at, exc)
            continue
        for scrip, t in zip(chunk, tickers):
            try:
                series = _series(data[t] if len(tickers) > 1 else data)
            except Exception:
                series = []
            for card in by_scrip[scrip]:
                rx = reaction(card["filed_at"], series, bench, ticker) if series else None
                if not rx:
                    continue
                if missed_alpha(card.get("impact_level"), rx):
                    rx["missed_alpha"] = 1
                    missed.append({"news_id": card["news_id"], "scrip_code": scrip, "filed_at": card["filed_at"],
                                   "impact": card.get("impact_level"), "t1": rx.get("t1"), "t2": rx.get("t2")})
                updates.append({"news_id": card["news_id"], "reaction": rx})
                stats["complete"] += rx["complete"]
    written = sink.execute("cards_reaction", updates) if updates else 0
    stats.update(updated=written, missed_alpha=len(missed))
    now = now_iso()
    if missed:
        try:
            previous = json.loads(sink.kv_get("learning:missed_alpha") or "[]")
        except ValueError:
            previous = []
        seen = {m["news_id"] for m in missed}
        merged = (missed + [m for m in previous if m.get("news_id") not in seen])[:MISSED_KEEP]
        sink.kv_set("learning:missed_alpha", json.dumps(merged), now)
        stats["requeued"] = queue_reruns(sink, missed, now)
    sink.kv_set("learning:dampen", json.dumps(dampen(sink)), now)
    sink.add_writes(utc_day(), written, now)
    log.info("post-mortem: %s", stats)
    return stats


def dampen(sink: Sink, days: int = 365) -> list[dict]:
    since = (now_ist().date() - timedelta(days=days)).isoformat()
    rows = sink.query("reaction_summary", [since, DAMPEN_MIN_CARDS])
    return [dict(r, flag="TIGHTEN") for r in rows
            if r.get("avg_t3_excess") is not None and abs(r["avg_t3_excess"]) <= DAMPEN_BAND
            and (r.get("avg_t3_rvol") or 0) < DAMPEN_RVOL]


def _reaction_text(m: dict) -> str:
    parts = []
    for k, label in (("t1", "the first session"), ("t2", "two sessions")):
        e = m.get(k) or {}
        if e.get("return_pct") is not None:
            parts.append(f"{label}: {e['return_pct']:+.1f}%"
                         + (f" ({e['excess_pct']:+.1f}% vs the index)" if e.get("excess_pct") is not None else "")
                         + (f" on {e['rvol']:.1f}x usual volume" if e.get("rvol") else ""))
    return "; ".join(parts)


def queue_reruns(sink: Sink, missed: list[dict], now: str) -> int:
    """Missed alpha: put up to MAX_RERUNS new cases back in the queue. The next run re-analyses each
    with its market reaction attached and asks for the lesson (blueprint §12.1)."""
    try:
        done = set(json.loads(sink.kv_get("learning:postmortem_done") or "[]"))
        queue = json.loads(sink.kv_get("learning:postmortem_queue") or "{}")
    except ValueError:
        done, queue = set(), {}
    fresh = [m for m in missed if m["news_id"] not in done and m["news_id"] not in queue][:max(0, MAX_RERUNS - len(queue))]
    if not fresh:
        return 0
    for m in fresh:
        queue[m["news_id"]] = f"Rated {m.get('impact', '').lower()} impact, then the stock moved: {_reaction_text(m)}."
    sink.kv_set("learning:postmortem_queue", json.dumps(queue), now)
    sink.execute("filings_update", [{"news_id": m["news_id"], "status": "PENDING", "attempts": 0, "updated_at": now,
                                     "last_error": "post-mortem: re-analysis with the market reaction"} for m in fresh])
    return len(fresh)
