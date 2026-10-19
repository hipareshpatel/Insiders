/** The company page's price chart: the range shown and where each analysed filing sits on it. No React here, so
 * `node --test` runs the cases in test/cardText.test.ts. */

export type Series = { d: string[]; c: number[] };
export const RANGES = { "1M": 21, "3M": 63, "6M": 125, "1Y": 250 } as const;   // trading days
export type Range = keyof typeof RANGES;

/** The last `sessions` trading days of the series (all of it when shorter). */
export function sliceRange(series: Series, range: Range): Series {
  const n = Math.min(series.d.length, series.c.length);
  const from = Math.max(0, n - RANGES[range]);
  return { d: series.d.slice(from, n), c: series.c.slice(from, n) };
}

/** Each filing at the first trading day on or after it (a filing after the close moves the next session's price),
 * inside the range only; several filings on one day share the day's point. */
export function placeFilings<T extends { filed_at: string }>(series: Series, filings: T[]): { index: number; items: T[] }[] {
  const out = new Map<number, T[]>();
  if (!series.d.length) return [];
  for (const f of filings) {
    const day = f.filed_at.slice(0, 10);
    if (day < series.d[0] || day > series.d[series.d.length - 1]) continue;
    let lo = 0, hi = series.d.length - 1;
    while (lo < hi) {   // the first date >= day
      const mid = (lo + hi) >> 1;
      if (series.d[mid] < day) lo = mid + 1; else hi = mid;
    }
    out.set(lo, [...(out.get(lo) ?? []), f]);
  }
  return [...out.entries()].sort((a, b) => a[0] - b[0]).map(([index, items]) => ({ index, items }));
}

/** The move over the range, in per cent; null when the first close is not positive. */
export function rangeMove(series: Series): number | null {
  const first = series.c[0], last = series.c[series.c.length - 1];
  return first > 0 && last != null ? (last / first - 1) * 100 : null;
}
