import { toBlob } from "html-to-image";
import {
  AlertTriangle, ArrowDownRight, ArrowUpRight, BadgeCheck, Calculator, Camera, CheckCircle2, ChevronDown, FileText,
  FolderOpen, Gauge, Info, ListChecks, Minus, Scale, ShieldAlert, Timer,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";
import type { CardBody, CardRow, Insight, QuantifiedImpact, Signal } from "../../shared/types";
import { cn } from "../lib/cn";
import { cr, exact, istDateTime, marketSession, pct, quantValue, signClass, titleCase } from "../lib/format";
import { EVENT_LABELS, IMPACT_LABEL, IMPACT_STYLE } from "../lib/taxonomy";
import { useQueryState } from "../lib/url";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";

const BASIS_LABEL: Record<Insight["basis"], string> = {
  MEMORY: "Memory link",
  BALANCE_SHEET: "Balance sheet",
  SECTOR: "Peer context",
  FILING: "Filing",
};

const SOURCE_STYLE: Record<string, string> = {
  FILING: "border-forest/30 text-forest",
  MEMORY: "border-info/30 text-info",
  ASSUMPTION: "border-warn/40 text-warn",
};

function QuantRow({ q }: { q: QuantifiedImpact }) {
  const [open, setOpen] = useState(false);
  const verified = q.check === "VERIFIED";
  return (
    <li className="rounded-md border border-memory-line bg-surface/60 px-2.5 py-2">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="mr-0.5 rounded bg-surface/70 px-1 py-px text-[10px] font-semibold uppercase tracking-wide text-forest">
          Quantified
        </span>
        <span className="font-medium text-ink">{q.label}:</span>
        <span className="num font-semibold text-ink">{quantValue(q.result, q.unit)}</span>
        <span
          className={cn("inline-flex items-center gap-1 text-[11px]", verified ? "text-pos" : q.check === "MISMATCH" ? "text-neg" : "text-ink-3")}
          title={q.check_note ?? (verified ? "The arithmetic was recomputed and matches" : "Not re-checked")}
        >
          {verified ? <BadgeCheck className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
          {verified ? "math checked" : q.check === "MISMATCH" ? "math doesn't check out" : "unchecked"}
        </span>
      </div>
      {q.interpretation ? <p className="mt-0.5 text-[13px] text-ink-2">{q.interpretation}</p> : null}
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} data-noexport="true"
        className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-forest hover:underline">
        <Calculator className="h-3 w-3" /> {open ? "Hide working" : "Show working"}
        <ChevronDown className={cn("h-3 w-3 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-1.5 space-y-1 text-[12px]">
          <code className="num block overflow-x-auto rounded bg-surface-2 px-2 py-1 text-ink">{q.formula}</code>
          <ul className="space-y-0.5">
            {q.inputs.map((i) => (
              <li key={i.name} className="flex flex-wrap items-baseline gap-x-2">
                <span className="num text-ink">{i.name} = {exact(i.value)}{i.unit ? ` ${i.unit}` : ""}</span>
                <span className={cn("rounded border px-1 text-[10px] font-semibold uppercase", SOURCE_STYLE[i.source] ?? SOURCE_STYLE.ASSUMPTION)}>
                  {i.source.toLowerCase()}
                </span>
                {q.unsourced_inputs?.includes(i.name) ? <span className="text-neg">not found in the filing</span> : null}
                {i.note ? <span className="text-ink-3">{i.note}</span> : null}
              </li>
            ))}
          </ul>
          <p className="text-[11px] text-ink-3">An estimate from the inputs above, not a forecast or recommendation.</p>
        </div>
      )}
    </li>
  );
}

const SIGNAL_ICON: Record<Signal["type"], typeof Info> = {
  PROMISE_DELIVERED: CheckCircle2,
  GUIDANCE_BREACH: ShieldAlert,
  WATCH_RESOLVED: ListChecks,
  DILUTION: Scale,
  WORKING_CAPITAL_STRAIN: AlertTriangle,
  METRIC_SHIFT: Gauge,
};

const SIGNAL_LABEL: Record<Signal["type"], string> = {
  PROMISE_DELIVERED: "Promise delivered",
  GUIDANCE_BREACH: "Guidance breach",
  WATCH_RESOLVED: "Follow-up",
  DILUTION: "Dilution",
  WORKING_CAPITAL_STRAIN: "Working capital strain",
  METRIC_SHIFT: "Metric shift",
};

const SEVERITY_STYLE: Record<Signal["severity"], string> = {
  POSITIVE: "border-pos/30 bg-pos/8 text-pos",
  WARNING: "border-warn/30 bg-warn/8 text-warn",
  INFO: "border-info/30 bg-info/8 text-info",
};

export function parseCard(row: CardRow): CardBody | null {
  try {
    return JSON.parse(row.card_json) as CardBody;
  } catch {
    return null;
  }
}

export function SuperCard({ row, highlight }: { row: CardRow; highlight?: boolean }) {
  const card = useMemo(() => parseCard(row), [row]);
  const ref = useRef<HTMLElement>(null);
  const [, setQuery] = useQueryState();
  const [copyState, setCopyState] = useState<"idle" | "copied" | "saved" | "error">("idle");

  if (!card) return null;

  const openCompany = (tab = "dossier") => setQuery({ company: row.scrip_code, tab, doc: tab === "pdf" ? row.news_id : null });

  async function copyPng() {
    if (!ref.current) return;
    try {
      const bg = getComputedStyle(document.documentElement).getPropertyValue("--surface").trim() || "#ffffff";
      const blob = await toBlob(ref.current, {
        pixelRatio: 2,
        backgroundColor: bg,
        filter: (node) => !(node instanceof HTMLElement && node.dataset.noexport === "true"),
      });
      if (!blob) throw new Error("render failed");
      if (navigator.clipboard && "ClipboardItem" in window) {
        await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
        setCopyState("copied");
      } else {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `${row.symbol ?? row.scrip_code}-${row.filing_date}.png`;
        a.click();
        setCopyState("saved");
      }
    } catch {
      setCopyState("error");
    }
    setTimeout(() => setCopyState("idle"), 2000);
  }

  const track = card.track_next;
  const hasTrack = !!track && track.milestones.length + track.kpis_to_verify.length + track.pending_approvals.length + track.risks.length > 0;
  const changes = card.notable_changes ?? [];

  return (
    <article
      ref={ref}
      id={`card-${row.news_id}`}
      className={cn(
        "overflow-hidden rounded-xl border border-line bg-surface shadow-[0_1px_2px_rgba(0,0,0,0.04)]",
        highlight && "ring-2 ring-forest",
      )}
    >
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1.5 px-4 pt-4 sm:px-5">
        <Badge className={IMPACT_STYLE[row.impact_level]}>{IMPACT_LABEL[row.impact_level]}</Badge>
        <Badge className="border-line bg-surface-2 text-ink-2">{card.category_tag || EVENT_LABELS[row.event_category]}</Badge>
        {row.sector && row.sector !== "default" ? (
          <Badge className="border-line bg-surface text-ink-3">{titleCase(row.sector)}</Badge>
        ) : null}
        <button
          type="button"
          onClick={() => openCompany()}
          className="min-w-0 truncate font-display text-sm font-semibold text-ink hover:text-forest hover:underline"
        >
          {row.company_name}
        </button>
        <span className="num text-xs text-ink-3">
          {row.symbol ? `${row.symbol} · ` : ""}
          {row.scrip_code}
          {row.market_cap_cr != null ? ` · ${cr(row.market_cap_cr)}` : ""}
          {row.size_category ? ` · ${titleCase(row.size_category)}cap` : ""}
        </span>
        <span className="ml-auto flex items-center gap-2 text-xs text-ink-3">
          <span className="hidden rounded border border-line px-1.5 py-px text-[10px] font-medium uppercase tracking-wide sm:inline">
            {marketSession(row.filed_at)}
          </span>
          <time className="num" dateTime={row.filed_at}>{istDateTime(row.filed_at)} IST</time>
        </span>
      </header>

      <h3 className="px-4 pt-2 font-display text-[17px] font-bold leading-snug text-ink sm:px-5">{card.headline}</h3>

      {card.key_numbers.length > 0 && (
        <dl className="mt-3 flex flex-wrap gap-2 px-4 sm:px-5">
          {card.key_numbers.slice(0, 6).map((k) => (
            <div key={k.label} className="rounded-md border border-line bg-surface-2 px-2.5 py-1.5">
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-3">{k.label}</dt>
              <dd className="num text-sm font-semibold text-ink">
                {k.value}
                {k.change ? <span className={cn("ml-1.5 text-xs", k.change.trim().startsWith("-") ? "text-neg" : "text-pos")}>{k.change}</span> : null}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <div className="grid gap-3 px-4 py-4 sm:px-5 md:grid-cols-2">
        <section>
          <h4 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-ink-3">What happened · the facts</h4>
          <ul className="space-y-1.5 text-sm leading-relaxed text-ink">
            {card.what_happened.map((fact, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-ink-3" />
                <span>{fact}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="overflow-hidden rounded-lg border border-memory-line bg-memory">
          <h4 className="bg-forest px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-forest-ink">
            Why it matters · memory &amp; forensics
          </h4>
          <ul className="space-y-2 px-3 py-2.5 text-sm leading-relaxed text-ink">
            {card.why_it_matters.map((insight, i) => (
              <li key={i}>
                <span className="mr-1.5 rounded bg-surface/70 px-1 py-px text-[10px] font-semibold uppercase tracking-wide text-forest">
                  {BASIS_LABEL[insight.basis] ?? insight.basis}
                </span>
                {insight.text}
              </li>
            ))}
            {(card.quantified_impact ?? []).map((q, i) => <QuantRow key={`q${i}`} q={q} />)}
            {card.missing_disclosures.map((m, i) => (
              <li key={`m${i}`} className="flex gap-1.5 text-warn">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  <strong className="font-semibold">Missing disclosure:</strong> {m}
                </span>
              </li>
            ))}
            {card.why_it_matters.length === 0 && card.missing_disclosures.length === 0 && !card.quantified_impact?.length && (
              <li className="text-ink-3">No memory links for this filing yet.</li>
            )}
          </ul>
        </section>
      </div>

      {card.signals.length > 0 && (
        <ul className="flex flex-col gap-1.5 px-4 pb-3 sm:px-5">
          {card.signals.map((s, i) => {
            const Icon = SIGNAL_ICON[s.type] ?? Info;
            return (
              <li key={i} className={cn("flex items-start gap-2 rounded-md border px-2.5 py-1.5 text-[13px]", SEVERITY_STYLE[s.severity])}>
                <Icon className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  <span className="mr-1 font-semibold">{SIGNAL_LABEL[s.type] ?? titleCase(s.type)}:</span>
                  <span className="text-ink">{s.text}</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {changes.length > 0 && (
        <div className="px-4 pb-3 sm:px-5">
          <h4 className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-3">Notable changes</h4>
          <ul className="divide-y divide-line rounded-md border border-line text-[13px]">
            {changes.map((c, i) => {
              const Arrow = c.direction === "POSITIVE" ? ArrowUpRight : c.direction === "NEGATIVE" ? ArrowDownRight : Minus;
              const tone = c.direction === "POSITIVE" ? "text-pos" : c.direction === "NEGATIVE" ? "text-neg" : "text-ink-3";
              return (
                <li key={i} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-2.5 py-1.5">
                  <span className="font-medium text-ink">
                    <Arrow className={cn("mr-1 inline h-3.5 w-3.5", tone)} />
                    {titleCase(c.metric)}
                  </span>
                  <span className="num text-ink-2">
                    {c.previous ?? "—"} → <span className="text-ink">{c.current ?? "—"}</span>
                  </span>
                  {c.change ? <span className={cn("num font-semibold", tone)}>{c.change}</span> : null}
                  {c.why ? <span className="basis-full text-ink-2 md:basis-auto md:flex-1">{c.why}</span> : null}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {hasTrack && track && (
        <div className="mx-4 mb-3 rounded-lg border border-dashed border-line bg-surface-2/60 px-3 py-2.5 sm:mx-5">
          <h4 className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-3">What to track next</h4>
          <ul className="grid gap-x-6 gap-y-1 text-[13px] text-ink md:grid-cols-2">
            {track.milestones.map((m, i) => (
              <li key={`ms${i}`} className="flex gap-1.5">
                <Timer className="mt-0.5 h-3.5 w-3.5 shrink-0 text-info" />
                <span>
                  {m.what}
                  {m.when ? <span className="num text-ink-2"> · {m.when}</span> : null}
                </span>
              </li>
            ))}
            {track.kpis_to_verify.map((k, i) => (
              <li key={`k${i}`} className="flex gap-1.5">
                <Gauge className="mt-0.5 h-3.5 w-3.5 shrink-0 text-forest" />
                <span>
                  Verify {k.kpi}
                  {k.target ? <span className="text-ink-2"> (target {k.target})</span> : null}
                  {k.check_in ? <span className="text-ink-2"> in {k.check_in}</span> : null}
                </span>
              </li>
            ))}
            {track.pending_approvals.map((a, i) => (
              <li key={`a${i}`} className="flex gap-1.5">
                <Scale className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-2" />
                <span>Pending: {a}</span>
              </li>
            ))}
            {track.risks.map((r, i) => (
              <li key={`r${i}`} className="flex gap-1.5">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" />
                <span>Risk: {r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <footer className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line bg-surface-2/40 px-4 py-2.5 sm:px-5">
        <div className="num flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          {card.fundamentals?.revenue && (
            <span className="text-ink-3">
              Rev {card.fundamentals.revenue.period ?? ""} <span className="text-ink">{cr(card.fundamentals.revenue.value)}</span>
            </span>
          )}
          {card.fundamentals?.debt && (
            <span className="text-ink-3">Debt <span className="text-ink">{cr(card.fundamentals.debt.value)}</span></span>
          )}
          {card.fundamentals?.net_worth && (
            <span className="text-ink-3">
              Net worth <span className={card.fundamentals.net_worth.value < 0 ? "text-neg" : "text-ink"}>{cr(card.fundamentals.net_worth.value)}</span>
            </span>
          )}
          <span className="text-ink-3">
            1W <span className={signClass(row.ret_1w)}>{pct(row.ret_1w)}</span>
          </span>
          <span className="text-ink-3">
            1M <span className={signClass(row.ret_1m)}>{pct(row.ret_1m)}</span>
          </span>
          <span className="text-ink-3">
            1Y <span className={signClass(row.ret_1y)}>{pct(row.ret_1y)}</span>
          </span>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-ink-3">
          {row.needs_review ? (
            <span className="inline-flex items-center gap-1 text-warn" title={`Unverified: ${card.grounding.ungrounded.join(", ")}`}>
              <AlertTriangle className="h-3.5 w-3.5" /> Numbers need review
            </span>
          ) : card.grounding.checked > 0 ? (
            <span className="inline-flex items-center gap-1" title="Every number on this card was found in the filing or memory">
              <BadgeCheck className="h-3.5 w-3.5 text-pos" /> {Math.round(card.grounding.score * 100)}% numbers verified
            </span>
          ) : null}
          {!row.memory_complete && <span title="Backfill had not reached this company's history yet">· partial memory</span>}
        </div>
        <div className="ml-auto flex flex-wrap gap-1.5" data-noexport="true">
          {row.pdf_url && (
            <Button size="sm" variant="ghost" onClick={() => openCompany("pdf")}>
              <FileText className="h-3.5 w-3.5" /> View PDF{card.pdf_pages ? ` (${card.pdf_pages}p)` : ""}
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => openCompany()}>
            <FolderOpen className="h-3.5 w-3.5" /> Company memory
          </Button>
          <Button size="sm" variant="ghost" onClick={copyPng}>
            <Camera className="h-3.5 w-3.5" />
            {copyState === "copied" ? "Copied" : copyState === "saved" ? "Saved" : copyState === "error" ? "Failed" : "Copy PNG"}
          </Button>
        </div>
      </footer>
    </article>
  );
}
