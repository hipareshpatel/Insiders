# Audit round 2: a blind audit on companies the pipeline has never read (2026-10-18)

Round 1 (2026-10-16) was the last broad audit: 98 cards, 33% WRONG. Everything since was a loop on the same ten
smoke-test companies, mostly on right cards wrongly held (`rerun-held-2026-10-18.md`): held 118 -> 28 and published
333 -> 412, by fixes that nearly all made the checks accept more. Nobody measured what that did to the cards readers
see, whether the fixes generalise beyond those ten companies, or whether real news is being set aside. This round
does, in the order `DATA_QUALITY.md` prescribes: a fresh audit after the fixes, then decide.

## Sample

Fourteen companies, one per sector-and-size stratum, drawn with seed 20261018 from those with no filing in the
ledger (scratchpad `round2/select.py`):

| stratum | company | market cap |
|---|---|---|
| bank, large | Bandhan Bank (541153) | ₹27,390 Cr |
| life insurer, large | SBI Life Insurance (540719) | ₹1,67,168 Cr |
| NBFC, large | Home First Finance (543259) | ₹11,625 Cr |
| NBFC, mid | GYFTR (507912) | ₹1,278 Cr |
| IT, large | ESDS Software Solution (544898) | ₹18,630 Cr |
| IT, mid | Magellanic Cloud (538891) | ₹1,393 Cr |
| pharma, mid | Sun Pharma Advanced Research (532872) | ₹6,117 Cr |
| capital goods, mid | HEG (509631) | ₹7,480 Cr |
| FMCG, large | Britannia Industries (500825) | ₹1,17,874 Cr |
| auto components, mid | SKF India (500472) | ₹7,111 Cr |
| metals, large | Jindal Stainless (532508) | ₹59,717 Cr |
| power, large | Adani Power (533096) | ₹3,78,559 Cr |
| chemicals, small | Poddar Pigments (524570) | ₹284 Cr |
| consumer durables, small | Lehar Footwears (532829) | ₹333 Cr |

Window: filings from 15 July to 18 October 2026 (Q1FY27 results, the AGM and annual-report season, the first Q2
results). Memory seeded from XBRL first (`seed-memory`), as for the smoke test.

## Method

1. Process the window with today's code (`backfill-companies --scrips ... --from 2026-07-15`), measuring AI
   requests per filing, 429s and filings an hour (scratchpad `round2/usage.py`) for the backfill decision.
2. **Accuracy**: about 80 published cards, a seeded random sample spread over the companies, exported blind
   (`audit_export.py --blind --memory --random`): reviewers see the card, the filing text and memory as the card saw
   it, not the pipeline's own checks. One independent reviewer per folder, `REVIEWER_PROMPT_ROUND2.md`: round 1's
   rules for the verdict, plus memory points (tallied apart) and whether the impact level fits.
3. **Held cards** (owner, 2026-10-18): about 10 cards the checks held back on these companies, mixed into the same
   folders and reviewed with the same prompt, the reviewer not told which they are. At 6% held on the smoke test,
   this shows whether the holds left are mostly right or still keep correct cards out; without them the round
   measures only one of the two ways the checks can fail.
4. **Missed news**: about 50 filings the companies' cards never covered (25 dropped by rule, 15 not material, 5
   timeline only, 5 duplicates), seeded sample, attachments read; same prompt file, second part.

## Pass marks, set before any review (owner, 2026-10-18)

- **Accuracy: WRONG at most 15% of the published cards** reviewed (round 1 was 33%; under 33% is not a pass, since
  30% would still be nearly one card in three misleading a reader). Memory-point errors are counted apart and
  reported beside it.
- **Recall: at most 2 MISSED** of the ~50 filings set aside.
- **Holds**: reported, no mark: the share of held cards the reviewers judge OK or MINOR is the share held wrongly.

Both marks met -> the backfill decision (PLAN 1c, the owner's). Either missed -> the commonest WRONG classes and every
MISSED class on these companies are the next fixes, and the round is repeated on fresh companies.

## Results (2026-10-18)

The run: 499 announcements for the 14 companies, 177 dropped by rule, 322 processed in 1.95 h (165 an hour; the
site went down once and the run was restarted), 2.06 AI requests and ~24k tokens a filing, 3.3% of requests 429s.
131 cards, **42 held (32%)** against 6% on the smoke-test companies after the held-card loop: the checks were tuned
to the filings they were tuned on. Reviewers: 14 independent, blind; findings in `round-2/` and `round-2.json`.

| Pass mark (set before review) | result | |
|---|---|---|
| WRONG <= 15% of published cards | **29 of 80 = 36%** (MINOR 40%, OK 24%) | **fail** |
| MISSED <= 2 of ~50 set aside | **1 MISSED, 3 UNSURE of 50**; all 25 rule drops RIGHT | pass (fails if 2 UNSURE are real) |
| holds (reported) | the 10 held: 6 WRONG, 4 MINOR, 0 OK | holds are right |

**Accuracy is no better than round 1 (33%) on companies the pipeline had never read.** Issues by class over the 90
cards: other 60, memory 47 (memory points wrong on 37 cards, tallied apart), arithmetic 20, invented 19, signal
verdict 16, wrong column 13, direction 12, unit scale 11, event type 9, standalone/consolidated 6. By writer model,
WRONG: deepseek-flash 42% (40 cards), nemotron-3-super 41% (32), glm-4.5-flash 29% (17). Impact level fits on 74
of 90. The recurring causes, from the reviewers' worst cases:

1. **Bases that are not like for like**: a demerger or deconsolidation leaves the year-ago figure on another base
   (SKF India, Prism's RQBE, Kanoria's APAG, HEG); standalone against consolidated (eMudhra, Magellanic's annual
   report); a share split in EPS (Adani Power). Signals (MARGIN_MIX, DILUTION, growth %) inherit the wrong base.
2. **Memory carrying a slip forward**: Magellanic's ₹12.76 Cr GAIL order stored as ₹127.62 Cr and then counted in
   ORDER_FLOW on three cards; Bandhan's net worth 100x too small ("contingent liabilities 110x net worth"); SBI
   Life's expense ratio 100x. The memory scale guard (dossier `_out_of_scale`) did not stop them.
3. **Columns and direction in prose**: Bandhan's business update read with its columns in the wrong order (every
   figure wrong); "margin improved from 12.83% to 11.78%"; inventory build called a drawdown (SKF, Britannia).
4. **Signals that contradict the card**: approvals "met" on an unrelated order (Adani), dilution counting only the
   equity shares beside 12.67 Cr warrants (Magellanic), a rating reaffirmation shown as a ₹105 Cr fundraise (Lehar).

**Other measurements this round:**
- *The cards the held-card loop released* (59 not checked before): **32% WRONG**, memory points wrong on 27. The
  loosening released wrong cards at round 1's rate (`round-2/released-cards.json`).
- *The 40 cards still held on the smoke test*: 57% WRONG, 33% MINOR, 10% OK - the remaining holds are right.
- *Dropped facts* (PLAN 1h, `round-2/dropped_facts.md`): 50 of 60 facts the quote check dropped were true; a
  fact whose quote fails is kept only when it has a plain figure above 31, so ratings, dates, percentages and small
  amounts are dropped outright.
- *Signals and ranking* (`round-2/signals_audit.md`): Top Signals is empty (no card scores 70); by score, 10 of the
  top 30 do not deserve their place (11 are open-offer filings; any computed ₹ figure counts as the deal size), and
  signals contradict the card on 12 of the top 30.
- *Backfill readiness* (`round-2/backfill_readiness.md`): the live flow (~720 filings a day for the 2,894
  companies above ₹100 Cr) fits the free tiers in ~5.5 h a day, 11-17 h in results season; a backfill from
  January 2025 (~467,000 filings) needs ~150 days of running free, ~118 with the paid route.
- *Repeat cards* (`round-2/repeat_cards.md`): a narrow SAST rule would merge 6 same-stage repeats and no separate
  stage; proposed, not built.

## Decision

The accuracy mark is missed, so by the rule set before review the backfill decision waits. Next fixes, in order of
how many WRONG cards they explain: like-for-like bases (demerger / restated / standalone-consolidated / split)
for every computed change and signal; memory refusing figures off scale by 10x and 100x before they are stored
and reused; column order read from a table's own headers and arithmetic; the signal verdict checks the reviewers
found; and keeping true facts the quote check drops. Then a round 3 on another 14 unseen companies, same marks.

The owner then set a structural order instead (2026-10-18): code computes and the model describes (cf52585,
12a83c0), memory stores only trusted figures (04bcda5), signals that contradict their card are off (d87ab01), and
true facts the quote check dropped are kept on their figures, dates, ratings or names (950db92). Round 2's 90
cards are re-run as a measured round, then round 3 on 14 more unseen companies at the same marks. DeepSeek's weight
stays where it is until round 3 passes.

## For the owner: backfill scope options (not acted on)

From January 2025 the backfill is ~467,000 filings and ~150 days free. Narrower scopes, from round 2's measured
rates (`round-2/backfill_readiness.md`):

- **Filings:** 7.5 a company a month (round 2's 14 companies, large-cap heavy, so small caps likely file less).
  Companies by market cap (D1 `companies`): 2,894 at ₹100 Cr and above, 1,908 at ₹500 Cr, 1,562 at ₹1,000 Cr.
- **Speed:** 130 filings an hour free, 165 with the DeepSeek route. "Free, 24 h" is the laptop running all day;
  "18.5 h" leaves the ~5.5 h a day the live flow needs.
- **DeepSeek cost:** 0.42 requests a filing x $0.0032 (D24), for the filings that reach pass 2.
- **Event types:** results, annual reports and major events (order wins, M&A, fundraises and rights issues,
  capex, ratings, litigation and regulatory, management changes) were 147 of round 2's 322 filings but 103 of its
  131 cards. Pass 1 still has to read every filing to know its type, and pass 2 is ~95% of the time, so this scope
  saves only ~20%: the filings it leaves out are mostly the ones pass 1 already stops (governance, "other").

| Companies | Months back | Types | Filings | Free, 24 h | Free, 18.5 h | With DeepSeek (24 h), cost |
|---|---|---|---|---|---|---|
| ≥ ₹100 Cr (2,894) | 21.5 | all | 467k | 150 d | 194 d | 118 d, ~$630 |
| | 12 | all | 260k | 83 d | 108 d | 66 d, ~$350 |
| | 6 | all | 130k | 42 d | 54 d | 33 d, ~$175 |
| | 12 | results, AR, major | 260k | 67 d | 86 d | 52 d, ~$275 |
| | 6 | results, AR, major | 130k | 33 d | 43 d | 26 d, ~$140 |
| ≥ ₹500 Cr (1,908) | 21.5 | all | 308k | 99 d | 128 d | 78 d, ~$415 |
| | 12 | all | 172k | 55 d | 71 d | 43 d, ~$230 |
| | 6 | all | 86k | 28 d | 36 d | 22 d, ~$115 |
| | 12 | results, AR, major | 172k | 44 d | 57 d | 35 d, ~$180 |
| | 6 | results, AR, major | 86k | 22 d | 28 d | 17 d, ~$90 |
| ≥ ₹1,000 Cr (1,562) | 21.5 | all | 252k | 81 d | 105 d | 64 d, ~$340 |
| | 12 | all | 141k | 45 d | 58 d | 36 d, ~$190 |
| | 6 | all | 70k | 23 d | 29 d | 18 d, ~$95 |
| | 12 | results, AR, major | 141k | 36 d | 47 d | 28 d, ~$150 |
| | 6 | results, AR, major | 70k | 18 d | 23 d | 14 d, ~$75 |

What moves the time most is the number of companies and months, not the event types. The levers that are not
scope (8 workers instead of 5, fewer second opinions, fewer wasted pass-2 calls) are in `backfill_readiness.md` §5
and are unmeasured. The paid route stays off the daily path whatever is chosen; it only shortens a backfill.

## Re-run as a measured round (2026-10-18, DATA_QUALITY.md step 6)

After the four structural changes (TRACKER F60-F63) the 14 companies were rebuilt from scratch: cards, catalysts
and memory reset, XBRL re-seeded, all 322 filings read again with the same provider weights
(`pipeline/scripts/audit_round2/reset.py`, `rerun_cards.py`). The same 90 filings were then reviewed against their
filings with round 2's prompt (`round-2-rerun.json`; comparison by `compare_rerun.py`). 84 have a card: 80 their own
and 4 whose filing was merged into another of the same event, judged on the card that now carries it. 6 have none:
4 merged into a card already in the sample, 2 now not material (a debt-servicing note round 2 called OK, and a
subsidiary's rename round 2 called WRONG).

**Who reviewed:** one reviewer, the author of the fixes, not blind to round 2's verdicts (the owner asked for no
agents). Round 2 had seven independent blind reviewers. Read the "after" figures with that in mind. Round 3 will
measure the changes on companies nobody has seen.

| Filings | Before (round 2) | After (re-run) |
|---|---|---|
| Published in round 2 (80) | WRONG 29, MINOR 32, OK 19 | WRONG 14, MINOR 21, OK 39, no card 6 |
| Held in round 2 (10) | WRONG 6, MINOR 4 | WRONG 3, MINOR 2, OK 5 |
| Cards published now | 29 of 80 WRONG (36%) | 13 of 70 WRONG (19%) |
| Memory points wrong | 37 cards | 11 cards |

WRONG cards by class (a card counts once per class):

| Class | Before | After |
|---|---|---|
| other | 20 | 7 |
| arithmetic | 12 | 3 |
| signal_verdict | 10 | 9 |
| invented | 10 | 0 |
| direction | 8 | 2 |
| unit_scale | 7 | 2 |
| wrong_column | 3 | 1 |
| standalone_consolidated | 3 | 0 |
| wrong_period, event_type | 4 | 0 |

Verdict moves: of the 35 WRONG, 21 now OK or MINOR, 11 still WRONG, 3 without a card; 6 cards got worse (2 OK and
4 MINOR now WRONG).

**What is left, by cause (to fix after round 3's review, not before: no change to the checks while round 3 runs):**

1. *One order counted twice, and a recap counted as an order* (7 of the 17 WRONG, all Magellanic): an order's BSE
   intimation and its press release are both carded and both stored as deals, and a press release listing
   ₹111.04 Cr of orders since April is stored as one order. ORDER_FLOW then reads "17th order, ₹291 Cr" where there
   were 10 orders and ₹100 Cr. The card's own text often says it is the same order.
2. *Percentages printed without a "%" sign are removed* (vote results "97.0846", stakes "17.12", "74.96"): change 1
   sees them as unproduced, and the stripped sentence keeps empty bold markers or loses its object ("** ** of
   votes", "increase stake to via", "of net worth"). Ten MINOR cards, no wrong figure, but unreadable sentences.
3. *A pooled figure on the wrong base*: "₹1,00,000 Cr limit is 22.6% of net worth" (22.6% is of market cap);
   "QIP is 38.9% of market cap and 206% of net worth" survived although neither figure is printed. Change 1 checks
   that a figure was produced, not what it is a share of.
4. *A table's columns read in the wrong order*: Bandhan's September update has garbled headers; the YoY and QoQ
   columns show the order is Sep-25, Jun-26, Sep-26, so advances grew 13.1%; the card says they fell 13.1%, and
   memory took the year-old figures as September 2026 (printed and in scale, so the trust rule let them in).
5. *Crore share counts read as million* (Adani SAST "10.8M shares" for 10,80,27,500; Magellanic "12.67 million
   warrants" for 12,67,00,000).
6. *Signals*: GUIDANCE_BREACH fires when the period ends, before its results are due (Jindal, 16 Oct for H1FY27).
7. *Direction of a level pair* ("margin slipped to 15.0% from 13.0%", SKF) and *two measures of one date shown as
   a change* (Jindal net debt ₹6,926 Cr covenant basis vs ₹3,040 Cr MD&A basis, both 31 March 2026).

Seven of the 13 published WRONG cards are cause 1 alone; without it the published WRONG share would be 6 of 70 (9%).
