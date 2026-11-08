import { Marked } from "marked";
import katex from "katex";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** Course text is Markdown + KaTeX with no raw HTML (course.py): HTML is escaped, images and unsafe links are dropped. */
const marked = new Marked({
  gfm: true,
  renderer: {
    html: ({ text }) => esc(text),
    image: ({ text }) => esc(text),
    link({ href, tokens }) {
      const inner = this.parser.parseInline(tokens);
      return /^(https?:|mailto:|#)/i.test(href) ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${inner}</a>` : inner;
    },
  },
});

const PATTERNS: { re: RegExp; display: boolean }[] = [
  { re: /\$\$([\s\S]+?)\$\$/g, display: true },
  { re: /\\\[([\s\S]+?)\\\]/g, display: true },
  { re: /\\\(([\s\S]+?)\\\)/g, display: false },
  { re: /\$(?![\s$])((?:\\.|[^$\\\n])+?)(?<![\s\\])\$(?!\d)/g, display: false },
];

function renderMath(tex: string, display: boolean): string {
  return katex.renderToString(tex.trim(), { displayMode: display, throwOnError: false, trust: false, output: "html", strict: "ignore" });
}

/** Markdown to an HTML string; math is rendered by KaTeX and kept out of the Markdown parser. */
export function renderMd(md: string): string {
  const math: string[] = [];
  let src = md;
  for (const { re, display } of PATTERNS) {
    src = src.replace(re, (_m, tex: string) => {
      math.push(renderMath(tex, display));
      return `MATHPH${math.length - 1}END`;
    });
  }
  const html = marked.parse(src, { async: false });
  return html.replace(/MATHPH(\d+)END/g, (_m, i: string) => math[Number(i)] ?? "");
}
