import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "./i18n";
import { App } from "./App";
import { AuthProvider } from "./state/auth";
import { hasSeen } from "./lib/tours";

/** The student's one screen (mockups/hs-03) and practice inside a course (mockups/hs-04), on the in-browser mock API. */

function seed(birth: number) {
  localStorage.setItem("mentor.mock.users", JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: null, birth_year: birth, language: "vi", theme: "system", quiet_until: null } } }));
  localStorage.setItem("mentor.token", "mock-u-hs");
  localStorage.setItem("mentor.lang", "vi");
}
const open = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
const thread = () => screen.findByRole("log", { name: "Trò chuyện với Mực" });
const SCHOOL = 2010;

beforeEach(async () => {
  await i18n.changeLanguage("vi");
});

describe("Today: Mực speaks first", () => {
  it("introduces himself once, then suggests what to do now with quick replies; courses in a strip; no floating Mực", async () => {
    seed(SCHOOL);
    open("/");
    const log = await thread();
    expect(await within(log).findByText(/mình là Mực/)).toBeInTheDocument();
    const go = await within(log).findByRole("link", { name: /Học tiếp/ });
    expect(go.getAttribute("href")).toMatch(/^\/khoa-hoc\//);
    expect(within(log).getByRole("button", { name: "Để sau" })).toBeInTheDocument();
    expect(within(log).getByRole("button", { name: "Việc khác" })).toBeInTheDocument();
    expect(hasSeen("u-hs", "today")).toBe(true);

    expect(await screen.findByRole("link", { name: /Vật lí 11: Điện trường/ })).toHaveAttribute("href", "/khoa-hoc/vat-li-11-dien-truong");
    expect(screen.getByRole("link", { name: "Tìm khóa" })).toHaveAttribute("href", "/khoa-hoc/tim-kiem");
    expect(screen.queryByRole("link", { name: /Đề tài của bạn/ })).toBeNull();
    expect(document.querySelector("mentor-mascot")).toHaveAttribute("hidden");
    expect(document.documentElement).toHaveAttribute("data-no-mascot");
  });

  it("Later sets a real reminder (a system notification at that time), with the streak in the greeting", async () => {
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["today"])); // not the first visit: no introduction
    seed(SCHOOL);
    const ui = userEvent.setup();
    open("/");
    const log = await thread();
    expect(await within(log).findByText(/Chào Lan!/)).toBeInTheDocument();
    expect(within(log).queryByText(/mình là Mực/)).toBeNull();
    expect(within(log).getByText(/Chuỗi 3 ngày đang chờ/)).toBeInTheDocument();
    await ui.click(await within(log).findByRole("button", { name: "Để sau" }));
    expect(await within(log).findByText("Nhắc em lúc nào?")).toBeInTheDocument();
    expect(within(log).queryByRole("button", { name: "Để sau" })).toBeNull(); // used replies go away
    expect(within(log).getByRole("button", { name: "Sau 1 tiếng" })).toBeInTheDocument();
    await ui.click(within(log).getByRole("button", { name: /^Mai / }));
    expect(await within(log).findByText(/Đã hẹn .* mai\. Tới giờ mình báo, kể cả khi tắt app\./)).toBeInTheDocument();
    const { api } = await import("./api");
    const rs = (await api.getReminders("mock-u-hs")).reminders;
    expect(rs.some((r) => r.kind === "later" && r.status === "scheduled" && r.text_vi.includes("Tới giờ hẹn rồi"))).toBe(true);
  });

  it("Something else: today's other things, picked with one tap", async () => {
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["today"]));
    seed(SCHOOL);
    const ui = userEvent.setup();
    open("/");
    const log = await thread();
    await ui.click(await within(log).findByRole("button", { name: "Việc khác" }));
    expect(await within(log).findByText(/Hôm nay còn:/)).toBeInTheDocument();
    expect(await within(log).findByRole("button", { name: /5 câu ôn/ })).toBeInTheDocument();
    expect(within(log).getByRole("button", { name: /Thi thử mẫu/ })).toBeInTheDocument();
  });

  it("the box continues the conversation: how to use the app, and practice", async () => {
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["today"]));
    seed(SCHOOL);
    const ui = userEvent.setup();
    open("/");
    const log = await thread();
    await within(log).findByText(/Chào Lan!/);
    const box = screen.getByPlaceholderText("Nhắn cho Mực");

    const before = log.querySelectorAll(".td-msg.muc").length;
    await ui.type(box, "thi thử ở đâu{Enter}");
    expect(await within(log).findByText("thi thử ở đâu")).toBeInTheDocument();
    await waitFor(() => expect(log.querySelectorAll(".td-msg.muc").length).toBeGreaterThan(before)); // Mực answers from the guide texts

    await ui.type(box, "cho em luyện tập{Enter}");
    expect(await within(log).findByText(/Ôn nhanh vài câu nhé/)).toBeInTheDocument();
    expect(await within(log).findByRole("button", { name: /Bắt đầu\s*· 6 phút/ })).toBeInTheDocument();
  });

  it("the ring opens the week as a sheet; Escape closes it", async () => {
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["today"]));
    seed(SCHOOL);
    const ui = userEvent.setup();
    open("/");
    await ui.click(await screen.findByRole("button", { name: /Tiến độ tuần này/ }));
    const sheet = await screen.findByRole("dialog", { name: "Tuần này" });
    // the compact sheet: 7 day cells, goals as one-line rows with a thin bar; no goals heading, no courses
    const week = await within(sheet).findByLabelText("Lịch 7 ngày do Mentor xếp");
    expect(week.children).toHaveLength(7);
    expect((await within(sheet).findAllByRole("progressbar")).length).toBeGreaterThan(0);
    expect(within(sheet).queryByRole("heading", { name: "Khóa học" })).toBeNull();
    await ui.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Tuần này" })).toBeNull());
  });

  it("the strip label is for screen readers only", async () => {
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["today"]));
    seed(SCHOOL);
    open("/");
    const h = await screen.findByRole("heading", { name: "Khóa của em" });
    expect(h).toHaveClass("sr");
  });

  it("primary school: two big buttons instead of typing", async () => {
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["today"]));
    seed(2018);
    open("/");
    const log = await thread();
    expect(await within(log).findByText(/Cùng học/)).toBeInTheDocument();
    expect(within(log).getByRole("link", { name: "Bắt đầu" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chụp bài" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nói với Mực" })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Nhắn cho Mực")).toBeNull();
  });

  it("university: the research topic sits in the strip", async () => {
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["today"]));
    seed(2000);
    open("/");
    expect(await screen.findByRole("link", { name: /Đề tài của bạn/ })).toHaveAttribute("href", "/nghien-cuu");
  });
});

describe("Progress page (hs-12)", () => {
  it("goals and courses as rows, the week as 7 cells, the reasons in a fold, home goes to Today", async () => {
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["today", "progress"]));
    seed(SCHOOL);
    open("/tien-do");
    expect(await screen.findByRole("heading", { name: "Mục tiêu" })).toBeInTheDocument();
    const week = await screen.findByLabelText("Lịch 7 ngày do Mentor xếp");
    expect(week.children).toHaveLength(7);
    expect(await screen.findByText("Vì sao xếp thế này")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /Vật lí 11: Điện trường/ })).toHaveAttribute("href", "/khoa-hoc/vat-li-11-dien-truong");
    expect(screen.getByRole("link", { name: "Về màn chính" })).toHaveAttribute("href", "/");
  });
});

describe("practice inside a course", () => {
  it("the Luyện tập group of the course tree: solid level ticked, Mentor's level marked, closed levels not tappable, tests inside Kiểm tra", async () => {
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["today", "course"]));
    seed(SCHOOL);
    open("/khoa-hoc/vat-li-11-dien-truong");
    const ladder = await waitFor(() => {
      const el = document.querySelector(".ct-grp.ladder") as HTMLElement | null;
      if (!el) throw new Error("no ladder yet");
      return el;
    });
    const node = (name: string) => [...ladder.querySelectorAll<HTMLElement>(".ct-node")].find((n) => n.textContent?.includes(name))!;
    expect(node("Nhận biết")).toHaveClass("done");
    expect(node("Thông hiểu")).toHaveAttribute("aria-current", "step");
    expect(node("Thông hiểu")).toBeEnabled();
    expect(node("Vận dụng cao").tagName).toBe("SPAN"); // nothing studied at that level yet: not tappable
    const tests = [...document.querySelectorAll<HTMLDetailsElement>("details.ct-grp")].find((d) => d.querySelector("summary")?.textContent?.includes("Kiểm tra"))!;
    expect(tests.open).toBe(false);
    expect(within(tests).getByRole("button", { name: /Thi thử mẫu/ })).toBeEnabled();
  });

});

describe("Today: Chụp vở", () => {
  it("photos of notes become review questions: Mực's line, then confirm, then start the session", async () => {
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["today"]));
    seed(SCHOOL);
    const ui = userEvent.setup();
    open("/");
    const log = await thread();
    await within(log).findByText(/Chào Lan!/);
    await ui.type(screen.getByPlaceholderText("Nhắn cho Mực"), "chụp vở{Enter}");
    expect(await within(log).findByText(/Em chụp trang vở nhé/)).toBeInTheDocument();
    await ui.click(within(log).getByRole("button", { name: "Chọn ảnh vở" }));
    const input = document.querySelector<HTMLInputElement>('input[type="file"][multiple]')!;
    await ui.upload(input, [new File(["x"], "a.jpg", { type: "image/jpeg" }), new File(["y"], "b.jpg", { type: "image/jpeg" })]);
    expect(await within(log).findByText("Vở ghi Điện trường, 2 trang. Mình tạo 6 câu ôn nhé?")).toBeInTheDocument();
    expect(within(log).getByRole("button", { name: "Thôi" })).toBeInTheDocument();
    await ui.click(within(log).getByRole("button", { name: "Tạo câu ôn" }));
    expect(await within(log).findByText(/Đã tạo 6 câu\. Ôn lần đầu .*, lần sau sau 3 ngày\./)).toBeInTheDocument();
    await ui.click(within(log).getByRole("button", { name: /Ôn ngay/ }));
    expect(await screen.findByRole("img", { name: /^Câu 1/ })).toBeInTheDocument(); // the practice session opened
  });

  it("an unreadable photo says what to do", async () => {
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["today"]));
    localStorage.setItem("mentor.mock.badphoto", "1");
    seed(SCHOOL);
    const ui = userEvent.setup();
    open("/");
    const log = await thread();
    await within(log).findByText(/Chào Lan!/);
    await ui.click(await within(log).findByRole("button", { name: "Việc khác" }));
    await ui.click(await within(log).findByRole("button", { name: "Chụp vở" }));
    const input = document.querySelector<HTMLInputElement>('input[type="file"][multiple]')!;
    await ui.upload(input, [new File(["x"], "a.jpg", { type: "image/jpeg" })]);
    expect(await within(log).findByText(/Mực chưa đọc được ảnh/)).toBeInTheDocument();
    localStorage.removeItem("mentor.mock.badphoto");
  });

  it("the little ones do not get it", async () => {
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["today"]));
    seed(2018);
    open("/");
    await thread();
    await screen.findByRole("link", { name: "Tìm khóa" });
    expect(screen.queryByRole("button", { name: "Chụp vở" })).toBeNull();
  });
});
