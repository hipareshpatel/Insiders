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


_BASIS_WORD = re.compile(r"\b(standalone|consolidated)\b", re.I)


def _memory_by_basis(dossier: dict | None) -> dict[tuple[str, str], dict[str | None, set[float]]]:
    """{(metric, period): {basis or None: values}} from memory's figures."""
    from .watch_code import _entry_basis

    out: dict[tuple[str, str], dict[str | None, set[float]]] = {}
    for m in (dossier or {}).get("financial_metrics") or []:
        if isinstance(m, dict) and isinstance(m.get("value"), (int, float)) and m.get("period") and m.get("metric"):
            b = _entry_basis(m)
            out.setdefault((m["metric"], m["period"]), {}).setdefault(b.upper() if b else None, set()).add(float(m["value"]))
    return out


def _held(by_basis: dict[str | None, set[float]] | None, basis: str | None) -> float | None:
    """Memory's one figure on ``basis`` (blind review of release check 41318733817: a standalone card figure was set against
    consolidated memory, 1,274.46 vs 1,240.62); with the basis unknown, only a figure memory holds on one basis alone."""
    if not by_basis:
        return None
    if basis:   # memory that labels no basis at all is read as before; a figure labelled another basis never is
        values = by_basis.get(basis.upper()) or (by_basis.get(None, set()) if set(by_basis) == {None} else set())
    else:
        values = set().union(*by_basis.values()) if len(by_basis) == 1 else set()
    return next(iter(values)) if len(values) == 1 else None


def contradictions(texts: list[str], dossier: dict | None, basis: str | None = None) -> list[str]:
    """Each "metric period: card X vs memory Y" the card's words state against memory, when the switch is on. Memory is read on
    the basis the figure's clause names, else the card's ``basis``."""
    if not card_comparative_matches_memory():
        return []
    memory = _memory_by_basis(dossier)
    if not memory:
        return []
    found = []
    for text in texts:
        flat = (text or "").replace("**", "")
        for m in _AMOUNT_PERIOD.finditer(flat):
            metric = _metric_before(flat, m.start())
            period = canonical_period(re.sub(r"\s|'", "", m.group(2)).upper()) or m.group(2)
            clause = re.split(r";|\.\s", flat[:m.start()])[-1]
            word = _BASIS_WORD.findall(clause)
            on = word[-1].upper() if word else basis
            held = _held(memory.get((metric, period)), on) if metric else None
            if held is None and metric == "pat":
                held = _held(memory.get(("pat_owners", period)), on)
            if held is None:
                continue
            said = abs(float(m.group(1).replace(",", "")))
            if abs(said - abs(held)) > max(0.005, 0.02 * abs(held)):
                found.append(f"{metric} {period}: the card says ₹{said:g} Cr, memory (the exchange's file) ₹{abs(held):g} Cr")
    return list(dict.fromkeys(found))
