// The Results table read from memory (shared/memoryResults.ts). Run: npm test.
import assert from "node:assert/strict";
import { test } from "node:test";
import { figureOf, isQuarter, memoryTable, priorYear, quarterFigure, resultRows, type MemoryRow } from "../shared/memoryResults.ts";

const row = (metric: string, period: string, ...candidates: [number, string | null][]): MemoryRow =>
  ({ metric, period, candidates: candidates.map(([value, basis]) => ({ value, basis })) });

test("consolidated is preferred; standalone only when memory holds no consolidated figure", () => {
  assert.deepEqual(figureOf([{ value: 1, basis: "STANDALONE" }, { value: 2, basis: "CONSOLIDATED" }]), { value: 2, basis: "CONSOLIDATED" });
  assert.deepEqual(figureOf([{ value: 1, basis: "STANDALONE" }]), { value: 1, basis: "STANDALONE" });
  assert.equal(figureOf([{ value: 1, basis: "CONSOLIDATED" }], "STANDALONE"), undefined);
});

test("resultRows keeps the result lines of quarters, with each source's figure as a candidate", () => {
  const rows = resultRows([
    { metric: "pat", period: "Q2FY27", value: 37.25, sources: [{ value: 37.25, basis: "STANDALONE" }, { value: 40, basis: "CONSOLIDATED" }] },
    { metric: "pat", period: "H1FY27", value: 70 },
    { metric: "eps", period: "Q2FY27", value: 1 },
  ]);
  assert.deepEqual(rows.map((r) => r.period), ["Q2FY27", "H1FY27"], "the half year is kept to work a quarter out; EPS is not");
  assert.deepEqual(rows[0].candidates.map((c) => c.basis), [null, "STANDALONE", "CONSOLIDATED"]);
});

test("the table reads a company's consolidated quarter and its year-ago on the same basis", () => {
  const rows = [
    row("revenue", "Q2FY27", [1100, "CONSOLIDATED"], [900, "STANDALONE"]),
    row("revenue", "Q2FY26", [1000, "CONSOLIDATED"]),
    row("ebitda", "Q2FY27", [220, "CONSOLIDATED"]),
    row("ebitda", "Q2FY26", [200, "CONSOLIDATED"]),
    row("pat", "Q2FY27", [110, "CONSOLIDATED"]),
    row("pat", "Q2FY26", [100, "STANDALONE"]),
  ];
  const t = memoryTable(rows, "Q2FY27");
  assert.equal(t.lens, "company");
  assert.equal(t.sales?.value, 1100);
  assert.equal(t.sales?.yoy_pct, 10);
  assert.equal(t.ebitda?.yoy_pct, 10);
  assert.equal(t.margin?.value, 20);
  assert.equal(t.margin?.yoy_bps, 0);
  assert.equal(t.pat?.yoy_pct, undefined, "no year-ago on the quarter's basis: blank, not a mixed-basis change");
});

test("a year-ago figure missing from memory leaves its change blank", () => {
  const t = memoryTable([row("revenue", "Q2FY27", [625, "STANDALONE"])], "Q2FY27");
  assert.equal(t.sales?.value, 625);
  assert.equal(t.sales?.yoy_pct, undefined);
});

test("a loss turning to profit is a turn, not a percentage on a negative base", () => {
  const t = memoryTable([row("pat", "Q2FY27", [5, "CONSOLIDATED"]), row("pat", "Q2FY26", [-20, "CONSOLIDATED"])], "Q2FY27");
  assert.equal(t.pat?.turn, "LOSS_TO_PROFIT");
  assert.equal(t.pat?.yoy_pct, undefined);
});

test("a bank's sales line is its interest earned, and insurers use gross premium", () => {
  const bank = memoryTable([row("interest_earned", "Q2FY27", [2066, "CONSOLIDATED"]), row("interest_earned", "Q2FY26", [1617.35, "CONSOLIDATED"]),
    row("revenue", "Q2FY27", [2357.51, null])], "Q2FY27");
  assert.equal(bank.lens, "bank");
  assert.equal(bank.sales?.yoy_pct, 27.7);
  const insurer = memoryTable([row("gross_premium", "Q2FY27", [900, "CONSOLIDATED"])], "Q2FY27");
  assert.equal(insurer.lens, "insurer");
  assert.equal(insurer.sales?.value, 900);
});

test("prior year of a quarter", () => {
  assert.equal(priorYear("Q2FY27"), "Q2FY26");
  assert.equal(priorYear("Q1FY10"), "Q1FY09");
  assert.equal(priorYear("H1FY27"), null);
});

test("only quarters are listed: a half year, nine months or a year is not", () => {
  assert.ok(isQuarter("Q2FY27"));
  assert.ok(!isQuarter("H1FY27"));
  assert.ok(!isQuarter("9MFY27"));
  assert.ok(!isQuarter("FY26"));
  assert.ok(!isQuarter(null));
});

test("a quarter memory does not hold is worked out from the half year less the first quarter, on the same basis", () => {
  // Coal India: the H1 filing gives H1 and Q1 EBITDA; Q2 = H1 - Q1 = 8498.58, against 6716.15 a year ago
  const rows = [
    row("ebitda", "H1FY27", [20567.09, "CONSOLIDATED"]),
    row("ebitda", "Q1FY27", [12068.51, "CONSOLIDATED"]),
    row("ebitda", "Q2FY26", [6716.15, "CONSOLIDATED"]),
    row("revenue", "Q2FY27", [44178.74, "CONSOLIDATED"]),
    row("revenue", "Q2FY26", [30186.7, "CONSOLIDATED"]),
  ];
  const t = memoryTable(rows, "Q2FY27");
  assert.equal(t.ebitda?.value, 8498.58);
  assert.equal(t.ebitda?.yoy_pct, 26.5);
  assert.equal(t.sales?.value, 44178.74);
});

test("a derived quarter never mixes bases: H1 consolidated less Q1 standalone is no quarter", () => {
  const rows = [
    row("ebitda", "H1FY27", [200, "CONSOLIDATED"]),
    row("ebitda", "Q1FY27", [90, "STANDALONE"]),
  ];
  assert.equal(quarterFigure(rows, "ebitda", "Q2FY27"), undefined);
  assert.equal(quarterFigure(rows, "ebitda", "Q2FY27", "CONSOLIDATED"), undefined);
});

test("a filed quarter is used as filed; the cumulative figures only fill a gap", () => {
  const rows = [
    row("pat", "Q3FY27", [70, "CONSOLIDATED"]),
    row("pat", "9MFY27", [300, "CONSOLIDATED"]),
    row("pat", "H1FY27", [200, "CONSOLIDATED"]),
  ];
  assert.equal(quarterFigure(rows, "pat", "Q3FY27")?.value, 70);
  const derived = [row("pat", "9MFY27", [300, "CONSOLIDATED"]), row("pat", "H1FY27", [200, "CONSOLIDATED"])];
  assert.equal(quarterFigure(derived, "pat", "Q3FY27")?.value, 100);
});
