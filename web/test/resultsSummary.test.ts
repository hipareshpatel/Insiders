// The Results KPI counts (shared/resultsSummary.ts). Run: npm test.
import assert from "node:assert/strict";
import { test } from "node:test";
import { moveOf, summariseResults } from "../shared/resultsSummary.ts";
import type { MemoryTable } from "../shared/memoryResults.ts";

test("a line's direction: change, turn across a loss, or nothing to compare", () => {
  assert.equal(moveOf({ value: 1, yoy_pct: 4 }), "up");
  assert.equal(moveOf({ value: 1, yoy_pct: -4 }), "down");
  assert.equal(moveOf({ value: 1, yoy_pct: 0 }), "flat");
  assert.equal(moveOf({ value: 1, turn: "LOSS_TO_PROFIT" }), "up");
  assert.equal(moveOf({ value: 1, turn: "PROFIT_TO_LOSS" }), "down");
  assert.equal(moveOf({ value: 1, turn: "LOSS_WIDENED" }), "down");
  assert.equal(moveOf({ value: 1 }), "none");
  assert.equal(moveOf({ value: 20, yoy_bps: -30 }), "down");
});

test("counts per line and a sales-by-profit matrix over the rows that can be compared", () => {
  const tables: MemoryTable[] = [
    { lens: "company", sales: { value: 110, yoy_pct: 10 }, pat: { value: 12, yoy_pct: 20 }, margin: { value: 20, yoy_bps: 50 } },
    { lens: "company", sales: { value: 110, yoy_pct: 10 }, pat: { value: 8, yoy_pct: -5 }, margin: { value: 18, yoy_bps: -20 } },
    { lens: "company", sales: { value: 90, yoy_pct: -3 }, pat: { value: 3, turn: "LOSS_TO_PROFIT" } },
    { lens: "company", sales: { value: 50 } },   // a new company: no year-ago figure
  ];
  const s = summariseResults(tables);
  assert.equal(s.declared, 4);
  assert.equal(s.sales.up, 2);
  assert.equal(s.sales.down, 1);
  assert.equal(s.sales.none, 1);
  assert.equal(s.profit.up, 2);
  assert.equal(s.profit.down, 1);
  assert.equal(s.margin.up, 1);
  assert.equal(s.margin.down, 1);
  assert.equal(s.matrix.up.up, 1);
  assert.equal(s.matrix.up.down, 1);
  assert.equal(s.matrix.down.up, 1);
  assert.equal(s.matrix.down.down, 0);
  assert.equal(s.notComparable, 1, "only the new company: its sales and profit have no year-ago figure");
});
