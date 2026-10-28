# The PDF reader for results statements: handover (28 Oct 2026, 15:40 IST)

For a new session that takes over the PDF reader. Read `CLAUDE.md`, `docs/STATUS.md` (section 3, item 3) and `docs/FROM_ZERO.md`
(step 2, F) first. This page holds what was learned and agreed in the 27-28 Oct sessions, including the outside reviews the owner
pasted in (Gemini, ChatGPT, and a long answer from another Claude). Each idea below says whether we adopted it, weakened it or turned
it down, and why.

## 1. The goal, and what the owner decided

- **The reader's job may be changing from "read everything" to "check, and never be wrong".**
  - The owner said on 28 Oct: "PDF and XBRL almost come together or might be a few minutes delay. Once we get XBRL and Screener
    matching, we will use XBRL only for cards."
  - If that holds, the reader is a checker. It catches XBRL files that are wrong (IMPAL Q1FY27 was 100 times too small) and checks
    BSE figures. Precision matters far more than coverage: a checker may skip a figure, but it must almost never be wrong.
  - The timing is an **assumption** for results until measured. The bulk XBRL download started on 28 Oct records NSE's own timestamps
    for this (STATUS, "Afternoon of 28 Oct"). For Reg 30 event XBRL it was measured on 18 Oct: 8 minutes median, up to 21 hours.
  - Until it is measured, keep both targets in view. Never trade a wrong answer for coverage.
- **Owner's rules for the reader:**
  - The answer key follows the printed page, not the XBRL. Example: SPANDANA Q2FY24 prints 610.27 and the XBRL has 610.26; the key
    holds 610.27.
  - **One filing at a time** (owner, 28 Oct, ~06:50 IST, STATUS item 3).
    - Fix everything on one PDF, then move to the next, a new layout each time: upright, sideways, tilted, scanned, sub-headings,
      units, notes.
    - Re-score every fix on the whole key, and keep it only if nothing gets worse. On 27 Oct a fix for one PDF broke the Titan test.
  - Pass marks for the normal key: **98% right, at most 5% no answer** (`docs/bench/normalpdf/README.md`). No reader meets them yet.
  - Where a BSE figure fills memory and the PDF disagrees: if the reader is confident and differs, hold the figure back. If the reader
    cannot read the page, write the figure marked "unchecked".
  - Annual-report PDFs wait until the reader proves itself on results statements. Annual XBRL is used where it is listed.
  - Cards show the continuing-business profit only. EPS is never shown on cards; memory keeps it for checks.
- **The lead's stop rule (28 Oct):** if about five fixes in a row do not move the measured rate, stop patching. Test two or three really
  different approaches side by side on the same key. For a week, about 120 small patches to the old reader left the WRONG rate
  between 15% and 23%. That was the "easy path" the owner criticised.

## 2. Where things stand (measured)

**The keys.**

| key | file | figures | filings | what is in it |
|---|---|---:|---:|---|
| normal | `docs/bench/normalpdf/key.csv` | 337 | 50 | revenue, total income, PBT, PAT; mostly scans (below) |
| hard | `docs/bench/hardpdf/key.csv` | 340 | 21 | revenue and PAT; lenders and banks, almost all scans without a text layer, not Schedule III |
| XBRL key | built by `xbrl-key` (`xbrl_key.py`, locator `2026-10-28.4`) | thousands | many | memory's exchange-file figures placed on the PDF page by word position; read only |

Every row carries its `pdf_url` and tags (`scanned_no_text_layer`, `lender`, `two_bases_separate_pages`...).

**Scores: right / wrong / no answer** (`docs/bench/normalpdf/numbers-first-2026-10-28.md`, `score-baseline-2026-10-27.md`). Flags
`PDF_DATES_2DIGIT`, `PDF_PAGE_RANK` and `PDF_ROW_FIXES` were all 1.

| reader | normal key (337) | hard key (340) |
|---|---|---|
| `native` (today's reader) | 45 / 0 / 292 | 156 / 0 / 184 |
| `numfirst` (numbers-first, bench only) | 125 / 0 / 212 | 71 / 0 / 269 |
| combined (native first, numfirst where native gives none) | **150 / 0 / 187** | **168 / 0 / 172** |

- Zero wrong in 677 figures bounds the true wrong rate at about 3/677, so about 0.45% (rule of three, below).
- On the normal key, native has no rows for total income or PBT at all, and 29 of 50 filings get no answer.
- Numfirst is worse on the hard key. That key is mostly lender layouts, where the chain total income - total expenses = PBT does not
  hold in the form the solver looks for.
- **Correction that must not be lost:** the "98.5%" of 17 Oct measured OCR text on 7-8 hand-picked filings, not the reader finding the
  right line. On 27 Oct (run 40414799620), over the hard set the reader gave 65 right, 10 wrong and no answer for 265. Never quote
  98.5% as the reader's accuracy.

**Why figures are lost.** This was found by the XBRL key on the two typed keys, 28 Oct. Most of the "normal" PDFs are scans:

| how the page was made | figures | placed for certain |
|---|---:|---:|
| typed (made on a computer) | 32 | 28 |
| scanned, the scanner's hidden text layer | 143 | 42 |
| scanned, text layer garbled ("30.09.202S", "Re\.enue", "Vear Ended") | 122 | 23 |
| scanned, no text at all | 40 | 0 |

Where the unplaced figures were lost (normal / hard):
- the label or date is garbled: 128 / 151;
- the number is not in the text layer: 62 / 47;
- the statement page was not found: 43 / 0;
- the unit was not read: 10 / 0.

**Conclusion:** on scans the problem starts before our reader runs, so our own OCR has to replace the scanner's text layer. On typed
pages the position method already works (28 of 32).

**The XBRL key's first live run** (`docs/audit/xbrl-key-disagreements-2026-10-28.md`): 28 figures where the row was on the page but
another number was printed.
- 7 were wrong in memory: IMPAL Q1FY27, the 100x slip, now fixed and on the known-wrong list.
- 9 were the locator's misreads: fixed in locator `.4`.
- 12 were another line by definition: taxonomy against printed total expenses, other income including finance income, continuing
  against discontinued.

## 3. Code map

- `pipeline/src/bse_intel/pdf_readers.py`: `READERS`, `Ensemble`, `settle` (the agreement rule), `configured_readers()` (env
  `PDF_READERS`, default `native`).
- `pipeline/src/bse_intel/pdf_numbers_first.py`: the `numfirst` reader. It is bench only, has no switch and is in no live path. What it
  does:
  - number tokens first, with columns and rows from coordinates;
  - a "Note" column treated as label text (Gemini's point, adopted);
  - decimals consistent within a column;
  - label stitching;
  - column dates and kinds;
  - a vertical arithmetic solver (each identity must hold in three columns, may fail in one, and must hold in the period's own column);
  - labels can only veto;
  - two explanations give no answer;
  - no unit gives no answer;
  - OCR for pages with no text layer and for garbled scans, 8 pages a PDF at most.

  19 tests are in `pipeline/tests/test_pdf_numbers_first.py`. The commit is in PR #214, which may already be merged. An independent
  review was running at handover; its findings go on that PR.
- `pdf_referee.py`: page finding, unit lines (`grounding.unit_before`), the boxed-table basis, `_pattern_kinds`, `be_gentle()` (leave a
  core free; full-core OCR once killed a runner).
- `ocr.py`: RapidOCR 3.10 with measured settings, deskew, row clustering, bracket repair, sideways pages. About 4-5 s a page.
- `extract.py`: `upright_text`. `xbrl_key.py` (and its tests `test_xbrl_key_misreads.py`): the word-position locator.
- `pdf_bench.py`: `load_key`, `answer_pair` (the scoring path), `outcome` (right means within half a unit of the printed decimals, and
  at least 0.005 Cr), `score`, `to_markdown`, `collect` and `run`.
- History worth reading: `docs/bench/hardpdf/why-readers-fail.md`, `docs/bench/hardpdf/reader-fixes-2026-10-27.md`,
  `docs/bench/normalpdf/README.md`.

## 4. How to score: the same path for every change

```bash
cd pipeline
# 1. Get the key's PDFs (NSE, the client's own pace, one at a time). The first fetch on a new path follows the 100-file rule; keep every file.
python -m bse_intel.pdf_bench --collect ../docs/bench/normalpdf/key.csv ../data/bench/normal
python -m bse_intel.pdf_bench --collect ../docs/bench/hardpdf/key.csv ../data/bench/hard
# 2. Score (both keys, every change, before and after)
export PDF_DATES_2DIGIT=1 PDF_PAGE_RANK=1 PDF_ROW_FIXES=1
PDF_READERS=native          python -m bse_intel.pdf_bench --run ../docs/bench/normalpdf/key.csv ../data/bench/normal out/native-normal
PDF_READERS=native,numfirst python -m bse_intel.pdf_bench --run ../docs/bench/normalpdf/key.csv ../data/bench/normal out/comb-normal
# (and the same for the hard key)
```

- From GitHub, the hard key is also scored by Maintenance `pdf-referee-ensemble` with `ids` = `hardset`.
- Cache OCR boxes by the page image's sha1 while iterating. A full OCR pass over both keys is slow.
- Report each change as a right / wrong / no answer table per metric for both keys, plus which filings moved. The one rule: a change that
  adds any wrong answer, or loses right ones on the other key, is not kept as it is.

## 5. Ideas agreed with the outside reviews (adopted)

| # | idea | from | status |
|---|---|---|---|
| A1 | **Numbers first**: find the number rows, let arithmetic name them, labels only veto | web idea, lead | built (`numfirst`) |
| A2 | **A "Note" column is label text**: in "Revenue from operations 24 1,245.60", the 24 is not revenue | Gemini | built in `numfirst` |
| A3 | **Our own OCR replaces a bad scanner layer**: re-read only the bad parts of the page; keep the layer where its numbers are sound; when the two disagree on a digit, give no answer | ChatGPT, XBRL-key finding | partly: numfirst OCRs no-text pages and scans with no named row; the digit-level gate is not built |
| A4 | **Offline OCR relabel of the answer key**: the XBRL key finds figures by searching the text, so pages with no text never get a key row, and anything tuned on it learns only the easy pages. Read those pages offline with OCR at the slowest, best settings, then search for the known figures there | the long Claude answer | not built; do it before tuning on the XBRL key |
| A5 | **Date-candidate matching**: we know which dates a quarter's columns should show, so a garbled "30.09.202S" only has to match one of about five expected dates | the long Claude answer | not built; it targets the biggest loss (garbled label or date, 128 / 151 figures) |
| A6 | **More sum checks**: half year = this quarter + last quarter (most filings arriving now are Q2), nine months = H1 + Q3, year = 9M + Q4, last quarter's own column equals this filing's previous-quarter column; a match in every column at once is hard to get by luck | the long Claude answer, STATUS item 3 | partly (numfirst checks vertical identities, not across periods) |
| A7 | **Fill empty cells with two OCR engines**: re-read only the empty cell with two different free engines and accept a figure only when both agree | the long Claude answer | not built |
| A8 | **Never publish a computed figure**: a figure the arithmetic implies but the page does not print is never an answer | the long Claude answer | numfirst answers only printed cells (check that the review confirms it) |
| A9 | **Test sizes for "zero wrong" (rule of three)**: 0 wrong in n bounds the rate at about 3/n. 0 in 150 is under 2%; under 0.3% needs about 1,000 with none wrong. The lead proposed a bar of at least 3,000 figures across companies | ChatGPT, the long Claude answer | adopted as the way to state results; the bar size is not yet the owner's decision |
| A10 | **Hard negatives**: test on the traps (the right number in the wrong column, the right period on the wrong basis), not random wrong examples | ChatGPT | adopt in the next key work |
| A11 | **Held-out companies and layouts**, not random rows: one company's filings look alike every quarter, so a random split flatters the score | ChatGPT | adopt: keep a held-out set of companies that no fix is tuned on |
| A12 | **Measure the page finder on its own**: is the right statement page in the top 3, 5 or 8 picked? Include the next page, since statements often run onto a second page | ChatGPT | not built |
| A13 | **One layout per company, reused each quarter**; pages sorted first by type | owner and lead, STATUS item 3 | not built |
| A14 | **Vision fallback that points, never types**: the model is shown numbered marks on the page (Set-of-Marks) and picks a mark's id; the digits always come from the text or OCR | Gemini (its answer was cut off at this point), ChatGPT, the long Claude answer | **last**, only for the one or two pages a filing fails on (see W3) |

## 6. Ideas weakened or turned down

- **W1. Use memory's past figures to find the unit**: only with figures marked as checked by two sources. Memory had 10x and 100x slips
  (DOLPHIN, IMPAL), so unchecked figures would copy old mistakes into new ones.
- **W2. A trained ranking model (LightGBM)**: too early with 50 filings in the normal key. It makes sense once the XBRL key, with the
  OCR relabel (A4), covers thousands of figures.
- **W3. Vision fallback costs**: it uses free-tier requests, and reading each page twice doubles them. Steady state must stay $0. Check
  that the model named is still offered before building it (`python -m bse_intel models`). Vision silently swaps digits in small print
  (measured 17 Oct: 7,993 read as 7983; 2.4% of its figures are not on the page), which is why it may only point.
- **W4. Claims in the outside answers with no source, so do not repeat them**: "quarterly XBRL has about 37% / 63% errors" (measured:
  0 differences in 2,780 figures for 5 companies; one bad file, IMPAL, in 73 filings) and "35% of pages sideways". Their idea of not
  trusting the XBRL as the production answer is turned down for now: the XBRL is the daily source and the PDF is the judge.
- **W5.** Gemini's points that annual-report PDFs are digital and bookmarked, and that annual XBRL arrives in Sep-Oct, are only partly
  true. ITC FY26 came on 20 Aug and L&T FY26 on 4 Jul, but L&T FY25 only on 13 Jan 2026. Annual work waits anyway (section 1).

## 7. Recommended order (proposed by the lead on 28 Oct; the owner has not yet said Yes to it as a whole)

1. **Measure when results XBRL appears against the PDF**: the bulk download's timestamps; it decides the target (checker or reader).
2. Run the reader on the **XBRL key**, which no fix was tuned on, after the **OCR relabel** (A4) so that scans are in it.
3. **Date-candidate matching** (A5) and the **extra sum checks** (A6).
4. **Two-engine hole fill** (A7).
5. **Vision pointer-only fallback** (A14), only if gaps remain.

Throughout, work one filing at a time (section 1), score both keys plus the held-out set, keep zero wrong, and apply the stop rule.
Record the owner's answer to this order in `docs/TODO.md` (batch rule).

## 8. Rules and traps

- **NSE downloads.**
  - The NSE client code and its pacing stay as written. The first fetch on a new or changed path is a 100-file test, and every file it
    downloads is kept.
  - Stop at once on any refusal.
  - Never open screener `/company/source/` pages, and respect robots.txt.
  - No headless browser.
- **Memory.** Never hand-edit stored data. A fix that changes memory follows `docs/DATA_QUALITY.md` and the owner's A/B/C freedoms in
  `docs/STATUS.md` section 0.
- **Readers in the live path.**
  - A reader goes live only behind a switch, after the on/off check over stored cards and a blind sample (owner's C).
  - The live default stays `native` until then.
- **Reviews.** Independent review by a subagent that did not write the fix (not the smallest model). The fix's author never grades it.
- **Labels.** "Total" or "(I+II)" alone names nothing. Bank layouts (interest income, operating profit before provisions) are not
  Schedule III.
- **Consolidated and standalone.**
  - They often sit on different pages, and the title above the table decides the basis.
  - Profit including discontinued operations is not memory's continuing profit (ABREL Q4FY26 -110.31 against 5.39).
  - A half-year column is not the quarter (AXISBANK Q2FY27 15,306 is six months).
- **Units.** Lakh against crore is the commonest slip. With no unit, give no answer.
- **Commits.** No AI model names in commits, PR text or code.
- **Writing to the owner.** Plain English, IST times.

## 9. Open questions for the owner

- The order in section 7: **answered, Yes as proposed** (owner, 28 Oct 2026, ~15:45 IST; `docs/TODO.md` item 114).
- The size of the "zero wrong" bar: **answered, 1,000 figures** across companies (owner, 28 Oct 2026; the lead had proposed 3,000).
- Whether `numfirst` (combined with native) goes behind a live switch once it passes on the XBRL key. It is bench only today.
