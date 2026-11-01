# Status: the one current page

Read this first (handover of 31 Oct 2026 07:45 IST: `docs/handover/2026-10-31.md`). It replaces the "pending", "status" and "next" parts of `PLAN.md`, `HANDOVER.md`, `TODO.md`, `TASKS.md`
and `docs/audit/actions-pending.md`. Those files stay as history; do not work from their lists. Keep this page current:
when something changes, change it here, in plain English, with the date and time in IST.

Last updated: 1 Nov 2026, 09:10 IST (handover at the top of section 3).

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
| Cards filed 30 Oct - 1 Nov (audited 1 Nov, `docs/audit/live/2026-11-01-audit.md`) | 50 | 14.0% | 7.0-26.2% |
| Cards from the single run with the 13 switches | not yet | | |

Not met. The rate has stayed between 15% and 23% for a week while about 120 fixes shipped (F104-F222).

## 3. Open work, in order

### 3.0 The one open list (consolidated 1 Nov 2026, ~09:30 IST; owner: "check past pending items ... many are cleared, not required or superseded")

Every list was swept: this section 3 (the lead's list and the 31 Oct table below), 3b, docs/TODO.md, TASKS, PLAN, HANDOVER, docs/handover/2026-10-31.md and docs/audit/actions-pending.md, each item checked against git, switches.toml and the code. **This sub-section is the one current list; everything below it in section 3 and 3b is history** (kept for its findings). Lanes (co-leads, #303): **cards** = second session; **data** = lead; **reader** = reader session; **owner** = needs the owner.

**Open, by impact on the go-live bar (cards WRONG <= 5%, **now 20 of 100, 20.0%, 13.3-28.9%**, the two 1 Nov audits pooled: 14.0% morning, 26.0% (15.9-39.6%) afternoon, `docs/audit/live/2026-11-01b-audit.md`) and on the Screener match:**

| # | Item | Lane | Next step |
|---|---|---|---|
| 1 | The 1 Nov audit's WRONG classes (7 of 50): footer fixed in #311; five single cases left (ZEEL quarter called half-year, KRN FY25 as FY26, POLICYBZR associates as discontinued, OSWALPUMPS new order as stage update, MEDIASSIST buyback as FUNDRAISE) and 2 "Our reading" WRONGs | cards | fix each with a test, then a fresh 50-card blind audit; repeat on the commonest class until <= 5% |
| 2 | `CARD_TEXT_SUPPORT` (off) | cards | **stays off, 1 Nov ~13:05 IST (measured)**: blind grade of run 41261609960's 60-item sample (mid model, filing text from the artifact, key opened after): 20 right drops, 40 true items lost (67%, ~54-77%); 2,001 of 9,798 cards would change, 2,654 items, 54% in track_next. The word check loses true items on abbreviations and spelling ("AGM" against "Annual General Meeting": 230 drops, 10 of 10 sampled true; "Build-Operate-Maintain"); its "discontinued" label check was right 5 of 5 (the associates' share, the class row 1b fixes). Next if wanted: AGM/EPC-style aliases and hyphen folding, then re-measure |
| 1b | Afternoon audit classes (13 of 50, `2026-11-01b-audit.md`) | cards | **built 1 Nov, off:** `DISCONTINUED_NEEDS_FIGURE` (NETWORK18, GABRIEL, SARDAEN, POLICYBZR: the associates' share called discontinued; release-check `discontinued_figure` run 41281847613); `DECK_DISCUSSED_PERIOD` (KRN: a deck has no figures of its own, so a target due that quarter was "not due"; release-check `deck_period` run 41282589971). Open: wrong column from decks (AVL, MEDIASSIST, SHARDACROP, AJANTPHARM), EICHERMOT volume strip mixing segments, HEGAM another company's results, TI PAT before exceptional items as the headline |
| 3 | Headline tag "(company-reported; results table ...)" against a table of the other basis; some headlines wrong at source (CDSL, BLIL "standalone revenue") | cards | tag by the headline's own basis word, or fix the headline at source |
| 4 | `RESULTS_PRESS_RELEASE` (off, #269) | cards | on/off on live results filings, then switch |
| 5 | `UNIT_SLIP_XBRL_GUARD` (#313) | data | **on, 1 Nov ~11:10 IST**: release-check 41263548723 over 9,884 cards: 70 with a unit correction, 3 with their file, 0 would change (each a real slip); nothing for a blind sample to judge |
| 6 | `D20_DROPPED_FILE_PERIOD` (off, #314; TMB root cause) | data | **stays off, 1 Nov ~11:50 IST (measured)**: Pipeline logs of all 474 runs: 111 filings had their results file set aside, ~15 of them published a second RESULTS card of a quarter that already had one; a blind read of those 15 pairs (mid model, both cards, 5 PDFs opened): 5 HOLD_OK, 10 LOSES_NEWS (the later card is the press release, call or correction: MARUTI volumes and share, CANBK FY26, ACC call guidance, KAYNES cash-flow correction), and with RESULTS_PRESS_RELEASE off `_fold_release` keeps nothing. Wider class handed to the cards lane (#316): since 25 Oct 40 of 412 companies have two or more published RESULTS cards (44 extra), mostly releases typed RESULTS with no quarter; the fix is fold or keep, never hold |
| 7 | `ANNUAL_SCALE_FIX` (TDPOWERSYS, MSPL annual reports 1e5 small) | data | **on and applied 1 Nov (#317)** |
| 8 | Screener gap (FY25 on, 1 Nov run 41269771761): exact / close (within 0.5%): quarters 95.7 / 96.4%, annual 90.3 / 92.8%, balance 92.2 / 93.8%, cash flow 94.1 / 94.5%; site = recipes (0 pairs differ, ~60 lacking) | data | **tried and dropped 1 Nov**: annual P&L from the Q4 file (branch run 41274289728: mended 594, broke 3,322; annual 90.3 -> 85.8%). Next candidates, each measured on every company before merge: finance-arm interest in Interest (Grasim, L&T), Sales incl. other operating revenue (Godrej Ind, Coal India); exceptional items need note text |
| 8a | Levy rows from notes (screener_view `_levies`): a contingent-liability or disputed-demand amount tagged on the expenses element was taken out of Sales and Expenses (GODREJIND "GST demands" 23,361 Cr against Sales 19,657; Ajanta, LTTS, Welspun Living, Bikaji, Salzer, Elgi Rubber) | data | **built 1 Nov (this PR)**: a described row larger than total Expenses is ignored; 36 FY25-on Sales pairs expected mended (rows.csv), every-company measurement run 41279412588 before merge |
| 8b | Live path: a December, June or September year (VBL, ABB, Siemens) was written by the rebuild only; the live run wrote years from March files alone | data | **merged 1 Nov (#320)**: `statements.rows_of` writes the year as "YE:2025-12" when the file holds twelve months to its quarter end (a March company's December file has nine: none), and a balance sheet at any quarter whose file has one, as the rebuild does; "YE:" years sort with the quarter that ends them, so the 120-entry cap no longer drops them first |
| 9 | Bank PDF reader full run (TODO 148 follow-up): City Union, Bank of Maharashtra FY23-25, UCO 0.0 depreciation | data | full `bank-pdf-read`, then rebuild |
| 10 | Memory gaps: 47 companies without stored facts; raw XBRL files with no facts copy (10 are Q2FY27) | data | **live-path cause fixed 1 Nov (this PR)**: the facts copy was written only at the memory write, so a file the card set aside had none; `xbrl_facts.keep` now writes it at download. Left: `xbrl-facts` on the 47 and the older files |
| 11 | Restated year-ago figures from the PDF (`restated-pdf`): trial 40431994775 stored nothing (reader slips) | data | fix the reader slips, re-run the trial, then top 500 |
| 12 | Memory errors (TODO 88-90, 96b: EPS sign flips) | data | re-read only the affected filings (DATA_QUALITY routine); owner go |
| 13 | REITs: Brookfield operating profit 713.6 vs Screener 701; daily refresh step; R2 lifecycle for raw/reit-xbrl/; step 2 (NDCF, DPU, NAV) | data | daily refresh and lifecycle first |
| 14 | Auto-fix chain (TODO 69-74) | data | approved "after the PDF trial (row 68) passes": check row 68 first |
| 15 | PDF readers (TODO 112/119/122): nemotron guard `NEMOTRON_BASIS_GUARD` (#315, off); Mistral and nemotron-parse-2.0 dead ends | reader | **fresh set FAIL, 1 Nov ~12:50 IST** (run 41278380328, 343 figures): numbers-first 183/2/158; numbers-first then guarded nemotron 203/5/135, 3 added wrong (consolidated PAT, another profit line: ZYDUSLIFE, PHOENIXLTD, COFFEEDAY), pass mark 0. #315 merges with the switch off; reader and lead advise keeping nemotron off (owner's call) |
| 16 | Call memory v2 (9.2-9.6% WRONG vs 2% bar; TODO 136/144 blocked) | owner | choose A keep off / B vision for slide quotes / D stronger model |
| 16b | Results page By group: the "What it says" box did not follow All / Ex-financials / Financials (owner, 1 Nov ~10:15 IST, phone screenshot): the medians did change, but the lead never named the companies and the bullets were all-company totals | data | **fixed (this PR)**: the lead names the cut ("Among banks, NBFCs and insurers, ..."), the bullets follow it (financials' own totals on Financials; no financials-share line off All) |
| 17 | Results and stock-page leftovers (A1 ADANIENT standalone, A4, B2, B5; TODO 143) | cards | low priority |

**Owner answers, 1 Nov ~09:45 IST:** Cloudflare Workers Paid renewal **done**; Mistral's admin page shows OCR **allowed** on the Free plan, October spend **$4.3** for the whole month (so the reader's 429 is a real rate limit, not a plan block). The second session was back at 09:28 IST (its post crossed the lead's takeover by 5 s): it keeps the cards lane (item 1, the five WRONG classes, in one PR; then text_support); the lead's two helpers on the same items were stopped, nothing pushed.
**Owner, 1 Nov ~10:00 IST:** nemotron-3.5-parse model id: not needed now (dropped); #281 Design E: already merged 31 Oct 07:15 IST (live); minimum group size **5** agreed, built (`MIN_GROUP_SIZE`, web `resultsView.ts`: a group with fewer than 5 companies reported is never ranked or named as leading). `ANNUAL_SCALE_FIX` on (measured: only TDPOWERSYS/MSPL's 9 left-out years return).
**Owner decisions / account actions:** results filing made twice: table on the repeat card?; daily card-audit routine on or by hand; B3 held-card display; B5 bhavcopy prices; G9 rate-limit rule; whether the 5% bar fits long cards; "Later" items (TODO 37/38/41/46/47/58/59/83/101/113).

**Second sweep, 1 Nov ~13:20 IST** (owner: "don't forget anything pending from day 1"; independent pass, evidence in each line; these sat in no row above):

| # | Item | Lane | Next step |
|---|---|---|---|
| S1 | Arithmetic in words ("accelerated... outperforming", "far outpaced"; HANDOVER class 7): no check exists outside CARD_TEXT_SUPPORT (off) | cards | a small comparative-word check, on/off over stored cards |
| S2 | Same event, different documents (results + deck + release; buyback + letter of offer): duplicates.py matches identical bodies only, D20 covers RESULTS only | cards | read-only count of stored non-results repeats, then the event-level rule with its on/off |
| S3 | `XBRL_FILER_CHECKS` (TODO 111, F219; built, off; owner "after BSE", BSE done) | data | on/off over stored memory, then owner's call |
| S4 | TODO 128 steps 2-3 (the "may be" memory link behind a mover) | cards | blocked on call memory (row 16) |
| S5 | TODO 121 PDF shadow check (#237): every scheduled run skipped, repository variable PDF_SHADOW not "on" | owner | set it on, or drop it after the reader's FAIL (row 15) |
| S6 | `fill-trades` remainder: 656 insider-trade filings unread; deals history 27 Apr - 21 Aug only (OPS 23 Oct) | data | one `fill-trades` run when the memory chain is idle |
| S7 | TODO 123 reader cleanup (`drop_twin_rows`, `tail_label` still in pdf_numbers_first.py) | reader | low while the reader set fails |
| S8 | TODO 126: 21 finance companies with empty BSE files | owner | Yes / No / Later never answered |
| S9 | TODO 113 and TODO 47 (owner Yes, conditional: after the 95% gate) | label | "Yes, waiting for its trigger" |

Doc notes: `MEMORY_CALL_V2 = true` only queues and gates the call-memory job; the v2 prompt is not live (TODO 101). "Unclear" also holds XBRL_FILER_CHECKS, CARD_EPS_WHOLE and PDF_SHADOW. Owner "Later": TODO 36, 39, 40 as well.

**Cleared in the sweep (evidence):** TODO 1/2/6 (on main), 7/9 (no gap / nothing needed), 18-20/25/26 (F132-F136 built), 45 prune-companies (2,496 removed 26 Oct; 3b's "dry run never run" was stale), 129 Borrowings (#270/#273/#298; SHILPAMED recorded exception), 140/141, 147 unit slips (#294-#301), 148 bank reader (#299), 149 weekly Screener check (screener-weekly.yml, #298), 150 (#298), 151 lender fact sheet (#300, on in #304); Hubtown nse-106629168 and BANKBARODA cards right; Varun Beverages no mapping fault; card switches 3b.1 listed as "waiting" are ON in switches.toml since 27/30 Oct (CARD_EBITDA_PROFIT_V2, CARD_TWO_PARTS, CARD_CONSOLIDATED_ONLY, CARD_RESULTS_ONE_LINE, CARD_WATCH_VERDICT, CARD_FOOTER_PLAUSIBLE, EPS_SHARE_COUNT_CHECK, CARD_GUIDANCE_DATED, CARD_ONE_BASIS, CARD_GROUNDED_FIGURES, QUOTE_EXACT_NUMBERS, CARD_SAME_DEFINITION; the 1 Nov audit is their post-switch measure); VITE_SCREENER_LINES and BSE_FILL_PRE_NSE default on; REIT full run done (41153853516). **Superseded:** TODO 3/10/13/16 (by MEMORY_FILE_ONLY and CARD_FACT_SHEET, both on), 103/100/108 (BSE_FILL_PRE_NSE), 114/116 (weekly check), RESULTS_NEEDS_STATEMENT (by D20_DROPPED_FILE_PERIOD); laptop-era TASKS/PLAN/HANDOVER lists. **Not needed:** G8, TODO 29/42/54 (owner No), 146 (Later), 8 (Later), 17 (measured). **Unclear (to decide):** MEMORY_YEAR_CHECK, LINE_MAP, MEMORY_SCREENER, MEMORY_STANDALONE_ONLY, MEMORY_RESTATED (built, off, no on/drop decision found); TODO 62/66/75/81/94/96b (Tijori follow-ups: did tijori-referee run?); docs/audit/actions-pending.md's 21-23 Oct requeues (live cards not re-checked).


**Handover, 31 Oct 2026 ~06:25 IST: the Results page and REITs session (branch `ccr-69266234-c8jxew`).** In plain words, for the next
session. Read this block, then the table below.

*Merged and live (30-31 Oct).*
- **#272** the Results page as a KPI report (took over #268, whose branch was left with a half-built page; #268 and the older #223 are
  closed). One row per company and quarter in D1 `results_kpi`, from each company's saved statements only (no card). Review fixes in
  it: stale quarters removed (`results_kpi_prune`), profit pace only on the same basis, a zero base going to a loss reads as "loss
  widened", avatar colours at 4.5:1, `resultsView.test.ts` added to `npm test` (CI had never run it; four of its tests were wrong).
- **#274** `results-table` saves every 100 companies (a stopped run keeps its work); each view ranks by its own column; market words
  ("median", "Profit up, EBITDA down"); the Nifty 500 box says how many members are not covered. **#275** a link naming only a view
  (`?view=momentum`) ranks by that view's column (measured live 31 Oct: the three views lead with different companies).
- **#276** REIT plan and findings (item 12). **#279** REITs and InvITs, step 1 (`reit_results.py`, Maintenance `reit-results`, kinds
  `reit` and `invit`, trusts kept by `prune-companies`). **#280** hotfix: #279 put a `#` comment inside the folded `group: >-`
  concurrency expression of `maintenance.yml`, and GitHub refused every Maintenance dispatch until it was merged (about 5 minutes,
  31 Oct ~06:00 IST). The automatic pipeline (`pipeline.yml`) was not affected.

*First full build of `results_kpi` (30 Oct, ~23:22 IST, Maintenance `results-table`).* Companies a quarter: Q2FY27 572 (season under
way), Q1FY27 1,820, Q4FY26 1,756, Q3FY26 1,744, Q2FY26 1,701, Q1FY26 1,683, Q4FY25 1,462, Q3FY25 1,469, Q2FY25 1,439, Q1FY25 1,404,
Q4FY24 929; older quarters a handful (a company keeps its newest ten). Index refresh (Sync indices) the same night: Nifty 500 247 of
497 reported for Q2FY27 then. A late filer appears within one or two pipeline runs once its exchange XBRL file is read (the results
step refreshes companies with a results card in the last 10 days).

*REIT 100-file test, read 31 Oct ~06:30 IST* (Maintenance `reit-results`, `file_cap` 100, run 41150836776, 06:10-06:20 IST): NSE listed
193 filings, 185 after revisions; 100 downloaded and kept (`raw/reit-xbrl/`), the cap reached as planned, none unreadable; all 27 trusts
in `companies`; 54 quarter rows (Q1FY27 26, Q2FY27 5, Q4FY26 23). The Nifty 500 box reads 260 of 500 members (no "not covered" note).
Against Screener: Embassy Sep 2026 1,302.6 / 980 / 831 and Jun 2026 1,240.8 / 959 / 195 (Screener 1,303 / 980 / 831 and 1,241 / 959 /
195): equal. Brookfield Jun 2026 sales 973.8 (Screener 974), operating profit 713.6 (Screener 701, not explained yet: our expenses are
total expenses less finance cost and depreciation), profit 179.8 to unitholders against Screener's 221.3 total (41.5 minority interest:
the page's rule is the owners' share, as for companies). Bagmane Jun 2026 437.0 / 364.2 / 57.9 (Screener 437 / 364 / 59, total 58.5).
Bagmane's newest file (broadcast 22 Oct) is its June quarter, filed late; NSE's list calls it period 31-Mar-2027. No growth figures yet:
the year-ago files are among the 85 not downloaded. Four more files were fetched once by hand (Brookfield, Bagmane) to check the above.
Next: the full run (`file_cap` 100 more is enough: 85 left), then the year-ago check; the list reaches back to Sep 2025 only by default
(Q1FY27 has no year-ago file without a `from_date`); a daily refresh step; trusts' market cap; the R2 lifecycle for `raw/reit-xbrl/`;
step 2 (NDCF, distribution per unit, NAV per unit).

*Open PR.* **#281** (not merged, waits for the owner's OK): the top of the Companies tab as the owner's Design E (revenue / EBITDA /
PAT up and loss-to-profit tiles with medians, progress ring with the next meeting, "What this list says" kept, spread of PAT growth,
"Is profit growth speeding up?"), and the By group ranked-dots chart removed (one outlying group squashed it on a phone).

*Waiting for the owner.* (1) Merge #281. (2) A minimum group size, proposed 5 companies reported, before a group is ranked or named
"leads the season" (live, 31 Oct: Diversified +480% and Telecom Equipment +1,746% led their tabs on one or two companies). (3) The REIT
full run (the 100-file test is read, above).

*Learned the hard way.*
- No `#` inside a folded `${{ }}` expression in a workflow: YAML loads it and CI passes, GitHub refuses the dispatch.
- NSE answers an unknown `index=` name with `{"data":[],"msg":"no data found"}`, the same as a real empty answer: test a made-up name as
  a control before calling a source empty. The REIT/InvIT call is `index=reitsinvits`, found in NSE's own `corporate-filings.js`.
- NSE's REIT list puts the year end in `periodEnded` on some new files (Embassy and IRB InvIT, Sep 2026 quarter: 31-Mar-2027); the quarter
  comes from the XBRL's own three-month context.
- Screener links a REIT's quarter to BSE's PDF; NSE has the XBRL, with the same Ind AS tags as a company plus the trust's own.
- `vite preview` keeps the file list it started with: restart it after a rebuild, or the page is blank (the scripts answer as HTML).
- `actions_list` on `maintenance.yml` returns very large JSON (commit messages): read only id, status and conclusion with `jq`.


**Results page as a KPI report from the saved statements, 30 Oct 2026 ~22:00 IST (owner: "only the saved statements, no card"; "consolidated over standalone"; "no company repeated"; "growth filters and sorting, redesign the entire page as a KPI report").** Built: `results_table.py` (`results-table`) turns each company's `statements` (the company page's Results tab source) into one row per company and quarter in the D1 table `results_kpi` (revenue, EBITDA, PAT, margin and their changes); the Worker's `/api/results-kpi` filters and sorts them in the database; the page shows one row per company for a quarter with a summary strip. Each pipeline run refreshes the live window's companies; the first full build is Maintenance > results-table (`--all`), run after the deploy has applied migration 0015. Also built (PR #268, owner 30 Oct 2026 "update it every Sunday"): `sync-indices` (workflow `sync-indices.yml`, Sundays 09:00 IST) keeps NSE's broad index members in `index_members`; the page's index filter, sector and industry filters and the by-group medians wait on the owner's approval of the design. Not yet measured: how many companies each quarter has (read the first full build). Banks and insurers have no row. The page no longer reads a card.

**Owner's decisions, 30 Oct 2026 ~14:30 IST** (TODO 101, 128, 136, 140, 141): (1) call memory prompt v2: read ~150 points of new
live calls apart, blind-judge, switch only at or under 2% wrong; (2) a late file's results card keeps no table until the file
(option A); (3) empty balance-sheet entries removed by code (backup, 50 a run, dry run first); (4) the card design is already
given (TODO 128 example, the Gemini APAR write-up, TODO 136): build from it, ask nothing more.

**Owner's decisions, 30 Oct 2026 ~17:25-19:20 IST:** (1) remove AI balance-sheet snapshots the exchange file covers: Yes
(TODO 141); (2) the chart-label rule for call memory: "Do it" (TODO 144); (3) NUMFIRST_STOP_EARLY on: Yes (PR #261, live
~19:26 IST). The owner offered a second Mistral key; lead: not needed, Mistral's limits are per organisation (TODO 145).

**Lead from 31 Oct 2026 ~13:50 IST: the session on branch `ccr-c282922e-vajnv9` (owner: "You are new lead and please finish other
pending work also"; handover from `ccr-e9a25af8-4vz8up` received, nothing of it running). A second engineering session (owner's other
account) builds TODO 148 then 151 in code only; it reaches the lead by commenting on the lead's open PR (now #298), the lead runs every
job. Hourly lead check-ins until 22:00 IST.**

**The lead's list, in order (31 Oct 2026, ~14:00 IST):**
1. Statements chain on main: statements-rebuild dry run (running) -> apply -> statements-correct -> results-table -> screener-rows
   (with the new run-against-previous report). Then tell nobody else is on maint-nse-memory.
2. Merge #298 after the rebuild (weekly Screener check, TODO 149; no old-rule tables, TODO 150).
3. Review and run the second session's PRs (TODO 148 bank PDF reader, TODO 151 fact sheet for lenders).
4. Hubtown nse-106629168: the live card still shows finance cost Q4FY25 0.02 Cr (right: 18.82); requeued 12:52 IST after #294 but
   a 19 May filing waits behind ~1,500 history filings. Re-run that one card by the existing path, never a hand edit.
   **31 Oct ~18:15 IST:** still the old card. #298's requeue puts Hubtown first in the history queue, but pipeline run
   41196991535 (17:03-17:43 IST) spent its whole 40-minute budget on the day's results filings (20 deferred) and never reached the
   history pass. It re-runs on the first run with time left; results season can delay that for days. Varun Beverages nse-106835976
   is re-made (revenue 6,815.59 Cr).
   **Fix on #301 (31 Oct ~19:30 IST, shipped as a live wrong card):** `requeue-failed --ids` also names the filings in
   `requeue:by_id`; each run gives them a slot of at most 3 minutes, 6 filings, right after today's filings
   (`pipeline._requeued_first`), before the history pass. Hubtown was requeued before this existed: after #301 merges, run
   `requeue-failed ids=nse-106629168` once more.
   **Owner, 31 Oct 2026 ~20:15 IST: the Screener match cut-off is FY25 onward** ("We took cut off of FY 25 onwards only data required so no problem if past data is not available for screener match"; was FY23). screener-rows-diff counts from FY25; quarters are compared from Q1FY26 (`FIRST_QUARTER`, also the BSE fetch start, left as is). Older years stay on the site as stored, not matched.
   **31 Oct 2026 ~22:50 IST (second session):** (a) `RESULTS_NEEDS_STATEMENT` stays **off**: release-check run 41209814351 retyped 181 of 2,305 stored results cards (7.9%), real ones among them (TATAELXSI, HINDZINC, VEDL, JIOFIN), so the heading test alone is too wide. Narrower rule, not built: retype only a RESULTS filing with no statement heading **and no exchange file of its own** (TMB's note borrowed the bank's quarterly file through `_results_xbrl_link`); measuring it needs the filing's `xbrl_url` in the release-check's cards (export_cards has none). (b) BANKBARODA nse-106836576's live headline "net NPA 0.00%, gross 0.00%": a gross NPA of 0 beside a real RoA is the file's filler and is dropped with the net NPA (`xbrl._bank_ratio_fillers`, on #302); requeue that card after merge.
   **1 Nov 2026 ~02:00 IST (second session, owner: "you can run anything now"):** #302 merged (9ecf94a). Every-company check (run 41225618362, 1,821 companies, FY25 on): stored statements = recipes, quarters 95.7%, annual 90.2%, balance 92.3%, cash flow 94.1%; 4,153 pairs missing on the site (December-year filers, Q2/Q4-only balance sheets) fixed in the backfill; statements-rebuild applied (run 41235721141; 639 entries, unit slips Navneet / Park Hotels Q4FY26 cons and IMPAL Q1FY27 removed), then results-table --all. Hubtown nse-106629168 and BANKBARODA nse-106836576 re-made right on the fixed code (the 1,000x comma-as-point shrink; the gross-NPA-0 filler). **Open:** a December-year company gets no annual statements at all (SCHAEFFLER: quarters and balance sheets only, no annual entry in any year): `_ours(..., "annual", ...)` for a non-March year end; the re-run of screener-rows limit=2000 on main counts what is left.
   **1 Nov 2026 ~06:30 IST:** #306 (comparative years) and #308 (December, June and September years, `YE:2025-12`) merged and applied (rebuild run 41251768188: 190 entries, 95 annual, 89 cash flow, 6 balance; results-table run 41253940036). Live: VBL Dec 2023-2025, ABB Dec 2025, Siemens Sep 2023-2025. Every-company check on main (run 41254893012, 1,856 companies, FY25 on): quarters 95.8%, annual 90.3%, balance 92.2%, cash flow 94.1%; pairs the recipes have and the site lacks 3,428 -> 142 (ELANTAS, KENNAMET, FOSECOIND year-end years; TDPOWERSYS, MSPL, PARKHOTELS annual; 50 quarters). **Found and fixed (this PR):** the live run re-reading old May results files (RITES, VINATIORGA, run 41252490055) put the results file's FY26 cash flow and March sheet back over the rebuild's annual-report figures (RITES cash from operations 165.97 over 327.48, Screener 327); `statements.remember` now keeps a stored-facts entry of the balance sheet, the year and its cash flow. After merge: statements-rebuild with `ids` 541556,524200.
   **1 Nov 2026 ~09:10 IST (lead):** #309 merged and RITES/VINATIORGA rebuilt (live: RITES FY26 CFO 327.48, borrowings 6.59; VINATIORGA total liabilities 3,579.04). #310 + #314 merged and applied (rebuild run 41263321995: 335 entries incl. #311's owners'-profit rule, CHOLAFIN Q2FY27 1,630.34; then the #314 rebuild): ELANTAS YE:2023-12/2024-12/2025-12 live. #313 merged: `UNIT_SLIP_XBRL_GUARD` (off; the owner's rule "the XBRL file is never overruled by the PDF"; release-check `unit_slip_guard` queued). #314 also holds `D20_DROPPED_FILE_PERIOD` (off): the TMB nse-106836238 root cause (an ECL note's set-aside results file left it with no quarter, so D20 never looked). refresh-card-blocks for #311: dry run 4,904 of 9,851 cards change (fundamentals 1,521, results 3,685, headline 76 by CARD_RESULTS_ONE_LINE), applied. On the branch: `ANNUAL_SCALE_FIX` (off; TDPOWERSYS/MSPL annual reports 1e5 small, rescaled only when Sales and Net Profit both match their four quarters at one factor), measured by a branch dry run before its PR. Three sessions in lanes (#303, 08:30 IST): cards (second session), PDF readers (reader session, NEMOTRON_BASIS_GUARD in #315, fresh pdf-oos seed 31), data/switches/jobs (lead).
5. TODO 147 leftovers (unit-slip enlargements: SYRMA nse-106836602 cause unproven; reading 2 on malformed digit groups). **31 Oct
   ~16:05 IST (second session):** SYRMA's live card is right (1,989.68, rewritten by the exchange-file card); the cause needs its PDF
   (`SYRMASGS_30102026163122_BMOutcome30102026.pdf`), not downloaded here: the lead checks R2 for a kept copy before any fetch (rule:
   never download twice, keep every file).
   **Varun Beverages (handover item): no mapping fault.** Card nse-106835976 (30 Oct 11:50 IST, before CARD_FACT_SHEET went on at 16:00)
   shows the file's gross revenue 6,815.59; card nse-106835992 (press release) 6,607.6 = our statements' Screener Sales 6,607.56 (net
   of levies). New results cards use the sheet; the old card is to be requeued (asked on #299).
   **TMB nse-106836238** (₹304 Cr ECL provision note, typed RESULTS): typed RESULTS by NSE's category or the model, it took the results
   path and found the bank's Q2FY27 file, so a second results card for the quarter. Proposed rule: a RESULTS-typed filing with no
   results statement and no results covering letter in its text (`_RESULTS_STATEMENT`, `results_cover`) is OTHER. It changes cards, so
   it needs the on/off audit over stored cards and a blind sample first (owner rule). **Built 31 Oct ~18:10 IST behind
   `RESULTS_NEEDS_STATEMENT` (off; `pipeline.lacks_results`: no statement heading, no results covering letter, no "financial results
   for the quarter/half/year", and at least 1,500 characters of text).** The audit: Maintenance `release-check` with `ids` =
   `results_statement` (the stored RESULTS cards whose text is in R2, the last 8 days; changed = would be OTHER), then a blind read of
   the changed cards; switch on only if no real results card is retyped.
   **TODO 147 reading 2: fixed on #301** (an enlargement from an amount in whole rupees needs well-formed digit groups, as #297
   made it for reading 3; a shrink is unchanged).
   **SHILPAMED (TODO 129's other half): left as a recorded exception.** Consolidated FY23 and FY24 Borrowings are 1.31 Cr above
   screener's (on ~800 Cr), the CurrentMaturitiesOfLongTermDebt element SCREENER_CMLTD adds (measured +34 / -2 rows when it went on;
   these are the 2). Its current borrowings' breakdown already holds the current term loans; no file-level signal found that tells
   this case from L&T's (where the maturities are outside borrowings), so no rule.
   **TODO 129: fixed on #298** (a later report gives a year's balance sheet only with that year's equity; every case found is before FY23).
6. Owner questions from docs/handover/2026-10-31.md section 4 (Mistral October spend; NVIDIA nemotron-3.5-parse model id; a results
   filing made twice: table on the repeat card?; Cloudflare Workers Paid renewal before ~21 Nov).
7. Handover section 5: TODO 129 Borrowings 0 on 169 annual-report pairs (UltraTech FY20-24, JSL, Jindal SAW), SHILPAMED double count;
   Varun Beverages quarter mapping; TMB provisioning note typed RESULTS; TODO 136/144; TODO 139 before Apr 2027.
8. Annual P&L above ~88%: only from the annual-report notes (screener's regrouping); a later TODO.

**Open work, in order (31 Oct 2026, 05:10 IST; the one list, kept current after every step). From 23:00 IST the session on branch `ccr-244dd8fc-rq75sb` leads (owner: "continue all pending tasks one by one").**
| # | Item | State | Next |
|---|---|---|---|
| 1 | Rating snapshots the 30 Oct empty-snapshot clean-up removed (found by the review of PR #256) | **Putting back**: 407 in 256 companies from the runs' backups (`statements-backfill --put-back-ratings`, 50 a run, backed up); **Done 31 Oct ~00:20 IST: 407 put back in 256 companies** (runs 1-6: 63, 82, 97, 75, 84, 6; run 6 41099900518, backup backup/statements-backfill-20261030T181741Z/); 115 file-covered AI balance snapshots dropped on the way. Checked on 570004's live company API: the ICRA BB+ (Negative) snapshot is back | Next: the file-covered drop over all companies, dry run with the count first (TODO 141), in the same statements-backfill as the Q1FY24 fill and the Borrowings fix (one dry run, one count) |
| 2 | 20 live results cards on the fact sheet (CARD_FACT_SHEET, on 16:00 IST) | Scheduled 31 Oct ~07:18 IST | Blind-score; off again if worse |
| 3 | NUMFIRST_STOP_EARLY (on ~19:26 IST) | Live | 31 Oct ~11:30 IST: the first 20 live results filings it read, revenue and total income against the file; any wrong, off (repository variable = 0) |
| 4 | API OCR readers on the hard set (Mistral OCR, NVIDIA nemotron-parse 1 and 2; #257, #258) | Scored (PDF session): nemotron-parse 185 right / 1 wrong / 154 none of 340 after its guards (best single reader; numbers-first then nemotron 294/0/46, in-sample); out of sample (run 41077643109) 103 / 5 / 444 of 552. Mistral OCR answered nothing (429 on the free plan), nemotron-parse-2.0 502, nemotron-3.5-parse 404 | The PDF session decides whether nemotron-parse joins a live path (off, measured, owner) |
| 5 | Card model grid (TODO 142) | Trial route has MiniMax M3.1 Flash (NVIDIA), Qwen 3.8 27B and gpt-oss-120b (Groq), each answered a tiny request (run 41062958287); Kimi K2.6 404, Nemotron 3 Ultra out (53-58% WRONG measured) | **Measured 30 Oct 20:41-22:31 IST: no new model can write a card on its free tier.** Eight fact-sheet-ab runs on the same 10 filings made 0 cards: MiniMax M3.1 Flash and Mistral Large 4 (NVIDIA) 300 s timeouts, Nemotron 3.5 Super VL cut off at its token limit, Qwen 3.8 27B and gpt-oss-120b (Groq) over the per-minute token limit (the card prompt is larger than Groq's free minute). The grid goes on with today's writers only: prompt current vs strict x temperature (item 6 first) |
| 6 | Card text strictness (TODO 142, CARD_TEXT_SUPPORT, off) | In-sample 12 of 23 targeted WRONG dropped, 19 true items dropped too (2.7%). **Out of sample, 31 Oct (release-check text_support, run 41100996875): over 9,249 stored cards it would drop 4,922 items on 3,341 cards (36%)**: track_next 2,191, core_catalyst 1,264, why_it_matters 647, notable_changes 604, what_happened 126, key_numbers 90. Many drops are on ordinary words the filing does not use ("acceleration", "compared"), so it is far too strict as built | Stays off. Next: blind-judge the 60-item sample (artifact `release-check`, text_support-blind.json; the judges need the filings' stored text, R2 text/<news_id>.json.gz, a small export job), then narrow the word check to names, dates and counts. **Narrowed 31 Oct ~19:55 IST (#301, still off):** by default only names, dates, small counts and the driver words kept checked on purpose (capacity, passengers, volumes, plants, subsidiaries, observations, schemes); one unprinted name drops an item, an item's long first word counts like an ordinary word (two misses drop). `CARD_TEXT_SUPPORT_WORDS=1` gives the old every-word check. Next: release-check `ids=text_support` from #301 (the lead runs it), then a blind read of the drops |
| 7 | Chart-label rule for call memory (TODO 144, owner "Do it") | Built behind CALL_MEMORY_GEOMETRY (off). **Re-measured 31 Oct ~00:30 IST on a fresh blind-judged set** (the 30 Oct set was lost with that session's scratchpad; now kept in docs/bench/geometry/judged-2026-10-31/): v2's 293 deck points, 27 WRONG. Rules of 30 Oct: WRONG 23 of 27 dropped, RIGHT 25.2% dropped; rules of 31 Oct (units and filler never labels, prose left alone): WRONG 23 of 27, RIGHT 22.4%. Bar: all WRONG, RIGHT at most 3%: far off | **A tuning round with a held-out set (31 Oct ~01:00 IST): held-out 4 decks, WRONG 7 of 10 dropped, RIGHT 13.2% dropped** (tune decks 6.7%, so part overfit; branch geom-tune, not merged). Word positions alone cannot reach the bar: swapped pie labels and a figure of another measure look the same on the page as right points. **Owner's call:** (A) stop here, the switch stays off; (B) a vision step that reads the chart (cost: one AI call a chart slide); (C) change the call-memory prompt so it keeps no figure from a chart unless its label is printed beside it, then re-judge (lead: C first, it is free) |
| 8 | Call memory v2 prompt (TODO 101) | **Measured 31 Oct ~00:30 IST: 27 of 293 deck points WRONG (9.2%)** by three blind judges (ESAF 9 of 71, MTAR 7 of 33, Welspun 7 of 32, Thyrocare 3, GK Energy 1, four decks 0); nearly all a chart or pie figure paired with another bar, year or segment. The 30 Oct count (6 of 146) was a smaller sample. The owner's bar is 2%: not met, so the prompt is not switched | **Option C measured 31 Oct ~01:00 IST: no gain.** The v2 prompt plus a chart rule (v3, run 41103785967, same model and decks): 27 of 282 WRONG (9.6%). Found: every WRONG point of both sets is a quote assembled from words across a slide (v2 27 of 27, v3 25 of 27); 40% of RIGHT points are assembled too, so dropping them costs too much (docs/bench/geometry/judged-v3-2026-10-31/). **Owner's call:** (A) keep v2 off as now; (B) a vision read of the slide only for assembled slide quotes (about 40% of deck points; one free-tier call a slide); (D) a stronger model for decks (Gemini Flash's ~20 a day) |
| 9 | Press release into the results card and memory (TODO 135; owner Yes) | Built 30 Oct (PR #269), switch RESULTS_PRESS_RELEASE off | Measure on/off on live results filings, then the owner's switch |
| 10 | Deck and call cards lead with what changed (TODO 136; owner Yes) | Waits for call memory | The owner's 34 example cards are in docs/design/card-examples/ (never ask again) |
| 11 | Smaller: PBT definition for numbers-first (TODO 143, later: no live path uses it); stock-page items (Q1FY24 gap: fixed, PR #271; stale standalone and overdue guidance: audited on 20 live pages 31 Oct, docs/audit/stock-pages-2026-10-31.md; **B1 (overdue counted from the results due date, 79 of 150 rows were early), B3 (no deadline before the day it was said, December year ends) and A2 (page basis from headline results) merged 31 Oct, PR #277**; left: A1 (ADANIENT's standalone block), A4 (mixed-basis metric entries), B2 (no verdict after the actuals: a no-AI sweep), B5 (fragments, duplicates); bank/insurer tables TODO 129); the 47 companies with no stored facts; XBRL extras' second group (done, PR #269); Borrowings read as 0 from annual-report balance sheets (TODO 129: fixed in PR #273, 187 pairs right, 0 broken); raw XBRL expiry check (TODO 139: merged PR #273; **first run 31 Oct, 41145772223: 47,079 raw files, 45,152 with their facts copy, 293 superseded by a later file, 220 with no results, 1,414 holding results with NO facts copy** (mostly Q2FY24-Q4FY25; 10 are Q2FY27, so the live path seems to store some raw files without their facts: to look into). The full xbrl-facts run now going reads stored raw files first, so run the check again after it; the rest need `xbrl-facts` over those companies before ~Apr 2027) | Open | In turn |
| 12 | **REITs and InvITs on the Results page** (owner, 30 Oct 2026: "REITs need to check XBRL"). 3 of the 500 Nifty 500 members are REITs (Embassy Office Parks, Brookfield India, Bagmane Prime); the page shows 497 of 500 and says so | **Step 1 built; the 100-file test read 31 Oct 2026 (run 41150836776, 06:20 IST: 27 trusts, 54 rows).** Against Screener: Embassy Mar, Jun and Sep 2026 equal; Brookfield sales equal, profit is the unitholders' share (Jun 2026 179.8 against Screener's 221.3 total, 41.5 minority), operating profit Jun 2026 713.6 against 701 (open); Bagmane Jun 2026 equal within 1 Cr. **Owner decisions, 31 Oct 2026:** profit stays the owners' (unitholders') share, as for companies; a quarter with zero sales (Bagmane Mar 2026, before it held its assets; Screener shows it too) is left out and its stored row pruned; the full run goes ahead. **Measured 31 Oct 2026:** NSE's list holds trust filings from Sep 2025 only (193 with no dates, with `from_date` 01-01-2024, and for `symbol=EMBASSY` alone 12, the same five periods), so year-ago growth starts with Sep 2026; Jun 2026 has no year-ago file on this list. **Full run 31 Oct 2026 06:38-06:48 IST** (run 41153853516): 185 files (100 stored, 85 downloaded), 28 with no sales left out, 93 rows; Bagmane Mar 2026 gone, Embassy Sep 2026 has its year-ago growth (sales +15.9%, profit +258%). **Found by it (published wrong, fixed at once):** six trusts not on BSE (Nxt-Infra, NDR, Oriental, SEIT, Shrem, TVS) have ScripCode 000000 in their files; keyed by it, they overwrote each other's quarters under one company shown as Nxt-Infra Trust. They are now keyed `NSE:<symbol>` and the 000000 rows are pruned by the next run. **Re-run 07:05 IST, then two more fixes:** the 000000 `companies` row (named Nxt-Infra) shadowed `NSE:NXT-INFRA` in the symbol lookup, so the run now removes it (through `companies_prune` and its guards); TVS and SEIT files fill the owners' and minority shares with 0 (TVS Jun 2026: profit 17.74 Cr, owners 0, minority 0), so the owners' share is used only when it and the minority's add up to the profit, as `screener_view` already does for companies. **Measured 30 Oct 2026 (the call is found):** NSE's own page loads REIT/InvIT results with `/api/corporates-financial-results?index=reitsinvits&period=Quarterly[&symbol=X]` (read from its script `corporate-filings.js`, function `loadFRInvitsreits`); the earlier tries (`reit`, `invit`, `reits`, `invitsreits`) failed because NSE answers any unknown index name with the same `no data found` (control: `index=zzzgarbage`). It returned 193 filings from 27 trusts (REITs and InvITs), Embassy 12, Brookfield 9, Bagmane 3, each with an `xbrl` file and an `ixbrl` page on nsearchives (Integrated Filing names, `consNoncons`, `periodEnded`, `typeOfSubmission` Original/Revised). One Embassy file read (Sep 2026, 392 KB, 306 numeric tags): the same Ind AS tags as companies (RevenueFromOperations, FinanceCosts, ProfitLossForPeriod, EPU) and values equal to Screener's (revenue 1,303 Cr, profit 831 Cr), plus REIT tags: NetDistributableCashFlows, DistributionPerUnit, NetAssetValuePerUnit, NetOperatingIncomeMargin, NetBorrowingsRatio, DebtEquityRatio, DebtServiceCoverageRatio. None of the three is in our companies table (the universe is NSE's equity list), and we had never called this index, so the XBRL exists and has not been downloaded. Screener (measured) links each quarter to a BSE announcement PDF, not XBRL | **Plan (owner agreed, 30 Oct 2026).** Practice measured or searched the same day: Screener.in (measured: pages for all three, filed under Realty > Real Estate Investment Trusts (REITs); the ordinary table of Sales, Operating Profit, OPM, Net Profit and EPS, Embassy to Sep 2026, Brookfield to Jun 2026, Bagmane three quarters; no distribution figures in its tables; a Raw PDF link per quarter). NSE's Nifty 500 list (measured 30 Oct 2026) holds all three. Industry practice (web search, no official SEBI text read): investors read net operating income, net distributable cash flow (NDCF), distribution per unit and NAV, not net profit; the 90% payout base is given as NDCF by some sources and taxable income by others (**assumption** until the regulation is read). **Step 1 (built):** `reit_results.py` and `reit-results` (Maintenance, `file_cap` required, files kept in `raw/reit-xbrl/`); sales, operating profit and profit by screener's rules (Embassy Sep 2026: 1,303 / 980 / 831 as Screener); trusts are in `companies`, neither ordinary companies for EBITDA statistics nor financials in the cuts. Next: the 100-file test (`file_cap` 100), read it against Screener for Embassy, Brookfield and Bagmane, check the R2 lifecycle covers `raw/reit-xbrl/` (the 180-day rule is for `raw/xbrl/`), add market cap for trusts (none yet: the market-cap filter leaves them out), then the daily refresh (a step in the pipeline run) once the test is read to the universe, revenue, operating profit and profit as Screener shows them, kind `reit` on the page (left out of EBITDA statistics like banks), then drop the "not covered yet" note. **Step 2:** NDCF, distribution per unit, NAV per unit and net borrowings ratio from the same file as their own columns. The first fetch of a new NSE path runs on 100 files (`file_cap` 100, files kept) |
| 13 | **Results page audit** (owner, 31 Oct 2026: "full page audit ... code, calculations (must be standard practice), UI/UX ... carry out all the improvements") | **Fixes built (this PR); re-audit after everything is live (owner: start only then).** | Three blind audits 31 Oct (calculations, 40 companies against Screener, UI/UX at 1440/1024/390) and a sweep of the live table (16,131 rows, 16 quarters). Fixed and shipped at once: 204 quarters with a profit of 0 (filler owners' share, #286). This PR: "X of Y" over comparable companies (401 of 611 read 65.6%, of 553 comparable 72.5%), loss to profit over the loss-makers a year ago, "best median in 8 quarters" only at 80% index coverage, coverage beside index medians, the median says whom it leaves out, no all-companies revenue total (banks' interest earned), NM past +999% and for margins outside +-100%, no margin change in bp on a meaningless base (SADHNANIQ +64,681 bp), turns sort after every %, the Nifty 500 progress card removed (owner), phone header fits with Export, peek panel as a dialog, empty-result card, Indian grouping, wording. **Follow-ups (owner: build):** PAT before exceptional items and the 5 NBFC-template non-financial companies (Westlife, Kirloskar Industries, HealthX, RTN India, Indiabulls Ltd) as companies: built (follow-up PR). Restated year-ago comparatives (HUL Q2FY26 16,241 as filed, 15,919 restated): **not buildable from XBRL, measured 31 Oct 2026**: NSE's results XBRL holds the current quarter only (HUL Sep 2024 consolidated file: one quarter context, 2024-07-01 to 2024-09-30; 13 fixture files incl. Q2FY27 the same); the restated figures are in the PDF only, and the PDF reader is not reliable enough to change growth figures (19% right on the hard set, 27 Oct). Growth stays against the year-ago quarter as first filed. Measured and genuine (filed so; Screener equal): Hindustan Oil Q4FY26 revenue -205.89, Unitech EBITDA above revenue, Sadhana -628.89% margin |
| 14 | **Results re-audit fixes and site-wide profit rules** (owner, 31 Oct 2026: re-audit after everything live; statements site-wide) | **Built (this PR); after merge: `statements-correct` dry run, read it, then `apply`, then `results-table`.** | Three blind re-audits 31 Oct. Shared profit-line rules in `screener_view.corrected_pl`, applied at write, on read and by the new `statements-correct` pass: owners + minority must equal the total (ATUL Q2FY26 owners 87.95 against total 182.37, minority 3.13, NSE's own file; Q2FY27 showed +77.1%, truth about -13%), a filler owners' 0 is the net profit, a corporate profit on the wrong side of zero from PBT - Tax by more than max(5 Cr, 50%) is PBT - Tax (APARINDS Q1FY27 -138.56; four sites 467.45). Insurers on the NBFC template as insurers (MFSL); banks get Screener's Financing Profit; sorts: NM after meaningful rows, falls first when lowest first, default market cap; momentum not comparable past +999%; table scrolls in its box (overlapped at 1024 px); phone Filters/Sort bar below the site header. **Owner decisions 31 Oct:** keep the owners' share; yes to restated year-ago figures (filing PDF text, a move past the 25% band only when it equals Screener's); banks as Screener; match Screener on every row of all three statements (screener-rows run 41164053629: quarters 93-98% exact a row, annual Expenses/Operating Profit 76%, Other Income 74%, lenders' Financing Profit 32%, balance sheet Other Liabilities 79%, Borrowings 85%; TMCV's gap is the Other expenses breakdown row "Fair value (gain)/loss on equity investments", 708 Cr Q2FY27, out of Screener's Expenses; the rule work is next). Table redesign mockups A/B/C wait for the owner. |
| 15 | **Statements matched to Screener, all three, FY23 on** (owner, 31 Oct 2026: "match Screener except their mistakes"; cut-off FY23) | **Batch 1 built and measured (this PR); after merge: statements-rebuild (dry run, read, apply), statements-correct, restated-pdf (dry run on 8, then top 500), results-table.** | screener-rows (top 500), exact share of compared pairs: baseline run 41164053629 92.13%, batch 1 run 41171327785 92.27% (183 pairs, no row worse); FY23 on: quarters 96.5%, annual 87.5%, balance 91.6%, cash flow 92.7%. Kept: associates' share follows the company's presentation on quarters (segment PBT = PBT + share: in; = PBT: out; no segment: in, out measured 95.0% -> 90.4% PBT, run 41172104462), fair value on investments out of Expenses in results files (TMCV), right-of-use rows under financial assets in Fixed Assets, lease liabilities however spelt. Dropped by measurement (run 41166426469): P2 on annual reports (Grasim FY23 8,736.95), exploration/biological assets, deferred-tax netting on every basis, associates on years. Not copied (Screener inconsistent, nothing in the filing tells the cases apart): associates on years, loss on sale of assets for IndiGo/ONGC, FX effect in cash flow (1,062 in, 102 out), leases in old borrowings. Owners' share rule guard: a minority share as large as the whole profit is the slip (FINCABLES, ABREL); CGPOWER Q2FY26 18.24 -> 284.29 (Screener 284). Restated year-ago figures from the filing PDF (F226). Coverage (measured): NSE files mostly stored; 1,414 stored results files had no facts doc (xbrl-facts dry run fills them); 25 banks' Q4FY23 files read nothing (fixed in #292, below); ~71 companies have no filing before listing (ceiling); `statements-backfill` stopped at 250 of ~1,900 companies on 30 Oct, finished by statements-rebuild. |
| 15b | **Statements batch 2 and the legacy-file fix** (31 Oct 2026, ~12:45 IST) | **#292 merged (bank and NBFC balance sheets, investment rows, legacy undeclared contexts). On the branch, to measure and merge: bank exceptional loss in Expenses (trial: SBI FY24 7,100.31 mended, HDFC cons may break), HDFC stock options from the balance-sheet note and Screener's March-only move (all HDFC Reserves and Other Liabilities rows equal Screener's in the files, except cons FY25 Other Liabilities +307), annual Screener tie-break in the backfill, stock page growth/ratios/chart/P/E/summary read the statements, year-by-source and sub-row columns in screener-rows. Then statements-rebuild (this session owns it; the lead session stays off), statements-correct, results-table.** | Measured: batch 2 (run 41174640014) lenders' balance sheets 3,958 rows newly compared, 82.0% exact; corporate rows: 51 mended, 4 broken (JSW CCD, Union and PSB Equity Capital). Legacy files: NSE's pre-integrated files tag figures to OneD/FourD/OneI without declaring them; 4,034 stored documents of 1,856 companies (mostly Q4FY21/Q4FY22, some Q4FY23) kept 102,696 of 886,258 facts; re-read from the stored raw files (xbrl-facts --reread-legacy, dry run 41176203821, apply dispatched). Match by year (run 41174640014): annual FY23 87.8%, FY24 87.8%, FY25 86.5%, FY26 87.9%; balance 89.7/90.8/89.3/92.2%, FY27 92.7%; cash flow 91.8/93.2/90.2/95.4%; quarters FY26 95.9%, FY27 98.4%. Not in the filings (ceilings, measured): banks filing a direct cash flow have no depreciation (Bank of Maharashtra), bank CWIP is inside FixedAssets (87% of bank Fixed Assets gaps = Screener's CWIP), ICICI/SBI consolidated March fixed assets and minority interest come from the annual report; Union and Canara FY25 Deposits-to-Borrowings moves (37,502 / 27,021) are in neither the XBRL nor the FY25 annual report (assumption to check: the FY26 report's restated comparatives). Annual P&L: where Screener's year = its four quarters we match 86%, where not 47%. Drill-down PDFs kept (keep-annual-pdfs --years): 6 banks x 2 years, 34 gap companies x 3 years (file cap 100). |
| 15c | **Banks' annual-report PDF reader, TODO 148** (31 Oct 2026, ~20:15 IST, co-lead) | #299 measured and merged: 100 BSE reports kept (no refusal), screener-rows 80 pairs mended, 0 broken; Bank of Maharashtra FY25/FY26 Depreciation, Expenses, Financing Profit now equal Screener. Next: the full bank-pdf-read (no file cap), then a statements rebuild so the stored statements take the readings. Open: City Union Bank and Bank of Maharashtra FY23-FY25 (columnar text layer), UCO's 0.0 file depreciation (owner or lead to decide). | Full run and rebuild: co-lead |

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
