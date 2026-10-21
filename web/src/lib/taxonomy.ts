import type { Impact, SizeCategory } from "../../shared/types";

export const EVENT_LABELS: Record<string, string> = {
  RESULTS: "Results",
  CONCALL_PRESENTATION: "Concall / presentation",
  ANNUAL_REPORT: "Annual report",
  RIGHTS_ISSUE: "Rights issue",
  FUNDRAISE: "Fundraise",
  CAPEX: "Capex",
  M_AND_A: "M&A",
  ORDER_WIN: "Order win",
  MONTHLY_BUSINESS_UPDATE: "Business update",
  DEBT_RATINGS: "Credit rating",
  CORPORATE_ACTION: "Corporate action",
  GOVERNANCE: "Governance",
  MANAGEMENT_CHANGE: "Management",
  LITIGATION_REGULATORY: "Regulatory",
  PRODUCT_LAUNCH: "Launch",
  OTHER: "Update",
};

/** Feed tabs: each maps to API filters. */
export const FEED_TABS: { key: string; label: string; impact?: string; category?: string; turnaround?: string }[] = [
  { key: "all", label: "All filings" },
  { key: "high", label: "High impact", impact: "HIGH" },
  { key: "results", label: "Results", category: "RESULTS,CONCALL_PRESENTATION,ANNUAL_REPORT" },
  // a quarter's profit after a year-ago loss: not a signal (4 of 5 were a one-off reversing, 2026-10-21), so its own tab
  { key: "turnaround", label: "Turnarounds", category: "RESULTS", turnaround: "1" },
  { key: "growth", label: "Capex & orders", category: "CAPEX,ORDER_WIN,PRODUCT_LAUNCH,MONTHLY_BUSINESS_UPDATE" },
  { key: "capital", label: "Capital & deals", category: "RIGHTS_ISSUE,FUNDRAISE,M_AND_A,CORPORATE_ACTION,DEBT_RATINGS" },
  { key: "governance", label: "Governance & regulatory", category: "GOVERNANCE,MANAGEMENT_CHANGE,LITIGATION_REGULATORY" },
  { key: "noise", label: "Noise audit" },
];

export const IMPACT_LABEL: Record<Impact, string> = { HIGH: "High impact", MODERATE: "Medium impact", LOW: "Low impact" };
export const IMPACT_TEXT: Record<Impact, string> = { HIGH: "text-ink", MODERATE: "text-ink-2", LOW: "text-ink-3" };

export type Tone = "POSITIVE" | "NEGATIVE" | "MIXED" | "NEUTRAL";
export const TONE_STRIPE: Record<Tone, string> = {
  POSITIVE: "bg-pos",
  NEGATIVE: "bg-neg",
  MIXED: "bg-warn",
  NEUTRAL: "bg-neutral-stripe",
};
export const TONE_BORDER: Record<Tone, string> = {
  POSITIVE: "border-l-pos",
  NEGATIVE: "border-l-neg",
  MIXED: "border-l-warn",
  NEUTRAL: "border-l-neutral-stripe",
};
export const TONE_CHIP: Record<Tone, string> = {
  POSITIVE: "bg-pos-soft text-pos",
  NEGATIVE: "bg-neg-soft text-neg",
  MIXED: "bg-warn-soft text-warn",
  NEUTRAL: "bg-surface-2 text-ink-2",
};
export const TONE_LABEL: Record<Tone, string> = { POSITIVE: "Positive", NEGATIVE: "Negative", MIXED: "Mixed", NEUTRAL: "Neutral" };

/** Results verdict from tone and impact. */
export function verdict(tone: Tone, impact: Impact): { label: string; tone: Tone } {
  if (tone === "POSITIVE") return { label: impact === "HIGH" ? "Strong" : "Good", tone };
  if (tone === "NEGATIVE") return { label: "Weak", tone };
  if (tone === "MIXED") return { label: "Mixed", tone };
  return { label: "Neutral", tone };
}

export const SIZES: SizeCategory[] = ["LARGE", "MID", "SMALL", "MICRO"];

export const SECTORS: Record<string, string> = {
  nbfc: "NBFC & finance", banks: "Banks", insurance: "Insurance", it: "IT services", hospitals: "Hospitals", pharma: "Pharma & healthcare",
  auto: "Automobiles", auto_components: "Auto components", cement: "Cement", metals: "Metals & mining", fmcg: "FMCG",
  oil_gas: "Oil & gas", power: "Power & utilities", capital_goods: "Capital goods", construction: "Construction & infra",
  realty: "Real estate", consumer_durables: "Consumer durables", chemicals: "Chemicals", textiles: "Textiles",
  telecom: "Telecom", media: "Media", hotels: "Hotels", aviation: "Aviation", consumer_services: "Consumer services",
  sugar: "Sugar", default: "Other",
};

/** Catalyst families for the calendar: colour by what the date means. */
export const CATALYST_FAMILIES: { key: string; label: string; types: string[]; dot: string; chip: string }[] = [
  { key: "corp", label: "Corporate actions", types: ["RECORD_DATE", "EX_DATE", "PAYMENT_DATE", "BUYBACK_OPEN", "BUYBACK_CLOSE", "WARRANT_EXPIRY"], dot: "bg-info", chip: "bg-info-soft text-info" },
  { key: "meet", label: "Meetings", types: ["AGM", "EGM", "BOARD_MEETING"], dot: "bg-violet", chip: "bg-violet-soft text-violet" },
  { key: "rights", label: "Rights windows", types: ["RIGHTS_OPEN", "RIGHTS_CLOSE"], dot: "bg-teal", chip: "bg-teal-soft text-teal" },
  { key: "exec", label: "Execution milestones", types: ["COMMISSIONING", "MILESTONE"], dot: "bg-pos", chip: "bg-pos-soft text-pos" },
  { key: "account", label: "Accountability checks", types: ["KPI_CHECK", "GUIDANCE_DUE"], dot: "bg-warn", chip: "bg-warn-soft text-warn" },
  { key: "other", label: "Other", types: ["OTHER"], dot: "bg-ink-3", chip: "bg-surface-2 text-ink-2" },
];

/** A catalyst's line for people: the exchange's "X Ltd has informed BSE that the meeting of the Board of Directors ... to
 * consider ..." becomes "Board meeting: to consider the financial results" (design audit, 2026-10-20: the rail showed
 * "Newgen Software Technologies Ltdhas informed BSE th…"). */
export function catalystText(type: string, description: string | null | undefined): string {
  let text = (description ?? "").replace(/\s+/g, " ").trim();
  text = text.replace(/^.{0,120}?has\s+informed\s+(?:BSE|NSE|the\s+Exchanges?)\s+that\s+/i, "");
  if (type === "BOARD_MEETING") {
    const purpose = /\b(to\s+(?:consider|approve|discuss)\b.*)$/i.exec(text)?.[1];
    return purpose ? `Board meeting: ${purpose.replace(/[.;,]\s*$/, "")}` : "Board meeting";
  }
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
}

export function catalystFamily(type: string) {
  return CATALYST_FAMILIES.find((f) => f.types.includes(type)) ?? CATALYST_FAMILIES[CATALYST_FAMILIES.length - 1];
}
