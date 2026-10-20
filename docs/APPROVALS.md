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
