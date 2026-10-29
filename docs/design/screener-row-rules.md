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

**Which kind a new rule should be (owner, 29 Oct 2026):** "most of the screener rules must be event specific vs few, a very few on
the basis of company based on company structure like holding company or other different structures". So a rule fires on an
event the filing shows (a discontinued operation, a loss from associates, a negative regulatory-deferral movement, bank charges,
an exceptional item, a finance lease): the line's presence is the trigger, on any company. A rule by company structure
(holding company, a lender inside a group, associates kept outside PBT) is kept rare and needs a signal read from the filing
itself, never a list of names. An event seen at one company only, with no line to trigger on, stays a recorded exception.

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
| Tax % | TaxExpense / the size of Profit before tax (above): a loss with a tax charge shows a positive rate | Policy | 92 % quarters, 95 % years after the PBT rule; L&T standalone Q2FY26 PBT −2,982, screener +20.0; the 500 largest: 289 quarters and 88 years exact by the size rule, 1 year broken |
| Net Profit (website) | ProfitLossForPeriod (whole profit) | Policy (contradicts the help page; measured, docs/bench/screener-rules.md row 5) | 90 % quarters, 95 % years |
| Net Profit (Excel Data Sheet) | ProfitOrLossAttributableToOwnersOfParent | Policy | Airtel FY26 26,695.2; Reliance FY26 80,775 |
| Exceptional items AT | exceptional − tax × exceptional / PBT (the exceptional item itself if that tax is larger) | Policy (help article 42) | carried, not on the page |

Breakdown-row patterns (Wording; `screener_view.py` / `screener_parts.py` constants):
- `FINANCE_MEMBER`: "Finance cost(s) of / relating to / in respect of ... financial services | NBFC | HFC | lending | housing finance".
- `INVESTMENT_LOSS`: "(Net) loss ... investment(s)" in OtherExpenses (M&M Q4FY26 410.2 Cr = its Expenses gap); an "Impairment of
  investments" row stays in Expenses (Tech Mahindra standalone Q4FY24–Q4FY26, Cipla Q4FY26, Purvankara, Kolte-Patil, Jagran).
- a net regulatory expense (a negative movement in the regulatory deferral balances) is in Expenses, a net regulatory income in
  Other Income: NHPC Q4FY26 −559.22 = the Expenses gap, Tata Power Q1FY27 −153.09 and Q1FY26 −570.76 (the owner's NHPC and Tata
  Power sheets, 29 Oct 2026); about 62 quarters and 18 years of 11 utilities in the every-company run (Power Grid, SJVN, Adani
  Energy Solutions, NLC, NTPC).
- an owners' share filed as 0 with a minority of 0 (Paradeep Q2FY26–Q1FY27) is the whole profit.
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

NBFC template (29 Oct 2026, the owner's Aditya Birla Capital and Bajaj Holdings sheets): Expenses = Expenses − FinanceCosts −
depreciation; Operating Profit = Sales − Expenses (a holding company's page); Financing Profit = Revenue − Expenses − Interest (a
lender's page; no depreciation); Other Income = PBT + Depreciation + Interest − Operating Profit. Screener's own identities hold on
all 116 NBFCs of the every-company run (5,009 periods, no miss). Union Bank's Q3FY25–Q2FY26 Revenue and Interest are restated
(interbank interest netted from the Q3FY26 results; only the nine-month sum is filed): an Event exception.

Insurer template, and the older NBFC note: only Revenue, Interest, Depreciation, PBT (ProfitBeforeTax + the associates' share: Bajaj Holdings
Q2FY24 + 1,464.08, Jio Financial Q3FY24 + 66.11, 93 quarters of NBFCs and holding companies in the 500 largest), Tax, Net Profit,
cash flows, Equity, Reserves have a recipe;
the rest is reported `no_recipe` (Bajaj Finance within 233 Cr on Interest; LIC needs its own insurer recipe).

## Balance sheet

| Row | Recipe | Scope | Evidence |
|---|---|---|---|
| Equity Capital | EquityShareCapital | Statement | 97 % |
| Reserves | OtherEquity | Statement | 97 % |
| Borrowings | BorrowingsNoncurrent + BorrowingsCurrent + lease liabilities (elements, else described rows) + "current maturities" rows + bank-debt rows ("payable to banks", "due to banks", "gold on loan", "metal loan", "supplier's / buyer's credit"); a lease row counts only as a lease liability or obligation ("lease" then "lia" / "lib" / "obl", or "liability for lease": filers misspell it, HUL "Lease Liablities", Coal India "Lease Liabiiities", Persistent "CurrentbLease Liability", MTAR "lease libaility"), also when filed under the non-financial other liabilities (Ambuja FY25 304.14, Concor FY24 746.11, Delhivery FY25 243.88) | Policy (help article 11) + Sector (jewellers' gold loans; metals' supplier's credit) + Wording | Reliance FY26 270,751 + 103,670 + 23,579 + 4,962 = 402,962; Infosys 9,176; Titan standalone 7,043 / 14,314 payable to banks; Hindalco FY25 supplier's credit 1,713 (its temporary overdraft 13 is not counted); + CurrentMaturitiesOfFinanceLeaseObligations (58 rows of 23 companies in the 500 largest, the gap exactly); JSW Steel's "payable for sale and lease back" 1,286 is not debt |
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
| DLF, BEL and 13 more always (RELINFRA, TSFINV, MAZDOCK, TATACONSUM, TATACOMM, SUNPHARMA, PETRONET, RAMCOIND, ALEMBICLTD, ADANIENT, BALMLAWRIE, SHRIRAMFIN, TAJGVK; 12 more in 4 of 5 rows, Zydus, Sundaram Finance, Reliance, Sarda, L&T, Pilani, Marathon, GNFC, JK Tyre, Indian Hotels, Minda Corp, Hindware) | PBT, Other Income (and Expenses for a loss) | the owner's Excel files (29 Oct 2026): DLF FY25/FY26 PBT = the filed ProfitBeforeTax 2,260.63 / 2,931.82, Other Income = OtherIncome + exceptional; BEL PBT = filed 7,099.00 / 8,052.96; Net profit keeps the share. Nothing in the XBRL tells these from the 190 that count the share (same element, same place after tax, size 0.1–140 % of PBT, either sign, every sector) | a named list would fix about 200 rows with 0 broken (333 / 15 with the 12): owner (29 Oct 2026): kept as a separate list, validated over 10–12 years, no code reads it: `docs/design/screener-associates-outside-pbt.md` |
| Reliance, Sun Pharma, L&T | PBT, Other Income, Expenses (quarters and years) | screener leaves the associates' share out of every row: not in PBT (37 quarters with a profit, 22 with a loss), and a loss not in Expenses (the 39 rows the loss rule broke in run 40737252219 are all these three) | the XBRL cannot tell them apart: Reliance's results file has the share outside the filed PBT exactly as Coal India's does (checked 28 Oct 2026); its printed results put it after tax. If the larger batch shows more, read the P&L layout from the PDF |
| Sundaram Finance, Shriram Finance, Cholamandalam (and its holding company), Nippon AMC, Motilal Oswal, LIC Housing | an NBFC's PBT | the associates' share left out, as at Reliance (40 rows; the rule fixed 143 at Bajaj Holdings, M&M Finance, Tata Investment, Jio Financial, TVS Holdings, Nuvama and others) | the same company-layout class: not in the XBRL |
| M&M, JSW Steel, Asian Paints, Eicher, TVS, Solar | standalone FY23 Total Assets | the filed Assets, no deferred tax offset (FY23 from the Q4 results file) | lead only |
| Tata Consumer | Borrowings, Total Assets, Other Assets (FY24–FY26) | its cash and cash equivalents net an "Others" amount (−1,147.98, −1,348.21, −1,633.78 Cr; an overdraft or cash pool, assumption) that screener shows gross, as borrowing | one company: the "Others" member names nothing |
| DPS (DPSCLTD) standalone | Q1FY26, FY26 | a negative regulatory movement kept in Other Income | the one exact case against the rule |
| Vedanta, Tata Motors PV, Ambuja | restated quarters (Vedanta Q4FY25–Q3FY26 after the demerger, Sales 16,686 against 40,455 filed; TMPV Q4FY25–Q1FY26 after the CV demerger; Ambuja's depreciation after its acquisitions) | the demerger class | PDF only |
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

## Every company (run 40793194881, 29 Oct 2026, 06:48–07:09 IST)

1,856 companies read, 1,723 with facts to compare (565,126 pairs): **92.7 % exact, 94.3 % FY25–FY27**. The 1,226 companies
beyond the 500 largest: 93.4 % (94.8 %), so the rules hold on small companies too. Against the 500-company run, on the same
companies, the three rules of 34f7274 fixed 896 rows and broke 56 (90.65 % → 91.14 %): Tax % on the size of PBT 463 fixed and
14 broken; an NBFC's PBT with the associates' share 143 fixed and 40 broken, the 40 all companies that leave the share out
(Sundaram Finance 14, Shriram Finance 10, Cholamandalam 8, Nippon AMC 3, Motilal Oswal 3, LIC Housing 2: the same
company-layout class as Reliance's, recorded below); the lease wordings and parents 290 fixed, 2 broken.

### The next run (40797693366, 29 Oct 2026, eebadb4: regulatory expense, investment impairment, filler zero)

Against run 40793194881: 299 rows fixed, 56 broken; 92.74 % → 92.78 % exact (FY25–FY27 94.25 % → 94.30 %). The negative
regulatory-deferral movement in Expenses: quarters 61 fixed, 10 broken; years 2 fixed, 8 broken (SJVN FY24–FY26 both bases and
NLC India standalone FY23 are exact without it, Adani Energy Solutions FY24–FY25 exact with it). Kept: the quarters carry it.
Seven companies outside power file the element with small amounts (Narayana Hrudayalaya 4 quarters fixed; Atul, Ind-Swift Labs,
filers, Rentomojo, Venus Remedies, ADSL 9 rows broken, all under 9 Cr).

**Looked at, not a rule:** Borrowings below screener's by exactly OtherNoncurrentFinancialLiabilities in 189 balance sheets
(Other Liabilities above by the same), against 20 the other way. 100 of them are FY23 years read from the Q4 results file with
no lease line at all: the lease liability sits inside "other financial liabilities" there, and the element equals it only
where the company has nothing else in that line. Tata Power, NHPC, Ambuja, DLF, BEL, Maruti and the Tata Motors companies file
the element (54 to 11,007 Cr) and are exact without it (the owner's 15 companies' stored files). It is the FY23 data gap
above, not a recipe.

### What the four parallel reviews of the 500 found (29 Oct 2026)

- **The year's source decides most of the yearly misses.** Years read from the annual report: Expenses 82.4 % exact, Interest
  96.3 %; years read from the Q4 results file (FY23 almost all, and FY26 where no report is stored yet): 58.6 % and 76.7 %. The
  Q4 file carries no breakdown rows (levies, bank charges, the financing arm's cost, lease lines), so the fix is data: the FY24
  annual reports, whose comparative column holds FY23. The same holds for Borrowings: 468 of its 1,045 misses are FY23 years
  read from a results file with no lease breakdown at all (80 % of FY23 columns apart, 21–27 % of FY24–FY26).
- **Where a FY24 or older annual report could come from (measured 29 Oct 2026, owner's request, 4 NSE and 6 BSE requests, no
  refusal):** NSE's annual-report XBRL list (`annual-reports-xbrl`) holds FY25 and FY26 only (Maruti, Mankind, Vedanta; a date
  range changes nothing; 10 more companies the same day: 36 files listed, all stored); NSE's annual-report list
  (`annual-reports`) goes back to FY10, FY15–FY23 as zips, and the FY23 zip holds the PDF alone; BSE's annual-report list
  (`AnnualReport_New`) is PDF only from FY15; BSE's announcement rows carry an `XML_NAME` on every filing alike (a press release
  too), so it is the announcement's own XBRL, not the statements. The XBRL mandate for annual reports dates from FY2018-19
  (BSE and NSE circulars of 2019), but neither exchange serves those files through these lists. MCA's AOC-4 XBRL (every
  listed company since 2011, lenders excepted) is the full archive, paid per document: not a $0 source. FY23 years therefore
  stay on the Q4 results file (or the PDF).
- **Screener's year is not the sum of its own quarters** in 83 % of the yearly misses (31 % of the exact rows): the year
  carries a reclassification of the annual report. Summing quarters would fix 29 rows and break 377: rejected.
- **The deferred tax offset on Total Assets has no single rule.** Consolidated years offset (465 annual-report rows exact with
  it, 12 not); standalone is split (36 rows exact, 56 not; TCS, Infosys and Wipro standalone exact with it). "Offset only on
  consolidated" would net +30 rows but has no reason behind it: not coded.
- **Coincidences**, not rules: DeferredTax and other comprehensive income items on quarterly PBT (sign agrees in about half),
  OtherNoncurrentFinancialLiabilities and ProvisionsNoncurrent on Borrowings (aggregates that happen to equal a gap).
- **Still to settle:** an exception list for the 33 company-bases that leave the associates' share out of PBT (mixed quarters
  in several, so a per-company rule needs the P&L layout); SRF's "payable to banks for discounted receivables" (one company);
  CurrentMaturitiesOfLongTermDebt as its own element (4 companies, may already sit inside BorrowingsCurrent for others);
  two public-sector banks with no tax fact read (Union Bank, Canara Bank).

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
