import type { Catalog, CatalogPage, CatalogQuery, CourseDetail, Enrollment, ProgressBody, SearchResult, Suggestions } from "./course";
import type { BehaviourEvent, EventsResult, Goal, GoalInput, GoalPatch, PushSubscriptionJson, Reminder, ReminderOutcome, RemindersResponse, Today, WeekPlan } from "./planner";

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
  /** The student's character in the village (Làng gà); set at first run via PATCH /me. */
  avatar?: "nam" | "nu" | null;
  /** Hub accounts (CONTRACTS-HUB): the sign-up email; absent or null on a local account. */
  email?: string | null;
  /** Teacher approval. `null`/absent (hub off) counts as verified; only `xac_minh` may use the course pages. */
  teacher_status?: TeacherStatus | null;
}

/** chua_nop: form not sent; cho_duyet: waiting for the owner; tu_choi: rejected; da_duyet: approved, code emailed; xac_minh: code entered. */
export type TeacherStatus = "chua_nop" | "cho_duyet" | "tu_choi" | "da_duyet" | "xac_minh";

/** A teacher who may use the course pages (the hub off, or no status, counts too). */
export const teacherVerified = (u: Pick<User, "teacher_status">) => !u.teacher_status || u.teacher_status === "xac_minh";

/** Grade of the student sign-up: "1".."12" or "dh" (university). */
export type SignupGrade = string;

export interface RegisterExtra {
  display_name?: string;
  email?: string;
  grade?: SignupGrade;
  parent_email?: string;
}

export interface TeacherAccount {
  teacher_status: TeacherStatus | null;
  reject_reason: string | null;
  email: string | null;
}

export interface ForgotResult {
  via: "email" | "none";
  /** masked address, e.g. "n•••@gmail.com" */
  to?: string;
}

export type UserPatch = Partial<Pick<User, "birth_year" | "language" | "theme" | "display_name" | "avatar">>;

export interface LoginResult {
  token: string;
  user: User;
}

/** The whole backend contract the UI depends on (real HTTP and the mock both implement it). */
export interface Api {
  /** `username` may be an email; `role` is sent only without the hub (the hub login has no role cards). */
  login(username: string, password: string, role?: Role): Promise<LoginResult>;
  /** Self-contained desktop package only: GET /auth/config says whether the login screen offers "Tạo tài khoản". */
  signupEnabled?(): Promise<boolean>;
  /** GET /auth/config `hub`: central accounts and teacher approval are on. */
  hubEnabled?(): Promise<boolean>;
  /** POST /auth/register: a new account, signed in at once. `extra` (hub only) carries name, email, grade, parent email. */
  register?(username: string, password: string, role: Role, extra?: RegisterExtra): Promise<LoginResult>;
  /** POST /auth/forgot: mails a 6-digit code to the email on record, or says there is none. */
  forgot?(login: string): Promise<ForgotResult>;
  /** POST /auth/forgot/request: no email on record, so the reset request goes to the teachers. */
  forgotRequest?(login: string, phone?: string): Promise<void>;
  /** POST /auth/reset; 400 `wrong_code` */
  reset?(login: string, code: string, password: string): Promise<void>;
  /** GET /teacher/account: the approval state, fresh from the hub. */
  teacherAccount?(token: string): Promise<TeacherAccount>;
  /** POST /teacher/account/verify; 400 `wrong_code` */
  teacherVerify?(token: string, code: string): Promise<void>;
  /** POST /teacher/account/resend-form: emails the declaration form link again. */
  teacherResendForm?(token: string): Promise<void>;
  /** POST /teacher/account/resend-code: only while `da_duyet`. */
  teacherResendCode?(token: string): Promise<void>;
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
  /** "remind me at ..." (CONTRACTS 12.1); ApiError bad_time / bedtime / quiet */
  remindLater(token: string, body: { at: string; title_vi?: string; title_en?: string; deep_link?: string }): Promise<Reminder>;
  postEvents(token: string, events: BehaviourEvent[]): Promise<EventsResult>;
  // ---- Web Push (CONTRACTS.md section 5)
  vapidPublicKey(token: string): Promise<{ enabled: boolean; public_key: string | null }>;
  pushSubscribe(token: string, subscription: PushSubscriptionJson): Promise<void>;
}

export type ApiErrorCode = "invalid_credentials" | "username_taken" | "role_mismatch" | "unauthorized" | "not_found" | "coming_soon" | "birth_year_locked" | "bad_request" | "bad_time" | "bedtime" | "quiet" | "network" | "needs_network" | "email_taken" | "wrong_code" | "hub_offline" | "teacher_unverified" | "pending" | "not_owner" | "level_unconfirmed" | "verify_failed" | "hub_not_linked" | "hash_mismatch" | "too_big" | "script_missing" | "script_failed" | "bad_state" | "unknown";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: ApiErrorCode,
  ) {
    super(code);
    this.name = "ApiError";
  }
}
