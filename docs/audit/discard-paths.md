# Where announcements, cards and figures are dropped or held: audit of 2026-10-18

The owner asked (2026-10-18) for every place a filing, a card, part of a card or a memory figure can be
discarded, held back or overwritten, the edge cases in each (rounding was the example: "1.09 lakh vs 1.1 lakh,
will it reject?"), a test for each, and a stage-by-stage count of how many announcements are lost where, so
the throughput of correct cards can be raised.

How it was done: the code was read end to end for every discard path and threshold (the inventory at the end);
the local D1 database, R2 noise objects and run logs were counted stage by stage for the ten smoke-test
companies (`funnel-2026-10-18.md`, re-run with `pipeline/scripts/funnel/`); each suspected defect was
reproduced with a test before it was fixed; loop rounds 3a-3c on the twenty audit filings found the rest.

## The funnel, in short (ten smoke-test companies, before the fixes below)

| Stage | Count | Note |
|---|---:|---|
| Announcements discovered | 1,861 | |
| dropped by rule | 772 (41.5%) | right in bulk; the "AGM notice" rule also takes 12 annual reports |
| filing rows | 1,089 | |
| duplicates | 174 | 105 exact text, 57 one-card-per-quarter (D20), 12 other |
| pass 1 not material | 200 | reads as routine (sub-CXO appointments, analyst meets, BRSR) |
| timeline only | 30 | |
| pass 2 not material | 70 | 8-12 look substantive; its reason is not stored |
| failed / pending | 4 / 160 | |
| **cards** | **451** | |
| held out of the feed | 118 (26%) | 77 held only for an unfound amount |
| **published** | **333** | 17.9% of announcements |

The two largest losses of correct cards were both in the checks, not the reading:
1. **Figures the pipeline gave the model, held as unfound.** Pass 2 is given the company's market cap, revenue,
   net worth and debt to measure an event against; grounding never looked there. 40 of the 77 cards held only
   for an unfound amount were this. Fixed: the scale block is a grounding source (41a67da).
2. **One card per results quarter (D20) let the first document decide.** 19 of 43 quarters with D20 duplicates
   had no published results card: 17 because the owner's card was held while the statement itself was marked a
   duplicate of it, 2 because a notice typed RESULTS claimed the quarter and was then found not material.
   Fixed: a held owner does not own the quarter; a claim without a card is given back (9c26041).

## Defects found, and what was done

Each has a test that fails without the fix. "Loop" means found on the twenty audit filings (rounds 3a-3c).

| # | Defect | Effect | Fix |
|---|---|---|---|
| 1 | A quoted figure matched by its digits whatever its unit; a prefix counted as a rounding ("95" of 951.96) | 10x/100x figures passed their own quote: Novartis employee cost ₹187.2 Cr (₹18.72), cash flow ₹745.7 Cr, CSB gross NPA ₹45,817 Cr (₹458.17) | compared in crore when the card writes a unit; XBRL "net_debt_cr 1348.6" read as crore (8e69ce5) |
| 2 | The sibling-row rule compared bare digits | Jubilant "exceptional items ₹3,595 Cr" (₹359.5) passed as "from another row" | the card's unit goes with the figure (8e69ce5) |
| 3 | A rounding to the card's last digit was refused; a unit written in the quote was not read | "₹1.1 lakh" of 1.09 lakh, "₹53 Cr" of 52.7, "₹1.68 Cr" of "16.8 million" held: 12 of 766 quoted items | rounding at the right unit accepted (e4ea180) |
| 4 | The unit-slip fixer skipped a fix when the right reading was within 0.5% of any figure | Jubilant's ₹3,595 Cr and ₹6,715 Cr stayed ten times too large | a row's digits copied under its own name are a slip regardless (c798b67) |
| 5 | Memory took a card's balance-sheet figure with no scale check | Kanoria net worth ₹5,794.25 Cr (₹579) in memory; a later card said net worth fell 91% | refused when 3x off the other sources for the date, XBRL first (afc4657) |
| 6 | A results XBRL file tagged in the wrong unit was taken as exact | Jubilant FY24 at a tenth: cards said revenue +979% YoY | revenue and implied share count off by the same 10^k: put right (82830ff) |
| 7 | Notable changes, deal sizes and impact results computed in code were held as figures no row prints | Kanoria net debt "+₹246.77 Cr", SML deal ₹554.65 Cr | checked by arithmetic, sides' rounding carried; code-computed figures are sources (e4ea180) |
| 8 | A "% YoY" compared with the latest quarter's changes only, then with any period's | 29 correct YoY changes held across rounds 2a-3b; a wrong-period change could pass | compared with the YoY of the period it names, before or after it (e4ea180) |
| 9 | Quotes from two-column pages and table cells were not found | SML's SPA disclosure: 5 quotes held as "not in the filing" | a block-by-block reading kept for the quote checks (34b3942) |
| 10 | A quote differing by a word ("Lakhs" for "Lakh") held its card; a fact with no large figure was dropped for it | right cards held, a re-appointment fact dropped | nine words in ten in order: checked against that sentence, reported for style - not when a figure or "not" differs (34b3942) |
| 11 | XBRL YoY: the year-ago figure rebuilt from a rounded YoY, looked for at two decimals | the right YoY refused on most results cards | the earlier quarter's own figure, or a match within the rounding (97756e5) |
| 12 | The change fixer looked for whole-crore sides at two decimals | "₹494 Cr → ₹418 Cr, +15%" never corrected | each side at its own precision (97756e5) |
| 13 | An unreadable attachment: card from the headline, checks crashed (3 values for 4) | filing FAILED with a ValueError, for good after 3 runs | fails before any AI call with the reason; a no-attachment announcement reads its headline (7708fb6) |
| 14 | The homepage snapshot had no `held = 0` (also peer context and search, 3775918) | held cards shown on the homepage | filtered (7708fb6) |
| 15 | D20: a held owner kept the quarter; a not-material claim kept it | 19 quarters without a published results card | 9c26041 |
| 16 | Timeline repeat checks matched later entries too | an older filing duplicate of a newer one (1 of 174) | earlier entries only (41a67da) |
| 17 | A prompt over a model's tokens-per-minute was "paced" for ever | filing deferred on every run, never failed | that model skipped as unavailable (a0d0105) |
| 18 | A scanned page past the OCR cap was cached as read | never OCR'd on a later run | kept only when read (a0d0105) |
| 19 | A card held only for an unfound amount had needs_review = 0 | outside the review count and the scoring veto (76 of 118 held) | held implies needs_review (a0d0105) |
| 20 | A scan's own OCR layer under its image was taken as the PDF's text | Heritage's "Total e.-.:pcnscs" over RapidOCR's right label | a page an image covers is a scan (5187ff0) |
| 21 | Raw BSE/NSE answers never stored (the Worker refused raw/) | D28's raw store empty | prefix allowed (31968bb) |

## Still open, by expected gain

| Item | Evidence | Proposed |
|---|---|---|
| A fact's comparative from a far row holds a right card | CSB Q3FY25: "provisions rose to ₹16.53 Cr (from -₹4.54 Cr)" | calibrate against the 40/8/3 baseline: a two-decimal figure found in the filing at its unit is ~3% chance; report rather than hold above a precision bar |
| Pass 2 "not material" on substantive filings; reason not stored | Prism Preferred Bidder, stake sale; Novartis tax orders, court admission; 3 board outcomes | store pass 2's reason; review the 70 |
| Annual reports | 4 annual reports not material; 12 taken by the "AGM notice" rule | ANNUAL_REPORT event type with NSE's AR XBRL (to-do item 4) |
| Memory facts outlive a filing's reclassification | Kanoria's ₹5,794.25 Cr is still in memory from a filing now NOT_MATERIAL | forget a filing's facts when a re-run ends without a card |
| A duplicate of a filing that later fails for good stays a duplicate | 4 duplicates point at results filings still PENDING | re-queue duplicates whose original ends FAILED at max attempts |
| Repeats published as separate cards | SML's acquisition: 15 M&A cards, four the same day saying the same | tighten the same-event check for M&A within a day |
| "HELD" (garbled scan, human hold) does not hold a card, and is lost when a second opinion ran | CSB 3649405a published with the garbled-scan note | record held reasons on the card; decide whether HELD should hold |
| XBRL `confirm()` rejects a file whose figures are all zero | code reading | treat zero as unconfirmable, not wrong |
| Shareholding XBRL never arrives through announcements | every shareholding filing goes to noise; the seed reads NSE's | leave (memory gets it from NSE) or link NSE's file |

## Inventory: every discard, hold and overwrite, with its threshold

In pipeline order. P = `pipeline.py`. Thresholds that compare numbers are where rounding-type edges hide; each
is listed with its value.

**Ingest.** A BSE row without news_id or scrip is skipped silently (bse.py `parse_row`); a missing date takes
now. Paging stops at the total, a page with nothing new, or 400 pages. An attachment 404 on both paths, or over
30 MB (PDF) / 8 MB (XBRL), is treated as missing; NSE downloads are cut at max_bytes. Known news_ids are
skipped (P `_record`). Rules drop to the noise file (DROP, CALENDAR - a catalyst only for a future date - and
XBRL-only without a file); companies under ₹100 Cr market cap go to noise as outside the universe. A failed
discovery day is skipped; backfill stops at a weekday with nothing found (twice), 5 days a run, or 80,000 D1
writes.

**Rules** (rules.py, taxonomy.toml): first match wins in the order drop, xbrl_only, calendar, timeline,
fast_track; material-word vetoes on every DROP rule but the newspaper one.

**Queue and run control.** PENDING, or FAILED with fewer than 3 attempts, are taken. A run stops at its deadline,
on quota ceilings, after 4 filings in a row with every provider busy (each waited 3 x 60 s), after 3 attachment
refusals or 3 unreachable-site errors. A sink rejection sets a filing FAILED at max attempts at once. Gateway:
no key, a disabled model, a prompt over the context window or over the per-minute tokens skip a model; 95% of
a quota is a ceiling; 3 failures open a circuit for 300 s; invalid JSON gets one repair.

**Reading.** Scanned page: under 80 characters and an image. Unreadable: 2% control characters or 10% foreign
letters (150 characters at least). OCR: 20 pages a document (6 on the vision route); figure pages (15 amounts) 12
a document, kept only when OCR read 80% of the layer's amounts; a page 90% covered by an image is a scan. Text
budgets: pass 2 40,000 characters (x3 for a presentation), pass 1 2,500, timeline 6,000, duplicates 60,000;
boilerplate lines (160 characters or less) removed. A scanned document whose OCR failed fails.

**XBRL.** Looked for on RESULTS only; rejected when its latest revenue/PAT is not in the PDF at any unit
(rounded to whole, value at least 10); dimensional and non-standard-period facts skipped; first fact wins;
no change on a loss base; a file 10^k off the company's other quarters (log10 within 0.2, revenue and implied
shares agreeing, 2 other quarters) put right.

**Duplicates.** Exact or near text (5-shingle Jaccard 0.9, same numbers, 40 words, 3 days), corrections exempt;
same timeline event (10 days, word Jaccard 0.5, earlier entries only); pass 1's named repeat confirmed on a
dated entry within 15 days; fast-track repeat check for one-event-one-card types (10 days, last 8 entries); D20
one card per results quarter; same event in other words after pass 2.

**Pass 1 / timeline tier / pass 2.** Not material at pass 1; timeline-only lines; pass 2 not material or no card.
Schema-level drops of invalid list items and placeholders (models.py) are silent.

**Corrections on every card** (`ground()`): period labels shifted to the statement's; unit slips (amounts 10 Cr
and up, exactly one wrong scale fits, not within 0.5% of a real figure unless copied from its own row); change
percentages (both sides in the filing at their own precision; rewritten when off by more than max(1 pt, 5%));
deal size from shares x price (3%), dropped when it equals revenue, net worth or capital (0.2%); XBRL key
numbers (value change max(0.01, 0.5%); YoY only when the year-ago figure is in the filing).

**Checks.** Grounding score below 0.7, an unfound headline amount, an unsupported "first/record" claim, a scale
issue (profit above revenue x 1.02, a quarter 5x the last four, revenue under a fifth), a margin off by 1 pt, a
footing off by max(0.06, 0.2%), an impact formula off by 2%, a quote problem: all send a card to a second
provider; still failing (and not only a quote-style note) holds it. Quote checks: a figure in its own quote at
the right unit and the card's last digit; near-verbatim quotes (90%, 6 words, no turning word or figure
difference, 15% skipped); sibling rows within 2,000 characters reported, not held; YoY/QoQ within 0.6 pt of the
named period's changes. Integers of 31 or less are never checked.

**Held and published.** held = second opinion UNRESOLVED and not only style; held implies needs_review;
needs_review caps the score at 35. Feed, homepage snapshot, peer context and search all exclude held. Prices
older than 10 days are dropped; catalysts before the filing dropped; signals capped (3 shift, 2 overdue).

**Memory.** XBRL outranks a card; periods kept per kind (12 quarters, 6 halves, 4 nine-months, 6 years, 18
months); balance sheets 16 (a figure 3x off the date's other sources refused); ownership only at a quarter end
with promoter+FII+DII at most 100.5; predictions within 5x of the reference; flow figures whose halves and year
do not add up within 2% left out of the view; a seeded shareholding refused when NSE and XBRL differ by 0.5 pt.
