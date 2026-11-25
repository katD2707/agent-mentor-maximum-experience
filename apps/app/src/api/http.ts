import { ApiError, type Api, type ApiErrorCode, type LoginResult, type User } from "./types";
import { fromWire, type Catalog, type CourseDetail, type ProgressBody, type SearchResult, type WireEnrollment, type CatalogPage, type Suggestions } from "./course";

/** `export let`: the self-contained desktop package learns its port at start-up (`initApiBase`), every module sees the update. */
export let API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) || "http://localhost:8000/api";

/**
 * Self-contained desktop package: the Rust shell starts the gateway on a free local port and answers
 * `gateway_base` with its URL once it is up. Anywhere else (browser, hosted-server installers) the command is absent or
 * returns null and VITE_API_BASE stays. Returns true when the base came from the shell.
 */
export async function initApiBase(): Promise<boolean> {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) return false;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const base = await invoke<string | null>("gateway_base");
    if (typeof base === "string" && base) {
      API_BASE = base.replace(/\/+$/, "") + "/api";
      return true;
    }
  } catch (e) {
    // an older shell has no such command: keep the configured base. Any other failure means the gateway did not start.
    if (!/not found|unknown command/i.test(String(e))) throw new Error(String(e));
  }
  return false;
}

const KNOWN_CODES: readonly string[] = ["invalid_credentials", "username_taken", "role_mismatch", "birth_year_locked", "bad_request", "bad_time", "bedtime", "quiet", "email_taken", "wrong_code", "hub_offline", "teacher_unverified", "pending", "not_owner", "level_unconfirmed", "verify_failed", "hub_not_linked", "hash_mismatch", "too_big", "script_missing", "script_failed", "bad_state"];
export const isKnownCode = (c: unknown): c is ApiErrorCode => typeof c === "string" && KNOWN_CODES.includes(c);

/** The gateway refused a course call because the teacher is not verified (any more): the app shows the gate. */
export const TEACHER_UNVERIFIED_EVENT = "mentor:teacher-unverified";
export function notifyUnverified(code: string) {
  if (code === "teacher_unverified" && typeof window !== "undefined") window.dispatchEvent(new Event(TEACHER_UNVERIFIED_EVENT));
}

export async function request<T>(method: string, path: string, opts: { token?: string; body?: unknown } = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers: {
        ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(opts.token ? { Authorization: `Bearer ${opts.token}` } : {}),
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "network");
  }
  if (!res.ok) {
    let code: ApiErrorCode = res.status === 401 ? "unauthorized" : res.status === 404 ? "not_found" : "unknown";
    try {
      const j = (await res.json()) as { error?: string };
      if (isKnownCode(j.error)) code = j.error;
    } catch {
      /* no JSON body */
    }
    notifyUnverified(code);
    throw new ApiError(res.status, code);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const qs = (o: Record<string, string | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : "";
};
const filter = (o?: { age_band?: string | null; all?: boolean }) => ({ age_band: o?.all ? undefined : (o?.age_band ?? undefined), all: o?.all ? "1" : undefined });

/** Raw GET with the Bearer token (pack bytes, asset blobs). */
export async function raw(path: string, token: string, headers: Record<string, string> = {}): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, { headers: { Authorization: `Bearer ${token}`, ...headers } });
  } catch {
    throw new ApiError(0, "network");
  }
  if (!res.ok && res.status !== 304) {
    // 503 needs_network: the course lives on Drive and this device has not downloaded it yet
    const needs = res.status === 503 && ((await res.json().catch(() => ({}))) as { error?: string }).error === "needs_network";
    throw new ApiError(res.status, needs ? "needs_network" : res.status === 401 ? "unauthorized" : res.status === 404 ? "not_found" : "unknown");
  }
  return res;
}

/** The catalog is revalidated with its ETag (§5.5); a 304 returns the copy from the last 200. */
const catalogCache = new Map<string, { etag: string; body: Catalog }>();

export const httpApi: Api = {
  login: (username, password, role) => request<LoginResult>("POST", "/auth/login", { body: role ? { username, password, role } : { username, password } }),
  signupEnabled: () => request<{ signup: boolean }>("GET", "/auth/config").then((c) => c.signup === true, () => false),
  hubEnabled: () => request<{ hub?: boolean }>("GET", "/auth/config").then((c) => c.hub === true, () => false),
  register: (username, password, role, extra) => request<LoginResult>("POST", "/auth/register", { body: { role, username, password, ...extra } }),
  forgot: (login) => request("POST", "/auth/forgot", { body: { login } }),
  forgotRequest: (login, phone) => request<void>("POST", "/auth/forgot/request", { body: phone ? { login, phone } : { login } }),
  reset: (login, code, password) => request<void>("POST", "/auth/reset", { body: { login, code, password } }),
  teacherAccount: (token) => request("GET", "/teacher/account", { token }),
  teacherVerify: (token, code) => request<void>("POST", "/teacher/account/verify", { token, body: { code } }),
  teacherResendForm: (token) => request<void>("POST", "/teacher/account/resend-form", { token }),
  teacherResendCode: (token) => request<void>("POST", "/teacher/account/resend-code", { token }),
  logout: (token) => request<void>("POST", "/auth/logout", { token }),
  getMe: (token) => request<User>("GET", "/me", { token }),
  patchMe: (token, patch) => request<User>("PATCH", "/me", { token, body: patch }),
  putQuiet: (token, until) => request<{ until: string | null }>("PUT", "/me/quiet", { token, body: { until } }),

  async getCatalog(token, opts) {
    const path = "/catalog" + qs(filter(opts));
    const hit = catalogCache.get(path);
    const res = await raw(path, token, hit ? { "If-None-Match": hit.etag } : {});
    if (res.status === 304 && hit) return hit.body;
    const body = (await res.json()) as Catalog;
    const etag = res.headers.get("ETag");
    if (etag) catalogCache.set(path, { etag, body });
    return body;
  },
  getCourse: (token, id) => request<CourseDetail>("GET", `/courses/${id}`, { token }),
  search: (token, q, opts) => request<SearchResult>("GET", "/search" + qs({ q, ...filter(opts) }), { token }),
  queryCatalog(token, query) {
    const p = new URLSearchParams();
    if (query.q) p.set("q", query.q);
    for (const [k, vs] of Object.entries(query.filters ?? {})) for (const v of vs ?? []) p.append(k, v);
    if (query.sort && query.sort !== "rel") p.set("sort", query.sort);
    if (query.sort === "dur" && query.dir) p.set("dir", query.dir);
    if (query.page && query.page > 1) p.set("page", String(query.page));
    if (query.page_size) p.set("page_size", String(query.page_size));
    const s = p.toString();
    return request<CatalogPage>("GET", "/catalog/query" + (s ? `?${s}` : ""), { token });
  },
  suggest: (token, q) => request<Suggestions>("GET", "/search/suggest" + qs({ q }), { token }),
  async mediaToken(token) {
    return (await request<{ token: string }>("POST", "/media-token", { token })).token;
  },
  async listEnrollments(token) {
    return (await request<WireEnrollment[]>("GET", "/enrollments", { token })).map(fromWire);
  },
  async enroll(token, courseId) {
    return fromWire(await request<WireEnrollment>("POST", "/enrollments", { token, body: { course_id: courseId } }));
  },
  async putProgress(token, courseId, body: ProgressBody) {
    return fromWire(await request<WireEnrollment>("PUT", `/enrollments/${courseId}/progress`, { token, body }));
  },
  unenroll: (token, courseId) => request<void>("DELETE", `/enrollments/${courseId}`, { token }),
  getToday: (token) => request("GET", "/today", { token }),
  getWeekPlan: (token) => request("GET", "/plan/week", { token }),
  listGoals: (token) => request("GET", "/goals", { token }),
  createGoal: (token, body) => request("POST", "/goals", { token, body }),
  patchGoal: (token, id, body) => request("PATCH", `/goals/${encodeURIComponent(id)}`, { token, body }),
  deleteGoal: (token, id) => request<void>("DELETE", `/goals/${encodeURIComponent(id)}`, { token }),
  getReminders: (token, since) => request("GET", "/reminders" + qs({ since }), { token }),
  async reminderOutcome(token, id, outcome) {
    await request("POST", `/reminders/${encodeURIComponent(id)}/outcome`, { token, body: { outcome } });
  },
  remindLater: (token, body) => request("POST", "/reminders", { token, body }),
  postEvents: (token, events) => request("POST", "/events", { token, body: { events } }),
  vapidPublicKey: (token) => request("GET", "/push/vapid-public-key", { token }),
  async pushSubscribe(token, subscription) {
    await request("POST", "/push/subscribe", { token, body: { subscription, device: "web" } });
  },
  async getPackBytes(token, id, v) {
    return (await raw(`/courses/${id}/versions/${v}/pack`, token)).arrayBuffer();
  },
  async getAssetBlob(token, id, v, path) {
    return (await raw(`/courses/${id}/versions/${v}/assets/${path.split("/").map(encodeURIComponent).join("/")}`, token)).blob();
  },
};
