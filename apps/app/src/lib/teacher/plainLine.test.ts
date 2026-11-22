import { describe, expect, it } from "vitest";
import { plainLine } from "./steps";

describe("plainLine", () => {
  it("drops list dashes, bold marks and LaTeX commands", () => {
    expect(plainLine("- **Quy tắc**: $a \\cdot b = c$")).toBe("Quy tắc: a · b = c");
    expect(plainLine("1. Tính $\\frac{1}{2} \\times 4$")).toBe("Tính 1/2 × 4");
    expect(plainLine("x \\\\cdot y")).toBe("x · y");
  });
});
