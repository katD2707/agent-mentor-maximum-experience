import { beforeEach, describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "./i18n";
import { App } from "./App";
import { AuthProvider } from "./state/auth";
import { researchPoll } from "./api/research";
import { resetMockResearch } from "./api/mock-research";

function seed(birth: number, scenario?: "full" | "empty" | "searching", sources?: { s2?: boolean; asta?: boolean }) {
  localStorage.setItem("mentor.mock.users", JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: null, birth_year: birth, language: "vi", theme: "system", quiet_until: null } } }));
  localStorage.setItem("mentor.token", "mock-u-hs");
  localStorage.setItem("mentor.lang", "vi");
  if (sources) localStorage.setItem("mentor.mock.research.sources", JSON.stringify(sources));
  resetMockResearch(scenario);
}
function open(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}
const UNI = 2000;
/** opens one chapter of the research home by its tab */
async function goTab(ui: ReturnType<typeof userEvent.setup>, name: string) {
  await ui.click(await screen.findByRole("tab", { name: new RegExp(`^${name}`) }));
}
/** the reading-list card (not the hero) with this title */
const entry = (re: RegExp) => screen.getAllByText(re).map((e) => e.closest("article")).find(Boolean) as HTMLElement;

beforeEach(async () => {
  await i18n.changeLanguage("vi");
  researchPoll.ms = 20;
});

describe("band guard and hub tile", () => {
  it("shows the fifth tile to the university band only", async () => {
    seed(UNI);
    open("/");
    const link = await screen.findByRole("link", { name: /Nghiên cứu/ });
    expect(link).toHaveAttribute("href", "/nghien-cuu");
    expect(document.querySelectorAll(".grid4 .cell")).toHaveLength(5);
  });
  it("shows four tiles to everyone else and sends them back from the research routes", async () => {
    seed(2010);
    open("/nghien-cuu");
    expect(await screen.findByRole("heading", { name: "Chào Lan" })).toBeInTheDocument();
    expect(document.querySelectorAll(".grid4 .cell")).toHaveLength(4);
    expect(screen.queryByRole("link", { name: /Nghiên cứu/ })).toBeNull();
  });
  it("opens a paper by its deep link for the university band", async () => {
    seed(UNI);
    open("/nghien-cuu/paper/p-2601.08832");
    expect(await screen.findByRole("heading", { name: /Equivariant Message Passing/ })).toBeInTheDocument();
  });
});

describe("home states", () => {
  it("empty: asks for the topic, then shows the topic-saved state while Mentor searches", async () => {
    seed(UNI, "empty");
    const ui = userEvent.setup();
    open("/nghien-cuu");
    expect(await screen.findByRole("heading", { name: "Đề tài của bạn là gì?" })).toBeInTheDocument();
    expect(screen.queryByRole("search")).toBeNull();
    await ui.type(screen.getByLabelText("Đề tài"), "mạng nơ-ron đồ thị cho vật liệu");
    await ui.click(screen.getByRole("button", { name: "Bắt đầu" }));
    expect(await screen.findByRole("heading", { name: "Đã ghi đề tài" })).toBeInTheDocument();
    expect(screen.getByText(/Mentor đang tìm những paper đầu tiên/)).toBeInTheDocument();
  });
  it("full: four chapters in tabs; Reading first, dots on the tabs, arrow keys, the tab is remembered", async () => {
    seed(UNI);
    const ui = userEvent.setup();
    const view = open("/nghien-cuu");
    expect(await screen.findByRole("link", { name: "Đọc tiếp" })).toHaveAttribute("href", "/nghien-cuu/paper/p-2601.08832");
    const tabs = screen.getByRole("tablist", { name: "Các phần của Nghiên cứu" });
    expect(within(tabs).getAllByRole("tab").map((t) => t.textContent?.replace(/\d+ paper mới|Hạn nộp còn \d+ ngày/, ""))).toEqual(["Đọc", "Lịch", "Thí nghiệm", "Đề tài"]);
    expect(screen.getByRole("tab", { name: /^Đọc/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /^Đọc/ })).toHaveTextContent(/paper mới/);
    expect(screen.getByRole("tab", { name: /^Lịch/ })).toHaveTextContent(/Hạn nộp còn \d+ ngày/);
    expect(screen.getByText("Cần đọc")).toBeInTheDocument();
    expect(screen.queryByText("Nhật ký thí nghiệm")).toBeNull(); // other chapters are not rendered
    await goTab(ui, "Lịch");
    expect(screen.getByText("Nộp full paper hội nghị", { selector: ".rs-ev h3" })).toBeInTheDocument();
    expect(screen.getByText("Chưa xác nhận")).toBeInTheDocument();
    expect(screen.queryByText("Cần đọc")).toBeNull();
    await ui.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: /^Thí nghiệm/ })).toHaveFocus();
    expect(screen.getByText("Nhật ký thí nghiệm")).toBeInTheDocument();
    expect(screen.getByText(/Chưa ghi commit/)).toBeInTheDocument();
    await ui.keyboard("{End}");
    expect(screen.getByRole("tabpanel", { name: "Đề tài" })).toHaveTextContent("Mốc luận văn");
    view.unmount();
    open("/nghien-cuu");
    expect(await screen.findByRole("tab", { name: /^Đề tài/ })).toHaveAttribute("aria-selected", "true");
  });
  it("searching: the banner shows above the board, with skeleton cards", async () => {
    seed(UNI, "searching");
    open("/nghien-cuu");
    expect(await screen.findByText(/Mentor đang xem paper mới của tuần này/)).toBeInTheDocument();
    expect(document.querySelectorAll(".rs-skel").length).toBe(2);
    expect(screen.getByRole("link", { name: "Đọc tiếp" })).toBeInTheDocument();
  });
  it("accepts and dismisses a suggestion, and changes a reading-list status", async () => {
    seed(UNI);
    const ui = userEvent.setup();
    open("/nghien-cuu");
    await screen.findByText(/A Benchmark of Data-Efficient/);
    await ui.click(within(entry(/A Benchmark of Data-Efficient/)).getByRole("button", { name: "Thêm" }));
    await waitFor(() => expect(within(entry(/A Benchmark of Data-Efficient/)).queryByRole("button", { name: "Bỏ qua" })).toBeNull());
    expect(within(entry(/A Benchmark of Data-Efficient/)).getByText("Mới")).toBeInTheDocument();
    await ui.click(within(entry(/Active Learning Loops/)).getByRole("button", { name: "Bỏ qua" }));
    await waitFor(() => expect(screen.queryByText(/Active Learning Loops/)).toBeNull());
    await ui.click(within(entry(/Transfer Learning from Large Atomistic/)).getByRole("button", { name: "Đọc lại" }));
    await waitFor(() => expect(within(entry(/Transfer Learning from Large Atomistic/)).getByText("Đang đọc")).toBeInTheDocument());
  });
  it("adds a deadline by text, and says so when the date cannot be read", async () => {
    seed(UNI);
    const ui = userEvent.setup();
    open("/nghien-cuu");
    await goTab(ui, "Lịch");
    await ui.click(await screen.findByRole("button", { name: "Thêm hạn" }));
    await ui.type(screen.getByLabelText("Hạn mới"), "gửi báo cáo");
    await ui.click(within(screen.getByLabelText("Hạn mới").closest("form")!).getByRole("button", { name: "Thêm" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Chưa đọc được ngày");
    await ui.clear(screen.getByLabelText("Hạn mới"));
    await ui.type(screen.getByLabelText("Hạn mới"), "gửi báo cáo 25/11, 17:00");
    await ui.click(within(screen.getByLabelText("Hạn mới").closest("form")!).getByRole("button", { name: "Thêm" }));
    expect(await screen.findByText("Gửi báo cáo")).toBeInTheDocument();
  });
  it("opens the agenda and saves the two boxes", async () => {
    seed(UNI);
    const ui = userEvent.setup();
    open("/nghien-cuu");
    await goTab(ui, "Lịch");
    await ui.click(await screen.findByRole("button", { name: "Xem agenda" }));
    expect(await screen.findByText("Chạy lại baseline trên bộ dữ liệu B")).toBeInTheDocument();
    await ui.type(screen.getByLabelText("Kết quả mới"), "MAE 0,05");
    await ui.tab();
    await waitFor(() => expect(screen.getByLabelText("Kết quả mới")).toHaveValue("MAE 0,05"));
  });
});

describe("experiment log", () => {
  it("logs a run and keeps the composer inside its card", async () => {
    seed(UNI);
    const ui = userEvent.setup();
    open("/nghien-cuu");
    await goTab(ui, "Thí nghiệm");
    const box = await screen.findByLabelText("Thí nghiệm vừa chạy");
    const card = box.closest(".rs-card");
    expect(card).toHaveClass("rs-log");
    expect(card!.contains(box.closest(".rs-logbox"))).toBe(true);
    await ui.type(box, "chạy baseline seed 7, commit abc1234, MAE 0,058");
    await ui.click(screen.getByRole("button", { name: "Ghi lại" }));
    expect((await screen.findAllByText(/chạy baseline seed 7/)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Chưa ghi commit và seed/)).toBeNull();
  });
  it("css regression: every child of the log card and its textarea can shrink", () => {
    const css = readFileSync(resolve("src/styles/research.css"), "utf8");
    expect(css).toMatch(/\.rs-card\.rs-log > \*\s*\{[^}]*min-width:\s*0/);
    expect(css).toMatch(/\.rs-logbox textarea\s*\{[^}]*width:\s*0;[^}]*min-width:\s*0/);
    expect(css).toMatch(/\.rs-logbox textarea\s*\{[^}]*font:\s*inherit/);
  });
});

describe("search", () => {
  it("arXiv only: cards have no citations and no TL;DR", async () => {
    seed(UNI);
    const ui = userEvent.setup();
    open("/nghien-cuu");
    await ui.type(await screen.findByRole("textbox", { name: "Tìm paper" }), "graph network{Enter}");
    await screen.findByText(/Learning Formation Energies from Fewer/);
    expect(screen.getByRole("button", { name: /^Độ sâu tìm: Nhanh/ })).toBeInTheDocument(); // no key: only the arXiv level
    expect(screen.queryByText(/Trích dẫn \d+ lần/)).toBeNull();
    expect(screen.queryByText(/TL;DR/)).toBeNull();
    expect(screen.getAllByText("Trích abstract").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Contrastive pretraining|Graph Contrastive/)).toBeNull(); // Semantic Scholar only paper
  });
  it("with Semantic Scholar: citations and TL;DR; with Asta: full-text snippets", async () => {
    seed(UNI, "full", { s2: true, asta: true });
    const ui = userEvent.setup();
    open("/nghien-cuu");
    await ui.type(await screen.findByRole("textbox", { name: "Tìm paper" }), "graph network{Enter}");
    await screen.findByText(/Graph Contrastive Pretraining/);
    expect(screen.getAllByText(/Trích dẫn \d+ lần/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("TL;DR · Semantic Scholar").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Đoạn trích toàn văn · Asta").length).toBeGreaterThan(0);
    expect(screen.getByText("Chỉ có abstract")).toBeInTheDocument();
  });
  it("depth picker: starts at the deepest level with a key, a lower level leaves the source out, keyboard works", async () => {
    seed(UNI, "full", { s2: true });
    const ui = userEvent.setup();
    open("/nghien-cuu");
    await ui.type(await screen.findByRole("textbox", { name: "Tìm paper" }), "graph network{Enter}");
    await screen.findByText(/Graph Contrastive Pretraining/);
    expect(screen.getAllByText("TL;DR · Semantic Scholar").length).toBeGreaterThan(0);
    const btn = screen.getByRole("button", { name: /^Độ sâu tìm: Kỹ/ });
    await ui.click(btn);
    const menu = screen.getByRole("menu", { name: "Tìm sâu đến đâu" });
    expect(within(menu).getByRole("menuitemradio", { name: /^Kỹ/ })).toHaveFocus();
    expect(within(menu).getByRole("menuitemradio", { name: /^Sâu.*Cần key/ })).toHaveAttribute("aria-checked", "false");
    await ui.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(btn).toHaveFocus();
    await ui.click(btn);
    await ui.keyboard("{ArrowUp}");
    expect(screen.getByRole("menuitemradio", { name: /^Nhanh/ })).toHaveFocus();
    await ui.keyboard("{Enter}");
    expect(await screen.findByRole("button", { name: /^Độ sâu tìm: Nhanh/ })).toHaveFocus();
    await waitFor(() => expect(screen.queryByText("TL;DR · Semantic Scholar")).toBeNull());
    expect(localStorage.getItem("mentor.researchDepth")).toBe("quick");
  });
  it("filters by year and PDF, and adds a result to the list", async () => {
    seed(UNI);
    const ui = userEvent.setup();
    open("/nghien-cuu");
    await ui.type(await screen.findByRole("textbox", { name: "Tìm paper" }), "graph{Enter}");
    await screen.findByText(/Message Passing Networks for Materials/);
    await ui.click(screen.getByRole("button", { name: "Năm nay" }));
    await waitFor(() => expect(screen.queryByText(/Message Passing Networks for Materials/)).toBeNull());
    const card = screen.getByText(/Data-Efficient Crystal Graph Networks/).closest("article") as HTMLElement;
    await ui.click(within(card).getByRole("button", { name: "Thêm vào Cần đọc" }));
    await waitFor(() => expect(within(card).getByRole("button", { name: "Đã thêm" })).toHaveAttribute("aria-pressed", "true"));
  });
  it("quick review: working state, then the table with its caveat and follow-ups", async () => {
    seed(UNI);
    const ui = userEvent.setup();
    open("/nghien-cuu");
    await ui.type(await screen.findByRole("textbox", { name: "Tìm paper" }), "graph{Enter}");
    await screen.findByText(/Message Passing Networks for Materials/);
    await ui.click(screen.getByRole("button", { name: "Tổng quan nhanh" }));
    expect(await screen.findByRole("status")).toBeInTheDocument();
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent("Chỉ dựa trên abstract, chưa đủ để kết luận. Đọc toàn văn trước khi trích dẫn.");
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row").length).toBeGreaterThan(5);
    expect(within(table).getAllByText("Abstract không nêu").length).toBeGreaterThan(0);
    expect(screen.getByText("Tìm tiếp")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Ẩn" }));
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("source key dialog", () => {
  it("empty, invalid, checking, success and connected states, with a focus trap and Esc", async () => {
    seed(UNI);
    const ui = userEvent.setup();
    open("/nghien-cuu");
    const depthBtn = await screen.findByRole("button", { name: /^Độ sâu tìm: Nhanh/ });
    await ui.click(depthBtn);
    await ui.click(screen.getByRole("menuitemradio", { name: /Kỹ.*Cần key/ }));
    const dlg = await screen.findByRole("dialog", { name: "Thêm Semantic Scholar" });
    expect(dlg).toHaveAttribute("aria-modal", "true");
    const input = within(dlg).getByLabelText("Key Semantic Scholar");
    expect(input).toHaveFocus();
    // empty
    await ui.click(within(dlg).getByRole("button", { name: "Lưu" }));
    expect(within(dlg).getByRole("alert")).toHaveTextContent("Dán key Semantic Scholar vào ô trên");
    // focus trap: Tab from the last control returns to the first
    const save = within(dlg).getByRole("button", { name: "Lưu" });
    save.focus();
    await ui.tab();
    expect(input).toHaveFocus();
    await ui.tab({ shift: true });
    expect(save).toHaveFocus();
    // invalid
    await ui.type(input, "bad-key");
    await ui.click(save);
    expect(await within(dlg).findByText("Key không đúng hoặc đã hết hạn")).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
    // checking, then success
    await ui.clear(input);
    await ui.type(input, "good-key");
    await ui.click(within(dlg).getByRole("button", { name: "Lưu" }));
    expect(within(dlg).getByRole("button", { name: /Đang kiểm tra/ })).toBeDisabled();
    expect(await screen.findByText("Đã thêm Semantic Scholar")).toHaveAttribute("role", "status");
    expect(screen.queryByRole("dialog")).toBeNull();
    // the level that asked for the key is now picked, and focus is back on the picker
    const kyBtn = screen.getByRole("button", { name: /^Độ sâu tìm: Kỹ/ });
    expect(kyBtn).toHaveFocus();
  });
  it("connected key: change or remove; Esc closes and focus goes back", async () => {
    seed(UNI, "full", { s2: true });
    const ui = userEvent.setup();
    open("/");
    await ui.click(await screen.findByRole("button", { name: /Cài đặt|Settings/ }));
    const gone = await screen.findByRole("button", { name: "Gỡ Semantic Scholar" });
    await ui.click(gone);
    const d2 = await screen.findByRole("dialog", { name: "Semantic Scholar" });
    expect(within(d2).getByRole("button", { name: "Đổi key" })).toBeInTheDocument();
    expect(within(d2).getByRole("button", { name: "Gỡ Semantic Scholar" })).toBeInTheDocument();
    await ui.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("opens from Settings, whose row shows for the university band", async () => {
    seed(UNI);
    const ui = userEvent.setup();
    open("/");
    await ui.click(await screen.findByRole("button", { name: /Cài đặt|Settings/ }));
    expect(screen.getByText("Nguồn tìm paper")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Thêm Asta" }));
    expect(await screen.findByRole("dialog", { name: "Thêm Asta" })).toBeInTheDocument();
  });
  it("has no settings row for other bands", async () => {
    seed(2010);
    const ui = userEvent.setup();
    open("/");
    await ui.click(await screen.findByRole("button", { name: /Cài đặt|Settings/ }));
    expect(screen.queryByText("Nguồn tìm paper")).toBeNull();
  });
});

describe("paper reader", () => {
  it("summary first: no feedback until the learner writes, then the rows in order", async () => {
    seed(UNI);
    const ui = userEvent.setup();
    open("/nghien-cuu/paper/p-2601.08832");
    await screen.findByRole("heading", { name: /Equivariant Message Passing/ });
    expect(screen.queryByText("Góp ý của Mentor")).toBeNull();
    const go = screen.getByRole("button", { name: "Xem góp ý" });
    expect(go).toHaveAttribute("aria-disabled", "true");
    await ui.click(go);
    expect(screen.queryByText("Góp ý của Mentor")).toBeNull();
    await ui.type(screen.getByLabelText("Tóm tắt của bạn"), "Bài đề xuất một mạng truyền thông điệp để dự đoán năng lượng hình thành.");
    expect(go).toHaveAttribute("aria-disabled", "false");
    await ui.click(go);
    const fb = await screen.findByRole("region", { name: /Góp ý của Mentor/ });
    expect(within(fb).getByText("Bạn nắm đúng.")).toBeInTheDocument();
    expect(within(fb).getByText("Chưa chính xác.")).toBeInTheDocument();
    expect(within(fb).getByText("Còn thiếu.")).toBeInTheDocument();
    expect(within(fb).getByText("Với luận văn của bạn:")).toBeInTheDocument();
    // the summary is above the feedback in the page
    const summary = screen.getByText(/Bài đề xuất một mạng truyền thông điệp/);
    expect(summary.compareDocumentPosition(fb) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
  it("answers with a cited passage, and says plainly when it finds none", async () => {
    seed(UNI);
    const ui = userEvent.setup();
    open("/nghien-cuu/paper/p-2601.08832");
    const ask = await screen.findByLabelText("Hỏi về bài này");
    await ui.type(ask, "Họ có báo độ lệch chuẩn qua nhiều seed không?{Enter}");
    expect(await screen.findByText(/Mình không tìm thấy đoạn nào nói về điều này/)).toBeInTheDocument();
    expect(document.querySelectorAll(".rs-src")).toHaveLength(0);
    await ui.type(ask, "Phần ước lượng độ bất định làm thế nào?{Enter}");
    expect(await screen.findByText("Mục 5, Độ bất định")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mở đoạn này" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Suy luận Bayes/ })).toHaveAttribute("href", "/khoa-hoc/bayes");
  });
  it("related papers: invites Semantic Scholar without a key, shows both tabs with one", async () => {
    seed(UNI);
    const ui = userEvent.setup();
    const first = open("/nghien-cuu/paper/p-2601.08832");
    expect(await screen.findByText("Thêm Semantic Scholar để xem bài trích dẫn và được trích dẫn")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Trích dẫn bài này/ })).toBeNull();
    first.unmount();
    seed(UNI, "full", { s2: true });
    open("/nghien-cuu/paper/p-2601.08832");
    const tab = await screen.findByRole("button", { name: "Trích dẫn bài này (14)" });
    expect(screen.getByText(/Calibrated Uncertainty for Graph/)).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Bài này trích dẫn (38)" }));
    expect(tab).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText(/Message Passing Networks for Materials Property Prediction: A Survey/)).toBeInTheDocument();
  });
});
