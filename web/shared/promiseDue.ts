// When a promise counts as overdue. One rule for the Worker and the page, the same as the pipeline's
// `periods.results_due`: a deadline given as a reporting period (Q1-Q4, H1/H2, 9M, FY) can be judged missed only once
// that period's results are due (SEBI LODR Reg 33(3): 45 days after a quarter, half or nine months, 60 after the year),
// not at its end. A date or a month is judged on that day. Tests: test/promiseDue.test.ts.
export const RESULTS_DAYS_QUARTER = 45;
export const RESULTS_DAYS_YEAR = 60;

const PERIOD = /\b(Q[1-4]|H[12]|9M)?\s*[-–]?\s*FY\s*'?\s*(\d{2,4})/g;
const CALENDAR = /\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\bCY\b/;

type Due = { due?: string | null; due_date?: string | null; overdue_from?: string | null };

function addDays(day: string, days: number): string {
  return new Date(Date.parse(`${day.slice(0, 10)}T00:00:00Z`) + days * 86400_000).toISOString().slice(0, 10);
}

/** The first day the deadline can be judged missed: `due_date` plus the results window when `due` names a reporting
 *  period (a range counts at its later end), else `due_date` itself. Null with no due date. */
export function judgedOn(due: string | null | undefined, dueDate: string | null | undefined): string | null {
  if (!dueDate) return null;
  const text = (due ?? "").toUpperCase();
  if (!text || CALENDAR.test(text)) return dueDate;
  const tokens = [...text.matchAll(PERIOD)];
  const last = tokens[tokens.length - 1];
  if (!last) return dueDate;
  const prefix = last[1] ?? "";
  return addDays(dueDate, prefix === "" || prefix === "Q4" || prefix === "H2" ? RESULTS_DAYS_YEAR : RESULTS_DAYS_QUARTER);
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
