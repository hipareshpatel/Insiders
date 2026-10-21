# Actions the daily card audit needs from the lead session

The daily audit (routine "Daily card audit (200 days)") may run without GitHub tools. It writes here each workflow
dispatch or merge it needs, one line each; the lead session's 15-minute check-in does them and marks them done with
the time and the run or PR link.

## Open

- After the units fix reaches main: requeue-failed --ids nse-106823248 (Mahindra Holidays, figures cut 100x by the unit fixer)




## Done

- 21 Oct 16:07 IST seed-memory (restart off, resume after 512008; deep audit D1): dispatched on main; a pass that ends with companies left starts the next outside market hours

- 21 Oct 13:05 IST requeue-failed --ids nse-106822983,nse-106619863,nse-106635264,nse-106743427 (order wins typed litigation): dispatched after #38 merged; the live runs re-read them

- 21 Oct 10:48 IST export-critic: dispatched on main after #36 merged; it commits docs/audit/live/critic-2026-10-21.json
- 21 Oct 10:46 IST export-held: committed docs/audit/live/held-2026-10-21.json to the branch

- 21 Oct 10:45 IST export-held (asked by the 10:07 audit): dispatched on main; it commits docs/audit/live/held-2026-10-21.json

- 21 Oct 07:03 IST requeue-failed --ids (Yes Bank AT1 nse-106819548; Kapston nse-106822801; 6 later copies of a results quarter): dispatched again after run 9 ended; the live runs re-read them
- 21 Oct 06:51 IST both (refresh-card-blocks + refresh-summaries): run 9, success
- 21 Oct 06:46-06:57 IST market-data and nightly, started by hand after their scheduled slots did not fire: all steps OK (job records on /api/system)

- 21 Oct 06:31 IST apply-verdicts: maintenance run 7, success (https://github.com/hipareshpatel/Insiders/actions/runs/39524796716)
