export type QuietPick = "30" | "60" | "120" | "tomorrow" | "week";

/** Quiet period end for a preset, as an ISO string. Same rules as mockups/shared.js. */
export function quietUntil(pick: QuietPick, now: Date = new Date()): string {
  let t: Date;
  if (pick === "tomorrow") {
    t = new Date(now);
    t.setDate(t.getDate() + 1);
    t.setHours(7, 0, 0, 0);
  } else if (pick === "week") {
    // end of the coming Sunday (a Sunday means the next one)
    t = new Date(now);
    t.setDate(t.getDate() + ((7 - t.getDay()) % 7 || 7));
    t.setHours(23, 59, 0, 0);
  } else {
    t = new Date(now.getTime() + Number(pick) * 60000);
  }
  return t.toISOString();
}

/** Custom end: `dayOffset` days from today (0, 1, 2) at `minutes` after midnight. Null if not in the future. */
export function quietCustom(dayOffset: number, minutes: number, now: Date = new Date()): string | null {
  const t = new Date(now);
  t.setDate(t.getDate() + dayOffset);
  t.setHours(Math.floor(minutes / 60), minutes % 60, 0, 0);
  return t.getTime() > now.getTime() ? t.toISOString() : null;
}

export function isQuiet(until: string | null, now: number = Date.now()): boolean {
  return !!until && new Date(until).getTime() > now;
}
