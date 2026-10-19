/** One event per company and day: a generic "Other" or "Milestone" beside a named event of the same day is the same
 * thing filed again (laptop test, 2026-10-19: Shivam Autotech's rights issue as Rights Open, Milestone and Other). */
const GENERIC_EVENTS = new Set(["OTHER", "MILESTONE"]);
export function dedupeEvents<T extends { scrip_code: string; event_date: string; event_type: string }>(events: T[]): T[] {
  const named = new Set(events.filter((e) => !GENERIC_EVENTS.has(e.event_type)).map((e) => `${e.scrip_code}|${e.event_date}`));
  const seen = new Set<string>();
  return events.filter((e) => {
    const day = `${e.scrip_code}|${e.event_date}`;
    if (GENERIC_EVENTS.has(e.event_type) && named.has(day)) return false;
    const key = `${day}|${e.event_type}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
