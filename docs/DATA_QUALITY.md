# Data quality: how data is cleaned, and what to do when it is wrong

Two things go by the name "cleaning" in this project, and they are kept apart:

1. **The cleaning built into the pipeline**: every filing passes the same stages, in the same order,
   with no one involved.
2. **The routine for bad data**: what a person or a session does when a card, a figure or a company's
   memory turns out to be wrong.

The rules behind both: code owns every number (D23); nothing is corrected by guessing (D25); what was
received is kept, so any cleaning step can be fixed and run again over it.

## 1. The cleaning built into the pipeline

| # | Stage | What it cleans | Where |
|---|---|---|---|
| 0 | **Raw copy** | Nothing: every JSON answer from BSE and NSE is saved exactly as received, before it is parsed | `raw.py`, `raw/` in the object store |
| 1 | Filter | Noise is dropped (certificates, trading-window notices, newspaper copies, ...); routine filings (votes, dividends, pledge declarations) get one timeline line instead of a card (D22) | `rules.py`, `config/taxonomy.toml` |
| 2 | Duplicates | One event filed several times becomes one card: the same document (`duplicates.py`), the same event in other words (`similar_timeline_entry`, pass 1 and the fast-track repeat check), one card per results quarter (D20) | `duplicates.py`, `pipeline.py` |
| 3 | Text | Text layer in reading order; scanned pages and pages in a broken font OCR'd (RapidOCR, D26); boilerplate lines removed; the filing's declared unit (lakh, million, crore) read from the document itself | `extract.py`, `ocr.py`, `grounding.declared_unit` |
| 4 | Trusted numbers | Tagged results (XBRL) from BSE's archive or NSE's Integrated Filing are the clean source of a company's figures; memory takes them over anything a model read | `xbrl.py`, `seed.py` |
| 5 | Model output | Shape only: units converted to crore, numbers written as text turned into numbers, schema placeholders treated as missing | validate step in `pipeline.py` |
| 6 | Checks | Change nothing. Each figure is tested against its quote, the filing, the tagged figures and the statement's own sums | `grounding.py`, `gate.py`, `quant.py` |
| 7 | Correction | Only where the filing proves the right value: a unit slip where the filing states the unit, a change recomputed only when the filing states both sides | `pipeline.py` fixers |
| 8 | Hold | A card still failing after a second provider is held back from the feed, not deleted; it waits in the review queue | `held`, migration 0009 |

What is kept, so a stage can be re-run without asking the exchange again:

| Kept | Where | Replaced when |
|---|---|---|
| BSE and NSE JSON answers (announcement pages, results archive, quote header, scrip list, NSE lists) | `raw/{bse,nse}/{endpoint}/{day}/` in the object store | never; `SAVE_RAW=0` turns it off |
| PDF text and OCR'd pages | `data/text_cache/` | when the extraction changes (`CACHE_VERSION`) |
| XBRL files | the text cache's `xbrl/` folder | never |

A saved answer is gzip of one JSON line (url, params, status, fetched_at), a newline, then the body
exactly as received; `raw.decode()` returns both and `raw.saved()` lists one endpoint's day.

## 2. When data is wrong

**Never edit the database or a dossier by hand.** A hand fix is lost at the next rebuild, and the same
error keeps arriving on every new filing.

1. **Find it.** `scripts/defect_digest.py` (what the code flagged, grouped by class), an audit round
   (cards against their PDFs, `docs/AUDIT_LOOP.md`), the review queue on the System page.
2. **Name the class.** Wrong unit, wrong period, wrong column, duplicate, invented fact, wrong
   direction... One class is one change in code; fix the commonest first.
3. **Find where the class is made**, from the logs and the local database, not by guessing. Ask
   whether one of our own fixers caused it before blaming the model: three of them did (D25).
4. **Fix it in code, with a test named after the filing that showed it.** If the fix is in parsing,
   check it against the raw copy (`raw.saved()`), not a fresh request.
5. **Re-run only the filings it touched**: `scripts/rerun.py` puts them back in the queue and
   `python -m bse_intel process --news-ids ...` reads only them. Their text is cached, so this costs
   AI calls only.
6. **Read the same filings again** with the model weights unchanged, so the comparison measures the
   fix. Better: next class. Not better: back to step 3.
7. **Rebuild memory** when the fix changed stored figures: `seed-memory` for the companies, then
   `scripts/memory_check.py`.
8. **Only then** a fresh audit round, on filings the loop has not seen.

Record each round in `docs/audit/` (what changed, the counts before and after) and the decision in
`docs/TRACKER.md`. The 2026-10-17 loop (`docs/audit/loop-2026-10-17.md`) is the worked example.

### Automatic correction: the two-source rule (owner, 26 Oct 2026)

Wherever a correction can be automated it must be, but only on proof:

- **Two independent sources agree on the right figure** (for example the filing PDF and the sum of the four quarters,
  or the PDF and screener.in): the figure is corrected automatically, by code, and labelled with both sources.
- **One source only, or the sources disagree**: the figure is held (not shown, never guessed) and listed for review.
- **A line our code computes** (EBITDA, total expenses) whose inputs are right is recomputed from them.
- The exchange's own file is one source, not proof: companies' XBRL can be wrong (Glenmark FY26 owners' and
  minorities' profit swapped, 26 Oct 2026). Every automatic correction is logged and can be undone; stored data is
  still never edited by hand. A correction path goes behind a switch and through the release check like any card change.
- **A PDF figure counts as a source only when read from the page's text layer, with its unit printed on that page and
  its column and basis proven.** A figure read only by OCR (a scanned page) can hold or list a figure, never correct one
  (owner, 26 Oct 2026: scanned copies, units and OCR misreads).

## What not to do

- Do not loosen a check until a card passes; calibrate it against the measured baselines
  (40/8/3 on grounding) and say what it lets through.
- Do not let a fixer write a value the filing does not state.
- Do not delete a held card or a duplicate: mark it, so the audit can still count it.
- Do not compare two rounds that used different model weights or different filings.
