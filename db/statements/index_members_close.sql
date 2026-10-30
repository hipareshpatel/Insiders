-- ?1 = JSON array of {index_id, isin, valid_to}: companies that left an index, on that day. Only an open stretch is closed.
UPDATE index_members
   SET valid_to = (SELECT json_extract(j.value, '$.valid_to') FROM json_each(?1) j
                    WHERE json_extract(j.value, '$.index_id') = index_members.index_id
                      AND json_extract(j.value, '$.isin') = index_members.isin LIMIT 1)
 WHERE valid_to IS NULL
   AND EXISTS (SELECT 1 FROM json_each(?1) j
                WHERE json_extract(j.value, '$.index_id') = index_members.index_id
                  AND json_extract(j.value, '$.isin') = index_members.isin);
