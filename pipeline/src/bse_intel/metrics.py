"""A company's metrics table, worked out by code from the exchange's XBRL results figures in its memory. No AI.

TODO row 22 (owner, 25 Oct 2026): the AI never types a past number; it names a cell (metric, period, basis) and code
writes the value. This module is that table. It reads only what the seed stored (dossier ``financial_metrics`` and
``balance_sheet`` entries whose source id starts "xbrl:", dossier.XBRL_SOURCE; a card-written figure is never used)
and keeps one basis per table: consolidated and standalone are never mixed in a row or across a growth comparison.

Units: the stored money figures are already ₹ crore (unit "INR_CR"; the seed divides the file's rupees by 1e7), EPS is
₹ a share ("INR"), ratios are percentages ("PCT"). A money figure stored in any other unit is left out, never rescaled.

Each cell is ``{"value", "unit", "source", "inputs"}``: ``source`` is "exchange" for a figure as filed, "computed" for
anything this code derived (including EBITDA, which the XBRL parser derives from filed lines, xbrl._results), and
``inputs`` the periods (and, for a derived cell, the metric names) it came from. A missing input gives ``None``,
never 0.
"""

from __future__ import annotations

import re

from . import eps_adjust
from .dossier import STANDALONE_KEY, XBRL_SOURCE, _entry_basis, _norm
from .periods import prior_quarter_period, prior_year_period, quarter_from_index, quarter_index

CONSOLIDATED = "CONSOLIDATED"
STANDALONE = "STANDALONE"
UNIT_NOTE = "₹ crore; EPS in ₹ a share; ratios and growth in per cent; margin changes in basis points"

_LENDER_METRICS = {"interest_earned", "interest_expended", "pre_provision_operating_profit", "nii", "gnpa_pct",
                   "nnpa_pct", "gross_premium", "incurred_claims", "net_premium", "first_year_premium"}
# A discontinued business's result sits in the headline profit but not in a continuing EPS (HUL Q3FY26: profit 6,603
# against continuing 2,125); the two differ by more than this share of the profit (associates' share is far smaller).
_DISCONTINUED_TOLERANCE = 0.02
# EPS across a split or bonus: adjusted with the recorded factor, blank only for an exact unrecorded ratio; an issue
# shows its reported growth (eps_adjust.py, F153, owner 25 Oct 2026)

COST_TO_INCOME_NOTE = ("not given on the consolidated basis: a group's other income carries its insurance "
                       "subsidiaries' premium income and its costs their claims (SBI group 60-71% against 47-55% for "
                       "the bank itself); see the STANDALONE table")
LENDER_CONSOLIDATED_NOTE = (
    "a lender's consolidated nii and pre-provision profit add its non-bank subsidiaries' lines (insurers' investment "
    "income and premiums, cards, brokers: SBI Q1FY27 nii 53,993 consolidated against 46,992 for the bank), so they "
    "describe the group; the bank's own figures are on the STANDALONE table")
_LENDER_WORDS = re.compile(r"\b(bank|banks|nbfc|finance|financial|financing|insurance|insurer|lending|housing finance|"
                           r"microfinance|asset reconstruction)\b", re.I)

# lines a general company's table carries (money) and what each draws from
_MONEY = ("revenue", "ebitda", "pat", "pat_owners", "raw_material_cost", "employee_cost", "other_expenses",
          "finance_cost", "depreciation", "other_income", "pbt")
_LENDER_MONEY = ("interest_earned", "interest_expended", "nii", "pre_provision_operating_profit", "provisions",
                 "pat", "pat_group", "pat_owners", "other_income", "revenue", "gross_premium", "incurred_claims")

# what a lender's table cannot show from the stored figures (the file's lines we do not keep, or that need averages)
LENDER_MISSING = (
    "ebitda and its margin (interest is a lender's cost of goods)",
    "net interest margin (needs average earning assets; only the year-end balance sheet is stored)",
    "CASA ratio, capital adequacy, liquidity coverage and provision coverage (not in the stored figures)",
    "credit cost and loan growth by segment (loans and deposits are stored at half-year ends only)",
)
GENERAL_MISSING = (
    "debt to equity and the other balance-sheet ratios at quarters with no half-year statement (the balance sheet is "
    "filed with the half-year and year results only)",
)


def _cell(value, unit, source, inputs=(), note=None):
    cell = {"value": None if value is None else round(value, 2), "unit": unit,
            "source": source if value is not None else None, "inputs": list(inputs)}
    if note:
        cell["note"] = note   # why the figure is to be read with care, or why it is not given
    return cell


def _empty(unit):
    return _cell(None, unit, None)


def _pct_change(now, before):
    """Per cent change; none when either side is missing or the base is not a positive number (a change from a loss or
    from nothing is no per cent)."""
    if now is None or before is None or before <= 0:
        return None
    return (now - before) / before * 100


def _valid_quarter(period: str) -> bool:
    return quarter_index(period) is not None


def _value_source(entry: dict) -> str:
    return str(entry.get("value_news_id") or entry.get("source_news_id") or "")


def _main_bases(dossier: dict) -> dict[str, str | None]:
    """news id -> basis, for every source of every stored main figure (a balance sheet snapshot carries no basis of its
    own, so it takes its results file's)."""
    out: dict[str, str | None] = {}
    for entry in dossier.get("financial_metrics", []):
        for src in entry.get("sources") or [{"news_id": entry.get("source_news_id"), "basis": entry.get("basis")}]:
            if src.get("news_id"):
                out.setdefault(src["news_id"], src.get("basis"))
    return out


def _figures(dossier: dict, basis: str) -> tuple[dict[tuple[str, str], dict], bool]:
    """(metric, period) -> entry for one basis, machine-tagged figures only; and whether the basis was recorded."""
    figures: dict[tuple[str, str], dict] = {}
    main = [e for e in dossier.get("financial_metrics", []) if isinstance(e, dict)]
    recorded = any(_entry_basis(e) for e in main)
    for entry in main:
        if not _value_source(entry).startswith(XBRL_SOURCE):
            continue
        entry_basis = _entry_basis(entry)
        if entry_basis == basis or (entry_basis is None and not recorded):
            figures[(_norm(entry["metric"]), entry["period"])] = entry
    if basis == STANDALONE:
        # a consolidated filer's standalone quarters are kept apart (dossier.put_standalone)
        for entry in (dossier.get(STANDALONE_KEY) or {}).get("metrics", []):
            if str(entry.get("source_news_id", "")).startswith(XBRL_SOURCE):
                figures.setdefault((_norm(entry["metric"]), entry["period"]), entry)
    return figures, recorded or basis == STANDALONE and bool((dossier.get(STANDALONE_KEY) or {}).get("metrics"))


def _snapshots(dossier: dict, basis: str) -> dict[str, dict]:
    """period -> statement of assets and liabilities on this basis, from results files only."""
    out: dict[str, dict] = {}
    bases = _main_bases(dossier)
    for snap in dossier.get("balance_sheet", []):
        news_id = str(snap.get("source_news_id") or "")
        if news_id.startswith(XBRL_SOURCE) and snap.get("period") and bases.get(news_id) == basis:
            out[snap["period"]] = snap
    if basis == STANDALONE:
        for snap in (dossier.get(STANDALONE_KEY) or {}).get("balance_sheet", []):
            if str(snap.get("source_news_id") or "").startswith(XBRL_SOURCE) and snap.get("period"):
                out.setdefault(snap["period"], snap)
    return out


def is_lender(dossier: dict, basis: str | None = None) -> bool:
    """A bank, NBFC or insurer: its banking, NBFC or insurance lines are stored, or its industry says so."""
    for entry in dossier.get("financial_metrics", []):
        if _norm(entry.get("metric", "")) in _LENDER_METRICS:
            return True
    return bool(_LENDER_WORDS.search(f"{dossier.get('industry') or ''} {dossier.get('sector') or ''}"))


def missing_lines(dossier: dict) -> tuple[str, ...]:
    """What this company's table cannot show, and why."""
    return LENDER_MISSING if is_lender(dossier) else GENERAL_MISSING


def table(dossier: dict | None, basis: str) -> list[dict]:
    """One row per quarter, newest first, for one basis ("CONSOLIDATED" or "STANDALONE"). Empty when memory has no
    machine-tagged quarter on that basis."""
    basis = (basis or "").upper()
    if not dossier or basis not in (CONSOLIDATED, STANDALONE):
        return []
    figures, recorded = _figures(dossier, basis)
    lender = is_lender(dossier)
    periods = sorted({p for _, p in figures if _valid_quarter(p)}, key=quarter_index, reverse=True)
    snapshots = _snapshots(dossier, basis)

    def stored(metric: str, period: str | None, unit: str = "INR_CR"):
        """(value, entry) of a stored figure, only in the expected unit."""
        entry = figures.get((metric, period)) if period else None
        if not entry or entry.get("value") is None or (entry.get("unit") or unit) != unit:
            return None
        return entry["value"]

    def exchange(metric: str, period: str, unit: str = "INR_CR"):
        value = stored(metric, period, unit)
        return _cell(value, unit, "exchange", [period]) if value is not None else _empty(unit)

    def nii(period: str | None):
        """Stated, else interest earned less interest expended; returns (value, source, metrics used)."""
        if period is None:
            return None, None, ()
        value = stored("nii", period)
        if value is not None:
            return value, "exchange", ()
        earned, spent = stored("interest_earned", period), stored("interest_expended", period)
        if earned is not None and spent is not None:
            return earned - spent, "computed", ("interest_earned", "interest_expended")
        return None, None, ()

    def margin(period: str | None):
        ebitda, revenue = stored("ebitda", period), stored("revenue", period)
        return ebitda / revenue * 100 if ebitda is not None and revenue else None

    def line(metric: str, period: str):
        """(value, source, metrics) for a metric on a period, with the lender derivations."""
        if metric == "nii":
            return nii(period)
        if metric == "profit_to_shareholders":
            for name in ("pat_owners", "pat_group"):
                value = stored(name, period)
                if value is not None:
                    return value, "exchange", (name,)
            if lender:
                # a bank's file has no owners' line of its own: xbrl.py folds the consolidated profit after minority
                # interest and associates (pat_group) into "pat", the figure its EPS is on
                value = stored("pat", period)
                if value is not None:
                    return value, "exchange", ("pat",)
            return None, None, ()
        value = stored(metric, period, "INR" if metric == "eps" else "INR_CR")   # EPS is ₹ a share, not crore
        return (value, "exchange", ()) if value is not None else (None, None, ())

    def discontinued(period: str | None):
        """The part of a period's headline profit that is not from continuing operations, when it is material."""
        pat, continuing = stored("pat", period), stored("pat_continuing", period)
        if pat is None or continuing is None or abs(pat - continuing) <= max(1.0, _DISCONTINUED_TOLERANCE * abs(pat)):
            return None
        return pat - continuing

    def eps_profit(period: str | None):
        """The profit EPS is on: continuing profit where a discontinued operation sits in the headline, else the owners'
        profit, else the profit (a lender's: its profit to shareholders)."""
        if lender:
            return line("profit_to_shareholders", period)[0]
        if discontinued(period) is not None:
            return stored("pat_continuing", period)
        profit = stored("pat_owners", period)
        return stored("pat", period) if profit is None else profit

    def eps_vs(period: str, other: str | None):
        """How another quarter's EPS stands against this one's: as stated, on this share count, or not comparable
        (eps_adjust.compare: a recorded split or bonus adjusts it, an unrecorded jump of the implied share count blanks it)."""
        eps_now, eps_other = stored("eps", period, "INR"), stored("eps", other, "INR") if other else None
        if eps_now is None or eps_other is None:
            return eps_adjust.Compare("same")
        return eps_adjust.compare(dossier, period, other, eps_now, eps_other, eps_profit(period), eps_profit(other))

    def growth(metric: str, period: str, prior: str | None):
        if metric == "eps" and prior:
            versus = eps_vs(period, prior)
            if versus.kind == "blank":
                return _cell(None, "PCT", None, [period, prior], note=versus.note)
            if versus.kind == "adjusted":
                value = _pct_change(stored("eps", period, "INR"), versus.eps_old)
                return (_cell(value, "PCT", "computed", [period, prior], note=versus.note) if value is not None
                        else _empty("PCT"))
        if not lender and metric in ("pat", "pat_owners") and (discontinued(period) or discontinued(prior)):
            # a change that runs through a demerger or sale gain is no growth: read pat_continuing_*
            return _cell(None, "PCT", None, [period, prior],
                         note="a period in the comparison holds a discontinued operation; see pat_continuing")
        now, before = line(metric, period)[0], (line(metric, prior)[0] if prior else None)
        value = _pct_change(now, before)
        return _cell(value, "PCT", "computed", [period, prior]) if value is not None else _empty("PCT")

    def share(metric: str, period: str):
        part, revenue = stored(metric, period), stored("revenue", period)
        if part is None or not revenue:
            return _empty("PCT")
        if part == 0:
            return _cell(None, "PCT", None, [period], note="the file prints 0, which is a filler for a line it does not have")
        return _cell(part / revenue * 100, "PCT", "computed", [period])

    def consecutive(period: str, count: int = 4) -> list[str] | None:
        start = quarter_index(period)
        if start is None:
            return None
        wanted = [quarter_from_index(start - i) for i in range(count)]
        return wanted

    def ttm(metric: str, period: str):
        wanted = consecutive(period)
        values = [line(metric, p)[0] for p in wanted] if wanted else []
        if not wanted or any(v is None for v in values):
            return _empty("INR_CR")
        if not lender and metric in ("pat", "pat_owners") and any(discontinued(p) for p in wanted):
            return _cell(None, "INR_CR", None, wanted,
                         note="a quarter in the year holds a discontinued operation; see ttm_pat_continuing")
        return _cell(sum(values), "INR_CR", "computed", wanted)

    has_discontinued = not lender and any(discontinued(p) is not None for p in periods)
    rows = []
    for period in periods:
        py, pq = prior_year_period(period), prior_quarter_period(period)
        py = py if py in periods else None
        pq = pq if pq in periods else None
        row: dict = {"period": period, "basis": basis, "kind": "lender" if lender else "general",
                     "unit_note": UNIT_NOTE}
        if not recorded:
            row["basis_recorded"] = False   # memory stored no basis at all for this company: assumed, not known
        if lender and basis == CONSOLIDATED:
            row["basis_note"] = LENDER_CONSOLIDATED_NOTE
        if lender:
            for name in ("interest_earned", "interest_expended", "pre_provision_operating_profit", "provisions", "pat",
                         "other_income"):
                row[name] = exchange(name, period)
            value, source, used = nii(period)
            row["nii"] = _cell(value, "INR_CR", source, [period, *used]) if value is not None else _empty("INR_CR")
            value, source, used = line("profit_to_shareholders", period)
            row["profit_to_shareholders"] = (_cell(value, "INR_CR", source, [period, *used]) if value is not None
                                             else _empty("INR_CR"))
            row["revenue"] = exchange("revenue", period)   # an NBFC's or insurer's top line; a bank files none
            for name in ("gross_premium", "incurred_claims"):
                if stored(name, period) is not None:
                    row[name] = exchange(name, period)
            row["eps"] = exchange("eps", period, "INR")
            for name in ("gnpa_pct", "nnpa_pct", "roa_pct", "combined_ratio", "claims_ratio"):
                if stored(name, period, "PCT") is not None:
                    row[name] = exchange(name, period, "PCT")
            # cost to income: (NII + other income - pre-provision profit) / (NII + other income), a bank's own ratio
            n, _, _ = nii(period)
            oi, ppop = stored("other_income", period), stored("pre_provision_operating_profit", period)
            income = n + oi if n is not None and oi is not None else None
            if basis != STANDALONE:
                row["cost_to_income"] = _cell(None, "PCT", None, [period], note=COST_TO_INCOME_NOTE)
            else:
                row["cost_to_income"] = (_cell((income - ppop) / income * 100, "PCT", "computed",
                                               [period, "nii", "other_income", "pre_provision_operating_profit"],
                                               note="the bank itself (standalone)")
                                         if income and ppop is not None else _empty("PCT"))
            row["ebitda"] = _empty("INR_CR")        # never for a lender
            row["ebitda_margin"] = _empty("PCT")
            for name in ("nii", "pre_provision_operating_profit", "pat", "profit_to_shareholders", "interest_earned"):
                row[f"{name}_yoy"] = growth(name, period, py)
                row[f"{name}_qoq"] = growth(name, period, pq)
            row["eps_yoy"] = growth("eps", period, py)
            row["eps_qoq"] = growth("eps", period, pq)
            for name in ("nii", "pre_provision_operating_profit", "pat", "interest_earned"):
                row[f"ttm_{name}"] = ttm(name, period)
        else:
            row["revenue"] = exchange("revenue", period)
            value = stored("ebitda", period)
            row["ebitda"] = (_cell(value, "INR_CR", "computed", [period, "pbt_before_exceptional", "finance_cost",
                                                                   "depreciation", "other_income"])
                             if value is not None else _empty("INR_CR"))
            m = margin(period)
            row["ebitda_margin"] = _cell(m, "PCT", "computed", [period]) if m is not None else _empty("PCT")
            row["pat"] = exchange("pat", period)
            row["profit_to_shareholders"] = exchange("pat_owners", period)
            held = discontinued(period)
            if held is not None:
                note = (f"includes {held:,.2f} cr from discontinued operations; eps and pat_continuing are on "
                        "continuing operations only")
                for name in ("pat", "profit_to_shareholders"):
                    if row[name]["value"] is not None:
                        row[name]["note"] = note
            if has_discontinued:
                row["pat_continuing"] = exchange("pat_continuing", period)
            row["eps"] = exchange("eps", period, "INR")
            row["pbt"] = exchange("pbt", period)
            for name in ("revenue", "ebitda", "pat", "profit_to_shareholders", "eps",
                         *(("pat_continuing",) if has_discontinued else ())):
                metric = {"profit_to_shareholders": "pat_owners"}.get(name, name)
                row[f"{name}_yoy"] = growth(metric, period, py)
                row[f"{name}_qoq"] = growth(metric, period, pq)
            m_before = margin(py)
            row["ebitda_margin_yoy_bps"] = (_cell((m - m_before) * 100, "bps", "computed", [period, py])
                                            if m is not None and m_before is not None else _empty("bps"))
            for name, metric in (("raw_material_cost_share", "raw_material_cost"), ("employee_cost_share", "employee_cost"),
                                 ("other_expenses_share", "other_expenses"), ("finance_cost_share", "finance_cost"),
                                 ("depreciation_share", "depreciation")):
                row[name] = share(metric, period)
            for name, metric in (("ttm_revenue", "revenue"), ("ttm_ebitda", "ebitda"), ("ttm_pat", "pat"),
                                 ("ttm_profit_to_shareholders", "pat_owners"),
                                 *((("ttm_pat_continuing", "pat_continuing"),) if has_discontinued else ())):
                row[name] = ttm(metric, period)
            row["ttm_eps"] = _empty("INR")
            wanted = consecutive(period)
            eps = [stored("eps", p, "INR") for p in wanted] if wanted else []
            if wanted and all(v is not None for v in eps):
                versus = [eps_vs(period, p) for p in wanted[1:]]
                if any(v.kind == "blank" for v in versus):
                    row["ttm_eps"] = _cell(None, "INR", None, wanted,
                                           note=next(v.note for v in versus if v.kind == "blank"))
                else:
                    # older quarters on the newest quarter's share count
                    total = eps[0] + sum(v.eps_old if v.kind == "adjusted" else e for v, e in zip(versus, eps[1:]))
                    notes = list(dict.fromkeys(v.note for v in versus if v.kind == "adjusted"))
                    row["ttm_eps"] = _cell(total, "INR", "computed", wanted, note="; ".join(notes) or None)
            row["ttm_ebitda_margin"] = _empty("PCT")
            if row["ttm_ebitda"]["value"] is not None and row["ttm_revenue"]["value"]:
                row["ttm_ebitda_margin"] = _cell(row["ttm_ebitda"]["value"] / row["ttm_revenue"]["value"] * 100, "PCT",
                                                 "computed", row["ttm_revenue"]["inputs"])
        row.update(_balance_cells(snapshots.get(period), period, lender))
        rows.append(row)
    return rows


def _balance_cells(snap: dict | None, period: str, lender: bool) -> dict:
    """The half-year statement's lines and ratios; only at quarters that have one (Q2 = September, Q4 = March)."""
    if not snap:
        return {}
    out: dict = {}

    def val(key: str):
        v = snap.get(key)
        return v if isinstance(v, (int, float)) else None

    for key in ("net_worth_cr", "gross_debt_cr", "cash_cr", "total_assets_cr"):
        if val(key) is not None:
            out[key[:-3]] = _cell(val(key), "INR_CR", "exchange", [period])
    if lender:
        for key in ("deposits_cr", "advances_cr"):
            if val(key) is not None:
                out[key[:-3]] = _cell(val(key), "INR_CR", "exchange", [period])
        return out
    debt, worth = val("gross_debt_cr"), val("net_worth_cr")
    out["debt_to_equity"] = (_cell(debt / worth, "x", "computed", [period, "gross_debt_cr", "net_worth_cr"])
                             if debt is not None and worth and worth > 0 else _empty("x"))
    ca, cl = val("current_assets_cr"), val("current_liabilities_cr")
    out["current_ratio"] = (_cell(ca / cl, "x", "computed", [period, "current_assets_cr", "current_liabilities_cr"])
                            if ca is not None and cl else _empty("x"))
    return out


def render(rows: list[dict], limit: int = 8) -> str:
    """The table as plain text for the command line: newest quarters, one line per metric."""
    if not rows:
        return "no machine-tagged quarters on this basis in memory"
    shown = rows[:limit]
    skip = {"period", "basis", "kind", "unit_note", "basis_recorded", "basis_note"}
    names = [k for k in shown[0] if k not in skip]
    for row in shown:
        names += [k for k in row if k not in skip and k not in names]
    width = max(len(n) for n in names)
    body = {name: ["-" if (row.get(name) or {}).get("value") is None else format(row[name]["value"], ",.2f")
                   for row in shown] for name in names}
    # each column as wide as its widest cell (or its period label), two spaces from the next
    col = [max([len(r["period"])] + [len(body[n][i]) for n in names]) for i, r in enumerate(shown)]
    out = [f"{rows[0]['basis']} ({rows[0]['kind']}), {UNIT_NOTE}",
           " " * width + "".join("  " + r["period"].rjust(col[i]) for i, r in enumerate(shown))]
    for name in names:
        out.append(f"{name:<{width}}" + "".join("  " + body[name][i].rjust(col[i]) for i in range(len(shown))))
    notes: dict[str, list[str]] = {}   # a cell's note: a figure to read with care, or why it is not given
    for name in names:
        for row in shown:
            note = (row.get(name) or {}).get("note")
            if note:
                notes.setdefault(f"{name}: {note}", []).append(row["period"])
    for text, periods in notes.items():
        out.append(f"note {text} ({', '.join(periods)})")
    if shown[0].get("basis_note"):
        out.append(f"note {shown[0]['basis_note']}")
    return "\n".join(out)
