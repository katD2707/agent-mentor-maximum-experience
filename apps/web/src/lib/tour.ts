/**
 * First-run tour: the rules, as pure functions (tour.test.ts), plus the tiny event bus the screens use to say
 * "the learner just did the thing this step waits for". State itself lives on the gateway (`Me.tour`).
 */
import { PAPER_PROMPTS } from "./setupGuide";
import type { Me, Role, TourState, TourStepId } from "./types";

export type TourSurface = "app" | "popup";

export const TOUR_ORDER: readonly TourStepId[] = ["welcome", "ask", "practice", "time"];

/** Steps shown to this learner: NCS has no practice step; the pop-up is a 2-step mini tour (no welcome card). */
export function tourSteps(role: Role | null, surface: TourSurface): TourStepId[] {
  if (surface === "popup") return ["ask", "time"];
  return role === "ncs" ? ["welcome", "ask", "time"] : ["welcome", "ask", "practice", "time"];
}

/** The step to show for a saved step: itself, or the next one this surface has (e.g. pop-up resuming at "practice"). */
export function resolveStep(list: readonly TourStepId[], saved: TourStepId | null): TourStepId | null {
  if (!saved) return null;
  const from = TOUR_ORDER.indexOf(saved);
  return list.find((s) => TOUR_ORDER.indexOf(s) >= from) ?? null;
}

/** null = after the last step (the finish moment). */
export function nextStep(list: readonly TourStepId[], current: TourStepId): TourStepId | null {
  const i = list.indexOf(current);
  return i >= 0 && i + 1 < list.length ? list[i + 1] : null;
}

/** "Bước 2/3": the welcome card is not counted. */
export function stepCounter(list: readonly TourStepId[], step: TourStepId): { index: number; total: number } | null {
  const real: TourStepId[] = list.filter((s) => s !== "welcome");
  const i = real.indexOf(step);
  return i < 0 ? null : { index: i + 1, total: real.length };
}

export function tourFinished(t: TourState | undefined): boolean {
  return !!t && (t.tour_completed_at !== null || t.tour_skipped_at !== null);
}

/** Start by itself once: onboarding done, never started or finished, and not a learner who already closed the old guide. */
export function shouldAutoStart(me: Me): boolean {
  const t = me.tour;
  if (!t || me.onboarding_state !== "active" || !me.role) return false;
  if (t.tour_step !== null || tourFinished(t)) return false;
  return me.setup_guide_dismissed_at === null;
}

/** A saved step on an unfinished tour: pick it up where it was left. */
export function shouldResume(me: Me): boolean {
  const t = me.tour;
  return !!t && me.onboarding_state === "active" && t.tour_step !== null && !tourFinished(t);
}

// ---- signals from the screens ----

export type TourSignal = "message-sent" | "diagnostic-answered" | "diagnostic-skipped";
const EVENT = "mentor:tour-signal";

export function emitTourSignal(signal: TourSignal): void {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent<TourSignal>(EVENT, { detail: signal }));
}

export function onTourSignal(handler: (s: TourSignal) => void): () => void {
  const h = (e: Event) => handler((e as CustomEvent<TourSignal>).detail);
  window.addEventListener(EVENT, h);
  return () => window.removeEventListener(EVENT, h);
}

/** Which signal finishes which step. "practice" also moves on by the learner's own "Bỏ qua" (not a signal). */
export function completes(step: TourStepId, signal: TourSignal): boolean {
  if (step === "ask") return signal === "message-sent";
  if (step === "practice") return signal === "diagnostic-answered" || signal === "diagnostic-skipped";
  return false;
}

// ---- copy ----

export function welcomeText(name: string, role: Role | null): string {
  const n = name.trim();
  const hi = n ? `Chào ${n}!` : "Chào bạn!";
  return role === "ncs" ? `${hi} Mình là Mầm. 2 bước, chưa tới 1 phút nhé.` : `${hi} Mình là Mầm. 3 bước, chưa tới 1 phút nhé.`;
}

export const SAMPLE_PROMPTS: Record<"thpt" | "ncs", string[]> = {
  thpt: ["Em giải x² − 5x + 6 = 0 ra x = −2 và x = −3, sai ở đâu ạ?", "Gợi ý cho em cách bắt đầu bài tích phân này"],
  ncs: [PAPER_PROMPTS[0], PAPER_PROMPTS[2]],
};

export const STEP_TEXT = {
  ask: {
    thpt: { title: "Hỏi bài", body: "Gửi Mầm một bài em đang làm dở — gõ hoặc chụp ảnh." },
    ncs: { title: "Hỏi việc", body: "Gửi Mầm một việc nghiên cứu đang dở — một câu hỏi, đoạn nháp hay chủ đề cần tìm paper." },
  },
  practice: { title: "Luyện nhanh", body: "5 câu nhanh để Mầm biết em đang ở đâu." },
  time: {
    thpt: { title: "Giờ học", body: "Em hay học lúc mấy giờ? Mầm sẽ nhắc nhẹ." },
    ncs: { title: "Giờ làm việc", body: "Bạn hay chốt việc trong ngày lúc mấy giờ? Mầm sẽ nhắc nhẹ." },
  },
} as const;

// ---- contextual tips (one line from Mầm, shown once per tip) ----

export interface Tip {
  id: string;
  text: string;
}

const TIPS: { id: string; path: RegExp; roles: Role[]; text: string }[] = [
  { id: "progress", path: /^\/progress(\/|$)/, roles: ["thpt"], text: "Mức thành thạo dựa trên bài em tự làm, không phải điểm thi." },
  { id: "plans", path: /^\/plans(\/|$)/, roles: ["thpt", "ncs"], text: "Tick khi xong một mốc — Mầm sẽ chúc mừng." },
  { id: "practice", path: /^\/practice\/?$/, roles: ["thpt"], text: "Chọn thời lượng rồi bấm Bắt đầu, phím 1–4 để chọn nhanh." },
];

/** The tip for this page, or null: unknown page, wrong role, already seen, or the tour itself is on screen. */
export function tipFor(pathname: string, role: Role | null, state: TourState | undefined, tourOpen: boolean): Tip | null {
  if (!state || !role || tourOpen) return null;
  const t = TIPS.find((x) => x.path.test(pathname) && x.roles.includes(role));
  if (!t || state.tips_seen.includes(t.id)) return null;
  return { id: t.id, text: t.text };
}
