/** The results season, by calendar (owner, 29 Oct 2026: "as of 30 Oct you get Q2 FY27 results till December end; from January
 * Q3 starts, and so on"). A quarter's results are declared in the three months after it ends: Q1 (Apr-Jun) in Jul-Sep, Q2 (Jul-Sep)
 * in Oct-Dec, Q3 (Oct-Dec) in Jan-Mar, Q4 (Jan-Mar) in Apr-Jun. The reporting quarter for a date is the last quarter that ended
 * before the first of that date's month. No React here, so `node --test` runs the cases in test/resultsCalendar.test.ts. */

export interface ReportingQuarter {
  /** e.g. "Q2FY27" (the card's period format) */
  period: string;
  /** e.g. "Q2 FY27" */
  label: string;
  /** the window its results are declared in, inclusive, YYYY-MM-DD */
  from: string;
  to: string;
  /** the window is open on the date asked about */
  current: boolean;
}

/** Quarter ends by calendar month: March is Q4 of the year it ends in; June, September and December are Q1-Q3 of the next FY. */
const QUARTER_OF_END_MONTH: Record<number, number> = { 3: 4, 6: 1, 9: 2, 12: 3 };
const END_MONTHS = [3, 6, 9, 12];

const ymd = (y: number, m: number, d: number) => `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
const lastDay = (y: number, m: number) => new Date(Date.UTC(y, m, 0)).getUTCDate();

/** The quarter that ended in `endYear`/`endMonth` (a quarter-end month). */
function quarterEnding(endYear: number, endMonth: number): ReportingQuarter {
  const q = QUARTER_OF_END_MONTH[endMonth];
  const fy = endMonth === 3 ? endYear : endYear + 1;
  const period = `Q${q}FY${String(fy % 100).padStart(2, "0")}`;
  // the three months after the quarter's end
  const startMonth = endMonth + 1, endWindowMonth = endMonth + 3;
  const windowEndYear = endWindowMonth > 12 ? endYear + 1 : endYear;
  const windowEndMonth = endWindowMonth > 12 ? endWindowMonth - 12 : endWindowMonth;
  const startYear = startMonth > 12 ? endYear + 1 : endYear;
  const startMonthNorm = startMonth > 12 ? startMonth - 12 : startMonth;
  return {
    period,
    label: `Q${q} FY${String(fy % 100).padStart(2, "0")}`,
    from: ymd(startYear, startMonthNorm, 1),
    to: ymd(windowEndYear, windowEndMonth, lastDay(windowEndYear, windowEndMonth)),
    current: false,
  };
}

/** The reporting quarter for `today` (YYYY-MM-DD, IST), then the `count` quarters before it, newest first. */
export function reportingQuarters(today: string, count = 5): ReportingQuarter[] {
  const y = Number(today.slice(0, 4)), m = Number(today.slice(5, 7));
  const firstOfMonth = y * 12 + (m - 1);   // month index of this month's first day
  // quarter ends before this month, newest first
  const ends: Array<{ year: number; month: number; index: number }> = [];
  for (let year = y; year >= y - 2; year--) {
    for (const month of [...END_MONTHS].reverse()) {
      const index = year * 12 + (month - 1);
      if (index < firstOfMonth) ends.push({ year, month, index });
    }
  }
  ends.sort((a, b) => b.index - a.index);
  return ends.slice(0, count).map((e, i) => ({ ...quarterEnding(e.year, e.month), current: i === 0 }));
}
