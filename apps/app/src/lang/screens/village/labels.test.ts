import { describe, expect, it } from "vitest";
import { marketTop, mostlyCovered, nudgeIntoView, spreadTags } from "./labels";
import { cropVars } from "../../chickenArt";

describe("village readability", () => {
  it("lifts overlapping name tags apart and leaves apart ones alone", () => {
    const a = { left: 0, right: 100, top: 100, bottom: 122 };
    const b = { left: 40, right: 140, top: 104, bottom: 126 };
    const c = { left: 400, right: 500, top: 100, bottom: 122 };
    const [da, db, dc] = spreadTags([a, b, c]);
    expect(db).toBe(0); // the lower one stays
    expect(da).toBeGreaterThan(18);
    expect(dc).toBe(0);
  });
  it("moves the market icon below a sign it would cover, and a cut sign into view", () => {
    const sign = { left: 1280, right: 1390, top: 100, bottom: 126 };
    expect(marketTop(74, 100, 1278, 1366, [sign], 768)).toBe(136);
    expect(marketTop(74, 100, 1000, 1100, [sign], 768)).toBe(74);
    expect(nudgeIntoView(sign, 1366)).toBe(38);
    expect(nudgeIntoView({ left: 100, right: 200, top: 0, bottom: 10 }, 1366)).toBe(0);
  });
  it("knows a bird under a canopy in front of it", () => {
    const spr = { left: 100, right: 160, top: 100, bottom: 180 };
    expect(mostlyCovered(spr, [{ box: { left: 50, right: 300, top: 0, bottom: 200 }, front: true }])).toBe(true);
    expect(mostlyCovered(spr, [{ box: { left: 50, right: 300, top: 0, bottom: 200 }, front: false }])).toBe(false);
  });
  it("crops every growth stage so the head stays inside the box", () => {
    for (const s of [1, 2, 3]) {
      const v = cropVars("toan", s);
      expect(parseFloat(v["--it"])).toBeLessThan(0);
      expect(parseFloat(v["--ih"])).toBeGreaterThan(100);
    }
  });
});
