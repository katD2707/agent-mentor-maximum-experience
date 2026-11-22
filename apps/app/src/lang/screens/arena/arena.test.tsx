import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "../../../i18n";
import { App } from "../../../App";
import { AuthProvider } from "../../../state/auth";
import { setPracticeApi, type PracticeApi } from "../../../api";
import { createMockPractice } from "../../../api/mock-practice-api";
import { courseMockSize } from "./CourseTests";

function student(age = "g10_12") {
  localStorage.setItem(
    "mentor.mock.users",
    JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: age, birth_year: ({ g1_5: 2018, g6_9: 2013, g10_12: 2010, uni: 2000 } as Record<string, number>)[age], language: "vi", theme: "system", quiet_until: null, avatar: "nam" } } }),
  );
  localStorage.setItem("mentor.token", "mock-u-hs");
  localStorage.setItem("mentor.lang", "vi");
  localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["lg-hello", "lg-village"]));
}
const open = (path: string | { pathname: string; state?: unknown }[], index?: number) =>
  render(
    <MemoryRouter initialEntries={typeof path === "string" ? [path] : path} initialIndex={index}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );

/** The server clock of a running exam, forced to `sec` seconds left (the 5-minute and 1-minute banners). */
function withClock(api: PracticeApi, sec: number): PracticeApi {
  return { ...api, get: async (t, i) => ({ ...(await api.get(t, i)), remaining_sec: sec }), tick: async () => ({ remaining_sec: sec }) };
}
function reduceMotion(on: boolean) {
  return vi.spyOn(window, "matchMedia").mockImplementation(
    (q: string) => ({ matches: on && q.includes("reduce"), media: q, onchange: null, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false }) as MediaQueryList,
  );
}
const learner = () => ({ age_band: "g10_12", language: "vi" });

describe("pure parts", () => {
  it("sizes the course mock like the gateway: 22 questions or all, 2 minutes each, at most 45", () => {
    expect(courseMockSize(40)).toEqual({ items: 22, minutes: 44 });
    expect(courseMockSize(18)).toEqual({ items: 18, minutes: 36 });
    expect(courseMockSize(6)).toEqual({ items: 6, minutes: 12 });
  });
});

describe("Đấu trường: the list", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("vi");
  });
  afterEach(() => sessionStorage.clear());

  it("lists the papers with their boss, 'Đề mẫu' for placeholders, filters by subject and year, and the practice papers apart", async () => {
    student();
    setPracticeApi(createMockPractice({ learner }));
    const ui = userEvent.setup();
    open("/dau-truong");
    expect(await screen.findByRole("heading", { name: "Đấu trường" })).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Đấu trường" });
    expect(within(list).getAllByRole("listitem").length).toBeGreaterThanOrEqual(3);
    expect(within(list).getAllByText("Đề mẫu").length).toBeGreaterThanOrEqual(3);
    expect(within(list).getByText(/THPT 2025 Toán/)).toBeInTheDocument();
    expect(within(list).getAllByText(/Boss Quái Sai Số/).length).toBeGreaterThan(0);
    expect(screen.getByText("Đề thi thật các năm. Bấm giờ như ngày thi.")).toBeInTheDocument();

    await ui.click(screen.getByRole("button", { name: "Anh" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(within(list).getByText(/Tiếng Anh/)).toBeInTheDocument();
    expect(within(list).getByText(/Boss Quái Lỗi Ngữ Pháp/)).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Tất cả" }));
    await ui.selectOptions(screen.getByRole("combobox", { name: "Năm" }), "2024");
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(within(list).getByText(/Đánh giá năng lực/)).toBeInTheDocument();

    // bank mocks live here as non-boss "Đề luyện"
    const practiceList = screen.getByRole("list", { name: "Đề luyện" });
    expect(within(practiceList).getByText("Thi thử mẫu")).toBeInTheDocument();
    expect(within(practiceList).queryByText(/Boss/)).toBeNull();
  });

  it("university students get their end-of-term papers", async () => {
    student("uni");
    setPracticeApi(createMockPractice({ learner: () => ({ age_band: "uni", language: "vi" }) }));
    open("/dau-truong");
    expect(await screen.findByText("Đề cuối kỳ các năm trước. Bấm giờ như ngày thi.")).toBeInTheDocument();
    expect(await screen.findByText(/Cuối kỳ Xác suất thống kê/)).toBeInTheDocument();
  });

  it("the village's Đấu trường place lands here and the old /luyen-tap goes back to the village", async () => {
    student();
    setPracticeApi(createMockPractice({ learner }));
    open("/luyen-tap");
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Đấu trường" })).toBeNull());
    expect(await screen.findByRole("button", { name: /Bảng tin/ })).toBeInTheDocument();
  });
});

describe("Đấu trường: sitting a paper", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("vi");
    student();
  });
  afterEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  async function openPaper(api: PracticeApi, ui: ReturnType<typeof userEvent.setup>) {
    setPracticeApi(api);
    open("/dau-truong");
    const list = await screen.findByRole("list", { name: "Đấu trường" });
    await ui.click(within(list).getAllByRole("link", { name: "Làm đề" })[0]);
    expect(await screen.findByRole("heading", { name: "Sẵn sàng?" })).toBeInTheDocument();
  }

  it("confirm card, then the exam: battle strip with hidden boss HP, power per answered question, clock from the server", async () => {
    const ui = userEvent.setup();
    await openPaper(createMockPractice({ learner, mockMinutes: 1 }), ui);
    expect(screen.getByText("Boss Quái Sai Số. Hạ boss bằng đề mẫu này.")).toBeInTheDocument();
    expect(screen.getByText("Hết giờ máy tự nộp bài")).toBeInTheDocument();
    expect(screen.getByText("Không có gợi ý")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Bắt đầu" }));

    expect(await screen.findByRole("timer")).toHaveTextContent(/^(01:00|00:59)$/);
    expect(screen.getByRole("heading", { name: "Đang thi" })).toBeInTheDocument();
    expect(screen.getByText("???")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /đã tích lực 0\/5\. Máu boss ẩn đến khi nộp bài/ })).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: /^A\s*14/ }));
    expect(screen.queryByText("Đúng rồi")).toBeNull(); // no feedback in an exam
    expect(screen.getByRole("img", { name: /đã tích lực 1\/5/ })).toBeInTheDocument();
    expect(screen.getByText("Lực 1/5")).toBeInTheDocument();
  }, 30000);

  it("the 5-minute and the 1-minute banners", async () => {
    const ui = userEvent.setup();
    const base = createMockPractice({ learner, mockMinutes: 90 });
    await openPaper(withClock(base, 290), ui);
    await ui.click(screen.getByRole("button", { name: "Bắt đầu" }));
    expect(await screen.findByText("Còn 5 phút")).toBeInTheDocument();
    expect(screen.getByRole("timer")).toHaveClass("warn");
  }, 30000);

  it("a minute left warns in red", async () => {
    const ui = userEvent.setup();
    const base = createMockPractice({ learner, mockMinutes: 90 });
    await openPaper(withClock(base, 55), ui);
    await ui.click(screen.getByRole("button", { name: "Bắt đầu" }));
    expect(await screen.findByText("Còn 1 phút. Hết giờ máy tự nộp bài.")).toBeInTheDocument();
    expect(screen.getByRole("timer")).toHaveClass("crit");
  }, 30000);

  it("at zero the paper is handed in: overlay 'Hết giờ!', boss replay (skippable), result", async () => {
    const ui = userEvent.setup();
    const api = createMockPractice({ learner, mockMinutes: 0.03 }); // 1.8 s
    await openPaper(api, ui);
    await ui.click(screen.getByRole("button", { name: "Bắt đầu" }));
    expect(await screen.findByText("Hết giờ! Bài đã được tự nộp.")).toBeInTheDocument();
    // the replay is skippable
    await ui.click(await screen.findByRole("button", { name: "Bỏ qua" }));
    expect(await screen.findByText("Boss chạy thoát. Lần sau đánh tiếp.")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Xem kết quả" }));
    expect(await screen.findByText("Hết giờ, bài đã được tự nộp.")).toBeInTheDocument();
    expect(screen.getByText("Quái Sai Số chạy thoát")).toBeInTheDocument();
  }, 30000);

  it("submit: confirm with the blank count, reduced motion shows the boss still, then the result with +40 and +50 KN", async () => {
    reduceMotion(true);
    const ui = userEvent.setup();
    await openPaper(createMockPractice({ learner, mockMinutes: 30 }), ui);
    await ui.click(screen.getByRole("button", { name: "Bắt đầu" }));
    await ui.click(await screen.findByRole("button", { name: /^A\s*14/ })); // right
    await ui.click(screen.getByRole("button", { name: "Câu tiếp" }));
    await ui.click(screen.getByRole("button", { name: /^B/ })); // right
    await ui.click(screen.getByRole("button", { name: "Câu tiếp" }));
    await ui.click(screen.getByRole("button", { name: "Câu tiếp" })); // skip the true/false one
    await ui.type(await screen.findByRole("textbox"), "4"); // right
    await ui.click(screen.getByRole("button", { name: "Câu tiếp" }));
    await ui.click(screen.getByRole("button", { name: /^B/ })); // wrong (A is right)
    await ui.click(screen.getByRole("button", { name: "Nộp bài" }));
    const dlg = screen.getByRole("alertdialog");
    expect(within(dlg).getByText("Em đã trả lời 4/5 câu. Nộp xong thì không sửa được nữa.")).toBeInTheDocument();
    expect(within(dlg).getByText("Còn 1 câu chưa làm.")).toBeInTheDocument();
    await ui.click(within(dlg).getByRole("button", { name: "Nộp bài" }));

    // reduced motion: no strikes, the final frame at once, no time-up overlay
    expect(await screen.findByText("Hạ boss!")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Xem kết quả" }));
    expect(await screen.findByText("Hạ Quái Sai Số!")).toBeInTheDocument();
    expect(document.querySelector(".score")).toHaveTextContent("6/10");
    expect(screen.getByText("Gà Toán +40 KN khi nộp bài")).toBeInTheDocument();
    expect(screen.getByText("+50 KN hạ boss")).toBeInTheDocument();
    expect(screen.getByText("Chưa làm: 1 câu")).toBeInTheDocument();

    // the wrong ones: review list
    await ui.click(screen.getByRole("button", { name: "Xem 1 câu sai" }));
    expect(await screen.findByRole("heading", { name: "Câu sai" })).toBeInTheDocument();
    expect(screen.getByText("1 câu cần xem lại")).toBeInTheDocument();
    expect(await screen.findByText(/Lực điện tác dụng lên điện tích q/)).toBeInTheDocument();
  }, 40000);

  it("the boss strikes one by one with motion on, and the damage equals the right answers", async () => {
    reduceMotion(false);
    const ui = userEvent.setup();
    const api = createMockPractice({ learner, mockMinutes: 30 });
    await openPaper(api, ui);
    await ui.click(screen.getByRole("button", { name: "Bắt đầu" }));
    await ui.click(await screen.findByRole("button", { name: /^A\s*14/ }));
    await ui.click(screen.getByRole("button", { name: "Nộp bài" }));
    await ui.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Nộp bài" }));
    const hp = await screen.findByRole("progressbar", { name: "Máu boss" });
    expect(hp).toHaveAttribute("aria-valuemax", "5");
    await waitFor(() => expect(screen.getByText("HP 4/5")).toBeInTheDocument(), { timeout: 5000 });
    expect(await screen.findByText("Boss chạy thoát. Lần sau đánh tiếp.", undefined, { timeout: 6000 })).toBeInTheDocument();
  }, 40000);

  it("an exam already running is offered again in the Arena", async () => {
    const api = createMockPractice({ learner, mockMinutes: 30 });
    setPracticeApi(api);
    await api.start("t", { source: "paper:thpt-toan-2025-mau" });
    const ui = userEvent.setup();
    open("/dau-truong");
    expect(await screen.findByText("Làm tiếp bài đang dở")).toBeInTheDocument();
    expect(screen.getByText(/Bài thi đang chạy, còn (29|30):/)).toBeInTheDocument();
    await ui.click(screen.getByRole("link", { name: "Làm tiếp" }));
    expect(await screen.findByRole("timer")).toBeInTheDocument();
  }, 30000);

  it("a practice paper (bank mock): confirm, timer, flag, hand-in confirm with counts", async () => {
    const ui = userEvent.setup();
    setPracticeApi(createMockPractice({ learner, mockMinutes: 1 }));
    open("/dau-truong");
    const practiceList = await screen.findByRole("list", { name: "Đề luyện" });
    await ui.click(within(practiceList).getByRole("button", { name: "Làm đề" }));
    expect(screen.getByText("Đáp án chỉ hiện sau khi nộp")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Bắt đầu" }));
    expect(await screen.findByRole("timer")).toHaveTextContent(/^(01:00|00:59)$/);
    expect(screen.getByRole("heading", { name: "Đề luyện" })).toBeInTheDocument();
    expect(screen.queryByText("???")).toBeNull(); // no boss on a practice paper
    await ui.click(screen.getByRole("button", { name: /^A\s*14/ }));
    await ui.click(screen.getByRole("button", { name: "Đánh dấu" }));
    expect(screen.getByRole("button", { name: "Bỏ đánh dấu" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Câu 1, Đánh dấu, đã làm/ })).toHaveAttribute("aria-current", "true");
    await ui.click(screen.getByRole("button", { name: "Nộp bài" }));
    expect(screen.getByText("Em đã trả lời 1/5 câu. Nộp xong thì không sửa được nữa.")).toBeInTheDocument();
    expect(screen.getByText("Còn 4 câu chưa làm.")).toBeInTheDocument();
    expect(screen.getByText("Còn 1 câu em đã đánh dấu.")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Làm tiếp" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    await ui.click(screen.getByRole("button", { name: "Nộp bài" }));
    await ui.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Nộp bài" }));
    expect(await screen.findByRole("heading", { name: "Kết quả thi thử" })).toBeInTheDocument();
    expect(document.querySelector(".score")).toHaveTextContent("2/10");
    expect(screen.getByText("Gà Toán +40 KN khi nộp bài")).toBeInTheDocument();
  }, 40000);

  it("the clock runs down on a session opened by link and hands in at zero", async () => {
    const api = createMockPractice({ learner, mockMinutes: 0.04 });
    setPracticeApi(api);
    const s = await api.start("t", { source: "mock:demo" });
    open(`/luyen-tap/${s.id}`);
    expect(await screen.findByRole("timer")).toHaveTextContent(/^00:0[123]$/);
    await waitFor(async () => expect((await api.get("t", s.id)).status).toBe("finished"), { timeout: 8000 });
    expect(await screen.findByText("Hết giờ, bài đã được tự nộp.")).toBeInTheDocument();
  }, 20000);
});

describe("Kiểm tra khóa", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("vi");
    student();
  });
  afterEach(() => sessionStorage.clear());
  const COURSE = "dev-sample-dien-truong";

  it("the course mock exam covers only the course: size, confirm, run and the result by question type", async () => {
    const ui = userEvent.setup();
    setPracticeApi(createMockPractice({ learner, mockMinutes: 30 }));
    open(`/kiem-tra/${COURSE}`);
    expect(await screen.findByRole("heading", { name: "Kiểm tra khóa" })).toBeInTheDocument();
    expect(await screen.findByText("18 câu · 36 phút · chỉ trong khóa này")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Thi thử" }));
    const dlg = screen.getByRole("alertdialog");
    expect(within(dlg).getByText(/Đề có 18 câu, 36 phút, chỉ gồm câu của khóa/)).toBeInTheDocument();
    await ui.click(within(dlg).getByRole("button", { name: "Bắt đầu" }));
    expect(await screen.findByRole("heading", { name: "Thi thử khóa" })).toBeInTheDocument();
    expect(screen.queryByText("???")).toBeNull();
    await ui.click(await screen.findByRole("button", { name: /^A\s*14/ }));
    await ui.click(screen.getByRole("button", { name: "Nộp bài" }));
    await ui.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Nộp bài" }));
    expect(await screen.findByRole("heading", { name: "Kết quả thi thử khóa" })).toBeInTheDocument();
    expect(await screen.findByText("Theo dạng câu")).toBeInTheDocument();
    expect(await screen.findByText("Gà Toán +40 KN khi nộp bài")).toBeInTheDocument();
    // Done goes back to the test page of the course
    await ui.click(screen.getByRole("button", { name: "Về khóa" }));
    expect(await screen.findByRole("heading", { name: "Kiểm tra khóa" })).toBeInTheDocument();
  }, 40000);

  it("the practice levels: suggested one marked, a level opens 'Luyện 10 câu', a later level is locked", async () => {
    const ui = userEvent.setup();
    setPracticeApi(createMockPractice({ learner }));
    open(`/kiem-tra/${COURSE}`);
    const ladder = await screen.findByRole("list", { name: "Luyện theo mức" });
    expect(within(ladder).getByText("Thông hiểu")).toBeInTheDocument();
    expect(within(ladder).getByText(/Mentor gợi ý/)).toBeInTheDocument();
    expect(within(ladder).getByText(/Vững rồi/)).toBeInTheDocument();
    expect(within(ladder).getAllByText("Học thêm vài bài để mở mức này")).toHaveLength(2); // levels 3 and 4
    await ui.click(within(ladder).getByRole("button", { name: /Thông hiểu/ }));
    expect(await screen.findByRole("heading", { name: "Luyện 5 câu" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  }, 30000);

  it("says kindly when there are too few questions for a mock exam", async () => {
    setPracticeApi({ ...createMockPractice({ learner }), courseLevels: async (_t, id) => ({ course_id: id, title: "Nhỏ", min_items: 3, levels: [{ level: 1, items: 3, studied: 3, answered: 0, correct: 0, solid: false }], suggested: 1, mocks: [] }) });
    open(`/kiem-tra/${COURSE}`);
    expect(await screen.findByText(/chưa đủ câu hỏi để thi thử/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thi thử" })).toBeDisabled();
  });
});

describe("the practice runner in the wood board", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("vi");
    student();
  });
  afterEach(() => sessionStorage.clear());

  it("quick session: right answer (+2), red pen on a wrong one, hint, result with takeaway, then Sửa câu sai once each", async () => {
    const api = createMockPractice();
    setPracticeApi(api);
    const s = await api.start("t", { source: "quick" });
    const ui = userEvent.setup();
    open([{ pathname: "/" }, { pathname: `/luyen-tap/${s.id}`, state: { back: "/" } }], 1);
    expect(await screen.findByRole("img", { name: /^Câu 1/ })).toHaveAttribute("aria-current", "true");

    await ui.click(screen.getByRole("button", { name: /^B\s*5/ })); // right (g1_5 bank)
    expect(await screen.findByText("Đúng rồi")).toBeInTheDocument();
    expect(screen.getByText("+2 kinh nghiệm")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Câu tiếp" }));

    expect(await screen.findByRole("img", { name: /^Câu 2/ })).toHaveAttribute("aria-current", "true");
    await ui.click(screen.getByRole("button", { name: "Gợi ý" }));
    expect(await screen.findByText("Đếm chậm từng quả.")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "4" })); // wrong
    expect(await screen.findByText("Chưa đúng")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "3" })).toHaveClass("right");
    expect(screen.getByRole("button", { name: "4" })).toHaveClass("wrong");
    expect(await screen.findByText("Hình A có ba quả.")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Câu tiếp" }));

    for (const n of [1, 2, 3]) await ui.click(await screen.findByRole("button", { name: `Đã chạm: ${n}` }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Đúng rồi")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Câu tiếp" }));

    const rows = (await screen.findAllByRole("group")).filter((g) => g.classList.contains("tf-btns"));
    await ui.click(within(rows[0]).getByRole("button", { name: "Đúng" }));
    await ui.click(within(rows[1]).getByRole("button", { name: "Sai" }));
    await ui.click(within(rows[2]).getByRole("button", { name: "Sai" }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Đúng một phần")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Câu tiếp" }));

    await ui.type(await screen.findByRole("textbox"), "0.5");
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Đúng rồi")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Xem kết quả" }));

    expect(await screen.findByText("Tốt rồi. Chỉ còn lỗi đếm thiếu.")).toBeInTheDocument();
    expect(screen.getByText(/Mentor sẽ cho em làm lại/)).toBeInTheDocument();
    expect(screen.getByText("Gà Toán +6 kinh nghiệm")).toBeInTheDocument(); // 3 right answers x 2
    expect(screen.queryByRole("button", { name: /^Xem .* câu sai/ })).toBeNull(); // practice: fix only

    await ui.click(screen.getByRole("button", { name: "Sửa 2 câu sai" }));
    expect(await screen.findByText("Câu sai 1/2")).toBeInTheDocument();
    expect(screen.getByText("Em đã chọn")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "4" })).toBeDisabled();
    await ui.click(screen.getByRole("button", { name: "3" }));
    expect(await screen.findByText("Đúng rồi!")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Câu sai tiếp" }));

    expect(await screen.findByText("Câu sai 2/2")).toBeInTheDocument();
    const rows2 = (await screen.findAllByRole("group")).filter((g) => g.classList.contains("tf-btns"));
    for (const r of rows2) await ui.click(within(r).getByRole("button", { name: "Đúng" }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText(/3 \+ 1 = 4, không phải 5/)).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Xong phần sửa" }));
    expect(await screen.findByText(/Sửa được 1\/2 câu/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Sửa 2/ })).not.toBeInTheDocument();
    // Done returns to where the run was opened (the village)
    await ui.click(screen.getByRole("button", { name: "Xong" }));
    expect(await screen.findByRole("button", { name: /Bảng tin/ })).toBeInTheDocument();
  }, 60000);

  it("an unfinished practice session is offered again and reopens at the next question", async () => {
    const api = createMockPractice();
    setPracticeApi(api);
    const s = await api.start("t", { source: "quick" });
    await api.answer("t", s.id, { position: 0, answer: "B", time_spent_sec: 3 });
    await api.answer("t", s.id, { position: 1, answer: "A", time_spent_sec: 3 });
    const ui = userEvent.setup();
    open("/dau-truong");
    expect(await screen.findByText("Làm tiếp bài đang dở")).toBeInTheDocument();
    expect(screen.getByText("Em đã làm 2/5 câu.")).toBeInTheDocument();
    await ui.click(screen.getByRole("link", { name: "Làm tiếp" }));
    expect(await screen.findByRole("img", { name: /^Câu 3/ })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
  });

  it("little ones: picture-first, no red marks, a gentle line", async () => {
    student("g1_5");
    const api = createMockPractice();
    setPracticeApi(api);
    const s = await api.start("t", { source: "quick" });
    const ui = userEvent.setup();
    open(`/luyen-tap/${s.id}`);
    await ui.click(await screen.findByRole("button", { name: /^A/ })); // wrong
    expect(await screen.findByText("Gần đúng rồi!")).toBeInTheDocument();
    expect(document.querySelector(".opt.wrong")).toBeNull();
    expect(document.querySelector(".opt.right")).not.toBeNull();
  }, 20000);

  it("a notes review link starts that session; a bare /luyen-tap goes to the village", async () => {
    const api = createMockPractice();
    setPracticeApi(api);
    open("/luyen-tap?notes=n-1");
    expect(await screen.findByRole("img", { name: /^Câu 1/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Luyện 5 câu|Ôn từ vở/ })).toBeInTheDocument();
  });

  it("saving and leaving an exam asks first and returns to where it was opened", async () => {
    const api = createMockPractice({ mockMinutes: 5 });
    setPracticeApi(api);
    const s = await api.start("t", { source: "mock:demo" });
    const ui = userEvent.setup();
    open([{ pathname: "/" }, { pathname: `/luyen-tap/${s.id}`, state: { back: "/" } }], 1);
    await ui.click(await screen.findByRole("button", { name: "Lưu và thoát" }));
    const dlg = screen.getByRole("alertdialog");
    expect(within(dlg).getByText(/Đồng hồ thi thử vẫn chạy/)).toBeInTheDocument();
    await ui.click(within(dlg).getByRole("button", { name: "Lưu và thoát" }));
    expect(await screen.findByRole("button", { name: /Bảng tin/ })).toBeInTheDocument();
  }, 20000);
});
