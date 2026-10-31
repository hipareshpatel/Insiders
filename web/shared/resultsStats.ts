/** The Results report's rules as pure functions (docs/design/results-kpi.md, rules 2 to 7): the summary above the table and the group
 *  view's figures. The Worker reads the rows from D1 and calls these, so every rule is tested under `node --test` (resultsStats.test.ts). */
import { INDICES } from "./resultsTypes.ts";
import type { Cut, GroupBy, GroupRow, KpiSummary, Kind, Momentum, Turn } from "./resultsTypes.ts";
import { momentumClass, momentumPts, periodsBack, quarterDay } from "./resultsKpi.ts";
import { industryParts } from "./industry.ts";

/** The figures of one company and quarter that the rules read. */
export interface StatRow {
  scrip_code: string;
  period: string;
  basis?: string;   // when given, momentum and the trend use only quarters on the quarter's own basis (as the table does)
  kind: Kind;
  revenue: number | null; revenue_prev: number | null; revenue_yoy: number | null;
  ebitda: number | null; ebitda_prev: number | null; ebitda_yoy: number | null; ebitda_turn: Turn | null;
  pat: number | null; pat_prev: number | null; pat_yoy: number | null; pat_turn: Turn | null;
}

/** A summary row: the figures above, whether profit came from outside operations, and last quarter's profit growth. */
export interface SummaryRow {
  kind: Kind;
  revenue: number | null; revenue_yoy: number | null;
  ebitda: number | null; ebitda_yoy: number | null; ebitda_turn: Turn | null;
  pat: number | null; pat_yoy: number | null; pat_turn: Turn | null;
  nfo: number;
  prev_pat_yoy: number | null;
}

export type Band = "below_0" | "from_0_to_10" | "from_10_to_20" | "above_20" | "loss_to_profit" | "loss_narrowed";

/** The middle of the numbers (the mean of the two middle ones for an even count), null for none. */
export function median(values: number[]): number | null {
  if (!values.length) return null;
  const v = [...values].sort((a, b) => a - b);
  const mid = v.length >> 1;
  return v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2;
}

/** Where a company's profit growth sits for the spread bars: a named turn first (profit to loss and a wider loss are falls; loss to
 *  profit and a narrower loss sit outside the bars), else the per cent (a fall is below 0, exactly 20 is above), else nowhere (null). */
export function bandOf(r: { pat_yoy: number | null; pat_turn: Turn | null }): Band | null {
  if (r.pat_turn === "PROFIT_TO_LOSS" || r.pat_turn === "LOSS_WIDENED") return "below_0";
  if (r.pat_turn === "LOSS_TO_PROFIT") return "loss_to_profit";
  if (r.pat_turn === "LOSS_NARROWED") return "loss_narrowed";
  if (r.pat_yoy == null) return null;
  return r.pat_yoy < 0 ? "below_0" : r.pat_yoy < 10 ? "from_0_to_10" : r.pat_yoy < 20 ? "from_10_to_20" : "above_20";
}

/** A company with a per cent change (a change across a loss has none and is left out of medians). */
const pct = (v: number | null, turn: Turn | null): number | null => (turn == null ? v : null);

/** Growth of a group's total: the sum of this quarter's amounts against the sum of the same line a year ago, loss-makers included; a
 *  company counts only when it has both amounts; null when no company does or the base total is not positive. */
export function totalGrowth(pairs: { cur: number | null; prev: number | null }[]): number | null {
  let cur = 0, prev = 0, n = 0;
  for (const x of pairs) if (x.cur != null && x.prev != null) { cur += x.cur; prev += x.prev; n++; }
  return n && prev > 0 ? (cur / prev - 1) * 100 : null;
}

const isUp = (yoy: number | null, turn: Turn | null) => turn === "LOSS_TO_PROFIT" || (turn == null && yoy != null && yoy > 0);

/** The numbers above the table for a set of companies (rules 2, 3, 4, 5, 7). */
export function summarise(rows: SummaryRow[]): KpiSummary {
  const ordinary = rows.filter((r) => r.kind === "company");
  const withEbitda = ordinary.filter((r) => r.ebitda != null || r.ebitda_turn != null);
  const spread = { below_0: 0, from_0_to_10: 0, from_10_to_20: 0, above_20: 0, loss_to_profit: 0, loss_narrowed: 0, with_pct: 0 };
  const momentum = { speeding_up: 0, slowing: 0, steady: 0, not_comparable: 0 };
  for (const r of rows) {
    const b = bandOf(r);
    if (b) spread[b]++;
    momentum[momentumClass(momentumPts(r.pat_yoy, r.prev_pat_yoy))]++;
  }
  spread.with_pct = spread.below_0 + spread.from_0_to_10 + spread.from_10_to_20 + spread.above_20;
  const withRevenue = rows.filter((r) => r.revenue != null);
  // "X of Y grew": Y holds only companies that can be compared (a per cent or a named turn); a company with no year-ago quarter is
  // in `*_n` (reported) but not in `*_of` (measured 31 Oct 2026, live Q2FY27: 401 of 611 read 65.6%, 401 of 553 comparable is 72.5%)
  const comparable = (yoy: number | null, turn: Turn | null) => yoy != null || turn != null;
  return {
    n: rows.length,
    revenue_up: withRevenue.filter((r) => r.revenue_yoy != null && r.revenue_yoy > 0).length,
    revenue_of: withRevenue.filter((r) => r.revenue_yoy != null).length,
    revenue_n: withRevenue.length,
    ebitda_up: withEbitda.filter((r) => isUp(r.ebitda_yoy, r.ebitda_turn)).length,
    ebitda_of: withEbitda.filter((r) => comparable(r.ebitda_yoy, r.ebitda_turn)).length,
    ebitda_n: withEbitda.length,
    pat_up: rows.filter((r) => isUp(r.pat_yoy, r.pat_turn)).length,
    pat_of: rows.filter((r) => comparable(r.pat_yoy, r.pat_turn)).length,
    pat_n: rows.length,
    loss_to_profit: rows.filter((r) => r.pat_turn === "LOSS_TO_PROFIT").length,
    // the base of "loss to profit": companies that made a loss a year ago (it turned to profit, narrowed or widened), not every company
    loss_prev_n: rows.filter((r) => r.pat_turn === "LOSS_TO_PROFIT" || r.pat_turn === "LOSS_NARROWED" || r.pat_turn === "LOSS_WIDENED").length,
    median_revenue_yoy: median(withRevenue.map((r) => r.revenue_yoy).filter((v): v is number => v != null)),
    median_ebitda_yoy: median(ordinary.map((r) => pct(r.ebitda_yoy, r.ebitda_turn)).filter((v): v is number => v != null)),
    median_pat_yoy: median(rows.map((r) => pct(r.pat_yoy, r.pat_turn)).filter((v): v is number => v != null)),
    median_pat_n: rows.filter((r) => pct(r.pat_yoy, r.pat_turn) != null).length,
    pat_turn_n: rows.filter((r) => r.pat_turn != null).length,
    spread, momentum,
    nfo: ordinary.filter((r) => r.nfo === 1).length,
  };
}

// ---- the group view ----

export interface IndexMember { index_id: string; isin: string; valid_from: string; valid_to: string | null }
export interface GroupCompany { scrip_code: string; isin: string | null; industry: string | null; market_cap_cr: number | null }

/** The ISINs that are members of an index on a day: valid_from <= day AND (valid_to IS NULL OR valid_to > day). */
export function membersOn(members: IndexMember[], indexId: string, day: string): Set<string> {
  const out = new Set<string>();
  for (const m of members) if (m.index_id === indexId && m.valid_from <= day && (m.valid_to == null || m.valid_to > day)) out.add(m.isin);
  return out;
}

/** Banks, NBFCs and insurers. A REIT or an InvIT is not one, and is not an ordinary company either: it is in "all" only. */
export const isFinancial = (kind: Kind) => kind === "bank" || kind === "nbfc" || kind === "insurer";
const inCut = (kind: Kind, cut: Cut) => cut === "all" || (cut === "ex_financials" ? kind === "company" : isFinancial(kind));

export interface GroupsInput {
  quarter: string;
  by: GroupBy;
  cut: Cut;
  /** rows of every company for the latest 8 quarters ending with `quarter` (more or fewer are fine) */
  rows: StatRow[];
  companies: GroupCompany[];
  members: IndexMember[];
  withinIndex: string | null;
  withinMcap: number | null;
}

/** One group per index, sector (classification step 1) or industry (steps 1-2), with the figures of GroupRow; sorted by median profit
 *  growth, highest first. Index members are read on each quarter's last day, so a trend point uses the members of its own quarter. */
export function computeGroups(input: GroupsInput): GroupRow[] {
  const { quarter, by, cut, withinIndex, withinMcap } = input;
  const periods = periodsBack(quarter);
  const company = new Map(input.companies.map((c) => [c.scrip_code, c]));
  const byPeriod = new Map<string, StatRow[]>(periods.map((p) => [p, []]));
  for (const r of input.rows) byPeriod.get(r.period)?.push(r);
  const prevByScrip = new Map((byPeriod.get(periods[periods.length - 2]) ?? []).map((r) => [r.scrip_code, r]));
  const basisNow = new Map((byPeriod.get(quarter) ?? []).map((r) => [r.scrip_code, r.basis]));
  /** a row of another quarter counts only on the basis its company reports this quarter (rows without a basis always count) */
  const sameBasis = (r: StatRow) => !r.basis || !basisNow.get(r.scrip_code) || basisNow.get(r.scrip_code) === r.basis;
  const narrowed = (c: GroupCompany | undefined, within: Set<string> | null) =>
    !!c && (withinMcap == null || (c.market_cap_cr != null && c.market_cap_cr >= withinMcap)) && (!within || (c.isin != null && within.has(c.isin)));
  const sets = new Map<string, Set<string>>();   // index members by "index|period"
  const setOf = (indexId: string, period: string) => {
    const key = `${indexId}|${period}`;
    if (!sets.has(key)) sets.set(key, membersOn(input.members, indexId, quarterDay(period) ?? "1900-01-01"));
    return sets.get(key)!;
  };
  const stepsOf = (c: GroupCompany): string | null => {
    const parts = industryParts(c.industry);
    return by === "sector" ? (parts[0] ?? null) : parts.length >= 2 ? parts.slice(0, 2).join(" > ") : null;
  };

  /** the companies' rows of one quarter by group id (every cut: the cut is applied afterwards) */
  const groupsAt = (period: string) => {
    const within = withinIndex ? setOf(withinIndex, period) : null;
    const groups = new Map<string, StatRow[]>();
    const add = (id: string, r: StatRow) => { (groups.get(id) ?? groups.set(id, []).get(id)!).push(r); };
    for (const r of byPeriod.get(period) ?? []) {
      const c = company.get(r.scrip_code);
      if (!narrowed(c, within) || !c) continue;
      if (by === "index") {
        if (c.isin) for (const i of INDICES) if (setOf(i.id, period).has(c.isin)) add(i.id, r);
      } else {
        const id = stepsOf(c);
        if (id) add(id, r);
      }
    }
    return groups;
  };

  const current = groupsAt(quarter);
  const ids = by === "index" ? INDICES.map((i) => i.id) : [...current.keys()];
  const trends = periods.map((p) => (p === quarter ? current : groupsAt(p)));
  const label = (id: string) => (by === "index" ? INDICES.find((i) => i.id === id)!.label : (industryParts(id).pop() ?? id));
  const withinNow = withinIndex ? setOf(withinIndex, quarter) : null;
  const out: GroupRow[] = [];
  for (const id of ids) {
    const all = current.get(id) ?? [];
    const rows = all.filter((r) => inCut(r.kind, cut));
    let of: number | null = null;
    if (by === "index") {
      const isins = setOf(id, quarter);
      of = input.companies.filter((c) => c.isin != null && isins.has(c.isin) && narrowed(c, withinNow)).length;
      if (!of) continue;
    } else if (!rows.length) continue;
    const fin = all.filter((r) => isFinancial(r.kind));
    const ord = all.filter((r) => r.kind === "company");
    const pairs = (xs: StatRow[], f: "pat" | "revenue" | "ebitda") => xs.map((r) => ({ cur: r[f], prev: r[`${f}_prev`] }));
    const patSum = (xs: StatRow[]) => xs.reduce((s, r) => s + (r.pat ?? 0), 0);
    const bands = { below_0: 0, from_0_to_10: 0, from_10_to_20: 0, above_20: 0 };
    for (const r of rows) { const b = bandOf(r); if (b && b in bands) bands[b as keyof typeof bands]++; }
    const inBars = bands.below_0 + bands.from_0_to_10 + bands.from_10_to_20 + bands.above_20;
    const known = rows.map((r) => momentumClass(momentumPts(r.pat_yoy, (sameBasis(prevByScrip.get(r.scrip_code) ?? r) ? prevByScrip.get(r.scrip_code)?.pat_yoy : null)))).filter((m: Momentum) => m !== "not_comparable");
    const totalPat = patSum(all.filter((r) => r.pat != null));
    out.push({
      id, label: label(id), reported: of != null ? all.length : rows.length, of,
      pat_median: median(rows.map((r) => pct(r.pat_yoy, r.pat_turn)).filter((v): v is number => v != null)),
      pat_total_all: totalGrowth(pairs(all, "pat")), pat_total_ex_financials: totalGrowth(pairs(ord, "pat")), pat_total_financials: totalGrowth(pairs(fin, "pat")),
      financials_share_pct: totalPat > 0 ? (patSum(fin) / totalPat) * 100 : null,
      revenue_total_all: totalGrowth(pairs(all, "revenue")), revenue_total_ex_financials: totalGrowth(pairs(ord, "revenue")),
      revenue_total_financials: totalGrowth(pairs(fin, "revenue")),
      ebitda_total_ex_financials: totalGrowth(pairs(ord, "ebitda")),
      spread_pct: inBars ? [bands.below_0, bands.from_0_to_10, bands.from_10_to_20, bands.above_20].map((n) => (n / inBars) * 100) as [number, number, number, number] : [0, 0, 0, 0],
      speeding_up_pct: known.length ? (known.filter((m) => m === "speeding_up").length / known.length) * 100 : null,
      trend_pat_median: trends.map((g) => median((g.get(id) ?? []).filter((r) => inCut(r.kind, cut) && sameBasis(r)).map((r) => pct(r.pat_yoy, r.pat_turn)).filter((v): v is number => v != null))),
    });
  }
  return out.sort((a, b) => (a.pat_median == null ? 1 : 0) - (b.pat_median == null ? 1 : 0) || (b.pat_median ?? 0) - (a.pat_median ?? 0) || a.label.localeCompare(b.label));
}
