import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Loader2, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { NoiseRow } from "../../shared/types";
import { FilingRow } from "../components/FilingCard";
import { Select, TabStrip } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { api, type FeedFilters } from "../lib/api";
import { addDays, istDateTime, todayIST } from "../lib/format";
import { FEED_TABS, SECTORS, SIZES } from "../lib/taxonomy";
import { useQueryState } from "../lib/url";

const RANGES = [
  { key: "today", label: "Today", days: 0 },
  { key: "7d", label: "Last 7 days", days: 7 },
  { key: "30d", label: "Last 30 days", days: 30 },
  { key: "ytd", label: "Since 1 Jan 2026", days: null },
] as const;

export function FeedView() {
  const [params, setParams] = useQueryState();
  const today = todayIST();
  const tabKey = params.get("tab") ?? "all";
  const tab = FEED_TABS.find((t) => t.key === tabKey) ?? FEED_TABS[0];
  const rangeKey = params.get("range") ?? "7d";
  const range = RANGES.find((r) => r.key === rangeKey) ?? RANGES[1];
  const from = range.days === null ? "2026-01-01" : addDays(today, -range.days);
  const shared = params.get("card");
  const filters: FeedFilters = {
    from, to: today,
    impact: tab.impact, category: tab.category,
    size: params.get("size") ?? undefined,
    sector: params.get("sector") ?? undefined,
    q: params.get("q") ?? undefined,
  };

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6">
      <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-[30px] leading-tight text-ink">Live filings</h1>
          <p className="mt-1 text-sm text-ink-2">Every material BSE filing, read against what each company said and did before.</p>
        </div>
      </header>

      <TabStrip items={FEED_TABS.map((t) => ({ key: t.key, label: t.label }))} value={tab.key}
        onChange={(key) => setParams({ tab: key === "all" ? null : key, card: null })} />

      {tab.key !== "noise" && (
        <FilterBar params={params} setParams={setParams} />
      )}

      <div className="mt-4 space-y-2">
        {shared && tab.key !== "noise" && <SharedCard id={shared} onClose={() => setParams({ card: null })} />}
        {tab.key === "noise" ? <NoiseAudit date={params.get("date") ?? today} onDate={(d) => setParams({ date: d })} /> : <CardList filters={filters} rangeLabel={range.label} />}
      </div>
    </div>
  );
}

function FilterBar({ params, setParams }: { params: URLSearchParams; setParams: ReturnType<typeof useQueryState>[1] }) {
  const [text, setText] = useState(params.get("q") ?? "");
  const q = params.get("q") ?? "";
  useEffect(() => setText(q), [q]);
  useEffect(() => {
    const id = setTimeout(() => { if (q !== text) setParams({ q: text || null }); }, 300);
    return () => clearTimeout(id);
  }, [text, q, setParams]);
  const active = ["size", "sector", "q", "range"].some((k) => params.get(k));

  return (
    <div className="mt-4 flex flex-wrap items-center gap-2">
      <Select aria-label="Date range" value={params.get("range") ?? "7d"} onChange={(e) => setParams({ range: e.target.value === "7d" ? null : e.target.value })}>
        {RANGES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
      </Select>
      <Select aria-label="Market cap" value={params.get("size") ?? ""} onChange={(e) => setParams({ size: e.target.value || null })}>
        <option value="">All sizes</option>
        {SIZES.map((s) => <option key={s} value={s}>{s.charAt(0) + s.slice(1).toLowerCase()}cap</option>)}
      </Select>
      <Select aria-label="Sector" value={params.get("sector") ?? ""} onChange={(e) => setParams({ sector: e.target.value || null })}>
        <option value="">All sectors</option>
        {Object.entries(SECTORS).filter(([k]) => k !== "default").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </Select>
      <label className="relative min-w-0 flex-1 basis-56">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Filter by company or headline"
          className="h-9 w-full rounded-lg border border-line bg-surface pl-9 pr-3 text-[13px] text-ink placeholder:text-ink-3 hover:border-line-strong focus:border-accent focus:outline-none" />
      </label>
      {active && (
        <Button variant="ghost" size="sm" onClick={() => setParams({ size: null, sector: null, q: null, range: null })}>
          <X className="h-3.5 w-3.5" /> Clear
        </Button>
      )}
    </div>
  );
}

function CardList({ filters, rangeLabel }: { filters: FeedFilters; rangeLabel: string }) {
  const query = useInfiniteQuery({
    queryKey: ["feed", filters],
    queryFn: ({ pageParam }) => api.feed(filters, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
  const sentinel = useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = query;
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) fetchNextPage();
    }, { rootMargin: "600px" });
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  if (query.isPending) return <Loading />;
  if (query.isError) return <Empty title="Couldn't load the feed" body={String(query.error)} />;
  const cards = query.data.pages.flatMap((p) => p.cards);
  if (!cards.length) {
    return <Empty title={`No material filings · ${rangeLabel.toLowerCase()}`} body="Try a wider date range or another tab. The noise audit shows what was filtered out." />;
  }
  return (
    <>
      {cards.map((row) => <FilingRow key={row.news_id} row={row} />)}
      <div ref={sentinel} className="flex justify-center py-5">
        {isFetchingNextPage ? <Loader2 className="h-5 w-5 animate-spin text-ink-3" /> : hasNextPage ? (
          <Button size="sm" onClick={() => fetchNextPage()}>Load more</Button>
        ) : (
          <span className="text-xs text-ink-3">{cards.length} filings · end of results</span>
        )}
      </div>
    </>
  );
}

function SharedCard({ id, onClose }: { id: string; onClose: () => void }) {
  const query = useQuery({ queryKey: ["card", id], queryFn: () => api.card(id) });
  if (!query.data) return null;
  return (
    <div className="mb-4 space-y-2">
      <div className="flex items-center justify-between">
        <span className="eyebrow text-accent">Linked filing</span>
        <Button variant="ghost" size="sm" onClick={onClose}><X className="h-3.5 w-3.5" /> Dismiss</Button>
      </div>
      <FilingRow row={query.data} defaultOpen highlight />
    </div>
  );
}

const STATUS_LABEL: Record<string, string> = { DROPPED_RULE: "Rule filter", NOT_MATERIAL: "AI gatekeeper" };

function NoiseAudit({ date, onDate }: { date: string; onDate: (d: string) => void }) {
  const query = useInfiniteQuery({
    queryKey: ["noise", date],
    queryFn: ({ pageParam }) => api.noise(date, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset,
  });
  const rows: NoiseRow[] = query.data?.pages.flatMap((p) => p.rows) ?? [];
  return (
    <section>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-2">Filings filtered out on this day, and why. Spot-check these to tune the rules.</p>
        <input type="date" aria-label="Day" value={date} onChange={(e) => e.target.value && onDate(e.target.value)}
          className="num h-9 rounded-lg border border-line bg-surface px-3 text-[13px] text-ink" />
      </div>
      {query.isPending ? <Loading /> : query.isError ? <Empty title="Couldn't load the noise audit" body={String(query.error)} /> : rows.length === 0 ? (
        <Empty title="Nothing was filtered on this day" />
      ) : (
        <div className="mt-3 overflow-hidden rounded-xl border border-line bg-surface">
          <table className="w-full text-[13.5px]">
            <thead className="eyebrow border-b border-line text-left text-ink-3">
              <tr><th className="px-4 py-2.5 font-semibold">Time</th><th className="px-4 py-2.5 font-semibold">Filing</th><th className="hidden px-4 py-2.5 font-semibold sm:table-cell">Filtered by</th><th className="px-4 py-2.5" /></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.news_id} className="border-b border-line last:border-0">
                  <td className="num whitespace-nowrap px-4 py-2.5 align-top text-ink-3">{istDateTime(r.filed_at).split(", ").pop()}</td>
                  <td className="px-4 py-2.5">
                    <div className="font-medium text-ink">{r.company_name}</div>
                    <div className="text-ink-2">{r.headline}</div>
                    <div className="text-xs text-ink-3 sm:hidden">{STATUS_LABEL[r.status] ?? r.status}{r.reason ? ` · ${r.reason}` : ""}</div>
                  </td>
                  <td className="hidden px-4 py-2.5 align-top text-ink-2 sm:table-cell">
                    <span className="font-medium text-ink">{STATUS_LABEL[r.status] ?? r.status}</span>
                    {r.reason ? <div className="text-xs text-ink-3">{r.reason}</div> : null}
                  </td>
                  <td className="px-4 py-2.5 text-right align-top">
                    {r.pdf_url && <a className="text-[13px] font-medium text-accent hover:underline" href={r.pdf_url} target="_blank" rel="noreferrer">PDF</a>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {query.hasNextPage && <div className="border-t border-line p-3 text-center"><Button size="sm" onClick={() => query.fetchNextPage()}>Load more</Button></div>}
        </div>
      )}
    </section>
  );
}

export function Loading() {
  return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-ink-3" /></div>;
}

export function Empty({ title, body }: { title: string; body?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-line-strong bg-surface px-6 py-12 text-center">
      <p className="text-[15px] font-medium text-ink">{title}</p>
      {body ? <p className="mx-auto mt-1 max-w-md text-sm text-ink-2">{body}</p> : null}
    </div>
  );
}
