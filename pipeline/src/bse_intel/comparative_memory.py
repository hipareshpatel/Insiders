"""CARD_COMPARATIVE_MATCHES_MEMORY: a PDF-read results card whose earlier-quarter figures contradict memory (settings.
card_comparative_matches_memory; off by default, then nothing here runs). Blind audit 1 Nov 2026, MASKINVEST nse-106838206: a
scanned statement read with its columns out of order. The card said "net loss of ₹0.02 Cr in Q2FY27 versus ₹0.04 Cr in Q1FY27"
and "revenue ₹0.04 Cr against ₹0.03 Cr in Q1FY27"; memory, from the exchange's own files, holds Q1FY27 at a ₹0.02 Cr loss and
₹0.02 Cr revenue (₹0.04 Cr and ₹0.03 Cr are the year-ago quarter's). When the comparatives are read from the wrong column, so is
the quarter itself.

A figure the card gives for a named quarter ("₹0.04 Cr in Q1FY27") of a metric memory holds for that quarter (revenue, total
income, EBITDA, PBT, PAT; a loss by its size) is compared with memory's; one off by more than rounding (2% and ₹0.005 Cr) is a
contradiction. Only cards without the exchange's file, whose figures are the PDF's reading."""

from __future__ import annotations

import re

from .periods import canonical_period
from .settings import card_comparative_matches_memory

_METRICS = (("revenue", r"revenue|sales|top[- ]?line"), ("total_income", r"total income"), ("ebitda", r"EBITDA"),
            ("pbt", r"PBT|profit before tax"),
            ("pat", r"PAT|net (?:profit|loss)|profit after tax|(?<!operating )(?<!gross )(?:profit|loss)(?!\s+before)"))
_AMOUNT_PERIOD = re.compile(r"₹\s?(-?[\d,]+(?:\.\d+)?)\s*(?:cr|crore)\b[^.;₹]{0,20}?\b(?:in|for|during|of)\s+"
                            r"(Q[1-4]\s?FY\s?'?\d{2}|[1-4]Q\s?FY\s?\d{2})", re.I)


def _metric_before(text: str, at: int) -> str | None:
    clause = re.split(r";|\b(?:while|whereas|but)\b", text[:at])[-1]
    best = None
    for key, pattern in _METRICS:
        for m in re.finditer(rf"\b(?:{pattern})\b", clause, re.I):
            if best is None or m.start() >= best[1]:
                best = (key, m.start())
    return best[0] if best else None


def contradictions(texts: list[str], dossier: dict | None) -> list[str]:
    """Each "metric period: card X vs memory Y" the card's words state against memory, when the switch is on."""
    if not card_comparative_matches_memory():
        return []
    memory = {(m["metric"], m["period"]): m["value"] for m in (dossier or {}).get("financial_metrics") or []
              if isinstance(m, dict) and isinstance(m.get("value"), (int, float)) and m.get("period")}
    if not memory:
        return []
    found = []
    for text in texts:
        flat = (text or "").replace("**", "")
        for m in _AMOUNT_PERIOD.finditer(flat):
            metric = _metric_before(flat, m.start())
            period = canonical_period(re.sub(r"\s|'", "", m.group(2)).upper()) or m.group(2)
            held = memory.get((metric, period)) if metric else None
            if held is None and metric == "pat":
                held = memory.get(("pat_owners", period))
            if held is None:
                continue
            said = abs(float(m.group(1).replace(",", "")))
            if abs(said - abs(held)) > max(0.005, 0.02 * abs(held)):
                found.append(f"{metric} {period}: the card says ₹{said:g} Cr, memory (the exchange's file) ₹{abs(held):g} Cr")
    return list(dict.fromkeys(found))
