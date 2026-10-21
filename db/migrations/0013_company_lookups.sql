-- The company page looks a company up by its NSE symbol (the site's addresses since 2026-10-21) and its peers by sector;
-- with no index each view scanned the companies table twice (deep audit F-09). An index entry is rewritten only when
-- the symbol or the sector changes, which the daily market-data update does not do.
CREATE INDEX IF NOT EXISTS idx_companies_symbol ON companies (symbol);
CREATE INDEX IF NOT EXISTS idx_companies_sector_mcap ON companies (sector, market_cap_cr);
