/** The paired Results table (owner, 2 Nov 2026: design C): one line per company, each figure beside its growth. Pure helpers, no React,
 *  so `node --test` runs the cases in test/resultsPaired.test.ts. */

import type { Kind, KpiRow, Turn } from "../../shared/resultsTypes.ts";
import { fmtBp, fmtMargin, NM, TURN_TEXT, turnTone, type Tone } from "./resultsView.ts";

const plain0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const plain2 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

/** An amount in crore with Indian grouping and no unit (the column header says "₹ Cr"): "1,26,398", "−1,879", "12.34"; a dash when missing. */
export function fmtCrAmount(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  return `${v < 0 ? "−" : ""}${a >= 100 ? plain0.format(a) : plain2.format(a)}`;
}

/** What the EBITDA slot of a row holds: banks and insurers have no EBITDA (a bank's financing profit is in the quick look), an NBFC's slot holds
 *  its financing profit, everyone else their EBITDA. */
export type EbitdaSlot = "none" | "figure" | "financing";
export const ebitdaSlot = (kind: Kind): EbitdaSlot => (kind === "bank" || kind === "insurer" ? "none" : kind === "nbfc" ? "financing" : "figure");

/** The small line under the EBITDA pair: "margin 17.1% (−90 bp)"; an NBFC's starts "financing profit · ". The bp change is NM where the margin is past
 *  ±100% or the base period was a loss (results_table.py), and left out when there is no year-ago (or last-quarter) figure. Null: no margin to show. */
export function marginLine(
  r: Pick<KpiRow, "kind" | "opm" | "opm_yoy_bps" | "opm_qoq_bps" | "ebitda_yoy" | "ebitda_turn" | "ebitda_qoq">, qoq = false,
): string | null {
  const slot = ebitdaSlot(r.kind);
  if (slot === "none" || r.opm == null) return null;
  const bps = qoq ? r.opm_qoq_bps : r.opm_yoy_bps;
  const hadBase = qoq ? r.ebitda_qoq != null : r.ebitda_yoy != null || r.ebitda_turn != null;
  const change = bps != null ? ` (${fmtBp(bps)})` : hadBase ? ` (${NM})` : "";
  return `${slot === "financing" ? "financing profit · " : ""}margin ${fmtMargin(r.opm)}${change}`;
}

/** A named turn across a loss is shown as a small labelled pill instead of a per cent: its words and tone. */
export function turnPill(turn: Turn | null | undefined): { text: string; tone: Tone } | null {
  return turn ? { text: TURN_TEXT[turn], tone: turnTone(turn) } : null;
}
