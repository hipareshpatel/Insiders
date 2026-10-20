// The call card's "Key takeaways from the call" (src/lib/callTakeaways.ts). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { callTakeaways } from "../src/lib/callTakeaways.ts";

const memory = [{ name: "Guidance", points: [{ text: "Volume growth of 10-12% in FY27", reiterated: true }] }];

test("verified takeaways show by heading, in the fixed order, with what changed as a note", () => {
  const view = callTakeaways([
    { category: "Risks", text: "Pricing pressure in the East", quote: "q", verified: true },
    { category: "Guidance", text: "FY27 volume growth 12-14%", quote: "q", versus_prior: "raised from 10-12% in the Q1FY27 call", verified: true },
    { category: "Guidance", text: "Net debt ₹900 Cr", quote: "q", verified: false, issue: "900 is not in its quote" },
  ], memory);
  assert.equal(view.source, "ai");
  assert.deepEqual(view.groups.map((g) => g.name), ["Guidance", "Risks"]);
  assert.deepEqual(view.groups[0].points, [{ text: "FY27 volume growth 12-14%", note: "raised from 10-12% in the Q1FY27 call" }]);
  assert.deepEqual(view.unverified, ["Net debt ₹900 Cr"]);
});

test("no verified takeaway: the block from memory, and the failed ones for the AI reading", () => {
  const view = callTakeaways([{ category: "Guidance", text: "FY27 growth 20%", versus_prior: "up from 15%" }], memory);
  assert.equal(view.source, "memory");
  assert.deepEqual(view.groups[0].points, [{ text: "Volume growth of 10-12% in FY27", note: "reiterated" }]);
  assert.deepEqual(view.unverified, ["FY27 growth 20% (up from 15%)"]);
});

test("nothing at all: hidden", () => {
  assert.deepEqual(callTakeaways(null, null), { source: null, groups: [], unverified: [] });
  assert.equal(callTakeaways([], [{ name: "Other", points: [] }]).source, null);
});
