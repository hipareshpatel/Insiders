import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ISSUE_LABEL, ISSUE_TYPES, type IssueRow, type IssueType } from "../../shared/cardChecks";
import { Badge } from "../components/ui/badge";
import { cn } from "../lib/cn";
import { ownerApi, useOwnerToken } from "../lib/owner";
import { titleCase } from "../lib/format";
import { Empty, Loading } from "./FeedView";

const day = (offset: number) => new Date(Date.now() + offset * 86400_000).toISOString().slice(0, 10);

/** The owner's list of cards with a check item: which card has which issue (TODO row 67). */
export function IssuesView() {
  const token = useOwnerToken();
  const [from, setFrom] = useState(day(-7));
  const [to, setTo] = useState(day(0));
  const [type, setType] = useState<IssueType | "all">("all");
  const query = useInfiniteQuery({
    queryKey: ["issues", token, from, to], enabled: !!token && from <= to, staleTime: 60_000,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => ownerApi.issues(token!, from, to, pageParam),
    getNextPageParam: (last) => last.next_cursor,
  });
  const rows = useMemo(() => (query.data?.pages ?? []).flatMap((p) => p.rows), [query.data]);
  const counts = useMemo(() => countTypes(rows), [rows]);
  const shown = type === "all" ? rows : rows.filter((r) => r.types.includes(type));

  if (!token) {
    return (
      <div className="mx-auto w-full max-w-[1240px] px-4 py-6 sm:px-6">
        <Empty title="Issues is for the site's owner" body="Sign in with the owner token on the System page." />
      </div>
    );
  }
  return (
    <div className="mx-auto w-full max-w-[1240px] space-y-4 px-4 py-6 sm:px-6">
      <header>
        <h1 className="font-display text-[30px] leading-tight text-ink">Issues</h1>
        <p className="mt-1 text-sm text-ink-2">Every card in the range that has something to look at: what our code corrected, what was held, checks that failed, and your own verdicts.</p>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-[12px] font-medium text-ink-3">From
          <input type="date" value={from} max={to} onChange={(e) => e.target.value && setFrom(e.target.value)}
            className="mt-0.5 block h-9 rounded-lg border border-line bg-surface px-2.5 text-[13px] text-ink" />
        </label>
        <label className="text-[12px] font-medium text-ink-3">To
          <input type="date" value={to} min={from} onChange={(e) => e.target.value && setTo(e.target.value)}
            className="mt-0.5 block h-9 rounded-lg border border-line bg-surface px-2.5 text-[13px] text-ink" />
        </label>
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Issue type">
        <TypeButton active={type === "all"} onClick={() => setType("all")} label="All" n={rows.length} />
        {ISSUE_TYPES.map((t) => <TypeButton key={t} active={type === t} onClick={() => setType(t)} label={ISSUE_LABEL[t]} n={counts[t]} />)}
      </div>

      {query.isPending ? <Loading /> : query.isError ? <Empty title="Could not load the issues" body={String(query.error)} />
        : !shown.length ? <Empty title="No cards with this issue in the range" />
        : (
          <div className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full min-w-[720px] text-left text-[13px]">
              <thead className="border-b border-line text-[12px] text-ink-3">
                <tr><th className="px-3 py-2 font-medium">Date</th><th className="px-3 py-2 font-medium">Company</th>
                  <th className="px-3 py-2 font-medium">Event</th><th className="px-3 py-2 font-medium">Issues</th>
                  <th className="px-3 py-2 font-medium">Card</th></tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.news_id} className="border-b border-line last:border-0 align-top">
                    <td className="num whitespace-nowrap px-3 py-2 text-ink-2">{r.filing_date}</td>
                    <td className="px-3 py-2 text-ink">{r.symbol ?? r.company_name}</td>
                    <td className="px-3 py-2 text-ink-2">{titleCase(r.event_category)}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {r.types.map((t) => (
                          <Badge key={t} className={cn(t.startsWith("verdict") || t === "held" ? "text-neg" : t === "corrected" ? "text-ink-2" : "text-warn")}>{ISSUE_LABEL[t]}</Badge>
                        ))}
                      </div>
                      {r.reasons[0] && <p className="mt-1 max-w-[520px] truncate text-[12px] text-ink-3" title={r.reasons.join(" · ")}>{r.reasons[0]}</p>}
                    </td>
                    <td className="px-3 py-2"><a href={`/feed?card=${encodeURIComponent(r.news_id)}`} className="font-medium text-accent hover:underline">Open</a></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

      {query.hasNextPage && (
        <button type="button" onClick={() => void query.fetchNextPage()} disabled={query.isFetchingNextPage}
          className="rounded-lg border border-line px-3 py-2 text-[13px] font-medium text-ink hover:bg-surface-2 disabled:opacity-60">
          {query.isFetchingNextPage ? "Loading..." : "Load older cards"}
        </button>
      )}
      <p className="text-[11.5px] leading-relaxed text-ink-3">
        Counts are for the {rows.length} cards loaded so far. Not in this version: disputes from the data checks (screener cross-check,
        NSE referee, self-check). Their results are artifacts, not stored per card yet.
      </p>
    </div>
  );
}

export function countTypes(rows: IssueRow[]): Record<IssueType, number> {
  const out = Object.fromEntries(ISSUE_TYPES.map((t) => [t, 0])) as Record<IssueType, number>;
  for (const r of rows) for (const t of r.types) out[t] += 1;
  return out;
}

function TypeButton({ active, onClick, label, n }: { active: boolean; onClick: () => void; label: string; n: number }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={active}
      className={cn("rounded-full border px-3 py-1 text-[12.5px] font-medium", active ? "border-accent bg-accent/10 text-ink" : "border-line text-ink-2 hover:bg-surface-2")}>
      {label} <span className="num text-ink-3">{n}</span>
    </button>
  );
}
