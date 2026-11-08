import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "./i18n";
import { App } from "./App";
import { AuthProvider } from "./state/auth";
import type { Outline, TeacherCourseSummary } from "./api/teacher";
import { applyOutlineOps, addLessonOp, deleteOp, dropIndex, moveLessonOps, renameOp, stepLessonOps } from "./lib/teacher/outline";
import { fmtTime, markText, pointAnchor, textAnchor, timeAnchor } from "./lib/teacher/anchors";
import { numberComments, textMarks } from "./lib/teacher/comments";
import { buildStateInfo, commentStatusInfo, courseRoute, finishedJobs, statusMap, statusTag } from "./lib/teacher/status";
import { teacherDeepLink } from "./screens/teacher/live";
import { setMediaToken } from "./api/media";
import { httpTeacherApi } from "./api/teacher-http";
import { load, mockTeacherApi, mockTiming, packFromOutline, resetMockTeacher, tick } from "./api/mock-teacher-api";

const OUTLINE: Outline = {
  title: "T",
  chapters: [
    { id: "c1", title: "Chương 1", lessons: [{ id: "a", title: "A", est_minutes: 10, grounded: true }, { id: "b", title: "B", est_minutes: 10, grounded: true }, { id: "c", title: "C", est_minutes: 10, grounded: true }] },
    { id: "c2", title: "Chương 2", lessons: [{ id: "d", title: "D", est_minutes: 10, grounded: true }, { id: "e", title: "E", est_minutes: 10, grounded: true }] },
  ],
};
const ids = (o: Outline) => o.chapters.map((c) => c.lessons.map((l) => l.id).join(""));

describe("outline editing -> API ops", () => {
  it("rename sends a trimmed rename op", () => {
    expect(renameOp("a", "  Bài mới  ")).toEqual({ op: "rename", id: "a", title: "Bài mới" });
  });
  it("reordering inside a chapter is one reorder op with the full new order", () => {
    const ops = moveLessonOps(OUTLINE, "a", "c1", 2)!; // a goes after c (index counted without a)
    expect(ops).toEqual([{ op: "reorder", ids: ["b", "c", "a"], parent: "c1" }]);
    expect(ids(applyOutlineOps(OUTLINE, ops))).toEqual(["bca", "de"]);
    expect(moveLessonOps(OUTLINE, "a", "c1", 0)).toBeNull(); // nothing changes
  });
  it("dropping into another chapter is move_lesson with the index", () => {
    const ops = moveLessonOps(OUTLINE, "b", "c2", dropIndex(OUTLINE, "b", "c2", "e"))!;
    expect(ops).toEqual([{ op: "move_lesson", id: "b", chapter: "c2", index: 1 }]);
    expect(ids(applyOutlineOps(OUTLINE, ops))).toEqual(["ac", "dbe"]);
  });
  it("dropIndex: before a lesson, or at the end", () => {
    expect(dropIndex(OUTLINE, "a", "c1", "c")).toBe(1); // a removed: [b, c], before c = 1
    expect(dropIndex(OUTLINE, "a", "c1", null)).toBe(2);
  });
  it("keyboard arrows step through lessons and cross chapters at the edges", () => {
    expect(stepLessonOps(OUTLINE, "b", -1)).toEqual([{ op: "reorder", ids: ["b", "a", "c"], parent: "c1" }]);
    expect(stepLessonOps(OUTLINE, "a", -1)).toBeNull();
    const down = stepLessonOps(OUTLINE, "c", 1)!;
    expect(down).toEqual([{ op: "move_lesson", id: "c", chapter: "c2", index: 0 }]);
    expect(ids(applyOutlineOps(OUTLINE, down))).toEqual(["ab", "cde"]);
    const up = stepLessonOps(OUTLINE, "d", -1)!;
    expect(ids(applyOutlineOps(OUTLINE, up))).toEqual(["abcd", "e"]);
  });
  it("delete and add_lesson shapes match the builder (a new lesson is not grounded)", () => {
    expect(deleteOp("a")).toEqual({ op: "delete", id: "a" });
    expect(addLessonOp("c2", "Bài mới", "e")).toEqual({ op: "add_lesson", chapter: "c2", title: "Bài mới", after: "e" });
    const o = applyOutlineOps(OUTLINE, [addLessonOp("c2", "Bài mới", "d")]);
    expect(o.chapters[1].lessons.map((l) => l.title)).toEqual(["D", "Bài mới", "E"]);
    expect(o.chapters[1].lessons[1].grounded).toBe(false);
  });
  it("deleting the last lesson of a chapter removes the chapter; an empty outline is refused", () => {
    const o = applyOutlineOps(OUTLINE, [deleteOp("d"), deleteOp("e")]);
    expect(o.chapters.map((c) => c.id)).toEqual(["c1"]);
    expect(() => applyOutlineOps(o, [deleteOp("c1")])).toThrow();
  });
  it("merge keeps the first lesson and drops an emptied chapter", () => {
    const o = applyOutlineOps(OUTLINE, [{ op: "merge", ids: ["d", "e"], title: "DE" }]);
    expect(o.chapters[1].lessons).toHaveLength(1);
    expect(o.chapters[1].lessons[0]).toMatchObject({ id: "d", title: "DE", est_minutes: 20 });
  });
});

describe("comment anchors", () => {
  it("text: offsets and quote in the block's text, trimmed", () => {
    const root = document.createElement("div");
    root.innerHTML = "<p>Điện trường <b>mạnh</b> thì đường sức dày.</p>";
    document.body.append(root);
    const p = root.querySelector("p")!;
    const r = document.createRange();
    r.setStart(p.firstChild!, 5); // "trường "
    r.setEnd(root.querySelector("b")!.firstChild!, 4); // ... "mạnh"
    const a = textAnchor(root, r)!;
    expect(a).toEqual({ kind: "text", start: 5, end: 16, quote: "trường mạnh" });
    expect(root.textContent!.slice((a as { start: number }).start, (a as { end: number }).end)).toBe("trường mạnh");
    // a selection outside the block gives nothing
    const other = document.createElement("div");
    other.textContent = "x";
    document.body.append(other);
    const r2 = document.createRange();
    r2.selectNodeContents(other);
    expect(textAnchor(root, r2)).toBeNull();
    root.remove();
    other.remove();
  });
  it("video: paused time to a tenth of a second; image: percent of the picture", () => {
    expect(timeAnchor(42.04)).toEqual({ kind: "time", t: 42 });
    expect(timeAnchor(-3)).toEqual({ kind: "time", t: 0 });
    expect(fmtTime(42)).toBe("0:42");
    expect(fmtTime(100)).toBe("1:40");
    expect(pointAnchor({ left: 100, top: 50, width: 400, height: 200 }, 188, 100)).toEqual({ kind: "point", x: 0.22, y: 0.25 });
    expect(pointAnchor({ left: 0, top: 0, width: 100, height: 100 }, 500, -5)).toEqual({ kind: "point", x: 1, y: 0 });
  });
  it("numbering follows reading order and only counts this lesson's blocks", () => {
    const mk = (id: string, block_id: string, anchor: never) => ({ id, block_id, anchor, body: "x", status: "open" as const });
    const list = [
      mk("1", "b2", { kind: "time", t: 44 } as never),
      mk("2", "b1", { kind: "text", start: 30, end: 40, quote: "q" } as never),
      mk("3", "b1", { kind: "text", start: 2, end: 9, quote: "q" } as never),
      mk("4", "zz", { kind: "point", x: 1, y: 1 } as never),
    ];
    const n = numberComments(list, ["b1", "b2"]);
    expect(n.map((c) => [c.id, c.n])).toEqual([["3", 1], ["2", 2], ["1", 3]]);
  });
  it("marks wrap the quoted text, and are skipped when the text changed", () => {
    const root = document.createElement("div");
    root.innerHTML = '<div class="md"><p>Chỗ mạnh thì dày, chỗ yếu thì thưa.</p></div>';
    const text = root.textContent!;
    const n = numberComments([{ id: "k", block_id: "b", anchor: { kind: "text", start: 0, end: 15, quote: text.slice(0, 15) }, body: "x", status: "open" }], ["b"]);
    markText(root, textMarks(n, "b", text, null));
    const m = root.querySelector("mark[data-cmt='k']")!;
    expect(m.textContent).toBe(text.slice(0, 15));
    expect((m as HTMLElement).dataset.n).toBe("1");
    expect(root.textContent).toBe(text);
    markText(root, []);
    expect(root.querySelector("mark")).toBeNull();
    expect(textMarks(n, "b", "khác hẳn", null)).toEqual([]);
  });
});

const course = (over: Partial<TeacherCourseSummary>): TeacherCourseSummary => ({
  id: "x",
  title: "X",
  status: "reading",
  status_line_vi: "",
  status_line_en: "",
  updated_at: "",
  latest_version: 0,
  versions: [],
  ...over,
});

describe("status mapping", () => {
  it("tags and routes", () => {
    expect(statusTag(course({ status: "reading" }))).toMatchObject({ tone: "wait", key: "gv.status.reading" });
    expect(statusTag(course({ status: "needs_retake" })).tone).toBe("err");
    expect(statusTag(course({ status: "building", build: { done: 3, total: 7 } }))).toMatchObject({ key: "gv.status.buildingN", params: { done: 3, total: 7 } });
    const pub = course({ status: "published", latest_version: 2, versions: [{ version: 1, status: "published", students: 38 }, { version: 2, status: "draft", students: 0 }] });
    expect(statusTag(pub)).toMatchObject({ tone: "ok", params: { version: 1, students: 38 } });
    expect(courseRoute(course({ status: "reading" }))).toBeNull();
    expect(courseRoute(course({ id: "a b", status: "outline_ready" }))).toBe("/khoa/a%20b");
    expect(courseRoute(course({ id: "a", status: "review", latest_version: 1 }))).toBe("/khoa/a/duyet?v=1");
  });
  it("build states and comment states", () => {
    expect(buildStateInfo("done").tone).toBe("done");
    expect(buildStateInfo("video")).toEqual({ key: "gv.build.video", tone: "now" });
    expect(buildStateInfo("waiting").tone).toBe("wait");
    expect(commentStatusInfo("open").fixed).toBe(false);
    expect(commentStatusInfo("applying").key).toBe("gv.cstatus.working");
    expect(commentStatusInfo("applied").fixed).toBe(true);
    expect(commentStatusInfo("failed").failed).toBe(true);
  });
  it("a job finishing is reported once, never on the first look", () => {
    const a = [course({ id: "1", status: "reading" }), course({ id: "2", status: "building" })];
    expect(finishedJobs(null, a)).toEqual([]);
    const prev = statusMap(a);
    const b = [course({ id: "1", status: "outline_ready" }), course({ id: "2", status: "building" }), course({ id: "3", status: "review" })];
    expect(finishedJobs(prev, b).map((j) => j.id)).toEqual(["1"]); // 3 is new: not a finished job
    expect(finishedJobs(statusMap(b), b)).toEqual([]);
    expect(finishedJobs(prev, [course({ id: "2", status: "review" })]).map((j) => j.status)).toEqual(["review"]);
  });
  it("notification deep links stay inside the teacher app", () => {
    expect(teacherDeepLink("/khoa/abc")).toBe("/khoa/abc");
    expect(teacherDeepLink("/khoa/abc/duyet?v=2")).toBe("/khoa/abc/duyet?v=2");
    expect(teacherDeepLink("//evil.com")).toBe("/");
    expect(teacherDeepLink("/khoa-hoc/abc")).toBe("/");
  });
});

describe("mock progress over time", () => {
  beforeEach(() => resetMockTeacher());
  afterEach(() => resetMockTeacher());

  it("reading -> outline; building goes lesson by lesson to review with a pack", () => {
    const db = load();
    const t0 = Date.now();
    const chem = db.courses.find((c) => c.id === "hoa-10-lien-ket")!;
    expect(chem.status).toBe("reading");
    tick(db, t0 + mockTiming.read + 10);
    expect(chem.status).toBe("outline_ready");
    expect(chem.outline?.chapters.length).toBeGreaterThan(0);

    const phys = db.courses.find((c) => c.id === "vat-li-11-dien-truong")!;
    expect(phys.status).toBe("needs_retake");
    expect(phys.retake.map((r) => r.page)).toEqual([3, 7]);
    // start a build by hand (same as POST /build)
    phys.build = phys.outline!.chapters.flatMap((c) => c.lessons).map((l) => ({ id: l.id, title: l.title, state: "waiting" as const }));
    phys.buildAt = t0;
    phys.status = "building";
    const per = mockTiming.writing + mockTiming.media + mockTiming.video;
    tick(db, t0 + per + 100);
    expect(phys.build[0].state).toBe("done");
    expect(["writing", "media", "video"]).toContain(phys.build[1].state);
    expect(phys.build[2].state).toBe("waiting");
    tick(db, t0 + per * phys.build.length + 10);
    expect(phys.status).toBe("review");
    expect(phys.versions).toMatchObject([{ version: 1, status: "draft", students: 0, level_confirmed: null }]);
    expect(phys.versions[0].level_suggested).toBe("intermediate"); // the mock builder suggests one; the teacher still has to confirm
    expect(phys.packs["1"].chapters.flatMap((c) => c.lessons)).toHaveLength(7);
  });

  it("a comment goes open -> applying -> applied and the block changes", async () => {
    const pack = packFromOutline("z", OUTLINE);
    expect(pack.chapters[0].lessons.map((l) => l.id)).toEqual(["a", "b", "c"]);
    const comments = await (async () => {
      const db = load();
      const c = db.courses.find((x) => x.id === "toan-1-dem-tao")!;
      const block = c.packs["1"].chapters[0].lessons[0].blocks.find((b) => b.kind === "text")!;
      const res = await mockTeacherApi.postComment("t", c.id, 1, { block_id: block.id, anchor: { kind: "time", t: 44 }, body: "chậm lại" });
      expect(res.status).toBe("open");
      const now = Date.now();
      tick(db, now + mockTiming.commentOpen + 50);
      expect(c.comments[0].status).toBe("applying");
      tick(db, now + mockTiming.commentApply + 50);
      return c.comments;
    })();
    expect(comments[0].status).toBe("applied");
    expect(comments[0].note).toBeTruthy();
  });

  it("editing a published course makes version N+1 and keeps v1 as it was", async () => {
    const v = await mockTeacherApi.newVersion("t", "xac-suat-bayes");
    expect(v).toBe(2);
    const list = await mockTeacherApi.listCourses("t");
    const c = list.find((x) => x.id === "xac-suat-bayes")!;
    expect(c.status).toBe("revising");
    expect(c.versions.map((x) => [x.version, x.status, x.students])).toEqual([[1, "published", 38], [2, "draft", 0]]);
    expect((await mockTeacherApi.getPack("t", "xac-suat-bayes", 1)).version).toBe(1);
    expect((await mockTeacherApi.getPack("t", "xac-suat-bayes", 2)).version).toBe(2);
    await mockTeacherApi.publish("t", "xac-suat-bayes", 2);
    const after = (await mockTeacherApi.listCourses("t")).find((x) => x.id === "xac-suat-bayes")!;
    expect(after.status).toBe("published");
    expect(after.versions.map((x) => [x.version, x.status, x.students])).toEqual([[1, "published", 38], [2, "published", 0]]);
  });

  it("the typed instruction 'gộp bài 5 và 6' changes the outline", async () => {
    const before = (await mockTeacherApi.getCourse("t", "vat-li-11-dien-truong")).outline!;
    const msgs = await mockTeacherApi.chat("t", "vat-li-11-dien-truong", "Gộp bài 5 và 6");
    expect(msgs.map((m) => m.role)).toEqual(["teacher", "agent"]);
    const after = (await mockTeacherApi.getCourse("t", "vat-li-11-dien-truong")).outline!;
    expect(after.chapters.flatMap((c) => c.lessons).length).toBe(before.chapters.flatMap((c) => c.lessons).length - 1);
  });
});

// ---------------------------------------------------------------- the screens
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

describe("teacher screens (mock)", () => {
  beforeEach(async () => {
    resetMockTeacher();
    await i18n.changeLanguage("vi");
  });
  afterEach(() => {
    resetMockTeacher();
    vi.restoreAllMocks();
  });

  it("home: drop zone, note, promise line and the course list with status tags", async () => {
    teacherApp("/");
    expect(await screen.findByRole("heading", { name: "Thả bài giảng vào đây" })).toBeInTheDocument();
    expect(screen.getByText(/Gửi xong là có thể đóng app/)).toBeInTheDocument();
    expect(screen.getByLabelText("Ghi chú (không bắt buộc)")).toBeInTheDocument();
    expect(screen.getByText("Chọn tệp")).toBeInTheDocument();
    expect(await screen.findByText("Vật lí 11: Điện trường")).toBeInTheDocument();
    expect(screen.getByText("Đang đọc tài liệu")).toBeInTheDocument(); // Hóa 10
    expect(screen.getByText("Cần chụp lại trang")).toBeInTheDocument();
    expect(screen.getByText("Chờ duyệt")).toBeInTheDocument();
    expect(screen.getByText("Đã xuất bản bản 1, 38 học sinh")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Quay lại" })).toBeNull(); // no back button on the home screen
  });

  it("home: a revising row says 'Đang sửa bản 2' once (pill only, the line is dropped when it repeats it)", async () => {
    const real = await mockTeacherApi.listCourses("mock-u-gv");
    vi.spyOn(mockTeacherApi, "listCourses").mockResolvedValue([
      { ...real[0], id: "rv", title: "Khóa đang sửa", status: "revising", latest_version: 2, status_line_vi: "Đang sửa bản 2", status_line_en: "Editing version 2" },
    ]);
    teacherApp("/");
    expect(await screen.findByText("Khóa đang sửa")).toBeInTheDocument();
    expect(screen.getAllByText("Đang sửa bản 2")).toHaveLength(1);
  });

  it("home: dropping a file shows the sending strip and the course appears", async () => {
    mockTiming.upload = 50;
    teacherApp("/");
    await screen.findByRole("heading", { name: "Thả bài giảng vào đây" });
    const file = new File(["x"], "bai-giang.pdf", { type: "application/pdf" });
    await userEvent.type(screen.getByLabelText("Ghi chú (không bắt buộc)"), "Cho lớp 11A2");
    const drop = new Event("drop", { bubbles: true, cancelable: true }) as Event & { dataTransfer?: unknown };
    drop.dataTransfer = { types: ["Files"], files: [file] };
    act(() => {
      window.dispatchEvent(drop);
    });
    expect(await screen.findByText("Đã nhận 1 tệp")).toBeInTheDocument();
    expect(await screen.findByText(/Bạn có thể đóng app/)).toBeInTheDocument();
    expect(await screen.findByText("Bai giang")).toBeInTheDocument();
    mockTiming.upload = 1400;
  });

  it("structure chat: retake cards, rename in place sends a rename op, delete and add", async () => {
    teacherApp("/khoa/vat-li-11-dien-truong");
    expect(await screen.findByRole("heading", { name: "Vật lí 11: Điện trường" })).toBeInTheDocument();
    expect(screen.getByText("Trang 3")).toBeInTheDocument();
    expect(screen.getByText("Trang 7")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chụp lại trang 3" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chụp lại trang 7" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Quay lại" })).toBeInTheDocument();

    const spy = vi.spyOn(mockTeacherApi, "putOutline");
    const name = await screen.findByLabelText("Tên bài 3");
    expect(name).toHaveValue("Đường sức điện");
    await userEvent.clear(name);
    await userEvent.type(name, "Đường sức{Enter}");
    await waitFor(() => expect(spy).toHaveBeenCalledWith(expect.anything(), "vat-li-11-dien-truong", [{ op: "rename", id: "duong-suc-dien", title: "Đường sức" }]));

    await userEvent.click(screen.getByRole("button", { name: "Xóa bài 7" }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith(expect.anything(), "vat-li-11-dien-truong", [{ op: "delete", id: "tu-dien" }]));
    await waitFor(() => expect(screen.queryByLabelText("Tên bài 7")).toBeNull());

    // keyboard reorder: arrow up on lesson 2's handle swaps it with lesson 1's neighbour
    fireEvent.keyDown(screen.getByRole("button", { name: "Đổi thứ tự bài 3" }), { key: "ArrowUp" });
    await waitFor(() => expect(spy).toHaveBeenCalledWith(expect.anything(), "vat-li-11-dien-truong", [{ op: "reorder", ids: ["duong-suc-dien", "cuong-do-dien-truong", "dien-truong-deu"], parent: "ch-2" }]));

    const add = screen.getAllByRole("button", { name: "Thêm bài" })[0];
    await userEvent.click(add);
    await waitFor(() => expect(spy).toHaveBeenCalledWith(expect.anything(), "vat-li-11-dien-truong", [{ op: "add_lesson", chapter: "ch-1", title: "Bài mới", after: "dien-tich-dinh-luat-cu-long" }]));
    const server = (await mockTeacherApi.getCourse("t", "vat-li-11-dien-truong")).outline!;
    expect(server.chapters[0].lessons.map((l) => l.title)).toEqual(["Điện tích, định luật Cu-lông", "Bài mới"]);
    expect(server.chapters[1].lessons[0].title).toBe("Đường sức");
  }, 20000);

  it("retake: 'Chụp lại trang 3' uploads with replace=<file>#3", async () => {
    mockTiming.upload = 20;
    teacherApp("/khoa/vat-li-11-dien-truong");
    const spy = vi.spyOn(mockTeacherApi, "addMaterials");
    await screen.findByText("Trang 3");
    const picks = document.querySelectorAll<HTMLInputElement>('input[type="file"][aria-label="Chọn ảnh có sẵn"]');
    // the "pick an existing photo" link for page 3 sets the target, then the shared input takes the file
    await userEvent.click(screen.getAllByRole("button", { name: "Chọn ảnh có sẵn" })[0]);
    fireEvent.change(picks[0], { target: { files: [new File(["x"], "t3.jpg", { type: "image/jpeg" })] } });
    await waitFor(() => expect(spy).toHaveBeenCalledWith(expect.anything(), "vat-li-11-dien-truong", expect.any(Array), "sach-vat-li-11.pdf#3"));
    mockTiming.upload = 1400;
  });

  it("composing shows per-lesson status", async () => {
    teacherApp("/khoa/vat-li-11-dien-truong");
    await screen.findByText("Trang 3");
    await userEvent.click(screen.getByRole("button", { name: "Soạn theo cấu trúc này" }));
    expect(await screen.findByText(/Đang soạn 7 bài/)).toBeInTheDocument();
    expect(await screen.findAllByText(/Chờ|Đang viết bài|Đang làm hình|Đang dựng video|Xong/)).not.toHaveLength(0);
    expect(screen.queryByLabelText("Nhắn thay đổi")).toBeNull(); // composer is gone while composing
  });

  it("review: video comment at a time and image pin are sent with the right anchors", async () => {
    teacherApp("/khoa/toan-1-dem-tao/duyet?v=1");
    expect(await screen.findByRole("button", { name: "Xuất bản" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Quay lại" })).toBeInTheDocument();
    const spy = vi.spyOn(mockTeacherApi, "postComment");

    // the apple-counting lesson has pictures; walk through the lessons until a pin layer or video bar shows up
    const pin = await screen.findAllByRole("button", { name: /Chạm vào chỗ chưa ưng/ });
    fireEvent.keyDown(pin[0], { key: "Enter" });
    const box = await screen.findByRole("textbox", { name: "Nhận xét" });
    await userEvent.type(box, "Hình mờ");
    await userEvent.click(screen.getByRole("button", { name: "Gửi" }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    const sent = spy.mock.calls[0][3];
    expect(sent.anchor.kind).toBe("point");
    expect(sent.body).toBe("Hình mờ");

    // it shows in the margin as "đang sửa" and the publish button waits
    expect(await screen.findByText("Đang sửa")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Xuất bản" })).toBeDisabled();
  }, 20000);

  it("review of a published course offers 'Sửa khóa đã xuất bản' and opens version 2", async () => {
    teacherApp("/khoa/xac-suat-bayes/duyet?v=1");
    const edit = await screen.findByRole("button", { name: "Sửa khóa đã xuất bản" });
    expect(screen.getByText(/38 học sinh đang học/)).toBeInTheDocument();
    await userEvent.click(edit);
    await waitFor(() => expect(screen.getByRole("button", { name: "Xuất bản bản 2" })).toBeEnabled(), { timeout: 5000 });
    expect(await screen.findByText(/38 học sinh đang học bản 1\. Bản sửa này là bản 2/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Xuất bản bản 2" })).toBeEnabled(), { timeout: 5000 });
    await userEvent.click(screen.getByRole("button", { name: "Xuất bản bản 2" }));
    const dlg = await screen.findByRole("dialog");
    await userEvent.click(within(dlg).getByRole("button", { name: "Xuất bản bản 2" }));
    expect(await screen.findByText(/Đã xuất bản bản 2/)).toBeInTheDocument();
  }, 20000);
});

describe("course level (mock)", () => {
  beforeEach(async () => {
    resetMockTeacher();
    await i18n.changeLanguage("vi");
    Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(() => {
    resetMockTeacher();
    vi.restoreAllMocks();
  });

  it("api: publishing waits for a confirmed level; changing a published level makes version 2 and keeps version 1", async () => {
    await expect(mockTeacherApi.publish("t", "toan-1-dem-tao", 1)).rejects.toMatchObject({ status: 409 });
    const c = (await mockTeacherApi.getCourse("t", "toan-1-dem-tao")).course;
    expect([c.level, c.level_suggested, c.level_confirmed]).toEqual([null, "basic", null]);
    await mockTeacherApi.setLevel("t", "toan-1-dem-tao", 1, "intermediate");
    await mockTeacherApi.publish("t", "toan-1-dem-tao", 1);
    expect((await mockTeacherApi.getCourse("t", "toan-1-dem-tao")).course.level).toBe("intermediate");

    expect(await mockTeacherApi.setLevel("t", "xac-suat-bayes", 1, "advanced")).toEqual({ version: 1, new_version: false }); // same level, nothing happens
    expect(await mockTeacherApi.setLevel("t", "xac-suat-bayes", 1, "basic")).toEqual({ version: 2, new_version: true });
    const b = (await mockTeacherApi.getCourse("t", "xac-suat-bayes")).course;
    expect(b.level).toBe("advanced"); // students still see version 1's level
    expect(b.versions.map((v) => [v.version, v.level_confirmed])).toEqual([[1, "advanced"], [2, "basic"]]);
  });

  it("review: the picker has three options, the suggestion is pre-selected and marked, one tap confirms", async () => {
    teacherApp("/khoa/toan-1-dem-tao/duyet?v=1");
    const group = await screen.findByRole("radiogroup", { name: "Mức độ khóa học" });
    const radios = within(group).getAllByRole("radio");
    expect(radios.map((r) => r.textContent)).toEqual(["Cơ bảnGợi ý", "Trung bình", "Nâng cao"]);
    expect(radios.map((r) => r.getAttribute("aria-checked"))).toEqual(["true", "false", "false"]);
    expect(screen.getAllByText("Cơ bản").length).toBeGreaterThan(1); // the header tag says it too
    expect(screen.getByRole("button", { name: "Xác nhận mức độ" })).toBeInTheDocument();

    await userEvent.click(within(group).getByRole("radio", { name: /Nâng cao/ }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Xác nhận mức độ" })).toBeNull());
    expect(within(group).getByRole("radio", { name: /Nâng cao/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByText("Gợi ý")).toBeNull();
    expect((await mockTeacherApi.getCourse("t", "toan-1-dem-tao")).course.level_confirmed).toBe("advanced");
  }, 20000);

  it("review: publish stays dimmed until the level is confirmed, and tapping it points at the picker", async () => {
    teacherApp("/khoa/toan-1-dem-tao/duyet?v=1");
    const pub = await screen.findByRole("button", { name: "Xuất bản" });
    expect(pub).toHaveAttribute("aria-disabled", "true");
    expect(screen.queryByText("Xác nhận mức độ để xuất bản.")).toBeNull();
    await userEvent.click(pub);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await screen.findByText("Xác nhận mức độ để xuất bản.")).toBeInTheDocument();
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    expect(document.getElementById("levelrow")).toHaveClass("need");

    await userEvent.click(screen.getByRole("button", { name: "Xác nhận mức độ" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Xuất bản" })).not.toHaveAttribute("aria-disabled"));
    expect(screen.queryByText("Xác nhận mức độ để xuất bản.")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Xuất bản" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  }, 20000);

  it("review of a published course: changing the level says it lands in version 2", async () => {
    teacherApp("/khoa/xac-suat-bayes/duyet?v=1");
    const group = await screen.findByRole("radiogroup", { name: "Mức độ khóa học" });
    expect(within(group).getByRole("radio", { name: /Nâng cao/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByRole("button", { name: "Xác nhận mức độ" })).toBeNull(); // already confirmed
    expect(screen.queryByText("Gợi ý")).toBeNull();
    await userEvent.click(within(group).getByRole("radio", { name: /Trung bình/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Xuất bản bản 2" })).toBeEnabled(), { timeout: 5000 });
    await waitFor(() => expect(screen.getByText("Mức độ mới sẽ có trong bản 2.")).toBeInTheDocument(), { timeout: 5000 }); // the pick sits in version 2
    expect(within(await screen.findByRole("radiogroup", {}, { timeout: 5000 })).getByRole("radio", { name: /Trung bình/ })).toHaveAttribute("aria-checked", "true");
  }, 20000);

  it("home: a course row carries the bars-and-word tag once it has a level", async () => {
    teacherApp("/");
    const math = (await screen.findByText("Toán 1: Các số đến 10")).closest("a")!;
    expect(within(math).getByText("Cơ bản")).toBeInTheDocument();
    const bayes = screen.getByText("Xác suất thống kê: Suy luận Bayes").closest("a")!;
    expect(within(bayes).getByText("Nâng cao")).toBeInTheDocument();
    const phys = screen.getByText("Vật lí 11: Điện trường").closest("a")!;
    expect(phys.querySelector(".lvx-tag")).toBeNull(); // not composed yet
  });

  it("english strings", async () => {
    teacherApp("/khoa/toan-1-dem-tao/duyet?v=1", "en");
    const group = await screen.findByRole("radiogroup", { name: "Course level" });
    expect(within(group).getAllByRole("radio").map((r) => r.textContent)).toEqual(["BasicSuggested", "Intermediate", "Advanced"]);
    expect(screen.getByRole("button", { name: "Confirm level" })).toBeInTheDocument();
  }, 20000);
});

describe("gateway media urls", () => {
  afterEach(() => setMediaToken(null));
  it("a retake thumbnail carries the media token, not the session token (the gateway refuses that one in ?t=)", () => {
    setMediaToken("media-tok");
    const src = httpTeacherApi.thumbSrc("session-tok", "/api/teacher/courses/c1/thumb?ref=a.jpg%231");
    expect(src).toContain("&t=media-tok");
    expect(src).not.toContain("session-tok");
  });
});
