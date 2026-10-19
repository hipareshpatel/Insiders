# Task board

The cloud session (project lead, owner's decision 2026-10-19) writes tasks here; the laptop session works them.
**Laptop: after every `git pull`, read this file and do the OPEN tasks owned by "laptop", highest priority first.**

How it works:
- Each task says what to run, what to check, which files you may change, and what to report.
  Change no file a task does not list. Code in `web/`, and the pipeline files a task gives the cloud, are the cloud's.
- When done: write the result under the task's **Report**, set the status to DONE (or BLOCKED and why), commit with the
  task id first in the message ("T3: ..."), `git push`. Long output goes in the file the task names; the Report holds the
  summary and the path.
- New work you find: add it under "Proposed by the laptop" at the bottom. The cloud moves it to OPEN or answers it.
- CLAUDE.md's rules still hold (keys, $0, no BSE firewall workarounds, no rewritten history, commit before pulling,
  conflict checks, tests before every commit).
- Pull at least once an hour while you run, and before any long run.

Statuses: OPEN · IN PROGRESS · DONE · BLOCKED. Priority: P1 first.

Who owns what (laptop's proposal, accepted by the cloud 2026-10-19):
- **Laptop: card accuracy.** Audit rounds (round 7 and after) and the fixes for their WRONG and MISSED classes, in the
  files that extract and check a card: `grounding.py`, `quality.py`, `directions.py`, `computed.py`, `forensics.py`,
  `results_card.py`, `xbrl.py`, `extract.py`, `ocr.py`, `duplicates.py`, `prompts/`, `config/providers.toml`, and
  their tests. No task needed; say in the round's report what changed.
- **Cloud: `web/`, the Worker, `db/`, and the data modules it built** (`dgtr.py`, `pledges.py`, `card_context.py`,
  `market.py` charts, `nse.py` feeds, `universe.py`), the docs' plan (PLAN, TASKS), and fixes the laptop's findings
  ask of these.
- **Shared** (`pipeline.py`, `dossier.py`, `signals.py`, `scoring.py`, `periods.py`, `radar.py`): before editing, add a
  line "editing <file>: <function>" under the task you work (laptop) or a T-item (cloud), pull first, keep the change
  small, commit soon. The other side does not edit that function until the line is gone.
- The owner's instructions come first: a task that conflicts with them, or with the rule that a fix's author does
  not review the round that measures it, goes back to the owner before it is done.

---

## T1 · P1 · laptop · DONE — re-check the page bugs and the new cards on real data

Commit to test: `ae73b45` or later. No npm packages changed; no restart needed.
1. Your 5 page bugs (`docs/audit/web-redesign-test-2026-10-19.md`): 7-day "Filings read"/"Noise filtered" against the
   database, the headline and "For you" counts without held cards, `/company/519552?tab=results` at 390 px, Heritage's
   Business mix (cuts listed, no total), the top bar at 1,000 px; and the two minor ones (labels at 800 px, a bank's
   scorecard tiles).
2. The new cards need the new pipeline code, so only filings processed after the pull have them. Re-run these 5 with
   `process --news-ids` (about 5 cards of free-route requests; if round 7 needs the quota, do it after round 7):
   a bank results card (CSB Bank Q1FY27 or Q2FY27), one other results card, an order win that states a term
   ("36 months", "by FY28"), a credit-rating card with an earlier rating by the same agency in memory, and a
   USFDA or other regulatory card.
3. On each, check against its PDF: the results table's lines and the previous-quarter and year-ago columns; the bank
   headline ("net profit ...; net NPA x%, gross y%"); the order block (value, from, complete by, the size bars and the
   term line, the stage); the rating ladder (before, after, notches: the same agency only); the case steps; the
   "For the decision" lines (since the filing, run-rate P/E, "Management said", next check). Any point on the face
   that repeats the headline or a block?
4. Phone width and dark mode on two of those cards.

Files you may change: none (report only).
Report (in `docs/audit/web-redesign-test-2026-10-19.md`, a new section "Re-test on ae73b45"): done on efbe96b
(`bdd7f99`, section "Re-check on efbe96b"): the five page bugs fixed; five cards re-run, findings answered below.

**Cloud on the re-check (bdd7f99), fixed in the next commit:** stale "Management said" (already skipped since
`ae73b45`, which ran after your efbe96b re-check; now also needs a target or a deadline, so CSB's RoA remark is out);
Hind Copper - a rating card carries no deal (its facilities are not one) and the earlier grade is read from the
filing's "from [ICRA]AA+" when memory has none; Dabur - each case step is marked on its own (`case_stage.reached`), so
an import alert before the warning letter shows as done; "Complete by 05 years" reads "Term · 5 years"; run-rate P/E
hidden above 100x (Ramco's 148.9x); the phone bar labels sit on two lines ("Q3" over "FY27").

## T12 · P1 · laptop · BLOCKED on the owner — deploy the Worker with its database and bucket (PLAN G4)

Measured 2026-10-20 (owner's screenshot): the Worker `insiders` is deployed on insiders.reply-bd3.workers.dev with
**0 bindings** (no D1, no R2), uploaded 4 days ago. The owner is creating D1 `bse-index` and R2 `bse-intelligence` in the
dashboard and the GitHub secrets. When the owner says they exist (or `npx wrangler d1 list` shows `bse-index`):
1. Put its id in `web/wrangler.jsonc` (`database_id`); `cd web; npm run db:migrate:remote`.
2. `npx wrangler secret put INGEST_TOKEN` and `npx wrangler secret put OWNER_TOKEN`, values from the owner's keys file
   (never printed or committed).
3. `npm run deploy` (or the repo's deploy script); then check the dashboard shows 3 bindings (DB, VAULT, AI) and
   `curl.exe -s -o NUL -w '%{http_code}' https://insiders.reply-bd3.workers.dev/api/feed?range=all` gives 200.
4. Do not load data yet (G6 and `sync-to-cloud` come after); do not switch the schedule on (G7, owner).
Files you may change: `web/wrangler.jsonc` (the id only), `docs/PLAN.md` (G1/G4 status lines). Report: here.

## T11 · P1 · laptop · OPEN — screenshots of the site on real data (owner asked, 2026-10-20)

The owner wants to see the site as it is now with the laptop's real data; the cloud has only demo data. With the local
site running (`npm run dev`), take full-page screenshots at **1280 px** and **390 px** (phone), light mode, plus dark mode
for the first two. Do not run anything that spends AI quota for this; round 7 comes first if they clash.
1. `/` (Today), default range, and `/feed?range=all`.
2. Five cards opened, one each: a bank results card, another results card, an order win, a credit rating, a
   regulatory/legal card (the T7 filings are fine).
3. Three company pages, each on Overview, Results and Owners: one bank, one with several cards, one with a price chart
   (after T9's `market-data`) or say none has one yet.
4. `/calendar`, `/results`, and the held-card review queue.
Save them as PNG in `docs/audit/screens-2026-10-20/` named `<nn>-<page>-<width>.png` (keep each under ~1.5 MB; a JPEG at
quality 80 is fine for long pages), plus `index.md` with one line per shot: the URL and anything that looks wrong
against the data (a figure, an empty panel, a cut label).
Files you may change: `docs/audit/screens-2026-10-20/`. Report: here, with the count and the worst three problems seen.

## T7 · P1 · laptop · OPEN — confirm the re-check fixes on the same filings

After pulling the commit that follows `bdd7f99`, process again (`process --news-ids`, FREE_ONLY):
Hind Copper `1a84a2bd-b7a2-440a-90b6-528b621ce310`, Dabur `nse-106729432`, CSB Bank `33717cd4-0f00-47c3-9a26-9c79acb7b4d4`,
Ceigall `nse-106801864`, Ramco `nse-106731799`. Check: Hind Copper published (unless a quote-contract hold remains:
report its reason), ladder AA+ -> AAA, 1 notch up, no order block; Dabur's import alert and warning letter both
marked, the warning letter as the current step; CSB has no stale "Management said"; Ceigall "Term · 5 years"; Ramco
has no P/E line. And `/company/519552?tab=results` at 390 px: the quarter labels whole.
Files you may change: none. Report: here.

## T8 · P2 · laptop · OPEN — check the new promoter-pledge memory against filings (module 42)

After the go-live load (T4), run `python -m bse_intel pledge-sync --days 365` (one NSE request a month of feed; a minute
or two). Then for 6 companies - 2 with an invocation, 2 with "up ... in 90 days", 1 released in full, 1 whose total is
withheld for group figures - open the disclosure (`attachment` in `pledges.events`) and check: promoter, event, shares and
% of the company, lender, and the company total on `/company/<scrip>?tab=owners` against the latest disclosures. Report
any figure the rules read wrong with the row.
Files you may change: none. Report: here.

## T9 · P3 · laptop · OPEN — fill and check the company page price charts

The company page's price chart (`6368e37`) reads `chart/<scrip>.json`, which `market-data` writes for each company it
prices. Run `python -m bse_intel market-data` once against the local site when no audit round needs Yahoo, then on three
company pages (one with several cards) check: the last close and date against NSE's quote page, the 1Y move against the
1Y return in the header (both from the same closes; small differences from the session count are fine), each filing dot on
its trading day (after-hours or holiday filings on the next session), and a click on a dot opening that card.
Files you may change: none. Report: here.

## T10 · P3 · laptop · OPEN — check the DGTR trade-remedy links (module 8)

After the go-live load (T4) and outside an audit round, run `python -m bse_intel dgtr-sync --pages 3` (three list pages
per investigation type, ~135 cases; scanned notices are OCR'd, so 30-60 minutes; the site drops a connection now and then
and each request is retried). Report the JSON it prints. Then from R2 `meta/dgtr_cases.json` (local:
`data/wrangler`, or `python -c` over `sink.get_object`) take 10 cases with names and check against each initiation notice:
the applicant(s) and supporter(s) it gives, whether the listed company it was linked to is the one named (not a namesake or
a private-limited group company), and any listed applicant that was **not** linked (the master's spelling, a former name).
On two linked companies' pages (`/company/<scrip>`) check the "Trade remedies" panel: product, countries, the latest step
and its date against the case page.
Files you may change: none. Report: here.

## T2 · P1 · laptop · OPEN — measure the bank ratio scale before it is trusted (CLAUDE.md rule 0)

The pipeline now reads `PercentageOfGrossNpa`, `PercentageOfNpa` and `ReturnOnAssets` from the banking results XBRL
as fractions (CSB Bank Q3FY25 files 0.0158 for 1.58%) and keeps a value above 1 as already a percentage. That is
measured on one file only. Check 8 banks' latest NSE results XBRL (public sector and private, large and small, e.g.
SBIN, PSB, CSBBANK, HDFCBANK, IDFCFIRSTB, J&KBANK, KARURVYSYA, UCOBANK).
For each: the raw value and `unitRef` of the three tags in the file, the figures in the bank's own press release or
results PDF, and what `python -m bse_intel analyze-pdf` (or `xbrl.parse` on the downloaded file) gives as `gnpa_pct`,
`nnpa_pct`, `roa_pct`. Is RoA annualised in the file?
Files you may change: `docs/SOURCES.md` (a "measured 2026-10-2x: ..." line for these tags).
Report:

## T3 · P1 · laptop · OPEN — round 7 on the current code

Run round 7 as planned (`docs/audit/round-7.md`, 12:40 IST after Gemini's reset). Start it after pulling `ae73b45` or
later so it measures the code that will go live, and write the commit in the round's report. Do not restart a round
mid-way for a later pull. The cards now carry `scale`, `rating_change`, `case_stage`, `guidance_recall` and the results
table's `lines`: the reviewers judge the face as published, so the review prompt should mention the blocks and the
"For the decision" lines as part of the card (WRONG if their figures are wrong).
Files you may change: `docs/audit/round-7*`, `pipeline/scripts/audit_round7/`.
Report:

## T4 · P2 · laptop · OPEN — finish the go-live load (PLAN G6a)

Re-run `pwsh -File pipeline\scripts\golive_load.ps1` when the seed allows (steps 2 and 3 failed on the network at
17:23). Report how many universe companies now have `ownership`, `governance.quarters` and results quarters in memory,
and the file failures left. Keep NSE's pace: no parallel NSE-heavy runs beside an audit round.
Files you may change: `docs/PLAN.md` (G6a status line only).
Report:

## T5 · P2 · laptop · OPEN — diagnose three content faults from your web test (data first, no code)

From `docs/audit/web-redesign-test-2026-10-19.md`, content items 1-3. For each, find from the local database and the
stored raw replies where the wrong value came from, following docs/DATA_QUALITY.md:
1. Heritage Foods Q4FY26 scorecard "PAT +16.7% YoY" against a fall from ₹38.17 Cr to ₹23.94 Cr: which year-ago PAT did
   `results_snapshot` use (period, value, source news id)? Restatement, a mixed basis (standalone vs consolidated), or a
   wrong period?
2. Heritage's two Q2FY27 results cards: which two filings, why D20 (one card per results quarter) did not merge them,
   and whose figures are right.
3. Guidance left OPEN after the results that settle it, and the same metric three times with different targets: two
   examples each with the guidance ids, the filings that should have settled them and what pass 2 returned in
   `promise_updates`.
Files you may change: none; write the findings in `docs/audit/content-faults-2026-10-20.md`. The cloud fixes the
classes in code from your findings, so say for each what the rule should be.
Report:

## T6 · cloud · DONE — content faults the cloud fixes in code now

From the same report, items 3 (part), 4 and the calendar:
- an agency's or analyst's expectation stored as the company's guidance ("Ind-Ra expects ...");
- a deadline written as a range ("FY26-FY27") read as its first year, so it shows overdue too early;
- group entities that are a lawsuit's other parties or a plant, not group companies;
- one event in Coming up three times (Rights Open, Milestone, Other on one date).
Files the cloud is changing: `pipeline/src/bse_intel/dossier.py` (guidance and identity merge), `periods.py`
(`due_date`), `pipeline.py` (catalysts), `web/`. **Laptop: do not edit these functions until this task is DONE.**
Report: done in the commit after `eb8691a` (tests `pipeline/tests/test_content_faults.py`, `web/test/cardText.test.ts`).
- Third-party views: `dossier.third_party_view` keeps "Ind-Ra / CRISIL / analysts expect ..." out of guidance when it is
  stored, and out of the overdue list and "Management said" for memory already stored. Pass-2 prompt says so too.
- Ranges: `periods.due_date` takes a range's later end ("FY26-FY27" -> 2027-03-31); "FY2026-27" stays one year. The
  overdue list re-reads each deadline from its words, so stored memory is right without a rebuild.
- Entities: kept only with a group, plant or brand type (`dossier.group_entity`; an acquisition target counts); the
  company page applies the same rule to memory already stored. Prompt: not a case's other parties, customers, lenders,
  regulators or ministries.
- Calendar: `/api/calendar` and the company page's Coming up drop a generic "Other"/"Milestone" beside a named event of
  the same company and day, and repeats of one event (`shared/events.ts`).
- Not changed: guidance left OPEN after the results that settle it and repeated targets (T5 first: data, then the rule).

---

## Proposed by the laptop

(none yet)
