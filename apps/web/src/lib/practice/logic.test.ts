import { describe, expect, it } from "vitest";
import {
  blockedFrom,
  canCheck,
  cycleStatement,
  decodeTF,
  earnsConfetti,
  encodeTF,
  errorCode,
  feedbackHeadline,
  formatClock,
  formatPoints,
  formatScore10,
  initialElapsed,
  isOver,
  keyAction,
  masteryChange,
  nextStreak,
  normalizeShortAnswerInput,
  optionIndexForKey,
  parseShortAnswer,
  partCounts,
  segmentStates,
  setStatement,
  shouldAutoSubmit,
  shouldTick,
  statementOutcome,
  submitCounts,
  submitMessage,
  summaryHeadline,
  timeLimitOf,
  timerView,
  type KeyContext,
} from "./logic";
import type { Report } from "./types";

const ctx = (o: Partial<KeyContext> = {}): KeyContext => ({ mode: "practice", phase: "answering", itemType: "SINGLE_CHOICE", optionCount: 4, hasHint: true, typing: false, modalOpen: false, ...o });
const key = (k: string) => ({ key: k });

describe("short-answer input", () => {
  it("keeps digits, one comma, a leading minus, and the answer-sheet width", () => {
    expect(normalizeShortAnswerInput("12,5", 4)).toBe("12,5");
    expect(normalizeShortAnswerInput("0.69", 4)).toBe("0,69");
    expect(normalizeShortAnswerInput("−0,5", 4)).toBe("-0,5");
    expect(normalizeShortAnswerInput("1,2,3", 8)).toBe("1,23");
    expect(normalizeShortAnswerInput("12-3", 8)).toBe("123");
    expect(normalizeShortAnswerInput("abc7x", 4)).toBe("7");
    expect(normalizeShortAnswerInput("123456", 4)).toBe("1234");
    expect(normalizeShortAnswerInput("123456", null)).toBe("123456");
  });

  it("parses to the sheet form or null", () => {
    expect(parseShortAnswer("0.5")).toBe("0,5");
    expect(parseShortAnswer("-0,25")).toBe("-0,25");
    expect(parseShortAnswer("300 K", "K")).toBe("300");
    expect(parseShortAnswer(",5")).toBe("0,5");
    expect(parseShortAnswer("-")).toBeNull();
    expect(parseShortAnswer("1,2,3")).toBeNull();
    expect(parseShortAnswer("")).toBeNull();
  });

  it("enables Kiểm tra only for a number", () => {
    expect(canCheck("SHORT_ANSWER", "-", {})).toBe(false);
    expect(canCheck("SHORT_ANSWER", "12", {})).toBe(true);
    expect(canCheck("SINGLE_CHOICE", null)).toBe(false);
    expect(canCheck("TRUE_FALSE_GROUP", "T---")).toBe(true);
  });
});

describe("true/false groups", () => {
  it("encodes and cycles statements", () => {
    expect(encodeTF([true, false, null, true])).toBe("TF-T");
    expect(decodeTF("TF-T")).toEqual([true, false, null, true]);
    expect(decodeTF("garbage")).toEqual([null, null, null, null]);
    let a: string | null = null;
    a = cycleStatement(a, 1);
    expect(a).toBe("-T--");
    a = cycleStatement(a, 1);
    expect(a).toBe("-F--");
    a = cycleStatement(a, 1);
    expect(a).toBe("-T--");
    expect(setStatement("-T--", 1, null)).toBeNull();
  });

  it("reads both shapes of statement results", () => {
    expect(statementOutcome([true, false, { correct: true }, { correct: false }])).toEqual([true, false, true, false]);
    expect(statementOutcome(null)).toEqual([null, null, null, null]);
  });
});

describe("keyboard map", () => {
  it("1-4 and A-D select, within the option count", () => {
    expect(optionIndexForKey("3")).toBe(2);
    expect(optionIndexForKey("c")).toBe(2);
    expect(optionIndexForKey("D")).toBe(3);
    expect(optionIndexForKey("5")).toBeNull();
    expect(keyAction(key("2"), ctx())).toEqual({ type: "select", index: 1 });
    expect(keyAction(key("D"), ctx({ optionCount: 3 }))).toBeNull();
    expect(keyAction(key("4"), ctx({ itemType: "TRUE_FALSE_GROUP", optionCount: 0 }))).toEqual({ type: "select", index: 3 });
  });

  it("Enter checks, H hints only before the check, E reveals only after", () => {
    expect(keyAction(key("Enter"), ctx())).toEqual({ type: "primary" });
    expect(keyAction(key("h"), ctx())).toEqual({ type: "hint" });
    expect(keyAction(key("h"), ctx({ phase: "feedback" }))).toBeNull();
    expect(keyAction(key("h"), ctx({ hasHint: false }))).toBeNull();
    expect(keyAction(key("e"), ctx())).toBeNull();
    expect(keyAction(key("E"), ctx({ phase: "feedback" }))).toEqual({ type: "reveal" });
    expect(keyAction(key("s"), ctx())).toEqual({ type: "skip" });
    expect(keyAction(key("s"), ctx({ phase: "feedback" }))).toBeNull();
    expect(keyAction(key("l"), ctx())).toBeNull();
    expect(keyAction(key("l"), ctx({ phase: "feedback" }))).toEqual({ type: "report" });
  });

  it("mock: F flags, G opens the grid, arrows navigate, no hint/skip/reveal", () => {
    const m = ctx({ mode: "mock" });
    expect(keyAction(key("f"), m)).toEqual({ type: "flag" });
    expect(keyAction(key("G"), m)).toEqual({ type: "grid" });
    expect(keyAction(key("ArrowLeft"), m)).toEqual({ type: "prev" });
    expect(keyAction(key("ArrowRight"), m)).toEqual({ type: "next" });
    expect(keyAction(key("h"), m)).toBeNull();
    expect(keyAction(key("s"), m)).toBeNull();
    expect(keyAction(key("l"), m)).toBeNull();
    expect(keyAction(key("f"), ctx())).toBeNull();
    expect(keyAction(key("ArrowRight"), ctx())).toBeNull();
  });

  it("typing in the answer box leaves only Enter and Esc; dialogs and modifiers own the keyboard", () => {
    const t = ctx({ typing: true, itemType: "SHORT_ANSWER" });
    expect(keyAction(key("1"), t)).toBeNull();
    expect(keyAction(key("h"), t)).toBeNull();
    expect(keyAction(key("Enter"), t)).toEqual({ type: "primary" });
    expect(keyAction(key("Escape"), t)).toEqual({ type: "pause" });
    expect(keyAction(key("1"), ctx({ itemType: "SHORT_ANSWER" }))).toBeNull();
    expect(keyAction(key("Enter"), ctx({ modalOpen: true }))).toBeNull();
    expect(keyAction({ key: "1", ctrlKey: true }, ctx())).toBeNull();
  });

  it("review is read-only", () => {
    const r = ctx({ mode: "review", phase: "feedback" });
    expect(keyAction(key("1"), r)).toBeNull();
    expect(keyAction(key("ArrowRight"), r)).toEqual({ type: "next" });
    expect(keyAction(key("l"), r)).toEqual({ type: "report" });
  });
});

describe("timer and auto-submit", () => {
  it("counts down for a mock with warn at 5 minutes and urgent at 1", () => {
    expect(timerView(0, 600)).toMatchObject({ shown: 600, counting: "down", warn: false, expired: false });
    expect(timerView(300, 600)).toMatchObject({ shown: 300, warn: true, urgent: false });
    expect(timerView(541, 600)).toMatchObject({ shown: 59, warn: true, urgent: true });
    expect(timerView(600, 600)).toMatchObject({ shown: 0, expired: true, warn: false });
    expect(timerView(700, 600).shown).toBe(0);
  });

  it("counts up for practice, never warns", () => {
    expect(timerView(125, null)).toEqual({ shown: 125, counting: "up", expired: false, warn: false, urgent: false });
  });

  it("auto-submits a mock exactly at the deadline, never practice", () => {
    expect(shouldAutoSubmit("mock", 599, 600)).toBe(false);
    expect(shouldAutoSubmit("mock", 600, 600)).toBe(true);
    expect(shouldAutoSubmit("practice", 9999, null)).toBe(false);
    expect(shouldAutoSubmit("diagnostic", 9999, 900)).toBe(false);
  });

  it("autosaves every 5 seconds and at the deadline", () => {
    expect(shouldTick(5, 600)).toBe(true);
    expect(shouldTick(7, 600)).toBe(false);
    expect(shouldTick(601, 600)).toBe(true);
  });

  it("resumes from remaining_sec, the deadline, or elapsed", () => {
    expect(initialElapsed({ remaining_sec: 200 }, 600, 0)).toBe(400);
    expect(initialElapsed({ elapsed_sec: 42, remaining_sec: 1 }, 600, 0)).toBe(42);
    const now = Date.parse("2026-11-06T10:00:00Z");
    expect(initialElapsed({ deadline: "2026-11-06T10:05:00Z" }, 600, now)).toBe(300);
    expect(initialElapsed({}, null, now)).toBe(0);
    expect(timeLimitOf({ kind: "mock", started_at: "2026-11-06T10:00:00Z", deadline: "2026-11-06T10:10:00Z" })).toBe(600);
    expect(timeLimitOf({ kind: "practice", started_at: "x" })).toBeNull();
  });

  it("formats the clock", () => {
    expect(formatClock(0)).toBe("00:00");
    expect(formatClock(65)).toBe("01:05");
    expect(formatClock(5400)).toBe("1:30:00");
  });
});

describe("gateway errors and states", () => {
  it("reads the error code and the active-session block", () => {
    expect(errorCode({ detail: "x", code: "expired" })).toBe("expired");
    expect(errorCode(null)).toBeNull();
    expect(blockedFrom({ status: 409, body: { code: "active_session", session_id: "p-1", kind: "mock" } })).toEqual({ id: "p-1", kind: "mock" });
    expect(blockedFrom({ status: 409, body: { code: "finished" } })).toBeNull();
    expect(blockedFrom({ status: 500, body: { code: "active_session", session_id: "x" } })).toBeNull();
  });

  it("a finished, expired or abandoned session goes to its summary", () => {
    expect(isOver({ status: "active" })).toBe(false);
    expect(isOver({})).toBe(false);
    expect(isOver({ status: "expired" })).toBe(true);
    expect(isOver({ finished: true })).toBe(true);
  });

  it("reads both spellings of a part result", () => {
    expect(partCounts({ part: 2, label: "Phần II · Đúng/Sai", total: 4, correct: 3, points: 1, max_points: 4 })).toEqual({ items: 4, fullyCorrect: 3, truefalse: true });
    expect(partCounts({ label: "Phần I", items: 12, fully_correct: 9, points: 1, max_points: 3 })).toEqual({ items: 12, fullyCorrect: 9, truefalse: false });
  });
});

describe("score display", () => {
  it("uses a decimal comma and no trailing zeros", () => {
    expect(formatPoints(0.25)).toBe("0,25");
    expect(formatPoints(1)).toBe("1");
    expect(formatPoints(0.1)).toBe("0,1");
    expect(formatScore10(7.25)).toBe("7,25");
    expect(formatScore10(10)).toBe("10,00");
  });

  it("headlines a true/false group by the number of right statements", () => {
    expect(feedbackHeadline("TRUE_FALSE_GROUP", { correct: true, points: 1, max_points: 1, right: 4, keyLabel: "" })).toBe("Chính xác cả 4 ý! · 1 điểm");
    expect(feedbackHeadline("TRUE_FALSE_GROUP", { correct: false, points: 0.25, max_points: 1, right: 2, keyLabel: "" })).toBe("Đúng 2/4 ý · 0,25/1 điểm");
    expect(feedbackHeadline("SINGLE_CHOICE", { correct: false, keyLabel: "B" })).toBe("Chưa đúng, đáp án đúng là B");
    expect(feedbackHeadline("SHORT_ANSWER", { correct: true, keyLabel: "0,69" })).toBe("Chính xác!");
  });

  it("shows mastery before to after with the gateway's label", () => {
    expect(masteryChange({ mastery_before: 0.4, mastery_after: 0.55, label: "Đang tiến bộ" })).toEqual({ text: "40% → 55% (▲ +15%)", direction: "up" });
    expect(masteryChange({ mastery_before: 0.6, mastery_after: 0.5, label: "Cần củng cố" }).direction).toBe("down");
    expect(masteryChange({ mastery_before: null, mastery_after: 0.5, label: "Cần thêm dữ liệu" }).text).toBe("mới: 50%");
    expect(masteryChange({ mastery_before: null, mastery_after: null, label: "Chưa có dữ liệu" }).text).toBe("Chưa có dữ liệu");
  });

  const rep = (o: Partial<Report>): Report => ({ session: { id: "s", kind: "practice", subject: "math" }, correct: 6, total: 10, answered: 10, minutes: 5, hints: 0, per_topic: [], recommendations: [], ...o });
  it("confetti from 60 % and never for an empty session", () => {
    expect(earnsConfetti(rep({ correct: 6 }), "practice")).toBe(true);
    expect(earnsConfetti(rep({ correct: 5 }), "practice")).toBe(false);
    expect(earnsConfetti(rep({ correct: 0, answered: 0 }), "practice")).toBe(false);
    expect(earnsConfetti(rep({ correct: 5, answered: 6, total: 10 }), "mock")).toBe(false);
    expect(summaryHeadline(rep({ correct: 9 }), "practice")).toBe("Xuất sắc!");
    expect(summaryHeadline(rep({ correct: 1, answered: 2 }), "practice")).toBe("Khởi động tốt!");
    expect(summaryHeadline(rep({}), "diagnostic")).toBe("Xong phần đánh giá!");
  });

  it("streak rises on a right answer and resets on a wrong one", () => {
    expect(nextStreak(2, true)).toBe(3);
    expect(nextStreak(5, false)).toBe(0);
  });
});

describe("progress segments and the submit dialog", () => {
  const items = [0, 1, 2, 3].map((position) => ({ position }));
  it("marks correct/wrong in practice but hides them in a mock", () => {
    const answers = { "0": { answer: "A", correct: true }, "1": { answer: "B", correct: false }, "2": { flagged: true }, "3": {} };
    expect(segmentStates(items, answers, "practice")).toEqual(["correct", "wrong", "flagged", "empty"]);
    expect(segmentStates(items, answers, "mock")).toEqual(["answered", "answered", "flagged", "empty"]);
  });

  it("counts unanswered and flagged for the dialog", () => {
    const c = submitCounts(items, { "0": { answer: "A" }, "1": { draft: "B", flagged: true }, "2": { flagged: true } });
    expect(c).toEqual({ unanswered: 2, flagged: 2 });
    expect(submitMessage(c)).toBe("Còn 2 câu chưa trả lời (tính 0 điểm). 2 câu đang được đánh dấu xem lại.");
    expect(submitMessage({ unanswered: 0, flagged: 0 })).toBe("Bạn đã trả lời tất cả các câu.");
  });
});
