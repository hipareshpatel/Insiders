// The results calendar (shared/resultsCalendar.ts). Run: npm test.
import assert from "node:assert/strict";
import { test } from "node:test";
import { reportingQuarters } from "../shared/resultsCalendar.ts";

test("on 30 Oct 2026 the reporting quarter is Q2 FY27, declared 1 Oct to 31 Dec", () => {
  const [now, prev] = reportingQuarters("2026-10-30");
  assert.deepEqual({ p: now.period, from: now.from, to: now.to, current: now.current }, { p: "Q2FY27", from: "2026-10-01", to: "2026-12-31", current: true });
  assert.equal(now.label, "Q2 FY27");
  assert.equal(prev.period, "Q1FY27");
  assert.equal(prev.current, false);
  assert.equal(prev.from, "2026-07-01");
  assert.equal(prev.to, "2026-09-30");
});

test("January starts Q3; the Q2 window closes at December's end", () => {
  const [now] = reportingQuarters("2027-01-05");
  assert.equal(now.period, "Q3FY27");
  assert.equal(now.from, "2027-01-01");
  assert.equal(now.to, "2027-03-31");
  assert.equal((reportingQuarters("2026-12-31"))[0].period, "Q2FY27");
});

test("April is Q4 of the year that just ended; its window runs April to June", () => {
  const [now, before] = reportingQuarters("2026-04-10");
  assert.equal(now.period, "Q4FY26");
  assert.equal(now.from, "2026-04-01");
  assert.equal(now.to, "2026-06-30");
  assert.equal(before.period, "Q3FY26");
});

test("July opens Q1 of the next FY", () => {
  assert.equal(reportingQuarters("2026-07-01")[0].period, "Q1FY27");
});

test("five quarters, newest first, with the windows in order", () => {
  const qs = reportingQuarters("2026-10-30");
  assert.equal(qs.length, 5);
  assert.deepEqual(qs.map((q) => q.period), ["Q2FY27", "Q1FY27", "Q4FY26", "Q3FY26", "Q2FY26"]);
});
