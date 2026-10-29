
| 22 Oct 15:30 | Hourly audit 9 | 7 new cards: 3 wrong (two call tables: basis label, older quarter; Havells OCR 9->6) / 3 minor; E11 in #71; d1-usage dispatched |
| 22 Oct 15:35 | #72 merged | Card refresh removes a call table of a quarter the call does not discuss (CI green); refresh-card-blocks queued behind run 23 |
| 22 Oct 16:01 | Visit | Health OK (last run OK, one running; queue 1000 pending / 57 failed); refresh run 24 (#72) in progress; work queue all ticked, daily audit next |
| 22 Oct 16:35 | Hourly audit 10 | Sapphire WRONG (profit turn on a loss) -> direction check for profit/loss turns (on/off: 1 of 1,094 changes); held dry run 177 kept, 0 releasable; Gemini packed model at daily quota, lighter model serving |
| 22 Oct 16:35 | Visit | Health OK (run in progress, last PARTIAL: history backlog); #73 merged; refresh run 24 done, Nippon and Beta call cards no longer show Q1 tables (E11 live) |
| 22 Oct 17:06 | Visit | Health OK (16:09 run PARTIAL on the history backlog, 16:53 running; queue 1,000 / 57 failed); work queue ticked |
| 22 Oct 17:20 | Hourly audit 11 | 16 new cards, 8 reviewed: 1 right / 5 minor / 2 wrong (E13: press-release figures vs statutory priors, open); prune on Swiggy dropped a true point kept elsewhere |
| 22 Oct 17:41 | Visit (last of the day) | Health OK (17:38 run going, earlier PARTIAL on the history backlog; queue 1,000 / 56 failed); day's docs merged to main; evening report sent; half-hour visits end |
| 22 Oct 18:20 | Hourly audit 12 (last) | 13 new cards, 5 reviewed: 1/2/2 (Cyient E13, CIE E14 new); prunes 2 of 2 dropped true points; d1-usage dispatched; hourly routine disabled |
| 22 Oct 20:15 | Owner session | #75 open (event-type definitions, deals-sync, probe: insider trades via corporates-pit-gg per the owner's tracker); Siemens FY26 is an 18-month year its own XBRL dates as 12 (fix tomorrow); hourly checks scheduled 23 Oct 10:07-18:07 IST (trig_01HBPHhE3BYZeXc6TDZkmJkq) |
| 22 Oct 23:55 | Owner session | Step 1 of the held-card plan (F98): unit fixer keeps 33/33 right stored fixes, blocks 9/12 wrong; change fixer leaves a printed %; release-reviewed built, plans a (100) and b (64 of 108) ready for a dry run |
| 23 Oct 00:40 | Owner session | Held-card plan: 133 cards released (82 as they stand, 51 with named points off; 30 kept, quarter has a card); step 2 fix 1 (F99, other groupings): 21 false holds freed, 0 true, fakes 70->71/1,673, blind sample 68/70 |
| 23 Oct 01:10 | Owner session | Step 2 fixes 2-3 (F100 quote sums: 17 freed, 0 true, 0 of 3,632 fakes, sample 125/127; F101 PCT impacts, discontinued PAT, exceptional quarters: 9 freed, all false); 5 hourly check-ins scheduled 01:25-05:25 IST |
| 23 Oct 04:35 | Hourly checks 1-4 (worker restarted; 2-4 arrived together) | Pipeline healthy on #79 code. Step 2: F102 (OCR letters as digits: 8 false holds freed, 1 true whose meaning is wrong, 0 fakes; garbled text not held on XBRL-backed cards: 15 stored, all false); F103 code mistakes (owners' profit > profit, lender EBITDA, face value as deal price). Blind OCR sample running |
| 23 Oct 04:50 | Hourly check 4 | OCR-letters reading failed its blind sample (33 of 70 wrong) and was removed from #80 before merge; #80 keeps the XBRL-backed garbled exemption and F103 |
| 23 Oct 05:25 | Hourly check 5 (last) | Wrap-up: #77-#80 merged overnight (F98-F103); 133 cards released; OCR-letters reading rejected on its blind sample; the 23 Oct 10:07 hourly audit takes over |
| 23 Oct 10:30 | Hourly check 1 + daily audit 1 | Health OK (runs OK, queue 1,000/57 failed). Overnight: market-data and nightly failed on deals-sync (its events written under 'deals', the M&A list already there) and the nightly's annual-xbrl-catchup skipped itself (its own timeout wrapper counted as another run): both fixed with tests. Event types since #75: 21 cards, no CORPORATE_ACTION, 1 OTHER (an MoU). 10 cards in blind review |
| 23 Oct 11:40 | Hourly check 2 | Batch C 6 cards: 3 right / 2 minor / 1 wrong (MCLOUD press-release duplicate of an order memory had merged); day 16 cards, 2 wrong. Built F104: insider-sync (NSE PIT filings + XBRL, nightly), deals-backfill, maintenance fill-trades (180 days) |
| 23 Oct 12:45 | Hourly check 3 + daily audit 2 | Health OK; F104 merged (#83). Batch D 6 cards: 3 right / 3 minor / 0 wrong; day 22 cards, 2 wrong (9%). F105: order repeats are duplicates (census: 18 of 18 true repeats), case_stage negations (8 of 109 stored blocks change, all toward the filing) |
| 23 Oct 13:45 | Hourly check 4 | Health OK; #84 merged, refresh-card-blocks dispatched. Batch E 3 cards: 2 right / 1 wrong (Godrej deck: Total Income as revenue); day 25 cards, 3 wrong (12%). F106: memory refuses a call figure on another definition (census 91 of 15,621), named-year order terms |
| 23 Oct 14:30 | Hourly check 5 + daily audit 3 | Health OK; #85 merged. Batch F 14 cards: 6 right / 7 minor / 1 wrong (Shree Cement results release typed OTHER); day 39 cards, 4 wrong (10%). Open: results releases typed OTHER (2 today), SWSOLAR call EBITDA YoY against a tiny memory base |
| 23 Oct 15:40 | Hourly check 6 | Health: 13:49 run PARTIAL (1 failed filing, failed 58). Batch G 5 cards: 1 right / 2 minor / 2 wrong (Atul results outcome typed CORPORATE_ACTION; CSB call cost of deposits from the borrowings column); day 44 cards, 6 wrong (14%). F107: a covering letter that submits the results makes the results filing (on/off 4 of 308, blind 5 of 5 right) |
| 23 Oct 16:45 | Hourly check 7 + daily audit 4 (day summary) | Batch H 16 cards: 6 right / 7 minor / 3 wrong. Day: 60 cards, 43% right, 15% WRONG (22 Oct 20%). fill-trades dispatched 16:08 (run 39940575235). Critic 1 of 9 points right on 3 overlapping cards |
| 23 Oct 17:30 | Hourly check 8 | fill-trades running (insider trades step since 16:24 IST; AI pipeline paused as designed). Batch I 3 cards: 1 right / 1 minor / 1 wrong (PNB call results block on another series; "7-" headline after a figure was cut). Day 63 cards, 10 wrong (16%) |
| 23 Oct 20:50 | fill-trades check-in | Run 39940575235 succeeded 16:08-19:35 IST: insider trades 3,947 filed (233 companies, 1,913 of 2,569 filings read), deals 7,264 filed (936 companies, 27 Apr-21 Aug); both stopped at their time budget, 0 errors; AI pipeline resumed 19:35. Remainder in actions-pending |
| 24 Oct 10:45 | Daily audit 1 | Runs OK/PARTIAL (failed 62). 15 cards: 6 right / 5 minor / 4 wrong. export-held 124 held; sample 5: 2 releasable, 9 of 11 hold reasons false. F108: broken text after a removed figure; promised transcript is call logistics (on/off 2 of 516, both audio links). export-critic dispatched |
| 24 Oct 11:15 | Daily audit 1 (fixes) | #91 merged (F108). F109: EBITDA told two ways shows no change; a broader rule was rejected after a blind check (10 of 10 changes right), narrowed to 3 cards of 489 |
| 24 Oct 13:30 | Daily audit 2 | 20 cards: 6 right / 9 minor / 5 wrong (review queue 5: 1 right, 3 minor, 1 wrong). Critic scored: 2 of 23 flags true, stays shadow. F110: a filing read after its repeat is the duplicate (on/off 17 of 892 pairs, all byte-identical) |
| 24 Oct 14:50 | Daily audit 3 | 20 cards: 10 right / 7 minor / 3 wrong (day 55: 22/21/12). #93 merged (F110). F111: rating before from the same agency and scale (on/off 9 of 21 cross-agency comparisons removed, none wrong) |
| 24 Oct 14:20 | Daily audit 3 (ship) | #94 merged (F111); maintenance.yml refresh-card-blocks dispatched on main so stored rating cards drop cross-agency comparisons |
| 24 Oct 16:30 | Daily audit 4 + day summary | 10 cards: 3 right / 4 minor / 3 wrong. Day: 65 cards, 38% right, 23% WRONG (bar 95%). F111 refresh confirmed (Muthoot shows no notch change). Summary in docs/audit/live/2026-10-24-audit.md |
| 24 Oct 16:50 | Handover | docs/HANDOVER.md written for the owner's account switch (state, the two main tasks, routine to recreate with its prompt, open classes, all pending). Audit tools copied to pipeline/scripts/daily_audit/. CLAUDE.md, PLAN, SETUP point to it |
| 24 Oct 19:30 | Survey fixes (new account, branch claude/gracious-goodall-jn9buu) | Code survey of the whole repo; fixes F112-F114 (AI layer checks, lost work and memory, site and schedules) with tests: 966 pipeline (6 skip), 55 web. Migration 0014 applies on deploy |
| 24 Oct 21:45 | Owner session | Branch claude/gracious-goodall-jn9buu confirmed by the owner (exports go there); public cards keep their check details; Workers Paid bought for one month: D1_PLAN switch (F115), renew or set D1_PLAN=free before ~21 Nov; audit rates pooled with 95% intervals (rates.py): 21-24 Oct WRONG 22% (17%-28%) |
| 24 Oct 22:30 | Owner decisions | D41 shadow critic off; D42 go-live bar = WRONG on the checked face <= 5% pooled (interval top), "Our reading" behind a tap, pruned points kept behind the tap (F116) |
| 24 Oct 22:30 | Routine | Daily card audit recreated on the new account (trig_01JtXb9RSm63zmvoar8VyXsx, 10:07/12:07/14:07/16:07 IST, prompt in HANDOVER §3); "Our reading" kept open (owner); #97 to merge when green |
| 24 Oct 23:05 | Owner session | F117: backfill filings before 1 Aug 2026 go into memory only (no card, slimmer prompt; BACKFILL_CARDS_FROM); live and recent filings unchanged |
| 24 Oct 23:20 | Owner correction | F117 memory-only backfill switched off by default (owner: "let current flow remains"); filings it read in the meantime requeued for cards |
| 24 Oct 23:55 | Code audit | Six independent reviewers over main; report docs/audit/code-audit-2026-10-24.md (accuracy A1-A14, quota/lost work R1-R12, site S1-S6, flow verdicts); nothing changed, fixes wait for the owner |
| 25 Oct 00:17 | Merge #100 | F118 prompt cleanup, F119-F121 richer results cards (RESULTS_FACTS / RESULTS_RICH on; a repository variable set to 0 turns either off), D43 richness in the daily audit; on/off over 25 stored results cards reviewed by 3 blind agents (105 right, 5 wrong, all fixed) |
| 25 Oct 00:17 | Sampling re-run (owner's go) | maintenance requeue-failed --ids for 12 filings: Apollo Micro Systems (results, call, capex, fundraise), Shakti Pumps (results, call, M&A, order), BlueStone (results, NCD, monthly, penalty); old cards saved in docs/audit/sampling-2026-10-24/before.json; queued pipeline run 207 (pre-merge code) cancelled so the re-runs use the merged code |
| 25 Oct 02:20 | Sampling and trial reviewed | Re-run of 12 filings: 5 better, 1 same, 3 worse, 1 wrong drop (Apollo warrant allotment, open); model trial: Gemma rate-limited for cards, Gemma 26B on the Gemini key fine for level 1, Nemotron thinking off 2 of 5 WRONG -> spare (owner); #101 merged |
| 25 Oct 03:10 | DeepSeek drain reopened (owner) | `pipeline/config/drain_until` 2026-10-28T00:00 UTC: runs pass the prepaid key, prefer deepseek-flash, 8 workers; spending stops at the prepaid balance; `providers-check` now prints the balance. Its cards were 11 of 34 WRONG on 21-23 Oct (not significantly worse than Gemini), so the daily audit watches its share |
| 25 Oct 04:30 | Wrong-card trace and checks A/B (owner: A and B yes; unverified points parked; no DeepSeek top-up; owner: one case proves nothing) | 48 WRONG cards traced (code 40, writer 36, input 12, memory 7 of 96 points); both checks judged on every stored card against pass marks set first and rejected (A 66% of 90 removals wrong, mark 80%; B 9% of 88 flags, mark 85%); a crash on a half-year-derived quarter fixed; Z.AI GLM flash models answer on both keys (missing only from Z.AI's model list); DeepSeek balance $7.54 |
| 25 Oct 09:00 | Second keys (owner) | Gemini, Groq, NVIDIA, Z.AI already rotate (since 22 Oct); Mistral's second key wired (F125), takes effect once the MISTRAL_API_KEY_2 repository secret is set; run 223: 3 Mistral 429s, none from either Gemini key |
| 25 Oct | Filing texts kept 6 months (owner, F147) | Texts live in two places: the GitHub cache `data/text_cache` (last 8 days, fast) and R2 `text/<news_id>.json.gz` in bucket `bse-intelligence` (written with every text, read when the local copy is missing). R2 deletes each object 180 days after it is written by the lifecycle rule `text-180d`, set by `deploy-web.yml` (look for the `::warning::` in that step if the token cannot edit R2; check with `npx wrangler r2 bucket lifecycle list bse-intelligence`). XBRL files stay local. |
| 25 Oct 15:05 UTC | DeepSeek off on regular jobs (owner: "stop DeepSeek from regular job, because we are going to need it for our next phase") | `pipeline/config/drain_until` removed, so the main run and the quick run no longer pass the DeepSeek key or use 8 workers (the drain was set to 28 Oct); `seed-calls.yml` no longer passes it either. The key stays in the repository secrets for the next phase; `providers-check.yml` still makes its one tiny balance check on demand. To use it again: restore `drain_until` with a UTC time ahead, or put the secret back in `seed-calls.yml` |
| 25 Oct 17:05 UTC | EPS across splits and bonuses switched on (F153, live-bug fix, owner's rule for fixes of live wrong cards) | `EPS_SHARE_ADJUST` defaults to 1 in pipeline.yml, pipeline-today.yml and maintenance.yml (repository variable EPS_SHARE_ADJUST=0 turns it off). Scan: 29 published results cards stated an EPS change across a recorded split/bonus (Kotak -74.7% vs +26.4% adjusted, Nestle -25.9% vs +48.1%, Pidilite, Adani Power, Metropolis, Bajaj Finance); stored tables are rebuilt by maintenance refresh-card-blocks |

## 27 Oct 2026, ~08:30 IST: eight card switches on (owner)
Owner: "Whatever can be switch ON, do it so at least we can see improvements in today's card." Set on in `pipeline.yml`
(a repository variable set to 0 turns one off): CARD_GROUND_ALL_FIELDS, CARD_GROUNDED_FIGURES, CARD_ONE_BASIS,
CARD_SAME_DEFINITION, CARD_YOY_RESTATED, CARD_FOOTER_PLAUSIBLE, QUOTE_EXACT_NUMBERS, CARD_EPS_FOLLOWS_PROFIT. Chosen because the
full suite with all eight on changes no other test (checked switch by switch). Left off: CARD_CONSOLIDATED_ONLY (the XBRL block
left the prompt in a test), CARD_EBITDA_PROFIT_V2, CARD_TWO_PARTS, CARD_GUIDANCE_DATED (they change other behaviour; their on/off
first), every MEMORY_* switch (they write stored memory). Not measured on live cards before switching on: the audit of
27 Oct's cards against the 26 Oct benchmark (18.8% WRONG) is the measurement, and with eight at once it cannot say which
switch helped.

## Runs tracker (owner, 27 Oct 2026: "I don't see you are tracking those")
Every maintenance run stays here until its result is read and acted on; the 15-minute tick updates it. Read 27 Oct 08:17 IST.

| Run | Command | Result | Next |
|---|---|---|---|
| 40431994775 | restated-pdf-trial, 60 companies | 28 restated figures found, 0 stored; many are digit or unit slips (CHENNPETRO 19,438 -> 19,43,839; BATAINDIA 788.21 -> 0.79; CIPLA PAT 1,305 -> 305) | Reader bug: fix in code, re-run the trial. Nothing stored, nothing live |
| 40429782319 | restated-pdf-trial, 12 companies | 360ONE 3, TITAN 4 (before the PR 170 fix) | 360ONE: check against its own-period files |
| 40405063481 | screener-referee | 6,827 pairs: ours = NSE's file 3,675, screener = file 22, neither 7, no file 226; 2,897 not run (5 h budget) | Run again to finish the 2,897 |
| 40378668456 | tijori-referee | 838 pairs: ours = file 758, Tijori = file 17, no file 63 | Look at the 17 |
| 40371891447 | screener-explain | 6,844 rows: 1,492 unexplained | Input of pdf-referee "explained" |
| 40381457050 / 40383247868 | memory-gaps / memory-gaps-fill | 2,628 company-quarters missing; the fill tried 373 companies and filled only 79 | Find why so few fill |
| 40432958750 | seed-memory next pass | 155 companies, 0 failures; the universe is seeded | Done |
| 40388620844 | seed-memory, whole universe | Failed: 2 of 12 shards lost their runner (GitHub side) | Covered by 40432958750 |
| 40429585773 | bse-results-test | 16 of 16 calls OK; BSE = NSE 7 of 7 | Done |
| 40429581504 (+ 40387691940, 40402679817, 40410658355) | call-memory | All docs read in the end; 31 of 36 points kept on the last 3; the earlier fails were provider limits | Score and second blind sample |
| 40388046768 | pdf-referee-ensemble, 20 pairs | 1 matched ours, 24 unsure | Trial only |
| 40387696323 | pdf-referee | Failed: runner lost (GitHub side), log gone | Same step now in 40393302149 |
| 40414799620 | pdf-referee-ensemble hardset | Done. 340 key figures. Right / wrong / no answer: docling 54/0/286, native (ours) 65/10/265, tatr 36/5, marker 44/7, tabula 40/9, mineru 60/18, paddle 39/24, rapidtable 26/19, surya 17/16, camelot 12/8, pdfplumber 12/7. Ensemble settled 14, all right; 130 disagreements | No reader answers most figures; docling is never wrong but answers 16%. Decide the reader set from this |
| 40407491267 | release-check | Stopped by GitHub at 6 h (08:49 IST), nothing saved. It hung on our own site's API ("Server disconnected without sending a response" for nse-106605841, nse-106606044, memory/544570), not on NSE | Make it save as it goes, run in parts |
| 40393302149 | pdf-referee "explained" | Done (5 h budget). 1,982 open pairs: PDF = ours 130, PDF = screener 9, = NSE file 1, none 9, unsure 151, unreadable 178, not run 1,504 | Run the rest after the PDF date/page fix (F215) and the file cap |
| not run | memory-gaps-fill-bse dry run, text-backfill | Never ran (skipped in the chain) | Dispatch |
| not found | seed signs APARINDS Q1FY27, PVRINOX Q1FY25, GLENMARK Q4FY26 | No run re-read them | seed-memory with ids |

## 27 Oct 2026, ~09:00 IST: reviewed builds merged and on (owner: "Once reviewed, merge and switch them on too")
Merged after independent review: F209 (row-name map, a pure refactor; its LINE_MAP switch does nothing yet), F210 (company-page
financials on screener's formulas: on through `VITE_SCREENER_LINES` in deploy-web.yml), F211 (EPS share-count check, memory only:
on), F208 (Wipro: an AI-read standalone EPS stored as consolidated is refused; stored EPS changes the profit does not carry are
not kept: on). EPS is never shown, so F208 and F211 change memory only. The suite with every live switch on together: 1,864 passed.
Still in review: F205 (watch verdicts), F206 (one line a results row), F212 (restated reader).
- ~09:10 IST: F206 merged and on (`CARD_RESULTS_ONE_LINE`), F212 merged (no switch: the restated reader only stores fewer
  figures; MEMORY_RESTATED stays off). Known cost of F206: when this quarter's EBITDA is only the release's and the comparatives
  are the file's, the EBITDA change is left off even where it would have been right (Shree Cement and Crompton tests under the
  switch): a missing change, never a wrong one. All other tests unchanged with every live switch on.
- File cap (owner rule, 100 NSE/BSE files a run): run 40441227348 (memory-gaps-fill over every company) cancelled before it
  passed the cap; the cap is being built (F213). No NSE/BSE maintenance run is dispatched until it is in.

## 27 Oct 2026, 14:02-14:22 IST: BSE fill, 100-file test (owner: one task at a time, benchmark)

Run 40474143469 (`memory-gaps-fill-bse`, dry run, `file_cap` 100): BSE answered every call through the ported adapter,
100 files downloaded and kept, none refused. 8 companies, 53 quarters, 1,417 figures would be filled. Against screener.in,
then the companies' own statements: 9 of 9 differences settled, BSE right in all 9. Report:
`docs/bench/bse-fill-2026-10-27.md`. The full run waits for the owner. (Run 40471967773 before it stopped at the start: the
step did not install `requests`; fixed in #179.)

## 29 Oct 2026: PDF shadow check built (TODO 121), off until the owner switches it on

`pdf-shadow.yml` reads the PDF of each results card filed in the last 3 hours with the numbers-first reader and logs, per
headline figure, agrees / disagrees / unknown against the card (R2 `meta/pdf-shadow/<day>.csv`, artifact `pdf-shadow`). Read only:
no card, memory or site change, no AI. **To switch it on (owner):** set the repository variable `PDF_SHADOW` to `on`
(Settings > Secrets and variables > Actions > Variables); the schedule then runs hourly at :41. Off: remove the variable or set it
to anything else. A manual dispatch (`limit`, `since_hours`) runs whatever the variable says. The first run measures seconds a PDF
on the runner (column `pdf_seconds`); the disagreements are set beside the daily audit after a few days. Assumption: a card that
does not store its basis is read on CONSOLIDATED first, then STANDALONE (the reason says so).
