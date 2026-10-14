import type {
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
  const url = qs.size ? `${path}?${qs}` : path;
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
}

export const api = {
  feed: (filters: FeedFilters, cursor?: string | null) =>
    get<FeedResponse>("/api/feed", { ...filters, cursor, limit: 20 }),
  card: (id: string) => get<CardRow>(`/api/cards/${encodeURIComponent(id)}`),
  noise: (date: string, offset = 0) =>
    get<{ rows: NoiseRow[]; next_offset: number | null }>("/api/noise", { date, offset }),
  search: (q: string) => get<SearchResponse>("/api/search", { q }),
  companies: (params: Record<string, string | number | null | undefined>) =>
    get<CompaniesResponse>("/api/companies", params),
  company: (scrip: string) => get<CompanyDetail>(`/api/companies/${encodeURIComponent(scrip)}`),
  calendar: (from: string, to: string) => get<{ events: Catalyst[] }>("/api/calendar", { from, to }),
  system: () => get<SystemResponse>("/api/system"),
};
