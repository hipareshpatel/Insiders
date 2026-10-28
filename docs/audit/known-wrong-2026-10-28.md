# Taking the 35 proven-wrong figures out of memory (plan, 28 Oct 2026)

Owner's rule (STATUS section 0, A): a figure proven wrong in memory is fixed as a class in code with a test, only the affected
filings are re-read (at most 50 filings a run), nothing is edited by hand, every write has a backup first and `restore` undoes it.
This page is the plan. **Nothing has been run.** The code it needs is in this change: `known_wrong.py` (the list),
`memory_drop.py` and the command `memory-drop-known-wrong` (the removal), and the list is honoured by every memory writer.

How this was worked out: offline, from the code and the tests, with no access to R2 or the stored dossiers. Every claim below is
either "measured <date>" with its source, "read in code" (a function and a test), or "assumption".

## 1. What the code does today (read in code, tested)

**A re-read replaces the file's own entries.** `seed-memory --scrips` reads every file of the company again
(`seed.seed_results`), and for each quarter `dossier.merge` first calls `_forget(dossier, "xbrl:res:<scrip>:<period>")`, which takes out
every stored source with that id, then writes what today's reader gives. So a stale figure written by older code goes, whether today's
reader writes another value or none (a filler 0 that is now dropped, an EPS now left out). A figure that sits in a later file's
comparative column is replaced when that later file is re-read, which the same run does (all files back to FY21 are read).
Tests: `tests/test_known_wrong.py` (the three re-read tests below).

**The screener referee's "official" figure is today's reader.** `screener_xbrl_referee.CompanyFiles.official` reads the NSE file with
`xbrl.parse`, the same reader the seed uses (it does not apply the seed's unit-slip step, see Dolphin). So where the referee run of
27-28 Oct found "screener matches the official figure, memory does not", memory holds something an older reader wrote
(measured 28 Oct: run 40513449694, STATUS section 3). That is why those items are "re-read fixes it" and not "needs a code fix".
This is the weakest link of the plan: it holds if the referee ran with the same code as the seed will, which was the case after
PR #199 (assumption, to be confirmed by the check in section 4).

**What the reader does for each class (tests in the repo):**

| Class | What today's code writes | Test |
|---|---|---|
| EPS sign flipped (Alembic Q4FY26: profit 67.13, owners' -33.87, EPS 2.61) | the filed sign: `xbrl.owners_share` drops an owners' profit of the opposite sign, `eps_signs` leaves it | `test_todo90.py`, `test_results_card.py::test_eps_keeps_its_filed_sign...`, and here `test_a_re_read_puts_a_flipped_eps_sign_right` |
| EPS stored as 0 | the real EPS when another EPS tag holds it (`xbrl._results`, a 0 tagged first is replaced); no EPS when only the filler is there and the profit is 1 Cr or more (`eps_fillers`). A 0 beside a profit under 1 Cr stays (can be real) | `test_results_card.py::test_a_zero_eps_beside_a_profit_is_a_filler`, and here `test_a_re_read_replaces_an_eps_stored_as_zero...` |
| Unit slip put the wrong way (Dolphin Offshore, F196, merged 26 Oct) | the file's own figure: a file within 3x of a neighbouring quarter is in the company's unit and is not multiplied | `test_f196_memory_figures.py`, and here `test_a_re_read_puts_a_scale_repair_made_before_the_neighbour_rule_right` (stale 19.5 replaced by the file's 1.95) |
| The exchange's own file differs from the company's own statement | the file's figure again: nothing in one file can show it (the profit equals PBT less tax in all four files, or the EPS is a real EPS of the wrong basis) | none possible; this is why the list exists |

## 2. The list and the command (built here)

* `known_wrong.KNOWN_WRONG_FIGURES`: scrip, basis, period, metric, the wrong value, the right value when known, the evidence (file,
  PDF page, why), the date proven, the exchange. Matching is on scrip, metric, period, a basis that fits and the **value** (to 0.005).
* Honoured by: `dossier.merge` (the seed, the live run, the BSE fill's seed copy, any card), `dossier.put_standalone`, and
  `bse_gap_fill` (`new_figures` counts "known wrong figure"; `_write` skips it). `bse_gap_fill.KNOWN_WRONG` (a whole quarter, Kovai) stays.
  Not touched: `screener_fill` (a screener figure is another source, and it fills the hole with the right figure), `restated_pdf` and
  `memory_labels` (they write no results figure of the main block).
* `memory-drop-known-wrong [--scrips A,B] [--apply] [--json P]`: dry run by default; with `--apply` each changed dossier is saved through
  `backup.RunBackup` (the dossier as stored, once, and the one about to be written; read back before the write), then written through
  the three-way merge. Removes a stored source only when metric, period, basis and value are the listed ones; keeps the others and
  rebuilds the figure from them. Reads the standalone block for a STANDALONE entry. `restore --backup backup/memory-drop-known-wrong-<time>/
  [--scrips X] --apply` undoes it, keeping what was written since.
* Maintenance: `command=memory-drop-known-wrong`, input `apply` (default off = dry run), input `ids` = scrip codes (empty = every listed
  company). Group `maint-nse-memory`. Artifact `memory-drop-known-wrong` (the report as text and JSON).
* Tests: `tests/test_known_wrong.py`, 16 tests on `LocalSink` (listed entry removed and a different value kept; a figure of another
  basis or period kept; a two-source figure rebuilt; dry run writes nothing; restore undoes it and keeps a later write; a backup that does
  not read back stops the run; the seed, the standalone block and the BSE fill skip a listed figure; a drop is not undone by a re-read;
  the workflow wiring).

## 3. The 35 items

Memory is stored by scrip code; `seed-memory --scrips` takes NSE symbols or scrip codes. The symbols below are as in STATUS. A value in
brackets is read from the repo; "(unread)" means the stored value is not in any file in the repo and is read from the dossier at run time.

### 3a. The exchange's own file is wrong: 4 items, plus 3 companion lines, plus Kovai (listed, not among the 35)

| # | Company (scrip) | Basis | Period | Metric | In memory | Statement | Proof | Action |
|---|---|---|---|---|---|---|---|---|
| 1 | Eco Recycling, ECORECO (530643) | consolidated | Q4FY25 | pat | 3.42 | 2.20 | PDF 0047672d (OCR, page 15): PBT 627 lakh, tax 288+(3)+122 prior-year, PAT 220 lakh; file's TaxExpense leaves out the 1.22 Cr; screener 2.20 | list + drop |
| 1b | same | consolidated | Q4FY25 | tax_expense | 2.85 | 4.07 | same statement and file (companion line) | list + drop |
| 2 | Vadilal Enterprises, VADILENT (519152) | standalone | Q3FY25 | pat | -42.94 | -18.31 | PDF 5f92d39f: net profit -18.31, EPS -212.25, no discontinued operation; file adds -24.63 discontinued; tijori -18.31 | list + drop |
| 2b | same | standalone | Q3FY25 | pat_discontinued | -24.63 | none | same (companion line) | list + drop |
| 3 | Pradeep Metals, PRADPME (513532) | consolidated | Q4FY26 | pat | 15.83 | 10.32 | PDF e40783f6: PBT 1,307.44 lakh, tax (275.52), PAT 1,031.92; file tags tax -2.76 (sign); screener 10.32, tijori 10.319 | list + drop |
| 3b | same | consolidated | Q4FY26 | tax_expense | -2.76 | 2.76 | same (companion line) | list + drop |
| 4 | Veljan Denison, VELJAN (505232) | consolidated | Q3FY26 | eps | 10.31 | 11.24 | PDF 75b5e969 (own filing, 11 Feb 2026): consolidated EPS 11.24; 10.31 is the standalone EPS; screener 11.24, tijori 11.2378 | list + drop |

Proof is from `docs/bench/bse-fill-batches-1-2-check.md` (measured 27 Oct 2026). Two-source rule (DATA_QUALITY): the PDF and screener agree
in all four, but Eco's PDF was read by OCR, and OCR "can list or hold a figure, never correct one": so none of the four is corrected, all are
taken out. The quarter is then empty on that line until the owner's rules fill it (`screener-fill` fills an empty quarter from screener.in with
the right figure, labelled screener; not part of this plan). The three companion lines (tax, discontinued) are the same files and the same
statements: leaving them in would show a profit that does not equal its own PBT less tax. **Added beyond the four named, for the lead to keep or strike.**
Kovai Medical Q4FY26 pat 59.69 (63.35) and eps 54.55 (57.90) are also on the list (read from the existing `KNOWN_WRONG` note), so that
no writer from the same file can store them; memory is not known to hold them.

**Maintenance runs (2):**
1. `command=memory-drop-known-wrong`, `apply` off, `ids` empty. Dry run: per listed figure "would drop" / "other value kept" / "not in memory" / "no dossier".
   Expect 7 "would drop" if memory is as STATUS says and Kovai "no dossier" or "not in memory".
2. If the dry run shows what is expected: `command=memory-drop-known-wrong`, `apply` on, `ids=530643,519152,513532,505232`. Reads no filing (0 of the 50);
   writes at most 4 dossiers, each backed up first. Note the backup prefix from the log.

Not put through `seed-memory`: these four have no NSE results list (the BSE fill wrote them), so a seed would read nothing for them.
Not recomputed: the yoy/qoq the next quarter's figures carry against the dropped one (a re-read of the company does that). **Unsure:** whether
Eco's `pat_owners`, Pradeep's `ebitda` or any other figure derived from the wrong profit or tax is also stored and wrong; the evidence names none.

### 3b. 12 EPS with a flipped sign: re-read fixes it (expected), not yet proven for each

Class: today's reader writes the filed sign for the Alembic pattern (section 1); STATUS 28 Oct says the code already refuses that case yet memory holds -2.61,
so memory was written before the 26 Oct fix (PR #154, F187, whose own entry says it acts "on new reads and on re-read filings only": memory written before it stays until the filing is re-read). No stored value of the others is in the repo (unread).

| # | Company | Period | In memory (sign flipped) | Action |
|---|---|---|---|---|
| 5 | ALEMBICLTD | Q4FY26 | -2.61 (file and screener 2.61) | re-read |
| 6 | APOLLOPIPE | Q2FY26 | unread | re-read |
| 7 | PRIVISCL | Q1FY25 | unread | re-read |
| 8 | RPOWER | Q2FY25 | unread | re-read |
| 9 | SILVERTUC | Q1FY27 | unread | re-read |
| 10-14 | MOLDTECH | five periods (unread) | unread | re-read |
| 15 | NITCO | Q4FY24 | unread | re-read |
| 16 | MAXESTATES | Q2FY24 | unread | re-read |

**Unsure, and the fallback:** five periods of one company (MOLDTECH) is a pattern, not five accidents. If a re-read leaves any of the 12 flipped, it is
a code class today's reader still has, and the file is its fixture (`docs/DATA_QUALITY.md` steps 3-4): fix in `xbrl.eps_signs` with a test, re-read again. If the
file itself is wrong (the PDF prints the other sign), it goes on the list with the two-source proof and through the drop. No code fix is made here
because none can be shown offline.

### 3c. 9 EPS stored as 0: re-read fixes it (expected)

Class: a file that tags 0 EPS first and the real EPS under another tag was stored as 0 before 26 Oct (F187: 47 such pairs in the referee, fixed for new reads and re-read filings only); today's reader keeps the real one, and drops a lone
filler 0 beside a profit of 1 Cr or more. AHLUCONT Q3FY24 is the measured case (0 beside profit 70.24; screener 10.55; docs/TRACKER F187). The other eight
entries: ARVIND, BGRENERGY, PILANIINVS, SKFINDIA, HARDWYN (periods unread).

| # | Company | Period | In memory | Action |
|---|---|---|---|---|
| 17 | AHLUCONT | Q3FY24 (+ any more of its nine) | 0 (screener 10.55) | re-read |
| 18-25 | ARVIND, BGRENERGY, PILANIINVS, SKFINDIA, HARDWYN | unread (8 entries) | 0 | re-read |

**Unsure:** a real 0 EPS beside a profit under 1 Cr is kept by design (`eps_fillers`); if one of these is that, the re-read leaves it and it was not an error. AHLUCONT Q3FY24
is the oldest of the 12 quarters memory keeps (Q3FY24 to Q2FY27): borderline for the re-read window, and a quarter outside it would stay.

### 3d. DOLPHIN revenue and profit ten times too big: re-read fixes it

Class: F196 (merged 26 Oct 2026, measured: `scale_slip` returned 1 for Q2FY24 and Q4FY24 and `fix_scale` multiplied the right figures by 10). Today a file within 3x
of its neighbour quarter is not multiplied.

| # | Company (522261) | Period | In memory | The file | Action |
|---|---|---|---|---|---|
| 26 | DOLPHIN | Q2FY24 | revenue and pat 10x (about 20.5 and 35.3, derived from the file's 2.05 and 3.53; unread) | 2.05 / 3.53 | re-read |
| 27 | DOLPHIN | Q4FY24 | revenue 19.5, pat 14.6 | 1.95 / 1.46 | re-read |
| 28 | DOLPHIN | FY24 | revenue 64.7, pat 55.7 | 6.47 / 5.57 | re-read (the year comes from the Q4FY24 file) |

The Q4FY24 file is in the repo (`tests/fixtures/nse_dolphin_q4fy24_cons.xml`); the test re-reads it over stale 19.5 and stores 1.95. **Unsure:** the Q2FY24 and FY24 steps are
reasoned, not run (their files are not in the repo); and if a future file of the company looks like a slip to `scale_slip`, F200 now needs the PDF's text layer to confirm it
and otherwise holds the quarter out of memory ("a missing quarter is better than a wrong one"): the re-read would then leave a hole, not a wrong figure.

### 3e. 7 where the official filing agrees with screener, not memory: re-read fixes it (assumption)

| # | Company | Period | Metric |
|---|---|---|---|
| 29 | AURUM | FY26 | pat |
| 30 | CHEMBONDCH | FY26 | eps |
| 31 | EMUDHRA | Q4FY25 | eps |
| 32 | LAXMIDENTL | FY26 | eps |
| 33 | RELTD | Q4FY26 | revenue |
| 34 | RELTD | Q4FY26 | pat |
| 35 | TITAN | Q4FY26 | eps |

The official figure is today's reader on the file (section 1), so the file is not wrong: memory is stale or was changed after the parse. Nothing in the repo says which; the stored
values are unread. RELTD's revenue and profit together point at a unit step (the seed's `fix_scale`, which the referee does not run), the same class as Dolphin; Aurum has a
discontinued operation (F173, `one_basis`), where the whole and the continuing profit differ. These are reasons to look first, not findings. **Unsure; this is the class most likely
to turn out to need a code fix.** If a re-read leaves memory different from the official figure, find the step between `xbrl.parse` and the stored figure (`fix_scale`, `drop_long_year`,
`_derive_quarters`, `merge`) with the file, fix the class with a test, and only then, if the file itself is wrong, list it.

## 4. The runs, in order (one command at a time: the memory group keeps one waiting run)

Every run is `Maintenance` > `command`, from `main` after this change is merged. None calls an AI model.

**Step 0 (read only):** `command=memory-drop-known-wrong`, `apply` off. Read the dry run.

**Step 1 (the drop):** `command=memory-drop-known-wrong`, `apply` on, `ids=530643,519152,513532,505232`. 0 filings.

**Step 2 (the re-reads), one company a run:** `command=seed-memory`, `ids=<symbol>`, `file_cap=50`. A consolidated filer reads up to 12 recent quarters plus the March quarters
back to FY21 (about 17 files) and the same number of standalone files (`_seed_standalone`), so one company is up to about 34 files, which is under 50, two might not be. Files
already in our XBRL store are not downloaded and do not count toward the cap; older ones (the store keeps files 6 months) are. The first run prints how many files a company
read (`n XBRL files`); if a company reads 25 or fewer, pair the standalone-only ones in later runs. A run that reaches the cap stops cleanly, saves what it wrote, and
the same command is run again.

| Run | `ids` | Items |
|---|---|---|
| 1 | `ALEMBICLTD` | 5 (pilot: check it before going on) |
| 2 | `AHLUCONT` | 17 (pilot) |
| 3 | `DOLPHIN` | 26-28 |
| 4 | `APOLLOPIPE` | 6 |
| 5 | `PRIVISCL` | 7 |
| 6 | `RPOWER` | 8 |
| 7 | `SILVERTUC` | 9 |
| 8 | `MOLDTECH` | 10-14 |
| 9 | `NITCO` | 15 |
| 10 | `MAXESTATES` | 16 |
| 11 | `ARVIND` | EPS zero |
| 12 | `BGRENERGY` | EPS zero |
| 13 | `PILANIINVS` | EPS zero |
| 14 | `SKFINDIA` | EPS zero |
| 15 | `HARDWYN` | EPS zero |
| 16 | `AURUM` | 29 |
| 17 | `CHEMBONDCH` | 30 |
| 18 | `EMUDHRA` | 31 |
| 19 | `LAXMIDENTL` | 32 |
| 20 | `RELTD` | 33-34 |
| 21 | `TITAN` | 35 |

Each run backs up its company's dossier first (`seed-memory --scrips` takes the dossiers before it starts and the after-state when it ends); `restore` with `backup=<prefix from the log>`,
`scrips=<scrip>`, `restore_mode=preview` then `apply` undoes it. The after-state includes any live write made to that company while the seed ran, so undo soon after.

**Check after each pilot (runs 1-3), then once at the end.** The figure must be the right one, and the rule of STATUS section 0 A needs two sources agreeing on it: the second source is
screener.in (the referee's pairs already hold its figures). Read the company's page, or run `screener-crosscheck` and `screener-referee` again after the last run: the 21 pairs of
"screener matches the official figure" and the Dolphin pairs must be gone. Any item still wrong goes back to section 3 as "needs a code fix" (or the list, with proof) and its company
is re-read again after the fix. A re-read can also change figures beyond the 35 of that company (older figures written by older code, and quarters now held out for an unconfirmed unit
slip, F200): the counts are in each run's log and the backup holds the difference. **Put the list of changes on STATUS after each batch.**

## 5. What was not done, and what is open

* Nothing was run, pushed or dispatched. No R2, no stored dossier and no GitHub workflow was touched, so every "memory holds X" for items 5-35 is from STATUS or the docs, not from the dossier.
* No code fix for items 5-35 was made, because none could be shown to be needed offline. Classes 3b, 3c and 3d are covered by tests that show today's reader writing the right figure
  over a stale one; 3e has no such test.
* A read-only way to show one company's stored figures for the 35 (a `show` beside the drop) would make the checks above exact; not built (the dry run shows only the list).
* The drop does not recompute yoy/qoq on neighbouring figures and does not write the right figure.
