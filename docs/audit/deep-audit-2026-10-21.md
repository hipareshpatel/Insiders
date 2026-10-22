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
| E9 | HIGH | CONFIRMED live | `ai/gateway.py` `reserved_for_live`, `providers.toml` `[gateway.live_reserve]` | The live reserve was released in full during bulk hours (21:00-09:00 IST), but Gemini's quota day ends at midnight Pacific (12:30 IST), so the night and the next market morning share one day: on 21 Oct every Flash model was at its day by 08:30 IST and the 07:04, 07:50 and 08:24 IST runs ended PARTIAL ("every AI provider busy", 5 filings failed in one) while 09:00-12:30 IST carries ~27% of live cards (15 of 56 on 16, 19, 20 Oct) | Fixed: `bulk_hours_share = 0.3` keeps 30% of each reserved model's day for live filings through the bulk hours (backfill may use 13 of 19 overnight, 3 by day); restricts backfill only |
| E10 | MEDIUM | CONFIRMED live | `pipeline.py` `_attempt` (AllProvidersFailed) | A filing whose only reachable writer was a spare that failed, while the better writers sat at their day or in the live reserve, spent one of its three attempts: 21 Oct 08:24-10:25 IST, 11-15 filings a run (74 failed by 11:15 IST), so three such mornings fail a filing for good | Fixed: such a failure (a ceiling among the outcomes) defers the filing up to MAX_DEFERRALS runs (`deferred Nx: the better writers are at their day`); a failure with every writer tried still spends an attempt at once (test) |
| E11 | MEDIUM | CONFIRMED live | `pipeline.py` `_live_jobs`, `HISTORY_INLINE = 30` | Each live company's pending history (up to 30 filings) is analysed before its new filing so the card has memory; with the backfill weeks behind, a company with a long tail holds a worker for most of a run. 21 Oct 13:25 IST: 30 of today's filings pending, 5 cards for today's filings, while the 12:37 IST run analysed 35 (mostly history) | Confirmed by the 13:19 IST run (Gemini back): 23 analysed, 1 of them today's, 27 of today's waiting. Fixed: HISTORY_INLINE 30 → 5; a company with a longer backlog gets its live card at once (memory still building) and moves to the front of the backfill, as before |

## C. Checks and card building

| id | sev | status | where | finding | done |
|---|---|---|---|---|---|
| C1 | HIGH | CONFIRMED (probe) | `grounding.SourceIndex.stated_crore`, quote checks | The figure checks are sound on units: "INR 99,09,87,896" accepts ₹99.10 Cr and refuses ₹9.91 Cr, 0.99 and 991; a lakh table refuses the 10x and 100x slips. The LIC card's "₹9.91 Cr demand" passed because ₹9.91 Cr is in the filing: it is the penalty. Attribution (which line a printed figure belongs to) is not something a number check can see; the same holds for the Airtel state figure and the Cyient segment figures | Covered by the new prompt rules (scope, units, same-event) and by the shadow critic, which judges each point's meaning against its quote; measured by the daily audit |
| C2 | LOW | MEASURED 21 Oct | `trust.Checker.printed_crore` | A figure goes into memory when it is printed anywhere in the filing at the declared unit and within 10x of the company's scale, so a figure attributed to the wrong line (C1) could enter memory and be reused | Measured on the live memory of 224 companies on the feed (no AI, `pipeline/scripts/memory_xbrl_agree.py`): where a card-read figure and the company's XBRL share metric, period and basis, they agree in 2,804 of 2,824 (99.3%); of the 20 that differ, 1 is a lakh-as-crore slip (Ambuja FY26 PAT 5,63,700 for 5,637.08), most are EBITDA (the company's own definition against the one computed from XBRL) and a few look like standalone figures labelled consolidated. Memory serves the XBRL value in all 20 (`_metric_entry`). Not worth a stricter rule that would drop true figures; the open risk is card-only periods, which the daily audit samples |

## D. Memory

| id | sev | status | where | finding | done |
|---|---|---|---|---|---|
| D1 | HIGH | CONFIRMED live | `maintenance.yml` seed-memory (T13 step 1), `dossier._metric_entry` | The basis re-seed stopped at company 512008 when D1 refused writes (20 Oct 19:29 UTC, `kv_set` 500) and was never resumed. Companies after it, and quarters older than the seed window, still hold laptop-era XBRL figures with no basis, and a basis-less XBRL source outranks consolidated cards: Heritage (519552) Q4FY25 PAT is 20.51 (standalone) in memory while five consolidated filings say 38.17, the T5 case the fix was meant to clear. Over 224 live companies, 25,456 XBRL sources have no basis (86 companies), and 706 of 9,407 card figures (7.5%) differ from such a source, against 0.7% where the basis is stated | Resume seed-memory (not restart) after the close, outside 08:00-16:00 IST; then re-measure with `pipeline/scripts/memory_xbrl_agree.py` and re-run Heritage's three cards (PLAN) |

## B. The AI layer

| id | sev | status | where | finding | done |
|---|---|---|---|---|---|
| B1 | HIGH | CONFIRMED (measured) | `prompts/engine.py` `pass2`, `config/prompts/pass2.md` | Every card call sends a ~35,800-character system prompt (~9,000 tokens) before the filing: the 26.5 KB general rules, the full output schema for every event type (5.6 KB, pretty-printed), the event focus (0.6-1.4 KB) and the sector lens. A rating card gets the results, capex, deal, call and quantified-impact rules and fields it never uses; long prompts are why long filings cannot be packed and fall to the weakest model (plan item 1), and conflicting rules leave the model to choose | Built (A/B): `prompts/pass2_short.md` + `engine.short_schema` / `field_rules`: the shared rules, the reviewers' mistakes and only this filing kind's fields with their rules copied from pass2.md, 11.5-17K characters (long 35.8K). On 30% of live filings (PROMPT_SHORT_SHARE, by news-id hash; backfill keeps the long one); `card_json.grounding.prompt_variant` records which wrote a card, and the daily audit scores the two apart. Worked examples from right-judged cards to follow once the audit has rated enough |
| B2 | LOW | CONFIRMED (measured) | `prompts/engine.py` `pass2` | The schema is pretty-printed (indent 1): 5,569 characters against 4,352 compact, ~300 tokens a call for nothing | The short prompt sends the shape compact |

## A. Intake and extraction (independent reviewer, 21 Oct; `scratchpad deep-audit/A`, every file in scope read)

| id | sev | status | where | finding | done |
|---|---|---|---|---|---|
| A-01 | HIGH | CONFIRMED | `xbrl.py` BALANCE_TAGS | An insurer's "Assets" is the application of funds net of current liabilities; ICICI Lombard's ₹20,891.52 Cr stored as total assets beside ₹64,332 Cr of investments | Fixed: insurers' totals dropped; any totals that do not add up (assets = equity (+ minority) + liabilities within 2%) refused (`_check_balance`) |
| A-02 | MEDIUM | CONFIRMED | `nse.py` parse_results_rows | The older results list's rows had no quarter end, so the seed never reached before Q4FY25 (Titan: 6 quarters) | Fixed: `period_end` from `toDate`, rows marked `legacy`; the seed reads them (integrated filing first), cards' comparative links do not |
| A-03 | MEDIUM | CONFIRMED | `xbrl.py` | Pre-2025 files tag the year to date ("FourD") with the quarter's dates: the year's figures lost, its cash flow stored as the quarter's (Asian Paints FY24 OCF 6,103.6 as Q4FY24) | Fixed: FourD starts on 1 April (`_legacy_year_to_date`); cash-flow lines refused on three-month contexts. FY22-era files that reference undefined contexts still do not parse (FY22 stays a gap) |
| A-10 | MEDIUM | CONFIRMED | `xbrl.py` | Banking and NBFC templates' capital, reserves, borrowings, loans, investments and cash not mapped: no bank had a net worth, Bajaj Finance no debt | Fixed: tags mapped; a bank's net worth and liabilities derived; NBFC debt = borrowings + debt securities + subordinated |
| A-05, A-06 | MEDIUM | CONFIRMED | `rules.py`, `periods.py` | NSE's "21-Oct-2026" not read: 26 of 27 record dates of 14-21 Oct never reached the calendar | Fixed (both patterns accept hyphens) |
| A-04 | MEDIUM | CONFIRMED | `event_xbrl.amount_found` | A year or a percentage "confirmed" an order amount, then overwrote the deal value | Fixed: years and percentages are not amounts (accepts less) |
| A-07 | MEDIUM | CONFIRMED | `pipeline._xbrl_comparatives` | Year-ago and previous-quarter NSE files fetched through the BSE client (no NSE pacing or refusal handling) | Fixed: NSE's client for NSE files |
| A-08, A-09 | MEDIUM | PLAUSIBLE | `pipeline` event match, `event_catchup` | One candidate event file answering 404 aborts the match and records nothing, so the card is re-run every run for 5 days; the catch-up re-runs a published card whenever a new file of the same family appears | Open |
| A-14 | MEDIUM | PLAUSIBLE | `raw.py` | The raw copy's key includes the fetch time, so unchanged answers are stored again every run; nothing prunes `raw/` (est. 0.5-1.5 GB a month of R2's free 10 GB) | Open: measure `raw/` size, then key by content hash |
| A-15 | MEDIUM | PLAUSIBLE | `extract.py` | OCR failing on a document under 50% scanned makes the card from the text read, without those pages | Open |
| A-11..A-23 | LOW | | | bank opex in other expenses, capex sign, non-March years, one page of the integrated list, empty balance-sheet snapshots (HDFC Bank 3 of 3), SBI's two bases | Open (listed in the reviewer's findings.json) |

## F. Website (independent reviewer, 21 Oct; `scratchpad deep-audit/FG`, rendered at 390 and 1440 px)

| id | sev | status | where | finding | done |
|---|---|---|---|---|---|
| F-01 | HIGH | CONFIRMED | `statements.ts` isBank | One stray "revenue" figure flipped 11 of 41 banks to the Sales/OPM layout (SBI "Sales 1,81,079") | Fixed: a bank by interest earned on most of its quarters |
| F-02 | HIGH | CONFIRMED | memory (area D) | CSB Bank's Q1FY27 EPS 35.00 (a card's annualised figure) over its XBRL 8.65; the tables show memory's value | Fixed 22 Oct: memory already prefers XBRL, but CSB had none for Q1FY27; the 35.00 came from its concall presentation (annualised), which replaced the results card's 8.65. Per-share figures now join the flows only a results filing or the XBRL may restate for a quarter (`dossier.QUARTER_OWNED`, test). The seed adds CSB's XBRL |
| F-03 | MEDIUM | CONFIRMED | `statements.ts` mainBasis | The metric's own basis field ignored: the "Consolidated" label and the switch vanished (HDFCBANK, ICICIBANK) | Fixed |
| F-04..F-07 | MEDIUM | CONFIRMED | `statements.ts` | CAGR by array position; TTM growth across gaps; minority interest missing so the balance sheet did not add up; a missing other income counted as zero | Fixed (tests); EPS not split-adjusted stays open |
| F-08 | MEDIUM | CONFIRMED | company page | The 60-card cap shown as the total (SMLMAH 60 of 89) | Fixed: the count is the company's, and the list says "the latest 60 of 89" |
| F-09 | MEDIUM | CONFIRMED | `public.ts` | No index on companies.symbol or sector: two table scans per company view | Fixed: migration 0013 |
| F-10 | MEDIUM | CONFIRMED | `public.ts` | `/company/tcs` answered 400 | Fixed: the key is upper-cased first |
| F-11 | MEDIUM | CONFIRMED | `TodayView.tsx` | Today never reads the R2 snapshot (about 10 D1 calls a view); SPEC says it does | Open |
| F-12 | MEDIUM | CONFIRMED | `cardText.ts` | A fact with any quote counts as verified on the face though its quote may not be in the filing (93 of 300 cards) | Open: store a per-fact `quote_found` (stricter, no audit needed) |
| F-13, F-14 | MEDIUM | CONFIRMED | card tiles, owner verdicts | Tile colour from the first character ("GNPA -17 bps" red); a verdict that fails (401) still looks saved | Fixed 22 Oct: `changeTone` (sign of the first figure or up/down, turned round for NPA, costs, debt, losses; no direction is grey, not green; tests); a refused verdict rolls back and says "Not saved" |
| F-15, F-16 | MEDIUM | CONFIRMED | Today on a phone; light theme | Filters take 326 of 844 px; text contrast 2.8-3.5:1 against 4.5:1 | Open |

## H. D1 reads (found 22 Oct, after the audit)

| ID | Severity | Status | Where | Finding | Resolution |
|---|---|---|---|---|---|
| H-01 | HIGH | MEASURED 22 Oct | `public.ts` peers, `filings_pending.sql` | D1's free 5,000,000 rows read a day ran out on 20 Oct (6,532,645) and 21 Oct (5,367,140, from 20:29 UTC): the site and every job answered 500 until 00:00 UTC. Nothing measured reads. Peers read the sector per view (6,745,950 rows in 1,220 calls); the queue listing re-read earlier pages (924,232 in 79 calls) | Both rewritten as bounded index seeks, checked equal to the old queries; `d1-usage.yml` prints D1's own rows read and written by day, hour and query (#54) |

## G. Tests, docs and config truth

| id | sev | status | where | finding | done |
|---|---|---|---|---|---|
| G-01 | MEDIUM | CONFIRMED | `docs/SPEC.md:288` | Claims Today reads the snapshot (F-11) | Open with F-11 |
| G-05, G-06 | MEDIUM | CONFIRMED | `web/worker`, `statements.test.ts` | The Worker has no tests; the statements test missed every class above | statements tests added for F-01, F-04, F-05, F-07; Worker tests open |
| G-02..G-04 | LOW | CONFIRMED | `docs/SETUP.md`, settings, scripts | SETUP describes a BSE self-hosted setup and "820 tests"; BACKFILL_START default 2025-01-01 against a live start of 2026-04-19; a dead script for a reverted rule | Fixed 22 Oct: SETUP on NSE and GitHub's runners, test counts, missing commands, D1 limits; `BACKFILL_START` defaults to 2026-04-19 (code and SPEC); the dead script removed. The web's `HISTORY_START` stays 2025-01-01: live cards go back before 19 Apr (annual reports, call seeds), and the "all" feed starts there |
