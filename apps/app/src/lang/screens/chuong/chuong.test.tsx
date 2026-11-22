import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import i18n from "../../../i18n";
import { App } from "../../../App";
import { AuthProvider } from "../../../state/auth";
import { SOON } from "../../../api/mock-soon";
import { chickenOfSubject } from "../../chickenOf";
import { MiniPlayer } from "./Recap";
import { activeFilters, activeIndex, emptyFind, ladderBand, lessonState, parseFind, stageIndex, toggleFacet, writeFind, type Row } from "./logic";

const THPT = 2010; // g10_12 on the 2026 school year
const KID = 2018; // g1_5
const UNI = 2000;

function seed(birth: number, band: string, chickens: string[] = ["li"]) {
  localStorage.setItem("mentor.mock.users", JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Bi", age_band: band, birth_year: birth, language: "vi", theme: "system", quiet_until: null, avatar: "nam" } } }));
  localStorage.setItem("mentor.token", "mock-u-hs");
  localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["lg-hello", "lg-village", "lg-chuong"]));
  if (chickens.length) localStorage.setItem("mentor.mock.lg.u-hs", JSON.stringify({ chickens: chickens.map((id) => ({ id, xp: 0, taken_at: "2026-11-01T00:00:00Z" })) }));
}
function Where() {
  const l = useLocation();
  return <output data-testid="where">{l.pathname + l.search}</output>;
}
const open = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
        <Where />
      </AuthProvider>
    </MemoryRouter>,
  );
const where = () => screen.getByTestId("where").textContent ?? "";
const cards = () => screen.queryAllByTestId("course-card");
const titles = () => cards().map((c) => c.querySelector("h3")?.textContent ?? "");

beforeEach(async () => {
  await i18n.changeLanguage("vi");
  localStorage.clear();
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => vi.restoreAllMocks());

// ------------------------------------------------------------------ pure logic
describe("which chicken a course belongs to", () => {
  it("follows the lg-03 table: school vs university, science only in grades 10 to 12", () => {
    expect(chickenOfSubject("Toán", "g10_12")).toBe("toan");
    expect(chickenOfSubject("Vật lí", "g10_12")).toBe("li");
    expect(chickenOfSubject("Vật lí", "g6_9")).toBe("khoahoc");
    expect(chickenOfSubject("Xác suất thống kê", "uni")).toBe("khdl");
    expect(chickenOfSubject("Lập trình Python", "uni")).toBe("khmt");
    expect(chickenOfSubject("Chuyện lạ", "g6_9")).toBe("kn");
    expect(chickenOfSubject("Chuyện lạ", "uni")).toBe("daicuong");
    expect(chickenOfSubject("Toán", "g10_12", "kn")).toBe("kn"); // a teacher's label wins
  });
});

describe("the chicken's page: logic", () => {
  const row = (state: Row["state"], at: number, finished = false): Row => ({ id: "c", title: "t", lessons: [1, 2, 3].map((n) => ({ id: `l${n}`, title: `L${n}`, est_minutes: 5, key_ideas: [] })), at, finished, percent: 0, state });
  it("names four stages by level", () => {
    expect([1, 2, 4, 5, 9, 10].map(stageIndex)).toEqual([1, 2, 2, 3, 3, 4]);
  });
  it("lessons before the saved one are done, that one is now, the rest later; a finished course is all done", () => {
    const r = row("now", 1);
    expect([0, 1, 2].map((i) => lessonState(r, i))).toEqual(["done", "now", "later"]);
    expect([0, 1, 2].map((i) => lessonState(row("fin", 3, true), i))).toEqual(["done", "done", "done"]);
  });
  it("the big button works on the course in progress, else the first not started", () => {
    expect(activeIndex([row("fin", 3, true), row("new", 0), row("now", 1)])).toBe(2);
    expect(activeIndex([row("fin", 3, true), row("new", 0)])).toBe(1);
    expect(activeIndex([])).toBe(0);
  });
  it("the ladder has its words by age band", () => {
    expect([ladderBand("g1_5"), ladderBand("g6_9"), ladderBand("uni")]).toEqual(["kid", "school", "uni"]);
  });
  it("the search board keeps its state in the address and leaves the other parameters alone", () => {
    const s = parseFind(new URLSearchParams("khoa=x&tim=1&q=dao+dong&c=abc&page=2&sort=new&level=basic&level=advanced"));
    expect(s).toMatchObject({ q: "dao dong", c: "abc", page: 2, sort: "new" });
    expect(s.f.level).toEqual(["basic", "advanced"]);
    expect(activeFilters(s)).toBe(2);
    const back = writeFind(new URLSearchParams("khoa=x"), s);
    expect(back.get("khoa")).toBe("x");
    expect(back.get("tim")).toBe("1");
    expect(back.getAll("level")).toEqual(["basic", "advanced"]);
    expect(writeFind(back, emptyFind(), false).toString()).toBe("khoa=x");
    const t = toggleFacet(s, "language", "en");
    expect(t.page).toBe(1);
    expect(t.f.language).toEqual(["en"]);
  });
});

// ------------------------------------------------------------------ the coop
describe("chuồng gà (lg-03)", () => {
  it("shows the chicken, its growth and its own courses: lessons done / now / later, the ladder, one big button", async () => {
    seed(THPT, "g10_12");
    open("/chuong/li");
    expect(await screen.findByRole("heading", { name: "Gà Lí" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Các giai đoạn lớn của gà" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Kinh nghiệm lên cấp tiếp theo" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Khóa của Gà Lí" })).toBeInTheDocument();
    const course = await screen.findByRole("article");
    expect(course).toHaveTextContent("Vật lí 11: Điện trường");
    const tree = within(course).getByRole("navigation", { name: /Nội dung khóa/ });
    expect(tree.querySelectorAll(".ck-nowrow")).toHaveLength(1);
    expect(tree.querySelectorAll(".ck-later").length).toBeGreaterThan(0);
    const now = tree.querySelector("a.ck-nowrow") as HTMLAnchorElement;
    expect(now.getAttribute("href")).toMatch(/^\/khoa-hoc\/vat-li-11-dien-truong\/hoc\?lesson=[^&]+&from=khoa$/);
    expect(await within(tree).findByText("Thông hiểu")).toBeInTheDocument(); // the practice ladder
    expect(await within(tree).findByRole("link", { name: /Thông hiểu/ })).toHaveAttribute("href", expect.stringMatching(/^\/kiem-tra\/vat-li-11-dien-truong\?state=luyen&level=2&from=chuong$/));
    // the other chickens' courses are not here
    expect(screen.queryByText(/Toán 1/)).toBeNull();
  });

  it("practice inside a course: solid level ticked, Mentor's level marked, closed levels not tappable, the mock exam under it", async () => {
    seed(THPT, "g10_12");
    open("/chuong/li");
    const tree = await screen.findByRole("navigation", { name: /Nội dung khóa/ });
    const ladder = await waitFor(() => {
      const el = [...tree.querySelectorAll<HTMLElement>("details.ck-grp")].find((d) => d.querySelector("summary")?.textContent?.includes("Luyện tập"));
      if (!el) throw new Error("no ladder yet");
      return el;
    });
    const node = (name: string) => [...ladder.querySelectorAll<HTMLElement>(".ck-node")].find((n) => n.textContent?.includes(name))!;
    expect(node("Nhận biết")).toHaveClass("ck-done");
    expect(node("Thông hiểu")).toHaveAttribute("aria-current", "step");
    expect(node("Thông hiểu").tagName).toBe("A");
    expect(node("Vận dụng cao").tagName).toBe("SPAN"); // nothing studied at that level yet: not tappable
    expect(node("Vận dụng cao")).toHaveClass("ck-later");
  });

  it("the big button continues the lesson in progress and the speech bubble offers it too", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/chuong/li");
    const cta = await screen.findByTestId("cta");
    expect(cta).toHaveTextContent("Tiếp tục");
    expect(cta).toHaveTextContent("Vật lí 11: Điện trường");
    expect(screen.getByText(/Mình học tiếp “Điện trường” nhé\?/)).toBeInTheDocument();
    await ui.click(cta);
    await waitFor(() => expect(where()).toMatch(/^\/khoa-hoc\/vat-li-11-dien-truong\/hoc\?lesson=[^&]+&from=khoa$/));
  });

  it("a course folds shut and open (the one in progress starts open)", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/chuong/li");
    const head = (await screen.findAllByRole("button", { name: /Vật lí 11: Điện trường/ })).find((b) => b.hasAttribute("aria-expanded"))!;
    expect(head).toHaveAttribute("aria-expanded", "true");
    await ui.click(head);
    expect(head).toHaveAttribute("aria-expanded", "false");
    expect(where()).toContain("khoa=-");
  });

  it("an unknown chicken goes back to the village", async () => {
    seed(THPT, "g10_12");
    open("/chuong/khong-co");
    await waitFor(() => expect(where()).toBe("/"));
  });

  it("the village's chicken lands here and 'Về làng' goes back", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/chuong/li");
    await ui.click(await screen.findByRole("button", { name: "Về làng gà" }));
    await waitFor(() => expect(where()).toBe("/"));
  });
});

describe("Nghe tóm tắt in the coop", () => {
  beforeEach(() => {
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
      Object.defineProperty(this, "paused", { value: false, configurable: true });
      this.dispatchEvent(new Event("play"));
      return Promise.resolve();
    });
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (this: HTMLMediaElement) {
      Object.defineProperty(this, "paused", { value: true, configurable: true });
      this.dispatchEvent(new Event("pause"));
    });
  });

  it("a row opens the docked player: play, 10 s back, speed 1x / 1,25x, progress", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/chuong/li");
    await ui.click(await screen.findByRole("button", { name: /Nghe tóm tắt · 4 phút/ }));
    const mini = await screen.findByRole("region", { name: "Nghe tóm tắt" });
    expect(within(mini).getByRole("button", { name: "Lùi 10 giây" })).toBeInTheDocument();
    expect(within(mini).getByRole("slider", { name: "Tiến độ" })).toBeInTheDocument();
    expect(await within(mini).findByRole("button", { name: "Tạm dừng" })).toBeInTheDocument(); // starts at once
    await ui.click(within(mini).getByRole("button", { name: "Tốc độ 1x" }));
    expect(within(mini).getByRole("button", { name: "Tốc độ 1.25x" })).toHaveTextContent("1.25x");
    await ui.click(within(mini).getByRole("button", { name: "Tạm dừng" }));
    expect(within(mini).getByRole("button", { name: "Phát" })).toBeInTheDocument();
    await ui.click(within(mini).getByRole("button", { name: "Đóng" }));
    expect(screen.queryByRole("region", { name: "Nghe tóm tắt" })).toBeNull();
  });

  it("little ones get one big play button", async () => {
    await i18n.changeLanguage("vi");
    const item = { chapter: { id: "c1", title: "Chương 1", lessons: [], recap: { script: ["Chào em"], duration_s: 120 } }, src: "recap.mp3", minutes: 2, offline: true };
    render(<MiniPlayer item={item} kid name="Gà Toán" face="" onClose={() => undefined} />);
    const mini = await screen.findByRole("region", { name: "Nghe tóm tắt" });
    expect(within(mini).queryByRole("button", { name: "Lùi 10 giây" })).toBeNull();
    expect(within(mini).queryByRole("slider")).toBeNull();
    expect(within(mini).getByText("Gà Toán kể lại · 2 phút")).toBeInTheDocument();
    expect(within(mini).getByRole("button", { name: /Tạm dừng|Phát/ })).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ Tìm thêm khóa, scoped to the chicken
describe("Tìm thêm khóa (only this chicken's subject)", () => {
  it("lists the chicken's own courses, 12 a page, with tags, a count and the pager", async () => {
    seed(THPT, "g10_12");
    open("/chuong/li?tim=1");
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    expect(titles().every((t) => /^Vật lí/.test(t))).toBe(true);
    expect(titles()).toContain("Vật lí 11: Điện trường");
    expect(screen.getByText(/^\d+ khóa$/)).toBeInTheDocument();
    expect(cards()[0].querySelector(".ck-pm")?.textContent).toMatch(/ · \d+ bài · /);
    expect(cards()[0].querySelector(".ck-ctags")).not.toBeNull();
    expect(cards().some((c) => /Sắp có/.test(c.textContent ?? ""))).toBe(true);
    const pager = screen.getByRole("navigation", { name: "Trang" });
    expect(within(pager).getByRole("button", { name: "Trang trước" })).toBeDisabled();
    expect(within(pager).getByRole("button", { name: "Trang 1" })).toHaveAttribute("aria-current", "page");
    // the course the student has says so
    expect(cards().find((c) => /Điện trường/.test(c.textContent ?? ""))).toHaveTextContent("Đã có");
    // sort tabs; no band chip (the chicken is the scope)
    expect(screen.getByRole("button", { name: "Liên quan" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText(/Cấp học/)).toBeNull();
  });

  it("typing searches within the chicken: the address keeps q, one result, bold match", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/chuong/li?tim=1");
    await waitFor(() => expect(cards().length).toBeGreaterThan(1));
    await ui.type(screen.getByRole("searchbox", { name: "Tìm khóa" }), "dao dong");
    await waitFor(() => expect(cards()).toHaveLength(1), { timeout: 4000 });
    expect(titles()[0]).toBe("Vật lí 12: Dao động cơ và sóng");
    expect(cards()[0].querySelector("mark")).not.toBeNull();
    expect(decodeURIComponent(where()).replaceAll("+", " ")).toContain("q=dao dong");
    expect(where()).toContain("tim=1");
  });

  it("autocomplete: recent searches (removable, per user); typing offers courses of this chicken", async () => {
    seed(THPT, "g10_12");
    localStorage.setItem("mentor.recentSearches.u-hs", JSON.stringify(["dao dong", "dien truong"]));
    const ui = userEvent.setup();
    open("/chuong/li?tim=1");
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    const input = screen.getByRole("searchbox", { name: "Tìm khóa" });
    await ui.click(input);
    expect(await screen.findByText("Tìm gần đây")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Xóa “dao dong”" }));
    expect(screen.queryByRole("button", { name: "dao dong" })).toBeNull();
    expect(JSON.parse(localStorage.getItem("mentor.recentSearches.u-hs")!)).toEqual(["dien truong"]);
    await ui.type(input, "dien");
    const group = await screen.findByText("Khóa", { selector: "h4" });
    expect(group).toBeInTheDocument();
    const item = await waitFor(() => {
      const el = document.querySelector(".ck-ac .ck-it");
      expect(el).not.toBeNull();
      return el as HTMLElement;
    });
    await ui.click(item);
    expect(JSON.parse(localStorage.getItem("mentor.recentSearches.u-hs")!)[0]).toMatch(/Điện trường/);
  });

  it("no results: 'Xem tất cả khóa' brings the list back; a typo offers 'Ý em là'", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/chuong/li?tim=1&q=tich+phan");
    const few = await screen.findByTestId("few-results");
    expect(few).toHaveTextContent("Không thấy khóa nào");
    await ui.click(within(few).getByRole("button", { name: "Xem tất cả khóa" }));
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    expect(where()).not.toContain("q=");
    // a typo
    const ui2 = userEvent.setup();
    document.body.innerHTML = "";
    open("/chuong/li?tim=1&q=dao+dogn");
    const few2 = await screen.findByTestId("few-results");
    const hint = await within(few2).findByRole("button", { name: /dong|động/ });
    await ui2.click(hint);
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
  });

  it("the filter panel: opens from 'Lọc' with a badge, a chip removes a filter, 'Xóa hết' clears them, changing one goes back to page 1", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/chuong/li?tim=1&page=1");
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    const btn = screen.getByRole("button", { name: /^Lọc/ });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    await ui.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "true");
    const group = screen.getByRole("group", { name: "Độ khó" });
    await ui.click(within(group).getByRole("button", { name: /Trung bình/ }));
    await waitFor(() => expect(where()).toContain("level=intermediate"));
    expect(screen.getByTestId("filter-badge")).toHaveTextContent("1");
    expect(screen.getByTestId("active-chips")).toHaveTextContent("Trung bình");
    await ui.click(within(group).getByRole("button", { name: /Nâng cao/ }));
    expect(where()).toContain("level=advanced");
    await ui.click(screen.getByRole("button", { name: "Xóa hết" }));
    await waitFor(() => expect(where()).not.toContain("level="));
    expect(screen.queryByTestId("active-chips")).toBeNull();
  });

  it("the kid version is simple: a big search with a mic, tiles with a title only, no filters or sort; the mic says so when it cannot listen", async () => {
    seed(KID, "g1_5", ["toan"]);
    const ui = userEvent.setup();
    open("/chuong/toan?tim=1");
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    expect(document.querySelector(".ck-pcs")).toHaveClass("ck-kid");
    expect(screen.queryByRole("button", { name: /^Lọc/ })).toBeNull();
    expect(screen.queryByRole("group", { name: "Sắp xếp" })).toBeNull();
    expect(cards()[0].querySelector(".ck-pm")).toBeNull();
    expect(screen.getByRole("searchbox", { name: "Tìm khóa" })).toHaveAttribute("placeholder", "Em muốn học gì?");
    await ui.click(screen.getByRole("button", { name: "Nói để tìm" }));
    expect(await screen.findByText("Máy này chưa nghe được. Em gõ nhé.")).toBeInTheDocument();
  });
});

describe("Thêm: a course joins this chicken", () => {
  it("Thêm enrolls (free), the card says 'Đã có', a toast offers 'Xem', the course shows in the chicken's list and opens; the big button starts it", async () => {
    seed(UNI, "uni", ["khdl"]);
    localStorage.setItem("mentor.mock.enroll.u-hs", "[]"); // nothing enrolled yet
    const ui = userEvent.setup();
    open("/chuong/khdl?tim=1");
    await waitFor(() => expect(titles()).toContain("Xác suất thống kê: Suy luận Bayes"));
    const card = cards().find((c) => /Bayes/.test(c.textContent ?? ""))!;
    expect(screen.queryByRole("article")).toBeNull(); // nothing of this chicken's yet
    await ui.click(within(card).getByRole("button", { name: "Thêm" }));
    await waitFor(() => expect(within(card).getByText("Đã có")).toBeInTheDocument());
    const toast = await screen.findByText("Đã thêm vào Gà Khoa học dữ liệu");
    expect(toast).toBeInTheDocument();
    const article = await screen.findByRole("article");
    expect(article).toHaveTextContent("Bayes");
    await ui.click(screen.getByRole("button", { name: "Xem" }));
    await waitFor(() => expect(where()).toContain("khoa=xac-suat-bayes"));
    expect(screen.getByTestId("cta")).toHaveTextContent("Bắt đầu");
    await ui.click(screen.getByTestId("cta"));
    await waitFor(() => expect(where()).toMatch(/^\/khoa-hoc\/xac-suat-bayes\/hoc\?lesson=[^&]+&from=khoa$/));
  }, 20000);

  it("the preview dialog: tree and outcomes, Thêm vào <gà>, then Bắt đầu học; Escape closes and leaves the address clean", async () => {
    seed(UNI, "uni", ["khdl"]);
    localStorage.setItem("mentor.mock.enroll.u-hs", "[]");
    const ui = userEvent.setup();
    open("/chuong/khdl?tim=1");
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    const link = within(cards().find((c) => /Bayes/.test(c.textContent ?? ""))!).getByRole("link");
    await ui.click(link);
    const dialog = await screen.findByRole("dialog");
    expect(where()).toContain("c=xac-suat-bayes");
    expect(await within(dialog).findByRole("heading", { name: /Bayes/ })).toBeInTheDocument();
    expect(within(dialog).getByText("Học xong em sẽ")).toBeInTheDocument();
    expect(within(dialog).getByText("Miễn phí")).toBeInTheDocument();
    await ui.click(within(dialog).getByRole("button", { name: "Thêm vào Gà Khoa học dữ liệu" }));
    expect(await within(dialog).findByRole("button", { name: "Bắt đầu học" })).toBeInTheDocument();
    await ui.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(where()).not.toContain("c=");
  }, 20000);

  it("a coming-soon course previews its tree and cannot be added or started", async () => {
    seed(THPT, "g10_12");
    const soon = SOON.find((x) => x.meta.title === "Vật lí 12: Dao động cơ và sóng")!;
    open(`/chuong/li?c=${soon.meta.id}`);
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("heading", { name: soon.meta.title })).toBeInTheDocument();
    expect(within(dialog).getByText(/Khóa này sắp có/)).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /Thêm vào|Bắt đầu/ })).toBeNull();
    expect(dialog.querySelectorAll(".ck-grp").length).toBeGreaterThan(1);
  });
});

// ------------------------------------------------------------------ old addresses
describe("old addresses land in the coop", () => {
  it("/khoa-hoc/<id> of a course the student has opens its tree; of one they have not, its preview", async () => {
    seed(THPT, "g10_12");
    localStorage.setItem("mentor.mock.enroll.u-hs", JSON.stringify([{ course_id: "vat-li-11-dien-truong", pinned_version: 1, enrolled_at: "2026-11-01T08:00:00Z", progress: null }]));
    const a = open("/khoa-hoc/vat-li-11-dien-truong");
    await waitFor(() => expect(where()).toBe("/chuong/li?khoa=vat-li-11-dien-truong"));
    await waitFor(() => expect(document.querySelector(".ck-c-head")).toHaveAttribute("aria-expanded", "true"));
    a.unmount();
    open("/khoa-hoc/xac-suat-bayes");
    await waitFor(() => expect(where()).toBe("/chuong/khdl?c=xac-suat-bayes"));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("/khoa-hoc/<id>?lesson= still opens the player; /khoa-hoc goes to the village", async () => {
    seed(THPT, "g10_12");
    const a = open("/khoa-hoc/vat-li-11-dien-truong?lesson=l1");
    await waitFor(() => expect(where()).toBe("/khoa-hoc/vat-li-11-dien-truong/hoc?lesson=l1"));
    a.unmount();
    open("/khoa-hoc");
    await waitFor(() => expect(where()).toBe("/"));
  });

  it("/khoa-hoc/tim-kiem is the search of the student's first chicken (the village when they have none)", async () => {
    seed(THPT, "g10_12", ["li", "toan"]);
    const a = open("/khoa-hoc/tim-kiem?q=dao+dong");
    await waitFor(() => expect(where()).toBe("/chuong/li?tim=1&q=dao+dong"));
    a.unmount();
    seed(THPT, "g10_12", []);
    localStorage.removeItem("mentor.mock.lg.u-hs");
    open("/khoa-hoc/tim-kiem");
    await waitFor(() => expect(where()).toMatch(/^\/(chon-ga)?$/));
  });
});
