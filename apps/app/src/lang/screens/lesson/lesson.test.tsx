import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import i18n from "../../../i18n";
import { App } from "../../../App";
import { AuthProvider } from "../../../state/auth";
import { stageIndex } from "../chuong/logic";
import { drawnStage, spriteVars } from "../../chickenArt";
import { verdictDetail } from "../../kit/QuizItemView";
import { TilesInput } from "../../kit/StepInputs";
import { renderMd } from "../../../lib/md";
import type { QuizItem } from "../../../api";

/** The lesson player as lg-04 draws it: the chicken explains, a miss is explained again, XP shows at the end. */
const seed = (band: string, birth: number) => {
  localStorage.setItem("mentor.mock.users", JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: band, birth_year: birth, language: "vi", theme: "system", quiet_until: null } } }));
  localStorage.setItem("mentor.token", "mock-u-hs");
  localStorage.setItem("mentor.mock.lg.u-hs", JSON.stringify({ chickens: [{ id: "li", xp: 95, taken_at: "2026-11-01T00:00:00Z" }] }));
};
function Where() {
  const l = useLocation();
  return <output data-testid="where">{l.pathname + l.search}</output>;
}
const open = (entry: string | { pathname: string; search: string; state?: unknown }, first = "/") =>
  render(
    <MemoryRouter initialEntries={[first, entry]} initialIndex={1}>
      <AuthProvider>
        <App />
        <Where />
      </AuthProvider>
    </MemoryRouter>,
  );
const where = () => screen.getByTestId("where").textContent ?? "";
const COURSE = "/khoa-hoc/vat-li-11-dien-truong/hoc";

beforeEach(async () => {
  await i18n.changeLanguage("vi");
  localStorage.clear();
});

describe("pure parts of the lesson look", () => {
  it("names the four stages of growth and frames each drawing", () => {
    expect([1, 2, 4, 5, 9, 10, 40].map(stageIndex)).toEqual([1, 2, 2, 3, 3, 4, 4]);
    expect(drawnStage("toan", 3)).toBe(3);
    expect(drawnStage("zzz", 1)).toBe(3); // a stage with no drawing of its own shows the grown one
    expect(drawnStage("li", 1)).toBe(1);
    expect(Number(spriteVars("li", 1)["--gh"])).toBeLessThan(Number(spriteVars("li", 3)["--gh"]));
  });
});

describe("explanations are rendered, not shown raw", () => {
  const item = {
    id: "q1",
    type: "SINGLE_CHOICE",
    stem: "Độ phức tạp?",
    options: [
      { id: "A", text: "$O(n)$" },
      { id: "B", text: "$O(1)$, xấu nhất" },
    ],
    answer_key: { correct: "B" },
    option_feedback: { A: "Đó là $O(n)$ khi duyệt hết." },
    explanation: "Truy cập `T a[n]` là $O(1)$.",
  } as unknown as QuizItem;
  it("keeps the full right answer (math included) and renders KaTeX and short inline code in one piece", () => {
    const md = verdictDetail(item, { correct: false, correctOptionId: "B" } as never, "A", "Đáp án");
    expect(md).toContain("Đáp án B: $O(1)$, xấu nhất.");
    const html = renderMd(md);
    expect(html).toContain("katex");
    expect(html).not.toContain("$O(1)$");
    expect(html).toContain('<code class="s">T a[n]</code>');
    expect(renderMd(`\`${"x".repeat(40)}\``)).toContain("<code>");
  });
});

describe("lesson with the chicken (lg-04)", () => {
  it("one step per screen: check, red band with the right answer, the chicken explains again, then the question once more", async () => {
    seed("g10_12", 2009);
    const ui = userEvent.setup();
    open({ pathname: COURSE, search: "?lesson=l1&from=khoa" });
    expect(await screen.findByRole("heading", { name: "Bài 1" })).toBeInTheDocument();
    await ui.click(await screen.findByRole("button", { name: "Tiếp tục" })); // the chicken's text step
    const check = await screen.findByRole("button", { name: "Kiểm tra" });
    expect(check).toBeDisabled();
    await ui.click(await screen.findByRole("button", { name: /Hút nhau/ }));
    await ui.click(check);
    expect(await screen.findByText("Chưa đúng")).toBeInTheDocument();
    expect(screen.getByText(/Đáp án B: Đẩy nhau/)).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));
    // the red band said it all and this question has no hint: no second telling, the same question comes straight back
    expect(screen.queryByText("Gà giảng lại")).toBeNull();
    expect(await screen.findByText("Thử lại câu này")).toBeInTheDocument();
    await ui.click(await screen.findByRole("button", { name: /Đẩy nhau/ }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Chính xác!")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));
    expect(await screen.findByRole("heading", { name: "Xong bài 1!" })).toBeInTheDocument();
    expect(screen.getByText("0/1")).toBeInTheDocument();
    expect(screen.getByText("Câu sai và ý chưa nhớ: ôn lại sau 2 ngày.")).toBeInTheDocument();
  }, 20000);

  it("a miss on the second try comes back once at the end of the lesson", async () => {
    seed("g10_12", 2009);
    const ui = userEvent.setup();
    open({ pathname: COURSE, search: "?lesson=l1" });
    await ui.click(await screen.findByRole("button", { name: "Tiếp tục" }));
    const miss = async () => {
      await ui.click(await screen.findByRole("button", { name: /Hút nhau/ }));
      await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
      expect(await screen.findByText("Chưa đúng")).toBeInTheDocument();
      await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));
    };
    await miss(); // first try: the same question comes back
    await miss(); // the second try is wrong too: it waits for the end
    await ui.click(await screen.findByRole("button", { name: /Đẩy nhau/ }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Chính xác!")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));
    expect(await screen.findByRole("heading", { name: "Xong bài 1!" })).toBeInTheDocument();
  }, 20000);

  it("the end shows the XP the server paid (+20, +5 when all right first time) and the chicken's level bar", async () => {
    seed("g10_12", 2009);
    const ui = userEvent.setup();
    open({ pathname: COURSE, search: "?lesson=l1" });
    await ui.click(await screen.findByRole("button", { name: "Tiếp tục" }));
    await ui.click(await screen.findByRole("button", { name: /Đẩy nhau/ }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Chính xác!")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));
    expect(await screen.findByRole("heading", { name: "Xong bài 1!" })).toBeInTheDocument();
    const box = screen.getByLabelText("Kinh nghiệm của gà");
    expect(await screen.findByText("+20 kinh nghiệm")).toBeInTheDocument();
    expect(await screen.findByText("+5 đúng hết ngay lần đầu")).toBeInTheDocument();
    expect(box).toHaveTextContent("Gà Lí");
    // 95 XP + 25 = level 2, 20 into the level
    await waitFor(() => expect(screen.getByText("Lên cấp!")).toBeInTheDocument());
    await waitFor(() => expect(box).toHaveTextContent("20/100 · còn 80 nữa là lên cấp 3"));
  }, 20000);

  it("leaving a lesson opened from the coop goes back to that chicken's coop with the course open; from anywhere else to the village", async () => {
    seed("g10_12", 2009);
    const ui = userEvent.setup();
    const a = open({ pathname: COURSE, search: "?lesson=l1&from=khoa" });
    await screen.findByRole("heading", { name: "Bài 1" });
    await ui.click(await screen.findByRole("button", { name: "Thoát" }));
    await waitFor(() => expect(where()).toBe("/chuong/li?khoa=vat-li-11-dien-truong"));
    a.unmount();
    open({ pathname: COURSE, search: "?lesson=l1" });
    await screen.findByRole("heading", { name: "Bài 1" });
    await ui.click(await screen.findByRole("button", { name: "Thoát" }));
    await waitFor(() => expect(where()).toBe("/"));
  }, 20000);

  it("a course the student does not have sends them to its page, not into the player", async () => {
    seed("g10_12", 2009);
    open({ pathname: "/khoa-hoc/xac-suat-bayes/hoc", search: "" });
    await waitFor(() => expect(where()).toMatch(/^\/chuong\/[a-z]+\?c=xac-suat-bayes$/));
  });
});

describe("a blank inside a formula", () => {
  const stem = "Địa chỉ của phần tử thứ $i$ là $addr(a[i]) = addr(a) + i \\cdot {{gap}}$, nhờ đó truy cập nhanh.";
  const parts = [{ id: "p1", text: "sizeof(T)" }, { id: "p2", text: "O(1)" }] as never;
  it("shows the formula as maths with the blank in its place, never raw TeX", async () => {
    const { container, rerender } = render(<TilesInput stem={stem} parts={parts} seed="s" value={[]} onChange={() => {}} locked={false} />);
    await waitFor(() => expect(container.querySelector(".gap-host .gap")).not.toBeNull());
    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container.textContent).not.toContain("$");
    expect(container.textContent).not.toContain("\\cdot");
    rerender(<TilesInput stem={stem} parts={parts} seed="s" value={["p1"]} onChange={() => {}} locked={false} />);
    await waitFor(() => expect(container.querySelector(".gap-host button.tile.placed")?.textContent?.trim()).toBe("sizeof(T)"));
  });
  it("a blank in plain text keeps its pieces and renders the text around it", () => {
    const { container } = render(<TilesInput stem="Có `T a[n]` và {{gap}} ở đây." parts={parts} seed="s" value={[]} onChange={() => {}} locked={false} />);
    expect(container.querySelector("code.s")?.textContent).toBe("T a[n]");
    expect(container.textContent).not.toContain("`");
    expect(container.querySelector(".gap-host")).toBeNull();
  });
});

describe("lesson links: resume and start", () => {
  const saveAt = (lesson: string, block: string, done: string[]) =>
    localStorage.setItem("mentor.mock.enroll.u-hs", JSON.stringify([{ course_id: "vat-li-11-dien-truong", pinned_version: 1, enrolled_at: "2026-11-01T08:00:00Z", progress: { lesson_id: lesson, block_id: block, completed_block_ids: done } }]));

  it("a link to the lesson left in the middle opens where the student stopped", async () => {
    seed("g10_12", 2009);
    saveAt("l1", "l1-b2", ["l1-b1"]);
    open({ pathname: COURSE, search: "?lesson=l1&from=khoa" });
    expect(await screen.findByText("Hai điện tích cùng dấu đặt gần nhau sẽ như thế nào?")).toBeInTheDocument(); // the question, not the text step before it
  });

  it("a link to another lesson starts that lesson from its first step", async () => {
    seed("g10_12", 2009);
    saveAt("l1", "l1-b2", ["l1-b1"]);
    open({ pathname: COURSE, search: "?lesson=l2&from=khoa" });
    expect(await screen.findByRole("heading", { name: "Bài 2" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Tiếp tục" })).toBeInTheDocument();
    expect(screen.queryByText("Hai điện tích cùng dấu đặt gần nhau sẽ như thế nào?")).toBeNull();
  });

  it("a miss with a hint the red band did not say gets the chicken's second telling", async () => {
    seed("g10_12", 2009);
    saveAt("l2", "l2-b8", []);
    open({ pathname: COURSE, search: "?lesson=l2" });
    await screen.findByRole("heading", { name: "Bài 2" });
    const ui = userEvent.setup();
    await ui.click(await screen.findByRole("button", { name: /Các đường tròn đồng tâm/ }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Chưa đúng")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));
    expect(await screen.findByText("Gà giảng lại")).toBeInTheDocument();
    expect(screen.getByText(/Nhớ chiều: đường sức đi ra/)).toBeInTheDocument();
  }, 20000);
});

describe("lesson with the chicken: every kind of step", () => {
  it("tiles, pairs, order, drag diagram and recall are graded by the bottom bar; forgotten ideas count under Ôn lại", async () => {
    seed("g10_12", 2009);
    const ui = userEvent.setup();
    open({ pathname: COURSE, search: "?lesson=l4" });
    await ui.click(await screen.findByRole("button", { name: "Tiếp tục" })); // the chicken's text step

    // FILL_TILES: tap a tile into the gap; a miss: the answer, the explanation again, then one more try
    expect(await screen.findByText("Điền chỗ trống")).toBeInTheDocument();
    const check = screen.getByRole("button", { name: "Kiểm tra" });
    expect(check).toBeDisabled();
    await ui.click(screen.getByRole("button", { name: "r" }));
    await ui.click(check);
    expect(await screen.findByText("Chưa đúng")).toBeInTheDocument();
    expect(screen.getByText(/Đáp án: r²/)).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));
    await ui.click(await screen.findByRole("button", { name: "r²" }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Chính xác!")).toBeInTheDocument();
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));

    // MATCH_PAIRS: a wrong match is a slip, the right ones lock
    await ui.click(await screen.findByRole("button", { name: "Cường độ E" }));
    await ui.click(screen.getByRole("button", { name: "N" })); // wrong
    await ui.click(screen.getByRole("button", { name: "V/m" }));
    await ui.click(screen.getByRole("button", { name: "Lực điện F" }));
    await ui.click(screen.getByRole("button", { name: "N" }));
    await ui.click(screen.getByRole("button", { name: "Điện tích q" }));
    await ui.click(screen.getByRole("button", { name: "C" }));
    expect(await screen.findByText("Chưa đúng")).toBeInTheDocument(); // one slip: not right on the first try
    await ui.click(screen.getByRole("button", { name: "Tiếp tục" }));
    for (const name of ["Cường độ E", "V/m", "Lực điện F", "N", "Điện tích q", "C"]) await ui.click(await screen.findByRole("button", { name }));
    expect(await screen.findByText(/Chính xác!|Xuất sắc!/)).toBeInTheDocument();
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
    expect(await screen.findByText(/Xa gấp đôi thì E còn 1\/4/)).toBeInTheDocument(); // the chicken's praise
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

    // the end: 1 of 3 right at first, plus the idea not remembered
    expect(await screen.findByRole("heading", { name: /^Xong bài/ })).toBeInTheDocument();
    expect(screen.getByText("1/3")).toBeInTheDocument();
    expect(screen.getByText("3 câu")).toBeInTheDocument();
  }, 40000);

  it("little ones: check from the bottom bar, a green band after a right answer, one big button", async () => {
    seed("g1_5", 2018);
    const ui = userEvent.setup();
    open({ pathname: "/khoa-hoc/toan-1-dem-tao/hoc", search: "?lesson=l1" });
    for (let i = 0; i < 6 && !screen.queryByRole("button", { name: "Đã chạm: 1" }); i++) {
      await ui.click(await screen.findByRole("button", { name: "Tiếp tục" }));
    }
    for (let n = 1; n <= 5; n++) await ui.click(await screen.findByRole("button", { name: `Đã chạm: ${n}` }));
    await ui.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByText("Chính xác!")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Tiếp tục" })).toBeInTheDocument();
    expect(document.querySelector(".lp")).toHaveAttribute("data-age", "tieu-hoc");
  }, 20000);

  it("Enter continues from a step", async () => {
    seed("g10_12", 2009);
    const ui = userEvent.setup();
    open({ pathname: COURSE, search: "?lesson=l1" });
    await screen.findByRole("button", { name: "Tiếp tục" });
    await ui.keyboard("{Enter}");
    expect(await screen.findByRole("button", { name: "Kiểm tra" })).toBeInTheDocument();
  });
});

describe("maths and captions in the practice items and lesson blocks", () => {
  it("renders stems, options, true/false statements and a figure caption through KaTeX, and a bare \log chip as maths", async () => {
    const { ItemView } = await import("../practice/ItemView");
    const { lineOf } = await import("../practice/Fix");
    const { StaticBlock } = await import("../../kit/blocks");
    const item = {
      id: "p1",
      type: "SINGLE_CHOICE",
      stem: "Phương trình $ax + b = 0$ ($a \\neq 0$) có nghiệm:",
      options: [
        { id: "A", text: "$x = -\\frac{b}{a}$" },
        { id: "B", text: "$x = \\frac{b}{a}$" },
      ],
    } as never;
    const { container } = render(<ItemView item={item} token="t" lang="vi" value="" onChange={() => undefined} locked={false} />);
    expect(container.querySelectorAll(".opt .katex").length).toBe(2);
    expect(container.querySelector(".q-stem .katex")).not.toBeNull();
    const fig = render(<StaticBlock b={{ id: "i", kind: "image", image: null, alt: "cây", caption: "chiều cao $h=2$" } as never} ctx={{ lang: "vi", url: () => "" }} />);
    expect(fig.container.querySelector("figcaption .katex")).not.toBeNull();
    expect(fig.container.textContent).not.toContain("$");
    // true/false answers read as "a: Đúng, b: Sai", not "TF"
    const tf = { id: "t1", type: "TRUE_FALSE_GROUP", stem: "", statements: [{ id: "a", text: "x" }, { id: "b", text: "y" }] } as never;
    expect(lineOf(tf, "TF", "Đúng", "Sai")).toBe("a: Đúng, b: Sai");
    const tiles = render(<TilesInput stem="T = {{gap}}" parts={[{ id: "p", text: "\\log_2 n" } as never]} seed="s" value={[]} onChange={() => undefined} locked={false} />);
    expect(tiles.container.querySelector(".bank .tile .katex")).not.toBeNull();
  });
});
