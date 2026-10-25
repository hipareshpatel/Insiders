"""A results file checked against SEBI's own sums (item 23, owner 25 Oct 2026: "big yes").

SEBI's results taxonomies (published by NSE, common to NSE and BSE; built into config/xbrl_sums/ by
scripts/xbrl_taxonomy_build.py) say how the lines of a statement add up: income less expenses is the profit before
exceptional items, that plus the exceptional items is the profit before tax, and so on. A file whose lines do not add up
within the company's own rounding was tagged wrongly, and a figure read from it is not to be trusted without the PDF.

Rounding comes from each figure's own `decimals`: a figure printed in crore (decimals -7) may be off by half a crore, one
printed in lakh to two places (decimals 3) by ₹500. A sum may be off by the rounding of every figure in it. No AI.
"""

from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .xbrl import _contexts, _local, _num, taxonomy

SUMS_DIR = Path(__file__).resolve().parents[2] / "config" / "xbrl_sums"
# the older (Regulation 33) results files name their entry point, not the IntegratedFinance folder
_LEGACY = (("Ind-AS_entry_point", "LEGACY_INDAS"), ("other_than_banks_entry_point", "LEGACY_OTHERTHANBANK"),
           ("banking_entry_point", "LEGACY_BANKING"), ("NBFC", "LEGACY_NBFC"), ("General_Insurance", "LEGACY_GI"),
           ("Life_Insurance", "LEGACY_LI"))
_SCHEMA = re.compile(rb'schemaRef[^>]*href="([^"]+)"')


@dataclass
class Mismatch:
    total: str
    context: str
    filed: float          # rupees, as tagged
    adds_up_to: float     # rupees, from its items
    tolerance: float

    @property
    def gap(self) -> float:
        return self.filed - self.adds_up_to


@dataclass
class SumReport:
    template: str
    checked: int = 0
    mismatches: list[Mismatch] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches

    def totals(self) -> set[str]:
        return {m.total for m in self.mismatches}


def template_key(data: bytes) -> str:
    """The config/xbrl_sums file this instance's sums come from ("" when none is known)."""
    integrated = taxonomy(data)
    if integrated:
        return integrated
    m = _SCHEMA.search(data[:8000])
    ref = m.group(1).decode("ascii", "ignore") if m else ""
    return next((key for marker, key in _LEGACY if marker.lower() in ref.lower()), "")


@lru_cache(maxsize=None)
def sums_for(key: str) -> dict[str, list[tuple[str, float]]]:
    path = SUMS_DIR / f"{key}.json"
    if not key or not path.exists():
        return {}
    body = json.loads(path.read_text())
    return {total: [(item, float(weight)) for item, weight in rows] for total, rows in body["sums"].items()}


def _rounding(decimals: str | None) -> float:
    """Half the last printed digit, in rupees: decimals -7 (crore) -> 5,000,000; 2 -> 0.005; INF -> 0."""
    if decimals is None:
        return 0.5   # not stated: a rupee
    if decimals.upper() == "INF":
        return 0.0
    try:
        return 0.5 * 10 ** (-int(decimals))
    except ValueError:
        return 0.5


def check(data: bytes) -> SumReport | None:
    """Every official sum the file can be checked on (its total and at least one item tagged, in the same plain
    context): the ones that do not add up within the rounding. None when the file is not a results instance we have
    sums for."""
    key = template_key(data)
    sums = sums_for(key)
    if not sums:
        return None
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    contexts = _contexts(root)
    facts: dict[tuple[str, str], tuple[float, float]] = {}
    for el in root.iter():
        ctx = el.get("contextRef")
        if ctx is None or el.text is None or el.get("unitRef") is None:
            continue
        info = contexts.get(ctx)
        value = _num(el.text.strip())
        if info is None or info["dims"] or value is None or not math.isfinite(value):
            continue
        facts.setdefault((_local(el.tag), ctx), (value, _rounding(el.get("decimals"))))
    report = SumReport(key)
    for (name, ctx), (total, slack) in facts.items():
        rows = sums.get(name)
        if not rows:
            continue
        present = [(facts[(item, ctx)], weight) for item, weight in rows if (item, ctx) in facts]
        if not present:
            continue
        report.checked += 1
        adds_up_to = sum(value * weight for (value, _), weight in present)
        tolerance = slack + sum(s for (_, s), _ in present) + 1.0
        if abs(total - adds_up_to) > tolerance:
            report.mismatches.append(Mismatch(name, ctx, total, adds_up_to, tolerance))
    return report
