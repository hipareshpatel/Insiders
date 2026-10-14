import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { useLocation } from "wouter";
import type { Catalyst } from "../../shared/types";
import { Avatar } from "../components/Avatar";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { addDays, istDate, titleCase, todayIST } from "../lib/format";
import { CATALYST_FAMILIES, catalystFamily } from "../lib/taxonomy";
import { useQueryState } from "../lib/url";
import { Empty, Loading } from "./FeedView";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function monthBounds(month: string) {
  const [y, m] = month.split("-").map(Number);
  const first = new Date(Date.UTC(y, m - 1, 1));
  const last = new Date(Date.UTC(y, m, 0));
  return { first, last, from: first.toISOString().slice(0, 10), to: last.toISOString().slice(0, 10) };
}

function shiftMonth(month: string, delta: number) {
  const [y, m] = month.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1 + delta, 1)).toISOString().slice(0, 7);
}

export function CalendarView() {
  const [params, setParams] = useQueryState();
  const [, navigate] = useLocation();
  const today = todayIST();
  const month = params.get("month") ?? today.slice(0, 7);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const { first, last, from, to } = monthBounds(month);
  const monthQuery = useQuery({ queryKey: ["calendar", from, to], queryFn: () => api.calendar(from, to) });
  const upcomingQuery = useQuery({ queryKey: ["calendar", today, "upcoming"], queryFn: () => api.calendar(today, addDays(today, 45)) });

  const visible = (e: Catalyst) => !hidden.has(catalystFamily(e.event_type).key);
  const byDay = useMemo(() => {
    const map = new Map<string, Catalyst[]>();
    for (const e of monthQuery.data?.events ?? []) if (visible(e)) map.set(e.event_date, [...(map.get(e.event_date) ?? []), e]);
    return map;
  }, [monthQuery.data, hidden]); // eslint-disable-line react-hooks/exhaustive-deps
  const agenda = (selected ? byDay.get(selected) ?? [] : (upcomingQuery.data?.events ?? []).filter(visible)).slice(0, 60);

  const leading = (first.getUTCDay() + 6) % 7;
  const cells: (string | null)[] = [
    ...Array.from({ length: leading }, () => null),
    ...Array.from({ length: last.getUTCDate() }, (_, i) => `${month}-${String(i + 1).padStart(2, "0")}`),
  ];
  while (cells.length % 7) cells.push(null);
  const label = first.toLocaleDateString("en-IN", { month: "long", year: "numeric", timeZone: "UTC" });

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6">
      <header className="mb-4">
        <h1 className="font-display text-[30px] leading-tight text-ink">Catalyst calendar</h1>
        <p className="mt-1 text-sm text-ink-2">Record dates, meetings, rights windows, execution milestones, and the dates promises fall due.</p>
      </header>

      <div className="mb-4 flex flex-wrap gap-1.5">
        {CATALYST_FAMILIES.map((f) => {
          const off = hidden.has(f.key);
          return (
            <button key={f.key} type="button" aria-pressed={!off}
              onClick={() => setHidden((h) => { const n = new Set(h); if (n.has(f.key)) n.delete(f.key); else n.add(f.key); return n; })}
              className={cn("inline-flex h-8 items-center gap-2 rounded-lg border border-line bg-surface px-3 text-[13px] font-medium text-ink-2 hover:text-ink", off && "opacity-45")}>
              <span className={cn("h-2 w-2 rounded-full", f.dot)} />{f.label}
            </button>
          );
        })}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,4fr)]">
        <section className="hidden overflow-hidden rounded-xl border border-line bg-surface sm:block">
          <header className="flex items-center gap-2 border-b border-line px-4 py-3">
            <h2 className="mr-auto font-display text-[18px] text-ink">{label}</h2>
            <Button size="icon" variant="ghost" aria-label="Previous month" onClick={() => setParams({ month: shiftMonth(month, -1) })}><ChevronLeft className="h-4 w-4" /></Button>
            <Button size="sm" variant="outline" onClick={() => { setParams({ month: null }); setSelected(null); }}>Today</Button>
            <Button size="icon" variant="ghost" aria-label="Next month" onClick={() => setParams({ month: shiftMonth(month, 1) })}><ChevronRight className="h-4 w-4" /></Button>
          </header>
          {monthQuery.isPending ? <Loading /> : (
            <>
              <div className="eyebrow grid grid-cols-7 border-b border-line text-center text-ink-3">
                {WEEKDAYS.map((d) => <div key={d} className="py-2">{d}</div>)}
              </div>
              <div className="grid grid-cols-7">
                {cells.map((day, i) => {
                  const events = day ? byDay.get(day) ?? [] : [];
                  return (
                    <button key={i} type="button" disabled={!day} onClick={() => day && setSelected(day === selected ? null : day)}
                      className={cn("flex min-h-[92px] flex-col items-stretch justify-start border-b border-r border-line p-1.5 text-left transition-colors", (i + 1) % 7 === 0 && "border-r-0", i >= cells.length - 7 && "border-b-0",
                        !day && "bg-surface-2/40", !!day && day === selected && "bg-accent-soft", !!day && day !== selected && "hover:bg-surface-2/50")}>
                      {day && (
                        <>
                          <span className={cn("num inline-grid h-6 w-6 place-items-center rounded-full text-xs",
                            day === today ? "bg-accent font-semibold text-accent-ink" : "text-ink-2")}>{Number(day.slice(8))}</span>
                          <div className="mt-1 space-y-0.5">
                            {events.slice(0, 3).map((e) => (
                              <div key={e.id} className="flex items-center gap-1 truncate text-[11px] text-ink">
                                <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", catalystFamily(e.event_type).dot)} />
                                <span className="truncate">{e.symbol ?? e.company_name}</span>
                              </div>
                            ))}
                            {events.length > 3 && <div className="text-[10px] text-ink-3">+{events.length - 3} more</div>}
                          </div>
                        </>
                      )}
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </section>

        <section className="rounded-xl border border-line bg-surface">
          <header className="flex items-baseline justify-between gap-2 border-b border-line px-4 py-3">
            <h2 className="font-display text-[18px] text-ink">{selected ? istDate(selected) : "Next 45 days"}</h2>
            {selected && <button type="button" onClick={() => setSelected(null)} className="text-xs font-medium text-accent hover:underline">Show upcoming</button>}
          </header>
          {upcomingQuery.isPending && !selected ? <Loading /> : agenda.length === 0 ? (
            <div className="p-4"><Empty title={selected ? "Nothing on this day" : "Nothing scheduled"} /></div>
          ) : (
            <ul className="divide-y divide-line">
              {agenda.map((e) => (
                <li key={e.id}>
                  <button type="button" onClick={() => navigate(`/company/${e.scrip_code}`)} className="flex w-full gap-3 px-4 py-3 text-left hover:bg-surface-2/50">
                    <span className="num w-14 shrink-0 text-[12px] text-ink-3">{istDate(e.event_date).replace(/ \d{4}$/, "")}</span>
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <Avatar name={e.company_name ?? e.scrip_code} symbol={e.symbol} size={16} />
                        <span className="text-[13.5px] font-semibold text-ink">{e.symbol ?? e.company_name}</span>
                        <Badge className={catalystFamily(e.event_type).chip}>{titleCase(e.event_type)}</Badge>
                      </span>
                      {e.description ? <span className="mt-0.5 block text-[13px] leading-relaxed text-ink-2">{e.description}</span> : null}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
