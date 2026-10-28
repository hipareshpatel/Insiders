# Screener against NSE's XBRL and our memory: fifty companies (28 Oct 2026)

Owner's goal (28 Oct 2026): scale the five-company study (`docs/audit/screener-five-2026-10-28.md`) to 50 large companies, with the same method, and name every reason our numbers and screener's differ. Read-only investigation; no pipeline code changed. Basis: consolidated.

**Status: partly done. The NSE downloads stopped early on the first non-XML answer (section 4), so 42 of the 50 companies have complete or near-complete files, 7 have partial files and DLF has none.** The comparison below uses every file that was saved; nothing was retried around the stop. The lead decides whether the remaining files are fetched.

## 1. The short answer, in plain English

- **How often screener and the XBRL file agree (all 50, 3,758 figure pairs).** "Agree" means the same within ₹1 Cr (exact), or after one named rule from section 6 (explained).

| Statement | Pairs | Agree (exact or by a named rule) | Exact alone |
|---|---:|---:|---:|
| Quarterly profit and loss, 6 quarters | 2,530 | **95.5%** | 66.8% |
| FY26 profit and loss | 440 | **81.1%** | 55.0% |
| Balance sheet, Mar 2026 and Sep 2026 | 620 | **86.0%** | 47.1% |
| Cash flow FY26 | 168 | **95.8%** | 77.4% |

- **Everything together: 2,355 exact (62.7%), 1,111 explained by a named rule (29.6%), 292 unexplained (7.8%).** The five-company study had 63.8%, 32.8% and 3.4%. The unexplained share is higher because 50 companies bring more cases of screener's own restating, more annual-report classification differences and the lenders.
- **Top reasons for disagreement (292 unexplained pairs).** (1) The annual column on screener is built from the annual report: 67 pairs where profit before tax and net profit agree and only the split between sales, expenses, other income and interest differs; screener's year is not the sum of its own four quarters for 22 of 39 companies. (2) Screener shows old quarters restated for a demerger (Hindustan Unilever, Vedanta): 45 pairs. (3) Balance sheet: 87 pairs, of which 24 are lines where screener counts a lease, a preference-share or a buyers' credit amount as borrowing that the file does not tag as borrowing (10 non-lender companies), 39 are the five banks, three insurers and Bajaj Finserv whose printed statements group reserves, other liabilities and fixed assets differently, and the rest are small totals (deferred-tax netting at four public-sector companies) and single member lines. (4) Screener's EPS uses its own share count or a later bonus or split: 30 pairs. (5) Another 29 pairs are reclassifications inside one quarter (profit before tax equal). Section 9 lists every one.
- **New named rules found in this study** (they explain 1,111 pairs together with the five-company rules): associates' loss goes to Expenses and a gain to Other Income (P4); regulatory-deferral gain or loss the same way (P9); a "loss from investments" member of other expenses is netted in Other Income (P11); profit from discontinued operations goes to Other Income (P12); Tax % is tax divided by the size of profit before tax (P8); the half-year balance sheet puts intangible assets under development in Fixed Assets, the March one in CWIP (B3/B4); the March balance sheet follows either the quarterly file or the annual-report file; the annual cash flow follows the annual-report file (24 of 24 companies that have one, 96 of 96 pairs).
- **Our memory is right for the figures it holds, with 24 exceptions in 21,300 checks (section 2).** The exceptions are the pipeline reader picking the continuing-operations EPS for Hindustan Unilever and Vedanta, memory's FY26 revenue and EBITDA for Vedanta on another base (174,075 against 78,437), profit before tax for Maruti and Bajaj Auto Q2FY27 that includes the associates' share, and SBI Life H1FY27 profit (1,270 against 1,274.17). Memory holds no entry at all for whole quarters of 21 of the 42 companies checked (15 of them miss three or more periods).
- **The associates rule (P4) is a per-company switch.** 30 companies count the associates' share (profit in Other Income, loss in Expenses), 6 do not (Reliance, Tata Consumer, Cipla, Adani Enterprises, BEL, Shriram Finance), plus L&T and Sun Pharma from the five-company study. No pattern in the size, the sign, the sector or the file explains the split (section 7).
- **A filing quirk worth knowing:** HDFC Bank's XBRL puts its minority-interest profit into the "ExceptionalItems" element in 3 of 6 quarters (Q2FY26, Q4FY26, Q2FY27). The Q4FY26 file's own note says minority interest is 723.46 Cr, the same number as the exceptional item (-723.46). Screener's profit before tax and net profit agree with each other and with that note; the file's are lower by that amount.

## 2. Where our memory differs from the XBRL files (our own errors, listed first)

Memory against raw XBRL, read only, both bases, every period we hold a file for: **corporates and NBFCs 17,143 profit and loss checks and 2,881 balance-sheet checks; banks and insurers 1,282 checks. 24 differ (and one more is a rounding case) and 2 balance-sheet figures are missing.** Memory rounds to 2 decimals; a difference is more than 0.011.

| Company | Basis | Period | Field | Memory | XBRL | Reading |
|---|---|---|---|---:|---:|---|
| HINDUNILVR | cons | 9MFY26 | eps | 32.49 | 51.28 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| HINDUNILVR | cons | Q3FY26 | eps | 9.03 | 28.12 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| HINDUNILVR | cons | FY26 | eps | 45.25 | 64.01 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| HINDUNILVR | cons | Q4FY26 | eps | 12.76 | 12.73 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| HINDUNILVR | std | 9MFY26 | eps | 34.4 | 53.19 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| HINDUNILVR | std | Q3FY26 | eps | 11.02 | 30.11 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| HINDUNILVR | std | FY26 | eps | 46.9 | 65.66 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| HINDUNILVR | std | Q4FY26 | eps | 12.5 | 12.47 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| MARUTI | cons | H1FY27 | pbt | 7,660.3 | 7,493.6 | memory PBT includes the associates share (equals XBRL + share) |
| MARUTI | cons | Q2FY27 | pbt | 3,219.1 | 3,150.1 | memory PBT includes the associates share (equals XBRL + share) |
| BAJAJ-AUTO | cons | H1FY27 | pbt | 9,033.18 | 8,996.16 | memory PBT includes the associates share (equals XBRL + share) |
| BAJAJ-AUTO | cons | Q2FY27 | pbt | 4,609.77 | 4,569.32 | memory PBT includes the associates share (equals XBRL + share) |
| VEDL | cons | 9MFY26 | eps | 7.03 | 27.38 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| VEDL | cons | Q3FY26 | eps | 5.45 | 14.62 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| VEDL | cons | FY26 | revenue | 174,075.0 | 78,437.0 | memory FY26 is a different base from the Q4 file 12-month figure |
| VEDL | cons | FY26 | ebitda | 55,976.0 | 23,184.0 | same base difference as revenue |
| VEDL | cons | Q4FY26 | eps | 5.95 | 17.15 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| VEDL | cons | Q1FY27 | eps | 7.95 | 14.02 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| VEDL | std | 9MFY26 | eps | 10.23 | 27.73 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| VEDL | std | Q3FY26 | eps | 0.07 | 7.43 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| VEDL | std | FY26 | eps | 15.93 | 45.34 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| VEDL | std | Q4FY26 | eps | 5.63 | 17.6 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |
| VEDL | std | Q1FY27 | eps | 6.49 | 11.21 | memory holds the continuing-operations EPS; the file also tags an all-operations EPS |

Reading the list:

1. **EPS, 17 rows (Hindustan Unilever and Vedanta, consolidated and standalone).** Memory's `eps` is the continuing-operations EPS where the file also tags an all-operations EPS; the pipeline's own reader returns the same numbers, so the reader is the source. Memory's `eps_total` equals the file. Hindustan Unilever Q3FY26: memory 9.03, all-operations EPS 28.12 (the ice-cream gain).
2. **Maruti Q2FY27 and Bajaj Auto Q2FY27 profit before tax (and the H1FY27 sums): memory is higher than the XBRL by exactly the associates' share** (Maruti 69.0, Bajaj Auto 40.5). The pipeline reader gives the XBRL value, so memory took these from another source (assumption: the printed result, where profit before tax is shown after the associates). Both are Q2FY27 filings of 24 to 27 Oct 2026.
3. **Vedanta FY26 revenue 174,075 and EBITDA 55,976 in memory against 78,437 and 23,184 in the Q4FY26 file's 12-month context.** Different bases (assumption: the original FY26 totals before the demerger against restated continuing operations). Screener's FY26 Vedanta Sales is not equal to either; see section 9.
4. **SBI Life H1FY27 profit: memory 1,270.0, XBRL 1,274.17.**
5. Cipla Q2FY27 EBITDA margin 18.7 against 18.744 is rounding, not a difference.

**Memory has no entry** (a coverage gap, not an error) for whole periods that the XBRL has: Cipla (all periods and the Q2FY27 balance sheet), Shriram Finance (10 consolidated periods), Maruti, BPCL, Bharti Airtel, Titan, Eicher Motors, Bajaj Auto, Power Grid, Tata Power, GAIL (8 to 10 periods each), Nestle India, Hindalco (7), Bajaj Finance (5), Adani Ports (3), and one or two periods each for Bajaj Finserv, HCL Tech, Tech Mahindra, Vedanta, Adani Enterprises standalone, IndiGo. For lenders memory has no gross premium, net premium and similar fields for HDFC Life and LICI. How often memory's figure equals screener's (corporates, quarterly, by definition, as in the five-company study): Sales 181 of 212, Operating Profit 132 of 211, Other Income 49 of 210, Profit before tax 64 of 211, Net Profit 209 of 212, Depreciation 205 of 210, Interest 198 of 210, Expenses 0 of 210 (memory includes interest and depreciation), EPS 112 of 210.

## 3. The 50 companies and their industries

Chosen from the NIFTY 50 and the NIFTY Next 50, excluding TCS, Sun Pharma, L&T, Tata Steel and ITC, with large names added for industries the Nifty barely covers (power, coal, gas, cement, real estate, defence, aviation). Lenders are listed at the end of each block and are reported separately everywhere. Siemens, ABB India and Tata Motors were left out on purpose, to avoid a different financial year or a recently restructured company (assumption about their year-ends; not checked).

"Pairs" in the last column are exact / explained / unexplained over every statement for that company. "FY26 source" is the document used for the FY26 profit and loss pairs: the annual-report XBRL where NSE lists one, otherwise the Q4FY26 results file. Banks, NBFCs and insurers have no annual-report XBRL listed by NSE (not found by `annual_reports` on 28 Oct 2026); neither do HCL Tech, Tata Power, BPCL, GAIL, Coal India and Apollo Hospitals. Every annual-report row NSE returned was report type IND-AS; no BRSR row came back.

| # | Symbol | Company | Industry | Kind | NSE files (quarterly + annual report) | FY26 source | Screener latest quarter | Pairs: exact / explained / unexplained |
|---|---|---|---|---|---|---|---|---|
| 1 | RELIANCE | Reliance Industries | Conglomerate: oil refining, retail, telecom | company | 10 + 2 | annual report | Jun 2026 | 58 / 16 / 6 |
| 2 | HDFCBANK | HDFC Bank | Bank (private) | bank | 12 + 0 | Q4 file | Sep 2026 | 80 / 15 / 8 |
| 3 | ICICIBANK | ICICI Bank | Bank (private) | bank | 12 + 0 | Q4 file | Sep 2026 | 80 / 13 / 10 |
| 4 | SBIN | State Bank of India | Bank (public sector) | bank | 10 + 0 | Q4 file | Jun 2026 | 56 / 12 / 13 |
| 5 | AXISBANK | Axis Bank | Bank (private) | bank | 12 + 0 | Q4 file | Sep 2026 | 81 / 13 / 9 |
| 6 | KOTAKBANK | Kotak Mahindra Bank | Bank (private) | bank | 12 + 0 | Q4 file | Sep 2026 | 81 / 10 / 12 |
| 7 | BAJFINANCE | Bajaj Finance | NBFC (consumer finance) | NBFC | 12 + 0 | Q4 file | Sep 2026 | 74 / 18 / 9 |
| 8 | BAJAJFINSV | Bajaj Finserv | NBFC / insurance holding | NBFC holding | 10 + 0 | Q4 file | Jun 2026 | 48 / 19 / 13 |
| 9 | SHRIRAMFIN | Shriram Finance | NBFC (vehicle finance) | NBFC | 12 + 0 | Q4 file | Sep 2026 | 86 / 9 / 6 |
| 10 | SBILIFE | SBI Life Insurance | Insurer (life) | insurer | 6 + 0 | none | no table | 0 / 0 / 0 |
| 11 | HDFCLIFE | HDFC Life Insurance | Insurer (life) | insurer | 12 + 0 | Q4 file | Sep 2026 | 17 / 23 / 2 |
| 12 | LICI | Life Insurance Corporation | Insurer (life, public sector) | insurer | 10 + 0 | Q4 file | Jun 2026 | 10 / 12 / 9 |
| 13 | INFY | Infosys | IT services | company | 12 + 1 | annual report | Sep 2026 | 74 / 27 / 0 |
| 14 | HCLTECH | HCL Technologies | IT services | company | 12 + 0 | Q4 file | Sep 2026 | 70 / 31 / 0 |
| 15 | WIPRO | Wipro | IT services | company | 12 + 2 | annual report | Sep 2026 | 67 / 34 / 0 |
| 16 | TECHM | Tech Mahindra | IT services | company | 12 + 2 | annual report | Sep 2026 | 71 / 19 / 11 |
| 17 | BHARTIARTL | Bharti Airtel | Telecom | company | 10 + 2 | annual report | Jun 2026 | 44 / 31 / 5 |
| 18 | HINDUNILVR | Hindustan Unilever | FMCG | company | 10 + 2 | annual report | Sep 2026 | 41 / 24 / 15 |
| 19 | NESTLEIND | Nestle India | FMCG (food) | company | 12 + 2 | annual report | Sep 2026 | 65 / 30 / 6 |
| 20 | TATACONSUM | Tata Consumer Products | FMCG (food and beverages) | company | 12 + 2 | annual report | Sep 2026 | 76 / 25 / 0 |
| 21 | TITAN | Titan Company | Consumer (jewellery, watches) | company | 10 + 2 | annual report | Jun 2026 | 59 / 16 / 5 |
| 22 | ASIANPAINT | Asian Paints | Paints | company | 10 + 2 | annual report | Jun 2026 | 49 / 26 / 5 |
| 23 | PIDILITIND | Pidilite Industries | Chemicals (adhesives) | company | 10 + 2 | annual report | Jun 2026 | 57 / 19 / 4 |
| 24 | MARUTI | Maruti Suzuki | Auto (cars) | company | 12 + 2 | annual report | Sep 2026 | 68 / 30 / 3 |
| 25 | M&M | Mahindra and Mahindra | Auto (utility vehicles, tractors) | company | 10 + 2 | annual report | Jun 2026 | 34 / 38 / 8 |
| 26 | EICHERMOT | Eicher Motors | Auto (motorcycles) | company | 10 + 2 | annual report | Jun 2026 | 49 / 28 / 3 |
| 27 | BAJAJ-AUTO | Bajaj Auto | Auto (two and three wheelers) | company | 12 + 2 | annual report | Sep 2026 | 59 / 35 / 7 |
| 28 | NTPC | NTPC | Power generation | company | 10 + 2 | annual report | Jun 2026 | 43 / 28 / 9 |
| 29 | POWERGRID | Power Grid Corporation | Power transmission | company | 10 + 2 | annual report | Jun 2026 | 37 / 39 / 4 |
| 30 | TATAPOWER | Tata Power | Power (generation and distribution) | company | 10 + 0 | Q4 file | Jun 2026 | 43 / 31 / 6 |
| 31 | ONGC | Oil and Natural Gas Corporation | Oil and gas (exploration) | company | 10 + 2 | annual report | Jun 2026 | 43 / 26 / 11 |
| 32 | BPCL | Bharat Petroleum | Oil refining and marketing | company | 12 + 0 | Q4 file | Sep 2026 | 42 / 59 / 0 |
| 33 | GAIL | GAIL (India) | Gas transmission and trading | company | 10 + 0 | Q4 file | Jun 2026 | 41 / 31 / 8 |
| 34 | COALINDIA | Coal India | Coal mining | company | 10 + 0 | Q4 file | Jun 2026 | 43 / 21 / 16 |
| 35 | VEDL | Vedanta | Metals and mining (diversified) | company | 10 + 2 | annual report | Jun 2026 | 28 / 20 / 32 |
| 36 | ULTRACEMCO | UltraTech Cement | Cement | company | 12 + 2 | annual report | Sep 2026 | 56 / 41 / 4 |
| 37 | GRASIM | Grasim Industries | Cement, chemicals, textiles | company | 10 + 2 | annual report | Jun 2026 | 28 / 42 / 10 |
| 38 | JSWSTEEL | JSW Steel | Steel | company | 12 + 2 | annual report | Sep 2026 | 52 / 46 / 3 |
| 39 | HINDALCO | Hindalco Industries | Aluminium and copper | company | 10 + 2 | annual report | Jun 2026 | 45 / 33 / 2 |
| 40 | CIPLA | Cipla | Pharma | company | 12 + 1 | Q4 file | Sep 2026 | 78 / 23 / 0 |
| 41 | DRREDDY | Dr. Reddy's Laboratories | Pharma | company | 12 + 2 | annual report | Sep 2026 | 64 / 37 / 0 |
| 42 | APOLLOHOSP | Apollo Hospitals | Hospitals and pharmacy | company | 10 + 0 | Q4 file | Jun 2026 | 49 / 26 / 5 |
| 43 | ADANIPORTS | Adani Ports and SEZ | Ports and logistics | company | 7 + 0 | Q4 file | Jun 2026 | 38 / 22 / 9 |
| 44 | ADANIENT | Adani Enterprises | Conglomerate (trading, airports, mining) | company | 3 + 0 | none | Jun 2026 | 17 / 3 / 2 |
| 45 | INDIGO | InterGlobe Aviation (IndiGo) | Airline | company | 4 + 0 | none | Jun 2026 | 20 / 2 / 0 |
| 46 | TRENT | Trent | Retail (apparel) | company | 4 + 0 | none | Jun 2026 | 14 / 6 / 2 |
| 47 | DMART | Avenue Supermarts (DMart) | Retail (supermarkets) | company | 2 + 0 | none | Sep 2026 | 10 / 1 / 0 |
| 48 | BEL | Bharat Electronics | Defence electronics | company | 1 + 0 | none | Jun 2026 | 10 / 1 / 0 |
| 49 | HAL | Hindustan Aeronautics | Defence aerospace | company | 0 + 0 | none | Jun 2026 | 0 / 0 / 0 |
| 50 | DLF | DLF | Real estate | company | 0 + 0 | none | Sep 2026 | 0 / 0 / 0 |

Screener: one page per company, `/company/<SYMBOL>/consolidated/`, all 50 answered with HTTP 200 and each one matched the consolidated file where we hold one; no company needed the standalone page. SBI Life's page has empty tables (screener shows no results for it), so SBI Life has no screener pairs. Bajaj Finserv, HDFC Life and LICI are shown by screener in the ordinary "Sales" layout, not the lender layout.

## 4. Run facts

- **NSE, with 8 parallel threads** (the owner's second message of 28 Oct): each thread had its own `NseClient()` with the client as written (its 3 to 5 second pause per client unchanged; no pause override). One thread worked on one company at a time: `integrated_filings`, then `annual_reports`, then the file downloads. Started 11:28 IST, finished 11:34 IST (05:58:37 to 06:04:26 UTC), **349 seconds**.
- **Files saved: 525** (477 quarterly results files, consolidated and standalone, and 48 annual-report files), 497 MB. **List calls: 98** (49 companies, two each). That is 623 calls in 349 seconds, 0.56 seconds a call. The five-company run did one call at a time: 59 calls in 254 seconds, 4.3 seconds a call. **About 7.7 times faster per call.** The 8 threads took the whole 49-company job in about the time the serial run took for five.
- **No HTTP 403 or 429 was seen.** The run stopped because my own guard, which stops every thread on any answer that is not XML, fired at 345 seconds: `download()` returned nothing for **CIPLA's consolidated annual-report file** (`AR_XBRL_CIPLA_09082026014930.xml`; the client returns nothing for a body that does not start like XML or one over its size limit, and does not show which). Three seconds later another thread's file was over the client's 8 MB default limit (**ADANIPORTS standalone Q4FY26**, the client logged "XBRL file over 8000000 bytes"), which is a large real file and not a refusal. That second event also set the stop flag. Every other request in the run, including requests in flight after 345 seconds, was answered normally, which points to an odd file and not a challenge page. **That is an inference, not a measurement:** I tried one diagnostic read of the CIPLA URL to see the body and the permission check refused it, so I did not look and did not retry. Nothing was fetched after the stop.
- **One listed file does not exist:** ADANIENT's standalone Q2FY26 file (filed 4 Nov 2025, `INTEGRATED_FILING_INDAS_1565339_04112025110514_WEB.xml`) answered HTTP 404 (listed by `integrated_filings`, not served). That 404 ended the thread's work on ADANIENT, so its other files were never tried.
- **Not downloaded (64 listed files, plus DLF):** quarterly files 51 (ADANIPORTS 3, ADANIENT 7, INDIGO 6, TRENT 6, DMART 10, BEL 9, HAL 10), annual-report files 13 (CIPLA consolidated, and two each for ADANIPORTS, INDIGO, TRENT, DMART, BEL, HAL). DLF: neither list call was made, so its files are unknown. HAL has no file at all. Those eight companies are compared only where a file exists, so their pair counts are small (the company table shows them).
- **Screener:** 50 pages, 5 seconds apart, plain browser User-Agent, one at a time, 05:58:20 to 06:03:52 UTC (11:28 to 11:34 IST), all HTTP 200; `/company/source/` was not opened; the hidden-row API was not called.
- **Memory:** 50 read-only `GET /api/companies/<SYMBOL>` calls, all 200.
- **Screener's Sep 2026 column** exists for Hindustan Unilever, but NSE's `integrated_filings('HINDUNILVR')` returned no 2026-09-30 row on 28 Oct 2026 (not found by that call on that date); screener has the quarter and its balance sheet.

## 5. Totals: exact, explained, unexplained

Pair = one screener figure against our XBRL value by the formula (whole crore, as screener's page shows; percent rows within 0.51 point; EPS within 0.015). Verdicts as in the five-company study: **exact** is the plain XBRL element within ₹1 Cr, **explained** is within 1.5 Cr only after a named rule, **unexplained** is neither. Each pair is counted once: FY26 uses the annual-report file where listed (24 companies) and the Q4FY26 file otherwise; the March balance sheet counts the better of its two documents. The full list of 4,358 pairs (including the pairs that were counted only as a second view) is in the scratchpad file `fifty/all_pairs.csv`.

| Statement | Pairs | Exact | Explained by a named rule | Unexplained |
|---|---:|---:|---:|---:|
| **Companies other than lenders** | | | | |
| Quarterly profit and loss (6 quarters) | 1,980 | 1,267 (64.0%) | 620 (31.3%) | 93 (4.7%) |
| FY26 profit and loss | 352 | 206 (58.5%) | 90 (25.6%) | 56 (15.9%) |
| Balance sheet (Mar 2026, Sep 2026) | 450 | 168 (37.3%) | 234 (52.0%) | 48 (10.7%) |
| Cash flow FY26 | 128 | 101 (78.9%) | 23 (18.0%) | 4 (3.1%) |
| **All statements** | 2,910 | 1,742 (59.9%) | 967 (33.2%) | 201 (6.9%) |
| **Lenders (banks, NBFCs, insurers)** | | | | |
| Quarterly profit and loss (6 quarters) | 550 | 424 (77.1%) | 104 (18.9%) | 22 (4.0%) |
| FY26 profit and loss | 88 | 36 (40.9%) | 25 (28.4%) | 27 (30.7%) |
| Balance sheet (Mar 2026, Sep 2026) | 170 | 124 (72.9%) | 7 (4.1%) | 39 (22.9%) |
| Cash flow FY26 | 40 | 29 (72.5%) | 8 (20.0%) | 3 (7.5%) |
| **All statements** | 848 | 613 (72.3%) | 144 (17.0%) | 91 (10.7%) |
| **All 50** | | | | |
| Quarterly profit and loss (6 quarters) | 2,530 | 1,691 (66.8%) | 724 (28.6%) | 115 (4.5%) |
| FY26 profit and loss | 440 | 242 (55.0%) | 115 (26.1%) | 83 (18.9%) |
| Balance sheet (Mar 2026, Sep 2026) | 620 | 292 (47.1%) | 241 (38.9%) | 87 (14.0%) |
| Cash flow FY26 | 168 | 130 (77.4%) | 31 (18.5%) | 7 (4.2%) |
| **All statements** | 3,758 | 2,355 (62.7%) | 1,111 (29.6%) | 292 (7.8%) |

By industry (lenders last; all statements together):

| Industry group | Companies | Pairs | Exact | Explained | Unexplained |
|---|---:|---:|---:|---:|---:|
| Auto | 4 | 362 | 210 (58.0%) | 131 (36.2%) | 21 (5.8%) |
| Energy, power and mining (coal) | 8 | 661 | 350 (53.0%) | 251 (38.0%) | 60 (9.1%) |
| FMCG, consumer and retail | 7 | 475 | 314 (66.1%) | 128 (26.9%) | 33 (6.9%) |
| IT services | 4 | 404 | 282 (69.8%) | 111 (27.5%) | 11 (2.7%) |
| Lenders: NBFCs | 3 | 282 | 208 (73.8%) | 46 (16.3%) | 28 (9.9%) |
| Lenders: banks | 5 | 493 | 378 (76.7%) | 63 (12.8%) | 52 (10.5%) |
| Lenders: insurers | 3 | 73 | 27 (37.0%) | 35 (47.9%) | 11 (15.1%) |
| Metals, cement and chemicals | 6 | 522 | 266 (51.0%) | 201 (38.5%) | 55 (10.5%) |
| Pharma and healthcare | 3 | 282 | 191 (67.7%) | 86 (30.5%) | 5 (1.8%) |
| Ports, defence, aviation, real estate, conglomerate | 6 | 124 | 85 (68.5%) | 28 (22.6%) | 11 (8.9%) |
| Telecom | 1 | 80 | 44 (55.0%) | 31 (38.8%) | 5 (6.2%) |

How the unexplained 292 split by cause (section 9 has every pair): annual-report classification 67; restated by screener 45; reclassification inside a quarter 29; EPS share count 23 and EPS restated 7; bank depreciation 8; Coal India quarter 6; small gaps 7; no cause found 6 (that is 198 profit and loss pairs); balance sheet 87; cash flow 7.

## 6. The formulas and how often each holds

All amounts in crore (XBRL rupees divided by 10 million). Quarter = the 3-month context ending on the quarter end. The five-company rules P1, P2, P3, P5, P6, P7 (EPS), B0 to B6 and C1 are kept; the changes and additions are marked **new** or **changed**.

### 6.1 Companies other than lenders: profit and loss

Pairs are the 6 quarters of each company that have a file (37 of the 39 companies; HAL and DLF have none). "Holds in every period" counts a company only when every one of its pairs matches.

| Formula | Companies it applies to | Companies where it holds in every period | Pairs matched / tested | Fails for |
|---|---:|---:|---:|---|
| P1 Sales = revenue - excise | 3 | 3 | 16 / 16 | - |
| Sales (all quarters) | 37 | 32 | 171 / 180 | HINDUNILVR, NTPC, ONGC, COALINDIA, VEDL |
| P2 Interest = FinanceCosts + finance-cost member of OtherExpenses | 1 | 1 | 5 / 5 | - |
| Interest (all quarters) | 37 | 35 | 174 / 180 | HINDUNILVR, VEDL |
| Depreciation = DepreciationDepletionAndAmortisationExpense | 37 | 35 | 175 / 180 | HINDUNILVR, VEDL |
| P3 Exceptional items go to Other Income (and PBT) | 25 | 21 | 109 / 122 | HINDUNILVR, ONGC, VEDL, GRASIM |
| P4 Associates' share, counted (profit to Other Income, loss to Expenses) or left out, as the company's flag says | 34 | 27 | 413 / 435 | HINDUNILVR, NESTLEIND, TATAPOWER, ONGC, COALINDIA, VEDL, GRASIM |
| P9 Regulatory deferral: gain to Other Income, loss to Expenses | 3 | 2 | 43 / 45 | TATAPOWER |
| P11 "Loss from investments..." member netted in Other Income | 1 | 1 | 10 / 10 | - |
| P12 Discontinued operations (after tax) go to Other Income | 2 | 1 | 6 / 10 | VEDL |
| P5 Expenses (all rules together) | 37 | 29 | 169 / 180 | TECHM, HINDUNILVR, NESTLEIND, TATAPOWER, ONGC, COALINDIA, VEDL, GRASIM |
| Operating Profit = Sales - Expenses | 37 | 28 | 167 / 180 | TECHM, HINDUNILVR, NESTLEIND, NTPC, TATAPOWER, ONGC, COALINDIA, VEDL, GRASIM |
| OPM % = Operating Profit / Sales | 37 | 34 | 175 / 180 | HINDUNILVR, COALINDIA, VEDL |
| Other Income (all rules together) | 37 | 31 | 169 / 180 | HINDUNILVR, NESTLEIND, TATAPOWER, ONGC, VEDL, GRASIM |
| Profit before tax (all rules together) | 37 | 33 | 171 / 180 | HINDUNILVR, COALINDIA, VEDL, GRASIM |
| P8 Tax % = TaxExpense / abs(PBT) | 37 | 36 | 177 / 180 | VEDL |
| P6 Net Profit = ProfitLossForPeriod (whole profit) | 37 | 35 | 177 / 180 | COALINDIA, GRASIM |
| EPS (filed EPS, owners/shares, or screener share count within 3%) | 37 | 30 | 162 / 180 | TECHM, NESTLEIND, PIDILITIND, M&M, GRASIM, ADANIENT, TRENT |

The rules in words:

| Id | Rule |
|---|---|
| P1 | Sales = RevenueFromOperations minus excise duty. Excise is the OtherExpenses member "Excise Duty", or the plain element `ExciseDuty` where there is no member (**changed**: ONGC's annual-report file carries 53,584.6 in the element, equal to the FY26 Sales gap to the paisa). |
| P2 | Interest = FinanceCosts + the OtherExpenses member "Finance cost of financial services business ...". Only Grasim has such a member among the 37 (L&T in the five-company study). |
| P3 | Other Income = OtherIncome + ExceptionalItemsBeforeTax, any sign (TCS Q3FY26 in the five-company study; Bharti Airtel Q4FY26: exceptional -3,161 sits in Other Income). |
| P4 **new form** | The associates' share, **where counted**, goes into Other Income if it is a profit and into **Expenses** if it is a loss, and into profit before tax either way. HCL Tech Q2FY27: share -38, screener Expenses 28,181 = file 28,143 + 38. Nestle India Q1FY26: -12.6, same. Companies that do not count it are in section 7. |
| P5 | Expenses = Expenses - FinanceCosts - DepreciationDepletionAndAmortisationExpense - excise - P2 - P11, plus the losses of P4 and P9. |
| P6 | Net Profit = ProfitLossForPeriod, the whole profit including the minority share (unchanged; holds for 35 of 37 companies, Coal India and Grasim fail). |
| P8 **changed** | Tax % = TaxExpense divided by the **size** of profit before tax. For a loss the five-company formula gave the wrong sign: IndiGo Q2FY26 (tax +100.4 on a loss of 2,482) screener +4%; BPCL Q1FY27 (tax -1,343 on a loss of 3,216) screener -42%. |
| P9 **new** | NetMovementInRegulatoryDeferralAccountBalances...: a gain goes to Other Income, a loss to Expenses (NTPC, Power Grid, Tata Power). Power Grid Q4FY26: -3,763.1 in Expenses. |
| P11 **new** | The OtherExpenses member "Loss from investments related to subsidiaries, associates and joint ventures" is taken out of Expenses and netted in Other Income. Mahindra and Mahindra Q1FY26: member 184.7; screener Other Income 1,210 = 916.9 + 478.1 (associates) - 184.7. Only M&M has it. |
| P12 **new** | ProfitLossFromDiscontinuedOperationsAfterTax goes to Other Income and so to profit before tax. Hindustan Unilever Q3FY26: 139 + 4,485 - 576 (exceptional) = 4,048 = screener. |
| EPS | (a) the filed basic EPS (EPS in the Ind AS taxonomy); (b) owners' profit divided by (PaidUpValueOfEquityShareCapital / FaceValueOfEquityShareCapital), which fits 25 pairs that (a) misses; (c) within 3% of the filed EPS (screener's own share count), 25 pairs. Of 180 quarterly EPS pairs: 102 exact, 60 explained, 18 not. |

**FY26 profit and loss.** The same formulas run on the 12-month figures. For the 24 companies with an annual-report file, 155 exact, 70 explained, 39 unexplained on the annual-report file, against 149, 71 and 44 on the Q4FY26 file's 12-month context for the same companies: screener's year follows the annual report slightly more than it follows the quarterly file, and neither explains the balanced reclassifications in section 9. Annual-report files list their element names the same way as the results files; two of them (Infosys, Tata Consumer) carry dates with line breaks inside the date tag, which my reader strips.

### 6.2 Companies other than lenders: balance sheet and cash flow

Balance sheet: Mar 2026 from the Q4FY26 file or the annual-report file (the better of the two), Sep 2026 from the Q2FY27 file where screener shows it and NSE lists it (13 companies). **Cash flow FY26 follows the annual-report file: 96 of 96 pairs agree for the 24 companies that have one; the Q4FY26 file alone leaves 5 pairs out (Hindustan Unilever, Power Grid).**

| Formula | Companies it applies to | Companies where it holds in every period | Pairs matched / tested | Fails for |
|---|---:|---:|---:|---|
| B0 Equity Capital = EquityShareCapital | 32 | 32 | 45 / 45 | - |
| B0 Reserves = OtherEquity | 32 | 31 | 44 / 45 | ADANIPORTS |
| B1 Borrowings = BorrowingsNoncurrent + BorrowingsCurrent + lease members | 32 | 22 | 33 / 45 | RELIANCE, NESTLEIND, TITAN, ASIANPAINT, M&M, BAJAJ-AUTO, VEDL, ULTRACEMCO, HINDALCO, ADANIPORTS |
| B6 Other Liabilities = Total - Equity - Reserves - Borrowings | 32 | 18 | 29 / 45 | RELIANCE, NESTLEIND, TITAN, ASIANPAINT, M&M, BAJAJ-AUTO, NTPC, ONGC, GAIL, COALINDIA, VEDL, ULTRACEMCO, HINDALCO, ADANIPORTS |
| B2 Total = Assets - min(DeferredTaxAssetsNet, DeferredTaxLiabilitiesNet) in March; Assets in Sep | 32 | 28 | 82 / 90 | NTPC, ONGC, GAIL, COALINDIA |
| B3 Fixed Assets = PPE + investment property + goodwill + intangibles + right-of-use (+ IAUD in Sep) | 32 | 30 | 43 / 45 | TECHM, COALINDIA |
| B4 CWIP = CapitalWorkInProgress (+ IAUD in March) | 32 | 31 | 44 / 45 | COALINDIA |
| B5 Investments = equity-method + non-current + current | 32 | 30 | 43 / 45 | GAIL, GRASIM |
| B6 Other Assets = Total - FA - CWIP - Investments | 32 | 26 | 39 / 45 | TECHM, NTPC, ONGC, GAIL, COALINDIA, GRASIM |
| Operating = CashFlowsFromUsedInOperatingActivities | 32 | 32 | 32 / 32 | - |
| C1 Investing = investing + EffectOfExchangeRateChanges | 32 | 30 | 30 / 32 | APOLLOHOSP, ADANIPORTS |
| Financing = CashFlowsFromUsedInFinancingActivities | 32 | 32 | 32 / 32 | - |
| Net = IncreaseDecreaseInCashAndCashEquivalents | 32 | 30 | 30 / 32 | APOLLOHOSP, ADANIPORTS |

New and changed balance-sheet rules:

- **B1 changed:** Borrowings = BorrowingsNoncurrent + BorrowingsCurrent + the "Lease liabilities" members. Where the file has no lease member, or screener also counts a preference share or a buyers' credit member, it fails (section 9).
- **B3/B4 changed:** In the half-year column IntangibleAssetsUnderDevelopment goes into **Fixed Assets**, and CWIP is CapitalWorkInProgress only; in the March column it is the other way round (eight half-year Fixed Assets pairs - HCL Tech 107, Tata Consumer 37, Maruti 522, Bajaj Auto 1,561, BPCL 19,726, UltraTech 486, Cipla 603, JSW Steel 602 - each equal the element to 0.5 Cr; the five-company L&T Sep 2026 gap of 778 moved from CWIP to Fixed Assets is the same rule).
- **B3 changed:** the right-of-use assets are found as a member of either OtherNoncurrentAssets or OtherNoncurrentFinancialAssets (JSW Steel Mar 2026: 4,922.0 under financial assets).
- **B2 unchanged in form:** Total = Assets - min(DeferredTaxAssetsNet, DeferredTaxLiabilitiesNet) in March, Assets in the half-year column. It holds for 28 of 32 companies; it fails for the four central public-sector companies NTPC, ONGC, GAIL and Coal India (all four are state-owned; whether that is the cause is an assumption).

### 6.3 Lenders

Screener lays out banks and two NBFCs (Bajaj Finance, Shriram Finance) in a lender layout: Revenue, Interest, Expenses, Financing Profit, Financing Margin %, Other Income, Depreciation, profit before tax, Tax %, Net Profit, EPS, gross and net NPA %. Bajaj Finserv, HDFC Life and LICI come in the ordinary layout; SBI Life has no table. The profit and loss rules follow.

**Banks (5 companies, banking taxonomy), quarterly:**

| Formula | Companies | Hold in every period | Pairs matched / tested | Fails for |
|---|---:|---:|---:|---|
| L1 Revenue = InterestEarned | 5 | 4 | 28 / 29 | SBIN |
| L2 Interest = InterestExpended | 5 | 4 | 28 / 29 | KOTAKBANK |
| L3 Expenses = OperatingExpenses + ProvisionsOtherThanTaxAndContingencies | 5 | 4 | 28 / 29 | KOTAKBANK |
| L4 Financing Profit = Revenue - Interest - Expenses | 5 | 4 | 28 / 29 | SBIN |
| Financing Margin % = Financing Profit / Revenue | 5 | 5 | 29 / 29 | - |
| L5 Other Income = OtherIncome (+ ExceptionalItems when not zero) | 5 | 4 | 28 / 29 | SBIN |
| L6 Profit before tax = Financing Profit + Other Income | 5 | 5 | 29 / 29 | - |
| L7 Tax % = TaxExpense / abs(PBT) | 5 | 5 | 29 / 29 | - |
| L8 Net Profit = PBT - TaxExpense + share of associates | 5 | 5 | 29 / 29 | - |
| EPS in Rs (filed basic EPS, or within 3%) | 5 | 2 | 25 / 29 | HDFCBANK, SBIN, KOTAKBANK |
| Depreciation (quarters: screener shows 0) | 5 | 5 | 29 / 29 | - |

L1 to L8 are new. L5: exceptional items are added to Other Income and PBT where they are real (SBI Q2FY26: +3,026.6; Kotak Q4FY26: +367.8). HDFC Bank's exceptional items are not (see the quirk in section 1), so for HDFC Bank profit before tax and net profit equal the file's plus that item. Depreciation is 0 on screener for every bank quarter; there is no such element. EPS: Kotak Q1 and Q2FY26 screener 4.50 and 4.49 against filed 22.49 (the 5:1 split, ratio 0.20) and HDFC Bank Q1FY26 10.60 against 21.23 (the 1:1 bonus).

**Banks, FY26 (Q4FY26 file's 12-month context; no annual-report file is listed for banks):**

| Formula | Companies | Hold in every period | Pairs matched / tested | Fails for |
|---|---:|---:|---:|---|
| L1 Revenue = InterestEarned | 5 | 5 | 5 / 5 | - |
| L2 Interest = InterestExpended | 5 | 5 | 5 / 5 | - |
| L3 Expenses = OperatingExpenses + ProvisionsOtherThanTaxAndContingencies | 5 | 4 | 4 / 5 | KOTAKBANK |
| L4 Financing Profit = Revenue - Interest - Expenses | 5 | 4 | 4 / 5 | KOTAKBANK |
| Financing Margin % = Financing Profit / Revenue | 5 | 5 | 5 / 5 | - |
| L5 Other Income = OtherIncome (+ ExceptionalItems when not zero) | 5 | 4 | 4 / 5 | KOTAKBANK |
| L6 Profit before tax = Financing Profit + Other Income | 5 | 5 | 5 / 5 | - |
| L7 Tax % = TaxExpense / abs(PBT) | 5 | 5 | 5 / 5 | - |
| L8 Net Profit = PBT - TaxExpense + share of associates | 5 | 5 | 5 / 5 | - |
| EPS in Rs (filed basic EPS, or within 3%) | 5 | 1 | 1 / 5 | HDFCBANK, ICICIBANK, SBIN, AXISBANK |
| Depreciation (quarters: screener shows 0) | 5 | 0 | 0 / 5 | HDFCBANK, ICICIBANK, SBIN, AXISBANK, KOTAKBANK |

**L9 (new):** in the annual column screener splits depreciation out of expenses: screener Expenses + Depreciation = XBRL operating expenses plus provisions to 1.5 Cr for HDFC (203,635 + 4,195 = 207,830), ICICI (142,971 + 3,061 = 146,032), SBI (278,781 + 4,830 = 283,611) and Axis (53,954 + 1,889 = 55,843). Kotak is 16 Cr off. The depreciation figure itself exists only in the annual report, so the Depreciation row cannot be rebuilt from the file.

**NBFCs and Bajaj Finserv (Ind AS Division III taxonomy), quarterly, then FY26:**

| Formula | Companies | Hold in every period | Pairs matched / tested | Fails for |
|---|---:|---:|---:|---|
| Revenue / Sales | 3 | 1 | 14 / 17 | BAJFINANCE, BAJAJFINSV |
| Interest | 3 | 3 | 17 / 17 | - |
| Expenses | 3 | 1 | 14 / 17 | BAJFINANCE, BAJAJFINSV |
| Financing Profit / Operating Profit | 3 | 3 | 17 / 17 | - |
| Other Income | 3 | 3 | 17 / 17 | - |
| Depreciation | 3 | 3 | 17 / 17 | - |
| Profit before tax | 3 | 3 | 17 / 17 | - |
| Tax % | 3 | 3 | 17 / 17 | - |
| Net Profit | 3 | 3 | 17 / 17 | - |
| EPS in Rs | 3 | 3 | 17 / 17 | - |

| Formula | Companies | Hold in every period | Pairs matched / tested | Fails for |
|---|---:|---:|---:|---|
| Revenue / Sales | 3 | 0 | 0 / 3 | BAJFINANCE, SHRIRAMFIN, BAJAJFINSV |
| Interest | 3 | 0 | 0 / 3 | BAJFINANCE, SHRIRAMFIN, BAJAJFINSV |
| Expenses | 3 | 0 | 0 / 3 | BAJFINANCE, SHRIRAMFIN, BAJAJFINSV |
| Financing Profit / Operating Profit | 3 | 0 | 0 / 3 | BAJFINANCE, SHRIRAMFIN, BAJAJFINSV |
| Other Income | 3 | 0 | 0 / 3 | BAJFINANCE, SHRIRAMFIN, BAJAJFINSV |
| Depreciation | 3 | 3 | 3 / 3 | - |
| Profit before tax | 3 | 3 | 3 / 3 | - |
| Tax % | 3 | 3 | 3 / 3 | - |
| Net Profit | 3 | 3 | 3 / 3 | - |
| EPS in Rs | 3 | 3 | 3 / 3 | - |

The corporate rules carry over (P3, P4, P5, P6, P8): Bajaj Finance Q4FY26 Other Income 11 = OtherIncome 0.71 + associates 10.21; Shriram Finance does not count its associates' share (6.23). The annual column on screener again differs from the file by balanced amounts (Interest, Expenses, Other Income) with equal profit before tax and net profit.

**Insurers (insurance taxonomy: HDFC Life and LICI):**

| Formula | Companies | Hold in every period | Pairs matched / tested | Fails for |
|---|---:|---:|---:|---|
| I1 Sales = NetPremiumIncome + IncomeFromInvestmentsNet + InvestmentIncome | 2 | 2 | 11 / 11 | - |
| I2 PBT = profit after tax + tax (ProvisionForTax + ProvisionsForTaxes) | 2 | 1 | 8 / 11 | LICI |
| Tax % | 2 | 2 | 11 / 11 | - |
| Net Profit = ProfitLossAfterTaxAndExtraordinaryItems | 2 | 1 | 8 / 11 | LICI |

Screener's insurer Expenses and Other Income cannot be rebuilt: a search over sums of up to four elements found no formula that holds for both companies. LICI's profit before tax and net profit disagree in Q1 to Q3FY26 (profit before tax by 1,087 to 1,674; the displayed Tax % is not consistent with the displayed profit before tax and net profit either), so screener's LICI quarters are not internally consistent for those three quarters.

**Lender balance sheets:**

| Formula | Companies | Hold in every period | Pairs matched / tested | Fails for |
|---|---:|---:|---:|---|
| Banks: Equity Capital = Capital | 5 | 4 | 7 / 9 | ICICIBANK |
| Banks: Reserves = ReservesAndSurplus | 5 | 0 | 3 / 9 | HDFCBANK, ICICIBANK, SBIN, AXISBANK, KOTAKBANK |
| Banks: Deposits = Deposits | 5 | 5 | 9 / 9 | - |
| Banks: Borrowing = Borrowings | 5 | 5 | 9 / 9 | - |
| Banks: Other Liabilities = OtherLiabilitiesAndProvisions | 5 | 0 | 3 / 9 | HDFCBANK, ICICIBANK, SBIN, AXISBANK, KOTAKBANK |
| Banks: Total = CapitalAndLiabilities | 5 | 3 | 14 / 18 | HDFCBANK, SBIN |
| Banks: Fixed Assets = FixedAssets | 5 | 1 | 5 / 9 | ICICIBANK, SBIN, AXISBANK, KOTAKBANK |
| Banks: Investments = Investments | 5 | 5 | 9 / 9 | - |

| Formula | Companies | Hold in every period | Pairs matched / tested | Fails for |
|---|---:|---:|---:|---|
| NBFCs: Borrowing = DebtSecurities + Borrowings + Deposits + SubordinatedLiabilities | 3 | 2 | 4 / 5 | BAJAJFINSV |
| NBFCs: Equity and Reserves | 3 | 3 | 10 / 10 | - |
| NBFCs: Fixed Assets and CWIP | 3 | 3 | 10 / 10 | - |
| NBFCs: Investments = Investments + equity-method | 3 | 3 | 5 / 5 | - |
| NBFCs: Total = Assets | 3 | 2 | 8 / 10 | BAJAJFINSV |

| Formula | Companies | Hold in every period | Pairs matched / tested | Fails for |
|---|---:|---:|---:|---|
| Insurers: Equity Capital = ShareCapital | 2 | 2 | 3 / 3 | - |
| Insurers: Borrowings | 2 | 2 | 3 / 3 | - |
| Insurers: Total = Assets + CurrentLiabilitiesAndProvisions | 2 | 2 | 6 / 6 | - |
| Insurers: Reserves = ReservesAndSurplus + fair-value change account | 2 | 1 | 2 / 3 | LICI |
| Insurers: Fixed Assets | 2 | 0 | 1 / 3 | HDFCLIFE, LICI |
| Insurers: Investments | 2 | 0 | 1 / 3 | HDFCLIFE, LICI |

Banks: screener's Reserves and Other Liabilities differ from the file for all five because the printed statements and the file group capital, ESOP outstanding, reserves and minority interest differently (the HDFC Bank file's own note says so); Fixed Assets differ because screener's number includes more than the file's FixedAssets line (assumption: intangibles, right-of-use assets and CWIP). Section 9 has every figure. NBFC rule: Borrowing = DebtSecurities + Borrowings + Deposits + SubordinatedLiabilities (Bajaj Finance Mar 2026: 193,131.9 + 170,642.5 + 68,532.8 + 2,805.3 = 435,112.5, screener 435,112). Insurer rule: Total = Assets + CurrentLiabilitiesAndProvisions (HDFC Life: 379,344.6 + 11,157.9 = 390,502.5, screener 390,502; the file's Assets is net of current liabilities).

**Lender cash flow (all ten lenders with a file):**

| Formula | Companies | Hold in every period | Pairs matched / tested | Fails for |
|---|---:|---:|---:|---|
| Operating = CashFlowsFromUsedInOperatingActivities | 10 | 9 | 9 / 10 | AXISBANK |
| Investing (+ exchange effect) | 10 | 9 | 9 / 10 | SHRIRAMFIN |
| Financing | 10 | 9 | 9 / 10 | AXISBANK |
| Net cash flow | 10 | 10 | 10 / 10 | - |

## 7. The associates rule: which companies count the associates' share

Test: for each quarter in which the share is not zero, does screener's Expenses, Other Income **and** profit before tax fit the XBRL with the share counted (a profit in Other Income, a loss in Expenses) or with it left out? The answer was the same in every quarter of a company: **30 count it, 6 do not.** From the five-company study: ITC and Tata Steel count it (as did BPCL), L&T and Sun Pharma do not, TCS has none. So of 41 companies with a non-zero share: 32 count it, 8 do not, 1 is unclear (Vedanta, one quarter of -1.0 that fits neither way).

Companies that do **not** count it: RELIANCE, SHRIRAMFIN, TATACONSUM, CIPLA, ADANIENT, BEL (and L&T and Sun Pharma).

| Company | Share of associates and JVs per quarter, Cr | Counted by screener? | Quarters that fit exactly one way (add only / none only / either / neither) |
|---|---|---|---|
| ADANIPORTS | +157.3, -210.2, +100.7, +209.8 | ADD | 4 / 0 / 0 / 0 |
| APOLLOHOSP | +13.6, +6.3, +14.9, +10.1, +13.4 | ADD | 5 / 0 / 0 / 0 |
| ASIANPAINT | +36.3, +38.3, +65.8, +25.2, +38.2 | ADD | 5 / 0 / 0 / 0 |
| BAJAJ-AUTO | -634.5, +1,195.2, -3.4, +40.5 | ADD | 4 / 0 / 0 / 0 |
| BAJAJFINSV | +0.6, +3.2, +1.7, +10.9, +5.1 | ADD | 3 / 0 / 1 / 1 |
| BAJFINANCE | +0.7, +3.3, +2.2, +10.2, +5.1, +3.7 | ADD | 3 / 0 / 1 / 2 |
| BHARTIARTL | +82.8, +81.0, +116.3, +84.4, +108.2 | ADD | 5 / 0 / 0 / 0 |
| BPCL | +1,158.1, +587.9, +207.6, -442.8, +401.1, +325.2 | ADD | 6 / 0 / 0 / 0 |
| COALINDIA | +144.2, +209.3, +288.8, +116.1, +240.3 | ADD | 4 / 0 / 0 / 1 |
| DRREDDY | +6.3, +2.3, +4.6, +0.8, -7.7 | ADD | 4 / 0 / 1 / 0 |
| EICHERMOT | +157.1, +134.9, +182.9, +322.9, +167.5 | ADD | 5 / 0 / 0 / 0 |
| GAIL | +421.6, +279.1, +345.3, +458.2, +342.7 | ADD | 5 / 0 / 0 / 0 |
| GRASIM | +68.7, +61.0, -56.4, +116.2, +26.1 | ADD | 3 / 0 / 0 / 2 |
| HCLTECH | -38.0 | ADD | 1 / 0 / 0 / 0 |
| HINDALCO | +2.0, +1.0, -3.0, -4.0, +6.0 | ADD | 4 / 0 / 1 / 0 |
| HINDUNILVR | -1.0, -3.0, -7.0, -4.0 | ADD | 2 / 0 / 0 / 2 |
| JSWSTEEL | -100.0, -88.0, -117.0, -170.0, -98.0, +292.0 | ADD | 6 / 0 / 0 / 0 |
| MARUTI | +35.5, +67.3, +85.4, +97.3, +97.7, +69.0 | ADD | 6 / 0 / 0 / 0 |
| M&M | +478.1, +469.2, +464.7, +552.8, +367.5 | ADD | 5 / 0 / 0 / 0 |
| NESTLEIND | -12.6, -10.0, -19.6, -3.2, -16.4, -17.2 | ADD | 5 / 0 / 0 / 1 |
| NTPC | +476.6, +580.1, +613.7, +1,193.7, +628.2 | ADD | 5 / 0 / 0 / 0 |
| ONGC | -227.9, +339.6, +97.2, +2,792.9, +597.9 | ADD | 3 / 0 / 0 / 2 |
| PIDILITIND | -2.0, +2.3 | ADD | 2 / 0 / 0 / 0 |
| POWERGRID | -44.4, -58.7, -46.2, +17.0, +2.3 | ADD | 5 / 0 / 0 / 0 |
| TATAPOWER | +129.6, +129.1, +198.7, +250.5, +241.4 | ADD | 4 / 0 / 0 / 1 |
| TECHM | +0.5, +0.9, -4.3 | ADD | 1 / 0 / 2 / 0 |
| TITAN | +1.0, +1.0, +2.0 | ADD | 1 / 0 / 2 / 0 |
| TRENT | +9.2, -1.1 | ADD | 1 / 0 / 1 / 0 |
| ULTRACEMCO | -4.3, -5.7, -4.5, -1.4, +1.4, -2.2 | ADD | 5 / 0 / 1 / 0 |
| WIPRO | +5.0, +15.2, +2.8, +2.7, -0.5, +8.6 | ADD | 5 / 0 / 1 / 0 |
| ADANIENT | +81.5, +17.9 | NONE | 0 / 2 / 0 / 0 |
| BEL | +8.4 | NONE | 0 / 1 / 0 / 0 |
| CIPLA | -7.6, -1.6, -5.0 | NONE | 0 / 3 / 0 / 0 |
| RELIANCE | +102.0, -54.0, +123.0, -27.0, +195.0 | NONE | 0 / 5 / 0 / 0 |
| SHRIRAMFIN | +4.2, +4.4, +5.7, +6.2, +5.5, +6.5 | NONE | 0 / 6 / 0 / 0 |
| TATACONSUM | -14.7, +9.5, -18.3, -67.2, -17.7, +2.9 | NONE | 0 / 6 / 0 / 0 |
| VEDL | -1.0 | neither fits | 0 / 0 / 0 / 1 |

What does not explain the split (all measured): the sign (Reliance and Tata Consumer have both signs and never count it; Nestle India has only losses and always counts it); the size against profit before tax (Reliance's 27 to 195 a quarter is not counted, Wipro's 3 to 15 is); the sector (Cipla and Sun do not count, Dr. Reddy's does; Reliance and Adani Enterprises do not, Mahindra and Mahindra and Bajaj Auto do); the shape of the file (in all 34 company files tested the net profit is profit before tax - tax + share, so the file always puts the share below tax). **Assumption to test:** screener reads the printed result, and companies print the associates line either before profit before tax (counted) or after tax (not counted). The test is to read the printed results of one counted and one not counted company, or to fetch screener's hidden Other Income rows for both (`/api/company/<id>/schedules/`, endpoint described in the five-company report; not fetched here).

The loss rule is new. In the five-company study a loss was read as "not counted". Of the 30 counting companies, 17 have a loss quarter, and in each of those quarters the loss sits in Expenses (HCL Tech, Nestle India, Power Grid, JSW Steel and 13 more); it looks the same as "not counted" only when Expenses and Other Income are not looked at.

## 8. Other findings

- **Screener's annual column is not the sum of its four quarters for 22 of 39 companies** (Expenses and Other Income move by equal and opposite amounts; Reliance also in Sales: -1,439). Bharti Airtel: 3,160 (the Q4FY26 exceptional item, -3,160.7). So FY26 on screener comes from another document than the quarters, most likely the annual report, as the five-company study found for Sun, L&T and ITC.
- **Screener's EPS restates for later bonus or split issues** (Nestle India Q1FY26 3.35 against 6.71, Pidilite Q1FY26 6.61 against 13.22, Trent Q1FY26 8.06 against 12.09, Kotak Q1FY26 4.50 against 22.49) and uses its own share count in other places, as the five-company study found for IMPAL.
- **Coal India's own files are not on one basis:** the four quarters in the files add up to 147,443 against the file's 12-month 168,400.
- **Memory's definitions differ across layouts:** for banks the memory field `pat` is the owners' profit (after minority interest and associates); for other companies `pat` is the whole profit and `pat_owners` is the owners'. Insurers' memory `tax_expense` is the shareholders'-account tax only (ProvisionsForTaxes), while screener's profit before tax adds the policyholders' provision as well.
- **Pipeline reader against raw file:** 18 differences, all EPS of Hindustan Unilever and Vedanta (same cause as memory, section 2).

## 9. Every gap no rule explains

Cause classes: **measured** means the file and screener show it; **assumption** means the reading is likely but not proven. The columns list screener's figure, the XBRL value by the formula, and the gap (screener minus XBRL). 292 pairs in all: 198 in the profit and loss, 87 in the balance sheet, 7 in the cash flow.

### 9.1 Profit and loss

**Restated by screener (demerger): 45 pairs.** Assumption: screener shows the quarter restated for a demerger. Measured: its Sales matches neither our consolidated nor standalone file, while the next quarters match; HUL: the ice-cream business moved to discontinued operations from Q3FY26 (ProfitLossFromDiscontinuedOperationsAfterTax 4,485 in Q3FY26 which rule P12 explains), so the two earlier quarters on screener (15,757 and 15,919) are below the filed ones (16,514 and 16,241). VEDL: Q1-Q3FY26 Sales 15,754 / 18,747 / 21,337 on screener against 37,824 / 39,868 / 23,369 consolidated in the files.

| Company | Period | Row: screener / XBRL by rule (gap) |
|---|---|---|
| HINDUNILVR | Q1FY26 | Sales 15,757 / 16,514 (-757); Expenses 12,118 / 12,797 (-679); Op. profit 3,639 / 3,717 (-78); Other inc. 103 / 74 (+29); Interest 122 / 127 (-5); Depr. 326 / 361 (-35); PBT 3,294 / 3,303 (-9) |
| HINDUNILVR | Q2FY26 | Sales 15,919 / 16,241 (-322); Expenses 12,137 / 12,515 (-378); Op. profit 3,782 / 3,726 (+56); OPM % 24.0 / 22.9 (+1.1); Other inc. 269 / 331 (-62); Interest 124 / 129 (-5); Depr. 322 / 358 (-36); PBT 3,605 / 3,570 (+35) |
| VEDL | Q1FY26 | Sales 15,754 / 37,824 (-22,070); Expenses 11,478 / 27,906 (-16,428); Op. profit 4,276 / 9,918 (-5,642); OPM % 27.0 / 26.2 (+0.8); Other inc. 2,737 / 985 (+1,752); Interest 609 / 2,026 (-1,417); Depr. 1,116 / 2,824 (-1,708); PBT 5,288 / 6,053 (-765); Tax % 16.0 / 26.4 (-10.4) |
| VEDL | Q2FY26 | Sales 18,747 / 39,868 (-21,121); Expenses 13,832 / 28,471 (-14,639); Op. profit 4,915 / 11,397 (-6,482); OPM % 26.0 / 28.6 (-2.6); Other inc. 1,248 / -1,471 (+2,719); Interest 1,033 / 2,110 (-1,077); Depr. 1,303 / 2,868 (-1,565); PBT 3,827 / 4,948 (-1,121); Tax % 9.0 / 29.7 (-20.7) |
| VEDL | Q3FY26 | Sales 21,337 / 23,369 (-2,032); Expenses 14,816 / 16,503 (-1,687); Op. profit 6,521 / 6,866 (-345); OPM % 31.0 / 29.4 (+1.6); Other inc. 4,426 / 4,428 (-2); Interest 547 / 989 (-442); Depr. 1,239 / 1,424 (-185); PBT 9,161 / 8,881 (+280); Tax % 15.0 / 12.1 (+2.9) |
| VEDL | Q4FY26 | Other inc. 5,503 / 5,520 (-17); Interest 694 / 737 (-43); PBT 11,036 / 11,010 (+26) |

**Screener quarter differs from the file (Coal India): 6 pairs.** Screener Jun 2025 differs from the file: Sales 42,919 against 35,842 (+7,077) and PBT 11,776 against 11,709 by the rule (+67; +211 against the file's own PBT, before the associates' share). Coal India's own quarters add up to 147,443 but its 12-month figure in the Q4 file is 168,400, so its quarterly and annual files are not on one basis.

| Company | Period | Row: screener / XBRL by rule (gap) |
|---|---|---|
| COALINDIA | Q1FY26 | Sales 42,919 / 35,842 (+7,077); Expenses 30,331 / 23,321 (+7,010); Op. profit 12,588 / 12,521 (+67); OPM % 29.0 / 34.9 (-5.9); PBT 11,776 / 11,709 (+67); Net profit 8,788 / 8,734 (+54) |

**Annual-report classification (balanced): 67 pairs.** Annual-report classification. Profit before tax and net profit equal in both, only the split of the same amount between sales, expenses, other income and interest differs (screener builds the year from the annual report, the file from the quarterly template). Screener's year is not the sum of its own four quarters for 22 of 39 companies.

| Company | Period | Row: screener / XBRL by rule (gap) |
|---|---|---|
| ADANIPORTS | FY26 | Expenses 15,868 / 15,884 (-16); Op. profit 22,868 / 22,851 (+17); Other inc. 2,152 / 2,169 (-17) |
| APOLLOHOSP | FY26 | Expenses 21,449 / 21,459 (-10); Op. profit 3,779 / 3,769 (+10); Other inc. 207 / 217 (-10) |
| ASIANPAINT | FY26 | Expenses 28,884 / 28,888 (-4); Op. profit 6,700 / 6,696 (+4); Other inc. 728 / 732 (-4) |
| BAJAJ-AUTO | FY26 | Expenses 49,808 / 49,844 (-36); Op. profit 13,097 / 13,061 (+36); Other inc. 2,668 / 2,704 (-36) |
| BAJAJFINSV | FY26 | Sales 150,530 / 150,504 (+26); Expenses 93,433 / 93,761 (-328); Op. profit 57,098 / 56,743 (+355); Other inc. -382 / -336 (-46); Interest 28,541 / 28,232 (+309) |
| BAJFINANCE | FY26 | Revenue 81,985 / 81,982 (+3); Interest 28,899 / 28,666 (+233); Expenses 25,998 / 26,249 (-251); Fin. profit 27,088 / 27,067 (+21); Other inc. -263 / -242 (-21) |
| BHARTIARTL | FY26 | Expenses 94,459 / 90,934 (+3,525); Op. profit 116,514 / 120,039 (-3,525); OPM % 55.0 / 56.9 (-1.9); Other inc. 2,925 / -600 (+3,525) |
| COALINDIA | FY26 | Expenses 131,228 / 127,158 (+4,070); Op. profit 37,172 / 41,242 (-4,070); OPM % 22.0 / 24.5 (-2.5); Other inc. 16,104 / 12,034 (+4,070) |
| EICHERMOT | FY26 | Expenses 17,618 / 17,622 (-4); Op. profit 5,789 / 5,785 (+4); Other inc. 2,225 / 2,229 (-4) |
| GAIL | FY26 | Expenses 130,096 / 130,088 (+8); Op. profit 11,502 / 11,510 (-8); Other inc. 3,023 / 3,014 (+9) |
| JSWSTEEL | FY26 | Expenses 156,006 / 156,124 (-118); Op. profit 29,464 / 29,346 (+118); Other inc. 18,489 / 18,607 (-118) |
| MARUTI | FY26 | Expenses 161,786 / 161,860 (-74); Op. profit 21,530 / 21,456 (+74); Other inc. 4,569 / 4,643 (-74) |
| NTPC | FY26 | Expenses 131,947 / 134,563 (-2,616); Op. profit 55,438 / 52,822 (+2,616); Other inc. 2,662 / 5,278 (-2,616) |
| PIDILITIND | FY26 | Expenses 11,080 / 11,084 (-4); Op. profit 3,521 / 3,517 (+4); Other inc. 248 / 252 (-4) |
| POWERGRID | FY26 | Expenses 13,901 / 11,528 (+2,373); Op. profit 32,831 / 35,205 (-2,374); OPM % 70.0 / 75.3 (-5.3); Other inc. 3,193 / 819 (+2,374) |
| RELIANCE | FY26 | Sales 1,055,780 / 1,057,035 (-1,255); Expenses 876,715 / 878,086 (-1,371); Op. profit 179,065 / 178,949 (+116); Other inc. 28,846 / 28,962 (-116) |
| SHRIRAMFIN | FY26 | Revenue 48,135 / 48,133 (+2); Interest 21,586 / 21,521 (+65); Expenses 12,602 / 12,673 (-71); Fin. profit 13,947 / 13,939 (+8); Other inc. 52 / 59 (-7) |
| TATAPOWER | FY26 | Expenses 49,157 / 49,334 (-177); Op. profit 13,271 / 13,095 (+176); Other inc. 3,433 / 3,609 (-176) |
| TITAN | FY26 | Expenses 79,227 / 79,229 (-2); Op. profit 8,357 / 8,355 (+2); Other inc. 450 / 452 (-2) |

**Reclassification inside a quarter (balanced): 29 pairs.** Reclassification inside the quarter. Profit before tax and net profit equal, an amount moves between sales or revenue, expenses and other income.

| Company | Period | Row: screener / XBRL by rule (gap) |
|---|---|---|
| BAJAJFINSV | Q1FY26 | Sales 35,288 / 35,439 (-151); Expenses 20,973 / 21,124 (-151); OPM % 41.0 / 40.4 (+0.6) |
| BAJFINANCE | Q2FY26 | Revenue 19,990 / 20,179 (-189); Expenses 6,119 / 6,307 (-188) |
| BAJFINANCE | Q3FY26 | Revenue 21,013 / 21,214 (-201); Expenses 7,737 / 7,938 (-201) |
| KOTAKBANK | Q1FY26 | Interest 7,527 / 7,529 (-2); Expenses 13,123 / 13,121 (+2) |
| NESTLEIND | Q2FY26 | Expenses 4,421 / 4,417 (+4); Op. profit 1,223 / 1,227 (-4); Other inc. 6 / 2 (+4) |
| NTPC | Q4FY26 | Sales 49,686 / 49,688 (-2); Op. profit 8,505 / 8,507 (-2) |
| ONGC | Q1FY26 | Sales 163,106 / 163,108 (-2); Expenses 137,336 / 137,429 (-93); Op. profit 25,770 / 25,679 (+91); Other inc. 2,464 / 2,555 (-91) |
| ONGC | Q4FY26 | Sales 173,801 / 173,805 (-4); Op. profit 25,352 / 25,356 (-4); Other inc. 5,702 / 5,699 (+3) |
| SBIN | Q3FY26 | Revenue 130,386 / 130,590 (-204); Fin. profit -25,196 / -24,992 (-204); Other inc. 55,262 / 55,059 (+203) |
| TATAPOWER | Q1FY26 | Expenses 14,470 / 14,467 (+3); Op. profit 3,565 / 3,568 (-3); Other inc. 494 / 491 (+3) |
| TECHM | Q2FY26 | Expenses 11,830 / 11,827 (+3); Op. profit 2,165 / 2,168 (-3) |

**Bank annual depreciation: 8 pairs.** Annual report: depreciation is split out of expenses on screener and has no element in the results file. Expenses + Depreciation reproduces the XBRL expenses for four banks (HDFC, ICICI, SBI, Axis); Kotak is 16 Cr off, the same size as its Other Income gap.

| Company | Period | Row: screener / XBRL by rule (gap) |
|---|---|---|
| AXISBANK | FY26 | Depr. 1,889 / 0 (+1,889) |
| HDFCBANK | FY26 | Depr. 4,195 / 0 (+4,195) |
| ICICIBANK | FY26 | Depr. 3,061 / 0 (+3,061) |
| KOTAKBANK | FY26 | Expenses 51,303 / 52,319 (-1,016); Fin. profit -11,142 / -12,158 (+1,016); Other inc. 38,166 / 37,782 (+384); Depr. 1,032 / 0 (+1,032) |
| SBIN | FY26 | Depr. 4,830 / 0 (+4,830) |

**EPS restated for bonus or split: 7 pairs.** Screener restates old EPS for a later bonus or split (ratio exactly 0.50, 0.67 or 0.20).

| Company | Period | Row: screener / XBRL by rule (gap) |
|---|---|---|
| HDFCBANK | Q1FY26 | EPS 10.60 / 21.23 (-10.63) |
| KOTAKBANK | Q1FY26 | EPS 4.50 / 22.49 (-17.99) |
| KOTAKBANK | Q2FY26 | EPS 4.49 / 22.47 (-17.98) |
| NESTLEIND | Q1FY26 | EPS 3.35 / 6.71 (-3.36) |
| PIDILITIND | Q1FY26 | EPS 6.61 / 13.22 (-6.61) |
| TRENT | Q1FY26 | EPS 8.06 / 12.09 (-4.03) |
| TRENT | Q2FY26 | EPS 7.07 / 10.60 (-3.53) |

**EPS on screener's own share count: 23 pairs.** Screener divides profit by its own share count. Gap 3% to 10% from the filed EPS (Tech Mahindra and Mahindra and Mahindra run at ratio 0.90 in every quarter). Assumption: treasury or trust shares, or period-end against weighted-average shares.

| Company | Period | Row: screener / XBRL by rule (gap) |
|---|---|---|
| ADANIENT | Q1FY26 | EPS 6.85 / 6.02 (+0.83) |
| ADANIENT | Q2FY26 | EPS 24.74 / 27.38 (-2.64) |
| ADANIPORTS | FY26 | EPS 55.58 / 58.23 (-2.65) |
| AXISBANK | FY26 | EPS 84.89 / 85.04 (-0.15) |
| BHARTIARTL | FY26 | EPS 43.81 / 45.96 (-2.15) |
| GRASIM | Q4FY26 | EPS 27.86 / 28.87 (-1.01) |
| HDFCBANK | FY26 | EPS 49.39 / 49.50 (-0.11) |
| ICICIBANK | FY26 | EPS 75.71 / 75.89 (-0.18) |
| M&M | FY26 | EPS 137.50 / 153.10 (-15.60) |
| M&M | Q1FY26 | EPS 32.84 / 36.58 (-3.74) |
| M&M | Q1FY27 | EPS 43.86 / 48.80 (-4.94) |
| M&M | Q2FY26 | EPS 29.54 / 32.90 (-3.36) |
| M&M | Q3FY26 | EPS 37.59 / 41.85 (-4.26) |
| M&M | Q4FY26 | EPS 37.53 / 41.77 (-4.24) |
| SBIN | FY26 | EPS 90.24 / 91.16 (-0.92) |
| SBIN | Q2FY26 | EPS 22.90 / 22.81 (+0.09) |
| TECHM | FY26 | EPS 49.10 / 54.28 (-5.18) |
| TECHM | Q1FY26 | EPS 11.65 / 12.87 (-1.22) |
| TECHM | Q1FY27 | EPS 14.95 / 16.53 (-1.58) |
| TECHM | Q2FY26 | EPS 12.19 / 13.48 (-1.29) |
| TECHM | Q2FY27 | EPS 16.18 / 17.88 (-1.70) |
| TECHM | Q3FY26 | EPS 11.45 / 12.66 (-1.21) |
| TECHM | Q4FY26 | EPS 13.82 / 15.27 (-1.45) |

**Small gap (5 Cr or less): 7 pairs.** Gap of 5 Cr or less on one or two rows; no cause found.

| Company | Period | Row: screener / XBRL by rule (gap) |
|---|---|---|
| GRASIM | Q1FY26 | Other inc. 376 / 372 (+4); PBT 3,837 / 3,834 (+3); Net profit 2,771 / 2,767 (+4) |
| GRASIM | Q4FY26 | Expenses 40,227 / 40,225 (+2); Op. profit 10,874 / 10,876 (-2) |
| LICI | Q1FY26 | Net profit 10,955 / 10,957 (-2) |
| LICI | Q2FY26 | Net profit 10,096 / 10,098 (-2) |

**No cause found: 6 pairs.** No cause found.

| Company | Period | Row: screener / XBRL by rule (gap) |
|---|---|---|
| GRASIM | Q4FY26 | PBT 4,960 / 5,078 (-118); Net profit 3,684 / 3,802 (-118) |
| LICI | Q1FY26 | PBT 11,253 / 12,602 (-1,349) |
| LICI | Q2FY26 | PBT 10,537 / 11,624 (-1,087) |
| LICI | Q3FY26 | PBT 13,188 / 14,862 (-1,674); Net profit 12,908 / 12,930 (-22) |

### 9.2 Balance sheet
| Company | Period | Rows: screener / XBRL by rule (gap) | Likely cause and evidence |
|---|---|---|---|
| ADANIPORTS | Q4FY26 | Reserves 95,498 / 95,665 (-167); Borrowings 63,566 / 55,103 (+8,463); Other Liabilities 23,574 / 31,870 (-8,296) | **Debt or lease amount not tagged as borrowing; reserves.** Borrowings +8,463 (nearest file item: other non-current financial liabilities 8,376); Reserves -167 against the file, no cause found. |
| ASIANPAINT | Q4FY26 | Borrowings 3,929 / 2,293 (+1,636); Other Liabilities 9,218 / 10,854 (-1,636) | **Lease liabilities not tagged.** Measured: the file has no lease member; "Other non-current financial liabilities" (14,206) is one lump. Assumption: leases sit inside it; gap 1,636. |
| AXISBANK | Q4FY26 | Reserves 214,414 / 212,957 (+1,457); Other Liabilities 116,713 / 118,169 (-1,456); Fixed Assets 6,776 / 6,756 (+20); CWIP 269 / 0 (+269); Other Assets 1,492,583 / 1,492,872 (-289) | **Minority interest in reserves; CWIP split.** Measured: reserves +1,457 and other liabilities -1,456 (a move between the two); CWIP 269 is not in the file. Assumption: minority interest or reserve-type items counted in reserves, from the printed balance sheet. |
| BAJAJ-AUTO | Q2FY27 | Borrowings 26,401 / 25,778 (+623); Other Liabilities 18,552 / 19,175 (-623) | **Lease liabilities not tagged.** Measured: no lease member in the file (Mar 2026 gap 732, Sep 2026 gap 623). Assumption: leases sit in other financial liabilities. |
| BAJAJ-AUTO | Q4FY26 | Borrowings 22,713 / 21,981 (+732); Other Liabilities 15,369 / 16,101 (-732) | **Lease liabilities not tagged.** Measured: no lease member in the file (Mar 2026 gap 732, Sep 2026 gap 623). Assumption: leases sit in other financial liabilities. |
| BAJAJFINSV | Q4FY26 | Borrowing 429,914 / 428,248 (+1,666); Other Liabilities 250,666 / 252,335 (-1,669); Total Liabilities 758,495 / 758,498 (-3); Other Assets 557,031 / 557,034 (-3); Total Assets 758,495 / 758,498 (-3) | **Borrowing differs.** Measured: Borrowing +1,667, no member found; total off by 2.5 (deferred-tax netting 2.8 would explain it, rule B2). |
| COALINDIA | Q4FY26 | Other Liabilities 150,782 / 150,247 (+535); Total Liabilities 283,956 / 283,421 (+535); Fixed Assets 87,252 / 84,267 (+2,985); CWIP 23,413 / 26,397 (-2,984); Other Assets 163,066 / 162,530 (+536); Total Assets 283,956 / 283,421 (+535) | **Fixed assets / capital work in progress split; netting.** Measured: fixed assets +2,985 and CWIP -2,984 (same sum, a split difference); total differs from Assets less the deferred-tax netting by 535. Cause not found. |
| GAIL | Q4FY26 | Other Liabilities 26,688 / 26,655 (+33); Total Liabilities 140,569 / 140,537 (+32); Investments 26,233 / 16,873 (+9,360); Other Assets 21,597 / 30,924 (-9,327); Total Assets 140,569 / 140,537 (+32) | **Member counted as investment; netting.** Measured: Investments +9,360 = the member "Other Investments" (9,360.2) of other non-current financial assets. Total is 32 above Assets, no cause found. |
| GRASIM | Q4FY26 | Investments 154,982 / 114,564 (+40,418); Other Assets 248,236 / 288,654 (-40,418) | **Insurance-business assets counted as investments.** Measured: Investments +40,418 = the members "Assets held to cover linked liabilities of Life Insurance Business" (32,023 non-current + 8,395 current = 40,418). |
| HDFCBANK | Q4FY26 | Reserves 584,520 / 579,975 (+4,545); Other Liabilities 633,519 / 638,404 (-4,885); Total Liabilities 4,907,701 / 4,908,041 (-340); Total Assets 4,907,701 / 4,908,041 (-340); Other Assets 3,610,993 / 3,611,333 (-340) | **Minority interest / ESOP reserve moved into reserves.** Measured: Reserves +4,545, other liabilities -4,885, total 340 below Assets. The file's own note says capital, ESOP outstanding, reserves and minority interest are given as one sum, so the split differs between the file and the printed statement (assumption). |
| HDFCLIFE | Q4FY26 | Fixed Assets 2,716 / 746 (+1,970); Investments 373,340 / 375,448 (-2,108) | **Fixed assets and investments.** Measured: fixed assets 2,716 against file 746; investments -2,108. Cause not found. |
| HINDALCO | Q4FY26 | Borrowings 99,165 / 99,161 (+4); Other Liabilities 108,933 / 108,937 (-4) | **Rounding-size gap.** 4 Cr on a 99,000 Cr line. |
| ICICIBANK | Q2FY27 | Equity Capital 1,436 / 4,299 (-2,863); Reserves 386,226 / 405,907 (-19,681); Other Liabilities 518,191 / 495,648 (+22,543) | **Equity capital and reserves split differently; fixed assets.** Measured: the file's "Capital" is 4,114, screener's Equity Capital 1,432 (2,682 less); Reserves -13,829, Other Liabilities +16,511; Fixed Assets +10,550 with Other Assets lower by the same. Cause not found (assumption: the file's Capital line holds more than share capital). |
| ICICIBANK | Q4FY26 | Equity Capital 1,432 / 4,114 (-2,682); Reserves 361,628 / 375,457 (-13,829); Other Liabilities 501,153 / 484,642 (+16,511); Fixed Assets 27,970 / 17,420 (+10,550); Other Assets 2,015,808 / 2,026,358 (-10,550) | **Equity capital and reserves split differently; fixed assets.** Measured: the file's "Capital" is 4,114, screener's Equity Capital 1,432 (2,682 less); Reserves -13,829, Other Liabilities +16,511; Fixed Assets +10,550 with Other Assets lower by the same. Cause not found (assumption: the file's Capital line holds more than share capital). |
| KOTAKBANK | Q4FY26 | Reserves 180,231 / 180,118 (+113); Other Liabilities 159,793 / 159,906 (-113); Fixed Assets 3,801 / 2,853 (+948); Other Assets 708,919 / 709,867 (-948) | **Reserves; fixed assets.** Measured: Reserves +113 (other liabilities -113); Fixed Assets +948 (other assets lower by the same). Assumption: intangibles or right-of-use assets shown as fixed assets. |
| LICI | Q4FY26 | Reserves 170,280 / 170,556 (-276); Fixed Assets 28,335 / 4,757 (+23,578); Investments 5,556,359 / 5,580,356 (-23,997) | **Fixed assets and investments; reserves.** Measured: Fixed Assets +23,578 and Investments -23,997; Reserves -276. Cause not found. |
| M&M | Q4FY26 | Borrowings 136,936 / 133,963 (+2,973); Other Liabilities 86,021 / 88,994 (-2,973) | **A member counted as borrowing.** Measured: gap 2,973 = the member "Compulsorily convertible preference shares" (2,972.8) of other non-current financial liabilities. The annual-report file already carries it in its borrowings (132,587 = 129,615 + 2,973) and 132,587 + 4,349 lease members = screener 136,936. |
| NESTLEIND | Q4FY26 | Borrowings 444 / 1,616 (-1,172); Other Liabilities 7,581 / 6,409 (+1,172) | **Lease liabilities counted only in part.** Screener 444 = 24 (borrowings) + 420; the file has lease members of 338 (non-current) and 1,254 (current) = 1,592 and the rule would give 1,616. Screener counts about a quarter of it. |
| NTPC | Q4FY26 | Other Liabilities 84,262 / 83,874 (+388); Total Liabilities 558,442 / 558,054 (+388); Other Assets 130,609 / 130,220 (+389); Total Assets 558,442 / 558,054 (+388) | **Deferred-tax netting differs.** Measured: screener nets 202 against Assets; min(DTA 590, DTL 10,568) would be 590; difference 388. Cause not found. |
| ONGC | Q4FY26 | Other Liabilities 239,518 / 238,317 (+1,201); Total Liabilities 785,602 / 784,401 (+1,201); Other Assets 222,173 / 220,972 (+1,201); Total Assets 785,602 / 784,401 (+1,201) | **Deferred-tax netting differs.** Measured: screener nets 6,303; min(DTA 7,504, DTL 40,655) would be 7,504; difference 1,201. Cause not found. |
| RELIANCE | Q4FY26 | Borrowings 402,962 / 398,000 (+4,962); Other Liabilities 870,554 / 875,516 (-4,962) | **Debt or lease amount not tagged as borrowing.** Measured: lease members 23,579 are counted; screener counts a further 4,962 that is not a single member of the file. Assumption: part of the deferred payment liability (99,552, a member of other financial liabilities). |
| SBIN | Q4FY26 | Reserves 595,208 / 613,976 (-18,768); Other Liabilities 904,646 / 886,270 (+18,376); Total Liabilities 8,321,176 / 8,321,569 (-393); Fixed Assets 59,772 / 57,152 (+2,620); CWIP 78 / 0 (+78); Total Assets 8,321,176 / 8,321,569 (-393); Other Assets 5,901,824 / 5,904,914 (-3,090) | **Reserves and other liabilities; fixed assets.** Measured: Reserves -18,768 and other liabilities +18,376; Fixed Assets +2,620, CWIP +78; total 393 below Assets. Cause not found. |
| TECHM | Q2FY27 | Fixed Assets 15,028 / 13,053 (+1,975); Other Assets 31,036 / 33,011 (-1,975) | **Right-of-use assets not tagged.** Measured: fixed assets +1,975 (Sep 2026) and +1,980 (Mar 2026), no single file item matches and the file has no right-of-use member. Assumption: right-of-use assets. |
| TITAN | Q4FY26 | Borrowings 30,621 / 11,378 (+19,243); Other Liabilities 14,237 / 33,480 (-19,243) | **Debt not tagged as borrowing (gold on lease).** Measured: Titan's Q4 file shows borrowings of 11,378, its annual-report file 27,448 (+16,070), screener 30,621 (3,173 more). Assumption: the 16,070 is gold on lease, tagged outside borrowings in the Q4 file, and the 3,173 is lease liabilities no file tags; Fixed assets +2,195 is probably right-of-use assets, also not tagged. |
| ULTRACEMCO | Q2FY27 | Borrowings 29,289 / 28,411 (+878); Other Liabilities 42,222 / 43,100 (-878) | **Lease liabilities not tagged.** Measured: no lease member in the file (Mar 2026 gap 974, Sep 2026 gap 878). Assumption: leases sit in other financial liabilities. |
| ULTRACEMCO | Q4FY26 | Borrowings 23,755 / 22,781 (+974); Other Liabilities 40,936 / 41,911 (-975) | **Lease liabilities not tagged.** Measured: no lease member in the file (Mar 2026 gap 974, Sep 2026 gap 878). Assumption: leases sit in other financial liabilities. |
| VEDL | Q4FY26 | Borrowings 32,947 / 27,844 (+5,103); Other Liabilities 149,712 / 154,815 (-5,103) | **A member counted as borrowing.** Measured: gap 5,103 = the member "Operational buyers' credit / suppliers' credit" of other current financial liabilities, exactly. |

### 9.3 Cash flow FY26
| Company | Rows: screener / XBRL by rule (gap) | Likely cause |
|---|---|---|
| SHRIRAMFIN | Investing -241 / -243 (+2) | 1.8 Cr, rounding size. |
| APOLLOHOSP | Investing -2,145 / -2,148 (+3); Net Cash Flow 233 / 230 (+3) | 3 Cr; Q4 file only (no annual report listed). |
| ADANIPORTS | Investing -13,191 / -13,118 (-73); Net Cash Flow 1,682 / 1,755 (-73) | 73 Cr; Q4 file only (no annual report listed or downloaded). |
| AXISBANK | Operating -8,637 / -8,474 (-163); Financing 60,358 / 60,195 (+163) | 163 Cr moves between operating and financing; equals the year's minority-interest profit (163.1) in the P&L. |

## 10. How the work was done

- **Scripts (scratchpad `fifty/scripts/`):** `get_nse50.py` (8 threads, one `NseClient()` each, stop flag), `get_screener.py`, `get_mem.py`, `xl.py` (the five-company reader, with a whitespace fix for dates), `master.py` (profit and loss formulas), `run_corp_pl.py`, `run_nbfc_pl.py`, `run_bank.py`, `run_ins.py`, `run_bs.py`, `run_nbfc_bs.py`, `run_bank_bs.py`, `run_cf.py`, `run_mem.py`, `run_mem_lend.py`, `assoc.py`, `fit.py`, `classify.py`, `final.py`, `formulas*.py`. Run with `python -I`. No client code or pipeline code was changed; the scripts use `NseClient.integrated_filings`, `annual_reports` and `download`, and read the raw annual-report list through the client's `raw` hook so the report type is seen.
- **Files:** `fifty/files/` (525 XBRL files), `fifty/lists/` (every list answer), `fifty/screener/` (50 pages and parsed tables), `fifty/mem/` (50 dossiers), `fifty/all_pairs.csv` (every pair with its verdict), `fifty/nse_run.json` and `fifty/nse_run.log`.
- **Choice of file per quarter:** the last filed row for that quarter end and basis, as in the five-company study.

## 11. For the lead

- **The NSE downloads are paused at the stop in section 4; I did not resume them.** The stop was set by a non-XML body, which the rules treat as a possible challenge page, and I could not read the body. If you judge it an odd file (the evidence in section 4 points that way), finishing is 64 listed files plus DLF's two list calls and its files; run them with the same eight threads and the same stop rule, and let the client's `max_bytes` be raised for the two large files (an extra argument to `download`, not a code change).
- **Things the owner can decide cheaply:** read the printed results of one counted and one not counted associates company; fetch screener's hidden Other Income rows for one of each (owner's tip in the five-company report); look at the printed HDFC Bank Q4FY26 minority-interest line.
- **Defects for the pipeline's backlog (measured):** the EPS choice for companies with discontinued operations (Hindustan Unilever, Vedanta); memory's profit before tax for Maruti and Bajaj Auto Q2FY27 includes the associates' share; memory `pat` means owners' profit for banks and whole profit for others.
