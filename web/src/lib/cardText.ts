/** Plain-text rules the card uses to say each thing once (owner, 2026-10-19: "lots of repeated items"). No React here,
 * so `node --test` runs the cases in cardText.test.ts. */

import type { CardBody } from "../../shared/types";

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
 * stays. Same pattern as pipeline no_eps.py EPS_WORDS; digits are Unicode (\p{Nd}) on both sides. */
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

// the separators a trailing EPS clause may follow: ", " "; " " — " " | "
const SEP = /,\s|;\s|\s[—–|]\s/g;
const LEAD_WORDS = /^(?:\s*\b(?:basic|diluted|and|net|adjusted|reported|with|plus)\b|\s*&)*\s*$/i;
const DANGLE = /(?:[\s,;:\-—–|(]+|\s+(?:basic|diluted|and|net)$)$/i;
// the only words a trailing EPS clause may carry after the EPS words: its figure, its change and its comparison
const CLAUSE_WORDS = new Set(("rs re inr cr crore crores lakh lakhs mn million bn billion bps pp x per share shares a an each of vs versus from to up down "
  + "rose fell yoy qoq yr yrs year years ago earlier prior previous last compared with at was were is in the quarter quarters "
  + "q fy h m basic diluted and or grew growth growing increase increased decrease decreased decline declined declining "
  + "dropped higher lower rise rising falling on by").split(" "));

function balanced(text: string): boolean {
  let depth = 0;
  for (const c of text) {
    if (c === "(" || c === "[") depth++;
    else if (c === ")" || c === "]") { depth--; if (depth < 0) return false; }
  }
  return depth === 0;
}

/** Mirrors pipeline no_eps.py `_trailing_cut`: the text without a TRAILING EPS clause (the EPS words start after the last
 * ", " / "; " / " — " / " | " outside brackets and nothing but the clause follows: its figure, a bracketed change, "vs ₹x",
 * "a year ago"); null when the EPS is anywhere else, so no figure can be given to the wrong metric. */
function trailingCut(text: string): string | null {
  const m = EPS_TEXT.exec(text);
  if (!m) return text;
  const depths: number[] = [];
  let depth = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === ")" || c === "]") depth = Math.max(0, depth - 1);
    depths.push(depth);
    if (c === "(" || c === "[") depth++;
  }
  let last: RegExpExecArray | null = null;
  for (const sm of text.matchAll(SEP)) if (depths[sm.index!] === 0) last = sm as unknown as RegExpExecArray;
  if (!last) return null;
  const lastEnd = last.index! + last[0].length;
  if (lastEnd > m.index || depths[m.index] !== 0) return null;
  if (!LEAD_WORDS.test(text.slice(lastEnd, m.index))) return null;
  const rest = text.slice(m.index + m[0].length);
  if (statesEps(rest) || !balanced(rest)) return null;
  const words = rest.replace(PERIOD_WORDS, " ").match(/[\p{L}\p{No}\p{Nl}]+/gu) ?? [];
  if (words.some((w) => !CLAUSE_WORDS.has(w.toLowerCase()))) return null;
  let prefix = text.slice(0, last.index);
  for (;;) {
    const cut = prefix.replace(DANGLE, "");
    if (cut === prefix) break;
    prefix = cut;
  }
  prefix = prefix.trimEnd();
  return prefix && balanced(prefix) && !statesEps(prefix) ? prefix : null;
}

/** Mirrors pipeline no_eps.py `cut_text`: the text unchanged without EPS, its trailing EPS clause cut when that is all there
 * is, and null when it states EPS anywhere else (the item is then dropped: a wrong line is worse than a missing one). */
export function trimEps(text: string): string | null {
  if (!text || !statesEps(text)) return text;
  const cut = trailingCut(text);
  return cut && !statesEps(cut) ? cut : null;
}

/** For text that is never hidden (a headline in a list or a tooltip): the trailing EPS clause cut, else as stored. */
export const cutEps = (text: string): string => trimEps(text) ?? text;

function headlineWithoutEps(headline: string, facts: string[]): string {
  const m = EPS_TEXT.exec(headline);
  let prefix = m ? headline.slice(0, m.index).replace(/^[\s:\-\u2013\u2014,;(]+|[\s:\-\u2013\u2014,;(]+$/g, "") : "";
  if (prefix && /\d/.test(prefix.replace(PERIOD_WORDS, " "))) {
    const p = new RegExp(PERIOD_WORDS.source, "i").exec(prefix);
    prefix = p ? prefix.slice(0, p.index + p[0].length).replace(/[\s:\-\u2013\u2014,;(]+$/, "") : "";
  }
  const fact = facts.map((f) => f.trim().replace(/\.$/, "")).find((f) => f && !statesEps(f)) ?? "";
  if (fact && prefix && fact.toLowerCase().startsWith(prefix.toLowerCase())) prefix = "";
  const line = prefix && fact ? `${prefix}: ${fact}` : fact || (prefix ? `${prefix}: results` : "Quarterly results announced");
  return line.length >= 8 ? line : "Quarterly results announced";
}

/** A stored card as a reader sees it under the owner's no-EPS rule, the same item rule as the pipeline (`drop_eps`): an item
 * whose text states EPS is dropped whole, except a trailing EPS clause, which is cut; `parts` is re-indexed so it still
 * points at the right lines. A headline that cannot be cut is rebuilt from the company and period and the first line left;
 * a takeaway or core catalyst that cannot be cut is left off (the face falls back to the insights). */
export function withoutEps(card: CardBody): CardBody {
  const keepers = <T>(items: T[] | null | undefined, texts: (t: T) => (string | null | undefined)[]) => {
    const map = new Map<number, number>();
    const kept: T[] = [];
    (items ?? []).forEach((item, i) => { if (!statesEps(...texts(item))) { map.set(i, kept.length); kept.push(item); } });
    return { kept, map };
  };
  // items with one text: a trailing EPS clause is cut, EPS anywhere else drops the item (its quote is left as it is)
  const refine = <T>(items: T[] | null | undefined, get: (t: T) => string, set: (t: T, text: string) => T) => {
    const map = new Map<number, number>();
    const kept: T[] = [];
    (items ?? []).forEach((item, i) => {
      const text = trimEps(get(item));
      if (text === null) return;
      map.set(i, kept.length);
      kept.push(text === get(item) ? item : set(item, text));
    });
    return { kept, map };
  };
  const strings = (items: string[] | null | undefined) => refine(items, (x) => x, (_, text) => text);
  const text = (f: string | { text: string }) => (typeof f === "string" ? f : f.text);
  const wh = refine(card.what_happened, text, (f, t) => (typeof f === "string" ? t : { ...f, text: t }));
  const why = refine(card.why_it_matters, (i) => i.text, (i, t) => ({ ...i, text: t }));
  const keys = keepers(card.key_numbers, (k) => [k.label, k.value, k.change]);
  const changes = keepers(card.notable_changes, (c) => [c.metric, c.why, c.change]);
  const quant = keepers(card.quantified_impact, (q) => [q.label, q.interpretation, q.formula]);
  const calls = refine(card.call_takeaways, (t) => t.text, (t, x) => ({ ...t, text: x }));
  const missing = strings(card.missing_disclosures);
  const headline = trimEps(card.headline) ?? headlineWithoutEps(card.headline, wh.kept.map(text));
  const out: CardBody = { ...card, headline, what_happened: wh.kept, why_it_matters: why.kept, key_numbers: keys.kept,
    missing_disclosures: missing.kept };
  if (card.takeaway) out.takeaway = trimEps(card.takeaway) ?? undefined;
  if (card.core_catalyst) out.core_catalyst = trimEps(card.core_catalyst);
  if (card.notable_changes) out.notable_changes = changes.kept;
  if (card.quantified_impact) out.quantified_impact = quant.kept;
  if (card.call_takeaways) out.call_takeaways = calls.kept;
  const t = card.track_next;
  if (t) {
    out.track_next = { ...t,
      milestones: (t.milestones ?? []).filter((m) => !statesEps(m.what)),
      kpis_to_verify: (t.kpis_to_verify ?? []).filter((k) => !statesEps(k.kpi, k.check_in, k.target)),
      pending_approvals: strings(t.pending_approvals).kept,
      risks: strings(t.risks).kept,
      ...(t.catalysts ? { catalysts: strings(t.catalysts).kept } : {}) };
  }
  const p = card.parts;
  if (p) {
    const remap = (idx: number[] | undefined, map: Map<number, number>) => idx?.flatMap((i) => (map.has(i) ? [map.get(i) as number] : []));
    const maps: Record<string, Map<number, number>> = { what_happened: wh.map, why_it_matters: why.map, key_numbers: keys.map,
      notable_changes: changes.map, quantified_impact: quant.map, call_takeaways: calls.map, missing_disclosures: missing.map };
    const fix = <T extends object>(part: T): T => {
      const next = { ...part } as Record<string, unknown>;
      for (const [name, map] of Object.entries(maps)) if (Array.isArray(next[name])) next[name] = remap(next[name] as number[], map);
      return next as unknown as T;
    };
    out.parts = { ...p, ...(p.part1 ? { part1: fix(p.part1) } : {}), ...(p.part2 ? { part2: fix(p.part2) } : {}) };
  }
  return out;
}
