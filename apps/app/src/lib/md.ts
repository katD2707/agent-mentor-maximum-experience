import { Marked } from "marked";
import katex from "katex";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** Course text is Markdown + KaTeX with no raw HTML (course.py): HTML is escaped, images and unsafe links are dropped. */
const marked = new Marked({
  gfm: true,
  renderer: {
    html: ({ text }) => esc(text),
    // short inline code (`T a[n]`) stays in one piece; a long one may wrap
    codespan: ({ text }) => `<code${text.length <= 28 ? ' class="s"' : ""}>${esc(text)}</code>`,
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

const GAP_TOKEN = /GAPN(\d+)END/g;

function renderMath(tex: string, display: boolean, gaps = false): string {
  // a blank inside a formula becomes an empty, tagged box (data-gap) that the lesson fills with the tile
  const src = gaps ? tex.replace(GAP_TOKEN, (_m, n: string) => `\\htmlData{gap=${n}}{\\phantom{0000}}`) : tex;
  return katex.renderToString(src.trim(), { displayMode: display, throwOnError: false, trust: gaps ? (c) => c.command === "\\htmlData" : false, output: "html", strict: "ignore" });
}

/** Markdown to an HTML string; math is rendered by KaTeX and kept out of the Markdown parser. */
export function renderMd(md: string): string {
  return render(md, false);
}

/**
 * The same, for a "fill the blanks" stem: every `{{gap}}` (in the text or inside a formula) becomes an empty
 * `<span data-gap="n">` in order, so the caller can put the tile there.
 */
export function renderMdGaps(md: string): string {
  let n = 0;
  return render(md.replace(/\{\{gap\}\}/g, () => `GAPN${n++}END`), true);
}

/**
 * A short answer chip such as `\log_2 n` that came without `$` (AI-made items): when the string holds a LaTeX command and
 * nothing that reads as a plain word besides the commands, the whole of it is a formula.
 */
export function bareMath(md: string): boolean {
  const t = md.trim();
  if (!t || t.length > 120 || /[$\n]|\\[([]/.test(t) || !/\\[a-zA-Z]{2,}/.test(t)) return false;
  return !/[a-zà-ỹ]{3,}/i.test(t.replace(/\\[a-zA-Z]+/g, " "));
}

function render(md: string, gaps: boolean): string {
  const math: string[] = [];
  let src = bareMath(md) ? `$${md.trim()}$` : md;
  for (const { re, display } of PATTERNS) {
    src = src.replace(re, (_m, tex: string) => {
      math.push(renderMath(tex, display, gaps));
      return `MATHPH${math.length - 1}END`;
    });
  }
  const html = marked.parse(src, { async: false });
  return html.replace(/MATHPH(\d+)END/g, (_m, i: string) => math[Number(i)] ?? "").replace(GAP_TOKEN, (_m, i: string) => `<span data-gap="${i}"></span>`);
}
