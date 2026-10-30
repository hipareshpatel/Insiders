/** The Results page as a KPI report: the filters, the sorts and the SQL they make. No React and no Worker types here, so the Worker
 * builds its query from it, the page reads its option lists from it, and `node --test` runs the cases in resultsKpi.test.ts.
 * The rows are `results_kpi` (pipeline results_table.py): one per company and quarter, worked out from the saved statements. */

export const SIZE_CATEGORIES = ["LARGE", "MID", "SMALL", "MICRO"] as const;
export const GROWTH_STEPS = [0, 10, 20, 30, 50, 100] as const;   // "at least this much growth, per cent"
export const MARGIN_STEPS = [0, 100, 200, 300, 500] as const;    // "margin up at least this many basis points"
export const PAGE_SIZE = 50;
const MAX_OFFSET = 10_000;

/** The columns a sort may name; the value is the SQL it orders by (growth sorts on the key that ranks a turn across a loss). */
export const KPI_SORTS = {
  company: "co.company_name COLLATE NOCASE",
  mcap: "co.market_cap_cr",
  revenue: "k.revenue", revenue_yoy: "k.revenue_yoy", revenue_qoq: "k.revenue_qoq",
  ebitda: "k.ebitda", ebitda_yoy: "k.ebitda_key", ebitda_qoq: "k.ebitda_qoq",
  opm: "k.opm", opm_yoy_bps: "k.opm_yoy_bps",
  pat: "k.pat", pat_yoy: "k.pat_key", pat_qoq: "k.pat_qoq",
} as const;
export type KpiSort = keyof typeof KPI_SORTS;

export interface KpiQuery {
  quarter: string | null;
  sizes: string[];
  q: string;
  sort: KpiSort;
  dir: "asc" | "desc";
  revMin: number | null;      // revenue growth at least this per cent (year on year)
  ebitdaMin: number | null;   // EBITDA growth at least this per cent; a loss turned to profit counts
  patMin: number | null;      // PAT growth at least this per cent; a loss turned to profit counts
  opmMin: number | null;      // EBITDA margin up at least this many basis points (year on year)
  turnaround: boolean;        // PAT: loss to profit only
  page: number;
}

/** A quarter as "Q2FY27" gives a number to order by (newest largest), else null. */
export function quarterIndex(period: string | null | undefined): number | null {
  const m = /^Q([1-4])FY(\d{2})$/.exec(period ?? "");
  return m ? Number(m[2]) * 4 + Number(m[1]) : null;
}

const step = (v: string | undefined, allowed: readonly number[]): number | null => {
  if (v == null || v === "") return null;
  const n = Number(v);
  return allowed.includes(n) ? n : null;
};

/** The request's query string as a KpiQuery: anything not on the lists is dropped, so nothing it holds reaches the SQL as written. */
export function parseKpiQuery(raw: Record<string, string | undefined>): KpiQuery {
  const sort = (raw.sort ?? "") in KPI_SORTS ? (raw.sort as KpiSort) : "pat_yoy";
  const page = Math.min(Math.max(Number.parseInt(raw.page ?? "", 10) || 1, 1), Math.floor(MAX_OFFSET / PAGE_SIZE) + 1);
  return {
    quarter: quarterIndex(raw.quarter) != null ? raw.quarter! : null,
    sizes: (raw.size ?? "").split(",").map((s) => s.trim()).filter((s) => (SIZE_CATEGORIES as readonly string[]).includes(s)),
    q: (raw.q ?? "").trim().slice(0, 60),
    sort,
    dir: raw.dir === "asc" ? "asc" : "desc",
    revMin: step(raw.rev_min, GROWTH_STEPS),
    ebitdaMin: step(raw.ebitda_min, GROWTH_STEPS),
    patMin: step(raw.pat_min, GROWTH_STEPS),
    opmMin: step(raw.opm_min, MARGIN_STEPS),
    turnaround: raw.turnaround === "1",
    page,
  };
}

export const KPI_COLUMNS = `k.scrip_code, k.period, k.basis, k.revenue, k.revenue_yoy, k.revenue_qoq,
  k.ebitda, k.ebitda_yoy, k.ebitda_qoq, k.ebitda_turn, k.pat, k.pat_yoy, k.pat_qoq, k.pat_turn,
  k.opm, k.opm_yoy_bps, k.opm_qoq_bps, co.symbol, co.company_name, co.market_cap_cr, co.size_category, co.sector`;

const like = (s: string) => `%${s.replace(/[\\%_]/g, (c) => `\\${c}`)}%`;

/** The filtered rows' FROM and WHERE for a quarter, with their positional parameters. */
export function kpiWhere(query: KpiQuery, quarter: string): { from: string; params: unknown[] } {
  const params: unknown[] = [];
  const p = (v: unknown) => (params.push(v), `?${params.length}`);
  const where = [`k.period = ${p(quarter)}`];
  if (query.sizes.length) where.push(`co.size_category IN (SELECT value FROM json_each(${p(JSON.stringify(query.sizes))}))`);
  if (query.q) { const t = p(like(query.q)); where.push(`(co.symbol LIKE ${t} ESCAPE '\\' OR co.company_name LIKE ${t} ESCAPE '\\')`); }
  if (query.revMin != null) where.push(`k.revenue_yoy >= ${p(query.revMin)}`);
  if (query.ebitdaMin != null) where.push(`(k.ebitda_yoy >= ${p(query.ebitdaMin)} OR k.ebitda_turn = 'LOSS_TO_PROFIT')`);
  if (query.patMin != null) where.push(`(k.pat_yoy >= ${p(query.patMin)} OR k.pat_turn = 'LOSS_TO_PROFIT')`);
  if (query.opmMin != null) where.push(`k.opm_yoy_bps >= ${p(query.opmMin)}`);
  if (query.turnaround) where.push(`k.pat_turn = 'LOSS_TO_PROFIT'`);
  return { from: `FROM results_kpi k LEFT JOIN companies co ON co.scrip_code = k.scrip_code WHERE ${where.join(" AND ")}`, params };
}

/** The page's rows: the chosen sort, a row without the figure last whichever way it runs, the company code to break ties. */
export function kpiRowsSql(query: KpiQuery, from: string): string {
  const col = KPI_SORTS[query.sort];
  return `SELECT ${KPI_COLUMNS} ${from} ORDER BY (${col}) IS NULL, ${col} ${query.dir === "asc" ? "ASC" : "DESC"}, k.scrip_code
     LIMIT ${PAGE_SIZE + 1} OFFSET ${(query.page - 1) * PAGE_SIZE}`;
}

/** How the filtered companies did, for the strip above the table. */
export const kpiSummarySql = (from: string) => `SELECT count(*) AS n,
  coalesce(sum(k.revenue_yoy > 0), 0) AS revenue_up,
  coalesce(sum(k.ebitda_yoy > 0 OR k.ebitda_turn = 'LOSS_TO_PROFIT'), 0) AS ebitda_up,
  coalesce(sum(k.pat_yoy > 0 OR k.pat_turn = 'LOSS_TO_PROFIT'), 0) AS pat_up,
  coalesce(sum(k.pat_turn = 'LOSS_TO_PROFIT'), 0) AS turnarounds ${from}`;

export interface KpiRow {
  scrip_code: string; period: string; basis: string;
  revenue: number | null; revenue_yoy: number | null; revenue_qoq: number | null;
  ebitda: number | null; ebitda_yoy: number | null; ebitda_qoq: number | null; ebitda_turn: string | null;
  pat: number | null; pat_yoy: number | null; pat_qoq: number | null; pat_turn: string | null;
  opm: number | null; opm_yoy_bps: number | null; opm_qoq_bps: number | null;
  symbol: string | null; company_name: string | null; market_cap_cr: number | null; size_category: string | null; sector: string | null;
}

export interface KpiResponse {
  quarter: string | null;
  quarters: { period: string; n: number }[];   // newest first
  rows: KpiRow[];
  summary: { n: number; revenue_up: number; ebitda_up: number; pat_up: number; turnarounds: number };
  page: number;
  pages: number;
}
