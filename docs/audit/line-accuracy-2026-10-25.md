# Line accuracy against the card WRONG rate (TODO 17, 25 Oct 2026)

## In plain English
1. A card carries a median of 13 lines (headline, takeaway, bullets, numbers). Results and call cards carry 17 to 19.
2. Measured 25 Oct: about 2.7% of lines are wrong, 95% interval 2.0-3.6% (3.8%, 3.0-4.8%, if faults outside the line count are included).
3. To keep cards at 95% right with 13 lines, each line must be wrong at most 0.39% of the time. We are about 7 to 10 times above that.
4. Faults clump: a WRONG card has 2.5 wrong points, not 1.6 as chance would give. One root error (a 10x slip, a wrong basis) repeats in several lines. So the simple model says 31-40% of cards would be WRONG; we see 21% (14-29%). Counting each root cause once, the working rate is 1.7% a line (1.1-2.5%).
5. At that working rate a card can carry about 3 lines (2 to 4.5) and stay at 5% WRONG. More lines do cost: cards above the median length are WRONG 29% of the time, those at or below 16% (30 of 105 against 16 of 103). The fix is fewer root causes (code checks), not fewer lines alone.

## Method
No AI calls. Line counts come from each card's stored JSON, read once from the public read-only API
(`/api/cards/<id>`, 0.4 s apart) and saved in `docs/audit/line-accuracy-2026-10-25/card_lines.json`. Reviewer verdicts come from
the audits already in `docs/audit/live/`. Everything is reproduced by `python -I scripts/daily_audit/line_rates.py`
(`--fetch` refreshes the line counts); its printed output of this run is `docs/audit/line-accuracy-2026-10-25/output.txt`.
It reuses `wilson` from `rates.py`; the test is `pipeline/tests/test_line_rates.py`.

What counts as a line: headline, takeaway, each item of what happened, key numbers, notable changes, quantified impact,
why it matters, missing disclosures, call takeaways and track-next lists (the "text lines"). Results-table rows (1.9 a card)
are counted apart and are not in n. Facts part = headline + what happened + key numbers + notable changes + quantified impact;
interpretation part = takeaway + why it matters + missing disclosures + call takeaways + track next.

Implied card WRONG rate = mean over cards of 1-(1-p)^n, with each card's own n.

## Data used
| Source | Cards | What it records |
|---|---|---|
| `live/2026-10-23-audit.json`, `2026-10-24-audit.json` | 121 with card JSON (128 audited; 7 gone or repeated) | verdict plus `wrong_points`, the faults found. 25 WRONG, 50 MINOR, 46 RIGHT. |
| `live/2026-10-21-audit.json`, `2026-10-22-audit.json` | about 80 more with card JSON (90 audited) | verdict only, no point list: used for the lines-per-card distribution and the WRONG-by-length split, not for p |
| `live/critic-review-2026-10-22.json`, `hourly-0713-review.json` | 30 | a reviewer graded every line (OK, WRONG_FIGURE, INVENTED, OVERSTATED, UNSUPPORTED_CAUSE): 266 lines |
| `trace-2026-10-25/trace_group*.json` | 48 WRONG cards of 21-24 Oct | 96 wrong points, about 2.0 a WRONG card (same clumping, not re-counted here) |

229 cards have line counts; 10 audited cards no longer have card JSON.

## Results
**Lines per card** (229 cards): mean 14.3, median 13, quartiles 9.5-18, range 5-37. Facts part 6.9, interpretation part 7.4.
By event type (cards, median): CONCALL_PRESENTATION 51, 19; RESULTS 41, 17; DEBT_RATINGS 9, 16; OTHER 26, 13;
ORDER_WIN 20, 12; CAPEX 13, 12; CORPORATE_ACTION 10, 12; FUNDRAISE 9, 12; LITIGATION_REGULATORY 17, 9; M_AND_A 17, 8.
The "about 25 lines" in the TODO row is the top of the range (the longest results and call cards reach 30-37), not the median.

**Per-line fault rate p** (daily audits 23-24 Oct, 121 cards, 1,670 lines; Wilson 95%):
| Definition | Faults | p |
|---|---|---|
| Wrong points on WRONG cards | 63 | 3.77% (2.96-4.80%) |
| ... only those in the counted lines | 45 | 2.69% (2.02-3.59%) |
| Every listed point, WRONG and MINOR cards | 132 | 7.90% (6.70-9.30%) |
| Reviewer graded every line, hard faults (wrong figure, invented) | 10 of 266 | 3.76% (2.05-6.78%) |
| Same, soft faults (overstated, unsupported cause) | 7 of 266 | 2.63% (1.28-5.33%) |

Two independent datasets agree on a hard-fault rate of 3-4% a line.

**Where the wrong points sit** (63 on WRONG cards): results-table and YoY/QoQ lines 16, signals/blocks (deal value, scale,
rating, memory) 12, unlabelled body sentences 9, headline 5, call takeaways 3, takeaway 3, event type / tone 3, whole card
(duplicate, noise) 3, quantified impact 2, what happened 2, why it matters 2, key numbers 1, track next 1, notable changes 1.
18 points lie outside the text lines (blocks, event type, whole card), and 4 WRONG cards have only such faults, so a line
count alone misses them. Facts against interpretation by label: facts (headline, what happened, key numbers, table) 24,
labelled interpretation (takeaway, why it matters) 5; most unlabelled body sentences are figure lines.
By card error class: wrong_column 4, duplicate 3, event_type 3, arithmetic 3, restated 2, standalone_consolidated 2,
unit_scale 2, attribution 2, memory 2, other 1, noise 1. In the fully graded set the non-OK lines fall mostly on
interpretation: why it matters 6 of 43, takeaway 3 of 30, track next 2 of 6, against what happened 0 of 85 and key numbers 0 of 54.
The two datasets disagree on which part fails: the daily audits, with the 10x/period/basis slips, put it on figures; the
graded set (drawn from cards where the writer was the weak point) puts it on interpretation. Read this as "both parts".

**Implied against observed card WRONG rate** (121 cards):
| Model | Implied card WRONG |
|---|---|
| p = 3.77% (all points on WRONG cards) | 39.9% (33.0-47.4%) |
| p = 2.69% (counted lines only) | 30.6% (24.1-38.4%) |
| p = 7.90% (every listed fault) | 64.6% (58.8-70.3%) |
| **Observed** | **20.7% (14.4-28.7%)**; 22.1% (17.0-28.2%) over all four days |

They do not agree: independent lines overshoot. Faults cluster. A WRONG card has 2.52 wrong points where independence
gives 1.59, and 21 WRONG cards have two or more where independence gives 12 (of all 121 cards). Typical cluster: HDFC Bank's
10x unit slip sat in the headline, what happened and the quote. The per-line rate that reproduces the observed card rate is
**1.70% (1.14-2.49%)**; that is the "root cause per line" rate.

**What is needed.** For 95% right cards (independent lines): fault rate at most 0.39% at the median 13 lines (99.61% right),
0.36% at the mean 14.3, about 0.30% for a RESULTS card at its median 17. The TODO's "99.8% at about 25 lines" is right for 25 lines.
**What a card can carry.** At the calibrated 1.70%, 3.0 lines (2.0-4.5); at the raw 3.77%, 1.3 lines. Today's cards carry 13.
Reaching 95% at 13 lines needs the root-cause rate down about 4x (1.7% to 0.39%), or the same faults caught before publish.

**Length does matter, in the data.** Cards at or below the median (13 text lines): 16 of 103 WRONG (16%); above it 30 of 105 (29%),
all four days, 208 cards.

## Caveats
- **Reviewers recorded faults, not every line checked.** For the 23-24 Oct audits a line not listed is assumed right.
  A reviewer who skims will undercount lines wrong, so p is a floor. Only the 30 graded cards have every line graded, and they
  were a critic-scoring sample, not a random draw.
- **Cards changed since review.** Line counts are from today's stored card; some cards were healed or refreshed after review
  (the trace found several), so n can differ slightly from what the reviewer saw. 10 audited cards are gone.
- **Whole-card faults are not lines**: duplicate card, noise card, wrong event type. They drag the card WRONG rate with no line fault.
- **Point lists are free text.** Mapping a point to a part uses its leading label (headline:, why_it_matters ...); 9 body sentences
  carry no label and are counted as body lines, and the facts-against-interpretation split is approximate.
- **MINOR cards' points** may be minor faults; the 7.90% row mixes severities and is an upper bound on "wrong lines".
- **Sample size**: 25 WRONG cards in 121; intervals on the card rate are +/-7 points. Two days only; the 21-22 Oct audits have no point lists.
- **Results rows** (1.9 a card) are outside n; counting them lifts n from 13 to about 15 and tightens the need slightly (0.34%).
- Independence is false (clustering shown above), so 1-(1-p)^n is a guide, not a forecast; the cut in root causes per card is what moves the rate.
- The "Reviewer wrong: 0" trace result (25 Oct) supports using the reviewers' faults as true faults.
