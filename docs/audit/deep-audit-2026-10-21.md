# Deep audit, 21 Oct 2026 (brief: docs/audit/deep-audit-prompt.md)

The seven auditors stopped at a usage limit before writing findings (20 Oct 21:15 UTC). The owner then asked for the
work to be done in the lead session with few subagents, so the areas are read here one at a time. Each finding:
severity, status (CONFIRMED = reproduced or seen live; PLAUSIBLE = read, not reproduced), where, what goes wrong,
and what was done.

## E. Orchestration, storage and operations

| id | sev | status | where | finding | done |
|---|---|---|---|---|---|
| E1 | HIGH | CONFIRMED live | `pipeline.py` `_backfill` | Backfill discovered up to 5 history days a run however far the analysis lagged: the 05:33 IST run on 21 Oct discovered 2,737 filings and wrote 7,234 D1 rows while the company queues were weeks behind, so discovery alone could eat the day's write budget and starve the analysis | Fixed (a30dc42): a further day only while fewer than 1,500 history filings wait (`filings_backlog`) |
| E2 | HIGH | CONFIRMED live | `sinks`, `cli.py` | Writes by maintenance commands were never added to the day's counter (93,369 shown when D1 refused writes at 100,000) | Fixed on #32 (counter counts every command) |
| E3 | HIGH | CONFIRMED | `db/statements/*` | Upserts and status updates wrote rows that did not change (re-runs with the same card, refresh-card-blocks / refresh-summaries over unchanged rows, a second market-data run, retried requests) | Fixed (c0e50cc): no write for an unchanged row; measured 1,000 -> 0 rows per 1,000 unchanged cards or companies |
| E4 | MEDIUM | CONFIRMED live | `pipeline.py` `run` -> `_run_critic` | The shadow critic ran inside the live part's deadline, so a run whose live filings used their share judged nothing (05:33 IST: 6 queued, 0 judged, "run time used") | Fixed: its own slot of at most 3 min after the live part, before the backfill |
| E5 | MEDIUM | CONFIRMED live | `maintenance.yml` concurrency | GitHub keeps one pending run per concurrency group, so a second dispatch queued behind a running one cancels the first queued one (the 06:31 IST requeue was cancelled by the refresh dispatched after it) | Process: one maintenance dispatch at a time (actions-pending.md); a list-of-commands input would remove it |
| E6 | LOW | CONFIRMED | `db/migrations/0011_card_write_trim.sql` | Its comment says the cards search index was rewritten on every update; migration 0005 had already narrowed that trigger, so 0011's trigger part changed nothing (the index drops did) | Noted; migrations are applied and not edited |
| E7 | MEDIUM | PLAUSIBLE | `pipeline.py` `_record` / NSE | A known filing whose attachment changes is now counted (`stats.attachment_changed`) but not re-read until a day's count shows NSE keeps unchanged links stable | Watch the count in the runs' stats, then set ATTACHMENT_REQUEUE=1 |
| E8 | HIGH | CONFIRMED live | `nightly.yml`, `market-data.yml` schedules | Neither daily job fired at its slot on 21 Oct (GitHub drops scheduled runs when busy; seed-calls lost runs the same way on 20 Oct), so prices, governance, shareholding, pledges, DGTR, annual reports and summaries would silently go stale | Started by hand 06:40 IST; fixed: `watchdog.py` + `missed-jobs`, the 15-minute pipeline starts a daily job with no run recorded 45 min after its slot, once a day |
