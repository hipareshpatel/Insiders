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

The run ended at 19:07 with one filing failed on its second attempt (a download cut off mid-transfer); the same
command run again at 19:08 analysed it. **No filing ended failed and none was requeued by hand.** Settled: 128 cards
(37 held, 29%), 104 not material, 53 duplicates; 143 more were dropped by rule at discovery.

## Results (reviewed 2026-10-18)

Sample drawn after the run (`sample_cards.py`, seed 20261019): 80 published cards from 13 companies (Goodyear had
none published) and 10 held cards, exported blind with memory into 9 folders, plus 50 set-aside filings for missed
news (`recall_export.py`). **Reviewed by the author of the pipeline's fixes, not blind and not by independent
reviewers** (owner: no agents), with `REVIEWER_PROMPT_ROUND2.md`'s rules, every figure checked against the filing text.
Findings: `round-3.json` (cards), `round-3/missed-news.json`, manifests in `round-3/`.

| | round 2 | round 2 re-run (F64) | **round 3** | mark |
|---|---|---|---|---|
| published cards WRONG | 29 / 80 (36%) | 13 / 70 (19%) | **10 / 80 (12.5%)** | ≤ 15% |
| held cards WRONG | 6 / 10 | 3 / 10 | 4 / 10 | none |
| missed news | 1 MISSED, 3 UNSURE / 50 | - | **1 MISSED, 2 UNSURE / 50** | ≤ 2 MISSED |
| memory points wrong | 37 cards | 11 cards | 8 / 90 cards | apart |
| impact level misfit | - | - | 10 / 90 (all too high) | none |

**Both marks are met.** All 90 cards: OK 56, MINOR 20, WRONG 14.

How close it is. The accuracy mark holds with two calls to spare: five published cards were judged MINOR on a
point a stricter reader could call WRONG - Andhra Petrochemicals' restart card ties FY26 revenue to an outage that
began two weeks before the year ended (the annual-report card with the same claim as its core catalyst was judged
WRONG), Balu Forge "first private Indian entity" where the release says "one of the first", HDFC Life's Q2 takeaway
crediting a lower expense ratio that was lower only QoQ, the OFS headline giving the 3% base without the 3% green
shoe, and a voting card with its two percentages blanked out. Three of those five as WRONG would be 16%.

The 10 published WRONG, by cause:

| cause | cards | example |
|---|---|---|
| a quantity read as a different one | 2 | Bank of Maharashtra: "₹65,000 Cr of advances added" carded as total advances ₹65,000 Cr; Capri: NNPA row labelled GNPA |
| sign or direction of a table line | 2 | Exxaro: inventory build and drawdown swapped, other expenses "rose" while they fell; HDFC Life: 83% persistency "below" an 80% target |
| a table read across its columns | 2 | Hindustan Copper: two-column designation table merged; NTPC: Q4 employee cost shown as Q1's |
| a ratio the model worked out | 1 | Milky Mist: "most of the PAT jump" from a deferred-tax credit that is 17% of it |
| a figure 100x in memory, then a signal | 1 | Newgen: employee cost ₹1,901 Mn stored as ₹19,010 Cr, so JAWS said +10,373% |
| event type | 1 | Hindustan Copper: two independent directors carded as ORDER_WIN |
| an invented cause | 1 | Andhra Petrochemicals: FY26 loss put on a five-month shutdown; the filing blames product prices |

Held WRONG (4, all HDFC Life or NTPC): a GST penalty of ₹2,423 Cr carded as the whole demand (tax ₹942 Cr comes on top),
new-business strain "narrowed" when it widened, NTPC's 136 GW renewables target carded as total capacity (250 GW), and
two quantified impacts on the wrong base (one still shown though code marked it MISMATCH).

Also seen, not counted WRONG: an AUDIT_FLAG from one filing repeated on later cards of the same company (3 cards); the
same "** **" blanked percentages that round 2's re-run found (3 cards; fixed on the post-round branch); memory holding
standalone quarters beside consolidated years (Capri, LTM), which skews ratios; two cards for one launch (Milky Mist).

Missed news: the one MISSED is LTM's 15 Oct "multi-million-dollar" managed-services deal, which pass 1 called a
routine corporate action. UNSURE: LTM leading L&T Group's Copilot rollout (no value, promoter group) and Milky Mist's
postal ballot to pay executive directors above the Section 197 limits (CMD about ₹10 Cr a year).

AI use (from the run logs, all four passes, outage retries included): 532 AI requests for 285 queued filings (1.9 a
filing, 4.2 per analysed filing), DeepSeek 89 (0.31 a filing), 25 rate-limited answers; about 106 filings an hour over
2.7 hours of running (round 2: 130 free, 165 with DeepSeek).

Next, in the owner's order: the backfill decision (PLAN 1c) and the DeepSeek weight for speed are the owner's; the
fixes written after round 2's re-run go in now (branch `fixes-after-round3`), then the causes above.
