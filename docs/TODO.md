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
| 10 | Tag every memory item with: who produced it (exchange figure file / our AI / our own calculation), the kind of document (results statement, call, slides, press release), basis (company alone or group), period, unit as printed, page and quote, and whether it passed our checks. Items with no tag count as "our AI" | Today an item records only which filing and date it came from: an exchange figure and our AI's figure from the same filing look the same, so R1 cannot be applied | Yes | Build order 2nd (with 3), after 23 |
| 4 | R2: keep the text and figure files of every filing for good (not 8 days) | We cannot re-check old cards; the repeat-filing check misses repeats once the text is gone | No | Owner: no change (25 Oct) |
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
| 22 | A per-company metrics table, worked out by code from the exchange files for every quarter (growth YoY and QoQ, margins, cost shares, last-four-quarters totals, EPS; balance-sheet ratios at each half-year; bank metrics for lenders), one table per basis. The AI never types a past number: it names the cell (metric, period, basis) and code writes the value | Wrong past numbers on cards (CIE India, HCL Tech) | Yes (owner, 25 Oct) | Build order 3rd. screener.in may be used as a reference for which metrics investors expect and as a hand spot-check of our numbers in testing; never as a data source on a card (item 3), and not scraped |
| 23 | Use SEBI's official XBRL taxonomy (from NSE's XBRL page; common to NSE and BSE) for every results format: map our lines to the official elements and labels, check every file against the official sums (income − expenses = profit before exceptional items, and so on), and keep the version each file names | Hand-made tag lists; a file tagged wrongly passes unless it trips a guess; the associates' share can leak into EBITDA (item 12) | Yes (owner, 25 Oct: "big yes") | Build order 1st. One-time job per format, then a check per new version. When a file's sums fail, the PDF is the second witness: file fails and PDF adds up, use the PDF's figures; the two disagree, hold that line |
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
| - | Can GitHub's machines reach BSE? (owner's question) | Measured 25 Oct from GitHub (runner in the US, `probe-bse`) and from this session: BSE's website answers (200), its data API refuses ("Access Denied", 403) for both announcements and results. BSE stays off the online path |
| - | Do real figure files add up? (item 23) | Measured 25 Oct, 166 files of 60 random companies (both formats, all templates): 3,355 official sums checked, **one** real mismatch (Master Trust Dec 2024: a broker's expense lines outside the Ind AS sums) and 8 segment-asset totals. Wrongly tagged files are rare: the sums are a safety net, not a big source of fixes |

| # | Improvement | What it fixes | Owner | State |
|---|---|---|---|---|
| 25 | A PDF cut short on NSE (no end of file, no pages) is told apart: wait for NSE to replace it, then fail once with "file cut short on NSE (X of Y MB)" | Apollo Hospitals' amalgamation and Hindustan Zinc's presentation failed as "empty"; the reason was invisible | Yes (25 Oct) | Built (F136) |
| 26 | A filing listed with no file picks up the file when NSE adds it (and is read again if its card came from the title alone) | A card written from the title when the PDF came later | Yes (25 Oct) | Built (F136) |

Build order (owner, 25 Oct 2026): next batch = items 18, 19, 20 (small); then **23** official definitions, then **10 + 3** memory clean-up, then **22** metrics table. Earlier: **batch 1** = items 1, 2, 6, 7 (small, independent; 5 moved to step 2, 9 needed no work); **batch 2** = items 10 then 3 (they change how memory works, so they are built and measured on their own).

## Step 2: reading the file (to discuss)

| # | Improvement | What it fixes | Owner | State |
|---|---|---|---|---|
| 11 | EBITDA: when the company prints EBITDA (press release or slides), show theirs with its own label; when it does not, show ours marked "calculated by us". Our formula stays: profit before exceptional items and tax + interest + depreciation − other income (the owner's note of 25 Oct gives the same formula); none for banks and NBFCs | Cards set our EBITDA against a company's printed one with a different definition (Lumax, Bansal Wire, Solara and others) | Yes (owner, 25 Oct): label ours "Operating EBITDA (calculated)" and show what it leaves out (other income ₹X Cr) | Step 2 |
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
| 14 | Show both EBITDA figures: the company's printed one leads (label "Filing"), ours beneath it (label "Computed"). Year-on-year only within one definition: theirs against their year-ago, ours against ours. When the company prints none, ours alone | The sample marks our EBITDA ₹286.61 Cr as "Statement" while the release prints its own (year-ago ₹212.90 Cr against our ₹213.45 Cr) | Yes (25 Oct) | With item 11 |
| 15 | One profit line everywhere: the one the company headlines in its own release, with its label; with no release, profit attributable to shareholders (the line EPS is on) | Two profit figures on one card read as a mistake | Yes (25 Oct) | To build |
| 16 | A figure computed from memory (cost per MSM from deal history) only when every input is an exchange-file or quoted-filing item (item 10's tags) | Otherwise "Computed" hides an AI-read input | Yes (25 Oct) | With items 3 and 10 |
| 21 | Two parts on every card. Part 1 "From the filing (checked)": exchange-file figures, code calculations, quotes; every line checked, a failed line removed; graded right / WRONG against the 5% bar. Part 2 "Our reading (AI)": interpretation, past promises, what to watch; opinions allowed and graded reasonable / unreasonable on their own bar (10% proposed, owner to set); any number or fact in it must still be right and cite its source, a failed line is hidden, not the card | A wrong opinion and a wrong figure are different faults; readers still judge the whole card | Yes (25 Oct); part 2 bar 30% for now | To build |
| 17 | Measure what more lines cost: a card is WRONG if any one line is wrong, so ~25 lines need each line right about 99.8% of the time to keep cards at 95% | The richer the card, the harder the 95% bar | – | Measure before go-live |

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
