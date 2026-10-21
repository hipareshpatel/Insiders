# Actions the daily card audit needs from the lead session

The daily audit (routine "Daily card audit (200 days)") may run without GitHub tools. It writes here each workflow
dispatch or merge it needs, one line each; the lead session's 15-minute check-in does them and marks them done with
the time and the run or PR link.

## Open

- requeue-failed --ids nse-106819548,nse-106822801,nse-106705473,nse-106635921,nse-106604225,nse-106606011,nse-106622331,feb1cb22-f062-4e82-90d9-434756f89309 (Yes Bank AT1 direction; 7 later copies of a results quarter: D20). Dispatched 06:31 IST, cancelled by GitHub when the next dispatch queued behind it in the same group (one pending run per group): dispatch again after run 9 ends, and from now on one dispatch at a time.

## Done

- 21 Oct 06:31 IST apply-verdicts: maintenance run 7, success (https://github.com/hipareshpatel/Insiders/actions/runs/39524796716)
- 21 Oct 06:31 IST both (refresh-card-blocks + refresh-summaries): maintenance run 9, started 06:31 (https://github.com/hipareshpatel/Insiders/actions/runs/39524816563)
