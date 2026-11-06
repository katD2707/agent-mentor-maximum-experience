/** Types for `/api/practice` (CONTRACTS 10.3) and the bank asset schema (agent-mentor question-schema.md section 5). */

export type SessionKind = "practice" | "mock" | "diagnostic";
export type PracticeGoal = "balanced" | "weak" | "challenge";
export type ItemType = "SINGLE_CHOICE" | "TRUE_FALSE_GROUP" | "SHORT_ANSWER";
export type DiagnosticState = "none" | "done" | "skipped";

export interface MockProfile {
  id: string;
  label: string;
  type: string;
  item_count: number;
  time_limit_sec: number;
  disclaimer: string;
  /** CONTRACTS 10.11: contains a topic above the learner grade. */
  above_grade?: boolean;
  note?: string | null;
}

export interface PracticeTopic {
  id: string;
  title: string;
  item_count: number;
  /** CONTRACTS 10.11 */
  grade?: number | null;
  above_grade?: boolean;
}

export interface PracticeSubject {
  id: string;
  label: string;
  topics: PracticeTopic[];
  diagnostic: DiagnosticState;
  learner_grade?: number | null;
  mock_profiles: MockProfile[];
}

export interface PreviewRequest {
  subject: string;
  minutes: number;
  goal: PracticeGoal;
  topics?: string[];
  include_above_grade?: boolean;
}

export interface PracticePreview {
  seed: number | string;
  item_count: number;
  minutes: number;
  level_mix: number[];
  per_topic: { topic: string; title: string; count: number }[];
}

export interface StartSessionRequest {
  kind: SessionKind;
  subject: string;
  minutes?: number;
  goal?: PracticeGoal;
  topics?: string[];
  seed?: number | string;
  profile_id?: string;
  include_above_grade?: boolean;
}

// ---- assets ----

export interface FunctionPlotSpec {
  kind: "function_plot";
  x_min: number;
  x_max: number;
  y_min: number;
  y_max: number;
  functions: { expr: string; label?: string | null }[];
  points?: { x: number; y: number; label?: string | null }[];
  show_grid?: boolean;
}
export interface ForceDiagramSpec {
  kind: "force_diagram";
  body?: "box" | "ball" | "point" | string;
  incline_deg?: number | null;
  forces: { label: string; angle_deg: number; magnitude: number }[];
}
export interface GeometrySpec {
  kind: "geometry";
  points: { id: string; x: number; y: number; label?: string | null }[];
  segments?: { from: string; to: string; dashed?: boolean; label?: string | null }[];
  circles?: { center: string; radius: number; dashed?: boolean }[];
  right_angles?: { vertex: string; from: string; to: string }[];
}
export type DiagramSpec = FunctionPlotSpec | ForceDiagramSpec | GeometrySpec;

export interface PracticeAsset {
  id: string;
  type: "diagram" | "table" | "image";
  alt_text: string;
  caption?: string | null;
  diagram?: DiagramSpec | null;
  table?: { headers: string[]; rows: string[][] } | null;
  image?: { sha256: string; media_type: string; width: number; height: number; byte_size?: number } | null;
}

// ---- session ----

export interface ClientItem {
  position: number;
  id: string;
  type: ItemType;
  stem: string;
  options?: { id: string; text: string }[];
  statements?: { id: string; text: string; truth?: boolean; explanation?: string | null }[];
  short_answer?: { max_chars: number | null; decimals?: number | null; unit?: string | null; hint?: string | null };
  assets: PracticeAsset[];
  topic: string;
  topic_title: string;
  level: number;
  estimated_seconds: number;
  has_hint?: boolean;
}

export interface AnswerState {
  answer?: string | null;
  draft?: string | null;
  flagged?: boolean;
  checked?: boolean;
  correct?: boolean | null;
  points?: number | null;
  /** Practice, once checked: the `/answer` response, so feedback survives a reload (CONTRACTS 10.9). */
  result?: AnswerResult | null;
  /** Practice: the hint text once one was used. */
  hint?: string | null;
  revealed?: boolean;
}

export interface SessionPart {
  label: string;
  positions: number[];
  points_each: number;
}

export interface Session {
  id: string;
  kind: SessionKind;
  subject: string;
  profile_id?: string | null;
  started_at: string;
  deadline?: string | null;
  /** Seconds left, when the gateway computes it (resume). */
  remaining_sec?: number | null;
  elapsed_sec?: number;
  position: number;
  /** `active | finished | expired | abandoned` (P); a session that is not active goes to its summary. */
  status?: string;
  items: ClientItem[];
  answers: Record<string, AnswerState>;
  parts?: SessionPart[] | null;
  disclaimer?: string | null;
  label?: string;
  finished?: boolean;
  finished_at?: string | null;
}

/** Practice answer result; mock/diagnostic return `{saved: true}`. */
export interface AnswerResult {
  saved?: boolean;
  /** null = a blank answer (a skip). */
  correct?: boolean | null;
  points?: number;
  max_points?: number;
  correct_answer?: string;
  option_feedback?: Record<string, string> | string | null;
  statement_results?: (boolean | { id?: string; correct: boolean; truth?: boolean })[] | null;
}

export interface RevealResult {
  explanation: string;
  tip?: string | null;
  assets?: PracticeAsset[];
  statements?: { id: string; truth: boolean; explanation?: string | null }[];
}

export interface TopicResult {
  topic: string;
  title: string;
  right: number;
  total: number;
  mastery_before: number | null;
  mastery_after: number | null;
  label: string;
}

/** `per_part` entry: P sends `{part, label, total, answered, correct, points, max_points}`; `items`/`fully_correct` are older spellings. */
export interface PartResult {
  part?: number;
  label: string;
  total?: number;
  items?: number;
  answered?: number;
  correct?: number;
  fully_correct?: number;
  points: number;
  max_points: number;
  type?: ItemType | string;
}

export interface PracticeRecommendation {
  code: string;
  subject: string;
  title: string;
  reason: string;
  action: { kind: "practice" | "mock" | "diagnostic" | "break" | "progress"; params?: Record<string, unknown> };
}

export interface Report {
  session: Pick<Session, "id" | "kind" | "subject"> & Partial<Session>;
  /** Practice and diagnostic: `total` = answered. Mock: all items, blanks count 0. */
  correct: number;
  total: number;
  answered: number;
  score_10?: number | null;
  minutes: number;
  hints: number;
  per_topic: TopicResult[];
  per_part?: PartResult[] | null;
  recommendations: PracticeRecommendation[];
  disclaimer?: string | null;
}

export interface SessionSummary {
  id: string;
  kind: SessionKind;
  subject: string;
  started_at: string;
  finished_at?: string | null;
  score_10?: number | null;
  correct: number;
  total: number;
  minutes: number;
}

export interface ReviewItem extends ClientItem {
  answer?: string | null;
  correct?: boolean | null;
  points?: number | null;
  correct_answer: string;
  explanation?: string;
  tip?: string | null;
  option_feedback?: Record<string, string> | null;
  statement_results?: AnswerResult["statement_results"];
  max_points?: number | null;
  hint?: string | null;
  statement_explanations?: { id: string; truth: boolean; explanation?: string | null }[];
  solution_assets?: PracticeAsset[];
}

export interface ItemReportRequest {
  session_id: string;
  reason: ItemReportReason;
  note?: string;
}
export type ItemReportReason = "wrong_key" | "wrong_solution" | "unclear" | "typo" | "other";

export interface ProgressSkill {
  skill_id: string;
  title: string;
  topic: string;
  mastery: number | null;
  evidence: number;
  confidence: "high" | "medium" | "low";
  label: string;
  trend: { at: string; mastery: number }[];
}

export interface PracticeItemReport {
  id: string | number;
  item_id: string;
  reason: ItemReportReason;
  status: string;
  created_at?: string;
}

/** Everything the web UI needs from `/api/practice`. */
export interface PracticeApi {
  subjects(): Promise<PracticeSubject[]>;
  preview(body: PreviewRequest): Promise<PracticePreview>;
  start(body: StartSessionRequest): Promise<Session>;
  skipDiagnostic(subject: string): Promise<{ ok: boolean }>;
  active(subject?: string): Promise<Session | null>;
  get(id: string): Promise<Session>;
  answer(id: string, body: { position: number; answer: string | null; time_spent_sec: number }): Promise<AnswerResult>;
  hint(id: string, position: number): Promise<{ hint: string }>;
  reveal(id: string, position: number): Promise<RevealResult>;
  flag(id: string, position: number, flagged: boolean): Promise<{ ok: boolean }>;
  tick(id: string, position: number, elapsedSec: number): Promise<{ remaining_sec?: number | null }>;
  finish(id: string): Promise<Report>;
  list(opts?: { subject?: string; limit?: number }): Promise<SessionSummary[]>;
  review(id: string): Promise<{ session?: Partial<Session>; items: ReviewItem[] } | ReviewItem[]>;
  progress(subject?: string): Promise<{ skills: ProgressSkill[] }>;
  recommendations(subject?: string): Promise<PracticeRecommendation[]>;
  reportItem(itemId: string, body: ItemReportRequest): Promise<{ id: string | number; status: string }>;
  itemReports(): Promise<PracticeItemReport[]>;
}
