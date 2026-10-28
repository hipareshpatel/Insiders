"""The parts of screener's treatment that memory has no line for, read from the stored full facts of a results file
(xbrl_facts.py; owner, 28 Oct 2026: "adjust our numbers as per screener's treatment"). Pure: facts in, parts out.

Screener's rules (docs/bench/screener-rules.md rows 1, 2, 10, 11; docs/design/screener-mapping.md 1a and 1d):

- Sales = revenue from operations less excise duty, sales tax, VAT (GST too: the same kind of levy) and discounts;
- Borrowings = long term + short term + current maturities + lease liabilities (a half-year balance sheet has no current maturities);
- Fixed Assets = property, plant and equipment + goodwill + intangibles + right-of-use assets, CWIP apart;
- deferred tax is shown net (assets and liabilities offset, so both totals are smaller by the amount offset);
- EPS on total shares (treasury shares counted) and on total profit against continuing profit.

The formulas below are the ones docs/audit/screener-five-2026-10-28.md (sections 4 and 11.2) reproduces to the paisa for TCS, Sun
Pharma, L&T, Tata Steel and ITC; in crore. Sales = revenue - the Excise Duty row. Interest = FinanceCosts + the finance-cost row of a
financial-services business (L&T); Expenses and Operating Profit leave it out. Borrowings = borrowings + the "Lease liabilities" rows.
Total = Assets - min(DTA, DTL) in a year-end column (not in a half-year one). Net Block = PPE + investment property + goodwill +
intangibles + right-of-use assets. CWIP + intangibles under development. Investments + equity-method investments. Cash from Investing
+ the exchange-rate effect on cash.

An adjustment is offered only for a part the facts show, never for a gap alone. Which element carries a part is not the same for
every filer, and the integrated taxonomy (config/xbrl_sums, read 28 Oct 2026: INDAS, NBFC, BANKING) has NO element for excise
duty, sales tax, VAT, GST, discounts, lease liabilities, right-of-use assets, current maturities or treasury shares. A filer
can still show such a line in two ways, and both are read here. Measured by the lead on BPCL Q2FY27 (the NSE and the BSE file
are identical, 28 Oct 2026): excise duty IS in the integrated file, as a breakdown row of ``OtherExpenses`` (axis
``in-capmkt:DetailsOfOtherExpensesAxis``, member ``OtherExpenses1Member``, ``DescriptionOfOtherExpenses`` "Excise Duty", 8,737.53 Cr;
the 18,201.41 Cr total of ``OtherExpenses`` includes it), and screener's Sales 1,49,080 = 1,57,817.93 - 8,737.53. The other levies, leases
and treasury shares are still an assumption (not yet seen on a real file; ``xbrl_facts.interesting`` lists what a file has):

1. an element of its own name (a filer's extension, or the older taxonomies' ``ExciseDuty``);
2. a line of a breakdown: the taxonomy lets a filer split Other expenses (and the other-liabilities lines) into rows, each a
   dimensional fact with a ``DescriptionOf...`` text ("Excise duty"; fixture nse_old_titan_q2fy24.xml has it for Other expenses).

Each part comes with a note saying where it was read, so the CSV can say which adjustment was applied and from what."""

from __future__ import annotations

import itertools
import re
from datetime import date

from .xbrl_facts import Facts

# --- patterns ---------------------------------------------------------------------------------------------------

EXPENSE_PARENTS = ("OtherExpenses", "Expenses")
# the lines a lease or a current maturity can be a row of, outside the borrowings lines themselves (a row inside
# BorrowingsCurrent / BorrowingsNoncurrent is already in memory's gross debt)
LIABILITY_PARENTS = ("OtherNoncurrentFinancialLiabilities", "OtherCurrentFinancialLiabilities", "NoncurrentFinancialLiabilities",
                     "CurrentFinancialLiabilities", "OtherNoncurrentLiabilities", "OtherCurrentLiabilities")
FLOW_PARTS = {   # part -> (element name regex, breakdown row description regex)
    "excise": (r"^ExciseDuty", r"^\s*excise"),
    "taxes": (r"^(SalesTax|ValueAddedTax|Vat|GoodsAndServicesTax|Gst)(?![a-z])",
              r"^\s*(sales tax|vat\b|value added tax|gst\b|goods (and|&) services tax)"),
    "discounts": (r"^(TradeDiscounts?|SalesDiscounts?|Discounts?|Rebates?)(?![a-z])", r"^\s*(trade )?(discount|rebate)s?\b"),
}
FLOW_ORDER = ("excise", "taxes", "discounts")
# L&T files the finance cost of its financial-services business as a row of Other expenses; screener moves it from Expenses to
# Interest (docs/audit/screener-five-2026-10-28.md, rule P2, reproduced to the paisa: Q1FY26 781.61 + 1,706.35 = 2,487.96)
# Grasim files the same row as "Finance Cost relating to NBFC/HFC's Business" (Q1FY26 2,734.5 Cr; screener's Interest 816.2 + 2,734.5 =
# 3,550.71 and Expenses 31,295.82, both exact, owner's Excel, measured 28 Oct 2026)
FINANCE_MEMBER = (r"^\s*finance costs?\b.{0,30}\b(of|relating to|in respect of|for)\b.{0,20}"
                  r"(financial[- ]services|nbfc|hfc|lending|housing finance|financing business)")
# the other lines a row of a breakdown can be: right-of-use assets are a row of Other non-current assets (rule B3, ITC 501.00 Cr)
ASSET_PARENTS = ("OtherNoncurrentAssets",)
# a lease line is a lease-liability element, or a current maturity OF a lease (a current lease liability, never a maturity of
# borrowings); a payment, interest, expense or undiscounted amount is no balance
LEASE_ELEMENT = r"LeaseLiabilit|Maturit\w*Lease"
# a payment, interest, expense or undiscounted amount is no balance, and neither is a maturity analysis (LeaseLiabilitiesMaturity...,
# LeaseLiabilitiesMaturityAnalysis...); the current-maturity form (CurrentMaturitiesOfLeaseLiabilities) is a balance and stays
LEASE_NOT = r"Payments|Interest|Expense|Proceeds|Adjustments|Undiscounted|Maturity|LeaseLiabilit\w*Maturit"
# a part counts only above a floor: a sliver of a line is how a chance match is made (independent review, 28 Oct 2026)
PART_FLOOR_ABS, PART_FLOOR_REL = 1.0, 0.002     # 1 Cr and 0.2% of the line it would be added to


def floor(base: float) -> float:
    return max(PART_FLOOR_ABS, PART_FLOOR_REL * abs(base))


def usable(parts: dict[str, float], base: float) -> dict[str, float]:
    """The parts at or above the floor of the line they would be added to."""
    return {name: value for name, value in parts.items() if value and abs(value) >= floor(base)}


# --- reading ----------------------------------------------------------------------------------------------------

def _sum(found: list[tuple], where: str) -> tuple[float, str] | None:
    if not found:
        return None
    return sum(row[-1] for row in found), where + ": " + "; ".join(
        (f"{row[0]} {row[1]}" if len(row) == 3 else row[0]) for row in found)


def flow_parts(facts: Facts, end: date, months: int) -> dict[str, tuple[float, str]]:
    """The levies and discounts of one results period (a 3-, 6-, 9- or 12-month context ending ``end``), in crore, each with
    where it was read: ``excise``, ``taxes`` (sales tax, VAT, GST) and ``discounts``. A part the facts do not show is absent.
    A part is its tagged element, else the rows of a breakdown of other expenses, never both for the same item."""
    out: dict[str, tuple[float, str]] = {}
    for part, (name_rx, desc_rx) in FLOW_PARTS.items():
        got = _sum(facts.find(name_rx, end=end, months=months), "element")
        got = got or _sum(facts.described(EXPENSE_PARENTS, desc_rx, end=end, months=months), "breakdown row")
        if got:
            out[part] = got
    return out


def finance_services_cost(facts: Facts, end: date, months: int) -> tuple[float, str] | None:
    """The finance cost of a financial-services business a company files as a row of Other expenses (L&T), in crore: screener's
    Interest holds it (``FinanceCosts`` + this) and its Expenses and Operating Profit leave it out. None when the file has no
    such row."""
    return _sum(facts.described(EXPENSE_PARENTS, FINANCE_MEMBER, end=end, months=months), "breakdown row")


def _side(name: str) -> str:
    """Which side of the balance sheet an element name is on: noncurrent, current, or total (neither word)."""
    lower = name.lower()
    return "noncurrent" if "noncurrent" in lower or "non-current" in lower else "current" if "current" in lower else "total"


def lease_liabilities(facts: Facts, instant: date) -> tuple[float, str] | None:
    """Lease liabilities at a date, each item once: one total element if the file has one; else the current plus the
    non-current element (the first of each: a current maturity of a lease is a current lease liability, and with a total it is
    inside it); else, only when no element at all, the rows of a breakdown described "lease liabilities". Never a total plus its
    parts, never an element plus rows for the same item."""
    cands = [(n, v) for n, v in facts.find(LEASE_ELEMENT, instant=instant) if not re.search(LEASE_NOT, n, re.I)]
    if cands:
        by_side: dict[str, tuple[str, float]] = {}
        for name, value in cands:
            by_side.setdefault(_side(name), (name, value))
        if "total" in by_side:
            name, value = by_side["total"]
            return value, f"element: {name}"
        chosen = [by_side[k] for k in ("noncurrent", "current") if k in by_side]
        return sum(v for _, v in chosen), "element: " + ", ".join(n for n, _ in chosen)
    return _sum(facts.described(LIABILITY_PARENTS, r"lease liabilit", instant=instant), "breakdown row")


def current_maturities(facts: Facts, instant: date) -> tuple[float, str] | None:
    """Current maturities of long-term borrowings at a date, never of a lease (those are in ``lease_liabilities``): the first
    element named so, else (only with no element) the rows of a breakdown described "current maturities"."""
    cands = [(n, v) for n, v in facts.find(r"CurrentMaturit", instant=instant) if not re.search(r"lease", n, re.I)]
    if cands:
        return cands[0][1], f"element: {cands[0][0]}"
    rows = [r for r in facts.described(LIABILITY_PARENTS, r"current maturit", instant=instant) if not re.search(r"lease", r[1], re.I)]
    return _sum(rows, "breakdown row")


def balance_parts(facts: Facts, instant: date) -> dict[str, tuple[float, str]]:
    """The balance-sheet parts screener adds at one date (crore, each with where it was read): ``lease_liabilities``,
    ``current_maturities``, ``intangibles``, ``right_of_use``, ``intangibles_under_development``, ``equity_method``,
    ``investment_property``, ``other_financial_assets``, and the two deferred-tax lines (``dta``, ``dtl``). Each item is read
    once (see ``lease_liabilities``). Right-of-use assets: a row "Right-of-use assets" of Other non-current assets (rule B3: a row
    of that line is outside property, plant and equipment by construction), else a separate right-of-use element with property,
    plant and equipment tagged apart; never a row of any other line (it could sit inside PPE)."""
    at = {"instant": instant}
    out: dict[str, tuple[float, str]] = {}

    def one(part: str, *names: str) -> None:
        found = [(n, v) for n in names if (v := facts.cr(n, **at)) is not None]
        if found:
            out[part] = (sum(v for _, v in found), "element: " + ", ".join(n for n, _ in found))

    for part, got in (("lease_liabilities", lease_liabilities(facts, instant)), ("current_maturities", current_maturities(facts, instant))):
        if got:
            out[part] = got
    one("intangibles", "OtherIntangibleAssets")
    one("goodwill", "Goodwill")
    rou = _sum(facts.find(r"RightOfUse", **at), "element")
    if rou and facts.cr("PropertyPlantAndEquipment", **at) is not None:
        out["right_of_use"] = rou
    elif not rou:
        rows = _sum(facts.described(ASSET_PARENTS, r"^\s*right.of.use", **at), "breakdown row")
        if rows:
            out["right_of_use"] = rows
    one("intangibles_under_development", "IntangibleAssetsUnderDevelopment")
    one("equity_method", "InvestmentsAccountedForUsingEquityMethod")
    one("investment_property", "InvestmentProperty")
    one("other_financial_assets", "OtherNoncurrentFinancialAssets", "OtherCurrentFinancialAssets")
    one("dta", "DeferredTaxAssetsNet")
    one("dtl", "DeferredTaxLiabilitiesNet")
    return out


def treasury_shares(facts: Facts, end: date, months: int) -> tuple[float, str] | None:
    """A tagged count of treasury (own) shares at the period, in shares. Looked for by element name (unit: shares), the
    taxonomy having none: an extension, or a line of a breakdown."""
    found = [(n, v) for n, v in facts.find(r"Treasury|OwnShares|SharesHeldByTrust|EsopTrust", end=end, months=months, money=False)
             if v and facts.units.get(_unit_of(facts, n), "") == "SHARES"]
    return _sum(found, "element") if found else None


def _unit_of(facts: Facts, name: str) -> str:
    return next((row[2] or "" for row in facts.rows if row[0] == name), "")


EPS_ELEMENTS = {"eps_total": "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                "eps_continuing": "BasicEarningsLossPerShareFromContinuingOperations"}


def eps_variants(facts: Facts, end: date, months: int) -> dict[str, float]:
    """Basic EPS on total profit (continuing and discontinued) and on continuing profit, as the file states them."""
    out = {}
    for label, name in EPS_ELEMENTS.items():
        value = facts.get(name, end=end, months=months)
        if value is not None:
            out[label] = float(value)
    return out


# --- the annual columns -----------------------------------------------------------------------------------------------

ANNUAL_EPS = ("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", "BasicEarningsLossPerShare")
ASSOCIATES_ELEMENT = "ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod"


def year_figures(facts: Facts, end: date, months: int = 12) -> dict[str, tuple[float, str]]:
    """Screener's annual profit and loss lines from one year's facts by the formulas reproduced to the paisa (docs/audit/
    screener-five-2026-10-28.md, 11.2; ITC FY26: Sales 89,913.33 - 11,044.93 = 78,868.40), in crore, each with the elements it was
    worked out from; a line whose elements the file lacks is absent. The facts are an annual report's own XBRL (an Ind AS file, with
    its 12-month contexts) or the Q4 integrated results file's 12-month figures:

    - ``revenue`` (Sales) = RevenueFromOperations - the Excise Duty (element or row; any other levy and discount the same way);
    - ``finance_cost`` (Interest) = FinanceCosts + the finance-cost row of a financial-services business;
    - ``ebitda`` (Operating Profit) = Sales - Expenses, Expenses = Expenses - FinanceCosts - depreciation - excise - that row;
    - ``other_income`` = OtherIncome + ExceptionalItemsBeforeTax, ``other_income_with_associates`` the same plus the associates'
      share (a named alternative, never a fit); ``depreciation``; ``pbt`` = ProfitBeforeTax, ``pbt_with_associates`` plus the share;
    - ``pat`` = ProfitLossForPeriod (the whole profit, the web page's), ``pat_owners`` the owners' share (the Excel's), ``eps``."""
    def cr(name: str) -> float | None:
        return facts.cr(name, end=end, months=months)

    out: dict[str, tuple[float, str]] = {}
    revenue, expenses = cr("RevenueFromOperations"), cr("Expenses")
    levies = usable({p: v for p, (v, _) in flow_parts(facts, end, months).items()}, revenue) if revenue is not None else {}
    excise = levies.get("excise", 0.0)
    fin = finance_services_cost(facts, end, months)
    fin_cost, depreciation = cr("FinanceCosts"), cr("DepreciationDepletionAndAmortisationExpense")
    if revenue is not None:
        used = [p for p in FLOW_ORDER if p in levies]
        out["revenue"] = (revenue - sum(levies.values()), "RevenueFromOperations" + "".join(f" - {p}" for p in used))
    if fin_cost is not None:
        out["finance_cost"] = (fin_cost + (fin[0] if fin else 0.0), "FinanceCosts" + (" + finance-cost row" if fin else ""))
    if depreciation is not None:
        out["depreciation"] = (depreciation, "DepreciationDepletionAndAmortisationExpense")
    if None not in (revenue, expenses, fin_cost, depreciation):
        sales = out["revenue"][0]
        screener_expenses = expenses - fin_cost - depreciation - excise - (fin[0] if fin else 0.0)
        out["ebitda"] = (sales - screener_expenses, "Sales - (Expenses - FinanceCosts - depreciation - excise - finance-cost row)")
    other, exceptional = cr("OtherIncome"), cr("ExceptionalItemsBeforeTax")
    share = cr(ASSOCIATES_ELEMENT)
    if other is not None:
        base = other + (exceptional or 0.0)
        out["other_income"] = (base, "OtherIncome" + (" + ExceptionalItemsBeforeTax" if exceptional else ""))
        if share:
            out["other_income_with_associates"] = (base + share, out["other_income"][1] + " + associates' share")
    pbt = cr("ProfitBeforeTax")
    if pbt is not None:
        out["pbt"] = (pbt, "ProfitBeforeTax")
        if share:
            out["pbt_with_associates"] = (pbt + share, "ProfitBeforeTax + associates' share")
    for key, name in (("pat", "ProfitLossForPeriod"), ("pat_owners", "ProfitOrLossAttributableToOwnersOfParent")):
        if cr(name) is not None:
            out[key] = (cr(name), name)
    for name in ANNUAL_EPS:
        value = facts.get(name, end=end, months=months)
        if value is not None:
            out["eps"] = (float(value), name)
            break
    return out


# --- views ------------------------------------------------------------------------------------------------------

def subsets(parts: list[str]) -> list[tuple[str, ...]]:
    """Every non-empty subset of the parts in their given order, smaller first. Used only to list the possible class names
    (REVENUE_RULES): a view never searches the subsets for the best fit."""
    return [c for size in range(1, len(parts) + 1) for c in itertools.combinations(parts, size)]


def additive_views(line: str, ours: float, parts: dict[str, float], order: tuple[str, ...]) -> list[tuple[float, str]]:
    """One view: our figure plus ALL the tagged parts at or above the floor, the way screener's formula adds them (never the
    subset that fits best: that would find a match by chance). ``[]`` when no part is usable. The rule names the line and the
    parts: ``borrowings_plus_lease_liabilities``; goodwill alone in the fixed assets keeps its older name
    ``goodwill_in_fixed_assets``."""
    used = usable({p: parts[p] for p in order if parts.get(p)}, ours)
    if not used:
        return []
    names = tuple(used)
    rule = "goodwill_in_fixed_assets" if line == "fixed_assets" and names == ("goodwill",) else f"{line}_plus_{'_'.join(names)}"
    return [(ours + sum(used.values()), rule)]
