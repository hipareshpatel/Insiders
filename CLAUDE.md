# Working on this repository

BSE corporate-filing intelligence platform: Python pipeline (`pipeline/`), Cloudflare Worker
with Hono and React (`web/`), shared SQL (`db/`). It must run at $0 a month on free tiers.

Read before changing anything:
- `docs/BLUEPRINT.md`: the spec (modules are numbered; "Module 35" means section 35).
- `docs/PLAN.md`: the phases from smoke test to go-live, how it runs after, open decisions and the
  single "Pending work" list. Work from that list and tick items off there.
- `docs/TRACKER.md`: decisions D1–D25, what is built and what is not.
- `docs/SPEC.md`: the design as built. `README.md`: setup and the CLI commands table.
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
- Pipeline: `cd pipeline; .venv\Scripts\activate`, then `python -m bse_intel <command>`. For long
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
- **To do, in this order (left 2026-10-17 afternoon).** The day's work was a measured loop on the same
  twenty filings: `scripts/rerun.py` picks a stratified sample from an audit file and puts those filings
  back in the queue, `process --news-ids` reads only them, so a fix is checked on the documents that
  failed rather than on a fresh sample. Keep the model weights unchanged between rounds or the
  comparison measures the models. Landed today: reading order (`sort=True`), the quote contract, NSE's
  Integrated Filing and the two insurance taxonomies (PLAN 1k and 1j, `docs/SOURCES.md`), and eight
  defects the loop found, each with a test. Still open:
  1. **Audit round 2 proper**, stratified by filing type and sector rather than newest first. Report the
     WRONG share *and* the share of WRONG the code flagged (56% at round 1). Baselines: 33% WRONG, 38%
     duplicate pairs, 40/8/3 on grounding.
  2. **ANNUAL_REPORT event type.** BSE labels it "Reg. 34 (1) Annual Report" and pass 1 types it RESULTS,
     so a 563k-character report is re-read for figures XBRL already has. Now cheaper than it looked: NSE
     serves the whole annual report machine-tagged (`/api/annual-reports-xbrl`, 631 numeric and 332 text
     facts), carrying related-party transactions, auditors, subsidiaries, continuing defaults and loans
     due from directors - three of the four buckets the prompt was going to ask a model to read.
  3. **Why a card is still held.** Round 2d measures the eight fixes; whatever is left is the next loop.
     The two known and unfixed: a figure the code itself derives (a deal size from shares x price) is
     then reported as ungrounded, and a percentage that is the sum of two stated ones (43.96 + 15) has
     no rule, while `_derived_change` and `derivable_difference` cover the other derivations.
  4. **Raise the paid weight**, then drain the 160 queued filings (4 FAILED are below max attempts and
     retry themselves). At the accuracy weights the run stalls.
  5. **PLAN 1h**: check the `quotes_dropped` facts against their filings, in one batch.
  6. **PLAN 1m**: the vision re-read, now only for pages with no text layer (2% of filings outright, 10%
     needing OCR). Reading order fixed what vision was wanted for everywhere else.
  Do not start the full backfill before the owner has reviewed the smoke test (D6) and chosen the order
  (PLAN.md item 1c). `sync-to-cloud` still cannot run: no PLATFORM_API_URL or INGEST_TOKEN for the
  deployed Worker, and laptop.ps1 hardcodes both to localhost.
- The site shows nothing with the default "Last 7 days" range while the rebuild is walking history: the
  newest card is as old as the filings being processed. Use `/feed?range=all`.
- Industry fill complete (5,111 companies, 3 without an industry).
- Fix in batches during a run, not by stopping it for each bug (owner, 2026-10-16).
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
