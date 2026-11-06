import { describe, expect, it } from "vitest";
import { isApiError } from "../client";
import type { PracticeApi } from "../../practice/types";
import { MockPractice } from "./mockPractice";

function make(startMs = Date.parse("2026-11-06T10:00:00Z")) {
  const clock = { now: startMs };
  const api: PracticeApi = new MockPractice({ now: () => clock.now });
  return { api, clock };
}

async function expectStatus(p: Promise<unknown>, status: number, code?: string) {
  try {
    await p;
  } catch (e) {
    expect(isApiError(e, status)).toBe(true);
    if (code) expect((e as { body?: { code?: string } }).body?.code).toBe(code);
    return;
  }
  throw new Error(`expected HTTP ${status}`);
}

function rightAnswer(type: string) {
  return type === "SINGLE_CHOICE" ? "A" : type === "TRUE_FALSE_GROUP" ? "TTTT" : "1";
}

describe("mock /practice", () => {
  it("lists subjects with topics and mock profiles", async () => {
    const { api } = make();
    const subjects = await api.subjects();
    const math = subjects.find((s) => s.id === "math")!;
    expect(math.topics.length).toBeGreaterThan(2);
    expect(math.mock_profiles.map((p) => p.id)).toContain("math.format-2025-mock");
    expect(math.mock_profiles.every((p) => p.disclaimer.length > 0)).toBe(true);
    expect(math.diagnostic).toBe("none");
  });

  it("previews and starts the same set; items never carry keys, hints or explanations", async () => {
    const { api } = make();
    const pv = await api.preview({ subject: "math", minutes: 10, goal: "balanced" });
    expect(pv.item_count).toBeGreaterThanOrEqual(3);
    const s = await api.start({ kind: "practice", subject: "math", minutes: 10, goal: "balanced", seed: pv.seed });
    expect(s.items).toHaveLength(pv.item_count);
    expect(JSON.stringify(s)).not.toMatch(/explanation|"hint"|correct_option|"truth"|answer_key/);
    expect(s.status).toBe("active");
  });

  it("practice: reveal before the answer is 409, one hint, the answer returns the key and survives a reload", async () => {
    const { api } = make();
    const s = await api.start({ kind: "practice", subject: "math", minutes: 10, goal: "balanced", seed: 1 });
    await expectStatus(api.reveal(s.id, 0), 409, "not_answered");
    expect((await api.hint(s.id, 0)).hint.length).toBeGreaterThan(0);
    const type = s.items[0].type;
    const wrong = type === "SINGLE_CHOICE" ? "D" : type === "TRUE_FALSE_GROUP" ? "FFFF" : "999";
    const r = await api.answer(s.id, { position: 0, answer: wrong, time_spent_sec: 5 });
    expect(typeof r.correct_answer).toBe("string");
    expect(r.saved).toBeUndefined();
    await expectStatus(api.hint(s.id, 0), 403, "hints_locked");
    expect((await api.reveal(s.id, 0)).explanation.length).toBeGreaterThan(0);
    // replaying a checked position returns the stored result
    expect(await api.answer(s.id, { position: 0, answer: rightAnswer(type), time_spent_sec: 9 })).toEqual(r);
    const again = await api.get(s.id);
    expect(again.answers["0"].result).toEqual(r);
    expect(again.answers["0"].hint).toBeTruthy();
    expect(again.position).toBe(1);
  });

  it("a blank answer is a skip: no verdict, no evidence", async () => {
    const { api } = make();
    const s = await api.start({ kind: "practice", subject: "math", minutes: 10, goal: "balanced", seed: 1 });
    const r = await api.answer(s.id, { position: 0, answer: "", time_spent_sec: 2 });
    expect(r.correct).toBeNull();
    const rep = await api.finish(s.id);
    expect(rep.answered).toBe(0);
    expect(rep.total).toBe(0);
  });

  it("scores a true/false group by the number of right statements (scoring-v2)", async () => {
    const { api } = make();
    const m = await api.start({ kind: "mock", subject: "math", profile_id: "math.format-2025-mock" });
    expect(m.parts).toHaveLength(3);
    const tfPos = m.parts![1].positions[0];
    await api.answer(m.id, { position: tfPos, answer: "TTTT", time_spent_sec: 3 });
    const rep = await api.finish(m.id);
    const review = await api.review(m.id);
    const items = Array.isArray(review) ? review : review.items;
    const right = [...items[tfPos].correct_answer].filter((c) => c === "T").length;
    expect(rep.per_part![1].points).toBeCloseTo([0, 0.1, 0.25, 0.5, 1][right], 5);
    expect(rep.per_part![1].part).toBe(2);
  });

  it("mock: saved but not graded until finish; the deadline is wall-clock and finishes it", async () => {
    const { api, clock } = make();
    const m = await api.start({ kind: "mock", subject: "math", profile_id: "math.mcq-mock.2026" });
    expect(m.deadline).toBe(new Date(clock.now + 12 * 60_000).toISOString());
    expect(await api.answer(m.id, { position: 0, answer: "A", time_spent_sec: 4 })).toEqual({ saved: true });
    await expectStatus(api.reveal(m.id, 0), 403, "reveal_locked");
    await expectStatus(api.hint(m.id, 0), 403, "hints_locked");
    const resumed = await api.get(m.id);
    expect(resumed.answers["0"].draft).toBe("A");
    expect(resumed.answers["0"].correct).toBeUndefined();
    await api.flag(m.id, 1, true);
    expect((await api.get(m.id)).answers["1"].flagged).toBe(true);
    // the tick reports the server's remaining time (item seconds are not the session clock)
    clock.now += 100_000;
    expect((await api.tick(m.id, 0, 12)).remaining_sec).toBe(620);
    clock.now += 700_000;
    expect(await api.tick(m.id, 0, 12)).toEqual({ remaining_sec: 0, expired: true });
    expect((await api.get(m.id)).status).toBe("finished");
    await expectStatus(api.answer(m.id, { position: 0, answer: "B", time_spent_sec: 1 }), 409);
    const rep = await api.finish(m.id); // idempotent
    expect(rep.score_10).not.toBeNull();
    expect(rep.total).toBe(8);
  });

  it("a running mock or diagnostic blocks a new session with active_session; resuming is offered", async () => {
    const { api } = make();
    const m = await api.start({ kind: "mock", subject: "math", profile_id: "math.mcq-mock.2026" });
    try {
      await api.start({ kind: "practice", subject: "math", minutes: 10, goal: "balanced", seed: 1 });
      throw new Error("should be blocked");
    } catch (e) {
      expect(isApiError(e, 409)).toBe(true);
      expect((e as { body: { code: string; session_id: string } }).body).toMatchObject({ code: "active_session", session_id: m.id });
    }
    expect((await api.active("math"))?.id).toBe(m.id);
    // another subject is free
    await api.start({ kind: "practice", subject: "physics", minutes: 10, goal: "balanced", seed: 1 });
  });

  it("finish reports topics with before/after mastery and the gateway's labels, and at most 3 next steps", async () => {
    const { api } = make();
    const s = await api.start({ kind: "practice", subject: "math", minutes: 10, goal: "balanced", seed: 2 });
    await api.answer(s.id, { position: 0, answer: rightAnswer(s.items[0].type), time_spent_sec: 3 });
    const rep = await api.finish(s.id);
    expect(rep.answered).toBe(1);
    expect(rep.total).toBe(1);
    expect(rep.per_topic.length).toBe(1);
    expect(rep.per_topic[0].mastery_before).toBeNull();
    expect(rep.per_topic[0].label).toMatch(/Chưa có dữ liệu|Cần thêm dữ liệu|Cần củng cố|Đang tiến bộ|Vững/);
    expect(rep.recommendations.length).toBeLessThanOrEqual(3);
    expect(rep.score_10).toBeNull();
    expect((await api.list({ subject: "math" }))[0].id).toBe(s.id);
  });

  it("item reports only after the answer is shown, capped at 10 a day", async () => {
    const { api } = make();
    const s = await api.start({ kind: "practice", subject: "math", minutes: 10, goal: "balanced", seed: 3 });
    const id = s.items[0].id;
    await expectStatus(api.reportItem(id, { session_id: s.id, reason: "typo" }), 409);
    await api.answer(s.id, { position: 0, answer: rightAnswer(s.items[0].type), time_spent_sec: 1 });
    expect((await api.reportItem(id, { session_id: s.id, reason: "wrong_key", note: "Kiểm tra lại" })).status).toBe("open");
    for (let i = 0; i < 9; i++) await api.reportItem(id, { session_id: s.id, reason: "other" });
    await expectStatus(api.reportItem(id, { session_id: s.id, reason: "other" }), 429);
    expect((await api.itemReports()).length).toBe(10);
  });

  it("starting a new practice session ends the old practice one", async () => {
    const { api } = make();
    const a = await api.start({ kind: "practice", subject: "math", minutes: 10, goal: "balanced", seed: 1 });
    expect((await api.active("math"))?.id).toBe(a.id);
    const b = await api.start({ kind: "practice", subject: "math", minutes: 10, goal: "weak", seed: 1 });
    expect((await api.active("math"))?.id).toBe(b.id);
    expect((await api.get(a.id)).status).toBe("finished");
    expect(await api.active("physics")).toBeNull();
  });

  it("diagnostic can be skipped; too few items is insufficient_content", async () => {
    const { api } = make();
    await api.skipDiagnostic("math");
    expect((await api.subjects()).find((s) => s.id === "math")!.diagnostic).toBe("skipped");
    await expectStatus(api.preview({ subject: "english", minutes: 10, goal: "balanced", topics: ["english.none"] }), 422, "insufficient_content");
  });
});

describe("mock /practice grade filter (CONTRACTS 10.11)", () => {
  it("flags above-grade topics and needs the opt-in to use them", async () => {
    const { api } = make();
    const math = (await api.subjects()).find((s) => s.id === "math")!;
    expect(math.learner_grade).toBe(11);
    const calc = math.topics.find((t) => t.id === "math.calculus")!;
    expect(calc).toMatchObject({ grade: 12, above_grade: true });
    const req = { subject: "math", minutes: 20, goal: "balanced" as const };
    await expectStatus(api.preview({ ...req, topics: ["math.calculus"] }), 422, "above_grade_topic");
    const p = await api.preview({ ...req, topics: ["math.calculus"], include_above_grade: true });
    expect(p.per_topic.every((t) => t.topic.endsWith("calculus"))).toBe(true);
    const plain = await api.preview(req);
    expect(plain.per_topic.some((t) => t.topic.endsWith("calculus"))).toBe(false);
  });
});
