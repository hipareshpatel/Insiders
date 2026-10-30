// When a promise is overdue (shared/promiseDue.ts): from when its period's results are due, not from the period end.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { daysPastDue, isPastDue, judgedOn } from "../shared/promiseDue.ts";
import { overdue } from "../src/components/company/companyText.ts";

test("a period deadline is judged once its results are due (45 days a quarter or half, 60 a year)", () => {
  assert.equal(judgedOn("Q2FY27", "2026-09-30"), "2026-11-14");
  assert.equal(judgedOn("Q2FY27 onwards", "2026-09-30"), "2026-11-14");
  assert.equal(judgedOn("H1FY27", "2026-09-30"), "2026-11-14");
  assert.equal(judgedOn("Q4FY27", "2027-03-31"), "2027-05-30");
  assert.equal(judgedOn("FY27", "2027-03-31"), "2027-05-30");
  assert.equal(judgedOn("FY26-FY27", "2027-03-31"), "2027-05-30");
  assert.equal(judgedOn("Q3FY27 to Q4FY27", "2027-03-31"), "2027-05-30");
});

test("a date or a month is judged on that day; no due date is never judged", () => {
  assert.equal(judgedOn("30 Sep 2026", "2026-09-30"), "2026-09-30");
  assert.equal(judgedOn("Sep-2026", "2026-09-30"), "2026-09-30");
  assert.equal(judgedOn("CY2026", "2026-12-31"), "2026-12-31");
  assert.equal(judgedOn("Q2FY27", null), null);
});

test("Q2FY27 guidance is not overdue on 30 Oct 2026, is on 15 Nov; the stored overdue_from wins", () => {
  const p = { due: "Q2FY27", due_date: "2026-09-30" };
  assert.equal(isPastDue(p, "2026-10-30"), false);
  assert.equal(daysPastDue(p, "2026-10-30"), 0);
  assert.equal(isPastDue(p, "2026-11-15"), true);
  assert.equal(daysPastDue(p, "2026-11-20"), 6);
  assert.equal(isPastDue({ ...p, overdue_from: "2026-10-01" }, "2026-10-30"), true);
  const g = { id: "g", statement: "s", source_type: "CALL", given_on: "2026-07-01", source_news_id: "n", status: "OPEN", status_history: [] };
  assert.equal(overdue([{ ...g, ...p }], "2026-10-30").length, 0);
  assert.equal(overdue([{ ...g, ...p }], "2026-11-15").length, 1);
});
