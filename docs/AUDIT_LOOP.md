# The audit loop: improve from every 100 cards

The owner's rule (2026-10-16): keep improving, again and again, from 100-card reviews. A card is judged against
its own filing by independent reviewers, never by the code that wrote it (the reference repo found 4 to 5 problems
in a batch by itself and about 60 with ten reviewers: "never audit alone").

## One round

1. **Sample.** 100 cards not yet audited, spread across **at least ten different companies** (the owner's rule,
   2026-10-16) and covering all event types, results included. `audit_export.py` takes the cards company by company,
   newest first, and refuses a round that covers fewer than ten companies (`--min-companies`); skip audited ids with
   `--skip docs/audit/audited_ids.txt`.
2. **Export.** Query the cards from the local database and run `scripts/audit_export.py` (it writes the same cached
   filing text the pipeline read, so reviewers see what the model saw): about 10 cards per reviewer folder.
3. **Review.** One independent reviewer per folder (a folder holds cards from several companies, so no reviewer
   sees one company only), with the prompt in `docs/audit/REVIEWER_PROMPT.md`. Each writes
   `findings.json`: per card OK, MINOR or WRONG, and each issue's field, what the card says, what the filing says
   and its class.
4. **Tally.** `python -I -X utf8 scripts/audit_tally.py <dir> --save docs/audit/round-N.json`; add the round to the
   table below and append the audited ids to `audited_ids.txt`.
5. **Fix by class, in code first.** Order: a check that can be written as a pure function with a regression test named
   after the real filing; then a prompt change; then a hold-list line (`pipeline/config/card_holds.txt`) for the
   cards already published. A fix that cannot be tested on the audited cards is not done.
6. **Re-run** the affected cards, then audit the next round. Do not fix and re-audit the same cards only: the target
   is the error rate on cards the fixes have never seen.

## Measure

Share of WRONG cards, share of OK cards, issues per card, and the class counts, per round. The gate for starting the
full backfill is set by the owner (suggested: under 10% WRONG on two consecutive fresh rounds, and no WRONG card
with a wrong headline figure).

| Round | Cards | OK | MINOR | WRONG | Main classes | Fixes made after |
|---|---|---|---|---|---|---|
| 0 (2026-10-16, both smoke tests, old code) | 177 | 26 (15%) | 56 (32%) | 95 (54%) | invented 147, arithmetic 89, unit scale 88, wrong period 64, signal verdict 55, wrong column 43, event type 34 | XBRL results, unit-slip correction, YoY/QoQ from XBRL, event-type rules, signal checks, D20, accuracy gate, deal size from shares x price, newspaper cuttings |
| 1 | next 100 fresh cards of the rebuild | | | | | |

## Standing checks between rounds

- Owner-reported cards (Novartis SPA, the KPI "missed" case) become regression tests in the same commit as the fix.
- The class that is largest and has no code check (invented facts) is the next piece of work: a verbatim quote per
  claim, checked in code (docs/REFERENCE_REVIEW.md section 1).
