/** The "add goal" form: a title and an optional deadline (none / this month / a picked date). Nothing else. */
export type DeadlinePick = { kind: "none" } | { kind: "month" } | { kind: "date"; value: string };

const pad = (n: number) => String(n).padStart(2, "0");
export const toYmd = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const lastDay = (d: Date) => new Date(d.getFullYear(), d.getMonth() + 1, 0);

/** YYYY-MM-DD for the API, or null for "no deadline". A date in the past or a malformed one is invalid (undefined). */
export function deadlineOf(pick: DeadlinePick, now: Date = new Date()): string | null | undefined {
  if (pick.kind === "none") return null;
  if (pick.kind === "month") return toYmd(lastDay(now));
  if (!/^\d{4}-\d{2}-\d{2}$/.test(pick.value)) return undefined;
  const d = new Date(`${pick.value}T00:00:00`);
  if (Number.isNaN(d.getTime()) || toYmd(d) !== pick.value) return undefined;
  return pick.value < toYmd(now) ? undefined : pick.value;
}

export interface GoalDraft {
  title: string;
  pick: DeadlinePick;
}
export type GoalFormResult = { ok: true; body: { title: string; deadline?: string } } | { ok: false; error: "title" | "deadline" };

export function buildGoal(draft: GoalDraft, now: Date = new Date()): GoalFormResult {
  const title = draft.title.replace(/\s+/g, " ").trim();
  if (!title || title.length > 200) return { ok: false, error: "title" };
  const deadline = deadlineOf(draft.pick, now);
  if (deadline === undefined) return { ok: false, error: "deadline" };
  return { ok: true, body: deadline ? { title, deadline } : { title } };
}
