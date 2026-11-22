import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "./i18n";
import { App } from "./App";
import { AuthProvider } from "./state/auth";
import { needsFirstRun } from "./lib/gate";
import { quietCustom, quietUntil } from "./lib/quiet";
import type { User } from "./api";

const user = (over: Partial<User> = {}): User => ({
  id: "1", role: "student", username: "hocsinh", display_name: "Lan",
  age_band: "g6_9", birth_year: 2013, language: "vi", theme: "system", quiet_until: null, ...over,
});

function renderApp() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("login", () => {
  it("shows the role_mismatch message only after a failed attempt", async () => {
    await i18n.changeLanguage("vi");
    const ui = userEvent.setup();
    renderApp();
    await screen.findByRole("radiogroup");
    expect(screen.queryByRole("alert")).toBeNull();

    await ui.click(screen.getByRole("radio", { name: "Giáo viên" }));
    await ui.type(screen.getByLabelText("Tài khoản"), "hocsinh");
    await ui.type(screen.getByLabelText("Mật khẩu"), "123456");
    await ui.click(screen.getByRole("button", { name: "Đăng nhập" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Sai vai trò.");
  });

  it("first run: language, then a birth year picks the figure and one line, then Next to the character", async () => {
    await i18n.changeLanguage("vi");
    const ui = userEvent.setup();
    renderApp();
    await ui.click(await screen.findByRole("radio", { name: "Học sinh" }));
    await ui.type(screen.getByLabelText("Tài khoản"), "hocsinh");
    await ui.type(screen.getByLabelText("Mật khẩu"), "123456");
    await ui.click(screen.getByRole("button", { name: "Đăng nhập" }));
    await ui.click(await screen.findByRole("button", { name: /Hello/ }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "What year were you born?" })).toBeInTheDocument());

    const select = screen.getByRole("combobox", { name: "Year of birth" });
    const next = screen.getByRole("button", { name: "Next" });
    const years = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(years.slice(0, 3)).toEqual(["Year of birth", "2020", "2019"]);
    expect(years.at(-1)).toBe("1980");
    expect(document.querySelector("input[type=range], input[type=number]")).toBeNull();
    // nothing is chosen yet: Next is disabled, no figure is picked, no description
    expect(next).toBeDisabled();
    expect(document.querySelector(".lg-figs")).not.toHaveAttribute("data-pick");
    expect(document.querySelector(".lg-level")).toHaveTextContent("");

    await ui.selectOptions(select, "1999"); // the university figure, whatever today's date in 2026-2030
    expect(document.querySelector(".lg-figs")).toHaveAttribute("data-pick", "uni");
    expect(document.querySelectorAll(".lg-figs svg.on")).toHaveLength(1);
    expect(document.querySelector(".lg-level")).toHaveTextContent("University");
    // never any age, grade or "change it later" text
    expect(document.body.textContent).not.toMatch(/Settings|grade d|Grade d|years old|tuổi|lớp d/i);
    expect(next).toBeEnabled();

    await ui.click(next);
    expect(await screen.findByRole("heading", { name: "Who are you?" })).toBeInTheDocument();
  });

  it("settings shows the birth year read-only, with no band or grade chips", async () => {
    await i18n.changeLanguage("vi");
    localStorage.setItem(
      "mentor.mock.users",
      JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: "g10_12", birth_year: 2010, language: "vi", theme: "system", quiet_until: null, avatar: "nam" } } }),
    );
    localStorage.setItem("mentor.mock.lg.u-hs", JSON.stringify({ chickens: [{ id: "toan", xp: 0, taken_at: "2026-11-01T00:00:00Z" }] }));
    localStorage.setItem("mentor.token", "mock-u-hs");
    const ui = userEvent.setup();
    renderApp();
    await ui.click(await screen.findByRole("button", { name: "Cài đặt" }));
    const pop = await screen.findByRole("dialog", { name: "Cài đặt" });
    expect(pop).toHaveTextContent("Năm sinh");
    const year = within(pop).getByText("2010");
    // read-only text, not a control; no chips for grades
    expect(year.closest("button, select, input")).toBeNull();
    expect(pop).not.toHaveTextContent(/10–12|1–5|6–9|ĐH|Lớp/);
  });
});

describe("age density follows the date", () => {
  afterEach(() => vi.useRealTimers());
  it("switches by itself when the app stays open across 1 September", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2028, 7, 31, 23, 0)); // born 2010: grade 12
    localStorage.setItem(
      "mentor.mock.users",
      JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: "g10_12", birth_year: 2010, language: "vi", theme: "system", quiet_until: null } } }),
    );
    localStorage.setItem("mentor.token", "mock-u-hs");
    renderApp();
    await waitFor(() => expect(document.documentElement.dataset.age).toBe("g10_12"));
    vi.setSystemTime(new Date(2028, 8, 1, 7, 0));
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(document.documentElement.dataset.age).toBe("uni"));
  });
});

describe("first-run gating", () => {
  it("applies to students missing language or birth year, never to teachers", () => {
    expect(needsFirstRun(user({ language: null }))).toBe(true);
    expect(needsFirstRun(user({ birth_year: null, age_band: null }))).toBe(true);
    expect(needsFirstRun(user())).toBe(false);
    expect(needsFirstRun(user({ role: "teacher", birth_year: null, age_band: null, language: "vi" }))).toBe(false);
  });
});

describe("quiet options", () => {
  const now = new Date(2026, 10, 6, 15, 10); // Fri 6 Nov 2026, 15:10 local
  it("durations add minutes", () => {
    expect(new Date(quietUntil("30", now)).getTime() - now.getTime()).toBe(30 * 60000);
    expect(new Date(quietUntil("60", now)).getTime() - now.getTime()).toBe(60 * 60000);
    expect(new Date(quietUntil("120", now)).getTime() - now.getTime()).toBe(120 * 60000);
  });
  it("until tomorrow is 07:00 next day", () => {
    const d = new Date(quietUntil("tomorrow", now));
    expect([d.getDate(), d.getHours(), d.getMinutes()]).toEqual([7, 7, 0]);
  });
  it("this week ends Sunday 23:59", () => {
    const d = new Date(quietUntil("week", now));
    expect([d.getDay(), d.getDate(), d.getHours(), d.getMinutes()]).toEqual([0, 8, 23, 59]);
  });
  it("custom needs a future time", () => {
    expect(quietCustom(0, 14 * 60, now)).toBeNull();
    const d = new Date(quietCustom(1, 9 * 60 + 30, now)!);
    expect([d.getDate(), d.getHours(), d.getMinutes()]).toEqual([7, 9, 30]);
  });
});
