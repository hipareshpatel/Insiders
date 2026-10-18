# Re-run of the held cards and the card-less results quarters (2026-10-18)

The funnel (`funnel-2026-10-18.md`) found the two largest losses of right cards in the checks: 118 of 451
cards held, and 19 of 43 D20 results quarters with no published card. The fixes from the audit of every
discard path (`discard-paths.md`) were then measured on the same filings: the 118 held cards, the 25 D20
duplicates and their owners, and the documents of the 19 quarters - 145 filings, re-run 06:10-07:19 with the
code of 2db6562 (`process --news-ids`, `--bulk`). Comparison script and its output: session scratchpad
`rerun_held/compare.py`.

## Held and published, against the funnel

| | funnel (before) | after the re-run |
|---|---|---|
| cards | 451 | 432 |
| held | 118 (26%) | 51 (12%) |
| published | 333 | 381 (+48) |

The 118 held cards: **45 now published**, 43 still held, 29 now duplicates, 1 not material.
The 19 results quarters with no published card: **10 now have one**. Of the 9 left, 8 have every document
held or an exact copy of a held one (Jubilant Q3FY25, Q3FY26, Q4FY26; Prism Q3FY26; Heritage Q3FY26; eMudhra
Q3FY26; Kanoria Q3FY26; Shivam Q4FY26) and 1 was lost to a wrong D20 claim (Ahluwalia Q3FY25, below).

## Duplicates the re-run made, and the ones that were wrong

27 of the 29 new duplicates were the same event again (a concall deck after its results, a buyer's and a
seller's SAST disclosure of one gift, an NCD approval filed twice). Six were not, and each cost a right card:

| filing | made a duplicate of | why it was wrong | fix |
|---|---|---|---|
| Ahluwalia Q3FY25 statement (435f98de) | the notice of the meeting that would consider it (4dc9a267) | the notice, typed RESULTS, took the quarter from "for the quarter ended 31st December, 2024" in its text; its deck (60a25438) then chained onto it | only XBRL, a statement of results or a page of figures claims a quarter (`results_quarter`); BSE's own wording for such notices under the bare "Board Meeting" subcategory goes to the date rule (4fb04c0) |
| Prism Johnson's RQBE rights subscription (1964621d) | its limestone-block bid ten days earlier | the repeat check before pass 2 saw only BSE's boilerplate headline | the repeat check reads the opening of the document and compares amounts, periods, parties and stage (4fb04c0) |
| Shivam's ₹1.73 Cr GST notice for FY22 (c083410d) | its ₹2.64 Cr notice for FY20 | same | same |
| Heritage's completed Get-A-Way acquisition (6441e456, 377f0ebe) | the SPA signing, then that duplicate | a completion is a later stage; the second was a duplicate of a duplicate whose memory entry had not been taken out (code before 2a11133) | same; the forget hook (2a11133) |

## What still holds a card

Of the 51 held: 92 issue lines of the quote contract ("Give each fact the filing's own sentence as its
quote"), 12 numbers not found, 5 figures that do not fit their unit or column, 2 headline figures, 2
quantified impacts. Two classes were plain bugs and are fixed:

- a written date read as an amount: "Order received on 16.12.2025" held as stating 16.12 (6a2433d);
- a quantity printed like a year: SML's April-August cargo sales of 2052 units were set aside as a year, so
  "2,052" on the card was "not in the filing" (40d0aff).

The rest are mostly a fact naming a comparison figure that sits elsewhere: last quarter's revenue from memory
(SML's "fell 34.4% QoQ from ₹845.89 Cr"), the company's revenue or market cap from the scale block, or the
price one sentence away (SML's ₹650). The run used code from before `stated_precisely` (48cb51c) and the forget
hook (2a11133), so these were re-run again with today's code (round 3d, below) before deciding on more.

## The released cards, against their filings

10 of the 45 released cards read against the filing text:

| card | verdict | note |
|---|---|---|
| 26915066 Heritage Q1FY26 | OK | EPS ₹4.37 and every figure from the statement |
| 76f3b6ed Heritage Q2FY26 | OK | ₹9.36 Cr exceptional = ₹61.54 mn GST refund + ₹32.02 mn reversal |
| 1ee7b071 Jubilant Q2FY26 | OK | key numbers from XBRL |
| d3e97826 Prism grinding capacity | OK | |
| c913f4c4 Kanoria ₹50 Cr NCRPS | OK | |
| 2f11c2e1 Jubilant solar stake | OK | one fact repeated |
| 0763d247 SML open offer result | minor | an open offer does not "raise" money for the company |
| ec3c9d0d Ahluwalia ₹888.38 Cr order | minor | the site is Punauradham, Sitamarhi (Bihar), not Ayodhya |
| e4d8f81b SML change of control | wrong insight | a memory insight says the 58.96% was bought at the ₹1,554.60 open-offer price (₹1,327 Cr); the SPA price was ₹650 and the filing gives neither |
| 9634c075 SML August volumes | wrong insight | a memory insight calls 842 units July's sales; 842 is August's, from the company's other August report |

The facts were right on all ten. Both wrong points are memory insights, which are checked for their figures
but not for what the figures belong to: every number in them exists in memory, attached to another month or
another leg of the deal. Now checked for the period: a memory insight whose figure memory holds under
another period (and not under the one named, nor printed in the filing) is dropped and the card kept
(`misdated_memory_insights`). A first, looser version caught 10 over the 343 cards with memory insights and 9
were right (a figure the filing itself reports, a range of percentages, a ratio, "a year ago", a 3.98% margin
for ₹3.98 Cr); the version kept reads only memory's metric series, at the figure's unit, and drops 3, all wrong:
SML's July, and two Shivam cards calling March 2025's net worth September's. e4d8f81b's error (a price from
another leg of the deal) is not a period and stays open.

## Annual reports (F57)

The audit had found 12 annual reports taken by the "AGM notice" date rule. They now have an `ANNUAL_REPORT`
type; `retriage --scrips` moved the 12 from the noise files to the queue (10 annual reports filed with their
AGM notice and 2 AGM filings whose subject names the report; the two shareholder letters stayed noise), and
`scripts/rerun.py` now routes a reset filing by today's rules, so the 19 annual reports pass 1 had typed
RESULTS or not material are read on the new route.

## Round 3d (running)

86 filings with today's code: the 51 still held, the 6 wrong duplicates and the 31 annual-report filings.
Results to follow here.
