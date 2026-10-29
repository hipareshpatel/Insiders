// The PDF shadow job's token: read queries and its own R2 rows only (shared/shadowToken.ts). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { shadowAllowed } from "../shared/shadowToken.ts";

test("the shadow token reads cards and reads and writes its own rows", () => {
  assert.ok(shadowAllowed("POST", "/api/internal/query/export_cards"));
  assert.ok(shadowAllowed("GET", "/api/internal/objects/meta/pdf-shadow/2026-10-29.csv"));
  assert.ok(shadowAllowed("PUT", "/api/internal/objects/meta/pdf-shadow/2026-10-29.csv"));
});

test("the shadow token can never write a card, another object, delete or call the AI", () => {
  assert.ok(!shadowAllowed("POST", "/api/internal/exec/cards_upsert"));
  assert.ok(!shadowAllowed("POST", "/api/internal/exec/cards_delete"));
  assert.ok(!shadowAllowed("PUT", "/api/internal/objects/memory/RELIANCE.json"));
  assert.ok(!shadowAllowed("PUT", "/api/internal/objects/meta/other.json"));
  assert.ok(!shadowAllowed("PUT", "/api/internal/objects/meta/pdf-shadow/../memory/x.json"));
  assert.ok(!shadowAllowed("GET", "/api/internal/objects/evidence/x.json"));
  assert.ok(!shadowAllowed("GET", "/api/internal/objects"));
  assert.ok(!shadowAllowed("DELETE", "/api/internal/objects/meta/pdf-shadow/2026-10-29.csv"));
  assert.ok(!shadowAllowed("POST", "/api/internal/ai/v1/chat/completions"));
  assert.ok(!shadowAllowed("POST", "/api/internal/query/export_cards/x"));
});
