# Annual reports with their own XBRL (F57, to-do item 4), 2026-10-18

NSE's annual-report XBRL (docs/SOURCES.md, `annual_xbrl.py`) is now read and put in front of an
ANNUAL_REPORT filing's text: the statements in crore on a named basis, the other basis's headline figures,
contingent liabilities, related parties party by party, KMP pay, loss-making group entities, the auditor,
the opinion by its basis-for-opinion heading, emphasis of matter and three CARO clauses. Code: c567fe0.

## The run

All 31 ANNUAL_REPORT filings of the ten smoke-test companies, reset with `scripts/rerun.py` and processed
with `laptop.ps1 process --news-ids` (Heritage FY25 at 09:47, the other 30 at 09:48-10:03; 0 failed). Round
3e (the parent session, 09:18) had re-run the 12 held ones too, but its process made no annual-reports-xbrl
call (none in the raw store, no warning logged): those 12 measured the quote-check change of 8f59bd3 alone.

| | round 3d | round 3e | this run |
|---|---|---|---|
| published | 10 | 11 | 9 |
| held | 12 | 9 | 12 |
| duplicate | 8 | 9 | 9 |
| not material | 1 | 2 | 1 |

| | with the table (10) | without (21) |
|---|---|---|
| round 3d | 4 published, 6 held | 6 published, 6 held, 8 duplicate, 1 not material |
| this run | **5 published, 5 held** | 4 published, 7 held, 9 duplicate, 1 not material |

The table reached the 10 filings that were not duplicates and whose year NSE lists (copies of the same report
are merged before the table is fetched). It was rightly refused once: Ahluwalia's separate AGM notice
(e6630a4e) prints no statements, so the FY25 file's figures were not in its text. The 21 without it are filings for years NSE
has no file for yet (FY26 for five companies, filed after the reports), Novartis and CSB Bank (no files),
SML's FY25 and the duplicates; their changes are run-to-run variance plus 8f59bd3.

Released by the table: Shivam FY25, eMudhra FY25 and Heritage FY26, all held in 3d for crore figures whose
quote, from a lakh or million statement, could not carry them. On the five held cards with the table, 29 of the
36 key numbers and notable changes quote a table line; 27 of those pass, and the two that do not are the two
table classes fixed below.

## Still held with the table, and why

| Card | Held for | Class |
|---|---|---|
| Kanoria FY25 (5fc5) | borrowings "₹506.72 Cr (FY24)": the FY24 total, which no line printed | **table: fixed**, the borrowings line carries the prior year |
| Jubilant FY25 (1e3f) | contingent liabilities ₹368.40 Cr quoting the by-class line; the total was on its own line | **table: fixed**, total and classes share one line (classes' sum stated when no total is tagged) |
| Ahluwalia FY25 (1c4e) | a ratio (1.4x net worth) in a key number; notable changes quoting lakh rows of the PDF | quote contract, not the table |
| Prism FY26 (4f33) | a fact about the RQBE divestment whose quote and figures are not in the filing | invented wording, not the table |
| SML FY26 (b87f) | a why-it-matters quoting a related-party cap sentence that is not found | quote contract, not the table |

The two fixed classes need their filings re-run (5fc5, 1e3f) when the run slot is free.

## Point in time

The XBRL comes weeks to months after the PDF (Kanoria FY25 3.5 months, eMudhra 2.5, Heritage 6 weeks), so
this measures the backfill. On the daily path a report is read the day it is filed and will usually find no
file yet; it is read from its PDF as before. Re-reading an annual report once its XBRL appears is not built.
