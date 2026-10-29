# The new PDF reader: handover to the lead session, for a go-live decision (29 Oct 2026, ~10:30 IST)

Written by the reader session (branch `ccr-d86d5b66-tvxfy0`, draft PR #215) for the lead session. The owner asks the lead to
decide what goes live. Times are IST. Every number below is measured unless it says "estimate".

## 1. What was asked and what changed

- The owner's direction (28-29 Oct): make the results-statement PDF reader reliable; it must never give a wrong figure; "no
  answer" is acceptable. It acts as a **checker**: the exchange's XBRL arrives within minutes, the PDF confirms, contradicts or
  says unknown. The new reader ("numbers-first", `pipeline/src/bse_intel/pdf_numbers_first.py`) names rows by arithmetic that
  must hold in at least 3 columns; labels can only veto.
- It does **not need the XBRL**: it reads the PDF alone. The XBRL was used only to build the answer keys it is scored on.

## 1a. The lead's four questions, answered first

1. **What it was scored against, on how many filings.** Two answer keys in the repository, every row a figure the page prints:
   - **Normal key** (`docs/bench/normalpdf/`): 337 figures from 50 ordinary results PDFs the live pipeline received 1-27 Oct
     2026, a random sample of what arrives. Keyed by hand from the printed page (the page is the answer; the card's value
     is a second witness only). Revenue, total income, PBT, profit; both bases where printed; crore, lakh and million.
   - **Hard key** (`docs/bench/hardpdf/`): 340 figures from 21 deliberately hard PDFs (scans, rotated pages, garbled text
     layers, two bases side by side, banks and lenders). Built 26 Oct from NSE's results XBRL and checked against the page;
     where the page prints another figure, the page wins.
   - A held-out set of companies (`docs/bench/heldout.csv`) is never tuned on. Right / wrong / blank (frozen 29b51f1):
     **normal 52 / 0 / 19** of 71 (48 / 0 / 19 of 67 without SBICARD, looked at on 29 Oct), **hard 12 / 0 / 32** of 44. The
     hard held-out set is 3 filings: GEOJITFSL 12 of 12 right; J&KBANK 16 blank (no unit read) and REPCOHOME 16 blank (a
     garbled scan). So its 27% is blanks, not wrong figures. It is small: 115 figures in all, 64 right, 0 wrong. Every change
     is re-scored on both keys from frozen code.
2. **Right against wrong.** Numbers-first alone: normal **250 right, 0 wrong, 87 blank**; hard **203 / 0 / 137**. Combined
   with the old reader in front (bench, options on): normal **260 / 0 / 77**; hard **264 / 0 / 76**,
   so 0 wrong in 453 answers alone and 524 combined (677 figures). It leaves a figure blank whenever the sums or labels
   do not prove it. The combined row needs the bench's reading options on: with them off, as live runs, the old reader adds
   1 and 10 wrong (GAEL; VLSFINANCE).
   - **The lead's "19% right, 13% wrong" (27 Oct, run 40414799620) is the old reader on the hard key** (65 right, 10 wrong,
     265 blank). On that same hard key numbers-first alone now gives 203 right and 0 wrong (264 combined). The two numbers are different readers.
   - This morning's annual-report test (46% right, 1.1% wrong) is a different tool on different documents; the new reader
     has not been run on annual reports, so the two are not comparable.
3. **What it is for.** Quarterly results statements only (the four headline figures, any period printed, both bases).
   - It fills: a check of the results cards' headline figures against the PDF (the shadow check, then perhaps holding a card
     the PDF contradicts), and the unit-slip check. It can also give a filing's figures with no XBRL.
   - It does not fill: FY23 years or lender years from annual reports. It was never built or tested on annual-report
     statements. If the BSE annual-report XBRL covers FY23, that is the better source, and the reader should not be extended
     for history. So on history the reader should indeed do less; its use is checking cards.
   - On cards its reach is limited: the 26 Oct audit's 29 wrong cards are mostly the AI's writing, and the estimate (not
     measured) is that it could catch 4-6 of them. The shadow check exists to measure that before anything is held.
4. **What is built where.**
   - `main`: the first numbers-first reader (d2b2935, "bench only", 28 Oct), long before the 29 Oct fixes.
   - Branch `ccr-d86d5b66-tvxfy0`, draft **PR #215**, not merged, contains `main` (no conflict at 29 Oct ~10:45 IST) plus 67
     commits: every reader fix since, the bank chain, the empty-cell re-read, the unit-slip switch (eb2474a), the shadow job
     (0739dcf), the bench workflow job `pdf-bench` and these notes.
   - The parked branch `claude/gracious-goodall-jn9buu` (EBITDA check, narrowed grounding) has nothing of this reader.

## 2. Where the reader stands (both answer keys, frozen code, 0 wrong throughout)

| | Normal key (337 figures) | Hard key (340 figures) |
|---|---|---|
| Start of 28 Oct night | 144 right / 0 wrong / 193 no answer | 168 / 0 / 172 |
| 29 Oct ~09:00 (29b51f1), combined (old reader first, numbers-first where it gives none) | **260 / 0 / 77** (77%) | **264 / 0 / 76** (78%) |
| Same code, **numbers-first alone** (what the shadow check uses; the slip check asks it first) | **250 / 0 / 87** (74%) | **203 / 0 / 137** (60%) |
| Same code, live reading options off (190765c): numbers-first alone / combined | 250 / 0 / 87 / 255 / **1** / 81 | 203 / 0 / 137 / 240 / **10** / 90 |
| Combined with the empty-cell re-read on (`PDF_CROP_REREAD=1`, off by default) | 262 / 0 / 75 | 266 / 0 / 74 |

- 0 wrong in 677 figures bounds the wrong rate at about 0.45% (rule of three). The owner's proof size is 1,000 figures (TODO 119).
- The go-live bar set earlier for the reader (98% right, at most 5% no answer) is **not met**.
- The old reader (what the live site uses): normal key 44 / 0 / 293; on 27 Oct, hard key 65 right / **10 wrong**.
- 29 Oct fixes, each with a test that fails without it and an independent review: banks in RBI format (KARURVYSYA, RBLBANK,
  UNIONBANK, ICICIBANK: 35 figures; a bank's "revenue" in the key is interest earned), a numbered associates' share (ATUL,
  BFINVEST), "not required to prepare consolidated results" (SBICARD).
- Tried and dropped, measured: joint match of the four XBRL figures to pick a column (244 false confirms), cell-by-cell merge
  of scanner text and OCR (0 gain), basis from the auditor's report (no safe rule), Tesseract as a second engine (0 of 15),
  page OCR at 300 dpi (5 -> 6 right of 120, +71% time).
- Full record: `docs/bench/READER_HANDOVER.md`.

## 3. What the live site does with PDFs today (traced in the code on 29 Oct)

1. **PDF to text for the AI that writes cards** (`extract.py`): text layer, our OCR on pages of figures, a vision model on
   textless scans within a quota. Not a figure reader; the new reader cannot replace it.
2. **The unit-slip check** (`slip_check.py`, F200): only when an XBRL file looks 10x / 100x off, the corrected figure is kept
   only if the PDF prints it. Uses the old reader, text layer only. Runs a handful of times.
- The new reader is **not used live**. `PDF_READERS` only changes the bench and the `pdf-referee-ensemble` maintenance job.
- Live card WRONG (cards filed 26 Oct): 29 of 154 (18.8%). Almost all are in what the AI writes (watch verdicts, wrong period,
  mixed bases, invented, direction), not in the exchange's figures. The lead's estimate (not measured): the reader could catch
  about 4-6 of the 29 (SONACOMS 10x unit, AVANTEL column swap, some period / basis figures), so about 18.8% -> 15-16%. It does
  not reach 5% alone.

## 4. What is built (all on PR #215, every switch off by default)

| Piece | Commit | Switch | State |
|---|---|---|---|
| The reader and all fixes | many, latest reader code 1fcb1ae | bench only | tested, reviewed, CI green |
| Empty-cell re-read from crops | 0b30926, 1fcb1ae | `PDF_CROP_REREAD` | reviewed; +4 figures; ~12-17 s a filing against ~9 s |
| Unit-slip check asks the new reader first, old reader as fallback, same download | eb2474a | `SLIP_CHECK_NUMFIRST` (repository variable) | 7 tests; independently reviewed, its two fixes in 58b4eb1 (a later candidate filing can still prove the figure; no second download) |
| Shadow check of live results cards (TODO 121): one row per card figure, agrees / disagrees / unknown, seconds per PDF, to R2 `meta/pdf-shadow/`; hourly workflow `pdf-shadow.yml`; figures that agree on different bases are flagged as mixed bases | 0739dcf | `PDF_SHADOW=on` (repository variable) | 12 tests; independently reviewed, fixes in 58b4eb1: a failed read of the day's log stops the run (it could overwrite the log); verdicts agrees / disagrees / unknown / basis_mismatch / mixed_bases / unclear (a consolidated profit may be the owners' share) |

## 5. Open before anything goes live

1. **The live reading options: done (eda3793).** Measured with the three options off (as the live pipeline runs), the new
   reader fell to 227 (normal) and 133 (hard) right, still 0 wrong; the old reader in that mode gave 1 and 10 wrong. The new
   reader now turns the three on for its own calls only (a per-thread switch), so live it reads as measured.
2. **Runner time.** Maintenance run 40810936312 (pdf-bench on this branch, started 08:43 IST) measures both readers on a runner
   with fresh OCR. The 28 Oct run: about 76-84 s a filing on the answer keys (mostly scans). Locally on 29 Oct, fresh OCR at
   200 dpi: 29-78 s for each of 8 hard scanned filings.
3. **Reviews: done.** One independent review of both; every defect it found is fixed with a test (58b4eb1).
4. **TODO 120** (owner chose "check first"): the live reader reads "Non-Consolidated" as consolidated; recorded, not changed.

## 6. The decisions asked of the lead (the reader session's recommendation in brackets)

1. **Merge PR #215 to `main`?** Every new behaviour is behind a switch that is off, so a merge alone changes nothing live.
   (Yes, once CI is green and item 5.3 is done.)
2. **Switch on `SLIP_CHECK_NUMFIRST`?** Rare and low-risk: the old reader still decides wherever the new one has no answer;
   it removes the old reader's wrong calls in that step. Visible effect on cards: very small. (Yes, after items 5.1 and 5.3.)
3. **Switch on `PDF_SHADOW` (the shadow check)?** Writes only a log; nothing on the site changes. After 2-3 days, compare its
   "disagrees" with the daily card audit: real wrong cards caught, false alarms. (Yes, after it is reviewed and item 5.2 shows
   it fits; it runs beside the 15-minute pipeline, not inside it.)
4. **Hold cards the PDF contradicts?** Only after the shadow data shows real catches and no false alarms. This is the step that
   would raise OK cards; it is the owner's call. (Not yet.)
5. **`PDF_CROP_REREAD`?** +4 figures for ~+50% time per filing. (Off until the runner time is known.)
6. **Optional, owner's Yes / No:** re-run the maintenance PDF referee with the new reader (`pdf-referee-ensemble` exists; the old
   reader misread 9 of 18 hand-settled cases); measure the restated-figures check with the new reader. The XBRL key builder must
   stay independent of the reader (it is the answer key).

What the owner should not expect: more OK cards from today. Items 1-3 change nothing visible; item 4 is the one that would,
and it needs the shadow data first.
