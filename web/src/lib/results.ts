/** Results-table rules shared by the Results page, the company page and the card's table. No React here, so
 * `node --test` runs the cases in cardText.test.ts. */

export const TURN: Record<string, [string, string]> = {
  LOSS_TO_PROFIT: ["Loss to profit", "text-pos"], PROFIT_TO_LOSS: ["Profit to loss", "text-neg"],
  LOSS_NARROWED: ["Loss narrowed", "text-pos"], LOSS_WIDENED: ["Loss widened", "text-neg"],
};

type TurnLine = { value?: number; prev_year?: number; prev_quarter?: number; yoy_turn?: string; qoq_turn?: string };

/** A change across a loss, in words: a % of a negative base means nothing (Prism Johnson's PAT "+2127%", T11). Cards
 *  stored before the pipeline named it carry the two values, so the turn is read from them here too. */
export function turnOf(line?: TurnLine | null, kind: "yoy" | "qoq" = "yoy"): string | undefined {
  if (!line) return undefined;
  const named = kind === "yoy" ? line.yoy_turn : line.qoq_turn;
  if (named) return named;
  const now = line.value, base = kind === "yoy" ? line.prev_year : line.prev_quarter;
  if (now == null || base == null || (now >= 0 && base >= 0)) return undefined;
  return now >= 0 ? "LOSS_TO_PROFIT" : base >= 0 ? "PROFIT_TO_LOSS" : now > base ? "LOSS_NARROWED" : "LOSS_WIDENED";
}

// Lines where a fall is the good news: bad loans, provisions, claims and the cost ratios (CSB's NNPA -27 bps read red)
// and the table's mover lines (depreciation, tax; O15, owner 2026-10-20)
const LOWER_IS_BETTER = /npa|provision|claim|combined|cost|expense|slippage|depreciation|^tax$/i;
export const lowerIsBetter = (key: string, label = "") => LOWER_IS_BETTER.test(key) || LOWER_IS_BETTER.test(label);

/** Lines a change of sign does not make a "loss to profit": a tax credit, an exceptional charge that did not recur, a
 *  mover row (O15). The pipeline names no turn on them; nor is one read from their values. */
export const NO_TURN = new Set(["exceptional_items", "tax_expense", "other_income", "depreciation", "finance_cost",
  "employee_cost", "raw_material_cost"]);

/** A row with nothing but zeros ("Exceptional items 0 0 0") is filler, not a figure. */
export const allZero = (line: { value: number; prev_year?: number; prev_quarter?: number }) =>
  [line.value, line.prev_year, line.prev_quarter].every((v) => v == null || v === 0);
