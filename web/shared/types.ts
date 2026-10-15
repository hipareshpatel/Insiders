// API contract shared by the Worker (worker/) and the React app (src/).
// Card shapes mirror the pipeline's pydantic models (pipeline/src/bse_intel/models.py).

export type Impact = "HIGH" | "MODERATE" | "LOW";
export type SizeCategory = "LARGE" | "MID" | "SMALL" | "MICRO";
export type Severity = "POSITIVE" | "WARNING" | "INFO";

export interface Insight {
  text: string;
  basis: "MEMORY" | "BALANCE_SHEET" | "FILING" | "SECTOR";
  memory_refs: string[];
}

export interface KeyNumber {
  label: string;
  value: string;
  change?: string | null;
}

export interface NotableChange {
  metric: string;
  previous?: string | null;
  current?: string | null;
  change?: string | null;
  direction: "POSITIVE" | "NEGATIVE" | "NEUTRAL";
  why: string;
}

export interface Signal {
  type: "PROMISE_DELIVERED" | "GUIDANCE_BREACH" | "WATCH_RESOLVED" | "DILUTION" | "SCALE" | "ORDER_FLOW" | "WORKING_CAPITAL_STRAIN" | "METRIC_SHIFT"
    | "BOARD_DELIBERATION" | "REG30_THRESHOLD" | "PREDICTION_RESOLVED" | "OWNERSHIP_SHIFT" | "AUDIT_FLAG"
    | "VOLUME_STREAK" | "QUARTER_PREVIEW" | "LOW_QUALITY_BEAT" | "MARGIN_MIX" | "JAWS" | "LOW_CASH_TAX" | "Q4_TRUE_UP"
    | "RECURRING_ONE_OFFS" | "DEBT_CASH_PARADOX" | "DISTRESS" | "RATING_LIQUIDITY" | "FESTIVE_SEASON" | "ASSET_TURN";
  severity: Severity;
  text: string;
  ref?: string | null;
}

export interface TrackNext {
  milestones: { what: string; when?: string | null; date?: string | null }[];
  kpis_to_verify: { kpi: string; check_in?: string | null; target?: string | null }[];
  pending_approvals: string[];
  catalysts?: string[];
  risks: string[];
}

export interface QuantInput {
  name: string;
  value: number | null;
  unit: string;
  source: "FILING" | "MEMORY" | "ASSUMPTION";
  note: string;
}

export interface QuantifiedImpact {
  label: string;
  formula: string;
  inputs: QuantInput[];
  result: number | null;
  unit: string;
  interpretation: string;
  check: "VERIFIED" | "MISMATCH" | "UNCHECKED";
  computed: number | null;
  check_note?: string;
  unsourced_inputs: string[];
}

export interface Fundamentals {
  revenue?: { period: string | null; value: number };
  debt?: { period: string | null; value: number };
  net_worth?: { period: string | null; value: number };
  gnpa_pct?: { period: string | null; value: number };
  nim_pct?: { period: string | null; value: number };
  /** The sector's footer figures (GNPA for a bank, EBITDA/t for cement, ARPU for telecom...). */
  kpis?: { label: string; format: "pct" | "cr" | "inr" | "x" | "usd" | "num"; period: string | null; value: number }[];
}

export interface ResultLine {
  value: number;
  prev_year?: number;
  prev_quarter?: number;
  yoy_pct?: number;
  qoq_pct?: number;
  yoy_bps?: number;
  qoq_bps?: number;
}

export interface ResultsSnapshot {
  period: string;
  prev_year_period?: string | null;
  prev_quarter_period?: string | null;
  revenue?: ResultLine;
  ebitda?: ResultLine;
  ebitda_margin?: ResultLine;
  pbt?: ResultLine;
  pat?: ResultLine;
  eps?: ResultLine;
}

export interface DealValue {
  kind: "ORDER" | "FUNDRAISE" | "CAPEX" | "ACQUISITION" | "DIVESTMENT" | "OTHER";
  amount_cr: number | null;
  includes_gst?: boolean | null;
  counterparty?: string | null;
  stage: string;
  segment?: string | null;
  execution_by?: string | null;
  progress?: string | null;
  updates_deal_id?: string | null;
}

export interface CallRead {
  guidance: "RAISED" | "LOWERED" | "MAINTAINED" | "NEW" | "WITHDRAWN" | "NONE";
  management_tone: "OPTIMISTIC" | "NEUTRAL" | "CAUTIOUS";
  transparency: "HIGH" | "MEDIUM" | "LOW";
  story?: string | null;
}

export interface CardBody {
  category_tag: string;
  event_type: string;
  impact_level: Impact;
  tone?: "POSITIVE" | "NEGATIVE" | "MIXED" | "NEUTRAL";
  headline: string;
  takeaway?: string;
  score?: CardScore;
  model_impact?: Impact;
  /** One line naming the economic driver (blueprint "📌 Core catalyst"). */
  core_catalyst?: string | null;
  themes?: string[];
  basis?: "CONSOLIDATED" | "STANDALONE" | "PROFORMA" | null;
  deal_value?: DealValue | null;
  call_read?: CallRead | null;
  results?: ResultsSnapshot | null;
  what_happened: string[];
  why_it_matters: Insight[];
  missing_disclosures: string[];
  key_numbers: KeyNumber[];
  notable_changes?: NotableChange[];
  track_next?: TrackNext;
  quantified_impact?: QuantifiedImpact[];
  fundamentals?: Fundamentals;
  pdf_pages?: number | null;
  signals: Signal[];
  timeline_entry: string;
  grounding: { score: number; checked: number; ungrounded: string[]; math_mismatches?: number; unsupported_claims?: string[] };
  /** Set when the first draft failed the checks and a second AI was asked to correct it. */
  review?: {
    status: "CORRECTED" | "UNRESOLVED" | "UNCHECKED";
    first_model?: string;
    checked_by?: string;
    issues?: string[];
    fixed?: string[];
  } | null;
  model: string;
  /** Monthly business updates: the main volume metric over recent months, from memory at the filing. */
  volume_strip?: { metric: string; unit: string | null; months: { period: string; value: number; yoy_pct: number | null }[] } | null;
  /** Set when the results figures came from the filing's XBRL file. */
  xbrl?: { basis: string | null; period: string | null; figures: number } | null;
  /** Market data as it stood when the filing came out (stored price series, else recent data). */
  priced_at_filing?: { last_price?: number; price_date?: string; market_cap_cr?: number; ret_1w?: number; ret_1m?: number; point_in_time?: boolean } | null;
}

export interface CardRow {
  news_id: string;
  scrip_code: string;
  symbol: string | null;
  company_name: string;
  filing_date: string;
  filed_at: string;
  sector: string | null;
  event_category: string;
  impact_level: Impact;
  headline: string;
  grounding_score: number | null;
  needs_review: number;
  memory_complete: number;
  card_json: string;
  pdf_url: string | null;
  market_cap_cr: number | null;
  size_category: SizeCategory | null;
  last_price: number | null;
  ret_1w: number | null;
  ret_1m: number | null;
  ret_1y: number | null;
  market_session?: "LIVE_MARKET" | "PRE_MARKET" | "AFTER_MARKET" | "NON_TRADING" | null;
  actionability_score?: number;
  is_actionable_signal?: number;
  /** Loop 1: JSON PriceReaction, filled by the nightly post-mortem. */
  post_event_return_json?: string | null;
  median_turnover_cr?: number | null;
  credibility_score?: number | null;
  watchlist?: number;
  /** Techno-funda tags from the market-data job (JSON Technicals). */
  technicals_json?: string | null;
  former_names_json?: string | null;
  /** BSE trading group (A, B, T, XT, Z...); T, XT and Z trade to trade with tight circuits. */
  bse_group?: string | null;
}

export interface FeedResponse {
  cards: CardRow[];
  next_cursor: string | null;
  /** Present when the request asked for a page number. */
  page?: number;
  pages?: number;
  total?: number;
  total_capped?: boolean;
}

export interface BriefResponse {
  from_at: string;
  scanned: number;
  noise: number;
  cards: number;
  high: number;
  signals: number;
}

/** The deterministic 0-100 actionability score (blueprint §11), stored in card_json.score. */
export interface CardScore {
  total: number;
  impact: Impact;
  actionable: boolean;
  pillars: Record<string, number>;
  gates: { magnitude: boolean; inflection: boolean; price: boolean; clean: boolean };
  vetoes: string[];
  reasons: string[];
  credibility: number | null;
}

export interface NoiseRow {
  news_id: string;
  scrip_code: string;
  company_name: string;
  headline: string;
  category: string | null;
  subcategory: string | null;
  filed_at: string;
  status: string;
  reason: string | null;
  pdf_url: string | null;
}

export interface Company {
  scrip_code: string;
  symbol: string | null;
  company_name: string;
  isin: string | null;
  industry: string | null;
  sector: string | null;
  market_cap_cr: number | null;
  size_category: SizeCategory | null;
  last_price: number | null;
  price_date: string | null;
  ret_1w: number | null;
  ret_1m: number | null;
  ret_1y: number | null;
  card_count: number;
  last_card_at: string | null;
  watchlist?: number;
  /** Techno-funda tags from the market-data job (JSON Technicals). */
  technicals_json?: string | null;
  former_names_json?: string;
  credibility_score?: number | null;
  median_turnover_cr?: number | null;
  bse_group?: string | null;
  /** From the company's memory summary (written with each card). */
  open_promises?: number | null;
  active_capex?: number | null;
  latest_revenue?: string | null;   // JSON {period, value}
  latest_ebitda?: string | null;
  gross_debt_cr?: number | null;
  /** Loop 2: how this management's targets and dates usually turn out. */
  calibration_rule?: string | null;
}

export interface InflectionTrigger { kind: string; date: string; text: string }
export interface RadarCompany {
  scrip_code: string; symbol: string | null; company_name: string; sector: string | null;
  market_cap_cr: number | null; size_category: SizeCategory | null; credibility_score: number | null;
  watchlist: number | null; inflection_last_at: string; triggers: InflectionTrigger[]; active_capex: number;
}
export interface OverduePromise {
  id: string; statement: string; due: string | null; due_date: string; given_on: string | null; status: string;
  source_news_id: string | null; scrip_code: string; symbol: string | null; company_name: string;
  credibility_score: number | null; days_overdue: number;
}
export interface ReviewCard {
  news_id: string; scrip_code: string; symbol: string | null; company_name: string; filed_at: string;
  headline: string; event_category: string; grounding: string | null; review: string | null;
}

export interface CompaniesResponse {
  companies: Company[];
  next_offset: number | null;
}

export interface Guidance {
  id: string;
  statement: string;
  metric?: string | null;
  target?: string | null;
  due?: string | null;
  due_date?: string | null;
  source_type: string;
  given_on: string;
  source_news_id: string;
  status: string;
  status_history: { status: string; evidence: string; as_of: string; source_news_id: string }[];
}

export interface WatchItem {
  id: string;
  kind: "KPI" | "APPROVAL" | "CONCERN";
  text: string;
  /** For an analyst concern: what management said on the call. */
  response?: string | null;
  check_in?: string | null;
  target?: string | null;
  check_by?: string | null;
  created_on: string;
  source_news_id: string;
  status: string;
  status_history: { status: string; evidence: string; as_of: string }[];
}

export interface Dossier {
  schema_version: number;
  scrip_code: string;
  company_name: string;
  symbol?: string | null;
  industry?: string | null;
  sector?: string | null;
  business_summary?: { text: string; as_of: string; source_news_id: string } | null;
  financial_metrics: { metric: string; period: string; value: number; unit: string; yoy_pct?: number | null; qoq_pct?: number | null; as_of: string; source_news_id: string }[];
  segment_mix: { segment: string; period: string; revenue_cr?: number | null; share_pct?: number | null; as_of: string }[];
  balance_sheet: (Record<string, string | number | null> & { as_of: string })[];
  capital_actions?: { instrument: string; new_shares?: number | null; issue_price?: number | null; amount_cr?: number | null; as_of: string }[];
  guidance: Guidance[];
  watchlist?: WatchItem[];
  timeline: { id: string; date: string; event_type: string; impact_level: Impact | null; summary: string; news_id: string }[];
  upcoming_events: { event_type: string; date: string; description: string }[];
  deals?: DealRecord[];
  operating_notes?: { text: string; as_of: string; source_news_id: string }[];
  identity?: { former_names: string[]; entities: { name: string; type?: string | null; as_of: string }[] };
  ownership?: { period: string; promoter_pct?: number; pledge_pct?: number; fii_pct?: number; dii_pct?: number; retail_holders?: number; as_of: string }[];
  governance?: { auditor: { name?: string; opinion?: string; note?: string; change?: string; as_of: string } | null };
  predictions?: { id: string; kpi: string; metric: string; period: string; value: number; comparison: string;
    status: "OPEN" | "MET" | "MISSED"; actual?: number; created_on: string; resolved_on?: string }[];
  updated_at: string | null;
}

export interface DealRecord {
  id: string;
  kind: DealValue["kind"];
  amount_cr: number | null;
  stage: string;
  counterparty?: string | null;
  segment?: string | null;
  execution_by?: string | null;
  progress?: string | null;
  includes_gst?: boolean | null;
  as_of: string;
  updated_as_of?: string;
  source_news_id: string;
  history?: { stage: string; amount_cr: number | null; progress?: string | null; as_of: string; source_news_id: string }[];
}

export interface CompanyDetail {
  company: Company | null;
  cards: CardRow[];
  dossier: Dossier | null;
}

export interface SearchResponse {
  companies: Pick<Company, "scrip_code" | "symbol" | "company_name" | "sector" | "card_count">[];
  cards: Pick<CardRow, "news_id" | "scrip_code" | "company_name" | "headline" | "impact_level" | "filed_at">[];
}

export interface Catalyst {
  id: string;
  scrip_code: string;
  company_name: string | null;
  symbol: string | null;
  event_type: string;
  event_date: string;
  description: string | null;
  source_news_id: string | null;
}

export interface ProviderUsage {
  day: string;
  provider: string;
  model: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  failures: number;
  rate_limited: number;
  limit_rpd: number | null;
  limit_tpd: number | null;
  last_error: string | null;
  updated_at: string | null;
}

export interface PipelineRun {
  run_id: string;
  mode: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  stats_json: string | null;
  error: string | null;
}

export interface SystemResponse {
  today: string;
  ledger_today: { status: string; n: number }[];
  /** Counts stop at cap (shown as "1,000+"): an exact count would read every queued row. */
  queue: { pending: number; failed: number; cap?: number };
  cards_7d: { impact_level: Impact; n: number }[];
  backfill: {
    start: string; discovered_through: string | null; complete: boolean;
    companies_left?: number | null; companies_total?: number | null;
  };
  d1?: { writes_today: number; size_bytes: number | null };
  /** Companies Yahoo Finance had a price for at the last market-data run. */
  market_coverage?: { date: string; companies: number; priced: number; missing: number; missing_pct: number } | null;
  usage: ProviderUsage[];
  runs: PipelineRun[];
}

/** Loop 1 price reaction after a filing (blueprint §12.1). */
export interface ReactionPoint { date: string; return_pct: number; excess_pct?: number; rvol?: number }
export interface PriceReaction {
  day0: string;
  base_date: string;
  benchmark: string | null;
  t1?: ReactionPoint;
  t2?: ReactionPoint;
  t3?: ReactionPoint;
  t5?: ReactionPoint;
  complete: number;
  missed_alpha?: number;
}

/** Optional price-structure tags (blueprint §11.3); never part of the score. */
export interface Technicals { stage2?: boolean; vcp?: boolean; rs_pct?: number; clenow?: number; rvol?: number; as_of?: string | null }
