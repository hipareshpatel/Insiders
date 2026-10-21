# Actions the daily card audit needs from the lead session

The daily audit (routine "Daily card audit (200 days)") may run without GitHub tools. It writes here each workflow
dispatch or merge it needs, one line each; the lead session's 15-minute check-in does them and marks them done with
the time and the run or PR link.

## Open

## Done

- 21 Oct 07:03 IST requeue-failed --ids (Yes Bank AT1 nse-106819548; Kapston nse-106822801; 6 later copies of a results quarter): dispatched again after run 9 ended; the live runs re-read them
- 21 Oct 06:51 IST both (refresh-card-blocks + refresh-summaries): run 9, success
- 21 Oct 06:46-06:57 IST market-data and nightly, started by hand after their scheduled slots did not fire: all steps OK (job records on /api/system)

- 21 Oct 06:31 IST apply-verdicts: maintenance run 7, success (https://github.com/hipareshpatel/Insiders/actions/runs/39524796716)
