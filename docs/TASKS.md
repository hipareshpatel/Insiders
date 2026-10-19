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

## T7 · P1 · laptop · OPEN — confirm the re-check fixes on the same filings

After pulling the commit that follows `bdd7f99`, process again (`process --news-ids`, FREE_ONLY):
Hind Copper `1a84a2bd-b7a2-440a-90b6-528b621ce310`, Dabur `nse-106729432`, CSB Bank `33717cd4-0f00-47c3-9a26-9c79acb7b4d4`,
Ceigall `nse-106801864`, Ramco `nse-106731799`. Check: Hind Copper published (unless a quote-contract hold remains:
report its reason), ladder AA+ -> AAA, 1 notch up, no order block; Dabur's import alert and warning letter both
marked, the warning letter as the current step; CSB has no stale "Management said"; Ceigall "Term · 5 years"; Ramco
has no P/E line. And `/company/519552?tab=results` at 390 px: the quarter labels whole.
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
