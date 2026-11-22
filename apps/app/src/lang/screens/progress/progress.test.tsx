import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import i18n from "../../../i18n";
import { App } from "../../../App";
import { AuthProvider } from "../../../state/auth";

/** Progress and practice inside a course on the in-browser mock API (the village that replaced Today is tested in lang/lang.test.tsx). */

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
const SCHOOL = 2010;

beforeEach(async () => {
  await i18n.changeLanguage("vi");
});

describe("Tiến độ page (lg-09)", () => {
  it("goals and courses as rows, the week as 7 cells, the reasons in a fold, home goes to the village", async () => {
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["today", "progress"]));
    seed(SCHOOL);
    open("/tien-do");
    expect(await screen.findByRole("heading", { name: "Mục tiêu" })).toBeInTheDocument();
    const week = await screen.findByLabelText("Lịch 7 ngày do Mentor xếp");
    expect(week.children).toHaveLength(7);
    expect(await screen.findByText("Vì sao xếp thế này")).toBeInTheDocument();
    const course = await screen.findAllByRole("link", { name: /Vật lí 11: Điện trường/ });
    for (const l of course) expect(l).toHaveAttribute("href", "/khoa-hoc/vat-li-11-dien-truong");
    expect(screen.getByRole("link", { name: "Về làng" })).toHaveAttribute("href", "/");
  });
});
