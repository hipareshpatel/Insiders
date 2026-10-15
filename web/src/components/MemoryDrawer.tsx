import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, X } from "lucide-react";
import { Fragment, type ReactNode } from "react";
import { Link } from "wouter";
import type { CardBody, CardRow, PriceReaction, Roiic } from "../../shared/types";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { istDate, istDateTime, rupees, titleCase } from "../lib/format";
import { EVENT_LABELS, SECTORS } from "../lib/taxonomy";
import { useQueryState } from "../lib/url";
import { DealsAndNotes, IdentityAndOwnership, MetricsPanel, Panel, promiseStats } from "../views/CompanyPage";
import { Empty, Loading } from "../views/FeedView";
import { Avatar } from "./Avatar";
import { parseCard } from "./FilingCard";
import { TabStrip } from "./ui/badge";

/**
 * The 360° memory drawer (blueprint §13.3): opens over any page from `?memory=<scrip>` (and
 * `&verify=<news_id>` for the PDF check), so the feed keeps its scroll position and the view is
 * linkable. Tabs: the living dossier, the event timeline with the market's reaction, and the
 * official PDF beside the card with every figure marked as found in the filing or not.
 */
export function MemoryDrawer() {
  const [params, setParams] = useQueryState();
  const scrip = params.get("memory");
  const verify = params.get("verify");
  const tab = params.get("mtab") ?? (verify ? "verify" : "dossier");
  const close = () => setParams({ memory: null, verify: null, mtab: null });
  return (
    <Dialog.Root open={!!scrip} onOpenChange={(open) => !open && close()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30 data-[state=open]:animate-in" />
        <Dialog.Content
          className={cn("fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-line bg-bg shadow-2xl focus:outline-none",
            tab === "verify" ? "max-w-[1200px]" : "max-w-[720px]")}
          aria-describedby={undefined}>
          {scrip && <DrawerBody scrip={scrip} verify={verify} tab={tab} onTab={(t) => setParams({ mtab: t })} onClose={close} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function DrawerBody({ scrip, verify, tab, onTab, onClose }: {
  scrip: string; verify: string | null; tab: string; onTab: (t: string) => void; onClose: () => void;
}) {
  const query = useQuery({ queryKey: ["company", scrip], queryFn: () => api.company(scrip) });
  const company = query.data?.company ?? null;
  const dossier = query.data?.dossier ?? null;
  const cards = query.data?.cards ?? [];
  const name = company?.company_name ?? dossier?.company_name ?? scrip;
  const symbol = company?.symbol ?? dossier?.symbol ?? null;
  const tabs = [
    { key: "dossier", label: "Living dossier" },
    { key: "timeline", label: "Timeline", count: dossier?.timeline?.length },
    ...(verify ? [{ key: "verify", label: "Verify against the PDF" }] : []),
  ];
  return (
    <>
      <header className="flex items-start gap-3 border-b border-line px-5 py-4">
        <Avatar name={name} symbol={symbol} size={32} />
        <div className="min-w-0 flex-1">
          <Dialog.Title className="font-display text-[22px] leading-tight text-ink">{symbol ?? name}</Dialog.Title>
          <p className="truncate text-[13px] text-ink-2">
            {name} · BSE {scrip}
            {company?.sector ? ` · ${SECTORS[company.sector] ?? titleCase(company.sector)}` : ""}
            {company?.median_turnover_cr != null ? ` · 💧 ₹${company.median_turnover_cr.toFixed(2)} Cr/day` : ""}
          </p>
        </div>
        <Link href={`/company/${scrip}`} className="mt-1 inline-flex items-center gap-1 text-[12.5px] text-accent hover:underline">
          Full page <ExternalLink className="h-3.5 w-3.5" />
        </Link>
        <Dialog.Close className="grid h-8 w-8 place-items-center rounded-lg text-ink-2 hover:bg-surface-2" aria-label="Close">
          <X className="h-4 w-4" />
        </Dialog.Close>
      </header>
      <TabStrip className="px-5" items={tabs} value={tab} onChange={onTab} />
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4" onKeyDown={(e) => e.key === "Escape" && onClose()}>
        {query.isPending ? <Loading /> : query.isError ? <Empty title="Couldn't load this company" body={String(query.error)} /> : (
          <>
            {tab === "dossier" && (
              <div className="space-y-4">
                <Scorecard guidance={dossier?.guidance ?? []} credibility={company?.credibility_score ?? null} rule={company?.calibration_rule ?? null}
                  roiic={parseRoiic(company?.roiic)} />
                <IdentityAndOwnership dossier={dossier} />
                {dossier ? <MetricsPanel dossier={dossier} /> : <Empty title="No financials in memory yet" />}
                <DealsAndNotes dossier={dossier} />
              </div>
            )}
            {tab === "timeline" && <ReactionTimeline dossier={dossier} cards={cards} />}
            {tab === "verify" && verify && <Verifier row={cards.find((c) => c.news_id === verify) ?? null} newsId={verify} />}
          </>
        )}
      </div>
    </>
  );
}

/** Delivered vs open vs broken promises as one bar. */
function parseRoiic(raw: string | null | undefined): Roiic | null {
  try { return raw ? (JSON.parse(raw) as Roiic) : null; } catch { return null; }
}

const ROIIC_VERDICT: Record<NonNullable<Roiic["verdict"]>, { text: string; tone: string }> = {
  COMPOUNDER: { text: "Capital compounder", tone: "text-pos" },
  DILUTER: { text: "Capital diluter", tone: "text-neg" },
  SELF_FUNDED: { text: "Self-funded growth", tone: "text-pos" },
};

function Scorecard({ guidance, credibility, rule, roiic }: { guidance: NonNullable<Parameters<typeof promiseStats>[0]>; credibility: number | null; rule: string | null; roiic: Roiic | null }) {
  const s = promiseStats(guidance);
  const total = s.delivered + s.open + s.missed;
  if (!total && !rule && !roiic) return null;
  const width = (n: number) => `${(n / total) * 100}%`;
  return (
    <Panel title="Management execution" hint={credibility != null ? `Credibility ${Math.round(credibility)}%` : undefined}>
      {total > 0 && <>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-surface-2" role="img"
        aria-label={`${s.delivered} delivered, ${s.open} open, ${s.missed} missed or revised`}>
        <span className="bg-pos" style={{ width: width(s.delivered) }} />
        <span className="bg-info" style={{ width: width(s.open) }} />
        <span className="bg-neg" style={{ width: width(s.missed) }} />
      </div>
      <p className="num mt-2 text-[12.5px] text-ink-2">
        <span className="text-pos">● {s.delivered} delivered</span> · <span className="text-info">● {s.open} open</span> ·{" "}
        <span className="text-neg">● {s.missed} missed, delayed or withdrawn</span>
      </p>
      </>}
      {rule && <p className="mt-2 rounded-lg bg-insight px-3 py-2 text-[13px] text-insight-ink">📐 {rule}</p>}
      {roiic && (
        <p className="num mt-2 text-[12.5px] text-ink-2">
          {roiic.verdict && <span className={cn("font-semibold", ROIIC_VERDICT[roiic.verdict].tone)}>{ROIIC_VERDICT[roiic.verdict].text} · </span>}
          {roiic.from} → {roiic.to}: EBITDA run-rate {roiic.ebitda_added_cr >= 0 ? "+" : ""}{rupees(roiic.ebitda_added_cr)} Cr on {rupees(roiic.capital_added_cr)} Cr of capital added
          {roiic.pct != null && <> (ROIIC {Math.round(roiic.pct)}%)</>}
        </p>
      )}
    </Panel>
  );
}

function reactionOf(row: CardRow | undefined): PriceReaction | null {
  try {
    return row?.post_event_return_json ? (JSON.parse(row.post_event_return_json) as PriceReaction) : null;
  } catch {
    return null;
  }
}

function move(v: number | undefined) {
  if (v === undefined) return null;
  return <span className={v > 0 ? "text-pos" : v < 0 ? "text-neg" : "text-ink-2"}>{v > 0 ? "+" : ""}{v.toFixed(1)}%</span>;
}

/** Every material filing since the history start, with T+1 / T+3 against the index. */
function ReactionTimeline({ dossier, cards }: { dossier: Awaited<ReturnType<typeof api.company>>["dossier"]; cards: CardRow[] }) {
  const events = [...(dossier?.timeline ?? [])].reverse();
  const byId = new Map(cards.map((c) => [c.news_id, c]));
  if (!events.length) return <Empty title="No events recorded yet" />;
  return (
    <ol className="relative ml-1.5 border-l border-line">
      {events.map((e) => {
        const rx = reactionOf(byId.get(e.news_id));
        const t1 = rx?.t1?.excess_pct ?? rx?.t1?.return_pct;
        const t3 = rx?.t3?.excess_pct ?? rx?.t3?.return_pct;
        return (
          <li key={e.id} className="relative ml-5 pb-5 last:pb-0">
            <span className={cn("absolute -left-[26px] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-bg",
              e.impact_level === "HIGH" ? "bg-accent" : "bg-line-strong")} />
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="num text-ink-3">{istDate(e.date)}</span>
              <span className="rounded bg-surface-2 px-1.5 py-0.5 text-ink-2">{EVENT_LABELS[e.event_type] ?? e.event_type}</span>
              {e.impact_level === "HIGH" && <span className="font-semibold text-ink">High impact</span>}
              {rx && (t1 !== undefined || t3 !== undefined) && (
                <span className="num text-ink-3">T+1 {move(t1) ?? "–"} · T+3 {move(t3) ?? "–"}{rx.benchmark ? " vs index" : ""}</span>
              )}
            </div>
            <p className="mt-1 text-[14px] leading-relaxed text-ink">{e.summary}</p>
          </li>
        );
      })}
    </ol>
  );
}

const NUMBER = /(?:₹\s?)?[-−]?\d[\d,]*(?:\.\d+)?\s?(?:%|bps|x|Cr|crore|lakh|MW|TPD|MTPA)?/g;

/** Card text with each figure marked: green when it was found in the filing, amber when not.
 * Spans wrapped in ** are bold, as on the card. */
function Marked({ text, ungrounded }: { text: string; ungrounded: Set<string> }) {
  const spans = text.split("**");
  if (spans.length > 1) {
    return <>{spans.map((s, i) => (i % 2 ? <strong key={i}><MarkedPlain text={s} ungrounded={ungrounded} /></strong>
      : <MarkedPlain key={i} text={s} ungrounded={ungrounded} />))}</>;
  }
  return <MarkedPlain text={text} ungrounded={ungrounded} />;
}

function MarkedPlain({ text, ungrounded }: { text: string; ungrounded: Set<string> }) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(NUMBER)) {
    const raw = m[0].trim();
    if (!/\d/.test(raw) || /^\d{1,2}$/.test(raw)) continue; // bare small integers are not checked
    const at = m.index ?? 0;
    parts.push(text.slice(last, at));
    const bad = [...ungrounded].some((u) => u.includes(raw.replace(/[₹\s]/g, "")) || raw.includes(u));
    parts.push(
      <mark key={at} className={cn("rounded px-0.5", bad ? "bg-warn-soft text-warn" : "bg-pos-soft text-pos")}
        title={bad ? "Not found in the filing" : "Found in the filing"}>{m[0]}</mark>,
    );
    last = at + m[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts.map((p, i) => <Fragment key={i}>{p}</Fragment>)}</>;
}

/** Split screen: the official BSE PDF beside the card's figures and the math working. */
function Verifier({ row, newsId }: { row: CardRow | null; newsId: string }) {
  const card: CardBody | null = row ? parseCard(row) : null;
  if (!row || !card) return <Empty title="This card is not in the company's last 60 filings" body={newsId} />;
  const ungrounded = new Set(card.grounding?.ungrounded ?? []);
  const lines = [card.headline, ...(card.what_happened ?? []), ...(card.why_it_matters ?? []).map((w) => w.text)];
  return (
    <div className="grid h-full gap-4 lg:grid-cols-2">
      <section className="flex min-h-[60vh] flex-col overflow-hidden rounded-xl border border-line bg-surface">
        <header className="flex items-center justify-between gap-2 border-b border-line px-3 py-2 text-[12.5px] text-ink-2">
          <span>Official filing · {istDateTime(row.filed_at)}</span>
          {row.pdf_url && (
            <a href={row.pdf_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline">
              Open on BSE <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </header>
        {row.pdf_url ? (
          <iframe src={row.pdf_url} title="Official BSE filing" className="min-h-[60vh] w-full flex-1 bg-white" />
        ) : (
          <Empty title="No PDF attached to this filing" />
        )}
        <p className="border-t border-line px-3 py-1.5 text-[11px] text-ink-3">
          If BSE does not allow the PDF to show here, use "Open on BSE".
        </p>
      </section>
      <section className="space-y-4">
        <Panel title="The card's figures"
          hint={`${card.grounding?.checked ?? 0} figures checked · ${ungrounded.size} not found`}>
          <ul className="space-y-2 text-[14px] leading-relaxed text-ink">
            {lines.filter(Boolean).map((l, i) => (
              <li key={i} className={i === 0 ? "font-semibold" : ""}><Marked text={l} ungrounded={ungrounded} /></li>
            ))}
          </ul>
          {ungrounded.size > 0 && (
            <p className="mt-3 text-[12.5px] text-warn">Not found in the filing: {[...ungrounded].join(", ")}</p>
          )}
          {(card.grounding?.unsupported_claims ?? []).length > 0 && (
            <p className="mt-1 text-[12.5px] text-warn">Claims without support: {card.grounding!.unsupported_claims!.join("; ")}</p>
          )}
          {card.xbrl && (
            <p className="mt-2 text-[12.5px] text-ink-3">
              Results figures in memory come from the filing's XBRL file ({card.xbrl.basis?.toLowerCase() ?? "basis not stated"}, {card.xbrl.period}).
            </p>
          )}
        </Panel>
        {(card.quantified_impact ?? []).length > 0 && (
          <Panel title="Math working" hint="recomputed by code from the stated inputs">
            <div className="space-y-3">
              {(card.quantified_impact ?? []).map((q, i) => (
                <div key={i} className="rounded-lg border border-line p-3 text-[13px]">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-semibold text-ink">{q.label}</span>
                    <span className={cn("text-xs font-semibold", q.check === "VERIFIED" ? "text-pos" : q.check === "MISMATCH" ? "text-neg" : "text-ink-3")}>
                      {q.check === "VERIFIED" ? "✓ Recomputed" : q.check === "MISMATCH" ? `✗ Code got ${q.computed ?? "?"}` : "Not checked"}
                    </span>
                  </div>
                  <code className="num mt-1 block break-words text-[12px] text-ink-2">{q.formula}</code>
                  <table className="num mt-2 w-full text-[12px]">
                    <tbody>
                      {q.inputs.map((input) => (
                        <tr key={input.name} className="border-t border-line">
                          <td className="py-1 pr-2 text-ink-2">{input.name}</td>
                          <td className="py-1 pr-2 text-ink">{input.value ?? "–"} {input.unit}</td>
                          <td className={cn("py-1 text-right", input.source === "ASSUMPTION" ? "text-warn" : "text-ink-3")}>{titleCase(input.source)}</td>
                        </tr>
                      ))}
                      <tr className="border-t border-line font-semibold">
                        <td className="py-1 pr-2 text-ink">Result</td>
                        <td className="py-1 pr-2 text-ink" colSpan={2}>{q.unit === "INR_CR" && q.result != null ? `₹${q.result} Cr` : `${q.result ?? "–"} ${q.unit}`}</td>
                      </tr>
                    </tbody>
                  </table>
                  {q.check_note && <p className="mt-1 text-[12px] text-ink-3">{q.check_note}</p>}
                </div>
              ))}
            </div>
          </Panel>
        )}
        {card.priced_at_filing?.last_price !== undefined && (
          <p className="num text-[12.5px] text-ink-3">
            Price at filing ({card.priced_at_filing.price_date}): {rupees(card.priced_at_filing.last_price)}
          </p>
        )}
      </section>
    </div>
  );
}
