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
# NSE pacing: NSE_PAUSE_SECONDS="low,high" (default 3,5; min 1 s) for every request; NSE_ARCHIVE_PAUSE_SECONDS="low,high" (0 allowed;
# unset = archive files share the API pace) for nsearchives.nseindia.com only, back to 3-5 s after a 403/429/503 (F169)
python -m pytest -q              # 1,429 tests (2 skip without the ocr extra); web: npm test (65: card text, company statements, owner holds, call takeaways, company keys, card parts, card checks)

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
| `failed-report [--since D]` | Every failed filing since the backfill start (or D), grouped by reason, with three examples each; reads only, no AI; also from GitHub (Maintenance > failed-report). The nightly requeue skips a file over the size cap |
| `dgtr-sync [--pages N] [--scrips a,b]` | DGTR anti-dumping / countervailing / safeguard cases into the memory of the companies their notices name as applicant or supporter, no AI (module 8); once a day in a live run (`NSE_DGTR=0` off); `--pages 42` reads every listed case (OCR of scanned notices, hours) |
| `python -m bse_intel sync-universe` | NSE's main-board equity list joined to the company master by ISIN: the companies analysed (market cap ≥ `UNIVERSE_MIN_MCAP_CR`, ₹500 Cr, to join; one already in leaves below `UNIVERSE_EXIT_MCAP_CR`, ₹400 Cr; unpriced and watchlisted ones stay in) and the maps NSE discovery uses. Needed before NSE discovery; `market-data` and `sync-companies` rebuild it too. 1,778 companies on 2026-10-19 at ₹500 Cr |
| `python -m bse_intel sync-companies [--source nse\|bse] [--max-lookups N] [--refresh-industry]` | The company master from NSE's equity list (new listings, names, industry → sector lens, size label), then the universe file; `--source bse` reads BSE's scrip list and needs an Indian address |
| `python -m bse_intel market-data [--all]` | Prices, returns, liquidity, market caps (`pip install -e ".[market]"`); `--all` for every company; reports companies Yahoo has no price for |
| `python -m bse_intel price-history [--scrips ...]` | Daily prices for point-in-time card footers (laptop, before the history fill) |
| `python -m bse_intel metrics --scrip X [--basis CONSOLIDATED\|STANDALONE] [--quarters N] [--json] [--file dossier.json]` | A company's metrics table (growth YoY and QoQ, margins, cost shares, last-four-quarters totals, half-year balance ratios; lenders get their own lines), worked out by code from the XBRL figures in its memory, no AI, not on any card yet (TODO 22, F141) |
| `python -m bse_intel memory-gaps [--scrips A,B] [--quarters 8] [--as-of D] [--json P] [--csv P] [--fill [--shard I/N] [--restart] [--time-budget S]]` | Universe companies whose memory lacks an NSE-XBRL revenue or PAT in the last 8 quarters past their filing deadline, and whether the latest quarter's year-ago quarter is there; no AI. `--fill` seeds those companies' results from NSE (exit 75 on refusal, 124 when the budget ends with companies left). From GitHub: Maintenance > memory-gaps (count) or memory-gaps-fill (F148) |
| `python -m bse_intel screener-fill [--scrips A,B] [--quarters 8] [--as-of D] [--apply] [--shard I/N] [--restart] [--time-budget S] [--json P] [--csv P]` | One-time (owner permission 26 Oct 2026), no AI: for each company with a memory gap, one screener.in page (the one on memory's basis, at least 3 s between requests, a plain browser User-Agent, no login) and the quarters it can fill by the rules in `screener_fill.py`. A dry run by default (counts, reasons skipped, CSV of every proposed fill with its overlap evidence); `--apply` writes them as `by="screener"` in the dossier's `screener_fill` section, which no card reads unless `MEMORY_SCREENER=1`. At most 2 shards; exit 75 on a refusal, 124 when the budget ends with companies left. From GitHub: Maintenance > screener-fill, then screener-fill-apply (F161). `MEMORY_STANDALONE_ONLY=1` (F162) makes `seed-memory` keep a quarter with no consolidated file on the standalone basis |
| `python -m bse_intel screener-download [--scrips A,B] [--day D] [--shard I/N] [--restart] [--time-budget S] [--json P]` | One-time (owner permission 26 Oct 2026), no AI, no NSE, no memory write: both screener.in pages of every universe company (`/company/<SYM>/consolidated/` and `/company/<SYM>/`; at least 3.2 s between requests per runner, a plain browser User-Agent, no login), each stored raw and gzipped in R2 at `raw/screener/<date>/<SYMBOL>_<c|s>.html.gz`. A page already stored for the date is skipped; the finished symbols are kept so a run resumes; at most 2 shards (about 3,800 requests, about 1.7 h); exit 75 on a 403, 429 or 503, 124 when the budget ends with companies left. From GitHub: Maintenance > screener-download (its own concurrency group, so it runs beside the NSE memory jobs; artifacts `screener-download-0` and `-1`) (F163) |
| `python -m bse_intel screener-crosscheck [--scrips A,B] [--day D] [--workers 8] [--no-referee] [--json P] [--csv P] [--referee-csv P] [--md P]` | Read only (no screener or NSE request, no write, no AI): memory's exchange-file figures against the stored screener pages, classed `match`, `wrong_quarter`, `scale`, `naming`, `lender_definition`, `steady_line_difference`, `mismatch`, plus memory's own `memory_period_suspect` checks and quarters either side lacks; the cached official results text is the referee (verdicts per pair; `referee.csv`). From GitHub: Maintenance > screener-crosscheck (artifact `screener-crosscheck`, nothing committed) (F163) |
| `python -m bse_intel screener-referee [--scrips A,B] [--day D] [--workers 8] [--limit N] [--time-budget S] [--json P] [--csv P] [--md P]` | Read only (no memory write, no card change, no AI, no screener request; reads R2, memory and NSE; owner 26 Oct 2026): NSE's own results XBRL as the referee of the cross-check's disagreeing pairs (every class but `match` and `naming`). The cross-check is worked out again, then each pair's company is looked up once (`financial_results`, 2 API calls at 3-5 s) and each file downloaded once (archive host on `NSE_ARCHIVE_PAUSE_SECONDS`), read on memory's basis: the period's own file (a year: the March file), else the next quarter's, else the same quarter a year on, with `official_from` saying which. Verdict `ours_matches_official`, `screener_matches_official`, `both_match`, `neither`, `no_file` (reason in the CSV) or `not_run`; a `wrong_quarter` pair also says `own_period_right`, `saved_under_wrong_quarter:<period>`, `neither_period` or `unknown`. `--limit` caps the pairs (a started company is finished). Exit 75 when NSE refuses, 124 when the time budget ends. From GitHub: Maintenance > screener-referee (artifact `screener-referee`: `referee-xbrl.csv`, `summary.json`, `screener-referee.md`) |
| `python -m bse_intel pdf-referee --csv P [--limit N] [--time-budget S] [--no-ocr] [--json P] [--out-csv P] [--md P]` | Read only (no memory write, no card change, no AI; reads NSE; owner 26 Oct 2026, TODO 61; `pdf_referee.py`): the filing PDF as the last referee of the pairs `screener-referee` left open (`--csv` is its `referee-xbrl.csv`; verdict `neither`, `no_file` or `screener_matches_official`). Each pair's results PDF is found in NSE's announcements for the period's window (the results lists carry no PDF link), downloaded once (`NseClient.fetch`, archive host on `NSE_ARCHIVE_PAUSE_SECONDS`) and read with the pipeline's own reader (text layer, local OCR on figure pages). The row (revenue, net profit, basic EPS) is read in the column of the period (group words and dates of the header, as many figures as dates), on memory's basis, in the unit the page declares. Verdict `pdf_matches_ours`, `pdf_matches_screener`, `pdf_matches_xbrl`, `pdf_matches_none`, `pdf_unsure` (a figure on the page whose column, basis or unit is not proven: never a match), `pdf_unreadable` (reason in the CSV) or `not_run`. Exit 75 when NSE refuses, 124 when the time budget ends. From GitHub: Maintenance > pdf-referee (takes the newest `screener-referee` artifact; artifact `pdf-referee`: `referee-pdf.csv`, `summary.json`, `pdf-referee.md`) |
| `python -m bse_intel text-backfill [--limit N] [--shard I/N] [--no-ocr] [--restart] [--time-budget S] [--json P]` | One-time (owner 26 Oct 2026), no AI, no card, memory or filings write: downloads the filing text of every stored card with no `text/<news_id>.json.gz` in R2 (one listing of `text/`), through the pipeline's NSE client (same headers and 3-5 s pacing) and Document reader, and writes the pipeline's own cache bytes. Local OCR on figure and scanned pages unless `--no-ocr` (those pages then keep their text layer only). Prints the cards lacking text and an estimate first; failures are kept by reason (404, cut short, too large, ZIP audio) and skipped next time unless `--restart`; at most 2 shards; exit 75 on an NSE refusal, 124 when the budget ends with filings left. From GitHub: Maintenance > text-backfill (inputs `limit`, `no_ocr`; group `maint-nse-memory`; artifacts `text-backfill-0` and `-1`) (F165) |
| `python -m bse_intel restated-report [--scrips A,B] [--json P]` | Read only (F167, owner 26 Oct 2026), no AI, no NSE, no write. Counts the quarter flow figures in memory whose restated value (a later results file's comparative column) differs from the first-filed one, by size of change, with the largest examples, and the later quarters whose stored YoY used the first-filed base. Old memory has the fields only after the seed-memory reload. Switch `MEMORY_RESTATED=1` (default off) names the restatement on a card's memory view. Workflow: Maintenance > `restated-report` (group `maint-ro-restated-report`, artifact `restated-report`) |
| `python -m bse_intel nse-selfcheck [--scrips A,B] [--json P] [--csv P]` | Read only (TODO row 60, owner 26 Oct 2026), no AI, no NSE, no write. Checks NSE's own figures in memory against themselves, exchange-file figures only: (a) a quarter's own file against the same quarter in a later file's comparative column, classed rounding / restated (several lines differing together: possible merger, discontinued operation or accounting change) / scale_suspect (single line at x10, x100 or x1000) / wrong_quarter_suspect; (b) Q1+Q2+Q3+Q4 against FY for flow metrics (quarter_sum_gap, with its size). Each `quarter_sum_gap` gets a `cause` (derived_line / one_quarter_off / restructuring_suspect / other) and, from memory's own H1, 9M and FY (stored for March-year companies, each from the Q2, Q3 and Q4 file), a year-to-date chain Q1+Q2=H1, H1+Q3=9M, 9M+Q4=FY whose first broken link names the quarter (`quarter`, `ytd_links`). Prints counts per class, per cause and per link, and the worst companies; `--csv` has every row; `--referee-csv` writes the one_quarter_off rows in the shape `pdf-referee --csv` reads (the PDF decides that quarter; artifact file `nse-selfcheck-referee.csv`). Workflow: Maintenance > `nse-selfcheck` (group `maint-ro-nse-selfcheck`, artifact `nse-selfcheck`) |
| `python -m bse_intel nse-speedtest [--companies 100] [--files 80] [--seed 26] [--json P]` | Read only (F168, owner 26 Oct 2026), no AI, writes only the JSON file. Times NSE's listing API (per company, and the all-company list) apart from the nsearchives file downloads, which run in rounds on different files at a 3-5 s, 1 s, 0.3 s, 0 s pause and with 4 workers; a round stops at the first 403/429/503 or third timeout, waits 60 s and no faster round follows. Prints files a minute per round, the fastest safe round and the projected full reload (~40,000 files) against today. Workflow: Maintenance > `nse-speedtest` (group `maint-ro-nse-speedtest`, artifact `nse-speedtest`) |
| `maintenance.yml` command `release-check` (script `python -I -X utf8 scripts/release_check.py OUT_DIR --platform [--limit N --seed 170 --sample 20 --only NAME,...]`) | Read only (F170, 26 Oct 2026), no AI, no write to D1, R2 or memory. The release check for the five card switches that are built but off, over every stored card, its text in R2 and its company's memory (the platform API, as `audit-precision`). Per switch (`ebitda_v2` = CARD_EBITDA_PROFIT_V2, `same_definition` = CARD_SAME_DEFINITION, `consolidated_only` = CARD_CONSOLIDATED_ONLY, `two_parts` = CARD_TWO_PARTS, `quote_exact` = QUOTE_EXACT_NUMBERS): `NAME.json` and `NAME.txt` (cards changed, lines added, removed, changed), `NAME-blind.json` / `NAME-blind.md` (a seeded sample of up to 20 changed cards, the off and on renderings as X and Y) and `NAME-key.json` (keep it from the reviewer); artifact `release-check`. Offline: `--cards ROWS.json --texts DIR [--dossiers DIR]`. |
| `python -m bse_intel prune-companies [--apply] [--keep-sme] [--bse-keep-min-mcap N] [--json P] [--csv P]` | Company rows that are not on NSE's equity or SME list (BSE-only equity, fund/ETF, REIT/InvIT, SME), with the memory and ledger rows each holds, and the rows kept because they hold cards or a star, and the BSE-only rows of 500 Cr or more kept and set aside (`--bse-keep-min-mcap`, 0 = off). Dry run by default (no writes). `--apply` writes `backup/prune-companies-<date>.json` to R2, reads it back, then removes the rows with no cards and their memory files. Maintenance: `prune-companies`, `prune-companies-apply` (F158) |
| `python -m bse_intel bse-verify-kept [--min-mcap N] [--limit N] [--json P] [--csv P]` | One-time, read-only: for each kept BSE-only company (stored market cap 500 Cr or more), three paced calls a company through the ported BSE adapter: status (active / suspended / delisted), current market cap, latest announcement in 90 days; a refusal stops the run and keeps the body's first 300 characters. No writes. From GitHub: Maintenance > bse-verify-kept (artifact, F160) |
| `python -m bse_intel label-memory [--scrips A,B] [--dry-run] [--json P] [--restart] [--time-budget S]` | Labels every item already in memory (file / ai / calc / unknown; design `docs/design/memory-labels.md` step 2); no AI, no NSE, no card change. `--dry-run` counts per section and label and writes nothing; a real run writes each changed memory by the safe merge and resumes after its last company (exit 124 when the budget ends with companies left). From GitHub: Maintenance > label-memory (dry run, artifact) or label-memory-apply (F150) |
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

**Maintenance groups and chaining (26 Oct 2026, F164).** Maintenance jobs wait by source and by what they write, not in one queue: `maint-nse-memory` (reads NSE or writes memory: seed-memory, memory-gaps-fill, fill-memory, fill-trades, label-memory-apply, screener-fill-apply, prune-companies-apply, text-backfill), `maint-cards` (writes cards: refresh-card-blocks, refresh-summaries, both, requeue-failed, apply-verdicts, release-pruned, export-held, export-critic), `maint-bse` (probe-bse, bse-results-test, bse-verify-kept), `maint-screener` (screener-download, screener-fill), and one group of its own for each read-only command (failed-report, memory-gaps, label-memory, prune-companies, audit-precision, release-check, screener-crosscheck). Groups run side by side; two jobs that write the same store never run together. A group keeps one waiting run, so queue one command per group. The input `then` is a comma-separated list of commands to run one after another, each started when the one before has finished and succeeded; `name:restart` passes restart=true. Example: command=memory-gaps-fill, then="seed-memory:restart" fills the gaps (all passes), then starts the seed from the first company. A command that resumes itself (seed-memory, memory-gaps-fill, screener-download, screener-fill, label-memory-apply, text-backfill) hands on only when no company is left. The table and the rules are in the header of `.github/workflows/maintenance.yml`.

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
