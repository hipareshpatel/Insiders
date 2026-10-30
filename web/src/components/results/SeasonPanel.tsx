import { INDICES, type GroupRow, type KpiProgress, type KpiSummary } from "../../../shared/resultsTypes";
import { cn } from "../../lib/cn";
import {
  fmtPct, indexLabel, meetingDay, progressText, quarterSeries, seasonHeadline, seasonLines, sharedScale, toneOf, type SpreadKey,
} from "../../lib/resultsView";
import { Panel, Segs, Skeleton } from "./bits";
import { Histogram, Spark } from "./charts";

/** "What the season says": the headline and its lines, reporting progress, the spread of profit growth, the middle company's
 *  figures and the indices' 8-quarter trends. Every number comes from the API's summary of the filtered set and the groups by index. */
export function SeasonPanel({ summary, progress, quarter, indexRows, filtered, spread, turnaround, onSpread, onTurnaround }: {
  summary: KpiSummary | undefined; progress: KpiProgress | null | undefined; quarter: string | null; indexRows: GroupRow[] | undefined;
  filtered: boolean; spread: SpreadKey | null; turnaround: boolean; onSpread: (k: SpreadKey | null) => void; onTurnaround: (on: boolean) => void;
}) {
  if (!summary) return <SeasonSkeleton />;
  const lines = seasonLines(summary, indexRows);
  const labels = quarterSeries(quarter);
  return (
    <div className="mt-4 flex flex-col gap-3 sm:mt-7 lg:grid lg:grid-cols-12 lg:gap-4">
      <Panel className="px-[18px] py-5 sm:px-7 sm:py-[26px] lg:col-span-9" title={filtered ? "What this list says" : "What the season says so far"}>
        <p className="max-w-[820px] text-[21px] font-semibold leading-[1.28] tracking-[-0.015em] text-ink sm:text-[26px]">
          <Segs segs={seasonHeadline(summary, filtered)} />
        </p>
        {lines.length > 0 && (
          <ul className="mt-[18px] grid gap-x-7 gap-y-2.5 sm:grid-cols-2">
            {lines.map((l, i) => (
              <li key={i} className={cn("relative pl-4 text-[14.5px] text-ink-2 before:absolute before:left-0 before:top-[0.62em] before:h-1.5 before:w-1.5 before:rounded-[2px] before:bg-line-strong",
                i >= 2 && "hidden sm:list-item")}>
                <Segs segs={l} />
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Progress progress={progress} />

      <Panel className="px-[18px] sm:px-6 lg:col-span-5" title={<>How much did profit grow? <span className="font-normal text-ink-2">· companies by profit growth vs a year ago</span></>}>
        {summary.n === 0 ? <p className="py-16 text-center text-[13px] text-ink-3">No company to chart yet.</p> : (
          <>
            <Histogram summary={summary} active={spread} onPick={onSpread} turnaround={turnaround} onTurnaround={onTurnaround} />
            <p className="text-[12.5px] text-ink-3">
              {summary.spread.with_pct} {summary.spread.with_pct === 1 ? "company" : "companies"} with a % change, plus {summary.spread.loss_to_profit} that
              turned a loss into a profit{summary.spread.loss_narrowed ? ` and ${summary.spread.loss_narrowed} whose loss narrowed` : ""} (no % exists, so kept
              apart). Bars are counts; click one to list its companies.
            </p>
          </>
        )}
      </Panel>

      <Panel className="grid grid-cols-3 gap-2.5 px-[18px] sm:px-6 lg:col-span-3 lg:flex lg:flex-col lg:gap-[18px]">
        <h2 className="col-span-3 text-[13px] font-semibold text-ink-2">Median growth</h2>
        <Median big value={summary.median_pat_yoy} label="Profit" up={summary.pat_up} of={summary.pat_of}
          extra={summary.loss_to_profit ? `, ${summary.loss_to_profit} of them from a loss` : ""} />
        <Median value={summary.median_ebitda_yoy} label="EBITDA" up={summary.ebitda_up} of={summary.ebitda_of} />
        <Median value={summary.median_revenue_yoy} label="Revenue" up={summary.revenue_up} of={summary.revenue_of} />
      </Panel>

      <Panel className="px-[18px] sm:px-6 lg:col-span-4" title="Median profit growth, by index">
        <IndexTrends rows={indexRows} labels={labels} />
      </Panel>
    </div>
  );
}

function Median({ value, label, up, of, extra = "", big = false }: { value: number | null; label: string; up: number; of: number; extra?: string; big?: boolean }) {
  return (
    <div>
      <div className={cn("num font-bold leading-[1.05] tracking-[-0.02em] text-ink", big ? "text-[22px] lg:text-[44px]" : "text-[22px] lg:text-[30px]")}>
        {value == null ? <span className="text-ink-3">—</span> : (
          <>
            <span aria-hidden className={cn("relative -top-[0.5em] mr-1.5 text-[0.42em]", toneOf(value) === "down" ? "text-neg" : "text-pos")}>{value < 0 ? "▼" : "▲"}</span>
            {fmtPct(value)}
          </>
        )}
      </div>
      <div className="mt-1 text-[13px] text-ink-2 lg:text-[13.5px]">
        {label} · <b className="num font-semibold text-ink">{up}</b><span className="hidden lg:inline"> of {of}</span> grew<span className="hidden lg:inline">{extra}</span>
      </div>
    </div>
  );
}

function Progress({ progress }: { progress: KpiProgress | null | undefined }) {
  if (!progress) {
    return (
      <Panel className="flex flex-col justify-between lg:col-span-3" title="Reporting progress">
        <p className="text-[14px] text-ink-2">Index members are not loaded yet, so progress against an index is not shown.</p>
      </Panel>
    );
  }
  const name = indexLabel(progress.index_id);
  const t = progressText(progress);
  const pctDone = progress.of ? Math.min(100, (progress.reported / progress.of) * 100) : 0;
  return (
    <Panel className="flex flex-col justify-between px-[18px] sm:px-6 lg:col-span-3">
      <div>
        <h2 className="mb-3 text-[13px] font-semibold text-ink-2">{name} reporting progress</h2>
        <div className="num"><span className="text-[34px] font-bold leading-none tracking-[-0.02em] text-ink">{progress.reported}</span>
          <span className="text-[20px] font-semibold text-ink-3"> / {progress.of}</span></div>
        <div className="mt-1.5 text-[14px] text-ink-2">{name} companies have reported</div>
        <div className="mb-2.5 mt-3.5 h-2 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuemin={0} aria-valuemax={progress.of}
          aria-valuenow={progress.reported} aria-label={`${name} companies reported`}>
          <i className="block h-full rounded-full bg-accent" style={{ width: `${pctDone}%` }} />
        </div>
        <div className="text-[13px] text-ink-3">{t.done}</div>
      </div>
      <div className="mt-3.5 flex items-center justify-between gap-2 border-t border-line pt-3.5 text-[14px]">
        <span className="text-ink-2">Still to come</span>
        {progress.still_to_come ? (
          <span className="text-right"><b className="font-semibold text-ink">{meetingDay(progress.still_to_come.date)}</b> <span className="text-ink-2">· {t.next}</span></span>
        ) : <span className="text-ink-3">dates not known</span>}
      </div>
    </Panel>
  );
}

function IndexTrends({ rows, labels }: { rows: GroupRow[] | undefined; labels: string[] }) {
  if (!rows) {
    return (
      <div className="grid grid-cols-2 gap-x-5 gap-y-3">
        {Array.from({ length: 8 }, (_, i) => <div key={i}><Skeleton className="h-3 w-20" /><Skeleton className="mt-2 h-6 w-full" /></div>)}
      </div>
    );
  }
  const order = (id: string) => { const i = INDICES.findIndex((x) => x.id === id); return i < 0 ? 99 : i; };
  const shown = rows.filter((r) => r.pat_median != null || r.trend_pat_median.some((v) => v != null))
    .sort((a, b) => order(a.id) - order(b.id)).slice(0, 8);
  if (!shown.length) return <p className="py-8 text-[13px] text-ink-3">No index has a median yet: no company with a per cent change.</p>;
  const [lo, hi] = sharedScale(shown.map((r) => r.trend_pat_median));
  const lead = [...shown].filter((r) => r.pat_median != null).sort((a, b) => b.pat_median! - a.pat_median!)[0];
  return (
    <>
      <div className="grid grid-cols-2 gap-x-3.5 gap-y-2.5 sm:gap-x-5 sm:gap-y-3">
        {shown.map((r) => (
          <div key={r.id} className="min-w-0">
            <div className="truncate text-[12.5px] text-ink-2">{r.label}</div>
            <div className="flex items-end justify-between gap-2">
              <span className={cn("num text-[17px] font-bold tracking-[-0.01em] sm:text-[19px]", r === lead ? "text-pos" : "text-ink")}>{fmtPct(r.pat_median)}</span>
              <Spark vals={r.trend_pat_median} lo={lo} hi={hi} w={78} h={28}
                title={`${r.label}: ${r.trend_pat_median.map((v, i) => `${labels[i]} ${fmtPct(v)}`).join(", ")}`} />
            </div>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[12.5px] text-ink-3">Lines: last 8 quarters, {labels[0]} to {labels[labels.length - 1]}, same scale for all.</p>
    </>
  );
}

/** The season block's shape while the numbers load, so nothing jumps when they arrive. */
function SeasonSkeleton() {
  return (
    <div className="mt-4 flex flex-col gap-3 sm:mt-7 lg:grid lg:grid-cols-12 lg:gap-4" aria-busy="true" aria-label="Loading the season's numbers">
      <Panel className="lg:col-span-9"><Skeleton className="h-3 w-40" /><Skeleton className="mt-5 h-7 w-4/5" /><Skeleton className="mt-2 h-7 w-1/2" />
        <div className="mt-6 grid gap-3 sm:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-9" />)}</div></Panel>
      <Panel className="lg:col-span-3"><Skeleton className="h-3 w-32" /><Skeleton className="mt-4 h-9 w-28" /><Skeleton className="mt-6 h-2" /><Skeleton className="mt-10 h-4" /></Panel>
      <Panel className="lg:col-span-5"><Skeleton className="h-3 w-48" /><Skeleton className="mt-6 h-[230px]" /></Panel>
      <Panel className="lg:col-span-3"><Skeleton className="h-3 w-32" /><Skeleton className="mt-6 h-12 w-36" /><Skeleton className="mt-6 h-9 w-28" /><Skeleton className="mt-6 h-9 w-28" /></Panel>
      <Panel className="lg:col-span-4"><Skeleton className="h-3 w-48" /><Skeleton className="mt-6 h-[230px]" /></Panel>
    </div>
  );
}
