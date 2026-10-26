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

## Measurement before the switch goes on (owner's Yes, 26 Oct 2026)

`call-memory --ids ... --out DIR` (maintenance, read only: reads the stored text and memory, calls the AI, writes the
points and every dropped point with its reason to the artifact, writes nothing to memory) on the 10 round-1 documents plus
10 new ones from a second export; the 10 new are read by fresh blind reviewers first. The comparer and the importance
grader are agents that did not build it. **Pass, set before the run:** at least 85% of important points kept, 2% or
fewer saved wrong, no unit error, transcripts and decks reported apart. Fail: the commonest missed class is fixed and the
same 20 are run again.
