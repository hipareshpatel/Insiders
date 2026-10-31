// The company page's screener-style statements (src/components/company/statements.ts). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { annualTable, balanceTable, cashFlowTable, formatCell, growth, quarterlyTable, ratioTable, statementDate, ttmQuarters, withRestated, statementMetrics } from "../src/components/company/statements.ts";

const m = (metric: string, period: string, value: number) => ({ metric, period, value, unit: "INR_CR", as_of: "2026-10-15", source_news_id: "xbrl:res:1:x" });
const quarter = (q: string, rev: number, pat: number) => [m("revenue", q, rev), m("pbt", q, pat * 1.3), m("finance_cost", q, 10), m("depreciation", q, 20),
  m("other_income", q, 5), m("tax_expense", q, pat * 0.3), m("pat", q, pat), m("eps", q, pat / 100)];

test("quarterly results read as screener's lines, filler and empty lines out", () => {
  const t = quarterlyTable([...quarter("Q1FY27", 1000, 100), ...quarter("Q2FY27", 1100, 120), m("raw_material_cost", "Q2FY27", 0)]);
  assert.deepEqual(t.columns, ["Q1FY27", "Q2FY27"]);
  const sales = t.rows.find((r) => r.label === "Sales")!, op = t.rows.find((r) => r.label === "Operating profit")!;
  assert.deepEqual(sales.cells, [1000, 1100]);
  assert.equal(op.cells[0], 130 + 10 + 20 - 5);                // PBT + interest + depreciation - other income
  assert.equal(t.rows.find((r) => r.label === "Expenses")!.cells[0], 1000 - 155);
  assert.equal(Math.round(t.rows.find((r) => r.label === "Tax %")!.cells[0]!), 23);
  assert.ok(!t.rows.some((r) => r.label === "Exceptional items"));
});

test("TTM is the four latest quarters, only when they are newer than the last year and consecutive", () => {
  const qs = [...quarter("Q3FY26", 900, 90), ...quarter("Q4FY26", 950, 95), ...quarter("Q1FY27", 1000, 100), ...quarter("Q2FY27", 1100, 120)];
  const year = [m("revenue", "FY26", 3600), m("pat", "FY26", 350)];
  assert.deepEqual(ttmQuarters([...qs, ...year]), ["Q3FY26", "Q4FY26", "Q1FY27", "Q2FY27"]);
  const t = annualTable([...qs, ...year]);
  assert.deepEqual(t.columns, ["FY26", "TTM"]);
  assert.equal(t.rows.find((r) => r.label === "Sales")!.cells[1], 3950);
  assert.equal(t.rows.find((r) => r.label === "Net profit")!.cells[1], 405);
  // a gap (no Q4FY26) is no TTM
  assert.equal(ttmQuarters([...qs.filter((x) => x.period !== "Q4FY26"), ...quarter("Q2FY26", 800, 80)]), null);
});

test("the balance sheet adds up, one statement a date, the filing's XBRL first", () => {
  const sheet = (period: string, as_of: string, source: string, assets: number) => ({ period, as_of, source_news_id: source,
    equity_capital_cr: 13.4, reserves_cr: 1654, net_worth_cr: 1667.4, gross_debt_cr: 10.6, total_liabilities_cr: 1724.7,
    total_assets_cr: assets, fixed_assets_cr: 306.9, cwip_cr: 0, investments_cr: 6.3, inventories_cr: 326.9, receivables_cr: 659, cash_cr: 281.7 });
  const t = balanceTable([sheet("Q2FY25", "2024-11-10", "card-1", 9999), sheet("Q2FY25", "2024-11-09", "xbrl:res:1:Q2FY25", 3392.1),
    { period: "Sep-2024", as_of: "2024-11-12", source_news_id: "card-2", cash_cr: 280 }]);
  assert.deepEqual(t.columns, ["Sep 2024"]);
  const row = (l: string) => t.rows.find((r) => r.label === l)!.cells[0]!;
  assert.equal(row("Total assets"), 3392.1);
  assert.equal(Math.round(row("Other liabilities") * 10) / 10, 1714.1);
  assert.equal(Math.round(row("Other assets") * 10) / 10, 3078.9);
  assert.ok(!t.rows.some((r) => r.label === "CWIP"));                // zero in every column
});

test("cash flows by year and the latest half year, with free cash flow", () => {
  const t = cashFlowTable([m("operating_cash_flow", "FY26", 500), m("capex", "FY26", 120), m("investing_cash_flow", "FY26", -200),
    m("operating_cash_flow", "H1FY27", 300), m("capex", "H1FY27", 50)]);
  assert.deepEqual(t.columns, ["FY26", "H1FY27"]);
  assert.deepEqual(t.rows.find((r) => r.label === "Free cash flow")!.cells, [380, 250]);
  assert.deepEqual(t.rows.find((r) => r.label === "Capex")!.cells, [-120, -50]);
});

test("ratios from the year and its March statement; growth boxes; screener's number format", () => {
  const metrics = [m("revenue", "FY26", 3650), m("pat", "FY26", 200), m("pbt", "FY26", 260), m("finance_cost", "FY26", 40)];
  const sheets = [{ period: "FY26", as_of: "2026-05-01", source_news_id: "xbrl:res:1:FY26", total_assets_cr: 5000, net_worth_cr: 1000,
    gross_debt_cr: 500, receivables_cr: 365 }];
  const t = ratioTable(metrics, sheets);
  assert.equal(t.rows.find((r) => r.label === "Debtor days")!.cells[0], 36.5);
  assert.equal(t.rows.find((r) => r.label === "ROE %")!.cells[0], 20);
  assert.equal(t.rows.find((r) => r.label === "ROCE %")!.cells[0], 20);
  assert.equal(t.rows.find((r) => r.label === "Debt to equity")!.cells[0], 0.5);
  const g = growth([m("revenue", "FY23", 1000), m("revenue", "FY24", 1100), m("revenue", "FY25", 1200), m("revenue", "FY26", 1331)], "revenue");
  assert.equal(g.find((x) => x.label === "3 years")!.value!.toFixed(1), "10.0");
  assert.equal(formatCell(123456.7), "1,23,457");
  assert.equal(formatCell(4.567), "4.57");
  assert.equal(formatCell(23.44, "pct"), "23%");
  assert.equal(formatCell(null), "");
});
test("a zero prints as 0", async () => { const { formatCell } = await import("../src/components/company/statements.ts"); assert.equal(formatCell(0), "0"); });

test("a bank reads on net interest income and pre-provision profit (HDFC Bank Q4FY25)", async () => {
  const { quarterlyTable } = await import("../src/components/company/statements.ts");
  const q = "Q4FY25";
  const t = quarterlyTable([m("interest_earned", q, 86779), m("interest_expended", q, 46986), m("other_income", q, 33489),
    m("employee_cost", q, 8810), m("other_expenses", q, 43904), m("provisions", q, 3805), m("pbt", q, 25124), m("pat", q, 18835)]);
  const row = (l: string) => t.rows.find((r) => r.label === l)!.cells[0];
  assert.equal(row("Net interest income"), 39793);
  assert.equal(row("Operating expenses"), 43904);
  assert.equal(row("Operating profit (before provisions)"), 29378);
});

test("the main figures' basis is read from their sources", async () => {
  const { mainBasis } = await import("../src/components/company/statements.ts");
  const withBasis = (b: string | null) => ({ ...m("pat", "Q2FY27", 1), sources: [{ basis: b }] });
  assert.equal(mainBasis([withBasis("STANDALONE"), withBasis("CONSOLIDATED")]), "CONSOLIDATED");
  assert.equal(mainBasis([withBasis("STANDALONE")]), "STANDALONE");
  assert.equal(mainBasis([m("pat", "Q2FY27", 1)]), null);
  // ICICIGI (audit 137, A2): one stray consolidated ratio among standalone figures is not a consolidated page
  const stray = [withBasis("STANDALONE"), { ...withBasis("STANDALONE"), metric: "revenue" }, { ...withBasis("CONSOLIDATED"), metric: "solvency_ratio" }];
  assert.equal(mainBasis(stray), "STANDALONE");
  assert.equal(mainBasis([...stray, { ...m("pat", "Q1FY27", 1), basis: "CONSOLIDATED" }, { ...m("revenue", "Q1FY27", 1), basis: "CONSOLIDATED" }]), "CONSOLIDATED");
});

test("deep audit F-01, F-04, F-05, F-07: a stray revenue row, a missing year, gaps, a missing other income", async () => {
  const { isBank, growth, quarterlyTable } = await import("../src/components/company/statements.ts");
  // SBI: interest earned every quarter, one revenue figure a card wrote
  const bank = ["Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26"].map((q) => m("interest_earned", q, 100));
  assert.ok(isBank([...bank, m("revenue", "Q4FY26", 181079)]));
  // FY24 missing: "3 years" is FY23 to FY26 (1000 -> 1331 = 10%), not the third entry back
  const g = growth([m("revenue", "FY22", 800), m("revenue", "FY23", 1000), m("revenue", "FY25", 1210), m("revenue", "FY26", 1331)], "revenue");
  assert.equal(g.find((x) => x.label === "3 years")!.value!.toFixed(1), "10.0");
  // a quarter missing in the eight: no TTM growth
  const qs = ["Q4FY25", "Q1FY26", "Q2FY26", "Q4FY26", "Q1FY27", "Q2FY27", "Q3FY27", "Q4FY27"].map((q) => m("revenue", q, 10));
  assert.equal(growth(qs, "revenue").find((x) => x.label === "TTM"), undefined);
  // no other income: operating profit not computed with it as zero
  const t = quarterlyTable([m("revenue", "Q2FY27", 100), m("pbt", "Q2FY27", 20), m("finance_cost", "Q2FY27", 2), m("depreciation", "Q2FY27", 3)]);
  assert.ok(!t.rows.some((r) => r.label === "Operating profit"));
});

test("no EPS row on the stock page, in any table, with or without a split on record (owner rule 26 Oct 2026)", () => {
  const metrics = [m("revenue", "Q1FY27", 100), m("pat", "Q1FY27", 10), m("eps", "Q1FY27", 10), m("diluted_eps", "Q1FY27", 9)];
  for (const t of [quarterlyTable(metrics), annualTable(metrics)]) assert.ok(!t.rows.some((r) => /eps|per share/i.test(r.label)));
  assert.ok(quarterlyTable(metrics).rows.some((r) => r.label === "Net profit"));
});

test("screener mode (F210) builds Sales, Expenses, Operating profit and Other income by screener's formulas; off is unchanged", () => {
  const q = [m("revenue", "Q2FY27", 1000), m("excise_duty", "Q2FY27", 50), m("total_expenses", "Q2FY27", 900), m("finance_cost", "Q2FY27", 10),
    m("depreciation", "Q2FY27", 20), m("other_income", "Q2FY27", 5), m("exceptional_items", "Q2FY27", -3), m("share_associates", "Q2FY27", 2),
    m("pbt", "Q2FY27", 100), m("tax_expense", "Q2FY27", 25), m("pat", "Q2FY27", 77)];
  const on = quarterlyTable(q, true), row = (t: ReturnType<typeof quarterlyTable>, l: string) => t.rows.find((r) => r.label === l)!.cells[0]!;
  assert.equal(row(on, "Sales"), 950);                                   // net of excise
  assert.equal(row(on, "Expenses"), 820);                                // 900 - 10 - 20 - 50 excise, as Sales
  assert.equal(row(on, "Operating profit"), 130);                      // 950 - 820 = 1000 - 900 + 30
  assert.equal(Math.round(row(on, "OPM %") * 10) / 10, 13.7);
  assert.equal(row(on, "Other income"), 4);                              // 5 - 3 + 2
  assert.equal(row(on, "Profit before tax"), 102);
  assert.ok(!on.rows.some((r) => r.label === "Exceptional items"));
  const off = quarterlyTable(q), offDefault = quarterlyTable(q, false);
  assert.deepEqual(off, offDefault);
  assert.equal(row(off, "Sales"), 1000);
});

test("screener mode: other liabilities is the plug and the minority sits inside it", () => {
  const sheet = { period: "Q4FY26", as_of: "2026-05-01", source_news_id: "xbrl:res:1:x", equity_capital_cr: 10, reserves_cr: 90, gross_debt_cr: 20,
    minority_interest_cr: 5, total_liabilities_cr: 50, total_assets_cr: 200, fixed_assets_cr: 100 };
  const t = balanceTable([sheet], true);
  assert.equal(t.rows.find((r) => r.label === "Other liabilities")!.cells[0], 80);
  assert.ok(!t.rows.some((r) => r.label === "Minority interest"));
});

test("screener mode: one table never mixes definitions, TTM needs every part in all four quarters, a missing part is no zero", () => {
  const full = (q: string) => [m("revenue", q, 1000), m("total_expenses", q, 900), m("finance_cost", q, 10), m("depreciation", q, 20), m("pbt", q, 70), m("pat", q, 50)];
  // a column lacking total expenses: the whole quarterly table keeps the usual lines
  const mixed = [...full("Q1FY27"), m("revenue", "Q2FY27", 1100), m("finance_cost", "Q2FY27", 10), m("depreciation", "Q2FY27", 20), m("pbt", "Q2FY27", 80), m("pat", "Q2FY27", 60)];
  const t = quarterlyTable(mixed, true);
  assert.deepEqual(t.rows.find((r) => r.label === "Sales")!.cells, [1000, 1100]);
  assert.ok(t.rows.some((r) => r.label === "Exceptional items") === false);
  assert.deepEqual(quarterlyTable(mixed, true), quarterlyTable(mixed, false));
  // TTM: excise in three of four quarters gives no derived TTM cell; in all four or none it does
  const qs = ["Q3FY26", "Q4FY26", "Q1FY27", "Q2FY27"];
  const year = [m("revenue", "FY26", 3600), m("total_expenses", "FY26", 3200), m("finance_cost", "FY26", 40), m("depreciation", "FY26", 80), m("pat", "FY26", 200)];
  const base = qs.flatMap(full);
  const partial = annualTable([...base, ...year, ...qs.slice(0, 3).map((q) => m("excise_duty", q, 10))], true);
  assert.equal(partial.rows.find((r) => r.label === "Sales")!.cells[1], null);
  const none = annualTable([...base, ...year], true);
  assert.equal(none.rows.find((r) => r.label === "Sales")!.cells[1], 4000);
  const all = annualTable([...base, ...year, ...qs.map((q) => m("excise_duty", q, 10))], true);
  assert.equal(all.rows.find((r) => r.label === "Sales")!.cells[1], 3960);
  // lender revenue: total income less other income; without total income the table keeps interest earned throughout
  const bankQ = (q: string, ti?: number) => [m("interest_earned", q, 500), m("interest_expended", q, 300), m("other_income", q, 50), m("pbt", q, 100), m("pat", q, 75), ...(ti ? [m("total_income", q, ti)] : [])];
  assert.equal(quarterlyTable([...bankQ("Q1FY27", 600), ...bankQ("Q2FY27", 620)], true).rows.find((r) => r.label === "Interest earned")!.cells[0], 550);
  assert.equal(quarterlyTable([...bankQ("Q1FY27", 600), ...bankQ("Q2FY27")], true).rows.find((r) => r.label === "Interest earned")!.cells[0], 500);
  // other liabilities is empty when reserves is missing
  const sheet = { period: "Q4FY26", as_of: "2026-05-01", source_news_id: "xbrl:res:1:x", equity_capital_cr: 10, gross_debt_cr: 20, total_assets_cr: 200, fixed_assets_cr: 100 };
  assert.ok(!balanceTable([sheet], true).rows.some((r) => r.label === "Other liabilities"));
});

test("screener's tables come from memory's statements, by basis, latest periods in date order", async () => {
  const { screenerTable } = await import("../src/components/company/statements.ts");
  const e = (period: string, basis: string, table: string, rows: Record<string, number>) => ({ period, basis, table, rows });
  const entries = [
    e("Q2FY27", "CONSOLIDATED", "quarters", { Sales: 44178.7, Expenses: 32000, "OPM %": 27.6, "Net Profit": 6547.4 }),
    e("Q1FY27", "CONSOLIDATED", "quarters", { Sales: 46254.8, Expenses: 34000, "OPM %": 26.5, "Net Profit": 8849.8 }),
    e("Q2FY27", "STANDALONE", "quarters", { Sales: 10, "Net Profit": 1 }),
    e("FY26", "CONSOLIDATED", "annual", { Sales: 150000 }),
  ];
  const t = screenerTable(entries, "CONSOLIDATED", "quarters", 12);
  assert.deepEqual(t.columns, ["Q1FY27", "Q2FY27"]);
  assert.deepEqual(t.rows.map((r) => r.label), ["Sales", "Expenses", "OPM %", "Net Profit"]);
  assert.equal(t.rows.find((r) => r.label === "OPM %")!.kind, "pct");
  assert.deepEqual(t.rows[0].cells, [46254.8, 44178.7]);
  assert.deepEqual(screenerTable(entries, "STANDALONE", "quarters", 12).columns, ["Q2FY27"]);
  assert.equal(screenerTable(undefined, "CONSOLIDATED", "quarters", 12).columns.length, 0);
});

test("a consolidated company's many standalone-only KPIs do not make its page Standalone", async () => {
  const { mainBasis } = await import("../src/components/company/statements.ts");
  const own = (metric: string, basis: string) => ({ ...m(metric, "Q2FY27", 1), basis });
  const metrics = [own("revenue", "CONSOLIDATED"), own("pat", "CONSOLIDATED"),
    ...["plant_utilisation", "stores", "solvency_ratio", "roe", "volume"].map((k) => own(k, "STANDALONE"))];
  assert.equal(mainBasis(metrics), "CONSOLIDATED");
  assert.equal(mainBasis([own("revenue", "STANDALONE"), own("pat", "STANDALONE"), own("roe", "CONSOLIDATED")]), "STANDALONE");
});

test("a quarter a later filing restated shows the restated figure, with the original kept for the marker", () => {
  const t = { columns: ["Q2FY26", "Q2FY27"], rows: [
    { label: "Sales", cells: [16241, 18226], strong: true }, { label: "Net Profit", cells: [2700, 2796] }, { label: "Tax %", cells: [25, 25], kind: "pct" as const }] };
  const fig = (metric: string, original: number, restated: number) => ({ metric, period: "Q2FY26", basis: "CONSOLIDATED", unit: "INR_CR", original, restated, restated_in: "Q2FY27" });
  const out = withRestated(t, [fig("revenue", 16241, 15919), fig("pat", 2500, 2400)], "CONSOLIDATED");
  assert.deepEqual(out.rows[0].cells, [15919, 18226]);
  assert.deepEqual(out.rows[0].restated, [{ original: 16241, restated_in: "Q2FY27" }, null]);
  assert.deepEqual(out.rows[1].cells, [2700, 2796]);            // the cell is not the original the restatement was made against: left alone
  assert.equal(out.rows[1].restated, undefined);
  assert.equal(withRestated(t, [fig("revenue", 16241, 15919)], "STANDALONE"), t);
  assert.equal(withRestated(t, undefined, "CONSOLIDATED"), t);
});

test("the page's figures, growth and ratios read the stored statements; no statements keeps the old metrics", async () => {
  const { statementMetrics, statementSheets, dossierMetrics } = await import("../src/components/company/statements.ts");
  const e = (table: string, period: string, rows: Record<string, number>, basis = "CONSOLIDATED") => ({ table, period, basis, rows });
  const entries = [
    e("annual", "FY24", { Sales: 100, "Profit before tax": 20, Interest: 5, "Net Profit": 15 }),
    e("annual", "FY25", { Sales: 150, "Profit before tax": 30, Interest: 5, "Net Profit": 22, "Net Profit (owners)": 20 }),
    e("quarters", "Q1FY26", { Sales: 40, "Operating Profit": 8, "OPM %": 20, "Net Profit": 5 }),
    e("balance", "FY24", { "Equity Capital": 10, Reserves: 90, Borrowings: 50, "Total Assets": 200 }),
    e("balance", "FY25", { "Equity Capital": 10, Reserves: 110, Borrowings: 60, "Total Assets": 260 }),
    e("quarters", "Q1FY26", { Sales: 1 }, "STANDALONE"),
  ];
  const m = statementMetrics(entries, "CONSOLIDATED", []);
  const at = (metric: string, period: string) => m.find((x) => x.metric === metric && x.period === period)?.value;
  assert.equal(at("revenue", "Q1FY26"), 40);
  assert.equal(at("ebitda", "Q1FY26"), 8);
  assert.equal(at("ebitda_margin", "Q1FY26"), 20);
  assert.equal(at("pat_owners", "FY25"), 20);
  assert.equal(growth(m, "revenue").length, 0);   // one year only: no 3 or 5 year rate
  const ratios = ratioTable(m, statementSheets(entries, "CONSOLIDATED", []));
  assert.equal(ratios.rows.find((r) => r.label === "Debt to equity")?.cells[1]?.toFixed(2), "0.50");
  assert.equal(ratios.rows.find((r) => r.label === "ROCE %")?.cells[1]?.toFixed(1), (35 / 180 * 100).toFixed(1));
  const old = [{ metric: "revenue", period: "Q1FY26", value: 7, unit: "INR_CR", as_of: "", source_news_id: "" }];
  assert.equal(statementMetrics([], "CONSOLIDATED", old), old);
  assert.equal(dossierMetrics({ statements: [], financial_metrics: old }), old);
  // a lender's Revenue is also its interest earned
  const bank = statementMetrics([e("quarters", "Q1FY26", { Revenue: 900, "Financing Profit": 300 })], "CONSOLIDATED", []);
  assert.equal(bank.find((x) => x.metric === "interest_earned")?.value, 900);
});

test("statement figures win for the years they cover; an older year keeps the old figure for the long growth boxes", () => {
  const old = [{ period: "FY20", metric: "revenue", value: 50, unit: "INR_CR", as_of: "", source_news_id: "" },
    { period: "FY25", metric: "revenue", value: 99, unit: "INR_CR", as_of: "", source_news_id: "" }];
  const got = statementMetrics([{ period: "FY25", basis: "CONSOLIDATED", table: "annual", rows: { Sales: 100 } }] as never, "CONSOLIDATED", old as never);
  assert.deepEqual(got.filter((m) => m.metric === "revenue").map((m) => [m.period, m.value]).sort(), [["FY20", 50], ["FY25", 100]]);
});

test("a year that ends in December is a year column, labelled by its month, and counts in the growth boxes (owner, 1 Nov 2026)", () => {
  const year = (p: string, rev: number) => [m("revenue", p, rev), m("pat", p, rev / 10), m("pbt", p, rev / 8)];
  const metrics = [...year("YE:2022-12", 1000), ...year("YE:2023-12", 1100), ...year("YE:2024-12", 1210), ...year("YE:2025-12", 1331)];
  const t = annualTable(metrics);
  assert.deepEqual(t.columns, ["YE:2022-12", "YE:2023-12", "YE:2024-12", "YE:2025-12"]);
  assert.equal(statementDate("YE:2025-12"), "Dec 2025");
  assert.equal(statementDate("YE:2024-06"), "Jun 2024");
  const three = growth(metrics, "revenue").find((g) => g.label === "3 years")!;
  assert.equal(Math.round(three.value! * 10) / 10, 10);   // 1,000 -> 1,331 over three December years
});
