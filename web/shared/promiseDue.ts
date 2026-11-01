// When a promise counts as overdue. One rule for the Worker and the page, the same as the pipeline's
// `periods.results_due`: a deadline given as a reporting period (Q1-Q4, H1/H2, 9M, FY) can be judged missed only once
// that period's results are due (SEBI LODR Reg 33(3): 45 days after a quarter, half or nine months, 60 after the year),
// not at its end. A written-out date or a month is judged on that day. Tests: test/promiseDue.test.ts.
export const RESULTS_DAYS_QUARTER = 45;
export const RESULTS_DAYS_YEAR = 60;

// periods._RANGE_SPLIT
const RANGE_SPLIT = /\s+(?:to|till|until|through|and|or)\s+|\s*[–—]\s*|\s+-\s+|(?<=\d)\s*-\s*(?=(?:Q[1-4]|H[12]|9M)?\s*FY)/i;
// periods.canonical_period's first search: a reporting period with its FY; its year digits
const PERIOD = /\b(Q[1-4]|H[12]|9M)\s*[-–]?\s*FY\s*'?([\d\s/–-]{2,9})/;
const FY_ONLY = /\bFY\s*'?([\d\s/–-]{2,9})/;
// periods.explicit_date: a calendar date written out (a month alone is not one)
const MON = "(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\\.?";
const EXPLICIT = [
  /\b20\d{2}-\d{2}-\d{2}\b/,
  /\b\d{1,2}[./-]\d{1,2}[./-]20\d{2}\b/,
  new RegExp(`\\b\\d{1,2}(?:ST|ND|RD|TH)?(?:\\s+|-)${MON}(?:,?\\s+|-)20\\d{2}\\b`),
  new RegExp(`\\b${MON}\\s+\\d{1,2}(?:ST|ND|RD|TH)?,?\\s+20\\d{2}\\b`),
];

type Due = { due?: string | null; due_date?: string | null; overdue_from?: string | null };
type Token = { prefix: string; rank: number };

function addDays(day: string, days: number): string {
  return new Date(Date.parse(`${day.slice(0, 10)}T00:00:00Z`) + days * 86400_000).toISOString().slice(0, 10);
}

/** The reporting period a text names (prefix "" for a whole year) and a rank to tell which ends later. */
function token(text: string): Token | null {
  const m = PERIOD.exec(text) ?? FY_ONLY.exec(text);
  if (!m) return null;
  const hasPrefix = m.length === 3;
  const digits = (hasPrefix ? m[2] : m[1]).replace(/\D/g, "");
  if (digits.length < 2) return null;
  const prefix = hasPrefix ? m[1] : "";
  const pos = { Q1: 1, Q2: 2, Q3: 3, Q4: 4, H1: 2, H2: 4, "9M": 3, "": 4 }[prefix] ?? 4;
  return { prefix, rank: Number(digits.slice(-2)) * 4 + pos };
}

/** The first day the deadline can be judged missed, as `periods.results_due`: `due_date` plus the results window when
 *  `due` names a reporting period (a range counts at its later end), else `due_date` itself. Null with no due date. */
export function judgedOn(due: string | null | undefined, dueDate: string | null | undefined): string | null {
  if (!dueDate) return null;
  const text = (due ?? "").toUpperCase();
  const parts = text.split(RANGE_SPLIT).filter((p) => p.trim());
  let last = text;
  if (parts.length > 1) {
    last = parts.reduce((best, p) => ((token(p)?.rank ?? -1) > (token(best)?.rank ?? -1) ? p : best), parts[0]);
  }
  if (EXPLICIT.some((r) => r.test(last))) return dueDate;
  const t = token(last);
  if (!t) return dueDate;
  return addDays(dueDate, ["", "Q4", "H2"].includes(t.prefix) ? RESULTS_DAYS_YEAR : RESULTS_DAYS_QUARTER);
}

/** `overdue_from` is the day the pipeline stored for the promise (radar summary), when it has one. */
function from(p: Due): string | null {
  return p.overdue_from ?? judgedOn(p.due, p.due_date);
}

export function isPastDue(p: Due, today: string): boolean {
  const f = from(p);
  return !!f && f < today;
}

/** Days past the judged day, never negative. */
export function daysPastDue(p: Due, today: string): number {
  const f = from(p);
  return f ? Math.max(0, Math.round((Date.parse(today) - Date.parse(f)) / 86400_000)) : 0;
}
