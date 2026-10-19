# Audit round 7: the fourth measured NSE round, after round 6

Written 2026-10-19 before any round-7 company was processed. Round 6 failed at 17% of published cards WRONG, nearly all of
it from a spare writer (Nemotron 3 Super, 12 of 36) taking cards when Gemini's quota ran out; Gemini wrote 3 WRONG of 55.
Its classes were fixed (TRACKER F77): the weak writers are off every card route, quota days follow each provider, and
results cards take their takeaway and memory comparisons from code. This round measures that on 20 more companies.

## Sample

Twenty companies, one per round 6's strata, on NSE at or above ₹500 Cr, with no filing in the ledger and in no earlier
round's sample, drawn with seed **20261023** (`pipeline/scripts/audit_round7/select.py`, `companies.json`): IndusInd
Bank, JSW Holdings, Aryaman Financial, Go Digit, L&T Technology Services, Brightcom, Indegene, Krsnaa Diagnostics, CG
Power, Skipper, Thirumalai Chemicals, BMW Ventures, Hero Motors, Gillette India, Radhika Jeweltech, KNR Constructions,
Puravankara, Lux Industries, ACC, Adani Green Energy. Window: 15 July to 18 October 2026.

## Method

As round 6: memory first, then two lanes of 10 companies (`PASS2_PACK=6`, `PASS2_PACK_WAIT=150`, 8 workers each, free
providers only), started after Gemini's quota reset (12:30 IST), on the start commit recorded when the run starts. Every
published and held card reviewed blind by independent agents with `REVIEWER_PROMPT_ROUND4.md` word for word (the
missed-news prompt with round 6's one change: a set-aside call transcript is MISSED). ~50 set-aside filings.

Added before the run (2026-10-19): two OpenRouter free writers on trial, MiniMax M3.1 Flash and Gemma 4 31B, with a
share of the regular pass-2 routes, reported per writer like the rest; and the **pack bleed check** -
`scripts/audit_round7/pack_bleed.py` after the run (every packed card records its pack's members), with the reviewers'
issue class `other` labelled "fact from another filing" when a card states a fact that belongs to another filing.

## Pass marks, set before any processing or review

- **Go-live: WRONG at most 5% of published cards** (owner). Beside it, 15%.
- Recall: at most 2 MISSED of ~50.
- Reported per event type (RESULTS, ORDER_WIN, CAPEX first) and per writer.
- Pack bleed: 0 facts from another filing on published cards.
