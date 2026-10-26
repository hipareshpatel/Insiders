// The Checks panel's and the Issues page's reading of a stored card (shared/cardChecks.ts, TODO row 67). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { cardChecks, noteText, parseCheckInput } from "../shared/cardChecks.ts";

test("a clean card has no groups and no issue types, so nothing renders for it", () => {
  const card = { grounding: { score: 1, checked: 9, ungrounded: [], unsupported_claims: [], unit_fixes: null }, review: null };
  assert.deepEqual(cardChecks(card, { held: 0, needs_review: 0 }), { groups: [], types: [] });
  assert.deepEqual(cardChecks(null, {}), { groups: [], types: [] });
});

test("corrections the code made are listed from the grounding notes, strings or objects", () => {
  const card = { grounding: {
    unit_fixes: ["count 5 million read as 0.5 million"], change_fixes: [{ text: "YoY set from XBRL" }],
    one_basis: ["results table removed: it is standalone"], quotes_dropped: ["Revenue doubled"], ungrounded: [] } };
  const out = cardChecks(card, { held: 0, needs_review: 0 });
  assert.deepEqual(out.types, ["corrected"]);
  assert.equal(out.groups.length, 1);
  assert.equal(out.groups[0].items.length, 4);
  assert.match(out.groups[0].items[1], /Change figure corrected: YoY set from XBRL/);
});

test("held, failed checks and the owner's verdict each get their own group and type", () => {
  const card = { grounding: { ungrounded: ["1,234"], unsupported_claims: ["Order is record high"], math_mismatches: 1 },
    review: { status: "UNRESOLVED", issues: ["Numbers not found in the filing: 1,234"], held: ["The filing's text layer is garbled"] } };
  const out = cardChecks(card, { held: 1, needs_review: 1 }, { verdict: "WRONG", note: "wrong quarter" });
  assert.deepEqual(out.groups.map((g) => g.key), ["held", "failed", "verdict"]);
  assert.deepEqual([...out.types].sort(), ["held", "review", "ungrounded", "unsupported", "verdict_wrong"]);
  assert.deepEqual(out.groups[0].items, ["The filing's text layer is garbled"]);
  assert.deepEqual(out.groups[2].items, ["Wrong: wrong quarter"]);
});

test("a hold made only by the owner's Wrong verdict is the verdict's, not a check's", () => {
  const card = { review: { status: "HELD", held: ["Held by the owner (Wrong): wrong quarter"] } };
  const out = cardChecks(card, { held: 1, needs_review: 0 }, { verdict: "WRONG", note: "wrong quarter" });
  assert.deepEqual(out.types, ["verdict_wrong"]);
  assert.equal(out.groups[0].key, "held");
});

test("a Right verdict shows but is not an issue; a flag with no stored reason still says so", () => {
  const right = cardChecks({}, {}, { verdict: "RIGHT", note: "" });
  assert.deepEqual(right.types, []);
  assert.deepEqual(right.groups[0].items, ["Right"]);
  const flagged = cardChecks({ grounding: {} }, { needs_review: 1 });
  assert.deepEqual(flagged.types, ["review"]);
  assert.match(flagged.groups[0].items[0], /no reason stored/);
});

test("stored notes of any shape read as one line, and bad JSON is no card", () => {
  assert.equal(noteText({ label: "Revenue", filed: 12 }), "label: Revenue; filed: 12");
  assert.equal(noteText(null), "");
  assert.equal(parseCheckInput("not json"), null);
  assert.deepEqual(parseCheckInput('{"review":null}'), { review: null });
});
