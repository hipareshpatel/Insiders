import { AlertTriangle, ArrowRight, X } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import { Link } from "wouter";
import type { KpiRow } from "../../../shared/resultsTypes";
import { industryLine } from "../../../shared/industry";
import { cn } from "../../lib/cn";
import { companyPath, cr } from "../../lib/format";
import { fmtMargin, fmtPct, lineLabels, paceSentence, quarterLabel, quarterSeries } from "../../lib/resultsView";
import { Avatar } from "../Avatar";
import { Growth } from "./bits";
import { LineChart } from "./charts";

const KIND_NOTE: Record<KpiRow["kind"], string | null> = {
  company: null,
  bank: "Banks: no operating-expense line is saved, so no EBITDA or margin; revenue is interest income.",
  nbfc: "NBFCs: financing profit and financing margin stand in for EBITDA and margin; left out of EBITDA medians and totals.",
  insurer: "Insurers: profit only; no revenue or EBITDA is saved in a comparable layout.",
  reit: "REITs: revenue, operating profit and profit as the trust files them; left out of EBITDA medians and totals. Cash distributions are not shown yet.",
  invit: "InvITs: revenue, operating profit and profit as the trust files them; left out of EBITDA medians and totals. Cash distributions are not shown yet.",
};

function Tile({ label, value, turn, amount, title }: { label: string; value: number | null; turn?: KpiRow["pat_turn"]; amount: number | null; title?: string }) {
  // min-w-0 and a value that may wrap: "Loss → profit" ran past the tile at 480 px (audit 31 Oct 2026)
  return (
    <div className="min-w-0 rounded-xl bg-surface-2 px-3 py-2.5 sm:px-3.5">
      <div className="text-[13px] text-ink-2" title={title}>{label}</div>
      <div className="mt-0.5 text-[18px] font-bold leading-tight tracking-[-0.01em] sm:text-[20px]"><Growth value={value} turn={turn} className="whitespace-normal break-words" /></div>
      <div className="num mt-0.5 text-[13px] text-ink-3">{cr(amount)}</div>
    </div>
  );
}

/** The side panel a row opens: the row stays visible to its left. The three growth figures, the "profit not from operations" warning,
 *  8 quarters of profit and revenue growth, and the way to the company page and the filing. */
export function PeekPanel({ row, onClose }: { row: KpiRow; onClose: () => void }) {
  const ref = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const opener = useRef<Element | null>(typeof document === "undefined" ? null : document.activeElement);
  const rowKey = row.symbol || row.scrip_code;
  useEffect(() => { closeRef.current?.focus({ preventScroll: true }); }, [row.scrip_code]);
  // closing hands focus back to the row's quick-look button (else to whatever opened the panel)
  useEffect(() => () => {
    const btn = document.querySelector<HTMLElement>(`[aria-label="Quick look at ${CSS.escape(rowKey)}"]`);
    const back = btn ?? (opener.current instanceof HTMLElement && opener.current.isConnected ? opener.current : null);
    back?.focus({ preventScroll: true });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key !== "Tab" || !ref.current) return;
      // a small focus trap: Tab and Shift+Tab stay inside the dialog
      const items = [...ref.current.querySelectorAll<HTMLElement>("a[href],button:not([disabled])")];
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      else if (!ref.current.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);
  const labels = lineLabels(row.kind);
  const name = row.company_name ?? row.symbol ?? row.scrip_code;
  const q = quarterLabel(row.period);
  return (
    <>
    <div aria-hidden onClick={onClose} className="fixed inset-0 z-30 hidden bg-black/10 sm:block" />
    <aside ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId}
      className="fixed inset-y-0 right-0 z-40 flex w-full flex-col bg-surface shadow-[-1px_0_0_var(--line-strong),-30px_0_60px_-40px_rgba(20,30,50,0.25)] sm:w-[480px]">
      <div className="flex-1 overflow-y-auto px-5 pb-6 pt-6 sm:px-7">
        <div className="flex items-center gap-3">
          <Avatar name={name} symbol={row.symbol} size={40} className="rounded-xl text-[16px]" />
          <div className="min-w-0">
            <h2 id={titleId} className="truncate text-[20px] font-bold tracking-[-0.01em] text-ink">{name}</h2>
            <p className="truncate text-[13px] text-ink-3">{row.symbol ?? row.scrip_code} · {industryLine(row.industry) ?? "Unclassified"}{row.basis === "STANDALONE" ? " · standalone" : ""}</p>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close"
            className="ml-auto grid h-11 w-11 shrink-0 place-items-center rounded-[10px] bg-surface-2 text-ink-2 hover:text-ink sm:h-9 sm:w-9">
            <X aria-hidden className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-[22px] grid grid-cols-3 gap-2.5">
          {labels.revenue ? <Tile label={labels.revenue} value={row.revenue_yoy} amount={row.revenue} /> : <NoTile label="Revenue" note="not for insurers" />}
          {labels.ebitda ? <Tile label={labels.ebitda} value={row.ebitda_yoy} turn={row.ebitda_turn} amount={row.ebitda} />
            : <NoTile label="EBITDA" note={row.kind === "bank" ? "not for banks" : "not for insurers"} />}
          <Tile label="Profit (PAT)" title="PAT: profit after tax" value={row.pat_yoy} turn={row.pat_turn} amount={row.pat} />
        </div>
        <p className="mt-2 text-[13px] text-ink-3">{q} vs the same quarter a year ago</p>

        {row.nfo && (
          <div className="mt-3.5 flex gap-3 rounded-xl bg-warn-soft px-4 py-3.5 text-[14px] text-ink">
            <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
            <p><b>Profit up, EBITDA down.</b> Profit {row.pat_turn === "LOSS_TO_PROFIT" ? "turned from a loss to a profit" : `rose ${fmtPct(row.pat_yoy)}`} while
              EBITDA fell{row.ebitda_yoy != null ? ` ${fmtPct(Math.abs(row.ebitda_yoy)).replace("+", "")}` : ""}. The rise came from outside the core business, such as
              other income or a one-off. Read the filing before relying on it.</p>
          </div>
        )}

        <section className="mt-[26px]">
          <h3 className="mb-1.5 text-[13px] font-semibold text-ink-2">Growth vs a year ago, last 8 quarters</h3>
          <div className="mb-1.5 flex gap-4 text-[13px] text-ink-2">
            <span><i aria-hidden className="mr-1.5 inline-block h-[3px] w-3.5 rounded-sm bg-accent align-middle" />Profit</span>
            {labels.revenue && <span><i aria-hidden className="mr-1.5 inline-block h-[3px] w-3.5 rounded-sm bg-ink-3 align-middle" />{labels.revenue}</span>}
          </div>
          <LineChart labels={quarterSeries(row.period)} series={[
            ...(labels.revenue ? [{ name: labels.revenue === "Revenue" ? "Revenue" : labels.revenue, vals: row.series_revenue, color: "var(--ink-3)" }] : []),
            { name: "Profit", vals: row.series_pat, color: "var(--accent)" },
          ]} />
          <p className="mt-2 text-[13px] text-ink-3">{paceSentence(row)}</p>
        </section>

        <section className="mt-[26px]">
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-2.5 text-[14px]">
            <dt className="text-ink-2">{labels.margin ? `${labels.margin} change` : "Margin change"}</dt>
            <dd className="text-right">
              {labels.margin && row.opm_yoy_bps != null
                ? <><Growth value={row.opm_yoy_bps} unit="bp" /> <span className="text-ink-3">to {fmtMargin(row.opm)}</span></>
                : labels.margin && row.opm != null && (row.ebitda_yoy != null || row.ebitda_turn != null)
                  ? <span className="font-semibold text-ink-2" title="Not meaningful: a margin outside −100%…+100%, or a loss in the base period">NM <span className="font-normal text-ink-3">to {fmtMargin(row.opm)}</span></span>
                  : <span className="text-ink-3">—</span>}
            </dd>
            <dt className="text-ink-2">Market cap</dt><dd className="num text-right text-ink">{cr(row.market_cap_cr)}</dd>
            <dt className="text-ink-2">Filed</dt>
            <dd className="text-right text-ink">
              {row.filed_at ? new Date(row.filed_at).toLocaleDateString("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric" }) : "—"}
              {row.filing_url && <> · <a href={row.filing_url} target="_blank" rel="noreferrer" className="font-semibold text-accent hover:underline">NSE filing ↗</a></>}
            </dd>
            <dt className="text-ink-2">Basis</dt><dd className="text-right text-ink">{row.basis === "CONSOLIDATED" ? "Consolidated" : "Standalone"}</dd>
          </dl>
          {KIND_NOTE[row.kind] && <p className="mt-3 text-[12.5px] text-ink-3">{KIND_NOTE[row.kind]}</p>}
        </section>
      </div>
      <div className="flex gap-2.5 border-t border-line bg-surface px-5 py-4 sm:px-7">
        <Link href={`${companyPath(row)}?tab=results`}
          className="inline-flex h-11 items-center gap-2 rounded-[11px] bg-accent px-3.5 text-[14px] font-semibold text-accent-ink hover:opacity-90 sm:h-[38px]">
          Open company page <ArrowRight aria-hidden className="h-4 w-4" />
        </Link>
        {row.filing_url && (
          <a href={row.filing_url} target="_blank" rel="noreferrer"
            className={cn("inline-flex h-11 items-center gap-2 rounded-[11px] bg-surface-2 px-3.5 text-[14px] font-semibold text-ink hover:bg-line sm:h-[38px]")}>
            Open NSE filing <span aria-hidden>↗</span>
          </a>
        )}
      </div>
    </aside>
    </>
  );
}

function NoTile({ label, note }: { label: string; note: string }) {
  return (
    <div className="min-w-0 rounded-xl bg-surface-2 px-3 py-2.5 sm:px-3.5">
      <div className="text-[13px] text-ink-2">{label}</div>
      <div className="mt-0.5 text-[20px] font-bold text-ink-3">—</div>
      <div className="mt-0.5 text-[13px] text-ink-3">{note}</div>
    </div>
  );
}
