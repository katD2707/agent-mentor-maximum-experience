import { ApiError, type Api, type User } from "./types";
import type { BehaviourEvent, Goal, GoalStatus, PlanItem, Reminder, TodaySession } from "./planner";
import { FIXTURES } from "./mock-courses";
import { mockResearchGoal, mockResearchLine } from "./mock-research";

const delay = () => new Promise((r) => setTimeout(r, 80));
const pad = (n: number) => String(n).padStart(2, "0");
const ymd = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const REASONS_VI = [
  "Em còn dở bài này, học tiếp lúc em hay tập trung nhất.",
  "",
  "Bài này nối thẳng với bài hôm qua.",
  "",
  "Trước bài kiểm tra, ôn lại phần này cho chắc.",
  "",
  "Câu hỏi tuần trước em còn sai, quay lại một lần.",
];
const REASONS_EN = [
  "You left this one half done, so pick it up when you focus best.",
  "",
  "This follows straight on from yesterday's lesson.",
  "",
  "Before the quiz, go over this part once more.",
  "",
  "You missed a question here last week, so come back to it.",
];
const WD_EN_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const WD_VI = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw) return JSON.parse(raw) as T;
  } catch {
    /* fall through */
  }
  return fallback;
}
function writeJson(key: string, v: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(v));
  } catch {
    /* ignore */
  }
}

/** In-browser mock of CONTRACTS.md section 12 (VITE_API_MOCK=1): a small, believable plan built from the fixtures. */
export function makeMockPlannerApi(userOf: (token: string) => User) {
  const goalsKey = (t: string) => `mentor.mock.goals.${userOf(t).id}`;
  const eventsKey = (t: string) => `mentor.mock.events.${userOf(t).id}`;
  const outcomeKey = (t: string) => `mentor.mock.outcomes.${userOf(t).id}`;

  const mineFixtures = (t: string) => {
    const band = userOf(t).age_band ?? "g10_12";
    const mine = FIXTURES.filter((f) => f.meta.age_band === band);
    return mine.length ? mine : FIXTURES.filter((f) => f.meta.age_band === "g10_12");
  };

  const goals = (t: string): Goal[] => {
    const stored = readJson<Goal[] | null>(goalsKey(t), null);
    if (stored) return stored;
    const inferred = mineFixtures(t).map(
      ({ meta }): Goal => ({
        id: `inf-${meta.id}`,
        title: `Học xong ${meta.title}`,
        kind: "inferred",
        deadline: null,
        progress_pct: 38,
        status: "on_track",
        line_vi: "Đang đúng nhịp, giữ đều mỗi tuần nhé.",
        line_en: "On track, keep it steady.",
        course_ids: [meta.id],
        courses: [{ id: meta.id, title: meta.title, subject: meta.subject }],
        required_min_per_day: null,
        created_at: "2026-11-01T08:00:00+07:00",
      }),
    );
    writeJson(goalsKey(t), inferred);
    return inferred;
  };

  /** The thesis goal of the university band comes from the research data (CONTRACTS.md 15.8). */
  const withResearch = (t: string, list: Goal[]): Goal[] => {
    const g = userOf(t).age_band === "uni" ? mockResearchGoal() : null;
    return g ? [...list, g] : list;
  };

  const items = (t: string): PlanItem[] => {
    const now = new Date();
    const out: PlanItem[] = [];
    const fx = mineFixtures(t);
    for (let i = -((now.getDay() + 6) % 7); i < 7; i++) {
      const d = new Date(now);
      d.setDate(now.getDate() + i);
      if (i % 3 === 2 || i % 3 === -1) continue;
      const f = fx[(i + 7) % fx.length];
      const lessons = f.pack.chapters.flatMap((c) => c.lessons);
      const lesson = lessons[Math.min(1, lessons.length - 1)];
      const wd = (d.getDay() + 6) % 7;
      const minutes = 15 + (i % 2) * 5;
      out.push({
        date: ymd(d),
        start: "19:30",
        minutes,
        kind: "lesson",
        course_id: f.meta.id,
        lesson_id: lesson.id,
        reason_vi: REASONS_VI[(i + 7) % REASONS_VI.length],
        reason_en: REASONS_EN[(i + 7) % REASONS_EN.length],
        weekday: wd,
        weekday_vi: WD_VI[wd],
        label: `${f.meta.title.split(":").pop()?.trim()} ${minutes}′`,
        title_vi: `${minutes} phút ${f.meta.title.split(":").pop()?.trim()}`,
        title_en: `${minutes} min ${f.meta.title.split(":").pop()?.trim()}`,
        course_title: f.meta.title,
        deep_link: `/khoa-hoc/${f.meta.id}?lesson=${lesson.id}`,
        done: i < 0 && i % 2 === 0,
      });
    }
    return out;
  };

  const reminders = (t: string): Reminder[] => {
    const at = new Date(Date.now() + 2 * 60000);
    const first = items(t).find((x) => x.date >= ymd(new Date()));
    return [
      {
        id: "mock-r1",
        at: at.toISOString(),
        kind: "study",
        text_vi: `Đến giờ học ${first?.minutes ?? 15} phút nhé. Mentor đã mở sẵn đúng chỗ em dừng.`,
        text_en: `Time for ${first?.minutes ?? 15} minutes. Mentor has your place ready.`,
        deep_link: first?.deep_link ?? "/khoa-hoc",
        status: "scheduled",
        outcome: (readJson<Record<string, string>>(outcomeKey(t), {})["mock-r1"] as Reminder["outcome"]) ?? null,
      },
    ];
  };

  const status = (p: number): GoalStatus => (p >= 100 ? "on_track" : "new");

  const planApi: Pick<Api, "getToday" | "getWeekPlan" | "listGoals" | "createGoal" | "patchGoal" | "deleteGoal" | "getReminders" | "reminderOutcome" | "postEvents" | "vapidPublicKey" | "pushSubscribe"> = {
    async getToday(token) {
      await delay();
      const u = userOf(token);
      const first = items(token)[0];
      const isToday = !!first && first.date === ymd(new Date());
      const today: TodaySession | null = first
        ? {
            title_vi: `${isToday ? "Tối nay" : first.weekday_vi === "CN" ? "Chủ nhật" : `Thứ ${Number(first.weekday_vi.slice(1))}`}: ${first.title_vi}`,
            title_en: `${isToday ? "Tonight" : WD_EN_LONG[first.weekday]}: ${first.title_en}`,
            date: first.date,
            start: first.start,
            is_today: isToday,
            minutes: first.minutes,
            kind: first.kind,
            course_id: first.course_id,
            lesson_id: first.lesson_id,
            reason_vi: first.reason_vi,
            reason_en: first.reason_en,
            deep_link: first.deep_link,
          }
        : null;
      const uni = u.age_band === "uni";
      const n = withResearch(token, goals(token)).length;
      return {
        date: ymd(new Date()),
        now: new Date().toISOString(),
        hub: {
          courses: { line_vi: today ? today.title_vi : "Chọn một khóa để bắt đầu", line_en: today ? today.title_en : "Pick a course to start" },
          practice: { line_vi: "10 câu, khoảng 12 phút", line_en: "10 questions, about 12 minutes" },
          ask: { line_vi: uni ? "Hỏi bất cứ điều gì về bài học" : "Chụp ảnh, gõ hoặc nói", line_en: uni ? "Ask anything about your lessons" : "Snap, type or talk" },
          progress: { line_vi: `${n} mục tiêu, tuần này 3/5 buổi`, line_en: `${n} goals, 3/5 sessions this week` },
          ...(uni ? { research: mockResearchLine() } : {}),
        },
        today,
        week: { done: 3, planned: 5 },
        due_review_count: 4,
        quiet_until: u.quiet_until,
        plan_source: "fallback",
      };
    },
    async getWeekPlan(token) {
      await delay();
      const back = (new Date().getDay() + 6) % 7;
      const days = Array.from({ length: back + 7 }, (_, i) => {
        const d = new Date();
        d.setDate(d.getDate() + i - back);
        return ymd(d);
      });
      return {
        generated_at: new Date().toISOString(),
        source: "fallback",
        trigger: "first",
        today: days[back],
        days,
        items: items(token),
        goals: goals(token).map((g) => ({ goal_id: g.id, status: g.status, line_vi: g.line_vi, line_en: g.line_en })),
        note_vi: "Buổi học giữ ngắn vì em tập trung tốt nhất trong 20 phút đầu.",
        note_en: "Sessions stay short because you focus best in the first 20 minutes.",
        moves: [],
      };
    },
    async listGoals(token) {
      await delay();
      return withResearch(token, goals(token));
    },
    async createGoal(token, body) {
      await delay();
      const list = goals(token);
      const g: Goal = {
        id: `g-${Date.now().toString(36)}`,
        title: body.title.trim(),
        kind: "student",
        deadline: body.deadline ?? null,
        progress_pct: 0,
        status: status(0),
        line_vi: "Mentor đang xếp mục tiêu này vào lịch học.",
        line_en: "Mentor is fitting this into your schedule.",
        course_ids: body.course_ids ?? [],
        courses: [],
        required_min_per_day: null,
        created_at: new Date().toISOString(),
      };
      list.push(g);
      writeJson(goalsKey(token), list);
      return g;
    },
    async patchGoal(token, id, body) {
      await delay();
      const list = goals(token);
      const g = list.find((x) => x.id === id);
      if (!g) throw new ApiError(404, "not_found");
      if (body.deadline !== undefined) g.deadline = body.deadline ?? null;
      if (g.kind === "student" && body.title) g.title = body.title;
      writeJson(goalsKey(token), list);
      return g;
    },
    async deleteGoal(token, id) {
      await delay();
      writeJson(
        goalsKey(token),
        goals(token).filter((g) => g.id !== id),
      );
    },
    async getReminders(token) {
      await delay();
      const u = userOf(token);
      const brk = u.age_band === "g1_5" ? 15 : u.age_band === "g6_9" ? 25 : u.age_band === "uni" ? 50 : 40;
      return { now: new Date().toISOString(), quiet_until: u.quiet_until, break_after_minutes: brk, reminders: reminders(token) };
    },
    async reminderOutcome(token, id, outcome) {
      const m = readJson<Record<string, string>>(outcomeKey(token), {});
      m[id] = outcome;
      writeJson(outcomeKey(token), m);
    },
    async postEvents(token, events: BehaviourEvent[]) {
      await delay();
      const have = readJson<BehaviourEvent[]>(eventsKey(token), []);
      const ids = new Set(have.map((e) => e.id));
      let accepted = 0;
      for (const e of events)
        if (!ids.has(e.id)) {
          have.push(e);
          accepted++;
        }
      writeJson(eventsKey(token), have.slice(-500));
      return { accepted, duplicates: events.length - accepted, rejected: 0 };
    },
    async vapidPublicKey() {
      return { enabled: false, public_key: null };
    },
    async pushSubscribe() {},
  };
  return planApi;
}
