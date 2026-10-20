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
