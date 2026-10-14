// Read-only API for the frontend. Every query is index-backed and bounded:
// D1's free tier meters rows *read* (5M/day), so full scans are avoided and
// responses carry short edge-cache lifetimes.
import { Hono } from "hono";
import type { AppEnv } from "./env";

const CARD_COLUMNS = `
  c.news_id, c.scrip_code, c.symbol, c.company_name, c.filing_date, c.filed_at, c.sector,
  c.event_category, c.impact_level, c.headline, c.grounding_score, c.needs_review,
  c.memory_complete, c.card_json, c.pdf_url,
  co.market_cap_cr, co.size_category, co.last_price, co.ret_1w, co.ret_1m, co.ret_1y`;

const COMPANY_COLUMNS = `scrip_code, symbol, company_name, isin, industry, sector, market_cap_cr,
  size_category, last_price, price_date, ret_1w, ret_1m, ret_1y, card_count, last_card_at`;

/** Turn free text into a safe FTS5 prefix query: "tata mot" -> "tata"* "mot"* */
export function ftsQuery(q: string | undefined): string | null {
  const tokens = (q ?? "").toLowerCase().match(/[\p{L}\p{N}]+/gu)?.slice(0, 6) ?? [];
  return tokens.length ? tokens.map((t) => `"${t}"*`).join(" ") : null;
}

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
const clamp = (v: string | undefined, def: number, max: number) =>
  Math.min(Math.max(Number.parseInt(v ?? "", 10) || def, 1), max);

export const api = new Hono<AppEnv>();

api.use("*", async (c, next) => {
  await next();
  if (c.req.path.startsWith("/api/internal/")) return;
  if (c.req.method === "GET" && c.res.status === 200 && !c.res.headers.has("Cache-Control")) {
    c.res.headers.set("Cache-Control", "public, max-age=30, s-maxage=60");
  }
});

api.get("/feed", async (c) => {
  const q = c.req.query();
  const from = isDate(q.from) ? q.from : "2000-01-01";
  const to = isDate(q.to) ? q.to : "2999-12-31";
  const limit = clamp(q.limit, 20, 50);
  const [cursorAt, cursorId] = (q.cursor ?? "").split("|");
  const sql = `
    SELECT ${CARD_COLUMNS}
      FROM cards c LEFT JOIN companies co ON co.scrip_code = c.scrip_code
     WHERE c.filing_date BETWEEN ?1 AND ?2
       AND (?3 IS NULL OR c.impact_level IN (SELECT value FROM json_each(?3)))
       AND (?4 IS NULL OR c.event_category IN (SELECT value FROM json_each(?4)))
       AND (?5 IS NULL OR co.size_category IN (SELECT value FROM json_each(?5)))
       AND (?6 IS NULL OR c.sector IN (SELECT value FROM json_each(?6)))
       AND (?7 IS NULL OR c.rowid IN (SELECT rowid FROM cards_fts WHERE cards_fts MATCH ?7))
       AND (?8 IS NULL OR (c.filed_at, c.news_id) < (?8, ?9))
       AND (?10 = 1 OR c.needs_review = 0)
     ORDER BY c.filed_at DESC, c.news_id DESC
     LIMIT ?11`;
  const { results } = await c.env.DB.prepare(sql)
    .bind(
      from, to,
      listParam(q.impact, IMPACTS), listParam(q.category), listParam(q.size, SIZES), listParam(q.sector),
      ftsQuery(q.q), cursorAt || null, cursorId || "", q.review === "0" ? 0 : 1, limit + 1,
    )
    .all();
  const more = results.length > limit;
  const cards = results.slice(0, limit) as { filed_at: string; news_id: string }[];
  const last = cards[cards.length - 1];
  return c.json({ cards, next_cursor: more && last ? `${last.filed_at}|${last.news_id}` : null });
});

api.get("/cards/:id", async (c) => {
  const row = await c.env.DB.prepare(
    `SELECT ${CARD_COLUMNS} FROM cards c LEFT JOIN companies co ON co.scrip_code = c.scrip_code WHERE c.news_id = ?1`,
  ).bind(c.req.param("id")).first();
  return row ? c.json(row) : c.json({ error: "not found" }, 404);
});

// Noise audit: what the rules and the gatekeeper filtered out on a given day.
api.get("/noise", async (c) => {
  const date = c.req.query("date");
  if (!isDate(date)) return c.json({ error: "date=YYYY-MM-DD required" }, 400);
  const limit = clamp(c.req.query("limit"), 100, 200);
  const offset = Math.max(Number.parseInt(c.req.query("offset") ?? "0", 10) || 0, 0);
  const [{ results }, counted] = await Promise.all([
    c.env.DB.prepare(`
      SELECT news_id, scrip_code, company_name, headline, category, subcategory, filed_at, status, reason, pdf_url
        FROM filings
       WHERE filing_date = ?1 AND status IN ('DROPPED_RULE', 'NOT_MATERIAL')
       ORDER BY filed_at DESC
       LIMIT ?2 OFFSET ?3`).bind(date, limit + 1, offset).all(),
    // Backfilled days count their rule-dropped filings instead of storing them (saves D1 writes).
    c.env.DB.prepare("SELECT value FROM kv WHERE key = ?1").bind(`noise_count:${date}`).first<{ value: string }>(),
  ]);
  return c.json({
    rows: results.slice(0, limit),
    next_offset: results.length > limit ? offset + limit : null,
    not_stored: counted ? Number(counted.value) : null,
  });
});

api.get("/search", async (c) => {
  const fts = ftsQuery(c.req.query("q"));
  if (!fts) return c.json({ companies: [], cards: [] });
  const [companies, cards] = await c.env.DB.batch([
    c.env.DB.prepare(`
      SELECT co.scrip_code, co.symbol, co.company_name, co.sector, co.card_count
        FROM companies_fts f JOIN companies co ON co.rowid = f.rowid
       WHERE companies_fts MATCH ?1
       ORDER BY co.card_count DESC, rank
       LIMIT 8`).bind(fts),
    c.env.DB.prepare(`
      SELECT c.news_id, c.scrip_code, c.company_name, c.headline, c.impact_level, c.filed_at
        FROM cards_fts f JOIN cards c ON c.rowid = f.rowid
       WHERE cards_fts MATCH ?1
       ORDER BY c.filed_at DESC
       LIMIT 8`).bind(fts),
  ]);
  return c.json({ companies: companies.results, cards: cards.results });
});

const SORTS: Record<string, string> = {
  name: "company_name COLLATE NOCASE ASC",
  mcap: "market_cap_cr IS NULL, market_cap_cr DESC",
  cards: "card_count DESC, company_name COLLATE NOCASE",
  recent: "last_card_at IS NULL, last_card_at DESC",
};

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
  const sql = `
    SELECT ${COMPANY_COLUMNS}
      FROM companies
     WHERE (?1 IS NULL OR rowid IN (SELECT rowid FROM companies_fts WHERE companies_fts MATCH ?1))
       AND (?2 IS NULL OR (company_name >= ?2 COLLATE NOCASE AND company_name < ?3 COLLATE NOCASE))
       AND (?4 IS NULL OR sector = ?4)
       AND (?5 IS NULL OR size_category IN (SELECT value FROM json_each(?5)))
       AND (?6 = 0 OR card_count > 0)
     ORDER BY ${SORTS[q.sort ?? "name"] ?? SORTS.name}
     LIMIT ?7 OFFSET ?8`;
  const { results } = await c.env.DB.prepare(sql)
    .bind(ftsQuery(q.q), lo, hi, q.sector || null, listParam(q.size, SIZES), q.all === "1" ? 0 : 1, limit + 1, offset)
    .all();
  return c.json({ companies: results.slice(0, limit), next_offset: results.length > limit ? offset + limit : null });
});

api.get("/companies/:scrip", async (c) => {
  const scrip = c.req.param("scrip");
  if (!/^\d{3,8}$/.test(scrip)) return c.json({ error: "bad scrip code" }, 400);
  const [company, cards, object] = await Promise.all([
    c.env.DB.prepare(`SELECT ${COMPANY_COLUMNS} FROM companies WHERE scrip_code = ?1`).bind(scrip).first(),
    c.env.DB.prepare(`
      SELECT ${CARD_COLUMNS} FROM cards c LEFT JOIN companies co ON co.scrip_code = c.scrip_code
       WHERE c.scrip_code = ?1 ORDER BY c.filed_at DESC LIMIT 60`).bind(scrip).all(),
    c.env.VAULT.get(`memory/${scrip}.json`),
  ]);
  return c.json({ company, cards: cards.results, dossier: object ? await object.json() : null });
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

api.get("/system", async (c) => {
  const today = new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10); // IST date
  const utcDay = new Date().toISOString().slice(0, 10);
  const weekAgo = new Date(Date.now() - 7 * 86400_000).toISOString().slice(0, 10);
  const db = c.env.DB;
  const [ledger, pending, failed, cards7d, usage, runs, kv] = await db.batch([
    db.prepare("SELECT status, count(*) AS n FROM filings WHERE filing_date = ?1 GROUP BY status").bind(today),
    db.prepare("SELECT count(*) AS n FROM filings WHERE status = 'PENDING'"),
    db.prepare("SELECT count(*) AS n FROM filings WHERE status = 'FAILED'"),
    db.prepare("SELECT impact_level, count(*) AS n FROM cards WHERE filing_date >= ?1 GROUP BY impact_level").bind(weekAgo),
    db.prepare("SELECT * FROM provider_usage WHERE day = ?1 ORDER BY provider, model").bind(utcDay),
    db.prepare("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 25"),
    db.prepare("SELECT key, value FROM kv WHERE key IN ('backfill:discovered_through', 'backfill:complete', 'backfill:start')"),
  ]);
  const kvMap = Object.fromEntries((kv.results as { key: string; value: string }[]).map((r) => [r.key, r.value]));
  return c.json(
    {
      today,
      ledger_today: ledger.results,
      queue: { pending: (pending.results[0] as { n: number })?.n ?? 0, failed: (failed.results[0] as { n: number })?.n ?? 0 },
      cards_7d: cards7d.results,
      backfill: {
        start: kvMap["backfill:start"] ?? "2026-01-01",
        discovered_through: kvMap["backfill:discovered_through"] ?? null,
        complete: kvMap["backfill:complete"] === "1",
      },
      usage: usage.results,
      runs: runs.results,
    },
    200,
    { "Cache-Control": "public, max-age=15, s-maxage=30" },
  );
});
