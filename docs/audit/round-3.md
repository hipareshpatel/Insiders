# Audit round 3: a blind audit on 14 more companies the pipeline has never read

Written 2026-10-18, before any round-3 company was processed. Round 2 missed its accuracy mark (36% WRONG of
published cards against a 15% mark, `round-2.md`). The owner then set four structural changes instead of more
fix-by-fix work (TRACKER F60-F63): code computes and the model describes, memory stores only trusted figures,
signals that contradict their card are off, and true facts the quote check dropped are kept. Round 2's own cards
are re-run as a measured round under those changes (F64). This round tests whether they generalise to companies
none of them were fitted on.

## Sample

Fourteen companies, one per sector-and-size stratum (round 2's strata), drawn with seed **20261019** from those
with no filing in the ledger, so neither the smoke-test ten nor round 2's fourteen
(`pipeline/scripts/audit_round3/select.py`, `companies.json`):

| stratum | company | market cap |
|---|---|---|
| bank, large | Bank of Maharashtra (532525) | ₹61,832 Cr |
| life insurer, large | HDFC Life Insurance (540777) | ₹1,19,731 Cr |
| NBFC, large | Capri Global Capital (531595) | ₹23,789 Cr |
| NBFC, mid | Balmer Lawrie Investments (532485) | ₹1,437 Cr |
| IT, large | LTM (540005) | ₹1,26,064 Cr |
| IT, mid | Newgen Software Technologies (540900) | ₹6,972 Cr |
| pharma, mid | Hester Biosciences (524669) | ₹1,863 Cr |
| capital goods, mid | Balu Forge Industries (531112) | ₹5,787 Cr |
| FMCG, large | Milky Mist Dairy Food (544868) | ₹23,757 Cr |
| auto components, mid | Goodyear India (500168) | ₹1,583 Cr |
| metals, large | Hindustan Copper (513599) | ₹43,821 Cr |
| power, large | NTPC (532555) | ₹3,04,572 Cr |
| chemicals, small | Andhra Petrochemicals (500012) | ₹344 Cr |
| consumer durables, small | Exxaro Tiles (543327) | ₹270 Cr |

Window: filings from 15 July to 18 October 2026, as in round 2. Memory seeded from XBRL first (`seed-memory`).

## Method (round 2's, unchanged)

1. After the round-2 rebuild ends (one pipeline run at a time): `seed-memory --scrips ...`, then
   `backfill-companies --scrips ... --from 2026-07-15` with today's code and today's provider weights. DeepSeek's
   weight is not raised for this round (owner): it may be raised later for backfill speed only, once round 3 passes.
2. **Accuracy**: about 80 published cards, seeded and spread over the companies (`audit_round3/sample_cards.py`),
   exported blind (`audit_export.py --blind --memory --random 20261019`), one independent reviewer per folder with
   `REVIEWER_PROMPT_ROUND2.md`; memory points and impact tallied apart.
3. **Held cards**: about 10, mixed into the same folders, the reviewer not told which they are.
4. **Missed news**: about 50 filings the cards never covered, seeded (`audit_round3/recall_export.py`).
5. Tally with `audit_tally.py` and the manifest, published and held apart, WRONG by class.

## Pass marks, set before any processing or review (owner, 2026-10-18)

- **Accuracy: WRONG at most 15% of the published cards** reviewed. Memory-point errors counted apart, beside it.
- **Recall: at most 2 MISSED** of the ~50 filings set aside.
- **Holds**: reported, no mark.

**No check is loosened between this round's processing and its review.** A defect found while the round runs is
written down and fixed after the review, so the round measures the code as it stood when it started (commit
recorded here when the run begins).

Run started 2026-10-18 at commit `ccf98d1` (pipeline code as of 950db92), provider weights unchanged since round 2.

Both marks met -> the backfill decision (PLAN 1c, the owner's; scope options in `round-2.md`). Either missed -> the
commonest WRONG classes and every MISSED class are the next fixes, and a round 4 on fresh companies.

Run log: the first pass ended PARTIAL at 15:03 when the laptop lost its internet connection (DNS lookups for BSE
failed); 36 filings were marked failed after one attempt and 151 were still queued. The same command was started
again at 15:13 with the code unchanged; the queue retries failed filings below three attempts, so no filing was
requeued by hand. The connection dropped again during that pass, and the local site stopped with a session restart;
the site was restarted and the same command started a third time at 17:40, code still unchanged (`git diff 958a567
HEAD -- pipeline/src pipeline/config` empty). At that start: 54 filings analysed, 46 not material, 21 duplicates,
146 failed below three attempts (retried by the queue), 18 queued; 54 cards, 15 held.
