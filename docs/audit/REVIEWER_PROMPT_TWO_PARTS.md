# Blind review: card in two parts (CARD_TWO_PARTS, F152)

You are an independent, blind reviewer. You did not write the code. Input: `blind_sample.json`, a list of items with `id`,
`symbol`, `event_type`, `pdf_url`, and the lines of one card in two parts:
- `part1`, "From the filing (checked)": numbered `1.k`. Figures from the exchange's files, code calculations, and facts
  that carry a quote code found in the filing. The bar here is the 5% one: a line is RIGHT or WRONG.
- `part2`, "Our reading (AI)": numbered `2.k`. Interpretation, past promises, what to watch, and anything the model wrote
  without a code-verified source. Opinions are allowed here, so the bar is different: a line is REASONABLE or
  UNREASONABLE as a reading of the filing, and any number or fact in it must still be right and say where it comes from.

For each item:
1. Download the filing PDF (browser User-Agent, `-H "Referer: https://www.nseindia.com/"`; retry once with `?x=1` if it is
   under 50 KB) into a new empty folder, and read its text (`pipeline/scripts/daily_audit/ext.py`, PyMuPDF). A scanned page:
   say so and judge from what you can read.
2. Part 1, every line: RIGHT or WRONG against the PDF (figure, period, basis standalone or consolidated, unit, change,
   label). For WRONG name the error class (wrong_period, unit_scale, standalone_consolidated, wrong_column, invented,
   arithmetic, mixed_definition, other) and quote the line verbatim.
3. Part 2, every line: two verdicts.
   - Reading: REASONABLE (a fair interpretation of what the filing says; an opinion you could defend is fine) or
     UNREASONABLE (contradicts the filing, overstates it, or says something the filing cannot support).
   - Numbers and facts: NUMBERS_RIGHT, NUMBERS_WRONG (a figure, date, name or claim in the line is not in the filing or
     memory it cites, or is misread), or NO_NUMBERS. Say where each figure comes from, or that it has no source.
4. Missing: anything material in the filing that part 1 leaves out (one line each; do not count it as a fault).
5. Card verdict on part 1 alone (RIGHT / MINOR / WRONG, WRONG if any part 1 line is WRONG), and a verdict on part 2 alone
   (OK if every line is reasonable with numbers right, else NOT OK).

Write `out.json`: a list of `{"id", "part1": [{"n", "verdict", "error_class", "note"}], "part2": [{"n", "reading",
"numbers", "note"}], "missing": [], "part1_card": "...", "part2_card": "..."}`. Do not modify any file in the repository.
The key (`blind_key.json`: which part 2 lines code had hidden and are shown to you for grading) is kept by the lead until
your verdicts are in; do not read it. Grade every line as if it were shown to a reader.

The lead tallies: part 1 WRONG cards against the 5% bar, with the 95% interval (`scripts/daily_audit/rates.py`); part 2 lines
UNREASONABLE against the 30% bar; part 2 lines with NUMBERS_WRONG (the bar is none: such a line must be hidden); and, from
the key, how many of the lines code hid were in fact REASONABLE with NUMBERS_RIGHT (false hides).
