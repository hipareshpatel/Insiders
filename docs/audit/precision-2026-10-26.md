# Number matching at the precision the filing prints: measurement (26 Oct 2026)

Owner question: if numbers are matched at the precision the filing prints (and cards show 1,000 Cr or more in whole crore,
smaller to one decimal), what share of cards is OK? Context: `root-causes-2026-10-25.md` P4 (the quote and prune checks are
wrong both ways), `grounding.SourceIndex.stated_crore` (already takes a whole-crore print for 1,000 Cr or more), F156
`QUOTE_EXACT_NUMBERS` (off).

**Status: the script is built and tested on a synthetic fixture; the real run has NOT been done.** Production cards and
their texts are reachable only from GitHub (the platform API with the ingest token, and the text cache in R2
`text/<news_id>.json.gz`); this session has neither (no `data/`, no secrets). Start it from Actions > Maintenance >
Run workflow > `audit-precision` (read-only, no AI, no writes; artifact `audit-precision`).

## The candidate rule

A function in `pipeline/scripts/audit_precision.py` (`make_candidate`), swapped in for `gate.numbers_in_quote` while the real
card checks run (`pipeline.check_quotes`, `pipeline.check_quoted_numbers`); live code is untouched.

- A card figure matches a source figure when they agree at the coarser of the two prints: the source's own decimals (source
  "10,738" takes card 10,737.58; source "10,737.58" takes 10,737.58 or its rounding to the card's decimals) or the card's last
  digit.
- The whole number must match. No prefix ("95" never matches "951.96"; "1,95,000" never matches "19,500").
- A figure cut rather than rounded at the card's last digit no longer matches ("79" of 79.6 stays wrong).
- Units as today (the card's written unit against the quote's own unit or the filing's declared unit; "458 Cr" of 457.86 million
  still fails). Same exemptions as today: percentages, bps, period labels, dates, days of the month, foreign currency.
- A bare integer source of fewer than three digits (a note number) has no rounding step, as today.

Variants run over every stored card, same inputs: `off` (today), `f156` (`QUOTE_EXACT_NUMBERS=1`), `on` (the candidate),
`on_display` (the candidate, with the card's explicit-crore figures first shown the owner's way: 1,000 or more in whole crore,
smaller to one decimal).

What differs from today, in plain words: today's check already rounds at the source's print for sources of three digits or more.
The candidate's changes are (1) no prefix match, (2) no cut-at-the-last-digit match, (3) a source with one or two digits and a
decimal ("9.5") now has a step. Prefix match only applies where the card writes no unit (a bare per-share figure, a count, a
lakh amount in full), so expect the newly failed lines mostly there; the unit-written case ("Rs 95 Cr" against 951.96) is
already refused today. This was seen on the fixture and should be read in the real counts.

## How it runs

    cd pipeline
    python -I -X utf8 scripts/audit_precision.py OUT_DIR --platform [--limit N]          # the GitHub job
    python -I -X utf8 scripts/audit_precision.py OUT_DIR --cards ROWS.json --texts DIR   # offline (export_cards rows + text caches)
    python -I -X utf8 scripts/audit_precision.py --selftest

Output: `summary.json` (per variant: cards checked; held cards released, loose and strict; held reasons that go away; published
cards newly failing; lines cleared and added), `lines.json` (every changed line with the card text, quote and figures),
and the blind-sample markdown.

Reading the summary:

- `held_only_quote_number_reasons`: held cards whose every stored issue is a "states X, which its own quote does not" issue,
  with no grounding fault and no owner hold. `held_only_number_reasons_incl_grounding` also lets "ungrounded" and
  "math mismatches" count as number reasons. `held_reason_classes` lists every class holding the held cards.
- `held_released_loose`: held, number-only, and the candidate finds no figure problem left. `held_released_strict`: also
  every stored issue is found again by today's re-run and cleared by the candidate.
- `published_newly_fail`: published cards with a line the candidate fails and today's checks pass.
- `reproduced_by_off` over `stored_number_issues`: how many stored number issues today's re-run finds again. It is below 100%
  because the re-run has no XBRL table, memory or second reading; compare the variants with each other, not with stored verdicts.

## Blind sample

`precision-sample-2026-10-26.md` (written by the job into the artifact): 20 released and 20 newly failed card lines, seeded
(2610), shuffled together, with card text, the card's quote and the pdf link; the key is at the bottom. A blind reviewer judges
each line RIGHT or WRONG from the filing alone. The author does not judge them. Release rule (CLAUDE.md): a check that accepts
more needs this on/off audit plus the independent sample; the share of the released lines the reviewer finds WRONG must be
within the go-live bar (D42, 5%).

## Not measured by this script

- Grounding (`SourceIndex.stated`, the "figure not found" hold). The candidate matches only the quote check. `stated_crore`
  already takes a whole-crore print for 1,000 Cr or more with decimals.
- The share of all cards that are OK: that needs the blind reviewer's verdicts on the sample, applied to the counts.
