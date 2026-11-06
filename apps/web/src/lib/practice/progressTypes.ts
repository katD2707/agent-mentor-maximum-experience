/** Shapes of CONTRACTS section 10.3 used by the progress screens (W2). */

export type Confidence = "high" | "medium" | "low";

export const PROGRESS_LABELS = ["Chưa có dữ liệu", "Cần thêm dữ liệu", "Cần củng cố", "Đang tiến bộ", "Vững"] as const;
export type ProgressLabel = (typeof PROGRESS_LABELS)[number];

export interface TrendPoint {
  at: string;
  mastery: number;
}

export interface ProgressSkill {
  skill_id: string;
  title: string;
  topic?: string | null;
  mastery: number;
  evidence: number;
  confidence: Confidence;
  label: string;
  trend: TrendPoint[];
}

export interface ProgressTopic {
  topic: string;
  title: string;
}

export interface Progress {
  skills: ProgressSkill[];
  /** Display titles per topic id (gateway CONTRACTS 10.9); older mocks may omit it. */
  topics?: ProgressTopic[];
}

export type RecommendationCode =
  | "TAKE_A_BREAK"
  | "TAKE_DIAGNOSTIC"
  | "PRACTICE_WEAK"
  | "PROBE_UNKNOWN"
  | "CHALLENGE_STRONG"
  | "TAKE_MOCK"
  | "REDIAGNOSE";

export interface RecommendationAction {
  kind: "practice" | "mock" | "diagnostic" | "break" | "progress";
  params?: Record<string, unknown>;
}

export interface Recommendation {
  code: RecommendationCode | string;
  subject?: string | null;
  title: string;
  reason: string;
  action: RecommendationAction;
}

export interface SessionSummary {
  id: string;
  kind: "practice" | "mock" | "diagnostic";
  subject: string;
  started_at: string;
  finished_at?: string | null;
  score_10?: number | null;
  correct: number;
  total: number;
  minutes: number;
}
