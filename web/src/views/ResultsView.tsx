import { useInfiniteQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Search } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "wouter";
import { GROWTH_STEPS, MARGIN_STEPS, SIZE_CATEGORIES, parseKpiQuery, type KpiRow, type KpiSort } from "../../shared/resultsKpi";
import { Avatar } from "../components/Avatar";
import { Select } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { cr, companyPath } from "../lib/format";
import { TURN, turnOf } from "../lib/results";
import { useQueryState } from "../lib/url";
import { Empty, Loading } from "./FeedView";

export { turnOf };

export function Change({ value, unit = "%", turn }: { value?: number | null; unit?: "%" | "bp"; turn?: string }) {
  if (turn && TURN[turn]) return <span className={cn("whitespace-nowrap font-semibold", TURN[turn][1])}>{TURN[turn][0]}</span>;
  if (value == null) return <span className="text-ink-3">—</span>;
  const text = unit === "bp" ? `${value > 0 ? "+" : ""}${Math.round(value)}bp` : `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
  return <span className={cn("font-semibold", value > 0 ? "text-pos" : value < 0 ? "text-neg" : "text-ink-2")}>{text}</span>;
}

/** Revenue, EBITDA and PAT growth for a quarter, a report not a feed: one row per company, from its saved statements (results_kpi;
 *  no card), with filters and sorts that run on every company of the quarter. */
export function ResultsView() {
  const [params, setParams] = useQueryState();
  const [, navigate] = useLocation();
  const q = params.get("q") ?? "";
  const [text, setText] = useState(q);
  useEffect(() => setText(q), [q]);
  useEffect(() => {
    const id = setTimeout(() => { if (q !== text) setParams({ q: text || null }); }, 300);
    return () => clearTimeout(id);
  }, [text, q, setParams]);

  const filters = Object.fromEntries(["quarter", "size", "q", "rev_min", "ebitda_min", "pat_min", "opm_min", "turnaround", "sort", "dir"]
    .map((k) => [k, params.get(k)]));
  const sort = parseKpiQuery({ sort: filters.sort ?? undefined }).sort;
  const dir = sort === "company" ? (filters.dir === "desc" ? "desc" : "asc") : (filters.dir === "asc" ? "asc" : "desc");
  const active = ["size", "q", "rev_min", "ebitda_min", "pat_min", "opm_min", "turnaround"].filter((k) => filters[k]).length;

  const query = useInfiniteQuery({
    queryKey: ["results-kpi", filters],
    queryFn: ({ pageParam }) => api.resultsKpi({ ...filters, sort, dir, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page < last.pages ? last.page + 1 : undefined),
  });
  const first = query.data?.pages[0];
  const rows = query.data?.pages.flatMap((p) => p.rows) ?? [];
  const quarter = first?.quarter ?? filters.quarter;

  const sortBy = (key: KpiSort) =>
    setParams(key === sort ? { sort: key, dir: dir === "desc" ? "asc" : "desc" } : { sort: key, dir: key === "company" ? "asc" : "desc" });
  const growth = (name: string, label: string) => (
    <Select aria-label={label} className="w-full sm:w-auto" value={filters[name] ?? ""} onChange={(e) => setParams({ [name]: e.target.value || null })}>
      <option value="">{label}: any</option>
      {GROWTH_STEPS.map((n) => <option key={n} value={n}>{label} ≥ {n}%</option>)}
    </Select>
  );

  return (
    <div className="mx-auto w-full max-w-[1240px] px-4 py-6 sm:px-6">
      <header className="mb-4">
        <h1 className="font-display text-[30px] leading-tight text-ink">Results</h1>
        <p className="mt-1 text-sm text-ink-2">
          Revenue, EBITDA and PAT growth against the same quarter a year ago, from each company's saved statements (the ones on its Results tab).
          Banks and insurers are not shown yet. A loss turned to profit counts as growth.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <Select aria-label="Quarter" value={quarter ?? ""} onChange={(e) => setParams({ quarter: e.target.value || null })}>
          {(first?.quarters ?? []).map((x) => <option key={x.period} value={x.period}>{x.period} · {x.n} companies</option>)}
        </Select>
        <Select aria-label="Market cap" value={filters.size ?? ""} onChange={(e) => setParams({ size: e.target.value || null })}>
          <option value="">All sizes</option>
          {SIZE_CATEGORIES.map((s) => <option key={s} value={s}>{s.charAt(0) + s.slice(1).toLowerCase()} cap</option>)}
        </Select>
        <label className="relative min-w-0 flex-1 basis-56">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Search company"
            className="h-9 w-full rounded-lg border border-line bg-surface pl-9 pr-3 text-[13px] text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none" />
        </label>
      </div>
      <div className="mt-2 grid grid-cols-2 items-center gap-2 sm:flex sm:flex-wrap">
        {growth("rev_min", "Revenue growth")}
        {growth("ebitda_min", "EBITDA growth")}
        {growth("pat_min", "PAT growth")}
        <Select aria-label="Margin change" className="w-full sm:w-auto" value={filters.opm_min ?? ""} onChange={(e) => setParams({ opm_min: e.target.value || null })}>
          <option value="">Margin change: any</option>
          {MARGIN_STEPS.map((n) => <option key={n} value={n}>Margin up ≥ {n}bp</option>)}
        </Select>
        <button type="button" aria-pressed={filters.turnaround === "1"} onClick={() => setParams({ turnaround: filters.turnaround === "1" ? null : "1" })}
          className={cn("h-9 rounded-lg border px-3 text-[13px] font-medium", filters.turnaround === "1" ? "border-accent bg-accent-soft text-accent" : "border-line bg-surface text-ink-2 hover:border-line-strong")}>
          Loss to profit
        </button>
        {active > 0 && (
          <button type="button" className="text-[13px] font-medium text-accent hover:underline"
            onClick={() => { setText(""); setParams({ size: null, q: null, rev_min: null, ebitda_min: null, pat_min: null, opm_min: null, turnaround: null }); }}>
            Clear filters
          </button>
        )}
      </div>

      {first && (
        <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
          <Stat label="Companies" value={first.summary.n} />
          <Stat label="Revenue up" value={first.summary.revenue_up} of={first.summary.n} />
          <Stat label="EBITDA up" value={first.summary.ebitda_up} of={first.summary.n} />
          <Stat label="PAT up" value={first.summary.pat_up} of={first.summary.n} />
          <Stat label="Loss to profit" value={first.summary.turnarounds} />
        </dl>
      )}

      <div className="mt-4">
        {query.isPending ? <Loading /> : !query.data ? <Empty title="Couldn't load results" body={String(query.error)} /> : rows.length === 0 ? (
          <Empty title="No company matches" body={active ? "Loosen a filter to see more." : "Results appear here once a company's statements for the quarter are saved."} />
        ) : (
          <div className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full min-w-[880px] text-[13.5px]">
              <thead className="eyebrow border-b border-line text-left text-ink-3">
                <tr>
                  <Th sortKey="company" {...{ sort, dir, sortBy }} className="pl-[17px]">Company</Th>
                  <Th sortKey="mcap" {...{ sort, dir, sortBy }} right>Market cap</Th>
                  <Th sortKey="revenue_yoy" {...{ sort, dir, sortBy }} right>Revenue</Th>
                  <Th sortKey="ebitda_yoy" {...{ sort, dir, sortBy }} right>EBITDA</Th>
                  <Th sortKey="opm_yoy_bps" {...{ sort, dir, sortBy }} right>EBITDA margin</Th>
                  <Th sortKey="pat_yoy" {...{ sort, dir, sortBy }} right>PAT</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => <Row key={r.scrip_code} row={r} onOpen={() => navigate(`${companyPath(r)}?tab=results`)} />)}
              </tbody>
            </table>
            {(query.hasNextPage || query.isFetchNextPageError) && (
              <div className="border-t border-line p-3 text-center">
                <Button size="sm" onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage}>
                  {query.isFetchNextPageError ? "Couldn't load more · retry" : "Load more"}
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
      <p className="mt-3 text-xs text-ink-3">
        ₹ crore, consolidated where the company files it, else standalone. Growth is against the same quarter a year ago; the small line is against the previous quarter.
        Built from NSE results files and our saved statements. Information only, not investment advice.
      </p>
    </div>
  );
}

function Stat({ label, value, of }: { label: string; value: number; of?: number }) {
  return (
    <div className="rounded-xl border border-line bg-surface px-3.5 py-2.5">
      <dt className="eyebrow text-ink-3">{label}</dt>
      <dd className="num mt-0.5 text-[20px] font-semibold text-ink">
        {value.toLocaleString("en-IN")}
        {of != null && of > 0 && <span className="ml-1.5 text-[12px] font-medium text-ink-3">{Math.round((value / of) * 100)}%</span>}
      </dd>
    </div>
  );
}

function Th({ sortKey, sort, dir, sortBy, right, className, children }:
  { sortKey: KpiSort; sort: KpiSort; dir: "asc" | "desc"; sortBy: (k: KpiSort) => void; right?: boolean; className?: string; children: ReactNode }) {
  const on = sort === sortKey;
  return (
    <th aria-sort={on ? (dir === "asc" ? "ascending" : "descending") : "none"} className={cn("px-3 py-3 font-semibold", right && "text-right", className)}>
      <button type="button" onClick={() => sortBy(sortKey)} className={cn("inline-flex items-center gap-1 uppercase tracking-[inherit] hover:text-ink", on && "text-ink")}>
        {children}
        {on && (dir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
      </button>
    </th>
  );
}

/** A growth cell: the change against a year ago, big; the figure and the change against the last quarter, small. */
function Kpi({ value, yoy, turn, qoq, unit }: { value: number | null; yoy: number | null; turn?: string | null; qoq: number | null; unit?: "bp" }) {
  return (
    <td className="px-3 py-2.5 text-right">
      <div><Change value={yoy} turn={turn ?? undefined} unit={unit} /></div>
      <div className="mt-0.5 text-[11.5px] text-ink-3">
        {unit === "bp" ? (value == null ? "—" : `${value.toFixed(1)}%`) : value == null ? "—" : cr(value)}
        {qoq != null && <span className="ml-1.5">QoQ {unit === "bp" ? `${qoq > 0 ? "+" : ""}${Math.round(qoq)}bp` : `${qoq > 0 ? "+" : ""}${qoq.toFixed(1)}%`}</span>}
      </div>
    </td>
  );
}

function Row({ row, onOpen }: { row: KpiRow; onOpen: () => void }) {
  return (
    <tr onClick={onOpen} tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen(); } }}
      className="num cursor-pointer border-b border-line hover:bg-surface-2/60">
      <td className="py-2.5 pl-[17px] pr-3">
        <span className="flex items-center gap-2">
          <Avatar name={row.company_name ?? row.scrip_code} symbol={row.symbol} size={22} />
          <span className="min-w-0">
            <span className="block font-sans font-semibold text-ink">{row.symbol ?? row.scrip_code}</span>
            <span className="block max-w-[220px] truncate font-sans text-[11.5px] text-ink-3">
              {row.company_name}{row.basis === "STANDALONE" && " · standalone"}
            </span>
          </span>
        </span>
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 text-right text-ink-2">{cr(row.market_cap_cr)}</td>
      <Kpi value={row.revenue} yoy={row.revenue_yoy} qoq={row.revenue_qoq} />
      <Kpi value={row.ebitda} yoy={row.ebitda_yoy} turn={row.ebitda_turn} qoq={row.ebitda_qoq} />
      <Kpi value={row.opm} yoy={row.opm_yoy_bps} qoq={row.opm_qoq_bps} unit="bp" />
      <Kpi value={row.pat} yoy={row.pat_yoy} turn={row.pat_turn} qoq={row.pat_qoq} />
    </tr>
  );
}
