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
| 21 Oct 10:07 | 20 | 2 | 12 | 6 | 0 (no export yet) | 0 | 0 of 4 checked | WRONG: invented or unsupported rationale 5 of 6 (HDB Financial peer comparison, Amagi FY26 profit claim, Moneyview rationale), event_type (Venus Pipes, PVP), Kapston Q2 prior-year EPS not bonus-restated (EPS direction wrong). Needs review: Kernex WRONG (order book from memory), Cleanmax and Ambuja MINOR, Supreme Infrastructure RIGHT, BHEL unread (12 MB PDF broken). Short vs long: 1 card carried a variant (long, MINOR). Critic not scored (no export). Recorded by the lead from the routine session's report: its push was refused (403, repository not attached), so its files were lost |
