# 360° audit: findings (in progress)

Status: 3 of 6 area reports received (frontend; contracts and docs; memory/checks/signals). Still running:
ingestion/orchestration, AI layer and prompts, SQL/D1/Worker.
Nothing below is fixed yet unless marked **fixed**. Each item was reported by an auditor and
still needs verification before fixing.

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

## Checked and found consistent

SQL statement/query whitelists, parameter counts and JSON field names (Python ↔ Worker ↔ db/); KV
key names; R2 prefixes; env var names for keys and platform; CLI commands; config files and keys;
thresholds in docs; card contract with older stored cards (no crash paths); hooks order; dark-mode
tokens; routing and SPA fallback; Telegram/WhatsApp/X fully removed.
