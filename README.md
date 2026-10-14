# BSE Corporate Intelligence & Persistent Memory Platform

Every BSE corporate filing, triaged and analysed against a living memory of each
company: what happened, why it matters given what management said before, what to
watch next. It runs on free tiers.

- **Pipeline** (`pipeline/`, Python). Fetches BSE announcements, drops noise by
  rules, gatekeeps ambiguous filings, extracts PDF text (OCR for scans), and analyses
  material filings through a 5-provider free AI gateway with a 95% quota ceiling. It
  checks every number against the source, re-computes every quantified estimate from
  its shown working, merges facts into per-company dossiers with provenance, computes
  signals (promise vs delivery, dilution, working capital,
  metric shifts), and publishes cards to the web app.
- **Web** (`web/`, Cloudflare Worker). A Hono API over D1 and R2, and a React app:
  a live feed of compact filing rows that expand into the full card, a Results table,
  company pages (overview, results scorecard, promise tracker, timeline, filings), a
  catalyst calendar and a system monitor. The website is the only distribution
  channel.
- **Shared SQL** (`db/`). One schema and one set of statements, used by both.

The design, and what changed from the original brief, is in
**[docs/SPEC.md](docs/SPEC.md)**.

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
python -m pytest -q              # 84 tests

# 3. Fictional demo data, written through the real pipeline into the local Worker
BSE_INTEL_SINK=platform PLATFORM_API_URL=http://localhost:5173 \
INGEST_TOKEN=dev-local-token python scripts/seed_demo.py
```

The demo companies are invented ("Demo … Ltd", scrip codes 9990xx). The seeder fakes
only BSE and the AI replies; rules, extraction, prompts, gateway, grounding, memory,
signals and storage all run for real.

Analyse a real PDF you have locally (needs at least one AI key):

```bash
export NVIDIA_API_KEY=...  # and/or GROQ_API_KEY, MISTRAL_API_KEY, ZAI_API_KEY
python -m bse_intel analyze-pdf results.pdf --scrip 500000 --company "Some Ltd" \
  --headline "Unaudited Financial Results" --event-type RESULTS --industry "Cement & Cement Products"
```

## Pipeline commands

| Command | Does |
|---|---|
| `python -m bse_intel run [--mode live\|backfill\|all] [--time-budget 2700]` | One scheduled run |
| `python -m bse_intel discover --date 2026-10-13` | Fetch and triage one day |
| `python -m bse_intel process --from D --to D [--bulk]` | Work the queue for a range |
| `python -m bse_intel analyze-pdf FILE ...` | Analyse one local PDF and print the card |
| `python -m bse_intel market-data` | Refresh prices, returns and market caps (`pip install -e ".[market]"`) |
| `python -m bse_intel sync-companies` | Load BSE's active equity scrip list |
| `python -m bse_intel backup --out DIR` | Export dossiers as JSON files |
| `python -m bse_intel health` | Configured AI targets and today's quota usage |

`BSE_INTEL_SINK=local` (the default) writes to `.local-data/` (SQLite + files).
`BSE_INTEL_SINK=platform` writes to the deployed Worker.

## Deploy

1. **Cloudflare.**
   ```bash
   cd web
   npx wrangler d1 create bse-index    # put the id in wrangler.jsonc, or in the D1_DATABASE_ID repo variable
   npx wrangler r2 bucket create bse-intelligence
   npx wrangler secret put INGEST_TOKEN    # a long random string
   npm run db:migrate:remote && npm run deploy
   ```
   Or let `.github/workflows/deploy-web.yml` do it on every push to `main`.
2. **GitHub secrets and variables.** See [SPEC §12](docs/SPEC.md#12-operations).
3. **Runner.** BSE's API refused a non-Indian datacenter IP in testing. Run the
   pipeline on a self-hosted runner on an Indian connection: register the runner and
   set the repository variable `PIPELINE_RUNNER_LABELS` to `["self-hosted","linux"]`.
   This repository is public; consider making it private before attaching a
   self-hosted runner.
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
