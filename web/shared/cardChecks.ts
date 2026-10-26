// What a card's stored data already says about its own checks, in plain English (owner TODO row 67: "how do I know
// which card is having which issues?"). Read by the Checks panel on a card and by the Worker's /api/owner/issues.
// No imports: the Worker uses it and `npm test` runs it under node.

export type IssueType = "corrected" | "held" | "unsupported" | "ungrounded" | "review" | "verdict_wrong" | "verdict_minor";

export const ISSUE_LABEL: Record<IssueType, string> = {
  corrected: "Corrected by code", held: "Held", unsupported: "Unsupported claim", ungrounded: "Ungrounded number",
  review: "Needs review", verdict_wrong: "Owner: Wrong", verdict_minor: "Owner: Minor",
};
export const ISSUE_TYPES = Object.keys(ISSUE_LABEL) as IssueType[];

// the line shared/ownerHold.ts writes into review.held for a Wrong verdict (copied: this file has no imports)
const OWNER_HOLD = "Held by the owner (Wrong): ";

export interface CheckGroup { key: "corrected" | "held" | "failed" | "unconfirmed" | "verdict"; title: string; items: string[] }
export interface CardChecks { groups: CheckGroup[]; types: IssueType[] }

/** The parts of the stored card JSON this reads (all optional: old cards lack most of them). */
export interface CheckInput {
  grounding?: Record<string, unknown> | null;
  review?: { status?: string; issues?: unknown; fixed?: unknown; held?: unknown; pruned?: unknown; checked_by?: string } | null;
}

/** Any stored note as one line: a string as it is, an object as its text or its "key: value" parts. */
export function noteText(x: unknown): string {
  if (x == null) return "";
  if (typeof x === "string") return x.trim();
  if (typeof x === "number" || typeof x === "boolean") return String(x);
  if (Array.isArray(x)) return x.map(noteText).filter(Boolean).join(", ");
  if (typeof x === "object") {
    const o = x as Record<string, unknown>;
    if (typeof o.text === "string") return o.text.trim();
    return Object.entries(o).map(([k, v]) => [k, noteText(v)] as const).filter(([, v]) => v)
      .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join("; ");
  }
  return "";
}
function list(x: unknown): string[] {
  if (x == null) return [];
  return (Array.isArray(x) ? x : [x]).map(noteText).filter(Boolean);
}

const CORRECTED_BY_CODE: [string, string][] = [
  ["unit_fixes", "Unit corrected"],
  ["change_fixes", "Change figure corrected"],
  ["one_basis", "One basis"],
  ["footer_hidden", "Footer figure hidden (cannot be right)"],
  ["call_figure_conflicts", "Call figure dropped (the company's own filing says otherwise)"],
  ["quotes_dropped", "Point dropped (its quote did not carry it)"],
];
const UNCONFIRMED: [string, string][] = [
  ["quotes_missing", "No quote found"],
  ["quotes_paraphrased", "Quote is a paraphrase"],
  ["out_of_fit", "Figure does not fit the statement's unit or column"],
  ["call_takeaways_unverified", "Call takeaway not verified"],
];

/** The card's checks from its stored JSON, the row's flags and the owner's verdict (RIGHT, MINOR or WRONG), if any. */
export function cardChecks(card: CheckInput | null | undefined, flags: { held?: number | boolean | null; needs_review?: number | boolean | null },
                           verdict?: { verdict?: string | null; note?: string | null } | null): CardChecks {
  const g = (card?.grounding ?? {}) as Record<string, unknown>;
  const r = card?.review ?? null;
  const groups: CheckGroup[] = [];
  const types: IssueType[] = [];
  const add = (key: CheckGroup["key"], title: string, items: string[], type?: IssueType) => {
    if (!items.length) return;
    groups.push({ key, title, items });
    if (type && !types.includes(type)) types.push(type);
  };

  const corrected = CORRECTED_BY_CODE.flatMap(([k, label]) => list(g[k]).map((t) => `${label}: ${t}`));
  if (r?.status === "CORRECTED") corrected.push(...list(r.fixed).map((t) => `Second AI fixed: ${t}`));
  if (r?.status === "PRUNED") corrected.push(...list(r.pruned).map((t) => `Point dropped (its quote did not carry it): ${t}`));
  add("corrected", "What our code corrected automatically", corrected, "corrected");

  const heldLines = list(r?.held);
  const checkLines = r?.status === "UNRESOLVED" || r?.status === "HELD" || r?.status === "UNCHECKED" ? list(r?.issues) : [];
  const ownerOnly = heldLines.length > 0 && heldLines.every((h) => h.startsWith(OWNER_HOLD)) && !checkLines.length;
  const isHeld = !!flags.held || r?.status === "HELD" || heldLines.length > 0;
  const heldItems = [...heldLines, ...(r?.status === "HELD" ? checkLines : [])];
  if (isHeld && !heldItems.length) heldItems.push("Held out of the public feed; no reason stored");
  // a hold the owner's own Wrong verdict made is the verdict's, not a check's: it shows, but is not counted as held
  add("held", "What was held, and why", heldItems, isHeld && !ownerOnly ? "held" : undefined);

  const claims = list(g.unsupported_claims).map((c) => `Claim not supported by the sources: "${c}"`);
  const ungrounded = list(g.ungrounded);
  const failed = [...claims,
    ...(ungrounded.length ? [`Numbers not found in the filing: ${ungrounded.join(", ")}`] : []),
    ...(Number(g.math_mismatches) > 0 ? [`${g.math_mismatches} sum or ratio did not add up`] : []),
    ...(r?.status === "UNRESOLVED" ? checkLines : [])];
  const review = !!flags.needs_review;
  if (review && !failed.length) failed.push("Flagged for review; no reason stored");
  if (claims.length) types.push("unsupported");
  if (ungrounded.length) types.push("ungrounded");
  if (review) types.push("review");
  add("failed", "Checks that failed", failed);

  add("unconfirmed", "Points the checks could not confirm", UNCONFIRMED.flatMap(([k, label]) => list(g[k]).map((t) => `${label}: ${t}`)));

  const v = verdict?.verdict?.toUpperCase();
  if (v === "WRONG" || v === "MINOR" || v === "RIGHT") {
    const word = v === "WRONG" ? "Wrong" : v === "MINOR" ? "Minor issue" : "Right";
    add("verdict", "Your verdict", [`${word}${verdict?.note ? `: ${verdict.note}` : ""}`],
      v === "WRONG" ? "verdict_wrong" : v === "MINOR" ? "verdict_minor" : undefined);
  }
  return { groups, types };
}

/** card_json text to the parts cardChecks reads; null when it is not JSON. */
export function parseCheckInput(json: string | null | undefined): CheckInput | null {
  try { return json ? (JSON.parse(json) as CheckInput) : null; } catch { return null; }
}

/** One row of the owner's Issues page (GET /api/owner/issues). */
export interface IssueRow {
  news_id: string; filed_at: string; filing_date: string; scrip_code: string; symbol: string | null; company_name: string;
  event_category: string; headline: string; types: IssueType[]; reasons: string[];
}
export interface IssuesResponse { rows: IssueRow[]; next_cursor: string | null; from: string; to: string; scanned: number }
