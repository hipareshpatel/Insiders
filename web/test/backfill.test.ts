// The System page's estimate of when the backfill's filing lists reach today (src/lib/backfill.ts). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { finishEstimate } from "../src/lib/backfill.ts";

test("no estimate before two mornings, or while the cursor has not moved", () => {
  assert.equal(finishEstimate(undefined, "2026-10-22"), null);
  assert.equal(finishEstimate([["2026-10-22", "2026-06-08"]], "2026-10-22"), null);
  assert.equal(finishEstimate([["2026-10-21", "2026-06-08"], ["2026-10-22", "2026-06-08"]], "2026-10-22"), null);
});

test("the history left divided by the cursor's pace", () => {
  // 20 history days in 2 days = 10 a day; 18 Jun to 21 Oct = 125 days left -> 13 days
  assert.deepEqual(finishEstimate([["2026-10-20", "2026-05-29"], ["2026-10-22", "2026-06-18"]], "2026-10-22"),
    { perDay: 10, daysLeft: 13 });
});
