"""Centralized multi-provider AI gateway.

Routes are fallback pools of (provider, model) targets defined in
config/providers.toml. For each request the gateway orders the pool
(priority order, or smooth weighted round-robin so no single provider is
hammered), keeps "spare" targets for last, and walks it:

* skips targets with no API key, a context window too small for the prompt,
  a tripped circuit breaker, a model the provider reported missing, or a
  quota at the 95% safety ceiling (per model, and per provider for shared
  monthly allowances);
* paces requests under each model's (95%-scaled) rpm/tpm limits; a long
  wait fails over instead of stalling the run;
* fails over on 429 / timeout / connection / 5xx, honouring Retry-After as
  a cooldown (a model that keeps answering 429 pauses 1, 5, then 30 min), and retires a model for the day when the provider says its
  daily quota is spent; an outage counts as transient, so it never uses up
  a filing's attempts;
* stops starting requests past the run's deadline (``gateway.deadline``) and
  caps each request's timeout to the time left, so a run ends on time;
* validates output against a pydantic schema, asks the same model once to
  repair invalid JSON, then fails over;
* records usage so quotas survive across stateless runs.

When nothing can serve a request, ``AllProvidersFailed`` says whether that is
transient (minute limits, cooldowns: wait ~60s and retry) or a ceiling
(daily/monthly quotas: leave work queued for the next run).
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import base64
import json
import logging
import math
import os
import re
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar

import openai
from pydantic import BaseModel, ValidationError

from .jsonutil import extract_json_object, strip_reasoning
from .limits import DEFAULT_CEILING, Limits, QuotaCounter, RateLimiter

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
ClientFactory = Callable[[str, str, float], Any]

CIRCUIT_THRESHOLD = 3
MAX_OUTPUT_TOKENS = 16000  # the widest retry for a reply cut off at max_tokens
CIRCUIT_OPEN_SECONDS = 300
# a model that answers 429 again after its pause is paused longer, up to 30 min, and the run goes on with the other
# models; a 429 is a day's ceiling only when it names a daily window (owner, 2026-10-20: a few passing 429s from Z.AI
# and Mistral, or Gemini's bare "quota", left a model out of the run)
RATE_PAUSES = (60.0, 300.0, 1800.0)
MAX_PACING_WAIT = 30.0
MAX_SLOT_WAIT = 10.0   # wait for a free slot on a concurrency-capped model, then try the next one
PREFER_WEIGHT = 5      # PREFER_MODEL's weight multiplier: about 6 requests in 10 on a pass-2 route. Was 20 (9 in 10), which
                       # left the free Z.AI slots, two keys since 22 Oct, almost idle during the drain (owner, 22 Oct)

CAP_MIN_CALL_S = 30.0  # a card-writing cap with less than this left starts no further call (TODO 35, F149)

UNAVAILABLE, CEILING, TRANSIENT, FAILED = "unavailable", "ceiling", "transient", "failed"


class AIError(RuntimeError):
    pass


class AllProvidersFailed(AIError):
    def __init__(self, route: str, outcomes: list[tuple[str, str, str]], capped_s: float = 0.0):
        self.route = route
        self.outcomes = outcomes  # (target key, kind, detail)
        # the filing's card-writing cap (seconds) ended the walk across targets: defer now, do not wait and retry
        self.capped_s = capped_s
        self.capped = capped_s > 0
        kinds = {kind for _, kind, _ in outcomes}
        self.attempted = FAILED in kinds
        # Nothing was tried because every usable model is paced, cooling down
        # or circuit-broken: waiting a minute will help.
        self.transient = not self.attempted and TRANSIENT in kinds
        # Nothing was tried and the only blockers are quota ceilings: stop for today.
        self.quota_exhausted = not self.attempted and not self.transient and CEILING in kinds
        detail = "; ".join(f"{k}: {d}" for k, _, d in outcomes[-8:])
        super().__init__(f"{route}: no provider could serve the request ({detail})")


# Model families by name: a second opinion, and the critic, are not of the writer's family, so the two do not share one
# blind spot (a second key's "gemini_2" is still Gemini).
_FAMILIES = (("gemini", "gemini"), ("gemma", "gemma"), ("glm", "glm"), ("nemotron", "nemotron"), ("deepseek", "deepseek"),
             ("llama", "llama"), ("gpt-oss", "gpt-oss"), ("ministral", "mistral"), ("mistral", "mistral"),
             ("qwen", "qwen"), ("minimax", "minimax"), ("kimi", "kimi"))


def model_family(model_label: str | None) -> str:
    """'gemini/gemini-3.6-flash' -> 'gemini'; 'openrouter/nvidia/nemotron-3.5-super-vl:free' -> 'nemotron'."""
    low = (model_label or "").lower()
    for word, name in _FAMILIES:
        if word in low:
            return name
    return low.split("/", 1)[0] or "unknown"


def expand_key_aliases(config: dict, env: dict[str, str]) -> dict:
    """A provider entry with `same_as = "<provider>"` is another key for that provider (owner, 2026-10-22: second keys for
    Gemini, Groq, NVIDIA and Z.AI, "work load will get divided"). It takes the base provider's settings, and every route
    entry of the base provider is repeated for it right after the original, so it has its own rate limiter, quota
    counter and usage row (provider "gemini_2" on the System page). An alias whose key is not set adds nothing."""
    providers = dict(config.get("providers", {}))
    aliases = {name: conf for name, conf in providers.items() if conf.get("same_as")}
    if not aliases:
        return config
    for name, conf in aliases.items():
        base = providers.get(conf["same_as"])
        if base is None:
            raise ValueError(f"provider {name} is same_as unknown provider {conf['same_as']}")
        providers[name] = {**base, **{k: v for k, v in conf.items() if k not in ("same_as", "only_routes")}}
    live = {name for name, conf in aliases.items() if (env.get(providers[name]["api_key_env"]) or "").strip()}
    # A key kept for named routes only (`only_routes`): on those routes it takes the place of the base provider and its
    # other keys, and it is on no other route. GEMINI_API_KEY_3 (owner, 26 Oct 2026) is a Gemini project of its own for
    # call memory, so that reading never spends the cards' 20-a-day Flash quota and the cards never spend its own.
    owned = {route: name for name in sorted(live) for route in aliases[name].get("only_routes", [])}
    routes = {}
    for route, entries in config.get("routes", {}).items():
        out = []
        for entry in entries:
            keeper = owned.get(route)
            if keeper and entry["provider"] == aliases[keeper]["same_as"]:
                out.append({**entry, "provider": keeper})
                continue
            out.append(entry)
            out += [{**entry, "provider": name} for name in sorted(live) if aliases[name]["same_as"] == entry["provider"]
                    and not aliases[name].get("only_routes") and not (keeper and aliases[keeper]["same_as"] == entry["provider"])]
        routes[route] = out
    return {**config, "providers": {k: v for k, v in providers.items() if k not in aliases or k in live}, "routes": routes}


@dataclass
class Target:
    route: str
    provider: str
    model: str
    base_url: str
    api_key: str | None
    timeout: float
    json_mode: bool = False
    max_tokens: int = 2000
    temperature: float = 0.1
    strip_reasoning: bool = False
    context_tokens: int | None = None
    weight: int = 1
    spare: bool = False
    extra_body: dict = field(default_factory=dict)
    # The share of the model's (and its provider's) day or month quota this route may take it up to: a route of spare
    # quota (the shadow critic) stops at, say, 60% and leaves the rest to the routes that share the model.
    max_share: float | None = None

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass
class Usage:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    failures: int = 0
    rate_limited: int = 0
    last_error: str | None = None


@dataclass
class AIResult:
    value: Any
    provider: str
    model: str
    latency_s: float
    raw_text: str = ""
    pack: dict | None = None   # a packed answer: {"id", "members"} - the filings that shared its request (ai/packer.py)

    @property
    def model_label(self) -> str:
        return f"{self.provider}/{self.model}"


def _default_client(base_url: str, api_key: str, timeout: float):
    # max_retries=0: the gateway owns retries and failover.
    return openai.OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)


def estimate_tokens(*texts: str) -> int:
    # Financial filings are number-dense; ~3 characters per token is a safe estimate.
    return sum(len(t) for t in texts) // 3 + 16


_ENV_REF = re.compile(r"\$\{(\w+)\}")


def _interpolate(value: str, env: dict[str, str]) -> str | None:
    missing = [name for name in _ENV_REF.findall(value) if not env.get(name)]
    if missing:
        return None
    return _ENV_REF.sub(lambda m: env[m.group(1)].rstrip("/"), value)


class _WeightedRotation:
    """Smooth weighted round-robin (as in nginx): even interleaving by weight."""

    def __init__(self, targets: list[Target]):
        self._targets = targets
        self._current = [0] * len(targets)
        self._lock = threading.Lock()

    def order(self) -> list[Target]:
        with self._lock:
            total = sum(t.weight for t in self._targets)
            for i, t in enumerate(self._targets):
                self._current[i] += t.weight
            ranked = sorted(range(len(self._targets)), key=lambda i: -self._current[i])
            self._current[ranked[0]] -= total
            return [self._targets[i] for i in ranked]


def _utc_day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _day_function(tz: str | None):
    """The provider's quota day as YYYY-MM-DD: UTC unless it names its own zone (`quota_tz` in providers.toml)."""
    if not tz:
        return _utc_day
    zone = ZoneInfo(tz)
    return lambda: datetime.now(zone).date().isoformat()


class AIGateway:
    def __init__(
        self,
        config: dict,
        usage_today: list[dict] | None = None,
        usage_month: list[dict] | None = None,
        client_factory: ClientFactory = _default_client,
        env: dict[str, str] | None = None,
    ):
        env = env if env is not None else dict(os.environ)
        gw = config.get("gateway", {})
        self.ceiling = float(gw.get("safety_ceiling", DEFAULT_CEILING))
        strategies = gw.get("strategies", {})
        self._client_factory = client_factory
        self._clients: dict[str, Any] = {}
        self._lock = threading.Lock()
        self.routes: dict[str, list[Target]] = {}
        self._rotations: dict[str, _WeightedRotation] = {}
        self.limiters: dict[str, RateLimiter] = {}
        self.slots: dict[str, threading.BoundedSemaphore] = {}  # per-model cap on requests in flight
        self.raw_limits: dict[str, Limits] = {}
        self.provider_quota: dict[str, QuotaCounter] = {}
        self.usage: dict[str, Usage] = {}
        self.disabled: dict[str, str] = {}
        self.unavailable_at_start: dict[str, str] = {}   # target key -> why it cannot be called at all (no key / URL)
        self.disabled_providers: dict[str, str] = {}   # a rejected key disables every model on it
        self._failures: dict[str, int] = {}
        self._rate_hits: dict[str, int] = {}
        self._circuit_open_until: dict[str, float] = {}
        self.deadline: float | None = None  # time.monotonic() after which no request starts
        # One filing's card-writing cap (TODO 35, F149): per worker thread, because a filing's pass 2 runs on one thread
        # while the run deadline above is shared. `card_scope` opens it for a filing, `start_cap` starts its clock.
        self.pass2_cap_s: float = 0.0
        self._cap = threading.local()
        # Live reserve (ai-quality plan item 1): the best free writers keep most of each day's requests for live
        # filings. A backfill request (bulk=True) may use a reserved model only while its day's requests stay under
        # (1 - share) of its ceiling, except in `bulk_hours` (local time), once the evening flood is over.
        reserve = gw.get("live_reserve", {})
        self.reserved: frozenset[str] = frozenset(reserve.get("models", ()))
        self.reserve_share = float(reserve.get("share", 0.0))
        # Gemini's day runs to midnight Pacific (12:30 IST), so the night's bulk hours and the next market morning
        # share one quota day: releasing the whole reserve overnight left the 21 Oct morning's live filings without
        # Flash (every Flash model at its day by 08:30 IST). The bulk hours keep this share instead.
        self.bulk_hours_share = float(reserve.get("bulk_hours_share", 0.0))
        self._bulk_hours = _hours(reserve.get("bulk_hours"))
        zone = ZoneInfo(reserve.get("tz", "Asia/Kolkata"))
        self.local_now: Callable[[], datetime] = lambda: datetime.now(zone)

        # a second key ("gemini_2", same_as = "gemini") is the same provider and the same models: what is avoided or
        # reserved for its base is avoided or reserved for it too
        self._base_provider = {name: conf["same_as"] for name, conf in config.get("providers", {}).items()
                               if conf.get("same_as")}
        own_quota = {name for name, conf in config.get("providers", {}).items() if conf.get("only_routes")}
        config = expand_key_aliases(config, env)
        providers = config.get("providers", {})
        self.reserved = self.reserved | frozenset(
            f"{alias}:{key.split(':', 1)[1]}" for alias, base in self._base_provider.items()
            if alias not in own_quota   # a key of its own for named routes has a quota of its own, not the cards' reserve
            for key in self.reserved if key.split(":", 1)[0] == base)
        self._day_of = {name: _day_function(pconf.get("quota_tz")) for name, pconf in providers.items()}
        # a ledger row counts for its provider's own day (usage rows for both the UTC day and that day may be passed)
        today = {f"{u['provider']}:{u['model']}": u for u in usage_today or []
                 if u.get("day") in (None, self._day_of.get(u["provider"], _utc_day)())}
        month = {f"{u['provider']}:{u['model']}": u for u in usage_month or []}
        tokens = lambda row: int(row.get("input_tokens", 0) or 0) + int(row.get("output_tokens", 0) or 0)  # noqa: E731

        for name, pconf in providers.items():
            plimits = Limits.from_config(pconf.get("limits"))
            self.provider_quota[name] = QuotaCounter(
                plimits.scaled(self.ceiling), day_of=self._day_of[name],
                day_requests=sum(int(r.get("requests", 0)) for k, r in today.items() if k.startswith(name + ":")),
                day_tokens=sum(tokens(r) for k, r in today.items() if k.startswith(name + ":")),
                month_requests=sum(int(r.get("requests", 0)) for k, r in month.items() if k.startswith(name + ":")),
                month_tokens=sum(tokens(r) for k, r in month.items() if k.startswith(name + ":")),
            )

        # A dispatched drain run may favour one model on every route that has it (owner, 21 Oct 2026: "use deepseek for
        # pending and let's clear them"): PREFER_MODEL=provider:model multiplies its weight. Scheduled runs never set it.
        prefer = (env.get("PREFER_MODEL") or "").strip()
        only = {k.strip() for k in (env.get("ONLY_MODEL") or "").split(",") if k.strip()}
        # A card-writing test of a trial model (TODO 142 step 4, owner 30 Oct 2026): a named model that is on no route but the
        # trial_new route is put, with its trial settings, on every route that has a primary, when ONLY_MODEL_ON_ALL_ROUTES=1.
        trial_entries = {f"{e['provider']}:{e['model']}": e for e in config.get("routes", {}).get("trial_new", [])}
        on_all = (env.get("ONLY_MODEL_ON_ALL_ROUTES") or "").strip() == "1"

        def build(route: str, entry: dict) -> tuple[Target, str | None]:
            pconf = providers.get(entry["provider"])
            if pconf is None:
                raise ValueError(f"route {route} references unknown provider {entry['provider']}")
            base_url = _interpolate(pconf["base_url"], env)
            reason = None
            if not base_url:
                reason = f"not configured: base_url {pconf['base_url']} has an unset variable"
            elif not (env.get(pconf["api_key_env"]) or "").strip():
                reason = f"not configured: {pconf['api_key_env']} is not set"
            target = Target(
                route=route,
                provider=entry["provider"],
                model=entry["model"],
                base_url=base_url or pconf["base_url"],
                api_key=((env.get(pconf["api_key_env"]) or "").strip() or None) if base_url else None,
                timeout=float(entry.get("timeout_s", pconf.get("timeout_s", 60))),
                json_mode=bool(entry.get("json_mode", False)),
                max_tokens=int(entry.get("max_tokens", 2000)),
                temperature=float(entry.get("temperature", 0.1)),
                strip_reasoning=bool(entry.get("strip_reasoning", False)),
                context_tokens=entry.get("context_tokens"),
                weight=max(1, int(entry.get("weight", 1))),
                spare=bool(entry.get("spare", False)),
                extra_body=dict(entry.get("extra_body", {})),
                max_share=float(entry["max_share"]) if entry.get("max_share") is not None else None,
            )
            if prefer and target.key == prefer and target.api_key:
                target.weight *= PREFER_WEIGHT
            if reason:
                self.unavailable_at_start[target.key] = reason
            if target.key not in self.limiters:
                limits = Limits.from_config(entry.get("limits"))
                scaled = limits.scaled(self.ceiling)
                t_row, m_row = today.get(target.key, {}), month.get(target.key, {})
                self.raw_limits[target.key] = limits
                self.limiters[target.key] = RateLimiter(scaled, QuotaCounter(
                    scaled, day_of=self._day_of.get(target.provider),
                    day_requests=int(t_row.get("requests", 0)), day_tokens=tokens(t_row),
                    month_requests=int(m_row.get("requests", 0)), month_tokens=tokens(m_row),
                ))
                self.usage[target.key] = Usage()
            concurrency = (entry.get("limits") or {}).get("concurrency")
            if concurrency and target.key not in self.slots:
                self.slots[target.key] = threading.BoundedSemaphore(int(concurrency))
            return target, reason

        for route, entries in config.get("routes", {}).items():
            targets = [build(route, entry)[0] for entry in entries]
            # A model trial (scripts/model_trial.py) sends every route that has the model to it alone, spare or not:
            # ONLY_MODEL=provider:model[,provider:model]. Scheduled runs never set it.
            # A measured call-memory test may set the models' thinking (CALL_MEMORY_REASONING=none/low/medium/high; owner, 30
            # Oct 2026: Flash-Lite reads with thinking off). Scheduled runs never set it.
            if route == "call_memory" and (think := (env.get("CALL_MEMORY_REASONING") or "").strip()):
                for t in targets:
                    if t.provider.startswith("gemini"):
                        t.extra_body = {**t.extra_body, "reasoning_effort": think}
            # card writing only (review of the harness, 30 Oct 2026): a text model on vision, the critic, call memory or level 1
            # would leave those routes with no target that can do their work
            if on_all and route.startswith(("pass2", "memory_seed")) and any(not t.spare for t in targets) \
                    and not any(t.key in only for t in targets):
                for key in sorted(only & trial_entries.keys()):
                    entry = dict(trial_entries[key])
                    # room for a whole card, not the trial's one-line answer; the window stays the model's own, so the
                    # oversize guard still skips a prompt it cannot take
                    if (room := max(int(entry.get("max_tokens") or 0), int(entries[0].get("max_tokens") or 0))):
                        entry["max_tokens"] = room
                    targets.append(build(route, entry)[0])
                    targets[-1].spare = False
            if only and any(t.key in only for t in targets):
                targets = [t for t in targets if t.key in only]
                for t in targets:
                    t.spare = False
            self.routes[route] = targets
            down = [f"{t.key} ({self.unavailable_at_start[t.key]})" for t in targets
                    if not t.spare and t.key in self.unavailable_at_start]
            if down:  # one line a route, only when a primary cannot be called (the DeepSeek gap of run 40192588628)
                log.info("gateway %s: primary targets unavailable: %s", route, ", ".join(down))
            if strategies.get(route) == "weighted":
                self._rotations[route] = _WeightedRotation([t for t in targets if not t.spare])

    # ------------------------------------------------------------------ public API

    def set_route(self, route: str, targets: list[Target]) -> None:
        """Point a route at other targets for this process (call_seed.use_seed_route). A weighted route's rotation is
        rebuilt with it: the seed replaced the card routes' lists and kept their rotations, so pass2_long still rotated
        over Gemini and DeepSeek and never reached the seed's free models (seed-calls run 3, 2026-10-20: 22 failed)."""
        self.routes[route] = list(targets)
        if route in self._rotations:
            primary = [t for t in targets if not t.spare]
            if primary:
                self._rotations[route] = _WeightedRotation(primary)
            else:
                del self._rotations[route]

    def has_route(self, route: str) -> bool:
        return any(t.api_key for t in self.routes.get(route, []))

    def complete_json(self, route: str, system: str, user: str, schema: type[T], avoid_providers: tuple[str, ...] = (),
                      bulk: bool = False, allow: Callable[[Target], bool] | None = None) -> AIResult:
        """One validated JSON reply. ``avoid_providers`` (provider names or model labels, see `_avoided`) are tried
        only after every other target, so a second opinion comes from another provider and model family whenever one
        is available. ``bulk`` marks a backfill
        request: it leaves the reserved models' live share alone (`[gateway.live_reserve]`). ``allow``, when given, leaves
        out every target it refuses (the critic: never a model of the card writer's own family)."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return self._run(route, messages, schema, avoid=avoid_providers, bulk=bulk, allow=allow)

    def transcribe_image(self, png: bytes, route: str = "vision") -> str:
        b64 = base64.b64encode(png).decode()
        messages = [{"role": "user", "content": [
            {"type": "text", "text": (
                "Transcribe all text, numbers and tables on this page exactly. Use Markdown "
                "tables for tabular data. Preserve units (Rs. in lakhs/crores) and brackets "
                "for negative numbers. Output only the transcription."
            )},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}]
        return self._run(route, messages, None, image_tokens=1500).value

    def ask_image(self, png: bytes, question: str, route: str = "vision") -> str:
        """One question about one image, answered in text (call memory's slide check, CALL_MEMORY_VISION_CHECK)."""
        b64 = base64.b64encode(png).decode()
        messages = [{"role": "user", "content": [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}]
        return self._run(route, messages, None, image_tokens=1500).value

    def usage_rows(self, day: str, updated_at: str) -> list[dict]:
        rows = []
        for key, usage in self.usage.items():
            if not (usage.requests or usage.failures or usage.rate_limited):
                continue
            provider, model = key.split(":", 1)
            limits = self.raw_limits[key]
            own = self._day_of.get(provider)
            rows.append({
                "day": own() if own is not None and own is not _utc_day else day, "provider": provider, "model": model,
                "requests": usage.requests, "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens, "failures": usage.failures,
                "rate_limited": usage.rate_limited, "limit_rpd": limits.rpd, "limit_tpd": limits.tpd,
                "last_error": usage.last_error, "updated_at": updated_at,
            })
        return rows

    def can_serve(self, route: str, bulk: bool = False) -> bool:
        """Whether any target on the route could take a request now: it has a key, is not switched off for this run,
        has quota left for the day and is not cooling down, and for a backfill request (``bulk``) is not kept for live
        filings. The packer asks before it holds a filing back to fill a pack (22 Oct: 84 packs failed in two runs with
        every Gemini model at its day's quota; a backfill pack waited for models only live filings could use)."""
        now = time.monotonic()
        for t in self.routes.get(route, []):
            if not t.api_key or t.key in self.disabled or t.provider in self.disabled_providers:
                continue
            if bulk and self.reserved_for_live(t):
                continue
            limiter, pquota = self.limiters[t.key], self.provider_quota.get(t.provider)
            if limiter.quota.exhausted() or (pquota and pquota.exhausted()):
                continue
            if self._circuit_open_until.get(t.key, 0) > now or limiter.cooling_down():
                continue
            return True
        return False

    def health(self) -> list[dict]:
        out = []
        for key, limiter in self.limiters.items():
            provider = key.split(":", 1)[0]
            pquota = self.provider_quota.get(provider)
            status = "ok"
            if key in self.disabled or provider in self.disabled_providers:
                status = "disabled"
            elif limiter.quota.exhausted() or (pquota and pquota.exhausted()):
                status = "ceiling"
            elif self._circuit_open_until.get(key, 0) > time.monotonic() or limiter.cooling_down():
                status = "cooling"
            out.append({
                "target": key, "status": status,
                "utilisation": round(max(limiter.quota.utilisation(), pquota.utilisation() if pquota else 0), 3),
                "last_error": self.usage[key].last_error,
            })
        return out

    # ------------------------------------------------------------------ internals

    def _ordered(self, route: str, avoid: tuple[str, ...] = ()) -> list[Target]:
        targets = self.routes[route]
        rotation = self._rotations.get(route)
        primary = rotation.order() if rotation else [t for t in targets if not t.spare]
        ordered = primary + [t for t in targets if t.spare]
        if not avoid:
            return ordered
        avoided = [t for t in ordered if self._avoided(t, avoid)]
        return [t for t in ordered if t not in avoided] + avoided

    def base_provider(self, provider: str) -> str:
        return self._base_provider.get(provider, provider)

    def _avoided(self, target: Target, avoid: tuple[str, ...]) -> bool:
        """``avoid`` holds provider names and model labels ("gemini_2/gemini-3.6-flash"): a target is avoided when it is
        the same provider by any of its keys, or, for a label, a model of the same family on any provider (a second
        opinion from the writer's own model on a second key checked nothing: AI-layer survey, 24 Oct 2026)."""
        bases = {self.base_provider(a.split("/", 1)[0]) for a in avoid}
        families = {model_family(a) for a in avoid if "/" in a}
        return (self.base_provider(target.provider) in bases
                or bool(families) and model_family(f"{target.provider}/{target.model}") in families)

    def _client(self, target: Target):
        with self._lock:
            key = f"{target.provider}|{target.base_url}|{target.timeout}"
            if key not in self._clients:
                self._clients[key] = self._client_factory(target.base_url, target.api_key, target.timeout)
            return self._clients[key]

    def reserved_for_live(self, target: Target) -> bool:
        """True when a backfill request must leave this model to live filings for now."""
        share = self.bulk_hours_share if self._in_bulk_hours() else self.reserve_share
        if target.key not in self.reserved or share <= 0:
            return False
        quota = self.limiters[target.key].quota
        if not quota.limits.rpd:
            return False
        return quota.day_requests >= math.floor(quota.limits.rpd * (1 - share))

    def _in_bulk_hours(self) -> bool:
        if self._bulk_hours is None:
            return False
        start, end = self._bulk_hours
        now = self.local_now()
        minute = now.hour * 60 + now.minute
        return start <= minute < end if start <= end else (minute >= start or minute < end)

    def _skip(self, target: Target, est_in: int, est_total: int, bulk: bool = False) -> tuple[str, str] | None:
        if not target.api_key:
            return UNAVAILABLE, "not configured"
        if target.key in self.disabled:
            return UNAVAILABLE, self.disabled[target.key]
        if target.provider in self.disabled_providers:
            return UNAVAILABLE, self.disabled_providers[target.provider]
        if target.context_tokens and est_in > target.context_tokens:
            return UNAVAILABLE, "prompt exceeds context window"
        tpm = self.limiters[target.key].limits.tpm
        if tpm and est_total > tpm:
            # It can never fit in this model's minute: reported as "paced" it was a busy provider for ever, and
            # the filing was deferred on every run without failing (audit of discard paths, 2026-10-18).
            return UNAVAILABLE, "prompt exceeds the per-minute token limit"
        reason = self.limiters[target.key].quota.exhausted(est_total)
        pquota = self.provider_quota.get(target.provider)
        reason = reason or (pquota.exhausted(est_total) if pquota else None)
        if reason:
            return CEILING, f"{reason} ({self.ceiling:.0%} safety limit)"
        if bulk and self.reserved_for_live(target):
            return CEILING, f"kept for live filings ({self.reserve_share:.0%} of the day)"
        if target.max_share is not None:
            used = max(self.limiters[target.key].quota.utilisation(), pquota.utilisation() if pquota else 0.0)
            if used >= target.max_share:
                return CEILING, f"route's share of the quota used ({used:.0%} of {target.max_share:.0%})"
        if self._circuit_open_until.get(target.key, 0) > time.monotonic():
            return TRANSIENT, "circuit open"
        return None

    def _note_failure(self, target: Target, message: str, *, rate_limited: bool = False) -> None:
        with self._lock:
            usage = self.usage[target.key]
            usage.last_error = message[:300]
            if rate_limited:
                usage.rate_limited += 1
                return
            usage.failures += 1
            count = self._failures.get(target.key, 0) + 1
            self._failures[target.key] = count
            if count >= CIRCUIT_THRESHOLD:
                self._circuit_open_until[target.key] = time.monotonic() + CIRCUIT_OPEN_SECONDS
                self._failures[target.key] = 0
                log.warning("circuit opened for %s after %d failures", target.key, count)

    def _run(self, route: str, messages: list[dict], schema: type[BaseModel] | None, image_tokens: int = 0,
             avoid: tuple[str, ...] = (), bulk: bool = False, allow: Callable[[Target], bool] | None = None) -> AIResult:
        if route not in self.routes:
            raise AIError(f"unknown route: {route}")
        prompt_chars = "".join(m["content"] if isinstance(m["content"], str) else "" for m in messages)
        est_in = estimate_tokens(prompt_chars) + image_tokens
        outcomes: list[tuple[str, str, str]] = []
        for target in self._ordered(route, avoid):
            if allow is not None and not allow(target):
                outcomes.append((target.key, UNAVAILABLE, "left out for this request"))
                continue
            est = est_in + target.max_tokens
            skip = self._skip(target, est_in, est, bulk)
            if skip:
                outcomes.append((target.key, *skip))
                continue
            left = self._time_left()
            if left is not None and left <= 0:
                outcomes.append((target.key, TRANSIENT, "run deadline reached"))
                continue
            if self._cap_reached():   # this filing has used its card-writing time: stop the walk (TODO 35)
                state = self._cap.state
                outcomes.append((target.key, TRANSIENT, self._cap_message()))
                if not state["logged"]:
                    state["logged"] = True
                    log.info("gateway %s: %s; stopping the walk with %d target(s) passed over", route,
                             self._cap_message(), len(outcomes))
                raise AllProvidersFailed(route, outcomes, capped_s=state["seconds"])
            pquota = self.provider_quota.get(target.provider)
            extra = (pquota,) if pquota else ()
            wait = MAX_PACING_WAIT if left is None else min(MAX_PACING_WAIT, left)
            slot = self.slots.get(target.key)
            # A model that allows N requests at once (Z.ai's free GLM models allow one) is waited on
            # briefly, then skipped for the next target; the request is counted only once it goes.
            if slot is not None and not slot.acquire(timeout=min(wait, MAX_SLOT_WAIT)):
                outcomes.append((target.key, TRANSIENT, "busy: concurrency limit"))
                continue
            try:
                if not self.limiters[target.key].acquire(est, max_wait=wait, extra_quota=extra):
                    outcomes.append((target.key, TRANSIENT, "paced"))
                    continue
                try:
                    result = self._call_target(target, messages, schema, est, extra)
                    if outcomes:  # off its first choice: say which targets were passed over and why (TODO 33)
                        log.info("%s", _fallback_line(route, target.key, outcomes))
                    return result
                except _Retryable as exc:
                    kind = TRANSIENT if exc.transient else FAILED
                    outcomes.append((target.key, kind, str(exc)))
                    continue
            finally:
                if slot is not None:
                    slot.release()
        if self._cap_reached():   # the last target's own call ran the cap out: still a cap stop, not a busy wait
            raise AllProvidersFailed(route, outcomes, capped_s=self._cap.state["seconds"])
        raise AllProvidersFailed(route, outcomes)

    def _time_left(self) -> float | None:
        return None if self.deadline is None else self.deadline - time.monotonic()

    @contextmanager
    def card_scope(self, capped: bool = True):
        """Around one filing's analysis on this thread: a cap started inside it ends with it. ``capped=False`` (a filing
        whose cap was lifted, F149) never starts one."""
        saved = getattr(self._cap, "state", None)
        self._cap.state = {"deadline": None, "seconds": 0.0, "logged": False, "off": not capped}
        try:
            yield
        finally:
            self._cap.state = saved

    def start_cap(self, seconds: float | None = None) -> None:
        """Start this filing's card-writing clock (first call only; later calls keep the first start). No scope, or
        0 seconds (`PASS2_CAP_S=0`): no cap."""
        state = getattr(self._cap, "state", None)
        seconds = self.pass2_cap_s if seconds is None else seconds
        if state is None or state["off"] or state["deadline"] is not None or seconds <= 0:
            return
        state["deadline"] = time.monotonic() + seconds
        state["seconds"] = float(seconds)

    @contextmanager
    def uncapped(self):
        """A shared request (the packed call) is not one filing's time: no cap while it runs on this thread."""
        state = getattr(self._cap, "state", None)
        saved = state["deadline"] if state else None
        if state:
            state["deadline"] = None
        try:
            yield
        finally:
            if state and saved is not None:
                state["deadline"] = saved

    def _cap_left(self) -> float | None:
        state = getattr(self._cap, "state", None)
        if not state or state["deadline"] is None:
            return None
        return state["deadline"] - time.monotonic()

    def _cap_reached(self) -> bool:
        left = self._cap_left()
        return left is not None and left < CAP_MIN_CALL_S

    def _cap_message(self) -> str:
        state = getattr(self._cap, "state", None) or {}
        return f"card-writing cap reached ({state.get('seconds', 0):.0f} s)"

    def _call_target(self, target: Target, messages: list[dict], schema, est: int, extra: tuple) -> AIResult:
        limiter = self.limiters[target.key]
        usage = self.usage[target.key]
        client = self._client(target)
        convo = list(messages)
        repaired = json_fallback = widened = False
        max_tokens = target.max_tokens
        while True:  # at most one JSON-mode fallback, one wider retry and one JSON repair, same model
            kwargs: dict[str, Any] = {
                "model": target.model,
                "messages": convo,
                "temperature": target.temperature,
                "max_tokens": max_tokens,
            }
            if target.json_mode and schema is not None:
                kwargs["response_format"] = {"type": "json_object"}
            if target.extra_body:
                kwargs["extra_body"] = target.extra_body
            left = self._time_left()
            if left is not None:
                kwargs["timeout"] = max(15.0, min(target.timeout, left))
            started = time.monotonic()
            try:
                resp = client.chat.completions.create(**kwargs)
            except openai.RateLimitError as exc:
                message = str(exc)
                if _DAILY_QUOTA.search(message):
                    limiter.quota.forced_exhausted = "provider reported daily quota reached"
                hits = self._rate_hits.get(target.key, 0)
                self._rate_hits[target.key] = hits + 1
                limiter.cooldown(max(_retry_after(exc), RATE_PAUSES[min(hits, len(RATE_PAUSES) - 1)]))
                self._note_failure(target, f"429: {message}", rate_limited=True)
                raise _Retryable("rate limited (429)", transient=True) from exc
            except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
                if _MODEL_NOT_ALLOWED.search(str(exc)):  # a 403 about this model's tier, not the key
                    self.disabled[target.key] = "model not in subscription tier"
                    self._note_failure(target, f"403 model not allowed: {exc}")
                    log.error("%s: model not available on this account's plan; update config/providers.toml", target.key)
                    raise _Retryable("model not allowed") from exc
                self.disabled[target.key] = f"auth error {exc.status_code}"
                self.disabled_providers[target.provider] = f"auth error {exc.status_code}"
                self._note_failure(target, f"auth error {exc.status_code}: {exc}")
                log.error("%s rejected the API key (%s); every %s model disabled for this run",
                          target.key, exc.status_code, target.provider)
                raise _Retryable("auth error") from exc
            except openai.NotFoundError as exc:
                self.disabled[target.key] = "model not found"
                self._note_failure(target, f"404 model not found: {exc}")
                log.error("%s: model not found; update config/providers.toml", target.key)
                raise _Retryable("model not found") from exc
            except openai.BadRequestError as exc:
                message = str(exc)
                if kwargs.get("response_format") and not json_fallback and _JSON_MODE_UNSUPPORTED.search(message):
                    log.warning("%s rejected JSON mode; retrying without it", target.key)
                    target.json_mode = False
                    json_fallback = True
                    if not limiter.acquire(est, max_wait=MAX_PACING_WAIT, extra_quota=extra):
                        raise _Retryable("paced", transient=True) from exc
                    continue
                self._note_failure(target, f"400 bad request: {message}")
                raise _Retryable("bad request") from exc
            except (openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError) as exc:
                # An outage, not a problem with the filing: fail over, and if nothing else can
                # serve it the filing waits for a later run without losing an attempt.
                self._note_failure(target, f"{type(exc).__name__}: {exc}")
                if isinstance(exc, openai.APITimeoutError):  # httpx logs only responses that arrive (TODO 33)
                    limit = float(kwargs.get("timeout", target.timeout))
                    elapsed = time.monotonic() - started
                    log.warning("gateway call timed out: %s after %.0f s (limit %.0f s)", target.key, elapsed, limit)
                    raise _Retryable(f"timeout after {limit:.0f}s", transient=True) from exc
                raise _Retryable(type(exc).__name__, transient=True) from exc
            except openai.APIStatusError as exc:
                if exc.status_code == 410:  # the provider retired the model
                    self.disabled[target.key] = "model retired"
                    self._note_failure(target, f"410 model retired: {exc}")
                    log.error("%s: model retired; update config/providers.toml", target.key)
                    raise _Retryable("model retired") from exc
                self._note_failure(target, f"HTTP {exc.status_code}: {exc}")
                raise _Retryable(f"HTTP {exc.status_code}", transient=exc.status_code >= 500) from exc
            except openai.APIError as exc:  # e.g. a body that is not JSON at all
                self._note_failure(target, f"{type(exc).__name__}: {exc}")
                raise _Retryable(type(exc).__name__, transient=True) from exc
            if not hasattr(resp, "choices"):  # the SDK returns the raw text when a 200 body is not JSON
                self._note_failure(target, "malformed response")
                raise _Retryable("malformed response", transient=True)

            latency = time.monotonic() - started
            in_tok = getattr(resp.usage, "prompt_tokens", None) if getattr(resp, "usage", None) else None
            out_tok = getattr(resp.usage, "completion_tokens", None) if getattr(resp, "usage", None) else None
            with self._lock:
                usage.requests += 1
                if in_tok is not None and out_tok is not None:
                    usage.input_tokens += in_tok
                    usage.output_tokens += out_tok
            if in_tok is not None and out_tok is not None:
                limiter.settle(est, in_tok + out_tok, extra_quota=extra)
            text = (resp.choices[0].message.content or "") if resp.choices else ""
            if not isinstance(text, str):  # a proxy that passed a parsed JSON reply through
                text = json.dumps(text, ensure_ascii=False)
            if target.strip_reasoning:
                text = strip_reasoning(text)
            if schema is None:
                if not text.strip():
                    self._note_failure(target, "empty response")
                    raise _Retryable("empty response")
                self._failures[target.key] = self._rate_hits[target.key] = 0
                return AIResult(text, target.provider, target.model, latency, text)
            try:
                value = schema.model_validate(extract_json_object(text))
            except (ValueError, ValidationError) as exc:
                problem = _short_error(exc)
                # A reply cut off at max_tokens is not a malformed one: asking for a "repair" in the same room cut it off
                # again ("no JSON object in response", 23 of DeepSeek's 214 calls on 22 Oct). It gets one try with twice
                # the room instead (MAX_OUTPUT_TOKENS at most), and the failure says it was cut off.
                finish = getattr(resp.choices[0], "finish_reason", None) if resp.choices else None
                if finish == "length":
                    if not widened and max_tokens < MAX_OUTPUT_TOKENS:
                        widened = True
                        max_tokens = min(max_tokens * 2, MAX_OUTPUT_TOKENS)
                        log.info("%s stopped at its max_tokens; trying again with %d", target.key, max_tokens)
                        if self._cap_reached():   # a repeat call would run past the filing's card-writing cap
                            raise _Retryable(self._cap_message(), transient=True) from exc
                        if not limiter.acquire(est, max_wait=MAX_PACING_WAIT, extra_quota=extra):
                            raise _Retryable("paced before a wider retry", transient=True) from exc
                        continue
                    self._note_failure(target, f"cut off at max_tokens {max_tokens}: {problem}")
                    raise _Retryable("cut off at max_tokens") from exc
                if not repaired:
                    repaired = True
                    log.info("%s returned invalid output (%s); asking for a repair", target.key, problem)
                    convo = convo + [
                        {"role": "assistant", "content": text[:6000]},
                        {"role": "user", "content": (
                            f"That reply did not match the required JSON schema: {problem}. "
                            "Reply with only the corrected JSON object."
                        )},
                    ]
                    if self._cap_reached():   # a repeat call would run past the filing's card-writing cap
                        raise _Retryable(self._cap_message(), transient=True) from exc
                    if not limiter.acquire(est, max_wait=MAX_PACING_WAIT, extra_quota=extra):
                        raise _Retryable("paced before repair", transient=True) from exc
                    continue
                self._note_failure(target, f"invalid output after repair: {problem}")
                raise _Retryable("invalid output") from exc
            self._failures[target.key] = self._rate_hits[target.key] = 0
            return AIResult(value, target.provider, target.model, latency, text)


# A provider saying it does not support JSON mode, not a model that failed to produce valid JSON
# (Groq's "json_validate_failed" is the latter).
_JSON_MODE_UNSUPPORTED = re.compile(r"response_format.*(?:not supported|unsupported|invalid|unknown)|"
                                    r"(?:not supported|unsupported|unknown).*response_format|json_object.*not supported",
                                    re.I | re.S)


def _fallback_line(route: str, served: str, outcomes: list[tuple[str, str, str]], max_reason: int = 80) -> str:
    """One line for a request that was not served by its first-choice target (TODO 33)."""
    passed = ", ".join(
        f"{key} ({kind}: {' '.join(str(detail).split())[:max_reason]})" for key, kind, detail in outcomes)
    return f"gateway {route}: served by {served} after {passed}"


class _Retryable(Exception):
    def __init__(self, message: str, transient: bool = False):
        super().__init__(message)
        self.transient = transient


# Gemini says "quota" in every 429 and names the window (PerMinute / PerDay); only a named day retires a model.
_DAILY_QUOTA = re.compile(r"per ?day|for the day|daily|\bTPD\b|\bRPD\b", re.I)
_MODEL_NOT_ALLOWED = re.compile(r"tier|not available|not allowed for (?:this )?model|model access|subscription", re.I)


def _hours(spec: str | None) -> tuple[int, int] | None:
    """ "21:00-09:00" -> (1260, 540): minutes after midnight; the window may cross midnight."""
    if not spec:
        return None
    minutes = [int(h) * 60 + int(m) for h, m in (part.strip().split(":") for part in spec.split("-"))]
    return minutes[0], minutes[1]


def _retry_after(exc: openai.APIStatusError) -> float:
    try:
        value = exc.response.headers.get("retry-after")
        if value:
            return min(max(float(value), 1.0), 3600.0)
    except Exception:
        pass
    return 60.0


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:4]]
        return "; ".join(parts)
    return str(exc)[:200]
