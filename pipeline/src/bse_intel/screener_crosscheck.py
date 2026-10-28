"""Read-only cross-check of memory's exchange-file figures against the stored screener.in pages. No request, no write, no AI.
TRACKER F163, TODO 50.

For every company, each quarter (and each financial year of screener's annual profit and loss section) is compared on
memory's basis with the exchange file's figure only (``metrics._figures``: ``xbrl:`` sources):

- revenue: screener's Sales against our ``revenue`` (a lender: its Revenue against our ``revenue``, revenue from operations,
  else ``interest_earned``: a bank's file has no revenue line. Interest earned first compared an NBFC's interest income with
  screener's revenue from operations: Aadhar Housing Q2FY25 672.56 against 764.27, RattanIndia 1.91 against 1,921.49, both
  in memory; screener-referee run 40288810286, checked on the 25 Oct backup),
- pat: Net Profit against our ``pat`` (a lender's profit is a different definition, so a difference is not a mismatch),
- eps: EPS in Rs against our ``eps`` (or ``basic_eps``), where both have it.
- the six other lines of screener's quarterly table (27 Oct 2026, quarters only; ``six_pairs``): Operating Profit against
  our ``ebitda``, Other Income against ``other_income``, Interest against ``finance_cost``, Depreciation against
  ``depreciation``, Profit before tax against ``pbt``, Tax % against our tax over ``pbt`` (``tax_expense``, else
  ``current_tax`` + ``deferred_tax``). Screener prints whole crore, so a money line is a match within ₹0.5 Cr (or 0.5%) and
  Tax % within one percentage point. A lender page (Revenue / Financing Profit layout) is not read for Operating Profit and
  Interest: its table is a different one. A gap is named only when one of screener's own rules (docs/bench/screener-rules.md
  rows 1 and 4) closes it and the gap is more than twice the tolerance: ``exceptional_in_other_income`` (screener's Other
  Income holds the exceptional items; an item of at least ₹5 Cr and a quarter of our other income); anything else is ``mismatch``. These lines are counted apart (``six_pairs``, ``six_by_class``), never in ``pairs`` or ``by_class``;
  the XBRL, explain and PDF referees read revenue, profit and EPS only and pass these rows through unread.
- the balance sheet and the cash flow (28 Oct 2026; ``bs_pairs``, ``cf_pairs``, counted apart from ``pairs`` and ``by_class``,
  per line in ``bs_by_line`` / ``cf_by_line``, their non-match rows in ``table_rows`` so the referees never see them, and in
  the same CSV under the field ``table``). Balance sheet: screener's Equity Capital, Reserves, Borrowings, Deposits (a bank),
  Other Liabilities, Total Liabilities, Fixed Assets, CWIP, Investments, Other Assets and Total Assets by statement date (March
  year ends and the latest half year, Q4FYxx and Q2FYxx) against memory's results-file snapshots (``metrics._snapshots``) on
  memory's basis, within ₹1 Cr or 0.5%. Total Liabilities is equity plus liabilities, so it is compared with our total assets
  (our ``total_liabilities_cr`` leaves equity out); Other Liabilities and Other Assets are screener's plugs, worked out from our
  lines as the company page does (a missing part gives no pair); they are information, and the report says so. Screener's
  own rules (docs/bench/screener-rules.md rows 10 and 11) add parts memory has no line for. A part counts only when the stored
  XBRL facts of the file show it (``xbrl_facts.py``, ``screener_parts.py``) and our figure plus it matches screener's within the
  tolerance: ``matches_screener_view:<line>_plus_<parts>`` (borrowings plus lease liabilities and current maturities, none in a
  half-year balance sheet; fixed assets plus goodwill, intangibles and right-of-use assets; CWIP plus intangibles under
  development; investments plus equity-method investments, investment property, other financial assets; both totals less the
  deferred tax netted off), also ``goodwill_in_fixed_assets`` and ``net_worth_less_capital`` (reserves) from memory's own lines. A
  gap no found part closes is NEVER a "definition" (independent review, 28 Oct 2026: that name, given to any larger screener
  figure, hid a missing current-borrowings block): ``unexplained_larger`` (screener's figure the larger of borrowings, fixed
  assets, CWIP, a non-lender's investments) or ``mismatch``, the note saying what the facts held. Also ``derived:part_differs`` (a
  plug that differs only because a line it is worked out of differs), ``wrong_period`` (ours equals screener's figure for another
  date), ``scale``, ``small_gap``. Cash flow: operating, investing, financing and net cash flow by the company's own year end:
  a March year (FYxx) against our file figures, any other year end ("YE:2025-06") against the 12-month cash flow in the stored
  facts of the file ending then (memory labels no such year), a column neither can pair is counted and its reason listed
  (``cf_skipped``); classes match, ``sign``, wrong_period, scale, small_gap, mismatch. The page sections are read by their ids
  ``balance-sheet`` and ``cash-flow``; ``sections`` in the summary counts the stored pages that carry them and how many were
  compared, always (also at 0), and the report warns in words when a section is missing. Revenue and EPS pairs use the facts too:
  Sales less excise, sales tax / VAT / GST and discounts, EPS on total shares (treasury shares tagged), EPS on total or on
  continuing profit named. Each adjustment applied is in the CSV field ``adjustment`` (rule and where the parts came from).

Each pair gets one class:

- ``match``: within ₹1 Cr or 0.5% (screener rounds to whole crore); EPS within 0.06 or 0.5%;
- ``wrong_quarter``: ours differs from screener's column for the period but equals (exactly, within rounding; at least
  ₹5 Cr) screener's figure for another quarter or year of the same line, any column, a year-ago comparative stored as
  current included: a figure saved under the wrong period in memory (or a mislabelled column on screener). Both labels are
  in the note, and the chance risk when several columns match. Memory's own period checks, no screener needed, are
  ``memory_period_suspect`` rows: the same value stored for two quarters (copy-forward), a source filed before its quarter
  ended, a quarter whose source file is labelled for another quarter (the file's own start and end dates are not stored);
- ``scale``: the ratio is 10, 100 or 1000 (or the inverse) within 3%: a unit slip;
- ``naming``: screener equals another official line of the same filing that memory holds (screener's Sales is our
  ``total_income``, its profit our ``pat_owners``, ``pat_continuing`` or ``pat_group``, revenue net of excise, ...): the
  line is recorded in the note; tried before anything is called a lender definition, a steady difference or a mismatch;
- ``lender_definition``: a bank, NBFC or insurer's profit or income differs (screener's definition is not the exchange's);
- ``steady_line_difference``: revenue only, four or more unmatched quarters of a company differ by a near-constant amount or
  ratio: a definition difference (an excise line included or left out), not a wrong figure;
- ``mismatch``: anything else.

Quarters one side has and the other lacks are counted as gaps (``screener_only``, ``memory_only``), memory's only inside
the span of quarters screener shows. Referee (owner, 26 Oct 2026: the official filing decides who is wrong): each ``wrong_quarter``, ``scale`` and ``mismatch`` pair
is looked up in the quarter's results filing text (the R2 text cache, ``text/<news_id>.json.gz``; nothing is downloaded) and
both values are searched for at the printed unit (crore, lakh, million): verdict ``ours_matches_official``,
``screener_matches_official``, ``both_match``, ``neither`` or ``no_official_text``. The output is a summary (counts by class and sector, worst companies), a CSV of every
non-match pair and a short markdown report; the job uploads them as an artifact and commits nothing.
"""

from __future__ import annotations

import csv
import calendar
import io
import json
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from . import line_map, screener_parts, xbrl_facts
from .dossier import _norm
from .memory_gaps import main_basis, quarter_end
from .metrics import CONSOLIDATED, STANDALONE, _figures, _snapshots, _value_source, is_lender
from .periods import canonical_period, quarter_index
from .screener_referee import referee, text_of
from .screener_download import PREFIX, unpack
from .screener_fill import BALANCE_LINES, CASH_LINES, YEAR_END, parse_full

MONEY_ABS, MONEY_REL = 1.0, 0.005
EPS_ABS, EPS_REL = 0.06, 0.005
SCALE_FACTORS = (10.0, 100.0, 1000.0)
SCALE_TOLERANCE = 0.03
MIN_SHIFT_VALUE = 5.0     # a wrong-quarter match needs a figure this big (₹ Cr): small ones match by chance
SHIFT_ABS, SHIFT_REL = 1.0, 0.001
REFEREED = ("wrong_quarter", "scale", "mismatch")
SUSPECT_KINDS = ("copy_forward", "filed_before_quarter_end", "source_label_differs")
STEADY_MIN = 4
STEADY_RATIO_SPREAD = 0.02       # relative spread of theirs/ours
STEADY_DIFF_SPREAD = (2.0, 0.05)  # max spread of the difference: ₹2 Cr or 5% of its median

VIEW = "matches_screener_view:"   # a class prefix: screener's own treatment of our figure closes the gap (never stored)
# screener's Sales: revenue less the levies and discounts the parts show, every non-empty mix (screener_parts, 28 Oct 2026)
REVENUE_RULES = tuple("_".join(c) for c in screener_parts.subsets(list(screener_parts.FLOW_ORDER)))
CLASSES = ("match", "wrong_quarter", "scale", "naming", "lender_definition", "steady_line_difference",
           *(VIEW + r for r in REVENUE_RULES), VIEW + "share_adjust", VIEW + "treasury_shares", "steady_older", "mismatch")
# the six other lines: our metric names (Tax % is a ratio of two of ours)
SIX_METRICS = ("ebitda", "other_income", "finance_cost", "depreciation", "pbt", "tax_pct")
SIX_LENDER_SKIP = ("ebitda", "finance_cost")      # a lender page's Operating Profit and Interest are not these lines
SIX_ABS, SIX_REL = 0.5, 0.005                      # screener prints whole crore: half a crore, or 0.5%
TAX_PCT_ABS = 1.0                                  # screener prints whole percent
SMALL_ABS, SMALL_REL = 1.0, 0.01                   # small_gap: a mismatch of at most 1 Cr or 1% of screener's value (not a match)
SMALL_GAP_LINES = ("ebitda", "other_income", "finance_cost", "depreciation", "pbt")
TAX_PCT_SMALL_PBT, TAX_PCT_SMALL_ABS = 10.0, 1.5   # tax_follows_pbt: below 10 Cr of PBT one Cr of tax moves the % by 10 points
ASSOCIATES_OTHER_INCOME_MIN = 5.0   # crore: below it a chance match is too likely (shuffle test, 27 Oct 2026)
ASSOCIATES_MIN = 1.0                               # a share of associates' profit under 1 Cr is not a rule's gap
STEADY_OLDER_MIN, STEADY_OLDER_SPREAD, STEADY_OLDER_OFF = 3, 0.03, 0.03
STEADY_OLDER_LINES = ("revenue", *SMALL_GAP_LINES)
SIX_EXPLAINED = (VIEW + "exceptional_in_other_income", VIEW + "associates_in_pbt", VIEW + "associates_in_other_income",
                 VIEW + "financial_services_finance_cost")
SECTION_KEYS = ("pages_read", "pages_unparsed", "pages_with_balance_sheet", "pages_with_cash_flow", "compared_pages",
                "compared_with_balance_sheet", "compared_with_cash_flow", "companies_with_balance_sheet_pairs",
                "companies_with_cash_flow_pairs")
SIX_CLASSES = ("match", *SIX_EXPLAINED, "small_gap", "tax_sign_on_loss", "tax_follows_pbt", "steady_older", "mismatch")
GAP_CLASSES = ("screener_only", "memory_only")
WORKERS = 8

CSV_HEADER = ("scrip,symbol,sector,basis,period,metric,class,memory_value,screener_value,memory_source_id,"
              "memory_filed,note,table,adjustment").split(",")

# our metric names for each compared line; a lender's revenue line is its revenue from operations, a bank's interest earned
_OURS = {k: line_map.crosscheck_ours(k) for k in ("revenue", "pat", "eps")}
_LENDER_OURS = {k: line_map.crosscheck_ours(k, lender=True) for k in ("revenue", "pat", "eps")}


_SCREENER_LINE = {"revenue": "Sales", "pat": "Net Profit", "eps": "EPS"}


# --- one pair -----------------------------------------------------------------------------------------------------

def _close(ours: float, theirs: float, metric: str) -> bool:
    absolute, relative = (EPS_ABS, EPS_REL) if metric == "eps" else (MONEY_ABS, MONEY_REL)
    return abs(ours - theirs) <= max(absolute, relative * abs(ours))


VIEW_ABS, VIEW_REL = 1.5, 0.0005    # a screener view closes a gap only within 1.5 Cr or 0.05% of screener's figure


def view_close(value: float, theirs: float, metric: str = "money") -> bool:
    """Whether a view of our figure (ours plus the parts screener adds) closes the gap to screener's figure. Tighter than a plain
    match (1 Cr or 0.5%): screener prints whole crore, so the residual of a sum of parts is at most a rounding or two, and 0.5% of a
    1,50,000 Cr line (750 Cr) would let almost any part close almost any gap (review, 28 Oct 2026). An EPS view keeps the EPS
    tolerance, which is already a few paise."""
    if metric == "eps":
        return _close(value, theirs, "eps")
    return abs(value - theirs) <= max(VIEW_ABS, VIEW_REL * abs(theirs)) + 1e-9


def _view_apart(ours: float, theirs: float, metric: str = "money", plain: tuple[float, float] = (MONEY_ABS, MONEY_REL)) -> bool:
    """A view is tried only for a gap of more than twice the SMALLER of the plain-match tolerance (``plain``: 1 Cr or 0.5%) and the
    view tolerance (``view_close``: 1.5 Cr or 0.05%). On a small line that is the plain one as before; on a large line the view's:
    the older ``_apart`` (twice the plain tolerance, 1% of a line) shut views out of the gaps of 0.5% to 1% of a large line, TCS's
    netted deferred tax among them (1,205 on 1,82,372 Cr), though the closing test is tight."""
    if metric == "eps":
        return _apart(ours, theirs, "eps")
    tol = min(max(plain[0], plain[1] * abs(theirs)), max(VIEW_ABS, VIEW_REL * abs(theirs)))
    return abs(ours - theirs) > 2 * tol + 1e-9


def _apart(ours: float, theirs: float, metric: str) -> bool:
    """More than twice the match tolerance: a rule credited with a gap this wide did not match by chance."""
    absolute, relative = (EPS_ABS, EPS_REL) if metric == "eps" else (MONEY_ABS, MONEY_REL)
    return abs(ours - theirs) > 2 * max(absolute, relative * abs(theirs)) + 1e-9


def _is_scale(ours: float, theirs: float) -> bool:
    if not ours or not theirs or (ours > 0) != (theirs > 0):
        return False
    ratio = abs(theirs / ours)
    return any(abs(ratio - f) <= SCALE_TOLERANCE * f or abs(ratio - 1 / f) <= SCALE_TOLERANCE / f for f in SCALE_FACTORS)


def _neighbours(period: str) -> list[str]:
    """The quarter before and after, or the year before and after."""
    if m := re.fullmatch(r"FY(\d{2})", period):
        y = int(m[1])
        return [f"FY{y - 1:02d}", f"FY{y + 1:02d}"]
    idx = quarter_index(period)
    if idx is None:
        return []
    out = []
    for i in (idx - 1, idx + 1):
        year, q = divmod(i - 1, 4)
        out.append(f"Q{q + 1}FY{year:02d}")
    return out


def classify(ours: float, theirs: float, metric: str, shifted_to: str | None, lender: bool,
             named: str | None = None) -> str:
    """One pair's class, before the company-level steady-line rule: ``shifted_to`` names a neighbouring column whose
    value ours equals; ``named`` an alternative official line of ours that screener's value equals."""
    if _close(ours, theirs, metric):
        return "match"
    if shifted_to:
        return "wrong_quarter"
    if metric != "eps" and _is_scale(ours, theirs):
        return "scale"
    if named:
        return "naming"
    if lender and metric in ("revenue", "pat"):
        return "lender_definition"
    return "mismatch"


def _steady(pairs: list[dict]) -> bool:
    """Four or more unmatched revenue quarters of one company whose difference or ratio hardly moves."""
    usable = [p for p in pairs if p["memory_value"] and p["screener_value"]]
    if len(usable) < STEADY_MIN:
        return False
    ratios = [p["screener_value"] / p["memory_value"] for p in usable]
    if statistics.mean(ratios) and (max(ratios) - min(ratios)) <= STEADY_RATIO_SPREAD * abs(statistics.mean(ratios)):
        return True
    diffs = [p["memory_value"] - p["screener_value"] for p in usable]
    median = abs(statistics.median(diffs))
    return (max(diffs) - min(diffs)) <= max(STEADY_DIFF_SPREAD[0], STEADY_DIFF_SPREAD[1] * median)


# --- the screener view of our figures ----------------------------------------------------------------------------

def screener_view(dossier: dict | None, figures: dict, period: str, today: str | None = None) -> dict[str, tuple[float, str]]:
    """Our figures of one period as screener's documented rules print them: ``{metric: (value, rule)}``, only for a metric a
    rule changes. Pure: nothing is stored or shown on a card (memory keeps the company's own figures).

    - ``revenue``: revenue less excise duty (rule ``excise``; screener's Sales is net of it, rules row 1);
    - ``other_income``: other income plus the exceptional items (``exceptional_in_other_income``, rules row 4);
    - ``eps``: EPS divided by the factor of a share split or bonus after the period (``share_adjust``, rules row 7);
    - ``pbt``: profit before tax plus the associates' share (``associates_in_pbt``, rules row 16: our PBT is the taxonomy's,
      without the share, screener's has it);
    - ``other_income`` also: plus the associates' share (``associates_in_other_income``, rule 16), alone or together with the
      exceptional items (``screener_views`` lists every candidate; this function keeps the first);
    - ``exceptional_after_tax``: the exceptional items less their share of the tax, tax x exceptional / pbt (screener's
      support article 42), the whole item when that tax exceeds it. Shown for the record: no compared line reads it yet.
    """
    return {k: vs[0] for k, vs in screener_views(dossier, figures, period, today).items()}


def screener_views(dossier: dict | None, figures: dict, period: str, today: str | None = None) -> dict[str, list[tuple[float, str]]]:
    """``screener_view`` with every candidate view of a metric, in the order they are tried."""
    def v(name: str) -> float | None:
        return _value(figures, name, period)

    out: dict[str, list[tuple[float, str]]] = {}
    exceptional = v("exceptional_items")
    # Sales is revenue less excise duty, sales tax / VAT / GST and discounts (rules rows 1 and 2): ALL the parts found at or above
    # the floor together, the way screener's formula nets them, never the mix that fits best (a chance match). Memory's excise
    # (``excise_duty``) and the facts' (``excise_duty``, ``indirect_taxes``, ``discounts``, put in by the caller from the stored
    # XBRL facts where memory has none) are read alike.
    if v("revenue") is not None:   # not Operating Profit: ours (PBT + interest + depreciation - other income) never held it
        levies = screener_parts.usable({p: v(n) for p, n in FACT_FIGURES.items() if v(n)}, v("revenue"))
        used = [p for p in screener_parts.FLOW_ORDER if p in levies]
        if used:
            out["revenue"] = [(v("revenue") - sum(levies.values()), "_".join(used))]
    # a small exceptional item beside a few crore of gap would "explain" it by chance (blind review, 27 Oct 2026: other income
    # 10 against 7.2 with exceptional -3): the item must be at least 5 Cr and a quarter of our other income
    other = v("other_income")
    exceptional_counts = bool(exceptional) and other is not None and abs(exceptional) >= max(5.0, 0.25 * abs(other))
    if exceptional_counts:
        out["other_income"] = [(other + exceptional, "exceptional_in_other_income")]
    share = v("share_associates")
    if share is not None and abs(share) >= ASSOCIATES_MIN:
        # rules row 16: profit from associates is always other ordinary income, so screener's PBT and other income hold it
        if v("pbt") is not None:
            out["pbt"] = [(v("pbt") + share, "associates_in_pbt")]
        if other is not None:
            views = out.get("other_income", [])
            # shuffle test, run 40505771830: with a 1 Cr floor another company's share closed 6.6% as many gaps as the real
            # ones did; at 5 Cr, 3% (950 of 1,420 kept); the same floor as the exceptional-items rule
            if abs(share) >= ASSOCIATES_OTHER_INCOME_MIN:
                views.append((other + share, "associates_in_other_income"))
            if exceptional_counts:
                views.append((other + exceptional + share, "associates_in_other_income"))
            if views:   # an empty list here crashed screener_view (run 40512034352: a share under 5 Cr, no exceptional)
                out["other_income"] = views
    if exceptional:
        pbt, tax = v("pbt"), _our_tax(figures, period)
        if pbt and tax is not None:
            on_exceptional = tax * exceptional / pbt
            out["exceptional_after_tax"] = [(exceptional if abs(on_exceptional) > abs(exceptional)
                                             else exceptional - on_exceptional, "exceptional_after_tax")]
    if v("eps") is not None and dossier:
        from .screener_explain import share_factor   # screener_explain imports this module
        from .timeutil import today_ist
        factor, actions = share_factor(dossier, period, today or today_ist().isoformat())
        if actions and abs(factor - 1) > 1e-9:
            out["eps"] = [(v("eps") / factor, "share_adjust")]
    # rule P2 (docs/audit/screener-five-2026-10-28.md, reproduced to the paisa): Interest = FinanceCosts + the finance-cost row of
    # Other expenses (L&T), taken out of Expenses; so Operating Profit (Sales - Expenses, the excise cancels out) is ours plus it
    fin = v("finance_services_cost")
    if fin:
        for metric in ("finance_cost", "ebitda"):
            base = v(metric)
            if base is not None and abs(fin) >= screener_parts.floor(base):
                out[metric] = [(base + fin, "financial_services_finance_cost")]
    # EPS on total shares (rules row 13: screener divides its own profit by its own share count): the file's basic EPS is on
    # the shares outstanding without the treasury (own) shares a filer tags; with them the count is larger. Only where a count
    # is tagged (``treasury_shares``, from the facts); the share count behind the EPS is profit / EPS.
    profit = v("pat_owners") if v("pat_owners") is not None else v("pat")
    treasury = v("treasury_shares")
    if v("eps") and treasury and profit:
        shares = profit * 1e7 / v("eps")
        if shares > 0:
            out.setdefault("eps", []).append((v("eps") * shares / (shares + treasury), "treasury_shares"))
    return out


# --- the six other lines -----------------------------------------------------------------------------------------

def _six_close(ours: float, theirs: float, metric: str) -> bool:
    if metric == "tax_pct":
        return abs(ours - theirs) <= TAX_PCT_ABS + 1e-9
    return abs(ours - theirs) <= max(SIX_ABS + 1e-9, SIX_REL * abs(ours))


def _six_apart(ours: float, theirs: float, metric: str) -> bool:
    """An explanation counts only for a gap of more than twice the tolerance (screener_explain.apart's rule): within it, a
    second line can match by chance."""
    if metric != "tax_pct":
        return _view_apart(ours, theirs, "money", (SIX_ABS, SIX_REL))      # a money line's views close within ``view_close``
    return abs(ours - theirs) > 2 * TAX_PCT_ABS + 1e-9


def classify_six(metric: str, ours: float, theirs: float, figures: dict, period: str,
                 view: dict | None = None, row: dict | None = None) -> tuple[str, str]:
    """(class, note) of one pair of the six lines, in this order: a match; a gap one of screener's own rules closes (a gap of
    more than twice the tolerance; ``view`` is ``screener_views``); ``small_gap`` (a money line off by at most 1 Cr or 1%:
    counted apart, not a match); for Tax %, ``tax_sign_on_loss`` and ``tax_follows_pbt`` (``row`` is screener's quarter);
    else a mismatch."""
    if _six_close(ours, theirs, metric):
        return "match", ""
    if _six_apart(ours, theirs, metric):
        for value, rule in (view or {}).get(metric, []):
            if _six_close(value, theirs, metric) if metric == "tax_pct" else view_close(value, theirs):
                return VIEW + rule, f"screener's view of our figure: {ours:g} -> {value:g} ({rule})"
    if metric in SMALL_GAP_LINES and abs(ours - theirs) <= max(SMALL_ABS, SMALL_REL * abs(theirs)) + 1e-9:
        return "small_gap", f"{ours:g} against {theirs:g}: gap {abs(ours - theirs):.2f}"
    if metric == "tax_pct":
        return _classify_tax(theirs, figures, period, row or {})
    return "mismatch", ""


def _classify_tax(theirs: float, figures: dict, period: str, row: dict) -> tuple[str, str]:
    tax, pbt = _our_tax(figures, period), _value(figures, "pbt", period)
    if tax is None or not pbt:
        return "mismatch", ""
    signed = tax / abs(pbt) * 100        # screener divides by |pbt| (63MOONS Q4FY24: ours +110, screener -110, pbt -33)
    if abs(signed - theirs) <= TAX_PCT_ABS + 1e-9:
        return "tax_sign_on_loss", f"tax {tax:g} / |pbt {pbt:g}| = {signed:.1f}%"
    their_pbt = row.get("pbt")
    if their_pbt and not _six_close(pbt, their_pbt, "pbt"):     # the tax % gap is the PBT gap carried over
        carried = tax / abs(their_pbt) * 100
        tol = TAX_PCT_SMALL_ABS if abs(their_pbt) < TAX_PCT_SMALL_PBT else TAX_PCT_ABS
        if abs(carried - theirs) <= tol + 1e-9:
            return "tax_follows_pbt", f"tax {tax:g} / |screener pbt {their_pbt:g}| = {carried:.1f}%"
    return "mismatch", ""


def _our_tax(figures: dict, period: str) -> float | None:
    """Our tax amount as stored: the tax total, else current plus deferred tax (both must be there). Never back-derived."""
    tax = _value(figures, "tax_expense", period)
    if tax is None:
        current, deferred = _value(figures, "current_tax", period), _value(figures, "deferred_tax", period)
        if current is None or deferred is None:
            return None
        tax = current + deferred
    return tax


def _our_tax_pct(figures: dict, period: str) -> tuple[float, dict] | None:
    """Our tax over our profit before tax, in percent."""
    pbt = figures.get(("pbt", period))
    tax = _our_tax(figures, period)
    if not pbt or not pbt.get("value") or tax is None:
        return None
    return tax / pbt["value"] * 100, pbt


def _associates_way(metric: str, ours: float, theirs: float, figures: dict, period: str) -> str:
    """Which way screener treated the associates' and joint ventures' share in Other Income or PBT of one quarter: ``with`` (it
    counts the share), ``without``, ``neither`` (neither fits) or "" (no share, or one too small to tell the two ways apart: within
    twice the view tolerance). A report, not a fit: the share is counted for ITC and Tata Steel and not for L&T and Sun Pharma, the
    same way for every quarter of a company (screener-five report, rule P4); the cause is not settled."""
    share = _value(figures, "share_associates", period)
    if share is None or abs(share) <= 2 * max(VIEW_ABS, VIEW_REL * abs(theirs)):
        return ""
    base = ours + ((_value(figures, "exceptional_items", period) or 0.0) if metric == "other_income" else 0.0)
    with_, without = view_close(base + share, theirs), view_close(base, theirs)
    return "with" if with_ and not without else "without" if without and not with_ else "neither"


def six_pairs(figures: dict, quarters: dict[str, dict], lender: bool, lender_layout: bool,
              dossier: dict | None = None, get_facts=None) -> list[dict]:
    """The pairs of the six other lines, quarters only. ``get_facts(period)`` gives a file's stored XBRL facts: read only for an
    Operating Profit or Interest pair that memory alone does not settle (the finance-cost row of a financial-services business).
    Other Income and PBT pairs carry ``associates`` (``_associates_way``)."""
    out: list[dict] = []
    for period, row in quarters.items():
        for metric in SIX_METRICS:
            theirs = row.get(metric)
            if theirs is None or (metric in SIX_LENDER_SKIP and (lender or lender_layout)):
                continue
            if metric == "tax_pct":
                got = _our_tax_pct(figures, period)
                if got is None:
                    continue
                ours, entry = got
            else:
                entry = figures.get((_norm(metric), period))
                if not entry or entry.get("value") is None:
                    continue
                ours = entry["value"]
            cls, note = classify_six(metric, ours, theirs, figures, period, screener_views(dossier, figures, period), row)
            adjustment = ""
            if cls == "mismatch" and metric in ("ebitda", "finance_cost") and get_facts is not None:
                extra = facts_extra(get_facts, figures, period)
                if ("finance_services_cost", period) in extra:
                    withfacts = {**figures, **extra}
                    cls, note = classify_six(metric, ours, theirs, withfacts, period, screener_views(dossier, withfacts, period), row)
                    if cls.startswith(VIEW):
                        fin = extra[("finance_services_cost", period)]
                        note += f"; finance_services_cost {fin['value']:g} ({fin['note']})"
                        adjustment = cls[len(VIEW):] + " (xbrl facts)"
            pair = {"period": period, "metric": metric, "memory_value": ours, "screener_value": theirs, "class": cls,
                    "shifted": [], "memory_source_id": _value_source(entry), "memory_filed": entry.get("as_of") or "",
                    "note": note, "adjustment": adjustment}
            if metric in ("other_income", "pbt"):
                pair["associates"] = _associates_way(metric, ours, theirs, figures, period)
            out.append(pair)
    return out


# --- balance sheet and cash flow ---------------------------------------------------------------------------------------

# screener's ten balance-sheet lines (a bank's page adds Deposits) in the page's order, and the four cash-flow lines
BS_LINES = tuple(BALANCE_LINES)
CF_LINES = tuple(CASH_LINES)
BS_FIELD = {"equity_capital": "equity_capital_cr", "reserves": "reserves_cr", "borrowings": "gross_debt_cr", "deposits": "deposits_cr",
            "total_liabilities": "total_assets_cr",   # screener's Total Liabilities is equity plus liabilities: our total assets
            "fixed_assets": "fixed_assets_cr", "cwip": "cwip_cr", "investments": "investments_cr", "total_assets": "total_assets_cr"}
# The parts screener adds to a line (docs/bench/screener-rules.md rows 10 and 11), in the order they are tried. A part counts
# only when the stored XBRL facts show it (screener_parts.balance_parts; goodwill is also memory's own ``goodwill_cr``) and our
# figure plus it matches screener's within the tolerance: the class is then ``matches_screener_view:<line>_plus_<parts>``. A gap
# no found part closes is NEVER given a definition (independent review, 28 Oct 2026: a "definition" class with no cap hid a
# missing current-borrowings block): it is ``unexplained_larger`` when screener's figure is the larger of these four lines (the
# rule's direction), else ``mismatch``, with the state of the facts in the note.
# The formulas below are screener's own, reproduced to the paisa from the XBRL elements for five companies (docs/audit/
# screener-five-2026-10-28.md section 11.2): Borrowings = borrowings + the "Lease liabilities" rows; Net Block = PPE + investment
# property + goodwill + intangibles + right-of-use assets; CWIP + intangibles under development; Investments + equity-method
# investments. Current maturities are not in them (a row of them is not added; memory's debt lines already hold them).
BS_PARTS = {"borrowings": ("lease_liabilities",), "fixed_assets": ("investment_property", "goodwill", "intangibles", "right_of_use"),
            "cwip": ("intangibles_under_development",), "investments": ("equity_method",)}
BS_PARTS_NOT_LENDER = ("investments",)     # a lender's investments equal screener's (mapping study: 25 of 25)
BS_TOTALS = ("total_assets", "total_liabilities")   # deferred tax net: the totals lose the part of the two lines that is offset
BS_CLASSES = ("match", "wrong_period", "scale", VIEW + "net_worth_less_capital", VIEW + "goodwill_in_fixed_assets",
              VIEW + "deferred_tax_net", "derived:part_differs", "small_gap", "unexplained_larger", "mismatch")
CF_CLASSES = ("match", VIEW + "investing_plus_exchange_effect", "sign", "wrong_period", "scale", "small_gap", "mismatch")
PLUG_ABS = 3.0       # a plug is worked out from up to five rounded figures: its gap is explained within 3 Cr (or 0.5%)
BS_PLUGS = ("other_liabilities", "other_assets")     # screener's remainders: reported as information, never as an error count
PLUG_NOTE = "informational (plug): "
MEMORY_VIEWS = ("net_worth_less_capital", "goodwill_in_fixed_assets")     # views built from memory's own lines, no facts
TABLE_RESULTS, TABLE_SIX, TABLE_PERIOD, TABLE_GAP = "results", "results_six", "period_check", "gap"
TABLE_BALANCE, TABLE_CASH = "balance_sheet", "cash_flow"


def _shifted_columns(table: dict[str, dict], period: str, line: str, ours: float, theirs: float) -> list[str]:
    """Every other column of the same line that ours equals (a figure stored under the wrong period)."""
    if abs(ours) < MIN_SHIFT_VALUE or _close(ours, theirs, "money"):
        return []
    return [other for other, row in table.items()
            if other != period and row.get(line) is not None and not _close(row[line], theirs, "money")
            and abs(ours - row[line]) <= max(SHIFT_ABS, SHIFT_REL * abs(ours))]


def _shift_note(period: str, shifted: list[str]) -> str:
    note = f"memory {period} = screener's {', '.join(shifted)}"
    return note + f" (chance risk: {len(shifted)} columns match)" if len(shifted) > 1 else note


def _small(ours: float, theirs: float) -> bool:
    return abs(ours - theirs) <= max(SMALL_ABS, SMALL_REL * abs(theirs)) + 1e-9


def classify_balance(line: str, ours: float, theirs: float, shifted: list[str], views, lender: bool, period: str = "",
                     state=None) -> tuple[str, str]:
    """(class, note) of one balance-sheet pair, in this order: ``match`` (within ₹1 Cr or 0.5%); ``wrong_period`` (ours
    equals screener's figure for another date); ``scale``; for a gap of more than twice the tolerance, a view of our own figure
    that closes it (``matches_screener_view:...``: our figure plus a part the facts show, or memory's own net worth less capital
    and goodwill); ``unexplained_larger`` when no view closes a gap in the direction of screener's rule (screener's figure is the
    larger of borrowings, fixed assets, CWIP or a non-lender's investments): the note says what the facts hold, and it is never
    a definition; ``small_gap`` (at most 1 Cr or 1%); else ``mismatch``. ``views`` is a list of (value, rule) or a function
    giving it (read only for a gap that needs it: the facts file is fetched then); ``state`` a function giving the facts' state."""
    if _close(ours, theirs, "money"):
        return "match", ""
    if shifted:
        return "wrong_period", _shift_note(period, shifted)
    if _is_scale(ours, theirs):
        return "scale", ""
    if _view_apart(ours, theirs):
        for value, rule in (views() if callable(views) else views):
            if view_close(value, theirs):
                return VIEW + rule, f"screener's view of our figure: {ours:g} -> {value:g} ({rule})"
    why = ""
    if _apart(ours, theirs, "money"):
        why = state() if callable(state) else ""
        if line in BS_PARTS and theirs > ours and not (lender and line in BS_PARTS_NOT_LENDER):
            return "unexplained_larger", (f"screener {theirs:g} against ours {ours:g}: {theirs - ours:g} more on screener, "
                                          "no part found that closes it" + (f"; {why}" if why else ""))
    if _small(ours, theirs):
        return "small_gap", f"{ours:g} against {theirs:g}: gap {abs(ours - theirs):.2f}"
    return "mismatch", (why if _apart(ours, theirs, "money") else "")


def classify_cash(ours: float, theirs: float, shifted: list[str], period: str = "", views=None) -> tuple[str, str]:
    """(class, note) of one cash-flow pair: ``match``; a view of our figure that closes a gap of more than twice the tolerance
    (``views``: a list or a function giving (value, rule); rule C1: screener has no foreign-exchange line and adds the exchange-rate
    effect on cash to Cash from Investing); ``sign`` (ours is the opposite sign); ``wrong_period``; ``scale``; ``small_gap``; else
    ``mismatch``."""
    if _close(ours, theirs, "money"):
        return "match", ""
    if _view_apart(ours, theirs):
        for value, rule in (views() if callable(views) else views or []):
            if view_close(value, theirs):
                return VIEW + rule, f"screener's view of our figure: {ours:g} -> {value:g} ({rule})"
    if abs(theirs) >= MIN_SHIFT_VALUE and _close(ours, -theirs, "money"):
        return "sign", "ours has the opposite sign"
    if shifted:
        return "wrong_period", _shift_note(period, shifted)
    if _is_scale(ours, theirs):
        return "scale", ""
    if _small(ours, theirs):
        return "small_gap", f"{ours:g} against {theirs:g}: gap {abs(ours - theirs):.2f}"
    return "mismatch", ""


def _bs_ours(snap: dict, line: str) -> float | None:
    """Our figure of one balance-sheet line (before any view): the stored field; Reserves fall back on net worth less equity
    capital (an insurer's file has no other-equity line; mapping 1d)."""
    value = snap.get(BS_FIELD[line])
    if value is None and line == "reserves" and snap.get("net_worth_cr") is not None and snap.get("equity_capital_cr") is not None:
        value = snap["net_worth_cr"] - snap["equity_capital_cr"]
    return value


def _half_year(period: str, fy_end: int) -> bool:
    """A balance sheet at a date that is not the company's year end (screener's half-year column: no current maturities)."""
    end = quarter_end(period)
    return end is not None and end.month != fy_end


def _bs_views(snap: dict, line: str, ours: float | None = None, parts: dict | None = None, lender: bool = False,
              half_year: bool = False) -> list[tuple[float, str]]:
    """The views of one balance-sheet line: memory's own (reserves: net worth less capital) and, from ``parts`` (the facts'
    ``screener_parts.balance_parts``: name -> (value in crore, where read)), our figure plus each mix of the parts screener
    adds to the line (BS_PARTS; goodwill is memory's own ``goodwill_cr`` where it has it; a half-year balance sheet has no
    current maturities); the two totals less the deferred tax screener nets (assets and liabilities offset)."""
    out: list[tuple[float, str]] = []
    if line == "reserves" and snap.get("reserves_cr") is not None and None not in (snap.get("net_worth_cr"), snap.get("equity_capital_cr")):
        out.append((snap["net_worth_cr"] - snap["equity_capital_cr"], "net_worth_less_capital"))
    ours = _bs_ours(snap, line) if ours is None else ours
    if ours is None:
        return out
    order = BS_PARTS.get(line)
    if (order or line in BS_TOTALS) and callable(parts):
        parts = parts()     # read only for a line a part can change: the facts file is fetched then
    if order and not (lender and line in BS_PARTS_NOT_LENDER):
        found = {name: value for name, (value, _) in (parts or {}).items() if name in order}
        if line == "fixed_assets" and snap.get("goodwill_cr"):
            found["goodwill"] = snap["goodwill_cr"]
        out += screener_parts.additive_views(line, ours, found, order)
    # rule B2: the total is Assets less the smaller of the two deferred-tax lines in a year-end column; a half-year column is not netted
    # (TCS Sep 2026 190,782 and L&T 484,727 equal Assets)
    if line in BS_TOTALS and not half_year and parts and parts.get("dta") and parts.get("dtl"):
        net = min(parts["dta"][0], parts["dtl"][0])
        if net >= screener_parts.floor(ours):
            out.append((ours - net, "deferred_tax_net"))
    return out


def _parts_read(line: str, parts: dict) -> str:
    """The parts of a line the facts hold, with where each was read (the note of a balance-sheet view)."""
    order = BS_PARTS.get(line) or (("dta", "dtl") if line in BS_TOTALS else ())
    return "; ".join(f"{p} {parts[p][0]:g} ({parts[p][1]})" for p in order if p in parts)


def _facts_state(line: str, parts: dict | None, half_year: bool = False) -> str:
    """What the facts hold for a line's parts, for the note of an unexplained gap."""
    order = BS_PARTS.get(line) or (("dta", "dtl") if line in BS_TOTALS else ())
    if not order:
        return ""
    if parts is None:
        return "no XBRL facts stored for this date"
    found = [p for p in order if p in parts]
    if not found:
        return f"XBRL facts stored: no {'/'.join(order)} tagged"
    listed = ", ".join(f"{p} {parts[p][0]:g} ({parts[p][1]})" for p in found)
    return (f"XBRL facts stored: parts found {listed}; all applied together (those under the floor left out), "
            "they do not close the gap" + ("; a half-year column is not netted for deferred tax" if half_year and line in BS_TOTALS else ""))


def _plug_parts(snap: dict, line: str) -> dict[str, float] | None:
    """The lines screener's plug is worked out of, from memory, as the company page does it (web/src/components/company/
    statements.ts): Other Liabilities = total less equity capital, reserves, borrowings and deposits (the first three must be
    there; no deposits is 0); Other Assets = total less fixed assets, CWIP and investments (fixed assets and investments must be
    there; no CWIP is 0). None when a part is missing: a plug of a missing part would only show that part."""
    if snap.get("total_assets_cr") is None:
        return None
    if line == "other_liabilities":
        parts = {p: _bs_ours(snap, p) for p in ("equity_capital", "reserves", "borrowings")}
        if any(v is None for v in parts.values()):
            return None
        return {**parts, "deposits": snap.get("deposits_cr") or 0.0}
    if snap.get("fixed_assets_cr") is None or snap.get("investments_cr") is None:
        return None
    return {"fixed_assets": snap["fixed_assets_cr"], "cwip": snap.get("cwip_cr") or 0.0, "investments": snap["investments_cr"]}


def classify_plug(ours: float, theirs: float, our_total: float, their_total: float | None, ours_parts: dict[str, float],
                  theirs_parts: dict[str, float]) -> tuple[str, str]:
    """A plug pair: ``match``; ``derived:part_differs`` when the plug gap equals the gap of the total less the gaps of the lines
    it is worked out of (screener's plug is that identity), at least one of which differs, so the plug is no second error;
    else ``scale`` or ``mismatch``."""
    if _close(ours, theirs, "money"):
        return "match", ""
    if their_total is not None:
        differing = [p for p in ours_parts if not _close(ours_parts[p], theirs_parts[p], "money")]
        if not _close(our_total, their_total, "money"):
            differing.insert(0, "total_assets")
        carried = (our_total - their_total) - sum(ours_parts[p] - theirs_parts[p] for p in ours_parts)
        if differing and abs((ours - theirs) - carried) <= max(PLUG_ABS, MONEY_REL * abs(theirs)):
            return "derived:part_differs", "the plug differs because " + ", ".join(differing) + " differ"
    if _is_scale(ours, theirs):
        return "scale", ""
    return "mismatch", ""


def balance_pairs(snapshots: dict[str, dict], table: dict[str, dict], lender: bool, parts_for=None, fy_end: int = 3) -> list[dict]:
    """The pairs of screener's balance-sheet lines against memory's exchange-file statements (``metrics._snapshots``: results
    files only, on memory's basis), by statement date. Screener's Total Liabilities is compared with our total assets (it is
    equity plus liabilities); Other Liabilities and Other Assets are screener's plugs, worked out from our lines (informational:
    the note says so). ``parts_for(period)`` gives the date's balance-sheet parts from the stored XBRL facts
    (``screener_parts.balance_parts``) or None when no facts are stored; it is called once a date, and only for a gap that a
    part could close. ``fy_end`` is the company's year-end month: another date is a half year."""
    out: list[dict] = []
    for period, row in table.items():
        snap = snapshots.get(period)
        if not snap:
            continue
        base = {"table": TABLE_BALANCE, "period": period, "memory_source_id": str(snap.get("source_news_id") or ""),
                "memory_filed": snap.get("as_of") or "", "shifted": []}
        read: list = []

        def parts(period=period, read=read):
            if not read:
                read.append(parts_for(period) if parts_for else None)
            return read[0]

        half = _half_year(period, fy_end)
        for line in BS_LINES:
            theirs = row.get(line)
            if theirs is None or line in BS_PLUGS:
                continue
            ours = _bs_ours(snap, line)
            if ours is None:
                continue
            shifted = _shifted_columns(table, period, line, ours, theirs)
            cls, note = classify_balance(line, ours, theirs, shifted,
                                         lambda snap=snap, line=line, ours=ours: _bs_views(snap, line, ours, parts, lender, half),
                                         lender, period, lambda line=line: _facts_state(line, parts(), half))
            pair = {**base, "metric": line, "memory_value": ours, "screener_value": theirs, "class": cls, "note": note,
                    "shifted": shifted}
            if cls.startswith(VIEW) and cls[len(VIEW):] not in MEMORY_VIEWS and parts() is not None:
                pair["note"] += "; parts read from " + _parts_read(line, parts())
            if cls.startswith(VIEW):
                pair["adjustment"] = cls[len(VIEW):] + (" (memory)" if cls[len(VIEW):] in MEMORY_VIEWS else " (xbrl facts)")
            out.append(pair)
        their_total = row.get("total_assets") if row.get("total_assets") is not None else row.get("total_liabilities")
        for line in BS_PLUGS:
            theirs, plug_parts = row.get(line), _plug_parts(snap, line)
            if theirs is None or plug_parts is None:
                continue
            ours = snap["total_assets_cr"] - sum(plug_parts.values())
            cls, note = classify_plug(ours, theirs, snap["total_assets_cr"], their_total, plug_parts,
                                      {p: row.get(p) or 0.0 for p in plug_parts})
            out.append({**base, "metric": line, "memory_value": ours, "screener_value": theirs, "class": cls,
                        "note": PLUG_NOTE + note if note else PLUG_NOTE.rstrip(": ")})
    return out


def _exchange_view(facts_for, label: str, end: date | None, months: int, ours: float):
    """A function giving the views of Cash from Investing (rule C1): ours plus the exchange-rate effect on cash and cash equivalents
    of the same 12-month context, read from the stored facts only when the gap needs it. [] without facts or without the element."""
    def views():
        facts = facts_for(label) if facts_for and end is not None else None
        effect = facts.cr("EffectOfExchangeRateChangesOnCashAndCashEquivalents", end=end, months=months) if facts is not None else None
        return [(ours + effect, "investing_plus_exchange_effect")] if effect else []
    return views


CASH_ELEMENTS = {"operating_cash_flow": "CashFlowsFromUsedInOperatingActivities",
                 "investing_cash_flow": "CashFlowsFromUsedInInvestingActivities",
                 "financing_cash_flow": "CashFlowsFromUsedInFinancingActivities",
                 "net_cash_flow": "IncreaseDecreaseInCashAndCashEquivalents"}


def _year_end(key: str) -> date | None:
    """The date a "YE:2025-06" cash-flow column's year ended (the last day of the month)."""
    year, month = int(key[len(YEAR_END):][:4]), int(key[len(YEAR_END):][5:7])
    return date(year, month, calendar.monthrange(year, month)[1])


def cash_flow_pairs(figures: dict, table: dict[str, dict], facts_for=None, skipped: list | None = None) -> list[dict]:
    """The pairs of screener's cash-flow lines against the exchange file's, by the company's own year end. A March year (FY26)
    is read from memory's figures of the year. Any other year end ("YE:2025-06", screener_fill.cash_year_of) is not in memory at
    all (xbrl.period_label gives a 6-, 9- or 12-month period no label when the year does not end in March), so it is read from
    the stored XBRL facts of the file whose quarter ends at that date (``facts_for(quarter label)``, its 12-month cash-flow
    elements). A column that cannot be paired is appended to ``skipped`` with the reason, never dropped silently."""
    out: list[dict] = []
    for period, row in table.items():
        if not period.startswith(YEAR_END):
            for line, name in CASH_LINES.items():
                theirs = row.get(line)
                entry = figures.get((_norm(name), period))
                if theirs is None or not entry or entry.get("value") is None:
                    continue
                ours = entry["value"]
                shifted = _shifted_columns(table, period, line, ours, theirs)
                views = _exchange_view(facts_for, f"Q4{period}", quarter_end(f"Q4{period}"), 12, ours) if line == "investing" else None
                cls, note = classify_cash(ours, theirs, shifted, period, views)
                out.append({"table": TABLE_CASH, "period": period, "metric": line, "memory_value": ours, "screener_value": theirs,
                            "class": cls, "shifted": shifted, "memory_source_id": _value_source(entry),
                            "memory_filed": entry.get("as_of") or "", "note": note,
                            "adjustment": "investing_plus_exchange_effect (xbrl facts)" if cls.startswith(VIEW) else ""})
            continue
        end = _year_end(period)
        label = canonical_period(f"quarter ended {end:%d.%m.%Y}")
        facts = facts_for(label) if facts_for and quarter_index(label) else None
        reason = ("" if facts is not None else f"year ends {end:%b %Y}, not a quarter end" if not quarter_index(label)
                  else f"no XBRL facts stored for {label}" if facts_for else "no XBRL facts available")
        paired = 0
        for line, name in CASH_LINES.items():
            theirs = row.get(line)
            ours = facts.cr(CASH_ELEMENTS[name], end=end, months=12) if facts is not None and theirs is not None else None
            if ours is None:
                continue
            paired += 1
            shifted = _shifted_columns(table, period, line, ours, theirs)
            cls, note = classify_cash(ours, theirs, shifted, period,
                                      (lambda ours=ours: _exchange_view(lambda _: facts, label, end, 12, ours)()) if line == "investing" else None)
            out.append({"table": TABLE_CASH, "period": period, "metric": line, "memory_value": ours, "screener_value": theirs,
                        "class": cls, "shifted": shifted, "memory_source_id": f"facts:{label}", "memory_filed": "",
                        "note": (note + "; " if note else "") + f"from the file's own 12-month cash flow to {end:%d %b %Y} (memory keeps none)",
                        "adjustment": "investing_plus_exchange_effect (xbrl facts)" if cls.startswith(VIEW)
                        else "own_year_end (xbrl facts)"})
        if not paired and skipped is not None:
            skipped.append({"period": period, "reason": reason or f"the {label} file holds no 12-month cash flow to {end:%d %b %Y}"})
    return out


def steady_older(pairs: list[dict], six: list[dict]) -> None:
    """Class ``steady_older`` (27 Oct 2026, in place): of one line (revenue and the five money lines, quarters only), three or
    more consecutive quarters of mismatches whose screener/ours ratio stays within 3% of the run's median, the median off 1 by
    at least 3%, and every later quarter of that line that was compared is a match (read from the full pair list, which holds
    the matches too). The restatement pattern: screener holds a restated figure or another definition for the older quarters
    only. It needs at least two later quarters (blind review, 27 Oct 2026: one is thin evidence)."""
    for line in STEADY_OLDER_LINES:
        rows = sorted((p for p in (pairs if line == "revenue" else six) if p["metric"] == line and quarter_index(p["period"])),
                      key=lambda p: quarter_index(p["period"]))
        start = 0
        while start < len(rows):
            end = start
            while end < len(rows) and _steady_ok(rows[start:end + 1]):
                end += 1
            run = rows[start:end]
            if len(run) >= STEADY_OLDER_MIN and len(rows[end:]) >= 2 and all(p["class"] == "match" for p in rows[end:]):
                median = statistics.median(p["screener_value"] / p["memory_value"] for p in run)
                if abs(median - 1) >= STEADY_OLDER_OFF:
                    for p in run:
                        p["class"] = "steady_older"
                        p["note"] = f"screener/ours x{median:.3f} for {len(run)} quarters, every later quarter matches"
                    start = end
                    continue
            start += 1


def _steady_ok(run: list[dict]) -> bool:
    """Consecutive quarters, all unexplained mismatches of positive figures, every ratio within 3% of the run's median."""
    if any(p["class"] != "mismatch" or not p["memory_value"] or not p["screener_value"] or
           (p["memory_value"] > 0) != (p["screener_value"] > 0) for p in run):
        return False
    index = [quarter_index(p["period"]) for p in run]
    if any(b - a != 1 for a, b in zip(index, index[1:])):
        return False
    ratios = [p["screener_value"] / p["memory_value"] for p in run]
    median = statistics.median(ratios)
    return all(abs(r / median - 1) <= STEADY_OLDER_SPREAD for r in ratios)


# --- one company --------------------------------------------------------------------------------------------------

def _ours(figures: dict, lender: bool, metric: str, period: str) -> dict | None:
    for name in (_LENDER_OURS if lender else _OURS)[metric]:
        entry = figures.get((_norm(name), period))
        if entry and entry.get("value") is not None:
            # a lender template's interest earned of 0 beside no revenue is the template's filler (ICICI Prudential AMC's
            # NBFC-template file tags InterestEarned 0, its revenue is revenue from operations): "not found", never a 0
            # revenue (Tijori referee, 26 Oct 2026, F196)
            if lender and metric == "revenue" and name == "interest_earned" and not entry["value"]:
                continue
            return entry
    return None


def _value(figures: dict, name: str, period: str) -> float | None:
    entry = figures.get((_norm(name), period))
    return entry["value"] if entry and entry.get("value") is not None else None


def alternatives(figures: dict, metric: str, period: str, lender: bool) -> list[tuple[str, float]]:
    """The other official lines memory holds for this company-quarter that screener's figure may be: (label, value)."""
    def v(name: str) -> float | None:
        return _value(figures, name, period)

    out: list[tuple[str, float | None]] = []
    if metric == "revenue":
        out += [("total_income", v("total_income"))]
        if lender:
            out.append(("interest_earned", v("interest_earned")))
        if v("revenue") is not None and v("excise_duty") is not None:
            out.append(("revenue less excise_duty", v("revenue") - v("excise_duty")))
        if v("revenue") is not None and v("other_income") is not None:
            out.append(("revenue + other_income", v("revenue") + v("other_income")))
        if v("interest_earned") is not None and v("other_income") is not None:
            out.append(("interest_earned + other_income", v("interest_earned") + v("other_income")))
    elif metric == "pat":
        out += [("pat_owners", v("pat_owners")), ("pat_continuing", v("pat_continuing")), ("pat_group", v("pat_group"))]
        if v("pat_continuing") is not None and v("pat_discontinued") is not None:
            out.append(("pat_continuing + pat_discontinued", v("pat_continuing") + v("pat_discontinued")))
        if v("pat") is not None and v("pat_minority") is not None:
            out.append(("pat less pat_minority", v("pat") - v("pat_minority")))
    elif metric == "eps":
        out += [("basic_eps", v("basic_eps")), ("diluted_eps", v("diluted_eps")), ("eps", v("eps")),
                # on total profit (continuing and discontinued) or on continuing profit only: which one screener printed
                ("eps_total (on total profit)", v("eps_total")), ("eps_continuing (on continuing profit)", v("eps_continuing"))]
    return [(label, value) for label, value in out if value is not None]


def memory_suspects(figures: dict) -> list[dict]:
    """Quarters whose period label memory itself puts in doubt, with no screener involved (``figures`` is
    ``metrics._figures``' exchange-file figures on one basis):

    - ``copy_forward``: the same value (at least ₹5 Cr, to the paise) stored for two different quarters of a line;
    - ``filed_before_quarter_end``: a source filed before the quarter it carries ended (impossible);
    - ``source_label_differs``: the figure of a quarter comes from a results file the seed labelled for another quarter
      (``xbrl:res:<scrip>:<period>``; the file's own start and end dates are not stored, so this is the label's check).
    """
    out: list[dict] = []
    seen: dict[tuple[str, float], list[str]] = {}
    for (metric, period), entry in sorted(figures.items(), key=lambda kv: kv[0][1]):
        if not quarter_index(period) or entry.get("value") is None or metric not in ("revenue", "pat", "interest_earned"):
            continue
        if abs(entry["value"]) >= MIN_SHIFT_VALUE:
            seen.setdefault((metric, round(entry["value"], 2)), []).append(period)

    def row(metric: str, period: str, entry: dict, kind: str, reason: str) -> dict:
        return {"period": period, "metric": metric, "kind": kind, "memory_value": entry["value"], "screener_value": None,
                "class": "memory_period_suspect", "memory_source_id": _value_source(entry),
                "memory_filed": entry.get("as_of") or "", "note": f"{kind}: {reason}"}

    for (metric, _), periods in seen.items():
        if len(periods) > 1:
            for period in periods:
                out.append(row(metric, period, figures[(metric, period)], "copy_forward",
                               "same value stored for " + ", ".join(p for p in periods if p != period)))
    for (metric, period), entry in sorted(figures.items(), key=lambda kv: kv[0][1]):
        end = quarter_end(period) if quarter_index(period) else None
        if end is None or entry.get("value") is None:
            continue
        for src in entry.get("sources") or [{"news_id": _value_source(entry), "as_of": entry.get("as_of")}]:
            news_id, filed = str(src.get("news_id") or ""), str(src.get("as_of") or "")[:10]
            if not news_id.startswith("xbrl:"):
                continue
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", filed) and filed < end.isoformat():
                out.append(row(metric, period, entry, "filed_before_quarter_end", f"filed {filed}, quarter ends {end}"))
                break
        label = re.fullmatch(r"xbrl:res(?:-sa)?:[^:]*:(Q[1-4]FY\d{2})", _value_source(entry))
        if label and label[1] != period and metric in ("revenue", "pat", "interest_earned"):
            out.append(row(metric, period, entry, "source_label_differs", f"source file is labelled {label[1]}"))
    return out


def _file_period(period: str) -> str:
    """The results file a period is read from: a quarter's own, a year's March (Q4) file."""
    return f"Q4{period}" if period.startswith("FY") else period


def _flow_window(period: str) -> tuple[date | None, int]:
    """(end date, months) of the context a quarter (3 months) or a March year (12) is read at in a results file."""
    return quarter_end(_file_period(period)), 12 if period.startswith("FY") else 3


FACT_FIGURES = {"excise": "excise_duty", "taxes": "indirect_taxes", "discounts": "discounts"}


def facts_extra(get_facts, figures: dict, period: str) -> dict:
    """Figure-like entries for a period that memory has no line for, from the stored XBRL facts of its file: ``excise_duty``,
    ``indirect_taxes`` (sales tax, VAT, GST), ``discounts`` (each only where memory holds none: memory's own is never
    doubled), ``treasury_shares`` and the two EPS bases ``eps_total`` / ``eps_continuing``. ``{}`` when no facts are stored.
    Each entry carries ``note`` (where the facts had it) and ``from_facts``."""
    facts = get_facts(_file_period(period)) if get_facts else None
    end, months = _flow_window(period)
    if facts is None or end is None:
        return {}
    out: dict = {}
    for part, (value, where) in screener_parts.flow_parts(facts, end, months).items():
        name = FACT_FIGURES[part]
        if _value(figures, name, period) is None:
            out[(_norm(name), period)] = {"value": value, "note": where, "from_facts": True}
    fin = screener_parts.finance_services_cost(facts, end, months)
    if fin and _value(figures, "finance_services_cost", period) is None:
        out[("finance_services_cost", period)] = {"value": fin[0], "note": fin[1], "from_facts": True}
    treasury = screener_parts.treasury_shares(facts, end, months)
    if treasury:
        out[("treasury_shares", period)] = {"value": treasury[0], "note": treasury[1], "from_facts": True}
    for label, value in screener_parts.eps_variants(facts, end, months).items():
        if _value(figures, label, period) is None:
            out[(label, period)] = {"value": value, "note": "XBRL facts", "from_facts": True}
    return out


def _parts_note(extra: dict, period: str, revenue: float | None) -> str:
    """The facts' parts of a period for a note: name, value, where read, and a levy under the floor marked as left out."""
    out = []
    for (name, _), entry in sorted(extra.items(), key=lambda kv: kv[0][0]):
        if (name in FACT_FIGURES.values()) != (revenue is not None):   # levies for a revenue pair, the share parts for an EPS pair
            continue
        text = f"{name} {entry['value']:g} ({entry['note']})"
        if revenue is not None and name in FACT_FIGURES.values() and entry["value"] < screener_parts.floor(revenue):
            text += " under the floor, left out"
        out.append(text)
    return "; ".join(out)


def _view_from_facts(rule: str, extra: dict, period: str) -> bool:
    """Whether a view's parts came from the facts (any part of it is in ``extra``)."""
    if rule in ("treasury_shares", "financial_services_finance_cost"):
        tokens = ["treasury_shares" if rule == "treasury_shares" else "finance_services_cost"]
    else:
        tokens = [FACT_FIGURES[t] for t in rule.split("_") if t in FACT_FIGURES]
    return any((_norm(t), period) in extra for t in tokens)


def page_sections(pages: dict[str, dict]) -> dict:
    """What the stored pages carry (parse_full's ``sections``: the ids balance-sheet and cash-flow), per page read."""
    return {"pages": len(pages), "balance_sheet": sum(1 for p in pages.values() if (p.get("sections") or {}).get("balance_sheet")),
            "cash_flow": sum(1 for p in pages.values() if (p.get("sections") or {}).get("cash_flow"))}


def compare_company(dossier: dict, pages: dict[str, dict], scrip: str = "", symbol: str = "", facts=None) -> dict:
    """Pairs and gaps for one company. ``pages`` maps a basis to parse_full's result. ``facts(period, basis)`` gives a file's
    stored XBRL facts (xbrl_facts.Facts) or None; it is called only for a pair that a part or a year end the facts hold could
    settle, once a period. Pure otherwise."""
    basis = main_basis(dossier) if dossier else None
    out = {"scrip": scrip, "symbol": symbol, "basis": basis, "sector": (dossier or {}).get("sector")
           or (dossier or {}).get("industry") or "unknown", "pairs": [], "six_pairs": [], "bs_pairs": [], "cf_pairs": [], "gaps": [], "suspects": [],
           "skipped": None, "sections": page_sections(pages), "page_used": None, "cf_skipped": []}
    cache: dict[str, object] = {}

    def get_facts(period: str):
        if facts is None:
            return None
        if period not in cache:
            cache[period] = facts(period, basis)
        return cache[period]

    if not basis:
        out["skipped"] = "no memory basis"
        return out
    out["suspects"] = memory_suspects(_figures(dossier, basis)[0])
    page = pages.get(basis)
    if not page or page.get("basis") != basis:
        out["skipped"] = "no stored page on memory's basis"
        return out
    out["page_used"] = page_sections({basis: page})
    lender = is_lender(dossier, basis)
    figures, _ = _figures(dossier, basis)
    columns = {"quarter": page["quarters"], "year": page.get("annual") or {}}
    pairs: list[dict] = []
    for kind, table in columns.items():
        for period, theirs_row in table.items():
            for metric in ("revenue", "pat", "eps"):
                theirs = theirs_row.get(metric)
                entry = _ours(figures, lender, metric, period)
                if theirs is None or entry is None:
                    continue
                shifted = []   # every other column of the same line that ours equals
                if metric != "eps" and abs(entry["value"]) >= MIN_SHIFT_VALUE and not _close(entry["value"], theirs, metric):
                    for other, other_row in table.items():
                        other_theirs = other_row.get(metric)
                        if other != period and other_theirs is not None and not _close(other_theirs, theirs, metric) \
                                and abs(entry["value"] - other_theirs) <= max(SHIFT_ABS, SHIFT_REL * abs(entry["value"])):
                            shifted.append(other)
                shifted_to = shifted[0] if shifted else None
                named = next((label for label, alt in alternatives(figures, metric, period, lender)
                              if _close(alt, theirs, metric) and abs(alt - entry["value"]) > 1e-9), None)
                note = ""
                if shifted:
                    note = f"memory {period} = screener's {', '.join(shifted)}"
                    if len(shifted) > 1:
                        note += f" (chance risk: {len(shifted)} columns match)"
                cls = classify(entry["value"], theirs, metric, shifted_to, lender, named)
                adjustment = ""
                if cls == "mismatch" and metric in ("revenue", "eps"):   # the existing "naming" (revenue less excise) keeps its place
                    extra = facts_extra(get_facts, figures, period)      # the stored XBRL facts: only now, for a gap to settle
                    withfacts = {**figures, **extra} if extra else figures
                    if metric == "eps" and extra:
                        named = next((label for label, alt in alternatives(withfacts, metric, period, lender)
                                      if _close(alt, theirs, metric) and abs(alt - entry["value"]) > 1e-9), None)
                        if named:
                            cls = "naming"
                            adjustment = "eps_on_total_profit" if named.startswith("eps_total") else \
                                "eps_on_continuing_profit" if named.startswith("eps_continuing") else ""
                    if cls == "mismatch":
                        for value, rule in screener_views(dossier, withfacts, period).get(metric, []):
                            if view_close(value, theirs, metric) and _view_apart(entry["value"], theirs, metric):
                                cls, note = VIEW + rule, f"screener's view of our figure: {entry['value']:g} -> {value:g} ({rule})"
                                from_facts = _view_from_facts(rule, extra, period)
                                adjustment = rule + (" (xbrl facts)" if from_facts else " (memory)")
                                if from_facts:
                                    note += "; parts read from " + "; ".join(
                                        f"{FACT_FIGURES[t]} {extra[(_norm(FACT_FIGURES[t]), period)]['value']:g} "
                                        f"({extra[(_norm(FACT_FIGURES[t]), period)]['note']})"
                                        for t in rule.split("_") if t in FACT_FIGURES and (_norm(FACT_FIGURES[t]), period) in extra)
                                break
                    if cls == "mismatch" and extra:
                        note = "XBRL facts held " + _parts_note(extra, period, entry["value"] if metric == "revenue" else None) + \
                            "; all applied together, they do not close the gap"
                if cls == "naming":
                    note = f"screener {_SCREENER_LINE[metric]} = our {named}"
                pairs.append({"period": period, "metric": metric, "memory_value": entry["value"], "screener_value": theirs,
                              "class": cls, "shifted": shifted, "memory_source_id": _value_source(entry),
                              "memory_filed": entry.get("as_of") or "", "note": note, "adjustment": adjustment})
    unmatched = [p for p in pairs if p["metric"] == "revenue" and p["class"] == "mismatch"]
    if _steady(unmatched):
        for p in unmatched:
            p["class"] = "steady_line_difference"
            p["note"] = "near-constant difference or ratio across quarters"
    out["pairs"] = pairs
    out["six_pairs"] = six_pairs(figures, page["quarters"], lender, bool(page.get("lender_layout")), dossier,
                                 get_facts if facts is not None else None)
    out["associates"] = {w: sum(1 for p in out["six_pairs"] if p.get("associates") == w) for w in ("with", "without", "neither")}
    steady_older(pairs, out["six_pairs"])
    # the balance sheet and the cash flow (28 Oct 2026): counted apart, read only, never in "pairs"
    def parts_for(period: str):
        facts_of = get_facts(period)
        end = quarter_end(period)
        return screener_parts.balance_parts(facts_of, end) if facts_of is not None and end else None

    out["bs_pairs"] = balance_pairs(_snapshots(dossier, basis), page.get("balance") or {}, lender, parts_for,
                                    int(dossier.get("fy_end_month") or 3))
    out["cf_pairs"] = cash_flow_pairs(figures, page.get("cash_flow") or {}, get_facts if facts is not None else None,
                                      out["cf_skipped"])
    # gaps: a quarter of the span screener shows, one side has and the other lacks
    ours_quarters = {p for (m, p) in figures if m in ("revenue", "interest_earned", "pat") and quarter_index(p)}
    theirs_quarters = {p for p, row in page["quarters"].items() if row.get("revenue") is not None or row.get("pat") is not None}
    if theirs_quarters:
        lo, hi = min(map(quarter_index, theirs_quarters)), max(map(quarter_index, theirs_quarters))
        out["gaps"] += [{"period": p, "class": "screener_only"} for p in sorted(theirs_quarters - ours_quarters, key=quarter_index)]
        out["gaps"] += [{"period": p, "class": "memory_only"} for p in sorted(ours_quarters - theirs_quarters, key=quarter_index)
                        if lo <= quarter_index(p) <= hi]
    return out


# --- the stored pages ---------------------------------------------------------------------------------------------

def stored_pages(sink, day: str | None = None) -> tuple[dict[str, dict[str, str]], str | None]:
    """symbol -> {basis: object key}, from ``raw/screener/<day>/`` (the newest day stored when ``day`` is None; a company
    missing from that day takes its page from the newest earlier day)."""
    keys = [k for k in sink.list_objects(PREFIX) if k.endswith(".html.gz")]
    found: dict[str, dict[str, tuple[str, str]]] = {}
    for key in keys:
        m = re.fullmatch(re.escape(PREFIX) + r"(\d{4}-\d{2}-\d{2})/(.+)_([cs])\.html\.gz", key)
        if not m or (day and m[1] > day):
            continue
        basis = CONSOLIDATED if m[3] == "c" else STANDALONE
        current = found.setdefault(m[2], {}).get(basis)
        if current is None or m[1] > current[0]:
            found[m[2]][basis] = (m[1], key)
    newest = max((d for by in found.values() for d, _ in by.values()), default=None)
    return {sym: {b: k for b, (_, k) in by.items()} for sym, by in found.items()}, newest


def official_texts(sink, scrip: str, cache: dict | None = None):
    """(periods -> news ids of the company's results cards, a getter of a filing's text from the R2 text cache). The list
    comes from the query ``results_cards_company``; a Worker without it gives none, and every pair is then
    ``no_official_text``. Texts are read from the cache only: nothing is downloaded."""
    from .pipeline import text_key

    by_period: dict[str, list[str]] = {}
    try:
        for r in sink.query("results_cards_company", [scrip]):
            if r.get("period"):
                by_period.setdefault(r["period"], []).append(r["news_id"])
    except Exception:   # noqa: BLE001 - an older Worker refuses an unknown query
        pass
    cache = {} if cache is None else cache

    def text(news_id: str) -> str | None:
        if news_id not in cache:
            try:
                body = sink.get_object(text_key(news_id))
                cache[news_id] = text_of(body) if body else None
            except Exception:   # noqa: BLE001 - a damaged or missing cache file is no text
                cache[news_id] = None
        return cache[news_id]

    return by_period, text


def attach_referee(result: dict, by_period: dict[str, list[str]], text) -> None:
    """The verdict on each wrong_quarter, scale and mismatch pair of a company, from the official text of the quarter (a
    year: its Q4 filing; a wrong_quarter: also the filing of the quarter ours equals)."""
    for pair in result["pairs"]:   # the six other lines are not in "pairs": the text search is for revenue, profit and EPS
        if pair["class"] not in REFEREED:
            continue
        wanted = [pair["period"]] + list(pair.get("shifted") or [])[:1]
        wanted = [f"Q4{p}" if p.startswith("FY") else p for p in wanted]
        texts = [t for p in wanted for nid in by_period.get(p, []) if (t := text(nid))]
        pair.update({k: v for k, v in referee(pair, texts).items() if k in ("verdict", "snippet")})


def run(sink, companies: list[tuple[str, str]], day: str | None = None, workers: int = WORKERS,
        use_referee: bool = True) -> dict:
    """The cross-check over ``companies`` ((scrip, symbol) pairs): reads each dossier, its stored pages and, for the
    pairs to referee, the cached official text."""
    pages_by_symbol, newest = stored_pages(sink, day)

    def one(item: tuple[str, str]) -> dict:
        scrip, symbol = item
        dossier = sink.get_dossier(scrip)
        pages, unparsed = {}, 0
        for basis, key in (pages_by_symbol.get(symbol) or {}).items():
            blob = sink.get_object(key)
            parsed = parse_full(unpack(blob)) if blob else None
            if parsed:
                pages[basis] = parsed
            else:
                unparsed += 1

        def facts(period: str, basis: str | None):    # a company's stored XBRL facts, read only for a pair that needs them
            return xbrl_facts.load(sink, scrip, period, basis)

        result = compare_company(dossier or {}, pages, scrip, symbol, facts)
        result["pages_unparsed"] = unparsed
        if not pages_by_symbol.get(symbol):
            result["skipped"] = "no stored page"
        if use_referee and any(p["class"] in REFEREED for p in result["pairs"]):
            attach_referee(result, *official_texts(sink, scrip))
        return result

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(one, companies))
    return summarise(results, newest)


def _in_order(by_line: dict[str, dict[str, int]], order: tuple[str, ...]) -> dict[str, dict[str, int]]:
    return {line: by_line[line] for line in order if line in by_line}


def summarise(results: list[dict], pages_day: str | None = None) -> dict:
    by_class = {c: 0 for c in CLASSES}
    by_metric: dict[str, dict[str, int]] = {}
    by_sector: dict[str, dict[str, int]] = {}
    gaps = {c: 0 for c in GAP_CLASSES}
    suspects = {k: 0 for k in SUSPECT_KINDS}
    verdicts: dict[str, int] = {}
    naming: dict[str, int] = {}
    skipped: dict[str, int] = {}
    worst = []
    rows = []
    six_by_class: dict[str, dict[str, int]] = {}
    bs_by_line: dict[str, dict[str, int]] = {}
    cf_by_line: dict[str, dict[str, int]] = {}
    table_rows = []     # balance-sheet and cash-flow rows: the CSV carries them, summary["rows"] (the referees' input) does not
    sections = {k: 0 for k in SECTION_KEYS}
    associates: list[dict] = []     # per company: the quarters screener counted the associates' share in, and those it did not
    cf_skipped: dict[str, int] = {}
    cf_skipped_companies = 0

    def adjusted(p: dict) -> dict:
        """The pair with its ``adjustment`` field: the view rule applied and where its parts came from (memory or the XBRL facts)."""
        if p.get("adjustment") or not p["class"].startswith(VIEW):
            return p
        return {**p, "adjustment": p["class"][len(VIEW):] + " (memory)"}

    for r in results:
        sec, used = r.get("sections") or {}, r.get("page_used") or {}
        sections["pages_read"] += sec.get("pages", 0)
        sections["pages_unparsed"] += r.get("pages_unparsed", 0)
        sections["pages_with_balance_sheet"] += sec.get("balance_sheet", 0)
        sections["pages_with_cash_flow"] += sec.get("cash_flow", 0)
        sections["compared_pages"] += used.get("pages", 0)
        sections["compared_with_balance_sheet"] += used.get("balance_sheet", 0)
        sections["compared_with_cash_flow"] += used.get("cash_flow", 0)
        sections["companies_with_balance_sheet_pairs"] += bool(r.get("bs_pairs"))
        sections["companies_with_cash_flow_pairs"] += bool(r.get("cf_pairs"))
        way = r.get("associates") or {}
        if sum(way.values()):
            associates.append({"scrip": r["scrip"], "symbol": r["symbol"], **way, "treatment": associates_treatment(way)})
        for skip in r.get("cf_skipped", []):
            cf_skipped[skip["reason"]] = cf_skipped.get(skip["reason"], 0) + 1
        cf_skipped_companies += bool(r.get("cf_skipped"))
        if r["skipped"]:
            skipped[r["skipped"]] = skipped.get(r["skipped"], 0) + 1
        base = {"scrip": r["scrip"], "symbol": r["symbol"], "sector": r["sector"], "basis": r["basis"]}
        bad = 0
        for p in r["pairs"]:
            by_class[p["class"]] = by_class.get(p["class"], 0) + 1
            for table, key in ((by_metric, p["metric"]), (by_sector, r["sector"])):
                counts = table.setdefault(key, {c: 0 for c in CLASSES})
                counts[p["class"]] = counts.get(p["class"], 0) + 1
            if p.get("verdict"):
                verdicts[p["verdict"]] = verdicts.get(p["verdict"], 0) + 1
            if p["class"] == "naming":
                naming[p["note"]] = naming.get(p["note"], 0) + 1
            if p["class"] != "match":
                rows.append({**base, **adjusted(p), "table": TABLE_RESULTS})
                if p["class"] in ("mismatch", "scale", "wrong_quarter"):
                    bad += 1
        for p in r.get("six_pairs", []):
            six_by_class.setdefault(p["metric"], {c: 0 for c in SIX_CLASSES})[p["class"]] += 1
            if p["class"] != "match":
                rows.append({**base, **adjusted(p), "table": TABLE_SIX})
        for key, by_line, classes in (("bs_pairs", bs_by_line, BS_CLASSES), ("cf_pairs", cf_by_line, CF_CLASSES)):
            for p in r.get(key, []):
                counts = by_line.setdefault(p["metric"], {c: 0 for c in classes})
                counts[p["class"]] = counts.get(p["class"], 0) + 1
                if p["class"] != "match":
                    table_rows.append({**base, **adjusted(p)})
        for s in r.get("suspects", []):
            suspects[s["kind"]] += 1
            rows.append({**base, **s, "table": TABLE_PERIOD})
        for g in r["gaps"]:
            gaps[g["class"]] += 1
            rows.append({**base, "period": g["period"], "metric": "", "class": g["class"], "memory_value": None,
                         "screener_value": None, "memory_source_id": "", "memory_filed": "", "note": "", "table": TABLE_GAP})
        if bad or r.get("suspects"):
            worst.append({"scrip": r["scrip"], "symbol": r["symbol"], "sector": r["sector"],
                          "wrong_pairs": bad + len(r.get("suspects", [])), "pairs": len(r["pairs"])})
    worst.sort(key=lambda w: (-w["wrong_pairs"], w["symbol"]))
    total = sum(by_class.values())
    return {"pages_day": pages_day, "companies": len(results), "companies_compared": sum(1 for r in results if not r["skipped"]),
            "skipped": skipped, "pairs": total, "by_class": by_class, "by_metric": by_metric, "by_sector": by_sector,
            "six_pairs": sum(sum(row.values()) for row in six_by_class.values()), "six_by_class": six_by_class,
            "bs_pairs": sum(sum(row.values()) for row in bs_by_line.values()), "bs_by_line": _in_order(bs_by_line, BS_LINES),
            "cf_pairs": sum(sum(row.values()) for row in cf_by_line.values()), "cf_by_line": _in_order(cf_by_line, CF_LINES),
            "associates": {"companies": associates,
                           **{k: [a["symbol"] for a in associates if a["treatment"] == k] for k in ASSOCIATES_TREATMENTS}},
            "sections": sections, "cf_skipped": {"columns": sum(cf_skipped.values()), "companies": cf_skipped_companies,
                                                  "by_reason": cf_skipped},
            "gaps": gaps, "memory_period_suspect": suspects, "verdicts": verdicts, "naming": naming,
            "worst_companies": worst[:25], "rows": rows, "table_rows": table_rows}


# --- the output ---------------------------------------------------------------------------------------------------

def _cell(v) -> str:
    return "" if v is None else f"{v:g}" if isinstance(v, float) else str(v)


def to_csv(summary: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for r in [*summary["rows"], *summary.get("table_rows", [])]:   # the ``table`` field says which table a row is from
        writer.writerow([_cell(r.get(k)) for k in CSV_HEADER])
    return buffer.getvalue()


REFEREE_HEADER = ("scrip,symbol,period,metric,class,ours,screener,verdict,official_hits").split(",")


def to_referee_csv(summary: dict) -> str:
    """referee.csv: every refereed pair, with the official line each value was found on and the verdict; the
    ``no_official_text`` ones are the list a later step fetches."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(REFEREE_HEADER)
    for r in summary["rows"]:
        if r.get("verdict"):
            writer.writerow([_cell(r["scrip"]), _cell(r["symbol"]), r["period"], r["metric"], r["class"],
                             _cell(r["memory_value"]), _cell(r["screener_value"]), r["verdict"], r.get("snippet", "")])
    return buffer.getvalue()


def to_json(summary: dict) -> str:
    return json.dumps({k: v for k, v in summary.items() if k not in ("rows", "table_rows")}, ensure_ascii=False, indent=1) + "\n"


ASSOCIATES_TREATMENTS = ("counted", "not counted", "mixed", "unclear")


def associates_treatment(way: dict) -> str:
    """How screener treated the associates' share over a company's quarters: ``counted`` (in Other Income and PBT, in every quarter
    that could tell), ``not counted``, ``mixed`` or ``unclear`` (only quarters where neither way fits)."""
    with_, without = way.get("with", 0), way.get("without", 0)
    return "mixed" if with_ and without else "counted" if with_ else "not counted" if without else "unclear"


def associates_lines(summary: dict) -> list[str]:
    """The associates' share as a named alternative, reported and not fitted: which way each company matches, quarter by quarter."""
    a = summary.get("associates") or {"companies": [], **{k: [] for k in ASSOCIATES_TREATMENTS}}
    lines = ["associates' share in Other Income and PBT (a named alternative, reported, never fitted; quarters whose share is within "
             f"twice the tolerance are left out): {len(a['companies'])} companies"]
    for k in ASSOCIATES_TREATMENTS:
        if a.get(k):
            lines.append(f"  {k:12}{len(a[k])}: " + ", ".join(a[k][:40]) + (" ..." if len(a[k]) > 40 else ""))
    for c in a["companies"][:40]:
        lines.append(f"    {c['symbol']:14}counted in {c['with']} quarters, not counted in {c['without']}, neither fits in {c['neither']}")
    return lines


def _line_label(line: str) -> str:
    return f"{line} (plug: informational)" if line in BS_PLUGS else line


def _columns(by_line: dict, classes: tuple[str, ...]) -> tuple[str, ...]:
    """The class columns of a per-line table: the fixed ones, then any other class the run found (a view's name carries the
    parts it used, so the set is open)."""
    return (*classes, *sorted({k for row in by_line.values() for k, n in row.items() if n and k not in classes}))


def sections_lines(summary: dict) -> list[str]:
    """How many stored pages carry the balance-sheet and cash-flow sections and how many were compared, with a warning in
    words when a section is missing: shown always, also at 0 (independent review, 28 Oct 2026: a missing section must be loud)."""
    sec = {**{k: 0 for k in SECTION_KEYS}, **(summary.get("sections") or {})}
    skipped = summary.get("cf_skipped") or {"columns": 0, "companies": 0, "by_reason": {}}
    lines = [f"stored pages read            {sec['pages_read']} ({sec['pages_unparsed']} could not be parsed)",
             f"  with id=balance-sheet      {sec['pages_with_balance_sheet']} of {sec['pages_read']}",
             f"  with id=cash-flow          {sec['pages_with_cash_flow']} of {sec['pages_read']}",
             f"pages compared (memory's basis) {sec['compared_pages']}",
             f"  with id=balance-sheet      {sec['compared_with_balance_sheet']} of {sec['compared_pages']}; "
             f"companies with balance-sheet pairs {sec['companies_with_balance_sheet_pairs']}",
             f"  with id=cash-flow          {sec['compared_with_cash_flow']} of {sec['compared_pages']}; "
             f"companies with cash-flow pairs {sec['companies_with_cash_flow_pairs']}",
             f"cash-flow columns not paired {skipped['columns']} ({skipped['companies']} companies)"]
    lines += [f"  {n:4}  {reason}" for reason, n in sorted(skipped["by_reason"].items(), key=lambda kv: -kv[1])]
    if not sec["pages_read"]:
        lines.append("WARNING: no stored page was read: nothing was compared")
    else:
        for name, key, pairs in (("balance-sheet", "pages_with_balance_sheet", "companies_with_balance_sheet_pairs"),
                                 ("cash-flow", "pages_with_cash_flow", "companies_with_cash_flow_pairs")):
            if not sec[key]:
                lines.append(f'WARNING: NO stored page carries id="{name}": the {name} was not compared at all '
                             "(the download or the page layout lacks the section)")
            elif not sec[pairs]:
                lines.append(f'WARNING: pages carry id="{name}" but no {name} pair was made (no column read, or no figure of '
                             "ours to set against it)")
    return lines


def render(summary: dict) -> str:
    c, g = summary["by_class"], summary["gaps"]
    lines = [f"screener cross-check (pages of {summary['pages_day']}, read only):",
             f"companies                    {summary['companies']}",
             f"compared                     {summary['companies_compared']}",
             f"pairs compared               {summary['pairs']}"]
    lines += [f"  {name:26}{c[name]}" for name in CLASSES]
    lines += [f"  {name:26}{n}" for name, n in sorted(c.items()) if name not in CLASSES and n]
    lines += sections_lines(summary)
    lines += associates_lines(summary)
    if summary.get("six_by_class"):
        lines += [f"six other lines, pairs       {summary['six_pairs']}"]
        for metric, row in sorted(summary["six_by_class"].items()):
            lines += [f"  {metric:16}" + "  ".join(f"{k} {n}" for k, n in row.items() if n)]
    for title, total, by_line in (("balance sheet", summary.get("bs_pairs", 0), summary.get("bs_by_line")),
                                  ("cash flow", summary.get("cf_pairs", 0), summary.get("cf_by_line"))):
        if by_line:
            lines += [f"{title}, pairs               {total}"]
            for line, row in by_line.items():
                lines += [f"  {_line_label(line):38}" + "  ".join(f"{k} {n}" for k, n in row.items() if n)]
    lines += [f"memory_period_suspect        {sum(summary['memory_period_suspect'].values())}"]
    lines += [f"  {k:26}{v}" for k, v in summary["memory_period_suspect"].items()]
    lines += ["referee verdicts:"] + [f"  {k:34}{v}" for k, v in sorted(summary["verdicts"].items())]
    lines += [f"quarters screener only       {g['screener_only']}", f"quarters memory only         {g['memory_only']}"]
    if summary["skipped"]:
        lines.append("companies skipped: " + ", ".join(f"{k} {v}" for k, v in sorted(summary["skipped"].items())))
    return "\n".join(lines)


def _table(rows: list[dict], limit: int = 15) -> list[str]:
    out = ["| Symbol | Period | Metric | Ours | Screener | Verdict | Note |", "|---|---|---|---|---|---|---|"]
    out += [f"| {r['symbol']} | {r['period']} | {r['metric']} | {_cell(r['memory_value'])} | {_cell(r['screener_value'])} | "
            f"{r.get('verdict', '')} | {r.get('note', '')} |" for r in rows[:limit]]
    return out + [""]


def to_markdown(summary: dict, date: str) -> str:
    """The short report, filled from the summary (``docs/audit/screener-crosscheck-<date>.md``); the owner's reading and
    the class fixes are written by hand after it. It leads with what is wrong with us, then screener's errors, then
    naming."""
    c, g, v = summary["by_class"], summary["gaps"], summary["verdicts"]
    total = summary["pairs"] or 1
    rows = summary["rows"]
    wrong_quarter = [r for r in rows if r["class"] == "wrong_quarter"]
    suspect = [r for r in rows if r["class"] == "memory_period_suspect"]
    ours_wrong = [r for r in rows if r.get("verdict") == "screener_matches_official"]
    screener_wrong = [r for r in rows if r.get("verdict") == "ours_matches_official"]
    out = [f"# Screener cross-check, {date}", "",
           f"Read only: memory's exchange-file figures against the screener.in pages downloaded on {summary['pages_day']} "
           f"(F163, TODO 50), the official filing as referee where the cached text allows. {summary['companies_compared']} of "
           f"{summary['companies']} companies compared, {summary['pairs']} pairs (quarters and years; revenue, profit, EPS).", "",
           "## What is wrong with us", "",
           f"- Official filing agrees with screener, not with us: {len(ours_wrong)} pairs.",
           f"- wrong_quarter (our figure equals screener's figure for another period): {c['wrong_quarter']} pairs.",
           f"- memory_period_suspect (memory's own period checks): {sum(summary['memory_period_suspect'].values())} "
           + "(" + ", ".join(f"{k} {n}" for k, n in summary["memory_period_suspect"].items()) + ").", "",
           "### Official filing agrees with screener", ""] + _table(ours_wrong)
    out += ["### wrong_quarter", ""] + _table(wrong_quarter)
    says = {k: n for k, n in v.items() if k.startswith("official_says_")}
    if says:
        out += ["Where the official text says the figure belongs: " + ", ".join(f"{k[14:]} {n}" for k, n in sorted(says.items())) + ".", ""]
    out += ["### memory_period_suspect", "", "| Symbol | Period | Metric | Value | Reason |", "|---|---|---|---|---|"]
    out += [f"| {r['symbol']} | {r['period']} | {r['metric']} | {_cell(r['memory_value'])} | {r['note']} |" for r in suspect[:15]]
    out += ["", "## Screener errors (the official filing agrees with us)", "",
            f"{len(screener_wrong)} pairs.", ""] + _table(screener_wrong)
    out += ["## Naming (screener equals another official line of ours)", "", f"{c['naming']} pairs.", ""]
    out += [f"- {note}: {n}" for note, n in sorted(summary["naming"].items(), key=lambda kv: -kv[1])[:15]] + [""]
    out += ["## Sections found on the stored pages", "",
            "The balance sheet and the cash flow are read from the page sections `id=\"balance-sheet\"` and `id=\"cash-flow\"`. "
            "A missing section is not a clean result: no pair was made.", "", "```", *sections_lines(summary), "```", ""]
    out += ["## The associates' share (Other Income and PBT)", "",
            "Screener counts the share of associates and joint ventures in Other Income and PBT for some companies and not for others, the "
            "same way in every quarter of a company (docs/audit/screener-five-2026-10-28.md, rule P4; the cause is not settled). It is "
            "reported here as a named alternative, never used to make a gap fit.", "", "```", *associates_lines(summary), "```", ""]
    out += ["## Not settled", "", f"- both_match (two different lines): {v.get('both_match', 0)}",
            f"- neither: {v.get('neither', 0)}",
            f"- no_official_text: {v.get('no_official_text', 0)} (listed in referee.csv, for a later step to fetch)", "",
            "## Counts by class", "", "| Class | Pairs | Share |", "|---|---|---|"]
    out += [f"| {name} | {c[name]} | {100 * c[name] / total:.1f}% |" for name in CLASSES]
    out += ["", f"Quarters on screener that memory lacks: {g['screener_only']}. Quarters in memory that screener lacks "
                f"(inside screener's span): {g['memory_only']}.", ""]
    if summary["skipped"]:
        out += ["Companies not compared: " + ", ".join(f"{k} {n}" for k, n in sorted(summary["skipped"].items())) + ".", ""]
    out += ["## By metric", "", "| Metric | " + " | ".join(CLASSES) + " |", "|---|" + "---|" * len(CLASSES)]
    out += [f"| {m} | " + " | ".join(str(row[k]) for k in CLASSES) + " |" for m, row in sorted(summary["by_metric"].items())]
    if summary.get("six_by_class"):
        out += ["", "## The six other lines (quarters; Operating Profit, Other Income, Interest, Depreciation, Profit before tax, "
                    "Tax %)", "", f"{summary['six_pairs']} pairs, counted apart from the table above. Explained: screener's "
                    "own rules close the gap (docs/bench/screener-rules.md).", "",
                "| Metric | " + " | ".join(SIX_CLASSES) + " |", "|---|" + "---|" * len(SIX_CLASSES)]
        out += [f"| {m} | " + " | ".join(str(row[k]) for k in SIX_CLASSES) + " |"
                for m, row in sorted(summary["six_by_class"].items())]
    for title, total, by_line, classes, intro in (
            ("The balance sheet (screener's lines, March year ends and the latest half year)", summary.get("bs_pairs", 0),
             summary.get("bs_by_line"), BS_CLASSES,
             "Compared on memory's basis with the exchange file's statement of assets and liabilities, within 1 Cr or 0.5%. "
             "Total Liabilities is compared with our total assets (it is equity plus liabilities); Other Liabilities and Other "
             "Assets are screener's plugs worked out from our lines: informational, not an error count. A "
             "`matches_screener_view:` class names a part the stored XBRL facts show and screener adds (docs/bench/screener-rules.md "
             "rows 10 and 11: lease liabilities and current maturities in borrowings, goodwill, intangibles and right-of-use assets in "
             "fixed assets, intangibles under development in CWIP, deferred tax netted off the totals); a gap no found part closes is "
             "never named a definition: `unexplained_larger` (screener's figure the larger) or `mismatch`."),
            ("The cash flow (years)", summary.get("cf_pairs", 0), summary.get("cf_by_line"), CF_CLASSES,
             "Operating, investing, financing and net cash flow of March years against the exchange file's figures.")):
        if by_line:
            classes = _columns(by_line, classes)
            out += ["", f"## {title}", "", f"{total} pairs, counted apart from the tables above. {intro}", "",
                    "| Line | Pairs | " + " | ".join(classes) + " |", "|---|---|" + "---|" * len(classes)]
            out += [f"| {_line_label(line)} | {sum(row.values())} | " + " | ".join(str(row.get(k, 0)) for k in classes) + " |"
                    for line, row in by_line.items()]
    out += ["", "## Sectors with the most unexplained pairs (mismatch, scale, wrong_quarter)", "",
            "| Sector | Pairs | Wrong |", "|---|---|---|"]
    sectors = sorted(summary["by_sector"].items(),
                     key=lambda kv: -(kv[1]["mismatch"] + kv[1]["scale"] + kv[1]["wrong_quarter"]))[:10]
    out += [f"| {s} | {sum(row.values())} | {row['mismatch'] + row['scale'] + row['wrong_quarter']} |" for s, row in sectors]
    out += ["", "## Worst companies", "", "| Symbol | Sector | Wrong pairs | Pairs |", "|---|---|---|---|"]
    out += [f"| {w['symbol']} | {w['sector']} | {w['wrong_pairs']} | {w['pairs']} |" for w in summary["worst_companies"][:15]]
    out += ["", "Every non-match pair, with both values, memory's source id and filed date, is in the CSV artifact; the "
                "refereed pairs, with the official line, in referee.csv.", "",
            "## Reading (to be written)", "", "- Classes found, and which are screener's (not ours):", "- Fixes, one class each:", ""]
    return "\n".join(out)
