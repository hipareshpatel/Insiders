# Commonest false holds, step 2 (22 Oct 2026, night)

This note covers step 2 of the owner's plan: fix the commonest false holds. Each fix that makes a check accept more gets three tests:
- a before-and-after over the stored cards;
- a test with random fake figures;
- an independent blind sample.

**The data.** The held-card audit (`docs/audit/held-audit-2026-10-22.md`) read 236 cards against their PDFs. Joining its reasons to each card's stored "not found" list gives 292 figures:
- 233 are false holds: the figure is in the filing.
- 57 are true holds.

The false holds by cause:

| Cause | Figures |
|---|---|
| Computed (sum, difference or ratio of filing figures) | 111 |
| Reformatted | 47 |
| In another unit | 29 |
| OCR | 23 |
| Other causes | 23 |

**The harness.** Scripts are in the session scratch folder, not in the repo. It runs `grounding.check_card` on each card against its PDF text layer, plus the card's memory context and scale block. The live check also sees XBRL, memory and OCR text, so the offline check is stricter than the live one (962 "not found" against 292 stored). It measures the change a fix makes, not the live rate.

## Fix 1: amounts in other groupings (F99)

The fix reads five forms of amount that the number pattern read wrongly or not at all:

| Form | Example | Read as |
|---|---|---|
| Rupees in any grouping after ₹/Rs/INR, even where the document declares lakh | "INR 2,993,59,08,147.6", "Rs. 92,00,00,000/-" | whole rupees |
| "N lakh crore" | "2 lakh crore" | N × 100,000 crore |
| A stray space after a comma, only when a comma group or decimals follow | "Rs.1, 27,000" | one number |
| A space as the separator, decimals required | "2 642.81", "3 83 509.48" | one number |
| A card figure of ₹1,000 Cr or more that the filing prints rounded to the crore | ₹10,737.58 Cr printed as 10,738 | a match |

| Measure | Result |
|---|---|
| Before and after over the 292 stored figures | 21 false holds freed (Adani Power, Shakti Pumps, Max Financial, eMudhra, Indian Bank, Hero, Ahluwalia, ICICI Bank, Adani Ports); 0 true holds freed; 0 newly held |
| 1,673 fakes at the same precision, on the same filings, as a crore figure | accepted: 70 before, 71 after |
| the same fakes as a bare figure | accepted: 128 before, 129 after |
| Independent blind sample of 70 new readings, checked against the PDFs | 68 right; 2 wrong, both OCR misreads in one scan's text layer (the join was right, but the characters it joined were misread) |

**Rejected on the way.** The first version took rounding from ₹100 Cr. It let 13 fakes through in a single annual report, matched against page numbers and note numbers. The first spaced pattern was also too loose: it read "Regulations 30, 33, 51" as one number and read "3 83 509.48" from its middle. Both were tightened before the measurements above were taken.

## Next: computed figures (111)

Most computed figures are a sum or difference of two to four figures printed close together, such as two guarantees, two borrowing lines or a limit raised from X to Y. F93 found that accepting any sum of two filing figures lets 56% of fakes through. So this check will accept only figures close to the point's own quote in the filing, and it gets the same three measurements before it ships.
