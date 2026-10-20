# Using the AI better: a plan for card quality (2026-10-21)

Research and design only. No model was called and nothing live was written for this document. The live figures come from
the public API at 2026-10-21 00:58 IST (`/api/system`, and `/api/feed?range=7d` gave 100 published cards filed 13-20 Oct).
The evidence comes from the blind reviews in `docs/audit/live/` (live 1, 2, 3 and 5: 107 cards) and from review 6 (the
20 needs-review cards in the scratch folders, `review6/folders/*/findings.json`). It also uses the interpretation audit
(`interp-audit/results.md`, `blind_variantB.json`), the restatement diagnosis (`restated-report.md`) and
`docs/audit/needs-review-2026-10-20.md`.

The owner's question: other sites write better cards from the same filings, so how can we use the AI better (prompt,
input, process)? The System page also shows unused free daily quota, and about 5,000 D1 rows a day are kept spare.

## 1. What the evidence says

**Where the WRONG verdicts come from.** Across the 127 cards in live reviews 1, 2, 3 and 5 and review 6, 39 cards were
WRONG. Their issues by class: other 43 (mostly **scope**, meaning a segment, region or plant read as the whole company,
plus deal **stage** and blocks that do not belong), **memory** 29, **invented** 24, wrong_column 12, signal_verdict 12,
direction 12, arithmetic 11, wrong_period 10, standalone/consolidated 8, unit_scale 5, event_type 4. Grouped:

- **Reading errors**: the wrong column, period, unit, basis, scope or kind of amount. Examples:
  - Kanoria's and Star Health's restated year-ago columns.
  - Cyient's FY28-29 column read as FY31, and a segment's target read as the company's.
  - Airtel's 22 mn customers, which are Maharashtra & Goa only.
  - LIC's GST "INR 99,09,87,896" read as ₹9.91 Cr.
  - Ceigall's ₹608.67 Cr a year treated as the order's size.
  - Star Health's GWP growth given as revenue growth.
- **Interpretation errors**: a memory link misframed, a cause or consequence with no source, or the wrong rating action.
  Examples:
  - eMudhra's "upgrade" from A to A.
  - SBI Life's ordinary litigation provision tied to the IRDAI order.
  - Jubilant's exceptional swing "boosting" PBT.
  - Aarti's sibling filing called "the existing order book".
- **Code blocks**: in live review 3, 6 of the 7 WRONG cards came from code (deal guards, `results_snapshot`, the XBRL PBT
  tag), not from the model's words. In live review 5 it was 3 of 5. On current live cards the model's own share of
  WRONG is therefore about 2-5 cards in 59. The interpretive points are where it fails. Interpretive points that pass rule
  R are still **20% WRONG** (interp-audit, 4 of 20). Three of those four are memory links misframed.

**Who writes the cards.** Writers of the last 7 days' 100 published cards:

| Writer | Cards | Live-review verdicts (reviews 3+5) |
|---|---|---|
| Gemini 3.5 Flash-Lite (28 packed, 18 on `pass2_long`) | 46 | 8 WRONG of 46 (17%) |
| GLM-4.5-Flash | 24 | 2 WRONG of 5 |
| Nemotron 3 Super (NVIDIA) | 10 | — |
| Nemotron 3.5 Super VL | 5 | 1 WRONG of 2 |
| Gemini 3.6 / 3.7 / 3 Flash preview | 9 | 1 WRONG of 6 (preview); 3.6 and 3.7: 0 of 5 |

Round 5 arm B gives the same order on larger samples: 3.7 Flash 0 of 33 WRONG, 3.8 Flash 3 of 30.

**Where Gemini Flash's quota goes.** The best free writer is Gemini Flash (five models at 20 requests a day each). On 20 Oct
it served 62 requests, yet only 9 of the 100 cards filed in the last 7 days are Flash cards. The rest of its quota went to
backfill filings, which share the packed route with live filings (`pipeline.py`: `route in ("pass2", "pass2_bulk")` → packer).
Gemini's day starts at 12:30 IST, before the evening results flood. *Inference from the usage and feed counts, not
verified by query: check by counting Flash-written cards by filed_at against processed date.*

**Why long filings miss the packer.** The rendered pass-2 system prompt is **34.8-36.1 K characters**: 26.5 K of
instructions, a 5.6 K schema, and the event focus and sector lens. That is about 8.8 K tokens before any filing text.
`LONG_PROMPT_TOKENS = 12_000`, so a filing with more than about 12 K characters of text goes to `pass2_long`. That route
is never packed, so it spends one Flash request per filing, and when Flash is out it falls to Flash-Lite (18 of the 46
Lite cards). Live packs are small anyway (34 packed cards: 17 packs of one, 11 of two, 6 of three).

**What the model is given as memory.** `view_as_of` caps memory at 6,000 characters. Each metric line reads only
`"Q4FY25: 431.42 INR_CR"`, with:

- no basis (standalone or consolidated);
- no "as first reported" marker;
- nothing that says the filing prints this same period itself.

Same-event items in the timeline and deals carry no marker either. Heritage (a standalone XBRL figure beating five
consolidated ones), Kanoria, Star Health, Man Industries, Jubilant Agri, Kapston and Bajaj all failed on this
(`content-faults-2026-10-20.md`, `restated-report.md`, live reviews 3 and 5). When the view overflows, it falls from
6 periods to 4, then 2, then 1.

**What already exists and what was learnt.**

- The second opinion fires only on mechanical failures (`CardChecks.wants_second_opinion`): 82 of the last 100 cards had
  no review at all. A meaning error passes every check.
- A claim checker (`causes.py`) was measured and **not adopted** (F74). It asked a binary "is it stated?" over 60 K
  characters of filing, cut 73% of all claims, and caught only 8 of 27 that the agents flagged. Any critic must avoid
  that design.
- The few-shot slot (`_owner_examples`, STARRED/NOISE) exists, but only the owner's rated cards fill it.
- Of the 223 held cards, 140 are right (needs-review). Re-writing held cards with another model mostly re-trips the same
  checks: 30 of 31 cards sent back for wording came back unresolved (2026-10-18).

## 2. Free quota left today (snapshot 2026-10-21 00:58 IST)

Gemini's rows are its Pacific day, about 12.5 h old. Ceilings are 95% of the limit (`safety_ceiling`).

| Model | Requests (fail / 429) | Tokens in / out | Ceiling | Spare now | Fit for quality work |
|---|---|---|---|---|---|
| Gemini 3.5 / 3.6 / 3.7 / 3.8 Flash, 3 Flash preview | 2 / 14 / 19 / 8 / 19, several 429 "daily" | 1.2 M / 0.1 M | 19 each | **~0** | best writer; scarce |
| Gemini 3.5 Flash-Lite | 348 (57 / 0) | 6.86 M / 0.66 M | 475 | **~70** | main writer today |
| Gemini 3.1 Flash-Lite | 19 (3 / 0) | 22 K / 63 | 475 | **~450** | pass 1 and vision only; unused |
| GLM-4.5-Flash (Z.AI) | 213 (17 timeouts) | 2.5 M / 0.26 M | no daily cap configured (assumption: none) | **hundreds**, bound by its one-at-a-time slot (12-96 s a call) | different family from Gemini |
| Nemotron 3.5 Super VL (OpenRouter) | 528 (218 empty) | 10.6 M / 3.65 M | 950 shared by all `:free` | **~200**, unreliable (29% empty) | spare |
| gpt-oss-20b (Groq) | 89 (8) | 117 K / 10 K | 190 K tokens a day | **~63 K tokens** (~15 small calls) | tiny calls only |
| ministral-8b (Mistral) | 776 | 1.03 M / 41 K | 1 B tokens a month on the provider | ~30 M tokens a day | weak model; pass 1 |
| mistral-small-2603 | 0 (27 × 429 at 20 K TPM) | — | — | per-minute bound | vision |
| Llama 3.3 70B (Workers AI) | 4 | 40 K / 3 K | 57 K route, 150 K provider | ~14 K route | negligible |
| DeepSeek Flash (prepaid) | 362 | 8.4 M / 1.17 M | prepaid | seeding only | **not allowed on daily paths** |

**Usable for quality without touching the writers:**

- Gemini 3.1 Flash-Lite, ~450 requests (packable at 250 K TPM);
- GLM-4.5-Flash, several hundred short calls;
- OpenRouter, ~200;
- Groq, ~15 small calls.

**Unchecked free sources:** Groq's other free models, Mistral's larger models on the Experiment tier, and their limits.
*Assumption: check with `python -m bse_intel models --provider groq|mistral` and the providers' own pages before using
them.*

**Sizing.** For results season, size for **150 live pass-2 filings a day**: Q2FY27 results for 1,778 companies over about
5 weeks, plus calls and presentations. Today's live rate is about 30 a day.

## 3. The plan: eight changes in priority order

D1 rows: every AI-only step below stores its output inside the card's own `card_json`, which is written once at commit,
or in R2. So it adds **0 rows**. Only a re-run (change 7) costs rows: about 24.5 a filing, measured on run
20261020T235537 (490 rows for 20 filings analysed).

"Daily audit" below means the ledger routine in `docs/audit/ledger.md`: a blind review of a seeded sample of yesterday's
published cards, with issues classed and marked on or off the face. Two kinds of measurement are used:

- **Counters**: per-card fields that code writes into `card_json`. No AI.
- **Live split**: filings assigned to the old or new path by `hash(news_id) % 2` for 5-7 days. Each filing is processed
  once, so this is production, not an AI test. With about 60 audited cards per arm, a fall from 15% to 5% WRONG is
  visible.

### 1. Give live filings the best free writer

**What**

1. Hold back Gemini Flash's daily requests for live filings: keep 80% of each Flash model's daily ceiling for the live
   route. Backfill (`pass2_bulk`) gets Flash only after 21:00 IST and otherwise uses GLM and Flash-Lite.
2. Pack `pass2_long` filings too. Gemini's window is 1 M tokens and the packer's cap is 400 K characters. Pack only with
   other long filings, at most 3 to a pack. Alternatively, raise `LONG_PROMPT_TOKENS` for the Gemini packed route.
3. Gemini 3.5 Flash-Lite stays last, as the owner decided.

**Why**

- Live (reviews 3 and 5): Flash-Lite 8 of 46 WRONG, Flash 1 of 6.
- Round 5 arm B: 3.7 Flash 0 of 33.
- Round 6 failed (17% WRONG) because a spare wrote when Gemini ran out.
- 62 Flash requests on 20 Oct produced only about 9 live Flash cards in a week (§1).
- With 2.4 filings a pack, Flash's ~95 requests a day carry about 230 filings; with 3 long filings a pack, more.

**Quota**: none extra; a reallocation of Flash's ~95 requests a day. **D1 rows**: 0. **Effort**: S (gateway reserve
plus packer route; 1 day).

**Measured by**

- Counters: share of live cards written by Flash (today 9%; target ≥ 60%), and Flash requests per live card.
- Daily audit: WRONG rate by writer.
- The backfill's daily filings, so its pace cost is visible (owner decision A2).

### 2. Feed the model memory it cannot misread

**What it is.** These are changes to `view_as_of` and the user prompt, made in code only.

1. **Basis on every metric line, and one basis only.** Lines read `"Q4FY25: 431.42 Cr (consolidated, first reported
   2025-05-14)"`. Lines of the other basis are left out when the company files consolidated, the same rule as the
   content-faults fix to `_metric_entry`.
2. **Periods the filing prints are taken out of memory.** For every period column the filing's statement prints
   (found by `statement_quarter` and the comparative headers, or by change 4's table), memory's figure for that
   period is replaced by `"(this filing prints Q4FY25: use its column)"`. Restated comparatives can then never be set
   against the filing. The prompt already asks for this (92d0df4); code makes it impossible to get wrong.
3. **Same-event markers.** A timeline or deal item within 10 days that shares the counterparty or the amount is
   labelled `"SAME EVENT, another document of this filing"`. A CANCELLED item is labelled cancelled, and running
   totals leave it out (Ceigall's ₹4,293 Cr included a cancelled tender).
4. **Per-page headers in the filing text.** For example `[p.32 · "DET segment" · amounts in ₹ lakh]`, built from each
   page's first heading line and its own unit declaration. Today the one `_unit_note` covers the whole filing (LIC mixes
   rupees and lakh), and a segment slide carries no heading (Cyient, Magellanic).
5. **Budget.** Raise `budget_chars` from 6,000 to 9,000 and drop low-value metric lines first (the long tail of
   statement lines), so the core lines keep 6 periods.

**Why it should raise quality.** Memory is the second-largest WRONG class (29 issues). Standalone/consolidated (8),
wrong_column (12) and wrong_period (10) follow. Seven named cards fail exactly because memory offered a figure for a
period the filing prints: Kanoria, Star Health, Heritage, Man Industries, Jubilant Agri, Kapston and Bajaj. The interp
audit's commonest WRONG is a misframed memory link (3 of 4), and same-event markers address it. Scope errors (Cyient,
Airtel, Magellanic) need the page header the model never sees today.

**Quota**: none (about +1 K tokens of input a filing). **D1 rows**: 0. **Effort**: M (2-3 days; tests on the review
folders' stored memory and text, no AI).

**Measured by**

- Counters, no AI: per card, the number of memory periods withheld and same-event markers shown.
- On/off over stored cards: how many published figures quote a withheld period. These become dashes and need the owner's
  on/off audit only if anything is accepted more; this change only removes.
- Daily audit: the classes memory, wrong_column, wrong_period and standalone_consolidated per 100 cards.

### 3. A meaning critic from another model family, per point

**What.** After the checks and before commit, every point on the card's face goes to a critic: the headline,
`what_happened`, `why_it_matters`, takeaway, key numbers, deal stage and kind, and the rating action. For each point the
critic gets:

- the point and its quote;
- **±600 characters of filing around the quote**, not 60 K;
- the memory items it cites, with their dates;
- the page header from change 2.

It answers a fixed checklist with one enum per item: period matches / entity and scope match / basis matches /
direction and sign right / amount type (total, per year, limit, running total) / stage and tense as written / cause or
consequence stated (`stated_in_quote | stated_in_memory | not_stated`) / memory item a different event (yes | no |
same_event). It then returns `KEEP`, `NARROW` (a shorter text using only words and figures in the quote: "₹608.67 Cr a
year for 35 years", "in Maharashtra & Goa") or `DROP`.

Code then acts:

- A NARROW text goes back through the same grounding.
- DROP removes the point.
- A failing headline is rebuilt from the first kept fact, or the card is held.
- The critic never adds a fact. Changes 4 and 6 extend it.

**Why it differs from `causes.py` (not adopted: it cut 73% of claims).**

- It checks named dimensions on a local window, not "is it stated anywhere in 60 K".
- It narrows rather than cuts.
- Cause words are judged only on interpretive fields.
- It runs in **shadow for 5 days**: verdicts are stored and nothing changes on the face. The daily audit then compares
  its DROP and NARROW calls with the reviewers' verdicts on the same cards. It is enforced only when its precision on
  drops is ≥ 80% and recall on WRONG points is ≥ 50%. Owner: does a live shadow run count as an AI test? It processes
  each live card once.

**Why it should raise quality**

- Interpretive points that passed rule R were still 20% WRONG (interp audit); variant B's tighter rule got that to 1 of
  19 by cutting points.
- The review 6 WRONG points can each be decided from the quote and its window: eMudhra's "upgrade" (same grade before
  and after), Ceigall's annual charge, Cyient's FY29 vs FY31 column, Airtel's state scope, SBI Life's provision, and
  Jubilant's exceptional item "boosting" PBT.
- Today 82 of 100 cards get no second look at all.
- Writer and critic from different families do not share the same blind spots: GLM checks Gemini-written cards;
  Gemini 3.1 Flash-Lite checks GLM- and Nemotron-written ones.

**Quota.** At 150 cards a day with about 5 points each, ~4-6 K tokens a card:

- GLM: about 150 calls a day (about 75 min of its slot spread over 96 runs);
- or Gemini 3.1 Flash-Lite, packed 8 cards a request: about 20 requests a day of the ~450 spare;
- fallback: OpenRouter.

**D1 rows**: 0 (`card_json.grounding.critic`). **Effort**: M (3 days with the shadow plumbing).

**Measured by**

- Counters: KEEP, NARROW and DROP per card and per writer.
- Daily audit: WRONG on face, plus a stratum of 5 dropped and 5 narrowed points a day judged blind: was the critic right?
  The ledger row records precision and recall before enforcement.

### 4. Read before writing: a facts table first, then a card that cites it

**What.** The pass-2 reply schema changes order.

1. First a `facts` array. Each row carries:
   - `id`;
   - `label`;
   - `value_as_printed`;
   - `unit_as_printed` (copied from the column or page header);
   - `period_header` (the column heading verbatim);
   - `scope` (company / segment / region / subsidiary, with the heading words);
   - `basis`;
   - `amount_type`;
   - `quote` (the row or sentence).
2. Then the card. Each point carries `fact_ids` and `memory_refs`.

Code then:

- converts units from `unit_as_printed`, so the model never converts;
- canonicalises periods from `period_header`;
- checks each fact's quote;
- drops any card point whose facts fail;
- renders numbers on the face from the fact rows.

The filing's own printed comparatives in the table (`period_header` = year-ago or previous-quarter column) go into the
results block in place of memory's figures. That is the "larger change" that `restated-report.md` §3 says is needed to
show restated columns rather than dashes.

- Phase 1, one call: the same packed Flash call, with no extra request. The table adds about 1-2 K output tokens a
  filing; the packed route's 60 K output fits 6 filings.
- Phase 2, two calls, only if the audit still shows writer errors: the reader runs on Flash over the filing; the writer
  gets the table and memory (about 4 K tokens) on a cheaper model.

**Why it should raise quality**

- It separates reading from writing, which already worked once: results cards built by code from the XBRL table went
  from about 45% WRONG (rounds 3-4) to round 5 arm B's 10% overall (F74).
- Reading errors (wrong_column, wrong_period, unit_scale, standalone/consolidated and scope: about 45 of the 170 WRONG
  issues) are visible and checkable in a table row, and invisible in prose.
- Fact ids make "is this point grounded" exact, instead of searching the filing for loose numbers. This also targets
  the 76 false holds for a reworded quote (needs-review): a point that cites a fact whose quote is found is grounded,
  whatever its wording.

**Quota**: phase 1 none (+1-2 K output tokens a filing); phase 2 +1 cheap call a filing on 3.1 Flash-Lite or GLM. **D1
rows**: 0 (the table in `card_json` or R2). **Effort**: L (4-6 days: schema, `ground()`, `results_snapshot` taking
printed comparatives, tests).

**Measured by**

- Counters: share of face figures traced to a fact row (target 100%), facts with a failing quote, comparatives shown
  from the filing against those withheld.
- Live split for a week; daily audit classes for reading errors.
- On/off over stored cards for the results block (it shows more, so it gets the owner's on/off audit and an independent
  sample, as with `audit_quote_rules.py`).

### 5. A short per-event prompt, with worked examples from cards reviewers judged right

**What.** The rendered system prompt is about 35 K characters and has grown by accretion. Reduce it to **≤ 12 K
characters**.

- A shared core (ground rules, units, periods, quotes, tone) of about 6 K characters.
- **Only the current event type's module**: deal_value rules only for deals, call_read only for calls, rating rules only
  for DEBT_RATINGS. Memory-compartment instructions move to the facts step.
- The schema keeps only the fields for that event type.
- Remove the instructions that conflict:
  - Proportions: the headline is told "Put the figure in proportion when memory allows (18% of FY26 sales)", the ground
    rules allow "a simple share", and the SCALE rule says "work out no proportion of your own". Keep only SCALE. Cards
    show the cost: eMudhra's "18.4% of order book", Ceigall's "63% of Q1 revenue", Northern Arc's "108.3% of market cap".
  - `why_it_matters` says "Good insights compare… earlier orders" and `notable_changes` says "compare everything with
    memory", while the same-event and consequence rules forbid much of that. Keep the restriction; the invitation feeds
    the memory class, 29 WRONG issues.
  - `quantified_impact` says "wherever the sources allow, quantify… instead of saying may improve margins", with
    ASSUMPTION inputs. Make it opt-in, only when the filing gives every input (Ceigall's "per year over 3.0 years").
  - `core_catalyst` says "name the economic driver", which conflicts with "a cause only when the filing says it". Drop
    the field or fill it from code.
- **Few-shot**: 2 worked examples per event type in the existing `_owner_examples` slot, taken from cards that blind
  reviewers judged OK, each with its filing excerpt. Add one contrast pair from a WRONG finding, the reviewer's
  `card_says` against `pdf_says`: eMudhra's rating, Ceigall's annual charge, Cyient's column, Kanoria's restated
  column. Sources: the OK cards in live reviews 3 and 5 (16), round 5 arm B, and the interp audit's 16 RIGHT points.
  They are refreshed weekly from the daily audit's OK cards.

**Why it should raise quality**

- Most cards are now written by a Lite model (46 of 100), which follows a long rule list less well than a short prompt
  with worked examples. *Assumption: measured only by the live split below.*
- The "Mistakes our reviewers found" rules of 92d0df4 are rules without examples.
- Live review 5's impact_level errors (14 of 32 wrong, 12 too high) persist despite the LOW list in the prompt.
- A shorter prompt also keeps more filings under `LONG_PROMPT_TOKENS`, so more are packed on Flash (change 1).

**Quota**: saves about 6 K input tokens a filing (about 0.9 M tokens a day at 150 filings) and raises filings per Flash
request. **D1 rows**: 0. **Effort**: M (3 days; tests render each event's prompt and pin length and conflicts).

**Measured by**

- Live split by `news_id` hash for 7 days; daily audit WRONG and MINOR per arm, and impact_ok rate per arm.
- Counters: prompt characters per event type, and share of filings routed to `pass2_long`.

### 6. A second, blind vote on the enumerated fields; conservative when the votes differ

**What.** Inside the critic call of change 3, *before* it sees the card, the critic answers the enum fields from the
filing's opening and the facts table: event_type, deal stage and kind, the rating action per instrument (reaffirmed,
upgraded, downgraded, outlook revised, withdrawn, assigned), impact_level and tone. Code compares the two votes:

- They agree: kept.
- They differ: the conservative value is used. Lower impact; IN_PROGRESS rather than COMPLETED; BOARD_APPROVED rather
  than SHAREHOLDER_APPROVED; reaffirmed when the grade is the same; OTHER kept off RESULTS only by the code rules.
- A third vote on GLM or Groq runs only on a disagreement in event_type or stage.

**Why it should raise quality**

- Deal stage caused 4 of live review 3's 7 WRONG cards (ITC, Jubilant Agri, JUBLCPL, Orient Bell).
- impact_level was wrong on 14 of 32 cards in review 5 and 4 of 27 in review 3, nearly all too high.
- Rating actions: eMudhra and Capri.
- Event type: Jubilant's results classed OTHER, which also removed its XBRL path.
- Enums are cheap to sample, and "agree or go conservative" needs no matching of free text.

**Why not full-card self-consistency (option e).**

- Two full samples double the writer calls on the scarcest quota (Flash). On Lite, two weaker samples would replace one
  better one.
- Matching agreed points in free text needs yet another model call.
- Option e is not recommended for whole cards.

**Quota**: +200 output tokens in the critic call; a third vote on about 10-20% of cards (about 30 small calls a day,
GLM or Groq's ~63 K tokens). **D1 rows**: 0. **Effort**: S once change 3 exists (1 day).

**Measured by**

- Counters: disagreement rate per field and per writer.
- Daily audit: impact_ok rate, deal stage and event_type issues per 100 cards.

### 7. The Gemini end-of-day sweep: re-write only the cards a stronger model can fix

**What.** From 11:30 to 12:25 IST, before Gemini's daily reset, whatever Flash quota is left goes to re-writing cards,
packed. The queue, in order:

1. held cards whose hold reason is a true class (invented, wrong period or row, unit 10x or 100x, mixed basis,
   arithmetic);
2. published cards where the critic of change 3 dropped a headline or two or more points;
3. cards a GLM or Lite writer produced on a RESULTS or CONCALL filing.

Cap: **40 a day**. Held cards that are false holds (a reworded quote, a figure in another unit, derived figures: 152 of
the 223 held) are **not** re-written. That is a check problem, not a writer problem, and a rewrite re-trips the check
(30 of 31 cards sent back for wording came back unresolved).

**Why it should raise quality**

- Needs-review: 27 of the 29 WRONG cards were held, so the hold catches them, but nothing then writes them better.
- Flash quota left unused at the reset is lost.
- Option f, applied in bulk, would mostly spend quota on false holds.

**Quota**: Flash requests left before the reset (0 today; more once change 1 stops backfill draining it). Fallback
Gemini 3.1 Flash-Lite. **D1 rows**: about 24.5 a re-run, so 40 a day is **about 1,000 rows** of the 5,000 spare. Use
`requeue-failed --ids` semantics and a daily cap in code. **Effort**: S-M (2 days; reuses `requeue-failed`).

**Measured by**

- Counters: held → published by the sweep, and critic DROP counts before and after the re-write.
- Daily audit: a "re-written" stratum of 5 cards a day. Releasing a held card makes the feed accept more, so the owner's
  rule applies: an on/off check over stored cards and an independent sample before it is enforced.

### 8. Keep the evidence: raw replies, fact tables and critic verdicts per card

**What.** Store each pass-2 raw reply (the packer already keeps up to 20 K characters in `AIResult.raw_text`), the facts
table, the critic's checklist answers and both enum votes:

- in R2 next to the text cache, keyed by news_id;
- with a compact summary in `card_json.grounding`: writer, pack size, critic counts and votes.

The daily audit export (`scripts/audit_round7/export.py`) includes them, so a reviewer's WRONG can be traced to reading,
interpretation, the critic or a code block without re-running anything. The audit's per-class counts per writer go into
the ledger automatically.

**Why it should raise quality.** Today "raw pass-2 replies are not stored" (`content-faults-2026-10-20.md`), so a WRONG
cannot be told apart as the model's reading, its interpretation or a code block, except by hand. Every change above is
measured by this split, and the owner's no-AI-re-runs rule means stored evidence is the only evidence.

**Quota**: none. **D1 rows**: 0 (R2 puts: 1-3 a filing, well inside R2's free tier). **Effort**: S (1 day). Build it
with changes 1 and 3 so their first days are measured.

## 4. Order of work and the daily budget

| # | Change | Extra AI calls a day at 150 cards | Free source | D1 rows | Effort |
|---|---|---|---|---|---|
| 1 | Flash for live, pack long filings | 0 (reallocated) | Gemini Flash | 0 | S |
| 2 | Memory with basis, withheld periods, same-event markers, page headers | 0 | — | 0 | M |
| 3 | Meaning critic, shadow then enforced | ~20 packed requests or ~150 GLM calls | 3.1 Flash-Lite, GLM | 0 | M |
| 4 | Facts table first, cited by the card | 0 (phase 1) | same call | 0 | L |
| 5 | Short per-event prompt with few-shot | − (saves ~0.9 M tokens) | — | 0 | M |
| 6 | Blind enum vote | ~30 small calls | GLM, Groq | 0 | S |
| 7 | End-of-day sweep, ≤ 40 a day | ≤ 40 packed | Flash left over, 3.1 Flash-Lite | ~1,000 | S-M |
| 8 | Evidence per card | 0 | — | 0 | S |

Total extra: about 20-60 requests a day on Gemini 3.1 Flash-Lite (of ~450 spare), ≤ 150 on GLM and ≤ 40 sweep
re-writes. That is about 1,000 of the 5,000 spare D1 rows. Nothing touches DeepSeek or another paid route; DeepSeek stays
on `memory_seed` only.

**Build first:** 1 and 8 together (one day, measured from the next audit). Then 2, then 3 in shadow. Then 4 and 5 under a
live split, 6 on top of 3, and 7 last.

Each change gets a ledger row in `docs/audit/ledger.md` before it merges, with its counter and its audit class. A change
that makes the feed accept more (4's printed comparatives, 7's releases) also gets the on/off audit over stored cards and
an independent sample (`pipeline/scripts/audit_quote_rules.py` pattern).

## 5. Open points for the owner

- Does a shadow critic, or a live split, on live cards count as "AI re-runs for testing"? Each processes every filing
  once.
- Change 1 slows the backfill: Flash goes to live filings first (PLAN A2).
- Groq's and Mistral's other free models and their limits are unchecked (*assumption*). Checking them could add a
  stronger critic family at $0.
