import { AlertTriangle, Check as CheckIcon } from "lucide-react";
import { useEffect, useRef, type ReactNode, type RefObject } from "react";
import type { KpiRow, Momentum, Turn } from "../../../shared/resultsTypes";
import { industryLine } from "../../../shared/industry";
import { cn } from "../../lib/cn";
import { growth, KIND_TAG, type Seg, type Tone } from "../../lib/resultsView";
import { Avatar } from "../Avatar";

export const TONE_TEXT: Record<Tone, string> = { up: "text-pos", down: "text-neg", flat: "text-ink-2" };

/** Runs of text from lib/resultsView (the season's sentences): bold and coloured parts as the numbers say. */
export function Segs({ segs }: { segs: Seg[] }) {
  return (
    <>
      {segs.map((s, i) => s.tone && s.tone !== "flat"
        ? <span key={i} className={cn("num", TONE_TEXT[s.tone])}>{s.t}</span>
        : s.b ? <b key={i} className="num font-semibold text-ink">{s.t}</b> : <span key={i}>{s.t}</span>)}
    </>
  );
}

/** A growth figure: a small arrow and the signed number (never a filled pill), or the named turn across a loss. */
export function Growth({ value, turn, unit = "%", className, arrowClass }: {
  value: number | null | undefined; turn?: Turn | null; unit?: "%" | "bp"; className?: string; arrowClass?: string;
}) {
  const g = growth(value, turn, unit);
  if (!g) return <span className="font-medium text-ink-3">—</span>;
  return (
    <span className={cn("num whitespace-nowrap font-semibold", TONE_TEXT[g.tone], className)}>
      {g.arrow && <span aria-hidden className={cn("relative -top-[0.12em] mr-1 text-[0.62em]", arrowClass)}>{g.arrow}</span>}
      {g.text}
    </span>
  );
}

/** Speeding up / slowing beside a profit figure: an arrow in a small tile, with words for screen readers and on hover. */
export function MomentumMark({ m }: { m: Momentum }) {
  if (m !== "speeding_up" && m !== "slowing") return null;
  const up = m === "speeding_up";
  const tip = up ? "Speeding up: faster than last quarter's growth" : "Slowing: slower than last quarter's growth";
  return (
    <span title={tip} role="img" aria-label={up ? "speeding up" : "slowing"}
      className="ml-1.5 inline-grid h-5 w-5 place-items-center rounded-md bg-surface-2 align-[1px] text-[13px] font-bold text-ink">
      {up ? "⇡" : "⇣"}
    </span>
  );
}

export function NfoFlag({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap text-[13px] text-ink", className)}
      title="Profit rose while EBITDA fell: check other income or one-offs">
      <AlertTriangle aria-hidden className="h-3.5 w-3.5 text-warn" />Profit not from operations
    </span>
  );
}

type Mark = { tone: "up" | "down" | "none"; tip: string };
const markOf = (label: string, value: number | null, turn: Turn | null, shown: boolean): Mark => {
  if (!shown) return { tone: "none", tip: `${label}: not shown for this kind of company` };
  if (turn) {
    const up = turn === "LOSS_TO_PROFIT" || turn === "LOSS_NARROWED";
    return { tone: up ? "up" : "down", tip: `${label}: ${turn === "LOSS_TO_PROFIT" ? "turned from loss to profit" : turn === "PROFIT_TO_LOSS" ? "turned from profit to loss" : turn === "LOSS_NARROWED" ? "loss narrowed" : "loss widened"}` };
  }
  if (value == null) return { tone: "none", tip: `${label}: no growth figure` };
  return { tone: value >= 0 ? "up" : "down", tip: `${label}: ${value >= 0 ? "up" : "down"} ${Math.abs(value).toFixed(1)}%` };
};

/** Three marks for revenue, EBITDA and profit: up, down, or not shown, each with its words. */
export function Signals({ row, qoq = false }: { row: KpiRow; qoq?: boolean }) {
  const marks: Mark[] = [
    markOf(row.kind === "bank" ? "Interest income" : "Revenue", qoq ? row.revenue_qoq : row.revenue_yoy, null, row.kind !== "insurer"),
    markOf(row.kind === "nbfc" ? "Financing profit" : "EBITDA", qoq ? row.ebitda_qoq : row.ebitda_yoy, qoq ? null : row.ebitda_turn,
      row.kind === "company" || row.kind === "nbfc"),
    markOf("Profit", qoq ? row.pat_qoq : row.pat_yoy, qoq ? row.pat_qoq_turn : row.pat_turn, true),
  ];
  return (
    <span className="inline-flex gap-1">
      {marks.map((m, i) => (
        <span key={i} title={m.tip} role="img" aria-label={m.tip}
          className={cn("grid h-[22px] w-[22px] place-items-center rounded-[7px] text-[10px] font-bold",
            m.tone === "up" ? "bg-pos-soft text-pos" : m.tone === "down" ? "bg-neg-soft text-neg" : "text-ink-3 ring-1 ring-inset ring-line-strong")}>
          {m.tone === "up" ? "▲" : m.tone === "down" ? "▼" : "–"}
        </span>
      ))}
    </span>
  );
}

/** The company cell: letter avatar, symbol with its kind (Bank, NBFC, Insurer), and the classification line. */
export function CompanyCell({ row, compact = false }: { row: Pick<KpiRow, "symbol" | "scrip_code" | "company_name" | "industry" | "kind" | "basis">; compact?: boolean }) {
  const line = industryLine(row.industry) ?? "Unclassified";
  return (
    <span className="flex min-w-0 items-start gap-3">
      <Avatar name={row.company_name ?? row.symbol ?? row.scrip_code} symbol={row.symbol} size={32} className="rounded-[10px] text-[14px]" />
      <span className="min-w-0">
        <span className="block text-[15px] font-bold leading-tight text-ink">
          {row.symbol ?? row.scrip_code}
          {KIND_TAG[row.kind] && <span className="ml-1.5 text-[12.5px] font-medium text-ink-3">{KIND_TAG[row.kind]}</span>}
        </span>
        <span className={cn("mt-0.5 block text-[13px] text-ink-3", compact && "truncate")} title={row.industry ?? undefined}>
          {line}{row.basis === "STANDALONE" && " · standalone"}
        </span>
      </span>
    </span>
  );
}

/** Closes a floating panel on a click outside `refs` or on Escape. */
export function useDismiss(open: boolean, onClose: () => void, refs: RefObject<HTMLElement | null>[]) {
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => {
      if (refs.every((r) => !r.current?.contains(e.target as Node))) close.current();
    };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") close.current(); };
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", down); document.removeEventListener("keydown", key); };
  }, [open, refs]);
}

/** A segmented switch (quarter, view, group by, cut): one choice pressed, on a grey track. */
export function SegControl<T extends string>({ items, value, onChange, label, className, itemClass }: {
  items: { key: T; label: ReactNode; title?: string }[]; value: T; onChange: (k: T) => void; label: string; className?: string; itemClass?: string;
}) {
  return (
    <div role="group" aria-label={label} className={cn("inline-flex gap-0.5 rounded-xl bg-surface-2 p-1", className)}>
      {items.map((it) => (
        <button key={it.key} type="button" aria-pressed={it.key === value} title={it.title} onClick={() => onChange(it.key)}
          className={cn("whitespace-nowrap rounded-[9px] px-3 py-[7px] text-[13.5px] font-semibold transition-colors",
            it.key === value ? "bg-surface text-ink shadow-[inset_0_0_0_1px_var(--line-strong)]" : "text-ink-2 hover:text-ink", itemClass)}>
          {it.label}
        </button>
      ))}
    </div>
  );
}

/** "At least" steps: Any, 0%, 10% ... */
export function Steps<T extends number | string>({ options, value, onChange, label, big = false }: {
  options: { value: T | null; label: string }[]; value: T | null; onChange: (v: T | null) => void; label: string; big?: boolean;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button key={String(o.value)} type="button" role="radio" aria-checked={on} onClick={() => onChange(o.value)}
            className={cn("min-w-[52px] rounded-[9px] px-2.5 text-[13.5px] font-semibold transition-colors", big ? "h-11 min-w-[56px]" : "h-[34px]",
              on ? "bg-accent text-accent-ink" : "bg-surface-2 text-ink-2 hover:text-ink")}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** A checkbox row with a hint underneath. */
export function CheckRow({ checked, onChange, label, hint, big = false }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string; big?: boolean }) {
  return (
    <button type="button" role="checkbox" aria-checked={checked} onClick={() => onChange(!checked)}
      className={cn("flex w-full items-start gap-3 py-2 text-left", big && "min-h-12 items-center")}>
      <span className={cn("mt-px grid h-5 w-5 shrink-0 place-items-center rounded-md", checked ? "bg-accent text-accent-ink" : "ring-[1.5px] ring-inset ring-ink-3")}>
        {checked && <CheckIcon className="h-3.5 w-3.5" strokeWidth={3} />}
      </span>
      <span className="text-[14px] text-ink">
        {label}
        {hint && <span className="block text-[13px] text-ink-3">{hint}</span>}
      </span>
    </button>
  );
}

/** A grey panel of the season block. */
export function Panel({ title, children, className }: { title?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-2xl bg-surface-2 px-6 py-[22px]", className)}>
      {title && <h2 className="mb-3 text-[13px] font-semibold text-ink-2">{title}</h2>}
      {children}
    </section>
  );
}

/** A grey block while data loads, the same size as what replaces it (no layout shift). */
export function Skeleton({ className }: { className?: string }) {
  return <span aria-hidden className={cn("block animate-pulse rounded-md bg-line/70", className)} />;
}
