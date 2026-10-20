import {
  AlertTriangle, ArrowDownRight, ArrowUpRight, BadgeCheck, BarChart3, Building2, Camera, Check, CheckCircle2, ChevronDown, ChevronRight,
  ChevronUp, CircleDollarSign, ClipboardCheck, FileSearch, FileText, Gauge, Flame, Minus, MoreHorizontal, RefreshCcw, Rocket, Scale,
  ShieldAlert, Star, Timer, Trash2, type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { useLocation } from "wouter";
import { useQueryState } from "../lib/url";
import type { CallRead, CardBody, CardRow, Fact, Impact, PriceReaction, Technicals, ResultLine, ResultsSnapshot, Signal } from "../../shared/types";
import { cn } from "../lib/cn";
import { useRatings, useVerdicts, type Verdict } from "../lib/owner";
import { copyNodeAsPng } from "../lib/png";
import { cr, formatKpi, istDate, istDateTime, pct, relativeTime, signClass, titleCase } from "../lib/format";
import { EVENT_LABELS, IMPACT_LABEL, IMPACT_TEXT, TONE_CHIP, TONE_LABEL, TONE_STRIPE, verdict, type Tone } from "../lib/taxonomy";
import { Avatar, TickerChip } from "./Avatar";
import { parseCard, QuantLine, SEVERITY_TEXT, SIGNAL, TrackItem } from "./FilingCard";
import { plain, RichText } from "./RichText";
import {
  executionFact, near, PERIOD_WORDS, ratedAmount, realValue, repeats, restatesHeadline, saysExGst, showsFigure, splitFacts, tilesBesides,
  verifiedFact,
} from "../lib/cardText";
import { callTakeaways, type CallTakeawaysView } from "../lib/callTakeaways";
import { allZero, lowerIsBetter, NO_TURN, TURN, turnOf } from "../lib/results";

const IMPACT_WORD: Record<Impact, string> = { HIGH: "High impact", MODERATE: "Moderate impact", LOW: "Low impact" };

export const STAGE_LABEL: Record<string, string> = {
  LOI: "LOI", LOA: "LOA", WORK_ORDER: "Work order", CONTRACT: "Contract", MOU: "MoU", DEVELOPMENT_ORDER: "Development order",
  PROPOSED: "Proposed", BOARD_APPROVED: "Board approved", TERMS_FINALISED: "Terms final", SHAREHOLDER_APPROVED: "Shareholder approved",
  IN_PROGRESS: "In progress", PARTIALLY_COMPLETED: "Partly complete", COMPLETED: "Completed", CANCELLED: "Cancelled",
};
/** Stages where nothing is firm yet: shown in amber. */
export const PROVISIONAL_STAGES = new Set(["LOI", "MOU", "DEVELOPMENT_ORDER", "PROPOSED", "BOARD_APPROVED", "CANCELLED"]);
const SESSION_LABEL: Record<string, string> = {
  LIVE_MARKET: "Live market", PRE_MARKET: "Pre-market", AFTER_MARKET: "After market", NON_TRADING: "Non-trading day",
};
const PILLAR_LABEL: Record<string, string> = {
  magnitude: "Size vs company (30)", margin: "Margin & operating leverage (25)", balance_sheet: "Funding & balance sheet (20)",
  credibility: "Management credibility (15)", disclosure: "Disclosure & price timing (10)", penalty: "Forensic penalties",
};
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
function boxItems(card: CardBody, skip: (s: Signal) => boolean = () => false) {
  const signal = [...card.signals].filter((s) => !skip(s)).sort((a, b) =>
    (SIGNAL_RANK[a.severity] ?? 2) - (SIGNAL_RANK[b.severity] ?? 2) || (INFO_RANK[a.type] ?? 9) - (INFO_RANK[b.type] ?? 9))[0];
  const missing = card.missing_disclosures[0];
  const room = Math.max(2, 4 - (signal ? 1 : 0) - (missing ? 1 : 0));
  const insights = card.why_it_matters.slice(0, room);
  return { insights, signal, missing, fallback: insights.length === 0 ? card.takeaway : undefined };
}

function Point({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <li className={cn("flex gap-2 text-[14.5px] leading-relaxed text-ink", className)}>
      <ChevronRight aria-hidden className="mt-[4px] h-4 w-4 shrink-0 text-[var(--fam,var(--accent))]" strokeWidth={2.5} />
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

/** A change in the table: a turn across a loss in words, as on the Results page; green is the good news, so a fall in
 * bad loans or provisions is green. */
function change(line: ResultLine | undefined, kind: "yoy" | "qoq", bps: boolean, lower: boolean, key = "") {
  const turn = bps || NO_TURN.has(key) ? undefined : turnOf(line, kind);
  if (turn && TURN[turn]) return <span className={cn("font-semibold", TURN[turn][1])}>{TURN[turn][0]}</span>;
  const v = bps ? line?.[`${kind}_bps`] : line?.[`${kind}_pct`];
  if (v == null) return <span className="text-ink-3">—</span>;
  return <span className={cn("font-semibold", signClass(lower ? -v : v))}>{bps ? `${v > 0 ? "+" : ""}${v} bps` : pct(v)}</span>;
}

type LineSpec = NonNullable<ResultsSnapshot["lines"]>[number];
const DEFAULT_LINES: LineSpec[] = [
  { key: "revenue", label: "Revenue", unit: "cr" }, { key: "ebitda", label: "EBITDA", unit: "cr" },
  { key: "ebitda_margin", label: "EBITDA margin", unit: "pct" },
  { key: "pat", label: "PAT", unit: "cr" }, { key: "eps", label: "EPS (₹)", unit: "inr" },
];

/** The table's rows: the statement's own lines (company, bank, insurer) and the sector's KPIs, as the pipeline chose them. */
export function resultLines(r: ResultsSnapshot): (LineSpec & { line: ResultLine })[] {
  const get = (key: string) => (r as unknown as Record<string, ResultLine | undefined>)[key];
  return (r.lines?.length ? r.lines : DEFAULT_LINES).flatMap((s) => {
    const line = get(s.key);
    return line && typeof line.value === "number" && !allZero(line) ? [{ ...s, line }] : [];
  });
}

export function lineValue(v: number, unit: LineSpec["unit"]): string {
  if (unit === "pct") return `${v.toFixed(Math.abs(v) < 10 ? 2 : 1)}%`;
  if (unit === "inr") return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
  if (unit === "num") return v.toLocaleString("en-IN", { maximumFractionDigits: 1 });
  return cr(v).replace("₹", "").replace(/ Cr$/, "");
}

const LENS_TITLE: Record<string, string> = { bank: "Bank lens · ₹ Cr", insurer: "Insurer lens · ₹ Cr" };

/** A P&L for results cards in the statement's own lines: this quarter, a year ago and its change, then the previous
 * quarter and its change (the approved card's order), with the Results page's verdict. On a phone the earlier values
 * sit under their change, so the changes stay in view without a sideways scroll. */
function ResultsTable({ r, judged }: { r: ResultsSnapshot; judged: { label: string; tone: Tone } }) {
  const rows = resultLines(r);
  if (rows.length < 2) return null;
  const has = (pick: (l: ResultLine, bps: boolean) => unknown) => rows.some(({ line, unit }) => pick(line, unit === "pct") != null);
  const py = has((l) => l.prev_year) && r.prev_year_period;
  const pq = has((l) => l.prev_quarter) && r.prev_quarter_period;
  const yoy = has((l, bps) => (bps ? l.yoy_bps : l.yoy_pct ?? turnOf(l, "yoy")));
  const qoq = has((l, bps) => (bps ? l.qoq_bps : l.qoq_pct ?? turnOf(l, "qoq")));
  const th = "px-1.5 py-1.5 text-right align-bottom text-[10.5px] font-semibold uppercase tracking-[0.08em] sm:whitespace-nowrap sm:px-3";
  const td = "px-1.5 py-1.5 text-right align-top sm:whitespace-nowrap sm:px-3";
  const was = (v: number | undefined, unit: LineSpec["unit"]) => (v != null ? lineValue(v, unit) : "—");
  const under = "block text-[11px] font-normal text-ink-3 sm:hidden";
  return (
    <BlockShell title={r.discussed ? `Quarter discussed · ${r.period}` : LENS_TITLE[r.lens ?? ""] ?? "Quarter in ₹ Cr"}
      right={<span className={cn("ml-auto rounded-full px-2.5 py-0.5 text-[11px] font-extrabold normal-case tracking-normal", TONE_CHIP[judged.tone])}>{judged.label}</span>}>
      <table className="num w-full text-[12.5px] sm:text-[13px]">
        <thead className="text-ink-3">
          <tr>
            <th className={cn(th, "pl-0 text-left sm:pl-0")}>₹ Cr</th>
            <th className={cn(th, "text-ink")}>{r.period}</th>
            {py && <th className={cn(th, "hidden sm:table-cell")}>{r.prev_year_period}</th>}
            {yoy && <th className={th}>YoY{py && <span className={cn(under, "whitespace-nowrap normal-case tracking-normal")}>vs {r.prev_year_period}</span>}</th>}
            {pq && <th className={cn(th, "hidden sm:table-cell")}>{r.prev_quarter_period}</th>}
            {qoq && <th className={cn(th, "pr-0 sm:pr-0")}>QoQ{pq && <span className={cn(under, "whitespace-nowrap normal-case tracking-normal")}>vs {r.prev_quarter_period}</span>}</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ key, label, unit, line }) => {
            const bps = unit === "pct", lower = lowerIsBetter(key, label);
            return (
              <tr key={key} className="border-t border-line">
                <td className={cn(td, "pl-0 text-left font-sans font-medium text-ink sm:pl-0")}>{label}</td>
                <td className={cn(td, "font-semibold text-ink")}>{lineValue(line.value, unit)}</td>
                {py && <td className={cn(td, "hidden text-ink-2 sm:table-cell")}>{was(line.prev_year, unit)}</td>}
                {yoy && <td className={td}>{change(line, "yoy", bps, lower, key)}{py && <span className={under}>{was(line.prev_year, unit)}</span>}</td>}
                {pq && <td className={cn(td, "hidden text-ink-2 sm:table-cell")}>{was(line.prev_quarter, unit)}</td>}
                {qoq && <td className={cn(td, "pr-0 sm:pr-0")}>{change(line, "qoq", bps, lower, key)}{pq && <span className={under}>{was(line.prev_quarter, unit)}</span>}</td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </BlockShell>
  );
}

/** Footer figures follow the company's sector (GNPA for a bank, EBITDA/t for cement, ARPU for
 * telecom, RevPAR for hotels...); without one, debt to equity, unless it rounds to nothing ("D/E 0.00x"). */
function footerMetrics(card: CardBody): { label: string; value: string; period?: string | null }[] {
  const f = card.fundamentals ?? {};
  if (f.kpis?.length) return f.kpis.map((k) => ({ label: k.label, value: formatKpi(k), period: k.period }));
  const de = f.debt && f.net_worth && f.net_worth.value > 0 ? f.debt.value / f.net_worth.value : null;
  if (de != null && de >= 0.005) return [{ label: "D/E", value: `${de.toFixed(2)}x` }];
  if (f.net_worth && f.net_worth.value < 0) return [{ label: "Net worth", value: cr(f.net_worth.value) }];
  return [];
}

/** The P&L table shows only when at least two of its lines are known. */
function tableShows(r: ResultsSnapshot | null | undefined): r is ResultsSnapshot {
  return !!r && resultLines(r).length >= 2;
}

/** A results bullet that only restates numbers the P&L table shows adds nothing; the card hides it. */
function coveredByTable(fact: Fact, r: ResultsSnapshot): boolean {
  const known = resultLines(r).flatMap(({ line }) =>
    [line.value, line.prev_year, line.prev_quarter, line.yoy_pct, line.qoq_pct, line.yoy_bps, line.qoq_bps]
      .filter((v): v is number => v != null).map(Math.abs));
  const raw = plain(fact).replace(PERIOD_WORDS, " ").match(/\d[\d,]*(?:\.\d+)?/g) ?? [];
  return raw.length > 0 && raw.every((x) => near(Number(x.replace(/,/g, "")), known, x));
}

/** The key numbers on the card's face, as tiles inside the family's block. */
function KeyBlock({ items }: { items: CardBody["key_numbers"] }) {
  return (
    <BlockShell title="Key numbers">
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {items.slice(0, 4).map((k, i) => (
          <div key={`${k.label}-${i}`} className="min-w-0 rounded-xl bg-surface-2 px-2.5 py-1.5">
            <dt className="truncate text-[11px] font-bold text-ink-3" title={k.label}>{k.label}</dt>
            <dd className="num text-[14px] font-bold text-ink">{k.value}</dd>
            {k.change ? <dd className={cn("num text-[12px] font-semibold", k.change.trim().startsWith("-") || k.change.trim().startsWith("−") ? "text-neg" : "text-pos")}>{k.change}</dd> : null}
          </div>
        ))}
      </dl>
    </BlockShell>
  );
}

function KeyTiles({ items }: { items: CardBody["key_numbers"] }) {
  return (
    <dl className="mt-3 grid grid-cols-2 overflow-hidden rounded-xl border border-line sm:grid-cols-4">
      {items.slice(0, 4).map((k, i) => (
        <div key={`${k.label}-${i}`} className={cn("px-3 py-2", i % 2 === 1 && "border-l border-line", i >= 2 && "border-t border-line sm:border-t-0", i >= 1 && "sm:border-l")}>
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

/** Event families: each has its own colour and its own block on the card's face (owner, 2026-10-19). Green and red
 * keep one meaning on every card, up or down; the family colour says what kind of news it is. */
type Family = "res" | "ord" | "cap" | "rat" | "reg" | "oth";
const FAMILY: Record<string, Family> = {
  RESULTS: "res", CONCALL_PRESENTATION: "res", ANNUAL_REPORT: "res", MONTHLY_BUSINESS_UPDATE: "res",
  ORDER_WIN: "ord", CAPEX: "ord", PRODUCT_LAUNCH: "ord",
  RIGHTS_ISSUE: "cap", FUNDRAISE: "cap", M_AND_A: "cap", CORPORATE_ACTION: "cap",
  DEBT_RATINGS: "rat", GOVERNANCE: "reg", MANAGEMENT_CHANGE: "reg", LITIGATION_REGULATORY: "reg",
};
const FAMILY_ICON: Record<Family, LucideIcon> = { res: BarChart3, ord: ClipboardCheck, cap: CircleDollarSign, rat: Star, reg: Scale, oth: FileText };
const famStyle = (f: Family) => ({ "--fam": `var(--fam-${f})`, "--fam-soft": `var(--fam-${f}-soft)` }) as CSSProperties;

const GRADE: Record<Impact, string> = { HIGH: "bg-neg-soft text-impact-high", MODERATE: "bg-warn-soft text-warn", LOW: "bg-surface-2 text-ink-3" };
const IMPACT_SHORT: Record<Impact, string> = { HIGH: "High", MODERATE: "Moderate", LOW: "Low" };
const DIRECTION: Record<Tone, { mark: string; cls: string } | null> = {
  POSITIVE: { mark: "▲", cls: "text-pos" }, NEGATIVE: { mark: "▼", cls: "text-neg" }, MIXED: { mark: "◆", cls: "text-warn" }, NEUTRAL: null,
};

function BlockShell({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="mt-3 rounded-2xl border border-[color-mix(in_srgb,var(--fam)_28%,var(--line))] px-3.5 py-3">
      <h4 className="mb-2.5 flex items-center gap-2 text-[10.5px] font-extrabold uppercase tracking-[0.12em] text-[var(--fam)]">{title}{right}</h4>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function Steps({ steps, at: raw, warn, reached }: { steps: string[]; at: number; warn?: boolean; reached?: number[] }) {
  const at = Math.max(0, Math.min(steps.length - 1, raw));
  // a stage ladder is filled up to the current step; a case marks each step that happened, in whatever order it came
  const done = (i: number) => (reached ? reached.includes(i) || i === at : i <= at);
  return (
    <ol className="flex items-start" aria-label={`Stage: ${steps[at]}`}>
      {steps.map((s, i) => (
        <li key={s + i} className={cn("relative flex min-w-0 flex-1 flex-col items-center gap-1 text-center text-[11.5px] font-bold",
          done(i) ? "text-ink" : "text-ink-3")}>
          {i > 0 && <span aria-hidden className={cn("absolute right-1/2 top-[7px] h-[2px] w-full", done(i) && done(i - 1) ? "bg-[var(--fam)]" : "bg-line-strong")} />}
          <span aria-hidden className={cn("relative z-[1] h-4 w-4 rounded-full border-2",
            done(i) ? (warn && i === at ? "border-warn bg-warn" : "border-[var(--fam)] bg-[var(--fam)]") : "border-line-strong bg-surface",
            i === at && "shadow-[0_0_0_4px_var(--fam-soft)]")} />
          <span className="w-full break-words px-0.5 leading-tight">{s}</span>
        </li>
      ))}
    </ol>
  );
}

function SizeBar({ label, pct: value }: { label: string; pct: number }) {
  return (
    <div>
      <div className="flex justify-between gap-3 text-[12.5px] font-semibold text-ink-2"><span>{label}</span><span className="num text-ink">{value.toFixed(value < 10 ? 1 : 0)}%</span></div>
      <div className="mt-1 h-2 overflow-hidden rounded bg-surface-2"><i className="block h-full rounded bg-[var(--fam)]" style={{ width: `${Math.min(100, Math.max(2, value))}%` }} /></div>
    </div>
  );
}

const TRACKS: Record<string, { steps: string[]; at: Record<string, number> }> = {
  ORDER: { steps: ["Award", "Contract", "Execution", "Completed"],
           at: { LOI: 0, LOA: 0, MOU: 0, DEVELOPMENT_ORDER: 0, WORK_ORDER: 1, CONTRACT: 1, IN_PROGRESS: 2, PARTIALLY_COMPLETED: 2, COMPLETED: 3 } },
  CAPEX: { steps: ["Proposed", "Approved", "Under way", "Completed"],
           at: { PROPOSED: 0, BOARD_APPROVED: 1, TERMS_FINALISED: 1, SHAREHOLDER_APPROVED: 1, IN_PROGRESS: 2, PARTIALLY_COMPLETED: 2, COMPLETED: 3 } },
  // "Approved" names the approval the stage records (board or shareholders): many deals need no shareholder vote, and a
  // "Shareholders" step lit for a deal under way said they had voted (Jindal Stainless, owner's review 2026-10-20)
  DEAL: { steps: ["Proposed", "Approved", "Under way", "Completed"],
          at: { PROPOSED: 0, BOARD_APPROVED: 1, TERMS_FINALISED: 1, SHAREHOLDER_APPROVED: 1, IN_PROGRESS: 2, PARTIALLY_COMPLETED: 2, COMPLETED: 3 } },
};

// What the deal's other party is: an order's client, a divestment's buyer, what pays for a capex. An acquisition's
// counterparty can be the seller as well as the target (Ceigall's JKJTL, bought from REC Power: "Target: REC Power",
// design audit 2026-10-20), so it is named only as the other party.
const COUNTERPARTY: Record<string, string> = { ORDER: "From", ACQUISITION: "Counterparty", DIVESTMENT: "Buyer", FUNDRAISE: "Investors", CAPEX: "Funded by" };

const TAKES_TARGET = new Set(["ACQUISITION", "DIVESTMENT"]);

/** A share count in Indian units: 2,64,93,882 reads "2.65 Cr", 12,50,000 "12.5 lakh". */
function sharesText(n: number): string {
  if (n >= 1e7) return `${(n / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 2 })} Cr`;
  if (n >= 1e5) return `${(n / 1e5).toLocaleString("en-IN", { maximumFractionDigits: 2 })} lakh`;
  return n.toLocaleString("en-IN");
}

const dealTrack = (deal: NonNullable<CardBody["deal_value"]>) => TRACKS[deal.kind === "ORDER" ? "ORDER" : deal.kind === "CAPEX" ? "CAPEX" : "DEAL"];

/** The deal block's tiles: the value (or that the filing gave none), the other party, the scope and the term. A
 * model's placeholder ("to be determined") is not a fact and is left out. */
function dealFacts(card: CardBody): { label: string; value: string; text?: boolean; none?: boolean }[] {
  const deal = card.deal_value, amount = card.scale?.amount_cr ?? deal?.amount_cr ?? null;
  const said = [plain(card.headline), ...card.what_happened.map((f) => (typeof f === "string" ? f : `${f.text} ${f.quote ?? ""}`))].join(" ");
  const value = deal?.includes_gst || card.scale?.gst ? "Value, incl. GST" : saysExGst(said) ? "Value, ex GST" : "Value";
  const scope = realValue(deal?.segment), term = realValue(deal?.execution_by);
  const [termLabel, termValue] = term ? executionFact(term) : ["", ""];
  // an acquisition or sale names what changes hands and the seller apart when the card has them; older cards keep
  // the one "Counterparty"
  const target = deal && TAKES_TARGET.has(deal.kind) ? realValue(deal.target) : null;
  const seller = target && deal!.kind === "ACQUISITION" ? realValue(deal!.seller) ?? realValue(deal!.counterparty) : null;
  const party = seller ? null : realValue(deal?.counterparty);
  return [
    amount != null ? { label: value, value: cr(amount) } : { label: "Value", value: "Not disclosed", none: true },
    ...(target ? [{ label: deal!.kind === "DIVESTMENT" ? "Sold" : "Target", value: target, text: true }] : []),
    ...(seller && seller !== target ? [{ label: "Seller", value: seller, text: true }] : []),
    ...(party ? [{ label: COUNTERPARTY[deal!.kind] ?? "Counterparty", value: party, text: true }] : []),
    ...(deal?.issue_price != null ? [{ label: "Issue price", value: `₹${deal.issue_price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}` }] : []),
    ...(deal?.discount_pct != null ? [{ label: "Discount", value: `${deal.discount_pct}%` }] : []),
    ...(deal?.new_shares != null ? [{ label: "New shares", value: sharesText(deal.new_shares) }] : []),
    ...(realValue(deal?.swap_ratio) ? [{ label: "Swap ratio", value: realValue(deal?.swap_ratio)!, text: true }] : []),
    ...(scope ? [{ label: "Scope", value: scope.charAt(0).toUpperCase() + scope.slice(1), text: true }] : []),
    ...(term ? [{ label: termLabel, value: termValue }] : []),
  ];
}

/** An order, capex or capital deal gets its block when there is anything to put in it besides "not disclosed". */
function hasDealBlock(card: CardBody): boolean {
  const deal = card.deal_value;
  if (card.scale) return true;
  if (!deal) return false;
  return deal.amount_cr != null || dealFacts(card).length > 1 || dealTrack(deal).at[deal.stage] !== undefined || deal.stage === "CANCELLED";
}

/** Orders, capex and capital deals: the size, against the company, over its term, and how far it has got. */
function DealBlock({ card, filedAt }: { card: CardBody; filedAt: string }) {
  const deal = card.deal_value, scale = card.scale;
  if (!deal && !scale) return null;
  const facts = dealFacts(card);
  const track = deal ? dealTrack(deal) : null;
  const at = deal && track ? track.at[deal.stage] : undefined;
  // the first step takes the stage's own name (LOI, LOA) only while the deal is there: a contract's ladder read
  // "Contract, Contract, Execution" (Newgen); the current step carries the filing's date
  const when = istDate(filedAt).split(" ").slice(0, 2).join(" ");
  const steps = deal && track && at !== undefined ? track.steps.map((s, i) => {
    const label = i === 0 && at === 0 && deal.kind === "ORDER" ? STAGE_LABEL[deal.stage] ?? s
      : i === 1 && at === 1 && track === TRACKS.DEAL ? (deal.stage === "SHAREHOLDER_APPROVED" ? "Shareholders" : deal.stage === "TERMS_FINALISED" ? "Terms" : "Board") : s;
    return i === at ? `${label} · ${when}` : label;
  }) : null;
  const title = deal?.kind === "ORDER" ? "The order" : deal?.kind === "CAPEX" ? "The capex" : deal?.kind === "FUNDRAISE" ? "The raise" : "The deal";
  return (
    <BlockShell title={title}>
      <dl className={cn("grid gap-2", facts.length >= 4 ? "grid-cols-2 sm:grid-cols-4" : facts.length === 3 ? "grid-cols-2 sm:grid-cols-3" : "grid-cols-2")}>
        {facts.map((f) => (
          <div key={f.label} className="min-w-0 rounded-xl bg-surface-2 px-2.5 py-1.5">
            <dt className="text-[11px] font-bold text-ink-3">{f.label}</dt>
            <dd className={cn("line-clamp-2 break-words text-[13.5px] font-bold", f.none ? "font-semibold text-ink-3" : "text-ink", !f.text && !f.none && "num")}
              title={f.value}>{f.value}</dd>
          </div>
        ))}
      </dl>
      {(scale?.against ?? []).slice(0, 2).map((a) => <SizeBar key={a.label} label={`Against ${a.label} (${cr(a.base_cr)})`} pct={a.pct} />)}
      {scale?.per_year && (
        <p className="text-[12.5px] text-ink-2">Over its {scale.per_year.years}-year term: <span className="num font-bold text-ink">{scale.per_year.pct.toFixed(1)}%</span> of {scale.per_year.label} a year.</p>
      )}
      {deal?.stage === "CANCELLED" ? <p className="text-[12.5px] font-bold text-neg">Cancelled or withdrawn.</p>
        : steps && <Steps steps={steps} at={at!} warn={PROVISIONAL_STAGES.has(deal!.stage)} />}
    </BlockShell>
  );
}

const LONG_TERM = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-", "C+", "C", "C-", "D"];

/** A credit rating: before and after on the agency's long-term scale. */
const OUTLOOK_RANK: Record<string, number> = { negative: 0, developing: 1, watch: 1, stable: 2, positive: 3 };
const outlookRank = (o: string | null) => (o ? Object.entries(OUTLOOK_RANK).find(([k]) => o.toLowerCase().includes(k))?.[1] : undefined);

function RatingBlock({ rc, amount }: { rc: NonNullable<CardBody["rating_change"]>; amount: string | null }) {
  const a = LONG_TERM.indexOf(rc.after), b = rc.before ? LONG_TERM.indexOf(rc.before) : -1;
  const lo = Math.max(0, Math.min(a, b < 0 ? a : b) - 2), hi = Math.min(LONG_TERM.length - 1, Math.max(a, b) + 2);
  const n = rc.notches;
  const move = n == null ? "First rating in memory" : n === 0 ? "Grade unchanged" : `${Math.abs(n)} notch${Math.abs(n) > 1 ? "es" : ""} ${n > 0 ? "↑" : "↓"}`;
  const was = outlookRank(rc.before_outlook), now = outlookRank(rc.after_outlook);
  const outlook = rc.before && was != null && now != null && was !== now ? `outlook ${now > was ? "↑" : "↓"}` : null;
  const down = (n ?? 0) < 0 || /negative/i.test(rc.after_outlook ?? "") && !/negative/i.test(rc.before_outlook ?? "");
  return (
    <BlockShell title={["Rating move", rc.agency, amount].filter(Boolean).join(" · ")}>
      <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2.5">
        <div className="rounded-xl bg-surface-2 px-3 py-2">
          <b className="num block text-[19px] font-extrabold">{rc.before ?? "—"}</b>
          <span className="text-[11.5px] font-semibold text-ink-3">{rc.before_outlook ?? "before"}{rc.as_of_before ? ` · ${istDate(rc.as_of_before)}` : ""}</span>
        </div>
        <span className={cn("text-center text-[11.5px] font-extrabold", down ? "text-neg" : n && n > 0 ? "text-pos" : "text-ink-2")}>{move}{outlook && <><br />{outlook}</>}{!n && !outlook && <><br />→</>}</span>
        <div className={cn("rounded-xl px-3 py-2", down ? "bg-neg-soft" : n && n > 0 ? "bg-pos-soft" : "bg-surface-2")}>
          <b className={cn("num block text-[19px] font-extrabold", down ? "text-neg" : n && n > 0 ? "text-pos" : "text-ink")}>{rc.after}</b>
          <span className="text-[11.5px] font-semibold text-ink-3">{rc.after_outlook ?? "now"}</span>
        </div>
      </div>
      {a >= 0 && (
        <div className="num flex flex-wrap gap-1 text-[11px] font-semibold text-ink-3" aria-label="Rating scale">
          {LONG_TERM.slice(lo, hi + 1).map((g) => (
            <span key={g} className={cn("rounded-md px-1.5 py-0.5", g === rc.after ? (down ? "bg-neg text-white" : "bg-[var(--fam)] text-white")
              : g === rc.before ? "outline outline-[1.5px] outline-ink-3" : "bg-surface-2")}>{g}</span>
          ))}
        </div>
      )}
    </BlockShell>
  );
}

function CaseBlock({ cs }: { cs: NonNullable<CardBody["case_stage"]> }) {
  return (
    <BlockShell title={cs.track === "USFDA" ? "Where the USFDA case stands" : "Where the case stands"}>
      <Steps steps={cs.steps} at={cs.at} reached={cs.reached ?? Array.from({ length: cs.at + 1 }, (_, i) => i)} warn={cs.at < cs.steps.length - 1} />
    </BlockShell>
  );
}

/** Context for a decision, all from memory: what memory held before the filing, and the next check. */
function decisionLines(row: CardRow, card: CardBody, _table: ResultsSnapshot | null, faceText: string) {
  const out: { label: string; text: string; tone?: "pos" | "neg" | "warn"; computed?: boolean }[] = [];
  const ageDays = (Date.now() - Date.parse(row.filed_at)) / 86400_000;
  const recent = ageDays <= 120;   // a "next check" from an old card describes a quarter long gone
  // No "Since the filing" price line (owner, 2026-10-20): the move is tracked inside, by the price post-mortem
  // No run-rate P/E (owner, 2026-10-20: "none of the cards needs it"): the space goes to up to four things memory held
  // before this filing (memory_context: guidance, the latest quarter, a holding shift, a watch item, an operating note);
  // an older card without the block shows its guidance
  const memory = card.memory_context?.length ? card.memory_context : (card.guidance_recall ?? []).map((g) => ({
    label: `Management said${g.given_on ? `, ${istDate(g.given_on).split(" ").slice(1).join(" ")}` : ""}`,
    text: `${g.statement}${g.target && !g.statement.includes(g.target) ? ` (${g.target})` : ""}${g.due ? ` · by ${g.due}` : ""}`,
  }));
  for (const m of memory.filter((m) => !repeats(m.text, faceText)).slice(0, 4)) out.push({ label: m.label, text: m.text });
  const next = recent ? card.track_next?.kpis_to_verify?.find((k) => k.check_in) : undefined;
  if (next) out.push({ label: `Next check, ${next.check_in}`, text: `${next.kpi}${next.target ? ` (${next.target})` : ""}`, tone: "warn" });
  return out;
}

/** Copy as image, verify against the PDF and the company memory: one button, not three. */
function MoreMenu({ items }: { items: { label: string; icon: LucideIcon; onClick: () => void; hidden?: boolean }[] }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", escape); };
  }, [open]);
  return (
    <span ref={box} className="relative">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-label="More actions" title="More"
        className="grid h-8 w-8 place-items-center rounded-lg text-ink-2 hover:bg-surface-2 hover:text-ink">
        <MoreHorizontal className="h-4 w-4" />
      </button>
      {open && (
        <span role="menu" className="absolute bottom-9 right-0 z-20 w-56 rounded-xl border border-line bg-surface p-1 shadow-lg">
          {items.filter((i) => !i.hidden).map(({ label, icon: Icon, onClick }) => (
            <button key={label} type="button" role="menuitem" onClick={() => { setOpen(false); onClick(); }}
              className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium text-ink hover:bg-surface-2">
              <Icon className="h-4 w-4 text-ink-3" />{label}
            </button>
          ))}
        </span>
      )}
    </span>
  );
}

/** One announcement as a self-contained card. Each fact is said once (owner, 2026-10-19: "lots of repeated items"), and
 * the card takes its event family's colour and block: the results table, the order's size and stage, the rating move,
 * where a case stands. In a list it opens from a row, and `onCollapse` folds it back. */
export function AnnouncementCard({ row, defaultOpen = false, highlight = false, onCollapse }: {
  row: CardRow; defaultOpen?: boolean; highlight?: boolean; onCollapse?: () => void;
}) {
  const card = useMemo(() => parseCard(row), [row]);
  const [open, setOpen] = useState(defaultOpen);
  const [exporting, setExporting] = useState(false);
  const [copy, setCopy] = useState<"idle" | "copied" | "saved" | "error">("idle");
  const ref = useRef<HTMLElement>(null);
  const [, setParams] = useQueryState();
  const openMemory = (verify?: string) => setParams({ memory: row.scrip_code, verify: verify ?? null, mtab: verify ? "verify" : null });
  const owner = useRatings();
  if (!card) return null;

  const tone = (card.tone ?? "NEUTRAL") as Tone;
  const event = card.event_type || row.event_category;
  const family = FAMILY[event] ?? "oth";
  const FamilyIcon = FAMILY_ICON[family];
  const deal = card.deal_value;
  const review = !!row.needs_review;
  // Held cards reach only the owner's feed (private launch, owner 2026-10-19).
  const held = !!row.held;
  const g = card.grounding;
  const allMatched = g.ungrounded.length === 0 && !g.math_mismatches && !(g.unsupported_claims ?? []).length;
  // A garbled scan or an owner's hold outlives a correction: it is why a corrected card is still unverified.
  const issues = [...(card.review?.held ?? []), ...(card.review?.issues?.length ? card.review.issues
    : [...(card.grounding.unsupported_claims ?? []).map((c) => `Claim not supported by the sources: "${c}"`),
       ...(card.grounding.ungrounded.length ? [`Numbers not found in the filing: ${card.grounding.ungrounded.join(", ")}`] : [])])];
  const corrected = card.review?.status === "CORRECTED";
  const longRead = event === "CONCALL_PRESENTATION" || event === "ANNUAL_REPORT";  // a 100-400 page document
  const tilesFor = longRead || (event === "RESULTS" && !card.results);
  // a call or presentation shows the quarter it discusses, as the results filing gave it (design audit fix 10)
  const table = (event === "RESULTS" || event === "CONCALL_PRESENTATION") && tableShows(card.results) ? card.results : null;
  const dealBlock = !table && (family === "ord" || family === "cap") && hasDealBlock(card);
  const rating = event === "DEBT_RATINGS" ? card.rating_change ?? null : null;
  const caseStage = card.case_stage ?? null;

  // Repeats out: a point that restates the headline, a fact the table or block already shows
  const headline = plain(card.headline);
  const factLimit = event === "RESULTS" || longRead ? 4 : 3;
  // key tiles the headline already gives are left out; the rest wait in "Full analysis"
  const tiles = tilesFor && card.key_numbers.length >= 2 ? tilesBesides(card.key_numbers, headline).slice(0, 4) : [];
  const rated = rating ? ratedAmount(headline, ...card.what_happened.filter((f) => verifiedFact(f, g.ungrounded)).map(plain)) : null;
  // every figure and name the table, tiles and blocks show, so a point, a line or a chip that only restates them is
  // left out too (UCO's Key numbers repeated the table's EPS)
  const blockText = [
    table ? resultLines(table).flatMap(({ line }) => [line.value, line.prev_year, line.prev_quarter, line.yoy_pct, line.qoq_pct, line.yoy_bps, line.qoq_bps])
      .filter((v): v is number => v != null).map((v) => String(Math.abs(v))).join(" ") : "",
    dealBlock ? [...dealFacts(card).map((f) => f.value), ...(card.scale?.against ?? []).flatMap((a) => [a.pct.toFixed(1), a.base_cr]),
                 card.scale?.per_year?.pct.toFixed(1)].filter((x) => x != null).join(" ") : "",
    rating ? `${rating.agency ?? ""} ${rating.after} ${rating.after_outlook ?? ""} ${rating.before ?? ""} ${rating.before_outlook ?? ""} ${rated ?? ""}` : "",
    tiles.map((k) => `${k.label} ${k.value} ${k.change ?? ""}`).join(" "),
    (card.volume_strip?.months ?? []).map((m) => `${m.value} ${m.yoy_pct ?? ""}`).join(" "),
  ].join(" ");
  const unique = card.what_happened.filter((fact) => !(table && coveredByTable(fact, table)) && !repeats(plain(fact), `${headline} ${blockText}`));
  // the verified face: only facts whose quoted sentence code found in the filing; the rest is the AI's reading
  const split = splitFacts(unique, g.ungrounded, factLimit);
  const facts = split.face, unverified = split.unverified;
  const shownText = [headline, blockText, ...facts.map(plain)].join(" ");
  const box = boxItems(card, (s) =>
    (s.type === "SCALE" && ((dealBlock && !!card.scale) || restatesHeadline(s.text, headline)))
    || (s.type === "RATING_LIQUIDITY" && !!rating && /outlook/i.test(s.text)) || repeats(s.text, shownText));
  const faceText = [shownText, ...box.insights.map((i) => i.text), box.signal?.text ?? ""].join(" ");
  const decision = decisionLines(row, card, table, faceText);
  const calls = event === "CONCALL_PRESENTATION" ? callTakeaways(card.call_takeaways, card.call_memory) : null;
  // the sector's KPI chips belong to results; on an order or a rating they said nothing about the news
  const footer = family !== "res" ? []
    : footerMetrics(card).filter((m) => !showsFigure(faceText, m.value) && !(table && /margin/i.test(m.label)));
  const thin = row.median_turnover_cr != null && row.median_turnover_cr < 0.5;
  const credibility = card.score?.credibility;
  const familyLabel = [EVENT_LABELS[event] ?? card.category_tag, table?.period, card.basis ? BASIS_LABEL[card.basis]?.toLowerCase() : null,
    table?.lens === "bank" ? "bank lens" : table?.lens === "insurer" ? "insurer lens" : null].filter(Boolean).join(" · ");
  const direction = DIRECTION[tone];

  async function share() {
    if (!ref.current) return;
    const node = ref.current;
    flushSync(() => setExporting(true));
    try {
      setCopy(await copyNodeAsPng(node, `${row.symbol ?? row.scrip_code}-${row.filing_date}.png`));
    } catch {
      setCopy("error");
    } finally {
      setExporting(false);
      setTimeout(() => setCopy("idle"), 2000);
    }
  }

  return (
    <article ref={ref} id={`card-${row.news_id}`} style={famStyle(family)}
      className={cn("card-soft card-lift rise-in relative", highlight && "ring-2 ring-accent")}>
      <div className="px-3.5 pb-3 pt-4 sm:px-6 sm:pt-5">
        {exporting && (
          <div className="mb-3 flex items-baseline justify-between text-[12px]">
            <span className="font-semibold text-accent">Insiders · NSE</span>
            <span className="num text-ink-3">{istDate(row.filed_at)}</span>
          </div>
        )}
        {exporting && review && (
          <p className="mb-3 flex items-center gap-2 rounded-lg bg-warn-soft px-3 py-1.5 text-[12px] font-medium text-warn">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> Unverified: some figures could not be matched to the filing. Check the official PDF.
          </p>
        )}

        {held && !exporting && (
          <div className="-mt-1 mb-3 rounded-lg border border-neg/40 bg-neg-soft px-3 py-2 text-[12.5px] leading-relaxed text-neg" data-noexport="true">
            <p className="flex items-center gap-2 font-semibold">
              <ShieldAlert className="h-3.5 w-3.5 shrink-0" /> Held: not on the public feed. Only you see this card.
            </p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5">
              {(issues.length ? issues : ["The checks could not verify this card."]).map((p, i) => <li key={i}>{p}</li>)}
            </ul>
          </div>
        )}

        {review && !held && !exporting && (
          <p className="-mt-1 mb-3 flex items-start gap-2 rounded-lg bg-warn-soft px-3 py-2 text-[12.5px] leading-relaxed text-warn" data-noexport="true">
            <AlertTriangle className="mt-[2px] h-3.5 w-3.5 shrink-0" />
            <span><span className="font-semibold">Unverified.</span> {issues[0] ?? "Some numbers could not be matched to the filing."}
              {card.review?.checked_by && !corrected ? " A second AI could not resolve it." : ""} Check the official PDF before relying on it.</span>
          </p>
        )}

        <header className="flex items-center justify-between gap-3">
          <button type="button" onClick={() => openMemory()}
            className="group flex min-w-0 items-center gap-3 text-left" title={`${row.company_name}: open the company memory`}>
            <Avatar name={row.company_name} symbol={row.symbol} size={44} />
            <span className="min-w-0">
              <span className="block truncate text-[16px] font-extrabold tracking-tight text-ink group-hover:text-accent">
                {row.company_name}
              </span>
              <span className="num block truncate text-[12px] font-medium text-ink-3">
                {row.symbol ?? row.scrip_code}
                {row.market_cap_cr != null && <span className="font-sans font-semibold"> · {cr(row.market_cap_cr)}{row.size_category ? ` · ${titleCase(row.size_category)} cap` : ""}</span>}
              </span>
            </span>
          </button>
          {row.last_price != null && (
            <span className="num shrink-0 text-right">
              <span className="block text-[15px] font-bold text-ink">₹{row.last_price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              {row.ret_1w != null && <span className={cn("block text-[12px] font-semibold", signClass(row.ret_1w))}>{row.ret_1w >= 0 ? "▲" : "▼"} {Math.abs(row.ret_1w).toFixed(1)}% 1W</span>}
            </span>
          )}
        </header>

        <div className="mt-3 flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-[12.5px] font-bold">
          <span className={cn("inline-flex items-center gap-1.5 rounded-full py-[3px] pl-1 pr-2.5", GRADE[row.impact_level])}
            title={card.score ? `Actionability ${card.score.total}/100, computed from the filing and memory` : undefined}>
            {card.score && <i className="num rounded-full bg-surface px-1.5 text-[11px] not-italic">{row.is_actionable_signal ? "🔥" : ""}{card.score.total}</i>}
            {IMPACT_SHORT[row.impact_level]}
          </span>
          {direction && <span className={direction.cls}>{direction.mark} {TONE_LABEL[tone]}</span>}
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--fam-soft)] px-2.5 py-[3px] text-[var(--fam)]">
            <FamilyIcon className="h-3.5 w-3.5" />{familyLabel}
          </span>
          {deal?.updates_deal_id && <span className="text-ink-3">Update to an earlier deal</span>}
          {(family === "ord" || family === "cap") && !dealBlock && deal && STAGE_LABEL[deal.stage] && PROVISIONAL_STAGES.has(deal.stage)
            && <span className="text-warn">{STAGE_LABEL[deal.stage]}</span>}
          {credibility != null && credibility < 50 && <span className="text-warn">🎯 Credibility {Math.round(credibility)}%</span>}
          {thin && <span className="text-warn" title="Median traded value a day">💧 ₹{row.median_turnover_cr!.toFixed(2)} Cr a day</span>}
          <TechnicalTags row={row} />
        </div>

        <h3 className="mt-3 font-display text-[18px] leading-snug text-ink sm:text-[19.5px]">{headline}</h3>

        {card.call_read && <CallReadChips read={card.call_read} />}
        {table && <ResultsTable r={table} judged={verdict(tone, row.impact_level)} />}
        {dealBlock && <DealBlock card={card} filedAt={row.filed_at} />}
        {rating && <RatingBlock rc={rating} amount={rated} />}
        {caseStage && <CaseBlock cs={caseStage} />}
        {card.volume_strip && <VolumeStrip s={card.volume_strip} />}
        {tiles.length > 0 && <KeyBlock items={tiles} />}

        {facts.length > 0 && (
          <ul className="mt-3 space-y-2">
            {facts.map((fact, i) => <Point key={i}><RichText text={fact} /></Point>)}
          </ul>
        )}

        {(box.signal || box.missing) && (
          <section className="mt-4 rounded-2xl bg-[var(--fam-soft)] px-4 py-3">
            <h4 className="text-[11px] font-bold uppercase tracking-[0.1em] text-[var(--fam)]">{boxLabel(event)}</h4>
            <ul className="mt-2 space-y-2">
              {box.signal && <Point><SignalLine s={box.signal} /></Point>}
              {box.missing && (
                <Point><span className="font-semibold text-warn">Not disclosed:</span> {box.missing}</Point>
              )}
            </ul>
          </section>
        )}

        {decision.length > 0 && (
          <section className="mt-3 rounded-2xl bg-[var(--fam-soft)] px-4 py-3">
            <h4 className="text-[11px] font-bold uppercase tracking-[0.1em] text-[var(--fam)]">For the decision</h4>
            <ul className="mt-2 space-y-2">
              {decision.map((d) => (
                <Point key={d.label}>
                  <span className={cn("font-semibold", d.tone === "warn" ? "text-warn" : "text-[var(--fam)]")}>{d.label}:</span>{" "}
                  <span className={cn(d.tone === "pos" ? "text-pos" : d.tone === "neg" ? "text-neg" : undefined)}>{d.text}</span>
                  {d.computed && <span className="ml-1.5 text-[10.5px] font-medium text-ink-3">✓ computed</span>}
                </Point>
              ))}
            </ul>
          </section>
        )}

        {calls?.source && <CallTakeaways view={calls} />}

        {!exporting && <AiReading catalyst={card.core_catalyst && !repeats(plain(card.core_catalyst), headline) ? plain(card.core_catalyst) : null}
          facts={[...unverified, ...(calls?.unverified ?? [])]} insights={box.insights.map((i) => i.text)} takeaway={box.fallback ?? null} />}

        {footer.length > 0 && (
          <div className="mt-3 flex flex-wrap items-baseline gap-2 text-[12px] font-semibold text-ink-3">
            {footer.map((m) => (
              <span key={m.label} className="rounded-[10px] bg-surface-2 px-2.5 py-1" title={m.period ? `${m.label}, ${m.period}` : undefined}>{m.label} <span className="num font-bold text-ink">{m.value}</span></span>
            ))}
          </div>
        )}

        {exporting ? (
          <p className="mt-2 text-[10.5px] text-ink-3">AI summary of a public NSE filing. Not investment advice; verify against the original filing.</p>
        ) : (
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-line pt-2.5 text-[12px] text-ink-3" data-noexport="true">
            <span className="num" title={`${istDateTime(row.filed_at)} IST · ${relativeTime(row.filed_at)}`}>
              {istDateTime(row.filed_at)}
              {row.market_session ? ` · ${SESSION_LABEL[row.market_session] ?? ""}` : ""}
            </span>
            {review ? (
              <span className="inline-flex items-center gap-1 font-medium text-warn" title={issues.join(" · ")}>
                <AlertTriangle className="h-3.5 w-3.5" /> Unverified
              </span>
            ) : corrected ? (
              <span className="inline-flex items-center gap-1" title={`Corrected by ${card.review?.checked_by}: ${(card.review?.fixed ?? []).join(" · ")}`}>
                <RefreshCcw className="h-3.5 w-3.5 text-pos" /> Re-checked
              </span>
            ) : g.checked > 0 && allMatched ? (
              <span className="inline-flex items-center gap-1 font-semibold text-pos" title={`All ${g.checked} numbers were found in the filing or company memory`}>
                <BadgeCheck className="h-3.5 w-3.5" /> {g.checked} numbers verified
              </span>
            ) : g.checked > 0 ? (
              <span className="num inline-flex items-center gap-1" title={g.ungrounded.length ? `Not found: ${g.ungrounded.join(", ")}` : undefined}>
                <BadgeCheck className="h-3.5 w-3.5 text-ink-3" /> {Math.max(0, g.checked - g.ungrounded.length)} of {g.checked} numbers matched
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
              {owner.token && (
                <>
                  <button type="button" onClick={() => owner.rate(row.news_id, "STARRED")} aria-pressed={owner.ratings[row.news_id] === "STARRED"}
                    title="Star signal: show more cards like this" aria-label="Star signal"
                    className={cn("grid h-8 w-8 place-items-center rounded-lg hover:bg-surface-2", owner.ratings[row.news_id] === "STARRED" ? "text-accent" : "text-ink-2")}>
                    <Flame className="h-4 w-4" />
                  </button>
                  <button type="button" onClick={() => owner.rate(row.news_id, "NOISE")} aria-pressed={owner.ratings[row.news_id] === "NOISE"}
                    title="Mark noise: show fewer cards like this" aria-label="Mark noise"
                    className={cn("grid h-8 w-8 place-items-center rounded-lg hover:bg-surface-2", owner.ratings[row.news_id] === "NOISE" ? "text-warn" : "text-ink-2")}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </>
              )}
              <MoreMenu items={[
                { label: copy === "idle" ? "Copy card as image" : copy === "error" ? "Could not copy" : "Copied", icon: copy === "error" ? AlertTriangle : copy === "idle" ? Camera : Check, onClick: share },
                { label: "Verify against the PDF", icon: FileSearch, onClick: () => openMemory(row.news_id), hidden: !row.pdf_url },
                { label: "Company memory", icon: Building2, onClick: () => openMemory() },
              ]} />
              {onCollapse && (
                <button type="button" onClick={onCollapse} aria-label="Fold back into the list" title="Fold back into the list"
                  className="grid h-8 w-8 place-items-center rounded-lg text-ink-2 hover:bg-surface-2 hover:text-ink">
                  <ChevronUp className="h-4 w-4" />
                </button>
              )}
            </span>
          </div>
        )}
      </div>
      {!exporting && <VerdictBar newsId={row.news_id} />}
      {open && !exporting && (
        <DeepDive row={row} card={card} shown={box.insights.length} shownSignal={box.signal}
          moreFacts={split.more} faceText={faceText} thinShown={thin}
          keyNumbers={card.key_numbers.filter((k) => !tiles.includes(k) && !showsFigure(faceText, k.value))} />
      )}
    </article>
  );
}

const VERDICTS: { v: Verdict; label: string; on: string }[] = [
  { v: "RIGHT", label: "Right", on: "border-pos bg-pos/10 text-pos" },
  { v: "MINOR", label: "Minor issue", on: "border-warn bg-warn-soft text-warn" },
  { v: "WRONG", label: "Wrong", on: "border-neg bg-neg-soft text-neg" },
];

/** The owner's verdict on the card and a note on what is wrong, stored with the card as judged (owner only). */
function VerdictBar({ newsId }: { newsId: string }) {
  const { token, verdicts, judge } = useVerdicts();
  const mine = verdicts[newsId];
  const [note, setNote] = useState<string | null>(null);
  if (!token) return null;
  const text = note ?? mine?.note ?? "";
  const pick = (v: Verdict) => {
    void judge(newsId, mine?.verdict === v ? "CLEAR" : v, text);
  };
  const save = () => {
    if (mine && note !== null && note !== mine.note) void judge(newsId, mine.verdict, note);
  };
  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-line px-3.5 py-2.5 sm:px-6" data-noexport="true">
      <span className="text-[12px] font-medium text-ink-3">Your verdict</span>
      {VERDICTS.map(({ v, label, on }) => (
        <button key={v} type="button" onClick={() => pick(v)} aria-pressed={mine?.verdict === v}
          className={cn("rounded-full border px-2.5 py-[3px] text-[12px] font-medium", mine?.verdict === v ? on : "border-line text-ink-2 hover:bg-surface-2")}>
          {label}
        </button>
      ))}
      <input value={text} onChange={(e) => setNote(e.target.value)} onBlur={save}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
        placeholder={mine ? "What is wrong? (saved when you leave the box)" : "Pick a verdict, then add a note"}
        disabled={!mine} maxLength={1000}
        className="h-8 min-w-0 flex-1 basis-48 rounded-lg border border-line bg-surface px-2.5 text-[12.5px] text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none disabled:opacity-60" />
    </div>
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
function DeepDive({ row, card, shown, shownSignal, moreFacts, keyNumbers, faceText, thinShown }: {
  row: CardRow; card: CardBody; shown: number; shownSignal?: Signal;
  moreFacts: Fact[]; keyNumbers: CardBody["key_numbers"]; faceText: string; thinShown: boolean;
}) {
  const more = card.why_it_matters.slice(shown);
  // The summary box above already shows the top-ranked signal, so showing every signal here printed it
  // twice on one card - the Scale line read the same in both places. The card is a page in a pocket
  // diary: a line that repeats costs a reader more than it tells them.
  const restSignals = card.signals.filter((s) => s !== shownSignal && !repeats(s.text, faceText));
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
    <div className="space-y-5 border-t border-line bg-surface-2/30 px-3.5 py-5 sm:px-6" data-noexport="true">
      {moreFacts.length > 0 && (
        <Section label="More from the filing">
          <ul className="space-y-2">{moreFacts.map((fact, i) => <Point key={i}><RichText text={fact} /></Point>)}</ul>
        </Section>
      )}

      {keyNumbers.length > 0 && (
        <Section label="Key numbers">
          <KeyTiles items={keyNumbers} />
        </Section>
      )}

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

      {restSignals.length > 0 && (
        <Section label="Signals computed from memory">
          <ul className="space-y-2">{restSignals.map((s, i) => <Point key={i}><SignalLine s={s} /></Point>)}</ul>
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

      {card.score && (
        <Section label={`How this was scored · ${card.score.total}/100`}>
          <dl className="num grid gap-x-6 gap-y-1 text-[13px] sm:grid-cols-2">
            {Object.entries(card.score.pillars).filter(([k, v]) => k !== "penalty" || v !== 0).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 border-b border-line py-1">
                <dt className="font-sans text-ink-2">{PILLAR_LABEL[k] ?? k}</dt><dd className="font-semibold text-ink">{v}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-[12.5px] text-ink-2">
            Gates: {([["magnitude", "size"], ["inflection", "inflection"], ["price", "price not run up"], ["clean", "clean checks"]] as const)
              .map(([k, label]) => `${card.score!.gates[k] ? "✓" : "✗"} ${label}`).join(" · ")}
            {card.model_impact && card.model_impact !== row.impact_level ? ` · the analyst rated it ${IMPACT_WORD[card.model_impact].toLowerCase()}` : ""}
          </p>
          {[...card.score.reasons, ...card.score.vetoes.map((v) => `Veto: ${v}`)].length > 0 && (
            <ul className="mt-1 space-y-0.5 text-[12.5px] text-ink-3">
              {[...card.score.reasons.filter((r) => !(thinShown && /^thin liquidity/i.test(r))), ...card.score.vetoes.map((v) => `Veto: ${v}`)].map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          )}
        </Section>
      )}

      <MarketReaction raw={row.post_event_return_json} atFiling={card.priced_at_filing} row={row} />

      {card.review && (
        <Section label="Second check">
          <p className="text-[13px] leading-relaxed text-ink-2">
            The first draft{card.review.first_model ? ` (${card.review.first_model})` : ""} failed the automatic checks
            {card.review.checked_by ? `, so ${card.review.checked_by} was asked to correct it` : ", and no second AI was available"}.
            {card.review.status === "CORRECTED" ? " The corrected card passed the number checks: each figure is found in the filing. The checks do not confirm that a figure means what the card says." : " Problems that remain are listed below."}
          </p>
          <ul className="mt-2 space-y-1">
            {(card.review.status === "CORRECTED" ? card.review.fixed ?? [] : card.review.issues ?? []).map((p, i) => (
              <li key={i} className={cn("text-[12.5px]", card.review!.status === "CORRECTED" ? "text-ink-3 line-through" : "text-warn")}>{p}</li>
            ))}
            {card.review.status === "CORRECTED" && (card.review.held ?? []).map((p, i) => (
              <li key={`held-${i}`} className="text-[12.5px] text-warn">{p}</li>
            ))}
          </ul>
        </Section>
      )}

      <p className="text-[12px] leading-relaxed text-ink-3">
        {g.checked > 0 ? `${g.checked} numbers checked against the filing and company memory` : "No numbers to check"}
        {g.ungrounded.length ? `; not found: ${g.ungrounded.join(", ")}` : ""}
        {g.unsupported_claims?.length ? `. Claims the sources don't support: ${g.unsupported_claims.map((c) => `"${c}"`).join(", ")}` : ""}
        {!row.memory_complete ? ". Written before this company's history finished loading" : ""}.
        {" "}AI summary of a public NSE filing; not investment advice.
      </p>
    </div>
  );
}

function signedPct(v: number | undefined) {
  return v === undefined ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}

/** Loop 1: what the stock did after the filing, against the index (filled nightly). */
function MarketReaction({ raw, atFiling, row }: { raw?: string | null; atFiling?: CardBody["priced_at_filing"]; row: CardRow }) {
  let rx: PriceReaction | null = null;
  try { rx = raw ? JSON.parse(raw) : null; } catch { rx = null; }
  const points = rx ? (["t1", "t3", "t5"] as const).filter((k) => rx![k]) : [];
  const at = atFiling?.last_price !== undefined ? atFiling : null;
  const now = ([["1W", row.ret_1w], ["1M", row.ret_1m], ["1Y", row.ret_1y]] as const).filter(([, v]) => v != null);
  if (!points.length && !at && !now.length) return null;
  return (
    <Section label="How the market reacted">
      {now.length > 0 && (
        <p className="num mb-2 flex flex-wrap gap-x-4 text-[12.5px] text-ink-2">
          <span className="font-sans">Now:</span>
          {now.map(([label, v]) => <span key={label}>{label} <span className={cn("font-semibold", signClass(v!))}>{pct(v)}</span></span>)}
        </p>
      )}
      {at && (
        <p className="num mb-2 text-[12.5px] text-ink-2">
          At filing ({at.price_date}): ₹{at.last_price!.toLocaleString("en-IN")}
          {at.market_cap_cr !== undefined ? ` · market cap ₹${Math.round(at.market_cap_cr).toLocaleString("en-IN")} Cr` : ""}
          {at.ret_1w !== undefined ? ` · 1W ${signedPct(at.ret_1w)}` : ""}{at.ret_1m !== undefined ? ` · 1M ${signedPct(at.ret_1m)}` : ""}
        </p>
      )}
      {rx && points.length > 0 && <>
      <dl className="num grid grid-cols-3 gap-x-4 text-[13px]">
        {points.map((k) => {
          const p = rx![k]!;
          const value = p.excess_pct ?? p.return_pct;
          return (
            <div key={k} className="border-b border-line py-1">
              <dt className="font-sans text-ink-3">T+{k.slice(1)}</dt>
              <dd className={cn("font-semibold", value > 0 ? "text-pos" : value < 0 ? "text-neg" : "text-ink")}>
                {signedPct(value)}{p.rvol !== undefined ? <span className="ml-1 font-normal text-ink-3">· {p.rvol.toFixed(1)}x vol</span> : null}
              </dd>
            </div>
          );
        })}
      </dl>
      <p className="mt-2 text-[12.5px] text-ink-3">
        {rx.benchmark ? `Return less the index (${rx.benchmark})` : "Raw return (no index data)"} from the close on {rx.base_date};
        day 0 is {rx.day0}.{rx.complete ? "" : " Still being measured."}
        {rx.missed_alpha ? " Flagged as missed alpha: rated below high impact, but the stock moved sharply on heavy volume." : ""}
      </p>
      </>}
    </Section>
  );
}

/** Price structure beside a fresh card (the tags describe the latest prices, so older cards skip them). */
function TechnicalTags({ row }: { row: CardRow }) {
  let tech: Technicals | null = null;
  try { tech = row.technicals_json ? JSON.parse(row.technicals_json) : null; } catch { tech = null; }
  if (!tech?.as_of) return null;
  const days = (Date.parse(tech.as_of) - Date.parse(row.filing_date)) / 86400_000;
  if (days < -3 || days > 10) return null;
  return (
    <>
      {tech.vcp && row.impact_level === "HIGH" && <span className="text-ink-2">⚡ Coiled spring</span>}
      {tech.stage2 && <span className="text-ink-2">📈 Stage 2 trend</span>}
      {tech.rvol != null && tech.rvol >= 2.5 && days >= 0 && days <= 2 && <span className="text-ink-2">Volume {tech.rvol.toFixed(1)}x</span>}
    </>
  );
}

/** The AI's own reading of the filing. Its interpretation (the catalyst, why it matters, the takeaway) sits on the
 *  face, marked as our reading and apart from the checked facts (owner 2026-10-20: "interpretation helps"; a blind
 *  review found 10% of such points overreach, so it is never shown as checked). Facts the checks could not quote stay
 *  behind a tap. */
function AiReading({ catalyst, facts, insights, takeaway }: { catalyst: string | null; facts: Fact[]; insights: string[]; takeaway: string | null }) {
  const reading = [...(catalyst ? [`Core catalyst: ${catalyst}`] : []), ...insights, ...(takeaway && !insights.length ? [takeaway] : [])];
  const unquoted = facts.map((f) => (typeof f === "string" ? f : f.text));
  if (!reading.length && !unquoted.length) return null;
  return (
    <div className="mt-3 rounded-2xl border border-dashed border-line-strong px-4 py-2" data-noexport="true">
      {reading.length > 0 && (
        <>
          <p className="text-[12px] font-bold text-ink-3">Our reading · not checked against the filing</p>
          <ul className="mt-2 space-y-2 pb-1">
            {reading.map((text, i) => <Point key={i} className="text-ink-2"><RichText text={text} /></Point>)}
          </ul>
        </>
      )}
      {unquoted.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer list-none py-1 text-[12px] font-bold text-ink-3 marker:hidden">
            <span className="mr-1 inline-block transition-transform group-open:rotate-90">›</span>
            Facts the checks could not quote ({unquoted.length})
          </summary>
          <ul className="mt-1 space-y-2 pb-1">
            {unquoted.map((text, i) => <Point key={i} className="text-ink-2"><RichText text={text} /></Point>)}
          </ul>
        </details>
      )}
    </div>
  );
}

export const OTHER_RENAME = /\(\s*now\b|\bnow\s+known\s+as\b|\brenamed\s+(?:as|to)\b/i;
// a model's placeholder stored as a name ("None", "N/A"): Persistent showed "formerly None"
const NO_NAME = /^\s*(?:none|nil|null|n[./]?\s?a\.?|not\s+applicable|-+)?\s*$/i;
// Former names stay in memory for search and on the company page, off the card header (owner, 2026-10-20).
export const formerOwnName = (n: string) => !NO_NAME.test(n) && !OTHER_RENAME.test(n);

/** Calls and presentations: the key takeaways under small headings. The model's takeaways that code verified against
 *  the filing and the memory they cite, else the points memory took from this filing (no AI); either way checked
 *  content, kept apart from the AI reading (owner, 2026-10-20). */
function CallTakeaways({ view }: { view: CallTakeawaysView }) {
  return (
    <BlockShell title="Key takeaways from the call" right={<span className="ml-auto text-[10px] font-semibold normal-case tracking-normal text-ink-3">
      {view.source === "ai" ? "checked against the filing and memory" : "from company memory"}</span>}>
      {view.groups.map((g) => (
        <div key={g.name}>
          <h5 className="text-[10.5px] font-bold uppercase tracking-[0.08em] text-ink-3">{g.name}</h5>
          <ul className="mt-1 space-y-1.5">
            {g.points.map((p, i) => (
              <Point key={i}>
                <RichText text={p.text} />
                {p.note && <span className="ml-1.5 text-[11px] font-medium text-ink-3">· {p.note}</span>}
              </Point>
            ))}
          </ul>
        </div>
      ))}
    </BlockShell>
  );
}

/** Monthly business update: the main volume over recent months, bars scaled to the largest. */
function VolumeStrip({ s }: { s: NonNullable<CardBody["volume_strip"]> }) {
  const top = Math.max(...s.months.map((m) => m.value), 1);
  return (
    <BlockShell title={`${s.metric.replace(/_/g, " ")}${s.unit === "INR_CR" ? " · ₹ Cr" : s.unit ? ` · ${s.unit.toLowerCase()}` : ""}`}>
      <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${s.months.length}, minmax(0, 1fr))` }}>
        {s.months.map((m, i) => (
          <div key={m.period} className="flex flex-col items-center gap-1">
            <div className="flex h-12 w-full items-end">
              <div className={cn("w-full rounded-t", i === s.months.length - 1 ? "bg-[var(--fam)]" : "bg-line-strong")}
                style={{ height: `${Math.max(6, (m.value / top) * 100)}%` }} title={`${m.period}: ${m.value.toLocaleString("en-IN")}`} />
            </div>
            <span className="num text-[11px] text-ink">{m.value.toLocaleString("en-IN", { maximumFractionDigits: 1 })}</span>
            <span className={cn("num text-[10.5px]", m.yoy_pct == null ? "text-ink-3" : m.yoy_pct >= 0 ? "text-pos" : "text-neg")}>
              {m.yoy_pct == null ? m.period.slice(0, 3) : `${m.yoy_pct > 0 ? "+" : ""}${m.yoy_pct.toFixed(0)}%`}
            </span>
          </div>
        ))}
      </div>
      <p className="num text-[10.5px] text-ink-3">{s.months[0].period} to {s.months[s.months.length - 1].period} · change vs a year ago</p>
    </BlockShell>
  );
}

/** One filing in a list (the List view, Today's low-impact rows): a compact row that opens into the card itself, so a
 * list never draws a second, older layout of the same filing. */
export function AnnouncementRow({ row, defaultOpen = false, highlight = false }: { row: CardRow; defaultOpen?: boolean; highlight?: boolean }) {
  const card = useMemo(() => parseCard(row), [row]);
  const [open, setOpen] = useState(defaultOpen);
  const [, navigate] = useLocation();
  if (!card) return null;
  if (open) return <AnnouncementCard row={row} highlight={highlight} onCollapse={() => setOpen(false)} />;
  const tone = (card.tone ?? "NEUTRAL") as Tone;
  const warnings = card.signals.filter((s) => s.severity === "WARNING").length;
  const positives = card.signals.filter((s) => s.severity === "POSITIVE").length;

  return (
    <article id={`card-${row.news_id}`}
      className={cn("card-soft card-lift relative overflow-hidden !rounded-2xl", highlight && "ring-2 ring-accent")}>
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-[3px]", TONE_STRIPE[tone])} />
      {/* The whole row opens the card; the headline is the accessible toggle button. */}
      <div onClick={() => setOpen(true)} className="cursor-pointer px-4 py-3.5 pl-5 sm:px-5 sm:pl-6">
        <div className="flex items-start gap-4">
          <h3 className="min-w-0 flex-1 font-display text-[15px] font-semibold leading-snug text-ink">
            <button type="button" aria-expanded={false} onClick={(e) => { e.stopPropagation(); setOpen(true); }}
              className="text-left hover:text-accent focus-visible:text-accent">
              {plain(card.headline)}
            </button>
          </h3>
          <span className="flex shrink-0 items-center gap-2 pt-0.5">
            <span className={cn("eyebrow hidden sm:inline", IMPACT_TEXT[row.impact_level])}>{IMPACT_LABEL[row.impact_level]}</span>
            <ChevronDown aria-hidden className="h-4 w-4 text-ink-3" />
          </span>
        </div>
        {card.takeaway ? (
          <p className="mt-1 line-clamp-2 text-[13.5px] leading-relaxed text-ink-2 sm:line-clamp-1"><span title="The AI's reading, not verified against the filing" className="mr-1.5 rounded bg-surface-2 px-1 py-px align-[1px] text-[10px] font-bold uppercase tracking-wide text-ink-3">AI</span>{card.takeaway}</p>
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
    </article>
  );
}
