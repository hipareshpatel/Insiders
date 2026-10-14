-- ?1 = JSON array of {key, value, updated_at}.
INSERT INTO kv (key, value, updated_at)
SELECT json_extract(value, '$.key'), json_extract(value, '$.value'), json_extract(value, '$.updated_at')
FROM json_each(?1)
WHERE true
ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
