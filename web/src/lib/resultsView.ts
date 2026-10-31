/** The Results page's words and shapes, worked out from the API's numbers (shared/resultsTypes.ts): growth text, the season's
 *  sentences, chart geometry, the CSV and the URL's filters. No React here, so `node --test` runs the cases in resultsView.test.ts.
 *  The design is docs/design/results-kpi.md (Direction C, white theme). */

import { num } from "./format.ts";
import { INDICES, MARKET_CAP_STEPS, MOMENTUM_POINTS, RESULTS_SORTS } from "../../shared/resultsTypes.ts";
import type { GroupBy, GroupRow, KpiQuery, KpiRow, KpiSummary, Kind, Momentum, ResultsSort, Turn, View } from "../../shared/resultsTypes.ts";

export const GROWTH_STEPS = [0, 10, 20, 30, 50, 100] as const;   // "growth at least this much, per cent"
export const MARGIN_STEPS = [0, 100, 200, 300, 500] as const;    // "margin up at least this many basis points"
export const SPREAD_KEYS = ["below_0", "from_0_to_10", "from_10_to_20", "above_20"] as const;
export type SpreadKey = (typeof SPREAD_KEYS)[number];
export const SPREAD_LABEL: Record<SpreadKey, string> = { below_0: "Below 0%", from_0_to_10: "0–10%", from_10_to_20: "10–20%", above_20: "Above 20%" };

/** The columns the page may sort by: the Worker's own list (shared/resultsTypes.ts); anything else falls back to profit growth. */
export const SORTS = RESULTS_SORTS;
export type Sort = ResultsSort;
export const DEFAULT_SORT: Sort = "pat_yoy";
/** What each view ranks by until the reader picks a column: year-on-year by profit growth, momentum by profit pace, quarter-on-quarter by profit
 *  growth against last quarter (the three lists lead with different companies). */
export const VIEW_SORT: Record<View, Sort> = { yoy: "pat_yoy", momentum: "pat_momentum", qoq: "pat_qoq" };
/** A name sorts A to Z first; every figure highest first. */
/** The view a URL names (year-on-year when it names none or an unknown one). */
export const viewOf = (p: URLSearchParams): View => (p.get("view") === "momentum" ? "momentum" : p.get("view") === "qoq" ? "qoq" : "yoy");
export const firstDir = (sort: string): "asc" | "desc" => (sort === "company" ? "asc" : "desc");

// ---------- quarters ----------

const QMONTHS = ["April–June", "July–September", "October–December", "January–March"];

function parseQuarter(period: string): { q: number; fy: number } | null {
  const m = /^Q([1-4])FY(\d{2})$/.exec(period);
  return m ? { q: Number(m[1]), fy: 2000 + Number(m[2]) } : null;
}

/** "Q2FY27" as people read it: "Q2 FY27". */
export const quarterLabel = (period: string | null | undefined) => (period ?? "").replace(/^(Q[1-4])(FY\d{2})$/, "$1 $2");

/** The months a quarter covers: Q2FY27 is "July–September 2026" (the fiscal year ends in March of its label's year). */
export function quarterMonths(period: string | null | undefined): string {
  const p = parseQuarter(period ?? "");
  if (!p) return "";
  return `${QMONTHS[p.q - 1]} ${p.q === 4 ? p.fy : p.fy - 1}`;
}

/** The labels of the `n` quarters ending with `period`, oldest first ("Q3 FY25" ... "Q2 FY27"), for the 8-quarter series. */
export function quarterSeries(period: string | null | undefined, n = 8): string[] {
  const p = parseQuarter(period ?? "");
  if (!p) return Array.from({ length: n }, () => "");
  const out: string[] = [];
  let { q, fy } = p;
  for (let i = 0; i < n; i++) {
    out.unshift(`Q${q} FY${String(fy % 100).padStart(2, "0")}`);
    q -= 1;
    if (q === 0) { q = 4; fy -= 1; }
  }
  return out;
}

// ---------- numbers ----------

export type Tone = "up" | "down" | "flat";
export const toneOf = (v: number | null | undefined): Tone => (v == null || v === 0 ? "flat" : v > 0 ? "up" : "down");
/** The small arrow beside a growth figure: never colour alone. */
export const arrowOf = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "▲" : "▼");

const signed = (v: number, digits: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(digits)}`;
/** +13.9% / −5.2% (a true minus sign, as the design sets it). */
export const fmtPct = (v: number | null | undefined, digits = 1) => (v == null ? "—" : `${signed(v, digits)}%`);
/** A change above this is "NM" (not meaningful), the sell-side convention; the exact figure goes in the cell's tooltip (owner audit, 31 Oct 2026:
 *  +6,643.4% for a profit of 30.99 Cr). A margin outside -100%..+100% is "NM" too. */
export const NM_PCT = 999;
export const NM = "NM";
export const isNmPct = (v: number | null | undefined) => v != null && v > NM_PCT;
export const isNmMargin = (v: number | null | undefined) => v != null && Math.abs(v) > 100;
/** A growth per cent as the page shows it: "NM" past +999%, else the signed figure. */
export const fmtGrowth = (v: number | null | undefined) => (isNmPct(v) ? NM : fmtPct(v));
/** The margin in per cent, "NM" outside -100%..+100%. */
export const fmtMargin = (v: number | null | undefined) => (v == null ? "—" : isNmMargin(v) ? NM : `${v.toFixed(1)}%`);
/** +399 bp: a margin's change, 100 bp = 1 percentage point. */
export const fmtBp = (v: number | null | undefined) => (v == null ? "—" : `${signed(Math.round(v), 0)} bp`);
/** +81.8 pts: a change in growth, this quarter's minus last quarter's. */
export const fmtPts = (v: number | null | undefined) => (v == null ? "—" : `${signed(v, 1)} pts`);

export const TURN_TEXT: Record<Turn, string> = {
  LOSS_TO_PROFIT: "Loss → profit", PROFIT_TO_LOSS: "Profit → loss", LOSS_NARROWED: "Loss narrowed", LOSS_WIDENED: "Loss widened",
};
export const turnTone = (t: Turn): Tone => (t === "LOSS_TO_PROFIT" || t === "LOSS_NARROWED" ? "up" : "down");

/** A growth figure in words: a per cent, or the named turn across a loss (no per cent exists), or nothing. */
export function growth(value: number | null | undefined, turn?: Turn | null, unit: "%" | "bp" = "%"): { text: string; tone: Tone; arrow: string; title?: string } | null {
  if (turn) { const tone = turnTone(turn); return { text: TURN_TEXT[turn], tone, arrow: tone === "up" ? "▲" : "▼" }; }
  if (value == null) return null;
  if (unit === "%" && isNmPct(value)) return { text: NM, tone: "up", arrow: "▲", title: `Not meaningful: ${fmtPct(value)} (a change above +${NM_PCT}%)` };
  if (unit === "bp") return { text: fmtBp(value), tone: toneOf(value), arrow: arrowOf(value), title: "100 bp = 1 percentage point" };
  return { text: fmtPct(value), tone: toneOf(value), arrow: arrowOf(value) };
}

/** The quiet second line of a growth cell: the amount this quarter and last quarter's growth ("₹2,900 Cr · was +17.1%"). */
export function wasLine(amount: string | null, prevYoy: number | null | undefined, prevTurn?: Turn | null): string {
  const was = prevTurn ? `last qtr ${TURN_TEXT[prevTurn].toLowerCase()}` : prevYoy != null ? `was ${fmtGrowth(prevYoy)}` : "";
  return [amount, was].filter(Boolean).join(" · ");
}

// ---------- kinds of company ----------

export const KIND_TAG: Record<Kind, string> = { company: "", bank: "Bank", nbfc: "NBFC", insurer: "Insurer", reit: "REIT", invit: "InvIT" };

/** What each column holds for a kind of company: a bank's revenue is interest income and it has no EBITDA; an NBFC's EBITDA columns hold
 *  its financing profit and margin; an insurer has profit only (docs/design/results-kpi.md rule 1). null: the line is not shown. */
export function lineLabels(kind: Kind): { revenue: string | null; ebitda: string | null; margin: string | null } {
  switch (kind) {
    case "bank": return { revenue: "Interest income", ebitda: null, margin: null };
    case "nbfc": return { revenue: "Income", ebitda: "Financing profit", margin: "Financing margin" };
    case "insurer": return { revenue: null, ebitda: null, margin: null };
    default: return { revenue: "Revenue", ebitda: "EBITDA", margin: "EBITDA margin" };
  }
}

/** Why a cell is empty, said once in the cell (an honest blank, not a zero). */
export function blankNote(kind: Kind, line: "revenue" | "ebitda" | "margin"): string {
  if (kind === "insurer") return line === "revenue" ? "Insurers: profit only" : "";
  if (kind === "bank") return line === "ebitda" ? "Not shown for banks" : "";
  return "";
}

export const MOMENTUM_TEXT: Record<Momentum, string> = {
  speeding_up: "Speeding up", slowing: "Slowing", steady: "Steady", not_comparable: "Not comparable",
};

/** Momentum from a change in growth, in points: >= +2 speeding up, <= -2 slowing, between steady; no change, not comparable. */
export function momentumOf(pts: number | null | undefined): Momentum {
  if (pts == null) return "not_comparable";
  return pts >= MOMENTUM_POINTS ? "speeding_up" : pts <= -MOMENTUM_POINTS ? "slowing" : "steady";
}

/** The pace sentence under the side panel's chart. */
export function paceSentence(row: Pick<KpiRow, "pat_yoy" | "pat_prev_yoy" | "pat_momentum_pts" | "pat_turn" | "pat_prev_turn">): string {
  if (row.pat_yoy == null || row.pat_prev_yoy == null || row.pat_momentum_pts == null) {
    if (row.pat_turn) return `Profit growth has no % this quarter: ${TURN_TEXT[row.pat_turn].toLowerCase()} against a year ago.`;
    if (row.pat_prev_turn) return `Last quarter's profit growth has no %: ${TURN_TEXT[row.pat_prev_turn].toLowerCase()}.`;
    return "No growth figure for last quarter to compare with.";
  }
  const m = momentumOf(row.pat_momentum_pts);
  const tail = m === "steady" ? "about the same pace" : `${m === "speeding_up" ? "speeding up" : "slowing"} by ${Math.abs(row.pat_momentum_pts).toFixed(1)} pts`;
  return `Profit growth was ${fmtPct(row.pat_prev_yoy)} last quarter and ${fmtPct(row.pat_yoy)} now: ${tail}.`;
}

/** Words for a row the momentum chart cannot place (a change across a loss in either quarter). */
export function notComparableText(row: Pick<KpiRow, "pat_turn" | "pat_prev_turn" | "pat_yoy" | "pat_prev_yoy">): string {
  const now = row.pat_turn === "LOSS_TO_PROFIT" || row.pat_turn === "LOSS_NARROWED" || row.pat_turn === "LOSS_WIDENED"
    ? "Loss a year ago: no % to compare." : row.pat_turn === "PROFIT_TO_LOSS" ? "A loss this quarter: no % to compare."
    : row.pat_yoy == null ? "No profit growth this quarter." : "";
  const was = row.pat_prev_turn ? `Last quarter the ${row.pat_prev_turn === "LOSS_NARROWED" ? "loss narrowed" : row.pat_prev_turn === "LOSS_WIDENED"
    ? "loss widened" : row.pat_prev_turn === "LOSS_TO_PROFIT" ? "loss turned to profit" : "profit turned to loss"}.`
    : row.pat_prev_yoy == null ? "No growth figure last quarter." : "";
  return [now, was].filter(Boolean).join(" ");
}

// ---------- the season, in words ----------

/** A run of text; `b` bold, `up`/`down` coloured (with a sign in the text, so never colour alone). */
export type Seg = { t: string; b?: boolean; tone?: Tone };

/** A count in Indian grouping ("1,27,000"): the page's one helper (lib/format.ts). */
export const fmtCount = (n: number) => num(n);

/** What the median of profit growth covers (rule: the median keeps companies with a per cent change; the rest are in the counts). */
export function medianNote(s: Pick<KpiSummary, "median_pat_n" | "pat_turn_n">): string {
  const t = s.pat_turn_n;
  return `Median of ${fmtCount(s.median_pat_n)} ${s.median_pat_n === 1 ? "company" : "companies"} with a % change; ${fmtCount(t)} whose profit crossed zero (loss to profit, profit to loss, loss narrowed or widened) ${t === 1 ? "is" : "are"} not in the median but ${t === 1 ? "is" : "are"} in the counts.`;
}

const pctOf = (a: number, b: number) => (b > 0 ? Math.round((a / b) * 100) : 0);

/** "Of 236 companies that have reported, 175 grew profit; median profit growth +13.9%." */
export function seasonHeadline(s: KpiSummary, filtered = false): Seg[] {
  if (s.n === 0) return [{ t: filtered ? "No company in this list has reported yet." : "No company has reported for this quarter yet." }];
  // the base of "grew" is the companies with a year-ago quarter to compare (C1); the rest are said once, in brackets
  const base = s.pat_of, noun = (n: number) => (n === 1 ? "company" : "companies");
  const gap = s.pat_n < s.n || base < s.pat_n ? ` (${fmtCount(s.n)} reported)` : "";
  const out: Seg[] = [
    { t: s.pat_of < s.n
        ? `Of ${fmtCount(base)} ${noun(base)} ${filtered ? "in this list " : ""}with a year-ago quarter to compare${gap}, `
        : filtered ? `Of ${fmtCount(s.n)} ${noun(s.n)} in this list, ` : `Of ${fmtCount(s.n)} ${noun(s.n)} that have reported, ` },
    { t: fmtCount(s.pat_up), tone: "up" }, { t: " grew profit" },
  ];
  if (s.median_pat_yoy != null) out.push({ t: "; median profit growth " }, { t: fmtPct(s.median_pat_yoy), tone: toneOf(s.median_pat_yoy) });
  out.push({ t: "." });
  return out;
}

/** The plain-English lines under the headline. The leading-index line and the best-median count need the groups by index; without
 *  them those parts are left out, never guessed. */
export function seasonLines(s: KpiSummary, indexRows?: GroupRow[] | null): Seg[][] {
  if (s.n === 0) return [];
  const lines: Seg[][] = [];
  const { median_revenue_yoy: rev, median_ebitda_yoy: ebitda, median_pat_yoy: pat } = s;
  if (rev != null && pat != null) {
    const lead = pat > rev ? "Profit grew faster than sales" : pat < rev ? "Sales grew faster than profit" : "Profit grew as fast as sales";
    lines.push([{ t: `${lead}: median revenue growth ` }, { t: fmtPct(rev), b: true },
      ...(ebitda != null ? [{ t: ", EBITDA " }, { t: fmtPct(ebitda), b: true }] : []), { t: "." }]);
  }
  const m = s.momentum;
  if (m.speeding_up + m.slowing > 0) {
    lines.push([{ t: String(m.speeding_up), b: true }, { t: " are speeding up, growing profit faster than last quarter; " },
      { t: String(m.slowing), b: true }, { t: " are slowing." }]);
  }
  const ranked = (indexRows ?? []).filter((r) => r.pat_median != null).sort((a, b) => b.pat_median! - a.pat_median!);
  if (ranked.length >= 2) {
    const top = ranked[0];
    const other = top.id === "NIFTY50" ? ranked[1] : ranked.find((r) => r.id === "NIFTY50") ?? ranked[ranked.length - 1];
    lines.push([{ t: top.label, b: true }, { t: " leads: its median profit growth is " }, { t: fmtPct(top.pat_median), b: true },
      { t: `${coverageOf(top)}, against ${fmtPct(other.pat_median)} in the ${other.label}${coverageOf(other)}.` }]);
  }
  const fell = s.spread.below_0;
  const fellLine: Seg[] = [{ t: String(fell), b: true }, { t: ` ${fell === 1 ? "company" : "companies"} (${pctOf(fell, s.n)}%) earned less than a year ago` }];
  const withTrend = wellCovered((indexRows ?? []).filter((r) => r.trend_pat_median.some((v) => v != null)));
  if (withTrend.length) {
    fellLine.push({ t: "; " }, { t: `${bestInEight(withTrend)} of ${withTrend.length}`, b: true },
      { t: ` ${withTrend.length === 1 ? "index" : "indices"} (with at least ${COVERAGE_MIN * 100}% of members reported) show their best median in 8 quarters.` });
  } else fellLine.push({ t: "." });
  lines.push(fellLine);
  return lines;
}

/** An index counts toward "best median in 8 quarters" only when this share of its members has reported: the current point is the median of
 *  early reporters, set against full-season medians (measured 31 Oct 2026: Midcap 150 showed a high on 80 of 150). */
export const COVERAGE_MIN = 0.8;
/** The groups that can be compared with full seasons: a sector or industry (no member list) is kept as it is. */
export const wellCovered = (rows: GroupRow[]): GroupRow[] => rows.filter((r) => !r.of || r.reported / r.of >= COVERAGE_MIN);
/** " (32 of 50 reported)" for an index, "" for a group with no member list. */
export const coverageOf = (r: Pick<GroupRow, "reported" | "of">) => (r.of ? ` (${fmtCount(r.reported)} of ${fmtCount(r.of)} reported)` : "");

/** How many groups have this quarter's median as the highest of their 8-quarter trend (an index counts only with 80% of its members reported). */
export function bestInEight(rows: GroupRow[]): number {
  return wellCovered(rows).filter((r) => {
    const vals = r.trend_pat_median.filter((v): v is number => v != null);
    const last = r.trend_pat_median[r.trend_pat_median.length - 1];
    return last != null && vals.length > 1 && last >= Math.max(...vals);
  }).length;
}

export const indexLabel = (id: string | null | undefined) => INDICES.find((x) => x.id === id)?.label ?? id ?? "";

/** "30 Oct" from a filing's own timestamp, in IST. */
export function filedDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short" });
}

/** "30 Oct 2026, 3:35 pm IST": the newest filing timestamp among rows. */
export function newestFiled(rows: Pick<KpiRow, "filed_at">[]): string | null {
  const iso = rows.map((r) => r.filed_at).filter((x): x is string => !!x).sort((a, b) => Date.parse(b) - Date.parse(a))[0];
  if (!iso) return null;
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric" });
  const time = d.toLocaleTimeString("en-US", { timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit", hour12: true }).toLowerCase();
  return `${day}, ${time} IST`;
}

// ---------- charts ----------

/** The spread of profit growth as four bars; a turn across a loss has no per cent and sits outside them. */
export function spreadBins(s: KpiSummary["spread"]): { key: SpreadKey; label: string; n: number }[] {
  return SPREAD_KEYS.map((key) => ({ key, label: SPREAD_LABEL[key], n: s[key] }));
}

/** A bar's height in pixels against the tallest; any bar above zero gets at least 2px, so a small count stays visible. */
export function barHeight(n: number, max: number, px: number): number {
  if (n <= 0 || max <= 0) return 0;
  return Math.max(2, (n / max) * px);
}

/** Where the median sits on the four bars: which bar, and how far across it (the outer bars read as -50..0 and 20..60). */
export function medianSlot(median: number | null | undefined): { bin: number; frac: number } | null {
  if (median == null) return null;
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  if (median < 0) return { bin: 0, frac: clamp((median + 50) / 50) };
  if (median < 10) return { bin: 1, frac: clamp(median / 10) };
  if (median < 20) return { bin: 2, frac: clamp((median - 10) / 10) };
  return { bin: 3, frac: clamp((median - 20) / 40) };
}

/** One scale for many series (sparklines compared by eye must share it): [low, high], whole numbers, never empty. */
export function sharedScale(series: (number | null)[][], includeZero = false): [number, number] {
  const vals = series.flat().filter((v): v is number => v != null && Number.isFinite(v));
  if (includeZero) vals.push(0);
  if (!vals.length) return [0, 1];
  let lo = Math.floor(Math.min(...vals)), hi = Math.ceil(Math.max(...vals));
  if (lo === hi) { lo -= 1; hi += 1; }
  return [lo, hi];
}

/** A sparkline's SVG path on a fixed scale; a missing quarter breaks the line. `last` is the end point when this quarter exists. */
export function sparkPath(vals: (number | null)[], w: number, h: number, lo: number, hi: number, pad = 3): { d: string; last: [number, number] | null } {
  const n = vals.length;
  const span = hi - lo || 1;
  const x = (i: number) => pad + (n > 1 ? (i * (w - 2 * pad)) / (n - 1) : (w - 2 * pad) / 2);
  const y = (v: number) => h - pad - ((Math.min(hi, Math.max(lo, v)) - lo) / span) * (h - 2 * pad);
  let d = "", on = false;
  vals.forEach((v, i) => {
    if (v == null) { on = false; return; }
    d += `${on ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)} `;
    on = true;
  });
  const lv = vals[n - 1];
  return { d: d.trim(), last: lv == null ? null : [Number(x(n - 1).toFixed(1)), Number(y(lv).toFixed(1))] };
}

/** A value's x on a clamped scale from x0 to x1. */
export function scaleX(v: number, lo: number, hi: number, x0: number, x1: number): number {
  const span = hi - lo || 1;
  return x0 + ((Math.min(hi, Math.max(lo, v)) - lo) / span) * (x1 - x0);
}

/** Round ticks covering [lo, hi]: steps of 1, 2, 2.5 or 5 times a power of ten, about `count` of them. */
export function niceTicks(lo: number, hi: number, count = 6): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / Math.max(1, count - 1);
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? 10 * pow;
  const out: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + step * 1e-9; t += step) out.push(Number(t.toFixed(6)));
  return out;
}

/** The four spread bands of a group as widths that add up to 100 (the API's shares may not, after rounding). */
export function stackWidths(pct: [number, number, number, number]): [number, number, number, number] {
  const clean = pct.map((v) => (Number.isFinite(v) && v > 0 ? v : 0));
  const sum = clean.reduce((a, b) => a + b, 0);
  if (!sum) return [0, 0, 0, 0];
  return clean.map((v) => (v / sum) * 100) as [number, number, number, number];
}

// ---------- groups, in words ----------

const GROUP_NOUN: Record<GroupBy, [string, string]> = { index: ["index", "indices"], sector: ["sector", "sectors"], industry: ["industry", "industries"] };
export const groupNoun = (by: GroupBy, plural = false) => GROUP_NOUN[by][plural ? 1 : 0];

/** "Nifty Midcap 150 leads the season: its median profit growth is +19.4%, the Nifty 50's +12.1%." */
export function groupsLead(rows: GroupRow[], by: GroupBy): Seg[] {
  const ranked = rows.filter((r) => r.pat_median != null).sort((a, b) => b.pat_median! - a.pat_median!);
  if (!ranked.length) return [{ t: `No ${groupNoun(by)} has a median yet: no company with a per cent change.` }];
  const top = ranked[0];
  const out: Seg[] = [{ t: `${top.label} leads the season: its median profit growth is ` }, { t: fmtPct(top.pat_median), tone: toneOf(top.pat_median) }];
  const ref = by === "index" ? ranked.find((r) => r.id === "NIFTY50" && r !== top) : undefined;
  const low = ref ?? (ranked.length > 1 ? ranked[ranked.length - 1] : undefined);
  if (low) out.push({ t: ref ? `, the ${low.label}'s ${fmtPct(low.pat_median)}.` : `; the lowest, ${low.label}, ${fmtPct(low.pat_median)}.` });
  else out.push({ t: "." });
  return out;
}

/** The lines under the groups' headline, each from the rows' own numbers. */
export function groupsBullets(rows: GroupRow[], by: GroupBy): string[] {
  const out: string[] = [];
  const share = rows.filter((r) => r.financials_share_pct != null && r.pat_total_financials != null && r.pat_total_ex_financials != null)
    .sort((a, b) => b.financials_share_pct! - a.financials_share_pct!)[0];
  if (share && share.pat_total_financials! < share.pat_total_ex_financials!) {
    out.push(`Banks and other financials hold the ${share.label} back: they make ${Math.round(share.financials_share_pct!)}% of its profit and grew ${fmtPct(share.pat_total_financials)} in total, the rest ${fmtPct(share.pat_total_ex_financials)}.`);
  } else if (share) {
    out.push(`Financials make ${Math.round(share.financials_share_pct!)}% of the ${share.label}'s profit and grew ${fmtPct(share.pat_total_financials)} in total, the rest ${fmtPct(share.pat_total_ex_financials)}.`);
  }
  const trended = wellCovered(rows.filter((r) => r.trend_pat_median.some((v) => v != null)));
  if (trended.length) {
    out.push(`${bestInEight(trended)} of ${trended.length} ${groupNoun(by, trended.length !== 1)}${by === "index" ? ` (with at least ${COVERAGE_MIN * 100}% of members reported)` : ""} show their best median in 8 quarters.`);
  }
  // ex-financials only: a bank's "revenue" is interest earned, not sales (C5)
  const both = rows.filter((r) => r.pat_total_ex_financials != null && r.revenue_total_ex_financials != null);
  if (both.length) {
    const faster = both.filter((r) => r.pat_total_ex_financials! > r.revenue_total_ex_financials!).length;
    out.push(faster === both.length ? `In every ${groupNoun(by)}, total profit grew faster than total revenue (companies other than financials).`
      : `Total profit grew faster than total revenue in ${faster} of ${both.length} ${groupNoun(by, true)} (companies other than financials).`);
  }
  return out;
}

// ---------- the URL's filters ----------

const stepOf = (v: string | null, allowed: readonly number[]): number | null => {
  if (v == null || v === "") return null;
  const n = Number(v);
  return allowed.includes(n) ? n : null;
};

/** The API's query as the page reads it from its URL. */
export type PageQuery = KpiQuery;

/** The page's URL as the API's query: anything not on the lists is dropped (the Worker checks again). */
export function readQuery(p: URLSearchParams): PageQuery {
  const view = viewOf(p);
  const sort = (SORTS as readonly string[]).includes(p.get("sort") ?? "") ? (p.get("sort") as Sort) : VIEW_SORT[view];   // no column picked: the view's own
  const dirRaw = p.get("dir");
  const momentum = p.get("momentum");
  const spread = p.get("spread");
  const quarter = p.get("quarter");
  const index = p.get("index");
  return {
    quarter: quarter && /^Q[1-4]FY\d{2}$/.test(quarter) ? quarter : null,
    index: index && INDICES.some((x) => x.id === index) ? index : null,
    mcap_min: stepOf(p.get("mcap_min"), MARKET_CAP_STEPS),
    class: (p.get("class") ?? "").trim().slice(0, 200) || null,
    q: (p.get("q") ?? "").trim().slice(0, 60),
    rev_min: stepOf(p.get("rev_min"), GROWTH_STEPS),
    ebitda_min: stepOf(p.get("ebitda_min"), GROWTH_STEPS),
    pat_min: stepOf(p.get("pat_min"), GROWTH_STEPS),
    opm_min: stepOf(p.get("opm_min"), MARGIN_STEPS),
    momentum: momentum === "speeding_up" || momentum === "slowing" ? momentum : null,
    turnaround: p.get("turnaround") === "1",
    nfo: p.get("nfo") === "1",
    spread: (SPREAD_KEYS as readonly string[]).includes(spread ?? "") ? (spread as SpreadKey) : null,
    sort,
    dir: dirRaw === "asc" || dirRaw === "desc" ? dirRaw : firstDir(sort),
    page: 1,
  };
}

/** The query as request parameters: empty filters left out, flags as "1". */
export function toApiParams(q: KpiQuery, page = q.page): Record<string, string | number | null> {
  return {
    quarter: q.quarter, index: q.index, mcap_min: q.mcap_min, class: q.class, q: q.q || null,
    rev_min: q.rev_min, ebitda_min: q.ebitda_min, pat_min: q.pat_min, opm_min: q.opm_min, momentum: q.momentum,
    turnaround: q.turnaround ? "1" : null, nfo: q.nfo ? "1" : null, spread: q.spread,
    sort: q.sort, dir: q.dir, page,
  };
}

/** The "Growth & signals" part of a query, which the popover edits as a draft and applies at once. */
export type GrowthDraft = Pick<KpiQuery, "pat_min" | "rev_min" | "ebitda_min" | "opm_min" | "momentum" | "turnaround" | "nfo">;
export const growthOf = (q: KpiQuery): GrowthDraft =>
  ({ pat_min: q.pat_min, rev_min: q.rev_min, ebitda_min: q.ebitda_min, opm_min: q.opm_min, momentum: q.momentum, turnaround: q.turnaround, nfo: q.nfo });
export const growthCount = (g: GrowthDraft) =>
  [g.pat_min, g.rev_min, g.ebitda_min, g.opm_min, g.momentum].filter((v) => v != null).length + (g.turnaround ? 1 : 0) + (g.nfo ? 1 : 0);
/** A growth draft as URL changes (null clears the parameter). */
export const growthParams = (g: GrowthDraft): Record<string, string | null> => ({
  pat_min: g.pat_min == null ? null : String(g.pat_min), rev_min: g.rev_min == null ? null : String(g.rev_min),
  ebitda_min: g.ebitda_min == null ? null : String(g.ebitda_min), opm_min: g.opm_min == null ? null : String(g.opm_min),
  momentum: g.momentum, turnaround: g.turnaround ? "1" : null, nfo: g.nfo ? "1" : null,
});

export const mcapText = (v: number) => (v >= 100000 ? `₹${v / 100000} lakh Cr` : `₹${v.toLocaleString("en-IN")} Cr`);
/** The narrowest step of a classification path: "Healthcare > Pharmaceuticals" -> "Pharmaceuticals". */
export const classLeaf = (path: string) => path.split(/\s*>\s*/).filter(Boolean).pop() ?? path;

/** The active filters as removable chips: each names the URL parameters its × clears. */
export function activeChips(q: KpiQuery): { id: string; label: string; clear: string[] }[] {
  const out: { id: string; label: string; clear: string[] }[] = [];
  if (q.q) out.push({ id: "q", label: `“${q.q}”`, clear: ["q"] });
  if (q.index) out.push({ id: "index", label: indexLabel(q.index), clear: ["index"] });
  if (q.mcap_min != null) out.push({ id: "mcap_min", label: `Market cap at least ${mcapText(q.mcap_min)}`, clear: ["mcap_min"] });
  if (q.class) out.push({ id: "class", label: classLeaf(q.class), clear: ["class"] });
  if (q.pat_min != null) out.push({ id: "pat_min", label: `Profit growth at least ${q.pat_min}%`, clear: ["pat_min"] });
  if (q.rev_min != null) out.push({ id: "rev_min", label: `Revenue growth at least ${q.rev_min}%`, clear: ["rev_min"] });
  if (q.ebitda_min != null) out.push({ id: "ebitda_min", label: `EBITDA growth at least ${q.ebitda_min}%`, clear: ["ebitda_min"] });
  if (q.opm_min != null) out.push({ id: "opm_min", label: `Margin up at least ${q.opm_min} bp`, clear: ["opm_min"] });
  if (q.momentum) out.push({ id: "momentum", label: MOMENTUM_TEXT[q.momentum], clear: ["momentum"] });
  if (q.turnaround) out.push({ id: "turnaround", label: "Turned loss to profit", clear: ["turnaround"] });
  if (q.nfo) out.push({ id: "nfo", label: "Profit up, EBITDA down", clear: ["nfo"] });
  if (q.spread) out.push({ id: "spread", label: `Profit growth ${SPREAD_LABEL[q.spread].toLowerCase()}`, clear: ["spread"] });
  return out;
}

// ---------- CSV ----------

/** A growth per cent in the CSV: "NM" past +999% (the same rule as the page). */
const nmCell = (v: number | null) => (isNmPct(v) ? NM : v);
const CSV_COLUMNS: [string, (r: KpiRow) => string | number | null | boolean][] = [
  ["Symbol", (r) => r.symbol ?? r.scrip_code], ["Company", (r) => r.company_name], ["Classification", (r) => r.industry],
  ["Kind (company/bank/nbfc/insurer/reit/invit)", (r) => r.kind], ["Basis", (r) => r.basis.toLowerCase()], ["Quarter", (r) => r.period], ["Market cap (Rs Cr)", (r) => r.market_cap_cr],
  ["Revenue (Rs Cr)", (r) => r.revenue], ["Revenue YoY %", (r) => nmCell(r.revenue_yoy)], ["Revenue QoQ %", (r) => nmCell(r.revenue_qoq)],
  ["EBITDA (Rs Cr)", (r) => r.ebitda], ["EBITDA YoY %", (r) => nmCell(r.ebitda_yoy)], ["EBITDA turn", (r) => (r.ebitda_turn ? TURN_TEXT[r.ebitda_turn] : null)],
  ["EBITDA QoQ %", (r) => nmCell(r.ebitda_qoq)], ["EBITDA margin %", (r) => (isNmMargin(r.opm) ? NM : r.opm)], ["Margin change YoY (bp; 100 bp = 1 percentage point)", (r) => r.opm_yoy_bps],
  ["PAT (Rs Cr)", (r) => r.pat], ["PAT YoY %", (r) => nmCell(r.pat_yoy)], ["PAT turn", (r) => (r.pat_turn ? TURN_TEXT[r.pat_turn] : null)],
  ["PAT QoQ %", (r) => nmCell(r.pat_qoq)], ["PAT YoY last quarter %", (r) => r.pat_prev_yoy], ["PAT growth change vs last quarter (pts)", (r) => r.pat_momentum_pts],
  ["Momentum", (r) => MOMENTUM_TEXT[r.momentum]], ["Profit up, EBITDA down", (r) => r.nfo], ["Filed", (r) => r.filed_at], ["Filing", (r) => r.filing_url],
];

function csvCell(v: string | number | null | boolean): string {
  if (v == null) return "";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isFinite(v) ? String(v) : "";
  // a text cell starting with = + - @ would run as a formula in a spreadsheet: a leading quote keeps it text
  const safe = /^[=+\-@\t\r]/.test(v) ? `'${v}` : v;
  return /[",\r\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

/** The rows as a CSV file's text (header first, CRLF lines, a byte-order mark so spreadsheets read the ₹-free UTF-8 right). */
export function toCsv(rows: KpiRow[]): string {
  const lines = [CSV_COLUMNS.map(([h]) => csvCell(h)).join(",")];
  for (const r of rows) lines.push(CSV_COLUMNS.map(([, f]) => csvCell(f(r))).join(","));
  return `﻿${lines.join("\r\n")}\r\n`;
}

export const csvName = (quarter: string | null) => `results-${quarter ?? "latest"}.csv`;
