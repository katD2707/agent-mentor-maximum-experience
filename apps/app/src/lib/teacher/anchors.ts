import type { CommentAnchor } from "../../api/teacher";

/** m:ss for a number of seconds. */
export function fmtTime(s: number): string {
  const t = Math.max(0, Math.round(s));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

const round1 = (n: number) => Math.round(n * 10) / 10;

/** Video: the paused position, to a tenth of a second. */
export function timeAnchor(t: number): CommentAnchor {
  return { kind: "time", t: round1(Math.max(0, t)) };
}

/** Image: a tap as a fraction (0-1) of the picture's width and height (the gateway contract). */
export function pointAnchor(rect: { left: number; top: number; width: number; height: number }, clientX: number, clientY: number): CommentAnchor {
  const pct = (v: number, size: number) => Math.round(Math.min(1, Math.max(0, size > 0 ? v / size : 0.5)) * 1000) / 1000;
  return { kind: "point", x: pct(clientX - rect.left, rect.width), y: pct(clientY - rect.top, rect.height) };
}

/** Characters of `root`'s text before (node, offset). */
function offsetIn(root: Node, node: Node, offset: number): number {
  const r = document.createRange();
  r.selectNodeContents(root);
  r.setEnd(node, offset);
  return r.toString().length;
}

/** Text: the selection as offsets in `root.textContent` plus the quote. Null when it is empty or leaves `root`. */
export function textAnchor(root: Element, range: Range): CommentAnchor | null {
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return null;
  const start = offsetIn(root, range.startContainer, range.startOffset);
  const end = offsetIn(root, range.endContainer, range.endOffset);
  const full = (root.textContent ?? "").slice(start, end);
  const lead = full.length - full.trimStart().length;
  const quote = full.trim().replace(/\s+/g, " ");
  if (!quote) return null;
  return { kind: "text", start: start + lead, end: start + lead + full.trim().length, quote };
}

export interface TextMark {
  id: string;
  start: number;
  end: number;
  cls: string;
  /** shown as a small red-pen number on the first piece */
  n?: number;
}

/** Remove the marks `markText` added. */
export function clearMarks(root: Element): void {
  const marks = root.querySelectorAll("mark[data-cmt]");
  const parents = new Set<Element>();
  marks.forEach((m) => {
    const p = m.parentElement;
    if (p) parents.add(p);
    m.replaceWith(...Array.from(m.childNodes));
  });
  parents.forEach((p) => p.normalize());
}

/**
 * Wrap the text of each mark (offsets in `root.textContent`) in <mark data-cmt>. Only text nodes inside `scope`
 * elements (the Markdown bodies, which React does not manage) are touched; offsets still count every text node.
 */
export function markText(root: Element, marks: TextMark[], scope = ".md"): void {
  clearMarks(root);
  if (!marks.length) return;
  const numbered = new Set<string>();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: { node: Text; start: number }[] = [];
  let pos = 0;
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    nodes.push({ node: n as Text, start: pos });
    pos += (n as Text).data.length;
  }
  for (const { node, start } of nodes) {
    if (!node.parentElement?.closest(scope)) continue;
    const end = start + node.data.length;
    const hit = marks.filter((m) => m.start < end && m.end > start);
    if (!hit.length) continue;
    const cuts = new Set<number>([0, node.data.length]);
    for (const m of hit) {
      cuts.add(Math.max(0, m.start - start));
      cuts.add(Math.min(node.data.length, m.end - start));
    }
    const pts = [...cuts].sort((a, b) => a - b);
    const frag = document.createDocumentFragment();
    for (let i = 0; i < pts.length - 1; i++) {
      const [a, b] = [pts[i], pts[i + 1]];
      const text = node.data.slice(a, b);
      if (!text) continue;
      const m = hit.find((h) => h.start - start <= a && h.end - start >= b);
      if (m) {
        const el = document.createElement("mark");
        el.dataset.cmt = m.id;
        el.className = `cmt ${m.cls}`;
        el.textContent = text;
        if (m.n && !numbered.has(m.id)) {
          numbered.add(m.id);
          el.dataset.n = String(m.n);
        }
        frag.append(el);
      } else frag.append(text);
    }
    node.replaceWith(frag);
  }
}
