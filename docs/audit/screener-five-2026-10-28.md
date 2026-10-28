# Screener against NSE's XBRL and our memory: five large companies (28 Oct 2026)

Owner's goal: match all three statements with screener.in for five large companies from five industries, over the last six quarters, so that every reason our numbers and screener's differ is known before we do 50 companies. Basis: consolidated. Read-only investigation; no pipeline code changed.

Companies: TCS (IT), SUNPHARMA (pharma), LT (engineering and finance), TATASTEEL (metals), ITC (FMCG, heavy excise).

## 1. The short answer, in plain English

- **Our memory is right.** We compared 2,780 figures in our live memory with the raw numbers in NSE's XBRL files (consolidated and standalone, every quarter, half year, nine months and year we hold). Not one differs by more than ₹0.011 Cr (memory rounds to 2 decimals). The pipeline's own reader (`bse_intel.xbrl.parse`) gives the same figures as the raw file for every metric checked. So every gap to screener below is a difference of definition or source, not an error in our numbers. Two small housekeeping problems in memory are listed in section 2.
- **Screener's numbers can be rebuilt from the XBRL file** with a short list of rules (section 4). Of 442 screener figures compared (quarterly table, FY26 profit and loss, balance sheet, cash flow): **282 match an XBRL element as it is (63.8%), 145 match once a named rule is applied (32.8%), 15 are not explained (3.4%).**
- **The 15 gaps** are: the FY26 annual profit-and-loss split for three companies (11 figures: screener's annual column is not the sum of its own four quarters, so it comes from another source, most likely the annual report), and four figures of the L&T Sep 2026 balance sheet (the file does not tag lease liabilities; screener splits fixed assets and CWIP differently). Section 5.
- **One rule is company-specific and we do not yet know why:** screener adds the associates' and joint ventures' profit share to Other Income and to PBT for ITC and Tata Steel, but not for L&T and Sun Pharma. Within each company the choice never changes over six quarters. The pipeline's `screener_crosscheck` already handles it by trying both. Section 4, rule P4.
- Our memory differs from screener by definition on several lines (section 3): revenue before excise (ITC), expenses including interest and depreciation, borrowings without leases, fixed assets without goodwill and intangibles, total assets without deferred-tax netting.

- **Screener's Excel (section 11) settles the formulas to the paisa:** 371 of 378 figures with an XBRL counterpart are reproduced exactly, the 7 exceptions are all in the FY26 annual column (annual-report classification). Screener's Data Sheet Net profit is the owners' share, while its web page shows the whole profit; no other row differs between the two. The associates' share (rule P4) is counted for ITC and Tata Steel (profit years) and not for L&T and Sun (loss for FY26), but the exact decision rule is still open.

## 2. Where our memory differs from the XBRL files (our own errors, listed first)

Figures: **none.** 2,376 profit-and-loss checks (25 metrics x periods x two bases) and 404 balance-sheet checks, 0 differ. Checked for all 5 companies, consolidated and standalone, every file downloaded.

Two housekeeping findings in the memory entries (not wrong numbers, but they will confuse a reader or a check that takes "the last entry"):

1. **Duplicate and oddly named balance-sheet entries.** The balance sheet list of a company holds several entries for one period, and some with labels that are not quarters:
   - TCS: `Q2FY27` twice (the second has no figures, only a news id), `May-2026` twice and `Jun-2026` (credit rating only).
   - Sun Pharma: `Q4FY26` twice (one with only debt, cash, net worth; one full), `Sep-2026` (no figures; stamped 7 May 2026, so the label is wrong) and one entry with no period.
   - L&T: `Mar-2026` six times and `Sep-2026` (credit-rating only entries).
   - Tata Steel: `Q4FY26` three times, `Mar-2026`, `May-2026`.
   - ITC: `Q4FY26` twice.
   A reader that takes the last entry of a period gets an empty one for TCS Q2FY27 (this is what my first pass did).
2. **Tata Steel net debt has two values for the same period.** The AI-sourced entries say gross debt 92,382, net debt 80,100 (entry from 20 May 2026) and net debt 80,144, cash 11,573 (entry from 15 May 2026, labelled `Mar-2026`). The XBRL-sourced entry has gross debt 92,381.68 and cash 8,884.95 (net 83,496.7). The AI entries count more than bank and cash balances as cash; the two AI entries also disagree with each other by 44 Cr.

Also: **L&T standalone Q2FY27 is not in memory yet** (52 metrics and the balance sheet; the consolidated one is). L&T filed these on 27 Oct 2026, the day before this check. Not an error, a lag.

## 3. Where memory and screener differ by definition (not errors)

How often our memory figure equals screener's figure (of 32 profit-and-loss periods: 27 quarters or years by company, 7 balance-sheet columns, 5 cash-flow years):

| Screener row | Memory field compared | Equal in | Why it differs |
|---|---|---|---|
| Sales | revenue from operations | 26 of 32 | Screener takes excise duty out. ITC only: memory shows revenue with excise (Q1FY27 29,523 against screener 19,114: excise 10,409). |
| Expenses | total expenses | 0 of 32 | Screener leaves out interest and depreciation (and excise). |
| Operating Profit | our EBITDA | 23 of 32 | Same unless excise cancels (ITC: equal) or finance cost of a financial-services arm sits in expenses (L&T: memory 6,318 against screener 8,024 in Q1FY26). |
| OPM % | our EBITDA margin | 18 of 32 | ITC (excise out of sales) and L&T. |
| Other Income | other income | 9 of 32 | Screener adds exceptional items (every company) and, for ITC and Tata Steel, the associates' share. |
| Interest | finance cost | 25 of 32 | L&T: screener adds the finance cost of the financial-services business, which L&T tags as a member of other expenses. |
| Depreciation, Net Profit | same | 32 of 32 | Screener's Net Profit is the whole profit (before the minority share), same as our `pat`. |
| Profit before tax | pbt | 20 of 32 | Associates' share added for ITC and Tata Steel. |
| Tax % | tax / pbt | 28 of 32 | Same cause (screener divides by its own PBT). |
| EPS | basic EPS | 29 of 32 | Sun Pharma tags EPS to 1 decimal; screener computes 2 decimals. |
| Borrowings | gross debt | 1 of 7 | Memory leaves out lease liabilities (TCS: memory 0, screener 11,283). |
| Total | total assets | 2 of 7 | Screener nets deferred tax in the March column. |
| Fixed Assets | PPE only | 0 of 7 | Screener adds goodwill, intangibles, investment property and right-of-use assets. |
| Investments | current + non-current investments | 3 of 7 | Screener adds investments in associates and joint ventures (equity method). |
| Cash flow: Investing | investing cash flow | 1 of 5 | Screener puts the exchange-rate effect on cash into Investing. |

If cards ever quote "operating profit" or "revenue" next to a screener figure, ITC's revenue and L&T's operating profit and interest are the two places where a reader will see a difference from screener for a good reason.

## 4. Screener's formulas, rebuilt from the XBRL elements

All amounts in crore (XBRL rupees / 10^7). Period = the 3-month context ending on the quarter end (quarter), or the 12-month context in the Q4FY26 file (year). Tested on 5 companies x 5 or 6 quarters, FY26.

### Profit and loss

| Id | Rule | Holds for |
|---|---|---|
| P1 | **Sales = RevenueFromOperations - excise.** Excise = `OtherExpenses` on the member whose `DescriptionOfOtherExpenses` is "Excise Duty" (axis `in-capmkt:DetailsOfOtherExpensesAxis`). | ITC (5 of 5 quarters and the year). The other four have no excise member. |
| P5 | **Expenses = Expenses - FinanceCosts - DepreciationDepletionAndAmortisationExpense - excise** (- P2). | All 5. |
| P2 | **Interest = FinanceCosts + the OtherExpenses member described as "Finance cost of financial services business ..."**, which is taken out of Expenses. | L&T (6 of 6 quarters: 1,706 to 2,033 Cr a quarter). No other company has such a member. |
| | **Operating Profit = Sales - Expenses; OPM % = Operating Profit / Sales.** | All 5. |
| P3 | **Other Income = OtherIncome + ExceptionalItemsBeforeTax** (a loss lowers it; TCS Q3FY26: 1,118 - 3,391 = -2,273, screener -2,273). | All 5 (zero exceptional items are neutral). |
| P4 | **+ ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod** added to Other Income, and so to PBT. | **Added: ITC, Tata Steel (and BPCL, lead's earlier check). Not added: L&T, Sun Pharma.** TCS has no share. Constant within a company over all quarters: ITC 5 of 5 quarters (share 66 to 140 Cr), Tata Steel 5 of 5 (50 to 134 Cr), L&T 6 of 6 not added (-184 to +34 Cr), Sun 5 of 5 not added (-20 to -10 Cr). Cause not settled: not the size against PBT (L&T Q4FY26 -184 is 2.2% of PBT and not added; ITC's 1% is added), and not the sign of each quarter alone; the Excel Data Sheet (section 11.3) shows the companies that count it are the profit-making ones for FY26 and the ones that leave it out have a loss for FY26, but L&T's two profit quarters of FY27 are still left out. Under one uniform "add" rule 22 pairs (Other Income and PBT of the L&T and Sun quarters) would fail; under a uniform "do not add" rule 20 pairs (ITC and Tata Steel) would. |
| | **Profit before tax = Sales - Expenses + Other Income - Interest - Depreciation.** In the XBRL this is `ProfitBeforeTax` (no associates; P4 off) or `ProfitBeforeTax` + the share (P4 on). | All 5. |
| P8 | **Tax % = TaxExpense / screener's PBT.** | All 5. |
| P6 | **Net Profit = ProfitLossForPeriod, the whole profit including the minority share** (not the owners' share). | All 5, 32 of 32 periods. (Screener's own help page says owners; measurement says whole profit: same finding as `screener-rules.md` row 5.) |
| P7 | **EPS = BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations.** Sun Pharma tags 1 decimal (47.8, 14.0, 12.1); screener prints 2 (47.84, 14.04, 12.06) from its own profit and share count. | Exact for 29 of 32, rounding for 3 (all Sun). |

### Balance sheet (screener's Mar 2026 column from the Q4FY26 file; Sep 2026 column from the Q2FY27 file)

| Id | Rule | Holds for |
|---|---|---|
| B0 | Equity Capital = EquityShareCapital. Reserves = OtherEquity (the owners' reserves; the minority share is not here). | All 5, exact (7 of 7 columns). |
| B1 | **Borrowings = BorrowingsNoncurrent + BorrowingsCurrent + lease liabilities.** Lease liabilities = the member "Lease liabilities" of `OtherNoncurrentFinancialLiabilities` and `OtherCurrentFinancialLiabilities`. | TCS (9,453 + 1,830 = 11,283), Sun (4,081 + 546), ITC (2,186 + 213), L&T Mar 2026 (121,683 + 3,814). Tata Steel: leases sit inside borrowings, nothing to add. **Fails for L&T Sep 2026**: the file has no lease member (gap 4,073). |
| B2 | **Total = Assets - min(DeferredTaxAssetsNet, DeferredTaxLiabilitiesNet) in the March column** (screener nets the smaller of the two against both sides): TCS 182,372 - 1,205 = 181,167. **In the Sep 2026 column no netting**: TCS 190,782 and L&T 484,727 equal `Assets`. | All 5 in March (to the rupee crore); TCS and L&T in September. Why the half-year column differs is not known (assumption: the March column is built from the annual statement, the half-year column from the results file). |
| B3 | **Fixed Assets = PropertyPlantAndEquipment + InvestmentProperty + Goodwill + OtherIntangibleAssets + right-of-use assets.** The right-of-use assets are the member "Right-of-use assets" of `OtherNoncurrentAssets` where tagged (ITC: 501 Cr; the others carry them inside PPE). | All 5 in March; TCS in Sep 2026. Fails for L&T Sep 2026 (see gap list). |
| B4 | **CWIP = CapitalWorkInProgress + IntangibleAssetsUnderDevelopment.** | All 5 in March; TCS in Sep 2026. L&T Sep 2026 differs (see gap list). |
| B5 | **Investments = InvestmentsAccountedForUsingEquityMethod + NoncurrentInvestments + CurrentInvestments.** | All 5. |
| B6 | **Other Assets = Total - Fixed Assets - CWIP - Investments. Other Liabilities = Total - Equity Capital - Reserves - Borrowings** (so the minority share, payables, provisions and the un-netted deferred tax sit here). | All 5. |

### Cash flow (FY26, from the 12-month context of the Q4FY26 file)

| Id | Rule | Holds for |
|---|---|---|
| | Operating = CashFlowsFromUsedInOperatingActivities. Financing = CashFlowsFromUsedInFinancingActivities. Net = IncreaseDecreaseInCashAndCashEquivalents (after the exchange-rate effect). | All 5, exact. |
| C1 | **Investing = CashFlowsFromUsedInInvestingActivities + EffectOfExchangeRateChangesOnCashAndCashEquivalents.** Screener has no foreign-exchange line, so it adds it to Investing: TCS -12,845 + 959 = -11,886 (screener -11,886). | TCS, Sun, L&T, Tata Steel; ITC has no such effect. |

Half-year balance sheets: screener's balance-sheet table shows **March columns plus only the latest half year**: TCS and L&T show "Sep 2026"; Sun Pharma, Tata Steel and ITC show none (their Sep 2026 results are not filed; NSE lists none for them on 28 Oct 2026). Sep 2025 is not shown for anyone, so the Q2FY26 balance sheets are checked against memory only (all equal).

Section ids on screener's page: `quarters`, `profit-loss`, `balance-sheet`, **`cash-flow`** (not `cash-flows`), then `ratios`, `shareholding`.

## 5. Gaps no rule explains, and the likely cause

| # | Pair | Screener | XBRL by the rules | Evidence | Likely cause |
|---|---|---:|---:|---|---|
| 1 | Sun FY26 Expenses / Operating Profit / OPM % / Other Income | 41,961 / 16,501 / 28% / 1,895 | 40,731 / 17,731 / 30.3% / 664 | Screener's FY26 column is not the sum of its own four quarters: Expenses +1,230, Operating Profit -1,230, Other Income +1,232. PBT 15,119 and Net Profit 11,509 are equal in both. The year's exceptional items are -1,307. | Screener's annual column comes from the **annual report**, where the exceptional items sit inside expenses by nature (about 1,230) and inside other income (about 77), not in Other Income as in the quarterly rule P3. Not a restatement of profit. To confirm: the annual report's note on exceptional items. |
| 2 | L&T FY26 Expenses / Operating Profit / Other Income / Interest | 249,530 / 36,345 / 4,052 / 10,056 | 249,728 / 36,146 / 4,038 / 9,844 | Annual against sum of its four quarters: Interest +211, Expenses -197, Operating Profit +199, Other Income +14. PBT 25,976 and Net Profit 18,954 equal. | Same: **annual report classification**: about 211 Cr more finance cost taken out of expenses than the quarterly files do (the finance cost of the financial-services business is larger in the annual statement). |
| 3 | ITC FY26 Expenses / Operating Profit / Other Income | 51,562 / 27,306 / 2,523 | 51,550 / 27,318 / 2,511 | Annual against sum of its four quarters: Expenses +12, Operating Profit -12, Other Income +11. PBT 28,033 and Net Profit 21,018 equal. | Same: **annual report reclassification of about 12 Cr** between other income and expenses. |
| 4 | L&T Sep 2026 Borrowings | 140,300 | 136,227 | The Sep 2026 file lumps lease liabilities into "Other non-current / current financial liabilities" (no "Lease liabilities" member, which the March file had: 3,814 Cr). Gap 4,073 is the same size. | **The file does not break out leases; screener has them** (from the results PDF or the notes). The gap would close if leases are 4,073 Cr. Cannot be settled from XBRL. |
| 5 | L&T Sep 2026 Other Liabilities | 231,398 | 235,471 | Follows gap 4 to the rupee crore (231,398 = 484,727 - 275 - 112,754 - 140,300). | Same as 4. |
| 6 | L&T Sep 2026 Fixed Assets / CWIP | 31,984 / 3,150 | 31,206 / 3,928 | Their sum is the same (35,134 against 35,134). 778 Cr moved from CWIP to Fixed Assets. | **Screener splits the two differently**: perhaps right-of-use or completed assets that the file keeps in capital work in progress. Not settled. |

Nothing in the 15 gaps is a case of our memory being wrong while the XBRL is right, or of screener being wrong: in each the XBRL element is a different line from the one screener prints, or screener's number comes from a document we did not read (annual report; results PDF). The tests that would settle gaps 1 to 3 and 6 are in section 6.

## 6. Screener's hidden breakdown rows (owner's tip)

The "+" beside Sales, Expenses, Other Income, Net Profit (quarters and profit-loss), Borrowings, Other Liabilities, Fixed Assets, Other Assets (balance-sheet) and Cash from Operating / Investing / Financing (cash-flow) is **not in the page HTML**. The saved pages have no hidden `tr` rows. The "+" button is `Company.showSchedule('<Row>', '<section>', this)` (screener's `company.customisation` script), which loads the rows on click from:

`GET /api/company/<companyId>/schedules/?parent=<Row name>&section=<quarters|profit-loss|balance-sheet|cash-flow>` plus an empty `consolidated=` flag on the consolidated page (path taken from screener's static `utils` and `company.customisation` scripts, which I read; the endpoint itself was **not fetched**, and no `/company/source/` page was opened).

Company ids on the saved pages: TCS 3365, SUNPHARMA 3245, LT 1870, TATASTEEL 3373, ITC 1552.

What those sub-rows would settle if the lead decides to fetch them: the Other Income sub-rows ("Exceptional items", "Other income normal") per company would show whether associates are in "normal" for ITC and Tata Steel and not for L&T and Sun (rule P4); the annual Expenses/Other Income rows would show the annual-report split (gaps 1 to 3); Borrowings and Fixed Assets would show the lease and CWIP split (gaps 4 to 6).

## 7. Does screener read PDFs or XBRL?

Two more screener pages fetched, same pacing (IMPAL's default page, which is the standalone one (the page carries no consolidated flag); STYRENIX consolidated). Screener's Jun 2026 (Q1FY27) quarter:

| Company | Sales | Net Profit | EPS | Pages | Our memory (Q1FY27) |
|---|---:|---:|---:|---|---|
| IMPAL (standalone) | **234** | **22** | **17.39** | `/company/IMPAL/` | revenue 234.29, profit 21.70, EPS 17.38 (basis STANDALONE) |
| STYRENIX (consolidated) | 1,011 | 138 | 78.64 | `/company/STYRENIX/consolidated/` | revenue 1,010.86, profit 138.30, EPS 78.64 |

IMPAL: NSE's XBRL tags every amount at 1/100 (revenue 2.34, profit 0.22, EPS 17.38 right, as the lead found). **Screener shows 234 and 22, not 2.34 and 0.22, so it does not take the XBRL as filed**: it corrects the figure, so it reads the PDF (or a vendor or a person fixes it). Its EPS 17.39 against the file's 17.38 shows that it works out EPS itself from its own profit and share count rather than copying the file. Consistent with this, from the five-company work: screener's FY26 annual column differs from its own quarters in the way an annual report would (section 5), and for L&T's Sep 2026 balance sheet screener has leases that the file does not tag. So screener's figures come from the printed documents (or a person or vendor correcting them), with the XBRL at most one input. One page is a small sample; the hidden-row endpoint (section 6) would show the split.

STYRENIX: screener's Sales, Net Profit and EPS agree with our memory to the rounding screener prints (1,011 / 138 / 78.64). I did not download Styrenix's XBRL, so this section does not say whether its file is clean.

## 8. How the work was done

- **NSE downloads:** 54 XBRL files (TCS 12, Sun Pharma 10, L&T 12, Tata Steel 10, ITC 10; consolidated and standalone for each quarter end 30 Jun 2025 to 30 Sep 2026 that NSE lists), 5 listing calls (`integrated_filings`), 59 calls in all, through the pipeline's own `NseClient` with its own pacing, one at a time. Time: TCS 52 s, the other four 202 s. **No refusal of any kind** (no 403, 429 or challenge page). Sun Pharma, Tata Steel and ITC have no Sep 2026 file listed on 28 Oct 2026 (not found by `integrated_filings` on that date), so they have 5 quarters, not 6.
- Revised filing noted: L&T Q4FY26 standalone is a revision filed 7 May 2026; the consolidated one is the original of 5 May.
- Q1 and Q3 files carry no balance sheet and no cash flow; Q2 files carry a Sep balance sheet and half-year cash flow; Q4 files the March balance sheet and 12-month cash flow. No file carries prior-year comparatives, so figures come from each quarter's own file.
- **Screener:** 7 pages, 5 s apart, plain browser User-Agent, all HTTP 200 (TCS, SUNPHARMA, LT, TATASTEEL, ITC consolidated; IMPAL, STYRENIX), plus 2 static script files from screener's CDN to find the hidden-row path.
- **Memory:** `GET /api/companies/<SYMBOL>` for the 5 companies and for IMPAL, STYRENIX (read only).
- Files and scripts: `scratchpad/five/files/` (54 XBRL files), `scratchpad/five/screener/` (pages and parsed tables), `scratchpad/five/scripts/` (`xl.py` reader, `master.py` and `run_*.py` comparisons), `scratchpad/five/{pl,bs,cf}_rows.json` (every pair), `scratchpad/five/mem_check.json` (memory against XBRL).
- Verdicts: `exact` = the plain XBRL element within 1 Cr of screener's whole-crore figure (percent rows within 0.51 point, EPS within 0.015); `explained` = closes within 1.5 Cr only with a named rule; `UNEXPLAINED` = neither. "XBRL" in the tables is the value by screener's formula; "Memory" is the memory field in section 3's table (it is a different definition on several rows, so unequal is not an error; section 2 holds the real comparison).

## 9. Totals

| Statement | Pairs | Exact | Explained | Unexplained |
|---|---:|---:|---:|---:|
| Quarterly profit and loss (27 company-quarters x 11 rows) | 297 | 209 | 88 | 0 |
| FY26 profit and loss (5 companies x 11 rows) | 55 | 33 | 11 | 11 |
| Balance sheet (7 company-columns x 10 rows) | 70 | 24 | 42 | 4 |
| Cash flow FY26 (5 companies x 4 rows) | 20 | 16 | 4 | 0 |
| **All** | **442** | **282 (63.8%)** | **145 (32.8%)** | **15 (3.4%)** |

By company (exact / explained / unexplained): TCS 79 / 22 / 0; Sun Pharma 57 / 19 / 4; L&T 55 / 38 / 8; Tata Steel 50 / 30 / 0; ITC 41 / 36 / 3.

What the "explained" share is made of: Expenses (29 of 32 always need rule P5, by definition), Other Income (20: exceptional items), Operating Profit and OPM (19: excise, L&T's finance cost), PBT and Tax % (16: associates), balance sheet (42: leases, deferred-tax netting, goodwill and intangibles, equity-method investments), cash-flow Investing (4: exchange effect).

## 10. Every row and period

Columns: Screener = the figure on screener's page; XBRL = our rebuild from the NSE file by the rules above (whole crore except %, EPS); Memory = the matching memory field (section 3 says which; `-` = no such field). Rule ids refer to section 4 (B0 to B6 balance sheet, C1 cash flow). Quarter labels are our fiscal quarters: Q1FY26 = Jun 2025, Q2FY26 = Sep 2025, Q3FY26 = Dec 2025, Q4FY26 = Mar 2026, Q1FY27 = Jun 2026, Q2FY27 = Sep 2026. The FY26 annual figures are shown with the period label FY26. Balance-sheet period Q4FY26 = Mar 2026, Q2FY27 = Sep 2026.


### TCS

**TCS: quarterly table (screener `quarters`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| Q1FY26 | Sales | 63,437.0 | 63,437.0 | 63,437.0 | exact |  |
| Q1FY26 | Expenses | 46,562.0 | 46,562.0 | 48,118.0 | explained | Expenses - FinanceCosts - D&A |
| Q1FY26 | Operating Profit | 16,875.0 | 16,875.0 | 16,875.0 | exact |  |
| Q1FY26 | OPM % | 27.0 | 26.6 | 26.6 | exact |  |
| Q1FY26 | Other Income | 1,660.0 | 1,660.0 | 1,660.0 | exact |  |
| Q1FY26 | Interest | 195.0 | 195.0 | 195.0 | exact |  |
| Q1FY26 | Depreciation | 1,361.0 | 1,361.0 | 1,361.0 | exact |  |
| Q1FY26 | Profit before tax | 16,979.0 | 16,979.0 | 16,979.0 | exact |  |
| Q1FY26 | Tax % | 24.0 | 24.5 | 24.5 | exact |  |
| Q1FY26 | Net Profit | 12,819.0 | 12,819.0 | 12,819.0 | exact |  |
| Q1FY26 | EPS in Rs | 35.27 | 35.27 | 35.27 | exact |  |
| Q2FY26 | Sales | 65,799.0 | 65,799.0 | 65,799.0 | exact |  |
| Q2FY26 | Expenses | 47,821.0 | 47,821.0 | 49,463.0 | explained | Expenses - FinanceCosts - D&A |
| Q2FY26 | Operating Profit | 17,978.0 | 17,978.0 | 17,978.0 | exact |  |
| Q2FY26 | OPM % | 27.0 | 27.3 | 27.3 | exact |  |
| Q2FY26 | Other Income | -268.0 | -268.0 | 867.0 | explained | OtherIncome; + ExceptionalItemsBeforeTax |
| Q2FY26 | Interest | 229.0 | 229.0 | 229.0 | exact |  |
| Q2FY26 | Depreciation | 1,413.0 | 1,413.0 | 1,413.0 | exact |  |
| Q2FY26 | Profit before tax | 16,068.0 | 16,068.0 | 16,068.0 | exact |  |
| Q2FY26 | Tax % | 24.0 | 24.5 | 24.5 | exact |  |
| Q2FY26 | Net Profit | 12,131.0 | 12,131.0 | 12,131.0 | exact |  |
| Q2FY26 | EPS in Rs | 33.37 | 33.37 | 33.37 | exact |  |
| Q3FY26 | Sales | 67,087.0 | 67,087.0 | 67,087.0 | exact |  |
| Q3FY26 | Expenses | 48,818.0 | 48,818.0 | 50,736.0 | explained | Expenses - FinanceCosts - D&A |
| Q3FY26 | Operating Profit | 18,269.0 | 18,269.0 | 18,269.0 | exact |  |
| Q3FY26 | OPM % | 27.0 | 27.2 | 27.2 | exact |  |
| Q3FY26 | Other Income | -2,273.0 | -2,273.0 | 1,118.0 | explained | OtherIncome; + ExceptionalItemsBeforeTax |
| Q3FY26 | Interest | 538.0 | 538.0 | 538.0 | exact |  |
| Q3FY26 | Depreciation | 1,380.0 | 1,380.0 | 1,380.0 | exact |  |
| Q3FY26 | Profit before tax | 14,078.0 | 14,078.0 | 14,078.0 | exact |  |
| Q3FY26 | Tax % | 24.0 | 23.9 | 23.9 | exact |  |
| Q3FY26 | Net Profit | 10,720.0 | 10,720.0 | 10,720.0 | exact |  |
| Q3FY26 | EPS in Rs | 29.45 | 29.45 | 29.45 | exact |  |
| Q4FY26 | Sales | 70,698.0 | 70,698.0 | 70,698.0 | exact |  |
| Q4FY26 | Expenses | 51,422.0 | 51,422.0 | 53,093.0 | explained | Expenses - FinanceCosts - D&A |
| Q4FY26 | Operating Profit | 19,276.0 | 19,276.0 | 19,276.0 | exact |  |
| Q4FY26 | OPM % | 27.0 | 27.3 | 27.3 | exact |  |
| Q4FY26 | Other Income | 757.0 | 757.0 | 757.0 | exact |  |
| Q4FY26 | Interest | 265.0 | 265.0 | 265.0 | exact |  |
| Q4FY26 | Depreciation | 1,406.0 | 1,406.0 | 1,406.0 | exact |  |
| Q4FY26 | Profit before tax | 18,362.0 | 18,362.0 | 18,362.0 | exact |  |
| Q4FY26 | Tax % | 25.0 | 24.9 | 24.9 | exact |  |
| Q4FY26 | Net Profit | 13,784.0 | 13,784.0 | 13,784.0 | exact |  |
| Q4FY26 | EPS in Rs | 37.92 | 37.92 | 37.92 | exact |  |
| Q1FY27 | Sales | 72,275.0 | 72,275.0 | 72,275.0 | exact |  |
| Q1FY27 | Expenses | 53,719.0 | 53,719.0 | 55,231.0 | explained | Expenses - FinanceCosts - D&A |
| Q1FY27 | Operating Profit | 18,556.0 | 18,556.0 | 18,556.0 | exact |  |
| Q1FY27 | OPM % | 26.0 | 25.7 | 25.7 | exact |  |
| Q1FY27 | Other Income | 900.0 | 900.0 | 1,568.0 | explained | OtherIncome; + ExceptionalItemsBeforeTax |
| Q1FY27 | Interest | 273.0 | 273.0 | 273.0 | exact |  |
| Q1FY27 | Depreciation | 1,239.0 | 1,239.0 | 1,239.0 | exact |  |
| Q1FY27 | Profit before tax | 17,944.0 | 17,944.0 | 17,944.0 | exact |  |
| Q1FY27 | Tax % | 25.0 | 25.2 | 25.2 | exact |  |
| Q1FY27 | Net Profit | 13,420.0 | 13,420.0 | 13,420.0 | exact |  |
| Q1FY27 | EPS in Rs | 36.90 | 36.90 | 36.90 | exact |  |
| Q2FY27 | Sales | 73,188.0 | 73,188.0 | 73,188.0 | exact |  |
| Q2FY27 | Expenses | 54,373.0 | 54,373.0 | 55,887.0 | explained | Expenses - FinanceCosts - D&A |
| Q2FY27 | Operating Profit | 18,815.0 | 18,815.0 | 18,815.0 | exact |  |
| Q2FY27 | OPM % | 26.0 | 25.7 | 25.7 | exact |  |
| Q2FY27 | Other Income | 1,337.0 | 1,337.0 | 1,337.0 | exact |  |
| Q2FY27 | Interest | 252.0 | 252.0 | 252.0 | exact |  |
| Q2FY27 | Depreciation | 1,262.0 | 1,262.0 | 1,262.0 | exact |  |
| Q2FY27 | Profit before tax | 18,638.0 | 18,638.0 | 18,638.0 | exact |  |
| Q2FY27 | Tax % | 25.0 | 25.2 | 25.2 | exact |  |
| Q2FY27 | Net Profit | 13,934.0 | 13,934.0 | 13,934.0 | exact |  |
| Q2FY27 | EPS in Rs | 38.37 | 38.37 | 38.37 | exact |  |

**TCS: annual profit and loss, FY26 (screener `profit-loss`, Mar 2026)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| FY26 | Sales | 267,021.0 | 267,021.0 | 267,021.0 | exact |  |
| FY26 | Expenses | 194,623.0 | 194,623.0 | 201,410.0 | explained | Expenses - FinanceCosts - D&A |
| FY26 | Operating Profit | 72,398.0 | 72,398.0 | 72,398.0 | exact |  |
| FY26 | OPM % | 27.0 | 27.1 | 27.1 | exact |  |
| FY26 | Other Income | -124.0 | -124.0 | 4,402.0 | explained | OtherIncome; + ExceptionalItemsBeforeTax |
| FY26 | Interest | 1,227.0 | 1,227.0 | 1,227.0 | exact |  |
| FY26 | Depreciation | 5,560.0 | 5,560.0 | 5,560.0 | exact |  |
| FY26 | Profit before tax | 65,487.0 | 65,487.0 | 65,487.0 | exact |  |
| FY26 | Tax % | 24.0 | 24.5 | 24.5 | exact |  |
| FY26 | Net Profit | 49,454.0 | 49,454.0 | 49,454.0 | exact |  |
| FY26 | EPS in Rs | 136.01 | 136.01 | 136.01 | exact |  |

**TCS: balance sheet (screener `balance-sheet`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| Q4FY26 | Equity Capital | 362.0 | 362.0 | 362.0 | exact |  |
| Q4FY26 | Reserves | 106,878.0 | 106,878.0 | 106,878.0 | exact |  |
| Q4FY26 | Borrowings | 11,283.0 | 11,283.0 | 0.0 | explained | B1 |
| Q4FY26 | Other Liabilities | 62,644.0 | 62,644.0 | - | explained | B6 |
| Q4FY26 | Total Liabilities | 181,167.0 | 181,167.0 | 182,372.0 | explained | B2 |
| Q4FY26 | Fixed Assets | 31,343.0 | 31,343.0 | 11,032.0 | explained | B3 |
| Q4FY26 | CWIP | 2,665.0 | 2,665.0 | 2,665.0 | exact |  |
| Q4FY26 | Investments | 33,988.0 | 33,988.0 | 33,988.0 | exact |  |
| Q4FY26 | Other Assets | 113,171.0 | 113,171.0 | - | explained | B6 |
| Q4FY26 | Total Assets | 181,167.0 | 181,167.0 | 182,372.0 | explained | B2 |
| Q2FY27 | Equity Capital | 362.0 | 362.0 | 362.0 | exact |  |
| Q2FY27 | Reserves | 118,624.0 | 118,624.0 | 118,624.0 | exact |  |
| Q2FY27 | Borrowings | 11,808.0 | 11,808.0 | 0.0 | explained | B1 |
| Q2FY27 | Other Liabilities | 59,988.0 | 59,988.0 | - | explained | B6 |
| Q2FY27 | Total Liabilities | 190,782.0 | 190,782.0 | 190,782.0 | exact |  |
| Q2FY27 | Fixed Assets | 32,872.0 | 32,872.0 | 11,893.0 | explained | B3 |
| Q2FY27 | CWIP | 2,380.0 | 2,380.0 | 2,380.0 | exact |  |
| Q2FY27 | Investments | 40,840.0 | 40,840.0 | 40,840.0 | exact |  |
| Q2FY27 | Other Assets | 114,690.0 | 114,690.0 | - | explained | B6 |
| Q2FY27 | Total Assets | 190,782.0 | 190,782.0 | 190,782.0 | exact |  |

**TCS: cash flow FY26 (screener `cash-flow`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| FY26 | Cash from Operating Activity | 52,094.0 | 52,094.0 | 52,094.0 | exact |  |
| FY26 | Cash from Investing Activity | -11,886.0 | -11,886.0 | -12,845.0 | explained | C1 |
| FY26 | Cash from Financing Activity | -42,133.0 | -42,133.0 | -42,133.0 | exact |  |
| FY26 | Net Cash Flow | -1,925.0 | -1,925.0 | -1,925.0 | exact |  |

### SUNPHARMA

**SUNPHARMA: quarterly table (screener `quarters`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| Q1FY26 | Sales | 13,851.0 | 13,851.4 | 13,851.4 | exact |  |
| Q1FY26 | Expenses | 9,550.0 | 9,549.7 | 10,325.1 | explained | Expenses - FinanceCosts - D&A |
| Q1FY26 | Operating Profit | 4,302.0 | 4,301.7 | 4,301.7 | exact |  |
| Q1FY26 | OPM % | 31.0 | 31.1 | 31.1 | exact |  |
| Q1FY26 | Other Income | -354.0 | -353.5 | 464.5 | explained | OtherIncome; + ExceptionalItemsBeforeTax |
| Q1FY26 | Interest | 75.0 | 74.8 | 74.8 | exact |  |
| Q1FY26 | Depreciation | 701.0 | 700.5 | 700.5 | exact |  |
| Q1FY26 | Profit before tax | 3,173.0 | 3,172.8 | 3,172.8 | exact |  |
| Q1FY26 | Tax % | 27.0 | 27.4 | 27.4 | exact |  |
| Q1FY26 | Net Profit | 2,293.0 | 2,292.9 | 2,292.9 | exact |  |
| Q1FY26 | EPS in Rs | 9.50 | 9.50 | 9.50 | exact |  |
| Q2FY26 | Sales | 14,478.0 | 14,478.3 | 14,478.3 | exact |  |
| Q2FY26 | Expenses | 9,951.0 | 9,951.3 | 10,780.6 | explained | Expenses - FinanceCosts - D&A |
| Q2FY26 | Operating Profit | 4,527.0 | 4,527.0 | 4,527.1 | exact |  |
| Q2FY26 | OPM % | 31.0 | 31.3 | 31.3 | exact |  |
| Q2FY26 | Other Income | 470.0 | 469.9 | 469.9 | exact |  |
| Q2FY26 | Interest | 100.0 | 99.9 | 99.9 | exact |  |
| Q2FY26 | Depreciation | 730.0 | 729.5 | 729.5 | exact |  |
| Q2FY26 | Profit before tax | 4,168.0 | 4,167.6 | 4,167.6 | exact |  |
| Q2FY26 | Tax % | 25.0 | 24.7 | 24.7 | exact |  |
| Q2FY26 | Net Profit | 3,125.0 | 3,124.9 | 3,124.9 | exact |  |
| Q2FY26 | EPS in Rs | 13.00 | 13.00 | 13.00 | exact |  |
| Q3FY26 | Sales | 15,521.0 | 15,520.5 | 15,520.5 | exact |  |
| Q3FY26 | Expenses | 10,572.0 | 10,572.0 | 11,382.7 | explained | Expenses - FinanceCosts - D&A |
| Q3FY26 | Operating Profit | 4,948.0 | 4,948.5 | 4,948.5 | exact |  |
| Q3FY26 | OPM % | 32.0 | 31.9 | 31.9 | exact |  |
| Q3FY26 | Other Income | 89.0 | 89.4 | 578.8 | explained | OtherIncome; + ExceptionalItemsBeforeTax |
| Q3FY26 | Interest | 78.0 | 78.4 | 78.4 | exact |  |
| Q3FY26 | Depreciation | 732.0 | 732.3 | 732.3 | exact |  |
| Q3FY26 | Profit before tax | 4,227.0 | 4,227.2 | 4,227.2 | exact |  |
| Q3FY26 | Tax % | 20.0 | 19.5 | 19.5 | exact |  |
| Q3FY26 | Net Profit | 3,381.0 | 3,381.2 | 3,381.2 | exact |  |
| Q3FY26 | EPS in Rs | 14.04 | 14.00 | 14.00 | explained | XBRL EPS tagged to 0 decimal(s); screener works from its own profit / shares |
| Q4FY26 | Sales | 14,612.0 | 14,611.8 | 14,611.8 | exact |  |
| Q4FY26 | Expenses | 10,658.0 | 10,657.6 | 11,519.0 | explained | Expenses - FinanceCosts - D&A |
| Q4FY26 | Operating Profit | 3,954.0 | 3,954.2 | 3,954.2 | exact |  |
| Q4FY26 | OPM % | 27.0 | 27.1 | 27.1 | exact |  |
| Q4FY26 | Other Income | 458.0 | 458.5 | 458.5 | exact |  |
| Q4FY26 | Interest | 86.0 | 85.9 | 85.9 | exact |  |
| Q4FY26 | Depreciation | 775.0 | 775.5 | 775.5 | exact |  |
| Q4FY26 | Profit before tax | 3,551.0 | 3,551.3 | 3,551.3 | exact |  |
| Q4FY26 | Tax % | 23.0 | 23.3 | 23.3 | exact |  |
| Q4FY26 | Net Profit | 2,710.0 | 2,709.7 | 2,709.7 | exact |  |
| Q4FY26 | EPS in Rs | 11.31 | 11.30 | 11.30 | exact |  |
| Q1FY27 | Sales | 15,300.0 | 15,299.9 | 15,299.9 | exact |  |
| Q1FY27 | Expenses | 10,882.0 | 10,882.2 | 11,720.6 | explained | Expenses - FinanceCosts - D&A |
| Q1FY27 | Operating Profit | 4,418.0 | 4,417.7 | 4,417.7 | exact |  |
| Q1FY27 | OPM % | 29.0 | 28.9 | 28.9 | exact |  |
| Q1FY27 | Other Income | 520.0 | 519.5 | 723.6 | explained | OtherIncome; + ExceptionalItemsBeforeTax |
| Q1FY27 | Interest | 100.0 | 99.7 | 99.7 | exact |  |
| Q1FY27 | Depreciation | 739.0 | 738.7 | 738.7 | exact |  |
| Q1FY27 | Profit before tax | 4,099.0 | 4,098.8 | 4,098.8 | exact |  |
| Q1FY27 | Tax % | 29.0 | 29.0 | 29.0 | exact |  |
| Q1FY27 | Net Profit | 2,901.0 | 2,901.2 | 2,901.2 | exact |  |
| Q1FY27 | EPS in Rs | 12.06 | 12.10 | 12.10 | explained | XBRL EPS tagged to 1 decimal(s); screener works from its own profit / shares |

**SUNPHARMA: annual profit and loss, FY26 (screener `profit-loss`, Mar 2026)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| FY26 | Sales | 58,462.0 | 58,462.0 | 58,462.0 | exact |  |
| FY26 | Expenses | 41,961.0 | 40,730.6 | 44,007.4 | UNEXPLAINED | see gap list |
| FY26 | Operating Profit | 16,501.0 | 17,731.4 | 17,731.4 | UNEXPLAINED | see gap list |
| FY26 | OPM % | 28.0 | 30.3 | 30.3 | UNEXPLAINED | see gap list |
| FY26 | Other Income | 1,895.0 | 664.2 | 1,971.7 | UNEXPLAINED | see gap list |
| FY26 | Interest | 339.0 | 338.9 | 338.9 | exact |  |
| FY26 | Depreciation | 2,938.0 | 2,937.8 | 2,937.8 | exact |  |
| FY26 | Profit before tax | 15,119.0 | 15,118.9 | 15,118.9 | exact |  |
| FY26 | Tax % | 24.0 | 23.5 | 23.5 | exact |  |
| FY26 | Net Profit | 11,509.0 | 11,508.6 | 11,508.6 | exact |  |
| FY26 | EPS in Rs | 47.84 | 47.80 | 47.80 | explained | XBRL EPS tagged to 1 decimal(s); screener works from its own profit / shares |

**SUNPHARMA: balance sheet (screener `balance-sheet`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| Q4FY26 | Equity Capital | 240.0 | 239.9 | 239.9 | exact |  |
| Q4FY26 | Reserves | 83,330.0 | 83,330.2 | 83,330.2 | exact |  |
| Q4FY26 | Borrowings | 4,627.0 | 4,627.3 | 4,081.6 | explained | B1 |
| Q4FY26 | Other Liabilities | 20,210.0 | 20,209.8 | - | explained | B6 |
| Q4FY26 | Total Liabilities | 108,407.0 | 108,407.2 | 108,785.2 | explained | B2 |
| Q4FY26 | Fixed Assets | 32,822.0 | 32,822.3 | 11,114.1 | explained | B3 |
| Q4FY26 | CWIP | 3,052.0 | 3,051.7 | 1,380.7 | explained | B4 |
| Q4FY26 | Investments | 24,723.0 | 24,722.5 | 24,722.5 | exact |  |
| Q4FY26 | Other Assets | 47,811.0 | 47,810.7 | - | explained | B6 |
| Q4FY26 | Total Assets | 108,407.0 | 108,407.2 | 108,785.2 | explained | B2 |

**SUNPHARMA: cash flow FY26 (screener `cash-flow`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| FY26 | Cash from Operating Activity | 12,419.0 | 12,419.2 | 12,419.2 | exact |  |
| FY26 | Cash from Investing Activity | -10,405.0 | -10,404.9 | -11,344.0 | explained | C1 |
| FY26 | Cash from Financing Activity | -2,513.0 | -2,512.6 | -2,512.6 | exact |  |
| FY26 | Net Cash Flow | -498.0 | -498.3 | -498.3 | exact |  |

### LT

**LT: quarterly table (screener `quarters`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| Q1FY26 | Sales | 63,679.0 | 63,678.9 | 63,678.9 | exact |  |
| Q1FY26 | Expenses | 55,655.0 | 55,654.9 | 59,176.2 | explained | Expenses - FinanceCosts - D&A |
| Q1FY26 | Operating Profit | 8,024.0 | 8,024.0 | 6,317.7 | explained | Sales - Expenses |
| Q1FY26 | OPM % | 13.0 | 12.6 | 9.9 | explained | OP / Sales |
| Q1FY26 | Other Income | 1,357.0 | 1,356.8 | 1,356.8 | exact |  |
| Q1FY26 | Interest | 2,488.0 | 2,488.0 | 781.6 | explained | element as is |
| Q1FY26 | Depreciation | 1,033.0 | 1,033.3 | 1,033.3 | exact |  |
| Q1FY26 | Profit before tax | 5,860.0 | 5,859.5 | 5,859.5 | exact |  |
| Q1FY26 | Tax % | 26.0 | 26.2 | 26.2 | exact |  |
| Q1FY26 | Net Profit | 4,318.0 | 4,318.2 | 4,318.2 | exact |  |
| Q1FY26 | EPS in Rs | 26.30 | 26.30 | 26.30 | exact |  |
| Q2FY26 | Sales | 67,984.0 | 67,983.5 | 67,983.5 | exact |  |
| Q2FY26 | Expenses | 59,470.0 | 59,470.3 | 63,031.7 | explained | Expenses - FinanceCosts - D&A |
| Q2FY26 | Operating Profit | 8,513.0 | 8,513.2 | 6,806.4 | explained | Sales - Expenses |
| Q2FY26 | OPM % | 13.0 | 12.5 | 10.0 | explained | OP / Sales |
| Q2FY26 | Other Income | 1,384.0 | 1,384.3 | 1,384.3 | exact |  |
| Q2FY26 | Interest | 2,470.0 | 2,469.6 | 762.8 | explained | element as is |
| Q2FY26 | Depreciation | 1,092.0 | 1,091.8 | 1,091.8 | exact |  |
| Q2FY26 | Profit before tax | 6,336.0 | 6,336.1 | 6,336.1 | exact |  |
| Q2FY26 | Tax % | 26.0 | 26.0 | 26.0 | exact |  |
| Q2FY26 | Net Profit | 4,678.0 | 4,678.0 | 4,678.0 | exact |  |
| Q2FY26 | EPS in Rs | 28.54 | 28.54 | 28.54 | exact |  |
| Q3FY26 | Sales | 71,450.0 | 71,449.7 | 71,449.7 | exact |  |
| Q3FY26 | Expenses | 62,259.0 | 62,259.5 | 65,729.8 | explained | Expenses - FinanceCosts - D&A |
| Q3FY26 | Operating Profit | 9,190.0 | 9,190.2 | 7,416.8 | explained | Sales - Expenses |
| Q3FY26 | OPM % | 13.0 | 12.9 | 10.4 | explained | OP / Sales |
| Q3FY26 | Other Income | -350.0 | -350.0 | 1,441.0 | explained | OtherIncome; + ExceptionalItemsBeforeTax |
| Q3FY26 | Interest | 2,399.0 | 2,398.5 | 625.1 | explained | element as is |
| Q3FY26 | Depreciation | 1,072.0 | 1,071.7 | 1,071.7 | exact |  |
| Q3FY26 | Profit before tax | 5,370.0 | 5,369.9 | 5,369.9 | exact |  |
| Q3FY26 | Tax % | 29.0 | 28.7 | 28.7 | exact |  |
| Q3FY26 | Net Profit | 3,825.0 | 3,824.7 | 3,824.7 | exact |  |
| Q3FY26 | EPS in Rs | 23.37 | 23.37 | 23.37 | exact |  |
| Q4FY26 | Sales | 82,762.0 | 82,762.2 | 82,762.2 | exact |  |
| Q4FY26 | Expenses | 72,343.0 | 72,343.1 | 75,999.1 | explained | Expenses - FinanceCosts - D&A |
| Q4FY26 | Operating Profit | 10,419.0 | 10,419.0 | 8,610.3 | explained | Sales - Expenses |
| Q4FY26 | OPM % | 13.0 | 12.6 | 10.4 | explained | OP / Sales |
| Q4FY26 | Other Income | 1,647.0 | 1,647.2 | 1,578.6 | explained | OtherIncome; + ExceptionalItemsBeforeTax |
| Q4FY26 | Interest | 2,488.0 | 2,488.0 | 679.3 | explained | element as is |
| Q4FY26 | Depreciation | 1,168.0 | 1,168.0 | 1,168.0 | exact |  |
| Q4FY26 | Profit before tax | 8,410.0 | 8,410.3 | 8,410.3 | exact |  |
| Q4FY26 | Tax % | 25.0 | 24.9 | 24.9 | exact |  |
| Q4FY26 | Net Profit | 6,133.0 | 6,133.1 | 6,133.1 | exact |  |
| Q4FY26 | EPS in Rs | 38.71 | 38.71 | 38.71 | exact |  |
| Q1FY27 | Sales | 67,942.0 | 67,941.7 | 67,941.7 | exact |  |
| Q1FY27 | Expenses | 59,793.0 | 59,792.6 | 63,396.2 | explained | Expenses - FinanceCosts - D&A |
| Q1FY27 | Operating Profit | 8,149.0 | 8,149.1 | 6,116.5 | explained | Sales - Expenses |
| Q1FY27 | OPM % | 12.0 | 12.0 | 9.0 | explained | OP / Sales |
| Q1FY27 | Other Income | 2,377.0 | 2,376.7 | 2,376.7 | exact |  |
| Q1FY27 | Interest | 2,571.0 | 2,571.3 | 538.7 | explained | element as is |
| Q1FY27 | Depreciation | 1,032.0 | 1,032.3 | 1,032.3 | exact |  |
| Q1FY27 | Profit before tax | 6,922.0 | 6,922.3 | 6,922.3 | exact |  |
| Q1FY27 | Tax % | 28.0 | 28.0 | 28.0 | exact |  |
| Q1FY27 | Net Profit | 4,988.0 | 4,988.0 | 4,988.0 | exact |  |
| Q1FY27 | EPS in Rs | 29.97 | 29.97 | 29.97 | exact |  |
| Q2FY27 | Sales | 78,750.0 | 78,749.9 | 78,749.9 | exact |  |
| Q2FY27 | Expenses | 69,936.0 | 69,936.4 | 73,415.1 | explained | Expenses - FinanceCosts - D&A |
| Q2FY27 | Operating Profit | 8,814.0 | 8,813.5 | 6,844.6 | explained | Sales - Expenses |
| Q2FY27 | OPM % | 11.0 | 11.2 | 8.7 | explained | OP / Sales |
| Q2FY27 | Other Income | 2,306.0 | 2,306.3 | 2,306.3 | exact |  |
| Q2FY27 | Interest | 2,442.0 | 2,441.8 | 472.9 | explained | element as is |
| Q2FY27 | Depreciation | 1,037.0 | 1,036.9 | 1,036.9 | exact |  |
| Q2FY27 | Profit before tax | 7,641.0 | 7,641.1 | 7,641.1 | exact |  |
| Q2FY27 | Tax % | 23.0 | 22.6 | 22.6 | exact |  |
| Q2FY27 | Net Profit | 5,949.0 | 5,949.1 | 5,949.1 | exact |  |
| Q2FY27 | EPS in Rs | 37.81 | 37.81 | 37.81 | exact |  |

**LT: annual profit and loss, FY26 (screener `profit-loss`, Mar 2026)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| FY26 | Sales | 285,874.0 | 285,874.4 | 285,874.4 | exact |  |
| FY26 | Expenses | 249,530.0 | 249,727.9 | 263,936.8 | UNEXPLAINED | see gap list |
| FY26 | Operating Profit | 36,345.0 | 36,146.5 | 29,151.1 | UNEXPLAINED | see gap list |
| FY26 | OPM % | 13.0 | 12.6 | 10.2 | explained | OP / Sales |
| FY26 | Other Income | 4,052.0 | 4,038.2 | 5,760.7 | UNEXPLAINED | see gap list |
| FY26 | Interest | 10,056.0 | 9,844.2 | 2,848.8 | UNEXPLAINED | see gap list |
| FY26 | Depreciation | 4,365.0 | 4,364.8 | 4,364.8 | exact |  |
| FY26 | Profit before tax | 25,976.0 | 25,975.8 | 25,975.8 | exact |  |
| FY26 | Tax % | 26.0 | 26.2 | 26.2 | exact |  |
| FY26 | Net Profit | 18,954.0 | 18,953.9 | 18,953.9 | exact |  |
| FY26 | EPS in Rs | 116.92 | 116.93 | 116.93 | exact |  |

**LT: balance sheet (screener `balance-sheet`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| Q4FY26 | Equity Capital | 275.0 | 275.1 | 275.1 | exact |  |
| Q4FY26 | Reserves | 109,015.0 | 109,014.7 | 109,014.7 | exact |  |
| Q4FY26 | Borrowings | 125,497.0 | 125,496.6 | 121,683.0 | explained | B1 |
| Q4FY26 | Other Liabilities | 217,596.0 | 217,596.4 | - | explained | B6 |
| Q4FY26 | Total Liabilities | 452,383.0 | 452,382.8 | 452,549.9 | explained | B2 |
| Q4FY26 | Fixed Assets | 30,867.0 | 30,866.9 | 19,436.8 | explained | B3 |
| Q4FY26 | CWIP | 3,311.0 | 3,310.9 | 3,036.2 | explained | B4 |
| Q4FY26 | Investments | 68,377.0 | 68,376.8 | 66,118.8 | explained | B5 |
| Q4FY26 | Other Assets | 349,828.0 | 349,828.1 | - | explained | B6 |
| Q4FY26 | Total Assets | 452,383.0 | 452,382.8 | 452,549.9 | explained | B2 |
| Q2FY27 | Equity Capital | 275.0 | 275.2 | 275.2 | exact |  |
| Q2FY27 | Reserves | 112,754.0 | 112,753.7 | 112,753.7 | exact |  |
| Q2FY27 | Borrowings | 140,300.0 | 136,227.0 | 136,227.0 | UNEXPLAINED | see gap list |
| Q2FY27 | Other Liabilities | 231,398.0 | 235,471.4 | - | UNEXPLAINED | see gap list |
| Q2FY27 | Total Liabilities | 484,727.0 | 484,727.3 | 484,727.3 | exact |  |
| Q2FY27 | Fixed Assets | 31,984.0 | 31,205.7 | 20,375.6 | UNEXPLAINED | see gap list |
| Q2FY27 | CWIP | 3,150.0 | 3,928.4 | 3,527.3 | UNEXPLAINED | see gap list |
| Q2FY27 | Investments | 82,754.0 | 82,753.5 | 80,621.6 | explained | B5 |
| Q2FY27 | Other Assets | 366,840.0 | 366,839.7 | - | explained | B6 |
| Q2FY27 | Total Assets | 484,727.0 | 484,727.3 | 484,727.3 | exact |  |

**LT: cash flow FY26 (screener `cash-flow`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| FY26 | Cash from Operating Activity | 16,741.0 | 16,741.0 | 16,741.0 | exact |  |
| FY26 | Cash from Investing Activity | -11,380.0 | -11,380.3 | -11,738.8 | explained | C1 |
| FY26 | Cash from Financing Activity | -2,156.0 | -2,156.4 | -2,156.4 | exact |  |
| FY26 | Net Cash Flow | 3,204.0 | 3,204.2 | 3,204.2 | exact |  |

### TATASTEEL

**TATASTEEL: quarterly table (screener `quarters`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| Q1FY26 | Sales | 53,178.0 | 53,178.1 | 53,178.1 | exact |  |
| Q1FY26 | Expenses | 45,751.0 | 45,750.6 | 50,347.3 | explained | Expenses - FinanceCosts - D&A |
| Q1FY26 | Operating Profit | 7,428.0 | 7,427.5 | 7,427.5 | exact |  |
| Q1FY26 | OPM % | 14.0 | 14.0 | 14.0 | exact |  |
| Q1FY26 | Other Income | 236.0 | 236.3 | 288.7 | explained | OtherIncome; + ExceptionalItemsBeforeTax; + share of associates/JVs |
| Q1FY26 | Interest | 1,852.0 | 1,852.4 | 1,852.4 | exact |  |
| Q1FY26 | Depreciation | 2,744.0 | 2,744.3 | 2,744.3 | exact |  |
| Q1FY26 | Profit before tax | 3,067.0 | 3,067.1 | 2,987.4 | explained | Sales - Expenses + OtherIncome' - Interest - D&A; + share of associates/JVs |
| Q1FY26 | Tax % | 35.0 | 35.5 | 35.5 | exact |  |
| Q1FY26 | Net Profit | 2,007.0 | 2,007.4 | 2,007.4 | exact |  |
| Q1FY26 | EPS in Rs | 1.66 | 1.67 | 1.67 | exact |  |
| Q2FY26 | Sales | 58,689.0 | 58,689.3 | 58,689.3 | exact |  |
| Q2FY26 | Expenses | 49,793.0 | 49,792.8 | 54,460.7 | explained | Expenses - FinanceCosts - D&A |
| Q2FY26 | Operating Profit | 8,897.0 | 8,896.5 | 8,896.5 | exact |  |
| Q2FY26 | OPM % | 15.0 | 15.2 | 15.2 | exact |  |
| Q2FY26 | Other Income | -6.0 | -6.1 | 363.6 | explained | OtherIncome; + ExceptionalItemsBeforeTax; + share of associates/JVs |
| Q2FY26 | Interest | 1,775.0 | 1,775.0 | 1,775.0 | exact |  |
| Q2FY26 | Depreciation | 2,893.0 | 2,893.0 | 2,893.0 | exact |  |
| Q2FY26 | Profit before tax | 4,222.0 | 4,222.5 | 4,171.7 | explained | Sales - Expenses + OtherIncome' - Interest - D&A; + share of associates/JVs |
| Q2FY26 | Tax % | 25.0 | 24.9 | 24.9 | exact |  |
| Q2FY26 | Net Profit | 3,183.0 | 3,183.1 | 3,183.1 | exact |  |
| Q2FY26 | EPS in Rs | 2.48 | 2.49 | 2.49 | exact |  |
| Q3FY26 | Sales | 57,002.0 | 57,002.4 | 57,002.4 | exact |  |
| Q3FY26 | Expenses | 48,803.0 | 48,802.7 | 53,598.8 | explained | Expenses - FinanceCosts - D&A |
| Q3FY26 | Operating Profit | 8,200.0 | 8,199.7 | 8,199.7 | exact |  |
| Q3FY26 | OPM % | 14.0 | 14.4 | 14.4 | exact |  |
| Q3FY26 | Other Income | 465.0 | 465.2 | 501.1 | explained | OtherIncome; + ExceptionalItemsBeforeTax; + share of associates/JVs |
| Q3FY26 | Interest | 1,747.0 | 1,747.3 | 1,747.3 | exact |  |
| Q3FY26 | Depreciation | 3,049.0 | 3,048.8 | 3,048.8 | exact |  |
| Q3FY26 | Profit before tax | 3,869.0 | 3,868.8 | 3,764.8 | explained | Sales - Expenses + OtherIncome' - Interest - D&A; + share of associates/JVs |
| Q3FY26 | Tax % | 29.0 | 29.4 | 30.2 | explained | TaxExpense / PBT; + share of associates/JVs |
| Q3FY26 | Net Profit | 2,730.0 | 2,730.4 | 2,730.4 | exact |  |
| Q3FY26 | EPS in Rs | 2.15 | 2.16 | 2.16 | exact |  |
| Q4FY26 | Sales | 63,270.0 | 63,270.1 | 63,270.1 | exact |  |
| Q4FY26 | Expenses | 53,441.0 | 53,441.5 | 58,502.2 | explained | Expenses - FinanceCosts - D&A |
| Q4FY26 | Operating Profit | 9,829.0 | 9,828.7 | 9,828.7 | exact |  |
| Q4FY26 | OPM % | 16.0 | 15.5 | 15.5 | exact |  |
| Q4FY26 | Other Income | 42.0 | 42.5 | 248.5 | explained | OtherIncome; + ExceptionalItemsBeforeTax; + share of associates/JVs |
| Q4FY26 | Interest | 1,792.0 | 1,792.4 | 1,792.4 | exact |  |
| Q4FY26 | Depreciation | 3,268.0 | 3,268.4 | 3,268.4 | exact |  |
| Q4FY26 | Profit before tax | 4,810.0 | 4,810.4 | 4,676.3 | explained | Sales - Expenses + OtherIncome' - Interest - D&A; + share of associates/JVs |
| Q4FY26 | Tax % | 38.0 | 38.4 | 39.5 | explained | TaxExpense / PBT; + share of associates/JVs |
| Q4FY26 | Net Profit | 2,965.0 | 2,965.0 | 2,965.0 | exact |  |
| Q4FY26 | EPS in Rs | 2.34 | 2.34 | 2.34 | exact |  |
| Q1FY27 | Sales | 60,794.0 | 60,794.3 | 60,794.3 | exact |  |
| Q1FY27 | Expenses | 51,530.0 | 51,529.9 | 56,940.1 | explained | Expenses - FinanceCosts - D&A |
| Q1FY27 | Operating Profit | 9,264.0 | 9,264.3 | 9,264.3 | exact |  |
| Q1FY27 | OPM % | 15.0 | 15.2 | 15.2 | exact |  |
| Q1FY27 | Other Income | -17.0 | -16.7 | 232.7 | explained | OtherIncome; + ExceptionalItemsBeforeTax; + share of associates/JVs |
| Q1FY27 | Interest | 1,771.0 | 1,770.5 | 1,770.5 | exact |  |
| Q1FY27 | Depreciation | 3,640.0 | 3,639.7 | 3,639.7 | exact |  |
| Q1FY27 | Profit before tax | 3,838.0 | 3,837.5 | 3,741.4 | explained | Sales - Expenses + OtherIncome' - Interest - D&A; + share of associates/JVs |
| Q1FY27 | Tax % | 38.0 | 37.8 | 38.8 | explained | TaxExpense / PBT; + share of associates/JVs |
| Q1FY27 | Net Profit | 2,385.0 | 2,385.2 | 2,385.2 | exact |  |
| Q1FY27 | EPS in Rs | 1.86 | 1.86 | 1.86 | exact |  |

**TATASTEEL: annual profit and loss, FY26 (screener `profit-loss`, Mar 2026)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| FY26 | Sales | 232,140.0 | 232,139.9 | 232,139.9 | exact |  |
| FY26 | Expenses | 197,788.0 | 197,787.5 | 216,909.1 | explained | Expenses - FinanceCosts - D&A |
| FY26 | Operating Profit | 34,352.0 | 34,352.4 | 34,352.4 | exact |  |
| FY26 | OPM % | 15.0 | 14.8 | 14.8 | exact |  |
| FY26 | Other Income | 738.0 | 737.8 | 1,401.8 | explained | OtherIncome; + ExceptionalItemsBeforeTax; + share of associates/JVs |
| FY26 | Interest | 7,167.0 | 7,167.1 | 7,167.1 | exact |  |
| FY26 | Depreciation | 11,955.0 | 11,954.5 | 11,954.5 | exact |  |
| FY26 | Profit before tax | 15,969.0 | 15,968.7 | 15,600.2 | explained | Sales - Expenses + OtherIncome' - Interest - D&A; + share of associates/JVs |
| FY26 | Tax % | 32.0 | 32.6 | 32.6 | explained | TaxExpense / PBT |
| FY26 | Net Profit | 10,886.0 | 10,885.8 | 10,885.8 | exact |  |
| FY26 | EPS in Rs | 8.65 | 8.65 | 8.65 | exact |  |

**TATASTEEL: balance sheet (screener `balance-sheet`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| Q4FY26 | Equity Capital | 1,247.0 | 1,247.4 | 1,247.4 | exact |  |
| Q4FY26 | Reserves | 100,920.0 | 100,920.2 | 100,920.2 | exact |  |
| Q4FY26 | Borrowings | 92,382.0 | 92,381.7 | 92,381.7 | exact |  |
| Q4FY26 | Other Liabilities | 101,965.0 | 101,965.3 | - | explained | B6 |
| Q4FY26 | Total Liabilities | 296,515.0 | 296,514.6 | 301,254.1 | explained | B2 |
| Q4FY26 | Fixed Assets | 179,908.0 | 179,908.1 | 159,950.9 | explained | B3 |
| Q4FY26 | CWIP | 28,497.0 | 28,496.7 | 27,510.3 | explained | B4 |
| Q4FY26 | Investments | 7,089.0 | 7,088.8 | 4,145.4 | explained | B5 |
| Q4FY26 | Other Assets | 81,021.0 | 81,020.9 | - | explained | B6 |
| Q4FY26 | Total Assets | 296,515.0 | 296,514.6 | 301,254.1 | explained | B2 |

**TATASTEEL: cash flow FY26 (screener `cash-flow`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| FY26 | Cash from Operating Activity | 35,064.0 | 35,064.5 | 35,064.5 | exact |  |
| FY26 | Cash from Investing Activity | -14,397.0 | -14,397.4 | -14,905.3 | explained | C1 |
| FY26 | Cash from Financing Activity | -21,387.0 | -21,387.1 | -21,387.1 | exact |  |
| FY26 | Net Cash Flow | -720.0 | -720.0 | -720.0 | exact |  |

### ITC

**ITC: quarterly table (screener `quarters`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| Q1FY26 | Sales | 21,495.0 | 21,494.8 | 23,129.3 | explained | - excise (OtherExpenses member "Excise Duty") |
| Q1FY26 | Expenses | 14,678.0 | 14,678.3 | 16,752.3 | explained | Expenses - FinanceCosts - D&A; - excise (OtherExpenses member "Excise Duty") |
| Q1FY26 | Operating Profit | 6,816.0 | 6,816.5 | 6,816.5 | exact |  |
| Q1FY26 | OPM % | 32.0 | 31.7 | 29.5 | explained | OP / Sales; - excise (OtherExpenses member "Excise Duty") |
| Q1FY26 | Other Income | 751.0 | 751.0 | 682.2 | explained | OtherIncome; + share of associates/JVs |
| Q1FY26 | Interest | 16.0 | 16.5 | 16.5 | exact |  |
| Q1FY26 | Depreciation | 423.0 | 423.0 | 423.0 | exact |  |
| Q1FY26 | Profit before tax | 7,128.0 | 7,128.0 | 7,059.2 | explained | Sales - Expenses + OtherIncome' - Interest - D&A; + share of associates/JVs |
| Q1FY26 | Tax % | 25.0 | 25.3 | 25.3 | exact |  |
| Q1FY26 | Net Profit | 5,343.0 | 5,343.4 | 5,343.4 | exact |  |
| Q1FY26 | EPS in Rs | 4.19 | 4.19 | 4.19 | exact |  |
| Q2FY26 | Sales | 19,502.0 | 19,501.6 | 21,255.9 | explained | - excise (OtherExpenses member "Excise Duty") |
| Q2FY26 | Expenses | 12,807.0 | 12,806.9 | 15,016.0 | explained | Expenses - FinanceCosts - D&A; - excise (OtherExpenses member "Excise Duty") |
| Q2FY26 | Operating Profit | 6,695.0 | 6,694.7 | 6,694.7 | exact |  |
| Q2FY26 | OPM % | 34.0 | 34.3 | 31.5 | explained | OP / Sales; - excise (OtherExpenses member "Excise Duty") |
| Q2FY26 | Other Income | 739.0 | 738.8 | 584.4 | explained | OtherIncome; + ExceptionalItemsBeforeTax; + share of associates/JVs |
| Q2FY26 | Interest | 20.0 | 20.1 | 20.1 | exact |  |
| Q2FY26 | Depreciation | 435.0 | 434.8 | 434.8 | exact |  |
| Q2FY26 | Profit before tax | 6,979.0 | 6,978.7 | 6,912.3 | explained | Sales - Expenses + OtherIncome' - Interest - D&A; + share of associates/JVs |
| Q2FY26 | Tax % | 26.0 | 25.9 | 25.9 | exact |  |
| Q2FY26 | Net Profit | 5,187.0 | 5,186.6 | 5,186.6 | exact |  |
| Q2FY26 | EPS in Rs | 4.09 | 4.09 | 4.09 | exact |  |
| Q3FY26 | Sales | 20,047.0 | 20,047.3 | 21,706.6 | explained | - excise (OtherExpenses member "Excise Duty") |
| Q3FY26 | Expenses | 13,165.0 | 13,164.8 | 15,274.4 | explained | Expenses - FinanceCosts - D&A; - excise (OtherExpenses member "Excise Duty") |
| Q3FY26 | Operating Profit | 6,883.0 | 6,882.5 | 6,882.5 | exact |  |
| Q3FY26 | OPM % | 34.0 | 34.3 | 31.7 | explained | OP / Sales; - excise (OtherExpenses member "Excise Duty") |
| Q3FY26 | Other Income | 322.0 | 321.8 | 574.0 | explained | OtherIncome; + ExceptionalItemsBeforeTax; + share of associates/JVs |
| Q3FY26 | Interest | 19.0 | 19.5 | 19.5 | exact |  |
| Q3FY26 | Depreciation | 431.0 | 430.8 | 430.8 | exact |  |
| Q3FY26 | Profit before tax | 6,754.0 | 6,754.1 | 6,651.7 | explained | Sales - Expenses + OtherIncome' - Interest - D&A; + share of associates/JVs |
| Q3FY26 | Tax % | 26.0 | 26.1 | 26.1 | exact |  |
| Q3FY26 | Net Profit | 5,018.0 | 5,018.4 | 5,018.4 | exact |  |
| Q3FY26 | EPS in Rs | 3.94 | 3.94 | 3.94 | exact |  |
| Q4FY26 | Sales | 17,825.0 | 17,824.7 | 23,821.5 | explained | - excise (OtherExpenses member "Excise Duty") |
| Q4FY26 | Expenses | 10,900.0 | 10,900.5 | 17,348.4 | explained | Expenses - FinanceCosts - D&A; - excise (OtherExpenses member "Excise Duty") |
| Q4FY26 | Operating Profit | 6,924.0 | 6,924.2 | 6,924.2 | exact |  |
| Q4FY26 | OPM % | 39.0 | 38.8 | 29.1 | explained | OP / Sales; - excise (OtherExpenses member "Excise Duty") |
| Q4FY26 | Other Income | 700.0 | 699.5 | 585.1 | explained | OtherIncome; + ExceptionalItemsBeforeTax; + share of associates/JVs |
| Q4FY26 | Interest | 29.0 | 29.2 | 29.2 | exact |  |
| Q4FY26 | Depreciation | 422.0 | 421.9 | 421.9 | exact |  |
| Q4FY26 | Profit before tax | 7,173.0 | 7,172.6 | 7,033.1 | explained | Sales - Expenses + OtherIncome' - Interest - D&A; + share of associates/JVs |
| Q4FY26 | Tax % | 24.0 | 24.2 | 24.2 | exact |  |
| Q4FY26 | Net Profit | 5,470.0 | 5,469.7 | 5,469.7 | exact |  |
| Q4FY26 | EPS in Rs | 4.30 | 4.30 | 4.30 | exact |  |
| Q1FY27 | Sales | 19,114.0 | 19,114.4 | 29,523.3 | explained | - excise (OtherExpenses member "Excise Duty") |
| Q1FY27 | Expenses | 13,934.0 | 13,933.5 | 24,810.0 | explained | Expenses - FinanceCosts - D&A; - excise (OtherExpenses member "Excise Duty") |
| Q1FY27 | Operating Profit | 5,181.0 | 5,180.9 | 5,180.9 | exact |  |
| Q1FY27 | OPM % | 27.0 | 27.1 | 17.6 | explained | OP / Sales; - excise (OtherExpenses member "Excise Duty") |
| Q1FY27 | Other Income | 1,148.0 | 1,147.5 | 655.7 | explained | OtherIncome; + ExceptionalItemsBeforeTax; + share of associates/JVs |
| Q1FY27 | Interest | 40.0 | 39.8 | 39.8 | exact |  |
| Q1FY27 | Depreciation | 428.0 | 427.7 | 427.7 | exact |  |
| Q1FY27 | Profit before tax | 5,861.0 | 5,860.8 | 5,774.9 | explained | Sales - Expenses + OtherIncome' - Interest - D&A; + share of associates/JVs |
| Q1FY27 | Tax % | 23.0 | 23.4 | 23.4 | exact |  |
| Q1FY27 | Net Profit | 4,509.0 | 4,508.8 | 4,508.8 | exact |  |
| Q1FY27 | EPS in Rs | 3.51 | 3.51 | 3.51 | exact |  |

**ITC: annual profit and loss, FY26 (screener `profit-loss`, Mar 2026)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| FY26 | Sales | 78,868.0 | 78,868.4 | 89,913.3 | explained | - excise (OtherExpenses member "Excise Duty") |
| FY26 | Expenses | 51,562.0 | 51,550.5 | 64,391.1 | UNEXPLAINED | see gap list |
| FY26 | Operating Profit | 27,306.0 | 27,317.9 | 27,317.9 | UNEXPLAINED | see gap list |
| FY26 | OPM % | 35.0 | 34.6 | 30.4 | explained | OP / Sales; - excise (OtherExpenses member "Excise Duty") |
| FY26 | Other Income | 2,523.0 | 2,134.1 | 2,425.8 | UNEXPLAINED | see gap list |
| FY26 | Interest | 85.0 | 85.2 | 85.2 | exact |  |
| FY26 | Depreciation | 1,711.0 | 1,710.5 | 1,710.5 | exact |  |
| FY26 | Profit before tax | 28,033.0 | 28,033.4 | 27,656.3 | explained | Sales - Expenses + OtherIncome' - Interest - D&A; + share of associates/JVs |
| FY26 | Tax % | 25.0 | 25.4 | 25.4 | exact |  |
| FY26 | Net Profit | 21,018.0 | 21,018.2 | 21,018.2 | exact |  |
| FY26 | EPS in Rs | 16.51 | 16.52 | 16.52 | exact |  |

**ITC: balance sheet (screener `balance-sheet`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| Q4FY26 | Equity Capital | 1,253.0 | 1,253.0 | 1,253.0 | exact |  |
| Q4FY26 | Reserves | 71,254.0 | 71,254.4 | 71,254.4 | exact |  |
| Q4FY26 | Borrowings | 2,399.0 | 2,399.1 | 2,186.2 | explained | B1 |
| Q4FY26 | Other Liabilities | 18,731.0 | 18,730.8 | - | explained | B6 |
| Q4FY26 | Total Liabilities | 93,637.0 | 93,637.2 | 93,792.4 | explained | B2 |
| Q4FY26 | Fixed Assets | 22,443.0 | 22,442.5 | 17,471.2 | explained | B3 |
| Q4FY26 | CWIP | 1,602.0 | 1,601.9 | 1,499.4 | explained | B4 |
| Q4FY26 | Investments | 38,128.0 | 38,128.4 | 32,840.2 | explained | B5 |
| Q4FY26 | Other Assets | 31,464.0 | 31,464.4 | - | explained | B6 |
| Q4FY26 | Total Assets | 93,637.0 | 93,637.2 | 93,792.4 | explained | B2 |

**ITC: cash flow FY26 (screener `cash-flow`)**

| Period | Row | Screener | XBRL (screener formula) | Memory | Verdict | Rule |
|---|---|---:|---:|---:|---|---|
| FY26 | Cash from Operating Activity | 18,464.0 | 18,464.3 | 18,464.3 | exact |  |
| FY26 | Cash from Investing Activity | -2,321.0 | -2,320.7 | -2,320.7 | exact |  |
| FY26 | Cash from Financing Activity | -16,147.0 | -16,147.1 | -16,147.1 | exact |  |
| FY26 | Net Cash Flow | -4.0 | -3.5 | -3.5 | exact |  |

## 11. Screener's Excel, to the paisa

The owner's five workbooks (`scrxl/itc.xlsx`, `lt.xlsx`, `tcs.xlsx`, `sunpharma.xlsx`, `tatasteel.xlsx`; the Data Sheet read straight from the zip XML, which also reads the three files `openpyxl` cannot open). The Data Sheet holds 10 quarters (up to Jun 2026 for Sun Pharma, Tata Steel and ITC; up to Sep 2026 for TCS and L&T), 10 years and the balance sheet and cash flow by year, to 2 decimals (TCS: whole crore, as TCS files). Sheets: Profit & Loss, Quarters (hidden), Balance Sheet, Cash Flow, Customization, Data Sheet; I read only the Data Sheet. "Exact" here means within ₹0.01 Cr (0.02 for lines screener derives: Total, Other Assets, Other Liabilities, Profit before tax, Operating Profit). Same XBRL files as before, consolidated; no new downloads.

### 11.1 Result

**371 of the 378 figures that have an XBRL counterpart are reproduced to the paisa by one formula per row, tested on all 5 companies** (6 quarters for TCS and L&T, 5 for the others; FY26; Mar 2026 balance sheet; FY26 cash flow). The 7 that are not are all in the FY26 annual column (section 11.4). On top of those, 30 Data Sheet figures have no XBRL element at all (section 11.4).

| Block | Rows | Figures | Reproduced to the paisa |
|---|---:|---:|---:|
| Quarters (Sales, Expenses, Other Income, Depreciation, Interest, Profit before tax, Tax, Net profit, Operating Profit) | 9 | 243 | **243** |
| FY26 annual (Sales, Raw Material Cost, Change in Inventory, Employee Cost, Other Income, Depreciation, Interest, Profit before tax, Tax, Net profit) | 10 | 50 | 43 |
| Mar 2026 balance sheet (10 rows + Receivables, Inventory, Cash & Bank) | 13 | 65 | **65** |
| FY26 cash flow | 4 | 20 | **20** |

### 11.2 The exact formulas (units: crore; XBRL rupees / 10^7; same elements as section 4)

| Data Sheet row | Formula | Pass |
|---|---|---|
| **Sales** (quarter, year) | `RevenueFromOperations` - excise (`OtherExpenses` member "Excise Duty"). ITC Q1FY27: 29,523.30 - 10,408.93 = 19,114.37 (Data Sheet 19,114.37). | 27/27, 5/5 |
| **Expenses** (quarter) | `Expenses` - `FinanceCosts` - `DepreciationDepletionAndAmortisationExpense` - excise - finance-cost member of `OtherExpenses`. | 27/27 |
| **Interest** (quarter) | `FinanceCosts` + `OtherExpenses` member "Finance cost of financial services business ..." (L&T only). L&T Q1FY26: 781.61 + 1,706.35 = 2,487.96 (Data Sheet 2,487.96). | 27/27 quarters; year 4/5 (not L&T) |
| **Depreciation** | `DepreciationDepletionAndAmortisationExpense`. | 27/27, 5/5 |
| **Other Income** (quarter) | `OtherIncome` + `ExceptionalItemsBeforeTax` (+ associates' share for ITC and Tata Steel only, 11.3). TCS Q3FY26: 1,118 - 3,391 = -2,273. | 27/27 quarters; year 2/5 (TCS, Tata Steel) |
| **Profit before tax** | Sales - Expenses + Other Income - Interest - Depreciation (= `ProfitBeforeTax` + the share where the share is counted). | 27/27, 5/5 |
| **Tax** | `TaxExpense`. | 27/27, 5/5 |
| **Net profit** | **`ProfitOrLossAttributableToOwnersOfParent`, the owners' share.** The whole-profit variant (`ProfitLossForPeriod`) fails 27/27. | 27/27, 5/5 |
| **Operating Profit** (quarter) | Sales - Expenses (as above). | 27/27 |
| Raw Material Cost (year) | `CostOfMaterialsConsumed` + `PurchasesOfStockInTrade` (Sun 11,200.55, Tata 92,628.07, ITC 35,098.34). | 3/5 |
| Change in Inventory (year) | **minus** `ChangesInInventoriesOfFinishedGoodsWorkInProgressAndStockInTrade` (the Data Sheet's sign is the opposite of the file's; ITC +2,550.46 against the file's -2,550.46); the sheet subtracts it in its expense total. | 5/5 |
| Employee Cost (year) | `EmployeeBenefitExpense`. | 4/5 |
| Equity Share Capital, Reserves | `EquityShareCapital`, `OtherEquity`. | 5/5 each |
| Borrowings | `BorrowingsNoncurrent` + `BorrowingsCurrent` + "Lease liabilities" members of `OtherNoncurrentFinancialLiabilities` and `OtherCurrentFinancialLiabilities`. | 5/5 |
| Total Liabilities, Total Assets | `Assets` - min(`DeferredTaxAssetsNet`, `DeferredTaxLiabilitiesNet`) (March column). | 5/5 |
| Net Block | `PropertyPlantAndEquipment` + `InvestmentProperty` + `Goodwill` + `OtherIntangibleAssets` + right-of-use assets (member of `OtherNoncurrentAssets`; ITC 501.00). | 5/5 |
| Capital Work in Progress | `CapitalWorkInProgress` + `IntangibleAssetsUnderDevelopment`. | 5/5 |
| Investments | `InvestmentsAccountedForUsingEquityMethod` + `NoncurrentInvestments` + `CurrentInvestments`. | 5/5 |
| Other Assets; Other Liabilities | Total - Net Block - CWIP - Investments; Total - Equity Share Capital - Reserves - Borrowings. | 5/5 each |
| Receivables | `TradeReceivablesCurrent` only (TCS: 67,714; the non-current 213 is left out). | 5/5 |
| Inventory | `Inventories`. | 5/5 |
| Cash & Bank | `CashAndCashEquivalents` + `BankBalanceOtherThanCashAndCashEquivalents` (ITC 643.46 + 2,365.33 = 3,008.79). | 5/5 |
| Cash from Operating / Financing / Net Cash Flow | `CashFlowsFromUsedIn...OperatingActivities`, `...FinancingActivities`, `IncreaseDecreaseInCashAndCashEquivalents` (after the exchange effect). | 5/5 each |
| Cash from Investing | `CashFlowsFromUsedInInvestingActivities` + `EffectOfExchangeRateChangesOnCashAndCashEquivalents`. TCS: -12,845 + 959 = -11,886. | 5/5 |

The paisa-level result confirms every rule of section 4 and removes the "within 1 Cr" slack: no row needed a tolerance.

### 11.3 The associates' share (open rule P4), from the Data Sheet's Other Income and Profit before tax

Test: for each company and quarter, the Data Sheet's Other Income and Profit before tax were compared with the XBRL value without the share and with it. Each fits exactly one way, to the paisa, and the way never changes inside a company.

| Company | Share of associates and JVs, FY26 | Quarterly shares (Cr) | Data Sheet counts it in Other Income and PBT |
|---|---:|---|---|
| ITC | +377.08 | 68.76, 66.36, 102.39, 139.57, 85.91 | **yes**, 5 of 5 quarters and the year |
| Tata Steel | +368.50 | 79.72, 50.75, 103.96, 134.07, 96.15 | **yes**, 5 of 5 and the year |
| L&T | -205.52 | -7.40, -9.08, -4.58, -184.47, +5.18, +34.00 | **no**, 6 of 6 and the year |
| Sun Pharma | -55.87 | -9.75, -12.14, -19.92, -14.06, -9.57 | **no**, 5 of 5 and the year |
| TCS | 0 | none | not applicable |

- **In every company the Net profit row does include the share** (owners' share of the whole profit). So where the share is not counted, the Data Sheet does not foot: Sun Q1FY26 PBT 3,172.77 - Tax 870.15 - minority 14.24 = 2,288.38, but Net profit is 2,278.63, short by exactly the share (-9.75). The share is in the profit and outside Other Income and PBT.
- **Pattern:** the companies that count it are the two whose share is a profit in every quarter and the year; the two that do not have a loss for FY26 (Sun in all five quarters; L&T in four of six and -205.5 for the year). That fits "counted when the associates earn a profit, left out when they make a loss". It is **not** a per-quarter sign test: L&T's two latest quarters are profits (+5.18, +34.00) and are still left out, so the choice is fixed for the company for a longer span (a year, or a flag per company). Size does not explain it (L&T's -184.47 is 2.2% of that quarter's PBT and is left out; ITC's 1% is counted). BPCL (lead's check) counts it and has a profit share.
- **Not settled** from the files in hand. The one test that separates "decided by the previous year's sign" from "a fixed flag per company": L&T's Dec 2026 quarter and FY27 year, or any company whose share changes sign between years (the XBRL files of FY24 and FY25 for L&T, Sun, ITC and Tata Steel plus their Data Sheet quarters back to Mar 2024 would show it; the Data Sheets hold those quarters, the XBRL files for them were not downloaded).

### 11.4 Figures no formula reproduces to the paisa

**Seven, all in the FY26 annual column**, with the closest formula and the residual (Data Sheet minus formula):

| Company | Row | Data Sheet | Closest formula | Residual | What it is |
|---|---|---:|---|---:|---|
| Sun Pharma | Other Income | 1,894.81 | `OtherIncome` + `ExceptionalItemsBeforeTax` = 664.24 | **+1,230.57** | the same amount shows in the sheet's expense lines (their sum is 41,961.21 against the file-based 40,730.64, +1,230.57). Of the year's exceptional items (-1,307.48), 1,230.57 sit in expenses and 76.91 stay in Other Income. |
| L&T | Other Income | 4,051.72 | 4,038.24 | +13.48 | annual-report classification |
| L&T | Interest | 10,055.94 | `FinanceCosts` + finance-cost member = 9,844.16 | +211.78 | annual-report classification |
| L&T | Raw Material Cost | 97,682.71 | `CostOfMaterialsConsumed` + purchases = 101,854.69 | -4,171.98 | annual-report classification |
| L&T | Employee Cost | 52,191.85 | `EmployeeBenefitExpense` = 52,187.22 | +4.63 | annual-report classification |
| ITC | Other Income | 2,523.09 | 2,511.18 (= the sum of the four Data Sheet quarters) | +11.91 | annual-report reclassification; the sheet's expense lines exceed the file's by the same 11.91 |
| TCS | Raw Material Cost | 43.00 | `CostOfMaterialsConsumed` = 0 | +43.00 | taken out of other expenses: the four annual-report lines below sum to 39,586, which is the file's other expenses 39,629 less 43 |

The reclassifications balance exactly, so profit is untouched: for L&T, Expenses -198.30 = Other Income +13.48 - Interest +211.78; for Sun and ITC the Other Income gap equals the Expenses gap. PBT and Net profit (owners) of FY26 are reproduced for all 5.

**Data Sheet figures with no XBRL element (30 figures):**
- Annual **Power and Fuel, Other Mfr. Exp, Selling and admin, Other Expenses** (20 figures; these come from the annual report, as the lead found). Only their **sum** can be tested: it equals the file's `OtherExpenses` less excise for Tata Steel exactly (78,170.83); equals it plus the Other Income gap for Sun (18,998.67 = 17,768.10 + 1,230.57) and ITC (12,233.02 = 12,221.11 + 11.91); less 43.00 for TCS (39,586 = 39,629 - 43); L&T 101,618.14 against 97,649.09 (file's 104,644.43 less the finance-cost member 6,995.34), +3,969.05, which with the raw-material (-4,171.98), employee (+4.63) differences adds to -198.30.
- **Dividend Amount** (5 figures; declared dividend). Nearest file figure: dividends paid in the cash flow. Data Sheet minus that: TCS 39,820 vs 39,571 (+249.00), Sun 3,838.88 vs 3,937.80 (-98.92), L&T 5,227.47 vs 4,676.22 (+551.25), Tata Steel 4,989.76 vs 4,489.87 (+499.89), ITC 18,167.78 vs 18,272.02 (-104.24). Not reproducible: declared against paid.
- **No. of Equity Shares** (5 figures): not in the results file. Share capital / face value is within the file's rounding for TCS, Sun, L&T and ITC, and 0.33 Cr (3.3 crore shares) short for Tata Steel (Data Sheet 12,477,659,071 shares against the file's 1,247.44 Cr of share capital).
- Price, market capitalisation, number of shares in the meta rows: market data.

### 11.5 Where the Data Sheet differs from the web page

565 figures that appear on both were compared (all quarters in the sheet, FY26 annual, Mar 2026 balance sheet, FY26 cash flow; "Fixed Assets" on the page is "Net Block" in the sheet; Tax % computed from the sheet's Tax and PBT; the page's annual Expenses against the sheet's expense lines summed with the inventory change subtracted). **510 are equal to the page's rounding. The 55 that differ are all one row, Net profit, in every company and every period** (all 55 of the 55 Net profit pairs): the page shows the whole profit (our `ProfitLossForPeriod`), the sheet shows the owners' share.

| Net profit, FY26 | Data Sheet (owners) | Web page (whole) | Gap (minority) |
|---|---:|---:|---:|
| TCS | 49,210 | 49,454 | 244 |
| Sun Pharma | 11,479.42 | 11,509 | 29.58 |
| L&T | 16,083.99 | 18,954 | 2,870.01 |
| Tata Steel | 10,793.87 | 10,886 | 92.13 |
| ITC | 20,689.47 | 21,018 | 328.53 |

I found no other row that differs. Other differences are structure, not figures: the sheet carries no EPS, Tax % or OPM % row (the page computes them), and the page's EPS follows the owners' share (ITC Q1FY27: 4,394.13 / 1,252.95 = 3.51). Our memory's `pat` is the whole profit and `pat_owners` the owners' share, so both screener views can be matched from memory.

Scripts: `scratchpad/five/scripts/xlsx.py` (zip reader), `ds.py`, `dsq.py`, `dsa.py`, `dsb.py`, `dscf.py`, `dscount.py` (counts, `dscount.json`), `dsweb.py` (Data Sheet against web page, `dsweb.json`).
