import type { ReactNode } from "react";
import type { Dossier } from "../../../shared/types";
import { cn } from "../../lib/cn";
import {
  annualTable, balanceTable, cashFlowTable, formatCell, growth, isBank, quarterlyTable, ratioTable, statementDate, type Table,
} from "./statements";
import { Panel } from "./Panel";

/** The statements as screener.in lays them out (owner, 2026-10-21): quarterly results, profit and loss by year with
 *  TTM, the balance sheet, cash flows and ratios, each a plain table in ₹ Cr. Built in statements.ts from memory. */
export function Financials({ dossier }: { dossier: Dossier }) {
  const metrics = dossier.financial_metrics;
  const bank = isBank(metrics);
  const quarterly = quarterlyTable(metrics), annual = annualTable(metrics);
  const balance = balanceTable(dossier.balance_sheet, bank), cash = cashFlowTable(metrics), ratios = ratioTable(metrics, dossier.balance_sheet);
  const top = bank ? "interest_earned" : "revenue";
  const boxes = [
    { title: bank ? "Compounded revenue growth" : "Compounded sales growth", rows: growth(metrics, top) },
    { title: "Compounded profit growth", rows: growth(metrics, "pat") },
  ].filter((b) => b.rows.length);
  return (
    <div className="space-y-[18px]">
      <Statement title="Quarterly results" t={quarterly} label={statementDate} />
      <Statement title="Profit & loss" t={annual} label={(p) => (p === "TTM" ? "TTM" : statementDate(p))}
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
      <Statement title="Balance sheet" t={balance} label={(p) => p} empty="No full statement of assets and liabilities in memory yet: it comes with the half-year and year results" />
      <Statement title="Cash flows" t={cash} label={(p) => (p.startsWith("H1") ? `${statementDate(p)} (6 months)` : statementDate(p))}
        empty="No cash-flow statement in memory yet: it comes with the half-year and year results" />
      <Statement title="Ratios" t={ratios} label={statementDate} />
    </div>
  );
}

function Statement({ title, t, label, footer, empty }: { title: string; t: Table; label: (p: string) => string; footer?: ReactNode; empty?: string }) {
  if (!t.columns.length || !t.rows.length) {
    return empty ? <Panel title={title}><p className="text-[13px] text-ink-3">{empty}</p></Panel> : null;
  }
  return (
    <Panel title={title} sub="₹ Cr · from the NSE filings">
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
                {r.cells.map((c, i) => (
                  <td key={i} className={cn("num whitespace-nowrap px-3 py-2 text-right", r.strong ? "font-bold text-ink" : r.kind === "pct" ? "text-ink-3" : "text-ink",
                    c != null && c < 0 && r.kind !== "pct" && "text-neg")}>{formatCell(c, r.kind)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {footer}
    </Panel>
  );
}
