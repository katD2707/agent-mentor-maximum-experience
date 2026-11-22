/** Pure parts of the village engine (ported from mockups/lang-engine.js): the map, the walk grid with road-preferring A*, headings. */

export type Pt = [number, number];

export interface Layout {
  size: [number, number];
  pxPerUnit: number;
  bounds: [number, number, number, number];
  affine: { ax: number; bx: number; ay: number; by: number };
  signs: Record<string, [number, number]>;
  doorsW: Record<string, Pt>;
  yard: Pt[];
  home: Pt;
  steam?: [number, number][];
  block: Pt[][];
  allow?: Pt[][];
  paths?: Pt[][];
  pathW?: number;
  occ?: { name: string; box: [number, number, number, number]; base: number }[];
  bg?: { file: string; box: [number, number, number, number] }[];
}

export interface AnimInfo {
  frames: number;
  fps: number;
  loop: boolean;
  dirs: string[];
  stride?: number;
}
export interface ActorsData {
  pxPerUnit: number;
  frame: [number, number];
  feet: [number, number];
  fps: number;
  dirs: string[];
  actors: Record<string, { anims: Record<string, AnimInfo> }>;
}

export const CELL = 0.5;
export const dist = (a: Pt, b: Pt): number => Math.hypot(a[0] - b[0], a[1] - b[1]);

export function inPoly(x: number, y: number, poly: Pt[]): boolean {
  let c = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
}

/** World <-> picture (0..1): the ground is flat and the camera orthographic, so the map is affine per axis. */
export function makeAffine(a: Layout["affine"]) {
  const { ax, bx, ay, by } = a;
  return {
    toS: (x: number, y: number): Pt => [ax * x + bx, ay * y + by],
    toW: (u: number, v: number): Pt => [(u - bx) / ax, (v - by) / ay],
  };
}
export type Affine = ReturnType<typeof makeAffine>;

// ---------- heading -> one of the 8 sprite directions, with hysteresis
export const DIRS = ["e", "ne", "n", "nw", "w", "sw", "s", "se"] as const;
export type Dir = (typeof DIRS)[number];
export const DIR_ANG: Record<Dir, number> = { e: 0, ne: 45, n: 90, nw: 135, w: 180, sw: -135, s: -90, se: -45 };
export const angDiff = (a: number, b: number): number => {
  let d = a - b;
  while (d > 180) d -= 360;
  while (d < -180) d += 360;
  return Math.abs(d);
};
/**
 * Heading (degrees in world space: 0 = east, 90 = away from the camera) to a sprite direction. The sprite only turns once
 * the heading is clearly nearer another direction (more than 31 degrees from the current one): no flicker on curves.
 */
export const dirFor = (deg: number, cur?: Dir | string | null): Dir => (cur && cur in DIR_ANG && angDiff(deg, DIR_ANG[cur as Dir]) < 31 ? (cur as Dir) : DIRS[((Math.round(deg / 45) % 8) + 8) % 8]);

// ---------- gait
/**
 * `stride` is the ground covered by one walk cycle, so feet keep pace with the ground. `ref` is the speed the cycle was drawn
 * for: going faster lengthens the stride a little as well as quickening the step.
 */
export const GAIT = { kid: { max: 4.2, acc: 12, stride: 1.45, ref: 2.5 }, ga: { max: 2.1, acc: 9, stride: 0.62, ref: 1.0 } } as const;
/** How much of the walk cycle (0..1 fraction) a step of `sp * dt` covers. */
export const phaseStep = (sp: number, dt: number, stride: number, ref: number): number => (sp * dt) / (stride * Math.max(1, Math.sqrt(sp / ref)));

// ---------- the walk grid
export class Grid {
  x0: number;
  y0: number;
  nx: number;
  ny: number;
  free: Uint8Array;
  road: Uint8Array;

  /** A grid over the village (0.5 world units), blocked by water, buildings, trunks, fences except where a bridge crosses. */
  constructor(L: Pick<Layout, "bounds" | "block" | "allow" | "paths" | "pathW" | "yard">) {
    const [x0, y0, x1, y1] = L.bounds;
    this.x0 = x0;
    this.y0 = y0;
    this.nx = Math.ceil((x1 - x0) / CELL);
    this.ny = Math.ceil((y1 - y0) / CELL);
    const { nx, ny } = this;
    this.free = new Uint8Array(nx * ny).fill(1);
    const boxes = (polys: Pt[][]) => polys.map((p) => ({ p, minx: Math.min(...p.map((q) => q[0])), maxx: Math.max(...p.map((q) => q[0])), miny: Math.min(...p.map((q) => q[1])), maxy: Math.max(...p.map((q) => q[1])) }));
    const B = boxes(L.block);
    const AL = boxes(L.allow ?? []);
    const hit = (bs: ReturnType<typeof boxes>, x: number, y: number) => bs.some((b) => x >= b.minx && x <= b.maxx && y >= b.miny && y <= b.maxy && inPoly(x, y, b.p));
    for (let j = 0; j < ny; j++)
      for (let i = 0; i < nx; i++) {
        const x = x0 + (i + 0.5) * CELL;
        const y = y0 + (j + 0.5) * CELL;
        if (hit(B, x, y) && !hit(AL, x, y)) this.free[j * nx + i] = 0;
      }
    // the dirt paths (and the yard): walking there is cheap, so people keep to them as they would
    this.road = new Uint8Array(nx * ny);
    const r = (L.pathW ?? 2) / 2;
    const mark = (x: number, y: number) => {
      const i = Math.floor((x - x0) / CELL);
      const j = Math.floor((y - y0) / CELL);
      if (i >= 0 && j >= 0 && i < nx && j < ny) this.road[j * nx + i] = 1;
    };
    for (const pl of L.paths ?? [])
      for (let k = 0; k + 1 < pl.length; k++) {
        const [ax, ay] = pl[k];
        const [bx, by] = pl[k + 1];
        const n = Math.ceil(Math.hypot(bx - ax, by - ay) / (CELL * 0.5));
        for (let t = 0; t <= n; t++) {
          const cx = ax + ((bx - ax) * t) / n;
          const cy = ay + ((by - ay) * t) / n;
          for (let dy = -r; dy <= r; dy += CELL * 0.5) for (let dx = -r; dx <= r; dx += CELL * 0.5) if (dx * dx + dy * dy <= r * r) mark(cx + dx, cy + dy);
        }
      }
    if (L.yard.length) for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) if (inPoly(x0 + (i + 0.5) * CELL, y0 + (j + 0.5) * CELL, L.yard)) this.road[j * nx + i] = 1;
  }

  cellOf = (p: Pt): [number, number] => [Math.floor((p[0] - this.x0) / CELL), Math.floor((p[1] - this.y0) / CELL)];
  ok = (i: number, j: number): boolean => i >= 0 && j >= 0 && i < this.nx && j < this.ny && this.free[j * this.nx + i] === 1;
  centre = (i: number, j: number): Pt => [this.x0 + (i + 0.5) * CELL, this.y0 + (j + 0.5) * CELL];
  walkable = (p: Pt): boolean => {
    const [i, j] = this.cellOf(p);
    return this.ok(i, j);
  };
  onRoad = (p: Pt): boolean => {
    const [i, j] = this.cellOf(p);
    return this.ok(i, j) && this.road[j * this.nx + i] === 1;
  };

  nearestFree(p: Pt): [number, number] | null {
    const [ci, cj] = this.cellOf(p);
    for (let r = 0; r < 12; r++)
      for (let dj = -r; dj <= r; dj++)
        for (let di = -r; di <= r; di++) {
          if (Math.max(Math.abs(di), Math.abs(dj)) !== r) continue;
          if (this.ok(ci + di, cj + dj)) return [ci + di, cj + dj];
        }
    return null;
  }

  /** Every cell on the line free, and on the road if the line starts and ends on it. */
  lineFree(a: Pt, b: Pt): boolean {
    const n = Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / (CELL * 0.5));
    const keepRoad = this.onRoad(a) && this.onRoad(b);
    for (let k = 0; k <= n; k++) {
      const t = k / Math.max(n, 1);
      const [i, j] = this.cellOf([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
      if (!this.ok(i, j) || (keepRoad && !this.road[j * this.nx + i])) return false;
    }
    return true;
  }

  /** A* over the grid (grass costs 2.6x the road, no squeezing through diagonal gaps), then straightened. */
  route(from: Pt, to: Pt): Pt[] {
    const s = this.nearestFree(from);
    const g = this.nearestFree(to);
    if (!s || !g) return [to];
    const { nx } = this;
    const N = nx * this.ny;
    const key = (i: number, j: number) => j * nx + i;
    const gs = new Float32Array(N).fill(1e9);
    const came = new Int32Array(N).fill(-1);
    const closed = new Uint8Array(N);
    const open: [number, number, number][] = [[0, s[0], s[1]]];
    gs[key(s[0], s[1])] = 0;
    const gk = key(g[0], g[1]);
    const sk = key(s[0], s[1]);
    const h = (i: number, j: number) => Math.hypot(i - g[0], j - g[1]);
    while (open.length) {
      let bi = 0;
      for (let k = 1; k < open.length; k++) if (open[k][0] < open[bi][0]) bi = k;
      const [, i, j] = open.splice(bi, 1)[0];
      const k0 = key(i, j);
      if (closed[k0]) continue;
      closed[k0] = 1;
      if (k0 === gk) break;
      for (let dj = -1; dj <= 1; dj++)
        for (let di = -1; di <= 1; di++) {
          if (!di && !dj) continue;
          const ni = i + di;
          const nj = j + dj;
          if (!this.ok(ni, nj)) continue;
          if (di && dj && (!this.ok(i + di, j) || !this.ok(i, j + dj))) continue;
          const k1 = key(ni, nj);
          const ng = gs[k0] + (di && dj ? 1.414 : 1) * (this.road[k1] ? 1 : 2.6);
          if (ng < gs[k1]) {
            gs[k1] = ng;
            came[k1] = k0;
            open.push([ng + h(ni, nj), ni, nj]);
          }
        }
    }
    if (came[gk] < 0 && gk !== sk) return [to];
    const cells: Pt[] = [];
    for (let k = gk; k >= 0; k = came[k]) {
      cells.unshift(this.centre(k % nx, Math.floor(k / nx)));
      if (k === sk) break;
    }
    // straighten: keep a point only when the straight line from the last kept one is blocked
    const pts: Pt[] = [[from[0], from[1]]];
    let last: Pt = [from[0], from[1]];
    for (let k = 1; k < cells.length; k++)
      if (!this.lineFree(last, cells[k])) {
        last = cells[k - 1];
        pts.push(last);
      }
    pts.push(this.walkable(to) ? to : cells[cells.length - 1]);
    return pts;
  }
}

/** A route becomes a smooth curve (Catmull-Rom), resampled every `step` world units. */
export function smooth(pts: Pt[], step = 0.35): Pt[] {
  if (pts.length < 3) return pts.slice(1);
  const P = [pts[0], ...pts, pts[pts.length - 1]];
  const out: Pt[] = [];
  for (let i = 1; i < P.length - 2; i++) {
    const p0 = P[i - 1];
    const p1 = P[i];
    const p2 = P[i + 1];
    const p3 = P[i + 2];
    const n = Math.max(2, Math.ceil(dist(p1, p2) / step));
    for (let k = 1; k <= n; k++) {
      const t = k / n;
      const t2 = t * t;
      const t3 = t2 * t;
      const f = (j: 0 | 1) => 0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2 + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3);
      out.push([f(0), f(1)]);
    }
  }
  return out;
}
