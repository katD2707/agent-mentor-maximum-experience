/**
 * Layout of the three bank diagram kinds as plain SVG primitives (port of agent-mentor `DiagramRenderer.kt`).
 * Colours are *roles* (`ink`, `grid`, `primary`, `accent`, `secondary`); the component maps them to CSS variables,
 * so a diagram follows the light/dark theme. Deterministic and DOM-free, so it is unit tested.
 */
import { parseExpr, type Expr } from "./expr";
import type { DiagramSpec, ForceDiagramSpec, FunctionPlotSpec, GeometrySpec } from "./types";

export type Role = "ink" | "grid" | "primary" | "accent" | "secondary" | "soft";

export type Prim =
  | { t: "line"; x1: number; y1: number; x2: number; y2: number; role: Role; w?: number; dash?: boolean; faint?: boolean }
  | { t: "path"; d: string; role: Role; w?: number; dash?: boolean; fill?: Role | "none"; fillOpacity?: number; clip?: boolean }
  | { t: "circle"; cx: number; cy: number; r: number; role: Role; fill?: boolean; fillOpacity?: number; dash?: boolean; w?: number }
  | { t: "rect"; x: number; y: number; w: number; h: number; role: Role; fillOpacity: number; rotate?: { deg: number; cx: number; cy: number } }
  | { t: "text"; x: number; y: number; s: string; role: Role; size?: number; bold?: boolean; italic?: boolean; anchor?: "start" | "middle" | "end" };

export interface DiagramModel {
  width: number;
  height: number;
  prims: Prim[];
  /** Clip rectangle for the curves of a plot. */
  clip?: { x: number; y: number; w: number; h: number };
}

export const DIAGRAM_WIDTH = 480;

const f2 = (n: number) => (Math.round(n * 100) / 100).toString();

/** Heights from agent-mentor `preferredAspect`. */
export function preferredAspect(spec: DiagramSpec): number {
  const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
  if (spec.kind === "function_plot") return clamp((spec.y_max - spec.y_min) / (spec.x_max - spec.x_min), 0.5, 0.9);
  if (spec.kind === "force_diagram") return 0.7;
  const { xs, ys } = geoExtent(spec);
  const w = Math.max(...xs) - Math.min(...xs);
  const h = Math.max(...ys) - Math.min(...ys);
  return w <= 0 ? 0.8 : clamp(h / w, 0.45, 1);
}

function geoExtent(spec: GeometrySpec): { xs: number[]; ys: number[] } {
  const byId = new Map(spec.points.map((p) => [p.id, p]));
  const xs = spec.points.map((p) => p.x);
  const ys = spec.points.map((p) => p.y);
  for (const c of spec.circles ?? []) {
    const p = byId.get(c.center);
    if (p) {
      xs.push(p.x - c.radius, p.x + c.radius);
      ys.push(p.y - c.radius, p.y + c.radius);
    }
  }
  if (xs.length === 0) return { xs: [0, 1], ys: [0, 1] };
  return { xs, ys };
}

export function niceStep(range: number): number {
  const raw = range / 8;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const nice = norm < 1.5 ? 1 : norm < 3.5 ? 2 : norm < 7.5 ? 5 : 10;
  return nice * mag;
}

/** Tick label: two decimals at most, decimal comma. */
export function fmtTick(v: number): string {
  const r = Math.round(v * 100) / 100;
  return Number.isInteger(r) ? String(r) : String(r).replace(".", ",");
}

export function buildDiagram(spec: DiagramSpec, width = DIAGRAM_WIDTH): DiagramModel {
  const height = Math.round(width * preferredAspect(spec));
  const m: DiagramModel = { width, height, prims: [] };
  if (spec.kind === "function_plot") plot(spec, m);
  else if (spec.kind === "force_diagram") forces(spec, m);
  else if (spec.kind === "geometry") geometry(spec, m);
  return m;
}

function arrow(m: DiagramModel, x1: number, y1: number, x2: number, y2: number, role: Role, w = 2, head = 9) {
  const ang = Math.atan2(y2 - y1, x2 - x1);
  const bx = x2 - head * 0.8 * Math.cos(ang);
  const by = y2 - head * 0.8 * Math.sin(ang);
  m.prims.push({ t: "line", x1, y1, x2: bx, y2: by, role, w });
  const d = `M${f2(x2)} ${f2(y2)}L${f2(x2 - head * Math.cos(ang - 0.4))} ${f2(y2 - head * Math.sin(ang - 0.4))}L${f2(x2 - head * Math.cos(ang + 0.4))} ${f2(y2 - head * Math.sin(ang + 0.4))}Z`;
  m.prims.push({ t: "path", d, role, fill: role, w: 0.5 });
}

// ---------------------------------------------------------------- function_plot

function plot(spec: FunctionPlotSpec, m: DiagramModel) {
  const { width: w, height: h } = m;
  const pad = 28;
  const left = pad;
  const right = w - pad * 0.6;
  const top = pad * 0.6;
  const bottom = h - pad;
  const xr = spec.x_max - spec.x_min || 1;
  const yr = spec.y_max - spec.y_min || 1;
  const sx = (x: number) => left + ((x - spec.x_min) / xr) * (right - left);
  const sy = (y: number) => bottom - ((y - spec.y_min) / yr) * (bottom - top);
  const xStep = niceStep(xr);
  const yStep = niceStep(yr);
  const P = m.prims;

  if (spec.show_grid !== false) {
    for (let x = Math.ceil(spec.x_min / xStep) * xStep; x <= spec.x_max + 1e-9; x += xStep) P.push({ t: "line", x1: sx(x), y1: top, x2: sx(x), y2: bottom, role: "grid", w: 1 });
    for (let y = Math.ceil(spec.y_min / yStep) * yStep; y <= spec.y_max + 1e-9; y += yStep) P.push({ t: "line", x1: left, y1: sy(y), x2: right, y2: sy(y), role: "grid", w: 1 });
  }
  const ax = sy(Math.min(spec.y_max, Math.max(spec.y_min, 0)));
  const ay = sx(Math.min(spec.x_max, Math.max(spec.x_min, 0)));
  arrow(m, left - 6, ax, right + 10, ax, "ink", 1.4, 8);
  arrow(m, ay, bottom + 6, ay, top - 10, "ink", 1.4, 8);
  P.push({ t: "text", x: right + 6, y: ax + 12, s: "x", role: "ink", italic: true });
  P.push({ t: "text", x: ay + 8, y: top - 2, s: "y", role: "ink", italic: true, anchor: "start" });
  if (spec.x_min <= 0 && spec.x_max >= 0 && spec.y_min <= 0 && spec.y_max >= 0) P.push({ t: "text", x: ay - 9, y: ax + 11, s: "O", role: "ink", size: 12, italic: true });
  for (let x = Math.ceil(spec.x_min / xStep) * xStep; x <= spec.x_max + 1e-9; x += xStep) {
    if (Math.abs(x) > 1e-9 && sx(x) < right - 10) {
      P.push({ t: "line", x1: sx(x), y1: ax - 3, x2: sx(x), y2: ax + 3, role: "ink", w: 1.2 });
      P.push({ t: "text", x: sx(x), y: ax + 12, s: fmtTick(x), role: "ink", size: 11 });
    }
  }
  for (let y = Math.ceil(spec.y_min / yStep) * yStep; y <= spec.y_max + 1e-9; y += yStep) {
    if (Math.abs(y) > 1e-9 && sy(y) > top + 10) {
      P.push({ t: "line", x1: ay - 3, y1: sy(y), x2: ay + 3, y2: sy(y), role: "ink", w: 1.2 });
      P.push({ t: "text", x: ay - 7, y: sy(y), s: fmtTick(y), role: "ink", size: 11, anchor: "end" });
    }
  }

  m.clip = { x: left, y: top, w: right - left, h: bottom - top };
  const roles: Role[] = ["primary", "accent", "secondary"];
  spec.functions.forEach((fn, i) => {
    let expr: Expr;
    try {
      expr = parseExpr(fn.expr);
    } catch {
      return; // a bad expression is skipped; the figure still has its alt text
    }
    const samples = 400;
    let d = "";
    let pen = false;
    let lastY = 0;
    for (let k = 0; k <= samples; k++) {
      const xv = spec.x_min + (xr * k) / samples;
      const yv = expr(xv);
      const usable = Number.isFinite(yv) && yv > spec.y_min - 4 * yr && yv < spec.y_max + 4 * yr;
      if (!usable || (pen && Math.abs(yv - lastY) > 2 * yr)) {
        pen = false;
        if (!usable) continue;
      }
      d += `${pen ? "L" : "M"}${f2(sx(xv))} ${f2(sy(yv))}`;
      pen = true;
      lastY = yv;
    }
    if (d) P.push({ t: "path", d, role: roles[i % 3], w: 2.6, fill: "none", clip: true });
    if (fn.label) {
      let lx: number | null = null;
      for (let k = 0; k <= 20; k++) {
        const c = spec.x_min + xr * (0.9 - 0.04 * k - 0.15 * i);
        const v = expr(c);
        if (Number.isFinite(v) && v >= spec.y_min && v <= spec.y_max) {
          lx = c;
          break;
        }
      }
      if (lx !== null) {
        const ly = expr(lx);
        const tw = fn.label.length * 7;
        const px = Math.min(sx(lx) + 8, right - tw - 4);
        P.push({ t: "text", x: px, y: Math.min(bottom - 10, Math.max(top + 10, sy(ly) - 12)), s: fn.label, role: roles[i % 3], size: 12, bold: true, anchor: "start" });
      }
    }
  });
  for (const pt of spec.points ?? []) {
    const px = sx(pt.x);
    const py = sy(pt.y);
    P.push({ t: "line", x1: px, y1: py, x2: px, y2: ax, role: "ink", w: 1, dash: true, faint: true });
    P.push({ t: "line", x1: px, y1: py, x2: ay, y2: py, role: "ink", w: 1, dash: true, faint: true });
    P.push({ t: "circle", cx: px, cy: py, r: 4, role: "accent", fill: true });
    if (pt.label) P.push({ t: "text", x: px + 8, y: py - 9, s: pt.label, role: "ink", size: 12, bold: true, anchor: "start" });
  }
}

// ---------------------------------------------------------------- force_diagram

function forces(spec: ForceDiagramSpec, m: DiagramModel) {
  const { width: w, height: h } = m;
  const P = m.prims;
  const incline = spec.incline_deg ?? null;
  const alpha = ((incline ?? 0) * Math.PI) / 180;
  const body = spec.body ?? "box";
  const bodySize = Math.min(w, h) * 0.16;
  let cx: number;
  let cy: number;
  if (incline && incline > 0) {
    const baseLeft = w * 0.08;
    const baseRight = w * 0.92;
    const baseY = h * 0.9;
    const rise = Math.min((baseRight - baseLeft) * Math.tan(alpha), h * 0.8);
    const run = rise / Math.tan(alpha);
    const x0 = baseRight - run;
    const tri = `M${f2(x0)} ${f2(baseY)}L${f2(baseRight)} ${f2(baseY)}L${f2(baseRight)} ${f2(baseY - rise)}Z`;
    P.push({ t: "path", d: tri, role: "ink", fill: "ink", fillOpacity: 0.11, w: 2 });
    const r = 34;
    const ex = x0 + r * Math.cos(alpha);
    const ey = baseY - r * Math.sin(alpha);
    P.push({ t: "path", d: `M${f2(x0 + r)} ${f2(baseY)}A${r} ${r} 0 0 0 ${f2(ex)} ${f2(ey)}`, role: "ink", fill: "none", w: 1.4 });
    P.push({ t: "text", x: x0 + r + 16, y: baseY - 10, s: `${fmtTick(incline)}°`, role: "ink", size: 12 });
    const t = 0.5;
    const sxp = x0 + run * t;
    const syp = baseY - rise * t;
    cx = sxp - (Math.sin(alpha) * bodySize) / 2;
    cy = syp - (Math.cos(alpha) * bodySize) / 2;
  } else {
    cx = w / 2;
    cy = h / 2;
    if (body === "box") {
      const gy = cy + bodySize / 2;
      P.push({ t: "line", x1: w * 0.12, y1: gy, x2: w * 0.88, y2: gy, role: "ink", w: 2 });
      for (let hx = w * 0.12; hx < w * 0.88; hx += 12) P.push({ t: "line", x1: hx, y1: gy + 8, x2: hx + 8, y2: gy, role: "ink", w: 1 });
    }
  }
  if (body === "box") {
    P.push({ t: "rect", x: cx - bodySize / 2, y: cy - bodySize / 2, w: bodySize, h: bodySize, role: "primary", fillOpacity: 0.25, rotate: { deg: -(alpha * 180) / Math.PI, cx, cy } });
  } else if (body === "ball") {
    P.push({ t: "circle", cx, cy, r: bodySize / 2, role: "primary", fill: true, fillOpacity: 0.25, w: 2.2 });
  } else {
    P.push({ t: "circle", cx, cy, r: 5, role: "primary", fill: true });
  }
  const unit = Math.min(w, h) * 0.34;
  for (const fc of spec.forces) {
    const a = (fc.angle_deg * Math.PI) / 180;
    const ex = cx + Math.cos(a) * unit * fc.magnitude;
    const ey = cy - Math.sin(a) * unit * fc.magnitude;
    arrow(m, cx, cy, ex, ey, "accent", 2.6, 11);
    const lx = ex + Math.cos(a) * 14;
    const ly = ey - Math.sin(a) * 14;
    P.push({ t: "text", x: lx, y: ly, s: fc.label, role: "ink", size: 14, bold: true, italic: true });
    const tw = fc.label.length * 8;
    const top = ly - 12;
    arrow(m, lx - tw / 2, top, lx + tw / 2 + 2, top, "ink", 1.1, 5);
  }
}

// ---------------------------------------------------------------- geometry

function geometry(spec: GeometrySpec, m: DiagramModel) {
  const { width: w, height: h } = m;
  const P = m.prims;
  if (spec.points.length === 0) return;
  const byId = new Map(spec.points.map((p) => [p.id, p]));
  const { xs, ys } = geoExtent(spec);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const pad = 30;
  const k = Math.min((w - 2 * pad) / Math.max(maxX - minX, 1e-6), (h - 2 * pad) / Math.max(maxY - minY, 1e-6));
  const ox = (w - (maxX - minX) * k) / 2;
  const oy = (h - (maxY - minY) * k) / 2;
  const tx = (x: number) => ox + (x - minX) * k;
  const ty = (y: number) => h - (oy + (y - minY) * k);
  const cxAll = spec.points.reduce((s, p) => s + tx(p.x), 0) / spec.points.length;
  const cyAll = spec.points.reduce((s, p) => s + ty(p.y), 0) / spec.points.length;

  for (const c of spec.circles ?? []) {
    const o = byId.get(c.center);
    if (o) P.push({ t: "circle", cx: tx(o.x), cy: ty(o.y), r: c.radius * k, role: "primary", w: 2, dash: c.dashed });
  }
  for (const seg of spec.segments ?? []) {
    const a = byId.get(seg.from);
    const b = byId.get(seg.to);
    if (!a || !b) continue;
    P.push({ t: "line", x1: tx(a.x), y1: ty(a.y), x2: tx(b.x), y2: ty(b.y), role: "ink", w: seg.dashed ? 1.6 : 2.2, dash: seg.dashed });
    if (seg.label) {
      const mx = (tx(a.x) + tx(b.x)) / 2;
      const my = (ty(a.y) + ty(b.y)) / 2;
      const dx = mx - cxAll;
      const dy = my - cyAll;
      const d = Math.max(Math.hypot(dx, dy), 1e-6);
      P.push({ t: "text", x: mx + (dx / d) * 12, y: my + (dy / d) * 12, s: seg.label, role: "accent", size: 12, bold: true });
    }
  }
  for (const ra of spec.right_angles ?? []) {
    const v = byId.get(ra.vertex);
    const a = byId.get(ra.from);
    const b = byId.get(ra.to);
    if (!v || !a || !b) continue;
    const size = 10;
    const unit = (p: { x: number; y: number }) => {
      const dx = tx(p.x) - tx(v.x);
      const dy = ty(p.y) - ty(v.y);
      const d = Math.max(Math.hypot(dx, dy), 1e-6);
      return [dx / d, dy / d] as const;
    };
    const [ux, uy] = unit(a);
    const [vx, vy] = unit(b);
    const X = tx(v.x);
    const Y = ty(v.y);
    P.push({ t: "path", d: `M${f2(X + ux * size)} ${f2(Y + uy * size)}L${f2(X + (ux + vx) * size)} ${f2(Y + (uy + vy) * size)}L${f2(X + vx * size)} ${f2(Y + vy * size)}`, role: "ink", fill: "none", w: 1.3 });
  }
  for (const pt of spec.points) {
    const label = pt.label ?? pt.id;
    const px = tx(pt.x);
    const py = ty(pt.y);
    P.push({ t: "circle", cx: px, cy: py, r: 2.6, role: "ink", fill: true });
    if (label) {
      const dx = px - cxAll;
      const dy = py - cyAll;
      const d = Math.hypot(dx, dy);
      const [ux, uy] = d < 1e-6 ? [0, -1] : [dx / d, dy / d];
      P.push({ t: "text", x: px + ux * 14, y: py + uy * 14, s: label, role: "ink", size: 14, bold: true, italic: true });
    }
  }
}
