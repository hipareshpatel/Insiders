// The company keys the routes accept (shared/companyKey.ts). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { isCompanyKey } from "../shared/companyKey.ts";

test("company keys: a scrip code, an NSE symbol, or the pipeline's NSE: key", () => {
  for (const key of ["500325", "TATATECH", "M&M", "BAJAJ-AUTO", "NSE:TATATECH", "NSE:M&M"]) assert.ok(isCompanyKey(key), key);
  for (const key of ["", "nse:tcs", "NSE:", "BSE:TCS", "-TCS", "TCS;DROP", "NSE:NSE:TCS", undefined]) assert.ok(!isCompanyKey(key), String(key));
});
