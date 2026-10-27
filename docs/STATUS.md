# Status: the one current page

Read this first. It replaces the "pending", "status" and "next" parts of `PLAN.md`, `HANDOVER.md`, `TODO.md`, `TASKS.md`
and `docs/audit/actions-pending.md`. Those files stay as history; do not work from their lists. Keep this page current:
when something changes, change it here, in plain English, with the date and time in IST.

Last updated: 28 Oct 2026, 01:35 IST.

## 0. How the lead session works (owner, 27 Oct 2026, ~22:15 IST)

Freedom inside a fence, with a short daily message to the owner.
- **Without asking:** code fixes with a test and an independent blind review (a separate subagent, not the smallest
  model), merging once CI is green, read-only jobs, the BSE fill batches (stop at once on any refusal), keeping this page
  current.
- **Ask the owner first:** anything that costs money, keys, deleting data, account or repository settings, switching on a
  switch that changes what cards say before it is measured, changing the go-live bar, big design choices.
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

1. **Blind audit of about 50 cards written by the single run** (28 Oct afternoon IST, once enough new cards exist):
   the first measurement of the 13 switches. Independent reviewers, the fix author does not grade.
2. **BSE memory fill, batch by batch** (owner, 27 Oct). Batch 1 (run 40504758920): 49 companies, 321 quarters, 8,324
   figures, no refusal, stopped at its 500-file cap. Batch 2 (run 40524728754): 43 companies, 277 quarters, 7,277
   figures. Batch 3 (run 40541696607, done 23:54 IST): 40 companies, 210 quarters, 5,444 figures, 428 BSE files kept,
   no refusal; 157 quarters skipped because BSE's basis differs from memory's, 148 held, 16 fetches failed (NBFC files
   that came back empty). Batch 4 (run 40561999277) started 00:09 IST 28 Oct. The owner said to run the rest back to
   back (27 Oct), stopping at once on any refusal. Risk the owner accepted: a wrong BSE figure (about 1 in 100 in the checks so far, e.g. Kovai
   Q4FY26) goes into memory unchecked; screener and tijori comparisons are the check.
   Checked 27 Oct night (`docs/bench/bse-fill-batches-1-2-check.md`): revenue and profit agree with screener in 98-99%
   of 1,776 pairs; of 89 differences read in the company's PDF, BSE right 82, **wrong 4** (Eco Recycling Q4FY25 profit,
   Vadilal Enterprises Q3FY25 profit, Pradeep Metals Q4FY26 profit, Veljan Denison Q3FY26 EPS: the company's own XBRL
   on BSE differs from its own PDF; tax sign flipped, prior-year tax left out, a discontinued line added, standalone
   EPS in the consolidated file). The four are in memory now; taking them out waits for item 6 and the owner.
3. **After the full BSE download: the BSE fill keeps its record as it goes and compares with memory before writing**
   (today the list of what it wrote is saved only at the end, and a refusal or a kill loses it).
   First half done (branch `bse-fill-record`): after each company the fill appends its rows to the CSV and rewrites the
   summary JSON (`bse_gap_fill.Record`; a dry run records what it would write; a refusal keeps what was filled before it).
   The upload step already runs `if: always()` after the fill step's own `timeout-minutes`. Second half (compare with memory
   before writing) is still open.
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
   follows the printed page). In review now.
6. **A way to take a proven-wrong figure out of memory in code** (not by hand). Today `bse_gap_fill.KNOWN_WRONG` only
   stops a future fill, and nothing removes a wrong figure already written.
7. **The docs clean-up the owner planned for later** (one doc per purpose, the one-off tools out of the live code); not
   started.

Not in the order, waiting where they are: call memory v2 (a second blind sample, then the owner's go); the screener
referee run 40513449694 (finished 28 Oct 00:11 IST at its 5-hour limit, results saved: 5,707 of 16,344 pairs decided by
NSE's own XBRL; memory matches the file in 5,480, screener in 21, neither in 10, no file 196; memory and the file are not
independent, memory was built from it). The 31 where memory is wrong or unsure: 12 EPS signs flipped (ALEMBICLTD Q4FY26,
APOLLOPIPE Q2FY26, PRIVISCL Q1FY25, RPOWER Q2FY25, SILVERTUC Q1FY27, MOLDTECH x5, NITCO Q4FY24, MAXESTATES Q2FY24), 9 EPS
stored as 0 (AHLUCONT, ARVIND, BGRENERGY, PILANIINVS, SKFINDIA, HARDWYN), DOLPHIN revenue and profit ten times too big
(Q2FY24, Q4FY24, FY24) and two lender revenue definitions (GEOJITFSL, SHRIRAMFIN): they wait for item 6; screener-explain run 40498040302 finished 27 Oct, and its planned PDF check on the
unexplained rows is not started (owner to say).

## 4. Known problems (found 27 Oct, not fixed)

- Fixed 27 Oct night: the audit exports are kept as a GitHub artifact (`audit-export`, or the command's name) and are
  committed only to the branch the repository variable `AUDIT_BRANCH` names (before, a parked branch); the critic's
  export runs only with the repository variable `CRITIC` at 1.
- Fixed 27 Oct night: the `file_cap` input (the 100-file first test) now reaches every job that marks the cap: seed-memory,
  memory-gaps-fill, text-backfill and the PDF ensemble's download, beside `run` and `textback-bse`. Empty means no cap.
- `xbrl.eps_signs` still flips an EPS sign from one source (the same file's profit sign). Measured 28 Oct: 12 of the 31
  memory errors in the screener referee are flipped EPS signs.
- Fixed 28 Oct, 01:30 IST (PR #200): the "company-reported" label on a headline or key number is no longer added to a
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
