import { ApiError, type Api, type ApiErrorCode, type LoginResult, type User } from "./types";
import { fromWire, type Catalog, type CourseDetail, type ProgressBody, type SearchResult, type WireEnrollment, type CatalogPage, type Suggestions } from "./course";

export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) || "http://localhost:8000/api";

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
      if (j.error === "invalid_credentials" || j.error === "role_mismatch" || j.error === "birth_year_locked" || j.error === "bad_request") code = j.error;
    } catch {
      /* no JSON body */
    }
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
  if (!res.ok && res.status !== 304) throw new ApiError(res.status, res.status === 401 ? "unauthorized" : res.status === 404 ? "not_found" : "unknown");
  return res;
}

/** The catalog is revalidated with its ETag (§5.5); a 304 returns the copy from the last 200. */
const catalogCache = new Map<string, { etag: string; body: Catalog }>();

export const httpApi: Api = {
  login: (username, password, role) => request<LoginResult>("POST", "/auth/login", { body: { username, password, role } }),
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
