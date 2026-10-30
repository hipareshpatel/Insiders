-- ?1 = JSON array of {index_id, as_of}: the indices just read in full. A row of such an index older than that day is a company that left it.
DELETE FROM index_members
 WHERE EXISTS (SELECT 1 FROM json_each(?1) j
                WHERE json_extract(j.value, '$.index_id') = index_members.index_id
                  AND index_members.as_of < json_extract(j.value, '$.as_of'));
