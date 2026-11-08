import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, type BehaviourEvent, type CoursePack, type Reminder, type RemindersResponse } from "./api";
import { dienPack } from "./api/mock-courses";
import { resolveDeepLink, withReminder } from "./lib/deeplink";
import { buildGoal, deadlineOf } from "./lib/goalForm";
import { IGNORE_AFTER_MS, ReminderScheduler, type FiredEntry, type FiredStore, type LocalNotification } from "./lib/reminders";
import { FocusTracker } from "./lib/focus";
import { BATCH, EventLogger, keepAfter, localEventStore, type EventStore } from "./lib/events";
import { courseInsight } from "./lib/insight";

describe("deep links", () => {
  it("a course with a lesson opens the player at that lesson", () => {
    expect(resolveDeepLink("/khoa-hoc/dien-truong?lesson=l2")).toEqual({ to: "/khoa-hoc/dien-truong/hoc?lesson=l2", reminderId: null });
  });
  it("a course alone opens its intro; the player route and fixed screens pass through", () => {
    expect(resolveDeepLink("/khoa-hoc/dien-truong").to).toBe("/khoa-hoc/dien-truong");
    expect(resolveDeepLink("/khoa-hoc/dien-truong/hoc").to).toBe("/khoa-hoc/dien-truong/hoc");
    expect(resolveDeepLink("/luyen-tap").to).toBe("/luyen-tap");
    expect(resolveDeepLink("/tien-do/").to).toBe("/tien-do");
  });
  it("a full app URL, as the service worker builds it, keeps the route and the reminder id", () => {
    const t = resolveDeepLink("https://app.example/#/khoa-hoc/c1?lesson=l1&reminder=r-9");
    expect(t).toEqual({ to: "/khoa-hoc/c1/hoc?lesson=l1", reminderId: "r-9" });
    expect(withReminder("/luyen-tap", "r1")).toBe("/luyen-tap?reminder=r1");
  });
  it("unknown, old or hostile links land on the hub", () => {
    for (const bad of [null, undefined, "", "/chat?notification=n1", "//evil.example/x", "https://evil.example/", "javascript:alert(1)", "/khoa-hoc/../../x", "/khoa-hoc/a b"]) {
      expect(resolveDeepLink(bad as string).to).toBe("/");
    }
    // a bad lesson id is dropped, the course still opens
    expect(resolveDeepLink("/khoa-hoc/c1?lesson=<x>").to).toBe("/khoa-hoc/c1");
  });
});

describe("goal form", () => {
  const now = new Date(2026, 10, 7, 9, 0); // 7 Nov 2026
  it("needs a title; the deadline is optional", () => {
    expect(buildGoal({ title: "   ", pick: { kind: "none" } }, now)).toEqual({ ok: false, error: "title" });
    expect(buildGoal({ title: " 8 điểm  Toán ", pick: { kind: "none" } }, now)).toEqual({ ok: true, body: { title: "8 điểm Toán" } });
  });
  it("this month means its last day", () => {
    expect(deadlineOf({ kind: "month" }, now)).toBe("2026-11-30");
    expect(deadlineOf({ kind: "month" }, new Date(2028, 1, 10))).toBe("2028-02-29");
  });
  it("a picked date must be real and not in the past", () => {
    expect(buildGoal({ title: "x", pick: { kind: "date", value: "2026-12-20" } }, now)).toEqual({ ok: true, body: { title: "x", deadline: "2026-12-20" } });
    expect(buildGoal({ title: "x", pick: { kind: "date", value: "2026-11-07" } }, now).ok).toBe(true); // today is fine
    expect(buildGoal({ title: "x", pick: { kind: "date", value: "2026-11-06" } }, now)).toEqual({ ok: false, error: "deadline" });
    expect(buildGoal({ title: "x", pick: { kind: "date", value: "2026-02-31" } }, now)).toEqual({ ok: false, error: "deadline" });
    expect(buildGoal({ title: "x", pick: { kind: "date", value: "" } }, now)).toEqual({ ok: false, error: "deadline" });
  });
});

// ---------------------------------------------------------------- reminders
const T0 = Date.parse("2026-11-07T12:00:00Z");
const rem = (id: string, minFromNow: number, over: Partial<Reminder> = {}): Reminder => ({
  id,
  at: new Date(T0 + minFromNow * 60000).toISOString(),
  kind: "study",
  text_vi: `vi ${id}`,
  text_en: `en ${id}`,
  deep_link: `/khoa-hoc/c1?lesson=${id}`,
  status: "scheduled",
  outcome: null,
  ...over,
});
const resp = (reminders: Reminder[], quiet: string | null = null): RemindersResponse => ({ now: new Date(T0).toISOString(), quiet_until: quiet, break_after_minutes: 40, reminders });
const memStore = (): FiredStore & { data: Record<string, FiredEntry> } => {
  const s = { data: {} as Record<string, FiredEntry>, read: () => s.data, write: (v: Record<string, FiredEntry>) => void (s.data = v) };
  return s;
};

describe("reminder scheduling", () => {
  let shown: LocalNotification[];
  let reports: [string, string][];
  let enabled: boolean;
  let lang: "vi" | "en";
  const make = (store = memStore()) =>
    new ReminderScheduler({
      notify: (n) => void shown.push(n),
      report: (id, o) => void reports.push([id, o]),
      lang: () => lang,
      enabled: () => enabled,
      store,
    });

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(T0);
    shown = [];
    reports = [];
    enabled = true;
    lang = "vi";
  });
  afterEach(() => vi.useRealTimers());

  it("shows a scheduled reminder at its time, in the UI language, with its deep link", () => {
    const s = make();
    s.sync(resp([rem("a", 10), rem("b", 20)]));
    expect(s.scheduledIds().sort()).toEqual(["a", "b"]);
    vi.advanceTimersByTime(9 * 60000);
    expect(shown).toHaveLength(0);
    vi.advanceTimersByTime(60000);
    expect(shown).toEqual([{ id: "a", kind: "study", title: "Mentor", body: "vi a", deepLink: "/khoa-hoc/c1?lesson=a" }]);
    lang = "en";
    vi.advanceTimersByTime(10 * 60000);
    expect(shown[1].body).toBe("en b");
  });

  it("ignores the past, other statuses and reminders that already have an outcome", () => {
    const s = make();
    s.sync(resp([rem("past", -5), rem("c", 5, { status: "cancelled" }), rem("q", 5, { status: "skipped_quiet" }), rem("p", 5, { status: "pushed" }), rem("o", 5, { outcome: "opened" }), rem("ok", 5)]));
    expect(s.scheduledIds()).toEqual(["ok"]);
  });

  it("cancels what the server no longer lists as scheduled (a new plan, quiet) and keeps the rest", () => {
    const s = make();
    s.sync(resp([rem("a", 10), rem("b", 20), rem("c", 30)]));
    s.sync(resp([rem("a", 10), rem("b", 20, { status: "cancelled" }), rem("d", 40)]));
    expect(s.scheduledIds().sort()).toEqual(["a", "d"]);
    vi.advanceTimersByTime(45 * 60000);
    expect(shown.map((n) => n.id)).toEqual(["a", "d"]);
  });

  it("moves a reminder when its time changed", () => {
    const s = make();
    s.sync(resp([rem("a", 10)]));
    s.sync(resp([rem("a", 30)]));
    vi.advanceTimersByTime(15 * 60000);
    expect(shown).toHaveLength(0);
    vi.advanceTimersByTime(15 * 60000);
    expect(shown).toHaveLength(1);
  });

  it("drops anything before quiet_until, from the server answer", () => {
    const s = make();
    s.sync(resp([rem("a", 10), rem("b", 60)], new Date(T0 + 30 * 60000).toISOString()));
    expect(s.scheduledIds()).toEqual(["b"]);
  });

  it("quiet mode set in Settings applies at once, to reminders already scheduled", () => {
    const s = make();
    s.sync(resp([rem("a", 10), rem("b", 20), rem("c", 90)]));
    s.setQuietUntil(new Date(T0 + 45 * 60000).toISOString());
    expect(s.scheduledIds()).toEqual(["c"]);
    vi.advanceTimersByTime(60 * 60000);
    expect(shown).toHaveLength(0);
    vi.advanceTimersByTime(30 * 60000);
    expect(shown.map((n) => n.id)).toEqual(["c"]);
  });

  it("a reminder due while quiet is switched on just before it fires is not shown", () => {
    const s = make();
    s.sync(resp([rem("a", 10)]));
    vi.advanceTimersByTime(9 * 60000);
    s.setQuietUntil(new Date(T0 + 120 * 60000).toISOString());
    vi.advanceTimersByTime(5 * 60000);
    expect(shown).toHaveLength(0);
  });

  it("does nothing when reminders are off in Settings", () => {
    const s = make();
    enabled = false;
    s.sync(resp([rem("a", 5)]));
    vi.advanceTimersByTime(10 * 60000);
    expect(shown).toHaveLength(0);
  });

  it("reports opened on a tap, and not ignored afterwards", () => {
    const s = make();
    s.sync(resp([rem("a", 5)]));
    vi.advanceTimersByTime(5 * 60000);
    s.opened("a");
    vi.advanceTimersByTime(IGNORE_AFTER_MS + 1000);
    expect(reports).toEqual([["a", "opened"]]);
    s.opened("a"); // a second tap is not reported twice
    expect(reports).toHaveLength(1);
  });

  it("reports ignored 30 minutes after it was shown, once", () => {
    const s = make();
    s.sync(resp([rem("a", 5)]));
    vi.advanceTimersByTime(5 * 60000 + IGNORE_AFTER_MS - 1000);
    expect(reports).toHaveLength(0);
    vi.advanceTimersByTime(2000);
    expect(reports).toEqual([["a", "ignored"]]);
  });

  it("does not show a reminder again after a restart, and settles the unanswered one", () => {
    const store = memStore();
    const s1 = make(store);
    s1.sync(resp([rem("a", 5)]));
    vi.advanceTimersByTime(5 * 60000);
    s1.dispose();
    expect(shown).toHaveLength(1);
    // the app restarts 40 minutes later; the server still lists "a" as scheduled
    vi.advanceTimersByTime(40 * 60000);
    const s2 = make(store);
    s2.restore();
    expect(reports).toEqual([["a", "ignored"]]);
    s2.sync(resp([rem("a", -35)]));
    expect(s2.scheduledIds()).toEqual([]);
    expect(shown).toHaveLength(1);
  });

  it("a restart inside the 30 minutes keeps waiting for the rest of the time", () => {
    const store = memStore();
    const s1 = make(store);
    s1.sync(resp([rem("a", 1)]));
    vi.advanceTimersByTime(60000);
    s1.dispose();
    vi.advanceTimersByTime(10 * 60000);
    const s2 = make(store);
    s2.restore();
    vi.advanceTimersByTime(19 * 60000);
    expect(reports).toHaveLength(0);
    vi.advanceTimersByTime(2 * 60000);
    expect(reports).toEqual([["a", "ignored"]]);
  });

  it("the break reminder is made on the device, respects quiet and is not reported to the server", () => {
    const s = make();
    s.breakDue(40);
    expect(shown).toHaveLength(1);
    expect(shown[0].kind).toBe("break");
    expect(shown[0].body).toContain("40");
    s.setQuietUntil(new Date(T0 + 3600000).toISOString());
    s.breakDue(40);
    expect(shown).toHaveLength(1);
    vi.advanceTimersByTime(IGNORE_AFTER_MS + 1000);
    expect(reports).toHaveLength(0);
  });
});

// ---------------------------------------------------------------- focus
describe("focus accounting", () => {
  let clock: number;
  let out: { kind: string; data: Record<string, unknown> }[];
  const make = (over: Partial<ConstructorParameters<typeof FocusTracker>[0]> = {}) =>
    new FocusTracker({ emit: (kind, data) => void out.push({ kind, data }), now: () => clock, ...over });
  /** run `seconds` of wall time, sampling each second; `input` = the user acts every `input` seconds (0 = never) */
  const run = (f: FocusTracker, seconds: number, input = 0) => {
    for (let i = 0; i < seconds; i++) {
      clock += 1000;
      if (input && i % input === 0) f.touch();
      f.sample();
    }
  };
  beforeEach(() => {
    clock = Date.parse("2026-11-07T12:00:00Z");
    out = [];
  });
  const ticks = () => out.filter((e) => e.kind === "focus_tick").reduce((n, e) => n + (e.data.seconds as number), 0);

  it("counts active seconds in ticks of about 30 s and starts a session", () => {
    const f = make();
    run(f, 95, 10);
    expect(out[0].kind).toBe("session_start");
    expect(out.filter((e) => e.kind === "focus_tick").map((e) => e.data.seconds)).toEqual([30, 30, 30]);
    f.end();
    expect(ticks()).toBe(95);
    const end = out[out.length - 1];
    expect(end.kind).toBe("session_end");
    expect(end.data.seconds).toBe(95);
    expect(new Set(out.map((e) => e.data.session)).size).toBe(1);
  });

  it("counts nothing while the page is hidden", () => {
    const f = make();
    run(f, 20, 5);
    f.setVisible(false);
    run(f, 120, 5); // input events while hidden do not make it active
    f.setVisible(true);
    run(f, 20, 5);
    f.end();
    expect(ticks()).toBe(40);
  });

  it("counts nothing once 60 s pass without an input, and resumes on the next one", () => {
    const f = make();
    run(f, 10, 1); // input every second for 10 s, last input at second 10
    run(f, 120); // no input: the first 60 s still count, then idle
    f.touch();
    run(f, 10, 1);
    f.end();
    expect(ticks()).toBe(10 + 60 + 10);
  });

  it("ends the session after a long idle gap and starts a new one afterwards", () => {
    const f = make({ sessionIdleMs: 5 * 60000 });
    run(f, 40, 5);
    run(f, 6 * 60);
    expect(out.map((e) => e.kind)).toContain("session_end");
    const first = out.find((e) => e.kind === "session_start")!.data.session;
    run(f, 10, 1);
    const starts = out.filter((e) => e.kind === "session_start");
    expect(starts).toHaveLength(2);
    expect(starts[1].data.session).not.toBe(first);
    f.end();
    expect(ticks()).toBe(40 + 56 + 10); // the last input was 4 s before the end of the first run
  });

  it("asks for a break after the age band's minutes of continuous focus, and starts counting again", () => {
    const due: number[] = [];
    const f = make({ breakAfterMin: () => 2, onBreakDue: (m) => due.push(m) });
    run(f, 119, 5);
    expect(due).toEqual([]);
    run(f, 2, 5);
    expect(due).toEqual([2]);
    run(f, 100, 5);
    expect(due).toEqual([2]);
    run(f, 25, 5);
    expect(due).toEqual([2, 2]);
  });

  it("a pause of a few minutes resets the continuous count", () => {
    const due: number[] = [];
    const f = make({ breakAfterMin: () => 3, onBreakDue: (m) => due.push(m), breakResetMs: 3 * 60000 });
    run(f, 90, 5);
    run(f, 5 * 60); // pause
    run(f, 90, 5);
    expect(due).toEqual([]);
  });
});

// ---------------------------------------------------------------- events + offline replay
const memEvents = (): EventStore & { list: BehaviourEvent[] } => {
  const s = { list: [] as BehaviourEvent[], read: () => s.list, write: (l: BehaviourEvent[]) => void (s.list = l) };
  return s;
};

describe("behaviour events", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("every event has a unique client id, an ISO time and is stored before it is sent", () => {
    const store = memEvents();
    const l = new EventLogger(store, async () => ({}));
    l.log("app_open");
    l.log("quiz_answer", { item: "q1", correct: true });
    expect(store.list).toHaveLength(2);
    expect(new Set(store.list.map((e) => e.id)).size).toBe(2);
    expect(Number.isNaN(Date.parse(store.list[0].ts))).toBe(false);
    l.stop();
  });

  it("sends batches of at most 500 and clears what was acknowledged", async () => {
    const store = memEvents();
    const sent: number[] = [];
    const l = new EventLogger(store, async (b) => void sent.push(b.length), { autoFlushAt: 1e9 });
    for (let i = 0; i < 1200; i++) l.log("focus_tick", { seconds: 30 });
    await l.flush();
    expect(sent).toEqual([BATCH, BATCH, 200]);
    expect(store.list).toHaveLength(0);
    l.stop();
  });

  it("keeps the queue offline and replays it, in order, when the network is back (nothing sent twice)", async () => {
    const store = memEvents();
    let online = false;
    const got: string[] = [];
    const l = new EventLogger(
      store,
      async (b) => {
        if (!online) throw new ApiError(0, "network");
        got.push(...b.map((e) => e.id));
      },
      { autoFlushAt: 1e9 },
    );
    l.log("app_open");
    l.log("session_start", { session: "s1" });
    await l.flush();
    expect(store.list).toHaveLength(2);
    l.log("focus_tick", { session: "s1", seconds: 30 });
    await l.flush();
    expect(store.list).toHaveLength(3);
    const ids = store.list.map((e) => e.id);
    online = true;
    await l.flush();
    expect(got).toEqual(ids);
    expect(store.list).toHaveLength(0);
    await l.flush();
    expect(got).toEqual(ids);
    l.stop();
  });

  it("survives closing the app: a new logger reads the unsent events from the device", async () => {
    localStorage.clear();
    const a = new EventLogger(localEventStore("u1"), async () => Promise.reject(new ApiError(0, "network")), { autoFlushAt: 1e9 });
    a.log("app_open");
    a.log("lesson_progress", { course_id: "c1", lesson_id: "l1", pct: 50 });
    await a.flush();
    a.stop();
    const seen: BehaviourEvent[] = [];
    const b = new EventLogger(localEventStore("u1"), async (batch) => void seen.push(...batch));
    expect(b.pending()).toBe(2);
    await b.flush();
    expect(seen.map((e) => e.kind)).toEqual(["app_open", "lesson_progress"]);
    expect(localEventStore("u1").read()).toEqual([]);
    b.stop();
  });

  it("a batch the server refuses as a whole is dropped so it cannot block the queue; auth and server errors are kept", async () => {
    expect(keepAfter(new ApiError(0, "network"))).toBe(true);
    expect(keepAfter(new ApiError(401, "unauthorized"))).toBe(true);
    expect(keepAfter(new ApiError(503, "unknown"))).toBe(true);
    expect(keepAfter(new ApiError(422, "unknown"))).toBe(false);
    const store = memEvents();
    const l = new EventLogger(store, async () => Promise.reject(new ApiError(422, "unknown")), { autoFlushAt: 1e9 });
    l.log("app_open");
    await l.flush();
    expect(store.list).toHaveLength(0);
    l.stop();
  });

  it("flushes by itself a little after the first event", async () => {
    const store = memEvents();
    const sent: number[] = [];
    const l = new EventLogger(store, async (b) => void sent.push(b.length), { flushDelayMs: 1000, autoFlushAt: 1e9 });
    l.log("app_open");
    l.log("app_open");
    await vi.advanceTimersByTimeAsync(1100);
    expect(sent).toEqual([2]);
    l.stop();
  });
});

describe("course insight", () => {
  const pack = dienPack as CoursePack;
  const quizItems = pack.chapters.flatMap((c) => c.lessons).flatMap((l) => l.blocks.flatMap((b) => (b.kind === "quiz" ? b.items.map((q) => ({ lesson: l.title, id: q.id })) : [])));
  it("names lessons whose answers were all right as strong and mostly wrong ones as watch-outs", () => {
    const byLesson = new Map<string, string[]>();
    for (const q of quizItems) byLesson.set(q.lesson, [...(byLesson.get(q.lesson) ?? []), q.id]);
    const [first, second] = [...byLesson.entries()];
    const quiz: Record<string, { correct: boolean; seconds: number; attempts: number }> = {};
    for (const id of first[1]) quiz[id] = { correct: true, seconds: 5, attempts: 1 };
    for (const id of second[1]) quiz[id] = { correct: false, seconds: 5, attempts: 2 };
    const r = courseInsight(pack, { quiz });
    if (first[1].length >= 2) expect(r.strong).toEqual([first[0]]);
    expect(r.watch).toEqual([second[0]]);
  });
  it("says nothing without a pack or without answers", () => {
    expect(courseInsight(null, { quiz: { a: { correct: true, seconds: 1, attempts: 1 } } })).toEqual({ strong: [], watch: [] });
    expect(courseInsight(pack, {})).toEqual({ strong: [], watch: [] });
  });
});
