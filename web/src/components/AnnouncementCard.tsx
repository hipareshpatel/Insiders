import { toBlob } from "html-to-image";
import {
  AlertTriangle, ArrowDownRight, ArrowUpRight, BadgeCheck, Building2, Camera, Check, ChevronDown, ChevronRight, FileText, Gauge,
  Minus, RefreshCcw, Rocket, Scale, ShieldAlert, Timer,
} from "lucide-react";
import { useMemo, useRef, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { useLocation } from "wouter";
import type { CallRead, CardBody, CardRow, Impact, ResultLine, ResultsSnapshot, Signal } from "../../shared/types";
import { cn } from "../lib/cn";
import { cr, istDate, istDateTime, marketSession, pct, relativeTime, signClass, titleCase } from "../lib/format";
import { EVENT_LABELS, SECTORS, TONE_STRIPE, type Tone } from "../lib/taxonomy";
import { Avatar } from "./Avatar";
import { parseCard, QuantLine, SEVERITY_TEXT, SIGNAL, TrackItem } from "./FilingCard";
import { plain, RichText } from "./RichText";

const IMPACT_PILL: Record<Impact, string> = {
  HIGH: "bg-accent text-accent-ink",
  MODERATE: "bg-accent-soft text-accent",
  LOW: "border border-line text-ink-3",
};
const IMPACT_WORD: Record<Impact, string> = { HIGH: "High impact", MODERATE: "Moderate impact", LOW: "Low impact" };

export const STAGE_LABEL: Record<string, string> = {
  LOI: "LOI", LOA: "LOA", WORK_ORDER: "Work order", CONTRACT: "Contract", MOU: "MoU", DEVELOPMENT_ORDER: "Development order",
  PROPOSED: "Proposed", BOARD_APPROVED: "Board approved", TERMS_FINALISED: "Terms final", SHAREHOLDER_APPROVED: "Shareholder approved",
  IN_PROGRESS: "In progress", PARTIALLY_COMPLETED: "Partly complete", COMPLETED: "Completed", CANCELLED: "Cancelled",
};
/** Stages where nothing is firm yet: shown in amber. */
export const PROVISIONAL_STAGES = new Set(["LOI", "MOU", "DEVELOPMENT_ORDER", "PROPOSED", "BOARD_APPROVED", "CANCELLED"]);
const BASIS_LABEL: Record<string, string> = { CONSOLIDATED: "Consolidated", STANDALONE: "Standalone", PROFORMA: "Proforma" };
const INSIGHT_BASIS: Record<string, string> = { MEMORY: "memory", BALANCE_SHEET: "balance sheet", SECTOR: "peers", FILING: "filing" };

/** The box label follows the event, as an analyst would title it. */
function boxLabel(eventType: string): string {
  if (eventType === "RESULTS" || eventType === "MONTHLY_BUSINESS_UPDATE") return "What these numbers mean";
  return "Why it matters";
}

const SIGNAL_RANK: Record<string, number> = { WARNING: 0, POSITIVE: 1 };
const INFO_RANK: Record<string, number> = { SCALE: 0, ORDER_FLOW: 1, DILUTION: 2 };

/** What goes in the tinted box: up to four lines, the rest waits in "Full analysis". */
function boxItems(card: CardBody) {
  const signal = [...card.signals].sort((a, b) =>
    (SIGNAL_RANK[a.severity] ?? 2) - (SIGNAL_RANK[b.severity] ?? 2) || (INFO_RANK[a.type] ?? 9) - (INFO_RANK[b.type] ?? 9))[0];
  const missing = card.missing_disclosures[0];
  const room = Math.max(2, 4 - (signal ? 1 : 0) - (missing ? 1 : 0));
  const insights = card.why_it_matters.slice(0, room);
  return { insights, signal, missing, fallback: insights.length === 0 ? card.takeaway : undefined };
}

function Chip({ children, tone = "accent" }: { children: ReactNode; tone?: "accent" | "neutral" | "warn" }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-[3px] text-[11px] font-semibold uppercase tracking-[0.06em]",
      tone === "accent" ? "bg-accent-soft text-accent" : tone === "warn" ? "bg-warn-soft text-warn" : "bg-surface-2 text-ink-2")}>
      {children}
    </span>
  );
}

function Point({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <li className={cn("flex gap-2 text-[14.5px] leading-relaxed text-ink", className)}>
      <ChevronRight aria-hidden className="mt-[4px] h-4 w-4 shrink-0 text-accent" strokeWidth={2.5} />
      <span className="min-w-0">{children}</span>
    </li>
  );
}

const GUIDANCE: Record<CallRead["guidance"], { text: string; cls?: string }> = {
  RAISED: { text: "Raised", cls: "bg-pos-soft text-pos" }, LOWERED: { text: "Lowered", cls: "bg-neg-soft text-neg" },
  MAINTAINED: { text: "Same as last call" }, NEW: { text: "New" }, WITHDRAWN: { text: "Withdrawn", cls: "bg-neg-soft text-neg" },
  NONE: { text: "Not given" },
};

function CallReadChips({ read }: { read: CallRead }) {
  const items: { label: string; value: string; cls?: string }[] = [
    { label: "Guidance", value: GUIDANCE[read.guidance]?.text ?? titleCase(read.guidance), cls: GUIDANCE[read.guidance]?.cls },
    { label: "Tone", value: titleCase(read.management_tone) },
    { label: "Transparency", value: titleCase(read.transparency) },
    ...(read.story ? [{ label: "Story", value: titleCase(read.story) }] : []),
  ];
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {items.map((i) => (
        <span key={i.label} className={cn("inline-flex items-baseline gap-1.5 rounded-full px-3 py-1 text-[12.5px]", i.cls ?? "bg-surface-2 text-ink")}>
          <span className="text-[10px] font-semibold uppercase tracking-[0.08em] opacity-70">{i.label}</span>
          <span className="font-semibold">{i.value}</span>
        </span>
      ))}
    </div>
  );
}

function change(line: ResultLine | undefined, kind: "yoy" | "qoq", bps: boolean) {
  const v = bps ? line?.[`${kind}_bps`] : line?.[`${kind}_pct`];
  if (v == null) return <span className="text-ink-3">—</span>;
  return <span className={cn("font-semibold", signClass(v))}>{bps ? `${v > 0 ? "+" : ""}${v} bps` : pct(v)}</span>;
}

/** A small P&L for results cards: this quarter, YoY and QoQ, computed from memory rather than prose. */
function ResultsTable({ r }: { r: ResultsSnapshot }) {
  const rows = ([
    ["Revenue", r.revenue, false], ["EBITDA", r.ebitda, false], ["EBITDA margin", r.ebitda_margin, true], ["PAT", r.pat, false],
  ] as const).filter(([, line]) => line);
  if (rows.length < 2) return null;
  const qoq = rows.some(([, line, bps]) => (bps ? line?.qoq_bps : line?.qoq_pct) != null);
  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-line">
      <table className="num w-full text-[13px]">
        <thead className="bg-surface-2/60 text-ink-3">
          <tr>
            <th className="whitespace-nowrap px-2 py-1.5 sm:px-3 text-left text-[10.5px] font-semibold uppercase tracking-[0.08em]">₹ Cr</th>
            <th className="whitespace-nowrap px-2 py-1.5 sm:px-3 text-right text-[10.5px] font-semibold uppercase tracking-[0.08em]">{r.period}</th>
            <th className="whitespace-nowrap px-2 py-1.5 sm:px-3 text-right text-[10.5px] font-semibold uppercase tracking-[0.08em]">YoY</th>
            {qoq && <th className="whitespace-nowrap px-2 py-1.5 sm:px-3 text-right text-[10.5px] font-semibold uppercase tracking-[0.08em]">QoQ</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, line, bps]) => (
            <tr key={label} className="border-t border-line">
              <td className="whitespace-nowrap px-2 py-1.5 sm:px-3 font-medium text-ink">{label}</td>
              <td className="whitespace-nowrap px-2 py-1.5 sm:px-3 text-right font-semibold text-ink">
                {bps ? `${line!.value.toFixed(1)}%` : cr(line!.value).replace(/^₹| Cr$/g, "")}
              </td>
              <td className="whitespace-nowrap px-2 py-1.5 sm:px-3 text-right">{change(line, "yoy", bps)}</td>
              {qoq && <td className="whitespace-nowrap px-2 py-1.5 sm:px-3 text-right">{change(line, "qoq", bps)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** One health ratio for the footer: gross NPA for lenders, otherwise debt to equity. */
function healthMetric(card: CardBody): { label: string; value: string } | null {
  const f = card.fundamentals ?? {};
  if (f.gnpa_pct) return { label: "GNPA", value: `${f.gnpa_pct.value.toFixed(2)}%` };
  if (f.debt && f.net_worth && f.net_worth.value > 0) return { label: "D/E", value: `${(f.debt.value / f.net_worth.value).toFixed(2)}x` };
  if (f.net_worth && f.net_worth.value < 0) return { label: "Net worth", value: cr(f.net_worth.value) };
  return null;
}

/** A results bullet that only restates numbers already in the P&L table adds nothing; the card hides it. */
function coveredByTable(fact: string, r: ResultsSnapshot): boolean {
  const known: number[] = [];
  for (const line of [r.revenue, r.ebitda, r.ebitda_margin, r.pbt, r.pat, r.eps]) {
    if (!line) continue;
    for (const v of [line.value, line.prev_year, line.prev_quarter, line.yoy_pct, line.qoq_pct, line.yoy_bps, line.qoq_bps]) {
      if (v != null) known.push(Math.abs(v));
    }
  }
  const numbers = plain(fact).replace(/\b(?:Q[1-4]|H[12]|FY)\s*'?\d{2,4}\b|\b20\d{2}\b/gi, " ").match(/\d[\d,]*(?:\.\d+)?/g) ?? [];
  return numbers.length > 0 && numbers.every((raw) => {
    const n = Number(raw.replace(/,/g, ""));
    const rounding = raw.includes(".") ? 0.051 : 0.5; // "+30%" restates 29.6%
    return known.some((k) => Math.abs(k - n) <= Math.max(rounding, k * 0.006));
  });
}

function KeyTiles({ items }: { items: CardBody["key_numbers"] }) {
  return (
    <dl className="mt-3 grid grid-cols-2 overflow-hidden rounded-xl border border-line sm:grid-cols-4">
      {items.slice(0, 4).map((k, i) => (
        <div key={k.label} className={cn("px-3 py-2", i % 2 === 1 && "border-l border-line", i >= 2 && "border-t border-line sm:border-t-0", i >= 1 && "sm:border-l")}>
          <dt className="truncate text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-3">{k.label}</dt>
          <dd className="num mt-0.5 text-[15px] font-bold text-ink">{k.value}</dd>
          {k.change ? <dd className={cn("num text-[12px] font-semibold", k.change.trim().startsWith("-") || k.change.trim().startsWith("−") ? "text-neg" : "text-pos")}>{k.change}</dd> : null}
        </div>
      ))}
    </dl>
  );
}

function SignalLine({ s }: { s: Signal }) {
  const meta = SIGNAL[s.type];
  return (
    <>
      <span className={cn("font-semibold", SEVERITY_TEXT[s.severity])}>{meta?.label ?? titleCase(s.type)}:</span> {s.text}
      <span className="ml-1.5 inline-flex items-center gap-0.5 align-middle text-[10.5px] font-medium text-ink-3" title="Computed by code from the filing and memory, not written by the model">
        <Check className="h-3 w-3" />computed
      </span>
    </>
  );
}

/** One announcement as a self-contained card: what happened, why it matters, and the footer numbers. */
export function AnnouncementCard({ row, defaultOpen = false, highlight = false }: { row: CardRow; defaultOpen?: boolean; highlight?: boolean }) {
  const card = useMemo(() => parseCard(row), [row]);
  const [open, setOpen] = useState(defaultOpen);
  const [exporting, setExporting] = useState(false);
  const [copy, setCopy] = useState<"idle" | "copied" | "saved" | "error">("idle");
  const ref = useRef<HTMLElement>(null);
  const [, navigate] = useLocation();
  if (!card) return null;

  const tone = (card.tone ?? "NEUTRAL") as Tone;
  const event = card.event_type || row.event_category;
  const box = boxItems(card);
  const deal = card.deal_value;
  const stage = deal ? STAGE_LABEL[deal.stage] : undefined;
  const revenue = card.fundamentals?.revenue;
  const health = healthMetric(card);
  const review = !!row.needs_review;
  const issues = card.review?.issues?.length ? card.review.issues
    : [...(card.grounding.unsupported_claims ?? []).map((c) => `Claim not supported by the sources: "${c}"`),
       ...(card.grounding.ungrounded.length ? [`Numbers not found in the filing: ${card.grounding.ungrounded.join(", ")}`] : [])];
  const corrected = card.review?.status === "CORRECTED";
  const tilesFor = event === "CONCALL_PRESENTATION" || (event === "RESULTS" && !card.results);
  const table = event === "RESULTS" && card.results ? card.results : null;
  const facts = card.what_happened
    .filter((fact) => !(table && coveredByTable(fact, table)))
    .slice(0, event === "RESULTS" || event === "CONCALL_PRESENTATION" ? 4 : 3);

  async function share() {
    if (!ref.current) return;
    flushSync(() => setExporting(true));
    try {
      const bg = getComputedStyle(document.documentElement).getPropertyValue("--surface").trim() || "#ffffff";
      const blob = await toBlob(ref.current, {
        pixelRatio: 2, backgroundColor: bg,
        filter: (node) => !(node instanceof HTMLElement && node.dataset.noexport === "true"),
      });
      if (!blob) throw new Error("render failed");
      if (navigator.clipboard && "ClipboardItem" in window) {
        await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
        setCopy("copied");
      } else {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `${row.symbol ?? row.scrip_code}-${row.filing_date}.png`;
        a.click();
        setCopy("saved");
      }
    } catch {
      setCopy("error");
    } finally {
      setExporting(false);
      setTimeout(() => setCopy("idle"), 2000);
    }
  }

  return (
    <article ref={ref} id={`card-${row.news_id}`}
      className={cn("relative overflow-hidden rounded-2xl border bg-surface", highlight ? "border-accent-line ring-2 ring-accent-soft" : "border-line")}>
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-[3px]", TONE_STRIPE[tone])} />
      <div className="px-5 pb-4 pt-4 sm:px-6 sm:pt-5">
        {exporting && (
          <div className="mb-3 flex items-baseline justify-between text-[12px]">
            <span className="font-semibold text-accent">Insiders · BSE</span>
            <span className="num text-ink-3">{istDate(row.filed_at)}</span>
          </div>
        )}

        {review && !exporting && (
          <p className="-mt-1 mb-3 flex items-start gap-2 rounded-lg bg-warn-soft px-3 py-2 text-[12.5px] leading-relaxed text-warn" data-noexport="true">
            <AlertTriangle className="mt-[2px] h-3.5 w-3.5 shrink-0" />
            <span><span className="font-semibold">Unverified.</span> {issues[0] ?? "Some numbers could not be matched to the filing."}
              {card.review?.checked_by ? " A second AI could not resolve it." : ""} Check the official PDF before relying on it.</span>
          </p>
        )}

        <header className="flex items-start justify-between gap-3">
          <button type="button" onClick={() => navigate(`/company/${row.scrip_code}`)}
            className="group flex min-w-0 items-center gap-2 text-left" title={`${row.company_name} · BSE ${row.scrip_code}`}>
            <Avatar name={row.company_name} symbol={row.symbol} size={24} />
            <span className="flex min-w-0 flex-wrap items-baseline gap-x-2">
              <span className="text-[17px] font-bold tracking-tight text-ink group-hover:text-accent">{row.symbol ?? row.company_name}</span>
              {row.market_cap_cr != null && (
                <span className="num whitespace-nowrap text-[13px] text-ink-3">
                  {cr(row.market_cap_cr)}{row.size_category ? ` · ${titleCase(row.size_category)}cap` : ""}
                </span>
              )}
            </span>
          </button>
          <span className={cn("shrink-0 rounded-full px-3 py-1 text-[10.5px] font-bold uppercase tracking-[0.08em]", IMPACT_PILL[row.impact_level])}>
            {IMPACT_WORD[row.impact_level]}
          </span>
        </header>

        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <Chip>{EVENT_LABELS[event] ?? card.category_tag}</Chip>
          {(card.themes ?? []).map((t) => <Chip key={t}>{t}</Chip>)}
          {stage && <Chip tone={PROVISIONAL_STAGES.has(deal!.stage) ? "warn" : "neutral"}>{stage}</Chip>}
          {deal?.updates_deal_id && <Chip tone="neutral">Update to earlier deal</Chip>}
          {card.basis && <Chip tone="neutral">{BASIS_LABEL[card.basis] ?? card.basis}</Chip>}
        </div>

        <h3 className="mt-3 text-[19px] font-bold leading-snug tracking-[-0.01em] text-ink sm:text-[21px]">{plain(card.headline)}</h3>

        {card.call_read && <CallReadChips read={card.call_read} />}
        {event === "RESULTS" && card.results && <ResultsTable r={card.results} />}
        {tilesFor && card.key_numbers.length >= 2 && <KeyTiles items={card.key_numbers} />}

        <ul className="mt-3 space-y-2">
          {facts.map((fact, i) => (
            <Point key={i}><RichText text={fact} /></Point>
          ))}
        </ul>

        {(box.insights.length > 0 || box.signal || box.missing || box.fallback) && (
          <section className="mt-4 rounded-xl bg-accent-soft/70 px-4 py-3">
            <h4 className="text-[11px] font-bold uppercase tracking-[0.1em] text-accent">{boxLabel(event)}</h4>
            <ul className="mt-2 space-y-2">
              {box.fallback && <Point>{box.fallback}</Point>}
              {box.insights.map((insight, i) => <Point key={i}><RichText text={insight.text} /></Point>)}
              {box.signal && <Point><SignalLine s={box.signal} /></Point>}
              {box.missing && (
                <Point><span className="font-semibold text-warn">Not disclosed:</span> {box.missing}</Point>
              )}
            </ul>
          </section>
        )}

        <div className="num mt-4 flex flex-wrap items-baseline gap-x-4 gap-y-1 border-y border-line py-2 text-[13px] text-ink-3">
          {revenue && (
            <span><span className="font-bold text-ink">{cr(revenue.value)}</span> {revenue.period} revenue</span>
          )}
          {health && <span>{health.label} <span className="font-bold text-ink">{health.value}</span></span>}
          <span>1W <span className={cn("font-semibold", signClass(row.ret_1w))}>{pct(row.ret_1w)}</span></span>
          <span>1M <span className={cn("font-semibold", signClass(row.ret_1m))}>{pct(row.ret_1m)}</span></span>
          <span>1Y <span className={cn("font-semibold", signClass(row.ret_1y))}>{pct(row.ret_1y)}</span></span>
        </div>

        {exporting ? (
          <p className="mt-2 text-[10.5px] text-ink-3">AI summary of a public BSE filing. Not investment advice; verify against the original filing.</p>
        ) : (
          <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-2 text-[12px] text-ink-3" data-noexport="true">
            <span className="num" title={`${istDateTime(row.filed_at)} IST`}>{istDateTime(row.filed_at).replace(/ \d{4},/, ",")} · {relativeTime(row.filed_at)}</span>
            {review ? (
              <span className="inline-flex items-center gap-1 font-medium text-warn" title={issues.join(" · ")}>
                <AlertTriangle className="h-3.5 w-3.5" /> Unverified
              </span>
            ) : corrected ? (
              <span className="inline-flex items-center gap-1" title={`Corrected by ${card.review?.checked_by}: ${(card.review?.fixed ?? []).join(" · ")}`}>
                <RefreshCcw className="h-3.5 w-3.5 text-pos" /> Verified after a second check
              </span>
            ) : card.grounding.checked > 0 ? (
              <span className="inline-flex items-center gap-1" title="Every number was found in the filing or company memory">
                <BadgeCheck className="h-3.5 w-3.5 text-pos" /> Numbers verified
              </span>
            ) : null}
            <span className="ml-auto flex items-center gap-1">
              <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
                className="inline-flex h-8 items-center gap-1 rounded-lg px-2.5 text-[13px] font-medium text-accent hover:bg-accent-soft">
                Full analysis <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
              </button>
              {row.pdf_url && (
                <a href={row.pdf_url} target="_blank" rel="noreferrer" title={`Official PDF${card.pdf_pages ? ` (${card.pdf_pages} pages)` : ""}`}
                  aria-label="Official PDF" className="grid h-8 w-8 place-items-center rounded-lg text-ink-2 hover:bg-surface-2 hover:text-ink">
                  <FileText className="h-4 w-4" />
                </a>
              )}
              <button type="button" onClick={share} title="Copy card as image" aria-label="Copy card as image"
                className="grid h-8 w-8 place-items-center rounded-lg text-ink-2 hover:bg-surface-2 hover:text-ink">
                {copy === "idle" ? <Camera className="h-4 w-4" /> : copy === "error" ? <AlertTriangle className="h-4 w-4 text-warn" /> : <Check className="h-4 w-4 text-pos" />}
              </button>
              <button type="button" onClick={() => navigate(`/company/${row.scrip_code}`)} title="Company memory" aria-label="Company memory"
                className="grid h-8 w-8 place-items-center rounded-lg text-ink-2 hover:bg-surface-2 hover:text-ink">
                <Building2 className="h-4 w-4" />
              </button>
            </span>
          </div>
        )}
      </div>
      {open && !exporting && <DeepDive row={row} card={card} shown={box.insights.length} />}
    </article>
  );
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section>
      <h4 className="mb-2 text-[11px] font-bold uppercase tracking-[0.1em] text-ink-3">{label}</h4>
      {children}
    </section>
  );
}

/** Everything else the analysis produced: shown on demand, never in the share image. */
function DeepDive({ row, card, shown }: { row: CardRow; card: CardBody; shown: number }) {
  const more = card.why_it_matters.slice(shown);
  const quant = card.quantified_impact ?? [];
  const changes = card.notable_changes ?? [];
  const track = card.track_next;
  const trackItems = [
    { icon: Timer, label: "Milestone dates", items: (track?.milestones ?? []).map((m) => `${m.what}${m.when ? ` · ${m.when}` : ""}`) },
    { icon: Gauge, label: "KPI to verify", items: (track?.kpis_to_verify ?? []).map((k) => `${k.kpi}${k.target ? ` (target ${k.target})` : ""}${k.check_in ? ` · ${k.check_in}` : ""}`) },
    { icon: Scale, label: "Pending approvals", items: track?.pending_approvals ?? [] },
    { icon: Rocket, label: "Growth catalyst", items: track?.catalysts ?? [] },
    { icon: ShieldAlert, label: "Road blocker", items: track?.risks ?? [] },
  ].filter((t) => t.items.length > 0);
  const g = card.grounding;

  return (
    <div className="space-y-5 border-t border-line bg-surface-2/30 px-5 py-5 sm:px-6" data-noexport="true">
      <p className="num flex flex-wrap gap-x-2 text-[12px] text-ink-3">
        <span>{EVENT_LABELS[card.event_type || row.event_category] ?? card.category_tag}</span>
        {row.sector && row.sector !== "default" && <><span>·</span><span>{SECTORS[row.sector] ?? titleCase(row.sector)} lens</span></>}
        <span>·</span><span>BSE {row.scrip_code}</span>
        <span>·</span><span>{istDateTime(row.filed_at)} IST, {marketSession(row.filed_at).toLowerCase()}</span>
      </p>

      {(more.length > 0 || card.missing_disclosures.length > 1) && (
        <Section label="More context">
          <ul className="space-y-2">
            {more.map((i, k) => (
              <Point key={k}><RichText text={i.text} /> <span className="text-[11px] text-ink-3">· {INSIGHT_BASIS[i.basis] ?? i.basis}</span></Point>
            ))}
            {card.missing_disclosures.slice(1).map((m, k) => <Point key={`m${k}`}><span className="font-semibold text-warn">Not disclosed:</span> {m}</Point>)}
          </ul>
        </Section>
      )}

      {quant.length > 0 && (
        <Section label="Quantified impact">
          <ul className="space-y-2">{quant.map((q, i) => <QuantLine key={i} q={q} />)}</ul>
        </Section>
      )}

      {card.signals.length > 0 && (
        <Section label="Signals computed from memory">
          <ul className="space-y-2">{card.signals.map((s, i) => <Point key={i}><SignalLine s={s} /></Point>)}</ul>
        </Section>
      )}

      {changes.length > 0 && (
        <Section label="Notable changes">
          <ul className="divide-y divide-line border-y border-line">
            {changes.map((c, i) => {
              const Arrow = c.direction === "POSITIVE" ? ArrowUpRight : c.direction === "NEGATIVE" ? ArrowDownRight : Minus;
              const color = c.direction === "POSITIVE" ? "text-pos" : c.direction === "NEGATIVE" ? "text-neg" : "text-ink-3";
              return (
                <li key={i} className="grid gap-x-4 gap-y-0.5 py-2 text-[13.5px] sm:grid-cols-[minmax(0,1.3fr)_minmax(0,2fr)_auto_minmax(0,2.5fr)] sm:items-baseline">
                  <span className="font-medium text-ink"><Arrow className={cn("mr-1 inline h-3.5 w-3.5", color)} />{titleCase(c.metric)}</span>
                  <span className="num text-ink-2">{c.previous ?? "—"} → <span className="text-ink">{c.current ?? "—"}</span></span>
                  <span className={cn("num font-semibold", color)}>{c.change ?? ""}</span>
                  <span className="text-ink-2">{c.why}</span>
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      <Section label="What to track next">
        {trackItems.length ? (
          <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">{trackItems.map((t) => <TrackItem key={t.label} {...t} />)}</dl>
        ) : <p className="text-[13.5px] text-ink-3">Nothing dated, pending or at risk in this filing.</p>}
      </Section>

      {card.review && (
        <Section label="Second check">
          <p className="text-[13px] leading-relaxed text-ink-2">
            The first draft{card.review.first_model ? ` (${card.review.first_model})` : ""} failed the automatic checks
            {card.review.checked_by ? `, so ${card.review.checked_by} was asked to correct it` : ", and no second AI was available"}.
            {card.review.status === "CORRECTED" ? " The corrected card passed every check." : " Problems that remain are listed below."}
          </p>
          <ul className="mt-2 space-y-1">
            {(card.review.status === "CORRECTED" ? card.review.fixed ?? [] : card.review.issues ?? []).map((p, i) => (
              <li key={i} className={cn("text-[12.5px]", card.review!.status === "CORRECTED" ? "text-ink-3 line-through" : "text-warn")}>{p}</li>
            ))}
          </ul>
        </Section>
      )}

      <p className="text-[12px] leading-relaxed text-ink-3">
        {g.checked > 0 ? `${g.checked} numbers checked against the filing and company memory` : "No numbers to check"}
        {g.ungrounded.length ? `; not found: ${g.ungrounded.join(", ")}` : ""}
        {g.unsupported_claims?.length ? `. Claims the sources don't support: ${g.unsupported_claims.map((c) => `"${c}"`).join(", ")}` : ""}
        {!row.memory_complete ? ". Written before this company's history finished loading" : ""}.
        {" "}AI summary of a public BSE filing; not investment advice.
      </p>
    </div>
  );
}
