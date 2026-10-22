import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useSyncExternalStore } from "react";
import type { CardRow, FeedResponse, ReviewCard, SystemResponse } from "../../shared/types";
import type { FeedFilters } from "./api";

/** The owner's verdict on a card, in the blind audit's own words. */
export type Verdict = "RIGHT" | "MINOR" | "WRONG";

// The owner's token for the few writes the site allows (watchlist, Star/Noise). Kept in this
// browser only; anyone else sees the site read-only.
const KEY = "owner-token";
const listeners = new Set<() => void>();

function read(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setOwnerToken(token: string | null) {
  try {
    if (token) localStorage.setItem(KEY, token);
    else localStorage.removeItem(KEY);
  } catch {
    /* private mode */
  }
  listeners.forEach((l) => l());
}

export function useOwnerToken(): string | null {
  return useSyncExternalStore((l) => { listeners.add(l); return () => listeners.delete(l); }, read, () => null);
}

async function call<T>(token: string, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/owner${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const ownerApi = {
  check: (token: string) => call<{ ok: boolean }>(token, "/check"),
  system: (token: string) => call<SystemResponse>(token, "/system"),
  watch: (token: string, scrip: string, on: boolean) =>
    call<{ ok: boolean }>(token, "/watchlist", { method: "POST", body: JSON.stringify({ scrip_code: scrip, on }) }),
  rate: (token: string, newsId: string, rating: "STARRED" | "NOISE" | "CLEAR") =>
    call<{ ok: boolean }>(token, "/feedback", { method: "POST", body: JSON.stringify({ news_id: newsId, rating }) }),
  requeue: (token: string, newsId: string) =>
    call<{ ok: boolean }>(token, "/requeue", { method: "POST", body: JSON.stringify({ news_id: newsId }) }),
  ratings: (token: string) => call<{ ratings: { news_id: string; rating: string }[] }>(token, "/feedback"),
  /** The feed with the cards held back from the public (private launch); held=only lists just those. */
  feedPage: (token: string, filters: FeedFilters, page: number, limit = 50) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries({ ...filters, page, limit })) if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    return call<FeedResponse>(token, `/feed?${qs.toString()}`);
  },
  verdict: (token: string, newsId: string, verdict: Verdict | "CLEAR", note = "") =>
    call<{ ok: boolean; held: number }>(token, "/verdict", { method: "POST", body: JSON.stringify({ news_id: newsId, verdict, note }) }),
  card: (token: string, id: string) => call<CardRow>(token, `/cards/${encodeURIComponent(id)}`),
  review: (token: string) => call<{ cards: ReviewCard[]; total?: number }>(token, "/review"),
  verdicts: (token: string) => call<{ verdicts: OwnerVerdict[] }>(token, "/verdicts"),
};

/** One of the owner's verdicts as GET /verdicts lists it; held is the card's state before the owner's own hold. */
export interface OwnerVerdict {
  news_id: string;
  verdict: Verdict;
  note: string | null;
  held: number;
  held_now: number | null;
  created_at: string;
  event_category: string | null;
  symbol: string;
  headline: string | null;
}

/** The owner's Star/Noise ratings, keyed by card, and a setter that updates them optimistically. */
export function useRatings() {
  const token = useOwnerToken();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["ratings", token], enabled: !!token, staleTime: 300_000,
    queryFn: async () => Object.fromEntries((await ownerApi.ratings(token!)).ratings.map((r) => [r.news_id, r.rating])) as Record<string, string>,
  });
  const rate = useCallback(async (newsId: string, rating: "STARRED" | "NOISE") => {
    if (!token) return;
    const current = query.data?.[newsId];
    const next = current === rating ? "CLEAR" : rating;
    client.setQueryData(["ratings", token], { ...(query.data ?? {}), [newsId]: next === "CLEAR" ? undefined : next });
    await ownerApi.rate(token, newsId, next);
  }, [token, query.data, client]);
  return { token, ratings: query.data ?? {}, rate };
}

/** The owner's RIGHT / MINOR / WRONG verdicts with notes, keyed by card, and a setter (same verdict again clears it).
 * A verdict holds or releases the card (WRONG holds it, RIGHT publishes it), so a changed verdict reloads the cards. */
export function useVerdicts() {
  const token = useOwnerToken();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["verdicts", token], enabled: !!token, staleTime: 300_000,
    queryFn: async () => Object.fromEntries((await ownerApi.verdicts(token!)).verdicts.map((v) => [v.news_id, { verdict: v.verdict, note: v.note ?? "" }])) as Record<string, { verdict: Verdict; note: string }>,
  });
  const judge = useCallback(async (newsId: string, verdict: Verdict | "CLEAR", note = ""): Promise<string | null> => {
    if (!token) return "not signed in";
    const next = { ...(query.data ?? {}) };
    const changed = next[newsId]?.verdict !== (verdict === "CLEAR" ? undefined : verdict);
    if (verdict === "CLEAR") delete next[newsId];
    else next[newsId] = { verdict, note };
    const before = query.data;
    client.setQueryData(["verdicts", token], next);
    // a verdict the API refused (an expired token answers 401) must not look saved (deep audit F-14)
    try {
      await ownerApi.verdict(token, newsId, verdict, note);
    } catch (err) {
      client.setQueryData(["verdicts", token], before);
      return String((err as Error)?.message ?? err);
    }
    if (changed) {
      void client.invalidateQueries({ predicate: (q) => ["feed", "card", "review", "verdict-list"].includes(String(q.queryKey[0])) });
    }
    return null;
  }, [token, query.data, client]);
  return { token, verdicts: query.data ?? {}, judge };
}
