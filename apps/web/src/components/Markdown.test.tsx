import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Markdown } from "./Markdown";

describe("<Markdown>", () => {
  it("renders GFM tables and task lists", () => {
    const html = renderToStaticMarkup(<Markdown>{"| a | b |\n|---|---|\n| 1 | 2 |\n\n- [x] xong\n- [ ] chưa"}</Markdown>);
    expect(html).toContain('<div class="table-wrap"><table>');
    expect(html).toContain("<td>1</td>");
    expect(html).toMatch(/type="checkbox"[^>]*checked/);
  });

  it("never renders raw HTML from workspace files", () => {
    const html = renderToStaticMarkup(
      <Markdown>{'Xin chào <script>alert(1)</script> <img src=x onerror="alert(2)"> <b>đậm</b>'}</Markdown>,
    );
    expect(html).not.toContain("<script");
    expect(html).not.toContain("onerror");
    expect(html).not.toContain("<b>");
    expect(html).toContain("Xin chào");
  });

  it("strips javascript: links and does not load remote images", () => {
    const html = renderToStaticMarkup(<Markdown>{"[bấm](javascript:alert(1)) ![ảnh](https://evil.example/x.png)"}</Markdown>);
    expect(html).not.toContain("javascript:");
    expect(html).not.toContain("<img");
    expect(html).toContain("[Ảnh: ảnh]");
    expect(html).toContain('rel="noopener noreferrer nofollow"');
  });
});
