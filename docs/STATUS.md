# Status: the one current page

Read this first. It replaces the "pending", "status" and "next" parts of `PLAN.md`, `HANDOVER.md`, `TODO.md`, `TASKS.md`
and `docs/audit/actions-pending.md`. Those files stay as history; do not work from their lists. Keep this page current:
when something changes, change it here, in plain English, with the date and time in IST.

Last updated: 27 Oct 2026, 21:45 IST.

## 1. What runs

| What | How | Since |
|---|---|---|
| Cards | One run, `pipeline.yml`, scheduled every 15 minutes; GitHub starts it about every 35-45 minutes. Today's new filings first, then the older work (the live window's earlier days, catch-ups, memory sweeps, backfill) in slices of about 3 minutes (10 for the backfill), and today's new filings are looked for again after each slice | 27 Oct, PR #190 (the quick run `pipeline-today.yml` is gone) |
| Switches | One list, `pipeline/config/switches.toml`, for every job. A repository variable of the same name wins over the file in every job (`0` turns one off). CI runs the tests with the switches off and with the file's switches on | 27 Oct, PR #190 |
| Site | https://insiders.reply-bd3.workers.dev; `deploy-web.yml` deploys every merge to `main` | 20 Oct |
| Maintenance | `maintenance.yml`, started by hand, one command a run (no AI) | |
| Daily card audit routine | **Off** since 24 Oct night (trigger `trig_01JtXb9RSm63zmvoar8VyXsx`, disabled). The 26 and 27 Oct audits were done by hand | owner to decide (section 5) |

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
   figures, no refusal, stopped at its 500-file cap. Batch 2 (run 40524728754) started 20:18 IST. Each further batch
   needs the owner's go. Risk the owner accepted: a wrong BSE figure (about 1 in 100 in the checks so far, e.g. Kovai
   Q4FY26) goes into memory unchecked; screener and tijori comparisons are the check.
3. **After the full BSE download: the BSE fill keeps its record as it goes and compares with memory before writing**
   (today the list of what it wrote is saved only at the end, and a refusal or a kill loses it).
4. **Before any `refresh-card-blocks`: a dry run** to list what `CARD_ONE_BASIS` now changes on stored cards (a refresh
   now applies it; before 27 Oct it never did).
5. **FROM_ZERO step 2** (owner: yes to A-H): F first, a reliable PDF reader for results statements, scored on a
   hand-checked answer key of about 50 statements with pass marks set before scoring (`docs/FROM_ZERO.md`, TODO 112).
   Then B on (`XBRL_FILER_CHECKS`, after its on/off over stored memory, TODO 111), C, D, E, G.
6. **A way to take a proven-wrong figure out of memory in code** (not by hand). Today `bse_gap_fill.KNOWN_WRONG` only
   stops a future fill, and nothing removes a wrong figure already written.
7. **The docs clean-up the owner planned for later** (one doc per purpose, the one-off tools out of the live code); not
   started.

Not in the order, waiting where they are: call memory v2 (a second blind sample, then the owner's go); the screener
referee run 40513449694 (running); screener-explain run 40498040302 finished 27 Oct, and its planned PDF check on the
unexplained rows is not started (owner to say).

## 4. Known problems (found 27 Oct, not fixed)

- `audit-export.yml` and `maintenance.yml` commit their exports to `claude/gracious-goodall-jn9buu` (a parked branch)
  unless the repository variable `AUDIT_BRANCH` is set.
- The shadow critic is off (D41) but `audit-export.yml` still exports its verdicts every morning at 09:51 IST.
- `FILE_CAP` (the 100-file first test) is wired only into the `run` and `textback-bse` jobs of `maintenance.yml`, not
  into seed-memory, memory-gaps-fill or text-backfill.
- `xbrl.eps_signs` still flips an EPS sign from one source (the same file's profit sign).
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
  Commits since PR #190 leave the model name out.
- From earlier: B3 (held cards hidden, flagged or approve/reject), A2/A3 (backfill pace, re-writing cards after it),
  B5 (prices from bhavcopy), G9 (a Cloudflare rate-limit rule), Workers Paid renewal before about 21 Nov (otherwise set
  `D1_PLAN=free`; reminder `trig_0197dpX6XnQXDm8B3vxWAUC8`, 18 Nov). G8 (delete the BSE client) is dropped: the BSE
  adapter is in use.

## 6. Facts that changed (older files still say otherwise)

- BSE answers GitHub's machines through the ported adapter (`adapters/bse.py`; measured 25 and 27 Oct); a bare probe got
  403. The pipeline's daily path is still NSE only; BSE fills memory gaps.
- Branch: the session's own branch (now `ccr-e9a25af8-4vz8up`); PRs to `main`; after a merge the branch restarts from
  `main`. `claude/gracious-goodall-jn9buu` is parked.
- Decisions run to D43 and findings to F222 (`docs/TRACKER.md`).
- Test count: 2,062 passed, 7 skipped (27 Oct), both with the switches off and with the file's switches.
