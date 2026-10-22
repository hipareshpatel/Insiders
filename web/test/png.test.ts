// The share image's size (src/lib/png.ts). Run: npm test (node --test, types stripped).
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { exportRatio } from "../src/lib/png.ts";

test("a card face exports 8K wide where the canvas allows it", () => {
  const r = exportRatio(720, 1100);
  assert.equal(Math.round(720 * r), 7680);
});

test("a phone's 16.7M-pixel canvas and a tall card step it down to what the canvas takes", () => {
  const phone = exportRatio(390, 1300, 16_000_000);
  assert.ok(390 * phone * 1300 * phone <= 16_000_001 && phone > 2);
  const tall = exportRatio(720, 9000);
  assert.ok(9000 * tall <= 16384);
  assert.ok(40000 * exportRatio(720, 40000) <= 16384);
});
