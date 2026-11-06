import { describe, expect, it } from "vitest";
import type { DeadlineCard, FlashcardCard, FocusCard } from "../types";
import {
  cardActionFor,
  cardReducer,
  countdown,
  countdownTickMs,
  deadlineTone,
  eventFromCardAction,
  focusProgress,
  formatClock,
  formatCountdown,
  formatDue,
  gradeFlashcard,
  mergeCardUpdate,
} from "./cards";

const flash: FlashcardCard = {
  id: "card-20261103-aaaaaaaaaaaa",
  kind: "flashcard",
  created_at: "2026-11-03T20:00:00+07:00",
  skill: "Bất phương trình bậc hai",
  front: "Tập nghiệm của x² − 5x + 6 < 0 là?",
  choices: ["(2; 3)", "(−∞; 2) ∪ (3; +∞)", "[2; 3]"],
  reveal: "(2; 3): tam thức âm giữa hai nghiệm.",
};

const focus: FocusCard = {
  id: "card-20261103-bbbbbbbbbbbb",
  kind: "focus",
  created_at: "2026-11-03T20:00:00+07:00",
  task: "Ôn bài",
  minutes: 25,
  ends_at: "2026-11-03T20:25:00+07:00",
};
const START = Date.parse("2026-11-03T20:00:00+07:00");

describe("flashcard", () => {
  it("grades by the choice text or the leading letter in reveal, else stays neutral", () => {
    expect(gradeFlashcard(flash, "(2; 3)")).toBe(true);
    expect(gradeFlashcard(flash, "[2; 3]")).toBe(false);
    expect(gradeFlashcard({ ...flash, reveal: "B. Ngoài khoảng hai nghiệm" }, "(−∞; 2) ∪ (3; +∞)")).toBe(true);
    expect(gradeFlashcard({ ...flash, reveal: "Nghĩ về dấu của a" }, "(2; 3)")).toBeNull();
    expect(gradeFlashcard({ ...flash, reveal: undefined }, "(2; 3)")).toBeNull();
  });

  it("sends the answer as the choice letter, skip without a value", () => {
    expect(cardActionFor(flash, { type: "flash_choose", value: "[2; 3]" })).toEqual({ action: "answer", value: "C" });
    expect(cardActionFor(flash, { type: "flash_skip" })).toEqual({ action: "skip" });
    expect(cardActionFor(flash, { type: "celebration_played" })).toBeNull();
  });

  it("takes one answer per card", () => {
    const a = cardReducer(flash, {}, { type: "flash_choose", value: "(2; 3)" });
    expect(a).toMatchObject({ chosen: "(2; 3)", correct: true });
    expect(cardReducer(flash, a, { type: "flash_choose", value: "[2; 3]" })).toBe(a);
    expect(cardReducer(flash, a, { type: "flash_skip" })).toBe(a);
  });

  it("replays recorded clicks from history (letter, free text, skip)", () => {
    expect(eventFromCardAction(flash, "answer", "B")).toEqual({ type: "flash_choose", value: "(−∞; 2) ∪ (3; +∞)" });
    expect(eventFromCardAction({ ...flash, choices: undefined }, "answer", "x = 2")).toEqual({ type: "flash_answer", text: "x = 2" });
    expect(eventFromCardAction(flash, "skip")).toEqual({ type: "flash_skip" });
  });
});

describe("focus", () => {
  it("extends from the current end and maps to card_action extend", () => {
    const ui = cardReducer(focus, {}, { type: "focus_extend", minutes: 10, now: START + 5 * 60_000 });
    expect(Date.parse(ui.endsAt!)).toBe(START + 35 * 60_000);
    expect(cardActionFor(focus, { type: "focus_extend", minutes: 10, now: 0 })).toEqual({ action: "extend", value: "10" });
  });

  it("computes progress from the total minutes and the current end", () => {
    const p = focusProgress(focus, {}, START + 5 * 60_000);
    expect(p.fraction).toBeCloseTo(0.2);
    expect(p.remainingMs).toBe(20 * 60_000);
    expect(p.finished).toBe(false);
    // the server's update after "extend 10": minutes is the new total, ends_at the new end
    const extended = { ...focus, minutes: 35, ends_at: "2026-11-03T20:35:00+07:00" };
    expect(focusProgress(extended, {}, START + 5 * 60_000).fraction).toBeCloseTo(5 / 35);
    expect(focusProgress({ ...focus, ended_at: "2026-11-03T20:10:00+07:00" }, {}, START + 30 * 60_000)).toMatchObject({
      ended: true,
      finished: true,
      fraction: 1,
      remainingMs: 0,
    });
    expect(formatClock(20 * 60_000 + 5_000)).toBe("20:05");
  });

  it("drops optimistic overrides when the updated card arrives", () => {
    expect(mergeCardUpdate({ ...focus, minutes: 35 }, { endsAt: "x" })).toEqual({});
    expect(mergeCardUpdate({ ...focus, ended_at: "2026-11-03T20:10:00+07:00" }, {})).toEqual({ focusDone: true });
  });
});

describe("deadline countdown", () => {
  const due: DeadlineCard = { id: "d", kind: "deadline", created_at: "", title: "Thi", due_at: "2026-11-06T07:30:00+07:00" };
  const at = (iso: string) => Date.parse(iso);

  it("reads calmly in days/hours/minutes, never seconds", () => {
    expect(formatCountdown(countdown(due.due_at, at("2026-11-03T05:30:00+07:00")))).toBe("còn 3 ngày 2 giờ");
    expect(formatCountdown(countdown(due.due_at, at("2026-11-06T04:00:00+07:00")))).toBe("còn 3 giờ 30 phút");
    expect(formatCountdown(countdown(due.due_at, at("2026-11-06T07:22:00+07:00")))).toBe("còn 8 phút");
    expect(formatCountdown(countdown(due.due_at, at("2026-11-06T07:29:30+07:00")))).toBe("còn chưa tới 1 phút");
    expect(formatCountdown(countdown(due.due_at, at("2026-11-06T08:00:00+07:00")))).toBe("đã tới hạn");
  });

  it("formats the due time in Vietnam time whatever the machine zone", () => {
    expect(formatDue("2026-11-06T00:30:00Z")).toBe("07:30, Thứ Sáu 06/11"); // 06/11/2026 is a Friday
  });

  it("uses calm tones and ticks slowly", () => {
    expect(deadlineTone(countdown(due.due_at, at("2026-11-01T07:30:00+07:00")))).toBe("far");
    expect(deadlineTone(countdown(due.due_at, at("2026-11-04T12:00:00+07:00")))).toBe("near");
    expect(deadlineTone(countdown(due.due_at, at("2026-11-05T12:00:00+07:00")))).toBe("soon");
    expect(countdownTickMs(countdown(due.due_at, at("2026-11-01T07:30:00+07:00")))).toBe(30_000);
    expect(countdownTickMs(countdown(due.due_at, at("2026-11-06T07:00:00+07:00")))).toBe(15_000);
    expect(countdownTickMs(countdown(due.due_at, at("2026-11-07T07:00:00+07:00")))).toBe(0);
  });
});
