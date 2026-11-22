import { describe, expect, it } from "vitest";
import type { PItem } from "./api";
import { createMockPractice } from "./api/mock-practice-api";
import { canCheck, clockText, firstSentence, fmtScore10, handInStats, initialRemaining, resumePosition, shown, tfDecode, tfEncode, unfinished } from "./lib/practice";

const item = (p: Partial<PItem> & Pick<PItem, "type">): PItem => ({ position: 0, id: "x", stem: "s", topic: "t", topic_title: "T", ...p });
const tf = item({ type: "TRUE_FALSE_GROUP", statements: [{ id: "a", text: "A" }, { id: "b", text: "B" }, { id: "c", text: "C" }] });

describe("scoring display per type", () => {
  it("encodes true/false groups of 3 and 4 statements", () => {
    expect(tfEncode(tf, { a: true, b: false })).toBe("TF-");
    expect(tfDecode(tf, "TFT")).toEqual({ a: true, b: false, c: true });
    expect(tfDecode(tf, "ĐSĐ")).toEqual({ a: true, b: false, c: true });
    expect(canCheck(tf, "TF-")).toBe(false);
    expect(canCheck(tf, "TFT")).toBe(true);
    expect(canCheck(item({ type: "TAP_COUNT" }), "0")).toBe(false);
    expect(canCheck(item({ type: "TAP_COUNT" }), "7")).toBe(true);
    expect(canCheck(item({ type: "SHORT_ANSWER" }), "  ")).toBe(false);
  });

  it("choice, count and short answer are right or wrong; a blank is a skip", () => {
    for (const type of ["SINGLE_CHOICE", "PICTURE_CHOICE", "TAP_COUNT", "SHORT_ANSWER"] as const) {
      expect(shown({ type }, { correct: true, points: 1, max_points: 1 }).outcome).toBe("right");
      expect(shown({ type }, { correct: false, points: 0, max_points: 1 }).outcome).toBe("wrong");
      expect(shown({ type }, { correct: null }).outcome).toBe("blank");
    }
  });

  it("a true/false group can be partly right, with the statement tally", () => {
    const r = { correct: false, points: 0.25, max_points: 1, statement_results: [{ id: "a", correct: true }, { id: "b", correct: false }, { id: "c", correct: true }] };
    expect(shown(tf, r)).toMatchObject({ outcome: "partial", points: 0.25, tally: { right: 2, total: 3 } });
    expect(shown(tf, { correct: false, points: 0, max_points: 1, statement_results: [{ id: "a", correct: false }] }).outcome).toBe("wrong");
    expect(shown(tf, { correct: true, points: 1, max_points: 1, statement_results: [{ id: "a", correct: true }] }).outcome).toBe("right");
  });

  it("formats scores and keeps the red-pen explanation to one sentence", () => {
    expect(fmtScore10(7.25, "vi")).toBe("7,25");
    expect(fmtScore10(7.25, "en")).toBe("7.25");
    expect(fmtScore10(8, "vi")).toBe("8");
    expect(firstSentence("Em để r theo cm. Đổi 3 cm = 0,03 m trước.")).toBe("Em để r theo cm.");
    expect(firstSentence("E = 9·10⁹ · 4·10⁻⁹ / 0,03² = 4·10⁴ V/m")).toContain("4·10⁴");
    expect(clockText(3725)).toBe("1:02:05");
    expect(clockText(59)).toBe("00:59");
  });
});

describe("mock clock and resume rules", () => {
  it("takes seconds left from the server, else from the deadline", () => {
    const now = Date.parse("2026-11-07T10:00:00Z");
    const base = { id: "m", subject: "s", started_at: "", position: 0, items: [item({ type: "SINGLE_CHOICE" })], answers: {} };
    expect(initialRemaining({ ...base, kind: "mock", deadline: "2026-11-07T10:10:00Z" }, now)).toBe(600);
    expect(initialRemaining({ ...base, kind: "mock", deadline: "2026-11-07T10:10:00Z", remaining_sec: 540 }, now)).toBe(540);
    expect(initialRemaining({ ...base, kind: "mock", deadline: "2026-11-07T09:00:00Z" }, now)).toBe(0);
    expect(initialRemaining({ ...base, kind: "practice" }, now)).toBeNull();
  });

  it("resumes practice at the first item not checked and a mock where the learner left", () => {
    const items = [0, 1, 2].map((position) => item({ type: "SINGLE_CHOICE", position }));
    const p = { id: "p", kind: "practice" as const, subject: "quick", started_at: "", position: 0, items, answers: { "0": { checked: true }, "1": { checked: true } } };
    expect(resumePosition(p)).toBe(2);
    expect(resumePosition({ ...p, kind: "mock", position: 1 })).toBe(1);
    expect(unfinished({ ...p, status: "finished" })).toBe(false);
    expect(unfinished(p)).toBe(true);
  });

  it("counts empty and flagged items before hand-in", () => {
    const items = [0, 1, 2].map((position) => item({ type: "SINGLE_CHOICE", position }));
    const s = { id: "m", kind: "mock" as const, subject: "s", started_at: "", position: 0, items, answers: {} };
    expect(handInStats(s, { 0: "A", 1: "" }, { 1: true })).toEqual({ total: 3, blank: 2, flagged: 1, answered: 1 });
  });
});

// The practice screens (quick session, mock, fix flow, resume, kid run) moved to the Làng gà runner: see
// src/lang/screens/arena/arena.test.tsx.

describe("mock practice banks", () => {
  it("gives every age band its own items, in the learner's language", async () => {
    const stem = async (age_band: string, language: string) => (await createMockPractice({ learner: () => ({ age_band, language }) }).start("t", { source: "quick" })).items[0].stem;
    expect(await stem("g1_5", "vi")).toBe("Bao nhiêu quả táo trong 2 + 3?");
    expect(await stem("g6_9", "en")).toBe("Which fraction is the largest?");
    expect(await stem("g10_12", "vi")).toContain("Cấp số cộng");
    expect(await stem("uni", "vi")).toContain("Cấp số cộng");
  });
});
