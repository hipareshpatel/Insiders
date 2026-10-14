import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import type { Catalyst } from "../../shared/types";
import { Button } from "../components/ui/button";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { istDate, titleCase, todayIST } from "../lib/format";
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
  const d = new Date(Date.UTC(y, m - 1 + delta, 1));
  return d.toISOString().slice(0, 7);
}

export function CalendarView() {
  const [params, setParams] = useQueryState();
  const today = todayIST();
  const month = params.get("month") ?? today.slice(0, 7);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const { first, last, from, to } = monthBounds(month);
  const query = useQuery({ queryKey: ["calendar", from, to], queryFn: () => api.calendar(from, to) });

  const byDay = useMemo(() => {
    const map = new Map<string, Catalyst[]>();
    for (const e of query.data?.events ?? []) {
      if (hidden.has(catalystFamily(e.event_type).key)) continue;
      map.set(e.event_date, [...(map.get(e.event_date) ?? []), e]);
    }
    return map;
  }, [query.data, hidden]);

  const leading = (first.getUTCDay() + 6) % 7;
  const cells: (string | null)[] = [
    ...Array.from({ length: leading }, () => null),
    ...Array.from({ length: last.getUTCDate() }, (_, i) => `${month}-${String(i + 1).padStart(2, "0")}`),
  ];
  while (cells.length % 7) cells.push(null);
  const label = first.toLocaleDateString("en-IN", { month: "long", year: "numeric", timeZone: "UTC" });
  const dayEvents = selected ? byDay.get(selected) ?? [] : [];

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-5 sm:px-6">
      <header className="mb-4 flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <h1 className="font-display text-xl font-bold text-ink">Catalyst calendar</h1>
          <p className="text-sm text-ink-2">Record dates, meetings, rights windows, execution milestones and accountability checks.</p>
        </div>
        <Button size="icon" aria-label="Previous month" onClick={() => setParams({ month: shiftMonth(month, -1) })}><ChevronLeft className="h-4 w-4" /></Button>
        <span className="num min-w-36 text-center text-sm font-semibold text-ink">{label}</span>
        <Button size="icon" aria-label="Next month" onClick={() => setParams({ month: shiftMonth(month, 1) })}><ChevronRight className="h-4 w-4" /></Button>
        <Button size="sm" onClick={() => setParams({ month: null })}>Today</Button>
      </header>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {CATALYST_FAMILIES.map((f) => {
          const off = hidden.has(f.key);
          return (
            <button key={f.key} type="button" aria-pressed={!off}
              onClick={() => setHidden((h) => { const n = new Set(h); if (n.has(f.key)) n.delete(f.key); else n.add(f.key); return n; })}
              className={cn("rounded-full border px-2.5 py-1 text-xs font-medium", f.className, off && "opacity-40")}>
              {f.label}
            </button>
          );
        })}
      </div>

      {query.isPending ? <Loading /> : query.isError ? <Empty title="Could not load the calendar" body={String(query.error)} /> : (
        <>
          <div className="overflow-hidden rounded-xl border border-line bg-surface">
            <div className="grid grid-cols-7 border-b border-line bg-surface-2 text-center text-[11px] font-semibold uppercase tracking-wide text-ink-3">
              {WEEKDAYS.map((d) => <div key={d} className="py-2">{d}</div>)}
            </div>
            <div className="grid grid-cols-7">
              {cells.map((day, i) => {
                const events = day ? byDay.get(day) ?? [] : [];
                return (
                  <button key={i} type="button" disabled={!day} onClick={() => day && setSelected(day)}
                    className={cn("min-h-20 border-b border-r border-line p-1 text-left align-top sm:min-h-28 sm:p-1.5",
                      !day && "bg-surface-2/50", !!day && day === selected && "bg-memory", (i + 1) % 7 === 0 && "border-r-0")}>
                    {day && (
                      <>
                        <span className={cn("num inline-grid h-6 w-6 place-items-center rounded-full text-xs",
                          day === today ? "bg-forest font-bold text-forest-ink" : "text-ink-2")}>{Number(day.slice(8))}</span>
                        <div className="mt-1 space-y-0.5">
                          {events.slice(0, 3).map((e) => (
                            <div key={e.id} className={cn("truncate rounded border px-1 text-[10px] font-medium sm:text-[11px]", catalystFamily(e.event_type).className)}>
                              {e.symbol ?? e.company_name}
                            </div>
                          ))}
                          {events.length > 3 && <div className="px-1 text-[10px] text-ink-3">+{events.length - 3} more</div>}
                        </div>
                      </>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
          {selected && (
            <section className="mt-4 rounded-xl border border-line bg-surface">
              <header className="border-b border-line px-4 py-2.5 font-display text-sm font-bold">{istDate(selected)}</header>
              {dayEvents.length === 0 ? <p className="px-4 py-4 text-sm text-ink-3">No catalysts on this day.</p> : (
                <ul className="divide-y divide-line">
                  {dayEvents.map((e) => (
                    <li key={e.id}>
                      <button type="button" onClick={() => setParams({ company: e.scrip_code, tab: "dossier" })}
                        className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-left hover:bg-surface-2">
                        <span className={cn("rounded border px-1.5 py-0.5 text-[11px] font-semibold", catalystFamily(e.event_type).className)}>{titleCase(e.event_type)}</span>
                        <span className="font-medium text-ink">{e.company_name}</span>
                        <span className="min-w-0 flex-1 text-sm text-ink-2">{e.description}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
