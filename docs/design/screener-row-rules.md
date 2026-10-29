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
| Expenses | Expenses − FinanceCosts − depreciation − the Sales deductions − financing-arm finance cost − bank charges − loss on disposal of PPE − loss on investments + a loss from associates | Policy + Wording | loss on disposal: 29 rows agree, 8 not (IndiGo 6, below); a loss from associates: 43 of 43 quarters with Expenses and Other Income both apart by the share had a loss (JSW Steel, Power Grid, Nestle, TVS, Adani Ports, Bajaj Auto Q2FY25 580 Cr from KTM), a profit stays in Other Income; HAL FY26 Expenses 23,301.28 and IOC 707,307.56 after the bank charges; Reliance FY26 876,715 (with the PDF sales-tax line); Grasim Q1FY26 31,295.82 |
| Operating Profit | Sales − Expenses | Policy | |
| Other Income | PBT (as below) + Depreciation + Interest − Operating Profit; equals OtherIncome + exceptional + associates + regulatory deferral − loss on disposal − loss on investments | Policy | Airtel FY26 2,817.3 + 364.5 − 256.8 (labour-code charge) = 2,925.0 |
| Interest | FinanceCosts + the financing arm's finance-cost row of OtherExpenses + BankCharges (out of Expenses) | Sector (conglomerates with a lending arm) + Wording; bank charges: Policy (any company that tags them) | HAL, IndiGo, IOC FY24–FY26, both bases: the yearly gap = BankCharges to within 0.5 Cr (e.g. IOC FY26 cons 8,307.88 + 46.22 = 8,354); L&T FY26 2,848.82 + 6,995.34 (+ bank charges 211.78, PDF note only) = 10,055.94; Grasim Q1FY26 816.2 + 2,734.5 = 3,550.71 |
| Depreciation | DepreciationDepletionAndAmortisationExpense | Statement | 93 % exact |
| Profit before tax | ProfitBeforeTax + associates' share + net movement in regulatory deferral balances + profit from discontinued operations after tax | Policy (associates are "other ordinary income"; screener has no discontinued line) + Sector (utilities) | HUL FY26 13,812 + 4,407 = 18,219 and Q3FY26 2,919 + 4,485 = 7,404 (ice-cream demerger); ITC Q3FY25 + 203.44 (hotels); 39 of 55 quarters with associates; Coal India Q4FY26 14,510.7 + 116.1 = 14,626.75; NTPC Q1FY26 5,281.2 + 2,007.3 + 476.6 = 7,765.06; Power Grid Q1FY26 4,330.2 + 212.8 − 44.4 = 4,498.57 |
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
| Net Profit (website) | ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates + ProfitLossOfMinorityInterest (the whole profit, as for every company) | consolidated quarters of HDFC Bank Q3FY24–Q1FY27 and ICICI Q3FY24–Q2FY26: the gap = the minority's share each quarter |
| Net Profit (Excel Data Sheet) | ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates | ICICI 54,208, SBI 83,299 |
| Deposits / Borrowing | separate lines (screener, March 2025) | 100 % on the banks compared |

NBFC and insurer templates: only Revenue, Interest, Depreciation, PBT, Tax, Net Profit, cash flows, Equity, Reserves have a recipe;
the rest is reported `no_recipe` (Bajaj Finance within 233 Cr on Interest; LIC needs its own insurer recipe).

## Balance sheet

| Row | Recipe | Scope | Evidence |
|---|---|---|---|
| Equity Capital | EquityShareCapital | Statement | 97 % |
| Reserves | OtherEquity | Statement | 97 % |
| Borrowings | BorrowingsNoncurrent + BorrowingsCurrent + lease liabilities (elements, else described rows) + "current maturities" rows + bank-debt rows ("payable to banks", "due to banks", "gold on loan", "metal loan", "supplier's / buyer's credit"); a lease row counts only as "lease liabilities" ("lease" then "lia": filers misspell it, HUL "Lease Liablities", Coal India "Lease Liabiiities") | Policy (help article 11) + Sector (jewellers' gold loans; metals' supplier's credit) + Wording | Reliance FY26 270,751 + 103,670 + 23,579 + 4,962 = 402,962; Infosys 9,176; Titan standalone 7,043 / 14,314 payable to banks; Hindalco FY25 supplier's credit 1,713 (its temporary overdraft 13 is not counted); + CurrentMaturitiesOfFinanceLeaseObligations (58 rows of 23 companies in the 500 largest, the gap exactly); JSW Steel's "payable for sale and lease back" 1,286 is not debt |
| Fixed Assets | PPE + Goodwill + OtherIntangibleAssets + InvestmentProperty + right-of-use assets (element, else the described row of OtherNoncurrentAssets) | Policy | TCS FY26 + 11,027 right-of-use; L&T 3,774 |
| CWIP | a year's column: CapitalWorkInProgress + IntangibleAssetsUnderDevelopment; the half-year column (September, from the results file): CapitalWorkInProgress only, intangibles under development in Fixed Assets | Policy (measured, by source) | Reliance FY26 237,686; HCL Tech, UltraTech, JSW Steel, Hindustan Zinc, Adani Green Q2FY27: CWIP and Fixed Assets both apart by IntangibleAssetsUnderDevelopment |
| Investments | NoncurrentInvestments + CurrentInvestments + InvestmentsAccountedForUsingEquityMethod | Policy | 98 % |
| Total | a year's column: Assets − min(DeferredTaxAssetsNet, DeferredTaxLiabilitiesNet); the half-year column: Assets as filed | Policy (deferred tax shown net) | Reliance 594, Infosys 1,679; HCL Tech, Adani Power, Adani Green, Wipro, Torrent Pharma Q2FY27 apart by exactly the offset, HCL Tech's year columns FY23–FY26 exact with it |
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
| Reliance | Sales, Expenses | sales tax / VAT 1,439 (FY26), 1,873 (FY25) is a line of the PDF's other-expenses note only | not in either XBRL file |
| L&T | Interest; Power and fuel | bank charges 211.78 and the split of power and fuel by note are PDF-only | |
| Airtel | Expenses | FY26 regulatory levy 3,160.7 put into Expenses, the labour-code charge into Other Income (note 32) | screener splits one-offs by nature; PDF note only |
| Maruti | FY23 (all rows) | restated after the Suzuki Motor Gujarat merger; NSE lists no FY24 annual-report XBRL | PDF only |
| Hindustan Unilever | Quarters before Q3FY26 (Sales, Expenses) | restated after the ice-cream demerger (Q1FY26 Sales 16,514 filed, 15,757 restated) | NSE's quarterly XBRL holds the current period only (no comparative column, checked on HUL Q1FY27: one duration context), so a restated quarter is PDF-only |
| ITC | Quarters Q3FY24–Q2FY25 (Sales, Expenses, Other Income, PBT) | restated after the hotels demerger (Sales 680–885 Cr less in screener's); every quarter from Q3FY25 exact | the same class as Hindustan Unilever: a demerger restates the quarters before it, and only the later PDF carries them. Pattern for the larger batch: a run of quarters apart on Sales and Expenses that ends at a demerger's effective quarter |
| Grasim | Quarters Q1–Q3 FY25 (Sales, Expenses) | about 585–770 Cr more in screener's Sales and Expenses, Operating Profit within 25 Cr: a restatement (assumption) | as above |
| Hindalco | Borrowings FY24 | the FY25 annual report's comparative column has "Supplier's credit" 4,475 Cr (cons) for FY24; screener's FY24 (56,356 cons, 8,376 standalone) leaves it out, while its FY25 includes the 1,713 Cr. Adani Green and Hindalco FY25 taken from a later report's comparative both match with it | assumption: a reclassification into the row in the FY25 report that screener's FY24 (from the FY24 report) never had; no FY24 annual-report XBRL is stored to check. If more companies show a comparative-column row the year's own report lacked, the year source rule changes |
| IndiGo | Expenses, Other Income (years) | screener keeps its loss on disposal (48.2 Cr FY25, 51.7 Cr FY26) in Expenses, both bases; 29 other rows of 13 companies take it out | assumption: aircraft sale-and-leaseback disposals are a normal operating item for an airline. Watch other airlines in the larger batch |
| Reliance, Sun Pharma, L&T | PBT, Other Income, Expenses (quarters and years) | screener leaves the associates' share out of every row: not in PBT (37 quarters with a profit, 22 with a loss), and a loss not in Expenses (the 39 rows the loss rule broke in run 40737252219 are all these three) | the XBRL cannot tell them apart: Reliance's results file has the share outside the filed PBT exactly as Coal India's does (checked 28 Oct 2026); its printed results put it after tax. If the larger batch shows more, read the P&L layout from the PDF |
| M&M, JSW Steel, Asian Paints, Eicher, TVS, Solar | standalone FY23 Total Assets | the filed Assets, no deferred tax offset (FY23 from the Q4 results file) | lead only |
| Grasim | Investments | about 38,000–40,000 Cr short (insurance business investments, assumption) | to check |

## Open sector patterns (measured, not yet a rule)

| Sector | What the sector view shows | Lead | Why not coded yet |
|---|---|---|---|
| Oil and gas | Total Assets apart in 22 of 32 pairs; screener's total is ABOVE the filed Assets (ONGC 731–1,201 Cr, IOC 310–397 Cr) | ONGC consolidated tags an inventory impairment allowance as a negative Inventories member, 1,010.5 / 1,200.89 Cr = the gap within 1 Cr: screener may show inventory gross and the allowance as a liability | one company, one basis: ONGC standalone and IOC have no such fact for their gaps |
| Power | yearly Other Income / Expenses / Operating Profit apart in 25–26 of 32 pairs, while Sales, PBT and Net Profit are exact in all of them | tried "the regulatory deferral movement sits in Expenses" on 8 company-years (NTPC, Power Grid, FY25–FY26, both bases): closer in 4, further in 4, exact in none; NTPC consolidated keeps it in Other Income, NTPC standalone in Expenses. Screener's own four quarters do not add up to its year (NTPC standalone FY25 Other Income 8,652 Cr over the quarters, 861 Cr for the year) and its Data Sheet "Other Expenses" is negative every year for NTPC (−2,301 to −7,699 Cr): the yearly split comes from a breakdown with a balancing line, not from the filed totals | not reproducible from the filings (measured 28 Oct 2026). Operating Profit and OPM of a power company are shown with that caveat; Sales, PBT and Net Profit are the rows to trust |
| Banks | yearly Expenses and Depreciation apart in equal and opposite amounts (Axis FY26 −1,810 / +1,810, Kotak FY24 −272 / +271, ICICI about 61 every year); HDFC Bank and SBI exact | the results file has one depreciation element, the cash-flow adjustment (Axis FY26 3,699 Cr), which also carries other amortisation; screener's figure (1,889) is the fixed-asset depreciation of the report's schedule | PDF only; the sum and Financing Profit are not moved by it |
| Capital goods, NBFC, aviation | yearly Interest above the filed finance cost in every year, by a small steady amount (HAL 6–18 Cr, BEL 2–5, IndiGo 36–53, Shriram 55–74, Bajaj Finance 139–233, Bajaj Finserv 179–309), while every quarter of the same years is exact (7 of 7 companies, 52 of 52 quarters) | an item of the annual report that screener adds to Interest (L&T's bank charges 211.78 Cr is one, PDF-only); the lenders have no annual-report XBRL, so their item comes from the report itself | the `screener-rows` report now names every filed fact equal to a row's gap ("gap matches", by row and across companies) to find it |

## The 500 largest (run 40759776253, 29 Oct 2026)

The rules worked out on the top 50 run unchanged on the next 450: exact 91.0 % of all pairs (92.8 % FY25–FY27), against
87.6 % (90.0 %) on the 50 themselves, so the rules generalise rather than fit. The associates rule holds: 2,302 PBT rows with a
material share agree with it, 326 do not (9 companies always against it: Adani Enterprises, BEL, DLF, Mazagon Dock, Natco,
Petronet, Sun Pharma, Tata Communications, Tata Consumer; 29 mixed, Reliance and L&T among them). Weakest rows: Other
Liabilities 59.6 %, Borrowings 65.4 %, yearly Operating Profit 72.1 %, Expenses 73.5 %, Other Income 75.1 %.

## How a pattern is found

The `screener-rows` report names, for every row apart by 2 Cr or more, the filed facts of that column equal to the gap within
₹1 Cr (an element, or a breakdown row by its words), and lists the leads seen in two or more companies on one row. A lead
becomes a rule only when it closes the gap in every company it names and breaks no row that was exact (the next run's
before/after). Leads of 28 Oct 2026 made rules the same day: bank charges, discontinued operations, a bank's minority share, the half-year
balance sheet (intangibles under development, the deferred tax offset), a loss from associates. Still a lead: other
comprehensive income items on quarterly PBT (7 companies, probably chance).

## Patterns to watch in a larger batch

The report of `screener-rows` will be grouped by sector as well as by row, so a rule that is really a sector practice shows up
as one sector's rows all apart (expected next: other utilities for the regulatory deferral rule, other conglomerates with a
lending arm — Bajaj Finserv, Aditya Birla group, Tata Motors — for the finance-cost row, other jewellers — Kalyan, Senco — for
gold loans, oil marketers — BPCL, HPCL — for excise, cement and steel for freight/discount rows).
