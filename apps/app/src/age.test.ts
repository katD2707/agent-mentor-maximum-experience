import { describe, expect, it } from "vitest";
import { bandForBirthYear } from "./lib/age";

const d = (y: number, m: number, day: number) => new Date(y, m - 1, day);

describe("band from birth year (September school year)", () => {
  it("born 2010 is g10_12 in Nov 2026 and uni in 2030", () => {
    expect(bandForBirthYear(2010, d(2026, 11, 7))).toBe("g10_12");
    expect(bandForBirthYear(2010, d(2030, 11, 7))).toBe("uni");
  });
  it("moves up on 1 September, not before", () => {
    expect(bandForBirthYear(2010, d(2028, 8, 31))).toBe("g10_12"); // grade 12
    expect(bandForBirthYear(2010, d(2028, 9, 1))).toBe("uni"); // grade 13
    expect(bandForBirthYear(2015, d(2026, 8, 31))).toBe("g1_5"); // grade 5
    expect(bandForBirthYear(2015, d(2026, 9, 1))).toBe("g6_9"); // grade 6
    expect(bandForBirthYear(2012, d(2026, 9, 1))).toBe("g6_9"); // grade 9
    expect(bandForBirthYear(2012, d(2027, 9, 1))).toBe("g10_12"); // grade 10
  });
  it("before grade 1 counts as primary, no birth year no band", () => {
    expect(bandForBirthYear(2020, d(2024, 11, 7))).toBe("g1_5");
    expect(bandForBirthYear(1980, d(2026, 11, 7))).toBe("uni");
    expect(bandForBirthYear(null)).toBeNull();
  });
});
