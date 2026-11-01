"""CARD_ONE_BASIS: one figure, one basis, on one card (settings.card_one_basis; off by default, then nothing here runs).

The class "two bases of one figure" (live audit of 26 Oct 2026: Shoppers Stop, L&T Technology Services, Aurum, TMCV,
Lumax). A card must never set a figure of one basis beside a figure of another without saying so:

1. **Total against continuing profit.** A results file that holds a discontinued operation prints a total profit (with the
   sale gain) and a continuing one. A profit figure, or a change on it, whose own quarter or comparison base holds a material
   discontinued part is labelled with that part (the figure is the file's, its basis is what the card left out). An EPS change
   across such a quarter is taken out: the file's EPS is on continuing operations, the comparative's may not be.
2. **Adjusted against reported.** A line whose own quote carries the company's adjusted basis ("non-GAAP", "pre-Ind AS 116")
   while the line's words do not is labelled with that basis.
3. **Standalone against consolidated.** A card's results table is dropped when its basis is not the basis the card states.
4. **A presentation's own EBITDA** set beside the results table's: the call's key number is labelled with its own definition
   and the table's figure, when the two differ by more than a few percent.

Labels are added where the basis is known; a figure whose basis cannot be told (an EPS change) or a table that is on the other
basis is removed. Every edit is returned as a note, as the other post-checks do."""

from __future__ import annotations

import re

from .grounding import _tokens
from .periods import prior_quarter_period, prior_year_period
from .settings import card_one_basis, discontinued_needs_figure

_TOLERANCE = 0.02   # as metrics._DISCONTINUED_TOLERANCE: the share of the profit a discontinued part must exceed
_MIN_CR = 1.0
_PROFIT = ("pat", "pat_owners")
_BASIS_WORDS = re.compile(r"\b(?:continuing|discontinued)\b", re.I)
_ADJUSTED = re.compile(r"non[- ]?GAAP|pre[- ]?Ind[- ]?AS[- ]?116|ex[- ]?Ind[- ]?AS[- ]?116|\bpro[- ]?forma\b|\badjusted\b|"
                       r"\bunderlying\b|\bnormali[sz]ed\b|before exceptional", re.I)
_REPORTED = re.compile(r"\bGAAP\b|\breported\b|\bnon-?GAAP\b|\bpre-?Ind\b|\badjusted\b|\bunderlying\b|\bnormali[sz]ed\b|"
                       r"\bpro[- ]?forma\b|before exceptional|\bexcluding\b|\bexcl\.", re.I)
_OWN_DEFINITION = re.compile(r"presentation|company'?s? (?:own )?definition|as defined|defined", re.I)


def _cr(value: float) -> str:
    return f"₹{abs(value):,.2f}".rstrip("0").rstrip(".") + " Cr"


def values(history, tagged=None) -> dict[tuple[str, str], float]:
    """(metric, period) -> value from memory's rows and, over them, the file's own."""
    found: dict[tuple[str, str], float] = {}
    for row in history or []:
        if isinstance(row, dict) and row.get("period") and isinstance(row.get("value"), (int, float)):
            found[(row["metric"], row["period"])] = row["value"]
    for m in getattr(tagged, "metrics", None) or []:
        if m.period and m.value is not None:
            found[(m.metric, m.period)] = m.value
    return found


def discontinued_part(found: dict[tuple[str, str], float], period: str | None) -> float | None:
    """The part of a period's total profit that is not from continuing operations, when it is material."""
    if not period:
        return None
    total, continuing = found.get(("pat", period)), found.get(("pat_continuing", period))
    if discontinued_needs_figure():
        # the period's own discontinued figure, never the gap: the taxonomy's continuing profit is before the associates' share,
        # so the gap is that share where no operation was discontinued (GABRIEL, SARDAEN, POLICYBZR; audit of 1 Nov 2026)
        part = found.get(("pat_discontinued", period))
        if total is None or part is None or abs(part) <= max(_MIN_CR, _TOLERANCE * abs(total)):
            return None
        return part
    if total is None or continuing is None or abs(total - continuing) <= max(_MIN_CR, _TOLERANCE * abs(total)):
        return None
    return total - continuing


def _has_figure(text: str, amounts: list[float]) -> bool:
    for value, decimals, _pos, kind, _raw in _tokens(text.replace("**", "")):
        if kind in ("plain", "qty") and any(round(abs(a), decimals) == round(value, decimals) for a in amounts):
            return True
    return False


def _has_change(text: str, pct: float) -> bool:
    return any(kind == "pct" and round(value, 1) == round(abs(pct), 1) for value, _d, _p, kind, _r in _tokens(text.replace("**", "")))


def _profit_labels(period: str, found: dict[tuple[str, str], float]):
    """(amounts that are total profit, {change % -> note}, the note for the quarter's own total) for a period."""
    own = discontinued_part(found, period)
    amounts = [found[(m, period)] for m in _PROFIT if (m, period) in found] if own is not None else []
    notes: dict[float, str] = {}
    for base_period in (prior_quarter_period(period), prior_year_period(period)):
        base_part = discontinued_part(found, base_period)
        if base_part is None and own is None:
            continue
        for metric in _PROFIT:
            now, base = found.get((metric, period)), found.get((metric, base_period or ""))
            if now is None or not base:
                continue
            what = (f"{base_period} includes {_cr(base_part)} from discontinued operations" if base_part is not None
                    else f"{period} includes {_cr(own)} from discontinued operations")
            notes[round((now - base) / abs(base) * 100, 1)] = what
    continuing = found.get(("pat", period), 0.0) - own if own is not None and discontinued_needs_figure() \
        else found.get(("pat_continuing", period), 0.0)
    own_note = (f"includes {_cr(own)} from discontinued operations; continuing operations "
                f"{_cr(continuing)}" if own is not None else None)
    return amounts, notes, own_note


def _append(text: str | None, label: str) -> str | None:
    if not text or label in text:
        return text
    return text.rstrip().rstrip(".") + f" ({label})." if text.rstrip().endswith(".") else f"{text.rstrip()} ({label})"


def apply(out, tagged, history, event_type: str | None = None) -> list[str]:
    """The text checks, on a card's words (pydantic). Returns what was changed."""
    card = getattr(out, "card", None)
    if card is None or not card_one_basis():
        return []
    notes: list[str] = []
    found = values(history, tagged)
    period = getattr(tagged, "period", None)

    # 1. total against continuing profit (a results card with its file)
    if period and any(discontinued_part(found, p) is not None for p in (period, prior_quarter_period(period), prior_year_period(period))):
        amounts, changes, own_note = _profit_labels(period, found)

        def label_for(text: str) -> str | None:
            if _BASIS_WORDS.search(text):
                return None
            if amounts and _has_figure(text, amounts) and own_note:
                return own_note
            return next((note for pct, note in changes.items() if _has_change(text, pct)), None)

        def fix(text: str | None, where: str) -> str | None:
            label = label_for(text or "") if text else None
            if label:
                notes.append(f"{where}: profit on two bases, labelled: {label}")
            return _append(text, label) if label else text

        card.headline = fix(card.headline, "headline") or card.headline
        card.takeaway = fix(card.takeaway, "takeaway") or card.takeaway
        for fact in card.what_happened:
            fact.text = fix(fact.text, "what_happened") or fact.text
        out.timeline_entry = fix(out.timeline_entry, "timeline") or out.timeline_entry
        for key in card.key_numbers:
            label = label_for(f"{key.value} {key.change or ''}")
            if label and not _BASIS_WORDS.search(key.label):
                notes.append(f"key_numbers {key.label}: profit on two bases, labelled: {label}")
                key.label = f"{key.label} ({label})"
        # an EPS change across a discontinued operation: the file's EPS is on continuing operations, a comparative's may be
        # the total (L&T Technology Services: 35.78 continuing against a prior-year 31.02 total)
        for key in card.key_numbers:
            if re.search(r"\bEPS\b|per share", key.label, re.I) and key.change and re.search(r"\d\s*%", key.change):
                notes.append(f"key_numbers {key.label}: change removed, its quarter or base holds a discontinued operation")
                key.change = None

    # 2. adjusted against reported: the line's quote carries the company's adjusted basis, its words do not
    def adjusted(text: str | None, quote: str | None, where: str) -> str | None:
        marker = _ADJUSTED.search(quote or "")
        if not text or not marker or _REPORTED.search(text):
            return text
        shared = {round(v, d) for v, d, _p, k, _r in _tokens(text.replace("**", "")) if k in ("pct", "plain", "qty")}
        if not shared & {round(v, d) for v, d, _p, k, _r in _tokens((quote or "").replace("**", "")) if k in ("pct", "plain", "qty")}:
            return text
        notes.append(f'{where}: the quote states the company\'s own basis ("{marker.group(0)}"), labelled')
        return _append(text, f"{marker.group(0)} basis, as the company states it")

    marked: list[str] = []
    marker_words: list[str] = []
    for fact in card.what_happened:
        new = adjusted(fact.text, fact.quote, "what_happened")
        if new != fact.text:
            marked.append(fact.text)
            marker_words.append(_ADJUSTED.search(fact.quote or "").group(0))
            fact.text = new
    for item in card.why_it_matters:
        item.text = adjusted(item.text, item.quote, "why_it_matters") or item.text
    for key in card.key_numbers:
        new = adjusted(f"{key.label}: {key.value}", key.quote, f"key_numbers {key.label}")
        if new and new != f"{key.label}: {key.value}":
            key.label = f"{key.label} ({_ADJUSTED.search(key.quote or '').group(0)} basis)"
    # the headline and takeaway state the same figures as a labelled line: they carry the label too
    if marked:
        figures = {round(v, d) for line in marked for v, d, _p, k, _r in _tokens(line.replace("**", "")) if k in ("pct", "plain", "qty")}
        for attr in ("headline", "takeaway"):
            text = getattr(card, attr, None)
            if text and not _REPORTED.search(text) and figures & {round(v, d) for v, d, _p, k, _r in _tokens(text.replace("**", ""))
                                                                  if k in ("pct", "plain", "qty")}:
                setattr(card, attr, _append(text, f"{marker_words[0]} basis, as the company states it"))
                notes.append(f"{attr}: states a figure of the company's adjusted basis, labelled")
    return notes


def _snapshot_basis(snapshot: dict, dossier: dict) -> str | None:
    """The basis memory holds the table's revenue on (its own, else as the dossier chose among its sources)."""
    from .dossier import _entry_basis

    for row in (dossier or {}).get("financial_metrics") or []:
        if row.get("metric") == "revenue" and row.get("period") == snapshot.get("period"):
            return _entry_basis(row)
    return None


def _first_number(text: str | None) -> float | None:
    found = re.search(r"-?\d[\d,]*(?:\.\d+)?", (text or "").replace("₹", ""))
    return float(found.group(0).replace(",", "")) if found else None


def apply_card_json(card_json: dict, dossier: dict | None) -> list[str]:
    """The checks that need the results table, on the stored card (a dict). Returns what was changed."""
    notes: list[str] = []
    results = card_json.get("results")
    if not card_one_basis() or not isinstance(results, dict):
        return notes
    # 3. the table is on the card's stated basis or it is not shown
    stated, table = card_json.get("basis"), _snapshot_basis(results, dossier or {})
    if stated in ("CONSOLIDATED", "STANDALONE") and table in ("CONSOLIDATED", "STANDALONE") and stated != table:
        notes.append(f"results table removed: it is {table.lower()}, the card states {stated.lower()} figures")
        card_json["results"] = None
        return notes
    # the table's PAT line says what its profit holds
    found = values((dossier or {}).get("financial_metrics"))
    period = results.get("period")
    parts = [(p, discontinued_part(found, p)) for p in (period, prior_quarter_period(period or ""), prior_year_period(period or ""))]
    held = [(p, d) for p, d in parts if p and d is not None]
    spec = next((s for s in results.get("lines") or [] if s.get("key") == "pat"), None)
    if spec is not None and held and "note" not in spec:
        spec["note"] = "; ".join(f"{p} includes {_cr(d)} from discontinued operations" for p, d in held)
        notes.append(f"results table PAT line: {spec['note']}")
    # 4. a presentation's own EBITDA beside the table's
    if card_json.get("event_type") == "CONCALL_PRESENTATION":
        for key in card_json.get("key_numbers") or []:
            label = str(key.get("label") or "")
            if not re.fullmatch(r"(?:operating )?EBITDA(?: margin)?", label.strip(), re.I) or _OWN_DEFINITION.search(label):
                continue
            margin = "margin" in label.lower()
            row = results.get("ebitda_margin" if margin else "ebitda") or {}
            shown, mine = _first_number(key.get("value")), row.get("value")
            if shown is None or mine is None:
                continue
            if (abs(shown - mine) > 0.5) if margin else (abs(shown - mine) > 0.03 * abs(mine)):
                key["label"] = (f"{label} (presentation's own definition; results table "
                                f"{f'{mine:g}%' if margin else _cr(mine)})")
                notes.append(f"key_numbers {label}: differs from the results table ({mine}), labelled")
    return notes
