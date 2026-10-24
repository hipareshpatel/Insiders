-- ?1 = JSON array of {key, value, updated_at}: an integer added to the stored one in the database itself, so two jobs
-- ending together both count (the d1_writes counter was read, added to and written back, and the last writer won).
INSERT INTO kv (key, value, updated_at)
SELECT json_extract(value, '$.key'), CAST(json_extract(value, '$.value') AS TEXT), json_extract(value, '$.updated_at')
FROM json_each(?1)
WHERE true
-- (Nothing may follow the final semicolon: D1 reads it as a second statement and refuses parameters.)
ON CONFLICT (key) DO UPDATE SET value = CAST(coalesce(CAST(kv.value AS INTEGER), 0) + CAST(excluded.value AS INTEGER) AS TEXT),
                                updated_at = excluded.updated_at;
