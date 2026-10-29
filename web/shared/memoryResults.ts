/** The Results table's figures, read from memory rather than from the card (owner, 29 Oct 2026: "use consolidated, use
 * numbers from memory not card"). Shared by the worker (which trims a company's memory to these rows) and the Results page
 * (which turns them into the table). Rule: consolidated wherever memory holds one, standalone only where it holds no
 * consolidated figure, and a year-ago figure only on the same basis as the quarter (never a consolidated quarter set
 * against a standalone year). No React and no Worker APIs here, so `node --test` runs the cases in test/memoryResults.test.ts. */

export interface Candidate { value: number; basis?: string | null }
export interface MemoryRow { metric: string; period: string; candidates: Candidate[] }
export type MemoryByScrip = Record<string, MemoryRow[]>;

/** The memory lines the Results table reads: the sales line by sector (revenue, a bank's interest earned, an insurer's gross
 * premium), operating profit and profit after tax. */
export const RESULT_METRICS = ["revenue", "interest_earned", "gross_premium", "ebitda", "pat"] as const;

const QUARTER = /^Q([1-4])FY(\d{2})$/;

export function priorYear(period: string): string | null {
  const m = QUARTER.exec(period);
  return m ? `Q${m[1]}FY${String(Number(m[2]) - 1).padStart(2, "0")}` : null;
}

const finite = (c: Candidate) => typeof c.value === "number" && Number.isFinite(c.value);

/** One figure from a memory row's candidates. With `want`, only that basis; else consolidated first, then standalone. */
export function figureOf(cands: Candidate[], want?: string): { value: number; basis: string | null } | undefined {
  const ok = cands.filter(finite);
  const hit = want !== undefined
    ? ok.find((c) => c.basis === want)
    : ok.find((c) => c.basis === "CONSOLIDATED") ?? ok.find((c) => c.basis === "STANDALONE") ?? ok[0];
  return hit ? { value: hit.value, basis: hit.basis ?? null } : undefined;
}

/** The trimmed rows of one company's memory (`financial_metrics`): the result lines of quarters, with every figure stored
 * for each (the entry's own and each source's), so the basis can be chosen here. */
export function resultRows(metrics: unknown): MemoryRow[] {
  if (!Array.isArray(metrics)) return [];
  const rows: MemoryRow[] = [];
  for (const m of metrics as Array<Record<string, unknown>>) {
    if (typeof m.metric !== "string" || typeof m.period !== "string") continue;
    if (!(RESULT_METRICS as readonly string[]).includes(m.metric) || !QUARTER.test(m.period)) continue;
    const sources = Array.isArray(m.sources) ? (m.sources as Array<Record<string, unknown>>) : [];
    const candidates: Candidate[] = [{ value: m.value as number, basis: (m.basis as string | undefined) ?? null },
      ...sources.map((s) => ({ value: s.value as number, basis: (s.basis as string | undefined) ?? null }))];
    rows.push({ metric: m.metric, period: m.period, candidates });
  }
  return rows;
}

export type Turn = "LOSS_TO_PROFIT" | "PROFIT_TO_LOSS" | "LOSS_NARROWED" | "LOSS_WIDENED";
export interface TableLine { value: number; yoy_pct?: number; yoy_bps?: number; turn?: Turn }
export interface MemoryTable { lens: "company" | "bank" | "insurer"; sales?: TableLine; ebitda?: TableLine; margin?: TableLine; pat?: TableLine }

/** A change from one figure to its year-ago figure: a percentage, a turn across a loss, or nothing. */
function changeOf(now: number, base: number | undefined): Pick<TableLine, "yoy_pct" | "turn"> {
  if (base === undefined) return {};
  if (now < 0 && base < 0) return { turn: now > base ? "LOSS_NARROWED" : "LOSS_WIDENED" };
  if (now >= 0 && base < 0) return { turn: "LOSS_TO_PROFIT" };
  if (now < 0 && base >= 0) return { turn: "PROFIT_TO_LOSS" };
  return base === 0 ? {} : { yoy_pct: Math.round(((now - base) / base) * 1000) / 10 };
}

/** The table for one quarter from memory. Undefined lines are blank cells: memory holds no such figure for that quarter. */
export function memoryTable(rows: MemoryRow[], period: string): MemoryTable {
  const prior = priorYear(period);
  const cands = (metric: string, p: string | null) => rows.find((r) => r.metric === metric && r.period === p)?.candidates ?? [];
  const has = (metric: string) => figureOf(cands(metric, period)) !== undefined;
  const lens = has("interest_earned") ? "bank" : has("gross_premium") ? "insurer" : "company";
  const salesMetric = lens === "bank" ? "interest_earned" : lens === "insurer" ? "gross_premium" : "revenue";

  // the sales line's basis decides the basis of every other line in the table, so a margin never mixes two bases
  const sales = figureOf(cands(salesMetric, period));
  const basis = sales?.basis ?? undefined;
  const pick = (metric: string, p: string | null) => (basis ? figureOf(cands(metric, p), basis) : figureOf(cands(metric, p)));
  const line = (metric: string): TableLine | undefined => {
    const now = pick(metric, period);
    if (!now) return undefined;
    return { value: now.value, ...changeOf(now.value, pick(metric, prior)?.value) };
  };

  const salesLine = line(salesMetric);
  const ebitdaNow = pick("ebitda", period), ebitdaPrior = pick("ebitda", prior);
  const salesPrior = pick(salesMetric, prior);
  let margin: TableLine | undefined;
  if (sales && ebitdaNow && sales.value > 0) {
    const now = (ebitdaNow.value / sales.value) * 100;
    const before = prior && salesPrior && ebitdaPrior && salesPrior.value > 0 ? (ebitdaPrior.value / salesPrior.value) * 100 : undefined;
    margin = { value: Math.round(now * 10) / 10, ...(before !== undefined ? { yoy_bps: Math.round((now - before) * 100) } : {}) };
  }
  return { lens, sales: salesLine, ebitda: line("ebitda"), margin, pat: line("pat") };
}
