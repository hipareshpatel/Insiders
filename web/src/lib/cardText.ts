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

/** `value` appears in `text` as a figure of its own ("2.1" is not inside "12.1"). Its sign, "₹" and its unit ("Cr",
 * "%", "x", "bps", "per share") are not part of the figure: "₹0.63 per share" is the table's EPS 0.63. */
export function showsFigure(text: string, value: string): boolean {
  const v = value.trim().replace(/^[+−-]\s*/, "").replace(/^₹\s*/, "")
    .replace(/\s*(?:Cr|crore|%|x|bps?|per share)\.?$/i, "").trim();
  if (!v) return false;
  return new RegExp(`(^|[^\\d.,])${v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\d]|[.,]\\d)`).test(text);
}

// A figure that says something on its own, not a count or a list number ("Stage 3", "2 units", "02 September")
const telling = (raw: string) => raw.includes(".") || Number(raw.replace(/,/g, "")) >= 10;

/** True when `text` says nothing `of` does not: its figures are all there and most of its words, or nearly every word,
 * or two or more of its figures are there in other words (Heritage's "19% YoY to ₹1,320 Cr" under its headline). */
export function repeats(text: string, of: string): boolean {
  const t = plainText(text), o = plainText(of);
  const mine = [...words(t)], theirs = words(o);
  const overlap = mine.length ? mine.filter((w) => theirs.has(w)).length / mine.length : 0;
  const nums = figures(t), known = figures(o);
  const allFigures = nums.length > 0 && nums.every((n) => near(n, known, String(n)));
  const raw = t.replace(PERIOD_WORDS, " ").match(/\d[\d,]*(?:\.\d+)?/g) ?? [];
  const shared = raw.filter((x) => telling(x) && near(Number(x.replace(/,/g, "")), known, x)).length;
  return (allFigures && overlap >= 0.4) || overlap >= 0.8 || shared >= 2;
}

/** A model's placeholder stored as a value ("to be determined via private placement", "N/A"): not a fact to show. */
const PLACEHOLDER = /\b(?:to be (?:determined|decided|finali[sz]ed|announced|identified|disclosed)|tbd|not (?:disclosed|specified|stated|available|applicable|known)|undisclosed|unknown)\b|^\s*(?:n[./]?\s?a\.?|nil|none|null|-+)?\s*$/i;
export const realValue = (text: string | null | undefined): string | null =>
  text && !PLACEHOLDER.test(text) ? text.trim() : null;

/** The filing states the value before GST ("excluding GST", "plus GST", "exclusive of taxes"). */
export const saysExGst = (text: string) =>
  /\b(?:excl(?:uding|usive of|\.)?|ex|without|plus)\s*(?:of\s+)?(?:applicable\s+)?(?:GST|taxes)\b|\+\s*GST\b|\bGST\s+(?:extra|excluded|additional)\b/i.test(text);

const RATED: [RegExp, string][] = [[/bank (?:loan )?facilit/i, "bank facilities"], [/facilit/i, "facilities"],
  [/NCD|debenture/i, "NCDs"], [/commercial paper|\bCP\b/i, "commercial paper"], [/bond/i, "bonds"], [/borrowing/i, "borrowings"],
  [/loan/i, "loans"], [/instrument/i, "instruments"], [/programme|program/i, "programme"], [/limit/i, "limits"], [/debt/i, "debt"]];

/** The amount a rating covers, as the text names it ("on ₹1,800 Cr facilities"), for the rating block's title. */
export function ratedAmount(...texts: string[]): string | null {
  for (const text of texts) {
    const m = plainText(text).match(/₹\s?(\d[\d,]*(?:\.\d+)?)\s*(lakh\s+)?(?:Cr|crore)\b([^.;]{0,40})/i);
    const noun = m && RATED.find(([re]) => re.test(m[3]));
    if (m && noun) return `₹${m[1]} ${m[2] ? "lakh " : ""}Cr ${noun[1]}`;
  }
  return null;
}

/** "36 months" or "05 years" is a term, "30 June 2027" a date (Ceigall's "Complete by 05 years", laptop re-check). */
export function executionFact(text: string): [string, string] {
  const term = text.match(/^\s*(?:within|over|for(?: a period of)?)?\s*0*(\d+(?:\.\d+)?)\s*(months?|years?)\b/i);
  return term ? ["Term", `${term[1]} ${term[2].toLowerCase()}`] : ["Complete by", text];
}

/** The verified face (owner, 2026-10-20, after two live reviews put 17 of 48 cards WRONG, nearly all in the prose): a
 * fact stays on the card when code found its quoted sentence in the filing and none of its figures is among those the
 * checks could not find. Anything else is the AI's reading and goes behind "AI reading · not verified". */
export function verifiedFact(fact: string | { text: string; quote?: string | null }, ungrounded: string[] = []): boolean {
  if (typeof fact === "string" || !fact.quote || !fact.quote.trim()) return false;
  const text = plainText(fact.text);
  return !ungrounded.some((u) => {
    const value = String(u).split("=").pop()!.trim();
    return value !== "" && showsFigure(text, value.replace(/^₹/, ""));
  });
}

type FactLike = string | { text: string; quote?: string | null };

/** The card's points: the verified facts that fit on the face, the verified rest for "More from the filing", and the
 * facts without a quote for the AI reading. A face point is never shown again below, and an unverified fact is never
 * labelled as coming from the filing. */
export function splitFacts<F extends FactLike>(unique: F[], ungrounded: string[], limit: number) {
  const verified = unique.filter((f) => verifiedFact(f, ungrounded));
  return { face: verified.slice(0, limit), more: verified.slice(limit), unverified: unique.filter((f) => !verifiedFact(f, ungrounded)) };
}

/** Key tiles whose value the headline already gives are left out (HDFC Life's VNB ₹2,037 Cr in both). */
export const tilesBesides = <K extends { value: string }>(tiles: K[], headline: string) =>
  tiles.filter((k) => !showsFigure(plainText(headline), k.value));

/** A Scale line that restates a figure of the headline (Jubilant's "35% of net worth" twice) is left out. */
export function restatesHeadline(text: string, headline: string): boolean {
  const known = figures(plainText(headline));
  const raw = plainText(text).replace(PERIOD_WORDS, " ").match(/\d[\d,]*(?:\.\d+)?/g) ?? [];
  return raw.some((x) => telling(x) && near(Number(x.replace(/,/g, "")), known, x));
}
