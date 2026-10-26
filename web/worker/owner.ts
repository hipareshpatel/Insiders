// The owner's few writes from the website: star a company (watchlist) and rate a card as a
// signal or as noise (blueprint Loop 3, the golden set the prompts learn from). Protected by a
// separate OWNER_TOKEN secret, which the browser keeps in localStorage after the owner enters it.
import { Hono, type MiddlewareHandler } from "hono";
import { bearerAuth } from "hono/bearer-auth";
import type { AppEnv } from "./env";
import { withOwnerHold } from "../shared/ownerHold";
import { cardChecks, parseCheckInput, type IssueRow } from "../shared/cardChecks";
import { cardById, feed, isCompanyKey, reviewQueue, SNAPSHOT_KEY, systemStatus } from "./public";

export const owner = new Hono<AppEnv>();

owner.use("*", async (c, next) => {
  if (!c.env.OWNER_TOKEN) return c.json({ error: "OWNER_TOKEN is not configured" }, 503);
  const auth: MiddlewareHandler<AppEnv> = bearerAuth({ token: c.env.OWNER_TOKEN });
  return auth(c, next);
});

owner.get("/check", (c) => c.json({ ok: true }));

// the whole System page (owner, 22 Oct 2026: owner only); never cached at the edge
owner.get("/system", async (c) => c.json(await systemStatus(c), 200, { "Cache-Control": "private, no-store" }));

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

// Which card has which issue (owner TODO row 67). One indexed read of the cards in a date range, newest first, with the
// owner's verdict joined by its primary key, and only the grounding and review parts of the card JSON (the evidence
// block is cut out in SQL). The WHERE keeps cards that might have an item; cardChecks then names the types exactly.
// Paged by a (filed_at, news_id) cursor like the feed, so a deep page re-reads nothing above it.
const ISSUE_LIMIT = 200;
const GROUNDING_KEYS = ["unit_fixes", "change_fixes", "one_basis", "footer_hidden", "call_figure_conflicts", "quotes_dropped"];
owner.get("/issues", async (c) => {
  const q = c.req.query();
  const day = (s: string | undefined) => (s && /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : null);
  const from = day(q.from) ?? new Date(Date.now() - 7 * 86400_000).toISOString().slice(0, 10);
  const to = day(q.to) ?? "2999-12-31";
  const limit = Math.min(Math.max(Number.parseInt(q.limit ?? "", 10) || 100, 1), ISSUE_LIMIT);
  const [cursorAt, cursorId] = (q.cursor ?? "").split("|");
  const upper = cursorAt && cursorAt < `${to}T99` ? cursorAt : `${to}T99`;   // filed_at is "YYYY-MM-DDTHH:MM:SS+05:30"
  const params: unknown[] = [from, upper];
  const cursor = cursorAt ? (params.push(cursorAt, cursorId ?? ""), "AND (c.filed_at, c.news_id) < (?3, ?4)") : "";
  const sql = `
    SELECT c.news_id, c.scrip_code, c.symbol, c.company_name, c.filing_date, c.filed_at, c.event_category, c.headline,
           c.held, c.needs_review, v.verdict, v.note,
           json_object('grounding', json(json_remove(json_extract(c.card_json, '$.grounding'), '$.evidence')),
                       'review', json(json_extract(c.card_json, '$.review'))) AS checks
      FROM cards c LEFT JOIN card_verdicts v ON v.news_id = c.news_id
     WHERE c.filed_at >= ?1 AND c.filed_at <= ?2 ${cursor}
       AND (c.held = 1 OR c.needs_review = 1 OR v.verdict IN ('WRONG', 'MINOR')
            OR json_extract(c.card_json, '$.review') IS NOT NULL
            OR json_array_length(c.card_json, '$.grounding.unsupported_claims') > 0
            OR json_array_length(c.card_json, '$.grounding.ungrounded') > 0
            ${GROUNDING_KEYS.map((k) => `OR json_extract(c.card_json, '$.grounding.${k}') IS NOT NULL`).join("\n            ")})
     ORDER BY c.filed_at DESC, c.news_id DESC LIMIT ${limit + 1}`;
  const { results } = await c.env.DB.prepare(sql).bind(...params).all<Record<string, unknown>>();
  const page = results.slice(0, limit);
  const rows: IssueRow[] = [];
  for (const r of page) {
    const checks = cardChecks(parseCheckInput(r.checks as string), { held: r.held as number, needs_review: r.needs_review as number },
      r.verdict ? { verdict: r.verdict as string, note: r.note as string | null } : null);
    if (!checks.types.length) continue;
    rows.push({ news_id: r.news_id as string, filed_at: r.filed_at as string, filing_date: r.filing_date as string,
      scrip_code: r.scrip_code as string, symbol: (r.symbol as string | null) ?? null, company_name: r.company_name as string,
      event_category: r.event_category as string, headline: r.headline as string, types: checks.types,
      reasons: checks.groups.filter((g) => g.key !== "unconfirmed").flatMap((g) => g.items).slice(0, 3) });
  }
  const last = page[page.length - 1];
  const more = results.length > limit && last;
  return c.json({ rows, next_cursor: more ? `${last.filed_at}|${last.news_id}` : null, from, to, scanned: page.length },
    200, { "Cache-Control": "private, no-store" });
});
