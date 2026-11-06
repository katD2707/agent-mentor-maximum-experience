import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Markdown } from "../Markdown";
import { QuestionView } from "./QuestionView";
import { RichText, StemView } from "./RichText";
import type { ClientItem, PracticeAsset } from "@/lib/practice/types";

describe("LaTeX in markdown", () => {
  it("renders inline and display math with KaTeX", () => {
    const html = renderToStaticMarkup(<Markdown>{"Cho $x^2 + 1$ và $$\\frac{a}{b}$$ cùng dòng\n\n$$\n\\int_0^1 x\\,dx\n$$"}</Markdown>);
    expect(html).toContain('class="katex"');
    expect(html).toContain("katex-display"); // the fenced block is display math
    expect(html).toContain("<math");
    expect(html).toContain("\\frac{a}{b}"); // a one-line $$..$$ renders too
  });

  it("shows source text instead of throwing on a broken formula", () => {
    const html = renderToStaticMarkup(<Markdown>{"Lỗi $\\frac{1}{$ vẫn đọc được"}</Markdown>);
    expect(html).toContain("Lỗi");
    expect(html).toContain("vẫn đọc được");
    expect(html).toContain("\\frac{1}{");
  });

  it("is not trusted: no links, images or HTML from LaTeX", () => {
    const html = renderToStaticMarkup(<Markdown>{"$\\href{javascript:alert(1)}{x}$ $\\includegraphics{http://evil/x.png}$ $\\url{http://evil}$"}</Markdown>);
    expect(html).not.toContain('href="javascript');
    expect(html).not.toContain("<img");
    expect(html).not.toContain('href="http://evil');
  });

  it("keeps the existing safety rules next to math", () => {
    const html = renderToStaticMarkup(<Markdown>{"$a$ <script>alert(1)</script> [x](javascript:alert(1))"}</Markdown>);
    expect(html).not.toContain("<script");
    expect(html).not.toContain("javascript:");
  });

  it("inline mode has no paragraph wrapper", () => {
    const html = renderToStaticMarkup(<Markdown inline>{"$I(1; -1)$"}</Markdown>);
    expect(html.startsWith('<span class="md md-inline">')).toBe(true);
    expect(html).not.toContain("<p>");
  });
});

const diagram: PracticeAsset = {
  id: "fig1",
  type: "diagram",
  alt_text: "Đồ thị parabol",
  diagram: { kind: "function_plot", x_min: -2, x_max: 4, y_min: -2, y_max: 5, functions: [{ expr: "x^2 - 2*x" }] },
};
const table: PracticeAsset = { id: "tab1", type: "table", alt_text: "Bảng tần số", table: { headers: ["Nhóm", "$[0;10)$"], rows: [["Tần số", "4"]] } };

const base: ClientItem = { position: 0, id: "q1", type: "SINGLE_CHOICE", stem: "Xem hình:", assets: [diagram], topic: "t", topic_title: "Hàm số", level: 2, estimated_seconds: 60 };

describe("assets", () => {
  it("renders a diagram as a labelled theme-aware SVG below the stem", () => {
    const html = renderToStaticMarkup(<StemView item={base} />);
    expect(html).toContain('role="img"');
    expect(html).toContain('aria-label="Đồ thị parabol"');
    expect(html).toContain("var(--accent)");
    expect(html).not.toMatch(/stroke="#/);
  });

  it("places an asset where a token says and not twice", () => {
    const item = { ...base, stem: "Trước\n\n![](asset:fig1)\n\nSau" };
    const html = renderToStaticMarkup(<StemView item={item} />);
    expect(html.match(/<svg/g)).toHaveLength(1);
    expect(html.indexOf("Trước")).toBeLessThan(html.indexOf("<svg"));
    expect(html.indexOf("<svg")).toBeLessThan(html.indexOf("Sau"));
  });

  it("renders a table with LaTeX in a cell, and a raster image from the gateway route", () => {
    const html = renderToStaticMarkup(
      <RichText text="![](asset:tab1) ![](asset:img1)" assets={[table, { id: "img1", type: "image", alt_text: "Bảng biến thiên", image: { sha256: "a".repeat(64), media_type: "image/png", width: 640, height: 220 } }]} />,
    );
    expect(html).toContain('scope="col"');
    expect(html).toContain("katex");
    expect(html).toContain(`/practice/assets/${"a".repeat(64)}`);
    expect(html).toContain('alt="Bảng biến thiên"');
  });

  it("falls back to alt text for a malformed image hash", () => {
    const html = renderToStaticMarkup(<RichText text="![](asset:i)" assets={[{ id: "i", type: "image", alt_text: "Hình lỗi", image: { sha256: "../../etc", media_type: "image/png", width: 1, height: 1 } }]} />);
    expect(html).not.toContain("<img");
    expect(html).toContain("Hình lỗi");
  });
});

describe("answer areas", () => {
  const noop = () => {};
  it("renders four options with letters, LaTeX and keycaps, then the result in words", () => {
    const item: ClientItem = { ...base, assets: [], options: [{ id: "A", text: "$I(1; -1)$" }, { id: "B", text: "B" }, { id: "C", text: "C" }, { id: "D", text: "D" }] };
    const open = renderToStaticMarkup(<QuestionView item={item} answer="B" onAnswer={noop} readOnly={false} />);
    expect(open).toContain('role="radiogroup"');
    expect(open).toContain('aria-checked="true"');
    expect(open).toContain("katex");
    expect(open).toContain("Thử nghiệm · AI đã kiểm định");
    const done = renderToStaticMarkup(<QuestionView item={item} answer="B" onAnswer={noop} readOnly outcome={{ correctAnswer: "A", correct: false, optionFeedback: { B: "Bạn đổi dấu." } }} />);
    expect(done).toContain("(đáp án đúng)");
    expect(done).toContain("(bạn đã chọn, chưa đúng)");
    expect(done).toContain("Bạn đổi dấu.");
  });

  it("renders a true/false group with Đúng/Sai per statement and per-statement results", () => {
    const item: ClientItem = { ...base, assets: [], type: "TRUE_FALSE_GROUP", statements: ["a", "b", "c", "d"].map((id) => ({ id, text: `Ý ${id}` })) };
    const html = renderToStaticMarkup(<QuestionView item={item} answer="TF-T" onAnswer={noop} readOnly outcome={{ correctAnswer: "TTTT", statementResults: [true, false, false, true] }} />);
    expect((html.match(/role="radio"/g) ?? []).length).toBe(8);
    expect(html).toContain("✓ Bạn chọn Đúng, chính xác");
    expect(html).toContain("✗ Bạn chọn Sai · đáp án: Đúng");
    expect(html).toContain("✗ Bạn chọn bỏ trống · đáp án: Đúng");
  });

  it("renders the short-answer box with its answer-sheet rules", () => {
    const item: ClientItem = { ...base, assets: [], type: "SHORT_ANSWER", short_answer: { max_chars: 4, decimals: 2 } };
    const html = renderToStaticMarkup(<QuestionView item={item} answer="0,6" onAnswer={noop} readOnly={false} />);
    expect(html).toContain("Đáp án của bạn");
    expect(html).toContain("3/4 kí tự");
    expect(html).toContain("tối đa 4 kí tự");
    expect(html).toContain("làm tròn đến hàng phần trăm");
    expect(html).toContain('inputMode="decimal"');
  });
});
