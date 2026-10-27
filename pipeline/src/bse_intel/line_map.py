"""One map of the lines cards and memory use, and what each is called in every source (TODO 93, F209; owner 26 Oct 2026:
"row names mapping is very important, we haven't done it for all types of companies").

A line is a canonical name (``revenue``, ``pat_owners``, ``interest_earned`` ...) with the names it goes by:

- ``xbrl``: the element names ``xbrl.py`` reads for it on every template, ``xbrl_by`` the names it adds (or, with the
  value ``None`` on a template in ``SUPPRESSED``, refuses) on one template: Ind AS (``INDAS``), other-than-bank
  (``OTHERTHANBANK``), ``NBFC``, ``BANKING``, general insurance ``GI``, life insurance ``LI``. These are copied from
  ``xbrl.RESULT_TAGS``, ``GENERAL_INSURANCE_TAGS``, ``LIFE_INSURANCE_TAGS``, ``RATIO_TAGS``, ``EPS_VARIANTS`` and
  ``BALANCE_TAGS``; ``tests/test_line_map.py`` fails if the two ever differ, so this is not a second list that can drift.
- ``xbrl_seen``: element names found in a stored sample file of that template (``tests/fixtures``) that the code does NOT
  read yet. Each is a candidate for a line, nothing more: the test re-reads the sample to prove the name is there. They are
  how the gaps show (a bank's minority share, diluted EPS, a lender's fees and commission income).
- ``screener``: the row of screener.in's results tables (``Sales`` / ``Revenue``, ``Net Profit``, ``EPS in Rs`` ... as the
  stored pages print them: the rows of 4 sample pages, one a bank), ``tijori``: Tijori's row names (2 sample pages, no
  lender), ``tijori_lender`` the ones tried for a lender; ``pdf``: the printed labels ``pdf_referee`` matches.
- ``crosscheck_ours``: the stored metric names a cross-check compares the source's row against.

Evidence, said plainly (the repo's rule 0): a name here is one of
  1. read by the code today (``xbrl``): it is in the code's own tables;
  2. seen in a stored sample file (``xbrl_seen``, a screener or Tijori row listed from the sample pages): measured on that
     sample, which is one to four companies, never "every company";
  3. found in the repo's own text but with no sample (the PDF phrases come from ``pdf_referee`` regexes and their tests);
  4. absent: an empty tuple. ``unverified(key)`` lists the sources where nothing was found. Never read an empty source as
     "the source has no such line": it means nobody has looked yet.
Coverage over 10 companies of each template, on real stored files, is NOT measured here: ``scripts/line_map_coverage.py``
does it on the runner, where the stored files are.

Nothing here reads a file but ``config/xbrl_sums`` (the official calculation labels), and it changes no behaviour.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

TEMPLATES = ("INDAS", "OTHERTHANBANK", "NBFC", "BANKING", "GI", "LI")
SOURCES = ("xbrl", "screener", "tijori", "pdf")
# the key ``xbrl.taxonomy`` gives an instance, for the templates the code overlays: GI and LI are overlays on the base names
OVERLAID = ("GI", "LI")
SUMS_DIR = Path(__file__).resolve().parents[2] / "config" / "xbrl_sums"

# sample files (tests/fixtures) per template: what ``xbrl_seen`` was read from. GI and OTHERTHANBANK have none.
FIXTURES = {
    "INDAS": ("nse_vesuvius_halfyearly_dec_h2fy26", "bse_main_ind_as_532811_q3fy25"),
    "NBFC": ("nse_bajfin_q2fy27_cons", "nse_irfc_q4fy26_nbfc", "nse_iciciamc_q1fy27_nbfc"),
    "BANKING": ("nse_hdfcbank_q2fy27_cons", "bse_bank_542867_q3fy25"),
    "LI": ("nse_hdfclife_q2fy27_cons",),
}
# an element the template's overlay turns off: it names another account there (xbrl.LIFE_INSURANCE_TAGS)
SUPPRESSED = {"LI": ("ProvisionForTax", "CurrentTax")}
# screener rows that are not a line (ratios of other lines, the attachment link): never a gap
SCREENER_IGNORED = ("OPM %", "Tax %", "Financing Margin %", "Raw PDF")
# Tijori's section headings that hold sub-rows (EPS sits under "Quarterly Ratios"): not lines
TIJORI_IGNORED = ("Quarterly Ratios",)


@dataclass(frozen=True)
class Line:
    key: str
    label: str
    group: str                                         # income, cost, profit, eps, lender, insurer, ratio, cash, balance, derived
    xbrl: tuple[str, ...] = ()
    xbrl_by: dict = field(default_factory=dict)        # template -> names added there (first in the file wins as in the code)
    xbrl_seen: dict = field(default_factory=dict)      # template -> names seen in a sample, not read by the code
    screener: tuple[str, ...] = ()
    tijori: tuple[str, ...] = ()
    tijori_lender: tuple[str, ...] = ()
    pdf: tuple[str, ...] = ()
    crosscheck_ours: tuple[str, ...] = ()              # the stored names a cross-check compares (non-lender)
    crosscheck_ours_lender: tuple[str, ...] = ()
    derived_from: tuple[str, ...] = ()                 # lines our own code works out of others
    note: str = ""


def _l(key, label, group, **kw) -> Line:
    return Line(key, label, group, **kw)


LINES: tuple[Line, ...] = (
    # --- top line and income -------------------------------------------------------------------------------------
    _l("revenue", "Revenue from operations", "income",
       xbrl=("RevenueFromOperations",), xbrl_by={"GI": ("PremiumEarned",), "LI": ("NetPremiumIncome",)},
       screener=("Sales", "Revenue"), tijori=("Net Sales", "Sales"),
       tijori_lender=("Net Sales", "Sales", "Revenue", "Total Income", "Interest Earned", "Income from Operations"),
       pdf=("Revenue from operations", "Income from operations", "Sales from operations", "Net sales"),
       crosscheck_ours=("revenue",), crosscheck_ours_lender=("revenue", "interest_earned"),
       note="a lender's revenue is its revenue from operations, else interest earned (F186); GI = net earned premium, "
            "LI = net premium income. Tijori's lender row is configurable and NOT confirmed on any lender page"),
    _l("total_income", "Total income", "income", xbrl=("Income",), screener=(), pdf=("Total income",),
       note="revenue + other income; screener's Sales is sometimes this (the 'naming' class of the cross-check)"),
    _l("other_income", "Other income", "income", xbrl=("OtherIncome",), screener=("Other Income",)),
    _l("excise_duty", "Excise duty", "income", xbrl=("ExciseDuty",), note="inside revenue; revenue_net_excise is derived"),
    _l("fees_commission_income", "Fees and commission income", "lender",
       xbrl_seen={"NBFC": ("FeesAndCommissionIncome",)},
       note="an NBFC's second revenue line beside interest earned; not read, no other source named"),
    _l("dividend_income", "Dividend income", "lender", xbrl_seen={"NBFC": ("DividendIncome",)}),
    _l("other_operating_revenue", "Other revenue from operations", "lender", xbrl_seen={"NBFC": ("OtherRevenueFromOperations",)}),
    _l("interest_earned", "Interest earned / interest income", "lender", xbrl=("InterestEarned",),
       pdf=("Interest earned", "Total interest earned", "Total interest income"),
       note="a bank's top line, and an NBFC's interest income beside its revenue from operations (both templates tag it)"),
    _l("interest_on_advances", "Interest on advances", "lender", xbrl_seen={"BANKING": ("InterestOrDiscountOnAdvancesOrBills",)},
       pdf=("Interest earned on advances",), note="a sub-line of interest earned; never the revenue (pdf_referee rank 3)"),
    _l("income_on_investments", "Income on investments", "lender", xbrl_seen={"BANKING": ("RevenueOnInvestments",)}),
    _l("interest_expended", "Interest expended", "lender", xbrl=("InterestExpended",), screener=("Interest",),
       note="screener's Interest row sits under Revenue on a bank's page (HDFC Bank sample); that it is interest expended is "
            "an assumption, not measured"),
    _l("nii", "Net interest income", "derived", derived_from=("interest_earned", "interest_expended"),
       note="worked out as interest earned less interest expended (metrics.py); no source row named"),
    _l("pre_provision_operating_profit", "Operating profit before provisions", "lender",
       xbrl=("OperatingProfitBeforeProvisionAndContingencies",), screener=("Financing Profit",),
       note="screener's Financing Profit on a bank's page: same-line is an assumption, not measured"),
    _l("provisions", "Provisions (other than tax)", "lender", xbrl=("ProvisionsOtherThanTaxAndContingencies",)),
    # --- costs ---------------------------------------------------------------------------------------------------
    _l("raw_material_cost", "Cost of materials consumed", "cost", xbrl=("CostOfMaterialsConsumed",)),
    _l("purchases_stock_in_trade", "Purchases of stock-in-trade", "cost", xbrl=("PurchasesOfStockInTrade",)),
    _l("inventory_change", "Changes in inventories", "cost",
       xbrl=("ChangesInInventoriesOfFinishedGoodsWorkInProgressAndStockInTrade",)),
    _l("employee_cost", "Employee benefit expense", "cost", xbrl=("EmployeeBenefitExpense", "EmployeesCost")),
    _l("finance_cost", "Finance costs", "cost", xbrl=("FinanceCosts",), screener=("Interest",),
       note="screener's Interest row on a non-lender page; its definition against FinanceCosts is not measured"),
    _l("depreciation", "Depreciation and amortisation", "cost",
       xbrl=("DepreciationDepletionAndAmortisationExpense", "DepreciationAndAmortisationExpense"), screener=("Depreciation",)),
    _l("other_expenses", "Other expenses / operating expenses", "cost", xbrl=("OtherExpenses", "OperatingExpenses")),
    _l("total_expenses", "Total expenses", "cost", xbrl=("Expenses",), screener=("Expenses",)),
    _l("expenditure_excl_provisions", "Expenditure excluding provisions", "lender",
       xbrl_seen={"BANKING": ("ExpenditureExcludingProvisionsAndContingencies",)}),
    # --- profit --------------------------------------------------------------------------------------------------
    _l("exceptional_items", "Exceptional items", "profit", xbrl=("ExceptionalItemsBeforeTax", "ExceptionalItems")),
    _l("pbt_before_exceptional", "Profit before exceptional items and tax", "profit", xbrl=("ProfitBeforeExceptionalItemsAndTax",),
       xbrl_seen={"BANKING": ("ProfitBeforeExtraordinaryItemsAndTax",)}, note="used for EBITDA only; not kept in memory"),
    _l("share_associates", "Share of profit of associates and JVs", "profit",
       xbrl=("ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod",),
       xbrl_seen={"BANKING": ("ShareOfProfitLossOfAssociates",)}),
    _l("pbt", "Profit before tax", "profit", xbrl=("ProfitBeforeTax", "ProfitLossBeforeTax", "ProfitLossFromOrdinaryActivitiesBeforeTax"),
       xbrl_by={"GI": ("ProfitOrLossBeforeTax",)}, screener=("Profit before tax",), pdf=()),
    _l("current_tax", "Current tax", "profit", xbrl=("CurrentTax",)),
    _l("deferred_tax", "Deferred tax", "profit", xbrl=("DeferredTax",)),
    _l("tax_expense", "Tax expense", "profit", xbrl=("TaxExpense",),
       xbrl_by={"GI": ("ProvisionForTax",), "LI": ("ProvisionsForTaxes",)},
       note="LI: ProvisionForTax is the policyholders' tax, refused on that template (SUPPRESSED)"),
    _l("pat", "Profit for the period (PAT)", "profit",
       xbrl=("ProfitLossForPeriod", "ProfitLossForThePeriod"),
       xbrl_by={"GI": ("ProfitLossAfterTax",), "LI": ("ProfitLossAfterTaxAndExtraordinaryItems",)},
       xbrl_seen={"BANKING": ("ProfitLossFromOrdinaryActivitiesAfterTax",), "LI": ("ProfitLossAfterTaxBeforeExtraordinaryItems",)},
       screener=("Net Profit",), tijori=("Net Profit",), tijori_lender=("Net Profit",),
       pdf=("Profit for the period", "Net profit for the period/year/quarter", "Profit after tax"),
       crosscheck_ours=("pat",), crosscheck_ours_lender=("pat",),
       note="pdf_referee skips rows that say before / attributable / owners / continuing / discontinued / comprehensive"),
    _l("pat_group", "Profit after minority interest and associates (bank)", "profit",
       xbrl=("ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates",),
       note="replaces pat for a bank when tagged: its EPS is on it"),
    _l("pat_continuing", "Profit from continuing operations", "profit", xbrl=("ProfitLossForPeriodFromContinuingOperations",)),
    _l("pat_discontinued", "Profit from discontinued operations after tax", "profit",
       xbrl=("ProfitLossFromDiscontinuedOperationsAfterTax",)),
    _l("pat_owners", "Profit attributable to owners of the parent", "profit",
       xbrl=("ProfitOrLossAttributableToOwnersOfParent",)),
    _l("pat_minority", "Profit attributable to non-controlling interests", "profit",
       xbrl=("ProfitOrLossAttributableToNonControllingInterests",), xbrl_seen={"BANKING": ("ProfitLossOfMinorityInterest",)},
       note="memory only (F166). A bank's own element is seen in a sample but not read: its minority share is never stored"),
    _l("ebitda", "EBITDA", "derived", derived_from=("pbt_before_exceptional", "finance_cost", "depreciation", "other_income"),
       screener=("Operating Profit",),
       note="worked out by xbrl.py, dropped for every lender template. Screener's Operating Profit is a different definition "
            "(not measured against ours)"),
    _l("ebitda_margin", "EBITDA margin", "derived", derived_from=("ebitda", "revenue"), screener=("OPM %",)),
    # --- per share -----------------------------------------------------------------------------------------------
    _l("eps", "Basic EPS (first tagged in the file)", "eps",
       xbrl=("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", "BasicEarningsLossPerShareFromContinuingOperations",
             "BasicEarningsPerShare", "BasicEarningsPerShareAfterExtraordinaryItems", "BasicEarningsPerShareBeforeExtraordinaryItems"),
       xbrl_by={"GI": ("BasicAndDilutedEPSAfterExtraordinaryItemsNetOfTaxExpenseForThePeriodNotToBeAnnualized",),
                "LI": ("BasicAndDilutedEPSAfterExtraordinaryItemsNetOfTaxExpenseForThePeriodNotToBeAnnualized",)},
       screener=("EPS in Rs",), tijori=("EPS",), tijori_lender=("EPS",),
       pdf=("Earnings per equity share (basic)", "Basic"),
       crosscheck_ours=("eps", "basic_eps"), crosscheck_ours_lender=("eps", "basic_eps"),
       note="never on a card (owner rule 26 Oct 2026). Tijori's EPS sits under Quarterly Ratios and is adjusted for later share "
            "changes; annual tables have no EPS row"),
    _l("eps_total", "Basic EPS, continuing and discontinued", "eps",
       xbrl=("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",), note="memory only (F188, TODO 89)"),
    _l("eps_continuing", "Basic EPS, continuing operations", "eps",
       xbrl=("BasicEarningsLossPerShareFromContinuingOperations",), note="memory only (F188, TODO 89)"),
    _l("eps_diluted", "Diluted EPS", "eps",
       xbrl_seen={"INDAS": ("DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations",),
                  "NBFC": ("DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                           "DilutedEarningsLossPerShareFromContinuingOperations"),
                  "BANKING": ("DilutedEarningsPerShareAfterExtraordinaryItems", "DilutedEarningsPerShareBeforeExtraordinaryItems")},
       note="no diluted EPS is read from any template; GI and LI file one element for basic and diluted"),
    _l("paid_up_capital", "Paid-up equity share capital", "balance", xbrl=("PaidUpValueOfEquityShareCapital",)),
    # --- insurers ------------------------------------------------------------------------------------------------
    _l("gross_premium", "Gross premium", "insurer", xbrl_by={"GI": ("GrossPremiumsWritten",), "LI": ("GrossPremiumIncome",)}),
    _l("net_premium", "Net premium written", "insurer", xbrl_by={"GI": ("NetPremiumWritten",)},
       xbrl_seen={"LI": ("NetPremium",)}),
    _l("incurred_claims", "Claims incurred", "insurer", xbrl_by={"GI": ("IncurredClaims",)}),
    _l("commission", "Net commission", "insurer", xbrl_by={"GI": ("NetCommission",), "LI": ("NetCommission",)}),
    _l("first_year_premium", "First year premium", "insurer", xbrl_by={"LI": ("IncomeFirstYearPremium",)}),
    _l("renewal_premium", "Renewal premium", "insurer", xbrl_by={"LI": ("IncomeRenewalPremium",)}),
    _l("single_premium", "Single premium", "insurer", xbrl_by={"LI": ("IncomeSinglePremium",)}),
    _l("benefits_paid", "Benefits paid (net)", "insurer", xbrl_by={"LI": ("BenefitsPaidNet",)}),
    _l("surplus", "Net surplus / deficit", "insurer", xbrl_by={"LI": ("NetSurplusDeficit",)}),
    _l("investment_income", "Income from investments", "insurer", xbrl_seen={"LI": ("IncomeFromInvestmentsNet",)}),
    # --- ratios, as fractions in the file ------------------------------------------------------------------------
    _l("gnpa_pct", "Gross NPA %", "ratio", xbrl=("PercentageOfGrossNpa",), screener=("Gross NPA %",)),
    _l("nnpa_pct", "Net NPA %", "ratio", xbrl=("PercentageOfNpa",), screener=("Net NPA %",)),
    _l("roa_pct", "Return on assets %", "ratio", xbrl=("ReturnOnAssets",)),
    _l("combined_ratio", "Combined ratio", "ratio", xbrl=("CombinedRatio",)),
    _l("claims_ratio", "Incurred claims ratio", "ratio", xbrl=("IncurredClaimRatio",)),
    _l("retention_ratio", "Net retention ratio", "ratio", xbrl=("NetRetentionRatio",)),
    _l("expense_ratio", "Expenses of management ratio", "ratio", xbrl=("ExpensesOfManagementRatio",)),
    # --- cash flow (half-year and year files) --------------------------------------------------------------------
    _l("operating_cash_flow", "Cash flow from operating activities", "cash", xbrl=("CashFlowsFromUsedInOperatingActivities",)),
    _l("investing_cash_flow", "Cash flow from investing activities", "cash", xbrl=("CashFlowsFromUsedInInvestingActivities",)),
    _l("financing_cash_flow", "Cash flow from financing activities", "cash", xbrl=("CashFlowsFromUsedInFinancingActivities",)),
    _l("net_cash_flow", "Net change in cash", "cash", xbrl=("IncreaseDecreaseInCashAndCashEquivalents",)),
    _l("capex", "Purchase of property, plant and equipment", "cash",
       xbrl=("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",)),
    _l("capex_intangible", "Purchase of intangible assets", "cash",
       xbrl=("PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",)),
    _l("capex_intangible_wip", "Purchase of intangibles under development", "cash",
       xbrl=("PurchaseOfIntangibleAssetsUnderDevelopment",)),
    # --- statement of assets and liabilities (instant facts; the keys are the BalanceSheet field names) -----------
    _l("net_worth_cr", "Net worth / equity", "balance", xbrl=("Equity", "EquityAttributableToOwnersOfParent", "ShareholdersFunds")),
    _l("debt_noncurrent", "Borrowings, non-current", "balance", xbrl=("BorrowingsNoncurrent",)),
    _l("debt_current", "Borrowings, current", "balance", xbrl=("BorrowingsCurrent",)),
    _l("debt_borrowings", "Borrowings (lender)", "balance", xbrl=("Borrowings",)),
    _l("debt_securities", "Debt securities (lender)", "balance", xbrl=("DebtSecurities",)),
    _l("debt_subordinated", "Subordinated liabilities (lender)", "balance", xbrl=("SubordinatedLiabilities",)),
    _l("cash_cr", "Cash and cash equivalents", "balance", xbrl=("CashAndCashEquivalents",)),
    _l("cash_rbi", "Cash and balances with RBI", "balance", xbrl=("CashAndBalancesWithReserveBankOfIndia",)),
    _l("cash_banks", "Balances with banks and money at call", "balance", xbrl=("BalancesWithBanksAndMoneyAtCallAndShortNotice",)),
    _l("equity_capital_cr", "Equity share capital", "balance", xbrl=("EquityShareCapital", "Capital", "ShareCapital")),
    _l("reserves_cr", "Reserves / other equity", "balance", xbrl=("OtherEquity", "ReservesAndSurplus")),
    _l("minority_interest_cr", "Non-controlling interest", "balance", xbrl=("NonControllingInterest",)),
    _l("total_assets_cr", "Total assets", "balance", xbrl=("Assets",), note="dropped for GI and LI (net of current liabilities there)"),
    _l("noncurrent_assets_cr", "Non-current assets", "balance", xbrl=("NoncurrentAssets",)),
    _l("current_assets_cr", "Current assets", "balance", xbrl=("CurrentAssets",)),
    _l("fixed_assets_cr", "Property, plant and equipment / fixed assets", "balance", xbrl=("PropertyPlantAndEquipment", "FixedAssets")),
    _l("cwip_cr", "Capital work in progress", "balance", xbrl=("CapitalWorkInProgress",)),
    _l("goodwill_cr", "Goodwill", "balance", xbrl=("Goodwill",)),
    _l("investments_noncurrent", "Investments, non-current", "balance", xbrl=("NoncurrentInvestments",)),
    _l("investments_current", "Investments, current", "balance", xbrl=("CurrentInvestments",)),
    _l("investments_total", "Investments (lender)", "balance", xbrl=("Investments",)),
    _l("inventories_cr", "Inventories", "balance", xbrl=("Inventories",)),
    _l("receivables_current", "Trade receivables, current", "balance", xbrl=("TradeReceivablesCurrent",)),
    _l("receivables_noncurrent", "Trade receivables, non-current", "balance", xbrl=("TradeReceivablesNoncurrent",)),
    _l("total_liabilities_cr", "Total liabilities", "balance", xbrl=("Liabilities",)),
    _l("noncurrent_liabilities_cr", "Non-current liabilities", "balance", xbrl=("NoncurrentLiabilities",)),
    _l("current_liabilities_cr", "Current liabilities", "balance", xbrl=("CurrentLiabilities",)),
    _l("payables_current", "Trade payables, current", "balance", xbrl=("TradePayablesCurrent",)),
    _l("payables_noncurrent", "Trade payables, non-current", "balance", xbrl=("TradePayablesNoncurrent",)),
    _l("deposits_cr", "Deposits (bank)", "balance", xbrl=("Deposits",)),
    _l("advances_cr", "Advances / loans (lender)", "balance", xbrl=("Advances", "Loans")),
)

BY_KEY = {line.key: line for line in LINES}
assert len(BY_KEY) == len(LINES), "duplicate line key"


def line(key: str) -> Line:
    return BY_KEY[key]


# --- the names ---------------------------------------------------------------------------------------------------------

def elements(key: str, template: str) -> tuple[str, ...]:
    """The element names the code reads for a line on a template: the template's own first, then the base names, minus what
    the template suppresses."""
    ln = BY_KEY[key]
    own = tuple(ln.xbrl_by.get(template, ()))
    return own + tuple(n for n in ln.xbrl if n not in own and n not in SUPPRESSED.get(template, ()))


def seen_only(key: str, template: str) -> tuple[str, ...]:
    """Element names a sample file of the template carries for the line that the code does not read."""
    return tuple(BY_KEY[key].xbrl_seen.get(template, ()))


def element_metric(template: str, element: str) -> str | None:
    """The line a code-read element name is on a template (None: not read, or suppressed there). The inverse of
    ``elements``; where a name serves two lines (the EPS variants) the first line in ``LINES`` wins, as ``eps`` does."""
    if element in SUPPRESSED.get(template, ()):
        return None
    for ln in LINES:
        if element in elements(ln.key, template):
            return ln.key
    return None


def known_elements(template: str | None = None) -> set[str]:
    """Every element name the map knows, read or seen (one template, or all)."""
    out: set[str] = set()
    for ln in LINES:
        for t in ([template] if template else TEMPLATES):
            out.update(elements(ln.key, t))
            out.update(seen_only(ln.key, t))
    return out


def screener_rows(key: str) -> tuple[str, ...]:
    return BY_KEY[key].screener


def tijori_rows(key: str, lender: bool = False) -> tuple[str, ...]:
    ln = BY_KEY[key]
    return ln.tijori_lender if lender and ln.tijori_lender else ln.tijori


def crosscheck_ours(key: str, lender: bool = False) -> tuple[str, ...]:
    ln = BY_KEY[key]
    return ln.crosscheck_ours_lender if lender else ln.crosscheck_ours


def known_screener_rows() -> set[str]:
    return {r for ln in LINES for r in ln.screener} | set(SCREENER_IGNORED)


def known_tijori_rows() -> set[str]:
    return {r for ln in LINES for r in (*ln.tijori, *ln.tijori_lender)} | set(TIJORI_IGNORED)


def unverified(key: str) -> tuple[str, ...]:
    """The sources where nothing was found for a line (see the module text: an unlooked-at source, not an empty one).
    ``xbrl:<T>`` marks a template with no element for it; ``xbrl`` alone means none on any template."""
    ln = BY_KEY[key]
    out = [name for name, names in (("screener", ln.screener), ("tijori", ln.tijori), ("pdf", ln.pdf)) if not names]
    if ln.derived_from and not ln.xbrl and not ln.xbrl_by:
        return tuple(out)       # worked out in code: it has no element by design
    if not any(elements(key, t) for t in TEMPLATES):
        out.insert(0, "xbrl")
    return tuple(out)


@lru_cache(maxsize=None)
def taxonomy_labels(template: str) -> frozenset[str]:
    """The element names SEBI's template calculates with (``config/xbrl_sums``, built from NSE's published taxonomy). Only
    the elements in a calculation relation are there, so a name's absence says nothing about the template."""
    path = SUMS_DIR / f"{template}.json"
    if not path.exists():
        return frozenset()
    return frozenset(json.loads(path.read_text()).get("labels", {}))


def in_taxonomy(template: str, element: str) -> bool:
    return element in taxonomy_labels(template)
