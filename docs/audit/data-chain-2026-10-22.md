# The data chain, source to screen (22 Oct 2026)

The owner asked (09:45 IST) four things: which data we collect, how it is cleaned, what goes wrong, and how it should
be shown for an investor's decision.

This is the first pass, by an independent read-only reviewer over the code: no AI calls, no live runs, 873 tests
passing. Findings are ranked by harm to an investor. Following the owner's rule, rounding is not counted as a mistake,
and neither is an AI reading that follows from the filing and memory.

"Verified" means checked in the code, or by running the pure function. How often each problem happens in live data is
measured next, by a no-AI scan of stored memory and cards.

## 1. What we collect

| Source | Module | Fields | When | Stored | Shown |
|---|---|---|---|---|---|
| NSE announcements + PDFs | `nse.py` parse_announcement, `extract.py`, `ocr.py` | headline, subject, seq id, attachment, broadcast time (IST) | every 15 min | D1 `filings`; text cache; R2 `raw/nse/`, `noise/` | cards, feed, noise audit |
| Results XBRL | `xbrl.py` parse, `nse.py` financial_results | 23-30 P&L lines (Ind AS, NBFC, bank, insurer); bank ratios; balance sheet; cash flow (H1/FY) | with each results filing | dossier `financial_metrics`, `balance_sheet`; standalone kept apart | results table, Financials, TTM, P/E |
| Event XBRL (Reg 30) | `event_xbrl.py`, `event_catchup.py` | order amount in rupees, counterparty, GST basis, dates, stage | minutes to ~92 h after the PDF | card, dossier `deals[]` | deal block, order-flow signal |
| Annual-report XBRL | `annual_xbrl.py`, annual catch-up | statements, related parties, KMP pay, contingent liabilities, auditor opinion, CARO | weeks to months after the PDF | prompt table, card | annual-report cards |
| Governance XBRL | `governance_xbrl.py`, `governance_memory.py` | board, committees, SEBI flags, fines, tax cases, loans to insiders | quarterly | dossier `governance` | governance lines |
| Shareholding | `nse.py`, `xbrl.py` _shareholding | promoter, FII, DII, pledge %; MF / insurer / FPI; holders over 1% | quarterly | dossier `ownership[]` | promoter / pledge tile, institutions |
| Pledges (SAST Reg 31) | `pledges.py` | event, % of share capital before and after, lender | each live run | dossier `pledges.events` | pledge signal |
| DGTR trade remedies | `dgtr.py` | case, stage, companies named | each live run | dossier | case block, signals |
| Prices | `market.py`, `yahoo.py` | close, volume, 1W/1M/3M/1Y, median turnover, technicals | daily | D1 `companies`, R2 `chart/` | card header, company page, chart |
| Shares / market cap | `market.py` (Yahoo `shares`) | shares x close | shares weekly, 150 lookups a run | D1 `companies` | market cap, size bucket, P/E, universe |
| Company master / universe | `company_master.py`, `universe.py` | ISIN, symbol, industry; in at ₹500 Cr, out below ₹400 Cr | each sync | D1, R2 `meta/universe.json` | Companies |
| Calls and presentations | pass 2, `call_summary.py` | guidance, operating notes, capex, analysts' concerns | per filing | dossier `guidance`, `call_points` | call cards, Earnings calls |
| Price reaction (Loop 1) | `learning.py` | T+1/3/5 excess return | post-mortem job | `cards.post_event_return_json` | internal |

## 2. How it is cleaned

**PDF path**, in order:
1. Rules.
2. Duplicates: within 3 days, an exact match or a 5-gram overlap of 0.9 with the same numbers.
3. OCR first on pages of figures, checked cell by cell against the text layer.
4. The declared unit.
5. The model's figures coerced: lakh x0.01, million x0.1, billion x100, brackets negative.
6. Grounding, unit-slip, foreign-currency and deal checks.
7. Hold when a check fails.

**XBRL path**, in order:
1. Contexts, with the legacy year-to-date fix.
2. The period label.
3. Rupees ÷ 1e7.
4. Ratios x100, with bounds.
5. Bank filler zeros dropped.
6. EBITDA = PBT + finance cost + depreciation - other income - exceptional items.
7. EPS given its profit's sign.
8. YoY/QoQ from the file's own comparative columns; none on a base of 0 or less.
9. Comparatives settled.
10. `fix_scale`: revenue and the implied share count off by the same power of ten.

**Memory:**
- XBRL beats cards.
- Consolidated is preferred per metric and period.
- H1 = Q1+Q2, 9M = H1+Q3 and FY = 9M+Q4 are checked.
- Balance-sheet fields 3x off are refused.

**Results table:**
- Comparatives are judged against the filing's printed text; a restated column is withheld.
- A quarter can be derived from cumulative periods.
- A change across a loss is named as a turn.

## 3. What goes wrong, by harm

### A. A wrong number a reader could trade on

| # | Finding | Status |
|---|---|---|
| A1 | **Years not ending in March are mislabelled.** `xbrl.period_label` and `periods.canonical_period` assume April-March. Jul-Jun gets no label (Gillette, P&G). Oct-Mar becomes "H2FY26" (Siemens' first half). Jul-Sep becomes Q2FY27 (Gillette's Q1). | verified in code |
| A2 | **Derived quarters look reported.** Q = H1 - Q1, 9M - H1 or FY - 9M is marked `derived` in memory, but the table drops the flag. A restated FY or a mid-year merger lands whole in Q4. | verified |
| A3 | **Bases can mix in one comparison.** Consolidated is preferred per metric and period, not matched to the current figure's basis. The company page labels its Consolidated tab by any one source. The TTM P/E mixes owners' profit and group profit. | in code; frequency not measured |
| A4 | **A US$ order can be stored as ₹ crore.** `DealValue` has no currency field, so "USD 138 million" grounds as 13.8 Cr. The order's share of revenue or market cap then comes out about 85x too small. | parsing verified |
| A5 | **EPS is not adjusted for splits and bonuses** across history. The TTM sums EPS across a split. | verified |
| A6 | **Market cap is wrong for up to a week after a split or bonus**: the new price times the old share count. The size bucket, the ₹400 Cr exit, "% of market cap" and P/E all move. | mechanism verified |
| A7 | **An old price passes as current** when Yahoo fails for a ticker; only a price that is too new is refused. | verified |
| A8 | **A revenue YoY comes back after its base was refused as restated.** | verified |
| A9 | **EBITDA depends on how exceptional items are signed.** The tagged profit before exceptional items is not read. | frequency not measured |
| A10 | **A bank ratio filed as a percentage under 1 would be multiplied by 100.** All 8 banks measured file fractions. | low risk |
| A11 | **The scale fixer could misfire on a real 10x change**, such as a reverse merger. | rare |

### B. Missing context

- **B1. Price and returns without a date.** The card header shows today's price and 1W/1M/3M returns on cards of any age, with no date.
- **B2. Company tiles without an as-of date or denominator.** This covers market cap, P/E, debt, net worth, promoter and pledge.
- **B3. Survivorship.** The universe uses today's market cap, so history statistics carry look-ahead bias.
- **B4. Holidays count as trading days** in the market-session label.
- **B5. EBITDA fallback.** The company page's fallback treats a missing exceptional item as 0.

## 4. What an investor needs next to each number

- The basis.
- The period and its end date.
- Whether it is reported, derived or adjusted.
- The source (XBRL, PDF, presentation or memory) and its filing date.
- An as-of date for anything market-based.
- Flags for restated figures, a year not ending in March, GST-inclusive amounts, and foreign currency converted at a stated rate.

## 5. Fix plan, in order (each testable without AI)

1. A1: store each company's year end and label periods by its own year, or refuse the label and flag it.
2. A2: carry the derived flag through to the table and statements, and show it as "derived".
3. A3: one basis per comparison, withholding comparatives of another basis; on the company page, show the basis by column.
4. A4: record the currency on deals, and show no ₹ ratio for a foreign amount without a stated rate.
5. A8: remove the stale revenue YoY.
6. A5, A6, A7: corporate actions. Adjust or blank EPS and share counts across a split or bonus, take the share count from shareholding XBRL, and refuse an old price.
7. A9: compute EBITDA from profit before exceptional items when it is tagged.
8. B1, B2: dates and denominators on the card header and company tiles.
9. Measure A3, A9 and the pledge denominator over stored memory, with no AI, before and after the fixes.

Progress on each is tracked in `docs/audit/work-2026-10-22.md` (item E).

## 6. Missing sources, measured (22 Oct 2026)

- **Corporate actions:** added (E6). NSE `/api/corporates-corporateActions`, history read 22 Oct: 14,305 rows listed,
  10,279 filed for 1,529 universe companies, 437 splits and bonuses, 0 errors; nightly `--days 30` after that.
- **Insider trades (SEBI PIT Reg 7):** NSE `/api/corporates-pit` (index=equities, a month at a time), measured
  22 Oct 2026 from a cloud IP: Feb 2026 1,279 rows, Mar 2,057, Apr 392, May 3 (last 2 May 16:46), Jun-Oct 0. Per
  symbol the same: Reliance's latest is 18 Feb 2026. Not found by `corporates-pit` for 3 May - 21 Oct 2026. The
  disclosures have moved somewhere this feed does not show (assumption: SEBI's system-driven disclosures through
  the depositories); where they now are is the next thing to find, before anything is built on them.
- **Bulk and block deals:** measured 22 Oct 2026 19:20 IST from the Actions runner with the pipeline's NSE session
  (`online-probe.yml`, check 13): `/api/historical/bulk-deals` and `/api/historical/block-deals` (7 days) return NSE's
  bot page (HTML, HTTP 200); **`/api/snapshot-capital-market-largedeal` answers JSON: today's 111 bulk deals, 4 block
  deals and 99 short-selling rows.** It holds the current session only, so history is built by storing it every
  trading evening (next: a nightly step with retries, a table, and the deals shown on the company page).
- **Insider trades, re-measured 22 Oct 19:20 IST from Actions:** `corporates-pit` over 7 days: 0 rows; for one symbol
  (Reliance) its default window returns 20 rows, the latest from 30 Sep 2021. `/api/corporate-sdd` (a guess at
  system-driven disclosures): 404. Still not found; next: NSE's SDD / PIT pages to find the address they call.

## 7. Event types: CORPORATE_ACTION is a catch-all (measured 22 Oct 2026)

Of the 86 stored cards typed CORPORATE_ACTION, 45 name a dividend, bonus, split, buyback, record date, rights,
delisting, reclassification, scheme or NCLT step; 41 (48%) do not: order wins (LTM, Advait), capacity starting
(Jindal Paradip port), stake sales (Swiggy's Lynks, RECPDCL's SPV, AGL), regulatory approvals (Zim Labs' TGA, Jaykay's
CDSCO licence), fundraises (Affle's warrants, Northern Arc's NCDs), a pledge release, a CP redemption (Titan), a
financial close (Ceigall) and one results letter (Eternal). The reviewers marked the class three times today (Caliber
Mining, Kopran, Neueon). What it costs an investor: the card gets the wrong blocks (no order size against revenue on an
order win, no results table on Eternal's letter, no deal block on a stake sale) and sits under the wrong filter.

Cause: the gatekeeper prompt (pass1.md) and pass 2 offer the event types as a bare list of names with no meaning
attached; CORPORATE_ACTION reads as "anything the company did". **Proposed (owner's decision, not built):** one line per
event type in both prompts ("CORPORATE_ACTION: dividend, split, bonus, buyback, record date, rights entitlement,
delisting, name or face-value change - not an order, a stake sale, a licence or a fundraise"), measured on live cards
the day after (the share of CORPORATE_ACTION cards that are corporate actions, now 52%), as the no-AI-for-testing rule
allows only live measurement of a prompt change.
