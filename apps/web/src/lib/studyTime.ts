/**
 * Tour step "Giờ học": turns the hour a learner usually studies into routine changes (pure, unit-tested).
 *
 * THPT, hour H:
 * - `evening_review` (the mentor prepares tonight's quick review) runs at H-0:30,
 * - `review_due` (the gateway's nudge "Có N kỹ năng đến hạn ôn") runs at H:00, which is the time Mầm tells the learner;
 * - a missing routine is added; weekdays/months of an existing cron are kept.
 * NCS, hour H: `evening_wrapup` runs at H:00 (their only evening routine).
 * "Không cần nhắc" (hour = null) switches those routines off. Routines the learner may not edit are never touched.
 * Quiet hours and the proactivity level stay as the learner set them; when they would swallow the reminder the
 * result says so (`blockedBy`) instead of silently changing them.
 */
import { isQuietNow } from "./quietHours";
import type { Role, Routine, Settings } from "./types";

export const STUDY_HOURS = [19, 20, 21] as const;

export interface StudyTimeResult {
  settings: Settings;
  /** the reminder will not reach the learner at the chosen time */
  blockedBy: "quiet_hours" | "proactivity" | null;
}

function cronAt(existing: string | undefined, hour: number, minute: number): string {
  const rest = existing?.trim().split(/\s+/).slice(2) ?? [];
  const tail = rest.length === 3 ? rest : ["*", "*", "*"];
  return `${minute} ${hour} ${tail.join(" ")}`;
}

/** [routine id, minutes after midnight, prompt for a routine that does not exist yet] */
function targets(role: Role | null, hour: number): [string, number, string][] {
  if (role === "ncs") return [["evening_wrapup", hour * 60, "Dùng skill daily-checkin, phần B (tổng kết buổi tối)."]];
  return [
    ["evening_review", hour * 60 - 30, "Dùng skill spaced-review, phần A: chuẩn bị bài ôn nhanh tối nay và báo học sinh theo mức chủ động."],
    ["review_due", hour * 60, "Nhắc ôn khi có kỹ năng đến hạn (hệ thống tự làm)."],
  ];
}

const IDS: Record<"thpt" | "ncs", string[]> = { thpt: ["evening_review", "review_due"], ncs: ["evening_wrapup"] };

export function applyStudyTime(current: Settings, role: Role | null, hour: number | null): StudyTimeResult {
  const routines: Routine[] = current.routines.map((r) => ({ ...r }));
  if (hour === null) {
    for (const r of routines) if (IDS[role === "ncs" ? "ncs" : "thpt"].includes(r.id) && r.user_editable) r.enabled = false;
    return { settings: { ...current, routines }, blockedBy: null };
  }
  for (const [id, minutes, prompt] of targets(role, hour)) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    const i = routines.findIndex((r) => r.id === id);
    if (i >= 0) {
      if (!routines[i].user_editable) continue;
      routines[i] = { ...routines[i], enabled: true, cron: cronAt(routines[i].cron, h, m) };
    } else {
      routines.push({ id, enabled: true, cron: cronAt(undefined, h, m), job_kind: "routine", prompt, user_editable: true });
    }
  }
  const atMs = Date.UTC(2026, 0, 1, hour, 0) - 7 * 3_600_000; // the same clock time in VN, for the quiet-hours check
  const blockedBy =
    current.proactivity === "off" ? "proactivity" : isQuietNow(current.quiet_hours, atMs) ? "quiet_hours" : null;
  return { settings: { ...current, routines }, blockedBy };
}

/** "20:00" */
export function hourLabel(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

/** The hour of the current reminder routine, to preselect the chip when the tour is replayed. */
export function currentStudyHour(settings: Settings, role: Role | null): number | null {
  const id = role === "ncs" ? "evening_wrapup" : "review_due";
  const r = settings.routines.find((x) => x.id === id);
  if (!r || !r.enabled) return null;
  const m = /^0 (\d{1,2}) /.exec(r.cron.trim());
  const h = m ? Number(m[1]) : NaN;
  return (STUDY_HOURS as readonly number[]).includes(h) ? h : null;
}
