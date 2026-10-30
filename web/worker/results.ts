// The Results KPI report's API (docs/design/results-kpi.md; shapes in shared/resultsTypes.ts). The rules are pure functions in
// shared/resultsKpi.ts and shared/resultsStats.ts; this file runs their SQL on D1 and puts the answers together.
import type { Hono } from "hono";
import type { Context } from "hono";
import { isCompanyKey } from "../shared/companyKey";
import { industryParts } from "../shared/industry";
import {
  PAGE_SIZE, kpiRowsSql, kpiSeriesSql, kpiSummaryRowsSql, kpiWhere, memberIsins, parseKpiQuery, periodsBack, quarterDay,
  quarterIndex, seriesFor, toKpiRow, companyRows, kpiCompanySql, type DbKpiRow,
} from "../shared/resultsKpi";
import { computeGroups, summarise, type GroupCompany, type IndexMember, type StatRow, type SummaryRow } from "../shared/resultsStats";
import { INDICES, type ClassNode, type ClassificationResponse, type CompanyKpiResponse, type Cut, type GroupBy, type GroupsResponse,
  type KpiProgress, type KpiResponse } from "../shared/resultsTypes";
import type { AppEnv } from "./env";

type Memoised = <T>(key: string, ttlMs: number, load: () => Promise<T>) => Promise<T>;
const todayIst = () => new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10);
const TRACKING_KEY = "index_members:tracking_since";
const MAIN_INDEX = "NIFTY500";

export function registerResultsRoutes(api: Hono<AppEnv>, memoised: Memoised) {
  const quartersOf = (c: Context<AppEnv>) => memoised("results-kpi:quarters", 60_000, async () => {
    const { results } = await c.env.DB.prepare("SELECT period, count(*) AS n FROM results_kpi GROUP BY period").all<{ period: string; n: number }>();
    return results.sort((a, b) => (quarterIndex(b.period) ?? 0) - (quarterIndex(a.period) ?? 0));
  });
  /** an unknown or missing quarter falls back to the newest */
  const pick = (asked: string | null | undefined, quarters: { period: string }[]) =>
    asked && quarters.some((x) => x.period === asked) ? asked : (quarters[0]?.period ?? null);
  const trackingSince = (c: Context<AppEnv>) => memoised("results-kpi:tracking", 60_000, async () => {
    const row = await c.env.DB.prepare("SELECT value FROM kv WHERE key = ?1").bind(TRACKING_KEY).first<{ value: string }>();
    return row && /^\d{4}-\d{2}-\d{2}/.test(row.value) ? row.value.slice(0, 10) : null;
  });

  api.get("/results-kpi", async (c) => {
    const query = parseKpiQuery(c.req.query());
    const quarters = await quartersOf(c);
    const quarter = pick(query.quarter, quarters);
    const since = await trackingSince(c);
    const emptySummary = summarise([]);
    if (!quarter) {
      return c.json({ quarter, quarters, indices: [], index_tracking_since: since, rows: [], summary: emptySummary, progress: null, page: 1, pages: 1 } satisfies KpiResponse);
    }
    const body = await memoised(`results-kpi:${JSON.stringify([query, quarter])}`, 20_000, async () => {
      const { from, params } = kpiWhere(query, quarter);
      const [page, light] = await c.env.DB.batch([
        c.env.DB.prepare(kpiRowsSql(query, from)).bind(...params),
        c.env.DB.prepare(kpiSummaryRowsSql(from)).bind(...params),
      ]);
      const raw = page.results as unknown as DbKpiRow[];
      const summary = summarise(light.results as unknown as SummaryRow[]);
      const series = await seriesOf(c, raw, quarter);
      const rows = raw.map((r) => toKpiRow(r, seriesFor(series.get(r.scrip_code) ?? new Map(), quarter)));
      const [indices, progress] = await Promise.all([indicesOf(c, quarter), progressOf(c, quarter, quarters)]);
      return { quarter, quarters, indices, index_tracking_since: since, rows, summary, progress, page: query.page,
        pages: Math.max(1, Math.ceil(summary.n / PAGE_SIZE)) } satisfies KpiResponse;
    });
    return c.json(body);
  });

  // The latest 8 quarters of profit and revenue growth for the page's companies, one query.
  async function seriesOf(c: Context<AppEnv>, raw: DbKpiRow[], quarter: string) {
    const out = new Map<string, Map<string, { pat_yoy: number | null; revenue_yoy: number | null }>>();
    if (!raw.length) return out;
    const { results } = await c.env.DB.prepare(kpiSeriesSql).bind(JSON.stringify(raw.map((r) => r.scrip_code)), JSON.stringify(periodsBack(quarter)))
      .all<{ scrip_code: string; period: string; pat_yoy: number | null; revenue_yoy: number | null }>();
    for (const r of results) (out.get(r.scrip_code) ?? out.set(r.scrip_code, new Map()).get(r.scrip_code)!).set(r.period, r);
    return out;
  }

  // Companies of the quarter in each index, members read on the quarter's last day.
  async function indicesOf(c: Context<AppEnv>, quarter: string): Promise<KpiResponse["indices"]> {
    const { results } = await c.env.DB.prepare(`SELECT im.index_id, count(DISTINCT k.scrip_code) AS n
        FROM index_members im JOIN companies co ON co.isin = im.isin JOIN results_kpi k ON k.scrip_code = co.scrip_code AND k.period = ?1
       WHERE im.valid_from <= ?2 AND (im.valid_to IS NULL OR im.valid_to > ?2) GROUP BY im.index_id`)
      .bind(quarter, quarterDay(quarter) ?? "1900-01-01").all<{ index_id: string; n: number }>();
    const n = new Map(results.map((r) => [r.index_id, r.n]));
    return INDICES.filter((i) => (n.get(i.id) ?? 0) > 0).map((i) => ({ id: i.id, label: i.label, n: n.get(i.id)! }));
  }

  // Nifty 500 results season: members matched to a company, those with a row, and the nearest board meeting of one that has none.
  // A board meeting is not always a results meeting (the catalysts table does not say), so the date is "the next board meeting".
  async function progressOf(c: Context<AppEnv>, quarter: string, quarters: { period: string; n: number }[]): Promise<KpiProgress | null> {
    const day = quarterDay(quarter) ?? "1900-01-01";
    const members = `SELECT DISTINCT co.scrip_code FROM companies co WHERE co.isin IN (${memberIsins("?1", "?2")})`;
    const [counts, next] = await c.env.DB.batch([
      c.env.DB.prepare(`SELECT count(*) AS of, coalesce(sum(k.scrip_code IS NOT NULL), 0) AS reported
        FROM (${members}) m LEFT JOIN results_kpi k ON k.scrip_code = m.scrip_code AND k.period = ?3`).bind(MAIN_INDEX, day, quarter),
      c.env.DB.prepare(`SELECT ct.event_date AS date, count(DISTINCT ct.scrip_code) AS companies
        FROM catalysts ct WHERE ct.event_type = 'BOARD_MEETING' AND ct.event_date >= ?4
         AND ct.scrip_code IN (${members}) AND NOT EXISTS (SELECT 1 FROM results_kpi k WHERE k.scrip_code = ct.scrip_code AND k.period = ?3)
         GROUP BY ct.event_date ORDER BY ct.event_date LIMIT 1`).bind(MAIN_INDEX, day, quarter, todayIst()),
    ]);
    const c0 = counts.results[0] as { of: number; reported: number } | undefined;
    if (!c0 || !c0.of) return null;
    // an upcoming meeting says nothing about a quarter that is not the newest
    const still = quarter === quarters[0]?.period ? ((next.results[0] as { date: string; companies: number } | undefined) ?? null) : null;
    return { index_id: MAIN_INDEX, reported: c0.reported, of: c0.of, quarter_reported: quarters.find((x) => x.period === quarter)?.n ?? 0, still_to_come: still };
  }

  api.get("/results-classification", async (c) => {
    const quarters = await quartersOf(c);
    const quarter = pick(c.req.query("quarter"), quarters);
    if (!quarter) return c.json({ quarter, tree: [], unclassified: 0 } satisfies ClassificationResponse);
    const body = await memoised(`results-class:${quarter}`, 300_000, async () => {
      const { results } = await c.env.DB.prepare(`SELECT co.industry AS industry, count(*) AS n FROM results_kpi k
          LEFT JOIN companies co ON co.scrip_code = k.scrip_code WHERE k.period = ?1 GROUP BY co.industry`).bind(quarter).all<{ industry: string | null; n: number }>();
      const tree: ClassNode[] = [];
      let unclassified = 0;
      for (const r of results) {
        const parts = industryParts(r.industry);
        if (!parts.length) { unclassified += r.n; continue; }
        let level = tree;
        parts.forEach((name, i) => {
          let node = level.find((x) => x.name === name);
          if (!node) level.push(node = { name, path: parts.slice(0, i + 1).join(" > "), n: 0, children: [] });
          node.n += r.n;
          level = node.children;
        });
      }
      const sort = (nodes: ClassNode[]) => { nodes.sort((a, b) => a.name.localeCompare(b.name)); nodes.forEach((x) => sort(x.children)); };
      sort(tree);
      return { quarter, tree, unclassified } satisfies ClassificationResponse;
    });
    return c.json(body);
  });

  api.get("/results-groups", async (c) => {
    const q = c.req.query();
    const by: GroupBy = q.by === "sector" || q.by === "industry" ? q.by : "index";
    const cut: Cut = q.cut === "ex_financials" || q.cut === "financials" ? q.cut : "all";
    const withinIndex = INDICES.some((i) => i.id === q.within_index) ? q.within_index : null;
    const mcap = Number(q.within_mcap);
    const withinMcap = q.within_mcap && Number.isFinite(mcap) ? Math.min(Math.max(mcap, 0), 1e8) : null;
    const quarters = await quartersOf(c);
    const quarter = pick(q.quarter, quarters);
    const since = await trackingSince(c);
    if (!quarter) return c.json({ quarter, quarters, by, cut, index_tracking_since: since, rows: [] } satisfies GroupsResponse);
    const body = await memoised(`results-groups:${JSON.stringify([quarter, by, cut, withinIndex, withinMcap])}`, 180_000, async () => {
      const periods = JSON.stringify(periodsBack(quarter));
      const db = c.env.DB;
      const [rows, companies, members] = await db.batch([
        db.prepare(`SELECT scrip_code, period, kind, revenue, revenue_prev, revenue_yoy, ebitda, ebitda_prev, ebitda_yoy, ebitda_turn,
            pat, pat_prev, pat_yoy, pat_turn FROM results_kpi WHERE period IN (SELECT value FROM json_each(?1))`).bind(periods),
        db.prepare(`SELECT scrip_code, isin, industry, market_cap_cr FROM companies WHERE scrip_code IN
            (SELECT DISTINCT scrip_code FROM results_kpi WHERE period IN (SELECT value FROM json_each(?1)))
            OR (?2 = 1 AND isin IN (SELECT isin FROM index_members))`).bind(periods, by === "index" ? 1 : 0),   // an index's "of" counts members with no row yet
        // an index view reads every index's members; a sector or industry view only the one it narrows to (or none)
        db.prepare(`SELECT index_id, isin, valid_from, valid_to FROM index_members WHERE ?1 = 'all' OR index_id = ?2`)
          .bind(by === "index" ? "all" : "one", withinIndex),
      ]);
      return { quarter, quarters, by, cut, index_tracking_since: since,
        rows: computeGroups({ quarter, by, cut, rows: rows.results as unknown as StatRow[], companies: companies.results as unknown as GroupCompany[],
          members: members.results as unknown as IndexMember[], withinIndex, withinMcap }) } satisfies GroupsResponse;
    });
    return c.json(body);
  });

  api.get("/results-company/:key", async (c) => {
    const asked = c.req.param("key").toUpperCase();
    if (!isCompanyKey(asked)) return c.json({ error: "bad company key" }, 400);
    const scrip = /^\d+$/.test(asked) || asked.startsWith("NSE:") ? asked
      : ((await c.env.DB.prepare("SELECT scrip_code FROM companies WHERE symbol = ?1 LIMIT 1").bind(asked).first<{ scrip_code: string }>())?.scrip_code ?? asked);
    const body = await memoised(`results-company:${scrip}`, 30_000, async () => {
      const [company, rows] = await c.env.DB.batch([
        c.env.DB.prepare("SELECT scrip_code, symbol, company_name, industry FROM companies WHERE scrip_code = ?1").bind(scrip),
        c.env.DB.prepare(kpiCompanySql).bind(scrip),
      ]);
      return { company: (company.results[0] as CompanyKpiResponse["company"] | undefined) ?? null, rows: companyRows(rows.results as unknown as DbKpiRow[]) } satisfies CompanyKpiResponse;
    });
    return c.json(body);
  });
}
