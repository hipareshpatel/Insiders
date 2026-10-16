# Card audit, 2026-10-16

Every card from both smoke tests (177 cards, 10 companies) was checked figure by figure against
its own filing text, one reviewer per company. Per-card findings (field, what the card says,
what the PDF says, class) are in `card-audit-2026-10-16.json`.

**Result:** 95 WRONG, 56 MINOR, 26 OK. Issues by class: invented 147, arithmetic 89, unit
scale 88, other 88, wrong period 64, signal verdict 55, wrong column 43, event type 34,
direction 29, standalone/consolidated mixed 12.

## What was fixed in code (commits 0e270f4 → 422f87e)

| Class | Fix |
|---|---|
| Unit scale (lakh/million read as crore) | XBRL results figures from BSE's results archive; unit slips corrected in code (single declared unit, or a figure's own unit); scale and margin-fit checks; second opinion for any unmatched amount |
| Wrong column (QoQ called YoY; previous quarter as current) | key numbers for revenue/EBITDA/PBT/PAT/EPS set from XBRL with exact YoY; YoY/QoQ from the year-ago and previous quarters' XBRL files; a "% YoY" that is the QoQ change is flagged |
| PBT or segment result called EBITDA | XBRL EBITDA (PBT + finance cost + depreciation − other income) replaces it on the card |
| Direction / arithmetic in comparisons | a notable change's % is recomputed from its two figures |
| Signal verdicts | KPI verdicts checked against target and quarter; no "met/missed" on "not disclosed", "assumed" or another item's news; concerns labelled as concerns; reduction targets compare downwards; off-scale targets dropped; dilution only for share issues; no other-income warning for lenders; overdue guidance flagged once |
| Event type | rules: results statements → RESULTS; open offer → M&A; promoter Reg 29 gift → governance; tax demand/penalty → litigation |
| Same results filed several times | D20: one card per company per results quarter, later documents linked |

## Still open (not fixable by a rule; prompt work or second opinion)

- **Invented facts** (the largest class): purposes of fundraises, "fixed-price" contracts,
  milestones and dates not in the filing, wrong names. Needs a stricter prompt ("only what the
  filing states") and claim checks.
- **Arithmetic in prose** ("85% + 26% = 111%", interest of ₹49 Cr on ₹50 Cr at 14%).
- **Standalone and consolidated mixed** in one comparison.
- **Wrong row of a table** (one segment's figure given to another).
- **OCR loses brackets**, so a negative "(5,25,552)" became positive (CSB cash flow).
- **Market cap** in signals from a stale price (₹4,983 Cr vs ₹7,339 Cr in the presentation).
- **Memory copies errors forward**: a wrong figure stored once is quoted by later cards; the
  rebuild clears it, the scale/fit checks now stop most at the source.
