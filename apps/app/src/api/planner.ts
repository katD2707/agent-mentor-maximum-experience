/** Planner, goals, reminders and behaviour events (CONTRACTS.md section 12; `research` additions from section 15.8). */
import type { Milestone } from "./research-types";

export interface LiveLine {
  line_vi: string;
  line_en: string;
}

export type PlanKind = "lesson" | "review" | "practice" | "break" | "research";

export interface TodaySession {
  title_vi: string;
  title_en: string;
  date: string;
  start: string;
  is_today: boolean;
  minutes: number;
  kind: PlanKind;
  course_id: string | null;
  lesson_id: string | null;
  reason_vi: string;
  reason_en: string;
  deep_link: string;
}

export interface Today {
  date: string;
  now: string;
  /** `research` only for the university band (omitted for the others) */
  hub: { courses: LiveLine; practice: LiveLine; ask: LiveLine; progress: LiveLine; research?: LiveLine };
  today: TodaySession | null;
  week: { done: number; planned: number };
  due_review_count: number;
  quiet_until: string | null;
  plan_source: "llm" | "fallback";
}

export interface PlanItem {
  date: string;
  start: string;
  minutes: number;
  kind: PlanKind;
  course_id: string | null;
  lesson_id: string | null;
  reason_vi: string;
  reason_en: string;
  weekday: number;
  weekday_vi: string;
  label: string;
  title_vi: string;
  title_en: string;
  course_title: string;
  deep_link: string;
  /** a study session happened in this slot (always false for breaks and for sessions still to come) */
  done: boolean;
}

export type GoalStatus = "on_track" | "slightly_behind" | "behind" | "new";

export interface PlanGoalLine {
  goal_id: string;
  status: GoalStatus;
  line_vi: string;
  line_en: string;
}

export interface WeekPlan {
  generated_at: string;
  source: "llm" | "fallback";
  trigger: string;
  today: string;
  days: string[];
  items: PlanItem[];
  goals: PlanGoalLine[];
  note_vi: string;
  note_en: string;
  moves: { date: string; reason_vi: string; reason_en: string; trigger: string; at: string }[];
}

export interface Goal {
  id: string;
  title: string;
  kind: "student" | "inferred";
  deadline: string | null;
  progress_pct: number;
  status: GoalStatus;
  line_vi: string;
  line_en: string;
  course_ids: string[];
  courses: { id: string; title: string; subject: string }[];
  required_min_per_day: number | null;
  created_at: string;
  /** "research" for the one thesis goal (id `res-thesis`); absent or "learning" for the rest */
  source?: "learning" | "research";
  /** the thesis milestones of the research goal, otherwise absent or [] */
  milestones?: Milestone[];
}

export interface GoalInput {
  title: string;
  /** YYYY-MM-DD */
  deadline?: string | null;
  course_ids?: string[];
}
export type GoalPatch = Partial<GoalInput>;

export type ReminderKind = "study" | "break" | "nudge" | "research";
export type ReminderStatus = "scheduled" | "cancelled" | "skipped_quiet" | "pushed";
export type ReminderOutcome = "opened" | "ignored" | "snoozed";

export interface Reminder {
  id: string;
  /** ISO with +07:00 */
  at: string;
  kind: ReminderKind;
  text_vi: string;
  text_en: string;
  deep_link: string;
  status: ReminderStatus;
  outcome: ReminderOutcome | null;
}

export interface RemindersResponse {
  now: string;
  quiet_until: string | null;
  break_after_minutes: number;
  reminders: Reminder[];
}

export type EventKind = "app_open" | "session_start" | "session_end" | "focus_tick" | "lesson_progress" | "video_watch" | "quiz_answer" | "reminder_outcome" | "ask_question" | "ask_course_open";

export interface BehaviourEvent {
  /** client id: the server is idempotent on it */
  id: string;
  kind: EventKind;
  ts: string;
  data: Record<string, unknown>;
}

export interface EventsResult {
  accepted: number;
  duplicates: number;
  rejected: number;
}

export interface PushSubscriptionJson {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}
