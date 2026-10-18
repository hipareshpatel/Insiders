# Are the cards useful as ranked? Signals, scores and Top Signals (2026-10-18)

Data: the D1 database, read-only. 431 to 433 published cards (held = 0) for the ten smoke-test companies; the pipeline was still writing while I read. Card IDs below are the first 8 characters of news_id.

## 0. The ranking the site uses does not show anything
- `/signals` and `snapshot_signals.sql` list only cards with `is_actionable_signal = 1`, ordered by `actionability_score DESC, filed_at DESC`. **No card has `is_actionable_signal = 1`, and no card is HIGH.** The highest score is 65, and a Top Signal needs 70 (`scoring.py`: `HIGH = 70`). So Top Signals is empty, and so is the "High impact" filter. The feed itself is sorted by date only.
- The model rated 56 cards HIGH. Code rescored all of them to MODERATE (42) or LOW (14). The impact pill shows the code's score; the model's rating appears only as "the analyst rated it…".
- **Why nothing reaches 70.** Without a stated amount or a margin inflection, the pillars add up to 28 to 53 points: magnitude 3, 10 or 18 from the model's call, margin 5, balance sheet 12, credibility 8, disclosure 0 to 10. In practice scores fall between 20 and 65.
- **Many published cards were built by older code.** 316 of 433 were created between 16 Oct 17:34 and 20:xx and never rebuilt. Ten DISTRESS lines still use the old wording that round 1 fixed: "Interest cover -1.2x … barely covers interest" (697d0fbb), and 0.7x or 0.8x read as "barely covers". Seven open-offer cards still say "raise = 68–71% of net worth" (b6d88ea1, 2ce7bff0, 9f7c54c7 and others), which the `_scale` guard now removes.

## 1. The 30 cards the ranking would put first (score order)
**20 of the 30 earn their place; 10 do not.** 12 of the 30 carry at least one signal that contradicts the card's own figures.

Cards that do not deserve their place:
- 277aec74 (score 65, #1): a daily tender count for Novartis's open offer.
- 5c033038: the Detailed Public Statement for that offer.
- b6d88ea1: "No shares tendered on day one".
- 5ad562bc: the offer closed with 40 shares.
- 04823247: the same SPA filed on the same day as d9d631a2.
- 0763d247 and 710cd936: SML open-offer process filings.
- fea8da6c (#2): Kanoria's postal ballot on a ₹5,445 Cr related-party-transaction ceiling between two of its subsidiaries.
- 10236fc6: a CAD 94.5m capex that its own takeaway says is "small for a company this size".
- a71e129f: Prism's enabling resolution.

**11 of the 30 are about two changes of control** (Novartis and SML). The Ahluwalia ₹2,089 Cr DLF order (51% of FY25 revenue) comes in at #28, below four Novartis open-offer filings.

How the ranking goes wrong:
- **Size taken from the model's own figures** (`scoring.py` L157–159). Any VERIFIED ₹ crore result in quantified_impact is divided by trailing revenue. 60 cards get their size points this way. Examples: "Offer value at the offer price" counted as 156% of revenue (277aec74), "Annualised revenue run-rate" as 114% (ebcc1569, which is revenue compared with itself), and an "aspirational FY27 target" as 138% (b7f60ddb). Others are the value of M&M's stake (e4d8f81b, 0763d247) and a "LAS runoff" figure (785a6677).
- **A fixed 20 points for brownfield** (L200). Any capex at an existing site gets 20 margin points, whatever its size (10236fc6, b7ce5a9b).
- **The target company scored as if it were the buyer** (`signals._scale` L367, 382–386). On ACQUISITION deals the company is often the target, yet the card says "₹1,446 Cr deal = 187% of net worth" (d9d631a2), and the same appears on 0ecbac14 and 53ddad8f. The guard covers only `kind == FUNDRAISE`.

Signals in the top 30 that contradict the card's own numbers:
- **MARGIN_MIX** "gross margin −3118 bps, fixed-cost +3239 bps" (f6495f61, b7f60ddb). 16 cards have component moves of 1,000 bps or more. `quality.py` M16 compares quarters whose cost lines were filed differently.
- **METRIC_SHIFT** "GNPA down 72767 bps … to 1.75%" (785a6677): a ₹ crore figure was compared with a percentage (`_change`). On ebcc1569 the signal says "EBITDA up 34% YoY" while the card says 28.1%.
- **CAPITAL_COMPOUNDER** "+38.2 Cr on −4976.4 Cr of capital added. Growth funded from internal accruals" (259fc33b). Net worth is about ₹573 Cr, so a balance-sheet unit slip is likely. Negative capital added is labelled POSITIVE (`quality.roiic`, L344). It appears alongside DISTRESS on 371cb9bc and bb1f7ecb.
- **WATCH_RESOLVED** "Concern met: 'Will margins take a hit…?'" (POSITIVE) on management reassurance alone (b7f60ddb). `signals._promises` maps MET to POSITIVE for CONCERN items, but the prompt never says what "met" means for a concern.
- **DILUTION** on non-convertible preference shares: "1.1% more shares; issue price 552% above last close" (f02fe231, and on 3 other Kanoria cards). `_NOT_AN_ISSUE` lacks NCRPS, NCD and debentures. Shivam's NCDs read "417710x book value" (8a997b8b).
- **Card text against its own signals:** c34ba4fe says the deal is "28% of net worth, 3.4x sales", while its signal and QI say 153% and 5.47x. 64a8b148 says "~13% of FY25 revenue" against a signal of 51%.

## 2. Distribution and calibration (433 cards)
| Event | n | LOW/MOD | mean score |
|---|---|---|---|
| M_AND_A | 72 | 33/39 | 40.0 |
| LITIGATION_REGULATORY | 68 | 56/12 | 34.2 |
| RESULTS | 61 | 36/25 | 34.8 |
| MONTHLY_BUSINESS_UPDATE | 40 | 24/16 | 38.1 |
| CONCALL_PRESENTATION | 38 | 20/18 | 35.6 |
| FUNDRAISE | 25 | 14/11 | 34.8 |
| ORDER_WIN, CAPEX | 10, 8 | 5/5, 4/4 | 40.0, 40.9 |

What is miscalibrated:
- **Procedural filings outrank results.** M&A process filings score higher than results; the top GOVERNANCE card (65) is a vote.
- **Bad news is pushed down.** The score mixes how bullish a filing is with how important it is: penalties lower the score, and only good news can earn pillar points. A USFDA Warning Letter (ee510e46) scores 45, and distress results cards score LOW.
- **The price gate is usually missing.** Historical filings carry no ret_1m, so the price gate passes on only 114 cards.

## 3. A random 30 of the rest (seed 7): signal verdicts
21 of the 30 carry signals. **6 have a signal that is wrong, 7 one that is misleading, and 8 are fine.**
- **c46de2fa:** a DILUTION WARNING on a subsidiary's preference shares, priced against Jubilant's share price, although Jubilant holds them. Its SCALE line uses "FY30 revenue ₹13,500 Cr", which is a target (`_latest_revenue` accepts future periods).
- **2d2c0b9f:** "PAT up 1180% to 805 Cr (9MFY26)". These are eMudhra's figures in ₹ million stored as crore.
- **0fd4cf53:** "Volumes down 41% vs JUL-2025". The filing itself prints −15% (842 against 990), so memory's July figure is wrong, and a PREDICTION "missed" verdict is built on it.
- **cfd08e37:** "Approval met" for a fund-raise approval, with evidence about the divestment.
- **b7fdbed5:** GUIDANCE_BREACH on rating-agency (Ind-Ra) expectations, flagged "deadline passed" in April 2026.
- **53ddad8f:** "68% of net worth" on an open offer.

Patterns across all cards:
- **METRIC_SHIFT is mostly noise.** 132 of its 322 lines are deferred tax, inventory change, current tax or exceptional items; 130 are moves of 300% or more; 75 refer to a period other than the card's own (an FY25 tax line on a Q1FY26 card). Year-to-date ranges are read as months: "Volumes up 413% vs JUL-2026 (APR-AUG-2026)" on b070501e. Some lines are duplicated ("PAT continuing up 9891%", cfe58901). All of this comes from `_metric_shifts` and `_period_kind`, which defaults to "M".
- **"KPI check met" (POSITIVE) often means only that the figure was disclosed.** Examples: 9 SML monthly-volume items, the CSB items feb1cb22 and 69fcd7b6, and eMudhra 1e84b557. Some contradict their own evidence: "Net worth turning positive: met … negative ₹40.68 Cr" (599c85e9), and gross debt up 2.4x counted as met (145bb59e). `kpi_verdict` checks only items that carry a numeric target.
- **SCALE reads a "raise" where no cash arrives:** enabling resolutions, rating assignments (0ccca397), refinancing loans (443a9dd1), and negative-net-worth percentages ("−295% of net worth", cc47851f).

## Fix order
1. Rebuild the 316 cards made with old code.
2. Use only deal_value amounts for size, not quantified_impact.
3. Separate a target company's M&A from the company's own spending in `_scale`, and tie the score to that.
4. In METRIC_SHIFT, use only headline metrics of the card's own period and unit, and treat ranges as their own period kind.
5. Make MET a verdict about the target, not about disclosure, and define it for CONCERN items.
6. Exclude non-convertible instruments from DILUTION, and future periods from the revenue denominator.
7. Recalibrate so that a material event can reach 70, whether it is good or bad news.
