// The Results page's words, chart shapes, CSV and URL filters (src/lib/resultsView.ts). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  activeChips, arrowOf, barHeight, bestInEight, fmtBp, fmtPct, fmtPts, groupsBullets, groupsLead, growth, growthCount, growthOf, lineLabels,
  medianSlot, momentumOf, niceTicks, notComparableText, paceSentence, quarterLabel, quarterMonths, quarterSeries, readQuery, seasonHeadline,
  seasonLines, sharedScale, sparkPath, stackWidths, toApiParams, toCsv, wasLine, type Seg,
} from "../src/lib/resultsView.ts";
import { EMPTY_SUMMARY, groupsResponse, ROWS, SUMMARY } from "./fixtures/resultsFixture.ts";

const text = (segs: Seg[]) => segs.map((s) => s.t).join("");

test("quarters read as people say them", () => {
  assert.equal(quarterLabel("Q2FY27"), "Q2 FY27");
  assert.equal(quarterMonths("Q2FY27"), "July–September 2026");
  assert.equal(quarterMonths("Q4FY26"), "January–March 2026");
  assert.equal(quarterMonths("junk"), "");
  assert.deepEqual(quarterSeries("Q2FY27"), ["Q3 FY25", "Q4 FY25", "Q1 FY26", "Q2 FY26", "Q3 FY26", "Q4 FY26", "Q1 FY27", "Q2 FY27"]);
});

test("growth has a sign, a true minus and an arrow, never colour alone", () => {
  assert.equal(fmtPct(13.94), "+13.9%");
  assert.equal(fmtPct(-5.2), "−5.2%");
  assert.equal(fmtPct(0), "0.0%");
  assert.equal(fmtPct(null), "—");
  assert.equal(fmtBp(398.6), "+399 bp");
  assert.equal(fmtBp(-145), "−145 bp");
  assert.equal(fmtPts(81.8), "+81.8 pts");
  assert.equal(arrowOf(1), "▲");
  assert.equal(arrowOf(-1), "▼");
  assert.equal(arrowOf(0), "");
  assert.deepEqual(growth(-5.2), { text: "−5.2%", tone: "down", arrow: "▼" });
  assert.deepEqual(growth(null, "LOSS_TO_PROFIT"), { text: "Loss → profit", tone: "up", arrow: "▲" });
  assert.deepEqual(growth(12, "PROFIT_TO_LOSS"), { text: "Profit → loss", tone: "down", arrow: "▼" }, "a named turn wins over a per cent");
  assert.equal(growth(null), null);
  assert.equal(wasLine("₹2,900 Cr", 17.1), "₹2,900 Cr · was +17.1%");
  assert.equal(wasLine("₹95 Cr profit", null, "LOSS_NARROWED"), "₹95 Cr profit · last qtr loss narrowed");
  assert.equal(wasLine(null, null), "");
});

test("banks, NBFCs and insurers get honest labels", () => {
  assert.deepEqual(lineLabels("bank"), { revenue: "Interest income", ebitda: null, margin: null });
  assert.deepEqual(lineLabels("nbfc"), { revenue: "Income", ebitda: "Financing profit", margin: "Financing margin" });
  assert.deepEqual(lineLabels("insurer"), { revenue: null, ebitda: null, margin: null });
});

test("momentum: +2 points speeds up, -2 slows, between is steady", () => {
  assert.equal(momentumOf(2), "speeding_up");
  assert.equal(momentumOf(-2), "slowing");
  assert.equal(momentumOf(1.9), "steady");
  assert.equal(momentumOf(null), "not_comparable");
  const kestrel = ROWS.find((r) => r.symbol === "KESTREL")!;
  assert.equal(paceSentence(kestrel), "Profit growth was +9.0% last quarter and +48.0% now: speeding up by 39.0 pts.");
  const delhivery = ROWS.find((r) => r.symbol === "DELHIVERY")!;
  assert.equal(notComparableText(delhivery), "Loss a year ago: no % to compare. Last quarter the loss narrowed.");
  assert.match(paceSentence(delhivery), /loss to profit/);
});

test("the season's headline and lines are templates over the summary", () => {
  assert.equal(text(seasonHeadline(SUMMARY)), "Of 236 companies that have reported, 175 grew profit; the middle company grew +13.9%.");
  assert.equal(text(seasonHeadline(EMPTY_SUMMARY)), "No company has reported for this quarter yet.");
  assert.equal(text(seasonHeadline({ ...SUMMARY, median_pat_yoy: null })), "Of 236 companies that have reported, 175 grew profit.");
  assert.match(text(seasonHeadline({ ...SUMMARY, n: 12 }, true)), /^Of 12 companies in this list/);
  const idx = groupsResponse("index").rows;
  const lines = seasonLines(SUMMARY, idx).map(text);
  assert.deepEqual(lines, [
    "Profit grew faster than sales: the middle company's revenue +11.8%, EBITDA +14.6%.",
    "118 are speeding up, growing profit faster than last quarter; 98 are slowing.",
    "Nifty Midcap 150 leads: its middle company grew profit +19.4%, against +12.1% in the Nifty 50.",
    "61 companies (26%) earned less than a year ago; 6 of 8 indices show their best median in 8 quarters.",
  ]);
  // without the groups, the index parts are left out, not guessed
  assert.deepEqual(seasonLines(SUMMARY).map(text).slice(2), ["61 companies (26%) earned less than a year ago."]);
  assert.deepEqual(seasonLines(EMPTY_SUMMARY), []);
});

test("groups in words", () => {
  const idx = groupsResponse("index").rows;
  assert.equal(bestInEight(idx), 6);
  assert.equal(text(groupsLead(idx, "index")), "Nifty Midcap 150 leads the season: its middle company grew profit +19.4%, the Nifty 50's +12.1%.");
  assert.equal(groupsBullets(idx, "index")[0],
    "Banks and other financials hold the Nifty 50 back: they make 38% of its profit and grew +8.4% in total, the rest +9.9%.");
  assert.equal(groupsBullets(idx, "index")[2], "In every index, total profit grew faster than total revenue.");
  assert.match(text(groupsLead([], "sector")), /No sector/);
});

test("the spread chart: bar heights, the middle company's place, band widths", () => {
  assert.equal(barHeight(85, 85, 160), 160);
  assert.equal(barHeight(1, 1000, 160), 2, "a small count stays visible");
  assert.equal(barHeight(0, 85, 160), 0);
  assert.deepEqual(medianSlot(13.9), { bin: 2, frac: 0.39000000000000006 });
  assert.deepEqual(medianSlot(20), { bin: 3, frac: 0 }, "exactly 20 counts above");
  assert.equal(medianSlot(-80)!.bin, 0);
  assert.equal(medianSlot(null), null);
  const w = stackWidths([14, 28, 38, 21]);
  assert.equal(Math.round(w.reduce((a, b) => a + b, 0)), 100);
  assert.deepEqual(stackWidths([0, 0, 0, 0]), [0, 0, 0, 0]);
});

test("sparklines share a scale and break at a missing quarter", () => {
  assert.deepEqual(sharedScale([[1.2, 5.6], [null, -3.4]]), [-4, 6]);
  assert.deepEqual(sharedScale([[5, 5]]), [4, 6]);
  assert.deepEqual(sharedScale([[]]), [0, 1]);
  assert.deepEqual(sharedScale([[5, 8]], true), [0, 8]);
  const p = sparkPath([0, 10, null, 10], 36, 16, 0, 10, 3);
  assert.equal(p.d, "M3.0 13.0 L13.0 3.0 M33.0 3.0");
  assert.deepEqual(p.last, [33, 3]);
  assert.equal(sparkPath([1, null], 36, 16, 0, 10).last, null);
  assert.deepEqual(niceTicks(0, 22.5, 6), [0, 5, 10, 15, 20]);
});

test("the URL's filters become the API's parameters; anything off the lists is dropped", () => {
  const q = readQuery(new URLSearchParams("quarter=Q2FY27&index=NIFTY500&mcap_min=5000&class=Healthcare > Pharmaceuticals&pat_min=20&momentum=speeding_up&turnaround=1&spread=above_20&sort=pat_momentum"));
  assert.equal(q.index, "NIFTY500");
  assert.equal(q.sort, "pat_momentum");
  assert.equal(q.dir, "desc");
  assert.deepEqual(toApiParams(q, 2), {
    quarter: "Q2FY27", index: "NIFTY500", mcap_min: 5000, class: "Healthcare > Pharmaceuticals", q: null, rev_min: null, ebitda_min: null,
    pat_min: 20, opm_min: null, momentum: "speeding_up", turnaround: "1", nfo: null, spread: "above_20", sort: "pat_momentum", dir: "desc", page: 2,
  });
  const bad = readQuery(new URLSearchParams("quarter=2027&index=SENSEX&mcap_min=7&pat_min=15&momentum=up&spread=x&sort=drop table&dir=sideways"));
  assert.deepEqual([bad.quarter, bad.index, bad.mcap_min, bad.pat_min, bad.momentum, bad.spread, bad.sort, bad.dir], [null, null, null, null, null, null, "pat_yoy", "desc"]);
  assert.equal(readQuery(new URLSearchParams("sort=company")).dir, "asc", "a name sorts A to Z first");
  assert.equal(growthCount(growthOf(q)), 3);
  assert.deepEqual(activeChips(q).map((c) => c.label), ["Nifty 500", "Market cap at least ₹5,000 Cr", "Pharmaceuticals", "Profit growth at least 20%",
    "Speeding up", "Turned loss to profit", "Profit growth above 20%"]);
  assert.deepEqual(activeChips(readQuery(new URLSearchParams(""))), []);
});

test("CSV export: header, every row, quoting, no formulas", () => {
  const csv = toCsv(ROWS.slice(0, 2));
  assert.ok(csv.startsWith("﻿Symbol,Company,"));
  const lines = csv.trimEnd().split("\r\n");
  assert.equal(lines.length, 3);
  assert.match(lines[2], /^IOC,Indian Oil Corporation,Energy > Refineries & Marketing,company,consolidated,Q2FY27,184000,241300,42.2,/);
  assert.match(lines[1], /,Loss → profit,/);
  const tricky = toCsv([{ ...ROWS[0], company_name: 'Say "hi", ok', industry: "=HYPERLINK()" }]);
  assert.match(tricky, /"Say ""hi"", ok"/);
  assert.match(tricky, /,'=HYPERLINK\(\),/);
  assert.equal(toCsv([]).trimEnd().split("\r\n").length, 1);
});
