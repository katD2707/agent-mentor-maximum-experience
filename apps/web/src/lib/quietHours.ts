/** Quiet hours (settings.quiet_hours, "HH:MM" in VN time). The UI never plays sound; in quiet hours it also stays still. */

const VN_OFFSET_MIN = 7 * 60; // Asia/Ho_Chi_Minh has no DST

function toMinutes(hhmm: string): number | null {
  const m = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(hhmm);
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}

/** Minute of the day in VN time. */
export function vnMinuteOfDay(nowMs: number): number {
  const m = Math.floor(nowMs / 60_000) + VN_OFFSET_MIN;
  return ((m % 1440) + 1440) % 1440;
}

/** True when `nowMs` falls in [start, end), wrapping past midnight (22:00–07:00). Equal or invalid bounds: never. */
export function isQuietNow(range: readonly [string, string] | null | undefined, nowMs: number): boolean {
  if (!range) return false;
  const start = toMinutes(range[0]);
  const end = toMinutes(range[1]);
  if (start === null || end === null || start === end) return false;
  const now = vnMinuteOfDay(nowMs);
  return start < end ? now >= start && now < end : now >= start || now < end;
}
