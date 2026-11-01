// The Results KPI report's query building and period rules (shared/resultsKpi.ts). Run: npm test.
import { strict as assert } from "node:assert";
import { RESULTS_SORTS } from "../shared/resultsTypes.ts";
import { test } from "node:test";
import { KPI_SORTS, sortExpr, momentumSql, companyRows, kpiRowsSql, kpiSummaryRowsSql, kpiWhere, momentumClass, momentumPts, parseKpiQuery, periodsBack, prevPeriod,
  quarterDay, quarterIndex, seriesFor, toKpiRow, type DbKpiRow } from "../shared/resultsKpi.ts";

test("quarters order newest first by their number", () => {
  assert.equal(quarterIndex("Q2FY27"), 27 * 4 + 2);
  assert.ok(quarterIndex("Q1FY27")! > quarterIndex("Q4FY26")!);
  for (const bad of ["", "Q5FY27", "FY27", "Q2FY2027", null, undefined]) assert.equal(quarterIndex(bad as string), null, String(bad));
});

test("a quarter's last day: Q1 30 Jun, Q2 30 Sep, Q3 31 Dec of the year before the label, Q4 31 Mar of the label's year", () => {
  assert.equal(quarterDay("Q1FY27"), "2026-06-30");
  assert.equal(quarterDay("Q2FY27"), "2026-09-30");
  assert.equal(quarterDay("Q3FY27"), "2026-12-31");
  assert.equal(quarterDay("Q4FY27"), "2027-03-31");
  assert.equal(quarterDay("Q4FY26"), "2026-03-31");
  assert.equal(quarterDay("nonsense"), null);
});

test("the quarter before, and the eight quarters ending with one", () => {
  assert.equal(prevPeriod("Q2FY27"), "Q1FY27");
  assert.equal(prevPeriod("Q1FY27"), "Q4FY26");
  assert.equal(prevPeriod("x"), null);
  assert.deepEqual(periodsBack("Q2FY27", 3), ["Q4FY26", "Q1FY27", "Q2FY27"]);
  const eight = periodsBack("Q2FY27");
  assert.equal(eight.length, 8);
  assert.equal(eight[0], "Q3FY25");
  assert.equal(eight[7], "Q2FY27");
});

test("momentum: +2 speeds up, -2 slows, between is steady, a missing per cent is not comparable", () => {
  assert.equal(momentumClass(momentumPts(25, 23)), "speeding_up");   // exactly +2
  assert.equal(momentumClass(momentumPts(21, 23)), "slowing");        // exactly -2
  assert.equal(momentumClass(momentumPts(24.9, 23)), "steady");       // +1.9
  assert.equal(momentumClass(momentumPts(5.2, 3.2)), "speeding_up");  // 5.2 - 3.2 is 1.9999999999999996 before rounding
  assert.equal(momentumClass(momentumPts(null, 10)), "not_comparable");
  assert.equal(momentumClass(momentumPts(10, null)), "not_comparable");
  assert.equal(momentumPts(30, 10), 20);
});

test("a request keeps only what is on the lists", () => {
  const q = parseKpiQuery({ quarter: "Q2FY27", index: "NIFTY500", q: "  tata  ", sort: "pat_yoy; DROP TABLE", dir: "sideways",
    mcap_min: "5000", class: " Healthcare > Pharma ", rev_min: "20", ebitda_min: "7", pat_min: "0", opm_min: "200", momentum: "slowing",
    turnaround: "1", nfo: "1", spread: "above_20", page: "-3" });
  assert.equal(q.index, "NIFTY500");
  assert.equal(q.q, "tata");
  assert.equal(q.sort, "mcap");   // an unknown sort falls back to the default: market cap
  assert.equal(q.dir, "desc");
  assert.equal(q.mcap_min, 5000);
  assert.equal(q.class, "Healthcare > Pharma");
  assert.equal(q.rev_min, 20);
  assert.equal(q.ebitda_min, 7);
  assert.equal(q.pat_min, 0);        // 0 is a value: "growing"
  assert.equal(q.opm_min, 200);
  assert.equal(q.momentum, "slowing");
  assert.equal(q.turnaround, true);
  assert.equal(q.nfo, true);
  assert.equal(q.spread, "above_20");
  assert.equal(q.page, 1);
  assert.equal(parseKpiQuery({ quarter: "nonsense" }).quarter, null);
  assert.equal(parseKpiQuery({ page: "999999" }).page, 201);
  const bad = parseKpiQuery({ index: "NIFTY1'; --", momentum: "steady", spread: "x", mcap_min: "abc", rev_min: "1e99", class: "" });
  assert.deepEqual([bad.index, bad.momentum, bad.spread, bad.mcap_min, bad.class], [null, null, null, null, null]);
  assert.equal(bad.rev_min, 1e6);    // clamped
  assert.equal(parseKpiQuery({}).turnaround, false);
});

test("every filter becomes a bound parameter, never text in the SQL", () => {
  const q = parseKpiQuery({ quarter: "Q2FY27", index: "NIFTY500", mcap_min: "5000", class: "Health_care%", q: "100%_x", rev_min: "20", ebitda_min: "10",
    pat_min: "0", opm_min: "100", momentum: "speeding_up", turnaround: "1", nfo: "1", spread: "from_0_to_10" });
  const { from, params } = kpiWhere(q, "Q2FY27");
  assert.equal(params[0], "Q1FY27");   // the previous quarter's join
  assert.ok(params.includes("Q2FY27") && params.includes("NIFTY500") && params.includes("2026-09-30"));
  assert.ok(params.includes("%100\\%\\_x%"), "q escaped");
  assert.ok(params.includes("Health_care%") && params.includes("Health\\_care\\% > %"), "class: the path as it is, and the prefix escaped");
  for (const v of [5000, 20, 10, 0, 100, 2]) assert.ok(params.includes(v), String(v));
  assert.ok(!from.includes("100%") && !from.includes("Q2FY27") && !from.includes("NIFTY500") && !from.includes("Health"));
  assert.match(from, /k\.ebitda_turn = 'LOSS_TO_PROFIT'/);   // a loss turned to profit is growth
  assert.match(from, /\(k\.pat_yoy >= \?\d+ OR k\.pat_turn = 'LOSS_TO_PROFIT'\)/);
  assert.match(from, /co\.industry LIKE \?\d+ ESCAPE '\\'/);
  assert.match(from, /valid_from <= \?\d+ AND \(valid_to IS NULL OR valid_to > \?\d+\)/);
  assert.match(from, /k\.nfo = 1/);
  const numbered = new Set(from.match(/\?\d+/g));
  assert.equal(Math.max(...[...numbered].map((s) => Number(s.slice(1)))), params.length);   // every parameter is used, none missing
});

test("no filter, only the quarter and the joins", () => {
  const { from, params } = kpiWhere(parseKpiQuery({}), "Q2FY27");
  assert.deepEqual(params, ["Q1FY27", "Q2FY27"]);
  assert.ok(!/index_members|LIKE|revenue_yoy >=|nfo = 1/.test(from));
  assert.match(from, /LEFT JOIN filings f ON f\.news_id = k\.source_news_id/);
});

test("the sort names a listed column, puts a missing figure last and breaks ties by company", () => {
  for (const sort of Object.keys(KPI_SORTS)) {
    for (const dir of ["asc", "desc"] as const) {
      const col = sortExpr(sort as keyof typeof KPI_SORTS, dir);
      assert.ok(kpiRowsSql(parseKpiQuery({ sort, dir }), "FROM results_kpi k").includes(`ORDER BY (${col}) IS NULL, ${col} ${dir.toUpperCase()}, k.scrip_code`), sort);
    }
  }
  assert.deepEqual(Object.keys(KPI_SORTS).sort(), [...RESULTS_SORTS].sort());   // the Worker accepts exactly the shared list the page sends from
  assert.match(kpiRowsSql(parseKpiQuery({}), "FROM x"), /ORDER BY \(co\.market_cap_cr\) IS NULL, co\.market_cap_cr DESC/);   // the default: market cap, largest first
  assert.match(kpiRowsSql(parseKpiQuery({ sort: "pat_momentum" }), "FROM x"), /k\.pat_yoy > 999 OR pk\.pat_yoy > 999 THEN NULL ELSE k\.pat_yoy - pk\.pat_yoy END\) DESC/);
  assert.match(kpiRowsSql(parseKpiQuery({ page: "3" }), "FROM x"), /LIMIT 50 OFFSET 100/);
  const hand = { ...parseKpiQuery({}), sort: "1; DROP TABLE x" };   // a hand-built query still cannot name a column
  assert.ok(!kpiRowsSql(hand, "FROM x").includes("DROP"));
  assert.match(kpiSummaryRowsSql("FROM x"), /LIMIT 5000$/);
});

const db = (over: Partial<DbKpiRow>): DbKpiRow => ({
  scrip_code: "1", period: "Q2FY27", basis: "CONSOLIDATED", kind: "company", revenue: 100, revenue_yoy: 10, revenue_qoq: 1, ebitda: 20, ebitda_yoy: 12,
  ebitda_qoq: 1, ebitda_turn: null, opm: 20, opm_yoy_bps: 50, opm_qoq_bps: 10, pat: 10, pat_yoy: 25, pat_qoq: 2, pat_turn: null, pat_qoq_turn: null, nfo: 0, pat_pre: null, pat_pre_yoy: null, pat_pre_turn: null,
  symbol: "AAA", company_name: "Aaa", industry: null, market_cap_cr: 1000, size_category: "SMALL", prev_revenue_yoy: 8, prev_ebitda_yoy: 9, prev_pat_yoy: 20,
  prev_pat_turn: null, filed_at: null, filing_url: null, ...over,
});

test("a database row becomes the API row with momentum points and class", () => {
  const r = toKpiRow(db({ nfo: 1 }), { series_pat: [], series_revenue: [] });
  assert.equal(r.pat_momentum_pts, 5);
  assert.equal(r.momentum, "speeding_up");
  assert.equal(r.revenue_momentum_pts, 2);
  assert.equal(r.ebitda_momentum_pts, 3);
  assert.equal(r.pat_prev_yoy, 20);
  assert.equal(r.nfo, true);
  const turn = toKpiRow(db({ pat_yoy: null, pat_turn: "LOSS_TO_PROFIT", prev_pat_yoy: null }), { series_pat: [], series_revenue: [] });
  assert.equal(turn.momentum, "not_comparable");
  assert.equal(turn.pat_momentum_pts, null);
});

test("a series has eight quarters ending with the row's own, null where a quarter or its per cent is missing", () => {
  const by = new Map([["Q2FY27", { pat_yoy: 25, revenue_yoy: 10 }], ["Q1FY27", { pat_yoy: null, revenue_yoy: 8 }], ["Q3FY26", { pat_yoy: 5, revenue_yoy: 4 }]]);
  const s = seriesFor(by, "Q2FY27");
  assert.deepEqual(s.series_pat, [null, null, null, null, 5, null, null, 25].map((v, i) => (i === 4 ? 5 : v)).map((v, i) => (i === 5 ? null : v)));
  assert.equal(s.series_pat.length, 8);
  assert.equal(s.series_pat[7], 25);
  assert.equal(s.series_pat[6], null);          // Q1FY27 has a row but no per cent
  assert.equal(s.series_pat[4], 5);             // Q3FY26
  assert.equal(s.series_revenue[6], 8);
});

test("a company's rows: the latest eight, oldest first, last quarter's growth taken from its own rows", () => {
  const rows = periodsBack("Q2FY27", 10).map((period, i) => { const { prev_revenue_yoy: _a, prev_ebitda_yoy: _b, prev_pat_yoy: _c, prev_pat_turn: _d, ...rest } = db({ period, pat_yoy: i * 3 }); return rest; });
  const out = companyRows(rows.reverse());
  assert.equal(out.length, 8);
  assert.equal(out[0].period, "Q3FY25");
  assert.equal(out[7].period, "Q2FY27");
  assert.equal(out[7].pat_prev_yoy, 24);         // the newest of ten rows is 27, the one before 24
  assert.equal(out[7].pat_momentum_pts, 3);
  assert.equal(out[7].series_pat[6], 24);
  assert.equal(out[0].pat_prev_yoy, 3);          // Q2FY25 is dropped from the eight but still gives Q3FY25 its last quarter
});

test("momentum compares only quarters on the same basis", () => {
  assert.match(kpiWhere(parseKpiQuery({}), "Q2FY27").from, /pk\.period = \?1 AND pk\.basis = k\.basis/);
  const row = (period: string, basis: "CONSOLIDATED" | "STANDALONE", pat_yoy: number) =>
    ({ scrip_code: "1", period, basis, kind: "company", pat_yoy, revenue_yoy: 1, ebitda_yoy: 1 }) as unknown as Omit<DbKpiRow, "prev_revenue_yoy" | "prev_ebitda_yoy" | "prev_pat_yoy" | "prev_pat_turn">;
  const same = companyRows([row("Q1FY27", "CONSOLIDATED", 10), row("Q2FY27", "CONSOLIDATED", 15)]).at(-1)!;
  const switched = companyRows([row("Q1FY27", "STANDALONE", 10), row("Q2FY27", "CONSOLIDATED", 15)]).at(-1)!;
  assert.equal(same.pat_momentum_pts, 5);
  assert.equal(switched.pat_momentum_pts, null);
  assert.equal(switched.momentum, "not_comparable");
});

// ---- the growth sorts and the NM rule (R3, R4): the SQL is run for real in SQLite below ----
import { DatabaseSync } from "node:sqlite";

function rank(sort: "pat_yoy" | "ebitda_yoy" | "pat_qoq", dir: "asc" | "desc", rows: Record<string, unknown>[]): string[] {
  const sql = new DatabaseSync(":memory:");
  sql.exec("CREATE TABLE k (id TEXT, pat_yoy REAL, pat_turn TEXT, ebitda_yoy REAL, ebitda_turn TEXT, pat_qoq REAL, pat_qoq_turn TEXT)");
  const ins = sql.prepare("INSERT INTO k VALUES (?, ?, ?, ?, ?, ?, ?)");
  for (const r of rows) ins.run(r.id as string, (r.pat_yoy ?? null) as number | null, (r.pat_turn ?? null) as string | null, (r.ebitda_yoy ?? null) as number | null,
    (r.ebitda_turn ?? null) as string | null, (r.pat_qoq ?? null) as number | null, (r.pat_qoq_turn ?? null) as string | null);
  const col = sortExpr(sort, dir).replace(/\bk\./g, "");
  return sql.prepare(`SELECT id FROM k ORDER BY (${col}) IS NULL, ${col} ${dir === "asc" ? "ASC" : "DESC"}, id`).all().map((r) => r.id as string);
}
const SORT_ROWS = [
  { id: "mid", pat_yoy: 12 }, { id: "top", pat_yoy: 80 }, { id: "nm", pat_yoy: 2159 }, { id: "nm2", pat_yoy: 6643 }, { id: "fall", pat_yoy: -40 },
  { id: "p2l", pat_turn: "PROFIT_TO_LOSS" }, { id: "wide", pat_turn: "LOSS_WIDENED" }, { id: "l2p", pat_turn: "LOSS_TO_PROFIT" },
  { id: "narrow", pat_turn: "LOSS_NARROWED" }, { id: "none" },
];

test("highest first: NM rows come after every meaningful row and before rows with no figure (R3a)", () => {
  const order = rank("pat_yoy", "desc", SORT_ROWS);
  assert.deepEqual(order.slice(0, 5), ["top", "mid", "fall", "nm2", "nm"]);   // 80, 12, -40, then the NM ones (6643 before 2159)
  assert.ok(order.indexOf("nm") < order.indexOf("p2l") && order.indexOf("nm") < order.indexOf("none"));
});

test("lowest first: falls across a loss lead, then the per cents, then rows with no figure; a gain across a loss never leads (R3b)", () => {
  const order = rank("pat_yoy", "asc", SORT_ROWS);
  assert.deepEqual(order.slice(0, 5), ["p2l", "wide", "fall", "mid", "top"]);
  assert.deepEqual(order.slice(5, 7), ["nm", "nm2"]);
  assert.ok(["l2p", "narrow", "none"].every((id) => order.indexOf(id) > order.indexOf("nm2")));
  assert.deepEqual(rank("pat_qoq", "asc", [{ id: "a", pat_qoq: 5 }, { id: "b", pat_qoq_turn: "PROFIT_TO_LOSS" }, { id: "c", pat_qoq_turn: "LOSS_TO_PROFIT" }]), ["b", "a", "c"]);
  assert.deepEqual(rank("ebitda_yoy", "asc", [{ id: "a", ebitda_yoy: -5 }, { id: "b", ebitda_turn: "LOSS_WIDENED" }]), ["b", "a"]);
});

test("momentum is not comparable when either quarter's growth is NM (R4): the SQL, the points and the class agree", () => {
  assert.equal(momentumPts(2159, 13), null);
  assert.equal(momentumPts(13, 2159), null);
  assert.equal(momentumPts(999, 13), 986);   // +999% is the last meaningful figure
  assert.equal(momentumClass(momentumPts(2159, 13)), "not_comparable");
  const sql = new DatabaseSync(":memory:");
  sql.exec("CREATE TABLE k (pat_yoy REAL); CREATE TABLE pk (pat_yoy REAL)");
  const expr = (a: number, b: number) => {
    sql.exec(`DELETE FROM k; DELETE FROM pk; INSERT INTO k VALUES (${a}); INSERT INTO pk VALUES (${b})`);
    return (sql.prepare(`SELECT ${momentumSql("pat_yoy").replace(/\b(k|pk)\./g, "$1.")} AS m FROM k, pk`).get() as { m: number | null }).m;
  };
  assert.equal(expr(2159, 13), null);
  assert.equal(expr(13, 2159), null);
  assert.equal(expr(20, 13), 7);
  const row = toKpiRow(db({ pat_yoy: 2159, prev_pat_yoy: 13 }), { series_pat: [], series_revenue: [] });
  assert.deepEqual([row.pat_momentum_pts, row.momentum], [null, "not_comparable"]);
});

test("a series point on another basis than the row's is left out (R8)", () => {
  const by = new Map([["Q1FY27", { pat_yoy: 10, revenue_yoy: 5, basis: "STANDALONE" }], ["Q2FY27", { pat_yoy: 20, revenue_yoy: 6, basis: "CONSOLIDATED" }]]);
  assert.deepEqual(seriesFor(by, "Q2FY27", "CONSOLIDATED").series_pat.slice(-2), [null, 20]);
  assert.deepEqual(seriesFor(by, "Q2FY27").series_pat.slice(-2), [10, 20]);   // no basis given: as before
});
