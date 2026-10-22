const inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

export function cr(value: number | null | undefined): string {
  if (value == null) return "—";
  const sign = value < 0 ? "−" : "";
  const v = Math.abs(value);
  // ₹1,00,000 Cr and above reads better the way Indian markets say it: "₹12.5 lakh Cr".
  if (v >= 100000) return `${sign}₹${(v / 100000).toFixed(v >= 1000000 ? 1 : 2).replace(/\.?0+$/, "")} lakh Cr`;
  return `${sign}₹${v >= 100 ? inr0.format(v) : inr2.format(v)} Cr`;
}

export function rupees(value: number | null | undefined): string {
  return value == null ? "—" : `₹${inr2.format(value)}`;
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

const precise = new Intl.NumberFormat("en-IN", { maximumSignificantDigits: 8 });

/** Exact value, for showing the inputs of a calculation. */
export function exact(value: number | null | undefined): string {
  return value == null ? "—" : precise.format(value);
}

export function num(value: number | null | undefined): string {
  return value == null ? "—" : inr2.format(value);
}

const IST = "Asia/Kolkata";

export function istDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    timeZone: IST, day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

export function istDate(iso: string): string {
  return new Date(iso.length === 10 ? `${iso}T00:00:00+05:30` : iso).toLocaleDateString("en-IN", {
    timeZone: IST, day: "2-digit", month: "short", year: "numeric",
  });
}

export function todayIST(): string {
  return new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10);
}

export function addDays(day: string, days: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function relativeTime(iso: string): string {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

const ACRONYMS = new Set([
  "agm", "egm", "kpi", "ebitda", "ebit", "pat", "pbt", "eps", "nim", "gnpa", "nnpa", "casa", "aum", "arpu", "pcr",
  "crar", "roe", "roa", "usfda", "fda", "qip", "ncd", "ip", "yoy", "qoq", "mtpa", "tpd", "gst", "sebi", "bse", "nse", "msme",
]);

export function titleCase(text: string): string {
  return text
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b[a-z0-9]+\b/g, (w) => (ACRONYMS.has(w) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1)));
}

export function signClass(value: number | null | undefined): string {
  if (value == null || value === 0) return "text-ink-3";
  return value > 0 ? "text-pos" : "text-neg";
}

/** A company page's address: its NSE symbol (owner, 2026-10-21: "why are we using BSE numbers on NSE site"), else
 *  its key for a company with no symbol stored. The Worker takes either. */
export const companyPath = (c: { symbol?: string | null; scrip_code: string }) =>
  `/company/${encodeURIComponent(c.symbol || c.scrip_code)}`;

/** How a company's listing is shown: its NSE symbol (owner, 2026-10-19: everything on NSE), else its key. */
export const listing = (symbol: string | null | undefined, key: string | null | undefined) =>
  symbol ? `NSE: ${symbol}` : (key ?? "");

/** NSE cash-market trading holidays (NSE holiday-master, measured 2026-10-22); the pipeline keeps the same list
 *  (timeutil.NSE_HOLIDAYS). A year not listed counts its weekdays as trading days. */
export const NSE_HOLIDAYS = new Set([
  "2026-01-15", "2026-01-26", "2026-02-15", "2026-03-03", "2026-03-21", "2026-03-26", "2026-03-31", "2026-04-03",
  "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26", "2026-08-15", "2026-09-14", "2026-10-02", "2026-10-20",
  "2026-11-08", "2026-11-10", "2026-11-24", "2026-12-25",
]);

/** NSE cash-market session for a timestamp: a weekend or an exchange holiday is a non-trading day. */
export function marketSession(iso: string): "Pre-market" | "Market hours" | "Post-market" | "Non-trading day" {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: IST, weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false,
    year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date(iso));
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  const day = `${get("year")}-${get("month")}-${get("day")}`;
  if (["Sat", "Sun"].includes(get("weekday")) || NSE_HOLIDAYS.has(day)) return "Non-trading day";
  const minutes = Number(get("hour")) * 60 + Number(get("minute"));
  if (minutes < 9 * 60 + 15) return "Pre-market";
  if (minutes <= 15 * 60 + 30) return "Market hours";
  return "Post-market";
}

export function quantValue(value: number | null | undefined, unit: string): string {
  if (value == null) return "—";
  switch (unit.toUpperCase()) {
    case "INR_CR":
      return cr(value);
    case "PCT":
      return `${num(value)}%`;
    case "BPS":
      return `${Math.round(value)} bps`;
    case "INR":
      return rupees(value);
    default:
      return `${num(value)}${unit ? ` ${unit.toLowerCase()}` : ""}`;
  }
}

/** A sector footer figure in the unit its label promises (the pipeline has checked the unit). */
export function formatKpi(k: { format: string; value: number }): string {
  const v = k.value;
  switch (k.format) {
    case "pct": return `${v.toFixed(Math.abs(v) < 10 ? 2 : 1)}%`;
    case "cr": return cr(v);
    case "inr": return `₹${v.toLocaleString("en-IN", { maximumFractionDigits: Math.abs(v) < 100 ? 2 : 0 })}`;
    case "usd": return `$${v.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
    case "x": return `${v.toFixed(2)}x`;
    default: return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
  }
}
