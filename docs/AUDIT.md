# 360° audit: findings (resolved)

Status (2026-10-16): all 6 area reports were received and the findings were fixed in these commits.
The list below is kept as the record of what was found; it is not a to-do list. What is still open
is listed at the end and in [PLAN.md](PLAN.md) ("Pending work").

| Findings | Fixed in |
|---|---|
| 1, 19, D1–D7, A1–A3 (D1 read/write cost, queue scans, no-op writes, budgets) | `2b46df3`, `627b7ef` |
| 2, 18 (sync-companies workflow, stale docs) | `788f879` and the sync-companies workflow |
| 3–13 (frontend honesty, Safari, error boundary, footer units) | `627b7ef` |
| 14 (subject and symbol in the ledger) | `2b46df3` (migration 0003) |
| 15–16, A4–A15 (orchestration, commits, attempts, live vs backfill) | `2b46df3`; saving every 5 filings `fc51611` |
| 17, B1–B11 (formula, second opinion, outages, null shapes, event type, R1) | `2b46df3`, `a536c09` |
| A16–A17 (triage drops, boilerplate) | `e614539` |
| M1–M15 (grounding, bi-temporal memory, periods, claims, caps) | `61c3892`, `b6232ac`, `788f879` |
| Low items (README count, ERROR exit code, assets binding, lakh/million...) | across the commits above |

## Critical / high

1. **`/api/system` can exhaust D1's 5M rows-read/day.** It counts every PENDING/FAILED row
   (walks `idx_filings_queue`) and `cards_7d` filters on `filing_date` (no index). During backfill a
   call reads ~100–175k rows; the feed side rail calls it on every page view (CSS-hidden on mobile,
   still fetched) and the System page polls every 30 s. Workers responses are not edge-cached without
   the Cache API. Fix: cap counts (`SELECT count(*) FROM (... LIMIT 1001)`), filter `cards_7d` on
   `filed_at`, drop the rail's call or poll every 5 min; correct SPEC/comment.
2. **`sync-companies` never runs.** No workflow calls it, so `companies.industry` stays NULL: every
   card uses the default sector lens, peer context is empty, and the backfill order by market cap
   falls back to "busiest first". Fix: weekly workflow on the self-hosted runner + README step.
3. **"Numbers verified" can be false** (`AnnouncementCard.tsx`, `FilingCard.tsx`): shown whenever
   `needs_review = 0`, but up to 30% of numbers may be unfound (threshold 0.7). Fix: show it only when
   `ungrounded` is empty and no math mismatch; otherwise "N of M numbers verified".
4. **Copied PNGs never carry the "Unverified" warning.** Fix: keep a one-line warning in the export.

## Medium

5. `URLSearchParams.size` (`web/src/lib/api.ts`) is undefined on Safari 16 / iOS 16: requests go out
   without query strings. Fix: use `qs.toString()`.
6. Infinite lists replace all loaded data with an error on one failed page fetch (TanStack v5 keeps
   data). Fix: render data when present, inline retry.
7. Scroll handling: scroll-to-top also runs on Back; `?card=` changes don't scroll; `SharedCard`
   shows nothing while loading or on 404.
8. Copy-as-PNG fails on Safari/iOS (clipboard write after an await). Fix: pass a Promise to
   `ClipboardItem`; fall back to download on rejection.
9. `coveredByTable` (results de-dup): period-label regex misses "Q2FY27"; matches PBT/EPS/prior values
   not shown in the table; hides bullets even when the table renders nothing.
10. Cards view: facts beyond 3–4 and key numbers are unreachable (Full analysis doesn't list them).
11. Results page: client-side quarter/verdict filters hide "Load more" when the first page has no
    match; quarter options sorted as strings.
12. GNPA footer could show a ₹ Cr amount as a percentage (no unit check). Being replaced by
    sector-specific footer metrics (`sectors.toml` `footer`); the UI still needs to render
    `fundamentals.kpis` with unit checks.
13. No React error boundary; `/calendar?month=x` throws and blanks the page.
14. Filing `subject` and `symbol` are not stored in the ledger, so queued filings lose the BSE subject
    line (Pass 1 prompt, grounding source) and the symbol. Fix: migration adding both columns.
15. System view's backfill bar measures discovery only; company-by-company analysis progress is not
    shown. `backfill:start` is read but never written.
16. Backfill re-discovers live days (noise_count written for days whose noise rows are stored). Fix:
    advance `backfill:discovered_through` after live discovery.
17. Prompt's worked example formula is off by 1000× (`capacity_mw * plf * 8760 * tariff_inr / 1e7`
    gives 0.0313, not 31.3). Fix: add `* 1000` in engine.py schema and pass2.md.
18. Docs stale: SPEC §3/§8/§12 (backfill now company-first, noise not stored, history first,
    `BACKFILL_PRIORITY_MCAP_CR` removed), §6 (second opinion, `SECOND_OPINION`), labels
    ("Unverified", "Verified after a second check"), roadmap (pull-forward done).
19. Backfill company order is rebuilt every run while discovery advances (adds to item 1). Fix:
    rebuild only on a new day or an empty list.

## Low

- README test count and `--time-budget` default; SPEC estimate cap (prompt says 3, code allows 5);
  "all tested" claim for gateway rules; System "Failed" tile text and count; tuning env vars not passed
  from Actions; `wrangler.jsonc` assets has no `binding: "ASSETS"`; `PLATFORM_API_URL` / `INGEST_TOKEN`
  setup not spelled out; a run ending in ERROR exits 0 (workflow stays green); scorecard tiles too
  narrow at 390px; results row expansion on mobile/keyboard; "Filings analysed" capped at 60;
  "Moderate" vs "Medium impact" wording; hard-coded "2026" labels; calendar error state; key-number
  keys can collide; `cr(-50)` gives "₹-50 Cr"; Companies search not in URL; object URL not revoked;
  palette aria-activedescendant; placeholder D1 `database_id` in `wrangler.jsonc`.

## Memory, checks and signals (report 3)

Critical / high:
- **M1. Grounding is far too permissive for %, bps and pp.** SCALES (×10, ×100…) and
  `_derivable_percent` (any pair a≈b(1±p)) accept ~100% of integer percents and ~98% of bps on a
  realistic results statement; a card with every ₹ figure invented scored 0.733 (passes 0.7). Fix:
  percents only at scale 1/0.01; derive % only from nearby, similar-sized pairs; differences only for
  pp/bps; any ungrounded headline ₹ figure forces review.
- **M2. Signals and footer see future facts during backfill.** `compute()` and `latest_fundamentals`
  use the whole stored dossier, so a May order is sized against October revenue; dilution uses today's
  share count/price; guidance status is read as of now. Fix: filter by `as_of` before computing.
- **M3. Re-reported comparatives take over a fact's as_of and source.** A Q2 results filing restating
  Q1FY27 moves that fact's as_of to October: time travel loses it, the backfilled Q1 card's results
  snapshot picks the wrong quarter, re-analysis deletes it. Fix: keep `known_since` and per-source
  values; choose the snapshot quarter from the filing's own delta.
- **M4. Memory view keeps the latest N rows by as_of, not the latest N periods.** A presentation with
  7-year history pushes all quarters out of the prompt. Fix: pick latest N by period end per kind.
- **M5. METRIC_SHIFT / WORKING_CAPITAL_STRAIN fire on comparative columns** (e.g. "PAT up 150% YoY
  (Q1FY27)" on a Q2 card). Fix: only the filing's latest period of each kind.
- **M6. Re-analysing the filing that created a guidance/watch item wipes later status history.**
  Fix: keep the item, drop only that filing's history entries.

Medium:
- M7. `_to_float` strips "lakh"/"crore"/"million" without scaling (`"₹85.50 lakh"` → 85.5 Cr).
- M8. Formula evaluator can raise non-FormulaError (complex powers, overflow, recursion) and fail the
  whole filing.
- M9. Integers ≤31 always pass and still count as checked (small-cap ₹ Cr figures).
- M10. Period labels like "Q2FY27" leak phantom numbers; the year rule strips "2050.45" → 45; "INR1,234"
  misread.
- M11. Takeaway and insight numbers are never grounded.
- M12. "basis points", "per cent", "3.1x" not recognised as units → correct figures flagged.
- M13. Periods not normalised ("Q2FY2027" vs "Q2FY27"; "Sep 2026" vs "SEP-2025"); `due_date` wrong for
  "FY2026-27", "Q2 FY 2026-27", "Q2-FY27", "30-09-2026", "November 15, 2026".
- M14. `check_claims` false positives/negatives ("further orders" anywhere defeats every "first";
  "track record"; bold "**maiden** order" skipped; "first quarter" supports "maiden order").
- M15. Size caps drop backfilled history (600 metric rows; watchlist 80 drops OPEN items).

Low: quant tolerance absolute 0.05; formula names not normalised; UNCHECKED never reviewed; buyback
shown as dilution; dilution should be new/(old+new); equal-to-high order wording; negative net worth
ratio; null/% metric units; guidance given_on not moved back on backfill.

## AI layer, prompts and models (report 4)

High:
- **B1. The second opinion replaces the whole reply, not just the card.** A verifier reply with only
  `{card}` wipes the filing's dossier delta (financials, deals, guidance). Fix: adopt only `card`.
- **B2. The prompt asks for numbers the grounding check rejects** (proportions such as "18% of FY26
  sales", computed EBITDA/margins): most results and order cards go to review plus a second call.
  Fix: accept ratios of grounded figures; computed figures belong in quantified_impact.
- **B3. Timeouts, 5xx and connection errors count as hard failures**: three outages drop a filing
  for good. Fix: raise them as transient; count attempts only for content failures.

Medium:
- B4. Null/number shapes (`key_numbers: null`, numeric `value`, `track_next: null`, `takeaway: null`,
  `dossier_delta: null`, `balance_sheet: []`) fail the whole reply.
- B5. R1 output with only a closing `</think>` is parsed from inside the reasoning.
- B6. Non-JSON 200 bodies raise AttributeError (no failover); `_second_opinion` catches only
  AllProvidersFailed, so any other error fails a filing whose card was fine.
- B7. Pass 2 overrides Pass 1's event type with OTHER or the example's "RESULTS". Fix: show the
  current type and the allowed list; keep Pass 1's when Pass 2 says OTHER.
- B8. Copied placeholders ("HIGH | MODERATE | LOW", "string or null") become confident values;
  call_read kept on non-call events; new deal stages missing from the schema and aliases.
- B9. Claim checker vs prompt: memory-based "first/record" always flagged; `is_repeat` scans memory;
  "track record" flagged.
- B10. The gateway ignores the run deadline (pacing, 180 s timeouts, second opinion, retry sleeps): a
  filing started near the deadline can outlive the job timeout and lose the uncommitted batch.
- B11. R1 at temperature 0.1, non-streaming, 8k tokens against a 180 s timeout; model id to verify.

Low: usage baseline updated before the D1 write succeeds; 429/connection errors keep their usage
estimate; JSON-mode fallback triggered by any 400 mentioning "json"; per-entry timeout ignored by the
client cache; vision route thinking/truncation; standalone vs consolidated metrics mix; lakh/million
not scaled; one route's ceiling stops all routes; "Aerospace & Defense" and "Industrial Gases" lens
patterns.

## SQL, D1 and Worker (report 5)

Critical:
- **D1. `filings_pending` reads every PENDING/FAILED row on every call** (planner picks
  `idx_filings_queue (status=?)` without stats; confirmed with EXPLAIN QUERY PLAN). The live loop and
  the backfill-complete check together read ~8–15M rows/day during backfill; once D1's read limit is
  hit, the site and the pipeline both fail until 00:00 UTC.
- **D2. `/api/system`** (same as item 1).
- **D3. `/api/feed` walks the whole cards index** whenever a window has fewer than limit+1 matches
  (Today early on, rare filters, the last page of every scroll, `?from=2999-01-01`). ~146k rows per
  request at one year.
- **D4. `/api/search`** sorts every FTS match (a 2-letter prefix like "li" matches almost every card).
- **D5. No edge caching or rate limiting exists**: Worker responses are not cached from
  Cache-Control headers.

High:
- **D6. D1's 500 MB per-database limit** is reached in roughly a year with `card_json` inline.
- **D7. Write budget**: `companies_au` fires on every companies upsert (5 rows written per price
  update); market-data and CLI writes are not counted; backfill analysis is not gated on the budget.

Medium: backfill order rebuilt every run (also when the list is empty); `/api/companies` sorts scan
all companies, no tie-break; `peer_cards` scans a category's whole window for rare sectors;
`catalysts_upsert` rewrites today's catalysts every run; the platform sink retries non-idempotent
statements (`usage_add`, `filings_update` attempt counts) and SQL errors.

Low: `usage_for_month` scans all usage rows; noise_count for live days (item 16); assets binding
missing (500 for unknown files); empty R2 list prefix lists the bucket; double URL-decoding; `__proto__`
sort key; `/noise` OFFSET paging not stable; malformed internal JSON gives 500; LocalSink re-runs
every migration; dossier re-serialised; error text published by `/api/system`; SPEC write-cost note.

## Ingestion and orchestration (report 6)

Critical / high:
- **A1. Queue scans** (same as D1): ~400k rows read per run including the completion check and the
  order rebuild.
- **A2. The write budget gates backfill discovery only**, not backfill analysis (~25 writes per card).
- **A3. No-op writes**: catalysts rewritten every run; `companies_au` fires on unchanged names (same
  as D7); market-data writes not counted.
- **A4. History first starves live work**: a live company's whole pending history (up to 200
  filings) runs inside the live budget; the batch commits only when every group finishes.
- **A5. Yesterday's unfinished live filings fall into the backfill order after 09:00 IST** and can
  wait days behind thousands of larger companies.
- **A6. A 403 on one attachment poisons every run**: SourceBlockedError aborts the run, the batch's
  finished work is never committed, the filing's attempts never grow, AttachHis is never tried.
- **A7. A failing history filing burns all its attempts in one run** (retried by both the history
  step and the company backfill).
- **A8. Commit granularity vs the job timeout**: a backfill batch commits once at the deadline; a
  kill at 55 min loses it, leaves the run RUNNING and the write counter stale.

Medium:
- A9. A discovery error (HTML body, 5xx, timeout) aborts all processing for the run.
- A10. An empty BSE response advances the backfill cursor for good.
- A11. `process()` exits early when a whole batch was already seen (retryable FAILED at the head).
- A12. Download timeouts/5xx, files over 30 MB and spent OCR quota are analysed as "no text", final.
- A13. The D1 write counter carries yesterday's total into the new UTC day.
- A14. Every run re-pages the whole day from BSE (politeness, block risk): stop at known pages.
- A15. memory_complete wrong in several paths (FAILED history counted as finished; leftover live
  days; `backfill:complete` never cleared).
- A16. Triage drops material filings: "Board Meeting Intimation … Closure of Trading Window",
  "Results … and Newspaper Publication", "Results with Investor Grievances", board-meeting outcomes
  whose headline lacks "outcome".
- A17. `strip_boilerplate` deletes factual lines ("Mr. X (DIN: …) appointed as MD", "shifting of the
  Registered Office: …", "NCDs will be listed on BSE Limited").
- A18. 500 MB D1 cap (same as D6); live noise rows add ~2 MB/day.
- A19. `peer_cards` scans a whole event type (same as report 5).

Low: setup-python on a self-hosted ARM/Debian runner; BSE paging has no page cap or de-dup;
usage_for_month scan; usage deltas lost on a failed write; a test fails between 00:00 and 00:05 IST.

## Checked and found consistent

SQL statement/query whitelists, parameter counts and JSON field names (Python ↔ Worker ↔ db/); KV
key names; R2 prefixes; env var names for keys and platform; CLI commands; config files and keys;
thresholds in docs; card contract with older stored cards (no crash paths); hooks order; dark-mode
tokens; routing and SPA fallback; Telegram/WhatsApp/X fully removed.

## Still open after the fixes

- D5: responses are memoised and use the Cache API where available, but there is no per-client rate
  limiting (the free plan has no built-in one). Revisit if the site gets abusive traffic.
- D6/A18: the 500 MB D1 cap is watched (the System page shows the size) rather than removed; card
  JSON stays inline. Move it to R2 if the size approaches the cap.
- `size_category` is still only on companies (tracker, "Points to discuss" 3): size filters join.
- The midnight-IST test failure (low, report 6) was fixed in `c1d3de3`.
