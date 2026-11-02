# memory-owners-drop, 2 Nov 2026

**Dry run (run 41382561379):** over 1,902 companies it found 91 owners'-profit rows whose only sources are labelled unknown and that the same period's file profit contradicts.

| Class | Rows | Examples |
|---|---|---|
| Filler 0 beside a real profit | ~60 | SCHAEFFLER, SKIPPER, 5PAISA, INDIAMART, AIIL, SUNTECK |
| Total comprehensive income or another line taken as owners' profit | | ADANIPORTS 1,238.67 vs 3,308.30; BALKRISIND FY25 1,843.09 vs 1,654.96 |
| Wrong sign | | CEATLTD H1FY27 -37 vs 116; JYOTISTRUC; SIS FY25 |

**Lead's read before apply.** Dropping an owners' row only ever falls back to the file's own whole profit, which is the safe direction. The one known cost is a company whose minority share is real but has no file tag. OIL 9MFY26 owners 4,250 vs whole 5,126 may be right, given NRL's minority share; it now shows the whole profit.

**Applied (run 41383888060):**
- 91 rows dropped across 39 dossiers.
- Backup `backup/memory-owners-drop-20261102T033542Z/`.
- Checked on the live site: ADANIPORTS no longer holds the 1,238.67 owners' row.
- results-table rebuilt after it.
