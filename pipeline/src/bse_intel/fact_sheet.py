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
With no sheet (the file is late, a quarter memory lacks) nothing here runs and the card is what it was.

TODO 151 (owner, 31 Oct 2026 ~13:45 IST), behind CARD_FACT_SHEET_LENDERS (default off): banks, NBFCs and insurers get a sheet too, on
the rows results_table.LAYOUT gives each family (screener_view's statements). A bank: interest earned (screener's "Revenue"), net
interest income (Revenue - Interest, as memory works out NII), financing profit and its margin, PBT and profit; an NBFC: revenue,
financing profit and its margin, PBT and profit; an insurer: profit only (its statements hold no other line). An NBFC-template filer
whose known industry is not financial services is a company (the corporate rows, as results_table), and one in insurance an insurer.
Each family has its own words in the text check (a bank's "operating profit" is its pre-provision profit and its "total income" adds
other income: neither is judged), and its sheet goes only into a card table of its own kind (a bank table's interest earned, NII, PBT
and profit; an insurer's PBT and profit; an NBFC's company table: revenue, PBT and profit, and its financing profit and margin in the EBITDA rows' place, owner 31 Oct 2026).
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
NII = ("Revenue", "Interest")       # a bank's net interest income: its statements' Revenue (interest earned) less Interest (expended)
_TURN_LINES = {"ebitda", "pbt", "pat", "financing_profit"}
# family -> (lines, (margin key, margin row, its label) or None); the rows are results_table.LAYOUT's for each family
FAMILY_LINES = {
    sv.CORPORATE: (LINES, ("ebitda_margin", MARGIN, "EBITDA margin")),
    sv.BANK: ((("revenue", "Revenue", "Interest earned"), ("nii", NII, "Net interest income"),
               ("financing_profit", "Financing Profit", "Financing profit"), ("pbt", "Profit before tax", "PBT"),
               ("pat", "Net Profit", "Net profit")), ("financing_margin", "Financing Margin %", "Financing margin")),
    sv.NBFC: ((("revenue", "Revenue", "Revenue"), ("financing_profit", "Financing Profit", "Financing profit"),
               ("pbt", "Profit before tax", "PBT"), ("pat", "Net Profit", "PAT")), ("financing_margin", "Financing Margin %", "Financing margin")),
    sv.INSURER: ((("pat", "Net Profit", "PAT"),), None),
}
# the card table a family's sheet goes into (results_snapshot's lens), and the sheet line -> that table's key where they differ
LENS = {sv.CORPORATE: "company", sv.NBFC: "company", sv.BANK: "bank", sv.INSURER: "insurer"}
TABLE_KEY = {sv.BANK: {"revenue": "interest_earned"}}


def _value(rows: dict, row) -> float | None:
    """A sheet line's figure from an entry's rows: the row itself, or for a pair (NII) the first less the second."""
    if isinstance(row, tuple):
        a, b = (rows or {}).get(row[0]), (rows or {}).get(row[1])
        return None if a is None or b is None else a - b
    return (rows or {}).get(row)


def layout_of(family: str | None, industry: str | None) -> str | None:
    """The sheet's layout for an entry's family: an NBFC-template filer in a known industry outside financial services is a company,
    one in insurance an insurer (results_table.table_of, measured 31 Oct 2026); None for a family with no sheet."""
    from . import results_table      # results_table imports this module

    if family == sv.NBFC:
        return sv.CORPORATE if results_table.non_lender(industry) else sv.INSURER if results_table.insurer_industry(industry) else sv.NBFC
    return family if family in FAMILY_LINES else None


def quarter_entries(dossier: dict, period: str, basis: str, families: tuple[str, ...] = (sv.CORPORATE,)) -> dict | None:
    """The file-labelled quarters-table entry of a period and basis whose family is one of ``families``, or None."""
    for e in dossier.get(statements.KEY, []) or []:
        if (isinstance(e, dict) and e.get("table") == "quarters" and e.get("period") == period and e.get("basis") == basis
                and e.get("family") in families and (e.get("lab") or {}).get("by") == "file"):
            return statements.corrected_entry(e)   # the shared profit-line rules, also for a dossier not yet rebuilt
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


def fact_sheet(dossier: dict, period: str | None, basis: str | None = None, lenders: bool | None = None) -> dict | None:
    """The quarter's fact sheet from ``dossier["statements"]``, or None when memory lacks the quarter (the exchange file is late,
    or, without ``lenders``, it is not a corporate filer's). ``basis`` None: consolidated when memory has the quarter on it, else
    standalone. ``lenders`` None: the switch CARD_FACT_SHEET_LENDERS (banks, NBFCs and insurers too, TODO 151)."""
    if not period or not period.startswith("Q"):
        return None
    if lenders is None:
        from .settings import card_fact_sheet_lenders
        lenders = card_fact_sheet_lenders()
    families = tuple(FAMILY_LINES) if lenders else (sv.CORPORATE,)
    prior = {"prev_year": prior_year_period(period), "prev_quarter": prior_quarter_period(period)}
    for b in ((basis,) if basis else (CONSOLIDATED, STANDALONE)):
        now = quarter_entries(dossier, period, b, families)
        if now is None:
            continue
        family = now.get("family")
        layout = layout_of(family, dossier.get("industry")) if lenders else family
        if layout is None:
            continue
        lines, margin_spec = FAMILY_LINES[layout]
        # the comparatives on the entry's own family (a quarter filed on another template is no base)
        before = {slot: quarter_entries(dossier, p, b, (family,)) if p else None for slot, p in prior.items()}
        sheet: dict = {"period": period, "basis": b, "unit": "₹ crore", "prev_year_period": prior["prev_year"],
                       "prev_quarter_period": prior["prev_quarter"], "source_news_id": now.get("source_news_id"), "lines": {},
                       "family": layout}
        for key, row, label in lines:
            if key == "pat" and (now.get("rows") or {}).get(OWNERS) is not None:
                # the profit to shareholders, the line a card calls PAT; its comparatives on the same footing only (A/B of 30 Oct
                # 2026: the total with minority interest went out as "profit to shareholders", Grindwell 133.17 for 132.70)
                row = OWNERS
            value = _value(now.get("rows"), row)
            if value is None:
                continue
            line: dict = {"label": label, "value": round(value, 2)}
            for slot, tag in (("prev_year", "yoy"), ("prev_quarter", "qoq")):
                base = _value((before[slot] or {}).get("rows"), row)
                if base is None:
                    continue
                line[slot] = round(base, 2)
                change = _change(value, base, key)
                if "pct" in change:
                    line[f"{tag}_pct"] = change["pct"]
                elif "turn" in change:
                    line[f"{tag}_turn"] = change["turn"]
            if key == "pat" and row == OWNERS and (now.get("rows") or {}).get("Net Profit") is not None:
                line["with_minority"] = round(now["rows"]["Net Profit"], 2)
            sheet["lines"][key] = line
        margin_key, margin_row, margin_label = margin_spec or (None, None, None)
        margin = (now.get("rows") or {}).get(margin_row) if margin_row else None
        if margin is not None:
            line = {"label": margin_label, "value": round(margin, 2)}
            for slot, tag in (("prev_year", "yoy"), ("prev_quarter", "qoq")):
                base = ((before[slot] or {}).get("rows") or {}).get(margin_row)
                if base is not None:
                    line[slot] = round(base, 2)
                    line[f"{tag}_bps"] = round((margin - base) * 100)
            sheet["lines"][margin_key] = line
        has_revenue = any(key == "revenue" for key, _, _ in lines)
        if "pat" in sheet["lines"] and ("revenue" in sheet["lines"] or not has_revenue):
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
        unit = "%" if key.endswith("_margin") else ""
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
    """The sheet's figures into a card's results table (``results_snapshot``'s dict, in place), for the lines the table holds: a
    company table's revenue, EBITDA, margin, PAT (PBT where it holds it); a bank table's interest earned, NII, PBT and profit; an
    insurer's PBT and profit; an NBFC's company table its revenue, PBT and profit, and its financing profit and margin in place of
    the EBITDA rows (``_nbfc_rows``). A row is the sheet's alone: a comparative the sheet lacks is not kept from memory's other sources.
    Returns what changed, {line, was, now}, for the card's grounding record. A table of another kind than the sheet's family (a
    bank's sheet beside a company table) and a table of another quarter are left as they are."""
    family = sheet.get("family", sv.CORPORATE) if sheet else None
    if not results or not sheet or results.get("lens") != LENS.get(family) or results.get("period") != sheet["period"]:
        return []
    notes = []
    for line_key, line in sheet["lines"].items():
        key = TABLE_KEY.get(family, {}).get(line_key, line_key)
        if key not in results and not (family == sv.NBFC and line_key in ("financing_profit", "financing_margin")):
            continue
        if key not in results:          # an NBFC's financing rows are new to its company table (_nbfc_rows puts them in its lines)
            results[key] = {}
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
    if family == sv.NBFC:
        notes += _nbfc_rows(results)
    return notes


# an NBFC's card shows its financing profit and margin where a company shows EBITDA (owner, 31 Oct 2026: "Yes, NBFC cards show
# financing profit"), as Screener and the Results page do; the EBITDA rows (ours, and a printed one under CARD_EBITDA_PROFIT_V2) go
_NBFC_SWAP = (("ebitda", "financing_profit", "Financing profit", "cr"), ("ebitda_margin", "financing_margin", "Financing margin", "pct"))
_EBITDA_KEYS = ("ebitda", "ebitda_margin", "ebitda_filing")


def _nbfc_rows(results: dict) -> list[dict]:
    """An NBFC's company table with the sheet's financing profit and margin in the EBITDA rows' place (in place); nothing when the sheet
    gave no financing profit (the table stays as it was). Returns what changed, as ``apply_to_results``."""
    if "financing_profit" not in results:
        return []
    notes = [{"line": key, "was": {k: v for k, v in (results.get(key) or {}).items() if isinstance(v, (int, float, str))},
              "now": "removed: an NBFC shows its financing profit"} for key in _EBITDA_KEYS if key in results]
    lines = results.get("lines")
    if isinstance(lines, list):
        new: list = []
        for spec in lines:
            key = spec.get("key") if isinstance(spec, dict) else None
            swap = next((x for x in _NBFC_SWAP if x[0] == key), None)
            if swap and swap[1] in results:
                new.append({"key": swap[1], "label": swap[2], "unit": swap[3]})
            elif key not in _EBITDA_KEYS:
                new.append(spec)
        if not any(isinstance(x, dict) and x.get("key") == "financing_profit" for x in new):
            at = next((i for i, x in enumerate(new) if isinstance(x, dict) and x.get("key") == "pat"), len(new))
            new.insert(at, {"key": "financing_profit", "label": "Financing profit", "unit": "cr"})
        results["lines"] = new
    for key in _EBITDA_KEYS:
        results.pop(key, None)
    return notes


# --- the card text -----------------------------------------------------------------------------------------------------------

_KEYWORDS = {"revenue": r"revenue|sales|turnover|total income",
             "ebitda": r"ebitda|operating profit",
             "pbt": r"pbt|profit before tax",
             "pat": r"pat|net profit|profit after tax|profit to shareholders|net income|bottom line"}
# a lender's own words for its lines: a bank's "operating profit" is its pre-provision profit and its "total income" adds other income,
# an NBFC's "total income" too, so neither is judged against the sheet; "interest income" is not the start of "net interest income"
FAMILY_KEYWORDS = {
    sv.CORPORATE: _KEYWORDS,
    sv.BANK: {"revenue": r"interest earned|(?<!net )interest income", "nii": r"net interest income|nii",
              "financing_profit": r"financing profit", "pbt": _KEYWORDS["pbt"], "pat": _KEYWORDS["pat"]},
    sv.NBFC: {"revenue": r"revenue", "financing_profit": r"financing profit", "pbt": _KEYWORDS["pbt"], "pat": _KEYWORDS["pat"]},
    sv.INSURER: {"pat": _KEYWORDS["pat"]},
}
_OTHER_PERIOD = re.compile(r"\b(H[12]|9M|FY\s?\d{2,4}|full[- ]year|annual|year[- ]to[- ]date|YTD|cumulative|guidance|outlook|target|"
                           r"expect\w*|segment\w*|division|order\s?book|backlog|capex|forecast|project\w*|estimate\w*)\b", re.I)
_OWN_QUARTER = re.compile(r"\bQ[1-4]\s?FY\s?\d{2,4}\b", re.I)
_CR = re.compile(r"\s*(?:cr\b|crores?\b)", re.I)
_PCT_UNIT = re.compile(r"\s*(?:%|per ?cent|percent)\s*", re.I)
_QOQ = re.compile(r"(?:\(?\s*)?(?:q[\s/-]*o[\s/-]*q|quarter[- ]on[- ]quarter|sequential|vs\.? (?:the )?(?:previous|prior))", re.I)
_CHANGE = re.compile(r"(?:\(?\s*)?(?:y[\s/-]*o[\s/-]*y|q[\s/-]*o[\s/-]*q|year[- ]on[- ]year|quarter[- ]on[- ]quarter|"
                     r"sequential\w*|from a year|vs\.? (?:the )?(?:year|previous|prior))", re.I)


def _lines_named(sentence: str, family: str = sv.CORPORATE) -> list[str]:
    words_of = FAMILY_KEYWORDS.get(family, _KEYWORDS)
    return [k for k, words in words_of.items() if re.search(rf"\b(?:{words})\b", sentence, re.I)]


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
        named = _lines_named(sentence, sheet.get("family", sv.CORPORATE))
        if len(named) != 1 or named[0] not in sheet["lines"]:
            continue
        line = sheet["lines"][named[0]]
        amounts = [line.get(k) for k in ("value", "prev_year", "prev_quarter", "with_minority")]
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
