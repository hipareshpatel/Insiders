# Working on this repository

BSE corporate-filing intelligence platform: Python pipeline (`pipeline/`), Cloudflare Worker
with Hono and React (`web/`), shared SQL (`db/`). It must run at $0 a month on free tiers.

Read before changing anything:
- `docs/BLUEPRINT.md`: the spec (modules are numbered; "Module 35" means section 35).
- `docs/PLAN.md`: the phases from smoke test to go-live, how it runs after, open decisions and the
  single "Pending work" list. Work from that list and tick items off there.
- `docs/TRACKER.md`: decisions D1–D15, what is built and what is not.
- `docs/SPEC.md`: the design as built. `README.md`: setup and the CLI commands table.
- `pipeline/config/providers.toml`: AI providers, models, free-tier limits and routes; `docs/SPEC.md` §4
  explains the gateway rules. Owner decisions D13–D15 in the tracker cover providers, keys and this setup.

## Rules

- Branch `claude/nice-goodall-ta0sxs` only; draft PR hipareshpatel/Insiders#1. Never push to
  another branch or rewrite pushed history. `git pull` before editing: another session also
  pushes to this branch.
- API keys live only in `C:\Users\Quali\insiders-keys.ps1` (outside the repo). Never print,
  log, commit or paste a key. Dot-source the file in each new shell: `. C:\Users\Quali\insiders-keys.ps1`.
- Don't work around BSE's firewall. BSE blocks non-Indian IPs, which is why BSE work runs here.
- Every paid upgrade must stay off. Don't ask the owner to verify a phone number with Mistral.
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
- Pipeline: `cd pipeline; .venv\Scripts\activate`, then `python -m bse_intel <command>`.
- Smoke-test backfill: `python -m bse_intel backfill-companies --scrips 506525,532776,505192,500672,530019`.
  Results are saved every 5 filings per company; re-running a filing is safe (memory replaces
  that filing's earlier entry).
- Backfill runs use `$env:PIPELINE_WORKERS = '5'` (decision D18); the gateway still paces each model.
- Long runs: keep the laptop awake; log to a file (e.g. `D:\backfill.log`) and check it.

## Status and next steps

- Done: all blueprint modules except 8 (DGTR) and 42 (promoter-group contagion), which have no data source.
- Smoke-test findings and their fixes: the table in `docs/TRACKER.md` ("Laptop smoke test").
- In progress: the 5-company smoke-test backfill (restarted on the save-every-5 fix); then the
  site check on localhost and a comparison with the case studies.
- Next: the full backfill; `post-mortem --since 2025-01-01`; deploy the Worker (`insiders`,
  at https://insiders.reply-bd3.workers.dev); `sync-to-cloud`.
- Confirmed 2026-10-16: Yahoo coverage 97.6% (4,988 of 5,111); `ai-check` passes for Cloudflare;
  Gemini per-minute limits (15/min Flash-Lite, 5/min 3.6 Flash, read from Gemini's 429 quota detail).
- To confirm: Gemini daily limits (Google publishes none; a per-day 429 shows the value on the
  System page); whether `ministral-14b-2512` keeps returning no JSON (1 in the first 10 min).
- Keep this file and `docs/TRACKER.md` current as things change: they are the project's memory.
