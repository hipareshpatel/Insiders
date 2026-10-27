# Three fixes to the PDF results reader, measured on the hard set (27 Oct 2026)

Branch `pdf-reader-fixes`. Not pushed. The diagnosis is `docs/bench/hardpdf/why-readers-fail.md`; the key is `key.csv` (340 figures, 21 PDFs).

## In plain words

- We read the 21 hard PDFs with our own reader (the "native" one) three ways and counted each figure against the key.
- **With the three F215 switches off** (what the live pipeline runs): 65 right, 10 wrong, 265 no answer. All 10 wrong are VLS Finance, where the reader took "Total Income" for revenue.
- **With the three switches on, before these fixes** (what `maintenance.yml` runs): 104 right, 0 wrong, 236 no answer.
- **With the three switches on and these fixes**: 155 right, 1 wrong, 184 no answer. That is 51 more right than (b).
- **The one wrong figure is the key's fault, not the reader's.** SPANDANA, consolidated, Q2 FY24 revenue: the PDF prints 610.27 (checked on the page image); the key says 610.26 (the XBRL value). The reader gave 610.27. If the key is set to the printed 610.27, the score is 156 right, 0 wrong. I did not change the key.
- **The fixes sit behind `PDF_ROW_FIXES`.** With the switches off, the code gives the same answer on all 340 figures as before (compared figure by figure: no change at all).
- **One right figure was lost** (CENTRUM, consolidated, FY23 revenue, from right to no answer). Reason below. It cannot become a wrong figure.

## How it was measured

- The 21 PDFs come from `pdf_url` on the NSE archive (browser User-Agent, `Referer: https://www.nseindia.com/`, one request at a time). 9 were reused from the diagnosis, 12 downloaded today. No file was under 50 KB. They are kept in their own folder and read with `python -I`.
- The reader is `NativeReader` through `Ensemble(["native"])`: `read_document` (text layer, local OCR on scanned pages and pages of figures) then `reading_of`, the same path the readers benchmark scores as its `native` column. No AI call, no database.
- Right = within half a unit of the printed decimals, at least 0.005 crore (`pdf_bench.outcome`). A conflict between two rows or a missing proof counts as no answer.
- State (a): `PDF_DATES_2DIGIT`, `PDF_PAGE_RANK`, `PDF_ROW_FIXES` all 0. State (b) and (c): all 1. (a) and (b) ran on the code before the change, (c) on the new code. (a) was run again on the new code: the same 340 outcomes and values.
- The OCR engine gives the same text for the same page image, so each page image was read once and the text shared by all runs (a memo around `ocr.recognise` in the scoring script only; the product code is untouched).

### Totals (right / wrong / no answer, of 340 figures)

| State | right | wrong | no answer |
|---|---|---|---|
| (a) all three switches off | 65 | 10 | 265 |
| (b) all three on, before the fixes | 104 | 0 | 236 |
| (c) all three on, with the fixes | 155 | 1 | 184 |


### Per PDF (right / wrong / no answer)

| PDF | figures | (a) off | (b) on, before | (c) on, with fixes |
|---|---|---|---|---|
| 360ONE | 20 | 5 / 0 / 15 | 5 / 0 / 15 | 5 / 0 / 15 |
| ABCAPITAL | 10 | 5 / 0 / 5 | 5 / 0 / 5 | 5 / 0 / 5 |
| AIIL | 20 | 18 / 0 / 2 | 18 / 0 / 2 | 18 / 0 / 2 |
| ARMANFIN | 20 | 10 / 0 / 10 | 10 / 0 / 10 | 20 / 0 / 0 |
| BAJAJHLDNG | 20 | 10 / 0 / 10 | 10 / 0 / 10 | 10 / 0 / 10 |
| BFINVEST | 16 | 0 / 0 / 16 | 0 / 0 / 16 | 0 / 0 / 16 |
| CENTRUM | 20 | 0 / 0 / 20 | 10 / 0 / 10 | 19 / 0 / 1 |
| EMKAY | 16 | 4 / 0 / 12 | 8 / 0 / 8 | 8 / 0 / 8 |
| FIVESTAR | 8 | 0 / 0 / 8 | 0 / 0 / 8 | 0 / 0 / 8 |
| GEOJITFSL | 12 | 3 / 0 / 9 | 6 / 0 / 6 | 6 / 0 / 6 |
| INDOSTAR | 8 | 0 / 0 / 8 | 0 / 0 / 8 | 0 / 0 / 8 |
| J&KBANK | 16 | 0 / 0 / 16 | 0 / 0 / 16 | 0 / 0 / 16 |
| KARURVYSYA | 10 | 0 / 0 / 10 | 0 / 0 / 10 | 0 / 0 / 10 |
| PNBHOUSING | 20 | 0 / 0 / 20 | 20 / 0 / 0 | 20 / 0 / 0 |
| PRIMESECU | 20 | 0 / 0 / 20 | 2 / 0 / 18 | 2 / 0 / 18 |
| RBLBANK | 16 | 0 / 0 / 16 | 0 / 0 / 16 | 0 / 0 / 16 |
| REPCOHOME | 16 | 0 / 0 / 16 | 0 / 0 / 16 | 0 / 0 / 16 |
| SPANDANA | 16 | 0 / 0 / 16 | 0 / 0 / 16 | 12 / 1 / 3 |
| SUNDARMFIN | 20 | 0 / 0 / 20 | 0 / 0 / 20 | 10 / 0 / 10 |
| UNIONBANK | 16 | 0 / 0 / 16 | 0 / 0 / 16 | 0 / 0 / 16 |
| VLSFINANCE | 20 | 10 / 10 / 0 | 10 / 0 / 10 | 20 / 0 / 0 |



## The three fixes, one by one

All behaviour changes are in `pipeline/src/bse_intel/pdf_referee.py`, each guarded by `_row_fixes()` (`PDF_ROW_FIXES`). Tests: `pipeline/tests/test_pdf_row_fixes.py` (52 tests, real text from the diagnosis; every test that checks a change fails on the old code with the switch on and passes now; the tests that check "nothing else moves" pass on both).

### 1. Garbled unit lines

- New `_garbled_units` / `_garbled_unit`. A unit line is accepted when it is short, has no digit, starts with a little junk or a lost rupee sign, then `in`, then **crore, lakh, lac, million or thousand**, then at most two stray letters, then at most a short tail starting with "unless", "except" or "other". Real lines now read: `(" in crores unless otherwise stated)` (SPANDANA), `f{ in crorest` and `r{ in crores` (SUNDARMFIN), `Ct In Lakhs} (except per equtty share dala}` (CENTRUM), `(~ in crores unless otherwise st ated)`, `(" in lakhs}`.
- Never a guess: `(in rupees)`, `( in crorepati)`, `(in lakhstan)`, `in millionaire terms`, `(in kg)`, a line with a figure in it, a sentence that has "in crores" in the middle, an empty line, and two different units near the header (a garbled one and a clean one) all give **no unit**, so the figure abstains.
- It runs only when the page's own unit finder found nothing, and the clean unit lines (`_bare_unit`) must agree with it.
- Result: SPANDANA +12 right, SUNDARMFIN +10, CENTRUM consolidated profit +5, minus the CENTRUM FY23 case below.

### 2. Basis of a boxed table

- New `_basis_above_boxed`. A short heading line with no figures that names a basis ("STANDALONE INFORMATION") and stands between the row and the page title that names the other basis takes the table out of the title's basis: **basis none, so no figure**, on either basis. It is not defaulted to standalone either. A heading that agrees with the title changes nothing; a heading with no title above it is not used.
- Test on the real EMKAY p12 text and grid (the simulation of the diagnosis): before, a consolidated question got 100.6876 and 24.5633 (the standalone box's revenue and profit, wrong); now both abstain.
- **No effect on the native score**: native already left that box unread (its text starts with the box, so no title was above it). The error was in the table readers' path (`tables_to_rows`, which puts the page title above the table). I could not run those readers here (camelot, tatr and the rest are not installed), so this fix is shown by the simulation only.

### 3. Labels

- **3a. A revenue heading is not joined to its first sub-line.** The wrapped-label rule joined `(a) Revenue from operations` with `interest income 21,742 ...` (INDOSTAR) and `1. Revenue from operations` with `a. Fees and commision Income` (CENTRUM), making a second, wrong revenue row. Now a line that is itself a revenue-from-operations or interest-earned label is never joined, and a next line that starts with its own `a.` / `ii.` is never a wrapped tail. A real wrap (`Total income from` / `operations 1,000.50 ...`) is still joined. Result: ARMANFIN +10 right (the same joined row), CENTRUM +9.
- **3b. `Total (a)` under `(a) Revenue from Operations` is revenue** (VLS Finance). Only when a heading `(x) Revenue from Operations` is above it with nothing but sub-lines between (no other total, no `(b)` step). `Total (b)` or a `Total (a)` after a `(b)` step is not. VLS: +10 right; "Total Income (a+b)" is no longer the revenue.
- **3c. A letter or roman prefix before the profit label** (`J.`, `H.`, `iii.`, `(c)`). Unit-tested (`J. Net Profit/(Loss) for the period (H-I)` now reads; `J. Profit before tax`, `K. Other comprehensive income for the period`, `Earnings per share for the period` still do not). **No effect on the native score**: UNIONBANK's statement page is still not found (a scan with a garbled text layer), so no UNIONBANK figure changed.
- **3d. "Total income" is never revenue when a revenue line exists: nothing is added beyond the old same-table rule, and a page with only "Total income" is left alone.** The old rule (one revenue line a table: revenue from operations, else interest earned, else total income) already drops the total-income row of a table that has a revenue row, with the switch off or on (unit-tested on the AIIL layout). Two attempts to go further were taken out after review: a heading-without-figures rule left Titan's page in restated-pdf with no row at all ("no results row found"), and a cross-table drop turned a conflict into a wrong figure (table A "Total Income" 903.11, table B a segment's revenue 100.00 on the same page and basis: off gives two values and no answer, the drop gave 100.00). Now a page whose only revenue line is "Total income" keeps that row, so `reading_of` and `verdict_of` give the explicit "only 'Total income' printed"; two tables with different revenue figures stay a conflict. **No effect on the native score** (AIIL 18 / 0 / 2 in all three states).

### A narrowing the measurement forced

The first run of the fixes gave 4 wrong, not 1. Three were SPANDANA consolidated **profit**: the page has `VII Profit / (Loss) after tax` (216.33) and, after the non-controlling share, `IX Profit / (Loss) for the period / year (VII-VIII)` (216.32; FY24 500.72 against 500.66). The existing F215 tie-break ("the line called profit for the period is the bottom line") took IX, the owners' share; the key wants VII. The unit fix had only uncovered it (before, SPANDANA had no unit and abstained). Narrowed: with the switch on, a "for the period" line printed as one line less another, `(VII-VIII)`, is no tie-break, so two rows that differ stay a conflict and the figure abstains. Lines that add a later line (`(7+8)` GEOJIT, `(XI+XIV)` EMKAY) are still the tie-break; none of the 7 rights that depend on it moved. After this: 1 wrong (the key figure above).

## What each fix adds (taken out one at a time from the full set)

Done on a copy of the new code with only that fix removed; right / wrong / no answer, against (c) = 155 / 1 / 184.


| Fix taken out | right | wrong | no answer | so the fix adds |
|---|---|---|---|---|
| 1. garbled unit lines | 129 | 0 | 211 | +26 right, +1 wrong |
| 2. basis of a boxed table | 155 | 1 | 184 | +0 right, +0 wrong |
| 3a. revenue heading not joined to its first sub-line | 136 | 1 | 203 | +19 right, +0 wrong |
| 3b. 'Total (a)' is revenue | 145 | 1 | 194 | +10 right, +0 wrong |
| 3c. letter or roman prefix before the profit label | 155 | 1 | 184 | +0 right, +0 wrong |
| 3d. total income never revenue (now the same-table rule only) | 155 | 1 | 184 | +0 right, +0 wrong |
| narrowing: a 'for the period (VII-VIII)' line is no tie-break | 155 | 4 | 181 | +0 right, -3 wrong |


### Every figure that changed from (a) to (b), the three existing switches

- **CENTRUM**, abstain -> right, 10: Cons FY23 revenue (key 1310.06; none -> 1310.06); Stan FY23 profit (key -72.37; none -> -72.37); Cons FY24 revenue (key 2206.81; none -> 2206.81); Stan FY24 profit (key -51.34; none -> -51.34); Cons Q3FY24 revenue (key 575.378; none -> 575.38); Stan Q3FY24 profit (key -20.84; none -> -20.84); Cons Q4FY23 revenue (key 394.36; none -> 394.36); Stan Q4FY23 profit (key -11.54; none -> -11.54); Cons Q4FY24 revenue (key 654.85; none -> 654.85); Stan Q4FY24 profit (key -5.79; none -> -5.79)
- **EMKAY**, abstain -> right, 4: Cons FY24 profit (key 32.44; none -> 32.44); Cons Q1FY25 profit (key 13.87; none -> 13.87); Cons Q2FY24 profit (key 9.27; none -> 9.27); Cons Q2FY25 profit (key 25.91; none -> 25.91)
- **GEOJITFSL**, abstain -> right, 3: Cons Q1FY24 profit (key 22.08; none -> 22.08); Cons Q2FY23 profit (key 23.76; none -> 23.76); Cons Q2FY24 profit (key 37.48; none -> 37.48)
- **PNBHOUSING**, abstain -> right, 20: Cons FY22 profit (key 836.48; none -> 836.48); Cons FY22 revenue (key 6195.93; none -> 6195.93); Stan FY22 profit (key 821.92; none -> 821.92); Stan FY22 revenue (key 6141.09; none -> 6141.09); Cons FY23 profit (key 1046; none -> 1046.00); Cons FY23 revenue (key 6527.33; none -> 6527.33); Stan FY23 profit (key 1056.27; none -> 1056.27); Stan FY23 revenue (key 6490.55; none -> 6490.55); Cons Q3FY23 profit (key 269.13; none -> 269.13); Cons Q3FY23 revenue (key 1796.51; none -> 1796.51); Stan Q3FY23 profit (key 272.25; none -> 272.25); Stan Q3FY23 revenue (key 1787.22; none -> 1787.22); Cons Q4FY22 profit (key 169.54; none -> 169.54); Cons Q4FY22 revenue (key 1425.42; none -> 1425.42); Stan Q4FY22 profit (key 169.96; none -> 169.96); Stan Q4FY22 revenue (key 1414.16; none -> 1414.16); Cons Q4FY23 profit (key 279.28; none -> 279.28); Cons Q4FY23 revenue (key 1635.71; none -> 1635.71); Stan Q4FY23 profit (key 282.91; none -> 282.91); Stan Q4FY23 revenue (key 1626.81; none -> 1626.81)
- **PRIMESECU**, abstain -> right, 2: Cons FY23 profit (key 11.18; none -> 11.18); Cons FY24 profit (key 18.56; none -> 18.56)
- **VLSFINANCE**, wrong -> abstain, 10: Cons FY23 revenue (key 82.06; 84.40 -> none); Stan FY23 revenue (key 75.71; 77.25 -> none); Cons FY24 revenue (key 407.02; 418.20 -> none); Stan FY24 revenue (key 399.89; 410.09 -> none); Cons Q3FY24 revenue (key 113.2; 114.75 -> none); Stan Q3FY24 revenue (key 112.42; 113.86 -> none); Cons Q4FY23 revenue (key -14.96; -13.67 -> none); Stan Q4FY23 revenue (key -15.53; -14.28 -> none); Cons Q4FY24 revenue (key 98.08; 100.55 -> none); Stan Q4FY24 revenue (key 97.54; 99.94 -> none)


### Every figure that changed from (b) to (c), the fixes of this change

- **ARMANFIN**, abstain -> right, 10: Cons FY23 revenue (key 423.9; none -> 423.90); Stan FY23 revenue (key 94.39; none -> 94.39); Cons FY24 revenue (key 661.46; none -> 661.46); Stan FY24 revenue (key 133.51; none -> 133.51); Cons Q3FY24 revenue (key 168.76; none -> 168.76); Stan Q3FY24 revenue (key 32.61; none -> 32.61); Cons Q4FY23 revenue (key 149.31; none -> 149.31); Stan Q4FY23 revenue (key 27.64; none -> 27.64); Cons Q4FY24 revenue (key 182.85; none -> 182.85); Stan Q4FY24 revenue (key 37.74; none -> 37.74)
- **CENTRUM**, abstain -> right, 10: Cons FY23 profit (key -182.94; none -> -182.94); Stan FY23 revenue (key 25.9; none -> 25.90); Cons FY24 profit (key -71.19; none -> -71.19); Stan FY24 revenue (key 57.22; none -> 57.22); Cons Q3FY24 profit (key -17.87; none -> -17.87); Stan Q3FY24 revenue (key 13.56; none -> 13.56); Cons Q4FY23 profit (key -20.75; none -> -20.75); Stan Q4FY23 revenue (key 12.74; none -> 12.74); Cons Q4FY24 profit (key 39.41; none -> 39.41); Stan Q4FY24 revenue (key 22.25; none -> 22.25)
- **CENTRUM**, right -> abstain, 1: Cons FY23 revenue (key 1310.06; 1310.06 -> none)
- **SPANDANA**, abstain -> right, 12: Cons FY24 revenue (key 2423.71; none -> 2423.71); Stan FY24 profit (key 467.88; none -> 467.88); Stan FY24 revenue (key 2299.76; none -> 2299.76); Cons Q1FY25 profit (key 55.71; none -> 55.71); Cons Q1FY25 revenue (key 709.89; none -> 709.89); Stan Q1FY25 profit (key 51.29; none -> 51.29); Stan Q1FY25 revenue (key 663.13; none -> 663.13); Stan Q2FY24 profit (key 116.32; none -> 116.32); Stan Q2FY24 revenue (key 584.31; none -> 584.31); Cons Q2FY25 revenue (key 686.38; none -> 686.38); Stan Q2FY25 profit (key -203.93; none -> -203.93); Stan Q2FY25 revenue (key 640.36; none -> 640.36)
- **SPANDANA**, abstain -> wrong, 1: Cons Q2FY24 revenue (key 610.26; none -> 610.27)
- **SUNDARMFIN**, abstain -> right, 10: Stan FY23 profit (key 1088.31; none -> 1088.31); Stan FY23 revenue (key 4046.17; none -> 4046.17); Stan FY24 profit (key 1454.01; none -> 1454.01); Stan FY24 revenue (key 5479.94; none -> 5479.94); Stan Q3FY24 profit (key 300.07; none -> 300.07); Stan Q3FY24 revenue (key 1345.76; none -> 1345.76); Stan Q4FY23 profit (key 316.36; none -> 316.36); Stan Q4FY23 revenue (key 1054.23; none -> 1054.23); Stan Q4FY24 profit (key 506.28; none -> 506.28); Stan Q4FY24 revenue (key 1571.69; none -> 1571.69)
- **VLSFINANCE**, abstain -> right, 10: Cons FY23 revenue (key 82.06; none -> 82.06); Stan FY23 revenue (key 75.71; none -> 75.71); Cons FY24 revenue (key 407.02; none -> 407.02); Stan FY24 revenue (key 399.89; none -> 399.89); Cons Q3FY24 revenue (key 113.2; none -> 113.20); Stan Q3FY24 revenue (key 112.42; none -> 112.42); Cons Q4FY23 revenue (key -14.96; none -> -14.96); Stan Q4FY23 revenue (key -15.53; none -> -15.53); Cons Q4FY24 revenue (key 98.08; none -> 98.08); Stan Q4FY24 revenue (key 97.54; none -> 97.54)


## One figure lost, one wrong by the key

- **Lost: CENTRUM, consolidated, FY23 revenue** (key 1,310.06 crore): right in (b), no answer in (c). With the unit now read on the consolidated results page (p6), its total-revenue row is a second reading of the figure, and p6's scan prints the FY23 cell as `t ,31,005.90` (the leading 1 lost), 310.06 against the p10 segment page's 1,310.06. The two readings differ, so the reader says nothing. The old "right" came from p10 alone, because p6 had no unit. Abstaining is the right behaviour for two readings that disagree.
- **Wrong by the key: SPANDANA, consolidated, Q2 FY24 revenue.** Page p12 prints `610.27` in the "Total revenue from operations" row (text layer and page image agree). The key has 610.26 (the XBRL value; the key's own rule says the printed figure wins). Our reader gave 610.27. No fix can honestly avoid it, so it is left for the lead to decide; with the key corrected to the printed 610.27 the (c) score is 156 / 0 / 184.
- The three SPANDANA profit rows that were wrong in the first run are no longer answered (see the narrowing above).

## Not done, and what is still open

- UNIONBANK (16), REPCOHOME (16), BFINVEST (16), INDOSTAR (8), J&KBANK (16), KARURVYSYA (10), FIVESTAR (8) are unchanged: page not found (scan), two bases in one row, split-line dates, a lost title, and so on (diagnosis fix ideas 5 and 6, and the INDOSTAR title). Not in the brief.
- The "label-only `Interest Earned` over a figure line `(a)+(b)+(c)+(d)`" case (diagnosis 3d) was not built: it would read a figure the page prints without a label of its own.
- PRIMESECU stays at 2 of 20: its revenue has no total line (the key tags it `revenue_total_not_printed`), and p17 is the 13th qualifying page.
- Fix 2 and the table readers: shown by the EMKAY simulation only, not by running the ten readers (not installed here).
- The diagnosis file `why-readers-fail.md` is not committed on this branch (it is untracked in the main checkout).

## Tests

From `pipeline/` of the worktree, with `PYTHONPATH` set to the worktree's `src` (the shared venv is installed in editable mode from the main checkout, so the worktree's code had to be put first):

- `python -m pytest -q -p no:cacheprovider`: 2125 passed, 4 skipped.
- The same with `BSE_INTEL_TEST_SWITCHES=live`: 2125 passed, 4 skipped.
- The same with `PDF_DATES_2DIGIT`, `PDF_PAGE_RANK`, `PDF_ROW_FIXES` and `BSE_FILL_PRE_NSE` exported as 1 in the shell: 2125 passed, 4 skipped (`tests/conftest.py` now removes those four from the environment in every test, so a shell variable never leaks in).
- After review: the restated-pdf Titan test now runs with the switch off and on; the cross-table Total-income drop was removed and a two-table test added (no figure, switch off and on). Re-scoring the hard set after each change gave the same 155 / 1 / 184 for (c) and 65 / 10 / 265 for (a).
