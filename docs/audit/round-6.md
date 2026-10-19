# Audit round 6: the third measured NSE round, after round 5 and its arm B

Written 2026-10-19 before any round-6 company was processed. Round 5 on its own companies went from 23% of published
cards WRONG (baseline) to 10% (arm B: packed Gemini writing, results cards built by code); every fix since was written
from those cards, so this round asks the question again on 20 companies none of them was fitted on.

## Sample

Twenty companies, one per round 5's sector-and-size strata, listed on NSE at or above ₹500 Cr, with no filing in the
ledger, drawn with seed **20261022** (`pipeline/scripts/audit_round6/select.py`, `companies.json`): Punjab & Sind Bank,
Bajaj Finserv, Northern Arc Capital, LIC, Mphasis, Kellton Tech, Poly Medicure, 3B BlackBio Dx, Titagarh Rail Systems,
Disa India, Jubilant Agri and Consumer Products, Man Industries, Automobile Corporation of Goa, ITC, Orient Bell, Supreme
Infrastructure, Sunteck Realty, DCM Shriram International, Ambuja Cements, Clean Max Enviro Energy.

Window: 15 July to 18 October 2026, as in rounds 2-5.

## Method

As round 5's arm B, on the code at the start commit **2aa4bf1** (run started 2026-10-19 12:09 IST in two lanes of 10 companies, each seeding then processing, so companies need not wait for all 20 to be seeded): memory first (`seed-memory`,
`governance-sync --scrips`), then `backfill-companies` on free providers only (`FREE_ONLY=1`) with packed Gemini
(`PASS2_PACK=6`, `PASS2_PACK_WAIT=150`, 10 workers) and the writers of `549d133`. Every published and held card reviewed
blind by independent agents, one per folder, with `REVIEWER_PROMPT_ROUND4.md` word for word, except two things decided
before the review: the export shows the impact the site shows (125f9a8), and in the missed-news prompt a call transcript
set aside is MISSED (owner, D33). Missed news: ~50 set-aside filings.

## Pass marks, set before any processing or review

- **Go-live: WRONG at most 5% of published cards** (owner, 2026-10-18). Beside it the earlier mark, 15%.
- Recall: at most 2 MISSED of ~50.
- Reported per event type (RESULTS, ORDER_WIN, CAPEX first: owner, 2026-10-19) and per writer model.

## Restart (2026-10-19 13:50 IST)

The first run (from 2aa4bf1, 12:09) wrote 119 cards, nearly all with the spare writers: Gemini's per-day 429 from before
its 12:30 IST reset kept all three Gemini models retired for the rest of the IST day, and the usage ledger counted
Gemini on the UTC day. Fixed in `0d22577` (quota days follow each provider; Gemini's is Pacific), the round's cards and
memory reset, and the round restarted at **f075647** with the same companies, window, settings and pass marks. The first
run's cards are kept in `data/audit/round6/cards_first_attempt.json` and are not reviewed.

## Result (2026-10-19, run from f075647; 14 card and 5 missed-news agents, blind)

- **Accuracy: FAIL.** Published: **17 of 101 WRONG (17%)**, 41 MINOR, 43 OK (`round-6.json`). Held: 13 of 37 WRONG.
- **Recall: PASS.** 0 MISSED of 50 on the owner's rules; agents marked 2: DCM Shriram International's ₹59,000 exchange fine
  (under D32's floor, so RIGHT) and Ambuja's ACC merger vote, which had a card (held) and was in the sample only because
  the export took it by its routing reason. 2 UNSURE: Ambuja's Orient Cement scheme approval; Jubilant's creditors'
  approval of its demerger, folded into the shareholders' card.
- **By writer, published:** Gemini 3.7 Flash 3 of 42, 3.6 Flash 0 of 7, 3.8 Flash 0 of 6 (**Gemini 3 of 55, 5.5%**);
  **Nemotron 3 Super 12 of 36 (33%)**, though a spare: it took the packs that fell back when Gemini's quota ran out
  (7 failed packs), 23 second opinions (a second opinion avoids the first writer's provider) and 8 long documents,
  whenever Nemotron 3.5 Super VL and GLM-4.5 were rate-limited. Nemotron 3.5 Super VL 1 of 6; GLM-4.5 0 of 3; GLM-4.7 1 of 1.
- **By type, published:** RESULTS 4 of 14; CONCALL 4 of 11; GOVERNANCE 4 of 9; LITIGATION 2 of 7; ORDER_WIN 1 of 9;
  CAPEX 1 of 6; M&A 1 of 16; RATINGS, MONTHLY, PRODUCT, FUNDRAISE, OTHER, CORPORATE_ACTION 0.

Done after it (2026-10-19):
1. Nemotron 3 Super and GLM-4.7-Flash taken off every card route: with no good writer free a filing waits or stays
   queued (no attempt spent) rather than getting a card from a 33%-WRONG writer.
2. Memory points read the vetted memory view, take the file's own earlier quarters first and rank only an unbroken
   run (Orient Bell "highest quarter" when memory lacked the higher Q4FY26; Jubilant "highest of 6" with two held).

Open classes for the next loop: vote and share counts written in crore 10-100x off (Ambuja twice); a promoter-pledge
warning memory does not support (Clean Max twice); EPS change against a pre-bonus year-ago figure (LIC); profit
including minority interest given as the owners' (Bajaj Finserv); a foreign amount written in crore ("THB 1.25 Cr"
for THB 12.5 lakh); a results card's quarter mislabelled (Clean Max Q1FY26 for Q1FY27); restated year-ago figures
(Ambuja, Titagarh); excise-inflated gross revenue as growth (ITC); the missed-news export taking a filing that has a card.
