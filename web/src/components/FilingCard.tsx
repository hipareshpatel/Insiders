import {
  Lock,
  AlertTriangle, BadgeCheck, Calculator, CheckCircle2, Gauge, Layers, ListChecks, Ruler, Scale, ShieldAlert, Timer,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import type { CardBody, CardRow, QuantifiedImpact, Signal } from "../../shared/types";
import { cn } from "../lib/cn";
import { withoutEps } from "../lib/cardText";
import { exact, quantValue } from "../lib/format";

/** Signal types the pipeline has turned off (signals.py SIGNALS_OFF): cards written before then still carry them, and
 * live reviews 1-2 found them wrong on the card's face (Ahluwalia's margin mix, Shivam's EPS shift, CSB's resolved
 * prediction). Keep in step with SIGNALS_OFF. */
export const SIGNALS_OFF = new Set<string>(["DILUTION", "MARGIN_MIX", "CAPITAL_COMPOUNDER", "METRIC_SHIFT", "PREDICTION_RESOLVED",
  "CAPITAL_DILUTER", "JAWS"]);

export function parseCard(row: CardRow): CardBody | null {
  try {
    const card = JSON.parse(row.card_json) as CardBody;
    return withoutEps({ ...card, signals: (card.signals ?? []).filter((s) => !SIGNALS_OFF.has(s.type)) });
  } catch {
    return null;
  }
}

export const SIGNAL: Record<Signal["type"], { label: string; icon: typeof Gauge }> = {
  PROMISE_DELIVERED: { label: "Promise delivered", icon: CheckCircle2 },
  GUIDANCE_BREACH: { label: "Guidance breach", icon: ShieldAlert },
  WATCH_RESOLVED: { label: "Follow-up", icon: ListChecks },
  DILUTION: { label: "Dilution", icon: Scale },
  SCALE: { label: "Scale", icon: Ruler },
  ORDER_FLOW: { label: "Order flow", icon: Layers },
  PLEDGE: { label: "Promoter pledge", icon: Lock },
  TRADE_REMEDY: { label: "Trade remedy", icon: Scale },
  WORKING_CAPITAL_STRAIN: { label: "Working capital", icon: AlertTriangle },
  METRIC_SHIFT: { label: "Metric shift", icon: Gauge },
  BOARD_DELIBERATION: { label: "Long board meeting", icon: Timer },
  REG30_THRESHOLD: { label: "Reg 30 materiality", icon: Scale },
  PREDICTION_RESOLVED: { label: "Target check", icon: ListChecks },
  OWNERSHIP_SHIFT: { label: "Ownership", icon: Layers },
  AUDIT_FLAG: { label: "Audit", icon: ShieldAlert },
  VOLUME_STREAK: { label: "Volume streak", icon: Gauge },
  QUARTER_PREVIEW: { label: "Quarter preview", icon: Gauge },
  LOW_QUALITY_BEAT: { label: "Earnings quality", icon: AlertTriangle },
  MARGIN_MIX: { label: "Margin drivers", icon: Gauge },
  JAWS: { label: "Cost vs revenue", icon: Scale },
  LOW_CASH_TAX: { label: "Tax rate", icon: Scale },
  Q4_TRUE_UP: { label: "Q4 true-up", icon: ShieldAlert },
  RECURRING_ONE_OFFS: { label: "Recurring one-offs", icon: AlertTriangle },
  DEBT_CASH_PARADOX: { label: "Debt and cash", icon: Scale },
  DISTRESS: { label: "Debt service", icon: ShieldAlert },
  RATING_LIQUIDITY: { label: "Rating", icon: ShieldAlert },
  FESTIVE_SEASON: { label: "Festive season", icon: Gauge },
  ASSET_TURN: { label: "Asset turns", icon: Scale },
  CAPITAL_COMPOUNDER: { label: "Capital compounder", icon: Gauge },
  CAPITAL_DILUTER: { label: "Capital diluter", icon: AlertTriangle },
};
export const SEVERITY_TEXT: Record<Signal["severity"], string> = { POSITIVE: "text-pos", WARNING: "text-warn", INFO: "text-info" };

function Bullet({ children }: { children: ReactNode }) {
  return (
    <li className="flex gap-2.5 text-[14px] leading-relaxed text-ink">
      <span aria-hidden className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-ink-3" />
      <span className="min-w-0">{children}</span>
    </li>
  );
}

export function TrackItem({ icon: Icon, label, items }: { icon: typeof Timer; label: string; items: string[] }) {
  return (
    <div>
      <dt className="flex items-center gap-1.5 text-[13px] font-semibold text-ink"><Icon className="h-3.5 w-3.5 text-ink-3" />{label}</dt>
      <dd className="mt-0.5 text-[13.5px] leading-relaxed text-ink-2">
        {items.map((t, i) => <div key={i}>{t}</div>)}
      </dd>
    </div>
  );
}

export function QuantLine({ q }: { q: QuantifiedImpact }) {
  const [open, setOpen] = useState(false);
  const verified = q.check === "VERIFIED";
  return (
    <Bullet>
      <span className="font-semibold text-accent">[Quantified impact]</span>{" "}
      {q.label}: <span className="num font-semibold text-ink">{quantValue(q.result, q.unit)}</span>
      {q.interpretation ? <span className="text-ink-2"> {q.interpretation}</span> : null}{" "}
      <span className={cn("ml-1 inline-flex items-center gap-1 align-middle text-[11px]", verified ? "text-pos" : q.check === "MISMATCH" ? "text-neg" : "text-ink-3")}
        title={q.check_note ?? undefined}>
        {verified ? <BadgeCheck className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
        {verified ? "math checked" : q.check === "MISMATCH" ? "math doesn't check out" : "unchecked"}
      </span>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} data-noexport="true"
        className="ml-2 inline-flex items-center gap-1 align-middle text-[11px] font-medium text-accent hover:underline">
        <Calculator className="h-3 w-3" /> {open ? "Hide working" : "Show working"}
      </button>
      {open && (
        <span className="mt-1.5 block rounded-lg bg-surface-2 px-3 py-2 text-[12.5px]">
          <code className="num block text-ink">{q.formula}</code>
          {q.inputs.map((i) => (
            <span key={i.name} className="mt-1 flex flex-wrap items-baseline gap-x-2">
              <span className="num text-ink">{i.name} = {exact(i.value)}{i.unit ? ` ${i.unit}` : ""}</span>
              <span className={cn("rounded px-1 text-[10px] font-semibold uppercase",
                i.source === "ASSUMPTION" ? "bg-warn-soft text-warn" : "bg-accent-soft text-accent")}>{i.source.toLowerCase()}</span>
              {q.unsourced_inputs?.includes(i.name) ? <span className="text-neg">not found in the filing</span> : null}
              {i.note ? <span className="text-ink-3">{i.note}</span> : null}
            </span>
          ))}
          <span className="mt-1 block text-[11px] text-ink-3">An estimate from the inputs shown, not a forecast or recommendation.</span>
        </span>
      )}
    </Bullet>
  );
}
