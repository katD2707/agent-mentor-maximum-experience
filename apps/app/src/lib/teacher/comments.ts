import type { CommentAnchor, TeacherComment } from "../../api/teacher";
import type { TextMark } from "./anchors";

/** Order inside a block: text by position, video by second, picture top to bottom then left to right. */
export function anchorPos(a: CommentAnchor): number {
  return a.kind === "text" ? a.start : a.kind === "time" ? a.t : a.y * 1000 + a.x;
}

export type Numbered = TeacherComment & { n: number };

/**
 * The red-pen numbers of one lesson: comments on its blocks, in reading order (block order, then position).
 * `blockIds` are the lesson's block ids in order; comments of other lessons are left out.
 */
export function numberComments(comments: readonly TeacherComment[], blockIds: readonly string[]): Numbered[] {
  const order = new Map(blockIds.map((b, i) => [b, i]));
  return comments
    .filter((c) => order.has(c.block_id))
    .sort((a, b) => order.get(a.block_id)! - order.get(b.block_id)! || anchorPos(a.anchor) - anchorPos(b.anchor))
    .map((c, i) => ({ ...c, n: i + 1 }));
}

/**
 * Highlights for one block. A text comment is only drawn when the text at its offsets is still the quote (after the
 * agent rewrote the block the old offsets may not fit; the margin note still shows it).
 */
export function textMarks(notes: readonly Numbered[], blockId: string, text: string, active: string | null): TextMark[] {
  const out: TextMark[] = [];
  for (const n of notes) {
    if (n.block_id !== blockId || n.anchor.kind !== "text") continue;
    const flat = (s: string) => s.replace(/\s+/g, " ").trim();
    if (flat(text.slice(n.anchor.start, n.anchor.end)) !== flat(n.anchor.quote)) continue;
    out.push({ id: n.id, start: n.anchor.start, end: n.anchor.end, n: n.n, cls: `${n.status === "applied" ? "fixed" : ""}${active === n.id ? " active" : ""}`.trim() });
  }
  return out;
}
