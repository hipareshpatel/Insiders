# Plan to go-live and after

The order of work from today (2026-10-16) to a live site, and how it runs afterwards. Status of
each blueprint item is in [TRACKER.md](TRACKER.md); the rules every session follows are in
[../CLAUDE.md](../CLAUDE.md). Everything stays on free tiers ($0 a month).

Who does what: **Laptop** = the Claude Code session on the Windows laptop (D:\Insiders), which
reaches BSE and runs everything; **Owner** = you, for accounts, keys and decisions.

## Phase 1: Smoke test (5 companies), now

Companies 506525, 532776, 505192, 500672, 530019, from 2025-01-01 to today (decision D6).

1. Laptop: `ai-check` passes for every provider (done 2026-10-16; Mistral's 429s are expected).
2. Laptop: `backfill-companies --scrips 506525,532776,505192,500672,530019` until no filing is PENDING.
3. Laptop: review on http://localhost:5173: home, feed, each company page, memory drawer, PDF
   verifier, System page; desktop and phone widths.
4. Owner and laptop: compare the cards with the six case studies in the blueprint (numbers,
   "why it matters", signals, missing disclosures). Fix prompts or code where they differ.

Exit: every filing ANALYZED or NOT_MATERIAL, no FAILED left unexplained, cards that read right,
and a measured rate (filings per hour) to size Phase 3.

## Phase 2: Data foundation

1. Laptop: `sync-companies`, then `market-data --all`. Check the Yahoo coverage it reports.
   If many companies have no price, build the bhavcopy fallback (TRACKER, "Price source fallback").
   Done 2026-10-16: 4,988 of 5,111 priced (97.6%), so no fallback for now.
2. Laptop: `price-history`, so history cards get the price and market cap of their own date.
   Done 2026-10-16: 4,995 companies stored.
3. Laptop: Gemini's free-tier limits. Google publishes no table, so the per-minute limits were read
   from Gemini's own 429 quota detail (done); the daily limits show up as a per-day 429 on the
   System page once reached, and then go into `providers.toml`.

Exit: universe (active, ≥ ₹100 Cr, plus starred) priced; daily price history stored.

## Phase 3: Full history on the laptop

1. Laptop: `run --mode backfill --max-backfill-days 30`, repeated until the System page shows the
   backfill complete. It resumes wherever it stopped and saves every 5 filings per company.
   Pass A is the 2025 baseline, then Pass B is 2026 to today.
2. Size it from the Phase 1 rate. The free AI quotas are the limit: when a day's quotas are used,
   the run stops and the next day continues. Keep the laptop awake and plugged in; log to a file.
3. Laptop: `post-mortem --since 2025-01-01` (how each stock moved after each card).
4. Spot-check a sample of companies across sectors and sizes.

Exit: backfill complete, post-mortem done, sample looks right.

## Phase 4: Go-live

1. Owner (Cloudflare, free plan): create D1 `bse-index` and R2 `bse-intelligence`; set the Worker
   secrets `INGEST_TOKEN` and `OWNER_TOKEN` (long random strings, kept in the keys file).
2. Laptop: put the D1 id in `web/wrangler.jsonc`, `npm run db:migrate:remote`, `npm run deploy`.
   The site is then at https://insiders.reply-bd3.workers.dev.
3. Owner: merge the draft PR into `main` once the steps above pass, so `deploy-web.yml`
   redeploys on later changes. (GitHub secrets `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.)
4. Laptop: `sync-to-cloud` once a day until it reports complete. D1 allows 100,000 row writes a
   day, so about 50,000 cards take about five days; live runs keep working meanwhile.
5. Choose how live runs are scheduled (owner decision, see below) and start them.

Exit: the deployed site shows the full history and new filings within the run interval.

## Phase 5: Running it

| When | What | Where |
|---|---|---|
| Every 15–30 min, market days | `run` (live filings first, then any backfill) | laptop |
| Weekdays after the close | `market-data`, then `post-mortem` | laptop |
| Weekly | `sync-companies`; `backup` of dossiers | laptop / GitHub Actions |
| Daily glance | System page: queue, failures, per-provider quota, review queue | owner |
| Monthly | `models` and `ai-check`: replace retired models in `providers.toml` | laptop |

## Decisions still open

1. **How live runs are scheduled.** The laptop is Windows, and `pipeline.yml` assumes a Linux
   runner. Recommended: Windows Task Scheduler runs a small PowerShell script (load the keys file,
   `python -m bse_intel run`) every 15–30 minutes, so keys never leave the laptop (D14). The
   alternative is a self-hosted GitHub runner, which needs the workflow adapted for Windows and the
   keys stored as GitHub secrets.
2. **Laptop uptime.** Live runs need the laptop on and online during market hours (09:00–18:00
   IST at least). A small always-on machine on an Indian connection (old PC, Raspberry Pi) is the
   fallback if that is not practical.
3. **Price fallback** (bhavcopy), only if Yahoo coverage turns out poor in Phase 2.

## Pending work (one list)

Everything not finished, from the tracker, the audit and the laptop smoke test. Phase numbers
refer to the sections above.

| # | Item | Who | When |
|---|---|---|---|
| 1 | Finish the 5-company backfill (rebuilt from scratch on 2026-10-16 after the unit, sector-lens and duplicate fixes; 5 workers; expected done about 07:00) and review the site against the case studies | Laptop, then owner | Phase 1 |
| 1a | Retry the one Kanoria long document (2025-05-21) that failed on every long-context provider; it is retried automatically by the next run | Laptop | Phase 1 |
| 1b | Measure 5 vs 3 workers over a full hour (filings/hour, 429 share) and keep the better (D18); the first 14 min gave ~125/h vs ~95/h, 9% 429s before the Z.ai one-at-a-time cap | Laptop | Phase 1 |
| 1d | Thinking for the Nemotron models: keep it (more accurate, 37 s a card, timeouts) or switch it off on the backfill route (2–4x faster, 8–16 s); measure accuracy on the second smoke test first (tracker F23) | Owner decides | Phase 1 |
| 1e | Batch from the site review (tracker F1–F23): done F1 units, F2 quarter labels, F11–F14 memory, F19 math names, F23 safe tuning; still open F3 same-results cards, F4/F15/F18 prose arithmetic, F5 raw rupees, F6/F10/F17 event tags, F7 derived payouts, F8 score size, F16 unit labels, F20 EBITDA vs PBT, F21/F22 System display | Laptop | Phase 1 |
| 1c | Full backfill order: owner leans to the ₹1,000–10,000 Cr band first (985 companies, large caps last); size it from the smoke-test rate and the 16.8% duplicate share, then decide | Owner decides | after Phase 1 |
| 2 | ~~`ai-check --provider cloudflare` after the Workers AI fix~~ done 2026-10-16: both models pass | Laptop | Phase 1 |
| 3 | `ministral-14b-2512` sometimes returns no JSON: find why (truncation at max_tokens?) or lower its weight | Laptop | Phase 1 |
| 4 | ~~Confirm BSE's XBRL field and tag names on real filings~~ done 2026-10-16: announcement rows carry no XBRL link (0 of 1,166 had one), so results XBRL now comes from BSE's results archive (`Result_Arch_ng`); 53 of 55 smoke-test results filings found and confirmed their file; the parser reads BSE's real files unchanged | Laptop | Phase 1 |
| 5 | Gemini daily limits (per-minute ones measured 2026-10-16): record the value from the first per-day 429 on the System page in `providers.toml` | Laptop | Phase 3 |
| 6 | ~~Yahoo price coverage after `market-data --all`~~ done 2026-10-16: 97.6%, no fallback needed for now | Laptop | Phase 2 |
| 6a | Industry for every company from BSE's quote header (`sync-companies`, about 5,100 lookups, saved every 200; finishing 2026-10-16 about 02:35), which also labels the 485 companies with a market cap but no size; confirm 0 remain unlabelled | Laptop | Phase 2 |
| 7 | Copy `size_category` onto cards at write time so size filters use the feed index (tracker, point 3) | Laptop | before Phase 4 |
| 8 | Live-run scheduler for Windows: a PowerShell script for Task Scheduler (or adapt `pipeline.yml` for a Windows runner); fix README/SPEC, which still say a Linux runner | Owner decides, laptop builds | before Phase 4 |
| 9 | Cloudflare D1 and R2, Worker secrets, D1 id in `wrangler.jsonc`, deploy | Owner and laptop | Phase 4 |
| 10 | Merge the PR into `main`; GitHub secrets for `deploy-web.yml` | Owner | Phase 4 |
| 11 | `sync-to-cloud` daily until complete | Laptop | Phase 4 |
| 12 | Per-client rate limiting on the public API (audit D5); card JSON to R2 if D1 nears 500 MB (D6) | Laptop | if needed after go-live |
| 13 | Modules 8 (DGTR duties) and 42 (promoter-group contagion): need a data source | Owner decides | later |

## Risks

- Free-tier changes: models get retired and limits change without notice. `ai-check` finds it;
  the gateway already skips disabled models and fails over.
- BSE format or access changes: the run stops after repeated refusals instead of failing filings.
- D1 write budget: bounded by design (sync is budget-aware, history stays local).
- Not built (no data source): Module 8 (DGTR) and Module 42 (promoter-group contagion).
