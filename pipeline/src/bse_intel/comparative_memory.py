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
# an adjusted or non-GAAP figure is no reported line (BLUESTONE's adjusted EBITDA 147.4 against 125.74: blind read of 41345924894)
_ADJUSTED = re.compile(r"\b(?:adjusted|underlying|normali[sz]ed|non[- ]?gaap|core|recurring|pre[- ]?ind[- ]?as|excluding|"
                       r"before\s+exceptional|ex[- ]exceptional)\b", re.I)


def _file_figures(dossier: dict | None) -> dict[tuple[str, str, str], float]:
    """{(metric, period, basis): value} of memory's figures the exchange's own results file gave (a source labelled ``file``, on a
    named basis); a calculated or a model-read figure, or one with no basis, is none (blind read of 41345924894: IOB's 1,962.67
    and STARHEALTH's 111.33 were not in their filings)."""
    from .dossier import _STORED_SCALE
    from .watch_code import _sources_of, _src_basis

    out: dict[tuple[str, str, str], float] = {}
    for m in (dossier or {}).get("financial_metrics") or []:
        if not isinstance(m, dict) or not m.get("period") or not m.get("metric"):
            continue
        for src in _sources_of(m):
            lab = src.get("lab") if isinstance(src.get("lab"), dict) else {}
            basis = _src_basis(src, m)
            unit = str(src.get("unit") or m.get("unit") or "INR_CR").upper()
            if lab.get("by") != "file" or not basis or not isinstance(src.get("value"), (int, float)) or unit not in _STORED_SCALE:
                continue   # a rate or per-share figure is no crore amount to set a card's "₹X Cr" against
            # in crore, whatever unit the source was stored in (lead's review of #369: a lakh source of 500 is ₹5 Cr)
            out.setdefault((m["metric"], m["period"], basis.upper()), float(src["value"]) * _STORED_SCALE[unit] / 1e7)
    return out


def _decimals(raw: str) -> int:
    return len(raw.split(".")[1]) if "." in raw else 0


def contradictions(texts: list[str], dossier: dict | None, basis: str | None = None) -> list[str]:
    """Each "metric period: card X vs memory Y" the card's words state against memory, when the switch is on (blind read of release
    check 41345924894, 9 of 20 holds wrong): only on the card's own basis (the figure's clause names it, else the card's
    ``basis``; none known, no hold), only against a figure the exchange's own file gave for that quarter and basis, at the card's
    printed precision ("₹3 Cr" is 3.11), and never for an adjusted figure."""
    if not card_comparative_matches_memory():
        return []
    memory = _file_figures(dossier)
    if not memory:
        return []
    found = []
    for text in texts:
        flat = (text or "").replace("**", "")
        for m in _AMOUNT_PERIOD.finditer(flat):
            metric = _metric_before(flat, m.start())
            period = canonical_period(re.sub(r"\s|'", "", m.group(2)).upper()) or m.group(2)
            clause = re.split(r";|\.\s", flat[:m.start()])[-1]
            if not metric or _ADJUSTED.search(clause):
                continue
            word = _BASIS_WORD.findall(clause)
            on = (word[-1] if word else basis or "").upper()
            if not on:
                continue
            held = memory.get((metric, period, on))
            if held is None and metric == "pat":
                held = memory.get(("pat_owners", period, on))
            if held is None:
                continue
            raw = m.group(1).replace(",", "")
            said = abs(float(raw))
            if abs(said - abs(held)) > max(0.005, 0.5 * 10 ** -_decimals(raw), 0.02 * abs(held)):
                found.append(f"{metric} {period}: the card says ₹{said:g} Cr, memory (the exchange's file) ₹{abs(held):g} Cr")
    return list(dict.fromkeys(found))
