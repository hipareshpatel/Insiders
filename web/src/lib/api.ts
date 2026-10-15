import type {
  BriefResponse,
  CardRow,
  Catalyst,
  CompaniesResponse,
  CompanyDetail,
  FeedResponse,
  NoiseRow,
  SearchResponse,
  SystemResponse,
} from "../../shared/types";

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
  to?: string;
  impact?: string;
  category?: string;
  size?: string;
  sector?: string;
  q?: string;
  review?: string;
  session?: string;
  watch?: string;
}

export const api = {
  feed: (filters: FeedFilters, cursor?: string | null, limit = 20) =>
    get<FeedResponse>("/api/feed", { ...filters, cursor, limit }),
  feedPage: (filters: FeedFilters, page: number, limit = 50) =>
    get<FeedResponse>("/api/feed", { ...filters, page, limit }),
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
  system: () => get<SystemResponse>("/api/system"),
};
