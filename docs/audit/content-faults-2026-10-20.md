# Content faults from the web test: where the wrong values came from (T5, 2026-10-20)

From the local D1 and R2 memory, at a1ed393. Raw pass-2 replies are not stored (see item 3), so item 3 is read from memory
and the cards. Company: Heritage Foods (519552), basis consolidated on every results card.

## 1. Heritage Q4FY26 "PAT +16.7% YoY" (actual: down 37%)

Card `145bb59e-db01-490b-86f5-ebe6eab36492` (Q4FY26, consolidated): `results.pat` = 23.94, `prev_year` = **20.51**,
`yoy_pct` = 16.7. Revenue's `prev_year` is **1,034.76** too.

Memory's Q4FY25 `pat` entry has six sources:

| Source | Value | Note |
|---|---|---|
| d7ea9e10 (board outcome, M&A card, basis STANDALONE) | 20.51 | its `fundamentals` gave revenue 1,034.76 |
| e87824b7 (Integrated Filing, Q4FY25 results card, consolidated) | 38.17 | |
| 1d36b5ce | 38.2 | |
| `xbrl:res:519552:Q4FY25` (seed, 2025-06-12) | **20.51** | seed log: `Integrated_Finance_Ind_As_519552_1262025132650.xml (STANDALONE)` |
| 26915066 (Q1FY26 card) | 38.17 | |
| 145bb59e (Q4FY26 card itself: the filing's own year-ago column) | 38.17 | |

`dossier._metric_entry` gives the value to the newest XBRL source ("a machine-tagged XBRL source outranks any card").
Here the seed's file is the **standalone** statement that Heritage filed again on 12 Jun 2025, so one standalone value
beats five consolidated ones, including the year-ago figure printed in the Q4FY26 filing itself. **Class: mixed basis**,
not a restatement and not a wrong period. The same thing happens in Q2FY26: the seed took
`Integrated_Finance_Ind_As_519552_2612202515164.xml (STANDALONE)` (revenue 1,090.41 and PAT 48.4, against 1,112.52 and
50.99 on five consolidated sources). Heritage's other 10 seeded quarters agree with the cards.

Rules:
- Each metric source carries its basis (the seed knows it; a card has `results.basis`). `_metric_entry` takes a value
  only from sources of one basis, consolidated when the company files both. XBRL outranks a card **within the same
  basis only**.
- The seed must not use a standalone file for a quarter when the company files consolidated results (it does for
  other quarters). It should leave that quarter to the cards, or keep it under a separate standalone key.
- A results card's YoY and QoQ come from the comparative columns its own statement prints when they are there; memory
  is only for what the statement does not print. This one filing printed 38.17 and the card still used 20.51.
- A non-results card (here M&A) does not write quarterly P&L figures into memory.

Check for other companies: compare each `xbrl:res` value with the card sources for the same metric and period. Every
quarter where the XBRL value is more than 1% from all card values, and the seed log says STANDALONE, is the same fault.

## 2. Heritage's two Q2FY27 results cards

| news_id | Filed | Filing | Card |
|---|---|---|---|
| 527b6923-cd12-4d50-adbe-3c07f3c0e733 | 15 Oct 15:06 | Board meeting outcome (the 16-page statement) | held, review UNRESOLVED |
| 1d299133-85bb-4263-bc45-d96015d2cb0a | 15 Oct 15:28 | Reg 30 press release (5 pages) | published |

D20 did not merge them on purpose. `_same_results_quarter` skips an owner whose card is held, so that another
document of the quarter can carry the published card (funnel fix, 2026-10-18). Q3FY26 has the same pair (`a43b6f5c`
held, `f6c62958` published). What looks wrong on the site:
- **Both are in the company timeline.** The held card's `timeline_entry` went into memory (`dossier.merge` adds every
  material card's timeline entry), so "How the story is unfolding" shows two Q2FY27 results lines with different
  figures. Rule: a held card's timeline entry stays out of memory, or the page drops a timeline entry whose card is
  held. Memory facts from a held card need the same decision. Its metrics are the statement's own figures, so they
  can stay.
- **Whose figures are right:** the press release's. Revenue +19% YoY = 1,319.58 / 1,112.52 (+18.6%) and PAT −39% =
  30.86 / 50.99 (−39.5%). The results table on both cards says +21.0% and −36.2%: that table reads its year-ago
  values from memory, which has the standalone Q2FY26 of item 1 (1,090.41 and 48.4). Fixing item 1 fixes the table.

## 3. Targets left Open after the results that settle them; one metric with three targets

These are `predictions` (the company page's "Targets being checked"), written from a card's
`track_next.kpis_to_verify`. They are not the `guidance` list.

| id | Metric, period | Target | From | Status |
|---|---|---|---|---|
| p_3b444feb | vap_share_pct Q2FY27 | ≥ 38 | 5b4d52d5 (Q1FY27 results, 16 Jul) | OPEN |
| p_f0d7233d | vap_share_pct Q2FY27 | ≥ 48 | 7706e7cb (20 Jul) | OPEN |
| p_13590891 | vap_share_pct Q2FY27 | ≥ 49 | a98480e8 (concall, 21 Jul) | OPEN |
| p_efa1bf1a | volume_growth Q2FY27 | ≥ 0 | a98480e8 | OPEN |
| p_32e365a0 | ebitda_margin Q2FY27 | ≥ 5.5 | 5b4d52d5 | MET by 1d299133 (5.61) |

**Why they stay Open.** `dossier.merge` settles a prediction only when this filing writes a `financial_metrics` entry
with the same metric key and period. Heritage's Q2FY27 filings wrote no `vap_share_pct` and no `volume_growth` for
Q2FY27 (memory's Q2FY27 metrics are the 22 statement lines). The VAP share they did report went into `segment_mix`:
"VAP (incl Ghee/Butter)" 42.5%, "VAP (excl Ghee/Butter)" 35.4%. A KPI that only an investor presentation or a call
reports, or one reported under another key, never settles. EBITDA margin settles because the statement has it.

**Why three targets for one metric.** The id is a hash of (scrip, metric, period, **value**), so each card proposing a
different number for the same metric and period adds a new row. Two of them may be different measures under one key:
38 looks like the excl-ghee share and 48/49 the incl share; Q1FY27's `vap_share_pct` in memory is 49.0, but the Q2FY27
filing gives 42.5 incl. The 38 probably came from a misread too.

Guidance (the `guidance` list, from `promise_updates`) has the same problem in two places:
- `g_2d148653` "5,000 farmer additions" is due Q2FY27 and still ON_TRACK after the Q2FY27 results.
- `g_1dda8bc2` "2 MLPD milk procurement" was due FY26 and is still ON_TRACK in Q2FY27, more than six months after
  FY26 ended.

`g_16180c7d` and `g_3b9e548d` are the same ₹6,000 Cr FY27 revenue target from two filings (21 May 2025 and 14 May 2026).
**What pass 2 returned in `promise_updates` cannot be checked: pass-2 replies are not stored** (`AIResult.raw_text`
stays in memory; no card field or object keeps it).

Rules:
- A prediction settles from any source of the period's figure: `financial_metrics`, `segment_mix` share (map the KPI to
  the segment), and the card's `key_numbers` for that period. Then, when the period's results and the call or deck are
  in and there is still no figure, mark it UNSETTLED ("not reported"), not OPEN forever.
- One open prediction per (metric, period). A later card with another value for the same metric and period replaces the
  open one, or is refused when a figure for that period already exists. Name the variant (incl / excl) in the metric key
  when the filing does.
- Guidance whose due period has ended stays ON_TRACK only until that period's results and call are in. After that it
  is DELIVERED or MISSED from the reported figure, or UNSETTLED, never ON_TRACK.
- Merge guidance with the same metric, target and due period from different filings into one entry with both sources.
- Keep pass 2's `promise_updates` (or the whole reply) with the card, so a status can be traced to the reply that set
  it.
