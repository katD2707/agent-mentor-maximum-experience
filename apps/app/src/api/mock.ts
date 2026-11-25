import { ApiError, type Api, type TeacherAccount, type TeacherStatus, type User } from "./types";
import { bandForBirthYear } from "../lib/age";
import { makeMockCourseApi } from "./mock-course-api";
import { makeMockPlannerApi } from "./mock-planner-api";

/** In-browser mock of the backend contract (VITE_API_MOCK=1). State survives reloads in localStorage. */
const DB_KEY = "mentor.mock.users";

interface Seed {
  password: string;
  user: User;
  /** hub demo: why a teacher was rejected */
  reject_reason?: string | null;
  parent_email?: string | null;
}

/**
 * The hub flavour of the mock (central accounts, teacher approval, "Gửi duyệt"): off by default so the plain mock keeps
 * today's behaviour. Turn it on with `?hub=1` in the address (remembered) or `localStorage["mentor.mock.hub"] = "1"`; `?hub=0` turns it off.
 */
const HUB_KEY = "mentor.mock.hub";
export function mockHubOn(): boolean {
  try {
    const q = typeof location !== "undefined" ? new URLSearchParams(location.search).get("hub") : null;
    if (q === "1" || q === "0") localStorage.setItem(HUB_KEY, q);
    return localStorage.getItem(HUB_KEY) === "1";
  } catch {
    return false;
  }
}
/** The code every mock mail carries (reset and teacher verification). */
export const MOCK_CODE = "482913";

/** Teacher accounts in each approval state, to see every gate screen: log in as one of these (password 123456). */
function hubDemos(): Record<string, Seed> {
  const t = (id: string, username: string, name: string, status: TeacherStatus, email: string, reason?: string): Seed => ({
    password: "123456",
    reject_reason: reason ?? null,
    user: { id, role: "teacher", username, display_name: name, age_band: null, birth_year: null, language: "vi", theme: "system", quiet_until: null, email, teacher_status: status },
  });
  return {
    "gv-chuanop": t("u-gv1", "gv-chuanop", "Cô Hằng", "chua_nop", "nguyenthuhang.gv@gmail.com"),
    "gv-cho": t("u-gv2", "gv-cho", "Thầy Nam", "cho_duyet", "nam.gv@gmail.com"),
    "gv-tuchoi": t("u-gv3", "gv-tuchoi", "Cô Lan", "tu_choi", "lan.gv@gmail.com", "Ảnh chứng chỉ mờ, không đọc được số."),
    "gv-duyet": t("u-gv4", "gv-duyet", "Thầy Bình", "da_duyet", "binh.gv@gmail.com"),
    "gv-xacminh": t("u-gv5", "gv-xacminh", "Cô Mai", "xac_minh", "mai.gv@gmail.com"),
  };
}

function seed(): Record<string, Seed> {
  return {
    hocsinh: {
      password: "123456",
      user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: null, birth_year: null, language: null, theme: "system", quiet_until: null },
    },
    giaovien: {
      password: "123456",
      user: { id: "u-gv", role: "teacher", username: "giaovien", display_name: "Thầy Minh", age_band: null, birth_year: null, language: "vi", theme: "system", quiet_until: null, email: "giaovien@gmail.com" },
    },
  };
}

function load(): Record<string, Seed> {
  const demos = mockHubOn() ? hubDemos() : {};
  try {
    const raw = localStorage.getItem(DB_KEY);
    if (raw) return { ...demos, ...(JSON.parse(raw) as Record<string, Seed>) };
  } catch {
    /* fall through to a fresh seed */
  }
  return { ...seed(), ...demos };
}

function save(db: Record<string, Seed>) {
  try {
    localStorage.setItem(DB_KEY, JSON.stringify(db));
  } catch {
    /* ignore */
  }
}

const delay = () => new Promise((r) => setTimeout(r, 120));

/** Saved mock users from before birth years have none: they go through first run again. The band is always derived. */
function fresh(seed: Seed): Seed {
  const birth = seed.user.birth_year ?? null;
  seed.user = { ...seed.user, birth_year: birth, age_band: bandForBirthYear(birth) };
  return seed;
}

function byToken(db: Record<string, Seed>, token: string): Seed {
  const hit = Object.values(db).find((s) => `mock-${s.user.id}` === token);
  if (!hit) throw new ApiError(401, "unauthorized");
  return fresh(hit);
}

/** The signed-in mock user (throws 401 for an unknown token), shared with the other mock APIs. */
export const mockUserOf = (token: string): User => byToken(load(), token).user;

const maskMail = (m: string) => {
  const [a, b] = m.split("@");
  return `${a.slice(0, 1)}•••@${b}`;
};
/** A user by username or by email (the hub login takes either). */
function find(db: Record<string, Seed>, login: string): Seed | undefined {
  const k = login.trim().toLowerCase();
  return db[k] ?? Object.values(db).find((s) => s.user.email?.toLowerCase() === k || s.parent_email === k);
}

export const mockApi: Api = {
  async login(username, password, role) {
    await delay();
    const db = load();
    const hit = find(db, username);
    if (!hit || hit.password !== password) throw new ApiError(401, "invalid_credentials");
    if (role && hit.user.role !== role) throw new ApiError(403, "role_mismatch");
    return { token: `mock-${hit.user.id}`, user: fresh(hit).user };
  },
  async hubEnabled() {
    return mockHubOn();
  },
  async signupEnabled() {
    return mockHubOn();
  },
  async register(username, password, role, extra) {
    await delay();
    if (!mockHubOn()) throw new ApiError(404, "not_found");
    const db = load();
    const name = username.trim().toLowerCase();
    if (!/^[a-z0-9][a-z0-9._-]{1,31}$/.test(name) || password.length < 6 || (role === "teacher" && !extra?.email)) throw new ApiError(422, "bad_request");
    if (db[name]) throw new ApiError(409, "username_taken");
    const mail = extra?.email?.trim().toLowerCase();
    if (mail && Object.values(db).some((s) => s.user.email?.toLowerCase() === mail)) throw new ApiError(409, "email_taken");
    const year = new Date().getFullYear();
    const g = extra?.grade;
    const birth = role === "student" && g ? (g === "dh" ? year - 20 : year - 6 - Number(g)) : null;
    const seed: Seed = {
      password,
      parent_email: extra?.parent_email?.trim().toLowerCase() || null,
      user: { id: `u-${name}`, role, username: name, display_name: extra?.display_name?.trim() || name, age_band: null, birth_year: birth, language: null, theme: "system", quiet_until: null, email: mail ?? null, teacher_status: role === "teacher" ? "chua_nop" : null },
    };
    db[name] = seed;
    save(db);
    return { token: `mock-${seed.user.id}`, user: fresh(seed).user };
  },
  async forgot(login) {
    await delay();
    const hit = find(load(), login);
    const mail = hit?.user.email ?? hit?.parent_email;
    return mail ? { via: "email", to: maskMail(mail) } : { via: "none" };
  },
  async forgotRequest(login, phone) {
    await delay();
    try {
      const x = JSON.parse(sessionStorage.getItem("mentor-mock-reset") || "[]") as unknown[];
      x.push({ user: login, phone: phone ?? "" });
      sessionStorage.setItem("mentor-mock-reset", JSON.stringify(x));
    } catch {
      /* the mock list is only for show */
    }
  },
  async reset(login, code, password) {
    await delay();
    const db = load();
    const hit = find(db, login);
    if (!hit || code !== MOCK_CODE) throw new ApiError(400, "wrong_code");
    hit.password = password;
    save(db);
  },
  async teacherAccount(token) {
    await delay();
    const hit = byToken(load(), token);
    const a: TeacherAccount = { teacher_status: hit.user.teacher_status ?? null, reject_reason: hit.reject_reason ?? null, email: hit.user.email ?? null };
    return a;
  },
  async teacherVerify(token, code) {
    await delay();
    const db = load();
    const hit = byToken(db, token);
    if (hit.user.teacher_status !== "da_duyet" || code !== MOCK_CODE) throw new ApiError(400, "wrong_code");
    hit.user = { ...hit.user, teacher_status: "xac_minh" };
    save(db);
  },
  async teacherResendForm() {
    await delay();
  },
  async teacherResendCode() {
    await delay();
  },
  async logout() {
    await delay();
  },
  async getMe(token) {
    await delay();
    return byToken(load(), token).user;
  },
  async patchMe(token, patch) {
    await delay();
    const db = load();
    const hit = byToken(db, token);
    // same rules as the gateway: the birth year is set once, the band follows from it
    if (patch.birth_year != null) {
      if (hit.user.birth_year != null) throw new ApiError(409, "birth_year_locked");
      if (!Number.isInteger(patch.birth_year) || patch.birth_year < 1950 || patch.birth_year > 2025) throw new ApiError(422, "bad_request");
    }
    hit.user = { ...hit.user, ...patch };
    if (hit.user.birth_year != null) hit.user.age_band = bandForBirthYear(hit.user.birth_year);
    save(db);
    return hit.user;
  },
  async putQuiet(token, until) {
    await delay();
    const db = load();
    const hit = byToken(db, token);
    hit.user = { ...hit.user, quiet_until: until };
    save(db);
    return { until };
  },
  ...makeMockCourseApi(mockUserOf),
  ...makeMockPlannerApi(mockUserOf),
};
