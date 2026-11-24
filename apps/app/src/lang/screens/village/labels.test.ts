import { describe, expect, it } from "vitest";
import { nudgeIntoView } from "./labels";
import { COS_BODY, COS_FIT, crowded } from "../../engine/village";
import { cropVars } from "../../chickenArt";

describe("village readability", () => {
  it("moves a cut sign into view and leaves a whole one alone", () => {
    const sign = { left: 1280, right: 1390, top: 100, bottom: 126 };
    expect(nudgeIntoView(sign, 1366)).toBe(38);
    expect(nudgeIntoView({ left: 100, right: 200, top: 0, bottom: 10 }, 1366)).toBe(0);
  });
  it("crops every growth stage so the head stays inside the box", () => {
    for (const s of [1, 2, 3]) {
      const v = cropVars("toan", s);
      expect(parseFloat(v["--it"])).toBeLessThan(0);
      expect(parseFloat(v["--ih"])).toBeGreaterThan(100);
    }
  });
  it("keeps chickens an oval of room apart and sizes a chick bigger than the old speck, below the grown one", () => {
    expect(crowded([0, 0], [1.5, 0.4], false)).toBe(true);
    expect(crowded([0, 0], [4.8, 0], false)).toBe(false);
    expect(crowded([0, 0], [0, 2], false)).toBe(true); // the name tag hangs under the bird
    expect(crowded([0, 0], [0, 3.2], false)).toBe(false);
    expect(crowded([0, 0], [2.6, 0], true)).toBe(false);
    // a costume: the bodies grow with the stage and the squeeze on the small ones stays mild
    const h = ([1, 2, 3, 4] as const).map((s) => (COS_BODY[s][3] - COS_BODY[s][1]) * COS_FIT[s]);
    expect(h[0]).toBeLessThan(h[1]);
    expect(h[1]).toBeLessThan(h[2]);
    expect(h[2]).toBeLessThanOrEqual(h[3] * 1.0001);
  });
});
