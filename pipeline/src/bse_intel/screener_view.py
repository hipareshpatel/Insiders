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

- a year (FYxx, March year end): the next year's annual-report facts doc (its prior-year comparative: FY25 from the FY26 report)
  or the year's own, whichever holds the year, then the Q4 results file when it holds it, then the nearest later report (a report
  two years later can carry stray facts at that date; CompanyFacts.year), else the Q4 file as it is. A Q4 file is read in its
  12-month context. Lenders file no annual-report XBRL on NSE: always the Q4 file. A balance sheet at a March year end is read the same way (the instant at the year end);
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
- Depreciation, Profit before tax = ProfitBeforeTax + associates' share (only where the company's own layout puts it inside PBT:
  SegmentProfitBeforeTax, else ASSOCIATES_DEFAULT_INCLUDE) + regulatory deferral movement, Tax % = TaxExpense / PBT, Net Profit = ProfitLossForPeriod (the website's Net
  Profit is the whole profit). Named rows not on the page: Tax, Net Profit (owners) (= profit for EPS), Minority share, Associates'
  share, Exceptional items, Exceptional items AT (= exceptional - tax x exceptional / PBT; the exceptional itself when that tax is
  larger than it), Profit for PE (= owners' profit - exceptional AT).

Corporate balance sheet (instant): Equity Capital = EquityShareCapital; Reserves = OtherEquity; Borrowings = BorrowingsNoncurrent +
BorrowingsCurrent + lease liabilities (elements, else described rows "lease" of the other financial liabilities) + described rows
"current maturities" (not of a lease when lease elements are used); Fixed Assets = PPE + Goodwill + OtherIntangibleAssets +
InvestmentProperty + exploration and evaluation assets + biological assets + right-of-use (element RightOfUseAssets, else the described
row "Right-of-use assets" of the other non-current (financial) assets); CWIP = CapitalWorkInProgress + IntangibleAssetsUnderDevelopment; Investments = NoncurrentInvestments + CurrentInvestments +
InvestmentsAccountedForUsingEquityMethod; Total (Liabilities and Assets) = Assets - min(DeferredTaxAssetsNet, DeferredTaxLiabilitiesNet) (a year-end column, B4_NET_ANY_BASIS);
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

import bisect
import csv
import io
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date

from . import xbrl_facts
from .memory_gaps import quarter_end
from .periods import quarter_index
from .metrics import CONSOLIDATED, STANDALONE
from .screener_fill import _section_table, _basis_of, cash_year_of, period_of

ABS_TOL, REL_TOL = 1.0, 0.0005          # a pair is exact within 1 Cr or 0.05% of screener's figure
PCT_TOL = 0.51                           # screener prints whole percent
PCT_ROWS = ("OPM %", "Financing Margin %", "Tax %")
STATUSES = ("ok", "apart", "no_facts", "no_recipe", "before_cutoff", "before_listing")
# the quarters compared start here (owner, 29 Oct 2026: "quarters from FY26"): every FY26 quarter is NSE's integrated filing, and the
# older ones carry screener's merger restatements and the older file format; a quarter before it is listed as before_cutoff, never
# counted in the exact share. Years and balance sheets are compared as before.
FIRST_QUARTER = "Q1FY26"
LISTING_FROM = "Q1FY24"       # before_listing is decided only from here: the years and quarters screener shows for a recent listing
# a period screener shows from before the company's first results on any exchange (its prospectus, or the year-ago column of its first
# results) is before_listing, never counted (owner, 29 Oct 2026: "we don't need it at all"): no facts for it, earlier than the first
# results file we hold, and not on BSE's results list for the company (raw/bse-results-xbrl/<scrip>/list.json, so only once the BSE
# fill has asked; a company listed on BSE before NSE has those quarters there). Measured 29 Oct 2026, run 40837941625: 1,253 of the
# 1,458 FY26 quarters we had no figure for end before the company's NSE listing date.

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
# a right-of-use asset row sits under any of these in Fixed Assets for screener: 66 company-periods of 34 companies closed by the
# three added parents (KIMS cons Q4FY26 gap -1,128.2 = row 1,128.3 under OtherNoncurrentFinancialAssets; JSW Steel Sep-26 4,689; Eternal
# Sep-26 5,360; run 41164053629, srules/bscf report rule 1)
ASSET_PARENTS = ("OtherNoncurrentAssetsOthers", "OtherNoncurrentAssets", "OtherNoncurrentFinancialAssets",
                 "OtherNoncurrentFinancialAssetsOthers")
# exploration and evaluation assets and biological assets (other than bearer plants, which are PPE) are Fixed Assets for screener: Coal
# India cons Q4FY23 -4,924.4 = 4,924.9, Oil India FY25/FY26 -2,482.7 / -3,894.6, Atul, Godrej Industries (10 company-periods; srules/bscf
# report rule 2)
FIXED_ASSET_EXTRAS: tuple[str, ...] = ()   # exploration and biological assets: +7 / -29 rows when added (run 41166426469), so Screener does not
# add them as a rule; the names: AssetsArisingFromExplorationForAndEvaluationOfMineralResources, BiologicalAssetsOtherThanBearerPlants
LEASE_ELEMENTS = ("LeaseLiabilitiesNoncurrent", "LeaseLiabilitiesCurrent", "NoncurrentLeaseLiabilities", "CurrentLeaseLiabilities")
# a line of the other current financial liabilities, tagged by its own element: in screener's Borrowings in 58 rows of 23
# companies (the 500 largest, run 40759776253: the gap = the element, screener above ours, every one an annual report)
FINANCE_LEASE_MATURITIES = "CurrentMaturitiesOfFinanceLeaseObligations"
# the current maturities of long-term debt tagged by their own element (help article 11: they are debt): in screener's
# Borrowings and not in ours in 129 rows of about 40 companies (L&T Q4FY21-FY26 22,719 / 31,373 / 26,399 Cr, Hyundai, KPR Mill,
# Dr Reddy's, Arvind, Titan: run 40874998205, screener above ours, the gap = the element). Behind the switch SCREENER_CMLTD (off until measured on/off: screener-rows on main and on a branch that turns it on).
LT_DEBT_MATURITIES = "CurrentMaturitiesOfLongTermDebt"
# the levies and discounts out of Sales (and Expenses): (elements, described row of the Other expenses breakdown)
LEVIES = {"excise": (("ExciseDuty",), r"^\s*excise"),
          "sales tax": (("SalesTax", "ValueAddedTax", "GoodsAndServicesTax", "SalesTaxAndValueAddedTax"),
                        r"^\s*(sales tax|vat\b|value added tax|gst\b|goods (and|&) services tax)"),
          # DiscountingCharges too: every company-year apart by it is our Sales and Expenses both above screener's by exactly it
          # (JSW Cement FY25 27.78 Cr, Yatharth, Borosil, Renuka: 35 years of 17 companies, all annual reports; run 40802884540)
          "discounts": (("TradeDiscounts", "SalesDiscounts", "Discounts", "Rebates", "DiscountingCharges"),
                        r"^\s*(trade )?(discount|rebate)s?\b")}
from .screener_parts import FINANCE_MEMBER as FIN_SERVICES_ROW  # noqa: E402 - one pattern for both (L&T's and Grasim's wording)
LOSS_ON_DISPOSAL = "LossOnDisposalDiscardDemolishmentAndDestructionOfDepreciablePropertyPlantAndEquipment"
ASSOCIATES = "ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod"
# the same share under its two split names (the apart pairs of 10 company-years where the recipe added nothing carry them; srules/annual
# report rule 2): read the joint element, else the sum of these
ASSOCIATES_SPLIT = ("ShareOfProfitLossOfAssociatesAccountedForUsingEquityMethod",
                    "ShareOfProfitLossOfJointVenturesAccountedForUsingEquityMethod")
SEGMENT_PBT = "SegmentProfitBeforeTax"
# the associates' share is in PBT (and in Other Income, or Expenses for a loss) when the company's own layout puts it there, as screener
# does: the undimensioned SegmentProfitBeforeTax says which (_share_in_pbt). With no segment figure this default decides. Measured
# 31 Oct 2026 (run 41164053629): a share added to PBT is right for 195 company-bases (870 PBT quarters), wrong for 28 (+27 mixed), so the
# default stays "include" until the owner's on/off measurement
ASSOCIATES_DEFAULT_INCLUDE = True   # measured 31 Oct 2026: False made quarterly PBT 95.0% -> 90.4% exact (run 41172104462)
ASSOCIATES_RULE_ON_YEARS = False   # the presentation rule on a year's P&L (off: measured worse there)
# a standalone sheet nets min(DTA, DTL) from the total like a consolidated one when both are filed (not a half-year column). Infosys
# standalone FY25: Assets 124,936 - min(497, 1,062) = 124,439 = screener; consolidated netted 754 ok / 64 apart, standalone filers matched
# both ways (1,371 without, 30 with), so the switch is measured on/off (srules/bscf report rule 7)
B4_NET_ANY_BASIS = False   # measured 31 Oct 2026 (screener-rows run 41166426469): +50 / -78 rows on; standalone filers net both ways
EXPENSE_ROW_PARENTS = ("OtherExpenses",)
# a row of other financial liabilities that is bank debt by its own words: Titan standalone "Secured and Unsecured Payable to Banks"
# 7,043 Cr FY25 and 14,314 Cr FY26 = screener's Borrowings less ours, exactly (its gold on loan; measured 28 Oct 2026)
# a supplier's or buyer's credit too (Hindalco FY25 "Supplier's credit" 1,713 Cr = the gap, cons and standalone; a temporary
# overdraft of 13 Cr in the same table is not in screener's figure); a "lease" that is not a lease liability is not debt (JSW
# Steel "Payable for sale and lease back of an under construction asset" 1,286 Cr, which screener leaves out)
# filers misspell the words (Hindustan Unilever "Lease Liablities" 365-404 Cr, Coal India "Lease Liabiiities" 3.30 Cr, both in
# screener's figure), so the pattern is "lease" followed by "lia", not the whole word
# and in other ways (Persistent "CurrentbLease Liability", MTAR "lease libaility", Belrise "Lease libilities", Avalon "Lease
# Obligations", Asahi India "Liability for Leased ...": 16 rows of 8 companies in the 500 largest, screener above ours)
LEASE_ROW = r"lease\w*\s*(lia|lib|obl)|liab\w*\s+for\s+leas"
# under a FINANCIAL-liability parent a row named "lease" (or "leases", followed by any word) is a lease liability: "Lease Laibility" (KPIT,
# SCI), "Payable for Lease Obiligation" (Dixon -252.7 / -312.0 / -417.8), "Lease" / "LEASE" (JSL, Granules), "Leases" (PGEL), "Financial
# Lease" (Maruti): 22 rows apart, ours below screener's (srules/bscf report rule 4c). A sale and lease back is not (JSW Steel)
# a lease liability however it is spelt (KPIT, SCI "Laibility", Dixon "Lease Obiligation", JSL/Granules "Lease", PGEL "Leases", Maruti
# "Financial Lease"); never a rent, a deposit or a receivable that only mentions a lease, nor a sale and lease back
LEASE_ROW_FINANCIAL = LEASE_ROW + r"|^(?!.*(sale\s+and\s+lease|lease\s*back|rent|deposit|receivable|advance)).*\bleases?\b"
# a lease liability filed under the NON-financial other liabilities (Ambuja FY25 "CURRENT LEASE LIABILITY" 304.14, Concor FY24
# "Lease liability-Ind AS 116" 746.11, Delhivery FY25 243.88: 18 rows of 12 companies, the gap exactly) is still debt
LEASE_PARENTS = ("OtherNoncurrentLiabilitiesOthers", "OtherCurrentLiabilitiesOthers", "OtherNoncurrentLiabilities",
                 "OtherCurrentLiabilities")
BANK_DEBT_ROW = r"payable to banks?|due to banks?|gold (on )?loan|metal loans?|(supplier|buyer)'?s'? credit"
# a loss on investments only: an impairment of investments stays in Expenses (Tech Mahindra standalone Q4FY24-Q4FY26, Cipla
# Q4FY26, Purvankara, Kolte-Patil, Jagran: about 11 rows apart by exactly the impairment row, none exact by it; run 40793194881)
INVESTMENT_LOSS = r"^\s*(net\s+)?loss\b.{0,25}\binvestments?\b"
# a fair value (gain) / loss ON INVESTMENTS in the Other expenses breakdown is not an operating cost for screener (TMCV Q2FY27 consolidated
# "Fair value (gain)/loss on equity investments measured at FVTPL" 708 Cr: Operating Profit 1,940 + 708 = 2,648 = screener, 5 of 5 quarters;
# srules/quarters report rule 2). It needs "investment" and never a derivative, commodity or foreign exchange line: TMPV Q1FY27 "Foreign
# exchange loss/(gain) and commodity derivatives fair value adjustments" 150 Cr stays in screener's Expenses
FAIR_VALUE_INVESTMENT = r"^(?!.*(derivative|commodit|foreign|exchange|forex|hedg)).*(fair.value.*\binvestments?\b|\binvestments?\b.*fair.value)"
DISCONTINUED = "ProfitLossFromDiscontinuedOperationsAfterTax"
REGULATORY_DEFERRAL = "NetMovementInRegulatoryDeferralAccountBalancesRelatedToProfitOrLossAndTheRelatedDeferredTaxMovement"

CORPORATE, BANK, NBFC, INSURER = "corporate", "bank", "nbfc", "insurer"


@dataclass
class Row:
    value: float | None        # None: an element the recipe needs is not in the facts
    note: str



def _cmltd() -> bool:
    from .settings import _switch

    return _switch("SCREENER_CMLTD")

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


GAP_HINT_MIN = 2.0     # Cr: a smaller gap equals too many filed facts by chance to be a lead


def gap_hints(r: _Reader, gap: float, limit: int = 3) -> list[str]:
    """The filed facts of the column's period whose size equals a row's gap (screener's figure less ours) within ₹1 Cr: an
    element, or a breakdown row by its own words. A lead to where the item screener adds or leaves out sits (L&T's yearly
    Interest: its bank charges), for the larger batch's pattern search; never part of a recipe."""
    if abs(gap) < GAP_HINT_MIN:
        return []
    found = getattr(r, "_money", None)
    if found is None:
        facts = r.facts
        found = [(el, v) for el, v in facts.find(".", **r.at)]
        names = {row[0] for row in facts.rows}
        # a "description" that is a unit or a blank ("INR", "NA") names nothing
        found += [(f"{el} [{text.strip()[:60]}]", v) for el, text, v in facts.described(tuple(names), ".", joined=True, **r.at)
                  if len(re.sub(r"[^A-Za-z]", "", text)) >= 4]
        r._money = found
    hits = sorted((abs(abs(v) - abs(gap)), label, v) for label, v in found if v and abs(abs(v) - abs(gap)) <= ABS_TOL)
    return [f"{label} {_fmt(v)}" for _, label, v in hits[:limit]]


def _fmt(v: float) -> str:
    return f"{v:,.2f}"


def _sum_rows(rows: list[tuple[str, str, float]]) -> float:
    return sum(r[2] for r in rows)


# the lines a two-line gap match may use: the statement's own lines and the breakdown rows of other expenses and exceptional items
# (an outside review's subset-sum idea, 29 Oct 2026); cash-flow, OCI, segment and related-party facts equal a gap by chance too often
PAIR_NOISE = re.compile(r"Adjustments|CashFlow|Classified|IncreaseDecrease|Comprehensive|Segment|RelatedParty|Reclassified|"
                        r"Disposals|Additions|Payments|Proceeds|Received|Paid|Dividend|Equity|Shares|PerShare|CashEquivalents|Tax(?!es)", re.I)
PAIR_PARENTS = ("OtherExpenses", "Expenses", "ExceptionalItems", "ExceptionalItemsBeforeTax")


def gap_pairs(r: _Reader, gap: float, limit: int = 3) -> list[str]:
    """Two filed lines whose sum (or difference) equals a row's gap within ₹1 Cr, where no single line does; and, when the
    exceptional items are filed as a breakdown, the sum of their losses and of their gains on their own. A lead only."""
    if abs(gap) < GAP_HINT_MIN:
        return []
    cand = getattr(r, "_pair_lines", None)
    if cand is None:
        facts = r.facts
        cand = [(el, v) for el, v in facts.find(".", **r.at) if v and not PAIR_NOISE.search(el)]
        rows = [(el, t, v) for el, t, v in facts.described(PAIR_PARENTS, ".", joined=True, **r.at)
                if v and len(re.sub(r"[^A-Za-z]", "", t)) >= 4]
        cand += [(f"{el} [{t.strip()[:40]}]", v) for el, t, v in rows]
        exc = [v for el, t, v in rows if el.startswith("ExceptionalItems")]
        if len(exc) >= 2:
            if (loss := sum(v for v in exc if v < 0)):
                cand.append(("exceptional losses (sum of the breakdown)", loss))
            if (gain := sum(v for v in exc if v > 0)):
                cand.append(("exceptional gains (sum of the breakdown)", gain))
        cand = sorted(set(cand), key=lambda x: -abs(x[1]))[:120]
        r._pair_lines = cand
    g = abs(gap)
    singles = [(abs(abs(v) - g), f"{label} {_fmt(v)}") for label, v in cand
               if label.startswith("exceptional ") and abs(abs(v) - g) <= ABS_TOL]
    if any(abs(abs(v) - g) <= ABS_TOL for label, v in cand if not label.startswith("exceptional ")):
        return [x for _, x in sorted(singles)][:limit]       # a single line already says it (gap_hints)
    sizes = sorted((abs(v), i) for i, (_, v) in enumerate(cand))
    keys = [x for x, _ in sizes]
    hits = []
    for i, (a, va) in enumerate(cand):
        # the other line's size for a sum (g - |a|) or a difference (|a| - g, |a| + g)
        for sign, want in (("+", g - abs(va)), ("-", abs(va) - g), ("-", abs(va) + g)):
            if want <= 0:
                continue
            for k in range(bisect.bisect_left(keys, want - ABS_TOL), bisect.bisect_right(keys, want + ABS_TOL)):
                j = sizes[k][1]
                if j != i and (sign == "-" or j > i):
                    b, vb = cand[j]
                    hits.append((abs(abs(keys[k]) - want), f"{a} {sign} {b}"))
    return [x for _, x in sorted(singles + hits)][:limit]


# screener's Expenses sub-rows, each a percent of Sales (screener_schedules.py), against our own parts of the same Expenses: the
# part whose gap is the row's gap is where screener moved a line, and only that part's own lines are searched (owner, 29 Oct
# 2026: "It can be two lines or 3 lines also, why don't we check sub rows"); a lead only, no recipe reads it
MATERIAL = ("CostOfMaterialsConsumed", "PurchasesOfStockInTrade", "ChangesInInventoriesOfFinishedGoodsWorkInProgressAndStockInTrade")
EMPLOYEE = ("EmployeeBenefitExpense",)
_MONTH = {"1": "Jun", "2": "Sep", "3": "Dec", "4": "Mar"}


def column_of(table: str, period: str) -> str | None:
    """Our period label as screener's column heading: FY25 -> "Mar 2025", Q1FY26 -> "Jun 2025" (March years only)."""
    m = re.fullmatch(r"FY(\d\d)", period) if table == "annual" else re.fullmatch(r"Q([1-4])FY(\d\d)", period)
    if not m:
        return None
    if table == "annual":
        return f"Mar 20{m[1]}"
    year = 2000 + int(m[2]) - (0 if m[1] == "4" else 1)
    return f"{_MONTH[m[1]]} {year}"


def _percent_text(text) -> float | None:
    try:
        return float(str(text).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def expense_parts(answer: dict, column: str, sales: float, expenses: float) -> tuple[dict[str, float], dict[str, float]] | None:
    """Screener's material and employee cost in crore from its Expenses sub-rows of one column, and the rest as its Expenses
    less those two (the quarters' sub-rows have no manufacturing or other cost); with each part's rounding in crore, as screener
    shows a percent to two places for some companies and to whole numbers for others (Maruti FY26 "72%": about 900 Cr)."""
    got, slack = {}, {}
    for name, row in (answer or {}).items():
        if not isinstance(row, dict) or (v := _percent_text(raw := row.get(column))) is None:
            continue
        places = len(str(raw).split(".")[1].rstrip("% ")) if "." in str(raw) else 0
        for part in ("material", "employee"):
            if part in name.lower():
                got[part] = got.get(part, 0.0) + v * sales / 100
                slack[part] = slack.get(part, 0.0) + 0.5 * 10 ** -places * abs(sales) / 100
    if not got:
        return None
    got.setdefault("material", 0.0)
    got.setdefault("employee", 0.0)
    got["rest"] = expenses - got["material"] - got["employee"]
    slack = {"material": slack.get("material", 0.0), "employee": slack.get("employee", 0.0)}
    slack["rest"] = slack["material"] + slack["employee"]
    return got, slack


def part_lines(r: _Reader) -> list[tuple[str, float]]:
    """The lines a part's gap may be made of: the other expenses breakdown, the exceptional-items breakdown, and the statement's
    loss, gain, impairment, provision and charge lines."""
    cand = [(f"{el} [{t.strip()[:40]}]", v) for el, t, v in r.facts.described(PAIR_PARENTS, ".", joined=True, **r.at)
            if v and len(re.sub(r"[^A-Za-z]", "", t)) >= 4]
    cand += [(el, v) for el, v in r.facts.find(r"Loss|Gain|Impairment|Provision|Charges|ExchangeDifference|Exceptional|WrittenOff|"
                                              r"WriteOff|Regulatory|ShareOfProfit", **r.at) if v and not PAIR_NOISE.search(el)]
    return sorted(set(cand), key=lambda x: -abs(x[1]))[:40]


def lines_making(cand: list[tuple[str, float]], gap: float, most: int = 3, limit: int = 3) -> list[str]:
    """One, two or three of the lines whose sizes add up to the gap within ₹1 Cr, fewest lines first."""
    from itertools import combinations
    g, out = abs(gap), []
    for n in range(1, most + 1):
        for combo in combinations(cand, n):
            if abs(sum(abs(v) for _, v in combo) - g) <= ABS_TOL:
                out.append(" + ".join(f"{label} {_fmt(v)}" for label, v in combo))
                if len(out) >= limit:
                    return out
        if out:
            return out
    return out


def part_gaps(r: _Reader, ours_expenses: float, answer: dict, column: str, sales: float, gap: float) -> tuple[str, str]:
    """(which part holds the gap, the lines inside that part that make it) for an Expenses row apart."""
    parts = expense_parts(answer, column, sales, ours_expenses + gap)     # screener's Expenses: ours + its gap
    if parts is None:
        return "", ""
    theirs, slack = parts
    mat = sum(v for n in MATERIAL if (v := r.cr(n)) is not None)
    emp = sum(v for n in EMPLOYEE if (v := r.cr(n)) is not None)
    ours = {"material": mat, "employee": emp, "rest": ours_expenses - mat - emp}
    gaps = {k: theirs[k] - ours[k] for k in ours}
    tol = {k: max(ABS_TOL, slack[k]) for k in ours}
    alone = [k for k in gaps if abs(gaps[k]) > tol[k]]
    where = ", ".join(f"{k} {gaps[k]:+.0f}" for k in alone) or "no part apart beyond rounding"
    found = ""
    if len(alone) == 1 and tol[alone[0]] < abs(gap) / 2:
        found = "; ".join(lines_making(part_lines(r), gaps[alone[0]]))
    return where, found


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


def _tax_pct(tax: float | None, pbt: float | None) -> float | None:
    """Screener divides the tax by the size of the PBT: a loss with a tax charge shows a positive rate (L&T standalone Q2FY26,
    PBT -2,982: screener +20.0; the 500 largest, run 40759776253: 289 quarters and 88 years exact by it, 1 year broken)."""
    return None if tax is None or not pbt else 100.0 * tax / abs(pbt)


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


def _associates(r: _Reader) -> float | None:
    """The share of profit of associates and joint ventures: the joint element, else the two split elements added."""
    v = r.cr(ASSOCIATES)
    if v is not None:
        return v
    parts = [x for n in ASSOCIATES_SPLIT if (x := r.cr(n)) is not None]
    return sum(parts) if parts else None


def _share_in_pbt(r: _Reader, filed_pbt: float | None, share: float | None) -> tuple[bool, str]:
    """Whether the associates' share goes into PBT, Other Income and Expenses: follow the company's own presentation. The undimensioned
    SegmentProfitBeforeTax equal to PBT + share (within 1 Cr) means the company presents the share inside its PBT: include (TATASTEEL,
    HINDALCO, ITC, BHARTIARTL, NTPC); equal to the filed ProfitBeforeTax: leave it out (RELIANCE, DLF, LT, TATACONSUM). No usable segment
    figure (absent, a filler 0, or neither): ASSOCIATES_DEFAULT_INCLUDE. Measured 31 Oct 2026 on 9 of 13 consolidated Q1/Q2FY27 files."""
    if not share:
        return True, ""
    if r.at.get("months") != 3 and not ASSOCIATES_RULE_ON_YEARS:   # a year: included as before (on years the rule moved 13 rows
        return True, ""                                                # right and 38 wrong, run 41166426469)
    seg = r.cr(SEGMENT_PBT)
    if seg and filed_pbt is not None:
        if abs(seg - filed_pbt) <= ABS_TOL:
            return False, "the segment PBT equals the filed PBT"
        if abs(seg - (filed_pbt + share)) <= ABS_TOL:
            return True, "the segment PBT holds the share"
    return ASSOCIATES_DEFAULT_INCLUDE, "default"


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
    # a loss on investments booked as a row of other expenses is an exceptional item for screener, so in Other Income, not
    # Expenses (docs: profit from the sale of investments / associates is exceptional). M&M Q4FY26 "Loss from investments
    # related to subsidiaries, associates and joint ventures" 410.2 Cr = the 410.47 Cr Expenses gap (run 40726456306)
    inv_rows = r.rows(EXPENSE_ROW_PARENTS, INVESTMENT_LOSS)
    # and a fair value (gain)/loss on investments, signed as filed (TMCV Q2FY27 708 Cr), once when a row matches both patterns
    if r.at.get("months") == 3:   # a results file's quarter only: in the annual reports the rule moved 0 rows right and 31 wrong (Grasim FY23
        # 8,736.95, Zydus, Lloyds Metals, OFSS; run 41166426469); proven on TMCV's quarters
        inv_rows += [x for x in r.rows(EXPENSE_ROW_PARENTS, FAIR_VALUE_INVESTMENT) if x not in inv_rows]
    inv_loss = _sum_rows(inv_rows) if inv_rows else 0.0
    loss += inv_loss
    # bank charges are a finance cost for screener: HAL, IndiGo and IOC, every year FY24-FY26 and both bases, the yearly
    # Interest gap = the annual report's BankCharges (run 40735344929); the quarters' files carry no such element
    bank = r.cr("BankCharges") or 0.0
    share_filed = share = _associates(r)
    # a loss from associates is an expense for screener, a profit other income: 43 of 43 quarters where Expenses and Other
    # Income were both apart by the share, PBT exact, had a loss (JSW Steel 8, Power Grid 7, Nestle 7, TVS 7, Adani Ports 5,
    # Bajaj Auto 3: Q2FY25 580 Cr, KTM; run 40735344929)
    pbt_filed = pbt
    in_pbt, in_pbt_why = _share_in_pbt(r, pbt_filed, share)
    if not in_pbt:      # the company's own layout keeps the share below PBT: out of PBT, Other Income, Expenses and Operating Profit
        share = 0.0
    assoc_loss = -share if share is not None and share < 0 else 0.0
    regulatory = r.cr(REGULATORY_DEFERRAL)
    # a net regulatory EXPENSE (a negative movement in the regulatory deferral balances) is an expense for screener, a net
    # regulatory income other income: NHPC Q4FY26 -559.22 = the Expenses gap, Tata Power Q1FY27 -153.09, Power Grid FY26 cons
    # -2,774 (with its rows; the owner's NHPC and Tata Power sheets, 29 Oct 2026; 62 quarters and about 18 years of 11 utilities)
    reg_expense = -regulatory if regulatory is not None and regulatory < 0 else 0.0
    sales = None if rev is None else rev - lev
    out["Sales"] = Row(sales, ("RevenueFromOperations" + (" less " + ", ".join(levy_notes) if levy_notes else "")
                               if rev is not None else "missing RevenueFromOperations") + src)
    interest = None if fc is None else fc + fin + bank
    out["Interest"] = Row(interest, ("FinanceCosts" + (" + " + fin_note if fin_note else "") + (f" + BankCharges {_fmt(bank)}" if bank else "")
                                     if fc is not None
                                     else "missing FinanceCosts") + src)
    out["Depreciation"] = Row(dep, ("DepreciationDepletionAndAmortisationExpense" if dep is not None
                                    else "missing DepreciationDepletionAndAmortisationExpense") + src)
    expenses = None
    if None not in (exp, fc, dep):
        expenses = exp - fc - dep - lev - fin - loss - bank + assoc_loss + reg_expense
        parts = ["FinanceCosts", "depreciation"] + (["levies"] if lev else []) + (["financial-services finance cost"] if fin else []) \
            + (["bank charges"] if bank else []) \
            + ([f"loss on disposal of PPE {_fmt(loss - inv_loss)}"] if loss - inv_loss else []) \
            + ([f"loss on investments {_fmt(inv_loss)}"] if inv_loss else [])
        out["Expenses"] = Row(expenses, "Expenses less " + ", ".join(parts)
                              + (f", plus the associates' loss {_fmt(assoc_loss)}" if assoc_loss else "")
                              + (f", plus the net regulatory expense {_fmt(reg_expense)}" if reg_expense else "") + src)
    else:
        out["Expenses"] = Row(None, "missing " + ", ".join(n for n, v in (("Expenses", exp), ("FinanceCosts", fc),
                                                                            ("DepreciationDepletionAndAmortisationExpense", dep)) if v is None) + src)
    op = None if sales is None or expenses is None else sales - expenses
    out["Operating Profit"] = Row(op, "Sales - Expenses" + src)
    out["OPM %"] = Row(_pct(op, sales), "Operating Profit / Sales" + src)
    oi_parts, exc = r.cr("OtherIncome"), r.cr("ExceptionalItemsBeforeTax")
    # screener has no line for discontinued operations: their profit after tax is in its PBT (Hindustan Unilever FY26 13,812 +
    # 4,407 = 18,219, the ice-cream demerger; Q3FY26 2,919 + 4,485 = 7,404; ITC Q3FY25 + 203.44, the hotels; run 40735344929)
    discontinued = r.cr(DISCONTINUED)
    # screener's PBT holds the associates' share ("profit from associates is always other ordinary income") and a utility's
    # net movement in regulatory deferral balances, both of which SEBI's results format puts below the filed PBT (measured
    # 28 Oct 2026 on the owner's screener Excel files: 39 of 55 quarters with associates, e.g. Coal India Q4FY26 14,510.7 +
    # 116.1 = 14,626.75; NTPC Q1FY26 5,281.2 + 2,007.3 + 476.6 = 7,765.06; Power Grid Q1FY26 4,330.2 + 212.8 - 44.4 = 4,498.57).
    # Reliance, DLF, L&T and Tata Consumer are the other way (their layout keeps the share below PBT): _share_in_pbt follows it.
    filed_pbt = pbt
    if pbt is not None:
        pbt = pbt + (share or 0.0) + (regulatory or 0.0) + (discontinued or 0.0)
    parts = None if oi_parts is None else oi_parts + (exc or 0.0) + (share or 0.0) + assoc_loss + (regulatory or 0.0) + reg_expense \
        + (discontinued or 0.0) - loss
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
    out["Profit before tax"] = Row(pbt, ("ProfitBeforeTax" + (" + associates' share" if share else "")
                                         + (" (share left out: " + in_pbt_why + ")" if share_filed and not in_pbt else "")
                                         + (" + regulatory deferral movement" if regulatory else "")
                                         + (" + discontinued operations after tax" if discontinued else "") if pbt is not None
                                         else "missing ProfitBeforeTax") + src)
    if filed_pbt is not None and pbt != filed_pbt:
        out["PBT as filed"] = Row(filed_pbt, "ProfitBeforeTax" + src)
    out["Tax"] = Row(tax, "TaxExpense" + src)
    out["Tax %"] = Row(_tax_pct(tax, pbt), "TaxExpense / |Profit before tax|" + src)
    whole, owners = r.cr("ProfitLossForPeriod"), r.cr("ProfitOrLossAttributableToOwnersOfParent")
    if not owners and whole and not r.cr("ProfitOrLossAttributableToNonControllingInterests"):
        owners = whole      # a filler zero (Paradeep Q2FY26-Q1FY27: owners 0 and minority 0): the owners' share is the whole profit
    out["Net Profit"] = Row(whole, ("ProfitLossForPeriod (whole profit)" if whole is not None else "missing ProfitLossForPeriod") + src
                            + (f"; owners' share {_fmt(owners)}" if owners is not None else ""))
    if owners is not None:
        out["Net Profit (owners)"] = Row(owners, "ProfitOrLossAttributableToOwnersOfParent (profit for EPS)" + src)
    minority = r.cr("ProfitOrLossAttributableToNonControllingInterests")
    if minority is not None:
        out["Minority share"] = Row(minority, "ProfitOrLossAttributableToNonControllingInterests" + src)
    if share_filed is not None:
        out["Associates' share"] = Row(share_filed, ASSOCIATES + src)
        if share_filed and not in_pbt:      # so the profit-line rules know the whole profit is PBT - Tax + this (corrected_pl)
            out["Associates' share outside PBT"] = Row(share_filed, "share kept below PBT: " + in_pbt_why + src)
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
    # PBT as filed, a negative exceptional item in it: adding it back fitted HDFC Bank alone (6 rows, its Net Profit apart by the
    # same item in each) and broke 15 at SBI, Bank of Baroda, Indian Bank, Bank of India, J&K Bank, AU, ESAF and Fino (FY26
    # quarters audit, run 40837941625); HDFC Bank is a Known exception
    pbt = pbt_filed
    out["Profit before tax"] = Row(pbt, ("ProfitLossFromOrdinaryActivitiesBeforeTax"
                                         if pbt_filed is not None else "missing ProfitLossFromOrdinaryActivitiesBeforeTax") + src)
    out["Tax"] = Row(tax, "TaxExpense" + src)
    out["Tax %"] = Row(_tax_pct(tax, pbt), "TaxExpense / |Profit before tax|" + src)
    name = "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates"
    net = r.cr(name)
    if net is None and r.cr("ProfitLossForThePeriod") is not None:
        net, name = r.cr("ProfitLossForThePeriod"), "ProfitLossForThePeriod"
    minority = r.cr("ProfitLossOfMinorityInterest")
    # the website's Net Profit is the whole profit, the minority's share included (policy; a bank's consolidated quarter:
    # HDFC Bank Q3FY24-Q1FY27 and ICICI Q3FY24-Q2FY26, the gap = ProfitLossOfMinorityInterest each quarter, run 40735344929)
    whole = None if net is None else net + (minority or 0.0)
    out["Net Profit"] = Row(whole, (name + (" + ProfitLossOfMinorityInterest" if minority else "") if net is not None
                                    else "missing " + name) + src)
    if net is not None:
        out["Net Profit (owners)"] = Row(net, name + src)
    if minority is not None:
        out["Minority share"] = Row(minority, "ProfitLossOfMinorityInterest" + src)
    share = r.cr("ShareOfProfitLossOfAssociates")
    if share is not None:
        out["Associates' share"] = Row(share, "ShareOfProfitLossOfAssociates" + src)
    _exceptional_rows(out, exc, tax, pbt_filed, net)
    return out


def nbfc_pl(r: _Reader, source: str = "") -> dict[str, Row]:
    """An NBFC (Ind AS NBFC template): every row of a lender's page (Revenue, Financing Profit) and a holding company's
    (Sales, Operating Profit) from the template's elements."""
    src = f" [{source}]" if source else ""
    out: dict[str, Row] = {}
    for row, name in (("Revenue", "RevenueFromOperations"), ("Interest", "FinanceCosts"),
                      ("Depreciation", "DepreciationDepletionAndAmortisationExpense"), ("Profit before tax", "ProfitBeforeTax"),
                      ("Tax", "TaxExpense"), ("Net Profit", "ProfitLossForPeriod"),
                      ("Net Profit (owners)", "ProfitOrLossAttributableToOwnersOfParent")):
        v = r.cr(name)
        out[row] = Row(v, (name if v is not None else "missing " + name) + src)
    # the associates' share is in PBT as for every company (policy): the holding companies and NBFCs of the 500 largest were
    # short by it in 93 quarters (Bajaj Holdings Q2FY24 1,464.08; Jio Financial Q3FY24 66.11; M&M Finance Q3FY24 12.75)
    share, pbt = r.cr(ASSOCIATES), out["Profit before tax"].value
    if share and pbt is not None:
        out["PBT as filed"] = Row(pbt, "ProfitBeforeTax" + src)
        out["Profit before tax"] = Row(pbt + share, f"ProfitBeforeTax + associates' share {_fmt(share)}" + src)
    out["Tax %"] = Row(_tax_pct(out["Tax"].value, out["Profit before tax"].value), "TaxExpense / |Profit before tax|" + src)
    # screener's own identities hold on every NBFC of the every-company run (116 companies, 5,009 periods, no miss): Operating
    # Profit = Sales - Expenses, Financing Profit = Revenue - Expenses - Interest (no depreciation), Other Income the plug of PBT.
    # A lender's page shows Revenue / Financing Profit, a holding company's Sales / Operating Profit (Bajaj Holdings Q4FY26
    # Expenses 36.97; Aditya Birla Capital Q4FY26 12,106.74 - 3,100.59 - 81.88 = 8,924.27; the owner's sheets, 29 Oct 2026)
    rev, exp = out["Revenue"].value, r.cr("Expenses")
    fc, dep, pbt = out["Interest"].value, out["Depreciation"].value, out["Profit before tax"].value
    out["Sales"] = Row(rev, out["Revenue"].note)
    if None not in (rev, exp, fc, dep):
        e = exp - fc - dep
        out["Expenses"] = Row(e, "Expenses less FinanceCosts, depreciation" + src)
        out["Operating Profit"] = Row(rev - e, "Sales - Expenses" + src)
        out["OPM %"] = Row(_pct(rev - e, rev), "Operating Profit / Sales" + src)
        out["Financing Profit"] = Row(rev - e - fc, "Revenue - Expenses - Interest" + src)
        out["Financing Margin %"] = Row(_pct(rev - e - fc, rev), "Financing Profit / Revenue" + src)
        if pbt is not None:
            out["Other Income"] = Row(pbt + dep + fc - (rev - e), "PBT + Depreciation + Interest - Operating Profit" + src)
    return out


def insurer_pl(r: _Reader, source: str = "") -> dict[str, Row]:
    """An insurer (LI / GI): Net Profit only (LIC's PBT is in two regimes: docs/audit/screener-rows-2026-10-28.md)."""
    v = r.cr("ProfitLossAfterTaxAndExtraordinaryItems")
    return {"Net Profit": Row(v, ("ProfitLossAfterTaxAndExtraordinaryItems" if v is not None
                                  else "missing ProfitLossAfterTaxAndExtraordinaryItems") + (f" [{source}]" if source else ""))}


# ---- the profit-line rules, applied where the statements are written and again where they are read ----

SLIP_MIN = 5.0     # Cr: a profit this far from PBT - tax, and on the other side of zero, is a slip
SLIP_SHARE = 0.5


def corrected_pl(rows: dict[str, float], fam: str) -> dict[str, float]:
    """A quarter's or year's P&L values (row name -> number, as stored) with the profit lines made consistent; the same dict when nothing
    changes. Three rules, each from a measured case (31 Oct 2026), in this order:
    1. owners' profit against the whole profit and the minority's share: owners + minority must add up to Net Profit within
       max(0.01 Cr, 0.5%) (the rule reit_results.read applies), else the owners' profit is the whole less the minority's. ATUL Q2FY26
       consolidated, NSE's own file: profit 182.37, owners 87.95, minority 3.13 (Screener 182, Tijori 179.24 = 182.37 - 3.13), so
       Q2FY27 showed +77.1% where the truth is about -13%.
    2. with no minority row, an owners' profit of exactly 0 beside a non-zero net profit is a filler and the net profit is the owners'
       (204 live quarters at 0: PNB Housing Q2FY27, CreditAccess, Kaynes Q2FY26, Goldiam; nbfc_pl lacks corporate_pl's guard).
    3. a corporate quarter whose profit is on the other side of zero from Profit before tax - Tax, and further from it than
       max(5 Cr, half of it), has PBT - Tax as its profit (APARINDS Q1FY27: PAT -138.56 beside EBITDA 757.57; four other sites 467.45).
       The corporate PBT already holds the associates' share (unless the company's layout keeps it below PBT: the row "Associates' share
       outside PBT" is then added back), the regulatory deferral movement and the discontinued operations after tax
       (corporate_pl) and Tax is the continuing tax, so PBT - Tax is the whole profit; the owners' is that less the minority's share
       (without a minority row it is guarded only when it equals the whole). A genuine loss (same side of zero) stays. Other families
       are not guarded: their PBT is not built the same way."""
    owners, net, minority = rows.get("Net Profit (owners)"), rows.get("Net Profit"), rows.get("Minority share")
    out = dict(rows)
    if owners is not None and net is not None:
        if minority is not None:
            # a minority share as large as the whole profit is itself the slip, not the owners' (measured 31 Oct 2026, the dry run of
            # statements-correct against Screener: FINCABLES Q4FY25 191.71 would have become 0, ABREL Q4FY26 10.84 -104.86; Screener
            # 192 and 5), so the owners' figure stays as filed; below it the rule held (CGPOWER Q2FY26 18.24 -> 284.29, Screener 284;
            # BANCOINDIA Q1FY26 164.06 -> 109.52, Screener 110; SUNFLAG Q1FY25 717.31 -> 27.89, Screener 28)
            if abs(owners + minority - net) > max(0.01, abs(net) / 200) and abs(minority) < abs(net):
                out["Net Profit (owners)"] = round(net - minority, 2)
        elif owners == 0 and net != 0:
            out["Net Profit (owners)"] = net
    pbt, tax = rows.get("Profit before tax"), rows.get("Tax")
    if fam == CORPORATE and pbt is not None and tax is not None:
        # PBT - Tax is the whole profit only when the associates' share is in PBT; a share kept below PBT (corporate_pl: its layout) is added
        whole = round(pbt - tax + (rows.get("Associates' share outside PBT") or 0.0), 2)
        for row in ("Net Profit", "Net Profit (owners)"):
            value = out.get(row)
            if value is None:
                continue
            if row == "Net Profit":
                expected = whole
            else:
                share = out.get("Minority share")
                if share is None:
                    share = 0.0 if value == out.get("Net Profit") else None
                if share is None:
                    continue
                expected = round(whole - share, 2)
            if value * expected < 0 and abs(value - expected) > max(SLIP_MIN, SLIP_SHARE * abs(expected)):
                out[row] = expected
    return out if out != rows else rows



def pl_rows(fam: str, r: _Reader, fallback: _Reader | None = None, source: str = "") -> dict[str, Row]:
    if fam == BANK:
        return bank_pl(r, source)
    if fam == NBFC:
        return nbfc_pl(r, source)
    if fam == INSURER:
        return insurer_pl(r, source)
    return corporate_pl(r, fallback, source)


# --- balance sheet ------------------------------------------------------------------------------------------------

def corporate_bs(r: _Reader, source: str = "", half_year: bool = False, standalone: bool = False) -> dict[str, Row]:
    """``half_year``: a September balance sheet, read from its results file, where screener puts intangibles under development in
    Fixed Assets (HCL Tech, UltraTech, JSW Steel, Hindustan Zinc, Adani Green Q2FY27: the CWIP and Fixed Assets gaps both =
    IntangibleAssetsUnderDevelopment, run 40735344929); in a year's column they are CWIP (Reliance FY26 237,686). Its total is the
    filed Assets, no deferred tax offset. ``standalone``: a standalone year-end total is the filed Assets too (every company, run
    40797693366: 147 standalone sheets exact without min(DTA, DTL), 35 with it, those of 15 companies, TCS, Infosys and Wipro among
    them; consolidated 1,099 with it, 102 without)."""
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
        rows = [x for x in r.rows(LIABILITY_PARENTS, rf"current maturit|{BANK_DEBT_ROW}") if not re.search("lease", x[1], re.I)]
        lease_note = f"lease {_fmt(lease)} ({', '.join(lease_names)})"
    else:
        rows = r.rows(LIABILITY_PARENTS, rf"{LEASE_ROW_FINANCIAL}|current maturit|{BANK_DEBT_ROW}")
        seen = {(t, round(v, 2)) for _, t, v in rows}
        for x in r.rows(LEASE_PARENTS, LEASE_ROW):      # a parent and its "Others" member can carry the same line
            if (x[1], round(x[2], 2)) not in seen:
                seen.add((x[1], round(x[2], 2)))
                rows.append(x)
        lease_note = ""
    fl = r.cr(FINANCE_LEASE_MATURITIES)
    if fl:      # the element, not the same line again as a described row
        rows = [x for x in rows if not re.search(r"finance lease", x[1], re.I)]
        lease += fl
        lease_note = " + ".join(x for x in (lease_note, f"{FINANCE_LEASE_MATURITIES} {_fmt(fl)}") if x)
    ltm = r.cr(LT_DEBT_MATURITIES) if _cmltd() else None
    if ltm:     # the element, not the same line again as a described row
        rows = [x for x in rows if not (re.search(r"current maturit", x[1], re.I) and abs(abs(x[2]) - abs(ltm)) <= 0.5)]
        lease += ltm
        lease_note = " + ".join(x for x in (lease_note, f"{LT_DEBT_MATURITIES} {_fmt(ltm)}") if x)
    extra = _sum_rows(rows)
    row_note = ("rows " + "; ".join(f"{t[:50]} {_fmt(v)}" for _, t, v in rows)) if rows else ""
    borrowings = debt + lease + extra
    # a balance sheet with no debt line, no lease and no maturity row is a company with no borrowings (0), not missing facts
    has_sheet = r.cr("Assets") is not None
    out["Borrowings"] = Row(borrowings if debt_names or lease_names or fl or ltm or rows or has_sheet else None,
                            " + ".join(x for x in (" + ".join(debt_names), lease_note, row_note) if x) + src
                            if debt_names or lease_names or fl or ltm or rows else ("no borrowings, lease or maturity line: 0" if has_sheet
                                                                         else "missing BorrowingsNoncurrent and BorrowingsCurrent") + src)
    fixed, fixed_names = total("PropertyPlantAndEquipment", "Goodwill", "OtherIntangibleAssets", "InvestmentProperty")
    extras, extra_names = total(*FIXED_ASSET_EXTRAS)
    if extras:      # a filler 0 is no line
        fixed += extras
        fixed_names += extra_names
    rou = r.cr("RightOfUseAssets")
    rou_note = "RightOfUseAssets" if rou is not None else ""
    if rou is None:
        rou_rows = r.rows(ASSET_PARENTS, r"right.of.use")
        rou = _sum_rows(rou_rows) if rou_rows else None
        rou_note = ("right-of-use row " + _fmt(rou)) if rou_rows else ""
    iaud = r.cr("IntangibleAssetsUnderDevelopment") if half_year else None
    if iaud is not None:
        fixed_names.append("IntangibleAssetsUnderDevelopment")
    fa = fixed + (rou or 0.0) + (iaud or 0.0)
    out["Fixed Assets"] = Row(fa if fixed_names or rou else None,
                              " + ".join(fixed_names + ([rou_note] if rou_note else [])) + src if fixed_names or rou
                              else "missing PropertyPlantAndEquipment" + src)
    cwip, cwip_names = total("CapitalWorkInProgress", *(() if half_year else ("IntangibleAssetsUnderDevelopment",)))
    # a 0 only on a balance sheet: a results file without one (the Q4 files of FY21-FY23 often) has no CWIP to show
    out["CWIP"] = Row(cwip if cwip_names or has_sheet else None,
                      (" + ".join(cwip_names) or ("neither CapitalWorkInProgress nor IntangibleAssetsUnderDevelopment: 0" if has_sheet
                                                  else "no balance sheet in the file")) + src)
    inv, inv_names = total("NoncurrentInvestments", "CurrentInvestments", "InvestmentsAccountedForUsingEquityMethod")
    out["Investments"] = Row(inv if inv_names or has_sheet else None,
                             (" + ".join(inv_names) or ("no investments element: 0" if has_sheet else "no balance sheet in the file")) + src)
    assets, dta, dtl = r.cr("Assets"), r.cr("DeferredTaxAssetsNet"), r.cr("DeferredTaxLiabilitiesNet")
    # the half-year column is the filed total: HCL Tech, Adani Power, Adani Green, Wipro, Torrent Pharma Q2FY27 apart by exactly
    # min(DTA, DTL), while HCL Tech's year columns FY23-FY26 are exact with it (run 40735344929)
    offset = min(dta, dtl) if dta is not None and dtl is not None and not half_year and (B4_NET_ANY_BASIS or not standalone) else 0.0
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


def bs_rows(fam: str, r: _Reader, source: str = "", half_year: bool = False, standalone: bool = False) -> dict[str, Row]:
    if fam == BANK:
        return bank_bs(r, source)
    if fam == NBFC:
        return nbfc_bs(r, source)
    if fam == INSURER:
        return {}
    return corporate_bs(r, source, half_year, standalone)


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
        self.bse_periods: set[str] | None = None     # the quarters BSE's results list holds; None: BSE not asked yet

    def before_listing(self, period: str) -> bool:
        """Whether ``period`` (a quarter, or a year "FY25": its March quarter) is before the company's first results on either
        exchange: earlier than every results doc we hold AND than every quarter on BSE's list for it (which reaches back years, so a
        hole at the start of what NSE gave us is not taken for a listing). Only from LISTING_FROM: an older year of a long-listed
        company may be older than BSE's list reaches. No BSE list, or an empty one (a failed answer is kept as one), decides nothing."""
        quarter = f"Q4{period}" if period.startswith("FY") else period
        index = quarter_index(quarter)
        if index is None or index < quarter_index(LISTING_FROM) or not self.bse_periods:
            return False
        held = [i for i in (quarter_index(p) for p, _ in self.results) if i is not None]
        on_bse = [i for i in (quarter_index(p) for p in self.bse_periods) if i is not None]
        return bool(held) and bool(on_bse) and index < min(held) and index < min(on_bse)

    def _load(self, key: str | None) -> xbrl_facts.Facts | None:
        if key is None:
            return None
        if key not in self._cache:
            body = self.loader(key)   # a failed read raises: an unread file must not pass for a missing one (blind review)
            try:
                self._cache[key] = xbrl_facts.Facts(xbrl_facts.loads(body)) if body else None
            except Exception:   # noqa: BLE001 - a damaged object is no facts
                self._cache[key] = None
        return self._cache[key]

    def result(self, period: str, basis: str) -> xbrl_facts.Facts | None:
        return self._load(self.results.get((period, basis)))

    def family(self, basis: str) -> str:
        for (period, b), key in sorted(self.results.items(), key=lambda kv: quarter_index(kv[0][0]) or 0, reverse=True):
            if b == basis and (f := self._load(key)) is not None:
                return family(f.doc.get("template"))
        return CORPORATE

    def year(self, fy: str, basis: str, fam: str, instant: bool = False):
        """(facts, label, Q4 facts) of a March year, in this order: the newest of the year's own annual report and the next
        year's (whose comparative it is) that holds the year; else the Q4 results file when it holds it; else the nearest later
        report that holds it; else the Q4 file as it is. A lender: always the Q4 file. A report two or more years later is the last resort because it can carry a stray fact
        at that date (UltraTech's FY26 report tags Assets at 31 Mar 2024 in a note, with no balance sheet there, which made FY24's
        Borrowings 0: TODO 129, 113 pairs), yet for a year with no nearer source it often holds the full sheet (HCL Tech FY20
        from its FY22 report, 16 rows equal to screener's)."""
        end = _fy_end(fy)
        q4 = self.result(f"Q4{fy}", basis)
        if fam != CORPORATE or end is None:
            return q4, f"results file Q4{fy}", None

        def holds(f) -> bool:
            return f.cr("Assets", instant=end) is not None if instant else \
                any(f.cr(n, end=end, months=12) is not None for n in ("RevenueFromOperations", "ProfitLossForPeriod"))

        def holding(offsets) -> tuple | None:
            reports = [(afy, key) for (afy, b), key in self.annual.items() if b == basis and _fy_num(afy) - _fy_num(fy) in offsets]
            for afy, key in sorted(reports, key=lambda r: offsets.index(_fy_num(r[0]) - _fy_num(fy))):
                f = self._load(key)
                if f is None:
                    continue
                if holds(f):
                    return f, f"annual report {afy}", q4
            return None

        near = holding([1, 0])                              # the newest first, as before: the next year's report, then the year's own
        if near is not None:
            return near
        if q4 is not None and holds(q4):           # a Q4 file without the year's balance sheet (HAL, NTPC FY22) is no source for it
            return q4, f"results file Q4{fy}", None
        return holding(list(range(2, 100))) or (q4, f"results file Q4{fy}", None)   # the nearest later report first


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
    reader = None
    if period.startswith("YE:"):
        result = None, "year end not March: no recipe source yet"
    elif table == "quarters":
        end, f = quarter_end(period), cf.result(period, basis)
        reader = _Reader(f, end=end, months=3) if f is not None and end else None
        result = (pl_rows(fam, reader, source=f"results file {period}"), "") if reader else (None, f"no results facts for {period}")
    elif table in ("annual", "cash_flow"):
        f, label, q4 = cf.year(period, basis, fam)
        end = _fy_end(period)
        reader = _Reader(f, end=end, months=12) if f is not None and end is not None else None
        if reader is None:
            result = None, f"no annual-report or Q4 results facts for {period}"
        elif table == "annual":
            fallback = _Reader(q4, end=end, months=12) if q4 is not None else None
            result = pl_rows(fam, reader, fallback, label), ""
        else:
            result = cf_rows(reader, label), ""
    else:   # balance
        end = quarter_end(period)
        if period.startswith("Q4"):
            f, label, _ = cf.year(period[2:], basis, fam, instant=True)
        else:
            f, label = cf.result(period, basis), f"results file {period}"
        reader = _Reader(f, instant=end) if f is not None and end else None
        sheet = bs_rows(fam, reader, label, half_year=not period.startswith("Q4"), standalone=basis == STANDALONE) if reader else None
        result = (sheet, "") if reader \
            else (None, f"no facts for {period}")
    memo[k] = result
    memo[("reader", k)] = reader
    return result


def compare(page: dict, cf: CompanyFacts, scrip: str = "", symbol: str = "", basis: str | None = None,
            sub_rows: dict | None = None) -> list[dict]:
    """Every (table, row, period) the page shows, with ours and a status: ok, apart, no_facts, no_recipe."""
    basis = basis or page.get("basis") or CONSOLIDATED
    fam = cf.family(basis)
    memo: dict = {}
    out = []
    for _, table, _ in TABLES:
        for row, by_period in (page.get("tables") or {}).get(table, {}).items():
            for period, theirs in by_period.items():
                rec = {"company": symbol, "scrip": scrip, "basis": basis, "family": fam, "period": period, "table": table,
                       "row": row, "screener": theirs, "ours": None, "diff": None, "status": "", "note": "", "hints": ""}
                if table == "quarters" and (quarter_index(period) or 0) < quarter_index(FIRST_QUARTER):
                    rec.update(status="before_cutoff", note=f"before {FIRST_QUARTER}: not compared")
                    out.append(rec)
                    continue
                ours_rows, why = _ours(cf, fam, basis, table, period, memo)
                if ours_rows is None and table in ("quarters", "annual") and cf.before_listing(period):
                    rec.update(status="before_listing", note=f"{period} is before the company's first results on NSE or BSE: not compared")
                elif ours_rows is None:
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
                        reader = memo.get(("reader", (table, period)))
                        if rec["status"] == "apart" and row not in PCT_ROWS and reader is not None:
                            rec["hints"] = "; ".join(gap_hints(reader, theirs - got.value))
                            rec["pairs"] = "; ".join(gap_pairs(reader, theirs - got.value))
                            sales = ((page.get("tables") or {}).get(table, {}).get("Sales") or {}).get(period)
                            answer = (sub_rows or {}).get(("quarters" if table == "quarters" else "profit-loss") + "|Expenses")
                            col = column_of(table, period)
                            if row == "Expenses" and answer and col and sales:
                                rec["parts"], rec["part lines"] = part_gaps(reader, got.value, answer, col, sales, theirs - got.value)
                out.append(rec)
    return out


def _sector(sink, scrip: str) -> tuple[str, str]:
    """(sector, industry) as the site shows them ("Chemicals > Dyes And Pigments": the companies table, company_master.py),
    memory's dossier when the company row has none, so a rule that is a sector's or an industry's practice shows as one
    group's rows apart in a larger batch (owner, 28 Oct 2026: "find the pattern: sector or industry practice")."""
    row, dossier = None, None
    try:
        row = sink.company(scrip) if hasattr(sink, "company") else None
    except Exception:  # noqa: BLE001 - no company row is no sector, never the company's skip
        row = None
    if not (row or {}).get("sector"):
        try:
            dossier = sink.get_dossier(scrip) if hasattr(sink, "get_dossier") else None
        except Exception:  # noqa: BLE001
            dossier = None
    src = row if (row or {}).get("sector") else (dossier or {})
    return (src.get("sector") or "unknown"), (src.get("industry") or "")


def _bse_periods(sink, scrip: str) -> set[str] | None:
    """The quarters on the company's kept BSE results list (bse_results_xbrl.list_key), None when BSE was never asked."""
    from .bse_results_xbrl import list_key

    try:
        blob = sink.get_object(list_key(scrip))
        return {x["period"] for x in json.loads(blob).get("links") or []} if blob else None
    except Exception:  # noqa: BLE001 - an unreadable list is no list: nothing is called before listing
        return None


def run(sink, companies: list[tuple[str, str]], workers: int = 8, day: str | None = None) -> dict:
    """Read only: the stored screener pages (screener_crosscheck.stored_pages) and the stored facts docs in R2. No request to
    NSE, BSE or screener."""
    from .screener_crosscheck import stored_pages
    from .screener_download import unpack

    pages_by_symbol, newest = stored_pages(sink, day)
    from . import screener_schedules as ss
    bundles: dict[str, str] = {}
    for key in sorted(sink.list_objects(ss.PREFIX)):       # the newest day's file of a company wins
        m = re.fullmatch(re.escape(ss.PREFIX) + r"[\d-]+/([^/_]+)\.json\.gz", key)
        if m:
            bundles[m[1]] = key

    def one(item: tuple[str, str]) -> dict:
        try:
            return company(item)
        except Exception as exc:  # noqa: BLE001 - one company's bad page or listing is that company's skip, not the run's end
            return {"scrip": item[0], "symbol": item[1], "rows": [], "skipped": f"error: {type(exc).__name__}: {exc}"[:200]}

    def company(item: tuple[str, str]) -> dict:
        scrip, symbol = item
        entry = {"scrip": scrip, "symbol": symbol, "rows": [], "skipped": None}
        entry["sector"], entry["industry"] = _sector(sink, scrip)
        stored = pages_by_symbol.get(symbol) or {}
        if not stored:
            entry["skipped"] = "no stored page"
            return entry
        facts = CompanyFacts(sink.list_objects(f"{xbrl_facts.PREFIX}{scrip}/"), sink.get_object)
        facts.bse_periods = _bse_periods(sink, scrip)
        if not facts.results and not facts.annual:
            entry["skipped"] = "no stored facts"
        bundle = {}
        if symbol in bundles and (raw := sink.get_object(bundles[symbol])):
            bundle = ss.unpack(raw).get("pages") or {}
        for basis, key in sorted(stored.items()):
            blob = sink.get_object(key)
            if not blob:
                continue
            page = parse_page(unpack(blob))
            answers = (bundle.get(page.get("basis") or basis) or {}).get("answers") or {}
            entry["rows"] += compare(page, facts, scrip, symbol, page.get("basis") or basis, answers)
        return entry

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(one, companies))
    return summarise(results, newest)


def summarise(results: list[dict], pages_day: str | None = None) -> dict:
    for c in results:
        for r in c["rows"]:
            r.setdefault("sector", c.get("sector") or "unknown")
            r.setdefault("industry", c.get("industry") or "")
    rows = [r for c in results for r in c["rows"]]
    # sector x row: a rule that is a sector's practice shows as one sector's rows apart
    by_sector_row: dict[str, dict[str, list[int]]] = {}
    for r in rows:
        if r["status"] in ("ok", "apart"):
            cell = by_sector_row.setdefault(r["sector"], {}).setdefault(f"{r['table']}: {r['row']}", [0, 0])
            cell[r["status"] == "apart"] += 1
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
        companies.append({"symbol": c["symbol"], "scrip": c["scrip"], "skipped": c["skipped"], "sector": c.get("sector") or "unknown",
                          "industry": c.get("industry") or "",
                          "ok": sum(1 for r in c["rows"] if r["status"] == "ok"), "apart": len(apart),
                          "no_facts": sum(1 for r in c["rows"] if r["status"] == "no_facts"),
                          "no_recipe": sum(1 for r in c["rows"] if r["status"] == "no_recipe"),
                          "rows_apart": sorted({f"{r['table']}: {r['row']}" for r in apart})})
    # a gap lead seen in two or more companies on one row is a pattern to check before the next recipe
    by_hint: dict[tuple[str, str], set[str]] = {}
    for r in rows:
        for hint in filter(None, (r.get("hints") or "").split("; ")):
            label = hint.rsplit(" ", 1)[0]
            label = label[label.index("[") + 1:-1].lower() if label.endswith("]") and "[" in label else label
            by_hint.setdefault((f"{r['table']}: {r['row']}", label), set()).add(r["company"])
    hints = sorted(([k[0], k[1], sorted(v)] for k, v in by_hint.items() if len(v) >= 2), key=lambda h: (-len(h[2]), h[0], h[1]))
    by_pair: dict[tuple[str, str], set[str]] = {}
    for r in rows:
        for pair in filter(None, (r.get("pairs") or "").split("; ")):
            label = re.sub(r"\s*\[[^\]]*\]", "", re.sub(r" -?[\d,]+\.\d\d$", "", pair)).lower()
            by_pair.setdefault((f"{r['table']}: {r['row']}", label), set()).add(r["company"])
    pairs = sorted(([k[0], k[1], sorted(v)] for k, v in by_pair.items() if len(v) >= 3), key=lambda h: (-len(h[2]), h[0], h[1]))
    by_part: dict[str, int] = {}
    by_part_line: dict[str, set[str]] = {}
    for r in rows:
        if r.get("parts"):
            for part in re.findall(r"(material|employee|rest) [+-]", r["parts"]) or ["no part apart beyond rounding"]:
                by_part[f"{r['table']}: {part}"] = by_part.get(f"{r['table']}: {part}", 0) + 1
        for found in filter(None, (r.get("part lines") or "").split("; ")):
            label = re.sub(r" -?[\d,]+\.\d\d", "", found).lower()
            by_part_line.setdefault(f"{r['table']}: {label}", set()).add(r["company"])
    part_lines_seen = sorted(([k, sorted(v)] for k, v in by_part_line.items() if len(v) >= 3), key=lambda x: -len(x[1]))
    total = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    return {"pages_day": pages_day, "companies": len(results), "pairs": len(rows), "by_status": total, "by_row": by_row,
            "per_company": companies, "by_sector_row": by_sector_row, "gap_hints": hints, "gap_pairs": pairs,
            "expense_parts": by_part, "expense_part_lines": part_lines_seen, "rows": rows}


CSV_HEADER = ("company", "sector", "industry", "basis", "period", "table", "row", "screener", "ours", "diff", "status", "recipe note",
              "gap matches", "gap pairs", "expense parts apart", "lines in that part")


def to_csv(summary: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_HEADER)
    for r in summary["rows"]:
        w.writerow([r["company"], r.get("sector", "unknown"), r.get("industry", ""), r["basis"], r["period"], r["table"], r["row"], r["screener"],
                    "" if r["ours"] is None else r["ours"], "" if r["diff"] is None else r["diff"], r["status"], r["note"],
                    r.get("hints", ""), r.get("pairs", ""), r.get("parts", ""), r.get("part lines", "")])
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
    lines += ["", "## By sector: the rows a sector has most apart", "",
              "A row apart in most of one sector's pairs and exact elsewhere is a sector practice to find, not a company's one-off.", "",
              "| Sector | Companies | Exact share | Rows most apart (apart / compared) |", "|---|---|---|---|"]
    members: dict[str, int] = {}
    for c in summary["per_company"]:
        members[c["sector"]] = members.get(c["sector"], 0) + 1
    for sector, cells in sorted(summary.get("by_sector_row", {}).items()):
        ok = sum(v[0] for v in cells.values())
        bad = sum(v[1] for v in cells.values())
        worst = sorted(((k, v) for k, v in cells.items() if v[1]), key=lambda kv: -kv[1][1] / sum(kv[1]))[:4]
        share = f"{ok / (ok + bad) * 100:.0f}%" if ok + bad else "-"
        lines.append(f"| {sector} | {members.get(sector, 0)} | {share} | "
                     + ", ".join(f"{k} {v[1]}/{sum(v)}" for k, v in worst) + " |")
    lines += ["", "## Gap matches in two or more companies", "",
              "A filed fact equal to a row's gap (within ₹1 Cr) in several companies: a lead to check, never a rule by itself.", "",
              "| Row | Fact | Companies |", "|---|---|---|"]
    for row, label, names in summary.get("gap_hints", [])[:40]:
        lines.append(f"| {row} | {label} | {len(names)}: {', '.join(names[:8])} |")
    lines += ["", "## By company", "", "| Company | Sector | Exact | Apart | No facts | No recipe | Rows apart |",
              "|---|---|---|---|---|---|---|"]
    for c in sorted(summary["per_company"], key=lambda c: (-c["apart"], c["symbol"])):
        apart = ", ".join(c["rows_apart"]) or ("(" + c["skipped"] + ")" if c["skipped"] else "")
        group = c["sector"] + (f" > {c['industry']}" if c.get("industry") else "")
        lines.append(f"| {c['symbol']} | {group} | {c['ok']} | {c['apart']} | {c['no_facts']} | {c['no_recipe']} | {apart} |")
    return "\n".join(lines) + "\n"


def render(summary: dict) -> str:
    out = [f"screener-rows: {summary['companies']} companies, {summary['pairs']} pairs: "
           + ", ".join(f"{k} {v}" for k, v in summary["by_status"].items())]
    for key, c in summary["by_row"].items():
        share = "-" if c["exact_share"] is None else f"{c['exact_share'] * 100:.1f}%"
        out.append(f"  {key:45s} exact {c['ok']:>4} apart {c['apart']:>4} ({share})")
    return "\n".join(out)
