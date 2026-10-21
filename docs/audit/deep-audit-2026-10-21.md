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

## C. Checks and card building

| id | sev | status | where | finding | done |
|---|---|---|---|---|---|
| C1 | HIGH | CONFIRMED (probe) | `grounding.SourceIndex.stated_crore`, quote checks | The figure checks are sound on units: "INR 99,09,87,896" accepts ₹99.10 Cr and refuses ₹9.91 Cr, 0.99 and 991; a lakh table refuses the 10x and 100x slips. The LIC card's "₹9.91 Cr demand" passed because ₹9.91 Cr is in the filing: it is the penalty. Attribution (which line a printed figure belongs to) is not something a number check can see; the same holds for the Airtel state figure and the Cyient segment figures | Covered by the new prompt rules (scope, units, same-event) and by the shadow critic, which judges each point's meaning against its quote; measured by the daily audit |
| C2 | MEDIUM | CONFIRMED (read) | `trust.Checker.printed_crore` | A figure goes into memory when it is printed anywhere in the filing at the declared unit and within 10x of the company's scale, so a figure attributed to the wrong line (C1) can enter memory too and be reused on later cards | Open: memory could require the figure's own quote line (as the card's checks do) before it is kept; measure on stored dossiers first |

## B. The AI layer

| id | sev | status | where | finding | done |
|---|---|---|---|---|---|
| B1 | HIGH | CONFIRMED (measured) | `prompts/engine.py` `pass2`, `config/prompts/pass2.md` | Every card call sends a ~35,800-character system prompt (~9,000 tokens) before the filing: the 26.5 KB general rules, the full output schema for every event type (5.6 KB, pretty-printed), the event focus (0.6-1.4 KB) and the sector lens. A rating card gets the results, capex, deal, call and quantified-impact rules and fields it never uses; long prompts are why long filings cannot be packed and fall to the weakest model (plan item 1), and conflicting rules leave the model to choose | Open, the biggest lever (AI-quality plan item 5): a short prompt per event family with only its fields and two worked examples from cards reviewers judged right, tried on a share of live cards and compared in the daily audit before it replaces the long one |
| B2 | LOW | CONFIRMED (measured) | `prompts/engine.py` `pass2` | The schema is pretty-printed (indent 1): 5,569 characters against 4,352 compact, ~300 tokens a call for nothing | Folded into B1 (changing the wording the model sees is measured with the rest) |
