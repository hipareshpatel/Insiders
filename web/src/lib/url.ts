import { useCallback, useMemo } from "react";
import { useLocation, useSearch } from "wouter";

/** URL search params as state, so every filter, drawer and card is linkable. */
export function useQueryState() {
  const search = useSearch();
  const [location, navigate] = useLocation();
  const params = useMemo(() => new URLSearchParams(search), [search]);
  const update = useCallback(
    (changes: Record<string, string | null | undefined>, opts: { path?: string; replace?: boolean } = {}) => {
      const next = new URLSearchParams(opts.path && opts.path !== location ? "" : search);
      for (const [key, value] of Object.entries(changes)) {
        if (value === null || value === undefined || value === "") next.delete(key);
        else next.set(key, value);
      }
      const qs = next.toString();
      const path = opts.path ?? location;
      navigate(qs ? `${path}?${qs}` : path, { replace: opts.replace ?? true });
    },
    [search, location, navigate],
  );
  return [params, update] as const;
}

export function toggleInList(list: string | null, value: string): string | null {
  const items = new Set((list ?? "").split(",").filter(Boolean));
  if (items.has(value)) items.delete(value);
  else items.add(value);
  return items.size ? [...items].join(",") : null;
}
