import type { Dossier } from "../../../shared/types";
import { cn } from "../../lib/cn";
import { Panel } from "./Panel";

type Row = NonNullable<Dossier["ownership"]>[number];
const CATEGORIES = [
  ["mf_pct", "Mutual funds"], ["fpi_pct", "Foreign portfolio (FPI)"], ["insurance_pct", "Insurers"],
  ["pension_pct", "Pension and provident funds"], ["banks_pct", "Banks"], ["aif_pct", "Alternative investment funds"],
] as const;
// a move worth a reader's eye: a category by half a point, a named holder by a quarter point (owner, 2026-10-21:
// "track significant changes in shareholding")
const CATEGORY_MOVE = 0.5;
const HOLDER_MOVE = 0.25;

function delta(now?: number, before?: number) {
  if (now == null || before == null) return null;
  const d = Math.round((now - before) * 100) / 100;
  return Math.abs(d) < 0.01 ? null : d;
}

function Change({ d, big }: { d: number | null; big: number }) {
  if (d == null) return <span className="text-ink-3">—</span>;
  return <span className={cn("num font-bold", d > 0 ? "text-pos" : "text-neg", Math.abs(d) < big && "opacity-60")}>{d > 0 ? "+" : ""}{d.toFixed(2)}</span>;
}

/** Who among the institutions holds the stock, the latest quarter against the one before: the categories of the
 *  public holding and every named holder of 1% or more, from NSE's shareholding XBRL. Hidden until a pattern with
 *  this detail is in memory. */
export function Institutions({ ownership }: { ownership: Row[] | undefined }) {
  const rows = (ownership ?? []).filter((o) => o.holders !== undefined);
  const now = rows[rows.length - 1];
  if (!now) return null;
  const before = rows[rows.length - 2];
  const prev = new Map((before?.holders ?? []).map((h) => [h.name.toLowerCase(), h]));
  const names = new Set((now.holders ?? []).map((h) => h.name.toLowerCase()));
  const exited = (before?.holders ?? []).filter((h) => !names.has(h.name.toLowerCase()));
  const cats = CATEGORIES.filter(([k]) => now[k] != null && (now[k]! > 0 || (before?.[k] ?? 0) > 0));
  return (
    <Panel title="Institutions" hint={`${now.period}${before ? ` against ${before.period}` : ""}, % of shares`}>
      {cats.length > 0 && (
        <dl className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {cats.map(([k, label]) => (
            <div key={k} className="rounded-xl bg-surface-2 px-3 py-2">
              <dt className="text-[11px] font-bold text-ink-3">{label}</dt>
              <dd className="num flex items-baseline justify-between gap-2 text-[15px] font-bold text-ink">
                {now[k]!.toFixed(2)}%
                {before && <span className="text-[12px]"><Change d={delta(now[k], before[k])} big={CATEGORY_MOVE} /></span>}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {(now.holders?.length ?? 0) > 0 ? (
        <table className="w-full text-[13px]">
          <thead className="eyebrow text-left text-ink-3">
            <tr><th className="pb-1.5 font-semibold">Holder (1% or more)</th><th className="pb-1.5 text-right font-semibold">Stake</th>{before && <th className="pb-1.5 text-right font-semibold">Change</th>}</tr>
          </thead>
          <tbody>
            {now.holders!.map((h) => {
              const was = prev.get(h.name.toLowerCase());
              return (
                <tr key={h.name} className="border-t border-line">
                  <td className="py-1.5 pr-2"><span className="text-ink">{h.name}</span> <span className="text-[11.5px] text-ink-3">· {h.category}</span></td>
                  <td className="num py-1.5 text-right font-semibold text-ink">{h.pct.toFixed(2)}%</td>
                  {before && <td className="py-1.5 text-right text-[12px]">{was ? <Change d={delta(h.pct, was.pct)} big={HOLDER_MOVE} /> : <span className="font-bold text-pos">new</span>}</td>}
                </tr>
              );
            })}
            {exited.map((h) => (
              <tr key={`x-${h.name}`} className="border-t border-line text-ink-3">
                <td className="py-1.5 pr-2">{h.name} <span className="text-[11.5px]">· {h.category}</span></td>
                <td className="num py-1.5 text-right">below 1%</td>
                <td className="py-1.5 text-right text-[12px] font-bold text-neg">was {h.pct.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="text-[13px] text-ink-3">No public holder at 1% or more this quarter.</p>}
    </Panel>
  );
}
