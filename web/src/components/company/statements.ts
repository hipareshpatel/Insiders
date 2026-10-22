/** The company page's statements as screener.in lays them out (owner, 2026-10-21: "replicate screener.in look ... we
 * need Q, year and TTM in year", and the balance sheet and cash flow): quarterly results, profit and loss by year with
 * a trailing-twelve-months column, the balance sheet by statement date, cash flows by year and ratios. Every figure is
 * memory's (the filings' XBRL first); the only arithmetic is sums, differences and ratios of those figures, and a line
 * is left empty rather than estimated when a part is missing. No React, so `node --test` runs test/statements.test.ts. */
import type { Dossier } from "../../../shared/types";
import { periodEnd } from "../../lib/periods.ts";

type Metric = Dossier["financial_metrics"][number];
type Values = Map<string, Map<string, number>>;   // metric -> period -> value
export type Cell = number | null;
export type Row = { label: string; cells: Cell[]; kind?: "pct" | "days" | "ratio" | "per_share"; strong?: boolean };
export type Table = { columns: string[]; rows: Row[] };

export type CorporateAction = { ex_date: string; kind: string; factor?: number; subject?: string };
const PER_SHARE = new Set(["eps", "basic_eps", "diluted_eps"]);

/** Per-share figures on today's share count: a period ending before a split or bonus has its EPS divided by the shares
 * one share became (corporate_actions.py), so a quarter before LIC's 1:1 bonus is not twice the one after it and a TTM
 * EPS sums like with like (data chain audit, 22 Oct 2026). Every other figure is untouched. */
export function adjustPerShare(metrics: Metric[], actions: CorporateAction[] | undefined | null): Metric[] {
  const steps = (actions ?? []).filter((a) => a.factor && a.factor > 0 && a.factor !== 1 && a.ex_date);
  if (!steps.length) return metrics;
  return metrics.map((m) => {
    if (!PER_SHARE.has(m.metric) || typeof m.value !== "number") return m;
    const end = periodEnd(String(m.period));
    const factor = steps.filter((a) => a.ex_date > end).reduce((f, a) => f * (a.factor as number), 1);
    return factor === 1 ? m : { ...m, value: Math.round((m.value / factor) * 100) / 100 };
  });
}

const QUARTERS = 12;
const YEARS = 6;

function collect(metrics: Metric[]): Values {
  const out: Values = new Map();
  for (const m of metrics) {
    if (typeof m.value !== "number" || !Number.isFinite(m.value)) continue;
    const row = out.get(m.metric) ?? new Map<string, number>();
    row.set(m.period, m.value);
    out.set(m.metric, row);
  }
  return out;
}

const get = (v: Values, metric: string, period: string): Cell => v.get(metric)?.get(period) ?? null;
const sub = (a: Cell, b: Cell): Cell => (a == null || b == null ? null : a - b);
const pct = (a: Cell, b: Cell): Cell => (a == null || b == null || b === 0 ? null : (a / b) * 100);

/** The basis of memory's main figures: consolidated when any of their sources is, else standalone (a company that files
 *  only standalone results), else not stated. */
export function mainBasis(metrics: Metric[]): "CONSOLIDATED" | "STANDALONE" | null {
  // the metric's own basis (memory sets it from a single source) as well as its sources' (deep audit F-03)
  const bases = new Set(metrics.flatMap((m) => {
    const x = m as Metric & { basis?: string | null; sources?: { basis?: string | null }[] };
    return [x.basis, ...(x.sources ?? []).map((s) => s.basis)];
  }));
  return bases.has("CONSOLIDATED") ? "CONSOLIDATED" : bases.has("STANDALONE") ? "STANDALONE" : null;
}

/** A bank files interest earned as its top line, not revenue. */
export function isBank(metrics: Metric[]): boolean {
  // interest earned on most of its quarters: one stray "revenue" a card wrote must not flip a bank to the Sales layout
  // (deep audit F-01: 11 of 41 banks, SBI's "Sales 1,81,079")
  const quarters = (m: string) => new Set(metrics.filter((x) => x.metric === m).map((x) => x.period)).size;
  return quarters("interest_earned") > 0 && quarters("interest_earned") >= quarters("revenue");
}

/** Screener's lines for one period, from memory's metrics. */
function lines(v: Values, p: string, bank: boolean): Record<string, Cell> {
  const g = (m: string) => get(v, m, p);
  if (bank) {
    // a bank's OperatingExpenses tag is the total, employee cost inside it (RBI Form B): HDFC Bank's Q4FY25
    // 86,779 + 33,489 - 46,986 - 43,904 = 29,378, its own pre-provision profit 29,379
    const revenue = g("interest_earned"), interest = g("interest_expended"), opex = g("other_expenses");
    const nii = sub(revenue, interest);
    const ppop = g("pre_provision_operating_profit") ?? (nii != null && opex != null ? nii + (g("other_income") ?? 0) - opex : null);
    return {
      revenue, interest, nii, other_income: g("other_income"), opex, ppop, provisions: g("provisions"), pbt: g("pbt"),
      tax_pct: pct(g("tax_expense"), g("pbt")), pat: g("pat"), eps: g("eps"),
      gnpa: g("gnpa_pct") ?? g("gnpa_ratio"), nnpa: g("nnpa_pct") ?? g("nnpa_ratio"),
    };
  }
  const revenue = g("revenue");
  const ebitda = g("ebitda") ?? (g("pbt") != null && g("finance_cost") != null && g("depreciation") != null
    && g("other_income") != null   // a missing other income is not zero (deep audit F-07)
    ? g("pbt")! + g("finance_cost")! + g("depreciation")! - g("other_income")! - (g("exceptional_items") ?? 0) : null);
  return {
    revenue, expenses: sub(revenue, ebitda), ebitda, opm: g("ebitda_margin") ?? pct(ebitda, revenue),
    other_income: g("other_income"), interest: g("finance_cost"), depreciation: g("depreciation"),
    exceptional: g("exceptional_items"), pbt: g("pbt"), tax_pct: pct(g("tax_expense"), g("pbt")),
    pat: g("pat"), pat_owners: g("pat_owners"), eps: g("eps"),
  };
}

const CORPORATE: [string, string, Row["kind"]?, boolean?][] = [
  ["revenue", "Sales", undefined, true], ["expenses", "Expenses"], ["ebitda", "Operating profit", undefined, true],
  ["opm", "OPM %", "pct"], ["other_income", "Other income"], ["interest", "Interest"], ["depreciation", "Depreciation"],
  ["exceptional", "Exceptional items"], ["pbt", "Profit before tax"], ["tax_pct", "Tax %", "pct"],
  ["pat", "Net profit", undefined, true], ["pat_owners", "Profit to shareholders"], ["eps", "EPS (₹)", "per_share"],
];
const BANK: [string, string, Row["kind"]?, boolean?][] = [
  ["revenue", "Interest earned", undefined, true], ["interest", "Interest expended"], ["nii", "Net interest income", undefined, true],
  ["other_income", "Other income"], ["opex", "Operating expenses"], ["ppop", "Operating profit (before provisions)", undefined, true],
  ["provisions", "Provisions"], ["pbt", "Profit before tax"], ["tax_pct", "Tax %", "pct"],
  ["pat", "Net profit", undefined, true], ["eps", "EPS (₹)", "per_share"], ["gnpa", "Gross NPA %", "pct"], ["nnpa", "Net NPA %", "pct"],
];

function table(columns: string[], perColumn: Record<string, Cell>[], bank: boolean): Table {
  const rows = (bank ? BANK : CORPORATE).map(([key, label, kind, strong]) => ({ label, kind, strong, cells: perColumn.map((c) => c[key] ?? null) }))
    // a line empty in every column, or zero in every column (the template's filler), is not shown
    .filter((r) => r.cells.some((c) => c != null && c !== 0));
  // profit to shareholders only where it differs from net profit (minority interests)
  const pat = rows.find((r) => r.label === "Net profit");
  return { columns, rows: rows.filter((r) => r.label !== "Profit to shareholders" || r.cells.some((c, i) => c != null && pat?.cells[i] != null && Math.abs(c - pat.cells[i]!) > 0.5)) };
}

const byEnd = (a: string, b: string) => periodEnd(a).localeCompare(periodEnd(b));
const periodsOf = (metrics: Metric[], test: RegExp) => [...new Set(metrics.map((m) => m.period).filter((p) => test.test(p)))].sort(byEnd);

/** Quarterly results, the latest twelve quarters. */
export function quarterlyTable(metrics: Metric[]): Table {
  const bank = isBank(metrics), v = collect(metrics);
  const quarters = periodsOf(metrics, /^Q[1-4]FY\d{2}$/).slice(-QUARTERS);
  return table(quarters, quarters.map((q) => lines(v, q, bank)), bank);
}

const ADDITIVE = ["revenue", "total_income", "other_income", "finance_cost", "depreciation", "exceptional_items", "pbt", "tax_expense",
  "pat", "pat_owners", "eps", "ebitda", "interest_earned", "interest_expended", "employee_cost", "other_expenses", "provisions",
  "pre_provision_operating_profit"];

/** The four quarters to the latest one, when memory has all four and the latest is after the last year's end. */
export function ttmQuarters(metrics: Metric[]): string[] | null {
  const quarters = periodsOf(metrics, /^Q[1-4]FY\d{2}$/);
  const last4 = quarters.slice(-4);
  if (last4.length < 4) return null;
  const years = periodsOf(metrics, /^FY\d{2}$/);
  if (years.length && periodEnd(years[years.length - 1]) >= periodEnd(last4[3])) return null;   // the year is the TTM
  // consecutive: each quarter ends three months after the one before
  const months = last4.map((q) => { const [y, m] = periodEnd(q).split("-").map(Number); return y * 12 + m; });
  return months.every((m, i) => i === 0 || m - months[i - 1] === 3) ? last4 : null;
}

/** Profit and loss by year, the latest six, with a TTM column (owner: "year and TTM in year"). */
export function annualTable(metrics: Metric[]): Table {
  const bank = isBank(metrics), v = collect(metrics);
  const years = periodsOf(metrics, /^FY\d{2}$/).slice(-YEARS);
  const cols = years.map((y) => lines(v, y, bank));
  const ttm = ttmQuarters(metrics);
  if (ttm) {
    for (const metric of ADDITIVE) {
      const parts = ttm.map((q) => get(v, metric, q));
      if (parts.every((x) => x != null)) (v.get(metric) ?? v.set(metric, new Map()).get(metric)!).set("TTM", parts.reduce((a, b) => a! + b!, 0)!);
    }
    v.get("ebitda_margin")?.delete("TTM");
    cols.push(lines(v, "TTM", bank));
  }
  return table([...years, ...(ttm ? ["TTM"] : [])], cols, bank);
}

/** "Mar 2026" for a statement date. */
export function statementDate(period: string): string {
  const end = periodEnd(period);
  const m = end.match(/^(\d{4})-(\d{2})/);
  if (!m) return period;
  return `${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(m[2]) - 1]} ${m[1]}`;
}

type Snapshot = Dossier["balance_sheet"][number];
const num = (s: Snapshot, k: string): Cell => (typeof s[k] === "number" ? (s[k] as number) : null);

/** One snapshot per statement date: the filing's own XBRL first, then the latest; only dates with a full statement
 *  (total assets), the six latest. */
export function balanceSnapshots(sheets: Snapshot[]): Snapshot[] {
  const best = new Map<string, Snapshot>();
  for (const s of sheets) {
    // a full statement: its total, or for an insurer (whose "Assets" is not a total, A-01) its net worth and investments
    if (!s.period || (num(s, "total_assets_cr") == null && (num(s, "net_worth_cr") == null || num(s, "investments_cr") == null))) continue;
    const key = periodEnd(String(s.period)).slice(0, 7);
    const old = best.get(key);
    const xbrl = (x: Snapshot) => String(x.source_news_id ?? "").startsWith("xbrl:");
    if (!old || (xbrl(s) && !xbrl(old)) || (xbrl(s) === xbrl(old) && s.as_of > old.as_of)) best.set(key, s);
  }
  return [...best.entries()].sort((a, b) => a[0].localeCompare(b[0])).slice(-YEARS - 2).map(([, s]) => s);
}

/** The balance sheet as screener.in prints it: what funds the company, then what it owns. */
export function balanceTable(sheets: Snapshot[]): Table {
  const snaps = balanceSnapshots(sheets);
  const col = (f: (s: Snapshot) => Cell) => snaps.map(f);
  const debt = (s: Snapshot) => num(s, "gross_debt_cr");
  const rows: Row[] = [
    { label: "Equity capital", cells: col((s) => num(s, "equity_capital_cr")) },
    { label: "Reserves", cells: col((s) => num(s, "reserves_cr")) },
    { label: "Minority interest", cells: col((s) => num(s, "minority_interest_cr")) },   // so the side adds up (F-06)
    { label: "Deposits", cells: col((s) => num(s, "deposits_cr")) },   // a bank's, and an NBFC's public deposits
    { label: "Borrowings", cells: col(debt) },
    { label: "Other liabilities", cells: col((s) => sub(sub(num(s, "total_liabilities_cr"), debt(s) ?? 0), num(s, "deposits_cr") ?? 0)) },
    { label: "Total liabilities", cells: col((s) => num(s, "total_assets_cr")), strong: true },
    { label: "Advances / loans", cells: col((s) => num(s, "advances_cr")) },
    { label: "Fixed assets", cells: col((s) => num(s, "fixed_assets_cr")) },
    { label: "CWIP", cells: col((s) => num(s, "cwip_cr")) },
    { label: "Investments", cells: col((s) => num(s, "investments_cr")) },
    { label: "Other assets", cells: col((s) => {
      const parts = ["fixed_assets_cr", "cwip_cr", "investments_cr", "advances_cr"].map((k) => num(s, k) ?? 0);
      return sub(num(s, "total_assets_cr"), parts.reduce((a, b) => a + b, 0));
    }) },
    { label: "Total assets", cells: col((s) => num(s, "total_assets_cr")), strong: true },
    { label: "Inventories", cells: col((s) => num(s, "inventories_cr")) },
    { label: "Trade receivables", cells: col((s) => num(s, "receivables_cr")) },
    { label: "Cash & equivalents", cells: col((s) => num(s, "cash_cr")) },
  ];
  return { columns: snaps.map((s) => statementDate(String(s.period))), rows: rows.filter((r) => r.cells.some((c) => c != null && c !== 0)) };
}

/** Cash flows by year, with the latest half year beside them when it is newer than the last year. */
export function cashFlowTable(metrics: Metric[]): Table {
  const v = collect(metrics);
  const has = (p: string) => get(v, "operating_cash_flow", p) != null;
  const years = periodsOf(metrics, /^FY\d{2}$/).filter(has).slice(-YEARS);
  const halves = periodsOf(metrics, /^H1FY\d{2}$/).filter(has);
  const half = halves[halves.length - 1];
  const cols = [...years, ...(half && (!years.length || periodEnd(half) > periodEnd(years[years.length - 1])) ? [half] : [])];
  const g = (m: string) => cols.map((p) => get(v, m, p));
  const capex = g("capex");
  const rows: Row[] = [
    { label: "Cash from operating activity", cells: g("operating_cash_flow"), strong: true },
    { label: "Cash from investing activity", cells: g("investing_cash_flow") },
    { label: "Cash from financing activity", cells: g("financing_cash_flow") },
    { label: "Net cash flow", cells: g("net_cash_flow"), strong: true },
    { label: "Capex", cells: capex.map((c) => (c == null ? null : -Math.abs(c))) },
    { label: "Free cash flow", cells: g("operating_cash_flow").map((o, i) => (o == null || capex[i] == null ? null : o - Math.abs(capex[i]!))) },
  ];
  return { columns: cols, rows: rows.filter((r) => r.cells.some((c) => c != null && c !== 0)) };
}

/** Ratios by year, from the year's figures and its March balance sheet. */
export function ratioTable(metrics: Metric[], sheets: Snapshot[]): Table {
  const v = collect(metrics);
  const years = periodsOf(metrics, /^FY\d{2}$/).slice(-YEARS);
  const march = new Map(balanceSnapshots(sheets).map((s) => [periodEnd(String(s.period)).slice(0, 7), s]));
  const sheet = (y: string) => march.get(periodEnd(y).slice(0, 7));
  const prior = (y: string) => march.get(`${Number(periodEnd(y).slice(0, 4)) - 1}-03`);
  const days = (k: string) => years.map((y) => { const s = sheet(y), rev = get(v, "revenue", y); return s && rev ? (num(s, k) ?? NaN) / rev * 365 : null; })
    .map((x) => (x == null || Number.isNaN(x) ? null : x));
  const roe = years.map((y) => {
    const s = sheet(y), p = prior(y), pat = get(v, "pat_owners", y) ?? get(v, "pat", y);
    const now = s ? num(s, "net_worth_cr") : null, before = p ? num(p, "net_worth_cr") : null;
    const base = now != null && before != null ? (now + before) / 2 : now;
    return pct(pat, base);
  });
  const roce = years.map((y) => {
    const s = sheet(y), pbt = get(v, "pbt", y), fin = get(v, "finance_cost", y);
    const capital = s && num(s, "net_worth_cr") != null ? num(s, "net_worth_cr")! + (num(s, "gross_debt_cr") ?? 0) : null;
    return pbt == null || fin == null ? null : pct(pbt + fin, capital);
  });
  const de = years.map((y) => { const s = sheet(y); const nw = s ? num(s, "net_worth_cr") : null, d = s ? num(s, "gross_debt_cr") : null; return nw && d != null ? d / nw : null; });
  const rows: Row[] = [
    { label: "Debtor days", cells: days("receivables_cr"), kind: "days" },
    { label: "Inventory days (on sales)", cells: days("inventories_cr"), kind: "days" },
    { label: "Payable days (on sales)", cells: days("payables_cr"), kind: "days" },
    { label: "ROE %", cells: roe, kind: "pct" },
    { label: "ROCE %", cells: roce, kind: "pct" },
    { label: "Debt to equity", cells: de, kind: "ratio" },
  ];
  return { columns: years, rows: rows.filter((r) => r.cells.some((c) => c != null)) };
}

/** Compounded growth of a line over the last N years (screener's boxes), and TTM against the four quarters before. */
export function growth(metrics: Metric[], metric: string): { label: string; value: Cell }[] {
  const v = collect(metrics);
  const years = periodsOf(metrics, /^FY\d{2}$/);
  const last = years[years.length - 1];
  // by fiscal year, not by position: with FY24 missing, "3 years" from FY26 is still FY23 (deep audit F-04)
  const fy = (p: string) => 2000 + Number(p.slice(2));
  const cagr = (n: number) => {
    if (!last) return null;
    const from = years.find((y) => fy(y) === fy(last) - n);
    const a = from ? get(v, metric, from) : null, b = get(v, metric, last);
    return a != null && b != null && a > 0 && b > 0 ? (Math.pow(b / a, 1 / n) - 1) * 100 : null;
  };
  // the last eight quarters, consecutive: two windows of four a year apart (deep audit F-05)
  const monthOf = (q: string) => { const [y, m] = periodEnd(q).split("-").map(Number); return y * 12 + m; };
  const quarters = periodsOf(metrics, /^Q[1-4]FY\d{2}$/).slice(-8);
  const consecutive = quarters.length === 8 && quarters.every((q, i) => i === 0 || monthOf(q) - monthOf(quarters[i - 1]) === 3);
  const sum = (qs: string[]) => (qs.length === 4 && qs.every((q) => get(v, metric, q) != null) ? qs.reduce((a, q) => a + get(v, metric, q)!, 0) : null);
  const now = consecutive ? sum(quarters.slice(4)) : null, before = consecutive ? sum(quarters.slice(0, 4)) : null;
  const ttm = now != null && before != null && before > 0 ? (now / before - 1) * 100 : null;
  return [{ label: "5 years", value: cagr(5) }, { label: "3 years", value: cagr(3) }, { label: "TTM", value: ttm }].filter((g) => g.value != null);
}

/** A cell as screener.in prints it: whole crore with Indian grouping (two decimals under 10), percentages to one. */
export function formatCell(c: Cell, kind?: Row["kind"]): string {
  if (c == null || !Number.isFinite(c)) return "";
  if (c === 0) return "0";
  if (kind === "pct") return `${c.toFixed(c !== 0 && Math.abs(c) < 10 ? 1 : 0)}%`;
  if (kind === "days") return Math.round(c).toLocaleString("en-IN");
  if (kind === "ratio") return c.toFixed(2);
  if (kind === "per_share") return c.toFixed(2);
  const digits = Math.abs(c) < 10 ? 2 : 0;
  return c.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
