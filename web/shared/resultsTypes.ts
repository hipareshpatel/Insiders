/** The Results KPI report's API shapes: the contract between the Worker (web/worker/results.ts) and the page (web/src/views/ResultsView.tsx).
 *  Types only: no code, so both sides can import it. The design is docs/design/results-kpi.md (Direction C, white theme).
 *  Growth is always against the same quarter a year ago unless the name says otherwise. A growth figure is null when it does not exist
 *  (no such line saved, or a change across a loss, which has a named *_turn instead of a per cent). */

export type Kind = "company" | "bank" | "nbfc" | "insurer";
export type Turn = "LOSS_TO_PROFIT" | "PROFIT_TO_LOSS" | "LOSS_NARROWED" | "LOSS_WIDENED";
export type View = "yoy" | "momentum" | "qoq";
/** this quarter's growth against last quarter's, in points: >= +2 speeding up, <= -2 slowing, between steady; not comparable when either
 *  quarter has no per cent (a loss, or a missing quarter) */
export type Momentum = "speeding_up" | "slowing" | "steady" | "not_comparable";
export const MOMENTUM_POINTS = 2;

/** The indices the page offers, in the order it lists them (ids as stored in index_members.index_id). */
export const INDICES: { id: string; label: string }[] = [
  { id: "NIFTY50", label: "Nifty 50" }, { id: "NIFTYNEXT50", label: "Nifty Next 50" }, { id: "NIFTY100", label: "Nifty 100" },
  { id: "NIFTY200", label: "Nifty 200" }, { id: "NIFTY500", label: "Nifty 500" }, { id: "LARGEMIDCAP250", label: "Nifty LargeMidcap 250" },
  { id: "MIDCAP150", label: "Nifty Midcap 150" }, { id: "MIDSMALLCAP400", label: "Nifty MidSmallcap 400" },
  { id: "SMALLCAP250", label: "Nifty Smallcap 250" }, { id: "MICROCAP250", label: "Nifty Microcap 250" }, { id: "TOTALMARKET", label: "Nifty Total Market" },
];
/** "Market cap at least" steps, in rupees crore. */
export const MARKET_CAP_STEPS = [500, 1000, 5000, 10000, 50000, 100000] as const;

export interface KpiRow {
  scrip_code: string;
  symbol: string | null;
  company_name: string | null;
  /** NSE's stored classification, broad to narrow: "Healthcare > Pharmaceuticals & Biotechnology > Pharmaceuticals" (shared/industry.ts) */
  industry: string | null;
  market_cap_cr: number | null;
  size_category: string | null;
  period: string;
  basis: "CONSOLIDATED" | "STANDALONE";
  kind: Kind;
  /** a bank's is interest income; an NBFC's its income; an insurer has none (null) */
  revenue: number | null;
  revenue_yoy: number | null;
  revenue_qoq: number | null;
  revenue_prev_yoy: number | null;       // last quarter's growth against its own year-ago quarter
  revenue_momentum_pts: number | null;
  /** an NBFC's holds its financing profit; a bank or an insurer has none (null) */
  ebitda: number | null;
  ebitda_yoy: number | null;
  ebitda_qoq: number | null;
  ebitda_turn: Turn | null;
  ebitda_prev_yoy: number | null;
  ebitda_momentum_pts: number | null;
  /** EBITDA margin (an NBFC's financing margin) in per cent, and its change in basis points */
  opm: number | null;
  opm_yoy_bps: number | null;
  opm_qoq_bps: number | null;
  pat: number | null;
  pat_yoy: number | null;
  pat_qoq: number | null;
  pat_turn: Turn | null;
  pat_qoq_turn: Turn | null;
  pat_prev_yoy: number | null;
  pat_prev_turn: Turn | null;
  pat_momentum_pts: number | null;
  momentum: Momentum;                    // of profit growth
  /** profit up (or a loss turned to profit) while EBITDA fell; never for banks, NBFCs or insurers */
  nfo: boolean;
  filed_at: string | null;               // the filing's own timestamp, ISO with +05:30
  filing_url: string | null;             // the NSE filing (PDF), when the filing is known
  /** profit and revenue growth against a year ago for the latest 8 quarters, oldest first, ending with this one; null where no per cent */
  series_pat: (number | null)[];
  series_revenue: (number | null)[];
}

/** The numbers above the table, for the filtered set (all companies of the quarter when nothing is filtered). */
export interface KpiSummary {
  n: number;
  revenue_up: number; revenue_of: number;      // a company with revenue saved
  ebitda_up: number; ebitda_of: number;        // ordinary companies only: banks, NBFCs and insurers are not in EBITDA statistics
  pat_up: number; pat_of: number;              // pat_up counts a loss turned to profit; pat_of is every company
  loss_to_profit: number;
  median_revenue_yoy: number | null;           // medians use companies with a per cent change
  median_ebitda_yoy: number | null;
  median_pat_yoy: number | null;
  /** companies by profit growth: below 0 (a fall, including profit to loss and a wider loss), 0-10, 10-20, above 20 (>= 20 counts above);
   *  loss_to_profit and loss_narrowed have no per cent and sit outside the bars */
  spread: { below_0: number; from_0_to_10: number; from_10_to_20: number; above_20: number; loss_to_profit: number; loss_narrowed: number; with_pct: number };
  momentum: { speeding_up: number; slowing: number; steady: number; not_comparable: number };
  nfo: number;                                  // companies flagged "profit not from operations"
}

export interface KpiProgress {
  index_id: string;                             // NIFTY500
  reported: number;
  of: number;                                   // members matched to a company with a results row possible (REITs left out)
  quarter_reported: number;                     // every company with a row this quarter
  /** the next board meeting date of a company in that index that has not reported, and how many meet on it; null when not known */
  still_to_come: { date: string; companies: number } | null;
}

export interface KpiResponse {
  quarter: string | null;
  quarters: { period: string; n: number }[];    // newest first
  indices: { id: string; label: string; n: number }[];   // the indices with members, n = companies of the quarter in each (as of the quarter's last day)
  index_tracking_since: string | null;          // YYYY-MM-DD: before it, an index's members are the list as first read
  rows: KpiRow[];
  summary: KpiSummary;
  progress: KpiProgress | null;
  page: number;
  pages: number;
}

/** GET /api/results-kpi?quarter=Q2FY27&index=NIFTY500&mcap_min=5000&class=Healthcare > Pharmaceuticals & Biotechnology&q=cip
 *      &rev_min=10&ebitda_min=10&pat_min=20&opm_min=100&momentum=speeding_up&turnaround=1&nfo=1&spread=above_20
 *      &sort=pat_yoy&dir=desc&page=1   (all optional)
 *  `class` is a prefix of the stored classification path, any depth. `spread` keeps the companies of one bar of the spread chart. */
export interface KpiQuery {
  quarter: string | null;
  index: string | null;
  mcap_min: number | null;
  class: string | null;
  q: string;
  rev_min: number | null;
  ebitda_min: number | null;
  pat_min: number | null;
  opm_min: number | null;
  momentum: "speeding_up" | "slowing" | null;
  turnaround: boolean;
  nfo: boolean;
  spread: "below_0" | "from_0_to_10" | "from_10_to_20" | "above_20" | null;
  sort: string;
  dir: "asc" | "desc";
  page: number;
}

/** GET /api/results-classification?quarter=Q2FY27 : the stored classification as a tree with the number of companies of the quarter under
 *  each step, for the sector picker. Companies with no stored path are counted in `unclassified`. */
export interface ClassNode { name: string; path: string; n: number; children: ClassNode[] }
export interface ClassificationResponse { quarter: string | null; tree: ClassNode[]; unclassified: number }

export type GroupBy = "index" | "sector" | "industry";
export type Cut = "all" | "ex_financials" | "financials";

export interface GroupRow {
  id: string;                                   // index id, or the classification path of the group
  label: string;
  reported: number;                             // companies of the group with a row this quarter (in the cut)
  of: number | null;                            // the group's size (an index's members matched to companies; null for a sector or industry)
  pat_median: number | null;                    // in the chosen cut
  /** total profit growth: every company's profit this quarter added up against the same total a year ago, losses included */
  pat_total_all: number | null;
  pat_total_ex_financials: number | null;
  pat_total_financials: number | null;
  financials_share_pct: number | null;          // of the group's profit this quarter
  revenue_total_all: number | null;
  revenue_total_ex_financials: number | null;
  revenue_total_financials: number | null;
  ebitda_total_ex_financials: number | null;
  /** share of companies with a per cent change in each band, in the chosen cut; loss-to-profit companies are outside */
  spread_pct: [number, number, number, number];
  speeding_up_pct: number | null;
  /** the median profit growth for the latest 8 quarters, oldest first, ending with this one; members as of each quarter's last day */
  trend_pat_median: (number | null)[];
}

export interface GroupsResponse {
  quarter: string | null;
  quarters: { period: string; n: number }[];
  by: GroupBy;
  cut: Cut;
  index_tracking_since: string | null;
  rows: GroupRow[];                             // sorted by pat_median, highest first
}

/** GET /api/results-groups?quarter=Q2FY27&by=index&cut=all&within_index=NIFTY500&within_mcap=5000 */

/** GET /api/results-company/:symbolOrScrip : the company's last 8 quarters of rows, oldest first (the side panel's chart). */
export interface CompanyKpiResponse { company: { scrip_code: string; symbol: string | null; company_name: string | null; industry: string | null } | null; rows: KpiRow[] }
