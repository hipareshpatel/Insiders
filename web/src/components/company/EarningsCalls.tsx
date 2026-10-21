import { useState } from "react";
import type { CallQuarter } from "../../../shared/types";
import { cn } from "../../lib/cn";
import { callQuarters } from "./companyText";
import { dayMonth } from "./OverviewPanels";
import { Panel } from "./Panel";

/** Earnings calls by quarter (O13/O4): each call's checked AI takeaways (what changed against the earlier call beside
 *  each), then what memory took from it, under fixed headings, newest quarter first. Built by the pipeline
 *  (call_summary.py); hidden when there is none. */
export function EarningsCalls({ calls }: { calls: CallQuarter[] | undefined }) {
  const quarters = callQuarters(calls);
  const [pick, setPick] = useState<string | null>(null);
  const q = quarters.find((x) => x.quarter === pick) ?? quarters[0];
  if (!q) return null;
  const several = q.sources.length > 1;
  return (
    <Panel title="Earnings calls" sub="key takeaways by quarter"
      hint={quarters.length > 1 ? (
        <span role="tablist" className="inline-flex gap-0.5 rounded-xl bg-surface-2 p-0.5">
          {quarters.map((x) => (
            <button key={x.quarter} type="button" role="tab" aria-selected={x.quarter === q.quarter} onClick={() => setPick(x.quarter)}
              className={cn("num rounded-[9px] px-2.5 py-1 text-[12px] font-bold transition-colors",
                x.quarter === q.quarter ? "bg-surface text-ink shadow-sm" : "text-ink-3 hover:text-ink")}>
              {x.quarter}
            </button>
          ))}
        </span>
      ) : <span className="num font-bold">{q.quarter}</span>}>
      <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
        {q.categories.map((c) => (
          <section key={c.name} className="min-w-0">
            <h3 className="mb-1.5 text-[10.5px] font-extrabold uppercase tracking-[0.07em] text-ink-3">{c.name}</h3>
            <ul className="space-y-1.5">
              {c.points.map((p, i) => (
                <li key={i} className="grid grid-cols-[10px_minmax(0,1fr)] gap-x-1.5 text-[13.5px] leading-snug text-ink">
                  <span aria-hidden className="mt-[7px] h-[5px] w-[5px] rounded-full bg-accent" />
                  <span title={`From the call filed ${dayMonth(p.date)}`}>
                    {p.text}
                    {p.versus && <span className="mt-0.5 block text-[12px] font-medium text-[var(--accent)]">vs earlier: {p.versus}</span>}
                    {p.reiterated && <small className="ml-1.5 rounded-full bg-surface-2 px-1.5 py-px text-[10.5px] font-bold text-ink-3">reiterated</small>}
                    {several && <small className="num ml-1.5 text-[11.5px] text-ink-3">{dayMonth(p.date)}</small>}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      <p className="mt-4 flex flex-wrap gap-x-3 gap-y-1 border-t border-line pt-2.5 text-[12px] text-ink-3">
        <span>The {q.quarter} call{several ? "s and presentations" : ""}, read by AI; each point and figure checked against the document and memory</span>
        {q.sources.map((s) => s.pdf_url ? (
          <a key={s.news_id} href={s.pdf_url} target="_blank" rel="noreferrer" className="font-bold text-accent hover:underline">⎙ Filed {dayMonth(s.date)}</a>
        ) : <span key={s.news_id}>Filed {dayMonth(s.date)}</span>)}
      </p>
    </Panel>
  );
}
