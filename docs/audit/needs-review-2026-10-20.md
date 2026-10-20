# Needs review, every card read by hand (2026-10-20)

The owner asked: "can you finish 'Needs review · 100 ...' all this by manually reviewing each one by yourself ... this
will help you to identify mistakes we are doing and why those goes for review".

**What was read.** All 239 cards: the 223 held cards of the live export (`docs/audit/live/held-2026-10-20.json`) and the
16 published with the Unverified mark. Each card was checked against its filing's text (the cached text, or the PDF).
The laptop session read 0-119. One independent agent read 120-238, with no sight of the first half's verdicts. Each
verdict, class and note is in `needs-review-2026-10-20/verdicts.json`.

## Result

| Verdict | All | Held | Unverified | Laptop (120) | Agent (119) |
|---|---|---|---|---|---|
| RIGHT | **152 (64%)** | 140 | 12 | 73 | 79 |
| MINOR | 52 (22%) | 51 | 1 | 29 | 23 |
| WRONG | 29 (12%) | 27 | 2 | 16 | 13 |
| UNSURE (source unreadable) | 6 | 5 | 1 | 2 | 4 |

The two halves agree within a few points. **Most holds are false: 140 of the 223 held cards are right**, and 51 more
have only a minor fault. The hold still does its job on the WRONG cards: 27 of the 29 were held, and only 2 reached the
feed. Those two are Clean Max (an AGM said to have 54 resolutions when it had 56) and Kanoria Chemicals (a standalone
impairment blamed for the consolidated loss).

## Why cards are held (grouped classes, 239 cards)

| Class | Cards | Right / minor / wrong / unsure |
|---|---|---|
| false: quote reworded, or a table row reflowed | 76 | 63 / 13 / 0 / 0 |
| false: figure in another unit (lakh, million, rupees, bn) | 38 | 31 / 7 / 0 / 0 |
| false: derived or computed figure (sums, ratios, EBITDA) | 38 | 28 / 10 / 0 / 0 |
| false: other (garbled-text warning, claim checker, a time read as a figure) | 17 | 12 / 4 / 0 / 1 |
| false: figure from memory or another row or period | 12 | 9 / 1 / 0 / 2 |
| false: sanity check on a loss or a one-off gain | 8 | 7 / 0 / 0 / 1 |
| false: YoY or margin check overrules the filing's own words | 2 | 2 / 0 / 0 / 0 |
| true: invented or unsourced figure or claim | 14 | 0 / 5 / 9 / 0 |
| true: wrong period, row or column | 8 | 0 / 3 / 5 / 0 |
| true: arithmetic, count or formula | 6 | 0 / 3 / 3 / 0 |
| true: unit scale (10x / 100x) | 5 | 0 / 1 / 4 / 0 |
| true: standalone and consolidated mixed | 5 | 0 / 2 / 3 / 0 |
| true: XBRL tag (owners' profit) | 3 | 0 / 0 / 3 / 0 |
| true: a memory comparison wrong | 3 | 0 / 2 / 1 / 0 |
| true: direction; the model's working left in; source unreadable | 4 | |

**Re-checked on today's code:** a figure converted from lakh or million is accepted at the declared unit, and so is a
rupee amount written out in full. "Rs. 1,165,179,600" passes as ₹116.52 Cr and is still refused as ₹1,165 Cr. Several of
the "unit" reasons were set by older code. Others come from the model's choice of quote: Goodyear's inventories quote the
cash-flow change line, not the balance sheet. The largest false-hold class is a reworded quote. Loosening it means taking
a figure from another sentence, and that was measured at 20% wrong (F92); taking a sum of two filing figures matches
random fakes 56% of the time (F93). Neither is done.

## The 29 WRONG cards

| Company | Card | Class | What is wrong |
|---|---|---|---|
| Jubilant Pharmova | `139e9236` | cause not in filing | Headline credits Q3 PAT to the SOFIE gain; the merger closed in Q1 |
| Heritage Foods | `d7ea9e10` | unit scale | ₹2,568.36 million (₹256.8 Cr) given as ₹2,568 Cr |
| Ahluwalia | `f6495f61` | XBRL filler | "net profit to shareholders ₹0 Cr" (fixed in F88; needs a re-run) |
| eMudhra | `106139d0` | cause not in filing | ICRA A (Stable) "upgraded from" A (Stable): no move; "follows the Cryptas acquisition" invented |
| SML Mahindra | `21089634` | cause not in filing | "post-acquisition business disruption" not in the filing |
| eMudhra | `acf426c3` | mixed sources | 1,910.6 mn given as ₹188.01 Cr; EBITDA 44.14 vs 41.09 on one card |
| Jubilant Pharmova | `360aa7a9` | direction | "14.6% is above the 16.3% H1FY26 level" |
| Adani Ports ×2 | `nse-106605493`, `-518` | XBRL tag | The company's file tags its owners' share of OCI, ₹1,238.67 Cr, as owners' profit; the statement prints 3,328.96 |
| Titan | `nse-106614413` | not in filing | Revenue ₹26,920 Cr; the statement's revenue from operations is 17,730 + 6,204 = ₹23,934 Cr |
| Kanoria Chemicals | `0758a110` | wrong period | Revenue "-29.4% from ₹431.42 Cr": 30,439 vs 21,388 lakh is +42% |
| SML Mahindra | `e7977858` | arithmetic | "4.2x FY26 revenue": 12,500 / 2,838 = 4.4x |
| NTPC | `6593e84a` | not in filing | A one-page cover letter; the card states revenue and PAT |
| LIC | `nse-106717498` | unit scale | GST demand INR 99,09,87,896 (₹99.1 Cr) given as ₹9.91 Cr |
| Kanoria Chemicals | `506bd3d1` | not in filing | Headline PAT ₹113.2 Cr; the filing and its own key number give ₹32.39 Cr |
| Anlon Healthcare | `nse-106733412` | unit scale | Rs. 1,165,179,600 (₹116.5 Cr) given as ₹1,165 Cr |
| SKF India | `a6245351` | memory | Pre-demerger memory figures where the deck gives continuing operations |
| NTPC | `ae4f7998` | wrong row | Four superannuations reported as three |
| Adani Power | `f10912ae` | wrong column | The FY22-26 CAGR column read as YoY |
| SML Mahindra ×2 | `e8652975`, `ebc54c08` | invented | Monthly sales totals and cargo/passenger splits the filing does not have |
| Magellanic Cloud | `4526e618` | not in filing | Consolidated revenue ₹714.2 Cr; the filing gives 69,787.64 lakh |
| HDFC Life | `64e7ea0c` | wrong row | ₹2,422.97 Cr penalty given as the total demand |
| Clean Max | `nse-106797207` | arithmetic | Five series add to ₹2,500 Cr; card says ₹2,065 Cr |
| RBL Bank | `nse-106806515` | unit scale | Deposits Rs. bn 1,562.8 given as ₹15,628 Cr; CASA "improved" when it fell |
| RBL Bank | `nse-106814520` | wrong period | H1 provisions used as Q2, so "provisions fell" when they rose |
| Persistent | `nse-106818661` | standalone | Standalone PAT shown; consolidated PAT fell 27% QoQ |
| Clean Max | `nse-106714378` | count | 54 resolutions; the AGM had 56 (published) |
| Kanoria Chemicals | `85751073` | standalone | Standalone impairment blamed for the consolidated loss (published) |

## Fixed in code (F94), each measured on stored cards

1. **An owners' profit its own file does not add up to is dropped** (`xbrl.owners_share`). Adani Ports' Q4FY26 file
   tags ₹1,238.67 Cr to owners and ₹179.14 Cr to minorities, against a profit of ₹3,308.30 Cr. The two shares add up to
   its other comprehensive income (1,417.81) instead. The card now falls back to the group's profit. Profit less that
   minority would be no truer, since the statement prints 3,328.96. A 0 minority is a filler and decides nothing.
   - Measured on 45 real consolidated files from stored cards: 8 dropped. Adani Ports' 2 periods are mistags. 6 are
     0/0 fillers, which the card already dropped (F88).
   - A −₹25.87 Cr owners' figure beside a 0 minority is kept.
2. **A YoY or QoQ change the filing itself writes with that label is never flagged** (`period_mixups`). Bandhan Bank's
   release says "representing a growth of 5.9% YoY", and the card was held because the tagged QoQ change was also near
   5.9.
3. **A loss beyond revenue is not a unit slip** (`grounding.scale_issues`). The rule now applies to a profit only. A loss
   read at the wrong unit is still caught by the 5× jump against the company's own quarters. Every stored flag of a
   loss above revenue was checked: SPARC, Supreme Infra and McNally. None was a unit slip (2 right, 1 unreadable but
   plausible).
4. **A sentence that shows the model's working goes back for a rewrite** (`working_text`). The example is SBI Life:
   "above Q4FY26's ₹805 Cr? No, below; it is the second-highest". It matches that one sentence in 1,263 stored cards.
5. **A sentence with a figure taken out goes back for a rewrite** (`_BLANK`). Examples: "holds ** ** stake", "passed
   with over votes in favour", "moved to 11.06% from in Q1FY26", "₹150 Cr NCD issuance, of net worth".
   - It matches 28 sentences on 18 stored cards, all of them real blanks, mostly governance.
   - They come from the second opinion, which is told to "remove a figure that matches no source". That instruction now
     says to rewrite the sentence so no blank is left.
6. **Two regexes that could never match.** A heredoc had written their `\b` as a backspace byte.
   - `event_xbrl._SHORTER`'s "of the listed entity".
   - `governance_xbrl._RUPEES`'s "mn": "Rs. 0.30 mn" was read as 0.30 rupees.
   - Tests for both.

Tests: 720 pass.

## Found, not changed (for the owner or the cloud)

- **Two cards for one results quarter, both held.** This happened at Bajaj Finance, Bajaj Finserv, Adani Ports,
  Novartis, Home First, Star Health and Bandhan: a board outcome plus a press release or "outcome without statements"
  10-20 minutes later. D20 lets a later document make the card when the first card is held (F58: 17 of 43 quarters
  had their only card held). When both are released, the quarter has two cards. This belongs with the owner's decision on
  held cards (PLAN B3): the later card should replace the held one, not sit beside it.
- **EBITDA and EBITDA margin on lenders and insurers.** Bajaj Finance and Bajaj Finserv show an "EBITDA margin 69.7%"
  that says nothing for a financial company. These were marked MINOR.
- **Quantified impacts whose formula does not give the stated figure** hold the card (3 MINOR). Dropping the impact and
  keeping the card, as is done for a memory insight naming the wrong period, would release them.
- **Memory comparing a quarter with itself** ("flat versus Q1FY27's own ₹502 Cr reported earlier") on a concall card
  that follows the same quarter's results card. Seen twice (Bandhan).

## Re-runs to release cards

Cards are released through the pipeline, never by setting a flag. The cards these fixes touch, for a re-run once F94 is
on main:
- Adani Ports `nse-106605493` and `nse-106605518`.
- Bandhan `a161327d-ef2c-4ed8-a17d-fc78dc92f13a`.
- SPARC `bc434117-982f-4af4-90fe-5a2249ab65ff`, Supreme Infra `nse-106745684` and `nse-106747091`, McNally
  `nse-106740331`.
- SBI Life `399697e7-fc7e-43ac-b7f9-97077db4dac1`.
- Ahluwalia `f6495f61-f9a4-43a0-9ac7-d1faf5fd6ca1`.

Re-running the other 140 right but held cards gives each one a new answer, but nothing in today's code is sure to
release them. The commonest reason is the model's choice of quote. Whether to spend the free quota on them is the owner's
call (PLAN B3).
