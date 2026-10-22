# Shadow critic scored against a blind review, 22 Oct 2026

The shadow critic's verdicts on the 23 live cards it judged on 20-21 Oct (`critic-2026-10-22.json`, from
`audit-export.yml`) against an independent reviewer. The reviewer read each card against its filing PDF without seeing
the critic's verdicts; the fix author did not review (`critic-review-2026-10-22.json`, a verdict per point).

## The cards

- **Overall:** 12 RIGHT, 10 MINOR, 1 WRONG (4% WRONG).
- **The WRONG card:** L&T, nse-106822983. The filing marks the orders "*Large", which its own table defines as ₹2,500-5,000 Cr. The card says the actual values are much smaller, which the filing contradicts.
- **Non-OK points:** 18 in all:
  - 6 unsupported causes;
  - 5 missing facts, counted once per card;
  - 2 wrong figures (Adani Power's takeaway gives 1,320 MW where supply is 1,234 MW; Imagicaa's takeaway is garbled);
  - 2 overstated;
  - 1 invented.
- **Figures:** every figure in the results cards and tables was recomputed from the statements, and all match.

## The critic

| | Critic | Blind reviewer | Agree |
|---|---|---|---|
| Points flagged | 8 | 10, plus 5 missing facts | 1 |
| Precision (critic flags the reviewer confirms) | 1 of 8 = **12%** | | |
| Recall (reviewer faults the critic caught) | 1 of 10 = **10%** | | |
| Cards flagged | 6 | 11 not RIGHT | 4 |
| Card-level precision / recall | 67% / 36% | | |
| The WRONG card | flagged | WRONG | yes |
| Missing facts | 2 | 5 | 0 |

**Reading:**
- At the point level, the critic and the reviewer rarely land on the same line.
- Its 7 unconfirmed flags are unsupported causes or invented items on lines the reviewer found supported.
- It missed the commonest real fault, a cause the filing does not give (INDIANB, VMM, HCLTECH), and both wrong figures.

**Decision:** the critic stays in shadow mode, where it neither holds nor edits a card. The audit scores it again each day. The 22 Oct export holds 23 cards, too few to retune it on.
