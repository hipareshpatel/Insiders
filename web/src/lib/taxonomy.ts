import type { Impact, SizeCategory } from "../../shared/types";

export const EVENT_LABELS: Record<string, string> = {
  RESULTS: "Results",
  CONCALL_PRESENTATION: "Concall / IP",
  RIGHTS_ISSUE: "Rights",
  FUNDRAISE: "Fundraise",
  CAPEX: "Capex",
  M_AND_A: "M&A",
  ORDER_WIN: "Order win",
  MONTHLY_BUSINESS_UPDATE: "Business update",
  DEBT_RATINGS: "Ratings",
  CORPORATE_ACTION: "Corp action",
  GOVERNANCE: "Governance",
  MANAGEMENT_CHANGE: "Management",
  LITIGATION_REGULATORY: "Regulatory",
  PRODUCT_LAUNCH: "Launch",
  OTHER: "Other",
};

export const IMPACTS: Impact[] = ["HIGH", "MODERATE", "LOW"];
export const SIZES: SizeCategory[] = ["LARGE", "MID", "SMALL", "MICRO"];

export const IMPACT_STYLE: Record<Impact, string> = {
  HIGH: "bg-high-bg text-high border-high/30",
  MODERATE: "bg-moderate-bg text-moderate border-moderate/30",
  LOW: "bg-low-bg text-low border-low/30",
};

export const IMPACT_LABEL: Record<Impact, string> = {
  HIGH: "High impact",
  MODERATE: "Moderate",
  LOW: "Low",
};

/** Catalyst families for the calendar: colour by what the date means. */
export const CATALYST_FAMILIES: { key: string; label: string; types: string[]; className: string }[] = [
  { key: "corp", label: "Corporate actions", types: ["RECORD_DATE", "EX_DATE", "PAYMENT_DATE", "BUYBACK_OPEN", "BUYBACK_CLOSE"], className: "bg-info/12 text-info border-info/30" },
  { key: "meet", label: "Meetings", types: ["AGM", "EGM", "BOARD_MEETING"], className: "bg-[#7a5af8]/12 text-[#7a5af8] border-[#7a5af8]/30 dark:text-[#bdb4fe]" },
  { key: "rights", label: "Rights windows", types: ["RIGHTS_OPEN", "RIGHTS_CLOSE"], className: "bg-[#0e9384]/12 text-[#0e9384] border-[#0e9384]/30 dark:text-[#5fe9d0]" },
  { key: "exec", label: "Execution milestones", types: ["COMMISSIONING", "MILESTONE"], className: "bg-pos/12 text-pos border-pos/30" },
  { key: "account", label: "Accountability checks", types: ["KPI_CHECK", "GUIDANCE_DUE"], className: "bg-warn/12 text-warn border-warn/30" },
  { key: "other", label: "Other", types: ["OTHER"], className: "bg-low-bg text-low border-low/30" },
];

export function catalystFamily(type: string) {
  return CATALYST_FAMILIES.find((f) => f.types.includes(type)) ?? CATALYST_FAMILIES[CATALYST_FAMILIES.length - 1];
}
