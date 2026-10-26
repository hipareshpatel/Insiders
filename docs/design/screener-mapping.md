# Screener.in terms against the official filing and our memory (study, 26 Oct 2026)

Status: read-only study. Nothing was fetched, built or written to memory. Owner's ask (26 Oct): map screener's words to the
official filing words and to our memory and card words before any test uses screener data.

## 0. How to read this

**Sample.** 47 saved screener pages (the owner's 48 count includes one stray `500325.json`): 30 companies, consolidated
`*_c.html` and standalone `*_s.html`. Our side: the 43 saved memory files in `mem/`. LT has no memory, so 29 companies are
measured. Each page was matched to memory on the page's own basis (the page says "Consolidated Figures" or "Standalone
Figures"; SBILIFE's `_c` page is standalone).

**What we compare with.** Only exchange-file figures in memory (source id starts `xbrl:`), on a labelled basis. No AI figure,
no `nse-...` id, no screener-fill figure. Memory is the exchange's own XBRL results file, so "agreement" here means
screener against the exchange file, not against the PDF. For lines memory lacks, it says "not in memory".

**Match rule (owner's).** Money lines: within ₹1 Cr or 0.5%. EPS: within ₹0.06 or 0.5%. Percent lines: within 0.6 point.
Share percentages: within 0.06 point. Screener shows whole crore, so rounding is inside the rule.

**Counts.** "Q" is the quarterly table, "A" the annual (Mar year) table. `n` is the pairs where both sides had a figure.
Written as matches/n. Consolidated and standalone are pooled (they behave alike unless noted).

**Hidden finding about memory itself.** 3,651 exchange figures in these 43 files have no basis label
(`basis` is empty on `xbrl:res` figures from older writes). On this sample they behave like consolidated figures: profit
45 of 50 against consolidated pages, 8 of 28 against standalone pages. They are left out of every count below. The label job
(F150, TODO 3) would fix it. Until it runs, a standalone page cannot be tested against them.

**Screener's page layout** (checked on all 47 pages): top ratios box, quarterly results (12 quarters), profit and loss
(12 years plus a TTM column), balance sheet (12 years plus the latest half year), cash flows (12 years), ratios (12 years),
shareholding (12 quarters; a hidden yearly tab). A line with a `+` opens a schedule of sub-lines on click, loaded by a
separate call that the saved pages do not hold. Expandable lines: Sales or Revenue, Expenses, Other Income, Net Profit
(both P&L tables); Borrowings, Fixed Assets, Other Assets, Other Liabilities (balance sheet); the three cash-flow activities.

**Screener's own sums (identities, measured on the 328 general-company quarter columns).** These are how its lines are built:

| Identity | Holds on |
| --- | --- |
| Operating Profit = Sales − Expenses | 328 of 328 |
| OPM % = Operating Profit / Sales | 326 of 328 |
| Profit before tax = Operating Profit + Other Income − Interest − Depreciation | 327 of 328 |
| Net Profit = PBT × (1 − Tax %) (rounding of Tax %) | 256 of 328 |
| Bank and NBFC: Financing Profit = Revenue − Interest − Expenses | 72 of 72 |
| Bank and NBFC: PBT = Financing Profit + Other Income − Depreciation | 91 of 91 |
| TTM column = sum of the last four quarter columns | 122 of 122 |

So Other Income is a plug. It takes whatever the filing's other lines do not put into Sales, Expenses, Interest and
Depreciation.

## 1. The tables

Official names: the left part is the Ind AS Schedule III line (companies and NBFCs); the XBRL element is the SEBI results
taxonomy name our parser reads (`xbrl.py` `RESULT_TAGS`, `BALANCE_TAGS`). The bank format is the RBI banking template; the
insurer format is IRDAI's revenue and profit-and-loss accounts. Names marked (assumption) are not in our code and were not
checked against a filing.

### 1a. Quarterly results and annual profit and loss, general companies (non-lender)

| Screener line | What it means (checked against the numbers) | Official line / XBRL element | Our memory metric / card term | How to compare | Measured (Q · A) | Notes and known differences |
| --- | --- | --- | --- | --- | --- | --- |
| Sales | Revenue from operations, but net of excise duty (and similar levies) where the company pays them | Revenue from operations / `RevenueFromOperations` | `revenue`; card "Revenue" | Equal, except for excise payers: Sales = `revenue` − excise (`ExciseDuty`, read by the parser as `excise_duty` but not kept in memory) | 244/287 · 69/85 (85%, 81%) | Misses sit in six companies. ITC: screener lower by 7 to 12% (ITC Q2FY24: 17,774 against 19,270). RELIANCE: screener lower by 1.3 to 1.9%. HINDUNILVR: lower by 1.7 to 4.6%. ONGC and MARUTI: screener higher by 0.5 to 3.2%, cause not found. Screener's wording "Sales" is not "Total income". `total_income` matches only 12 of 293. Excise is the cause for ITC (our own `xbrl.py` comment, round 6); for the others it is an assumption |
| Expenses | All operating costs: total expenses less finance cost and depreciation, with the associates' result (and sometimes an exceptional loss) pushed in | Total expenses / `Expenses`, less `FinanceCosts`, less depreciation | `total_expenses` − `finance_cost` − `depreciation`. No card term | Derived: `total_expenses` − `finance_cost` − `depreciation` | 240/290 · 72/87 (83%) | `total_expenses` alone matches 4 of 293 (it includes interest and depreciation). ADANIPORTS: screener adds the associates' loss (Q2FY26 3,827 against 3,617 + 210). KIRLPNU Q3FY26: adds the 18 Cr exceptional charge. ITC standalone: follows the Sales difference. Line is a derived sum: not a filing line |
| Operating Profit | Sales − Expenses. Not an official line. Other income and exceptional items are out, associates' result is in (as a cost or income) | None (screener's own). Closest: our EBITDA | `ebitda`; card "EBITDA" | Derived: `revenue` − (`total_expenses` − `finance_cost` − `depreciation`), or compare with `ebitda` as a naming match | vs `ebitda` 262/289 · 66/87 (91%, 76%) | Our EBITDA = profit before exceptional items and tax + finance cost + depreciation − other income (`xbrl.py` derived, F140). It leaves out the associates' result and exceptional items; screener's puts associates in. Same name family, small steady differences (ADANIPORTS 5 quarters differ by the associates' share). Annual match is lower: restated years |
| OPM % | Operating Profit / Sales × 100, shown to 0 or 1 decimal | None | `ebitda_margin`; card "EBITDA margin" | Derived: equal to `ebitda_margin` within 0.6 point | 251/286 · 74/87 (88%, 85%) | Same cause as Operating Profit and Sales |
| Other Income | The plug: includes the filing's other income, and exceptional gains and losses (and in some companies the associates' result) | Other income / `OtherIncome`, plus `ExceptionalItemsBeforeTax`, plus `ShareOfProfitLossOfAssociates...` | `other_income` (+ `exceptional_items`, `share_associates`). No card term | Sum of lines: `other_income` + `exceptional_items` + `share_associates` | plain `other_income` 167/290 · 21/87 (58%, 24%); sum of three 225/290 · 50/87 (78%, 57%) | TCS FY26: screener −124 = 4,402 other income − 4,526 exceptional. ADANIPORTS Q4FY24: −70 = 303 − 374. GAIL, MARUTI, ONGC, ITC miss even the sum (not explained). Not safe as "other income" |
| Interest | Finance cost | Finance costs / `FinanceCosts` | `finance_cost` | Equal | 271/290 · 72/87 (93%, 83%) | Misses: ITC, HINDUNILVR, ONGC (quarters), KIRLPNU, GHCL (annual). Not checked whether screener adds lease or other interest |
| Depreciation | Depreciation and amortisation | Depreciation, depletion and amortisation / `DepreciationDepletionAndAmortisationExpense` | `depreciation` | Equal | 267/290 · 82/87 (92%, 94%) | Misses: ITC, HINDUNILVR, ONGC, MARUTI (a handful of columns) |
| Profit before tax | Profit after exceptional items and after the associates' share. Equal to profit + tax | Profit before tax / `ProfitBeforeTax` (before the associates' share in SEBI's sums), plus `ShareOfProfitLoss...` | `pbt`; card "Profit before tax" | Sum of lines: `pbt` + `share_associates` (= `pat` + `tax_expense`) | `pbt` alone 229/290 · 70/87 (79%); `pbt` + `share_associates` 252/290 · 75/87 (87%) | SEBI's taxonomy adds the associates after tax (`xbrl._pbt_without_associates`, F140); screener adds them in. Standalone has no associates: `pbt` matches. Misses beyond that: ONGC, ITC, SunPharma and TorrentPharma standalone, MARUTI standalone (screener differs by 0.5 to 15%, cause not found; possibly restated) |
| Tax % | Tax expense / screener's profit before tax × 100, to whole percent | Tax expense / `TaxExpense` (= `CurrentTax` + `DeferredTax`) | `tax_expense`; no ratio stored | Derived: `tax_expense` / (`pbt` + `share_associates`) × 100 | 263/290 · 79/87 (91%) | With plain `pbt` as the base: 249/293. Screener leaves the annual TTM tax blank. Tax % is rounded to whole percent |
| Net Profit | Profit for the period including the minority's share (not "profit to owners") | Profit for the period / `ProfitLossForPeriod` | `pat`; card "Net profit" (the card's "profit to shareholders" is `pat_owners`) | Equal to `pat` | `pat` 278/288 · 82/85 (97%); `pat_owners` 92/142 · 27/42 (65%) | Where the minority share is real (80 columns) screener equals `pat` on 74 and `pat_owners` on 31. So screener's name hides the minority. Misses: ONGC, MARUTI, NMDC (one column each is wrong on screener, see NMDC Q4FY25 in `screener_fill.py`) |
| EPS in Rs | Basic EPS, restated by screener for later splits and bonus issues | Basic EPS / `BasicEarningsLossPerShare...` | `eps`; card "EPS (₹)" | Equal at the same date; not equal across a split | 220/287 · 60/85 (77%) | Screener restates history. RELIANCE (bonus): ×0.5. KIRLPNU (×0.5), NMDC (×0.333), HDFCBANK (×0.5), BAJFINANCE (×0.1, split plus bonus). Ours is as filed. Also: a Q4 column can show the year's EPS (ITC standalone Q4FY25: 15.63 against 3.89; ABB standalone Q4FY26: 84.17 against 16.14; assumption, not checked against the PDF). GHCL differs by 0.5%: basic against diluted or screener's own sum (assumption) |
| Dividend Payout % (annual only) | Dividends paid / net profit | Dividends declared (corporate action; not in the results file) | not in memory | Not testable here | not measured | "Not in memory, can be compared only with the official PDF or the board's dividend filings" |
| Raw PDF | A link to the quarter's filing. Not a number | the results filing itself | none | Not a figure | n/a | Useful: gives the PDF to referee a screener figure (the referee in `screener_referee.py` already uses our R2 text cache) |
| TTM (a column) | Sum of the last four quarters (profit and loss only) | none | `ttm_*` in `metrics.py` | Derived: our sum of four quarters | TTM = last four quarters 122/122 | Our ttm needs four quarters in memory |

### 1b. Banks and NBFCs (the lender variants)

Screener renames the top line "Revenue", adds "Financing Profit" and "Financing Margin %", and for banks adds
"Gross NPA %" and "Net NPA %" to the quarterly table. "Depreciation" stays. Annual tables have no NPA rows.

| Screener line | What it means | Official line / XBRL element | Our memory metric / card term | How to compare | Measured (Q · A) | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Revenue (bank) | Interest earned | Interest earned (RBI Form B, I) / `InterestEarned` | `interest_earned` | Equal | 48/48 · 11/11 | Not "total income": a bank's income also has other income (fees and trading), which screener files under Other Income |
| Revenue (NBFC) | Revenue from operations (interest + fees + fair-value gains) | Revenue from operations / `RevenueFromOperations` | `revenue` | Equal | 18/18 · 5/5 | `interest_earned` fails for NBFCs: BAJFINANCE and MUTHOOTFIN differ by 1.5 to 13% |
| Revenue (both) | Total income less other income | `Income` − `OtherIncome` | `total_income` − `other_income` | Derived | 66/66 · 17/17 | Works for every sampled lender: a safe rule when the type is not known |
| Interest (bank) | Interest expended | Interest expended / `InterestExpended` | `interest_expended` | Equal | 48/48 · 11/11 | |
| Interest (NBFC) | Finance costs | Finance costs / `FinanceCosts` | `finance_cost` | Equal | 18/18 · 3/6 | Annual NBFC misses: 3 of 6 (BAJFINANCE, MUTHOOTFIN; cause not found) |
| Expenses | Bank: operating expenses plus provisions (not interest). NBFC: total expenses less finance cost and depreciation | Operating expenses + provisions / `OperatingExpenses`, `ProvisionsOtherThanTaxAndContingencies` | `other_expenses` (opex), `provisions`; no sum | Bank: Revenue − Interest − Financing Profit (identity, 72/72). NBFC: `total_expenses` − `finance_cost` − `depreciation` | NBFC 15/18 · 0/6 | `total_expenses` on a bank is not stored in a usable form (0 of 18) |
| Financing Profit | Bank: what is left after interest, operating cost and provisions but **before other income**. Not pre-provision profit | None (screener's own) | `pre_provision_operating_profit`, `provisions`, `other_income` | Bank: `pre_provision_operating_profit` − `provisions` − `other_income`. NBFC: `pbt` − `other_income` + `depreciation` | bank 46/48 · 0/11; NBFC 15/18 · 5/6 | **Danger of a wrong match:** it is not our PPOP. PPOP on a card is a different (larger) figure. For a bank it is often negative (HDFCBANK −15,342), because the non-interest income sits below it. Annual bank 0/11: the sums mix the annual figures (provisions or other income missing in the year; not investigated) |
| Financing Margin % | Financing Profit / Revenue | None | none | Derived | not measured | Do not compare with NIM or margin on cards. NIM is not in memory ("needs average earning assets") |
| Other Income | Bank: non-interest income. NBFC: other income only | Other income / `OtherIncome` | `other_income` | Equal | bank 42/48 (SBIN: 6 misses); NBFC 10/18 · 11/17 pooled A | Screener's Other Income in a bank is large (HDFCBANK 42,535 a quarter); keep the word "non-interest income" in front of it |
| Depreciation | Depreciation | `DepreciationDepletionAndAmortisationExpense` | `depreciation` | Equal | 18/18 · 6/6 | Banks mostly show 0 |
| Profit before tax | Profit before tax | Profit before tax / `ProfitLossFromOrdinaryActivitiesBeforeTax` (bank), `ProfitBeforeTax` (NBFC) | `pbt` | Equal | 62/66 · 14/17 | The misses are HDFCBANK consolidated, 4 quarters |
| Tax % | Tax / PBT | Tax expense | `tax_expense` / `pbt` | Derived | 65/66 · 16/17 | |
| Net Profit | Consolidated bank: profit after the associates' share and before the minority. Standalone bank and NBFC: profit for the period | `ProfitLossForThePeriod`, group profit | `pat` (a bank's `pat` is overwritten with the group figure when tagged) | Equal to `pat` for standalone and NBFC; consolidated bank needs a look | `pat` 51/66 · 11/16; `pat_owners` 5/18 | Consolidated banks: screener is 1 to 4% above our `pat` (HDFCBANK Q4FY24 18,013 against 17,622; SBIN 9 of the consolidated quarters). Likely the associates' share, which we do not keep for banks (assumption). Standalone matches 24/24 |
| EPS in Rs | Basic EPS, restated | `BasicEarningsPerShareAfterExtraordinaryItems` | `eps` | Equal at the same date | 45/66 · 9/16 | Same restating as 1a: HDFCBANK bonus (×0.5), BAJFINANCE (×0.1) |
| Gross NPA % / Net NPA % | Gross and net NPA ratio of the quarter | `PercentageOfGrossNpa`, `PercentageOfNpa` (our scale rule: a fraction becomes a percent) | `gnpa_pct`, `nnpa_pct` | Equal | 24/24 and 24/24 (standalone banks) | Screener's NPA rows are blank on most consolidated bank pages (HDFCBANK consolidated shows none). Safe where present |

### 1c. Insurers (HDFCLIFE, SBILIFE; screener keeps the company layout)

| Screener line | What it means | Official line | Our memory metric / card term | How to compare | Measured (Q · A) | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Sales | About total income (premium plus investment income), not premium | Total income (revenue account) / `Income` | `total_income`; `revenue` is net premium; `gross_premium` | Not equal: close to `total_income` within 0.1 to 1.1%, never exact | `total_income` 2/17 · 0/4 | Not a safe equal. Screener adds a small amount (HDFCLIFE Q4FY25 24,191 against 23,965). `revenue` (net premium) and `gross_premium` match 0 of 15 |
| Expenses, Operating Profit, OPM % | Screener's plug of the two accounts (OPM 1 to 2%) | none | none | Unusable | not measured | Meaningless for an insurer: they mix the policyholders' and the shareholders' accounts |
| Other Income, Interest, Depreciation | Mostly 0 or small | none | `other_income` is absent for these two | Unusable | not measured | |
| Profit before tax | Shareholders' profit before tax, as screener reads it | Profit before tax (profit and loss account) | `pbt` | Not equal: screener is 15 to 48 Cr higher | 0/16 · 0/4 | Seen on every quarter. Screener's figure may include the policyholders' transfer (assumption) |
| Tax % | Tax / its PBT | `ProvisionsForTaxes` | `tax_expense` | Unusable | 0/16 | Our `tax_expense` is the shareholders' tax |
| Net Profit | Profit after tax of the shareholders' account | `ProfitLossAfterTaxAndExtraordinaryItems` (life) | `pat` | Equal | 14/14 · 3/3 | The safe one. Quarter figures agree to the rupee crore |
| EPS in Rs | Basic EPS | `BasicAndDilutedEPSAfterExtraordinaryItems...` | `eps` | Equal | 14/14 · 4/4 | Safe |

### 1d. Balance sheet (annual Mar columns plus the latest half year; "Sep 2026" = our period Q2FY27)

Screener's balance sheet is a compressed layout: only ten lines. Memory's balance sheet is filed only with half-year and
year results. The screener Total Liabilities line is the same as Total Assets (equity + liabilities).

| Screener line | What it means | Official line / XBRL element | Our memory metric / card term | How to compare | Measured | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Equity Capital | Paid-up share capital | Equity share capital / `EquityShareCapital` | `equity_capital_cr` | Equal | 106/107 | Safe |
| Reserves | Other equity (reserves and surplus) | Other equity / `OtherEquity` | `reserves_cr` (or `net_worth_cr` − `equity_capital_cr`) | Equal | 104/107 (`reserves_cr`); 102/107 (net worth less capital) | Banks: 13/26 on `reserves_cr`. Insurers: only net worth less capital matches (6/6). Minority is not in Reserves for most (adding it matches only 26/54) |
| Borrowings (Borrowing for lenders) | Debt, **including lease liabilities** and other debt-like items | Borrowings (current + non-current) / `BorrowingsNoncurrent` + `BorrowingsCurrent`; for lenders `Borrowings`, `DebtSecurities`, `SubordinatedLiabilities` | `gross_debt_cr`; card "Gross debt" | Not equal: screener is larger | general 10/109; lenders 18/25 | Screener 5% to 12x our figure (DBCORP 213 against 32.5: leases). Cause is an assumption: leases. Do not compare on a card |
| Deposits (banks only) | Customer deposits | Deposits / `Deposits` | `deposits_cr` | Equal | 17/17 | Safe |
| Other Liabilities | A plug: total liabilities less equity, reserves and borrowings. Includes minority | none (sum of lines) | none | Derived (needs the line list) | general 16/107 | Unusable. Also an expandable line |
| Total Liabilities | Equal to Total Assets | Total equity and liabilities | `total_assets_cr`; our `total_liabilities_cr` is liabilities **without equity** | Equal to `total_assets_cr`, not to `total_liabilities_cr` | general 82/107; lenders 21/21; | Naming trap: same word, different line. Misses: ADANIPORTS, INFY, ONGC (1 to 2%), MARUTI and NMDC FY23 (6 to 18%). Likely restated or a different minority treatment (assumption) |
| Fixed Assets | Net block: property, right of use, intangibles and others | Property, plant and equipment / `PropertyPlantAndEquipment` (plus other lines) | `fixed_assets_cr` (PPE only), `goodwill_cr` | Not equal: screener is larger | general 0/107 | Do not compare. Adding goodwill does not close it (3/107) |
| CWIP | Capital work in progress | `CapitalWorkInProgress` | `cwip_cr` | Equal | 67/107 | Misses are screener adding intangibles under development (assumption) |
| Investments | Non-current plus current investments, wider than ours | `NoncurrentInvestments` + `CurrentInvestments` | `investments_cr` | Equal for lenders; general companies differ | general 80/107; lenders 25/25 | Misses: ADANIPORTS (×1.5 to ×3), GAIL, INFY, ITC (screener adds other financial assets; assumption) |
| Other Assets | A plug | none | none | Unusable | 5/107 | |
| Total Assets | Total assets | Total assets / `Assets` | `total_assets_cr` | Equal | general 82/107; lenders 21/21 | Same misses as Total Liabilities |

### 1e. Cash flows (annual only; half years are not on screener)

| Screener line | What it means | Official line / XBRL element | Our memory metric / card term | How to compare | Measured | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Cash from Operating Activity | Net cash from operations | `CashFlowsFromUsedInOperatingActivities` | `operating_cash_flow` | Equal | general 84/91; insurers 5/5; lenders 15/19 | Our memory has it only at half-year and year ends (FYxx, H1FYxx) |
| Cash from Investing Activity | Net cash from investing | `CashFlowsFromUsedInInvestingActivities` | `investing_cash_flow` | Equal | general 57/93; insurers 5/5; lenders 4/19 | Misses of 1 to 25% (ADANIPORTS, BAJAJFINSV, INFY). One real clash: INFY FY26 3,546 against our 1,946 (our FY26 equals the FY25 figure; check memory) |
| Cash from Financing Activity | Net cash from financing | `CashFlowsFromUsedInFinancingActivities` | `financing_cash_flow` | Equal | general 88/93; lenders 14/19 | |
| Net Cash Flow | Net change in cash | `IncreaseDecreaseInCashAndCashEquivalents` | `net_cash_flow` | Equal | general 82/93; lenders 15/19 | |
| Free Cash Flow | Operating cash flow less screener's purchase of fixed assets | none | `capex`, `capex_intangible`, `capex_intangible_wip` (our parts) | Derived: `operating_cash_flow` − `capex` (not equal) | general 26/91 | Screener's purchases are wider than the "purchase of PPE" line we keep: the implied purchases equal our `capex` in 24 of 103 years. Do not use as a card figure |
| CFO/EBITDA (annual; the tooltip says "CFO (before tax) / Operating Profit") | Operating cash flow before tax over screener's Operating Profit | none | none | Derived | not measured (the plain `CFO / Operating Profit` matches 24 of 436) | Tax paid is not in memory; "before tax" cannot be rebuilt |

### 1f. Ratios (annual)

| Screener line | What it means | Official line | Our memory metric | How to compare | Measured (our rebuild) | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Debtor Days | Year-end trade receivables / Sales × 365 | none (ratio) | `receivables_cr` (year-end) and `revenue`; no ratio stored | Derived: `receivables_cr` / Sales × 365 | 90/97 within 1.5 days | Year-end, not an average (the average matches 13 of 67) |
| Inventory Days | Year-end inventory / material cost × 365 | none | `inventories_cr`, `raw_material_cost`, `purchases_stock_in_trade`, `inventory_change` | Derived: `inventories_cr` / (`raw_material_cost` + `purchases_stock_in_trade` + `inventory_change`) × 365 | 45/52 | Not Sales or Expenses (0 and 3 of 73) |
| Days Payable | Year-end payables / material cost × 365 | none | `payables_cr` | Same material cost | 43/52 | |
| Cash Conversion Cycle | Debtor + Inventory − Payable days | none | none | Identity | 436/436 on screener's own rows | |
| Working Capital Days | Working capital over Sales × 365 (exact formula not tested) | none | `current_assets_cr`, `current_liabilities_cr` | Not tested | not measured | Assumption: current assets less current liabilities, over Sales |
| ROCE % | Operating return: (profit before tax + interest) / average capital employed | none | none stored | Derived (rough) | 264/395 within 1 point with the average of equity + reserves + borrowings; the year-end version 179/429 | Our metric table has no ROCE. The match is rough: a 1-point gap is common |
| ROE % (banks and NBFCs only on the page) | Net profit / average (equity + reserves) | none | `roa_pct` exists, not ROE | Derived | 65/77 within 1 point with the average; year-end 42/84 | Banks show only ROE in this section |

### 1g. Shareholding (quarterly)

| Screener line | What it means | Official line (SEBI shareholding pattern XBRL) | Our memory field / term | How to compare | Measured | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Promoters | Promoter and promoter group holding | Promoter and promoter group | `promoter_pct` | Equal | 92/92 | Banks without promoters show no row on screener; memory writes 0.0 |
| FIIs | Foreign portfolio investors | Foreign portfolio investors | `fii_pct` (= `fpi_pct`) | Equal | 108/109 | The miss is ICICIBANK (screener 34.68 against our 50.44: our figure appears to include something more, depository receipts; assumption) |
| DIIs | Domestic institutions **without** the government | Institutions (domestic) | `dii_pct` includes the government's share | Sum of lines: screener DIIs + Government = `dii_pct` | DIIs alone 62/109; DIIs + Government 93/109 | Naming trap: screener splits "Government" out. 16 columns still differ (BAJFINANCE, GAIL, HDFCBANK; 0.1 to 0.2 points) |
| Government | Central and state government holdings | part of institutions | not stored separately | Derived | not measured | Appears on 28 pages |
| Public | The rest (non-institutions) | Non-institutions | not stored (100 − others) | Derived | not measured | The screener rows sum to 100 on 109 of 109 columns |
| Others | A small rest line (7 pages) | custodians and others | not stored | None | not measured | |
| No. of Shareholders | Total holders of record | Number of shareholders | `retail_holders` (holders of the retail class only) | Not equal: ours is 3 to 8% lower | 0/109 | Different definition; do not compare |

### 1h. Other items on the page

| Screener item | Meaning | Notes |
| --- | --- | --- |
| Market Cap, Current Price, High / Low, Stock P/E, Book Value, Dividend Yield, Face Value | Market data and per-share ratios from screener's own price feed | Not exchange filings. Not tested. Face Value is the one filed fact (₹ per share). Book Value is screener's (equity + reserves) / shares |
| ROCE and ROE in the top box | Latest annual ratio | Same formula as 1f, one number |
| Compounded Sales Growth and Compounded Profit Growth (10, 5, 3 years, TTM) | CAGR of Sales and of Net Profit | Derived from the annual table. Profit growth uses screener's Net Profit (incl. minority) |
| Pros and Cons, Peers, Documents, Concall summaries | Screener's checklists and links | Not figures. The tooltip says its own checklist: "exercise caution" |
| Expandable schedule lines | Sub-lines of Sales, Expenses, Other Income, Net Profit, Borrowings, Fixed Assets, Other Assets, Other Liabilities, cash-flow activities | Loaded by a separate call; not in the saved pages. They would map line by line to the filing (Other Income would show the exceptional items), but we have not seen them |

## 2. Measurement notes

1. **Counts use `xbrl:`, labelled-basis figures only** (3,651 unlabelled ones set aside, see section 0). The comparison
   script is a one-off in the session's scratch folder; it is not in the repo. It used our memory as saved in `mem/*.json`
   (the public memory API was not needed).
2. **Memory has the following P&L lines for these companies:** `revenue`, `total_income`, `other_income`, `total_expenses`,
   `raw_material_cost`, `purchases_stock_in_trade`, `inventory_change`, `employee_cost`, `other_expenses`,
   `finance_cost`, `depreciation`, `exceptional_items`, `pbt`, `current_tax`, `deferred_tax`, `tax_expense`,
   `share_associates`, `pat_continuing`, `pat_discontinued`, `pat`, `pat_owners`, `eps`, `paid_up_capital`, `ebitda`,
   `ebitda_margin` (derived); lenders: `interest_earned`, `interest_expended`, `pre_provision_operating_profit`,
   `provisions`, `gnpa_pct`, `nnpa_pct`, `roa_pct`; insurers: `gross_premium`, `first_year_premium`, `renewal_premium`,
   `single_premium`, `benefits_paid`, `commission`, `surplus`, `expense_ratio`. **Not in memory** (compare only with the
   official XBRL or PDF): excise duty (`excise_duty` is parsed but not kept), minority share (`pat_minority` is parsed
   but not kept), interest on lease, dividend paid, tax paid, material cost split by item at the quarter, Working Capital,
   NIM, CASA, capital adequacy, holders count by total, price and market cap.
3. **Memory periods used.** Quarters Q1..Q4 and annual `FYxx` (the year's own statement), half years for balance sheet and
   cash flow, `xbrl:shp` for shareholding. Screener's 12 quarters cover Q3FY24 to Q2FY27; memory holds fewer
   on average, so `n` is lower than the page's cells.
4. **Where the exchange's file itself is the odd one out is not tested.** Screener and our memory agree on a figure and are
   both wrong is possible; the referee in `screener_crosscheck.py` (the filing text, a R2 cache) is the only tie-break.
5. **Screener-side oddities seen:** one column per company can be a restated or mislabelled one (the NMDC Q4FY25
   consolidated column was already caught in `screener_fill.py`); EPS restates for splits and bonus; a Q4 EPS can be
   the year's; the SunPharma standalone page shows Sales 45 to 63% below the unlabelled memory figures, which are probably
   consolidated (so the miss belongs to the label gap, not to screener).
6. **Already mapped in the repo** (`screener_fill.py`, `screener_crosscheck.py`): Sales to `revenue` (lender: Revenue to
   `interest_earned`), Net Profit to `pat`, EPS to `eps`; classes naming, lender definition, steady line difference. This
   study adds: Expenses, Operating Profit, OPM, Other Income, Interest, Depreciation, PBT, Tax %, balance sheet, cash
   flow, ratios, shareholding; and corrects two points: for NBFCs Revenue is `revenue`, not `interest_earned` (0 of 18);
   for every lender it is `total_income` − `other_income` (66 of 66).

## 3. What to use screener for

**Safe as a second witness, with the mapping** (agreement of 94% or better, a plain rule):

| Screener line | Mapping | Agreement |
| --- | --- | --- |
| Net Profit (companies) | = `pat` (profit including minority) | 97% Q, 96% A |
| Net Profit (standalone banks, NBFCs, insurers) | = `pat` | standalone banks 24/24; NBFC 18/18; insurers 14/14 |
| EPS (insurers; same-date companies without split or bonus) | = `eps` | insurers 14/14; companies 77% (drops at a split) |
| Revenue (banks) | = `interest_earned`; (NBFC) = `revenue`; (all lenders) = `total_income` − `other_income` | 100%, 100%, 100% |
| Interest (banks, NBFCs) | = `interest_expended` / `finance_cost` | 100% |
| Gross NPA %, Net NPA % (standalone banks) | = `gnpa_pct`, `nnpa_pct` | 100% |
| Promoters, FIIs (shareholding) | = `promoter_pct`, `fii_pct` | 100%, 99% |
| Equity Capital, Reserves, Deposits | = `equity_capital_cr`, `reserves_cr`, `deposits_cr` | 99%, 97%, 100% |
| Interest, Depreciation (companies) | equal | 93%, 92% |
| Cash from Operating and Financing Activity (companies) | equal | 92%, 95% |

**Close, but only with a stated derivation (definition-different; the name is the trap).**

- Sales: `revenue` except for excise payers (ITC, RELIANCE, HINDUNILVR, ONGC, MARUTI). 85%.
- Operating Profit, OPM %: screener's own line; our `ebitda` is the nearest, 88 to 91%. Different formulas, same name
  family. A card must say which.
- Profit before tax: `pbt` + `share_associates`. 87% Q.
- Tax %: `tax_expense` / (`pbt` + `share_associates`). 91%.
- Expenses: `total_expenses` − `finance_cost` − `depreciation`. 83%.
- Other Income: a plug that includes exceptional items; `other_income` + `exceptional_items` + `share_associates`. 78% Q.
- Net Profit (consolidated bank): screener is after the associates' share; ours is not. 77%.
- DIIs: screener DIIs + Government = `dii_pct`. 85%.
- Total Liabilities = our `total_assets_cr`, not our `total_liabilities_cr`.
- Debtor, Inventory and Payable Days: rebuildable from memory (90/97, 45/52, 43/52).

**Unusable** (no equal, or a different thing):

- Insurers: Sales, Expenses, Operating Profit, OPM, PBT, Tax % (0 to 12% agreement).
- Financing Profit and Financing Margin % (a screener plug, not our pre-provision profit).
- Borrowings (screener includes leases), Fixed Assets, Other Liabilities, Other Assets (0 to 16%).
- Free Cash Flow, Cash from Investing Activity (general: 62%; lenders: 21%).
- No. of Shareholders (a different count), Government, Public, Others (not in memory).
- EPS across a split or bonus date, and any Q4 column showing a year's EPS.
- ROCE and ROE (screener's own average, a one-point gap), CFO/EBITDA (needs tax paid).
- Dividend Payout %, Working Capital Days, Market Cap, Price, Book Value, P/E, Compounded Growth (not testable here).

## 4. Open questions for the owner

1. When a card is tested against screener, may the test treat only section 3's "safe" table as the second witness, and
   report the "derived" lines but never fail a card on them?
2. Net Profit: should a card call screener's Net Profit "profit including minority"? Our card uses "Net profit" for
   `pat` and "profit to shareholders" for `pat_owners`.
3. Should we spend one run to open screener's expandable schedules (Sales, Other Income, Expenses, Borrowings) on a few
   companies? That would settle the excise, exceptional-item and lease questions. Needs your OK (a second call per line).
4. May I run the label job (F150) first? The 3,651 unlabelled exchange figures block a clean standalone test.
5. ITC, RELIANCE, ONGC and MARUTI: do you want the excise (and other levy) line kept in memory (`excise_duty`), so Sales
   can be compared exactly?
6. Insurers: do you want any insurer figure other than profit and EPS compared, and if yes against which official
   account (revenue account or the shareholders' account)?
