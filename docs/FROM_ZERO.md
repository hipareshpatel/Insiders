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

### What comes in

| What | Where from | What we keep |
|---|---|---|
| The list of new filings | NSE's announcements page, checked every 15 minutes | A row in our database (D1) for each filing |
| The filing itself (PDF) | NSE's link in that list | Only the text we read from it, for 8 days. The PDF is not kept. |
| Results figures in a machine-readable file (XBRL) | NSE's results files | The figures, in our company memory |
| Other machine-readable files | NSE: event files, annual-report files, shareholding | The figures, in our company memory |
| Share prices | Yahoo | Prices on the company page |
| Company memory | **Our own earlier cards and files** | One file per company in storage (R2) |

### What first principles say is wrong here (checked in the code on 25 Oct 2026)

1. **Our memory is fed back in as if it were a source.** Last year's and last quarter's figures in a results table
   come from our memory, and our memory holds what earlier cards and files said. If one earlier reading was wrong,
   every later card that uses it is wrong too. NSE's results files hold only the current quarter, not last year's,
   which is why we lean on memory. This is where most results-table mistakes start (EBITDA defined two ways, one
   company vs the group, profit before or after associates).
2. **We do not keep the filing.** The PDF is thrown away and the text we read is deleted after 8 days
   (`pipeline.yml`, `find data/text_cache -mtime +8 -delete`). So we cannot re-check an old card against exactly what we
   read, and the check for repeat filings only works while the text is still there.
3. **We guess the unit of machine-readable files.** The XBRL file states its own unit, but our reader does not look at
   it (`xbrl.py` never reads `decimals` or `scale`). It guesses by comparing revenue or profit with the PDF. When the
   guess fails, a figure can be 10 or 100 times off (this happened: Jubilant, F54).
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
- Open, not yet measured: why the other failed filings failed (70 on 25 Oct); whether NSE's one-call-a-day list holds
  every filing on a busy day; runs take about 41 minutes, so the 15-minute schedule really runs every ~42 minutes.
