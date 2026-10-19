import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link, useLocation } from "wouter";
import { AnnouncementCard } from "../components/AnnouncementCard";
import { FilingRow } from "../components/FilingCard";
import { api, type FeedFilters } from "../lib/api";
import { cn } from "../lib/cn";
import { addDays, istDate, num, titleCase, todayIST } from "../lib/format";
import { catalystFamily, FEED_TABS, SIZES } from "../lib/taxonomy";
import { useQueryState } from "../lib/url";
import { Empty, Loading, Pager } from "./FeedView";
import { lastClose } from "./TopSignalsView";

/** Redesign, step 1 (owner, 2026-10-19): one home page instead of "Top signals" and "Live feed". The day's
 * high-impact cards in full, everything else as rows that open in place; filters on the left, what is due and what
 * needs checking on the right. */

const RANGES = [
  { key: "close", label: "Since close" },
  { key: "today", label: "Today" },
  { key: "7d", label: "7 days" },
] as const;
type RangeKey = (typeof RANGES)[number]["key"];

const GROUPS = FEED_TABS.filter((t) => t.category);   // Results, Capex & orders, Capital & deals, Governance
const ROWS_PER_PAGE = 30;

function startOf(range: RangeKey, today: string): string {
  if (range === "today") return `${today}T00:00:00+05:30`;
  if (range === "7d") return `${addDays(today, -7)}T00:00:00+05:30`;
  return lastClose();
}

export function TodayView() {
  const [params, setParams] = useQueryState();
  const [, navigate] = useLocation();
  // Links from before the feed moved to /feed (shared cards, tabs) still open where they meant to.
  useEffect(() => {
    if (params.get("card") || params.get("tab")) navigate(`/feed?${params.toString()}`, { replace: true });
  }, [params, navigate]);

  const today = todayIST();
  const range = (RANGES.find((r) => r.key === params.get("range"))?.key ?? "close") as RangeKey;
  const fromAt = startOf(range, today);
  const group = GROUPS.find((g) => g.key === params.get("cat"));
  const size = params.get("size") ?? undefined;
  const watch = params.get("watch") === "1";
  const withLow = params.get("low") === "1";
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);
  const base: FeedFilters = { from_at: fromAt, category: group?.category, size, watch: watch ? "1" : undefined };
  // Any filter change starts the list again at page 1.
  const set = (changes: Record<string, string | null>) => setParams({ ...changes, page: null });

  const brief = useQuery({ queryKey: ["brief", fromAt], queryFn: () => api.brief(fromAt), staleTime: 60_000 });
  const high = useQuery({
    queryKey: ["today-high", base], queryFn: () => api.feedPage({ ...base, impact: "HIGH" }, 1, 20),
    placeholderData: keepPreviousData,
  });
  const rest = useQuery({
    queryKey: ["today-rest", base, withLow, page],
    queryFn: () => api.feedPage({ ...base, impact: withLow ? "MODERATE,LOW" : "MODERATE" }, page, ROWS_PER_PAGE),
    placeholderData: keepPreviousData,
  });
  const review = useQuery({ queryKey: ["review"], queryFn: () => api.review(), staleTime: 120_000 });
  const held = (review.data?.cards ?? []).filter((c) => c.held === 1 && c.filed_at >= fromAt).length;
  const b = brief.data;

  const filtersOn = !!(group || size || watch);
  const rangeLabel = range === "close" ? "since the last close" : range === "today" ? "today" : "in the last 7 days";

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-5 sm:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-[28px] leading-tight text-ink">Today</h1>
          <p className="mt-0.5 text-sm text-ink-2">The day's material NSE filings, the important ones first.</p>
        </div>
        <div role="radiogroup" aria-label="Window" className="inline-flex rounded-lg border border-line bg-surface p-0.5">
          {RANGES.map((r) => (
            <button key={r.key} type="button" role="radio" aria-checked={range === r.key}
              onClick={() => set({ range: r.key === "close" ? null : r.key })}
              className={cn("h-8 rounded-md px-3 text-[13px] font-medium",
                range === r.key ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink")}>
              {r.label}
            </button>
          ))}
        </div>
      </header>

      {/* The window in numbers */}
      <dl className="mt-4 flex flex-wrap overflow-hidden rounded-xl border border-line bg-surface">
        {([
          ["Filings read", b ? num(b.scanned) : "—", ""],
          ["Cards", b ? num(b.cards) : "—", ""],
          ["High impact", b ? num(b.high) : "—", "text-impact-high"],
          ["Pass all 4 gates", b ? num(b.signals) : "—", ""],
          ["To verify", review.data ? num(held) : "—", held ? "text-warn" : ""],
        ] as const).map(([label, value, tone]) => (
          // four tiles on a phone (the gates count is in the rail), five from 640px
          <div key={label} className={cn("min-w-[120px] flex-1 border-b border-r border-line px-4 py-2.5 last:border-r-0 sm:border-b-0",
            label === "Pass all 4 gates" && "hidden sm:block")}>
            <dd className={cn("num text-[19px] font-semibold leading-tight text-ink", tone)}>{value}</dd>
            <dt className="eyebrow mt-0.5 text-ink-3">{label}</dt>
          </div>
        ))}
      </dl>

      {/* Filters as chips below 1024px; the left column takes them above */}
      <div className="mt-4 flex gap-2 overflow-x-auto pb-1 lg:hidden">
        <Chip on={!group} onClick={() => set({ cat: null })}>All events</Chip>
        {GROUPS.map((g) => <Chip key={g.key} on={group?.key === g.key} onClick={() => set({ cat: group?.key === g.key ? null : g.key })}>{g.label}</Chip>)}
        <Chip on={watch} onClick={() => set({ watch: watch ? null : "1" })}>★ Watchlist</Chip>
      </div>

      <div className="mt-5 grid items-start gap-6 lg:grid-cols-[200px_minmax(0,1fr)_280px]">
        <aside aria-label="Filters" className="sticky top-20 hidden space-y-5 lg:block">
          <FilterGroup title="Event">
            <Option on={!group} onClick={() => set({ cat: null })}>All events</Option>
            {GROUPS.map((g) => <Option key={g.key} on={group?.key === g.key} onClick={() => set({ cat: g.key })}>{g.label}</Option>)}
          </FilterGroup>
          <FilterGroup title="Size">
            <Option on={!size} onClick={() => set({ size: null })}>All sizes</Option>
            {SIZES.map((s) => <Option key={s} on={size === s} onClick={() => set({ size: s })}>{titleCase(s)} cap</Option>)}
          </FilterGroup>
          <FilterGroup title="Only">
            <Option on={watch} onClick={() => set({ watch: watch ? null : "1" })}>★ My watchlist</Option>
            <Option on={withLow} onClick={() => set({ low: withLow ? null : "1" })}>Include low impact</Option>
          </FilterGroup>
          {filtersOn && (
            <button type="button" onClick={() => set({ cat: null, size: null, watch: null })}
              className="text-[13px] font-medium text-accent hover:underline">Clear filters</button>
          )}
        </aside>

        <main className="min-w-0 space-y-4">
          <SectionHead title="High impact" note={high.data ? `${num(high.data.total ?? high.data.cards.length)} ${rangeLabel}` : undefined} />
          {high.isPending ? <Loading /> : !high.data ? <Empty title="Couldn't load high-impact cards" body={String(high.error)} /> :
            high.data.cards.length === 0 ? (
              <p className="rounded-xl border border-dashed border-line-strong bg-surface px-4 py-5 text-[14px] text-ink-2">
                No high-impact filing {rangeLabel}{filtersOn ? " with these filters" : ""}.
                {range !== "7d" && <> <button type="button" className="font-medium text-accent hover:underline" onClick={() => set({ range: "7d" })}>See the last 7 days</button>.</>}
              </p>
            ) : (
              <>
                {high.data.cards.map((row) => <AnnouncementCard key={row.news_id} row={row} />)}
                {(high.data.total ?? 0) > high.data.cards.length && (
                  <Link href="/feed?tab=high" className="block text-center text-[13px] font-medium text-accent hover:underline">All high-impact filings</Link>
                )}
              </>
            )}

          <SectionHead title={withLow ? "Everything else" : "Moderate impact"}
            note={rest.data ? `${num(rest.data.total ?? rest.data.cards.length)} cards` : undefined}
            action={<button type="button" onClick={() => set({ low: withLow ? null : "1" })} className="font-medium text-accent hover:underline">
              {withLow ? "Hide low impact" : "Show low impact too"}</button>} />
          {rest.isPending ? <Loading /> : !rest.data ? <Empty title="Couldn't load the other cards" body={String(rest.error)} /> :
            rest.data.cards.length === 0 ? (
              <p className="rounded-xl border border-dashed border-line-strong bg-surface px-4 py-5 text-[14px] text-ink-2">Nothing else {rangeLabel}.</p>
            ) : (
              <div className="space-y-2">
                {rest.data.cards.map((row) => <FilingRow key={row.news_id} row={row} />)}
                <Pager page={page} pages={rest.data.pages ?? 1} capped={!!rest.data.total_capped}
                  onPage={(n) => setParams({ page: n > 1 ? String(n) : null })} />
              </div>
            )}
        </main>

        <Rail today={today} held={held} reviewLoaded={!!review.data} signals={b?.signals ?? 0} fromAt={fromAt} />
      </div>
    </div>
  );
}

function SectionHead({ title, note, action }: { title: string; note?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2 pt-1">
      <h2 className="font-display text-[17px] text-ink">{title}</h2>
      <span className="flex items-baseline gap-3 text-[12.5px] text-ink-3">{note && <span className="num">{note}</span>}{action}</span>
    </div>
  );
}

function FilterGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="eyebrow mb-1.5 text-ink-3">{title}</h3>
      <div className="flex flex-col">{children}</div>
    </section>
  );
}

function Option({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick}
      className={cn("rounded-md px-2 py-1.5 text-left text-[13.5px]", on ? "bg-accent-soft font-semibold text-accent" : "text-ink-2 hover:bg-surface-2 hover:text-ink")}>
      {children}
    </button>
  );
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick}
      className={cn("shrink-0 rounded-full border px-3 py-1 text-[12.5px] font-semibold",
        on ? "border-ink bg-ink text-bg" : "border-line bg-surface text-ink-2")}>
      {children}
    </button>
  );
}

/** Right column: what needs checking, what is due today, and the watchlist's cards in this window. */
function Rail({ today, held, reviewLoaded, signals, fromAt }: {
  today: string; held: number; reviewLoaded: boolean; signals: number; fromAt: string;
}) {
  const due = useQuery({ queryKey: ["calendar", today, today], queryFn: () => api.calendar(today, today), staleTime: 300_000 });
  const watched = useQuery({ queryKey: ["today-watch", fromAt], queryFn: () => api.feed({ from_at: fromAt, watch: "1" }, null, 8), staleTime: 60_000 });
  const events = due.data?.events ?? [];
  const cards = watched.data?.cards ?? [];
  return (
    <aside className="space-y-4 lg:sticky lg:top-20">
      {signals > 0 && (
        <Link href="/signals" className="block rounded-xl border border-accent-line bg-accent-soft px-4 py-3 hover:border-accent">
          <span className="num text-[18px] font-semibold text-accent">{num(signals)}</span>
          <span className="ml-2 text-[13px] text-ink-2">passed all four gates: big for the company, an inflection, not run up, clean checks</span>
        </Link>
      )}
      {reviewLoaded && held > 0 && (
        <Panel title="To verify" link={{ href: "/system", label: "Review" }}>
          <p className="rounded-lg bg-warn-soft px-3 py-2 text-[13px] text-ink-2">
            <span className="num mr-1.5 text-[17px] font-semibold text-warn">{num(held)}</span>
            {held === 1 ? "card's figures" : "cards' figures"} did not fully match the filing, so {held === 1 ? "it is" : "they are"} held back.
          </p>
        </Panel>
      )}
      <Panel title="Due today" link={{ href: "/calendar", label: "Calendar" }}>
        {due.isPending ? <p className="text-[13px] text-ink-3">Loading…</p> : events.length === 0 ? (
          <p className="text-[13px] text-ink-3">Nothing scheduled today.</p>
        ) : (
          <ul className="space-y-1.5">
            {events.slice(0, 8).map((e) => (
              <li key={e.id}>
                <Link href={`/company/${e.scrip_code}`} className="flex items-baseline justify-between gap-3 text-[13.5px] hover:text-accent">
                  <span className="min-w-0 truncate text-ink">{e.company_name ?? e.symbol ?? e.scrip_code}</span>
                  <span className={cn("shrink-0 rounded px-1.5 text-[11px] font-semibold", catalystFamily(e.event_type).chip)}>{titleCase(e.event_type)}</span>
                </Link>
              </li>
            ))}
            {events.length > 8 && <li className="text-[12.5px] text-ink-3">+ {events.length - 8} more</li>}
          </ul>
        )}
      </Panel>
      <Panel title="Watchlist" link={{ href: "/?watch=1", label: "Only these" }}>
        {watched.isPending ? <p className="text-[13px] text-ink-3">Loading…</p> : cards.length === 0 ? (
          <p className="text-[13px] text-ink-3">No cards for your watchlist in this window. Star a company on its page to follow it.</p>
        ) : (
          <ul className="space-y-1.5">
            {cards.map((c) => (
              <li key={c.news_id} className="flex items-baseline justify-between gap-3 text-[13.5px]">
                <Link href={`/company/${c.scrip_code}`} className="min-w-0 truncate text-ink hover:text-accent">{c.company_name}</Link>
                <span className="num shrink-0 text-[12px] text-ink-3">{istDate(c.filed_at).replace(/ \d{4}$/, "")}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </aside>
  );
}

function Panel({ title, link, children }: { title: string; link?: { href: string; label: string }; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-surface px-4 py-3.5">
      <header className="mb-2.5 flex items-baseline justify-between">
        <h2 className="eyebrow text-ink-3">{title}</h2>
        {link && <Link href={link.href} className="text-[12.5px] font-medium text-accent hover:underline">{link.label}</Link>}
      </header>
      {children}
    </section>
  );
}
