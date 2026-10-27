# Why the readers fail on the hard set (diagnosis, measured 27 Oct 2026)

Read-only diagnosis. No code, data or database was changed. Two puzzles from `hardset-readings.json` (340 figures, 21 PDFs, 11 readers):

1. Nine PDFs where no reader got any figure right (152 figures).
2. Rows where two or more readers agreed on one value and all were wrong (23 rows, 4 PDF/basis groups).

## How this was measured

- The 12 PDFs were downloaded once each from the NSE archive (browser User-Agent and Referer, one request at a time). The page text layer was read with PyMuPDF and each statement page was rendered and looked at.
- **Benchmark code** = the code before F215, i.e. commit `e559bcb^`, with `PDF_DATES_2DIGIT`, `PDF_PAGE_RANK` and `PDF_ROW_FIXES` off. Our own reader (`read_document` + `figure_for`) on this code gave **0 right, 0 wrong, all "none" on all nine PDFs** (152 of 152). That matches the benchmark's `native` column, so these runs reproduce the benchmark.
- **HEAD+flags** = current `HEAD` (`1f0e1ae`) with the three F215 flags on. Our reader on it: PNBHOUSING 20 of 20 right, CENTRUM 10 of 20, PRIMESECU 2 of 20, the other six 0. No wrong answers survive `reading_of` (see PRIMESECU).
- The ten table readers (camelot ... surya) only see the pages that `pdf_readers.statement_pages` picks (at most 4). Under benchmark code the picked pages were:

| PDF | pages picked (benchmark code) | real statement page(s) | hit? | picked with flags on |
|---|---|---|---|---|
| INDOSTAR | none (scan, 25 pages, limit is 12) | 5 | no | 3,4,5,6 (hit) |
| UNIONBANK | none | 3 (standalone), 5 (consolidated) | no | none (still no) |
| PNBHOUSING | 5,9,13,18 | 2, 10 | no | 2,9,10,18 (hit) |
| PRIMESECU | 4,12,14,21 | 8, 17 | no | 4,8,12,17 (hit) |
| REPCOHOME | 2,3 | 2 | yes | 2,3 |
| CENTRUM | 5,16 | 6, 14 | no | 5,6,9,14 (hit) |
| SPANDANA | 2,5,8,10 | 4, 12 | no | 2,4,9,12 (hit) |
| BFINVEST | 4 | 2, 3 | no | 2,3,4 (hit) |
| SUNDARMFIN | 2,3,4,6 | 3, 4 | yes | same |

So for **7 of the 9 PDFs (116 of 152 figures) the ten table readers were never shown the statement page.** F215's page rank fixes 6 of those 7.

## Puzzle 1: the nine PDFs

Units are as printed. "Expected line" is the line label on which the key's figure sits. Evidence lines say which run showed it.

| PDF | Statement page(s) | Layout facts | Expected line | Most likely reason (benchmark code) | Evidence |
|---|---|---|---|---|---|
| **INDOSTAR** (8) | p5 standalone only (consolidated review report is p10). Scan, 25 pages, p3-22 and p25 have no text layer at all | Portrait 612x792, slightly tilted, 6 columns: 3 quarters, 2 half-years, 1 year. Rs lakh. Standalone only | `Total revenue from operations` (23,418 lakh = 234.18 cr); `5 Profit/(loss) after tax (3-4)` (1,051 lakh) | **Basis not recognised.** Our OCR reads every row and figure correctly, but the bold title ("STATEMENT OF STANDALONE ...") comes out as `STAEG E S O O2E`. Page 1 of the PDF names "Consolidated", so the "no word means standalone" default is off. All 8 answers: `the table's basis is not told`. The ten table readers never get the page (scan over 12 pages) | Run: rows found (23,418 / 24,121 / ... / 96,888, columns proven) and `basis=None`. Counterfactual with basis set to standalone: 4 of 4 profit figures right. The revenue figure then still fails: the heading `(a) Revenue from operations` is joined to the next line `interest income 21,742 ...`, which gives a second revenue row (217.42 against 234.18): "other" cause |
| **UNIONBANK** (16) | p3 standalone, p5 consolidated (p4, p6 are ratio pages). Each is a scan with a garbled embedded text layer | /Rotate 270 pages (render upright 594x838). 6 columns: 3 quarters, 2 nine-months, 1 year. Rs lakh in Indian grouping (26,95,793). Standalone and consolidated on separate pages | `1 Interest Earned (a)+(b)+(c)+(d)` = 26,95,793 lakh = 26,957.93 cr. Profit: `J. Net Profit/(Loss) for the period (H-I)` = 4,60,363 | **No usable text layer, so the page is not found.** The layer reads `Strndrlono Unludltod Flnrnclal RetulB`, dates `31.12.2021`, numbers `7t.12,7E6`. No page passes the date-header test, so the ten readers get no page. Our reader never looks at p3/p5 (no "quarter / year ended" word in the layer) and reads the segment pages p7/p8 instead, where "Income from operations" is total income, basis not told | Run: `statement_pages` = [] on both code versions; native rows are p7/p8 only (3,137,450 lakh = total income). Forced OCR of p3 is perfect (all 6 columns of both lines). Even on perfect OCR text, 2 label problems remain: revenue figures are on the line `(a)+(b)+(c)+(d)` under a label-only line `1 Interest Earned`, and `_PAT_NAME` does not match `J.` / `H.` prefixes. Result: revenue falls to `A. TOTAL INCOME` (31,374.5, wrong) and profit gives nothing |
| **PNBHOUSING** (20) | p2 consolidated, p10 standalone (p18 is a one-line "Net Profit After Tax" summary with no basis) | /Rotate 270, 600x845, text is column by column. Embedded OCR layer (slips like `34.1O`). 5 columns: 3 quarters + 2 years. Rs crore. Bases on separate pages | `Total revenue from operations` (row I); `VII Net profit after tax (V-VI)` | **Period headers not recognised.** The headers print `31-Mar-23`, `31-Dec-22` (two-digit year). The date matcher needs a four-digit year unless `PDF_DATES_2DIGIT` is on, so no row finds a header (benchmark rows: only p18). Table readers also miss p2 and p10 | Run: benchmark code finds 2 rows (p18), HEAD+flags finds 8 rows and **20 of 20 figures right**. Layout fits: header on separate lines, rows rebuilt by position |
| **PRIMESECU** (20) | p8 consolidated, p17 standalone. Born-digital (no image on p8, p17) | Portrait. Text layer lists every cell on a line of its own, labels last. 5 columns. Rs lakh. Dates `31-Mar-24` (two-digit) | Revenue is `I Revenue from Operations` with one sub-line `Fee and commission income` (1,136 lakh = 11.36 cr) and no total line (`revenue_label_definition`). Profit: `IX Profit after tax (VII-VIII)` (165) | **Period headers not recognised** (two-digit year), then **label**: with dates on, the only revenue row left is `III Total income (I+II)` (12.82 against 11.36), which `reading_of` drops as "only Total income printed". Standalone p17 is also never read by our reader: it is the 13th page with a "quarter / year ended" word and the cap is 12 (`MAX_PAGES`) | Run: benchmark code 0 rows. HEAD+flags: 3 rows, p8 only, revenue = total income, profit right for FY only (2 of 20 right); quarter profit cells are `no figure under the period's column`. Page count check: p17 is the 13th qualifying page |
| **REPCOHOME** (16) | p2 only (one landscape page, 837x596). Scan with a garbled embedded text layer (`I naudited`, `X45.57`) | **Standalone and consolidated side by side: one 12-figure row** (6 + 6 columns). Title: "UNAUDITED STANDALONE AND CONSOLIDATED FINANCIAL RESULTS". Rs crore. Header says Quarter, Period, Year Ended twice | `Total revenue from operations` (435.93 in column 1 and column 7); `7 Net profit for the period / year (5-6)` standalone, `9 Profit after tax and share of profit from associate` consolidated | **Columns/basis: two bases in one row.** The title names both bases, so the row has no basis (`basis not told`, 16 of 16). The row has 12 dates, and `figure_for` finds 2 columns for each date. `_pattern_kinds` only knows 4, 5 or 6 columns | Run: row read exactly right (`435.93, 415.25, 387.3, 1259.01, 1131.94, 1524.52` twice), `basis=None`, `cols=no`. Same on HEAD+flags (0 of 16) |
| **CENTRUM** (20) | p6 consolidated, p14 standalone (p10 is a consolidated segment table; p5 is the audit report) | Portrait 596x842 scans with embedded OCR layer (`Audiled`, `lrading`, `t ,31,005.90` for 1,31,005.90). 5 columns. Rs lakh, 2 decimals. Dates `31-Mar-24` | `Total revenue from operations` (65,484.55 lakh); profit consolidated `8 Net Profit/(Loss) for the period/year (6+7)`, standalone `5. Profit/(Loss) for the period/year (3-4)` | **Period headers not recognised** (two-digit year) and **page not found** for the table readers (picked 5 and 16, the audit report and the cash flow). Two more faults wait behind: unit line on p6 reads `Ct In Lakhs}`; and the standalone revenue heading joins its first sub-line | Run: benchmark code finds 3 rows (p14, no header). HEAD+flags: 10 of 20 right; 5 standalone revenue conflict (`1. Revenue from operations a. Fees and commision` row gives 19.95 against 22.25); 5 consolidated profit `no unit declared above the row`. Cons revenue is right only via the p10 segment table |
| **SPANDANA** (16) | p4 standalone, p12 consolidated | Portrait scans with embedded OCR. Column-by-column text: labels, then three quarter columns, then half-years, then the year. 6 columns. Rs crore. Dates `30-Sep-24` (two-digit) | `Total revenue from operations` (640.36); `VII Profit/(Loss) after tax (V-VI)` (-203.93) | **Period headers not recognised** (two-digit year), then **unit not recognised.** The unit line is `(" in crores unless otherwise stated)`: the rupee sign came out as `"` and the `unless otherwise stated` tail defeats the bare-unit fallback. HEAD+flags reads every row right and still gives 0 of 16 | Run: benchmark 0 rows; HEAD+flags 9 rows, columns proven, then `no unit declared above the row` on p4 and p12. Direct test of `unit_before` on the three unit strings: `(" in crores ...` -> None, `f{ in crorest` -> None, `Ct In Lakhs}` -> None, `(Rs.in Lakhs ...` -> 100. Also: consolidated p12 prints 610.27 for Q2FY24 revenue (key 610.26), and profit has two rows 216.33 / 216.32 that differ by 0.01 |
| **BFINVEST** (16) | p2 standalone, p3 consolidated | Scan with embedded OCR, 599x842. **Header dates are split over two lines** (`September 30,` above `2024`; `March 31,` above `2024`). 6 columns. Rs million. The revenue total is **not printed** (three sub-lines: interest, dividend, fair-value gain), key = their sum | Revenue: no line (key 73.81 cr = 57.46 + 655.73 + 24.86 million). Profit: `9 Profit/ (loss) after tax (7- 8)` (493.47 million = 49.35 cr) | **Period headers not recognised** (a date is never on one line). No row is found on any page, even with the flags on. After that: revenue can never be read as a line (only `Total income (1+2)` = 745.07 would appear, wrong) | Run: benchmark and HEAD+flags both "rows 0, no results row found" (`_dates_in` on the header line returns no date). The page text shows the split. `statement_pages` benchmark picks p4 only |
| **SUNDARMFIN** (20) | p3 standalone, p4 consolidated | Scans with garbled embedded text: cells merged (`1570.46724.32`, `67,53120.49`), text runs column by column. 5 columns. Rs crore. Titles and unit garbled | `Total Revenue from Operations` (1571.69); profit standalone `9 Profit/(loss) after tax (PAT)`; consolidated `12 Profit/(loss) after tax(PAT)` (472.41), row 9 `PAT` (388.64) is before associates | **Unit and basis not recognised in garbled text.** p3 unit line is `f{ in crorest` (no unit). p4 title is `STATEMENTOFAUDITEDCONSOLIl)ATEDFINANCIALRESULTS` (no basis). Then: two "PAT" rows on p4 (388.64 and 472.41) conflict | Run: benchmark code and HEAD+flags give the same: rows rebuilt by position are right (1571.69, 1345.76, ...); p3 `no unit declared above the row`; p4 `the table's basis is not told`. 0 of 20 |

### Grouped summary of causes (nine PDFs, 152 figures)

First blocker for our own reader, benchmark code. Each figure is counted once.

| Cause | PDFs | Figures |
|---|---|---|
| Period headers not recognised (two-digit year `31-Mar-24`; year split from the day on another line) | PNBHOUSING 20, PRIMESECU 20, CENTRUM 20, SPANDANA 16, BFINVEST 16 | **92** |
| Unit or title garbled in the text layer (unit not recognised, basis not recognised) | SUNDARMFIN 20 | 20 |
| Basis not recognised (title lost by OCR, or both bases in one title and one 12-figure row) | INDOSTAR 8, REPCOHOME 16 | 24 |
| No usable text layer; statement page not found | UNIONBANK 16 | 16 |

Second lens, for the ten table readers: **statement page never given to them in 7 PDFs = 116 figures** (table above).

Causes hidden behind the first blocker, still open on HEAD+flags (figures that stay "none"):

| Cause | Figures (HEAD+flags) |
|---|---|
| Unit line not recognised (`" in crores unless otherwise stated`, `f{ in crorest`, `Ct In Lakhs}`) | SPANDANA 16, SUNDARMFIN 10 standalone, CENTRUM 5 = 31 |
| Basis not recognised or two bases side by side | INDOSTAR 8, REPCOHOME 16, SUNDARMFIN 10 consolidated = 34 |
| Revenue or profit label not matched, wrong fallback line, joined heading | UNIONBANK 16, PRIMESECU 18, CENTRUM 5, INDOSTAR 4 revenue = 43 |
| Header dates split across lines | BFINVEST 16 |
| Fixed by F215 flags on the benchmark PDFs | PNBHOUSING 20, CENTRUM 10, PRIMESECU 2 (32 figures) |

## Puzzle 2: rows where 2 or more readers agreed and were all wrong

23 rows, 4 groups (the earlier estimate was "about 10"). Every wrong value was found on the page and sits in the same period column as the right one. Two mechanisms.

### Mechanism A (15 rows): the "Total Income" line was read as revenue

| Group | Rows | Readers that agreed | Wrong value sits on | Why |
|---|---|---|---|---|
| AIIL standalone revenue, p17 | 5 | tatr + surya (native, tabula, docling were right) | line `Total Income` (903.11 = 886.01 revenue + 17.10 other income) | The page prints only "Revenue from operations", "Other Income", "Total Income". These two readers kept the "Total Income" row and not the revenue row. Inference: Table Transformer and Surya were not run here; the five wrong values equal the printed Total Income of each column exactly |
| VLSFINANCE consolidated revenue, p13 | 5 | native, paddle, surya | line `Total Income (a+b)` (10,054.78 lakh = 100.5478 against 9,807.71 lakh on `Total (a)`) | The revenue total is labelled `Total (a)`, under the heading `(a) Revenue from Operations`. That label is not a revenue label, so the best revenue-like line left is `Total Income (a+b)` |
| VLSFINANCE standalone revenue, p10 | 5 | native, pdfplumber, paddle, marker, surya (mineru read 3.81, the interest sub-line) | line `Total Income (a+b)` (9,994.03 lakh against 9,754.03 on `Total (a)`) | Same as above |

Evidence: on the benchmark code our reader returns `Total Income (a+b)` rank 2 for VLS (13 and 10), values 100.55 and 99.94. With `PDF_ROW_FIXES` on, `reading_of` returns "none: only 'Total income' printed" for the same rows (run). So F215 turns the 10 VLS rows into abstentions. The AIIL rows are expected to follow if the two readers had no revenue row, not tested.

### Mechanism B (8 rows): the other basis, read under the wrong title

| Group | Rows | Readers that agreed | Wrong value sits on | Why |
|---|---|---|---|---|
| EMKAY consolidated revenue and profit (4 + 4) | 8 | camelot, tabula, rapidtable, paddle (native was right on revenue, native had a conflict on profit) | p12, the box `STANDALONE INFORMATION` at the top of the consolidated "Statement of assets and liabilities" page: revenue 10,068.76, profit after tax 2,456.33 (lakh), same period columns as p11 | p12 has one title, `CONSOLIDATED UNAUDITED STATEMENT OF ASSETS AND LIABILITIES`. A table without its own title takes the page's title, so the standalone box is read as consolidated. `STANDALONE INFORMATION` is not a title line for the code (`_TITLE` needs results, statement, financial, profit or particulars) |

Evidence: I fed the p12 box as a table grid to `tables_to_rows` with the page's layers. The row comes out `basis=CONSOLIDATED`, and `figure_for(Q2FY25, revenue, CONSOLIDATED)` returns 100.6876 and profit 24.5633, the same values as the four readers (run, benchmark and HEAD code). F215 did not touch this path. The other seven values are the standalone box values for Q1FY25, Q2FY24 and FY24 (75.6902, 63.4936, 252.0917; 13.5346, 7.4999, 24.4699).

## Fix ideas, each testable on this set

1. **Turn the three F215 flags on and keep the page rank for the table readers.** Test: re-run `pdf-referee-ensemble hardset`; expect PNBHOUSING 20 of 20, CENTRUM 10 more, `statement_pages` containing the page in the first table for 8 of 9 PDFs.
2. **Unit and basis lines in garbled text.** Accept a unit word within the three lines after the title when the line is short, ignore a wrong glyph or a trailing `unless otherwise stated`, and allow letters after `crore` (`crorest`). Test: `unit_before` and `_bare_unit` return the right unit for the three strings above (SPANDANA 16 and SUNDARMFIN 10 start to read). For a lost title on a scan, take the basis from the nearest title word of the statement's page range, or from the order of the review reports.
3. **Revenue and profit labels.** (a) Do not join a heading that is itself a revenue label with its first sub-line (INDOSTAR and CENTRUM conflicts). (b) Treat `Total (a)` under a `Revenue from operations` heading as revenue. (c) Allow letter prefixes (`J.`, `H.`) in `_PAT_NAME`. (d) Read a figure line under a label-only `Interest Earned`. Test: INDOSTAR revenue 4 of 4, CENTRUM standalone revenue 5 of 5, VLS 10 revenue rows right, UNIONBANK after OCR.
4. **Basis of a table without a title.** Never inherit the page title when the table's own first cell names the other basis (`STANDALONE INFORMATION`). Test: EMKAY p12 simulation returns no consolidated value (removes 8 agreed-wrong rows).
5. **Header dates.** Join `September 30,` with a following line that holds only years (BFINVEST) and read side-by-side bases as two column blocks (REPCOHOME). Test: `_dates_in` on BFINVEST p2 gives 6 dates; REPCOHOME row yields one value per basis.
6. **Garbled text layer (UNIONBANK).** Treat a page whose layer holds no recognisable period words but is an image-covered page as scanned, so it goes to OCR (forced OCR on p3 was exact).

Scratch files: `/tmp/claude-0/-home-user-Insiders/da2b9981-89ea-5c08-8427-7ebe29cc22f4/scratchpad/pdfdiag/` (PDFs in `pdfs/`, scripts in `scripts/`, run outputs in `out/`).
