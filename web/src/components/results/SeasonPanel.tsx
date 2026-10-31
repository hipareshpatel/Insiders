import { ArrowRight, ChartColumn, ChevronsDown, ChevronsUp, IndianRupee, Minus, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import type { GroupRow, KpiSummary } from "../../../shared/resultsTypes";
import { cn } from "../../lib/cn";
import { fmtCount, fmtPct, medianNote, seasonHeadline, seasonLines, toneOf, type SpreadKey } from "../../lib/resultsView";
import { Panel, Segs, Skeleton } from "./bits";
import { Histogram } from "./charts";

/** The top of the Companies tab (owner, 31 Oct 2026: Design E's crafted elements, keeping "What this list says"): four tiles (revenue, EBITDA
 *  and PAT up, loss to profit) with each median, the season's words, the spread of PAT growth and whether profit growth is speeding up
 *  (owner, 31 Oct 2026: no Nifty 500 progress card, it may mislead). Every number comes from the API's summary of the filtered set; the words also read the groups by index. */
export function SeasonPanel({ summary, indexRows, filtered, spread, turnaround, onSpread, onTurnaround }: {
  summary: KpiSummary | undefined; indexRows: GroupRow[] | undefined;
  filtered: boolean; spread: SpreadKey | null; turnaround: boolean; onSpread: (k: SpreadKey | null) => void; onTurnaround: (on: boolean) => void;
}) {
  if (!summary) return <SeasonSkeleton />;
  const lines = seasonLines(summary, indexRows);
  return (
    <div className="mt-4 flex flex-col gap-3 sm:mt-7 lg:gap-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        <Tile icon={<IndianRupee className="h-3.5 w-3.5" />} label="Revenue up" of={summary.revenue_of} up={summary.revenue_up} reported={summary.revenue_n}
          foot={<MedianFoot noun="revenue" value={summary.median_revenue_yoy} />} />
        <Tile icon={<ChartColumn className="h-3.5 w-3.5" />} label="EBITDA up" up={summary.ebitda_up} of={summary.ebitda_of} reported={summary.ebitda_n}
          note={summary.ebitda_n < summary.n ? "Banks and NBFCs have no EBITDA, so this base is smaller." : undefined}
          foot={<MedianFoot noun="EBITDA" value={summary.median_ebitda_yoy} />} />
        <Tile icon={<TrendingUp className="h-3.5 w-3.5" />} label="PAT up" title="PAT: profit after tax" up={summary.pat_up} of={summary.pat_of} reported={summary.pat_n}
          foot={<MedianFoot noun="profit" value={summary.median_pat_yoy} title={medianNote(summary)} />} />
        <Tile icon={<ArrowRight className="h-3.5 w-3.5" />} label="Loss to profit" up={summary.loss_to_profit} of={summary.n} reported={summary.n}
          foot={<span className="text-ink-3">No % when last year was a loss</span>} />
      </div>

      <Panel className="px-[18px] py-5 sm:px-7 sm:py-[22px]" title={filtered ? "What this list says" : "What the season says so far"}>
        <p className="max-w-[920px] text-[19px] font-semibold leading-[1.3] tracking-[-0.015em] text-ink sm:text-[22px]">
          <Segs segs={seasonHeadline(summary, filtered)} />
        </p>
        {lines.length > 0 && (
          <ul className="mt-4 grid gap-x-7 gap-y-2.5 sm:grid-cols-2">
            {lines.map((l, i) => (
              <li key={i} className={cn("relative pl-4 text-[14.5px] text-ink-2 before:absolute before:left-0 before:top-[0.62em] before:h-1.5 before:w-1.5 before:rounded-[2px] before:bg-line-strong",
                i >= 2 && "hidden sm:list-item")}>
                <Segs segs={l} />
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <div className="flex flex-col gap-3 lg:grid lg:grid-cols-12 lg:gap-4">
        <Panel className="px-[18px] sm:px-6 lg:col-span-7" title={
          <span className="flex flex-wrap items-baseline justify-between gap-2">
            <span><abbr title="PAT: profit after tax" className="no-underline">Spread of PAT growth</abbr> <span className="block font-normal text-ink-3 sm:inline"><span className="hidden sm:inline">· </span>{fmtCount(summary.n)} {summary.n === 1 ? "company" : "companies"} · profit this quarter vs a year ago</span></span>
            <span className="flex gap-3 text-[12px] font-normal text-ink-2">
              <span><i aria-hidden className="mr-1 inline-block h-2 w-2 rounded-[2px] bg-neg align-[1px]" />Fell</span>
              <span><i aria-hidden className="mr-1 inline-block h-2 w-2 rounded-[2px] bg-pos align-[1px]" />Grew</span>
            </span>
          </span>}>
          {summary.n === 0 ? <p className="py-16 text-center text-[13px] text-ink-3">No company to chart yet.</p> : (
            <>
              <Histogram summary={summary} active={spread} onPick={onSpread} turnaround={turnaround} onTurnaround={onTurnaround} />
              <p className="text-[12.5px] text-ink-3">
                {medianNote(summary)} The {fmtCount(summary.spread.loss_to_profit)} that turned a loss into a profit sit apart from the four bars. Click a bar to list its companies.
              </p>
            </>
          )}
        </Panel>
        <SpeedingUp summary={summary} />
      </div>
    </div>
  );
}

/** One tile: how many grew out of how many that can be compared with a year ago, a 20-step bar, and what sits under it (the median, or why
 *  there is none). `reported` is every company with the line: when it is more than `of`, the rest have no year-ago quarter. */
function Tile({ icon, label, title, up, of, reported, note, foot }: {
  icon: ReactNode; label: string; title?: string; up: number; of: number; reported: number; note?: string; foot: ReactNode;
}) {
  const pct = of ? Math.round((up / of) * 100) : 0;
  const filled = Math.round(pct / 5);
  const gap = reported > of;
  return (
    <Panel className="flex flex-col justify-between px-4 py-4 sm:px-5">
      <div>
        <div className="flex items-center gap-1.5 text-[13px] font-semibold text-ink-2" title={title}>
          <span aria-hidden className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-surface text-ink-2">{icon}</span>
          <span>{label} <span className="font-normal text-ink-3">vs a year ago</span></span>
        </div>
        <div className="num mt-3 flex items-baseline gap-1.5">
          <span className="text-[28px] font-bold leading-none tracking-[-0.02em] text-ink sm:text-[32px]">{fmtCount(up)}</span>
          <span className="text-[13px] text-ink-3">of {fmtCount(of)} · {pct}%</span>
        </div>
        <div className="mt-3 flex gap-[2px]" role="img" aria-label={`${fmtCount(up)} of ${fmtCount(of)}, ${pct}%`}>
          {Array.from({ length: 20 }, (_, i) => <i key={i} className={cn("h-2 flex-1 rounded-[1px]", i < filled ? "bg-pos" : "bg-line")} />)}
        </div>
        {(gap || note) && (
          <p className="mt-2 text-[12px] leading-snug text-ink-3">
            {gap && <span title="Companies with no quarter a year ago to compare with are left out of the base">{fmtCount(of)} with a year-ago quarter of {fmtCount(reported)} reported. </span>}
            {note}
          </p>
        )}
      </div>
      <div className="mt-3.5 flex items-center justify-between gap-2 text-[12.5px] text-ink-2">{foot}</div>
    </Panel>
  );
}

function MedianFoot({ value, noun, title }: { value: number | null; noun: string; title?: string }) {
  return (
    <>
      <span title={title}>Median<span className="hidden sm:inline"> {noun} growth</span></span>
      {value == null ? <span className="text-ink-3">—</span> : (
        <b className={cn("num whitespace-nowrap font-semibold", toneOf(value) === "down" ? "text-neg" : "text-pos")}>{value < 0 ? "▼" : "▲"} {fmtPct(value)}</b>
      )}
    </>
  );
}

/** "Is profit growth speeding up?": one bar split three ways and the counts under it. */
function SpeedingUp({ summary }: { summary: KpiSummary }) {
  const m = summary.momentum;
  const other = m.steady + m.not_comparable;
  const total = m.speeding_up + m.slowing + other;
  const pct = (n: number) => (total ? Math.round((n / total) * 100) : 0);
  const rows = [
    { n: m.speeding_up, label: "speeding up", icon: <ChevronsUp className="h-3.5 w-3.5" />, tone: "bg-pos-soft text-pos" },
    { n: m.slowing, label: "slowing", icon: <ChevronsDown className="h-3.5 w-3.5" />, tone: "bg-neg-soft text-neg" },
    { n: other, label: "steady or not comparable", icon: <Minus className="h-3.5 w-3.5" />, tone: "bg-surface text-ink-3" },
  ];
  return (
    <Panel className="px-[18px] sm:px-6 lg:col-span-5" title={
      <>Is profit growth speeding up? <span className="mt-0.5 block font-normal text-ink-3">This quarter's year-on-year profit growth compared with last quarter's (earnings acceleration); within ±2 points counts as steady.</span></>}>
      {total === 0 ? <p className="py-10 text-center text-[13px] text-ink-3">No company to compare yet.</p> : (
        <>
          <div className="mt-1 flex h-2.5 gap-[2px] overflow-hidden rounded-full" role="img"
            aria-label={`${m.speeding_up} speeding up, ${m.slowing} slowing, ${other} steady or not comparable`}>
            <i className="bg-pos" style={{ width: `${pct(m.speeding_up)}%` }} />
            <i className="bg-neg" style={{ width: `${pct(m.slowing)}%` }} />
            <i className="flex-1 bg-line-strong" />
          </div>
          <ul className="mt-4 grid gap-2.5">
            {rows.map((r) => (
              <li key={r.label} className="flex items-center gap-3 text-[14px]">
                <span aria-hidden className={cn("grid h-6 w-6 place-items-center rounded-md", r.tone)}>{r.icon}</span>
                <b className="num w-11 text-[17px] font-bold text-ink">{fmtCount(r.n)}</b>
                <span className="flex-1 text-ink-2">{r.label}</span>
                <span className="num text-[13px] text-ink-3">{pct(r.n)}%</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 border-t border-line pt-3 text-[12.5px] text-ink-3">
            Speeding up: PAT grew faster vs a year ago than it did last quarter. Shown for each company in the Momentum view.
          </p>
        </>
      )}
    </Panel>
  );
}

/** The top's shape while the numbers load, so nothing jumps when they arrive. */
function SeasonSkeleton() {
  return (
    <div className="mt-4 flex flex-col gap-3 sm:mt-7 lg:gap-4" aria-busy="true" aria-label="Loading the season's numbers">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        {[0, 1, 2, 3].map((i) => <Panel key={i}><Skeleton className="h-3 w-24" /><Skeleton className="mt-4 h-8 w-20" /><Skeleton className="mt-4 h-2" /><Skeleton className="mt-4 h-3 w-28" /></Panel>)}
      </div>
      <Panel><Skeleton className="h-3 w-40" /><Skeleton className="mt-5 h-7 w-4/5" /><div className="mt-5 grid gap-3 sm:grid-cols-2">{[0, 1].map((i) => <Skeleton key={i} className="h-8" />)}</div></Panel>
      <div className="flex flex-col gap-3 lg:grid lg:grid-cols-12 lg:gap-4">
        <Panel className="lg:col-span-7"><Skeleton className="h-3 w-48" /><Skeleton className="mt-6 h-[230px]" /></Panel>
        <Panel className="lg:col-span-5"><Skeleton className="h-3 w-48" /><Skeleton className="mt-6 h-2.5" /><Skeleton className="mt-6 h-[120px]" /></Panel>
      </div>
    </div>
  );
}
