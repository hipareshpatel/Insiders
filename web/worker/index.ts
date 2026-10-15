import { Hono } from "hono";
import { HTTPException } from "hono/http-exception";
import type { AppEnv } from "./env";
import { internal } from "./internal";
import { api } from "./public";

const app = new Hono<AppEnv>();

app.route("/api/internal", internal);
app.route("/api", api);

app.notFound((c) =>
  c.req.path.startsWith("/api/") || !c.env.ASSETS ? c.json({ error: "not found" }, 404) : c.env.ASSETS.fetch(c.req.raw));

app.onError((err, c) => {
  if (err instanceof HTTPException) return err.getResponse();
  console.error(err);
  return c.json({ error: "internal error" }, 500);
});

export default app;
