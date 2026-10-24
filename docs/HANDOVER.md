# Handover: state of the platform and the work in hand (24 Oct 2026, 16:45 IST)

Written by the lead cloud session at the end of 24 Oct 2026, before the owner moves to another account. A new session
should be able to carry on from this file alone. It links to the detailed records rather than repeating them.

Read in this order:
1. This file.
2. `CLAUDE.md`: the rules.
3. `docs/PLAN.md`: the "Pending work" list.
4. `docs/audit/ledger.md`: every change and its measured effect.
5. The latest `docs/audit/live/<date>-audit.md`.

---

## 0. The two main tasks (owner, still open)

These are the platform's two jobs until go-live. Everything else serves them.

### Task A: the right-card requirement (the go-live gate)

**Target (owner, 24 Oct 2026, D42; replaces "95% RIGHT" of 18 Oct):** WRONG on the checked face at or below 5% of
published cards, read pooled over days with the 95% interval's top at or below 5% (`rates.py`), when an independent
blind reviewer checks them against the filing PDF and the company's memory. The checked face is the headline, the
quoted points, the tables and blocks and the key numbers; the model's interpretation sits open beside it in its own box,
"Our reading · not checked against the filing" (owner: kept readable), and the facts the checks could not quote sit
behind a tap; a fault only in those is MINOR (`reading_only`). The bar
is **not met** (21-24 Oct pooled: 22%, 17%-28%).

| Day | Audited | RIGHT | MINOR | WRONG | Right | Right or minor | WRONG |
|---|---|---|---|---|---|---|---|
| 21 Oct | 48 | 10 | 27 | 11 | 21% | 77% | 23% |
| 22 Oct | 60 | 24 | 24 | 12 | 40% | 80% | 20% |
| 23 Oct | 60 | 26 | 25 | 9 | 43% | 85% | 15% |
| 24 Oct | 65 | 25 | 25 | 15 | 38% | 77% | 23% |

**Reading the numbers:**
- WRONG has stayed between 15% and 23%. Each day's fixes remove the class that was found, but new filings bring new
  classes.
- MINOR is about 40% of cards and blocks "RIGHT" almost as much as WRONG does. MINOR is mostly unsupported causes,
  invented milestones, generous impact levels and loose labels.
- Reaching 95% RIGHT needs both:
  - WRONG down to ≤ 5%, through the audit-and-fix loop below;
  - the common MINOR classes removed, mostly in the prompt and the checks.

**Short vs long prompt (A/B, since 21 Oct):**
- Short: 46 cards, 9 WRONG (20%).
- Long: 139 cards, 27 WRONG (19%).
- No difference so far. Keep scoring it; ~30% of live filings use the short prompt.

### Task B: the wrong-card audit loop (run after every analysis)

This is how WRONG comes down. Each step was agreed with the owner, and none may be skipped.

1. **Audit.** Independent, blind subagents review live published cards, newest first:
   - at least 20 cards a day, in the 4 runs at 10:07, 12:07, 14:07 and 16:07 IST;
   - plus the newest flagged cards on `/api/review`;
   - plus a sample of held cards once a day.

   Each reviewer downloads the PDF, extracts its text and reads `/api/companies/<scrip>` (memory and earlier cards). It
   then judges the card's face RIGHT / MINOR / WRONG, with an error class and the wrong points verbatim. The fix
   author never grades their own fix.
2. **Correct.** Take the commonest WRONG class with a root cause in code or the prompt and find that root cause in
   code, from the logs and stored data, not guesses (`docs/DATA_QUALITY.md`). Fix the class, not the card, and add a
   test that fails on the old code.
3. **Check how many other cards the new rule affects (on/off, no AI).**
   - Run the old and new code over all stored cards: the feed cache, `/api/companies/<scrip>`, the PDFs where needed.
   - List every card that changes and how: became right, stayed wrong, or became wrong.
   - **Ship only if more cards become right and none become wrong.**
   - An independent subagent blind-checks a sample of the changed cards. This is mandatory for any change that makes a
     check accept more (owner: "any fix that makes a check accept more gets this same audit (on/off over stored cards,
     then an independent sample) before I call it done").
   - Examples:
     - F109's first draft would have changed 47 cards; the blind check found the 10 it sampled all right as they were,
       so the rule was narrowed to 3.
     - F108's first regex flagged 390 texts; it was tightened to 3.
4. **Apply.**
   - PR from `claude/gracious-goodall-jn9buu` (since 24 Oct; was `claude/nice-goodall-ta0sxs`) to `main`; merge when CI is green (the owner's standing approval,
     `docs/APPROVALS.md`).
   - Then dispatch the refresh or re-run that heals stored cards, e.g. `maintenance.yml refresh-card-blocks`, one
     dispatch at a time, with D1 writes below 85,000 a day.
   - Never hand-edit or hand-delete stored data.
5. **Record.**
   - Verdicts go to `docs/audit/live/<date>-audit.json`.
   - The change row and day totals go to `docs/audit/ledger.md`.
   - Add one line to `docs/OPS.md`.
   - Add a TRACKER `F<n>` row.
   - Update SETUP's test count.
   - At 16:07, write the day summary at the top of `docs/audit/live/<date>-audit.md`.
6. **Next day:** the new audit fills the previous change's "after" figure in the ledger.

**Reading the numbers (code survey, 24 Oct 2026).** One day is 60-75 cards, so a day's WRONG share carries a 95%
interval of about +/-10 points (24 Oct: 23%, 15%-35%). A day-to-day move says nothing about a fix: judge a fix by its
on/off over stored cards, and the audit rate over pooled days with intervals:
`python -I pipeline/scripts/daily_audit/rates.py --window 3`. 21-24 Oct pooled: 218 cards, WRONG 22% (17%-28%), right
39% (32%-45%); short and long prompts 21% and 23%, no difference; the prune removed 32 true points of 34. The go-live
bar is shown met only when the pooled WRONG interval's top is at or below 5%.

---

## 1. Owner rules (verbatim where quoted, all still in force)

- "no more ai usage for testing as we will review live only cards". Testing calls no AI. Prompt changes are measured on
  live cards only.
- "any fix that makes a check accept more gets this same audit (on/off over stored cards, then an independent sample)
  before I call it done".
- "we are using AI, so we need to accept AI's analyisis based on details we provide, second rounding of number etc are
  not errors". Rounding and reasonable interpretation are not errors.
- **Cost:** $0 a month.
  - Cloudflare Workers Paid ($5, D40) is the only subscription.
  - The prepaid DeepSeek balance (D24) is for the backfill/seed only.
  - Never add a paid route to the daily path.
- **Keys:** keys live only in the owner's keys file outside the repo. Never print, log or commit one.
- **Stored data:** never edit stored data by hand and never hand-delete live data. Fix the class in code and re-run
  (`docs/DATA_QUALITY.md`).
- **Git:**
  - Branch `claude/gracious-goodall-jn9buu` only (owner, 24 Oct 2026; was `claude/nice-goodall-ta0sxs`).
  - `git pull` before editing.
  - Never force-push or rewrite pushed history.
  - Run `git diff --check` and check for conflict markers before committing.
- **Commit text:** no AI model names or IDs in commits, PR text or code.
- **BSE:** don't work around BSE's firewall. BSE is off the online path (NSE only, D34).
- **Data-source claims:** every claim in the docs about a data source carries "measured <date>: <example>" or
  "assumption".
- **Approvals (`docs/APPROVALS.md`):** the lead may merge its own green PRs and dispatch workflows. Anything that costs
  money, touches keys, deletes live data or changes account settings goes to the owner.

---

## 2. The live system

| | |
|---|---|
| Site | https://insiders.reply-bd3.workers.dev (Worker `insiders`, D1 `bse-index-nse`, R2 `bse-intelligence`) |
| Pipeline | `.github/workflows/pipeline.yml` on `main`, cron `2,17,32,47 * * * *` (every 15 min, concurrency group `bse-pipeline`, never two at once); `run --mode all --time-budget 2400`; text cache restored and saved per run (`data/text_cache`, 8 days) |
| Deploy | `deploy-web.yml` deploys every merge to `main` |
| Maintenance (no AI) | `maintenance.yml` (`workflow_dispatch`, input `command`): refresh-card-blocks, refresh-summaries, both, export-held, export-critic, requeue-failed (`--ids`), apply-verdicts, seed-memory, fill-memory, fill-trades, release-pruned |
| Other workflows | `release-held.yml` (dry_run / plan), `d1-usage.yml`, market-data, nightly, the annual-report XBRL catch-up |
| Public API | `/api/system` (runs, queue, failures, D1 writes), `/api/feed?range=7d&limit=N` (`{cards, next_cursor}`; `card_json.grounding.prompt_variant`, `card_json.review.status` PRUNED/CORRECTED/HELD), `/api/cards/<news_id>`, `/api/companies/<scrip or symbol>` (`{company, cards, dossier, ...}`), `/api/review` (published cards the checks flagged; 51 on 24 Oct) |
| Owner API | `/api/owner/feed?held=only`, `/api/owner/review`, `/api/owner/cards/:id` (needs the owner token, which lives in the keys file) |
| Universe | 1,778 NSE companies ≥ ₹500 Cr (D31) |
| D1 budget | Workers Paid (D40), bought for one month on 22 Oct 2026 (owner, 24 Oct: "$5 plan for one month now"): the code's daily budget is 1.5M. **Before ~21 Nov:** the owner renews, or the repository variable `D1_PLAN` is set to `free`, which puts every job under the free tier's 100,000 writes a day (budget 80,000); left at the paid budgets on the free tier, D1 would refuse writes mid-run. Keep bulk dispatches near ~85,000 a day so either plan holds (`/api/system` → `d1.writes_today`) |

---

## 3. The scheduled routine, and what changes when the account changes

**Active (new account, recreated 24 Oct 2026 22:27 IST):** "Daily card audit (200 days, in the lead session)", trigger
`trig_01JtXb9RSm63zmvoar8VyXsx`, bound to session `session_01VQVLJ154mWQVPxa8jEJTWY`, the prompt below; first run
25 Oct 10:07 IST. The old account's routine `trig_016w88QsTBpwiUbY8a7PCmzC` (below) is the owner's to disable.

**Old account:** "Daily card audit (200 days, in the lead session)", trigger `trig_016w88QsTBpwiUbY8a7PCmzC`.
- Cron `CRON_TZ=Asia/Kolkata 7 10,12,14,16 * * *`; runs until 2027-05-08.
- It fires into this session (`session_01CKTcRXiDuaCJ9ffRDZzVvq`) on the **current account**.

**After the switch:** a session on the new account will not receive it. The new lead session should:
1. Get the repository attached. Read `mcp__claude-code-remote__read_documentation` topic `github.access`; the GitHub App
   must be installed for `hipareshpatel/Insiders`, with push access.
2. Recreate the routine with `create_trigger`, bound to the new session, using the same cron and the prompt below.
3. Ask the owner whether to disable the old routine on the old account. It would keep firing into a session nobody
   reads; it does no harm, but it is noise.

Disabled routines, kept for the record:
- `trig_01HBPHhE3BYZeXc6TDZkmJkq`: hourly checks, 23 Oct.
- `trig_01WKWMXqJgb1JxUQro2yENQP`: hourly audit, 22 Oct.
- `trig_01BewcoAbZh5c5aLgBUoMPu2`: the first daily audit. It ran in its own session, which could not push.

The routine's prompt, verbatim:

```
Daily card audit (owner, 20 Oct: 200 days, 10:07/12:07/14:07/16:07 IST, at least 20 cards a day; moved into the lead session on 21 Oct because routine sessions could not push). If today (IST) is after 2027-05-08, disable this routine and stop. Otherwise, in this session (git pull first; branch claude/gracious-goodall-jn9buu):
1. Published cards from /api/feed newest first, those not yet in today's docs/audit/live/<date>-audit.json (at least 5 a run): give them in batches to independent general-purpose subagents with pipeline/scripts/daily_audit/reviewer_prompt.txt (you do not grade your own fixes). Each downloads the filing PDF into its own new directory, extracts text with `python -I`, and judges the card's face (headline, points, tables, blocks, "Our reading", direction, impact) RIGHT / MINOR / WRONG with the error class (wrong_period, unit_scale, restated, standalone_consolidated, wrong_column, invented, arithmetic, direction, duplicate, event_type, memory, attribution, unsupported_cause, other) and a one-line reason. Record each card's prompt_variant (card_json.grounding.prompt_variant).
2. First run of the day: dispatch maintenance.yml export-held; review a sample of held cards (release candidate or not). (The shadow critic is off since 24 Oct, D41: no export-critic or critic scoring until it is rebuilt.)
3. /api/review: check the flagged cards the same way.
4. Fix: the commonest WRONG class with a root cause in code or prompt, with a test; on/off over stored cards (no AI) and ship only if more cards become right and none wrong; an independent subagent blind-checks a sample of the changed cards. Any fix that makes a check accept more gets that audit before it is called done. Re-runs or refreshes needed go to docs/audit/actions-pending.md or are dispatched one at a time (D1 writes below 85,000).
5. Save judgements to docs/audit/live/<date>-audit.json (each with reading_only: true when every fault is in "Our reading" or behind the tap), append the ledger rows (docs/audit/ledger.md: per change and the daily totals, incl. short vs long and WRONG on the checked face), commit and push.
6. 16:07 run only: the day's summary at the top of docs/audit/live/<date>-audit.md (audited, right/minor/wrong, WRONG on the checked face vs the 5% bar (D42), short vs long, fixes and their effect, held released, open classes) with the pooled rates and their 95% intervals from `python -I pipeline/scripts/daily_audit/rates.py --window 3` (a day alone cannot show a fix worked), then a short summary for the owner.
Rules: no AI for testing; never edit stored data by hand or hand-delete live data; $0 (no paid routes beyond the owner's DeepSeek seed use); no keys printed; no AI model names in commits or PR text.
```

**PR flow used every run:**
1. Commit on the branch and push.
2. Open a draft PR to `main` (one at a time) and subscribe to its activity.
3. When the `pipeline` and `web` checks are green, mark it ready and merge it with `expectedHeadSha`.
4. Unsubscribe.

`main` and the branch were level at #95 (24 Oct 16:15 IST). Nothing is open.

---

## 4. How a daily audit run is done (tools kept in the repo)

`pipeline/scripts/daily_audit/`:
- `reviewer_prompt.txt`: the blind reviewer's instructions. Substitute these placeholders:
  - `WORKDIR`: a scratch directory;
  - `XX`: the batch name;
  - `<repo>`: the checkout;
  - `EXTRA`: an extra line, or blank;
  - `FIELDS`: extra output keys, or blank.

  For `/api/review` cards, add step 7, saying whether each flag is warranted, and add the keys `flags_true` and
  `flags_false`.
- `ext.py`: PyMuPDF text by page. Run it with `python -I`, and keep downloaded PDFs in their own new directory.
- `onoff_duplicates.py`: F110's on/off. Same-company card pairs within 3 days, PDFs compared with `duplicates.match`.
- `onoff_ratings.py`: F111's on/off. Stored rating cards whose before/after the same-agency rule keeps or drops.

Batch building:
1. Take `/api/feed?range=7d&limit=40`, newest first, minus the ids already in today's audit JSON.
2. For each card keep `{news_id, symbol, scrip_code, pdf_url, filed_at, prompt_variant, card: card_json}`.
3. Write 5 per `batch_<x>.json` and give one batch to each general-purpose subagent, run in parallel.
4. Merge their `out_<x>.json` into `docs/audit/live/<date>-audit.json`. Each row needs: `run`, `verdict`,
   `error_class`, `reason`, `event_type`, `event_type_ok`, `prompt_variant`, `review_status`, `wrong_points`,
   `pruned_points_true/false` and `broken_text`.

On/off over stored cards:
- Export the feed. The cloud session kept a cache of about 2,050 cards: two `/api/feed` exports, at
  `/tmp/claude-0/a23/dup/feed_all.json` and `/tmp/claude-0/a24/feed.json`. These are lost with the container, so
  re-export with `next_cursor` paging.
- Run the old code from a `git worktree` of the previous commit via `PYTHONPATH`. Importing an old copy of a module
  directly breaks dataclasses.

Critic scoring:
- `docs/audit/live/critic-<date>.json` (from `export-critic`) against the reviewers' verdicts, joined on `news_id`.
- Point precision: flags the reviewers confirm. Recall: reviewer faults the critic caught, overall and on the lines it
  reads (headline, takeaway, what happened, why it matters).
- Template: `docs/audit/live/critic-score-2026-10-24.md`.

---

## 5. Fixes shipped in the last days (each measured first; full rows in `docs/TRACKER.md` and the ledger)

| Id | PR | What | On/off result |
|---|---|---|---|
| F104 | #82-#87 | Insider trades (NSE PIT XBRL) and the bulk/block deals history | new sources; `insider-sync`, `deals-backfill`, `fill-trades` |
| F105 | | Duplicate orders; case-stage negations | |
| F106 | | Memory refuses a call figure on another definition; named-year order terms | |
| F107 | | A covering letter that submits the results is RESULTS | |
| F108 | #91 | Broken text after a removed figure ("a 7- boost", "represents under of market cap") repaired; a call's audio-link letter promising a transcript is no card | 2 of 516 cards changed, both audio links |
| F109 | #92 | An EBITDA its own filings tell two ways (> 3% apart, no XBRL) shows no YoY/QoQ | broad rule rejected (47 cards; blind check 10 of 10 right), narrowed to 3 of 489 |
| F110 | #93 | A filing read after its repeat is the duplicate: `_duplicate_of` looks `duplicates.DAYS` either side, `filings_recent_company` limit 40 | 17 of 892 pairs, all byte-identical PDFs (14 repeats; 3 one-document-two-event, where one card per document is the existing rule) |
| F111 | #94 | A rating's "before" is the same agency's on the same scale; a global scale (S&P, Moody's, Fitch, "Global") is never set beside a domestic one, and an unknown agency is matched by its own name | 9 of 21 cross-agency comparisons removed, none wrong; refresh dispatched, Muthoot's card verified healed |

Earlier: E1-E14 (22 Oct, #65-#74), F98-F103 (fixers and false holds, 22-23 Oct), D1-D40 decisions. All are in
`docs/TRACKER.md`.

---

## 6. Open WRONG and MINOR classes, commonest first, with where to start

### WRONG classes

1. **The model misreads deck, call and chart figures (wrong_column / unit_scale).** Examples:
   - UTI AMC's SIP inflow taken from February's bar of a chart instead of September's;
   - Chembond's segment revenue growth read as order-book growth;
   - Newgen's "SaaS growth 45.3%", which is employee cost;
   - CSB's cost of deposits from the borrowings column;
   - HDFC Bank's PAT of ₹1,950 Cr from the transcript's "19.5 billion" (the real figure is ₹19,510 Cr);
   - KPIL's SEK 86.4 Mn shown as ₹8.64 Cr.

   Where to start:
   - A currency check: an amount next to SEK/USD/EUR in the quote must not be stated as ₹ without conversion. `computed.py`
     already sizes exchange-rate units (22 Oct).
   - A "billion" check on call figures against the results XBRL. The PAT is in memory, so a 10x gap is detectable.
   - Measure both over stored cards before shipping.
2. **Repeat cards for one event from different documents (duplicate).**
   - Examples: Triveni Power Transmission (results, deck, press release: 3 cards), VRL (buyback terms, then the letter of
     offer), Bajaj Housing Finance (deck card, then transcript card), Geojit.
   - F110 handles only identical documents. This class needs an event-level repeat rule (same company, same quarter or
     same corporate action, within N days), plus an on/off to make sure it does not merge different events.
   - Related open item: **one document with two events gets one card** (Jindal Stainless results + merger, Eternal
     results + ZEPL, GOCL results + NCLT).
3. **Results blocks mixing bases (restated / arithmetic).**
   - Geojit's prior year came from the old XBRL, before treasury income was moved out of revenue.
   - Persistent's EBITDA was computed after one-offs and contradicts the EBIT on the same card.
   - Shree Cement's EBITDA with other income sat beside comparatives without it (F109 narrowed this).
   - Fix: prefer the current filing's own restated comparative column over stored XBRL for the prior period. Measure over
     stored results cards.
4. **Attribution.**
   - TruAlt's all-India ethanol capacity given as the company's.
   - Jindal Photo's Manager to the Offer named as the acquirer. The card's quote was trimmed so it passed the quote
     check: a quote check that accepts a trimmed quote is a check gap.
5. **Event type.**
   - VRL's buyback letter of offer typed RIGHTS.
   - KPIL's stake sale by a subsidiary typed FUNDRAISE.
   - Dynamatic's intra-group carve-out typed FUNDRAISE.
   - Results press releases typed OTHER (Westlife, Shree Cement).
6. **Memory.** Cyient's call block took a segment's (DET) prior margin of 13.2% from memory where the group's was 9.7%.
   Memory figures need their segment or entity scope checked before use in a results block.
7. **Arithmetic in words.**
   - CRISIL "accelerated to 20.2%… outperforming 25.7%".
   - Gujarat Ambuja "PAT +247% far outpaced PBT +249%".
   - Dynamatic's ESOP shares priced at ₹50 instead of ₹10.

   A check that compares "accelerated / outpaced / faster" with the two figures it cites would catch the first two.
8. **Standalone vs consolidated label.** The BPCL call card put the standalone PBT under a CONSOLIDATED label.

### MINOR classes (frequent; they block RIGHT)

- Unsupported causes: Wheels, B L Kashyap, Beta (cause reversed), Kissht "steep premium".
- Invented milestones: Ashoka's monetisation date, Havells' Lloyd margin target.
- Guidance marked MAINTAINED where the company gives none: Persistent, Urban Company.
- Generous impact levels.
- Themes that don't fit: "Infra / EPC" on Panache and DIC India.
- Case-stage steps marked reached when they aren't: Cipla's Form 483 step, Park's "Order", Lupin's "Closed".

### Checks that remove true points (class G)

- 24 Oct: 15 of 16 pruned points were true. 23 Oct: 16 of 17.
- The prune and quote-drop checks still cost more true points than they save.
- Cyient's ₹12 interim dividend was dropped as "not in the filing", but it is on pages 14 and 19.

---

## 7. Pending work (one list; also in `docs/PLAN.md` and `docs/audit/actions-pending.md`)

### Workflow actions waiting (from `docs/audit/actions-pending.md`)

- **The rest of `fill-trades`**, after a market close; it pauses the AI pipeline:
  - `insider-sync --days 180` reads the 656 filings not yet read;
  - `deals-backfill --days 62` covers 22 Aug-21 Oct.

  Dispatch `maintenance.yml fill-trades` again.
- **`requeue-failed --ids nse-106705473,nse-106635921,nse-106707056,nse-106597136,nse-106601360`:**
  - the later cards of the Sunteck Q1FY27 and Sun Pharma Q4FY26 duplicate pairs;
  - three "uploads audio recording" cards.
- **Standalone-made results cards:**
  - Wendt `nse-106823265`, HDFC Life `4af25650-…`, ICICI Lombard `nse-106817737` and ICICI Pru Life `nse-106815694`:
    re-read once their consolidated file is listed;
  - another 10 to check once memory knows each company's basis.
- **Re-run Sapphire Foods `nse-106824614`:** "PAT turns positive" on a ₹1.51 Cr loss.
- **Optional:** re-run the second card of each F110 pair. Stored duplicates stay published until re-run.

### Held cards and the review queue

- 124 held (export 24 Oct). In a sample of 5, 2 could be released, and only 2 of the 11 hold reasons were true.
- `/api/review` lists 51 flagged published cards. The "text layer garbled" flag matched no wrong figure in the 5
  checked.
- The owner decides how held cards are shown (PLAN §7 B3: hidden, shown with a warning, or approve/reject).
  `release-held.yml` has `plan` and `dry_run`.

### Shadow critic

- **Off since 24 Oct 2026 (owner, D41; `CRITIC` defaults to 0).** 22 Oct: point precision 12%, recall 10%. 24 Oct:
  precision 9%, recall 12%, and 40% on the lines it reads; it used up to 3 minutes of every run and spare quota.
- Before it comes back it needs the whole filing, not a 600-character excerpt, for its INVENTED verdicts to mean
  anything; then a week in shadow mode scored against the reviewers.

### From `docs/PLAN.md`'s list (22-23 Oct blocks)

- E13: a press release's own-definition figure (operational, adjusted, a segment) set against statutory comparatives
  (Adani Energy Solutions, Swiggy, Cyient).
- E14: a December-year company's call figures stored under the wrong quarter (CIE Automotive).
- G: prunes drop true points (above).
- §5 item 9: measure A3, A9 and the pledge denominator over stored memory.
- Display of insider trades and bulk/block deals on the company page.
- Siemens-type years: 26 stored years disagree with their quarters (`docs/audit/long-years-2026-10-22.md`).
- Card design fixes 5, 9 and 10 (`docs/audit/design/cards-2026-10-20.md`).
- Company-page parts not yet checked against the approved design.
- Dabur's import alert in the case steps; AHLUCONT's promise fragment.
- The 70 "not material" reasons from pass 2.

### Tasks board (`docs/TASKS.md`; laptop tasks wait for the laptop)

- T25 (laptop): live review 5's classes.
- T16 (cloud): the daily review. The routine above does it.
- T13 steps 3-5 (laptop).
- T15 step 3 (laptop).
- T4 (laptop).
- Proposals P-L1 to P-L4.

### Owner decisions waiting (PLAN §7)

- **B3:** how held cards are shown.
- **A2:** backfill pace and route (free Gemini over ~111 days, three months only, or prepaid DeepSeek).
- **A3:** re-write a company's last ~30 days after the backfill.
- **B5:** prices from bhavcopy (Yahoo lags a session).
- **G8:** after a week's watch, delete the BSE client and `laptop.ps1`.
- **G9:** a Cloudflare rate-limit rule.
- Sign-in and indexing when the site is shared.
- Whether to disable the old account's routine (section 3).

### Still to confirm (assumptions)

- Gemini's daily limits.
- `ministral-14b-2512` returning no JSON.

---

## 8. Where things are

| What | File |
|---|---|
| Rules | `CLAUDE.md` |
| Plan and pending list | `docs/PLAN.md` |
| Decisions and findings (D1-D40, F1-F111) | `docs/TRACKER.md` |
| Design as built | `docs/SPEC.md`; spec by module `docs/BLUEPRINT.md` |
| Setup, commands, test count (977) | `docs/SETUP.md` |
| The routine when data is wrong | `docs/DATA_QUALITY.md` |
| Owner approvals | `docs/APPROVALS.md` |
| Operations log | `docs/OPS.md` |
| Daily audits | `docs/audit/live/<date>-audit.json` and `.md`, `held-<date>.json`, `critic-<date>.json`, `critic-score-<date>.md`, samples |
| Change ledger | `docs/audit/ledger.md` |
| Workflow actions waiting | `docs/audit/actions-pending.md` |
| Audit tools | `pipeline/scripts/daily_audit/`, `pipeline/scripts/audit_quote_rules.py`, `pipeline/scripts/audit_export.py` |
| AI providers | `pipeline/config/providers.toml`, `docs/AI_PROVIDERS.md` |
| Sources | `docs/SOURCES.md` |

## 9. Gotchas learned

- **Duplicate check:** the text cache (`data/text_cache`) is what lets the check see earlier filings across runs. NSE
  can list the original after its repeat (F110).
- **Ratings:** `card_context.agency_of` knows only the domestic agencies. Anything else is matched by name (F111).
- **Results text:** the duplicate check reads `select_text(..., figures=False)`. Byte-identical PDFs always match.
- **Parallel runs:** `pipeline.yml` never runs two at once (concurrency group). Each run discovers at its start, so a
  filing broadcast during a run waits for the next one.
- **Reviewer downloads:** NSE archive PDFs need a browser User-Agent and `Referer: https://www.nseindia.com/`. Retry
  once with `?x=1` if the file is under 50 KB.
- **Waiting in the cloud session:** a foreground `sleep` is blocked. Use a background until-loop, or wait for task
  notifications.
- **GitHub MCP tools:** they disconnect now and then. Reload them with ToolSearch (`select:mcp__github__…`).
- **Workflow dispatch:** dispatch export commands on the branch ref when the output should land on the branch. Dispatch
  refreshes on `main`.
