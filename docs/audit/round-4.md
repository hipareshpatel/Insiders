# Audit round 4: the measured NSE round, 20 companies the pipeline has never read

Written 2026-10-19, before any round-4 company was processed. This is PLAN 18's step 3: the NSE pipeline (parts 1-8:
NSE discovery and attachments, event XBRL, results from NSE's integrated filing, shareholding and governance into
memory) measured on companies none of its fixes were fitted on, at the owner's ₹500 Cr floor (D31). The owner asked for
at least 100 cards to be checked (2026-10-19), so 20 companies where round 3 had 14.

## Sample

Twenty companies, one per sector-and-size stratum (large ≥ ₹10,000 Cr, mid ₹500-10,000 Cr), listed on NSE, with no
filing in the ledger, drawn with seed **20261020** (`pipeline/scripts/audit_round4/select.py`, `companies.json`):

| stratum | company | market cap |
|---|---|---|
| bank, large | RBL Bank (540065) | ₹58,079 Cr |
| NBFC, large | HUDCO (540530) | ₹32,261 Cr |
| NBFC, mid | Wealth First Portfolio Managers (544536) | ₹938 Cr |
| insurer, large | Star Health and Allied Insurance (543412) | ₹32,374 Cr |
| IT, large | Cyient (532175) | ₹12,481 Cr |
| IT, mid | Excelsoft Technologies (544617) | ₹956 Cr |
| pharma, large | Torrent Pharmaceuticals (500420) | ₹1,75,189 Cr |
| pharma, mid | Anlon Healthcare (544497) | ₹1,465 Cr |
| capital goods, large | Siemens (500550) | ₹1,30,347 Cr |
| capital goods, mid | Jai Corp (512237) | ₹1,670 Cr |
| chemicals, mid | Foseco India (500150) | ₹4,725 Cr |
| metals, mid | Manaksia Coated Metals (539046) | ₹1,355 Cr |
| auto components, mid | Sterling Tools (530759) | ₹801 Cr |
| FMCG, large | Nestlé India (500790) | ₹2,46,824 Cr |
| consumer durables, mid | Hawkins Cooker (508486) | ₹4,172 Cr |
| construction, mid | McNally Bharat Engineering (532629) | ₹1,429 Cr |
| realty, mid | AGI Infra (539042) | ₹3,083 Cr |
| textiles, mid | RSWM (500350) | ₹942 Cr |
| cement, large | Nuvoco Vistas (543334) | ₹11,981 Cr |
| power, large | NHPC (533098) | ₹72,907 Cr |

Window: filings from 15 July to 18 October 2026, as in rounds 2 and 3.

## Method

1. Memory first, with no AI call: `seed-memory --scrips ...` (results and shareholding history from XBRL),
   `governance-sync --pages 2 --scrips ...` (the June and September governance reports).
2. `backfill-companies --scrips ... --from 2026-07-15 --to 2026-10-18` with **free providers only** (`FREE_ONLY=1`:
   the online pipeline will run without the paid route; rounds 2-3 had DeepSeek at its backfill weight), NSE as the
   discovery source.
3. **Accuracy**: at least 100 published cards (110 drawn if the run makes them), seeded and spread over the companies
   (`audit_round4/sample_cards.py`), exported blind (`audit_export.py --blind --memory --random 20261020`), one
   independent agent per reviewer folder with `REVIEWER_PROMPT_ROUND2.md`; the author of the fixes does not review.
   About 10 held cards mixed in, unmarked.
4. **Missed news**: about 50 filings the cards never covered, seeded (`audit_round4/recall_export.py`), blind agents.
5. Tally with `audit_tally.py`; published and held apart, WRONG by class; memory points and impact apart.
6. Measured alongside: filings an hour, AI requests a filing, 429s, on free tiers - the backfill's sizing (PLAN 18).

## Pass marks, set before any processing or review

- **Go-live (owner, 2026-10-18): WRONG at most 5% of the published cards** (95% right). This round is the first
  measured against it.
- **The round's earlier mark: WRONG at most 15%** (rounds 2-3), reported beside it.
- **Recall: at most 2 MISSED** of the ~50 set-aside filings.
- Held cards and memory-point errors reported, no mark.

No check is loosened between this round's processing and its review. A defect found while the round runs is written
down and fixed after the review, so the round measures the code as it stood when it started (commit recorded below).

Results go below once reviewed. Below 95%: the commonest WRONG classes and every MISSED class are the next fixes,
with card output and contextual memory first (owner, 2026-10-19), then a round 5 on fresh companies.

## Run

Started 2026-10-19 02:22 IST at commit `32a518b` (`backfill-companies`, FREE_ONLY=1), after `seed-memory` (168 results
quarters, 166 shareholding quarters; one 2025 shareholding file of Manaksia answered 404) and `governance-sync` (14 of the
20 companies had a governance report in NSE's list's last 2,000 rows).

Defects seen in the run's log, fixed in code after the round started (the run keeps the code it started with, so the
round still measures `32a518b`):
- Siemens Q1FY27: the card's "PAT (Continuing) ₹343 Cr (-18.7% YoY)" was replaced by the file's total PAT, ₹2,143.10 Cr
  with the demerged business's gain (+406%). A continuing label now takes the file's continuing-operations PAT; a
  discontinued one is left as read.

## Results (reviewed 2026-10-19 by 18 independent blind agents)

The run settled all 309 queued filings in 1 h 22 min on free providers only (about 225 filings an hour; round 3 106 with
DeepSeek): 122 cards (28 held, 23%), 144 not material, 43 duplicates; 262 more dropped by rule at discovery. AI requests:
534 for 309 filings (1.7 a filing, 4.4 a card) - Mistral 251, NVIDIA 146, Z.ai 69, OpenRouter 57, Gemini 11 - with 5
rate-limited answers (429) and 3 server errors. Every published card (94, from 17 companies) and every held card (28),
mixed blind, were reviewed in 13 folders with `REVIEWER_PROMPT_ROUND4.md`; 50 set-aside filings in 5. Findings:
`round-4.json`, `round-4/`.

| | round 3 (agents) | **round 4 (agents)** | mark |
|---|---|---|---|
| published cards WRONG | 10 / 80 (12.5%) | **20 / 94 (21%)** | go-live ≤ 5%; round ≤ 15% |
| held cards WRONG | 6 / 10 | 10 / 28 | none |
| missed news | 2 MISSED, 3 UNSURE / 50 | **2 MISSED, 3 UNSURE / 50** (1 MISSED once checked) | ≤ 2 MISSED |
| all cards OK / MINOR / WRONG | 29 / 45 / 16 | 31 / 61 / 30 | |
| memory points wrong | 36 cards | 23 cards | apart |
| impact level misfit | 25 / 90 | 38 / 122 | none |

**Accuracy fails both marks; recall passes.** The figures themselves held up better than the words around them: most
reviewers recomputed every ₹ amount and change on most cards. By writer: nemotron-3-super 65 cards, 26% WRONG;
glm-4.5-flash 24, 17%; nemotron-3-ultra (free, OpenRouter) 12, **58%**; nemotron-3.5-super-vl 10, 10%; Gemini 9, 11%.
Round 3 had the paid route writing a share of its cards; this round had none (as the online pipeline will run).

Published WRONG by cause (the 20, from the reviewers' reports):
- **Invented causes, outcomes and stages** (most): profit "on lower tax" when tax rose (AGI Infra, RSWM, Sterling Tools
  twice), "lower credit costs" when they rose 53% (RBL), an income-tax visit "concluded without penalties" (RSWM), a
  scheme "after NCLT approval" when only the meetings were dispensed with (Siemens), a reclassification that "reduces
  promoter shareholding" of nil holders (Siemens), creditors' recovery money "improving liquidity" (McNally), a merger
  effect credited before the merger (Anlon).
- **Units the code did not catch**: a rating table in INR million read as crore (AGI Infra, 10x), "INR 3 Million" as
  ₹3 Cr (Excelsoft), Rs billion as crore (RBL, 100x), NGN 90 million as ₹ (Anlon).
- **Direction and sign**: change in inventories read the wrong way (Nestle, RSWM, Foseco), EPS "declined" when up 48%
  (Nestle), a margin fall shown as expansion (Nestle), an arbitration claim against NHPC carded as an award in its favour.
- **Signals from code that contradict the filing**: BOARD_DELIBERATION ("the board meeting ran 8.0 hours") on a
  postal-ballot result (Torrent), CAPITAL_DILUTER and JAWS on mixed bases (Sterling Tools, Cyient), REG30_THRESHOLD
  against "no major financial impact" (Nuvoco, Siemens), DISTRESS on a lender's interest cover (HUDCO).
- **Deal figures**: Anlon's ₹153.3 Cr share swap stored in memory and the timeline as ₹1,533 Cr; the two targets' share
  counts and prices swapped; Siemens' continuing PAT replaced by total PAT (fixed during the run, `a264359`).

Missed news: Nestle's ₹6.67 Cr Tripura VAT demand (borderline for a company of Nestle's size); Anlon's board outcome
filed under "Record Date" and dropped unread - the same outcome filed as "Outcome of Board Meeting" (nse-106743024) has a
published card, so the news was not lost. UNSURE: RBL's USD 350 mn notes (a duplicate of nse-106776948, whose card is
held: the news did not reach the feed), Cyient's director resignation (the zip filing; its XBRL names an independent
director's tenure ending: RIGHT under D30), McNally's results clarification query (text blank).

Note on the missed-news prompt: a cloud session changed it after it was set (7794802, "MD/CEO/CFO exits keep a card,
owner, D30 amended") while the pipeline still drops those exits. No MISSED or UNSURE verdict here turned on such an exit.

Next: the classes above, in code first (units, directions, signals, deal arithmetic), then the writer routes (the
58% model off pass 2), then the prompt's limits on causes and stages; re-run these same 122 cards as a measured re-run,
then round 5 on fresh companies.

## Measured re-run on the fixes (2026-10-19, `7dc29f7` + the long-document spare `92190f3`)

The 20 companies rebuilt from scratch (`audit_round4/reset.py`: cards saved to `data/audit/round4/cards_before_rerun.json`,
deleted, all 309 filings back in the queue, memory emptied, re-seeded from XBRL and governance), then read again on free
providers only: 50 minutes. One filing, Anlon's 13 Aug board outcome (a long document), failed twice on the
long-document route on free tiers (no card). 120 cards (28 held), all reviewed blind by 12 new agents with the same
prompt. Findings: `round-4-rerun.json`.

| | round 4 | **re-run** | mark |
|---|---|---|---|
| published cards WRONG | 20 / 94 (21%) | **12 / 92 (13%)** | go-live ≤ 5% |
| held cards WRONG | 10 / 28 | 16 / 28 | none |
| all cards OK / MINOR / WRONG | 31 / 61 / 30 | 42 / 50 / 28 | |
| published cards OK | 27 | 36 | |
| impact level misfit | 38 / 122 | 34 / 120 | none |

By writer: Nemotron 3 Super 80 cards, 24% WRONG (all cards); GLM-4.5-Flash 28, 25%; Nemotron 3.5 Super VL 7, 0%;
GLM-4.7-Flash 5, 40%. The held cards now catch most WRONG ones (16 of 28 held are WRONG).

What is still WRONG on published cards (reviewers' reports):
- **Rupee amounts written out in full** ("Rs 11,10,59,061" carded as ₹1.11 Cr, Nestle; "Rs. 1,165,179,600" as ₹1,165 Cr,
  Anlon; "Rs 85,000 million" as Rs 8,500 million, Siemens) and a statement in ₹ million read as crore (Nestle other
  income ₹224.7 Cr for ₹22.47 Cr): the unit checks do not yet read whole-rupee figures.
- **Units not caught where expected**: Excelsoft's "INR 3 Million" still ₹3 Cr (its deal size field is not corrected;
  the text check did not fire on the live text); RBL's billion table now ₹15,628 Cr for ₹1,56,280 Cr.
- **Direction claims the guard missed**: inventory read the wrong way on cards whose claim sits in a notable change or
  without XBRL (RSWM's presentation, Sterling Tools), "reversal of deferred tax" (RSWM), "tax base effect" (AGI Infra).
- **Invented causes and outcomes remain the largest class** (44 issues on all cards): Star Health's turnaround put on
  underwriting when investment income drove it, McNally's creditors' money "improving liquidity", merger effects before
  the merger (Anlon), "completes the programme" for one tranche (RBL).
- **Metric mislabels**: gross written premium growth as revenue growth (Star Health), exports growth as a tax rate
  (Nestle), segment margin ambition as revenue CAGR (Cyient), a pricing supplement as the issue.

Next: whole-rupee amounts and the remaining unit paths, the direction guard on notable changes and without XBRL, then
round 5 on fresh companies.

