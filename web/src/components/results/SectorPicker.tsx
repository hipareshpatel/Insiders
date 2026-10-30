import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import type { ClassNode } from "../../../shared/resultsTypes";
import { industryParts } from "../../../shared/industry";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { Button } from "../ui/button";
import { Skeleton } from "./bits";

const LEVELS = ["Sector", "Industry group", "Industry", "Basic industry"];
const FIRST = 7;   // sectors shown before "+ n more"

/** NSE's stored classification as cascading columns (sector > industry group > industry > basic industry): pick any level, and the
 *  list keeps the companies whose path starts with it. On a phone, `stacked` shows one level at a time. */
export function SectorPicker({ quarter, value, onApply, stacked = false }: {
  quarter: string | null; value: string | null; onApply: (path: string | null) => void; stacked?: boolean;
}) {
  const tree = useQuery({ queryKey: ["results-classification", quarter], queryFn: () => api.resultsClassification(quarter), staleTime: 5 * 60_000 });
  const [sel, setSel] = useState<string[]>(() => industryParts(value));
  const [more, setMore] = useState(false);

  if (tree.isPending) return <div className="grid gap-2 sm:w-[620px]">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-8" />)}</div>;
  if (!tree.data) return <p className="py-6 text-[14px] text-ink-2">Couldn't load the classification. <button type="button" className="font-semibold text-accent" onClick={() => tree.refetch()}>Try again</button></p>;

  // the chain of picked nodes, one per level
  const chain: ClassNode[] = [];
  let level = tree.data.tree;
  for (const name of sel) {
    const node = level.find((n) => n.name === name);
    if (!node) break;
    chain.push(node);
    level = node.children;
  }
  const picked = chain[chain.length - 1];
  const columns: { parent: ClassNode | null; nodes: ClassNode[] }[] = [{ parent: null, nodes: tree.data.tree }];
  chain.forEach((n, i) => { if (n.children.length && i < LEVELS.length - 1) columns.push({ parent: n, nodes: n.children }); });
  const pick = (depth: number, node: ClassNode | null) => setSel(node ? [...chain.slice(0, depth).map((c) => c.name), node.name] : chain.slice(0, depth).map((c) => c.name));

  const item = (on: boolean, label: string, onClick: () => void, opts: { n?: number; arrow?: boolean; muted?: boolean } = {}) => (
    <button type="button" aria-pressed={on} onClick={onClick}
      className={cn("flex w-full items-start justify-between gap-3 rounded-[9px] px-2.5 py-2 text-left text-[13.5px]", stacked && "min-h-11 items-center",
        on ? "bg-accent-soft text-ink" : opts.muted ? "text-ink-3 hover:bg-surface-2" : "text-ink-2 hover:bg-surface-2 hover:text-ink")}>
      <span>{label}{opts.arrow && " ›"}</span>
      {opts.n != null && <span className="num shrink-0 text-ink-3">{opts.n}</span>}
    </button>
  );

  const column = (c: { parent: ClassNode | null; nodes: ClassNode[] }, depth: number) => {
    const chosen = chain[depth];
    const all = depth === 0;
    const shown = all && !more && !stacked && c.nodes.length > FIRST + 1
      ? c.nodes.slice(0, FIRST).concat(chosen && c.nodes.indexOf(chosen) >= FIRST ? [chosen] : []) : c.nodes;
    return (
      <div key={depth} className={cn(!stacked && "max-h-[340px] overflow-y-auto border-r border-line px-2 last:border-r-0")}>
        {!stacked && <div className="px-2.5 pb-2 pt-1 text-[12.5px] text-ink-3">{LEVELS[depth]}{all ? ` · ${c.nodes.length}` : ""}</div>}
        {item(!chosen, all ? "All sectors" : depth === 1 ? `All in ${c.parent!.name}` : depth === 2 ? "All in this group" : `All in ${c.parent!.name}`, () => pick(depth, null))}
        {shown.map((n) => item(chosen === n, n.name, () => pick(depth, n), { n: n.n, arrow: n.children.length > 0 && depth < LEVELS.length - 1 }))}
        {all && !more && !stacked && shown.length < c.nodes.length && item(false, `+ ${c.nodes.length - shown.length} more`, () => setMore(true), { muted: true })}
        {all && tree.data.unclassified > 0 && (
          <div className="flex justify-between px-2.5 py-2 text-[13.5px] text-ink-3" title="Companies with no stored NSE classification: not a filter">
            <span>Unclassified</span><span className="num">{tree.data.unclassified}</span>
          </div>
        )}
      </div>
    );
  };

  const path = chain.map((c) => c.name).join(" > ") || null;
  const crumbs = (
    <div className="mb-3.5 flex flex-wrap items-center gap-2 text-[13.5px] text-ink-2">
      <span>Sector</span>
      {chain.map((c) => <span key={c.path} className="contents"><span aria-hidden className="text-ink-3">›</span><b className="font-semibold text-ink">{c.name}</b></span>)}
    </div>
  );
  const foot = (
    <div className={cn("flex items-center justify-between gap-3 pt-4", stacked && "sticky bottom-0 bg-surface pb-1")}>
      {!stacked && <span className="text-[13px] text-ink-3">NSE's own classification, as stored. Pick any level.</span>}
      <Button variant="primary" className={cn("h-10 rounded-[11px] font-semibold", stacked && "h-12 flex-1 justify-center")} onClick={() => onApply(path)}>
        {picked ? `Show ${picked.name}` : "Show all sectors"}
      </Button>
    </div>
  );

  if (stacked) {
    const depth = Math.min(columns.length - 1, chain.length);
    const col = columns[depth] ?? columns[columns.length - 1];
    return (
      <div>
        {crumbs}
        {chain.length > 0 && (
          <button type="button" onClick={() => setSel(sel.slice(0, Math.max(0, chain.length - 1)))} className="mb-1 inline-flex min-h-11 items-center gap-1 text-[14px] font-semibold text-accent">
            <ChevronLeft aria-hidden className="h-4 w-4" />Up a level
          </button>
        )}
        <div className="text-[12.5px] text-ink-3">{LEVELS[columns.indexOf(col)]}</div>
        {column(col, columns.indexOf(col))}
        {picked && !picked.children.length && <p className="px-2.5 py-2 text-[13px] text-ink-3"><ChevronRight aria-hidden className="mr-1 inline h-3.5 w-3.5" />The narrowest level.</p>}
        {foot}
      </div>
    );
  }
  return (
    <div>
      {crumbs}
      <div className="grid" style={{ gridTemplateColumns: `repeat(${Math.max(columns.length, 2)}, 200px)` }}>{columns.map((c, i) => column(c, i))}</div>
      {foot}
    </div>
  );
}
