# Held for quoting only: published without the unquoted points (21 Oct 2026)

Owner: "Needs review · 475 · 20 re-runs queued", cards stored but not published, "because we can't do manual audit to
fix our errors".

## What holds them

Holds on the live export of 21 Oct (`docs/audit/live/held-2026-10-21.json`, 328 cards), counted by issue line:

| Issue | Lines |
|---|---|
| A key number, notable change or "why it matters" quotes a sentence not in the filing | 273 |
| A point states a figure its own quote does not carry | about 230 |
| A figure not found in the filing or memory | about 60 |
| Headline figure not found | 17 |
| Unsupported claim | 13 |
| Scale or fit (QoQ for YoY, margin, PAT above revenue) | about 25 |
| Formula | 6 |

## The rule

- A card whose only faults are points whose quote does not carry them is published **without those points**
  (`pipeline.prune_quote_failures` for new cards, `prune.release` for stored ones). Every point left on it passed every
  check.
- These still hold the card:
  - a figure not found;
  - a headline figure;
  - a sum, a scale or a claim;
  - a garbled scan;
  - the card's last fact;
  - the owner's Wrong.
- A results card whose quarter already has a published card stays held (D20).

## Measured before it was built (no AI)

**On/off over the stored cards:** the rule releases 215 of the 328 held; 113 stay held.

**Independent sample:** the 20 Oct hand review (`needs-review-2026-10-20/verdicts.json`, read by the laptop session and an
independent agent, blind to each other) had read 223 of these cards.

| | Right | Minor | Wrong | Unsure |
|---|---|---|---|---|
| Released by the rule (134 read) | 91 | 26 | **15 (11%)** | 2 |
| Kept held (89 read) | 49 | 25 | **12 (13%)** | 3 |
| Published cards, 21 Oct daily audit (48) | 10 | 27 | **11 (23%)** | 0 |

**What this shows:**
- The quote hold does not tell good cards from bad: 11% wrong among those the rule releases, 13% among those it keeps.
- Both are better than the cards already published.
- Several of the 15 wrong ones were made before fixes that exist now:
  - the owners'-profit filler (F88);
  - Adani Ports' OCI tag;
  - rupee amounts in full.

**Rejected:** a stricter variant that also required every headline figure in a kept fact or the XBRL table released 129
and still let 10 of the 11 wrong cards through. Their errors are in facts that pass the checks, not in the quotes.

**Not met:** the 95% go-live bar. These cards are about as accurate as the rest; the daily audit keeps sampling them
(review status `PRUNED`). The 113 still held, with true faults, go to the end-of-day sweep (`sweep.py`) to be written
again with today's code.
