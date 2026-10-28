# How screener builds each row: evidence, 28 Oct 2026

Input to the row-by-row design (owner, 28 Oct 2026: "make our statements as like screener, all line items row by row and
all their rules ... screener has the same source as we do"). One fixed recipe per screener row, the same for every company
(a lender / insurer set by template only), checked against the owner's screener Excel files (Data Sheet) for the top 10, then
run unchanged on the other 40 of the fifty as the hold-out. Measured on local XBRL files (results and annual-report) against
the Excel files in the session's scratchpad; nothing below is in code yet except where a commit is named.

## Rows with a recipe the evidence supports

| Row | Recipe | Evidence |
|---|---|---|
| Sales | RevenueFromOperations - excise (an element, or the OtherExpenses breakdown row "Excise duty") | ITC FY26 89,913.33 - 11,044.93 = 78,868.40; BPCL, Reliance quarters |
| Interest | FinanceCosts + the row "Finance cost of financial services business and finance lease activity" (moved out of Expenses) | L&T FY26 2,848.82 + 6,995.34 = 9,844.16 (Excel 10,055.94: 211.78 left, no single fact); the row is only in the Q4 integrated file's 12-month context (commit 9b84064 on `screener-rules`) |
| Other Income (quarter) | OtherIncome + ExceptionalItemsBeforeTax (+ share of associates for some companies) | Airtel FY25 quarters 1,573.7 + 7,286.8 + 3,703.0 = 12,563.5 |
| Other Income (year, Data Sheet) | a plug: PBT + Depreciation + Interest - Operating Profit | so a gap here is a gap in the expense mapping, not in Other Income |
| Loss on disposal of PPE (year) | out of Expenses, netted in Other Income (a gain added) | Reliance FY26 116 and FY25 154, Maruti FY26 73.9 and FY25 67.3, ITC FY26 -11.84 (2,523.0 vs Excel 2,523.09): both lines to the crore. Counter-case ONGC (103.35, Operating Profit matches without it): unsettled |
| PBT (non-lender) | ProfitBeforeTax as filed, exceptional included | |
| Net Profit | web page: the whole profit; Data Sheet: the owners' share | Airtel FY26 Data Sheet 26,695.2 = owners' share; HDFC Bank Q2/Q4 files carry the owners' share with minority 0 |
| Borrowings | Borrowings + lease liabilities, current and non-current | Infosys FY26 6,016 + 3,160 = 9,176; Airtel FY26 121,671.4 + 73,740.6 = 195,412 |
| Net Block | PPE + goodwill + other intangibles (+ investment property, right-of-use, intangibles under development when separate), all from one file (the results file) | Airtel FY26 224,390.3 + 56,685.9 + 125,260.4 = 406,336.6; Infosys FY26 33,770; TCS FY26 31,343 (the annual report's intangibles 176 would not match) |
| EPS (year) | restated on today's share count (splits and bonuses after the year end) | Bajaj Finance FY25 268.94 / 10 = 26.89 (Excel 26.77); Reliance FY23 98.59 / 2 = 49.29 (commit 97b7f40). Not shown on pages (owner rule: no EPS) |
| Cash from Investing | Investing + the foreign-exchange effect | earlier study |

## Rows that are not one recipe yet

- **Reliance annual Sales**: XBRL 1,075,675 - 18,640 = 1,057,035 against the Excel's 1,055,780 (FY26, 1,255 apart; FY25 1,822). No
  element, row or sum equals the gap; quarterly Sales match. Assumption: the year column comes from the annual report's own statement.
- **Airtel annual Other Income / Operating Profit**: FY26 the Q4 exceptional (-3,160.7) sits in Expenses in the year column
  (annual Operating Profit 116,513.8 against the quarters' 119,674.5, exactly 3,160.7 apart); FY25 the other way (8,099.0). No
  element found for either.
- **PBT of lenders**: HDFC Bank, six of six quarters, screener's PBT is before exceptional items; SBI Q2FY26, Kotak Q4FY26 and Bajaj
  Finance Q3FY26 keep them inside. Banks are not uniform on this row.
- **LIC**: PBT and Tax % in two regimes (Q4FY25, Q4FY26: PBT = net profit + tax; Q1FY26 not); Sales and Expenses differ from the
  file's Income and Expenses by amounts no element matches.
- **Associates in Other Income**: ITC and Bajaj Finance yes, L&T and Sun Pharma no.
- **Bank fixed assets**: ICICI FY25 +8,460, FY26 +10,550; SBI FY26 +2,620; the local bank files carry one FixedAssets element.
- **Borrowings** of Reliance FY25 (+26,783), Bajaj Finance and L&T Q4FY26 (+3,814): the files are not local.

## Not wrong quarters

The three wrong_quarter pairs of the 10-company check are coincidences of the 0.1% shift tolerance on steady figures: Reliance
Q3FY25 revenue is memory's gross figure (screener's is less excise), and HDFC Bank's Q4FY26 / Q2FY27 PAT is the owners' share
against screener's whole profit.

## Branch `screener-rules` (not merged)

9b84064 and 97b7f40 are rules (kept). b90b3d6 (loss on disposal), 527fb7b (lender PBT before exceptional) and 6546d4b (second
set of balance-sheet parts) are "tried only when the gap is not closed" alternatives: dropped for the fixed-recipe design, their
evidence is above. 7e30240 (the lease-row reader) is a read fix that makes more rows found: it needs the on/off comparison first.
