# Audit 137: stale standalone and overdue guidance (live site, 30 Oct 2026, read only)

Sample (20, BSE scrip): 500034 BAJFINANCE (NBFC), 500180 HDFCBANK, 500247 KOTAKBANK (banks), 540716 ICICIGI, 540719 SBILIFE (insurers),
500209 INFY, 500325 RELIANCE, 500470 TATASTEEL, 500510 LT, 500875 ITC, 512599 ADANIENT, 524715 SUNPHARMA, 532500 MARUTI, 532978 BAJAJFINSV,
500338 PRSMJOHNSN, 500870 CASTROLIND, 532811 AHLUCONT, 519552 HERITGFOOD, 532928 TARIL, 533022 20MICRONS. 25 requests made.
Page code: web/src/components/company/Financials.tsx (tables), statements.ts (mainBasis :39, screenerTable :333), CompanyPage.tsx (promises), companyText.ts:353 overdue().

Finding up front: the quarterly, annual, balance and cash-flow tables (dossier.statements) are in step between Consolidated and Standalone
for 17 of 20 (same latest quarter, same FY). Companies still on Q1FY27 (ITC, SUNPHARMA, TATASTEEL, BAJAJFINSV, AHLUCONT, PRSMJOHNSN) have
no Q2 card or file yet, so that is not stale. "Stale standalone" is narrower than it sounds (classes A1-A4).

## A. Stale / wrong standalone

| Class | Scrip | Shown | Expected | Cause |
|---|---|---|---|---|
| A1 standalone block (dossier.standalone) not refreshed | ADANIENT 512599 | Standalone view: growth boxes, ratios and fallback tables read standalone.metrics: latest quarter Q1FY27 (9 quarters), latest FY24, balance Q4FY24 | statements already hold standalone Q2FY27; metrics should reach Q2FY27 / FY26 | Financials.tsx:21-35 feeds `growth()` and `ratioTable()` from `alone.metrics`; the block is written only by put_standalone (dossier.py:791), called from pipeline.py:3886/4160 when the live run has the standalone file, and seed.py:360-385. Q4FY25/Q2FY26/Q4FY26 standalone files never reached it |
| A1b standalone statements have holes | ADANIENT | Standalone annual / cash flow end FY25, quarters miss Q2FY26, Q4FY25, Q4FY26, balance misses Q4FY25, Q4FY26 (consolidated has all, FY26) | FY26 standalone | statements for STANDALONE built only from files the run saw (pipeline.py ~3886 `standalone_file.raw`); the Q4 standalone file was not fetched or not parsed |
| A2 wrong basis label | ICICIGI 540716 | Page says "Consolidated" though every figure is standalone | "Standalone" | statements.ts:39-47 `mainBasis` returns CONSOLIDATED if any one metric is; ICICIGI has one stray `solvency_ratio Q1FY27` tagged CONSOLIDATED (lab by=unknown, doc=other). Financials.tsx:27 then labels, and `screenerTable(...,"CONSOLIDATED")` is empty so the fallback runs |
| A3 standalone-only filers missing tables | CASTROLIND, ICICIGI, SBILIFE | Castrol: quarters only, no annual / balance / cash flow (fy_end_month = 12, Financials.tsx:62 hides yearly tables). ICICIGI: no quarterly statements at all, only cash_flow FY25-26. SBILIFE: no balance sheet | tables from the exchange files | statements.py has no insurer family (TODO 129); Castrol is a December filer, `due_date`/period labels assume March (periods.py:195) |
| A4 standalone source on a consolidated metric | ITC (5), MARUTI (14), AHLUCONT (7), TARIL (16) metric entries | metric `basis` is None, `sources` hold CONSOLIDATED and STANDALONE values together (ITC FY26 revenue 89,913 consolidated vs 80,867 standalone from an AI source; AHLUCONT order_inflow FY26 shows 10,257.4 from a STANDALONE source against 4,521.06) | one basis per entry | dossier merge keeps both sources under one entry when the AI card does not state a basis (dossier.py merge, `_entry_basis`). Top value is consolidated in ITC/MARUTI/TARIL today; AHLUCONT order_inflow looks wrong |

Hit count (of 20): A1/A1b 1 (Adani Enterprises), A2 1 (ICICIGI), A3 3, A4 4. Any class: 8 of 20.

Fix by class:
- A1: after any results run, rebuild `dossier.standalone.metrics` and `.balance_sheet` from the stored standalone statements / facts (same source as `dossier.statements`), or make growth()/ratioTable() read the statements tables for the chosen basis. A maintenance pass over companies whose standalone latest period < consolidated latest (Adani first).
- A1b: re-fetch the missing standalone files (res-sa) for periods absent from `statements` where the consolidated one exists; the exchange file first.
- A2: `mainBasis` should count only metrics from file/results sources and use the majority (or the basis of the latest results filing), not "any". Also ignore ratio metrics with doc=other.
- A3: finish TODO 129 (bank / insurer families); for December filers pass fy_end_month into due_date and the yearly tables.
- A4: store a basis on every entry; refuse to attach a source of another basis to an entry (split into two entries); never let an AI source with no stated basis join a file-tagged one.

## B. Guidance

Sitewide /api/promises/overdue: 150 rows, 122 OPEN, 19 ON_TRACK, 9 REVISED; none has a verdict. Of the 150, 79 are not past their results window.

| Class | Scrip | Shown | Expected | Cause |
|---|---|---|---|---|
| B1 overdue counted from period end | sitewide: 62 Q2FY27, 8 H1FY27, 4 Sep-2026, 3 "Q2FY27 onwards" (INDIGO, MATRIMONY, DALBHARAT, BAJAJ-AUTO ...) | "Not reported", red due date, "30 days overdue" on 30 Oct | not overdue before results are due (14 Nov for Q2) | the pipeline already has the rule (dossier.py:1335 `judged_on`, periods.py:218 `results_due`, O12) but the page and API do not: companyText.ts:353 `overdue()`, CompanyPage.tsx:443 `isLate`, web/worker/public.ts:522-527 and radar.py:171 `earliest_open_due` compare raw `due_date < today`. None of my 20 hit it (0/20), it is a Q2-season effect |
| B2 no verdict after the actuals are in | AHLUCONT (9 FY26 items OPEN/ON_TRACK/REVISED, FY26 revenue 4,565 Cr and Q4FY26 results are stored), PRSMJOHNSN (3: capex FY26-27, FY26 cement growth, "Q2FY26 raise 300 Cr" 395 days), CASTROLIND (2), HERITGFOOD (milk 2 MLPD by FY26, still ON_TRACK, 213 days), TARIL (Q2FY26 production, 395 days) | OPEN / ON_TRACK long after due | delivered / missed / not reported with the actual | verdicts only come when an AI card emits promise_updates (dossier.py:1330-1343) and passes F172 `why_no_verdict` (guidance_dated.py); nothing sweeps after `results_due` and compares the due period's stored actual to `metric` / `target`. `relative_guidance_verdict` (watch_code.py:374) covers only relative targets. Also REVISED is left out of `overdue()` and `isLate`, so a revised past-due target never shows as late. promiseStats (CompanyPage.tsx:205-211) counts overdue items in "Open" |
| B3 due before it was said | CASTROLIND g_d9bc7969, g_4cf42c3d, g_90c97c9a (FY26 = 31 Mar 2026, given 10 Aug 2026), TARIL g_d766775e (Q2FY26 given 21 Apr 2026); 7 sitewide | 213 / 395 days "overdue" at birth | no date, or the date derived from the company's own year | periods.py:186-196 assumes March year end (Castrol is December); the new-guidance code (dossier.py ~1318) does not reject `deadline < given_on` |
| B4 no due date, never overdue | 18 items in 8 of 20 (HDFCBANK 4 of 5, RELIANCE 2, PRSMJOHNSN 4, HERITGFOOD 3, TARIL 2, INFY, SUNPHARMA, CASTROLIND 1 each) | due "—" | fine by F172 (undated stays "said on"), but they pile up as OPEN | by design; no expiry |
| B5 fragment statements | AHLUCONT "it would be about 15%.", "our margin should increase.", "Same, 15% to 20% growth.", "we will maintain what I had projected last time [.", plus duplicates of the same FY26 15% revenue target (g_274eb0c6, g_6d392001); 13 of 150 overdue rows under 35 characters | | a full sentence naming the metric | raw transcript sentence stored as `statement`; the duplicate check (dossier.py ~1318) needs equal metric+target+due_date |

Hit count (of 20): B2 5, B3 2, B4 8, B5 1 (Ahluwalia), B1 0 (79 sitewide). Any class: 12 of 20 (20 minus the 8 with no open past-due items and no undated items).

Fix by class:
- B1: use one rule everywhere: compute `judged_on` / `results_due` into the stored promise (`overdue_from`) and have `earliest_open_due` (radar.py:171), public.ts, companyText.ts `overdue()` and `isLate` use it. Include REVISED.
- B2: add a no-AI sweep (Maintenance) that, once `results_due(due)` has passed, reads the due period's figure from the stored exchange facts (dossier.financial_metrics file-tagged, same basis) and sets DELIVERED / MISSED by `target`; when no numeric target or no figure, set a "NOT_REPORTED" status with the date. Figures from the exchange files first; the AI only words it.
- B3: reject or null `due_date` earlier than `given_on`; pass `fy_end_month` into `due_date()`.
- B5: drop statements shorter than a sentence or starting lowercase / pronoun; dedupe by metric + period + target.

## C. Other blank or wrong (one line each)
- ICICIGI: segment_mix only 6 rows, one "Crop Insurance 3.49 Cr" revenue; SBILIFE segment_mix 2 rows (share only, no revenue).
- segment_mix newest period is Q4FY26 for 15 of 20 while results are at Q1/Q2FY27 (PR #236 backfill pending).
- dossier.balance_sheet mixes period labels ("Sep-2026" vs "Q4FY26") for KOTAKBANK, ADANIENT, HERITGFOOD, TARIL, 20MICRONS, ICICIGI.
- dossier.business_summary empty on 17 of 20 (page falls back to `story`; not checked what `story` shows).
- No guidance at all for KOTAKBANK, LT, ITC, MARUTI, BAJAJFINSV, 20MICRONS, ICICIGI (7 of 20); upcoming_events empty for BAJFINANCE, HDFCBANK, KOTAKBANK; LT has no calls.
- Castrol (December year end): banner hides all yearly tables; quarters named on the April-March convention (Q2FY27 = Jul-Sep 2026).
