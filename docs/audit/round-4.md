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
