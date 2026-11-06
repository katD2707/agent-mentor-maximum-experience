import type { Routine, Settings } from "./types";

export const ROUTINE_NAMES: Record<string, string> = {
  nightly_reflection: "Reflection hằng đêm",
  evening_review: "Ôn ngắn buổi tối",
  weekend_review: "Review cuối tuần",
  exam_prep_reminder: "Nhắc chuẩn bị trước kỳ thi",
  parent_report: "Báo cáo phụ huynh",
  literature_watch: "Theo dõi paper mới",
  deadline_watch: "Theo dõi deadline",
  weekly_review: "Tổng kết tuần",
  review_due: "Nhắc ôn buổi tối",
  morning_checkin: "Check-in buổi sáng",
  evening_wrapup: "Chốt ngày buổi tối",
};

/** The only routines a learner sees, as plain switches. Each maps to the first of its ids the gateway has. */
export const LEARNER_TOGGLES: { label: string; ids: string[] }[] = [
  { label: "Nhắc ôn buổi tối", ids: ["review_due", "evening_review"] },
  { label: "Tổng kết tuần", ids: ["weekly_review", "weekend_review"] },
  { label: "Check-in buổi sáng", ids: ["morning_checkin"] },
];

/** Up to 3 switches: editable routines only (mandatory ones stay hidden), none when the routine does not exist. */
export function learnerToggles(routines: Routine[]): { label: string; routine: Routine }[] {
  const out: { label: string; routine: Routine }[] = [];
  for (const t of LEARNER_TOGGLES) {
    const r = t.ids.map((id) => routines.find((x) => x.id === id)).find((x) => !!x);
    if (r && r.user_editable) out.push({ label: t.label, routine: r });
  }
  return out;
}

/** Vietnamese message for a 422 from PUT /settings (FastAPI detail may be a string or a list). */
export function invalidSettingsMessage(body: unknown, current: Settings): string {
  const raw = JSON.stringify((body as { detail?: unknown } | undefined)?.detail ?? body ?? "");
  // A 422 naming a routine means the gateway considers it locked, even if this page thought otherwise.
  const named = current.routines.filter((r) => raw.includes(r.id));
  const locked = named.find((r) => !r.user_editable) ?? named[0];
  if (locked) {
    return `Không lưu được: “${ROUTINE_NAMES[locked.id] ?? locked.id}” là việc nền bắt buộc, không thể tắt hoặc đổi lịch.`;
  }
  if (/quiet_hours/i.test(raw)) return "Không lưu được: giờ yên lặng phải có dạng HH:MM (ví dụ 22:00).";
  if (/proactivity/i.test(raw)) return "Không lưu được: mức độ chủ động không hợp lệ.";
  if (/language/i.test(raw)) return "Không lưu được: ngôn ngữ không hợp lệ.";
  return "Không lưu được cài đặt vì có giá trị không hợp lệ. Hãy kiểm tra lại các thay đổi hoặc khôi phục cài đặt đã lưu.";
}
