import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "./i18n";
import { App } from "./App";
import { AuthProvider } from "./state/auth";
import { setPracticeApi, type PItem } from "./api";
import { createMockPractice } from "./api/mock-practice-api";
import { canCheck, clockText, firstSentence, fmtScore10, handInStats, initialRemaining, resumePosition, shown, tfDecode, tfEncode, unfinished } from "./lib/practice";

const item = (p: Partial<PItem> & Pick<PItem, "type">): PItem => ({ position: 0, id: "x", stem: "s", topic: "t", topic_title: "T", ...p });
const tf = item({ type: "TRUE_FALSE_GROUP", statements: [{ id: "a", text: "A" }, { id: "b", text: "B" }, { id: "c", text: "C" }] });

describe("scoring display per type", () => {
  it("encodes true/false groups of 3 and 4 statements", () => {
    expect(tfEncode(tf, { a: true, b: false })).toBe("TF-");
    expect(tfDecode(tf, "TFT")).toEqual({ a: true, b: false, c: true });
    expect(tfDecode(tf, "ĐSĐ")).toEqual({ a: true, b: false, c: true });
    expect(canCheck(tf, "TF-")).toBe(false);
    expect(canCheck(tf, "TFT")).toBe(true);
    expect(canCheck(item({ type: "TAP_COUNT" }), "0")).toBe(false);
    expect(canCheck(item({ type: "TAP_COUNT" }), "7")).toBe(true);
    expect(canCheck(item({ type: "SHORT_ANSWER" }), "  ")).toBe(false);
  });

  it("choice, count and short answer are right or wrong; a blank is a skip", () => {
    for (const type of ["SINGLE_CHOICE", "PICTURE_CHOICE", "TAP_COUNT", "SHORT_ANSWER"] as const) {
      expect(shown({ type }, { correct: true, points: 1, max_points: 1 }).outcome).toBe("right");
      expect(shown({ type }, { correct: false, points: 0, max_points: 1 }).outcome).toBe("wrong");
      expect(shown({ type }, { correct: null }).outcome).toBe("blank");
    }
  });

  it("a true/false group can be partly right, with the statement tally", () => {
    const r = { correct: false, points: 0.25, max_points: 1, statement_results: [{ id: "a", correct: true }, { id: "b", correct: false }, { id: "c", correct: true }] };
    expect(shown(tf, r)).toMatchObject({ outcome: "partial", points: 0.25, tally: { right: 2, total: 3 } });
    expect(shown(tf, { correct: false, points: 0, max_points: 1, statement_results: [{ id: "a", correct: false }] }).outcome).toBe("wrong");
    expect(shown(tf, { correct: true, points: 1, max_points: 1, statement_results: [{ id: "a", correct: true }] }).outcome).toBe("right");
  });

  it("formats scores and keeps the red-pen explanation to one sentence", () => {
    expect(fmtScore10(7.25, "vi")).toBe("7,25");
    expect(fmtScore10(7.25, "en")).toBe("7.25");
    expect(fmtScore10(8, "vi")).toBe("8");
    expect(firstSentence("Em để r theo cm. Đổi 3 cm = 0,03 m trước.")).toBe("Em để r theo cm.");
    expect(firstSentence("E = 9·10⁹ · 4·10⁻⁹ / 0,03² = 4·10⁴ V/m")).toContain("4·10⁴");
    expect(clockText(3725)).toBe("1:02:05");
    expect(clockText(59)).toBe("00:59");
  });
});

describe("mock clock and resume rules", () => {
  it("takes seconds left from the server, else from the deadline", () => {
    const now = Date.parse("2026-11-07T10:00:00Z");
    const base = { id: "m", subject: "s", started_at: "", position: 0, items: [item({ type: "SINGLE_CHOICE" })], answers: {} };
    expect(initialRemaining({ ...base, kind: "mock", deadline: "2026-11-07T10:10:00Z" }, now)).toBe(600);
    expect(initialRemaining({ ...base, kind: "mock", deadline: "2026-11-07T10:10:00Z", remaining_sec: 540 }, now)).toBe(540);
    expect(initialRemaining({ ...base, kind: "mock", deadline: "2026-11-07T09:00:00Z" }, now)).toBe(0);
    expect(initialRemaining({ ...base, kind: "practice" }, now)).toBeNull();
  });

  it("resumes practice at the first item not checked and a mock where the learner left", () => {
    const items = [0, 1, 2].map((position) => item({ type: "SINGLE_CHOICE", position }));
    const p = { id: "p", kind: "practice" as const, subject: "quick", started_at: "", position: 0, items, answers: { "0": { checked: true }, "1": { checked: true } } };
    expect(resumePosition(p)).toBe(2);
    expect(resumePosition({ ...p, kind: "mock", position: 1 })).toBe(1);
    expect(unfinished({ ...p, status: "finished" })).toBe(false);
    expect(unfinished(p)).toBe(true);
  });

  it("counts empty and flagged items before hand-in", () => {
    const items = [0, 1, 2].map((position) => item({ type: "SINGLE_CHOICE", position }));
    const s = { id: "m", kind: "mock" as const, subject: "s", started_at: "", position: 0, items, answers: {} };
    expect(handInStats(s, { 0: "A", 1: "" }, { 1: true })).toEqual({ total: 3, blank: 2, flagged: 1, answered: 1 });
  });
});

function student(age = "g10_12") {
  localStorage.setItem(
    "mentor.mock.users",
    JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: age, birth_year: ({ g1_5: 2018, g6_9: 2013, g10_12: 2010, uni: 2007 } as Record<string, number>)[age], language: "vi", theme: "system", quiet_until: null } } }),
  );
  localStorage.setItem("mentor.token", "mock-u-hs");
}
const open = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );

describe("practice screens", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("vi");
    student();
  });
  afterEach(() => {
    sessionStorage.clear();
  });

  it("quick session: right answer, red-pen on a wrong one, hint, result with takeaway and redo line", async () => {
    setPracticeApi(createMockPractice());
    const ui = userEvent.setup();
    open("/luyen-tap");
    expect(await screen.findByText("5 câu, khoảng 6 phút")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Bắt đầu" }));
    expect(await screen.findByText("1/5")).toBeInTheDocument();

    await ui.click(screen.getByRole("button", { name: /^B\s*5/ })); // right
    expect(await screen.findByText("Đúng rồi")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Câu tiếp" }));

    expect(await screen.findByText("2/5")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Gợi ý" }));
    expect(await screen.findByText("Đếm chậm từng quả.")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "4" })); // PICTURE_CHOICE B (text fallback): wrong
    expect(await screen.findByText("Chưa đúng")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "3" })).toHaveClass("right");
    expect(screen.getByRole("button", { name: "4" })).toHaveClass("wrong");
    expect(await screen.findByText("Hình A có ba quả.")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Câu tiếp" }));

    // tap count: tap 3 apples, check
    for (const n of [1, 2, 3]) await ui.click(await screen.findByRole("button", { name: `Đã chạm: ${n}` }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Đúng rồi")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Câu tiếp" }));

    // true/false group of 3: a, b, c = T F F -> partly right (2/3)
    const rows = (await screen.findAllByRole("group")).filter((g) => g.classList.contains("tf-btns"));
    await ui.click(within(rows[0]).getByRole("button", { name: "Đúng" }));
    await ui.click(within(rows[1]).getByRole("button", { name: "Sai" }));
    await ui.click(within(rows[2]).getByRole("button", { name: "Sai" }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Đúng một phần")).toBeInTheDocument();
    expect(screen.getByText("Đúng 2/3 ý.")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Câu tiếp" }));

    // short answer: 0.5 equals 0,5
    await ui.type(await screen.findByRole("textbox"), "0.5");
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Đúng rồi")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Xem kết quả" }));

    expect(await screen.findByText("Tốt rồi. Chỉ còn lỗi đếm thiếu.")).toBeInTheDocument();
    expect(screen.getByText(/Mentor sẽ cho em làm lại/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Xong" })).toBeInTheDocument();
    await ui.click(screen.getByRole("link", { name: "Xem lại bài" }));
    expect(await screen.findAllByText(/^Câu \d/)).toHaveLength(5);
  }, 30000);

  it("an unfinished session is offered again and reopens at the next question", async () => {
    const api = createMockPractice();
    setPracticeApi(api);
    const s = await api.start("t", { source: "quick" });
    await api.answer("t", s.id, { position: 0, answer: "B", time_spent_sec: 3 });
    await api.answer("t", s.id, { position: 1, answer: "A", time_spent_sec: 3 });
    const ui = userEvent.setup();
    open("/luyen-tap");
    expect(await screen.findByText("Làm tiếp bài đang dở")).toBeInTheDocument();
    expect(screen.getByText("Em đã làm 2/5 câu.")).toBeInTheDocument();
    await ui.click(screen.getByRole("link", { name: "Làm tiếp" }));
    expect(await screen.findByText("3/5")).toBeInTheDocument();
    // feedback of an answered item survives (go back is not offered in practice; the progress bar counts 2 done)
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
  });

  it("says so kindly when there is not enough to practise, pointing to Courses", async () => {
    setPracticeApi(createMockPractice({ enough: false }));
    open("/luyen-tap");
    expect(await screen.findByText(/Em chưa học đủ để luyện/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mở Khóa học" })).toHaveAttribute("href", "/khoa-hoc");
    expect(screen.queryByRole("button", { name: "Bắt đầu" })).toBeNull();
  });

  it("mock: confirm, timer from the server deadline, flag, answers hidden, confirm before hand-in", async () => {
    setPracticeApi(createMockPractice({ mockMinutes: 1 }));
    const ui = userEvent.setup();
    open("/luyen-tap");
    await ui.click(await screen.findByRole("button", { name: "Thi thử" }));
    expect(screen.getByText(/Đồng hồ chạy ngay/)).toBeInTheDocument();
    await ui.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Thi thử" }));

    expect(await screen.findByRole("timer")).toHaveTextContent(/^(01:00|00:59)$/);
    await ui.click(screen.getByRole("button", { name: /^B/ }));
    expect(screen.queryByText("Đúng rồi")).toBeNull(); // hidden until finish
    expect(screen.getByRole("button", { name: /^B/ })).toHaveAttribute("aria-pressed", "true");
    await ui.click(screen.getByRole("button", { name: "Đánh dấu" }));
    expect(screen.getByRole("button", { name: "Bỏ đánh dấu" })).toBeInTheDocument();

    // free navigation, the grid shows flag and answered
    await ui.click(screen.getByRole("button", { name: "Tất cả câu" }));
    expect(screen.getByRole("button", { name: /Câu 1, Đánh dấu, đã làm/ })).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Nộp bài" }));
    expect(screen.getByText("Em đã trả lời 1/5 câu. Nộp xong thì không sửa được nữa.")).toBeInTheDocument();
    expect(screen.getByText("Còn 4 câu chưa làm.")).toBeInTheDocument();
    expect(screen.getByText("Còn 1 câu em đã đánh dấu.")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Làm tiếp" })); // back
    expect(screen.queryByRole("dialog")).toBeNull();
    await ui.click(screen.getByRole("button", { name: "Tất cả câu" }));
    await ui.click(screen.getByRole("button", { name: "Nộp bài" }));
    await ui.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Nộp bài" }));
    expect(await screen.findByText("Đúng 1/5 câu, đã làm 1 câu.")).toBeInTheDocument();
    expect(document.querySelector(".score")).toHaveTextContent("2/10");
  }, 30000);

  it("mock: the clock runs down and hands the exam in at zero", async () => {
    const api = createMockPractice({ mockMinutes: 0.04 }); // 2.4 s on the server clock
    setPracticeApi(api);
    const s = await api.start("t", { source: "mock:demo" });
    open(`/luyen-tap/${s.id}`);
    expect(await screen.findByRole("timer")).toHaveTextContent(/^00:0[123]$/);
    await waitFor(() => expect(screen.getByRole("link", { name: "Xong" })).toBeInTheDocument(), { timeout: 8000 });
    expect((await api.get("t", s.id)).status).toBe("finished");
  }, 20000);

  it("little ones get a picture-first start and no red marks", async () => {
    student("g1_5");
    setPracticeApi(createMockPractice());
    const ui = userEvent.setup();
    open("/luyen-tap");
    expect(await screen.findByText("5 câu thôi nhé!")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Bắt đầu nào" }));
    await ui.click(await screen.findByRole("button", { name: /^A/ })); // wrong
    expect(await screen.findByText("Gần đúng rồi!")).toBeInTheDocument();
    expect(document.querySelector(".opt.wrong")).toBeNull();
    expect(document.querySelector(".opt.right")).not.toBeNull();
  }, 20000);
});

describe("mock practice banks", () => {
  it("gives every age band its own items, in the learner's language", async () => {
    const stem = async (age_band: string, language: string) => (await createMockPractice({ learner: () => ({ age_band, language }) }).start("t", { source: "quick" })).items[0].stem;
    expect(await stem("g1_5", "vi")).toBe("Bao nhiêu quả táo trong 2 + 3?");
    expect(await stem("g6_9", "en")).toBe("Which fraction is the largest?");
    expect(await stem("g10_12", "vi")).toContain("Cấp số cộng");
    expect(await stem("uni", "vi")).toContain("Cấp số cộng");
  });
});
