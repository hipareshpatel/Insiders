# Blind review: results card, two renderings (CARD_EBITDA_PROFIT_V2, F151)

You are an independent, blind reviewer. You did not write the code. Input: `blind_sample.json`, a list of items with
`id`, `symbol`, `period`, `pdf_url`, and two renderings of one results card, `X` and `Y` (lines of the results table and
of the card's face). You do not know which is the new one.

For each item:
1. Download the filing PDF (browser User-Agent, `-H "Referer: https://www.nseindia.com/"`; retry once with `?x=1` if it is
   under 50 KB) into a new empty folder, and read its text (`pipeline/scripts/daily_audit/ext.py`, PyMuPDF). A scanned page:
   say so and judge from what you can read.
2. For X and Y each, check every line against the PDF:
   - EBITDA: a line labelled "(Filing)" must be the company's own printed EBITDA for the quarter, under the company's own
     name for it, with a year-ago figure and change only if the filing prints them. A line labelled "Operating EBITDA
     (calculated)" is code's sum (profit before exceptional items and tax + finance cost + depreciation - other income);
     it must not be set against the company's figure, and its "leaves out other income" figure must be the quarter's.
   - Profit: one profit line only. It must be the line the company headlines in its release (its own label), or with no
     release the profit attributable to shareholders. Say if a second profit figure appears anywhere (headline, facts,
     key numbers, takeaway, table).
   - Every other figure, period, basis (standalone or consolidated), unit and change.
3. Verdict for each rendering: RIGHT, MINOR (does not mislead) or WRONG (a figure, period, basis, label or change that
   misleads). Name the error class (wrong_period, unit_scale, standalone_consolidated, wrong_column, invented, arithmetic,
   mixed_definition, second_profit, other) and quote the wrong line verbatim.
4. Which rendering you would publish: X, Y, or SAME.

Write `out.json`: a list of `{"id", "X": {"verdict", "error_class", "wrong_lines"}, "Y": {...}, "prefer", "reason"}`. Do not
modify any file in the repository. The key (which is the new rendering) is in `blind_key.json`, kept by the lead until your
verdicts are in; do not read it.
