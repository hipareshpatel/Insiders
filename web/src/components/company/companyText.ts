/** The company page's derived figures and short texts: what memory and the cards hold, cleaned and condensed for
 * the Overview (design audit 2026-10-20, fixes 4-9). No React and no imports beyond types, so `node --test` runs the
 * cases in test/company.test.ts. Every figure here comes from the data passed in; nothing is estimated. */
import type { CallQuarter, CardBody, DealRecord, Dossier, Guidance, PriceReaction, ResultsSnapshot, WatchItem } from "../../../shared/types";

type Series = { d: string[]; c: number[] };
type Metric = Dossier["financial_metrics"][number];

// ---------- machine text ----------

const UNIT_WORDS: Record<string, string> = {
  INR_CR: "₹ Cr", INR_PER_SHARE: "₹ a share", INR_LAKH: "₹ lakh", INR: "₹", PCT: "%", BPS: "bps", UNITS: "", USD_MN: "$ mn",
};

/** Text written by the pipeline with its own ids and unit codes taken out ("guidance g_662b6e23", "INR_PER_SHARE"). */
export function cleanText(text: string): string {
  return text
    .replace(/\*\*/g, "")
    .replace(/\s*\((?:guidance|watch|deal|id)?\s*[gwdtp]_[0-9a-f]{6,12}\)/gi, "")
    .replace(/\b(?:guidance|watch item|deal)\s+[gwdtp]_[0-9a-f]{6,12}\b/gi, "")
    .replace(/\b[gwdtp]_[0-9a-f]{6,12}\b/g, "")
    .replace(/\s*\(flagged \d{4}-\d{2}-\d{2}\)/g, "")
    .replace(/(\d[\d,]*(?:\.\d+)?)\s*INR_PER_SHARE\b/g, "₹$1 a share")
    .replace(/(\d[\d,]*(?:\.\d+)?)\s*INR_CR\b/g, "₹$1 Cr")
    .replace(/\b[A-Z]{2,}(?:_[A-Z]+)+\b|\b(?:PCT|BPS|UNITS)\b/g, (code) => UNIT_WORDS[code] ?? code.replace(/_/g, " ").toLowerCase())
    .replace(/\s+([,.;:)])/g, "$1")
    .replace(/\(\s*\)/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/** A move no business makes in a quarter: the pipeline read a unit or a base wrong (Heritage's "GNPA down 72767 bps",
 *  "VAP revenue up 1323%"). Such an item is dropped, not shown with a warning. */
export function impossible(text: string): boolean {
  for (const m of text.matchAll(/([+\-−]?\d[\d,]*(?:\.\d+)?)\s*(bps|bp|%)/gi)) {
    const v = Math.abs(Number(m[1].replace(/[,−+]/g, "")));
    if (/^bp/i.test(m[2]) ? v > 5000 : v > 1000) return true;
  }
  return false;
}

/** The first sentence, cut at a word near `max` characters. */
export function short(text: string, max = 110): string {
  // a full stop before a capital ends the sentence, except after a title or an abbreviation ("Mr. Rao", "No. 4")
  const end = [...text.matchAll(/([A-Za-z0-9%)\]]+)\.\s+(?=[A-Z])/g)].find((m) => !/^(?:Mr|Mrs|Ms|Dr|No|Nos|Rs|Ltd|Pvt|Co|Inc|vs|St|Sr|Jr|Prof)$/.test(m[1]));
  const first = (end ? text.slice(0, end.index! + end[0].indexOf(".")) : text).replace(/\.$/, "");
  if (first.length <= max) return first;
  const cut = first.slice(0, max);
  return `${cut.slice(0, Math.max(cut.lastIndexOf(" "), max - 20)).replace(/[,;:\s]+$/, "")}…`;
}

const ACRONYM = new Set(["vap", "dso", "roce", "roiic", "aum", "ape", "vnb", "usd", "ebitda", "ebit", "pat", "pbt", "gnpa", "nnpa", "casa", "nim", "roa", "roe", "crar", "pcr", "eps",
  "plf", "nii", "cet1", "aum", "arpu", "gst", "capex", "kpi"]);
const DROP_UNIT = new Set(["pct", "cr", "mlpd", "llpd", "inr", "mn", "lakh"]);

/** "vap_share_pct" -> "VAP share", "ebitda_margin" -> "EBITDA margin". */
export function metricLabel(metric: string): string {
  const words = metric.toLowerCase().replace(/_pct_(?=revenue|sales|income)/, "_to_").split(/[_\s]+/).filter((w) => w && !DROP_UNIT.has(w));
  const text = words.map((w) => (ACRONYM.has(w) ? w.toUpperCase() : w)).join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// ---------- the financial baseline in statement order ----------

/** The order a results statement prints its lines in (owner, 2026-10-21: the company page's financials "not in the
 * right order"): income, costs, profit down to EPS, then the bank and insurer lines, operating figures, cash and the
 * balance sheet. A line not listed goes after the others of its section, in the order memory holds it. */
const STATEMENT: [string, string[]][] = [
  ["Profit and loss", ["interest_earned", "interest_expended", "net_interest_income", "gross_premium", "net_premium",
    "first_year_premium", "renewal_premium", "single_premium", "new_business_premium", "revenue", "other_income",
    "total_income", "raw_material_cost", "purchases_stock_in_trade", "inventory_change", "employee_cost", "commission",
    "benefits_paid", "other_expenses", "operating_expenses", "total_expenses", "ebitda", "ebitda_margin",
    "operating_profit", "ebit_margin", "provisions", "depreciation", "finance_cost", "exceptional_items",
    "share_associates", "pbt", "current_tax", "deferred_tax", "tax_expense", "pat_continuing", "pat", "pat_owners",
    "surplus", "eps"]],
  ["Ratios and operating figures", ["nim", "gnpa", "gnpa_ratio", "nnpa", "nnpa_ratio", "pcr", "casa_ratio", "crar",
    "roa", "roe", "cost_to_income", "advances", "deposits", "ape", "individual_ape", "vnb", "vnb_margin", "expense_ratio",
    "solvency_ratio", "embedded_value", "operating_roev", "persistency_13m", "persistency_61m", "aum", "volumes",
    "ebitda_per_ton", "order_book", "deal_wins_usd_mn", "attrition", "dso", "roce"]],
  ["Cash and balance sheet", ["operating_cash_flow", "free_cash_flow", "cash_and_equivalents", "gross_debt", "net_debt",
    "net_worth", "trade_receivables", "paid_up_capital"]],
];
const SECTION_OF = new Map(STATEMENT.flatMap(([section, lines], s) => lines.map((m, i) => [m, { section, s, i }] as const)));

/** Each metric's section and place in it; an unknown line counts as an operating figure, after the listed ones. */
export function statementPlace(metric: string): { section: string; s: number; i: number } {
  return SECTION_OF.get(metric) ?? { section: STATEMENT[1][0], s: 1, i: 999 };
}

/** A stored figure with its unit in words ("13.17 INR" read as "₹13.17", "1,078 USD_MN" as "$1,078 mn", "84 DAYS"). */
export function unitValue(text: string, unit: string): string {
  if (unit === "INR" || unit === "INR_PER_SHARE") return `₹${text}`;
  if (unit === "USD_MN") return `$${text} mn`;
  if (unit === "PCT") return `${text}%`;
  if (!unit || unit === "UNITS") return text;
  return `${text} ${UNIT_WORDS[unit] ?? unit.replace(/_/g, " ").toLowerCase()}`;
}

/** A line whose every stored figure is zero is the XBRL's filler (an IT company's raw-material cost), not a fact. */
export const allZero = (values: Iterable<{ value: number }>) => [...values].every((v) => v.value === 0);

/** The metrics in statement order (a stable sort: unknown lines keep memory's order). */
export function inStatementOrder<T>(rows: [string, T][]): [string, T][] {
  return rows.map((r, k) => ({ r, k, p: statementPlace(r[0]) }))
    .sort((a, b) => a.p.s - b.p.s || a.p.i - b.p.i || a.k - b.k).map((x) => x.r);
}

const noPeriod = (v: string) => v.replace(/\s*\([^()]*FY\d{2}[^()]*\)|\s*\([A-Z][a-z]{2}-\d{4}\)/g, "").trim();

// ---------- the good & the bad ----------

export type GoodBadItem = { text: string; source: string };
type GoodBadInput = { source: string; card: Pick<CardBody, "signals" | "notable_changes"> };

/** Positive and negative points from the newest cards first: notable changes as "X up to a from b", then the computed
 *  signals' first sentence. Ids and unit codes are cleaned, impossible values dropped, each metric said once. */
export function goodAndBad(entries: GoodBadInput[]): { good: GoodBadItem[]; bad: GoodBadItem[] } {
  const good: GoodBadItem[] = [], bad: GoodBadItem[] = [];
  const seen = new Set<string>();
  const push = (list: GoodBadItem[], key: string, raw: string, source: string) => {
    const text = short(cleanText(raw));
    const k = key.toLowerCase();
    if (!text || impossible(raw) || impossible(text) || seen.has(k) || seen.has(text.slice(0, 40).toLowerCase())) return;
    seen.add(k);
    seen.add(text.slice(0, 40).toLowerCase());
    list.push({ text, source });
  };
  for (const { source, card } of entries) {
    for (const c of card.notable_changes ?? []) {
      if (c.direction === "NEUTRAL" || !c.current || impossible(c.change ?? "")) continue;
      const label = metricLabel(c.metric);
      const ch = (c.change ?? "").trim();
      const way = /^[−-]/.test(ch) ? "down" : /^\+/.test(ch) ? "up" : null;
      const text = c.previous && way
        ? `${label} ${way} to ${noPeriod(c.current)} from ${noPeriod(c.previous)}`
        : `${label} at ${noPeriod(c.current)}${ch ? ` (${ch})` : ""}`;
      push(c.direction === "POSITIVE" ? good : bad, `m:${label}`, text, source);
    }
    for (const s of card.signals ?? []) {
      if (s.severity === "INFO") continue;
      push(s.severity === "POSITIVE" ? good : bad, `s:${s.type}`, s.text, source);
    }
  }
  return { good, bad };
}

// ---------- periods ----------

/** "Q2FY27" -> a running quarter number (FY*4 + Q); a year "FY26" counts as its Q4. Null when not a quarter or year. */
export function quarterIndex(label: string | null | undefined): number | null {
  const s = (label ?? "").toUpperCase();
  let m = s.match(/Q([1-4])\s*FY'?(\d{2})\b/);
  if (m) return Number(m[2]) * 4 + Number(m[1]);
  m = s.match(/\bFY'?(\d{2})\b/);
  return m ? Number(m[1]) * 4 + 4 : null;
}
export const quarterLabel = (i: number) => `Q${((i - 1) % 4) + 1}FY${String(Math.floor((i - 1) / 4)).padStart(2, "0")}`;

/** Quarterly values of one metric by quarter number ("pat_owners" before "pat" when both exist). */
export function quarterly(metrics: Metric[], names: string[]): Map<number, number> {
  const out = new Map<number, number>();
  for (const name of [...names].reverse()) {
    for (const m of metrics) {
      if (m.metric !== name || !/^Q[1-4]FY\d{2}$/.test(m.period)) continue;
      out.set(quarterIndex(m.period)!, m.value);
    }
  }
  return out;
}

const latestOf = (q: Map<number, number>) => (q.size ? Math.max(...q.keys()) : null);

/** The latest quarter memory holds results for. */
export function latestQuarter(metrics: Metric[]): number | null {
  return latestOf(quarterly(metrics, ["revenue", "pat"]));
}

// ---------- key figures ----------

/** P/E on the last four quarters' profit; only when the four are consecutive, the latest is less than nine months
 *  old and their sum is a profit. */
export function peTtm(metrics: Metric[], marketCapCr: number | null | undefined, today: string): { pe: number; through: string } | null {
  if (!marketCapCr) return null;
  const pat = quarterly(metrics, ["pat_owners", "pat"]);
  const last = latestOf(pat);
  if (last == null) return null;
  const four = [0, 1, 2, 3].map((k) => pat.get(last - k));
  if (four.some((v) => v == null)) return null;
  const sum = four.reduce<number>((a, v) => a + (v ?? 0), 0);
  const fy = Math.floor((last - 1) / 4), q = ((last - 1) % 4) + 1;
  const end = new Date(Date.UTC(2000 + fy - (q === 4 ? 0 : 1), [5, 8, 11, 2][q - 1] + 1, 0));
  if ((Date.parse(today) - end.getTime()) / 86400_000 > 270 || sum <= 0) return null;
  return { pe: marketCapCr / sum, through: quarterLabel(last) };
}

/** Low and high of the last 250 sessions; null below 200 sessions (not a year of data). */
export function yearRange(chart: Series | null | undefined): { lo: number; hi: number } | null {
  if (!chart || chart.c.length < 200) return null;
  const year = chart.c.slice(-250);
  return { lo: Math.min(...year), hi: Math.max(...year) };
}

/** Price-structure tags the series itself shows: at or near its 52-week high or low, against the 200-day average. */
export function chartTags(chart: Series | null | undefined): { text: string; tone: "pos" | "neg" | "neutral" }[] {
  const range = yearRange(chart);
  if (!chart || !range) return [];
  const last = chart.c[chart.c.length - 1];
  const out: { text: string; tone: "pos" | "neg" | "neutral" }[] = [];
  if (last >= range.hi * 0.98) out.push({ text: last >= range.hi ? "52-week high" : "Near 52-week high", tone: "pos" });
  else if (last <= range.lo * 1.02) out.push({ text: last <= range.lo ? "52-week low" : "Near 52-week low", tone: "neg" });
  const dma = chart.c.slice(-200).reduce((a, v) => a + v, 0) / 200;
  out.push({ text: last >= dma ? "Above 200 DMA" : "Below 200 DMA", tone: "neutral" });
  return out;
}

/** The latest session's change: the series' last two closes, or the quoted price against the series' last close when
 *  the quote is from the next trading day (only weekend days between). Null otherwise. */
export function dayChange(chart: Series | null | undefined, price: number | null | undefined, priceDate: string | null | undefined):
  { change: number; pct: number; date: string } | null {
  if (!chart || chart.c.length < 2) return null;
  const n = chart.c.length, lastDay = chart.d[n - 1];
  const day = priceDate?.slice(0, 10);
  let now: number, before: number, date: string;
  if (price != null && day && day > lastDay) {
    for (let t = Date.parse(`${lastDay}T00:00:00Z`) + 86400_000; t < Date.parse(`${day}T00:00:00Z`); t += 86400_000) {
      if (![0, 6].includes(new Date(t).getUTCDay())) return null;
    }
    [now, before, date] = [price, chart.c[n - 1], day];
  } else if (!day || day === lastDay) {
    [now, before, date] = [chart.c[n - 1], chart.c[n - 2], lastDay];
  } else return null;
  if (!(before > 0)) return null;
  return { change: now - before, pct: (now / before - 1) * 100, date };
}

/** When the next quarter's results should come: a year after the same quarter's results were filed last year. */
export function nextResults(results: { period: string; filed_at: string }[], today: string): { period: string; date: string } | null {
  const quarters = results.filter((r) => /^Q[1-4]FY\d{2}$/.test(r.period));
  if (!quarters.length) return null;
  const next = Math.max(...quarters.map((r) => quarterIndex(r.period)!)) + 1;
  const ago = quarters.filter((r) => quarterIndex(r.period) === next - 4).map((r) => r.filed_at.slice(0, 10)).sort()[0];
  if (!ago) return null;
  const d = new Date(`${ago}T00:00:00Z`);
  d.setUTCFullYear(d.getUTCFullYear() + 1);
  const date = d.toISOString().slice(0, 10);
  return date >= today ? { period: quarterLabel(next), date } : null;
}

/** The T+1 and T+5 moves the post-mortem stored for a card. */
export function reaction(json: string | null | undefined): { t1?: number; t5?: number } {
  if (!json) return {};
  try {
    const r = JSON.parse(json) as PriceReaction;
    return { t1: r.t1?.return_pct, t5: r.t5?.return_pct };
  } catch { return {}; }
}

// ---------- the story so far ----------

const DEAL_WORD: Record<string, string> = { ORDER: "order", ACQUISITION: "acquisition", CAPEX: "capex plan", DIVESTMENT: "sale", FUNDRAISE: "fundraise" };
const STAGE_WORD: Record<string, string> = {
  COMPLETED: "completed", IN_PROGRESS: "in progress", BOARD_APPROVED: "approved by the board", PROPOSED: "proposed",
  LOI: "at letter-of-intent stage", MOU: "at MoU stage", RECEIVED: "received", EXECUTING: "being executed", CANCELLED: "cancelled",
};
const month = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00Z`).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });
const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(Math.abs(v) < 10 ? 1 : 0)}%`;

/** Two or three sentences from memory: the results streak, the latest deal, the promise record. Figures are wrapped in
 *  ** for highlighting; a sentence whose figures are missing is left out. Null when memory has none of the three. */
export function composeStory(input: { metrics: Metric[]; deals: DealRecord[]; guidance: Guidance[]; money: (cr: number) => string;
  latest?: ResultsSnapshot | null }): string | null {
  const { metrics, deals, guidance, money, latest } = input;
  const out: string[] = [];
  const rev = quarterly(metrics, ["revenue"]);
  const pat = quarterly(metrics, ["pat_owners", "pat"]);
  const last = latestOf(rev);
  if (last != null && rev.get(last - 4)) {
    const yoy = (q: Map<number, number>, i: number) => { const a = q.get(i), b = q.get(i - 4); return a != null && b != null && b > 0 ? (a / b - 1) * 100 : null; };
    let streak = 0;
    for (let i = last; yoy(rev, i) != null && yoy(rev, i)! > 0; i--) streak++;
    // the latest results card's own figures when it is this quarter's (the filing's basis), else memory's
    const card = latest && quarterIndex(latest.period) === last && /^Q/.test(latest.period) ? latest : null;
    const revNow = card?.revenue?.value ?? rev.get(last)!;
    const r = card?.revenue?.yoy_pct ?? yoy(rev, last)!;
    if (r <= 0) streak = 0;
    let s = streak >= 2
      ? `Revenue has grown year on year for **${streak} quarters in a row**, to **${money(revNow)}** in ${quarterLabel(last)} (**${signed(r)}**)`
      : `Revenue was **${money(revNow)}** in ${quarterLabel(last)} (**${signed(r)}** year on year)`;
    const p = card?.pat?.value ?? pat.get(last), pb = card?.pat?.prev_year ?? pat.get(last - 4);
    const pc = card?.pat?.yoy_pct ?? (p != null && pb != null && pb > 0 ? (p / pb - 1) * 100 : null);
    if (p != null && pb != null) {
      s += p > 0 && pb > 0 && pc != null
        ? `; profit ${pc >= 0 ? "rose" : "fell"} **${Math.abs(pc).toFixed(0)}%** to **${money(p)}**`
        : `; profit was **${money(p)}** against ${money(pb)} a year earlier`;
    }
    out.push(`${s}.`);
  }
  const deal = deals.filter((d) => DEAL_WORD[d.kind] && d.amount_cr != null && d.amount_cr > 0)
    .sort((a, b) => (b.updated_as_of ?? b.as_of).localeCompare(a.updated_as_of ?? a.as_of))[0];
  if (deal) {
    const where = deal.segment && deal.segment.length <= 40 ? ` (${cleanText(deal.segment)})` : "";
    const stage = STAGE_WORD[deal.stage] ?? deal.stage.replace(/_/g, " ").toLowerCase();
    out.push(`The latest on the deal book: a **${money(deal.amount_cr!)}** ${DEAL_WORD[deal.kind]}${where}, ${stage} as of ${month(deal.updated_as_of ?? deal.as_of)}.`);
  }
  const delivered = guidance.filter((g) => g.status === "DELIVERED").length;
  const resolved = delivered + guidance.filter((g) => ["MISSED", "DELAYED", "WITHDRAWN"].includes(g.status)).length;
  const open = guidance.filter((g) => ["OPEN", "ON_TRACK", "REVISED"].includes(g.status)).length;
  if (resolved) out.push(`Management has delivered **${delivered} of ${resolved}** commitments that came due${open ? `, with ${open} still open` : ""}.`);
  return out.length ? out.join(" ") : null;
}

// ---------- what to track ----------

export type TrackTile = { label: string; text: string; sub: string } | { label: string; text: null; sub: null };

/** Four tiles, the newest current item of each kind. A KPI whose check-in quarter has already reported, a promise past
 *  its due date and an item without a date are not current, so they are not shown here (the tracker lists them). */
export function trackTiles(input: {
  watchlist: WatchItem[]; guidance: Guidance[]; latestQuarter: number | null; today: string;
  risks: { text: string; source: string }[]; date: (iso: string) => string;
}): TrackTile[] {
  const { watchlist, guidance, latestQuarter: lq, today, risks, date } = input;
  const open = (w: WatchItem) => ["OPEN", "PENDING", "PARTIAL"].includes(w.status);
  const newest = <T,>(xs: T[], at: (x: T) => string) => [...xs].sort((a, b) => at(b).localeCompare(at(a)))[0];
  const kpi = newest(watchlist.filter((w) => w.kind === "KPI" && open(w) && !!w.check_in
    && (lq == null || (quarterIndex(w.check_in) ?? Infinity) > lq) && !(w.check_by && w.check_by < today)), (w) => w.created_on);
  const promise = newest(guidance.filter((g) => ["OPEN", "ON_TRACK", "REVISED"].includes(g.status) && !!g.given_on
    && (!g.due_date || g.due_date >= today)), (g) => g.given_on);
  const approval = newest(watchlist.filter((w) => w.kind === "APPROVAL" && open(w) && !!w.created_on), (w) => w.created_on);
  const concern = newest(watchlist.filter((w) => w.kind === "CONCERN" && open(w) && !!w.created_on), (w) => w.created_on);
  const none = (label: string): TrackTile => ({ label, text: null, sub: null });
  const risk = risks.find((r) => r.text && !impossible(r.text));
  return [
    kpi ? { label: "KPI to verify", text: short(cleanText(`${kpi.text}${kpi.target ? ` (${kpi.target})` : ""}`)), sub: `at ${kpi.check_in} · flagged ${date(kpi.created_on)}` } : none("KPI to verify"),
    promise ? { label: "Guidance", text: short(cleanText(promise.statement)), sub: `${promise.due ? `due ${promise.due} · ` : ""}${promise.status === "ON_TRACK" ? "on track" : promise.status === "REVISED" ? "revised" : "open"} · ${date(promise.given_on)}` } : none("Guidance"),
    approval ? { label: "Pending approval", text: short(cleanText(approval.text)), sub: `since ${date(approval.created_on)}` } : none("Pending approval"),
    risk ? { label: "Road blocker", text: short(cleanText(risk.text)), sub: risk.source }
      : concern ? { label: "Road blocker", text: short(cleanText(concern.text)), sub: `analyst concern · ${date(concern.created_on)}` } : none("Road blocker"),
  ];
}

/** Commitments past their due date with no result on record, oldest due first. */
export function overdue(guidance: Guidance[], today: string): (Guidance & { days: number })[] {
  return guidance.filter((g) => !!g.due_date && g.due_date < today && ["OPEN", "ON_TRACK"].includes(g.status))
    .map((g) => ({ ...g, days: Math.round((Date.parse(today) - Date.parse(g.due_date!)) / 86400_000) }))
    .sort((a, b) => a.due_date!.localeCompare(b.due_date!));
}

/** The earnings-call quarters as the page shows them: texts cleaned of machine ids and unit codes, a point said twice
 *  under one heading once, empty headings and quarters left out. */
export function callQuarters(calls: CallQuarter[] | undefined): CallQuarter[] {
  return (calls ?? []).flatMap((q) => {
    const categories = q.categories.flatMap((c) => {
      const seen = new Set<string>();
      const points = c.points.flatMap((p) => {
        const text = cleanText(p.text);
        const key = text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
        if (!key || seen.has(key)) return [];
        seen.add(key);
        return [{ ...p, text }];
      });
      return points.length ? [{ ...c, points }] : [];
    });
    return categories.length ? [{ ...q, categories }] : [];
  });
}
