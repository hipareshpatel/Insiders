# BSE Corporate Intelligence & Persistent Memory Platform

Every BSE corporate filing, triaged and analysed against a living memory of each
company: what happened, why it matters given what management said before, what to
watch next. It runs on free tiers.

- **Pipeline** (`pipeline/`, Python). Fetches BSE announcements, drops noise by
  rules, gatekeeps ambiguous filings, extracts PDF text (OCR for scans), and analyses
  material filings through a 6-provider free AI gateway with a 95% quota ceiling. It
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

> Summaries of public BSE disclosures. Not investment advice.

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
pip install -e ".[dev]"
python -m pytest -q              # 220 tests

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
| `python -m bse_intel sync-companies` | BSE's active equity list (industry → sector lens), then the universe file |
| `python -m bse_intel market-data [--all]` | Prices, returns, liquidity, market caps (`pip install -e ".[market]"`); `--all` for every company; reports companies Yahoo has no price for |
| `python -m bse_intel price-history [--scrips ...]` | Daily prices for point-in-time card footers (laptop, before the history fill) |
| `python -m bse_intel post-mortem [--since D]` | Loop 1: T+1/T+3/T+5 return less the index after each card (nightly after market data) |
| `python -m bse_intel discover --date 2026-10-13` | Fetch and triage one day |
| `python -m bse_intel process --from D --to D [--bulk]` | Work the queue for a range |
| `python -m bse_intel analyze-pdf FILE ...` | Analyse one local PDF and print the card |
| `python -m bse_intel backup --out DIR` | Export dossiers as JSON files |
| `python -m bse_intel health` | Configured AI targets and today's quota usage |
| `python -m bse_intel ai-check [--provider nvidia]` | One tiny real request to every configured model; prints OK, or the HTTP error and what it means |
| `python -m bse_intel models [--filter llama]` | Each provider's live model list; flags IDs in `providers.toml` it no longer serves |

## Filling history on the laptop (before go-live)

The blueprint's playbook ([docs/BLUEPRINT.md §15](docs/BLUEPRINT.md), status in
[docs/TRACKER.md](docs/TRACKER.md)):

1. `cd web && npm run dev` (local Worker; D1/R2 persist in `data/wrangler`, git-ignored).
2. In `pipeline/`, point the pipeline at it:
   `export BSE_INTEL_SINK=platform PLATFORM_API_URL=http://localhost:5173 INGEST_TOKEN=dev-local-token`
   plus one key per AI provider (`GROQ_API_KEY`, `NVIDIA_API_KEY`, `MISTRAL_API_KEY`, `ZAI_API_KEY`, `GEMINI_API_KEY`).
   Run `python -m bse_intel models` and replace any model it flags as missing in `config/providers.toml`
   (free-tier catalogues change often). The Cloudflare Workers AI target needs `npx wrangler login` in
   `web/` first, because the local Worker calls Workers AI remotely; without it that target is skipped.
3. `python -m bse_intel sync-companies && python -m bse_intel market-data --all` (industries, market caps, universe ≥ ₹100 Cr).
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
   npx wrangler d1 create bse-index    # put the id in wrangler.jsonc, or in the D1_DATABASE_ID repo variable
   npx wrangler r2 bucket create bse-intelligence
   npx wrangler secret put INGEST_TOKEN    # a long random string
   npx wrangler secret put OWNER_TOKEN     # another one: owner mode (watchlist, Star/Noise) on the site
   npm run db:migrate:remote && npm run deploy
   ```
   The Worker is named `insiders`, so it serves at `https://insiders.<your-subdomain>.workers.dev`
   (this account: https://insiders.reply-bd3.workers.dev).
   Or let `.github/workflows/deploy-web.yml` do it on every push to `main`.
2. **GitHub secrets and variables.** See [SPEC §12](docs/SPEC.md#12-operations).
3. **Runner.** BSE's API refused a non-Indian datacenter IP in testing. Run the
   pipeline on a self-hosted runner on an Indian connection: register the runner and
   set the repository variable `PIPELINE_RUNNER_LABELS` to `["self-hosted","linux"]`.
   The repository is private, as it should be with a self-hosted runner.
4. **Trigger.** cron-job.org → `POST /repos/{owner}/{repo}/actions/workflows/pipeline.yml/dispatches`
   every 15–30 minutes, using a fine-grained PAT with Actions read/write on this
   repository only.

## Tuning without code

| File | Controls |
|---|---|
| `pipeline/config/providers.toml` | Models, limits, weights, spares, safety ceiling |
| `pipeline/config/taxonomy.toml` | Noise, calendar and fast-track rules |
| `pipeline/config/events.toml` | Per-event analyst focus and page-selection keywords |
| `pipeline/config/sectors.toml` | Sector lenses and KPIs |
| `pipeline/config/prompts/*.md` | Prompt templates |
| `pipeline/config/market.toml` | Size buckets, market-data limits |
