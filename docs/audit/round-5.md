# Audit round 5: a second measured NSE round, after round 4's fixes

Written 2026-10-19, before any round-5 company was processed. Round 4 (`round-4.md`) failed accuracy at 21% of published
cards WRONG on free providers; its classes were fixed in two waves (TRACKER F73 and after) and its own companies' re-run
measured 13%. A re-run is measured on the cards the fixes were written from, so this round asks the honest question on 20
companies none of them was fitted on.

## Sample

Twenty companies, one per round 4's sector-and-size strata (large ≥ ₹10,000 Cr, mid ₹500-10,000 Cr), listed on NSE, with
no filing in the ledger (so none of rounds 2-4 or the smoke test), drawn with seed **20261021**
(`pipeline/scripts/audit_round5/select.py`, `companies.json`): UCO Bank, Sundaram Finance, Repco Home Finance, Max
Financial Services, Persistent Systems, Protean eGov, Granules India, Lincoln Pharmaceuticals, Siemens Energy India,
Texmaco Rail, Balaji Amines, Electrosteel Castings, Saint-Gobain Sekurit, Dabur India, IFB Industries, Ceigall India,
Runwal Enterprises, Sunrakshakk Industries, Ramco Cements, NLC India.

Window: 15 July to 18 October 2026, as in rounds 2-4.

## Method (round 4's)

Memory first (`seed-memory`, `governance-sync --scrips`), then `backfill-companies` on free providers only
(`FREE_ONLY=1`). Every published card and every held card (mixed in, unmarked) reviewed blind by independent agents,
one per folder, with `REVIEWER_PROMPT_ROUND4.md` word for word (the exports now carry the XBRL table itself); the author
of the fixes does not review. Missed news: ~50 set-aside filings, same prompt.

## Pass marks, set before any processing or review

- **Go-live: WRONG at most 5% of published cards** (owner, 2026-10-18).
- Beside it, rounds 2-4's mark: WRONG at most 15%.
- Recall: at most 2 MISSED of ~50.

No check is loosened between processing and review; a defect seen in the run is written down and fixed after.
