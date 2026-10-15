-- ?1 = filing date. News ids already in the ledger for one day, so discovery can stop paging BSE
-- once it reaches filings it has seen (index idx_filings_date).
SELECT news_id FROM filings WHERE filing_date = ?1;
