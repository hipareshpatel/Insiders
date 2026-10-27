# Native PDF reader on the normal-results key: baseline before any fix (27 Oct 2026)

Read-only measurement. Nothing was changed, committed or written to a database. Reader: the "native" reader (`pdf_referee.read_document` + `figure_for`, wrapped by `pdf_readers.NativeReader`, local RapidOCR on scanned pages, OCR on, the vision route never used), main at 27 Oct 2026. Key: `docs/bench/normalpdf/key.csv`, 337 printed figures (11 `not_printed` rows skipped), 50 PDFs. Scoring is the hard-set rule of `pdf_bench.py` unchanged: right = within half a unit of the printed decimals (at least 0.005 crore) of the printed figure; "no answer" = the reader gave no figure (none, conflict, other basis only, error). Two states: (a) `PDF_DATES_2DIGIT`, `PDF_PAGE_RANK`, `PDF_ROW_FIXES` all 0 (live pipeline); (b) all 1 (maintenance).

## Result

| | right | wrong | no answer |
|---|---|---|---|
| (a) live flags, all 337 figures | 35 (10.4%) | 1 (0.3%) | 301 (89.3%) |
| (b) maintenance flags, all 337 figures, code before PR #199 | 40 (11.9%) | 0 | 297 (88.1%) |
| (a) revenue + pat only (165 figures the reader can answer) | 35 (21%) | 1 | 129 (78%) |
| (b) revenue + pat only, code before PR #199 | 40 (24%) | 0 | 125 (76%) |

Answered 36 figures in (a): 35 right, 1 wrong (2.8% of what it answered). Answered 40 in (b) (pre-#199): all right. Filings with at least one answer: 17 of 50 in (a), 21 of 50 in (b, with #199).

CORRECTION (28 Oct): an earlier version of this section called state (b) not repeatable (40 right on one run, 45 on another). That was wrong. The checkout's `pdf_referee.py` was replaced by the PR #199 revisions at 19:13 UTC while the runs were going, so the first (b) run used the code before #199 (40 right) and the rerun used the code with it (45). The headline (b) rows above and the pass-mark table are the pre-#199 code (40); the detailed tables further down for (b) come from the rerun with #199 (45). State (a) is unchanged by #199 and was identical on two runs. See the section at the end.

## Pass marks (set before scoring: at least 98% right, at most 5% no answer, at most 1 wrong in 100)

| mark | (a) | (b) |
|---|---|---|
| at least 98% right | 10.4%: FAIL | 11.9%: FAIL |
| at most 5% no answer | 89.3%: FAIL | 88.1%: FAIL |
| at most 1 wrong per 100 | 0.3 per 100: pass | 0: pass |

Only the wrong-rate mark is met, and only because the reader says nothing when unsure. Even on the two metrics it can answer, it answers about 1 figure in 4.

Note: the by-metric, by-basis, by-unit, by-tag and by-reason tables below for state (b) were made from the rerun, which already had the #199 code (45 right). The pre-#199 (b) differs only in the 7 figures listed in the last section.

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

## After PR #199 (merged 28 Oct 00:48 IST, commit 97e2a23): state (b) rescored alone, twice, and the repeatability check

Code: `git archive` of origin/main a940049 (the reader modules are the same as at 97e2a23) in a scratch folder; the pre-#199 code is a `git archive` of 97e2a23^ (a502761). The run script asserts which copy was imported. Each run alone on the machine, one after another, all three switches 1, `python -I`, same key, same 50 PDFs.

| run | code | right | wrong | no answer | revenue + pat |
|---|---|---|---|---|---|
| old | before #199 (a502761) | 40 (11.9%) | 0 | 297 | 40/0/125 of 165 |
| new 1 | main a940049 | 45 (13.4%) | 0 | 292 | 45/0/120 of 165 |
| new 2 | main a940049 | 45 (13.4%) | 0 | 292 | 45/0/120 of 165 |

(1) What #199 changed on the normal set: +5 right, 0 wrong, no answer 297 to 292. By metric: revenue 20 to 24 right, pat 20 to 21. By basis: standalone 22 to 27, consolidated 18 to 18. Still 13% right against the 98% mark and 87% no answer against the 5% mark; total_income and pbt are still 0 of 172. State (a) is untouched by #199 (35/1/301 before and after).

Seven figures changed between the old and the new code, all in six filings:

| figure | key | before #199 | after #199 |
|---|---|---|---|
| SRF standalone revenue | 3,808.61 | conflict (rows differ: 3,718.1 and 3,808.61) | right |
| VISL standalone revenue | 1,069 | conflict (rows differ: 1,045 and 1,069) | right |
| HUHTAMAKI standalone revenue | 768.84 | conflict (rows differ: 748.13 and 768.84) | right |
| TBZ standalone revenue | 705.35 | none ("no unit declared above the row") | right |
| TBZ standalone profit | 15.43 | none (same reason) | right |
| TBZ consolidated revenue and profit | 705.35 / 14.27 | none ("basis not told") | other basis only (the reader now sees the standalone table and says the figure is printed on the standalone basis only; still no answer) |

All five gains match what #199 lists: garbled unit lines (TBZ) and revenue/profit label fixes that drop the second, wrong row (SRF, VISL, HUHTAMAKI).

(2) Repeatability: the two new runs are identical figure for figure (status, value and note of all 337 pairs; 0 differences). The old code run is identical to the first (b) run made earlier (0 differences). So (b) is repeatable when nothing else runs, and the earlier flips were not noise: they were the code change landing mid-session (file replaced at 19:13 UTC; the first (b) run started before it, the rerun after it). No OCR thread, page order, timing or cache effect was seen. (Run times were 22 minutes each alone, against about 50 minutes when two runs shared the machine; the results did not depend on it.)

Files (scratch, not committed): `scratchpad/normalscore/new_b1.json`, `new_b2.json`, `old_b1.json`, run scripts `scripts/run_state2.py`, `scripts/cmp.py`.
