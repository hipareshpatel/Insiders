// The Results page's KPI filters, sorts and SQL (shared/resultsKpi.ts). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { KPI_SORTS, kpiRowsSql, kpiSummarySql, kpiWhere, parseKpiQuery, quarterIndex } from "../shared/resultsKpi.ts";

test("quarters order newest first by their number", () => {
  assert.equal(quarterIndex("Q2FY27"), 27 * 4 + 2);
  assert.ok(quarterIndex("Q1FY27")! > quarterIndex("Q4FY26")!);
  for (const bad of ["", "Q5FY27", "FY27", "Q2FY2027", null, undefined]) assert.equal(quarterIndex(bad as string), null, String(bad));
});

test("a request keeps only what is on the lists", () => {
  const q = parseKpiQuery({ quarter: "Q2FY27", size: "LARGE,HUGE,MID", q: "  tata  ", sort: "pat_yoy; DROP TABLE", dir: "sideways",
    rev_min: "20", ebitda_min: "7", pat_min: "0", opm_min: "200", turnaround: "1", page: "-3" });
  assert.deepEqual(q.sizes, ["LARGE", "MID"]);
  assert.equal(q.q, "tata");
  assert.equal(q.sort, "pat_yoy");   // an unknown sort falls back to PAT growth
  assert.equal(q.dir, "desc");
  assert.equal(q.revMin, 20);
  assert.equal(q.ebitdaMin, null);   // 7 is not a step
  assert.equal(q.patMin, 0);         // 0 is a step: "growing"
  assert.equal(q.opmMin, 200);
  assert.equal(q.turnaround, true);
  assert.equal(q.page, 1);
  assert.equal(parseKpiQuery({ quarter: "nonsense" }).quarter, null);
  assert.equal(parseKpiQuery({ page: "999999" }).page, 201);
});

test("every filter becomes a bound parameter, never text in the SQL", () => {
  const q = parseKpiQuery({ quarter: "Q2FY27", size: "LARGE", q: "100%_x", rev_min: "20", ebitda_min: "10", pat_min: "0", opm_min: "100", turnaround: "1" });
  const { from, params } = kpiWhere(q, "Q2FY27");
  assert.equal(params[0], "Q2FY27");
  assert.ok(params.includes('["LARGE"]') && params.includes("%100\\%\\_x%") && params.includes(20) && params.includes(10) && params.includes(0) && params.includes(100));
  assert.ok(!from.includes("100%") && !from.includes("Q2FY27"));
  assert.match(from, /k\.ebitda_turn = 'LOSS_TO_PROFIT'/);   // a loss turned to profit is growth
  assert.match(from, /k\.pat_turn = 'LOSS_TO_PROFIT'/);
  assert.equal((from.match(/\?\d+/g) ?? []).length >= params.length, true);
});

test("no filter, only the quarter", () => {
  const { from, params } = kpiWhere(parseKpiQuery({}), "Q2FY27");
  assert.deepEqual(params, ["Q2FY27"]);
  assert.ok(!/size_category|LIKE|revenue_yoy >=/.test(from));
});

test("the sort names a listed column, puts a missing figure last and breaks ties by company", () => {
  for (const sort of Object.keys(KPI_SORTS)) {
    const sql = kpiRowsSql(parseKpiQuery({ sort, dir: "asc" }), "FROM results_kpi k");
    assert.ok(sql.includes(`ORDER BY (${KPI_SORTS[sort as keyof typeof KPI_SORTS]}) IS NULL, ${KPI_SORTS[sort as keyof typeof KPI_SORTS]} ASC, k.scrip_code`), sort);
  }
  assert.match(kpiRowsSql(parseKpiQuery({ sort: "pat_yoy" }), "FROM x"), /k\.pat_key DESC/);   // growth ranks a turn across a loss beside the per cents
  assert.match(kpiRowsSql(parseKpiQuery({ page: "3" }), "FROM x"), /LIMIT 51 OFFSET 100/);
});

test("the summary counts a loss turned to profit as growth", () => {
  const sql = kpiSummarySql("FROM results_kpi k");
  assert.match(sql, /sum\(k\.pat_yoy > 0 OR k\.pat_turn = 'LOSS_TO_PROFIT'\)/);
  assert.match(sql, /count\(\*\) AS n/);
});
