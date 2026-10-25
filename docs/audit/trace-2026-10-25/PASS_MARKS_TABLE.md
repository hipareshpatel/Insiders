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
