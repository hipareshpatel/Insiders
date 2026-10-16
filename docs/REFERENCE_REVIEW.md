# Reference repo review: practices worth taking

Source: https://github.com/Pareshking/NSE-BSE-Insider-Tracker, read in full on 2026-10-16 by four
reviewers (AI reading, data collection, clean layer and data model, UI and operations). Their repo
covers insider trades, deals and announcements; their cards are weak but their AI side does not leak
wrong figures. The review kept only what serves this project's goal: accurate, context-rich cards.
Detail per file is in the reviewers' reports (scratchpad, not kept); the practices are below.

**Main lesson.** Their accuracy comes from rejecting, not from better extraction. A 97% reader and an
80% reader both leak nothing because a strict code gate sits after the model. Our 95 wrong cards of
177 (docs/audit/) point the same way: a stricter gate, not a different model.

## 1. Accuracy gate (highest value; small pure functions, each with a regression test named after the real failing filing)

| Practice | How it works | Our error class |
|---|---|---|
| Unit next to the number | The model gives the number as written plus the unit word; code converts. A number already written out in full (299,99,99,852) cannot carry "crore"/"lakh". A unit must sit directly after the number in the quote. A figure with no unit but "15.5 billion" beside it is rejected. | unit slips |
| Unit heading block | A bare table figure counts only if the unit heading is in the lines just above it and no differently sized unit appears in that block (mixed-unit blocks rejected). | lakh/million tables, rating reports |
| Garbled-scan gate | Count digit tokens with letters inside ("2J9,51o"); at 25+ and 4% or more, hold every figure from that filing. | bad OCR text layers |
| Quote must be in the filing | Normalised substring match; a value's digits must appear in its own quote (4.5 never matches 45); headline and point numbers must come from their own quote. | invented facts |
| No column guessing | A "previous" value is accepted only when its quote has 3+ numbers and a comparison word (vs, from, year-ago); code computes YoY and QoQ, never the model. | wrong column, YoY/QoQ |
| Status and meaning guards | "Recommended" is not "approved"; "expected/estimated/potential" figures rejected; "shares of Rs 10 each" is not a price; turnover, net worth and share capital are never a deal size; a cancelled/terminated headline nulls the deal fields. | event types, invented sizes |
| Size guards | An amount outside a sane range is blanked and flagged; an issue amount outside 0.5x to 2x of shares x price is blanked; a power-of-ten test (10^2, 3, 5, 6, 7) against a reference value catches lakh/crore/paise slips. | unit slips in any event |
| Currency from the quote only | Never assume Rs; "USD 15.5 bn" must not become Rs. | currency |
| Dates as dates | 22.10.2026, 22nd October 2026 and 2026-10-22 compare equal; a claimed date not in the quote is rejected; identifiers (CIN, ISIN, DIN) must appear in the quote. | invented dates |
| Held, not shown | A failed check keeps the value with `shown=false` and a reason, counted per reason on the page; never silently dropped. | all |
| Human hold list | A text file, one line per card or field with a reason, applied at display; each hold becomes an automated check later. | known-wrong cards |
| Validate models on a hand-read set | Score "right and quote-backed" and log "wrong values that passed"; each leak becomes a check and is rescored over all saved replies. | model choice |

## 2. Context engine (our own build; their design is unbuilt, so only the discipline transfers)

- Link by identity, refuse on ambiguity: a conversion links to its original issue only when exactly one
  candidate exists in the window; zero or several means no link and a stated reason. Refuse when the
  converted number exceeds the issued number. Same pattern for order book before/after.
- Fill only when unambiguous; a sum is None if any line is missing, never a partial sum; never fill
  missing with 0 (they themselves use None with a reason code).
- Each context input carries value, as_of, source, basis in {filed, derived, rule} and a status or reason.
  Show the filing's two numbers plus our difference (stake 59.67% to 58.23%), never only our estimate.
- Point-in-time shares outstanding for dilution and market cap from shareholding XBRL (`total_shares`)
  or the exchange's share-count file; per-share figures need split/bonus adjustment with no look-ahead.
- Percent changes only where both bases are above zero; holding-change % only above a minimum base.
- Write each interpretation threshold with its calibration count and keep a rules version.
- Conservative name matching: merge only spelling and suffix variants; never by similarity.
- Amendments: key on content (entity, quantity-bearing fields) as well as the exchange's revision id;
  record the reason an earlier row was replaced; keep revisions as rows.

## 3. Data and operations

- Save the raw bytes (sha256, URL, params) before parsing, so parser fixes re-run without refetching.
- Per-item status (ok, pending, none exists, failed:reason); retry pending first; per-run cap; stop all
  workers on the first 401/403/429; compare counts with the exchange's own total for the day.
- PDFs: on a 404 under `AttachLive`, retry under `AttachHis` (BSE moves older files); check the size
  against the row's `Fld_Attachsize` and the `%PDF` magic bytes; keep text, not PDFs, for long storage.
- A restart loop continues only if something is pending, the last round made progress and nothing was
  refused, up to a round cap; concurrency groups; per-job timeouts; failure alerts (they have none).
- Tests from real payloads: fixtures are real fetched BSE/XBRL files with fetch date and provenance;
  a smoke test builds a whole data folder through the real pipeline and renders every page.
- Each script writes a small report JSON that the next step and the summary read.

## 4. Presentation

- Evidence tag per figure (in the filing / table row / calculated); a collapsible "the filing's own words".
- One place formats numbers (Indian grouping, Cr/L, em dash for unknown, "<0.01%"); the model never formats.
- "As of" is the latest filing in the data, never the wall clock; a coverage line per page.
- A data-quality section on the System page: rows removed or held per reason, and each check's counts.

## 5. Not adopted

- Their BSE client falls back to a disguised headless browser (spoofed identity, calls from inside a
  BSE page) after a block: that is evasion; ours stops on a block (CLAUDE.md rule).
- Calling BSE from non-Indian runners; the Parquet-in-R2 rebuild-everything model (D1 counts every row
  written); `fillna(0)` on sums; their NSE-only sources for results and shareholding XBRL (ours cover BSE);
  their 36 near-duplicate workflows and very long docs.
- Their validity measure ("quote is real") does not prove the right column or period.

## 6. Data sources they have that we lack (NSE unless noted; details in their `collectors/`)

Corporate actions (BSE `DefaultData/w`), bulk and block deals (BSE `BulkDealData_ng/w`), insider (PIT)
trades (BSE `Corp_Regulation_DownloadCSV_ng/w`), SAST Reg 29 (BSE `Corporatesast/w`, needs window
tiling), board meetings, buybacks, tender offers, preferential/rights/QIP details, index closes. Not in
their repo and ours: BSE results archive (`Result_Arch_ng`), BSE-side XBRL fetch.

## 7. Proposed build order

1. Accuracy gate (section 1): unit adjacency, unit-block, garbled-scan, quote and digits, column rule,
   status guards, held-with-reason, hold list. Then re-run the audit sample to measure.
2. History seed and raw store: results and shareholding XBRL back to 2023 from the results archive,
   raw bytes kept, per-item status, AttachHis fallback and PDF checks.
3. Context engine blocks (section 2) on that history.
4. Restart loop with a progress guard; fixtures from real data.
