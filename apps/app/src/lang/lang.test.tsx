import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "../i18n";
import { App } from "../App";
import { AuthProvider } from "../state/auth";
import { hasSeen } from "../lib/tours";
import { Grid, GAIT, dirFor, phaseStep, smooth, inPoly, type Pt } from "./engine/geometry";
import { ALL_SUBJECTS, artFile, levelOf, stageOf, subjectsFor, xpInLevel } from "./subjects";
import { helpTopic, laterOptions, routeText } from "./screens/village/logic";
import { lg, mockGiveXp } from "./api";
import { streamChat } from "./api/chat";
import { watchSlow } from "./screens/village/logic";

vi.mock("./api/chat", async (orig) => {
  const m = await orig<typeof import("./api/chat")>();
  return { ...m, streamChat: vi.fn(m.streamChat) };
});

// ---------------------------------------------------------------- pure parts
describe("engine: heading and gait", () => {
  it("picks one of 8 sprite directions and only turns once clearly nearer another (hysteresis)", () => {
    expect(dirFor(0)).toBe("e");
    expect(dirFor(90)).toBe("n");
    expect(dirFor(-90)).toBe("s");
    expect(dirFor(180)).toBe("w");
    expect(dirFor(-45)).toBe("se");
    expect(dirFor(30, "e")).toBe("e"); // 30 degrees off: keep facing east
    expect(dirFor(33, "e")).toBe("ne"); // more than 31 degrees off: turn
    expect(dirFor(179, "w")).toBe("w");
    expect(dirFor(-179, "w")).toBe("w"); // across the +-180 seam
  });
  it("locks the walk cycle to the ground, with a longer stride when going faster than the drawn speed", () => {
    const g = GAIT.ga;
    expect(phaseStep(g.ref, 1, g.stride, g.ref)).toBeCloseTo(g.ref / g.stride);
    expect(phaseStep(4, 1, 1, 1)).toBeCloseTo(2); // 4x the speed: 2x the cycles, not 4x
    expect(phaseStep(0.5, 1, 1, 1)).toBeCloseTo(0.5); // slower than drawn: plain proportion
  });
});

describe("engine: the walk grid", () => {
  const wall: Pt[] = [[4, 0], [6, 0], [6, 8], [4, 8]];
  const grid = new Grid({ bounds: [0, 0, 10, 10], block: [wall], allow: [], paths: [], pathW: 2, yard: [] });
  it("blocks what is blocked and walks around it with A*", () => {
    expect(grid.walkable([5, 4])).toBe(false);
    expect(grid.walkable([2, 4])).toBe(true);
    const r = grid.route([1, 5], [9, 5]);
    expect(r[0]).toEqual([1, 5]);
    expect(r.at(-1)).toEqual([9, 5]);
    // every straight piece of the route is free of the wall
    for (let i = 0; i + 1 < r.length; i++) expect(grid.lineFree(r[i], r[i + 1])).toBe(true);
    // it had to go over the top of the wall (y > 8)
    expect(Math.max(...r.map((p) => p[1]))).toBeGreaterThan(8);
  });
  it("prefers the road to the grass", () => {
    const road = new Grid({ bounds: [0, 0, 10, 10], block: [], paths: [[[0, 8], [10, 8]]], pathW: 2, yard: [] });
    const r = road.route([0.5, 5], [9.5, 5]); // a long way over open grass, or down to the road and back up?
    expect(r.length).toBeGreaterThanOrEqual(2);
    expect(road.onRoad([5, 8])).toBe(true);
    expect(road.onRoad([5, 2])).toBe(false);
  });
  it("smooths a route into a curve ending where it ends, and tests polygons", () => {
    const s = smooth([[0, 0], [4, 0], [4, 4]], 0.5);
    expect(s.at(-1)).toEqual([4, 4]);
    expect(s.length).toBeGreaterThan(8);
    expect(inPoly(5, 4, wall)).toBe(true);
    expect(inPoly(1, 4, wall)).toBe(false);
  });
});

describe("chickens: levels and growth", () => {
  it("100 XP a level from level 1; chick, young, grown, master at levels 1, 2-4, 5-9, 10+", () => {
    expect([levelOf(0), levelOf(99), levelOf(100), levelOf(250), levelOf(-5)]).toEqual([1, 1, 2, 3, 1]);
    expect(xpInLevel(250)).toBe(50);
    expect([1, 2, 4, 5, 9, 10, 40].map(stageOf)).toEqual([1, 2, 2, 3, 3, 4, 4]);
    expect(artFile("toan", 4)).toBe("toan-4.webp"); // the master has its own costume, with the halo
    expect(artFile("zzz", 1)).toBe("zzz.webp"); // no drawing for the stage: the grown one
    expect([1, 2, 3, 4].map((s) => artFile("khmt", s))).toEqual(["khmt-1.webp", "khmt-2.webp", "khmt.webp", "khmt-4.webp"]);
    // an angry chicken shows the angry picture, drawn grown, whatever its stage
    expect([1, 2, 4].map((s) => artFile("anh", s, true))).toEqual(["anh-gian.webp", "anh-gian.webp", "anh-gian.webp"]);
    expect(artFile("zzz", 2, true)).toBe("zzz.webp");
  });
  it("lists per stage as in the contract", () => {
    expect(subjectsFor("g6_9").map((s) => s.id)).toEqual(["toan", "van", "anh", "khoahoc", "su", "dia", "cd", "tin", "cn", "nt", "kn"]);
    expect(subjectsFor("g10_12").map((s) => s.id)).toContain("li");
    expect(subjectsFor("uni")).toHaveLength(11);
    const art = Object.fromEntries(ALL_SUBJECTS.map((s) => [s.id, s.art]));
    expect([art.nt, art.kn, art.toanhoc, art.nna]).toEqual(["nghethuat", "kynang", "toan", "anh"]);
  });
});

describe("tray: what a typed line means", () => {
  it("routes the app's own errands and sends the rest to the chicken", () => {
    expect(routeText("thi thử ở đâu")).toBe("help");
    expect(routeText("chụp vở")).toBe("notes");
    expect(routeText("cho em đề thật")).toBe("mock");
    expect(routeText("cho em luyện tập")).toBe("practice");
    expect(routeText("em muốn được 8 điểm Toán")).toBe("goal");
    expect(routeText("cộng hai phân số thế nào")).toBe("chat"); // a subject question, not app help
    expect(routeText("đề thật ở đâu")).toBe("help");
    expect(routeText("1 + 1 bằng mấy")).toBe("chat");
    expect(routeText("chụp vở", true)).toBe("chat"); // the little ones have no notes
    expect(routeText("đề thật", true)).toBe("chat");
  });
  it("answers app questions from the guide map", () => {
    expect(helpTopic("Đề thật ở đâu?")).toBe("arena");
    expect(helpTopic("where is the study room")).toBe("study");
    expect(helpTopic("blah")).toBeNull();
  });
  it("offers in 1 hour, tonight (only while it is ahead) and tomorrow", () => {
    const noon = new Date(2026, 10, 22, 12, 0);
    expect(laterOptions(noon, {}).map((o) => o.key)).toEqual(["in1h", "tonight", "tomorrow"]);
    expect(laterOptions(noon, {})[1].time).toBe("20:00");
    expect(laterOptions(noon, { sessionStart: "19:30", sessionToday: true })[1].time).toBe("19:30");
    const late = new Date(2026, 10, 22, 21, 0);
    expect(laterOptions(late, {}).map((o) => o.key)).toEqual(["in1h", "tomorrow"]);
    expect(laterOptions(late, { kid: true }).at(-1)!.time).toBe("18:00");
  });
});

// ---------------------------------------------------------------- mock API
describe("mock Làng gà API: taking chickens", () => {
  beforeEach(() => {
    localStorage.setItem("mentor.mock.users", JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: null, birth_year: 2010, language: "vi", theme: "system", quiet_until: null, avatar: "nam" } } }));
  });
  it("takes, refuses a second take, keeps XP when let go and gives it back when taken again", async () => {
    const t = "mock-u-hs";
    expect((await lg.getVillage(t)).chickens).toEqual([]);
    const c = await lg.takeChicken(t, "toan");
    expect(c).toMatchObject({ id: "toan", level: 1, stage: 1, name_vi: "Gà Toán" });
    await expect(lg.takeChicken(t, "toan")).rejects.toMatchObject({ status: 409 });
    await expect(lg.takeChicken(t, "khmt")).rejects.toMatchObject({ status: 400 }); // not in this stage
    expect(mockGiveXp(t, "toan", 250)).toBe(true); // lv 1 -> 3
    expect((await lg.getVillage(t)).news[0].text_vi).toMatch(/lên cấp 3/);
    await lg.letGo(t, "toan");
    expect((await lg.getVillage(t)).chickens).toHaveLength(0);
    const back = await lg.takeChicken(t, "toan");
    expect(back).toMatchObject({ xp: 250, level: 3, stage: 2, xp_in_level: 50 });
    const m = await lg.getMarket(t);
    expect(m.chickens.find((x) => x.id === "toan")?.owned).toBe(true);
    expect(m.chickens.some((x) => x.id === "khmt")).toBe(false);
  });
});

// ---------------------------------------------------------------- screens
function seed(opts: { birth?: number | null; language?: string | null; avatar?: string | null; chickens?: string[]; angry?: Record<string, string> } = {}) {
  const { birth = 2010, language = "vi", avatar = "nam", chickens = ["toan", "van", "anh"], angry } = opts;
  localStorage.setItem("mentor.mock.users", JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: null, birth_year: birth, language, theme: "system", quiet_until: null, avatar } } }));
  localStorage.setItem("mentor.token", "mock-u-hs");
  localStorage.setItem("mentor.lang", "vi");
  if (chickens.length) localStorage.setItem("mentor.mock.lg.u-hs", JSON.stringify({ chickens: chickens.map((id) => ({ id, xp: 0, taken_at: "2026-11-01T00:00:00Z" })), ...(angry ? { angry } : {}) }));
}
const open = (path = "/") =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
const thread = () => screen.findByRole("log", { name: "Trò chuyện với gà" });
const seenHello = () => localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["lg-hello", "lg-village"]));

beforeEach(async () => {
  await i18n.changeLanguage("vi");
});
afterEach(() => vi.restoreAllMocks());

describe("login", () => {
  it("student is picked already; empty boxes are asked for, not sent; then the same errors as before; no Mực", async () => {
    localStorage.setItem("mentor.lang", "vi");
    const ui = userEvent.setup();
    open();
    expect(await screen.findByRole("radio", { name: "Học sinh" })).toBeChecked();
    await ui.click(screen.getByRole("button", { name: "Đăng nhập" }));
    expect(await screen.findByText("Điền tài khoản và mật khẩu nhé.")).toBeInTheDocument();
    expect(screen.queryByText("Sai tài khoản hoặc mật khẩu.")).toBeNull();
    await ui.type(screen.getByLabelText("Tài khoản"), "hocsinh");
    await ui.type(screen.getByLabelText("Mật khẩu"), "sai");
    await ui.click(screen.getByRole("button", { name: "Đăng nhập" }));
    expect(await screen.findByText("Sai tài khoản hoặc mật khẩu.")).toBeInTheDocument();
    expect(document.querySelector("mentor-mascot")).toBeNull();
    expect(document.querySelector(".cg")).not.toBeNull(); // the chicken guide stands in its place
  });
});

describe("first run", () => {
  it("language, birth year (then locked), boy or girl, then up to 3 chickens, and into the village", async () => {
    seed({ birth: null, language: null, avatar: null, chickens: [] });
    localStorage.removeItem("mentor.lang"); // nothing picked on the login screen yet
    const ui = userEvent.setup();
    open();
    await ui.click(await screen.findByRole("button", { name: /Tiếng Việt/ }));
    const year = await screen.findByRole("combobox", { name: "Năm sinh" });
    const next = screen.getByRole("button", { name: "Tiếp" });
    expect(next).toBeDisabled();
    await ui.selectOptions(year, "2010");
    expect(screen.getByText("THPT")).toBeInTheDocument(); // the level name only, never an age or grade
    await ui.click(next);
    await ui.click(await screen.findByRole("button", { name: /Bạn nữ/ }));
    await ui.click(screen.getByRole("button", { name: "Tiếp" }));
    expect(await screen.findByText("Chọn ít nhất 1 gà", { selector: "button" })).toBeDisabled();
    await screen.findByRole("button", { name: /Gà Toán.*khóa/ });
    for (const n of ["Gà Toán", "Gà Văn", "Gà Lí", "Gà Hóa"]) await ui.click(within(document.querySelector<HTMLElement>(".lg-grid")!).getByRole("button", { name: new RegExp(n) }));
    expect(screen.getByText("Đã chọn 3/3")).toBeInTheDocument(); // a fourth is not taken
    await ui.click(screen.getByRole("button", { name: "Vào làng" }));
    expect(await screen.findByRole("button", { name: /Cài đặt/ })).toBeInTheDocument(); // the village
    const stored = JSON.parse(localStorage.getItem("mentor.mock.lg.u-hs")!) as { chickens: { id: string }[] };
    expect(stored.chickens.map((c) => c.id)).toEqual(["toan", "van", "li"]);
    expect(JSON.parse(localStorage.getItem("mentor.mock.users")!).hocsinh.user.avatar).toBe("nu");
  });

  it("a language already picked on the login screen is not asked again", async () => {
    seed({ birth: null, language: null, avatar: null, chickens: [] });
    open();
    expect(await screen.findByRole("combobox", { name: "Năm sinh" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Tiếng Việt/ })).toBeNull();
  });

  it("an existing student with no chickens goes straight to choosing them", async () => {
    seed({ chickens: [] });
    open();
    expect(await screen.findByText("Chọn gà")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).toBeNull();
  });
});

describe("village: the chicken speaks first", () => {
  it("introduces itself once, suggests what to do now with Học / Để sau / Việc khác; no Mực, the chicken guide instead", async () => {
    seed();
    open();
    const log = await thread();
    expect(await within(log).findByText(/mình là Gà Toán/)).toBeInTheDocument();
    const go = await within(log).findByRole("link", { name: /Học tiếp/ });
    expect(go.getAttribute("href")).toMatch(/^\/khoa-hoc\//);
    expect(within(log).getByRole("button", { name: "Để sau" })).toBeInTheDocument();
    expect(within(log).getByRole("button", { name: "Việc khác" })).toBeInTheDocument();
    expect(hasSeen("u-hs", "lg-hello")).toBe(true);
    // chickens with their levels, places, market, list view toggle
    expect(await screen.findByRole("button", { name: /Gà Toán, cấp 1/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đấu trường" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Bảng tin/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thư viện" })).toBeInTheDocument(); // grade 6 and up: the notes shelf
    expect(document.querySelector("mentor-mascot")).toBeNull();
    expect(document.querySelector(".cg")).not.toBeNull();
  });

  it("an angry chicken speaks first: why, and a Học button; chickens wear only a level badge and keep their name in the label", async () => {
    seed({ angry: { van: "Đọc hiểu" } });
    seenHello();
    open();
    const log = await thread();
    expect(await within(log).findByText(/Gà Văn giận rồi: 7 ngày chưa học «Đọc hiểu»\. Học 10 phút cho gà vui nhé!/)).toBeInTheDocument();
    expect(within(log).getByRole("link", { name: /Học/ })).toBeInTheDocument();
    const btn = await screen.findByRole("button", { name: /Gà Văn, cấp 1/ });
    expect(btn.getAttribute("title")).toBe("Gà Văn");
    // the angry picture is drawn (a still: a costume without an animated stand)
    await waitFor(() => expect(document.querySelector('.lg-actor[data-id="van"]')?.classList.contains("angry")).toBe(true));
    expect(document.querySelector(".lg-plate.ga .nm")).toBeNull(); // no name plate on a chicken, only the level badge
    expect(document.querySelector(".lg-plate.ga .lv")?.textContent).toBe("1");
  });

  it("Để sau sets a real reminder, with the streak in the greeting", async () => {
    seed();
    seenHello();
    const ui = userEvent.setup();
    open();
    const log = await thread();
    expect(await within(log).findByText(/Chào Lan!/)).toBeInTheDocument();
    expect(within(log).queryByText(/mình là Gà/)).toBeNull();
    expect(within(log).getByText(/Chuỗi 3 ngày đang chờ/)).toBeInTheDocument();
    await ui.click(await within(log).findByRole("button", { name: "Để sau" }));
    expect(await within(log).findByText("Nhắc em lúc nào?")).toBeInTheDocument();
    expect(within(log).queryByRole("button", { name: "Để sau" })).toBeNull();
    await ui.click(within(log).getByRole("button", { name: /^Mai / }));
    expect(await within(log).findByText(/Đã hẹn .* mai\. Tới giờ mình báo, kể cả khi tắt app\./)).toBeInTheDocument();
    const { api } = await import("../api");
    const rs = (await api.getReminders("mock-u-hs")).reminders;
    expect(rs.some((r) => r.kind === "later" && r.status === "scheduled")).toBe(true);
  });

  it("Việc khác lists the other things to do today", async () => {
    seed();
    seenHello();
    const ui = userEvent.setup();
    open();
    const log = await thread();
    await ui.click(await within(log).findByRole("button", { name: "Việc khác" }));
    expect(await within(log).findByText(/Hôm nay còn:/)).toBeInTheDocument();
    expect(await within(log).findByRole("button", { name: /5 câu ôn/ })).toBeInTheDocument();
    expect(within(log).queryByRole("link", { name: "Đấu trường" })).toBeNull(); // the arena has one door: its sign on the map
    expect(within(log).getByRole("button", { name: "Chụp vở" })).toBeInTheDocument();
  });

  it("shows a retry when the village does not load, and opens it after Thử lại", async () => {
    seed();
    seenHello();
    const spy = vi.spyOn(lg, "getVillage").mockRejectedValueOnce(new Error("offline"));
    const ui = userEvent.setup();
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Chưa mở được làng");
    await ui.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(await thread()).toBeInTheDocument();
    spy.mockRestore();
  });

  it("the tray points mock exams at the arena (no second place to start them)", async () => {
    seed();
    seenHello();
    const ui = userEvent.setup();
    open();
    const log = await thread();
    await ui.type(screen.getByRole("textbox", { name: "Nhắn cho gà" }), "cho em đề thi thử{Enter}");
    expect(await within(log).findByText(/Đề thi thật và thi thử ở Đấu trường/)).toBeInTheDocument(); // words only: the map sign is the one way in
    expect(within(log).queryByRole("link", { name: "Đấu trường" })).toBeNull();
  });

  it("the box: app questions get a local answer, practice offers a session, goals are saved, the rest goes to the chicken", async () => {
    seed();
    seenHello();
    const ui = userEvent.setup();
    open();
    const log = await thread();
    await within(log).findByText(/Chào Lan!/);
    const box = screen.getByRole("textbox", { name: "Nhắn cho gà" });

    await ui.type(box, "đề thật ở đâu{Enter}");
    expect(await within(log).findByText(/Đề thi thật ở Đấu trường/)).toBeInTheDocument();

    await ui.type(box, "cho em luyện tập{Enter}");
    expect(await within(log).findByText(/Ôn nhanh vài câu nhé/)).toBeInTheDocument();
    expect(await within(log).findByRole("button", { name: /Bắt đầu\s*· 6 phút/ })).toBeInTheDocument();

    await ui.type(box, "em muốn được 8 điểm Toán{Enter}");
    expect(await within(log).findByText(/Đã thêm “em muốn được 8 điểm Toán”/)).toBeInTheDocument();
    const { api } = await import("../api");
    expect((await api.listGoals("mock-u-hs")).some((g) => g.title.includes("8 điểm"))).toBe(true);
    await ui.click(within(log).getByRole("button", { name: "Xem tuần" }));
    expect(await screen.findByRole("dialog", { name: "Tuần này" })).toBeInTheDocument();
    await ui.keyboard("{Escape}");

    await ui.type(box, "xin chào gà{Enter}");
    // the bubble re-renders its Markdown when the stream ends, so wait on the text, not on one node
    await waitFor(() => expect(within(log).getByText(/Gà Toán đây! Em hỏi: "xin chào gà"/)).toBeInTheDocument()); // streamed from /chat/toan
    expect(await within(log).findByRole("link", { name: "Luyện tập" })).toHaveAttribute("href", "/luyen-tap"); // its action
  });

  it("Chụp vở: photos of notes become review questions, then the session opens", async () => {
    seed();
    seenHello();
    const ui = userEvent.setup();
    open();
    const log = await thread();
    await within(log).findByText(/Chào Lan!/);
    await ui.type(screen.getByRole("textbox", { name: "Nhắn cho gà" }), "chụp vở{Enter}");
    expect(await within(log).findByText(/Em chụp trang vở nhé/)).toBeInTheDocument();
    await ui.click(within(log).getByRole("button", { name: "Chọn ảnh vở" }));
    const input = document.querySelector<HTMLInputElement>('input[type="file"][multiple]')!;
    await ui.upload(input, [new File(["x"], "a.jpg", { type: "image/jpeg" }), new File(["y"], "b.jpg", { type: "image/jpeg" })]);
    expect(await within(log).findByText("Vở ghi Điện trường, 2 trang. Mình tạo 6 câu ôn nhé?")).toBeInTheDocument();
    await ui.click(within(log).getByRole("button", { name: "Tạo câu ôn" }));
    expect(await within(log).findByText(/Đã tạo 6 câu\. Ôn lần đầu .*, lần sau sau 3 ngày\./)).toBeInTheDocument();
    expect((await lg.listNotes("mock-u-hs"))[0].title).toBe("Điện trường");
    await ui.click(within(log).getByRole("button", { name: /Ôn ngay/ }));
    expect(await screen.findByRole("img", { name: /^Câu 1/ })).toBeInTheDocument();
  });

  it("an unreadable notes photo says what to do", async () => {
    seed();
    seenHello();
    localStorage.setItem("mentor.mock.badphoto", "1");
    const ui = userEvent.setup();
    open();
    const log = await thread();
    await within(log).findByText(/Chào Lan!/);
    await ui.click(await within(log).findByRole("button", { name: "Việc khác" }));
    await ui.click(await within(log).findByRole("button", { name: "Chụp vở" }));
    await ui.upload(document.querySelector<HTMLInputElement>('input[type="file"][multiple]')!, [new File(["x"], "a.jpg", { type: "image/jpeg" })]);
    expect(await within(log).findByText(/Gà chưa đọc được ảnh/)).toBeInTheDocument();
    localStorage.removeItem("mentor.mock.badphoto");
  });

  it("primary school: two big buttons instead of typing", async () => {
    seed({ birth: 2018 });
    seenHello();
    open();
    const log = await thread();
    expect(await within(log).findByRole("link", { name: "Bắt đầu" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chụp bài" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nói với gà" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Nhắn cho gà" })).toBeNull();
  });

  it("university: the Thư viện place appears", async () => {
    seed({ birth: 2000, chickens: ["khmt"] });
    seenHello();
    open();
    expect(await screen.findByRole("button", { name: "Thư viện" })).toBeInTheDocument();
  });
});

describe("village: sheets", () => {
  it("the market: take a chicken (free), see it turn to 'Đã có', and it joins the village", async () => {
    seed();
    seenHello();
    const ui = userEvent.setup();
    open();
    await ui.click(await screen.findByRole("button", { name: /Chợ gà: nhận thêm gà/ }));
    const sheet = await screen.findByRole("dialog", { name: "Chợ gà" });
    expect(await within(sheet).findByText("Gà Toán")).toBeInTheDocument();
    expect(within(sheet).getAllByText(/✓ Đã có/)).toHaveLength(3);
    await ui.click((await within(sheet).findAllByRole("button", { name: "Nhận" }))[0]);
    expect(await screen.findByText(/Đã nhận Gà/)).toBeInTheDocument();
    await waitFor(() => expect(within(sheet).getAllByText(/✓ Đã có/)).toHaveLength(4));
    expect(await screen.findByRole("button", { name: /Gà Khoa học|Gà Lí/ })).toBeInTheDocument();
    await ui.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("the ring opens the week (7 days, goals); Escape closes it", async () => {
    seed();
    seenHello();
    const ui = userEvent.setup();
    open();
    await ui.click(await screen.findByRole("button", { name: /Tuần này: 3 trên 5 buổi/ }));
    const sheet = await screen.findByRole("dialog", { name: "Tuần này" });
    const week = await within(sheet).findByLabelText("Lịch 7 ngày do Mentor xếp");
    expect(week.children).toHaveLength(7);
    expect(await within(sheet).findByRole("link", { name: "Xem tiến độ và mục tiêu" })).toHaveAttribute("href", "/tien-do");
    await ui.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Tuần này" })).toBeNull());
  });

  it("the notice board lists the news", async () => {
    seed();
    seenHello();
    const ui = userEvent.setup();
    open();
    const { mockGiveXp: give } = await import("./api");
    give("mock-u-hs", "toan", 120);
    await ui.click(await screen.findByRole("button", { name: /Bảng tin/ }));
    expect(await screen.findByText(/Gà Toán lên cấp 2/)).toBeInTheDocument();
  });

  it("settings keeps every row of the old popover", async () => {
    seed();
    seenHello();
    const ui = userEvent.setup();
    open();
    await ui.click(await screen.findByRole("button", { name: "Cài đặt" }));
    const s = await screen.findByRole("dialog", { name: "Cài đặt" });
    for (const label of ["Năm sinh", "Ngôn ngữ", "Giao diện", "Nhắc học", "Tạm im lặng", "Hướng dẫn của gà"]) expect(within(s).getByText(label)).toBeInTheDocument();
    expect(within(s).getByRole("switch", { name: "Nhắc học" })).toBeChecked();
    expect(within(s).getByRole("button", { name: "Xem lại từ đầu" })).toBeInTheDocument();
    await ui.click(within(s).getByRole("button", { name: "English" }));
    await waitFor(() => expect(within(s).getByRole("button", { name: "Log out" })).toBeInTheDocument());
    await waitFor(() => expect(JSON.parse(localStorage.getItem("mentor.mock.users")!).hocsinh.user.language).toBe("en")); // the save finishes before the test ends
    expect(within(s).getByText(/^Mentor \d/)).toBeInTheDocument(); // the version
  });

  it("the list view shows chickens and places", async () => {
    seed();
    seenHello();
    const ui = userEvent.setup();
    open();
    await ui.click(await screen.findByRole("button", { name: "Xem dạng danh sách" }));
    const aside = await screen.findByRole("complementary", { name: "Làng gà dạng danh sách" });
    expect(within(aside).getByRole("link", { name: /Gà Toán · cấp 1/ })).toHaveAttribute("href", "/chuong/toan");
    expect(within(aside).getByRole("link", { name: /Đấu trường/ })).toHaveAttribute("href", "/dau-truong");
    expect(within(aside).getByRole("link", { name: /Phòng tự học/ })).toHaveAttribute("href", "/phong-tu-hoc");
  });
});

describe("tray: a slow or broken chicken", () => {
  it("watchSlow: soft line after 15 s, drops the call at 50 s, cancel is its own thing", () => {
    vi.useFakeTimers();
    const c = new AbortController();
    const slow = vi.fn();
    const w = watchSlow(c, slow);
    vi.advanceTimersByTime(14999);
    expect(slow).not.toHaveBeenCalled();
    vi.advanceTimersByTime(2);
    expect(slow).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(35000);
    expect(c.signal.aborted).toBe(true);
    expect(w.timedOut).toBe(true);
    const c2 = new AbortController();
    const w2 = watchSlow(c2, () => {});
    w2.cancel();
    expect(c2.signal.aborted && w2.cancelled && !w2.timedOut).toBe(true);
    vi.useRealTimers();
  });

  it("shows Gà đang nghĩ at once, then an error event becomes a friendly line with Thử lại that works", async () => {
    seed();
    seenHello();
    vi.mocked(streamChat).mockImplementationOnce(async (_t, _c, _r, onEvent) => {
      onEvent({ event: "error", data: { code: "model_unavailable" } } as never);
    });
    const ui = userEvent.setup();
    open();
    const log = await thread();
    await within(log).findByText(/Chào Lan!/);
    await ui.type(screen.getByRole("textbox", { name: "Nhắn cho gà" }), "xin chào gà{Enter}");
    expect(await within(log).findByText("Gà chưa trả lời được. Thử lại nhé.")).toBeInTheDocument();
    await ui.click(within(log).getByRole("button", { name: "Thử lại" }));
    // the bubble re-renders its Markdown when the stream ends, so wait on the text, not on one node
    await waitFor(() => expect(within(log).getByText(/Gà Toán đây! Em hỏi: "xin chào gà"/)).toBeInTheDocument());
    expect(within(log).queryByRole("button", { name: "Thử lại" })).toBeNull();
  });

  it("a network failure says so; a hanging call gets the soft line and Hủy, then 50 s ends it with Thử lại", async () => {
    seed();
    seenHello();
    vi.mocked(streamChat).mockImplementationOnce(async () => {
      throw new (await import("../api")).AskError(0, "network");
    });
    const ui = userEvent.setup();
    open();
    const log = await thread();
    await within(log).findByText(/Chào Lan!/);
    const box = screen.getByRole("textbox", { name: "Nhắn cho gà" });
    await ui.type(box, "một{Enter}");
    expect(await within(log).findByText("Chưa kết nối được. Thử lại sau nhé.")).toBeInTheDocument();

    const hang = async (_t: string, _c: string, _r: unknown, _e: unknown, signal?: AbortSignal) =>
      new Promise<void>((_ok, bad) => signal?.addEventListener("abort", () => bad(new DOMException("aborted", "AbortError"))));
    vi.mocked(streamChat).mockImplementationOnce(hang as never);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await ui.type(box, "hai{Enter}");
    expect(await within(log).findByText("Gà đang nghĩ…")).toBeInTheDocument();
    await act(async () => void vi.advanceTimersByTime(16000));
    expect(within(log).getByText("Gà nghĩ hơi lâu…")).toBeInTheDocument();
    await act(async () => void vi.advanceTimersByTime(36000));
    vi.useRealTimers();
    expect(await within(log).findAllByText("Gà chưa trả lời được. Thử lại nhé.")).toHaveLength(1);
    expect(within(log).getByRole("button", { name: "Thử lại" })).toBeInTheDocument();

    vi.mocked(streamChat).mockImplementationOnce(hang as never);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await ui.click(within(log).getByRole("button", { name: "Thử lại" }));
    await within(log).findByText("Gà đang nghĩ…");
    await act(async () => void vi.advanceTimersByTime(16000));
    vi.useRealTimers();
    await ui.click(within(log).getByRole("button", { name: "Hủy" }));
    expect(await within(log).findByText(/Đã hủy/)).toBeInTheDocument();
  });
});
