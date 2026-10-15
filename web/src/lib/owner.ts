import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useSyncExternalStore } from "react";

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
  watch: (token: string, scrip: string, on: boolean) =>
    call<{ ok: boolean }>(token, "/watchlist", { method: "POST", body: JSON.stringify({ scrip_code: scrip, on }) }),
  rate: (token: string, newsId: string, rating: "STARRED" | "NOISE" | "CLEAR") =>
    call<{ ok: boolean }>(token, "/feedback", { method: "POST", body: JSON.stringify({ news_id: newsId, rating }) }),
  requeue: (token: string, newsId: string) =>
    call<{ ok: boolean }>(token, "/requeue", { method: "POST", body: JSON.stringify({ news_id: newsId }) }),
  ratings: (token: string) => call<{ ratings: { news_id: string; rating: string }[] }>(token, "/feedback"),
};

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
