# The new PDF reader: handover to the lead session, for a go-live decision (29 Oct 2026, ~10:30 IST)

Written by the reader session (branch `ccr-d86d5b66-tvxfy0`, draft PR #215) for the lead session. The owner asks the lead to
decide what goes live. Times are IST. Every number below is measured unless it says "estimate".

## 1. What was asked and what changed

- The owner's direction (28-29 Oct): make the results-statement PDF reader reliable; it must never give a wrong figure; "no
  answer" is acceptable. It acts as a **checker**: the exchange's XBRL arrives within minutes, the PDF confirms, contradicts or
  says unknown. The new reader ("numbers-first", `pipeline/src/bse_intel/pdf_numbers_first.py`) names rows by arithmetic that
  must hold in at least 3 columns; labels can only veto.
- It does **not need the XBRL**: it reads the PDF alone. The XBRL was used only to build the answer keys it is scored on.

## 2. Where the reader stands (both answer keys, frozen code, 0 wrong throughout)

| | Normal key (337 figures) | Hard key (340 figures) |
|---|---|---|
| Start of 28 Oct night | 144 right / 0 wrong / 193 no answer | 168 / 0 / 172 |
| 29 Oct ~09:00 (29b51f1) | **260 / 0 / 77** (77%) | **264 / 0 / 76** (78%) |
| With the empty-cell re-read on (`PDF_CROP_REREAD=1`, off by default) | 262 / 0 / 75 | 266 / 0 / 74 |

- 0 wrong in 677 figures bounds the wrong rate at about 0.45% (rule of three). The owner's proof size is 1,000 figures (TODO 114).
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
| Unit-slip check asks the new reader first, old reader as fallback, same download | eb2474a | `SLIP_CHECK_NUMFIRST` (repository variable) | tested (5 tests), CI green; **independent review not yet done** |
| Shadow check of live results cards (TODO 116): one row per card figure, agrees / disagrees / unknown, seconds per PDF, to R2 `meta/pdf-shadow/`; hourly workflow `pdf-shadow.yml` | not committed yet | `PDF_SHADOW=on` (repository variable) | **being built by a helper; not reviewed** |

## 5. Open before anything goes live

1. **The live reading options.** The reader was measured with `PDF_DATES_2DIGIT`, `PDF_PAGE_RANK`, `PDF_ROW_FIXES` on; the live
   pipeline runs with them off. A re-score with them off is running. If it is worse or not 0 wrong, the new reader must turn
   them on for itself only (small change) before `SLIP_CHECK_NUMFIRST` is switched on.
2. **Runner time.** Maintenance run 40810936312 (pdf-bench on this branch, started 08:43 IST) measures both readers on a runner
   with fresh OCR. The 28 Oct run: about 76-84 s a filing on the answer keys (mostly scans). Locally on 29 Oct, fresh OCR at
   200 dpi: 29-78 s for each of 8 hard scanned filings.
3. **Reviews:** the unit-slip change (eb2474a) and the shadow job need an independent review.
4. **TODO 115** (owner chose "check first"): the live reader reads "Non-Consolidated" as consolidated; recorded, not changed.

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
