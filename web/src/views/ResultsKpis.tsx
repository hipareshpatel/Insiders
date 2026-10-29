import { cn } from "../lib/cn";
import type { ReportingQuarter } from "../../shared/resultsCalendar";
import type { Move, ResultsSummary } from "../../shared/resultsSummary";

const dayLabel = (day: string) => new Date(`${day}T00:00:00+05:30`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
const monthSpan = (q: ReportingQuarter) => `${dayLabel(q.from)} to ${dayLabel(q.to)}`;

/** The quarters the calendar offers, as chips: the reporting one first, marked open while its results are still being declared. */
export function QuarterChips({ quarters, value, onChange }: { quarters: ReportingQuarter[]; value: string; onChange: (period: string) => void }) {
  return (
    <div role="radiogroup" aria-label="Quarter" className="flex gap-2 overflow-x-auto pb-1">
      {quarters.map((q) => {
        const on = q.period === value;
        return (
          <button key={q.period} type="button" role="radio" aria-checked={on} onClick={() => onChange(q.period)}
            className={cn("min-w-[9.5rem] shrink-0 rounded-xl border px-3.5 py-2.5 text-left transition",
              on ? "border-accent bg-accent-soft text-ink shadow-[0_1px_0_var(--accent-line)]" : "border-line bg-surface text-ink-2 hover:border-line-strong hover:text-ink")}>
            <span className="flex items-center gap-2">
              <span className="font-display text-[17px] leading-none">{q.label}</span>
              {q.current && <span className="rounded-full bg-pos-soft px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-pos">Open</span>}
            </span>
            <span className="mt-1 block text-[11.5px] text-ink-3">Declared {monthSpan(q)}</span>
          </button>
        );
      })}
    </div>
  );
}

function Tile({ label, value, sub, tone }: { label: string; value: number | string; sub?: string; tone?: "pos" | "neg" }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="eyebrow text-ink-3">{label}</div>
      <div className={cn("num mt-2 font-display text-[30px] leading-none", tone === "pos" ? "text-pos" : tone === "neg" ? "text-neg" : "text-ink")}>{value}</div>
      {sub && <div className="mt-1.5 text-[12px] text-ink-3">{sub}</div>}
    </div>
  );
}

/** Share of the comparable rows that moved up: the tile's figure, and its sub-line. */
const comparable = (m: Record<Move, number>) => m.up + m.down + m.flat;
const shareUp = (m: Record<Move, number>) => (comparable(m) ? `${Math.round((m.up / comparable(m)) * 100)}%` : "—");
const shareLine = (m: Record<Move, number>) => (comparable(m) ? `${m.up} up of ${comparable(m)} comparable` : "no year-ago figures yet");

/** The KPI strip for the rows on screen: counts follow the quarter and the filters. `pending`: some companies' figures are still loading. */
export function ResultsKpis({ calendar, summary, pending }: { calendar: ReportingQuarter; summary: ResultsSummary; pending: boolean }) {
  const { matrix } = summary;
  const cell = (sales: "up" | "down", profit: "up" | "down") => {
    const n = matrix[sales][profit];
    const good = sales === "up" && profit === "up" ? "bg-pos-soft text-pos" : sales === "down" && profit === "down" ? "bg-neg-soft text-neg" : "bg-warn-soft text-warn";
    return <div className={cn("grid place-items-center rounded-lg py-3 font-display text-[22px] leading-none", good)}>{n}</div>;
  };
  return (
    <section aria-label={`${calendar.label} results at a glance`} className="rounded-2xl border border-line bg-surface p-4 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-[20px] text-ink">{calendar.label} at a glance</h2>
        <span className="text-[12px] text-ink-3">{pending ? "Counting…" : `Results declared ${monthSpan(calendar)}`}</span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="Results declared" value={summary.declared} sub={summary.notComparable ? `${summary.notComparable} with no year-ago figure` : "all comparable"} />
        <Tile label="Profit growth" value={shareUp(summary.profit)} sub={shareLine(summary.profit)} tone="pos" />
        <Tile label="Sales growth" value={shareUp(summary.sales)} sub={shareLine(summary.sales)} tone="pos" />
        <Tile label="Margin expanded" value={summary.margin.up} sub={`${summary.margin.down} contracted`} />
      </div>
      <div className="mt-5">
        <div className="eyebrow mb-2 text-ink-3">Sales against profit</div>
        <div className="grid grid-cols-[minmax(5.5rem,auto)_1fr_1fr] gap-2 text-center text-[12px] text-ink-3">
          <span />
          <span>Profit up</span>
          <span>Profit down</span>
          <span className="self-center text-left">Sales up</span>
          {cell("up", "up")}
          {cell("up", "down")}
          <span className="self-center text-left">Sales down</span>
          {cell("down", "up")}
          {cell("down", "down")}
        </div>
      </div>
    </section>
  );
}
