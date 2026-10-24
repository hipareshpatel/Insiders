# NSE Corporate Intelligence & Persistent Memory Platform

Every NSE corporate filing of a company worth ₹500 Cr or more, triaged and analysed against a living memory of each
company: what happened, why it matters given what management said before, what to
watch next. It runs on free tiers.

- **Pipeline** (`pipeline/`, Python). Fetches NSE announcements, drops noise by
  rules, gatekeeps ambiguous filings, extracts PDF text (OCR for scans), and analyses
  material filings through a 7-provider free AI gateway with a 95% quota ceiling. It
  checks every number against the source, re-computes every quantified estimate from
  its shown working, merges facts into per-company dossiers with provenance, computes
  signals (promise vs delivery, dilution, working capital,
  metric shifts), and publishes cards to the web app.
- **Web** (`web/`, Cloudflare Worker). A Hono API over D1 and R2, and a React app:
  a home feed of announcement cards (facts, "why it matters", a P&L for results, the
  call read for concalls) with a compact list view, a Results table,
  company pages (overview, results scorecard, promise tracker, timeline, filings), a
  catalyst calendar and a system monitor. The website is the only distribution
  channel.
- **Shared SQL** (`db/`). One schema and one set of statements, used by both.

The design, and what changed from the original brief, is in
**[docs/SPEC.md](docs/SPEC.md)**. The plan to go-live is [docs/PLAN.md](docs/PLAN.md); status and owner decisions are in [docs/TRACKER.md](docs/TRACKER.md);
working rules for Claude Code sessions are in [CLAUDE.md](CLAUDE.md).

> Summaries of public NSE disclosures. Not investment advice.

## Quick start (local, no accounts needed)

Requirements: Python 3.11+, Node 22.

```bash
# 1. Web app with local D1/R2 (Miniflare)
cd web
npm install
printf 'INGEST_TOKEN=dev-local-token\n' > .dev.vars
npm run db:migrate:local
npm run dev                      # http://localhost:5173

# 2. Pipeline, in another terminal
cd pipeline
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,ocr]"      # ocr: RapidOCR for scanned pages (optional)
python -m pytest -q              # 981 tests (6 skip without the ocr extra); web: npm test (55: card text, company statements, owner holds, call takeaways, company keys)

# 3. Fictional demo data, written through the real pipeline into the local Worker
BSE_INTEL_SINK=platform PLATFORM_API_URL=http://localhost:5173 \
INGEST_TOKEN=dev-local-token python scripts/seed_demo.py
```

The demo companies are invented ("Demo … Ltd", scrip codes 9990xx). The seeder fakes
only BSE and the AI replies; rules, extraction, prompts, gateway, grounding, memory,
signals and storage all run for real.

Analyse a real PDF you have locally (needs at least one AI key):

```bash
export NVIDIA_API_KEY=...  # and/or GROQ_API_KEY, MISTRAL_API_KEY, ZAI_API_KEY, GEMINI_API_KEY
python -m bse_intel analyze-pdf results.pdf --scrip 500000 --company "Some Ltd" \
  --headline "Unaudited Financial Results" --event-type RESULTS --industry "Cement & Cement Products"
```

## Pipeline commands

| Command | Does |
|---|---|
| `python -m bse_intel run [--mode live\|backfill\|all] [--time-budget 2400]` | One run: live window, then backfill |
| `python -m bse_intel backfill-companies --scrips 506525,532776,505192,500672,530019` | Smoke test: discover and analyse given companies since `BACKFILL_START` |
| `python -m bse_intel sync-to-cloud [--source http://localhost:5173]` | Copy the laptop's local data to Cloudflare (resumable, stops at the D1 daily write budget) |
| `python -m bse_intel seed-memory --scrips A,B [--since 2023-01-01]` | Financial and ownership history from XBRL, no AI call: results (consolidated and standalone, FY21 on) and shareholding from NSE's XBRL (decision D23); `--universe [--shard I/N]` walks every company resumably, in 12 shards from GitHub (Maintenance > seed-memory) |
| `python -m bse_intel governance-sync [--pages N]` | The quarterly governance XBRL of the universe's companies into memory (board, committees, SEBI flags, penalties, loans and guarantees to insiders, cyber incidents); no AI, no card. The live run does 40 a run; `--pages` reads back for the backfill |
| `python -m bse_intel shareholding-sync [--days N]` | Each universe company's quarterly shareholding XBRL into memory (promoter, pledge, FII, DII), cross-checked against NSE's list; no AI, no card. The live run reads 10 days |
| `python -m bse_intel pause-ai [--minutes N]` / `resume-ai` | Pause the AI pipeline while memory jobs write (kv `pause:ai`): no live run starts and a running one stops between filings, the work stays queued; the pause ends by itself. The nightly job and maintenance `fill-memory` use it |
| `pledge-sync [--days N] [--scrips a,b]` | Promoter pledge events (NSE SAST Reg 31) into memory, no AI (module 42); also at the end of every live run |
| `deals-sync [--scrips a,b]` | The latest session's bulk and block deals (NSE's large-deals snapshot) into memory, no AI; each trading morning in market-data and again in the nightly, with a retry (the snapshot holds one session) |
| `deals-backfill [--days 180] [--scrips a,b]` | Past bulk and block deals from NSE's deals history (CSV, a week at a time) into the same memory as `deals-sync`, no AI; maintenance `fill-trades` |
| `insider-sync [--days 3] [--scrips a,b]` | Insider trades (SEBI PIT Reg 7 filings, each read from its XBRL) into memory, no AI; nightly with a retry, 180 days by maintenance `fill-trades` |
| `seed-calls [--scrips a,b] [--restart] [--time-budget S]` | Each universe company's last two quarters of call transcripts (else presentations) into memory through the regular analysis, no Gemini (route `memory_seed`), no card, no ledger row; resumable; from GitHub `seed-calls.yml` twice an hour 21:45-05:15 IST until done |
| `refresh-summaries [--scrips a,b]` | Rebuild each company's stored summary (overdue promises, radar, credibility) from its memory, no AI; run after a change to what summaries hold |
| `release-pruned [--dry-run]` | Held cards whose only faults were points their quote did not carry, published without those points (owner, 2026-10-21); no AI. Also from GitHub (`release-held.yml`, dry run by default) and nightly |
| `export-held [--out held.json]` | Every held card to a JSON file for the live reviews; no AI (Maintenance > export-held) |
| `refresh-card-blocks [--scrips a,b]` | Rebuild every stored card's code blocks from memory; no AI (Maintenance > refresh-card-blocks) |
| `missed-jobs` | Daily workflows GitHub did not start, for the pipeline to start; no AI |
| `critic-export --since YYYY-MM-DD [--until D] [--out critic.json]` | The shadow meaning critic's stored verdicts (R2 `evidence/critic/<news_id>.json`, beside the raw replies, one per live published card it judged) to a JSON file, for the daily audit to set beside the reviewers' verdicts; read only, no AI, no D1. The critic itself runs inside each live run (`critic.py`, route `critic` in providers.toml; `CRITIC=0` off, `CRITIC_MAX` cards a run, default 8, `CRITIC_MAX_S` seconds, default 180) |
| `apply-verdicts` | The owner's standing Wrong / Right verdicts applied to the stored cards once, no AI (verdicts saved before they acted on the card, O11, never held or released it); also from GitHub (Maintenance > apply-verdicts). A re-run keeps a verdict by itself: Wrong holds the new version with the owner's note; Right releases it only if its headline is the approved card's |
| `requeue-failed [--since D \| --days 30] [--attempts N] [--ids a,b] [--dry-run]` | Filings that used all 3 attempts get fresh attempts (after a fix), no AI; with `--ids`, the named filings re-run whatever their status (held or stale cards); also from GitHub (Maintenance > requeue-failed). Each night after 22:00 IST a live run gives the last 7 days' failed filings one more try by itself |
| `dgtr-sync [--pages N] [--scrips a,b]` | DGTR anti-dumping / countervailing / safeguard cases into the memory of the companies their notices name as applicant or supporter, no AI (module 8); once a day in a live run (`NSE_DGTR=0` off); `--pages 42` reads every listed case (OCR of scanned notices, hours) |
| `python -m bse_intel sync-universe` | NSE's main-board equity list joined to the company master by ISIN: the companies analysed (market cap ≥ `UNIVERSE_MIN_MCAP_CR`, ₹500 Cr, to join; one already in leaves below `UNIVERSE_EXIT_MCAP_CR`, ₹400 Cr; unpriced and watchlisted ones stay in) and the maps NSE discovery uses. Needed before NSE discovery; `market-data` and `sync-companies` rebuild it too. 1,778 companies on 2026-10-19 at ₹500 Cr |
| `python -m bse_intel sync-companies [--source nse\|bse] [--max-lookups N] [--refresh-industry]` | The company master from NSE's equity list (new listings, names, industry → sector lens, size label), then the universe file; `--source bse` reads BSE's scrip list and needs an Indian address |
| `python -m bse_intel market-data [--all]` | Prices, returns, liquidity, market caps (`pip install -e ".[market]"`); `--all` for every company; reports companies Yahoo has no price for |
| `python -m bse_intel price-history [--scrips ...]` | Daily prices for point-in-time card footers (laptop, before the history fill) |
| `python -m bse_intel post-mortem [--since D]` | Loop 1: T+1/T+3/T+5 return less the index after each card (nightly after market data) |
| `python -m bse_intel discover --date 2026-10-13` | Fetch and triage one day |
| `python -m bse_intel retriage --scrips A,B [--from D] [--to D]` | After a drop or date rule is narrowed: re-read those companies' filings from BSE and queue the ones today's rules no longer drop (discovery skips what is already in the noise file) |
| `python -m bse_intel process --from D --to D [--bulk]` | Work the queue for a range |
| `python -m bse_intel annual-xbrl-catchup [--max-reruns 10] [--wait 30] [--scrips A,B]` | Daily, after the close: read an annual report again once NSE lists its XBRL (filed weeks to months after the PDF). One NSE list per company with a card lacking the table, at most weekly; free routes only. Exit 3 when another pipeline command or NSE fetch is running on the machine (or a log in `data/logs` was written in the last 10 min), 2 when NSE refuses |
| `python -m bse_intel analyze-pdf FILE ...` | Analyse one local PDF and print the card |
| `python -m bse_intel backup --out DIR` | Export dossiers as JSON files |
| `python -m bse_intel health` | Configured AI targets and today's quota usage |
| `python -m bse_intel ai-check [--provider nvidia]` | One tiny real request to every configured model; prints OK, or the HTTP error and what it means |
| `python -m bse_intel models [--filter llama]` | Each provider's live model list; flags IDs in `providers.toml` it no longer serves |

## Filling history on the laptop (before go-live)

The blueprint's playbook ([docs/BLUEPRINT.md §15](docs/BLUEPRINT.md), status in
[docs/TRACKER.md](docs/TRACKER.md)):

On Windows, `pwsh -File pipeline\scripts\laptop.ps1 <command> [args]` does step 2 for any command
below (keys from the keys file, 5 workers) and logs to `data\logs`.

1. `cd web && npm run dev` (local Worker; D1/R2 persist in `data/wrangler`, git-ignored). On the
   laptop set `CF_REMOTE_BINDINGS=1` first so the Workers AI spare works.
2. In `pipeline/`, point the pipeline at it:
   `export BSE_INTEL_SINK=platform PLATFORM_API_URL=http://localhost:5173 INGEST_TOKEN=dev-local-token`
   plus one key per AI provider (`GROQ_API_KEY`, `NVIDIA_API_KEY`, `MISTRAL_API_KEY`, `ZAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`,
   and `DEEPSEEK_API_KEY` for the one paid provider, D24). A provider whose key is unset is skipped.
   Run `python -m bse_intel models` and replace any model it flags as missing in `config/providers.toml`
   (free-tier catalogues change often). The Cloudflare Workers AI target needs `npx wrangler login` in
   `web/` first, because the local Worker calls Workers AI remotely; without it that target is skipped.
3. `python -m bse_intel sync-companies && python -m bse_intel market-data --all` (industries, market caps, universe ≥ ₹500 Cr).
4. `python -m bse_intel price-history` (daily prices since a year before `BACKFILL_START`, stored in
   `data/prices`), so each history card gets the price, market cap and returns of its own date.
5. Smoke test: `python -m bse_intel backfill-companies --scrips 506525,532776,505192,500672,530019`,
   then check those companies on http://localhost:5173.
6. Full history: repeat `python -m bse_intel run --mode backfill --max-backfill-days 30` until System shows the
   backfill complete (it resumes wherever it stopped; extracted text is cached in `data/text_cache`),
   then `python -m bse_intel post-mortem --since 2025-01-01` (how each stock reacted to its cards).
7. Go live: deploy, then `PLATFORM_API_URL=<deployed> INGEST_TOKEN=<secret> python -m bse_intel sync-to-cloud`
   once a day until it reports `complete`.

## Deploy

1. **Cloudflare.**
   ```bash
   cd web
   npx wrangler d1 create bse-index-nse    # put the id in wrangler.jsonc, or in the D1_DATABASE_ID repo variable
   npx wrangler r2 bucket create bse-intelligence
   npx wrangler secret put INGEST_TOKEN    # a long random string
   npx wrangler secret put OWNER_TOKEN     # another one: owner mode (watchlist, Star/Noise) on the site
   npm run db:migrate:remote && npm run deploy
   ```
   The Worker is named `insiders`, so it serves at `https://insiders.<your-subdomain>.workers.dev`
   (this account: https://insiders.reply-bd3.workers.dev).
   Or let `.github/workflows/deploy-web.yml` do it on every push to `main`.
2. **GitHub secrets and variables.** See [SPEC §12](docs/SPEC.md#12-operations).
3. **Runner and trigger.** Since 2026-10-18 the pipeline reads NSE only and runs on GitHub's own runners
   (`pipeline.yml`, every 15 minutes on its schedule; decision D34). The repository is public, so its Actions
   minutes are free. BSE refuses datacenter addresses, so the BSE code stays an off-path backup: a
   self-hosted runner on an Indian connection (repository variable `PIPELINE_RUNNER_LABELS`) would bring it back.
4. **Free-tier limits to watch.** D1 allows 5,000,000 rows read and 100,000 rows written a day (reset 00:00 UTC);
   the pipeline counts its writes (`d1_writes:<day>`) and `d1-usage.yml` prints D1's own reads and writes by day,
   hour and query. On 21 Oct 2026 the reads ran out and the site answered 500 until the reset (OPS.md).

## Tuning without code

| File | Controls |
|---|---|
| `pipeline/config/providers.toml` | Models, limits, weights, spares, safety ceiling |
| `pipeline/config/taxonomy.toml` | Noise, calendar and fast-track rules |
| `pipeline/config/events.toml` | Per-event analyst focus and page-selection keywords |
| `pipeline/config/sectors.toml` | Sector lenses and KPIs |
| `pipeline/config/prompts/*.md` | Prompt templates |
| `pipeline/config/market.toml` | Size buckets, market-data limits |

## Daily card audit tools

`pipeline/scripts/daily_audit/`: `reviewer_prompt.txt` (the blind reviewer's instructions; placeholders WORKDIR, XX,
`<repo>`, EXTRA, FIELDS), `ext.py` (PDF text by page, run with `python -I`), `onoff_duplicates.py <workdir>` (F110 on/off over
card pairs), `onoff_ratings.py <feed.json>...` (F111 on/off over rating cards), `rates.py [--window 3]` (each day and pooled
days with 95% intervals; a single day cannot show a fix worked). How a run is done: `docs/HANDOVER.md` §4.
