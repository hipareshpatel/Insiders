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

## Check A: a comparative against the filings' stated change (rejected)
The first sample was 12 lines over 3 days: 9 WRONG, 3 RIGHT. That was too few to judge. The check was then judged on all
1,986 stored tables against pass marks set first (`PASS_MARKS.md`). It removed 90 distinct comparatives
(`onoff_stated_full.json`).

**Blind review** (`onoff_stated_full_review.json`):
- WRONG 59, RIGHT 26, UNSURE 5: 66% WRONG, 95% CI 55-75%. The mark was 80%.
- 29% of removals dropped a right figure, against a limit of 20%.
- Counting EBITDA on our own definition as WRONG: 77% (67-84%), still a fail.

So the check is not shipped.

**What the reviews show instead: the results table's own defects.** The table sets one line against another:
- profit before associates against profit after (Union Bank, PNB, Canara, ICICI Bank);
- standalone against consolidated (PNB, Federal Bank);
- gross income against net (RBL);
- EBITDA computed without other income, against companies that print it with other income (Lumax, Bansal Wire,
  Solara, MHRIL, Manaksia, Juniper).

These are fixes at source, not a filter after the fact.

## Check B: words against the card's own figures (rejected)
On the first sample (218 audited cards) it flagged only 3, too few to judge. Judged on all 5,344 stored cards against
pass marks set first (`PASS_MARKS.md`): 88 sentences flagged (`consistency_all.json`). Blind review against the PDFs
(`consistency_review.json`) found 8 WRONG and 80 RIGHT, a precision of 9% against a mark of 85%, so the check is not
shipped.

The 69 direction flags where the sentence was right are a lead, not yet a finding. In each, the code-built results
table disagreed with a correct sentence. Either the table was wrong, or the two covered different periods or bases.
