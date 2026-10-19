"""Client-side pacing and quota ceilings, so free-tier limits are respected
instead of discovered via 429s.

Every configured limit is scaled by a safety ceiling (default 95%): a model
leaves the active pool once it reaches 95% of its daily or monthly quota,
and per-minute pacing keeps it under 95% of its rpm/tpm.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, replace

DEFAULT_CEILING = 0.95


@dataclass(frozen=True)
class Limits:
    rpm: int | None = None    # requests per minute
    tpm: int | None = None    # tokens per minute
    rpd: int | None = None    # requests per day
    tpd: int | None = None    # tokens per day
    rpmo: int | None = None   # requests per month
    tpmo: int | None = None   # tokens per month

    @classmethod
    def from_config(cls, data: dict | None) -> "Limits":
        data = data or {}
        return cls(**{k: int(v) for k, v in data.items() if k in cls.__dataclass_fields__})

    def scaled(self, ceiling: float) -> "Limits":
        """Apply the safety ceiling (floor, but never below 1)."""
        values = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            values[name] = None if value is None else max(1, math.floor(value * ceiling))
        return replace(self, **values)


class QuotaCounter:
    """Day and month totals against (already scaled) limits. Thread-safe."""

    def __init__(self, limits: Limits, day_requests=0, day_tokens=0, month_requests=0, month_tokens=0, day_of=None):
        self.limits = limits
        self.day_requests = day_requests
        self.day_tokens = day_tokens
        self.month_requests = month_requests
        self.month_tokens = month_tokens
        self.forced_exhausted: str | None = None
        self._lock = threading.Lock()
        # The provider's own quota day (Gemini's ends at midnight Pacific, 12:30 IST): when it changes during a run, the
        # day's counters and a per-day 429 are cleared. Round 6 (2026-10-19) ran past the reset with Gemini still
        # retired, and every pack fell to the spare writers.
        self._day_of = day_of
        self._day = day_of() if day_of else None

    def _roll(self) -> None:
        if self._day_of is None:
            return
        day = self._day_of()
        if day != self._day:
            with self._lock:
                self._day, self.day_requests, self.day_tokens, self.forced_exhausted = day, 0, 0, None

    def exhausted(self, est_tokens: int = 0) -> str | None:
        self._roll()
        lim = self.limits
        if self.forced_exhausted:
            return self.forced_exhausted
        if lim.rpd and self.day_requests >= lim.rpd:
            return "daily request ceiling"
        if lim.tpd and self.day_tokens + est_tokens > lim.tpd:
            return "daily token ceiling"
        if lim.rpmo and self.month_requests >= lim.rpmo:
            return "monthly request ceiling"
        if lim.tpmo and self.month_tokens + est_tokens > lim.tpmo:
            return "monthly token ceiling"
        return None

    def add(self, requests: int, tokens: int) -> None:
        self._roll()
        with self._lock:
            self.day_requests += requests
            self.month_requests += requests
            self.day_tokens += tokens
            self.month_tokens += tokens

    def utilisation(self) -> float:
        """Highest fraction used across day/month limits (for health meters)."""
        lim, ratios = self.limits, []
        for used, cap in ((self.day_requests, lim.rpd), (self.day_tokens, lim.tpd),
                          (self.month_requests, lim.rpmo), (self.month_tokens, lim.tpmo)):
            if cap:
                ratios.append(used / cap)
        return max(ratios, default=0.0)


class RateLimiter:
    """Sliding one-minute window for one provider/model, plus its day/month quota."""

    def __init__(self, limits: Limits, quota: QuotaCounter | None = None, clock=time.monotonic, sleep=time.sleep):
        self.limits = limits
        self.quota = quota or QuotaCounter(limits)
        self._window: deque[tuple[float, int]] = deque()
        self._blocked_until = 0.0
        self._lock = threading.Lock()
        self._clock = clock
        self._sleep = sleep

    def cooldown(self, seconds: float) -> None:
        with self._lock:
            self._blocked_until = max(self._blocked_until, self._clock() + seconds)

    def cooling_down(self) -> bool:
        return self._blocked_until > self._clock()

    def acquire(self, est_tokens: int, max_wait: float = 30.0, extra_quota: tuple[QuotaCounter, ...] = ()) -> bool:
        """Reserve capacity for one request, sleeping up to ``max_wait`` seconds.

        Returns False when the request cannot be made soon enough; the caller
        should then fail over to another provider rather than block.
        """
        deadline = self._clock() + max_wait
        while True:
            with self._lock:
                if self.quota.exhausted(est_tokens) or any(q.exhausted(est_tokens) for q in extra_quota):
                    return False
                now = self._clock()
                while self._window and now - self._window[0][0] >= 60:
                    self._window.popleft()
                wait = max(0.0, self._blocked_until - now)
                if self.limits.rpm and len(self._window) >= self.limits.rpm:
                    wait = max(wait, 60 - (now - self._window[0][0]))
                if self.limits.tpm:
                    if est_tokens > self.limits.tpm:
                        return False  # can never fit in this model's minute budget
                    used = sum(t for _, t in self._window)
                    if used + est_tokens > self.limits.tpm:
                        freed, i = used, 0
                        while freed + est_tokens > self.limits.tpm and i < len(self._window):
                            freed -= self._window[i][1]
                            i += 1
                        wait = max(wait, 60 - (now - self._window[i - 1][0]))
                if wait <= 0:
                    self._window.append((now, est_tokens))
                    self.quota.add(1, est_tokens)
                    for q in extra_quota:
                        q.add(1, est_tokens)
                    return True
                if now + wait > deadline:
                    return False
            self._sleep(min(wait, max(0.05, deadline - self._clock())))

    def settle(self, est_tokens: int, actual_tokens: int, extra_quota: tuple[QuotaCounter, ...] = ()) -> None:
        """Replace the estimate made in ``acquire`` with the provider-reported usage."""
        delta = actual_tokens - est_tokens
        self.quota.add(0, delta)
        for q in extra_quota:
            q.add(0, delta)
        with self._lock:
            for i in range(len(self._window) - 1, -1, -1):
                ts, tokens = self._window[i]
                if tokens == est_tokens:
                    self._window[i] = (ts, actual_tokens)
                    break
