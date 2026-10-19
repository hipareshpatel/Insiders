# Plan to go-live and after

The single plan, rewritten 2026-10-19 for the setup the owner chose on 2026-10-18/19: **NSE only, online only**
(GitHub Actions + Cloudflare, no laptop on the daily path), companies at or above ₹500 Cr. What each item built and
measured is in [TRACKER.md](TRACKER.md) (decisions D1-D34, findings F1-F77); the rules every session follows are in
[../CLAUDE.md](../CLAUDE.md); the design is in [SPEC.md](SPEC.md). Everything stays on free tiers ($0 a month); the
prepaid DeepSeek balance is the one exception, for the backfill only, never the daily path (D24).

The earlier plan (a Windows laptop reading BSE, phases 1-5 of 2026-10-16) is superseded; it is in git history
(this file before 2026-10-19). Who does what: **Owner** = you (accounts, keys, decisions); **Laptop** = the Claude
Code session on the laptop, which now builds and runs audit rounds only; **Cloud** = the cloud Claude session that
reviews every push and fixes what it finds.

## 1. Where things stand (2026-10-19)

| | Planned | Actual |
|---|---|---|
| Source | BSE | **NSE only** (BSE refuses cloud addresses; BSE-only companies dropped, D34) |
| Runs on | the laptop | **GitHub Actions + Cloudflare**; the laptop builds and audits |
| Companies | ~5,100 BSE scrips | **1,778 NSE companies ≥ ₹500 Cr** (D31) |
| Quality gate | "cards that read right" | blind agent rounds; **go-live at ≤ 5% of published cards WRONG** |
| Accuracy | | round 0 53% wrong → round 4 21% → round 5 23% → **round 5 arm B 10%** (Gemini writing, results built by code) |
| Missed news | | 0-2 of ~50 per round: on target |
| Round 6 | | **running** (20 unseen companies, seed 20261022, `docs/audit/round-6.md`) |

How a filing flows today: NSE announcement → universe filter → rule book (noise / calendar / timeline / data-only /
fast track / pass 1) → PDF + OCR + NSE XBRL (event: wait ≤ 90 min; results: ≤ 180 min) → card (packed Gemini; results
figures by code) → checks (figures, units, directions, arithmetic, one card per event) → published, or held after a
second opinion → later: re-read when XBRL lands, price reaction T+1/3/5, governance and shareholding into memory.

## 2. Built for the online NSE pipeline (PLAN 18 of the old list, all done)

| Part | What | Tracker |
|---|---|---|
| 1-2 | Universe from NSE's equity list; discovery from NSE announcements; rule book on NSE's subjects; attachments from nsearchives | F67 |
| 3 | Event XBRL joined to its announcement (same file, else content); a card re-read when its file lands | F68 |
| 4 | Results from NSE's integrated-filing XBRL; results cards written by code; memory comparisons by code | F69, F74 |
| 5 | Shareholding and quarterly governance XBRL into memory | F70, F71 |
| 6-8 | Annual-report wording; `pipeline.yml` online (off until switched on); refusals and network errors spend no attempts | F72 |
| — | Packed Gemini writing (several filings a request); writers weighted by measured WRONG | F75, round 5 arm B |
| — | **Company master from NSE** (new listings under their NSE symbol, industry from NSE's own data), daily workflow; no BSE call on the online path; annual-report catch-up inside `run` after 18:30 IST | F77 |

## 3. Now: reach 95% right

1. Round 6 (running): review blind; pass mark WRONG ≤ 5% of published, MISSED ≤ 2 of ~50.
2. Below 5%? Fix the commonest WRONG classes in code, measure on round 6's own cards, then a fresh round 7. Classes
   still open after round 5 arm B: results without an XBRL file read from memory's other quarters; a model takeaway
   giving a cause the statement contradicts (results takeaway now from the file's profit bridge); impact level too
   high on routine filings.
3. Measure before relying on them: the unit check on computed impacts (done, 3 true flips of 383); packing bleed
   between filings in one Gemini request; per-writer WRONG each round (Gemini 3.7/3.8 have small samples).

## 4. Go-live checklist (after 95%)

| # | Step | Who |
|---|---|---|
| G1 | Cloudflare (free plan): D1 `bse-index`, R2 `bse-intelligence`, an API token; Worker secrets `INGEST_TOKEN`, `OWNER_TOKEN` | Owner |
| G2 | GitHub secrets (entered on GitHub only, never pasted in chat): `GROQ_API_KEY`, `NVIDIA_API_KEY`, `MISTRAL_API_KEY`, `ZAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `INGEST_TOKEN`, `PLATFORM_API_URL`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | Owner |
| G3 | Make the repository public (GitHub's free minutes then cover the 15-30 minute runs) | Owner |
| G4 | D1 id in `web/wrangler.jsonc`, `npm run db:migrate:remote`, deploy (https://insiders.reply-bd3.workers.dev); merge the PR so `deploy-web.yml` redeploys later changes | Laptop, then owner merges |
| G5 | Timing run on a GitHub runner: filings an hour, AI requests a filing, 429s (the audit rounds' figures are laptop figures) | Cloud / laptop |
| G6 | `sync-companies` (NSE) once by hand, then **seed every universe company's history from XBRL** (results, shareholding, governance; no AI), so day-one cards know each company's past numbers | Laptop or a workflow run |
| G7 | Switch on: repository variable `PIPELINE_SCHEDULE = on`; cron-job.org calls `pipeline.yml` every 15-30 minutes | Owner |
| G8 | Watch a week: System page (queue, failures, quotas, held cards); then delete the BSE client and `laptop.ps1` | Owner, laptop |
| G9 | Cloudflare rate-limiting rule on the public API (one free rule, e.g. 60 requests a minute per visitor), so a scraper cannot spend the free quota | Owner |

## 5. After go-live

| # | Item | Who | Notes |
|---|---|---|---|
| A1 | **Backfill six months** (`BACKFILL_START` 2026-04-19), newest month first, on free Gemini | runs itself | ~21,400 card tasks: about 111 days beside the live run (measured from arm B, F75); faster options are an owner choice (A2) |
| A2 | Backfill pace | Owner decides | (a) as A1; (b) three months only; (c) DeepSeek prepaid for the backfill only, after a blind A/B on round 5's companies |
| A3 | Optionally re-write a company's last ~30 days of cards once its backfill is complete (they were written before its history loaded) | Owner decides | costs AI requests |
| A4 | `post-mortem` over the history; spot-check a sample | runs daily / laptop | |
| A5 | Weekly `ai-check` and `models`: replace retired models in `providers.toml` | Laptop | |

## 6. Build next (owner asked for these)

| # | Item | Notes |
|---|---|---|
| B1 | **Module 42, promoter pledges**: NSE's SAST Reg 31 encumbrance feed into memory, a "pledge rising / invoked" signal | source measured on GitHub (`docs/SOURCES.md`) |
| B2 | **Module 8, anti-dumping (DGTR)**: case PDFs by product, linked to companies | linking product → company needs its own accuracy check |
| B3 | Held cards: owner **Approve / Reject** on the review queue (today only Re-run); optionally show unreviewed held cards with a "verify against the filing" banner | 34 of 146 cards held in arm B, 10 of them WRONG |
| B4 | Company page panels from data already stored: quarterly governance (board, penalties, insider loans), peers, segment mix, auditor history, a price chart | |
| B5 | Prices from NSE's bhavcopy (official daily file) instead of Yahoo; market cap = price × shares from the shareholding XBRL | probe on GitHub first |
| B6 | Newer free models on NVIDIA's catalog (DeepSeek V4.1 Flash, Kimi K2.6, GLM-5.3, Gemma 4 31B, Palmyra Fin 70B; Nemotron Parse 2.0 for tables), each `ai-check`ed, then a blind A/B | replaces the old "re-test thinking mode" item (thinking measured 16 Oct: 3-10x slower, no accuracy gain, D21) |
| B7 | A "report an error" button for the owner on each card, feeding the audit set (the Star / Noise feedback teaches taste, not correctness) | |

## 7. Decisions open for the owner

1. Held cards: keep hidden, show with a warning, or approve/reject (B3).
2. Backfill pace (A2) and re-writing cards after it (A3).
3. Prices from bhavcopy (B5).

## 8. Risks

- Free-tier changes: models are retired and limits change without notice; `ai-check` finds it and the gateway fails over.
  Gemini's free tier is 20 requests a day per model (measured): it carries the daily flow (~23 of 60 calls) with room.
- NSE limits by IP address: the pipeline stops politely on 401/403/429 with the work queued, and never spends a
  filing's attempts on refusals or network failures. NSE's quote page already refuses cloud and GitHub addresses.
- D1 write budget (100,000 rows a day): bounded by design; the company sync writes only changed rows.
- Yahoo is unofficial (B5 removes it).
