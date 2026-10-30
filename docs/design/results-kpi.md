# Results page as a KPI report (Direction C, white theme)

Owner decisions (30 Oct 2026): the Results page shows only figures worked out from the saved statements (the company page's Results tab
source), never a card's; Direction C of the five design explorations, white theme only; consolidated over standalone; one row per
company and quarter; growth filters and sorting; sector and industry from the stored NSE classification; NSE broad indices with history
(weekly Sunday refresh, exact members from the next quarter); the five financials rules below. References: `docs/design/results-kpi/`
(`c-prototype.html` is the designer's hash-state prototype, `c-*-light.png` the white screens, `sample-data.json` the sample data the
designs were drawn from). Contract: `db/migrations/0015_results_kpi.sql`, `0016_index_members.sql`, `web/shared/resultsTypes.ts`.

## Rules (measured 30 Oct 2026 on the live site unless marked)
1. **Financials** are told apart by the layout of their saved statements (`family`: corporate, bank, nbfc, insurer), not by industry text.
   Banks (9 of 9 in the Nifty 100 sample): revenue = the `Revenue` row (interest earned), no EBITDA or margin (no operating-expense row is saved).
   NBFCs: revenue = `Revenue`, the ebitda columns hold `Financing Profit`, margin holds `Financing Margin %`. Insurers: only `Net Profit`
   (no revenue). PAT = `Net Profit (owners)` when present, else `Net Profit`.
2. EBITDA statistics (up counts, medians, totals) include ordinary companies only. Revenue statistics include every company with revenue.
3. **Median** = middle company among those with a per cent change; a change across a loss has no per cent (named turn) and is left out.
   **Total growth** = the group's profit (or revenue, EBITDA) this quarter added up against the same total a year ago, loss-makers included;
   a company counts only when it has both amounts; null when the base total is not positive. Three cuts: all, ex-financials (kind = company), financials.
4. **Spread of profit growth** bands: below 0 (a fall; includes profit to loss and a wider loss), 0-10, 10-20, above 20 (exactly 20 counts above).
   Loss to profit and loss narrowed have no per cent and sit outside the bars.
5. **Momentum** = this quarter's year-on-year growth minus last quarter's, in points: >= +2 speeding up, <= -2 slowing, between steady;
   not comparable when either quarter has no per cent.
6. **Index members** are those on the quarter's last day (`valid_from <= day AND (valid_to IS NULL OR valid_to > day)`); quarter days:
   Q1 = 30 Jun, Q2 = 30 Sep, Q3 = 31 Dec of the calendar year before the FY label's year, Q4 = 31 Mar of the label's year (Q2FY27 = 30 Sep 2026).
   Tracking began on `kv index_members:tracking_since`; before it the list as first read stands in (the page says so). REITs have no results
   in the company layout and are left out of counts (index lists match our companies by ISIN: Nifty 500 497 of 500).
7. "Profit not from operations" (`nfo`): ordinary companies only; profit up (or loss to profit) while EBITDA fell.
8. Classification = `companies.industry`, NSE's path "A > B > C > D" (1-4 steps; 142 of 2,767 have none: "Unclassified"). The line under a name is
   `industryLine()` (shared/industry.ts). Group by Sector = step 1 (20 values), Industry = step 2 (39). The picker filters by path prefix.
9. Reported PAT as filed, not adjusted. Growth is against the same quarter a year ago.

## Who owns which files (no one commits; the lead integrates)
- Pipeline (`pipeline/**`): `results_table.py`, `index_members.py`, their tests, CLI wiring. Database files (`db/**`) and `web/shared/resultsTypes.ts` are fixed by the lead: ask before changing.
- Worker (`web/worker/**`, `web/shared/resultsKpi.ts` and new `web/shared/*` helpers, `web/test/*` for them): `/api/results-kpi`, `/api/results-classification`, `/api/results-groups`, `/api/results-company/:key`, as typed in `resultsTypes.ts`.
- Page (`web/src/**`, `web/test/*` for page helpers, `web/package.json` test list): replaces `ResultsView.tsx`, new components in `web/src/components/results/`, API client functions in `web/src/lib/api.ts`. Keep exporting `Change` and `turnOf` from `ResultsView.tsx` (the company page imports them) or move them and fix the import.

## Acceptance
Pipeline: `cd pipeline && python -m pytest -q` passes. Worker and page: `cd web && npm run typecheck && npm test && npx vite build` pass; every
rule above has a unit test; SQL is checked against a real SQLite with sample rows; every filter value is a bound parameter. Page: screenshots at 1440 and 390 wide
against mocked API data match the references' structure (same blocks, same states), white theme only, text contrast >= 4.5:1, touch targets >= 44px on the phone.
