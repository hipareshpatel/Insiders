import { ArrowDown, ArrowRight, ArrowUp, PanelRight } from "lucide-react";
import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "wouter";
import type { KpiRow, View } from "../../../shared/resultsTypes";
import { cn } from "../../lib/cn";
import { companyPath } from "../../lib/format";
import { ebitdaSlot, fmtCrAmount, marginLine } from "../../lib/resultsPaired";
import {
  blankNote, filedDay, NBFC_EBITDA_NOTE, fmtGrowth, fmtPts, MOMENTUM_TEXT, notComparableText, sharedScale, type Sort,
} from "../../lib/resultsView";
import { CompanyCell, Growth, Paired, Skeleton, TurnPill } from "./bits";
import { Dumbbell } from "./charts";

export const rowKey = (r: Pick<KpiRow, "symbol" | "scrip_code">) => r.symbol || r.scrip_code;

interface TableProps {
  rows: KpiRow[];
  view: View;
  sort: Sort;
  dir: "asc" | "desc";
  onSort: (s: Sort) => void;
  selected: string | null;
  onSelect: (r: KpiRow | null) => void;
}

function Th({ children, hint, title, sortKey, sort, dir, onSort, left, className }: {
  children: ReactNode; hint?: ReactNode; title?: string; sortKey?: Sort; sort: Sort; dir: "asc" | "desc"; onSort: (s: Sort) => void; left?: boolean; className?: string;
}) {
  const on = sortKey != null && sortKey === sort;
  const Arrow = dir === "asc" ? ArrowUp : ArrowDown;
  const body = (
    <>
      <span className={cn("inline-flex items-center gap-1", on && "text-ink")}>{children}{on && <Arrow aria-hidden className="h-3 w-3 text-accent" />}</span>
      {hint && <span className="block text-[12px] font-normal text-ink-3">{hint}</span>}
    </>
  );
  return (
    <th scope="col" title={title} aria-sort={sortKey ? (on ? (dir === "asc" ? "ascending" : "descending") : "none") : undefined}
      className={cn("whitespace-nowrap border-b border-line px-2.5 py-2.5 align-bottom text-[13px] font-semibold text-ink-2", left ? "text-left" : "text-right", className)}>
      {sortKey ? <button type="button" onClick={() => onSort(sortKey)} className={cn("rounded hover:text-ink", left ? "text-left" : "text-right")}>{body}</button> : body}
    </th>
  );
}

/** The quiet second line under a figure (the pace columns). */
const Sm = ({ children }: { children: ReactNode }) => <div className="num mt-0.5 text-[13px] text-ink-3">{children}</div>;
const Muted =({ children, title }: { children: ReactNode; title?: string }) => <span className="text-[13px] text-ink-3" title={title}>{children}</span>;
/** A growth with no figure says why on hover (U4, 31 Oct 2026). */
const NO_BASE = (qoq?: boolean) => (qoq ? "No prior-quarter figure to compare" : "No year-ago figure to compare");

function RevenueCell({ r, qoq }: { r: KpiRow; qoq?: boolean }) {
  if (r.kind === "insurer" || (r.revenue == null && (qoq ? r.revenue_qoq : r.revenue_yoy) == null)) return <Muted title={blankNote(r.kind, "revenue") || undefined}>—</Muted>;
  return <Paired amount={fmtCrAmount(r.revenue)} value={qoq ? r.revenue_qoq : r.revenue_yoy} noBase={NO_BASE(qoq)} />;
}

/** EBITDA beside its growth with the margin under it; a bank or insurer says "no EBITDA"; an NBFC's slot is its financing profit. */
function EbitdaCell({ r, qoq }: { r: KpiRow; qoq?: boolean }) {
  if (ebitdaSlot(r.kind) === "none") return <Muted title={r.kind === "bank" ? "Banks have no EBITDA; their financing profit is in the quick look" : undefined}>no EBITDA</Muted>;
  const turn = qoq ? null : r.ebitda_turn;
  const margin = marginLine(r, qoq);
  if (r.ebitda == null && (qoq ? r.ebitda_qoq : r.ebitda_yoy) == null && !turn) return <Muted>—</Muted>;
  return (
    <>
      <Paired amount={fmtCrAmount(r.ebitda)} value={qoq ? r.ebitda_qoq : r.ebitda_yoy} turn={turn} noBase={NO_BASE(qoq)} />
      {margin && <span className="num mt-0.5 block text-[12.5px] text-ink-3" title={r.kind === "nbfc" ? NBFC_EBITDA_NOTE : "100 bp = 1 percentage point"}>{margin}</span>}
    </>
  );
}

function ProfitCell({ r, qoq }: { r: KpiRow; qoq?: boolean }) {
  return <Paired amount={fmtCrAmount(r.pat)} value={qoq ? r.pat_qoq : r.pat_yoy} turn={qoq ? r.pat_qoq_turn : r.pat_turn} noBase={NO_BASE(qoq)} className="font-semibold" />;
}

function Filed({ r }: { r: KpiRow }) {
  return (
    <>
      <span className="whitespace-nowrap text-ink" title={!r.filed_at && !r.filing_url ? "No filing date or link on NSE yet" : undefined}>{filedDay(r.filed_at)}</span>
      {r.filing_url && (
        <div>
          {/* the ::before reaches a 44x44 touch area (the link is 38x18) without moving anything */}
          <a href={r.filing_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} title="Open the filing on NSE"
            className="relative inline-block text-[13px] font-semibold text-accent before:absolute before:-inset-x-[3px] before:-inset-y-[13px] before:content-[''] hover:underline">NSE<span aria-hidden> ↗</span><span className="sr-only"> filing (opens in a new tab)</span></a>
        </div>
      )}
    </>
  );
}

/** Profit and revenue pace: this quarter's growth minus last quarter's, in points. */
function Pace({ now, was, pts, big }: { now: number | null; was: number | null; pts: number | null; big?: boolean }) {
  if (pts == null || now == null || was == null) return <span className="font-medium text-ink-3">—</span>;
  return (
    <>
      <span className={cn("num whitespace-nowrap font-semibold text-ink", big ? "text-[16.5px] font-bold" : "text-[15px]")}>
        <span aria-hidden>{pts > 0 ? "⇡ " : pts < 0 ? "⇣ " : ""}</span>{fmtPts(pts)}
      </span>
      <Sm>{fmtGrowth(was)} → {fmtGrowth(now)}</Sm>
    </>
  );
}

/** Quick actions that appear on a row's hover or focus: the side panel and the company page. */
function QuickActions({ r, onPeek }: { r: KpiRow; onPeek: () => void }) {
  return (
    <span className="absolute right-1 top-3 flex gap-1 opacity-0 focus-within:opacity-100 group-hover:opacity-100">
      <button type="button" title="Quick look" aria-label={`Quick look at ${rowKey(r)}`} onClick={(e) => { e.stopPropagation(); onPeek(); }}
        className="grid h-7 w-7 place-items-center rounded-lg bg-surface text-ink-2 shadow-[0_0_0_1px_var(--line-strong)] hover:text-ink">
        <PanelRight aria-hidden className="h-3.5 w-3.5" />
      </button>
      <Link href={`${companyPath(r)}?tab=results`} onClick={(e) => e.stopPropagation()} title="Open company page" aria-label={`Open ${rowKey(r)} company page`}
        className="grid h-7 w-7 place-items-center rounded-lg bg-surface text-ink-2 shadow-[0_0_0_1px_var(--line-strong)] hover:text-ink">
        <ArrowRight aria-hidden className="h-3.5 w-3.5" />
      </Link>
    </span>
  );
}

/** The table's narrowest width: below it the table scrolls inside its own box, never the page (U1: it overlapped itself at 1024 px). */
const MIN_WIDTH: Record<View, string> = { yoy: "min-w-[820px]", momentum: "min-w-[1040px]", qoq: "min-w-[820px]" };

const COLS: Record<View, number[]> = {
  yoy: [22, 21, 25, 21, 11],
  momentum: [21, 20, 13, 12, 13, 12, 9],
  qoq: [22, 21, 25, 21, 11],
};

/** The companies as a table: one row per company, the columns of the chosen view. Keyboard: j and k move, Enter opens the side
 *  panel, Space toggles it. */
export function CompanyTable({ rows, view, sort, dir, onSort, selected, onSelect }: TableProps) {
  const body = useRef<HTMLTableSectionElement>(null);
  const [, setCursor] = useState(0);
  const th = { sort, dir, onSort };
  const q = view === "qoq";
  const focusRow = (i: number) => {
    const n = Math.max(0, Math.min(rows.length - 1, i));
    setCursor(n);
    (body.current?.children[n] as HTMLElement | undefined)?.focus();
  };
  const onKey = (e: KeyboardEvent<HTMLTableRowElement>, i: number, r: KpiRow) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); focusRow(i + 1); }
    else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); focusRow(i - 1); }
    else if (e.key === "Enter") { e.preventDefault(); onSelect(r); }
    else if (e.key === " ") { e.preventDefault(); onSelect(selected === rowKey(r) ? null : r); }
    else if (e.key === "Escape" && selected) onSelect(null);
  };
  const momentumScale = view === "momentum"
    ? sharedScale(rows.map((r) => (r.pat_momentum_pts != null ? [r.pat_yoy, r.pat_prev_yoy] : [])), true) : [0, 1];

  return (
    <div className="overflow-x-auto">
    <table className={cn("w-full table-fixed border-collapse text-[14px]", MIN_WIDTH[view])}>
      <colgroup>{COLS[view].map((w, i) => <col key={i} style={{ width: `${w}%` }} />)}</colgroup>
      <thead>
        {view !== "momentum" ? (
          <tr>
            <Th {...th} left sortKey="company" className="pl-3">Company</Th>
            <Th {...th} sortKey={q ? "revenue_qoq" : "revenue_yoy"} hint={q ? "vs last quarter" : "vs year ago"}>Revenue</Th>
            <Th {...th} sortKey={q ? "ebitda_qoq" : "ebitda_yoy"} title="100 bp = 1 percentage point" hint="margin, change">EBITDA · margin</Th>
            <Th {...th} sortKey={q ? "pat_qoq" : "pat_yoy"} title="PAT: profit after tax">Net profit</Th>
            <Th {...th} sortKey="mcap" className="pr-3">Mcap ₹ Cr</Th>
          </tr>
        ) : view === "momentum" ? (
          <tr>
            <Th {...th} left sortKey="company" className="pl-3">Company</Th>
            <Th {...th} left hint={
              <span className="flex justify-between gap-2">
                <span><i aria-hidden className="inline-block h-[9px] w-[9px] rounded-full align-[-1px] ring-[1.5px] ring-inset ring-ink-2" /> last quarter{" "}
                  <i aria-hidden className="ml-1 inline-block h-[9px] w-[9px] rounded-full bg-accent align-[-1px]" /> this quarter</span>
                <span className="num">{momentumScale[0]}% · {momentumScale[1]}%</span>
              </span>}>Profit growth: last quarter → this quarter</Th>
            <Th {...th} sortKey="pat_momentum" hint="change in growth, points">Profit pace</Th>
            <Th {...th} sortKey="revenue_momentum">Revenue pace</Th>
            <Th {...th} sortKey="ebitda_momentum">EBITDA pace</Th>
            <Th {...th}>Verdict</Th>
            <Th {...th} sortKey="filed" className="pr-3">Filed</Th>
          </tr>
        ) : null}
      </thead>
      <tbody ref={body}>
        {rows.map((r, i) => {
          const sel = selected === rowKey(r);
          const td = "border-b border-line px-2.5 py-3.5 text-right align-top";
          return (
            <tr key={`${r.scrip_code}-${r.period}`} tabIndex={-1} aria-selected={sel}
              onClick={() => { setCursor(i); onSelect(sel ? null : r); }} onFocus={() => setCursor(i)} onKeyDown={(e) => onKey(e, i, r)}
              className={cn("group cursor-pointer outline-none focus-visible:[&>td]:bg-accent-soft hover:[&>td]:bg-[#f7f8fa]",
                sel && "[&>td]:!bg-accent-soft [&>td:first-child]:shadow-[inset_3px_0_0_var(--accent)]")}>
              <td className={cn(td, "relative pl-3 text-left")}><CompanyCell row={r} /><QuickActions r={r} onPeek={() => onSelect(r)} /></td>
              {view !== "momentum" && (
                <>
                  <td className={td}><RevenueCell r={r} qoq={view === "qoq"} /></td>
                  <td className={td}><EbitdaCell r={r} qoq={view === "qoq"} /></td>
                  <td className={td}><ProfitCell r={r} qoq={view === "qoq"} /></td>
                  <td className={cn(td, "num whitespace-nowrap pr-3 text-ink-2")}>{fmtCrAmount(r.market_cap_cr)}</td>
                </>
              )}
              {view === "momentum" && (
                <>
                  <td className={cn(td, "text-left")}>
                    {r.pat_momentum_pts != null && r.pat_yoy != null && r.pat_prev_yoy != null
                      ? <Dumbbell was={r.pat_prev_yoy} now={r.pat_yoy} lo={momentumScale[0]} hi={momentumScale[1]} />
                      : <span className="block text-[13px] text-ink-3">{notComparableText(r)}</span>}
                  </td>
                  <td className={td}>
                    {r.pat_momentum_pts != null ? <Pace now={r.pat_yoy} was={r.pat_prev_yoy} pts={r.pat_momentum_pts} big />
                      : r.pat_turn ? <Growth value={null} turn={r.pat_turn} className="text-[15px]" /> : <span className="text-ink-3">—</span>}
                  </td>
                  <td className={td}><Pace now={r.revenue_yoy} was={r.revenue_prev_yoy} pts={r.revenue_momentum_pts} /></td>
                  <td className={td}><Pace now={r.ebitda_yoy} was={r.ebitda_prev_yoy} pts={r.ebitda_momentum_pts} /></td>
                  <td className={cn(td, "whitespace-nowrap")}>
                    {r.momentum === "not_comparable" ? <span className="text-ink-2">Not comparable</span> : <b className="font-semibold text-ink">{MOMENTUM_TEXT[r.momentum]}</b>}
                  </td>
                  <td className={cn(td, "pr-3")}><Filed r={r} /></td>
                </>
              )}
            </tr>
          );
        })}
      </tbody>
    </table>
    </div>
  );
}

function PhoneCell({ label, amount, value, turn, none, title }: {
  label: string; amount?: string; value?: number | null; turn?: KpiRow["pat_turn"]; none?: string; title?: string;
}) {
  return (
    <span className="flex min-w-0 flex-col gap-0.5" title={title}>
      <span className="text-[12.5px] text-ink-3">{label}</span>
      {none ? <span className="text-[13.5px] text-ink-3">{none}</span> : (
        <>
          <span className="num text-[14px] text-ink">{amount}</span>
          {turn ? <TurnPill turn={turn} className="self-start" /> : <Growth value={value} className="text-[13px]" />}
        </>
      )}
    </span>
  );
}

/** The phone list: one small card per company. Symbol and market cap on top, then Revenue, EBITDA (Fin. profit for a lender, none for a bank)
 *  and Net profit, each amount over its growth (or the turn pill). The whole card opens the quick look. */
export function PhoneList({ rows, onSelect }: { rows: KpiRow[]; onSelect: (r: KpiRow) => void }) {
  return (
    <ul className="flex flex-col gap-2 py-1">
      {rows.map((r) => {
        const slot = ebitdaSlot(r.kind);
        return (
          <li key={`${r.scrip_code}-${r.period}`}>
            <button type="button" onClick={() => onSelect(r)} aria-label={`${rowKey(r)}: open quick look`}
              className="block min-h-11 w-full rounded-xl border border-line bg-surface px-3.5 py-3 text-left focus-visible:outline-2 focus-visible:outline-accent">
              <span className="flex items-baseline justify-between gap-3">
                <span className="min-w-0 flex-1"><CompanyCell row={r} /></span>
                <span className="num shrink-0 text-[13px] text-ink-3">₹{fmtCrAmount(r.market_cap_cr)} Cr</span>
              </span>
              <span className="mt-2.5 grid grid-cols-3 gap-2">
                {r.kind === "insurer" || (r.revenue == null && r.revenue_yoy == null)
                  ? <PhoneCell label="Revenue" none="—" />
                  : <PhoneCell label="Revenue" amount={fmtCrAmount(r.revenue)} value={r.revenue_yoy} />}
                {slot === "none" ? <PhoneCell label="EBITDA" none="none" />
                  : <PhoneCell label={slot === "financing" ? "Fin. profit" : "EBITDA"} amount={fmtCrAmount(r.ebitda)} value={r.ebitda_yoy} turn={r.ebitda_turn} />}
                <PhoneCell label="Net profit" amount={fmtCrAmount(r.pat)} value={r.pat_yoy} turn={r.pat_turn} />
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** Rows of grey while the list loads, at the rows' own height. */
export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading companies">
      <Skeleton className="mb-2 h-10" />
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex h-[74px] items-start gap-3 border-b border-line py-3.5">
          <Skeleton className="h-8 w-8 rounded-[10px]" />
          <div className="flex-1"><Skeleton className="h-4 w-28" /><Skeleton className="mt-2 h-3 w-44" /></div>
          <Skeleton className="hidden h-4 w-20 sm:block" /><Skeleton className="hidden h-4 w-20 sm:block" /><Skeleton className="h-5 w-24" />
        </div>
      ))}
    </div>
  );
}
