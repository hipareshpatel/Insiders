// Mock API answers for the Results page (screenshots and tests only; never imported by src/, so never in the production bundle).
// Built from docs/design/results-kpi/sample-data.json (the designer's sample: made-up numbers apart from four companies' growth), plus rows
// that exercise every state: profit to loss, a wider loss, an unclassified standalone company with no market cap or filing link, a
// steady pace, and an EBITDA turn.
import { INDICES } from "../../shared/resultsTypes.ts";
import type { ClassificationResponse, ClassNode, GroupBy, GroupRow, GroupsResponse, KpiRow, KpiResponse, KpiSummary } from "../../shared/resultsTypes.ts";

const PERIOD = "Q2FY27";

function row(r: Partial<KpiRow> & Pick<KpiRow, "symbol" | "company_name">): KpiRow {
  const base: KpiRow = {
    scrip_code: r.symbol!, symbol: r.symbol, company_name: r.company_name, industry: null, market_cap_cr: null, size_category: null,
    period: PERIOD, basis: "CONSOLIDATED", kind: "company",
    revenue: null, revenue_yoy: null, revenue_qoq: null, revenue_prev_yoy: null, revenue_momentum_pts: null,
    ebitda: null, ebitda_yoy: null, ebitda_qoq: null, ebitda_turn: null, ebitda_prev_yoy: null, ebitda_momentum_pts: null,
    opm: null, opm_yoy_bps: null, opm_qoq_bps: null,
    pat: null, pat_yoy: null, pat_qoq: null, pat_turn: null, pat_qoq_turn: null, pat_prev_yoy: null, pat_prev_turn: null, pat_momentum_pts: null,
    momentum: "not_comparable", nfo: false, filed_at: "2026-10-30T15:35:00+05:30", filing_url: `https://nsearchives.nseindia.com/corporate/${r.symbol}_Q2FY27.pdf`,
    series_pat: [null, null, null, null, null, null, null, null], series_revenue: [null, null, null, null, null, null, null, null],
  };
  const out = { ...base, ...r };
  const pts = (now: number | null, was: number | null) => (now == null || was == null ? null : Number((now - was).toFixed(1)));
  out.revenue_momentum_pts ??= pts(out.revenue_yoy, out.revenue_prev_yoy);
  out.ebitda_momentum_pts ??= pts(out.ebitda_yoy, out.ebitda_prev_yoy);
  out.pat_momentum_pts ??= pts(out.pat_yoy, out.pat_prev_yoy);
  const m = out.pat_momentum_pts;
  out.momentum = m == null ? "not_comparable" : m >= 2 ? "speeding_up" : m <= -2 ? "slowing" : "steady";
  return out;
}

export const ROWS: KpiRow[] = [
  row({ symbol: "DELHIVERY", company_name: "Delhivery Limited", industry: "Services > Logistics Solution Provider", market_cap_cr: 28857,
    revenue: 2900, revenue_yoy: 19.8, revenue_prev_yoy: 17.1, revenue_qoq: 6.2, ebitda: 193, ebitda_yoy: 199.1, ebitda_prev_yoy: 120.0, ebitda_qoq: 14.0,
    opm: 6.7, opm_yoy_bps: 399, opm_qoq_bps: 45, pat: 95, pat_turn: "LOSS_TO_PROFIT", pat_prev_turn: "LOSS_NARROWED", pat_qoq: 58.3,
    series_pat: [null, null, null, null, null, null, null, null], series_revenue: [12.0, 13.5, 14.8, 15.9, 16.2, 17.0, 17.1, 19.8] }),
  row({ symbol: "IOC", company_name: "Indian Oil Corporation", industry: "Energy > Refineries & Marketing", market_cap_cr: 184000,
    revenue: 241300, revenue_yoy: 42.2, revenue_prev_yoy: 31.0, revenue_qoq: 8.1, ebitda: 32100, ebitda_yoy: 108.0, ebitda_prev_yoy: 64.0, ebitda_qoq: 12.5,
    opm: 13.3, opm_yoy_bps: 421, opm_qoq_bps: 52, pat: 9100, pat_yoy: 173.8, pat_prev_yoy: 92.0, pat_qoq: 21.3,
    series_pat: [-60, -35, -10, 12, 30, 55, 92, 173.8], series_revenue: [-4, 2, 8, 14, 20, 26, 31, 42.2] }),
  row({ symbol: "GAIL", company_name: "GAIL (India) Limited", industry: "Energy > Gas Transmission/Marketing", market_cap_cr: 108000,
    revenue: 35400, revenue_yoy: 32.6, revenue_prev_yoy: 35.0, revenue_qoq: 3.4, ebitda: 5240, ebitda_yoy: 102.0, ebitda_prev_yoy: 88.0, ebitda_qoq: 7.7,
    opm: 14.8, opm_yoy_bps: 509, opm_qoq_bps: 60, pat: 3300, pat_yoy: 139.3, pat_prev_yoy: 120.0, pat_qoq: 9.9,
    series_pat: [20, 28, 44, 62, 80, 101, 120, 139.3], series_revenue: [10, 14, 19, 24, 28, 31, 35, 32.6] }),
  row({ symbol: "NORTHGATE", company_name: "Northgate Bank", industry: "Financial Services > Banks > Private Sector Bank", market_cap_cr: 62400, kind: "bank",
    filed_at: "2026-10-29T17:10:00+05:30", revenue: 11800, revenue_yoy: 16.4, revenue_prev_yoy: 18.2, revenue_qoq: 2.9, pat: 2150, pat_yoy: 61.0, pat_prev_yoy: 72.0, pat_qoq: -4.4,
    series_pat: [24, 30, 38, 45, 55, 64, 72, 61], series_revenue: [15, 16, 17.5, 18, 18.4, 18, 18.2, 16.4] }),
  row({ symbol: "NTPCGREEN", company_name: "NTPC Green Energy", industry: "Utilities > Power Generation", market_cap_cr: 70124,
    revenue: 1150, revenue_yoy: 53.2, revenue_prev_yoy: 48.0, revenue_qoq: 4.1, ebitda: 998, ebitda_yoy: 56.7, ebitda_prev_yoy: 52.0, ebitda_qoq: 5.0,
    opm: 86.8, opm_yoy_bps: 194, opm_qoq_bps: 30, pat: 310, pat_yoy: 57.0, pat_prev_yoy: 60.0, pat_qoq: 3.3,
    series_pat: [30, 36, 41, 47, 52, 56, 60, 57], series_revenue: [38, 40, 43, 45, 46, 47, 48, 53.2] }),
  row({ symbol: "KESTREL", company_name: "Kestrel Industries", industry: "Industrials > Industrial Machinery", market_cap_cr: 6310,
    revenue: 980, revenue_yoy: 6.1, revenue_prev_yoy: 7.0, revenue_qoq: 1.0, ebitda: 120, ebitda_yoy: -5.2, ebitda_prev_yoy: 4.0, ebitda_qoq: -3.2,
    opm: 12.2, opm_yoy_bps: -145, opm_qoq_bps: -55, pat: 96, pat_yoy: 48.0, pat_prev_yoy: 9.0, pat_qoq: 31.5, nfo: true,
    series_pat: [6, 4, 2, -3, 1, 5, 9, 48], series_revenue: [9, 8, 8.5, 7.5, 7, 7.2, 7, 6.1] }),
  row({ symbol: "SUNRISE", company_name: "Sunrise Finance", industry: "Financial Services > NBFC", market_cap_cr: 21900, kind: "nbfc",
    filed_at: "2026-10-28T19:02:00+05:30", revenue: 3200, revenue_yoy: 22.8, revenue_prev_yoy: 20.1, revenue_qoq: 5.2, ebitda: 2050, ebitda_yoy: 30.4, ebitda_prev_yoy: 33.0,
    ebitda_qoq: 6.0, opm: 64.1, opm_yoy_bps: 370, opm_qoq_bps: 50, pat: 880, pat_yoy: 41.5, pat_prev_yoy: 36.0, pat_qoq: 7.3,
    series_pat: [28, 30, 31, 33, 34, 35, 36, 41.5], series_revenue: [17, 18, 19, 19.5, 20, 20, 20.1, 22.8] }),
  row({ symbol: "EVERGREEN", company_name: "Evergreen Life", industry: "Financial Services > Insurance > Life Insurance", market_cap_cr: 48200, kind: "insurer",
    filed_at: "2026-10-29T16:40:00+05:30", pat: 740, pat_yoy: 36.8, pat_prev_yoy: 30.2, pat_qoq: 4.0,
    series_pat: [18, 20, 22, 24, 26, 27, 30.2, 36.8] }),
  row({ symbol: "MERIDIAN", company_name: "Meridian Pharma", industry: "Healthcare > Pharmaceuticals & Biotechnology > Pharmaceuticals > Pharmaceuticals",
    market_cap_cr: 15400, revenue: 1420, revenue_yoy: 11.2, revenue_prev_yoy: 10.4, revenue_qoq: 2.1, ebitda: 210, ebitda_turn: "LOSS_TO_PROFIT", ebitda_qoq: 40.0,
    opm: 14.8, opm_yoy_bps: 1650, pat: 120, pat_yoy: 14.0, pat_prev_yoy: 13.1, pat_qoq: 3.0,
    series_pat: [4, 6, 8, 10, 11, 12, 13.1, 14.0], series_revenue: [6, 7, 8, 9, 9.5, 10, 10.4, 11.2] }),
  row({ symbol: "AURUM", company_name: "Aurum Textiles", industry: "Consumer Discretionary > Textiles & Apparels > Other Textile Products",
    market_cap_cr: 1850, basis: "STANDALONE", filed_at: "2026-10-27T13:05:00+05:30", filing_url: null,
    revenue: 410, revenue_yoy: -8.4, revenue_prev_yoy: -2.0, revenue_qoq: -5.1, ebitda: 12, ebitda_yoy: -71.5, ebitda_prev_yoy: -20.0, ebitda_qoq: -40.0,
    opm: 2.9, opm_yoy_bps: -610, opm_qoq_bps: -180, pat: -18, pat_turn: "PROFIT_TO_LOSS", pat_qoq_turn: "PROFIT_TO_LOSS", pat_prev_yoy: -35.0,
    series_pat: [12, 8, 5, -4, -12, -20, -35, null], series_revenue: [6, 4, 2, 0, -1, -1.5, -2, -8.4] }),
  row({ symbol: "BLUEFIN", company_name: "Bluefin Marine Services", industry: null, market_cap_cr: null, filed_at: "2026-10-26T10:15:00+05:30",
    revenue: 95, revenue_yoy: 2.0, revenue_prev_yoy: 1.5, ebitda: -6, ebitda_turn: "LOSS_WIDENED", opm: -6.3, opm_yoy_bps: -240, pat: -14, pat_turn: "LOSS_WIDENED", pat_prev_turn: "LOSS_WIDENED" }),
  row({ symbol: "CEDAR", company_name: "Cedar Home Finance", industry: "Financial Services > Finance > Housing Finance Company", market_cap_cr: 4120, kind: "nbfc",
    revenue: 640, revenue_yoy: 9.0, revenue_prev_yoy: 9.4, revenue_qoq: 2.0, ebitda: 300, ebitda_yoy: 8.1, ebitda_prev_yoy: 8.0, opm: 46.9, opm_yoy_bps: -40,
    pat: 150, pat_yoy: 9.6, pat_prev_yoy: 8.7, pat_qoq: 1.5, series_pat: [7, 8, 9, 8.5, 9, 8.8, 8.7, 9.6], series_revenue: [8, 8.5, 9, 9.2, 9.1, 9.3, 9.4, 9.0] }),
];

/** Page 2: three more rows, so "Show more" has something to load. */
export const ROWS_PAGE_2: KpiRow[] = [
  row({ symbol: "HARBOUR", company_name: "Harbour Ports", industry: "Services > Port & Port services", market_cap_cr: 32100,
    revenue: 1800, revenue_yoy: 7.5, revenue_prev_yoy: 9.0, ebitda: 1100, ebitda_yoy: 6.0, ebitda_prev_yoy: 8.0, opm: 61.1, opm_yoy_bps: -85,
    pat: 640, pat_yoy: 5.1, pat_prev_yoy: 11.0, series_pat: [12, 13, 11, 12, 10, 11, 11, 5.1], series_revenue: [9, 9, 10, 9, 9.5, 9, 9, 7.5] }),
  row({ symbol: "ORBIT", company_name: "Orbit Chemicals", industry: "Commodities > Chemicals > Specialty Chemicals", market_cap_cr: 7600,
    revenue: 520, revenue_yoy: -3.0, revenue_prev_yoy: 1.0, ebitda: 70, ebitda_yoy: -12.0, ebitda_prev_yoy: -4.0, opm: 13.5, opm_yoy_bps: -140,
    pat: 40, pat_yoy: -18.4, pat_prev_yoy: -6.0, series_pat: [10, 6, 2, -1, -3, -5, -6, -18.4], series_revenue: [5, 4, 3, 2, 1.5, 1, 1, -3] }),
  row({ symbol: "VERTEX", company_name: "Vertex Software", industry: "Information Technology > IT - Software > Computers - Software & Consulting", market_cap_cr: 54000,
    revenue: 6200, revenue_yoy: 10.1, revenue_prev_yoy: 9.8, ebitda: 1500, ebitda_yoy: 11.0, ebitda_prev_yoy: 10.5, opm: 24.2, opm_yoy_bps: 20,
    pat: 1040, pat_yoy: 12.3, pat_prev_yoy: 12.9, series_pat: [14, 13, 12, 12.5, 13, 12, 12.9, 12.3], series_revenue: [11, 10.5, 10, 10, 9.9, 9.7, 9.8, 10.1] }),
];

export const SUMMARY: KpiSummary = {
  n: 236, revenue_up: 196, revenue_of: 230, ebitda_up: 182, ebitda_of: 205, pat_up: 175, pat_of: 236, loss_to_profit: 11,
  median_revenue_yoy: 11.8, median_ebitda_yoy: 14.6, median_pat_yoy: 13.9,
  spread: { below_0: 61, from_0_to_10: 38, from_10_to_20: 41, above_20: 85, loss_to_profit: 11, loss_narrowed: 4, with_pct: 225 },
  momentum: { speeding_up: 118, slowing: 98, steady: 12, not_comparable: 8 },
  nfo: 9,
};

const QUARTERS = [
  { period: "Q2FY27", n: 236 }, { period: "Q1FY27", n: 1890 }, { period: "Q4FY26", n: 2410 }, { period: "Q3FY26", n: 2380 },
  { period: "Q2FY26", n: 2350 }, { period: "Q1FY26", n: 2300 },
];
const INDEX_N: Record<string, number> = { NIFTY50: 31, NIFTYNEXT50: 22, NIFTY100: 53, NIFTY200: 91, NIFTY500: 185, LARGEMIDCAP250: 120, MIDCAP150: 62,
  MIDSMALLCAP400: 132, SMALLCAP250: 70, MICROCAP250: 51, TOTALMARKET: 236 };

export function kpiResponse(page = 1, over: Partial<KpiResponse> = {}): KpiResponse {
  return {
    quarter: PERIOD, quarters: QUARTERS, indices: INDICES.map((x) => ({ ...x, n: INDEX_N[x.id] ?? 0 })), index_tracking_since: "2026-10-30",
    rows: page === 1 ? ROWS : ROWS_PAGE_2, summary: SUMMARY,
    progress: { index_id: "NIFTY500", reported: 185, of: 497, members: 500, quarter_reported: 236, still_to_come: { date: "2026-11-03", companies: 14 } },
    page, pages: 2, ...over,
  };
}

/** A filtered answer that keeps nothing (the empty state). */
export const EMPTY_SUMMARY: KpiSummary = {
  n: 0, revenue_up: 0, revenue_of: 0, ebitda_up: 0, ebitda_of: 0, pat_up: 0, pat_of: 0, loss_to_profit: 0,
  median_revenue_yoy: null, median_ebitda_yoy: null, median_pat_yoy: null,
  spread: { below_0: 0, from_0_to_10: 0, from_10_to_20: 0, above_20: 0, loss_to_profit: 0, loss_narrowed: 0, with_pct: 0 },
  momentum: { speeding_up: 0, slowing: 0, steady: 0, not_comparable: 0 }, nfo: 0,
};

// the sample's index table: [label, id, reported, of, median, total all, ex-fin, fin, fin share, rev all, rev ex, rev fin, ebitda ex, spread, speeding, trend]
const IDX: [string, number, number, number, number, number, number, number, number, number, number, number, [number, number, number, number], number, number[]][] = [
  ["NIFTY50", 31, 50, 12.1, 9.3, 9.9, 8.4, 38, 8.7, 8.5, 9.4, 12.4, [14, 28, 38, 20], 52, [8.4, 9.8, 7.1, 10.9, 9.2, 11.0, 10.4, 12.1]],
  ["NIFTYNEXT50", 22, 50, 11.0, 11.6, 12.5, 9.1, 27, 9.9, 9.6, 10.4, 14.1, [16, 30, 40, 14], 49, [12.0, 11.2, 9.8, 10.4, 11.4, 10.6, 9.6, 11.0]],
  ["NIFTY100", 53, 100, 11.8, 10.0, 10.7, 8.6, 34, 9.1, 8.9, 9.8, 12.9, [15, 29, 33, 23], 51, [9.6, 10.4, 8.4, 10.6, 10.0, 10.5, 10.1, 11.8]],
  ["NIFTY200", 91, 200, 13.6, 11.6, 12.4, 9.8, 31, 10.5, 10.2, 11.1, 15.0, [13, 24, 36, 27], 53, [9.0, 9.4, 8.6, 10.8, 11.2, 11.0, 12.0, 13.6]],
  ["NIFTY500", 185, 497, 14.6, 12.4, 12.9, 11.2, 28, 10.5, 10.4, 10.9, 14.5, [14, 20, 35, 31], 54, [9.5, 10.0, 9.6, 11.8, 12.4, 12.6, 13.0, 14.6]],
  ["MIDCAP150", 62, 149, 19.4, 17.4, 18.2, 14.9, 24, 14.0, 13.6, 15.2, 20.1, [9, 13, 30, 48], 58, [10.2, 12.4, 11.0, 14.6, 15.0, 13.8, 16.2, 19.4]],
  ["SMALLCAP250", 70, 248, 16.8, 18.0, 17.5, 21.0, 14, 13.0, 12.8, 14.0, 15.3, [14, 17, 28, 41], 55, [7.2, 9.0, 10.4, 11.2, 12.6, 13.4, 14.8, 16.8]],
  ["MICROCAP250", 51, 250, 10.5, 9.5, 9.2, 12.4, 9, 8.2, 8.0, 9.0, 9.8, [22, 26, 40, 12], 47, [8.0, 9.2, 9.8, 9.4, 10.0, 9.6, 10.2, 10.5]],
];

const indexRows = (): GroupRow[] => IDX.map(([id, reported, of, med, ta, te, tf, share, ra, re, rf, ee, sp, su, tr]) => ({
  id, label: INDICES.find((x) => x.id === id)!.label, reported, of, pat_median: med, pat_total_all: ta, pat_total_ex_financials: te,
  pat_total_financials: tf, financials_share_pct: share, revenue_total_all: ra, revenue_total_ex_financials: re, revenue_total_financials: rf,
  ebitda_total_ex_financials: ee, spread_pct: sp, speeding_up_pct: su, trend_pat_median: tr,
})).sort((a, b) => b.pat_median! - a.pat_median!);

const SECTORS: [string, number, number | null, number | null][] = [
  ["Energy", 18, 24.0, 21.0], ["Healthcare", 21, 17.2, 15.0], ["Industrials", 34, 15.1, 13.2], ["Utilities", 9, 14.0, 16.0],
  ["Information Technology", 19, 9.8, 8.6], ["Consumer Discretionary", 31, 8.2, 6.1], ["Commodities", 27, 4.0, 2.2], ["Financial Services", 42, 11.4, 9.1],
];
const sectorRows = (by: GroupBy): GroupRow[] => SECTORS.map(([label, reported, med, tot], i) => ({
  id: by === "sector" ? label : `${label} > Group ${i + 1}`, label: by === "sector" ? label : `${label.split(" ")[0]} industry ${i + 1}`,
  reported, of: null, pat_median: med, pat_total_all: tot, pat_total_ex_financials: tot == null ? null : tot + 0.6, pat_total_financials: label === "Financial Services" ? 9.1 : null,
  financials_share_pct: label === "Financial Services" ? 100 : 0, revenue_total_all: tot == null ? null : tot - 3, revenue_total_ex_financials: tot == null ? null : tot - 2.4,
  revenue_total_financials: null, ebitda_total_ex_financials: tot == null ? null : tot + 2, spread_pct: [18, 22, 30, 30], speeding_up_pct: 40 + i * 2,
  trend_pat_median: [med! - 6, med! - 4, med! - 5, med! - 2, med! - 3, med! - 1, med! - 2, med!],
})).sort((a, b) => b.pat_median! - a.pat_median!);

export function groupsResponse(by: GroupBy = "index", cut: GroupsResponse["cut"] = "all"): GroupsResponse {
  return { quarter: PERIOD, quarters: QUARTERS, by, cut, index_tracking_since: "2026-10-30", rows: by === "index" ? indexRows() : sectorRows(by) };
}

const node = (path: string[], n: number, children: ClassNode[] = []): ClassNode => ({ name: path[path.length - 1], path: path.join(" > "), n, children });
export const CLASSIFICATION: ClassificationResponse = {
  quarter: PERIOD, unclassified: 142,
  tree: [
    node(["Energy"], 18, [node(["Energy", "Oil, Gas & Consumable Fuels"], 14, [node(["Energy", "Oil, Gas & Consumable Fuels", "Petroleum Products"], 6)])]),
    node(["Financial Services"], 42, [node(["Financial Services", "Banks"], 12), node(["Financial Services", "Finance"], 20), node(["Financial Services", "Insurance"], 10)]),
    node(["Healthcare"], 21, [node(["Healthcare", "Pharmaceuticals & Biotechnology"], 16, [
      node(["Healthcare", "Pharmaceuticals & Biotechnology", "Pharmaceuticals"], 14, [node(["Healthcare", "Pharmaceuticals & Biotechnology", "Pharmaceuticals", "Pharmaceuticals"], 14)]),
    ])]),
    node(["Industrials"], 34), node(["Services"], 15), node(["Utilities"], 9), node(["Information Technology"], 19),
    ...["Automobile and Auto Components", "Capital Goods", "Chemicals", "Construction", "Construction Materials", "Consumer Durables", "Consumer Services",
      "Diversified", "Fast Moving Consumer Goods", "Forest Materials", "Media, Entertainment & Publication", "Metals & Mining", "Realty", "Telecommunication"]
      .map((s, i) => node([s], 3 + i)),
  ],
};
