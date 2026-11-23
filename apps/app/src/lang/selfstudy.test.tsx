import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "../i18n";
import { App } from "../App";
import { AuthProvider } from "../state/auth";
import { FocusTracker } from "../lib/focus";
import { lg, mockSeedWeek } from "./api";
import { markStreak, sourceRows } from "./screens/progress/Progress";
import { resolveDeepLink } from "../lib/deeplink";

const TOKEN = "mock-u-hs";

function seed(birth: number, chickens: { id: string; xp: number }[]) {
  localStorage.setItem("mentor.mock.users", JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: null, birth_year: birth, language: "vi", theme: "system", quiet_until: null } } }));
  localStorage.setItem("mentor.token", TOKEN);
  localStorage.setItem("mentor.lang", "vi");
  localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["lg-village", "lg-first", "today", "progress"]));
  localStorage.setItem("mentor.mock.lg.u-hs", JSON.stringify({ chickens: chickens.map((c) => ({ ...c, taken_at: "2026-11-01T00:00:00Z" })) }));
}
const open = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );

beforeEach(async () => {
  await i18n.changeLanguage("vi");
});
afterEach(() => {
  vi.useRealTimers();
});

describe("study room (lg-06)", () => {
  /** Real timers keep the app's promises moving; only the clock is ours, so minutes pass in a blink. */
  const startClock = () => vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ["Date", "setInterval", "clearInterval"] });
  const pass = async (ms: number) => {
    await act(async () => {
      vi.advanceTimersByTime(ms);
    });
  };

  it("picks a chicken and the minutes, counts down, and pays +1 a minute plus +5 for a full session", async () => {
    seed(2010, [{ id: "toan", xp: 90 }, { id: "van", xp: 0 }]);
    const ui = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
    startClock();
    open("/phong-tu-hoc");
    expect(await screen.findByRole("heading", { name: "Phòng tự học" })).toBeInTheDocument();
    // the chicken that speaks in the village is chosen first; 25 minutes is the default
    expect(await screen.findByRole("radio", { name: /^Gà Toán/ })).toBeChecked();
    await ui.click(screen.getByRole("radio", { name: /^Gà Văn/ }));
    await ui.click(screen.getByRole("radio", { name: /^Gà Toán/ }));
    await ui.click(screen.getByRole("radio", { name: /^15 phút/ }));
    expect(screen.getByRole("button", { name: /Bắt đầu 15 phút/ })).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: /Bắt đầu 15 phút/ }));

    expect(await screen.findByText("Đang học cùng Gà Toán")).toBeInTheDocument();
    expect(screen.getByText("15:00")).toBeInTheDocument();
    expect((await lg.focusActive(TOKEN))?.minutes).toBe(15); // the server (mock) knows the session
    await pass(7 * 60000 + 1000);
    expect(screen.getByText("07:59")).toBeInTheDocument();
    expect(screen.getByText("+7")).toBeInTheDocument();

    await pass(8 * 60000); // the whole time is over: the session finishes by itself
    expect(await screen.findByText("15 phút học + 5 điểm thưởng vì em học trọn buổi")).toBeInTheDocument(); // 15 minutes + 5 for staying to the end
    expect(document.querySelector(".lg-sr-gain b")).toHaveTextContent("+20");
    // 90 + 20 XP: level 1 -> 2 with 10 in the new level
    expect(screen.getByText("Lên cấp!", { selector: ".up" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Kinh nghiệm lên cấp tiếp theo" })).toHaveAttribute("aria-valuenow", "10");
    expect(await lg.focusActive(TOKEN)).toBeNull();
    const week = await lg.xpWeek(TOKEN);
    expect(week.chickens.find((c) => c.chicken === "toan")?.by_source).toEqual({ focus: 15, focus_full: 5 });
  });

  it("pause stands the clock still; stopping early keeps +1 for each finished minute and no bonus", async () => {
    seed(2010, [{ id: "toan", xp: 0 }]);
    const ui = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
    startClock();
    open("/phong-tu-hoc");
    await ui.click(await screen.findByRole("button", { name: /Bắt đầu 25 phút/ }));
    await screen.findByText("25:00");
    await pass(5 * 60000 + 500);
    await ui.click(screen.getByRole("button", { name: "Tạm dừng" }));
    expect(screen.getByText("Đang tạm dừng")).toBeInTheDocument();
    await waitFor(async () => expect((await lg.focusActive(TOKEN))?.status).toBe("paused")); // the server holds the pause
    const frozen = document.querySelector(".time")?.textContent;
    await pass(10 * 60000); // ten minutes of rest do not count
    expect(document.querySelector(".time")?.textContent).toBe(frozen);
    await ui.click(screen.getByRole("button", { name: "Học tiếp" }));
    await screen.findByRole("button", { name: "Tạm dừng" }); // the server resumed the clock
    await pass(2 * 60000);
    await ui.click(screen.getByRole("button", { name: "Dừng" }));
    expect(await screen.findByText("Em đã học 7 phút")).toBeInTheDocument();
    expect(screen.getByText("+7")).toBeInTheDocument();
    expect(screen.queryByText(/điểm thưởng/)).toBeNull();
    expect(screen.getByText(/Mình giữ 7 điểm kinh nghiệm/)).toBeInTheDocument();
    expect(screen.getByText(/Học đủ 10 phút hoặc xong 1 bài/)).toBeInTheDocument();
  });

  it("a session still running on the server comes back after a reload, with the time that is left", async () => {
    seed(2010, [{ id: "van", xp: 0 }]);
    const f = await lg.focusStart(TOKEN, { minutes: 25, chicken: "van" });
    expect(f.minutes).toBe(25);
    open("/phong-tu-hoc");
    expect(await screen.findByText("Đang học cùng Gà Văn")).toBeInTheDocument();
    expect(screen.getByRole("timer")).toHaveAccessibleName(/Còn 25 phút/);
  });

  it("a session paused on the server stays paused after a reload; resuming starts the clock again", async () => {
    seed(2010, [{ id: "van", xp: 0 }]);
    const f = await lg.focusStart(TOKEN, { minutes: 25, chicken: "van" });
    await lg.focusPause(TOKEN, f.id);
    open("/phong-tu-hoc");
    expect(await screen.findByText("Đang tạm dừng")).toBeInTheDocument();
    const ui = userEvent.setup();
    await ui.click(screen.getByRole("button", { name: "Học tiếp" }));
    expect(await screen.findByRole("button", { name: "Tạm dừng" })).toBeInTheDocument();
    expect((await lg.focusActive(TOKEN))?.status).toBe("active");
  });

  it("with no chicken yet it points back to the village", async () => {
    seed(2010, []);
    open("/phong-tu-hoc");
    expect(await screen.findByText(/Nhận một chú gà ở Chợ gà/)).toBeInTheDocument();
  });
});

describe("study room and the old focus accounting do not count twice", () => {
  it("held, the tracker counts the visible countdown as active time; released, it is idle again", () => {
    let t = 0;
    const emitted: { kind: string; seconds?: number }[] = [];
    const tr = new FocusTracker({ emit: (kind, d) => emitted.push({ kind, seconds: d.seconds as number | undefined }), now: () => t, tickEveryS: 30 });
    tr.touch();
    const run = (sec: number) => {
      for (let i = 0; i < sec; i++) {
        t += 1000;
        tr.sample();
      }
    };
    run(120); // no input after the first touch: idle after 60 s, nothing more counts
    const before = emitted.filter((e) => e.kind === "focus_tick").reduce((n, e) => n + (e.seconds ?? 0), 0);
    expect(before).toBeLessThanOrEqual(60);
    tr.hold(true);
    run(300); // the countdown runs: five minutes of focus with no touch at all
    const held = emitted.filter((e) => e.kind === "focus_tick").reduce((n, e) => n + (e.seconds ?? 0), 0);
    expect(held - before).toBeGreaterThanOrEqual(270);
    tr.hold(false);
    run(200);
    const after = emitted.filter((e) => e.kind === "focus_tick").reduce((n, e) => n + (e.seconds ?? 0), 0);
    expect(after - held).toBeLessThanOrEqual(90); // back to the 60 s idle rule
  });
});

describe("progress (lg-09)", () => {
  it("lists the chickens' week by source, the rules of growth, and the streak", async () => {
    seed(2010, [{ id: "toan", xp: 278 }, { id: "van", xp: 40 }]);
    mockSeedWeek(TOKEN, "toan", [0, 20, 0, 45, 0, 0, 136], { lesson_done: 40, lesson_perfect: 5, practice_right: 20, fix_right: 9, paper_submit: 40, boss_beaten: 50, focus: 20, focus_full: 5, notes_review: 12 });
    open("/tien-do");
    expect(await screen.findByRole("heading", { name: "Gà của em tuần này" })).toBeInTheDocument();
    const card = (await screen.findByRole("link", { name: "Gà Toán" })).closest("article") as HTMLElement;
    expect(within(card).getByText("+201 kinh nghiệm")).toBeInTheDocument(); // 20 + 45 + 136
    expect(within(card).getByText("Cấp 5 thành Trưởng thành.")).toBeInTheDocument();
    expect(within(card).getByText("còn 22 lên cấp 4")).toBeInTheDocument();
    // the six rows: lessons, practice, arena, study room, review cards
    expect(within(card).getByText("Bài học")).toBeInTheDocument();
    expect(within(card).getByText("2 bài, 1 bài đúng hết lần đầu")).toBeInTheDocument();
    expect(within(card).getByText("10 câu đúng, sửa 3 câu sai")).toBeInTheDocument();
    expect(within(card).getByText("1 đề nộp, hạ 1 boss")).toBeInTheDocument();
    expect(within(card).getByText("20 phút, học trọn buổi")).toBeInTheDocument();
    expect(within(card).getByText("6 thẻ")).toBeInTheDocument();
    expect(within(card).getByText("+90")).toBeInTheDocument();
    // a chicken with no points this week says so
    const van = screen.getByRole("link", { name: "Gà Văn" }).closest("article") as HTMLElement;
    expect(within(van).getByText("+0 kinh nghiệm")).toBeInTheDocument();
    expect(within(van).getByText(/Học 10 phút hôm nay/)).toBeInTheDocument();
    // how chickens grow: the approved amounts
    const rules = screen.getByRole("heading", { name: "Cách gà lớn" }).closest("section") as HTMLElement;
    expect(within(rules).getByText("Phòng tự học: mỗi phút (+5 nếu học trọn buổi), tối đa 120 kinh nghiệm mỗi ngày")).toBeInTheDocument();
    expect(within(rules).getByText("+20 kinh nghiệm")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Chuỗi ngày" })).toBeInTheDocument();
  });

  it("the week dots follow the village streak, so the HUD and Tiến độ say the same", () => {
    const none = [false, false, false, false, false, false, true]; // the chickens only earned today
    expect(markStreak(none, { days: 6, today_done: true })).toEqual([false, true, true, true, true, true, true]);
    expect(markStreak([false, true, false, false, false, false, false], { days: 3, today_done: false })).toEqual([false, true, false, true, true, true, false]);
    expect(markStreak(none, { days: 0, today_done: true })).toEqual(none);
    expect(markStreak(none, null)).toEqual(none);
  });
  it("sourceRows works the counts back from what each source pays", () => {
    const t = (k: string, o?: Record<string, unknown>) => `${k}:${JSON.stringify(o ?? {})}`;
    const rows = sourceRows({ focus: 15, focus_full: 5, notes_review: 4 }, t);
    expect(rows.map((r) => [r.key, r.amount])).toEqual([["room", 20], ["cards", 4]]);
    expect(sourceRows({}, t)).toEqual([]);
  });

  it("the goal form: a title with no deadline, this month or a date; a goal can be removed after asking", async () => {
    seed(2010, [{ id: "toan", xp: 0 }]);
    const ui = userEvent.setup();
    open("/tien-do");
    await screen.findByRole("heading", { name: "Mục tiêu" });
    await ui.click(screen.getByRole("button", { name: "Thêm" }));
    await ui.click(screen.getByRole("button", { name: "Lưu" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Gõ mục tiêu của em nhé.");
    await ui.type(screen.getByLabelText("Mục tiêu mới"), "Xong chương 2");
    await ui.click(screen.getByRole("button", { name: "Cuối tháng này" }));
    await ui.click(screen.getByRole("button", { name: "Lưu" }));
    expect(await screen.findByRole("heading", { name: /Xong chương 2 trước/ })).toBeInTheDocument();
    // the new goal is in the list; remove it (asks first)
    const row = screen.getByRole("heading", { name: /Xong chương 2/ }).closest("li") as HTMLElement;
    await ui.click(within(row).getByRole("button", { name: "Bỏ mục tiêu" }));
    expect(within(row).getByText(/Bỏ mục tiêu này\?/)).toBeInTheDocument();
    await ui.click(within(row).getByRole("button", { name: "Bỏ" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: /Xong chương 2/ })).toBeNull());
  });
});

describe("old research links", () => {
  it("land in the Library", () => {
    expect(resolveDeepLink("/nghien-cuu").to).toBe("/thu-vien");
    expect(resolveDeepLink("/nghien-cuu/paper/p-1").to).toBe("/thu-vien/paper/p-1");
    expect(resolveDeepLink("/thu-vien/paper/p-1").to).toBe("/thu-vien/paper/p-1");
    expect(resolveDeepLink("/phong-tu-hoc").to).toBe("/phong-tu-hoc");
  });
});
