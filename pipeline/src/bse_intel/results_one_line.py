"""CARD_RESULTS_ONE_LINE: each row of the results block is one statement line (settings.card_results_one_line; off by
default, then nothing here runs). Live audit of 26 Oct 2026, class "two bases in the results block":

1. **Revenue.** Five Star's block set the quarter's total income (875.0) against comparatives that were revenue from
   operations (799.44, 828.98): +9.5% / +5.6% for a true +8% / +4%. A row keeps the line its current figure is on (revenue
   from operations, or total income); a comparative on the other line is taken from the same line when memory holds it,
   else left out with its change. The row is named for its line ("Total income").
2. **EBITDA.** Gravita's block: this quarter's EBITDA worked out from the tagged file (169.47, margin 24.37%) against
   comparatives the company stated (133.0, 192). A tagged current figure takes comparatives worked out the same way from the
   tagged parts (profit before tax, finance cost, depreciation, less other income and exceptional items), else none; a
   margin follows its EBITDA.
3. **Headline and key numbers.** A revenue or EBITDA figure that is not the block's (the CFO's spoken 1,153 against the
   statement's 1,131.87; the company's printed EBITDA beside ours) is labelled "company-reported" with the block's figure,
   and two EBITDA key numbers are each named. A figure that already names its basis is left alone.

Every change is returned as a note for the card's change log (`grounding.one_line`)."""

from __future__ import annotations

import re

from .settings import card_results_one_line

NOTES_KEY = "one_line"   # where the table keeps its notes until the card's change log takes them

_REVENUE_OPS = ("revenue", "revenue_from_operations", "net_sales")
_REVENUE_TOTAL = ("total_revenue", "total_income")
_NEAR = 0.005   # a stored figure within this share (and 0.011) of a row's value is the figure the row shows
_PARTS = ("pbt", "finance_cost", "depreciation", "other_income", "exceptional_items")
_STATED = re.compile(r"reported|calculated|computed|filing|presentation|company|statement|table|own definition|"
                     r"derived|tagged|excluding|adjusted|underlying", re.I)
_FIG = r"₹\s?(-?[\d,]+(?:\.\d+)?)\s*(?:cr|crore)\b"
_HEAD = re.compile(rf"\b(total income|revenue|EBITDA)\b[^₹]{{0,40}}{_FIG}", re.I)
_KEY_REVENUE = re.compile(r"(?:q[1-4]\s*(?:fy\d{2})?\s*)?(?:consolidated\s+|standalone\s+)?(?:total income|revenue(?: from operations)?)", re.I)
_KEY_EBITDA = re.compile(r"(?:operating )?EBITDA", re.I)


def _cr(value: float) -> str:
    return f"₹{value:,.2f}".rstrip("0").rstrip(".") + " Cr"


def _near(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= _NEAR * abs(b) + 0.011


def _entry(table: dict, names: tuple[str, ...], period: str | None, value: float | None) -> dict | None:
    """The memory entry a row's figure came from: the one whose value it is, else the first line held."""
    found = [table[(n, period)] for n in names if period and (n, period) in table]
    return next((e for e in found if _near(value, e.get("value"))), found[0] if found else None)


def _tagged(entry: dict | None) -> bool:
    """Whether the exchange's own file states this figure (a source labelled by file, or the seed's XBRL id)."""
    from .dossier import XBRL_SOURCE, _sources

    return any(str(src.get("news_id", "")).startswith(XBRL_SOURCE) or (src.get("lab") or {}).get("by") == "file"
               for src in _sources(entry or {}))


def _set_changes(row: dict, slot: str, now: float, base: float | None, bps: bool) -> None:
    label = "yoy" if slot == "prev_year" else "qoq"
    for suffix in ("pct", "bps", "turn"):
        row.pop(f"{label}_{suffix}", None)
    if base is None:
        row.pop(slot, None)
        return
    row[slot] = round(base, 2)
    if bps:
        row[f"{label}_bps"] = round((now - base) * 100)
    elif base > 0 and now >= 0:
        row[f"{label}_pct"] = round((now - base) / base * 100, 1)


def _revenue_row(out: dict, lines: list[dict], table: dict, periods: dict, period: str, notes: list[str]) -> None:
    row = out.get("revenue")
    if not isinstance(row, dict) or row.get("value") is None:
        return
    every = _REVENUE_OPS + _REVENUE_TOTAL
    cur = _entry(table, every, period, row["value"])
    if cur is None or cur["metric"] not in every:
        return
    total = cur["metric"] in _REVENUE_TOTAL
    names = _REVENUE_TOTAL if total else _REVENUE_OPS
    line = "total income" if total else "revenue from operations"
    for slot in ("prev_year", "prev_quarter"):
        p, shown = periods.get(slot), row.get(slot)
        if not p or shown is None:
            continue
        got = _entry(table, every, p, shown)
        if got is None or got["metric"] in names:
            continue
        same = next((table[(n, p)] for n in names if (n, p) in table and table[(n, p)].get("value") is not None), None)
        if same is not None:
            _set_changes(row, slot, row["value"], same["value"], False)
            notes.append(f"results revenue {slot}: {p} taken from {line} ({_cr(same['value'])}), not {got['metric']}")
        else:
            _set_changes(row, slot, row["value"], None, False)
            notes.append(f"results revenue {slot}: {p} is not on {line} in the tagged data, comparative and change left out")
    if total:
        for spec in lines:
            if spec.get("key") == "revenue":
                spec["label"] = "Total income"
                notes.append("results revenue row named for its line: total income")


def _worked_out(table: dict, period: str) -> float | None:
    """EBITDA from the tagged parts, as xbrl.py works it out: profit before tax + finance cost + depreciation - other
    income - exceptional items; None unless profit before tax, finance cost and depreciation are tagged."""
    parts = {}
    for name in _PARTS:
        entry = table.get((name, period))
        if entry is not None and entry.get("value") is not None and _tagged(entry):
            parts[name] = entry["value"]
    if not all(n in parts for n in ("pbt", "finance_cost", "depreciation")):
        return None
    return (parts["pbt"] + parts["finance_cost"] + parts["depreciation"]
            - parts.get("other_income", 0.0) - parts.get("exceptional_items", 0.0))


def _ebitda_rows(out: dict, table: dict, periods: dict, period: str, notes: list[str]) -> None:
    row, margin = out.get("ebitda"), out.get("ebitda_margin")
    if not isinstance(row, dict) or row.get("value") is None:
        return
    cur = _entry(table, ("ebitda", "operating_profit"), period, row["value"])
    if cur is None or not _tagged(cur):
        return
    for slot in ("prev_year", "prev_quarter"):
        p, shown = periods.get(slot), row.get(slot)
        if not p or shown is None:
            continue
        got = _entry(table, ("ebitda", "operating_profit"), p, shown)
        if got is None or _tagged(got):
            continue
        again = _worked_out(table, p)
        _set_changes(row, slot, row["value"], again, False)
        how = (f"worked out the same way it is {_cr(again)}" if again is not None
               else "no tagged parts for it, comparative and change left out")
        notes.append(f"results EBITDA {slot}: {p} {_cr(shown)} is the company's stated figure, this quarter's is worked out "
                     f"from the file; {how}")
        if isinstance(margin, dict) and "value" in margin:
            revenue = (out.get("revenue") or {}).get(slot)
            base = round(again / revenue * 100, 2) if again is not None and revenue else None
            _set_changes(margin, slot, margin["value"], base, True)
            notes.append(f"results EBITDA margin {slot}: follows its EBITDA")


def snapshot_rows(out: dict, lines: list[dict], table: dict, periods: dict, period: str) -> None:
    """The results table's rows on one line each (called by dossier.results_snapshot). Notes go under `NOTES_KEY`."""
    if not card_results_one_line():
        return
    notes: list[str] = []
    _revenue_row(out, lines, table, periods, period, notes)
    _ebitda_rows(out, table, periods, period, notes)
    if notes:
        out[NOTES_KEY] = notes


def _amount(text: str | None) -> float | None:
    found = re.search(r"-?\d[\d,]*(?:\.\d+)?", (text or "").replace("₹", ""))
    return float(found.group(0).replace(",", "")) if found else None


def _differs(shown: float, block: float, share: float) -> bool:
    return abs(shown - block) > share * abs(block)


def apply_card_json(card_json: dict) -> list[str]:
    """The checks on the stored card (a dict): lifts the table's notes, labels a headline or key number on another basis
    than the block's row. Returns what was changed."""
    results = card_json.get("results")
    if not card_results_one_line() or not isinstance(results, dict):
        return []
    notes = [str(n) for n in results.pop(NOTES_KEY, None) or []]
    rows = {key: (results.get(key) or {}).get("value") for key in ("revenue", "ebitda")}

    def tag(block: float) -> str:
        return f"company-reported; results table {_cr(block)}"

    keys = [k for k in card_json.get("key_numbers") or [] if isinstance(k, dict)]
    ebitda_keys = [k for k in keys if _KEY_EBITDA.fullmatch(str(k.get("label") or "").strip())]
    for key in keys:
        label = str(key.get("label") or "").strip()
        which = "revenue" if _KEY_REVENUE.fullmatch(label) else "ebitda" if _KEY_EBITDA.fullmatch(label) else None
        block, shown = (rows.get(which) if which else None), _amount(key.get("value"))
        if which is None or block is None or shown is None or _STATED.search(label):
            continue
        if _differs(shown, block, 0.03 if which == "ebitda" else 0.015):
            key["label"] = f"{label} ({tag(block)})"
            notes.append(f"key_numbers {label}: {_cr(shown)} is not the block's {which} ({_cr(block)}), labelled company-reported")
        elif which == "ebitda" and len(ebitda_keys) > 1:
            key["label"] = f"{label} (calculated from the statement)"
            notes.append(f"key_numbers {label}: two EBITDA figures on the card, this one named as the statement's")
    headline = card_json.get("headline")
    if isinstance(headline, str) and not _STATED.search(headline):
        for match in _HEAD.finditer(headline):
            which = "ebitda" if match.group(1).lower() == "ebitda" else "revenue"
            block, shown = rows.get(which), float(match.group(2).replace(",", ""))
            if block is not None and _differs(shown, block, 0.03 if which == "ebitda" else 0.015):
                card_json["headline"] = f"{headline.rstrip().rstrip('.')} ({tag(block)})"
                notes.append(f"headline: {match.group(1)} {_cr(shown)} is not the block's ({_cr(block)}), labelled company-reported")
                break
    return notes
