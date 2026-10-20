// The company page's derived figures and cleaned texts (src/components/company/companyText.ts). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  callQuarters, chartTags, cleanText, composeStory, dayChange, goodAndBad, impossible, metricLabel, nextResults, overdue, peTtm, short,
  trackTiles, yearRange,
} from "../src/components/company/companyText.ts";

const metric = (m: string, period: string, value: number) => ({ metric: m, period, value, unit: "INR_CR", as_of: "2026-10-15", source_news_id: "x" });

test("machine ids and unit codes are taken out of the text", () => {
  // Heritage's notable change and CSB's EPS signal (design audit 2026-10-20)
  assert.equal(cleanText("supports volume growth target of 7-8% (guidance g_662b6e23)"), "supports volume growth target of 7-8%");
  assert.equal(cleanText("EPS up 412% YoY to 35 INR_PER_SHARE (Q1FY27)"), "EPS up 412% YoY to ₹35 a share (Q1FY27)");
  assert.equal(cleanText('KPI check missed: "PBJL" (flagged 2026-07-27). Next'), 'KPI check missed: "PBJL". Next');
  assert.equal(metricLabel("vap_share_pct"), "VAP share");
  assert.equal(metricLabel("raw_material_cost_pct_revenue"), "Raw material cost to revenue");
});

test("a move no business makes is dropped", () => {
  assert.ok(impossible("GNPA down 72767 bps"));
  assert.ok(impossible("Inventory change up 16562% vs Q1FY27"));
  assert.ok(!impossible("EBITDA margin down 133 bps YoY; revenue up 21%"));
});

test("short text keeps the first sentence and does not stop at a title", () => {
  assert.equal(short("Approval of re-appointment of Mr. M P Vijay Kumar. Second sentence."), "Approval of re-appointment of Mr. M P Vijay Kumar");
  assert.ok(short("word ".repeat(60), 50).length <= 51);
});

test("good and bad: changes read as 'up to a from b', each metric once, impossible ones out", () => {
  const card = {
    signals: [{ type: "GUIDANCE_BREACH" as const, severity: "WARNING" as const, text: "Deadline passed: farmers. More text." }],
    notable_changes: [
      { metric: "vap_share_pct", previous: "37.9% (Q2FY26)", current: "42.5% (Q2FY27)", change: "+4.6 pp YoY", direction: "POSITIVE" as const, why: "" },
      { metric: "gnpa", previous: "1%", current: "2%", change: "-72767 bps", direction: "POSITIVE" as const, why: "" },
      { metric: "ebitda_margin", previous: "6.94% (Q2FY26)", current: "5.61% (Q2FY27)", change: "-133 bps YoY", direction: "NEGATIVE" as const, why: "" },
    ],
  };
  const { good, bad } = goodAndBad([{ source: "Q2FY27 results · 15 Oct", card }, { source: "older", card }]);
  assert.deepEqual(good, [{ text: "VAP share up to 42.5% from 37.9%", source: "Q2FY27 results · 15 Oct" }]);
  assert.deepEqual(bad.map((b) => b.text), ["EBITDA margin down to 5.61% from 6.94%", "Deadline passed: farmers"]);
});

test("P/E needs four consecutive recent quarters of profit", () => {
  const m = [metric("pat", "Q3FY26", 34.6), metric("pat", "Q4FY26", 23.94), metric("pat", "Q1FY27", 24.97), metric("pat", "Q2FY27", 30.86)];
  assert.equal(peTtm(m, 3595.84, "2026-10-20")!.pe.toFixed(1), "31.4");
  assert.equal(peTtm(m.filter((x) => x.period !== "Q4FY26"), 3595.84, "2026-10-20"), null);
  assert.equal(peTtm(m, 3595.84, "2027-12-01"), null);   // the latest quarter is too old
});

test("52-week range, tags and the day's change come from the series", () => {
  const c = Array.from({ length: 260 }, (_, i) => 100 + i);
  const d = Array.from({ length: 260 }, (_, i) => new Date(Date.UTC(2025, 0, 1 + i)).toISOString().slice(0, 10));
  assert.deepEqual(yearRange({ d, c }), { lo: 110, hi: 359 });
  assert.deepEqual(chartTags({ d, c }).map((t) => t.text), ["52-week high", "Above 200 DMA"]);
  assert.equal(yearRange({ d: d.slice(0, 100), c: c.slice(0, 100) }), null);
  // a Friday close and a Monday quote: the day's change; a quote a week later is not one
  const fri = { d: ["2026-10-15", "2026-10-16"], c: [397.65, 405.4] };
  assert.equal(dayChange(fri, 387.5, "2026-10-19")!.change.toFixed(2), "-17.90");
  assert.equal(dayChange(fri, 387.5, "2026-10-23"), null);
  assert.equal(dayChange(fri, null, null)!.change.toFixed(2), "7.75");
});

test("the next results are expected a year after the same quarter's", () => {
  const r = [{ period: "Q2FY27", filed_at: "2026-10-15T15:28:02+05:30" }, { period: "Q3FY26", filed_at: "2026-01-28T17:07:04+05:30" }];
  assert.deepEqual(nextResults(r, "2026-10-20"), { period: "Q3FY27", date: "2027-01-28" });
  assert.equal(nextResults(r.slice(0, 1), "2026-10-20"), null);
});

test("the story uses only figures in memory and the latest card", () => {
  const metrics = ["Q2FY26", "Q3FY26", "Q4FY26", "Q1FY27", "Q2FY27"].map((p, i) => metric("revenue", p, 100 + i * 10));
  const story = composeStory({ metrics, deals: [], guidance: [], money: (v) => `₹${v} Cr` })!;
  assert.equal(story, "Revenue was **₹140 Cr** in Q2FY27 (**+40%** year on year).");
  assert.equal(composeStory({ metrics: [], deals: [], guidance: [], money: String }), null);
});

test("what to track shows current items only, and overdue lists promises past due", () => {
  const w = (kind: "KPI" | "APPROVAL" | "CONCERN", text: string, check_in: string | null, created_on: string) =>
    ({ id: text, kind, text, check_in, created_on, source_news_id: "x", status: "OPEN", status_history: [] });
  const tiles = trackTiles({
    watchlist: [w("KPI", "old check", "Q1FY26 results", "2025-05-01"), w("KPI", "margin", "Q3FY27 results", "2026-10-15"), w("APPROVAL", "no date", null, "")],
    guidance: [], latestQuarter: 27 * 4 + 2, today: "2026-10-20", risks: [], date: (x) => x,
  });
  assert.equal(tiles[0].text, "margin");
  assert.equal(tiles[2].text, null);
  const g = { id: "g", statement: "2 MLPD by FY26", due: "FY26", due_date: "2026-03-31", source_type: "CONCALL", given_on: "2025-05-01", source_news_id: "x", status: "OPEN", status_history: [] };
  assert.equal(overdue([g, { ...g, status: "DELIVERED" }], "2026-10-20")[0].days, 203);
});

test("earnings-call quarters: cleaned, each point once, empty headings and quarters dropped", () => {
  const point = (text: string) => ({ text, date: "2026-08-14", news_id: "n1" });
  const got = callQuarters([
    { quarter: "Q1FY27", date: "2026-08-14", sources: [{ news_id: "n1", date: "2026-08-14" }], categories: [
      { name: "Guidance", points: [point("Volume growth 10-12% in FY27 (guidance g_662b6e23)"), point("Volume growth 10-12% in FY27")] },
      { name: "Other", points: [] },
    ] },
    { quarter: "Q4FY26", date: "2026-05-20", sources: [], categories: [{ name: "Other", points: [] }] },
  ]);
  assert.equal(got.length, 1);
  assert.deepEqual(got[0].categories.map((c) => c.name), ["Guidance"]);
  assert.deepEqual(got[0].categories[0].points.map((p) => p.text), ["Volume growth 10-12% in FY27"]);
  assert.deepEqual(callQuarters(undefined), []);
});
