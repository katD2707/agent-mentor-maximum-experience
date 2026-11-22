import { describe, expect, it } from "vitest";
import { makeMockCourseApi } from "./api/mock-course-api";
import { SOON } from "./api/mock-soon";
import type { User } from "./api";

// The mock catalog API (same rules as the gateway). The screens that use it moved to the chicken's coop:
// see lang/screens/chuong/chuong.test.tsx (search scoped to a chicken, add, preview, tree) and lang/screens/lesson/lesson.test.tsx.
const THPT = 2010; // g10_12 on the 2026 school year

describe("mock catalog query", () => {
  const user = { id: "u", role: "student", username: "u", display_name: "u", age_band: "g10_12", birth_year: THPT, language: "vi", theme: "system", quiet_until: null } as User;
  const api = makeMockCourseApi(() => user);
  const q = (query: Parameters<typeof api.queryCatalog>[1]) => api.queryCatalog("t", query);

  it("has all 107 placeholders and the 3 live courses, 10 per page", async () => {
    expect(SOON).toHaveLength(107);
    const r = await q({});
    expect(r.total).toBe(110);
    expect(r.pages).toBe(11);
    expect(r.items).toHaveLength(10);
    expect(r.items.slice(0, 3).every((c) => c.status !== "coming_soon")).toBe(true); // real courses first
    expect((await q({ page: 11 })).items).toHaveLength(10);
    expect((await q({ page: 99 })).page).toBe(11);
  });

  it("filters (AND across facets, OR inside one) with live facet counts", async () => {
    const base = await q({ filters: { band: ["g10_12"] } });
    expect(base.total).toBe(30);
    const maths = await q({ filters: { band: ["g10_12"], subject: ["Toán"] } });
    expect(maths.total).toBeGreaterThan(3);
    expect(maths.items.every((c) => c.subject === "Toán" && c.age_band === "g10_12")).toBe(true);
    // the subject facet ignores its own filter, so siblings stay visible
    const subj = Object.fromEntries(maths.facets.subject.map((o) => [o.v, o.n]));
    expect(subj["Toán"]).toBe(maths.total);
    expect(subj["Vật lí"]).toBeGreaterThan(0);
    // other facets follow the subject filter
    expect(maths.facets.status.find((o) => o.v === "coming_soon")!.n).toBe(maths.total);
    const two = await q({ filters: { band: ["g10_12"], level: ["basic", "advanced"] } });
    expect(two.total).toBe(base.facets.level.filter((o) => o.v !== "intermediate").reduce((n, o) => n + o.n, 0));
    expect((await q({ filters: { language: ["en"] } })).items.every((c) => c.language === "en")).toBe(true);
    expect((await q({ filters: { status: ["live"] } })).total).toBe(3);
  });

  it("duration buckets come from est_minutes", async () => {
    const all = await q({ page_size: 50, sort: "dur", dir: "asc" });
    const short = await q({ filters: { duration: ["short"] }, page_size: 50 });
    const medium = await q({ filters: { duration: ["medium"] }, page_size: 50 });
    const long = await q({ filters: { duration: ["long"] }, page_size: 50 });
    expect(short.items.every((c) => c.est_minutes < 60)).toBe(true);
    expect(medium.items.every((c) => c.est_minutes >= 60 && c.est_minutes <= 180)).toBe(true);
    expect(long.items.every((c) => c.est_minutes > 180)).toBe(true);
    expect(short.total + medium.total + long.total).toBe(110);
    const mins = all.items.map((c) => c.est_minutes);
    expect(mins).toEqual([...mins].sort((a, b) => a - b));
    const desc = (await q({ page_size: 50, sort: "dur", dir: "desc" })).items.map((c) => c.est_minutes);
    expect(desc).toEqual([...desc].sort((a, b) => b - a));
  });

  it("sorts by popularity (students) and newest", async () => {
    const pop = await q({ sort: "pop" });
    expect(pop.items[0].students).toBeGreaterThanOrEqual(pop.items[1].students);
    expect(pop.items[0].students).toBe(412);
    const fresh = await q({ sort: "new" });
    expect(fresh.items[0].status).not.toBe("coming_soon");
  });

  it("matches without accents and by teacher or subject", async () => {
    const a = await q({ q: "TÍCH PHÂN" });
    const b = await q({ q: "tich phan" });
    expect(a.items.map((c) => c.id)).toEqual(b.items.map((c) => c.id));
    expect(a.total).toBeGreaterThan(0);
    expect(a.items[0].title.toLowerCase()).toContain("tích phân");
    expect((await q({ q: "quang" })).items.some((c) => c.teacher_name.includes("Quang"))).toBe(true);
    expect((await q({ q: "english" })).items.every((c) => c.language === "en")).toBe(true);
  });

  it("suggests 'did you mean' for typos, not for half-typed words", async () => {
    expect((await q({ q: "tich phna" })).did_you_mean).toContain("phân");
    expect((await q({ q: "ilets" })).did_you_mean).toBe("ielts");
    expect((await q({ q: "tích ph" })).did_you_mean).toBeNull();
    const s = await api.suggest("t", "toan");
    expect(s.subjects).toContain("Toán");
    expect(s.courses.length).toBeGreaterThan(0);
    expect((await api.suggest("t", "tich phna")).did_you_mean).toBeTruthy();
  });

  it("every course has a level", async () => {
    const r = await q({ page_size: 50 });
    expect(r.items.every((c) => c.level)).toBe(true);
    expect((await q({ filters: { status: ["live"] } })).items.map((c) => c.level).sort()).toEqual(["advanced", "basic", "intermediate"]);
  });
});

