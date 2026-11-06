import { describe, expect, it } from "vitest";
import { invalidSettingsMessage, learnerToggles } from "./settings";
import type { Settings } from "./types";

const settings: Settings = {
  proactivity: "normal",
  quiet_hours: ["22:00", "07:00"],
  language: "vi",
  routines: [
    { id: "parent_report", enabled: true, cron: "0 18 */14 * *", job_kind: "parent_report", user_editable: false },
    { id: "evening_review", enabled: true, cron: "0 20 * * 1-5", job_kind: "routine", user_editable: true },
  ],
};

describe("invalidSettingsMessage (422 from PUT /settings)", () => {
  it("names the locked routine from a string detail", () => {
    expect(invalidSettingsMessage({ detail: "routine parent_report is not user_editable" }, settings)).toContain("Báo cáo phụ huynh");
  });
  it("understands FastAPI validation lists", () => {
    const body = { detail: [{ loc: ["body", "quiet_hours", 0], msg: "invalid", type: "value_error" }] };
    expect(invalidSettingsMessage(body, settings)).toContain("giờ yên lặng");
  });
  it("falls back to a generic Vietnamese message", () => {
    expect(invalidSettingsMessage(undefined, settings)).toMatch(/^Không lưu được cài đặt/);
  });
});

describe("learnerToggles", () => {
  it("shows only editable, mapped routines under plain names", () => {
    const t = learnerToggles([
      ...settings.routines,
      { id: "morning_checkin", enabled: false, cron: "30 7 * * 1-5", job_kind: "routine", user_editable: true },
    ]);
    expect(t.map((x) => [x.label, x.routine.id])).toEqual([
      ["Nhắc ôn buổi tối", "evening_review"],
      ["Check-in buổi sáng", "morning_checkin"],
    ]);
  });
});
