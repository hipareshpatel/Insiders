# bench_score.py audit (2026-10-17)

I checked all 26 outputs against the PDFs and re-scored with each fix alone (`scripts/audit/`). text-sorted's 82 misses split into 30 answer-key faults, 24 scanned pages, 12 scorer misses and 16 real failures (garbled OCR text).

## Defects

**1. The key holds 33 of 228 figures (14%) that the PDF never prints.**
- tax_expense where only current and deferred are printed (8). SML `1e874774`: 0.22 = 0.03+0.19.
- other_expenses as the sum of rows printed separately (7). Prism `bcad18ec`: 1,090.73 is the sum of four printed rows.
- total_expenses including finance and D&A (3). Kanoria `5f89acb4`: the PDF prints 43,741 lakh; the truth is 46,500.
- pbt (3). Prism: 159.37 is before the share of associates; the printed PBT is 165.97. Jubilant `139e9236`: the PDF prints 1,305 million; the truth is 130.8.
- `db04e18b` is a press release, not the results statement (12).

Fix: drop these from the manifest and replace db04e18b.

**2. Whitespace inside labels blocks a match.**
- Effect: plumber-text +42, p4llm-legacy-text +47, p4llm-layout +32.
- Examples: "g) Other expe nses 46.86"; "Net\x03profit\x03for\x03the\x03period".
- plumber-text actually places 63% of figures, not 44%.
- Fix: strip `[\s\x00-\x1f]` from labels and patterns before matching.

**3. Some patterns are too narrow** (+6 per text engine). They miss "Revenue from Operation" (Shivam), "Profit/(Loss) for the period" (Kanoria) and the banks' "Operating expenses (i)+(ii)" (CSB 37,417).

**4. Sub-rows and text-layer typos** (+3 each).
- "Income 1,472.99" sits under the heading "Income from operations"; the scorer reads only the row's own label.
- Typos such as "Tax exoense 6610".
- Fix: also match the label-only row above; allow edit distance ≤2.

**5. Tolerance and scales.** No row+column hit uses a wrong unit. But:
- `max(0.011, 0.06%)` passes "4.1" for EPS 4.11 and "683" for 683.1.
- `anywhere` gets 4–9 wrong-scale hits per engine.
- 1e5 is not "thousand" (that is 1e4).
- `abs()` hides sign errors.
- Fix: try only the declared unit, compare EPS at scale 1, use a tolerance of about 0.006 crore.

**6.** `--detail` prints "(row)" when the figure is *not* on the row.

## find-tables: both the finder and the wrapper

- PyMuPDF's finder returns no table on 7 filings.
- Where it finds one, each "row" holds several line items: cell "331.80\n1.63".
- The wrapper drops any cell that is not a single number, so it keeps 43 of the 78 figures the finder captured.
- Splitting rows into lines scores 55 (24%), not 20, equal to text-sorted on Jubilant Q3, SML and eMudhra Q1.

## Sound

- Serial stripping removed no truth figure.
- Indian grouping, parenthesised negatives, period column and basis check out.
- Spot checks on CSB, Jubilant, Prism, Kanoria and SML: two of three figures matched in each; the third is a defect listed above.
- Ahluwalia matches the OCR at lakh, so its declared_unit should be 100.

## Trust

- **row+column hits:** I trust them. I hand-checked 25+ and none were wrong.
- **row+column level and rankings:** I don't trust them. Fixed and scored over the 195 figures the PDFs print: text-sorted 157 (81%), plumber-text 151, find-tables 28.
- **row:** not trusted; it adds at most 3 over row+column.
- **anywhere:** not trusted.
