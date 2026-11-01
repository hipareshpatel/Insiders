/** A company's stored classification is NSE's own address from broad to narrow, one to four steps:
 *  "Healthcare > Pharmaceuticals & Biotechnology > Pharmaceuticals" (measured 30 Oct 2026 over 2,767 companies: 17 with one step, 35 with
 *  two, 1,403 with three, 1,170 with four, 142 with none). The Results page and the company page show it the same way, from this one
 *  function. No React here, so `node --test` runs the cases in industry.test.ts. */

export function industryParts(raw?: string | null): string[] {
  return (raw ?? "").split(/\s*>\s*/).map((p) => p.trim()).filter(Boolean);
}

/** The line under a company's name: the second step and the narrowest step ("Banks › Private Sector Bank", "Realty › Residential,
 *  Commercial Projects"). The first step is NSE's broadest sector ("Consumer Discretionary" for a property developer), which tells an
 *  investor less than the second. A company with one step shows it; with two, both; with none, null (the caller says "Unclassified"). */
export function industryLine(raw?: string | null): string | null {
  const parts = industryParts(raw);
  if (!parts.length) return null;
  if (parts.length === 1) return parts[0];
  if (parts.length === 2) return `${parts[0]} › ${parts[1]}`;
  return `${parts[1]} › ${parts[parts.length - 1]}`;
}
