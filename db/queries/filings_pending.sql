-- ?1 = from date, ?2 = to date (YYYY-MM-DD, inclusive), ?3 = max attempts, ?4 = limit,
-- ?5 = minimum market cap in ₹ Cr (NULL for no filter; companies without a market cap yet always qualify).
-- Oldest first, so dossier memory is built in chronological order. The market-cap filter is per
-- company, so it never reorders one company's filings.
SELECT f.news_id, f.scrip_code, f.company_name, f.headline, f.category, f.subcategory, f.filed_at,
       f.filing_date, f.pdf_url, f.status, f.route, f.event_type, f.reason, f.attempts
  FROM filings f
  LEFT JOIN companies c ON c.scrip_code = f.scrip_code
 WHERE (f.status = 'PENDING' OR (f.status = 'FAILED' AND f.attempts < ?3))
   AND f.filing_date BETWEEN ?1 AND ?2
   AND (?5 IS NULL OR c.market_cap_cr IS NULL OR c.market_cap_cr >= ?5)
 ORDER BY f.filed_at ASC, f.news_id ASC
 LIMIT ?4;
