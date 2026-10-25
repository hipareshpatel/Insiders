-- ?1 = JSON array of {scrip_code}. prune-companies --apply: the calendar rows of companies just removed from the master
-- (run after companies_prune: a company still in the master keeps its rows).
DELETE FROM catalysts
 WHERE scrip_code IN (SELECT json_extract(j.value, '$.scrip_code') FROM json_each(?1) AS j)
   AND NOT EXISTS (SELECT 1 FROM companies WHERE companies.scrip_code = catalysts.scrip_code);
