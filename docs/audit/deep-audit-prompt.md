# Deep audit: the brief each auditor works from

Owner, 21 Oct 2026: "a slow audit of every code line, website, workflow and everything, to find the issues of the
kind we met so far and the improvements that would raise output quality, code quality and the website. Not a surface
level one: everything must be looked at as critical." Seven auditors, one per area below, each reading every line of
its area. A consolidation pass then removes duplicates, checks every HIGH finding independently, and turns the
confirmed ones into fixes, each under the owner's standing rule (a fix that makes a check accept more gets the on/off
audit over stored cards and an independent sample; no AI used for testing).

## Rules for every auditor

1. **Read every line in your scope**, top to bottom, not a sample and not by grep alone. List at the end every file
   you read with its line count, so coverage can be checked. A file you could not finish is named as such.
2. **Evidence, not impressions.** Every finding cites `path:line`, quotes the code, and gives a concrete failure
   scenario: the input or state, and the wrong output or crash that follows. Where you can, confirm it: run the
   function in a scratch script (`cd pipeline && PYTHONPATH=src /home/user/Insiders/pipeline/.venv/bin/python -I ...`
   from a scratch directory), run the tests, or check a live example read-only on
   https://insiders.reply-bd3.workers.dev (`/api/feed`, `/api/cards/<id>`, `/api/company/<scrip>`, `/api/system`,
   `/api/review`). Mark each finding CONFIRMED (you reproduced it or saw it live) or PLAUSIBLE (read, not reproduced).
3. **Never** call an AI model API, write to the live database, push, or edit repository files. Scratch work goes to
   `/tmp/claude-0/-home-user-Insiders/f30268c6-b725-5315-957d-dec11f4670c9/scratchpad/deep-audit/<area>/`.
   Downloaded filings go in their own new directory and are read with `python -I`.
4. **Look for the classes we have already been hurt by**, and for their cousins elsewhere:
   - a figure from the wrong period or column (restated comparatives taken from memory; YoY against the wrong year;
     a comparative "printed" check fooled by a stray number);
   - unit and scale slips (lakh/crore/million/rupees; Indian digit grouping; a table header's unit not carried);
   - scope slips (a segment, a region, a subsidiary or a parent's letter read as the company);
   - direction and sign (a negative "change in inventories", tax below PBT, exceptional gain vs charge; tone for the
     counterparty instead of the shareholder);
   - an outcome or stage the filing does not state (reaffirmed shown as an upgrade, approval shown as completion);
   - duplicates (the same event filed twice, typed differently, read in a different order, or by parallel workers);
   - memory pollution (another entity's facts, an auditor's name as a former name, a sibling filing treated as history,
     facts from a filing whose card was later discarded);
   - checks that silently accept too much (a match anywhere in the text, tolerance too wide) or reject right cards;
   - state that only lives in the browser or one process (the Re-run button), counters that miss writers (D1 writes),
     caps shown as totals (Needs review · 100);
   - scheduled work that never runs, runs twice, or fails quietly; a retry that spends quota and loses the result;
   - free-tier limits (D1 rows, R2, Gemini/Z.AI/OpenRouter quotas) hit without warning;
   - an AI step fed too little or the wrong context, or instructions that conflict or are too long.
5. **Then look for what is missing**: improvements that would make cards more often right and more useful to a
   shareholder, the code simpler or safer, the site faster or clearer. Each with the expected effect and its cost.
6. **Severity**: HIGH = a published card or stored memory can be wrong, data can be lost, the pipeline can stop, a
   secret can leak, or a limit can be hit; MEDIUM = degraded output, silent failure, wasted quota, a misleading UI;
   LOW = code quality, clarity, small UX. Say how many live cards a finding plausibly touches when you can estimate it.
7. **No fixes in code.** Propose each fix in a few lines (what, where, the test that proves it), and say whether it
   makes any check accept more (then it needs the owner's audit rule).

## Output

Write `findings.json` (a list of `{id, area, severity, status, title, path, line, evidence, scenario, live_example,
fix, accepts_more, effect}`) and `report.md` (the top findings in plain language first, then coverage) into your
scratch folder, and return a summary of at most 400 words: counts by severity, the ten most serious findings in one
line each, and the files you could not finish.

## The seven areas

- **A. Intake and extraction**: `nse.py`, `universe.py`, `company_master.py`, `rules.py`, `duplicates.py`, `extract.py`,
  `ocr.py`, `xbrl.py`, `event_xbrl.py`, `annual_xbrl.py`, `governance_xbrl.py`, `raw.py`, `periods.py`, `timeutil.py`,
  `bse.py` (off path; check only that nothing on the live path calls it), `event_catchup.py`, `annual_catchup.py`.
- **B. The AI layer**: `pipeline/config/prompts/*.md`, `pipeline/config/providers.toml`, `prompts/engine.py`,
  `ai/*.py` (gateway, packer, providers, repair), `models.py`; how pass 1, pass 2, the second opinion, verify, the
  timeline route and the seeds use them; what each model is fed (memory view, SCALE, peers, text selection and budget)
  and whether it is the best use of the free quota.
- **C. Checks and card building**: `grounding.py`, `quality.py`, `trust.py`, `computed.py`, `results_card.py`,
  `scoring.py`, `gate.py`, `signals.py`, `impact.py`, `quant.py`, `card_context.py`, `card_refresh.py`, `directions.py`,
  `causes.py`, `forensics.py`, and the card assembly in `pipeline.py`.
- **D. Memory**: `dossier.py`, `radar.py`, `call_summary.py`, `call_seed.py`, `seed.py`, `governance_memory.py`,
  `learning.py`, `pledges.py`, `dgtr.py`, `prices.py`, `market.py`, `technicals.py`, `yahoo.py`.
- **E. Orchestration, storage and operations**: `pipeline.py` (run loop, queue, budgets, parallel workers, commit,
  retries), `cli.py`, `sync.py`, `requeue.py`, `settings.py`, `sinks/*.py`, `db/` (every migration, statement and
  query), `web/worker/internal.ts`, `web/worker/sql.ts`, every `.github/workflows/*.yml`; D1 rows per filing, R2 use,
  failure modes, concurrency, secrets handling, schedules and their records.
- **F. Website**: `web/worker/public.ts`, `owner.ts`, `index.ts`, `ai.ts`, `env.ts`, every file under `web/src/` and
  `web/shared/`; correctness of what each page shows, caching and the R2 snapshot, the owner token, performance,
  mobile layout, accessibility, empty and error states, search, and how a shareholder reads a card in ten seconds.
- **G. Tests, docs and config truth**: `pipeline/tests/`, `web/test/`, `pipeline/scripts/`, `docs/*.md` against the
  code as it is (claims the code no longer backs, commands that no longer exist, counts that drifted), dead code,
  config the code never reads, and gaps where a class above has no test.
