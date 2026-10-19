-- sync-to-cloud: pipeline state (backfill cursor and order, noise counts, live start), not the
-- per-day write counters, which belong to each database.
SELECT key, value, updated_at FROM kv WHERE key NOT LIKE 'd1_writes:%';
