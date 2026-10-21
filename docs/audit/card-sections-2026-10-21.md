# The card's three analysis boxes (owner item A18, 21 Oct 2026)

Owner: "What these numbers mean", "For the decision" and "Our reading" are "really important and not used correctly".
Examples given:
- a "Tax rate" line on a results card;
- "Not disclosed: swap ratio" on a results card;
- "Watching: … cost auditor approval" under "For the decision";
- "Our reading" holding only a restatement.

## What similar sites put there

| Source | Finding |
|---|---|
| Tijori Alerts, Zerodha's WhatsApp filing alerts ([zerodha.com](https://zerodha.com/z-connect/general/tijori-alerts-stock-exchange-filings-on-whatsapp)) | Short AI summary with a link to the filing. No interpretation layer is described. |
| Indian announcement monitors ([tradingqna.com](https://tradingqna.com/t/ai-driven-corporate-announcement-monitoring-for-indian-markets/190337)), Trendlyne, Tickertape | Classify, tag and alert. None publishes an "interpretation" standard (searched 21 Oct; Trendlyne's AI "evaluates sentiment in earnings calls"). |
| International earnings tools: AlphaSense, Aiera, Quartr, Koyfin, Seeking Alpha, Bloomberg ([2026 roundup](https://pro.stockalarm.io/blog/best-ai-earnings-call-summary-tools)) | A good summary carries: results with their drivers; guidance raised, lowered, reiterated or vague; management tone; analysts' concerns; market reaction; what to watch next quarter. |
| Sell-side earnings-update notes (e.g. the published earnings-analysis guides) | Lead with the result against what was expected, quantify the gap, say why it differed, then guidance and the thesis. |

The common standard:
1. Against what was expected.
2. Why it moved.
3. What it means for the shareholder.
4. What to watch next.

Housekeeping is in none of them.

## The rule for each box

| Box | Holds | Never holds |
|---|---|---|
| **What these numbers mean** / **Why it matters** | Code's checked signals: size against the company, guidance kept or breached, a one-off that flatters profit, order flow, an audit flag. A "not disclosed" item only when this event should disclose it. | The Reg 30 materiality boilerplate; the three-quarter tax-rate check (both stay in "Full analysis"); a deal term on a non-deal card (a swap ratio on results). |
| **For the decision** | What memory held before the filing that bears on it: management's guidance, the latest quarter, a holding shift, an open watch item on the topic, the next check. | Procedure: auditor appointments, AGM or postal-ballot approvals, record dates. These stay on governance and deal cards, where a vote is a stage of the deal. |
| **Our reading** (AI, labelled unchecked) | Up to three insights, in this order: (1) against what was expected; (2) the driver or the quality; (3) what it means for the shareholder or what could undo it. | A restatement of the headline; a procedural point; filler ("fewer insights rather than filler"). |

## Built

- **Web** (`web/src/lib/cardText.ts`; tests in `web/test/cardText.test.ts`):
  - `boxSignal` and `missingOnTopic` filter the first box;
  - `procedural` filters "For the decision";
  - `restates` filters "Our reading" against the headline.
- **Pipeline:** `card_context.memory_context` applies the same procedural rule to new cards (`test_quant.py`).
- **Prompt:** `pass2.md` gives `why_it_matters` the three-part order, the no-restatement and no-filler rule, and "only what this event should disclose" for `missing_disclosures`. This shapes new live cards only: no AI was run to test it.

## Measured over stored cards (no AI)

On/off over the 400 cards of the last 30 days on the live feed. The rules only remove lines, so no check accepts more.

| Rule | Cards changed | Lines removed |
|---|---|---|
| Housekeeping signal off the box | 9 | REG30_THRESHOLD ×6 (Laxmi Dental, Seamec, Sharda Motor, Regaal, Bharat Coking Coal, SPARC); LOW_CASH_TAX ×3 (Indosolar, BHEL, Sejal) |
| Off-topic "not disclosed" | 1 | Indosolar results: the Waaree swap ratio |
| Procedural decision line | 4 | Indosolar (cost auditor), Titan and BHEL (dividend approval at the AGM), Kanoria Chem ("Shareholder approval") |
| Reading restates the headline | 1 | Heritage Foods: "Acquisition completes consolidation of Heritage Novandie Foods" |
| Catalyst restates the headline (rule already live) | 6 | — |

### A stricter reading rule, tried and dropped

The first version dropped a reading that repeated anything on the card's face. It removed 71 cards' readings, and the hand check found good ones among them:
- UCO Bank: advances "exceeding the 12-14% credit growth guidance";
- KEI: growth "an acceleration over Q1FY27";
- TBO Tek: the penalty "already flagged in the accounts";
- Yes Bank: the watch item settled.

So the reading is now checked against the headline only. The prompt does the rest.

### Two procedural lines kept on purpose

- QPower's "Shareholder approval for enabling resolution for fundraising" stays on fundraise cards: there the vote is a stage of the deal.
- Persistent's "EGM considered enabling resolutions for borrowing" stays: bare AGM/EGM are not in the rule.
