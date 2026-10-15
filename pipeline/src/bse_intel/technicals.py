"""Optional techno-funda tags (blueprint §11.3), computed by the market-data job from daily prices.

* Stage 2 (Minervini trend template): close > 50-DMA > 150-DMA > 200-DMA, the 200-DMA rising over
  20 sessions, and the close within 25% of the 52-week high.
* VCP (tight base): 10-day ATR below 0.7x the 50-day ATR, and a 20-day high-low range under 12%.
  With a HIGH impact card this is the "coiled spring" badge.
* RS: an O'Neil-style weighted 3/6/9/12-month return, turned into a 0-99 percentile across the
  companies priced in the same run; plus Clenow's volatility-adjusted slope (annualised exponential
  regression slope over 90 sessions x R²).
* RVOL: the latest session's volume against the 50-session median.

Tags describe price structure only. They are shown beside the card, never added to the score.
"""

from __future__ import annotations

import math
import statistics


def _sma(values: list[float], n: int, end: int | None = None) -> float | None:
    end = len(values) if end is None else end
    if end < n:
        return None
    return sum(values[end - n:end]) / n


def stage2(closes: list[float]) -> bool | None:
    if len(closes) < 220:
        return None
    c = closes[-1]
    s50, s150, s200 = _sma(closes, 50), _sma(closes, 150), _sma(closes, 200)
    s200_then = _sma(closes, 200, len(closes) - 20)
    high = max(closes[-250:])
    return bool(c > s50 > s150 > s200 and s200 > s200_then and c >= high * 0.75)


def _atr_pct(highs: list[float], lows: list[float], closes: list[float], n: int) -> float | None:
    if len(closes) < n + 1:
        return None
    ranges = []
    for i in range(len(closes) - n, len(closes)):
        prev = closes[i - 1]
        ranges.append(max(highs[i] - lows[i], abs(highs[i] - prev), abs(lows[i] - prev)) / prev * 100 if prev else 0)
    return sum(ranges) / n


def vcp(highs: list[float], lows: list[float], closes: list[float]) -> bool | None:
    a10, a50 = _atr_pct(highs, lows, closes, 10), _atr_pct(highs, lows, closes, 50)
    if a10 is None or a50 is None or not a50 or len(closes) < 20:
        return None
    hi, lo = max(highs[-20:]), min(lows[-20:])
    return bool(a10 < 0.7 * a50 and lo > 0 and (hi - lo) / lo * 100 < 12)


def rs_score(closes: list[float]) -> float | None:
    """O'Neil weighting: 40% the last quarter's return, 20% each of the three before."""
    if len(closes) < 253:
        return None
    def ret(back: int) -> float:
        return closes[-1] / closes[-1 - back] - 1 if closes[-1 - back] else 0.0
    return 0.4 * ret(63) + 0.2 * ret(126) + 0.2 * ret(189) + 0.2 * ret(252)


def clenow(closes: list[float], n: int = 90) -> float | None:
    if len(closes) < n or min(closes[-n:]) <= 0:
        return None
    ys = [math.log(c) for c in closes[-n:]]
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return round(((math.exp(slope) ** 250) - 1) * 100 * r2, 1)


def rvol(volumes: list[float]) -> float | None:
    base = [v for v in volumes[-51:-1] if v]
    if len(base) < 20 or not volumes[-1]:
        return None
    return round(volumes[-1] / statistics.median(base), 2)


def tags(highs: list[float], lows: list[float], closes: list[float], volumes: list[float]) -> dict:
    out = {"stage2": stage2(closes), "vcp": vcp(highs, lows, closes), "clenow": clenow(closes), "rvol": rvol(volumes)}
    score = rs_score(closes)
    if score is not None:
        out["rs_raw"] = round(score, 4)
    return {k: v for k, v in out.items() if v is not None}


def rank_rs(rows: list[dict]) -> None:
    """Turn each row's ``rs_raw`` into a 0-99 percentile among the rows (in place)."""
    scored = sorted((r for r in rows if "rs_raw" in r), key=lambda r: r["rs_raw"])
    n = len(scored)
    for i, r in enumerate(scored):
        r["rs_pct"] = int(i / (n - 1) * 99) if n > 1 else 50
        r.pop("rs_raw")
