// Read-only API for the frontend. Every query is index-backed and bounded:
// D1's free tier meters rows *read* (5M/day), so each query seeks a range
// (dates, the cursor) instead of walking a table, and hot responses are kept
// briefly in the isolate and, on a custom domain, in Cloudflare's edge cache.
import { Hono } from "hono";
import type { Context } from "hono";
import type { AppEnv } from "./env";

const CARD_COLUMNS = `
  c.news_id, c.scrip_code, c.symbol, c.company_name, c.filing_date, c.filed_at, c.sector,
  c.event_category, c.impact_level, c.headline, c.grounding_score, c.needs_review,
  c.memory_complete, c.card_json, c.pdf_url, c.market_session, c.actionability_score, c.is_actionable_signal, c.post_event_return_json, c.held,
  co.market_cap_cr, co.size_category, co.last_price, co.ret_1w, co.ret_1m, co.ret_1y,
  co.median_turnover_cr, co.credibility_score, co.watchlist, co.bse_group, co.technicals_json, co.former_names_json`;

const COMPANY_COLUMNS = `scrip_code, symbol, company_name, isin, industry, sector, market_cap_cr,
  size_category, last_price, price_date, ret_1w, ret_1m, ret_1y, card_count, last_card_at,
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
// A company's key: its BSE scrip code, or for a company never on BSE (a listing after the move to NSE,
// 2026-10-19) its NSE symbol ("TATATECH", "M&M", "BAJAJ-AUTO")
export const isCompanyKey = (s: string | undefined) => !!s && /^(\d{3,8}|[A-Z0-9][A-Z0-9&-]{0,19})$/.test(s);
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
const SNAPSHOT_KEY = "daily_feed/latest_snapshot.json";

interface Snapshot {
  generated_at: string;
  from: string;
  limit: number;
  feed: { cards: unknown[]; total: number };
  signals: unknown[];
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
  const page = q.page ? clamp(q.page, 1, 400) : null;
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

const todayIst = () => new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10);

// Top Signals: cards that cleared the 4 gates, best score first (partial index idx_cards_signals).
api.get("/signals", async (c) => {
  const q = c.req.query();
  const fromAt = q.from_at && /^\d{4}-\d{2}-\d{2}T/.test(q.from_at) ? q.from_at : `${isDate(q.from) ? q.from : todayIst()}`;
  const toAt = q.to_at && /^\d{4}-\d{2}-\d{2}T/.test(q.to_at) ? q.to_at : `${isDate(q.to) ? q.to : "2999-12-31"}T99`;
  const snap = !q.from_at && !q.to && q.from ? await snapshot(c) : null;
  if (snap && snap.from === q.from) return c.json({ cards: snap.signals, source: "snapshot" });
  const { results } = await c.env.DB.prepare(`
    SELECT ${CARD_COLUMNS}
      FROM cards c LEFT JOIN companies co ON co.scrip_code = c.scrip_code
     WHERE c.held = 0 AND c.is_actionable_signal = 1 AND c.filed_at >= ?1 AND c.filed_at <= ?2
     ORDER BY c.actionability_score DESC, c.filed_at DESC
     LIMIT 50`).bind(fromAt, toAt).all();
  return c.json({ cards: results });
});

// Pre-market brief: what came in since a moment (by default yesterday's 15:30 IST close).
api.get("/brief", async (c) => {
  const q = c.req.query();
  if (!q.from_at || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(q.from_at)) return c.json({ error: "from_at required" }, 400);
  const fromAt = q.from_at;
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

api.get("/cards/:id", async (c) => {
  const row = await c.env.DB.prepare(
    `SELECT ${CARD_COLUMNS} FROM cards c LEFT JOIN companies co ON co.scrip_code = c.scrip_code WHERE c.news_id = ?1`,
  ).bind(c.req.param("id")).first();
  return row ? c.json(row) : c.json({ error: "not found" }, 404);
});

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
  const offset = Math.max(Number.parseInt(q.offset ?? "0", 10) || 0, 0);
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
  const scrip = c.req.param("scrip");
  if (!isCompanyKey(scrip)) return c.json({ error: "bad company key" }, 400);
  const [company, cards, object] = await Promise.all([
    c.env.DB.prepare(`SELECT ${COMPANY_COLUMNS} FROM companies WHERE scrip_code = ?1`).bind(scrip).first(),
    c.env.DB.prepare(`
      SELECT ${CARD_COLUMNS} FROM cards c LEFT JOIN companies co ON co.scrip_code = c.scrip_code
       WHERE c.held = 0 AND c.scrip_code = ?1 ORDER BY c.filed_at DESC LIMIT 60`).bind(scrip).all(),
    c.env.VAULT.get(`memory/${scrip}.json`),
  ]);
  // The dossier is spliced in as stored text: parsing and re-serialising a large one would spend
  // most of the free plan's CPU allowance.
  const dossier = object ? await object.text() : "null";
  // Peers: the same sector's companies nearest in market cap (the company page's peers panel)
  const co = company as { sector?: string | null; market_cap_cr?: number | null } | null;
  const peers = co?.sector && co.sector !== "default" && co.market_cap_cr != null
    ? (await c.env.DB.prepare(`SELECT scrip_code, symbol, company_name, market_cap_cr, ret_1m, ret_1y, card_count FROM companies
         WHERE sector = ?1 AND scrip_code <> ?2 AND market_cap_cr IS NOT NULL
         ORDER BY abs(market_cap_cr - ?3) LIMIT 5`).bind(co.sector, scrip, co.market_cap_cr).all()).results
    : [];
  return c.body(`{"company":${JSON.stringify(company)},"cards":${JSON.stringify(cards.results)},"peers":${JSON.stringify(peers)},"dossier":${dossier}}`, 200,
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
  return c.json({ events: results });
});

type MemorySummary = {
  open_promises: { id: string; statement: string; due: string | null; due_date: string | null; given_on: string | null; status: string; source_news_id: string | null }[];
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
        .filter((p) => p.due_date && p.due_date < today)
        .map((p) => ({ ...p, scrip_code: r.scrip_code, symbol: r.symbol, company_name: r.company_name,
                       credibility_score: r.credibility_score,
                       days_overdue: Math.round((Date.parse(today) - Date.parse(p.due_date!)) / 86400_000) })));
    promises.sort((a, b) => b.days_overdue - a.days_overdue);
    return { today, promises: promises.slice(0, 500) };
  });
  return c.json(body, 200, { "Cache-Control": "public, max-age=300" });
});

// Needs-review queue (View 5): cards held back by the checks, newest first (partial index).
api.get("/review", async (c) => {
  const { results } = await c.env.DB.prepare(`
    SELECT c.news_id, c.scrip_code, c.symbol, c.company_name, c.filed_at, c.headline, c.event_category,
           json_extract(c.card_json, '$.grounding') AS grounding, json_extract(c.card_json, '$.review') AS review, c.held
      FROM cards c WHERE c.needs_review = 1 OR c.held = 1
     ORDER BY c.held DESC, c.filed_at DESC LIMIT 100`).all();
  return c.json({ cards: results }, 200, { "Cache-Control": "public, max-age=60" });
});

// Counts above this are shown as "1,000+": an exact count would read every queued row.
const QUEUE_CAP = 1000;

api.get("/system", async (c) => {
  const body = await memoised("system", 30_000, () => systemStatus(c));
  return c.json(body, 200, { "Cache-Control": "public, max-age=15, s-maxage=30" });
});

async function systemStatus(c: Context<AppEnv>) {
  const today = new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10); // IST date
  const utcDay = new Date().toISOString().slice(0, 10);
  const weekAgo = new Date(Date.now() + 5.5 * 3600_000 - 7 * 86400_000).toISOString().slice(0, 10);
  const db = c.env.DB;
  const [ledger, pending, failed, cards7d, usage, runs, kv] = await db.batch([
    db.prepare("SELECT status, count(*) AS n FROM filings WHERE filing_date = ?1 GROUP BY status").bind(today),
    db.prepare(`SELECT count(*) AS n FROM (SELECT 1 FROM filings WHERE status = 'PENDING' LIMIT ${QUEUE_CAP})`),
    db.prepare(`SELECT count(*) AS n FROM (SELECT 1 FROM filings WHERE status = 'FAILED' LIMIT ${QUEUE_CAP})`),
    db.prepare(`SELECT impact_level, count(*) AS n FROM cards
                 WHERE impact_level IN ('HIGH', 'MODERATE', 'LOW') AND filed_at >= ?1 GROUP BY impact_level`).bind(weekAgo),
    db.prepare(`SELECT day, provider, model, requests, input_tokens, output_tokens, failures, rate_limited, limit_rpd,
                       limit_tpd, substr(last_error, 1, 160) AS last_error, updated_at
                  FROM provider_usage WHERE day = ?1 ORDER BY provider, model`).bind(utcDay),
    db.prepare(`SELECT run_id, mode, started_at, finished_at, status, stats_json, substr(error, 1, 200) AS error
                  FROM pipeline_runs ORDER BY started_at DESC LIMIT 25`),
    db.prepare(`SELECT key, value FROM kv WHERE key IN ('backfill:discovered_through', 'backfill:complete',
                  'backfill:start', 'backfill:progress', 'market:coverage', ?1, ?2)`).bind(`noise_count:${today}`, `d1_writes:${utcDay}`),
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
    },
    d1: { writes_today: Number(kvMap[`d1_writes:${utcDay}`] ?? 0) || 0, size_bytes: ledger.meta?.size_after ?? null },
    usage: usage.results,
    runs: runs.results,
  };
}
