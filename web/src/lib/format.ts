const inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

export function cr(value: number | null | undefined): string {
  if (value == null) return "—";
  return `₹${Math.abs(value) >= 100 ? inr0.format(value) : inr2.format(value)} Cr`;
}

export function rupees(value: number | null | undefined): string {
  return value == null ? "—" : `₹${inr2.format(value)}`;
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
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
