"""CARD_RATIO_COLUMNS: a ratio row read by position against an amount row that has change columns (settings.card_ratio_columns;
off by default, then nothing here runs). Blind audit 1 Nov 2026, VIMTALABS nse-106836191 (a deck): the amount row reads
"EBIDTA 408 411 -0.8% 369 10.5% 819 723 13.2%" (Q2FY27, Q1FY27, QoQ, Q2FY26, YoY, H1FY27, H1FY26, YoY) and the margin row
"EBIDTA (%) 35.5% 36.4% 35.3% 36.0% 35.5%", which has no change columns. The card took 35.3% (Q2FY26) for Q1FY27 and wrote "margin
expansion" against a quarter whose margin was 36.4%.

The ratio row's cells are laid on the amount row's value cells (the cells that are no change). The amount row's own arithmetic
reads its header: a value cell followed by a change cell is a comparison column when that change is the current value against it
(within half a point); the first such column is the previous quarter, the second the year-ago quarter (the results layout).

A card line comparing the ratio with the previous quarter or the year-ago quarter is checked against that column. When its figure
is the ratio of the other comparison column (the shift), a structured "previous" value is corrected to the right cell, and a line
of words is dropped: its claim (higher, expansion) was drawn from the wrong figure, so the figure alone cannot be put right. When
the amount row's columns cannot be read, a comparison resting on a shifted-looking ratio row is dropped. Every change is
returned as a note."""

from __future__ import annotations

import re

from .periods import prior_quarter_period, prior_year_period
from .settings import card_ratio_columns

_CELL = re.compile(r"\(?-?[\d,]+(?:\.\d+)?%?\)?")
_LABEL_WORD = re.compile(r"[A-Za-z]{3,}")
_LISTS = ("what_happened", "why_it_matters", "notable_changes")
_PREV_WORDS = re.compile(r"\bQoQ\b|sequential|quarter[- ]on[- ]quarter|previous quarter|preceding quarter|last quarter", re.I)
_YOY_WORDS = re.compile(r"\bYoY\b|year[- ]on[- ]year|year[- ]ago|a year earlier|same quarter last year", re.I)
_PERIOD = re.compile(r"\b(?:Q[1-4]\s?FY\s?'?\d{2,4})\b", re.I)


def _cells(row: str) -> tuple[str, list[str]]:
    """(the row's label, its number cells as printed)."""
    m = re.search(r"\(?-?\d", row)
    label = row[:m.start()] if m else row
    return label.strip(), _CELL.findall(row[m.start():]) if m else []


def _num(cell: str) -> float | None:
    raw = cell.replace(",", "").replace("%", "")
    negative = raw.startswith("(") and raw.endswith(")") or raw.startswith("-")
    try:
        value = float(raw.strip("()-"))
    except ValueError:
        return None
    return -value if negative else value


def _stem(label: str) -> str:
    words = [w.lower() for w in _LABEL_WORD.findall(label)]
    return words[0].replace("ebidta", "ebitda") if words else ""


def comparison_columns(amount_row: str) -> tuple[int, int] | None:
    """(previous-quarter, year-ago) positions among the amount row's value cells, read from its own change cells; None when
    the row has no two checked change columns."""
    _label, cells = _cells(amount_row)
    values: list[float] = []
    comparisons: list[int] = []
    for i, cell in enumerate(cells):
        if cell.endswith("%"):
            continue
        value = _num(cell)
        if value is None:
            return None
        values.append(value)
        nxt = cells[i + 1] if i + 1 < len(cells) else ""
        if nxt.endswith("%") and len(values) > 1 and values[-1]:
            change = _num(nxt)
            if change is not None and abs((values[0] / values[-1] - 1) * 100 - change) <= 0.5:
                comparisons.append(len(values) - 1)
    return (comparisons[0], comparisons[1]) if len(comparisons) >= 2 else None


def _rows(card_json: dict) -> list[str]:
    rows = []
    for name in (*_LISTS, "key_numbers"):
        for item in card_json.get(name) or []:
            if isinstance(item, dict) and isinstance(item.get("quote"), str):
                rows += [r for r in re.split(r"\s*\|\s*|\n", item["quote"]) if r.strip()]
    return rows


def _amount_row_for(ratio_row: str, rows: list[str]) -> str | None:
    """The amount row of the same line (its label's first word, EBIDTA / EBITDA alike) with change cells."""
    label, ratio_cells = _cells(ratio_row)
    stem = _stem(label)
    for row in rows:
        if row is ratio_row:
            continue
        other_label, cells = _cells(row)
        values = [c for c in cells if not c.endswith("%")]
        if stem and _stem(other_label) == stem and len(values) == len(ratio_cells) and len(values) < len(cells):
            return row
    return None


def _claim(text: str, card_period: str | None) -> str | None:
    """'prev' or 'yoy': which comparison a line of words or a structured field makes."""
    prev_label = prior_quarter_period(card_period or "") if card_period else None
    year_label = prior_year_period(card_period or "") if card_period else None
    named = {re.sub(r"[\s']", "", m.group(0)).upper() for m in _PERIOD.finditer(text or "")}
    if prev_label and prev_label in named or _PREV_WORDS.search(text or ""):
        return "prev"
    if year_label and year_label in named or _YOY_WORDS.search(text or ""):
        return "yoy"
    return None


def _card_period(card_json: dict) -> str | None:
    period = (card_json.get("results") or {}).get("period") if isinstance(card_json.get("results"), dict) else None
    if isinstance(period, str):
        return period
    m = _PERIOD.search(str(card_json.get("headline") or "") + " " + str(card_json.get("timeline_entry") or ""))
    return re.sub(r"[\s']", "", m.group(0)).upper() if m else None


def _pct_values(text: str) -> list[float]:
    return [float(m.group(1)) for m in re.finditer(r"(-?\d+(?:\.\d+)?)\s?%", text or "")]


def apply_card_json(card_json: dict) -> list[str]:
    """Correct or drop a ratio comparison read from a shifted column (VIMTALABS); the notes of what was changed."""
    if not card_ratio_columns():
        return []
    period = _card_period(card_json)
    rows = _rows(card_json)
    notes: list[str] = []
    for name in _LISTS:
        items = card_json.get(name)
        if not isinstance(items, list):
            continue
        kept = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("quote"), str):
                kept.append(item)
                continue
            ratio_row = next((r for r in re.split(r"\s*\|\s*|\n", item["quote"]) if r.strip()), "")
            label, ratio_cells = _cells(ratio_row)
            if len(ratio_cells) < 3 or not all(c.endswith("%") for c in ratio_cells):
                kept.append(item)
                continue
            amount_row = _amount_row_for(ratio_row, rows)
            if amount_row is None:
                kept.append(item)
                continue
            ratios = [_num(c) for c in ratio_cells]
            columns = comparison_columns(amount_row)
            words = " ".join(str(item.get(k) or "") for k in ("text", "previous", "why"))
            claim = _claim(words, period)
            stated = [v for v in _pct_values(str(item.get("previous") or "") or str(item.get("text") or "")) if v != ratios[0]]
            if claim is None or not stated:
                kept.append(item)
                continue
            if columns is None:
                # the amount row's columns cannot be read: a comparison resting on a ratio row that lacks its change cells
                notes.append(f"{name}: dropped '{(item.get('text') or item.get('previous') or '')[:80]}', its ratio row cannot be "
                             f"aligned with '{amount_row[:40]}' (CARD_RATIO_COLUMNS)")
                continue
            right = ratios[columns[0] if claim == "prev" else columns[1]]
            other = ratios[columns[1] if claim == "prev" else columns[0]]
            if any(abs(v - right) <= 0.05 for v in stated) or not any(abs(v - other) <= 0.05 for v in stated):
                kept.append(item)   # the right column, or no sign of the shift
                continue
            which = "previous quarter" if claim == "prev" else "year-ago quarter"
            if item.get("previous") and not item.get("text"):
                fixed = re.sub(rf"{re.escape(f'{other:g}')}%", f"{right:g}%", str(item["previous"]), count=1)
                notes.append(f"{name}: {which} {item['previous']} corrected to {fixed}, the {label} row read against "
                             f"'{amount_row[:40]}' (CARD_RATIO_COLUMNS)")
                item = {**item, "previous": fixed}
                kept.append(item)
                continue
            notes.append(f"{name}: dropped '{str(item.get('text'))[:80]}', its {which} figure {other:g}% is the other column's; "
                         f"the {which} is {right:g}% (CARD_RATIO_COLUMNS)")
        card_json[name] = kept
    return notes
