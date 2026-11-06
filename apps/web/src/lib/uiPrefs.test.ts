import { describe, expect, it } from "vitest";
import { applyTextScale, clampScale, readSounds, readTextScale, scaleToPercent, TEXT_SCALE_SCRIPT } from "./uiPrefs";

describe("text size", () => {
  it("clamps to 85..140 %", () => {
    expect(clampScale(0.5)).toBe(0.85);
    expect(clampScale(2)).toBe(1.4);
    expect(clampScale(1.15)).toBe(1.15);
    expect(clampScale(NaN)).toBe(1);
  });

  it("applies as a root font-size, clearing it at 100 %", () => {
    const root = { style: { fontSize: "" } };
    applyTextScale(root, 1.25);
    expect(root.style.fontSize).toBe("125%");
    applyTextScale(root, 1);
    expect(root.style.fontSize).toBe("");
    applyTextScale(root, 9);
    expect(root.style.fontSize).toBe("140%");
    expect(scaleToPercent(0.85)).toBe("85%");
  });

  it("reads the stored value defensively", () => {
    expect(readTextScale({ getItem: () => "1.3" })).toBe(1.3);
    expect(readTextScale({ getItem: () => "abc" })).toBe(1);
    expect(readTextScale({ getItem: () => "9" })).toBe(1.4);
    expect(readTextScale({ getItem: () => null })).toBe(1);
    expect(readTextScale({ getItem: () => { throw new Error("blocked"); } })).toBe(1);
    expect(readTextScale(null)).toBe(1);
  });

  it("head script applies the stored size before paint", () => {
    const root = { style: { fontSize: "" } };
    const store: Record<string, string> = { "mentor-text-scale": "1.2" };
    new Function("localStorage", "document", TEXT_SCALE_SCRIPT)({ getItem: (k: string) => store[k] ?? null }, { documentElement: root });
    expect(root.style.fontSize).toBe("120%");
  });
});

describe("sounds", () => {
  it("is off by default", () => {
    expect(readSounds({ getItem: () => null })).toBe(false);
    expect(readSounds({ getItem: () => "1" })).toBe(true);
    expect(readSounds(null)).toBe(false);
  });
});
