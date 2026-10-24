# Code audit of `main`, 24 Oct 2026 (evening)

Asked by the owner: a systematic audit of the whole code on `main` (after #97-#99), finding defects and judging whether
each existing flow does what it is meant to. Six independent read-only reviewers, one per area; the lead session then
re-checked the main findings in code. **Nothing was changed: every fix below waits for the owner's go-ahead.**

Status of each finding:
- **Confirmed**: reproduced or read in code by the lead session.
- **Reported**: reproduced by its reviewer (script or code trace), not yet re-run by the lead.
- **Uncertain**: needs data to confirm.

How to read it: section 1 is what makes cards wrong (the go-live bar), section 2 what wastes quota or loses work,
section 3 the site and operations, section 4 the verdict on each flow, section 5 a proposed order. Every accuracy fix
needs the owner's rule: on/off over stored cards, and an independent blind sample for any check that accepts more.

---

## 1. What makes cards wrong or MINOR

| # | Finding | Status | Effect | Fix | Measure |
|---|---|---|---|---|---|
| A1 | **The number check accepts digit prefixes**: `gate.numbers_in_quote` (`gate.py:318`) accepts a figure whose digits start or are the start of any number in its quote, period labels included ("Q2FY27" adds 2 and 27). "₹29.4 a share" passes against "9.42", "1,95,000 units" against "19,500", "95" against "951.96" | Confirmed | 10x slips in EPS, per-share amounts, counts, tonnes, MW published as checked | exact digits only; strip period labels from the quote first (rounding is handled later) | on/off over stored cards; stricter, so it moves some points behind the tap |
| A2 | **True points pruned by normalisation gaps**: "lakh crore"/"thousand crore" read as lakh/thousand (`gate._unit_after`, `gate.py:356`); short quotes fail on a ":" or "₹ 1,095" spacing (`quote_near`/`quote_scattered` refuse under 6 words); a filing with two declared units (press release in crore, statements in lakh) gives no unit, so the card's own "(3,779.80 lakh)" fails; the prune matches key numbers by label only (two "PAT" tiles both go) | Confirmed (lakh crore); Reported (rest) | most of the 32 of 34 true points pruned on 23-24 Oct (PNB, Bajaj Housing, KSOLVES, NTPC) | normalise the unit words, punctuation, the card's stated unit; match a key number by label and value | `scripts/audit_quote_rules.py` over stored cards; accepts more: blind sample |
| A3 | **A foreign amount stated as rupees passes every guard**: "₹8.64 Cr" against "SEK 86.4 Mn" passes `numbers_in_quote`; SEK is missing from `grounding._FOREIGN`; three different currency lists exist | Confirmed | KPIL's WRONG card; the wrong amount also enters memory | one shared currency list; a figure after a foreign currency gets no crore conversion | on/off over stored deal cards |
| A4 | **A call or deck card overwrites the results filing's margin and FY/H1/9M figures in memory**: live XBRL figures are stored under the filing's id (not `xbrl:`), so they get no priority; `QUARTER_OWNED` protects only quarterly flows and EPS; a call's segment margin 13.2 replaces the group's 9.7, its "total income" 1,400 replaces revenue 1,000 | Confirmed (repro) | Cyient's wrong margin; the next card's comparative and "restated" note are wrong | live tagged sources count as XBRL; a call/deck card fills only metric-periods memory lacks, margins and every period kind included; refuse a margin that disagrees with EBITDA/revenue by > 1 point | census over stored dossiers: entries a non-results card wrote over a results source |
| A5 | **A call card's table shows comparatives that were never restated**: `xbrl.add_comparatives` adds old files' year-ago figures, `_apply_xbrl` puts them over the card's restated comparative, and `call_results_snapshot` passes no printed text to catch it | Reported | Geojit / Man Industries class | skip old-file comparatives where the filing printed one; pass the results filing's text to the call snapshot | compare stored call tables with the quarter's results card |
| A6 | **The prompt rulebook contradicts itself and invites the MINOR classes**: `events.toml` tells the model to compute YoY, MoM, shares of revenue/net worth and "330 operating days" while `pass2.md` forbids it; milestones and catalysts may be "stated or clearly implied" (`pass2.md:272-277`); "the driver … what moved it" against "no cause unless stated"; HIGH is "likely to move the stock" with no tie to size; sector "drivers" lines hand the model ready causes | Confirmed (events.toml, "clearly implied") | unsupported causes, invented milestones, generous impact: about 40% of cards MINOR | remove the compute lines from `events.toml`; "stated" only; each risk, catalyst and milestone needs a quote or memory id code checks | live cards only (owner rule): MINOR by class, pooled (`rates.py`) |
| A7 | **Code inflates impact and case stages**: `case_stage` reads `why_it_matters` and misses negations ("does not expect a warning letter" marks the warning letter reached, then HIGH); the scale block and the HIGH rule ignore `signals.misfires` and the deal stage (bank limits on a rating card, an open offer where the company is the target, a recap, an L1/MoU/proposed deal all sized as firm); a rating outlook compared as free text ("Stable" vs "Stable outlook reaffirmed" is a change, HIGH); keywords ("existing", "grant") lift LOW cards to MODERATE | Confirmed (case stage); Reported (rest) | generous impact, case steps marked reached, wrong HIGH cards | case stage from the headline and quoted facts only, with wider negations; misfires and a firm stage in the scale block and HIGH rule; outlook by keyword; keyword boosts only for CAPEX/FUNDRAISE | recompute impact over every stored card (all inputs are stored, no AI, no PDF); blind-sample the changes |
| A8 | **Guidance "MAINTAINED" passes with any guidance in memory** (`reconcile_call_read`, `pipeline.py:1783`), of any age, though the call gives none | Reported (two reviewers) | Persistent, Urban Company | MAINTAINED/RAISED/LOWERED need this filing's guidance or a verified guidance takeaway; else NONE | over stored call cards |
| A9 | **Results cards lose the model's risk facts**: with a tagged XBRL file, `results_card.build` replaces `what_happened` and blanks `notable_changes` and `quantified_impact`, so an insolvency petition, an auditor's emphasis of matter or a regulator's order the prompt asks for is dropped; only the model's "why" points survive, which is where unsupported causes sit | Reported | true risk facts missing from results cards | a quote-checked `risk_notes` field code keeps; a short results-only instruction | share of live results cards whose filed risk note reaches the face |
| A10 | **The face shows two kinds of unchecked content as checked**: a fact whose quote was not found but whose figures were keeps its quote and is shown as verified (`cardText.verifiedFact` checks only that a quote exists); key-number tiles are shown with no quote check | Reported | unchecked text among the checked points | the pipeline clears the quote of such facts (or the face drops facts named in `quotes_paraphrased`); tiles follow the same rule | count published cards with such facts on the face |
| A11 | **refresh-card-blocks only adds**: a block computed from the card itself (case stage, scale) is never removed, and impact is only ever raised (`card_refresh.py:83, 187-200`) | Reported | Muthoot Microfin stays HIGH with "Rating moved 9 notches" in its reasons after its rating block was healed | let such a block become empty; recompute impact both ways | dry run's diff |
| A12 | **No code checks causes**: `causes.py` is never called by the pipeline | Confirmed | unsupported causes reach the face unchecked | wire it as a MINOR class check, or rely on A6 | live cards |
| A13 | **The results XBRL catch-up only ever checks the 60 oldest cards**: `results_cards_recent.sql` sorts oldest first and every row, up to date or not, uses one of 60 slots (`event_catchup.py:131-140`) | Confirmed | in results season newer cards made from the PDF alone (wrong basis) are never re-read; ~6-8 min of NSE calls a run spent on the same 60 | select only cards that could be due, newest first, count companies | read-only count of due rows past position 60 |
| A14 | Smaller: `results_card._CHANGE` uses `[+-−]`, a character range that matches almost anything ("~2.7%" breaks the call check); the "issuer not cooperating" veto matches " inc" inside "includes" (`scoring.py:280`); `rating_signals` compares outlooks across agencies; the NBFC lens matches AMCs, exchanges and CRISIL | Confirmed (first two) | crash or wrong veto on edge cases | `[+\-−]`; `\binc\b`; same-agency; narrower lens match | unit tests |

## 2. What wastes quota or loses work

| # | Finding | Status | Effect | Fix |
|---|---|---|---|---|
| R1 | **The long-filing test counts the instructions**: system + user characters / 4 > 12,000 (`pipeline.py:3617`), and the long system prompt alone is ~41k characters, so nearly every long-prompt filing goes to the long route | Confirmed | packs of 3 instead of 6 (half the cards per Gemini request); fallback to `pass2_long`; the short/long comparison is confounded (short and long go to different writers) | test the user part (memory + text) only |
| R2 | **One bad answer fails a whole Gemini pack**: `PackedItem.answer: dict` rejects a null; the gateway then repairs the whole 6-task reply, then tries the next Gemini model | Confirmed (type) / Reported (effect) | up to 2 requests on each Gemini model of 19 a day, then 6 filings fall back | accept any answer and drop the bad one; no repair on the packed route |
| R3 | **Live-window filings run as backfill when the same company files today**: `_live_jobs(window_start=today)` takes yesterday's pending window filings as history, `bulk=True` | Reported | best writers left to backfill, long prompt only, critic skipped | history only before the live window |
| R4 | **MD/CEO/CFO exits and auditor changes wait 90 minutes for an XBRL file that is never read** (the management family is filtered out of candidates but not returned early) | Reported (code read) | a 90-minute delay on exits the owner wants carded | return at once for that family |
| R5 | **AI calls repeat during the 180-minute results XBRL wait**: pass 1 or the timeline call runs before the wait, which leaves the route unchanged | Reported | the same call up to ~12 times a filing | check for a results statement and the wait before pass 1 / timeline |
| R6 | Gemini usage booked on the wrong quota day when the 12:17 IST run crosses Gemini's 12:30 reset | Reported | later runs think part of the new day is spent | book by the request's own time |
| R7 | **refresh-card-blocks writes back memory it read hours earlier**, with no re-read (`card_refresh.py:174-176, 235-237`); it runs beside the pipeline | Reported (two reviewers) | memory a live card or a sync wrote during the walk is lost | re-read and `keep_concurrent_writes` before each write |
| R8 | **`keep_concurrent_writes` (F113) drops the other writer's edits to existing entries**: only new keys are added when both changed a keyed list; a seed's added source on an existing figure is lost | Reported (repro) | a gap in today's fix | merge entries a level down by key |
| R9 | The annual-report catch-up switches paid providers off for the rest of the run (`annual_catchup.py:156-162`) | Reported | the DeepSeek seed/drain loses its writer for the evening | restore in a `finally` |
| R10 | **Point-in-time figures**: market cap and returns multiply raw old closes by today's share count (wrong across a split or bonus; `corporate_actions.share_factor_after` exists and is unused); the SCALE block uses today's market cap for an older filing | Reported | wrong "x% of market cap" on backfilled or re-run cards | apply the split factor; pass the point-in-time price to `scale_block` |
| R11 | Predictions are never created in a backfill or call seed (the "figure already in" test reads the whole dossier, not memory as of the filing) | Reported | the credibility loop is empty for history | test against `dossier_as_of` |
| R12 | Memory compartments with no cap (guidance, open watchlist, upcoming events) and `_forget` residue (call points, standalone, repeated guidance) | Reported | slow growth; re-read residue | caps; forget by news id |

## 3. Site and operations

| # | Finding | Status | Fix |
|---|---|---|---|
| S1 | **Taking back a RIGHT leaves a held card public**: `owner.ts:107-117` restores the stored held flag only after a WRONG; RIGHT then MINOR or CLEAR keeps it published | Confirmed | restore `prior.held` after a RIGHT too |
| S2 | **CI never runs the web tests** (`ci.yml` runs typecheck and build only) | Confirmed | add `npm test` |
| S3 | Calendar catalysts are written for companies outside the universe or not in the master | Reported | write them after the universe checks |
| S4 | The owner's verdicts and Star/Noise (`card_verdicts`, `card_feedback`) are in no backup | Reported | add them to the weekly export |
| S5 | The System page states the paid plan and a 500 MB cap as fact; the footer shows a stuck RUNNING run as "healthy (running)" with no date | Reported | read the plan from `D1_PLAN`; mark old runs stopped, show the date |
| S6 | The homepage snapshot is rebuilt only at the end of a run (a card held mid-run stays up to ~40 min) | Reported | acceptable; rebuild after a hold if it matters |

## 4. The flows: do they need correcting?

| Flow | Verdict |
|---|---|
| Live first, then the window, then the backfill by market cap | **Fine**, apart from R3 |
| Rule book (drop / calendar / fast track / pass 1) | **Fine**: 17 NSE subject cases classify as designed. Risk: a generic "Change in Management" subject hides an MD/CEO exit from the D30 exception |
| Duplicates: identical documents, pass 1, the repeat check, one card per results quarter (D20) | **Fine for identical documents and D20.** Needs a deterministic rule for one event in different documents (results + press release + deck, same quarter, within days): the open duplicate class |
| XBRL wait and catch-up | The event catch-up is **fine**; the results catch-up is **broken in season** (A13); R4 and R5 waste time and quota |
| Retries and deferrals | **Fine** |
| Quote checks and prune | **Needs correction**: they cost more than they save (32 of 34 pruned points true). Fix the normalisation gaps (A2) and the loose prefix match (A1) together, measured |
| Number fixers (unit slips, change %, count millions) | **Fine**; their guards hold. Gap: currencies (A3) |
| Second opinion | **Needs correction**: it adopts the whole second card (headline, impact, deal) but only numbers and quotes are re-checked; CORRECTED cards were 6 of 21 WRONG (29%) against 21% unreviewed. Skip it when only quotes fail (prune instead), and keep the first card's deal and impact unless the issues named them |
| Hold / prune / publish | **Works as designed**; a card whose second opinion was skipped or failed (UNCHECKED) is published flagged — the one audited was WRONG |
| Impact (score bands and the clear-event rule) | **Needs correction** (A7) |
| Memory: time-travel view, idempotent re-reads | **Fine for figures**; leaks in prices and predictions (R10, R11) |
| Memory: which source wins, scope labels | **Needs correction** (A4, A5): no scope field at all, and model-read call figures can replace results figures |
| Prompts | **Needs correction** (A6): one rulebook without contradictions; the long prompt is ~41k characters |
| Writer weights by measured WRONG | **Cannot work today**: the audit records have no writer field, so WRONG per model cannot be measured. Add the model, route and pack size to the audit rows |
| Site: verified face, "Our reading", owner verdicts, caches, D1 budget | **Fine**, apart from A10 and S1 |
| Workflows and concurrency | **Fine**, apart from R7 and a thin nightly pause margin |

## 5. Proposed order (for the owner to approve, item by item)

1. **Deterministic accuracy fixes with small blast radius**, each with its on/off over stored cards:
   - A3: currency.
   - A7: case-stage negation.
   - A8: guidance MAINTAINED.
   - A14: the regex, " inc" and the same-agency outlook.
   - A4: a call card may not overwrite results figures.
2. **The quote check** (A2 then A1), measured together, with a blind sample.
3. **The prompt rulebook** (A6) and results risk notes (A9), measured on live cards.
4. **Quota and lost work**, no accuracy risk:
   - R1: the long-filing test.
   - R2: a bad pack answer.
   - R4: the management-family wait.
   - R5: repeated calls during the results wait.
   - R7 and R8: memory writes.
   - A13: the results catch-up.
5. **Site and ops**:
   - S1: taking back a RIGHT.
   - S2: web tests in CI.
   - S3: catalysts outside the universe.
   - S4: backups.
   - S5: the System page.
6. **Measurement**: add the writer, route and pack size to the audit rows, so writer weights can follow measured WRONG.
