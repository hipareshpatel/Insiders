# Owner's requests: the A, B and C lists with today's status (22 Oct 2026, 06:10 IST)

Carries `owner-items-2026-10-21.md` forward. Each status is checked against main and the live site, not taken from
earlier replies. "Live" means deployed and on the site; "PR" means on the branch in an open pull request.

## A. Raised on 21 Oct

| # | Request | Status 22 Oct |
|---|---|---|
| A1-A2, A5, A20-A22 | Where to verify; Today vs Signals; the 34 high-impact cards; pipeline-run columns; read-back; merge after the list | **Done** |
| A3 | DeepSeek drains the pending queue | **Live** until 23 Oct. Queue still at the 1,000 cap: the outage stopped 3½ hours of runs |
| A4 | Signals: 7/30-day tabs, results sized by their own change | **Live** (#45) |
| A6 | Turnarounds tab; acquisitions count as growth | Tab **live**. **Open:** acquisition-driven growth is not yet told apart |
| A7 | Monthly updates, press releases, shareholder letters dropped as noise | **Live** (#45). **Open:** requeue of the 10 listed filings (`actions-pending.md`) |
| A8 | Held cards: memory vs filing quote rule | Built, audited, **reverted** (2 of 7 released cards wrong). Replaced by A25 |
| A9-A13 | Analysis panels and 4K image; backfill counters; fonts; no "✓ computed"; industry path and 1W/1M/3M | **Live** (#45) |
| A14 | Previous quarters missing (E2E) | **Live, filling.** Quarters derived from H1/9M/FY; the 12-shard seed reads every company back to FY21. It stopped with the outage at 20:29 UTC, restarted 05:40 IST |
| A15 | Consolidated vs standalone | **Live** (#45, #52): consolidated waits for its file, standalone kept apart with a switch on the company page. **Open:** recheck 14 standalone-made results cards after the seed (`actions-pending.md`) |
| A16 | Call summaries on company pages | **Live** (#46) |
| A17 | NSE symbols, not BSE codes | **Live** (#45) |
| A18 | Card boxes used wrongly; benchmark similar sites | **Live** (#48) |
| A19 | One company view; complete financials and notes | **Live** (#49) |
| A23 | Institutional shareholding, governance, pledges, DGTR in one go | **Live** (#47; `fill-memory` run 18 finished 21 Oct) |
| A24 | Financials as on screener.in, with standalone vs consolidated | **Live** (#50-#53): quarterly, P&L by year with TTM, balance sheet, cash flows, ratios, Consolidated / Standalone switch. Fills as the seed reaches each company |
| A25 | Needs review · 475 | **Live 21 Oct 23:40:** 252 held cards published without their unquoted points. See D3 for the 223 left |

## B. Open from 19-20 Oct

| # | Request | Status 22 Oct |
|---|---|---|
| B1 | AI instructions and inputs (8-item plan) | Items 1, 2, 3 (critic, shadow), 5, 6 (blind vote, shadow), 7 (end-of-day sweep, #52), 8 **done**. Memory view rebuilt for the new data (`previous_calls`, full balance sheet, cash flow, institutions; #53). **Open:** item 4 (facts table first: needs a live split, AI) |
| B2 | Call cards linked to earlier calls | **Done** as A16 |
| B3 | Re-run Yes Bank AT1, Sunteck, Sun Pharma pairs | Yes Bank re-run 21 Oct. **Open:** the 5 ids after the seed (`actions-pending.md`) |
| B4 | Deep audit of all code, site, workflows | Sections A-H reviewed. Fixed: A-01..A-07, A-10, F-01..F-10, F-13, F-14, G-02..G-04, H-01. **Open:** see E below |
| B5 | Live cards only, no AI for testing | Followed |
| B6 | Accuracy gate (≥ 95% right) | **Not met** (21 Oct audit: 21% right, 77% right-or-minor of 48). Next measurement: today's 10:07 audit, now with the shadow critic scored (D4) |

## C. Done earlier

16-20 Oct: everything in `owner-items-2026-10-20.md` except what is carried above (scheduled jobs, no dividend or
small-fine cards, duplicate rule, verdicts that act, results table, shareholder direction, 200-day audit, RapidOCR,
NSE-only online, redesigned site, 15-minute runs).

## D. New, 21-22 Oct

| # | Request | Status |
|---|---|---|
| D1 | Site and pipeline down from 21 Oct 20:29 UTC | **Fixed.** Cause measured: D1's free 5,000,000 rows read a day (not writes; nothing measured reads). Two queries read 7.7M of the 12M: company-page peers and the queue listing, both now bounded index seeks (#54, live 22 Oct 05:31). `d1-usage.yml` prints D1's own counts daily. Recovered at the reset: every page 200 at 00:01 UTC |
| D2 | "Such things may happen, it should start automatically" | **PR #56.** The pipeline and call seed already restart on their schedules; `recover.yml` (00:07 UTC daily, after D1's reset) re-runs a failed deploy and restarts the memory seed when its chain stopped |
| D3 | Needs review · 223 · 14 re-runs queued | Measured (`release-pruned --dry-run`, new breakdown): 61 published but flagged + 162 held. **PR #56:** 36 held cards whose quarter already has a published card leave the queue (superseded, D20); 29 flagged published cards lose the points their quotes do not carry (dry run: 1-9 points each), and 1 held card is released. Left after that: 126 held for true faults (82 figures not found in filing or memory, 21 headline figures, 18 out of fit, 17 unsupported claims, 10 math) — the end-of-day sweep re-runs 40 a day, 14 queued now; 31 flagged with true faults |
| D4 | Shadow card audit | **PR #56:** `audit-export.yml` writes held cards, what keeps each, and the shadow critic's verdicts to `docs/audit/live/` at 09:51 IST daily, outside Maintenance (a seed pass would cancel it there). The 10:07 audit scores the critic's precision and recall against the independent reviewers |

## E. Deep audit items still open

| ID | What | Plan |
|---|---|---|
| F-11, G-01 | Today runs ~10 D1 queries a view; SPEC says it reads the R2 snapshot | Next, with the read budget (measure first) |
| F-12 | A fact with any quote shows as verified though the quote may not be in the filing | Store per-fact `quote_found` (stricter) |
| F-15, F-16 | Phone filters take 326 of 844 px; light-theme contrast 2.8-3.5:1 | UI pass |
| A-08, A-09 | One 404 aborts the event-file match; the catch-up re-runs published cards | Fix with tests |
| A-14 | `raw/` stored again every run (R2 growth) | Measure size, key by content hash |
| A-15 | OCR failing on a partly scanned PDF loses those pages silently | Hold or flag the card |
| A-11..A-23 | LOW items (bank opex, capex sign, non-March years, ...) | After the above |
| G-05, G-06 | No Worker tests | Add for the read paths changed today |
