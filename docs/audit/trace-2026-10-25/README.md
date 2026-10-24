# Wrong-card trace and the two checks it led to (25 Oct 2026)

## The trace
All 48 WRONG cards of the 21-24 Oct daily audits were traced: 96 wrong points. Three independent agents did the work,
each with the PDF's text layer (OCR was not run). Their files are `trace_group*.json`.

Where each error entered:

| Stage | Points |
|---|---|
| Our code (results table, XBRL comparatives, units, duplicates, memory facts) | 40 |
| Writer (the figure was in the text; the words were wrong) | 36 |
| Input: ambiguous 8, wrong at source 2, unreadable 2 | 12 |
| Memory from an earlier filing | 7 |
| Reviewer wrong | 0 |

**A second reading of the same input.** It would have caught 1 point clearly and 18 partly; 77 it would not have
caught. Most of the "partly" points need a different source, such as the filing's printed comparative against XBRL,
rather than a second reader. Several cards had already changed since review, and some errors were fixed by later
code (Sagility's INR/USD unit, 22 Oct), so the trace overstates what is still open.

## Check A: a comparative against the filings' stated change (`dossier.contradicted`)
A results-table comparative is removed when its change disagrees with every change the quarter's own filings state
for that line. The threshold is more than 1 point and more than 10% of the stated change. The check is not applied
across a loss or to basis-point lines.

**On/off result.** Over 153 stored RESULTS and call tables from 22-25 Oct (`onoff_stated.json`), the check removed
comparatives in 11 tables, 12 distinct lines.

**Blind review against the PDFs** (`onoff_stated_review.json`): 9 WRONG, 3 RIGHT.
- WRONG (9):
  - PNB: profit before associates set against profit after associates.
  - Geojit: the pre-restatement year-ago figure, which flipped the sign of the change.
  - Dr Reddy's ×4: comparatives taken from scanned pages.
  - STL: the wrong quarter.
  - Indorama: a different EBITDA definition.
- RIGHT (3):
  - Godrej Properties ×2: the "stated" +38% was another measure, so two correct comparatives were lost.
  - CIE: the comparative was right but the current figure was not, so its +7.1% was wrong anyway.

The mover line (employee cost) goes with a removed year-ago revenue, because it is scaled by that revenue.

## Check B: words against the card's own figures (`consistency.py`)
The check looks for four kinds of conflict:
- a turn to profit or loss that the PAT row does not show;
- a direction ("rises", "falls") against every comparison the words could mean;
- a direction word between two figures the sentence states;
- a "doubled", "tripled" or "halved" the YoY change does not bear out.

A faulted point is dropped. A faulted headline sends the card to review.

**Results:**
- On the 218 audited cards (`consistency_audited.json`), it flags 3: 2 WRONG (Sapphire, TruAlt) and 1 MINOR.
- On the 240 newest live cards (`consistency_live.json`), it flags 2.
- The yield is small: most writer errors are semantic (a role, a cause, a target), which no pattern rule catches.
