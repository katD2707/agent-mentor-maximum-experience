import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import i18n from "../../../i18n";
import { App } from "../../../App";
import { AuthProvider } from "../../../state/auth";
import { setPracticeApi } from "../../../api";
import { createMockPractice } from "../../../api/mock-practice-api";

const COURSE = "dev-sample-dien-truong";
const open = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );

/** Links to /kiem-tra/<course> that name what to do (`?state=thi`, `?state=luyen&level=N`) go straight to it. */
describe("Kiểm tra khóa: links that start something", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("vi");
    localStorage.setItem("mentor.mock.users", JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: "g10_12", birth_year: 2010, language: "vi", theme: "system", quiet_until: null, avatar: "nam" } } }));
    localStorage.setItem("mentor.token", "mock-u-hs");
    localStorage.setItem("mentor.lang", "vi");
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["lg-hello", "lg-village"]));
    setPracticeApi(createMockPractice({ learner: () => ({ age_band: "g10_12", language: "vi" }) }));
  });
  afterEach(() => sessionStorage.clear());

  it("?state=thi opens the mock exam's 'ready?' dialog at once", async () => {
    open(`/kiem-tra/${COURSE}?state=thi&from=chuong`);
    const dlg = await screen.findByRole("alertdialog");
    expect(within(dlg).getByRole("button", { name: "Bắt đầu" })).toBeInTheDocument();
  }, 30000);

  it("?state=luyen&level=2 starts that practice level at once", async () => {
    open(`/kiem-tra/${COURSE}?state=luyen&level=2&from=chuong`);
    expect(await screen.findByRole("heading", { name: "Luyện 5 câu" }, { timeout: 8000 })).toBeInTheDocument();
  }, 30000);

  it("a plain /kiem-tra link stays on the hub and the ladder has no 'đúng 0%' for levels nothing was answered in", async () => {
    open(`/kiem-tra/${COURSE}`);
    expect(await screen.findByRole("heading", { name: "Luyện theo mức" })).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.queryByText(/đúng 0%/)).toBeNull();
  }, 30000);
});
