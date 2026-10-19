# Audit round 5: a second measured NSE round, after round 4's fixes

Written 2026-10-19, before any round-5 company was processed. Round 4 (`round-4.md`) failed accuracy at 21% of published
cards WRONG on free providers; its classes were fixed in two waves (TRACKER F73 and after) and its own companies' re-run
measured 13%. A re-run is measured on the cards the fixes were written from, so this round asks the honest question on 20
companies none of them was fitted on.

## Sample

Twenty companies, one per round 4's sector-and-size strata (large ≥ ₹10,000 Cr, mid ₹500-10,000 Cr), listed on NSE, with
no filing in the ledger (so none of rounds 2-4 or the smoke test), drawn with seed **20261021**
(`pipeline/scripts/audit_round5/select.py`, `companies.json`): UCO Bank, Sundaram Finance, Repco Home Finance, Max
Financial Services, Persistent Systems, Protean eGov, Granules India, Lincoln Pharmaceuticals, Siemens Energy India,
Texmaco Rail, Balaji Amines, Electrosteel Castings, Saint-Gobain Sekurit, Dabur India, IFB Industries, Ceigall India,
Runwal Enterprises, Sunrakshakk Industries, Ramco Cements, NLC India.

Window: 15 July to 18 October 2026, as in rounds 2-4.

## Method (round 4's)

Memory first (`seed-memory`, `governance-sync --scrips`), then `backfill-companies` on free providers only
(`FREE_ONLY=1`). Every published card and every held card (mixed in, unmarked) reviewed blind by independent agents,
one per folder, with `REVIEWER_PROMPT_ROUND4.md` word for word (the exports now carry the XBRL table itself); the author
of the fixes does not review. Missed news: ~50 set-aside filings, same prompt.

## Pass marks, set before any processing or review

- **Go-live: WRONG at most 5% of published cards** (owner, 2026-10-18).
- Beside it, rounds 2-4's mark: WRONG at most 15%.
- Recall: at most 2 MISSED of ~50.

No check is loosened between processing and review; a defect seen in the run is written down and fixed after.

## Result, baseline run (2026-10-19, code `caeef2c`, free providers only)

Reviewed by 14 independent blind agents (cards, one folder each) and 5 (missed news), with `REVIEWER_PROMPT_ROUND4.md`
word for word; tally in `round-5.json`. The run predates results cards built by code (F74) and packed Gemini (F75).

- **Accuracy: FAIL.** Published cards: **26 of 113 WRONG (23%)**, 48 MINOR, 39 OK. Held: 11 of 27 WRONG (41%).
  Marks set before review: go-live WRONG <= 5%, the earlier rounds' mark <= 15%.
- **Recall: PASS.** 0 MISSED of 50, 3 UNSURE: Persistent's AGM approval of the Nagarro deal (its own card exists,
  nse-106725226: RIGHT); Max Financial's FY26 annual report filed with its AGM notice and turned away as a notice
  (its SEBI show-cause matter has a card from the disposal order, nse-106755435; the routing of an annual report inside
  an AGM notice is open); Texmaco's Q1 call transcript, set aside as a repeat of the results card although it gives the
  order book and a new South Africa order (whether transcripts get their own card is the owner's call).
- **By event type, published:** RESULTS 8 of 16 WRONG; ORDER_WIN 7 of 23; LITIGATION 2 of 10; CAPEX 2 of 7; OTHER 2 of 7;
  CONCALL 2 of 6; FUNDRAISE, CORPORATE_ACTION, MONTHLY 1 each; M&A 0 of 16, GOVERNANCE 0 of 9, RATINGS 0 of 5.
- **By writer, published:** Nemotron 3 Super 18 of 63 WRONG (29%; results 7 of 12, others 11 of 51); Nemotron 3.5 Super
  VL 5 of 15; GLM 4.5 Flash 3 of 32 (9%); Llama 3.3 0 of 2; Gemini 0 of 1.
- **Classes (all cards):** other 96, invented 58, memory 37 (apart), signal_verdict 16, event_type 15, direction 15,
  wrong_period 12, arithmetic 9, standalone_consolidated 4, unit_scale 4, wrong_column 3. Impact level fits on 91 of 140.

What the agents found, by class, and what was done (2026-10-19, after the review):

1. **Results cards** (8 of 16): the year-ago column taken from memory's other quarters (Dabur EBITDA, Protean margin),
   inventory and tax read backwards (Lincoln, IFB, Texmaco, Repco, Ceigall), causes the statement contradicts (Ramco
   "lower other income", Texmaco PAT up on "cost savings" when a tax credit did it), standalone H1 as the quarter
   (Persistent). Built since: results cards written by code from the XBRL (F74); measured in arm B.
2. **A later event's XBRL joined to an earlier filing** (Dabur: the 7 Aug court-stay file paired with the 6 Aug FDA
   letter, so the card told of a stay granted the day after its own filing). Cause: the company's own name confirmed a
   content join. Fixed: `EventFacts.names` never offers the company's own name (test).
3. **Order sizes that are another quantity** (Ceigall: ₹608.67 Cr a year for 35 years read as the order value, the
   ₹5,300 Cr project cost Ceigall funds read as an order; Ramco's cumulative ₹1,106 Cr disposals as one sale; a stone
   block lease Ceigall pays for as an order). Prompt rule added to `deal_value` (per-year amounts, running totals,
   amounts the company pays).
4. **One order counted twice** (Ceigall's Bihar LoI "in continuation to our earlier intimation dated 08th September").
   Fixed in code: `pipeline.continued_deal` makes the card the next stage of memory's deal of that date (test).
5. **A twelve-month share written as the quarter's** (Ceigall "19.5% of Q1FY27 revenue", 72.7%; Protean, Max
   Financial). Fixed: the scale block names each revenue ("trailing-12-month revenue", "Q1FY27 quarter revenue").
6. **The writer.** Nemotron 3 Super wrote 63 of 113 published cards at 29% WRONG; GLM 4.5 Flash 9%. Arm B (below) re-runs
   the same companies with packed Gemini writing pass 2.
7. Open, not yet fixed: impact level set too high on routine reaffirmations and procedural steps (49 of 140 off);
   pending approvals copied from a stale memory watchlist; ratios against a holding company's standalone revenue.
8. **Impact level, measured against what the site shows** (2026-10-19, after the review). The export gave reviewers
   the writer's impact; the site shows the card's score. Against the agents' calls the writer fitted 91 of 140, the
   site's score 85: it fixed overrated cards (22 shown LOW where the writer said MODERATE and the agents said LOW) but
   put 12 results cards at LOW. Results are now never shown LOW (`scoring.score`, test), and the export carries the
   shown impact from round 6 on (`audit_export.py`, `audit_round5/sample_cards.py`).
