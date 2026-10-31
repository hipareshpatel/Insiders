import { ArrowDown, ArrowRight, ArrowUp, PanelRight } from "lucide-react";
import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "wouter";
import type { KpiRow, View } from "../../../shared/resultsTypes";
import { cn } from "../../lib/cn";
import { companyPath, cr } from "../../lib/format";
import {
  blankNote, filedDay, NBFC_EBITDA_NOTE, fmtGrowth, fmtPct, fmtMargin, fmtPts, lineLabels, NM, MOMENTUM_TEXT, notComparableText, sharedScale, wasLine, oneOff as oneOffOf, type Sort,
} from "../../lib/resultsView";
import { CompanyCell, Growth, MomentumMark, NfoFlag, Signals, Skeleton } from "./bits";
import { Dumbbell, Spark } from "./charts";

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

/** The quiet second line under a figure. */
const Sm = ({ children, italic }: { children: ReactNode; italic?: boolean }) => (
  <div className={cn("num mt-0.5 text-[13px] text-ink-3", italic && "italic")}>{children}</div>
);
const Blank = ({ note }: { note?: string }) => (<><span className="font-medium text-ink-3">—</span>{note && <Sm>{note}</Sm>}</>);
/** A growth cell with no figure says why (U4, 31 Oct 2026: UDS, DIAMONDYD and JNPR showed "—" in every growth cell with no reason). */
const NO_BASE = (qoq?: boolean) => (qoq ? "No prior-quarter figure to compare" : "No year-ago figure to compare");

function RevenueCell({ r, qoq }: { r: KpiRow; qoq?: boolean }) {
  const label = lineLabels(r.kind).revenue;
  if (!label || (r.revenue == null && r.revenue_yoy == null)) return <Blank note={blankNote(r.kind, "revenue")} />;
  return (
    <>
      <Growth value={qoq ? r.revenue_qoq : r.revenue_yoy} className="text-[15px]" />
      <Sm>{qoq ? cr(r.revenue) : wasLine(r.revenue == null ? null : cr(r.revenue), r.revenue_prev_yoy)}</Sm>
      {(qoq ? r.revenue_qoq : r.revenue_yoy) == null && <Sm italic>{NO_BASE(qoq)}</Sm>}
      {label !== "Revenue" && <Sm italic>{label}</Sm>}
    </>
  );
}

function EbitdaCell({ r, qoq }: { r: KpiRow; qoq?: boolean }) {
  const label = lineLabels(r.kind).ebitda;
  if (!label || (r.ebitda == null && r.ebitda_yoy == null && !r.ebitda_turn)) return <Blank note={blankNote(r.kind, "ebitda")} />;
  return (
    <>
      <Growth value={qoq ? r.ebitda_qoq : r.ebitda_yoy} turn={qoq ? null : r.ebitda_turn} className="text-[15px]" />
      <Sm>{qoq ? cr(r.ebitda) : wasLine(r.ebitda == null ? null : cr(r.ebitda), r.ebitda_prev_yoy)}</Sm>
      {(qoq ? r.ebitda_qoq : r.ebitda_yoy) == null && !(qoq ? false : r.ebitda_turn) && <Sm italic>{NO_BASE(qoq)}</Sm>}
      {label !== "EBITDA" && <Sm italic><span title={r.kind === "nbfc" || r.kind === "bank" ? NBFC_EBITDA_NOTE : undefined}>{label}{(r.kind === "nbfc" || r.kind === "bank") && <sup aria-hidden> *</sup>}</span></Sm>}
    </>
  );
}

function MarginCell({ r, qoq }: { r: KpiRow; qoq?: boolean }) {
  const label = lineLabels(r.kind).margin;
  const bps = qoq ? r.opm_qoq_bps : r.opm_yoy_bps;
  if (!label || (r.opm == null && bps == null)) return <span className="font-medium text-ink-3" title="No EBITDA margin for this kind of company">—</span>;
  // no bp where a margin is past +-100% or the base EBITDA is a loss (results_table.py); NM when a year-ago (or last-quarter) figure exists
  const hadBase = qoq ? r.ebitda_qoq != null : r.ebitda_yoy != null || r.ebitda_turn != null;
  return (
    <>
      {bps == null && r.opm != null && hadBase
        ? <span className="num whitespace-nowrap text-[15px] font-semibold text-ink-2" title="Not meaningful: a margin outside −100%…+100%, or a loss in the base period">{NM}</span>
        : <Growth value={bps} unit="bp" className="text-[15px]" />}
      <Sm>{r.kind === "nbfc" || r.kind === "bank" ? "margin" : "now"} <span title={r.opm != null && Math.abs(r.opm) > 100 ? `Not meaningful: ${r.opm.toFixed(1)}%` : undefined}>{fmtMargin(r.opm)}</span></Sm>
    </>
  );
}

function ProfitCell({ r, qoq }: { r: KpiRow; qoq?: boolean }) {
  const turn = qoq ? r.pat_qoq_turn : r.pat_turn;
  const amount = r.pat == null ? null : `${cr(r.pat)}${turn ? (r.pat >= 0 ? " profit" : " loss") : ""}`;
  const oneOff = qoq ? null : oneOffOf(r);   // the year-ago comparison only: its growth is a year-on-year one
  return (
    <>
      <span className="whitespace-nowrap">
        <Growth value={qoq ? r.pat_qoq : r.pat_yoy} turn={turn} className="text-[16.5px] font-bold" />
        {!qoq && <MomentumMark m={r.momentum} />}
      </span>
      <Sm>{qoq ? amount ?? "—" : wasLine(amount, r.pat_prev_yoy, r.pat_prev_turn)}</Sm>
      {(qoq ? r.pat_qoq : r.pat_yoy) == null && !turn && <Sm italic>{NO_BASE(qoq)}</Sm>}
      {oneOff && <Sm><span title={oneOff.title}>{oneOff.text}</span></Sm>}
      {r.nfo && <div className="mt-1.5"><NfoFlag /></div>}
    </>
  );
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
const MIN_WIDTH: Record<View, string> = { yoy: "min-w-[1280px]", momentum: "min-w-[1040px]", qoq: "min-w-[1260px]" };

const COLS: Record<View, number[]> = {
  yoy: [18.5, 7, 14.5, 14.5, 9.5, 15.5, 6.5, 8, 6],
  momentum: [21, 20, 13, 12, 13, 12, 9],
  qoq: [23, 7.5, 15, 15, 11, 15, 7.5, 6],
};

/** The companies as a table: one row per company, the columns of the chosen view. Keyboard: j and k move, Enter opens the side
 *  panel, Space toggles it. */
export function CompanyTable({ rows, view, sort, dir, onSort, selected, onSelect }: TableProps) {
  const body = useRef<HTMLTableSectionElement>(null);
  const [, setCursor] = useState(0);
  const th = { sort, dir, onSort };
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
        {view === "yoy" ? (
          <tr>
            <Th {...th} left sortKey="company" hint="Sector › industry" className="pl-3">Company</Th>
            <Th {...th} left hint="Rev · EBITDA · Profit">Signals</Th>
            <Th {...th} sortKey="revenue_yoy">Revenue</Th>
            <Th {...th} sortKey="ebitda_yoy">EBITDA</Th>
            <Th {...th} sortKey="opm_yoy_bps" title="100 bp = 1 percentage point" hint="EBITDA margin">Margin change</Th>
            <Th {...th} sortKey="pat_yoy" title="PAT: profit after tax" hint="⇡ faster / ⇣ slower than last qtr">Profit (PAT)</Th>
            <Th {...th} title="Profit growth in the last 8 quarters, on its own scale" hint="own scale">Profit trend</Th>
            <Th {...th} sortKey="mcap">Market cap</Th>
            <Th {...th} sortKey="filed" className="pr-3">Filed</Th>
          </tr>
        ) : view === "momentum" ? (
          <tr>
            <Th {...th} left sortKey="company" hint="Sector › industry" className="pl-3">Company</Th>
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
        ) : (
          <tr>
            <Th {...th} left sortKey="company" hint="Sector › industry" className="pl-3">Company</Th>
            <Th {...th} left hint="vs last quarter">Signals</Th>
            <Th {...th} sortKey="revenue_qoq">Revenue</Th>
            <Th {...th} sortKey="ebitda_qoq">EBITDA</Th>
            <Th {...th} sortKey="opm_qoq_bps" title="100 bp = 1 percentage point" hint="EBITDA margin">Margin change</Th>
            <Th {...th} sortKey="pat_qoq" title="PAT: profit after tax">Profit (PAT)</Th>
            <Th {...th} sortKey="mcap">Market cap</Th>
            <Th {...th} sortKey="filed" className="pr-3">Filed</Th>
          </tr>
        )}
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
              {view === "yoy" && (
                <>
                  <td className={cn(td, "text-left")}><Signals row={r} /></td>
                  <td className={td}><RevenueCell r={r} /></td>
                  <td className={td}><EbitdaCell r={r} /></td>
                  <td className={td}><MarginCell r={r} /></td>
                  <td className={td}><ProfitCell r={r} /></td>
                  <td className={cn(td, "pt-4")}>
                    <span className="inline-flex justify-end">
                      <Spark vals={r.series_pat} lo={sharedScale([r.series_pat], true)[0]} hi={sharedScale([r.series_pat], true)[1]} w={64} h={26} title={`Profit growth, last 8 quarters: ${r.series_pat.map((v) => fmtPct(v)).join(", ")}`} />
                    </span>
                  </td>
                  <td className={cn(td, "num whitespace-nowrap text-ink-2")}>{cr(r.market_cap_cr)}</td>
                  <td className={cn(td, "pr-3")}><Filed r={r} /></td>
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
              {view === "qoq" && (
                <>
                  <td className={cn(td, "text-left")}><Signals row={r} qoq /></td>
                  <td className={td}><RevenueCell r={r} qoq /></td>
                  <td className={td}><EbitdaCell r={r} qoq /></td>
                  <td className={td}><MarginCell r={r} qoq /></td>
                  <td className={td}><ProfitCell r={r} qoq /></td>
                  <td className={cn(td, "num whitespace-nowrap text-ink-2")}>{cr(r.market_cap_cr)}</td>
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

/** The phone list: one block per company, profit growth on the right, the other two lines under it. */
export function PhoneList({ rows, onSelect }: { rows: KpiRow[]; onSelect: (r: KpiRow) => void }) {
  return (
    <ul>
      {rows.map((r) => {
        const labels = lineLabels(r.kind);
        const amount = r.pat == null ? null : `${cr(r.pat)}${r.pat_turn ? (r.pat >= 0 ? " profit" : " loss") : ""}`;
        return (
          <li key={`${r.scrip_code}-${r.period}`} className="border-b border-line">
            <button type="button" onClick={() => onSelect(r)} className="block min-h-11 w-full py-3.5 text-left">
              <span className="flex items-start gap-3">
                <span className="min-w-0 flex-1"><CompanyCell row={r} compact /></span>
                <span className="shrink-0 text-right">
                  <Growth value={r.pat_yoy} turn={r.pat_turn} className="text-[19px] font-bold" />
                  <span className="num block text-[12.5px] text-ink-3">{wasLine(amount, r.pat_turn ? null : r.pat_prev_yoy)}</span>
                </span>
              </span>
              <span className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 pl-11 text-[13.5px] text-ink-2">
                <Signals row={r} />
                {labels.revenue ? (
                  <span>{labels.revenue === "Revenue" ? "Rev" : labels.revenue} <Growth value={r.revenue_yoy} arrowClass="hidden" /></span>
                ) : <span className="text-ink-3">No revenue (insurer)</span>}
                {labels.ebitda ? (
                  <span>{labels.ebitda === "EBITDA" ? "EBITDA" : "Fin. profit"} <Growth value={r.ebitda_yoy} turn={r.ebitda_turn} arrowClass="hidden" /></span>
                ) : null}
              </span>
              {r.nfo && <span className="mt-2 block pl-11"><NfoFlag /></span>}
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
