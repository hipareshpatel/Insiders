# To-do list: improvements waiting to be built together

The owner asked on 25 Oct 2026 to collect the improvements here and build them all together, to save time and
tokens. How it works:

- Each idea is added here as it comes up, with what it fixes, in simple English.
- The owner marks each one **Yes**, **No** or **Later**.
- When the owner says "build", every **Yes** item is built in one go: one set of changes, one test run, one PR.
- Once built, an item moves to `docs/TRACKER.md` (with its F number) and leaves this list.
- Exception: a fix for something live that is being lost or published wrong is built at once, and noted here.

This list holds only the first-principles review's items (`docs/FROM_ZERO.md`). The older lists stay where they are:
`docs/PLAN.md` "Pending work" and `docs/TASKS.md`.

## Step 1: what we collect

| # | Improvement | What it fixes | Owner | State |
|---|---|---|---|---|
| 1 | One 120 MB size limit for every filing | Big results PDFs (NHPC FY26) were skipped at 30 MB and failed | Yes | Built, PR #108 (not merged) |
| 2 | When a file is still too large, say "file too large (X MB)" and do not retry it | Today it says "no readable text" and downloads the file 3 times for nothing | Yes | Built (F131), PR #108 |
| 3 | R1: a figure shown as a fact (results table, key numbers, "from memory" figures) comes only from an exchange figure file or a statement page we can point to. What management said (guidance, orders, capex, call remarks) stays in memory as "said on <date> in <document>", never as a checked figure | Old mistakes in our memory repeat on every later card (CIE India, HCL Tech) | Yes | Build order 2nd, after 10 |
| 10 | Tag every memory item with: who produced it (exchange figure file / our AI / our own calculation), the kind of document (results statement, call, slides, press release), basis (company alone or group), period, unit as printed, page and quote, and whether it passed our checks. Items with no tag count as "our AI" | Today an item records only which filing and date it came from: an exchange figure and our AI's figure from the same filing look the same, so R1 cannot be applied | Yes | Build order 2nd (with 3), after 23. State: step 1 built (F144): every item is labelled when written; readers unchanged, no card change; step 2 built (F150): `label-memory` labels old memory, dry run first (Maintenance > label-memory), not run yet; steps 3-5 not built |
| 4 | R2: keep the text and figure files of every filing for 6 months (not 8 days), then delete | We cannot re-check old cards; the repeat-filing check misses repeats once the text is gone | Yes, 6 months with auto-delete (owner, 25 Oct) | Built (F147) |
| 5 | R3: read the `decimals` the XBRL file states (checked live 25 Oct: values are always in rupees; `decimals="-7"` means printed in crore, `-5` in lakh) and use it to match figures at the company's printed precision | We ignore it today. It does **not** catch a file the company itself filed at the wrong scale (Jubilant, F54): our check against the PDF still does that | Yes | Moved to step 2: its only use is matching EBITDA and table figures at the printed precision (items 11, 13); built alone it would do nothing |
| 6 | List the failed filings by reason (70 on 25 Oct) | We do not know how many filings we lose, or why | Yes | Built: `failed-report` (F131); run it from GitHub once PR #108 is merged |
| 7 | Check one busy day's NSE list against a second count | We have never checked that NSE gives us every filing | Yes | **Done, no gap found**: measured 25 Oct for 23 Oct 2026 (601 filings in the one-call list): 120 companies asked one by one (60 in the list, 60 not) gave 113 filings, all 113 in the list. Not yet tried on a peak results day (1,000+ filings); repeat then |
| 8 | Look at why each run takes ~41 minutes | The "every 15 minutes" schedule really runs every ~42 minutes, so cards come late | Later | Owner: when we reach the AI step (most of a run's time is AI calls) |
| 9 | Cover companies listed only on NSE | Thought to be set aside | Yes | **No work needed**: measured 23 Oct (company-list job log): 2,613 NSE listings, all 2,613 matched, `nse_only` 0; the company master adds NSE listings itself. A company listed after the morning sync is matched the next weekday |


### What the failed-filings report found (run 25 Oct 2026 after batch 1: 71 failed since 19 Apr)

| Reason | Filings | What it really is |
|---|---|---|
| The file could not be opened ("Failed to open stream") | 18 | Checked 2 of them: both are **ZIP files**, not PDFs. PGEL's is an **auditor's resignation** (a PDF and an XML inside the ZIP), so real news was lost; BETA's is call audio |
| "No attachment" | 17 | Checked 2: ARIS's is an 85 MB PDF (the old 30 MB limit; now read). CGCL's 0.75 MB PDF downloads fine today, so it was probably not there yet when we tried: three quick tries and it was given up |
| AI providers busy or out of daily quota | 28 | AI step (item 8) |
| Our own code crashed | 4 | KeyError 'as_of' (PNC Infra, 2 calls), a missing number in a results calculation (MODIS, 24 Oct), a division giving infinity (L&T Finance) |
| Empty file | 3 | Not looked at yet |
| Too large | 1 | NHPC (batch 1 fixed it) |

| # | Improvement | What it fixes | Owner | State |
|---|---|---|---|---|
| 22 | A per-company metrics table, worked out by code from the exchange files for every quarter (growth YoY and QoQ, margins, cost shares, last-four-quarters totals, EPS; balance-sheet ratios at each half-year; bank metrics for lenders), one table per basis. The AI never types a past number: it names the cell (metric, period, basis) and code writes the value | Wrong past numbers on cards (CIE India, HCL Tech) | Yes (owner, 25 Oct) | Build order 3rd. **Table built 25 Oct (F141, `metrics.py`, `metrics --scrip X`); not yet used on cards or the site, awaiting owner review.** screener.in may be used as a reference for which metrics investors expect and as a hand spot-check of our numbers in testing; never as a data source on a card (item 3), and not scraped |
| 23 | Use SEBI's official XBRL taxonomy (from NSE's XBRL page; common to NSE and BSE) for every results format: map our lines to the official elements and labels, check every file against the official sums (income − expenses = profit before exceptional items, and so on), and keep the version each file names | Hand-made tag lists; a file tagged wrongly passes unless it trips a guess; the associates' share can leak into EBITDA (item 12) | Yes (owner, 25 Oct: "big yes") | Build order 1st. One-time job per format, then a check per new version. Built (F140), hold version: lines in a failing sum are left off; no PDF fallback (1 real failure in 166 files) |
| 18 | Open ZIP attachments and read the PDF inside (and its XML); an audio ZIP is set aside as "audio, no text" | 18 filings lost, including an auditor's resignation | Yes (25 Oct) | Built (F132) |
| 19 | A filing whose PDF is not there yet waits and is tried again over the next day, instead of three tries in about two hours | Filings given up while NSE was still uploading the file | Yes (25 Oct) | Built (F132): waits 24 h. Checked 3 of the 17: ARIS too large (batch 1), CGCL there now, XTRANET's file still 0 bytes on NSE two days on (an empty upload; it now fails once with that reason). How fast NSE adds files was not measurable from the failed list |
| 20 | Fix the 4 code crashes, each with a test | 4 filings with no card, from our own bugs | Yes (25 Oct) | Built (F133); a crash now records the line it came from |

### Step 1 checks (owner's answers a-h, 25 Oct 2026)

| | Check | Result |
|---|---|---|
| a | The 25 requeued filings get cards | Requeued 25 Oct 10:44 UTC; checked at 10 PM IST (scheduled) |
| b | NSE's daily list on a busy results day | Scheduled for 26 Oct, 10 PM IST |
| c | The 3 "empty file" failures | Measured 25 Oct: Apollo Hospitals' and Hindustan Zinc's PDFs are **cut short on NSE itself** (3.47 of 12.45 MB, 0.33 of 4.40 MB; no end of file, NSE's own Content-Length matches the short file). Sun Pharma's is a ZIP of two scanned pages (now read, F132; OCR needed). Item 25 |
| d | A PDF NSE adds after the filing is listed | Confirmed in code: a filing first listed with no file never picks up a later one (`_attachment_changed` counts "no attachment" as no change) and its card is written from the title. Rare: on 23 Oct 2 of 601 rows had no file, both NSE's own questions to companies. Item 26 |
| e | How late the results figure file comes | Measured 25 Oct, 45 companies' Sep-2026 results: the figure file came a median **132 minutes** after the PDF, 75% within 225 min, 90% within 364 min, the latest 504 min; **16 of 45 (36%) after our 3-hour wait**, so those cards are first made from the PDF alone, and the results catch-up reads them again once the file lands (`event_catchup.results_catch_up`, 10 days) |
| f | Corrected (revised) results | Handled: NSE's list marks a revision and it replaces the original for the quarter and basis (`nse.py`), and the results catch-up re-reads a card whose file was revised within 10 days |
| g | 28 filings failed on AI capacity | Built (F134): they now wait up to about a day for the quota; the writer whose replies did not parse left the long route |
| h | Runs take ~41 minutes | By design: each run fills its 40-minute budget with older work; today's filings were done ~5 minutes in, but waited ~42 minutes for the next run. Built (F135): a quick 15-minute run for today; the memory sweeps hourly |
| - | Can GitHub's machines reach BSE? (owner's question) | Measured 25 Oct: a bare curl probe from GitHub (`probe-bse`) got 403 from BSE's data API; the ported adapter (Python requests, BSE's page headers) then got 200 on 16 of 16 calls from GitHub (`bse-results-test`, run 40189201441). BSE is reachable through the adapter; it stays a backup, not the online path |
| - | Do real figure files add up? (item 23) | Measured 25 Oct, 166 files of 60 random companies (both formats, all templates): 3,355 official sums checked, **one** real mismatch (Master Trust Dec 2024: a broker's expense lines outside the Ind AS sums) and 8 segment-asset totals. Wrongly tagged files are rare: the sums are a safety net, not a big source of fixes |

| # | Improvement | What it fixes | Owner | State |
|---|---|---|---|---|
| 25 | A PDF cut short on NSE (no end of file, no pages) is told apart: wait for NSE to replace it, then fail once with "file cut short on NSE (X of Y MB)" | Apollo Hospitals' amalgamation and Hindustan Zinc's presentation failed as "empty"; the reason was invisible | Yes (25 Oct) | Built (F136) |
| 26 | A filing listed with no file picks up the file when NSE adds it (and is read again if its card came from the title alone) | A card written from the title when the PDF came later | Yes (25 Oct) | Built (F136) |

Build order (owner, 25 Oct 2026): next batch = items 18, 19, 20 (small); then **23** official definitions, then **10 + 3** memory clean-up, then **22** metrics table. Earlier: **batch 1** = items 1, 2, 6, 7 (small, independent; 5 moved to step 2, 9 needed no work); **batch 2** = items 10 then 3 (they change how memory works, so they are built and measured on their own).

## Step 2: reading the file (to discuss)

| # | Improvement | What it fixes | Owner | State |
|---|---|---|---|---|
| 11 | EBITDA: when the company prints EBITDA (press release or slides), show theirs with its own label; when it does not, show ours marked "calculated by us". Our formula stays: profit before exceptional items and tax + interest + depreciation − other income (the owner's note of 25 Oct gives the same formula); none for banks and NBFCs | Cards set our EBITDA against a company's printed one with a different definition (Lumax, Bansal Wire, Solara and others) | Yes (owner, 25 Oct): label ours "Operating EBITDA (calculated)" and show what it leaves out (other income ₹X Cr) | Built behind `CARD_EBITDA_PROFIT_V2` (F151); release check pending |
| 12 | (Built: F137, PR #111) Group EBITDA leaves out the share of associates' and joint ventures' profit (owner's note, 25 Oct: Ind AS 28, they are not line-by-line). Subtract it only when the profit we start from includes it, which differs by file; check that per file, never assume | "Profit before vs after associates" was one of the results-table mistakes | Yes (owner, 25 Oct) | Step 2 |
| 13 | Official lines (revenue, profit, interest, tax): the PDF's figure is shown, read with care for the unit (lakh or crore) and the basis (standalone or consolidated); the figure file is the second witness, and a line the two disagree on is held, not published | 98.5% per figure is about 64% for a 30-figure table to be all right; the figure file is exact | Yes (owner, 25 Oct: PDF, hold on disagreement) | With item 23 |

Not taken: EBITDA from Yahoo (the owner's note mentions it). It is not an exchange file (item 3), and Yahoo's own
definition is not published.

## The card we are building towards

The owner's target card (25 Oct 2026): `docs/design/target-card-kajaria-q2fy27.md` (Kajaria Ceramics Q2FY27, every
line with its source: Statement, Computed, Filing, Memory). Items 3, 10, 11, 12 and 13 are the groundwork for it.
Fixes to the sample itself, found on review:

| # | Improvement | What it fixes | Owner | State |
|---|---|---|---|---|
| 14 | Show both EBITDA figures: the company's printed one leads (label "Filing"), ours beneath it (label "Computed"). Year-on-year only within one definition: theirs against their year-ago, ours against ours. When the company prints none, ours alone | The sample marks our EBITDA ₹286.61 Cr as "Statement" while the release prints its own (year-ago ₹212.90 Cr against our ₹213.45 Cr) | Yes (25 Oct) | Built behind `CARD_EBITDA_PROFIT_V2` (F151); release check pending |
| 15 | One profit line everywhere: the one the company headlines in its own release, with its label; with no release, profit attributable to shareholders (the line EPS is on) | Two profit figures on one card read as a mistake | Yes (25 Oct) | Built behind `CARD_EBITDA_PROFIT_V2` (F151); release check pending |
| 16 | A figure computed from memory (cost per MSM from deal history) only when every input is an exchange-file or quoted-filing item (item 10's tags) | Otherwise "Computed" hides an AI-read input | Yes (25 Oct) | With items 3 and 10 |
| 21 | Two parts on every card. Part 1 "From the filing (checked)": exchange-file figures, code calculations, quotes; every line checked, a failed line removed; graded right / WRONG against the 5% bar. Part 2 "Our reading (AI)": interpretation, past promises, what to watch; opinions allowed and graded reasonable / unreasonable on their own bar (10% proposed, owner to set); any number or fact in it must still be right and cite its source, a failed line is hidden, not the card | A wrong opinion and a wrong figure are different faults; readers still judge the whole card | Yes (25 Oct); part 2 bar 30% for now | Built behind CARD_TWO_PARTS (F152); release check pending |
| 17 | Measure what more lines cost: a card is WRONG if any one line is wrong, so ~25 lines need each line right about 99.8% of the time to keep cards at 95% | The richer the card, the harder the 95% bar | – | Measured 25 Oct (docs/audit/line-accuracy-2026-10-25.md): median 13 lines a card; 2.7% of lines wrong (2.0-3.6%); faults cluster, so cards are 21% WRONG not 31-40%; 95% at 13 lines needs 0.39% of lines wrong |

## Parked (owner, 25 Oct 2026: stopped, kept for later)

- F126d, the EBITDA check (removes our EBITDA where the company prints a different one), and its blind review of
  ~200 unseen tables (52 collected). Replaced in the plan by items 11, 14 and 23.
- The narrowed grounding (memory grounds only memory-type points; 1,018 of 5,226 cards, 19.5%) and its 150-figure
  blind review. Replaced in the plan by items 3 and 10.
- Both live on the branch `claude/gracious-goodall-jn9buu` (with `docs/ARCHITECTURE_AS_BUILT.md` and the 25 Oct trace
  files), not on `main`.

## Last item: the audit after all the improvements

| # | Improvement | What it fixes | Owner | State |
|---|---|---|---|---|
| 24 | **Audit pending.** Run the full audit once every item above is built: part 1 (checked) right / WRONG against the 5% bar; part 2 (AI reading) reasonable / unreasonable against **30%** for now. The owner will set the final part 2 bar from that audit's results | We do not yet know where the new card stands | 30% for now (owner, 25 Oct) | Audit pending, last |

## Other work the owner asked for (25 Oct 2026)

| # | Improvement | Owner | State |
|---|---|---|---|
| 27 | Port the reference repository's BSE client as an off-path adapter (TASKS T26) | Asked | Built (F138), PR #111. Its headless-browser fallback left out (CLAUDE.md). Measured: from GitHub the adapter got 200 on 16 of 16 calls (run 40189201441); an earlier bare curl probe got 403 |
| 28 | One timing line per filing (where its seconds went: download, XBRL, reading, OCR with its page count, pass 1, waiting to share a request, pass 2, memory writes) and the reason every deferral is logged | The first quick run (25 Oct, 11:30 UTC) took 11 min for 3 filings with two silent ~3-min gaps; a deferred filing left no reason in the log | Yes (owner, 25 Oct: "add the logging"; download-first only if the timings show downloads are slow) | Built (F139). Next: read a few quick runs' timing lines; first suspect the 60-s wait to share a request when only 2-3 filings are live |

## Item 13 measured (25 Oct 2026): what "hold a line the PDF does not print" would do

38 Sep-2026 results, 438 official lines from the figure files, PDF text layer only (no OCR), every miss classified by
an independent agent (`scratchpad` table summarised here):
- 308 lines (70%) the PDF prints exactly.
- 130 not found: 81 the PDF's statement page has no usable text (scans, garbled layers: OCR would read most; the
  pipeline OCRs figure pages, this measurement did not), 24 printed in a form our matcher misses ("1.253.52",
  "935,20", letters for digits), 10 a wrong PDF (a voting result), **15 real definition differences, 0 different
  figures for the same line**.
- The 15 real ones would put a wrong line on a card: "other expenses" tagged as the sum of several printed expense
  lines (Wipro ₹5,008 Cr where the statement's "Other expenses" is (174); Shree Cement, NELCO, NECC, OFSS, MHRIL), profit
  before tax before the associates' share where the statement prints it after (Bajaj Finance, ixigo), and tax given as
  one total where the statement prints current and deferred tax only (Oberoi Realty, Heritage, CCL, HFCL, GNA).
- So the rule as written would hold about 8 right lines for each wrong one. Next, before it is switched on: OCR for
  the figure pages (as the pipeline already does), a number normaliser for the matcher misses, and per line: "other
  expenses" shown only when the statement prints that figure, tax as current + deferred when that is what is printed,
  profit before tax as printed (`settle_pbt` already does this for the card's line).

### Item 13: final design (owner, 25 Oct 2026: OK)

| Lines | When the PDF and the figure file disagree |
|---|---|
| Tier 1: revenue, profit before tax as the statement prints it, profit, EPS | Hold that line |
| Tier 2: other expenses, tax, finance cost, materials and the rest | Leave that line out, or show the statement's own lines (e.g. current + deferred tax) |

Both stay off until the check reads figure pages as images (as the pipeline already does) and the number matcher reads
"1.253.52", "935,20" and letters in place of digits.

### BSE results XBRL through the adapter, tested (owner, 25 Oct 2026)

Run from the cloud session's machine and again from GitHub (run 40189201441, same result: 16 of 16 calls 200, 7 of 7 identical, Tata Motors has no NSE file to compare), 8 dual-listed companies, the adapter's own pace:
- 16 calls (8 results lists `Result_Arch_ng`, 8 figure files), **all 200**, no refusal, no dropped connection; lists
  99-142 KB (182-272 rows, 62-67 quarter files each), figure files 35-152 KB; four list calls took ~6 s at BSE's end,
  the rest under 0.5 s.
- Every file parsed with our reader (`xbrl.parse`), both formats: Ind AS (TCS, Infosys, Reliance, Wipro, HUL, Tata
  Motors) and banking (HDFC Bank, ICICI Bank).
- **7 of 7 comparable companies: revenue, total income, profit before tax, profit and EPS identical to NSE's file for
  the same quarter and basis** (Reliance, HUL and Tata Motors' latest is Jun 2026, the others Sep 2026). Tata Motors'
  NSE copy was not found under the symbol TATAMOTORS (likely renamed after its demerger), so it was not compared.
- So BSE's results files carry the same figures as NSE's: no new information for results; useful only as a backup
  source. 16 calls is not a load test: a full backfill (thousands of calls) is unmeasured.
| 29 | Quick run only: cut the wait to share a request from 60 s to 10 s (`PASS2_PACK_WAIT` in pipeline-today.yml; the main run keeps 60 s) | Measured 25 Oct, quick run 40191102782: 3 of 3 filings waited 60-66 s of their 97-185 s for others to share a request, with only 3 filings live. Cost: on a busy hour fewer filings share one request, so more AI requests | No (owner, 25 Oct: keep 60 s) | Not built |
| 30 | Time the steps still unmeasured (the checks after pass 2, building the card, sending it to the site) | Main run 40192588628: "other" (time outside every measured step) was 57-88 s on 8 filings, so a minute a filing is still unexplained. Logging only, no card change | Yes (owner, 25 Oct) | Built (F142) |
| 31 | Find why pass 2 took 13-18 minutes on some filings (retries, a slow provider or long waits for the rate limit) | Main run 40192588628: pass 2 983 s (LICI), 941 s (ROHLTD), 1,062 s (ZEEL), 772 s (NTPC); each ties up a worker. Diagnosis first, no change yet | Yes (owner, 25 Oct) | Diagnosed 25 Oct: spare models timing out one after another (120-300 s each), after packed Gemini was reserved for live filings; fixes are rows 33-35 |
| 32 | Skip OCR on a filing that is an exact repeat of one already read (same file), before reading its pages | Main run 40192588628: 3 filings OCR'd 7-15 pages (70-129 s each) and then were dropped as repeats (ITC nse-106633666, GOLDIAM nse-106643200 and nse-106643216). Only a same-file repeat can be caught before reading; a same-content repeat still needs the text | Yes (owner, 25 Oct) | Built (F143) |
| 33 | Log every AI model the gateway skips (and why) and every call that times out | Item 31 diagnosis (run 40192588628, 25 Oct): pass 2 took 13-18 min on 4 filings and the log cannot say why; the paid DeepSeek model got 0 calls in that run although the drain was on (40-56 calls in each of the 7 runs around it). Logging only | Yes (owner, 25 Oct) | Built (F145) |
| 34 | Shorter waits on spare models for one-filing card writing: 300 s -> 120 s (NVIDIA GLM 5.3, the Gemini spares on `pass2`); packed requests keep 300 s | Measured: NVIDIA models' circuits opened 4 times after 3 failures each; with timeouts of 120-300 s a filing that walks 4-6 spares takes 13-18 min. Cost: a slow but valid answer is dropped and the next model tried | Yes (owner, 25 Oct) | Built (F146) |
| 35 | A time cap per filing for card writing (e.g. 4 min across all models), then the filing waits for the next run (no attempt spent) | One filing held a worker for up to 18 min. Cost: more filings wait 15-40 min for the next run | Yes (owner, 25 Oct: "Yes increase it"): a cap above 4 min, 6 min chosen, a setting | Built (F149): 360 s, lifted for a filing after 3 cap deferrals; a cap hit never spends an attempt |
| 36 | Lists from the exchange's own files only: debt cut sharply, half-year growth against last year, monthly sales streaks, margin up on the year (the metrics table, F141, already works these out) | Cross-company views: today only the Inflection Radar does this | Later (owner, 25 Oct: after the 95% go-live gate) | Not started |
| 37 | Industry view: every company's latest quarter growth side by side within its industry, each with its own management words beside it, quoted and dated ("TVS: industry under pressure, -20%" against "Hero: +27%, optimistic") | A card sees up to 5 peer cards but nothing compares them | Later (owner, 25 Oct: after the 95% gate) | Not started |
| 38 | Guidance tracker across companies: raised, cut, withdrawn (e.g. 18% -> 22%), and "said full-year growth above 20%"; first check the AI stores guidance as a number with its period | Guidance revisions are kept per company only | Later (owner, 25 Oct: after the 95% gate) | Not started |
| 39 | Run-rate estimate: e.g. H1 is 65% of last full year and management expects the same run rate, so the year grows ~30%; always "our estimate" with inputs named; seasonality warning | Not built | Later (owner, 25 Oct: after the 95% gate; after 38) | Not started |
| 40 | Capacity coming online next quarter, from management's stated dates (a forward list; today only finished capacity counts on the Radar) | Not built | Later (owner, 25 Oct: after the 95% gate) | Not started |
| 41 | Customer dependence from annual reports (a customer at 10% or more of revenue must be disclosed; link to the customer company only when it is named), e.g. "ABC Auto: 70% from Hero; watch Hero's numbers" | Customers are left out of memory today (a laptop test filled the list with lawsuit parties) | Later (owner, 25 Oct: after the 95% gate) | Not started |
| 42 | Faster NSE history loads: read file links from NSE's all-company results list (about 30 calls) instead of each company's page (about 1,150 calls for 576 companies), with a 1.5-2.5 s pause for one-off loads; the daily results check could use the same list | memory-gaps-fill, 25 Oct: about 1-1.5 h on 4 machines at 3-5 s a call | Proposed (owner to decide) | Proposed |
| 44 | Consolidated first: standalone kept from the AI. The model sees consolidated figures only, each block naming its basis; a printed EBITDA or headline profit is taken only on the card's basis; a standalone figure the model writes on a consolidated card is removed (standalone only for a company that files standalone alone) | Cards quoting the company-alone EBITDA or profit from a release that prints both | Yes (owner, 25 Oct) | Built behind `CARD_CONSOLIDATED_ONLY` and `CARD_EBITDA_PROFIT_V2` (F154); release check pending |

### Owner's answers on memory labels (items 3, 10, 16), 25 Oct 2026 evening

- **Q1 Yes:** an AI-read figure counts as a fact when code finds it on a results or annual-report page with its column
  heading (the period) above it; never from slides or call notes.
- **Q2 Yes:** a year-ago figure that cannot be checked is left blank. Owner: fill them from the exchange files for every
  company once. The seed (`seed-memory`, 21-22 Oct) already read every universe company's results files back to FY21;
  the dry run (build step 2) counts the companies and quarters it still lacks, and those are fetched once before the
  blank rule goes on.
  Built (F148): Maintenance > `memory-gaps` counts the gaps (dry run), `memory-gaps-fill` fetches only those once;
  what stays missing after it is "not found by NSE's results list on <date>", not "no source".
- **Q3 Yes, with a running estimate:** slide and call figures show as "said on <date>". Kept and wanted (owner): a
  running order book, e.g. ₹5,000 Cr in the slides of 21 Oct plus ₹2,000 Cr of orders filed since = about ₹7,000 Cr,
  shown as our estimate with both inputs named. Rules: only orders filed after the slide's date, each order once,
  restarted at the next slides or call; it is not reduced for work done since, and says so.
- **Item 4:** keep filing texts 6 months, then delete automatically (owner, 25 Oct); built (F147).
