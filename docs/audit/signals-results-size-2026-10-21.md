# Signals: results sized by their own change (2026-10-21)

Owner, 21 Oct: "Signals page is empty most days, why?" Measured live that day: 216 cards in 7 days, 34 high impact, 2 signals;
4 signals in 90 days.

## Why the page was empty
1. The R2 snapshot the page reads held 3 days of signals for a 7-day page (fixed in hipareshpatel/Insiders#44).
2. Of the 34 high-impact cards, 32 scored under 70: "high impact" is set by event rules, a signal needs 70 points.
3. Gate 1 (size) measured only a deal amount against revenue or market cap. A results card has none, so Gate 1 never
   opened on results (31 of the 34 failed it) and the size pillar fell back to the analyst's call (at most 18 points):
   strong quarters stopped at 62-67 (Bajaj Consumer revenue +26% margin +671 bps: 67; LMW +38%: 65; IGI +31%: 62).

## The rule (`scoring._results_size`, RESULTS cards only)
Size = PAT growth YoY when revenue grew 15% or more, the year-ago PAT was a profit, and PAT did not fall more than 30% from
the quarter before. The size pillar takes `_band(PAT %)` when higher than the analyst's call; Gate 1 opens at 25%.
Call and presentation cards are not sized this way (the same quarter would count twice).

## On/off over stored cards (`pipeline/scripts/signals_onoff/results_size.py`, no AI)
| Version | Published results cards | Gate 1 opens | Signals gained | Lost |
|---|---|---|---|---|
| v1: PAT growth on revenue >= 15%, or a loss turned to profit | 310 | 73 | 26 | 0 |
| v2 (shipped): no turnaround, no size after a QoQ fall > 30% | 315 | 60 | 20 | 0 |

## Independent blind review of v1's 26 (two agents, PDFs only; `signals-results-size/signals_review_{1,2}.json`)
- Figures: 25 of 26 claims match the filing within 3 points; 1 miss is NGL Fine-Chem PAT +2,398% against +2,381% in the filing
  (a depressed base).
- Signal-worthy: 19 of 26. The 7 that were not:
  - 4 turnarounds, each the year-ago one-off reversing: PNB Gilts bond mark-to-market, Ganesh Benzoplast exceptional charge,
    SIS goodwill impairment, IndusInd one-off losses. The 5th turnaround, Orient Bell, was a true one.
  - 1 sharp fall from the last quarter: Eimco Elecon, profit −49% QoQ.
  - 2 acquisition-driven: JTL Industries, Sejal Glass ("not comparable", note 5).
- v2 drops the 4 turnarounds and Eimco, and loses one good card (Orient Bell): **18 of its 20 are signal-worthy (90%)**.
  The 2 acquisition cases stay; nothing on the card says so today.
- Open: a growth from an acquisition (the filing's "not comparable" note, standalone against consolidated) and
  PAT % from tiny bases (SML Mahindra +3,209%, a ₹0.53 Cr base; capped by `_band` at 30 points).

Stored cards keep the flag they were scored with; new results cards are scored with the rule.
