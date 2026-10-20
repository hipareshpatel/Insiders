# Card-quality ledger

One row per change made by the daily card audit (owner, 2026-10-20: 200 days from 21 Oct 2026, 10:00-17:00 IST).
It shows whether our changes move the published output the right way. Each row is written before the change is
merged and its "after" figure filled in on the next day's audit.

Columns:
- **date**: the audit day (IST).
- **class**: the error class fixed (wrong_period, unit_scale, restated, direction, invented, duplicate, ...).
- **change**: what changed (code / prompt / rule), with the commit.
- **on/off over stored cards**: cards that change, and how many of those became right, stayed wrong or became wrong
  (measured with no AI over the stored cards before merging).
- **sample**: the independent blind check, right / minor / wrong.
- **published right, before → after**: the day's audited share of published cards judged right, the day before
  and the first audit after the change.

| date | class | change | on/off over stored cards | sample | published right, before → after |
|---|---|---|---|---|---|

## Daily audit totals

| date | audited | right | minor | wrong | held reviewed | held released | needs-review fixed | notes |
|---|---|---|---|---|---|---|---|---|
