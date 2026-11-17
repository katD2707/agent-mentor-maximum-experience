import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "./i18n";
import { App } from "./App";
import { AuthProvider } from "./state/auth";

describe("player for the little ones", () => {
  it("checks from the bottom bar and offers 'Tiếp tục' with a green band after a correct answer", async () => {
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
      await ui.click(await screen.findByRole("button", { name: "Tiếp tục" }));
    }
    for (let n = 1; n <= 5; n++) await ui.click(await screen.findByRole("button", { name: `Đã chạm: ${n}` }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Chính xác!")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Tiếp tục" })).toBeInTheDocument();
  }, 20000);
});

describe("stepped lesson player", () => {
  it("one step per screen: check, red band with the right answer, review count, then leave", async () => {
    await i18n.changeLanguage("vi");
    localStorage.setItem(
      "mentor.mock.users",
      JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: "g10_12", birth_year: 2009, language: "vi", theme: "system", quiet_until: null } } }),
    );
    localStorage.setItem("mentor.token", "mock-u-hs");
    const ui = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/", { pathname: "/khoa-hoc/vat-li-11-dien-truong/hoc", search: "?lesson=l1", state: { back: "/" } }]} initialIndex={1}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>,
    );
    await ui.click(await screen.findByRole("button", { name: "Tiếp tục" })); // the text step
    const check = await screen.findByRole("button", { name: "Kiểm tra" });
    expect(check).toBeDisabled();
    await ui.click(await screen.findByRole("button", { name: /Hút nhau/ }));
    await ui.click(check);
    expect(await screen.findByText("Chưa đúng")).toBeInTheDocument();
    expect(screen.getByText(/Đáp án B: Đẩy nhau/)).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));
    // the missed item comes back once
    await ui.click(await screen.findByRole("button", { name: /Đẩy nhau/ }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Chính xác!")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));
    expect(await screen.findByRole("heading", { name: "Xong bài 1!" })).toBeInTheDocument();
    expect(screen.getByText("0/1")).toBeInTheDocument();
    expect(screen.getByText("Câu sai: ôn lại sau 2 ngày.")).toBeInTheDocument();
  }, 20000);
});

describe("stepped lesson: tiles, pairs, order, drag diagram, recall", () => {
  it("every new kind is answered by tapping and graded by the bottom bar; the diagram needs its target; forgotten ideas count under Ôn lại", async () => {
    await i18n.changeLanguage("vi");
    localStorage.setItem(
      "mentor.mock.users",
      JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: "g10_12", birth_year: 2009, language: "vi", theme: "system", quiet_until: null } } }),
    );
    localStorage.setItem("mentor.token", "mock-u-hs");
    const ui = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/", { pathname: "/khoa-hoc/vat-li-11-dien-truong/hoc", search: "?lesson=l4", state: { back: "/" } }]} initialIndex={1}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>,
    );
    await ui.click(await screen.findByRole("button", { name: "Tiếp tục" })); // Mực's text step

    // FILL_TILES: tap a tile into the gap
    expect(await screen.findByText("Điền chỗ trống")).toBeInTheDocument();
    const check = screen.getByRole("button", { name: "Kiểm tra" });
    expect(check).toBeDisabled();
    await ui.click(screen.getByRole("button", { name: "r" }));
    await ui.click(check);
    expect(await screen.findByText("Chưa đúng")).toBeInTheDocument();
    expect(screen.getByText(/Đáp án: r²/)).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));

    // MATCH_PAIRS: tap left then right; a wrong match is a slip, the right ones lock
    await ui.click(await screen.findByRole("button", { name: "Cường độ E" }));
    await ui.click(screen.getByRole("button", { name: "N" })); // wrong
    await ui.click(screen.getByRole("button", { name: "V/m" }));
    await ui.click(screen.getByRole("button", { name: "Lực điện F" }));
    await ui.click(screen.getByRole("button", { name: "N" }));
    await ui.click(screen.getByRole("button", { name: "Điện tích q" }));
    await ui.click(screen.getByRole("button", { name: "C" }));
    expect(await screen.findByText("Chưa đúng")).toBeInTheDocument(); // one slip: not right on the first try
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));

    // ORDER_STEPS
    for (const name of ["Đọc đề", "Chọn công thức", "Thay số", "Ra kết quả"]) await ui.click(await screen.findByRole("button", { name }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Chính xác!")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));

    // "Kéo sơ đồ": the point starts at r = 0,10 m; Tiếp tục waits for the target (E = 1/4 at r = 0,20 m)
    const go = await screen.findByRole("button", { name: "Tiếp tục" });
    expect(go).toBeDisabled();
    const slider = screen.getByRole("slider");
    expect(slider).toHaveAttribute("aria-valuetext", expect.stringContaining("Khoảng cách 0,1 m"));
    slider.focus();
    await ui.keyboard("{ArrowRight}");
    expect(screen.getByRole("slider")).toHaveAttribute("aria-valuenow", "0.15");
    expect(go).toBeDisabled();
    await ui.keyboard("{ArrowRight}");
    expect(screen.getByRole("slider")).toHaveAttribute("aria-valuetext", expect.stringContaining("4 500 V/m"));
    expect(await screen.findByText(/Xa gấp đôi thì E còn 1\/4/)).toBeInTheDocument(); // Mực's praise
    expect(go).toBeEnabled();
    await ui.click(go);

    // "Nhớ lại": type, see the idea, mark it; the second one is not remembered
    expect(await screen.findByText("1/2")).toBeInTheDocument();
    await ui.type(screen.getByRole("textbox", { name: "Câu trả lời của em" }), "điện trường");
    await ui.click(screen.getByRole("button", { name: "Xem ý đúng" }));
    expect(screen.getByText("Điện trường")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Nhớ" }));
    expect(await screen.findByText("2/2")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Xem ý đúng" }));
    await ui.click(screen.getByRole("button", { name: "Chưa nhớ" }));
    await ui.click(await screen.findByRole("button", { name: "Tiếp tục" }));

    // the missed items come back once: the gap, then the pairs
    await ui.click(await screen.findByRole("button", { name: "r²" }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Chính xác!")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));
    for (const name of ["Cường độ E", "V/m", "Lực điện F", "N", "Điện tích q", "C"]) await ui.click(await screen.findByRole("button", { name }));
    expect(await screen.findByText(/Chính xác!|Xuất sắc!/)).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));

    // the end: 1 of 3 right at first, plus the idea not remembered
    expect(await screen.findByRole("heading", { name: /^Xong bài/ })).toBeInTheDocument();
    expect(screen.getByText("1/3")).toBeInTheDocument();
    expect(screen.getByText("3 câu")).toBeInTheDocument();
  }, 40000);
});
