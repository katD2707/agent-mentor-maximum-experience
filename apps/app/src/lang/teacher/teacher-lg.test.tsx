import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "../../i18n";
import { App } from "../../App";
import { AuthProvider } from "../../state/auth";
import { mockTeacherApi, resetMockTeacher } from "../../api/mock-teacher-api";
import type { HubCourse, HubState, TeacherCourseSummary } from "../../api/teacher";
import { hubRowView } from "../../lib/teacher/hubStatus";
import { canPublish, gradeWarning, guessLabels, labelsBody, labelsComplete, missingFields, type Labels } from "./labels";

const L = (o: Partial<Labels>): Labels => ({ bac: null, chicken: null, grade: null, difficulty: null, ...o });

describe("labels (pure)", () => {
  it("Mentor guesses from the title: 'Vật lí 11' is Lí, grade 11, school", () => {
    expect(guessLabels({ title: "Vật lí 11: Điện trường", level_suggested: "basic" }, null)).toEqual({ bac: "pt", chicken: "li", grade: 11, difficulty: "basic" });
    expect(guessLabels({ title: "Toán 1: Các số đến 10" }, null)).toMatchObject({ bac: "pt", chicken: "toan", grade: 1 });
  });
  it("the gateway's read of the files wins over the title; saved labels win over both", () => {
    const g = guessLabels({ title: "Hệ điều hành", age_band: "uni" }, null);
    expect(g).toMatchObject({ bac: "dh", chicken: "ktmt", grade: null });
    const saved = guessLabels({ title: "Hệ điều hành", age_band: "uni", versions: [{ version: 1, status: "draft", students: 0, labels: { chicken: "khmt", band: "uni", grade: 2 }, level_confirmed: "advanced" }] }, 1);
    expect(saved).toEqual({ bac: "dh", chicken: "khmt", grade: 2, difficulty: "advanced" });
  });
  it("the gateway's saved chicken/band/grade and a published difficulty come back", () => {
    const base = { title: "Vật lí 11: Điện trường", subject: "physics", age_band: "g10_12", level: "advanced" as const, saved: { chicken: "hoa", band: "g10_12", grade: 11 } };
    const pub = [{ version: 1, status: "published" as const, students: 1 }];
    expect(guessLabels({ ...base, versions: pub }, 1)).toEqual({ bac: "pt", chicken: "hoa", grade: 11, difficulty: "advanced" });
    // saved labels belong to the working version only: an older published version is not overridden by a newer draft's labels
    const both = [...pub, { version: 2, status: "draft" as const, students: 0 }];
    expect(guessLabels({ ...base, versions: both }, 1).chicken).toBe("li");
    expect(guessLabels({ ...base, versions: both }, 2).chicken).toBe("hoa");
  });
  it("what it cannot decide stays empty and blocks Continue", () => {
    const g = guessLabels({ title: "Xác suất thống kê: Suy luận Bayes" }, null);
    expect(g.chicken).toBeNull();
    expect(missingFields(g)).toContain("chicken");
    expect(labelsComplete(g)).toBe(false);
  });
  it("the body of PUT labels: band follows the grade, university is uni", () => {
    expect(labelsBody(L({ bac: "pt", chicken: "li", grade: 11, difficulty: "basic" }))).toEqual({ chicken: "li", band: "g10_12", level: 11, difficulty: "basic" });
    expect(labelsBody(L({ bac: "pt", chicken: "toan", grade: 3, difficulty: "advanced" }))?.band).toBe("g1_5");
    expect(labelsBody(L({ bac: "pt", chicken: "toan", grade: 7, difficulty: "advanced" }))?.band).toBe("g6_9");
    expect(labelsBody(L({ bac: "dh", chicken: "ktmt", grade: 2, difficulty: "intermediate" }))?.band).toBe("uni");
    expect(labelsBody(L({ bac: "pt", chicken: "li", grade: 11 }))).toBeNull();
  });
  it("Lí/Hóa/Sinh below grade 10 and Khoa học from grade 10 get a warning", () => {
    expect(gradeWarning(L({ bac: "pt", chicken: "li", grade: 8 }))).toBe("low");
    expect(gradeWarning(L({ bac: "pt", chicken: "khoahoc", grade: 11 }))).toBe("high");
    expect(gradeWarning(L({ bac: "pt", chicken: "li", grade: 11 }))).toBeNull();
    expect(gradeWarning(L({ bac: "dh", chicken: "vatli", grade: 1 }))).toBeNull();
  });
  it("publishing needs a confirmed difficulty (a published version always counts)", () => {
    const c = { level: null, level_confirmed: null, versions: [{ version: 1, status: "draft", students: 0, level_suggested: "basic" as const, level_confirmed: null }] };
    expect(canPublish(c, 1)).toBe(false);
    expect(canPublish({ ...c, versions: [{ ...c.versions[0], level_confirmed: "basic" as const }] }, 1)).toBe(true);
    expect(canPublish({ level: "advanced", level_confirmed: null, versions: [{ version: 1, status: "published", students: 3 }] }, 1)).toBe(true);
  });
});

function teacherApp(path: string, language: "vi" | "en" = "vi") {
  localStorage.setItem("mentor.token", "mock-u-gv");
  localStorage.setItem("mentor.mock.users", JSON.stringify({ giaovien: { password: "123456", user: { id: "u-gv", role: "teacher", username: "giaovien", display_name: "Thầy Minh", age_band: null, language, theme: "system", quiet_until: null } } }));
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("labels and publish gating (mock)", () => {
  beforeEach(async () => {
    resetMockTeacher();
    localStorage.removeItem("mentor.mock.teacher");
    await i18n.changeLanguage("vi");
  });
  afterEach(() => {
    resetMockTeacher();
    vi.restoreAllMocks();
  });

  it("the Nhãn step is step 3 with Mentor's guess filled in; Lưu is the one action", async () => {
    teacherApp("/khoa/toan-1-dem-tao/nhan?v=1");
    expect(await screen.findByRole("heading", { name: "Toán 1: Các số đến 10" })).toBeInTheDocument();
    await screen.findByRole("button", { name: "Lưu" });
    const steps = screen.getByRole("navigation", { name: "Các bước" });
    expect(within(steps).getAllByRole("link").map((a) => a.getAttribute("aria-label"))).toEqual(["Gửi", "Cấu trúc", "Nhãn", "Duyệt"]);
    expect(within(steps).getByRole("link", { name: "Nhãn" })).toHaveAttribute("aria-current", "step");
    expect(screen.getByRole("radio", { name: "Toán" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "1" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: /Cơ bản/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getAllByText("Mentor điền").length).toBe(4);
    expect(screen.getByText("Gà Toán")).toBeInTheDocument(); // the preview: where students will find it
    expect(screen.getByRole("button", { name: "Lưu" })).not.toHaveAttribute("aria-disabled");
  }, 20000);

  it("a label Mentor is unsure about must be picked: Continue stays dimmed and points at it", async () => {
    teacherApp("/khoa/xac-suat-bayes/nhan?v=1");
    await screen.findByRole("heading", { name: "Xác suất thống kê: Suy luận Bayes" });
    await screen.findByRole("button", { name: "Lưu" });
    expect(screen.getByText(/Mentor chưa chắc/)).toBeInTheDocument();
    const go = screen.getByRole("button", { name: "Lưu" });
    expect(go).toHaveAttribute("aria-disabled", "true");
    const put = vi.spyOn(mockTeacherApi, "publish");
    await userEvent.click(go);
    expect(await screen.findByText("Chọn đủ bậc học, gà, lớp và độ khó để lưu.")).toBeInTheDocument();
    expect(screen.getAllByText("Cần chọn", { selector: ".tag" })).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Xuất bản" })).toBeNull(); // still on the labels step
    expect(put).not.toHaveBeenCalled();
  }, 20000);

  it("Continue saves the labels, which confirms the difficulty, and opens the review", async () => {
    teacherApp("/khoa/toan-1-dem-tao/nhan?v=1");
    await screen.findByRole("heading", { name: "Toán 1: Các số đến 10" });
    await screen.findByRole("button", { name: "Lưu" });
    await userEvent.click(screen.getByRole("radio", { name: /Nâng cao/ }));
    await userEvent.click(screen.getByRole("radio", { name: "3" }));
    await userEvent.click(screen.getByRole("radio", { name: "Văn" }));
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(await screen.findByText("Đã lưu nhãn.")).toBeInTheDocument(); // saved, and still on the labels step
    expect(screen.queryByRole("button", { name: "Xuất bản" })).toBeNull();
    const c = (await mockTeacherApi.getCourse("t", "toan-1-dem-tao")).course;
    expect(c.versions[0].level_confirmed).toBe("intermediate");
    expect(c.versions[0].labels).toEqual({ chicken: "van", band: "g1_5", grade: 3, goals: [], language: "vi", topics: [] });
    expect(c.labels).toMatchObject({ chicken: "van", band: "g1_5", grade: 3 }); // reopening shows what was saved
  }, 20000);

  it("goals (one a line), language and topic chips are sent with the labels and come back prefilled", async () => {
    teacherApp("/khoa/toan-1-dem-tao/nhan?v=1");
    await screen.findByRole("heading", { name: "Toán 1: Các số đến 10" });
    await screen.findByRole("button", { name: "Lưu" });
    await userEvent.click(screen.getByRole("radio", { name: /Nâng cao/ }));
    await userEvent.click(screen.getByRole("radio", { name: "3" }));
    await userEvent.click(screen.getByRole("radio", { name: "Văn" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Mục tiêu" }), "Đếm đến 10{Enter}{Enter}  Cộng trong phạm vi 10  ");
    await userEvent.click(screen.getByRole("radio", { name: "Tiếng Anh" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Chủ đề" }), "đếm số{Enter}phép cộng{Enter}đếm số{Enter}");
    expect(screen.getAllByText(/^(đếm số|phép cộng)$/)).toHaveLength(2); // no duplicate chip
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(await screen.findByText("Đã lưu nhãn.")).toBeInTheDocument();
    const c = (await mockTeacherApi.getCourse("t", "toan-1-dem-tao")).course;
    expect(c.versions[0].labels).toMatchObject({ goals: ["Đếm đến 10", "Cộng trong phạm vi 10"], language: "en", topics: ["đếm số", "phép cộng"] });
    expect(c.labels).toMatchObject({ goals: ["Đếm đến 10", "Cộng trong phạm vi 10"], language: "en", topics: ["đếm số", "phép cộng"] });
  }, 30000);

  it("switching to Đại học offers the ngành chickens and years, and starts the pick over", async () => {
    teacherApp("/khoa/toan-1-dem-tao/nhan?v=1");
    await screen.findByRole("heading", { name: "Toán 1: Các số đến 10" });
    await screen.findByRole("button", { name: "Lưu" });
    await userEvent.click(screen.getByRole("radio", { name: "Đại học" }));
    expect(screen.getByRole("radio", { name: "Kỹ thuật máy tính" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("radio", { name: "Năm 2" })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Toán" })).toBeNull();
    expect(screen.getByRole("button", { name: "Lưu" })).toHaveAttribute("aria-disabled", "true");
  }, 20000);

  it("review shows each step the way the student player draws it (the chicken says the text)", async () => {
    teacherApp("/khoa/toan-1-dem-tao/duyet?v=1");
    await screen.findByRole("button", { name: "Xuất bản" });
    await waitFor(() => expect(document.querySelector(".pv .lp .lp-in")).not.toBeNull());
    expect(document.querySelector(".pv .lp-gsp img, .pv .lp-twinbox, .pv .ls-media")).not.toBeNull();
  }, 20000);

  it("review: publish is dimmed until the labels are confirmed; tapping it says so and links to Nhãn", async () => {
    teacherApp("/khoa/toan-1-dem-tao/duyet?v=1");
    const pub = await screen.findByRole("button", { name: "Xuất bản" });
    expect(pub).toHaveAttribute("aria-disabled", "true");
    const pubApi = vi.spyOn(mockTeacherApi, "publish");
    await userEvent.click(pub);
    expect(await screen.findByText("Xác nhận nhãn ở bước 3 để xuất bản.")).toBeInTheDocument();
    expect(document.getElementById("levelrow")).toHaveClass("need");
    expect(pubApi).not.toHaveBeenCalled();
    expect(screen.queryByRole("link", { name: "Sửa ở bước Nhãn" })).toBeNull(); // step 3 in the header is the one way back to the labels
    expect(screen.getByRole("link", { name: "Nhãn" })).toHaveAttribute("href", "/khoa/toan-1-dem-tao/nhan?v=1");
  }, 20000);

  it("after the labels are confirmed, publish goes through", async () => {
    await mockTeacherApi.listCourses("t");
    teacherApp("/khoa/toan-1-dem-tao/nhan?v=1");
    await screen.findByRole("heading", { name: "Toán 1: Các số đến 10" });
    await screen.findByRole("button", { name: "Lưu" });
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await screen.findByText("Đã lưu nhãn.");
    await userEvent.click(screen.getByRole("link", { name: "Duyệt" }));
    const pub = await screen.findByRole("button", { name: "Xuất bản" });
    await waitFor(() => expect(pub).not.toHaveAttribute("aria-disabled"));
    await userEvent.click(pub);
    expect(await screen.findByText("Đã xuất bản.")).toBeInTheDocument();
  }, 20000);

  it("a published course takes new labels at once, without a new version", async () => {
    teacherApp("/khoa/xac-suat-bayes/nhan?v=1");
    await screen.findByRole("heading", { name: "Xác suất thống kê: Suy luận Bayes" });
    await screen.findByRole("button", { name: "Lưu" });
    expect(screen.getByText("Đã xuất bản: nhãn mới có hiệu lực ngay, không thành bản mới.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "Toán" }));
    await userEvent.click(screen.getByRole("radio", { name: "12" }));
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await screen.findByText("Đã lưu nhãn.");
    const c = (await mockTeacherApi.getCourse("t", "xac-suat-bayes")).course;
    expect(c.versions.map((v) => v.version)).toEqual([1]);
    expect(c.versions[0].labels).toMatchObject({ chicken: "toan", grade: 12 });
  }, 20000);

  it("english strings", async () => {
    teacherApp("/khoa/toan-1-dem-tao/nhan?v=1", "en");
    expect(await screen.findByText("Main chicken (subject)")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Exam prep" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tags" })).toHaveAttribute("aria-current", "step");
  }, 20000);
});

describe("hub on: the course list by hub.state, Gửi duyệt (mock)", () => {
  beforeEach(async () => {
    resetMockTeacher();
    localStorage.removeItem("mentor.mock.teacher");
    localStorage.setItem("mentor.mock.hub", "1");
    await i18n.changeLanguage("vi");
  });
  afterEach(() => {
    resetMockTeacher();
    localStorage.removeItem("mentor.mock.hub");
    vi.restoreAllMocks();
  });
  const row = (title: string) => screen.getByRole("heading", { name: title }).closest("li") as HTMLElement;

  it("each course shows the chip of its state with the actions that fit it", async () => {
    teacherApp("/");
    await screen.findByRole("heading", { name: "Ngữ văn 9: Truyện Kiều" });
    const draft = within(row("Toán 1: Các số đến 10"));
    expect(draft.getByText("Bản nháp")).toBeInTheDocument();
    expect(draft.getByRole("link", { name: /Tiếp tục/ })).toBeInTheDocument();
    const wait = within(row("Ngữ văn 9: Truyện Kiều"));
    expect(wait.getByText("Chờ duyệt")).toBeInTheDocument();
    expect(wait.getByRole("button", { name: /Rút lại/ })).toBeInTheDocument();
    const no = within(row("Hóa 8: Phản ứng hóa học"));
    expect(no.getByText("Bị từ chối")).toBeInTheDocument();
    expect(no.getByText("Bài 3 thiếu đáp án.")).toBeInTheDocument();
    expect(no.getByRole("link", { name: /Sửa/ })).toBeInTheDocument();
    const live = within(row("Xác suất thống kê: Suy luận Bayes"));
    expect(live.getByText("Đã đăng")).toBeInTheDocument();
    expect(live.getByRole("link", { name: /Sửa/ })).toBeInTheDocument();
    expect(live.getByRole("button", { name: /Gỡ/ })).toBeInTheDocument();
  }, 20000);

  it("Rút lại sends the course back to a draft; Gỡ asks first, then unpublishes", async () => {
    const ui = userEvent.setup();
    teacherApp("/");
    await screen.findByRole("heading", { name: "Ngữ văn 9: Truyện Kiều" });
    await ui.click(within(row("Ngữ văn 9: Truyện Kiều")).getByRole("button", { name: /Rút lại/ }));
    expect(await screen.findByText("Đã rút lại. Bản nháp còn nguyên.")).toBeInTheDocument();
    await waitFor(() => expect(within(row("Ngữ văn 9: Truyện Kiều")).getByText("Bản nháp")).toBeInTheDocument());

    await ui.click(within(row("Xác suất thống kê: Suy luận Bayes")).getByRole("button", { name: /Gỡ/ }));
    const dlg = await screen.findByRole("alertdialog");
    expect(dlg).toHaveTextContent("Học sinh đã tải về vẫn học tiếp được.");
    await ui.click(within(dlg).getByRole("button", { name: "Giữ lại" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(within(row("Xác suất thống kê: Suy luận Bayes")).getByText("Đã đăng")).toBeInTheDocument(); // kept
    await ui.click(within(row("Xác suất thống kê: Suy luận Bayes")).getByRole("button", { name: /Gỡ/ }));
    await ui.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Gỡ" }));
    await waitFor(() => expect(within(row("Xác suất thống kê: Suy luận Bayes")).getByText("Bản nháp")).toBeInTheDocument());
  }, 30000);

  it("the final button is Gửi duyệt: it submits, never publishes, and then waits", async () => {
    await mockTeacherApi.setLevel("t", "toan-1-dem-tao", 1, "basic");
    const submit = vi.spyOn(mockTeacherApi, "submit");
    const publish = vi.spyOn(mockTeacherApi, "publish");
    teacherApp("/khoa/toan-1-dem-tao/duyet?v=1");
    const go = await screen.findByRole("button", { name: "Gửi duyệt" });
    expect(screen.queryByRole("button", { name: "Xuất bản" })).toBeNull();
    await waitFor(() => expect(go).not.toHaveAttribute("aria-disabled"));
    await userEvent.click(go);
    expect(await screen.findByText(/Đã gửi duyệt\./)).toBeInTheDocument();
    expect(submit).toHaveBeenCalledWith(expect.anything(), "toan-1-dem-tao", 1);
    expect(publish).not.toHaveBeenCalled();
    const waiting = await screen.findByRole("button", { name: "Đã gửi, đang chờ duyệt" });
    expect(waiting).toBeDisabled();
  }, 30000);
});

describe("hubRowView (pure)", () => {
  const c = (over: Partial<TeacherCourseSummary>): TeacherCourseSummary => ({ id: "x", title: "X", status: "review", status_line_vi: "", status_line_en: "", updated_at: "", latest_version: 1, versions: [], ...over });
  const hub = (state: HubState, over: Partial<HubCourse> = {}): HubCourse => ({ course_id: "x", title: "X", version: 1, kind: "new", state, live_version: null, reason: null, updated_at: "", ...over });
  it("follows hub.state", () => {
    expect(hubRowView(c({ hub: null })).actions).toEqual(["continue"]);
    expect(hubRowView(c({ hub: hub("cho_duyet") }))).toMatchObject({ actions: ["withdraw"], oldVersion: false });
    expect(hubRowView(c({ hub: hub("cho_duyet", { live_version: 1, version: 2 }) }))).toMatchObject({ actions: ["withdraw", "remove"], oldVersion: true });
    expect(hubRowView(c({ hub: hub("tu_choi", { reason: "Thiếu đáp án" }) }))).toMatchObject({ actions: ["edit"], why: "Thiếu đáp án" });
    expect(hubRowView(c({ hub: hub("da_dang", { live_version: 1 }) })).actions).toEqual(["edit", "remove"]);
    expect(hubRowView(c({ hub: hub("rut_lai") })).chips[0].key).toBe("lg.hub.course.draft");
    expect(hubRowView(c({ hub: hub("da_go") })).chips[0].key).toBe("lg.hub.course.draft");
  });
  it("a course still being read has no actions and keeps its processing chip", () => {
    const v = hubRowView(c({ status: "reading", hub: null }));
    expect(v.actions).toEqual([]);
    expect(v.chips[0].key).toBe("gv.status.reading");
  });
});
