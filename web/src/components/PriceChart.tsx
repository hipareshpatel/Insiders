import { useMemo, useState } from "react";
import type { CardRow, CompanyDetail } from "../../shared/types";
import { cn } from "../lib/cn";
import { placeFilings, rangeMove, type Series } from "../lib/chart";
import { istDate, signClass } from "../lib/format";

const W = 1000, H = 220;   // the drawing's own units; it stretches to the plot's box
// trading days; 3Y is offered only when the series is longer than a year (market-data stores a year today)
const RANGES = { "1M": 21, "3M": 63, "6M": 125, "1Y": 250, "3Y": 750 } as const;
type Range = keyof typeof RANGES;
// a low-impact dot in the muted ink, which stays visible on the dark surface (design audit 2026-10-20)
export const IMPACT_DOT: Record<string, string> = {
  HIGH: "var(--impact-high)", MODERATE: "var(--impact-moderate)", LOW: "color-mix(in srgb, var(--ink-3) 70%, var(--surface))",
};
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Where the axis is labelled: months (years on 3Y, weeks on 1M), at most about six. */
function ticks(d: string[], range: Range): { i: number; label: string }[] {
  if (range === "1M") return d.flatMap((day, i) => (i % 5 === 0 ? [{ i, label: `${Number(day.slice(8, 10))} ${MONTHS[Number(day.slice(5, 7)) - 1]}` }] : []));
  const out: { i: number; label: string }[] = [];
  for (let i = 1; i < d.length; i++) {
    if (d[i].slice(0, 7) === d[i - 1].slice(0, 7)) continue;
    if (range === "3Y" ? d[i].slice(5, 7) === "01" : true) out.push({ i, label: range === "3Y" ? d[i].slice(0, 4) : MONTHS[Number(d[i].slice(5, 7)) - 1] });
  }
  const step = Math.ceil(out.length / 6);
  return out.filter((_, k) => k % step === 0);
}

/** Daily closes with each analysed filing marked on its trading day (market-data writes the series). A dot opens its
 *  card on this page through `onOpen`. */
export function PriceChart({ chart, cards, onOpen }: { chart: CompanyDetail["chart"]; cards: CardRow[]; onOpen?: (newsId: string) => void }) {
  const [range, setRange] = useState<Range>("1Y");
  const [hover, setHover] = useState<number | null>(null);
  const [dot, setDot] = useState<number | null>(null);
  const shown: Series | null = useMemo(() => {
    if (!chart) return null;
    const n = Math.min(chart.d.length, chart.c.length), from = Math.max(0, n - RANGES[range]);
    return { d: chart.d.slice(from, n), c: chart.c.slice(from, n) };
  }, [chart, range]);
  if (!chart || !shown || shown.c.length < 5) return null;
  const offered = (Object.keys(RANGES) as Range[]).filter((r) => r !== "3Y" || chart.c.length > RANGES["1Y"] + 10);

  const min = Math.min(...shown.c), max = Math.max(...shown.c);
  const pad = (max - min || max || 1) * 0.06;   // room above and below, so the line never runs into a label
  const lo = min - pad, hi = max + pad;
  const x = (i: number) => (i / Math.max(1, shown.c.length - 1)) * W;
  const y = (v: number) => (1 - (v - lo) / (hi - lo)) * H;
  const line = shown.c.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const area = `${line}L${W},${H}L0,${H}Z`;
  const move = rangeMove(shown);
  const filings = placeFilings(shown, cards);
  const at = hover ?? shown.c.length - 1;
  const grid = [0, 1, 2, 3].map((k) => min + (k / 3) * (max - min));
  const axis = ticks(shown.d, range);
  const tip = dot != null ? filings.find((f) => f.index === dot) : null;
  const digits = max < 100 ? 2 : 0;

  return (
    <section className="card-soft rise-in min-w-0 px-5 pb-4 pt-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[16px] font-extrabold leading-tight tracking-tight text-ink">Price
          <small className="ml-1.5 text-[12.5px] font-semibold text-ink-3">dots are filings with a card</small></h2>
        <span className="inline-flex rounded-[11px] bg-surface-2 p-[3px]" role="radiogroup" aria-label="Range">
          {offered.map((r) => (
            <button key={r} type="button" role="radio" aria-checked={range === r} onClick={() => { setRange(r); setHover(null); setDot(null); }}
              className={cn("num rounded-lg px-2.5 py-1 text-[12px] font-bold", range === r ? "bg-surface text-ink shadow-sm" : "text-ink-3")}>{r}</button>
          ))}
        </span>
      </header>
      <p className="num mt-1 text-[12.5px] text-ink-3">
        {istDate(shown.d[at])} · <span className="font-bold text-ink">₹{shown.c[at].toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        {hover == null && move != null && <> · <span className={cn("font-semibold", signClass(move))}>{move > 0 ? "+" : ""}{move.toFixed(1)}% over {range}</span></>}
      </p>
      <div className="relative mt-2 h-[210px] w-full sm:h-[240px]">
        {/* the price axis in its own gutter, the month axis under the plot */}
        {grid.map((v) => (
          <span key={v} className="num pointer-events-none absolute left-0 w-[40px] -translate-y-1/2 text-right text-[10.5px] text-ink-3"
            style={{ top: `calc(6px + (100% - 28px) * ${y(v) / H})` }}>{v.toLocaleString("en-IN", { maximumFractionDigits: digits })}</span>
        ))}
        <div className="absolute bottom-[22px] left-[48px] right-1 top-[6px]"
          onPointerMove={(e) => {
            const box = e.currentTarget.getBoundingClientRect();
            const i = Math.round(((e.clientX - box.left) / box.width) * (shown.c.length - 1));
            setHover(Math.max(0, Math.min(shown.c.length - 1, i)));
          }}
          onPointerLeave={() => { setHover(null); setDot(null); }}>
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
            <defs>
              <linearGradient id="pricefill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="var(--accent)" stopOpacity="0.22" />
                <stop offset="1" stopColor="var(--accent)" stopOpacity="0" />
              </linearGradient>
            </defs>
            {grid.map((v) => <line key={v} x1={0} x2={W} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeWidth="1" vectorEffect="non-scaling-stroke" />)}
            <path d={area} fill="url(#pricefill)" />
            <path d={line} fill="none" stroke="var(--accent)" strokeWidth="2.4" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            {hover != null && <line x1={x(hover)} x2={x(hover)} y1={0} y2={H} stroke="var(--line-strong)" strokeWidth="1" vectorEffect="non-scaling-stroke" />}
          </svg>
          {/* markers in HTML, so they stay round when the drawing stretches */}
          {filings.map(({ index, items }) => {
            const top = items.some((c) => c.impact_level === "HIGH") ? "HIGH" : items.some((c) => c.impact_level === "MODERATE") ? "MODERATE" : "LOW";
            return (
              <button key={index} type="button" aria-label={`Filing on ${istDate(shown.d[index])}: ${items[0].headline}. Open its card`}
                onClick={() => onOpen?.(items[0].news_id)} onPointerEnter={() => setDot(index)} onFocus={() => setDot(index)} onBlur={() => setDot(null)}
                className={cn("absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface shadow transition-transform hover:scale-125",
                  top === "LOW" ? "h-3 w-3" : "h-3.5 w-3.5")}
                style={{ left: `${(x(index) / W) * 100}%`, top: `${(y(shown.c[index]) / H) * 100}%`, background: IMPACT_DOT[top] }} />
            );
          })}
          {tip && (
            <div role="tooltip" className="pointer-events-none absolute z-10 w-max max-w-[240px] rounded-xl bg-ink px-2.5 py-2 text-[12.5px] leading-snug text-surface shadow-lg"
              style={{ left: `${(x(tip.index) / W) * 100}%`, top: `${(y(shown.c[tip.index]) / H) * 100}%`,
                transform: `translate(${x(tip.index) / W > 0.66 ? "-100%" : x(tip.index) / W < 0.33 ? "0" : "-50%"}, calc(-100% - 12px))` }}>
              <b className="num block text-[11.5px] opacity-75">{istDate(shown.d[tip.index])}{tip.items.length > 1 ? ` · ${tip.items.length} filings` : ""}</b>
              <span className="line-clamp-3">{tip.items[0].headline}</span>
            </div>
          )}
        </div>
        <div className="pointer-events-none absolute bottom-0 left-[48px] right-1 h-[16px]">
          {axis.map((t, k) => (
            <span key={t.i} className={cn("num absolute -translate-x-1/2 whitespace-nowrap text-[10.5px] text-ink-3", k % 2 === 1 && axis.length > 4 && "hidden sm:block")}
              style={{ left: `${(x(t.i) / W) * 100}%` }}>{t.label}</span>
          ))}
        </div>
      </div>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] font-semibold text-ink-3">
        {(["HIGH", "MODERATE", "LOW"] as const).map((k) => (
          <span key={k}><i className="mr-1.5 inline-block h-[9px] w-[9px] rounded-full align-[0px]" style={{ background: IMPACT_DOT[k] }} />{k === "HIGH" ? "High-impact card" : k === "MODERATE" ? "Moderate" : "Low"}</span>
        ))}
        <span className="font-medium">Hover or tap a dot; a click opens its card</span>
      </p>
    </section>
  );
}
