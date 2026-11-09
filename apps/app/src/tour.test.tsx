import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import "@mentor/mentor-mascot/mascot.js";
import type { MentorMascot } from "@mentor/mentor-mascot/mascot";
import i18n from "./i18n";
import { App } from "./App";
import { AuthProvider } from "./state/auth";
import { GUIDES } from "./lib/guides";
import { MAX_STEPS, TOUR_KEYS, hasSeen, markSeen, resetSeen, tourScreen, tourSteps } from "./lib/tours";

/** jsdom lays nothing out: give every data-guide area (except `hide`) a box on screen, stacked down the page. */
function layout(hide: string[] = []) {
  const orig = Element.prototype.getBoundingClientRect;
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    const key = this instanceof HTMLElement ? this.dataset.guide : undefined;
    if (!key) return orig.call(this);
    if (hide.includes(key)) return new DOMRect(0, 0, 0, 0);
    const i = Array.from(document.querySelectorAll("[data-guide]")).indexOf(this);
    return new DOMRect(40, 90 + (i % 6) * 100, 400, 80);
  });
}
const shadow = () => (document.querySelector("mentor-mascot") as MentorMascot).shadowRoot!;
const bubble = () => shadow().querySelector<HTMLElement>(".bubble");
const okBtn = () => shadow().querySelector<HTMLButtonElement>(".bubble .ok")!;

afterEach(() => {
  vi.restoreAllMocks();
  document.documentElement.style.overflow = "";
  document.body.replaceChildren(); // a mascot mounted by hand is not React's to clean up
});

describe("tours: which screen, which steps", () => {
  it("maps routes to tours for students, teachers and the login screen", () => {
    expect(tourScreen("/", null)).toBe("login");
    expect(tourScreen("/", "student")).toBe("hub");
    expect(tourScreen("/khoa-hoc", "student")).toBe("courses");
    expect(tourScreen("/khoa-hoc/tim-kiem", "student")).toBe("course-search");
    expect(tourScreen("/khoa-hoc/c1", "student")).toBe("course");
    expect(tourScreen("/khoa-hoc/c1/hoc", "student")).toBe("player");
    expect(tourScreen("/luyen-tap", "student")).toBe("practice");
    expect(tourScreen("/luyen-tap/s1/cau/2", "student")).toBe("practice-run");
    expect(tourScreen("/nghien-cuu/paper/p1", "student")).toBe("research-paper");
    expect(tourScreen("/", "teacher")).toBe("gv-home");
    expect(tourScreen("/khoa/c1", "teacher")).toBe("gv-course");
    expect(tourScreen("/khoa/c1/duyet", "teacher")).toBe("gv-review");
  });

  it("every area a tour points at has Mực's explanation", () => {
    for (const k of TOUR_KEYS) expect(GUIDES[k], k).toBeDefined();
  });

  it("keeps only the areas on screen, at most three, and never a lone hello", () => {
    const all = () => true;
    expect(tourSteps("practice", false, all)).toHaveLength(MAX_STEPS);
    expect(tourSteps("practice", false, (k) => k !== "practice-resume").map((s) => s.key)).toEqual(["practice-quick", "practice-mock", "practice-courses"]);
    const hub = tourSteps("hub", false, all);
    expect(hub[0].key).toBeUndefined();
    expect(hub[0].title?.vi).toBe("Chào em, mình là Mực!");
    expect(tourSteps("hub", true, all)[0].title?.vi).toBe("Chào bạn, mình là Mực!");
    expect(tourSteps("hub", false, () => false)).toEqual([]);
    // the bubble already shows the name: "Khóa học: bài hôm nay…" becomes "Bài hôm nay…"
    expect(hub[1].text?.vi).toMatch(/^Bài hôm nay Mentor/);
    expect(hub[1].text?.en).toMatch(/^Today's lesson/);
  });

  it("remembers screens per account until reset", () => {
    markSeen("u1", "hub");
    expect(hasSeen("u1", "hub")).toBe(true);
    expect(hasSeen("u2", "hub")).toBe(false);
    markSeen("u1", "hub", false);
    expect(hasSeen("u1", "hub")).toBe(false);
    markSeen("u1", "hub");
    markSeen("u1", "progress");
    resetSeen("u1");
    expect(hasSeen("u1", "progress")).toBe(false);
  });
});

describe("<mentor-mascot> tour()", () => {
  beforeEach(() => {
    document.body.innerHTML = '<section data-guide="a">A</section><section data-guide="gone">G</section><section data-guide="b">B</section>';
    layout(["gone"]);
  });
  const mount = () => {
    const m = document.createElement("mentor-mascot") as MentorMascot;
    m.guides = { a: { vi: "Chữ A", en: "Text A" }, b: { vi: "Chữ B", en: "Text B" }, gone: { vi: "Ẩn", en: "Hidden" } };
    m.setAttribute("lang", "vi");
    document.body.append(m);
    return m;
  };

  it("goes on only with the button: outside taps and scrolling nudge, the page is locked, then all is put back", async () => {
    const m = mount();
    const done = m.tour([{ key: "a", title: { vi: "Phần A", en: "Part A" } }, { key: "gone" }, { key: "b" }]);
    await waitFor(() => expect(bubble()).toHaveTextContent("Phần A"));
    expect(bubble()).toHaveTextContent("Chữ A");
    expect(shadow().querySelector(".bubble .n")).toHaveTextContent("1/2"); // the hidden area is left out
    expect(document.documentElement.style.overflow).toBe("hidden");
    expect(okBtn()).toHaveTextContent("Hiểu rồi, tiếp");
    expect(shadow().activeElement).toBe(okBtn());

    const layer = shadow().querySelector(".catch")!;
    fireEvent.pointerDown(layer);
    fireEvent.wheel(layer);
    expect(bubble()).toHaveTextContent("Chữ A");
    expect(bubble()).toHaveClass("nudge");

    fireEvent.click(okBtn());
    await waitFor(() => expect(bubble()).toHaveTextContent("Chữ B"));
    expect(okBtn()).toHaveTextContent("Hiểu rồi");
    expect(shadow().querySelector(".skip")).toBeNull(); // last step: just the button
    fireEvent.click(okBtn());
    await expect(done).resolves.toBe("done");
    expect(shadow().querySelector(".catch, .bubble, .hl")).toBeNull();
    expect(document.documentElement.style.overflow).toBe("");
  });

  it("Skip or Escape leaves; nothing on screen means no tour", async () => {
    const m = mount();
    const first = m.tour([{ key: "a" }, { key: "b" }]);
    await waitFor(() => expect(shadow().querySelector(".skip")).toHaveTextContent("Bỏ qua"));
    fireEvent.keyDown(document, { key: "Escape" });
    await expect(first).resolves.toBe("skipped");
    expect(document.documentElement.style.overflow).toBe("");
    await waitFor(() => expect(m.tour([{ key: "gone" }])).resolves.toBe("none"));
  });
});

describe("Mực guides a new user on each new screen", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("vi");
    localStorage.setItem("mentor.mock.users", JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: null, birth_year: 2013, language: "vi", theme: "system", quiet_until: null } } }));
    localStorage.setItem("mentor.token", "mock-u-hs");
    localStorage.setItem("mentor.lang", "vi");
    layout();
  });
  const open = (path: string) =>
    render(
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>,
    );

  it("home: hello, then its parts, once; Settings shows the tours again", async () => {
    const ui = userEvent.setup();
    const view = open("/");
    await waitFor(() => expect(bubble()).toHaveTextContent("Chào em, mình là Mực!"));
    expect(shadow().querySelector(".bubble .n")).toHaveTextContent("1/3");
    fireEvent.click(okBtn());
    await waitFor(() => expect(bubble()).toHaveTextContent("Khóa học"));
    fireEvent.click(okBtn());
    await waitFor(() => expect(bubble()).toHaveTextContent("Cài đặt"));
    fireEvent.click(okBtn());
    await waitFor(() => expect(bubble()).toBeNull());
    expect(hasSeen("u-hs", "hub")).toBe(true);

    view.unmount();
    open("/");
    await screen.findByRole("button", { name: /Cài đặt/ });
    await new Promise((r) => setTimeout(r, 1600));
    expect(bubble()).toBeNull(); // seen: never twice

    markSeen("u-hs", "progress");
    await ui.click(screen.getByRole("button", { name: /Cài đặt/ }));
    await ui.click(await screen.findByRole("button", { name: "Xem lại từ đầu" }));
    await waitFor(() => expect(bubble()).toHaveTextContent("Chào em, mình là Mực!"));
    expect(hasSeen("u-hs", "progress")).toBe(false); // every screen will show its tour again
  });
});
