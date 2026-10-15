// The owner's few writes from the website: star a company (watchlist) and rate a card as a
// signal or as noise (blueprint Loop 3, the golden set the prompts learn from). Protected by a
// separate OWNER_TOKEN secret, which the browser keeps in localStorage after the owner enters it.
import { Hono, type MiddlewareHandler } from "hono";
import { bearerAuth } from "hono/bearer-auth";
import type { AppEnv } from "./env";

export const owner = new Hono<AppEnv>();

owner.use("*", async (c, next) => {
  if (!c.env.OWNER_TOKEN) return c.json({ error: "OWNER_TOKEN is not configured" }, 503);
  const auth: MiddlewareHandler<AppEnv> = bearerAuth({ token: c.env.OWNER_TOKEN });
  return auth(c, next);
});

owner.get("/check", (c) => c.json({ ok: true }));

owner.post("/watchlist", async (c) => {
  const body = await c.req.json<{ scrip_code?: string; on?: boolean }>().catch(() => null);
  if (!body?.scrip_code || !/^\d{3,8}$/.test(body.scrip_code)) return c.json({ error: "scrip_code required" }, 400);
  const result = await c.env.DB.prepare("UPDATE companies SET watchlist = ?1 WHERE scrip_code = ?2")
    .bind(body.on === false ? 0 : 1, body.scrip_code).run();
  return c.json({ ok: (result.meta.changes ?? 0) > 0 });
});

owner.post("/feedback", async (c) => {
  const body = await c.req.json<{ news_id?: string; rating?: string; note?: string }>().catch(() => null);
  const rating = body?.rating?.toUpperCase();
  if (!body?.news_id || (rating !== "STARRED" && rating !== "NOISE" && rating !== "CLEAR")) {
    return c.json({ error: "news_id and rating (STARRED, NOISE or CLEAR) required" }, 400);
  }
  if (rating === "CLEAR") {
    await c.env.DB.prepare("DELETE FROM card_feedback WHERE news_id = ?1").bind(body.news_id).run();
    return c.json({ ok: true });
  }
  const card = await c.env.DB.prepare("SELECT scrip_code, sector, event_category, card_json FROM cards WHERE news_id = ?1")
    .bind(body.news_id).first<{ scrip_code: string; sector: string | null; event_category: string; card_json: string }>();
  if (!card) return c.json({ error: "card not found" }, 404);
  await c.env.DB.prepare(`
    INSERT INTO card_feedback (news_id, scrip_code, sector, event_category, rating, user_note, card_json_snapshot, created_at)
    VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)
    ON CONFLICT (news_id) DO UPDATE SET rating = excluded.rating, user_note = excluded.user_note, created_at = excluded.created_at`)
    .bind(body.news_id, card.scrip_code, card.sector, card.event_category, rating, (body.note ?? "").slice(0, 500),
      card.card_json, new Date().toISOString())
    .run();
  return c.json({ ok: true });
});

// Re-run a card held for review: the filing goes back to the queue with its attempts reset. The
// next pipeline run re-analyses it from the cached text (no new download).
owner.post("/requeue", async (c) => {
  const body = await c.req.json<{ news_id?: string }>().catch(() => null);
  if (!body?.news_id) return c.json({ error: "news_id required" }, 400);
  const result = await c.env.DB.prepare(
    "UPDATE filings SET status = 'PENDING', attempts = 0, last_error = 'requeued by owner', updated_at = ?2 WHERE news_id = ?1")
    .bind(body.news_id, new Date().toISOString()).run();
  return c.json({ ok: (result.meta.changes ?? 0) > 0 });
});

owner.get("/feedback", async (c) => {
  const { results } = await c.env.DB.prepare(
    "SELECT news_id, rating FROM card_feedback ORDER BY created_at DESC LIMIT 500").all();
  return c.json({ ratings: results });
});
