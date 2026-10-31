import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { MARKET_CAP_STEPS, type KpiQuery, type View } from "../../../shared/resultsTypes";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import {
  activeChips, classLeaf, GROWTH_STEPS, growthCount, growthOf, growthParams, indexLabel, MARGIN_STEPS, mcapText, toApiParams, type GrowthDraft,
} from "../../lib/resultsView";
import { Button } from "../ui/button";
import { CheckRow, SegControl, Steps, useDismiss } from "./bits";
import { SectorPicker } from "./SectorPicker";

type SetParams = (changes: Record<string, string | null | undefined>) => void;
type Open = null | "index" | "mcap" | "sector" | "growth";

export const VIEWS: { key: View; label: string }[] = [
  { key: "yoy", label: "Year-on-year" }, { key: "momentum", label: "Momentum" }, { key: "qoq", label: "Quarter-on-quarter" },
];

export const growthSteps = (unit: "%" | "bp") => [
  { value: null, label: "Any" },
  ...(unit === "%" ? GROWTH_STEPS.map((n) => ({ value: n as number, label: `${n}%` })) : MARGIN_STEPS.map((n) => ({ value: n as number, label: n === 0 ? "0 bp" : `+${n}` }))),
];
export const MOMENTUM_STEPS = [{ value: null, label: "Any" }, { value: "speeding_up" as const, label: "Speeding up" }, { value: "slowing" as const, label: "Slowing" }];

/** The search box with its "/" hint: types into the URL a moment after the last key. */
export function SearchBox({ q, setParams, className }: { q: string; setParams: SetParams; className?: string }) {
  const [text, setText] = useState(q);
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => setText(q), [q]);
  useEffect(() => {
    const id = setTimeout(() => { if (text.trim() !== q) setParams({ q: text.trim() || null }); }, 300);
    return () => clearTimeout(id);
  }, [text, q, setParams]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key !== "/" || e.metaKey || e.ctrlKey || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable) return;
      e.preventDefault();
      ref.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <label className={cn("flex h-10 items-center gap-2 rounded-xl bg-surface-2 px-3.5 text-ink-3 focus-within:ring-2 focus-within:ring-accent", className)}>
      <Search aria-hidden className="h-4 w-4 shrink-0" />
      <input ref={ref} value={text} onChange={(e) => setText(e.target.value)} placeholder="Search company or symbol" aria-label="Search company or symbol"
        onKeyDown={(e) => { if (e.key === "Escape") { setText(""); e.currentTarget.blur(); } }}
        className="h-full min-w-0 flex-1 bg-transparent text-[14px] text-ink placeholder:text-ink-3 focus:outline-none focus-visible:!outline-none" />
      {text ? (
        <button type="button" aria-label="Clear search" onClick={() => setText("")} className="grid h-6 w-6 place-items-center rounded-md hover:bg-line"><X className="h-3.5 w-3.5" /></button>
      ) : <kbd aria-hidden className="rounded border border-line-strong px-1.5 text-[11px] font-semibold text-ink-3">/</kbd>}
    </label>
  );
}

function FilterButton({ label, value, open, onClick, count, controls }: { label: string; value?: string; open: boolean; onClick: () => void; count?: number; controls: string }) {
  return (
    <button type="button" aria-expanded={open} aria-controls={controls} onClick={onClick}
      className={cn("inline-flex h-10 items-center gap-1.5 rounded-[11px] px-3 text-[14px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink", open && "bg-surface-2 text-ink")}>
      {label}
      {value && <b className="max-w-[180px] truncate font-semibold text-ink">{value}</b>}
      {count ? <span className="num rounded-full bg-accent px-[7px] text-[12px] leading-5 text-accent-ink">{count}</span> : null}
      <ChevronDown aria-hidden className="h-3.5 w-3.5" />
    </button>
  );
}

function Pop({ id, children, className, label }: { id: string; children: ReactNode; className?: string; label: string }) {
  return (
    <div id={id} role="dialog" aria-label={label}
      className={cn("absolute top-full z-30 mt-2 rounded-[18px] bg-surface p-[22px] shadow-[0_0_0_1px_var(--line-strong),0_24px_60px_-24px_rgba(20,30,50,0.25)]", className)}>
      {children}
    </div>
  );
}

function MenuItem({ on, onClick, children, n }: { on: boolean; onClick: () => void; children: ReactNode; n?: number }) {
  return (
    <button type="button" role="menuitemradio" aria-checked={on} onClick={onClick}
      className={cn("flex w-full items-center justify-between gap-6 rounded-[9px] px-2.5 py-2 text-left text-[13.5px]", on ? "bg-accent-soft font-semibold text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink")}>
      <span>{children}</span>{n != null && <span className="num text-ink-3">{n}</span>}
    </button>
  );
}

/** The desktop toolbar: search, index, market cap, sector, growth & signals, and the view switch; then the active filters as chips. */
export function FilterBar({ query, view, indices, setParams, onView }: {
  query: KpiQuery; view: View; indices: { id: string; label: string; n: number }[]; setParams: SetParams; onView: (v: View) => void;
}) {
  const [open, setOpen] = useState<Open>(null);
  const bar = useRef<HTMLDivElement>(null);
  const refs = useMemo(() => [bar], []);
  useDismiss(open != null, () => setOpen(null), refs);
  const toggle = (k: Open) => setOpen((o) => (o === k ? null : k));
  const g = growthOf(query);
  return (
    <>
      <div ref={bar} className="relative mt-9 hidden flex-wrap items-center gap-2 sm:flex">
        <SearchBox q={query.q} setParams={setParams} className="w-[260px]" />
        <span className="relative">
          <FilterButton label="Index" value={query.index ? indexLabel(query.index) : "All indices"} open={open === "index"} onClick={() => toggle("index")} controls="pop-index" />
          {open === "index" && (
            <Pop id="pop-index" label="Index" className="left-0 w-[300px] p-2">
              <div role="menu" aria-label="Index">
                <MenuItem on={!query.index} onClick={() => { setParams({ index: null }); setOpen(null); }}>All indices</MenuItem>
                {indices.map((x) => (
                  <MenuItem key={x.id} on={query.index === x.id} n={x.n} onClick={() => { setParams({ index: x.id }); setOpen(null); }}>{x.label}</MenuItem>
                ))}
              </div>
              <p className="px-2.5 pb-1 pt-2 text-[12px] text-ink-3">Members as of the quarter's last day. Numbers are companies reported.</p>
            </Pop>
          )}
        </span>
        <span className="relative">
          <FilterButton label="Market cap" value={query.mcap_min != null ? `≥ ${mcapText(query.mcap_min)}` : "Any"} open={open === "mcap"} onClick={() => toggle("mcap")} controls="pop-mcap" />
          {open === "mcap" && (
            <Pop id="pop-mcap" label="Market cap at least" className="left-0 w-[240px] p-2">
              <p className="px-2.5 pb-1 pt-1 text-[12.5px] text-ink-3">Market cap at least</p>
              <div role="menu" aria-label="Market cap at least">
                <MenuItem on={query.mcap_min == null} onClick={() => { setParams({ mcap_min: null }); setOpen(null); }}>Any</MenuItem>
                {MARKET_CAP_STEPS.map((n) => (
                  <MenuItem key={n} on={query.mcap_min === n} onClick={() => { setParams({ mcap_min: String(n) }); setOpen(null); }}>{mcapText(n)}</MenuItem>
                ))}
              </div>
            </Pop>
          )}
        </span>
        <span>
          <FilterButton label="Sector" value={query.class ? classLeaf(query.class) : "All"} open={open === "sector"} onClick={() => toggle("sector")} controls="pop-sector" />
          {open === "sector" && (
            <Pop id="pop-sector" label="Sector and industry" className="left-0 right-0 max-w-[880px] lg:left-auto">
              <SectorPicker quarter={query.quarter} value={query.class} onApply={(path) => { setParams({ class: path }); setOpen(null); }} />
            </Pop>
          )}
        </span>
        <span className="relative">
          <FilterButton label="Growth & signals" open={open === "growth"} onClick={() => toggle("growth")} count={growthCount(g)} controls="pop-growth" />
          {open === "growth" && (
            <Pop id="pop-growth" label="Growth and signals" className="left-0 w-[540px] max-lg:-left-40">
              <GrowthForm query={query} onApply={(d) => { setParams(growthParams(d)); setOpen(null); }} />
            </Pop>
          )}
        </span>
        <span className="flex-1" />
        <SegControl label="View" items={VIEWS} value={view} onChange={onView} />
      </div>
      <Chips query={query} setParams={setParams} />
    </>
  );
}

export function Chips({ query, setParams, className }: { query: KpiQuery; setParams: SetParams; className?: string }) {
  const chips = activeChips(query);
  if (!chips.length) return null;
  const clearAll = Object.fromEntries(chips.flatMap((c) => c.clear).map((k) => [k, null]));
  return (
    <div className={cn("mt-3 flex flex-wrap items-center gap-2", className)} aria-label="Active filters">
      {chips.map((c) => (
        <span key={c.id} className="inline-flex h-[30px] items-center gap-1 rounded-full bg-accent-soft pl-3 pr-1 text-[13px] text-ink">
          {c.label}
          <button type="button" aria-label={`Remove filter: ${c.label}`} onClick={() => setParams(Object.fromEntries(c.clear.map((k) => [k, null])))}
            className="grid h-[22px] w-[22px] place-items-center rounded-full text-ink-2 hover:bg-surface hover:text-ink sm:h-[22px] max-sm:h-8 max-sm:w-8">
            <X aria-hidden className="h-3.5 w-3.5" />
          </button>
        </span>
      ))}
      <button type="button" onClick={() => setParams(clearAll)} className="px-2 text-[13px] font-medium text-ink-2 hover:text-ink max-sm:min-h-11">Clear all</button>
    </div>
  );
}

/** How many companies a draft of filters would keep: the API's own count (summary.n) for the draft, asked only while the form is open. */
export function useDraftCount(query: KpiQuery, draft: GrowthDraft) {
  const params = toApiParams({ ...query, ...draft }, 1);
  const r = useQuery({
    queryKey: ["results-kpi", "count", params],
    queryFn: () => api.resultsKpi(params),
    staleTime: 60_000,
  });
  return r.data?.summary.n;
}

/** The "Growth & signals" form: a draft the reader changes freely, applied in one go. */
export function GrowthForm({ query, onApply, compact = false }: { query: KpiQuery; onApply: (d: GrowthDraft) => void; compact?: boolean }) {
  const [d, setD] = useState<GrowthDraft>(() => growthOf(query));
  const set = (patch: Partial<GrowthDraft>) => setD((x) => ({ ...x, ...patch }));
  const count = useDraftCount(query, d);
  const n = growthCount(d);
  const group = (label: string, hint: string, body: ReactNode) => (
    <div className="border-b border-line py-3.5 last:border-b-0">
      <div className="mb-2 flex justify-between gap-4 text-[13.5px] text-ink-2"><span>{label}</span><span className="text-ink-3">{hint}</span></div>
      {body}
    </div>
  );
  return (
    <div>
      {!compact && <h3 className="text-[15px] font-bold text-ink">Growth &amp; signals</h3>}
      {!compact && <p className="mt-1 text-[13px] text-ink-3">All growth is against the same quarter a year ago.</p>}
      {group("Profit growth at least", "Profit = PAT, as filed",
        <Steps label="Profit growth at least" options={growthSteps("%")} value={d.pat_min} onChange={(v) => set({ pat_min: v })} big={compact} />)}
      {group("Revenue growth at least", "",
        <Steps label="Revenue growth at least" options={growthSteps("%")} value={d.rev_min} onChange={(v) => set({ rev_min: v })} big={compact} />)}
      {group("EBITDA growth at least", "not for banks and insurers",
        <Steps label="EBITDA growth at least" options={growthSteps("%")} value={d.ebitda_min} onChange={(v) => set({ ebitda_min: v })} big={compact} />)}
      {group("Margin change at least", "100 bp = 1 percentage point",
        <Steps label="Margin change at least" options={growthSteps("bp")} value={d.opm_min} onChange={(v) => set({ opm_min: v })} big={compact} />)}
      {group("Momentum", "profit growth this quarter vs last quarter's",
        <Steps label="Momentum" options={MOMENTUM_STEPS} value={d.momentum} onChange={(v) => set({ momentum: v })} big={compact} />)}
      <div className="py-2">
        <CheckRow checked={d.turnaround} onChange={(v) => set({ turnaround: v })} label="Turned loss to profit" hint="a loss a year ago, a profit now" big={compact} />
        <CheckRow checked={d.nfo} onChange={(v) => set({ nfo: v })} label="Profit up, EBITDA down" hint="profit rose while EBITDA fell: check other income or one-offs" big={compact} />
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-line pt-4">
        <Button variant="ghost" className="h-10" onClick={() => setD({ pat_min: null, rev_min: null, ebitda_min: null, opm_min: null, momentum: null, turnaround: false, nfo: false })}>Reset</Button>
        <span className="num flex-1 text-right text-[13px] text-ink-3" aria-live="polite">
          {count == null ? "" : `${count} ${count === 1 ? "company" : "companies"} match`}
        </span>
        <Button variant="primary" className="h-10 rounded-[11px] px-3.5 font-semibold" onClick={() => onApply(d)}>
          {n ? `Apply ${n} ${n === 1 ? "filter" : "filters"}` : "Apply"}
        </Button>
      </div>
    </div>
  );
}
