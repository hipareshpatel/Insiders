const DAY = 86_400_000;
const at = (iso: string) => new Date(`${iso}T00:00:00Z`).getTime();

/** When the filing lists reach yesterday, at the pace of the last few days: the discovery cursor's first position on
 *  each IST day ([day, through]). Null until two mornings are recorded or while the cursor has not moved. */
export function finishEstimate(pace: [string, string][] | undefined, today: string): { perDay: number; daysLeft: number } | null {
  if (!pace || pace.length < 2) return null;
  const [d0, t0] = pace[0], [d1, t1] = pace[pace.length - 1];
  const elapsed = (at(d1) - at(d0)) / DAY;
  const moved = (at(t1) - at(t0)) / DAY;
  if (elapsed <= 0 || moved <= 0) return null;
  const perDay = moved / elapsed;
  const left = Math.max(0, (at(today) - DAY - at(t1)) / DAY);
  return { perDay, daysLeft: Math.ceil(left / perDay) };
}
