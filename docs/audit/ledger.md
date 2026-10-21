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
| 21 Oct 12:55 | event_type | Order releases mentioning market demand no longer turned into LITIGATION_REGULATORY; "wins … orders" / "awarded … order" read as orders (pipeline.py `_TAX_OR_PENALTY`, `_REAL_ORDER`) | 304 stored ORDER_WIN + LITIGATION cards, rule decision off/on from each filing's text: 8 change; blind reviewer: 4 are order wins (L&T nse-106822983 and nse-106619863, Suzlon nse-106635264, Man Industries nse-106743427) and become right; 3 bank strike notices and Prestige's sales update are not litigation either way (wrong before and after); 0 made wrong | blind: 8 of 8 not litigation | 0 of 12 right (12:07) → next audit |

## Daily audit totals

| date | audited | right | minor | wrong | held reviewed | held released | needs-review fixed | notes |
|---|---|---|---|---|---|---|---|---|
| 21 Oct 10:07 | 20 | 2 | 12 | 6 | 0 (no export yet) | 0 | 0 of 4 checked | WRONG: invented or unsupported rationale 5 of 6 (HDB Financial peer comparison, Amagi FY26 profit claim, Moneyview rationale), event_type (Venus Pipes, PVP), Kapston Q2 prior-year EPS not bonus-restated (EPS direction wrong). Needs review: Kernex WRONG (order book from memory), Cleanmax and Ambuja MINOR, Supreme Infrastructure RIGHT, BHEL unread (12 MB PDF broken). Short vs long: 1 card carried a variant (long, MINOR). Critic not scored (no export). Recorded by the lead from the routine session's report: its push was refused (403, repository not attached), so its files were lost |
| 21 Oct 12:07 | 12 | 0 | 6 | 6 | 7 of 328 (1 releasable after fixes) | 0 | 0 of 2 | WRONG: event_type (L&T order win as litigation, Vintage Coffee fundraise as OTHER), Kapston EPS not bonus-restated, Kapston duplicate 801 of 799, invented (Moneyview, TVS facilities scope). Commonest: invented/memory claims 8 of 12; results blocks on the wrong column 4. Recorded by the lead (routine session could not push) |
| 21 Oct 14:07 | 6 | 2 | 3 | 1 | 0 | 0 | 0 | WRONG: Bajaj Consumer call card took a transcript slip over its own results block. Short 0 / long 2. Critic: no verdict for any audited card |
