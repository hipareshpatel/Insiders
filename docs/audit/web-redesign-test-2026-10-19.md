# Redesigned Today and company pages: laptop test, 2026-10-19 22:00 IST

Commit tested: 92e301d, merged with bf85e1f. `npm install` and `npm run typecheck` were clean. The site was restarted for the
Manrope package; before the restart it failed with `Failed to resolve import "@fontsource-variable/manrope"`. The dev server
also exited once with no error, about 3 minutes after starting. Restarted, it then stayed up. The data is the local
D1 and R2 (audit-round companies plus the go-live seed, at 162 of 1,778 companies).

Scrips tested: 519552 HERITGFOOD (8 results quarters, segment mix, 6 ownership quarters), 542867 CSBBANK (bank, 7
quarters), 530019 JUBLPHARMA (pledge in memory). Today page: Since close / Today / 7 days.

No console errors and no failing `/api` call after the restart. Every call returned 200 in under 0.1 s. Rows read are not
shown locally: the System page reports only `d1.writes_today` and size.

## Page bugs (the data exists)

1. **`/api/brief` counts "Filings read" and "Noise filtered" for the first day and today only.** `days` is
   `[fromAt.slice(0, 10), todayIst()]` (`web/worker/public.ts`, the `/brief` handler), so the days between are skipped.
   7 days from 2026-10-12: page shows 40 read, 14 noise (35%). The local D1 has 127 `filings` rows with
   `filed_at >= 2026-10-12`, and the `noise_count:` keys for 10-12 to 10-18 add up to 81. As a result "Cards 43" is
   larger than "Filings read 40".
2. **The headline and "For you" count include held cards.** "43 filings worth your time", the For you badge 43 and
   Today's mix "43 cards" all count `cards` with no held filter. For the 7-day window 11 of those 43 are held (10 low,
   1 moderate); the public feed lists 32. The sector bars already use `held = 0`.
3. **Results tab, phone width (390 px): the page scrolls sideways.** The "Quarterly results" bars section and the
   "Business mix" section are 427 px wide (`scrollWidth` 443); the eight bars, the Revenue/Profit/Margin toggle and
   the mix percentages are cut off on the right. URL: `/company/519552?tab=results`. The Today page, the company
   Overview and the Ownership tab fit (scrollWidth = 390).
4. **Business mix sums overlapping segments.** Heritage Q2FY27 ring centre reads "₹3,224 Cr" against revenue ₹1,320 Cr.
   The shares are Milk 58%, VAP incl Ghee/Butter 43%, Dairy 40%, VAP excl Ghee/Butter 35%, Nutrivet 7%, Feed 3%, which
   add up to 186%. `segment_mix` holds nested and alternative cuts (Dairy contains Milk and VAP; VAP is given incl and
   excl). The ring should not add up rows that overlap. The data is partly at fault too (see data item 6).
5. **The header overflows at about 1,000 px.** At a 1,009 px window the top bar (search box and the button after it)
   ends at 1,025 px, so the page scrolls 16 px sideways, and "All filings" wraps onto two lines.
6. Minor: at about 800 px the key-figure labels are cut ("Revenue · Q2…", "Avg traded a …", "Filings analys…").
   A bank's scorecard shows EBITDA "—" and OPM "—" on every quarter (CSB); hiding those rows for banks would read better.

## Checked and right

- Today top figures equal `/api/brief` (apart from item 1); the signals strip is empty and 0 cards pass all four gates;
  High impact shows 0 (no HIGH card in 7 days); `+ Low impact` goes from 15 to 32 cards; Results 7, Capex & orders 7,
  Capital & deals 12, Governance 2; size, sector, session and text filters change the URL and the list; Verified only
  leaves 32 because no published card needs review in the window; Watchlist 0 (no company starred). Moderate paging
  past 20 could not be tested: there are 15 moderate cards in the window.
- Right column: the mix donut, results scorecard (6 rows), coming up (8 catalysts), overdue promises, watchlist (empty)
  and sector bars all render. The radar is hidden because `/api/radar?min=3` returns no company (none has 3 trigger
  kinds in 90 days).
- Company headers: price, 1W/1M/1Y, mcap and size match `companies`. Revenue, Debt and Net worth match the newest card's
  `fundamentals` (CSB debt is null, so "—" is right). Promoter and pledge come from the last `ownership` entry
  (Jubilant 47.68%, pledge 6.58%; Heritage has no pledge field, so none is shown). Latest PDF opens the newest filing.
- Results bars agree with the financial table (Heritage revenue 1,034 to 1,320). Ownership bars add up to 100 with
  Public as the remainder (labels under about 5% are hidden; the values are there). Peers are the same sector, nearest
  in mcap, and their links open company pages. Promises kept 75% = 3 / (3 + 1) on Heritage's tracker. "Next catalyst:
  none scheduled" is right: every `upcoming_events` date is before today.
- Phone width: no sideways scroll except item 3; the tab strip scrolls inside itself. Light and dark both render.

## Data gaps (the page is right, the data is missing)

| Check | State | Filled by |
|---|---|---|
| A4 prices | 4,990 of 5,251 companies priced, 4,409 with 1W, 4,840 with mcap, 4,340 with technicals, 4,990 with turnover; 1,017 with sector `default`/null. HERITGFOOD has no 1W/1M/1Y and no technicals | `market-data` |
| B4 governance | `governance.quarters` empty for all 3 companies tested (auditor present). The go-live load's step 3 `governance-sync` failed at 17:23 on the laptop's network (`getaddrinfo failed`) | `governance-sync`, re-run with `golive_load.ps1` |
| B4 ownership | Jubilant skips Q4FY26 and Q1FY26 (Q4FY25, Q2FY26, Q3FY26, Q1FY27 present) | `seed-memory` (53 file failures so far, NSE timeouts) / `shareholding-sync` |
| A10 health line | `pipeline_runs` is empty locally, so the line shows "25 filings failed in the queue" instead of the last run | written by the online run only |
| A5 scorecard | works; the verdict is read from the card (`results` block), not `$.results.verdict` | - |
| Overview story | JUBLPHARMA has no `business_summary` | memory refresh |

Content problems seen on the way (pipeline, not web; they go to the accuracy loop):
1. **Card arithmetic.** Heritage Q4FY26 scorecard says PAT +16.7% YoY, but the PAT went from ₹38.17 Cr to ₹23.94 Cr, which is −37%, as the card's own verdict says.
2. **Two results cards disagree.** Heritage Q2FY27 has two timeline entries with different figures: revenue +19% against +16% YoY, and PAT −39%; the scorecard says +21.0% and −36.2%. Q2FY26 is ₹1,090 Cr in memory and ₹1,113 Cr on its own card, which may be a restatement.
3. **Promises and guidance.** Overdue promises lists a rating agency's expectations as the company's promises (Prism Johnson, "Ind-Ra expects ..."), and calls "due FY26-FY27" 202 days overdue. Heritage's Q2FY27 targets are still Open after its Q2FY27 results, and the same metric appears three times with different targets.
4. **Group entities and calendar.** The group-entities list includes a lawsuit's defendants (Meta, Google, X Corp, a ministry) and a plant. The calendar shows Shivam Autotech's rights issue opening three times (Rights Open, Milestone, Other).

## Re-check on efbe96b (2026-10-19 22:45 IST)

621 pipeline tests pass (one more than the cloud's 620); `npm run typecheck` is clean.

**The five page bugs are fixed.** 7 days: Filings read 208 (127 filings + 81 noise, as in the database), noise 81
(39%); the headline, For you and Today's mix say 32 with the 11 held shown only as "To verify"; `/company/519552?tab=results`
at 390 px has scrollWidth 390; Business mix lists each segment with "the cuts overlap" and no total; the header at
1,009 px has no sideways scroll. New, minor: at 390 px the bar chart's quarter labels are cut ("Q3FY…").

**The five filings re-processed** (`process --news-ids`, FREE_ONLY, after `/api/owner/requeue`). Cards before the run
are kept locally in `data/audit/newblocks/before.json`.

| Card | news_id | Result |
|---|---|---|
| CSB Bank Q1FY27 (bank) | 33717cd4-0f00-47c3-9a26-9c79acb7b4d4 | Right: headline "net profit ₹150.04 Cr (+26.5% YoY); net NPA 0.39%, gross 1.75%"; the table has interest earned, NII, operating profit, provisions, PBT, PAT, gross/net NPA, RoA and EPS with Q4FY26 and Q1FY26 columns; since the filing ₹370.15 → ₹310.8 (−16.0%); run-rate P/E 9.0x. **Wrong: "Management said, Nov 2025: credit cost 40-50 bps · by FY26"**: that target was due before this Q1FY27 card, so it is stale. The recall should skip guidance already due (or show its outcome). Its second recalled item is an RoA explanation from the call, not guidance (hidden on the card, but it is in `guidance_recall`). |
| Ramco Cements Q1FY27 | nse-106731799 | Right: revenue, EBITDA, margin, exceptional items, PBT, PAT and EPS with both comparison columns; recurring one-offs line; run-rate P/E 148.9x = 18,602 ÷ (31.24 × 4). |
| Ceigall ₹214.52 Cr LoI (order) | nse-106801864 | Right: the size against Q1FY27 (22%) and FY26 revenue (5.3%); the 5-year term (the filing says "for a period of five years") gives 1.1% of FY26 revenue a year; the stage moves from other to LOI. Minor: the label reads "Complete by 05 years"; "Over 5 years" would read better. |
| Hind Copper ICRA upgrade (rating) | 1a84a2bd-b7a2-440a-90b6-528b621ce310 | **Regression: the card was published and is now held.** The new `scale` block treats the ₹2,100 Cr of rated facilities as a "deal" (224% of Q1 revenue), and the figure check then holds it: "₹2100 Cr appears in the filing only in a clause about instruments, not as the deal's consideration or value". A rating card's rated amount is not a deal size. **And `rating_change.before` is null, so no ladder or notches**, though the filing says "upgraded the Long-term rating to [ICRA]AAA (Stable) ... from [ICRA]AA+ (Stable)". The agency's square brackets around its name probably defeat the match. Two quote-contract holds also appeared ("Short-term rating", "Upgrade to AAA is the highest rating..."). |
| Dabur USFDA warning letter (case) | nse-106729432 | The block shows Form 483 → Warning letter → Import alert → Closed, at "Warning letter". **Wrong for this case**: the import alert came first (June), and the warning letter followed it (July), as the card's own previous headline said. A fixed linear ladder puts the import alert ahead of the company when it has already happened. The steps need to come from what the filing and memory say happened, or the ladder should mark each step separately. |

The "Since the filing" and "Management said" lines appear on CSB and Ceigall (Ceigall: "Revenue growth guidance for
FY27 (minimum 15%) · by FY27", right).
