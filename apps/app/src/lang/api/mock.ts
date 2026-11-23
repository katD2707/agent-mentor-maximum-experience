import { ApiError, type User } from "../../api/types";
import { mockApi, mockUserOf } from "../../api/mock";
import { chickenOfCourse } from "../chickenOf";
import { levelOf, stageOf, subjectOf, subjectsFor, xpInLevel } from "../subjects";
import type { ArenaPaper, Chicken, ChatMessage, FocusActive, LgApi, Market, NewsItem, NotesSet, Speaker, XpWeek } from "./types";

/** In-browser mock of the Làng gà endpoints (VITE_API_MOCK=1). State survives reloads in localStorage, per user. */
interface Own {
  id: string;
  xp: number;
  taken_at: string;
}
interface State {
  chickens: Own[];
  /** chickens let go: their XP is kept and comes back when they are taken again */
  kept: Record<string, number>;
  news: NewsItem[];
  focus: { id: string; ends_at: string; chicken: string; minutes: number; paused_at?: string } | null;
  chat: Record<string, ChatMessage[]>;
  notes: NotesSet[];
  week: Record<string, number[]>;
  /** week XP by source, per chicken (what lg-09 lists) */
  sources?: Record<string, Record<string, number>>;
}

const delay = () => new Promise((r) => setTimeout(r, 60));
const key = (uid: string) => `mentor.mock.lg.${uid}`;
const empty = (): State => ({ chickens: [], kept: {}, news: [], focus: null, chat: {}, notes: [], week: {} });

function focusView(f: NonNullable<State["focus"]>): FocusActive {
  const at = f.paused_at ? new Date(f.paused_at).getTime() : Date.now();
  const ends = new Date(f.ends_at).getTime();
  return { id: f.id, ends_at: f.ends_at, chicken: f.chicken, minutes: f.minutes, started_at: new Date(ends - f.minutes * 60000).toISOString(), remaining_sec: Math.max(0, Math.round((ends - at) / 1000)), status: f.paused_at ? "paused" : "active", ...(f.paused_at ? { paused_at: f.paused_at } : {}) };
}

function load(uid: string): State {
  try {
    const raw = localStorage.getItem(key(uid));
    if (raw) return { ...empty(), ...(JSON.parse(raw) as State) };
  } catch {
    /* fresh state */
  }
  return empty();
}
function save(uid: string, s: State) {
  try {
    localStorage.setItem(key(uid), JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

/** How many courses the mock says a chicken has (stable per id). */
export const mockCourseCount = (id: string): number => 1 + ((id.charCodeAt(0) + id.length * 3) % 9);

function toChicken(o: Own): Chicken {
  const s = subjectOf(o.id);
  const level = levelOf(o.xp);
  return {
    id: o.id,
    name_vi: `Gà ${s?.vi ?? o.id}`,
    name_en: `${s?.en ?? o.id} chicken`,
    art: s?.art ?? o.id,
    level,
    xp: o.xp,
    xp_in_level: xpInLevel(o.xp),
    stage: stageOf(level),
    courses: mockCourseCount(o.id),
    active_course: o.id === "toan" ? { id: "mock", title: "Cấp số cộng", percent: 40 } : null,
    done_today: o.id === "van",
    taken_at: o.taken_at,
  };
}

const push = (s: State, n: Omit<NewsItem, "id" | "at">) => {
  s.news = [{ ...n, id: `n-${Date.now().toString(36)}-${s.news.length}`, at: new Date().toISOString() }, ...s.news].slice(0, 30);
};

/** Test and demo helper: give a chicken XP (a level-up line lands in the news). Returns true on a level-up. */
export function mockGiveXp(token: string, chicken: string, amount: number): boolean {
  const u = mockUserOf(token);
  const s = load(u.id);
  const c = s.chickens.find((x) => x.id === chicken);
  if (!c) return false;
  const before = levelOf(c.xp);
  c.xp += amount;
  const up = levelOf(c.xp) > before;
  if (up) push(s, { chicken, kind: "level_up", text_vi: `Gà ${subjectOf(chicken)?.vi ?? chicken} lên cấp ${levelOf(c.xp)}. Giỏi lắm!`, text_en: `${subjectOf(chicken)?.en ?? chicken} chicken reached level ${levelOf(c.xp)}. Well done!` });
  save(u.id, s);
  return up;
}

/** What a chicken says when today's lesson is another subject's: one of its own courses from the catalog, else a plain greeting. */
async function ownLesson(token: string, chicken: string): Promise<Speaker> {
  const cat = await mockApi.getCatalog(token).catch(() => null);
  const own = cat?.courses.find((c) => chickenOfCourse(c) === chicken);
  const title = own?.title.split(":").pop()?.trim();
  if (!own || !title) return { chicken, line_vi: "Hôm nay mình học gì nhỉ?", line_en: "What shall we learn today?", action: null };
  return { chicken, line_vi: `10 phút ${title}`, line_en: `10 min ${title}`, action: { kind: "lesson", deep_link: `/khoa-hoc/${own.id}`, minutes: 10 } };
}

export const mockLg: LgApi = {
  async getVillage(token) {
    await delay();
    const u: User = mockUserOf(token);
    const s = load(u.id);
    const today = await mockApi.getToday(token).catch(() => null);
    const chickens = s.chickens.map(toChicken);
    let speaker: Speaker | null = null;
    if (chickens.length) {
      const t = today?.today ?? null;
      // the chicken speaks of its own course: today's lesson belongs to the chicken of that course, else a plain greeting
      const cid = /^\/khoa-hoc\/([^/?#]+)/.exec(t?.deep_link ?? "")?.[1];
      const info = cid ? await mockApi.getCourse(token, decodeURIComponent(cid)).catch(() => null) : null;
      const owner = info ? chickens.find((c) => c.id === chickenOfCourse(info)) : undefined;
      const who = owner ?? chickens.find((c) => c.id === "toan") ?? chickens[0];
      speaker = t && owner
        ? { chicken: who.id, line_vi: t.title_vi, line_en: t.title_en, action: { kind: t.kind, deep_link: t.deep_link, minutes: t.minutes } }
        : await ownLesson(token, who.id);
    }
    return {
      chickens,
      speaker,
      news: s.news,
      streak: today?.streak ?? { days: 0, today_done: false },
      week: today?.week ?? { done: 0, planned: 0 },
    };
  },
  async getMarket(token) {
    await delay();
    const u = mockUserOf(token);
    const s = load(u.id);
    const band = u.age_band ?? "g10_12";
    const m: Market = {
      stage: band,
      chickens: subjectsFor(band).map((x) => ({ id: x.id, name_vi: `Gà ${x.vi}`, name_en: `${x.en} chicken`, art: x.art, courses: mockCourseCount(x.id), owned: s.chickens.some((c) => c.id === x.id) })),
    };
    return m;
  },
  async takeChicken(token, chicken) {
    await delay();
    const u = mockUserOf(token);
    const s = load(u.id);
    if (!subjectsFor(u.age_band ?? "g10_12").some((x) => x.id === chicken)) throw new ApiError(400, "bad_request");
    if (s.chickens.some((c) => c.id === chicken)) throw new ApiError(409, "unknown");
    const own: Own = { id: chicken, xp: s.kept[chicken] ?? 0, taken_at: new Date().toISOString() };
    delete s.kept[chicken];
    s.chickens.push(own);
    const sub = subjectOf(chicken);
    push(s, { chicken, kind: "course", text_vi: `Em nhận Gà ${sub?.vi}. Tìm khóa trong chuồng của gà nhé.`, text_en: `You took the ${sub?.en} chicken. Find its courses in its coop.` });
    save(u.id, s);
    return toChicken(own);
  },
  async letGo(token, chicken) {
    await delay();
    const u = mockUserOf(token);
    const s = load(u.id);
    const c = s.chickens.find((x) => x.id === chicken);
    if (c) s.kept[chicken] = c.xp;
    s.chickens = s.chickens.filter((x) => x.id !== chicken);
    save(u.id, s);
  },
  async getChicken(token, chicken) {
    await delay();
    const u = mockUserOf(token);
    const s = load(u.id);
    const c = s.chickens.find((x) => x.id === chicken);
    if (!c) throw new ApiError(404, "not_found");
    return { chicken: toChicken(c), week_xp: s.week[chicken] ?? [0, 0, 0, 0, 0, 0, 0] };
  },
  async xpWeek(token) {
    await delay();
    const u = mockUserOf(token);
    const s = load(u.id);
    const today = new Date();
    const days = Array.from({ length: 7 }, (_, i) => {
      const d = new Date(today);
      d.setDate(d.getDate() - (6 - i));
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    });
    const chickens = s.chickens.map((c) => {
      const t = toChicken(c);
      const week = s.week[c.id] ?? [0, 0, 0, 0, 0, 0, 0];
      return { chicken: c.id, owned: true, level: t.level, xp: t.xp, xp_in_level: t.xp_in_level, stage: t.stage, week, week_total: week.reduce((a, b) => a + b, 0), by_source: s.sources?.[c.id] ?? {} };
    });
    const out: XpWeek = { days, chickens, total: chickens.reduce((a, c) => a + c.week_total, 0) };
    return out;
  },
  async focusStart(token, body) {
    await delay();
    const u = mockUserOf(token);
    const s = load(u.id);
    s.focus = { id: `f-${Date.now().toString(36)}`, ends_at: new Date(Date.now() + body.minutes * 60000).toISOString(), chicken: body.chicken, minutes: body.minutes };
    save(u.id, s);
    return { id: s.focus.id, ends_at: s.focus.ends_at, chicken: body.chicken, minutes: body.minutes };
  },
  async focusFinish(token, id, minutesDone) {
    await delay();
    const u = mockUserOf(token);
    const s = load(u.id);
    const f = s.focus;
    const own = s.chickens.find((c) => c.id === f?.chicken);
    if (!f || f.id !== id || !own) throw new ApiError(404, "not_found");
    // the gateway's rule: +1 a minute (never above the planned minutes) and +5 more for a session done in full
    const done = Math.max(0, Math.min(Math.floor(minutesDone), f.minutes));
    const xp = done + (done >= f.minutes ? 5 : 0);
    const before = levelOf(own.xp);
    own.xp += xp;
    const wk = (s.week[own.id] ??= [0, 0, 0, 0, 0, 0, 0]);
    wk[6] += xp;
    const src = ((s.sources ??= {})[own.id] ??= {});
    src.focus = (src.focus ?? 0) + done;
    if (done >= f.minutes) src.focus_full = (src.focus_full ?? 0) + 5;
    if (levelOf(own.xp) > before) push(s, { chicken: own.id, kind: "level_up", text_vi: `Gà ${subjectOf(own.id)?.vi ?? own.id} lên cấp ${levelOf(own.xp)}. Giỏi lắm!`, text_en: `${subjectOf(own.id)?.en ?? own.id} chicken reached level ${levelOf(own.xp)}. Well done!` });
    s.focus = null;
    save(u.id, s);
    return { xp, minutes_done: done, daily_cap: 120, chicken: toChicken(own) };
  },
  async focusActive(token) {
    await delay();
    const f = load(mockUserOf(token).id).focus;
    const a: FocusActive | null = f ? focusView(f) : null;
    return a;
  },
  async focusPause(token, id, agoSec = 0) {
    await delay();
    const u = mockUserOf(token);
    const s = load(u.id);
    if (!s.focus || s.focus.id !== id) throw new ApiError(404, "not_found");
    if (!s.focus.paused_at) s.focus.paused_at = new Date(Date.now() - agoSec * 1000).toISOString();
    save(u.id, s);
    return focusView(s.focus);
  },
  async focusResume(token, id) {
    await delay();
    const u = mockUserOf(token);
    const s = load(u.id);
    if (!s.focus || s.focus.id !== id) throw new ApiError(404, "not_found");
    if (s.focus.paused_at) {
      s.focus.ends_at = new Date(new Date(s.focus.ends_at).getTime() + Date.now() - new Date(s.focus.paused_at).getTime()).toISOString();
      delete s.focus.paused_at;
    }
    save(u.id, s);
    return focusView(s.focus);
  },
  focusPauseOnLeave() {
    /* the mock keeps nothing across a closed page */
  },
  async listNotes(token) {
    await delay();
    return load(mockUserOf(token).id).notes;
  },
  async arenaPapers(token, q) {
    await delay();
    const band = mockUserOf(token).age_band ?? "g10_12";
    const B = { toan: { name_vi: "Quái Sai Số", name_en: "The Slip-Up Monster", art: "boss-toan" }, van: { name_vi: "Bóng Lạc Đề", name_en: "The Off-Topic Phantom", art: "boss-van" }, anh: { name_vi: "Quái Lỗi Ngữ Pháp", name_en: "The Grammar-Slip Monster", art: "boss-anh" } };
    const P = (id: string, title_vi: string, title_en: string, chicken: string, year: number, minutes: number, items: number, boss: keyof typeof B, kind: ArenaPaper["kind"] = "thpt"): ArenaPaper => ({ id, kind, title_vi, title_en, year, minutes, items, chicken, boss: B[boss], best_score: null, beaten: false, placeholder: true });
    const all: ArenaPaper[] =
      band === "uni"
        ? [P("cuoi-ky-xstk-mau", "Cuối kỳ Xác suất thống kê (đề mẫu)", "Final: Probability and Statistics (sample)", "toanhoc", 2025, 90, 8, "toan", "cuoi-ky")]
        : [
            P("thpt-toan-2025-mau", "THPT 2025 Toán (đề mẫu)", "National exam 2025 Maths (sample)", "toan", 2025, 90, 22, "toan"),
            P("thpt-anh-2025-mau", "THPT 2025 Tiếng Anh (đề mẫu)", "National exam 2025 English (sample)", "anh", 2025, 50, 40, "anh"),
            P("thpt-ly-2025-mau", "THPT 2025 Vật lí (đề mẫu)", "National exam 2025 Physics (sample)", "li", 2025, 50, 22, "toan"),
            P("dgnl-toan-mau", "Đánh giá năng lực Toán (đề mẫu)", "Aptitude test Maths (sample)", "toan", 2024, 60, 30, "toan", "dgnl"),
          ];
    return all.filter((p) => (!q?.chicken || p.chicken === q.chicken) && (!q?.year || p.year === q.year));
  },
  async chatHistory(token, chicken, limit = 30) {
    await delay();
    return (load(mockUserOf(token).id).chat[chicken] ?? []).slice(-limit);
  },
};

/** Mock side effects the village shows: a notes set appears in the list, chat turns are remembered. */
export function mockRememberNotes(token: string, n: NotesSet) {
  const u = mockUserOf(token);
  const s = load(u.id);
  s.notes = [n, ...s.notes];
  save(u.id, s);
}
export function mockRememberChat(token: string, chicken: string, turns: ChatMessage[]) {
  const u = mockUserOf(token);
  const s = load(u.id);
  s.chat[chicken] = [...(s.chat[chicken] ?? []), ...turns].slice(-30);
  save(u.id, s);
}

/** Test and demo helper: put a week of XP (and its sources) on a chicken the student owns. */
export function mockSeedWeek(token: string, chicken: string, week: number[], sources: Record<string, number>) {
  const u = mockUserOf(token);
  const s = load(u.id);
  s.week[chicken] = week;
  (s.sources ??= {})[chicken] = sources;
  save(u.id, s);
}
