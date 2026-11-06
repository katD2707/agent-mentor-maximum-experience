import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TourController, type TourApi, type TourDeps } from "./tourController";
import type { Settings, TourPatch, TourState } from "./types";

const settings = (): Settings => ({
  proactivity: "normal",
  quiet_hours: ["22:00", "07:00"],
  language: "vi",
  routines: [
    { id: "evening_review", enabled: true, cron: "30 19 * * *", job_kind: "routine", prompt: "p", user_editable: true },
    { id: "review_due", enabled: true, cron: "30 20 * * *", job_kind: "routine", prompt: "p", user_editable: true },
  ],
});

function setup(over: Partial<TourDeps> = {}, role: "thpt" | "ncs" = "thpt", surface: "app" | "popup" = "app") {
  const saved: TourPatch[] = [];
  let state: TourState = { tour_step: null, tour_completed_at: null, tour_skipped_at: null, tips_seen: [] };
  const put = vi.fn(async (s: Settings) => s);
  const api: TourApi = {
    updateTour: async (p) => {
      saved.push(p);
      if ("step" in p) state = { ...state, tour_step: p.step };
      if ("complete" in p) state = { ...state, tour_step: null, tour_completed_at: "t" };
      if ("skip" in p) state = { ...state, tour_step: null, tour_skipped_at: "t" };
      return state;
    },
    getSettings: async () => settings(),
    putSettings: put,
  };
  const confetti = vi.fn();
  const onState = vi.fn();
  const c = new TourController({
    api,
    role,
    surface,
    onState,
    reducedMotion: () => false,
    confetti,
    errorText: (e) => String(e),
    ackMs: 100,
    finishMs: 500,
    ...over,
  });
  return { c, saved, put, confetti, onState, state: () => state };
}

describe("TourController", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("walks welcome -> ask -> practice -> time and saves every step", async () => {
    const t = setup();
    t.c.start();
    expect(t.c.getSnapshot()).toMatchObject({ phase: "step", step: "welcome" });
    t.c.advance();
    t.c.advance();
    t.c.advance();
    expect(t.c.getSnapshot().step).toBe("time");
    await vi.advanceTimersByTimeAsync(0);
    expect(t.saved).toEqual([{ step: "welcome" }, { step: "ask" }, { step: "practice" }, { step: "time" }]);
    expect(t.onState).toHaveBeenLastCalledWith(expect.objectContaining({ tour_step: "time" }));
  });

  it("NCS skips the practice step; the pop-up starts at ask", () => {
    const n = setup({}, "ncs");
    n.c.start();
    n.c.advance();
    n.c.advance();
    expect(n.c.getSnapshot().step).toBe("time");
    const p = setup({}, "thpt", "popup");
    p.c.start();
    expect(p.c.getSnapshot().step).toBe("ask");
  });

  it("a sent message completes ask after a short thank-you; other signals do nothing there", async () => {
    const t = setup();
    t.c.resume("ask");
    t.c.signal("diagnostic-answered");
    expect(t.c.getSnapshot().step).toBe("ask");
    t.c.signal("message-sent");
    expect(t.c.getSnapshot()).toMatchObject({ step: "ask", ack: true });
    await vi.advanceTimersByTimeAsync(100);
    expect(t.c.getSnapshot()).toMatchObject({ step: "practice", ack: false });
    expect(t.saved).toContainEqual({ step: "practice" });
  });

  it("the first diagnostic answer or skip completes practice at once and the next step is saved for the way back", async () => {
    const a = setup();
    a.c.resume("practice");
    a.c.signal("diagnostic-answered");
    expect(a.c.getSnapshot().step).toBe("time");
    await vi.advanceTimersByTimeAsync(0);
    expect(a.state().tour_step).toBe("time");
    const b = setup();
    b.c.resume("practice");
    b.c.signal("diagnostic-skipped");
    expect(b.c.getSnapshot().step).toBe("time");
  });

  it("resume picks the saved step without writing; the pop-up maps practice to time", async () => {
    const t = setup();
    t.c.resume("practice");
    expect(t.c.getSnapshot().step).toBe("practice");
    const p = setup({}, "thpt", "popup");
    p.c.resume("practice");
    expect(p.c.getSnapshot().step).toBe("time");
    await vi.advanceTimersByTimeAsync(0);
    expect(t.saved).toEqual([]);
  });

  it("skip closes at once and records it", async () => {
    const t = setup();
    t.c.start();
    t.c.skip();
    expect(t.c.getSnapshot().phase).toBe("idle");
    await vi.advanceTimersByTimeAsync(0);
    expect(t.saved.at(-1)).toEqual({ skip: true });
    expect(t.state().tour_skipped_at).toBe("t");
  });

  it("choosing 20h writes the routines, celebrates with confetti, completes and closes itself", async () => {
    const t = setup();
    t.c.resume("time");
    const p = t.c.chooseHour(20);
    expect(t.c.getSnapshot().busy).toBe(true);
    await p;
    const written = t.put.mock.calls[0][0] as Settings;
    expect(written.routines.find((r) => r.id === "evening_review")?.cron).toBe("30 19 * * *");
    expect(written.routines.find((r) => r.id === "review_due")?.cron).toBe("0 20 * * *");
    expect(t.c.getSnapshot()).toMatchObject({ phase: "finish", hour: 20, celebrate: true, blockedBy: null });
    expect(t.confetti).toHaveBeenCalledTimes(1);
    expect(t.saved.at(-1)).toEqual({ complete: true });
    await vi.advanceTimersByTimeAsync(500);
    expect(t.c.getSnapshot().phase).toBe("idle");
  });

  it("'Không cần nhắc' switches the routines off", async () => {
    const t = setup();
    t.c.resume("time");
    await t.c.chooseHour(null);
    const written = t.put.mock.calls[0][0] as Settings;
    expect(written.routines.every((r) => !r.enabled)).toBe(true);
    expect(t.c.getSnapshot()).toMatchObject({ phase: "finish", hour: null });
  });

  it("reduced motion: no confetti and no celebrate animation, the finish card still shows", async () => {
    const t = setup({ reducedMotion: () => true });
    t.c.resume("time");
    await t.c.chooseHour(21);
    expect(t.confetti).not.toHaveBeenCalled();
    expect(t.c.getSnapshot()).toMatchObject({ phase: "finish", celebrate: false, hour: 21 });
  });

  it("a failed settings save keeps the step with an error and does not complete", async () => {
    const t = setup();
    t.put.mockRejectedValueOnce(new Error("boom"));
    t.c.resume("time");
    await t.c.chooseHour(20);
    expect(t.c.getSnapshot()).toMatchObject({ phase: "step", step: "time", busy: false });
    expect(t.c.getSnapshot().error).toContain("boom");
    expect(t.saved).not.toContainEqual({ complete: true });
    await t.c.chooseHour(20); // retry works
    expect(t.c.getSnapshot().phase).toBe("finish");
  });

  it("'Để sau' on the last step completes without touching settings", async () => {
    const t = setup();
    t.c.resume("time");
    t.c.advance();
    expect(t.c.getSnapshot().phase).toBe("idle");
    await vi.advanceTimersByTimeAsync(0);
    expect(t.put).not.toHaveBeenCalled();
    expect(t.saved.at(-1)).toEqual({ complete: true });
  });

  it("a failed progress save never blocks the tour", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const t = setup();
    (t.c as unknown as { deps: TourDeps }).deps.api.updateTour = async () => {
      throw new Error("offline");
    };
    t.c.start();
    t.c.advance();
    await vi.advanceTimersByTimeAsync(0);
    expect(t.c.getSnapshot().step).toBe("ask");
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("replay asks the server to restart first", async () => {
    const t = setup();
    t.c.restart();
    expect(t.c.getSnapshot().step).toBe("welcome");
    await vi.advanceTimersByTimeAsync(0);
    expect(t.saved[0]).toEqual({ restart: true });
  });
});
