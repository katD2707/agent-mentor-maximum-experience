/**
 * Mock data for the progress endpoints (CONTRACTS 10.3: /practice/progress, /recommendations, /sessions).
 * W1 owns the rest of the practice mocks; these three are W2's. Deterministic, no randomness.
 */
import type { Progress, ProgressSkill, Recommendation, SessionSummary } from "../../practice/progressTypes";

type Seed = [id: string, title: string, topic: string, mastery: number, evidence: number, confidence: "high" | "medium" | "low", label: string];

const SEEDS: Record<string, Seed[]> = {
  math: [
    ["math.func.monotone", "Xét tính đơn điệu của hàm số", "Hàm số", 0.82, 14, "high", "Vững"],
    ["math.func.extrema", "Tìm cực trị", "Hàm số", 0.58, 9, "medium", "Đang tiến bộ"],
    ["math.explog.equations", "Phương trình mũ và logarit", "Mũ - Logarit", 0.34, 8, "medium", "Cần củng cố"],
    ["math.explog.inequality", "Bất phương trình logarit", "Mũ - Logarit", 0.5, 2, "low", "Cần thêm dữ liệu"],
    ["math.geo.volume", "Thể tích khối đa diện", "Hình học không gian", 0.5, 0, "low", "Chưa có dữ liệu"],
  ],
  physics: [
    ["phys.osc.shm", "Dao động điều hòa", "Dao động cơ", 0.66, 6, "medium", "Đang tiến bộ"],
    ["phys.osc.pendulum", "Con lắc lò xo, con lắc đơn", "Dao động cơ", 0.41, 4, "low", "Cần củng cố"],
  ],
  english: [
    ["eng.tense", "Thì của động từ", "Ngữ pháp", 0.5, 0, "low", "Chưa có dữ liệu"],
    ["eng.cloze", "Điền từ vào đoạn văn", "Đọc hiểu", 0.5, 0, "low", "Chưa có dữ liệu"],
  ],
};

function trendFor(mastery: number, evidence: number, now: number): { at: string; mastery: number }[] {
  const n = Math.min(8, evidence);
  if (n === 0) return [];
  const start = Math.max(0.2, mastery - 0.18);
  return Array.from({ length: n }, (_, i) => ({
    at: new Date(now - (n - 1 - i) * 3 * 86_400_000).toISOString(),
    mastery: Math.round((start + ((mastery - start) * i) / Math.max(1, n - 1)) * 100) / 100,
  }));
}

export function mockProgress(subject: string | undefined, now: number): Progress {
  const ids = subject ? [subject] : Object.keys(SEEDS);
  const skills: ProgressSkill[] = ids.flatMap((id) =>
    (SEEDS[id] ?? []).map(([skill_id, title, topic, mastery, evidence, confidence, label]) => ({
      skill_id,
      title,
      topic,
      mastery,
      evidence,
      confidence,
      label,
      trend: trendFor(mastery, evidence, now),
    })),
  );
  return { skills };
}

export function mockRecommendations(subject: string | undefined, now: number): Recommendation[] {
  const all: Recommendation[] = [
    {
      code: "PRACTICE_WEAK",
      subject: "math",
      title: "Luyện 20 phút Mũ - Logarit",
      reason: "Vì sao: phần này còn ít bài làm đúng, luyện ngắn sẽ giúp củng cố nhanh.",
      action: { kind: "practice", params: { subject: "math", minutes: 20, goal: "weak", topics: ["explog"] } },
    },
    {
      code: "TAKE_DIAGNOSTIC",
      subject: "english",
      title: "Làm bài chẩn đoán Tiếng Anh",
      reason: "Vì sao: mình chưa có dữ liệu nào về môn này, 12 câu ngắn là đủ để bắt đầu.",
      action: { kind: "diagnostic", params: { subject: "english" } },
    },
    {
      code: "TAKE_MOCK",
      subject: "math",
      title: "Thử một đề thi thử Toán",
      reason: "Vì sao: bạn đã luyện đều tuần này, đề thi thử giúp làm quen nhịp thời gian.",
      action: { kind: "mock", params: { subject: "math" } },
    },
  ];
  const list = subject ? all.filter((r) => r.subject === subject) : all;
  void now;
  return list.slice(0, 3);
}

export function mockSessions(subject: string | undefined, limit: number, now: number): SessionSummary[] {
  const list: SessionSummary[] = Array.from({ length: 6 }, (_, i) => {
    const subj = i % 3 === 2 ? "physics" : "math";
    const total = i % 2 === 0 ? 10 : 12;
    const correct = Math.max(3, total - 2 - (i % 4));
    const started = now - (i + 1) * 36 * 3_600_000;
    return {
      id: `p-mock-${i + 1}`,
      kind: i === 3 ? "mock" : "practice",
      subject: subj,
      started_at: new Date(started).toISOString(),
      finished_at: new Date(started + 20 * 60_000).toISOString(),
      score_10: Math.round((correct / total) * 1000) / 100,
      correct,
      total,
      minutes: 20,
    } satisfies SessionSummary;
  });
  return list.filter((s) => !subject || s.subject === subject).slice(0, limit);
}
