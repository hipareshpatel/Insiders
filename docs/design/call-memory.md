# Call memory v2: what memory keeps from earnings-call transcripts and investor decks (TODO 83)

Owner, 26 Oct 2026: "What we are missing or not saving or incorrectly saving for transcript and presentations need a
complete overhaul ... use everything possible because this is one of most important task." Switch `MEMORY_CALL_V2`,
default off; on only after the measured pass below.

## Why (memory recall audit round 1, TODO 82, 26 Oct 2026)

Ten call documents (4 transcripts, 6 decks, 10 companies, 8 sectors) read whole by blind reviewers, 178 points, compared
point by point with memory:

- memory kept 39% of all points and 55% of the important ones (53 important points missed);
- the whole text already reaches the model (call budget 120,000 characters; the longest document was 74,000), so
  length is not the cause;
- **one AI reply writes the card and memory together** and asks for "8 to 15 takeaways"; reviewers found 11-26
  important points a document;
- **no place in memory** for dependence (customers, geographies, top brands), capacities and store targets,
  quantified risks;
- call points are saved **without page or quote**, so a later check cannot trace them;
- **opening remarks beat the Q&A**: Sobha's "much higher than 15% for the whole of FY27" was clarified in the Q&A as the
  second half of FY27; memory kept the first; its "towards 20% from FY28" was filed under Q4FY27;
- **two definitions under one name**: Sobha's statutory operating cash flow (-342 Cr, exchange file) and its own
  "operational cash flow" (+755 Cr) as sources of one metric; Vishal Mega Mart's EBITDA margin 12.1% (file) and its
  own operating EBITDA margin 7.7%;
- **unit errors**: APL Apollo's 10 lakh t target judged against 963,143 t (fixed separately, F179).

The analyst checklist (the equity-research skill files: what an analyst tracks from a call, what changed since the last
one, sector KPIs, what not to keep) is folded into the point types and the prompt below.

## Design

### 1. A separate memory reading of every call document

`call_memory.py`. After the card is written (live) or the memory-only reading (backfill) of a `CONCALL_PRESENTATION`
filing, with the switch on: one more AI call (free providers only, the bulk route; never DeepSeek on the daily path),
prompt `config/prompts/call_memory.md`, the document's whole selected text with page markers, the company's sector KPIs,
and the company's points from its previous call (up to 40) for "what changed". The card path is not touched. A failure
never fails the filing: the card stands, the call points wait for a re-run (`call-memory --ids`).

**Changed after the first measured run** (26 Oct, maintenance run 40306940769): the whole document in one request on the
long route got 67 points over the ten round-1 documents against the reviewers' 178, mostly from Flash-Lite with a
6,000-token reply. The document is now read in parts of whole pages of about 18,000 characters (3-4 requests a long
transcript), on its own `call_memory` route (Gemma 4 on Google's key and NVIDIA's free DeepSeek first, Gemini Flash only as
the last spare, so the cards' 20-a-day Flash quota is not spent). A figure in words ("three more", "our fourth") counts
as a figure; on a slide, where words sit in boxes, a quote whose every word and figure is on the named page is kept and
marked `quote_assembled`.

### 2. Typed points, each with page and exact quote

| type | what | key fields |
|---|---|---|
| `guidance` | a number or range for a future period | metric, value, value_high, unit, period, basis |
| `outlook` | a direction without a number, with its period | topic, direction, period |
| `commitment` | a dated operational or financial target management owns | value, unit, deadline |
| `capex_capacity` | capex amounts, capacity, plants, stores, commissioning dates | value, unit, period |
| `order_book` | order book, inflow, pipeline, backlog, executable period | value, unit, as of |
| `margin_driver` | why a margin or cost moved or will move, with its size | effect, period, recurring |
| `volume_price_mix` | growth split into volume, price/realisation and mix | value, unit, period |
| `dependence` | customer, segment, product, brand or geography concentration | share, of what |
| `kpi` | the sector's operating metrics (sectors.toml) and the company's own defined ones | metric, value, unit, period, definition |
| `risk` | a named threat, with size, trigger or window | exposure, window, mitigation |
| `catalyst` | a dated external or corporate event (approval, hearing, launch, ruling) | date or window |
| `capital_allocation` | acquisition, sale, fundraise, dividend policy, buyback, debt target | counterparty, size, status |
| `management_change` | a person joining, leaving or changing role (memory only; D30: no card) | role, name, date |
| `one_off` | exceptional gains or losses, provisions, restatements, with the line | size, line, recurring |
| `competitive_view` | market share, industry growth, rivals, imports, as the company says | figure, source |

Every point carries: `statement` (plain words, the figure and period as stated), `metric` (snake_case) and `topic` (a
short key that stays the same call to call, such as `fy27_revenue_growth`), `value` / `value_high` / `unit` / `period` /
`basis`, `definition` (only when the company defines the measure itself: "operational cash flow, collections less
construction and land spend"), `direction` against the previous call (`NEW | RAISED | CUT | MAINTAINED | WITHDRAWN |
REWORDED`, with the earlier point's id), `certainty` (`WILL | EXPECT | AIM | HOPE`), `condition` ("if steel prices hold"),
`speaker` (`MANAGEMENT | ANALYST`), `section` (`PREPARED | QA | SLIDE`), `page` and `quote` (copied exactly, short).

Not kept: greetings, introductions, safe harbour, call logistics, company background, routine reported figures the
results filing carries (revenue, profit, EPS, statement lines), adjectives with no figure or period, analysts' names,
anything about share price, valuation, ratings or estimates.

### 3. Code checks every point (no AI)

1. **Quote**: `gate.quote_found` against the document's text and its block reading; a point whose quote is not found is
   dropped, with the reason kept in the run report.
2. **Figures**: every figure in `statement`, `value` and `value_high` is in the quote (Indian commas, decimals and a
   `~` allowed); else dropped.
3. **Unit**: the quote's own scale word (lakh, crore, million, billion, %, bps, tonnes, MW, sq ft) must agree with `unit`;
   "10 lakh tonnes" is stored as `value 10, unit LAKH_TONNES` and also `value_base 1,000,000, base_unit TONNES`, so a later
   comparison is in one unit; a disagreement drops the point.
4. **Period**: the period must be named in the quote or within the 600 characters around it on its page; else it is set to
   null (`period_stated: false`), never guessed, and the point can never become a checkable target.
5. **Page**: the page is the one the quote is found on (corrected by code when the model named another).
6. **Q&A clarifications win**: a `QA` point on the same topic as a `PREPARED` or `SLIDE` point of the same document with
   another period or figure supersedes it (`superseded_by`); both are kept, only the later one is current.
7. **One fact once**: the same type, topic, figure and period within a document is one point with several pages.
8. **Company-defined measures stay apart**: a point with a `definition` never writes `financial_metrics`.

### 4. Memory: `call_memory`

`dossier["call_memory"]`: the checked points, newest call first, at most 600 a company (about eight quarters), each with
`id` (`cm_` + hash of company, filing, topic, period), `news_id`, `date`, `quarter` (the quarter the call discussed,
`call_summary.quarter_of`) and a memory label (`label("ai", "call", ok=True)` with page and quote). A re-run replaces
that filing's points. Nothing else in memory changes in this first build.

Also behind the switch, in `dossier.merge`: a figure a call or deck gives for a metric and period that an exchange file
already holds, more than 5% away from the file's, is not added as a source of that metric (the Sobha and Vishal cases);
the call reading keeps it as a `kpi` point with its own definition.

### 5. Later builds (after this one passes)

Guidance and commitment points with a stated figure and period feed `guidance` and `predictions` (judged with
`comparable_target`, F179); the stock page's call summary reads `call_memory`; "dropped topic" and slipped-deadline
signals from one call to the next.

**Changed after the second measured run** (26 Oct, maintenance run 40308409939): the free side models failed 8 of the 10
documents (Gemma 4 on Google's key HTTP 500 ten times; NVIDIA's DeepSeek timed out at 120 s on every long reply; Z.AI and
OpenRouter 429); the 2 read were far fuller than run 1 (Onward 18 points kept against 9, Sobha 16 against 6). Gemini Flash
(3.8, 3.7, 3.6, 3.5) is now first on the route with a 32,000-token reply and a 300 s wait, one request a document up to
60,000 characters. Before the switch goes on: (1) the reading leaves the 15-minute pipeline run (a queued job of its own,
so a slow reply never holds the cards), and (2) its Gemini requests move to a project of their own (owner's offer, 26 Oct),
so they never share the cards' 20-a-day Flash quota.

**The queued job** (built 26 Oct, behind `MEMORY_CALL_V2`, default off; with it off nothing changes). With the switch on the
pipeline step makes no AI call: it adds the filing's news id, scrip code and filing time to a queue kept in the sink's kv
table (`call_queue.py`). The kv table cannot list or delete, so the queue is two sets of keys with one writer each:
`callmem:q:<UTC day>` (the pipeline only: a read, add and write of one key under a lock, re-read just before the write; the
pipeline runs one at a time) and `callmem:s:<UTC day>` (the job only, one at a time: done, gave_up or retry with an attempt
count and the reason). A filing is pending until its state is done or gave_up for its latest enqueue, so a re-run of a
filing queues it again. The job looks back 14 days. `call-memory --pending [--apply] [--time-budget S] [--limit N]` reads
the queue oldest first with the same per-document code as `--ids`; a filing leaves the queue only after its points are
written (an empty reading counts) or on a permanent failure (no stored text, not in the ledger, an invitation) with its
reason; a transient failure (every provider failed, a write error) leaves it queued with an attempt counted and is given up
after 3; at the time budget it stops and exits 124 (filings left). Without `--apply` it reads and changes no queue state.
`.github/workflows/call-memory.yml` runs it every 30 minutes in its own concurrency group (never cancelled), skipped unless
the repository variable `MEMORY_CALL_V2` is `1`, with `GEMINI_API_KEY_3` and `NVIDIA_API_KEY` only (the cards' Gemini keys and
DeepSeek are not passed). The gateway builds without the base `GEMINI_API_KEY`: `gemini_3` is live on its own key, takes the
Gemini entries of the `call_memory` route, and (fixed with this job) is not held back by the cards' live reserve, because its
quota is its own.

## Measurement before the switch goes on (owner's Yes, 26 Oct 2026)

`call-memory --ids ... --out DIR` (maintenance, read only: reads the stored text and memory, calls the AI, writes the
points and every dropped point with its reason to the artifact, writes nothing to memory) on the 10 round-1 documents plus
10 new ones from a second export; the 10 new are read by fresh blind reviewers first. The comparer and the importance
grader are agents that did not build it. **Pass, set before the run:** at least 85% of important points kept, 2% or
fewer saved wrong, no unit error, transcripts and decks reported apart. Fail: the commonest missed class is fixed and the
same 20 are run again.

**Changed after the third measured run** (26 Oct, maintenance run 40314304047; independent comparison against the blind lists
of round 1). The result was a FAIL:
- important points kept: 38.1% over the ten documents, 45.1% over the eight read, 69.2% on the pages actually read;
- saved wrong: 1.62% (3 of 185 kept);
- unit errors: 0.

The causes and the changes:
1. **Parts never read (29 of the 45 important points missed).** The cards' Gemini keys were at their daily ceiling or held
   for live cards, and the free spares timed out. The run started before the third key was wired in; run 4 uses it
   (`GEMINI_API_KEY_3`, `only_routes`).
2. **The figure check dropped 99 true points of 107** for the 4 it rightly stopped. The quote was a slide heading, a table
   cell or the answer without its number: APL Apollo's 8 Mn Ton by FY28 under "Capacity Expansion Plan By FY28", Eris's
   +100 bps levers, Sobha's Chandivali INR 1,000 cr in the next sentence. A figure now counts when it is in the quote or
   within `CONTEXT_CHARS` of it on its page (a slide: the whole page). Such a point is marked `figure_beside_quote`, so its
   saved-wrong rate can be measured on its own; it is the risk the comparison found once, APL's 64% given the wrong label.
3. **A model's wrong `value_base` dropped true points** (Sobha's 12 million sq ft). Code now works the base figure out from
   the value and the scale word and never drops for it.

Review of that change (re-run on the 113 points the third run dropped): it kept 73, but two of the four rightly dropped
leaked (APL's 64% on the quote "64% 19%", Eris's 37.3% on "37.3%"), and 31 true table rows were still dropped by the unit
check, whose scale word stands in the table heading. So: a quote with no word of three letters (figures alone) is dropped;
the whole slide is the context only for an assembled quote (other slides: the 600-character window); the unit check may
find the scale its unit names beside the quote (a number followed by a scale word is still read in the quote). On the same
113: 67 kept, the four wrong ones all dropped again; 14 points kept before are now dropped (bare-figure quotes such as
Sakar's "30+", "40", "18", which cannot prove their label). Left: a date such as "as at September 26" read as the figure 26.

Not changed yet: dependence, mix and risk points not taken where the page was read (4 of the 45). This is the next prompt
change if run 5 still misses them.

### Run 5 (maintenance run 40326324044, 26 Oct 2026, 18:25-20:12 IST): FAIL on recall

10 documents asked, **5 read, 5 failed**: every model on the free route answered server errors (InternalServerError, then
circuit open) for nse-106828232, 106828285 and three more; nothing of ours. The 5 read gave 55 points; the checks at the
current head keep 52 (4 unit drops of the run are kept now). Scored by an independent agent against the blind keys
(`scratchpad/review5/score.md`; one key per filing, 39 important reference points graded by that agent):

| Bar | Result | |
|---|---|---|
| Important points kept, ≥ 85% | 24 of 39 = 61.5% (72.7% without PNG Sreva) | FAIL |
| Wrong, ≤ 2% of kept | 1 of 52 = 1.9% (VMM: "3,000 small-format stores"; the 3,000 are large-format) | pass, at the edge |
| Unit errors, 0 | 0 (every value_base recomputed) | pass |

Why the 15 important points were missed:
- **13 never asked for or never returned by the model** (47 of all 50 misses): risks, one-offs and dependences above all
  (one risk point in the whole run; ERIS exceptional items ₹36 Cr; ABREL PAT from discontinued operations; VMM festival shift
  Q2 to Q3; PNG Sreva parent dependence and gold price risk). This is the reading, not the checks: the next fix is the ask.
- **2 dropped by the quote check, both true** (PNG Sreva page 25, checked by the lead against the text): the slide is two
  columns read straight across, so each sentence is split by the other column's words; and the model gave page 24, the
  slide's printed number. Fix class: look on the cited page and the next, and match a quote across a two-column line split.
- 1 minor dropped by the unit check (ABREL portfolio GDV ₹77,718 Cr; "Cr" is in the table heading, not the quote).
