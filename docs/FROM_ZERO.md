# Starting from zero: how our data comes in and where mistakes start

The owner asked on 25 Oct 2026 to look at the whole system again from first principles, one step at a time, in very
simple English. This file records each step: what we have, what is wrong with it, and what the owner decided.
Code details for every step are in `docs/ARCHITECTURE_AS_BUILT.md` (branch `claude/gracious-goodall-jn9buu`).

## The one idea everything rests on

A card is right only if every figure on it can be found in the company's own filing, for the right period, the right
basis (one company alone or the whole group) and the right unit (lakh or crore). So a card can go wrong in five places:

1. **We fetch the wrong thing, or miss part of it** (collecting).
2. **We read the file wrongly** (a figure lost, moved to the wrong column, wrong unit).
3. **We pick the wrong figure** (last year's number, the group number instead of the company number).
4. **The AI writes it wrongly** (copies a figure badly, says "up" when it went down).
5. **Our checks let a wrong card through, or throw a right one away.**

The last trace of 48 wrong cards (95 faults) found: our own code 40, the AI writer 36, the input 12, our memory 7.

## Step 1: what we collect, and from where

### What comes in (from the code, 25 Oct 2026)

Almost everything comes from NSE. Two things come from elsewhere: share prices (Yahoo) and trade-remedy cases (DGTR).

| # | What | From where | How often | Used for |
|---|---|---|---|---|
| 1 | The company list | NSE's list of listed shares (EQUITY_L.csv); we keep companies worth ₹500 Cr or more | Weekdays | Which companies we cover |
| 2 | The list of new filings | NSE "Corporate announcements" | Every run | Finding each new filing, its title and its PDF link |
| 3 | The filing itself (PDF) | NSE's archive, from the link in 2 | Each filing | The card's text: results, slides, call transcripts, orders, and so on |
| 4 | Results figures (XBRL) | NSE "Financial results" and "Integrated filing" pages | Each results filing | The results table's current quarter |
| 5 | Event figures (XBRL) | NSE "Announcements XBRL" (three kinds: announcements, Reg 30 events, corporate actions) | Each filing that has one | Orders, deals, actions |
| 6 | Annual-report figures (XBRL) | NSE "Annual reports XBRL" | Daily catch-up | Annual-report cards |
| 7 | Shareholding (XBRL) | NSE "Shareholding pattern" | Daily | Memory only: promoter, FII, DII holdings |
| 8 | Governance reports | NSE | Daily | Memory only: board, auditor |
| 9 | Promoter pledges | NSE SAST Reg 31 list | Daily | Pledge news |
| 10 | Insider trades | NSE PIT Reg 7 list | Daily | Insider news |
| 11 | Bulk and block deals | NSE large deals | Daily | Deal news |
| 12 | Trade-remedy cases | DGTR's website | Daily | Linked only to companies a notice names |
| 13 | Share prices | Yahoo | Daily | Company page, price at the time of a filing |
| 14 | Company memory | **Our own earlier cards and the files above** | Each card | Last quarter's and last year's figures, guidance, orders, notes |

### What first principles say is wrong here (checked in the code on 25 Oct 2026)

1. **Our memory is fed back in as if it were a source.** Last year's and last quarter's figures in a results table
   come from our memory, and our memory holds what earlier cards and files said. If one earlier reading was wrong,
   every later card that uses it is wrong too. NSE's results files hold only the current quarter, not last year's,
   which is why we lean on memory. This is where most results-table mistakes start (EBITDA defined two ways, one
   company vs the group, profit before or after associates).
2. **We do not keep the filing.** The PDF is thrown away and the text we read is deleted after 8 days
   (`pipeline.yml`, `find data/text_cache -mtime +8 -delete`). So we cannot re-check an old card against exactly what we
   read, and the check for repeat filings only works while the text is still there.
3. **We ignore the precision the XBRL file states.** Values are always in rupees; `decimals` says how the company
   printed them (crore or lakh), and our reader does not look at it. Corrected 25 Oct after a live check: this is not a
   unit guess. A file the company itself tagged at the wrong scale (Jubilant, F54) is caught by our check against the
   PDF, and `decimals` would not catch it.
4. **Some filings never reach us.** Companies listed only on NSE are set aside as "not in the company master". These
   are gaps in what we cover, not wrong cards, but they are invisible unless someone looks. (Shareholding filings are
   set aside from the card path, but a separate daily job reads every company's shareholding file into memory: no gap.)

### The rules proposed for step 1 (waiting for the owner)

- **R1.** A figure on a card comes from an exchange file only: this filing, or an earlier exchange file we kept with its
  name and page. Never from what our AI wrote earlier.
- **R2.** Keep what we read: the text and the machine-readable files for every filing, for good (in R2, not the
  8-day cache), so any card can be checked again later. Assumption, to measure before building: about 20 KB of
  compressed text per filing, so storage stays small.
- **R3.** Read the unit that the machine-readable file states. Use the guess only when the file states none.

### Step 1 findings and decisions (25 Oct 2026)

- Of the 95 wrong points in the 25 Oct trace, 1 started at fetching (Panache filed the same PDF twice and the repeat
  check, which needs the first filing's text, did not catch it). The 12 "input" points are reading problems (slides
  whose numbers and labels come out apart, poor scans: step 2) and two speakers' own slips.
- We skipped large PDFs: a 30 MB cap for everything but annual reports. NHPC's FY26 results (nse-106633606) was
  skipped on 25 Oct and failed as "no readable text". **Decided (owner): 120 MB for every filing** (F130).
- NSE's one-call-a-day list, measured 25 Oct for 23 Oct (601 filings): 120 companies asked one by one gave 113
  filings, all in the list. No gap found; repeat on a peak results day.
- NSE-only companies: none set aside (company-list job, 23 Oct: 2,613 listings, all matched).
- Open: why the failed filings failed (70 on 25 Oct; `failed-report` after batch 1); runs take about 41 minutes, so the 15-minute schedule really runs every ~42 minutes.

### Past results history (checked 25 Oct 2026)

Measured 25 Oct 2026: NSE lists every quarter's results figure file per company, both bases, on two pages
(`corporates-financial-results` up to Dec 2024: 130 rows for RELIANCE; `integrated-filing-results` from Mar 2025:
12 rows, Mar 2025 to Jun 2026). One file holds one quarter only (all 38 contexts of RELIANCE's Jun 2026 consolidated
file are that quarter), in rupees, with `decimals="-7"` (printed in crore). So year-ago and last-quarter figures come
from those quarters' own files.

This is already built: `seed-memory` (`seed.py`, run from `maintenance.yml` since 20 Oct) reads 12 quarters from NSE
into memory, consolidated first, standalone kept apart. RELIANCE's memory holds Q1FY27 revenue ₹3,11,850 Cr from
`xbrl:res:500325:Q1FY27`, the same as the file. What history does not fix: our own EBITDA definition (memory says
Q1FY27 EBITDA ₹47,517 Cr = profit before tax + finance cost + depreciation − other income; companies that count other
income print a different figure), the choice of basis, and figures our AI wrote into memory before the file existed.

### The official XBRL taxonomy (found 25 Oct 2026)

Measured 25 Oct 2026: the results files are written against SEBI's own taxonomy (`in-capmkt`; RELIANCE's Jun 2026 file
names `in-capmkt-ent-2026-01-31.xsd`, namespace `http://www.sebi.gov.in/xbrl/IntegratedFinance_IndAS/2026-01-31/...`).
NSE publishes it on its "XBRL information" page (`/static/companies-listing/xbrl-information`): one package per format
(Ind AS, other than banks, banking, NBFC, general and life insurance, REITs/InvITs), for both the old Regulation 33
results and the Integrated Filing. NSE's 2018 circular says the results taxonomy is common to NSE and BSE, so one set
covers both. The Ind AS Integrated Filing package (`Taxonomy Integrated filing finance (IndAS).zip`, version
2025-01-31) holds the element list, 499 official labels, and the calculation, presentation, definition and reference
linkbases. The 2026-01-31 version the live files use is still to be found (the "Taxonomy Archives" zip, or NSE's
XBRL desk, nsexbrl@nse.co.in).

What it settles, read from the calculation linkbase:
- Profit before exceptional items and tax = Income − Expenses; profit before tax = that + exceptional items.
- Profit for the period = continuing operations + discontinued operations + **share of associates and joint ventures**.
  So the associates' share is added after tax, and profit before tax excludes it by definition. Our EBITDA starts from
  profit before exceptional items, so it is clean; but `xbrl.settle_pbt` swaps in an after-associates profit before tax
  when a filer tags it that way (Orient Bell), and EBITDA falls back to that figure when no before-exceptional profit
  is tagged. That is where item 12's error can enter.
- Every file can be checked against these sums: a file whose lines do not add up was tagged wrongly.

### An outside review of step 1 (Gemini, shared by the owner 25 Oct 2026), checked against the code

- "Add BSE as a source; its event XBRL is more mature": not possible from where the pipeline runs. BSE refuses
  non-Indian IPs and the pipeline runs on GitHub's US machines (CLAUDE.md; D34); the BSE code is an off-path backup.
  The results taxonomy is common to NSE and BSE (NSE circular, 2 May 2018). Whether BSE has event files NSE lacks is an
  assumption, not checked.
- "Keep management claims (calls, slides) apart from the audited figures": agreed, and already the plan: item 10 tags
  every memory item with its document kind, item 3 keeps call and slide figures out of tables and key numbers, item
  21 puts them in the card's second part.
- "No adjustment for splits and bonuses": already built. `corporate_actions.py` reads NSE's corporate-actions feed and
  turns each split, bonus and consolidation into a factor that EPS and share counts are adjusted by (LIC's 1:1 bonus,
  Kapston's 1:2).
