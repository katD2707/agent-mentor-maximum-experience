import { describe, expect, it } from "vitest";
import { buildDiagram, niceStep, preferredAspect } from "./diagram";
import { ExprError, parseExpr } from "./expr";

describe("expression parser", () => {
  it("evaluates the bank grammar", () => {
    expect(parseExpr("x^2 - 2*x")(3)).toBe(3);
    expect(parseExpr("-x^2")(3)).toBe(-9);
    expect(parseExpr("2^3^2")(0)).toBe(512);
    expect(parseExpr("sqrt(abs(x))")(-16)).toBe(4);
    expect(parseExpr("log(100) + ln(e)")(0)).toBeCloseTo(3);
    expect(parseExpr("sin(pi/2)")(0)).toBeCloseTo(1);
  });
  it("rejects implicit multiplication, unknown names and junk (no eval)", () => {
    expect(() => parseExpr("3x")).toThrow(ExprError);
    expect(() => parseExpr("foo(x)")).toThrow(ExprError);
    expect(() => parseExpr("x +")).toThrow(ExprError);
    expect(() => parseExpr("alert(1)")).toThrow(ExprError);
    expect(() => parseExpr("x; y")).toThrow(ExprError);
  });
});

describe("diagram layout", () => {
  it("plots a parabola with axes, ticks, a curve and the labelled point", () => {
    const m = buildDiagram({ kind: "function_plot", x_min: -2, x_max: 4, y_min: -2, y_max: 5, functions: [{ expr: "x^2 - 2*x", label: "y = f(x)" }], points: [{ x: 1, y: -1, label: "I" }] });
    expect(m.width).toBe(480);
    expect(m.clip).toBeDefined();
    const curve = m.prims.find((p) => p.t === "path" && p.clip);
    expect(curve && curve.t === "path" && curve.d.startsWith("M")).toBe(true);
    const texts = m.prims.filter((p) => p.t === "text").map((p) => (p.t === "text" ? p.s : ""));
    expect(texts).toEqual(expect.arrayContaining(["x", "y", "O", "y = f(x)", "I"]));
  });
  it("skips a bad expression instead of failing", () => {
    const m = buildDiagram({ kind: "function_plot", x_min: 0, x_max: 1, y_min: 0, y_max: 1, functions: [{ expr: "3x" }] });
    expect(m.prims.some((p) => p.t === "path" && p.clip)).toBe(false);
  });
  it("breaks the curve at an asymptote", () => {
    const m = buildDiagram({ kind: "function_plot", x_min: -2, x_max: 2, y_min: -3, y_max: 3, functions: [{ expr: "1/x" }] });
    const curve = m.prims.find((p) => p.t === "path" && p.clip);
    expect(curve && curve.t === "path" && (curve.d.match(/M/g) ?? []).length).toBeGreaterThan(1);
  });
  it("draws forces on an incline and a geometry figure with a right angle", () => {
    const f = buildDiagram({ kind: "force_diagram", body: "box", incline_deg: 30, forces: [{ label: "P", angle_deg: 270, magnitude: 1 }] });
    expect(f.prims.some((p) => p.t === "rect")).toBe(true);
    expect(f.prims.some((p) => p.t === "text" && p.s === "30°")).toBe(true);
    const g = buildDiagram({
      kind: "geometry",
      points: [
        { id: "A", x: 0, y: 0 },
        { id: "B", x: 4, y: 0 },
        { id: "C", x: 0, y: 3 },
      ],
      segments: [{ from: "B", to: "C", dashed: true, label: "5" }],
      right_angles: [{ vertex: "A", from: "B", to: "C" }],
    });
    expect(g.prims.filter((p) => p.t === "circle")).toHaveLength(3);
    expect(g.prims.some((p) => p.t === "line" && p.dash)).toBe(true);
  });
  it("aspect and tick step follow agent-mentor", () => {
    expect(preferredAspect({ kind: "force_diagram", forces: [] })).toBe(0.7);
    expect(preferredAspect({ kind: "function_plot", x_min: 0, x_max: 10, y_min: 0, y_max: 1, functions: [] })).toBe(0.5);
    expect(niceStep(6)).toBe(1);
    expect(niceStep(20)).toBe(2);
  });
});
