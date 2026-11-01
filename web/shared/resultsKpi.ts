/** The Results KPI report: the filters, the sorts, the period rules and the SQL they make (docs/design/results-kpi.md). No React and no
 * Worker types here, so the Worker builds its queries from it and `node --test` runs the cases in resultsKpi.test.ts. The rows are
 * `results_kpi` (pipeline results_table.py): one per company and quarter, worked out from the saved statements. Every filter value is a
 * bound parameter; sort and direction come from whitelists; LIKE patterns are escaped. */
import { INDICES, MOMENTUM_POINTS, NM_PCT } from "./resultsTypes.ts";
import type { KpiQuery, KpiRow, Kind, Momentum, ResultsSort, Turn } from "./resultsTypes.ts";

export type { KpiQuery, KpiResponse, KpiRow } from "./resultsTypes.ts";

export const PAGE_SIZE = 50;
export const SERIES_QUARTERS = 8;
const MAX_OFFSET = 10_000;
/** The most filtered rows the summary reads (a quarter holds about 2,800 companies, so this is never reached in practice). */
export const SUMMARY_CAP = 5000;

/** The columns a sort may name; the value is the SQL it orders by. A growth sort is built by `sortExpr` from its per cent and named turn
 *  (highest first: the meaningful per cents, then the "NM" ones above +999%, then rows with no figure, a turn across a loss among them;
 *  lowest first: the falls across a loss, then the per cents, then no figure; measured 31 Oct 2026: the profit-growth list opened with
 *  8 NM rows and the lowest-first list held the 61 profit-to-loss rows after row 500). Momentum is this quarter's growth minus
 *  last quarter's, null when either is missing or "NM". */
/** The points between this quarter's growth and last quarter's, as SQL; null when either is missing or above +999% ("NM": a base effect,
 *  not a pace; measured 31 Oct 2026: CGPOWER 13% to 2,159% showed "+2,146 pts", EMKAY "+6,553 pts"). */
export const momentumSql = (col: string) =>
  `(CASE WHEN k.${col} > ${NM_PCT} OR pk.${col} > ${NM_PCT} THEN NULL ELSE k.${col} - pk.${col} END)`;

/** The growth sorts: per cent column and the column of its named turn (null: the line has none). */
const GROWTH: Record<string, { pct: string; turn: string | null }> = {
  revenue_yoy: { pct: "k.revenue_yoy", turn: null }, ebitda_yoy: { pct: "k.ebitda_yoy", turn: "k.ebitda_turn" },
  pat_yoy: { pct: "k.pat_yoy", turn: "k.pat_turn" }, revenue_qoq: { pct: "k.revenue_qoq", turn: null },
  ebitda_qoq: { pct: "k.ebitda_qoq", turn: null }, pat_qoq: { pct: "k.pat_qoq", turn: "k.pat_qoq_turn" },
};

/** What a sort orders by (a NULL goes last, either way). Highest first: NM per cents sit below every meaningful one, in their own order.
 *  Lowest first: a profit that turned to a loss, then a loss that widened, then the per cents; a loss turned to profit or narrowed has no
 *  place on a lowest-first list, so it has none. */
export function sortExpr(sort: KpiSort, dir: "asc" | "desc"): string {
  const g = GROWTH[sort];
  if (!g) return KPI_SORTS[sort];
  if (dir === "desc") return `(CASE WHEN ${g.pct} IS NULL THEN NULL WHEN ${g.pct} > ${NM_PCT} THEN ${g.pct} - 1e12 ELSE ${g.pct} END)`;
  const falls = g.turn ? `WHEN ${g.turn} = 'PROFIT_TO_LOSS' THEN -2e12 WHEN ${g.turn} = 'LOSS_WIDENED' THEN -1e12 ` : "";
  return `(CASE ${falls}WHEN ${g.pct} IS NOT NULL THEN ${g.pct} END)`;
}

export const KPI_SORTS = {
  company: "co.company_name COLLATE NOCASE",
  mcap: "co.market_cap_cr",
  revenue_yoy: "k.revenue_yoy",
  ebitda_yoy: "k.ebitda_yoy",
  pat_yoy: "k.pat_yoy",
  opm_yoy_bps: "k.opm_yoy_bps",
  revenue_qoq: "k.revenue_qoq",
  ebitda_qoq: "k.ebitda_qoq",
  pat_qoq: "k.pat_qoq",
  opm_qoq_bps: "k.opm_qoq_bps",
  pat_momentum: momentumSql("pat_yoy"),
  revenue_momentum: momentumSql("revenue_yoy"),
  ebitda_momentum: momentumSql("ebitda_yoy"),
  filed: "f.filed_at",
} as const satisfies Record<ResultsSort, string>;
export type KpiSort = keyof typeof KPI_SORTS;

const INDEX_IDS: readonly string[] = INDICES.map((i) => i.id);
const SPREADS = ["below_0", "from_0_to_10", "from_10_to_20", "above_20"] as const;

/** A quarter as "Q2FY27" gives a number to order by (newest largest), else null. */
export function quarterIndex(period: string | null | undefined): number | null {
  const m = /^Q([1-4])FY(\d{2})$/.exec(period ?? "");
  return m ? Number(m[2]) * 4 + Number(m[1]) : null;
}

/** The quarter with that order number: 27 * 4 + 2 is "Q2FY27". */
const periodOf = (index: number): string => `Q${((index - 1) % 4) + 1}FY${String(Math.floor((index - 1) / 4)).padStart(2, "0")}`;

/** The quarter before this one ("Q1FY27" -> "Q4FY26"), or null when the text is not a quarter. */
export function prevPeriod(period: string | null | undefined): string | null {
  const i = quarterIndex(period);
  return i == null ? null : periodOf(i - 1);
}

/** The latest `n` quarters ending with this one, oldest first ("Q2FY27", 3 -> Q4FY26, Q1FY27, Q2FY27). */
export function periodsBack(period: string, n = SERIES_QUARTERS): string[] {
  const i = quarterIndex(period);
  if (i == null) return [];
  return Array.from({ length: n }, (_, k) => periodOf(i - (n - 1 - k)));
}

/** A quarter's last day, the day index membership is read on: Q1 = 30 Jun, Q2 = 30 Sep, Q3 = 31 Dec of the calendar year before the
 *  FY label's year, Q4 = 31 Mar of the label's year (Q2FY27 = 2026-09-30, Q4FY27 = 2027-03-31). Null for a text that is not a quarter. */
export function quarterDay(period: string | null | undefined): string | null {
  const m = /^Q([1-4])FY(\d{2})$/.exec(period ?? "");
  if (!m) return null;
  const year = 2000 + Number(m[2]);
  return { 1: `${year - 1}-06-30`, 2: `${year - 1}-09-30`, 3: `${year - 1}-12-31`, 4: `${year}-03-31` }[Number(m[1]) as 1 | 2 | 3 | 4];
}

const round2 = (n: number) => Math.round(n * 100) / 100;

/** This quarter's year-on-year growth minus last quarter's, in points; null when either quarter has no per cent or is "NM" (above +999%). */
export function momentumPts(yoy: number | null | undefined, prevYoy: number | null | undefined): number | null {
  return yoy == null || prevYoy == null || yoy > NM_PCT || prevYoy > NM_PCT ? null : round2(yoy - prevYoy);
}

/** >= +2 points speeding up, <= -2 slowing, between steady; not comparable when either quarter has no per cent. */
export function momentumClass(pts: number | null): Momentum {
  if (pts == null) return "not_comparable";
  return pts >= MOMENTUM_POINTS ? "speeding_up" : pts <= -MOMENTUM_POINTS ? "slowing" : "steady";
}

/** A numeric parameter: a finite number inside the limits, else null. */
const num = (v: string | undefined, min: number, max: number): number | null => {
  if (v == null || v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.min(Math.max(n, min), max) : null;
};

/** The request's query string as a KpiQuery: anything not on the lists is dropped and numbers are clamped, so nothing it holds reaches
 *  the SQL as written. */
export function parseKpiQuery(raw: Record<string, string | undefined>): KpiQuery {
  const sort = (raw.sort ?? "") in KPI_SORTS ? (raw.sort as KpiSort) : "mcap";
  const page = Math.min(Math.max(Number.parseInt(raw.page ?? "", 10) || 1, 1), Math.floor(MAX_OFFSET / PAGE_SIZE) + 1);
  const flag = (v: string | undefined) => v === "1" || v === "true";
  return {
    quarter: quarterIndex(raw.quarter) != null ? raw.quarter! : null,
    index: INDEX_IDS.includes(raw.index ?? "") ? raw.index! : null,
    mcap_min: num(raw.mcap_min, 0, 1e8),
    class: (raw.class ?? "").trim().slice(0, 200) || null,
    q: (raw.q ?? "").trim().slice(0, 60),
    rev_min: num(raw.rev_min, -1e4, 1e6),
    ebitda_min: num(raw.ebitda_min, -1e4, 1e6),
    pat_min: num(raw.pat_min, -1e4, 1e6),
    opm_min: num(raw.opm_min, -1e5, 1e5),
    momentum: raw.momentum === "speeding_up" || raw.momentum === "slowing" ? raw.momentum : null,
    turnaround: flag(raw.turnaround),
    nfo: flag(raw.nfo),
    spread: (SPREADS as readonly string[]).includes(raw.spread ?? "") ? (raw.spread as KpiQuery["spread"]) : null,
    sort,
    dir: raw.dir === "asc" ? "asc" : "desc",
    page,
  };
}

/** Text for LIKE with %, _ and \ taken literally (the query says ESCAPE '\'). */
export const likeEscape = (s: string) => s.replace(/[\\%_]/g, (c) => `\\${c}`);
export const likeContains = (s: string) => `%${likeEscape(s)}%`;

/** The members of an index on a day, as a subquery of ISINs (the day and the index are the caller's placeholders). */
export const memberIsins = (indexPh: string, dayPh: string) =>
  `SELECT isin FROM index_members WHERE index_id = ${indexPh} AND valid_from <= ${dayPh} AND (valid_to IS NULL OR valid_to > ${dayPh})`;

/** The band of profit growth a company sits in, as SQL; a named turn beats the per cent, loss to profit and loss narrowed sit in none. */
export const SPREAD_SQL: Record<NonNullable<KpiQuery["spread"]>, string> = {
  below_0: `(k.pat_turn IN ('PROFIT_TO_LOSS', 'LOSS_WIDENED') OR (k.pat_turn IS NULL AND k.pat_yoy < 0))`,
  from_0_to_10: `(k.pat_turn IS NULL AND k.pat_yoy >= 0 AND k.pat_yoy < 10)`,
  from_10_to_20: `(k.pat_turn IS NULL AND k.pat_yoy >= 10 AND k.pat_yoy < 20)`,
  above_20: `(k.pat_turn IS NULL AND k.pat_yoy >= 20)`,
};

const FROM_SQL = `FROM results_kpi k LEFT JOIN companies co ON co.scrip_code = k.scrip_code
  LEFT JOIN results_kpi pk ON pk.scrip_code = k.scrip_code AND pk.period = `;

/** The filtered rows' FROM and WHERE for a quarter, with their positional parameters (the joins' own come first). */
export function kpiWhere(query: KpiQuery, quarter: string): { from: string; params: unknown[] } {
  const params: unknown[] = [];
  const p = (v: unknown) => (params.push(v), `?${params.length}`);
  const prev = p(prevPeriod(quarter));
  const joins = `${FROM_SQL}${prev} AND pk.basis = k.basis LEFT JOIN filings f ON f.news_id = k.source_news_id`;
  const where = [`k.period = ${p(quarter)}`];
  if (query.index) {
    const day = quarterDay(quarter) ?? "1900-01-01";
    where.push(`co.isin IN (${memberIsins(p(query.index), p(day))})`);
  }
  if (query.mcap_min != null) where.push(`co.market_cap_cr >= ${p(query.mcap_min)}`);
  if (query.class) {
    const path = query.class.replace(/\s*>\s*/g, " > ");
    where.push(`(co.industry = ${p(path)} OR co.industry LIKE ${p(`${likeEscape(path)} > %`)} ESCAPE '\\')`);
  }
  if (query.q) { const t = p(likeContains(query.q)); where.push(`(co.symbol LIKE ${t} ESCAPE '\\' OR co.company_name LIKE ${t} ESCAPE '\\')`); }
  if (query.rev_min != null) where.push(`k.revenue_yoy >= ${p(query.rev_min)}`);
  if (query.ebitda_min != null) where.push(`(k.ebitda_yoy >= ${p(query.ebitda_min)} OR k.ebitda_turn = 'LOSS_TO_PROFIT')`);
  if (query.pat_min != null) where.push(`(k.pat_yoy >= ${p(query.pat_min)} OR k.pat_turn = 'LOSS_TO_PROFIT')`);
  if (query.opm_min != null) where.push(`k.opm_yoy_bps >= ${p(query.opm_min)}`);
  if (query.momentum === "speeding_up") where.push(`round(${momentumSql("pat_yoy")}, 2) >= ${p(MOMENTUM_POINTS)}`);
  if (query.momentum === "slowing") where.push(`round(${momentumSql("pat_yoy")}, 2) <= ${p(-MOMENTUM_POINTS)}`);
  if (query.turnaround) where.push(`k.pat_turn = 'LOSS_TO_PROFIT'`);
  if (query.nfo) where.push(`k.nfo = 1`);
  if (query.spread) where.push(SPREAD_SQL[query.spread]);
  return { from: `${joins} WHERE ${where.join(" AND ")}`, params };
}

/** What a page row is made of: the table's figures, the company's, the filing's and last quarter's growth (for momentum). */
const KPI_BASE = `k.scrip_code, k.period, k.basis, k.kind,
  k.revenue, k.revenue_yoy, k.revenue_qoq, k.ebitda, k.ebitda_yoy, k.ebitda_qoq, k.ebitda_turn,
  k.opm, k.opm_yoy_bps, k.opm_qoq_bps, k.pat, k.pat_yoy, k.pat_qoq, k.pat_turn, k.pat_qoq_turn, k.nfo,
  k.pat_pre, k.pat_pre_yoy, k.pat_pre_turn, k.pat_total, k.pat_total_yoy, k.pat_total_turn,
  co.symbol, co.company_name, co.industry, co.market_cap_cr, co.size_category, f.filed_at, f.pdf_url AS filing_url`;
export const KPI_COLUMNS = `${KPI_BASE},
  pk.revenue_yoy AS prev_revenue_yoy, pk.ebitda_yoy AS prev_ebitda_yoy, pk.pat_yoy AS prev_pat_yoy, pk.pat_turn AS prev_pat_turn`;

/** One company's rows of every quarter, oldest first; last quarter's growth is filled in by the caller from the same rows. */
export const kpiCompanySql = `SELECT ${KPI_BASE} FROM results_kpi k LEFT JOIN companies co ON co.scrip_code = k.scrip_code
  LEFT JOIN filings f ON f.news_id = k.source_news_id WHERE k.scrip_code = ?1`;

/** A company's latest 8 rows, oldest first, each with last quarter's growth and its own series filled from the rows themselves. */
export function companyRows(rows: Omit<DbKpiRow, "prev_revenue_yoy" | "prev_ebitda_yoy" | "prev_pat_yoy" | "prev_pat_turn">[]): KpiRow[] {
  const by = new Map(rows.map((r) => [r.period, r]));
  return [...rows].sort((a, b) => (quarterIndex(a.period) ?? 0) - (quarterIndex(b.period) ?? 0)).slice(-SERIES_QUARTERS).map((r) => {
    const before = by.get(prevPeriod(r.period) ?? "");
    const prev = before?.basis === r.basis ? before : undefined;   // growth on another basis is no pace
    return toKpiRow({ ...r, prev_revenue_yoy: prev?.revenue_yoy ?? null, prev_ebitda_yoy: prev?.ebitda_yoy ?? null,
      prev_pat_yoy: prev?.pat_yoy ?? null, prev_pat_turn: prev?.pat_turn ?? null }, seriesFor(by, r.period, r.basis));
  });
}

/** The page's rows: the chosen sort, a row without the figure last whichever way it runs, the company code to break ties. */
export function kpiRowsSql(query: KpiQuery, from: string): string {
  const col = sortExpr(Object.hasOwn(KPI_SORTS, query.sort) ? (query.sort as KpiSort) : "mcap", query.dir === "asc" ? "asc" : "desc");   // the whitelist again, in case the query was built by hand
  return `SELECT ${KPI_COLUMNS} ${from} ORDER BY (${col}) IS NULL, ${col} ${query.dir === "asc" ? "ASC" : "DESC"}, k.scrip_code
     LIMIT ${PAGE_SIZE} OFFSET ${(query.page - 1) * PAGE_SIZE}`;
}

/** The light columns of every filtered row (capped), which the summary's rules read in resultsStats.ts. */
export const kpiSummaryRowsSql = (from: string) => `SELECT k.scrip_code, k.kind, k.revenue, k.revenue_yoy, k.ebitda, k.ebitda_yoy, k.ebitda_turn,
  k.pat, k.pat_yoy, k.pat_turn, k.nfo, pk.pat_yoy AS prev_pat_yoy ${from} LIMIT ${SUMMARY_CAP}`;

/** A row's last 8 quarters of profit and revenue growth: its own company's rows, the calendar quarters ending with `period`. */
export const kpiSeriesSql = `SELECT scrip_code, period, basis, pat_yoy, revenue_yoy FROM results_kpi
  WHERE scrip_code IN (SELECT value FROM json_each(?1)) AND period IN (SELECT value FROM json_each(?2))`;

export interface DbKpiRow {
  scrip_code: string; period: string; basis: "CONSOLIDATED" | "STANDALONE"; kind: Kind;
  revenue: number | null; revenue_yoy: number | null; revenue_qoq: number | null;
  ebitda: number | null; ebitda_yoy: number | null; ebitda_qoq: number | null; ebitda_turn: Turn | null;
  opm: number | null; opm_yoy_bps: number | null; opm_qoq_bps: number | null;
  pat: number | null; pat_yoy: number | null; pat_qoq: number | null; pat_turn: Turn | null; pat_qoq_turn: Turn | null; nfo: number;
  pat_pre: number | null; pat_pre_yoy: number | null; pat_pre_turn: Turn | null;
  pat_total: number | null; pat_total_yoy: number | null; pat_total_turn: Turn | null;
  symbol: string | null; company_name: string | null; industry: string | null; market_cap_cr: number | null; size_category: string | null;
  prev_revenue_yoy: number | null; prev_ebitda_yoy: number | null; prev_pat_yoy: number | null; prev_pat_turn: Turn | null;
  filed_at: string | null; filing_url: string | null;
}

/** The series of one company for the quarters ending with `period`, from its rows by period; null where no per cent or on another basis. */
export function seriesFor(byPeriod: Map<string, { pat_yoy: number | null; revenue_yoy: number | null; basis?: string }>, period: string, basis?: string) {
  const periods = periodsBack(period);
  // a quarter on the other basis is no point of this row's trend (the table's momentum needs the same basis too)
  const at = (q: string) => { const r = byPeriod.get(q); return r && (!basis || !r.basis || r.basis === basis) ? r : undefined; };
  return {
    series_pat: periods.map((q) => at(q)?.pat_yoy ?? null),
    series_revenue: periods.map((q) => at(q)?.revenue_yoy ?? null),
  };
}

/** A database row as the API's KpiRow: momentum points and class worked out, nfo as a flag. */
export function toKpiRow(r: DbKpiRow, series: { series_pat: (number | null)[]; series_revenue: (number | null)[] }): KpiRow {
  const pat = momentumPts(r.pat_yoy, r.prev_pat_yoy);
  return {
    scrip_code: r.scrip_code, symbol: r.symbol, company_name: r.company_name, industry: r.industry,
    market_cap_cr: r.market_cap_cr, size_category: r.size_category, period: r.period, basis: r.basis, kind: r.kind,
    revenue: r.revenue, revenue_yoy: r.revenue_yoy, revenue_qoq: r.revenue_qoq,
    revenue_prev_yoy: r.prev_revenue_yoy, revenue_momentum_pts: momentumPts(r.revenue_yoy, r.prev_revenue_yoy),
    ebitda: r.ebitda, ebitda_yoy: r.ebitda_yoy, ebitda_qoq: r.ebitda_qoq, ebitda_turn: r.ebitda_turn,
    ebitda_prev_yoy: r.prev_ebitda_yoy, ebitda_momentum_pts: momentumPts(r.ebitda_yoy, r.prev_ebitda_yoy),
    opm: r.opm, opm_yoy_bps: r.opm_yoy_bps, opm_qoq_bps: r.opm_qoq_bps,
    pat: r.pat, pat_yoy: r.pat_yoy, pat_qoq: r.pat_qoq, pat_turn: r.pat_turn, pat_qoq_turn: r.pat_qoq_turn,
    pat_prev_yoy: r.prev_pat_yoy, pat_prev_turn: r.prev_pat_turn, pat_momentum_pts: pat,
    pat_pre: r.pat_pre, pat_pre_yoy: r.pat_pre_yoy, pat_pre_turn: r.pat_pre_turn,
    pat_total: r.pat_total, pat_total_yoy: r.pat_total_yoy, pat_total_turn: r.pat_total_turn,
    momentum: momentumClass(pat), nfo: r.nfo === 1,
    filed_at: r.filed_at, filing_url: r.filing_url, ...series,
  };
}
