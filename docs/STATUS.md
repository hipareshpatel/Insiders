# Status: the one current page

Read this first. It replaces the "pending", "status" and "next" parts of `PLAN.md`, `HANDOVER.md`, `TODO.md`, `TASKS.md`
and `docs/audit/actions-pending.md`. Those files stay as history; do not work from their lists. Keep this page current:
when something changes, change it here, in plain English, with the date and time in IST.

Last updated: 29 Oct 2026, 18:37 IST.

## 0. How the lead session works (owner, 27 Oct 2026, ~22:15 IST)

Freedom inside a fence, with a short daily message to the owner.
- **Without asking:** code fixes with a test and an independent blind review (a separate subagent, not the smallest
  model), merging once CI is green, read-only jobs, the BSE fill batches (stop at once on any refusal), keeping this page
  current.
- **Ask the owner first:** anything that costs money, keys, deleting data, account or repository settings, switching on a
  switch that changes what cards say before it is measured, changing the go-live bar, big design choices.
- **Data writes the lead may do without asking (owner, 28 Oct 2026, ~06:15 IST), only once the undo is merged**
  (a saved copy of exactly what a job changes, read back before any write, and a `restore` command):
  - A. Fixing a figure proven wrong in memory: fix the class in code with a test, re-read only the affected filings,
    at most 50 filings a run, only when two sources agree on the new figure, the list of changes put on this page.
  - B. Refreshing the stored cards: only after 30 changed cards pass an independent blind check with no rise in WRONG.
  - C. Switching on a switch that changes what cards say: only after the on/off check over stored cards and a blind
    sample show no rise in WRONG; otherwise ask. (Repository variables are the owner's; the lead can only change
    `pipeline/config/switches.toml` in a PR, and a repository variable of the same name still wins over it.)
  - Silence is never a yes for a data write that falls outside A-C.
- **Stop at once and tell the owner:** any NSE or BSE refusal; a measured rise in WRONG; anything shipped that breaks a
  run.
- **Never:** get around a site's blocks, ignore robots.txt (never screener `/company/source/` pages), hand-edit stored
  data, print keys, put AI model names in commits.
- **The owner's message:** short, plain English, IST: what changed, the WRONG rate with its range, what is next, what
  waits for the owner.
- Routine: "Overnight work loop" (`trig_01DZ25syuiJGt8HTbMxedqNP`), hourly 23:07-06:07 IST on 27-28 Oct, in the lead
  session; the 06:07 run sends the morning message and switches it off.

## 1. What runs

| What | How | Since |
|---|---|---|
| Cards | One run, `pipeline.yml`, scheduled every 15 minutes; GitHub starts it about every 35-45 minutes. Today's new filings first, then the older work (the live window's earlier days, catch-ups, memory sweeps, backfill) in slices of about 3 minutes (10 for the backfill), and today's new filings are looked for again after each slice | 27 Oct, PR #190 (the quick run `pipeline-today.yml` is gone) |
| Switches | One list, `pipeline/config/switches.toml`, for every job. A repository variable of the same name wins over the file in every job (`0` turns one off). CI runs the tests with the switches off and with the file's switches on | 27 Oct, PR #190 |
| Site | https://insiders.reply-bd3.workers.dev; `deploy-web.yml` deploys every merge to `main` | 20 Oct |
| Maintenance | `maintenance.yml`, started by hand, one command a run (no AI) | |
| Daily card audit routine | **Off** since 24 Oct night (trigger `trig_01JtXb9RSm63zmvoar8VyXsx`, disabled). The 26 and 27 Oct audits were done by hand; an overnight work loop runs 27-28 Oct (section 0) | owner to decide (section 5) |

Switches on (the file): EPS_SHARE_ADJUST, CARD_GROUND_ALL_FIELDS, CARD_GROUNDED_FIGURES, CARD_ONE_BASIS,
CARD_SAME_DEFINITION, CARD_YOY_RESTATED, CARD_FOOTER_PLAUSIBLE, QUOTE_EXACT_NUMBERS, CARD_EPS_FOLLOWS_PROFIT,
EPS_BASE_CHECK, EPS_SHARE_COUNT_CHECK, CARD_RESULTS_ONE_LINE, CARD_WATCH_VERDICT. On by code default:
MEMORY_STANDALONE_ONLY, RESULTS_FACTS, RESULTS_RICH. On in maintenance only: PDF_DATES_2DIGIT, PDF_PAGE_RANK,
PDF_ROW_FIXES, BSE_FILL_PRE_NSE. Everything else is off: CARD_EBITDA_PROFIT_V2, CARD_TWO_PARTS, CARD_CONSOLIDATED_ONLY,
CARD_GUIDANCE_DATED, CARD_EPS_WHOLE, MEMORY_YEAR_CHECK, MEMORY_RESTATED, MEMORY_SCREENER, MEMORY_CALL_V2,
XBRL_FILER_CHECKS, LINE_MAP, CRITIC. The 13 were switched on on 27 Oct at the owner's word ("Whatever can be switch
ON"); their release check never finished (run 40407491267 stopped at 6 hours with nothing saved), so the measurement is
the blind audit in section 3.

### Switches: what each off one does, and the owner's call (30 Oct 2026, 00:20 IST)

A switch turns a rule that is already on `main` on or off, without new code. Code goes to `main` only after the tests, a
blind review and a measurement; a switch then decides whether the rule acts on live cards. The owner decides each line.

| Switch (off today) | What it does, in one line | Lead's advice | Owner |
|---|---|---|---|
| MEMORY_CALL_V2 | Each call transcript and deck gets its own memory reading (Gemini key 3); its points are checked by code and kept | **On** (owner, 30 Oct 2026 ~06:45 IST) | Yes |
| MEMORY_YEAR_CHECK | A year or half-year figure its own quarters do not add up to is not used on a card | Measure on stored memory, then on | Yes / No / Later |
| XBRL_FILER_CHECKS | Where the company's own file contradicts itself, the figure is held, not kept | Measure on stored memory, then on | Yes / No / Later |
| MEMORY_RESTATED | A restated comparative is named as such on the card ("restated in Q2FY27, first filed X") | Later, with the card work | Yes / No / Later |
| CARD_CONSOLIDATED_ONLY | A consolidated company's card states consolidated figures only | Decide in the card work (the fact-sheet flow covers it) | **On** (owner, 30 Oct 2026, ~00:40 IST) |
| CARD_EBITDA_PROFIT_V2 | The company's own EBITDA first, ours below as "calculated"; one profit line | Decide in the card work | **On** (owner, 30 Oct 2026, ~00:40 IST) |
| CARD_TWO_PARTS | The card in two parts: "from the filing (checked)" and "our reading (AI)" | Decide in the card work | **On** (owner, 30 Oct 2026, ~00:40 IST) |
| CARD_GUIDANCE_DATED | A guidance verdict (met / missed) only from a dated target due this period | Decide in the card work | **On** (owner, 30 Oct 2026, ~00:40 IST) |
| CARD_EPS_WHOLE | EPS line on the whole company (EPS is not shown on cards, so memory only) | Later | Yes / No / Later |
| LINE_MAP | Row names mapped by one table for changes that would alter output | Keep off | Yes / No / Later |
| SLIP_CHECK_NUMFIRST, PDF_SHADOW | The new PDF reader in the unit check; its shadow run | Off until the PDF work resumes | Yes / No / Later |
| MEMORY_SCREENER | Screener's figures read as memory | Keep off: screener is for checking only | Yes / No / Later |
| CRITIC | A second AI reviewing each card | Keep off (D41) | Yes / No / Later |

No switch, on as soon as merged (30 Oct): the exchange file's figure outranks a later AI reading (TODO 118 B); a footer
figure 10x off its comparative is not shown (TODO 127); each filing's own results XBRL kept in R2.

## 2. The go-live bar (one definition)

WRONG on the checked face at or below 5% of published cards, read pooled over days, with the top of the 95% interval at
or below 5% (owner, 24 Oct, D42; `pipeline/scripts/daily_audit/rates.py`). "95% right", "15% WRONG" and the other bars
in older files are history.

| Measured | Cards | WRONG | 95% interval |
|---|---|---|---|
| 21-24 Oct, pooled | 218 | 22% | 17-28% |
| Cards filed 26 Oct (audited 27 Oct, `docs/audit/live/2026-10-27-audit.md`) | 154 | 18.8% | 13.4-25.7% |
| Cards from the single run with the 13 switches | not yet | | |

Not met. The rate has stayed between 15% and 23% for a week while about 120 fixes shipped (F104-F222).

## 3. Open work, in order

**Results page as a KPI report from the saved statements, 30 Oct 2026 ~22:00 IST (owner: "only the saved statements, no card"; "consolidated over standalone"; "no company repeated"; "growth filters and sorting, redesign the entire page as a KPI report").** Built: `results_table.py` (`results-table`) turns each company's `statements` (the company page's Results tab source) into one row per company and quarter in the D1 table `results_kpi` (revenue, EBITDA, PAT, margin and their changes); the Worker's `/api/results-kpi` filters and sorts them in the database; the page shows one row per company for a quarter with a summary strip. Each pipeline run refreshes the live window's companies; the first full build is Maintenance > results-table (`--all`), run after the deploy has applied migration 0015. Also built (PR #268, owner 30 Oct 2026 "update it every Sunday"): `sync-indices` (workflow `sync-indices.yml`, Sundays 09:00 IST) keeps NSE's broad index members in `index_members`; the page's index filter, sector and industry filters and the by-group medians wait on the owner's approval of the design. Not yet measured: how many companies each quarter has (read the first full build). Banks and insurers have no row. The page no longer reads a card.

**Owner's decisions, 30 Oct 2026 ~14:30 IST** (TODO 101, 128, 136, 140, 141): (1) call memory prompt v2: read ~150 points of new
live calls apart, blind-judge, switch only at or under 2% wrong; (2) a late file's results card keeps no table until the file
(option A); (3) empty balance-sheet entries removed by code (backup, 50 a run, dry run first); (4) the card design is already
given (TODO 128 example, the Gemini APAR write-up, TODO 136): build from it, ask nothing more.

**Owner's decisions, 30 Oct 2026 ~17:25-19:20 IST:** (1) remove AI balance-sheet snapshots the exchange file covers: Yes
(TODO 141); (2) the chart-label rule for call memory: "Do it" (TODO 144); (3) NUMFIRST_STOP_EARLY on: Yes (PR #261, live
~19:26 IST). The owner offered a second Mistral key; lead: not needed, Mistral's limits are per organisation (TODO 145).

**Open work, in order (31 Oct 2026, 05:10 IST; the one list, kept current after every step). From 23:00 IST the session on branch `ccr-244dd8fc-rq75sb` leads (owner: "continue all pending tasks one by one").**
| # | Item | State | Next |
|---|---|---|---|
| 1 | Rating snapshots the 30 Oct empty-snapshot clean-up removed (found by the review of PR #256) | **Putting back**: 407 in 256 companies from the runs' backups (`statements-backfill --put-back-ratings`, 50 a run, backed up); **Done 31 Oct ~00:20 IST: 407 put back in 256 companies** (runs 1-6: 63, 82, 97, 75, 84, 6; run 6 41099900518, backup backup/statements-backfill-20261030T181741Z/); 115 file-covered AI balance snapshots dropped on the way. Checked on 570004's live company API: the ICRA BB+ (Negative) snapshot is back | Next: the file-covered drop over all companies, dry run with the count first (TODO 141), in the same statements-backfill as the Q1FY24 fill and the Borrowings fix (one dry run, one count) |
| 2 | 20 live results cards on the fact sheet (CARD_FACT_SHEET, on 16:00 IST) | Scheduled 31 Oct ~07:18 IST | Blind-score; off again if worse |
| 3 | NUMFIRST_STOP_EARLY (on ~19:26 IST) | Live | 31 Oct ~11:30 IST: the first 20 live results filings it read, revenue and total income against the file; any wrong, off (repository variable = 0) |
| 4 | API OCR readers on the hard set (Mistral OCR, NVIDIA nemotron-parse 1 and 2; #257, #258) | Scored (PDF session): nemotron-parse 185 right / 1 wrong / 154 none of 340 after its guards (best single reader; numbers-first then nemotron 294/0/46, in-sample); out of sample (run 41077643109) 103 / 5 / 444 of 552. Mistral OCR answered nothing (429 on the free plan), nemotron-parse-2.0 502, nemotron-3.5-parse 404 | The PDF session decides whether nemotron-parse joins a live path (off, measured, owner) |
| 5 | Card model grid (TODO 142) | Trial route has MiniMax M3.1 Flash (NVIDIA), Qwen 3.8 27B and gpt-oss-120b (Groq), each answered a tiny request (run 41062958287); Kimi K2.6 404, Nemotron 3 Ultra out (53-58% WRONG measured) | **Measured 30 Oct 20:41-22:31 IST: no new model can write a card on its free tier.** Eight fact-sheet-ab runs on the same 10 filings made 0 cards: MiniMax M3.1 Flash and Mistral Large 4 (NVIDIA) 300 s timeouts, Nemotron 3.5 Super VL cut off at its token limit, Qwen 3.8 27B and gpt-oss-120b (Groq) over the per-minute token limit (the card prompt is larger than Groq's free minute). The grid goes on with today's writers only: prompt current vs strict x temperature (item 6 first) |
| 6 | Card text strictness (TODO 142, CARD_TEXT_SUPPORT, off) | In-sample 12 of 23 targeted WRONG dropped, 19 true items dropped too (2.7%). **Out of sample, 31 Oct (release-check text_support, run 41100996875): over 9,249 stored cards it would drop 4,922 items on 3,341 cards (36%)**: track_next 2,191, core_catalyst 1,264, why_it_matters 647, notable_changes 604, what_happened 126, key_numbers 90. Many drops are on ordinary words the filing does not use ("acceleration", "compared"), so it is far too strict as built | Stays off. Next: blind-judge the 60-item sample (artifact `release-check`, text_support-blind.json; the judges need the filings' stored text, R2 text/<news_id>.json.gz, a small export job), then narrow the word check to names, dates and counts |
| 7 | Chart-label rule for call memory (TODO 144, owner "Do it") | Built behind CALL_MEMORY_GEOMETRY (off). **Re-measured 31 Oct ~00:30 IST on a fresh blind-judged set** (the 30 Oct set was lost with that session's scratchpad; now kept in docs/bench/geometry/judged-2026-10-31/): v2's 293 deck points, 27 WRONG. Rules of 30 Oct: WRONG 23 of 27 dropped, RIGHT 25.2% dropped; rules of 31 Oct (units and filler never labels, prose left alone): WRONG 23 of 27, RIGHT 22.4%. Bar: all WRONG, RIGHT at most 3%: far off | **A tuning round with a held-out set (31 Oct ~01:00 IST): held-out 4 decks, WRONG 7 of 10 dropped, RIGHT 13.2% dropped** (tune decks 6.7%, so part overfit; branch geom-tune, not merged). Word positions alone cannot reach the bar: swapped pie labels and a figure of another measure look the same on the page as right points. **Owner's call:** (A) stop here, the switch stays off; (B) a vision step that reads the chart (cost: one AI call a chart slide); (C) change the call-memory prompt so it keeps no figure from a chart unless its label is printed beside it, then re-judge (lead: C first, it is free) |
| 8 | Call memory v2 prompt (TODO 101) | **Measured 31 Oct ~00:30 IST: 27 of 293 deck points WRONG (9.2%)** by three blind judges (ESAF 9 of 71, MTAR 7 of 33, Welspun 7 of 32, Thyrocare 3, GK Energy 1, four decks 0); nearly all a chart or pie figure paired with another bar, year or segment. The 30 Oct count (6 of 146) was a smaller sample. The owner's bar is 2%: not met, so the prompt is not switched | **Option C measured 31 Oct ~01:00 IST: no gain.** The v2 prompt plus a chart rule (v3, run 41103785967, same model and decks): 27 of 282 WRONG (9.6%). Found: every WRONG point of both sets is a quote assembled from words across a slide (v2 27 of 27, v3 25 of 27); 40% of RIGHT points are assembled too, so dropping them costs too much (docs/bench/geometry/judged-v3-2026-10-31/). **Owner's call:** (A) keep v2 off as now; (B) a vision read of the slide only for assembled slide quotes (about 40% of deck points; one free-tier call a slide); (D) a stronger model for decks (Gemini Flash's ~20 a day) |
| 9 | Press release into the results card and memory (TODO 135; owner Yes) | Built 30 Oct (PR #269), switch RESULTS_PRESS_RELEASE off | Measure on/off on live results filings, then the owner's switch |
| 10 | Deck and call cards lead with what changed (TODO 136; owner Yes) | Waits for call memory | The owner's 34 example cards are in docs/design/card-examples/ (never ask again) |
| 11 | Smaller: PBT definition for numbers-first (TODO 143, later: no live path uses it); stock-page items (Q1FY24 gap: fixed, PR #271; stale standalone and overdue guidance: audited on 20 live pages 31 Oct, docs/audit/stock-pages-2026-10-31.md, fixes B1 (overdue counted from the results due date), B3 (no deadline before the day it was said) and A2 (page basis) to build next (the helper stopped on its usage limit before any code); bank/insurer tables TODO 129); the 47 companies with no stored facts; XBRL extras' second group (done, PR #269); Borrowings read as 0 from annual-report balance sheets (TODO 129: fixed in PR #273, 187 pairs right, 0 broken); raw XBRL expiry check (TODO 139: built 30 Oct, Maintenance > xbrl-expiry-check, read only; first run to read) | Open | In turn |
| 12 | **REITs and InvITs on the Results page** (owner, 30 Oct 2026: "REITs need to check XBRL"). 3 of the 500 Nifty 500 members are REITs (Embassy Office Parks, Brookfield India, Bagmane Prime); the page shows 497 of 500 and says so | Not started. **Measured 30 Oct 2026 (the call is found):** NSE's own page loads REIT/InvIT results with `/api/corporates-financial-results?index=reitsinvits&period=Quarterly[&symbol=X]` (read from its script `corporate-filings.js`, function `loadFRInvitsreits`); the earlier tries (`reit`, `invit`, `reits`, `invitsreits`) failed because NSE answers any unknown index name with the same `no data found` (control: `index=zzzgarbage`). It returned 193 filings from 27 trusts (REITs and InvITs), Embassy 12, Brookfield 9, Bagmane 3, each with an `xbrl` file and an `ixbrl` page on nsearchives (Integrated Filing names, `consNoncons`, `periodEnded`, `typeOfSubmission` Original/Revised). One Embassy file read (Sep 2026, 392 KB, 306 numeric tags): the same Ind AS tags as companies (RevenueFromOperations, FinanceCosts, ProfitLossForPeriod, EPU) and values equal to Screener's (revenue 1,303 Cr, profit 831 Cr), plus REIT tags: NetDistributableCashFlows, DistributionPerUnit, NetAssetValuePerUnit, NetOperatingIncomeMargin, NetBorrowingsRatio, DebtEquityRatio, DebtServiceCoverageRatio. None of the three is in our companies table (the universe is NSE's equity list), and we had never called this index, so the XBRL exists and has not been downloaded. Screener (measured) links each quarter to a BSE announcement PDF, not XBRL | **Plan (owner agreed, 30 Oct 2026).** Practice measured or searched the same day: Screener.in (measured: pages for all three, filed under Realty > Real Estate Investment Trusts (REITs); the ordinary table of Sales, Operating Profit, OPM, Net Profit and EPS, Embassy to Sep 2026, Brookfield to Jun 2026, Bagmane three quarters; no distribution figures in its tables; a Raw PDF link per quarter). NSE's Nifty 500 list (measured 30 Oct 2026) holds all three. Industry practice (web search, no official SEBI text read): investors read net operating income, net distributable cash flow (NDCF), distribution per unit and NAV, not net profit; the 90% payout base is given as NDCF by some sources and taxable income by others (**assumption** until the regulation is read). **Step 1:** add the REITs and InvITs (27 trusts) to the universe, fetch them through `index=reitsinvits` and read their XBRL with the existing reader plus the REIT tags to the universe, revenue, operating profit and profit as Screener shows them, kind `reit` on the page (left out of EBITDA statistics like banks), then drop the "not covered yet" note. **Step 2:** NDCF, distribution per unit, NAV per unit and net borrowings ratio from the same file as their own columns. The first fetch of a new NSE path runs on 100 files (`file_cap` 100, files kept) |

**Summary for the owner, 30 Oct 2026, 07:00 IST.**
- Done: the live path saves every result by screener's rules (3); one results card a quarter (6); late exchange file fetched
  for PDF-only cards first (7); every filing of 28-30 Oct read, none waiting, none failed but one audio file (5); four card
  switches on (12); new PDF reader on for the unit-slip check (14); call memory on (10, owner 06:45 IST).
- Running: past statements into memory (2): 850 of ~1,900 companies, 40,221 entries, about 2 minutes a run of 50, ends
  about 07:45 IST. Then the re-read of the 223 recent results companies (4), runs of 50.
- Waiting for the owner: MEMORY_FILE_ONLY (1: memory's figures from the exchange file only; 28 tests feed AI figures on
  purpose and change); the PDF reader's speed gate (PR #232, being measured); the call-memory prompt and the Flash-Lite
  tests (10: lock the model, smaller parts, thinking; plan agreed in chat); the card's PBT is screener's (9, decided:
  the general rule, the ~20 exceptions stay).
- After memory: cards read their figures from memory (9, TODO 131); richer cards borrowing the good parts of the Gemini
  write-up (11, TODO 128); balance-sheet gaps (8, TODO 129); annual-report extras (15).

**Owner's list, night of 29-30 Oct 2026 (every instruction of the session, in the owner's order; state at 06:35 IST).**
The order: correct memory first, from the exchange's files by screener's rules; then cards read memory.
1. **Memory's financial figures from the exchange's XBRL only, by screener's rules, never from cards or AI readings.**
   Built: `MEMORY_FILE_ONLY` (dossier.STATEMENT_FIGURES from file/calc sources only), OFF until D20 (one card a quarter)
   no longer finds a quarter's card through the figures it left in memory (32 tests rely on that). Next: D20 from the
   timeline's own quarter, then the switch on (owner's word).
2. **The stock page's statements as screener shows them, row by row, for every past quarter and year.** Built (PR #224):
   `statements-backfill` turns the stored facts (raw/xbrl-facts/, no download) into `dossier["statements"]` by the
   screener_view recipes (quarters, years, balance sheets, cash flows, both bases; a unit-slipped quarter, or a year or
   quarter whose Net Profit is 1.5x off memory's profit on the same basis, left out); the stock page shows those tables.
   **Applying, 30 Oct from 05:30 IST:** runs of 50 (OPS), 250 companies done by 06:30 IST (12,138 entries; a handful left
   out by the profit check, e.g. MTNL Q2FY24: the stored file -7.93 Cr against memory's -793). Faster each round: 17 min a
   run, then 8.7 (8 reads at once, PR #227), 5.7 (24, PR #229), 4.9; writes 8 at once from PR #230. ~1,650 companies left.
3. **Every future result saved by screener's rules at filing time.** Live (PR #220, #222): the live path keeps each
   results file's statements, consolidated and standalone; the seed too (PR #224).
4. **The last 3 days' results from the exchange files, missing quarters into memory.** Next: `seed-memory` for the 223
   companies with results cards 27-29 Oct (scratchpad/cm2/recent_results_scrips.json), runs of 50; 42 of 143 recent filers
   had their latest quarter from the AI only (Coal India among them).
5. **Every results filing of the last 2 days processed?** **Yes (30 Oct, 06:10 IST):** of the filings of 28-30 Oct none is
   waiting and none failed except one audio-only ZIP (CNL, no text). failed-report now counts the last days' waiting
   filings by day and type (PR #228). The "1,000 pending" is the old history backlog, not recent filings.
6. **One results card a quarter; consolidated when it exists, else standalone.** Live (PR #220). A press release naming no
   quarter and a deck filed as results no longer take a second card (PR #224; 13 companies had two on 28-29 Oct).
7. **The late exchange file fetched for a card made from the PDF.** PR #224: the catch-up reads the PDF-only cards first.
8. **Balance-sheet and cash-flow rules too.** Rules exist for all three statements; where they still differ from screener
   (Borrowings 77%, Other liabilities 74%, no insurer balance sheet): TODO 129.
9. **Cards take their figures from memory (the fact sheet), the AI only the words.** Planned; after items 1-4. The card's
   PBT is screener's: the filed ProfitBeforeTax + the associates' and JVs' share + regulatory deferral + discontinued profit
   (docs/design/screener-row-rules.md; 2,302 PBT rows exact), read from memory's statements; the plain file PBT the card
   shows today is before the share (M&M Q1FY27 7,260.60 against the printed 7,628.09). The ~20 companies screener keeps the
   share out for (Reliance, Sun Pharma, L&T, DLF, BEL, some NBFCs) stay as they are (owner, 30 Oct 2026, ~02:50 IST: "Let
   those 20 companies stay as they are right now"): the general rule, no named list (docs/design/screener-associates-outside-pbt.md).
10. **Transcripts and presentations into memory on the third Gemini key (call-only).** Second blind check: FAIL, important
    recall 59/123 = 48%, wrong 3/120. Why (30 Oct): about 46 of the missed points the model never returned (risks, segment
    mix, margin drivers, demand outlook, one-offs), about 9 lost to a deck part that failed to read, at most 7 dropped by
    our checks. Key 3 serves more models than we used: the two Flash-Lite models (~500 a day each) joined the route (PR
    #227), so ~1,080 requests a day instead of ~80. A prompt that asks for every true point and names mix, policy backdrop
    and working capital (held, not merged): the same 10 documents re-read (run 40982123227) all 10 read (8 before), points
    kept 225 (120), important points found by the same matcher 88 of 153 = 58% (64 = 42% before; on the 8 read both
    times 60% against 52%). In-sample and below the 85% bar, wrong points not yet counted; and 8 of the 10 were served by Flash-Lite (the Flash models' 20 a day were spent), so the gain is the prompt and the model together, not the prompt alone. Flash-Lite's quotes on a deck's figure slides are often bare numbers (Waaree: 21 of 40 points dropped by the quote check, rightly). **`MEMORY_CALL_V2` ON since 30 Oct
    ~06:45 IST (owner: "Switch it ON"; switches.toml, TODO 101).**
11. **Richer cards: what moved and why, from memory** (TODO 128), and the other card improvements, after memory.
12. **The four card switches on** (consolidated only, company EBITDA first, two parts, dated guidance): live (PR #219).
13. **Memory gaps checked against listing dates** (TODO 130): 1,445 before listing, 26 missed by the count, 50 truly absent
    in 37 companies; the 28 NSE-listed re-read (run 40944604129).
14. **PDF reader:** tested in its own session. Out-of-sample result (docs/bench/oos/README.md on #218): 60 filings, 500 figures
    against the exact XBRL key, numbers-first 243 right / 11 wrong / 246 none after two fixes (the 60 never opened while fixing:
    126/6/124); all 11 wrongs hand-sorted, 0 misreadings: 10 are the PBT definition (the XBRL tag is before the associates' and
    JVs' share, the printed PBT after it: M&M Q1FY27 7,260.60 against 7,628.09), 1 a file's own unit. #218 waits for the lead's
    line-by-line review. **Owner, 30 Oct ~02:55 IST: Yes** to switching the new reader on (SLIP_CHECK_NUMFIRST) once the
    review is clean; the old reader stays as the fallback. Next build (off, measured, owner decides): the new reader fills a
    results quarter whose file is late, instead of the AI's figures. The PBT finding matters for memory and cards: which PBT a card shows.
15. **Annual-report extras into memory** (related parties, contingent liabilities, auditor remarks, pay): TODO, owner's Yes.


**29 Oct 2026, 18:37 IST: where the financial work stands (the blocks below are the record they came from).**
- Done today:
  - The Screener rows compare quarters from Q1FY26 only (owner); a period before a company's listing is "before listing",
    not "no facts". Re-run 40874998205: the six main rows of the FY26 quarters 96.7 % exact (94,251 pairs); target 98–98.5 %
    (owner). Bank PBT as filed kept (13 fixed, 6 broken, all HDFC Bank); the fair-value rule dropped (5 fixed, 10 broken).
    Every rule is marked "cause known" or "numbers only" (TODO 115). `docs/design/screener-row-rules.md`.
  - The BSE FY26 results fill (894 facts) and the BSE annual reports part 1 (773 facts); part 2 (run 40875086865) runs.
  - Results XBRL against the PDF, 40 companies, Q1FY27: median 75 minutes after the PDF, 39 of 40 within 6.5 h
    (`docs/SOURCES.md`).
  - The numbers-first PDF reader merged (PR #215, 18:35 IST), switches off: 0 wrong on both keys, options off and on; about
    1.6–2x slower than the old reader (TODO 117).
  - Memory gaps (run 40875940744, read only): 326 of 1,856 companies have a gap from Q2FY25; from Q1FY26, 132 of 199 only
    before their first held quarter (likely before listing), 20 with a hole, 26 stopping early, 21 with nothing held.
  - Memory's own errors traced in code (TODO 118): Maruti and Bajaj PBT and the HUL/Vedanta EPS are by design; a ranking gap
    (a live file figure ranks like a card) is to be measured; Vedanta FY26 and SBI Life H1FY27 need their stored sources read.
- Next, in order:
  1. Sort the 239 year and balance-sheet pairs the BSE annual files moved away from screener; finish BSE annual part 2.
  2. The 47 memory-gap companies with a hole, an early stop or nothing held: check each against NSE's list, fill from files
     already downloaded where they exist.
  3. TODO 118 B (the ranking gap): an on/off count over stored memory, then the owner's Yes.
  4. The gap to 98 %: confirm the merger/demerger restatements as exceptions (327 pairs); screener's restated year-ago
     quarter (505 pairs) waits for the PDF reader to read the comparative column.
  5. The PDF reader's next PR (TODO 123): the causes behind its patches and one OCR per page, then a speed check against
     main on an empty OCR cache, before the owner decides its switches.
- **Owner, 29 Oct, ~19:02 IST: "run the 50 card blind audit after financials".** It runs once items 1-3 above are done
  (the BSE annual files and the gap fill read, TODO 118 B measured): 50 cards published since then, blind, independent
  reviewers (mid model at least), WRONG on the checked face with its 95 % interval (`daily_audit/rates.py`), against the bar of
  5 %. Its result says whether the financial work reached the cards.
- Waiting for the owner: TODO 118 A/B/C; the PDF reader's switches (`SLIP_CHECK_NUMFIRST`, `PDF_SHADOW`).

**Owner, 28 Oct, ~15:40 IST: "No blind audit of cards today", "Let's settle financial first".** The card audit and the
card-wording experiment wait. The financial-data order, until the owner says otherwise:
1. The bulk XBRL download (below): the 100-file test, then all 1,778 companies.
2. The 50-company screener check run inside the pipeline (`xbrl-facts`, then `screener-crosscheck --top-mcap 50`), on the
   downloaded files.
3. Close the gaps toward 99%, one named rule at a time, each tested on all 50:
   - screener's annual columns from the annual report;
   - quarters screener restated for a demerger;
   - lender balance sheets;
   - screener's own share count for EPS;
   - the associates switch per company.
4. Memory's own errors from the fifty study, each fixed in code under the owner's A:
   - Maruti and Bajaj Auto Q2FY27 profit before tax with the associates' share;
   - Vedanta FY26 on another basis;
   - SBI Life H1FY27 profit;
   - HUL and Vedanta EPS;
   - the missing quarters of 21 of 42 companies, re-seeded from the downloaded files.
5. The XBRL-against-PDF timing, from the download's timestamps.

**Afternoon of 28 Oct (15:17 IST):**
- **The bulk NSE download (owner, 28 Oct, ~15:00 IST: "start downloading all the files from NSE... Don't miss annual
  reports").**
  - The owner chose XBRL now, PDFs on demand. A trial downloads the PDFs it needs (measured 28 Oct: 525 files in 349 s
    with 8 parallel downloads).
  - The 180-day auto-delete of the raw files stays. The facts taken from them are kept (`raw/xbrl-facts/` is not under the
    rule).
  - Scope: the results XBRL (latest 12 quarters, both bases) and the annual-report XBRL (Ind AS only, 3 years) of the
    1,778 universe companies (count measured 19 Oct).
  - Size, measured 28 Oct on the 525 files of the fifty-company study:
    - results file: 9 KB gzipped on average;
    - annual-report file: 85 KB median and 240 KB mean gzipped;
    - their facts: about 75 KB a file.
  - Expected total: about 2 to 3.5 GB of the 5 GB R2 budget. That corrects the "about 1 GB" told to the owner at 15:05 IST,
    which left out the annual reports' size. The raw XBRL store stops taking new files at its 2 GB cap; the facts are
    still saved past it.
  - Why a new path: today's `xbrl-facts --download` fetches only the files memory recorded, and memory misses whole
    quarters for 21 of 42 large companies. A download from NSE's own list, in up to 8 shards, is being built (read-only for
    memory).
  - The first run is the 100-file test (`file_cap` = 100), read before the full run. It stops at once on any refusal. It
    also records NSE's own timestamps for every results row, to measure when the XBRL appears against the PDF.
- **Owner, 28 Oct: "PDF and XBRL almost come together... Once we get XBRL and Screener matching, we will use XBRL only for
  cards."**
  - Timing: an assumption for results until the timestamps above are measured. For Reg 30 event XBRL it was measured on
    18 Oct: 8 minutes median, up to 21 hours (`docs/SOURCES.md`).
  - Lead's view: the XBRL is not always right. IMPAL Q1FY27 was 100 times too small, and 13 known-wrong exchange figures
    were dropped from memory today. So a card from the XBRL alone still needs a check: the PDF, or the XBRL's own sums.
- **Screener against XBRL, 50 large companies** (`docs/audit/screener-fifty-2026-10-28.md`, partial: 64 files not fetched
  after a download returned nothing for one CIPLA annual file, with no refusal seen).
  - Pairs agreeing, exact or by a named rule:
    - quarterly P&L 95.5% (2,530 pairs);
    - FY26 P&L 81.1%;
    - balance sheet 86.0%;
    - cash flow 95.8%.
  - Short of the 99% aim. The main causes:
    - screener's annual column is built from the annual report;
    - quarters screener restated for a demerger (HUL, Vedanta);
    - lender balance sheets;
    - screener's own share count for EPS.
  - Memory against the files: 24 differences in 21,300 checks.
    - 17 are continuing-operations EPS (HUL, Vedanta). EPS is never shown.
    - Maruti and Bajaj Auto Q2FY27 profit before tax include the associates' share.
    - Vedanta FY26 revenue is on another basis.
    - SBI Life H1FY27 profit: 1,270 against 1,274.17.
- **Keeping every XBRL fact (PR #213, F224)**: four review rounds, 2,359 tests pass, CI pending.
- **The numbers-first PDF reader** (normal key: 125 right, 0 wrong, 212 no answer; the native reader gave 45 / 0 / 292):
  independent review resumed 15:02 IST; then it is merged as bench-only and scored on the XBRL key.
- The 50-card blind audit: at the 15:30 IST check-in, then the card-wording experiment (owner: "build it after the
  50-card check").

**Order the owner approved, 28 Oct 2026, ~06:50 IST** ("Yes, go ahead in that order"):
1. The blind audit of about 50 cards (item 1 below), this afternoon (check-in at 15:30 IST).
2. **The XBRL answer key**: memory's exchange-file figures located on each filing's PDF page by word position (row label,
   column header date, unit), so every PDF reader is scored on thousands of figures instead of a few hundred typed by
   hand, and every filing where the XBRL figure is not on the page is listed. Being built (`xbrl-key`, read only; its
   locator is measured against the hand keys first, and its first run is on 100 files).
   First run read against its PDFs (28 Oct, F224, `docs/audit/xbrl-key-disagreements-2026-10-28.md`): of the 28 figures
   with another number printed, 7 are wrong in memory (all IMPAL Q1FY27, a unit slip the guard missed; fixed, and on the
   known-wrong list), 9 were the locator's misreads (fixed, locator 2026-10-28.4), 12 are another line by definition.
3. **The PDF reader, one filing at a time**: fix everything on one PDF, then the next, a new layout each time (upright,
   sideways, tilted, scanned, sub-headings, units, notes). Every fix is re-scored on the whole key and kept only if
   nothing gets worse (a fix for one PDF broke the Titan test on 27 Oct). Ideas to use: one layout per company reused
   each quarter; arithmetic checks (revenue + other income = total income, total income - expenses = profit before tax,
   last quarter's own column equals this filing's previous-quarter column); pages sorted first by type.
4. In parallel, once the undo is merged: a "checked" mark where the XBRL file and the printed PDF agree, and fixes
   where the PDF and one more source agree against memory (owner's A). NSE and BSE agreeing is not two sources: a
   company files the same XBRL to both.
Owner's aim (28 Oct): the printed PDF as the source of truth. Measured today the XBRL is the better source (about 1 in
100 wrong; our PDF reader 13% of its answers wrong on the hard set), so the XBRL stays the daily source and the PDF the
judge until the reader measures better.

1. **Blind audit of about 50 cards written by the single run** (28 Oct afternoon IST, once enough new cards exist):
   the first measurement of the 13 switches. Independent reviewers, the fix author does not grade.
2. **BSE memory fill, batch by batch** (owner, 27 Oct). Batch 1 (run 40504758920): 49 companies, 321 quarters, 8,324
   figures, no refusal, stopped at its 500-file cap. Batch 2 (run 40524728754): 43 companies, 277 quarters, 7,277
   figures. Batch 3 (run 40541696607, done 23:54 IST): 40 companies, 210 quarters, 5,444 figures, 428 BSE files kept,
   no refusal; 157 quarters skipped because BSE's basis differs from memory's, 148 held, 16 fetches failed (NBFC files
   that came back empty). Batch 4 (run 40561999277, 00:09-01:24 IST 28 Oct): 1 company, 1 quarter, 27 figures, no
   refusal, "more left: False": **the BSE fill is done** under today's rules. Totals: 133 companies, 809 quarters, 21,072
   figures. Left out on purpose: 54 quarters where BSE's basis differs from memory's, 82 held, 127 with no new quarter.
   23 BSE lender files (NBFC template, e.g. TATACAP, PIRAMALFIN Q2FY26) came back empty: the known gap of 16 Oct (BSE's
   NBFC path answers a plain fetch with its homepage; `seed.py`), not a refusal. Risk the owner accepted: a wrong BSE figure (about 1 in 100 in the checks so far, e.g. Kovai
   Q4FY26) goes into memory unchecked; screener and tijori comparisons are the check.
   Checked 27 Oct night (`docs/bench/bse-fill-batches-1-2-check.md`): revenue and profit agree with screener in 98-99%
   of 1,776 pairs; of 89 differences read in the company's PDF, BSE right 82, **wrong 4** (Eco Recycling Q4FY25 profit,
   Vadilal Enterprises Q3FY25 profit, Pradeep Metals Q4FY26 profit, Veljan Denison Q3FY26 EPS: the company's own XBRL
   on BSE differs from its own PDF; tax sign flipped, prior-year tax left out, a discontinued line added, standalone
   EPS in the consolidated file). The four are in memory now; taking them out waits for item 6 and the owner.
3. **After the full BSE download: the BSE fill keeps its record as it goes and compares with memory before writing**
   (today the list of what it wrote is saved only at the end, and a refusal or a kill loses it).
   First half done 28 Oct, 02:30 IST (PR #201, two review rounds): after each company the fill appends its rows to the CSV and rewrites the
   summary JSON (`bse_gap_fill.Record`; a dry run records what it would write; a refusal keeps what was filled before it).
   The upload step already runs `if: always()` after the fill step's own `timeout-minutes`; a disk error in the record never
   stops the fill. Second half (compare with memory before writing) waits for the owner: what to compare a BSE figure with
   when memory has nothing for that quarter (the fill only fills empty quarters), and whether a disagreement holds the
   figure back.
4. **`refresh-card-blocks` waits for the owner.** The dry run (run 40546510549, 27 Oct 23:08 IST) would change **3,214
   of 7,895 stored cards**: the results block on 2,876, grounding 1,344, headline 288, key numbers 287, memory context
   270, fundamentals 140, scale 123. That is far more than `CARD_ONE_BASIS` alone; the refresh rebuilds every block
   with today's code and switches. Not run for real.
   Read 28 Oct, 01:15 IST (run 40565069516, artifact `refresh-diff`, 3,221 cards): mostly what the owner's rules want. 2,571
   cards lose the EPS line (owner: no EPS on cards), about 260 lose EBITDA comparatives, 145 lose a results table on the
   other basis (`CARD_ONE_BASIS`), 36 bank cards change their profit (for example ICICI Bank Q4FY26 15,611.87 to
   14,755.06: to be checked against the filing before any refresh). One defect found: 289 headlines got "(company-reported;
   results table ₹X Cr)", and 158 of them set a year's or a guided figure against the quarter's row. Fixed (below, PR
   #200); with the fix, 209 of those labels go. Before a real refresh: the bank profits checked, then the owner's go.
5. **FROM_ZERO step 2** (owner: yes to A-H): F first, a reliable PDF reader for results statements, scored on a
   hand-checked answer key of about 50 statements with pass marks set before scoring (`docs/FROM_ZERO.md`, TODO 112).
   Then B on (`XBRL_FILER_CHECKS`, after its on/off over stored memory, TODO 111), C, D, E, G.
   Done 27 Oct night: the answer key for normal statements (`docs/bench/normalpdf/`, PR #197). Built, not merged: three
   reader fixes behind `PDF_ROW_FIXES` (garbled unit lines, a boxed table's basis, revenue/profit labels). On the hard
   set of 340 figures, with the maintenance switches on: 104 right, 0 wrong before; 155 right, 1 wrong after. The one
   wrong is the key's mistake: the PDF prints 610.27, the key has the XBRL's 610.26 (owner to say whether the key
   follows the printed page). Merged 28 Oct 00:48 IST (PR #199) after two review rounds; one rule was withdrawn because it
   could turn a conflict into a wrong figure.
   The normal key scored (27 Oct night, code before #199; `docs/bench/normalpdf/score-baseline-2026-10-27.md`): of 337
   figures, live switches 35 right / 1 wrong / 301 no answer, maintenance switches 45 / 0 / 292. Fails the 98% right and 5%
   no-answer marks by far; passes the wrong mark. The reader has no rows for total income or profit before tax at all,
   and 29 of 50 filings give no answer. Re-scored alone, twice, on the code with #199 (28 Oct, 02:40 IST): 45 / 0 / 292 both
   times, identical on all 337 figures, so the score is repeatable; #199 added 5 right (SRF, VISL, HUHTAMAKI revenue; TBZ
   revenue and profit) and no wrong. The earlier 40-then-45 was the #199 code arriving between two runs.
6. **A way to take a proven-wrong figure out of memory in code** (not by hand). Built 28 Oct, not merged or run (F223):
   `known_wrong.py` (the list, with evidence; every memory writer skips a listed figure) and the Maintenance command
   `memory-drop-known-wrong` (dry run by default; a backup first; `restore` undoes it). The plan for the 35 proven-wrong
   figures and its exact runs is `docs/audit/known-wrong-2026-10-28.md`: 4 are the exchange's own file (list and drop), 31
   are expected to be put right by re-reading the company (`seed-memory --scrips`, one company a run, 50 files at most),
   to be confirmed by the re-read itself. Before the first run: merge, then the dry run.
7. **The docs clean-up the owner planned for later** (one doc per purpose, the one-off tools out of the live code); not
   started.

Not in the order, waiting where they are: call memory v2 (a second blind sample, then the owner's go); the screener
referee run 40513449694 (finished 28 Oct 00:11 IST at its 5-hour limit, results saved: 5,707 of 16,344 pairs decided by
NSE's own XBRL; memory matches the file in 5,480, screener in 21, neither in 10, no file 196; memory and the file are not
independent, memory was built from it). The 31 where memory is wrong or unsure: 12 EPS signs flipped (ALEMBICLTD Q4FY26,
APOLLOPIPE Q2FY26, PRIVISCL Q1FY25, RPOWER Q2FY25, SILVERTUC Q1FY27, MOLDTECH x5, NITCO Q4FY24, MAXESTATES Q2FY24), 9 EPS
stored as 0 (AHLUCONT, ARVIND, BGRENERGY, PILANIINVS, SKFINDIA, HARDWYN), DOLPHIN revenue and profit ten times too big
(Q2FY24, Q4FY24, FY24) and two lender revenue definitions (GEOJITFSL, SHRIRAMFIN): they wait for item 6. The PDF
referee on the open pairs (run 40541837810, finished 28 Oct 02:53 IST at its time budget, code before PR #199): 3,235 pairs,
1,157 PDFs, no refusal; decided 226 (PDF agrees with memory 197, with screener 17, with the XBRL 1, with none 11), unsure
or unreadable 529, not run 2,480. The 28 disagreements read by hand: mostly definitions, not wrong figures. Profit
including discontinued operations against memory's continuing figure (ABREL Q4FY26 -110.31 vs 5.39, ADANIENT Q4FY25
1,382.17 vs 4,014.9, ANUP FY25, BALMLAWRIE Q2FY26, BHARATRAS Q2FY26); bank profit before or after the minority share
(AXISBANK, six quarters, 0.3-0.5% apart); the reader on a sub-line or a half-year column (ADANIGREEN "i. Power Supply",
AXISBANK Q2FY27 15,306 = six months): reader errors. A lead for the owner: memory's profit is the continuing figure when a
company reports a discontinued line, so a card can show ₹1,382 Cr where the company's own headline profit is ₹4,015 Cr. screener-explain run 40498040302 finished 27 Oct, and its planned PDF check on the
unexplained rows is not started (owner to say).

**Every download and test run, and where its files are kept:** `docs/bench/test-downloads.md` (owner, 29 Oct: reuse test
files, never download twice). Add a row for each run.

## 3b. Built or agreed, waiting (swept from docs/TODO.md, 29 Oct 2026, ~10:50 IST; owner: "add all above")

Every Yes item of `docs/TODO.md` that is not done, by what it waits on. Nothing approved was lost; none of these is on the
live site yet. Keep this list current: an item leaves it when it ships or the owner drops it.

1. **Built behind a switch that is off, waiting for the release check** (on/off over stored cards plus an independent
   blind sample; the plan is one run with all of them together, then an audit: section 2's "single run with the 13
   switches"). Paused by the owner on 28 Oct ("settle financial first"); this is what moves the WRONG-card rate.
   - Card wording: the company's own EBITDA and one profit line (TODO 11, 14, 15, `CARD_EBITDA_PROFIT_V2`); two parts on
     every card (21, `CARD_TWO_PARTS`); consolidated first (44, `CARD_CONSOLIDATED_ONLY`); the results block on one basis
     (107, `CARD_RESULTS_ONE_LINE`); memory watch verdicts the filing contradicts (106, `CARD_WATCH_VERDICT`).
   - Memory checks: a year that does not match its quarters and the owners' / minority share swap (64, 65, 76,
     `MEMORY_YEAR_CHECK`); a KPI outside what its sector allows (77, `CARD_FOOTER_PLAUSIBLE`); the share count behind an EPS
     change (79, `EPS_SHARE_COUNT_CHECK`).
   - Other: the row-name map (93, `LINE_MAP`); the screener-style table on company pages (52, `VITE_SCREENER_LINES`); the
     BSE quarters before a company's first NSE file (108b, `BSE_FILL_PRE_NSE`).
2. **Waiting for the owner's decision.**
   - **Call memory v2** (TODO 101, `MEMORY_CALL_V2`, F180): what memory keeps from call transcripts and decks. Measured 27 Oct
     on 9 documents: important points kept 87.8% (bar 85%), wrong 1.9% (bar 2%); needs a second independent blind sample,
     then the owner's go. First in line for the card work once the screener work is settled (owner, 29 Oct).
   - Removing the companies not on NSE (45, `prune-companies`): built, its dry run never run.
   - Whether the 5% bar is reachable (85): waits for the 150-card measurement.
3. **Agreed, not started.**
   - A daily BSE pass for the BSE-only companies kept (47).
   - The automatic memory fixes and nightly jobs (69-74): a figure under the wrong quarter moved (69); the same figure in two
     quarters (70); a 100x slip (71); cards re-rendered after a proven memory fix, no AI (72); failed filings retried each
     night (73); nightly checks of the day's filings (74).
4. **Loose ends fixed in this sweep:** TODO 1, 2 and 6 said "PR #108 not merged", out of date (the 120 MB limit, the "file
   too large" reason and `failed-report` are on `main`); two rows were both numbered 108 (the second is now 108b).

## 4. Known problems (found 27 Oct, not fixed)

- Fixed 27 Oct night: the audit exports are kept as a GitHub artifact (`audit-export`, or the command's name) and are
  committed only to the branch the repository variable `AUDIT_BRANCH` names (before, a parked branch); the critic's
  export runs only with the repository variable `CRITIC` at 1.
- Fixed 27 Oct night: the `file_cap` input (the 100-file first test) now reaches every job that marks the cap: seed-memory,
  memory-gaps-fill, text-backfill and the PDF ensemble's download, beside `run` and `textback-bse`. Empty means no cap.
- `xbrl.eps_signs` still flips an EPS sign from one source (the same file's profit sign). Measured 28 Oct: 12 of the 31
  memory errors in the screener referee are flipped EPS signs. Read 28 Oct, 03:20 IST: the code already refuses the
  Alembic Q4FY26 case (26 Oct: owners' and whole profit of opposite signs), yet memory still holds -2.61 there, so at least
  part of the 12 is memory written before that fix. Putting it right means re-reading only those filings through today's
  code (the routine in DATA_QUALITY.md, a memory write): waits for the owner's go, with item 6.
- Fixed 28 Oct, 01:30 IST (PR #200, merged 01:33 IST): the "company-reported" label on a headline or key number is no longer added to a
  figure of another period (a year, nine months, a half, another quarter), to a guided or target figure, or to the
  earlier figure after "from". It was live since 27 Oct (`CARD_RESULTS_ONE_LINE`); cards written since then keep the
  label until a refresh.
- `screener-fill-apply` sits in the `maint-nse-memory` group, so it can run beside `screener-fill` and
  `screener-download`.
- During the hourly memory sweeps and the daily annual catch-up (they run whole), a new filing can wait about 15 minutes
  for its card instead of a slice.
- Several jobs can call NSE at the same time. Assumption, not measured as a risk: each job runs on its own GitHub machine,
  and no NSE list call has been refused in three days of side-by-side runs (27 Oct). Look again on the first refusal.

## 5. Waiting for the owner

**Decided 28 Oct 2026, ~08:10 IST (owner):**
- A company with a discontinued business: cards show the **continuing** business's profit only (as today). Lead's note:
  label it "continuing operations" on the card, since the company's headline profit can differ (ADANIENT Q4FY25 1,382
  continuing against 4,015 whole).
- The answer key follows the **printed page** when the XBRL differs by a rounding step. Applied: SPANDANA consolidated
  Q2FY24 revenue is 610.27 in `docs/bench/hardpdf/key.csv` (was the XBRL's 610.26).
- A BSE figure that fills a quarter memory lacks is checked against the filing's **PDF**, NSE's and BSE's alike: that is
  what the PDF work (section 3, steps 2-3) is for. Decided too (owner, ~08:25 IST): when the PDF reader places a
  different figure for certain, the BSE figure is held back; when it cannot read the page, the BSE figure is written,
  marked unchecked, and checked again once the reader improves. To build: the fill's compare step (section 3 item 3,
  second half) with an `unchecked` mark on each such figure.
- The company page switches to screener's layout (`VITE_SCREENER_LINES`) only after a check of the 50 largest companies
  against screener with every XBRL line and screener's rules; cards keep the printed figures.

**Decided 28 Oct, ~11:40 IST (owner):** annual-report XBRL (NSE, IND-AS type, not BRSR) is used as soon as it is
listed (measured: ITC FY26 on 20 Aug 2026, L&T FY26 on 4 Jul 2026, L&T FY25 only on 13 Jan 2026); screener's annual
columns equal it to the paisa (ITC FY26: sales 89,913.33 - excise 11,044.93 = 78,868.40, power and fuel 947.71,
employee cost 6,781.50). Annual-report PDFs are read only later, once the PDF reader meets a measured bar on the
answer keys (lead's proposal: no wrong figure and at least 98% placed).

**Measured 28 Oct, 10:10 IST (owner asked: BPCL's files from both exchanges, line by line):** BPCL Q2FY27 consolidated
XBRL from NSE (`INTEGRATED_FILING_INDAS_1744982_...`) and from BSE (`Integrated_Finance_Ind_As_500547_23102026081027.xml`,
maintenance run 40633429544, 2 calls, both 200): the same 356 facts, 0 differences, so NSE and BSE agreeing is one source,
not two. The standalone file matches the owner's PDF on all 21 printed lines. Excise duty IS in the integrated XBRL: a
breakdown row of `OtherExpenses` (`DetailsOfOtherExpensesAxis`, description "Excise Duty", 8,737.53 Cr of the 18,201.41
total), which memory never read; screener's sales 1,49,080 = 1,57,817.93 - 8,737.53, and its other income 675 = 349.43 +
associates 325.24. The file carries only the quarter and the half-year, no earlier columns. Memory matches every line it
keeps. The four re-read pilots (ALEMBICLTD, AHLUCONT, DOLPHIN, MOLDTECH) fixed their EPS signs, zero EPS and 10x figures;
13 known-wrong figures were dropped (backup `backup/memory-drop-known-wrong-20261028T024424Z/`).

**Done 28 Oct morning:** the undo (PR #205), the XBRL answer key (PR #206; first live run of 100 files started 07:58 IST),
a fresh memory backup, a fresh screener cross-check (revenue 92.7%, profit 97.7%, EPS 75.3% the same; 349 of 1,603
companies with a revenue or profit gap; BPCL, IOC and United Spirits are screener's excise netting, which our check
missed because memory holds no excise line). Built and in review or CI: the known-wrong list and drop (PR #207), every
XBRL line kept plus screener's full rules and the balance-sheet / cash-flow comparison, the numbers-first reader
experiment.

- Turn the daily card audit routine back on (it would need re-binding to the current session), or keep audits by hand.
- The go-live bar against long cards: measured 25 Oct, 2.7% of lines wrong; at about 13 lines a card, 5% WRONG needs
  about 0.39%. The owner chose long cards (25 Oct); the two may not fit together. Decide after the audit in section 3.
- Commit trailer: CLAUDE.md says no AI model names in commits; the 27 Oct handover asked for a trailer that names one.
  Correction (28 Oct, 01:00 IST): several commits of 27-28 Oct night (PRs #198, #199) still name a model in their
  Co-Authored-By line, and older commits on `main` do too; merged history is not rewritten. From 28 Oct the lead
  session's commits use "Co-Authored-By: Claude" with no model name, as CLAUDE.md says.
- From earlier: B3 (held cards hidden, flagged or approve/reject), A2/A3 (backfill pace, re-writing cards after it),
  B5 (prices from bhavcopy), G9 (a Cloudflare rate-limit rule), Workers Paid renewal before about 21 Nov (otherwise set
  `D1_PLAN=free`; reminder `trig_0197dpX6XnQXDm8B3vxWAUC8`, 18 Nov). G8 (delete the BSE client) is dropped: the BSE
  adapter is in use.

## 6. Facts that changed (older files still say otherwise)

- **The PDF reader is not reliable** (owner, 27 Oct). The 98.5% in older files is OCR text on a few hand-picked
  filings (17 Oct). Measured 27 Oct on the hard set of 340 key figures (run 40414799620): our reader 65 right, 10
  wrong, 265 no answer (about 19% right; 13% of its answers wrong); the best of 11 readers about the same. In the PDF
  check of memory (run 40393302149) a third of the pairs it reached ended unsure or unreadable, and it read the wrong
  line in 9 of 18 hand-settled cases. A figure from the PDF reader alone is a lead, never a confirmed figure, until
  TODO 112 (an answer key and pass marks) says otherwise.
- BSE answers GitHub's machines through the ported adapter (`adapters/bse.py`; measured 25 and 27 Oct); a bare probe got
  403. The pipeline's daily path is still NSE only; BSE fills memory gaps.
- Branch: the session's own branch (now `ccr-e9a25af8-4vz8up`); PRs to `main`; after a merge the branch restarts from
  `main`. `claude/gracious-goodall-jn9buu` is parked.
- Decisions run to D43 and findings to F222 (`docs/TRACKER.md`).
- Test count: 2,062 passed, 7 skipped (27 Oct), both with the switches off and with the file's switches.
