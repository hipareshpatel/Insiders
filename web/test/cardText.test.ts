// The card's "say each thing once" rules (src/lib/cardText.ts). Run: npm test (node --test, types stripped).
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { executionFact, figures, repeats, showsFigure } from "../src/lib/cardText.ts";

test("a point that restates the headline is a repeat", () => {
  // the owner's Punjab & Sind Bank card: headline and first point were the same figure
  assert.ok(repeats("Interest earned Q1FY27: **₹3,213.37 Cr**.", "Punjab & Sind Bank Q1FY27: interest earned ₹3,213.37 Cr"));
  assert.ok(repeats("Rating revised to CARE A- (Negative) from CARE A (Stable) on ₹1,800 Cr facilities",
    "CARE cuts Demo Finance to A- (Negative) on ₹1,800 Cr facilities"));
});

test("a point that adds a counterparty, a place or a new figure is kept", () => {
  const headline = "Demo Infra arm wins ₹228 Cr wind EPC LOI, near three-quarters of Q1 sales";
  assert.ok(!repeats("Subsidiary Demo Wind EPC received an LOI from Demo Renewables LLP for a ₹228 Cr turnkey contract", headline));
  assert.ok(!repeats("Covers an 80 MW wind project at Satara, Maharashtra", headline));
  assert.ok(!repeats("Stage 3 assets at 4.9%", "CARE cuts Demo Finance to A- (Negative) on ₹1,800 Cr facilities"));
});

test("periods and years are not figures; rounding is allowed", () => {
  assert.deepEqual(figures("Q2FY27 revenue ₹456 Cr in FY 2026-27, up 19.6% in 2026"), [456, 19.6]);
  assert.ok(repeats("Revenue ₹455.6 Cr, up 19.6% YoY", "Demo Cement Q2 revenue up 19.6% YoY to ₹455.6 Cr"));
  assert.ok(!repeats("Exports ₹141 Cr, up 35%", "Revenue ₹318 Cr, up 19%"));
});

test("empty and figure-free text is never a repeat by figures alone", () => {
  assert.ok(!repeats("", "anything"));
  assert.ok(!repeats("No volume given", ""));
});

test("a figure is shown only as a whole number", () => {
  assert.ok(showsFigure("GNPA at 2.1% this quarter", "2.1%"));
  assert.ok(!showsFigure("margin 12.1%", "2.1%"));
  assert.ok(!showsFigure("₹2,104 Cr", "2.1"));
  assert.ok(showsFigure("interest earned ₹3,213.37 Cr", "₹3,213.37 Cr"));
  assert.ok(showsFigure("D/E 0.53x", "0.53x"));
  assert.ok(!showsFigure("anything", ""));
  assert.ok(showsFigure("a (b) c", "(b") && !showsFigure("a b) c", "(b"));   // regex characters are escaped, not run
});

test("one event per company and day in the calendar", async () => {
  const { dedupeEvents } = await import("../shared/events.ts");
  const e = (scrip_code: string, event_date: string, event_type: string) => ({ scrip_code, event_date, event_type });
  const got = dedupeEvents([
    e("1", "2026-10-24", "RIGHTS_OPEN"), e("1", "2026-10-24", "MILESTONE"), e("1", "2026-10-24", "OTHER"),
    e("1", "2026-10-24", "RIGHTS_OPEN"),                    // the same event from a second filing
    e("1", "2026-10-25", "MILESTONE"),                      // alone on its day: kept
    e("2", "2026-10-24", "OTHER"),                          // another company: kept
    e("1", "2026-10-24", "RECORD_DATE"),                    // a different named event the same day: kept
    e("3", "2026-10-26", "OTHER"), e("3", "2026-10-26", "MILESTONE"),   // UCO's strike, two generic types: one
  ]);
  assert.deepEqual(got.map((x) => `${x.scrip_code} ${x.event_date} ${x.event_type}`), [
    "1 2026-10-24 RIGHTS_OPEN", "1 2026-10-25 MILESTONE", "2 2026-10-24 OTHER", "1 2026-10-24 RECORD_DATE",
    "3 2026-10-26 OTHER"]);
});

test("an execution term reads as a term, a date as a date", () => {
  assert.deepEqual(executionFact("05 years"), ["Term", "5 years"]);
  assert.deepEqual(executionFact("within 36 months"), ["Term", "36 months"]);
  assert.deepEqual(executionFact("for a period of five years"), ["Complete by", "for a period of five years"]); // words kept as written
  assert.deepEqual(executionFact("30 June 2027"), ["Complete by", "30 June 2027"]);
  assert.deepEqual(executionFact("2.5 Years"), ["Term", "2.5 years"]);
});

test("price chart: range, filings on their trading day, move", async () => {
  const { placeFilings, rangeMove, sliceRange } = await import("../src/lib/chart.ts");
  const series = { d: ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"], c: [100, 101, 99, 103, 110] };
  assert.deepEqual(sliceRange(series, "1M"), series);                     // shorter than the range: all of it
  const long = { d: Array.from({ length: 300 }, (_, i) => `d${String(i).padStart(3, "0")}`), c: Array.from({ length: 300 }, (_, i) => i + 1) };
  assert.equal(sliceRange(long, "1Y").d.length, 250);
  assert.equal(sliceRange(long, "1M").c[0], 280);
  const placed = placeFilings(series, [
    { filed_at: "2026-10-13T18:20:00+05:30", id: "a" },   // trading day itself
    { filed_at: "2026-10-11T10:00:00+05:30", id: "b" },   // before the range: left out
    { filed_at: "2026-10-14T09:00:00+05:30", id: "c" },
    { filed_at: "2026-10-14T19:00:00+05:30", id: "d" },   // same day: shares the point
    { filed_at: "2026-10-17T10:00:00+05:30", id: "e" },   // after the last close: left out
  ]);
  assert.deepEqual(placed.map((p) => [p.index, p.items.map((x) => x.id)]), [[1, ["a"]], [2, ["c", "d"]]]);
  assert.equal(Math.round(rangeMove(series)!), 10);
  assert.equal(rangeMove({ d: ["x"], c: [0] }), null);
  assert.deepEqual(placeFilings({ d: [], c: [] }, [{ filed_at: "2026-10-13" }]), []);
});
