import * as Dialog from "@radix-ui/react-dialog";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";
import { MARKET_CAP_STEPS, type KpiQuery } from "../../../shared/resultsTypes";
import { cn } from "../../lib/cn";
import { classLeaf, growthCount, growthOf, growthParams, indexLabel, mcapText, type GrowthDraft } from "../../lib/resultsView";
import { Button } from "../ui/button";
import { CheckRow, Steps } from "./bits";
import { growthSteps, MOMENTUM_STEPS, useDraftCount } from "./FilterBar";
import { SectorPicker } from "./SectorPicker";

type Page = "main" | "index" | "mcap" | "sector" | "more";
type Draft = GrowthDraft & Pick<KpiQuery, "index" | "mcap_min" | "class">;

/** The phone's filters in one bottom sheet: index, market cap and sector open their own page inside it; profit growth and momentum
 *  are steps on the first page; every target is at least 44px. Nothing applies until "Apply". */
export function FilterSheet({ open, onOpenChange, query, indices, setParams }: {
  open: boolean; onOpenChange: (o: boolean) => void; query: KpiQuery; indices: { id: string; label: string; n: number }[];
  setParams: (c: Record<string, string | null>) => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      {/* no portal: the sheet stays inside the page, so the page's own colours apply */}
      <Dialog.Overlay className="fixed inset-0 z-40 bg-black/20" />
      <Dialog.Content aria-describedby={undefined}
        className="fixed inset-x-0 bottom-0 z-50 max-h-[88vh] overflow-y-auto rounded-t-[22px] bg-surface px-4 pb-4 pt-2.5 shadow-[0_-1px_0_var(--line-strong)] focus:outline-none">
        {open && <SheetBody query={query} indices={indices} onApply={(changes) => { setParams(changes); onOpenChange(false); }} />}
      </Dialog.Content>
    </Dialog.Root>
  );
}

function SheetBody({ query, indices, onApply }: { query: KpiQuery; indices: { id: string; label: string; n: number }[]; onApply: (c: Record<string, string | null>) => void }) {
  const [page, setPage] = useState<Page>("main");
  const [d, setD] = useState<Draft>(() => ({ ...growthOf(query), index: query.index, mcap_min: query.mcap_min, class: query.class }));
  const set = (patch: Partial<Draft>) => setD((x) => ({ ...x, ...patch }));
  const count = useDraftCount({ ...query, index: d.index, mcap_min: d.mcap_min, class: d.class }, d);
  const n = growthCount(d) + (d.index ? 1 : 0) + (d.mcap_min != null ? 1 : 0) + (d.class ? 1 : 0);
  const apply = () => onApply({ ...growthParams(d), index: d.index, mcap_min: d.mcap_min == null ? null : String(d.mcap_min), class: d.class });
  const reset = () => setD({ pat_min: null, rev_min: null, ebitda_min: null, opm_min: null, momentum: null, turnaround: false, nfo: false, index: null, mcap_min: null, class: null });
  const more = [d.rev_min != null && `Rev ≥ ${d.rev_min}%`, d.ebitda_min != null && `EBITDA ≥ ${d.ebitda_min}%`, d.opm_min != null && `Margin ≥ +${d.opm_min} bp`].filter(Boolean).join(", ");

  const row = (label: string, value: string, to: Page) => (
    <button type="button" onClick={() => setPage(to)} className="flex min-h-[52px] w-full items-center justify-between gap-4 border-b border-line text-left text-[15px] text-ink">
      {label}<span className="flex min-w-0 items-center gap-1 text-ink-2"><span className="truncate">{value}</span><ChevronRight aria-hidden className="h-4 w-4 shrink-0" /></span>
    </button>
  );
  const option = (on: boolean, label: ReactNode, onClick: () => void, key: string) => (
    <button key={key} type="button" role="radio" aria-checked={on} onClick={onClick}
      className={cn("flex min-h-12 w-full items-center justify-between border-b border-line text-left text-[15px]", on ? "font-semibold text-accent" : "text-ink")}>
      {label}{on && <span aria-hidden>✓</span>}
    </button>
  );
  const back = (title: string) => (
    <div className="mb-2 flex items-center gap-2">
      <button type="button" onClick={() => setPage("main")} aria-label="Back to filters" className="grid h-11 w-11 place-items-center rounded-xl text-ink-2 hover:bg-surface-2"><ChevronLeft className="h-5 w-5" /></button>
      <Dialog.Title className="text-[19px] font-bold text-ink">{title}</Dialog.Title>
    </div>
  );
  const cta = (
    <div className="sticky bottom-0 mt-3 flex gap-2.5 bg-surface pt-3.5">
      <Button variant="primary" className="h-12 flex-1 justify-center rounded-xl text-[15px] font-semibold" onClick={apply}>
        {n ? `Apply ${n} ${n === 1 ? "filter" : "filters"}` : "Show all"}{count != null ? ` · ${count}` : ""}
      </Button>
    </div>
  );

  return (
    <div>
      <div aria-hidden className="mx-auto mb-3 h-[5px] w-10 rounded-full bg-line-strong" />
      {page === "main" && (
        <>
          <div className="mb-1.5 flex items-center justify-between">
            <Dialog.Title className="text-[19px] font-bold text-ink">Filters</Dialog.Title>
            <Button variant="ghost" className="h-11 text-[15px]" onClick={reset}>Reset</Button>
          </div>
          {row("Index", d.index ? indexLabel(d.index) : "All indices", "index")}
          {row("Market cap", d.mcap_min != null ? `≥ ${mcapText(d.mcap_min)}` : "Any", "mcap")}
          {row("Sector › industry", d.class ? classLeaf(d.class) : "All", "sector")}
          <div className="pb-1 pt-3.5 text-[14px] text-ink-2">Profit growth vs a year ago, at least</div>
          <Steps big label="Profit growth at least" options={growthSteps("%").filter((o) => o.value !== 30)} value={d.pat_min} onChange={(v) => set({ pat_min: v })} />
          <div className="pb-1 pt-3.5 text-[14px] text-ink-2">Momentum</div>
          <Steps big label="Momentum" options={MOMENTUM_STEPS} value={d.momentum} onChange={(v) => set({ momentum: v })} />
          <div className="mt-2">{row("Revenue, EBITDA, margin", more || "Any", "more")}</div>
          <CheckRow big checked={d.turnaround} onChange={(v) => set({ turnaround: v })} label="Turned loss to profit" />
          <CheckRow big checked={d.nfo} onChange={(v) => set({ nfo: v })} label="Profit up, EBITDA down" />
          {cta}
        </>
      )}
      {page === "index" && (
        <>
          {back("Index")}
          <div role="radiogroup" aria-label="Index">
            {option(!d.index, "All indices", () => { set({ index: null }); setPage("main"); }, "all")}
            {indices.map((x) => option(d.index === x.id, <span>{x.label} <span className="num text-[13px] font-normal text-ink-3">{x.n}</span></span>,
              () => { set({ index: x.id }); setPage("main"); }, x.id))}
          </div>
        </>
      )}
      {page === "mcap" && (
        <>
          {back("Market cap at least")}
          <div role="radiogroup" aria-label="Market cap at least">
            {option(d.mcap_min == null, "Any", () => { set({ mcap_min: null }); setPage("main"); }, "any")}
            {MARKET_CAP_STEPS.map((v) => option(d.mcap_min === v, mcapText(v), () => { set({ mcap_min: v }); setPage("main"); }, String(v)))}
          </div>
        </>
      )}
      {page === "sector" && (
        <>
          {back("Sector › industry")}
          <SectorPicker stacked quarter={query.quarter} value={d.class} onApply={(path) => { set({ class: path }); setPage("main"); }} />
        </>
      )}
      {page === "more" && (
        <>
          {back("Revenue, EBITDA, margin")}
          <div className="pb-1 pt-2 text-[14px] text-ink-2">Revenue growth at least</div>
          <Steps big label="Revenue growth at least" options={growthSteps("%")} value={d.rev_min} onChange={(v) => set({ rev_min: v })} />
          <div className="pb-1 pt-3.5 text-[14px] text-ink-2">EBITDA growth at least <span className="text-ink-3">· not for banks and insurers</span></div>
          <Steps big label="EBITDA growth at least" options={growthSteps("%")} value={d.ebitda_min} onChange={(v) => set({ ebitda_min: v })} />
          <div className="pb-1 pt-3.5 text-[14px] text-ink-2">Margin change at least <span className="text-ink-3">· 100 bp = 1 point</span></div>
          <Steps big label="Margin change at least" options={growthSteps("bp")} value={d.opm_min} onChange={(v) => set({ opm_min: v })} />
          <Button className="mt-4 h-12 w-full justify-center rounded-xl text-[15px]" onClick={() => setPage("main")}>Done</Button>
        </>
      )}
    </div>
  );
}
