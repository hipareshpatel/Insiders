"""CARD_RESULTS_ONE_LINE: each row of the results block is one statement line (settings.card_results_one_line; off by
default, then nothing here runs). Live audit of 26 Oct 2026, class "two bases in the results block":

1. **Revenue.** Five Star's block set the quarter's total income (875.0) against comparatives that were revenue from
   operations (799.44, 828.98): +9.5% / +5.6% for a true +8% / +4%. A row keeps the line its current figure is on (revenue
   from operations, or total income); a comparative on the other line is taken from the same line when memory holds it,
   else left out with its change. The row is named for its line ("Total income").
2. **EBITDA.** Garware Hi-Tech's block: this quarter's EBITDA worked out from the tagged file (169.47, margin 24.37%) against
   comparatives the company stated (133.0, 192) where the file's own were 119.44 and 172.0. The kind of each figure is read
   from the source whose value the row shows; a tagged current figure takes the tagged source of the comparative's own entry
   (xbrl.py's figure, so its sign and exceptional-item rules stay xbrl's), else no comparative; a margin follows its EBITDA.
   Every replacement passes the table's own guards (`lookup`: restated column, basis, refused comparative).
3. **Headline and key numbers.** A revenue or EBITDA figure that is not the block's (the CFO's spoken 1,153 against the
   statement's 1,131.87; the company's printed EBITDA beside ours) is labelled "company-reported" with the block's figure,
   and two EBITDA key numbers are each named. A figure that already names its basis is left alone.

Every change is returned as a note for the card's change log (`grounding.one_line`)."""

from __future__ import annotations

import re

from .settings import card_results_one_line

NOTES_KEY = "one_line"   # where the table keeps its notes until the card's change log takes them

_REVENUE_OPS = ("revenue", "revenue_from_operations", "net_sales")
_REVENUE_TOTAL = ("total_income", "total_revenue")
_NEAR = 0.005   # a stored figure within this share (and 0.011) of a row's value is the figure the row shows
_FLOOR_CR = 1.0   # a headline or key number is on another basis only when it is also this far from the block's figure
_STATED = re.compile(r"reported|calculated|computed|filing|presentation|company|statement|table|own definition|"
                     r"derived|tagged|excluding|adjusted|underlying", re.I)
_FIG = r"₹\s?(-?[\d,]+(?:\.\d+)?)\s*(?:cr|crore)\b"
_HEAD_WORD = re.compile(r"\b(total income|revenue|EBITDA)\b", re.I)
_KEY_REVENUE = re.compile(r"(?:q[1-4]\s*(?:fy\d{2})?\s*)?(?:consolidated\s+|standalone\s+)?(total income|revenue(?: from operations)?)", re.I)
_KEY_EBITDA = re.compile(r"(?:operating )?EBITDA", re.I)


def _cr(value: float) -> str:
    return f"₹{value:,.2f}".rstrip("0").rstrip(".") + " Cr"


def _near(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= _NEAR * abs(b) + 0.011


def _tagged_values(entry: dict | None, basis: str | None = None) -> list[float]:
    """The values the exchange's own file states for this figure (a source with the seed's XBRL id, or labelled by file or
    as worked out from it), on the given basis."""
    from .dossier import XBRL_SOURCE, _sources

    return [src["value"] for src in _sources(entry or {}) if isinstance(src.get("value"), (int, float))
            and (str(src.get("news_id", "")).startswith(XBRL_SOURCE) or (src.get("lab") or {}).get("by") in ("file", "calc"))
            and (basis is None or src.get("basis") in (None, basis))]


def _basis(entry: dict | None) -> str | None:
    from .dossier import _entry_basis

    return _entry_basis(entry) if entry else None


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


def _is_total_income(table: dict, period: str, value: float) -> bool | None:
    """Whether the quarter's revenue figure is total income: it is a figure of the total-income line and not the file's
    revenue from operations (Five Star: the card's own reading, 875.0, stored as `revenue`, the file's revenue 858.48 and
    its total income 875.03). None when the figure is neither's."""
    total = [table[(n, period)] for n in _REVENUE_TOTAL if (n, period) in table]
    ops = [table[(n, period)] for n in _REVENUE_OPS if (n, period) in table]
    on_ops = any(_near(value, v) for e in ops for v in (_tagged_values(e) or [e.get("value")]))
    on_total = any(_near(value, v) for e in total for v in (_tagged_values(e) or [e.get("value")]))
    if on_total and not on_ops:
        return True
    if on_ops and not on_total:
        return False
    return False if on_ops else None


def _revenue_row(out: dict, lines: list[dict], table: dict, periods: dict, period: str, lookup, notes: list[str]) -> None:
    row = out.get("revenue")
    if not isinstance(row, dict) or row.get("value") is None:   # the row is data of the block even where its lens does not list it
        return
    total = _is_total_income(table, period, row["value"])
    if total is None:
        return
    names = _REVENUE_TOTAL if total else _REVENUE_OPS
    other = _REVENUE_OPS if total else _REVENUE_TOTAL
    line = "total income" if total else "revenue from operations"
    for slot in ("prev_year", "prev_quarter"):
        p, shown = periods.get(slot), row.get(slot)
        if not p or shown is None:
            continue
        mine = [table[(n, p)] for n in names if (n, p) in table]
        theirs = [table[(n, p)] for n in other if (n, p) in table]
        if any(_near(shown, e.get("value")) for e in mine) or not any(_near(shown, e.get("value")) for e in theirs):
            continue   # on this row's line already (or a figure of no line we know)
        same = lookup(names, p)   # through the table's own guards: restated column, basis, refused comparative
        if same is not None:
            _set_changes(row, slot, row["value"], same, False)
            notes.append(f"results revenue {slot}: {p} taken from {line} ({_cr(same)}), the one this quarter's figure is on")
        else:
            _set_changes(row, slot, row["value"], None, False)
            notes.append(f"results revenue {slot}: {p} is not on {line} in the tagged data, comparative and change left out")
    if total:
        for spec in lines:
            if spec.get("key") == "revenue":
                spec["label"] = "Total income"
                notes.append("results revenue row named for its line: total income")


def _ebitda_rows(out: dict, lines: list[dict], table: dict, periods: dict, period: str, lookup, notes: list[str]) -> None:
    """A tagged EBITDA (the file's, as xbrl.py works it out) takes comparatives of the same kind: the tagged source of
    the comparative's own entry (xbrl.py's figure for that quarter), else none. Memory's stored value of a comparative may
    be the company's stated one (Garware Hi-Tech: 133.0 stated, 119.44 from its file), so the kind is read from the
    source whose value the row shows."""
    row, margin = out.get("ebitda"), out.get("ebitda_margin")
    if not isinstance(row, dict) or row.get("value") is None:
        return
    names = ("ebitda", "operating_profit")
    cur = next((table[(n, period)] for n in names if (n, period) in table), None)
    basis = _basis(cur)
    cur_tagged = any(_near(row["value"], v) for v in _tagged_values(cur, basis))
    for slot in ("prev_year", "prev_quarter"):
        p, shown = periods.get(slot), row.get(slot)
        if not p or shown is None:
            continue
        got = next((table[(n, p)] for n in names if (n, p) in table), None)
        base_values = _tagged_values(got, basis)
        base_tagged = any(_near(shown, v) for v in base_values)
        if cur_tagged == base_tagged or (not cur_tagged and not base_values) or got is None:
            continue
        again = base_values[0] if cur_tagged and base_values and lookup(names, p) is not None else None
        _set_changes(row, slot, row["value"], again, False)
        how = (f"the file's figure for it, {_cr(again)}" if again is not None
               else "left out, the file has no figure for it on the same footing")
        notes.append(f"results EBITDA {slot}: {p} {_cr(shown)} is on another footing than this quarter's; {how}")
        if isinstance(margin, dict) and "value" in margin:
            base = None
            if again is not None:
                stated = _tagged_values(table.get(("ebitda_margin", p)), basis)
                revenue = _tagged_values(table.get(("revenue", p)), basis)
                base = stated[0] if stated else round(again / revenue[0] * 100, 2) if revenue and revenue[0] else None
            _set_changes(margin, slot, margin["value"], base, True)
            notes.append(f"results EBITDA margin {slot}: follows its EBITDA")


def snapshot_rows(out: dict, lines: list[dict], table: dict, periods: dict, period: str, lookup) -> None:
    """The results table's rows on one line each (called by dossier.results_snapshot, with its own guarded `lookup`).
    Notes go under `NOTES_KEY` until the card's change log takes them."""
    if not card_results_one_line():
        return
    notes: list[str] = []
    _revenue_row(out, lines, table, periods, period, lookup, notes)
    _ebitda_rows(out, lines, table, periods, period, lookup, notes)
    if notes:
        out[NOTES_KEY] = notes


def _amount(text: str | None) -> float | None:
    found = re.search(r"-?\d[\d,]*(?:\.\d+)?", (text or "").replace("₹", ""))
    return float(found.group(0).replace(",", "")) if found else None


def _differs(shown: float, block: float, share: float) -> bool:
    return abs(shown - block) > share * abs(block) and abs(shown - block) > _FLOOR_CR


def _headline_figure(text: str, end: int) -> float | None:
    """The ₹ crore figure a word in the headline states: the one after "to" or "at", else the last in its clause ("Revenue up
    ₹50 Cr to ₹700 Cr" states 700)."""
    clause = re.split(r";|, (?=[A-Za-z])| and ", text[end:end + 90])[0]
    found = list(re.finditer(_FIG, clause, re.I))
    if not found:
        return None
    pick = next((m for m in found if re.search(r"\b(?:to|at)\s*$", clause[:m.start()], re.I)), found[-1])
    return float(pick.group(1).replace(",", ""))


def apply_card_json(card_json: dict) -> list[str]:
    """The checks on the stored card (a dict): lifts the table's notes, labels a headline or key number on another basis
    than the block's row. Returns what was changed. Only a row the table shows is compared with, and a revenue figure only
    with a row of its own line (total income with total income)."""
    results = card_json.get("results")
    if not card_results_one_line() or not isinstance(results, dict):
        return []
    notes = [str(n) for n in results.pop(NOTES_KEY, None) or []]
    shown = {s.get("key"): s for s in results.get("lines") or [] if isinstance(s, dict)}
    rows = {}
    if "revenue" in shown and (results.get("revenue") or {}).get("value") is not None:
        rows["revenue"] = (results["revenue"]["value"], "total income" if "total income" in str(shown["revenue"].get("label", "")).lower() else "revenue")
    if "ebitda" in shown and (results.get("ebitda") or {}).get("value") is not None:
        rows["ebitda"] = (results["ebitda"]["value"], "ebitda")

    def which_of(word: str) -> str | None:
        w = word.lower()
        kind = "ebitda" if w.endswith("ebitda") else "total income" if w.startswith("total income") else "revenue"
        key = "ebitda" if kind == "ebitda" else "revenue"
        return key if key in rows and rows[key][1] == kind else None   # a total-income figure is not compared with revenue

    def tag(block: float) -> str:
        return f"company-reported; results table {_cr(block)}"

    keys = [k for k in card_json.get("key_numbers") or [] if isinstance(k, dict)]
    ebitda_keys = [k for k in keys if _KEY_EBITDA.fullmatch(str(k.get("label") or "").strip())]
    for key in keys:
        label = str(key.get("label") or "").strip()
        word = (_KEY_REVENUE.fullmatch(label) or _KEY_EBITDA.fullmatch(label))
        which = which_of(word.group(0) if _KEY_EBITDA.fullmatch(label) else word.group(1)) if word else None
        figure = _amount(key.get("value"))
        if which is None or figure is None or _STATED.search(label):
            continue
        block = rows[which][0]
        if _differs(figure, block, 0.03 if which == "ebitda" else 0.015):
            key["label"] = f"{label} ({tag(block)})"
            notes.append(f"key_numbers {label}: {_cr(figure)} is not the block's {which} ({_cr(block)}), labelled company-reported")
        elif which == "ebitda" and len(ebitda_keys) > 1:
            key["label"] = f"{label} (calculated from the statement)"
            notes.append(f"key_numbers {label}: two EBITDA figures on the card, this one named as the statement's")
    headline = card_json.get("headline")
    if isinstance(headline, str) and not _STATED.search(headline):
        for match in _HEAD_WORD.finditer(headline):
            which, figure = which_of(match.group(1)), _headline_figure(headline, match.end())
            if which is None or figure is None:
                continue
            block = rows[which][0]
            if _differs(figure, block, 0.03 if which == "ebitda" else 0.015):
                card_json["headline"] = f"{headline.rstrip().rstrip('.')} ({tag(block)})"
                notes.append(f"headline: {match.group(1)} {_cr(figure)} is not the block's ({_cr(block)}), labelled company-reported")
                break
    return notes
