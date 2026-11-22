import { describe, expect, it } from "vitest";
import { GUIDE_DEFS, GUIDE_TOURS, HELLO } from "./data";
import { guideScreen } from "./RouteGuide";
import { hasSeen, markSeen, resetSeen } from "../../lib/tours";

describe("chicken guide: tours", () => {
  it("every part a tour points at has a text on that screen", () => {
    for (const [screen, steps] of Object.entries(GUIDE_TOURS)) {
      for (const s of steps) {
        if (s === HELLO || typeof s !== "string") continue;
        expect(GUIDE_DEFS.some((d) => d.sel === s && (!d.page || d.page === screen)), `${screen}: ${s}`).toBe(true);
      }
      expect(steps.length, screen).toBeLessThanOrEqual(3);
    }
  });

  it("maps routes to guide screens for students and teachers", () => {
    expect(guideScreen("/chuong/toan", false)).toBe("chuong");
    expect(guideScreen("/dau-truong/p1", false)).toBe("arena");
    expect(guideScreen("/phong-tu-hoc", false)).toBe("study");
    expect(guideScreen("/tien-do", false)).toBe("progress");
    expect(guideScreen("/khoa-hoc/c1/hoc", false)).toBe("lesson");
    expect(guideScreen("/luyen-tap/s1", false)).toBe("run");
    expect(guideScreen("/luyen-tap/s1/ket-qua", false)).toBeNull();
    expect(guideScreen("/", false)).toBeNull(); // the village mounts its own guide
    expect(guideScreen("/", true)).toBe("gv-home");
    expect(guideScreen("/khoa/c1", true)).toBe("gv-course");
    expect(guideScreen("/khoa/c1/nhan", true)).toBe("gv-labels");
    expect(guideScreen("/khoa/c1/duyet", true)).toBe("gv-review");
  });

  it("remembers screens per account until reset", () => {
    markSeen("u1", "lg-chuong");
    expect(hasSeen("u1", "lg-chuong")).toBe(true);
    expect(hasSeen("u2", "lg-chuong")).toBe(false);
    markSeen("u1", "lg-chuong", false);
    expect(hasSeen("u1", "lg-chuong")).toBe(false);
    markSeen("u1", "lg-a");
    markSeen("u1", "lg-b");
    resetSeen("u1");
    expect(hasSeen("u1", "lg-b")).toBe(false);
  });
});
