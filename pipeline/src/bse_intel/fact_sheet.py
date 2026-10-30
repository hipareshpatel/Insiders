"""CARD_FACT_SHEET (default off; owner, 30 Oct 2026, TODO 131 and 134): a results card whose RESULTS figures come from memory's
statements, not from the AI.

Memory holds each quarter's statements by screener's rules, built from the exchange's own file (``statements.py``, entries labelled
``lab.by == "file"``). For a corporate filer's results filing the fact sheet is that quarter's revenue (screener's "Sales"),
operating profit (EBITDA as screener defines it, and its margin), profit before tax (with the associates' share) and net profit, beside
the same quarter a year ago and the previous quarter, with the YoY and QoQ changes worked out here, never read from a model. EPS is not
in it (owner rule 26 Oct 2026: no EPS on cards). The basis is consolidated when memory has the quarter on it, else standalone.

With the switch on and a sheet:
- the results table's revenue, EBITDA, margin, PBT and PAT rows are the sheet's (``apply_to_results``);
- pass 2 is given the sheet as a block, "RESULTS FIGURES (from the exchange file; use only these for results lines)" (``block``);
- a revenue / EBITDA / PBT / profit amount, or a YoY / QoQ change of one, that the model writes about the quarter and that disagrees with
  the sheet beyond rounding is taken out of the card text (``removed``; the same shape as ``standalone_figures_removed``: a sentence is
  cut, a point or key number hidden, the card not held).
With no sheet (the file is late, a bank or insurer, a quarter memory lacks) nothing here runs and the card is what it was.
Orders of book, guidance, capex and segment figures are not touched: a sentence is judged only when it names one results line and no
other period, segment or outlook."""

from __future__ import annotations

import logging
import math
import re

from . import screener_view as sv
from . import statements, xbrl_facts
from .metrics import CONSOLIDATED, STANDALONE
from .periods import prior_quarter_period, prior_year_period

log = logging.getLogger(__name__)

# (line, the screener row it is, its label on the card); EBITDA is screener's Operating Profit
LINES = (("revenue", "Sales", "Revenue"), ("ebitda", "Operating Profit", "EBITDA"),
         ("pbt", "Profit before tax", "PBT"), ("pat", "Net Profit", "PAT"))
OWNERS = "Net Profit (owners)"      # the profit to shareholders, also accepted for the PAT line in the text check
MARGIN = "OPM %"
_TURN_LINES = {"ebitda", "pbt", "pat"}


def quarter_entries(dossier: dict, period: str, basis: str) -> dict | None:
    """The file-labelled corporate quarters-table entry of a period and basis, or None."""
    for e in dossier.get(statements.KEY, []) or []:
        if (isinstance(e, dict) and e.get("table") == "quarters" and e.get("period") == period and e.get("basis") == basis
                and e.get("family") == sv.CORPORATE and (e.get("lab") or {}).get("by") == "file"):
            return e
    return None


def _change(now: float | None, base: float | None, key: str) -> dict:
    """YoY / QoQ of one line as results_snapshot gives it: a per cent, or a named turn across a loss (never a per cent across one)."""
    if now is None or base is None or not (math.isfinite(now) and math.isfinite(base)):
        return {}
    if base < 0 or now < 0:
        if key not in _TURN_LINES:
            return {}
        return {"turn": ("LOSS_TO_PROFIT" if now >= 0 else "PROFIT_TO_LOSS" if base >= 0
                         else "LOSS_NARROWED" if now > base else "LOSS_WIDENED")}
    return {"pct": round((now - base) / abs(base) * 100, 1)} if base else {}


def fact_sheet(dossier: dict, period: str | None, basis: str | None = None) -> dict | None:
    """The quarter's fact sheet from ``dossier["statements"]``, or None when memory lacks the quarter (the exchange file is late,
    or it is not a corporate filer's). ``basis`` None: consolidated when memory has the quarter on it, else standalone."""
    if not period or not period.startswith("Q"):
        return None
    prior = {"prev_year": prior_year_period(period), "prev_quarter": prior_quarter_period(period)}
    for b in ((basis,) if basis else (CONSOLIDATED, STANDALONE)):
        now = quarter_entries(dossier, period, b)
        if now is None:
            continue
        before = {slot: quarter_entries(dossier, p, b) if p else None for slot, p in prior.items()}
        sheet: dict = {"period": period, "basis": b, "unit": "₹ crore", "prev_year_period": prior["prev_year"],
                       "prev_quarter_period": prior["prev_quarter"], "source_news_id": now.get("source_news_id"), "lines": {}}
        for key, row, label in LINES:
            value = (now.get("rows") or {}).get(row)
            if value is None:
                continue
            line: dict = {"label": label, "value": round(value, 2)}
            for slot, tag in (("prev_year", "yoy"), ("prev_quarter", "qoq")):
                base = ((before[slot] or {}).get("rows") or {}).get(row)
                if base is None:
                    continue
                line[slot] = round(base, 2)
                change = _change(value, base, key)
                if "pct" in change:
                    line[f"{tag}_pct"] = change["pct"]
                elif "turn" in change:
                    line[f"{tag}_turn"] = change["turn"]
            if key == "pat" and (now.get("rows") or {}).get(OWNERS) is not None:
                line["owners"] = round(now["rows"][OWNERS], 2)
            sheet["lines"][key] = line
        margin = (now.get("rows") or {}).get(MARGIN)
        if margin is not None:
            line = {"label": "EBITDA margin", "value": round(margin, 2)}
            for slot, tag in (("prev_year", "yoy"), ("prev_quarter", "qoq")):
                base = ((before[slot] or {}).get("rows") or {}).get(MARGIN)
                if base is not None:
                    line[slot] = round(base, 2)
                    line[f"{tag}_bps"] = round((margin - base) * 100)
            sheet["lines"]["ebitda_margin"] = line
        if "revenue" in sheet["lines"] and "pat" in sheet["lines"]:
            return sheet
    return None


def with_file(dossier: dict, data: bytes, scrip: str, url: str, news_id: str, as_of: str, at: str):
    """(statements-only dossier, period, basis): memory's statements with this filing's own file put in, as it will be when the card
    is merged (``statements.remember``, the same rows), but read here before pass 2. Nothing is written anywhere (the facts are
    not saved to R2: that is ``statements.from_file``'s step, at the memory write). (None, None, None) when the file has no quarter."""
    doc = xbrl_facts.parse_facts(data, scrip, url)
    if doc is None or not doc.get("period"):
        return None, None, None
    held = {statements.KEY: [dict(e) for e in dossier.get(statements.KEY, []) if isinstance(e, dict)]}
    statements.remember(held, doc, news_id, as_of, at)
    return held, doc["period"], doc.get("basis")


def for_filing(dossier: dict, raw: bytes | None, scrip: str, url: str, news_id: str, as_of: str, at: str) -> dict | None:
    """The sheet of a results filing from its own file; None on any failure (the card is then made as without the switch)."""
    if not raw:
        return None
    try:
        held, period, basis = with_file(dossier, raw, scrip, url, news_id, as_of, at)
        return fact_sheet(held, period, basis) if held is not None else None
    except Exception as exc:  # noqa: BLE001 - an addition: a failure is logged, the card is made as before
        log.warning("fact sheet of %s not built: %s", news_id, exc)
        return None


# --- the prompt's block ----------------------------------------------------------------------------------------------------

def _cr(v: float) -> str:
    return f"{v:,.2f}"


def block(sheet: dict) -> str:
    """The sheet as text for pass 2, in front of the document's text (as the XBRL table and the computed facts are)."""
    out = [f"RESULTS FIGURES (from the exchange file; use only these for results lines)",
           f"{sheet['basis'].title()}, ₹ crore, quarter {sheet['period']} (year ago {sheet['prev_year_period']}, "
           f"previous quarter {sheet['prev_quarter_period']}); changes worked out by code"]
    for key, line in sheet["lines"].items():
        unit = "%" if key == "ebitda_margin" else ""
        parts = [f"{_cr(line['value'])}{unit}"]
        if "prev_year" in line:
            parts.append(f"year ago {_cr(line['prev_year'])}{unit}")
        if "prev_quarter" in line:
            parts.append(f"previous quarter {_cr(line['prev_quarter'])}{unit}")
        for tag, name in (("yoy", "YoY"), ("qoq", "QoQ")):
            if f"{tag}_pct" in line:
                parts.append(f"{line[f'{tag}_pct']:+.1f}% {name}")
            elif f"{tag}_bps" in line:
                parts.append(f"{line[f'{tag}_bps']:+d} bps {name}")
            elif f"{tag}_turn" in line:
                parts.append(f"{name}: {line[f'{tag}_turn'].replace('_', ' ').lower()}")
        out.append(f"{line['label']}: " + "; ".join(parts))
    return "\n".join(out)


# --- the results table -----------------------------------------------------------------------------------------------------

_SLOTS = (("prev_year", "yoy"), ("prev_quarter", "qoq"))


def apply_to_results(results: dict | None, sheet: dict | None) -> list[dict]:
    """The sheet's figures into a card's results table (``results_snapshot``'s dict, in place), for the lines of a company table
    (revenue, EBITDA, margin, PAT; PBT where the table holds it). A row is the sheet's alone: a comparative the sheet lacks is not kept
    from memory's other sources. Returns what changed, {line, was, now}, for the card's grounding record. A bank's or an
    insurer's table (another lens) and a table of another quarter are left as they are."""
    if not results or not sheet or results.get("lens") != "company" or results.get("period") != sheet["period"]:
        return []
    notes = []
    for key, line in sheet["lines"].items():
        if key not in results:
            continue
        was = results[key]
        row: dict = {"value": line["value"]}
        for slot, tag in _SLOTS:
            if slot in line:
                row[slot] = line[slot]
            for suffix in ("pct", "bps", "turn"):
                if f"{tag}_{suffix}" in line:
                    row[f"{tag}_{suffix}"] = line[f"{tag}_{suffix}"]
        if row != {k: v for k, v in was.items() if k in row or k in ("derived", "held")}:
            notes.append({"line": key, "was": {k: v for k, v in was.items() if isinstance(v, (int, float, str))}, "now": row})
        results[key] = row
    return notes


# --- the card text -----------------------------------------------------------------------------------------------------------

_KEYWORDS = {"revenue": r"revenue|sales|turnover|total income",
             "ebitda": r"ebitda|operating profit",
             "pbt": r"pbt|profit before tax",
             "pat": r"pat|net profit|profit after tax|profit to shareholders|net income|bottom line"}
_OTHER_PERIOD = re.compile(r"\b(H[12]|9M|FY\s?\d{2,4}|full[- ]year|annual|year[- ]to[- ]date|YTD|cumulative|guidance|outlook|target|"
                           r"expect\w*|segment\w*|division|order\s?book|backlog|capex|forecast|project\w*|estimate\w*)\b", re.I)
_OWN_QUARTER = re.compile(r"\bQ[1-4]\s?FY\s?\d{2,4}\b", re.I)
_CR = re.compile(r"\s*(?:cr\b|crores?\b)", re.I)
_PCT_UNIT = re.compile(r"\s*(?:%|per ?cent|percent)\s*", re.I)
_QOQ = re.compile(r"(?:\(?\s*)?(?:q[\s/-]*o[\s/-]*q|quarter[- ]on[- ]quarter|sequential|vs\.? (?:the )?(?:previous|prior))", re.I)
_CHANGE = re.compile(r"(?:\(?\s*)?(?:y[\s/-]*o[\s/-]*y|q[\s/-]*o[\s/-]*q|year[- ]on[- ]year|quarter[- ]on[- ]quarter|"
                     r"sequential\w*|from a year|vs\.? (?:the )?(?:year|previous|prior))", re.I)


def _lines_named(sentence: str) -> list[str]:
    return [k for k, words in _KEYWORDS.items() if re.search(rf"\b(?:{words})\b", sentence, re.I)]


def _near(value: float, decimals: int, target: float | None, scale: float = 1.0) -> bool:
    """The figure as written is the target rounded to the figure's own decimals (or within a hair of it)."""
    if target is None:
        return False
    return abs(value - abs(target)) <= 0.5 * 10 ** -decimals + 0.011 * scale


def disagreements(text: str, sheet: dict) -> list[tuple[str, str]]:
    """(figure as written, why) for each amount or change in `text` that this fact sheet contradicts. A sentence is judged only when it
    names exactly one results line and no other period, segment or outlook; an amount is fine when it is the sheet's value, its year-ago
    or previous-quarter value for the line, and a change when it is the sheet's YoY or QoQ."""
    from .grounding import _tokens

    found: list[tuple[str, str]] = []
    for sentence in re.split(r"(?<=[.;])\s+", (text or "").replace("**", "")):
        if _OTHER_PERIOD.search(_OWN_QUARTER.sub(" ", sentence)):
            continue
        named = _lines_named(sentence)
        if len(named) != 1 or named[0] not in sheet["lines"]:
            continue
        line = sheet["lines"][named[0]]
        amounts = [line.get(k) for k in ("value", "prev_year", "prev_quarter", "owners")]
        for value, decimals, pos, kind, raw in _tokens(sentence):
            after = sentence[pos + len(raw):pos + len(raw) + 40]
            if kind not in ("pct", "bps", "pp", "x") and _CR.match(after):
                if not any(_near(value, decimals, a, max(1.0, abs(a or 0) / 1000)) for a in amounts):
                    found.append((raw, f'{line["label"]} is {_cr(line["value"])} Cr in the exchange file'))
            elif kind == "pct" and (unit := _PCT_UNIT.match(after)) and (_CHANGE.match(after, unit.end()) or _QOQ.match(after, unit.end())):
                tag = "qoq" if _QOQ.match(after, unit.end()) else "yoy"
                shown = line.get(f"{tag}_pct")
                if shown is not None and abs(value - abs(shown)) > 0.5 * 10 ** -decimals + 0.051:
                    found.append((raw, f'{line["label"]} {tag.upper()} is {shown:+.1f}% in the exchange file'))
    return found


def removed(out, sheet: dict | None) -> list[str]:
    """Take out of the model's card text the results figures the sheet contradicts (as ``standalone_figures_removed`` does for a
    standalone figure): a sentence of the headline, takeaway, core catalyst or timeline line is cut (kept as it is when nothing would
    be left, for the number checks to judge); a fact, point, key number or change that states one is hidden. The card is not held.
    Returns what was removed."""
    if out.card is None or not sheet:
        return []
    notes: list[str] = []

    def hits(text, where: str) -> bool:
        found = disagreements(str(text or ""), sheet)
        for raw, why in found[:1]:
            notes.append(f'{where}: "{raw}" disagrees with the exchange file ({why}), removed')
        return bool(found)

    def clean(text: str | None, where: str) -> str | None:
        if not text or not hits(text, where):
            return text
        parts = re.split(r"(?<=[.;])\s+", text)
        kept = [x for x in parts if not disagreements(x, sheet)]
        return " ".join(kept) if kept else text

    card = out.card
    card.headline = clean(card.headline, "headline") or card.headline
    card.takeaway = clean(card.takeaway, "takeaway") or card.takeaway
    card.core_catalyst = clean(card.core_catalyst, "core_catalyst")
    card.what_happened = [f for f in card.what_happened if not hits(f.text, "what_happened")] or card.what_happened
    card.why_it_matters = [i for i in card.why_it_matters if not hits(i.text, "why_it_matters")]
    card.key_numbers = [k for k in card.key_numbers if not hits(f"{k.label} {k.value} {k.change or ''}", "key_numbers")]
    card.notable_changes = [c for c in card.notable_changes
                            if not hits(f"{c.metric} {c.previous or ''} ; {c.current or ''} {c.change or ''}", "notable_changes")]
    out.timeline_entry = clean(out.timeline_entry, "timeline") or out.timeline_entry
    for note in notes:
        log.info("%s", note)
    return notes
