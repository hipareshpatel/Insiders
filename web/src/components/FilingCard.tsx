import {
  AlertTriangle, ArrowDownRight, ArrowUpRight, BadgeCheck, Calculator, Camera, CheckCircle2, ChevronDown, FileText,
  FolderOpen, Gauge, Layers, ListChecks, Minus, Rocket, Ruler, Scale, ShieldAlert, Timer,
} from "lucide-react";
import { useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation } from "wouter";
import type { CardBody, CardRow, Insight, QuantifiedImpact, Signal } from "../../shared/types";
import { cn } from "../lib/cn";
import { cr, exact, formatKpi, istDateTime, marketSession, pct, quantValue, relativeTime, signClass, titleCase } from "../lib/format";
import { copyNodeAsPng } from "../lib/png";
import { EVENT_LABELS, IMPACT_LABEL, IMPACT_TEXT, SECTORS, TONE_STRIPE, type Tone } from "../lib/taxonomy";
import { TickerChip } from "./Avatar";
import { plain, RichText } from "./RichText";

export function parseCard(row: CardRow): CardBody | null {
  try {
    return JSON.parse(row.card_json) as CardBody;
  } catch {
    return null;
  }
}

const BASIS_LABEL: Record<Insight["basis"], string> = {
  MEMORY: "Memory link",
  BALANCE_SHEET: "Balance sheet",
  SECTOR: "Peer context",
  FILING: "Filing",
};

export const SIGNAL: Record<Signal["type"], { label: string; icon: typeof Gauge }> = {
  PROMISE_DELIVERED: { label: "Promise delivered", icon: CheckCircle2 },
  GUIDANCE_BREACH: { label: "Guidance breach", icon: ShieldAlert },
  WATCH_RESOLVED: { label: "Follow-up", icon: ListChecks },
  DILUTION: { label: "Dilution", icon: Scale },
  SCALE: { label: "Scale", icon: Ruler },
  ORDER_FLOW: { label: "Order flow", icon: Layers },
  WORKING_CAPITAL_STRAIN: { label: "Working capital", icon: AlertTriangle },
  METRIC_SHIFT: { label: "Metric shift", icon: Gauge },
  BOARD_DELIBERATION: { label: "Long board meeting", icon: Timer },
  REG30_THRESHOLD: { label: "Reg 30 materiality", icon: Scale },
};
export const SEVERITY_TEXT: Record<Signal["severity"], string> = { POSITIVE: "text-pos", WARNING: "text-warn", INFO: "text-info" };

/** One filing in a list: a compact row that expands into the full card. */
export function FilingRow({ row, defaultOpen = false, highlight = false }: { row: CardRow; defaultOpen?: boolean; highlight?: boolean }) {
  const card = useMemo(() => parseCard(row), [row]);
  const [open, setOpen] = useState(defaultOpen);
  const [, navigate] = useLocation();
  if (!card) return null;
  const tone = (card.tone ?? "NEUTRAL") as Tone;
  const warnings = card.signals.filter((s) => s.severity === "WARNING").length;
  const positives = card.signals.filter((s) => s.severity === "POSITIVE").length;

  return (
    <article id={`card-${row.news_id}`}
      className={cn("relative overflow-hidden rounded-xl border bg-surface transition-colors",
        highlight ? "border-accent-line" : "border-line", !open && "hover:border-line-strong")}>
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-[3px]", TONE_STRIPE[tone])} />
      {/* The whole header toggles; the headline is the accessible toggle button. */}
      <div onClick={() => setOpen((v) => !v)} className="cursor-pointer px-4 py-3.5 pl-5 sm:px-5 sm:pl-6">
        <div className="flex items-start gap-4">
          <h3 className="min-w-0 flex-1 text-[15px] font-medium leading-snug text-ink">
            <button type="button" aria-expanded={open} onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
              className="text-left hover:text-accent focus-visible:text-accent">
              {plain(card.headline)}
            </button>
          </h3>
          <span className="flex shrink-0 items-center gap-2 pt-0.5" data-noexport="true">
            <span className={cn("eyebrow hidden sm:inline", IMPACT_TEXT[row.impact_level])}>{IMPACT_LABEL[row.impact_level]}</span>
            <ChevronDown aria-hidden className={cn("h-4 w-4 text-ink-3 transition-transform", open && "rotate-180")} />
          </span>
        </div>
        {card.takeaway && !open ? (
          <p className="mt-1 line-clamp-2 text-[13.5px] leading-relaxed text-ink-2 sm:line-clamp-1">{card.takeaway}</p>
        ) : null}
        <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-xs text-ink-3">
          <TickerChip name={row.company_name} symbol={row.symbol} scrip={row.scrip_code} onClick={() => navigate(`/company/${row.scrip_code}`)} />
          <span className="hidden text-ink-2 sm:inline">{row.company_name}</span>
          {row.market_cap_cr != null && (
            <span className="num">{cr(row.market_cap_cr)}{row.size_category ? ` · ${titleCase(row.size_category)}cap` : ""}</span>
          )}
          <span>{EVENT_LABELS[row.event_category] ?? card.category_tag}</span>
          <span className="num" title={istDateTime(row.filed_at)}>{istDateTime(row.filed_at).split(", ").pop()} · {relativeTime(row.filed_at)}</span>
          <span className="sm:hidden">· {IMPACT_LABEL[row.impact_level]}</span>
          {positives > 0 && <span className="inline-flex items-center gap-1 text-pos"><CheckCircle2 className="h-3.5 w-3.5" />{positives}</span>}
          {warnings > 0 && <span className="inline-flex items-center gap-1 text-warn"><AlertTriangle className="h-3.5 w-3.5" />{warnings}</span>}
        </div>
      </div>
      {open && <FilingBody row={row} card={card} />}
    </article>
  );
}

function Section({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <section className={className}>
      <h4 className="eyebrow mb-2 text-accent">{label}</h4>
      {children}
    </section>
  );
}

function Bullet({ children }: { children: ReactNode }) {
  return (
    <li className="flex gap-2.5 text-[14px] leading-relaxed text-ink">
      <span aria-hidden className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-ink-3" />
      <span className="min-w-0">{children}</span>
    </li>
  );
}

/** The expanded card, in the order an analyst reads it. */
export function FilingBody({ row, card, showHeadline = false }: { row: CardRow; card: CardBody; showHeadline?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const [, navigate] = useLocation();
  const [copy, setCopy] = useState<"idle" | "copied" | "saved" | "error">("idle");
  const track = card.track_next;
  const changes = card.notable_changes ?? [];
  const quant = card.quantified_impact ?? [];
  const f = card.fundamentals ?? {};
  const trackItems = [
    { icon: Timer, label: "Milestone dates", items: (track?.milestones ?? []).map((m) => `${m.what}${m.when ? ` · ${m.when}` : ""}`) },
    { icon: Gauge, label: "KPI to verify", items: (track?.kpis_to_verify ?? []).map((k) => `${k.kpi}${k.target ? ` (target ${k.target})` : ""}${k.check_in ? ` · ${k.check_in}` : ""}`) },
    { icon: Scale, label: "Pending approvals", items: track?.pending_approvals ?? [] },
    { icon: Rocket, label: "Growth catalyst", items: track?.catalysts ?? [] },
    { icon: ShieldAlert, label: "Invalidation risk", items: track?.risks ?? [] },
  ].filter((t) => t.items.length > 0);
  // In a feed row the headline is already on screen, so the catalyst line carries the takeaway instead.
  const catalyst = plain(showHeadline || !card.takeaway ? card.headline : card.takeaway);

  async function copyPng() {
    // Export the whole card (header included) when it sits in a feed row, so the PNG stands alone.
    const target = (ref.current?.closest("article") as HTMLElement | null) ?? ref.current;
    if (!target) return;
    try {
      setCopy(await copyNodeAsPng(target, `${row.symbol ?? row.scrip_code}-${row.filing_date}.png`));
    } catch {
      setCopy("error");
    }
    setTimeout(() => setCopy("idle"), 2000);
  }

  return (
    <div ref={ref} className="border-t border-line bg-surface px-4 pb-4 pt-4 pl-5 sm:px-6 sm:pl-6">
      {/* Telemetry: what the row header doesn't already say */}
      <div className="num flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-3">
        {showHeadline && <><span className={cn("eyebrow", IMPACT_TEXT[row.impact_level])}>{IMPACT_LABEL[row.impact_level]}</span><span>·</span></>}
        <span className="font-medium text-ink-2">{card.category_tag || EVENT_LABELS[row.event_category]}</span>
        {row.sector && row.sector !== "default" && <><span>·</span><span>{SECTORS[row.sector] ?? titleCase(row.sector)} lens</span></>}
        <span>·</span>
        <span>BSE {row.scrip_code}</span>
        <span className="sm:ml-auto">{istDateTime(row.filed_at)} IST · {marketSession(row.filed_at)}</span>
      </div>

      <div className="mt-3">
        <h4 className="eyebrow text-accent">Core catalyst</h4>
        <p className="mt-1 font-display text-[21px] leading-snug text-ink">{catalyst}</p>
        {showHeadline && card.takeaway ? <p className="mt-1 text-[14px] leading-relaxed text-ink-2">{card.takeaway}</p> : null}
        {card.key_numbers.length > 0 && (
          <dl className="num mt-3 flex flex-wrap gap-x-6 gap-y-2">
            {card.key_numbers.slice(0, 6).map((k) => (
              <div key={k.label}>
                <dt className="eyebrow text-ink-3">{k.label}</dt>
                <dd className="text-[15px] font-semibold text-ink">
                  {k.value}
                  {k.change ? <span className={cn("ml-1.5 text-[13px] font-medium", k.change.trim().startsWith("-") || k.change.trim().startsWith("−") ? "text-neg" : "text-pos")}>{k.change}</span> : null}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>

      <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <Section label="What happened · the facts">
          <ul className="space-y-1.5">{card.what_happened.map((fact, i) => <Bullet key={i}><RichText text={fact} /></Bullet>)}</ul>
        </Section>
        <Section label="Why it matters · memory & forensics">
          <ul className="space-y-2">
            {card.why_it_matters.map((insight, i) => (
              <Bullet key={i}>
                <span className="font-semibold text-accent">[{BASIS_LABEL[insight.basis] ?? insight.basis}]</span> <RichText text={insight.text} />
              </Bullet>
            ))}
            {quant.map((q, i) => <QuantLine key={`q${i}`} q={q} />)}
            {card.missing_disclosures.map((m, i) => (
              <Bullet key={`m${i}`}>
                <span className="font-semibold text-warn">[⚠ Missing disclosure]</span> {m}
              </Bullet>
            ))}
            {card.why_it_matters.length + quant.length + card.missing_disclosures.length === 0 && (
              <li className="text-sm text-ink-3">No memory links for this filing yet.</li>
            )}
          </ul>
        </Section>
      </div>

      {card.signals.length > 0 && (
        <Section label="Signals" className="mt-5">
          <ul className="space-y-1.5">
            {card.signals.map((s, i) => {
              const meta = SIGNAL[s.type];
              const Icon = meta?.icon ?? Gauge;
              return (
                <li key={i} className="flex gap-2.5 text-[14px] leading-relaxed text-ink">
                  <Icon className={cn("mt-[3px] h-4 w-4 shrink-0", SEVERITY_TEXT[s.severity])} />
                  <span><span className={cn("font-semibold", SEVERITY_TEXT[s.severity])}>{meta?.label ?? titleCase(s.type)}:</span> {s.text}</span>
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      {changes.length > 0 && (
        <Section label="Notable changes" className="mt-5">
          <ul className="divide-y divide-line border-y border-line">
            {changes.map((c, i) => {
              const Arrow = c.direction === "POSITIVE" ? ArrowUpRight : c.direction === "NEGATIVE" ? ArrowDownRight : Minus;
              const tone = c.direction === "POSITIVE" ? "text-pos" : c.direction === "NEGATIVE" ? "text-neg" : "text-ink-3";
              return (
                <li key={i} className="grid gap-x-4 gap-y-0.5 py-2 text-[13.5px] sm:grid-cols-[minmax(0,1.3fr)_minmax(0,2fr)_auto_minmax(0,2.5fr)] sm:items-baseline">
                  <span className="font-medium text-ink"><Arrow className={cn("mr-1 inline h-3.5 w-3.5", tone)} />{titleCase(c.metric)}</span>
                  <span className="num text-ink-2">{c.previous ?? "—"} → <span className="text-ink">{c.current ?? "—"}</span></span>
                  <span className={cn("num font-semibold", tone)}>{c.change ?? ""}</span>
                  <span className="text-ink-2">{c.why}</span>
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      <Section label="What to track next" className="mt-5">
        {trackItems.length ? (
          <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
            {trackItems.map((t) => <TrackItem key={t.label} {...t} />)}
          </dl>
        ) : <p className="text-[13.5px] text-ink-3">Nothing dated, pending or at risk in this filing.</p>}
      </Section>

      <div className="num mt-5 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-3 text-[13px] text-ink-3">
        <span className="eyebrow text-ink-3">Financial footer</span>
        {f.revenue && <span>{f.revenue.period} Rev <span className="font-semibold text-ink">{cr(f.revenue.value)}</span></span>}
        {f.debt && <span>Debt <span className="font-semibold text-ink">{cr(f.debt.value)}</span></span>}
        {f.net_worth && <span>Net worth <span className={cn("font-semibold", f.net_worth.value < 0 ? "text-neg" : "text-ink")}>{cr(f.net_worth.value)}</span></span>}
        {row.market_cap_cr != null && <span>MCap <span className="font-semibold text-ink">{cr(row.market_cap_cr)}</span></span>}
        {(f.kpis ?? []).map((k) => (
          <span key={k.label}>{k.label} <span className="font-semibold text-ink">{formatKpi(k)}</span></span>
        ))}
        <span>1W <span className={signClass(row.ret_1w)}>{pct(row.ret_1w)}</span></span>
        <span>1M <span className={signClass(row.ret_1m)}>{pct(row.ret_1m)}</span></span>
        <span>1Y <span className={signClass(row.ret_1y)}>{pct(row.ret_1y)}</span></span>
      </div>

      {row.needs_review ? (
        <p className="mt-3 flex items-center gap-1.5 text-[12px] font-medium text-warn">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> Unverified: some figures could not be matched to the filing. Check the official PDF.
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2" data-noexport="true">
        {row.pdf_url && (
          <a href={row.pdf_url} target="_blank" rel="noreferrer"
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line px-3 text-[13px] font-medium text-ink hover:border-accent-line hover:text-accent">
            <FileText className="h-3.5 w-3.5" /> View official PDF{card.pdf_pages ? ` (${card.pdf_pages}p)` : ""}
          </a>
        )}
        <button type="button" onClick={() => navigate(`/company/${row.scrip_code}`)}
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line px-3 text-[13px] font-medium text-ink hover:border-accent-line hover:text-accent">
          <FolderOpen className="h-3.5 w-3.5" /> Open company memory
        </button>
        <button type="button" onClick={copyPng}
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line px-3 text-[13px] font-medium text-ink hover:border-accent-line hover:text-accent">
          <Camera className="h-3.5 w-3.5" /> {copy === "copied" ? "Copied" : copy === "saved" ? "Saved" : copy === "error" ? "Couldn't copy" : "Copy card as PNG"}
        </button>
        <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-ink-3">
          {row.needs_review ? (
            <span className="inline-flex items-center gap-1 text-warn" title={card.grounding.ungrounded.join(", ")}>
              <AlertTriangle className="h-3.5 w-3.5" /> Unverified: check the PDF
            </span>
          ) : card.grounding.checked > 0 ? (
            <span className="inline-flex items-center gap-1"
              title={card.grounding.ungrounded.length ? `Not found: ${card.grounding.ungrounded.join(", ")}` : "Every number was found in the filing or company memory"}>
              <BadgeCheck className={cn("h-3.5 w-3.5", card.grounding.ungrounded.length ? "text-ink-3" : "text-pos")} />
              {card.grounding.ungrounded.length
                ? `${Math.max(0, card.grounding.checked - card.grounding.ungrounded.length)} of ${card.grounding.checked} numbers matched`
                : "Numbers verified"}
            </span>
          ) : null}
          {!row.memory_complete && <span>· partial memory</span>}
        </span>
      </div>
      <p className="mt-3 text-[11px] text-ink-3">AI summary of a public BSE filing. Not investment advice; verify against the original filing.</p>
    </div>
  );
}

export function TrackItem({ icon: Icon, label, items }: { icon: typeof Timer; label: string; items: string[] }) {
  return (
    <div>
      <dt className="flex items-center gap-1.5 text-[13px] font-semibold text-ink"><Icon className="h-3.5 w-3.5 text-ink-3" />{label}</dt>
      <dd className="mt-0.5 text-[13.5px] leading-relaxed text-ink-2">
        {items.map((t, i) => <div key={i}>{t}</div>)}
      </dd>
    </div>
  );
}

export function QuantLine({ q }: { q: QuantifiedImpact }) {
  const [open, setOpen] = useState(false);
  const verified = q.check === "VERIFIED";
  return (
    <Bullet>
      <span className="font-semibold text-accent">[Quantified impact]</span>{" "}
      {q.label}: <span className="num font-semibold text-ink">{quantValue(q.result, q.unit)}</span>
      {q.interpretation ? <span className="text-ink-2"> {q.interpretation}</span> : null}{" "}
      <span className={cn("ml-1 inline-flex items-center gap-1 align-middle text-[11px]", verified ? "text-pos" : q.check === "MISMATCH" ? "text-neg" : "text-ink-3")}
        title={q.check_note ?? undefined}>
        {verified ? <BadgeCheck className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
        {verified ? "math checked" : q.check === "MISMATCH" ? "math doesn't check out" : "unchecked"}
      </span>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} data-noexport="true"
        className="ml-2 inline-flex items-center gap-1 align-middle text-[11px] font-medium text-accent hover:underline">
        <Calculator className="h-3 w-3" /> {open ? "Hide working" : "Show working"}
      </button>
      {open && (
        <span className="mt-1.5 block rounded-lg bg-surface-2 px-3 py-2 text-[12.5px]">
          <code className="block font-mono text-ink">{q.formula}</code>
          {q.inputs.map((i) => (
            <span key={i.name} className="mt-1 flex flex-wrap items-baseline gap-x-2">
              <span className="num text-ink">{i.name} = {exact(i.value)}{i.unit ? ` ${i.unit}` : ""}</span>
              <span className={cn("rounded px-1 text-[10px] font-semibold uppercase",
                i.source === "ASSUMPTION" ? "bg-warn-soft text-warn" : "bg-accent-soft text-accent")}>{i.source.toLowerCase()}</span>
              {q.unsourced_inputs?.includes(i.name) ? <span className="text-neg">not found in the filing</span> : null}
              {i.note ? <span className="text-ink-3">{i.note}</span> : null}
            </span>
          ))}
          <span className="mt-1 block text-[11px] text-ink-3">An estimate from the inputs shown, not a forecast or recommendation.</span>
        </span>
      )}
    </Bullet>
  );
}
