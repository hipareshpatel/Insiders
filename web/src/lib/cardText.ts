/** Plain-text rules the card uses to say each thing once (owner, 2026-10-19: "lots of repeated items"). No React here,
 * so `node --test` runs the cases in cardText.test.ts. */

const plainText = (text: string) => text.replace(/\*\*/g, "");

// Period labels ("Q2FY27", "Q2 FY 2026-27", "H1FY27") and years are not figures.
export const PERIOD_WORDS = /\b(?:Q[1-4]|H[12]|9M)?\s*FY\s*'?\d{2,4}(?:-\d{2})?\b|\b(?:Q[1-4]|H[12]|9M)\b|\b20\d{2}(?:-\d{2})?\b/gi;

export function figures(text: string): number[] {
  return (text.replace(PERIOD_WORDS, " ").match(/\d[\d,]*(?:\.\d+)?/g) ?? []).map((raw) => Number(raw.replace(/,/g, "")));
}

export function near(n: number, known: number[], raw = ""): boolean {
  const rounding = raw.includes(".") ? 0.051 : 0.5; // "+30%" restates 29.6%
  return known.some((k) => Math.abs(k - n) <= Math.max(rounding, Math.abs(k) * 0.006));
}

const STOP = new Set(["with", "from", "that", "this", "were", "have", "been", "which", "their", "into", "over", "under",
  "after", "before", "about", "against", "company", "limited", "crore", "lakh", "year", "quarter", "said", "will", "also"]);
export function words(text: string): Set<string> {
  return new Set((text.toLowerCase().match(/[a-z][a-z-]{3,}/g) ?? []).filter((w) => !STOP.has(w)));
}

/** `value` appears in `text` as a figure of its own ("2.1" is not inside "12.1"). Its sign, "₹" and its unit ("Cr",
 * "%", "x", "bps", "per share") are not part of the figure: "₹0.63 per share" is the table's EPS 0.63. */
export function showsFigure(text: string, value: string): boolean {
  const v = value.trim().replace(/^[+−-]\s*/, "").replace(/^₹\s*/, "")
    .replace(/\s*(?:Cr|crore|%|x|bps?|per share)\.?$/i, "").trim();
  if (!v) return false;
  return new RegExp(`(^|[^\\d.,])${v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\d]|[.,]\\d)`).test(text);
}

// A figure that says something on its own, not a count or a list number ("Stage 3", "2 units", "02 September")
const telling = (raw: string) => raw.includes(".") || Number(raw.replace(/,/g, "")) >= 10;

/** True when `text` says nothing `of` does not: its figures are all there and most of its words, or nearly every word,
 * or two or more of its figures are there in other words (Heritage's "19% YoY to ₹1,320 Cr" under its headline). */
export function repeats(text: string, of: string): boolean {
  const t = plainText(text), o = plainText(of);
  const mine = [...words(t)], theirs = words(o);
  const overlap = mine.length ? mine.filter((w) => theirs.has(w)).length / mine.length : 0;
  const nums = figures(t), known = figures(o);
  const allFigures = nums.length > 0 && nums.every((n) => near(n, known, String(n)));
  const raw = t.replace(PERIOD_WORDS, " ").match(/\d[\d,]*(?:\.\d+)?/g) ?? [];
  const shared = raw.filter((x) => telling(x) && near(Number(x.replace(/,/g, "")), known, x)).length;
  return (allFigures && overlap >= 0.4) || overlap >= 0.8 || shared >= 2;
}

/** A model's placeholder stored as a value ("to be determined via private placement", "N/A"): not a fact to show. */
const PLACEHOLDER = /\b(?:to be (?:determined|decided|finali[sz]ed|announced|identified|disclosed)|tbd|not (?:disclosed|specified|stated|available|applicable|known)|undisclosed|unknown)\b|^\s*(?:n[./]?\s?a\.?|nil|none|null|-+)?\s*$/i;
export const realValue = (text: string | null | undefined): string | null =>
  text && !PLACEHOLDER.test(text) ? text.trim() : null;

/** The filing states the value before GST ("excluding GST", "plus GST", "exclusive of taxes"). */
export const saysExGst = (text: string) =>
  /\b(?:excl(?:uding|usive of|\.)?|ex|without|plus)\s*(?:of\s+)?(?:applicable\s+)?(?:GST|taxes)\b|\+\s*GST\b|\bGST\s+(?:extra|excluded|additional)\b/i.test(text);

const RATED: [RegExp, string][] = [[/bank (?:loan )?facilit/i, "bank facilities"], [/facilit/i, "facilities"],
  [/NCD|debenture/i, "NCDs"], [/commercial paper|\bCP\b/i, "commercial paper"], [/bond/i, "bonds"], [/borrowing/i, "borrowings"],
  [/loan/i, "loans"], [/instrument/i, "instruments"], [/programme|program/i, "programme"], [/limit/i, "limits"], [/debt/i, "debt"]];

/** The amount a rating covers, as the text names it ("on ₹1,800 Cr facilities"), for the rating block's title. */
export function ratedAmount(...texts: string[]): string | null {
  for (const text of texts) {
    const m = plainText(text).match(/₹\s?(\d[\d,]*(?:\.\d+)?)\s*(lakh\s+)?(?:Cr|crore)\b([^.;]{0,40})/i);
    const noun = m && RATED.find(([re]) => re.test(m[3]));
    if (m && noun) return `₹${m[1]} ${m[2] ? "lakh " : ""}Cr ${noun[1]}`;
  }
  return null;
}

/** "36 months" or "05 years" is a term, "30 June 2027" a date (Ceigall's "Complete by 05 years", laptop re-check). */
export function executionFact(text: string): [string, string] {
  const term = text.match(/^\s*(?:within|over|for(?: a period of)?)?\s*0*(\d+(?:\.\d+)?)\s*(months?|years?)\b/i);
  return term ? ["Term", `${term[1]} ${term[2].toLowerCase()}`] : ["Complete by", text];
}

/** The verified face (owner, 2026-10-20, after two live reviews put 17 of 48 cards WRONG, nearly all in the prose): a
 * fact stays on the card when code found its quoted sentence in the filing and none of its figures is among those the
 * checks could not find. Anything else is the AI's reading and goes behind "AI reading · not verified". */
export function verifiedFact(fact: string | { text: string; quote?: string | null }, ungrounded: string[] = []): boolean {
  if (typeof fact === "string" || !fact.quote || !fact.quote.trim()) return false;
  const text = plainText(fact.text);
  return !ungrounded.some((u) => {
    const value = String(u).split("=").pop()!.trim();
    return value !== "" && showsFigure(text, value.replace(/^₹/, ""));
  });
}

type FactLike = string | { text: string; quote?: string | null };

/** The card's points: the verified facts that fit on the face, the verified rest for "More from the filing", and the
 * facts without a quote for the AI reading. A face point is never shown again below, and an unverified fact is never
 * labelled as coming from the filing. */
export function splitFacts<F extends FactLike>(unique: F[], ungrounded: string[], limit: number) {
  const verified = unique.filter((f) => verifiedFact(f, ungrounded));
  return { face: verified.slice(0, limit), more: verified.slice(limit), unverified: unique.filter((f) => !verifiedFact(f, ungrounded)) };
}

/** Key tiles whose value the headline already gives are left out (HDFC Life's VNB ₹2,037 Cr in both). */
export const tilesBesides = <K extends { value: string }>(tiles: K[], headline: string) =>
  tiles.filter((k) => !showsFigure(plainText(headline), k.value));

/** A Scale line that restates a figure of the headline (Jubilant's "35% of net worth" twice) is left out. */
export function restatesHeadline(text: string, headline: string): boolean {
  const known = figures(plainText(headline));
  const raw = plainText(text).replace(PERIOD_WORDS, " ").match(/\d[\d,]*(?:\.\d+)?/g) ?? [];
  return raw.some((x) => telling(x) && near(Number(x.replace(/,/g, "")), known, x));
}

// The three analysis boxes (owner, 2026-10-21: "What these numbers mean", "For the decision" and "Our reading" were
// used wrongly; docs/audit/card-sections-2026-10-21.md). Earnings write-ups lead with the result against what was
// expected, why it moved, guidance and what to watch next; housekeeping does not belong in any of the three.

/** Signals that stay in "Full analysis" but never take the box: Reg 30 boilerplate (Laxmi Dental's tariff refund) and the
 * three-quarter tax-rate check (Indosolar, a company being merged away). */
const HOUSEKEEPING_SIGNALS = new Set(["REG30_THRESHOLD", "LOW_CASH_TAX"]);
export const boxSignal = (type: string) => !HOUSEKEEPING_SIGNALS.has(type);

// A "not disclosed" item about a deal on a card that is not about the deal: Indosolar's results did not need a swap ratio
const DEAL_WORDS = /\b(?:amalgamat\w*|merger|swap ratio|share exchange ratio|scheme of arrangement|acquisition|demerger)\b/i;
const NOT_DEAL_EVENTS = new Set(["RESULTS", "CONCALL_PRESENTATION", "MONTHLY_BUSINESS_UPDATE", "DEBT_RATINGS", "ANNUAL_REPORT"]);
export const missingOnTopic = (event: string, text: string) => !(NOT_DEAL_EVENTS.has(event) && DEAL_WORDS.test(text));

/** A memory item about procedure, not the business (Indosolar's results showed "Watching: shareholders' approval of a cost
 * auditor"): appointments, meetings, votes, record dates. It is not for the decision. */
const PROCEDURAL = /\b(?:(?:cost|statutory|secretarial|internal|branch)\s+auditors?|(?:re-?)?appoint\w*|annual general meeting|postal ballot|e-?voting|scrutini[sz]er|record date|book closure|trading window|company secretary|compliance officer|independent director|(?:shareholders?'?|members?'?)\s+approval)\b/i;
// on a governance card the procedure is the news, and on a deal a shareholder vote is a stage of it (QPower's fundraise);
// pipeline/src/bse_intel/card_context.py matches this
const PROCEDURE_EVENTS = new Set(["GOVERNANCE", "MANAGEMENT_CHANGE", "ANNUAL_REPORT", "FUNDRAISE", "M_AND_A", "RIGHTS_ISSUE"]);
export const procedural = (text: string, event = "") => !PROCEDURE_EVENTS.has(event) && PROCEDURAL.test(text);

/** Stricter than `repeats`, for "Our reading": a reading that reuses the face's figures to compare them ("8.3% of market
 * cap, 1.5% of the order book") adds something; only one with every figure on the face and most of its words is a
 * restatement (HDFC AMC's "revenue grew 13.9% YoY to ₹1,170.22 Cr, supported by ongoing operational growth"). */
export function restates(text: string, of: string): boolean {
  const t = plainText(text), o = plainText(of);
  const mine = [...words(t)], theirs = words(o);
  const overlap = mine.length ? mine.filter((w) => theirs.has(w)).length / mine.length : 0;
  const nums = figures(t), known = figures(o);
  return nums.every((n) => near(n, known, String(n))) && (overlap >= 0.6 || (nums.length > 0 && overlap >= 0.45));
}

// lines where a fall is the good news: asset quality, costs, debt, losses (deep audit F-13: "GNPA -17 bps" showed red)
const LOWER_IS_BETTER = /\b(?:g?npa|nnpa|non[- ]performing|slippages?|credit\s+cost|provisions?|cost[- ]to[- ]income|expenses?|costs?|debt|borrowings?|leverage|losses?|attrition|days?\s+(?:receivable|inventory|payable)|working\s+capital\s+days|pledged?)\b/i;

/** A key number's change as good (pos), bad (neg) or neither: the sign of its first figure (or up/down in words),
 *  turned round for a line where less is better; no direction at all is neither, never green by default. */
export function changeTone(label: string, change: string): "pos" | "neg" | null {
  const text = change.trim();
  const sign = text.match(/([+\-−])\s*[₹$]?\s*\d/);
  const word = text.match(/\b(up|rose|higher|increase[sd]?|gain(?:ed)?|down|fell|lower|decrease[sd]?|decline[sd]?|drop(?:ped)?)\b/i);
  const up = sign ? sign[1] === "+" : word ? /^(up|rose|higher|increase|gain)/i.test(word[1]) : null;
  if (up === null) return null;
  const good = LOWER_IS_BETTER.test(label) ? !up : up;
  return good ? "pos" : "neg";
}

// A governance event an investor must not read past (owner, 22 Oct 2026: governance flags blended in with routine
// news): an auditor's or CFO's exit, a regulator's order, a forensic audit, a fraud, a default. Matched on the card's
// own headline and facts, worded tightly so an auditor's appointment or a routine SEBI letter is no flag.
const GOVERNANCE_FLAGS: [RegExp, string][] = [
  [/\b(?:statutory\s+|secretarial\s+|internal\s+)?auditors?\b[^.]{0,60}\b(?:resign|resigned|resignation|quit|steps?\s+down)|\bresign(?:ed|ation)\b[^.]{0,60}\bauditors?\b/i, "Auditor exit"],
  [/\b(?:chief\s+financial\s+officer|cfo)\b[^.]{0,50}\b(?:resign|resigned|resignation|steps?\s+down|exit)|\bresign(?:ed|ation)\b[^.]{0,40}\b(?:chief\s+financial\s+officer|cfo)\b/i, "CFO exit"],
  [/\bforensic\s+audit\b/i, "Forensic audit"],
  [/(?<!\bno\s)(?<!\bnot\s)\bfraud\b(?![^.]{0,30}\b(?:no|not)\b)/i, "Fraud"],
  [/\b(?:sebi|rbi|sfio|enforcement\s+directorate|\bed\b)\b[^.]{0,60}\b(?:order|penalty|debar|barred|show\s+cause|attach|search|raid)/i, "Regulator action"],
  [/\bdefault(?:ed|s)?\b[^.]{0,40}\b(?:interest|principal|repayment|ncds?|debentures?|loans?)\b/i, "Default"],
];

export function governanceFlags(text: string): string[] {
  return GOVERNANCE_FLAGS.filter(([re]) => re.test(text)).map(([, label]) => label);
}

/** Owner rule 26 Oct 2026: no EPS on cards or stock pages. True when a line of a stored card states earnings per share
 * ("EPS", "E.P.S.", "earnings per share", "earnings/share", "earnings ₹5 per share", "earnings per ₹10 share", "profit per
 * share", "profit after tax per share", "PAT/share"); a dividend, DPS, book value, NAV or price per share is not EPS and
 * stays. Used to keep EPS rows off the face of stored cards; the pipeline's no_eps.py guards new cards (it is wider: per-share figures, LPS). */
const D = "\\d";
const AMT = "(?:(?:rs\\.?|inr|₹)\\s*)?\\d[\\d.,]*\\s*(?:/-)?";
const PER = "(?:\\s+(?:per|a|each)\\s+|\\s*/\\s*)";
const SHARE = "(?:(?:rs\\.?|inr|₹)\\s*\\d[\\d.,]*\\s*(?:/-)?\\s+)?(?:(?:equity|ordinary|diluted|basic)\\s+)*share"
  + "(?:\\s+of\\s+(?:rs\\.?|inr|₹)\\s*\\d[\\d.,]*(?:\\s*/-)?(?:\\s+each)?)?";
const QUAL = "(?:\\s*\\([^)]{0,40}\\))?";
const EPS_SOURCE = ("(?<![\\p{L}\\p{N}_])(?:eps|e\\.p\\.s\\.?|"
  + "(?:diluted\\s+|basic\\s+)?earnings?" + QUAL + PER + SHARE + "|"
  + "earnings?\\s+(?:of\\s+)?" + AMT + PER + SHARE + "|"
  + "(?:profit|pat)\\s+(?:of\\s+)?" + AMT + PER + SHARE + "|"
  + "(?:net\\s+)?(?:profit(?:\\s+after\\s+tax)?|income|pat)" + QUAL + PER + SHARE + "|"
  + "per[\\s-]share\\s+(?:earnings|profit|income))(?![\\p{L}\\p{N}_])").split(D).join("\\p{Nd}");
export const EPS_TEXT = new RegExp(EPS_SOURCE, "iu");
export const statesEps = (...texts: (string | null | undefined)[]): boolean => texts.some((t) => !!t && EPS_TEXT.test(t));
