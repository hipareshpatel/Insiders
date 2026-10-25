# Labels on every memory item (TODO items 3, 10, 16): design, 25 Oct 2026

Status: design only; nothing built. Drafted by a helper from the code (references checked by the lead session:
dossier.py `new_dossier` :290, `_metric_entry` :419, `put_standalone` :569, `merge` :827, `view_as_of` :1212,
`latest_fundamentals` :1467, `results_snapshot` :1798; pipeline.py `_apply_xbrl` :3427-3428, :3672; web/worker/public.ts :413).

## The gap today
Memory records which filing an item came from (a news id), and for exchange figure files an id starting `xbrl:`.
It records nothing about the kind of document, the page, the quote or the unit as printed. A figure from a results
filing's own XBRL file can sit under a plain `nse-...` id, so the id alone cannot tell an exchange figure from an AI one.

## The label (`lab`)
`by` file | ai | calc | unknown; `doc` results | call | slides | release | board | annual | other; `basis`;
`unit` as printed; `page` and `quote` (required when by=ai); `at` (recorded); `ok` (passed our checks);
`from` (input ids, calc only). On each source of a figure, on each table row, on text items (they only need by, doc, at).
Sections that only exchange feeds write (ownership, governance, corporate actions, pledges, insider trades) are
labelled `file` by section.

## Old memory (no AI)
`xbrl:` ids and exchange-feed sections -> file. Call and slide items -> ai, no quote, so "said on <date>" only.
A figure under an `nse-...` results id -> file only when the stored card's XBRL block has the same value for that
quarter; else unknown. Everything else unknown. Unknown is never shown as a fact and never feeds a computed figure.

## Build steps
1. Label writers and schema; readers unchanged (no card change).
2. One-off labelling job, dry run first with counts per section (no card change).
3. AI figures carry page and quote, checked against the filing's text (new items only; no card change yet).
4. Readers enforce item 3 (results table comparatives, "from memory" figures, the memory the model sees, list
   columns), behind a switch. Changes cards: release check (on/off audit over stored cards, blind sample).
5. facts.py enforces item 16 (computed figures only from labelled inputs); the company page shows labels.
   Changes cards: release check.

## Open questions for the owner
See the to-do list (items 3 / 10 / 16).
