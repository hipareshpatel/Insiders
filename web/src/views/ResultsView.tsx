import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { ArrowDownUp, ChevronDown, Download, SlidersHorizontal } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import type { Cut, GroupBy, GroupRow, KpiRow, View } from "../../shared/resultsTypes";
import { CompanyTable, PhoneList, rowKey, TableSkeleton } from "../components/results/CompanyTable";
import { Chips, FilterBar, SearchBox, VIEWS } from "../components/results/FilterBar";
import { FilterSheet } from "../components/results/FilterSheet";
import { GroupsView } from "../components/results/GroupsView";
import { PeekPanel } from "../components/results/PeekPanel";
import { SeasonPanel } from "../components/results/SeasonPanel";
import { SegControl, useDismiss } from "../components/results/bits";
import { Button } from "../components/ui/button";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { TURN, turnOf } from "../lib/results";
import {
  activeChips, csvName, firstDir, VIEW_SORT, viewOf, fmtCount, growthCount, growthOf, indexLabel, newestFiled, quarterLabel, quarterMonths, readQuery, toApiParams,
  toCsv, type Sort, type SpreadKey,
} from "../lib/resultsView";
import { useQueryState } from "../lib/url";

export { turnOf };

/** A change against a year ago in a company page's line (the company page's Results tab uses it). */
export function Change({ value, unit = "%", turn }: { value?: number | null; unit?: "%" | "bp"; turn?: string }) {
  if (turn && TURN[turn]) return <span className={cn("whitespace-nowrap font-semibold", TURN[turn][1])}>{TURN[turn][0]}</span>;
  if (value == null) return <span className="text-ink-3">—</span>;
  const text = unit === "bp" ? `${value > 0 ? "+" : ""}${Math.round(value)}bp` : `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
  return <span className={cn("font-semibold", value > 0 ? "text-pos" : value < 0 ? "text-neg" : "text-ink-2")}>{text}</span>;
}

const SORT_LABEL: Record<Sort, string> = {
  company: "name", mcap: "market cap", revenue_yoy: "revenue growth", ebitda_yoy: "EBITDA growth", opm_yoy_bps: "margin change", pat_yoy: "profit growth",
  revenue_qoq: "revenue vs last quarter", ebitda_qoq: "EBITDA vs last quarter", opm_qoq_bps: "margin vs last quarter", pat_qoq: "profit vs last quarter",
  pat_momentum: "profit pace", revenue_momentum: "revenue pace", ebitda_momentum: "EBITDA pace", filed: "filing date",
};
/** The direction in words: a name runs A to Z, every figure highest first (it was "reversed", which said nothing). */
const dirWords = (sort: Sort, dir: "asc" | "desc") => (sort === "company" ? (dir === "asc" ? "A to Z" : "Z to A") : dir === "desc" ? "highest first" : "lowest first");
const PHONE_SORTS: Sort[] = ["pat_yoy", "revenue_yoy", "ebitda_yoy", "opm_yoy_bps", "pat_momentum", "mcap", "filed", "company"];
const MAX_EXPORT_PAGES = 40;

/** The Results page as a KPI report (Direction C, docs/design/results-kpi.md): one quarter's growth from each company's saved statements
 *  (never a card's), the season in a few plain sentences, filters and sorts over every company of the quarter, and the same numbers by
 *  index, sector or industry. Every filter lives in the URL, so a view is a link. */
export function ResultsView() {
  const [params, setParams] = useQueryState();
  const query = useMemo(() => readQuery(params), [params]);
  const tab = params.get("tab") === "groups" ? "groups" : "companies";
  const view: View = viewOf(params);
  const by: GroupBy = params.get("by") === "sector" ? "sector" : params.get("by") === "industry" ? "industry" : "index";
  const cut: Cut = params.get("cut") === "ex_financials" ? "ex_financials" : params.get("cut") === "financials" ? "financials" : "all";
  const peekKey = params.get("peek");
  const set = useCallback((c: Record<string, string | null | undefined>) => setParams(c), [setParams]);

  const apiParams = toApiParams(query, 1);
  const kpi = useInfiniteQuery({
    queryKey: ["results-kpi", apiParams],
    queryFn: ({ pageParam }) => api.resultsKpi(toApiParams(query, pageParam)),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page < last.pages ? last.page + 1 : undefined),
    placeholderData: keepPreviousData,
  });
  const first = kpi.data?.pages[0];
  const rows = useMemo(() => kpi.data?.pages.flatMap((p) => p.rows) ?? [], [kpi.data]);
  const quarter = first?.quarter ?? query.quarter;
  const quarters = first?.quarters ?? [];

  // the indices' medians and trends, for the season's lines and mini charts (the same request as By group, by index, all companies)
  const groups = useQuery({
    queryKey: ["results-groups", quarter, "index", "all"],
    queryFn: () => api.resultsGroups({ quarter, by: "index", cut: "all" }),
    enabled: tab === "companies" && !!first,
    staleTime: 5 * 60_000,
  });
  const indexRows: GroupRow[] | undefined = groups.data?.rows ?? (groups.isError ? [] : undefined);

  // the side panel: a row already loaded, else the company's own rows (a shared link to a row on a later page)
  const loaded = peekKey ? rows.find((r) => rowKey(r) === peekKey) : undefined;
  const company = useQuery({
    queryKey: ["results-company", peekKey],
    queryFn: () => api.resultsCompany(peekKey!),
    enabled: !!peekKey && !loaded && !!first,
  });
  const peekRow: KpiRow | undefined = loaded ?? (company.data?.rows.find((r) => r.period === quarter) ?? company.data?.rows[company.data.rows.length - 1]);
  const select = useCallback((r: KpiRow | null) => setParams({ peek: r ? rowKey(r) : null }), [setParams]);

  const onSort = (s: Sort) => {
    const dir = s === query.sort ? (query.dir === "desc" ? "asc" : "desc") : firstDir(s);
    setParams({ sort: s === VIEW_SORT[view] ? null : s, dir: dir === firstDir(s) ? null : dir });
  };
  const onView = (v: View) => setParams({ view: v === "yoy" ? null : v, sort: null, dir: null });
  const onPickGroup = (r: GroupRow, groupBy: GroupBy) =>
    setParams(groupBy === "index" ? { tab: null, index: r.id, class: null, spread: null } : { tab: null, class: r.id, index: null, spread: null });

  const [sheet, setSheet] = useState(false);
  const filtered = activeChips(query).length > 0;
  const summary = first?.summary;
  const total = summary?.n ?? 0;
  const noMatch = filtered && !!first && !kpi.isPlaceholderData && summary?.n === 0;

  return (
    <div className="results-c min-h-full">
      <div className="mx-auto w-full max-w-[1360px] px-4 pb-16 sm:px-10">
        <header className="pt-[18px] sm:flex sm:items-end sm:justify-between sm:gap-6 sm:pt-[34px]">
          <div>
            <h1 className="text-[30px] font-bold leading-[1.05] tracking-[-0.025em] text-ink sm:text-[40px]">
              Results{quarter && <span className="font-medium text-ink-2"> {quarterLabel(quarter)}</span>}
            </h1>
            <p className="mt-2 text-[14px] text-ink-2">{quarter ? `${quarterMonths(quarter)} · ` : ""}growth is against the same quarter a year ago</p>
          </div>
          <div className="mt-3.5 flex flex-wrap items-center gap-2.5 sm:mt-0">
            <QuarterSwitch quarters={quarters} value={quarter} onChange={(p) => setParams({ quarter: p === quarters[0]?.period ? null : p, peek: null, spread: null })} />
            <ExportButton rows={rows} total={total} quarter={quarter} pages={first?.pages ?? 1} loadedPages={kpi.data?.pages.length ?? 0}
              fetchPage={(p) => api.resultsKpi(toApiParams(query, p))} />
          </div>
        </header>
        <Fresh rows={rows} className="mt-2.5 sm:hidden" />

        <nav className="mt-4 flex items-end gap-[22px] border-b border-line sm:mt-[26px] sm:gap-7" role="tablist" aria-label="Results views">
          {(["companies", "groups"] as const).map((t) => (
            <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setParams({ tab: t === "companies" ? null : t, peek: null })}
              className={cn("-mb-px min-h-11 border-b-2 pb-3 pt-2.5 text-[15px] font-semibold", tab === t ? "border-accent text-ink" : "border-transparent text-ink-2 hover:text-ink")}>
              {t === "companies" ? "Companies" : "By group"}
            </button>
          ))}
          <Fresh rows={rows} className="mb-3 ml-auto hidden sm:block" />
        </nav>

        {kpi.isError && !first ? (
          <div className="mt-7 rounded-2xl bg-surface-2 px-6 py-16 text-center" role="alert">
            <p className="text-[17px] font-semibold text-ink">Couldn't load the results</p>
            <p className="mx-auto mt-1 max-w-md text-[14px] text-ink-2">The server did not answer ({kpi.error?.message}). Your filters are kept in the address; try again in a moment.</p>
            <Button className="mt-4" onClick={() => kpi.refetch()}>Try again</Button>
          </div>
        ) : tab === "groups" ? (
          <GroupsView quarter={quarter} by={by} cut={cut} setParams={set} onPick={onPickGroup} />
        ) : (
          <>
            {/* nothing matches: one card below says so, not tiles of "0 of 0" */}
            {!noMatch && (
              <SeasonPanel summary={summary} indexRows={indexRows} filtered={filtered}
                spread={query.spread} turnaround={query.turnaround}
                onSpread={(k: SpreadKey | null) => setParams({ spread: k, turnaround: null })} onTurnaround={(on) => setParams({ turnaround: on ? "1" : null, spread: null })} />
            )}

            <FilterBar query={query} view={view} indices={first?.indices ?? []} setParams={set} onView={onView} />

            {/* phone: title, filters, sort, search and the view */}
            <div className="sticky top-0 z-20 -mx-4 mt-6 bg-surface px-4 pb-2 pt-2.5 sm:hidden">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-[19px] font-bold text-ink">Companies</h2>
                <div className="flex gap-2">
                  <Button className="h-11 rounded-[11px] border-0 bg-surface-2 px-3.5 text-[14px] font-semibold" onClick={() => setSheet(true)}>
                    <SlidersHorizontal aria-hidden className="h-4 w-4" />Filters
                    {growthCount(growthOf(query)) + (query.index ? 1 : 0) + (query.mcap_min != null ? 1 : 0) + (query.class ? 1 : 0) > 0 && (
                      <span className="num rounded-full bg-accent px-[7px] text-[12px] leading-5 text-accent-ink">
                        {growthCount(growthOf(query)) + (query.index ? 1 : 0) + (query.mcap_min != null ? 1 : 0) + (query.class ? 1 : 0)}
                      </span>
                    )}
                  </Button>
                  <PhoneSort sort={query.sort} dir={query.dir} onSort={onSort} />
                </div>
              </div>
            </div>
            <div className="sm:hidden">
              <SearchBox q={query.q} setParams={set} className="h-11" />
              <SegControl className="mt-2.5 flex w-full" itemClass="min-h-11 flex-1 px-2" label="View" items={VIEWS.map((v) => ({ ...v, label: v.key === "qoq" ? "QoQ" : v.label }))}
                value={view} onChange={onView} />
              <Chips query={query} setParams={set} />
            </div>

            <div className="mb-2 mt-[26px] hidden items-end justify-between gap-5 sm:flex">
              <div>
                <h2 className="text-[20px] font-bold tracking-[-0.01em] text-ink">{view === "momentum" ? "Momentum" : view === "qoq" ? "Quarter-on-quarter" : "Companies"}</h2>
                <p className="text-[13.5px] text-ink-2">
                  {view === "momentum" && summary
                    ? `Is profit growth speeding up or slowing? ${fmtCount(summary.momentum.speeding_up)} speeding up · ${fmtCount(summary.momentum.slowing)} slowing · ${fmtCount(summary.momentum.steady + summary.momentum.not_comparable)} steady or not comparable`
                    : view === "qoq" ? `${quarterLabel(quarter)} against the quarter just before it · sorted by ${SORT_LABEL[query.sort]}, ${dirWords(query.sort, query.dir)}`
                    : `Growth vs the same quarter a year ago · sorted by ${SORT_LABEL[query.sort]}, ${dirWords(query.sort, query.dir)}`}
                </p>
              </div>
              <p className="num text-right text-[13.5px] text-ink-2">{summary ? `${fmtCount(total)} ${total === 1 ? "company" : "companies"} · ${query.index ? indexLabel(query.index) : "all indices"}` : ""}</p>
            </div>
            <p className="mb-1 mt-3 text-[13px] text-ink-3 sm:hidden">
              {summary ? `${fmtCount(rows.length)} of ${fmtCount(total)} · ${SORT_LABEL[query.sort]}, ${dirWords(query.sort, query.dir)}` : ""}
            </p>

            <div className={cn("transition-opacity", kpi.isPlaceholderData && "opacity-60")} aria-busy={kpi.isFetching}>
              {!first ? <TableSkeleton /> : rows.length === 0 ? (
                <div className="rounded-2xl bg-surface-2 px-6 py-14 text-center">
                  <p className="text-[17px] font-semibold text-ink">{filtered ? "No companies match these filters" : `No results saved for ${quarterLabel(quarter)} yet`}</p>
                  <p className="mx-auto mt-1 max-w-md text-[14px] text-ink-2">
                    {filtered ? "Loosen or remove a filter to see more companies." : "Companies appear here once their statements for the quarter are saved."}
                  </p>
                  {filtered && <Button className="mt-4 h-11" onClick={() => setParams(Object.fromEntries(activeChips(query).flatMap((c) => c.clear).map((k) => [k, null])))}>Clear all</Button>}
                </div>
              ) : (
                <>
                  <div className="hidden sm:block">
                    <CompanyTable rows={rows} view={view} sort={query.sort} dir={query.dir} onSort={onSort} selected={peekKey} onSelect={select} />
                  </div>
                  <div className="sm:hidden"><PhoneList rows={rows} onSelect={select} /></div>
                  <div className="flex flex-col items-stretch gap-3 py-4 text-[13px] text-ink-3 sm:flex-row sm:items-center sm:justify-between sm:px-3">
                    <span className="hidden sm:inline">
                      Showing {fmtCount(rows.length)} of {fmtCount(total)}
                      {view === "momentum" ? " · points = this quarter's growth vs a year ago minus last quarter's" : " · small grey line: amount this quarter · “was” = last quarter's growth vs a year ago"}
                    </span>
                    {(kpi.hasNextPage || kpi.isFetchNextPageError) && (
                      <Button className="h-12 justify-center rounded-[11px] border-0 bg-surface-2 font-semibold text-ink sm:h-[38px]" onClick={() => kpi.fetchNextPage()} disabled={kpi.isFetchingNextPage}>
                        {kpi.isFetchNextPageError ? "Couldn't load more · retry" : kpi.isFetchingNextPage ? "Loading…" : `Show more (${fmtCount(total - rows.length)} left)`}
                      </Button>
                    )}
                  </div>
                </>
              )}
            </div>
            <FilterSheet open={sheet} onOpenChange={setSheet} query={query} indices={first?.indices ?? []} setParams={set} />
          </>
        )}
        <p className="mt-6 text-[12.5px] text-ink-3">
          ₹ crore. Figures are worked out from each company's saved statements (consolidated where filed, else standalone), reported profit as filed,
          not adjusted. Information only, not investment advice.
        </p>
      </div>
      {tab === "companies" && peekRow && <PeekPanel row={peekRow} onClose={() => select(null)} />}
    </div>
  );
}

function Fresh({ rows, className }: { rows: KpiRow[]; className?: string }) {
  const at = newestFiled(rows);
  return <p className={cn("text-[13px] text-ink-3", className)}>{at ? `Latest filing shown: ${at}` : " "}</p>;
}

/** The last four quarters as a switch, and the rest in an "Older" menu. */
function QuarterSwitch({ quarters, value, onChange }: { quarters: { period: string; n: number }[]; value: string | null; onChange: (p: string) => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const refs = useMemo(() => [box], []);
  useDismiss(open, () => setOpen(false), refs);
  if (!quarters.length) return <span className="inline-block h-[46px] w-[380px] max-w-full rounded-xl bg-surface-2" aria-hidden />;
  const recent = quarters.slice(0, 4), older = quarters.slice(4);
  const olderOn = older.some((q) => q.period === value);
  return (
    <div ref={box} className="relative inline-flex max-w-full flex-wrap gap-0.5 rounded-xl bg-surface-2 p-1 max-sm:w-full" role="group" aria-label="Quarter">
      {recent.map((q) => (
        <button key={q.period} type="button" aria-pressed={q.period === value} onClick={() => onChange(q.period)} title={`${q.n} companies`}
          className={cn("min-h-[38px] whitespace-nowrap rounded-[9px] px-3 text-[13.5px] font-semibold max-sm:min-h-11 max-sm:flex-1 max-sm:px-2",
            q.period === value ? "bg-surface text-ink shadow-[inset_0_0_0_1px_var(--line-strong)]" : "text-ink-2 hover:text-ink")}>
          {q.period}
        </button>
      ))}
      {older.length > 0 && (
        <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)}
          className={cn("inline-flex min-h-[38px] items-center gap-1 whitespace-nowrap rounded-[9px] px-3 text-[13.5px] font-semibold max-sm:min-h-11 max-sm:flex-1 max-sm:justify-center max-sm:px-2",
            olderOn ? "bg-surface text-ink shadow-[inset_0_0_0_1px_var(--line-strong)]" : "text-ink-2 hover:text-ink")}>
          {olderOn ? value : "Older"}<ChevronDown aria-hidden className="h-3.5 w-3.5" />
        </button>
      )}
      {open && (
        <div role="menu" className="absolute right-0 top-full z-30 mt-2 max-h-[320px] w-[200px] overflow-y-auto rounded-2xl bg-surface p-2 shadow-[0_0_0_1px_var(--line-strong),0_24px_60px_-24px_rgba(20,30,50,0.25)]">
          {older.map((q) => (
            <button key={q.period} type="button" role="menuitemradio" aria-checked={q.period === value} onClick={() => { onChange(q.period); setOpen(false); }}
              className={cn("flex w-full justify-between rounded-[9px] px-2.5 py-2 text-[13.5px]", q.period === value ? "bg-accent-soft font-semibold text-ink" : "text-ink-2 hover:bg-surface-2")}>
              <span>{q.period}</span><span className="num text-ink-3">{q.n}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** "Export CSV": every company of the filtered list, not only the rows on screen; pages not yet loaded are asked for one by one. */
function ExportButton({ rows, total, quarter, pages, loadedPages, fetchPage }: {
  rows: KpiRow[]; total: number; quarter: string | null; pages: number; loadedPages: number; fetchPage: (p: number) => Promise<{ rows: KpiRow[] }>;
}) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const run = async () => {
    setBusy(true); setFailed(false);
    try {
      const all = [...rows];
      for (let p = loadedPages + 1; p <= Math.min(pages, MAX_EXPORT_PAGES); p++) all.push(...(await fetchPage(p)).rows);
      const url = URL.createObjectURL(new Blob([toCsv(all)], { type: "text/csv;charset=utf-8" }));
      const a = Object.assign(document.createElement("a"), { href: url, download: csvName(quarter) });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button onClick={run} disabled={busy || !total} title={`Download the filtered list (all ${total} companies, every column) as a CSV file`}
      className="h-11 rounded-[11px] border-0 bg-surface-2 px-3.5 text-[13.5px] font-semibold text-ink sm:h-[38px]">
      <Download aria-hidden className="h-4 w-4" />{busy ? "Preparing…" : failed ? "Export failed · retry" : "Export CSV"}
    </Button>
  );
}

/** The phone's sort menu. */
function PhoneSort({ sort, dir, onSort }: { sort: Sort; dir: "asc" | "desc"; onSort: (s: Sort) => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const refs = useMemo(() => [box], []);
  useDismiss(open, () => setOpen(false), refs);
  return (
    <div ref={box} className="relative">
      <Button aria-expanded={open} className="h-11 rounded-[11px] border-0 bg-surface-2 px-3.5 text-[14px] font-semibold" onClick={() => setOpen((o) => !o)}>
        Sort <ArrowDownUp aria-hidden className="h-4 w-4" />
      </Button>
      {open && (
        <div role="menu" className="absolute right-0 top-full z-30 mt-2 w-[240px] rounded-2xl bg-surface p-2 shadow-[0_0_0_1px_var(--line-strong),0_24px_60px_-24px_rgba(20,30,50,0.25)]">
          {PHONE_SORTS.map((s) => (
            <button key={s} type="button" role="menuitemradio" aria-checked={s === sort} onClick={() => { onSort(s); setOpen(false); }}
              className={cn("flex min-h-11 w-full items-center justify-between rounded-[9px] px-3 text-left text-[14px]", s === sort ? "bg-accent-soft font-semibold text-ink" : "text-ink-2")}>
              <span className="first-letter:uppercase">{SORT_LABEL[s]}</span>
              {s === sort && <span className="text-[12.5px] text-ink-3">{dir === "desc" ? "highest first" : "lowest first"}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
