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
export type Restated = { original: number; restated_in: string };
export type Row = { label: string; cells: Cell[]; kind?: "pct" | "days" | "ratio" | "per_share"; strong?: boolean;
  /** per cell: the figure was restated by a later filing (the cell shows the restated one; this keeps the original) */
  restated?: (Restated | null)[] };
export type Table = { columns: string[]; rows: Row[] };

// owner rule 26 Oct 2026: no EPS on cards or stock pages. Memory keeps every EPS figure; no row, TTM or split adjustment of it here.
const NO_EPS = new Set(["eps", "basic_eps", "diluted_eps", "eps_total", "eps_continuing"]);

const QUARTERS = 12;
const YEARS = 6;

function collect(metrics: Metric[]): Values {
  const out: Values = new Map();
  for (const m of metrics) {
    if (NO_EPS.has(m.metric)) continue;
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

const HEADLINE = new Set(["revenue", "interest_earned", "total_income", "ebitda", "pat", "pbt"]);

/** The basis of memory's main figures: the one most of its metrics carry (a tie goes to consolidated), else not stated.
 *  Not "any one metric is consolidated": ICICI General's single stray solvency ratio tagged consolidated labelled a page
 *  of standalone figures Consolidated (stock-page audit 137, A2). A metric counts once, by its own basis, else by its
 *  sources'. */
export function mainBasis(metrics: Metric[]): "CONSOLIDATED" | "STANDALONE" | null {
  // the headline results lines only: standalone-only KPIs and ratios must not outvote a consolidated company's results;
  // with none of them on record, all metrics
  const headline = metrics.filter((m) => HEADLINE.has(m.metric));
  const count = (rows: Metric[]) => {
    let consolidated = 0;
    let standalone = 0;
    for (const m of rows) {
      const x = m as Metric & { basis?: string | null; sources?: { basis?: string | null }[] };
      // the metric's own basis (memory sets it from a single source) as well as its sources' (deep audit F-03)
      const votes = x.basis ? [x.basis] : (x.sources ?? []).map((s) => s.basis);
      const c = votes.filter((v) => v === "CONSOLIDATED").length;
      const st = votes.filter((v) => v === "STANDALONE").length;
      if (c && c >= st) consolidated++;
      else if (st) standalone++;
    }
    return { consolidated, standalone };
  };
  let n = count(headline);
  if (n.consolidated === 0 && n.standalone === 0) n = count(metrics);
  return n.consolidated === 0 && n.standalone === 0 ? null : n.consolidated >= n.standalone ? "CONSOLIDATED" : "STANDALONE";
}

/** A bank files interest earned as its top line, not revenue. */
export function isBank(metrics: Metric[]): boolean {
  // interest earned on most of its quarters: one stray "revenue" a card wrote must not flip a bank to the Sales layout
  // (deep audit F-01: 11 of 41 banks, SBI's "Sales 1,81,079")
  const quarters = (m: string) => new Set(metrics.filter((x) => x.metric === m).map((x) => x.period)).size;
  return quarters("interest_earned") > 0 && quarters("interest_earned") >= quarters("revenue");
}

/** Screener's lines for one period, from memory's metrics. `screener` (TODO 52, F210, default off) builds the lines by
 *  the formulas docs/design/screener-mapping.md measures: Sales net of excise duty, Expenses = total expenses less
 *  interest and depreciation, Operating profit = Sales - Expenses, Other income as the plug that holds exceptional items
 *  and the associates' share, PBT and Tax % with the associates' share, a lender's Revenue = total income - other income. */
function lines(v: Values, p: string, bank: boolean, screener = false): Record<string, Cell> {
  const g = (m: string) => get(v, m, p);
  if (screener && !bank) {
    // the caller (screenerReady) has checked every column; a column that still lacks a part shows no derived cell
    if (g("revenue") == null || g("total_expenses") == null || g("finance_cost") == null || g("depreciation") == null) return {};
    const excise = g("excise_duty") ?? 0;
    const sales = g("revenue")! - excise;
    // total expenses hold the excise duty (Schedule III), so screener's Expenses take it out as its Sales does: ITC revenue
    // 100, excise 10, total expenses 60 + 20 interest and depreciation: Sales 90, Expenses 50 (80 - 20 - 10), Operating profit 40
    const expenses = g("total_expenses")! - g("finance_cost")! - g("depreciation")! - excise;
    const op = sales - expenses;
    const assoc = g("share_associates") ?? 0;
    const pbt = g("pbt") != null ? g("pbt")! + assoc : null;
    return {
      revenue: sales, expenses, ebitda: op, opm: pct(op, sales), other_income: (g("other_income") ?? 0) + (g("exceptional_items") ?? 0) + assoc,
      interest: g("finance_cost"), depreciation: g("depreciation"), pbt, tax_pct: pct(g("tax_expense"), pbt),
      pat: g("pat"), pat_owners: g("pat_owners"),
    };
  }
  if (bank) {
    // a bank's OperatingExpenses tag is the total, employee cost inside it (RBI Form B): HDFC Bank's Q4FY25
    // 86,779 + 33,489 - 46,986 - 43,904 = 29,378, its own pre-provision profit 29,379
    const revenue = screener ? sub(g("total_income"), g("other_income")) : g("interest_earned"), interest = g("interest_expended"), opex = g("other_expenses");
    const nii = sub(revenue, interest);
    const ppop = g("pre_provision_operating_profit") ?? (nii != null && opex != null ? nii + (g("other_income") ?? 0) - opex : null);
    return {
      revenue, interest, nii, other_income: g("other_income"), opex, ppop, provisions: g("provisions"), pbt: g("pbt"),
      tax_pct: pct(g("tax_expense"), g("pbt")), pat: g("pat"),
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
    pat: g("pat"), pat_owners: g("pat_owners"),
  };
}

/** Screener's formulas for a table only when every column has the parts of its top line; else the table keeps the usual lines
 *  whole, so one table never mixes two definitions (F210). */
function screenerReady(v: Values, columns: string[], bank: boolean): boolean {
  const need = bank ? ["total_income", "other_income"] : ["revenue", "total_expenses", "finance_cost", "depreciation"];
  return columns.length > 0 && columns.every((c) => need.every((m) => get(v, m, c) != null));
}

const CORPORATE: [string, string, Row["kind"]?, boolean?][] = [
  ["revenue", "Sales", undefined, true], ["expenses", "Expenses"], ["ebitda", "Operating profit", undefined, true],
  ["opm", "OPM %", "pct"], ["other_income", "Other income"], ["interest", "Interest"], ["depreciation", "Depreciation"],
  ["exceptional", "Exceptional items"], ["pbt", "Profit before tax"], ["tax_pct", "Tax %", "pct"],
  ["pat", "Net profit", undefined, true], ["pat_owners", "Profit to shareholders"],
];
const BANK: [string, string, Row["kind"]?, boolean?][] = [
  ["revenue", "Interest earned", undefined, true], ["interest", "Interest expended"], ["nii", "Net interest income", undefined, true],
  ["other_income", "Other income"], ["opex", "Operating expenses"], ["ppop", "Operating profit (before provisions)", undefined, true],
  ["provisions", "Provisions"], ["pbt", "Profit before tax"], ["tax_pct", "Tax %", "pct"],
  ["pat", "Net profit", undefined, true], ["gnpa", "Gross NPA %", "pct"], ["nnpa", "Net NPA %", "pct"],
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
export function quarterlyTable(metrics: Metric[], screener = false): Table {
  const bank = isBank(metrics), v = collect(metrics);
  const quarters = periodsOf(metrics, /^Q[1-4]FY\d{2}$/).slice(-QUARTERS);
  const useScreener = screener && screenerReady(v, quarters, bank);
  return table(quarters, quarters.map((q) => lines(v, q, bank, useScreener)), bank);
}

const ADDITIVE = ["revenue", "total_income", "other_income", "finance_cost", "depreciation", "exceptional_items", "pbt", "tax_expense",
  "pat", "pat_owners", "ebitda", "interest_earned", "interest_expended", "employee_cost", "other_expenses", "provisions",
  "pre_provision_operating_profit", "total_expenses", "total_income", "excise_duty", "share_associates"];

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
export function annualTable(metrics: Metric[], screener = false): Table {
  const bank = isBank(metrics), v = collect(metrics);
  const years = periodsOf(metrics, /^FY\d{2}$/).slice(-YEARS);
  const ttm = ttmQuarters(metrics);
  const useScreener = screener && screenerReady(v, years, bank);
  const cols = years.map((y) => lines(v, y, bank, useScreener));
  if (ttm) {
    for (const metric of ADDITIVE) {
      const parts = ttm.map((q) => get(v, metric, q));
      if (parts.every((x) => x != null)) (v.get(metric) ?? v.set(metric, new Map()).get(metric)!).set("TTM", parts.reduce((a, b) => a! + b!, 0)!);
    }
    v.get("ebitda_margin")?.delete("TTM");
    // a part a formula uses must be in all four quarters or none of them: else the TTM column shows no derived cell
    const partial = useScreener && ["excise_duty", "share_associates", "exceptional_items", "other_income"]
      .some((m) => { const n = ttm.filter((q) => get(v, m, q) != null).length; return n > 0 && n < 4; });
    cols.push(partial ? {} : lines(v, "TTM", bank, useScreener));
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
export function balanceTable(sheets: Snapshot[], screener = false): Table {
  const snaps = balanceSnapshots(sheets);
  const col = (f: (s: Snapshot) => Cell) => snaps.map(f);
  const debt = (s: Snapshot) => num(s, "gross_debt_cr");
  const rows: Row[] = [
    { label: "Equity capital", cells: col((s) => num(s, "equity_capital_cr")) },
    { label: "Reserves", cells: col((s) => num(s, "reserves_cr")) },
    ...(screener ? [] : [{ label: "Minority interest", cells: col((s) => num(s, "minority_interest_cr")) }]),   // so the side adds up (F-06); screener files it in Other liabilities
    { label: "Deposits", cells: col((s) => num(s, "deposits_cr")) },   // a bank's, and an NBFC's public deposits
    { label: "Borrowings", cells: col(debt) },
    // screener's plug: total less equity, reserves, borrowings and deposits, the minority inside it (mapping 1d)
    // null when equity, reserves or borrowings is missing, so a missing part is not dumped into it; deposits only a bank has
    { label: "Other liabilities", cells: col((s) => screener
      ? sub(num(s, "total_assets_cr"), [num(s, "equity_capital_cr"), num(s, "reserves_cr"), debt(s)].some((x) => x == null)
        ? null : num(s, "equity_capital_cr")! + num(s, "reserves_cr")! + debt(s)! + (num(s, "deposits_cr") ?? 0))
      : sub(sub(num(s, "total_liabilities_cr"), debt(s) ?? 0), num(s, "deposits_cr") ?? 0)) },
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


type StatementEntry = NonNullable<Dossier["statements"]>[number];

/** The table screener.in shows, from memory's statements (the exchange's files by screener's rules, statements.py), for one
 *  basis: the latest `most` periods, rows in the order the recipes give them. Empty when memory holds none. */
type RestatedFigure = NonNullable<Dossier["restated_figures"]>[number];
const RESTATED_ROWS: Record<string, string> = { Sales: "revenue", Revenue: "revenue", "Net Profit": "pat" };

/** The quarters table shows a quarter's figure as its latest filing restates it (owner, 31 Oct 2026: "as Screener does"). A cell is
 *  replaced only when it is the original the restatement was made against (within half a crore or 0.05%): the same quantity. The
 *  original stays in `Row.restated` for the marker and its tooltip. */
export function withRestated(t: Table, restated: RestatedFigure[] | undefined, basis: string | null): Table {
  if (!restated?.length || !basis) return t;
  const rows = t.rows.map((r) => {
      const metric = RESTATED_ROWS[r.label];
      if (!metric) return r;
      const marks: (Restated | null)[] = [];
      const cells = r.cells.map((c, i) => {
        const f = restated.find((x) => x.metric === metric && x.period === t.columns[i] && x.basis === basis && x.unit === "INR_CR");
        if (!f || c == null || Math.abs(c - f.original) > Math.max(0.5, 0.0005 * Math.abs(f.original))) { marks.push(null); return c; }
        marks.push({ original: c, restated_in: f.restated_in });
        return f.restated;
      });
      return marks.some(Boolean) ? { ...r, cells, restated: marks } : r;
    });
  return rows.some((r, i) => r !== t.rows[i]) ? { columns: t.columns, rows } : t;
}

export function screenerTable(entries: StatementEntry[] | undefined, basis: string | null, table: string, most: number): Table {
  const mine = (entries ?? []).filter((e) => e.table === table && (e.basis ?? null) === basis && e.rows && Object.keys(e.rows).length);
  if (!mine.length) return { columns: [], rows: [] };
  const byPeriod = new Map<string, Record<string, number>>();
  for (const e of mine) byPeriod.set(e.period, e.rows);
  const columns = [...byPeriod.keys()].sort((a, b) => periodEnd(a).localeCompare(periodEnd(b))).slice(-most);
  const names: string[] = [];
  for (const p of columns) for (const n of Object.keys(byPeriod.get(p)!)) if (!names.includes(n)) names.push(n);
  const STRONG = new Set(["Sales", "Revenue", "Operating Profit", "Financing Profit", "Net Profit", "Total Liabilities",
    "Total Assets", "Cash from Operating Activity"]);
  return {
    columns,
    rows: names.map((n) => ({ label: n, kind: n.includes("%") ? "pct" as const : undefined, strong: STRONG.has(n),
      cells: columns.map((p) => byPeriod.get(p)?.[n] ?? null) })),
  };
}

/** The bases memory's statements cover. */
export function statementBases(entries: StatementEntry[] | undefined): string[] {
  return [...new Set((entries ?? []).map((e) => e.basis ?? "").filter(Boolean))];
}

/** Screener row -> the metric name the page code reads. A lender's "Revenue" is also its interest earned (isBank). */
const STATEMENT_METRICS: [string, string][] = [["Sales", "revenue"], ["Revenue", "revenue"], ["Expenses", "total_expenses"],
  ["Operating Profit", "ebitda"], ["Financing Profit", "ebitda"], ["OPM %", "ebitda_margin"], ["Financing Margin %", "ebitda_margin"],
  ["Other Income", "other_income"], ["Interest", "finance_cost"], ["Depreciation", "depreciation"], ["Profit before tax", "pbt"],
  ["Net Profit", "pat"], ["Net Profit (owners)", "pat_owners"]];

/** The metrics the stock page's growth boxes, ratios, chart, P/E and story read, taken from memory's statements for one basis
 *  (owner, 31 Oct 2026: financial statements are one source for the whole site) from the quarters and annual tables. A company with
 *  none of them on that basis keeps `fallback`, the old metrics, so nothing goes blank. */
export function statementMetrics(entries: StatementEntry[] | undefined, basis: string | null, fallback: Metric[]): Metric[] {
  const out: Metric[] = [];
  for (const e of entries ?? []) {
    if ((e.basis ?? null) !== basis || (e.table !== "quarters" && e.table !== "annual") || !e.rows) continue;
    for (const [row, metric] of STATEMENT_METRICS) {
      const value = e.rows[row];
      if (typeof value !== "number" || !Number.isFinite(value)) continue;
      const base = { period: e.period, value, unit: metric === "ebitda_margin" ? "PCT" : "INR_CR", as_of: e.as_of ?? "", source_news_id: e.source_news_id ?? "" };
      out.push({ ...base, metric });
      if (row === "Revenue") out.push({ ...base, metric: "interest_earned" });
    }
  }
  return out.some((m) => m.metric === "revenue" || m.metric === "pat") ? out : fallback;
}

/** `statementMetrics` on the page's main basis: the one memory's metrics carry, else consolidated when its statements have it. */
export function dossierMetrics(d: Pick<Dossier, "statements" | "financial_metrics">): Metric[] {
  const bases = statementBases(d.statements);
  const basis = mainBasis(d.financial_metrics) ?? (bases.includes("CONSOLIDATED") ? "CONSOLIDATED" : bases[0] ?? null);
  return statementMetrics(d.statements, basis, d.financial_metrics);
}

/** The balance-sheet inputs of the ratios (equity = Equity Capital + Reserves, debt = Borrowings, total assets), from the "balance"
 *  statements for one basis, laid over the old snapshot of the same date so the lines statements do not hold (receivables, stock,
 *  payables) stay. Without a balance entry the old sheets are returned as they are. */
export function statementSheets(entries: StatementEntry[] | undefined, basis: string | null, sheets: Snapshot[]): Snapshot[] {
  const old = new Map(balanceSnapshots(sheets).map((s) => [periodEnd(String(s.period)).slice(0, 7), s]));
  const out = new Map(old);
  for (const e of entries ?? []) {
    if (e.table !== "balance" || (e.basis ?? null) !== basis || !e.rows) continue;
    const key = periodEnd(e.period).slice(0, 7);
    const r = e.rows, debt = r.Borrowings ?? r.Borrowing;
    const next: Snapshot = { ...(old.get(key) ?? {}), period: e.period, as_of: e.as_of ?? "", source_news_id: `xbrl:${e.source_news_id ?? ""}` };
    if (r["Equity Capital"] != null && r.Reserves != null) next.net_worth_cr = r["Equity Capital"] + r.Reserves;
    if (debt != null) next.gross_debt_cr = debt;
    if (r["Total Assets"] != null) next.total_assets_cr = r["Total Assets"];
    out.set(key, next);
  }
  return [...out.values()];
}
