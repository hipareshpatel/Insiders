// The paired Results table's helpers (src/lib/resultsPaired.ts). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { ebitdaSlot, fmtCrAmount, marginLine, turnPill } from "../src/lib/resultsPaired.ts";

test("amounts are crore with Indian grouping and a true minus", () => {
  assert.equal(fmtCrAmount(1576398), "15,76,398");
  assert.equal(fmtCrAmount(330601.4), "3,30,601");
  assert.equal(fmtCrAmount(73188), "73,188");
  assert.equal(fmtCrAmount(12.345), "12.35");
  assert.equal(fmtCrAmount(-1878.6), "−1,879");
  assert.equal(fmtCrAmount(null), "—");
});

test("banks and insurers have no EBITDA slot, lenders hold financing profit", () => {
  assert.equal(ebitdaSlot("bank"), "none");
  assert.equal(ebitdaSlot("insurer"), "none");
  assert.equal(ebitdaSlot("nbfc"), "financing");
  assert.equal(ebitdaSlot("company"), "figure");
  assert.equal(ebitdaSlot("reit"), "figure");
});

const base = { kind: "company" as const, opm: 17.13, opm_yoy_bps: -90, opm_qoq_bps: 40, ebitda_yoy: 23.4, ebitda_turn: null, ebitda_qoq: 5 };

test("the margin line says the margin and its bp change", () => {
  assert.equal(marginLine(base), "margin 17.1% (−90 bp)");
  assert.equal(marginLine(base, true), "margin 17.1% (+40 bp)");
  assert.equal(marginLine({ ...base, kind: "nbfc" }), "financing profit · margin 17.1% (−90 bp)");
});

test("the margin line says NM where the bp change is withheld, and nothing where there was no base", () => {
  assert.equal(marginLine({ ...base, opm_yoy_bps: null }), "margin 17.1% (NM)");
  assert.equal(marginLine({ ...base, opm_yoy_bps: null, ebitda_yoy: null }), "margin 17.1%");
  assert.equal(marginLine({ ...base, opm: 150, opm_yoy_bps: null }), "margin NM (NM)");
  assert.equal(marginLine({ ...base, kind: "bank" }), null);
  assert.equal(marginLine({ ...base, opm: null }), null);
});

test("a turn across a loss is a labelled pill, never a per cent", () => {
  assert.deepEqual(turnPill("LOSS_TO_PROFIT"), { text: "Loss → profit", tone: "up" });
  assert.deepEqual(turnPill("LOSS_NARROWED"), { text: "Loss narrowed", tone: "up" });
  assert.deepEqual(turnPill("PROFIT_TO_LOSS"), { text: "Profit → loss", tone: "down" });
  assert.deepEqual(turnPill("LOSS_WIDENED"), { text: "Loss widened", tone: "down" });
  assert.equal(turnPill(null), null);
});
