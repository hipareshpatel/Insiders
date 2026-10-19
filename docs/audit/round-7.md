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

Added before the run (2026-10-19): the **pack bleed check** -
`scripts/audit_round7/pack_bleed.py` after the run (every packed card records its pack's members), with the reviewers'
issue class `other` labelled "fact from another filing" when a card states a fact that belongs to another filing.

Also added before the run (owner, 2026-10-19 19:20 IST): Gemini 3.5 Flash and 3 Flash preview join the packed rotation
after 3.6, 3.7 and 3.8 Flash, each with its own free daily quota (60 -> 100 packed requests a day), so a round no longer
runs out of Gemini as round 6 did; reported per model. Gemini 3.5 Flash Lite is last (owner): it writes a pack only when all five
Flash models are out for the day, under the trial writers' rule (at most about 8% WRONG).

MiniMax and Gemma were planned as trial writers and taken off again before the run (their evening trial failed on
supply, round-6.md); long documents go to Gemini 3.6 Flash first.

**Started early** at **fd1e180** (owner, 2026-10-19 20:25 IST, "let's continue our round 7 audit") on the Gemini quota left of the
Pacific day (about 19 requests on 3 Flash preview, 9 on 3.6, 4 on 3.8, none on 3.7 or 3.5 Flash, about 490 on 3.5 Flash
Lite), so 3 Flash preview and 3.5 Flash Lite write more of it than a full day would; the per-writer report shows each.
Writers measured besides Gemini: GLM-4.5 Flash and Nemotron 3.5 Super VL. The scheduled 12:40 start is disabled.

**First start stopped** (20:58 IST, 30 minutes in): Gemini's remaining quota could not carry it - 3.6, 3.7 and 3.5 Flash
spent, 3.8 nearly, and 3 Flash preview answering Google's "503 high demand" until its circuit opened - so every pack
went to 3.5 Flash Lite, and 10 long documents failed with 3.6 Flash out and Nemotron 3.5 Super VL answering empty. Fixed
before the restart: long documents now go to all five Flash models, then Lite, VL last. Companies reset; the 13 cards
written are kept in `data/audit/round7/cards_first_start.json`, not reviewed. Round 7 runs again at 12:40 IST on
2026-10-20 with Gemini's full daily quota.

Added 2026-10-20 01:50 IST (TASKS T3): **the card blocks are part of the card.** Since efbe96b a card's face carries the
results table (`results` with `lines`, previous-quarter and year-ago columns), the size of an order or deal (`scale`),
the rating move (`rating_change`), the case steps (`case_stage`), "Management said" (`guidance_recall`) and the
"For the decision" lines computed from `priced_at_filing` (since the filing, run-rate P/E). `audit_export.py` leaves
these out, so the round exports with `scripts/audit_round7/export.py` (the same script with those fields kept; same
arguments). The reviewers get round 4's prompt word for word, plus this one paragraph at its end:

> The card also carries computed blocks: `results` (a table of the statement's lines with the previous quarter and
> the year-ago quarter, and YoY/QoQ), `scale` (the order or deal size against revenue, market cap or net worth, and per
> year of its term), `rating_change` (the agency's grade before and after, and notches), `case_stage` (where a
> regulatory case stands), `guidance_recall` (what management said earlier, with its date and deadline) and
> `fundamentals`. They are shown on the card as published. Judge them like any other figure: a wrong figure, period,
> comparison, grade or stage in a block makes the card WRONG; a block that does not belong to this event (an order
> size on a rating card, guidance already past its deadline shown as current) is at least MINOR. A block that is
> absent is not an error.

The start commit goes in the report when the run starts (the scheduled task runs on whatever is checked out; at
01:50 IST that is a1ed393 or later, after ae73b45 as T3 asks).

## Pass marks, set before any processing or review

- **Go-live: WRONG at most 5% of published cards** (owner). Beside it, 15%.
- Recall: at most 2 MISSED of ~50.
- Reported per event type (RESULTS, ORDER_WIN, CAPEX first) and per writer.
- Pack bleed: 0 facts from another filing on published cards.
