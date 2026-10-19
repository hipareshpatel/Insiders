import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CheckCircle2 } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useLocation, useParams } from "wouter";
import type { CardRow, Company, Dossier, Guidance, Peer, Technicals } from "../../shared/types";
import { Avatar } from "../components/Avatar";
import { PriceChart } from "../components/PriceChart";
import { AnnouncementCard, lineValue, PROVISIONAL_STAGES, resultLines, STAGE_LABEL } from "../components/AnnouncementCard";
import { parseCard, SIGNAL } from "../components/FilingCard";
import { Badge } from "../components/ui/badge";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { cr, istDate, listing, num, pct, rupees, signClass, titleCase, todayIST } from "../lib/format";
import { periodEnd, periodKind } from "../lib/periods";
import { EVENT_LABELS, SECTORS, TONE_CHIP, TONE_LABEL, TONE_STRIPE, verdict, type Tone } from "../lib/taxonomy";
import { ownerApi, useOwnerToken } from "../lib/owner";
import { HISTORY_START } from "../lib/config";
import { useQueryState } from "../lib/url";
import { Empty, Loading } from "./FeedView";
import { Change, turnOf } from "./ResultsView";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "results", label: "Results" },
  { key: "promises", label: "Promise tracker" },
  { key: "timeline", label: "Timeline" },
  { key: "filings", label: "Filings" },
  { key: "owners", label: "Ownership & governance" },
];

const WATCH_VERB: Record<string, string> = { KPI: "Verify", APPROVAL: "Pending", CONCERN: "Analyst concern" };

export const STATUS_CHIP: Record<string, string> = {
  DELIVERED: "bg-pos-soft text-pos", MET: "bg-pos-soft text-pos", ON_TRACK: "bg-info-soft text-info",
  OPEN: "bg-surface-2 text-ink-2", PENDING: "bg-surface-2 text-ink-2", PARTIAL: "bg-warn-soft text-warn",
  REVISED: "bg-warn-soft text-warn", DELAYED: "bg-warn-soft text-warn", MISSED: "bg-neg-soft text-neg", WITHDRAWN: "bg-neg-soft text-neg",
};

export function CompanyPage() {
  const { scrip } = useParams<{ scrip: string }>();
  const [params, setParams] = useQueryState();
  const [, navigate] = useLocation();
  const tab = params.get("tab") ?? "overview";
  const query = useQuery({ queryKey: ["company", scrip], queryFn: () => api.company(scrip!), enabled: !!scrip });

  if (query.isPending) return <Loading />;
  if (query.isError) return <div className="mx-auto max-w-[1200px] p-6"><Empty title="Couldn't load this company" body={String(query.error)} /></div>;
  const { company, cards, dossier } = query.data;
  if (!company && !dossier) return <div className="mx-auto max-w-[1200px] p-6"><Empty title={`No company ${scrip}`} /></div>;
  const name = company?.company_name ?? dossier?.company_name ?? scrip!;
  const symbol = company?.symbol ?? dossier?.symbol ?? null;

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6">
      <Link href="/companies" className="mb-4 inline-flex items-center gap-1 text-[13px] text-ink-3 hover:text-ink">
        <ArrowLeft className="h-3.5 w-3.5" /> Companies
      </Link>
      <header className="grid items-start gap-4 md:grid-cols-[minmax(0,1fr)_auto]">
        <div className="flex min-w-0 items-center gap-4">
          <Avatar name={name} symbol={symbol} size={64} className="shadow-lg" />
          <div className="min-w-0">
            <h1 className="font-display text-[24px] leading-tight text-ink sm:text-[28px]">{name}</h1>
            <p className="mt-0.5 text-[13.5px] font-semibold text-ink-3">
              <span className="num">{listing(symbol, scrip)}</span>
              {company?.sector ? ` · ${SECTORS[company.sector] ?? titleCase(company.sector)}` : ""}
              {company?.industry ? ` › ${company.industry.split(">").pop()?.trim()}` : ""}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {company?.size_category && <Badge className="bg-accent-soft text-accent">{titleCase(company.size_category)} cap</Badge>}
              {company?.credibility_score != null && (
                <Badge className={company.credibility_score >= 75 ? "bg-pos-soft text-pos" : company.credibility_score < 50 ? "bg-warn-soft text-warn" : "bg-surface-2 text-ink-2"}>
                  🎯 Credibility {Math.round(company.credibility_score)}%
                </Badge>
              )}
              {company?.median_turnover_cr != null && company.median_turnover_cr < 0.5 && <Badge className="bg-warn-soft text-warn">💧 Thin liquidity</Badge>}
              {technicalTags(company).map((t) => <Badge key={t} className="bg-surface-2 text-ink-2">{t}</Badge>)}
            </div>
          </div>
        </div>
        <div className="md:text-right">
          <div className="num text-[28px] font-bold tracking-tight text-ink sm:text-[32px]">{rupees(company?.last_price)}</div>
          <div className="num flex flex-wrap gap-x-3 text-[13px] font-semibold md:justify-end">
            {([["1W", company?.ret_1w], ["1M", company?.ret_1m], ["1Y", company?.ret_1y]] as const).map(([l, v]) => (
              <span key={l} className="text-ink-3">{l} <span className={signClass(v)}>{pct(v)}</span></span>
            ))}
          </div>
          {company?.price_date && <div className="text-[11.5px] text-ink-3">as of {istDate(company.price_date)}</div>}
          <div className="mt-2.5 flex flex-wrap gap-2 md:justify-end">
            {company && <WatchButton scrip={company.scrip_code} on={!!company.watchlist} />}
            <button type="button" onClick={() => setParams({ memory: scrip })} className="card-soft h-9 rounded-xl px-4 text-[13px] font-bold text-ink hover:text-accent">◎ Memory</button>
            {cards[0]?.pdf_url && <a href={cards[0].pdf_url} target="_blank" rel="noreferrer" className="card-soft inline-flex h-9 items-center rounded-xl px-4 text-[13px] font-bold text-ink hover:text-accent">Latest PDF</a>}
          </div>
        </div>
      </header>

      <KeyFigures company={company} dossier={dossier} cards={cards} />

      <div className="sticky top-14 z-10 -mx-4 mt-4 bg-bg px-4 py-2 sm:-mx-6 sm:px-6">
        <div role="tablist" className="card-soft no-scrollbar inline-flex max-w-full gap-0.5 overflow-x-auto rounded-2xl p-1">
          {TABS.map((t) => (
            <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setParams({ tab: t.key === "overview" ? null : t.key })}
              className={cn("whitespace-nowrap rounded-[10px] px-3.5 py-2 text-[13.5px] font-bold transition-colors", tab === t.key ? "grad-accent shadow-md" : "text-ink-2 hover:text-ink")}>
              {t.key === "filings" ? `Filings · ${cards.length}` : t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5">
        {tab === "overview" && (
          <div className="space-y-4">
            <PriceChart chart={query.data.chart} cards={cards} onOpen={(id) => navigate(`/feed?card=${encodeURIComponent(id)}`)} />
            <Overview dossier={dossier} cards={cards} onTab={(t) => setParams({ tab: t })} />
            <TradeRemediesPanel dossier={dossier} />
          </div>
        )}
        {tab === "results" && (
          <div className="space-y-4">
            {dossier && (
              <div className={cn("grid grid-cols-[minmax(0,1fr)] items-start gap-4", dossier.segment_mix?.length && "lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]")}>
                <QuarterBars dossier={dossier} />
                <SegmentMix dossier={dossier} />
              </div>
            )}
            <ResultsScorecard cards={cards} />
            {dossier ? <MetricsPanel dossier={dossier} /> : <Empty title="No results analysed yet" />}
          </div>
        )}
        {tab === "promises" && <PromiseTracker dossier={dossier} />}
        {tab === "timeline" && <Timeline dossier={dossier} />}
        {tab === "owners" && <OwnersTab dossier={dossier} peers={query.data.peers ?? []} company={company} />}
        {tab === "filings" && (
          <div className="mx-auto max-w-[720px] space-y-4">
            {cards.length ? cards.map((row) => <AnnouncementCard key={row.news_id} row={row} />) : <Empty title="No material filings analysed yet" />}
          </div>
        )}
      </div>
      <p className="mt-10 text-center text-[11px] text-ink-3">AI summaries of public NSE filings, refreshed with every new filing. Not investment advice.</p>
    </div>
  );
}

export function Panel({ title, children, hint, className }: { title: string; children: ReactNode; hint?: ReactNode; className?: string }) {
  return (
    <section className={cn("card-soft rise-in min-w-0", className)}>
      <header className="flex flex-wrap items-baseline justify-between gap-2 px-5 pt-4">
        <h2 className="text-[16px] font-extrabold leading-tight tracking-tight text-ink">{title}</h2>
        {hint ? <span className="text-xs text-ink-3">{hint}</span> : null}
      </header>
      <div className="px-5 pb-5 pt-3">{children}</div>
    </section>
  );
}

export function promiseStats(guidance: Guidance[]) {
  const delivered = guidance.filter((g) => g.status === "DELIVERED").length;
  const missed = guidance.filter((g) => ["MISSED", "DELAYED", "WITHDRAWN"].includes(g.status)).length;
  const open = guidance.filter((g) => ["OPEN", "ON_TRACK", "REVISED"].includes(g.status)).length;
  return { delivered, missed, open, resolved: delivered + missed };
}

function Overview({ dossier, cards, onTab }: { dossier: Dossier | null; cards: CardRow[]; onTab: (t: string) => void }) {
  const today = todayIST();
  const parsed = useMemo(() => cards.map((row) => ({ row, card: parseCard(row) })).filter((x) => x.card), [cards]);
  const latest = parsed[0];
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
      <div className="card-soft rise-in grid grid-cols-2 gap-2.5 p-3 lg:grid-cols-4">
          <Tile label="Promise record" value={stats.resolved ? `${stats.delivered} of ${stats.resolved} delivered` : "No promises resolved yet"}
            tone={stats.resolved ? (stats.missed ? "MIXED" : "POSITIVE") : "NEUTRAL"} action="View tracker" onAction={() => onTab("promises")} />
          <Tile label="Open commitments" value={`${stats.open} tracked`} tone="NEUTRAL" action="View tracker" onAction={() => onTab("promises")} />
          <Tile label="Latest filing" value={latest?.card?.tone ? TONE_LABEL[latest.card.tone as Tone] : "—"} tone={(latest?.card?.tone ?? "NEUTRAL") as Tone}
            sub={latest ? `${EVENT_LABELS[latest.row.event_category] ?? ""} · ${istDate(latest.row.filed_at)}` : undefined} action="View filings" onAction={() => onTab("filings")} />
          <Tile label="Next catalyst" value={next ? titleCase(next.event_type) : "None scheduled"} tone="NEUTRAL"
            sub={next ? istDate(next.date) : undefined} />
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
      <div className="min-w-0 space-y-4">

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

      <Panel title="How the story is unfolding" hint={dossier?.timeline.length ? `${dossier.timeline.length} events since ${istDate(HISTORY_START)}` : undefined}>
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

      <Panel title="The good & the bad" hint="Computed signals and notable changes from recent filings">
        <div className="grid gap-6 md:grid-cols-2">
          <GoodBad title="The good" items={good} tone="POSITIVE" />
          <GoodBad title="The bad" items={bad} tone="NEGATIVE" />
        </div>
      </Panel>

      <Panel title="What to track" hint={tracking.length > TRACK_SHOWN ? `${tracking.length} items` : undefined}>
        {tracking.length ? <TrackList items={tracking} /> : <p className="text-sm text-ink-3">Nothing to track yet.</p>}
      </Panel>
      </div>
      <div className="min-w-0 space-y-4">
        <PromiseSummary dossier={dossier} />
        <DealsAndNotes dossier={dossier} stacked />
        <ComingUp dossier={dossier} />
      </div>
      </div>
    </div>
  );
}

// The first few, then a button: Heritage's list made the phone Overview 10,040 px long (laptop T11, 2026-10-20)
const TRACK_SHOWN = 8;

function TrackList({ items }: { items: { when: string; text: string }[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, TRACK_SHOWN);
  return (
    <>
      <ul className="divide-y divide-line">
        {shown.map((t, i) => (
          <li key={i} className="grid gap-x-4 gap-y-0.5 py-2 sm:grid-cols-[140px_minmax(0,1fr)]">
            <span className="num text-[13px] text-ink-3">{t.when}</span>
            <span className="text-[14px] text-ink">{t.text}</span>
          </li>
        ))}
      </ul>
      {items.length > TRACK_SHOWN && (
        <button type="button" onClick={() => setAll(!all)} className="mt-2 text-[13px] font-semibold text-accent hover:underline">
          {all ? "Show fewer" : `Show all ${items.length}`}
        </button>
      )}
    </>
  );
}

/** ★ the company (owner only): starred companies stay in the universe whatever their size. */
function WatchButton({ scrip, on }: { scrip: string; on: boolean }) {
  const token = useOwnerToken();
  const client = useQueryClient();
  const [value, setValue] = useState(on);
  if (!token) return value ? <Badge className="bg-accent-soft text-accent">★ Watchlist</Badge> : null;
  return (
    <button type="button" aria-pressed={value} onClick={async () => {
      setValue(!value);
      await ownerApi.watch(token, scrip, !value).catch(() => setValue(value));
      void client.invalidateQueries({ queryKey: ["company", scrip] });
    }} className={cn("h-7 rounded-full border px-3 text-[12px] font-semibold", value ? "border-accent bg-accent-soft text-accent" : "border-line text-ink-2 hover:text-ink")}>
      {value ? "★ On watchlist" : "☆ Watch"}
    </button>
  );
}

/** Who the company is (former names, subsidiaries, brands), who owns it, what the auditor said, and
 * the numeric targets the platform is checking against results (blueprint compartments 1, 9, 10). */
const GROUP_TYPE = /subsidiar|step[- ]?down|\bwos\b|wholly|target\s+compan|acqui|investee|\bjv\b|joint\s+venture|associate|holding|parent|promoter|group\s+compan|sister|affiliate|\bllp\b|partnership|\bspv\b|trust|plant|factory|unit\b|facility|division|brand|branch|office|warehouse|mine|refinery|hospital|hotel|store/i;

export function IdentityAndOwnership({ dossier }: { dossier: Dossier | null }) {
  const identity = dossier?.identity;
  const owners = dossier?.ownership ?? [];
  const auditor = dossier?.governance?.auditor;
  // one open target per metric and period, the latest (memory stored before 2026-10-20 can hold several)
  const predictions = [...(dossier?.predictions ?? [])].reverse()
    .filter((p, i, all) => p.status !== "OPEN" || all.findIndex((q) => q.status === "OPEN" && q.metric === p.metric && q.period === p.period) === i)
    .slice(0, 8);
  // the group, plants and brands only: memory written before the pipeline checked the type holds a case's other
  // parties too (Meta, Google, a ministry; laptop test, 2026-10-19). The same rule as dossier.group_entity.
  const entities = (identity?.entities ?? []).filter((e) => e.type && GROUP_TYPE.test(e.type));
  if (!identity?.former_names?.length && !entities.length && !owners.length && !auditor && !predictions.length) return null;
  const last = owners[owners.length - 1];
  const prev = owners[owners.length - 2];
  const delta = (k: "promoter_pct" | "fii_pct" | "dii_pct" | "pledge_pct") =>
    last?.[k] != null && prev?.[k] != null ? ` (${(last[k]! - prev[k]!) >= 0 ? "+" : ""}${(last[k]! - prev[k]!).toFixed(1)} pp)` : "";
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Panel title="Identity & governance" hint="Former names, group entities, auditor">
        <dl className="space-y-2 text-[13.5px]">
          {identity?.former_names?.length ? <div><dt className="eyebrow text-ink-3">Formerly</dt><dd className="text-ink">{identity.former_names.join(" · ")}</dd></div> : null}
          {entities.length ? (
            <div><dt className="eyebrow text-ink-3">Group entities, plants & brands</dt>
              <dd className="text-ink">{entities.map((e) => `${e.name} (${e.type})`).join(" · ")}</dd></div>
          ) : null}
          {auditor ? (
            <div><dt className="eyebrow text-ink-3">Auditor</dt>
              <dd className={cn(["QUALIFIED", "ADVERSE", "DISCLAIMER"].includes(auditor.opinion ?? "") ? "text-neg" : "text-ink")}>
                {[auditor.name, auditor.opinion && titleCase(auditor.opinion), auditor.change].filter(Boolean).join(" · ")}
                {auditor.note ? <span className="block text-[12px] text-ink-3">{auditor.note}</span> : null}
              </dd></div>
          ) : null}
          {last ? (
            <div><dt className="eyebrow text-ink-3">Shareholding · {last.period}</dt>
              <dd className="num text-ink">
                {last.promoter_pct != null && <span className="mr-3">Promoter {last.promoter_pct}%{delta("promoter_pct")}</span>}
                {last.fii_pct != null && <span className="mr-3">FII {last.fii_pct}%{delta("fii_pct")}</span>}
                {last.dii_pct != null && <span className="mr-3">DII {last.dii_pct}%{delta("dii_pct")}</span>}
                {last.pledge_pct != null && <span className={cn((last.pledge_pct ?? 0) > 0 && "text-warn")}>Pledged {last.pledge_pct}%{delta("pledge_pct")}</span>}
              </dd></div>
          ) : null}
        </dl>
      </Panel>
      {predictions.length > 0 && (
        <Panel title="Targets being checked" hint="Numeric guidance, checked automatically against results">
          <ul className="divide-y divide-line">
            {predictions.map((p) => (
              <li key={p.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3 py-2 text-[13.5px]">
                <span className="text-ink">{p.kpi}
                  <span className="num block text-[12px] text-ink-3">{p.period} · target {p.comparison} {p.value}{p.actual != null ? ` · actual ${p.actual}` : ""}</span>
                </span>
                <Badge className={p.status === "MET" ? "bg-pos-soft text-pos" : p.status === "MISSED" ? "bg-neg-soft text-neg" : "bg-surface-2 text-ink-2"}>
                  {p.status === "OPEN" ? "Open" : p.status === "MET" ? "Met" : p.status === "NOT_REPORTED" ? "Not reported" : "Missed"}
                </Badge>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

/** Each order, deal or capex plan once, at its latest stage; plus operating facts worth remembering. */
export function DealsAndNotes({ dossier, stacked = false }: { dossier: Dossier | null; stacked?: boolean }) {
  const deals = [...(dossier?.deals ?? [])].reverse().slice(0, 10);
  const notes = [...(dossier?.operating_notes ?? [])].reverse().slice(0, 6);
  if (!deals.length && !notes.length) return null;
  return (
    <div className={cn("grid gap-4", !stacked && deals.length && notes.length && "md:grid-cols-2")}>
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
    <div className="flex flex-col rounded-2xl bg-surface-2 px-4 py-3">
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
                      {/* past its deadline a promise is not "on track": delivered, missed, or not reported yet */}
                      <td className="px-3 py-2.5"><Badge className={overdue ? "bg-warn-soft text-warn" : STATUS_CHIP[g.status] ?? STATUS_CHIP.OPEN}>{overdue ? "Not reported" : titleCase(g.status)}</Badge></td>
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
                <button type="button" onClick={() => navigate(`/feed?card=${encodeURIComponent(row.news_id)}`)}
                  className="mt-1 text-xs font-medium text-accent hover:underline">Read the full card →</button>
              </div>
              <dl className="num grid grid-cols-4 gap-2">
                {/* the statement's own first lines: revenue, EBITDA, margin, PAT for a company; a bank's NII, NPA... */}
                {resultLines(r).filter((l) => !["exceptional_items", "pbt", "eps", "interest_earned"].includes(l.key)).slice(0, 4)
                  .map(({ label, unit, line }) => [label, unit === "cr" ? cr(line.value) : lineValue(line.value, unit),
                    unit === "pct" ? <Change value={line.yoy_bps} unit="bp" /> : <Change value={line.yoy_pct} turn={turnOf(line)} />] as const)
                  .map(([label, value, change]) => (
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

export function MetricsPanel({ dossier }: { dossier: Dossier }) {
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
    <Panel title={`Event timeline since ${istDate(HISTORY_START)}`} hint={`${events.length} material filings`}>
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

/** Price-structure tags from the market-data job, as the cards show them. */
function technicalTags(company: Company | null): string[] {
  let t: Technicals | null = null;
  try { t = company?.technicals_json ? JSON.parse(company.technicals_json) : null; } catch { t = null; }
  if (!t) return [];
  return [t.stage2 ? "📈 Stage 2 trend" : "", t.vcp ? "⚡ Coiled spring" : "", t.rs_pct != null && t.rs_pct >= 80 ? `RS ${t.rs_pct}` : ""].filter(Boolean);
}

/** The company in eight figures under its name: size, balance sheet, liquidity, owners and how much we know. */
function KeyFigures({ company, dossier, cards }: { company: Company | null; dossier: Dossier | null; cards: CardRow[] }) {
  const fundamentals = cards.map(parseCard).find((c) => c?.fundamentals)?.fundamentals ?? {};
  const own = dossier?.ownership?.[dossier.ownership.length - 1];
  const high = cards.filter((c) => c.impact_level === "HIGH").length;
  const items: [string, string, string?][] = [
    ["Market cap", cr(company?.market_cap_cr)],
    [`Revenue${fundamentals.revenue?.period ? ` · ${fundamentals.revenue.period}` : ""}`, cr(fundamentals.revenue?.value)],
    ["Debt", cr(fundamentals.debt?.value)],
    ["Net worth", cr(fundamentals.net_worth?.value)],
    ["Avg traded a day", company?.median_turnover_cr != null ? `₹${company.median_turnover_cr.toFixed(company.median_turnover_cr < 10 ? 2 : 0)} Cr` : "—"],
    ["Promoter", own?.promoter_pct != null ? `${own.promoter_pct}%` : "—", own?.pledge_pct != null ? `pledge ${own.pledge_pct}%` : undefined],
    ["1-year return", pct(company?.ret_1y)],
    ["Filings analysed", num(cards.length), high ? `${high} high` : undefined],
  ];
  return (
    <dl className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-4 lg:grid-cols-8">
      {items.map(([label, value, sub]) => (
        <div key={label} className="card-soft rise-in rounded-2xl px-3.5 py-2.5">
          <dt className="text-[11.5px] font-bold leading-tight text-ink-3">{label}</dt>
          <dd className="num text-[15px] font-bold text-ink">{value}{sub && <span className="block text-[11px] font-medium text-ink-3">{sub}</span>}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Revenue, profit or margin for the last eight quarters in memory, as bars (the latest in the accent). */
function QuarterBars({ dossier }: { dossier: Dossier }) {
  const [metric, setMetric] = useState<"revenue" | "pat" | "ebitda_margin">("revenue");
  const series = useMemo(() => {
    const rows = dossier.financial_metrics.filter((m) => periodKind(m.period) === "Quarter" && (m.metric === metric || (metric === "pat" && m.metric === "pat_owners")));
    const by = new Map<string, number>();
    for (const m of rows) if (!(metric === "pat" && m.metric === "pat" && by.has(m.period))) by.set(m.period, m.value);
    return [...by.entries()].sort((a, b) => periodEnd(a[0]).localeCompare(periodEnd(b[0]))).slice(-8);
  }, [dossier.financial_metrics, metric]);
  if (series.length < 2 && metric === "revenue") return null;
  const values = series.map(([, v]) => v);
  const lo = metric === "ebitda_margin" ? Math.min(...values) - 2 : Math.min(0, ...values);
  const hi = Math.max(...values) * 1.08 || 1;
  const label = (v: number) => metric === "ebitda_margin" ? `${v.toFixed(1)}%` : Math.abs(v) >= 10000 ? `${(v / 1000).toFixed(1)}k` : Math.round(v).toLocaleString("en-IN");
  return (
    <Panel title="Quarterly results" hint={
      <span className="inline-flex rounded-[11px] bg-surface-2 p-[3px]">
        {([["revenue", "Revenue"], ["pat", "Profit"], ["ebitda_margin", "Margin"]] as const).map(([k, l]) => (
          <button key={k} type="button" onClick={() => setMetric(k)}
            className={cn("rounded-lg px-2.5 py-1 text-[12px] font-bold", metric === k ? "bg-surface text-ink shadow-sm" : "text-ink-3")}>{l}</button>
        ))}
      </span>}>
      {series.length < 2 ? <p className="text-sm text-ink-3">Not enough quarters in memory for this figure yet.</p> : (
        <div className="flex h-[210px] items-end gap-1.5 sm:gap-4" role="img" aria-label={`${metric} by quarter`}>
          {series.map(([period, v], i) => {
            const last = i === series.length - 1;
            return (
              <div key={period} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1.5">
                <span className="num w-full truncate text-center text-[10.5px] font-bold text-ink sm:text-[11.5px]">{label(v)}</span>
                <span className={cn("w-full max-w-[96px] rounded-[10px]", last ? "grad-accent" : "border border-line-strong bg-surface-2")}
                  style={{ height: `${Math.max(2, ((v - lo) / (hi - lo)) * 150)}px` }} />
                {/* "Q3" over "FY27": eight quarters fit a phone without cutting the labels */}
                <span className="num w-full text-center text-[10px] leading-tight text-ink-3 sm:text-[11px]">
                  {period.replace(/^(Q[1-4])(FY\d{2})$/, "$1\u200b$2").split("\u200b").map((part, k) => <span key={k} className="block">{part}</span>)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

const MIX_COLORS = ["var(--accent)", "var(--accent-2)", "var(--teal)", "var(--impact-moderate)", "var(--violet)", "var(--neutral-stripe)"];

/** Revenue by segment for the latest period memory has, as a ring. */
function SegmentMix({ dossier }: { dossier: Dossier }) {
  const rows = dossier.segment_mix ?? [];
  if (!rows.length) return null;
  const latest = [...rows].sort((a, b) => periodEnd(b.period).localeCompare(periodEnd(a.period)))[0].period;
  const now = rows.filter((r) => r.period === latest);
  const total = now.reduce((a, r) => a + (r.revenue_cr ?? 0), 0);
  const parts = now.map((r) => ({ name: r.segment, share: r.share_pct ?? (total ? ((r.revenue_cr ?? 0) / total) * 100 : 0), cr: r.revenue_cr }))
    .filter((r) => r.share > 0).sort((a, b) => b.share - a.share).slice(0, 6);
  if (!parts.length) return null;
  const R = 50, len = 2 * Math.PI * R, sum = parts.reduce((a, p) => a + p.share, 0);
  // Filings often give nested or alternative cuts (Dairy holds Milk; VAP with and without ghee): they add up past
  // 100% and cannot be drawn as parts of one whole, so each is shown as its own share of revenue.
  // ...and when only amounts are given, cuts that add up past the quarter's revenue overlap in the same way
  const quarterRevenue = dossier.financial_metrics.find((m) => m.period === latest && m.metric === "revenue")?.value;
  if (sum > 105 || (quarterRevenue && total > quarterRevenue * 1.05)) {
    return (
      <Panel title="Business mix" hint={`${latest} · each segment's share of revenue; the cuts overlap`}>
        <ul className="space-y-2.5 text-[13.5px]">
          {parts.map((p, i) => (
            <li key={p.name} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_40px] items-center gap-2.5">
              <span className="truncate">{p.name}</span>
              <span className="h-2 overflow-hidden rounded bg-surface-2"><i className="block h-full rounded" style={{ width: `${Math.min(100, p.share)}%`, background: MIX_COLORS[i] }} /></span>
              <span className="num text-right text-ink-2">{p.share.toFixed(0)}%</span>
            </li>
          ))}
        </ul>
      </Panel>
    );
  }
  let off = 0;
  return (
    <Panel title="Business mix" hint={`${latest} revenue`}>
      <div className="grid items-center gap-4 sm:grid-cols-[130px_minmax(0,1fr)]">
        <svg viewBox="0 0 130 130" className="mx-auto h-[130px] w-[130px]" role="img" aria-label="Revenue by segment">
          {parts.map((p, i) => {
            const seg = (p.share / sum) * len;
            const el = <circle key={p.name} cx="65" cy="65" r={R} fill="none" stroke={MIX_COLORS[i]} strokeWidth="18" strokeDasharray={`${Math.max(0, seg - 2)} ${len}`} strokeDashoffset={-off} transform="rotate(-90 65 65)" />;
            off += seg;
            return el;
          })}
          {total > 0 && <text x="65" y="69" textAnchor="middle" fill="var(--ink)" style={{ font: "800 13px var(--font-sans)" }}>{cr(total)}</text>}
        </svg>
        <ul className="space-y-2 text-[13.5px]">
          {parts.map((p, i) => (
            <li key={p.name} className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
              <span className="truncate"><i className="mr-2 inline-block h-2.5 w-2.5 rounded-[3px]" style={{ background: MIX_COLORS[i] }} />{p.name}</span>
              <span className="num text-ink-2">{p.share.toFixed(0)}%</span>
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  );
}

/** The promise record in one number, with the latest few commitments and how they ended. */
function PromiseSummary({ dossier }: { dossier: Dossier | null }) {
  const guidance = dossier?.guidance ?? [];
  const s = promiseStats(guidance);
  if (!guidance.length) return null;
  const rate = s.resolved ? Math.round((s.delivered / s.resolved) * 100) : null;
  return (
    <Panel title="Promises kept">
      <div className="flex items-center gap-3.5">
        <span className={cn("text-[34px] font-extrabold tracking-tight", rate == null ? "text-ink-3" : rate >= 75 ? "text-pos" : rate < 50 ? "text-warn" : "text-ink")}>{rate == null ? "—" : `${rate}%`}</span>
        <span className="text-[13px] text-ink-2">{s.resolved ? `${s.delivered} of ${s.resolved} resolved commitments delivered` : "No commitment resolved yet"}, {s.open} open, checked against later filings.</span>
      </div>
      <ul className="mt-2 space-y-2">
        {[...guidance].reverse().slice(0, 4).map((g) => (
          <li key={g.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-2 text-[13.5px]">
            <span className="text-ink">{g.statement}</span>
            <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-bold", STATUS_CHIP[g.status] ?? "bg-surface-2 text-ink-2")}>{titleCase(g.status)}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function ComingUp({ dossier }: { dossier: Dossier | null }) {
  const today = todayIST();
  const upcoming = (dossier?.upcoming_events ?? []).filter((e) => e.date >= today);
  // a generic entry beside a named event of the same day is the same event filed again
  const named = new Set(upcoming.filter((e) => !["OTHER", "MILESTONE"].includes(e.event_type)).map((e) => e.date));
  const events = upcoming.filter((e, i) => !(["OTHER", "MILESTONE"].includes(e.event_type) && named.has(e.date))
      && upcoming.findIndex((x) => x.date === e.date && x.event_type === e.event_type) === i)
    .sort((a, b) => a.date.localeCompare(b.date)).slice(0, 5);
  if (!events.length) return null;
  return (
    <Panel title="Coming up">
      <ul className="space-y-2.5">
        {events.map((e, i) => {
          const [day, mon] = istDate(e.date).split(" ");
          return (
            <li key={i} className="grid grid-cols-[52px_minmax(0,1fr)] items-center gap-2.5 text-[13.5px]">
              <span className="num rounded-xl bg-accent-soft py-1.5 text-center text-[12px] font-extrabold leading-tight text-accent">{day}<span className="block text-[10px] font-bold uppercase">{mon}</span></span>
              <span className="text-ink">{titleCase(e.event_type)}{e.description ? <span className="block text-[12px] text-ink-3">{e.description}</span> : null}</span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

const OWN = [["promoter_pct", "Promoter", "var(--accent)"], ["fii_pct", "FII", "var(--accent-2)"], ["dii_pct", "DII", "var(--teal)"]] as const;

/** Ownership by quarter, identity, the quarterly governance report, and the peers. */
function OwnersTab({ dossier, peers, company }: { dossier: Dossier | null; peers: Peer[]; company: Company | null }) {
  const own = [...(dossier?.ownership ?? [])].slice(-6).reverse();
  const quarters = (dossier?.governance?.quarters ?? []) as Record<string, unknown>[];
  const gov = quarters[quarters.length - 1];
  const exceptions = (gov?.exceptions as string[] | undefined) ?? [];
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
      <div className="min-w-0 space-y-4">
        {!own.length && (gov || peers.length > 0) && <Empty title="No shareholding data yet" body="It fills in from the quarterly shareholding filings on NSE." />}
        {own.length > 0 && (
          <Panel title="Ownership" hint="% of shares, from the quarterly shareholding XBRL">
            <ul className="space-y-2">
              {own.map((o) => {
                const pub = Math.max(0, 100 - (o.promoter_pct ?? 0) - (o.fii_pct ?? 0) - (o.dii_pct ?? 0));
                return (
                  <li key={o.period} className="grid grid-cols-[64px_minmax(0,1fr)] items-center gap-2.5">
                    <span className="num text-[12px] text-ink-3">{o.period}</span>
                    <span className="flex h-[26px] overflow-hidden rounded-[9px]">
                      {OWN.map(([k, l, c]) => o[k] != null && o[k]! > 0 ? (
                        <i key={k} title={`${l} ${o[k]}%`} className="num grid place-items-center text-[10.5px] font-bold not-italic text-white" style={{ width: `${o[k]}%`, background: c }}>{o[k]! >= 6 ? o[k]!.toFixed(1) : ""}</i>
                      ) : null)}
                      <i title={`Public ${pub.toFixed(1)}%`} className="num grid place-items-center bg-neutral-stripe text-[10.5px] font-bold not-italic text-ink" style={{ width: `${pub}%` }}>{pub >= 6 ? pub.toFixed(1) : ""}</i>
                    </span>
                  </li>
                );
              })}
            </ul>
            <p className="mt-3 flex flex-wrap gap-3 text-[12px] font-semibold text-ink-3">
              {[...OWN, ["", "Public", "var(--neutral-stripe)"] as const].map(([, l, c]) => <span key={l}><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full" style={{ background: c }} />{l}</span>)}
              {own[0]?.pledge_pct != null && <span className={cn("ml-auto", own[0].pledge_pct > 0 ? "text-warn" : "text-pos")}>Promoter pledge {own[0].pledge_pct}%</span>}
            </p>
          </Panel>
        )}
        <PledgesPanel dossier={dossier} />
        <IdentityAndOwnership dossier={dossier} />
      </div>
      <div className="min-w-0 space-y-4">
        {gov && (
          <Panel title="Governance" hint={`quarter ended ${String(gov.quarter_end ?? "")}, NSE filing`}>
            <ul className="space-y-2.5 text-[13.5px]">
              <GovLine ok={exceptions.length === 0} text={exceptions.length === 0 ? "Nothing to flag this quarter: board, committees, penalties and related-party money within the rules" : `${exceptions.length} point${exceptions.length > 1 ? "s" : ""} to note`} />
              {gov.board_size != null && <GovLine ok text={`Board: ${gov.board_size} directors, ${gov.independent_directors ?? "?"} independent`} />}
              {exceptions.map((e) => <GovLine key={e} ok={false} text={e} />)}
            </ul>
          </Panel>
        )}
        {peers.length > 0 && (
          <Panel title="Peers" hint={company?.sector ? `${SECTORS[company.sector] ?? titleCase(company.sector)}, nearest in size` : undefined}>
            <div className="-mx-2 overflow-x-auto">
              <table className="w-full border-separate border-spacing-y-1.5 text-[13px]">
                <thead className="eyebrow text-ink-3"><tr><th className="px-2 text-left">Company</th><th className="px-2 text-right">Mcap</th><th className="px-2 text-right">1M</th><th className="px-2 text-right">1Y</th></tr></thead>
                <tbody>
                  {company && (
                    <tr className="bg-accent-soft">
                      <td className="rounded-l-xl px-2 py-2 font-extrabold text-ink">{company.symbol ?? company.company_name}</td>
                      <td className="num px-2 text-right">{cr(company.market_cap_cr)}</td>
                      <td className={cn("num px-2 text-right", signClass(company.ret_1m))}>{pct(company.ret_1m)}</td>
                      <td className={cn("num rounded-r-xl px-2 text-right", signClass(company.ret_1y))}>{pct(company.ret_1y)}</td>
                    </tr>
                  )}
                  {peers.map((pr) => (
                    <tr key={pr.scrip_code} className="bg-surface-2">
                      <td className="rounded-l-xl px-2 py-2"><Link href={`/company/${pr.scrip_code}`} className="font-bold text-ink hover:text-accent">{pr.symbol ?? pr.company_name}</Link></td>
                      <td className="num px-2 text-right">{cr(pr.market_cap_cr)}</td>
                      <td className={cn("num px-2 text-right", signClass(pr.ret_1m))}>{pct(pr.ret_1m)}</td>
                      <td className={cn("num rounded-r-xl px-2 text-right", signClass(pr.ret_1y))}>{pct(pr.ret_1y)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}
        {!gov && !peers.length && !own.length && !dossier?.pledges?.events?.length && <Empty title="No ownership or governance data yet" body="It fills in from the quarterly shareholding and governance filings on NSE." />}
      </div>
    </div>
  );
}

const PLEDGE_EVENT: Record<string, { word: string; cls: string }> = {
  CREATED: { word: "Created", cls: "bg-warn-soft text-warn" },
  RELEASED: { word: "Released", cls: "bg-pos-soft text-pos" },
  INVOKED: { word: "Invoked", cls: "bg-neg-soft text-neg" },
};

/** Module 42: promoter encumbrance events from NSE's SAST Reg 31 disclosures, newest first (pipeline pledges.py). */
function PledgesPanel({ dossier }: { dossier: Dossier | null }) {
  const box = dossier?.pledges;
  const events = [...(box?.events ?? [])].reverse().slice(0, 8);
  if (!events.length) return null;
  const total = box?.summary?.encumbered_pct;
  return (
    <Panel title="Promoter pledges" hint="SAST Reg 31 disclosures on NSE · % of the company's shares">
      <p className="mb-3 text-[13.5px] text-ink-2">
        {total == null
          ? "The filings give group figures on single promoters' rows, so no total is added up here."
          : <>Encumbered now, as disclosed: <span className={cn("num font-extrabold", total > 0 ? "text-warn" : "text-pos")}>{total.toFixed(2)}%</span> of the company across {box?.summary?.promoters} promoter{box?.summary?.promoters === 1 ? "" : "s"}.</>}
      </p>
      <ul className="space-y-2">
        {events.map((e, i) => {
          const kind = PLEDGE_EVENT[e.event] ?? { word: titleCase(e.event), cls: "bg-surface-2 text-ink-2" };
          return (
            <li key={e.seq_id ?? i} className="grid grid-cols-[76px_minmax(0,1fr)_auto] items-baseline gap-2.5 text-[13px]">
              <span className="num text-[12px] text-ink-3">{e.event_on ? istDate(e.event_on) : istDate(e.as_of)}</span>
              <span className="min-w-0">
                <span className={cn("mr-1.5 rounded-full px-2 py-0.5 text-[11px] font-bold", kind.cls)}>{kind.word}</span>
                <span className="text-ink">{e.promoter ?? "Promoter"}</span>
                <span className="line-clamp-2 block break-words text-[12px] text-ink-3" title={e.lender ?? undefined}>
                  {e.type && e.type !== "Pledge" ? `${e.type} · ` : ""}{e.lender ?? ""}
                  {e.attachment && <> · <a href={e.attachment} target="_blank" rel="noreferrer" className="text-accent hover:underline">filing</a></>}
                </span>
              </span>
              <span className="num text-right font-semibold text-ink">{e.pct != null ? `${e.pct.toFixed(2)}%` : "—"}</span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

const REMEDY_STAGE: Record<string, { word: string; cls: string }> = {
  INITIATION: { word: "Started", cls: "bg-surface-2 text-ink-2" },
  PRELIMINARY_FINDING: { word: "Preliminary finding", cls: "bg-warn-soft text-warn" },
  FINAL_FINDING: { word: "Final finding", cls: "bg-pos-soft text-pos" },
  CUSTOMS_NOTIFICATION: { word: "Duty notified", cls: "bg-pos-soft text-pos" },
  TERMINATED: { word: "Terminated", cls: "bg-neg-soft text-neg" },
};

/** Module 8: DGTR anti-dumping, countervailing and safeguard cases the company asked for or supported, latest step
 *  first (pipeline dgtr.py; linked only when the initiation notice names the company). */
function TradeRemediesPanel({ dossier }: { dossier: Dossier | null }) {
  const cases = [...(dossier?.trade_remedies ?? [])].sort((a, b) => (b.stage_on ?? "").localeCompare(a.stage_on ?? "")).slice(0, 6);
  if (!cases.length) return null;
  return (
    <Panel title="Trade remedies" hint="DGTR cases the company applied for or supported · from the case pages">
      <ul className="divide-y divide-line">
        {cases.map((c) => {
          const stage = REMEDY_STAGE[c.stage ?? ""] ?? { word: titleCase(c.stage ?? "Listed"), cls: "bg-surface-2 text-ink-2" };
          return (
            <li key={c.case_url} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3 py-2 text-[13.5px]">
              <span className="min-w-0 text-ink">
                <a href={c.case_url} target="_blank" rel="noreferrer" className="font-semibold hover:underline">{c.product ?? "Case"}</a>
                {c.countries ? <span className="text-ink-2"> · {c.countries}</span> : null}
                <span className="block break-words text-[12px] text-ink-3">
                  {[c.investigation, c.proceeding].filter(Boolean).join(" · ")}
                  {" · "}{c.role === "APPLICANT" ? "the company applied" : "the company supported it"}
                  {c.stage_on ? ` · ${istDate(c.stage_on)}` : ""}
                </span>
              </span>
              <Badge className={stage.cls}>{stage.word}</Badge>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function GovLine({ ok, text }: { ok: boolean; text: string }) {
  return (
    <li className="grid grid-cols-[26px_minmax(0,1fr)] items-start gap-2.5">
      <span className={cn("grid h-[26px] w-[26px] place-items-center rounded-[9px] text-[13px] font-extrabold", ok ? "bg-pos-soft text-pos" : "bg-warn-soft text-warn")}>{ok ? "✓" : "!"}</span>
      <span className="pt-0.5 text-ink">{text}</span>
    </li>
  );
}
