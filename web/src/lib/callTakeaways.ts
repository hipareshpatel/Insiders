/** What a call card shows under "Key takeaways from the call" (owner, 2026-10-20). The model's takeaways that code
 * verified (quote in the filing, figures in the quote or the memory cited, the earlier figure in that memory) come
 * first; when none passed, the points memory took from this filing (call_summary.py, no AI). A takeaway that failed
 * its checks goes behind the AI reading tap. No React here, so `node --test` runs callTakeaways.test.ts. */

export const CALL_CATEGORIES = ["Guidance", "Capex & capacity", "Demand & orders", "Margins & costs",
  "Balance sheet & funding", "Risks", "Other"] as const;

export interface AiCallTakeaway {
  category: string;
  text: string;
  quote?: string | null;
  memory_refs?: string[];
  versus_prior?: string | null;
  verified?: boolean;
  issue?: string | null;
}

export interface MemoryCallGroup { name: string; points: { text: string; reiterated?: boolean }[] }

export interface TakeawayGroup { name: string; points: { text: string; note?: string }[] }

export interface CallTakeawaysView {
  source: "ai" | "memory" | null;
  groups: TakeawayGroup[];
  /** the model's takeaways that failed a check: for the AI reading, never the face */
  unverified: string[];
}

export function callTakeaways(ai: AiCallTakeaway[] | null | undefined, memory: MemoryCallGroup[] | null | undefined): CallTakeawaysView {
  const items = (ai ?? []).filter((t) => t && typeof t.text === "string" && t.text.trim());
  const verified = items.filter((t) => t.verified === true);
  const unverified = items.filter((t) => t.verified !== true)
    .map((t) => (t.versus_prior ? `${t.text} (${t.versus_prior})` : t.text));
  if (verified.length) {
    const order = (name: string) => {
      const i = (CALL_CATEGORIES as readonly string[]).indexOf(name);
      return i < 0 ? CALL_CATEGORIES.length : i;
    };
    const names = [...new Set(verified.map((t) => t.category || "Other"))].sort((a, b) => order(a) - order(b));
    return {
      source: "ai",
      groups: names.map((name) => ({
        name,
        points: verified.filter((t) => (t.category || "Other") === name)
          .map((t) => ({ text: t.text, ...(t.versus_prior ? { note: t.versus_prior } : {}) })),
      })),
      unverified,
    };
  }
  const groups = (memory ?? []).filter((g) => g.points?.length)
    .map((g) => ({ name: g.name, points: g.points.map((p) => ({ text: p.text, ...(p.reiterated ? { note: "reiterated" } : {}) })) }));
  return { source: groups.length ? "memory" : null, groups, unverified };
}
