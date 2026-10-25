// The card's two parts (src/lib/cardParts.ts, F152). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { partsView, PART1_TITLE, PART2_TITLE } from "../src/lib/cardParts.ts";

const base = {
  category_tag: "RESULTS", event_type: "RESULTS", impact_level: "HIGH", headline: "Acme Q2 profit up 12%", takeaway: "Margins held.",
  what_happened: [{ text: "**Revenue** ₹388 Cr", quote: "Revenue 388.15" }, { text: "Management sounded upbeat", quote: null }],
  why_it_matters: [{ text: "Pricing power is intact", basis: "MEMORY", memory_refs: [] }],
  missing_disclosures: ["No volume data"], key_numbers: [{ label: "PAT", value: "₹46 Cr", change: "+12% YoY" }, { label: "X", value: "1" }],
  notable_changes: [{ metric: "Margin", previous: "24%", current: "29%", change: "+5 pp", direction: "POSITIVE", why: "mix" }],
  quantified_impact: [], signals: [], timeline_entry: "", grounding: { score: 1, checked: 0, ungrounded: [] }, model: "m",
} as never;

test("titles are the owner's wording", () => {
  assert.equal(PART1_TITLE, "From the filing (checked)");
  assert.equal(PART2_TITLE, "Our reading (AI)");
});

test("an old card, with no parts block, renders as before", () => {
  assert.equal(partsView(base), null);
});

test("each line lands in the part the pipeline gave it", () => {
  const card = { ...(base as object), parts: { v: 1,
    part1: { headline: true, what_happened: [0], key_numbers: [0], blocks: ["results"] },
    part2: { takeaway: true, what_happened: [1], key_numbers: [1], why_it_matters: [0], notable_changes: [0],
             missing_disclosures: [0], blocks: ["signals"] },
    hidden: [{ field: "why_it_matters", text: "gone", why: "figure not found: 9" }] } } as never;
  const v = partsView(card)!;
  assert.deepEqual(v.part1.facts, ["Revenue ₹388 Cr"]);
  assert.deepEqual(v.part1.keyNumbers.map((k) => k.label), ["PAT"]);
  assert.deepEqual(v.part1.blocks, ["results"]);
  assert.deepEqual(v.part2.lines, ["Margins held.", "Pricing power is intact", "Management sounded upbeat", "X: 1",
    "Margin: 24% → 29% (+5 pp) · mix", "Not disclosed: No volume data"]);
  assert.ok(!JSON.stringify(v).includes("gone"));   // a hidden line is never shown
});

test("an index that points nowhere is ignored", () => {
  const card = { ...(base as object), parts: { v: 1, part1: { what_happened: [7] }, part2: { why_it_matters: [3] } } } as never;
  const v = partsView(card)!;
  assert.deepEqual(v.part1.facts, []);
  assert.deepEqual(v.part2.lines, []);
});
