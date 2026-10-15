"""The investable universe (blueprint §15 phase 3): which companies' filings are analysed.

Companies with a known market cap below ``UNIVERSE_MIN_MCAP_CR`` (default ₹100 Cr) are left out
unless the owner starred them; companies without a market cap yet stay in. The excluded list is
built after each market-data or company sync (one scan of the companies table) and published to
R2 as ``meta/universe.json``, so a pipeline run reads one small object instead of the table.
Filings of excluded companies go to the day's noise file with the reason, so nothing is silently lost.
"""

from __future__ import annotations

import json
import logging

from .settings import Settings
from .sinks.base import Sink
from .timeutil import now_iso

log = logging.getLogger(__name__)

UNIVERSE_KEY = "meta/universe.json"


def build(settings: Settings, sink: Sink) -> int:
    floor = settings.universe_min_mcap_cr
    rows = sink.query("companies_outside_universe", [floor]) if floor > 0 else []
    body = {"min_mcap_cr": floor, "excluded": sorted(r["scrip_code"] for r in rows), "built_at": now_iso()}
    sink.put_object(UNIVERSE_KEY, json.dumps(body, separators=(",", ":")).encode())
    log.info("universe: %d companies below ₹%g Cr excluded", len(rows), floor)
    return len(rows)


def load(sink: Sink) -> tuple[set[str], float]:
    try:
        body = sink.get_object(UNIVERSE_KEY)
    except Exception as exc:  # no universe file is the same as no filter
        log.warning("universe file unreadable: %s", exc)
        return set(), 0.0
    if not body:
        return set(), 0.0
    data = json.loads(body)
    return set(data.get("excluded", [])), float(data.get("min_mcap_cr", 0))
