import { describe, expect, it } from "vitest";
import type { Me, TourState } from "./types";
import { completes, nextStep, resolveStep, shouldAutoStart, shouldResume, stepCounter, tipFor, tourSteps, welcomeText } from "./tour";

const fresh: TourState = { tour_step: null, tour_completed_at: null, tour_skipped_at: null, tips_seen: [] };
const me = (over: Partial<Me> = {}, tour: Partial<TourState> = {}): Me => ({
  user_id: "u1",
  email: "a@b.c",
  role: "thpt",
  display_name: "An",
  language: "vi",
  onboarding_state: "active",
  inbound_email_address: null,
  setup_guide_dismissed_at: null,
  tour: { ...fresh, ...tour },
  ...over,
});

describe("tour steps", () => {
  it("gives THPT three steps, NCS two (no practice), the pop-up two", () => {
    expect(tourSteps("thpt", "app")).toEqual(["welcome", "ask", "practice", "time"]);
    expect(tourSteps("ncs", "app")).toEqual(["welcome", "ask", "time"]);
    expect(tourSteps("thpt", "popup")).toEqual(["ask", "time"]);
  });

  it("walks forward and ends with null (the finish moment)", () => {
    const l = tourSteps("thpt", "app");
    expect(nextStep(l, "welcome")).toBe("ask");
    expect(nextStep(l, "ask")).toBe("practice");
    expect(nextStep(l, "practice")).toBe("time");
    expect(nextStep(l, "time")).toBeNull();
  });

  it("resumes a step the surface does not have at the next one it has", () => {
    expect(resolveStep(tourSteps("thpt", "popup"), "practice")).toBe("time");
    expect(resolveStep(tourSteps("ncs", "app"), "practice")).toBe("time");
    expect(resolveStep(tourSteps("thpt", "popup"), "welcome")).toBe("ask");
    expect(resolveStep(tourSteps("thpt", "app"), null)).toBeNull();
  });

  it("counts steps without the welcome card", () => {
    expect(stepCounter(tourSteps("thpt", "app"), "welcome")).toBeNull();
    expect(stepCounter(tourSteps("thpt", "app"), "time")).toEqual({ index: 3, total: 3 });
    expect(stepCounter(tourSteps("ncs", "app"), "time")).toEqual({ index: 2, total: 2 });
  });

  it("words the welcome for the role", () => {
    expect(welcomeText("An", "thpt")).toBe("Chào An! Mình là Mầm. 3 bước, chưa tới 1 phút nhé.");
    expect(welcomeText("", "ncs")).toContain("2 bước");
  });
});

describe("auto start and resume", () => {
  it("starts once for a new active learner", () => {
    expect(shouldAutoStart(me())).toBe(true);
    expect(shouldAutoStart(me({}, { tour_completed_at: "2026-11-06T00:00:00Z" }))).toBe(false);
    expect(shouldAutoStart(me({}, { tour_skipped_at: "2026-11-06T00:00:00Z" }))).toBe(false);
    expect(shouldAutoStart(me({}, { tour_step: "ask" }))).toBe(false); // already started: resume instead
  });

  it("does not start while onboarding, without the field, or for learners who closed the old guide", () => {
    expect(shouldAutoStart(me({ onboarding_state: "needs_parent" }))).toBe(false);
    expect(shouldAutoStart(me({ tour: undefined }))).toBe(false);
    expect(shouldAutoStart(me({ setup_guide_dismissed_at: "2026-11-01T00:00:00Z" }))).toBe(false);
  });

  it("resumes a saved step on an unfinished tour only", () => {
    expect(shouldResume(me({}, { tour_step: "practice" }))).toBe(true);
    expect(shouldResume(me())).toBe(false);
    expect(shouldResume(me({}, { tour_step: "time", tour_skipped_at: "2026-11-06T00:00:00Z" }))).toBe(false);
  });
});

describe("step completion triggers", () => {
  it("ask completes on a sent message only; practice on a diagnostic answer or skip", () => {
    expect(completes("ask", "message-sent")).toBe(true);
    expect(completes("ask", "diagnostic-answered")).toBe(false);
    expect(completes("practice", "diagnostic-answered")).toBe(true);
    expect(completes("practice", "diagnostic-skipped")).toBe(true);
    expect(completes("practice", "message-sent")).toBe(false);
    expect(completes("time", "message-sent")).toBe(false);
    expect(completes("welcome", "message-sent")).toBe(false);
  });
});

describe("contextual tips", () => {
  it("shows the tip of a page once, for the right role, never over the tour", () => {
    const s = { ...fresh };
    expect(tipFor("/progress", "thpt", s, false)?.id).toBe("progress");
    expect(tipFor("/progress", "ncs", s, false)).toBeNull();
    expect(tipFor("/plans", "ncs", s, false)?.id).toBe("plans");
    expect(tipFor("/practice", "thpt", s, false)?.id).toBe("practice");
    expect(tipFor("/practice/session/x", "thpt", s, false)).toBeNull();
    expect(tipFor("/chat", "thpt", s, false)).toBeNull();
    expect(tipFor("/progress", "thpt", s, true)).toBeNull();
    expect(tipFor("/progress", "thpt", { ...s, tips_seen: ["progress"] }, false)).toBeNull();
  });
});
