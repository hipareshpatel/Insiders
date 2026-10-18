# Working on this repository

BSE corporate-filing intelligence platform: Python pipeline (`pipeline/`), Cloudflare Worker
with Hono and React (`web/`), shared SQL (`db/`). It must run at $0 a month on free tiers.

Read before changing anything:
- `docs/BLUEPRINT.md`: the spec (modules are numbered; "Module 35" means section 35).
- `docs/PLAN.md`: the phases from smoke test to go-live, how it runs after, open decisions and the
  single "Pending work" list. Work from that list and tick items off there.
- `docs/TRACKER.md`: decisions D1–D28, what is built and what is not.
- `docs/SPEC.md`: the design as built. `README.md`: setup and the CLI commands table.
- `docs/DATA_QUALITY.md`: the cleaning stages and **the routine when data is wrong** (fix the class in
  code with a test, re-run only the affected filings, never edit stored data by hand). Follow it.
- `pipeline/config/providers.toml`: AI providers, models, free-tier limits and routes; `docs/SPEC.md` §4
  explains the gateway rules. Owner decisions D13–D15 cover providers, keys and this setup; D24–D25
  the one paid route and the weights each audit round measures.

## Rules

- Branch `claude/nice-goodall-ta0sxs` only; draft PR hipareshpatel/Insiders#1. Never push to
  another branch or rewrite pushed history. `git pull` before editing: another session also
  pushes to this branch.
- API keys live only in `C:\Users\Quali\insiders-keys.ps1` (outside the repo). Never print,
  log, commit or paste a key. Dot-source the file in each new shell: `. C:\Users\Quali\insiders-keys.ps1`.
- Don't work around BSE's firewall. BSE blocks non-Indian IPs, which is why BSE work runs here.
- Every paid upgrade must stay off, with one exception the owner chose: the prepaid DeepSeek balance
  (`DEEPSEEK_API_KEY`, decision D24) that speeds up the backfill. The steady state must still cost $0,
  so never add a paid route to a path that runs every day. Don't ask the owner to verify a phone number
  with Mistral.
- No AI model names or IDs of the assistant itself in commits, PR text or code.

## How to work

1. Diagnose from logs and the local database (`data/`), not guesses. Each provider's model list
   and free-tier limits change often: check with `python -m bse_intel models` and
   `python -m bse_intel ai-check [--provider X]`, and read the provider's own docs before changing
   `providers.toml`. Prefer established models to the newest (they are often overloaded).
2. Fix the root cause, keep the change small, and match the surrounding code style.
3. Add or adjust a test. Run `python -m pytest -q` in `pipeline/` (all must pass) and
   `npx tsc -p . --noEmit` in `web/` for Worker or React changes.
4. Before committing after a `git pull` or `git stash pop`, make sure no conflict markers remain:
   `git diff --check` and `git grep -n "^<<<<<<<"` must print nothing, and the tests must pass.
   Commit with a clear message, `git push -u origin claude/nice-goodall-ta0sxs`, and watch CI on the PR.
5. Update `README.md` / `docs/TRACKER.md` when behaviour, commands or the test count change.

## Running locally (Windows laptop, D:\Insiders)

- Web: `cd web; $env:CF_REMOTE_BINDINGS = '1'; npm run dev` → http://localhost:5173. Workers AI
  runs remotely only with that variable set (vite.config.ts overrides `remote: true`), and needs
  `npx wrangler login`; the account's workers.dev subdomain is `reply-bd3`. Vite hot-reloads Worker
  code changes, so a pull rarely needs a restart. Avoid restarting it during a backfill: the
  pipeline's retries to the Worker last about 14 s and a remote-mode start takes about 12 s.
- Pipeline: `cd pipeline; .venv\Scripts\activate`, then `python -m bse_intel <command>`. Install once with
  `pip install -e ".[dev,ocr,market]"`: without `ocr` (RapidOCR) scanned pages go to the vision route, 6 a document. For long
  runs use `pwsh -File pipeline\scripts\laptop.ps1 <command> [args]`: it loads and trims the keys,
  points the pipeline at the local site, sets 5 workers and logs to `data\logs\<command>-<time>.log`.
- Smoke-test backfill: `python -m bse_intel backfill-companies --scrips 506525,532776,505192,500672,530019`.
  Results are saved every 5 filings per company; re-running a filing is safe (memory replaces
  that filing's earlier entry).
- Backfill runs use `$env:PIPELINE_WORKERS = '5'` (decision D18); the gateway still paces each model.
- Long runs: keep the laptop awake; log to a file (e.g. `D:\backfill.log`) and check it.

## Status and next steps

- Done: all blueprint modules except 8 (DGTR) and 42 (promoter-group contagion), which have no data source.
- Smoke-test findings and their fixes: the table in `docs/TRACKER.md` ("Laptop smoke test").
- **State at 2026-10-16 19:30 (laptop awake; the rebuild is running).** Round 0 checked every card of
  both smoke tests (177) against its PDF: 95 wrong, 56 minor, 26 OK. The error classes were fixed in code
  (XBRL results from BSE's results archive, unit-slip correction, YoY/QoQ from XBRL, event-type rules,
  signal-verdict checks, D20 one card per results quarter), all ten companies were reset, and the rebuild
  was re-audited: **round 1, 98 cards, 32 wrong / 46 minor / 20 OK (33% against 53%), 2.0 issues a card
  against 3.67** (`docs/audit/round-1.json`). wrong_period, invented, unit_scale and signal_verdict all
  roughly halved or better; arithmetic and direction did not move, because two of our own fixers were
  writing wrong numbers over right ones (D25, now guarded against the filing's own figures).
- **To do, in this order (left 2026-10-17 evening, owner out of tokens; local tests may still be running).**
  The extraction benchmark is the current work. Everything is in `docs/bench/` (reports, score tables,
  answer keys) and `pipeline/scripts/bench_*.py`; PDFs and raw engine outputs are local in `data/bench/`.
  Measured (scorer audited independently, then reproduced exactly - see docs/bench/scorer-audit.md):
  results statements, 195 printed figures: **RapidOCR 98.5%** on the right row and column, PyMuPDF
  reading-order text (what we run) 80.0%, pdfplumber/pymupdf4llm/combinations 56-80%, MinerU standard
  ~100% on 7 filings but ~1 min/page and 2.7 GB, MinerU basic 69%. Non-results pages (84 pages, 14 types,
  page's own text layer as key): RapidOCR 92.3% figures exact at 200 dpi, 88.7% at 150, 92.0% at 300;
  weakest on credit ratings (79%) and "other" (86%); ~1 in 10 bracketed negatives loses its brackets.
  1. **Done 2026-10-17: the complicated-pages test** (docs/bench/hard-pages-results.txt). 7 pages, key from
     two independent readers (1,063 cells, all agreed). Figures on their own line: text layer 60%, pipeline
     OCR 98%, vision route 97%; whole rows with nils kept: 49% / 53% / 77%. Vision silently swaps digits in
     small print (7,993 read as 7983; 2.4% of its figures are not on the page, OCR 0.8%) and costs 13-83 s
     and a free-tier request a page. OCR drops thin cells - a "-" nil, "Nil" - so a later figure slides a
     column; the text layer keeps them but has no rows on rotated or garbled pages.
  2. **Done 2026-10-17: the pipeline's OCR is the benchmarked one.** `ocr.py` now runs rapidocr 3.10 with the
     measured settings, takes out page tilt, clusters rows on a running centre, repairs half-lost brackets,
     and turns a sideways page upright. Hard pages 36% -> 98% figures on their line; ~4-5 s a page.
     Install with `pip install -e ".[ocr]"` (the extra is now `rapidocr>=3.10`, not rapidocr_onnxruntime).
  2a. **Done 2026-10-17: OCR is the first reader on pages of figures** (D29; 15+ amounts on the page). Its
     rows are checked cell by cell against the text layer: a PDF-text line with exactly the row's figures
     is the row; otherwise nils OCR dropped go back and garbled figures are taken from the layer; a scan's
     invisible OCR layer never overrules. Sideways pages' text layers are rebuilt in rows. Hard pages: rows
     intact 77% (vision 77%, text layer 49%), figures in column order 95% (vision 85%). Prose pages keep the
     text layer. Open: nils on scanned grids (governance grid 4/20 rows, vision 14/20).
  3. **Done 2026-10-17: loop rounds 3a-3b** (docs/audit/loop-2026-10-17.md). OCR-first lost no figure a
     card states and made two cards' rows quotable. Found and fixed on the way: Jubilant's own Q4FY24 XBRL
     tagged at a tenth of its value (F54, `xbrl.fix_scale`; cards said revenue +979% YoY), raw answers never
     stored (F55), and the YoY/QoQ check holding real full-year and loss changes (all 10 such holds were
     false). 3b: 15 cards, 6 held. 3c (computed figures, rounding, YoY period, two-column and near quotes):
     15 cards, 5 held.
  3a. **Done 2026-10-18: audit of every discard and hold path** (owner; `docs/audit/discard-paths.md`, funnel in
     `funnel-2026-10-18.md`, re-run with `pipeline/scripts/funnel/`). 21 defects fixed with tests; the biggest
     losses of right cards were scale-block figures held as unfound and D20 ownership. Open items are listed
     there (pass 2's reason not stored, annual reports, memory facts after reclassification, repeat M&A cards).
     **Re-run done 2026-10-18** (`docs/audit/rerun-held-2026-10-18.md`, F58): held 118 -> 51, published
     333 -> 381, 10 of the 19 card-less quarters now have a card; six wrong duplicate merges found and fixed
     (D20 claim by a meeting notice, a repeat check blind to the attachment). Round 3d (the 51 still held, those
     six, the 31 annual-report filings): **43 held, 400 published** (from 333). What still holds a card:
     the quote contract on figures from memory or the scale block, and the annual-report path (lakh,
     standalone vs consolidated) until NSE's annual-report XBRL is read. Also new today: a memory insight
     naming the wrong period is dropped (card kept); no second opinion for quote wording alone.
  4. **Done 2026-10-18: ANNUAL_REPORT event type and its own XBRL** (F57). Reg 34(1) filings and annual reports
     filed with their AGM notice go to a fast track with an auditor / CARO / related-party / contingent-liability
     focus, 3x page budget, a 120 MB download cap; the Reg 36(1)(b) letters are dropped. NSE's annual-report XBRL
     (`annual_xbrl.py`, docs/SOURCES.md) is fetched for the report's year and put in front of the text: the
     statements in crore on a named basis, related parties by party, KMP pay, contingent liabilities, loss-making
     group entities, the auditor's opinion by its basis-for-opinion heading, CARO. Filler zeros are never shown
     as nil. All 31 annual-report filings re-run (docs/audit/annual-xbrl-2026-10-18.md): the 10 that got the
     table 5 published / 5 held (round 3d 4 / 6); Shivam FY25, eMudhra FY25 and Heritage FY26 released. Two table
     classes fixed after the run (the borrowings line's prior year; the contingent total sharing its line with
     the classes): re-run 5fc5b553 and 1e3f6e56 when the slot is free. The file comes weeks to months after the
     PDF, so the daily path mostly still reads the PDF alone (`NSE_ANNUAL_XBRL=0` turns it off).
  5. Raise the paid weight and drain the 160 queued filings; audit round 2; PLAN 1h.
  Do not start the full backfill before the owner has reviewed the smoke test (D6) and chosen the order
  (PLAN.md item 1c). `sync-to-cloud` still cannot run: no PLATFORM_API_URL or INGEST_TOKEN for the
  deployed Worker, and laptop.ps1 hardcodes both to localhost.
- The site shows nothing with the default "Last 7 days" range while the rebuild is walking history: the
  newest card is as old as the filings being processed. Use `/feed?range=all`.
- Industry fill complete (5,111 companies, 3 without an industry).
- Fix in batches during a run, not by stopping it for each bug (owner, 2026-10-16).
- A dead local site no longer costs a round: `laptop.ps1` refuses to start if the site does not answer,
  and the pipeline stops after three filings in a row it could not reach, leaving them queued
  rather than spending their attempts (2026-10-17: a run had marked twenty filings failed in thirty
  seconds). To check by hand in PowerShell: `curl.exe -s -o NUL -w '%{http_code}' "http://localhost:5173/api/feed?range=all"`.
- Gotchas found tonight: models copy lakh figures as crore (grounding now enforces the declared unit);
  BSE's scrip list no longer carries industry; one event can be filed up to 8 times (duplicates.py);
  commit before `git pull`, never autostash over another session's changes.
- Next: the full backfill; `post-mortem --since 2025-01-01`; deploy the Worker (`insiders`,
  at https://insiders.reply-bd3.workers.dev); `sync-to-cloud`.
- Confirmed 2026-10-16: Yahoo coverage 97.6% (4,988 of 5,111); `ai-check` passes for Cloudflare;
  Gemini per-minute limits (15/min Flash-Lite, 5/min 3.6 Flash, read from Gemini's 429 quota detail
  and AI Studio); the duplicate rule skips 91 of the 543 smoke-test filings, all exact repeats.
- To confirm: Gemini daily limits (Google publishes none; a per-day 429 shows the value on the
  System page); whether `ministral-14b-2512` keeps returning no JSON (1 in the first 10 min).
- Keep this file and `docs/TRACKER.md` current as things change: they are the project's memory.
