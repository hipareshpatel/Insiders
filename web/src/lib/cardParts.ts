/** The card's two parts (CARD_TWO_PARTS, F152; owner-approved TODO 21). The pipeline sorts each line by a code rule and
 *  stores the indexes in `card.parts`; this reads them. Part 1 "From the filing (checked)" is figures from the exchange's
 *  files, code calculations and quotes code found in the filing. Part 2 "Our reading (AI)" is interpretation, with a
 *  number or fact in it still checked (a failed line was hidden by the pipeline, never shown). A card without `parts`
 *  returns null and renders as before. No React here, so `node --test` runs cardParts.test.ts. */
import type { CardBody, KeyNumber, QuantifiedImpact } from "../../shared/types";

export const PART1_TITLE = "From the filing (checked)";
export const PART2_TITLE = "Our reading (AI)";

export interface PartsView {
  part1: { facts: string[]; keyNumbers: KeyNumber[]; estimates: string[]; blocks: string[] };
  part2: { lines: string[]; blocks: string[]; callTakeaways: { category: string; text: string; versus_prior?: string | null }[];
           track: boolean };
}

const plainText = (f: string | { text: string }) => (typeof f === "string" ? f : f.text).replace(/\*\*/g, "");
const pick = <T>(items: T[] | null | undefined, idx: number[] | undefined): T[] =>
  (idx ?? []).flatMap((i) => (items && i >= 0 && i < items.length ? [items[i]] : []));

function estimateLine(q: QuantifiedImpact): string {
  const result = q.result != null ? `: ${q.result}${q.unit ? ` ${q.unit.replace("INR_CR", "Cr").replace("PCT", "%")}` : ""}` : "";
  return `${q.label}${result}${q.interpretation ? ` · ${q.interpretation}` : ""}`;
}

export function partsView(card: CardBody): PartsView | null {
  const p = card.parts;
  if (!p || !p.part1 || !p.part2) return null;
  const key = (k: KeyNumber) => `${k.label}: ${k.value}${k.change ? ` (${k.change})` : ""}`;
  const change = (c: NonNullable<CardBody["notable_changes"]>[number]) =>
    `${c.metric}: ${[c.previous, c.current].filter(Boolean).join(" → ")}${c.change ? ` (${c.change})` : ""}${c.why ? ` · ${c.why}` : ""}`;
  const lines: string[] = [];
  if (p.part2.takeaway && card.takeaway) lines.push(card.takeaway);
  if (p.part2.core_catalyst && card.core_catalyst) lines.push(`Core catalyst: ${card.core_catalyst}`);
  lines.push(...pick(card.why_it_matters, p.part2.why_it_matters).map((i) => i.text));
  lines.push(...pick(card.what_happened, p.part2.what_happened).map(plainText));
  lines.push(...pick(card.key_numbers, p.part2.key_numbers).map(key));
  lines.push(...pick(card.notable_changes, p.part2.notable_changes).map(change));
  lines.push(...pick(card.quantified_impact, p.part2.quantified_impact).map(estimateLine));
  lines.push(...pick(card.missing_disclosures, p.part2.missing_disclosures).map((m) => `Not disclosed: ${m}`));
  return {
    part1: {
      facts: pick(card.what_happened, p.part1.what_happened).map(plainText),
      keyNumbers: pick(card.key_numbers, p.part1.key_numbers),
      estimates: pick(card.quantified_impact, p.part1.quantified_impact).map(estimateLine),
      blocks: p.part1.blocks ?? [],
    },
    part2: {
      lines: lines.filter((l) => l.trim()),
      blocks: p.part2.blocks ?? [],
      callTakeaways: pick(card.call_takeaways, p.part2.call_takeaways).map((t) => ({ category: t.category, text: t.text, versus_prior: t.versus_prior })),
      track: !!p.part2.track_next,
    },
  };
}
