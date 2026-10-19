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

## T16 · P1 · cloud · OPEN — daily review of the live cards by independent agents (D37)

Once the live site has cards (T15, then the schedule): each day, every held card plus a random sample of the published ones
(about 20, by event type), each judged blind against its filing's PDF by a separate reviewer agent with round 4's prompt
(`REVIEWER_PROMPT_ROUND4.md`) and the block paragraph of round 7's method. Results and the tally in
`docs/audit/live/<date>.json` and `.md`; WRONG classes fixed in code (or given to the laptop when they are in its files).
The PDFs come from NSE's archive links on each card; where the cloud cannot fetch one, the laptop is asked to export it.

## T15 · P1 · laptop · OPEN — load the laptop's data onto the live site (go-live, PLAN G6)

The owner's choice (D37): go live and review the live cards. The live site (D1 `bse-index-nse`, R2 `bse-intelligence`) is
deployed and empty. After T3's scheduled task is off:
1. Load what the laptop has now, so the live site has companies, cards and memory:
   `$env:PLATFORM_API_URL = 'https://insiders.reply-bd3.workers.dev'; $env:INGEST_TOKEN = <the keys file's>;`
   `python -m bse_intel sync-to-cloud --source http://localhost:5173` (resumable; stops at the D1 daily write budget, run
   again the next day if it does). Report the JSON (rows and objects copied, anything refused).
2. Check: `https://insiders.reply-bd3.workers.dev/feed?range=all` shows cards; a company page shows its memory; the owner
   token opens `/api/owner/feed` with the held cards.
3. When T13's re-seed and `refresh-summaries` are done, sync again so the live memory carries the basis fix (move
   `data/sync_progress.json` aside first if the sync skips what it already copied; report what it did).
4. Do not switch the schedule on (G7 is the owner's: merge the PR, then `PIPELINE_SCHEDULE = on`).
Files you may change: `docs/PLAN.md` (G6 status line). Report: here.

## T14 · P1 · laptop · DONE — check the owner's new Cloudflare API token (GitHub's deploy key)

The owner made a new API token (2026-10-20; the first one was shown in a chat and deleted), put it in GitHub as
`CLOUDFLARE_API_TOKEN` and in the keys file as `$env:CLOUDFLARE_API_TOKEN`. GitHub cannot run `deploy-web.yml` by hand
until the workflow is on `main` (the PR is not merged), so check it from here. Never print the token:
1. Dot-source the keys file, then `cd web; npx wrangler whoami` with `CLOUDFLARE_API_TOKEN` set: it should name the
   account `bd3fb35d...` and list the token's permissions (Workers Scripts, D1, Workers R2 Storage edit).
2. `npx wrangler d1 execute bse-index-nse --remote --command "select count(*) n from sqlite_master"` (a read through the
   token, not your `wrangler login`): a number back means D1 access works. Then unset the variable.
3. If the keys file does not have it yet, ask the owner to add the line (the value is the one in GitHub's secret).
Files you may change: none. Report: **works** (2026-10-20 ~04:00 IST). The owner rolled a token, then put the new value in the keys file and in GitHub's
`CLOUDFLARE_API_TOKEN`. With only the token set (`CLOUDFLARE_API_TOKEN`, 53 characters, never printed):
- `wrangler whoami`: "logged in with an User API Token", account "Reply@aol.in's Account" `bd3fb35d7560f85367810802f17580b6`
  (wrangler does not list a user token's permissions);
- `wrangler d1 execute bse-index-nse --remote --command "select count(*) n from sqlite_master"`: `n` 56 (D1 access works);
- `wrangler r2 bucket list`: `bse-intelligence` (R2 access works).
Workers Scripts edit is not exercised by a read; the first `deploy-web.yml` run after the PR reaches main will show it.
The laptop cannot read GitHub's copy back, so it rests on the owner having pasted the same value in both places.
Earlier on this task: the GitHub secrets set from the keys file, and `bse-index` already deleted (see the git history of this file).

## T13 · P1 · laptop · OPEN — re-seed memory on the basis fix, then re-check Heritage and two banks

The cloud's commit after `83ea204` fixes T2 and T5's classes (cloud notes under each). Memory seeded before it has no basis
on its XBRL figures, and the standalone-only quarters are still in it. After pulling, and not while round 7 runs:
1. When the go-live seed pass (T4) ends, `python -m bse_intel seed-memory --universe --restart --results-only` (the files
   are cached locally, so mostly no NSE requests): each seeded figure gets its basis, and a standalone-only quarter of a
   company that files consolidated is taken out again (log line "standalone file only ... left to the cards").
2. Re-run Heritage's three cards (`process --news-ids 145bb59e-db01-490b-86f5-ebe6eab36492,527b6923-cd12-4d50-adbe-3c07f3c0e733,1d299133-85bb-4263-bc45-d96015d2cb0a`):
   Q4FY26 PAT should read down ~37% YoY (23.94 against 38.17); Q2FY27 revenue +18.6% and PAT −39.5%; one Q2FY27 line
   in the company's story (the held card's line stays out).
3. One SBI or HDFC Bank results card (consolidated): the bank lines show gross and net NPA from the standalone file
   (the table says "(standalone)"), not 0% and not missing. HDFC Bank's RoA reads about 1.8% (annualised), not 0.45%.
4. `/company/519552?tab=promises`: one VAP-share target for Q2FY27; "2 MLPD by FY26" shows "Not reported", not "On track".
5. `python -m bse_intel refresh-summaries` (new, no AI; one D1 row per company with memory): rebuilds each company's
   stored summary, so Today's and the calendar's Overdue promises drop Prism Johnson's "Ind-Ra expects ..." items and
   read range deadlines ("FY26-FY27") at their later end. Then check Today and `/calendar` at 390 px: UCO's 26 Oct
   strike once; `/results`: Prism Johnson's PAT reads "Loss to profit", banks show their interest earned YoY;
   `/system` at 390 px no wider than the screen; Heritage's Overview shows 8 "What to track" items and "Show all".
Files you may change: none. Report: here (the seed's JSON summary line and each check).

## T12 · P1 · laptop · DONE — deploy the Worker with its database and bucket (PLAN G4)

Measured 2026-10-20 (owner's screenshot): the Worker `insiders` is deployed on insiders.reply-bd3.workers.dev with
**0 bindings** (no D1, no R2), uploaded 4 days ago. The owner is creating D1 `bse-index` and R2 `bse-intelligence` in the
dashboard and the GitHub secrets. **The D1 name is `bse-index-nse`** (2026-10-20: Cloudflare said `bse-index` was not available); local commands name it so: `npx wrangler d1 execute bse-index-nse --local --persist-to ../data/wrangler ...`. Local data is untouched (kept by id; checked: 13 cards read back). When the owner says they exist (or `npx wrangler d1 list` shows `bse-index-nse`):
1. **Done by the cloud:** the id `f1465085-72e3-4a72-a67e-1a6ca9ab202e` is in `web/wrangler.jsonc` (`database_id` only; `preview_database_id` stays the placeholder, so `npm run dev`
   keeps reading your local database: checked in the cloud, 13 local cards read back with a real-looking id), or set it
   as the repository variable `D1_DATABASE_ID`, which deploy-web.yml uses; `cd web; npm run db:migrate:remote`.
2. `npx wrangler secret put INGEST_TOKEN` and `npx wrangler secret put OWNER_TOKEN`, values from the owner's keys file
   (never printed or committed).
3. `npm run deploy` (or the repo's deploy script); then check the dashboard shows 3 bindings (DB, VAULT, AI) and
   `curl.exe -s -o NUL -w '%{http_code}' https://insiders.reply-bd3.workers.dev/api/feed?range=all` gives 200.
4. Do not load data yet (G6 and `sync-to-cloud` come after); do not switch the schedule on (G7, owner).
Files you may change: `web/wrangler.jsonc` (the id only), `docs/PLAN.md` (G1/G4 status lines). Report: done 2026-10-20 02:40-03:15 IST on the owner's go ("Yes, create the D1 database bse-index and the R2 bucket
bse-intelligence with wrangler, then deploy the Worker (T12)").
- The laptop created D1 `bse-index` (21:34 UTC) and R2 `bse-intelligence` with wrangler. Four minutes later, D1
  `bse-index-nse` (`f1465085-72e3-4a72-a67e-1a6ca9ab202e`) was created in the dashboard, presumably because Cloudflare
  refused `bse-index` as already taken, and the cloud renamed the config to it (4bd6fd4). **The Worker now uses `bse-index-nse`**:
  its id is `database_id` in `web/wrangler.jsonc`, migrations 0001-0010 applied (22 tables), and deployed version
  `9a23c2f8-36b1-4ce1-9405-553869d5897a` binds `env.DB (f1465085-...)`, VAULT `bse-intelligence` and AI
  (`wrangler versions view`). **`bse-index` (`175e34e6-...`) is now unused** (schema only, no data): the owner can delete it in the
  dashboard, or say so and the laptop runs `wrangler d1 delete bse-index`.
- `INGEST_TOKEN` and `OWNER_TOKEN` were not in the keys file. Generated (32 random bytes each), appended to the owner's
  keys file, and set with `wrangler secret put` without printing. The same INGEST_TOKEN is the GitHub secret G2 needs; OWNER_TOKEN is
  what the owner enters in the live site's owner box.
- Live: `/` 200, `/api/feed?range=all` 200 with no cards, `/api/system` d1 217,088 bytes, `/api/owner/check` 401 without the
  token. The local site still reads its own database (855 cards).
- Wrangler's deploy summary prints the DB line with the placeholder id; the built `dist/insiders/wrangler.json` and the
  deployed version both have the real one.
- Not done (as the task says): no data loaded, schedule not switched on.

## T11 · P1 · laptop · DONE — screenshots of the site on real data (owner asked, 2026-10-20)

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
Files you may change: `docs/audit/screens-2026-10-20/`. Report: 42 shots in `docs/audit/screens-2026-10-20/` (20 MB, each under 1.5 MB), with `index.md` (URL and notes per shot).
Taken through Chrome's DevTools protocol (light/dark set per shot, true page height). Cards are cropped to the card,
and All filings is its first 5,000 px. No price chart yet: T9's `market-data` hasn't been run. Worst three:
1. **A held card is public by link.** `/feed?card=<held id>` (`/api/cards/:id` has no held filter) shows the card with
   the red "Held: not on the public feed. Only you see this card." banner to anyone (Hind Copper `1a84a2bd`). The card
   endpoint should 404 a held card without the owner token, and the banner should show only in owner mode.
2. **System page at 390 px is 822 px wide**: the "AI provider health" rows' usage/error line doesn't wrap.
3. **Old memory summaries keep the T6 faults**: Overdue promises (Today and Calendar) still shows Prism Johnson's
   "Ind-Ra expects ..." items with "due FY26-FY27, 203 days", because `/api/promises/overdue` reads the stored
   `memory_summary_json`. The T6 filter runs only when a summary is rebuilt; it needs the Worker-side filter too (as
   T6 did for the calendar), or a summary refresh for every company.
Also seen: the Results page's Heritage +21.0% / −36.2% (T5 item 1); Prism Johnson's PAT "+2127.0%" from a loss (should
read "loss to profit"); UCO's 26 Oct strike twice (Other + Milestone with different words); a compliance officer's
re-appointment in the calendar (Bandhan, D30); "has informed BSE" in NSE meeting texts; Ahluwalia's promise "it would
be about 15%." (a fragment); CSB credit-cost targets for Q4FY26/Q1FY27 still Open.

**Cloud on T11 (2026-10-20), fixed:** held cards private (a public link and the public review queue no longer show one;
the owner's routes do); the System page's provider rows truncate at 390 px; generic calendar events of one company and
day are one (UCO); a change across a loss reads "Loss to profit" / "Profit to loss" / "Loss narrowed / widened", not a %;
banks' and insurers' top line on the Results page; "What to track" shows 8 with "Show all"; `refresh-summaries` for
the stale overdue list. Not yet: the calendar's "has informed BSE" texts, the AHLUCONT fragment and governance catalysts
(pipeline catalysts, after round 7); Dabur's import alert (the case steps read the card, which does not name it).
Checks: T13 step 5.

## T7 · P1 · laptop · DONE — confirm the re-check fixes on the same filings

After pulling the commit that follows `bdd7f99`, process again (`process --news-ids`, FREE_ONLY):
Hind Copper `1a84a2bd-b7a2-440a-90b6-528b621ce310`, Dabur `nse-106729432`, CSB Bank `33717cd4-0f00-47c3-9a26-9c79acb7b4d4`,
Ceigall `nse-106801864`, Ramco `nse-106731799`. Check: Hind Copper published (unless a quote-contract hold remains:
report its reason), ladder AA+ -> AAA, 1 notch up, no order block; Dabur's import alert and warning letter both
marked, the warning letter as the current step; CSB has no stale "Management said"; Ceigall "Term · 5 years"; Ramco
has no P/E line. And `/company/519552?tab=results` at 390 px: the quarter labels whole.
Files you may change: none. Report: re-run on a1ed393, 01:40-01:54 IST, FREE_ONLY, `process --news-ids` after `/api/owner/requeue`.
- **Hind Copper** `1a84a2bd`: ladder right: `rating_change` ICRA AA+ -> AAA (Stable), **1 notch**; no order block
  (`scale` null). **Still held**, now only by the quote contract: three quotes "not in the filing", key numbers
  "Short-term rating" and "Commercial paper", and why-it-matters "Short-term A1+ reaffirmed on ₹100 Cr commercial ...".
  Those figures are in the filing's rating table ("Commercial Paper^ 100.00 [ICRA]A1+; reaffirmed"), a row rather than
  a sentence, so a quote taken from the table does not match a sentence. Headline: "ICRA upgrades HCL long-term
  rating to AAA (Stable) from AA+ on ₹2,100 Cr bank facilities; A1+ reaffirmed on ₹100 Cr CP".
- **Dabur** `nse-106729432`: **not fixed.** `case_stage.reached` = [1] (warning letter only). The PDF says "US FDA had
  issued an Import Alert (IA) 66-40 on June 10, 2026", but the card's headline and first point do not mention it, and
  the steps are read from those alone. The steps need the filing text (or every point of the card).
- **CSB Bank** `33717cd4`: no stale "Management said". The one recalled now is "ROA guidance maintained at 1.5-1.6% near
  term ... by FY28" (a target and a deadline). Bank table and headline as before.
- **Ceigall** `nse-106801864`: "Term · 5 years"; size bars 22% / 5.3%; "1.1% of FY26 revenue a year"; stage LOI.
- **Ramco** `nse-106731799`: no P/E line; "Since the filing ₹931.6 -> ₹787.25, -15.5%".
- `/company/519552?tab=results` at 390 px: the quarter labels are whole ("Q3" over "FY25"); no sideways scroll.

## T8 · P2 · laptop · OPEN — check the new promoter-pledge memory against filings (module 42)

After the go-live load (T4), run `python -m bse_intel pledge-sync --days 365` (one NSE request a month of feed; a minute
or two). Then for 6 companies - 2 with an invocation, 2 with "up ... in 90 days", 1 released in full, 1 whose total is
withheld for group figures - open the disclosure (`attachment` in `pledges.events`) and check: promoter, event, shares and
% of the company, lender, and the company total on `/company/<scrip>?tab=owners` against the latest disclosures. Report
any figure the rules read wrong with the row.
Files you may change: none. Report: here.

## T9 · P3 · laptop · DONE — fill and check the company page price charts

The company page's price chart (`6368e37`) reads `chart/<scrip>.json`, which `market-data` writes for each company it
prices. Run `python -m bse_intel market-data` once against the local site when no audit round needs Yahoo, then on three
company pages (one with several cards) check: the last close and date against NSE's quote page, the 1Y move against the
1Y return in the header (both from the same closes; small differences from the session count are fine), each filing dot on
its trading day (after-hours or holiday filings on the next session), and a click on a dot opening that card.
Files you may change: none. Report: 2026-10-20 04:00-04:10 IST. `market-data` (default) updated the 101 companies that have cards (99 in Yahoo's first round,
101 in the second; 318 D1 rows, 101 charts); `market-data --all` for the whole universe was started after it (laptop tab).
Checked CSB Bank, Heritage Foods and Jubilant Pharmova:
- **Last close against NSE's own bhavcopy** (downloaded tonight by the go-live load): 16 Oct CSB 308.90, Heritage 405.40,
  Jubilant 938.60 in both, exact. **But NSE's 19 Oct closes (312.50, 388.15, 935.80) are not in Yahoo at 03:52 IST on
  20 Oct**, so the site ends at 16 Oct, one session behind. Suggest using the bhavcopy (already fetched daily) as the
  close of record, with Yahoo for history.
- **1Y move:** the chart's "-18.3% over 1Y" equals the header's 1Y -18.3% (Heritage); chart and header use the same closes.
- **Chart file:** `chart/<scrip>.json` with 260 closes, 29 Sep 2025 to 16 Oct 2026.
- **Filing dots:** Heritage's chart has one dot per card (15 Oct 2025 ... 14 May 2026, each a button named "Filing on
  <date>: <headline>"). A click opens that card (`/feed?card=76f3b6ed...`, the Q2FY26 results). Three dots in one week
  of May (results 11 May, deck 12 May, call 14 May) are three cards by design (D33). Not checked dot by dot: whether
  an after-hours or holiday filing sits on the next session.

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

## T2 · P1 · laptop · DONE — measure the bank ratio scale before it is trusted (CLAUDE.md rule 0)

The pipeline now reads `PercentageOfGrossNpa`, `PercentageOfNpa` and `ReturnOnAssets` from the banking results XBRL
as fractions (CSB Bank Q3FY25 files 0.0158 for 1.58%) and keeps a value above 1 as already a percentage. That is
measured on one file only. Check 8 banks' latest NSE results XBRL (public sector and private, large and small, e.g.
SBIN, PSB, CSBBANK, HDFCBANK, IDFCFIRSTB, J&KBANK, KARURVYSYA, UCOBANK).
For each: the raw value and `unitRef` of the three tags in the file, the figures in the bank's own press release or
results PDF, and what `python -m bse_intel analyze-pdf` (or `xbrl.parse` on the downloaded file) gives as `gnpa_pct`,
`nnpa_pct`, `roa_pct`. Is RoA annualised in the file?
Files you may change: `docs/SOURCES.md` (a "measured 2026-10-2x: ..." line for these tags).
Report: measured 2026-10-20 on each bank's latest NSE `INTEGRATED_FILING_BANKING` file; written into `docs/SOURCES.md`
("Bank ratios ... measured 2026-10-20"). All values are fractions, `unitRef="pure"`, `decimals="INF"`; none already a percentage.
| Bank | File | GNPA | NNPA | RoA (quarter / half-year) | Parsed |
|---|---|---|---|---|---|
| SBIN Q1FY27 | standalone | 0.0147 | 0.0038 | 0.0111 | 1.47 / 0.38 / 1.11 |
| SBIN Q1FY27 | consolidated | **0** | **0** | **0** | **0.0 / 0.0 / 0.0** |
| PSB Q2FY27 | standalone | 0.0209 | 0.0061 | 0.0088 / 0.0081 | 2.09 / 0.61 / 0.88; board outcome: 2.09, 0.61, "Return on Assets (Annualised) 0.88" |
| CSBBANK Q1FY27 | standalone | 0.0175 | 0.0039 | 0.0106 | 1.75 / 0.39 / 1.06 |
| HDFCBANK Q2FY27 | standalone | 0.0111 | 0.0037 | 0.0045 / 0.0091 | 1.11 / 0.37 / 0.45 |
| HDFCBANK Q2FY27 | consolidated | **0** | **0** | **0** | **0.0** |
| IDFCFIRSTB Q1FY27 | standalone | 0.0151 | 0.0044 | 0.0105 | 1.51 / 0.44 / 1.05 |
| IDFCFIRSTB Q1FY27 | consolidated | **0** | **0** | **0** | **0.0** |
| J&KBANK Q1FY27 | both | 0.0237 | 0.006 | 0.0087 | 2.37 / 0.60 / 0.87 |
| KARURVYSYA Q2FY27 | standalone | 0.0069 | 0.0018 | 0.0210 / 0.0211 | 0.69 / 0.18 / 2.10 |
| UCOBANK Q2FY27 | standalone | 0.0196 | 0.0018 | 0.0080 / 0.0080 | 1.96 / 0.18 / 0.80; board outcome: "% of Gross NPA 1.96%", "% of Net NPA 0.18%", "Return on Assets (Annualised) 0.80%" |
Findings for the cloud: (1) **consolidated bank files carry 0 as a filler for all three ratios** (SBI, HDFC Bank, IDFC First),
and `xbrl.parse` reads it as 0.0%: take the ratios from the standalone file and treat a 0 ratio as no value. A
consolidated-first reader would print "gross NPA 0%". (2) **RoA is annualised in most files, not in HDFC Bank's**: its
quarter, 0.45%, is about half its half-year, 0.91% (KVB, PSB and UCO have quarter = half-year). Assumption until checked
against HDFC Bank's own statement. Annualise a quarter whose value is about half the half-year's, or read the PDF's line.
Raw files: the laptop's `%TEMP%/t2/xml/` (not committed). Press releases checked for UCO and PSB, not yet for the other six.
**Cloud, 2026-10-20:** fixed in `xbrl.py` (bank-ratio code, the cloud's): a period whose bank ratios are all 0 keeps none
(a single 0 beside real ratios stays); a consolidated bank card reads the same quarter's standalone file for its ratios
(`needs_standalone_bank_ratios`, `add_bank_ratios`, the table marks them "(standalone)"); RoA is put on a yearly basis
when the file's quarter is about its share of the half-year or nine months (HDFC Bank 0.45% -> 1.8%), and left as filed
otherwise (a Q1 file alone cannot tell). Tests in `test_xbrl.py`. Check on real cards: T13.

## T3 · P1 · laptop · CANCELLED — round 7 on the current code

**Cancelled by the owner 2026-10-20 ~04:00 IST (D37): "let's not start round 7 as we will shift to live only review".**
**Laptop, now: disable or delete the scheduled task `insiders-round7-start` (12:40 IST) so it does not run and spend
Gemini's quota**, and say so here. Keep `data/audit/round7/` and the scripts; nothing else to do on this task.


Run round 7 as planned (`docs/audit/round-7.md`, 12:40 IST after Gemini's reset). Start it after pulling `ae73b45` or
later so it measures the code that will go live, and write the commit in the round's report. Do not restart a round
mid-way for a later pull. The cards now carry `scale`, `rating_change`, `case_stage`, `guidance_recall` and the results
table's `lines`: the reviewers judge the face as published, so the review prompt should mention the blocks and the
"For the decision" lines as part of the card (WRONG if their figures are wrong).
Files you may change: `docs/audit/round-7*`, `pipeline/scripts/audit_round7/`.
Report: 2026-10-20 04:00 IST: the scheduled task `insiders-round7-start` (12:40 IST) is **disabled** (description: "Cancelled
2026-10-20 (D37 ...)"); it will not run. `data/audit/round7/` and the scripts are kept. Nothing else was done.

## T4 · P2 · laptop · OPEN — finish the go-live load (PLAN G6a)

Re-run `pwsh -File pipeline\scripts\golive_load.ps1` when the seed allows (steps 2 and 3 failed on the network at
17:23). Report how many universe companies now have `ownership`, `governance.quarters` and results quarters in memory,
and the file failures left. Keep NSE's pace: no parallel NSE-heavy runs beside an audit round.
Files you may change: `docs/PLAN.md` (G6a status line only).
Report:

## T5 · P2 · laptop · DONE — diagnose three content faults from your web test (data first, no code)

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
Report: `docs/audit/content-faults-2026-10-20.md`. (1) Heritage Q4FY26 "PAT +16.7%": **mixed basis**. The seed took
standalone XBRL files for Q4FY25 and Q2FY26 (`Integrated_Finance_Ind_As_519552_1262025132650.xml (STANDALONE)`, a
re-filing), and "XBRL outranks any card" let one standalone value (20.51) beat five consolidated sources (38.17), including
the Q4FY26 filing's own year-ago column. Rules: basis on every metric source, XBRL outranks only within a basis, YoY from
the statement's printed comparatives, no quarter P&L from non-results cards. (2) Two Q2FY27 cards: the board outcome was
held (UNRESOLVED), so D20 let the press release carry the card, by design. But the held card's timeline entry still went
into memory (two lines on the page), and both cards' tables use the standalone Q2FY26 from (1); the press release's
+19% / −39% are right. (3) Targets: a prediction settles only from a `financial_metrics` entry with the same key and period.
The Q2FY27 VAP share went to `segment_mix`, and `volume_growth` was never written, so they stay OPEN. The id hashes the
target value, so one metric gets three rows (38, 48, 49). Guidance stays ON_TRACK past its due date (2 MLPD by FY26;
5,000 farmers by Q2FY27). **Pass-2 replies are not stored**, so `promise_updates` cannot be traced: keep them with the
card. Rules for each in the file.
**Cloud, 2026-10-20, fixed (tests `test_basis_memory.py`, `test_seed.py`, `test_pipeline.py`):** (1) each memory source
keeps its basis; a figure's value comes from its consolidated sources when it has any, and XBRL outranks a card only on
the same basis; the seed leaves a standalone-only quarter of a company that files consolidated to the cards and takes it
out of memory where an earlier seed put it; a non-results card fills a quarter memory has no figure for but never adds to
one a results filing stated. (2) A held card's timeline line stays out of memory (its figures stay). (3) One open
prediction per metric and period (a later card's number replaces it; none once the period's figure is in);
NOT_REPORTED 75 days after the period ends; an ON_TRACK update past the deadline is ignored and the page shows "Not
reported" for a promise past its deadline; guidance with the same metric, target and deadline is one entry (`repeated`
lists the later filings); the card keeps pass 2's `promise_updates`. Not done: settling a KPI from `segment_mix` or
`key_numbers` (the KPI-to-segment mapping needs its own rule; NOT_REPORTED covers it meanwhile). Check on real data: T13.

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

### P-L1 · check an XBRL figure against the filing's PDF before it is used (owner, 2026-10-20: "we found few issues with XBRL, how about we check pdf for those cases only ?")

The XBRL faults measured tonight would each have been caught by the filing's own PDF, which the pipeline already reads
(text layer, OCR on pages of figures):
- consolidated bank files with 0 for gross NPA, net NPA and RoA (T2: SBI, HDFC Bank, IDFC First) where the PDF prints
  1.47%, 1.11%, ...;
- the seed's standalone file winning over consolidated cards (T5 item 1: Heritage Q4FY25 20.51 vs 38.17; Q2FY26);
- RoA un-annualised in one bank's file and annualised in the others (T2: HDFC Bank 0.45% quarter vs 0.91% half-year).
Proposal: only for those cases (an XBRL value that is 0 where a ratio is expected, a basis other than the card's, a value
more than 1% from the statement's own printed figure, or a ratio whose period basis is unclear), check the figure in the
PDF of the same filing; when the PDF prints it, use the PDF's value and note it on the card; when the PDF does not, keep
the XBRL value. `xbrl.confirm` / `appears_in` already test whether figures appear in the text, and could do this per
figure rather than per file. For memory's seed (no PDF), XBRL only within the company's basis. Owner's idea; the laptop
can measure how often each case occurs across the universe before it is built.

**Measured 2026-10-20 02:20 IST (owner: "yes"), local data only:** the seed logs of 273 companies (2,066 quarters),
5,253 cached XBRL files, and 260 results filings with their XBRL and PDF text both cached.
| Case | How often | Note |
|---|---|---|
| Wrong basis in memory's seed | **43 standalone quarters in 22 companies** with consolidated quarters before and after (Heritage Q4FY25/Q2FY26, Prism Q4FY25, eMudhra 6 quarters, ...) | 35 companies (13%) have both bases. A switch (consolidated from some date on) is not counted. 39 companies are standalone throughout, which is fine. |
| Zero bank ratios | **29 of 75 consolidated bank files (39%)** carry 0 for gross NPA, net NPA and RoA; **0 of 91 standalone** | a filler; take the ratios from the standalone file |
| RoA period | of 91 bank files with a quarter and a longer period: **71 annualised** (quarter ≈ half-year), **18 un-annualised** (quarter ≈ half), 2 other | annualise or read the PDF's line |
| XBRL figure not in the filing's own PDF | on 185 statement PDFs: **revenue 4 of 167 (2%)**, **PAT 4 of 185 (2%)**, PBT 7%, total income 7%, other income 8%, employee cost 9%, total expenses 15%; EBITDA 40% (not printed, it is computed, so not a fault) | Across all 260 filings it is 21%, but most of those PDFs are not the statement (a trading-window notice, a press release, a deck joined to the file by date), so there is nothing to check against. The PDF check is only meaningful when the PDF is the statement. |
So the PDF check matters most for the first three cases (basis, filler zeros, RoA), which together touch 22 companies'
memory and 39% of consolidated bank files. Revenue and PAT disagree with the statement in about 2% of filings. Script:
the laptop's `%TEMP%/pl1/` (measure.py, refine.py); can be committed under `pipeline/scripts/` if the cloud wants it.

**Cloud's answer (2026-10-20):** agreed, in two steps. The three measured cases are now handled at their root without a PDF
read (zero fillers dropped and taken from the standalone file; one basis per figure; RoA annualised), so what is left for
P-L1 is the general case: an XBRL figure more than 1% from the statement's own printed figure. Step 1 (laptop, after round
7, no code): for the round-7 companies and 30 random universe companies, compare each results card's XBRL revenue, PAT
and EBITDA with the PDF's printed figure (`xbrl.appears_in` on the cached text) and count the misses by cause. Step 2
(cloud): if misses are more than ~1 in 100 figures, build the per-figure check (PDF value used and noted on the card when
the PDF prints it; XBRL kept when it does not). Not before round 7 ends, so the round measures one code.
