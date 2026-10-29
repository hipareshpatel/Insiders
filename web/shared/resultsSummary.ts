/** The Results page's KPI counts, from the rows on screen (after the filters). A row is one declared quarter; each line is
 * the memory table's line (shared/memoryResults.ts). A line with no year-ago figure is "not comparable", not "flat".
 * No React here, so `node --test` runs the cases in test/resultsSummary.test.ts. */

import type { MemoryTable, Turn } from "./memoryResults.ts";

export type Move = "up" | "down" | "flat" | "none";

/** The direction of a line: a percentage or basis-point change, or a turn across a loss (a turn to profit is "up"). */
export function moveOf(line?: { yoy_pct?: number; yoy_bps?: number; turn?: Turn }): Move {
  if (!line) return "none";
  if (line.turn) return line.turn === "LOSS_TO_PROFIT" || line.turn === "LOSS_NARROWED" ? "up" : "down";
  const change = line.yoy_pct ?? line.yoy_bps;
  if (change === undefined) return "none";
  return change > 0 ? "up" : change < 0 ? "down" : "flat";
}

export interface ResultsSummary {
  declared: number;
  sales: Record<Move, number>;
  profit: Record<Move, number>;
  margin: Record<Move, number>;
  /** sales direction (rows) by profit direction (columns), counting only rows with both lines comparable */
  matrix: Record<"up" | "down", Record<"up" | "down", number>>;
  /** rows where the sales line or the profit line has no year-ago figure */
  notComparable: number;
}

const blank = (): Record<Move, number> => ({ up: 0, down: 0, flat: 0, none: 0 });

export function summariseResults(tables: MemoryTable[]): ResultsSummary {
  const out: ResultsSummary = {
    declared: tables.length,
    sales: blank(), profit: blank(), margin: blank(),
    matrix: { up: { up: 0, down: 0 }, down: { up: 0, down: 0 } },
    notComparable: 0,
  };
  for (const t of tables) {
    const sales = moveOf(t.sales), profit = moveOf(t.pat), margin = moveOf(t.margin ? { yoy_bps: t.margin.yoy_bps } : undefined);
    out.sales[sales]++;
    out.profit[profit]++;
    out.margin[margin]++;
    if (sales === "up" || sales === "down") {
      if (profit === "up" || profit === "down") out.matrix[sales][profit]++;
    }
    if (sales === "none" || profit === "none") out.notComparable++;
  }
  return out;
}
