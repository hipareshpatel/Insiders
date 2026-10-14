import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import type { CardRow, Company, Dossier, Guidance } from "../../shared/types";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { cr, istDate, num, pct, rupees, signClass, titleCase } from "../lib/format";
import { periodEnd, periodKind } from "../lib/periods";
import { EVENT_LABELS, IMPACT_STYLE } from "../lib/taxonomy";
import { useQueryState } from "../lib/url";
import { parseCard } from "./SuperCard";
import { Badge } from "./ui/badge";
import { Sheet } from "./ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";

const STATUS_STYLE: Record<string, string> = {
  DELIVERED: "border-pos/30 bg-pos/10 text-pos",
  MET: "border-pos/30 bg-pos/10 text-pos",
  ON_TRACK: "border-info/30 bg-info/10 text-info",
  OPEN: "border-line bg-surface-2 text-ink-2",
  PENDING: "border-line bg-surface-2 text-ink-2",
  PARTIAL: "border-warn/30 bg-warn/10 text-warn",
  REVISED: "border-warn/30 bg-warn/10 text-warn",
  DELAYED: "border-warn/30 bg-warn/10 text-warn",
  MISSED: "border-neg/30 bg-neg/10 text-neg",
  WITHDRAWN: "border-neg/30 bg-neg/10 text-neg",
};

export function CompanyDrawer() {
  const [params, setParams] = useQueryState();
  const scrip = params.get("company");
  const tab = params.get("tab") ?? "dossier";
  const query = useQuery({
    queryKey: ["company", scrip],
    queryFn: () => api.company(scrip!),
    enabled: !!scrip,
  });
  const close = () => setParams({ company: null, tab: null, doc: null });
  const company = query.data?.company;
  const dossier = query.data?.dossier ?? null;
  const name = company?.company_name ?? dossier?.company_name ?? (scrip ? `BSE ${scrip}` : "");

  return (
    <Sheet
      open={!!scrip}
      onOpenChange={(open) => !open && close()}
      title={name}
      description={company ? <CompanyLine company={company} /> : scrip ? <span className="num">BSE {scrip}</span> : null}
    >
      {query.isPending ? (
        <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-ink-3" /></div>
      ) : query.isError ? (
        <p className="p-6 text-sm text-neg">Could not load this company: {String(query.error)}</p>
      ) : (
        <Tabs value={tab} onValueChange={(t) => setParams({ tab: t })} className="flex h-full flex-col">
          <TabsList className="bg-surface">
            <TabsTrigger value="dossier">Living dossier</TabsTrigger>
            <TabsTrigger value="timeline">2026 timeline</TabsTrigger>
            <TabsTrigger value="pdf">Filings &amp; PDF</TabsTrigger>
          </TabsList>
          <TabsContent value="dossier" className="p-5">
            {dossier ? <DossierPanel dossier={dossier} /> : <p className="text-sm text-ink-3">No memory yet: no material filing has been analysed for this company.</p>}
          </TabsContent>
          <TabsContent value="timeline" className="p-5">
            <TimelinePanel dossier={dossier} onOpen={(id) => setParams({ tab: "pdf", doc: id })} />
          </TabsContent>
          <TabsContent value="pdf" className="min-h-0 flex-1">
            <PdfPanel cards={query.data?.cards ?? []} selected={params.get("doc")} onSelect={(id) => setParams({ doc: id })} />
          </TabsContent>
        </Tabs>
      )}
    </Sheet>
  );
}

function CompanyLine({ company }: { company: Company }) {
  return (
    <span className="num flex flex-wrap gap-x-3 gap-y-1 text-xs">
      <span>{company.symbol ? `${company.symbol} · ` : ""}{company.scrip_code}</span>
      {company.sector && <span className="font-sans text-ink-2">{titleCase(company.sector)}</span>}
      {company.industry && <span className="font-sans text-ink-3">{company.industry}</span>}
      <span>{cr(company.market_cap_cr)}{company.size_category ? ` · ${titleCase(company.size_category)}cap` : ""}</span>
      <span>Last {rupees(company.last_price)}</span>
      <span>1W <span className={signClass(company.ret_1w)}>{pct(company.ret_1w)}</span></span>
      <span>1M <span className={signClass(company.ret_1m)}>{pct(company.ret_1m)}</span></span>
      <span>1Y <span className={signClass(company.ret_1y)}>{pct(company.ret_1y)}</span></span>
    </span>
  );
}

function Section({ title, children, hint }: { title: string; children: React.ReactNode; hint?: string }) {
  return (
    <section className="overflow-hidden rounded-xl border border-line bg-surface">
      <header className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-2.5">
        <h3 className="font-display text-sm font-bold text-ink">{title}</h3>
        {hint ? <span className="text-xs text-ink-3">{hint}</span> : null}
      </header>
      {children}
    </section>
  );
}

function DossierPanel({ dossier }: { dossier: Dossier }) {
  const balance = dossier.balance_sheet[dossier.balance_sheet.length - 1];
  return (
    <div className="space-y-4">
      {dossier.business_summary && (
        <div className="rounded-xl border border-memory-line bg-memory px-4 py-3 text-sm leading-relaxed text-ink">
          {dossier.business_summary.text}
        </div>
      )}
      <PromiseTable guidance={dossier.guidance} />
      {(dossier.watchlist?.length ?? 0) > 0 && (
        <Section title="Watchlist" hint="Follow-ups flagged by earlier cards">
          <table className="w-full text-sm">
            <tbody>
              {dossier.watchlist!.map((w) => (
                <tr key={w.id} className="border-b border-line last:border-0">
                  <td className="px-4 py-2 text-ink">{w.text}{w.target ? <span className="text-ink-2"> · target {w.target}</span> : null}</td>
                  <td className="num whitespace-nowrap px-4 py-2 text-xs text-ink-2">{w.check_in ?? "—"}</td>
                  <td className="px-4 py-2 text-right"><Badge className={STATUS_STYLE[w.status] ?? STATUS_STYLE.OPEN}>{titleCase(w.status)}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}
      <MetricsPivot dossier={dossier} />
      <div className="grid gap-4 md:grid-cols-2">
        <Section title="Balance sheet" hint={balance ? `as of ${istDate(String(balance.as_of))}` : undefined}>
          {balance ? (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 px-4 py-3 text-sm">
              {Object.entries(balance)
                .filter(([k, v]) => v !== null && !["as_of", "source_news_id"].includes(k))
                .map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-[11px] uppercase tracking-wide text-ink-3">{titleCase(k.replace(/_cr$/, ""))}</dt>
                    <dd className="num text-ink">{typeof v === "number" ? (k.endsWith("_cr") ? cr(v) : num(v)) : String(v)}</dd>
                  </div>
                ))}
            </dl>
          ) : <p className="px-4 py-3 text-sm text-ink-3">No balance-sheet data yet.</p>}
        </Section>
        <Section title="Upcoming events">
          {dossier.upcoming_events.length ? (
            <ul className="divide-y divide-line text-sm">
              {dossier.upcoming_events.slice(-8).map((e, i) => (
                <li key={i} className="flex gap-3 px-4 py-2">
                  <span className="num w-24 shrink-0 text-xs text-ink-2">{istDate(e.date)}</span>
                  <span className="text-ink"><span className="font-medium">{titleCase(e.event_type)}</span>{e.description ? ` · ${e.description}` : ""}</span>
                </li>
              ))}
            </ul>
          ) : <p className="px-4 py-3 text-sm text-ink-3">None recorded.</p>}
        </Section>
      </div>
      {(dossier.capital_actions?.length ?? 0) > 0 && (
        <Section title="Capital actions">
          <ul className="divide-y divide-line text-sm">
            {dossier.capital_actions!.map((a, i) => (
              <li key={i} className="num flex flex-wrap gap-x-4 px-4 py-2 text-ink">
                <span className="font-sans font-medium">{a.instrument}</span>
                {a.new_shares ? <span>{num(a.new_shares)} shares</span> : null}
                {a.issue_price ? <span>@ {rupees(a.issue_price)}</span> : null}
                {a.amount_cr ? <span>{cr(a.amount_cr)}</span> : null}
                <span className="text-ink-3">{istDate(a.as_of)}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function PromiseTable({ guidance }: { guidance: Guidance[] }) {
  return (
    <Section title="Promise vs delivery" hint={`${guidance.length} management commitments tracked`}>
      {guidance.length === 0 ? (
        <p className="px-4 py-3 text-sm text-ink-3">No forward-looking guidance recorded yet. Concall transcripts, AGM speeches and investor presentations feed this table.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-surface-2 text-left text-[11px] uppercase tracking-wide text-ink-3">
              <tr>
                <th className="px-4 py-2 font-semibold">Commitment</th>
                <th className="px-4 py-2 font-semibold">Given</th>
                <th className="px-4 py-2 font-semibold">Due</th>
                <th className="px-4 py-2 font-semibold">Status</th>
                <th className="px-4 py-2 font-semibold">Latest evidence</th>
              </tr>
            </thead>
            <tbody>
              {[...guidance].reverse().map((g) => {
                const last = g.status_history[g.status_history.length - 1];
                const overdue = g.due_date && g.due_date < new Date().toISOString().slice(0, 10) && ["OPEN", "ON_TRACK"].includes(g.status);
                return (
                  <tr key={g.id} className="border-t border-line align-top">
                    <td className="px-4 py-2 text-ink">
                      {g.statement}
                      {g.target ? <span className="text-ink-2"> · {g.target}</span> : null}
                      <div className="text-[11px] text-ink-3">{titleCase(g.source_type)}</div>
                    </td>
                    <td className="num whitespace-nowrap px-4 py-2 text-xs text-ink-2">{istDate(g.given_on)}</td>
                    <td className={cn("num whitespace-nowrap px-4 py-2 text-xs", overdue ? "font-semibold text-neg" : "text-ink-2")}>
                      {g.due ?? "—"}{overdue ? " · overdue" : ""}
                    </td>
                    <td className="px-4 py-2"><Badge className={STATUS_STYLE[g.status] ?? STATUS_STYLE.OPEN}>{titleCase(g.status)}</Badge></td>
                    <td className="px-4 py-2 text-xs text-ink-2">{last ? `${last.evidence} (${istDate(last.as_of)})` : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

function MetricsPivot({ dossier }: { dossier: Dossier }) {
  const groups = useMemo(() => {
    type Cell = { value: number; unit: string; yoy?: number | null };
    type Group = { periods: string[]; metrics: Map<string, Map<string, Cell>> };
    const byKind = new Map<string, Group>();
    for (const m of dossier.financial_metrics) {
      const kind = periodKind(m.period);
      const g: Group = byKind.get(kind) ?? { periods: [], metrics: new Map() };
      if (!g.periods.includes(m.period)) g.periods.push(m.period);
      const row = g.metrics.get(m.metric) ?? new Map<string, Cell>();
      row.set(m.period, { value: m.value, unit: m.unit, yoy: m.yoy_pct });
      g.metrics.set(m.metric, row);
      byKind.set(kind, g);
    }
    for (const g of byKind.values()) g.periods.sort((a, b) => periodEnd(a).localeCompare(periodEnd(b)));
    return [...byKind.entries()];
  }, [dossier.financial_metrics]);
  const [kind, setKind] = useState<string | null>(null);
  const active = groups.find(([k]) => k === kind) ?? groups.find(([k]) => k === "Quarter") ?? groups[0];

  return (
    <Section title="Financial baseline" hint="Every figure links to the filing it came from">
      {!active ? (
        <p className="px-4 py-3 text-sm text-ink-3">No financial metrics extracted yet.</p>
      ) : (
        <>
          {groups.length > 1 && (
            <div className="flex gap-1 border-b border-line px-4 py-2">
              {groups.map(([k]) => (
                <button key={k} type="button" onClick={() => setKind(k)}
                  className={cn("rounded px-2 py-0.5 text-xs", k === active[0] ? "bg-forest text-forest-ink" : "text-ink-2 hover:text-ink")}>
                  {k}
                </button>
              ))}
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-surface-2 text-[11px] uppercase tracking-wide text-ink-3">
                <tr>
                  <th className="px-4 py-2 text-left font-semibold">Metric</th>
                  {active[1].periods.slice(-6).map((p) => <th key={p} className="num px-3 py-2 text-right font-semibold">{p}</th>)}
                </tr>
              </thead>
              <tbody>
                {[...active[1].metrics.entries()].map(([metric, values]) => (
                  <tr key={metric} className="border-t border-line">
                    <td className="whitespace-nowrap px-4 py-1.5 text-ink">{titleCase(metric)}</td>
                    {active[1].periods.slice(-6).map((p) => {
                      const v = values.get(p);
                      return (
                        <td key={p} className="num whitespace-nowrap px-3 py-1.5 text-right text-ink">
                          {v ? (v.unit === "INR_CR" ? cr(v.value) : v.unit === "PCT" ? `${num(v.value)}%` : `${num(v.value)} ${v.unit === "UNITS" ? "" : v.unit}`) : <span className="text-ink-3">—</span>}
                          {v?.yoy != null ? <div className={cn("text-[11px]", signClass(v.yoy))}>{pct(v.yoy)} YoY</div> : null}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Section>
  );
}

function TimelinePanel({ dossier, onOpen }: { dossier: Dossier | null; onOpen: (newsId: string) => void }) {
  const events = [...(dossier?.timeline ?? [])].reverse();
  if (!events.length) return <p className="text-sm text-ink-3">No events recorded yet.</p>;
  let lastMonth = "";
  return (
    <ol className="relative ml-2 border-l border-line">
      {events.map((e) => {
        const month = new Date(e.date).toLocaleDateString("en-IN", { month: "long", year: "numeric", timeZone: "Asia/Kolkata" });
        const header = month !== lastMonth ? month : null;
        lastMonth = month;
        return (
          <li key={e.id} className="ml-4 pb-4">
            {header && <div className="-ml-4 mb-2 pl-4 text-[11px] font-bold uppercase tracking-wider text-ink-3">{header}</div>}
            <span className={cn("absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full border-2 border-bg",
              e.impact_level === "HIGH" ? "bg-high" : e.impact_level === "MODERATE" ? "bg-moderate" : "bg-low")} />
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="num text-ink-2">{istDate(e.date)}</span>
              <Badge className="border-line bg-surface-2 text-ink-2">{EVENT_LABELS[e.event_type] ?? e.event_type}</Badge>
              {e.impact_level && <Badge className={IMPACT_STYLE[e.impact_level]}>{titleCase(e.impact_level)}</Badge>}
            </div>
            <button type="button" onClick={() => onOpen(e.news_id)} className="mt-1 text-left text-sm text-ink hover:text-forest">
              {e.summary}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function PdfPanel({ cards, selected, onSelect }: { cards: CardRow[]; selected: string | null; onSelect: (id: string) => void }) {
  const current = cards.find((c) => c.news_id === selected) ?? cards[0];
  if (!cards.length) return <p className="p-5 text-sm text-ink-3">No analysed filings for this company yet.</p>;
  return (
    <div className="grid h-full min-h-[70vh] md:grid-cols-[320px_1fr]">
      <ul className="max-h-[40vh] overflow-y-auto border-b border-line md:max-h-none md:border-b-0 md:border-r">
        {cards.map((c) => {
          const body = parseCard(c);
          return (
            <li key={c.news_id}>
              <button type="button" onClick={() => onSelect(c.news_id)}
                className={cn("w-full border-b border-line px-4 py-2.5 text-left hover:bg-surface-2", c.news_id === current?.news_id && "bg-memory")}>
                <div className="num text-[11px] text-ink-3">{istDate(c.filed_at)} · {EVENT_LABELS[c.event_category] ?? c.event_category}</div>
                <div className="line-clamp-2 text-sm text-ink">{body?.headline ?? c.headline}</div>
              </button>
            </li>
          );
        })}
      </ul>
      <div className="flex min-h-[60vh] flex-col">
        {current?.pdf_url ? (
          <>
            <div className="flex items-center justify-between gap-2 border-b border-line bg-surface px-4 py-2 text-xs text-ink-2">
              <span className="truncate">Official filing on BSE</span>
              <a href={current.pdf_url} target="_blank" rel="noreferrer" className="inline-flex shrink-0 items-center gap-1 font-medium text-forest hover:underline">
                Open in new tab <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>
            <iframe key={current.pdf_url} src={current.pdf_url} title="Filing PDF" className="min-h-0 w-full flex-1 bg-surface-2" />
          </>
        ) : (
          <p className="p-5 text-sm text-ink-3">This filing has no attachment.</p>
        )}
      </div>
    </div>
  );
}
