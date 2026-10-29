# The out-of-sample test of the PDF readers, 30 Oct 2026

The owner's decisions and the batch rules are in `docs/bench/READER_HANDOVER.md` section 4a.

**The run.** Maintenance `pdf-oos` run 40933340958 (seed 29, `file_cap` = 100) kept 100 PDFs from 60 filings of 58 companies.
None of these companies is in either hand key.

**The key.** 500 figures: revenue, total income, PBT and PAT, on both bases, for Q1FY27, Q2FY27 and H1FY27. Each figure is
the exchange's XBRL value that memory holds. The groups run in plan order, ten filings each, so there are 6 groups.

The first key's values were rounded to 6 significant digits (`xbrl_key._cell` used `{:g}`, fixed in b399de0). The exact values
came from a second read-only run, xbrl-key 40947529080, on the same companies. 21 values changed, and no other value
differed. `key-seed29.csv` is the exact key.

**The score.** Options on. Reported as right / wrong / no answer for the numbers-first reader; the native reader is in the
text files.

| | First read (`first-read-2026-10-30.txt`) | After the two fixes (`after-fix-2026-10-30.txt`) |
|---|---|---|
| groups 1-3: the fixes were designed on these | 94 / 4 / 146 of 244 | 117 / 5 / 122 |
| groups 4-6: never opened while fixing | 111 / 5 / 140 of 256 | **126 / 6 / 124** |
| all | 205 / 9 / 286 of 500 (41%) | 243 / 11 / 246 (49%) |

The native reader got 78 / 3 / 419 on both reads.

GitHub's own scoring in the same run, scored against the exact key, matches the local first read figure for figure, with the
options both on and off. Numbers-first gives 205 / 9 / 286 either way. The native reader gives 78 / 3 / 419 with the options
on and 60 / 2 / 438 with them off.

**The two fixes.** Each has a named cause seen in at least 2 filings of groups 1-3, a test that fails without it, a blind
review and four frozen bench re-scores with 0 new wrong answers.

- 1cefbed, the half year: the H1FY27 column is read, but only when the table's two quarters add up to it. Seen in 5PAISA,
  ADOR, CYIENT and MAHLOG.
- 24f5e52, side-by-side bases: a page that prints its two bases next to each other, with headings such as "Consolidated
  results   Standalone results", is split into one table per basis. Seen in CYIENT and HITECHGEAR.

**Every wrong answer, sorted by hand on its page.** None of the 11 is a misreading:

- **Definition, 10.** These are the consolidated PBT of YUKEN, M&M, GRASIM, MAHLOG (Q2 and H1), ERIS, UNOMINDA, DABUR and
  MRPL (Q2 and H1). The exchange's PBT tag holds the profit before the share of associates or joint ventures (some
  companies also exclude exceptional items). The reader gave the printed "Profit before tax", which includes them.
  - MRPL's consolidated tag equals its standalone PBT.
- **File, 1.** RATEGAIN's standalone PAT is printed as 42.09 million (4.209 crore); the XBRL figure is 4.22 crore.

**No answer.** In groups 1-3, 52 of the 244 figures pair with a PDF that is not a results statement: AGM proceedings, postal
ballot results, a Reg 30 disclosure or an intimation letter (AFCONS, SWANCORP, KSL, POLYPLEX, RMDRIP, INDOTECH, SREEL and
ASIANTILES). No reader can answer them. Groups 4-6 have not been sorted this way yet.

The other misses in groups 1-3 have causes seen in only one filing each, so under the rules they are not fixed yet:

- KSHINTL: "June 30,2026" dates;
- AHLUCONT: a rotated page with the heading "Quarter Endod";
- KRN: a garbled scan;
- IPCALAB, IGPL, UNITECH, GVPTECH: rows not named by arithmetic.
