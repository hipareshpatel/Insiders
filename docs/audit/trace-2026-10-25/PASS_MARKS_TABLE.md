# Pass marks for the results-table fix at source, set before any code (25 Oct 2026)

The owner chose EBITDA option (a): show the company's own printed EBITDA when it prints one. The fix also sets every
comparison line on one basis and one definition: profit attributable to owners against the same, standalone against
standalone, net income against net income.

**Population.** Every stored results and call table (the 2,053 on the live API on 25 Oct), rebuilt with the fix off and
on, with no AI.

**Review.** Every line whose value, comparative or change differs between off and on is reviewed; above 150 lines, a
random 150. Independent agents judge both versions against the filing PDF, blind to which version is which.

**Accepted only if all of these hold:**
1. ON lines are RIGHT in at least 85% of cases, with the lower 95% Wilson bound at 75% or above.
2. ON beats OFF by at least 20 points of RIGHT.
3. At most 5% of changed lines go from RIGHT (off) to WRONG (on).

**Otherwise** the fix does not ship as it is: it is narrowed and re-measured on tables not used to tune it, or dropped.

## Re-measure of the narrowed fix (set before measuring, 25 Oct 2026)
The first version failed: ON 71.8% right, +31.5 points over OFF, 11.4% right-to-wrong (`table_fix_review.json`). It
was narrowed on what broke:
- the company's EBITDA is used only when the filing's text prints that figure with "EBITDA" just before it;
- that EBITDA's comparatives must be printed beside it;
- its margin is computed from it, never a rounded printed margin.

**Population.** Only tables filed after the narrowing (`onoff_table.py --since`), which played no part in tuning,
rebuilt off and on with each filing's PyMuPDF text.

**Review.** Changed lines are reviewed blind exactly as before, once there are at least 100; if there are more than
150, a random 150.

**Pass marks.** The same three apply unchanged: ON ≥ 85% right (lower bound ≥ 75%), ON beats OFF by ≥ 20 points,
right-to-wrong ≤ 5%.

## How a removed line counts (set before reviewing the fresh set, 25 Oct 2026)
The narrowed fix also removes lines it cannot show honestly: our EBITDA where the filing prints another, or a comparative
the text contradicts. The three marks above did not say how a removed line scores, so this is fixed before any verdict is
read. In the fresh run, 249 lines changed in 109 of 223 tables, 171 of them removed.

1. **Mark 1** (ON ≥ 85% right, lower bound ≥ 75%) is computed over the ON lines still shown.
2. **Mark 2** (ON beats OFF by ≥ 20 points) is computed as the share of changed lines that end up RIGHT or removed-
   while-OFF-was-WRONG, against the share that were RIGHT off.
3. **Mark 3** (right-to-wrong ≤ 5%) counts a shown line that goes from RIGHT to WRONG.
4. **A new limit on removals:** at most 20% of removed lines may have been RIGHT off (the same limit check A had). Above
   it, the fix throws away too much.

Review sample: a random 150 of the distinct changed lines (seed 2511), each in two versions X and Y. A removed version
shows as null.

## Stricter removal limit (owner's engineering handover, adopted before any fresh-set verdict was read, 25 Oct 2026)
The owner's handover sets "correct-content removal ≤ 5%", and says stricter thresholds win. It replaces the 20% limit in
item 4 of the section above: **at most 5% of removed lines may have been RIGHT off.** It was adopted before any of the
four reviewers' verdicts existed (no `verdicts_*.json` file had been written).

## Third independent measurement: the period- and basis-aware EBITDA check (set before measuring, 25 Oct 2026)
The 223-table fresh set is spent: it was used to develop this version (F126d) and proves nothing about it. The owner's
instruction of 25 Oct: fix rounding, operating EBITDA and annual-against-quarterly rows; freeze; measure on about 200
tables no version was tuned on, under the same four marks.

**The rule, frozen at the commit that adds this section** (`dossier._ebitda_check`, `_ebitda_rows`, `_at_rounding`):
- a printed figure is ours when it is within half its last printed digit plus `ROUNDING` (0.05%) of ours, at one of
  the units crore, lakh, million, thousand, rupees, or billion when the word follows it;
- plain and operating EBITDA rows count; margin, adjusted, core, normalised and pro-forma rows do not, nor ratio rows
  (a "/", "per", "CAGR", "coverage" in the label); a period's name, a year or a rate is not a figure;
- a row's period is what its own line names, else (a table row of two or more figures) every period named above it on
  its page, else (a single figure) the two lines before it. Only "Q" or "QY" rows count; "Y" rows and rows with no
  period never remove ours, and a row with no period confirms ours only when it also prints one of our comparatives;
- a row on the other basis (the last "consolidated" or "standalone" on its page up to it) counts neither way;
- a row stands against ours only with a figure between half and twice ours at some unit.

**Population.** Every RESULTS and CONCALL_PRESENTATION table on the live API whose news_id is in none of the earlier
sets (`all_stored.json` of 25 Oct morning, the first measurement's cards, `fresh_cards.json`), taken once at least 200
such tables exist. The card list, each company's memory (`onoff_table.py --memory-dir`) and the run's output are kept,
so the run can be repeated on the same inputs.

**Review.** `table_review.py sample`: a random 150 of the changed lines (all when fewer; at least 100 are needed, as
before), seed 2511, X and Y in random order, four independent reviewers blind to which is which. Reviewers also name,
for every line they judge, the basis and definition the company prints, so false removals can be classed (rounding,
operating EBITDA, annual against quarterly, standalone against consolidated, other).

**Pass marks, unchanged** (`table_review.py score`, which reproduces F126b's 52/58, +32 points, 1/150 and 28/92 from its
files): 1. ON shown lines RIGHT ≥ 85%, Wilson low ≥ 75%; 2. ON beats OFF by ≥ 20 points; 3. right-to-wrong ≤ 5%;
4. removed lines that were RIGHT ≤ 5%. UNSURE counts as not RIGHT and is reported. Any fail: not shipped, diagnosed, and
the next version is measured on another unseen batch.
