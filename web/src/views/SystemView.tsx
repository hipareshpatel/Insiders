import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ownerApi, setOwnerToken, useOwnerToken } from "../lib/owner";
import type { FailedFiling, PipelineRun, ProviderUsage, ReviewCard } from "../../shared/types";
import { Badge } from "../components/ui/badge";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { istDateTime, num, relativeTime, titleCase } from "../lib/format";
import { Empty, Loading } from "./FeedView";

const CEILING = 0.95;
const PROVIDER_LABEL: Record<string, string> = { groq: "Groq", nvidia: "NVIDIA NIM", mistral: "Mistral", zai: "Z.AI", cloudflare: "Workers AI" };

export function SystemView() {
  const query = useQuery({ queryKey: ["system"], queryFn: api.system, refetchInterval: 60_000 });
  if (query.isPending) return <Loading />;
  if (query.isError) return <div className="p-6"><Empty title="Could not load system status" body={String(query.error)} /></div>;
  const s = query.data;
  const count = (status: string) => s.ledger_today.find((r) => r.status === status)?.n ?? 0;
  const discoveredToday = s.ledger_today.reduce((a, r) => a + r.n, 0);
  const cards7d = s.cards_7d.reduce((a, r) => a + r.n, 0);
  const high7d = s.cards_7d.find((r) => r.impact_level === "HIGH")?.n ?? 0;

  const start = new Date(`${s.backfill.start}T00:00:00Z`).getTime();
  const end = new Date(`${s.today}T00:00:00Z`).getTime() - 86400_000;
  const through = s.backfill.discovered_through ? new Date(`${s.backfill.discovered_through}T00:00:00Z`).getTime() : start - 86400_000;
  const totalDays = Math.max(1, Math.round((end - start) / 86400_000) + 1);
  const doneDays = Math.min(totalDays, Math.max(0, Math.round((through - start) / 86400_000) + 1));

  return (
    <div className="mx-auto w-full max-w-[1240px] space-y-4 px-4 py-6 sm:px-6">
      <header>
        <h1 className="font-display text-[30px] leading-tight text-ink">System</h1>
        <p className="mt-1 text-sm text-ink-2">Throughput, backfill progress and free-tier quota health. Refreshes every minute.</p>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Filings today" value={discoveredToday} sub={`${count("DROPPED_RULE")} noise · ${count("NOT_MATERIAL")} not material · ${count("DUPLICATE")} duplicate`} />
        <Stat label="Analysed today" value={count("ANALYZED")} sub={`${cards7d} cards in 7 days · ${high7d} high impact`} />
        <Stat label="Queue" value={s.queue.pending} cap={s.queue.cap} sub="pending analysis" tone={s.queue.pending > 500 ? "warn" : undefined} />
        <Stat label="Failed" value={s.queue.failed} cap={s.queue.cap} sub="3 tries, then one more each night" tone={s.queue.failed ? "warn" : undefined} />
      </div>

      <section className="rounded-xl border border-line bg-surface p-4">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-display text-[18px] text-ink">Historical backfill</h2>
          <span className="num text-xs text-ink-2">
            {s.backfill.complete ? "Complete" : `Filing lists fetched for ${doneDays} of ${totalDays} days`} · {s.backfill.start}
            {s.backfill.discovered_through ? ` to ${s.backfill.discovered_through}` : ""}
          </span>
        </div>
        <Meter value={s.backfill.complete ? 1 : doneDays / totalDays} />
        {!s.backfill.complete && s.backfill.companies_total ? (
          <div className="mt-3">
            <div className="num mb-1 text-xs text-ink-2">
              {/* the list is rebuilt each morning from the companies still owing history, so this is today's progress, not the
                  total (owner, 2026-10-21: "39 yesterday, zero this morning") */}
              Today: {num(Math.max(0, s.backfill.companies_total - (s.backfill.companies_left ?? 0)))} of {num(s.backfill.companies_total)} companies with history still to read are done; the list restarts each morning without the finished ones
            </div>
            <Meter value={1 - (s.backfill.companies_left ?? 0) / Math.max(1, s.backfill.companies_total)} />
          </div>
        ) : null}
        <p className="mt-2 text-xs text-ink-3">
          Days are discovered oldest first; history is then analysed company by company, largest market cap first, each in date order, so early results and AGM guidance are in memory before later filings.
        </p>
        {s.d1 ? (
          <p className="num mt-2 text-xs text-ink-3">
            D1 today: {num(s.d1.writes_today)} rows written (free tier 100,000; backfill pauses at the budget)
            {s.d1.size_bytes ? ` · database ${(s.d1.size_bytes / 1e6).toFixed(1)} MB of 500 MB` : ""}
          </p>
        ) : null}
        {s.market_coverage ? (
          <p className="num mt-1 text-xs text-ink-3">
            Prices (Yahoo Finance, {s.market_coverage.date.slice(0, 10)}): {num(s.market_coverage.priced)} of {num(s.market_coverage.companies)} companies
            {s.market_coverage.missing ? ` · ${num(s.market_coverage.missing)} without a price (${s.market_coverage.missing_pct}%)` : ""}
          </p>
        ) : null}
      </section>

      <OwnerMode />

      <ScheduledJobs jobs={s.jobs ?? {}} />
      <FailedFilings rows={s.failed_recent ?? []} />
      <ReviewQueue />
      <OwnerVerdicts />

      <section className="rounded-xl border border-line bg-surface">
        <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-4 py-3">
          <h2 className="font-display text-[18px] text-ink">AI provider health · current quota day</h2>
          <span className="text-xs text-ink-3">Models leave the pool at {CEILING * 100}% of their daily quota</span>
        </header>
        {s.usage.length === 0 ? <p className="px-4 py-4 text-sm text-ink-3">No AI calls recorded today.</p> : (
          <ul className="divide-y divide-line">
            {s.usage.map((u) => <ProviderRow key={`${u.provider}:${u.model}`} usage={u} />)}
          </ul>
        )}
      </section>

      <section className="overflow-hidden rounded-xl border border-line bg-surface">
        <header className="border-b border-line px-4 py-3">
          <h2 className="font-display text-[18px] text-ink">Recent pipeline runs</h2>
          {/* owner, 2026-10-21: "what does this title mean" */}
          <p className="mt-0.5 text-[12.5px] leading-relaxed text-ink-3">
            Each row is one pass of the pipeline (GitHub Actions, every 15 minutes): it looks for new NSE filings, reads them
            and writes cards. "All" runs do today's filings first, then history.
          </p>
        </header>
        {s.runs.length === 0 ? <p className="px-4 py-4 text-sm text-ink-3">No runs recorded yet.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-[13.5px]">
              <thead className="eyebrow border-b border-line text-left text-ink-3">
                <tr>
                  {RUN_COLUMNS.map(([h, help]) => <th key={h} title={help} className="cursor-help px-4 py-2.5 font-semibold">{h}</th>)}
                </tr>
              </thead>
              <tbody>{s.runs.map((r) => <RunRow key={r.run_id} run={r} />)}</tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

/** The owner enters OWNER_TOKEN once; this browser then shows Star/Noise and watchlist controls. */
function OwnerMode() {
  const token = useOwnerToken();
  const [value, setValue] = useState("");
  const [state, setState] = useState<"idle" | "checking" | "bad">("idle");
  async function save() {
    setState("checking");
    try {
      await ownerApi.check(value.trim());
      setOwnerToken(value.trim());
      setValue("");
      setState("idle");
    } catch {
      setState("bad");
    }
  }
  return (
    <section className="rounded-xl border border-line bg-surface px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-[18px] text-ink">Owner mode</h2>
          <p className="text-xs text-ink-3">Star or mark cards as noise (the prompts learn from them) and keep a watchlist. Stored in this browser only.</p>
        </div>
        {token ? (
          <button type="button" onClick={() => setOwnerToken(null)} className="h-9 rounded-lg border border-line px-3 text-[13px] font-medium text-ink hover:border-accent-line">
            Sign out of owner mode
          </button>
        ) : (
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void save(); }}>
            <input type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder="OWNER_TOKEN" aria-label="Owner token"
              className="h-9 w-48 rounded-lg border border-line bg-surface px-3 text-[13px] text-ink" />
            <button type="submit" disabled={!value.trim() || state === "checking"}
              className="h-9 rounded-lg bg-accent px-3 text-[13px] font-medium text-accent-ink disabled:opacity-50">
              {state === "checking" ? "Checking…" : "Enter"}
            </button>
            {state === "bad" && <span className="self-center text-xs text-neg">Token refused</span>}
          </form>
        )}
      </div>
    </section>
  );
}

function Stat({ label, value, sub, tone, cap }: { label: string; value: number; sub: string; tone?: "warn"; cap?: number }) {
  return (
    <div className="rounded-xl border border-line bg-surface px-4 py-3">
      <div className="eyebrow text-ink-3">{label}</div>
      <div className={cn("num mt-1.5 text-[26px] font-bold leading-none", tone === "warn" ? "text-warn" : "text-ink")}>
        {num(value)}{cap && value >= cap ? "+" : ""}
      </div>
      <div className="mt-0.5 text-xs text-ink-2">{sub}</div>
    </div>
  );
}

function Meter({ value, ceiling }: { value: number; ceiling?: number }) {
  const v = Math.max(0, Math.min(1, value));
  const tone = ceiling && v >= ceiling ? "bg-neg" : ceiling && v >= ceiling * 0.8 ? "bg-warn" : "bg-accent";
  return (
    <div className="relative h-2 overflow-hidden rounded-full bg-surface-2" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v * 100)}>
      <div className={cn("h-full rounded-full transition-[width]", tone)} style={{ width: `${v * 100}%` }} />
      {ceiling ? <div className="absolute inset-y-0 w-px bg-ink-2" style={{ left: `${ceiling * 100}%` }} title="95% safety ceiling" /> : null}
    </div>
  );
}

function ProviderRow({ usage }: { usage: ProviderUsage }) {
  const tokens = usage.input_tokens + usage.output_tokens;
  const ratios = [usage.limit_rpd ? usage.requests / usage.limit_rpd : null, usage.limit_tpd ? tokens / usage.limit_tpd : null].filter((r): r is number => r !== null);
  const utilisation = ratios.length ? Math.max(...ratios) : null;
  // by share of attempts, not by any one error: Gemini Flash-Lite served 472 requests on 21 Oct with 60 failures and was
  // shown as "Errors" all day, which read as a model switched off (owner, 2026-10-22). No model is switched off by an
  // error: the gateway skips it for 5 minutes after 3 failures in a row, for the day only on a stated daily quota.
  const attempts = usage.requests + usage.failures;
  const failRate = attempts ? usage.failures / attempts : 0;
  const status = utilisation !== null && utilisation >= CEILING ? "At ceiling"
    : attempts === 0 && usage.rate_limited > 0 ? "Rate limited"
    : attempts >= 5 && failRate >= 0.25 ? `Errors ${Math.round(failRate * 100)}%`
    : usage.requests > 0 ? "Working" : "Idle";
  const statusStyle = status === "Working" ? "bg-pos-soft text-pos" : status === "Idle" ? "bg-surface-2 text-ink-3" : status === "At ceiling" ? "bg-neg-soft text-neg" : "bg-warn-soft text-warn";
  return (
    <li className="grid gap-2 px-4 py-3 md:grid-cols-[minmax(0,1.2fr)_minmax(0,2fr)_auto] md:items-center">
      <div className="min-w-0">
        <div className="truncate text-[14px] font-semibold text-ink">{PROVIDER_LABEL[usage.provider] ?? titleCase(usage.provider)}</div>
        <div className="num truncate text-[11px] text-ink-3">{usage.model}</div>
      </div>
      {/* min-w-0: a long one-line error must truncate, not widen the page (390 px was 822 wide, laptop T11) */}
      <div className="min-w-0 space-y-1">
        {utilisation !== null ? <Meter value={utilisation} ceiling={CEILING} /> : <div className="text-[11px] text-ink-3">No daily limit configured (paced per minute)</div>}
        <div className="num flex flex-wrap gap-x-3 text-[11px] text-ink-2">
          <span>{num(usage.requests)}{usage.limit_rpd ? ` / ${num(usage.limit_rpd)}` : ""} req</span>
          <span>{num(tokens)}{usage.limit_tpd ? ` / ${num(usage.limit_tpd)}` : ""} tok</span>
          {usage.rate_limited ? <span className="text-warn">{usage.rate_limited} × 429</span> : null}
          {usage.failures ? <span className={failRate >= 0.25 ? "text-neg" : "text-ink-3"}>{usage.failures} errors ({Math.round(failRate * 100)}% of attempts)</span> : null}
        </div>
        {usage.last_error ? <div className="truncate text-[11px] text-ink-3" title={usage.last_error}>{usage.last_error}</div> : null}
      </div>
      <Badge className={cn("justify-self-start md:justify-self-auto", statusStyle)}>{status}</Badge>
    </li>
  );
}

const RUN_COLUMNS: [string, string][] = [
  ["Started", "When the run began (hover for the exact time)"],
  ["Mode", "live: today's filings only; all: today's first, then history (backfill)"],
  ["Status", "OK: finished; PARTIAL: some filings failed and will be retried; STOPPED: the runner's time limit ended it"],
  ["New filings", "Filings seen for the first time on NSE in this run"],
  ["Read", "Filings read and decided in this run: a card, memory only, noise or a duplicate"],
  ["High impact", "Cards rated high impact"],
  ["To verify", "Cards held back or marked for review by the checks"],
  ["Took", "How long the run took"],
  ["Why it stopped", "The reason a run ended early: its time budget, the free AI quota, or the database's daily write limit"],
];

/** A table of the run's numbers; RUN_COLUMNS says what each one counts. */
function RunRow({ run }: { run: PipelineRun }) {
  let stats: Record<string, unknown> = {};
  try {
    stats = run.stats_json ? JSON.parse(run.stats_json) : {};
  } catch {
    /* tolerate malformed stats */
  }
  const n = (k: string) => (typeof stats[k] === "number" ? (stats[k] as number) : 0);
  const duration = run.finished_at ? Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000) : null;
  // A run still "RUNNING" after the job's timeout was stopped by the runner before it could report.
  const stale = run.status === "RUNNING" && Date.now() - new Date(run.started_at).getTime() > 70 * 60_000;
  const status = stale ? "STOPPED" : run.status;
  const tone = stale ? "bg-neg-soft text-neg" : run.status === "OK" ? "bg-pos-soft text-pos" : run.status === "RUNNING" ? "bg-info-soft text-info" : run.status === "PARTIAL" ? "bg-warn-soft text-warn" : "bg-neg-soft text-neg";
  return (
    <tr className="border-b border-line last:border-0">
      <td className="num whitespace-nowrap px-4 py-2 text-xs text-ink-2" title={istDateTime(run.started_at)}>{relativeTime(run.started_at)}</td>
      <td className="px-4 py-2 text-ink">{run.mode}</td>
      <td className="px-4 py-2"><Badge className={tone}>{status}</Badge></td>
      <td className="num px-4 py-2 text-ink">{num(n("discovered"))}</td>
      <td className="num px-4 py-2 text-ink">{num(n("analyzed"))}</td>
      <td className="num px-4 py-2 text-ink">{num(n("cards_high"))}</td>
      <td className="num px-4 py-2 text-ink">{num(n("needs_review"))}</td>
      <td className="num whitespace-nowrap px-4 py-2 text-ink-2">{duration !== null ? `${Math.floor(duration / 60)}m ${duration % 60}s` : "—"}</td>
      <td className="max-w-xs truncate px-4 py-2 text-xs text-ink-2" title={run.error ?? String(stats.stopped_reason ?? "")}>{run.error ?? String(stats.stopped_reason ?? "")}</td>
    </tr>
  );
}

/** The schedule (workflows on GitHub) and each job's last run, so a job that never ran shows (owner, 2026-10-20). */
const SCHEDULE: { command: string; what: string; when: string; days: number }[] = [
  { command: "market-data", what: "Prices, charts, technicals", when: "Tue-Sat 06:05 IST", days: 4 },
  { command: "post-mortem", what: "Price reaction after cards", when: "after market data", days: 4 },
  { command: "governance-sync", what: "Governance reports into memory", when: "daily 06:10 IST", days: 2 },
  { command: "shareholding-sync", what: "Shareholding into memory", when: "daily 06:10 IST", days: 2 },
  { command: "pledge-sync", what: "Promoter pledges into memory", when: "daily 06:10 IST", days: 2 },
  { command: "dgtr-sync", what: "Trade-remedy cases into memory", when: "daily 06:10 IST", days: 2 },
  { command: "annual-xbrl-catchup", what: "Annual reports re-read", when: "daily 06:10 IST", days: 2 },
  { command: "refresh-summaries", what: "Company summaries", when: "daily 06:10 IST", days: 2 },
  { command: "sync-companies", what: "Company master from NSE", when: "Mon-Fri 07:15 IST", days: 4 },
  { command: "seed-calls", what: "Calls and presentations into memory", when: "twice an hour 21:45-05:15 IST until done", days: 2 },
  { command: "backup", what: "Memory backup", when: "Mondays 02:00 IST", days: 8 },
];

// When the schedule reached main (#17, 20 Oct 2026 17:00 IST): a job with no run yet is only "Never run" once its
// first slot has passed; before that it is waiting for its first run (owner, 20 Oct: the panel read "Never run" for
// jobs whose first slot was the next morning)
const SCHEDULED_FROM = Date.parse("2026-10-20T11:30:00Z");

function ScheduledJobs({ jobs }: { jobs: Record<string, { at: string; ok: boolean }> }) {
  const now = Date.now();
  return (
    <section className="rounded-xl border border-line bg-surface p-4">
      <h2 className="text-[14px] font-semibold text-ink">Scheduled jobs</h2>
      <p className="mt-0.5 text-xs text-ink-3">No AI. The pipeline itself runs every 15 minutes (runs table below).</p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-[12.5px]">
          <thead className="text-left text-ink-3">
            <tr><th className="py-1 pr-3 font-medium">Job</th><th className="py-1 pr-3 font-medium">When</th><th className="py-1 pr-3 font-medium">Last run</th><th className="py-1 font-medium">Status</th></tr>
          </thead>
          <tbody>
            {SCHEDULE.map(({ command, what, when, days }) => {
              const last = jobs[command];
              const late = !last || now - new Date(last.at).getTime() > days * 86400_000;
              const waiting = !last && now - SCHEDULED_FROM <= days * 86400_000;
              const status = waiting ? "First run due" : !last ? "Never run" : !last.ok ? "Failed" : late ? "Overdue" : "OK";
              return (
                <tr key={command} className="border-t border-line">
                  <td className="py-1.5 pr-3 text-ink">{what}<span className="block text-[11px] text-ink-3">{command}</span></td>
                  <td className="py-1.5 pr-3 text-ink-2">{when}</td>
                  <td className="num py-1.5 pr-3 text-ink-2">{last ? istDateTime(last.at) : "—"}</td>
                  <td className={cn("py-1.5 font-semibold", status === "OK" ? "text-pos" : waiting ? "text-ink-3" : "text-warn")}>{status}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** Filings of the last 7 days that failed, with why; retried up to 3 times, then once more each night after 22:00
 * IST. The owner can re-run one now. */
function FailedFilings({ rows }: { rows: FailedFiling[] }) {
  const token = useOwnerToken();
  const [queued, setQueued] = useState<Set<string>>(new Set());
  if (!rows.length) return null;
  const requeue = async (newsId: string) => {
    if (!token) return;
    await ownerApi.requeue(token, newsId);
    setQueued((s) => new Set(s).add(newsId));
  };
  return (
    <section className="rounded-xl border border-line bg-surface p-4">
      <h2 className="text-[14px] font-semibold text-ink">Failed filings · last 7 days · {rows.length}</h2>
      <p className="mt-0.5 text-xs text-ink-3">
        A filing is tried up to 3 times; busy or rate-limited AI, timeouts and refusals do not count. After the third
        failure it gets one more try each night after 22:00 IST while it is within 7 days.
      </p>
      <ul className="mt-3 divide-y divide-line">
        {rows.map((f) => (
          <li key={f.news_id} className="flex flex-wrap items-start gap-3 py-2">
            <span className="min-w-0 flex-1 text-[13px]">
              <span className="font-semibold text-ink">{f.symbol ?? f.scrip_code}</span>
              <span className="text-ink-2"> · {f.headline ?? f.company_name}</span>
              <span className="num block text-xs text-ink-3">{istDateTime(f.filed_at)} · {f.attempts} of 3 tries used</span>
              {f.last_error && <span className="block break-words text-xs text-warn">{f.last_error}</span>}
            </span>
            {token && (
              <button type="button" disabled={queued.has(f.news_id)} onClick={() => requeue(f.news_id)}
                className="h-7 shrink-0 rounded-md border border-line px-2.5 text-xs font-medium text-ink-2 hover:text-ink disabled:opacity-50">
                {queued.has(f.news_id) ? "Queued for the next run" : "Re-run"}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

const VERDICT_TONE: Record<string, string> = { RIGHT: "text-pos", MINOR: "text-warn", WRONG: "text-neg" };
const VERDICT_TEXT: Record<string, string> = { RIGHT: "Right", MINOR: "Minor issue", WRONG: "Wrong" };

/** The owner's latest verdicts with their notes (owner mode), for the cloud lead to turn into fixes (O11). */
function OwnerVerdicts() {
  const token = useOwnerToken();
  const query = useQuery({ queryKey: ["verdict-list", token], enabled: !!token, queryFn: () => ownerApi.verdicts(token!) });
  const rows = (query.data?.verdicts ?? []).slice(0, 50);
  if (!token || !rows.length) return null;
  return (
    <section className="rounded-xl border border-line bg-surface p-4">
      <h2 className="text-[14px] font-semibold text-ink">Your verdicts · latest {rows.length}</h2>
      <p className="mt-0.5 text-xs text-ink-3">A card marked Wrong is held from the public feed with your note as the reason; Right publishes it.</p>
      <ul className="mt-3 divide-y divide-line">
        {rows.map((v) => (
          <li key={v.news_id} className="py-2 text-[13px]">
            <a href={`/feed?card=${encodeURIComponent(v.news_id)}`} className="hover:underline">
              <span className="font-semibold text-ink">{v.symbol}</span>
              <span className="text-ink-2"> · {v.headline ?? v.news_id}</span>
            </a>
            <span className="num block text-xs text-ink-3">
              <span className={cn("font-semibold", VERDICT_TONE[v.verdict])}>{VERDICT_TEXT[v.verdict] ?? v.verdict}</span>
              {" · "}{istDateTime(v.created_at)}{v.event_category ? ` · ${titleCase(v.event_category)}` : ""}
              {v.held_now === null ? " · card no longer stored" : v.held_now ? " · held" : " · public"}
            </span>
            {v.note && <span className="block text-xs text-ink-2">{v.note}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Cards held back by the checks, with what failed and (owner mode) a re-run. */
function ReviewQueue() {
  const token = useOwnerToken();
  const [queued, setQueued] = useState<Set<string>>(new Set());
  const query = useQuery({ queryKey: ["review", !!token], queryFn: () => (token ? ownerApi.review(token) : api.review()) });
  const cards = query.data?.cards ?? [];
  const total = query.data?.total ?? cards.length;
  const isQueued = (card: ReviewCard) => queued.has(card.news_id) || card.filing_status === "PENDING";
  const waiting = cards.filter(isQueued).length;
  if (!cards.length) return null;
  const problems = (card: ReviewCard) => {
    const out: string[] = [];
    try {
      const g = card.grounding ? JSON.parse(card.grounding) : null;
      if (g?.ungrounded?.length) out.push(`Not found in the filing: ${g.ungrounded.slice(0, 4).join(", ")}`);
      if (g?.math_mismatches?.length) out.push(`Math check: ${g.math_mismatches.slice(0, 2).join("; ")}`);
      if (g?.unsupported_claims?.length) out.push(`Unsupported: ${g.unsupported_claims.slice(0, 2).join("; ")}`);
      const r = card.review ? JSON.parse(card.review) : null;
      if (r?.issues?.length && !out.length) out.push(...r.issues.slice(0, 3));
    } catch {
      /* malformed: show the card without details */
    }
    return out;
  };
  const requeue = async (newsId: string) => {
    if (!token) return;
    await ownerApi.requeue(token, newsId);
    setQueued((s) => new Set(s).add(newsId));
  };
  return (
    <section className="rounded-xl border border-line bg-surface p-4">
      <h2 className="text-[14px] font-semibold text-ink">Needs review · {total}{waiting ? ` · ${waiting} re-run${waiting === 1 ? "" : "s"} queued` : ""}</h2>
      <p className="mt-0.5 text-xs text-ink-3">Cards whose figures or math the automatic checks could not confirm{total > cards.length ? ` (the latest ${cards.length} shown)` : ""}. A re-run replaces the card at the next pipeline run; it stays here when the new reading fails the checks again.</p>
      <ul className="mt-3 divide-y divide-line">
        {cards.map((card) => (
          <li key={card.news_id} className="flex flex-wrap items-start gap-3 py-2">
            <a href={`/feed?card=${encodeURIComponent(card.news_id)}`} className="min-w-0 flex-1 text-[13px] hover:underline">
              <span className="font-semibold text-ink">{card.symbol ?? card.scrip_code}</span>
              <span className="text-ink-2"> · {card.headline}</span>
              <span className="num block text-xs text-ink-3">{istDateTime(card.filed_at)} · {titleCase(card.event_category)}</span>
              {problems(card).map((p, i) => <span key={i} className="block text-xs text-warn">{p}</span>)}
            </a>
            {token && (
              <button type="button" disabled={isQueued(card)} onClick={() => requeue(card.news_id)}
                className="h-7 shrink-0 rounded-md border border-line px-2.5 text-xs font-medium text-ink-2 hover:text-ink disabled:opacity-50">
                {isQueued(card) ? "Queued for the next run" : "Re-run"}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
