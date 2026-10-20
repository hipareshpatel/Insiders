// The owner's few writes from the website: star a company (watchlist) and rate a card as a
// signal or as noise (blueprint Loop 3, the golden set the prompts learn from). Protected by a
// separate OWNER_TOKEN secret, which the browser keeps in localStorage after the owner enters it.
import { Hono, type MiddlewareHandler } from "hono";
import { bearerAuth } from "hono/bearer-auth";
import type { AppEnv } from "./env";
import { withOwnerHold } from "../shared/ownerHold";
import { cardById, feed, isCompanyKey, reviewQueue, SNAPSHOT_KEY } from "./public";

export const owner = new Hono<AppEnv>();

owner.use("*", async (c, next) => {
  if (!c.env.OWNER_TOKEN) return c.json({ error: "OWNER_TOKEN is not configured" }, 503);
  const auth: MiddlewareHandler<AppEnv> = bearerAuth({ token: c.env.OWNER_TOKEN });
  return auth(c, next);
});

owner.get("/check", (c) => c.json({ ok: true }));

owner.post("/watchlist", async (c) => {
  const body = await c.req.json<{ scrip_code?: string; on?: boolean }>().catch(() => null);
  if (!body || !isCompanyKey(body.scrip_code)) return c.json({ error: "scrip_code required" }, 400);
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

// The owner's own feed: the public one plus the cards held back from it (private launch, owner 2026-10-19).
// A card by id and the review queue with the held cards in them (the public routes leave those out)
owner.get("/cards/:id", async (c) => {
  const res = await cardById(c, true);
  res.headers.set("Cache-Control", "private, no-store");
  return res;
});
owner.get("/review", (c) => reviewQueue(c, true));

owner.get("/feed", async (c) => {
  const res = await feed(c, true);
  res.headers.set("Cache-Control", "private, no-store");
  return res;
});

// The owner's verdict on a card (RIGHT, MINOR or WRONG, with a note), kept with the card as it was judged;
// CLEAR removes it. Read back by GET /verdicts (the System page) and by the pipeline's audit tally.
// A verdict acts on the card (O11, owner 2026-10-20: a card marked Wrong stayed public): WRONG holds it out of
// the public feed with the note as the hold reason; RIGHT publishes it, a card the checks held included (the
// owner's approve); MINOR and CLEAR put back the held flag the card had before the owner's own hold.
owner.post("/verdict", async (c) => {
  const body = await c.req.json<{ news_id?: string; verdict?: string; note?: string }>().catch(() => null);
  const verdict = body?.verdict?.toUpperCase();
  if (!body?.news_id || !verdict || !["RIGHT", "MINOR", "WRONG", "CLEAR"].includes(verdict)) {
    return c.json({ error: "news_id and verdict (RIGHT, MINOR, WRONG or CLEAR) required" }, 400);
  }
  const db = c.env.DB;
  const [card, prior] = await Promise.all([
    db.prepare("SELECT scrip_code, event_category, held, card_json FROM cards WHERE news_id = ?1")
      .bind(body.news_id).first<{ scrip_code: string; event_category: string; held: number; card_json: string }>(),
    db.prepare("SELECT verdict, held FROM card_verdicts WHERE news_id = ?1")
      .bind(body.news_id).first<{ verdict: string; held: number }>(),
  ]);
  if (!card && verdict !== "CLEAR") return c.json({ error: "card not found" }, 404);
  const note = (body.note ?? "").slice(0, 1000);
  const heldNow = card?.held ? 1 : 0;
  // the card's held flag before the owner's own hold: under a standing WRONG it is the one stored with that verdict
  const before = prior?.verdict === "WRONG" ? (prior.held ? 1 : 0) : heldNow;
  const statements: D1PreparedStatement[] = [];
  let held: number | null = null;
  if (verdict === "CLEAR") {
    statements.push(db.prepare("DELETE FROM card_verdicts WHERE news_id = ?1").bind(body.news_id));
    if (prior?.verdict === "WRONG") held = before;
  } else {
    held = verdict === "WRONG" ? 1 : verdict === "RIGHT" ? 0 : before;
    // a note saved under a standing WRONG keeps the card as first judged, not the one the hold rewrote; any other
    // verdict takes the card as it is now, since a re-run releases a RIGHT only for this snapshot's headline
    statements.push(db.prepare(`
      INSERT INTO card_verdicts (news_id, scrip_code, event_category, verdict, note, held, card_json_snapshot, created_at)
      VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)
      ON CONFLICT (news_id) DO UPDATE SET verdict = excluded.verdict, note = excluded.note, held = excluded.held,
        card_json_snapshot = CASE WHEN card_verdicts.verdict = 'WRONG' AND excluded.verdict = 'WRONG'
                                  THEN card_verdicts.card_json_snapshot
                                  ELSE excluded.card_json_snapshot END,
        created_at = excluded.created_at`)
      .bind(body.news_id, card!.scrip_code, card!.event_category, verdict, note, before, card!.card_json, new Date().toISOString()));
  }
  if (card && held !== null) {
    const json = withOwnerHold(card.card_json, verdict === "WRONG" ? note : null);
    if (held !== heldNow || json !== card.card_json) {
      statements.push(db.prepare("UPDATE cards SET held = ?2, card_json = json(?3) WHERE news_id = ?1").bind(body.news_id, held, json));
    }
  }
  await db.batch(statements);
  // The homepage's first page is the pipeline's R2 snapshot, rebuilt after every run: drop it so a card held or
  // released shows so now rather than after the next run (the feed reads D1 until then).
  if (held !== null && held !== heldNow) await c.env.VAULT.delete(SNAPSHOT_KEY).catch(() => undefined);
  return c.json({ ok: true, held: held ?? heldNow });
});

// The owner's verdicts, newest first, with the card's headline (the System page lists the latest).
owner.get("/verdicts", async (c) => {
  const { results } = await c.env.DB.prepare(`
    SELECT v.news_id, v.verdict, v.note, v.held, v.created_at, v.event_category,
           coalesce(c.symbol, v.scrip_code) AS symbol, c.held AS held_now,
           coalesce(c.headline, json_extract(v.card_json_snapshot, '$.headline')) AS headline
      FROM card_verdicts v LEFT JOIN cards c ON c.news_id = v.news_id
     ORDER BY v.created_at DESC LIMIT 1000`).all();
  return c.json({ verdicts: results });
});

owner.get("/feedback", async (c) => {
  const { results } = await c.env.DB.prepare(
    "SELECT news_id, rating FROM card_feedback ORDER BY created_at DESC LIMIT 500").all();
  return c.json({ ratings: results });
});
