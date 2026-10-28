# A numbers-first reader for results statements: build and score (28 Oct 2026)

Experiment, bench only. Code: `pipeline/src/bse_intel/pdf_numbers_first.py`, registered as the reader `numfirst` in `pdf_readers.READERS`
(only `PDF_READERS=native,numfirst` selects it; the default stays `native`; it is in no live path and has no switch). Tests:
`pipeline/tests/test_pdf_numbers_first.py` (19). It is scored by the bench's own `pdf_bench.answer_pair` / `outcome` (right = within half a unit of
the printed decimals, at least 0.005 crore), the same as the native reader, on the same PDFs. Flags `PDF_DATES_2DIGIT`, `PDF_PAGE_RANK`,
`PDF_ROW_FIXES` all 1 (maintenance state), as in `score-baseline-2026-10-27.md`. Hard key: main's version of 28 Oct (SPANDANA consolidated
Q2FY24 revenue 610.27). All 50 normal PDFs and all 21 hard PDFs were local.

## What it does

1. Words with coordinates from PyMuPDF `get_text("words")`; a sideways page is turned as `extract.upright_text` turns it; a tilted page is
   straightened with `ocr._skew`. A page with no text layer is read with the pipeline's RapidOCR (`ocr`): its boxes (they carry positions)
   are cut into words in proportion to their characters. A scan whose own text layer gave no named row is read with OCR too (the layer of
   a scan is OCR output and is often garbled). OCR budget: 8 pages a PDF.
2. Number tokens first (Indian or western grouping, brackets or minus, a lone `-`, an en dash or "Nil" is nil); tokens that line up make
   columns, tokens at one height make rows; a numeric row has cells in two columns or more. A column prints one number of decimals: a
   figure with another number of decimals is dropped as garbled (row, column and page checks). A small whole number in a column of
   decimals (a "Note" column, a serial number) is label text, never a figure; in a column of whole numbers it is a figure.
3. Label stitching: the label of a row is all words left of the first column between the previous numeric row and the row's own band.
4. Column dates from the header words over each column (a date broken over two lines is joined); the kind (quarter, half year, year) from
   the nearest group phrase ("Quarter ended"...) or the standard layout of the dates (`pdf_referee._pattern_kinds`). A table gives no
   column when its kinds do not fit a standard layout, and a column of unknown kind counts only when every date was read and it is the one
   column of its date.
5. A vertical arithmetic solver over all columns: total income = the 2 or 3 rows above it; total expenses = a block of rows above it;
   profit before exceptional items = total income - total expenses; profit before tax = that plus or minus rows in between (hops of up to
   three rows, up to three hops: exceptional items, share of associates, a bank's provisions); tax = a row or a sum of rows; profit
   after tax = profit before tax - tax (plus or minus discontinued operations or an associate's share, where a label does not object).
   Each identity must hold in three columns (all, when fewer are printed), may fail in one, and must hold again in the period's own column
   before a figure is given. The label is the second signal (landmarks: total income, total expenses, profit before tax, tax, profit for
   the period, comprehensive income, continuing/discontinued ...): a label that names another line than the arithmetic does vetoes the
   row; a bare "Total" or "(I+II)" does not. The names are kept only when a label of the chain says what the arithmetic says or the chain
   runs through to a profit after tax. Two explanations of the table with two values give no answer.
6. Unit from the unit line above the table (`grounding.unit_before`, then the short garbled unit lines `pdf_referee` reads), else the
   page's one unit; no unit, no answer. Basis from the title lines above the table (`pdf_referee._basis_above_boxed`; for an OCR'd page
   whose title OCR cannot read, the title of the page's own text layer).
7. Revenue and other income are the components of total income: by position when it has two parts, by label when it has three.

Metrics it can name: revenue, other income, total income, total expenses, profit before exceptional items, profit before tax, tax, profit
after tax. The keys hold only revenue, total income, profit before tax and profit after tax (the normal key has no EPS, no other income,
no expenses, no tax; the hard key has revenue and profit after tax only), so only those four are scored. EPS is not built.

## Result

Right / wrong / no answer. Normal key: 337 figures, 50 filings. Hard key: 340 figures, 21 filings.

Normal key (`docs/bench/normalpdf/key.csv`):

| metric | native (current reader) | numfirst | combined (native first, numfirst where native gives none) |
|---|---|---|---|
| revenue (79) | 24 / 0 / 55 | 28 / 0 / 51 | 40 / 0 / 39 |
| total income (85) | 0 / 0 / 85 | 35 / 0 / 50 | 35 / 0 / 50 |
| profit before tax (87) | 0 / 0 / 87 | 34 / 0 / 53 | 34 / 0 / 53 |
| profit after tax (86) | 21 / 0 / 65 | 28 / 0 / 58 | 41 / 0 / 45 |
| all (337) | 45 / 0 / 292 | 125 / 0 / 212 | 150 / 0 / 187 |
| filings with at least one answer (50) | 21 | 22 | 29 |

(Native reproduces the baseline of `score-baseline-2026-10-27.md`, 45 / 0 / 292.) Right by numfirst where native gave no answer: 103
figures; right by native where numfirst gave none: 25. Filings that went from no answer to some answer (native none, numfirst some): 8,
ABREL, AEGISLOG, AEGISVOPAK, ATGL, GROWW, IFBIND, KANPRPLA, TMCV. With the combination, 29 of 50 filings have an answer (native 21): the
8 above. Share right: native 13.4%, numfirst 37.1%, combined 44.5%; no answer: 87%, 63%, 55.5%. The pass marks of the key (98% right,
at most 5% no answer) are met by none.

Hard key (`docs/bench/hardpdf/key.csv`, revenue and profit after tax):

| metric | native | numfirst | combined |
|---|---|---|---|
| revenue (170) | 83 / 0 / 87 | 48 / 0 / 122 | 90 / 0 / 80 |
| profit after tax (170) | 73 / 0 / 97 | 23 / 0 / 147 | 78 / 0 / 92 |
| all (340) | 156 / 0 / 184 | 71 / 0 / 269 | 168 / 0 / 172 |
| filings with at least one answer (21) | 13 | 11 | 14 |

On the hard key the new reader is worse than the current one (71 right against 156). It gives 12 figures the native reader does not (all
of FIVESTAR's answers) and misses 97 that native gets. Combined: +12, 168 of 340 (49%). The hard key is lenders and banks, almost all
scans without a text layer, in layouts that are not Schedule III (interest income, operating profit before provisions): there the chain
total income - total expenses - profit before tax often does not hold in the form the solver looks for.

## Wrong answers

Final code, both keys, all three readings: none (0 wrong of 677 figures).

During tuning the reader gave wrong answers; each was a class, fixed in the code (not by editing data), and the final run has none:

| figure | wrong value | cause | fix |
|---|---|---|---|
| IFBIND standalone revenue and total income (normal) | 150,528 for 1,505.28 and 151,254 for 1,512.54 | the OCR layer had lost the decimal point in the first column; the sums still added up in that column (150528 + 726 = 151254), so every identity held on a value 100 times too large | a row prints one number of decimals: a figure with another is dropped (row, column and page rule) |
| JKTYRE consolidated total income (normal) | 17,760.31 for 4,849.96 | a segment table (total assets - total liabilities = capital employed) adds up as total income - total expenses = profit; every label was neutral | the chain's names are kept only when a label of the chain agrees or the chain runs through to a profit after tax |
| PNBHOUSING consolidated FY23 revenue, profit after tax (hard) | 1,635.71 and 279.28 for 6,527.33 and 1,046.00 | the year column's date was unreadable ("_31-Mar-23"), so the quarter column of the same date, of unknown kind, was taken as the year | a column of unknown kind counts only when every date was read and it is the only one of its date |
| AIIL consolidated FY23 revenue (hard) | 10.98 for 624.68 | the third quarter column was given the kind "year" by the nearest group phrase (cramped header, two dates garbled) | a table whose kinds do not fit a standard layout (at most 3 quarter, 2 half year, 2 year columns) gives no column |
| KANPRPLA consolidated total income (normal, first run) | 449.15 for 240.22 | not isolated: it was in the first version, before the date, basis, page and OCR changes, and was gone at the next run; I did not keep that version to trace it | none specific. This is a reason to read the first-run behaviour as unproven |

## Why there is still no answer (by stage reached, any table of the asked basis)

Normal key (337 figures): 16 no table found at all (3 filings); 51 no table of the asked basis (basis not told, or the page is not among
the 8 OCR'd pages: ATGL, SBICARD, TATAELXSI ...); 52 no unit (the unit line is garbled or not in the text layer: NESTLEIND, SONACOMS,
VISL, ATUL); 23 the period's column is not unique or the dates are unreadable; 70 a table of the basis exists but no row is named
(garbled figures in the asked column, so the identity cannot be checked there: CREDITACC, PARIN, AVANTEL, RADICO; a layout the solver does not
know); 125 answered. Hard key (340): 42 no table of the basis, 24 no unit, 58 column not unique, 145 no row named (lenders and banks), 71 answered.

Where the figure is garbled in the period's own column the reader says nothing rather than reading it, by design. The other three
causes (page budget, unit line, header dates) are fixable parts of this first version.

## Not done / limits

- EPS (not keyed; the native reader still has it), other income, total expenses and tax are named but not scored (no key rows).
- OCR: no more than 8 pages a PDF and PDFs up to 30 pages for scans with no text layer, so a statement on a later page of a long scan
  is not found (ATGL standalone, SBICARD). No deskew beyond `ocr._skew`; a scan turned sideways is turned by `ocr.lying_flat` only. OCR is slow
  (about 8-10 s a page here, 4 cores): the 50 normal PDFs took about 20 minutes with the native reader alongside.
- Two bases side by side on one page, a table split over two pages, a unit or basis inferred from another page of the PDF: not done (each
  would be a guess without a printed proof here).
- A statement of a bank or an insurer is read only as far as the chain finds it (ICICI Bank, the hard key's banks give little).
- Tuning: the rules were written looking at the failures of the normal key; the hard key was run after the first set of rules, once with an
  earlier version (61 right, 3 wrong), and then fixed generally (above). The hard-key result is therefore not a clean hold-out. 50 and 21
  filings are small samples; 0 wrong of 677 is a measured zero, not a bound (95% upper bound about 0.5%).
- Page order and the OCR cache of the runs are in the scratch folder, not in the repository.

## Does it help?

On ordinary results statements, yes: the same scorer, 125 right and 0 wrong against 45 and 0, and total income and profit before tax, which
the current reader cannot answer at all, are answered 35 and 34 times of 85 and 87. Combined with the native reader first: 150 of 337 right (44.5%),
0 wrong, 29 of 50 filings with an answer. On the hard (lender, scanned) key it does not replace the current reader (71 against 156) and adds 12
figures in combination. It is nowhere near the 98% / 5% marks: two thirds of the normal figures still get no answer, mainly because of garbled
cells in the asked column, missing unit lines and OCR budget. Whether to keep going is a call for the owner; the code is small enough
(about 1,000 lines) to extend the page budget and the unit and header reading without touching the live path.

## Reproduce

`PDF_READERS=native,numfirst PDF_DATES_2DIGIT=1 PDF_PAGE_RANK=1 PDF_ROW_FIXES=1 python -m bse_intel.pdf_bench --run docs/bench/normalpdf/key.csv <pdf dir> <out dir>`
reads each key row with both readers through the bench path (the PDFs named as `pdf_bench.collect` stores them). The runs above used a
small driver that calls `pdf_bench.answer_pair` with an `Ensemble(["native", "numfirst"])` and a disk cache of RapidOCR's boxes.
