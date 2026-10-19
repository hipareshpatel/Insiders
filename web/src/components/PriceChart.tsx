import { useMemo, useState } from "react";
import type { CardRow, CompanyDetail } from "../../shared/types";
import { cn } from "../lib/cn";
import { placeFilings, RANGES, rangeMove, sliceRange, type Range } from "../lib/chart";
import { istDate, signClass } from "../lib/format";

const W = 1000, H = 220, PAD = 8;   // the drawing's own units; it stretches to the card's width
const IMPACT_DOT: Record<string, string> = { HIGH: "var(--impact-high)", MODERATE: "var(--impact-moderate)", LOW: "var(--neutral-stripe)" };

/** A year of daily closes with each analysed filing marked on its trading day (market-data writes the series). */
export function PriceChart({ chart, cards, onOpen }: { chart: CompanyDetail["chart"]; cards: CardRow[]; onOpen?: (newsId: string) => void }) {
  const [range, setRange] = useState<Range>("1Y");
  const [hover, setHover] = useState<number | null>(null);
  const shown = useMemo(() => (chart ? sliceRange(chart, range) : null), [chart, range]);
  if (!chart || !shown || shown.c.length < 5) return null;

  const lo = Math.min(...shown.c), hi = Math.max(...shown.c);
  const span = hi - lo || hi || 1;
  const x = (i: number) => PAD + (i / Math.max(1, shown.c.length - 1)) * (W - PAD * 2);
  const y = (v: number) => PAD + (1 - (v - lo) / span) * (H - PAD * 2);
  const line = shown.c.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const area = `${line}L${x(shown.c.length - 1).toFixed(1)},${H}L${x(0).toFixed(1)},${H}Z`;
  const move = rangeMove(shown);
  const up = (move ?? 0) >= 0;
  const filings = placeFilings(shown, cards);
  const at = hover ?? shown.c.length - 1;
  const atFilings = filings.find((f) => f.index === at)?.items ?? [];

  return (
    <section className="card-soft rise-in min-w-0 px-5 pb-4 pt-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[16px] font-extrabold leading-tight tracking-tight text-ink">Price</h2>
          <p className="num text-[12.5px] text-ink-3">
            {istDate(shown.d[at])} · <span className="font-bold text-ink">₹{shown.c[at].toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span>
            {hover == null && move != null && <> · <span className={cn("font-semibold", signClass(move))}>{move > 0 ? "+" : ""}{move.toFixed(1)}% over {range}</span></>}
            {atFilings.length > 0 && <> · <span className="font-sans text-ink-2">{atFilings.length} filing{atFilings.length > 1 ? "s" : ""}: {atFilings[0].headline}</span></>}
          </p>
        </div>
        <span className="inline-flex rounded-[11px] bg-surface-2 p-[3px]" role="radiogroup" aria-label="Range">
          {(Object.keys(RANGES) as Range[]).map((r) => (
            <button key={r} type="button" role="radio" aria-checked={range === r} onClick={() => { setRange(r); setHover(null); }}
              className={cn("rounded-lg px-2.5 py-1 text-[12px] font-bold", range === r ? "bg-surface text-ink shadow-sm" : "text-ink-3")}>{r}</button>
          ))}
        </span>
      </header>
      <div className="relative mt-3 h-[200px] w-full sm:h-[220px]"
        onPointerMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          const i = Math.round(((e.clientX - box.left) / box.width) * (shown.c.length - 1));
          setHover(Math.max(0, Math.min(shown.c.length - 1, i)));
        }}
        onPointerLeave={() => setHover(null)}>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden>
          <defs>
            <linearGradient id="pricefill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor={up ? "var(--pos)" : "var(--neg)"} stopOpacity="0.18" />
              <stop offset="1" stopColor={up ? "var(--pos)" : "var(--neg)"} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={area} fill="url(#pricefill)" />
          <path d={line} fill="none" stroke={up ? "var(--pos)" : "var(--neg)"} strokeWidth="2" vectorEffect="non-scaling-stroke" />
          {hover != null && <line x1={x(hover)} x2={x(hover)} y1={0} y2={H} stroke="var(--line-strong)" strokeWidth="1" vectorEffect="non-scaling-stroke" />}
        </svg>
        {/* markers and labels in HTML, so they keep their shape when the drawing stretches */}
        {filings.map(({ index, items }) => {
          const top = items.some((c) => c.impact_level === "HIGH") ? "HIGH" : items.some((c) => c.impact_level === "MODERATE") ? "MODERATE" : "LOW";
          return (
            <button key={index} type="button" title={`${istDate(shown.d[index])}: ${items.map((c) => c.headline).join(" · ")}`}
              onClick={() => onOpen?.(items[0].news_id)} aria-label={`Filing on ${istDate(shown.d[index])}: ${items[0].headline}`}
              className="absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface shadow"
              style={{ left: `${(x(index) / W) * 100}%`, top: `${(y(shown.c[index]) / H) * 100}%`, background: IMPACT_DOT[top] }} />
          );
        })}
        <span className="num pointer-events-none absolute left-1 top-0 text-[10.5px] text-ink-3">₹{hi.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
        <span className="num pointer-events-none absolute bottom-0 left-1 text-[10.5px] text-ink-3">₹{lo.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
      </div>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] font-semibold text-ink-3">
        <span className="num">{istDate(shown.d[0])} – {istDate(shown.d[shown.d.length - 1])}</span>
        {filings.length > 0 && <span><i className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: "var(--impact-moderate)" }} />Filings analysed (open one with a click)</span>}
        <span>Daily closes from Yahoo, adjusted for splits and bonuses</span>
      </p>
    </section>
  );
}
