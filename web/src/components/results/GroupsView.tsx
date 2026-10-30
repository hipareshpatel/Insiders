import { useQuery } from "@tanstack/react-query";
import { ArrowDown } from "lucide-react";
import type { Cut, GroupBy, GroupRow } from "../../../shared/resultsTypes";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { istDate } from "../../lib/format";
import { fmtPct, groupNoun, groupsBullets, groupsLead, quarterLabel, quarterSeries, sharedScale } from "../../lib/resultsView";
import { Button } from "../ui/button";
import { Growth, Panel, SegControl, Segs, Skeleton } from "./bits";
import { RankedDots, Spark, SpreadStack } from "./charts";

const BY: { key: GroupBy; label: string }[] = [{ key: "index", label: "Index" }, { key: "sector", label: "Sector" }, { key: "industry", label: "Industry" }];
const CUTS: { key: Cut; label: string }[] = [{ key: "all", label: "All" }, { key: "ex_financials", label: "Ex-financials" }, { key: "financials", label: "Financials" }];
const CUT_WORDS: Record<Cut, string> = { all: "all companies", ex_financials: "excluding financials", financials: "financials only" };
const patTotal = (r: GroupRow, c: Cut) => (c === "all" ? r.pat_total_all : c === "ex_financials" ? r.pat_total_ex_financials : r.pat_total_financials);
const revTotal = (r: GroupRow, c: Cut) => (c === "all" ? r.revenue_total_all : c === "ex_financials" ? r.revenue_total_ex_financials : r.revenue_total_financials);
const KEY = [["bg-d-neg", "Below 0%"], ["bg-d-1", "0–10%"], ["bg-d-2", "10–20%"], ["bg-d-3", "Above 20%"]];

/** Profit growth by index, sector or industry: a ranked dot plot of the median against the total, what it says, and a table of every
 *  group's numbers. Clicking a group opens the Companies tab filtered to it. */
export function GroupsView({ quarter, by, cut, setParams, onPick }: {
  quarter: string | null; by: GroupBy; cut: Cut; setParams: (c: Record<string, string | null>) => void; onPick: (r: GroupRow, by: GroupBy) => void;
}) {
  const res = useQuery({ queryKey: ["results-groups", quarter, by, cut], queryFn: () => api.resultsGroups({ quarter, by, cut }), placeholderData: (p) => p });
  const rows = res.data?.rows ?? [];
  const q = quarterLabel(res.data?.quarter ?? quarter);
  const labels = quarterSeries(res.data?.quarter ?? quarter);
  const [lo, hi] = sharedScale(rows.map((r) => r.trend_pat_median));
  const plural = groupNoun(by, true);
  return (
    <div className="pb-4">
      <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-3 sm:mt-7">
        <span className="flex items-center gap-2"><span className="text-[14px] text-ink-2">Group by</span>
          <SegControl label="Group by" items={BY} value={by} onChange={(k) => setParams({ by: k === "index" ? null : k })} itemClass="max-sm:min-h-11" /></span>
        <span className="flex items-center gap-2"><span className="text-[14px] text-ink-2">Companies</span>
          <SegControl label="Companies" items={CUTS} value={cut} onChange={(k) => setParams({ cut: k === "all" ? null : k })} itemClass="max-sm:min-h-11" /></span>
        <span className="flex-1" />
        <span className="text-[13px] text-ink-3">Financials = banks, NBFCs and insurers</span>
      </div>

      {res.isError && !res.data ? (
        <div className="mt-7 rounded-2xl bg-surface-2 px-6 py-14 text-center" role="alert">
          <p className="text-[17px] font-semibold text-ink">Couldn't load the groups</p>
          <p className="mt-1 text-[14px] text-ink-2">The server did not answer ({String(res.error?.message ?? "error")}).</p>
          <Button className="mt-4" onClick={() => res.refetch()}>Try again</Button>
        </div>
      ) : !res.data ? (
        <div className="mt-7 grid gap-4 lg:grid-cols-[7fr_5fr]" aria-busy="true">
          <Panel><Skeleton className="h-3 w-56" /><Skeleton className="mt-6 h-[320px]" /></Panel>
          <div className="flex flex-col gap-4"><Panel><Skeleton className="h-3 w-24" /><Skeleton className="mt-4 h-20" /><Skeleton className="mt-4 h-16" /></Panel>
            <Panel><Skeleton className="h-24" /></Panel></div>
        </div>
      ) : rows.length === 0 ? (
        <div className="mt-7 rounded-2xl bg-surface-2 px-6 py-14 text-center">
          <p className="text-[17px] font-semibold text-ink">No {groupNoun(by)} has results for {q} yet</p>
          <p className="mt-1 text-[14px] text-ink-2">Groups appear once their companies' statements for the quarter are saved.</p>
        </div>
      ) : (
        <>
          <div className="mt-7 grid gap-4 lg:grid-cols-[7fr_5fr]">
            <Panel title={<>Profit growth by {groupNoun(by)}, {q} <span className="font-normal text-ink-2">· ranked by median profit growth{cut !== "all" ? `, ${CUT_WORDS[cut]}` : ""}</span>
              <span className="mt-2 flex flex-wrap gap-3.5 text-[12.5px] font-normal text-ink-2">
                <span><i aria-hidden className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full bg-accent align-[-1px]" />Median</span>
                <span><i aria-hidden className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full align-[-1px] ring-[1.8px] ring-inset ring-ink-2" />Total (all profits added up)</span>
              </span></>}>
              <div className={cn(rows.length > 14 && "max-h-[620px] overflow-y-auto")}>
                <RankedDots rows={rows} total={(r) => patTotal(r, cut)} onPick={(r) => onPick(r, by)} />
              </div>
            </Panel>
            <div className="flex flex-col gap-4">
              <Panel title="What it says">
                <p className="text-[19px] font-semibold leading-[1.32] tracking-[-0.01em] text-ink sm:text-[21px]"><Segs segs={groupsLead(rows, by)} /></p>
                <ul className="mt-3.5 grid gap-2 text-[14px] text-ink-2">{groupsBullets(rows, by).map((t) => <li key={t}>· {t}</li>)}</ul>
              </Panel>
              <Panel title="Median or total?" className="text-[15px] text-ink-2">
                <p><b className="text-ink">Median</b> is the middle value: every company counts the same. <b className="text-ink">Total</b> adds up all their
                  profits: the biggest companies count most. Companies that turned a loss into a profit have no % and sit out of medians; totals include them.</p>
              </Panel>
            </div>
          </div>

          <div className="mb-2 mt-[34px] flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-[20px] font-bold tracking-[-0.01em] text-ink">All {plural}</h2>
              <p className="text-[13.5px] text-ink-2">Growth vs the same quarter a year ago · sorted by median profit growth · click a row to see its companies</p>
            </div>
            <div className="flex flex-wrap gap-3.5 text-[12.5px] text-ink-2" aria-hidden>
              {KEY.map(([c, l]) => <span key={l}><i className={cn("mr-1.5 inline-block h-2.5 w-2.5 rounded-[3px] align-[-1px]", c)} />{l}</span>)}
            </div>
          </div>
          <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
            <table className="w-full min-w-[1180px] table-fixed border-collapse text-[14px]">
              <colgroup>{[14, 7, 8.5, 6.5, 6.5, 7, 7.5, 8, 7.5, 10.5, 11, 6].map((w, i) => <col key={i} style={{ width: `${w}%` }} />)}</colgroup>
              <thead className="text-[13px] font-semibold text-ink-2">
                <tr>
                  <th colSpan={3} /><th colSpan={3} scope="colgroup" className="pb-0 text-center font-semibold text-ink-2">Profit, total growth</th><th colSpan={6} />
                </tr>
                <tr className="[&>th]:border-b [&>th]:border-line [&>th]:px-3 [&>th]:py-2.5 [&>th]:text-right [&>th]:align-bottom [&>th]:font-semibold">
                  <th scope="col" className="!text-left">{by === "index" ? "Index" : by === "sector" ? "Sector" : "Industry"}</th>
                  <th scope="col">Reported</th>
                  <th scope="col" aria-sort="descending" className="text-ink"><span className="inline-flex items-center gap-1">Profit median<ArrowDown aria-hidden className="h-3 w-3" /></span></th>
                  {CUTS.map((c) => (
                    <th key={c.key} scope="col" className={cn(c.key === cut && "text-ink shadow-[inset_0_-2px_0_var(--accent)]")}>{c.key === "ex_financials" ? "Ex-fin." : c.key === "all" ? "All" : "Financials"}</th>
                  ))}
                  <th scope="col">Financials'<span className="block text-[12px] font-normal text-ink-3">share of profit</span></th>
                  <th scope="col">Revenue total<span className="block text-[12px] font-normal text-ink-3">{CUT_WORDS[cut]}</span></th>
                  <th scope="col">EBITDA total<span className="block text-[12px] font-normal text-ink-3">ex-financials</span></th>
                  <th scope="col" className="!text-left">Median trend<span className="block text-[12px] font-normal text-ink-3">8 quarters, one scale</span></th>
                  <th scope="col">Profit growth spread<span className="block text-[12px] font-normal text-ink-3">% of companies</span></th>
                  <th scope="col">Speeding<span className="block text-[12px] font-normal text-ink-3">up</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} tabIndex={0} onClick={() => onPick(r, by)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(r, by); } }}
                    title={`Show the companies in ${r.label}`}
                    className="num cursor-pointer hover:[&>td]:bg-[#f7f8fa] focus-visible:[&>td]:bg-accent-soft [&>td]:border-b [&>td]:border-line [&>td]:px-3 [&>td]:py-3 [&>td]:text-right [&>td]:align-middle">
                    <td className="!text-left"><span className="block truncate font-sans text-[14.5px] font-bold text-ink" title={r.id}>{r.label}</span></td>
                    <td>
                      <div className="whitespace-nowrap text-ink">{r.reported}{r.of != null && <span className="text-ink-3"> / {r.of}</span>}</div>
                      {r.of ? <span className="ml-auto mt-1.5 block h-[5px] w-14 overflow-hidden rounded-full bg-surface-2"><i className="block h-full bg-ink-3" style={{ width: `${Math.min(100, (r.reported / r.of) * 100)}%` }} /></span> : null}
                    </td>
                    <td><Growth value={r.pat_median} className="text-[15px]" /></td>
                    {CUTS.map((c) => (
                      <td key={c.key} className={c.key === cut ? "font-bold text-ink" : "text-ink-2"}>{fmtPct(patTotal(r, c.key))}</td>
                    ))}
                    <td className="text-ink">{r.financials_share_pct == null ? "—" : `${Math.round(r.financials_share_pct)}%`}</td>
                    <td className="text-ink">{fmtPct(revTotal(r, cut))}</td>
                    <td className="text-ink">{fmtPct(r.ebitda_total_ex_financials)}</td>
                    <td className="!text-left"><Spark vals={r.trend_pat_median} lo={lo} hi={hi} w={104} h={30}
                      title={`${r.label}: ${r.trend_pat_median.map((v, i) => `${labels[i]} ${fmtPct(v)}`).join(", ")}`} /></td>
                    <td><SpreadStack pct={r.spread_pct} /></td>
                    <td className="text-ink">{r.speeding_up_pct == null ? "—" : `${Math.round(r.speeding_up_pct)}%`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-[18px] grid gap-x-10 gap-y-2.5 text-[13px] text-ink-3 sm:grid-cols-2">
            {by === "index" ? (
              <p><b className="font-semibold text-ink-2">Index members</b> {res.data.index_tracking_since
                ? <>are tracked weekly since {istDate(res.data.index_tracking_since)}; quarters before use the list as first read, so a company that left an index earlier may be missing.</>
                : <>are the list as first read; weekly tracking has not started.</>}</p>
            ) : (
              <p><b className="font-semibold text-ink-2">{by === "sector" ? "Sectors" : "Industries"}</b> are NSE's own classification as stored ({by === "sector" ? "first" : "second"} step of the path); companies with none are left out.</p>
            )}
            <p><b className="font-semibold text-ink-2">EBITDA</b> totals leave out banks, NBFCs and insurers. Banks' revenue is interest income; insurers count in profit only. Profit is as filed, not adjusted; consolidated where filed.</p>
          </div>
        </>
      )}
    </div>
  );
}
