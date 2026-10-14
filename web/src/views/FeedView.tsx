import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Filter, Loader2, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { NoiseRow } from "../../shared/types";
import { SuperCard } from "../components/SuperCard";
import { Pill } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Switch } from "../components/ui/switch";
import { api, type FeedFilters } from "../lib/api";
import { addDays, istDateTime, titleCase, todayIST } from "../lib/format";
import { EVENT_LABELS, IMPACTS, IMPACT_LABEL, SIZES } from "../lib/taxonomy";
import { toggleInList, useQueryState } from "../lib/url";

const PRESETS: { label: string; days: number | null }[] = [
  { label: "Today", days: 0 },
  { label: "7D", days: 7 },
  { label: "30D", days: 30 },
  { label: "2026", days: null },
];

export function FeedView() {
  const [params, setParams] = useQueryState();
  const noise = params.get("noise") === "1";
  const shared = params.get("card");
  const today = todayIST();
  const filters: FeedFilters = {
    from: params.get("from") ?? addDays(today, -7),
    to: params.get("to") ?? today,
    impact: params.get("impact") ?? undefined,
    category: params.get("category") ?? undefined,
    size: params.get("size") ?? undefined,
    q: params.get("q") ?? undefined,
  };

  return (
    <div className="mx-auto w-full max-w-5xl">
      <FilterRibbon filters={filters} noise={noise} setParams={setParams} />
      <div className="space-y-4 px-4 py-4 sm:px-6">
        {shared && !noise && <SharedCard id={shared} onClose={() => setParams({ card: null })} />}
        {noise ? <NoiseAudit date={filters.to ?? today} /> : <CardList filters={filters} />}
      </div>
    </div>
  );
}

function FilterRibbon({
  filters, noise, setParams,
}: {
  filters: FeedFilters;
  noise: boolean;
  setParams: ReturnType<typeof useQueryState>[1];
}) {
  const [text, setText] = useState(filters.q ?? "");
  const [open, setOpen] = useState(false);
  useEffect(() => setText(filters.q ?? ""), [filters.q]);
  useEffect(() => {
    const id = setTimeout(() => {
      if ((filters.q ?? "") !== text) setParams({ q: text || null });
    }, 300);
    return () => clearTimeout(id);
  }, [text, filters.q, setParams]);

  const today = todayIST();
  const activeCount = [filters.impact, filters.category, filters.size].filter(Boolean).length;

  return (
    <div className="sticky top-0 z-20 border-b border-line bg-bg/95 px-4 py-3 backdrop-blur sm:px-6">
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative min-w-0 flex-1 basis-56">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Filter by company or headline…"
            className="h-9 w-full rounded-md border border-line bg-surface pl-8 pr-14 text-sm text-ink placeholder:text-ink-3 focus:border-forest focus:outline-none"
          />
          <kbd className="num absolute right-2 top-1/2 -translate-y-1/2 rounded border border-line px-1.5 text-[10px] text-ink-3">Ctrl K</kbd>
        </label>
        <div className="flex items-center gap-1">
          {PRESETS.map((p) => {
            const from = p.days === null ? "2026-01-01" : addDays(today, -p.days);
            const active = filters.from === from && filters.to === today;
            return (
              <Pill key={p.label} active={active} onClick={() => setParams({ from, to: today })}>
                {p.label}
              </Pill>
            );
          })}
        </div>
        <div className="flex items-center gap-1 text-xs text-ink-2">
          <input
            type="date"
            aria-label="From date"
            value={filters.from}
            min="2026-01-01"
            onChange={(e) => setParams({ from: e.target.value || null })}
            className="num h-8 rounded-md border border-line bg-surface px-2 text-xs text-ink"
          />
          <span>–</span>
          <input
            type="date"
            aria-label="To date"
            value={filters.to}
            onChange={(e) => setParams({ to: e.target.value || null })}
            className="num h-8 rounded-md border border-line bg-surface px-2 text-xs text-ink"
          />
        </div>
        <Button size="sm" variant={open ? "forest" : "outline"} onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          <Filter className="h-3.5 w-3.5" /> Filters{activeCount ? ` (${activeCount})` : ""}
        </Button>
        <label className="flex items-center gap-2 text-xs font-medium text-ink-2">
          <Switch checked={noise} onCheckedChange={(v) => setParams({ noise: v ? "1" : null })} />
          Noise audit
        </label>
      </div>

      {open && (
        <div className="mt-3 space-y-2.5">
          <PillRow label="Impact">
            {IMPACTS.map((i) => (
              <Pill key={i} active={!!filters.impact?.split(",").includes(i)} onClick={() => setParams({ impact: toggleInList(filters.impact ?? null, i) })}>
                {IMPACT_LABEL[i]}
              </Pill>
            ))}
          </PillRow>
          <PillRow label="Event">
            {Object.entries(EVENT_LABELS).map(([key, label]) => (
              <Pill key={key} active={!!filters.category?.split(",").includes(key)} onClick={() => setParams({ category: toggleInList(filters.category ?? null, key) })}>
                {label}
              </Pill>
            ))}
          </PillRow>
          <PillRow label="Market cap">
            {SIZES.map((s) => (
              <Pill key={s} active={!!filters.size?.split(",").includes(s)} onClick={() => setParams({ size: toggleInList(filters.size ?? null, s) })}>
                {titleCase(s)}
              </Pill>
            ))}
          </PillRow>
          {activeCount > 0 && (
            <Button size="sm" variant="ghost" onClick={() => setParams({ impact: null, category: null, size: null })}>
              <X className="h-3.5 w-3.5" /> Clear filters
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function PillRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <span className="w-20 shrink-0 pt-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-3">{label}</span>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function CardList({ filters }: { filters: FeedFilters }) {
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
  if (query.isError) return <Empty title="Could not load the feed" body={String(query.error)} />;
  const cards = query.data.pages.flatMap((p) => p.cards);
  if (!cards.length) {
    return <Empty title="No material filings match" body="Widen the date range or clear filters. The noise audit shows what was filtered out." />;
  }
  return (
    <>
      {cards.map((row) => (
        <SuperCard key={row.news_id} row={row} />
      ))}
      <div ref={sentinel} className="flex justify-center py-4">
        {isFetchingNextPage ? <Loader2 className="h-5 w-5 animate-spin text-ink-3" /> : hasNextPage ? (
          <Button variant="outline" size="sm" onClick={() => fetchNextPage()}>Load more</Button>
        ) : (
          <span className="text-xs text-ink-3">End of results</span>
        )}
      </div>
    </>
  );
}

function SharedCard({ id, onClose }: { id: string; onClose: () => void }) {
  const query = useQuery({ queryKey: ["card", id], queryFn: () => api.card(id) });
  if (!query.data) return null;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-forest">
        Shared card
        <Button size="sm" variant="ghost" onClick={onClose}>
          <X className="h-3.5 w-3.5" /> Dismiss
        </Button>
      </div>
      <SuperCard row={query.data} highlight />
    </div>
  );
}

const STATUS_LABEL: Record<string, string> = {
  DROPPED_RULE: "Rule filter",
  NOT_MATERIAL: "AI: not material",
};

function NoiseAudit({ date }: { date: string }) {
  const query = useInfiniteQuery({
    queryKey: ["noise", date],
    queryFn: ({ pageParam }) => api.noise(date, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset,
  });
  if (query.isPending) return <Loading />;
  if (query.isError) return <Empty title="Could not load the noise audit" body={String(query.error)} />;
  const rows: NoiseRow[] = query.data.pages.flatMap((p) => p.rows);
  return (
    <section className="rounded-xl border border-line bg-surface">
      <header className="border-b border-line px-4 py-3">
        <h2 className="font-display text-sm font-bold">Noise audit · {date}</h2>
        <p className="text-xs text-ink-2">Filings that were filtered out, and why. Spot-check these to tune the rules.</p>
      </header>
      {rows.length === 0 ? (
        <p className="px-4 py-6 text-sm text-ink-3">Nothing was filtered on this date.</p>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((r) => (
            <li key={r.news_id} className="flex flex-col gap-1 px-4 py-2.5 text-sm sm:flex-row sm:items-center sm:gap-3">
              <span className="num w-28 shrink-0 text-xs text-ink-3">{istDateTime(r.filed_at).split(", ").pop()}</span>
              <span className="min-w-0 flex-1">
                <span className="font-medium text-ink">{r.company_name}</span>
                <span className="text-ink-2"> · {r.headline}</span>
              </span>
              <span className="shrink-0 text-xs text-ink-3">
                {STATUS_LABEL[r.status] ?? r.status}
                {r.reason ? `: ${r.reason}` : ""}
              </span>
              {r.pdf_url && (
                <a className="shrink-0 text-xs text-forest hover:underline" href={r.pdf_url} target="_blank" rel="noreferrer">
                  PDF
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
      {query.hasNextPage && (
        <div className="border-t border-line p-3 text-center">
          <Button size="sm" onClick={() => query.fetchNextPage()}>Load more</Button>
        </div>
      )}
    </section>
  );
}

export function Loading() {
  return (
    <div className="flex justify-center py-16">
      <Loader2 className="h-6 w-6 animate-spin text-ink-3" />
    </div>
  );
}

export function Empty({ title, body }: { title: string; body?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-surface px-6 py-14 text-center">
      <p className="font-display text-base font-semibold text-ink">{title}</p>
      {body ? <p className="mx-auto mt-1 max-w-md text-sm text-ink-2">{body}</p> : null}
    </div>
  );
}
