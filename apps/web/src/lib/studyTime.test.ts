import { describe, expect, it } from "vitest";
import { applyStudyTime, currentStudyHour, hourLabel } from "./studyTime";
import type { Routine, Settings } from "./types";

const r = (id: string, cron: string, over: Partial<Routine> = {}): Routine => ({ id, enabled: true, cron, job_kind: "routine", prompt: "p", user_editable: true, ...over });
const base = (routines: Routine[], over: Partial<Settings> = {}): Settings => ({ proactivity: "normal", quiet_hours: ["22:00", "07:00"], language: "vi", routines, ...over });

describe("applyStudyTime (THPT)", () => {
  it("moves evening_review to H-0:30 and review_due to H:00, keeping the weekdays", () => {
    const s = base([r("evening_review", "0 20 * * 1-5"), r("review_due", "30 20 * * *"), r("weekly_review", "0 16 * * 0")]);
    const out = applyStudyTime(s, "thpt", 20);
    expect(out.settings.routines.find((x) => x.id === "evening_review")).toMatchObject({ cron: "30 19 * * 1-5", enabled: true });
    expect(out.settings.routines.find((x) => x.id === "review_due")).toMatchObject({ cron: "0 20 * * *", enabled: true });
    expect(out.settings.routines.find((x) => x.id === "weekly_review")?.cron).toBe("0 16 * * 0"); // untouched
    expect(out.blockedBy).toBeNull();
  });

  it("adds a missing review_due and enables a disabled routine", () => {
    const out = applyStudyTime(base([r("evening_review", "0 20 * * *", { enabled: false })]), "thpt", 19);
    expect(out.settings.routines.find((x) => x.id === "evening_review")).toMatchObject({ cron: "30 18 * * *", enabled: true });
    expect(out.settings.routines.find((x) => x.id === "review_due")).toMatchObject({ cron: "0 19 * * *", enabled: true, user_editable: true, job_kind: "routine" });
  });

  it("switches both off for 'Không cần nhắc' and leaves others alone", () => {
    const out = applyStudyTime(base([r("evening_review", "0 20 * * *"), r("review_due", "0 20 * * *"), r("morning_checkin", "30 7 * * 1-5")]), "thpt", null);
    expect(out.settings.routines.map((x) => [x.id, x.enabled])).toEqual([["evening_review", false], ["review_due", false], ["morning_checkin", true]]);
  });

  it("never edits a routine the learner may not edit, and does not mutate the input", () => {
    const s = base([r("evening_review", "0 20 * * *", { user_editable: false })]);
    const out = applyStudyTime(s, "thpt", 21);
    expect(out.settings.routines.find((x) => x.id === "evening_review")?.cron).toBe("0 20 * * *");
    expect(s.routines).toHaveLength(1);
  });

  it("says when quiet hours or proactivity off would swallow the reminder", () => {
    expect(applyStudyTime(base([], { quiet_hours: ["20:30", "07:00"] }), "thpt", 21).blockedBy).toBe("quiet_hours");
    expect(applyStudyTime(base([], { proactivity: "off" }), "thpt", 20).blockedBy).toBe("proactivity");
    expect(applyStudyTime(base([]), "thpt", 21).blockedBy).toBeNull();
  });
});

describe("applyStudyTime (NCS) and helpers", () => {
  it("sets evening_wrapup for NCS", () => {
    const out = applyStudyTime(base([r("evening_wrapup", "0 21 * * *")]), "ncs", 20);
    expect(out.settings.routines[0].cron).toBe("0 20 * * *");
  });
  it("reads the chosen hour back and formats it", () => {
    expect(currentStudyHour(base([r("review_due", "0 20 * * *")]), "thpt")).toBe(20);
    expect(currentStudyHour(base([r("review_due", "0 20 * * *", { enabled: false })]), "thpt")).toBeNull();
    expect(currentStudyHour(base([r("review_due", "30 20 * * *")]), "thpt")).toBeNull();
    expect(hourLabel(9)).toBe("09:00");
  });
});
