import { describe, expect, it } from "vitest";
import { band, groupByTopic, progressLabel, reasonText, sparkPoints, splitRecommendations, trendSummary } from "./progress";
import { PROGRESS_LABELS, type ProgressSkill, type Recommendation } from "./progressTypes";
import { actionRoute } from "./routes";

const skill = (o: Partial<ProgressSkill>): ProgressSkill => ({
  skill_id: "s",
  title: "S",
  topic: "T",
  mastery: 0.5,
  evidence: 5,
  confidence: "medium",
  label: "",
  trend: [],
  ...o,
});

describe("progressLabel", () => {
  it("keeps the server's contract labels", () => {
    for (const l of PROGRESS_LABELS) expect(progressLabel({ mastery: 0.5, evidence: 5, label: l })).toBe(l);
  });
  it("maps unknown labels from mastery and evidence, never 'yếu'", () => {
    expect(progressLabel({ mastery: 0.2, evidence: 0, label: "?" })).toBe("Chưa có dữ liệu");
    expect(progressLabel({ mastery: 0.2, evidence: 2, label: "?" })).toBe("Cần thêm dữ liệu");
    expect(progressLabel({ mastery: 0.2, evidence: 6, label: "yếu" })).toBe("Cần củng cố");
    expect(progressLabel({ mastery: 0.6, evidence: 6, label: "" })).toBe("Đang tiến bộ");
    expect(progressLabel({ mastery: 0.9, evidence: 6, label: "" })).toBe("Vững");
    expect(PROGRESS_LABELS.join(" ").toLowerCase()).not.toContain("yếu");
  });
});

describe("band (confidence -> uncertainty)", () => {
  it("is narrower for higher confidence", () => {
    const w = (c: "high" | "medium" | "low") => {
      const b = band({ mastery: 0.5, confidence: c, evidence: 5 });
      return b.hi - b.lo;
    };
    expect(w("high")).toBeLessThan(w("medium"));
    expect(w("medium")).toBeLessThan(w("low"));
  });
  it("stays within 0..1", () => {
    expect(band({ mastery: 0.98, confidence: "low", evidence: 5 }).hi).toBe(1);
    expect(band({ mastery: 0.02, confidence: "low", evidence: 5 }).lo).toBe(0);
  });
});

describe("groupByTopic", () => {
  it("weights topic mastery by evidence and labels no-evidence topics", () => {
    const g = groupByTopic([
      skill({ skill_id: "a", topic: "A", mastery: 0.9, evidence: 9 }),
      skill({ skill_id: "b", topic: "A", mastery: 0.1, evidence: 1 }),
      skill({ skill_id: "c", topic: "B", mastery: 0.5, evidence: 0 }),
    ]);
    const a = g.find((x) => x.topic === "A")!;
    expect(a.mastery).toBeCloseTo(0.82, 2);
    expect(a.label).toBe("Vững");
    const b = g.find((x) => x.topic === "B")!;
    expect(b.mastery).toBeNull();
    expect(b.label).toBe("Chưa có dữ liệu");
  });
});

describe("sparkline", () => {
  it("draws a flat line for one point and nothing for none", () => {
    expect(sparkPoints([])).toBe("");
    expect(sparkPoints([{ mastery: 0.5 }]).split(" ")).toHaveLength(2);
  });
  it("higher mastery is higher on screen (smaller y)", () => {
    const [a, b] = sparkPoints([{ mastery: 0.2 }, { mastery: 0.8 }]).split(" ");
    expect(Number(b.split(",")[1])).toBeLessThan(Number(a.split(",")[1]));
  });
  it("summarises the trend in words", () => {
    expect(trendSummary([{ mastery: 0.3 }, { mastery: 0.5 }])).toContain("tăng 20");
    expect(trendSummary([{ mastery: 0.5 }, { mastery: 0.5 }])).toBe("gần như không đổi");
    expect(trendSummary([{ mastery: 0.5 }])).toContain("chưa đủ");
  });
});

const rec = (code: string, kind: Recommendation["action"]["kind"], extra: Partial<Recommendation> = {}): Recommendation => ({
  code,
  title: code,
  reason: "r",
  action: { kind },
  ...extra,
});

describe("recommendations", () => {
  it("caps steps at 3 and splits TAKE_A_BREAK off", () => {
    const { steps, rest } = splitRecommendations([
      rec("PRACTICE_WEAK", "practice"),
      rec("TAKE_A_BREAK", "break"),
      rec("TAKE_MOCK", "mock"),
      rec("PROBE_UNKNOWN", "practice"),
      rec("CHALLENGE_STRONG", "practice"),
    ]);
    expect(rest?.code).toBe("TAKE_A_BREAK");
    expect(steps.map((s) => s.code)).toEqual(["PRACTICE_WEAK", "TAKE_MOCK", "PROBE_UNKNOWN"]);
  });
  it("prefixes the reason with 'Vì sao:' once", () => {
    expect(reasonText("bài này còn mới")).toBe("Vì sao: bài này còn mới");
    expect(reasonText("Vì sao: đã có")).toBe("Vì sao: đã có");
  });
  it("routes actions with params into W1's screens; break has no route", () => {
    expect(actionRoute({ kind: "practice", params: { subject: "math", minutes: 20, goal: "weak", topics: ["a", "b"] } })).toBe(
      "/practice?subject=math&minutes=20&goal=weak&topics=a%2Cb",
    );
    expect(actionRoute({ kind: "mock", params: { profile_id: "math.mcq-mock.2026" } }, "math")).toBe("/practice/mock?subject=math&profile_id=math.mcq-mock.2026");
    expect(actionRoute({ kind: "diagnostic" }, "english")).toBe("/practice/diagnostic?subject=english");
    expect(actionRoute({ kind: "progress" }, "physics")).toBe("/progress?subject=physics");
    expect(actionRoute({ kind: "break" })).toBeNull();
  });
});
