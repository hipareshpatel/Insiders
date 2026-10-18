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
3. **Missed news**: about 50 filings the companies' cards never covered (25 dropped by rule, 15 not material, 5
   timeline only, 5 duplicates), seeded sample, attachments read; same prompt file, second part.
4. **Decide**: WRONG under round 1's 33% and few MISSED -> the backfill decision (PLAN 1c, owner). Otherwise the
   commonest wrong classes on these companies are the next fixes.

## Results

(to follow)
