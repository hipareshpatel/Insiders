# PLAN 1h: facts the quote check dropped, checked against their filings

Read-only. Source: 45 dropped facts on 37 cards (`grounding.quotes_dropped`, D1 `cards`, 583 cards), plus the 15 most recent log-only drops (`backfill-companies-20261018-1024.log`, `process-20261018-0918.log`). That makes 60 of the 105 available (60 more appear only in older logs). Each fact was searched in every page of its cached text, its OCR pages and its XBRL file, allowing for lakh, million and rupee units and Indian digit grouping.

**Limit:** only the first 60 characters of a dropped fact are recorded (`fact.text[:60]`). The full fact and its quote are discarded, so each fact was judged from that prefix plus the rest of the card.

## Counts (60)

| Verdict | n | Items |
|---|---|---|
| TRUE (wrongly dropped) | **50** | 36 from cards, 14 from logs |
| INVENTED (rightly dropped) | **4** | 6e962d61, daee44c8, f6495f61 (order book), 33717cd4 |
| PARTLY | **3** | f6495f61 (revenue), b96d5057, 106139d0 |
| Cannot settle | **3** | e87824b7, 4f339729, 46662556 |

Only 4 to 7 of the 60 drops removed a wrong fact, so about 83% of drops lost a right one. Four TRUE facts (8482ffe1 ×1, 7884fa38, d77c229e, f5f42d0a) came back on the published card because the second opinion re-quoted them. The rest are gone.

## The main cause: no figure to fall back on

`check_quotes` keeps a fact whose quote is missing only when all of its figures are in the filing. It counts only `plain`/`qty` figures above 31. Percentages, multiples, dates, ratings and amounts of ₹31 Cr or less are skipped. A fact without such a figure is therefore dropped as soon as its quote fails to match. That covers all 50 TRUE facts:
- ~34 have no qualifying figure at all: ratings, dates, appointments, deal terms.
- 12 carry only percentages or multiples, e.g. 86.21% post-sale stake (ae81308e), 96.86% votes (2dc389b3), GNPA 1.96% vs 1.58% (9c550b5c), 2.12x net debt/EBITDA (a1eee381), 97.08% (17762e34, printed 97.0846).
- 4 carry only small rupee amounts: ₹6.98 Cr GST and ₹2.72 Cr penalty (055a7fef); ₹5.22 Cr = "522 Lakhs" (9531fc86); ₹22.05 Cr other income, which is in the XBRL (5ea83de7); ₹23.50 dividend (058736cc).

## Why the quote missed (the 50 TRUE facts)

| Reason | n | Examples |
|---|---|---|
| Quote put together from cells of a Reg 30 annexure table, or a slide or chart | 18 | 8552d896 ("25-01-2025" + "will file the appeal"), ae81308e ("To be entered" / "By April 2025"), e1ca78a1 (coupon 12.85%), bf70fbaa (ISIN listed 03.10.2022), f09cf3e8 |
| Paraphrase, abbreviation or date format | 12 | 6a86f5e1 ("JBIRSPL"), 04823247, 72b7c4c1, 0fd5286f, 8811eec0 ("April 2, 2025" vs "2nd April, 2025") |
| Damaged text layer of a scan | 6 | f4a2a9d3 ×2 ("10rt Augus! 2026", "13m Augus!"), 95bb1b99 ("April 1. 2025."), af518a6a ("CrisilAl+"), 6333b7c2, 9531fc86 |
| Word broken at a line end | 5 | c6b7260b ("Long- \| term"), 3b3f7bfb ("Non- \| PartiCipating"), f5f42d0a ("E- \| waybill"), 433788bc ("step \| down"), 309b4a7c |
| Two-column page read across | 3 | 797bf4b0, 3f9fef6a, 1225fc63 |
| Ligature glyphs in the PDF text | 2 | 24a95dd4 ("quick-seƫng"), d4cbdf9f ("EﬀecƟve") |
| Derived figure (XBRL or a computed margin) | 2 | 7884fa38 (31.11% vs 25.97% = 31.11 − 5.14 pp from the XBRL), 5ea83de7 |
| Sentence runs across a page break | 1 | cbd78d5c ("growth of 9.3% in \| --- Page --- \| turnover") |
| Not known (all visible figures are in the filing) | 1 | e4f66b93 |

## Rightly dropped or partly wrong

- **6e962d61** (eMudhra): "EBITDA ₹432.10 Cr from ₹231.50 Cr". These are segment results in INR million, so the true value is ₹43.2 Cr, and 231.50 is one segment's figure.
- **daee44c8** (Heritage): "Feed loss ₹4.77 Cr Q3FY25". The (4.77) is renewable energy, in million, for Q3FY24.
- **f6495f61** (Ahluwalia): "order book ₹7,794 Cr" is printed nowhere in the filing. A second fact from the same filing is PARTLY: revenue 121,583.63 lakh is written as ₹1,215 Cr (cut off rather than rounded to 1,216), and its EBITDA is computed, not printed.
- **33717cd4** (CSB Q1FY27): "NIM 3.86% vs 3.75%" is in neither the PDF nor the XBRL. 3.86% is the Q3FY26 NIM.
- **b96d5057**: the ratings are right, but the filing never says "affirmed". **106139d0**: the date is right, but "Rating Committee" is not in the filing.

## Cannot settle

- **e87824b7**: a ₹2.50 dividend. Pages 13–15 are scans, blank in the cache and never OCR'd.
- **4f339729**: what is visible is true. The claim the fact goes on to make is cut off.
- **46662556**: Form C value ₹13,76,88,87,281. The scanned Form C pages gave only about 230 characters of OCR.

## Recurring fixes the evidence points to

1. When the quote fails, check percentages, multiples, dates, rating symbols and amounts up to ₹31 Cr with the existing unit-aware grounding (`grounded(kind=...)`), or send the fact to the second opinion instead of dropping it. This would cover all 50 losses. The 4 INVENTED facts would still fail: two have a wrong figure or unit, one has an unprinted order book, one a NIM from another quarter.
2. Normalise before matching: join "word- \| word" across lines, map ligature glyphs (Ɵ→ti, ƫ→tti, ﬀ→ff, ﬁ→fi), and remove page separators.
3. Store the full dropped fact and its quote on the card. 60 characters were not enough to settle 3 of these 60.
