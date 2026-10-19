# Live review (D37, TASKS T16)

The daily review of the live site's cards by independent reviewer agents.

1. Save the published feed: page `https://insiders.reply-bd3.workers.dev/api/feed?range=all&limit=50` by `next_cursor`
   into `<work>/../live/feed.json` (a browser User-Agent: the site refuses Python's default one).
2. `python -I build.py <work> [seed] [feed folder]` (defaults 20261020, `live`): a seeded sample by event type (the plan and seed are in the script), one folder of
   four cards per reviewer, each with `<news_id>.card.json` (the card as published; the check fields `model`, `pack`,
   `review`, `grounding`, `promise_updates` removed), `<news_id>.memory.json` (the company's live memory as it stood
   just before the filing, `dossier_as_of`, with the card's `scale` block as `scale_block`) and `<news_id>.pdf`.
3. `python -I text.py <work>/folders`: `<news_id>.pdf.txt`, the text layer, OCR on pages with almost none.
4. One reviewer agent per folder, with `docs/audit/REVIEWER_PROMPT_ROUND4.md`'s published-cards prompt word for word,
   round 7's card-blocks paragraph (`docs/audit/round-7.md`, Method) and one line pointing at the PDF beside its text.
   The reviewers see nothing else: not the code, the fixes or this session.
5. Tally into `docs/audit/live/<date>.json` (every finding) and `<date>.md` (counts, the WRONG classes, what is fixed).
