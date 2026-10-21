-- ?1 = filing date. News ids already in the ledger for one day, so discovery can stop paging BSE
-- once it reaches filings it has seen (index idx_filings_date), with each one's attachment, so a filing the exchange
-- now serves with another file is read again (filings_discover.sql).
SELECT news_id, pdf_url FROM filings WHERE filing_date = ?1;
