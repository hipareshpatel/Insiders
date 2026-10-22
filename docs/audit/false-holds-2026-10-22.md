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

## Fix 2: a sum of the point's own quote (F100)

A card figure is grounded when it is the sum of 2 to 4 figures in its own point's quote, or the difference of 2 of them. The quote checks find that quote in the filing.
- **Units:** each part is read at its own unit. A bare part takes the unit the quote declares before it, otherwise the filing's unit.
- **Margins:** a change in points or basis points is grounded when it is the difference of two of the quote's percentages.
- **Repeats:** a figure grounded this way also stands where the card repeats it, for example in the headline.

| Measure | Result |
|---|---|
| Before and after over the 292 stored figures | 17 false holds freed (Repco, Prism, Kernex ×4, M&M Finance ×7, NLC, Novartis, Swiggy, Britannia); 0 true holds freed; 0 newly held |
| 3,632 fakes, each placed on a point that carries the real quote | 0 newly accepted |
| Independent blind sample: every figure the rule grounds on the 236 cards (127) | 125 right; 2 wrong, neither let through by the sum (both are printed in their quotes and wrong for another reason: a standalone figure compared with a consolidated one, and a wrong column); 1 right only by coincidence (Heritage 41% = 39 + 2, which the filing also states) |

The first version without units freed one true hold. Zydus's ₹38.65 mn + ₹90.18 mn is ₹12.88 Cr, which the card wrote as ₹128.83 Cr, a 10× slip. Reading each part at its own unit keeps it held, and a test guards this.

## Fix 3: three check mistakes from the review queue (F101)

**Quantified impact.** A share stated as a percentage, where the formula gives the fraction, now passes. Examples: Novartis 0.513 against 51.3%, DLF −0.71%, and Kilitch's 40.4%, which the owner sent from the queue. Among the stored mismatches, every exact 100× gap with unit PCT was a false hold (4). A 10× gap stays a mismatch, because half of those are real (HDFC Life, Transrail).

**Footing.** PAT may include a discontinued business's result. CIE's 243.69 is 242.66 plus 1.03, which the owner also sent. XBRL `ProfitLossFromDiscontinuedOperationsAfterTax` is now read as `pat_discontinued`.

**Fit.** A PBT or PAT above revenue, or above 5× the company's recent quarters, now passes when the same period's exceptional items, other income, associates' share or a tax credit account for it. EBITDA gets no such allowance (Hester's EBITDA with its exceptional gain inside was a true hold). A margin may also be on total income (Adani Power's 43%, GMR's 25%).

Before and after over the 132 results cards, with metrics rebuilt from each card's results block, the fit change freed:
- Kiri;
- Jaykay (2 cards);
- DLF;
- Hester;
- Tata Teleservices;
- Swan;
- Tata Chemicals.

Every one of these is a reviewer-confirmed false hold. Prism Johnson drops 1 of its 2 holds, and that card has no individual audit reason. No true hold changed.

## Fix 4: garbled text on XBRL-backed cards (F102), 23 Oct, small hours

**Tried and rejected: reading OCR letters as digits.** The idea was to read O/o as 0, l/I as 1, S as 5 and B as 8 inside number-like tokens, with a leading l or I read both as the rupee sign and as 1. It looked good on the first two tests and failed the third.

| Measure | Result |
|---|---|
| Before and after over the 292 stored figures | 8 false holds freed; 1 true hold freed (NTPC 5.97, whose card is wrong in its meaning) |
| Fakes test | 0 newly accepted |
| Independent blind sample of 70 readings, checked against the rendered pages | 16 right, 21 harmless (labels, registration numbers), 33 wrong |

Of the 33 wrong readings, 21 are outright errors, for example:
- a leading t that was really a 1;
- "o/o" for % and the degree sign;
- a leading digit that the text layer split off as a separate word;
- a letter that stood for a different digit than the mapping assumed;
- sideways pages read upside down.

Where the reviewer could check a letter swap, it gave the wrong digit as often as the right one. The fakes test missed this because random fakes rarely land on these readings, while real card figures sit right next to them. The code was removed before merge.

The OCR-garbled class stays held. Its fix belongs upstream: OCR the page itself (D29) rather than repair the text layer.

**Garbled text on XBRL-backed cards.** A card whose figures come from its own XBRL file, with every amount grounded, is no longer held because the PDF's text layer is garbled.
- Stored holds: 15 such cards, every one false according to the reviewers. 13 cards are right or minor.
- 2 cards are wrong for other reasons:
  - CSB's headline gives the wrong quarter's NIM.
  - DB Corp shows owners' profit that is really total comprehensive income; that is fixed below.

## Mistakes in our own code (F103)

- **Owners' profit above the whole profit, with no minority figure in the file, is dropped.** DB Corp tags its total comprehensive income of ₹63.98 Cr as owners' profit, beside a ₹62.19 Cr profit.
- **No EBITDA for lenders and insurers.** On the NBFC, banking and insurance templates, EBITDA and its margin are no longer built.
  - IRFC's Q4FY26 file gave an "EBITDA" of ₹7,218 Cr at a 98.4% margin. Bajaj Finance and Bajaj Finserv file on the NBFC template too.
- **A face value is not a deal price.** Shares "of Rs. 5 each" no longer make a deal of shares × ₹5. Torrent's JB Pharma merger had become a "₹20.96 Cr deal".
