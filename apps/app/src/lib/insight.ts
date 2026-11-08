import type { CoursePack, Enrollment } from "../api";

/**
 * Per-course strengths and watch-outs, from what the enrollment holds: the last result of every quiz item
 * (GET /enrollments `quiz`) mapped to lessons through the course pack. A lesson is "strong" when it has at least two
 * answered items and all of them were right, a "watch" when most of its answered items are wrong. Without the pack or
 * without answers there is nothing to say (the caller shows a progress line instead).
 */
export interface Insight {
  strong: string[];
  watch: string[];
}

export function courseInsight(pack: CoursePack | null, e: Pick<Enrollment, "quiz">, max = 2): Insight {
  const out: Insight = { strong: [], watch: [] };
  const quiz = e.quiz;
  if (!pack || !quiz) return out;
  for (const ch of pack.chapters) {
    for (const l of ch.lessons) {
      const ids = l.blocks.flatMap((b) => (b.kind === "quiz" ? b.items.map((q) => q.id) : []));
      const answered = ids.map((id) => quiz[id]).filter((x) => !!x);
      if (!answered.length) continue;
      const wrong = answered.filter((x) => !x.correct).length;
      if (wrong === 0 && answered.length >= 2) out.strong.push(l.title);
      else if (wrong * 2 > answered.length) out.watch.push(l.title);
    }
  }
  out.strong = out.strong.slice(0, max);
  out.watch = out.watch.slice(0, max);
  return out;
}
