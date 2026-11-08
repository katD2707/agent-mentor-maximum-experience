import type { Catalog, CatalogPage, CatalogQuery, CourseDetail, Enrollment, ProgressBody, SearchResult, Suggestions } from "./course";
import type { BehaviourEvent, EventsResult, Goal, GoalInput, GoalPatch, PushSubscriptionJson, ReminderOutcome, RemindersResponse, Today, WeekPlan } from "./planner";

export type Role = "student" | "teacher";
export type AgeBand = "g1_5" | "g6_9" | "g10_12" | "uni";
export type Lang = "vi" | "en";
export type Theme = "light" | "dark" | "system";

export interface User {
  id: string;
  role: Role;
  username: string;
  display_name: string;
  /** Derived from birth_year; the server recomputes it per request and the app on every launch and focus. */
  age_band: AgeBand | null;
  /** Set once at first run (PATCH /me accepts it only while null); an admin corrects it. */
  birth_year: number | null;
  language: Lang | null;
  theme: Theme;
  quiet_until: string | null;
}

export type UserPatch = Partial<Pick<User, "birth_year" | "language" | "theme" | "display_name">>;

export interface LoginResult {
  token: string;
  user: User;
}

/** The whole backend contract the UI depends on (real HTTP and the mock both implement it). */
export interface Api {
  login(username: string, password: string, role: Role): Promise<LoginResult>;
  logout(token: string): Promise<void>;
  getMe(token: string): Promise<User>;
  patchMe(token: string, patch: UserPatch): Promise<User>;
  putQuiet(token: string, until: string | null): Promise<{ until: string | null }>;

  // ---- courses (§3.3, §5.4, §5.5)
  /** GET /catalog; the http client revalidates with ETag. `all` drops the age filter. */
  /** POST /media-token: short-lived token for ?t= on cover and asset URLs (<img>, <video>). */
  mediaToken(token: string): Promise<string>;
  getCatalog(token: string, opts?: { age_band?: AgeBand | null; all?: boolean }): Promise<Catalog>;
  getCourse(token: string, courseId: string): Promise<CourseDetail>;
  search(token: string, q: string, opts?: { age_band?: AgeBand | null; all?: boolean }): Promise<SearchResult>;
  /** GET /catalog/query: search, filters with facet counts, sort and paging in one call. */
  queryCatalog(token: string, query: CatalogQuery): Promise<CatalogPage>;
  /** GET /search/suggest: autocomplete groups (courses, subjects, teachers) and a typo hint. */
  suggest(token: string, q: string): Promise<Suggestions>;
  listEnrollments(token: string): Promise<Enrollment[]>;
  enroll(token: string, courseId: string): Promise<Enrollment>;
  putProgress(token: string, courseId: string, body: ProgressBody): Promise<Enrollment>;
  unenroll(token: string, courseId: string): Promise<void>;
  /** Raw pack.json bytes (so the client can verify sha256 before parsing). */
  getPackBytes(token: string, courseId: string, version: number): Promise<ArrayBuffer>;
  getAssetBlob(token: string, courseId: string, version: number, path: string): Promise<Blob>;

  // ---- planner, goals, reminders, behaviour events (CONTRACTS.md section 12)
  getToday(token: string): Promise<Today>;
  getWeekPlan(token: string): Promise<WeekPlan>;
  listGoals(token: string): Promise<Goal[]>;
  createGoal(token: string, body: GoalInput): Promise<Goal>;
  patchGoal(token: string, id: string, body: GoalPatch): Promise<Goal>;
  deleteGoal(token: string, id: string): Promise<void>;
  getReminders(token: string, since?: string): Promise<RemindersResponse>;
  reminderOutcome(token: string, id: string, outcome: ReminderOutcome): Promise<void>;
  postEvents(token: string, events: BehaviourEvent[]): Promise<EventsResult>;
  // ---- Web Push (CONTRACTS.md section 5)
  vapidPublicKey(token: string): Promise<{ enabled: boolean; public_key: string | null }>;
  pushSubscribe(token: string, subscription: PushSubscriptionJson): Promise<void>;
}

export type ApiErrorCode = "invalid_credentials" | "role_mismatch" | "unauthorized" | "not_found" | "coming_soon" | "birth_year_locked" | "bad_request" | "network" | "unknown";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: ApiErrorCode,
  ) {
    super(code);
    this.name = "ApiError";
  }
}
