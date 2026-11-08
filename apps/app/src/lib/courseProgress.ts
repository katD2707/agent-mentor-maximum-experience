import type { Block, CoursePack, Enrollment, Lesson, Progress, TreeChapter } from "../api";

export interface Pos {
  lessonId: string;
  blockId: string;
}

export const allLessons = (pack: CoursePack): Lesson[] => pack.chapters.flatMap((c) => c.lessons);
export const blockIds = (lesson: Lesson): string[] => lesson.blocks.map((b) => b.id);
export const allBlockIds = (pack: CoursePack): string[] => allLessons(pack).flatMap(blockIds);

/** Fraction 0..100 of the course's blocks completed. Without the pack: lessons before the current one / lessons_count. */
export function progressPercent(pack: CoursePack | null, progress: Progress | null, lessonsCount = 0, lessonIds: string[] = []): number {
  if (!progress) return 0;
  if (pack) {
    const all = new Set(allBlockIds(pack));
    if (all.size === 0) return 0;
    const done = progress.completed_block_ids.filter((id) => all.has(id)).length;
    return Math.round((done / all.size) * 100);
  }
  const idx = lessonIds.indexOf(progress.lesson_id);
  return lessonsCount > 0 && idx > 0 ? Math.round((idx / lessonsCount) * 100) : 0;
}

/** Progress inside one lesson, 0..100 (drives the player's bar). */
export function lessonPercent(lesson: Lesson, completed: ReadonlySet<string>): number {
  const ids = blockIds(lesson);
  return ids.length ? Math.round((ids.filter((i) => completed.has(i)).length / ids.length) * 100) : 0;
}

export function isFinished(pack: CoursePack, progress: Progress | null): boolean {
  if (!progress) return false;
  const done = new Set(progress.completed_block_ids);
  return allBlockIds(pack).every((id) => done.has(id));
}

/**
 * Where to open the course: the saved block if it still exists (ids are stable across versions); otherwise the
 * first block of the saved lesson; otherwise the first block not yet completed; otherwise the very start.
 */
export function resumePosition(pack: CoursePack, progress: Progress | null): Pos {
  const lessons = allLessons(pack);
  const first: Pos = { lessonId: lessons[0].id, blockId: lessons[0].blocks[0].id };
  if (!progress) return first;
  const lesson = lessons.find((l) => l.id === progress.lesson_id);
  if (lesson) {
    const block = lesson.blocks.find((b) => b.id === progress.block_id);
    return { lessonId: lesson.id, blockId: (block ?? lesson.blocks[0]).id };
  }
  const done = new Set(progress.completed_block_ids);
  for (const l of lessons) {
    const b = l.blocks.find((x) => !done.has(x.id));
    if (b) return { lessonId: l.id, blockId: b.id };
  }
  return first;
}

/** "Bài 3/7": 1-based index of the current lesson and the total. */
export function lessonOrdinal(lessonIds: string[], progress: Progress | null): { n: number; total: number } {
  const i = progress ? lessonIds.indexOf(progress.lesson_id) : -1;
  return { n: Math.max(i, 0) + 1, total: lessonIds.length };
}

export function chapterOrdinal(tree: TreeChapter[], progress: Progress | null): { n: number; total: number } {
  const i = progress ? tree.findIndex((c) => c.lessons.some((l) => l.id === progress.lesson_id)) : -1;
  return { n: Math.max(i, 0) + 1, total: tree.length };
}

/** 0..5 stars for the small ones. */
export const stars = (percent: number): number => Math.round((percent / 100) * 5);

/** Next unfinished enrollment for the "today" block: started ones first (most recently updated), then not-started. */
export function pickToday(list: Enrollment[], finished: ReadonlySet<string> = new Set()): Enrollment | null {
  const open = list.filter((e) => !finished.has(e.course_id));
  const started = open.filter((e) => e.progress).sort((a, b) => (b.progress?.updated_at ?? "").localeCompare(a.progress?.updated_at ?? ""));
  return started[0] ?? open[0] ?? null;
}

/** Steps the little ones walk through: every block, with quiz blocks split into one step per question. */
export interface Step {
  blockId: string;
  block: Block;
  itemIndex?: number;
}
export function stepsOf(lesson: Lesson): Step[] {
  return lesson.blocks.flatMap((b): Step[] => (b.kind === "quiz" ? b.items.map((_, i) => ({ blockId: b.id, block: b, itemIndex: i })) : [{ blockId: b.id, block: b }]));
}
