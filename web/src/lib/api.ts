import type { KpiResponse } from "../../shared/resultsKpi";
import type { BriefResponse, CardRow, Catalyst, CompaniesResponse, CompanyDetail, FeedResponse, NoiseRow, OverduePromise, RadarCompany, ReviewCard, PublicSystemResponse, SearchResponse } from "../../shared/types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function get<T>(path: string, params?: Record<string, string | number | null | undefined>): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== null && v !== undefined && v !== "") qs.set(k, String(v));
  }
  const query = qs.toString(); // not qs.size: undefined on Safari 16, which would drop every filter
  const url = query ? `${path}?${query}` : path;
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface FeedFilters {
  from?: string;
  /** Since a moment, "YYYY-MM-DDTHH:MM:SS+05:30" (overrides from). */
  from_at?: string;
  to?: string;
  impact?: string;
  category?: string;
  size?: string;
  sector?: string;
  q?: string;
  review?: string;
  session?: string;
  watch?: string;
  /** "1": results cards whose PAT turned from a year-ago loss to a profit. */
  turnaround?: string;
  /** Owner feed only: "only" lists just the cards held back from the public. */
  held?: string;
}

export const api = {
  feed: (filters: FeedFilters, cursor?: string | null, limit = 20) =>
    get<FeedResponse>("/api/feed", { ...filters, cursor, limit }),
  feedPage: (filters: FeedFilters, page: number, limit = 50) =>
    get<FeedResponse>("/api/feed", { ...filters, page, limit }),
  /** The Results KPI report: filters and sort as shared/resultsKpi.ts parses them. */
  resultsKpi: (params: Record<string, string | number | null | undefined>) => get<KpiResponse>("/api/results-kpi", params),
  signals: (params: { from?: string; from_at?: string }) => get<{ cards: CardRow[] }>("/api/signals", params),
  brief: (fromAt: string) => get<BriefResponse>("/api/brief", { from_at: fromAt }),
  card: (id: string) => get<CardRow>(`/api/cards/${encodeURIComponent(id)}`),
  noise: (date: string, offset = 0) =>
    get<{ rows: NoiseRow[]; next_offset: number | null; rule_total: number }>("/api/noise", { date, offset }),
  search: (q: string) => get<SearchResponse>("/api/search", { q }),
  companies: (params: Record<string, string | number | null | undefined>) =>
    get<CompaniesResponse>("/api/companies", params),
  company: (scrip: string) => get<CompanyDetail>(`/api/companies/${encodeURIComponent(scrip)}`),
  calendar: (from: string, to: string) => get<{ events: Catalyst[] }>("/api/calendar", { from, to }),
  system: () => get<PublicSystemResponse>("/api/system"),
  radar: (min = 3) => get<{ since: string; min: number; companies: RadarCompany[] }>("/api/radar", { min }),
  overdue: () => get<{ today: string; promises: OverduePromise[] }>("/api/promises/overdue"),
  review: () => get<{ cards: ReviewCard[]; total?: number }>("/api/review"),
};
