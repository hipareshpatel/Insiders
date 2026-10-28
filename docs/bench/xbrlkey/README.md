# The XBRL-key locator against the hand answer keys

Measured 28 Oct 2026, locally, on the PDFs of `docs/bench/normalpdf/key.csv` (337 printed figures, 50 ordinary statements) and
`docs/bench/hardpdf/key.csv` (340 figures, 21 hard PDFs). Read only, no network, no OCR. Code: `pipeline/src/bse_intel/xbrl_key.py`;
the script that makes this table: `pipeline/scripts/xbrl_key_vs_handkey.py`; every figure's result is in `locator-vs-normal-key.csv` and
`locator-vs-hard-key.csv` (the key's value is handed to the locator as the "XBRL value").

## What is measured, and what is not

The hand keys have no coordinates: a key row is (filing, basis, period, metric, value) and, for the normal key only, the page. The
locator already conditions on the metric (row label), the period (column header) and the basis, so a `found_unique` is at the key's row,
column and basis *by construction*. What can be checked independently is (1) the page (normal key) and (2) for a miss, whether the
value is in the page's words at all (the text layer holds it, in any printed unit) and which stage lost it. That is what is reported.
For the hard key there is no page, so a `found_unique` there is checked only by its arithmetic and by the value itself.

## Result

| | normal key (337) | hard key (340) |
|---|---|---|
| `found_unique` | 93 (27.6%) | 134 (39.4%) |
| `found_ambiguous` | 79 | 95 |
| `row_found_other_value` | 0 | 3 |
| `not_found` | 125 | 60 |
| `no_text` | 40 | 48 |

Normal key, the 93 `found_unique`: 87 on the key's page; 5 on another page that also holds the value on the key's page (the
statement printed twice, or its segment table); **1 on another page that does not** (Gael consolidated revenue 1,450.73: its segment
table, page 13, while the statement page 9 has no readable figure; the note says "the table names only 1 metric"). No unique
placement had a wrong value, by construction.

Precision of `found_unique` where it can be checked (normal key): 92 of 93 are the key's figure on the key's page or on a page that
also prints it. The hard key's 134 cannot be checked for place.

Recall ceiling without OCR, normal key: the text layer holds the value (in some unit, on the key's page) for 263 of 337 figures
(78%); for 74 (22%) the value is not in the words at all (garbled or missing text layer) and no word-position locator can find it.
The locator proves its place for 93 of those 263 (35%); the other 79 ambiguous ones are placed but not proven.

Failure stage of every figure not found or only weakly placed (`failure_stage`):

| stage | normal | hard |
|---|---|---|
| `not_in_text_layer` | 62 | 47 |
| `no_statement_page` | 43 | 0 |
| `unit_unknown` | 10 | 0 |
| `in_text_wrong_place` | 128 | 151 |

By text layer (normal key): born-digital PDFs 28 of 32 unique (the other 4: Tata Elxsi, whose dates wrap over three lines); OCR text layers 42 of 143; garbled text layers 23 of 122; no text layer 0 of 40
(`no_text`). By unit: crore 53 of 155, lakh 20 of 115, million 20 of 67.

## Where it misses (examples, all in the CSVs)

- OCR layers misread the header dates ("30.09.202S", "31.03.2", "30-0'l-2025", "Vear Ended"): the column cannot be proven, so the figure is
  `found_ambiguous` (the value is on a plausible row, the column is not). Kanplas, Crompton consolidated, Aegis Vopak, ALOK.
- OCR layers garble the row label ("Re\.enue from operations", "Rրvenue fr,un opcrai;nns", "Protltaltor tax"): the row is not recognised
  (`not row`). Aegis Vopak, Newgen, SPL Petro.
- Unusual headers: "Period Ended" (not a quarter/half/nine/year word), a date wrapped over three lines (Tata Elxsi), dates not in the
  standard order (Kanplas).
- No basis word on the page while the document names "consolidated" elsewhere (Orient Cement): the basis is unknown, the figure ambiguous.
- Banks: a bank prints no revenue from operations; memory has `interest_earned` for it, and the harness retries a bank's "revenue" as
  interest earned (the key's own convention). Memory's own `revenue` for a lender is whatever its XBRL file tagged.
- Two lines of one table can print the same figure (Profit after tax, Profit for the period): taken as one figure (the lower line).
- 3 `row_found_other_value` in the hard set are Bajaj Holdings consolidated figures printed in lakh on a page that declares crore (the
  note says so) or a figure printed twice in the row's column.

## Weak spots

1. The header rule is strict by design: a column counts only when its parent heading ("Quarter ended") was read from the page's words,
   one a column or one over its run, or the standard layout agrees with the headings read. Before the rule was added the normal key gave
   103 unique and the hard key 141, but with columns guessed from the nearest date; the strict rule drops about 10 and 7 figures of those and
   the heading-less layouts, which is what the lead asked for.
2. No OCR: a scan is `no_text`. 40 + 48 of the key figures are in that class.
3. Born-digital PDFs are 28 of 32 here, which is the most useful number for the live key; the OCR-layer and garbled-layer numbers are low
   and will pull the whole key's share down. The share of born-digital filings among the live ones is not measured here.
4. Unit: the last declaration above the row on the page, else the previous page's, else the document's first; with none, every unit is tried
   and the printed unit is marked `?`. A page that declares two units for two tables is read per table (nearest above); a figure that
   matches only in another unit is reported as `row_found_other_value` with a note.
5. The statement/segment tie-break (a table that names three or more metrics and no "segment" heading wins) is a rule of thumb: it can
   take the statement for a segment table that carries a profit line.
