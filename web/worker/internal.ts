// Token-protected API used by the pipeline runner. It can only execute the
// whitelisted SQL files in ../db and touch whitelisted R2 prefixes, so a
// leaked INGEST_TOKEN cannot run arbitrary SQL or read other objects.
import { Hono, type MiddlewareHandler } from "hono";
import { bearerAuth } from "hono/bearer-auth";
import { aiChatCompletions } from "./ai";
import type { AppEnv } from "./env";
import { QUERIES, STATEMENTS } from "./sql";

const MAX_BODY_BYTES = 1_000_000;
// raw/: every BSE and NSE answer as received (pipeline raw.py, D28); refused until 2026-10-17, so none was kept.
// evidence/: each card's raw model reply, for audits (pipeline _save_evidence; R2 only, no D1 row).
// text/: each filing's extracted text for 6 months (pipeline _cache_text, F147; an R2 lifecycle rule deletes it).
const OBJECT_PREFIXES = ["memory/", "daily_feed/", "backup/", "noise/", "meta/", "learning/", "raw/", "chart/", "evidence/", "text/"];
const has = (table: Record<string, string>, key: string) => Object.hasOwn(table, key);

const allowedKey = (key: string) =>
  OBJECT_PREFIXES.some((p) => key.startsWith(p)) && !key.includes("..") && key.length < 512;

export const internal = new Hono<AppEnv>();

internal.use("*", async (c, next) => {
  if (!c.env.INGEST_TOKEN) return c.json({ error: "INGEST_TOKEN is not configured" }, 503);
  // bearerAuth compares tokens in constant time.
  const auth: MiddlewareHandler<AppEnv> = bearerAuth({ token: c.env.INGEST_TOKEN });
  return auth(c, next);
});

// Run one write statement over a JSON array of rows. The body is bound as-is
// (never parsed here), which keeps CPU time flat regardless of batch size.
internal.post("/exec/:statement", async (c) => {
  const name = c.req.param("statement");
  if (!has(STATEMENTS, name)) return c.json({ error: "unknown statement" }, 404);
  // The cap is in bytes: a declared length over it is refused unread, and the text is measured as UTF-8, since
  // body.length counted UTF-16 units and let a body of Devanagari or ₹ signs through at up to three times the cap
  // (survey, 24 Oct 2026)
  const declared = Number(c.req.header("Content-Length") ?? "");
  if (declared > MAX_BODY_BYTES) return c.json({ error: "payload too large" }, 413);
  const body = await c.req.text();
  if (body.length > MAX_BODY_BYTES || new TextEncoder().encode(body).byteLength > MAX_BODY_BYTES) {
    return c.json({ error: "payload too large" }, 413);
  }
  if (!body.startsWith("[")) return c.json({ error: "body must be a JSON array" }, 400);
  try {
    const result = await c.env.DB.prepare(STATEMENTS[name]).bind(body).run();
    return c.json({ rows_written: result.meta.rows_written ?? result.meta.changes ?? 0 });
  } catch (err) {
    // A constraint or a malformed row will fail the same way again: 400 tells the pipeline not to
    // retry, and to find the bad row instead. Anything else stays a retryable 500.
    const message = String((err as Error)?.message ?? err);
    if (/constraint|malformed|datatype mismatch|too big|JSON/i.test(message)) return c.json({ error: message.slice(0, 300) }, 400);
    throw err;
  }
});

internal.post("/query/:name", async (c) => {
  const name = c.req.param("name");
  if (!has(QUERIES, name)) return c.json({ error: "unknown query" }, 404);
  const { params = [] } = await c.req.json<{ params?: unknown[] }>().catch(() => ({ params: undefined as unknown as unknown[] }));
  if (!Array.isArray(params) || params.length > 20) return c.json({ error: "bad params" }, 400);
  const { results } = await c.env.DB.prepare(QUERIES[name]).bind(...params.map((p) => p ?? null)).all();
  return c.json({ rows: results });
});

internal.get("/objects", async (c) => {
  const prefix = c.req.query("prefix") ?? "";
  if (!allowedKey(prefix)) return c.json({ error: "prefix not allowed" }, 403);
  const listing = await c.env.VAULT.list({ prefix, cursor: c.req.query("cursor") || undefined, limit: 1000 });
  return c.json({ keys: listing.objects.map((o) => o.key), cursor: listing.truncated ? listing.cursor : null });
});

// Hono has already decoded the path parameter; decoding again would mangle keys containing "%".
internal.get("/objects/:key{.+}", async (c) => {
  const key = c.req.param("key");
  if (!allowedKey(key)) return c.json({ error: "key not allowed" }, 403);
  const object = await c.env.VAULT.get(key);
  if (!object) return c.json({ error: "not found" }, 404);
  return new Response(object.body, {
    headers: { "Content-Type": object.httpMetadata?.contentType ?? "application/octet-stream" },
  });
});

internal.put("/objects/:key{.+}", async (c) => {
  const key = c.req.param("key");
  if (!allowedKey(key)) return c.json({ error: "key not allowed" }, 403);
  const body = await c.req.arrayBuffer();
  await c.env.VAULT.put(key, body, {
    httpMetadata: { contentType: c.req.header("Content-Type") ?? "application/json" },
  });
  return c.json({ ok: true, bytes: body.byteLength });
});

// OpenAI-compatible endpoint over the Workers AI binding: the gateway's spare.
internal.post("/ai/v1/chat/completions", aiChatCompletions);
