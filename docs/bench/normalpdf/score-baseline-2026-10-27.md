# Native PDF reader on the normal-results key: baseline before any fix (27 Oct 2026)

Read-only measurement. Nothing was changed, committed or written to a database. Reader: the "native" reader (`pdf_referee.read_document` + `figure_for`, wrapped by `pdf_readers.NativeReader`, local RapidOCR on scanned pages, OCR on, the vision route never used), main at 27 Oct 2026. Key: `docs/bench/normalpdf/key.csv`, 337 printed figures (11 `not_printed` rows skipped), 50 PDFs. Scoring is the hard-set rule of `pdf_bench.py` unchanged: right = within half a unit of the printed decimals (at least 0.005 crore) of the printed figure; "no answer" = the reader gave no figure (none, conflict, other basis only, error). Two states: (a) `PDF_DATES_2DIGIT`, `PDF_PAGE_RANK`, `PDF_ROW_FIXES` all 0 (live pipeline); (b) all 1 (maintenance).

## Result

| | right | wrong | no answer |
|---|---|---|---|
| (a) live flags, all 337 figures | 35 (10.4%) | 1 (0.3%) | 301 (89.3%) |
| (b) maintenance flags, all 337 figures | 45 (13.4%) | 0 | 292 (86.6%) |
| (a) revenue + pat only (165 figures the reader can answer) | 35 (21%) | 1 | 129 (78%) |
| (b) revenue + pat only | 45 (27%) | 0 | 120 (73%) |

Answered 36 figures in (a): 35 right, 1 wrong (2.8% of what it answered). Answered 45 in (b): all right. Filings with at least one answer: 17 of 50 in (a), 21 of 50 in (b).

Run to run noise: state (a) gave identical results on two runs. State (b) did not: the first run (made while the (a) run used the same machine) scored 40 right, the rerun alone scored 45. Seven figures flipped (Standalone revenue of SRF, VISL, HUHTAMAKI: "conflict" to right; TBZ standalone revenue and profit: none to right; TBZ consolidated: none to other-basis). The cause was not traced; OCR or page choice is not fully repeatable under load. The tables below use the second (alone) runs. Treat (b) as 40 to 45 right.

## Pass marks (set before scoring: at least 98% right, at most 5% no answer, at most 1 wrong in 100)

| mark | (a) | (b) |
|---|---|---|
| at least 98% right | 10.4%: FAIL | 13.4%: FAIL |
| at most 5% no answer | 89.3%: FAIL | 86.6%: FAIL |
| at most 1 wrong per 100 | 0.3 per 100: pass | 0: pass |

Only the wrong-rate mark is met, and only because the reader says nothing when unsure. Even on the two metrics it can answer, it answers about 1 figure in 4.

## Metrics the reader cannot answer at all

- `total_income` (85 figures) and `pbt` (87 figures): 0 answers in both states. `parse_page` only builds rows for revenue, pat and eps; there is no row type for either. (It does use a "Total income" line as revenue when a table has no revenue-from-operations line; that is a revenue answer, not a total_income answer.)
- That is 172 of 337 figures (51%) that can never be answered in its current form.

By metric (right/wrong/no answer):

| metric | (a) | (b) |
|---|---|---|
| revenue (79) | 18/1/60 | 24/0/55 |
| pat (86) | 17/0/69 | 21/0/65 |
| total_income (85) | 0/0/85 | 0/0/85 |
| pbt (87) | 0/0/87 | 0/0/87 |

By basis (all metrics): (a) standalone 19/1/165, consolidated 16/0/136; (b) standalone 27/0/158, consolidated 18/0/134.

By unit printed (revenue + pat answered of asked): (a) crore 15 of 75, lakh 11 of 56, million 10 of 34; (b) crore 21, lakh 13, million 11.

## By tag (right/wrong/no answer, all 337 figures; half of every tag's figures are pbt or total_income, so the ceiling is about 50%)

| tag | (a) | (b) |
|---|---|---|
| born_digital | 6/0/26 | 6/0/26 |
| scanned_ocr_text_layer | 17/0/126 | 24/0/119 |
| scanned_garbled_text_layer | 7/1/114 | 10/0/112 |
| scanned_no_text_layer | 5/0/35 | 5/0/35 |
| poor_scan | 3/0/33 | 3/0/33 |
| lakh | 11/0/104 | 13/0/102 |
| million | 10/0/57 | 11/0/56 |
| printed_as_lacs | 0/0/22 | 2/0/20 |
| indian_digit_grouping | 5/0/26 | 5/0/26 |
| whole_unit_figures | 2/0/52 | 3/0/51 |
| associate_line_before_pbt | 1/0/31 | 1/0/31 |
| lender | 0/0/24 | 4/0/20 |
| bank, insurer | 0/0/7 | 0/0/7 |
| mixed_document | 3/1/36 | 5/0/35 |
| long_pdf | 2/1/15 | 2/0/16 |
| landscape | 6/0/31 | 6/0/31 |
| rotated_page | 4/0/4 | 4/0/4 |
| bases_identical | 0/0/8 | 4/0/4 |

Worst tags (nothing answered in either state): nil_as_dash, statement_spans_two_pages, minority_lines, title_mismatch, pat_above_pbt, side_by_side_bases, printed_total_off_by_rounding, standalone_in_note_skipped, total_income_line_absent, unusual_statement_layout, bank, insurer. With revenue + pat only, the weakest tags with 10 or more figures are lender (0 of 11 in (a), 4 of 11 in (b)), printed_as_lacs (0 of 10 / 2 of 10), associate_line_before_pbt (1 of 16 in both), whole_unit_figures (3 of 27), broker (1 of 8). Best: rotated_page 4 of 4, bases_identical (b) 4 of 4. By page kind (revenue + pat, answered of asked): born digital 6 of 16, OCR text layer 24 of 69 (17 in a), garbled text layer 10 of 60 (8 in a), no text layer 5 of 20. Even born-digital pages are answered only 6 of 16 times.

## Why there is no answer (state b, 120 unanswered revenue + pat figures)

- 67: the reader found no metric row at all ("no row" 34, "no results row" 33). 29 of 50 filings give nothing in (b), 33 in (a). Examples: ATUL (0 rows), GROWW (born digital; the text layer puts one cell per line and the date header is split over several lines, so only one stray row on page 3 is built, and it has 1 figure for 2 dates).
- 16: the figure was found only on the other basis (the table's basis was read wrongly, or the page prints one basis).
- about 25: "the table's basis is not told" on every table of the filing.
- about 11: row figure count differs from the header's date count (SONACOMS: 6 figures, 2 dates read; TMCV: header dates read as 22 and 23 October, the signing dates).
- 3: no unit declared above the row; 1: decimals missing in a garbled layer; 1: only "Total income" printed; 1: two rows differ (conflict).

## Wrong figures

State (a): one.

| filing | basis | metric | key (crore) | reader returned (crore) | where it sits |
|---|---|---|---|---|---|
| GAEL | STANDALONE | revenue | 1,451.33 (page 3, "Revenue from Operations") | 1,468.30 | page 12, a table labelled standalone, the "Total Income" row, taken as revenue because that table's revenue-from-operations row was not read. 1,468.30 is the key's own standalone total_income (page 3). Tags: scanned_garbled_text_layer, mixed_document, long_pdf. |

State (b): none. `PDF_ROW_FIXES` turns that case into "only Total income printed, no answer".

## Method notes

- Script: `scratchpad/normalscore/scripts/run_state.py` (Ensemble of the `native` reader, `pdf_bench.answer_pair` and `pdf_bench.outcome`, reused unchanged; settings built after setting the three flags, checked by assertion). Run with `python -I`, one process a state, PDFs from `scratchpad/normalkey/pdfs/` (all 50 present, none downloaded again). The reader's own verdict rule (`settle`) was not used because it needs two reader families; each reading is scored directly, as `pdf_bench` scores each reader.
- Readings: `scratchpad/normalscore/readings_a_rerun.json`, `readings_b_rerun.json` (first runs `readings_a.json`, `readings_b.json`).
