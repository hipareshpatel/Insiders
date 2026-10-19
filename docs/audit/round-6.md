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

As round 5's arm B, on the code at the start commit (recorded when the run starts): memory first (`seed-memory`,
`governance-sync --scrips`), then `backfill-companies` on free providers only (`FREE_ONLY=1`) with packed Gemini
(`PASS2_PACK=6`, `PASS2_PACK_WAIT=150`, 10 workers) and the writers of `549d133`. Every published and held card reviewed
blind by independent agents, one per folder, with `REVIEWER_PROMPT_ROUND4.md` word for word, except two things decided
before the review: the export shows the impact the site shows (125f9a8), and in the missed-news prompt a call transcript
set aside is MISSED (owner, D33). Missed news: ~50 set-aside filings.

## Pass marks, set before any processing or review

- **Go-live: WRONG at most 5% of published cards** (owner, 2026-10-18). Beside it the earlier mark, 15%.
- Recall: at most 2 MISSED of ~50.
- Reported per event type (RESULTS, ORDER_WIN, CAPEX first: owner, 2026-10-19) and per writer model.
