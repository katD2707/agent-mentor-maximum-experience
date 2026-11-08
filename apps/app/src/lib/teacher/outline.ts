import type { Outline, OutlineChapter, OutlineLesson, OutlineOp } from "../../api/teacher";

/** Mirror of services/course-builder outline.py apply_outline_edits (same op shapes, applied to a copy). */
export class OutlineEditError extends Error {}

const clone = (o: Outline): Outline => JSON.parse(JSON.stringify(o)) as Outline;
const allIds = (o: Outline) => new Set([...o.chapters.map((c) => c.id), ...o.chapters.flatMap((c) => c.lessons.map((l) => l.id))]);

export function slugify(s: string, fallback: string, max = 40): string {
  const t = s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, max);
  return t || fallback;
}
function uniqueId(base: string, taken: Set<string>): string {
  if (!taken.has(base)) return base;
  for (let n = 2; ; n++) if (!taken.has(`${base}-${n}`)) return `${base}-${n}`;
}

function findLesson(o: Outline, id: string): [OutlineChapter, number] {
  for (const ch of o.chapters) {
    const i = ch.lessons.findIndex((l) => l.id === id);
    if (i >= 0) return [ch, i];
  }
  throw new OutlineEditError(`no lesson ${id}`);
}
function findChapter(o: Outline, id: string): OutlineChapter {
  const ch = o.chapters.find((c) => c.id === id);
  if (!ch) throw new OutlineEditError(`no chapter ${id}`);
  return ch;
}
function insert<T extends { id: string }>(items: T[], item: T, index?: number | null, after?: string | null) {
  if (after != null) {
    const i = items.findIndex((x) => x.id === after);
    if (i < 0) throw new OutlineEditError(`no item ${after} to insert after`);
    items.splice(i + 1, 0, item);
  } else if (index == null || index >= items.length) items.push(item);
  else items.splice(Math.max(0, index), 0, item);
}

export function applyOutlineOps(outline: Outline, ops: OutlineOp[]): Outline {
  const o = clone(outline);
  for (const op of ops) {
    switch (op.op) {
      case "rename": {
        const title = op.title.trim();
        if (!title) throw new OutlineEditError("empty title");
        const ch = o.chapters.find((c) => c.id === op.id);
        if (ch) ch.title = title;
        else {
          const [c, i] = findLesson(o, op.id);
          c.lessons[i].title = title;
        }
        break;
      }
      case "update": {
        const [c, i] = findLesson(o, op.id);
        if (op.est_minutes !== undefined) c.lessons[i].est_minutes = Math.max(1, Math.min(240, Math.round(op.est_minutes)));
        break;
      }
      case "reorder": {
        const items: { id: string }[] = op.parent == null ? o.chapters : findChapter(o, op.parent).lessons;
        const known = new Set(items.map((x) => x.id));
        const bad = op.ids.filter((i) => !known.has(i));
        if (bad.length) throw new OutlineEditError(`reorder: unknown ids ${bad.join(",")}`);
        const listed = [...new Set(op.ids)];
        const first = listed.map((i) => items.find((x) => x.id === i)!);
        const rest = items.filter((x) => !listed.includes(x.id));
        items.splice(0, items.length, ...first, ...rest);
        break;
      }
      case "delete": {
        const before = o.chapters.length;
        o.chapters = o.chapters.filter((c) => c.id !== op.id);
        if (o.chapters.length === before) {
          const [c, i] = findLesson(o, op.id);
          c.lessons.splice(i, 1);
          if (!c.lessons.length) o.chapters = o.chapters.filter((x) => x !== c);
        }
        break;
      }
      case "add_lesson": {
        const ch = findChapter(o, op.chapter);
        const title = op.title.trim();
        const ls: OutlineLesson = { id: uniqueId(slugify(title, "bai"), allIds(o)), title, est_minutes: Math.max(1, Math.min(240, op.est_minutes || 8)), grounded: false };
        insert(ch.lessons, ls, op.index, op.after);
        break;
      }
      case "add_chapter": {
        const title = op.title.trim();
        insert(o.chapters, { id: uniqueId("ch-" + slugify(title, "chuong", 30), allIds(o)), title, lessons: [] }, op.index, op.after);
        break;
      }
      case "move_lesson": {
        const [src, i] = findLesson(o, op.id);
        const dest = findChapter(o, op.chapter);
        const [ls] = src.lessons.splice(i, 1);
        insert(dest.lessons, ls, op.index, op.after);
        break;
      }
      case "merge": {
        const ids = [...new Set(op.ids)];
        if (ids.length < 2) throw new OutlineEditError("merge needs two or more lessons");
        const [kc, ki] = findLesson(o, ids[0]);
        const keep = kc.lessons[ki];
        for (const other of ids.slice(1)) {
          const [c, i] = findLesson(o, other);
          const [ls] = c.lessons.splice(i, 1);
          keep.est_minutes = Math.min(240, keep.est_minutes + ls.est_minutes);
          keep.grounded = keep.grounded && ls.grounded;
        }
        if (op.title) keep.title = op.title.trim();
        o.chapters = o.chapters.filter((c) => c.lessons.length);
        break;
      }
      default:
        throw new OutlineEditError(`unknown op ${(op as { op: string }).op}`);
    }
  }
  if (!o.chapters.length) throw new OutlineEditError("the outline would be empty");
  return o;
}

// ---------------------------------------------------------------- what the editable tree sends

export const renameOp = (id: string, title: string): OutlineOp => ({ op: "rename", id, title: title.trim() });
export const deleteOp = (id: string): OutlineOp => ({ op: "delete", id });
export const addLessonOp = (chapter: string, title: string, after?: string): OutlineOp => (after ? { op: "add_lesson", chapter, title, after } : { op: "add_lesson", chapter, title });

export function locate(o: Outline, lessonId: string): { chapter: string; index: number } | null {
  for (const c of o.chapters) {
    const i = c.lessons.findIndex((l) => l.id === lessonId);
    if (i >= 0) return { chapter: c.id, index: i };
  }
  return null;
}

/**
 * Put lesson `id` into chapter `chapter` at `index` (index counted in that chapter's list WITHOUT the lesson).
 * Same chapter: one `reorder` with the full new order. Another chapter: `move_lesson`. Null when nothing changes.
 */
export function moveLessonOps(o: Outline, id: string, chapter: string, index: number): OutlineOp[] | null {
  const at = locate(o, id);
  const dest = o.chapters.find((c) => c.id === chapter);
  if (!at || !dest) return null;
  if (at.chapter === chapter) {
    const ids = dest.lessons.map((l) => l.id).filter((x) => x !== id);
    const i = Math.max(0, Math.min(index, ids.length));
    if (i === at.index) return null;
    ids.splice(i, 0, id);
    return [{ op: "reorder", ids, parent: chapter }];
  }
  return [{ op: "move_lesson", id, chapter, index: Math.max(0, Math.min(index, dest.lessons.length)) }];
}

/** Arrow up / down on a handle: one step in the flattened lesson order, crossing chapters at the edges. */
export function stepLessonOps(o: Outline, id: string, dir: -1 | 1): OutlineOp[] | null {
  const at = locate(o, id);
  if (!at) return null;
  const ci = o.chapters.findIndex((c) => c.id === at.chapter);
  const ch = o.chapters[ci];
  if (dir === -1) {
    if (at.index > 0) return moveLessonOps(o, id, ch.id, at.index - 1);
    const prev = o.chapters[ci - 1];
    return prev ? moveLessonOps(o, id, prev.id, prev.lessons.length) : null;
  }
  if (at.index < ch.lessons.length - 1) return moveLessonOps(o, id, ch.id, at.index + 1);
  const next = o.chapters[ci + 1];
  return next ? moveLessonOps(o, id, next.id, 0) : null;
}

export function lessonCount(o: Outline): number {
  return o.chapters.reduce((n, c) => n + c.lessons.length, 0);
}
export function totalMinutes(o: Outline): number {
  return o.chapters.reduce((n, c) => n + c.lessons.reduce((m, l) => m + l.est_minutes, 0), 0);
}

/** Index (for `moveLessonOps`) of a drop "before lesson `beforeId` of `chapter`", or at the end when `beforeId` is null. */
export function dropIndex(o: Outline, dragId: string, chapter: string, beforeId: string | null): number {
  const ch = o.chapters.find((c) => c.id === chapter);
  if (!ch) return 0;
  const ids = ch.lessons.map((l) => l.id).filter((x) => x !== dragId);
  if (beforeId == null) return ids.length;
  const i = ids.indexOf(beforeId);
  return i < 0 ? ids.length : i;
}
