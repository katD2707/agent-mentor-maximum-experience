import { PROGRESS_LABELS, type Confidence, type ProgressLabel, type ProgressSkill, type Recommendation } from "./progressTypes";

export const SUBJECT_NAMES: Record<string, string> = {
  math: "Toán",
  physics: "Vật lý",
  english: "Tiếng Anh",
  chemistry: "Hoá học",
  biology: "Sinh học",
  literature: "Ngữ văn",
};
export const subjectName = (id: string) => SUBJECT_NAMES[id] ?? id;

/** Never "yếu": unknown labels from the server are mapped by mastery/evidence instead. */
export function progressLabel(s: Pick<ProgressSkill, "mastery" | "evidence" | "label">): ProgressLabel {
  if ((PROGRESS_LABELS as readonly string[]).includes(s.label)) return s.label as ProgressLabel;
  if (s.evidence <= 0) return "Chưa có dữ liệu";
  if (s.evidence < 3) return "Cần thêm dữ liệu";
  if (s.mastery < 0.5) return "Cần củng cố";
  if (s.mastery < 0.8) return "Đang tiến bộ";
  return "Vững";
}

/** Half-width of the uncertainty band around the mastery value, 0..1. */
export function uncertaintyHalfWidth(c: Confidence, evidence: number): number {
  if (evidence <= 0) return 0.5;
  return c === "high" ? 0.06 : c === "medium" ? 0.14 : 0.26;
}

export function band(s: Pick<ProgressSkill, "mastery" | "confidence" | "evidence">): { lo: number; hi: number } {
  const w = uncertaintyHalfWidth(s.confidence, s.evidence);
  return { lo: Math.max(0, s.mastery - w), hi: Math.min(1, s.mastery + w) };
}

export const CONFIDENCE_TEXT: Record<Confidence, string> = {
  high: "Khá chắc",
  medium: "Tương đối chắc",
  low: "Còn ít bằng chứng",
};

export type LabelTone = "none" | "few" | "work" | "grow" | "strong";
export function labelTone(l: ProgressLabel): LabelTone {
  return l === "Chưa có dữ liệu" ? "none" : l === "Cần thêm dữ liệu" ? "few" : l === "Cần củng cố" ? "work" : l === "Đang tiến bộ" ? "grow" : "strong";
}

/** SVG polyline points for a sparkline, `w`x`h`, mastery 0..1 mapped to full height. */
export function sparkPoints(trend: { mastery: number }[], w = 80, h = 22): string {
  if (trend.length === 0) return "";
  const pts = trend.length === 1 ? [trend[0], trend[0]] : trend;
  return pts
    .map((p, i) => {
      const x = (i / (pts.length - 1)) * w;
      const y = h - Math.max(0, Math.min(1, p.mastery)) * (h - 2) - 1;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function trendSummary(trend: { mastery: number }[]): string {
  if (trend.length < 2) return "chưa đủ điểm để xem xu hướng";
  const d = trend[trend.length - 1].mastery - trend[0].mastery;
  if (d > 0.03) return `tăng ${Math.round(d * 100)} điểm phần trăm`;
  if (d < -0.03) return `giảm ${Math.round(-d * 100)} điểm phần trăm`;
  return "gần như không đổi";
}

export interface TopicGroup {
  topic: string;
  skills: ProgressSkill[];
  mastery: number | null;
  evidence: number;
  label: ProgressLabel;
}

/** Topic mastery = mean of its skills weighted by evidence (CONTRACTS 10.4); no evidence = "Chưa có dữ liệu". */
export function groupByTopic(skills: ProgressSkill[]): TopicGroup[] {
  const map = new Map<string, ProgressSkill[]>();
  for (const s of skills) {
    const k = s.topic || "Khác";
    map.set(k, [...(map.get(k) ?? []), s]);
  }
  return [...map.entries()].map(([topic, list]) => {
    const evidence = list.reduce((a, s) => a + s.evidence, 0);
    const mastery = evidence > 0 ? list.reduce((a, s) => a + s.mastery * s.evidence, 0) / evidence : null;
    const label = progressLabel({ mastery: mastery ?? 0, evidence, label: "" });
    return { topic, skills: list, mastery, evidence, label };
  });
}

/** At most 3 steps; TAKE_A_BREAK is split off for its own gentle card. */
export function splitRecommendations(recs: Recommendation[]): { steps: Recommendation[]; rest: Recommendation | null } {
  const rest = recs.find((r) => r.code === "TAKE_A_BREAK" || r.action.kind === "break") ?? null;
  const steps = recs.filter((r) => r !== rest).slice(0, 3);
  return { steps, rest };
}

export function reasonText(reason: string): string {
  return /^vì sao\s*:/i.test(reason.trim()) ? reason.trim() : `Vì sao: ${reason.trim()}`;
}
