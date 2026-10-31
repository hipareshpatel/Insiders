import { useState, type ReactNode } from "react";
import type { Dossier } from "../../../shared/types";
import { cn } from "../../lib/cn";
import {
  annualTable, balanceTable, cashFlowTable, formatCell, growth, isBank, mainBasis, quarterlyTable, ratioTable, screenerTable, statementDate, withRestated, type Table,
} from "./statements";
import { Panel } from "./Panel";

/** The statements as screener.in lays them out (owner, 2026-10-21): quarterly results, profit and loss by year with
 *  TTM, the balance sheet, cash flows and ratios, each a plain table in ₹ Cr. Built in statements.ts from memory. */
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
  "November", "December"];

// TODO 52 / F210: screener's own formulas for the lines (statements.ts `screener`); build-time switch, default off
const SCREENER_LINES = (import.meta.env?.VITE_SCREENER_LINES ?? "") === "1";

export function Financials({ dossier }: { dossier: Dossier }) {
  // consolidated and standalone, as screener.in switches them (owner, 2026-10-21); memory's main figures are the
  // consolidated ones for a group that files both, its standalone file is kept apart (dossier.put_standalone)
  const main = mainBasis(dossier.financial_metrics);
  const alone = dossier.standalone?.metrics?.length || (dossier.statements ?? []).some((e) => e.basis === "STANDALONE")
    ? (dossier.standalone ?? { metrics: [], balance_sheet: [] }) : null;
  const [basis, setBasis] = useState<"main" | "standalone">("main");
  const useAlone = basis === "standalone" && alone;
  const metrics = (useAlone ? alone.metrics : dossier.financial_metrics) as Dossier["financial_metrics"];
  const sheets = useAlone ? alone.balance_sheet ?? [] : dossier.balance_sheet;
  const label = useAlone ? "Standalone" : main === "CONSOLIDATED" ? "Consolidated" : main === "STANDALONE" ? "Standalone" : null;
  const bank = isBank(metrics);
  // screener's tables by its rules from the exchange's files when memory holds them (owner, 30 Oct 2026: "our stock page
  // having financial statements will be saved as per screener"); else the lines worked out from memory's figures, as before
  const stBasis = useAlone ? "STANDALONE" : (main ?? "CONSOLIDATED");
  const pick = (t: Table, fallback: () => Table) => (t.columns.length ? t : fallback());
  const quarterly = pick(withRestated(screenerTable(dossier.statements, stBasis, "quarters", 12), dossier.restated_figures, stBasis),
    () => quarterlyTable(metrics, SCREENER_LINES));
  const annual = pick(screenerTable(dossier.statements, stBasis, "annual", 6), () => annualTable(metrics, SCREENER_LINES));
  const balance = pick(screenerTable(dossier.statements, stBasis, "balance", 8), () => balanceTable(sheets, SCREENER_LINES));
  const cash = pick(screenerTable(dossier.statements, stBasis, "cash_flow", 6), () => cashFlowTable(metrics));
  const ratios = ratioTable(metrics, sheets);
  const top = bank ? "interest_earned" : "revenue";
  const boxes = [
    { title: bank ? "Compounded revenue growth" : "Compounded sales growth", rows: growth(metrics, top) },
    { title: "Compounded profit growth", rows: growth(metrics, "pat") },
  ].filter((b) => b.rows.length);
  const sub = `${label ? `${label} · ` : ""}₹ Cr · from the NSE filings`;
  const yearEnd = dossier.fy_end_month && dossier.fy_end_month !== 3 ? MONTHS[dossier.fy_end_month - 1] : null;
  return (
    <div className="space-y-[18px]">
      {yearEnd && (
        // a year not ending in March (Siemens: September): its quarters are named by calendar months, and its
        // half-year and year figures are not kept, as their labels would name the wrong months (22 Oct 2026)
        <p className="rounded-xl border border-warn/40 bg-warn-soft px-3.5 py-2.5 text-[12.5px] leading-relaxed text-warn">
          This company's financial year ends in {yearEnd}. Quarters here are named by calendar months on the April-March
          convention (Q2FY27 = July-September 2026), not by the company's own numbering; its half-year and full-year
          figures are left out, so the yearly tables and growth rates are not shown.
        </p>
      )}
      {alone && main === "CONSOLIDATED" && (
        <div role="tablist" className="inline-flex gap-0.5 rounded-xl bg-surface-2 p-0.5">
          {([["main", "Consolidated"], ["standalone", "Standalone"]] as const).map(([key, text]) => (
            <button key={key} type="button" role="tab" aria-selected={basis === key} onClick={() => setBasis(key)}
              className={cn("rounded-[9px] px-3 py-1.5 text-[12.5px] font-bold transition-colors",
                basis === key ? "bg-surface text-ink shadow-sm" : "text-ink-3 hover:text-ink")}>{text}</button>
          ))}
        </div>
      )}
      <Statement title="Quarterly results" t={quarterly} label={statementDate} sub={sub}
        footer={quarterly.rows.some((r) => r.restated?.some(Boolean)) && (
          <p className="mt-3 text-[12px] text-ink-3"><sup>R</sup> Restated: the figure a later results filing gives for that quarter, as Screener shows it. Hover for the figure first filed.</p>
        )} />
      <Statement title="Profit & loss" t={annual} label={(p) => (p === "TTM" ? "TTM" : statementDate(p))} sub={sub}
        footer={boxes.length > 0 && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {boxes.map((b) => (
              <div key={b.title} className="rounded-xl border border-line px-3.5 py-2.5">
                <div className="mb-1 text-[12px] font-bold text-ink-2">{b.title}</div>
                {b.rows.map((r) => (
                  <div key={r.label} className="num flex justify-between text-[13px]"><span className="text-ink-3">{r.label}:</span><span className="font-semibold text-ink">{formatCell(r.value, "pct")}</span></div>
                ))}
              </div>
            ))}
          </div>
        )} />
      <Statement title="Balance sheet" t={balance} label={(p) => (/^(Q[1-4]|H[12])FY/.test(p) ? statementDate(p) : p)} sub={sub} empty="No full statement of assets and liabilities in memory yet: it comes with the half-year and year results" />
      <Statement title="Cash flows" t={cash} sub={sub} label={(p) => (p.startsWith("H1") ? `${statementDate(p)} (6 months)` : statementDate(p))}
        empty="No cash-flow statement in memory yet: it comes with the half-year and year results" />
      <Statement title="Ratios" t={ratios} label={statementDate} sub={sub} />
    </div>
  );
}

function Statement({ title, t, label, footer, empty, sub }: { title: string; t: Table; label: (p: string) => string; footer?: ReactNode; empty?: string; sub: string }) {
  if (!t.columns.length || !t.rows.length) {
    return empty ? <Panel title={title}><p className="text-[13px] text-ink-3">{empty}</p></Panel> : null;
  }
  return (
    <Panel title={title} sub={sub}>
      <div className="-mx-5 overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-[13.5px]">
          <thead>
            <tr className="border-b border-line-strong">
              <th className="sticky left-0 bg-surface px-5 py-2 text-left font-semibold text-ink-3" />
              {t.columns.map((c) => <th key={c} className="num whitespace-nowrap px-3 py-2 text-right font-semibold text-ink-2">{label(c)}</th>)}
            </tr>
          </thead>
          <tbody>
            {t.rows.map((r) => (
              <tr key={r.label} className={cn("border-b border-line last:border-0", r.strong && "bg-surface-2/60")}>
                <td className={cn("sticky left-0 whitespace-nowrap px-5 py-2 text-left", r.strong ? "bg-surface-2 font-bold text-ink" : "bg-surface text-ink-2")}>{r.label}</td>
                {r.cells.map((c, i) => {
                  const was = r.restated?.[i];
                  return (
                    <td key={i} title={was ? `Restated in the ${was.restated_in} results. Originally filed: ₹${formatCell(was.original)} Cr` : undefined}
                      className={cn("num whitespace-nowrap px-3 py-2 text-right", r.strong ? "font-bold text-ink" : r.kind === "pct" ? "text-ink-3" : "text-ink",
                        c != null && c < 0 && r.kind !== "pct" && "text-neg")}>
                      {formatCell(c, r.kind)}
                      {was && <sup className="ml-0.5 text-[9px] font-semibold text-ink-3" aria-label="restated">R</sup>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {footer}
    </Panel>
  );
}
