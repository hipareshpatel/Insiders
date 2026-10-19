import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useLocation } from "wouter";
import type { Company, RadarCompany } from "../../shared/types";
import { Avatar } from "../components/Avatar";
import { Select } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { cr, istDate, pct, signClass, titleCase } from "../lib/format";
import { SECTORS, SIZES } from "../lib/taxonomy";
import { HISTORY_START } from "../lib/config";
import { useQueryState } from "../lib/url";
import { Empty, Loading } from "./FeedView";

const LETTERS = ["#", ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ"];

const col = createColumnHelper<Company>();
const columns = [
  col.accessor("company_name", {
    header: "Company",
    cell: (info) => (
      <span className="flex items-center gap-2.5">
        <Avatar name={info.getValue()} symbol={info.row.original.symbol} size={24} />
        <span className="min-w-0">
          <span className="block font-semibold text-ink">{info.row.original.symbol ?? info.row.original.scrip_code}</span>
          <span className="block truncate text-xs text-ink-3">{info.getValue()}</span>
        </span>
      </span>
    ),
  }),
  col.accessor("sector", { header: "Sector", cell: (i) => <span className="text-ink-2">{i.getValue() ? SECTORS[i.getValue()!] ?? titleCase(i.getValue()!) : "—"}</span> }),
  col.accessor("market_cap_cr", {
    header: "Market cap",
    cell: (i) => <span className="num text-ink">{cr(i.getValue())}{i.row.original.size_category ? <span className="block text-[11px] text-ink-3">{titleCase(i.row.original.size_category)}cap</span> : null}</span>,
  }),
  col.accessor("ret_1w", { header: "1W", cell: (i) => <span className={cn("num", signClass(i.getValue()))}>{pct(i.getValue())}</span> }),
  col.accessor("ret_1m", { header: "1M", cell: (i) => <span className={cn("num", signClass(i.getValue()))}>{pct(i.getValue())}</span> }),
  col.accessor("credibility_score", {
    header: "Credibility",
    cell: (i) => <span className="num text-ink-2">{i.getValue() != null ? `${Math.round(i.getValue()!)}%` : "—"}</span>,
  }),
  col.accessor("open_promises", {
    header: "Promises / capex",
    cell: (i) => <span className="num text-ink-2">{i.getValue() ?? 0} open · {i.row.original.active_capex ?? 0} capex</span>,
  }),
  col.accessor("latest_revenue", {
    header: "Latest quarter",
    cell: (i) => {
      const rev = parseJson<{ period: string; value: number }>(i.getValue());
      const ebitda = parseJson<{ period: string; value: number }>(i.row.original.latest_ebitda);
      if (!rev) return <span className="text-ink-3">—</span>;
      return (
        <span className="num text-ink">{cr(rev.value)}<span className="block text-[11px] text-ink-3">{rev.period}
          {ebitda && ebitda.period === rev.period ? ` · EBITDA ${cr(ebitda.value)}` : ""}
          {i.row.original.gross_debt_cr != null ? ` · debt ${cr(i.row.original.gross_debt_cr)}` : ""}</span></span>
      );
    },
  }),
  col.accessor("card_count", { header: "Filings", cell: (i) => <span className="num text-ink">{i.getValue()}</span> }),
  col.accessor("last_card_at", { header: "Last filing", cell: (i) => <span className="num text-ink-2">{i.getValue() ? istDate(i.getValue()!) : "—"}</span> }),
];

function parseJson<T>(raw: string | null | undefined): T | null {
  try {
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

const TRIGGER_LABEL: Record<string, string> = {
  CAPEX_COMMISSIONED: "Capex commissioned", VOLUME_STREAK: "Volume streak", MARGIN_EXPANSION: "Margin expansion",
  DELEVERAGING: "Debt cut", SMART_MONEY: "Smart money buying",
};

/** Companies where several independent positive triggers converged in the last 90 days. */
function InflectionRadar() {
  const [min, setMin] = useState(3);
  const [, navigate] = useLocation();
  const query = useQuery({ queryKey: ["radar", min], queryFn: () => api.radar(min) });
  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-2 text-[13px] text-ink-2">
        <span>Companies with</span>
        <Select aria-label="Minimum triggers" value={String(min)} onChange={(e) => setMin(Number(e.target.value))}>
          <option value="3">3 or more triggers</option>
          <option value="2">2 or more (building)</option>
        </Select>
        <span>in the last 90 days: capex commissioned, volume streak or margin expansion, debt cut or smart-money buying.</span>
      </div>
      {query.isPending ? <Loading /> : query.isError ? <Empty title="Couldn't load the radar" body={String(query.error)} /> :
        query.data.companies.length === 0 ? (
          <Empty title="Nothing on the radar" body="No company has that many inflection triggers in its memory over the last 90 days." />
        ) : (
          <ul className="mt-3 grid gap-3 sm:grid-cols-2">
            {query.data.companies.map((c: RadarCompany) => (
              <li key={c.scrip_code}>
                <button type="button" onClick={() => navigate(`/company/${c.scrip_code}`)}
                  className="w-full rounded-xl border border-line bg-surface p-4 text-left hover:border-accent focus:border-accent focus:outline-none">
                  <span className="flex items-center gap-2.5">
                    <Avatar name={c.company_name} symbol={c.symbol} size={28} />
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold text-ink">{c.watchlist ? "★ " : ""}{c.symbol ?? c.scrip_code}</span>
                      <span className="block truncate text-xs text-ink-3">{c.company_name} · {cr(c.market_cap_cr)}
                        {c.credibility_score != null ? ` · credibility ${Math.round(c.credibility_score)}%` : ""}</span>
                    </span>
                    <span className="num rounded-md bg-accent-soft px-2 py-0.5 text-xs font-semibold text-accent">{c.triggers.length}</span>
                  </span>
                  <ul className="mt-3 space-y-1 text-[12.5px]">
                    {c.triggers.map((t) => (
                      <li key={t.kind} className="flex gap-2">
                        <span className="num shrink-0 text-ink-3">{istDate(t.date)}</span>
                        <span className="text-ink-2"><span className="font-medium text-ink">{TRIGGER_LABEL[t.kind] ?? t.kind}</span> · {t.text}</span>
                      </li>
                    ))}
                  </ul>
                </button>
              </li>
            ))}
          </ul>
        )}
    </div>
  );
}

export function CompaniesView() {
  const [params, setParams] = useQueryState();
  const [, navigate] = useLocation();
  const letter = params.get("letter");
  const sort = params.get("sort") ?? "recent";
  const size = params.get("size");
  const all = params.get("all") === "1";
  const radar = params.get("view") === "radar";
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
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
    <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6">
      <header className="mb-4">
        <h1 className="font-display text-[30px] leading-tight text-ink">Companies</h1>
        <p className="mt-1 text-sm text-ink-2">Every company with a living memory: its story, promises and filings since {istDate(HISTORY_START)}.</p>
        <div className="mt-3 flex gap-1" role="tablist">
          {([["", "Directory"], ["radar", "🚀 Inflection Radar"]] as const).map(([v, label]) => (
            <button key={v} type="button" role="tab" aria-selected={(v === "radar") === radar}
              onClick={() => setParams({ view: v || null })}
              className={cn("h-8 rounded-lg px-3 text-[13px] font-medium", (v === "radar") === radar ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink")}>
              {label}
            </button>
          ))}
        </div>
      </header>
      {radar ? <InflectionRadar /> : <>

      <div className="flex flex-wrap items-center gap-2">
        <label className="relative min-w-0 flex-1 basis-60">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Name, former name or NSE symbol"
            className="h-9 w-full rounded-lg border border-line bg-surface pl-9 pr-3 text-[13px] text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none" />
        </label>
        <Select aria-label="Sort" value={sort} onChange={(e) => setParams({ sort: e.target.value === "recent" ? null : e.target.value })}>
          <option value="recent">Latest filing first</option>
          <option value="name">A to Z</option>
          <option value="cards">Most filings</option>
          <option value="mcap">Largest first</option>
        </Select>
        <Select aria-label="Market cap" value={size ?? ""} onChange={(e) => setParams({ size: e.target.value || null })}>
          <option value="">All sizes</option>
          {SIZES.map((s) => <option key={s} value={s}>{titleCase(s)}cap</option>)}
        </Select>
        <Select aria-label="Coverage" value={all ? "1" : ""} onChange={(e) => setParams({ all: e.target.value || null })}>
          <option value="">With analysed filings</option>
          <option value="1">All listed companies</option>
        </Select>
      </div>

      <div className="mt-3 flex flex-wrap gap-0.5" role="toolbar" aria-label="First letter">
        <button type="button" onClick={() => setParams({ letter: null })}
          className={cn("h-7 rounded-md px-2 text-xs font-medium", !letter ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink")}>All</button>
        {LETTERS.map((l) => (
          <button key={l} type="button" onClick={() => setParams({ letter: l === letter ? null : l })}
            className={cn("num h-7 w-7 rounded-md text-xs font-medium", letter === l ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink")}>{l}</button>
        ))}
      </div>

      <div className="mt-3">
        {query.isPending ? <Loading /> : query.isError ? <Empty title="Couldn't load companies" body={String(query.error)} /> : data.length === 0 ? (
          <Empty title="No companies match" body="Companies appear here once a material filing of theirs is analysed." />
        ) : (
          <div className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full min-w-[820px] text-[13.5px]">
              <thead className="eyebrow border-b border-line text-left text-ink-3">
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>{hg.headers.map((h) => <th key={h.id} className="px-4 py-3 font-semibold">{flexRender(h.column.columnDef.header, h.getContext())}</th>)}</tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => (
                  <tr key={row.id} tabIndex={0}
                    onClick={() => navigate(`/company/${row.original.scrip_code}`)}
                    onKeyDown={(e) => e.key === "Enter" && navigate(`/company/${row.original.scrip_code}`)}
                    className="cursor-pointer border-b border-line last:border-0 hover:bg-surface-2/60 focus:bg-surface-2/60 focus:outline-none">
                    {row.getVisibleCells().map((cell) => <td key={cell.id} className="max-w-[18rem] px-4 py-2.5">{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
            {query.hasNextPage && <div className="border-t border-line p-3 text-center"><Button size="sm" onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage}>Load more</Button></div>}
          </div>
        )}
      </div>
      </>}
    </div>
  );
}
