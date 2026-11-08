import { ApiError, type Api, type User } from "./types";
import { bandForBirthYear } from "../lib/age";
import { makeMockCourseApi } from "./mock-course-api";
import { makeMockPlannerApi } from "./mock-planner-api";

/** In-browser mock of the backend contract (VITE_API_MOCK=1). State survives reloads in localStorage. */
const DB_KEY = "mentor.mock.users";

interface Seed {
  password: string;
  user: User;
}

function seed(): Record<string, Seed> {
  return {
    hocsinh: {
      password: "123456",
      user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: null, birth_year: null, language: null, theme: "system", quiet_until: null },
    },
    giaovien: {
      password: "123456",
      user: { id: "u-gv", role: "teacher", username: "giaovien", display_name: "Thầy Minh", age_band: null, birth_year: null, language: "vi", theme: "system", quiet_until: null },
    },
  };
}

function load(): Record<string, Seed> {
  try {
    const raw = localStorage.getItem(DB_KEY);
    if (raw) return JSON.parse(raw) as Record<string, Seed>;
  } catch {
    /* fall through to a fresh seed */
  }
  return seed();
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

export const mockApi: Api = {
  async login(username, password, role) {
    await delay();
    const db = load();
    const hit = db[username.trim().toLowerCase()];
    if (!hit || hit.password !== password) throw new ApiError(401, "invalid_credentials");
    if (hit.user.role !== role) throw new ApiError(403, "role_mismatch");
    return { token: `mock-${hit.user.id}`, user: fresh(hit).user };
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
