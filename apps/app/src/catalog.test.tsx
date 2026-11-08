import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import i18n from "./i18n";
import { App } from "./App";
import { AuthProvider } from "./state/auth";
import { makeMockCourseApi } from "./api/mock-course-api";
import { SOON } from "./api/mock-soon";
import type { AgeBand, User } from "./api";

const THPT = 2010; // g10_12 on the 2026 school year
const KID = 2018; // g1_5

function seed(birth: number, band: AgeBand) {
  const u: User = { id: "u-hs", role: "student", username: "hocsinh", display_name: "Bi", age_band: band, birth_year: birth, language: "vi", theme: "system", quiet_until: null };
  localStorage.setItem("mentor.mock.users", JSON.stringify({ hocsinh: { password: "123456", user: u } }));
  localStorage.setItem("mentor.token", "mock-u-hs");
  return u;
}

function Where() {
  const l = useLocation();
  return <output data-testid="where">{l.pathname + l.search}</output>;
}

function open(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
        <Where />
      </AuthProvider>
    </MemoryRouter>,
  );
}

const cards = () => screen.queryAllByTestId("course-card");
const titles = () => cards().map((c) => c.querySelector("h3")?.textContent ?? "");
const where = () => screen.getByTestId("where").textContent ?? "";

let scrolled: HTMLElement[] = [];
beforeEach(async () => {
  await i18n.changeLanguage("vi");
  scrolled = [];
  Element.prototype.scrollIntoView = vi.fn(function (this: HTMLElement) {
    scrolled.push(this);
  });
});
afterEach(() => vi.restoreAllMocks());

// ------------------------------------------------------------------ the mock API (same rules as the gateway)
describe("mock catalog query", () => {
  const user = { id: "u", role: "student", username: "u", display_name: "u", age_band: "g10_12", birth_year: THPT, language: "vi", theme: "system", quiet_until: null } as User;
  const api = makeMockCourseApi(() => user);
  const q = (query: Parameters<typeof api.queryCatalog>[1]) => api.queryCatalog("t", query);

  it("has all 107 placeholders and the 3 live courses, 10 per page", async () => {
    expect(SOON).toHaveLength(107);
    const r = await q({});
    expect(r.total).toBe(110);
    expect(r.pages).toBe(11);
    expect(r.items).toHaveLength(10);
    expect(r.items.slice(0, 3).every((c) => c.status !== "coming_soon")).toBe(true); // real courses first
    expect((await q({ page: 11 })).items).toHaveLength(10);
    expect((await q({ page: 99 })).page).toBe(11);
  });

  it("filters (AND across facets, OR inside one) with live facet counts", async () => {
    const base = await q({ filters: { band: ["g10_12"] } });
    expect(base.total).toBe(30);
    const maths = await q({ filters: { band: ["g10_12"], subject: ["Toán"] } });
    expect(maths.total).toBeGreaterThan(3);
    expect(maths.items.every((c) => c.subject === "Toán" && c.age_band === "g10_12")).toBe(true);
    // the subject facet ignores its own filter, so siblings stay visible
    const subj = Object.fromEntries(maths.facets.subject.map((o) => [o.v, o.n]));
    expect(subj["Toán"]).toBe(maths.total);
    expect(subj["Vật lí"]).toBeGreaterThan(0);
    // other facets follow the subject filter
    expect(maths.facets.status.find((o) => o.v === "coming_soon")!.n).toBe(maths.total);
    const two = await q({ filters: { band: ["g10_12"], level: ["basic", "advanced"] } });
    expect(two.total).toBe(base.facets.level.filter((o) => o.v !== "intermediate").reduce((n, o) => n + o.n, 0));
    expect((await q({ filters: { language: ["en"] } })).items.every((c) => c.language === "en")).toBe(true);
    expect((await q({ filters: { status: ["live"] } })).total).toBe(3);
  });

  it("duration buckets come from est_minutes", async () => {
    const all = await q({ page_size: 50, sort: "dur", dir: "asc" });
    const short = await q({ filters: { duration: ["short"] }, page_size: 50 });
    const medium = await q({ filters: { duration: ["medium"] }, page_size: 50 });
    const long = await q({ filters: { duration: ["long"] }, page_size: 50 });
    expect(short.items.every((c) => c.est_minutes < 60)).toBe(true);
    expect(medium.items.every((c) => c.est_minutes >= 60 && c.est_minutes <= 180)).toBe(true);
    expect(long.items.every((c) => c.est_minutes > 180)).toBe(true);
    expect(short.total + medium.total + long.total).toBe(110);
    const mins = all.items.map((c) => c.est_minutes);
    expect(mins).toEqual([...mins].sort((a, b) => a - b));
    const desc = (await q({ page_size: 50, sort: "dur", dir: "desc" })).items.map((c) => c.est_minutes);
    expect(desc).toEqual([...desc].sort((a, b) => b - a));
  });

  it("sorts by popularity (students) and newest", async () => {
    const pop = await q({ sort: "pop" });
    expect(pop.items[0].students).toBeGreaterThanOrEqual(pop.items[1].students);
    expect(pop.items[0].students).toBe(412);
    const fresh = await q({ sort: "new" });
    expect(fresh.items[0].status).not.toBe("coming_soon");
  });

  it("matches without accents and by teacher or subject", async () => {
    const a = await q({ q: "TÍCH PHÂN" });
    const b = await q({ q: "tich phan" });
    expect(a.items.map((c) => c.id)).toEqual(b.items.map((c) => c.id));
    expect(a.total).toBeGreaterThan(0);
    expect(a.items[0].title.toLowerCase()).toContain("tích phân");
    expect((await q({ q: "quang" })).items.some((c) => c.teacher_name.includes("Quang"))).toBe(true);
    expect((await q({ q: "english" })).items.every((c) => c.language === "en")).toBe(true);
  });

  it("suggests 'did you mean' for typos, not for half-typed words", async () => {
    expect((await q({ q: "tich phna" })).did_you_mean).toContain("phân");
    expect((await q({ q: "ilets" })).did_you_mean).toBe("ielts");
    expect((await q({ q: "tích ph" })).did_you_mean).toBeNull();
    const s = await api.suggest("t", "toan");
    expect(s.subjects).toContain("Toán");
    expect(s.courses.length).toBeGreaterThan(0);
    expect((await api.suggest("t", "tich phna")).did_you_mean).toBeTruthy();
  });

  it("every course has a level", async () => {
    const r = await q({ page_size: 50 });
    expect(r.items.every((c) => c.level)).toBe(true);
    expect((await q({ filters: { status: ["live"] } })).items.map((c) => c.level).sort()).toEqual(["advanced", "basic", "intermediate"]);
  });
});

// ------------------------------------------------------------------ the screen, upper secondary
describe("catalog screen (thpt)", () => {
  it("shows 10 cards with tags, the student's band as a chip, a count and an always visible pager", async () => {
    seed(THPT, "g10_12");
    open("/khoa-hoc/tim-kiem");
    await waitFor(() => expect(cards()).toHaveLength(10));
    expect(screen.getByTestId("active-chips")).toHaveTextContent("Cấp học: THPT");
    expect(screen.getByText("30 khóa")).toBeInTheDocument();
    const first = cards()[0];
    expect(within(first).getByTestId("course-tags")).toHaveTextContent(/Vật lí|Toán|Tiếng Anh|Ngữ văn|Tin học|Hóa học|Sinh học/);
    expect(first.textContent).toMatch(/học sinh đang học/); // the live course comes first
    expect(cards().some((c) => /Sắp có/.test(c.textContent ?? ""))).toBe(true);
    const pager = screen.getByRole("navigation", { name: "Trang" });
    expect(within(pager).getByRole("button", { name: "Trang trước" })).toBeDisabled();
    expect(within(pager).getByRole("button", { name: "Trang 1" })).toHaveAttribute("aria-current", "page");
    expect(within(pager).getByRole("button", { name: "Trang 3" })).toBeInTheDocument();
    expect(within(pager).getByRole("button", { name: "Trang sau" })).toBeEnabled();
    // sort tabs, grid/list toggle
    expect(screen.getByRole("button", { name: "Liên quan" })).toHaveAttribute("aria-pressed", "true");
    for (const n of ["Mới nhất", "Phổ biến"]) expect(screen.getByRole("button", { name: n })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Thời lượng/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dạng danh sách" })).toBeInTheDocument();
  });

  it("an English course shows the EN badge, and every card shows the difficulty word", async () => {
    seed(THPT, "g10_12");
    open("/khoa-hoc/tim-kiem?q=ielts");
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    expect(within(cards()[0]).getByText("EN")).toBeInTheDocument();
    expect(within(cards()[0]).getByTestId("course-tags").querySelector("[data-level]")).not.toBeNull();
  });

  it("page 2 starts at item 11, scrolls under the sticky bar and moves focus to it", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/khoa-hoc/tim-kiem");
    await waitFor(() => expect(cards()).toHaveLength(10));
    const p1 = titles();
    const user = { id: "u-hs", age_band: "g10_12" } as User;
    const all = await makeMockCourseApi(() => user).queryCatalog("t", { filters: { band: ["g10_12"] }, page_size: 50 });
    expect(p1).toEqual(all.items.slice(0, 10).map((c) => c.title));
    await ui.click(screen.getByRole("button", { name: "Trang 2" }));
    await waitFor(() => expect(titles()[0]).toBe(all.items[10].title));
    expect(titles()).toEqual(all.items.slice(10, 20).map((c) => c.title));
    await waitFor(() => expect(document.activeElement).toBe(cards()[0]));
    expect(scrolled.at(-1)).toBe(cards()[0]);
    expect(screen.getByRole("button", { name: "Trang 2" })).toHaveAttribute("aria-current", "page");
    expect(where()).toContain("page=2");
    // last page: the next chevron is dimmed
    await ui.click(screen.getByRole("button", { name: "Trang 3" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Trang sau" })).toBeDisabled());
  });

  it("changing a filter or the sort resets to page 1; chips remove filters; 'Xóa tất cả' clears them", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/khoa-hoc/tim-kiem?page=2");
    await waitFor(() => expect(screen.getByRole("button", { name: "Trang 2" })).toHaveAttribute("aria-current", "page"));
    await ui.click(screen.getByRole("button", { name: "Phổ biến" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Trang 1" })).toHaveAttribute("aria-current", "page"));
    expect(where()).toContain("sort=pop");
    expect(where()).not.toContain("page=");

    const subject = document.querySelector('[data-facet="subject"]') as HTMLElement;
    const box = within(subject).getAllByRole("checkbox")[0];
    await ui.click(box);
    await waitFor(() => expect(screen.getByTestId("active-chips").querySelectorAll(".chip:not(.clear)")).toHaveLength(2));
    expect(screen.getByRole("button", { name: "Xóa tất cả" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Trang 1" })).toHaveAttribute("aria-current", "page");

    await ui.click(screen.getByRole("button", { name: "Xóa tất cả" }));
    await waitFor(() => expect(screen.getByText("110 khóa")).toBeInTheDocument()); // the band chip went too
    expect(where()).toContain("band=all");

    await ui.click(screen.getByRole("button", { name: "Trang 4" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Trang 4" })).toHaveAttribute("aria-current", "page"));
  });

  it("the pager stays on screen with a single page", async () => {
    seed(THPT, "g10_12");
    open("/khoa-hoc/tim-kiem?q=bayes&band=all");
    await waitFor(() => expect(cards()).toHaveLength(1));
    const pager = screen.getByRole("navigation", { name: "Trang" });
    expect(within(pager).getByRole("button", { name: "Trang 1" })).toHaveAttribute("aria-current", "page");
    expect(within(pager).getByRole("button", { name: "Trang trước" })).toBeDisabled();
    expect(within(pager).getByRole("button", { name: "Trang sau" })).toBeDisabled();
  });

  it("no results: one-tap 'Bỏ lọc ... (+N)' chips and related subjects", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/khoa-hoc/tim-kiem?q=tich+phan&band=g6_9");
    const few = await screen.findByTestId("few-results");
    expect(few).toHaveTextContent("Không có khóa nào khớp");
    const gain = await within(few).findByRole("button", { name: /^Bỏ lọc Cấp học: ?THCS \(\+\d+\)$|^Bỏ lọc THCS \(\+\d+\)$/ });
    expect(await within(few).findByText("Môn học liên quan")).toBeInTheDocument();
    await ui.click(gain);
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    expect(where()).not.toContain("band=g6_9");
  });

  it("a typo offers 'Có phải bạn muốn tìm', one tap runs the corrected search", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/khoa-hoc/tim-kiem?q=tich+phna&band=all");
    const few = await screen.findByTestId("few-results");
    const hint = await within(few).findByRole("button", { name: /phân/ });
    await ui.click(hint);
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    expect(decodeURIComponent(where()).replaceAll("+", " ")).toContain("q=tích phân");
  });

  it("autocomplete: recent searches (removable, per user) and 'Tìm nhiều'; typing groups courses, subjects, teachers with bold matches", async () => {
    seed(THPT, "g10_12");
    localStorage.setItem("mentor.recentSearches.u-hs", JSON.stringify(["python", "vật lí 12"]));
    const ui = userEvent.setup();
    open("/khoa-hoc/tim-kiem");
    await waitFor(() => expect(cards()).toHaveLength(10));
    const input = screen.getByRole("searchbox", { name: "Tìm khóa học" });
    await ui.click(input);
    expect(await screen.findByText("Tìm gần đây")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "python" })).toBeInTheDocument();
    expect(screen.getByText("Tìm nhiều")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Xóa “python” khỏi tìm gần đây" }));
    expect(screen.queryByRole("button", { name: "python" })).toBeNull();
    expect(JSON.parse(localStorage.getItem("mentor.recentSearches.u-hs")!)).toEqual(["vật lí 12"]);

    await ui.type(input, "toa");
    const panel = document.querySelector(".ac") as HTMLElement;
    await waitFor(() => expect(within(panel).getByText("Khóa học")).toBeInTheDocument());
    expect(within(panel).getByText("Môn học")).toBeInTheDocument();
    expect(panel.querySelector("b")?.textContent?.toLowerCase()).toBe("toá");
    // accent-insensitive: "toa" bolds "Toá" in "Toán"
    await ui.click(within(panel).getAllByRole("button", { name: /Toán/ })[0]);
    await waitFor(() => expect(where()).toMatch(/q=|subject=/));
  });

  it("a submitted search is kept as a recent search for this user only", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/khoa-hoc/tim-kiem");
    await waitFor(() => expect(cards()).toHaveLength(10));
    await ui.type(screen.getByRole("searchbox", { name: "Tìm khóa học" }), "python{Enter}");
    await waitFor(() => expect(JSON.parse(localStorage.getItem("mentor.recentSearches.u-hs") ?? "[]")).toEqual(["python"]));
    await waitFor(() => expect(where()).toContain("q=python"));
  });
});

// ------------------------------------------------------------------ phones: the filter bottom sheet
describe("filter sheet", () => {
  it("opens from 'Bộ lọc' with a badge, 'Đặt lại' and 'Áp dụng (N kết quả)'; Escape and Apply close it", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/khoa-hoc/tim-kiem");
    await waitFor(() => expect(cards()).toHaveLength(10));
    const fbtn = screen.getByRole("button", { name: /^Bộ lọc/ });
    expect(screen.queryByTestId("filter-badge")).toBeNull(); // the default band does not count
    await ui.click(fbtn);
    const sheet = await screen.findByRole("dialog", { name: "Bộ lọc" });
    expect(document.body.classList.contains("cat-sheet")).toBe(true);
    expect(within(sheet).getByRole("button", { name: "Đặt lại" })).toBeInTheDocument();
    const apply = within(sheet).getByRole("button", { name: /^Áp dụng \(30 kết quả\)$/ });
    const level = document.querySelector('[data-facet="level"]') as HTMLElement;
    await ui.click(within(level).getAllByRole("checkbox")[0]);
    await waitFor(() => expect(within(sheet).getByRole("button", { name: /^Áp dụng \((?!30 )\d+ kết quả\)$/ })).toBeInTheDocument());
    expect(screen.getByTestId("filter-badge")).toHaveTextContent("1");
    await ui.click(within(sheet).getByRole("button", { name: "Đặt lại" }));
    await waitFor(() => expect(screen.queryByTestId("filter-badge")).toBeNull());
    await ui.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.body.classList.contains("cat-sheet")).toBe(false);
    await ui.click(fbtn);
    await ui.click(await screen.findByRole("button", { name: /^Áp dụng/ }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    void apply;
  });
});

// ------------------------------------------------------------------ the kids version
describe("catalog screen (g1_5)", () => {
  it("is the simple one: big search with a mic, subject pictures, 2-column tiles, no sidebar, no sort bar", async () => {
    seed(KID, "g1_5");
    open("/khoa-hoc/tim-kiem");
    await waitFor(() => expect(cards()).toHaveLength(10));
    expect(document.querySelector("#cat")).toHaveClass("kid");
    expect(screen.getByRole("button", { name: "Nói để tìm" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Bộ lọc/ })).toBeNull();
    expect(screen.queryByRole("group", { name: "Sắp xếp" })).toBeNull();
    expect(document.querySelector(".filters")).toBeNull();
    const chips = await screen.findByTestId("kid-subjects");
    await waitFor(() => expect(within(chips).getAllByRole("button").length).toBeGreaterThan(3));
    expect(within(chips).getByRole("button", { name: "Tất cả" })).toHaveAttribute("aria-pressed", "true");
    expect(chips.querySelectorAll("img").length).toBeGreaterThan(2);
    // only primary courses; tiles keep to subject + level, with no teacher or lesson line
    expect(cards()[0].querySelector(".pt")).toBeNull();
    expect(cards()[0].querySelector(".pm")).toBeNull();
    expect(screen.getByRole("navigation", { name: "Trang" })).toBeInTheDocument();
    const ui = userEvent.setup();
    await ui.click(within(chips).getByRole("button", { name: "Toán" }));
    await waitFor(() => expect(cards().every((c) => /Toán/.test(c.querySelector(".ct-sub")?.textContent ?? ""))).toBe(true));
    expect(where()).toContain("subject=");
    // no band is ever offered to a kid
    expect(where()).not.toContain("band");
  });

  it("the mic says so when this device cannot listen", async () => {
    seed(KID, "g1_5");
    const ui = userEvent.setup();
    open("/khoa-hoc/tim-kiem");
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    await ui.click(screen.getByRole("button", { name: "Nói để tìm" }));
    await waitFor(() => expect(document.querySelector(".mic-note")).toHaveTextContent("chưa nghe được giọng nói"));
  });
});

// ------------------------------------------------------------------ back arrow, preview, tags
describe("navigation", () => {
  it("coming back from a course restores the query, filters, sort and page", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    const path = "/khoa-hoc/tim-kiem?sort=pop&subject=To%C3%A1n&level=basic&level=intermediate&view=list";
    open(path);
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getByRole("button", { name: "Phổ biến" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("button", { name: "Dạng danh sách" })).toHaveAttribute("aria-pressed", "true");
    const total = screen.getByText(/^\d+ khóa$/).textContent;
    const link = cards()[0].querySelector("a")!;
    const href = link.getAttribute("href")!;
    await ui.click(link);
    await waitFor(() => expect(where()).toContain(href));
    const back = await screen.findByRole("link", { name: "Kết quả tìm" });
    await ui.click(back);
    await waitFor(() => expect(where()).toBe(path));
    await waitFor(() => expect(screen.getByRole("button", { name: "Phổ biến" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("button", { name: "Dạng danh sách" })).toHaveAttribute("aria-pressed", "true");
    const chips = screen.getByTestId("active-chips").textContent;
    expect(chips).toContain("Môn học: Toán");
    expect(chips).toContain("Độ khó: Cơ bản");
    expect(chips).toContain("Độ khó: Trung bình");
    await waitFor(() => expect(screen.getByText(/^\d+ khóa$/).textContent).toBe(total));
  });

  it("a deep page survives the round trip", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/khoa-hoc/tim-kiem?page=2");
    await waitFor(() => expect(screen.getByRole("button", { name: "Trang 2" })).toHaveAttribute("aria-current", "page"));
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
    await ui.click(cards()[0].querySelector("a")!);
    await ui.click(await screen.findByRole("link", { name: "Kết quả tìm" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Trang 2" })).toHaveAttribute("aria-current", "page"));
    expect(where()).toContain("page=2");
  });

  it("'Khóa học khác' previews 4 courses with tags and 'Xem tất cả' opens the catalog", async () => {
    seed(THPT, "g10_12");
    const ui = userEvent.setup();
    open("/khoa-hoc");
    const more = await waitFor(() => {
      const el = document.querySelector('[data-guide="more-courses"]') as HTMLElement | null;
      expect(el).not.toBeNull();
      return el!;
    });
    expect(more.querySelectorAll("li")).toHaveLength(4);
    expect(more.querySelectorAll('[data-testid="course-tags"]')).toHaveLength(4);
    await ui.click(within(more).getByRole("link", { name: /Xem tất cả/ }));
    await waitFor(() => expect(cards()).toHaveLength(10));
    expect(where()).toBe("/khoa-hoc/tim-kiem");
  });

  it("the coming-soon course page shows the tags", async () => {
    seed(THPT, "g10_12");
    const c = SOON.find((x) => x.meta.id === "ph-toan-12-dao-ham-va-khao-sat-ham-so")!;
    open(`/khoa-hoc/${c.meta.id}`);
    const tags = await screen.findByTestId("course-tags");
    expect(tags).toHaveTextContent("Toán");
    expect(tags).toHaveTextContent("Tiếng Việt");
    expect(tags).toHaveTextContent(c.meta.level === "advanced" ? "Nâng cao" : c.meta.level === "basic" ? "Cơ bản" : "Trung bình");
    expect(tags.querySelectorAll(".bars i.on").length).toBeGreaterThan(0);
  });
});
