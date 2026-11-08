import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "./i18n";
import { App } from "./App";
import { AuthProvider } from "./state/auth";

describe("player for the little ones", () => {
  it("shows 'Tiếp' after a correct answer (the step must redraw when the item is done)", async () => {
    await i18n.changeLanguage("vi");
    localStorage.setItem(
      "mentor.mock.users",
      JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Bi", age_band: "g1_5", birth_year: 2018, language: "vi", theme: "system", quiet_until: null } } }),
    );
    localStorage.setItem("mentor.token", "mock-u-hs");
    const ui = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/khoa-hoc/toan-1-dem-tao/hoc?lesson=l1"]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>,
    );

    // walk to the tap-to-count step
    for (let i = 0; i < 6 && !screen.queryByRole("button", { name: "Đã chạm: 1" }); i++) {
      await ui.click(await screen.findByRole("button", { name: /^Tiếp/ }));
    }
    for (let n = 1; n <= 5; n++) await ui.click(await screen.findByRole("button", { name: `Đã chạm: ${n}` }));
    await ui.click(screen.getByRole("button", { name: "Xong" }));
    expect(await screen.findByRole("button", { name: /^Tiếp/ })).toBeInTheDocument();
  }, 20000);
});
