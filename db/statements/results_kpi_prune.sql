-- ?1 = JSON array of {scrip_code, periods: [..]} (results_table.py). Removes a company's rows for a quarter its statements no longer hold
-- (a corrected profit line, a quarter that fell out of the kept ten); a company not listed is untouched.
DELETE FROM results_kpi
 WHERE EXISTS (SELECT 1 FROM json_each(?1) AS j
                WHERE json_extract(j.value, '$.scrip_code') = results_kpi.scrip_code
                  AND results_kpi.period NOT IN (SELECT p.value FROM json_each(json_extract(j.value, '$.periods')) AS p));
