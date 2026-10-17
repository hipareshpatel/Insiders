-- Recent cards from same-sector peers for the same event type (Pass 2 peer context). Held cards are left
-- out: one held for figures the checks could not verify must not shape another company's card.
-- ?1 = sector, ?2 = event category, ?3 = scrip code to exclude, ?4 = since, ?5 = until (filed_at), ?6 = limit.
SELECT scrip_code, company_name, filed_at, headline, impact_level
  FROM cards
 WHERE event_category = ?2
   AND held = 0
   AND sector = ?1
   AND scrip_code <> ?3
   AND filed_at >= ?4
   AND filed_at < ?5
 ORDER BY filed_at DESC
 LIMIT ?6;
