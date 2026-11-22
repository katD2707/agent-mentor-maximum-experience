import { describe, expect, it, vi } from "vitest";
import { emitXp, onXp, takeLevelUps } from "./xp";
import { practice, setPracticeApi, type PracticeApi } from "../api/practice";

describe("XP event bus", () => {
  it("tells listeners what was paid, normalises level_up, and keeps level-ups for the village once", () => {
    takeLevelUps();
    const seen = vi.fn();
    const off = onXp(seen);
    emitXp([{ chicken: "toan", source: "practice_right", amount: 2 }], "practice:s1");
    emitXp([{ chicken: "van", source: "lesson_done", amount: 20, level_up: true }], "c1");
    emitXp([], "x");
    emitXp(undefined);
    off();
    emitXp([{ chicken: "anh", source: "focus", amount: 5, level_up: true }]);
    expect(seen).toHaveBeenCalledTimes(2);
    expect(seen.mock.calls[0]).toEqual([[{ chicken: "toan", source: "practice_right", amount: 2, level_up: false }], "practice:s1"]);
    expect(takeLevelUps().sort()).toEqual(["anh", "van"]);
    expect(takeLevelUps()).toEqual([]);
  });

  it("practice answer, fix and finish put what they paid on the bus", async () => {
    takeLevelUps();
    const seen = vi.fn();
    const off = onXp(seen);
    const xp = [{ chicken: "toan", source: "practice_right", amount: 2, level_up: true }];
    setPracticeApi({ answer: async () => ({ correct: true, xp }), fix: async () => ({ correct: true, xp }), finish: async () => ({ xp }), tick: async () => ({}) } as unknown as PracticeApi);
    await practice.answer("t", "s1", { position: 0, answer: "A", time_spent_sec: 1 });
    await practice.fix("t", "s1", { item_id: "i", answer: "A" });
    await practice.finish("t", "s1");
    await practice.tick("t", "s1", 0, 1);
    off();
    expect(seen).toHaveBeenCalledTimes(3);
    expect(takeLevelUps()).toEqual(["toan"]);
  });
});
