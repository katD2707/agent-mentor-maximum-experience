import { describe, expect, it } from "vitest";
import { ApiError } from "../client";
import { MockApiClient } from "./mockApi";

async function signedIn(persona: "thpt" | "ncs" = "thpt") {
  const api = new MockApiClient({ persona, now: () => Date.parse("2026-10-30T13:00:00Z"), origin: "http://localhost:3000" });
  const { dev_link } = await api.requestLink("hs@example.com");
  await api.verifyLink(new URL(dev_link!).searchParams.get("token")!);
  return api;
}

describe("mock onboarding tour endpoints", () => {
  it("starts empty and is part of /me", async () => {
    const api = await signedIn();
    const t = await api.getTour();
    expect(t).toEqual({ tour_step: null, tour_completed_at: null, tour_skipped_at: null, tips_seen: [] });
    expect((await api.getMe()).tour).toEqual(t);
  });

  it("saves the step, completes, replays and keeps tips", async () => {
    const api = await signedIn();
    expect((await api.updateTour({ step: "practice" })).tour_step).toBe("practice");
    const done = await api.updateTour({ complete: true });
    expect(done).toMatchObject({ tour_step: null, tour_completed_at: "2026-10-30T13:00:00.000Z" });
    await api.updateTour({ tip: "progress" });
    await api.updateTour({ tip: "progress" });
    expect((await api.getTour()).tips_seen).toEqual(["progress"]);
    const again = await api.updateTour({ restart: true });
    expect(again).toMatchObject({ tour_step: "welcome", tour_completed_at: null, tips_seen: ["progress"] });
  });

  it("skip is recorded and rejects bad input", async () => {
    const api = await signedIn("ncs");
    expect((await api.updateTour({ skip: true })).tour_skipped_at).not.toBeNull();
    await expect(api.updateTour({ tip: "Bad Tip" })).rejects.toBeInstanceOf(ApiError);
    await expect(api.updateTour({} as never)).rejects.toBeInstanceOf(ApiError);
  });

  it("accepts a new learner routine through PUT /settings (the study-time step adds review_due)", async () => {
    const api = await signedIn();
    const s = await api.getSettings();
    s.routines.push({ id: "review_due", enabled: true, cron: "0 20 * * *", job_kind: "routine", prompt: "x", user_editable: true });
    const out = await api.putSettings(s);
    expect(out.routines.find((r) => r.id === "review_due")).toMatchObject({ cron: "0 20 * * *", user_editable: true });
  });
});
