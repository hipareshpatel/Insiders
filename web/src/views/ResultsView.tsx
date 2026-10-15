import { useInfiniteQuery } from "@tanstack/react-query";
import { ArrowUpRight, FileText, Search } from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";
import { useLocation } from "wouter";
import type { CardBody, CardRow } from "../../shared/types";
import { Avatar } from "../components/Avatar";
import { FilingBody, parseCard } from "../components/FilingCard";
import { Badge, Select } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { cr, istDate, todayIST } from "../lib/format";
import { SIZES, TONE_BORDER, TONE_CHIP, verdict, type Tone } from "../lib/taxonomy";
import { periodEnd } from "../lib/periods";
import { useQueryState } from "../lib/url";
import { Empty, Loading } from "./FeedView";

export function Change({ value, unit = "%" }: { value?: number; unit?: "%" | "bp" }) {
  if (value == null) return <span className="text-ink-3">—</span>;
  const text = unit === "bp" ? `${value > 0 ? "+" : ""}${Math.round(value)}bp` : `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
  return <span className={cn("font-semibold", value > 0 ? "text-pos" : value < 0 ? "text-neg" : "text-ink-2")}>{text}</span>;
}

export function ResultsView() {
  const [params, setParams] = useQueryState();
  const [, navigate] = useLocation();
  const [open, setOpen] = useState<string | null>(null);
  const q = params.get("q") ?? "";
  const [text, setText] = useState(q);
  useEffect(() => setText(q), [q]);
  useEffect(() => {
    const id = setTimeout(() => { if (q !== text) setParams({ q: text || null }); }, 300);
    return () => clearTimeout(id);
  }, [text, q, setParams]);
  const size = params.get("size");
  const quarter = params.get("quarter");
  const tone = params.get("verdict");

  const query = useInfiniteQuery({
    queryKey: ["results", size, params.get("q")],
    queryFn: ({ pageParam }) => api.feed({ from: "2026-01-01", to: todayIST(), category: "RESULTS", size: size ?? undefined, q: params.get("q") ?? undefined }, pageParam, 50),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
  const rows = useMemo(() => (query.data?.pages.flatMap((p) => p.cards) ?? [])
    .map((row) => ({ row, card: parseCard(row) }))
    .filter((r): r is { row: CardRow; card: CardBody } => !!r.card), [query.data]);
  const quarters = [...new Set(rows.map((r) => r.card.results?.period).filter(Boolean) as string[])]
    .sort((a, b) => periodEnd(b).localeCompare(periodEnd(a)));
  const visible = rows.filter((r) => (!quarter || r.card.results?.period === quarter) && (!tone || (r.card.tone ?? "NEUTRAL") === tone));

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6">
      <header className="mb-4">
        <h1 className="font-display text-[30px] leading-tight text-ink">Results</h1>
        <p className="mt-1 text-sm text-ink-2">Quarterly results with year-on-year changes, read against each company's memory. Click a row for the full card.</p>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <Select aria-label="Quarter" value={quarter ?? ""} onChange={(e) => setParams({ quarter: e.target.value || null })}>
          <option value="">All quarters</option>
          {quarters.map((q) => <option key={q} value={q}>{q}</option>)}
        </Select>
        <Select aria-label="Verdict" value={tone ?? ""} onChange={(e) => setParams({ verdict: e.target.value || null })}>
          <option value="">Any verdict</option>
          <option value="POSITIVE">Strong / Good</option>
          <option value="MIXED">Mixed</option>
          <option value="NEGATIVE">Weak</option>
          <option value="NEUTRAL">Neutral</option>
        </Select>
        <Select aria-label="Market cap" value={size ?? ""} onChange={(e) => setParams({ size: e.target.value || null })}>
          <option value="">All sizes</option>
          {SIZES.map((s) => <option key={s} value={s}>{s.charAt(0) + s.slice(1).toLowerCase()}cap</option>)}
        </Select>
        <label className="relative min-w-0 flex-1 basis-56">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Search company"
            className="h-9 w-full rounded-lg border border-line bg-surface pl-9 pr-3 text-[13px] text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none" />
        </label>
      </div>

      <div className="mt-4">
        {query.isPending ? <Loading /> : !query.data ? <Empty title="Couldn't load results" body={String(query.error)} /> : visible.length === 0 ? (
          <div className="space-y-3">
            <Empty title="No results match" body={query.hasNextPage
              ? "None in the results loaded so far. Load older results to keep looking."
              : "Results appear here as companies report and the pipeline analyses them."} />
            {query.hasNextPage && (
              <div className="text-center"><Button size="sm" onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage}>Load older results</Button></div>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full min-w-[920px] text-[13.5px]">
              <thead className="eyebrow border-b border-line text-left text-ink-3">
                <tr>
                  <th className="py-3 pl-5 pr-3 font-semibold">Date</th>
                  <th className="px-3 py-3 font-semibold">Company</th>
                  <th className="px-3 py-3 font-semibold">Verdict</th>
                  <th className="px-3 py-3 text-right font-semibold">MCap</th>
                  <th className="px-3 py-3 font-semibold">Qtr</th>
                  <th className="px-3 py-3 text-right font-semibold">Rev YoY</th>
                  <th className="px-3 py-3 text-right font-semibold">EBITDA YoY</th>
                  <th className="px-3 py-3 text-right font-semibold">OPM YoY</th>
                  <th className="px-3 py-3 text-right font-semibold">PAT YoY</th>
                  <th className="px-3 py-3 font-semibold">Signals</th>
                  <th className="px-3 py-3" />
                </tr>
              </thead>
              <tbody>
                {visible.map(({ row, card }) => {
                  const t = (card.tone ?? "NEUTRAL") as Tone;
                  const v = verdict(t, row.impact_level);
                  const r = card.results;
                  const isOpen = open === row.news_id;
                  return (
                    <Fragment key={row.news_id}>
                      <tr onClick={() => setOpen(isOpen ? null : row.news_id)} tabIndex={0} aria-expanded={isOpen}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(isOpen ? null : row.news_id); } }}
                        className={cn("num cursor-pointer border-b border-line border-l-[3px] hover:bg-surface-2/60", TONE_BORDER[t], isOpen && "bg-surface-2/60")}>
                        <td className="whitespace-nowrap py-3 pl-[17px] pr-3 text-ink-3">{istDate(row.filed_at).replace(/ \d{4}$/, "")}</td>
                        <td className="px-3 py-3">
                          <span className="flex items-center gap-2">
                            <Avatar name={row.company_name} symbol={row.symbol} size={20} />
                            <span className="font-sans font-semibold text-ink">{row.symbol ?? row.scrip_code}</span>
                          </span>
                        </td>
                        <td className="px-3 py-3"><Badge className={TONE_CHIP[v.tone]}>{v.label}</Badge></td>
                        <td className="whitespace-nowrap px-3 py-3 text-right text-ink-2">{cr(row.market_cap_cr)}</td>
                        <td className="num whitespace-nowrap px-3 py-3 font-medium text-ink">{r?.period ?? "—"}</td>
                        <td className="px-3 py-3 text-right"><Change value={r?.revenue?.yoy_pct} /></td>
                        <td className="px-3 py-3 text-right"><Change value={r?.ebitda?.yoy_pct} /></td>
                        <td className="px-3 py-3 text-right"><Change value={r?.ebitda_margin?.yoy_bps} unit="bp" /></td>
                        <td className="px-3 py-3 text-right"><Change value={r?.pat?.yoy_pct} /></td>
                        <td className="px-3 py-3 font-sans text-xs">
                          {card.signals.filter((s) => s.severity === "WARNING").length > 0 && <span className="mr-2 text-warn">⚠ {card.signals.filter((s) => s.severity === "WARNING").length}</span>}
                          {card.signals.filter((s) => s.severity === "POSITIVE").length > 0 && <span className="text-pos">✓ {card.signals.filter((s) => s.severity === "POSITIVE").length}</span>}
                        </td>
                        <td className="whitespace-nowrap px-3 py-3 text-right">
                          {row.pdf_url && (
                            <a href={row.pdf_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} aria-label="Official PDF"
                              className="mr-2 inline-grid h-7 w-7 place-items-center rounded-md text-ink-3 hover:bg-surface-2 hover:text-ink"><FileText className="h-4 w-4" /></a>
                          )}
                          <button type="button" aria-label="Open company" onClick={(e) => { e.stopPropagation(); navigate(`/company/${row.scrip_code}`); }}
                            className="inline-grid h-7 w-7 place-items-center rounded-md text-ink-3 hover:bg-surface-2 hover:text-ink"><ArrowUpRight className="h-4 w-4" /></button>
                        </td>
                      </tr>
                      {isOpen && (
                        <tr className="border-b border-line">
                          <td colSpan={11} className="p-0"><FilingBody row={row} card={card} showHeadline /></td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
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
      </div>
    </div>
  );
}
