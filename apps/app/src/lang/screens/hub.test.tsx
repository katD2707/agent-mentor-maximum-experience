import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "../../i18n";
import { App } from "../../App";
import { AuthProvider } from "../../state/auth";
import { TEACHER_UNVERIFIED_EVENT } from "../../api/http";
import { slugName } from "./LoginHub";

/** The mock API in its hub flavour (CONTRACTS-HUB): see mockHubOn in api/mock.ts. */
function hubApp() {
  localStorage.setItem("mentor.mock.hub", "1");
  return render(
    <MemoryRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}
const submitBtn = (name: string) => screen.getAllByRole("button", { name }).find((b) => b.getAttribute("type") === "submit")!;

async function logIn(ui: ReturnType<typeof userEvent.setup>, who: string, pw = "123456") {
  await ui.type(await screen.findByLabelText("Tên đăng nhập hoặc email"), who);
  await ui.type(screen.getByLabelText("Mật khẩu"), pw);
  await ui.click(submitBtn("Đăng nhập"));
}

beforeEach(async () => {
  localStorage.clear();
  await i18n.changeLanguage("vi");
});
afterEach(() => localStorage.clear());

describe("login with the hub on", () => {
  it("has no role cards: one box for username or email, and a wrong password says so", async () => {
    const ui = userEvent.setup();
    hubApp();
    await screen.findByLabelText("Tên đăng nhập hoặc email");
    expect(screen.queryByRole("radiogroup")).toBeNull();
    await ui.click(submitBtn("Đăng nhập"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Điền đủ các ô.");
    await logIn(ui, "hocsinh", "sai-mat-khau");
    expect(await screen.findByRole("alert")).toHaveTextContent("Sai tên đăng nhập hoặc mật khẩu.");
  });

  it("logs a student in by username, and a teacher in by email", async () => {
    const ui = userEvent.setup();
    hubApp();
    await logIn(ui, "giaovien@gmail.com");
    // a teacher without a hub status counts as verified: the teacher home, not the gate
    expect(await screen.findByRole("heading", { name: /Thả bài|Drop/ })).toBeInTheDocument();
  });

  it("sign-up: role cards, then the student form with grade buttons; the username follows the name; no parent email asks first", async () => {
    const ui = userEvent.setup();
    hubApp();
    await ui.click(await screen.findByRole("button", { name: "Tạo tài khoản" }));
    expect(screen.getByRole("heading", { name: "Tạo tài khoản" })).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Em là học sinh" }));

    await ui.type(screen.getByLabelText("Tên của em"), "Nguyễn Đào");
    expect(screen.getByLabelText("Tên đăng nhập (sửa được)")).toHaveValue("nguyendao");
    await ui.type(screen.getByLabelText("Mật khẩu"), "123");
    await ui.click(submitBtn("Tạo tài khoản"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Mật khẩu ít nhất 6 ký tự.");
    await ui.type(screen.getByLabelText("Mật khẩu"), "456");
    await ui.click(submitBtn("Tạo tài khoản"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Chọn lớp của em.");

    expect(screen.getAllByRole("radio")).toHaveLength(13); // 1 to 12 and Đại học
    await ui.click(screen.getByRole("radio", { name: "5" }));
    await ui.click(submitBtn("Tạo tài khoản"));
    // the parent email is optional, but the child is told what it is for first
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("quên mật khẩu phải nhờ thầy cô");
    await ui.click(screen.getByRole("button", { name: "Bỏ qua" }));
    await waitFor(() => expect(screen.queryByLabelText("Tên của em")).toBeNull()); // signed in, past the login screen
  });

  it("says when the username or the email is taken", async () => {
    const ui = userEvent.setup();
    hubApp();
    await ui.click(await screen.findByRole("button", { name: "Tạo tài khoản" }));
    await ui.click(screen.getByRole("button", { name: "Tôi là giáo viên" }));
    await ui.type(screen.getByLabelText("Email"), "giaovien@gmail.com");
    await ui.type(screen.getByLabelText("Tên đăng nhập"), "ten.moi");
    await ui.type(screen.getByLabelText("Tên hiển thị"), "Cô Mới");
    await ui.type(screen.getByLabelText("Mật khẩu"), "123456");
    await ui.click(submitBtn("Tạo tài khoản"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Email này đã có tài khoản");

    await ui.clear(screen.getByLabelText("Email"));
    await ui.type(screen.getByLabelText("Email"), "moi@truong.edu.vn");
    await ui.clear(screen.getByLabelText("Tên đăng nhập"));
    await ui.type(screen.getByLabelText("Tên đăng nhập"), "hocsinh");
    await ui.click(submitBtn("Tạo tài khoản"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Tên đăng nhập đã có.");
  });

  it("a new teacher lands on the gate, which says to open the email; Đăng xuất goes back to login", async () => {
    const ui = userEvent.setup();
    hubApp();
    await ui.click(await screen.findByRole("button", { name: "Tạo tài khoản" }));
    await ui.click(screen.getByRole("button", { name: "Tôi là giáo viên" }));
    await ui.type(screen.getByLabelText("Email"), "co.hang@truong.edu.vn");
    await ui.type(screen.getByLabelText("Tên đăng nhập"), "co.hang");
    await ui.type(screen.getByLabelText("Tên hiển thị"), "Cô Hằng");
    await ui.type(screen.getByLabelText("Mật khẩu"), "123456");
    await ui.click(submitBtn("Tạo tài khoản"));
    expect(await screen.findByRole("heading", { name: "Mở email, bấm vào link để kê khai hồ sơ" })).toBeInTheDocument();
    expect(screen.getByText("co.hang@truong.edu.vn")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Gửi lại email" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Đã gửi lại.");
    expect(screen.queryByRole("heading", { name: /Thả bài/ })).toBeNull(); // no course page behind the gate
    await ui.click(screen.getByRole("button", { name: "Đăng xuất" }));
    expect(await screen.findByLabelText("Tên đăng nhập hoặc email")).toBeInTheDocument();
  });

  it("forgot password: no email on record goes to a request for the teachers; an email gets the code path", async () => {
    const ui = userEvent.setup();
    hubApp();
    await ui.click(await screen.findByRole("button", { name: "Quên mật khẩu?" }));
    await ui.type(screen.getByLabelText("Tên đăng nhập hoặc email"), "hocsinh");
    await ui.click(submitBtn("Gửi mã"));
    expect(await screen.findByRole("heading", { name: "Tài khoản này chưa có email" })).toBeInTheDocument();
    await ui.type(screen.getByLabelText(/Số điện thoại bố mẹ/), "abc");
    await ui.click(submitBtn("Gửi yêu cầu đặt lại"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Số điện thoại chưa đúng.");
    await ui.clear(screen.getByLabelText(/Số điện thoại bố mẹ/));
    await ui.type(screen.getByLabelText(/Số điện thoại bố mẹ/), "0901234567");
    await ui.click(submitBtn("Gửi yêu cầu đặt lại"));
    expect(await screen.findByRole("heading", { name: /Thầy cô sẽ liên hệ bố mẹ em/ })).toBeInTheDocument();
    await ui.click(submitBtn("Về đăng nhập"));

    await ui.click(await screen.findByRole("button", { name: "Quên mật khẩu?" }));
    await ui.type(screen.getByLabelText("Tên đăng nhập hoặc email"), "giaovien");
    await ui.click(submitBtn("Gửi mã"));
    expect(await screen.findByText("g•••@gmail.com")).toBeInTheDocument();
    await ui.click(screen.getByLabelText("Số 1"));
    await ui.paste("111111");
    await ui.type(screen.getByLabelText("Mật khẩu mới"), "matkhaumoi");
    await ui.click(submitBtn("Đổi mật khẩu"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Mã chưa đúng.");
    await ui.click(screen.getByLabelText("Số 1"));
    await ui.paste("482913");
    await ui.click(submitBtn("Đổi mật khẩu"));
    expect(await screen.findByRole("status")).toHaveTextContent("Đã đổi mật khẩu. Đăng nhập nhé.");
    expect(screen.getByLabelText("Tên đăng nhập hoặc email")).toHaveValue("giaovien"); // kept for the new password
    await ui.type(screen.getByLabelText("Mật khẩu"), "matkhaumoi");
    await ui.click(submitBtn("Đăng nhập"));
    expect(await screen.findByRole("heading", { name: /Thả bài|Drop/ })).toBeInTheDocument();
  });
});

describe("teacher gate", () => {
  it("chờ duyệt: only says so; Đăng xuất is there", async () => {
    const ui = userEvent.setup();
    hubApp();
    await logIn(ui, "gv-cho");
    expect(await screen.findByRole("heading", { name: "Đang chờ duyệt hồ sơ" })).toBeInTheDocument();
    expect(screen.getByText("Có thể đóng app.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đăng xuất" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Thả bài/ })).toBeNull();
  });

  it("từ chối: shows the reason; Nộp lại hồ sơ asks for the form link again", async () => {
    const ui = userEvent.setup();
    hubApp();
    await logIn(ui, "gv-tuchoi");
    expect(await screen.findByRole("heading", { name: "Hồ sơ bị từ chối" })).toBeInTheDocument();
    expect(await screen.findByText("Ảnh chứng chỉ mờ, không đọc được số.")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Nộp lại hồ sơ" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Đã gửi link kê khai vào email");
  });

  it("đã duyệt: six boxes; a wrong code is refused; the right one opens the teacher home", async () => {
    const ui = userEvent.setup();
    hubApp();
    await logIn(ui, "gv-duyet");
    expect(await screen.findByText("binh.gv@gmail.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Gửi lại mã" })).toBeInTheDocument();
    await ui.click(screen.getByLabelText("Số 1"));
    await ui.paste("123456");
    await ui.click(submitBtn("Xác nhận"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Mã chưa đúng.");
    await ui.click(screen.getByLabelText("Số 1"));
    await ui.paste("482913");
    await ui.click(submitBtn("Xác nhận"));
    expect(await screen.findByRole("heading", { name: /Thả bài|Drop/ })).toBeInTheDocument();
  });

  it("a 403 teacher_unverified in the middle of a session shows the gate", async () => {
    const ui = userEvent.setup();
    hubApp();
    await logIn(ui, "gv-xacminh");
    expect(await screen.findByRole("heading", { name: /Thả bài|Drop/ })).toBeInTheDocument();
    // the owner pulled the approval: the hub now says cho_duyet
    const db = { "gv-xacminh": { password: "123456", user: { id: "u-gv5", role: "teacher", username: "gv-xacminh", display_name: "Cô Mai", age_band: null, birth_year: null, language: "vi", theme: "system", quiet_until: null, email: "mai.gv@gmail.com", teacher_status: "cho_duyet" } } };
    localStorage.setItem("mentor.mock.users", JSON.stringify(db));
    act(() => {
      window.dispatchEvent(new Event(TEACHER_UNVERIFIED_EVENT));
    });
    expect(await screen.findByRole("heading", { name: "Đang chờ duyệt hồ sơ" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Thả bài/ })).toBeNull();
  });
});

describe("slugName", () => {
  it("drops accents, spaces and symbols", () => {
    expect(slugName("Nguyễn Đào")).toBe("nguyendao");
    expect(slugName("Lan 7A!")).toBe("lan7a");
  });
});
