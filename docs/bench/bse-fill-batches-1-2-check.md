# BSE fill, batches 1 and 2 against screener.in, tijori and the company's own statement (27 Oct 2026)

Owner's rule: a BSE-filled figure is checked against a second source, and every difference that no documented rule explains is settled against the company's own results statement. Screener and tijori are leads, never the verdict. This is a read-only measurement: nothing was written to memory, to a database or to GitHub.

## Result in short

- Revenue and profit agree with screener in 577 of 590 and 587 of 592 pairs (98% and 99%); with tijori in 465 of 476 and 441 of 476 (98% and 93%).
- EPS agrees in 411 of 594 pairs with screener (69%) and 326 of 478 with tijori (68%). Almost all EPS differences are a share-count change after the filing (split or bonus) or an EPS recomputed on the owners' profit; BSE's file carries the figure the company printed that day.
- 89 differences were read in the company's own results statement (47 PDFs, 37 companies): **BSE right 82, BSE wrong 4, definition 1, unsure 2**. 15 more EPS lines were left unread.
- **The four wrong BSE figures** (listed in full below): Eco Recycling Q4FY25 profit 3.42 (statement 2.20); Vadilal Enterprises Q3FY25 profit -42.94 (statement -18.31); Pradeep Metals Q4FY26 profit 15.83 (statement 10.32); Veljan Denison Q3FY26 EPS 10.31 (statement 11.24). In all four the company's own XBRL differs from its own PDF. The batches were applied, so memory holds these four figures now.

## What was checked

- Method as in `docs/bench/bse-fill-2026-10-27.md`. Batch 1 (`memory-gaps-fill-bse` CSV): 8,324 figures, 49 companies, 321 company-quarters. Batch 2: 7,277 figures, 43 companies, 277 company-quarters. Quarters Q2FY25 to Q1FY27. Revenue, total profit (`pat`) and EPS were compared; EPS in rupees, money in crore.
- Screener: 99 pages, one per company and basis the CSV rows need (consolidated page for consolidated rows, the plain page for standalone rows). Read with the repo's `parse_full`. Tijori: 73 company pages (the other 19 companies have no page found by name, see Limits), read with the repo's `tijori_crosscheck.parse_tables`.
- Bands (owner's): revenue and profit to within 0.5 Cr, EPS to 0.01. The same bands are used against tijori. (Tijori prints 2 to 4 decimals, so a stricter 0.011 Cr band is also given for it.)
- The comparison script `pipeline/scripts/bench_bse/compare_screener.py` was run as it is (strict: a pair needs the screener page's own basis label) and gave 1,364 pairs. It cannot compare the 20 companies whose screener page carries no basis label (one basis only; all their CSV rows are standalone). Those pages were read as standalone here (measured: they agree as well as the labelled ones: revenue 136 of 136, profit 136 of 136, EPS 108 of 140, against 441 of 454, 451 of 456 and 303 of 454 on the labelled pages), which brings the pairs to 1,776 against screener. The tables below use the 1,776.

## Pairs compared

| line | against | pairs | agree | differ |
|---|---|---|---|---|
| revenue (0.5 Cr) | screener | 590 | 577 | 13 |
| profit (0.5 Cr) | screener | 592 | 587 | 5 |
| EPS (0.01) | screener | 594 | 411 | 183 |
| revenue (0.5 Cr) | tijori | 476 | 465 | 11 |
| profit (0.5 Cr) | tijori | 476 | 441 | 35 |
| EPS (0.01) | tijori | 478 | 326 | 152 |

Against tijori with the strict band (0.011 Cr or 0.05%): revenue 458 of 476, profit 409 of 476, EPS 326 of 478.

By batch (same bands):

| line | against | batch 1: pairs / agree | batch 2: pairs / agree |
|---|---|---|---|
| revenue | screener | 313 / 306 | 277 / 271 |
| profit | screener | 315 / 313 | 277 / 274 |
| EPS | screener | 317 / 218 | 277 / 193 |
| revenue | tijori | 250 / 243 | 226 / 222 |
| profit | tijori | 250 / 224 | 226 / 217 |
| EPS | tijori | 252 / 175 | 226 / 151 |

Revenue and profit agree with screener in 98 to 99% of pairs. EPS agrees in 69% (411 of 594): the EPS differences are mostly share-count changes after the filing (see below), not wrong figures.

## The differences and their classes

**Against screener: 201 differences beyond the band.**

| line | class | pairs |
|---|---|---|
| revenue | read in the company's statement (table below) | 9 |
| revenue | screener's sales is BSE's total income (revenue plus other income) | 4 |
| profit | read in the company's statement (table below) | 5 |
| EPS | read in the company's statement (table below) | 62 |
| EPS | EPS: share count changed later (split or bonus); BSE is as first filed (pattern, not read) | 33 |
| EPS | EPS: company divides total profit, the other source divides the owners' profit (pattern) | 23 |
| EPS | EPS: small difference (2% or less, or 0.06 or less), the other source recomputes (pattern) | 37 |
| EPS | EPS: not read; no rule fits, but the same company was read in another quarter and BSE was right there (lead) | 13 |
| EPS | EPS: not read, no pattern fits, company not read (lead, listed below) | 15 |

**Against tijori: 198 differences beyond the band.**

| line | class | pairs |
|---|---|---|
| revenue | read in the company's statement (table below) | 7 |
| revenue | tijori's sales is BSE's total income (revenue plus other income) | 4 |
| profit | read in the company's statement (table below) | 13 |
| profit | tijori shows profit for the owners, BSE shows total profit | 22 |
| EPS | read in the company's statement (table below) | 48 |
| EPS | EPS: share count changed later (split or bonus); BSE is as first filed (pattern, not read) | 11 |
| EPS | EPS: company divides total profit, the other source divides the owners' profit (pattern) | 27 |
| EPS | EPS: small difference (2% or less, or 0.06 or less), the other source recomputes (pattern) | 49 |
| EPS | EPS: not read; no rule fits, but the same company was read in another quarter and BSE was right there (lead) | 14 |
| EPS | EPS: not read, no pattern fits, company not read (lead, listed below) | 3 |

How the classes were made. "Read in the statement": the company's own results PDF was opened and the line read (table further down). The other classes are patterns, not readings: a quarter is put in a class only when a rule fits it and it is the same shape as quarters of the same company that were read. The pattern classes are leads for the quarters not read; they are not verdicts.

The three big causes, with the quarters that were read:

1. **Share count changed after BSE's file (split, bonus, consolidation).** BSE's file is the figure the company filed that day; screener and tijori put old EPS on today's share count (screener-rules.md rule 7). The statements say so for KSE (1:10 split), Shardul (1:5 split), Fedders (split of 20 Sep 2024), Triton (3:1 bonus) and Bharat Seats (1:1 bonus, in a note), and the capital column shows it for Investment & Precision, Jaykay and Shukra Pharma. For Sika, Frontier Springs, TCC, GYFTR, Anuh Pharma, Shilchar, Belding and others the statement prints BSE's figure and screener and tijori are 1.5 to 6 times lower for a reason the statement does not give; a later share-count change is the likely one.
2. **Company divides total profit, screener and tijori divide the owners' profit.** ZF Steering and Aryaman: the company prints EPS on total profit (before the minority share). Tijori's profit line is the owners' profit too: 33 of its 35 profit differences fit this (22 by the CSV's own owners' profit line, 11 more in statements read); the other 2 are tijori being right where BSE is wrong. So it differs from BSE's total profit in every company with a minority share.
3. **Definition of sales.** Deccan Gold prints net sales 0.59 Cr and, one line below, other operating income 8.74 Cr; the statement's total income from operations is 9.34 Cr. BSE's file takes the first line, screener and tijori the total.

Screener and tijori errors seen while settling (BSE was right each time): screener 10 times too high on Onix Solar Q3FY25 revenue and profit; screener 0 revenue for Belding Q1FY26; screener showing Blackrose's standalone revenue 93.0 in the consolidated line (tijori too); tijori 4 times too high on Triton Q4FY26 EPS (bonus not applied); screener and tijori 10 times too low on Shukra Pharma EPS; screener 15.48 for One Global Q4FY25 EPS; screener and tijori both carry the older Onix Solar Q4FY26 figures (the company revised its consolidated results in Oct 2026).

## Differences settled against the company's statement

89 lines (company, quarter, line) were read in the company's own results statement: 47 PDFs from BSE, 37 companies, at most 3 quarters a company asked for and up to 3 columns read in each file (the quarter, the quarter before it, the same quarter a year earlier). Largest differences first (relative size, money lines before EPS); every revenue or profit difference that no rule explained was taken. The file count is 47, above the owner's "about 40": 37 first-choice files (one, Anuh Pharma, was retried after a typo in the file name), 7 second files (the quarter's own filing, taken where the first file showed only a restated comparative column: Shardul, Shukra Pharma, Sika, Deccan Gold, Fedders, Veljan; and Onix Solar's revised result of Oct 2026) and 3 more where both other sources disagreed with BSE (Permanent Magnets, Agarwal's Eye, Sunshield). Scanned or part-scanned files were read with the repo's OCR (RapidOCR) and are marked.

"(=)" after a figure means that source agrees with BSE's figure within the band. Statement figures are in crore unless the lakh or million figure is shown. "BSE (as first filed)" means the statement of that quarter printed BSE's number, and a later statement restated it.

| company | quarter | line | BSE file | screener | tijori | statement prints | right | file and note |
|---|---|---|---|---|---|---|---|---|
| ALGOQUANT | Q3FY25 | EPS | 3.26 | 0.18 | - | 3.26 | BSE | ALGOQUANT_Q4FY25; screener 0.18 matches no printed figure |
| ALGOQUANT | Q4FY25 | EPS | 0.39 | 0.02 | - | 0.39 | BSE | ALGOQUANT_Q4FY25; screener 0.02 matches no printed figure |
| ANUHPHR | Q2FY25 | EPS | 3.00 | 1.50 | 1.50 | 3.00 | BSE | ANUHPHR_Q2FY25 (own file); screener and tijori are 2 times lower; the statement gives no reason (a later bonus or split is the likely one) |
| ARYAMAN | Q2FY25 | EPS | 5.90 | 4.52 | 4.52 | 5.90 | BSE | ARYAMAN_Q3FY25; same |
| ARYAMAN | Q2FY25 | profit | 6.89 | 7.00 (=) | 5.28 | 6.89 | BSE | ARYAMAN_Q3FY25; tijori 5.28 owners' share |
| ARYAMAN | Q3FY25 | EPS | 18.50 | 12.19 | 12.19 | 18.50 | BSE | ARYAMAN_Q3FY25; scanned page (OCR); company divides total profit 21.61, screener and tijori the owners' profit |
| ARYAMAN | Q3FY25 | profit | 21.61 | 22.00 (=) | 14.24 | 21.61 | BSE | ARYAMAN_Q3FY25; tijori 14.24 owners' share |
| BAJAJST | Q2FY25 | EPS | 33.83 | 8.38 | 8.38 | 8.46 (restated for 3:1 bonus) | Unsure | BAJAJST_Q3FY25; BSE 33.83 is 4 times the restated 8.46, so probably the pre-bonus figure as first filed; the quarter's own file was not read |
| BAJAJST | Q3FY25 | EPS | 6.50 | 6.59 | 6.59 | 6.50 | BSE | BAJAJST_Q3FY25; screener and tijori 6.59 recompute |
| BELDING | Q3FY25 | EPS | 0.18 | 0.33 | - | 0.18 | BSE | BELDING_Q4FY25; screener 0.33 is about 2 times the printed 0.18; preceding-quarter column |
| BELDING | Q4FY25 | EPS | -0.73 | -1.44 | - | -0.73 | BSE | BELDING_Q4FY25; screener -1.44 is about 2 times the printed -0.73 |
| BELDING | Q1FY26 | EPS | 13.43 | 26.00 | - | 13.43 | BSE | BELDING_Q1FY26; screener 26.0 is about 2 times; the statement prints 13.43 on 87 lakh capital of Rs 5 shares (17.4 lakh shares) |
| BELDING | Q1FY26 | revenue | 5.19 | 0.00 | - | 5.19 (519.42 lakh) | BSE | BELDING_Q1FY26; screener shows 0 |
| BHARATSE | Q2FY25 | EPS | 2.26 | 1.13 | 1.13 | 2.26 | BSE (as first filed) | BHARATSE_Q2FY25; scanned (OCR); note says 1.13 after the 1:1 bonus |
| BLACKROSE | Q2FY25 | revenue | 123.33 | 93.00 | 93.05 | 123.33 (12,333.29 lakh) | BSE | BLACKROSE_Q2FY25; screener and tijori show the standalone 93.05 (9,304.61 lakh) |
| CIFL | Q2FY25 | EPS | 0.39 | 0.08 | 0.08 | 0.39 | BSE | CIFL_Q3FY25; comparative column |
| CIFL | Q2FY25 | profit | 0.60 | 0.60 (=) | 3.06 | 0.60 | BSE | CIFL_Q3FY25; comparative column |
| CIFL | Q2FY25 | revenue | 165.71 | 142.82 | 142.82 | 165.93 (comparative column) | BSE | CIFL_Q3FY25; comparative column 0.22 above BSE's file (regrouped); own Q2 file not read |
| CIFL | Q3FY25 | EPS | 0.09 | 0.02 | 0.02 | 0.09 | BSE | CIFL_Q3FY25 |
| CIFL | Q3FY25 | profit | -1.91 | -1.91 (=) | 0.69 | -1.91 (191.11 lakh loss) | BSE | CIFL_Q3FY25; owners' share 0.69 is what tijori shows |
| CIFL | Q3FY25 | revenue | 154.45 | 135.01 | 135.01 | 154.45 (15,444.93 lakh) | BSE | CIFL_Q3FY25; text layer misreads one digit; total income 15,488.90 less other income 43.97 = 15,444.93 lakh |
| DECNGOLD | Q4FY25 | EPS | 0.78 | 0.74 | 0.88 | 0.78 | BSE | DECNGOLD_Q4FY25 (own file); the Q4FY26 comparative shows 0.918 |
| DECNGOLD | Q4FY25 | profit | 11.82 | 11.82 (=) | 14.45 | 11.82 (118.16 mn) | BSE | DECNGOLD_Q4FY26; tijori owners' share |
| DECNGOLD | Q3FY26 | profit | -22.20 | -22.19 (=) | -18.92 | -22.19 (-221.94 mn) | BSE | DECNGOLD_Q4FY26; tijori owners' share |
| DECNGOLD | Q4FY26 | EPS | 0.44 | 0.39 | 0.39 | 0.443 | BSE | DECNGOLD_Q4FY26 |
| DECNGOLD | Q4FY26 | profit | 5.74 | 5.73 (=) | 7.62 | 5.74 (57.35 mn) | BSE | DECNGOLD_Q4FY26; tijori 7.62 is owners' share |
| DECNGOLD | Q4FY26 | revenue | 0.59 | 9.33 | 9.34 | net sales 0.59 (5.94 mn); other operating income 8.74; total income from operations 9.34 | Definition | DECNGOLD_Q4FY26; scanned page (OCR); BSE takes the net-sales line, screener and tijori the total |
| DRAGARWQ | Q2FY26 | EPS | 41.04 | 39.98 | 40.00 | 41.04 | BSE | DRAGARWQ_Q2FY26; scanned (OCR); company uses weighted shares; screener 39.98 and tijori 40.00 use closing shares |
| ECORECO | Q4FY25 | EPS | 1.19 | 1.08 | 1.08 | 1.19 (printed) | BSE | ECORECO_Q4FY25; statement prints 1.19, though 2.08 / 1.93 Cr shares is 1.08 |
| ECORECO | Q4FY25 | profit | 3.42 | 2.20 | 2.08 | 2.20 (220 lakh) | **BSE WRONG** | ECORECO_Q4FY25; BSE file's own tax line leaves out 1.22 Cr prior-year tax; the company's XBRL says 3.42, its PDF 2.20 |
| ELPROINTL | Q2FY25 | revenue | 207.42 | 207.00 (=) | 206.69 | 207.42 (20,741.61 lakh) | BSE | ELPROINTL_Q2FY25; tijori 206.69 off by 0.73 |
| FEDDERSHOL | Q2FY25 | EPS | 6.23 | 0.34 | - | 6.23 | BSE (as first filed) | FEDDERSHOL_Q2FY25 (own file); split of 20 Sep 2024 restated it to 0.62 in the Q3FY25 statement |
| FEDDERSHOL | Q3FY25 | EPS | 0.27 | 0.20 | - | 0.27 | BSE | FEDDERSHOL_Q3FY25; scanned table (OCR) |
| FRONTSP | Q2FY25 | EPS | 21.20 | 6.18 | 6.13 | 21.20 | BSE | FRONTSP_Q2FY26; year-ago column; screener and tijori about 3 times lower |
| FRONTSP | Q1FY26 | EPS | 40.11 | 12.49 | 12.40 | 40.11 | BSE | FRONTSP_Q2FY26; preceding-quarter column; screener and tijori about 3 times lower |
| FRONTSP | Q2FY26 | EPS | 39.64 | 13.31 | 13.21 | 39.64 | BSE | FRONTSP_Q2FY26; screener and tijori are about 3 times lower; the statement gives no reason (a later bonus or split is the likely one) |
| GYFTR | Q2FY25 | EPS | 13.85 | 2.27 | - | 13.85 | BSE | GYFTR_Q3FY25; comparative column; screener 2.27 is 6 times lower |
| GYFTR | Q3FY25 | EPS | -8.62 | -1.41 | - | -8.62 | BSE | GYFTR_Q3FY25; screener -1.41 is 6 times lower; the statement gives no reason |
| INVPRECQ | Q4FY25 | EPS | 3.79 | 1.90 | 1.90 | 1.90 (restated after the bonus) | BSE (as first filed) | INVPRECQ_Q1FY26; scanned (OCR); paid-up capital was 500 lakh at 31 Mar 2025 and 1,000 lakh at 30 Jun 2025: 189.50 lakh over 50 lakh shares is the 3.79 of BSE's file |
| INVPRECQ | Q1FY26 | revenue | 44.90 | 44.09 | 44.09 | 44.90 (sales 4,401.96 + other operating income 87.58 lakh) | BSE | INVPRECQ_Q1FY26; scanned (OCR); screener and tijori 44.09 match neither 44.02 nor 44.90 |
| JAYKAY | Q3FY25 | EPS | 0.83 | 0.38 | 0.41 | 0.83 | BSE (as first filed) | JAYKAY_Q4FY25; preceding-quarter column; paid-up capital 1,169.16 lakh, 584.58 a year earlier |
| JAYKAY | Q4FY25 | EPS | -0.49 | -0.27 | -0.29 | -0.49 | BSE (as first filed) | JAYKAY_Q4FY25; scanned in part (OCR); paid-up capital rose from 584.58 to 1,223.69 lakh between the columns |
| JAYKAY | Q4FY25 | profit | -4.41 | -4.42 (=) | -3.79 | -4.41 (441.05 lakh loss) | BSE | JAYKAY_Q4FY25; scanned in part (OCR); owners' share -3.80 is what tijori shows |
| JYOTIRES | Q2FY25 | EPS | 14.00 | 13.58 | 13.57 | 14 (printed whole) | BSE | JYOTIRES_Q2FY26 |
| JYOTIRES | Q1FY26 | EPS | 14.00 | 14.48 | 14.48 | 14 (printed whole) | BSE | JYOTIRES_Q2FY26 |
| JYOTIRES | Q2FY26 | EPS | 14.00 | 14.30 | 14.30 | 14 (printed whole) | BSE | JYOTIRES_Q2FY26; company prints EPS in whole rupees |
| KLBRENG-B | Q3FY25 | EPS | 3.46 | 3.19 | 3.19 | 3.46 | BSE | KLBRENG-B_Q3FY26; year-ago column |
| KLBRENG-B | Q2FY26 | EPS | 5.45 | 5.23 | 5.23 | 5.45 | BSE | KLBRENG-B_Q3FY26; preceding-quarter column |
| KLBRENG-B | Q3FY26 | EPS | 4.63 | 4.46 | 4.46 | 4.63 | BSE | KLBRENG-B_Q3FY26; scanned (OCR); screener 4.46 |
| KSE | Q2FY25 | EPS | 53.54 | 5.35 | 5.35 | 53.54 | BSE (as first filed) | KSE_Q2FY26; year-ago column of the Q2FY26 statement |
| KSE | Q1FY26 | EPS | 120.48 | 12.05 | 12.05 | 120.48 | BSE (as first filed) | KSE_Q2FY26; preceding-quarter column of the Q2FY26 statement |
| KSE | Q2FY26 | EPS | 102.72 | 10.27 | 10.27 | 102.72 | BSE (as first filed) | KSE_Q2FY26; statement note: EPS on old Rs 10 share; 1:10 split after |
| NITTAGELA | Q2FY25 | revenue | 134.29 | 132.00 | 132.34 | 134.29 (13,429.05 lakh) | BSE | NITTAGELA_Q2FY25; screener 132 and tijori 132.34 do not match the line |
| ONEGLOBAL | Q4FY25 | EPS | 5.63 | 15.48 | 5.63 (=) | 5.63 | BSE | ONEGLOBAL_Q4FY25; screener 15.48 wrong; tijori agrees with BSE |
| ONIXSOLAR | Q2FY25 | EPS | 0.75 | 0.43 | - | 0.75 | BSE | ONIXSOLAR_Q3FY25; comparative column; screener 0.43 matches no printed figure |
| ONIXSOLAR | Q3FY25 | EPS | 3.16 | 17.89 | - | 3.16 | BSE | ONIXSOLAR_Q3FY25; screener 17.89 matches nothing |
| ONIXSOLAR | Q3FY25 | profit | 0.63 | 6.26 | - | 0.63 (62.64 lakh) | BSE | ONIXSOLAR_Q3FY25; screener 10 times too high |
| ONIXSOLAR | Q3FY25 | revenue | 5.73 | 57.26 | - | 5.73 (572.58 lakh) | BSE | ONIXSOLAR_Q3FY25; screener 10 times too high |
| ONIXSOLAR | Q4FY26 | EPS | 6.02 | 7.62 | - | 6.02 | BSE | ONIXSOLAR_Q4FY26rev; screener 7.62 older |
| ONIXSOLAR | Q4FY26 | profit | 15.08 | 28.10 | - | 15.08 (1,508.46 lakh), revised consolidated result of Oct 2026 | BSE | ONIXSOLAR_Q4FY26rev; screener 28.10 is an older figure (the results were revised; the first PDF of 23 Apr 2026 had standalone only) |
| PERMAGN | Q4FY26 | EPS | 4.99 | 4.64 | 4.64 | 4.99 | BSE | PERMAGN_Q4FY26; consolidated table; screener and tijori 4.64 recompute |
| PRADPME | Q4FY26 | profit | 15.83 | 10.32 | 10.32 | 10.32 (1,031.92 lakh) | **BSE WRONG** | PRADPME_Q4FY26; company's XBRL tags tax as negative (-2.76), so 13.07 - (-2.76) = 15.83; statement tax is +2.76 |
| SHARDUL | Q2FY25 | EPS | 16.43 | 3.29 | 3.29 | 16.43 | BSE (as first filed) | SHARDUL_Q3FY25; comparative column (pre-split) |
| SHARDUL | Q3FY25 | EPS | -22.82 | -4.56 | -4.56 | -22.82 | BSE (as first filed) | SHARDUL_Q3FY25 (own file); 1:5 split restated it to -4.56 in the Q4FY25 statement |
| SHILCTECH | Q2FY25 | EPS | 42.92 | 28.71 | 28.61 | 42.92 | BSE | SHILCTECH_Q3FY25; comparative column; no text layer (OCR); screener and tijori about 1.5 times lower |
| SHILCTECH | Q3FY25 | EPS | 45.59 | 30.50 | 30.39 | 45.59 | BSE | SHILCTECH_Q3FY25; no text layer (OCR); screener and tijori about 1.5 times lower; the statement gives no reason |
| SHUKRAPHAR | Q2FY25 | EPS | 0.25 | 0.01 | 0.01 | 0.25 | BSE | SHUKRAPHAR_Q2FY25 (own file); bonus later restated it to 0.12; screener 0.01 and tijori 0.0123 match neither |
| SHUKRAPHAR | Q3FY25 | EPS | 0.72 | 0.07 | 0.07 | 0.72 | BSE | SHUKRAPHAR_Q3FY25; screener and tijori are 10 times too small |
| SIKA | Q2FY25 | EPS | 14.59 | 2.92 | 2.92 | 14.59 | BSE | SIKA_Q2FY25 (own file); own file prints 14.59 (the Q3FY25 statement's comparative shows 14.50); screener and tijori 5 times lower |
| SIKA | Q3FY25 | EPS | 16.85 | 3.37 | 3.37 | 16.85 | BSE | SIKA_Q3FY25; screener and tijori 5 times lower; the statement gives no reason (a later 1:5 split is the likely one) |
| SUNSHIEL | Q3FY26 | EPS | 5.83 | 5.56 | 5.56 | 5.83 | BSE | SUNSHIEL_Q3FY26; screener and tijori 5.56 recompute |
| SYSTMTXC | Q2FY25 | EPS | 17.06 | 1.71 | 1.71 | 1.71 (comparative, after 1:10 split of 5 Nov 2024) | Unsure | SYSTMTXC_Q3FY25; BSE 17.06 is 10 times the restated 1.71, so probably the pre-split figure as first filed; the quarter's own file was not read |
| SYSTMTXC | Q3FY25 | EPS | 1.40 | 1.36 | 1.36 | 1.40 | BSE | SYSTMTXC_Q3FY25 |
| SYSTMTXC | Q3FY25 | revenue | 43.82 | 42.27 | 43.82 (=) | 43.82 (4,382.45 lakh: 399.97 + 2,482.14 + 1,500.34) | BSE | SYSTMTXC_Q3FY25; screener 42.27 matches no line; tijori agrees with BSE |
| TCC | Q2FY25 | EPS | 4.59 | 0.52 | - | 4.59 | BSE | TCC_Q2FY26; year-ago column; screener 0.52 is far lower |
| TCC | Q1FY26 | EPS | 2.64 | 0.53 | - | 2.64 | BSE | TCC_Q2FY26; preceding-quarter column; screener 0.53 is one fifth |
| TCC | Q2FY26 | EPS | 2.92 | 0.59 | - | 2.92 | BSE | TCC_Q2FY26; scanned table (OCR); screener 0.59 is one fifth; the statement gives no reason |
| TRITONV | Q3FY25 | EPS | 9.01 | 2.23 | 2.23 | 9.01 | BSE (as first filed) | TRITONV_Q3FY26; year-ago column |
| TRITONV | Q2FY26 | EPS | 16.12 | 4.04 | 4.03 | 16.13 | BSE (as first filed) | TRITONV_Q3FY26; preceding-quarter column; BSE 16.12 |
| TRITONV | Q3FY26 | EPS | 20.63 | 5.18 | 5.15 | 20.63 | BSE (as first filed) | TRITONV_Q3FY26; 3:1 bonus (April 2026) restated it later to 5.15 |
| TRITONV | Q4FY26 | EPS | 7.03 | 7.03 (=) | 28.11 | 7.03 | BSE | TRITONV_Q4FY26; scanned PDF (OCR); after the bonus; tijori 28.11 is 4 times too high (not adjusted) |
| VADILENT | Q3FY25 | EPS | -212.25 | -212.24 (=) | -212.91 | -212.25 | BSE | VADILENT_Q3FY25; EPS agrees with -18.31, not -42.94 |
| VADILENT | Q3FY25 | profit | -42.94 | -18.00 | -18.31 | -18.31 | **BSE WRONG** | VADILENT_Q3FY25; BSE file adds a -24.63 'discontinued' profit that the statement does not have; XBRL ProfitLossForPeriod -42.94 |
| VELJAN | Q3FY26 | EPS | 10.31 | 11.24 | 11.24 | 11.24 (consolidated) | **BSE WRONG** | VELJAN_Q3FY26 (own file); BSE's 10.31 is the standalone EPS; XBRL carries it in the consolidated filing |
| VIRAT | Q1FY26 | EPS | 0.98 | 0.61 | 0.61 | 0.98 | BSE | VIRAT_Q1FY26; screener 0.61, tijori 0.6087 recompute on weighted shares |
| ZFSTEERING | Q3FY25 | EPS | -1.91 | -0.95 | -0.95 | -1.91 | BSE | ZFSTEERING_Q4FY25; same |
| ZFSTEERING | Q3FY25 | profit | -1.73 | -2.00 (=) | -0.86 | -1.73 | BSE | ZFSTEERING_Q4FY25; tijori -0.86 owners' share |
| ZFSTEERING | Q4FY25 | EPS | 2.66 | 4.27 | 4.27 | 2.66 | BSE | ZFSTEERING_Q4FY25; statement divides total profit; screener and tijori divide owners' profit |
| ZFSTEERING | Q4FY25 | profit | 2.41 | 2.00 (=) | 3.87 | 2.41 | BSE | ZFSTEERING_Q4FY25; tijori 3.87 owners' share |

## Result of the statement check

| verdict | lines |
|---|---|
| BSE right (the statement prints BSE's figure) | 82 |
|   of which BSE as first filed, and the statement or its capital column shows the share count changed later | 13 |
|   of which another source differs from the printed figure (owners' profit, standalone, 10 times, no printed figure, or a later share count the statement does not mention) | 45 |
|   of which the other source only recomputes the figure (EPS, 2% or less, or rounded EPS) | 24 |
| **BSE wrong** (screener and tijori had the statement's figure in all of them) | 4 |
| Definition (neither side wrong) | 1 |
| Unsure among the lines read (first filing of the quarter not read) | 2 |
| Unsure because the statement was not read | 15 EPS lines (listed below) |

## BSE figures found wrong

**4 figures, 4 company-quarters, none of them a reading error of ours: in each case the company's own XBRL (the file BSE publishes) carries a figure that its own PDF statement does not.** I fetched the four XBRL files again and read the tags.

| company | quarter | basis | line | BSE file | correct (statement) | evidence |
|---|---|---|---|---|---|---|
| ECORECO (Eco Recycling) | Q4FY25 | consolidated | profit | 3.42 | 2.20 | PDF `0047672d` (OCR of the consolidated page): profit before tax 627 lakh, tax 288 + (3) + 122 prior-year, profit after tax 220 lakh. XBRL `Integrated_Finance_Ind_As_530643_1062025234722.xml`: TaxExpense 28,500,000 (leaves out the 1.22 Cr prior-year tax), ProfitLossForPeriod 34,200,000. Screener 2.20 and tijori 2.08 (owners) have the statement's figure. Its EPS 1.19 matches the printed EPS. |
| VADILENT (Vadilal Enterprises) | Q3FY25 | standalone | profit | -42.94 | -18.31 | PDF `5f92d39f`: net profit -18.31 Cr and EPS -212.25; the statement has no discontinued operation. XBRL `Main_Ind_As_519152_3112025174535.xml`: ProfitLossFromDiscontinuedOperationsAfterTax -246,300,000, ProfitLossForPeriod -429,400,000, while EPS stays -212.25 (which is -18.31 over 8.63 lakh shares). Screener -18 and tijori -18.31 are right. |
| PRADPME (Pradeep Metals) | Q4FY26 | consolidated | profit | 15.83 | 10.32 | PDF `e40783f6`: profit before tax 1,307.44 lakh, tax (275.52) lakh, profit 1,031.92 lakh; EPS 5.98. XBRL `Integrated_Finance_Ind_As_513532_165202621228.xml`: TaxExpense -27,552,000 (sign wrong), ProfitLossForPeriod 158,296,000 = 130,744,000 + 27,552,000. Screener 10.32 and tijori 10.319 are right. |
| VELJAN (Veljan Denison) | Q3FY26 | consolidated | EPS | 10.31 | 11.24 | PDF `75b5e969` (own filing, 11 Feb 2026): consolidated EPS 11.24 (profit 505.72 lakh); 10.31 is the standalone EPS in the same filing. XBRL `Integrated_Finance_Ind_As_505232_112202614112.xml` carries 10.31 in the consolidated filing. Screener 11.24 and tijori 11.2378 are right. Profit 5.06 and revenue 36.92 are right. |

Not wrong but worth knowing: BSE's file for **Deccan Gold** revenue takes net sales only (0.59 Cr against the statement's total income from operations of 9.34 Cr, Q4FY26; the same shape in Q2FY25, Q2FY26 and Q3FY26, not read: BSE revenue is total income less other income there too); and **Onix Solar** Q4FY26 consolidated is the revised result of 26 Oct 2026 (revenue 76.61, profit 15.08, EPS 6.02, checked in the revised statement), not the older figures screener holds.

The four wrong figures are 4 of the 1,776 pairs compared (0.2%) and sit in 4 of the 598 company-quarters (0.7%); the earlier tests found 2 wrong in 273 pairs (Kovai, one company-quarter). All four are profit or EPS lines, none a revenue line. Each would pass a check against any other copy of the same XBRL, which is why it took the statement to find them.

## Not settled (statement not read, EPS only)

These stay leads. Each differs from screener or tijori and fits no pattern, and none of these companies was read for EPS in another quarter. Also unsure, read but the quarter's own first filing not opened: Systematix Q2FY25 EPS (BSE 17.06, restated comparative 1.71) and Bajaj Steel Q2FY25 EPS (BSE 33.83, restated comparative 8.46); in both BSE's figure is exactly the old share count times the restated figure, which fits the first filing being before the split or bonus.

| company | quarter | basis | BSE | screener | tijori | note |
|---|---|---|---|---|---|---|
| EFCIL | Q2FY25 | cons | 7.35 | 2.70 | - |  |
| FERMENTA | Q2FY26 | cons | 6.48 | 6.14 | - |  |
| FERMENTA | Q4FY26 | cons | 6.66 | 6.52 | - |  |
| MAFATIND | Q4FY26 | cons | 2.43 | 2.49 | 2.49 |  |
| NITTAGELA | Q1FY26 | cons | 21.65 | 21.11 | 21.12 |  |
| NITTAGELA | Q2FY26 | cons | 20.81 | 20.30 | 20.29 |  |
| SHRJAGP | Q4FY26 | cons | 9.98 | 10.23 | 9.97 (=) |  |
| YOGI | Q4FY26 | cons | 0.84 | 0.92 | - |  |
| BNAGROCHEM | Q1FY27 | cons | 0.03 | 0.30 | - |  |
| BNAGROCHEM | Q3FY25 | cons | 9.88 | 9.61 | - |  |
| BNAGROCHEM | Q4FY25 | cons | 3.49 | 1.97 | - |  |
| FISCHER | Q4FY25 | cons | 0.09 | 0.02 | - | same 5 times ratio as Q2FY25 and Q3FY25; tiny figures |
| MERCURYEV | Q4FY26 | cons | 0.00 | 0.02 | - |  |
| PRAVEG | Q4FY25 | cons | 1.31 | 1.55 | - |  |
| RAJOOENG | Q2FY25 | cons | 0.64 | 0.48 | 0.48 |  |

## Limits

- Screener and tijori probably share a vendor and mostly copy the exchange's XBRL. A wrong XBRL figure that both copy the same way cannot be seen here. The four found were visible only because both had read something else (the PDF figure).
- 19 of the 92 companies have no tijori page found by name (ALGOQUANT, BELDING, BNAGROCHEM, COCKERILL, EFCIL, FEDDERSHOL, FERMENTA, FISCHER, GRANDOAK, GYFTR, IIRM, MERCURYEV, ONIXSOLAR, PRAVEG, PRIMO, RIR, TCC, WELSPLSOL, YOGI); tijori's slug is not the symbol, so slugs were matched on the company name from the sitemap (69 matched by name, 4 more by hand: AKCAPIT, JYOTIRES, VELJAN, UPHOT) and the page's own symbol or name was checked. Tijori has a value for 476 of the 590 revenue pairs.
- Only revenue, profit and EPS were compared. Total income, PBT, tax, depreciation and the other 25 lines of the CSV were not (apart from the internal checks below).
- No corporate-action data was used. "Share count changed later" is inferred from a ratio that is a round number (1.5, 2, 2.5, 3, 4, 5, 10, 20) or the same across a company's quarters; it was read in the statements of 7 companies. For the others in that class it is a pattern.
- The pattern classes (share count, owners' profit, recompute, same company read) cover 106 of the 183 EPS differences against screener and 101 of the 152 against tijori. They are leads. A wrong BSE EPS inside such a class would be hidden by the pattern; of the 64 EPS lines read in statements, BSE was right in 61, unsure in 2 and wrong in 1 (Veljan); that is evidence, not proof.
- 15 EPS lines were not read and fit no pattern (listed above); more are in the "same company read" class. The cap of about 40 files was passed (47), to settle first-filing figures that the first file showed only restated and to read the three lines where both other sources disagreed with BSE.
- Statements read by OCR (scanned or garbled text layer; OCR can drop or swap a digit, so a line was taken only where the printed figure matched BSE's or another column to the digit, or the table's arithmetic held): Triton Q4FY26, Jaykay Q4FY25 (page 21), TCC Q2FY26 (page 11), Eco Recycling Q4FY25 (page 15), Investment & Precision Q1FY26, Deccan Gold Q4FY26, Fedders Q3FY25 and Q2FY25 (page 8), Aryaman Q3FY25 (page 6), Shilchar Q3FY25, Bharat Seats Q2FY25, Kilburn Q3FY26, Agarwal's Q2FY26. CIFL's consolidated page has a text layer that misreads one digit (9,044 for 3,044); the revenue was settled by the sum and by total income less other income. Lines whose files were not opened (for example Bajaj Steel Q4FY25 and Q4FY26, Nitta Gelatin Q1FY26 and Q2FY26 EPS) stay in the lead classes.
- BSE client retries are not counted. The XBRL files and PDFs are the files BSE served; the company PDF is the referee, and a company's own PDF can differ from its XBRL (all four wrong figures).
- Internal check on the CSV itself (no outside source): profit = profit before tax - tax + associates + discontinued operations holds in 564 of the 590 company-quarters that carry all of those lines. The other 26: 25 have a negative tax line with profit above profit before tax (real tax credits in most cases; the one read, Pradeep Metals, was a sign error), and 1 does not add up (Shukra Pharma Q3FY26 consolidated, profit 20.36 against 21.98; not read). They are leads, not proofs.

## Requests made (27 Oct 2026)

- screener.in: 99 requests, 99 answered 200, no refusal. At least 2.3 seconds apart, plain browser User-Agent, only `/company/<SYMBOL>/` and `/company/<SYMBOL>/consolidated/`. No `/company/source/` URL was opened.
- tijori: 74 requests (the sitemap once, 73 company financials pages), 74 answered 200, no 403, 429 or 503. At most about 1.8 requests a second (0.55 s between them). No slow-down was needed.
- BSE (for the statements): 107 requests, about 54 announcement lists, 49 PDF downloads (2 of them 404, my typo in one file name, then corrected), 4 XBRL files; the repo's adapter (`adapters/bse.py`, its own headers and pace of 4 to 6 seconds), no refusal.

## Open, for the owner

- The four wrong figures are already in memory (both batches were applied). By the routine in `docs/DATA_QUALITY.md` they are fixed as a class in code with a test, not by hand. The scrip codes: Eco Recycling 530643 (Q4FY25), Vadilal Enterprises 519152 (Q3FY25), Pradeep Metals 513532 (Q4FY26), Veljan Denison 505232 (Q3FY26). `bse_gap_fill.KNOWN_WRONG` skips a quarter for the BSE fill, as it does for Kovai; whether to add these is the owner's call. Nothing was changed here.
- A check that sends every profit difference of more than 1 Cr between a filled figure and screener or tijori to the statement would have found three of the four (Eco Recycling, Vadilal, Pradeep Metals) from the money lines alone. Veljan came out through the EPS check. Not built.
- EPS: 69% agreement with screener is not a quality measure. A fair EPS check needs the share count at the time of the filing (dated corporate actions) so that split and bonus quarters can be set aside.
- Whether the full run (no cap) goes ahead: on the lines read, BSE's figures are right except these four (and one definition, Deccan Gold revenue). The rate is 4 of 598 company-quarters (0.7%).
