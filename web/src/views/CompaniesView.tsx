import { useInfiniteQuery } from "@tanstack/react-query";
import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Company } from "../../shared/types";
import { Pill } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Switch } from "../components/ui/switch";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { cr, istDate, pct, signClass, titleCase } from "../lib/format";
import { SIZES } from "../lib/taxonomy";
import { toggleInList, useQueryState } from "../lib/url";
import { Empty, Loading } from "./FeedView";

const LETTERS = ["#", ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ"];
const SORTS = [
  { key: "name", label: "A–Z" },
  { key: "recent", label: "Recent activity" },
  { key: "cards", label: "Most cards" },
  { key: "mcap", label: "Market cap" },
];

const col = createColumnHelper<Company>();
const columns = [
  col.accessor("company_name", {
    header: "Company",
    cell: (info) => (
      <div className="min-w-0">
        <div className="truncate font-medium text-ink">{info.getValue()}</div>
        <div className="num text-[11px] text-ink-3">{info.row.original.symbol ? `${info.row.original.symbol} · ` : ""}{info.row.original.scrip_code}</div>
      </div>
    ),
  }),
  col.accessor("sector", { header: "Sector", cell: (i) => <span className="text-ink-2">{i.getValue() ? titleCase(i.getValue()!) : "—"}</span> }),
  col.accessor("market_cap_cr", {
    header: "Market cap",
    cell: (i) => (
      <span className="num text-ink">
        {cr(i.getValue())}
        {i.row.original.size_category ? <span className="block text-[11px] text-ink-3">{titleCase(i.row.original.size_category)}cap</span> : null}
      </span>
    ),
  }),
  col.accessor("ret_1w", { header: "1W", cell: (i) => <span className={cn("num", signClass(i.getValue()))}>{pct(i.getValue())}</span> }),
  col.accessor("ret_1m", { header: "1M", cell: (i) => <span className={cn("num", signClass(i.getValue()))}>{pct(i.getValue())}</span> }),
  col.accessor("ret_1y", { header: "1Y", cell: (i) => <span className={cn("num", signClass(i.getValue()))}>{pct(i.getValue())}</span> }),
  col.accessor("card_count", { header: "Cards", cell: (i) => <span className="num text-ink">{i.getValue()}</span> }),
  col.accessor("last_card_at", { header: "Last activity", cell: (i) => <span className="num text-xs text-ink-2">{i.getValue() ? istDate(i.getValue()!) : "—"}</span> }),
];

export function CompaniesView() {
  const [params, setParams] = useQueryState();
  const letter = params.get("letter");
  const sort = params.get("sort") ?? "recent";
  const size = params.get("size");
  const all = params.get("all") === "1";
  const [text, setText] = useState(params.get("cq") ?? "");
  const [q, setQ] = useState(text);
  useEffect(() => {
    const id = setTimeout(() => setQ(text.trim()), 250);
    return () => clearTimeout(id);
  }, [text]);

  const filters = useMemo(() => ({ q, letter, sort, size, all: all ? "1" : null }), [q, letter, sort, size, all]);
  const query = useInfiniteQuery({
    queryKey: ["companies", filters],
    queryFn: ({ pageParam }) => api.companies({ ...filters, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset,
  });
  const data = useMemo(() => query.data?.pages.flatMap((p) => p.companies) ?? [], [query.data]);
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-5 sm:px-6">
      <header className="mb-4">
        <h1 className="font-display text-xl font-bold text-ink">Company memory directory</h1>
        <p className="text-sm text-ink-2">Every company with a living dossier. Open one for its memory, promise tracker and timeline.</p>
      </header>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className="relative min-w-0 flex-1 basis-60">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Name, symbol or scrip code…"
            className="h-9 w-full rounded-md border border-line bg-surface pl-8 pr-3 text-sm text-ink placeholder:text-ink-3 focus:border-forest focus:outline-none" />
        </label>
        <div className="flex flex-wrap gap-1">
          {SORTS.map((s) => <Pill key={s.key} active={sort === s.key} onClick={() => setParams({ sort: s.key })}>{s.label}</Pill>)}
        </div>
        <div className="flex flex-wrap gap-1">
          {SIZES.map((s) => (
            <Pill key={s} active={!!size?.split(",").includes(s)} onClick={() => setParams({ size: toggleInList(size, s) })}>{titleCase(s)}</Pill>
          ))}
        </div>
        <label className="flex items-center gap-2 text-xs font-medium text-ink-2">
          <Switch checked={all} onCheckedChange={(v) => setParams({ all: v ? "1" : null })} /> Include companies without cards
        </label>
      </div>

      <div className="mb-3 flex flex-wrap gap-0.5" role="toolbar" aria-label="Filter by first letter">
        <button type="button" onClick={() => setParams({ letter: null })}
          className={cn("h-7 rounded px-2 text-xs font-medium", !letter ? "bg-forest text-forest-ink" : "text-ink-2 hover:bg-surface-2")}>All</button>
        {LETTERS.map((l) => (
          <button key={l} type="button" onClick={() => setParams({ letter: l === letter ? null : l })}
            className={cn("num h-7 w-7 rounded text-xs font-medium", letter === l ? "bg-forest text-forest-ink" : "text-ink-2 hover:bg-surface-2")}>{l}</button>
        ))}
      </div>

      {query.isPending ? <Loading /> : query.isError ? <Empty title="Could not load companies" body={String(query.error)} /> : data.length === 0 ? (
        <Empty title="No companies match" body="Companies appear here once their first material filing is analysed." />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="bg-surface-2 text-left text-[11px] uppercase tracking-wide text-ink-3">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((h) => (
                    <th key={h.id} className="px-4 py-2.5 font-semibold">{flexRender(h.column.columnDef.header, h.getContext())}</th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr key={row.id} tabIndex={0}
                  onClick={() => setParams({ company: row.original.scrip_code, tab: "dossier" })}
                  onKeyDown={(e) => e.key === "Enter" && setParams({ company: row.original.scrip_code, tab: "dossier" })}
                  className="cursor-pointer border-t border-line hover:bg-memory/60 focus:bg-memory/60 focus:outline-none">
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="max-w-[18rem] px-4 py-2.5">{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {query.hasNextPage && (
            <div className="border-t border-line p-3 text-center">
              <Button size="sm" onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage}>Load more</Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
