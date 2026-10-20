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
