# Actions the daily card audit needs from the lead session

> **History since 27 Oct 2026.** The current state and the one list of open work are in [`docs/STATUS.md`](../STATUS.md). Read this file for its findings; do not work from its lists.

The daily audit (routine "Daily card audit (200 days)") may run without GitHub tools. It writes here each workflow
dispatch or merge it needs, one line each; the lead session's 15-minute check-in does them and marks them done with
the time and the run or PR link.

## Open

- After the seed passes end (maintenance busy until then; a requeue dispatched before would be replaced in the queue): `requeue-failed --ids nse-106705473,nse-106635921,nse-106707056,nse-106597136,nse-106601360` (B3: the later card of the Sunteck Q1FY27 and Sun Pharma Q4FY26 duplicate pairs, which the one-card-per-quarter rule now marks duplicate; the three "uploads audio recording" cards, which today's rules keep out of the feed). Vedanta/HZL: no filing id found; left.
- Standalone-made results cards, measured 21 Oct over the 30-day feed: 14 RESULTS cards on a standalone file; 4 of them for companies memory knows file consolidated (Wendt nse-106823265, HDFC Life 4af25650-945d-486d-ae4d-134cc1c6f69a, ICICI Lombard nse-106817737, ICICI Pru Life nse-106815694), all within 10 days, so the results catch-up re-reads each once its consolidated file is listed. The other 10 are checked again after the seed, when memory knows each company's basis.
- The 13 results cards made on a standalone XBRL since 20 Sep: the results catch-up reads the recent ones again once their consolidated file is listed. Older ones (more than 10 days) stay unless re-run by id after a check of which companies file consolidated.

## Done

- 21 Oct 21:44 IST maintenance `both` after #46 (run 17). 22:33 IST `fill-memory` (days 110) dispatched on main after hipareshpatel/Insiders#48: shareholding two quarters, governance, a year of pledges, DGTR, with the AI pipeline paused for those steps; it then starts the seed passes itself (replaces the separate seed-memory dispatch).

- 21 Oct 21:33 IST requeue-failed --ids (14: Mahindra Holidays, LMW, Jubilant; CONCOR, Bajaj Finserv, SRF, UltraTech, Jindal Stainless, LTM, NTPC, GMDC, Eternal, Unicommerce; Yes Bank AT1): maintenance run 16, success, after #45 merged. The seed-memory pass on the old order was cancelled for it (resumes from its saved point).

- 21 Oct 16:07 IST seed-memory (restart off, resume after 512008; deep audit D1): dispatched on main; a pass that ends with companies left starts the next outside market hours

- 21 Oct 13:05 IST requeue-failed --ids nse-106822983,nse-106619863,nse-106635264,nse-106743427 (order wins typed litigation): dispatched after #38 merged; the live runs re-read them

- 21 Oct 10:48 IST export-critic: dispatched on main after #36 merged; it commits docs/audit/live/critic-2026-10-21.json
- 21 Oct 10:46 IST export-held: committed docs/audit/live/held-2026-10-21.json to the branch

- 21 Oct 10:45 IST export-held (asked by the 10:07 audit): dispatched on main; it commits docs/audit/live/held-2026-10-21.json

- 21 Oct 07:03 IST requeue-failed --ids (Yes Bank AT1 nse-106819548; Kapston nse-106822801; 6 later copies of a results quarter): dispatched again after run 9 ended; the live runs re-read them
- 21 Oct 06:51 IST both (refresh-card-blocks + refresh-summaries): run 9, success
- 21 Oct 06:46-06:57 IST market-data and nightly, started by hand after their scheduled slots did not fire: all steps OK (job records on /api/system)

- 21 Oct 06:31 IST apply-verdicts: maintenance run 7, success (https://github.com/hipareshpatel/Insiders/actions/runs/39524796716)
- Re-run Sapphire Foods nse-106824614 (Q2FY27 'PAT turns positive' on a ₹1.51 Cr loss; the direction check from 22 Oct cuts it) when a slot is free.

- **23 Oct, trades fill remainder** (after the market close, one at a time: it pauses the AI pipeline): `insider-sync --days 180` reads only the 656 filings not yet read (it skips read ones); `deals-backfill --days 62` covers 22 Aug - 21 Oct (the first run reached 21 Aug). Dispatch maintenance `fill-trades` again, or run the two commands with those days.
