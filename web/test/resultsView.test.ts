// The Results page's words, chart shapes, CSV and URL filters (src/lib/resultsView.ts). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  activeChips, arrowOf, barHeight, bestInEight, coverageOf, fmtBp, fmtPct, fmtPts, groupsBullets, groupsLead, growth, growthCount, growthOf, lineLabels,
  medianSlot, momentumOf, niceTicks, notComparableText, paceSentence, quarterLabel, quarterMonths, quarterSeries, readQuery, seasonHeadline,
  KIND_TAG, nmLines, spreadHeading, tilesIntro, blankNote, medianNote, wellCovered, fmtGrowth, fmtMargin, isNmPct, seasonLines, sharedScale, sparkPath, stackWidths, toApiParams, toCsv, wasLine, oneOff, wholeProfit, type Seg,
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
  assert.deepEqual(lineLabels("bank"), { revenue: "Interest income", ebitda: "Financing profit", margin: "Financing margin" });   // Screener's rows (31 Oct 2026)
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
  assert.match(paceSentence(delhivery), /loss → profit/);
});

test("the season's headline and lines are templates over the summary", () => {
  assert.equal(text(seasonHeadline(SUMMARY)), "Of 236 companies that have reported, 175 grew profit; median profit growth +13.9%.");
  assert.equal(text(seasonHeadline(EMPTY_SUMMARY)), "No company has reported for this quarter yet.");
  // a company with no year-ago quarter is reported but not in the base of "grew" (C1)
  assert.equal(text(seasonHeadline({ ...SUMMARY, n: 611, pat_n: 611, pat_of: 553, pat_up: 401 })),
    "Of 553 companies with a year-ago quarter to compare (611 reported), 401 grew profit; median profit growth +13.9%.");
  assert.match(text(seasonHeadline({ ...SUMMARY, n: 1772, pat_n: 1772, pat_of: 1500, pat_up: 1127 })), /^Of 1,500 companies with a year-ago quarter to compare \(1,772 reported\), 1,127 grew/);
  assert.equal(text(seasonHeadline({ ...SUMMARY, median_pat_yoy: null })), "Of 236 companies that have reported, 175 grew profit.");
  assert.match(text(seasonHeadline({ ...SUMMARY, n: 12 }, true)), /^Of 12 companies in this list/);
  const idx = groupsResponse("index").rows;
  const lines = seasonLines(SUMMARY, idx).map(text);
  assert.deepEqual(lines, [
    "Profit grew faster than sales: median revenue growth +11.8%, EBITDA +14.6%.",
    "118 are speeding up, growing profit faster than last quarter; 98 are slowing.",
    "Nifty Midcap 150 leads: its median profit growth is +19.4% (130 of 149 reported), against +12.1% in the Nifty 50 (41 of 50 reported).",
    "61 companies (26% of those with a year-ago quarter) earned less than a year ago; 7 of 7 indices (with at least 80% of members reported) show their best median in 8 quarters.",
  ]);
  // without the groups, the index parts are left out, not guessed
  assert.deepEqual(seasonLines(SUMMARY).map(text).slice(2), ["61 companies (26% of those with a year-ago quarter) earned less than a year ago."]);
  assert.deepEqual(seasonLines(EMPTY_SUMMARY), []);
});

test("groups in words", () => {
  const idx = groupsResponse("index").rows;
  assert.equal(bestInEight(idx), 7);   // Nifty Next 50 (22 of 50 reported) is not counted; the other 7 are all at their 8-quarter high
  // an index with under 80% of its members reported is not compared with full seasons (measured 31 Oct 2026: Midcap 150 on 80 of 150)
  const mid = idx.find((r) => r.id === "MIDCAP150")!;
  assert.equal(bestInEight([mid]), 1);
  assert.equal(bestInEight([{ ...mid, reported: 80, of: 150 }]), 0);
  assert.deepEqual(wellCovered([mid, { ...mid, reported: 80, of: 150 }, { ...mid, reported: 5, of: null }]).length, 2);   // no member list: kept
  assert.equal(coverageOf({ reported: 32, of: 50 }), " (32 of 50 reported)");
  assert.equal(coverageOf({ reported: 32, of: null }), "");
  assert.equal(medianNote({ median_pat_n: 511, pat_turn_n: 51 }),
    "Median of 511 companies with a % change; 51 whose profit crossed zero (loss to profit, profit to loss, loss narrowed or widened) are not in the median but are in the counts.");
  // revenue totals compare ex-financials only: a bank's revenue is interest earned (C5)
  assert.match(groupsBullets(idx, "index").join("|"), /companies other than financials/);
  assert.equal(text(groupsLead(idx, "index")), "Nifty Midcap 150 leads the season: its median profit growth is +19.4%, the Nifty 50's +12.1%.");
  assert.equal(groupsBullets(idx, "index")[0],
    "Banks and other financials hold the Nifty 50 back: they make 38% of its profit and grew +8.4% in total, the rest +9.9%.");
  assert.equal(groupsBullets(idx, "index")[2], "In every index, total profit grew faster than total revenue (companies other than financials).");
  assert.match(text(groupsLead([], "sector")), /No sector/);
});

test("the spread chart: bar heights, the middle company's place, band widths", () => {
  assert.equal(barHeight(85, 85, 160), 160);
  assert.equal(barHeight(1, 1000, 160), 2, "a small count stays visible");
  assert.equal(barHeight(0, 85, 160), 0);
  const slot = medianSlot(13.9);
  assert.equal(slot.bin, 2);
  assert.ok(Math.abs(slot.frac - 0.39) < 1e-9);
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
  assert.deepEqual([bad.quarter, bad.index, bad.mcap_min, bad.pat_min, bad.momentum, bad.spread, bad.sort, bad.dir], [null, null, null, null, null, null, "mcap", "desc"]);
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

test("every avatar colour keeps its white initials at 4.5:1 or better", async () => {
  const { readFileSync } = await import("node:fs");
  const src = readFileSync(new URL("../src/components/Avatar.tsx", import.meta.url), "utf8");
  const colours = src.match(/const PALETTE = \[([^\]]+)\]/)![1].match(/#[0-9a-f]{6}/gi)!;
  const lum = (h: string) => { const [r, g, b] = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  assert.equal(colours.length, 10);
  for (const c of colours) assert.ok(1.05 / (lum(c) + 0.05) >= 4.5, c);
});

test("each view ranks by its own column until a column is picked", async () => {
  const { VIEW_SORT, SORTS, DEFAULT_SORT } = await import("../src/lib/resultsView.ts");
  assert.deepEqual(VIEW_SORT, { yoy: "mcap", momentum: "pat_momentum", qoq: "pat_qoq" });
  for (const s of Object.values(VIEW_SORT)) assert.ok((SORTS as readonly string[]).includes(s), s);
  assert.equal(VIEW_SORT.yoy, DEFAULT_SORT);
});

test("a link that names only a view ranks by that view's own column; a picked column wins", () => {
  assert.equal(readQuery(new URLSearchParams("")).sort, "mcap");   // market cap, largest first (R3c)
  assert.equal(readQuery(new URLSearchParams("sort=pat_yoy")).sort, "pat_yoy");   // every other sort stays one param away
  assert.equal(readQuery(new URLSearchParams("view=momentum")).sort, "pat_momentum");
  assert.equal(readQuery(new URLSearchParams("view=qoq")).sort, "pat_qoq");
  assert.equal(readQuery(new URLSearchParams("view=qoq&sort=mcap")).sort, "mcap");
  assert.equal(readQuery(new URLSearchParams("view=nonsense")).sort, "mcap");
});

test("a trust is tagged REIT or InvIT and shows revenue, EBITDA and margin like a company", () => {
  assert.equal(KIND_TAG.reit, "REIT");
  assert.equal(KIND_TAG.invit, "InvIT");
  for (const kind of ["reit", "invit"] as const) assert.deepEqual(lineLabels(kind), { revenue: "Revenue", ebitda: "EBITDA", margin: "EBITDA margin" });
});

test("NM: a change above +999% and a margin outside -100..+100% are not meaningful; the exact figure goes in the title (C6)", () => {
  assert.equal(fmtGrowth(6643.4), "NM");
  assert.equal(fmtGrowth(999), "+999.0%");
  assert.equal(fmtGrowth(-100), "−100.0%");
  assert.equal(isNmPct(null), false);
  assert.equal(fmtMargin(-628.89), "NM");
  assert.equal(fmtMargin(17.92), "17.9%");
  const g = growth(6643.4)!;
  assert.deepEqual([g.text, g.title], ["NM", "Not meaningful: +6643.4% (a change above +999%)"]);
  assert.equal(growth(12, null, "bp")!.title, "100 bp = 1 percentage point");
  assert.equal(wasLine("₹10 Cr", 2159), "₹10 Cr · was NM");
  // the CSV keeps the real numbers and names the NM lines in one column (U3)
  const csv = toCsv([{ ...ROWS[0], pat_yoy: 2159, opm: -628.89 }]).split("\r\n")[1];
  assert.ok(csv.includes(",2159,") && csv.includes("-628.89") && !csv.includes(",NM,"));
  assert.deepEqual(nmLines({ ...ROWS[0], pat_yoy: 2159, revenue_qoq: 1200, revenue_yoy: 999 }), ["Revenue QoQ", "PAT YoY"]);
  assert.match(csv, /PAT YoY,/);
  assert.ok(toCsv([]).includes("Growth NM (over +999%)"));
});

test("CSV headers say what a column is (U14)", () => {
  const head = toCsv([]).trimEnd();
  for (const h of ["EBITDA margin %", "Kind (company/bank/nbfc/insurer/reit/invit)", "PAT growth change vs last quarter (pts)"]) assert.ok(head.includes(h), h);
  assert.ok(!head.includes("PAT momentum"));
});

test("the profit before one-offs shows only when the exceptional item is at least 10% of PAT (F1)", () => {
  const live = { pat: 412, pat_pre: 112, pat_pre_yoy: 514, pat_pre_turn: null };   // CGPOWER-like: an exceptional gain of 300 after tax
  assert.equal(oneOff(live)?.text, "Before one-offs ₹112 Cr · +514.0%");
  assert.equal(oneOff(live)?.title, "Profit after tax excluding exceptional items, after their tax");
  assert.equal(oneOff({ pat: 100, pat_pre: 95, pat_pre_yoy: 5, pat_pre_turn: null }), null);   // 5% of PAT: not shown
  assert.ok(oneOff({ pat: 100, pat_pre: 90, pat_pre_yoy: 5, pat_pre_turn: null }));            // exactly 10%: shown
  assert.equal(oneOff({ pat: 100, pat_pre: null, pat_pre_yoy: null, pat_pre_turn: null }), null);
  assert.equal(oneOff({ pat: 858.5, pat_pre: 158.5, pat_pre_yoy: null, pat_pre_turn: "LOSS_TO_PROFIT" })?.text, "Before one-offs ₹159 Cr · loss → profit");
  const csv = toCsv([{ ...ROWS[0], pat_pre: 112, pat_pre_yoy: 514 }]);
  assert.ok(csv.includes("PAT before exceptional items (Rs Cr),PAT before exceptional items YoY %"));
  assert.match(csv.split("\r\n")[1], /,112,514,/);
});

test("the spread chart's header gives its base, and one sentence above the tiles says who can be compared (R5, U5)", () => {
  // live Q2FY27: 611 reported, 558 with a year-ago quarter, 515 in the bars, 29 loss to profit, 14 loss narrowed
  const s = { n: 611, pat_of: 558, spread: { below_0: 138, from_0_to_10: 54, from_10_to_20: 50, above_20: 273, loss_to_profit: 29, loss_narrowed: 14, with_pct: 515 } };
  assert.equal(spreadHeading(s), "558 with a year-ago quarter: 515 in the bars, 29 loss to profit, 14 loss narrowed");
  assert.equal(515 + 29 + 14, 558);
  assert.equal(tilesIntro(s), "611 companies have reported; 558 can be compared with the same quarter last year.");
  assert.equal(tilesIntro({ n: 1, pat_of: 1 }), "1 company has reported; 1 can be compared with the same quarter last year.");
});

test("an empty cell says why: insurers show no revenue by design (U4)", () => {
  assert.equal(blankNote("insurer", "revenue"), "Not shown for insurers");
  assert.equal(blankNote("bank", "ebitda"), "");   // a bank has a financing profit now
});

test("the whole profit (minority share included) shows beside the owners' PAT only when the row has one (owner, 31 Oct 2026)", () => {
  assert.equal(wholeProfit({ pat: 325.71, pat_total: 427, pat_total_yoy: 11.2, pat_total_turn: null })?.text, "Whole profit ₹427 Cr · +11.2%");
  assert.equal(wholeProfit({ pat: 100, pat_total: null, pat_total_yoy: null, pat_total_turn: null }), null);
});
