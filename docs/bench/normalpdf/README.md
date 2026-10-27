# Normal-PDF answer key (TODO 112)

337 printed figures from 50 ordinary results-statement PDFs that the live pipeline received between 1 and 27 October 2026. Built 27 October 2026, read only: no database was touched and nothing was changed in the pipeline. This is the first step of TODO 112 ("make the PDF reader reliable on results statements"): an answer key now, scoring later.

The older hard set (`docs/bench/hardpdf/`) is deliberately extreme. This key is the opposite. It is a random sample of what actually arrives, so it shows how hard the everyday file is.

## What is in the key

`key.csv` has the same columns as the hard set, plus two at the end: `symbol, scrip (blank), period_end, period, basis, metric, expected_cr, unit_printed, pdf_url, tags, page, card_value`.

- `metric` is one of `revenue` (revenue from operations), `total_income`, `pbt` (profit before tax), `pat` (profit for the period, total, before minority).
- `basis` is STANDALONE or CONSOLIDATED, as the page prints it. Where a page prints both, both are keyed.
- `expected_cr` is what the page prints, converted to crore exactly (lakh divided by 100, million divided by 10). A loss is negative.
- `unit_printed` is the unit the page prints (crore, lakh or million). `page` is the PDF page (counted from 1) that holds the figure.
- `card_value` is the number on our published card for the same filing, basis and metric, in crore. It is blank when the card has no such number. It is there as a second witness only. The page is always the answer.
- A line the page does not print has a blank `expected_cr` and the tag `not_printed`. Nothing is ever computed. A scorer should skip these rows (they are not figures to answer). Example: a bank prints no "revenue from operations".
- 348 rows in total, of which 337 are printed figures and 11 are `not_printed`.

Figures by basis: 185 standalone, 152 consolidated. By metric: revenue 79, total income 85, profit before tax 87, profit for the period 86. By unit printed: crore 155, lakh 115, million 67. Quarter: 48 of the 50 filings are the quarter ended 30 Sep 2026 (Q2FY27); 2 are late June-quarter results (Q1FY27, German Green Steel and SRIT).

## How the sample was drawn

1. Source: the public feed of our site (`/api/feed?range=all`), read to the end of September. It gave 1,750 cards. I kept cards with category RESULTS, a PDF on nsearchives, filed 1 to 27 October 2026, and size LARGE, MID or SMALL. That is 392 filings from 338 companies (LARGE 121, MID 98, SMALL 119 companies). Two cards had no size or MICRO and were left out.
2. One filing per company, picked at random with seed 112 (some companies filed more than once).
3. Each size group was shuffled with the same seed. I walked the three groups in turn (large, mid, small, large, ...) and downloaded the PDFs one request at a time, with a pause. Rule: take the next company in the list. If its PDF holds no results statement, drop it and take the next. I stopped when the groups were 17 large, 17 mid and 16 small.
4. No bank, finance company or sector was removed or capped. They are in their natural share. Spread across sectors came out wide on its own (below).
5. Dropped on the way (10 of the 60 companies walked, 17%): 8 PDFs are a press release or investor summary with no statement of results at all (Indian Bank, LTF, WeWork India, E2E Networks, Fedbank Financial, Sobha, DCB Bank, Geojit), and 2 files are damaged at the source (Central Bank of India and Adani Green: the file on NSE is cut short and no PDF reader can open it; a second download gave the same bytes). The pipeline gets such files too, so this loss rate is itself a finding.
6. 72 PDFs were downloaded in all; 12 of them (the next names on the lists) were never needed and are not in the key.

## Counts

Filings by size: LARGE 17, MID 17, SMALL 16 (size is the site's own market-cap class).

Filings by sector (top level of our industry label), then the finer label:

- Consumer Discretionary: 13
- Financial Services: 9
- Industrials: 7
- Commodities: 6
- Fast Moving Consumer Goods: 5
- Energy: 3
- Information Technology: 3
- Services: 2
- Healthcare: 1
- (no industry in our data): 1

- Industrials > Capital Goods: 7
- Consumer Discretionary > Consumer Services: 4
- Financial Services > Finance: 4
- Consumer Discretionary > Consumer Durables: 4
- Financial Services > Capital Markets: 3
- Energy > Oil, Gas & Consumable Fuels: 3
- Commodities > Chemicals: 3
- Consumer Discretionary > Automobile and Auto Components: 2
- Information Technology > IT - Software: 2
- Consumer Discretionary > Realty: 2
- Commodities > Construction Materials: 2
- Fast Moving Consumer Goods > Agricultural Food & other Products: 2
- Financial Services > Banks: 1
- Fast Moving Consumer Goods > Beverages: 1
- Fast Moving Consumer Goods > Personal Products: 1
- Financial Services > Insurance: 1
- Fast Moving Consumer Goods > Food Products: 1
- Commodities > Metals & Mining: 1
- Services > Commercial Services & Supplies: 1
- Healthcare > Pharmaceuticals & Biotechnology: 1
- Services > Transport Services: 1
- (no industry in our data): 1
- Information Technology > IT - Services: 1
- Consumer Discretionary > Textiles: 1

Financial Services companies are 9 of 50 (18%): ICICI Bank, SBI Cards, HDB Financial, CreditAccess Grameen, Aye Finance, Angel One, Groww, KFin Technologies and ICICI Prudential Life (an insurer). That is their natural share, not a quota.

### What the pages look like (most important for the reader)

Only 5 of the 50 filings have a true text layer (born digital). **45 of 50 are scanned or printed-to-image pages**: 23 have an OCR text layer that reads mostly right, 16 have an OCR text layer with wrong digits or broken cells, and 6 have no text layer at all. So the "normal" results PDF is a scan, not a clean table. This is the main result of building the key.

Tags (filings / figures). A tag is a difficulty fact seen on the statement page. Sector words are not used as tags.

- `two_bases_separate_pages`: 36 / 281
- `scanned_ocr_text_layer`: 23 / 143
- `lakh`: 18 / 115
- `scanned_garbled_text_layer`: 16 / 122
- `one_basis_only`: 13 / 48
- `basis_not_labelled`: 11 / 42
- `million`: 10 / 67
- `whole_unit_figures`: 9 / 54
- `landscape`: 6 / 37
- `revenue_sub_lines`: 6 / 40
- `scanned_no_text_layer`: 6 / 40
- `born_digital`: 5 / 32
- `indian_digit_grouping`: 5 / 31
- `lender`: 5 / 24
- `mixed_document`: 5 / 40
- `poor_scan`: 5 / 36
- `associate_line_before_pbt`: 4 / 32
- `exceptional_items`: 4 / 30
- `loss_making`: 4 / 32
- `text_layer_issue`: 4 / 24
- `unusual_column_layout`: 4 / 26
- `discontinued_ops`: 3 / 22
- `long_pdf`: 3 / 18
- `printed_as_lacs`: 3 / 22
- `revenue_no_total_line`: 3 / 15
- `broker`: 2 / 16
- `overlay`: 2 / 12
- `q1_results`: 2 / 16
- `associate_below_pat`: 1 / 8
- `bank`: 1 / 5
- `bank_statement_layout`: 1 / 5
- `bases_identical`: 1 / 8
- `bracket_zero`: 1 / 8
- `dec_year_end`: 1 / 4
- `insurer`: 1 / 2
- `minority_lines`: 1 / 8
- `nil_as_dash`: 1 / 8
- `pat_above_pbt`: 1 / 8
- `printed_total_off_by_rounding`: 1 / 8
- `rotated_page`: 1 / 8
- `side_by_side_bases`: 1 / 8
- `standalone_in_note_skipped`: 1 / 4
- `statement_spans_two_pages`: 1 / 8
- `title_mismatch`: 1 / 8
- `total_income_line_absent`: 1 / 3
- `unusual_statement_layout`: 1 / 2

Short meaning of the less obvious tags: `basis_not_labelled` = the results page does not say standalone or consolidated (basis taken from the XBRL basis of the same filing, the page does not contradict it); `revenue_no_total_line` = only a "Sales" and "Other operating income" line, no total, so revenue is `not_printed`; `revenue_sub_lines` = revenue is a total under several sub-lines; `associate_line_before_pbt` = a line for share of associate or joint venture sits just above profit before tax, so there are two near profit lines; `unusual_column_layout` = the quarter columns are not in the usual order or the labels sit to the right of the quarter columns; `title_mismatch` = the page title and the column dates disagree; `mixed_document` = the PDF also holds a cover letter, audit report, press release or presentation; `poor_scan` = skewed, blurred or photographed page; `overlay` = a stamp or digital signature sits on the table; `bases_identical` = standalone and consolidated print the same numbers.

## Second witness: card against page

140 figures had a card value on the same basis and period to compare with. For 129 the card and the page agree (within the rounding of what the page prints). **For 11 they disagree. In every one the page is the verdict and the card is wrong or uses a different line.** All 11 are consolidated statements, and 9 of the 11 are profit before tax.

| Company | Basis | Metric | Page prints (crore) | Card (crore) | What happened |
|---|---|---|---|---|---|
| ICICIBANK | CONSOLIDATED | pbt | 23,191.75 | 23,114.76 | Page line 12 is profit before tax and minority interest (after share of associates 76.99). The card took line 9, the profit before exceptional items and tax, before associates. Page 13. |
| SWIGGY | CONSOLIDATED | pbt | -922 | -920 | Card took line III (loss before share of associate loss, exceptional items and tax). Page prints line VII, Loss before tax, -922. Page 30. |
| GROWW | CONSOLIDATED | pbt | 983.86 | 984.61 | Card took the line before share of loss of associate. The page's Profit before tax is 983.86. Page 7. |
| SONACOMS | CONSOLIDATED | revenue | 1,535.84 | 1,546.42 | Page prints revenue from operations 15,358.40 million. The card number is 15,464.19 million: revenue plus the foreign exchange gain of 105.79 million. Page 12. |
| NESTLEIND | CONSOLIDATED | pbt | 1,382.20 | 1,399.36 | Card number 13,993.6 million is the STANDALONE profit before tax. The consolidated page prints 13,822.0 million. Page 7. |
| VISL | CONSOLIDATED | revenue | 2,788 | 2,742 | Card took the first sub-line, Revenue (a) 2,742. The page's total revenue from operations (a+b) is 2,788. Page 6. |
| ABREL | CONSOLIDATED | pbt | 173.79 | 175.24 | Card took line 5 (before share of loss of joint venture). The page's profit before tax from continuing operations is 173.79. Page 13. |
| KFINTECH | CONSOLIDATED | pbt | 138.981 | 139.24 | Card took line 4 (before share of loss of joint venture, 1,392.44 million, shown on the card as 139.24). Page prints Profit before tax 1,389.81 million. Page 6. |
| JSWCEMENT | CONSOLIDATED | pbt | 100.74 | 80.70 | Card took line V (before share of profit from joint ventures and associate). Page prints profit before tax 100.74. Page 9. |
| IFBIND | CONSOLIDATED | pbt | 53.67 | 60.23 | Card took the line before share of loss of an associate. Page prints profit before tax 53.67. Page 10. |
| DELTACORP | CONSOLIDATED | pbt | -115.96 | -115.35 | Card took the line before share of associates (-115.35). Page prints Profit before tax -115.96. Page 12. |

The pattern: of the 9 profit-before-tax cases, 8 are on a consolidated statement with a line for an associate or joint venture, and the card took the profit line just above it instead of the line the page calls profit before tax (ICICI Bank, Swiggy, Groww, ABREL, KFin, JSW Cement, IFB, Delta Corp). The ninth (Nestle India) used the standalone figure on the consolidated basis. The two revenue cases are a sub-line taken for the total (Vedanta Iron and Steel) and a revenue that includes the foreign exchange gain (Sona BLW). Fixing these classes is not part of this task.

Things that are differences of definition, not of figure (no row counted above):

- ICICI Bank consolidated profit: the page prints profit after minority interest (16,333.18, the card number) but not a total before minority, so the key has `pat` as not printed.
- Aye Finance: the page does not say consolidated or standalone; the card says consolidated; the key uses consolidated (tag `basis_not_labelled`).
- Huhtamaki India has a December year end (the page shows "Year ended 31.12.2025" and a nine-month column), but the card names the quarter Q2FY27. The key keeps the card's name, because the figures are the quarter ended 30 Sep 2026 and nothing else depends on the label.
- Where the card has no number for a metric (every card lacks total income, banks lack revenue), `card_value` is blank.
- Rounding is not counted as a disagreement. Several pages print whole crore, whole million or whole lakh; the card holds the exact XBRL figure.

## Checks on my own reading

- Presence check: every one of the 337 key figures was looked for, digit for digit, on its page in the PDF text layer and in an independent RapidOCR pass over the page image at 200 dpi. 332 were found. The other 5 (Supreme Petrochem standalone revenue, JSW Cement standalone and consolidated revenue, German Green Steel standalone and consolidated revenue) were not found because the text layer and the OCR both garble that cell. I re-read each of the 5 on the page image at 220 dpi. One was a slip of mine and is fixed (Supreme Petrochem standalone revenue is 1,95,669.83 lakh, not 1,95,659.83); the other four were right.
- Consistency check: total income is at least revenue, and profit after tax is at most profit before tax, for every filing and basis, except where the page itself explains it (ABREL: large profit from discontinued operations; Delta Corp: a tax credit; Parin: other income is negative, and its printed total income is 0.01 lakh lower than the sum of its two lines, as printed).
- Not every scanned page was looked at as an image by me. Pages where the OCR text layer was clean were read from the layer and then covered by the two checks above. The pages I looked at as images are the garbled, no-text-layer and rotated ones, and every page behind a card disagreement.

## How the page was read

For each filing I found the statement of results page or pages (standalone and consolidated are usually on different pages), read the printed figures for the latest quarter column, and wrote down the printed text, unit and page. Text pages were read with PyMuPDF (`python -I`, in a separate folder from the downloads). For every scanned page, and for every page where the text layer looked odd, I rendered the page to an image and read the image. Every figure in the key was read from the page image or from a clean text layer. Nothing was computed: where a line is not printed it is marked `not_printed`.

Which column: the latest quarter (30 Sep 2026, or 30 Jun 2026 for the two late filings). Not the half year, the nine months or the year.

## Limits

- 50 filings is a small sample. The key is a fair picture of the mix, not a precise rate for any one kind of file. With the sample size, a tag held by 1 to 3 filings (for example `rotated_page`) is an example, not a measurement.
- The pages were read once, by one reader. The card and, where the text layer was clean, the text layer are the only other witnesses. No second human read, so a slip in a figure the card does not cover (the non-card basis, about 190 figures) is possible. Scored results that look wrong by a digit should be re-read against the page.
- Only RESULTS filings with a PDF on nsearchives, and only filings whose PDF holds a statement of results. About 1 filing in 6 of those the live site shows has no statement in its PDF (press release only, or a damaged file). Those are outside this key; they are a separate problem for the pipeline (it must fall back to XBRL).
- Banks are thin: of the 4 banks the draw reached (ICICI Bank, Indian Bank, Central Bank of India, DCB Bank), only ICICI Bank has a usable statement in its PDF; the other three are a press release or a damaged file. So the key holds one bank, one insurer and no other lender of that type; do not read bank accuracy from it.
- Only 4 metrics and only the latest quarter. No half-year, nine-month or year figures, no profit attributable to owners, no EPS.
- Banks and insurers print no "revenue from operations", and several statements print no total income line. Those cells are `not_printed`, so those metrics are thinner for them.
- The standalone figures in a note (Brigade Hotel Ventures prints standalone revenue, profit before tax and profit after tax in note 8 with no unit stated) were not keyed.
- Basis for 11 filings is not printed on the results page (`basis_not_labelled`); it was taken from the XBRL basis of the same filing.
- Dates are the NSE filing dates in IST on the site's cards. The PDF links are NSE archive links as served on 27 October 2026; a link can disappear or change.
- Fixed key, no scoring in this task. No reader was run against it.

## Pass marks

Pass marks (set before scoring, proposed 27 Oct 2026, owner to confirm): at least 98% of key figures exactly right, at most 5% not answered, and no more than 1 wrong figure in 100.

## The 50 filings

| Symbol | Size | Period | Unit | Statement pages (standalone / consolidated) | Page kind |
|---|---|---|---|---|---|
| ICICIBANK | LARGE | Q2FY27 | crore | 3 / 13 | scan, OCR layer |
| RADICO | LARGE | Q2FY27 | lakh | 4 / 11 | scan, OCR layer |
| SWIGGY | LARGE | Q2FY27 | crore | 37 / 30 | scan, OCR layer |
| TMCV | LARGE | Q2FY27 | crore | 7 / 17 | scan, OCR layer |
| ANGELONE | LARGE | Q2FY27 | million | 11 / 5 | scan, no text layer |
| SBICARD | LARGE | Q2FY27 | crore | 2 / - | scan, OCR layer |
| ATGL | LARGE | Q2FY27 | crore | 14 / 8 | scan, no text layer |
| AEGISVOPAK | LARGE | Q2FY27 | lakh | 4 / 12 | scan, garbled OCR layer |
| COLPAL | LARGE | Q2FY27 | lakh | 4 / - | scan, OCR layer |
| GROWW | LARGE | Q2FY27 | crore | 13 / 7 | born digital |
| SONACOMS | LARGE | Q2FY27 | million | 4 / 12 | scan, no text layer |
| ICICIPRULI | LARGE | Q2FY27 | lakh | 3 / - | scan, OCR layer |
| HDBFS | LARGE | Q2FY27 | million | 6 / - | scan, OCR layer |
| AEGISLOG | LARGE | Q2FY27 | lakh | 4 / 12 | scan, garbled OCR layer |
| SRF | LARGE | Q2FY27 | crore | 4 / 15 | scan, OCR layer |
| TATAELXSI | LARGE | Q2FY27 | lakh | 5 / - | born digital |
| NESTLEIND | LARGE | Q2FY27 | million | 2 / 7 | born digital |
| LOTUSDEV | MID | Q2FY27 | million | 10 / 5 | scan, garbled OCR layer |
| IXIGO | MID | Q2FY27 | crore | 11 / 5 | scan, garbled OCR layer |
| VISL | MID | Q2FY27 | crore | 16 / 6 | scan, garbled OCR layer |
| ABREL | MID | Q2FY27 | crore | 4 / 13 | scan, garbled OCR layer |
| CMPDI | MID | Q2FY27 | crore | 4 / - | scan, no text layer |
| CREDITACC | MID | Q2FY27 | crore | 6 / 13 | scan, OCR layer |
| CROMPTON | MID | Q2FY27 | crore | 13 / 7 | scan, OCR layer |
| KFINTECH | MID | Q2FY27 | million | 14 / 6 | born digital |
| SPLPETRO | MID | Q2FY27 | lakh | 2 / 2 | scan, garbled OCR layer |
| ATUL | MID | Q2FY27 | crore | 4 / 9 | scan, OCR layer |
| NEWGEN | MID | Q2FY27 | lakh | 9 / 8 | scan, garbled OCR layer |
| JSWCEMENT | MID | Q2FY27 | crore | 14 / 9 | scan, garbled OCR layer |
| TBZ | MID | Q2FY27 | lakh | 4 / 9 | scan, garbled OCR layer |
| GAEL | MID | Q2FY27 | crore | 3 / 9 | scan, garbled OCR layer |
| JKTYRE | MID | Q2FY27 | crore | 10 / 2 | scan, OCR layer |
| MOREPENLAB | MID | Q2FY27 | lakh | 10 / 5 | scan, garbled OCR layer |
| KIRLPNU | MID | Q2FY27 | million | 2 / 9 | scan, OCR layer |
| NAVKARCORP | SMALL | Q2FY27 | lakh | 2 / - | scan, OCR layer |
| ORIENTCEM | SMALL | Q2FY27 | crore | 2 / - | scan, OCR layer |
| PARIN | SMALL | Q2FY27 | lakh | 5 / 11 | scan, garbled OCR layer |
| PNGSREVA | SMALL | Q2FY27 | million | 4 / - | scan, garbled OCR layer |
| HUHTAMAKI | SMALL | Q2FY27 | million | 3 / - | scan, OCR layer |
| BRIGHOTEL | SMALL | Q2FY27 | lakh | - / 4 | born digital |
| IFBIND | SMALL | Q2FY27 | crore | 3 / 10 | scan, garbled OCR layer |
| AVANTEL | SMALL | Q2FY27 | lakh | 4 / 10 | scan, OCR layer |
| GERMAN | SMALL | Q1FY27 | lakh | 2 / 7 | scan, garbled OCR layer |
| SRIT | SMALL | Q1FY27 | million | 5 / 9 | scan, OCR layer |
| ALOKINDS | SMALL | Q2FY27 | crore | 10 / 5 | scan, OCR layer |
| DELTACORP | SMALL | Q2FY27 | crore | 4 / 12 | scan, OCR layer |
| TRUALT | SMALL | Q2FY27 | lakh | 5 / 11 | scan, no text layer |
| RIR | SMALL | Q2FY27 | lakh | 4 / - | scan, no text layer |
| KANPRPLA | SMALL | Q2FY27 | lakh | 4 / 10 | scan, OCR layer |
| AYE | SMALL | Q2FY27 | crore | - / 5 | scan, OCR layer |
