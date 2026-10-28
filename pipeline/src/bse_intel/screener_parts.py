"""The parts of screener's treatment that memory has no line for, read from the stored full facts of a results file
(xbrl_facts.py; owner, 28 Oct 2026: "adjust our numbers as per screener's treatment"). Pure: facts in, parts out.

Screener's rules (docs/bench/screener-rules.md rows 1, 2, 10, 11; docs/design/screener-mapping.md 1a and 1d):

- Sales = revenue from operations less excise duty, sales tax, VAT (GST too: the same kind of levy) and discounts;
- Borrowings = long term + short term + current maturities + lease liabilities (a half-year balance sheet has no current maturities);
- Fixed Assets = property, plant and equipment + goodwill + intangibles + right-of-use assets, CWIP apart;
- deferred tax is shown net (assets and liabilities offset, so both totals are smaller by the amount offset);
- EPS on total shares (treasury shares counted) and on total profit against continuing profit.

An adjustment is offered only for a part the facts show, never for a gap alone. Which element carries a part is not the same for
every filer, and the integrated taxonomy (config/xbrl_sums, read 28 Oct 2026: INDAS, NBFC, BANKING) has NO element for excise
duty, sales tax, VAT, GST, discounts, lease liabilities, right-of-use assets, current maturities or treasury shares. A filer
can still show such a line in two ways, and both are read here (assumption: not yet seen on a real file, the first run of
``xbrl-facts`` tells; ``xbrl_facts.interesting`` lists what a file has):

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
LEASE_NAME = r"LeaseLiabilit"
LEASE_NOT = r"Payments|Interest|Expense|Proceeds|Adjustments|Maturity|Maturities"


# --- reading ----------------------------------------------------------------------------------------------------

def _sum(found: list[tuple], where: str) -> tuple[float, str] | None:
    if not found:
        return None
    return sum(row[-1] for row in found), where + ": " + "; ".join(
        (f"{row[0]} {row[1]}" if len(row) == 3 else row[0]) for row in found)


def flow_parts(facts: Facts, end: date, months: int) -> dict[str, tuple[float, str]]:
    """The levies and discounts of one results period (a 3-, 6-, 9- or 12-month context ending ``end``), in crore, each with
    where it was read: ``excise``, ``taxes`` (sales tax, VAT, GST) and ``discounts``. A part the facts do not show is absent."""
    out: dict[str, tuple[float, str]] = {}
    for part, (name_rx, desc_rx) in FLOW_PARTS.items():
        got = _sum(facts.find(name_rx, end=end, months=months), "element")
        got = got or _sum(facts.described(EXPENSE_PARENTS, desc_rx, end=end, months=months), "breakdown row")
        if got:
            out[part] = got
    return out


def balance_parts(facts: Facts, instant: date) -> dict[str, tuple[float, str]]:
    """The balance-sheet parts screener adds at one date (crore, each with where it was read): ``lease_liabilities``,
    ``current_maturities``, ``intangibles``, ``right_of_use``, ``intangibles_under_development``, ``equity_method``,
    ``investment_property``, ``other_financial_assets``, and the two deferred-tax lines (``dta``, ``dtl``)."""
    at = {"instant": instant}
    out: dict[str, tuple[float, str]] = {}

    def one(part: str, *names: str) -> None:
        found = [(n, v) for n in names if (v := facts.cr(n, **at)) is not None]
        if found:
            out[part] = (sum(v for _, v in found), "element: " + ", ".join(n for n, _ in found))

    # a lease or a maturity can be a line in two places at once in part (the non-current lease liability an element, the current
    # one a row of a breakdown), so both sources are added here; a levy of a period (``flow_parts``) is one or the other
    lease = [(n, v) for n, v in facts.find(LEASE_NAME, **at) if not re.search(LEASE_NOT, n, re.I)]
    for part, tagged, rows in (("lease_liabilities", lease, facts.described(LIABILITY_PARENTS, r"lease liabilit", **at)),
                               ("current_maturities", facts.find(r"CurrentMaturit", **at),
                                facts.described(LIABILITY_PARENTS, r"current maturit", **at))):
        got = [g for g in (_sum(tagged, "element"), _sum(rows, "breakdown row")) if g]
        if got:
            out[part] = (sum(v for v, _ in got), "; ".join(w for _, w in got))
    one("intangibles", "OtherIntangibleAssets")
    one("goodwill", "Goodwill")
    rou = _sum(facts.find(r"RightOfUse", **at), "element")
    if rou:
        out["right_of_use"] = rou
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


# --- views ------------------------------------------------------------------------------------------------------

def subsets(parts: list[str]) -> list[tuple[str, ...]]:
    """Every non-empty subset of the parts in their given order, smaller first (a single part is the plainest explanation)."""
    return [c for size in range(1, len(parts) + 1) for c in itertools.combinations(parts, size)]


def additive_views(line: str, ours: float, parts: dict[str, float], order: tuple[str, ...]) -> list[tuple[float, str]]:
    """``(ours + a subset of the found parts, rule)`` for each subset. The rule names the line and the parts:
    ``borrowings_plus_lease_liabilities``; goodwill alone in the fixed assets keeps its older name ``goodwill_in_fixed_assets``."""
    found = [p for p in order if parts.get(p)]
    out = []
    for combo in subsets(found):
        rule = "goodwill_in_fixed_assets" if line == "fixed_assets" and combo == ("goodwill",) else f"{line}_plus_{'_'.join(combo)}"
        out.append((ours + sum(parts[p] for p in combo), rule))
    return out
