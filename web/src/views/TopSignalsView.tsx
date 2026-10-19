import { useQuery } from "@tanstack/react-query";
import { Flame, Sunrise } from "lucide-react";
import { useEffect } from "react";
import { Link, useLocation } from "wouter";
import { AnnouncementCard } from "../components/AnnouncementCard";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { addDays, num, todayIST } from "../lib/format";
import { useQueryState } from "../lib/url";
import { Empty, Loading } from "./FeedView";

/** The last 15:30 IST close before now (Friday's on a weekend or a Monday morning). */
export function lastClose(now = new Date()): string {
  const ist = new Date(now.getTime() + 5.5 * 3600_000);
  let day = ist.toISOString().slice(0, 10);
  const minutes = ist.getUTCHours() * 60 + ist.getUTCMinutes();
  if (minutes < 15 * 60 + 30) day = addDays(day, -1);
  for (let i = 0; i < 4; i++) {
    const weekday = new Date(`${day}T00:00:00Z`).getUTCDay();
    if (weekday !== 0 && weekday !== 6) break;
    day = addDays(day, -1);
  }
  return `${day}T15:30:00+05:30`;
}

/** Blueprint view 1: the morning cockpit. Cards that cleared all four gates, best score first, with
 * what came in overnight in four numbers. */
export function TopSignalsView() {
  const [params, setParams] = useQueryState();
  const [, navigate] = useLocation();
  // Links from before the feed moved to /feed (shared cards, tabs) still open where they meant to.
  useEffect(() => {
    if (params.get("card") || params.get("tab")) navigate(`/feed?${params.toString()}`, { replace: true });
  }, [params, navigate]);
  const sinceClose = params.get("window") !== "3d";
  const fromAt = sinceClose ? lastClose() : `${addDays(todayIST(), -3)}T00:00:00+05:30`;
  const signals = useQuery({
    queryKey: ["signals", fromAt],
    queryFn: () => api.signals(sinceClose ? { from_at: fromAt } : { from: addDays(todayIST(), -3) }),
  });
  const brief = useQuery({ queryKey: ["brief", fromAt], queryFn: () => api.brief(fromAt), staleTime: 60_000 });
  const b = brief.data;

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6">
      <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-[30px] leading-tight text-ink">Top signals</h1>
          <p className="mt-1 text-sm text-ink-2">
            Filings that cleared all four gates: big for the company, a real inflection, a stock not already run up, and clean checks.
          </p>
        </div>
        <div role="radiogroup" aria-label="Window" className="inline-flex rounded-lg border border-line bg-surface p-0.5">
          {([["close", "Since 3:30 PM close", Sunrise], ["3d", "Last 3 days", Flame]] as const).map(([key, label, Icon]) => {
            const on = key === "close" ? sinceClose : !sinceClose;
            return (
              <button key={key} type="button" role="radio" aria-checked={on} onClick={() => setParams({ window: key === "close" ? null : key })}
                className={cn("inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-[13px] font-medium",
                  on ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink")}>
                <Icon className="h-4 w-4" />{label}
              </button>
            );
          })}
        </div>
      </header>

      <dl className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ["Filings scanned", b ? num(b.scanned) : "—"],
          ["Noise filtered out", b && b.scanned ? `${Math.round((b.noise / b.scanned) * 100)}%` : "—"],
          ["Memory dossiers updated", b ? num(b.cards) : "—"],
          ["Signals passing all 4 gates", b ? num(b.signals) : "—"],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-line bg-surface px-4 py-3">
            <dt className="eyebrow text-ink-3">{label}</dt>
            <dd className="num mt-1.5 text-[24px] font-bold leading-none text-ink">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="mx-auto w-full max-w-[720px] space-y-4">
        {signals.isPending ? <Loading /> : !signals.data ? <Empty title="Couldn't load signals" body={String(signals.error)} /> : signals.data.cards.length === 0 ? (
          <Empty title="No filing cleared all four gates in this window"
            body="That is normal on quiet days: most material filings update memory without being a signal. The live feed has every high-impact filing." />
        ) : signals.data.cards.map((row) => <AnnouncementCard key={row.news_id} row={row} />)}
        <p className="text-center text-[13px] text-ink-3">
          <Link href="/feed?tab=high" className="font-medium text-accent hover:underline">All high-impact filings</Link>
          {" · "}
          <Link href="/feed" className="font-medium text-accent hover:underline">Live feed</Link>
        </p>
      </div>
    </div>
  );
}
