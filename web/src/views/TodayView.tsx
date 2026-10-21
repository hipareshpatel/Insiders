import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useLocation } from "wouter";
import type { CardRow } from "../../shared/types";
import { AnnouncementCard, AnnouncementRow } from "../components/AnnouncementCard";
import { Avatar } from "../components/Avatar";
import { parseCard } from "../components/FilingCard";
import { api, type FeedFilters } from "../lib/api";
import { cn } from "../lib/cn";
import { addDays, istDate, istDateTime, marketSession, num, pct, signClass, titleCase, todayIST, companyPath } from "../lib/format";
import { catalystFamily, catalystText, FEED_TABS, SECTORS, SIZES, verdict, type Tone } from "../lib/taxonomy";
import { useQueryState } from "../lib/url";
import { Empty, Loading, Pager } from "./FeedView";
import { lastClose } from "./TopSignalsView";

/** The home page (redesign approved by the owner, 2026-10-19): the day in six numbers, the cards that cleared all
 * four gates, the companies that filed, then the feed with every filter the old pages had, and a rail of what is due,
 * overdue, building and watched. Everything comes from the existing endpoints. */

const RANGES = [
  { key: "close", label: "Since close" },
  { key: "today", label: "Today" },
  { key: "7d", label: "7 days" },
] as const;
type RangeKey = (typeof RANGES)[number]["key"];
const TABS = [{ key: "all", label: "For you" }, { key: "high", label: "High impact" }, ...FEED_TABS.filter((t) => t.category)];
const PAGE = 20;

function startOf(range: RangeKey, today: string): string {
  if (range === "today") return `${today}T00:00:00+05:30`;
  if (range === "7d") return `${addDays(today, -7)}T00:00:00+05:30`;
  return lastClose();
}

function greeting(now = new Date()): string {
  const h = Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", hour12: false }).format(now));
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export function TodayView() {
  const [params, setParams] = useQueryState();
  const [, navigate] = useLocation();
  // Links from before the feed moved to /feed (shared cards, tabs) still open where they meant to.
  useEffect(() => {
    if (params.get("card") || params.get("tab")) navigate(`/feed?${params.toString()}`, { replace: true });
  }, [params, navigate]);

  const today = todayIST();
  const chosen = RANGES.find((r) => r.key === params.get("range"))?.key as RangeKey | undefined;
  // The page never opens on an empty window: with nothing published since the close (before the first run of the
  // day, or on a holiday), it shows the last 7 days and says so (design audit, 2026-10-20: six zeros on first view).
  const sinceClose = useQuery({ queryKey: ["brief", startOf("close", today)], queryFn: () => api.brief(startOf("close", today)),
    staleTime: 60_000, enabled: !chosen });
  const fellBack = !chosen && sinceClose.data?.cards === 0;
  const range: RangeKey = chosen ?? (fellBack ? "7d" : "close");
  const fromAt = startOf(range, today);
  const tabKey = params.get("t") ?? "all";
  const tab = TABS.find((t) => t.key === tabKey) ?? TABS[0];
  const withLow = params.get("low") === "1";
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);
  const base: FeedFilters = {
    from_at: fromAt, category: "category" in tab ? tab.category : undefined, turnaround: "turnaround" in tab ? tab.turnaround : undefined,
    size: params.get("size") ?? undefined, sector: params.get("sector") ?? undefined, session: params.get("session") ?? undefined,
    review: params.get("verified") === "1" ? "0" : undefined, watch: params.get("watch") === "1" ? "1" : undefined,
    q: params.get("q") ?? undefined,
  };
  const set = (changes: Record<string, string | null>) => setParams({ ...changes, page: null });

  const brief = useQuery({ queryKey: ["brief", fromAt], queryFn: () => api.brief(fromAt), staleTime: 60_000 });
  const signals = useQuery({ queryKey: ["signals", fromAt], queryFn: () => api.signals({ from_at: fromAt }), staleTime: 60_000 });
  const high = useQuery({
    queryKey: ["today-high", base], queryFn: () => api.feedPage({ ...base, impact: "HIGH" }, 1, PAGE),
    placeholderData: keepPreviousData,
  });
  const rest = useQuery({
    queryKey: ["today-rest", base, page], queryFn: () => api.feedPage({ ...base, impact: "MODERATE" }, page, PAGE),
    placeholderData: keepPreviousData, enabled: tab.key !== "high",
  });
  const low = useQuery({
    queryKey: ["today-low", base], queryFn: () => api.feedPage({ ...base, impact: "LOW" }, 1, 30),
    enabled: withLow && tab.key !== "high",
  });
  const b = brief.data;
  const rangeLabel = range === "close" ? "since the close" : range === "today" ? "today" : "in the last 7 days";
  const now = new Date().toISOString();
  const cards = [...(high.data?.cards ?? []), ...(tab.key !== "high" ? rest.data?.cards ?? [] : [])];

  return (
    <div className="mx-auto w-full max-w-[1240px] px-4 py-6 sm:px-6">
      <section className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-[13.5px] font-semibold text-ink-3">
          <span className="live-dot" aria-hidden />
          {greeting()} · {istDate(now)} · {marketSession(now).toLowerCase()} · as of {istDateTime(now).split(", ").pop()} IST
        </p>
        <div role="radiogroup" aria-label="Window" className="card-soft inline-flex gap-0.5 rounded-xl p-[3px]">
          {RANGES.map((r) => (
            <button key={r.key} type="button" role="radio" aria-checked={range === r.key} onClick={() => set({ range: r.key === "close" ? null : r.key })}
              className={cn("rounded-[9px] px-3 py-1.5 text-[12.5px] font-bold transition-colors", range === r.key ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink")}>
              {r.label}
            </button>
          ))}
        </div>
      </section>
      <h1 className="mt-2 font-display text-[26px] leading-tight text-ink sm:text-[30px]">
        {b ? <>{num(b.cards)} filings worth your time {rangeLabel}{b.high ? <>, <span className="text-grad">{num(b.high)} that could move a stock.</span></> : "."}</>
          : "The day's material NSE filings"}
      </h1>
      {fellBack && <p className="mt-1 text-[13px] text-ink-3">Nothing new since the last close yet; showing the last 7 days.</p>}

      <dl className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi label="Filings read" value={b ? num(b.scanned) : "—"} />
        <Kpi label="Noise filtered" value={b && b.scanned ? `${Math.round((b.noise / b.scanned) * 100)}%` : "—"} sub={b ? `${num(b.noise)} set aside` : undefined} />
        <Kpi label="Cards" value={b ? num(b.cards) : "—"} />
        <Kpi label="High impact" value={b ? num(b.high) : "—"} tone="text-impact-high" />
        <Kpi label="Pass all 4 gates" value={b ? num(b.signals) : "—"} tone="text-pos" />
        <Kpi label="To verify" value={b ? num(b.held ?? 0) : "—"} tone={b?.held ? "text-warn" : undefined} />
      </dl>

      <SignalsStrip rows={signals.data?.cards ?? []} />

      <div className="sticky top-14 z-10 -mx-4 mt-2 bg-bg px-4 pb-2 pt-3 sm:-mx-6 sm:px-6">
        <div role="tablist" className="card-soft no-scrollbar inline-flex max-w-full gap-0.5 overflow-x-auto rounded-2xl p-1">
          {TABS.map((t) => {
            const on = t.key === tab.key;
            const count = t.key === "all" ? b?.cards : t.key === "high" ? b?.high : undefined;
            return (
              <button key={t.key} type="button" role="tab" aria-selected={on} onClick={() => set({ t: t.key === "all" ? null : t.key })}
                className={cn("flex items-center gap-1.5 whitespace-nowrap rounded-[10px] px-3.5 py-2 text-[13.5px] font-bold transition-colors",
                  on ? "grad-accent shadow-md" : "text-ink-2 hover:text-ink")}>
                {t.label}
                {count != null && <span className={cn("num rounded-full px-1.5 text-[11px] font-semibold", on ? "bg-white/25" : "bg-surface-2 text-ink-3")}>{num(count)}</span>}
              </button>
            );
          })}
        </div>
        <Filters params={params} set={set} withLow={withLow} noise={b?.noise} />
      </div>

      <div className="mt-3 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_330px]">
        <main className="min-w-0 space-y-4">
          {high.isPending ? <Loading /> : !high.data ? <Empty title="Couldn't load the cards" body={String(high.error)} /> : (
            <>
              {high.data.cards.map((row) => <AnnouncementCard key={row.news_id} row={row} />)}
              {tab.key !== "high" && rest.data?.cards.map((row) => <AnnouncementCard key={row.news_id} row={row} />)}
              {cards.length === 0 && (
                <Empty title={`No material filing ${rangeLabel}`}
                  body={range !== "7d" ? "Try the last 7 days, or clear the filters." : "Clear the filters, or open All filings for the full history."} />
              )}
              {withLow && (low.data?.cards.length ?? 0) > 0 && (
                <section className="card-soft overflow-hidden">
                  <h3 className="eyebrow px-5 pb-1 pt-4 text-ink-3">Low impact {rangeLabel}</h3>
                  <div className="space-y-2 p-3">{low.data!.cards.map((row) => <AnnouncementRow key={row.news_id} row={row} />)}</div>
                </section>
              )}
              {tab.key !== "high" && rest.data && (
                <Pager page={page} pages={rest.data.pages ?? 1} capped={!!rest.data.total_capped}
                  onPage={(n) => { setParams({ page: n > 1 ? String(n) : null }); window.scrollTo({ top: 0 }); }} />
              )}
            </>
          )}
        </main>
        <Rail today={today} fromAt={fromAt} brief={b} />
      </div>
      <Health />
    </div>
  );
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="card-soft rise-in rounded-2xl px-4 py-2.5">
      <dd className={cn("num text-[22px] font-bold leading-tight tracking-tight text-ink", tone)}>{value}</dd>
      <dt className="text-[11.5px] font-semibold text-ink-3">{label}{sub && <span className="num block text-[11px] font-medium">{sub}</span>}</dt>
    </div>
  );
}

function scrollToCard(id: string, fallback: () => void) {
  const el = document.getElementById(`card-${id}`);
  if (el) el.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  else fallback();
}

function SignalsStrip({ rows }: { rows: CardRow[] }) {
  const [, navigate] = useLocation();
  if (!rows.length) return null;
  return (
    <section aria-label="Signals" className="mt-4 rounded-[20px] p-4 shadow-[var(--shadow-1)]"
      style={{ background: "linear-gradient(135deg, color-mix(in srgb, var(--accent) 10%, var(--surface)), var(--surface))" }}>
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-extrabold text-ink">🔥 Signals <span className="ml-1.5 text-[12.5px] font-semibold text-ink-3">cleared all four gates: big for the company, a real inflection, not already run up, clean checks</span></h2>
        <Link href="/signals" className="text-[12.5px] font-bold text-accent hover:underline">All signals</Link>
      </header>
      <div className="mt-2.5 grid gap-2.5 md:grid-cols-3">
        {rows.slice(0, 3).map((row) => {
          const card = parseCard(row);
          return (
            <button key={row.news_id} type="button" onClick={() => scrollToCard(row.news_id, () => navigate(`/feed?card=${encodeURIComponent(row.news_id)}`))}
              className="card-lift grid grid-cols-[40px_minmax(0,1fr)] gap-2.5 rounded-2xl bg-surface p-3 text-left">
              <Avatar name={row.company_name} symbol={row.symbol} size={40} />
              <span className="min-w-0">
                <span className="block text-[13.5px] font-bold text-ink">{row.company_name} <span className="num font-semibold text-ink-3">· {card?.score?.total ?? row.actionability_score ?? ""}</span></span>
                <span className="mt-0.5 line-clamp-2 block text-[12.5px] leading-snug text-ink-2">{card?.headline ?? row.headline}</span>
                <span className="mt-1.5 flex flex-wrap gap-1">
                  {["Big", "Inflection", "Not run up", "Clean"].map((g) => <span key={g} className="rounded-md bg-pos-soft px-1.5 py-px text-[10px] font-extrabold text-pos">{g}</span>)}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function Filters({ params, set, withLow, noise }: {
  params: URLSearchParams; set: (c: Record<string, string | null>) => void; withLow: boolean; noise?: number;
}) {
  const [text, setText] = useState(params.get("q") ?? "");
  const q = params.get("q") ?? "";
  useEffect(() => setText(q), [q]);
  useEffect(() => {
    const id = setTimeout(() => { if (q !== text) set({ q: text || null }); }, 300);
    return () => clearTimeout(id);
  }, [text, q, set]);
  const sel = "h-9 rounded-[11px] border border-line bg-surface px-3 text-[13px] font-semibold text-ink hover:border-line-strong focus:border-accent focus:outline-none";
  const tog = (on: boolean) => cn("inline-flex h-9 items-center gap-1.5 rounded-[11px] border px-3 text-[13px] font-bold transition-colors",
    on ? "border-transparent bg-accent-soft text-accent" : "border-line bg-surface text-ink-2 hover:text-ink");
  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-2">
      <select aria-label="Size" className={sel} value={params.get("size") ?? ""} onChange={(e) => set({ size: e.target.value || null })}>
        <option value="">All sizes</option>
        {SIZES.map((s) => <option key={s} value={s}>{titleCase(s)} cap</option>)}
      </select>
      <select aria-label="Sector" className={sel} value={params.get("sector") ?? ""} onChange={(e) => set({ sector: e.target.value || null })}>
        <option value="">All sectors</option>
        {Object.entries(SECTORS).filter(([k]) => k !== "default").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <select aria-label="Market session" className={sel} value={params.get("session") ?? ""} onChange={(e) => set({ session: e.target.value || null })}>
        <option value="">All sessions</option>
        <option value="LIVE_MARKET">Live market</option>
        <option value="AFTER_MARKET,PRE_MARKET,NON_TRADING">After hours &amp; weekend</option>
      </select>
      <button type="button" aria-pressed={params.get("verified") === "1"} className={tog(params.get("verified") === "1")} onClick={() => set({ verified: params.get("verified") === "1" ? null : "1" })}>✓ Verified only</button>
      <button type="button" aria-pressed={params.get("watch") === "1"} className={tog(params.get("watch") === "1")} onClick={() => set({ watch: params.get("watch") === "1" ? null : "1" })}>★ Watchlist</button>
      <button type="button" aria-pressed={withLow} className={tog(withLow)} onClick={() => set({ low: withLow ? null : "1" })}>+ Low impact</button>
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Filter by company or headline" aria-label="Filter by company or headline"
        className="h-9 min-w-0 flex-1 basis-44 rounded-[11px] border border-line bg-surface px-3 text-[13px] text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none" />
      <Link href="/feed?tab=noise" className="text-[12.5px] font-bold text-accent hover:underline sm:ml-auto">
        See what was filtered out{noise ? ` (${num(noise)})` : ""} →
      </Link>
    </div>
  );
}

function Panel({ title, link, children }: { title: string; link?: { href: string; label: string }; children: ReactNode }) {
  return (
    <section className="card-soft rise-in flex flex-col gap-2.5 px-[18px] py-4">
      <header className="flex items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-extrabold text-ink">{title}</h2>
        {link && <Link href={link.href} className="text-[12.5px] font-bold text-accent hover:underline">{link.label}</Link>}
      </header>
      {children}
    </section>
  );
}

const VERDICT_CHIP: Record<Tone, string> = { POSITIVE: "bg-pos-soft text-pos", NEGATIVE: "bg-neg-soft text-neg", MIXED: "bg-warn-soft text-warn", NEUTRAL: "bg-accent-soft text-accent" };
const FAMILY_TILE: Record<string, string> = { corp: "bg-info-soft text-info", meet: "bg-violet-soft text-violet", rights: "bg-teal-soft text-teal", exec: "bg-pos-soft text-pos", account: "bg-warn-soft text-warn", other: "bg-accent-soft text-accent" };

function Rail({ today, fromAt, brief }: { today: string; fromAt: string; brief?: import("../../shared/types").BriefResponse }) {
  const results = useQuery({ queryKey: ["today-results", fromAt], queryFn: () => api.feed({ from_at: fromAt, category: "RESULTS" }, null, 6), staleTime: 60_000 });
  const upcoming = useQuery({ queryKey: ["calendar", today, "7d"], queryFn: () => api.calendar(today, addDays(today, 7)), staleTime: 300_000 });
  const overdue = useQuery({ queryKey: ["overdue"], queryFn: () => api.overdue(), staleTime: 300_000 });
  const radar = useQuery({ queryKey: ["radar", 3], queryFn: () => api.radar(3), staleTime: 300_000 });
  const watched = useQuery({ queryKey: ["today-watch", fromAt], queryFn: () => api.feed({ from_at: fromAt, watch: "1" }, null, 6), staleTime: 60_000 });
  const mix = brief ? [
    { label: "High", n: brief.high, color: "var(--impact-high)" },
    { label: "Moderate", n: brief.moderate ?? 0, color: "var(--impact-moderate)" },
    { label: "Low", n: brief.low ?? 0, color: "var(--neutral-stripe)" },
  ] : [];
  const sectors = useMemo(() => Object.entries(brief?.sectors ?? {})
    .map(([k, v]) => ({ k, ...v, total: v.high + v.moderate + v.low })).sort((a, b) => b.total - a.total).slice(0, 6), [brief]);
  const top = Math.max(1, ...sectors.map((s) => s.total));
  return (
    <aside className="space-y-4 lg:sticky lg:top-36">
      {brief && (
        <Panel title="Today's mix" link={{ href: "/feed", label: "All filings" }}>
          <div className="grid grid-cols-[110px_minmax(0,1fr)] items-center gap-3.5">
            <Donut parts={mix} />
            <ul className="space-y-1.5 text-[13px]">
              {[...mix, { label: "To verify", n: brief.held ?? 0, color: "var(--warn)" }].map((m) => (
                <li key={m.label} className="flex justify-between gap-2">
                  <span><i className="mr-2 inline-block h-2.5 w-2.5 rounded-[3px]" style={{ background: m.color }} />{m.label}</span>
                  <span className="num text-ink-3">{num(m.n)}</span>
                </li>
              ))}
            </ul>
          </div>
        </Panel>
      )}
      {(results.data?.cards.length ?? 0) > 0 && (
        <Panel title="Results scorecard" link={{ href: "/results", label: "Results" }}>
          <ul className="space-y-2">
            {results.data!.cards.map((row) => {
              const card = parseCard(row);
              const v = verdict((card?.tone ?? "NEUTRAL") as Tone, row.impact_level);
              const pat = card?.results?.pat?.yoy_pct;
              return (
                <li key={row.news_id} className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-2 text-[13px]">
                  <Link href={`${companyPath(row)}`} className="truncate"><b className="text-ink">{row.symbol ?? row.company_name}</b> <span className="text-ink-3">{card?.results?.period ?? ""}</span></Link>
                  <span className={cn("num", signClass(pat))}>{pat != null ? pct(pat) : ""}</span>
                  <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-extrabold", VERDICT_CHIP[v.tone])}>{v.label}</span>
                </li>
              );
            })}
          </ul>
        </Panel>
      )}
      <Panel title="Coming up, 7 days" link={{ href: "/calendar", label: "Calendar" }}>
        {(upcoming.data?.events ?? []).length === 0 ? <p className="text-[13px] text-ink-3">Nothing scheduled in the next 7 days.</p> : (
          <ul className="space-y-2">
            {upcoming.data!.events.slice(0, 6).map((e) => {
              const [day, mon] = istDate(e.event_date).split(" ");   // "19 Oct 2026"
              return (
                <li key={e.id}>
                  <Link href={`${companyPath(e)}`} className="grid grid-cols-[46px_minmax(0,1fr)] items-center gap-2.5 text-[13px] hover:text-accent">
                    <span className={cn("num rounded-[10px] py-1 text-center text-[12px] font-extrabold leading-tight", FAMILY_TILE[catalystFamily(e.event_type).key])}>
                      {day}<span className="block text-[9.5px] font-bold uppercase tracking-wide">{mon}</span>
                    </span>
                    <span className="min-w-0"><span className="block truncate text-ink">{e.company_name ?? e.symbol} · {titleCase(e.event_type)}</span>
                      {e.description && <span className="block truncate text-[11.5px] text-ink-3">{catalystText(e.event_type, e.description)}</span>}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
      {(overdue.data?.promises.length ?? 0) > 0 && (
        <Panel title="⚠ Overdue promises" link={{ href: "/calendar", label: "All" }}>
          <ul className="divide-y divide-line">
            {overdue.data!.promises.slice(0, 3).map((p) => (
              <li key={p.id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 py-1.5 text-[13px]">
                <Link href={`${companyPath(p)}?tab=promises`} className="min-w-0"><span className="text-ink">{p.symbol ?? p.company_name}: {p.statement}</span>
                  <span className="block text-[11.5px] text-ink-3">due {p.due ?? istDate(p.due_date)}</span></Link>
                <span className="num whitespace-nowrap text-[12px] font-bold text-warn">{p.days_overdue} days</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {(radar.data?.companies.length ?? 0) > 0 && (
        <Panel title="🚀 Inflection radar" link={{ href: "/companies?view=radar", label: "Radar" }}>
          <ul className="space-y-2">
            {radar.data!.companies.slice(0, 3).map((c) => (
              <li key={c.scrip_code}>
                <Link href={`${companyPath(c)}`} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 text-[13.5px] hover:text-accent">
                  <span className="min-w-0"><b className="text-ink">{c.company_name}</b><span className="block truncate text-[11.5px] text-ink-3">{c.triggers.map((t) => t.text).join(" · ")}</span></span>
                  <span className="flex gap-[3px]">{c.triggers.map((t) => <i key={t.kind} className="h-2 w-2 rounded-full bg-accent" />)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <Panel title="Watchlist" link={{ href: "/?watch=1", label: "Only these" }}>
        {(watched.data?.cards ?? []).length === 0 ? (
          <p className="text-[13px] text-ink-3">No cards for your watchlist in this window. Star a company on its page to follow it.</p>
        ) : (
          <ul className="space-y-2">
            {watched.data!.cards.map((c) => (
              <li key={c.news_id} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-2 text-[13.5px]">
                <Link href={`${companyPath(c)}`} className="truncate font-bold text-ink hover:text-accent">{c.company_name}</Link>
                <span className={cn("num text-[12.5px] font-bold", signClass(c.ret_1w))}>{c.ret_1w != null ? `1W ${pct(c.ret_1w)}` : ""}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      {sectors.length > 0 && (
        <Panel title="Where the news is">
          <ul className="space-y-1.5">
            {sectors.map((s) => (
              <li key={s.k} className="grid grid-cols-[100px_minmax(0,1fr)_24px] items-center gap-2 text-[12.5px] text-ink-2">
                <span className="truncate">{SECTORS[s.k] ?? titleCase(s.k)}</span>
                <span className="flex h-2 overflow-hidden rounded-full bg-surface-2">
                  <i style={{ width: `${(s.high / top) * 100}%`, background: "var(--impact-high)" }} />
                  <i style={{ width: `${(s.moderate / top) * 100}%`, background: "var(--impact-moderate)" }} />
                  <i style={{ width: `${(s.low / top) * 100}%`, background: "var(--neutral-stripe)" }} />
                </span>
                <span className="num text-right text-ink-3">{s.total}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </aside>
  );
}

function Donut({ parts }: { parts: { label: string; n: number; color: string }[] }) {
  const total = parts.reduce((a, p) => a + p.n, 0);
  const r = 44, len = 2 * Math.PI * r;
  let offset = 0;
  return (
    <svg viewBox="0 0 110 110" className="h-[110px] w-[110px]" role="img" aria-label={parts.map((p) => `${p.n} ${p.label.toLowerCase()}`).join(", ")}>
      <circle cx="55" cy="55" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="14" />
      {total > 0 && parts.map((p) => {
        const seg = (p.n / total) * len;
        const el = <circle key={p.label} cx="55" cy="55" r={r} fill="none" stroke={p.color} strokeWidth="14"
          strokeDasharray={`${Math.max(0, seg - 2)} ${len}`} strokeDashoffset={-offset} transform="rotate(-90 55 55)" />;
        offset += seg;
        return el;
      })}
      <text x="55" y="58" textAnchor="middle" fill="var(--ink)" style={{ font: "800 20px var(--font-sans)" }}>{num(total)}</text>
      <text x="55" y="72" textAnchor="middle" fill="var(--ink-3)" style={{ font: "600 9.5px var(--font-sans)" }}>cards</text>
    </svg>
  );
}

function Health() {
  const system = useQuery({ queryKey: ["system"], queryFn: api.system, staleTime: 120_000 });
  const run = system.data?.runs?.[0];
  const failed = system.data?.queue?.failed ?? 0;
  // the day's AI requests against the models' stated daily limits (models with no limit are left out)
  const limited = (system.data?.usage ?? []).filter((u) => u.limit_rpd);
  const quota = limited.length ? limited.reduce((n, u) => n + u.requests, 0) / limited.reduce((n, u) => n + (u.limit_rpd ?? 0), 0) : null;
  const start = system.data?.backfill?.start;
  return (
    <footer className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line pt-3.5 text-[12.5px] text-ink-3">
      {run && (
        <span><b className={run.status === "OK" || run.status === "RUNNING" ? "text-pos" : "text-warn"}>●</b> Pipeline {run.status === "OK" || run.status === "RUNNING" ? "healthy" : run.status.toLowerCase()} · last run {istDateTime(run.started_at).split(", ").pop()} IST{run.status === "RUNNING" ? " (running)" : ""}</span>
      )}
      {system.data && <span>{num(failed)} filings failed in the queue</span>}
      {quota != null && <span>AI quota today: {Math.round(quota * 100)}% used</span>}
      <span>{start ? `History since ${istDate(`${start}T12:00:00+05:30`)}` : "History"} · NSE companies ≥ ₹500 Cr</span>
    </footer>
  );
}
