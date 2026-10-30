import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import { Link, useParams } from "wouter";
import type { CallQuarter, CardRow, Company, Dossier, Guidance, Peer, PriceReaction, Technicals } from "../../shared/types";
import { EarningsCalls } from "../components/company/EarningsCalls";
import { Institutions } from "../components/company/Institutions";
import { Avatar } from "../components/Avatar";
import { PriceChart } from "../components/PriceChart";
import { formerOwnName, PROVISIONAL_STAGES, resultLines, STAGE_LABEL } from "../components/AnnouncementCard";
import { parseCard } from "../components/FilingCard";
import { CardList, RailTime, railDate } from "../components/company/CardList";
import { chartTags, dayChange, allZero, inStatementOrder, latestBalance, metricLabel, nextResults, overdue, peTtm, quarterly, quarterLabel, short, statementPlace, unitValue, yearRange } from "../components/company/companyText";
import { dayMonth, GoodAndBad, StorySoFar, WhatToTrack, type Parsed } from "../components/company/OverviewPanels";
import { CapitalAndCalibration, parseRoiic } from "../components/company/Execution";
import { Financials } from "../components/company/Financials";
import { Panel } from "../components/company/Panel";
import { IMPACT_DOT } from "../components/PriceChart";
import { Badge } from "../components/ui/badge";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { cr, istDate, listing, num, pct, signClass, titleCase, todayIST, companyPath } from "../lib/format";
import { periodEnd, periodKind } from "../lib/periods";
import { EVENT_LABELS, SECTORS, TONE_CHIP, TONE_LABEL, verdict, type Tone } from "../lib/taxonomy";
import { ownerApi, useOwnerToken } from "../lib/owner";
import { HISTORY_START } from "../lib/config";
import { useQueryState } from "../lib/url";
import { Empty, Loading } from "./FeedView";
import { Change, turnOf } from "./ResultsView";

export { Panel };

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

/** A share price in rupees with its paise ("₹405.40"). */
const price2 = (v: number) => `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
/** Crore in a tile: "₹3.78 L Cr" fits where "₹3.78 lakh Cr" wraps. */
const crShort = (v: number | null | undefined) => cr(v).replace(" lakh Cr", " L Cr");
const TAG_CLS = { pos: "bg-pos-soft text-pos", neg: "bg-neg-soft text-neg", neutral: "bg-surface-2 text-ink-2" } as const;
const btn = "card-soft inline-flex h-[38px] items-center rounded-xl px-4 text-[13.5px] font-extrabold text-ink hover:text-accent";

export function CompanyPage() {
  // the address carries the NSE symbol (or, for older links and companies without one, the key)
  const { scrip: key } = useParams<{ scrip: string }>();
  const [params, setParams] = useQueryState();
  const tab = params.get("tab") ?? "overview";
  // a chart dot or a scorecard tile asks for a card: its list pages to it, opens it and scrolls to it
  const [focus, setFocus] = useState<{ id: string; n: number } | null>(null);
  const query = useQuery({ queryKey: ["company", key], queryFn: () => api.company(key!), enabled: !!key });
  const scrip = (query.data?.company?.scrip_code as string | undefined) ?? key;
  const cards = query.data?.cards;
  const parsed = useMemo(() => (cards ?? []).flatMap((row) => { const card = parseCard(row); return card ? [{ row, card }] : []; }), [cards]);

  if (query.isPending) return <Loading />;
  if (query.isError) return <div className="mx-auto max-w-[1240px] p-6"><Empty title="Couldn't load this company" body={String(query.error)} /></div>;
  const { company, dossier, chart } = query.data;
  if (!company && !dossier) return <div className="mx-auto max-w-[1240px] p-6"><Empty title={`No company ${scrip}`} /></div>;
  const rows = query.data.cards;
  const name = company?.company_name ?? dossier?.company_name ?? scrip!;
  const symbol = company?.symbol ?? dossier?.symbol ?? null;
  const today = todayIST();
  const day = dayChange(chart, company?.last_price, company?.price_date);
  const expected = nextResults(parsed.filter((p) => p.card.results).map((p) => ({ period: p.card.results!.period, filed_at: p.row.filed_at })), today);
  const openCard = (id: string, inTab?: string) => {
    if (inTab) setParams({ tab: inTab });
    setFocus((f) => ({ id, n: (f?.n ?? 0) + 1 }));
  };

  return (
    <div className="mx-auto w-full max-w-[1240px] px-4 py-5 sm:px-6">
      <Link href="/companies" className="mb-3 inline-flex items-center gap-1 text-[13px] text-ink-3 hover:text-ink">
        <ArrowLeft className="h-3.5 w-3.5" /> Companies
      </Link>
      <header className="grid items-start gap-4 md:grid-cols-[minmax(0,1fr)_auto]">
        <div className="flex min-w-0 items-center gap-4">
          <Avatar name={name} symbol={symbol} size={64} className="shadow-lg" />
          <div className="min-w-0">
            <h1 className="font-display text-[23px] font-extrabold leading-tight tracking-tight text-ink sm:text-[28px]">{name}</h1>
            <p className="mt-0.5 text-[13.5px] font-semibold text-ink-3">
              <span className="num">{listing(symbol, scrip)}</span>
              {company?.sector ? ` · ${SECTORS[company.sector] ?? titleCase(company.sector)}` : ""}
              {company?.industry ? ` › ${company.industry.split(">").pop()?.trim()}` : ""}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {company?.size_category && <Badge className="rounded-full bg-accent-soft px-2.5 py-1 font-bold text-accent">{titleCase(company.size_category)} cap</Badge>}
              {company?.credibility_score != null && (
                <Badge className={cn("rounded-full px-2.5 py-1 font-bold", company.credibility_score >= 75 ? "bg-pos-soft text-pos" : company.credibility_score < 50 ? "bg-warn-soft text-warn" : "bg-surface-2 text-ink-2")}>
                  🎯 Credibility {Math.round(company.credibility_score)}%
                </Badge>
              )}
              {chartTags(chart).map((t) => <Badge key={t.text} className={cn("rounded-full px-2.5 py-1 font-bold", TAG_CLS[t.tone])}>{t.text}</Badge>)}
              {company?.median_turnover_cr != null && company.median_turnover_cr < 0.5 && <Badge className="rounded-full bg-warn-soft px-2.5 py-1 font-bold text-warn">💧 Thin liquidity</Badge>}
              {technicalTags(company).map((t) => <Badge key={t} className="rounded-full bg-surface-2 px-2.5 py-1 font-bold text-ink-2">{t}</Badge>)}
              {expected && expected.date <= addDaysIso(today, 120) && (
                <Badge className="rounded-full bg-warn-soft px-2.5 py-1 font-bold text-warn" title={`${expected.period} results, expected from last year's date`}>
                  Results due {new Date(`${expected.date}T00:00:00Z`).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" })}
                </Badge>
              )}
            </div>
          </div>
        </div>
        <div className="md:text-right">
          <div className="num text-[26px] font-bold tracking-tight text-ink sm:text-[32px]">{company?.last_price != null ? price2(company.last_price) : "—"}</div>
          {day && (
            <div className={cn("num text-[14px] font-bold", signClass(day.change))}>
              {day.change >= 0 ? "▲" : "▼"} {Math.abs(day.change).toFixed(2)} ({day.pct > 0 ? "+" : day.pct < 0 ? "−" : ""}{Math.abs(day.pct).toFixed(2)}%) {day.date === today ? "today" : `on ${dayMonth(day.date)}`}
            </div>
          )}
          <div className="num flex flex-wrap gap-x-3 text-[12px] font-semibold md:justify-end">
            {([["1W", company?.ret_1w], ["1M", company?.ret_1m], ["1Y", company?.ret_1y]] as const).map(([l, v]) => (
              <span key={l} className="text-ink-3">{l} <span className={signClass(v)}>{pct(v)}</span></span>
            ))}
            {company?.price_date && <span className="text-ink-3">· {istDate(company.price_date)}</span>}
          </div>
          <div className="mt-2.5 flex flex-wrap gap-2 md:justify-end">
            {company && <WatchButton scrip={company.scrip_code} on={!!company.watchlist} />}
            {rows[0]?.pdf_url && <a href={rows[0].pdf_url} target="_blank" rel="noreferrer" className={btn}>⎙ Latest PDF</a>}
          </div>
        </div>
      </header>

      <KeyFigures company={company} dossier={dossier} cards={rows} chart={chart} today={today} />

      <div className="sticky top-[62px] z-10 -mx-4 mt-3.5 bg-bg px-4 pb-1 pt-3 sm:-mx-6 sm:px-6">
        <div role="tablist" className="card-soft no-scrollbar inline-flex max-w-full gap-0.5 overflow-x-auto rounded-2xl p-1">
          {TABS.map((t) => (
            <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setParams({ tab: t.key === "overview" ? null : t.key })}
              className={cn("whitespace-nowrap rounded-[10px] px-3.5 py-2 text-[13.5px] font-bold transition-colors", tab === t.key ? "grad-accent shadow-md" : "text-ink-2 hover:text-ink")}>
              {t.key === "filings" ? `Filings · ${Math.max(rows.length, company?.card_count ?? 0)}` : t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4">
        {tab === "overview" && (
          <Overview dossier={dossier} parsed={parsed} cards={rows} chart={chart} calls={query.data.calls} expected={expected} focus={focus}
            onOpen={(id) => openCard(id)} onTab={(t) => setParams({ tab: t })} />
        )}
        {tab === "results" && (
          dossier || parsed.some((p) => p.card.results) ? (
            <div className="grid items-start gap-[18px] lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
              <div className="min-w-0 space-y-[18px]">
                {dossier && <QuarterBars dossier={dossier} />}
              </div>
              <div className="min-w-0 space-y-[18px]">
                <ResultsScorecard parsed={parsed} onOpen={(id) => openCard(id, "filings")} />
                {dossier && <BalanceTiles dossier={dossier} />}
                {dossier && <SegmentMix dossier={dossier} />}
              </div>
              {/* the statements as screener.in lays them out, then every other figure the filings gave (owner, 2026-10-21) */}
              {dossier && <div className="min-w-0 space-y-[18px] lg:col-span-2"><Financials dossier={dossier} />
                <details className="group">
                  <summary className="cursor-pointer list-none text-[13px] font-bold text-accent marker:hidden">
                    <span className="mr-1 inline-block transition-transform group-open:rotate-90">›</span>Every reported figure, line by line
                  </summary>
                  <div className="mt-3"><MetricsPanel dossier={dossier} balance={false} /></div>
                </details></div>}
            </div>
          ) : <Empty title="No results analysed yet" />
        )}
        {tab === "promises" && <PromiseTracker dossier={dossier} company={company} />}
        {tab === "timeline" && (
          <div className="grid items-start gap-[18px] lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
            <div className="min-w-0"><Timeline dossier={dossier} cards={rows} /></div>
            <div className="min-w-0"><DealsAndNotes dossier={dossier} stacked /></div>
          </div>
        )}
        {tab === "owners" && <OwnersTab dossier={dossier} peers={query.data.peers ?? []} company={company} />}
        {tab === "filings" && (
          rows.length ? (
            <CardList cards={rows} pageSize={20} focus={focus} header={(filters, n) => (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-[16px] font-extrabold tracking-tight text-ink">All filings with a card <small className="ml-1.5 text-[12.5px] font-semibold text-ink-3">{n}{(company?.card_count ?? 0) > rows.length ? ` (the latest ${rows.length} of ${company!.card_count})` : ""} · newest first</small></h2>
                {filters}
              </div>
            )} />
          ) : <Empty title="No material filings analysed yet" />
        )}
      </div>
      <p className="mt-10 text-center text-[11px] text-ink-3">AI summaries of public NSE filings, refreshed with every new filing. Not investment advice.</p>
    </div>
  );
}

function addDaysIso(day: string, days: number): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) + days * 86400_000).toISOString().slice(0, 10);
}

export function promiseStats(guidance: Guidance[]) {
  const delivered = guidance.filter((g) => g.status === "DELIVERED").length;
  const missed = guidance.filter((g) => ["MISSED", "DELAYED", "WITHDRAWN"].includes(g.status)).length;
  const open = guidance.filter((g) => ["OPEN", "ON_TRACK", "REVISED"].includes(g.status)).length;
  return { delivered, missed, open, resolved: delivered + missed };
}

type Expected = ReturnType<typeof nextResults>;

/** The approved order (design 2026-10-19): four summary tiles, then price, the story, good & bad, what to track and
 *  the cards on the left; promises, deals, notes and what is coming up on the right. */
function Overview({ dossier, parsed, cards, chart, calls, expected, focus, onOpen, onTab }: {
  dossier: Dossier | null; parsed: Parsed[]; cards: CardRow[]; chart: Parameters<typeof PriceChart>[0]["chart"]; calls?: CallQuarter[]; expected: Expected;
  focus: { id: string; n: number } | null; onOpen: (id: string) => void; onTab: (t: string) => void;
}) {
  const today = todayIST();
  const latest = parsed[0];
  const stats = promiseStats(dossier?.guidance ?? []);
  const next = (dossier?.upcoming_events ?? []).filter((e) => e.date >= today).sort((a, b) => a.date.localeCompare(b.date))[0];
  const nextTile = next && (!expected || next.date <= expected.date)
    ? { value: titleCase(next.event_type), sub: dayMonth(next.date) }
    : expected ? { value: `${expected.period} results`, sub: `~${dayMonth(expected.date)}, from last year` } : null;

  return (
    <div className="space-y-[18px]">
      <div className="card-soft rise-in grid grid-cols-2 gap-2.5 p-3 sm:p-4 lg:grid-cols-4">
        <Tile label="Promise record" value={stats.resolved ? `${stats.delivered} of ${stats.resolved} delivered` : "None resolved yet"}
          tone={stats.resolved ? (stats.missed ? "MIXED" : "POSITIVE") : "NEUTRAL"} action="View tracker" onAction={() => onTab("promises")} />
        <Tile label="Open commitments" value={`${stats.open} tracked`} tone="NEUTRAL" action="View tracker" onAction={() => onTab("promises")} />
        <Tile label="Latest filing" value={latest?.card.tone ? TONE_LABEL[latest.card.tone as Tone] : "—"} tone={(latest?.card.tone ?? "NEUTRAL") as Tone}
          action={latest ? `${EVENT_LABELS[latest.row.event_category] ?? "Filing"}, ${dayMonth(latest.row.filed_at)}` : undefined} onAction={latest ? () => onOpen(latest.row.news_id) : undefined} />
        <Tile label="Next catalyst" value={nextTile?.value ?? "None scheduled"} tone="NEUTRAL" sub={nextTile?.sub} />
      </div>
      <div className="grid items-start gap-[18px] lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-[18px]">
          <PriceChart chart={chart} cards={cards} onOpen={onOpen} />
          <StorySoFar dossier={dossier} parsed={parsed} count={cards.length} />
          <GoodAndBad parsed={parsed} />
          <EarningsCalls calls={calls} />
          <WhatToTrack dossier={dossier} parsed={parsed} onTracker={() => onTab("promises")} />
          {cards.length > 0 && (
            <CardList cards={cards} pageSize={4} focus={focus} header={(filters, n) => (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-[16px] font-extrabold tracking-tight text-ink">Cards <small className="ml-1.5 text-[12.5px] font-semibold text-ink-3">
                  {n} since {istDate(HISTORY_START).split(" ").slice(1).join(" ")} · <button type="button" onClick={() => onTab("filings")} className="font-bold text-accent hover:underline">all filings</button></small></h2>
                {filters}
              </div>
            )} />
          )}
        </div>
        <div className="min-w-0 space-y-[18px]">
          <PromiseSummary dossier={dossier} />
          <DealsAndNotes dossier={dossier} stacked compact />
          <ComingUp dossier={dossier} expected={expected} />
          <TradeRemediesPanel dossier={dossier} />
        </div>
      </div>
    </div>
  );
}

/** ★ the company (owner only): starred companies stay in the universe whatever their size. */
function WatchButton({ scrip, on }: { scrip: string; on: boolean }) {
  const token = useOwnerToken();
  const client = useQueryClient();
  const [value, setValue] = useState(on);
  if (!token) return value ? <Badge className="h-[38px] rounded-xl bg-accent-soft px-4 text-[13.5px] font-extrabold text-accent">★ Watchlist</Badge> : null;
  return (
    <button type="button" aria-pressed={value} onClick={async () => {
      setValue(!value);
      await ownerApi.watch(token, scrip, !value).catch(() => setValue(value));
      void client.invalidateQueries({ queryKey: ["company", scrip] });
    }} className={cn("inline-flex h-[38px] items-center rounded-xl px-4 text-[13.5px] font-extrabold shadow-sm", value ? "grad-accent" : "card-soft text-ink hover:text-accent")}>
      {value ? "★ Watching" : "☆ Watch"}
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
  const ownNames = (identity?.former_names ?? []).filter(formerOwnName);
  if (!ownNames.length && !entities.length && !owners.length && !auditor && !predictions.length) return null;
  const last = owners[owners.length - 1];
  const prev = owners[owners.length - 2];
  const delta = (k: "promoter_pct" | "fii_pct" | "dii_pct" | "pledge_pct") =>
    last?.[k] != null && prev?.[k] != null ? ` (${(last[k]! - prev[k]!) >= 0 ? "+" : ""}${(last[k]! - prev[k]!).toFixed(1)} pp)` : "";
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Panel title="Identity & governance" hint="Former names, group entities, auditor">
        <dl className="space-y-2 text-[13.5px]">
          {ownNames.length ? <div><dt className="eyebrow text-ink-3">Formerly</dt><dd className="text-ink">{ownNames.join(" · ")}</dd></div> : null}
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
                  {p.status === "OPEN" ? "Open" : p.status === "MET" ? "Met" : p.status === "NOT_REPORTED" ? "Not reported" : p.status === "UNCHECKED" ? "Not comparable (units)" : "Missed"}
                </Badge>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

/** Each order, deal or capex plan once, at its latest stage; plus operating facts worth remembering. `compact` (the
 *  Overview) keeps the three latest of each and leaves out "Other" records: tax orders and settlements are not deals. */
export function DealsAndNotes({ dossier, stacked = false, compact = false }: { dossier: Dossier | null; stacked?: boolean; compact?: boolean }) {
  const deals = [...(dossier?.deals ?? [])].filter((d) => !compact || d.kind !== "OTHER")
    .sort((a, b) => (b.updated_as_of ?? b.as_of).localeCompare(a.updated_as_of ?? a.as_of)).slice(0, compact ? 3 : undefined);
  // the full lists on the Timeline tab (owner, 2026-10-21: "operating notes data, is that all we have?": it showed 6)
  const notes = [...(dossier?.operating_notes ?? [])].sort((a, b) => String(b.as_of).localeCompare(String(a.as_of)))
    .slice(0, compact ? 3 : undefined);
  if (!deals.length && !notes.length) return null;
  return (
    <div className={cn("grid gap-[18px]", !stacked && deals.length && notes.length && "md:grid-cols-2")}>
      {deals.length > 0 && (
        <Panel title="Orders, deals and capex" sub="each once, at its latest stage">
          <ul>
            {deals.map((d) => (
              <li key={d.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-2.5 gap-y-0.5 border-t border-line py-2 first:border-0 first:pt-0">
                <span className="min-w-0 text-[13.5px] text-ink">{titleCase(d.kind)}{d.segment ? ` · ${d.segment}` : ""}</span>
                <Badge className={cn("rounded-full px-2.5 py-[3px] font-bold", PROVISIONAL_STAGES.has(d.stage) ? "bg-warn-soft text-warn" : d.stage === "COMPLETED" ? "bg-pos-soft text-pos" : "bg-surface-2 text-ink-2")}>
                  {STAGE_LABEL[d.stage] ?? titleCase(d.stage)}
                </Badge>
                <small className={cn("col-span-2 text-[12px] text-ink-3", compact && "line-clamp-2")}>
                  {[d.amount_cr != null ? cr(d.amount_cr) : null, d.counterparty, istDate(d.updated_as_of ?? d.as_of), d.progress].filter(Boolean).join(" · ")}
                </small>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {notes.length > 0 && (
        <Panel title="Operating notes" sub="facts worth remembering">
          <ul className="space-y-2">
            {notes.map((n, i) => (
              <li key={i} className="grid grid-cols-[52px_minmax(0,1fr)] gap-x-2.5 text-[13.5px]">
                <span className="num pt-px text-[12px] text-ink-3">{railDate(n.as_of).split(" ").slice(1).join(" ")}</span>
                <span className={cn("text-ink-2", compact && "line-clamp-2")}>{n.text}</span>
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
    <div className="flex min-w-0 flex-col rounded-2xl bg-surface-2 px-3 py-2.5 sm:px-3.5">
      <span className="text-[11px] font-bold text-ink-3">{label}</span>
      <span className={cn("text-[15px] font-extrabold leading-snug", tone === "POSITIVE" ? "text-pos" : tone === "NEGATIVE" ? "text-neg" : tone === "MIXED" ? "text-warn" : "text-ink")}>{value}</span>
      {sub ? <span className="text-[12px] font-bold text-accent">{sub}</span> : null}
      {action && onAction ? (
        <button type="button" onClick={onAction} className="text-left text-[12px] font-bold text-accent hover:underline">{action}</button>
      ) : null}
    </div>
  );
}

const FOLLOW_SHOWN = 8;

/** The commitments with their evidence, the follow-ups earlier cards set, and what is overdue. */
function PromiseTracker({ dossier, company }: { dossier: Dossier | null; company: Company | null }) {
  const guidance = [...(dossier?.guidance ?? [])].reverse();
  const stats = promiseStats(guidance);
  const today = todayIST();
  const late = overdue(guidance, today);
  const [allFollow, setAllFollow] = useState(false);
  // open follow-ups first, newest first; resolved ones after them
  const follow = [...(dossier?.watchlist ?? [])].sort((a, b) =>
    Number(!["OPEN", "PENDING", "PARTIAL"].includes(a.status)) - Number(!["OPEN", "PENDING", "PARTIAL"].includes(b.status)) || b.created_on.localeCompare(a.created_on));
  return (
    <div className="space-y-[18px]">
      <div className="card-soft rise-in grid grid-cols-2 gap-2.5 p-3 sm:grid-cols-4 sm:p-4">
        {[["Delivered", stats.delivered, "text-pos"], ["Missed or delayed", stats.missed, "text-neg"], ["Open", stats.open, "text-ink"],
          ["Delivery rate", stats.resolved ? `${Math.round((stats.delivered / stats.resolved) * 100)}%` : "—", "text-accent"]].map(([label, value, cls]) => (
          <div key={String(label)} className="rounded-2xl bg-surface-2 px-3.5 py-2.5">
            <div className="text-[11px] font-bold text-ink-3">{label}</div>
            <div className={cn("num text-[22px] font-bold", String(cls))}>{value}</div>
          </div>
        ))}
      </div>
      <CapitalAndCalibration rule={company?.calibration_rule ?? null} roiic={parseRoiic(company?.roiic)} />
      <div className="grid items-start gap-[18px] lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <Panel title="Management commitments" sub="from AGMs, calls, presentations and filings; status from later filings">
          {guidance.length ? (
            <div className="-mx-5 overflow-x-auto">
              <table className="w-full min-w-[520px] text-[13px]">
                <thead className="border-b border-line text-left text-[10.5px] font-extrabold uppercase tracking-[0.07em] text-ink-3">
                  <tr><th className="px-5 py-1.5">Commitment</th><th className="px-2 py-1.5">Made</th><th className="px-2 py-1.5">Due</th><th className="py-1.5 pl-2 pr-5">Status</th></tr>
                </thead>
                <tbody>
                  {guidance.map((g) => {
                    const last = g.status_history[g.status_history.length - 1];
                    const isLate = !!g.due_date && g.due_date < today && ["OPEN", "ON_TRACK"].includes(g.status);
                    return (
                      <tr key={g.id} className="border-b border-line align-top last:border-0">
                        <td className="px-5 py-2 text-ink">{short(g.statement, 160)}{g.target ? <span className="text-ink-2"> · {g.target}</span> : null}
                          <div className="text-[11.5px] leading-snug text-ink-3">{titleCase(g.source_type)}{last ? <> · {short(last.evidence, 140)} ({dayMonth(last.as_of)})</> : null}</div></td>
                        <td className="num whitespace-nowrap px-2 py-2 text-ink-2">{railDate(g.given_on).split(" ").slice(1).join(" ")}</td>
                        <td className={cn("num whitespace-nowrap px-2 py-2", isLate ? "font-semibold text-neg" : "text-ink-2")}>{g.due ?? "—"}</td>
                        {/* past its deadline a promise is not "on track": delivered, missed, or not reported yet */}
                        <td className="py-2 pl-2 pr-5"><Badge className={cn("rounded-full px-2.5 py-[3px] font-bold", isLate ? "bg-warn-soft text-warn" : STATUS_CHIP[g.status] ?? STATUS_CHIP.OPEN)}>{isLate ? "Not reported" : titleCase(g.status)}</Badge></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : <p className="text-sm text-ink-3">No commitments recorded yet. Concall transcripts, AGM speeches and investor presentations feed this tracker.</p>}
        </Panel>
        <div className="min-w-0 space-y-[18px]">
          <Panel title="⚠ Overdue" sub="past the due date, nothing on record">
            {late.length ? (
              <ul>
                {late.map((g) => (
                  <li key={g.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-2.5 border-t border-line py-2 text-[13.5px] first:border-0 first:pt-0">
                    <span className="text-ink">{short(g.statement)}</span>
                    <Badge className="num rounded-full bg-neg-soft px-2.5 py-[3px] font-bold text-neg">{g.days} days</Badge>
                    <small className="col-span-2 text-[12px] text-ink-3">due {g.due ?? istDate(g.due_date!)} · made {istDate(g.given_on)}</small>
                  </li>
                ))}
              </ul>
            ) : <p className="m-0 text-[13.5px] text-ink-2">No overdue commitments for this company.</p>}
          </Panel>
          <Panel title="Follow-ups" sub="what earlier cards said to verify, and analysts' concerns on calls">
            {follow.length ? (
              <>
                <ul>
                  {(allFollow ? follow : follow.slice(0, FOLLOW_SHOWN)).map((w) => (
                    <li key={w.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-2.5 border-t border-line py-2 text-[13.5px] first:border-0 first:pt-0">
                      <span className="text-ink">{WATCH_VERB[w.kind] ?? "Pending"}: {short(w.text, 140)}{w.target ? <span className="text-ink-2"> · target {w.target}</span> : null}</span>
                      <Badge className={cn("rounded-full px-2.5 py-[3px] font-bold", STATUS_CHIP[w.status] ?? STATUS_CHIP.OPEN)}>{titleCase(w.status)}</Badge>
                      <small className="col-span-2 text-[12px] text-ink-3">
                        {[w.check_in, `flagged ${istDate(w.created_on)}`, w.response ? `management said: ${short(w.response, 120)}` : null].filter(Boolean).join(" · ")}
                      </small>
                    </li>
                  ))}
                </ul>
                {follow.length > FOLLOW_SHOWN && (
                  <button type="button" onClick={() => setAllFollow(!allFollow)} className="mt-2 text-[12.5px] font-bold text-accent hover:underline">
                    {allFollow ? "Show fewer" : `Show all ${follow.length}`}
                  </button>
                )}
              </>
            ) : <p className="text-sm text-ink-3">No follow-ups yet.</p>}
          </Panel>
        </div>
      </div>
    </div>
  );
}

/** One compact tile per results filing: the verdict, profit and revenue against a year ago; a tile opens its card. */
function ResultsScorecard({ parsed, onOpen }: { parsed: Parsed[]; onOpen: (newsId: string) => void }) {
  const [all, setAll] = useState(false);
  const quarters = parsed.filter((p) => p.card.results);
  if (!quarters.length) return null;
  return (
    <Panel title="Quarterly scorecard" sub="verdict for each results filing">
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {(all ? quarters : quarters.slice(0, 4)).map(({ row, card }) => {
          const v = verdict((card.tone ?? "NEUTRAL") as Tone, row.impact_level);
          const lines = resultLines(card.results!);
          const profit = lines.find((l) => l.key === "pat");
          const top = lines.find((l) => ["revenue", "interest_earned", "gross_premium", "net_interest_income"].includes(l.key));
          return (
            <button key={row.news_id} type="button" onClick={() => onOpen(row.news_id)} title="Open the card"
              className="flex min-w-0 flex-col items-start gap-1 rounded-2xl bg-surface-2 px-3 py-2.5 text-left text-[12.5px] hover:ring-1 hover:ring-accent">
              <span className="num text-ink-3">{card.results!.period}</span>
              <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-extrabold", TONE_CHIP[v.tone])}>{v.label}</span>
              {profit && <b className="text-[14px] leading-snug">Profit <Change value={profit.line.yoy_pct} turn={turnOf(profit.line)} /></b>}
              {top && <span className="text-ink-2">{top.label} <Change value={top.line.yoy_pct} turn={turnOf(top.line)} /></span>}
            </button>
          );
        })}
      </div>
      {quarters.length > 4 && (
        <button type="button" onClick={() => setAll(!all)} className="mt-2.5 text-[12.5px] font-bold text-accent hover:underline">
          {all ? "Show fewer" : `Show all ${quarters.length} results filings`}
        </button>
      )}
    </Panel>
  );
}

// The lines a reader looks for first: a company's P&L, a bank's and an insurer's
/** Every figure memory holds by period, every line in statement order under its section (owner, 2026-10-21: the
 *  drawer's baseline was complete, the page's in the wrong order; now one baseline on the page); `balance` adds the
 *  balance sheet below. */
export function MetricsPanel({ dossier, balance: showBalance = true, periods = 8 }: { dossier: Dossier; balance?: boolean; periods?: number }) {
  // owner rule 26 Oct 2026: no EPS on cards or stock pages; memory keeps every EPS figure (F188 variants too), the page shows none
  const MEMORY_ONLY_ROWS = new Set(["eps", "basic_eps", "diluted_eps", "eps_total", "eps_continuing"]);
  type Cell = { value: number; unit: string; yoy?: number | null };
  type Group = { periods: string[]; metrics: Map<string, Map<string, Cell>> };
  const groups = useMemo(() => {
    const byKind = new Map<string, Group>();
    for (const m of dossier.financial_metrics) {
      if (MEMORY_ONLY_ROWS.has(m.metric)) continue;   // no EPS rows (owner rule 26 Oct 2026)
      const kind = periodKind(m.period);
      const g: Group = byKind.get(kind) ?? { periods: [], metrics: new Map() };
      if (!g.periods.includes(m.period)) g.periods.push(m.period);
      const row = g.metrics.get(m.metric) ?? new Map<string, Cell>();
      row.set(m.period, { value: m.value, unit: m.unit, yoy: m.yoy_pct });
      g.metrics.set(m.metric, row);
      byKind.set(kind, g);
    }
    for (const g of byKind.values()) g.periods.sort((a, b) => periodEnd(a).localeCompare(periodEnd(b)));
    // quarters and years only (owner, 2026-10-21: "what is monthly"; half-year and nine-month sums are in the years)
    return [...byKind.entries()].filter(([k]) => k === "Quarter" || k === "Year");
  }, [dossier.financial_metrics]);
  const [kind, setKind] = useState<string | null>(null);
  const active = groups.find(([k]) => k === kind) ?? groups.find(([k]) => k === "Quarter") ?? groups[0];
  const balance = showBalance ? latestBalance(dossier.balance_sheet) ?? null : null;
  const rows = inStatementOrder(active ? [...active[1].metrics.entries()].filter(([, v]) => !allZero(v.values())) : []);
  const shown = active ? active[1].periods.slice(-periods) : [];

  return (
    <div className="space-y-4">
      <Panel title="Every reported figure" sub="each line memory holds from the filings; restatements replace older numbers">
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
                  <tr><th className="px-5 py-2 text-left font-semibold">Metric</th>{shown.map((p) => <th key={p} className="num px-3 py-2 text-right font-semibold">{p}</th>)}</tr>
                </thead>
                <tbody>
                  {rows.map(([metric, values], k) => (
                    <Fragment key={metric}>
                    {(k === 0 || statementPlace(rows[k - 1][0]).section !== statementPlace(metric).section) && (
                      <tr><td colSpan={shown.length + 1} className="eyebrow bg-surface-2 px-5 py-1.5 text-ink-3">{statementPlace(metric).section}</td></tr>
                    )}
                    <tr className="border-b border-line last:border-0">
                      <td className="whitespace-nowrap px-5 py-2 font-medium text-ink">{metricLabel(metric)}</td>
                      {shown.map((p) => {
                        const v = values.get(p);
                        return (
                          <td key={p} className="num whitespace-nowrap px-3 py-2 text-right text-ink">
                            {v ? (v.unit === "INR_CR" ? cr(v.value) : unitValue(num(v.value), v.unit)) : <span className="text-ink-3">—</span>}
                            {v?.yoy != null ? <div className={cn("text-[11px]", signClass(v.yoy))}>{pct(v.yoy)} YoY</div> : null}
                          </td>
                        );
                      })}
                    </tr>
                    </Fragment>
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

const TIMELINE_SHOWN = 20;

/** How the story is unfolding: one entry per event, newest first. A filing of the same kind within two days of another
 *  (the results, their press release, the XBRL) is the same event, kept once with the fullest summary. */
function Timeline({ dossier, cards }: { dossier: Dossier | null; cards: CardRow[] }) {
  const [all, setAll] = useState(false);
  const byId = useMemo(() => new Map(cards.map((c) => [c.news_id, c])), [cards]);
  const events = useMemo(() => {
    const out: Dossier["timeline"] = [];
    for (const e of [...(dossier?.timeline ?? [])].sort((a, b) => b.date.localeCompare(a.date))) {
      const same = out.find((o) => o.event_type === e.event_type && Math.abs(Date.parse(o.date) - Date.parse(e.date)) <= 2 * 86400_000);
      if (!same) out.push({ ...e });
      else if (e.summary.length > same.summary.length) Object.assign(same, { summary: e.summary, impact_level: same.impact_level ?? e.impact_level });
    }
    return out;
  }, [dossier]);
  if (!events.length) return <Empty title="No events recorded yet" />;
  return (
    <Panel title="How the story is unfolding" sub={`${events.length} events since ${istDate(HISTORY_START)}`}>
      <ol>
        {(all ? events : events.slice(0, TIMELINE_SHOWN)).map((e, k, shown) => {
          const period = e.summary.match(/\b(?:Q[1-4]|H[12]|9M)?FY\d{2}\b/)?.[0];
          return (
            <li key={e.id} className="grid grid-cols-[58px_16px_minmax(0,1fr)] gap-x-2 sm:grid-cols-[70px_18px_minmax(0,1fr)] sm:gap-x-2.5">
              <RailTime iso={e.date} />
              <span aria-hidden className="flex flex-col items-center">
                <i className="mt-[3px] h-3 w-3 shrink-0 rounded-full border-[3px] border-surface ring-1 ring-line-strong" style={{ background: IMPACT_DOT[e.impact_level ?? "LOW"] }} />
                {k < shown.length - 1 && <u className="w-[2px] flex-1 bg-line" />}
              </span>
              <div className="min-w-0 pb-4">
                <b className="block text-[14.5px] font-extrabold tracking-tight text-ink">{EVENT_LABELS[e.event_type] ?? titleCase(e.event_type)}{period && e.event_type === "RESULTS" ? ` · ${period}` : ""}</b>
                {/* memory written before 2026-10-20 starts some summaries with their own date */}
                <p className="m-0 mt-0.5 line-clamp-2 text-[13.5px] leading-snug text-ink-2">{e.summary.replace(/^\d{4}-\d{2}-\d{2}:\s*/, "")}</p>
                <Reaction row={byId.get(e.news_id)} />
              </div>
            </li>
          );
        })}
      </ol>
      {events.length > TIMELINE_SHOWN && (
        <button type="button" onClick={() => setAll(!all)} className="text-[12.5px] font-bold text-accent hover:underline">{all ? "Show fewer" : `Show all ${events.length}`}</button>
      )}
    </Panel>
  );
}

/** The market's move after the event, against the index where the post-mortem had one (from the drawer's timeline). */
function Reaction({ row }: { row: CardRow | undefined }) {
  let rx: PriceReaction | null = null;
  try { rx = row?.post_event_return_json ? (JSON.parse(row.post_event_return_json) as PriceReaction) : null; } catch { rx = null; }
  const t1 = rx?.t1?.excess_pct ?? rx?.t1?.return_pct, t3 = rx?.t3?.excess_pct ?? rx?.t3?.return_pct;
  if (t1 === undefined && t3 === undefined) return null;
  const move = (v: number | undefined) => v === undefined ? "–" : <span className={signClass(v)}>{pct(v)}</span>;
  return <small className="num mt-0.5 block text-[12px] text-ink-3">T+1 {move(t1)} · T+3 {move(t3)}{rx?.benchmark ? " vs index" : ""}</small>;
}

/** Price-structure tags from the market-data job, as the cards show them. */
function technicalTags(company: Company | null): string[] {
  let t: Technicals | null = null;
  try { t = company?.technicals_json ? JSON.parse(company.technicals_json) : null; } catch { t = null; }
  if (!t) return [];
  return [t.stage2 ? "📈 Stage 2 trend" : "", t.vcp ? "⚡ Coiled spring" : "", t.rs_pct != null && t.rs_pct >= 80 ? `RS ${t.rs_pct}` : ""].filter(Boolean);
}

/** The company in eight figures under its name: size and price, balance sheet, liquidity, owners and how much we know. */
function KeyFigures({ company, dossier, cards, chart, today }: { company: Company | null; dossier: Dossier | null; cards: CardRow[];
  chart: Parameters<typeof PriceChart>[0]["chart"]; today: string }) {
  const fundamentals = cards.map(parseCard).find((c) => c?.fundamentals)?.fundamentals ?? {};
  const own = dossier?.ownership?.[dossier.ownership.length - 1];
  const high = cards.filter((c) => c.impact_level === "HIGH").length;
  const pe = peTtm(dossier?.financial_metrics ?? [], company?.market_cap_cr, today);
  const range = yearRange(chart);
  const px = (v: number) => v.toLocaleString("en-IN", { maximumFractionDigits: v < 100 ? 2 : 0 });
  const items: [string, string, string?][] = [
    // each figure with its as-of (data chain audit B2, 22 Oct 2026): the close it is priced at, the quarter it is to,
    // the balance sheet it is from
    ["Market cap", crShort(company?.market_cap_cr), company?.price_date ? `at ${istDate(company.price_date).replace(/ \d{4}$/, "")} close` : undefined],
    ["P/E (TTM)", pe ? `${pe.pe.toFixed(1)}x` : "—", pe ? `to ${pe.through}` : undefined],
    ["Debt", crShort(fundamentals.debt?.value), fundamentals.debt?.period ?? undefined],
    ["Net worth", crShort(fundamentals.net_worth?.value), fundamentals.net_worth?.period ?? undefined],
    ["Traded a day", company?.median_turnover_cr != null ? `₹${company.median_turnover_cr.toFixed(company.median_turnover_cr < 10 ? 2 : 0)} Cr` : "—", company?.median_turnover_cr != null ? "median" : undefined],
    ["52-week range", range ? `${px(range.lo)}–${px(range.hi)}` : "—"],
    ["Promoter", own?.promoter_pct != null ? `${own.promoter_pct}%` : "—",
      [own?.period, own?.pledge_pct != null ? `${own.pledge_pct}% of it pledged` : null].filter(Boolean).join(" · ") || undefined],
    ["Filings analysed", num(cards.length), high ? `${high} high` : undefined],
  ];
  return (
    <dl className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4 lg:grid-cols-8">
      {items.map(([label, value, sub]) => (
        <div key={label} className="card-soft rise-in min-w-0 !rounded-2xl px-3.5 py-2.5">
          <dt className="text-[11.5px] font-bold leading-tight text-ink-3">{label}</dt>
          <dd className="num text-[15px] font-bold leading-snug text-ink"><span className="whitespace-nowrap">{value}</span>{sub && <small className="ml-1 inline-block text-[11px] font-semibold text-ink-3">{sub}</small>}</dd>
        </div>
      ))}
    </dl>
  );
}

/** The latest balance sheet in memory as tiles. */
function BalanceTiles({ dossier }: { dossier: Dossier }) {
  const balance = latestBalance(dossier.balance_sheet);
  if (!balance) return null;
  // the label (lab) is memory's provenance, an object: never a tile
  const items = Object.entries(balance).filter(([k, v]) => v !== null && typeof v !== "object" && !["as_of", "source_news_id", "period"].includes(k));
  if (!items.length) return null;
  return (
    <Panel title="Balance sheet" sub={balance.period ? `${balance.period} · filed ${istDate(String(balance.as_of))}` : `as of ${istDate(String(balance.as_of))}`}>
      <dl className="grid grid-cols-2 gap-2.5">
        {items.map(([k, v]) => (
          <div key={k} className="min-w-0 rounded-2xl bg-surface-2 px-3 py-2.5">
            <dt className="text-[11px] font-bold text-ink-3">{titleCase(k.replace(/_cr$/, ""))}</dt>
            <dd className="num text-[14.5px] font-extrabold text-ink">{typeof v === "number" ? (k.endsWith("_cr") ? crShort(v) : num(v)) : String(v)}</dd>
          </div>
        ))}
      </dl>
    </Panel>
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
  const table = useMemo(() => {
    const rev = quarterly(dossier.financial_metrics, ["revenue"]), pat = quarterly(dossier.financial_metrics, ["pat_owners", "pat"]);
    const last = Math.max(...rev.keys(), ...pat.keys());
    if (!Number.isFinite(last)) return null;
    const qs = [3, 2, 1, 0].map((k) => last - k).filter((q) => rev.has(q) || pat.has(q));
    const yoy = (m: Map<number, number>, q: number) => { const a = m.get(q), b = m.get(q - 4); return a != null && b != null && b > 0 && a >= 0 ? (a / b - 1) * 100 : undefined; };
    return { qs, rows: [["Revenue", rev], ["Profit", pat]] as const, yoy };
  }, [dossier.financial_metrics]);
  if (series.length < 2 && metric === "revenue") return null;
  const values = series.map(([, v]) => v);
  const lo = metric === "ebitda_margin" ? Math.min(...values) - 2 : Math.min(0, ...values);
  const hi = Math.max(...values) * 1.08 || 1;
  const label = (v: number) => metric === "ebitda_margin" ? `${v.toFixed(1)}%` : Math.abs(v) >= 10000 ? `${(v / 1000).toFixed(1)}k` : Math.round(v).toLocaleString("en-IN");
  return (
    <Panel title="Quarterly trend" hint={
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
      {table && table.qs.length > 1 && (
        <div className="-mx-5 mt-3 overflow-x-auto">
          <table className="w-full min-w-[420px] text-[12.5px]">
            <thead className="text-[10.5px] font-extrabold uppercase tracking-[0.07em] text-ink-3">
              <tr><th className="px-5 py-1.5 text-left">₹ Cr</th>{table.qs.map((q) => <th key={q} className="num px-2 py-1.5 text-right last:pr-5">{quarterLabel(q)}</th>)}</tr>
            </thead>
            <tbody>
              {table.rows.flatMap(([label, m]) => [
                <tr key={label} className="border-t border-line">
                  <td className="px-5 py-1.5 font-bold text-ink-2">{label}</td>
                  {table.qs.map((q) => <td key={q} className="num px-2 py-1.5 text-right last:pr-5">{m.has(q) ? cr(m.get(q)).replace("₹", "").replace(/ Cr$/, "") : "—"}</td>)}
                </tr>,
                <tr key={`${label}-yoy`} className="border-t border-line">
                  <td className="px-5 py-1.5 font-bold text-ink-2">{label} YoY</td>
                  {table.qs.map((q) => <td key={q} className="num px-2 py-1.5 text-right last:pr-5"><Change value={table.yoy(m, q)} /></td>)}
                </tr>,
              ])}
            </tbody>
          </table>
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
  const one = now.find((r) => r.single);
  if (one) return <Panel title="Business mix" hint={`${latest} · from the results file`}><p className="text-[13.5px] text-ink-2">One segment{one.segment ? `: ${one.segment}` : ""}</p></Panel>;
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

/** The promise record in one number, with the latest few commitments and how they stand. */
function PromiseSummary({ dossier }: { dossier: Dossier | null }) {
  const guidance = dossier?.guidance ?? [];
  const s = promiseStats(guidance);
  if (!guidance.length) return null;
  const rate = s.resolved ? Math.round((s.delivered / s.resolved) * 100) : null;
  return (
    <Panel title="Promises kept">
      <div className="flex items-center gap-3.5">
        <span className={cn("text-[34px] font-extrabold leading-none tracking-tight", rate == null ? "text-ink-3" : rate >= 75 ? "text-pos" : rate < 50 ? "text-warn" : "text-ink")}>{rate == null ? "—" : `${rate}%`}</span>
        <span className="text-[13px] leading-snug text-ink-2">{s.resolved ? `${s.delivered} of ${s.resolved} commitments that came due were delivered` : "No commitment has come due yet"}; {s.open} open, checked against later filings.</span>
      </div>
      <ul className="mt-3 space-y-2">
        {[...guidance].reverse().slice(0, 4).map((g) => {
          const last = g.status_history[g.status_history.length - 1];
          return (
            <li key={g.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3 text-[13.5px]">
              <span className="line-clamp-2 text-ink">{short(g.statement, 90)}{g.due ? <span className="text-ink-3"> ({g.due})</span> : null}</span>
              <span className={cn("whitespace-nowrap rounded-full px-2.5 py-[3px] text-[11.5px] font-bold", STATUS_CHIP[g.status] ?? "bg-surface-2 text-ink-2")}>
                {titleCase(g.status)}{last && g.status !== "OPEN" ? ` · ${dayMonth(last.as_of)}` : ""}
              </span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

/** Dated events ahead, and the next results where last year's date says when they should come. */
function ComingUp({ dossier, expected }: { dossier: Dossier | null; expected?: Expected }) {
  const today = todayIST();
  const upcoming = (dossier?.upcoming_events ?? []).filter((e) => e.date >= today);
  // a generic entry beside a named event of the same day is the same event filed again
  const named = new Set(upcoming.filter((e) => !["OTHER", "MILESTONE"].includes(e.event_type)).map((e) => e.date));
  const events: { date: string; title: string; note?: string; approx?: boolean }[] = upcoming.filter((e, i) => !(["OTHER", "MILESTONE"].includes(e.event_type) && named.has(e.date))
      && upcoming.findIndex((x) => x.date === e.date && x.event_type === e.event_type) === i)
    .map((e) => ({ date: e.date, title: titleCase(e.event_type), note: e.description ? short(e.description, 90) : undefined }));
  if (expected && !upcoming.some((e) => e.event_type === "BOARD_MEETING" && /result/i.test(e.description))) {
    events.push({ date: expected.date, title: `${expected.period} results`, note: "expected from last year's date", approx: true });
  }
  events.sort((a, b) => a.date.localeCompare(b.date));
  if (!events.length) return null;
  return (
    <Panel title="Coming up">
      <ul className="space-y-2.5">
        {events.slice(0, 4).map((e, i) => {
          const [day, mon] = istDate(e.date).split(" ");
          return (
            <li key={i} className="grid grid-cols-[52px_minmax(0,1fr)] items-center gap-2.5 text-[13.5px]">
              <span className="num rounded-xl bg-accent-soft py-1.5 text-center text-[12px] font-extrabold leading-tight text-accent">{e.approx ? "~" : ""}{day}<span className="block text-[10px] font-bold uppercase">{mon}</span></span>
              <span className="text-ink">{e.title}{e.note ? <span className="block text-[12px] text-ink-3">{e.note}</span> : null}</span>
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
    <div className="space-y-4">
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
        <Institutions ownership={dossier?.ownership} />
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
                      <td className="rounded-l-xl px-2 py-2"><Link href={`${companyPath(pr)}`} className="font-bold text-ink hover:text-accent">{pr.symbol ?? pr.company_name}</Link></td>
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
    <IdentityAndOwnership dossier={dossier} />
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
