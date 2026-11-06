/** Pure helpers for the practice setup page: prefill from a link or chat card, and the preview wording. */
import type { PracticeGoal, PracticePreview, PracticeSubject } from "./types";

export const MINUTES = [10, 20, 30, 45] as const;
export const GOALS: { id: PracticeGoal; label: string; hint: string }[] = [
  { id: "balanced", label: "Cân bằng", hint: "Trải đều các chủ đề" },
  { id: "weak", label: "Chủ đề cần luyện thêm", hint: "Nhiều câu hơn ở chỗ còn cần củng cố" },
  { id: "challenge", label: "Thử thách", hint: "Thêm câu khó hơn một chút" },
];

export function parseMinutes(v: string | number | null | undefined): number {
  const n = Number(v);
  return (MINUTES as readonly number[]).includes(n) ? n : 20;
}

export function parseGoal(v: string | null | undefined): PracticeGoal {
  return v === "weak" || v === "challenge" || v === "balanced" ? v : "balanced";
}

/**
 * Topic ids from a link (`a,b`) matched against the subject's topics. A requested id matches a topic when equal or
 * when it is the topic id's last dotted part. Unknown ids are dropped (`dropped` > 0 tells the page to say so).
 */
export function matchTopics(requested: string[], subject: PracticeSubject | undefined): { ids: string[]; dropped: number } {
  if (!subject || requested.length === 0) return { ids: [], dropped: 0 };
  const ids: string[] = [];
  for (const r of requested) {
    const t = subject.topics.find((x) => x.id === r || x.id.split(".").pop() === r);
    if (t && !ids.includes(t.id)) ids.push(t.id);
  }
  return { ids, dropped: requested.length - ids.length };
}

export function splitParam(v: string | null | undefined): string[] {
  return (v ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/** `12 câu · khoảng 20 phút` */
export function previewSummary(p: Pick<PracticePreview, "item_count" | "minutes">): string {
  return `${p.item_count} câu · khoảng ${p.minutes} phút`;
}

/** Share of each difficulty level for the preview bar (zero levels omitted). */
export function levelShares(mix: number[]): { level: number; n: number; pct: number }[] {
  const total = mix.reduce((a, b) => a + b, 0) || 1;
  return mix.map((n, i) => ({ level: i + 1, n, pct: (n / total) * 100 })).filter((x) => x.n > 0);
}
