// The company page's screener-style statements (src/components/company/statements.ts). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { annualTable, balanceTable, cashFlowTable, formatCell, growth, quarterlyTable, ratioTable, ttmQuarters } from "../src/components/company/statements.ts";

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
    { period: "Sep-2024", as_of: "2024-11-12", source_news_id: "card-2", cash_cr: 280 }], false);
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
