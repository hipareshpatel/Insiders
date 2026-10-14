import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CheckCircle2 } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useLocation, useParams } from "wouter";
import type { CardRow, Company, Dossier, Guidance } from "../../shared/types";
import { Avatar } from "../components/Avatar";
import { AnnouncementCard, PROVISIONAL_STAGES, STAGE_LABEL } from "../components/AnnouncementCard";
import { parseCard, SIGNAL } from "../components/FilingCard";
import { Badge, TabStrip } from "../components/ui/badge";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { cr, istDate, num, pct, rupees, signClass, titleCase, todayIST } from "../lib/format";
import { periodEnd, periodKind } from "../lib/periods";
import { EVENT_LABELS, SECTORS, TONE_CHIP, TONE_LABEL, TONE_STRIPE, verdict, type Tone } from "../lib/taxonomy";
import { useQueryState } from "../lib/url";
import { Empty, Loading } from "./FeedView";
import { Change } from "./ResultsView";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "results", label: "Results" },
  { key: "promises", label: "Promise tracker" },
  { key: "timeline", label: "Timeline" },
  { key: "filings", label: "Filings" },
];

const WATCH_VERB: Record<string, string> = { KPI: "Verify", APPROVAL: "Pending", CONCERN: "Analyst concern" };

const STATUS_CHIP: Record<string, string> = {
  DELIVERED: "bg-pos-soft text-pos", MET: "bg-pos-soft text-pos", ON_TRACK: "bg-info-soft text-info",
  OPEN: "bg-surface-2 text-ink-2", PENDING: "bg-surface-2 text-ink-2", PARTIAL: "bg-warn-soft text-warn",
  REVISED: "bg-warn-soft text-warn", DELAYED: "bg-warn-soft text-warn", MISSED: "bg-neg-soft text-neg", WITHDRAWN: "bg-neg-soft text-neg",
};

export function CompanyPage() {
  const { scrip } = useParams<{ scrip: string }>();
  const [params, setParams] = useQueryState();
  const tab = params.get("tab") ?? "overview";
  const query = useQuery({ queryKey: ["company", scrip], queryFn: () => api.company(scrip!), enabled: !!scrip });

  if (query.isPending) return <Loading />;
  if (query.isError) return <div className="mx-auto max-w-[1200px] p-6"><Empty title="Couldn't load this company" body={String(query.error)} /></div>;
  const { company, cards, dossier } = query.data;
  if (!company && !dossier) return <div className="mx-auto max-w-[1200px] p-6"><Empty title={`No company with BSE code ${scrip}`} /></div>;
  const name = company?.company_name ?? dossier?.company_name ?? scrip!;
  const symbol = company?.symbol ?? dossier?.symbol ?? null;

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6">
      <Link href="/companies" className="mb-4 inline-flex items-center gap-1 text-[13px] text-ink-3 hover:text-ink">
        <ArrowLeft className="h-3.5 w-3.5" /> Companies
      </Link>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Avatar name={name} symbol={symbol} size={36} />
            <h1 className="font-display text-[32px] leading-none text-ink">{symbol ?? name}</h1>
            <span className="text-[15px] text-ink-2">{name} <span className="text-[12px] text-ink-3">· BSE {scrip}</span></span>
          </div>
          <div className="num mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="text-[26px] font-bold text-ink">{rupees(company?.last_price)}</span>
            <span className="text-[13px] text-ink-3">1W <span className={signClass(company?.ret_1w)}>{pct(company?.ret_1w)}</span></span>
            <span className="text-[13px] text-ink-3">1M <span className={signClass(company?.ret_1m)}>{pct(company?.ret_1m)}</span></span>
            <span className="text-[13px] text-ink-3">1Y <span className={signClass(company?.ret_1y)}>{pct(company?.ret_1y)}</span></span>
            {company?.price_date && <span className="text-[12px] text-ink-3">as of {istDate(company.price_date)}</span>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {company?.sector && <Badge className="bg-surface-2 text-ink-2">{SECTORS[company.sector] ?? titleCase(company.sector)}</Badge>}
          {company?.size_category && <Badge className="bg-accent-soft text-accent">{titleCase(company.size_category)}cap</Badge>}
        </div>
      </header>

      <TabStrip className="mt-6" items={TABS} value={tab} onChange={(key) => setParams({ tab: key === "overview" ? null : key })} />

      <div className="mt-5">
        {tab === "overview" && <Overview company={company} dossier={dossier} cards={cards} onTab={(t) => setParams({ tab: t })} />}
        {tab === "results" && (
          <div className="space-y-4">
            <ResultsScorecard cards={cards} />
            {dossier ? <MetricsPanel dossier={dossier} /> : <Empty title="No results analysed yet" />}
          </div>
        )}
        {tab === "promises" && <PromiseTracker dossier={dossier} />}
        {tab === "timeline" && <Timeline dossier={dossier} />}
        {tab === "filings" && (
          <div className="mx-auto max-w-[720px] space-y-4">
            {cards.length ? cards.map((row) => <AnnouncementCard key={row.news_id} row={row} />) : <Empty title="No material filings analysed yet" />}
          </div>
        )}
      </div>
      <p className="mt-10 text-center text-[11px] text-ink-3">AI summaries of public BSE filings, refreshed with every new filing. Not investment advice.</p>
    </div>
  );
}

function Panel({ title, children, hint, className }: { title: string; children: ReactNode; hint?: ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-xl border border-line bg-surface", className)}>
      <header className="flex flex-wrap items-baseline justify-between gap-2 px-5 pt-4">
        <h2 className="font-display text-[19px] leading-tight text-ink">{title}</h2>
        {hint ? <span className="text-xs text-ink-3">{hint}</span> : null}
      </header>
      <div className="px-5 pb-5 pt-3">{children}</div>
    </section>
  );
}

function promiseStats(guidance: Guidance[]) {
  const delivered = guidance.filter((g) => g.status === "DELIVERED").length;
  const missed = guidance.filter((g) => ["MISSED", "DELAYED", "WITHDRAWN"].includes(g.status)).length;
  const open = guidance.filter((g) => ["OPEN", "ON_TRACK", "REVISED"].includes(g.status)).length;
  return { delivered, missed, open, resolved: delivered + missed };
}

function Overview({ company, dossier, cards, onTab }: { company: Company | null; dossier: Dossier | null; cards: CardRow[]; onTab: (t: string) => void }) {
  const today = todayIST();
  const parsed = useMemo(() => cards.map((row) => ({ row, card: parseCard(row) })).filter((x) => x.card), [cards]);
  const latest = parsed[0];
  const fundamentals = latest?.card?.fundamentals ?? {};
  const stats = promiseStats(dossier?.guidance ?? []);
  const next = (dossier?.upcoming_events ?? []).filter((e) => e.date >= today).sort((a, b) => a.date.localeCompare(b.date))[0];

  const good: { title: string; text: string; date: string }[] = [];
  const bad: { title: string; text: string; date: string }[] = [];
  for (const { row, card } of parsed.slice(0, 12)) {
    for (const s of card!.signals) {
      const item = { title: SIGNAL[s.type]?.label ?? titleCase(s.type), text: s.text, date: row.filed_at };
      if (s.severity === "POSITIVE") good.push(item);
      else if (s.severity === "WARNING") bad.push(item);
    }
    // A notable change that a computed signal already reports (same % move) would say the same thing twice.
    const said = card!.signals.map((s) => s.text).join(" ");
    for (const c of card!.notable_changes ?? []) {
      const moves = (c.change ?? "").match(/\d+(?:\.\d+)?/g) ?? [];
      if (moves.some((n) => said.includes(`${n}%`) || said.includes(`${n} bps`))) continue;
      const item = { title: titleCase(c.metric), text: `${c.previous ?? "—"} → ${c.current ?? "—"}${c.change ? ` (${c.change})` : ""}. ${c.why}`, date: row.filed_at };
      if (c.direction === "POSITIVE") good.push(item);
      else if (c.direction === "NEGATIVE") bad.push(item);
    }
  }

  const tracking = [
    ...(dossier?.watchlist ?? []).filter((w) => ["OPEN", "PENDING", "PARTIAL"].includes(w.status))
      .map((w) => ({ when: w.check_in ?? "—", text: `${WATCH_VERB[w.kind] ?? "Pending"}: ${w.text}${w.target ? ` (target ${w.target})` : ""}` })),
    ...(dossier?.guidance ?? []).filter((g) => ["OPEN", "ON_TRACK"].includes(g.status))
      .map((g) => ({ when: g.due ?? "—", text: `Promise due: ${g.statement}` })),
    ...(dossier?.upcoming_events ?? []).filter((e) => e.date >= today)
      .map((e) => ({ when: istDate(e.date), text: `${titleCase(e.event_type)}${e.description ? `: ${e.description}` : ""}` })),
  ];

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-3">
          {[
            ["Market cap", cr(company?.market_cap_cr)],
            ["Size", company?.size_category ? `${titleCase(company.size_category)}cap` : "—"],
            [`Revenue${fundamentals.revenue?.period ? ` · ${fundamentals.revenue.period}` : ""}`, cr(fundamentals.revenue?.value)],
            ["Debt", cr(fundamentals.debt?.value)],
            ["Net worth", cr(fundamentals.net_worth?.value)],
            ["Filings analysed", num(cards.length)],
          ].map(([label, value]) => (
            <div key={label} className="bg-surface px-4 py-3 text-center">
              <div className="eyebrow text-ink-3">{label}</div>
              <div className="num mt-1 text-[15px] font-semibold text-ink">{value}</div>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line">
          <Tile label="Promise record" value={stats.resolved ? `${stats.delivered} of ${stats.resolved} delivered` : "No promises resolved yet"}
            tone={stats.resolved ? (stats.missed ? "MIXED" : "POSITIVE") : "NEUTRAL"} action="View tracker" onAction={() => onTab("promises")} />
          <Tile label="Open commitments" value={`${stats.open} tracked`} tone="NEUTRAL" action="View tracker" onAction={() => onTab("promises")} />
          <Tile label="Latest filing" value={latest?.card?.tone ? TONE_LABEL[latest.card.tone as Tone] : "—"} tone={(latest?.card?.tone ?? "NEUTRAL") as Tone}
            sub={latest ? `${EVENT_LABELS[latest.row.event_category] ?? ""} · ${istDate(latest.row.filed_at)}` : undefined} action="View filings" onAction={() => onTab("filings")} />
          <Tile label="Next catalyst" value={next ? titleCase(next.event_type) : "None scheduled"} tone="NEUTRAL"
            sub={next ? istDate(next.date) : undefined} />
        </div>
      </div>

      <Panel title="The story">
        {dossier?.business_summary ? (
          <p className="text-[14.5px] leading-relaxed text-ink">{dossier.business_summary.text}</p>
        ) : <p className="text-sm text-ink-3">No business summary yet. It is written from the first material filing analysed.</p>}
        {latest?.card?.takeaway ? (
          <p className="mt-3 border-l-2 border-accent-line pl-3 text-[14px] leading-relaxed text-ink-2">
            <span className="font-semibold text-ink">Latest read · {istDate(latest.row.filed_at)}:</span> {latest.card.takeaway}
          </p>
        ) : null}
      </Panel>

      <Panel title="How the story is unfolding" hint={dossier?.timeline.length ? `${dossier.timeline.length} events since 1 Jan 2026` : undefined}>
        {dossier?.timeline.length ? (
          <ul className="space-y-2.5">
            {[...dossier.timeline].reverse().slice(0, 8).map((t) => (
              <li key={t.id} className="grid gap-x-4 gap-y-0.5 sm:grid-cols-[110px_minmax(0,1fr)]">
                <span className="num text-[13px] text-ink-3">{istDate(t.date)}</span>
                <span className="text-[14px] leading-relaxed text-ink">
                  <span className="font-semibold text-accent">{EVENT_LABELS[t.event_type] ?? titleCase(t.event_type)}</span> · {t.summary}
                </span>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-ink-3">No events recorded yet.</p>}
      </Panel>

      <DealsAndNotes dossier={dossier} />

      <Panel title="The good & the bad" hint="Computed signals and notable changes from recent filings">
        <div className="grid gap-6 md:grid-cols-2">
          <GoodBad title="The good" items={good} tone="POSITIVE" />
          <GoodBad title="The bad" items={bad} tone="NEGATIVE" />
        </div>
      </Panel>

      <Panel title="What to track">
        {tracking.length ? (
          <ul className="divide-y divide-line">
            {tracking.map((t, i) => (
              <li key={i} className="grid gap-x-4 gap-y-0.5 py-2 sm:grid-cols-[140px_minmax(0,1fr)]">
                <span className="num text-[13px] text-ink-3">{t.when}</span>
                <span className="text-[14px] text-ink">{t.text}</span>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-ink-3">Nothing to track yet.</p>}
      </Panel>
    </div>
  );
}

/** Each order, deal or capex plan once, at its latest stage; plus operating facts worth remembering. */
function DealsAndNotes({ dossier }: { dossier: Dossier | null }) {
  const deals = [...(dossier?.deals ?? [])].reverse().slice(0, 10);
  const notes = [...(dossier?.operating_notes ?? [])].reverse().slice(0, 6);
  if (!deals.length && !notes.length) return null;
  return (
    <div className={cn("grid gap-4", deals.length && notes.length && "md:grid-cols-2")}>
      {deals.length > 0 && (
        <Panel title="Orders, deals and capex" hint="Each deal once, at its latest stage">
          <ul className="divide-y divide-line">
            {deals.map((d) => (
              <li key={d.id} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-baseline gap-x-3 py-2">
                <span className="num text-[12px] text-ink-3">{istDate(d.as_of)}</span>
                <span className="min-w-0 text-[13.5px] text-ink">
                  <span className="num font-semibold">{d.amount_cr != null ? cr(d.amount_cr) : "—"}</span> {titleCase(d.kind)}
                  {d.segment ? <span className="text-ink-2"> · {d.segment}</span> : null}
                  {d.counterparty ? <span className="text-ink-2"> · {d.counterparty}</span> : null}
                  {d.progress ? <span className="block text-[12px] text-ink-3">{d.progress}</span> : null}
                </span>
                <Badge className={PROVISIONAL_STAGES.has(d.stage) ? "bg-warn-soft text-warn" : "bg-surface-2 text-ink-2"}>
                  {STAGE_LABEL[d.stage] ?? titleCase(d.stage)}
                </Badge>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {notes.length > 0 && (
        <Panel title="Operating notes" hint="Facts from filings worth remembering">
          <ul className="space-y-2">
            {notes.map((n, i) => (
              <li key={i} className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 text-[13.5px]">
                <span className="num text-[12px] text-ink-3">{istDate(n.as_of)}</span>
                <span className="text-ink">{n.text}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

function Tile({ label, value, sub, tone, action, onAction }: { label: string; value: string; sub?: string; tone: Tone; action?: string; onAction?: () => void }) {
  return (
    <div className="flex flex-col bg-surface px-4 py-3">
      <span className="eyebrow text-ink-3">{label}</span>
      <span className={cn("mt-1 text-[15px] font-semibold", tone === "POSITIVE" ? "text-pos" : tone === "NEGATIVE" ? "text-neg" : tone === "MIXED" ? "text-warn" : "text-ink")}>{value}</span>
      {sub ? <span className="text-xs text-ink-3">{sub}</span> : null}
      {action && onAction ? (
        <button type="button" onClick={onAction} className="mt-auto pt-2 text-left text-xs font-medium text-accent hover:underline">{action} →</button>
      ) : null}
    </div>
  );
}

function GoodBad({ title, items, tone }: { title: string; items: { title: string; text: string; date: string }[]; tone: Tone }) {
  const [all, setAll] = useState(false);
  const Icon = tone === "POSITIVE" ? CheckCircle2 : AlertTriangle;
  const color = tone === "POSITIVE" ? "text-pos" : "text-neg";
  return (
    <div>
      <h3 className={cn("eyebrow mb-2", color)}>{title}</h3>
      {items.length ? (
        <>
          <ul className="space-y-3">
            {(all ? items : items.slice(0, 4)).map((item, i) => (
              <li key={i} className="flex gap-2.5">
                <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", color)} />
                <span className="min-w-0 text-[13.5px] leading-relaxed text-ink-2">
                  <span className="font-semibold text-ink">{item.title}.</span> {item.text}
                  <span className="num ml-1.5 text-[11px] text-ink-3">{istDate(item.date)}</span>
                </span>
              </li>
            ))}
          </ul>
          {items.length > 4 && (
            <button type="button" onClick={() => setAll((v) => !v)} className="mt-2 text-xs font-medium text-accent hover:underline">
              {all ? "Show fewer" : `Show all ${items.length}`}
            </button>
          )}
        </>
      ) : <p className="text-sm text-ink-3">Nothing flagged in recent filings.</p>}
    </div>
  );
}

function PromiseTracker({ dossier }: { dossier: Dossier | null }) {
  const guidance = [...(dossier?.guidance ?? [])].reverse();
  const stats = promiseStats(guidance);
  const today = todayIST();
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-4">
        {[["Delivered", stats.delivered, "text-pos"], ["Missed or delayed", stats.missed, "text-neg"], ["Open", stats.open, "text-ink"],
          ["Delivery rate", stats.resolved ? `${Math.round((stats.delivered / stats.resolved) * 100)}%` : "—", "text-accent"]].map(([label, value, cls]) => (
          <div key={String(label)} className="bg-surface px-4 py-3">
            <div className="eyebrow text-ink-3">{label}</div>
            <div className={cn("num mt-1 text-[22px] font-semibold", String(cls))}>{value}</div>
          </div>
        ))}
      </div>
      <Panel title="Management commitments" hint="From AGMs, concalls, presentations and filings; status updated by later filings">
        {guidance.length ? (
          <div className="-mx-5 overflow-x-auto">
            <table className="w-full min-w-[760px] text-[13.5px]">
              <thead className="eyebrow border-b border-line text-left text-ink-3">
                <tr><th className="px-5 py-2 font-semibold">Commitment</th><th className="px-3 py-2 font-semibold">Given</th><th className="px-3 py-2 font-semibold">Due</th><th className="px-3 py-2 font-semibold">Status</th><th className="px-5 py-2 font-semibold">Evidence</th></tr>
              </thead>
              <tbody>
                {guidance.map((g) => {
                  const last = g.status_history[g.status_history.length - 1];
                  const overdue = !!g.due_date && g.due_date < today && ["OPEN", "ON_TRACK"].includes(g.status);
                  return (
                    <tr key={g.id} className="border-b border-line align-top last:border-0">
                      <td className="px-5 py-2.5 text-ink">{g.statement}{g.target ? <span className="text-ink-2"> · {g.target}</span> : null}
                        <div className="text-[11px] text-ink-3">{titleCase(g.source_type)}</div></td>
                      <td className="num whitespace-nowrap px-3 py-2.5 text-ink-2">{istDate(g.given_on)}</td>
                      <td className={cn("num whitespace-nowrap px-3 py-2.5", overdue ? "font-semibold text-neg" : "text-ink-2")}>{g.due ?? "—"}{overdue ? " · overdue" : ""}</td>
                      <td className="px-3 py-2.5"><Badge className={STATUS_CHIP[g.status] ?? STATUS_CHIP.OPEN}>{titleCase(g.status)}</Badge></td>
                      <td className="px-5 py-2.5 text-ink-2">{last ? <>{last.evidence} <span className="num text-[11px] text-ink-3">({istDate(last.as_of)})</span></> : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : <p className="text-sm text-ink-3">No commitments recorded yet. Concall transcripts, AGM speeches and investor presentations feed this tracker.</p>}
      </Panel>
      <Panel title="Follow-ups" hint="What earlier cards said to verify, and concerns analysts raised on calls">
        {dossier?.watchlist?.length ? (
          <ul className="divide-y divide-line">
            {dossier.watchlist.map((w) => (
              <li key={w.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2">
                <span className="text-[14px] text-ink">{WATCH_VERB[w.kind] ?? "Pending"}: {w.text}{w.target ? <span className="text-ink-2"> · target {w.target}</span> : null}
                  {w.response ? <span className="block text-[12.5px] text-ink-3">Management said: {w.response}</span> : null}</span>
                <span className="flex items-center gap-3">
                  <span className="num text-[12px] text-ink-3">{w.check_in ?? ""}</span>
                  <Badge className={STATUS_CHIP[w.status] ?? STATUS_CHIP.OPEN}>{titleCase(w.status)}</Badge>
                </span>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-ink-3">No follow-ups yet.</p>}
      </Panel>
    </div>
  );
}

function ResultsScorecard({ cards }: { cards: CardRow[] }) {
  const [, navigate] = useLocation();
  const quarters = cards.flatMap((row) => {
    const card = parseCard(row);
    return card?.results ? [{ row, card, r: card.results }] : [];
  });
  if (!quarters.length) return null;
  return (
    <Panel title="Quarterly scorecard" hint="Verdict and year-on-year change for each results filing">
      <ul className="-mx-5 divide-y divide-line border-t border-line">
        {quarters.map(({ row, card, r }) => {
          const t = (card.tone ?? "NEUTRAL") as Tone;
          const v = verdict(t, row.impact_level);
          return (
            <li key={row.news_id} className="relative grid gap-3 px-5 py-4 md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] md:items-center">
              <span aria-hidden className={cn("absolute inset-y-0 left-0 w-[3px]", TONE_STRIPE[v.tone])} />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-[20px] leading-none text-ink">{r.period}</span>
                  <Badge className={TONE_CHIP[v.tone]}>{v.label}</Badge>
                  <span className="num text-xs text-ink-3">{istDate(row.filed_at)}</span>
                </div>
                {card.takeaway ? <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-2">{card.takeaway}</p> : null}
                <button type="button" onClick={() => navigate(`/?card=${encodeURIComponent(row.news_id)}`)}
                  className="mt-1 text-xs font-medium text-accent hover:underline">Read the full card →</button>
              </div>
              <dl className="num grid grid-cols-4 gap-2">
                {[
                  ["Revenue", r.revenue ? cr(r.revenue.value) : "—", <Change value={r.revenue?.yoy_pct} />],
                  ["EBITDA", r.ebitda ? cr(r.ebitda.value) : "—", <Change value={r.ebitda?.yoy_pct} />],
                  ["OPM", r.ebitda_margin ? `${num(r.ebitda_margin.value)}%` : "—", <Change value={r.ebitda_margin?.yoy_bps} unit="bp" />],
                  ["PAT", r.pat ? cr(r.pat.value) : "—", <Change value={r.pat?.yoy_pct} />],
                ].map(([label, value, change]) => (
                  <div key={String(label)} className="rounded-lg bg-surface-2/70 px-2.5 py-2">
                    <dt className="eyebrow text-ink-3">{label}</dt>
                    <dd className="mt-0.5 text-[14px] font-semibold text-ink">{value}</dd>
                    <dd className="text-[12px]">{change} <span className="text-ink-3">YoY</span></dd>
                  </div>
                ))}
              </dl>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function MetricsPanel({ dossier }: { dossier: Dossier }) {
  type Cell = { value: number; unit: string; yoy?: number | null };
  type Group = { periods: string[]; metrics: Map<string, Map<string, Cell>> };
  const groups = useMemo(() => {
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
  const balance = dossier.balance_sheet[dossier.balance_sheet.length - 1];

  return (
    <div className="space-y-4">
      <Panel title="Financial baseline" hint="Every figure comes from a filing; restatements replace older numbers">
        {!active ? <p className="text-sm text-ink-3">No financial metrics extracted yet.</p> : (
          <>
            {groups.length > 1 && (
              <div className="mb-3 flex gap-1">
                {groups.map(([k]) => (
                  <button key={k} type="button" onClick={() => setKind(k)}
                    className={cn("rounded-lg px-2.5 py-1 text-xs font-medium", k === active[0] ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink")}>{k}</button>
                ))}
              </div>
            )}
            <div className="-mx-5 overflow-x-auto">
              <table className="w-full min-w-[560px] text-[13.5px]">
                <thead className="eyebrow border-b border-line text-ink-3">
                  <tr><th className="px-5 py-2 text-left font-semibold">Metric</th>{active[1].periods.slice(-6).map((p) => <th key={p} className="num px-3 py-2 text-right font-semibold">{p}</th>)}</tr>
                </thead>
                <tbody>
                  {[...active[1].metrics.entries()].map(([metric, values]) => (
                    <tr key={metric} className="border-b border-line last:border-0">
                      <td className="whitespace-nowrap px-5 py-2 font-medium text-ink">{titleCase(metric)}</td>
                      {active[1].periods.slice(-6).map((p) => {
                        const v = values.get(p);
                        return (
                          <td key={p} className="num whitespace-nowrap px-3 py-2 text-right text-ink">
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
      </Panel>
      {balance && (
        <Panel title="Balance sheet" hint={`as of ${istDate(String(balance.as_of))}`}>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
            {Object.entries(balance).filter(([k, v]) => v !== null && !["as_of", "source_news_id"].includes(k)).map(([k, v]) => (
              <div key={k}>
                <dt className="eyebrow text-ink-3">{titleCase(k.replace(/_cr$/, ""))}</dt>
                <dd className="num mt-0.5 text-[15px] font-semibold text-ink">{typeof v === "number" ? (k.endsWith("_cr") ? cr(v) : num(v)) : String(v)}</dd>
              </div>
            ))}
          </dl>
        </Panel>
      )}
    </div>
  );
}

function Timeline({ dossier }: { dossier: Dossier | null }) {
  const events = [...(dossier?.timeline ?? [])].reverse();
  if (!events.length) return <Empty title="No events recorded yet" />;
  return (
    <Panel title="2026 event timeline" hint={`${events.length} material filings`}>
      <ol className="relative ml-1.5 border-l border-line">
        {events.map((e) => (
          <li key={e.id} className="relative ml-5 pb-5 last:pb-0">
            <span className={cn("absolute -left-[26px] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-surface",
              e.impact_level === "HIGH" ? "bg-accent" : "bg-line-strong")} />
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="num text-ink-3">{istDate(e.date)}</span>
              <Badge className="bg-surface-2 text-ink-2">{EVENT_LABELS[e.event_type] ?? e.event_type}</Badge>
              {e.impact_level === "HIGH" && <Badge className="bg-surface-2 font-semibold text-ink">High impact</Badge>}
            </div>
            <p className="mt-1 text-[14px] leading-relaxed text-ink">{e.summary}</p>
          </li>
        ))}
      </ol>
    </Panel>
  );
}
