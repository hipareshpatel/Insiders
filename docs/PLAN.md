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
| Weekdays after the close | `market-data`, then `post-mortem`, then `annual-xbrl-catchup --wait 30` | laptop |
| Weekly | `sync-companies`; `backup` of dossiers | laptop / GitHub Actions |
| Daily glance | System page: queue, failures, per-provider quota, review queue | owner |
| Monthly | `models` and `ai-check`: replace retired models in `providers.toml` | laptop |

## Decisions still open

0. **Run everything on GitHub (owner's aim, D27).** Repo public, keys as GitHub secrets, an external free
   scheduler. NSE, Yahoo and RapidOCR all work on a GitHub-hosted runner (probed 2026-10-17); BSE refuses it
   (HTTP 403), so items 1 and 2 below stand for the BSE half until a re-test after the repo is public says
   otherwise. `runner-probe.yml` and `ocr-probe.yml` re-run the checks from the Actions tab.
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
| 1 | Rebuild both smoke tests (10 companies, reset 2026-10-16 06:30 after the card-vs-PDF audit) and re-audit a sample: rebuild running, **audit round 1 done** (98 cards, 33% wrong against round 0's 53%; `docs/audit/round-1.json`, D25). Still to do: the owner reviews the site against the case studies | Laptop, then owner | Phase 1 |
| 1o | ~~Measure an NLI check on the audited cards~~ **Measured and rejected 2026-10-17.** A local NLI model (MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli) scored each card sentence against its quote or the filing window it rests on. On 20 hand-built pairs it caught 18 of 20 misreadings with no false flags, but on the round-1 audited cards it flagged all 15 WRONG cards the code had missed and also 95% of the 20 OK cards, against the rule fixed in advance (at most 15%): real card sentences are analytical and lean on more than their quote, so the model reads them as unsupported. Script and test removed. | Laptop | done |
| 1n | **Done 2026-10-17 (D26).** Scanned and unreadable pages are OCR'd by RapidOCR on the CPU at 200 dpi, up to 20 pages a document, with the vision route as fallback. Laptop: run `pip install -e ".[ocr]"` once in `pipeline\.venv` after pulling, or it keeps the vision route and 6 pages | Laptop | Phase 1 |
| 1m | **Vision re-read for a held card** (owner, 2026-10-17). A card held because its numbers could not be verified goes to a vision model with the page that carries the disputed figure, and only that page. The parts already exist: `extract.py` renders a page to PNG and calls the `vision` route, which has three free providers (z.ai glm-4.6v-flash, mistral-small-2603, gemini-3.1-flash-lite) and a per-document budget; migration 0009 gives the held queue. What is missing is pointing it at a figure rather than at a scanned page: locate the page by searching each page's text for the figure or its quote (needs item 1, the quote contract, to know which figure is disputed and what sentence it claims), render it, ask for the row with its column header and the unit header above the table, then re-run the checks. **It must be verified against something other than the text that was already wrong**, or it only swaps one unchecked reading for another: XBRL for the period where there is one, the cumulative identity (`dossier.unreconciled`), the declared unit on that page, or a second vision provider. That is also why it pays most where XBRL is absent - annual reports, the NBFC integrated filings of 1k, and scans. Scope it to held cards, not every card: images cost far more tokens than text and Gemini's vision shares its daily quota with pass 1. Expect it to address the layout classes - unit_scale 22, wrong_column 14, direction 17 and part of arithmetic 40 of round 1's 172 issues - and not the judgement ones: invented 30, event_type 10, signal_verdict 16, nor the 21% of cards that looked clean to the code and were still wrong | Laptop | Phase 1, after item 1 |
| 1k | **Done 2026-10-17.** SEBI's Integrated Filing replaced the standalone results filing for quarters from March 2025; it was never unfetchable, it is served from a different NSE endpoint (`/api/integrated-filing-results`), which the owner pointed out. Both surfaces are read and merged, so Bajaj Finance has every quarter from 2025 on. Taxonomies are named in each instance's namespace; see `docs/SOURCES.md` | Laptop | Done |
| 1i | Results XBRL from NSE when BSE's archive gives nothing. Measured 2026-10-16 across industries: the commercial template reads 22 metrics (Infosys, Apollo, Tata Communications, Nava) and a bank 13 after the banking tags, but BSE's `NBFCUploadDocument` path returns its HTML homepage to a plain fetch and 0 bytes through `bse.download`, so Bajaj Finance and Max Financial silently get no machine-tagged figures at all. NSE's `corporates-financial-results` serves the same quarters and both parse to 23 metrics with the tag map we already have, so `seed_results` should fall back to NSE per quarter (NseClient already warms up, paces and downloads). Affects the financial-services block: ~683 companies, ~198 of them at Rs 1,000 Cr and above | Laptop | Phase 1 |
| 1j | **Done 2026-10-17.** General and life insurance both have tag maps, added as overlays on the commercial one because the same element name means different things across templates. ICICI Lombard 4 metrics -> 30, HDFC Life 8 -> 30, both reconciling (PBT - tax = PAT), with the combined ratio read as a percentage | Laptop | Done |
| 1g | Error classes round 1 left open: filings read without XBRL still carry 10x slips (the annual-report path; to measure on the first ANNUAL_REPORT cards, F57). Fixed: the DISTRESS template's "barely covers interest" at 0.2x and -0.0x (d5985f1); an approval called "met" on a disclosure about the approval process (6c8b5e3); debt converted into shares read as a "raise" against net worth (2026-10-18: now "conversion", against market cap only; warrants and convertibles issued for cash stay raises) | Laptop | Phase 1 |
| 1h | Check the 48 `quotes_dropped` facts from the rebuild against their filings in one batch | Laptop | Phase 1 |
| 1f | Audit classes not fixable by a rule (docs/audit/README.md "Still open"): invented facts (stricter prompt + claim checks), prose arithmetic, standalone/consolidated mixing, wrong table row, OCR losing brackets on negatives, stale market cap in signals | Laptop | Phase 1 |
| 1a | Retry the one Kanoria long document (2025-05-21) that failed on every long-context provider; it is retried automatically by the next run | Laptop | Phase 1 |
| 1b | Measure 5 vs 3 workers over a full hour (filings/hour, 429 share) and keep the better (D18); the first 14 min gave ~125/h vs ~95/h, 9% 429s before the Z.ai one-at-a-time cap | Laptop | Phase 1 |
| 1d | ~~Thinking for the Nemotron models~~ decided by the owner 2026-10-16 (D21): switched off for Pass 2 on every route; an A/B on the same 20 filings, same model and prompt, showed 150–760 s a card with thinking on (1 in 3 timed out at 300 s) against 23–68 s with it off at similar grounding scores. OpenRouter's Nemotron models (spares and weight 1 in bulk) keep their defaults until probed | Laptop | done |
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
| 14 | **Last item, once everything is live and up to date:** re-measure thinking on the Nemotron models (and OpenRouter's), A/B on a fresh audited set including accuracy against the PDFs, and re-enable where it pays (undo: remove the `extra_body` line and set `json_mode = true` on the three NVIDIA entries in `providers.toml`; a test pins the current setting) | Laptop, owner decides | after Phase 4 |
| 15 | **Ownership history from NSE's shareholding XBRL** (probed 2026-10-16, tracker F50: `/api/corporate-share-holdings-master?index=equities` gives a direct `.xml` per filing and our parser reads it unchanged). Build a polite NSE client (browser headers, one warm-up visit, 3–5 s pacing, hard stop on 401/403/429, raw bytes kept by checksum) and a `sync-shareholding` command: promoter, pledge, FII, DII and retail holders per quarter into memory, by ISIN or symbol. Covers 96% of companies above ₹1,000 Cr; BSE-only micro caps keep having no ownership history until a BSE route is found. Until then shareholding filings stay dropped as noise | Laptop | before Phase 3 |
| 16 | **Results flash then verify.** A card written from the board-outcome PDF carries `PROVISIONAL_PDF`; a later pass fetches the quarter's XBRL (measured 2026-10-18: NSE's integrated filing follows the outcome by 5 min to 2 h 40 min the same day, docs/SOURCES.md "Timing checked live"; so check hourly for the first few hours, not at T+24h) (NSE `/api/integrated-filing-results` for dual-listed, BSE `Result_Arch_ng` otherwise) and, where a figure differs by more than 2%, replaces the numbers on the existing card and in memory instead of writing a second card. BSE's `TabResults/w` returned an empty body and is not the route | Laptop | before Phase 4 |
| 17 | Event XBRL (Reg 30 events, voting results, related-party, insider/SAST). **Source verified 2026-10-18:** NSE publishes it after the announcement (`/api/XBRL-announcements`, docs/SOURCES.md "Event XBRL"): orders, litigation, regulatory actions, director changes as exact fields. Measured 2026-10-18: median 8 minutes after the PDF, 19 of 24 within an hour, up to 21 hours; no shared key with the announcement row. Read it first for those events; the PDF only for narrative. Part of the NSE switch (item 18) | Laptop | after item 15 |
| 18 | **The NSE pipeline, online only (owner, 2026-10-18; starts now that round 3 passed the blind review).** GitHub Actions + Cloudflare, NSE only; BSE and BSE-only companies dropped (the BSE client and laptop.ps1 stay in the repo, off the daily path, as a possible future backup, until the online run has been green a week). **Universe: NSE-listed companies with market cap >= ₹100 Cr: 2,232 of our 5,111** (measured 2026-10-18 with `universe.select`: NSE `EQUITY_L.csv`, 2,605 rows, matched to the companies table by ISIN, else symbol: 2,480 matched; 2,231 at or above ₹100 Cr or watchlisted plus 1 not yet priced; 248 below the floor; 125 on NSE but not in our master, their filings set aside with that reason; 1,503 of ours above ₹1,000 Cr, 576 above ₹10,000 Cr; 666 of our ₹100 Cr+ companies are BSE-only). **Part 4 built 2026-10-19 (TRACKER F69):** results from NSE's integrated-filing XBRL per company, a 180-min wait for a live filing's file at no attempt, cards re-read when the file lands or is revised. **Part 3 built 2026-10-18 (TRACKER F68):** event XBRL joined by the same file, else by content (106 of 130 files of 13-18 Oct, none joined wrongly where the PDF is known; docs/SOURCES.md), its fields in front of the text, an order's amount, client, GST basis and execution date set by code; a live filing waits up to 90 min for its file at no attempt, a card made without it is re-read when the file lands. Director/KMP changes get no card (D30). **Go-live gate (owner, 2026-10-18): 95% of published cards right** (blind review), not 85%; after the pipeline works, the focus is card output and contextual memory. **Parts 1-2 built 2026-10-18 (TRACKER F67):** `sync-universe`, NSE discovery (`DISCOVERY_SOURCE=nse`, the default), the rule book on NSE's subjects, attachments from nsearchives. One live day (16 Oct): 515 filings, 327 queued, 159 rule-dropped, 13 below the floor, 11 NSE-only. Build, each part with tests: (1) universe from NSE's list and our market data; (2) discovery from `/api/corporate-announcements` (PDF; `hasXbrl` is true on every row and says nothing), the rule filters mapped to NSE's `desc`; (3) event XBRL first (`/api/XBRL-announcements`, types announcements / para-b / action): code takes amount, unit, counterparty, dates, new/amendment and related-party from the XML, the model writes only context; join to the announcement on a tested key (symbol+time matched 220 of 354 in the cloud probe; the XML carries ScripCode, ISIN and event date), and correct a card when its XBRL lands (median 8 min, up to 21 h); one order's notice and press release become one order; (4) results from the integrated-filing XBRL within hours, code builds the numbers, the model adds 1-2 lines; once it is in, remove the newspaper rule's exception for "Financial Results ... and Newspaper Publication" (a BSE-era case; none on NSE 13-18 Oct, measured), so any newspaper filing is dropped (owner, 2026-10-18); (5) shareholding XBRL each quarter into memory (item 15); (6) annual reports, PDF + annual-report XBRL with the catch-up; (7) `pipeline.yml` on ubuntu-latest with the owner's secrets (GROQ, NVIDIA, MISTRAL, ZAI, GEMINI, OPENROUTER, INGEST_TOKEN, PLATFORM_API_URL), a polite stop on NSE 401/403/429 that leaves filings queued and never spends attempts on network errors. Then a measured round on 14 unseen NSE companies >= ₹100 Cr (blind agent review, WRONG <= 15%, MISSED <= 2 of ~50, set before review), size the 6-month free-tier backfill from it (filings an hour, AI requests a filing, 429s; days and cost recorded here), and tell the owner when it is ready for cron-job.org | Online | now |

## Risks

- Free-tier changes: models get retired and limits change without notice. `ai-check` finds it;
  the gateway already skips disabled models and fails over.
- BSE format or access changes: the run stops after repeated refusals instead of failing filings.
- D1 write budget: bounded by design (sync is budget-aware, history stays local).
- Not built: Module 8 (DGTR) and Module 42 (promoter-group contagion). Each has a source, measured 2026-10-18 (docs/SOURCES.md): DGTR's case pages (PDF findings) and NSE's SAST Reg 31 encumbrance feed.
