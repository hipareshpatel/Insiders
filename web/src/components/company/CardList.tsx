import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { CardRow } from "../../../shared/types";
import { cn } from "../../lib/cn";
import { istDate } from "../../lib/format";
import { EVENT_LABELS } from "../../lib/taxonomy";
import { AnnouncementCard } from "../AnnouncementCard";
import { parseCard } from "../FilingCard";
import { IMPACT_DOT } from "../PriceChart";
import { plain } from "../RichText";
import { reaction } from "./companyText";

const FILTERS = [["all", "All"], ["high", "High"], ["results", "Results"], ["deals", "Deals"]] as const;
type Filter = (typeof FILTERS)[number][0];
const RESULTS = new Set(["RESULTS", "CONCALL_PRESENTATION", "ANNUAL_REPORT"]);
const DEALS = new Set(["ORDER_WIN", "M_AND_A", "CAPEX", "FUNDRAISE", "RIGHTS_ISSUE"]);
const keep = (f: Filter, r: CardRow) => f === "all" || (f === "high" ? r.impact_level === "HIGH" : f === "results" ? RESULTS.has(r.event_category) : DEALS.has(r.event_category));

const IMPACT_CHIP: Record<string, [string, string]> = {
  HIGH: ["High", "bg-neg-soft text-impact-high"], MODERATE: ["Moderate", "bg-warn-soft text-warn"], LOW: ["Low", "bg-surface-2 text-ink-2"],
};
export const chip = "inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-[3px] text-[11.5px] font-bold";
/** "19 Oct 26", the rail's date. */
export const railDate = (iso: string) => istDate(iso).replace("Sept", "Sep").replace(/ 20(\d\d)$/, " $1");
/** The rail's date column; a phone drops the year so the date keeps to one line. */
export function RailTime({ iso }: { iso: string }) {
  const [day, mon, year] = railDate(iso).split(" ");
  return <time className="num whitespace-nowrap pt-[3px] text-right text-[11.5px] font-semibold text-ink-3 sm:text-[12px]">{day} {mon}<span className="hidden sm:inline"> {year}</span></time>;
}

/** The company's cards as a dated rail: an impact dot, the headline, one line of the AI's reading and chips (impact,
 *  family, the T+1 / T+5 move once the post-mortem has it); a row opens into the full card. `focus` (a news id and a
 *  counter, from a chart dot) pages to that card, opens it and scrolls to it. */
export function CardList({ cards, pageSize, focus, header }: {
  cards: CardRow[]; pageSize: number; focus?: { id: string; n: number } | null;
  header: (filters: ReactNode, shown: number) => ReactNode;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [scrollTo, setScrollTo] = useState<string | null>(null);
  const rows = useMemo(() => cards.filter((r) => keep(filter, r)), [cards, filter]);
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));

  useEffect(() => {
    if (!focus) return;
    const i = cards.findIndex((r) => r.news_id === focus.id);
    if (i < 0) return;
    setFilter("all");
    setPage(Math.floor(i / pageSize));
    setOpen(focus.id);
    setScrollTo(focus.id);
  }, [focus, cards, pageSize]);
  // after the page with the card has rendered
  useEffect(() => {
    if (!scrollTo) return;
    document.getElementById(`co-card-${scrollTo}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    setScrollTo(null);
  }, [scrollTo, page, filter]);

  const filters = (
    <span className="inline-flex rounded-[11px] bg-surface-2 p-[3px]" role="radiogroup" aria-label="Show">
      {FILTERS.map(([k, l]) => (
        <button key={k} type="button" role="radio" aria-checked={filter === k} onClick={() => { setFilter(k); setPage(0); }}
          className={cn("rounded-lg px-2.5 py-1 text-[12px] font-bold", filter === k ? "bg-surface text-ink shadow-sm" : "text-ink-3")}>{l}</button>
      ))}
    </span>
  );
  const slice = rows.slice(page * pageSize, (page + 1) * pageSize);
  return (
    <section className="card-soft rise-in min-w-0 px-5 pb-4 pt-4">
      {header(filters, rows.length)}
      {slice.length ? (
        <ol className="mt-3">
          {slice.map((row, k) => <Row key={row.news_id} row={row} last={k === slice.length - 1} open={open === row.news_id}
            onToggle={() => setOpen(open === row.news_id ? null : row.news_id)} />)}
        </ol>
      ) : <p className="mt-3 text-[13.5px] text-ink-3">No {filter === "high" ? "high-impact" : filter === "results" ? "results" : "deal"} cards for this company yet.</p>}
      {pages > 1 && <Pager page={page} pages={pages} onPage={setPage} />}
    </section>
  );
}

function Row({ row, last, open, onToggle }: { row: CardRow; last: boolean; open: boolean; onToggle: () => void }) {
  const card = useMemo(() => parseCard(row), [row]);
  const move = reaction(row.post_event_return_json);
  const [impact, impactCls] = IMPACT_CHIP[row.impact_level] ?? IMPACT_CHIP.LOW;
  return (
    <li id={`co-card-${row.news_id}`} className="grid scroll-mt-32 grid-cols-[58px_16px_minmax(0,1fr)] gap-x-2 sm:grid-cols-[70px_18px_minmax(0,1fr)] sm:gap-x-2.5">
      <RailTime iso={row.filed_at} />
      <span aria-hidden className="flex flex-col items-center">
        <i className="mt-[3px] h-3 w-3 shrink-0 rounded-full border-[3px] border-surface ring-1 ring-line-strong" style={{ background: IMPACT_DOT[row.impact_level] ?? IMPACT_DOT.LOW }} />
        {!last || open ? <u className="w-[2px] flex-1 bg-line" /> : null}
      </span>
      <div className={cn("min-w-0", last && !open ? "pb-1" : "pb-4")}>
        <button type="button" aria-expanded={open} onClick={onToggle} className="block w-full text-left">
          <b className="block text-[14.5px] font-extrabold leading-snug tracking-tight text-ink hover:text-accent">{plain(card?.headline ?? row.headline)}</b>
          {card?.takeaway && !open ? <span className="mt-0.5 line-clamp-2 block text-[13.5px] leading-snug text-ink-2 sm:line-clamp-1">{plain(card.takeaway)}</span> : null}
        </button>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <span className={cn(chip, impactCls)}>{impact}</span>
          <span className={cn(chip, "bg-accent-soft text-accent")}>{EVENT_LABELS[row.event_category] ?? card?.category_tag ?? "Update"}</span>
          {([["T+1", move.t1], ["T+5", move.t5]] as const).map(([l, v]) => v != null && (
            <span key={l} className={cn(chip, "num", v >= 0 ? "bg-pos-soft text-pos" : "bg-neg-soft text-neg")}>{l} {v > 0 ? "+" : v < 0 ? "−" : ""}{Math.abs(v).toFixed(1)}%</span>
          ))}
        </div>
      </div>
      {open && <div className="col-span-3 pb-4"><AnnouncementCard row={row} /></div>}
    </li>
  );
}

/** Page numbers, with the ends and the pages next to the current one when there are many. */
function Pager({ page, pages, onPage }: { page: number; pages: number; onPage: (p: number) => void }) {
  const show = [...new Set([0, page - 1, page, page + 1, pages - 1])].filter((p) => p >= 0 && p < pages).sort((a, b) => a - b);
  return (
    <nav aria-label="Pages" className="mt-2 flex flex-wrap items-center justify-center gap-1.5 border-t border-line pt-3">
      {show.map((p, k) => (
        <span key={p} className="contents">
          {k > 0 && p - show[k - 1] > 1 && <span className="px-1 text-ink-3">…</span>}
          <button type="button" aria-current={p === page ? "page" : undefined} onClick={() => onPage(p)}
            className={cn("num h-8 min-w-8 rounded-[10px] px-2.5 text-[12.5px] font-extrabold", p === page ? "grad-accent" : "bg-surface-2 text-ink-2 hover:text-ink")}>{p + 1}</button>
        </span>
      ))}
    </nav>
  );
}
