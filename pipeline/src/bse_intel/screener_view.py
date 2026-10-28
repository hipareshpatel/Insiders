"""Screener's statements row by row: ONE FIXED RECIPE PER SCREENER WEBSITE ROW, the same for every company (owner, 28 Oct 2026:
"make our statements like screener, all line items row by row and all their rules ... screener has the same source as we do").
Pure: stored XBRL facts (xbrl_facts.Facts) in, rows out. The comparison against the stored screener pages is ``compare`` / ``run``
(command ``screener-rows``, read only).

No fitting. A recipe is never tried "only when the gap is not closed", a subset of parts is never searched, and a row's value never
depends on screener's figure: the recipe set is chosen by the results file's TEMPLATE alone (corporate Ind AS, BANKING, NBFC, an
insurer's LI / GI), and its source by what is stored (below), never by a gap. screener_parts.py and screener_crosscheck.py classify gaps
after the fact with alternatives; this module does not extend that approach.

Sources (screener's own docs, read by the lead 28 Oct 2026: "annual data is imported from the annual extract in the quarterly (Q4)
filings until the annual report is published ... we revise old numbers when the company revises them in new annual reports"):

- a year (FYxx, March year end): the NEWEST stored annual-report facts doc that holds that year (its prior-year comparative counts:
  FY25 from the FY26 report when stored), else the Q4 results file's 12-month context. Lenders file no annual-report XBRL on NSE:
  always the Q4 file. A balance sheet at a March year end is read the same way (the instant at the year end);
- a quarter: that quarter's own results file, its 3-month context; a half-year balance sheet (Sep): that quarter's file's instant.

Every row carries a note naming the elements used and the source ("annual report FY26", "results file Q4FY26").

Corporate (Ind AS) profit and loss, crore (evidence: docs/audit/screener-rows-2026-10-28.md):

- Sales = RevenueFromOperations - excise - sales tax / VAT / GST - discounts, each its own element (ExciseDuty, ...) or a described
  row of the Other expenses breakdown ("Excise duty"); screener: "Sales = Revenue - (excise + VAT + Sales Tax)", net of discounts;
- Expenses = Expenses - FinanceCosts - DepreciationDepletionAndAmortisationExpense - those levies - the finance cost of a
  financial-services business (L&T's described row) - LossOnDisposal...PropertyPlantAndEquipment (screener: profit or loss on sale
  of fixed assets is always exceptional, so in Other Income);
- Operating Profit = Sales - Expenses; OPM % = Operating Profit / Sales;
- Other Income = PBT + Depreciation + Interest - Operating Profit (the identity, PBT as filed); the parts (OtherIncome +
  ExceptionalItemsBeforeTax + the associates' share - loss on disposal; screener: "Other Income also includes exceptional items",
  "profit from associates is always other ordinary income") are in the note, and the note says when the two differ;
- Interest = FinanceCosts + the financial-services finance-cost row ("Finance cost of financial services business..."; an annual
  report files that breakdown only as a text block, so for a year read from it the row is read from the Q4 results file);
- Depreciation, Profit before tax = ProfitBeforeTax, Tax % = TaxExpense / PBT, Net Profit = ProfitLossForPeriod (the website's Net
  Profit is the whole profit). Named rows not on the page: Tax, Net Profit (owners) (= profit for EPS), Minority share, Associates'
  share, Exceptional items, Exceptional items AT (= exceptional - tax x exceptional / PBT; the exceptional itself when that tax is
  larger than it), Profit for PE (= owners' profit - exceptional AT).

Corporate balance sheet (instant): Equity Capital = EquityShareCapital; Reserves = OtherEquity; Borrowings = BorrowingsNoncurrent +
BorrowingsCurrent + lease liabilities (elements, else described rows "lease" of the other financial liabilities) + described rows
"current maturities" (not of a lease when lease elements are used); Fixed Assets = PPE + Goodwill + OtherIntangibleAssets +
InvestmentProperty + right-of-use (element RightOfUseAssets, else the described row "Right-of-use assets" of Other non-current
assets); CWIP = CapitalWorkInProgress + IntangibleAssetsUnderDevelopment; Investments = NoncurrentInvestments + CurrentInvestments +
InvestmentsAccountedForUsingEquityMethod; Total (Liabilities and Assets) = Assets - min(DeferredTaxAssetsNet, DeferredTaxLiabilitiesNet);
Other Liabilities and Other Assets are the remainders.

Cash flow (every template): Operating, Investing + EffectOfExchangeRateChangesOnCashAndCashEquivalents, Financing, Net Cash Flow =
IncreaseDecreaseInCashAndCashEquivalents.

Banks (BANKING): Revenue = InterestEarned; Interest = InterestExpended; Depreciation = AdjustmentsForDepreciationAndAmortisationExpense
(the cash flow's, so only in a half or full year); Expenses = OperatingExpenses + ProvisionsOtherThanTaxAndContingencies - Depreciation;
Financing Profit = Revenue - Interest - Expenses; Other Income = OtherIncome + a positive ExceptionalItems; PBT =
ProfitLossFromOrdinaryActivitiesBeforeTax - a negative ExceptionalItems (HDFC FY26: 98,948 + 3,193 = 102,141); Net Profit =
ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates (a standalone file: ProfitLossForThePeriod). Balance sheet: Equity
Capital = Capital, Deposits = Deposits, Borrowing = Borrowings (screener 2025: deposits a line apart; the Excel Data Sheet still adds
them); the rest has no recipe yet (Reserves: ReservesAndSurplus is 4,545 Cr under the Excel's for HDFC Bank FY26, 18,768 over for
SBI). Measured on the FY26 Q4 files against the Excel: HDFC Bank and SBI profit and loss (8 rows) and cash flow (4) all exact. NBFC and insurers: what maps cleanly (below); every other row is ``no_recipe``.

Not implemented on purpose: the L&T segment element InterestExpenseReportableSegment (Wipro FY26 files it equal to its FinanceCosts,
1,457.7 Cr: adding it would count Wipro's interest twice); PDF-only lines (Reliance's sales tax, L&T's bank charges); director
remuneration moved into employee cost (Employee Cost is not a website row)."""

from __future__ import annotations

import csv
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date

from . import xbrl_facts
from .memory_gaps import quarter_end
from .metrics import CONSOLIDATED
from .screener_fill import _section_table, _basis_of, cash_year_of, period_of

ABS_TOL, REL_TOL = 1.0, 0.0005          # a pair is exact within 1 Cr or 0.05% of screener's figure
PCT_TOL = 0.51                           # screener prints whole percent
PCT_ROWS = ("OPM %", "Financing Margin %", "Tax %")
STATUSES = ("ok", "apart", "no_facts", "no_recipe")

PL_ROWS = ("Sales", "Revenue", "Expenses", "Operating Profit", "Financing Profit", "OPM %", "Financing Margin %", "Other Income",
           "Interest", "Depreciation", "Profit before tax", "Tax %", "Net Profit")
BS_ROWS = ("Equity Capital", "Reserves", "Borrowings", "Borrowing", "Deposits", "Other Liabilities", "Total Liabilities",
           "Fixed Assets", "CWIP", "Investments", "Other Assets", "Total Assets")
CF_ROWS = ("Cash from Operating Activity", "Cash from Investing Activity", "Cash from Financing Activity", "Net Cash Flow")
EXTRA_ROWS = ("Tax", "Net Profit (owners)", "Minority share", "Associates' share", "Exceptional items", "Exceptional items AT",
              "Profit for PE")
TABLES = (("quarters", "quarters", PL_ROWS), ("profit-loss", "annual", PL_ROWS), ("balance-sheet", "balance", BS_ROWS),
          ("cash-flow", "cash_flow", CF_ROWS))

EXPENSE_PARENTS = ("OtherExpenses", "Expenses")
LIABILITY_PARENTS = ("OtherNoncurrentFinancialLiabilitiesOthers", "OtherCurrentFinancialLiabilitiesOthers",
                     "OtherNoncurrentFinancialLiabilities", "OtherCurrentFinancialLiabilities")
ASSET_PARENTS = ("OtherNoncurrentAssetsOthers", "OtherNoncurrentAssets")
LEASE_ELEMENTS = ("LeaseLiabilitiesNoncurrent", "LeaseLiabilitiesCurrent", "NoncurrentLeaseLiabilities", "CurrentLeaseLiabilities")
# the levies and discounts out of Sales (and Expenses): (elements, described row of the Other expenses breakdown)
LEVIES = {"excise": (("ExciseDuty",), r"^\s*excise"),
          "sales tax": (("SalesTax", "ValueAddedTax", "GoodsAndServicesTax", "SalesTaxAndValueAddedTax"),
                        r"^\s*(sales tax|vat\b|value added tax|gst\b|goods (and|&) services tax)"),
          "discounts": (("TradeDiscounts", "SalesDiscounts", "Discounts", "Rebates"), r"^\s*(trade )?(discount|rebate)s?\b")}
FIN_SERVICES_ROW = r"^\s*finance costs? of (a |the )?financial[- ]services"
LOSS_ON_DISPOSAL = "LossOnDisposalDiscardDemolishmentAndDestructionOfDepreciablePropertyPlantAndEquipment"
ASSOCIATES = "ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod"

CORPORATE, BANK, NBFC, INSURER = "corporate", "bank", "nbfc", "insurer"


@dataclass
class Row:
    value: float | None        # None: an element the recipe needs is not in the facts
    note: str


def family(template: str | None) -> str:
    """The recipe set, by the results file's template alone (xbrl.taxonomy: INDAS, NBFC, BANKING, GI, LI; LEGACY_* alike)."""
    t = (template or "").upper()
    if "BANK" in t and "OTHERTHANBANK" not in t:
        return BANK
    if "NBFC" in t:
        return NBFC
    if t.replace("LEGACY_", "") in ("LI", "GI"):
        return INSURER
    return CORPORATE


# --- reading --------------------------------------------------------------------------------------------------------

class _Reader:
    """One period of one facts doc: ``cr`` an undimensioned money fact, ``rows`` the described breakdown rows."""

    def __init__(self, facts: xbrl_facts.Facts, *, end: date | None = None, months: int | None = None, instant: date | None = None):
        self.facts, self.at = facts, {"end": end, "months": months, "instant": instant}

    def cr(self, name: str) -> float | None:
        return self.facts.cr(name, **self.at)

    def rows(self, parents: tuple[str, ...], rx: str) -> list[tuple[str, str, float]]:
        return self.facts.described(parents, rx, joined=True, **self.at)


def _fmt(v: float) -> str:
    return f"{v:,.2f}"


def _sum_rows(rows: list[tuple[str, str, float]]) -> float:
    return sum(r[2] for r in rows)


def _levies(r: _Reader) -> tuple[dict[str, float], list[str]]:
    """Each levy and discount the facts show: its own element(s), else the described rows of the Other expenses breakdown."""
    out: dict[str, float] = {}
    notes: list[str] = []
    for part, (names, rx) in LEVIES.items():
        found = [(n, v) for n in names if (v := r.cr(n)) is not None and v]
        if found:
            out[part] = sum(v for _, v in found)
            notes.append(f"{part} {_fmt(out[part])} ({', '.join(n for n, _ in found)})")
            continue
        rows = r.rows(EXPENSE_PARENTS, rx)
        if rows:
            out[part] = _sum_rows(rows)
            notes.append(f"{part} {_fmt(out[part])} (row " + "; ".join(t[:50] for _, t, _ in rows) + ")")
    return out, notes


def _fin_services(r: _Reader, fallback: _Reader | None) -> tuple[float, str]:
    rows = r.rows(EXPENSE_PARENTS, FIN_SERVICES_ROW)
    where = "this file"
    if not rows and fallback is not None:
        rows, where = fallback.rows(EXPENSE_PARENTS, FIN_SERVICES_ROW), "the Q4 results file"
    if not rows:
        return 0.0, ""
    value = _sum_rows(rows)
    return value, f"financial-services finance cost {_fmt(value)} (row of {where})"


def _need(r: _Reader, *names: str) -> tuple[dict[str, float], list[str]]:
    got, missing = {}, []
    for n in names:
        v = r.cr(n)
        if v is None:
            missing.append(n)
        else:
            got[n] = v
    return got, missing


def _pct(num: float | None, den: float | None) -> float | None:
    return None if num is None or not den else 100.0 * num / den


# --- profit and loss -----------------------------------------------------------------------------------------------

def _exceptional_rows(out: dict[str, Row], exceptional: float | None, tax: float | None, pbt: float | None,
                      owners: float | None) -> None:
    """Screener's Net Profit breakup: exceptional items after tax and the profit for PE."""
    if exceptional is None:
        return
    out["Exceptional items"] = Row(exceptional, "ExceptionalItems")
    if tax is None or not pbt:
        return
    tax_on = tax * exceptional / pbt
    at = exceptional if abs(tax_on) > abs(exceptional) else exceptional - tax_on
    out["Exceptional items AT"] = Row(at, f"exceptional {_fmt(exceptional)} - tax x exceptional / PBT {_fmt(tax_on)}")
    if owners is not None:
        out["Profit for PE"] = Row(owners - at, "owners' profit - exceptional items AT")


def corporate_pl(r: _Reader, fallback: _Reader | None = None, source: str = "") -> dict[str, Row]:
    """The corporate (Ind AS) profit and loss rows of one period. ``fallback`` is where the financial-services finance-cost row is
    read when this doc has none (a year read from the annual report: its Q4 results file)."""
    src = f" [{source}]" if source else ""
    out: dict[str, Row] = {}
    rev, exp, fc, dep = r.cr("RevenueFromOperations"), r.cr("Expenses"), r.cr("FinanceCosts"), r.cr("DepreciationDepletionAndAmortisationExpense")
    pbt, tax = r.cr("ProfitBeforeTax"), r.cr("TaxExpense")
    levies, levy_notes = _levies(r)
    lev = sum(levies.values())
    fin, fin_note = _fin_services(r, fallback)
    loss = r.cr(LOSS_ON_DISPOSAL) or 0.0
    sales = None if rev is None else rev - lev
    out["Sales"] = Row(sales, ("RevenueFromOperations" + (" less " + ", ".join(levy_notes) if levy_notes else "")
                               if rev is not None else "missing RevenueFromOperations") + src)
    interest = None if fc is None else fc + fin
    out["Interest"] = Row(interest, ("FinanceCosts" + (" + " + fin_note if fin_note else "") if fc is not None
                                     else "missing FinanceCosts") + src)
    out["Depreciation"] = Row(dep, ("DepreciationDepletionAndAmortisationExpense" if dep is not None
                                    else "missing DepreciationDepletionAndAmortisationExpense") + src)
    expenses = None
    if None not in (exp, fc, dep):
        expenses = exp - fc - dep - lev - fin - loss
        parts = ["FinanceCosts", "depreciation"] + (["levies"] if lev else []) + (["financial-services finance cost"] if fin else []) \
            + ([f"loss on disposal of PPE {_fmt(loss)}"] if loss else [])
        out["Expenses"] = Row(expenses, "Expenses less " + ", ".join(parts) + src)
    else:
        out["Expenses"] = Row(None, "missing " + ", ".join(n for n, v in (("Expenses", exp), ("FinanceCosts", fc),
                                                                            ("DepreciationDepletionAndAmortisationExpense", dep)) if v is None) + src)
    op = None if sales is None or expenses is None else sales - expenses
    out["Operating Profit"] = Row(op, "Sales - Expenses" + src)
    out["OPM %"] = Row(_pct(op, sales), "Operating Profit / Sales" + src)
    oi_parts, exc, share = r.cr("OtherIncome"), r.cr("ExceptionalItemsBeforeTax"), r.cr(ASSOCIATES)
    parts = None if oi_parts is None else oi_parts + (exc or 0.0) + (share or 0.0) - loss
    if None not in (pbt, dep, interest, op):
        oi = pbt + dep + interest - op
        note = "PBT + Depreciation + Interest - Operating Profit"
        if parts is not None:
            note += f"; parts OtherIncome + exceptional + associates - loss on disposal = {_fmt(parts)}"
            if abs(parts - oi) > ABS_TOL:
                note += f" (differ by {_fmt(oi - parts)})"
        out["Other Income"] = Row(oi, note + src)
    else:
        out["Other Income"] = Row(None, "missing a line of the identity (PBT, Depreciation, Interest, Operating Profit)" + src)
    out["Profit before tax"] = Row(pbt, ("ProfitBeforeTax" if pbt is not None else "missing ProfitBeforeTax") + src)
    out["Tax"] = Row(tax, "TaxExpense" + src)
    out["Tax %"] = Row(_pct(tax, pbt), "TaxExpense / ProfitBeforeTax" + src)
    whole, owners = r.cr("ProfitLossForPeriod"), r.cr("ProfitOrLossAttributableToOwnersOfParent")
    out["Net Profit"] = Row(whole, ("ProfitLossForPeriod (whole profit)" if whole is not None else "missing ProfitLossForPeriod") + src
                            + (f"; owners' share {_fmt(owners)}" if owners is not None else ""))
    if owners is not None:
        out["Net Profit (owners)"] = Row(owners, "ProfitOrLossAttributableToOwnersOfParent (profit for EPS)" + src)
    minority = r.cr("ProfitOrLossAttributableToNonControllingInterests")
    if minority is not None:
        out["Minority share"] = Row(minority, "ProfitOrLossAttributableToNonControllingInterests" + src)
    if share is not None:
        out["Associates' share"] = Row(share, ASSOCIATES + src)
    _exceptional_rows(out, exc, tax, pbt, owners)
    return out


def bank_pl(r: _Reader, source: str = "") -> dict[str, Row]:
    src = f" [{source}]" if source else ""
    out: dict[str, Row] = {}
    earned, expended = r.cr("InterestEarned"), r.cr("InterestExpended")
    dep = r.cr("AdjustmentsForDepreciationAndAmortisationExpense")
    opex, prov = r.cr("OperatingExpenses"), r.cr("ProvisionsOtherThanTaxAndContingencies")
    other, exc = r.cr("OtherIncome"), r.cr("ExceptionalItems")
    pbt_filed, tax = r.cr("ProfitLossFromOrdinaryActivitiesBeforeTax"), r.cr("TaxExpense")
    out["Revenue"] = Row(earned, ("InterestEarned" if earned is not None else "missing InterestEarned") + src)
    out["Interest"] = Row(expended, ("InterestExpended" if expended is not None else "missing InterestExpended") + src)
    out["Depreciation"] = Row(dep, ("AdjustmentsForDepreciationAndAmortisationExpense (cash flow)" if dep is not None
                                    else "missing AdjustmentsForDepreciationAndAmortisationExpense (no cash flow in this period)") + src)
    expenses = None if None in (opex, dep) else opex + (prov or 0.0) - dep
    out["Expenses"] = Row(expenses, ("OperatingExpenses + ProvisionsOtherThanTaxAndContingencies - Depreciation" if expenses is not None
                                     else "missing OperatingExpenses or Depreciation") + src)
    fp = None if None in (earned, expended, expenses) else earned - expended - expenses
    out["Financing Profit"] = Row(fp, "Revenue - Interest - Expenses" + src)
    out["Financing Margin %"] = Row(_pct(fp, earned), "Financing Profit / Revenue" + src)
    out["Other Income"] = Row(None if other is None else other + max(exc or 0.0, 0.0),
                              ("OtherIncome" + (" + exceptional items" if (exc or 0) > 0 else "") if other is not None
                               else "missing OtherIncome") + src)
    pbt = None if pbt_filed is None else pbt_filed - min(exc or 0.0, 0.0)
    out["Profit before tax"] = Row(pbt, ("ProfitLossFromOrdinaryActivitiesBeforeTax" + (" less the negative exceptional items"
                                                                                        if (exc or 0) < 0 else "")
                                         if pbt_filed is not None else "missing ProfitLossFromOrdinaryActivitiesBeforeTax") + src)
    out["Tax"] = Row(tax, "TaxExpense" + src)
    out["Tax %"] = Row(_pct(tax, pbt), "TaxExpense / Profit before tax" + src)
    name = "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates"
    net = r.cr(name)
    if net is None and r.cr("ProfitLossForThePeriod") is not None:
        net, name = r.cr("ProfitLossForThePeriod"), "ProfitLossForThePeriod"
    out["Net Profit"] = Row(net, (name if net is not None else "missing " + name) + src)
    minority = r.cr("ProfitLossOfMinorityInterest")
    if minority is not None:
        out["Minority share"] = Row(minority, "ProfitLossOfMinorityInterest" + src)
    share = r.cr("ShareOfProfitLossOfAssociates")
    if share is not None:
        out["Associates' share"] = Row(share, "ShareOfProfitLossOfAssociates" + src)
    _exceptional_rows(out, exc, tax, pbt_filed, net)
    return out


def nbfc_pl(r: _Reader, source: str = "") -> dict[str, Row]:
    """An NBFC (Ind AS NBFC template): the rows that map cleanly; Expenses, Financing Profit and Other Income have no recipe yet."""
    src = f" [{source}]" if source else ""
    out: dict[str, Row] = {}
    for row, name in (("Revenue", "RevenueFromOperations"), ("Interest", "FinanceCosts"),
                      ("Depreciation", "DepreciationDepletionAndAmortisationExpense"), ("Profit before tax", "ProfitBeforeTax"),
                      ("Tax", "TaxExpense"), ("Net Profit", "ProfitLossForPeriod"),
                      ("Net Profit (owners)", "ProfitOrLossAttributableToOwnersOfParent")):
        v = r.cr(name)
        out[row] = Row(v, (name if v is not None else "missing " + name) + src)
    out["Tax %"] = Row(_pct(out["Tax"].value, out["Profit before tax"].value), "TaxExpense / ProfitBeforeTax" + src)
    return out


def insurer_pl(r: _Reader, source: str = "") -> dict[str, Row]:
    """An insurer (LI / GI): Net Profit only (LIC's PBT is in two regimes: docs/audit/screener-rows-2026-10-28.md)."""
    v = r.cr("ProfitLossAfterTaxAndExtraordinaryItems")
    return {"Net Profit": Row(v, ("ProfitLossAfterTaxAndExtraordinaryItems" if v is not None
                                  else "missing ProfitLossAfterTaxAndExtraordinaryItems") + (f" [{source}]" if source else ""))}


def pl_rows(fam: str, r: _Reader, fallback: _Reader | None = None, source: str = "") -> dict[str, Row]:
    if fam == BANK:
        return bank_pl(r, source)
    if fam == NBFC:
        return nbfc_pl(r, source)
    if fam == INSURER:
        return insurer_pl(r, source)
    return corporate_pl(r, fallback, source)


# --- balance sheet ------------------------------------------------------------------------------------------------

def corporate_bs(r: _Reader, source: str = "") -> dict[str, Row]:
    src = f" [{source}]" if source else ""
    out: dict[str, Row] = {}

    def total(*names: str) -> tuple[float, list[str]]:
        found = [(n, v) for n in names if (v := r.cr(n)) is not None]
        return sum(v for _, v in found), [n for n, _ in found]

    cap, res = r.cr("EquityShareCapital"), r.cr("OtherEquity")
    out["Equity Capital"] = Row(cap, ("EquityShareCapital" if cap is not None else "missing EquityShareCapital") + src)
    out["Reserves"] = Row(res, ("OtherEquity" if res is not None else "missing OtherEquity") + src)
    debt, debt_names = total("BorrowingsNoncurrent", "BorrowingsCurrent")
    lease, lease_names = total(*LEASE_ELEMENTS)
    if lease_names:
        rows = [x for x in r.rows(LIABILITY_PARENTS, r"current maturit") if not re.search("lease", x[1], re.I)]
        lease_note = f"lease {_fmt(lease)} ({', '.join(lease_names)})"
    else:
        rows = r.rows(LIABILITY_PARENTS, r"lease|current maturit")
        lease_note = ""
    extra = _sum_rows(rows)
    row_note = ("rows " + "; ".join(f"{t[:50]} {_fmt(v)}" for _, t, v in rows)) if rows else ""
    borrowings = debt + lease + extra
    out["Borrowings"] = Row(borrowings if debt_names or lease_names or rows else None,
                            " + ".join(x for x in (" + ".join(debt_names), lease_note, row_note) if x) + src
                            if debt_names or lease_names or rows else "missing BorrowingsNoncurrent and BorrowingsCurrent" + src)
    fixed, fixed_names = total("PropertyPlantAndEquipment", "Goodwill", "OtherIntangibleAssets", "InvestmentProperty")
    rou = r.cr("RightOfUseAssets")
    rou_note = "RightOfUseAssets" if rou is not None else ""
    if rou is None:
        rou_rows = r.rows(ASSET_PARENTS, r"right.of.use")
        rou = _sum_rows(rou_rows) if rou_rows else None
        rou_note = ("right-of-use row " + _fmt(rou)) if rou_rows else ""
    fa = fixed + (rou or 0.0)
    out["Fixed Assets"] = Row(fa if fixed_names or rou else None,
                              " + ".join(fixed_names + ([rou_note] if rou_note else [])) + src if fixed_names or rou
                              else "missing PropertyPlantAndEquipment" + src)
    cwip, cwip_names = total("CapitalWorkInProgress", "IntangibleAssetsUnderDevelopment")
    out["CWIP"] = Row(cwip, (" + ".join(cwip_names) or "neither CapitalWorkInProgress nor IntangibleAssetsUnderDevelopment: 0") + src)
    inv, inv_names = total("NoncurrentInvestments", "CurrentInvestments", "InvestmentsAccountedForUsingEquityMethod")
    out["Investments"] = Row(inv, (" + ".join(inv_names) or "no investments element: 0") + src)
    assets, dta, dtl = r.cr("Assets"), r.cr("DeferredTaxAssetsNet"), r.cr("DeferredTaxLiabilitiesNet")
    offset = min(dta, dtl) if dta is not None and dtl is not None else 0.0
    tot = None if assets is None else assets - offset
    tot_note = ("Assets" + (f" - min(DTA, DTL) {_fmt(offset)}" if offset else "") if assets is not None else "missing Assets") + src
    out["Total Liabilities"] = Row(tot, tot_note)
    out["Total Assets"] = Row(tot, tot_note)
    b = out["Borrowings"].value
    out["Other Liabilities"] = Row(None if None in (tot, cap, res, b) else tot - cap - res - b,
                                   "Total - Equity Capital - Reserves - Borrowings" + src)
    out["Other Assets"] = Row(None if None in (tot, out["Fixed Assets"].value) else tot - fa - cwip - inv,
                              "Total - Fixed Assets - CWIP - Investments" + src)
    return out


def bank_bs(r: _Reader, source: str = "") -> dict[str, Row]:
    src = f" [{source}]" if source else ""
    out = {}
    # Reserves: no recipe yet (ReservesAndSurplus is 4,545 Cr under screener's Excel for HDFC Bank FY26, 18,768 over for SBI)
    for row, name in (("Equity Capital", "Capital"), ("Deposits", "Deposits"), ("Borrowing", "Borrowings")):
        v = r.cr(name)
        out[row] = Row(v, (name if v is not None else "missing " + name) + src)
    return out


def nbfc_bs(r: _Reader, source: str = "") -> dict[str, Row]:
    src = f" [{source}]" if source else ""
    out = {}
    for row, name in (("Equity Capital", "EquityShareCapital"), ("Reserves", "OtherEquity")):
        v = r.cr(name)
        out[row] = Row(v, (name if v is not None else "missing " + name) + src)
    return out


def bs_rows(fam: str, r: _Reader, source: str = "") -> dict[str, Row]:
    if fam == BANK:
        return bank_bs(r, source)
    if fam == NBFC:
        return nbfc_bs(r, source)
    if fam == INSURER:
        return {}
    return corporate_bs(r, source)


# --- cash flow ------------------------------------------------------------------------------------------------------

def cf_rows(r: _Reader, source: str = "") -> dict[str, Row]:
    src = f" [{source}]" if source else ""
    out = {}
    for row, name in (("Cash from Operating Activity", "CashFlowsFromUsedInOperatingActivities"),
                      ("Cash from Financing Activity", "CashFlowsFromUsedInFinancingActivities"),
                      ("Net Cash Flow", "IncreaseDecreaseInCashAndCashEquivalents")):
        v = r.cr(name)
        out[row] = Row(v, (name if v is not None else "missing " + name) + src)
    inv, fx = r.cr("CashFlowsFromUsedInInvestingActivities"), r.cr("EffectOfExchangeRateChangesOnCashAndCashEquivalents")
    out["Cash from Investing Activity"] = Row(None if inv is None else inv + (fx or 0.0),
                                              ("CashFlowsFromUsedInInvestingActivities" + (" + EffectOfExchangeRateChanges" if fx else "")
                                               if inv is not None else "missing CashFlowsFromUsedInInvestingActivities") + src)
    order = ("Cash from Operating Activity", "Cash from Investing Activity", "Cash from Financing Activity", "Net Cash Flow")
    return {k: out[k] for k in order}


# --- a company's stored facts ---------------------------------------------------------------------------------------

_DOC = re.compile(r"(annual-)?((?:Q[1-4])?FY\d{2}(?:-\d{2})?)-(consolidated|standalone|unknown)\.json\.gz")


class CompanyFacts:
    """The stored facts docs of one company (``raw/xbrl-facts/<scrip>/``), loaded when first asked for. ``loader(key)`` gives a
    doc's bytes (the sink's get_object)."""

    def __init__(self, keys: list[str], loader):
        self.loader = loader
        self.results: dict[tuple[str, str], str] = {}
        self.annual: dict[tuple[str, str], str] = {}
        for key in keys:
            m = _DOC.fullmatch(key.rsplit("/", 1)[-1])
            if m:
                (self.annual if m[1] else self.results)[(m[2], m[3].upper())] = key
        self._cache: dict[str, xbrl_facts.Facts | None] = {}

    def _load(self, key: str | None) -> xbrl_facts.Facts | None:
        if key is None:
            return None
        if key not in self._cache:
            try:
                body = self.loader(key)
                self._cache[key] = xbrl_facts.Facts(xbrl_facts.loads(body)) if body else None
            except Exception:   # noqa: BLE001 - a damaged object is no facts
                self._cache[key] = None
        return self._cache[key]

    def result(self, period: str, basis: str) -> xbrl_facts.Facts | None:
        return self._load(self.results.get((period, basis)))

    def family(self, basis: str) -> str:
        for (period, b), key in sorted(self.results.items(), key=lambda kv: kv[0][0], reverse=True):
            if b == basis and (f := self._load(key)) is not None:
                return family(f.doc.get("template"))
        return CORPORATE

    def year(self, fy: str, basis: str, fam: str, instant: bool = False):
        """(facts, label, Q4 facts) of a March year: the newest annual-report doc holding the year (a later report's comparative
        counts), else the Q4 results file. A lender: always the Q4 file."""
        end = _fy_end(fy)
        q4 = self.result(f"Q4{fy}", basis)
        if fam == CORPORATE and end is not None:
            for (afy, b), key in sorted(self.annual.items(), key=lambda kv: _fy_num(kv[0][0]), reverse=True):
                if b != basis or _fy_num(afy) < _fy_num(fy):
                    continue
                f = self._load(key)
                if f is None:
                    continue
                holds = f.cr("Assets", instant=end) is not None if instant else \
                    any(f.cr(n, end=end, months=12) is not None for n in ("RevenueFromOperations", "ProfitLossForPeriod"))
                if holds:
                    return f, f"annual report {afy}", q4
        return q4, f"results file Q4{fy}", None


def _fy_num(fy: str) -> int:
    m = re.fullmatch(r"FY(\d{2})", fy)
    return int(m[1]) if m else -1


def _fy_end(fy: str) -> date | None:
    m = re.fullmatch(r"FY(\d{2})", fy)
    return date(2000 + int(m[1]), 3, 31) if m else None


# --- the page -------------------------------------------------------------------------------------------------------

def parse_page(body: str) -> dict:
    """{"basis", "tables": {table: {row: {period: value}}}} from a stored screener page: the quarters (Q2FY27), the annual profit
    and loss (FY26; another year end "YE:2025-12"), the balance sheet (Q4FY26, Q2FY27) and the cash flow (FY26), every row named as
    the page names it (the trailing "+" removed)."""
    out: dict = {"basis": None, "tables": {}}
    for section, table, wanted in TABLES:
        got = _section_table(body, section)
        if not got:
            continue
        columns, rows, text = got
        if out["basis"] is None:
            out["basis"] = _basis_of(text)
        by_row: dict[str, dict[str, float]] = {}
        for label, values in rows.items():
            if label not in wanted:
                continue
            for i, column in enumerate(columns):
                period = cash_year_of(column) if table in ("annual", "cash_flow") else period_of(column)
                if period and i < len(values) and values[i] is not None:
                    by_row.setdefault(label, {})[period] = values[i]
        out["tables"][table] = by_row
    return out


# --- the comparison -------------------------------------------------------------------------------------------------

def exact(ours: float, theirs: float, row: str) -> bool:
    if row in PCT_ROWS:
        return abs(ours - theirs) <= PCT_TOL
    return abs(ours - theirs) <= ABS_TOL or (theirs != 0 and abs(ours - theirs) <= REL_TOL * abs(theirs))


def _ours(cf: CompanyFacts, fam: str, basis: str, table: str, period: str, memo: dict) -> tuple[dict[str, Row] | None, str]:
    """Our rows of one column, or (None, why)."""
    k = (table, period)
    if k in memo:
        return memo[k]
    result: tuple[dict[str, Row] | None, str]
    if period.startswith("YE:"):
        result = None, "year end not March: no recipe source yet"
    elif table == "quarters":
        end, f = quarter_end(period), cf.result(period, basis)
        result = (pl_rows(fam, _Reader(f, end=end, months=3), source=f"results file {period}"), "") if f is not None and end \
            else (None, f"no results facts for {period}")
    elif table in ("annual", "cash_flow"):
        f, label, q4 = cf.year(period, basis, fam)
        end = _fy_end(period)
        if f is None or end is None:
            result = None, f"no annual-report or Q4 results facts for {period}"
        elif table == "annual":
            fallback = _Reader(q4, end=end, months=12) if q4 is not None else None
            result = pl_rows(fam, _Reader(f, end=end, months=12), fallback, label), ""
        else:
            result = cf_rows(_Reader(f, end=end, months=12), label), ""
    else:   # balance
        end = quarter_end(period)
        if period.startswith("Q4"):
            f, label, _ = cf.year(period[2:], basis, fam, instant=True)
        else:
            f, label = cf.result(period, basis), f"results file {period}"
        result = (bs_rows(fam, _Reader(f, instant=end), label), "") if f is not None and end else (None, f"no facts for {period}")
    memo[k] = result
    return result


def compare(page: dict, cf: CompanyFacts, scrip: str = "", symbol: str = "", basis: str | None = None) -> list[dict]:
    """Every (table, row, period) the page shows, with ours and a status: ok, apart, no_facts, no_recipe."""
    basis = basis or page.get("basis") or CONSOLIDATED
    fam = cf.family(basis)
    memo: dict = {}
    out = []
    for _, table, _ in TABLES:
        for row, by_period in (page.get("tables") or {}).get(table, {}).items():
            for period, theirs in by_period.items():
                ours_rows, why = _ours(cf, fam, basis, table, period, memo)
                rec = {"company": symbol, "scrip": scrip, "basis": basis, "family": fam, "period": period, "table": table,
                       "row": row, "screener": theirs, "ours": None, "diff": None, "status": "", "note": ""}
                if ours_rows is None:
                    rec.update(status="no_facts", note=why)
                elif row not in ours_rows:
                    rec.update(status="no_recipe", note=f"no {fam} recipe for {row} yet")
                else:
                    got = ours_rows[row]
                    if got.value is None:
                        rec.update(status="no_facts", note=got.note)
                    else:
                        rec.update(ours=round(got.value, 2), diff=round(got.value - theirs, 2),
                                   status="ok" if exact(got.value, theirs, row) else "apart", note=got.note)
                out.append(rec)
    return out


def run(sink, companies: list[tuple[str, str]], workers: int = 8, day: str | None = None) -> dict:
    """Read only: the stored screener pages (screener_crosscheck.stored_pages) and the stored facts docs in R2. No request to
    NSE, BSE or screener."""
    from .screener_crosscheck import stored_pages
    from .screener_download import unpack

    pages_by_symbol, newest = stored_pages(sink, day)

    def one(item: tuple[str, str]) -> dict:
        scrip, symbol = item
        entry = {"scrip": scrip, "symbol": symbol, "rows": [], "skipped": None}
        stored = pages_by_symbol.get(symbol) or {}
        if not stored:
            entry["skipped"] = "no stored page"
            return entry
        facts = CompanyFacts(sink.list_objects(f"{xbrl_facts.PREFIX}{scrip}/"), sink.get_object)
        if not facts.results and not facts.annual:
            entry["skipped"] = "no stored facts"
        for basis, key in sorted(stored.items()):
            blob = sink.get_object(key)
            if not blob:
                continue
            page = parse_page(unpack(blob))
            entry["rows"] += compare(page, facts, scrip, symbol, page.get("basis") or basis)
        return entry

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(one, companies))
    return summarise(results, newest)


def summarise(results: list[dict], pages_day: str | None = None) -> dict:
    rows = [r for c in results for r in c["rows"]]
    by_row: dict[str, dict[str, int]] = {}
    for r in rows:
        key = f"{r['table']}: {r['row']}"
        counts = by_row.setdefault(key, {s: 0 for s in STATUSES})
        counts[r["status"]] += 1
    order = {t: i for i, (_, t, _) in enumerate(TABLES)}
    names = {t: rows_ for _, t, rows_ in TABLES}

    def sort_key(k: str):
        table, row = k.split(": ", 1)
        return order.get(table, 9), names.get(table, ()).index(row) if row in names.get(table, ()) else 99

    by_row = {k: by_row[k] for k in sorted(by_row, key=sort_key)}
    for counts in by_row.values():
        compared = counts["ok"] + counts["apart"]
        counts["exact_share"] = round(counts["ok"] / compared, 4) if compared else None
    companies = []
    for c in results:
        apart = [r for r in c["rows"] if r["status"] == "apart"]
        companies.append({"symbol": c["symbol"], "scrip": c["scrip"], "skipped": c["skipped"],
                          "ok": sum(1 for r in c["rows"] if r["status"] == "ok"), "apart": len(apart),
                          "no_facts": sum(1 for r in c["rows"] if r["status"] == "no_facts"),
                          "no_recipe": sum(1 for r in c["rows"] if r["status"] == "no_recipe"),
                          "rows_apart": sorted({f"{r['table']}: {r['row']}" for r in apart})})
    total = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    return {"pages_day": pages_day, "companies": len(results), "pairs": len(rows), "by_status": total, "by_row": by_row,
            "per_company": companies, "rows": rows}


CSV_HEADER = ("company", "basis", "period", "table", "row", "screener", "ours", "diff", "status", "recipe note")


def to_csv(summary: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_HEADER)
    for r in summary["rows"]:
        w.writerow([r["company"], r["basis"], r["period"], r["table"], r["row"], r["screener"],
                    "" if r["ours"] is None else r["ours"], "" if r["diff"] is None else r["diff"], r["status"], r["note"]])
    return buf.getvalue()


def to_json(summary: dict) -> str:
    return json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=1, ensure_ascii=False)


def to_markdown(summary: dict, day: str) -> str:
    lines = [f"# Screener rows, one fixed recipe a row ({day})", "",
             f"Pages stored on {summary['pages_day'] or 'no day'}; {summary['companies']} companies, {summary['pairs']} pairs: "
             + ", ".join(f"{k} {v}" for k, v in summary["by_status"].items()) + ".",
             f"A pair is exact within ₹{ABS_TOL:g} Cr or {REL_TOL * 100:g}% of screener's figure (a percent row within "
             f"{PCT_TOL:g} point). No fitting: one recipe a row, by template (screener_view.py).", "",
             "## By row", "", "| Row | Exact | Apart | Exact share | No facts | No recipe |", "|---|---|---|---|---|---|"]
    for key, c in summary["by_row"].items():
        share = "-" if c["exact_share"] is None else f"{c['exact_share'] * 100:.1f}%"
        lines.append(f"| {key} | {c['ok']} | {c['apart']} | {share} | {c['no_facts']} | {c['no_recipe']} |")
    lines += ["", "## By company", "", "| Company | Exact | Apart | No facts | No recipe | Rows apart |", "|---|---|---|---|---|---|"]
    for c in sorted(summary["per_company"], key=lambda c: (-c["apart"], c["symbol"])):
        apart = ", ".join(c["rows_apart"]) or ("(" + c["skipped"] + ")" if c["skipped"] else "")
        lines.append(f"| {c['symbol']} | {c['ok']} | {c['apart']} | {c['no_facts']} | {c['no_recipe']} | {apart} |")
    return "\n".join(lines) + "\n"


def render(summary: dict) -> str:
    out = [f"screener-rows: {summary['companies']} companies, {summary['pairs']} pairs: "
           + ", ".join(f"{k} {v}" for k, v in summary["by_status"].items())]
    for key, c in summary["by_row"].items():
        share = "-" if c["exact_share"] is None else f"{c['exact_share'] * 100:.1f}%"
        out.append(f"  {key:45s} exact {c['ok']:>4} apart {c['apart']:>4} ({share})")
    return "\n".join(out)
