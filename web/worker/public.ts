// Read-only API for the frontend. Every query is index-backed and bounded:
// D1's free tier meters rows *read* (5M/day), so each query seeks a range
// (dates, the cursor) instead of walking a table, and hot responses are kept
// briefly in the isolate and, on a custom domain, in Cloudflare's edge cache.
import { dedupeEvents } from "../shared/events";
import { daysPastDue, isPastDue } from "../shared/promiseDue.ts";
import { isCompanyKey } from "../shared/companyKey";
import type { CallQuarter, PublicSystemResponse } from "../shared/types";
import { registerResultsRoutes } from "./results";
import { Hono } from "hono";
import type { Context } from "hono";
import type { AppEnv } from "./env";

const CARD_COLUMNS = `
  c.news_id, c.scrip_code, c.symbol, c.company_name, c.filing_date, c.filed_at, c.sector,
  c.event_category, c.impact_level, c.headline, c.grounding_score, c.needs_review,
  c.memory_complete, c.card_json, c.pdf_url, c.market_session, c.actionability_score, c.is_actionable_signal, c.post_event_return_json, c.held,
  co.market_cap_cr, co.size_category, co.last_price, co.ret_1w, co.ret_1m, co.ret_3m, co.ret_1y, co.industry,
  co.median_turnover_cr, co.credibility_score, co.watchlist, co.bse_group, co.technicals_json, co.former_names_json`;

const COMPANY_COLUMNS = `scrip_code, symbol, company_name, isin, industry, sector, market_cap_cr,
  size_category, last_price, price_date, ret_1w, ret_1m, ret_3m, ret_1y, card_count, last_card_at,
  watchlist, former_names_json, credibility_score, median_turnover_cr, bse_group, technicals_json,
  json_array_length(memory_summary_json, '$.open_promises') AS open_promises,
  json_extract(memory_summary_json, '$.active_capex') AS active_capex,
  json_extract(memory_summary_json, '$.revenue') AS latest_revenue,
  json_extract(memory_summary_json, '$.ebitda') AS latest_ebitda,
  json_extract(memory_summary_json, '$.gross_debt_cr') AS gross_debt_cr,
  json_extract(memory_summary_json, '$.calibration') AS calibration_rule,
  json_extract(memory_summary_json, '$.roiic') AS roiic`;

/** Turn free text into a safe FTS5 prefix query: "tata mot" -> "tata"* "mot"*. One-letter tokens
 * are dropped: a prefix that short matches nearly every row. */
export function ftsQuery(q: string | undefined): string | null {
  const tokens = ((q ?? "").toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []).filter((t) => t.length >= 2).slice(0, 6);
  return tokens.length ? tokens.map((t) => `"${t}"*`).join(" ") : null;
}

/** Positional parameters for SQL built from optional filters: p(value) returns its placeholder. */
function binder() {
  const params: unknown[] = [];
  const p = (value: unknown) => {
    params.push(value);
    return `?${params.length}`;
  };
  return { params, p };
}

// Responses kept in this isolate for a few seconds. An isolate serves many requests, so a
// popular page costs one D1 query per interval instead of one per view.
const memo = new Map<string, { until: number; body: unknown }>();
async function memoised<T>(key: string, ttlMs: number, load: () => Promise<T>): Promise<T> {
  const hit = memo.get(key);
  if (hit && hit.until > Date.now()) return hit.body as T;
  const body = await load();
  if (memo.size > 200) memo.clear();
  memo.set(key, { until: Date.now() + ttlMs, body });
  return body;
}

const edgeCache = (): Cache | undefined => {
  try {
    return (globalThis as unknown as { caches?: { default: Cache } }).caches?.default;
  } catch {
    return undefined;
  }
};

/** "HIGH,LOW" -> '["HIGH","LOW"]' restricted to allowed values, or null. */
function listParam(value: string | undefined, allowed?: Set<string>): string | null {
  const items = (value ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s && (!allowed || allowed.has(s)));
  return items.length ? JSON.stringify(items) : null;
}

const IMPACTS = new Set(["HIGH", "MODERATE", "LOW"]);
const SIZES = new Set(["LARGE", "MID", "SMALL", "MICRO"]);
const isDate = (s: string | undefined) => !!s && /^\d{4}-\d{2}-\d{2}$/.test(s);
export { isCompanyKey };   // shared/companyKey.ts: a scrip code, an NSE symbol or "NSE:<symbol>"
const clamp = (v: string | undefined, def: number, max: number) =>
  Math.min(Math.max(Number.parseInt(v ?? "", 10) || def, 1), max);

export const api = new Hono<AppEnv>();

// Worker responses are not cached by Cloudflare from their headers alone; the Cache API stores
// them per data centre. It works on a custom domain and does nothing on workers.dev.
api.use("*", async (c, next) => {
  const isPrivate = c.req.path.startsWith("/api/internal/") || c.req.path.startsWith("/api/owner/");
  const cache = c.req.method === "GET" && !isPrivate ? edgeCache() : undefined;
  const key = new Request(c.req.url);
  if (cache) {
    const hit = await cache.match(key).catch(() => undefined);
    if (hit) return hit;
  }
  await next();
  c.res.headers.set("X-Robots-Tag", "noindex");   // private launch: the API stays out of search engines too
  if (c.req.method !== "GET" || c.res.status !== 200 || isPrivate) return;
  if (!c.res.headers.has("Cache-Control")) c.res.headers.set("Cache-Control", "public, max-age=30, s-maxage=60");
  if (cache) {
    try {
      c.executionCtx.waitUntil(cache.put(key, c.res.clone()).catch(() => undefined));
    } catch {
      /* no execution context (tests) */
    }
  }
});

const SESSIONS = new Set(["LIVE_MARKET", "PRE_MARKET", "AFTER_MARKET", "NON_TRADING"]);
const PAGE_COUNT_CAP = 2000; // "40+ pages": an exact total would read every matching card
const MAX_OFFSET = 10_000;
export const SNAPSHOT_KEY = "daily_feed/latest_snapshot.json";

interface Snapshot {
  generated_at: string;
  from: string;
  limit: number;
  feed: { cards: unknown[]; total: number };
  signals: unknown[];
  signals_from?: string; // the window the signals were built for (the pipeline's 7 days); older snapshots held 3
}

/** The pipeline publishes the default first page and the top signals to R2 after every run, so the
 * homepage costs no D1 reads (blueprint §3.3). */
async function snapshot(c: Context<AppEnv>): Promise<Snapshot | null> {
  return memoised("snapshot", 30_000, async () => {
    const object = await c.env.VAULT.get(SNAPSHOT_KEY);
    return object ? ((await object.json()) as Snapshot) : null;
  });
}

// withHeld: the owner's private view (/api/owner/feed, behind OWNER_TOKEN and outside the edge cache) also
// lists the cards held back from the public feed, so the owner can review them (owner, 2026-10-19).
export async function feed(c: Context<AppEnv>, withHeld = false) {
  const q = c.req.query();
  // from_at: since a moment ("since yesterday's 15:30 close", the Today page); else from a day
  const from = q.from_at && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(q.from_at) ? q.from_at : isDate(q.from) ? q.from : "2000-01-01";
  const to = `${isDate(q.to) ? q.to : "2999-12-31"}T99`; // filed_at is "YYYY-MM-DDTHH:MM:SS+05:30"
  const limit = clamp(q.limit, 20, 50);
  // OFFSET reads every row it skips: at most MAX_OFFSET of them (400 pages of 50 allowed 19,950; the pager stops at
  // PAGE_COUNT_CAP, 2,000 cards) (survey, 24 Oct 2026)
  const page = q.page ? clamp(q.page, 1, Math.floor(MAX_OFFSET / limit) + 1) : null;
  const [cursorAt, cursorId] = (q.cursor ?? "").split("|");

  // The default first page comes from the R2 snapshot when it was built for the same window.
  const keys = Object.keys(q).filter((k) => q[k] !== "" && !["from", "to", "limit", "page"].includes(k));
  if (!withHeld && !keys.length && (page ?? 1) === 1 && !cursorAt) {
    const snap = await snapshot(c);
    if (snap && snap.from === q.from && snap.limit === limit && q.to === todayIst()) {
      return c.json({ cards: snap.feed.cards, page: 1, pages: Math.max(1, Math.ceil(snap.feed.total / limit)),
        total: snap.feed.total, total_capped: snap.feed.total >= PAGE_COUNT_CAP, next_cursor: null, source: "snapshot" });
    }
  }

  // The scan walks idx_cards_feed newest first between these two bounds; the cursor is folded into
  // the upper one so a deep page does not re-read everything above it.
  const upper = cursorAt && cursorAt < to ? cursorAt : to;
  const { params, p } = binder();
  // held = 0: a card whose numbers a second provider could not verify stays out of the feed rather
  // than appearing with an "Unverified" warning (migration 0009). It is still in the table, for the
  // review queue and the audit export.
  const where = [...(withHeld ? [] : [`c.held = 0`]), `c.filed_at >= ${p(from)}`, `c.filed_at <= ${p(upper)}`];
  const impact = listParam(q.impact, IMPACTS);
  const category = listParam(q.category);
  const size = listParam(q.size, SIZES);
  const sector = listParam(q.sector);
  const session = listParam(q.session, SESSIONS);
  const fts = ftsQuery(q.q);
  // Unary + keeps the planner on the date index (with a LIMIT, walking it is the cheap plan).
  if (impact) where.push(`+c.impact_level IN (SELECT value FROM json_each(${p(impact)}))`);
  if (category) where.push(`+c.event_category IN (SELECT value FROM json_each(${p(category)}))`);
  if (size) where.push(`co.size_category IN (SELECT value FROM json_each(${p(size)}))`);
  if (sector) where.push(`+c.sector IN (SELECT value FROM json_each(${p(sector)}))`);
  if (session) where.push(`+c.market_session IN (SELECT value FROM json_each(${p(session)}))`);
  if (q.watch === "1") where.push("co.watchlist = 1");
  if (q.turnaround === "1") {
    where.push(`json_extract(c.card_json, '$.results.pat.prev_year') < 0 AND json_extract(c.card_json, '$.results.pat.value') > 0`);
  }
  if (cursorAt) where.push(`(c.filed_at, c.news_id) < (${p(cursorAt)}, ${p(cursorId ?? "")})`);
  if (q.review === "0") where.push("c.needs_review = 0");
  if (withHeld && q.held === "only") where.push("c.held = 1");
  // A text filter starts from the 500 best matches instead of testing every card in the window.
  const source = fts
    ? `(SELECT rowid AS rid FROM cards_fts WHERE cards_fts MATCH ${p(fts)} ORDER BY rank LIMIT 500) f
       CROSS JOIN cards c ON c.rowid = f.rid`
    : "cards c";
  const body = `FROM ${source} LEFT JOIN companies co ON co.scrip_code = c.scrip_code WHERE ${where.join(" AND ")}`;
  const countParams = [...params];
  const sql = `SELECT ${CARD_COLUMNS} ${body} ORDER BY c.filed_at DESC, c.news_id DESC
     LIMIT ${p(limit + 1)}${page ? ` OFFSET ${p((page - 1) * limit)}` : ""}`;
  const run = async () => {
    if (!page) return { rows: (await c.env.DB.prepare(sql).bind(...params).all()).results, total: null as number | null };
    const [rows, counted] = await c.env.DB.batch([
      c.env.DB.prepare(sql).bind(...params),
      c.env.DB.prepare(`SELECT count(*) AS n FROM (SELECT 1 ${body} LIMIT ${PAGE_COUNT_CAP})`).bind(...countParams),
    ]);
    return { rows: rows.results, total: (counted.results[0] as { n: number } | undefined)?.n ?? 0 };
  };
  // The first page of an unfiltered view is what most visitors load.
  const result = !cursorAt && !fts && (page ?? 1) === 1 ? await memoised(`feed:${sql}:${page}:${JSON.stringify(params)}`, 20_000, run) : await run();
  const more = result.rows.length > limit;
  const cards = result.rows.slice(0, limit) as { filed_at: string; news_id: string }[];
  const last = cards[cards.length - 1];
  return c.json({
    cards,
    next_cursor: more && last ? `${last.filed_at}|${last.news_id}` : null,
    ...(page ? { page, pages: Math.max(1, Math.ceil((result.total ?? 0) / limit)), total: result.total,
      total_capped: (result.total ?? 0) >= PAGE_COUNT_CAP } : {}),
  });
}

api.get("/feed", (c) => feed(c));

// The Results page as a KPI report (worker/results.ts): /results-kpi, /results-classification, /results-groups, /results-company/:key.
registerResultsRoutes(api, memoised);

const todayIst = () => new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10);

// Top Signals: cards that cleared the 4 gates, best score first (walks idx_cards_feed_live over the range; migration 0011 dropped the unused idx_cards_signals).
api.get("/signals", async (c) => {
  const q = c.req.query();
  const fromAt = q.from_at && /^\d{4}-\d{2}-\d{2}T/.test(q.from_at) ? q.from_at : `${isDate(q.from) ? q.from : todayIst()}`;
  const toAt = q.to_at && /^\d{4}-\d{2}-\d{2}T/.test(q.to_at) ? q.to_at : `${isDate(q.to) ? q.to : "2999-12-31"}T99`;
  const snap = !q.from_at && !q.to && q.from ? await snapshot(c) : null;
  if (snap && snap.signals_from === q.from) return c.json({ cards: snap.signals, source: "snapshot" });
  const { results } = await c.env.DB.prepare(`
    SELECT ${CARD_COLUMNS}
      FROM cards c LEFT JOIN companies co ON co.scrip_code = c.scrip_code
     WHERE c.held = 0 AND c.is_actionable_signal = 1 AND c.filed_at >= ?1 AND c.filed_at <= ?2
     ORDER BY c.actionability_score DESC, c.filed_at DESC
     LIMIT 50`).bind(fromAt, toAt).all();
  return c.json({ cards: results });
});

// Pre-market brief: what came in since a moment (by default yesterday's 15:30 IST close).
const BRIEF_DAYS = 31;
api.get("/brief", async (c) => {
  const q = c.req.query();
  const asked = q.from_at ?? "";
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,3})?)?(Z|[+-]\d{2}:\d{2})?$/.test(asked) || Number.isNaN(Date.parse(asked))) {
    return c.json({ error: "from_at (YYYY-MM-DDTHH:MM[:SS][+05:30]) required" }, 400);
  }
  // No earlier than BRIEF_DAYS back (the pages ask for the close, today, 7 days and, on Top Signals, 30 days): an old
  // from_at counted the whole cards table, and each new value missed both caches (survey, 24 Oct 2026)
  const floor = `${istDay(-BRIEF_DAYS)}T00:00:00+05:30`;
  const fromAt = Date.parse(asked) < Date.parse(floor) ? floor : asked;
  // every IST day from the window's first to today: a 7-day window has 8 days of filings and noise counts
  const days: string[] = [];
  for (let d = fromAt.slice(0, 10), end = todayIst(), n = 0; d <= end && n < 40; n++) {
    days.push(d);
    d = new Date(Date.parse(`${d}T00:00:00Z`) + 86400_000).toISOString().slice(0, 10);
  }
  const body = await memoised(`brief:${fromAt}`, 60_000, async () => {
    const db = c.env.DB;
    const [cards, ledger, kv, bySector] = await db.batch([
      db.prepare(`SELECT impact_level, sum(is_actionable_signal * (held = 0)) AS signals, sum(held) AS held, sum(held = 0) AS n FROM cards
                   WHERE impact_level IN ('HIGH', 'MODERATE', 'LOW') AND filed_at >= ?1 GROUP BY impact_level`).bind(fromAt),
      db.prepare(`SELECT count(*) AS n FROM filings WHERE filing_date IN (SELECT value FROM json_each(?1)) AND filed_at >= ?2`)
        .bind(JSON.stringify(days), fromAt),
      db.prepare("SELECT key, value FROM kv WHERE key IN (SELECT 'noise_count:' || value FROM json_each(?1))").bind(JSON.stringify(days)),
      // where the news is: published cards by sector and impact (the home page's sector bars)
      db.prepare(`SELECT coalesce(sector, 'default') AS sector, impact_level, count(*) AS n FROM cards
                   WHERE held = 0 AND filed_at >= ?1 GROUP BY 1, 2`).bind(fromAt),
    ]);
    const rows = cards.results as { impact_level: string; signals: number; held: number; n: number }[];
    const sectors: Record<string, { high: number; moderate: number; low: number }> = {};
    for (const r of bySector.results as { sector: string; impact_level: string; n: number }[]) {
      const row = (sectors[r.sector] ??= { high: 0, moderate: 0, low: 0 });
      if (r.impact_level === "HIGH") row.high += r.n; else if (r.impact_level === "MODERATE") row.moderate += r.n; else row.low += r.n;
    }
    const count = (level: string) => rows.find((r) => r.impact_level === level)?.n ?? 0;
    const material = rows.reduce((a, r) => a + r.n, 0);
    const noise = (kv.results as { value: string }[]).reduce((a, r) => a + (Number(r.value) || 0), 0);
    const queued = (ledger.results[0] as { n: number } | undefined)?.n ?? 0;
    return {
      from_at: fromAt,
      scanned: queued + noise, noise, cards: material,
      high: count("HIGH"), moderate: count("MODERATE"), low: count("LOW"),
      held: rows.reduce((a, r) => a + (r.held ?? 0), 0),
      signals: rows.reduce((a, r) => a + (r.signals ?? 0), 0),
      sectors,
      noise_note: "noise counts cover the whole of each day",
    };
  });
  return c.json(body);
});

// One card by its id. A held card is the owner's only (/api/owner/cards/:id): a shared link to it answers 404 here,
// as the public feed never lists it (laptop's screenshots, 2026-10-20: the held banner showed to any visitor).
export async function cardById(c: Context<AppEnv>, withHeld = false) {
  const row = await c.env.DB.prepare(
    `SELECT ${CARD_COLUMNS} FROM cards c LEFT JOIN companies co ON co.scrip_code = c.scrip_code
      WHERE c.news_id = ?1${withHeld ? "" : " AND c.held = 0"}`,
  ).bind(c.req.param("id")).first();
  return row ? c.json(row) : c.json({ error: "not found" }, 404);
}

api.get("/cards/:id", (c) => cardById(c));

// Noise audit: what the AI gatekeeper (D1 ledger) and the rules (one R2 file set per day, newest
// first, NOISE_CHUNK rows each) filtered out on a given day. The first page leads with the
// gatekeeper's rejections; the rule drops follow, paged by offset.
const NOISE_CHUNK = 500;

api.get("/noise", async (c) => {
  const date = c.req.query("date");
  if (!isDate(date)) return c.json({ error: "date=YYYY-MM-DD required" }, 400);
  const limit = clamp(c.req.query("limit"), 100, 200);
  const offset = Math.max(Number.parseInt(c.req.query("offset") ?? "0", 10) || 0, 0);
  const [counted, judged] = await Promise.all([
    c.env.DB.prepare("SELECT value FROM kv WHERE key = ?1").bind(`noise_count:${date}`).first<{ value: string }>(),
    offset === 0
      ? c.env.DB.prepare(`
          SELECT news_id, scrip_code, company_name, headline, category, subcategory, filed_at, status, reason, pdf_url
            FROM filings
           WHERE status = 'NOT_MATERIAL' AND filed_at >= ?1 AND filed_at < date(?1, '+1 day')
           ORDER BY filed_at DESC, news_id DESC
           LIMIT 500`).bind(date).all().then((r) => r.results)
      : Promise.resolve([]),
  ]);
  const total = Number(counted?.value ?? 0) || 0;
  const rows: Record<string, unknown>[] = [];
  for (let chunk = Math.floor(offset / NOISE_CHUNK); chunk * NOISE_CHUNK < Math.min(total, offset + limit); chunk++) {
    const object = await c.env.VAULT.get(`noise/${date}/${String(chunk).padStart(3, "0")}.json`);
    if (!object) break;
    const { fields, rows: part } = (await object.json()) as { fields: string[]; rows: unknown[][] };
    const start = Math.max(offset - chunk * NOISE_CHUNK, 0);
    for (const values of part.slice(start, start + limit - rows.length)) {
      rows.push({ ...Object.fromEntries(fields.map((f, i) => [f, values[i] ?? null])), status: "DROPPED_RULE" });
    }
  }
  return c.json({
    rows: [...judged, ...rows],
    next_offset: offset + limit < total ? offset + limit : null,
    rule_total: total,
  });
});

api.get("/search", async (c) => {
  const fts = ftsQuery(c.req.query("q"));
  if (!fts) return c.json({ companies: [], cards: [] });
  // Each side starts from a bounded set of best matches, so a short, common prefix costs the same
  // as a rare one (sorting every match by date would read every matching card).
  const [companies, cards] = await c.env.DB.batch([
    c.env.DB.prepare(`
      SELECT co.scrip_code, co.symbol, co.company_name, co.sector, co.card_count
        FROM (SELECT rowid AS rid, rank FROM companies_fts WHERE companies_fts MATCH ?1 ORDER BY rank LIMIT 30) f
        CROSS JOIN companies co ON co.rowid = f.rid
       ORDER BY co.card_count DESC, f.rank
       LIMIT 8`).bind(fts),
    c.env.DB.prepare(`
      SELECT c.news_id, c.scrip_code, c.company_name, c.headline, c.impact_level, c.filed_at
        FROM (SELECT rowid AS rid FROM cards_fts WHERE cards_fts MATCH ?1 ORDER BY rank LIMIT 50) f
        CROSS JOIN cards c ON c.rowid = f.rid
       WHERE c.held = 0
       ORDER BY c.filed_at DESC
       LIMIT 8`).bind(fts),
  ]);
  return c.json({ companies: companies.results, cards: cards.results });
});

// Every sort ends on the primary key, so OFFSET paging never repeats or skips a company.
const SORTS = new Map<string, string>([
  ["name", "company_name COLLATE NOCASE ASC, scrip_code"],
  ["mcap", "market_cap_cr IS NULL, market_cap_cr DESC, scrip_code"],
  ["cards", "card_count DESC, company_name COLLATE NOCASE, scrip_code"],
  ["recent", "last_card_at IS NULL, last_card_at DESC, scrip_code"],
]);

api.get("/companies", async (c) => {
  const q = c.req.query();
  const limit = clamp(q.limit, 60, 200);
  // the table holds ~5,500 companies (all=1), so no list runs past this; an unbounded OFFSET read every row it skipped
  const offset = Math.min(Math.max(Number.parseInt(q.offset ?? "0", 10) || 0, 0), 10_000);
  const letter = (q.letter ?? "").toUpperCase();
  let lo: string | null = null;
  let hi: string | null = null;
  if (/^[A-Z]$/.test(letter)) {
    lo = letter;
    hi = String.fromCharCode(letter.charCodeAt(0) + 1);
  } else if (letter === "#") {
    lo = "";
    hi = "A";
  }
  const { params, p } = binder();
  const where = ["1"];
  const fts = ftsQuery(q.q);
  const size = listParam(q.size, SIZES);
  if (fts) where.push(`rowid IN (SELECT rowid FROM companies_fts WHERE companies_fts MATCH ${p(fts)})`);
  if (lo !== null && hi !== null) where.push(`company_name >= ${p(lo)} COLLATE NOCASE AND company_name < ${p(hi)} COLLATE NOCASE`);
  if (q.sector) where.push(`sector = ${p(q.sector)}`);
  if (size) where.push(`size_category IN (SELECT value FROM json_each(${p(size)}))`);
  if (q.all !== "1") where.push("card_count > 0");
  const sql = `
    SELECT ${COMPANY_COLUMNS}
      FROM companies
     WHERE ${where.join(" AND ")}
     ORDER BY ${SORTS.get(q.sort ?? "name") ?? SORTS.get("name")}
     LIMIT ${p(limit + 1)} OFFSET ${p(offset)}`;
  const { results } = await c.env.DB.prepare(sql).bind(...params).all();
  return c.json({ companies: results.slice(0, limit), next_offset: results.length > limit ? offset + limit : null });
});

api.get("/companies/:scrip", async (c) => {
  const asked = c.req.param("scrip").toUpperCase();   // "/company/tcs" as "TCS" (deep audit F-10)
  if (!isCompanyKey(asked)) return c.json({ error: "bad company key" }, 400);
  // an NSE symbol (the site's addresses since 2026-10-21) or the internal key (older links)
  const scrip = /^\d+$/.test(asked) || asked.startsWith("NSE:") ? asked
    : (await c.env.DB.prepare("SELECT scrip_code FROM companies WHERE symbol = ?1 LIMIT 1").bind(asked.toUpperCase())
        .first<{ scrip_code: string }>())?.scrip_code ?? asked;
  const [company, cards, object, chart] = await Promise.all([
    c.env.DB.prepare(`SELECT ${COMPANY_COLUMNS}, json_extract(memory_summary_json, '$.calls') AS calls_json
      FROM companies WHERE scrip_code = ?1`).bind(scrip).first<Record<string, unknown>>(),
    c.env.DB.prepare(`
      SELECT ${CARD_COLUMNS} FROM cards c LEFT JOIN companies co ON co.scrip_code = c.scrip_code
       WHERE c.held = 0 AND c.scrip_code = ?1 ORDER BY c.filed_at DESC LIMIT 60`).bind(scrip).all(),
    c.env.VAULT.get(`memory/${scrip}.json`),
    c.env.VAULT.get(`chart/${scrip}.json`),   // a year of daily closes, written by market-data
  ]);
  // The dossier is spliced in as stored text: parsing and re-serialising a large one would spend
  // most of the free plan's CPU allowance.
  const dossier = object ? await object.text() : "null";
  // Peers: the same sector's companies nearest in market cap (the company page's peers panel)
  const co = company as { sector?: string | null; market_cap_cr?: number | null } | null;
  // Two seeks on idx_companies_sector_mcap, five above the company's cap and five below, nearest five picked here:
  // ORDER BY abs(market_cap_cr - ?) read every row of the sector (before 0013 the whole table, ~5,500 a view) and
  // was 6.7M of the rows D1 read on 20-21 Oct 2026, when the free 5M a day ran out and the site answered 500
  const cap = co?.market_cap_cr;
  const peers = co?.sector && co.sector !== "default" && cap != null
    ? ((await c.env.DB.prepare(`SELECT * FROM (SELECT scrip_code, symbol, company_name, market_cap_cr, ret_1m, ret_1y, card_count
         FROM companies WHERE sector = ?1 AND market_cap_cr >= ?3 AND scrip_code <> ?2 ORDER BY market_cap_cr LIMIT 5)
       UNION ALL SELECT * FROM (SELECT scrip_code, symbol, company_name, market_cap_cr, ret_1m, ret_1y, card_count
         FROM companies WHERE sector = ?1 AND market_cap_cr < ?3 AND scrip_code <> ?2 ORDER BY market_cap_cr DESC LIMIT 5)`)
        .bind(co.sector, scrip, cap).all()).results as { market_cap_cr: number }[])
        .sort((a, b) => Math.abs(a.market_cap_cr - cap) - Math.abs(b.market_cap_cr - cap)).slice(0, 5)
    : [];
  const series = chart ? await chart.text() : "null";
  const { calls_json: callsJson, ...companyRow } = company ?? {};
  const calls = await callLinks(c, parseCalls(callsJson), cards.results as { news_id: string; pdf_url: string | null }[]);
  return c.body(`{"company":${JSON.stringify(company ? companyRow : null)},"cards":${JSON.stringify(cards.results)},"peers":${JSON.stringify(peers)},"chart":${series},"calls":${JSON.stringify(calls)},"dossier":${dossier}}`, 200,
    { "Content-Type": "application/json; charset=UTF-8" });
});

api.get("/calendar", async (c) => {
  const q = c.req.query();
  if (!isDate(q.from) || !isDate(q.to)) return c.json({ error: "from and to (YYYY-MM-DD) required" }, 400);
  const { results } = await c.env.DB.prepare(`
    SELECT id, scrip_code, company_name, symbol, event_type, event_date, description, source_news_id
      FROM catalysts
     WHERE event_date BETWEEN ?1 AND ?2
       AND (?3 IS NULL OR event_type IN (SELECT value FROM json_each(?3)))
     ORDER BY event_date, company_name
     LIMIT 3000`).bind(q.from, q.to, listParam(q.types)).all();
  return c.json({ events: dedupeEvents(results as { scrip_code: string; event_date: string; event_type: string }[]) });
});

export const parseCalls = (raw: unknown): CallQuarter[] => {
  try {
    const v = typeof raw === "string" ? JSON.parse(raw) : null;
    return Array.isArray(v) ? (v as CallQuarter[]) : [];
  } catch {
    return [];
  }
};

/** Each call's PDF: memory keeps it for calls read since 2026-10-20; older ones from their card, else their filing row. */
async function callLinks(c: Context<AppEnv>, calls: CallQuarter[], cards: { news_id: string; pdf_url: string | null }[]): Promise<CallQuarter[]> {
  const known = new Map(cards.filter((r) => r.pdf_url).map((r) => [r.news_id, r.pdf_url as string]));
  const missing = [...new Set(calls.flatMap((q) => q.sources.filter((s) => !s.pdf_url && !known.has(s.news_id)).map((s) => s.news_id)))];
  if (missing.length) {
    const { results } = await c.env.DB.prepare(`SELECT news_id, pdf_url FROM filings
       WHERE news_id IN (SELECT value FROM json_each(?1)) AND pdf_url IS NOT NULL`)
      .bind(JSON.stringify(missing.slice(0, 40))).all<{ news_id: string; pdf_url: string }>();
    for (const r of results) known.set(r.news_id, r.pdf_url);
  }
  return calls.map((q) => ({ ...q, sources: q.sources.map((s) => ({ ...s, pdf_url: s.pdf_url ?? known.get(s.news_id) ?? null })) }));
}

type MemorySummary = {
  open_promises: { id: string; statement: string; due: string | null; due_date: string | null; given_on: string | null; status: string; source_news_id: string | null; overdue_from?: string | null }[];
  triggers: { kind: string; date: string; text: string }[];
  active_capex: number;
  revenue: { period: string; value: number } | null;
  ebitda: { period: string; value: number } | null;
  gross_debt_cr: number | null;
};

const parseSummary = (raw: unknown): MemorySummary | null => {
  try {
    return typeof raw === "string" ? (JSON.parse(raw) as MemorySummary) : null;
  } catch {
    return null;
  }
};

const istDay = (offsetDays = 0) => new Date(Date.now() + 5.5 * 3600_000 + offsetDays * 86400_000).toISOString().slice(0, 10);

// Inflection Radar (blueprint §13 View 3): companies with at least `min` different positive
// triggers in the last 90 days. One range read on idx_companies_inflection.
api.get("/radar", async (c) => {
  const min = clamp(c.req.query("min"), 3, 5);
  const body = await memoised(`radar:${min}`, 300_000, async () => {
    const since = istDay(-90);
    const { results } = await c.env.DB.prepare(`
      SELECT scrip_code, symbol, company_name, sector, market_cap_cr, size_category, credibility_score, watchlist,
             memory_summary_json, inflection_last_at
        FROM companies WHERE inflection_last_at >= ?1 ORDER BY inflection_last_at DESC LIMIT 2000`).bind(since).all();
    const companies = (results as Record<string, unknown>[]).flatMap((r) => {
      const s = parseSummary(r.memory_summary_json);
      const recent = (s?.triggers ?? []).filter((t) => t.date >= since);
      if (new Set(recent.map((t) => t.kind)).size < min) return [];
      const { memory_summary_json: _drop, ...row } = r;
      return [{ ...row, inflection_last_at: String(r.inflection_last_at ?? ""), triggers: recent, active_capex: s?.active_capex ?? 0 }];
    });
    companies.sort((a, b) => b.triggers.length - a.triggers.length || b.inflection_last_at.localeCompare(a.inflection_last_at));
    return { since, min, companies };
  });
  return c.json(body, 200, { "Cache-Control": "public, max-age=300" });
});

// Overdue management promises (Module 44): open promises whose due date has passed, earliest first.
api.get("/promises/overdue", async (c) => {
  const body = await memoised("overdue", 300_000, async () => {
    const today = istDay();
    const { results } = await c.env.DB.prepare(`
      SELECT scrip_code, symbol, company_name, credibility_score, memory_summary_json
        FROM companies WHERE earliest_open_due < ?1 ORDER BY earliest_open_due LIMIT 500`).bind(today).all();
    const promises = (results as Record<string, unknown>[]).flatMap((r) =>
      (parseSummary(r.memory_summary_json)?.open_promises ?? [])
        .filter((p) => isPastDue(p, today))
        .map((p) => ({ ...p, scrip_code: r.scrip_code, symbol: r.symbol, company_name: r.company_name,
                       credibility_score: r.credibility_score,
                       days_overdue: daysPastDue(p, today) })));
    promises.sort((a, b) => b.days_overdue - a.days_overdue);
    return { today, promises: promises.slice(0, 500) };
  });
  return c.json(body, 200, { "Cache-Control": "public, max-age=300" });
});

// Needs-review queue (View 5): published cards marked for review, newest first (partial index). The held ones are the
// owner's (/api/owner/review): the public never sees a held card's headline (private launch, 2026-10-20).
export async function reviewQueue(c: Context<AppEnv>, withHeld = false) {
  // a held results card whose quarter a published card already owns (D20) is superseded, not waiting on anyone: 36 of
  // the 223 in the owner's count on 22 Oct 2026 (release-pruned keeps them held for the same reason)
  // Basis counts: a held consolidated card is not superseded by a published standalone one for the same quarter, the
  // consolidated one is the better card (hourly audit 22 Oct: SMLMAH Q2FY26, PVR INOX Q4FY26, Bandhan Q1FY27 were hidden)
  const superseded = `c.held = 1 AND c.event_category = 'RESULTS' AND EXISTS (SELECT 1 FROM cards p
      WHERE p.scrip_code = c.scrip_code AND p.held = 0 AND p.news_id <> c.news_id AND p.event_category = 'RESULTS'
        AND json_extract(p.card_json, '$.results.period') = json_extract(c.card_json, '$.results.period')
        AND NOT (json_extract(c.card_json, '$.basis') = 'CONSOLIDATED'
                 AND coalesce(json_extract(p.card_json, '$.basis'), '') <> 'CONSOLIDATED'))`;
  // A window on filed_at (idx_cards_feed, idx_cards_feed_live) instead of the whole table, which both queries walked
  // once 0011 dropped idx_cards_review: the public list covers the live window, the owner's a month; an older held card
  // is still in the owner's feed under "Held for review only" (survey, 24 Oct 2026)
  const since = istDay(withHeld ? -30 : -8);
  const which = withHeld ? `c.filed_at >= ?1 AND (c.needs_review = 1 OR c.held = 1) AND NOT (${superseded})`
    : "c.filed_at >= ?1 AND c.needs_review = 1 AND c.held = 0";
  // the list shows 100, the heading the real count; a card whose filing is queued again says so (owner, 2026-10-20:
  // "never seen anything getting reduced": the heading was the list's length, capped at 100, and the button's
  // "queued" state lived only in the open page)
  const load = async () => {
    const [list, total] = await c.env.DB.batch([
      c.env.DB.prepare(`
        SELECT c.news_id, c.scrip_code, c.symbol, c.company_name, c.filed_at, c.headline, c.event_category,
               json_extract(c.card_json, '$.grounding') AS grounding, json_extract(c.card_json, '$.review') AS review, c.held,
               f.status AS filing_status
          FROM cards c LEFT JOIN filings f ON f.news_id = c.news_id WHERE ${which}
         ORDER BY c.held DESC, c.filed_at DESC LIMIT 100`).bind(since),
      c.env.DB.prepare(`SELECT count(*) AS n FROM cards c WHERE ${which}`).bind(since),
    ]);
    return { cards: list.results, total: Number((total.results[0] as { n?: number } | undefined)?.n ?? list.results.length) };
  };
  const body = withHeld ? await load() : await memoised(`review:${since}`, 60_000, load);
  return c.json(body, 200, { "Cache-Control": withHeld ? "private, no-store" : "public, max-age=60" });
}

api.get("/review", (c) => reviewQueue(c));

// Counts above this are shown as "1,000+": an exact count would read every queued row.
const QUEUE_CAP = 1000;

// The System page is the owner's (owner, 22 Oct 2026: "system page ideally should be only visible to owner not public"):
// /api/owner/system has everything; this public one only what the public pages show, and the recover job's health probe.
api.get("/system", async (c) => {
  const body = await memoised("system", 30_000, () => systemStatus(c));
  return c.json(publicSystem(body), 200, { "Cache-Control": "public, max-age=15, s-maxage=30" });
});

export function publicSystem(s: Awaited<ReturnType<typeof systemStatus>>): PublicSystemResponse {
  const limited = (s.usage as { requests: number; limit_rpd: number | null }[]).filter((u) => u.limit_rpd);
  const allowed = limited.reduce((n, u) => n + (u.limit_rpd ?? 0), 0);
  return {
    today: s.today,
    ledger_today: s.ledger_today,
    queue: s.queue,
    // published cards only: the held ones are the owner's, as on the feed (survey, 24 Oct 2026)
    cards_7d: (s.cards_7d as { impact_level: string; published: number | null }[])
      .map((r) => ({ impact_level: r.impact_level, n: r.published ?? 0 })) as PublicSystemResponse["cards_7d"],
    backfill: { start: s.backfill.start, discovered_through: s.backfill.discovered_through, complete: s.backfill.complete },
    runs: (s.runs as PublicSystemResponse["runs"]).map(({ run_id, mode, started_at, finished_at, status }) =>
      ({ run_id, mode, started_at, finished_at, status })),
    quota_used: allowed ? limited.reduce((n, u) => n + u.requests, 0) / allowed : null,
  };
}

export async function systemStatus(c: Context<AppEnv>) {
  const today = new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10); // IST date
  const utcDay = new Date().toISOString().slice(0, 10);
  // each provider's own quota day: Gemini's runs on Pacific time and is still yesterday (UTC) until 07:00 UTC, so
  // "today (UTC)" alone left Gemini off the page while it served most packed calls (owner, 2026-10-20)
  const yesterdayUtc = new Date(Date.now() - 86400_000).toISOString().slice(0, 10);
  const weekAgo = new Date(Date.now() + 5.5 * 3600_000 - 7 * 86400_000).toISOString().slice(0, 10);
  const db = c.env.DB;
  const [ledger, pending, failed, cards7d, usage, runs, kv, failedList, jobs] = await db.batch([
    db.prepare("SELECT status, count(*) AS n FROM filings WHERE filing_date = ?1 GROUP BY status").bind(today),
    db.prepare(`SELECT count(*) AS n FROM (SELECT 1 FROM filings WHERE status = 'PENDING' LIMIT ${QUEUE_CAP})`),
    db.prepare(`SELECT count(*) AS n FROM (SELECT 1 FROM filings WHERE status = 'FAILED' LIMIT ${QUEUE_CAP})`),
    db.prepare(`SELECT impact_level, count(*) AS n, sum(held = 0) AS published FROM cards
                 WHERE impact_level IN ('HIGH', 'MODERATE', 'LOW') AND filed_at >= ?1 GROUP BY impact_level`).bind(weekAgo),
    db.prepare(`SELECT day, provider, model, requests, input_tokens, output_tokens, failures, rate_limited, limit_rpd,
                       limit_tpd, substr(last_error, 1, 160) AS last_error, updated_at
                  FROM provider_usage p WHERE day >= ?1
                   AND day = (SELECT max(day) FROM provider_usage q WHERE q.provider = p.provider AND q.model = p.model)
                 ORDER BY provider, model`).bind(yesterdayUtc),
    db.prepare(`SELECT run_id, mode, started_at, finished_at, status, stats_json, substr(error, 1, 200) AS error
                  FROM pipeline_runs ORDER BY started_at DESC LIMIT 25`),
    db.prepare(`SELECT key, value FROM kv WHERE key IN ('backfill:discovered_through', 'backfill:complete',
                  'backfill:start', 'backfill:progress', 'backfill:pace', 'market:coverage', ?1, ?2)`).bind(`noise_count:${today}`, `d1_writes:${utcDay}`),
    // which filings failed and why (owner, 2026-10-20: the count alone did not say); a range seek on (status, filed_at)
    db.prepare(`SELECT news_id, scrip_code, symbol, company_name, headline, filed_at, attempts, substr(last_error, 1, 200) AS last_error
                  FROM filings WHERE status = 'FAILED' AND filed_at >= ?1 ORDER BY filed_at DESC LIMIT 50`).bind(weekAgo),
    // each scheduled job's last run, written by the CLI when it ends (cli._record_job)
    db.prepare("SELECT key, value FROM kv WHERE key >= 'job:' AND key < 'job;'"),
  ]);
  const kvMap = Object.fromEntries((kv.results as { key: string; value: string }[]).map((r) => [r.key, r.value]));
  const count = (r: D1Result) => (r.results[0] as { n: number } | undefined)?.n ?? 0;
  const ruleDropped = Number(kvMap[`noise_count:${today}`] ?? 0) || 0;
  let progress: { companies_left: number; companies_total: number | null } | null = null;
  try {
    progress = kvMap["backfill:progress"] ? JSON.parse(kvMap["backfill:progress"]) : null;
  } catch {
    progress = null;
  }
  let pace: [string, string][] = [];
  try {
    pace = kvMap["backfill:pace"] ? JSON.parse(kvMap["backfill:pace"]) : [];
  } catch {
    pace = [];
  }
  let coverage: Record<string, unknown> | null = null;
  try {
    coverage = kvMap["market:coverage"] ? JSON.parse(kvMap["market:coverage"]) : null;
  } catch {
    coverage = null;
  }
  return {
    today,
    market_coverage: coverage
      ? { date: coverage.date, companies: coverage.companies, priced: coverage.priced, missing: coverage.missing, missing_pct: coverage.missing_pct }
      : null,
    ledger_today: [...(ledger.results as { status: string; n: number }[]), ...(ruleDropped ? [{ status: "DROPPED_RULE", n: ruleDropped }] : [])],
    queue: { pending: count(pending), failed: count(failed), cap: QUEUE_CAP },
    cards_7d: cards7d.results,
    backfill: {
      start: kvMap["backfill:start"] ?? "2025-01-01",
      discovered_through: kvMap["backfill:discovered_through"] ?? null,
      complete: kvMap["backfill:complete"] === "1",
      companies_left: progress?.companies_left ?? null,
      companies_total: progress?.companies_total ?? null,
      pace,
    },
    d1: { writes_today: Number(kvMap[`d1_writes:${utcDay}`] ?? 0) || 0, size_bytes: ledger.meta?.size_after ?? null },
    usage: usage.results,
    runs: runs.results,
    failed_recent: failedList.results,
    jobs: Object.fromEntries((jobs.results as { key: string; value: string }[]).flatMap((r) => {
      try {
        return [[r.key.slice(4), JSON.parse(r.value) as { at: string; ok: boolean }]];
      } catch {
        return [];
      }
    })),
  };
}
