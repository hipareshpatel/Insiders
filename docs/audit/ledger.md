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
| 21 Oct 17:35 | arithmetic (multiple in words) | A 'more than double' / 'tripled' / 'halved' the card's own amounts contradict is cut (`directions.multiple_guard`) | 1,736 stored cards, 88 texts with a multiple word: a first rule cut 4 (2 wrong: a doubling named by its result, a figure of another line); with the base within 40 characters in the same clause, 2: LMW nse-106823292 (₹71.23 Cr against ₹40.92 Cr, +74%) and Jubilant Pharmova 1ee7b071 (₹71 Cr against ₹43.1 Cr, 1.65x), both wrong as written | LMW judged WRONG by the 16:07 blind reviewer; Jubilant checked from the card's own figures | 4 of 10 right (16:07) → next audit |
| 21 Oct 16:45 | unit_scale (our unit fixer) | '₹ Cr' read as a declared unit, so a crore deck with one lakh line declares no single unit and the fixer leaves its figures alone (`grounding._DECLARED_UNIT`) | declared unit old/new over 323 stored filings (19 the fixer changed, 304 order-win and litigation): 1 changes, Mahindra Holidays nse-106823248, whose 9 crore figures the fixer had cut 100x | the 16:07 blind reviewer: the deck's figures are ₹ crore (₹395.3 Cr), so the card becomes right on re-run | 4 of 10 right (16:07) → next audit |
| 21 Oct 15:20 | other (call-card figure against the company's XBRL) | Call cards: a quarter key number for revenue, EBITDA or PAT whose figure and stated change both contradict the results block is dropped; a headline or point repeating it sends the card to review (`results_card.call_figure_conflicts`) | 198 stored call cards with a results block: a value-only rule flagged 54 (full-year figures, segments, adjusted EBITDA, other basis); with the quarter named in the quote 7; with the stated change contradicting the filed one too, 2: Bajaj Consumer nse-106823055 (the audited slip) and LTM c707fc7d (already held) | 2 of 2 checked against their quotes and blocks | 2 of 6 right (14:07) → next audit |
| 21 Oct 12:55 | event_type | Order releases mentioning market demand no longer turned into LITIGATION_REGULATORY; "wins … orders" / "awarded … order" read as orders (pipeline.py `_TAX_OR_PENALTY`, `_REAL_ORDER`) | 304 stored ORDER_WIN + LITIGATION cards, rule decision off/on from each filing's text: 8 change; blind reviewer: 4 are order wins (L&T nse-106822983 and nse-106619863, Suzlon nse-106635264, Man Industries nse-106743427) and become right; 3 bank strike notices and Prestige's sales update are not litigation either way (wrong before and after); 0 made wrong | blind: 8 of 8 not litigation | 0 of 12 right (12:07) → next audit |

## Daily audit totals

| date | audited | right | minor | wrong | held reviewed | held released | needs-review fixed | notes |
|---|---|---|---|---|---|---|---|---|
| 21 Oct 10:07 | 20 | 2 | 12 | 6 | 0 (no export yet) | 0 | 0 of 4 checked | WRONG: invented or unsupported rationale 5 of 6 (HDB Financial peer comparison, Amagi FY26 profit claim, Moneyview rationale), event_type (Venus Pipes, PVP), Kapston Q2 prior-year EPS not bonus-restated (EPS direction wrong). Needs review: Kernex WRONG (order book from memory), Cleanmax and Ambuja MINOR, Supreme Infrastructure RIGHT, BHEL unread (12 MB PDF broken). Short vs long: 1 card carried a variant (long, MINOR). Critic not scored (no export). Recorded by the lead from the routine session's report: its push was refused (403, repository not attached), so its files were lost |
| 21 Oct 12:07 | 12 | 0 | 6 | 6 | 7 of 328 (1 releasable after fixes) | 0 | 0 of 2 | WRONG: event_type (L&T order win as litigation, Vintage Coffee fundraise as OTHER), Kapston EPS not bonus-restated, Kapston duplicate 801 of 799, invented (Moneyview, TVS facilities scope). Commonest: invented/memory claims 8 of 12; results blocks on the wrong column 4. Recorded by the lead (routine session could not push) |
| 21 Oct 14:07 | 6 | 2 | 3 | 1 | 0 | 0 | 0 | WRONG: Bajaj Consumer call card took a transcript slip over its own results block. Short 0 / long 2. Critic: no verdict for any audited card |
| 21 Oct 16:07 | 10 | 4 | 1 | 5 | 0 | 0 | 0 | WRONG: MHRIL (our unit fixer, lakh read for a crore deck), HCLTech (USD figures in memory as ₹ Cr), LMW (more than double for +74%), ABSLAMC (unsupported cause), VMM call (cities count). Short 4 (2/1/1), long 6 (2/0/4) |
| 21 Oct (day) | 48 | 10 | 27 | 11 | 7 of 328 | 0 | 2 | 21% right, 77% right or minor; short 4 cards (2/1/1) vs long 10 (2/2/6); critic not scored (3 verdicts in two days) |
