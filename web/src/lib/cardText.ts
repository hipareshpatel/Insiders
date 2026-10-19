/** Plain-text rules the card uses to say each thing once (owner, 2026-10-19: "lots of repeated items"). No React here,
 * so `node --test` runs the cases in cardText.test.ts. */

const plainText = (text: string) => text.replace(/\*\*/g, "");

// Period labels ("Q2FY27", "Q2 FY 2026-27", "H1FY27") and years are not figures.
export const PERIOD_WORDS = /\b(?:Q[1-4]|H[12]|9M)?\s*FY\s*'?\d{2,4}(?:-\d{2})?\b|\b(?:Q[1-4]|H[12]|9M)\b|\b20\d{2}(?:-\d{2})?\b/gi;

export function figures(text: string): number[] {
  return (text.replace(PERIOD_WORDS, " ").match(/\d[\d,]*(?:\.\d+)?/g) ?? []).map((raw) => Number(raw.replace(/,/g, "")));
}

export function near(n: number, known: number[], raw = ""): boolean {
  const rounding = raw.includes(".") ? 0.051 : 0.5; // "+30%" restates 29.6%
  return known.some((k) => Math.abs(k - n) <= Math.max(rounding, Math.abs(k) * 0.006));
}

const STOP = new Set(["with", "from", "that", "this", "were", "have", "been", "which", "their", "into", "over", "under",
  "after", "before", "about", "against", "company", "limited", "crore", "lakh", "year", "quarter", "said", "will", "also"]);
export function words(text: string): Set<string> {
  return new Set((text.toLowerCase().match(/[a-z][a-z-]{3,}/g) ?? []).filter((w) => !STOP.has(w)));
}

/** `value` appears in `text` as a figure of its own ("2.1" is not inside "12.1"). */
export function showsFigure(text: string, value: string): boolean {
  const v = value.replace(/^₹|\s*Cr$|%$|x$/g, "").trim();
  if (!v) return false;
  return new RegExp(`(^|[^\\d.,])${v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\d]|[.,]\\d)`).test(text);
}

/** True when `text` says nothing `of` does not: its figures are all there and most of its words, or nearly every word. */
export function repeats(text: string, of: string): boolean {
  const t = plainText(text), o = plainText(of);
  const mine = [...words(t)], theirs = words(o);
  const overlap = mine.length ? mine.filter((w) => theirs.has(w)).length / mine.length : 0;
  const nums = figures(t), known = figures(o);
  const allFigures = nums.length > 0 && nums.every((n) => near(n, known, String(n)));
  return (allFigures && overlap >= 0.4) || overlap >= 0.8;
}
