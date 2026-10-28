# XBRL key, the 28 figures where the row is on the page and another number is printed (28 Oct 2026)

Source: the first live run of `xbrl-key` (`xbrl-key.csv`, status `row_found_other_value`, locator `2026-10-28.3`): 28 figures of 9 filings. Each was read against its PDF from NSE (nine downloads, one at a time, 3 s apart, plain browser User-Agent, no refusal; PyMuPDF text layer, and the page image where the text layer was a scan). Memory values are as the CSV gives them (six significant digits) and, for the cases that matter, as live memory holds them on 28 Oct 2026.

## Result

| class | figures | what it means |
|---|---|---|
| XBRL_WRONG | 7 | the page prints another figure and memory holds the file's: IMPAL Q1FY27, every amount at a hundredth |
| LOCATOR_WRONG | 9 | the locator misread the page (cut words, a header it could not read, a lost decimal point); memory is right |
| DEFINITION | 12 | a different line: memory's is the taxonomy's, the page's is another line or period |
| UNSURE | 0 | |

Of the 28, 7 are wrong in memory (all IMPAL) and 21 are not. No other figure of the run was shown wrong by its page. The 12 DEFINITION rows are three kinds: the taxonomy's total expenses includes finance costs and depreciation where the statement's 'Total expenses' stops before them (STYRENIX, JNPR x2: 3 rows); the taxonomy's other income includes finance income (WEWORK: 1 row); continuing against discontinued operations (ABREL, 7 rows); and a profit before tax without the joint ventures' share (BLUESTARCO, 1 row).

## The 28 figures

| # | company | basis | period | metric | memory | page prints | class | evidence |
|---|---|---|---|---|---|---|---|---|
| 1 | BLUESTARCO | Cons | Q1FY27 | pbt | 134.79 | 134.59 | DEFINITION | p6: p6 line 7 'Profit before tax (5+6)' 134.59 = 125.42 + 9.17 and 32.08 tax + 102.51 profit; memory's 134.79 = 125.62 (before the joint ventures' share of -0.20) + 9.17: the taxonomy's profit before tax, without the share. |
| 2 | ASHOKLEY | Cons | Q1FY27 | total_expenses | 12314.7 | 12,31 (as read; page p3) | LOCATOR_WRONG | p3: p3 (scan, OCR layer) 'Total Expenses' is two words '12,31' '4.66' = 12,314.66 (the eight lines above sum to 12,314.66); memory holds 12,314.66 (the CSV rounds to six digits: 12314.7). |
| 3 | ABREL | Cons | H1FY27 | exceptional_items | 0 | 868.12 | DEFINITION | p13: The printed 868.12 is row 12/13 'Exceptional items (Refer note 2b and 3)' under DISCONTINUED OPERATIONS (the gain on the pulp and paper sale); the continuing row 6/8 'Exceptional items' prints '-'. Memory's 0 is the continuing one. |
| 4 | ABREL | Cons | Q2FY27 | exceptional_items | 0 | 868.12 | DEFINITION | p13: The printed 868.12 is row 12/13 'Exceptional items (Refer note 2b and 3)' under DISCONTINUED OPERATIONS (the gain on the pulp and paper sale); the continuing row 6/8 'Exceptional items' prints '-'. Memory's 0 is the continuing one. |
| 5 | ABREL | Cons | Q2FY27 | tax_expense | 30.48 | (73.38) | DEFINITION | p15: The printed (73.38) / (83.62) is 'Total Tax expenses' of the discontinued business (note 3 table, page 6 / 15), not the continuing tax. Continuing tax: current 11.11 + deferred 19.37 = 30.48 (p13). |
| 6 | ABREL | Stan | H1FY27 | exceptional_items | 0 | 868.12 | DEFINITION | p4: The printed 868.12 is row 12/13 'Exceptional items (Refer note 2b and 3)' under DISCONTINUED OPERATIONS (the gain on the pulp and paper sale); the continuing row 6/8 'Exceptional items' prints '-'. Memory's 0 is the continuing one. |
| 7 | ABREL | Stan | H1FY27 | tax_expense | 32.28 | (83.62) | DEFINITION | p6: The printed (73.38) / (83.62) is 'Total Tax expenses' of the discontinued business (note 3 table, page 6 / 15), not the continuing tax. Continuing tax: current 14.77 + deferred 17.51 = 32.28 (p4). |
| 8 | ABREL | Stan | Q2FY27 | exceptional_items | 0 | 868.12 | DEFINITION | p4: The printed 868.12 is row 12/13 'Exceptional items (Refer note 2b and 3)' under DISCONTINUED OPERATIONS (the gain on the pulp and paper sale); the continuing row 6/8 'Exceptional items' prints '-'. Memory's 0 is the continuing one. |
| 9 | ABREL | Stan | Q2FY27 | tax_expense | 21.67 | (73.38) | DEFINITION | p6: The printed (73.38) / (83.62) is 'Total Tax expenses' of the discontinued business (note 3 table, page 6 / 15), not the continuing tax. Continuing tax: current 12.99 + deferred 8.68 = 21.67 (p4). |
| 10 | STYRENIX | Cons | Q1FY27 | eps | 78.64 | 78.64 (first column) | LOCATOR_WRONG | p6: Scanned page with an OCR text layer. The layer reads the third column header 'Jun 30, 2026' (the image prints 'Jun 30, 2025', the year-ago column: 946.88 total income, 29.52 EPS); the first column's header 'Jun, 30 2026' has a comma the date reader did not take. The first column prints 78.64, equal to memory. |
| 11 | STYRENIX | Cons | Q1FY27 | other_income | 3.33 | 3.33 (first column) | LOCATOR_WRONG | p6: Scanned page with an OCR text layer. The layer reads the third column header 'Jun 30, 2026' (the image prints 'Jun 30, 2025', the year-ago column: 946.88 total income, 29.52 EPS); the first column's header 'Jun, 30 2026' has a comma the date reader did not take. The first column prints 3.33, equal to memory. |
| 12 | STYRENIX | Cons | Q1FY27 | pbt | 188.63 | 188.63 (first column) | LOCATOR_WRONG | p6: Scanned page with an OCR text layer. The layer reads the third column header 'Jun 30, 2026' (the image prints 'Jun 30, 2025', the year-ago column: 946.88 total income, 29.52 EPS); the first column's header 'Jun, 30 2026' has a comma the date reader did not take. The first column prints 188.63, equal to memory. |
| 13 | STYRENIX | Cons | Q1FY27 | tax_expense | 50.33 | 50.33 (first column) | LOCATOR_WRONG | p6: Scanned page with an OCR text layer. The layer reads the third column header 'Jun 30, 2026' (the image prints 'Jun 30, 2025', the year-ago column: 946.88 total income, 29.52 EPS); the first column's header 'Jun, 30 2026' has a comma the date reader did not take. The first column prints 50.33, equal to memory. |
| 14 | STYRENIX | Cons | Q1FY27 | total_expenses | 825.56 | 847.04 | DEFINITION | p6: p6 first column 'Total expenses (4)' 790.60; memory's 825.56 = 790.60 + finance costs 4.42 + depreciation 30.54, the taxonomy's total. (The locator took the year-ago column, 847.04.) |
| 15 | STYRENIX | Cons | Q1FY27 | total_income | 1014.19 | 1,014.19 (first column) | LOCATOR_WRONG | p6: Scanned page with an OCR text layer. The layer reads the third column header 'Jun 30, 2026' (the image prints 'Jun 30, 2025', the year-ago column: 946.88 total income, 29.52 EPS); the first column's header 'Jun, 30 2026' has a comma the date reader did not take. The first column prints 1,014.19, equal to memory. |
| 16 | KIRLOSBROS | Cons | Q1FY27 | total_expenses | 1024.6 | 10 (as read; page p6) | LOCATOR_WRONG | p6: p6 'Total Expenses' is two words '10' '246' = 10,246 million = 1,024.6 crore = memory; the lines above sum to 10,246. |
| 17 | JNPR | Cons | Q1FY27 | total_expenses | 280.06 | 297.23 | DEFINITION | p10: p10 'Total expenses' 297.23 million = 21.72 + 73.36 + 202.15; memory 280.06 Cr = 2,800.58 million = 297.23 + finance costs 1,758.18 + depreciation 745.17. |
| 18 | JNPR | Stan | Q1FY27 | total_expenses | 154.86 | 980.98 | DEFINITION | p4: p4 'Total expenses' 980.98 million; memory 154.86 Cr = 1,548.63 million = 980.98 + finance costs 512.15 + depreciation 55.50. |
| 19 | IMPAL | Stan | Q1FY27 | other_income | 0.1 | 9.67 | XBRL_WRONG | p2: p2, Rs in Crores, 'Other income' prints 9.67; the file's 0.1 is that at a hundredth (23,429,000 rupees for the statement's 234.29 crore: the figure typed as lakh). Earlier quarters 188-231 revenue; EPS 17.38 matches. |
| 20 | IMPAL | Stan | Q1FY27 | pat | 0.22 | 21.70 | XBRL_WRONG | p2: p2, Rs in Crores, 'Profit after tax for the period' prints 21.70; the file's 0.22 is that at a hundredth (23,429,000 rupees for the statement's 234.29 crore: the figure typed as lakh). Earlier quarters 188-231 revenue; EPS 17.38 matches. |
| 21 | IMPAL | Stan | Q1FY27 | pbt | 0.27 | 27.44 | XBRL_WRONG | p2: p2, Rs in Crores, 'Profit/ (Loss) before tax (1-2)' prints 27.44; the file's 0.27 is that at a hundredth (23,429,000 rupees for the statement's 234.29 crore: the figure typed as lakh). Earlier quarters 188-231 revenue; EPS 17.38 matches. |
| 22 | IMPAL | Stan | Q1FY27 | revenue | 2.34 | 234.29 | XBRL_WRONG | p2: p2, Rs in Crores, 'Net Revenue from Operations' prints 234.29; the file's 2.34 is that at a hundredth (23,429,000 rupees for the statement's 234.29 crore: the figure typed as lakh). Earlier quarters 188-231 revenue; EPS 17.38 matches. |
| 23 | IMPAL | Stan | Q1FY27 | tax_expense | 0.06 | 5.74 | XBRL_WRONG | p2: p2, Rs in Crores, 'Total Tax Expense' prints 5.74; the file's 0.06 is that at a hundredth (23,429,000 rupees for the statement's 234.29 crore: the figure typed as lakh). Earlier quarters 188-231 revenue; EPS 17.38 matches. |
| 24 | IMPAL | Stan | Q1FY27 | total_expenses | 2.17 | 216.52 | XBRL_WRONG | p2: p2, Rs in Crores, 'Total Expenses' prints 216.52; the file's 2.17 is that at a hundredth (23,429,000 rupees for the statement's 234.29 crore: the figure typed as lakh). Earlier quarters 188-231 revenue; EPS 17.38 matches. |
| 25 | IMPAL | Stan | Q1FY27 | total_income | 2.44 | 243.96 | XBRL_WRONG | p2: p2, Rs in Crores, 'TOTAL INCOME' prints 243.96; the file's 2.44 is that at a hundredth (23,429,000 rupees for the statement's 234.29 crore: the figure typed as lakh). Earlier quarters 188-231 revenue; EPS 17.38 matches. |
| 26 | TECHNOE | Stan | Q1FY27 | eps | 8.27 | 827 (as read; page p8) | LOCATOR_WRONG | p8: p8 (rotated scan, OCR layer): the layer prints '827'; the page image (250 dpi) prints 8.27 for basic and diluted EPS, equal to memory. The layer drops the decimal point. |
| 27 | WEWORK | Cons | Q2FY27 | total_income | 786.44 | 7 (as read; page p9) | LOCATOR_WRONG | p9: p9 'Total income' is two words '7' '864.39' = 7,864.39 million = 786.44 crore = memory (7,678.38 + 110.98 + 75.03). |
| 28 | WEWORK | Cons | H1FY27 | other_income | 35.51 | 184.61 | DEFINITION | p9: p9 'Other income' H1 184.61 million; memory 35.51 Cr = 355.09 million = other income 184.61 + finance income 170.48 (the file's other income takes in the finance income line). |

## Why IMPAL Q1FY27 passed every guard

India Motor Parts & Accessories' standalone file tags each amount at 1/100 of the statement's crore figure (23,429,000 rupees where the
page prints 234.29 crore). Memory held revenue 2.34, PAT 0.22, EPS 17.38 beside quarters of 188-231, 16-33 and 13-27. Four things let it in:

1. `xbrl.confirm` (the file's revenue or profit looked for in the PDF text in any unit) found it: 2.34 crore x 100 is 234 lakh, and `appears_in`
   compares whole numbers, so the printed 234.29 matched at the lakh scale.
2. `xbrl.scale_slip` needs the revenue and the share count (profit / EPS) to be off by the same power of ten, and `_shares` returned "unknown"
   whenever the profit was under 0.5 crore. A file at a hundredth of its value has a profit of 0.22 crore, so the share count was never
   available and the slip never confirmed. This is the gap. (A real fall keeps its shares, so the share count is what tells a slip from a
   fall; the floor was the problem, not the rule.)
3. No neighbour shield applied: the quarter before it (210.72) is not within 3x of 2.34.
4. Even a slip that had been found would not have been put right: `fix_scale` multiplied the rounded 2.34 (234.00) and the PDF check compares
   with the printed 234.29 to a rounding, so the quarter would have been held, not corrected.

## What changed in the code

- `xbrl._shares`: the profit floor is 0.001 crore, not 0.5. With the share count available, IMPAL's revenue (10^2) and shares (10^2) agree.
- `XbrlResult.exact_values`, `balance_exact`, `balance_prior_exact`: the file's own figures before the two-decimal rounding. `scale_slip`
  reads the share count from them, `fix_scale` asks the PDF for the unrounded figure times the factor (234.29, not 234.00) and corrects
  every crore amount from them: the statement's figures, the memory-only ones (the profit to minorities), the balance sheet and its earlier
  date (the last two were not moved before). The factor stays a power of ten, applied only when the PDF text layer prints the corrected
  revenue; otherwise the quarter is held out of memory and logged, as before.
- `known_wrong.py`: IMPAL Q1FY27 standalone, 7 proven figures and 10 sibling lines of the same file (the statement's lines and our own EBITDA).
- `xbrl_key.py` (locator `2026-10-28.4`): `_mend_numbers` puts back figures cut in two words; a month followed by a comma ("Jun, 30 2026") is a date;
  two columns of one table with the same date and heading and no basis between them are not proven; a discontinued business's exceptional
  item and tax are not the company's; a lost decimal point ("827" for 8.27) is named in the note.

Re-run of the locator on the 28 figures after the changes: the 9 LOCATOR_WRONG rows no longer say the page prints another figure (KIRLOSBROS,
WEWORK total income, ASHOKLEY: found_unique; STYRENIX 5: found_ambiguous, the page's duplicated header date named; TECHNOE: noted as a lost decimal
point); ABREL's 7 are `not_found` (the continuing exceptional row prints '-', and the page has no continuing total tax line); the 12 DEFINITION
rows and IMPAL's 7 are unchanged (BLUESTARCO, STYRENIX total expenses, JNPR, WEWORK other income: another line; IMPAL: another figure).

## Left alone, and why

- The three taxonomy definitions (total expenses with finance costs and depreciation, other income with finance income, profit before tax
  without the joint ventures' share) are memory's by design. They show as `row_found_other_value` in every future key run. A later locator
  version could try the printed line plus finance costs and depreciation (and finance income, and the associates' share) before reporting another
  value; not done here.
- Memory still holds IMPAL's slipped Q1FY27 as of the live read of 28 Oct 2026. `memory-drop-known-wrong` removes it; `seed-memory --scrips 590065`
  writes the corrected quarter (it needs NSE's PDF for the check).
