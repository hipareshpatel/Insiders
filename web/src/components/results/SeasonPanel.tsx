import { ArrowRight, ChartColumn, ChevronsDown, ChevronsUp, IndianRupee, Minus, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import type { GroupRow, KpiProgress, KpiSummary } from "../../../shared/resultsTypes";
import { cn } from "../../lib/cn";
import { fmtPct, indexLabel, progressText, seasonHeadline, seasonLines, toneOf, type SpreadKey } from "../../lib/resultsView";
import { Panel, Segs, Skeleton } from "./bits";
import { Histogram } from "./charts";

/** The top of the Companies tab (owner, 31 Oct 2026: Design E's crafted elements, keeping "What this list says"): four tiles (revenue, EBITDA
 *  and PAT up, loss to profit) with each median, the index's reporting progress, the season's words, the spread of PAT growth and whether
 *  profit growth is speeding up. Every number comes from the API's summary of the filtered set; the words also read the groups by index. */
export function SeasonPanel({ summary, progress, quarter: _quarter, indexRows, filtered, spread, turnaround, onSpread, onTurnaround }: {
  summary: KpiSummary | undefined; progress: KpiProgress | null | undefined; quarter: string | null; indexRows: GroupRow[] | undefined;
  filtered: boolean; spread: SpreadKey | null; turnaround: boolean; onSpread: (k: SpreadKey | null) => void; onTurnaround: (on: boolean) => void;
}) {
  if (!summary) return <SeasonSkeleton />;
  const lines = seasonLines(summary, indexRows);
  return (
    <div className="mt-4 flex flex-col gap-3 sm:mt-7 lg:gap-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-[repeat(4,minmax(0,1fr))_minmax(0,1.35fr)] lg:gap-4">
        <Tile icon={<IndianRupee className="h-3.5 w-3.5" />} label="Revenue up" up={summary.revenue_up} of={summary.revenue_of}
          foot={<MedianFoot value={summary.median_revenue_yoy} />} />
        <Tile icon={<ChartColumn className="h-3.5 w-3.5" />} label="EBITDA up" up={summary.ebitda_up} of={summary.ebitda_of}
          foot={<MedianFoot value={summary.median_ebitda_yoy} />} />
        <Tile icon={<TrendingUp className="h-3.5 w-3.5" />} label="PAT up" up={summary.pat_up} of={summary.pat_of}
          foot={<MedianFoot value={summary.median_pat_yoy} />} />
        <Tile icon={<ArrowRight className="h-3.5 w-3.5" />} label="Loss to profit" up={summary.loss_to_profit} of={summary.n}
          foot={<span className="text-ink-3">No % exists</span>} />
        <Progress progress={progress} />
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
            <span>Spread of PAT growth <span className="block font-normal text-ink-3 sm:inline"><span className="hidden sm:inline">· </span>{summary.n} {summary.n === 1 ? "company" : "companies"} · profit this quarter vs a year ago</span></span>
            <span className="flex gap-3 text-[12px] font-normal text-ink-2">
              <span><i aria-hidden className="mr-1 inline-block h-2 w-2 rounded-[2px] bg-neg align-[1px]" />Fell</span>
              <span><i aria-hidden className="mr-1 inline-block h-2 w-2 rounded-[2px] bg-pos align-[1px]" />Grew</span>
            </span>
          </span>}>
          {summary.n === 0 ? <p className="py-16 text-center text-[13px] text-ink-3">No company to chart yet.</p> : (
            <>
              <Histogram summary={summary} active={spread} onPick={onSpread} turnaround={turnaround} onTurnaround={onTurnaround} />
              <p className="text-[12.5px] text-ink-3">
                {summary.spread.with_pct} {summary.spread.with_pct === 1 ? "company has" : "companies have"} a % change; the {summary.spread.loss_to_profit} that
                turned a loss into a profit{summary.spread.loss_narrowed ? ` and ${summary.spread.loss_narrowed} whose loss narrowed` : ""} sit apart and are left
                out of the median. Click a bar to list its companies.
              </p>
            </>
          )}
        </Panel>
        <SpeedingUp summary={summary} />
      </div>
    </div>
  );
}

/** One tile: how many grew out of how many, a 20-step bar, and what sits under it (the median, or why there is none). */
function Tile({ icon, label, up, of, foot }: { icon: ReactNode; label: string; up: number; of: number; foot: ReactNode }) {
  const pct = of ? Math.round((up / of) * 100) : 0;
  const filled = Math.round(pct / 5);
  return (
    <Panel className="flex flex-col justify-between px-4 py-4 sm:px-5">
      <div>
        <div className="flex items-center gap-1.5 text-[13px] font-semibold text-ink-2">
          <span aria-hidden className="grid h-6 w-6 place-items-center rounded-md bg-surface text-ink-2">{icon}</span>{label}
        </div>
        <div className="num mt-3 flex items-baseline gap-1.5">
          <span className="text-[28px] font-bold leading-none tracking-[-0.02em] text-ink sm:text-[32px]">{up}</span>
          <span className="text-[13px] text-ink-3">of {of} · {pct}%</span>
        </div>
        <div className="mt-3 flex gap-[2px]" role="img" aria-label={`${up} of ${of}, ${pct}%`}>
          {Array.from({ length: 20 }, (_, i) => <i key={i} className={cn("h-2 flex-1 rounded-[1px]", i < filled ? "bg-pos" : "bg-line")} />)}
        </div>
      </div>
      <div className="mt-3.5 flex items-center justify-between gap-2 text-[12.5px] text-ink-2">{foot}</div>
    </Panel>
  );
}

function MedianFoot({ value }: { value: number | null }) {
  return (
    <>
      <span>Median<span className="hidden sm:inline"> growth</span></span>
      {value == null ? <span className="text-ink-3">—</span> : (
        <b className={cn("num whitespace-nowrap font-semibold", toneOf(value) === "down" ? "text-neg" : "text-pos")}>{value < 0 ? "▼" : "▲"} {fmtPct(value)}</b>
      )}
    </>
  );
}

/** "185 / 497 Nifty 500 reported" with a ring, and the next board meeting for results. */
function Progress({ progress }: { progress: KpiProgress | null | undefined }) {
  if (!progress) {
    return (
      <Panel className="col-span-2 flex flex-col justify-center px-4 py-4 sm:px-5 lg:col-span-1" title="Reporting progress">
        <p className="text-[13.5px] text-ink-2">Index members are not loaded yet, so progress against an index is not shown.</p>
      </Panel>
    );
  }
  const name = indexLabel(progress.index_id);
  const t = progressText(progress);
  const pct = progress.of ? Math.min(100, Math.round((progress.reported / progress.of) * 100)) : 0;
  const r = 22, c = 2 * Math.PI * r;
  const next = progress.still_to_come ? calendarDay(progress.still_to_come.date) : null;
  return (
    <Panel className="col-span-2 flex flex-col justify-between px-4 py-4 sm:px-5 lg:col-span-1">
      <div className="flex items-center gap-3.5">
        <svg width="58" height="58" viewBox="0 0 58 58" role="progressbar" aria-valuemin={0} aria-valuemax={progress.of} aria-valuenow={progress.reported}
          aria-label={`${name} companies reported`} className="shrink-0 -rotate-90">
          <circle cx="29" cy="29" r={r} fill="none" stroke="var(--line)" strokeWidth="5" />
          <circle cx="29" cy="29" r={r} fill="none" stroke="var(--accent)" strokeWidth="5" strokeLinecap="round" strokeDasharray={`${(pct / 100) * c} ${c}`} />
          <text x="29" y="29" textAnchor="middle" dominantBaseline="central" transform="rotate(90 29 29)" fill="var(--ink)"
            style={{ font: "700 13px var(--font-sans)" }}>{pct}%</text>
        </svg>
        <div className="min-w-0">
          <div className="num"><span className="text-[26px] font-bold leading-none tracking-[-0.02em] text-ink">{progress.reported}</span>
            <span className="text-[15px] font-semibold text-ink-3"> / {progress.of}</span></div>
          <div className="mt-1 text-[13px] text-ink-2">{name} reported</div>
        </div>
      </div>
      {t.note && <div className="mt-2 text-[12px] text-ink-3">{t.note}</div>}
      <div className="mt-3 flex items-center gap-3 border-t border-line pt-3 text-[13px]">
        {next ? (
          <>
            <span aria-hidden className="grid w-9 shrink-0 overflow-hidden rounded-md border border-line text-center leading-none">
              <span className="bg-accent py-[3px] text-[9px] font-bold text-white">{next.month}</span>
              <span className="pt-1 text-[15px] font-bold text-ink">{next.day}</span>
              <span className="pb-1 text-[8.5px] font-semibold text-ink-3">{next.weekday}</span>
            </span>
            <span className="min-w-0"><span className="block text-ink-3">Still to come</span>
              <b className="font-semibold text-ink">{next.label}</b> <span className="text-ink-2">· {t.next}</span></span>
          </>
        ) : <span className="text-ink-3">Still to come: dates not known</span>}
      </div>
    </Panel>
  );
}

/** A meeting day as the calendar badge reads it: NOV / 3 / TUE, and "Tue 3 Nov". */
function calendarDay(day: string): { month: string; day: string; weekday: string; label: string } | null {
  const d = new Date(`${day}T12:00:00+05:30`);
  if (Number.isNaN(d.getTime())) return null;
  const part = (o: Intl.DateTimeFormatOptions) => d.toLocaleDateString("en-GB", { timeZone: "Asia/Kolkata", ...o });
  return { month: part({ month: "short" }).toUpperCase(), day: part({ day: "numeric" }), weekday: part({ weekday: "short" }).toUpperCase(),
    label: `${part({ weekday: "short" })} ${part({ day: "numeric" })} ${part({ month: "short" })}` };
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
      <>Is profit growth speeding up? <span className="mt-0.5 block font-normal text-ink-3">This quarter's growth vs last quarter's, both vs a year ago</span></>}>
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
                <b className="num w-11 text-[17px] font-bold text-ink">{r.n}</b>
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
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-[repeat(4,minmax(0,1fr))_minmax(0,1.35fr)] lg:gap-4">
        {[0, 1, 2, 3].map((i) => <Panel key={i}><Skeleton className="h-3 w-24" /><Skeleton className="mt-4 h-8 w-20" /><Skeleton className="mt-4 h-2" /><Skeleton className="mt-4 h-3 w-28" /></Panel>)}
        <Panel className="col-span-2 lg:col-span-1"><Skeleton className="h-14 w-40" /><Skeleton className="mt-5 h-8" /></Panel>
      </div>
      <Panel><Skeleton className="h-3 w-40" /><Skeleton className="mt-5 h-7 w-4/5" /><div className="mt-5 grid gap-3 sm:grid-cols-2">{[0, 1].map((i) => <Skeleton key={i} className="h-8" />)}</div></Panel>
      <div className="flex flex-col gap-3 lg:grid lg:grid-cols-12 lg:gap-4">
        <Panel className="lg:col-span-7"><Skeleton className="h-3 w-48" /><Skeleton className="mt-6 h-[230px]" /></Panel>
        <Panel className="lg:col-span-5"><Skeleton className="h-3 w-48" /><Skeleton className="mt-6 h-2.5" /><Skeleton className="mt-6 h-[120px]" /></Panel>
      </div>
    </div>
  );
}
