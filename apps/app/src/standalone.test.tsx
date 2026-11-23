import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "./i18n";
import { App } from "./App";
import { AuthProvider } from "./state/auth";
import { ApiError } from "./api";
import { API_BASE, initApiBase } from "./api/http";

const register = vi.hoisted(() => vi.fn());

vi.mock("./api", async (orig) => {
  const m = await orig<typeof import("./api")>();
  return {
    ...m,
    api: {
      ...m.api,
      signupEnabled: async () => true,
      register: async (u: string, p: string, r: "student" | "teacher") => {
        register(u, p, r);
        if (u === "taken") throw new m.ApiError(409, "username_taken");
        return m.api.login("hocsinh", "123456", r);
      },
    },
  };
});

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
  invoke.mockReset();
  register.mockReset();
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

describe("local sign-up (self-contained package)", () => {
  it("offers Tạo tài khoản, checks the password length, and signs the new user in", async () => {
    await i18n.changeLanguage("vi");
    const ui = userEvent.setup();
    renderApp();
    await ui.click(await screen.findByRole("button", { name: "Tạo tài khoản" }));
    expect(screen.getByRole("heading", { name: "Tạo tài khoản" })).toBeInTheDocument();

    await ui.type(screen.getByLabelText("Tài khoản"), "lan.nguyen");
    await ui.type(screen.getByLabelText("Mật khẩu"), "123");
    await ui.click(screen.getAllByRole("button", { name: "Tạo tài khoản" }).find((b) => b.getAttribute("type") === "submit")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Mật khẩu cần ít nhất 6 ký tự.");
    expect(register).not.toHaveBeenCalled();

    await ui.type(screen.getByLabelText("Mật khẩu"), "456");
    await ui.click(screen.getAllByRole("button", { name: "Tạo tài khoản" }).find((b) => b.getAttribute("type") === "submit")!);
    await waitFor(() => expect(register).toHaveBeenCalledWith("lan.nguyen", "123456", "student"));
    await waitFor(() => expect(screen.queryByRole("radiogroup")).toBeNull()); // past the login screen
  });

  it("says when the name is taken and can go back to logging in", async () => {
    await i18n.changeLanguage("vi");
    const ui = userEvent.setup();
    renderApp();
    await ui.click(await screen.findByRole("button", { name: "Tạo tài khoản" }));
    await ui.type(screen.getByLabelText("Tài khoản"), "taken");
    await ui.type(screen.getByLabelText("Mật khẩu"), "matkhau");
    await ui.click(screen.getAllByRole("button", { name: "Tạo tài khoản" }).find((b) => b.getAttribute("type") === "submit")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Tên này có người dùng rồi");
    expect(new ApiError(409, "username_taken").code).toBe("username_taken");
    await ui.click(screen.getByRole("button", { name: "Đăng nhập" }));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("heading", { name: "Đăng nhập" })).toBeInTheDocument();
  });
});

describe("API base from the desktop shell", () => {
  it("is left alone in a browser", async () => {
    const before = API_BASE;
    expect(await initApiBase()).toBe(false);
    expect(invoke).not.toHaveBeenCalled();
    expect(API_BASE).toBe(before);
  });

  it("takes the gateway address the shell reports, and keeps VITE_API_BASE when the shell has none", async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    const before = API_BASE;
    invoke.mockResolvedValueOnce(null);
    expect(await initApiBase()).toBe(false);
    expect(API_BASE).toBe(before);
    invoke.mockRejectedValueOnce("Command gateway_base not found");
    expect(await initApiBase()).toBe(false);
    invoke.mockResolvedValueOnce("http://127.0.0.1:50123/");
    expect(await initApiBase()).toBe(true);
    expect(invoke).toHaveBeenLastCalledWith("gateway_base");
    expect((await import("./api/http")).API_BASE).toBe("http://127.0.0.1:50123/api");
  });

  it("fails loudly when the gateway did not start", async () => {
    (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    invoke.mockRejectedValueOnce("the gateway did not answer in time");
    await expect(initApiBase()).rejects.toThrow("did not answer");
  });
});
