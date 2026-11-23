import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import i18n from "../../i18n";
import { AiKeyPrompt, AiKeyProvider, AiKeyRow, useAiKey } from "./aiKey";
import type { AiKeyStatus } from "../../api/aikey";

const off: AiKeyStatus = { mode: "direct", configured: false, masked_key: null, base: "https://omniroute.example/v1", default_base: "https://omniroute.example/v1", models: {} };
const on: AiKeyStatus = { ...off, configured: true, masked_key: "••••1234" };
const api = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn(), test: vi.fn(), remove: vi.fn() }));

vi.mock("../../api/aikey", async (orig) => ({ ...(await orig<typeof import("../../api/aikey")>()), aiKeyApi: api }));
vi.mock("../../state/auth", () => ({ useAuth: () => ({ token: "tok" }) }));

/** An AI screen: shows the prompt instead of its feature while no key is saved. */
function Feature() {
  const { configured } = useAiKey();
  return configured === false ? <AiKeyPrompt /> : <p>chicken chat ready</p>;
}
const app = () =>
  render(
    <AiKeyProvider>
      <AiKeyRow rowClass="row" labelClass="lbl" buttonClass="btn" />
      <Feature />
    </AiKeyProvider>,
  );

beforeEach(async () => {
  Object.values(api).forEach((f) => f.mockReset());
  await i18n.changeLanguage("vi");
});

describe("Khóa AI", () => {
  it("shows the friendly prompt when no key is saved, and its button opens the dialog", async () => {
    api.get.mockResolvedValue(off);
    app();
    expect(await screen.findByText("Thêm khóa AI trong Cài đặt để dùng tính năng này")).toBeTruthy();
    expect(screen.queryByText("chicken chat ready")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Thêm khóa AI" }));
    const dlg = await screen.findByRole("dialog", { name: "Khóa AI" });
    expect(dlg.textContent).toContain("Dán khóa AI để trò chuyện với gà, hỏi bài và chụp vở.");
    expect((screen.getByLabelText("Địa chỉ") as HTMLInputElement).value).toBe(off.base);
  });

  it("does not block anything when a key is saved, or while the status is still unknown", async () => {
    api.get.mockResolvedValue(on);
    app();
    expect(screen.getByText("chicken chat ready")).toBeTruthy(); // unknown yet: go ahead
    await waitFor(() => expect(screen.getByRole("button", { name: /Đã có khóa/ })).toBeTruthy());
    expect(screen.getByText("chicken chat ready")).toBeTruthy();
    expect(screen.queryByText(/Thêm khóa AI trong Cài đặt/)).toBeNull();
  });

  it("tests, saves and shows only the masked key; the typed key is cleared", async () => {
    api.get.mockResolvedValue(off);
    api.test.mockResolvedValue({ ok: false, code: "bad_key", message: "" });
    api.save.mockResolvedValue(on);
    app();
    fireEvent.click(await screen.findByRole("button", { name: "Chưa có" }));
    const key = screen.getByLabelText("Khóa") as HTMLInputElement;
    expect(key.type).toBe("password");
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(await screen.findByText("Em dán khóa AI vào ô Khóa nhé.")).toBeTruthy(); // nothing typed: no request
    expect(api.save).not.toHaveBeenCalled();

    fireEvent.change(key, { target: { value: "sk-secret-abcdef-1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Thử" }));
    expect(await screen.findByText("Khóa AI chưa đúng. Em kiểm tra lại khóa rồi thử nhé.")).toBeTruthy();
    expect(api.test).toHaveBeenCalledWith("tok", { base: off.base, key: "sk-secret-abcdef-1234" });

    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(await screen.findByText("Đã lưu khóa AI.")).toBeTruthy();
    expect(screen.getByText("••••1234", { selector: "code" })).toBeTruthy();
    expect((screen.getByLabelText("Khóa") as HTMLInputElement).value).toBe(""); // the key is not kept in the form
    expect(document.body.innerHTML).not.toContain("sk-secret-abcdef-1234");
    expect(screen.getByText("chicken chat ready")).toBeTruthy(); // the feature is back
  });

  it("deletes the key and the prompt returns", async () => {
    api.get.mockResolvedValue(on);
    api.remove.mockResolvedValue(off);
    app();
    fireEvent.click(await screen.findByRole("button", { name: /Đã có khóa/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Xóa" }));
    expect(await screen.findByText("Đã xóa khóa AI.")).toBeTruthy();
    expect(await screen.findByText("Thêm khóa AI trong Cài đặt để dùng tính năng này")).toBeTruthy();
  });

  it("says plainly what went wrong on a network failure, never a raw error", async () => {
    api.get.mockResolvedValue(off);
    api.save.mockRejectedValue(Object.assign(new Error("x"), { code: "weird" }));
    app();
    fireEvent.click(await screen.findByRole("button", { name: "Chưa có" }));
    fireEvent.change(screen.getByLabelText("Khóa"), { target: { value: "sk-secret-abcdef-1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(await screen.findByText("Chưa lưu được. Em thử lại nhé.")).toBeTruthy();
  });

  it("has no row when a router brings the AI (hosted or dev server)", async () => {
    api.get.mockResolvedValue({ ...on, mode: "router" });
    app();
    await waitFor(() => expect(screen.queryByTestId("aikey-row")).toBeNull());
    expect(screen.getByText("chicken chat ready")).toBeTruthy();
  });
});
