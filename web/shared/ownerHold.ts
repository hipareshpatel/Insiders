// The owner's own hold on a card (O11, owner 2026-10-20): a WRONG verdict keeps the card out of the public feed and
// its note is the hold reason, kept in the card's review block beside the checks' own reasons (review.held), where
// the held banner, the audit export and the defect digest already read them. Any other verdict takes it out again.
// No imports: the Worker uses it and `npm test` runs it under node.

export const OWNER_HOLD = "Held by the owner (Wrong): ";

interface Review { status?: string; issues?: string[]; held?: string[]; [k: string]: unknown }

/** The card JSON with the owner's hold line set (a note, or "" for none) or, with null, taken out. A review block
 * this added and nothing else uses goes with it, so a released card reads as it did before the verdict. */
export function withOwnerHold(cardJson: string, note: string | null): string {
  const card = JSON.parse(cardJson) as { review?: Review | null; [k: string]: unknown };
  const review: Review = { ...(card.review ?? {}) };
  const held = (review.held ?? []).filter((h) => !h.startsWith(OWNER_HOLD));
  if (note !== null) held.push(OWNER_HOLD + (note.trim() || "no note yet"));
  if (held.length) review.held = held;
  else delete review.held;
  const added = review.status === "HELD" && !review.issues?.length && Object.keys(review).length === 1;
  if (note !== null && !card.review) review.status = "HELD";
  card.review = note === null && (added || !Object.keys(review).length) ? null : review;
  return JSON.stringify(card);
}
