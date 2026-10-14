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
  type: "PROMISE_DELIVERED" | "GUIDANCE_BREACH" | "WATCH_RESOLVED" | "DILUTION" | "WORKING_CAPITAL_STRAIN" | "METRIC_SHIFT";
  severity: Severity;
  text: string;
  ref?: string | null;
}

export interface TrackNext {
  milestones: { what: string; when?: string | null; date?: string | null }[];
  kpis_to_verify: { kpi: string; check_in?: string | null; target?: string | null }[];
  pending_approvals: string[];
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
}

export interface ResultsSnapshot {
  period: string;
  revenue?: { value: number; yoy_pct?: number };
  ebitda?: { value: number; yoy_pct?: number };
  ebitda_margin?: { value: number; yoy_bps?: number };
  pat?: { value: number; yoy_pct?: number };
}

export interface CardBody {
  category_tag: string;
  event_type: string;
  impact_level: Impact;
  tone?: "POSITIVE" | "NEGATIVE" | "MIXED" | "NEUTRAL";
  headline: string;
  takeaway?: string;
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
  grounding: { score: number; checked: number; ungrounded: string[]; math_mismatches?: number };
  model: string;
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
}

export interface FeedResponse {
  cards: CardRow[];
  next_cursor: string | null;
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
  kind: "KPI" | "APPROVAL";
  text: string;
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
  updated_at: string | null;
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
  queue: { pending: number; failed: number };
  cards_7d: { impact_level: Impact; n: number }[];
  backfill: { start: string; discovered_through: string | null; complete: boolean };
  usage: ProviderUsage[];
  runs: PipelineRun[];
}
