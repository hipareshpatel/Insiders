import type { KpiSummary } from "../../../shared/resultsTypes";
import { cn } from "../../lib/cn";
import {
  barHeight, fmtPct, medianSlot, niceTicks, scaleX, sparkPath, spreadBins, stackWidths, type SpreadKey,
} from "../../lib/resultsView";

/** An 8-quarter line on a scale the caller shares across every line it is compared with. */
export function Spark({ vals, lo, hi, w = 84, h = 30, title, color = "var(--ink-2)", dot = "var(--ink)" }: {
  vals: (number | null)[]; lo: number; hi: number; w?: number; h?: number; title?: string; color?: string; dot?: string;
}) {
  const { d, last } = sparkPath(vals, w, h, lo, hi);
  const zeroY = lo < 0 && hi > 0 ? sparkPath([0], w, h, lo, hi).last?.[1] : undefined;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role={title ? "img" : undefined} aria-label={title} aria-hidden={title ? undefined : true}
      className="shrink-0 overflow-visible">
      {title && <title>{title}</title>}
      {zeroY != null && <line x1={0} x2={w} y1={zeroY} y2={zeroY} stroke="var(--line-strong)" strokeDasharray="2 3" />}
      {d && <path d={d} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />}
      {last && <circle cx={last[0]} cy={last[1]} r={3} fill={dot} />}
    </svg>
  );
}

const BAR_FILL: Record<SpreadKey, string> = { below_0: "bg-d-neg", from_0_to_10: "bg-d-1", from_10_to_20: "bg-d-2", above_20: "bg-d-3" };

/** Companies by profit growth: four bars (each a button that keeps that bar's companies), the middle company's mark under them, and
 *  loss-to-profit as a dashed bar apart (no per cent exists). Built in HTML so the bars are real buttons. */
export function Histogram({ summary, active, onPick, turnaround, onTurnaround, height = 190 }: {
  summary: KpiSummary; active: SpreadKey | null; onPick: (k: SpreadKey | null) => void;
  turnaround: boolean; onTurnaround: (on: boolean) => void; height?: number;
}) {
  const bins = spreadBins(summary.spread);
  const lp = summary.spread.loss_to_profit;
  const max = Math.max(1, ...bins.map((b) => b.n), lp);
  const slot = medianSlot(summary.median_pat_yoy);
  const plot = height - 30;   // room above the tallest bar for its count
  return (
    <div>
      <div className="flex items-end gap-0" style={{ height }}>
        <div className="relative flex h-full flex-1 items-end gap-1 border-b border-line-strong">
          {bins.map((b) => {
            const on = active === b.key;
            const h = barHeight(b.n, max, plot);
            return (
              <button key={b.key} type="button" aria-pressed={on} onClick={() => onPick(on ? null : b.key)}
                title={`${b.label}: ${b.n} ${b.n === 1 ? "company" : "companies"}${on ? " (showing only these; click to show all)" : " (click to show only these)"}`}
                className={cn("group relative flex h-full flex-1 flex-col items-center justify-end rounded-t-[5px] focus-visible:outline-offset-4",
                  active && !on && "opacity-45")}>
                <span className="num mb-2 text-[18px] font-bold text-ink">{b.n}</span>
                <span className={cn("block w-full rounded-[5px] rounded-b-none transition-[filter] group-hover:brightness-110", BAR_FILL[b.key],
                  on && "ring-2 ring-ink ring-offset-2 ring-offset-surface-2")} style={{ height: h }} />
              </button>
            );
          })}
        </div>
        <div className="mx-4 h-full w-px bg-line-strong" aria-hidden />
        <button type="button" aria-pressed={turnaround} onClick={() => onTurnaround(!turnaround)}
          title={`Loss to profit: ${lp} ${lp === 1 ? "company" : "companies"} (no % exists)${turnaround ? "; click to show all" : "; click to show only these"}`}
          className="flex h-full w-[52px] shrink-0 flex-col items-center justify-end">
          <span className="num mb-2 text-[18px] font-bold text-ink">{lp}</span>
          <span className={cn("block w-full rounded-[5px] border-[1.5px] border-dashed border-pos", turnaround && "bg-pos-soft ring-2 ring-ink ring-offset-2 ring-offset-surface-2")}
            style={{ height: Math.max(barHeight(lp, max, plot), lp > 0 ? 18 : 0) }} />
        </button>
      </div>
      <div className="flex">
        <div className="relative flex flex-1 gap-1">
          {bins.map((b) => <span key={b.key} className="flex-1 pt-1.5 text-center text-[12.5px] text-ink-2">{b.label}</span>)}
          {slot && (
            <span className="absolute top-6 flex -translate-x-1/2 flex-col items-center whitespace-nowrap text-[12.5px] text-ink"
              style={{ left: `${((slot.bin + slot.frac) / 4) * 100}%` }}>
              <span aria-hidden className="text-[10px] leading-none">▲</span>
              <span>Median <b className="num">{fmtPct(summary.median_pat_yoy)}</b></span>
            </span>
          )}
        </div>
        <span className="mx-4 w-px" aria-hidden />
        <span className="w-[52px] pt-1.5 text-center text-[12.5px] leading-tight text-ink-2">Loss → profit</span>
      </div>
      <div className={slot ? "h-10" : "h-3"} />
    </div>
  );
}

/** Profit growth last quarter (hollow) to this quarter (filled), on one scale shared by every row. */
export function Dumbbell({ was, now, lo, hi, w = 230, h = 28 }: { was: number; now: number; lo: number; hi: number; w?: number; h?: number }) {
  const a = scaleX(was, lo, hi, 8, w - 8), b = scaleX(now, lo, hi, 8, w - 8), y = h / 2;
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" className="max-w-[230px] overflow-visible"
      aria-label={`Profit growth ${fmtPct(was)} last quarter, ${fmtPct(now)} this quarter`}>
      <line x1={8} x2={w - 8} y1={y} y2={y} stroke="var(--line)" />
      <line x1={a} x2={b} y1={y} y2={y} stroke="var(--ink-3)" strokeWidth={2} />
      <circle cx={a} cy={y} r={4.5} fill="var(--surface)" stroke="var(--ink-2)" strokeWidth={1.5} />
      <circle cx={b} cy={y} r={5} fill="var(--accent)" stroke="var(--surface)" strokeWidth={2} />
    </svg>
  );
}

/** Growth against a year ago over 8 quarters, profit and revenue, with the end values written beside the last points. */
export function LineChart({ series, labels, w = 424, h = 230 }: {
  series: { name: string; vals: (number | null)[]; color: string }[]; labels: string[]; w?: number; h?: number;
}) {
  const all = series.flatMap((s) => s.vals.filter((v): v is number => v != null));
  if (!all.length) return <p className="py-8 text-center text-[13px] text-ink-3">No per cent growth in these quarters (a loss in the year-ago quarter).</p>;
  let lo = Math.min(0, ...all), hi = Math.max(0, ...all);
  const pad = (hi - lo || 10) * 0.12;
  if (lo < 0) lo -= pad;
  hi += pad;
  const L = 36, R = 118, T = 12, B = 26, n = Math.max(1, labels.length - 1);
  const xs = (i: number) => L + (i * (w - L - R)) / n;
  const ys = (v: number) => T + ((hi - v) / (hi - lo)) * (h - T - B);
  const ticks = niceTicks(lo, hi, 4);
  const ends = series.map((s) => ({ s, v: s.vals[s.vals.length - 1] })).filter((e): e is { s: typeof e.s; v: number } => e.v != null)
    .map((e) => ({ y: ys(e.v), text: fmtPct(e.v), name: e.s.name.toLowerCase() })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 18) ends[i].y = ends[i - 1].y + 18;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" role="img" aria-label={`Growth against a year ago, ${labels[0]} to ${labels[labels.length - 1]}`}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={w - R} y1={ys(t)} y2={ys(t)} stroke={t === 0 ? "var(--line-strong)" : "var(--line)"} />
          <text x={L - 8} y={ys(t) + 4} textAnchor="end" fontSize={11} fill="var(--ink-3)">{`${t}%`}</text>
        </g>
      ))}
      {labels.map((q, i) => (i % 2 === 1 || i === labels.length - 1) && (
        <text key={q + i} x={xs(i)} y={h - 6} textAnchor="middle" fontSize={11} fill="var(--ink-3)">{q}</text>
      ))}
      {series.map((s) => {
        const { d } = sparkPathOn(s.vals, xs, ys);
        return (
          <g key={s.name}>
            <path d={d} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            {s.vals.map((v, i) => v != null && (
              <circle key={i} cx={xs(i)} cy={ys(v)} r={i === s.vals.length - 1 ? 4 : 2.5} fill={s.color} stroke="var(--surface)" strokeWidth={1.5}>
                <title>{`${s.name}, ${labels[i]}: ${fmtPct(v)}`}</title>
              </circle>
            ))}
          </g>
        );
      })}
      {ends.map((e) => (
        <text key={e.name} x={xs(labels.length - 1) + 10} y={e.y + 4} fontSize={12.5} fontWeight={700} fill="var(--ink)">
          {e.text} <tspan fontWeight={400} fill="var(--ink-2)">{e.name}</tspan>
        </text>
      ))}
    </svg>
  );
}

function sparkPathOn(vals: (number | null)[], xs: (i: number) => number, ys: (v: number) => number) {
  let d = "", on = false;
  vals.forEach((v, i) => {
    if (v == null) { on = false; return; }
    d += `${on ? "L" : "M"}${xs(i).toFixed(1)} ${ys(v).toFixed(1)} `;
    on = true;
  });
  return { d: d.trim() };
}

const STACK = ["bg-d-neg text-white", "bg-d-1 text-[#0b1a12]", "bg-d-2 text-white", "bg-d-3 text-white"];
const BANDS = ["Below 0%", "0–10%", "10–20%", "Above 20%"];

/** A group's spread of profit growth as one bar of four bands; a band wide enough carries its share. */
export function SpreadStack({ pct }: { pct: [number, number, number, number] }) {
  const widths = stackWidths(pct);
  const tip = BANDS.map((b, i) => `${b}: ${Math.round(pct[i])}%`).join(", ");
  if (!widths.some((x) => x > 0)) return <span className="text-ink-3">—</span>;
  return (
    <div role="img" aria-label={`Profit growth spread: ${tip}`} title={tip} className="ml-auto flex h-[22px] w-full max-w-[160px] gap-0.5">
      {widths.map((wd, i) => wd > 0 && (
        <span key={i} style={{ flexGrow: wd, flexBasis: 0 }}
          className={cn("num grid min-w-[6px] place-items-center rounded-[3px] text-[11px] font-bold first:rounded-l-md last:rounded-r-md", STACK[i])}>
          {pct[i] >= 15 ? Math.round(pct[i]) : ""}
        </span>
      ))}
    </div>
  );
}
