// Which company keys the routes accept. No imports: the Worker uses it and `npm test` runs it under node.

// A company's key: its BSE scrip code; for a company never on BSE (a listing after the move to NSE, 2026-10-19) its
// NSE symbol ("TATATECH", "M&M", "BAJAJ-AUTO"); or "NSE:<symbol>", the key the pipeline stores for a company the
// master does not carry (nse.py, scrip_for falling back), which the company page and the watchlist refused until
// 24 Oct 2026 (survey, 24 Oct 2026)
export const isCompanyKey = (s: string | undefined | null) =>
  !!s && /^(\d{3,8}|(NSE:)?[A-Z0-9][A-Z0-9&-]{0,19})$/.test(s);
