# Owner approvals

A standing record of what the owner has approved, so a session can act without asking and the owner can review it later.

## 2026-10-20 ~06:00 IST: "giving all approvals"

The owner, going offline, approved everything the lead session does to run and improve the site, to be reviewed on
return ("note them, when i will be back, i will ask for it"). Under it the cloud session may, without asking:
- merge its own PRs into `main` once CI is green (each merge redeploys the site through `deploy-web.yml`);
- start, re-run and re-schedule GitHub workflows (the pipeline every 15 minutes: owner, same message);
- change pipeline, Worker and site code and the AI routes on the free tiers; give the laptop tasks.

It does not cover, and still goes to the owner:
- anything that costs money: no paid AI route on the daily path; D24's prepaid DeepSeek stays backfill-only;
- keys, tokens and secrets (never read, printed or changed);
- deleting live data by hand (DATA_QUALITY.md: fix the class in code and re-run);
- making the repository private, or changing Cloudflare or GitHub account settings.

Every action taken under it is listed below with its commit or run, for the owner's review.

### Actions taken
- 20 Oct 05:19 IST: PR #1 merged into `main` (d346309) and `pipeline.yml` run 1 started by hand (owner's "work on production now", before this record).
- 20 Oct 05:51 IST: PR #2 merged into `main` (b143a79) with CI green; the pipeline schedule moved to every 15 minutes (c88f358); lead check-ins every 15 minutes (chained one-off check-ins: routines allow hourly at most).
- 20 Oct 06:27 IST: PR #3 merged into `main` (1ef32e5) with CI green: the company page and the cards to the approved designs.
- 20 Oct 06:12 IST: `pipeline.yml` run 2 started by hand (the new 15-minute schedule had not fired yet).
- 20 Oct 06:52 IST: PR #4 merged into `main` (c0002ef) with CI green: live review 3 fixes.
- 20 Oct 06:31 IST: PR #5 merged into `main` (926e2d8) with CI green: the Today footer.
- 20 Oct 06:55 IST: PR #6 merged into `main` (91b832b) with CI green: `maintenance.yml`, the no-AI refreshes run from GitHub (T23 taken off the laptop). Started its dry run of `refresh-card-blocks`.
- 20 Oct 07:00 IST: `maintenance.yml` run for real (after a clean dry run): `refresh-card-blocks` changed 1,042 of 1,106 stored cards, 0 failed (99 re-rated HIGH under D39), `refresh-summaries` rebuilt 1,418 company summaries.
- 20 Oct 07:06 IST: PR #7 merged into `main` (d0958d8) with CI green: the capex counterparty guard, T23 records.
- 20 Oct 07:41 IST: PR #8 merged into `main` (09fd351) with CI green: Coming up and calendar text.
- 20 Oct 09:43 IST: PR #9 merged into `main` (b17d49c) with CI green: export-held in maintenance.yml (T19 to the cloud). Started export-held.
- 20 Oct 10:00-11:30 IST: PRs #10-#15 merged into `main` with CI green: the 7-day live window and 429 pauses (#10), failed filings listed and retried plus the laptop's T24/T17/T18 fixes (#11), requeue by id (#12), seed-memory from GitHub (#13), card design fixes 5 and 10 with the docs refresh (#14), fix 9's deal terms (#15).
- 20 Oct 11:40 IST: owner approved ("YES") a live-only blind review of ~30 published cards tonight after the catch-up: independent reviewers read live cards against their PDFs; no pipeline re-runs, no AI used by the pipeline for it.
- 20 Oct 12:00 IST: dispatched market-data.yml on main by hand (it had never run on GitHub: company pages had no price chart, no technicals, prices from 16 Oct); no AI, about 1-2k D1 writes.
- 20 Oct 20:36 IST: dispatched maintenance.yml seed-memory (restart) on main (T13 step 1; no AI).
- 20 Oct 20:50 IST: PR #22 merged into `main` (1883b5d) with CI green: DeepSeek first on the seed (cache, 40M-token cap), the near-cap guard, F94.
- 20 Oct 21:25 IST: seed-memory step limit raised to 5 h in maintenance.yml (no AI; one D1 kv write a company); re-dispatched with restart=false.
- 20 Oct 21:59 IST: dispatched seed-calls.yml on main by hand (its first scheduled run did not start; owner approved the DeepSeek seed with its cap).

## 2026-10-21 02:30 IST: owner decisions in chat
- Shadow critic: "shadow mode is fine, go ahead with the critic". A second model on spare free quota records per-point
  verdicts on live cards and changes nothing; after a week the daily audit compares its verdicts with the reviewers'
  before it may act on cards.
- Interpretation on the card face, marked "Our reading · not checked", and the card instructions tightened from the
  reviewers' findings.
- Daily card audit for 200 days, 10:00-17:00 IST, from the cloud (routine "Daily card audit (200 days)"), with a
  ledger of every change and its effect (docs/audit/ledger.md).
- Keep about 5,000 D1 rows a day spare for spending spare free AI quota on better output.
- Merges queued for 05:45 IST; the owner does not push them.
- 21 Oct 19:10 IST (owner, in the lead session): "use deepseek for pending and let's clear them". The prepaid DeepSeek
  (D24) drains the pending queue on the scheduled pipeline runs while `pipeline/config/drain_until` is ahead
  (2026-10-23 00:00 UTC): key passed, DeepSeek preferred on every route that has it (PREFER_MODEL, weight x5 (x20 until 22 Oct 08:45 IST, which left the free Z.AI slots idle)), 8
  workers. The balance is prepaid with no card, so spending stops when it runs out; past the date, or with the file
  removed, the pipeline is free-tier only again. Cards keep their model label, so the daily audit scores DeepSeek's
  (47% WRONG in round 1, before today's checks).

## 2026-10-25 08:45 UTC: "Yes for all green"

The owner approved merging every PR into `main` without asking, once it is green: CI passing on the current head, no
merge conflict, and no review thread left open. A merge redeploys the site and changes the next 15-minute pipeline run,
so a change that alters what cards say also needs its release gate passed before merging (for example F126d under
`PASS_MARKS_TABLE.md`, and the blind review for narrowed grounding): green CI shows the code runs, not that the cards are
right. Everything the 2026-10-20 approval leaves to the owner still goes to the owner.

### Actions taken
- 25 Oct 08:43 UTC: PR #105 merged into `main` (6bdf77f) with CI green, on the owner's "Merge it, do not ask": the
  CLAUDE.md rule on cheaper subagents.
- 25 Oct 08:46 UTC: PR #106 merged into `main` (02ead06) with CI green: this standing approval.
- 25 Oct 11:37 UTC: PR #112 merged into `main` (67d3126) with CI green: this standing approval.
- 25 Oct 11:58 UTC: PR #113 merged into `main` (a34cec8) with CI green: this standing approval.
- 25 Oct 14:28 UTC: PR #114 merged into `main` (1de413b) with CI green: this standing approval. Includes F140 (only removes figures; on/off over the 7 failing real files: 1 file changed).
- 25 Oct 14:52 UTC: PR #115 merged into `main` (f073b6f) with CI green: this standing approval. Includes DeepSeek off on regular jobs (owner).
- 25 Oct 15:10 UTC: PR #116 merged into `main` (68315b1) with CI green: this standing approval.
- 25 Oct 15:28 UTC: PR #117 merged into `main` (c5de004) with CI green: this standing approval. F149 changes timing only, not card content.
- 25 Oct 15:32 UTC: PR #118 merged into `main` (a60c911) with CI green: this standing approval. No card change (measurement, a memory job not yet run, the metrics table not on cards).
- 25 Oct 15:36 UTC: PR #119 merged into `main` (e3379cb) with CI green: this standing approval. F151 is behind CARD_EBITDA_PROFIT_V2, off; turning it on waits for the release check.
- 25 Oct 16:05 UTC: PR #120 merged into `main` (53ef3b9) with CI green: this standing approval. F152/F154/QUOTE_EXACT_NUMBERS are off; live changes: newest-first results catch-up and the shared currency list (bug fixes).
- 25 Oct 16:18 UTC: PR #121 merged into `main` (f8a5eec) with CI green: this standing approval. F155's two memory guards are live (they refuse bad figures on new writes only); the PBT and EBITDA-change parts are behind switches.
- 25 Oct 17:00 UTC: PR #122 merged into `main` (c59e338) with CI green: this standing approval. F153 switched on as a fix of live wrong cards (owner's rule).
- 25 Oct 17:49 UTC: PR #123 merged into `main` (b4f7eb0) with CI green: this standing approval. F157 changes what the seed writes to memory (derived quarters labelled calc; mis-dated files refused).
