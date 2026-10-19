# Context engine: what we build, what we defer, what we reject

Input: a long design note from the owner (2026-10-16) on making every announcement carry the company's
history, sector economics and materiality. Decisions below are the engineer's (the owner asked for
accept/reject). It builds on docs/REFERENCE_REVIEW.md and the card-vs-PDF audit (docs/audit/).

## Accepted (the spec)

**Five questions for every material event.** What happened (verified event, values, dates, parties);
what was the position before (the baseline from memory); how material is the change; how does the
sector change the reading; what remains uncertain (missing, conditional, conflicting, next milestone).

**Rule of the engine: Python decides arithmetic, the AI explains.** Deterministic functions compute
before/after, relative size, dilution, growth; the model works from structured facts with provenance and
never infers an undisclosed balance or fills a gap with a plausible number. The gate (gate.py) and the
unit/XBRL fixes already enforce half of this.

**Provenance on every number.** Source filing, reporting period, publication date, unit, currency,
standalone or consolidated, and a status: known (reported), calculated (derived from known inputs),
estimated (stated assumptions), unavailable, conflicting, stale. The last reported value is never shown
as the current state (a March debt figure is not October's). A comparison across different bases or
dates is not shown; "comparison unavailable" is.

**Headline rule.** A context headline ("₹500 Cr order, 50% of TTM revenue") only when both values and the
period are verified; otherwise a precise factual headline. Never invent a ratio to look insightful.

**Materiality as several ratios, not one score, and never forced bullish/bearish.** Financial (value vs
revenue, assets, market cap, equity, cash flow), operational (capacity added vs installed, order vs
sales, stores vs network), balance sheet (debt repaid vs borrowings, new shares vs existing),
strategic/governance (control, key management, auditor, regulator). Direction stays "unclear" unless the
evidence settles it.

**Event-linked memory as structured ledgers** (source of truth), the model only interprets: orders
(exists: deals with stages and updates), plus debt position, equity instruments (warrants: issued,
converted, remaining), projects (planned cost, capacity, milestones), ratings history, management
tenure, operational events (a shutdown resolved by a restart). A follow-up updates its record and shows
what changed since the last verified state; a cancellation reduces an order, a repayment is not a
refinancing or a fresh draw (no double counting). Lifecycle states are kept apart: announced, approved,
signed, completed, commissioned.

**Event calculations**, per the note: debt (before, after, % reduction; net debt only when cash is known;
interest saving only when the rate is disclosed; not for banks and NBFCs, whose funding is the business,
where capital adequacy, cost of funds and asset quality apply); orders (order vs TTM revenue, opening and
pro forma order book only when the opening book excludes the order and definitions match, firm order vs
LoI/L1/framework kept apart); results (YoY and QoQ, margins, other income, one-offs, cash conversion over
several periods, seasonal comparison against the same quarter); fundraise (size vs market cap, price vs
reference, shares before and after, promoter participation, use of proceeds, approval stage; new shares vs
a transfer; warrant conversion remaining); M&A (value vs acquirer size, stake in percentage points, funding,
a stake above 50% is not loss of control); capex (existing vs new capacity, phases kept apart, cost,
remaining spend, commissioning date, plan vs earlier announcement).

**Source hierarchy.** Original exchange filings, XBRL, annual reports, presentations and rating rationales
first; a news article may help discover context but never supplies a material number.

**Sector layer**, starting where the economics differ most: banks and NBFCs (credit growth, NIM, GNPA,
capital, funding), EPC and capital goods (order book, execution, working capital), IT (TCV vs ACV), pharma
(approvals, mix, inspections), power and renewables (awarded, PPA, financial close, commissioned),
cement and metals (per-tonne economics). Our `sectors.toml` lenses and footer metrics already exist; each
playbook extends its lens and the calculations it unlocks.

**Evaluation.** A fixed evaluation set of real filings across sectors and event types (the audited cards
are the seed), scoring numerical accuracy, context coverage, source traceability, event continuity, sector
relevance, uncertainty handling; every change is re-measured against it.

## Staged build (acceptance per stage)

| Stage | Deliverable | Done when |
|---|---|---|
| 1 | History seed: results and shareholding XBRL back to 2023, raw bytes kept, per-item status | memory has correct periods, units and basis for every priced company |
| 2 | Debt and capital structure: debt ledger, share-count ledger (warrants, ESOP, buybacks), banks excluded from industrial tests | before/after verified on audited filings, no double counting |
| 3 | Orders: order-book reconciliation, order vs TTM revenue (replace "latest quarter or year") | ratios match hand calculation on the audited orders |
| 4 | Results and earnings quality over several periods | YoY/QoQ exact (done), cash conversion, other income, exceptional items |
| 5 | Sector playbooks, in the order above | correct metrics chosen per sector on the evaluation set |
| 6 | Event lifecycle linking | follow-ups update records; no duplicate events |
| 7 | Adaptive card: sections only when the data exists | no empty or irrelevant sections on the web card |
| 8 | Monitoring | every material metric traces to evidence; unsupported claims flagged |

## Deferred

- Debt maturity profile, covenants, annual cash-flow series: need annual-report or rating-report data;
  XBRL quarterly results do not carry them. Taken when the source is read, not before.
- The sixteen extra event types: first dividend, buyback, bonus/split, warrant conversion, promoter pledge,
  rating action, regulatory/litigation, related-party (all cheap and deterministic); ESOP pool, insolvency
  detail, plant shutdown impact and customer concentration wait for data.
- NSE sources (their integrated results, shareholding, insider and bulk-deal feeds): useful, but our scope
  is BSE; revisit after stage 3.
- Per-sector playbooks beyond the six above.

## Rejected

- Embedding-based retrieval as a source of numerical state (structured records only).
- Industry benchmarks from "credible publications": no primary source, unsourced numbers on a card.
- News articles as a source of any material figure.
- A single bullish/bearish label for every event.
- Streamlit as the renderer: our card is the React web page; the calculations stay in Python and are
  independent of the renderer, as the note recommends.
