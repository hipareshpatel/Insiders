# Working on this repository

BSE corporate-filing intelligence platform: Python pipeline (`pipeline/`), Cloudflare Worker
with Hono and React (`web/`), shared SQL (`db/`). It must run at $0 a month on free tiers.

Read before changing anything:
- `docs/BLUEPRINT.md`: the spec (modules are numbered; "Module 35" means section 35).
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
4. Commit with a clear message, `git push -u origin claude/nice-goodall-ta0sxs`, and watch CI on the PR.
5. Update `README.md` / `docs/TRACKER.md` when behaviour, commands or the test count change.

## Running locally (Windows laptop, D:\Insiders)

- Web: `cd web; npm run dev` → http://localhost:5173 (Workers AI runs remotely: needs
  `npx wrangler login`; the account's workers.dev subdomain is `reply-bd3`).
- Pipeline: `cd pipeline; .venv\Scripts\activate`, then `python -m bse_intel <command>`.
- Smoke-test backfill: `python -m bse_intel backfill-companies --scrips 506525,532776,505192,500672,530019`.
  Results are saved every 5 filings per company; re-running a filing is safe (memory replaces
  that filing's earlier entry).
- Long runs: keep the laptop awake; log to a file (e.g. `D:\backfill.log`) and check it.

## Status and next steps

- Done: all blueprint modules except 8 (DGTR) and 42 (promoter-group contagion), which have no data source.
- Smoke-test findings and their fixes: the table in `docs/TRACKER.md` ("Laptop smoke test").
- In progress: the 5-company smoke-test backfill (restarted on the save-every-5 fix); then the
  site check on localhost and a comparison with the case studies.
- Next: the full backfill; `post-mortem --since 2025-01-01`; deploy the Worker (`insiders`,
  at https://insiders.reply-bd3.workers.dev); `sync-to-cloud`.
- To confirm: Gemini free-tier limits in AI Studio (providers.toml has cautious guesses); Yahoo
  price coverage after the symbol-based lookup (`market-data`, `price-history`); `ai-check
  --provider cloudflare` after the Workers AI fix; whether `ministral-14b-2512` keeps returning no JSON.
- Keep this file and `docs/TRACKER.md` current as things change: they are the project's memory.
