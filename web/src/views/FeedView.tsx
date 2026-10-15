import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, LayoutList, Loader2, Rows3, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "wouter";
import type { NoiseRow } from "../../shared/types";
import { AnnouncementCard } from "../components/AnnouncementCard";
import { Avatar } from "../components/Avatar";
import { FilingRow } from "../components/FilingCard";
import { Badge, Select, TabStrip } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { api, type FeedFilters } from "../lib/api";
import { cn } from "../lib/cn";
import { HISTORY_START } from "../lib/config";
import { addDays, istDate, istDateTime, num, titleCase, todayIST } from "../lib/format";
import { catalystFamily, FEED_TABS, SECTORS, SIZES } from "../lib/taxonomy";
import { useQueryState } from "../lib/url";

type View = "cards" | "list";

const RANGES = [
  { key: "today", label: "Today", days: 0 },
  { key: "7d", label: "Last 7 days", days: 7 },
  { key: "30d", label: "Last 30 days", days: 30 },
  { key: "all", label: "Full history (since 1 Jan 2025)", days: null },
] as const;

export function FeedView() {
  const [params, setParams] = useQueryState();
  const today = todayIST();
  const tabKey = params.get("tab") ?? "all";
  const tab = FEED_TABS.find((t) => t.key === tabKey) ?? FEED_TABS[0];
  const rangeKey = params.get("range") ?? "7d";
  const range = RANGES.find((r) => r.key === rangeKey) ?? RANGES[1];
  const from = range.days === null ? HISTORY_START : addDays(today, -range.days);
  const shared = params.get("card");
  const view: View = params.get("view") === "list" ? "list" : "cards";
  const filters: FeedFilters = {
    from, to: today,
    impact: tab.impact, category: tab.category,
    size: params.get("size") ?? undefined,
    sector: params.get("sector") ?? undefined,
    q: params.get("q") ?? undefined,
    review: params.get("verified") === "1" ? "0" : undefined,
    session: params.get("session") ?? undefined,
    watch: params.get("verified") === "watch" ? "1" : undefined,
  };
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6">
      <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-[30px] leading-tight text-ink">Live filings</h1>
          <p className="mt-1 text-sm text-ink-2">Every material BSE filing, read against what each company said and did before.</p>
        </div>
        {tab.key !== "noise" && (
          <div role="radiogroup" aria-label="Layout" className="inline-flex rounded-lg border border-line bg-surface p-0.5">
            {([["cards", "Cards", Rows3], ["list", "List", LayoutList]] as const).map(([key, label, Icon]) => (
              <button key={key} type="button" role="radio" aria-checked={view === key}
                onClick={() => setParams({ view: key === "cards" ? null : key })}
                className={cn("inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-[13px] font-medium",
                  view === key ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink")}>
                <Icon className="h-4 w-4" />{label}
              </button>
            ))}
          </div>
        )}
      </header>

      <TabStrip items={FEED_TABS.map((t) => ({ key: t.key, label: t.label }))} value={tab.key}
        onChange={(key) => setParams({ tab: key === "all" ? null : key, card: null })} />

      {tab.key !== "noise" && (
        <FilterBar params={params} setParams={setParams} />
      )}

      {tab.key === "noise" ? (
        <div className="mt-4"><NoiseAudit date={params.get("date") ?? today} onDate={(d) => setParams({ date: d })} /></div>
      ) : (
        <div className={cn("mt-5 grid gap-6", view === "cards" && "lg:grid-cols-[minmax(0,1fr)_300px]")}>
          <div className={cn("min-w-0", view === "cards" ? "mx-auto w-full max-w-[720px] space-y-4" : "space-y-2")}>
            {shared && <SharedCard id={shared} view={view} onClose={() => setParams({ card: null })} />}
            <CardList filters={filters} rangeLabel={range.label} view={view} page={page}
              onPage={(n) => { setParams({ page: n > 1 ? String(n) : null }); window.scrollTo({ top: 0 }); }} />
          </div>
          {view === "cards" && <Rail today={today} />}
        </div>
      )}
    </div>
  );
}

function FilterBar({ params, setParams: setRaw }: { params: URLSearchParams; setParams: ReturnType<typeof useQueryState>[1] }) {
  // Any filter change starts again at page 1.
  const setParams = (changes: Record<string, string | null>) => setRaw({ ...changes, page: null });
  const [text, setText] = useState(params.get("q") ?? "");
  const q = params.get("q") ?? "";
  useEffect(() => setText(q), [q]);
  useEffect(() => {
    const id = setTimeout(() => { if (q !== text) setParams({ q: text || null }); }, 300);
    return () => clearTimeout(id);
  }, [text, q, setParams]);
  const active = ["size", "sector", "q", "range", "verified", "session"].some((k) => params.get(k));

  return (
    <div className="mt-4 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center">
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
      <Select aria-label="Market session" value={params.get("session") ?? ""} onChange={(e) => setParams({ session: e.target.value || null })}>
        <option value="">All sessions</option>
        <option value="LIVE_MARKET">Live market (09:15–15:30)</option>
        <option value="AFTER_MARKET,PRE_MARKET,NON_TRADING">After hours &amp; weekend</option>
      </Select>
      <Select aria-label="Verification" value={params.get("verified") ?? ""} onChange={(e) => setParams({ verified: e.target.value || null })}>
        <option value="">All cards</option>
        <option value="1">Verified only</option>
        <option value="watch">★ Watchlist only</option>
      </Select>
      <label className="relative col-span-2 min-w-0 sm:flex-1 sm:basis-56">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Filter by company or headline"
          className="h-9 w-full rounded-lg border border-line bg-surface pl-9 pr-3 text-[13px] text-ink placeholder:text-ink-3 hover:border-line-strong focus:border-accent focus:outline-none" />
      </label>
      {active && (
        <Button variant="ghost" size="sm" onClick={() => setParams({ size: null, sector: null, q: null, range: null, verified: null, session: null })}>
          <X className="h-3.5 w-3.5" /> Clear
        </Button>
      )}
    </div>
  );
}

const PAGE_SIZE = 50;

/** One page of 50 cards with page numbers (the owner's choice over endless scrolling: pages stay
 * light however far back the filters reach). */
function CardList({ filters, rangeLabel, view, page, onPage }: {
  filters: FeedFilters; rangeLabel: string; view: View; page: number; onPage: (n: number) => void;
}) {
  const query = useQuery({
    queryKey: ["feed", filters, page],
    queryFn: () => api.feedPage(filters, page, PAGE_SIZE),
    placeholderData: keepPreviousData,
  });
  if (query.isPending) return <Loading />;
  if (!query.data) return <Empty title="Couldn't load the feed" body={String(query.error)} />;
  const { cards, pages = 1, total = cards.length, total_capped } = query.data;
  if (!cards.length) {
    return <Empty title={`No material filings · ${rangeLabel.toLowerCase()}`} body="Try a wider date range or another tab. The noise audit shows what was filtered out." />;
  }
  return (
    <>
      <p className="num text-xs text-ink-3">
        {total_capped ? `${total.toLocaleString("en-IN")}+` : total.toLocaleString("en-IN")} filings · page {page} of {pages}{total_capped ? "+" : ""}
        {query.isFetching ? <Loader2 className="ml-2 inline h-3.5 w-3.5 animate-spin" /> : null}
      </p>
      {cards.map((row) => view === "cards" ? <AnnouncementCard key={row.news_id} row={row} /> : <FilingRow key={row.news_id} row={row} />)}
      <Pager page={page} pages={pages} capped={!!total_capped} onPage={onPage} />
    </>
  );
}

export function Pager({ page, pages, capped, onPage }: { page: number; pages: number; capped: boolean; onPage: (n: number) => void }) {
  if (pages <= 1) return null;
  const numbers = [...new Set([1, page - 2, page - 1, page, page + 1, page + 2, pages])].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b);
  return (
    <nav aria-label="Pages" className="flex flex-wrap items-center justify-center gap-1 py-5">
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page"
        className="grid h-9 w-9 place-items-center rounded-lg border border-line text-ink-2 enabled:hover:border-accent-line enabled:hover:text-accent disabled:opacity-40">
        <ChevronLeft className="h-4 w-4" />
      </button>
      {numbers.map((n, i) => (
        <span key={n} className="flex items-center gap-1">
          {i > 0 && n - numbers[i - 1] > 1 && <span className="px-1 text-ink-3">…</span>}
          <button type="button" onClick={() => onPage(n)} aria-current={n === page ? "page" : undefined}
            className={cn("num h-9 min-w-9 rounded-lg px-2 text-[13px] font-medium",
              n === page ? "bg-accent text-accent-ink" : "border border-line text-ink-2 hover:border-accent-line hover:text-accent")}>
            {n}{capped && n === pages ? "+" : ""}
          </button>
        </span>
      ))}
      <button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page"
        className="grid h-9 w-9 place-items-center rounded-lg border border-line text-ink-2 enabled:hover:border-accent-line enabled:hover:text-accent disabled:opacity-40">
        <ChevronRight className="h-4 w-4" />
      </button>
    </nav>
  );
}

function SharedCard({ id, view, onClose }: { id: string; view: View; onClose: () => void }) {
  const query = useQuery({ queryKey: ["card", id], queryFn: () => api.card(id), retry: false });
  useEffect(() => window.scrollTo({ top: 0 }), [id]); // a linked card opens at the top of the feed
  if (query.isPending) return <div className="mb-6"><Loading /></div>;
  if (!query.data) {
    return (
      <div className="mb-6 flex items-center justify-between gap-3 rounded-xl border border-dashed border-line-strong px-4 py-3 text-sm text-ink-2">
        <span>That filing could not be found. It may have been removed or the link is incomplete.</span>
        <Button variant="ghost" size="sm" onClick={onClose}><X className="h-3.5 w-3.5" /> Dismiss</Button>
      </div>
    );
  }
  return (
    <div className="mb-6 space-y-2">
      <div className="flex items-center justify-between">
        <span className="eyebrow text-accent">Linked filing</span>
        <Button variant="ghost" size="sm" onClick={onClose}><X className="h-3.5 w-3.5" /> Dismiss</Button>
      </div>
      {view === "cards" ? <AnnouncementCard row={query.data} defaultOpen highlight /> : <FilingRow row={query.data} defaultOpen highlight />}
    </div>
  );
}

/** Side rail: the day in numbers and what is coming up, so the feed stays about the filings. */
function Rail({ today }: { today: string }) {
  // The rail is hidden below 1024px; fetching its data there would cost reads for nothing.
  const wide = useMediaQuery("(min-width: 1024px)");
  const system = useQuery({ queryKey: ["system"], queryFn: api.system, staleTime: 120_000, enabled: wide });
  const upcoming = useQuery({ queryKey: ["calendar", today, "rail"], queryFn: () => api.calendar(today, addDays(today, 7)),
    staleTime: 300_000, enabled: wide });
  const s = system.data;
  const count = (status: string) => s?.ledger_today.find((r) => r.status === status)?.n ?? 0;
  const filed = s?.ledger_today.reduce((a, r) => a + r.n, 0) ?? 0;
  const noise = count("DROPPED_RULE") + count("NOT_MATERIAL");
  const high7d = s?.cards_7d.find((r) => r.impact_level === "HIGH")?.n ?? 0;
  const events = (upcoming.data?.events ?? []).slice(0, 8);
  return (
    <aside className="hidden lg:block">
      <div className="sticky top-20 space-y-4">
        <section className="rounded-xl border border-line bg-surface p-4">
          <h2 className="font-display text-[17px] text-ink">Today</h2>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            {[["Filed", filed], ["Analysed", count("ANALYZED")], ["Noise", noise]].map(([label, value]) => (
              <div key={label} className="rounded-lg bg-surface-2/70 px-2 py-2">
                <div className="num text-[18px] font-bold text-ink">{num(Number(value))}</div>
                <div className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-3">{label}</div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[12px] text-ink-3">
            {num(high7d)} high-impact filings in the last 7 days. <Link href="/feed?tab=noise" className="font-medium text-accent hover:underline">See what was filtered</Link>
          </p>
        </section>
        <section className="rounded-xl border border-line bg-surface">
          <header className="flex items-baseline justify-between px-4 pt-4">
            <h2 className="font-display text-[17px] text-ink">Coming up</h2>
            <Link href="/calendar" className="text-[12px] font-medium text-accent hover:underline">Calendar</Link>
          </header>
          {events.length === 0 ? <p className="px-4 pb-4 pt-2 text-[13px] text-ink-3">Nothing in the next 7 days.</p> : (
            <ul className="mt-2 divide-y divide-line">
              {events.map((e) => (
                <li key={e.id}>
                  <Link href={`/company/${e.scrip_code}`} className="flex gap-3 px-4 py-2.5 hover:bg-surface-2/50">
                    <span className="num w-12 shrink-0 text-[12px] text-ink-3">{istDate(e.event_date).replace(/ \d{4}$/, "")}</span>
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5">
                        <Avatar name={e.company_name ?? e.scrip_code} symbol={e.symbol} size={14} />
                        <span className="truncate text-[13px] font-semibold text-ink">{e.symbol ?? e.company_name}</span>
                      </span>
                      <Badge className={cn("mt-1", catalystFamily(e.event_type).chip)}>{titleCase(e.event_type)}</Badge>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </aside>
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
  const ruleTotal = query.data?.pages[0]?.rule_total ?? 0;
  return (
    <section>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-2">Filings filtered out on this day, and why. Spot-check these to tune the rules.</p>
        <input type="date" aria-label="Day" value={date} onChange={(e) => e.target.value && onDate(e.target.value)}
          className="num h-9 rounded-lg border border-line bg-surface px-3 text-[13px] text-ink" />
      </div>
      {ruleTotal > 0 && (
        <p className="mt-3 text-[13px] text-ink-3">
          {num(ruleTotal)} filtered by the rules; filings the AI gatekeeper judged not material are listed first.
        </p>
      )}
      {query.isPending ? <Loading /> : !query.data ? <Empty title="Couldn't load the noise audit" body={String(query.error)} /> : rows.length === 0 ? (
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
          {(query.hasNextPage || query.isFetchNextPageError) && (
            <div className="border-t border-line p-3 text-center">
              <Button size="sm" onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage}>
                {query.isFetchNextPageError ? "Couldn't load more · retry" : "Load more"}
              </Button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = () => setMatches(list.matches);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);
  return matches;
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
