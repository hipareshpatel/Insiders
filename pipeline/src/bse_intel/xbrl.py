"""Stage 0 XBRL fast path (blueprint §5.1): machine-tagged figures from the filing's XBRL file.

Listed companies file results (Reg 33) and shareholding patterns (Reg 31) in XBRL beside the PDF.
The tagged figures are exact, so they take precedence over figures the model reads from the PDF:

* Results: revenue, other income, cost lines, finance cost, depreciation, PBT, taxes, PAT, EPS
  and paid-up capital per period (quarter, half year, nine months, year), with EBITDA and its
  margin derived, YoY/QoQ from the comparative columns, and net worth, debt and cash when a
  balance sheet is tagged. Results still go to Pass 2 for the narrative; the XBRL table is put at
  the top of the prompt and its figures overwrite the model's in memory.
* Shareholding patterns: promoter, pledge, FII and DII percentages and the number of small
  shareholders go straight to memory with no AI call.

Parsing is namespace-agnostic (BSE's in-bse-fin / in-bse-shp taxonomies have changed names
between versions); figures are matched by element name, periods come from the context dates, and
facts with dimensions (segments, categories) are kept apart from the totals. Monetary values are
in rupees and are converted to ₹ crore. A results file whose revenue or profit cannot be found in
the PDF text in any common unit is treated as unconfirmed and not used (a wrongly scaled filing).
"""

from __future__ import annotations

import logging
import math
import re
import statistics
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date

from .models import BalanceSheet, FinancialMetric, Ownership
from .periods import canonical_period, prior_quarter_period, prior_year_period

log = logging.getLogger(__name__)

# element name -> dossier metric (first match wins for each metric)
RESULT_TAGS = {
    "RevenueFromOperations": "revenue",
    "OtherIncome": "other_income",
    "Income": "total_income",
    "CostOfMaterialsConsumed": "raw_material_cost",
    "PurchasesOfStockInTrade": "purchases_stock_in_trade",
    "ChangesInInventoriesOfFinishedGoodsWorkInProgressAndStockInTrade": "inventory_change",
    "EmployeeBenefitExpense": "employee_cost",
    "FinanceCosts": "finance_cost",
    "DepreciationDepletionAndAmortisationExpense": "depreciation",
    "DepreciationAndAmortisationExpense": "depreciation",
    "OtherExpenses": "other_expenses",
    "Expenses": "total_expenses",
    "ExceptionalItemsBeforeTax": "exceptional_items",
    "ProfitBeforeExceptionalItemsAndTax": "pbt_before_exceptional",   # for EBITDA only; not kept in memory
    # a consolidated bank's net profit after minority interest and its associates' share, which its EPS is on (Indian
    # Bank Q4FY26: ₹3,173.05 Cr where ProfitLossForThePeriod, before both, is ₹3,115.2 Cr; hourly review, 22 Oct 2026)
    "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates": "pat_group",
    "ExceptionalItems": "exceptional_items",
    "ProfitBeforeTax": "pbt",
    "ProfitLossBeforeTax": "pbt",
    # kept to settle which PBT the statement prints (`settle_pbt`): some filers tag ProfitBeforeTax before it
    "ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod": "share_associates",
    "CurrentTax": "current_tax",
    "DeferredTax": "deferred_tax",
    "TaxExpense": "tax_expense",
    "ProfitLossForPeriod": "pat",
    "ProfitLossForThePeriod": "pat",
    "ProfitLossForPeriodFromContinuingOperations": "pat_continuing",
    # the discontinued business's own after-tax result, which a statement adds to continuing PAT (CIE's Q2FY27: 2,426.61
    # + 10.25 = 2,436.86 ₹ mn; the footing check held it as PBT - tax missing PAT, held-card audit, 22 Oct 2026)
    "ProfitLossFromDiscontinuedOperationsAfterTax": "pat_discontinued",
    # the shareholders' share, apart from minority interests: Bajaj Finserv's ₹6,296.67 Cr consolidated profit is
    # ₹3,132 Cr to its owners, and the card gave the first as the company's (round 6, 2026-10-19)
    "ProfitOrLossAttributableToOwnersOfParent": "pat_owners",
    "ProfitOrLossAttributableToNonControllingInterests": "pat_minority",
    # excise collected for the government sits inside revenue: ITC's Q1FY27 revenue "+27.6%" was -11% net of it (round 6)
    "ExciseDuty": "excise_duty",
    "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations": "eps",
    "BasicEarningsLossPerShareFromContinuingOperations": "eps",
    "BasicEarningsPerShare": "eps",
    "PaidUpValueOfEquityShareCapital": "paid_up_capital",
    # Banks file the banking template, not the commercial one, so none of the names above appear on a
    # bank's results and its memory held almost nothing: no top line, no PBT, no interest cost (found on
    # CSB Bank, audit round 1 - 6 of 12 metrics). Interest earned is the top line of a bank's statement,
    # interest expended its cost of funds, and operating profit before provisions its pre-provision
    # operating profit, which is the figure a bank is read on rather than EBITDA.
    # EPS too: the banking template reports it before and after extraordinary items (the RBI Form B
    # names), not under the commercial tag, so SBI and CSB Bank had no EPS at all. Where a bank
    # reports both and they differ, the first in the document wins, as for every other metric.
    "BasicEarningsPerShareAfterExtraordinaryItems": "eps",
    "BasicEarningsPerShareBeforeExtraordinaryItems": "eps",
    "InterestEarned": "interest_earned",
    "InterestExpended": "interest_expended",
    "OperatingProfitBeforeProvisionAndContingencies": "pre_provision_operating_profit",
    "ProvisionsOtherThanTaxAndContingencies": "provisions",
    "ProfitLossFromOrdinaryActivitiesBeforeTax": "pbt",
    "EmployeesCost": "employee_cost",
    "OperatingExpenses": "other_expenses",
    # The cash-flow statement filed with the half-year and year results (owner, 2026-10-21: the company page needs
    # the cash flow, as on screener.in). Only on six- and twelve-month contexts; an outflow is negative as filed.
    "CashFlowsFromUsedInOperatingActivities": "operating_cash_flow",
    "CashFlowsFromUsedInInvestingActivities": "investing_cash_flow",
    "CashFlowsFromUsedInFinancingActivities": "financing_cash_flow",
    "IncreaseDecreaseInCashAndCashEquivalents": "net_cash_flow",
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": "capex",
    # capitalised R&D and software: Tejas Networks' H1FY27 intangible spend (₹358.59 Cr) was nine times its plant and
    # equipment, and free cash flow without it read half the burn (on-off review, 24 Oct 2026)
    "PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities": "capex_intangible",
    "PurchaseOfIntangibleAssetsUnderDevelopment": "capex_intangible_wip",
}
# Insurers file neither template above. SEBI gives them their own taxonomies and the names share almost
# nothing with a manufacturer's: a general insurer's top line is premium earned and its profit comes out of
# an underwriting account, a life insurer's is net premium income with the result struck in a shareholders'
# account below a policyholders' one. With only the commercial map, ICICI Lombard yielded 4 metrics of 23
# and HDFC Life 8, so cards for 198 financial companies had almost nothing machine-tagged to stand on.
#
# These are overlays, not additions, because one name means two things: `ProvisionForTax` is the tax on a
# general insurer's profit but a life insurer's POLICYHOLDERS' tax, nowhere near the tax on its result. The
# taxonomy each instance declares picks the overlay, and a None suppresses a commercial tag that would
# otherwise read the wrong account.
GENERAL_INSURANCE_TAGS = {
    "GrossPremiumsWritten": "gross_premium",
    "NetPremiumWritten": "net_premium",
    "PremiumEarned": "revenue",          # net earned premium is the top line of the revenue account
    "IncurredClaims": "incurred_claims",
    "NetCommission": "commission",
    "ProfitOrLossBeforeTax": "pbt",
    "ProfitLossAfterTax": "pat",
    "ProvisionForTax": "tax_expense",
    "BasicAndDilutedEPSAfterExtraordinaryItemsNetOfTaxExpenseForThePeriodNotToBeAnnualized": "eps",
}
LIFE_INSURANCE_TAGS = {
    "GrossPremiumIncome": "gross_premium",
    "NetPremiumIncome": "revenue",
    "IncomeFirstYearPremium": "first_year_premium",
    "IncomeRenewalPremium": "renewal_premium",
    "IncomeSinglePremium": "single_premium",
    "BenefitsPaidNet": "benefits_paid",
    "NetCommission": "commission",
    "NetSurplusDeficit": "surplus",
    "ProfitLossAfterTaxAndExtraordinaryItems": "pat",
    "ProvisionsForTaxes": "tax_expense",      # the shareholders' account, where the result is struck
    "ProvisionForTax": None,                  # the policyholders' account: not the tax on this profit
    "CurrentTax": None,
    "BasicAndDilutedEPSAfterExtraordinaryItemsNetOfTaxExpenseForThePeriodNotToBeAnnualized": "eps",
}
OVERLAYS = {"GI": GENERAL_INSURANCE_TAGS, "LI": LIFE_INSURANCE_TAGS}
# Ratios an insurer reports as a fraction (1.0705) and everyone quotes as a percentage. The combined ratio
# is the one general insurance is read on: above 100% the underwriting itself loses money. Solvency is
# deliberately left out - filers disagree on its scale (0.0275 against 1.8 for the same kind of number).
RATIO_TAGS = {
    "CombinedRatio": "combined_ratio",
    "IncurredClaimRatio": "claims_ratio",
    "NetRetentionRatio": "retention_ratio",
    "ExpensesOfManagementRatio": "expense_ratio",
    # A bank's asset quality and return, on the banking template as fractions (CSB Bank Q3FY25: 0.0158 gross NPA,
    # 0.0064 net, 0.0148 return on assets). A bank is read on these before its profit, and its card had none of them.
    "PercentageOfGrossNpa": "gnpa_pct",
    "PercentageOfNpa": "nnpa_pct",
    "ReturnOnAssets": "roa_pct",
}
# The range a bank ratio can take as a percentage; a filer that already wrote 1.58 for 1.58% would read as 158%.
RATIO_BOUNDS = {"gnpa_pct": (0.0, 60.0), "nnpa_pct": (0.0, 40.0), "roa_pct": (-20.0, 20.0)}
# The statement of assets and liabilities (half-year and year results), in full since 2026-10-21 (owner: the company
# page needs the balance sheet as on screener.in). Keys without `_cr` are halves summed below.
BALANCE_TAGS = {
    "Equity": "net_worth_cr",
    "EquityAttributableToOwnersOfParent": "net_worth_cr",
    "BorrowingsNoncurrent": "debt_noncurrent",
    "BorrowingsCurrent": "debt_current",
    "CashAndCashEquivalents": "cash_cr",
    "EquityShareCapital": "equity_capital_cr",
    "OtherEquity": "reserves_cr",
    "NonControllingInterest": "minority_interest_cr",
    "Assets": "total_assets_cr",
    "NoncurrentAssets": "noncurrent_assets_cr",
    "CurrentAssets": "current_assets_cr",
    "PropertyPlantAndEquipment": "fixed_assets_cr",
    "CapitalWorkInProgress": "cwip_cr",
    "Goodwill": "goodwill_cr",
    "NoncurrentInvestments": "investments_noncurrent",
    "CurrentInvestments": "investments_current",
    "Inventories": "inventories_cr",
    "TradeReceivablesCurrent": "receivables_current",
    "TradeReceivablesNoncurrent": "receivables_noncurrent",
    "Liabilities": "total_liabilities_cr",
    "NoncurrentLiabilities": "noncurrent_liabilities_cr",
    "CurrentLiabilities": "current_liabilities_cr",
    "TradePayablesCurrent": "payables_current",
    "TradePayablesNoncurrent": "payables_noncurrent",
    "Deposits": "deposits_cr",
    "Advances": "advances_cr",
    # the banking and NBFC templates (deep audit A-10, 2026-10-21: no bank had a net worth, Bajaj Finance no debt)
    "Capital": "equity_capital_cr",
    "ShareCapital": "equity_capital_cr",
    "ReservesAndSurplus": "reserves_cr",
    "ShareholdersFunds": "net_worth_cr",
    "Borrowings": "debt_borrowings",
    "DebtSecurities": "debt_securities",
    "SubordinatedLiabilities": "debt_subordinated",
    "Loans": "advances_cr",
    "Investments": "investments_total",
    "FixedAssets": "fixed_assets_cr",
    "CashAndBalancesWithReserveBankOfIndia": "cash_rbi",
    "BalancesWithBanksAndMoneyAtCallAndShortNotice": "cash_banks",
}
# insurers' "Assets" is the application of funds net of current liabilities (IRDAI forms; A-01): not a total
# halves of one balance-sheet line, summed into it
BALANCE_SUMS = {"investments_cr": ("investments_noncurrent", "investments_current"),
                "receivables_cr": ("receivables_current", "receivables_noncurrent"),
                "payables_cr": ("payables_current", "payables_noncurrent")}
PER_SHARE = {"eps"}
CASH_FLOW = {"operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "net_cash_flow", "capex", "capex_intangible",
             "capex_intangible_wip"}
PERCENT = {"ebitda_margin", *RATIO_TAGS.values()}
CONFIRM = ("revenue", "pat")  # figures looked for in the PDF text before the file is trusted


@dataclass
class XbrlResult:
    kind: str                                   # RESULTS or SHAREHOLDING
    basis: str | None = None                    # CONSOLIDATED / STANDALONE
    period: str | None = None                   # the latest period reported
    metrics: list[FinancialMetric] = field(default_factory=list)
    balance_sheet: BalanceSheet | None = None
    balance_prior: BalanceSheet | None = None    # the file's own earlier balance-sheet date (March for a half year)
    ownership: Ownership | None = None
    confirmed: bool = True
    template: str = ""                          # the SEBI template filed on: INDAS, NBFC, BANKING, GI, LI
    # memory-only figures (F166): the profit to minority interests, kept beside the owners' profit it was checked
    # against. Never in ``metrics``, so no card, prompt, table or check reads it; `memory_metrics` joins the two
    memory_extra: list[FinancialMetric] = field(default_factory=list)
    ratio_basis: str | None = None              # STANDALONE when a consolidated bank file's ratios came from it
    fy_end_month: int | None = None             # the company's year end, from DateOfEndOfFinancialYear (3 = March)

    def memory_metrics(self) -> list[FinancialMetric]:
        """What memory stores from this file: the figures a card reads and the memory-only ones (F166)."""
        return [*self.metrics, *self.memory_extra]

    def table(self, explicit_basis: bool = False) -> str:
        """The figures as text for the Pass 2 prompt (and for grounding). `explicit_basis` (CARD_CONSOLIDATED_ONLY, F154)
        names the basis and the period in the header: "Consolidated, ₹ crore, quarter ended 30 Sep 2026"."""
        if self.kind == "SHAREHOLDING" and self.ownership:
            o = self.ownership
            parts = [f"{k}: {v}" for k, v in o.model_dump().items() if v is not None]
            return "Shareholding pattern (XBRL, exact): " + "; ".join(parts)
        lines = [f"Machine-tagged results (XBRL, {self.basis or 'basis not stated'}, ₹ crore unless noted; exact, "
                 "prefer these over figures read from the PDF):"]
        if explicit_basis and self.basis:
            lines[0] = (f"Machine-tagged results (XBRL, {self.basis.capitalize()}, ₹ crore unless noted{_period_words(self.period)}; "
                        "exact, prefer these over figures read from the PDF):")
        for m in self.metrics:
            unit = " ₹/share" if m.unit == "INR" else " %" if m.unit == "PCT" else " Cr"
            change = "".join(f", {label} {v:+.1f}%" for label, v in (("YoY", m.yoy_pct), ("QoQ", m.qoq_pct)) if v is not None)
            basis = " (standalone)" if self.ratio_basis and m.metric in BANK_RATIOS else ""
            note = f" ({m.eps_note})" if m.eps_note else ""   # EPS_SHARE_ADJUST only
            lines.append(f"- {m.metric} {m.period}{basis}: {m.value:g}{unit}{change}{note}")
        if self.balance_sheet and not self.balance_sheet.is_empty():
            b = self.balance_sheet
            lines.append(f"- balance sheet {b.period}: " + ", ".join(
                f"{k} {v:g}" for k, v in b.model_dump().items() if isinstance(v, float)))
        return "\n".join(lines)


def _period_words(period: str | None) -> str:
    """", quarter ended 30 Sep 2026" for Q2FY27; "" when the period is not one the date can be read from."""
    from .periods import due_date

    day = due_date(period) if period else None
    if day is None:
        return ""
    kind = "quarter" if re.match(r"Q[1-4]", period) else "half year" if period.startswith("H") else \
        "nine months" if period.startswith("9M") else "year" if period.startswith("FY") else None
    return f", {kind} ended {day.day} {day.strftime('%b %Y')}" if kind else ""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


_BALANCE_TOTALS = ("total_assets_cr", "total_liabilities_cr", "current_assets_cr", "noncurrent_assets_cr",
                   "current_liabilities_cr", "noncurrent_liabilities_cr")


def _check_balance(result: "XbrlResult") -> None:
    """An insurer's totals are dropped (its "Assets" is net of current liabilities: ICICI Lombard's ₹20,891.52 Cr beside
    ₹64,332 Cr of investments, deep audit A-01), and so are any totals that do not add up: assets must equal equity
    (with or without minority interest) plus liabilities within 2%."""
    sheet = result.balance_sheet
    if sheet is None:
        return
    assets, worth, liabilities = sheet.total_assets_cr, sheet.net_worth_cr, sheet.total_liabilities_cr
    off = result.template in ("GI", "LI")
    if not off and assets and worth is not None and liabilities is not None:
        sums = [worth + liabilities, worth + (sheet.minority_interest_cr or 0) + liabilities]
        off = all(abs(assets - total) > 0.02 * abs(assets) for total in sums)
        if off:
            log.info("balance sheet totals refused: assets %s against equity %s + liabilities %s", assets, worth, liabilities)
    if off:
        for key in _BALANCE_TOTALS:
            setattr(sheet, key, None)


def _legacy_year_to_date(contexts: dict[str, dict]) -> None:
    """NSE's results files before the integrated filing (to 2024) tag the year to date as "FourD" with the quarter's own
    dates (Titan and Asian Paints Q4FY24, Q4FY23, Q2FY24: deep audit A-03, 2026-10-21), so the year's figures read as
    the quarter's and its cash flow was stored under the quarter. Its start is the financial year's (1 April): from
    a March quarter that makes it the year, from September the half year, from December nine months."""
    quarter, ytd = contexts.get("OneD"), contexts.get("FourD")
    if not quarter or not ytd or quarter.get("dims") or ytd.get("dims"):
        return
    start, end = ytd.get("startDate"), ytd.get("endDate")
    if not start or not end or (start, end) != (quarter.get("startDate"), quarter.get("endDate")):
        return
    fy_start = date(end.year if end.month >= 4 else end.year - 1, 4, 1)
    if fy_start < start:
        ytd["startDate"] = fy_start


def _contexts(root) -> dict[str, dict]:
    out = {}
    for ctx in root.iter():
        if _local(ctx.tag) != "context":
            continue
        info: dict = {"dims": {}}
        for el in ctx.iter():
            name = _local(el.tag)
            if name in ("startDate", "endDate", "instant") and el.text:
                try:
                    info[name] = date.fromisoformat(el.text.strip()[:10])
                except ValueError:
                    pass
            elif name == "explicitMember":
                info["dims"][_local(el.get("dimension", ""))] = (el.text or "").strip().rsplit(":", 1)[-1]
            elif name == "typedMember":   # its value is a child element's text ("MutualFundsOrUTI_Context15")
                info["dims"][_local(el.get("dimension", ""))] = "".join(el.itertext()).strip().rsplit(":", 1)[-1]
        out[ctx.get("id")] = info
    return out


def _units(root) -> dict[str, str]:
    """unit id -> MONEY, PER_SHARE, SHARES or PURE."""
    out = {}
    for unit in root.iter():
        if _local(unit.tag) != "unit":
            continue
        measures = [(m.text or "").upper() for m in unit.iter() if _local(m.tag) == "measure"]
        divide = any(_local(el.tag) == "divide" for el in unit.iter())
        if divide:
            out[unit.get("id")] = "PER_SHARE"
        elif any("INR" in m for m in measures):
            out[unit.get("id")] = "MONEY"
        elif any("SHARES" in m for m in measures):
            out[unit.get("id")] = "SHARES"
        else:
            out[unit.get("id")] = "PURE"
    return out


def _facts(root):
    for el in root.iter():
        ctx = el.get("contextRef")
        if ctx is None or el.text is None:
            continue
        yield _local(el.tag), ctx, el.get("unitRef"), el.text.strip()


def _num(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _months(info: dict) -> int | None:
    if "startDate" not in info or "endDate" not in info:
        return None
    return round(((info["endDate"] - info["startDate"]).days + 1) / 30.44)


def _fy_end(d: date) -> int:
    return d.year if d.month <= 3 else d.year + 1


def period_label(info: dict, fy_end_month: int | None = None) -> str | None:
    """A context's period on the April-March convention every label here uses. A quarter is named by its calendar
    months whatever the company's year (Q2FY27 is July-September 2026 for Siemens too), so it is the same row for
    every company. A half year, nine months or year is not: for a company whose year ends in another month
    (Siemens in September, Gillette in June) "FY" and "H1" would name the wrong months, its full year stored as
    H1FY24 and its half year as FY23 (Siemens' memory, 22 Oct 2026). Those periods get no label, and are not kept."""
    months, end = _months(info), info.get("endDate")
    if not end or months is None:
        return None
    if months == 3:
        return canonical_period(f"quarter ended {end:%d.%m.%Y}")
    if fy_end_month not in (None, 3):
        return None
    fy = f"FY{_fy_end(end) % 100:02d}"
    if months == 12 and end.month == 3:
        return fy
    if months == 6 and end.month in (9, 3):
        return ("H1" if end.month == 9 else "H2") + fy
    if months == 9 and end.month == 12:
        return "9M" + fy
    return None


_TAXONOMY = re.compile(rb"IntegratedFinance_(\w+)")


BANK_RATIOS = ("gnpa_pct", "nnpa_pct", "roa_pct")


def _bank_ratio_fillers(values: dict) -> None:
    """A bank's consolidated file carries 0 for gross NPA, net NPA and RoA alike (SBI Q1FY27, HDFC Bank Q2FY27, IDFC
    First Q1FY27; measured 2026-10-20, docs/SOURCES.md): a filler, not a value, so a period whose bank ratios are all
    0 keeps none of them ("gross NPA 0%" on a card otherwise). A single 0 beside real ratios (a net NPA of nil) stays."""
    for label in {p for m, p in values if m in BANK_RATIOS}:
        present = [values[(m, label)] for m in BANK_RATIOS if (m, label) in values]
        if present and all(v == 0 for v in present):
            for m in BANK_RATIOS:
                values.pop((m, label), None)


_YTD_MONTHS = {"H1": 6, "H2": 6, "9M": 9, "FY": 12}


def _annualise_roa(values: dict, ends: dict) -> dict[tuple[str, str], list[str]]:
    """Most banks file RoA annualised (UCO, PSB and KVB: the quarter equals the half-year); HDFC Bank's Q2FY27 file
    has 0.45% for the quarter beside 0.91% for the half-year, the period's own return (measured 2026-10-20). When a
    file's quarter is about its share of a longer period's figure, the whole file is un-annualised: each RoA is put
    on a yearly basis, so banks compare. A file with the quarter alone is left as filed (no way to tell). Returns the
    RoA figures this changed with their input (our own arithmetic on the filed quarterly RoA: memory label `calc`)."""
    quarter = max((p for m, p in values if m == "roa_pct" and p.startswith("Q")), key=lambda p: ends.get(p) or date.min,
                  default=None)
    if quarter is None or not values.get(("roa_pct", quarter)):
        return {}
    for (metric, label), longer in list(values.items()):
        months = next((n for k, n in _YTD_MONTHS.items() if label.startswith(k)), None)
        if metric != "roa_pct" or not months or not longer or ends.get(label) != ends.get(quarter):
            continue
        share = values[("roa_pct", quarter)] / longer
        if abs(share - 3 / months) <= 0.25 * 3 / months and share < 0.8:
            scaled = {}
            for (m, p) in list(values):
                n = 3 if p.startswith("Q") else next((x for k, x in _YTD_MONTHS.items() if p.startswith(k)), None)
                if m == "roa_pct" and n:
                    values[(m, p)] *= 12 / n
                    if n != 12:
                        scaled[(m, p)] = [f"roa_pct_quarterly:{quarter}"]   # the filed (un-annualised) quarter's RoA
            return scaled
    return {}


def taxonomy(data: bytes) -> str:
    """Which SEBI template this instance was filed on: INDAS, NBFC, BANKING, GI or LI ("" if it says)."""
    m = _TAXONOMY.search(data[:8000])
    return m.group(1).decode("ascii", "ignore").upper() if m else ""


def untrusted_lines(data: bytes, contexts: dict, year_end: int | None, tags: dict[str, str],
                    news_id: str = "") -> set[tuple[str, str]]:
    """(metric, period) of every figure in a sum that does not add up on SEBI's own rules (xbrl_sums, item 23, owner
    25 Oct 2026): the total and its items, in the failing context only. A hold, not a repair: they are left off and
    the rest of the file is used. One warning per file. Empty with XBRL_SUMS=0."""
    from . import xbrl_sums
    from .settings import get_settings
    if not get_settings().xbrl_sums:
        return set()
    report = xbrl_sums.check(data)
    if not report or report.ok:
        return set()
    out: set[tuple[str, str]] = set()
    for miss in report.mismatches:
        label = period_label(contexts.get(miss.context) or {}, year_end)
        names = [miss.total, *(item for item, _ in xbrl_sums.sums_for(report.template).get(miss.total, []))]
        metrics = sorted({tags[n] for n in names if n in tags})
        if label:
            out.update((m, label) for m in metrics)
        log.warning("xbrl sums: %s %s: %s filed %s adds up to %s (%s) -> left off: %s", news_id, report.template,
                    miss.total, round(miss.filed), round(miss.adds_up_to), label or miss.context,
                    ", ".join(metrics) or "nothing we use")
    return out


def parse(data: bytes, news_id: str = "") -> XbrlResult | None:
    """Parse an XBRL instance; None when it is not one or holds nothing we use. Figures in a sum that fails SEBI's own
    rules are left off (untrusted_lines), here at the one place every card, fact and table reads them from."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    contexts = _contexts(root)
    if not contexts:
        return None
    _legacy_year_to_date(contexts)
    units = _units(root)
    facts = list(_facts(root))
    names = {name for name, *_ in facts}
    text_facts = {name: value for name, ctx, unit, value in facts if unit is None}
    tags = {**RESULT_TAGS, **OVERLAYS.get(taxonomy(data), {})}
    tags = {name: metric for name, metric in tags.items() if metric}
    if any("Shareholding" in n or "Shareholder" in n for n in names) and not names & set(tags):
        return _shareholding(facts, contexts)
    untrusted = untrusted_lines(data, contexts, fy_end_month(text_facts), tags, news_id)
    result = _results(facts, contexts, units, text_facts, tags, untrusted)
    if result:
        result.template = taxonomy(data)
        if result.template in LENDER_TEMPLATES:
            # interest is a lender's cost of goods: profit + finance cost + depreciation is no EBITDA for a bank, an NBFC
            # or an insurer (held-card audit, 22 Oct 2026: Bajaj Finance's ₹12,430.66 Cr, IRFC's, held or shown as
            # its "EBITDA" and margin)
            result.metrics = [m for m in result.metrics if m.metric not in ("ebitda", "ebitda_margin")]
        _check_balance(result)
    return result


LENDER_TEMPLATES = ("NBFC", "BANKING", "GI", "LI")


def needs_standalone_bank_ratios(result: "XbrlResult | None") -> bool:
    """A bank's consolidated file without its asset-quality ratios for the quarter (SBI, HDFC Bank and IDFC First file
    0 there, dropped as fillers): RBI states them for the bank, so they come from its standalone file."""
    return bool(result and result.kind == "RESULTS" and result.template == "BANKING" and result.basis == "CONSOLIDATED"
                and not any(m.metric in BANK_RATIOS and m.period == result.period for m in result.metrics))


def add_bank_ratios(result: "XbrlResult", standalone: "XbrlResult | None") -> int:
    """The standalone file's bank ratios added to a consolidated result, for the same periods (the table says so).
    Returns how many were added."""
    if not standalone or standalone.basis != "STANDALONE":
        return 0
    have = {(m.metric, m.period) for m in result.metrics}
    periods = {m.period for m in result.metrics}
    added = [m for m in standalone.metrics
             if m.metric in BANK_RATIOS and m.period in periods and (m.metric, m.period) not in have]
    result.metrics += added
    if added:
        result.ratio_basis = "STANDALONE"
    return len(added)


def fy_end_month(text_facts: dict) -> int | None:
    """The month the company's financial year ends, from the file's DateOfEndOfFinancialYear ("2026-09-30" -> 9)."""
    raw = str(text_facts.get("DateOfEndOfFinancialYear") or "").strip()
    m = re.match(r"(20\d{2})-(\d{2})-\d{2}", raw)
    return int(m[2]) if m and 1 <= int(m[2]) <= 12 else None


def _balance_sheet(balance: dict[str, float], balance_date: date) -> BalanceSheet:
    """One date's statement of assets and liabilities from its tagged lines (crore)."""
    debt = ([balance[k] for k in ("debt_noncurrent", "debt_current") if k in balance]
            or [balance[k] for k in ("debt_borrowings", "debt_securities", "debt_subordinated") if k in balance])
    if "cash_cr" not in balance and ("cash_rbi" in balance or "cash_banks" in balance):
        balance["cash_cr"] = balance.get("cash_rbi", 0) + balance.get("cash_banks", 0)   # a bank's cash
    if "investments_total" in balance and not any(k in balance for k in BALANCE_SUMS["investments_cr"]):
        balance["investments_current"] = balance["investments_total"]
    if "net_worth_cr" not in balance and "equity_capital_cr" in balance and "reserves_cr" in balance:
        balance["net_worth_cr"] = balance["equity_capital_cr"] + balance["reserves_cr"]   # a bank's net worth
    if ("total_liabilities_cr" not in balance and "total_assets_cr" in balance and "net_worth_cr" in balance
            and "deposits_cr" in balance):
        balance["total_liabilities_cr"] = balance["total_assets_cr"] - balance["net_worth_cr"]
    sums = {key: _r(sum(balance[p] for p in parts if p in balance)) for key, parts in BALANCE_SUMS.items()
            if any(p in balance for p in parts)}
    lines = {k: _r(v) for k, v in balance.items() if k.endswith("_cr") and k not in ("net_worth_cr", "cash_cr")}
    sheet = BalanceSheet(period=canonical_period(f"quarter ended {balance_date:%d.%m.%Y}"),
                         net_worth_cr=_r(balance.get("net_worth_cr")), cash_cr=_r(balance.get("cash_cr")),
                         gross_debt_cr=_r(sum(debt)) if debt else None, **lines, **sums)
    # No net debt: the file's cash is cash and cash equivalents alone, without bank deposits and liquid investments,
    # and Kajaria's Q2FY27 came out at "net debt ₹291.98 Cr" where its release states net cash of ₹635 Cr (owner,
    # 24 Oct 2026). A filing that states its net debt gives it; signals.stated_net_debt ignores the old derived ones.
    return sheet


def _results(facts, contexts, units, text_facts, tags: dict[str, str] | None = None,
             untrusted: set[tuple[str, str]] = frozenset()) -> XbrlResult | None:
    nature = " ".join(v for k, v in text_facts.items() if "Standalone" in k or "Consolidated" in k or k == "NatureOfReport").lower()
    basis = "CONSOLIDATED" if "consolidated" in nature else "STANDALONE" if "standalone" in nature else None
    tags = tags or RESULT_TAGS
    year_end = fy_end_month(text_facts)
    values: dict[tuple[str, str], float] = {}
    ends: dict[str, date] = {}
    instants: dict[date, dict[str, float]] = {}   # balance-sheet lines by date: the latest, and the file's comparative
    for name, ctx, unit, raw in facts:
        info = contexts.get(ctx)
        value = _num(raw)
        if info is None or value is None or info["dims"]:
            continue  # segment and other dimensional facts are not totals
        kind = units.get(unit or "", "PURE")
        if name in tags or name in RATIO_TAGS:
            label = period_label(info, year_end)
            if not label:
                continue
            if name in RATIO_TAGS:
                metric = RATIO_TAGS[name]
                if kind != "PURE":
                    continue
                # filed as a fraction, read as a percentage; a bank ratio above 1 was already written as one
                # (assumption, not seen yet: the SEBI template asks for the fraction, CSB Bank files 0.0158)
                if not (metric in RATIO_BOUNDS and abs(value) > 1):
                    value *= 100
                low, high = RATIO_BOUNDS.get(metric, (-math.inf, math.inf))
                if not low <= value <= high:
                    continue
            else:
                metric = tags[name]
                if metric in CASH_FLOW and label.startswith("Q"):
                    continue   # the cash-flow statement is filed for six and twelve months, never a quarter (A-03)
                if metric in PER_SHARE:
                    if kind != "PER_SHARE" and kind != "PURE":
                        continue
                elif kind != "MONEY":
                    continue
                else:
                    value = value / 1e7
            if metric in PER_SHARE and values.get((metric, label)) == 0 and value != 0:
                values[(metric, label)] = value   # a 0 EPS tagged first is a filler; the real one may come under another tag
            else:
                values.setdefault((metric, label), value)
            ends[label] = info["endDate"]
        elif name in BALANCE_TAGS and kind == "MONEY" and info.get("instant"):
            instants.setdefault(info["instant"], {}).setdefault(BALANCE_TAGS[name], value / 1e7)
    if not values:
        return None
    # Net NPA cannot exceed gross NPA: when it does, one of the two was read at the wrong scale, so neither is kept
    for label in {p for m, p in values if m == "nnpa_pct"}:
        gross, net = values.get(("gnpa_pct", label)), values.get(("nnpa_pct", label))
        if gross is not None and net is not None and net > gross + 0.005:
            values.pop(("gnpa_pct", label)), values.pop(("nnpa_pct", label))
    for label in {p for m, p in values if m == "pat_group"}:
        group = values.pop(("pat_group", label))
        if group or values.get(("pat", label)) is None:   # a 0 there is the template's filler
            values[("pat", label)] = group
    _bank_ratio_fillers(values)
    annualised = _annualise_roa(values, ends)
    # EBITDA = profit before exceptional items and tax + finance cost + depreciation - other income. From the file's
    # own profit before exceptional items when it tags one: PBT less the exceptional items depends on the sign a filer
    # gives a charge, and a charge tagged positive took EBITDA down by twice it (data chain audit A9, 22 Oct 2026)
    derived: dict[tuple[str, str], list[str]] = {}   # figures our code worked out, and the lines they came from (memory label)
    derived.update(annualised)   # the yearly RoA is our arithmetic on the filed quarterly one, not the file's own figure
    for label in {p for _, p in values}:
        before = values.pop(("pbt_before_exceptional", label), None)
        start = before if before is not None else _pbt_without_associates(values, label)
        parts = [start, values.get(("finance_cost", label)), values.get(("depreciation", label))]
        if all(v is not None for v in parts):
            ebitda = sum(parts) - (values.get(("other_income", label)) or 0) \
                - (0 if before is not None else values.get(("exceptional_items", label)) or 0)
            values[("ebitda", label)] = ebitda
            names = ["pbt_before_exceptional" if before is not None else "pbt", "finance_cost", "depreciation", "other_income"]
            if before is None:
                names.append("exceptional_items")
            derived[("ebitda", label)] = [f"{n}:{label}" for n in names]
            revenue = values.get(("revenue", label))
            if revenue:
                values[("ebitda_margin", label)] = ebitda / revenue * 100
                derived[("ebitda_margin", label)] = [f"ebitda:{label}", f"revenue:{label}"]
    if untrusted:
        # before the changes are worked out, so none is built on a left-off figure; a derived EBITDA goes with its parts
        parts = {"pbt", "pbt_before_exceptional", "finance_cost", "depreciation", "other_income", "exceptional_items",
                 "revenue"}
        for key in [k for k in values if k in untrusted
                    or (k[0] in ("ebitda", "ebitda_margin") and any(p == k[1] and m in parts for m, p in untrusted))]:
            del values[key]
        if not values:
            return None
        ends = {p: e for p, e in ends.items() if any(label == p for _, label in values)}
    latest = max(ends, key=lambda p: (ends[p], p.startswith("Q")))
    quarter = max((p for p in ends if p.startswith("Q")), key=lambda p: ends[p], default=None)
    # EPS takes its period's profit sign: Shivam Autotech's file tags H1FY24 EPS 2.27 beside a loss of ₹27.77 Cr, and
    # memory then read a fall to a loss as "EPS down 177%" (live review 2, 2026-10-20). The owners' profit decides
    # where the file has one (a 0 there is a filler), else the group's.
    minority: dict[tuple[str, str], float] = {}
    owners_share(values, minority)
    eps_fillers(values)
    eps_signs(values)
    metrics = []
    for (metric, label), value in sorted(values.items(), key=lambda kv: (ends.get(kv[0][1]) or date.min, kv[0][0])):
        unit = "INR" if metric in PER_SHARE else "PCT" if metric in PERCENT else "INR_CR"
        yoy = qoq = None
        if metric not in PERCENT:
            yoy = _change(value, _match(values, ends, metric, label, years=1))
            if label.startswith("Q"):
                qoq = _change(value, _match(values, ends, metric, label, months=3))
        metrics.append(FinancialMetric(metric=metric, period=label, value=round(value, 2), unit=unit,
                                       yoy_pct=yoy, qoq_pct=qoq,
                                       by="calc" if (metric, label) in derived else "file",
                                       derived_from=derived.get((metric, label)), file_basis=basis))
    extra = []
    for (metric, label), value in sorted(minority.items(), key=lambda kv: (ends.get(kv[0][1]) or date.min, kv[0][0])):
        if label not in ends:
            continue
        all_values = {**values, **minority}
        yoy = _change(value, _match(all_values, ends, metric, label, years=1))
        qoq = _change(value, _match(all_values, ends, metric, label, months=3)) if label.startswith("Q") else None
        extra.append(FinancialMetric(metric=metric, period=label, value=round(value, 2), unit="INR_CR", yoy_pct=yoy,
                                     qoq_pct=qoq, by="file", file_basis=basis))
    dates = sorted(instants)
    sheet = _balance_sheet(instants[dates[-1]], dates[-1]) if dates else None
    # the file's own earlier date (March for a half year): like for like by construction, what facts.py compares with
    prior = _balance_sheet(instants[dates[-2]], dates[-2]) if len(dates) > 1 else None
    return XbrlResult("RESULTS", basis, quarter or latest, metrics, sheet, fy_end_month=year_end, balance_prior=prior,
                      memory_extra=extra)


def _pbt_without_associates(values: dict, label: str) -> float | None:
    """Profit before tax as SEBI's taxonomy defines it, without the associates' and joint ventures' share, which the
    official sums add after tax (profit = continuing + discontinued + share; config/xbrl_sums, item 12, owner 25 Oct
    2026). Some filers tag profit before tax with the share in it (Orient Bell); the file's own lines tell: when profit
    before tax less tax already gives the profit without adding the share, the share is in it and is taken out."""
    pbt, share = values.get(("pbt", label)), values.get(("share_associates", label))
    if pbt is None or not share:
        return pbt
    tax = values.get(("tax_expense", label))
    if tax is None:
        tax = (values.get(("current_tax", label)) or 0) + (values.get(("deferred_tax", label)) or 0)
    continuing = values.get(("pat_continuing", label))
    if continuing is None and values.get(("pat", label)) is not None:
        continuing = values[("pat", label)] - (values.get(("pat_discontinued", label)) or 0) - share
    if continuing is None:
        return pbt
    slack = 0.02 + 0.001 * abs(continuing)
    if abs(pbt - tax - continuing) <= slack:
        return pbt                       # tagged as the taxonomy defines it
    if abs(pbt - share - tax - continuing) <= slack:
        return pbt - share               # the share is in the tagged profit before tax
    return pbt


def owners_share(values: dict, kept: dict | None = None) -> int:
    """Drop, in place, an owners' profit that its own file's minority share does not add up to. Returns how many.

    Adani Ports' Q4FY26 file tags ₹1,238.67 Cr as the profit attributable to owners beside a ₹3,308.30 Cr profit and a
    ₹179.14 Cr minority share: both are the shares of its other comprehensive income (1,417.81), the statement prints
    3,328.96 and (20.66), and the card's headline gave "net profit to shareholders ₹1,238.67 Cr (-58.9%)" (needs-review
    sweep, 2026-10-20). Profit less that minority figure would be wrong too, so the card falls back to the group's
    profit. The minority figure is not on the card path; with ``kept`` given (F166) a minority share that does add up
    to the file's own profit and owners' figures goes into it, {(metric, period): value}, for memory only."""
    changed = 0
    # with no minority share in the file, owners cannot have more than the whole profit: D.B. Corp's Q4FY26 file tags
    # its total comprehensive income ₹63.98 Cr as the owners' profit beside a ₹62.19 Cr profit (held-card audit,
    # 22 Oct 2026: the card's headline said "net profit to shareholders ₹63.98 Cr")
    # A 0 minority is the template's filler, not a share (IREDA's Q2FY26 file tags 0 beside owners 614.76 on a 549.33
    # profit: the owners' tag holds the total comprehensive income, F155), so it does not excuse an owners' figure above
    # the profit.
    with_minority = {label for (metric, label), v in values.items() if metric == "pat_minority" and v}
    for (metric, label), owners in list(values.items()):
        profit = values.get(("pat", label))
        if metric == "pat_owners" and label not in with_minority and profit is not None and profit > 0 \
                and owners - profit > max(0.5, 0.01 * profit):
            values.pop((metric, label))
            changed += 1
    for (metric, label), minority in list(values.items()):
        if metric != "pat_minority":
            continue
        values.pop((metric, label))
        profit, owners = values.get(("pat", label)), values.get(("pat_owners", label))
        # a 0 is the template's filler, not a share: a 0 minority says nothing about -25.87 to owners of -25.27 (2026-10-20)
        if profit is None or owners is None or (minority == 0 and owners != 0):
            continue
        if abs(owners + minority - profit) > max(0.5, 0.01 * abs(profit)):
            values.pop(("pat_owners", label))
            changed += 1
        elif kept is not None and minority != 0:   # a 0 is the template's filler, not a share
            kept[("pat_minority", label)] = minority
    return changed


def eps_fillers(values: dict) -> int:
    """Drop an EPS of exactly 0 beside a profit of ₹1 Cr or more either way, in place: the template's filler, not a figure
    (Ahluwalia Contracts Q3FY24 EPS 0 beside a profit of ₹70.24 Cr; screener 10.55; 47 such pairs in the screener referee
    of 26 Oct 2026). Returns how many it dropped."""
    dropped = 0
    for (metric, label), value in list(values.items()):
        if metric != "eps" or value != 0:
            continue
        profit = values.get(("pat_owners", label)) or values.get(("pat", label))
        if profit is not None and abs(profit) >= 1:
            values.pop((metric, label))
            dropped += 1
    return dropped


def eps_signs(values: dict) -> int:
    """Give each period's EPS its profit's sign, in place ({(metric, period): value}). Returns how many it changed. Not when
    the whole profit and the owners' profit disagree in sign: one of them is wrong, so the filed sign stays (Alembic Q4FY26:
    profit ₹67.13 Cr, owners' -33.87, filed EPS 2.61 turned into -2.61; screener 2.61; 27 such pairs, 26 Oct 2026)."""
    changed = 0
    for (metric, label), value in list(values.items()):
        if metric != "eps" or not value:
            continue
        owners, whole = values.get(("pat_owners", label)), values.get(("pat", label))
        if owners and whole and (owners < 0) != (whole < 0):
            continue
        profit = owners or whole
        if profit and abs(profit) >= 0.01 and (profit < 0) != (value < 0):
            values[(metric, label)] = -value
            changed += 1
    return changed


def _r(v: float | None) -> float | None:
    return round(v, 2) if v is not None else None


def _match(values, ends, metric, label, years: int = 0, months: int = 0) -> float | None:
    end = ends[label]
    target_month = end.month - months
    target = date(end.year - years + (target_month - 1) // 12, (target_month - 1) % 12 + 1, 1)
    kind = re.match(r"(9M|Q|H|FY)", label)
    for other, other_end in ends.items():
        same_kind = re.match(r"(9M|Q|H|FY)", other)
        if other != label and same_kind and kind and same_kind[1] == kind[1] \
                and (other_end.year, other_end.month) == (target.year, target.month):
            return values.get((metric, other))
    return None


def _change(now: float, before: float | None) -> float | None:
    if before is None or before <= 0:
        return None
    return round((now / before - 1) * 100, 1)


# Institutional categories of the public holding, by the explicit member SEBI's template gives each
_CATEGORY_MEMBERS = {"MutualFundsOrUTIMember": "mf_pct", "InsuranceCompaniesMember": "insurance_pct",
                     "InstitutionsForeignPortfolioInvestorCategoryOneMember": "fpi_pct",
                     "InstitutionsForeignPortfolioInvestorCategoryTwoMember": "fpi_pct",
                     "AlternativeInvestmentFundsMember": "aif_pct", "BanksMember": "banks_pct",
                     "ProvidentFundsOrPensionFundsMember": "pension_pct"}
# The axis a named holder is listed under (its typed member), as a category a reader knows
_HOLDER_AXES = (("mutualfund", "Mutual fund"), ("insurance", "Insurer"), ("foreignportfolio", "FPI"),
                ("institutionsforeign", "Foreign institution"), ("alternativeinvestment", "AIF"), ("bank", "Bank"),
                ("pension", "Pension fund"), ("providentfund", "Pension fund"), ("sovereign", "Sovereign fund"),
                ("otherinstitution", "Other institution"), ("individual", "Individual"), ("bodiescorporate", "Company"),
                ("othersindian", "Other"), ("otherforeign", "Foreign other"))
HOLDERS_KEPT = 25


def _institutions(facts, contexts, scale: float) -> tuple[dict, list[dict]]:
    """The institutional categories' % of the company, and the named public holders of 1% or more with their
    category, from a shareholding XBRL. A holder's name sits on the quarter's duration context and its stake on the
    instant one, both carrying the same typed member ("MutualFundsOrUTI_Context15"); a promoter-group holder (one with
    TypeOfPromoterShareholding) is left out, as the promoter's total already says it."""
    totals: dict[str, float] = {}
    names: dict[tuple[str, str], str] = {}
    stakes: dict[tuple[str, str], float] = {}
    promoters: set[tuple[str, str]] = set()
    for name, ctx, _unit, raw in facts:
        info = contexts.get(ctx)
        if info is None or len(info["dims"]) != 1:
            continue
        ((axis, member),) = info["dims"].items()
        if name == "NameOfTheShareholder":
            names[(axis, member)] = " ".join(raw.split())
        elif name == "TypeOfPromoterShareholding":
            promoters.add((axis, member))
        elif name == "ShareholdingAsAPercentageOfTotalNumberOfShares":
            value = _num(raw)
            if value is None:
                continue
            if member in _CATEGORY_MEMBERS:
                key = _CATEGORY_MEMBERS[member]
                totals[key] = totals.get(key, 0.0) + value * scale
            else:
                stakes[(axis, member)] = value * scale
    categories = {k: round(v, 2) for k, v in totals.items()}
    named = []
    for key, holder in names.items():
        stake = stakes.get(key)
        if stake is None or stake < 1.0 or key in promoters or not holder or holder.isdigit():
            continue
        axis = key[0].lower()
        kind = next((label for word, label in _HOLDER_AXES if word in axis), "Other")
        named.append({"name": holder, "category": kind, "pct": round(stake, 2)})
    named.sort(key=lambda h: -h["pct"])
    return categories, named[:HOLDERS_KEPT]


def _shareholding(facts, contexts) -> XbrlResult | None:
    """Promoter / FII / DII % and small-holder count from category members."""
    pct: dict[str, list[float]] = {"promoter": [], "fii": [], "dii": [], "pledge": []}
    holders: list[float] = []
    as_of: date | None = None
    for name, ctx, _unit, raw in facts:
        info, value = contexts.get(ctx), _num(raw)
        if info is None or value is None:
            continue
        instant = info.get("instant") or info.get("endDate")
        if instant and (as_of is None or instant > as_of):
            as_of = instant
        members = " ".join(info["dims"].values()).lower()
        lowered = name.lower()
        if "percentage" in lowered and "pledged" in lowered and "promoter" in members:
            pct["pledge"].append(value)
        elif ("percentage" in lowered and ("totalnumberofshares" in lowered or "shareholding" in lowered)
              # A percentage of the holder's own stake, not of the company: CSB Bank's promoter locked-in
              # shares were 80.45% of its holding while the promoter held 49.72% (NSE's own list disagreed,
              # and the seed's cross-check refused to store either figure).
              and not any(w in lowered for w in ("lockedin", "encumber", "assumingfullconversion", "underlyingoutstanding"))):
            if "promoter" in members and "nonpromoter" not in members and "public" not in members:
                pct["promoter"].append(value)
            elif "foreignportfolio" in members or "foreigninstitution" in members or "institutionsforeign" in members:
                pct["fii"].append(value)
            elif "institutionsdomestic" in members or "domesticinstitution" in members:
                pct["dii"].append(value)
        elif "numberofshareholders" in lowered and ("uptorstwolakh" in members or "nominalsharecapitalupto" in members):
            holders.append(value)
    if not pct["promoter"] and not pct["fii"] and not pct["dii"]:
        return None
    scale = 100.0 if max(pct["promoter"] + pct["fii"] + pct["dii"]) <= 1.0 else 1.0  # fractions or percentages

    def top(values: list[float]) -> float | None:  # the category total is the largest of its members
        return round(max(values) * scale, 2) if values else None

    period = canonical_period(f"quarter ended {as_of:%d.%m.%Y}") if as_of else None
    categories, named = _institutions(facts, contexts, scale)
    own = Ownership(period=period or "", promoter_pct=top(pct["promoter"]), fii_pct=top(pct["fii"]),
                    dii_pct=top(pct["dii"]), pledge_pct=top(pct["pledge"]),
                    retail_holders=max(holders) if holders else None, holders=named, **categories)
    return XbrlResult("SHAREHOLDING", period=period, ownership=own) if period else None


def confirm(result: XbrlResult, text: str) -> bool:
    """True when the latest revenue or profit appears in the PDF text in ₹ crore, lakh, million or
    thousand (or there is no text to check against). Guards against a file filed in the wrong scale."""
    if not text or result.kind != "RESULTS":
        return True
    figures = {m.metric: m.value for m in result.metrics if m.period == result.period and m.metric in CONFIRM}
    # Every figure zero (a shell company's quarter: no revenue, nil profit) cannot be looked for at any unit;
    # that is no evidence of a wrong scale, and refusing the file left the card to read the PDF alone.
    return appears_in(list(figures.values()), text) is not False


def appears_in(crores: list[float], text: str) -> bool | None:
    """Whether any of these ₹ crore figures is in the text in crore, lakh, million, thousand or rupees: None
    when none is large enough to tell apart from any other number in it (or there are none)."""
    numbers = {round(float(n.replace(",", "")), 0) for n in re.findall(r"\d[\d,]*\.?\d*", text or "")
               if n.replace(",", "").replace(".", "").isdigit()}
    checked = False
    for crore in crores:
        for scale in (1, 100, 10, 10_000, 1e7):  # crore, lakh, million, thousand, rupees
            if abs(crore) * scale < 10:
                continue  # too small to tell apart from any other number in the text
            checked = True
            if round(abs(crore) * scale, 0) in numbers or round(abs(crore) * scale + 0.5, 0) in numbers \
                    or round(abs(crore) * scale - 0.5, 0) in numbers:
                return True
    return False if checked else None


_SCALE_REFERENCE = ("revenue", "total_income", "interest_earned")
_SCALE_TOLERANCE = 0.2   # in powers of ten: within 0.63x-1.58x of an exact 10^k


def _quarters(metrics) -> dict[str, dict[str, float]]:
    """{quarter: {metric: value}} for the single-quarter figures among metrics (XBRL's or memory's)."""
    out: dict[str, dict[str, float]] = {}
    for m in metrics or []:
        get = m.get if isinstance(m, dict) else (lambda key, m=m: getattr(m, key, None))
        period, value = get("period") or "", get("value")
        if re.fullmatch(r"Q[1-4]FY\d\d", period) and isinstance(value, (int, float)) and not isinstance(value, bool):
            out.setdefault(period, {})[get("metric")] = float(value)
    return out


def _shares(figures: dict[str, float]) -> float | None:
    """The share count a quarter's profit and EPS imply, in crore: EPS is per share and keeps its value
    whatever unit a file's amounts are tagged in, so a file in the wrong unit moves this with them."""
    pat, eps = figures.get("pat"), figures.get("eps")
    if pat and eps and abs(eps) >= 0.5 and abs(pat) >= 0.5:
        return abs(pat / eps)
    return None


def scale_slip(result: XbrlResult, history) -> int:
    """The power of ten a results file's amounts are off by, against the company's other quarters; 0 when
    they fit or there is too little to tell.

    Jubilant Pharmova's Q4FY24 file tags revenue as 1,758,600,000 INR with its rounding declared "Lakhs";
    the statement is in millions and the quarter was ₹1,758.6 Cr. Every amount in the file is a tenth of
    its value, so memory held FY24 at ₹670 Cr and the FY25 cards said revenue +979% YoY (2026-10-17).
    confirm() passed it, since 175.86 crore is the statement's 17,586 read as lakh. A slip is told from a
    real fall by two things moving together by the same power of ten: the quarter's revenue, and the share
    count its profit and EPS imply. A business that shrinks keeps its shares; a file in the wrong unit
    does not."""
    if result.kind != "RESULTS" or not result.period:
        return 0
    own = _quarters(result.metrics).get(result.period) or {}
    others = [f for period, f in _quarters(history).items() if period != result.period]

    def power(mine: float | None, theirs: list) -> int | None:
        theirs = [t for t in theirs if t and t > 0]
        if not mine or mine <= 0 or len(theirs) < 2:
            return None
        ratio = math.log10(statistics.median(theirs) / mine)
        k = round(ratio)
        return k if k and abs(ratio - k) <= _SCALE_TOLERANCE else None

    metric = next((m for m in _SCALE_REFERENCE if own.get(m)), None)
    if metric is None:
        return 0
    by_revenue = power(own[metric], [f.get(metric) for f in others])
    by_shares = power(_shares(own), [_shares(f) for f in others])
    return by_revenue if by_revenue is not None and by_revenue == by_shares else 0


def _printed_exactly(crore: float, text: str) -> bool:
    """Whether the text prints this ₹ crore amount to its last digit, in crore, lakh, million or thousand (appears_in
    rounds to whole numbers, which cannot tell 11.15 from 11.41)."""
    numbers = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*\.\d+|\d[\d,]*", text or "")
               if n.replace(",", "").replace(".", "").isdigit()]
    for scale in (1, 100, 10, 10_000):   # crore, lakh, million, thousand
        target = abs(crore) * scale
        if any(abs(n - target) <= 0.005 * scale + 1e-9 for n in numbers):
            return True
    return False


def settle_pbt(result: XbrlResult | None, text: str) -> list[str]:
    """The profit before tax the statement prints, where the file tags it before the share of associates.

    Orient Bell's Q1FY27 file tags ProfitBeforeTax 11.41 and the associates' share -0.26 apart; the statement prints
    11.15, and the card's PBT line was the unprinted one (live review 3, 2026-10-20). Filers differ in where they tag
    the share, so the statement decides: PBT plus the share replaces the tagged PBT only when the text prints that
    figure and not the tagged one. Returns the periods changed."""
    if result is None or not text:
        return []
    by = {}
    for m in result.metrics:
        by.setdefault(m.period, {})[m.metric] = m
    changed = []
    for period, line in by.items():
        pbt, share = line.get("pbt"), line.get("share_associates")
        if pbt is None or share is None or not share.value or pbt.value is None:
            continue
        alt = round(pbt.value + share.value, 2)
        if _printed_exactly(alt, text) and not _printed_exactly(pbt.value, text):
            changed.append(f"{period}: {pbt.value:g} -> {alt:g}")
            pbt.value, pbt.yoy_pct, pbt.qoq_pct = alt, None, None
    if changed:
        log.info("XBRL PBT taken after the associates' share, as the statement prints it: %s", changed)
    return changed


def fix_scale(result: XbrlResult | None, history, source: str = "") -> int:
    """Put a results file tagged in the wrong unit right (scale_slip): every ₹ crore amount, the balance
    sheet's included, times the power of ten found. EPS, per-share and percentage figures are left as
    they are. Returns the power applied, 0 for none."""
    k = scale_slip(result, history) if result else 0
    if not k:
        return 0
    factor = 10 ** k
    for m in result.metrics:
        if m.unit == "INR_CR" and m.value is not None:
            m.value = round(m.value * factor, 2)
    if result.balance_sheet:
        for name, value in result.balance_sheet.model_dump().items():
            if name.endswith("_cr") and isinstance(value, (int, float)):
                setattr(result.balance_sheet, name, round(value * factor, 2))
    log.warning("XBRL %s %s: amounts tagged at 10^%d of their value (revenue and the share count its profit "
                "and EPS imply both off by it against the company's other quarters); multiplied by %g",
                source, result.period, -k, factor)
    return k


_YEAR_GAP = 0.15        # a year's revenue this far from the sum of its four quarters is not their year
_QUARTER_BAND = (0.3, 2.0)   # with one quarter unknown, the one the year implies against the median of the others


def long_year(result: XbrlResult | None, history) -> str | None:
    """Why a results file's year is not its four quarters, or None when it is or there is too little to tell.

    Siemens moved its year end from September to March: its "year" to March 2026 is 18 months (October 2024 - March
    2026, ₹24,845.6 Cr of revenue), yet its own Q4 file dates the year-to-date context 1 April 2025 - 31 March 2026
    (owner's check against Screener's 18M column, 22 Oct 2026). Memory took the dates and stored the 18 months as
    a 12-month FY26. A year is its four quarters (Q1-Q4 of the same FY, the file's own quarter and memory's): with all
    four, its revenue is within 15% of their sum; with three, the fourth it implies is within 0.3-2x the median of
    the three."""
    if result is None or result.kind != "RESULTS":
        return None
    years = {m.period for m in result.metrics if re.fullmatch(r"FY\d\d", m.period or "")}
    if not years:
        return None
    quarters = _quarters([*(history or []), *result.metrics])
    for year in years:
        revenue = next((m.value for m in result.metrics if m.period == year and m.metric == "revenue"
                        and isinstance(m.value, (int, float))), None)
        if not revenue or revenue <= 0:
            continue
        known = [quarters[q]["revenue"] for q in (f"Q{i}{year}" for i in range(1, 5))
                 if q in quarters and quarters[q].get("revenue", 0) > 0]
        if len(known) == 4:
            total = sum(known)
            if abs(revenue / total - 1) > _YEAR_GAP:
                return f"{year} revenue ₹{revenue:,.1f} Cr against its four quarters' ₹{total:,.1f} Cr"
        elif len(known) == 3:
            implied, median = revenue - sum(known), statistics.median(known)
            if not _QUARTER_BAND[0] * median <= implied <= _QUARTER_BAND[1] * median:
                return (f"{year} revenue ₹{revenue:,.1f} Cr leaves ₹{implied:,.1f} Cr for its fourth quarter, against "
                        f"a median quarter of ₹{median:,.1f} Cr")
    return None


def drop_long_year(result: XbrlResult | None, history, source: str = "") -> str | None:
    """Take a year that is not its four quarters (long_year) out of a results file, every figure of it, so memory
    keeps the quarters and no year. Returns why, None when nothing was taken."""
    why = long_year(result, history)
    if not why:
        return None
    years = {m.period for m in result.metrics if re.fullmatch(r"FY\d\d", m.period or "")}
    result.metrics = [m for m in result.metrics if m.period not in years]
    log.warning("XBRL %s %s: its year is not twelve months of quarters (%s); the year's figures are not kept",
                source, result.period, why)
    return why


def add_comparatives(result: XbrlResult, *earlier: XbrlResult) -> int:
    """YoY and QoQ for a results file from the year-ago and previous quarters' own files. BSE's files
    carry only the current quarter and the year to date (Ahluwalia Q3FY25: Q3FY25 and 9MFY25), so the
    changes come from those quarters' filings. Their figures are added for memory too. Returns how
    many changes were filled."""
    if result.kind != "RESULTS":
        return 0
    known = {(m.metric, m.period): m for m in result.metrics}
    for other in earlier:
        if other and other.kind == "RESULTS" and (not result.basis or other.basis in (None, result.basis)):
            for m in other.metrics:
                if (m.metric, m.period) not in known:
                    known[(m.metric, m.period)] = m
                    result.metrics.append(m)
    filled = 0
    for m in result.metrics:
        if m.unit == "PCT" or m.value is None:
            continue
        year_ago = known.get((m.metric, prior_year_period(m.period) or ""))
        if m.yoy_pct is None and year_ago and year_ago.value:
            m.yoy_pct, filled = _change(m.value, year_ago.value), filled + 1
        before = known.get((m.metric, prior_quarter_period(m.period) or "")) if m.period.startswith("Q") else None
        if m.qoq_pct is None and before and before.value:
            m.qoq_pct, filled = _change(m.value, before.value), filled + 1
    return filled
