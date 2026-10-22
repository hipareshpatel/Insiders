// NSE sessions on the site (src/lib/format.ts marketSession). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { marketSession } from "../src/lib/format.ts";

test("an exchange holiday is a non-trading day (data chain audit B4)", () => {
  assert.equal(marketSession("2026-10-20T11:00:00+05:30"), "Non-trading day");   // Dussehra, a Tuesday
  assert.equal(marketSession("2026-10-21T11:00:00+05:30"), "Market hours");
  assert.equal(marketSession("2026-10-24T11:00:00+05:30"), "Non-trading day");   // a Saturday
  assert.equal(marketSession("2026-10-21T08:00:00+05:30"), "Pre-market");
});
