import type { Roiic } from "../../../shared/types";
import { cn } from "../../lib/cn";
import { rupees } from "../../lib/format";
import { Panel } from "./Panel";

/** The company's calibration rule and return on incremental capital, moved from the memory drawer to the promise
 *  tracker (owner, 2026-10-21: one company view, not a half-window beside it). */
export function parseRoiic(raw: string | null | undefined): Roiic | null {
  try { return raw ? (JSON.parse(raw) as Roiic) : null; } catch { return null; }
}

const ROIIC_VERDICT: Record<NonNullable<Roiic["verdict"]>, { text: string; tone: string }> = {
  COMPOUNDER: { text: "Capital compounder", tone: "text-pos" },
  DILUTER: { text: "Capital diluter", tone: "text-neg" },
  SELF_FUNDED: { text: "Self-funded growth", tone: "text-pos" },
};

export function CapitalAndCalibration({ rule, roiic }: { rule: string | null; roiic: Roiic | null }) {
  if (!rule && !roiic) return null;
  return (
    <Panel title="How to read management" sub="calibration and capital">
      <div className="space-y-2">
        {rule && <p className="rounded-lg bg-insight px-3 py-2 text-[13px] text-insight-ink">📐 {rule}</p>}
        {roiic && (
          <p className="num text-[12.5px] text-ink-2">
            {roiic.verdict && <span className={cn("font-semibold", ROIIC_VERDICT[roiic.verdict].tone)}>{ROIIC_VERDICT[roiic.verdict].text} · </span>}
            {roiic.from} → {roiic.to}: EBITDA run-rate {roiic.ebitda_added_cr >= 0 ? "+" : ""}{rupees(roiic.ebitda_added_cr)} Cr on {rupees(roiic.capital_added_cr)} Cr of capital added
            {roiic.pct != null && <> (ROIIC {Math.round(roiic.pct)}%)</>}
          </p>
        )}
      </div>
    </Panel>
  );
}
