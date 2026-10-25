# Root causes of wrong cards: the master list (25 Oct 2026)

Built from every audit and finding on file (rounds 0-6, the 20 Oct live reviews, the daily audits of 21-24 Oct, the 25 Oct
trace, the held-card and data-chain audits, the code audits, TRACKER F-rows, HANDOVER, PLAN, TODO, FROM_ZERO). Read-only
analysis: no code was changed and no AI was run. Statuses were checked against TRACKER text and, where a function is
named, against the code (the checks I ran are listed in section 7).

## 1. In plain English (8 lines)

1. I read every audit since 16 Oct and found 38 separate root causes. 5 are fixed, 1 is built but not re-measured, 25 are partly fixed and 7 are still open.
2. Most wrong cards start in our own code, not in the AI writer. Of the 95 faults on the 48 wrong cards of 21-24 Oct, 45 (47%) were a wrong number or label put in, 34 (36%) were wrong words about right numbers, and 16 (17%) were whole-card problems (repeat cards, wrong event type, broken sentences).
3. 30 of the 48 wrong cards (62%) have at least one wrong number put in. Only 12 (25%) are wrong in words alone.
4. Call and deck cards are about one card in five (27 of 128) but half of the wrong ones (13 of 25 on 23-24 Oct). Results cards were 4 of 29. The call and deck path is where the money is.
5. No single cause is big. The biggest (results-table lines on mixed definitions) is about 3 points of the 22% wrong rate. To reach 5% we must remove almost all of the causes, not one or two.
6. The ten fixes in section 3 would, by my estimate, take the pooled wrong rate from about 22% to about 9-10% on the same kind of cards. The last 4-5 points need the "new classes" that every new day brings, or the two-part card (checked part only counts).
7. Our fixes worked on the companies they were written from and less on new ones: re-runs went 36% to 19%, 21% to 13%, 23% to 10%, but fresh companies scored 12.5%, 21%, 23%, 17% and (live, pooled) 22%. Invented causes, memory, event type and direction have not moved since round 3.
8. Advice: do the data-in review first (how tables pick their numbers, units and currency, comparatives), then the words (let code write comparisons), then the repeat-card and event-type rules. Section 5 gives the split.

How to read the counts. Reviewer class tags ("other" is 35-60% of all tags) are too coarse, so for 21-24 Oct I used the
25 Oct trace (48 WRONG cards, 95 fault points in `trace_group*.json`) and assigned each point to a mechanism myself (the
assignment is in Appendix B). A card with several mechanisms is split evenly between them ("fair share"), so the shares add
to 48. Counts for earlier rounds are issue tags per round (Appendix A), not cards. Audit instruments differ, so counts are
a guide to size and recency, not exact rates. The trace overstates what is still open: several cards were healed or fixed
since review.

Status words. **FIXED** = a TRACKER F-row, and what was re-measured is stated. **BUILT** = code exists but there is no
F-row, or the switch is off, or nothing has re-measured it. **PARTLY** = some of the mechanism is fixed, the rest named.
**OPEN** = nothing built. Not marked FIXED without an F-row: the 22 Oct fixes E1-E14 (`docs/audit/work-2026-10-22.md`,
PRs #65-#74) and several ledger-only changes have no F-row in TRACKER (a gap in the record).

## 2. The master table

"Trace" = points / cards among the 48 WRONG cards of 21-24 Oct (95 points). Ids are `nse-1068xxxxx` (last five digits
shown); a longer number is the digits after `nse-`. "Fix touches": EXT = extraction or reading, TBL = the table or block the code builds,
WRT = the writer or its prompt, CHK = a check, CARD = whole-card rules.

### A. Reading the filing (extraction)

| ID | Root cause (mechanism) | Where | Findings (by date) | Example cards | Status | Fix touches |
|---|---|---|---|---|---|---|
| X1 | A slide, chart or tile figure is paired with the wrong label or the wrong x-axis point: the text layer puts a value apart from its label; chart bars are matched by order, not by the x label; tile slides give employee cost 45.3% next to "SaaS growth" | extraction (text layer, chart/tile reading), then the writer's quote | Trace 7 / 5. R0 wrong_column 43 issues, R1 14, R2 13, R3-R6 2-8. HANDOVER open #1 | Newgen 26271, CSB 26208 (cost of deposits), Grwr Hitech 24530, UTI AMC 27362 (SIP: Feb bar for Sep), Cyient 24929 | OPEN. D29 (OCR first on figure pages, hard pages 98% of figures) covers statements, not charts or tiles. F66 fixed one table's column order (Bandhan) | EXT |
| X2 | A printed cell is misread: scan or garbled text layer; OCR drops a thin "-" or "Nil" cell so a later figure slides, swaps digits in small print, or loses brackets (a negative becomes positive) | extraction (OCR, text layer) | Trace 2 / 2. R0 brackets (CSB cash flow); bench: ~1 in 10 bracketed negatives lost, vision swaps digits (2.4% of figures not on page) | Havells 24696 ("(99)" read "(66)"), Dynamatic 27580 (ESOP price) | PARTLY. D29 (17 Oct, no F-row): OCR-first, rows checked cell by cell, brackets repaired. Open: nils on scanned grids (governance grid 4 of 20 rows) | EXT |
| X3 | The speaker's or document's own slip is copied faithfully (transcript says "19.5 billion" for 195; a Q2FY27 call says "233 crores... quarter two FY24") | input; no check against the results XBRL | Trace 3 / 2. Seen 21 and 24 Oct | Bajaj Consumer 23055, HDFC Bank 27180 (PAT 1,950 for 19,510 Cr) | PARTLY. `results_card.call_figure_conflicts` (ledger 21 Oct 15:20, no F-row; 2 of 198 call cards) needs both the figure and its stated change to contradict: HDFC had no stated change and passed | CHK |
| X4 | Currency and unit: a foreign amount shown as rupees (SEK, THB, USD); our unit fixer rescales a right figure (one "(₹ Lakh)" line made a crore deck lakh); an FX product with no unit (20 x 89); memory holds USD millions labelled crore | grounding, deal value, memory | Trace 5 / 5, four with no other fault. unit_scale: R0 88, R1 22, R2 11, R4 13, R4 re-run 14, R5 4, R5b 6, R6 7; daily 21-24 Oct 5 WRONG cards | MHRIL 23248, Sagility 23961, HCL Tech 23370, KPIL 27464 (SEK 86.4 Mn as Rs 8.64 Cr), Cyient 24929 ($121 Mn) | PARTLY. F1, F35, F54, F73 (`foreign_as_rupees`), F98 (fixers: all 33 right fixes kept, 9 of 12 wrong blocked), F99; exchange-rate units (22 Oct, ledger). Re-measured: no fall after F73 (R4 re-run 14). Still open: SEK and THB are in no currency list (grep, section 7); three different currency lists exist (code audit A3); a "billion" slip against the results XBRL | EXT + CHK |
| X5 | The company's own XBRL is wrong at source (Jubilant tagged at a tenth; Siemens' 18-month year dated as 12) | XBRL parse, memory | Jubilant R3a (FY25 +979%); Siemens 22 Oct and R4; 27 of 1,349 stored years disagree with their quarters | Jubilant FY25, Siemens FY26 | PARTLY. F54 FIXED (re-run: FY25 revenue +7.9%, round 3b). F97 `xbrl.long_year` built, memory reseeded 22 Oct; the 27 flagged years not yet checked source by source (`long-years-2026-10-22.md`) | EXT |
| X6 | Years not ending in March mislabelled; a derived quarter (H1 minus Q1) looks reported | XBRL period labels, memory, results table | Data chain A1/A2 (22 Oct): Gillette, P&G, Siemens | Siemens (Oct-Mar "H2FY26"), Gillette | BUILT. E1 (`fy_end_month`) and E2 ("derived" mark), 22 Oct, PRs #65-#74, no F-row, not re-measured. Risk left: a restated FY lands whole in Q4 | EXT |
| X7 | Results XBRL arrives after the PDF (median 132 min, 36% after our 3-hour wait, measured 25 Oct on 45 companies), so the card is first made from the PDF alone (standalone-made, wrong base); the catch-up re-reads only the 60 oldest cards | pipeline orchestration | 13 of 52 results cards since 20 Sep were standalone-made (owner-items A15); 4 waiting re-read (HANDOVER) | Wendt 106823265, HDFC Life, ICICI Lombard 106817737 | OPEN. Code audit A13 confirmed by me: `db/queries/results_cards_recent.sql` is `ORDER BY c.filed_at` (oldest first), one of 60 slots for every row. F132/F136 are about missing PDFs, not this | EXT |
| X8 | XBRL tag choices: PBT before or after associates, owners' profit vs group profit, "other expenses" tagged as a sum, bank group profit before minorities | `xbrl.py` | Live review 3 (IFB, Orient Bell, Sunteck, ITC); held audit (Bajaj Finance, DB Corp, NIIT); item 13 measured 25 Oct: 15 of 438 official lines are real definition differences, 0 different figures | Orient Bell Q1FY27, Bajaj Finance | PARTLY. F91 (23 periods of 17 filings right on an independent check), F137, F140 (SEBI sums check: 1 real failure in 166 files), E9. Open: TODO 13 (PDF is the witness; Tier 1 hold, Tier 2 leave out) is designed and off | EXT |
| X9 | Early reading errors: model alone read results (no XBRL), 10x from lakh/million, a mangled "(₹ in million)" header, QoQ called YoY, previous quarter as current, PBT or segment result called EBITDA | model-only results path | R0: 95 of 177 WRONG; unit_scale 88, wrong_period 64, wrong_column 43 | Novartis, Ahluwalia, Heritage, Prism | FIXED. F1, F24, F29, F33 then F69 (XBRL from the exchange), F34-F36, F38. Re-measured: R1 unit_scale 88 to 22, wrong_period 64 to 5, wrong_column 43 to 14 | EXT |

### B. Choosing the number (data selection and the tables code builds)

| ID | Root cause (mechanism) | Where | Findings (by date) | Example cards | Status | Fix touches |
|---|---|---|---|---|---|---|
| D1 | One results or call-table line sets figures on different definitions or scopes: EBITDA with and without other income, EBIT labelled EBITDA, adjusted or operational against statutory, a segment against the group, total income against revenue from operations, profit before against after associates | `dossier.results_snapshot`, call tables, XBRL EBITDA | Trace 12 / 10 (largest share, 6.4 cards). R0 PBT/segment as EBITDA; live review 3 (IFB, Orient Bell); F123 review: Union, PNB, Canara, ICICI, Federal, RBL, Lumax, Bansal, Solara, MHRIL, Manaksia, Juniper; E13 22 Oct | Shree Cement 26054, Cyient 25071, Swiggy 24838, Adani Energy 24806, Sapphire 24625, TechM 23950, Godrej 26077, Trivenipt 27039 | PARTLY. F38, F91, F109 (3 of 489 changed, narrowed from 47), F119 (EBITDA change kept where the filing prints its own year-ago within 0.5%), F137, E10 (call-table EBITDA from the results filing only; 13 of 461 changed). F151 (print their EBITDA, label ours) is built behind `CARD_EBITDA_PROFIT_V2`, default off, release check pending. F123 (filter after the fact) was rejected: 66% of removals WRONG, mark 80%. E13 still open | TBL |
| D2 | Year-ago or previous comparative taken from old or unrestated XBRL or memory instead of the current filing's own printed comparative column | `results_snapshot`, `xbrl.add_comparatives` | Trace 6 / 3. R2 (SKF, Prism, Kanoria, HEG); live review 3 (Man Industries, Jubilant Agri), review 5 (Kapston, Bajaj Finance); R6 (Ambuja, Titagarh); 23-24 Oct still | Pitti 25268 (3 points), Geojit 27476 (2), UTI AMC 27362 | PARTLY. F60 (a change only where the filing prints the base), 20 Oct rule (a comparative the text does not print is dropped; Kapston and Bajaj healed), F77 (change left out where not printed). Still wrong after those: Pitti and Geojit. Code audit A5: a call table's old-file comparatives go over the restated one (reported, not fixed) | TBL |
| D3 | Basis and lens: a handout's standalone figures under a CONSOLIDATED label; standalone current beside consolidated priors; a bank lens (interest earned) on an AMC; an older quarter's table on a call | results block, call blocks, seed | Trace 5 / 5. standalone_consolidated R0 12, R2 6, R3 5, R4 re-run 6, R5b 5; daily 21-24 Oct 4 WRONG cards | BPCL 27243, J&K Bank 24719, PNB 26336, NAM India 24702, UTI AMC 27362 | PARTLY. F83 (one basis per metric), E3 (one basis per comparison), E11 (call table only for the quarter just ended: 14 of 493 lost theirs), `settle` of standalone files in F76/F77. Open: A14 (NBFC lens matches AMCs, exchanges, CRISIL); a deck's own basis against the card's | TBL |
| D4 | Memory-fed claims with the wrong scope or period: a prediction of another quarter "met"; board size from memory ignoring the filing's appointments; July call figures stored under Q2FY27; a call's segment margin written over the group's in memory | memory view, `dossier.merge` | Trace 5 / 4 (plus Cyient's margin in D1). Memory class: R2 47 issues (37 cards), R2 re-run 11, R3 39, R4 25, R4 re-run 30, R5 37, R5b 40, R6 42 | HDFC Bank 27180 (p_d48ef89e), Shriram PPS 24587, CIE India 24995, Cyient 24929 | PARTLY. F61 (trusted figures only), F106 (`other_definition`: 91 of 15,621 call figures refused), F128 (memory quarantine), F144 and F150 (labels on every item, readers unchanged, no card change). Open: E14 (calendar-year company's call figures under the wrong quarter), A4 (a call card may overwrite results figures), TODO 3 "R1" planned | TBL + CHK |
| D5 | Memory stores a wrong figure (10x, another basis, another entity's) and later cards quote it | trust filter, memory | R2 Magellanic 127.62, Bandhan net worth, SBI Life; R3 Newgen (employee cost 19,010 Cr, JAWS +10,373%); R4 Anlon 1,533; 21 Oct HCL (USD as Cr) | Newgen, HCL Tech 23370 | PARTLY. F61 (R2 re-run: memory-point errors 37 cards to 11, author-reviewed); F128. R3 blind review found 36 cards with memory points wrong, so the gain did not hold | EXT + CHK |
| D6 | Wrong period label in prose: H1FY25 for H1FY26, a quarter's margin as "a year ago", a 30-09-2025 column labelled Q2FY25, "Q2FY26" for the Sep 2026 quarter, cumulative H1 called Q2 | writer, `ground()` label shift | Trace 4 / 4. wrong_period R0 64, R4 9, R4 re-run 10, R5 12, R6 7; 22 Oct 5 WRONG cards | Beta 24520, Swiggy 24838, CSB 26208 (CASA), Panache 27016 | PARTLY. F2 (quarter from "quarter ended" date), period shift in `ground()`, `misdated_memory_insights` (3 of 343, all wrong). Not built: the trace's "derive the period label from the column's date header in code" | WRT + CHK |
| D7 | Per-share and price items across a split or bonus: EPS year-ago before the bonus; market cap and returns on old share count; book value, dividend per share | table, scale block, price | Adani Power (R2), Kapston (21 Oct, listed twice that day), LIC (R6), Bajaj Finance (held audit, twice); A5/A6/R10 | Kapston Q2FY27, Bajaj Finance | PARTLY. F60, F77, E6 (NSE corporate-actions feed; the company page divides EPS, no F-row), F141 (EPS growth blank across a share-count change). `corporate_actions.share_factor_after` has no caller in the pipeline (section 7): cards, market cap, the scale block are not adjusted (code audit R10 open) | TBL |
| D8 | An amount's meaning or base is wrong in a deal or scale block: an enabling limit as money raised, a per-year charge, face value as price, an earlier award, shares x face value, net worth from a memory guidance item, TTM against a quarter | `deal_value`, SCALE block | Trace 2 / 1 (Godrej). R4 (Torrent 20.96 Cr, Anlon 10x), R5 Ceigall x4, Repco 20,000 Cr ceiling, R6 Titagarh | Godrej Properties 26077 | PARTLY. F66, F73 (`deal_echo_slips`), F76 (per-year, running totals), F77 (computed impacts in their units), F103 (face value never a price), E4 (foreign deals), F106 (`term_years`) | CARD |
| D9 | Deal stage or kind wrong (BOARD_APPROVED for proposed, COMPLETED before closing, CANCELLED for done, demerger typed ACQUISITION) | `deal_guards`, `gate.supported_stage` | Live review 3: 4 of 7 WRONG; review 5; R4 re-run, R6 | ITC, Jubilant Agri, Orient Bell | PARTLY. `gate.supported_stage` (20 Oct: 3 of 197 COMPLETED corrected), F105 (case steps: 8 of 109, all toward the filing). No stage WRONG in the 21-24 Oct trace | CARD |
| D10 | One order counted twice in memory, or a recap read as an order | `dossier.same_deal`, `is_recap` | R2 re-run: 7 of the 17 WRONG (all Magellanic: "17th order, Rs 291 Cr" for 10 orders, Rs 100 Cr) | Magellanic Cloud | FIXED. F66; F105 (census of 21 stored orders told twice: 18 true repeats). Not re-measured on a fresh review since 23 Oct | CARD |
| D11 | Memory seed took a standalone file where a consolidated one exists | `seed.py`, `dossier._metric_entry` | Heritage Q4FY25 PAT 20.51 against 38.17 ("+16.7%" for a 37% fall); Max Financial | Heritage 145bb59e | PARTLY. F83, F76/F77 (consolidated first). T13 steps 3-5 (checks after the re-seed) still open (HANDOVER); the re-seed stopped at company 512008 on 20 Oct and its completion is not recorded in the files I read | EXT |
| D12 | Ownership or pledge claims from other cards instead of a shareholding pattern (Clean Max's 20.02% pledge) | memory | R6 (2 cards) | Clean Max | FIXED. F77 (ownership only from shareholding patterns). Not re-measured: round 7 was cancelled (D37) | EXT |

### C. Writing (right number in, wrong words out)

| ID | Root cause (mechanism) | Where | Findings (by date) | Example cards | Status | Fix touches |
|---|---|---|---|---|---|---|
| W1 | Unsupported or invented cause, outcome, milestone, catalyst, target, or "fully utilized" | pass 2 prompt (rulebook said "stated or clearly implied"), no check on causes | Trace 10 / 10 (5.0 cards; only 2 cards have this as their only fault). invented: R0 147, R1 30, R2 19, R3 31, R4 48, R4 re-run 44, R5 58, R5b 31, R6 40. MINOR unsupported_cause 12 and invented 4 in 21-24 Oct. HANDOVER MINOR list | ABSL AMC 23286, NAM India 24708, BPCL 27243, Shree Cement 106826079, PNB 26336 | PARTLY. F73 prompt, F118 (prompts without contradictions, 24 Oct: "built, measured live", no result recorded), `directions.py` (tax, inventory, EPS, credit-cost guards). Rejected on their audits: `causes.py` (cut 73% of claims, caught 8 of 27), NLI check, F124 words-against-figures (precision 9%), shadow critic (precision 9-12%, off, D41). Code audit A12 confirmed: nothing calls `causes.py`. F152 (two-part card) built, default off | WRT |
| W2 | Comparison words contradict the card's own figures: "accelerated... outperforming 25.7%" for 20.2%; "more than double" for +74%; "turns positive" on a loss; +2324% from a loss base; "slipped" where the filing says improved | writer | Trace 4 / 4. direction: R0 29, R1 17, R4 21, R4 re-run 16, R5 15, R5b 6, R6 10 | CRISIL 27017, LMW 23292, Sapphire 24614, TruAlt 27073 | PARTLY. F60, `directions.multiple_guard` (ledger 21 Oct: 2 of 1,736), E12 profit-turn (1 of 1,094), F73 XBRL-contradicted claims. F124's comparison and direction flags were 1 of 5 and 5 of 74 right, because the code-built table was the wrong side (a lead on D1/D2) | WRT |
| W3 | Entity or scope attribution: industry capacity as the company's; a manager to the offer as the acquirer; a segment's heading dropped; both exchanges' fines added; "with subsidiaries" for an associate | writer; quote check accepts a trimmed or spliced quote | Trace 4 / 4. ai-quality plan (21 Oct): "other" 43 of 127 cards, mostly scope. R6 Clean Max x5, Airtel Maharashtra; 24 Oct 2 WRONG and 4 MINOR | TruAlt 27073, Jindal Photo 27030, HUDCO 24516, Dynamatic 27580 | OPEN. No F-row. The trace's check (quote must be one contiguous passage, no ellipsis) is not built | WRT + CHK |
| W4 | The writer pairs a figure with the wrong nearby label: 443 "cities" is the Tier III store count; NIM given for cost of funds; two provision types merged; other-expenses cell | writer | Trace 4 / 3. R4 and R5 "metric mislabels" (Star Health GWP as revenue, Nestle exports growth as a tax rate, Siemens EBIT as EBITDA target), R6 (advances growth tracked as revenue) | VMM 23242, Bajaj Finance 26278, NAM India 24702 | OPEN | WRT + CHK |
| W5 | Arithmetic by the model: shares x one price when tranches differ; sums and streak counts; discount to a price it derived; "H2 potential" | writer, computed impacts | Trace 6 / 4. arithmetic: R0 89, R1 40, R2 20, R3 12, R4 6, R4 re-run 13, R5 9, R5b 9, R6 5 | Dynamatic 27580, TechM 23950, Natco 24629, Godrej 26077 | PARTLY. F60 (code computes), F100 (sum of a point's own quote), computed impacts checked in units (22 Oct). Gains held: 89 to about 5-13 | WRT |
| W6 | Event type wrong, or one document carrying two events | rules plus pass 1 | Trace 3 / 3. event_type: R0 34, R3 12, R4 14, R5 15, R5b 17, R6 26 (rising); 41 of 86 CORPORATE_ACTION cards were not corporate actions (22 Oct); 23-24 Oct 3 WRONG, 3 MINOR | Atul 26222, VRL 27546 (buyback as RIGHTS), Shree Cement 106826079 | PARTLY. F40, F87, F88, F91, F107 (cover letter submits results: 4 of 308 changed, 5 of 5 right), `EVENT_DEFINITIONS` in prompts (22 Oct; the promised measurement from 23 Oct is not in the files). Open: results press releases typed OTHER (Westlife, Shree), buyback typed RIGHTS, KPIL stake sale typed FUNDRAISE, one document two events | CARD |
| W7 | Impact level too high on routine items (MINOR, blocks RIGHT) | scoring, prompt | R3 25 of 90, R4 38 of 122, R5 49 of 140, R5b 25 of 146 misfit; live review 5: 12 of 32 too high | reaffirmations, notices, housekeeping | PARTLY. Results never LOW (F76), procedural steps LOW in the prompt (F73). Code audit A7 (code inflates impact: keywords, outlook as text, misfires) not fixed | CARD |
| W8 | Guidance and KPI verdicts: "MAINTAINED" accepted with any guidance in memory; target set on the wrong metric; a full-year target judged on a quarter; predictions never settled | `reconcile_call_read`, track-next | HANDOVER MINOR (Persistent, Urban Company); live review 2 (CSB); R5b Siemens Energy (EBIT 21.9 as EBITDA target); Heritage targets open forever | Persistent, Urban Company | PARTLY. F37, F39, F83 (one open prediction per metric, no ON_TRACK past deadline), F86. Code audit A8 confirmed by me: `pipeline.reconcile_call_read` still only asks that memory holds any guidance | CHK |
| W9 | Signals and scores that misfire: WATCH_RESOLVED with no KPI figure, "LOA to LOA" stage update, rating notches scoring HIGH, GUIDANCE_BREACH before results are due | `signals.py`, `scoring.py` | Trace 3 / 3. signal_verdict: R0 55, R1 16, R2 16, R3 2, R4 15, R4 re-run 12, R5 16, R5b 20, R6 3 | MCLOUD 25832, Muthoot 27430, VRL 27546 | PARTLY. F37, F39, F62 (signals that contradicted their card are off), F111 (rating on the same agency and scale: 9 of 21 changed, none wrong). Open: the three trace cases | CARD |

### D. Whole card, checks and process

| ID | Root cause (mechanism) | Where | Findings (by date) | Example cards | Status | Fix touches |
|---|---|---|---|---|---|---|
| P1 | Repeat cards for one event from different documents (results, deck, press release; buyback terms then letter of offer; an order's intimation and its press release; one PDF refiled) | duplicates, D20 | Trace 4 / 4. R2 re-run Magellanic; Kapston, SML (15 M&A cards), Heritage; 21-24 Oct 3 WRONG, 1 MINOR | MCLOUD 25832, Trivenipt 27039 (third card), Panache 27016, VRL 27546 | PARTLY. D20, F66, F105 (order told twice: 18 of 18 true repeats), F110 (17 of 892 pairs, all byte-identical), F143 (same file skipped before OCR). Open (HANDOVER #2): a rule for the same event in different documents; one document with two events gets one card (Jindal Stainless, Eternal, GOCL); stored duplicates stay published | CARD |
| P2 | A card for a letter with no news (an audio-link letter) | rules | Trace 1 / 1 (Shriram Finance 27198); IREDA MINOR | Shriram Finance | FIXED. F108 (2 of 516 cards changed). Not yet re-measured on live cards | CARD |
| P3 | A sentence left broken after a figure is stripped ("under of market cap", "7- margin boost", "** **") | `computed.broken`, strip | Trace 3 / 2 (Atul, PNB). R2 re-run and R3: 10 and 3 cards | Atul 26222, PNB 26336 | FIXED. F66, then F108 (`_DANGLING` reads ranges: 2 of 516 changed). Atul and PNB occurred the day before F108; live re-measure pending | CHK |
| P4 | The quote and prune checks are wrong both ways: they drop true points (15 of 16 pruned points true on 24 Oct, 16 of 17 on 23 Oct; 81% of 675 hold reasons false on 22 Oct) and let some wrong ones through (prefix digits accepted; a trimmed quote passes) | `gate.py`, `prune.py`, `grounding.py` | Trace 2 / 2 (Swiggy, CIE: true points pruned). Code audit A1/A2/A10 | Swiggy 24838, CIE 24995 (a Cyient interim dividend was also dropped, HANDOVER) | PARTLY. F89, F98-F103 (21 + 17 + 9 false holds freed, 0 true), F116 (pruned points kept behind the tap), F120 (results cards keep the model's quoted facts). Reproduced 25 Oct: `gate.numbers_in_quote` still passes "95" against "951.96" and "1,95,000" against "19,500" (it refuses "29.4" against "9.42"). Not built: A1, A2 | CHK |
| P5 | The second opinion adopts the whole second card but re-checks only numbers and quotes | `pipeline` second opinion | CORRECTED cards: 6 of 21 WRONG (29%) against 21% overall, 23-24 Oct; one UNCHECKED card published and WRONG | audit rows with review_status CORRECTED | OPEN (code audit section 4; only F112's provider rule is built) | CHK |
| P6 | `refresh-card-blocks` only adds: a block computed from the card is never removed, impact only raised | `card_refresh.py` | Muthoot Microfin stayed HIGH after its rating block healed; stored duplicates stay published | Muthoot 27430 | OPEN (code audit A11) | CARD |
| P7 | Weak writers and route fallbacks: Nemotron 3 Super 29-33% WRONG, Ultra 53-58%, GLM-4.7 73%; Gemini 3-5.5%; a spare took packs when Gemini quota ran out | `providers.toml`, gateway | R4, R5, R6 per-writer tables; live reviews 3+5: Flash-Lite 8 of 46 (17%) | R6: Nemotron 12 of 36 | PARTLY. F73, F77 (weak writers off every card route), F75; re-measured: R5 arm B 23% to 10%, R6 Gemini 3 of 55. Open: the audit rows carry no writer field, so WRONG per model cannot be measured now (code audit section 4) | WRT |
| P8 | Packed Gemini calls could put another filing's fact on a card ("pack bleed") | packer | Round 7 would have measured it; cancelled (D37) | none known | OPEN, unmeasured. F78 (tool), F112(3) (`packer.misplaced`: swaps only) | CHK |

Not in the table because they are not accuracy faults: D1 write budgets, quota and worker waste (code audit R1-R12,
deep audit E1-E11), site and operations (S1-S6), and the future features in TODO 36-42.

## 3. Ranking: expected wrong-card reduction, and the top-10 work list

Method. Expected gain (percentage points of all cards) = fair-share cards of the cause (section 2, trace) divided by 218
audited cards (21-24 Oct pooled, 48 WRONG = 22%), times the share a fix would remove (my judgement, stated per row).
Ranks follow that gain. Recency is shown in brackets (a card from 23-24 Oct counts 1.0, from 21-22 Oct 0.6) and nudged ties
only; ranked by the weighted figure instead, item 5 would move up to second and item 9 above item 8. Causes with no trace count (X5-X8, D5,
D7, D9, W7, W8, P5-P8) are not scored and are listed as "unscored" below. Fixes that make a check accept more still need
the owner's on/off plus blind-sample rule (HANDOVER task B step 3); a check that removes or flags more needs the pass marks
set first (the F123/F124 pattern: precision of removals at least 80%, lower Wilson bound at least 70%, wrong-removal at most 20%).

| Rank | Work item (causes) | Fair-share cards (recency-weighted) | Removal share | Expected gain, points | Status of the causes |
|---|---|---|---|---|---|
| 1 | Tables: one source, one definition, one basis, one lens (D1, D3; X7 catch-up) | 9.0 (6.7) | 0.6 | 2.5 | PARTLY, OPEN |
| 2 | Units and currency (X4) | 4.3 (3.1) | 0.8 | 1.6 | PARTLY |
| 3 | Causes and claims out of the checked face (W1) | 5.0 (4.2) | 0.6 | 1.4 | PARTLY |
| 4 | Comparison words and arithmetic written by code (W2, W5) | 5.6 (4.2) | 0.5 | 1.3 | PARTLY |
| 5 | Repeat cards, event types, signals (P1, W6, W9) | 4.5 (4.5) | 0.6 | 1.2 | PARTLY |
| 6 | Memory-fed claims and period labels (D4, D6) | 4.5 (3.4) | 0.6 | 1.2 | PARTLY |
| 7 | Attribution and label adjacency (W3, W4) | 5.3 (4.3) | 0.5 | 1.2 | OPEN |
| 8 | Reading slides, charts, scans, transcript slips (X1, X2, X3) | 4.6 (3.6) | 0.4 | 0.8 | OPEN, PARTLY |
| 9 | Printed comparative as the source (D2) | 2.3 (2.3) | 0.7 | 0.7 | PARTLY |
| 10 | Checks that damage true text (P3, P4) | 1.7 (1.3) | 0.6 | 0.5 | PARTLY (plus richness) |

Sum: about 12.5 of the 22 points, so about 9-10% WRONG if every fix lands at the assumed share. That is not 5%. The rest is
new classes each day, the long tail (unscored causes), and the interpretation lines (see the two-part card, rank 3).

Unscored but real: X7 (PDF-only results cards never re-read, a large share in results season), X5/X6, D5, D7 (split and
bonus), D9, W7 (impact level, MINOR only), W8 (guidance MAINTAINED), P5 (second opinion), P6, P8.

### The top 10

**1. Tables: one source, one definition, one basis, one lens (D1, D3, X7).**
Fix: every line of the results or call table takes current and prior from one source and one definition (both XBRL, or both
the filing's own printed row); segment, adjusted and operational figures never sit beside statutory ones; a call or deck
figure never enters a table line, it goes in the prose as "said on"; the lens comes from the company's sector, not a keyword;
turn on F151 after its release check; make the results catch-up pick the newest cards that could be due (A13), so PDF-only
and standalone-made cards are re-read. Do not add a filter after the fact: F123 showed that fails (66% of removals WRONG).
Measure without AI: replay `results_snapshot` over the 1,986 stored results and call tables with the new rule on and off
(the F119 `onoff_facts.py` pattern); list the lines that change; the 48 traced cards give the recall set (15 cards
carry D1 or D3 points, 18 with D2); blind-check a seeded 120 changed lines against the PDFs; ship only if at least 80% of changed lines
were wrong and none newly wrong.

**2. Units and currency (X4).**
Fix: one shared currency list (SEK, THB and every ISO code the filings use) for grounding, gate and deal checks; a rupee
figure next to a foreign code never reaches a crore conversion; the unit fixer never touches a figure that appears
verbatim beside a crore label (MHRIL); a call or deck headline figure that differs from the results XBRL by about 10x or 100x
is held or replaced by the XBRL figure (HDFC, Bajaj Consumer). Measure: on/off over the stored deal and call cards (the A3
census in the code audit; `scripts/audit_call_takeaways.py` pattern for the 198 call cards with a results block); count
changes; blind-sample them. Pass mark: every change a true slip.

**3. Causes and claims out of the checked face (W1).**
Fix: turn on the two-part card (F152, default off) so a cause, outcome or milestone sits in "Our reading" and is graded on
its own bar (D42); keep F118's rulebook; add the one deterministic cause check the data supports, that a cause naming a line
(other income, tax, inventory) must agree in sign with that line's XBRL change (`directions.py` already does this for four
lines). Do not retry an AI "is this stated" check (rejected three times). Measure: for the 48 traced cards and the 128 audited
on 23-24 Oct, re-label each fault by face (checked or reading) from the point text and count how many WRONG cards become
MINOR under D42's rule (`reading_only` already exists in the audit rows); for the sign check, on/off over stored cards plus
a blind sample. Caution: from the trace, only 2 of the 10 cards have W1 as their only fault, so the box rule alone moves
little; the gain depends on items 1 and 4.

**4. Comparison words and arithmetic written by code (W2, W5).**
Fix: extend F60 ("code computes, the model describes") from percentages to verbs and multiples: the writer gives the two
figures, code writes "rose / fell / accelerated / more than doubled / turns positive" from them and refuses a comparison
word the figures do not support; tranche sums and "fully utilized" computed in code from the filing's own columns. Do it
after items 1 and 9: F124 showed that 69 of the 74 direction flags were right sentences beside a wrong table. Measure: replay
over the 5,344 stored cards, list changed sentences (F124 flagged 88, 8 WRONG); blind sample; pass mark as F124 (85%) if used
as an alert, or "no changed sentence wrong" if used as a rewrite.

**5. Repeat cards, event types, signals (P1, W6, W9).**
Fix: (a) an event-level repeat rule for results-family documents of one company and one quarter (results, press release,
deck) within days, later ones linked as follow-ups, call transcripts keeping their own card (D33); (b) when a document has a
Reg 33 annex beside other items, run the results path as well (Atul pattern, F107 extended); a tender-offer buyback never
RIGHTS; a press release with a results table is RESULTS; (c) WATCH_RESOLVED only when the filing has a figure for that KPI,
a stage-change signal only when the stage differs. Measure: extend `onoff_duplicates.py` (892 same-company pairs within 3
days) to same quarter and different PDF; on/off over the 308 stored OTHER / GOVERNANCE / CORPORATE_ACTION cards as F107 did;
blind-check the changed pairs: ship only if none merges two different events.

**6. Memory-fed claims and period labels (D4, D6).**
Fix: a MEMORY-basis point with no `memory_refs` is dropped; a prediction or guidance item is used only when its period and
type match the card's; period labels in text come from the column's date header in code (the trace's own proposal); no
current-quarter table value from memory (CIE). Measure: count stored points with basis MEMORY and no memory ref (field exists
on the card); on/off over stored cards; blind sample of the dropped ones (do not drop true points: P4 shows how easily that
happens).

**7. Attribution and label adjacency (W3, W4).**
Fix: a quote is one contiguous passage (whitespace only; no ellipsis or splice); each key number's label must appear in its
own quote; a segment statement needs the segment heading in the same block; a total that two exchange documents both print
is not summed. This makes a check stricter (more points move behind the tap), so measure with `scripts/audit_quote_rules.py`
over stored cards and blind-check that the moved points are true faults. Pass mark: at least 80% of moved points faulty or
unverifiable.

**8. Reading slides, charts, scans and transcript slips (X1, X2, X3).**
Fix: for chart and tile pages pair value to label by bounding box and x position, and keep a figure behind the tap when its
label is not adjacent; scanned grids: nil cells kept (the open D29 item); a call figure 10x off the results XBRL is flagged
(item 2). Measure: replay the stored call and deck cards' key numbers and takeaways against the cached page text or bounding
boxes (PDFs from NSE; filing text in R2 is kept 6 months from 25 Oct, F147); compare the flagged points with the reviewers'
wrong points (recall set: 12 traced points on 9 cards); precision at least 80% before use.

**9. Printed comparative as the source (D2).**
Fix: the prior in the table is the current filing's printed comparative column when the filing prints one (parsed from the
text or OCR rows); XBRL priors only where the filing prints none and says nothing about restatement; when printed and XBRL
priors differ by more than 2%, show the printed one and mark "restated". This is a source choice, not the removal that F123
tried. Measure: over the stored tables, count lines where the printed prior and the XBRL prior differ; blind sample 30 of the
differing lines; accept at 80% or more.

**10. Checks that damage true text (P3, P4).**
Fix: A2 (normalise "lakh crore", punctuation and a card's stated unit before comparing) and A1 (exact digits only, strip
period labels), measured together; re-derive a pruned point from the sentence that holds all its figures only when the
figure is in a table row (F92 and F93 show looser versions let 20% wrong figures through). This accepts more and refuses
more at once, so it needs the full on/off and a blind sample (the F90 pattern: 24 sampled, 21 right was not enough).

## 4. Edge cases not yet seen in audits, but likely

Each is from reading the code paths, SOURCES.md and the audits. "Seen" names the nearest audit finding. All are
assumptions until a no-AI census over stored memory (companies, quarters) or filings finds one.

| # | Edge case | Why it is likely | Nearest finding | How to check without AI |
|---|---|---|---|---|
| 1 | Split, bonus, consolidation in per-share items beyond EPS: book value, dividend per share, dividend yield, buyback price against market, share counts in deal sizing, market cap on the old count | `share_factor_after` has no caller in the pipeline; only the web page adjusts EPS (E6) | Kapston, LIC, Adani Power EPS | stored cards whose company had an ex-date in the corporate-actions feed after the period; recompute |
| 2 | Demerger or amalgamation: continuing against total operations, restated year-ago, a new listing with no history | NSE files tag discontinued operations separately; the demerged entity's first results have no year-ago | Pitti, Siemens (LVM), Prism (RMC), Anlon | list quarters where the company has a corporate action of type scheme |
| 3 | Revised results (NSE marks a revision; catch-up re-reads within 10 days) | a revision after day 10, or one that changes earlier comparatives, leaves stored cards on the old figures | TODO check f | compare each card's figures with the latest file per quarter and basis |
| 4 | 9-month and half-year files: a quarter derived as H1 minus Q1; a restated FY lands whole in Q4 | E2 marks "derived" but the table can still show a restated total as a quarter (data chain A2) | none | stored derived quarters whose neighbours disagree by more than 3x |
| 5 | Short and 18-month years, first year after IPO | `long_year` accepts within 15%; 27 stored years unchecked | Siemens | the 27 years in `long-years-2026-10-22.md`, source by source |
| 6 | Units: "in thousands", "in Lacs", per-share amounts, share counts in crore, USD reporters, "Mn" against "Cr" symbols | declared unit is read per page; one-unit-per-document assumptions | Ambuja votes (crore), Anlon NGN, MHRIL | scan stored filings for several declared units |
| 7 | Negative numbers in brackets lost by OCR; percentages across a loss base; margin on token revenue | bench: ~1 in 10 bracketed negatives lose their brackets; no % off a negative base is built (F60) but GOCL 985% net margin was seen | CSB (R0), GOCL (F119 review) | OCR rows with a single bracket against the text layer |
| 8 | SME, REIT, InvIT, debt-only issuers: results come in the old format | SOURCES.md: the old-format page is still current for SME, debt, REIT/InvIT; our templates cover Ind AS, NBFC, banking, two insurance maps | none (they are below the main-board universe, assumption) | list universe companies with no integrated-filing file |
| 9 | Banks, NBFCs, insurers: bank lens on an AMC or exchange; insurance revenue is premium, not "revenue" (GWP read as revenue); VNB and APE are not in the taxonomy; consolidated bank files carry 0 asset-quality ratios | A14 lens match; F83 | Star Health, UTI AMC, NAM India | stored cards for lenders and AMCs: lens and labels |
| 10 | Name or symbol changes after a merger or demerger (Tata Motors' NSE file not found under its old symbol); ISIN change | company master joins by ISIN, then symbol; file lookup by symbol | Tata Motors BSE test | memory with no XBRL source for a quarter that exists |
| 11 | Standalone-only filers and companies that file standalone first and never consolidated | consolidated waits for its file (A15); a company that never files one | 13 of 52 standalone-made cards | stored results cards with basis STANDALONE and a later consolidated file |
| 12 | Non-March and calendar-year companies in call figures (E14 open) | quarters are labelled on April-March | CIE India | cards of December-year companies: call figure stored under Q2FY27 |
| 13 | EBITDA sign conventions for exceptional items | data chain A9: "frequency not measured" | none | recompute EBITDA both ways over stored XBRL |
| 14 | Multi-resolution documents (AGM, postal ballot with 20-32 items): "largest", counts, institution against non-institution vote shares | R6 Clean Max (five WRONG points on three cards) | Clean Max | cards typed GOVERNANCE with 10 or more items |
| 15 | A parent's filing that carries a listed subsidiary's results (Reg 30(9)) | the card reads the wrong entity's table | Vedanta and Hindustan Zinc | filings whose title names two companies |
| 16 | Annual reports: lakh against crore, standalone against consolidated, related parties, an XBRL file months after the PDF | F57 path; annual XBRL catch-up | Kanoria, Magellanic AR | stored ANNUAL_REPORT cards without annual XBRL |
| 17 | PDFs: cut short on NSE, ZIPs, rotated or two-column pages, a file added after listing | F132, F136 handle ZIP and cut-short; two-column quote reads (F89) | Apollo, Hindustan Zinc | failed-report by reason |
| 18 | A very large or very small base: percentages on tiny quarters, a ratio to market cap on a stale or just-adjusted price | A6 and R10 | Natco (price ~1,000 from market cap), Novartis | cards with a market-cap ratio and a price older than a week |

## 5. Data extraction against card writing

From the 25 Oct trace of the 48 WRONG cards (95 points; three independent agents; reviewer wrong: 0).

| Where the fault entered | Trace's own stage | My regrouping (Appendix B) |
|---|---|---|
| Code built a wrong table or block: wrong source, definition, basis, comparative, period, unit | CODE 40 | wrong figure or label in: 45 (47%) |
| Input unreadable, ambiguous or the speaker's slip | INPUT 12 | (counted in the 45) |
| Memory carried an earlier reading | MEMORY 7 | (counted in the 45) |
| Writer: right figures, wrong words (cause, direction, attribution, arithmetic, label) | WRITER 36 | writing: 34 (36%) |
| Whole card: duplicate, event type, noise, broken text, prune, signal | (inside CODE) | process: 16 (17%) |

Per card: of the 48 WRONG cards, 30 (62%) have at least one wrong-number-in point, 12 (25%) have only writing faults, 4
have only process faults, 2 have writing plus process. 26 cards have a single mechanism, 22 have two to four, which is why
one fix rarely turns a card right.

Other evidence that points the same way:
- Live review 3 (20 Oct): 6 of the 7 WRONG cards came from code (deal guards, `results_snapshot`, the XBRL PBT tag); review 5: 3 of 5.
- Round 4: "the figures themselves held up better than the words around them" (reviewers recomputed every amount); live review 2: headline figures mostly right, errors in what is written around them. Round 5: results cards 8 of 16 WRONG before code built them, 2 of 17 after (F74).
- Line accuracy (25 Oct): the daily audits put wrong lines on figures and the table; the fully graded set (drawn from cards where the writer was the weak point) put them on interpretation (why it matters 6 of 43, takeaway 3 of 30, against what happened 0 of 85). Both parts fail.
- Event type: call and deck cards are 21% of audited cards and 52% of WRONG on 23-24 Oct (13 of 25); in the trace 23 of the 48 are CONCALL_PRESENTATION.

Reading. Extraction in the wide sense (what number the code puts into a table or block) is the larger share, and four of
the top five work items (1, 2, 8, 9) are data-in. The writing share is real (W1-W5 are 28 points) but 2 of the 10 W1 cards
have no other fault, and the card's own interpretation lines are already outside the 5% bar (D42, F116, F152). So the
data extraction review should come before more card-writing work. Concretely, before more prompt work:
(1) the table-source rule (item 1), (2) the printed-comparative source (item 9), (3) units and currency (item 2), (4) the
call and deck path (13 of 25 WRONG; D1, D3, D4, X1, X3 all live there). The cheap writing items (3, 4) can run in parallel
because they are rules, not reading.

## 6. What changed in the picture since the last plan

- The classes did not fall as a set. Since round 3, invented 19-58 issues a round, memory 25-47, event type 12-26 (rising), direction 6-21, signal verdicts 2-20 swing. Arithmetic fell 18x (89 to 5-13) and unit scale 88 to 4-14 and stopped there.
- Fixes work on the companies they were written from and generalise only in part: round 2 re-run 36% to 19% (author-reviewed), round 3 on new companies 12.5% (blind), round 4 on new companies 21% then 13% on its own re-run, round 5 on new companies 23% then arm B 10% on its own, round 6 on new companies 17%, live pooled 21-24 Oct 22% (17-28%).
- Faults cluster (a WRONG card has 2.5 points, 21 of 48 trace cards have two or more mechanisms). A fix that removes one mechanism from a multi-cause card does not make it right.
- Line accuracy needs a roughly 4x drop in root causes per card to hold 95% at today's 13 lines.

## 7. Verification notes and caveats

Checked in code on 25 Oct (HEAD of branch `ccr-b604559f-45p2yh`, one commit ahead of `origin/main`, F152 on top):
- Exist: `dossier.other_definition`, `dossier.repeated_order`, `dossier.results_snapshot`, `card_context._same_agency`, `xbrl.long_year`, `pipeline.results_cover`, `pipeline.continued_deal`, `pipeline.stale_approvals`, `pipeline.misdated_memory_insights`, `directions.multiple_guard`, `grounding.foreign_as_rupees`, `computed.broken`, `models.EVENT_DEFINITIONS`, `results_card.call_figure_conflicts`, `fy_end_month` in `dossier.py`.
- `corporate_actions.share_factor_after` is defined and called nowhere in `pipeline/src` (D7, code audit R10 still open).
- No `SEK` anywhere in `pipeline/src`; `grounding._FOREIGN` and `gate._FOREIGN` are two different lists (X4).
- `pipeline.reconcile_call_read` still only requires that memory holds any guidance (W8, A8 open).
- `db/queries/results_cards_recent.sql` orders by `filed_at` ascending (X7, A13 open).
- `causes.py` is imported by nothing; only a comment in `critic.py` mentions it (W1, A12).
- `gate.numbers_in_quote("95 beds","revenue 951.96")` and `("1,95,000 units","19,500 units sold")` return no missing figure (P4), while `("EPS of ₹29.4 a share","EPS 9.42")` returns `['29.4']`.

Caveats.
- The trace read text layers only (OCR not run), so reading faults on scans may be under-counted, and some cards were healed after review (Sagility's unit, Tech Mahindra's EBITDA), so the trace overstates what is open.
- I assigned the 95 points to mechanisms; another reader could move a few points between D1/D2/D3 and W1/W4. The split 45 / 34 / 16 moves by a few points, not by a class.
- Counts before 21 Oct are reviewer issue tags per round (one card can carry several), not card rates. Round 7 has no result (cancelled, D37); live reviews 3 and 5 gave no per-class counts.
- Expected gains in section 3 rest on my "removal share" judgements and on no overlap between items beyond the fair-share split; read them as ordering, not as forecasts.
- TRACKER has no F-row for E1-E14 (22 Oct), the 21 Oct ledger-only changes (multiple guard, call-figure conflict, unit-fixer declared unit), or F126, F127, F129 (parked branch). That is a gap in the record; I did not mark those FIXED.

## Appendix A: issue tags by class and audit

Issues per class on all cards of each audit (a card can have several). Memory was tallied from round 2 on. Live 20 Oct
reviews 1 and 2 (48 cards): other 31, invented 22, signal_verdict 10, arithmetic 7, direction 6, event_type 6, wrong_period 6,
wrong_column 3, unit_scale 3, standalone_consolidated 4. Daily audits 21-24 Oct (class tags as the reviewers recorded them): the 48 WRONG
cards carry 56 tags: wrong_column 8, arithmetic 7, other 6, unit_scale 5, memory 5, wrong_period 5,
standalone_consolidated 4, duplicate 3, event_type 3, invented 2, direction 2, restated 2, attribution 2, unsupported_cause 1,
noise 1; MINOR cards: other 29, memory 12, unsupported_cause 12, event_type 10, wrong_period 6, attribution 4, invented 4,
direction 3, arithmetic 3, standalone_consolidated 2, duplicate 1, noise 1.

| class | R0 (177 cards, 95 WRONG) | R1 (98, 32) | R2 (90, 35) | R2 re-run (84, 17) | R3 blind (90, 16) | R4 (122, 30) | R4 re-run (120, 28) | R5 (140, 37) | R5b (146, 21) | R6 (138, 30) |
|---|---|---|---|---|---|---|---|---|---|---|
| invented | 147 | 30 | 19 | 2 | 31 | 48 | 44 | 58 | 31 | 40 |
| other | 88 | 46 | 60 | 31 | 56 | 90 | 68 | 96 | 72 | 72 |
| memory | - | - | 47 | 11 | 39 | 25 | 30 | 37 | 40 | 42 |
| arithmetic | 89 | 40 | 20 | 3 | 12 | 6 | 13 | 9 | 9 | 5 |
| unit_scale | 88 | 22 | 11 | 2 | 1 | 13 | 14 | 4 | 6 | 7 |
| wrong_period | 64 | 5 | 3 | 0 | 8 | 9 | 10 | 12 | 9 | 7 |
| wrong_column | 43 | 14 | 13 | 1 | 7 | 5 | 6 | 3 | 2 | 8 |
| signal_verdict | 55 | 16 | 16 | 9 | 2 | 15 | 12 | 16 | 20 | 3 |
| direction | 29 | 17 | 12 | 2 | 8 | 21 | 16 | 15 | 6 | 10 |
| event_type | 34 | 10 | 9 | 1 | 12 | 14 | 15 | 15 | 17 | 26 |
| standalone_consolidated | 12 | 3 | 6 | 1 | 5 | 3 | 6 | 4 | 5 | 1 |

Published WRONG share by audit: R0 54%, R1 33%, R2 36%, R2 re-run 19%, R3 12.5% (blind), R4 21%, R4 re-run 13%, R5 23%,
R5b 10%, R6 17%; live 20 Oct 29%, 42%, 26%, 15.6%; daily 21-24 Oct 23%, 20%, 15%, 23% (pooled 22%, 17-28%).

## Appendix B: how the 95 trace points were assigned

Trace points are in `docs/audit/trace-2026-10-25/trace_group{1,2,3}.json`. Cause (points / cards), cards by symbol:
- X1 (7/5): Newgen x2, CSB (cost of deposits), Grwr Hitech, Cyient (segment heading), UTI AMC x2.
- X2 (2/2): Havells, Dynamatic (ESOP price).
- X3 (3/2): Bajaj Consumer, HDFC Bank x2.
- X4 (5/5): Sagility, KPIL, HCL Tech, MHRIL, Cyient ($121 Mn).
- D1 (12/10): Cyient x3 (segment revenue, memory margin, block EBITDA), Tech Mahindra, Swiggy, Godrej, Shree Cement x2, Trivenipt (QoQ), Grwr Hitech, Sapphire (call), Adani Energy.
- D2 (6/3): Pitti x3, Geojit x2, UTI AMC (PAT base).
- D3 (5/5): BPCL, J&K Bank, PNB (basis); NAM India, UTI AMC (lens or period).
- D4 (5/4): Shriram PPS, CIE India x2, Muthoot (rating block), HDFC Bank (prediction).
- D6 (4/4): Swiggy, CSB (CASA), Panache, Beta.
- D8 (2/1): Godrej x2 (deal kind, net worth). W1 (10/10): ABSL AMC, Newgen, BPCL, NAM India, Godrej, CSB, Shree Cement, PNB, HDFC Bank (theme), UTI AMC.
- W2 (4/4): Sapphire, TruAlt, CRISIL, LMW. W3 (4/4): HUDCO, TruAlt, Dynamatic, Jindal Photo. W4 (4/3): VMM, NAM India, Bajaj Finance x2.
- W5 (6/4): Dynamatic x2, Tech Mahindra x2, Natco, Godrej.
- P1 (4/4): MCLOUD, Trivenipt, Panache, VRL. W6 (3/3): Atul, VRL, Shree Cement. P2 (1/1): Shriram Finance. W9 (3/3): MCLOUD, Muthoot, VRL.
- P3 (3/2): Atul, PNB x2. P4 (2/2): Swiggy, CIE India (true points pruned).

Totals by cause group: X 17, D 34, W 28, P 16 (95). The 45 / 34 / 16 split in sections 1 and 5 regroups them: wrong figure or
label in = X minus Cyient's "$121 Mn" (16) plus D minus the four period-label points and the Godrej deal kind (29) = 45;
writing = W 28 plus those five points plus the "$121 Mn" point = 34; process = P 16. Those six points keep the trace's own
stage, WRITER; every CODE, INPUT and MEMORY point is counted as wrong-number-in.
