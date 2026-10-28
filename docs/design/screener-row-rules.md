# Screener row rules: one recipe a row, with its scope and evidence

The one place every rule of `pipeline/src/bse_intel/screener_view.py` is written down (owner, 28 Oct 2026: "all the findings
must go into the rules file ... those rules must apply to other companies ... find the pattern: sector or industry practice,
or individual companies and their events"). A rule is added here in the same commit as its code and its test. Measured with
`screener-rows` (Maintenance, read only) on the top 50 by market cap; exact = within ₹1 Cr or 0.05 % of screener's figure.

**Scope** says why a rule holds, which decides whether it can be trusted on a company we have not checked:
- **Policy**: screener's own documented treatment (support.screener.in articles 4, 11, 42; screener.in/docs changelog). Applies to
  every company; a company that breaks it is an exception to record, not a reason to drop the rule.
- **Statement**: how Ind AS / SEBI's results format lays out a line; holds for every filer of that template.
- **Sector**: holds for an industry because of how that industry reports (utilities, lenders, insurers, conglomerates with a
  financing arm, jewellers, oil marketers, tobacco). Expect it on every company of the sector, and only there.
- **Wording**: the item is a filer's own breakdown row (a `DescriptionOf...` text), so the rule is a text pattern; it holds
  wherever the words are used, and a new wording needs the pattern widened (never a company name in code).
- **Event**: one company's one-off (a merger restatement, a levy, its own layout). Recorded, not coded; the row stays apart.

Source of a quarter: its own results file. NSE's results XBRL has no comparative column (measured 28 Oct 2026, Hindustan
Unilever Q1FY27: only the quarter's own contexts), so screener's restated quarters (a merger, a demerger) cannot be read from
XBRL; they are Event exceptions below.

Source of a year (policy, docs "annual-quarterly-filings"): the newest stored annual report that holds the year (a later report's
comparative column counts: restated years), else the Q4 results file's 12-month context. Lenders always the Q4 file (NSE has no
annual-report XBRL for banks, NBFCs or insurers). Consolidated by default; standalone pages are compared on their own basis.

## Profit and loss (corporate: Ind AS template)

| Row | Recipe | Scope | Evidence (exact unless noted) |
|---|---|---|---|
| Sales | RevenueFromOperations − excise (element, or the OtherExpenses row "Excise duty") − sales tax / VAT / GST / discount rows | Policy | ITC FY26 89,913.33 − 11,044.93 = 78,868.40; Reliance FY26 1,075,675 − 18,456 − 1,439 (sales tax, PDF note only) = 1,055,780 |
| Expenses | Expenses − FinanceCosts − depreciation − the Sales deductions − financing-arm finance cost − loss on disposal of PPE − loss on investments | Policy + Wording | Reliance FY26 876,715 (with the PDF sales-tax line); Grasim Q1FY26 31,295.82 |
| Operating Profit | Sales − Expenses | Policy | |
| Other Income | PBT (as below) + Depreciation + Interest − Operating Profit; equals OtherIncome + exceptional + associates + regulatory deferral − loss on disposal − loss on investments | Policy | Airtel FY26 2,817.3 + 364.5 − 256.8 (labour-code charge) = 2,925.0 |
| Interest | FinanceCosts + the financing arm's finance-cost row of OtherExpenses | Sector (conglomerates with a lending arm) + Wording | L&T FY26 2,848.82 + 6,995.34 (+ bank charges 211.78, PDF note only) = 10,055.94; Grasim Q1FY26 816.2 + 2,734.5 = 3,550.71 |
| Depreciation | DepreciationDepletionAndAmortisationExpense | Statement | 93 % exact |
| Profit before tax | ProfitBeforeTax + associates' share + net movement in regulatory deferral balances | Policy (associates are "other ordinary income") + Sector (utilities) | 39 of 55 quarters with associates; Coal India Q4FY26 14,510.7 + 116.1 = 14,626.75; NTPC Q1FY26 5,281.2 + 2,007.3 + 476.6 = 7,765.06; Power Grid Q1FY26 4,330.2 + 212.8 − 44.4 = 4,498.57 |
| Tax % | TaxExpense / Profit before tax (above) | Policy | 92 % quarters, 95 % years after the PBT rule |
| Net Profit (website) | ProfitLossForPeriod (whole profit) | Policy (contradicts the help page; measured, docs/bench/screener-rules.md row 5) | 90 % quarters, 95 % years |
| Net Profit (Excel Data Sheet) | ProfitOrLossAttributableToOwnersOfParent | Policy | Airtel FY26 26,695.2; Reliance FY26 80,775 |
| Exceptional items AT | exceptional − tax × exceptional / PBT (the exceptional item itself if that tax is larger) | Policy (help article 42) | carried, not on the page |

Breakdown-row patterns (Wording; `screener_view.py` / `screener_parts.py` constants):
- `FINANCE_MEMBER`: "Finance cost(s) of / relating to / in respect of ... financial services | NBFC | HFC | lending | housing finance".
- `INVESTMENT_LOSS`: "(Net) loss / impairment ... investment(s)" in OtherExpenses (M&M Q4FY26 410.2 Cr = its Expenses gap).
- levies: "Excise duty", "Sales tax", "VAT", "GST", discounts / rebates.

## Profit and loss (lenders: BANKING template)

| Row | Recipe | Evidence |
|---|---|---|
| Revenue | InterestEarned | HDFC Bank, ICICI, SBI FY26 exact |
| Expenses | OperatingExpenses + ProvisionsOtherThanTaxAndContingencies − depreciation | HDFC Bank FY26 203,635 |
| Other Income | OtherIncome + a positive exceptional item | SBI FY26 +3,027 |
| Profit before tax | ProfitLossFromOrdinaryActivitiesBeforeTax − a negative exceptional item | HDFC Bank FY26 98,948 + 3,193 = 102,141 |
| Net Profit | ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates | ICICI 54,208, SBI 83,299 |
| Deposits / Borrowing | separate lines (screener, March 2025) | 100 % on the banks compared |

NBFC and insurer templates: only Revenue, Interest, Depreciation, PBT, Tax, Net Profit, cash flows, Equity, Reserves have a recipe;
the rest is reported `no_recipe` (Bajaj Finance within 233 Cr on Interest; LIC needs its own insurer recipe).

## Balance sheet

| Row | Recipe | Scope | Evidence |
|---|---|---|---|
| Equity Capital | EquityShareCapital | Statement | 97 % |
| Reserves | OtherEquity | Statement | 97 % |
| Borrowings | BorrowingsNoncurrent + BorrowingsCurrent + lease liabilities (elements, else described rows) + "current maturities" rows + bank-debt rows ("payable to banks", "due to banks", "gold on loan", "metal loan", "supplier's / buyer's credit"); a lease row counts only as "lease liabilities" | Policy (help article 11) + Sector (jewellers' gold loans; metals' supplier's credit) + Wording | Reliance FY26 270,751 + 103,670 + 23,579 + 4,962 = 402,962; Infosys 9,176; Titan standalone 7,043 / 14,314 payable to banks; Hindalco FY25 supplier's credit 1,713 (its temporary overdraft 13 is not counted); JSW Steel's "payable for sale and lease back" 1,286 is not debt |
| Fixed Assets | PPE + Goodwill + OtherIntangibleAssets + InvestmentProperty + right-of-use assets (element, else the described row of OtherNoncurrentAssets) | Policy | TCS FY26 + 11,027 right-of-use; L&T 3,774 |
| CWIP | CapitalWorkInProgress + IntangibleAssetsUnderDevelopment | Policy | Reliance FY26 237,686 |
| Investments | NoncurrentInvestments + CurrentInvestments + InvestmentsAccountedForUsingEquityMethod | Policy | 98 % |
| Total | Assets − min(DeferredTaxAssetsNet, DeferredTaxLiabilitiesNet) | Policy (deferred tax shown net) | Reliance 594, Infosys 1,679 |
| Other Liabilities / Other Assets | the balancing lines | | |
| (no balance sheet in the file) | no value, never 0 | | the Q4 files of FY21–FY23 |

## Cash flow

| Row | Recipe | Evidence |
|---|---|---|
| Operating / Financing / Net | CashFlowsFromUsedIn...Activities; IncreaseDecreaseInCashAndCashEquivalents | 93–96 % |
| Investing | CashFlowsFromUsedInInvestingActivities + EffectOfExchangeRateChangesOnCashAndCashEquivalents | Infosys 1,946 + 1,600; HDFC 1,114; ICICI 1,306; SBI 9,931 |

## Known exceptions (Event: recorded, not coded)

| Company | Row | What | Why it stays apart |
|---|---|---|---|
| Reliance, Sun Pharma | PBT, Other Income | screener keeps the filed PBT, associates left out (Reliance prints them after tax; Sun Pharma Q1FY26 3,172.77 = filed, ours with associates 3,163.02) | 2 of the 13 companies with Excel files; the XBRL cannot show the print layout. If the larger batch shows more, read the P&L layout from the PDF |
| Reliance | Sales, Expenses | sales tax / VAT 1,439 (FY26), 1,873 (FY25) is a line of the PDF's other-expenses note only | not in either XBRL file |
| L&T | Interest; Power and fuel | bank charges 211.78 and the split of power and fuel by note are PDF-only | |
| Airtel | Expenses | FY26 regulatory levy 3,160.7 put into Expenses, the labour-code charge into Other Income (note 32) | screener splits one-offs by nature; PDF note only |
| Maruti | FY23 (all rows) | restated after the Suzuki Motor Gujarat merger; NSE lists no FY24 annual-report XBRL | PDF only |
| Hindustan Unilever | Quarters before Q3FY26 (Sales, Expenses) | restated after the ice-cream demerger (Q1FY26 Sales 16,514 filed, 15,757 restated) | NSE's quarterly XBRL holds the current period only (no comparative column, checked on HUL Q1FY27: one duration context), so a restated quarter is PDF-only |
| Grasim | Quarters Q1–Q3 FY25 (Sales, Expenses) | about 585–770 Cr more in screener's Sales and Expenses, Operating Profit within 25 Cr: a restatement (assumption) | as above |
| Grasim | Investments | about 38,000–40,000 Cr short (insurance business investments, assumption) | to check |

## Open sector patterns (measured, not yet a rule)

| Sector | What the sector view shows | Lead | Why not coded yet |
|---|---|---|---|
| Oil and gas | Total Assets apart in 22 of 32 pairs; screener's total is ABOVE the filed Assets (ONGC 731–1,201 Cr, IOC 310–397 Cr) | ONGC consolidated tags an inventory impairment allowance as a negative Inventories member, 1,010.5 / 1,200.89 Cr = the gap within 1 Cr: screener may show inventory gross and the allowance as a liability | one company, one basis: ONGC standalone and IOC have no such fact for their gaps |
| Power | yearly Other Income / Expenses / Operating Profit apart in 25–26 of 32 pairs; NTPC Q4FY26 Operating Profit 6,815 apart ≈ that quarter's regulatory deferral movement −6,813.5 | the regulatory deferral movement may sit in screener's Sales or Expenses in a year-end quarter | Q1 (movement 2,007, gap 578) does not fit |
| Capital goods, NBFC | yearly Interest apart in 16 of 16 / 20 of 24 pairs | an item screener adds to Interest every year (L&T's bank charges are one such, PDF-only) | to measure |

## Patterns to watch in a larger batch

The report of `screener-rows` will be grouped by sector as well as by row, so a rule that is really a sector practice shows up
as one sector's rows all apart (expected next: other utilities for the regulatory deferral rule, other conglomerates with a
lending arm — Bajaj Finserv, Aditya Birla group, Tata Motors — for the finance-cost row, other jewellers — Kalyan, Senco — for
gold loans, oil marketers — BPCL, HPCL — for excise, cement and steel for freight/discount rows).
