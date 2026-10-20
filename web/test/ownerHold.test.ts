// The owner's hold line in a card's review block (shared/ownerHold.ts, O11). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { OWNER_HOLD, withOwnerHold } from "../shared/ownerHold.ts";

const NOTE = "Former name is another company's. 'Guidance breach' is false: H1 results not out yet";

test("a Wrong verdict on a clean card holds it with the note, and taking it back leaves the card as it was", () => {
  const card = JSON.stringify({ headline: "Jindal Stainless", review: null });
  const held = JSON.parse(withOwnerHold(card, NOTE));
  assert.deepEqual(held.review, { held: [OWNER_HOLD + NOTE], status: "HELD" });
  assert.equal(withOwnerHold(JSON.stringify(held), null), card);
});

test("a later note replaces the owner's line instead of adding one", () => {
  const first = withOwnerHold(JSON.stringify({ review: null }), "");
  assert.deepEqual(JSON.parse(first).review.held, [OWNER_HOLD + "no note yet"]);
  assert.deepEqual(JSON.parse(withOwnerHold(first, NOTE)).review.held, [OWNER_HOLD + NOTE]);
});

test("the checks' own review and hold reasons are kept through a hold and a release", () => {
  const review = { status: "UNRESOLVED", issues: ["Numbers not found"], held: ["The filing's text layer is garbled"] };
  const card = JSON.stringify({ review });
  const held = JSON.parse(withOwnerHold(card, NOTE));
  assert.deepEqual(held.review, { ...review, held: [...review.held, OWNER_HOLD + NOTE] });
  assert.deepEqual(JSON.parse(withOwnerHold(JSON.stringify(held), null)).review, review);
  // the pipeline's own HELD block (status and issues) is not taken for one the owner's hold made
  const pipelineHeld = JSON.stringify({ review: { status: "HELD", issues: ["Held after review: x"] } });
  assert.equal(withOwnerHold(withOwnerHold(pipelineHeld, NOTE), null), pipelineHeld);
});
