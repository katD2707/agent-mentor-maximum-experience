import { startAmbient, type Puff } from "./ambient";
import { Grid, GAIT, dirFor, dist, makeAffine, phaseStep, smooth, type ActorsData, type Affine, type Dir, type Layout, type Pt } from "./geometry";

/**
 * The village scene (ported from mockups/lang-engine.js): the painted picture in tiles, cut-outs that stand over the
 * characters behind them, the student and the chickens walking around (8-direction sprite sheets where they exist, the
 * still picture with a gentle bob where they do not), ambient life, and the camera.
 */
export interface EngineOptions {
  world: HTMLElement;
  scene: HTMLElement;
  bgHost: HTMLElement;
  occHost: HTMLElement;
  fx: HTMLCanvasElement | null;
  steam: HTMLElement | null;
  layout: Layout;
  /** sprite sheets of the actors that have them (toan, van, anh, nam, nu); null: every actor shows its still picture */
  sheets: ActorsData | null;
  /** folder of the village files, with a trailing slash */
  base: string;
  reduced?: boolean;
}

export interface ActorSpec {
  /** engine key ("kid", or the chicken id) */
  key: string;
  /** sprite id: nam / nu, or the chicken id */
  id: string;
  kind: "kid" | "ga";
  pos?: Pt;
  /** stands still (e.g. while it has something to say) */
  stay?: boolean;
  /** height of the drawing, world units (default: from the growth stage) */
  head?: number;
  /** still picture for an actor without sprite sheets */
  still?: string;
  /** the name tag: it hangs under the actor's feet and follows it, drawn over the scenery (never behind a tree) */
  tag?: HTMLElement | null;
  /** growth stage of a chicken (1 chick .. 4 master): the still is drawn at a size that fits the stage; before stage 3 it is always a still */
  stage?: number;
}

/**
 * How big a chicken's still looks, by growth stage. The pictures are 512 squares with the bird at the bottom and the chick fills only
 * ~28% of it, so a chick drawn as is would be a speck beside the student: it is scaled so the bird stands this much of the frame high
 * (grown = 52%), and its feet stay on the same spot. `K` is that scale, `FRAC` the bird's share of the frame afterwards.
 */
export const STILL_FRAC = [0.44, 0.5, 0.54, 0.58] as const;
export const STILL_K = [1.55, 1.14, 1.04, 1.12] as const;
/** world units a bird of `frac` of the frame stands high: frame (416 px) / pxPerUnit (94.1) = 4.42 u, and `--head` is 0.899 of the height */
export const stillHead = (stage: number): number => (STILL_FRAC[Math.min(Math.max(stage, 1), 4) - 1] * 4.42) / 0.899;
const FEET_Y_ART = 84.4; // % of the 512 picture where the bird's feet are
const FEET_X_ART = 51;

/** Are two standing actors too close? Chickens keep an oval of room (wide and deep enough for the name tag that hangs under them), the student a round one. */
export const crowded = (a: Pt, b: Pt, withKid: boolean): boolean => {
  const rx = withKid ? 2.4 : 4.6;
  const ry = withKid ? 2.4 : 2.8;
  return Math.hypot((a[0] - b[0]) / rx, (a[1] - b[1]) / ry) < 1;
};

/** a box in world px: left, top, right, bottom */
type Box = [number, number, number, number];
/** px of air kept round a name plate */
const GAP = 6;
const boxHit = (a: Box, b: Box, m = 0): boolean => a[0] < b[2] + m && b[0] < a[2] + m && a[1] < b[3] + m && b[1] < a[3] + m;

type Anim ="idle" | "walk" | "peck" | "jump" | "wave";

export class Actor {
  el: HTMLElement;
  spr: HTMLElement;
  id: string;
  key: string;
  kind: "kid" | "ga";
  pos: Pt;
  vel: Pt = [0, 0];
  dir: Dir = "s";
  anim: Anim = "idle";
  t0 = performance.now();
  path: Pt[] = [];
  phase = 0;
  base: number;
  max: number;
  acc: number;
  stride: number;
  ref: number;
  stay: boolean;
  head: number;
  stage = 3;
  tag: HTMLElement | null;
  /** name plate, CSS px (full, and shrunk to the level badge); measured by the engine, a guess until then */
  plateW = 120;
  plateH = 38;
  miniW = 30;
  miniH = 24;
  mini = false;
  gone = false;
  miniAt = 0;
  /** the body, as offsets (world px) from the feet point: left, top, right, bottom; measured by the engine */
  body: Box = [-24, -60, 24, 0];
  /** shift (px) that keeps the plate inside the view; 0 most of the time */
  dx = 0;
  /** lower number = its plate wins a clash (the student first, then the chickens in the order they came) */
  prio = 0;
  wait = 1 + Math.random() * 3;
  busy = false;
  cur: string | null = null;
  still = 0;
  stillUrl?: string;
  flip = false;
  onEnd: (() => void) | null = null;
  arrive: (() => void) | null = null;

  constructor(
    private V: VillageEngine,
    el: HTMLElement,
    spec: ActorSpec,
  ) {
    this.el = el;
    this.id = spec.id;
    this.key = spec.key;
    this.kind = spec.kind;
    this.spr = el.querySelector<HTMLElement>(".lg-spr")!;
    this.pos = (spec.pos ?? V.randomHomePoint()).slice() as Pt;
    const g = GAIT[spec.kind];
    this.base = g.max;
    this.max = g.max;
    this.acc = g.acc;
    this.stride = g.stride;
    this.ref = g.ref;
    this.stay = !!spec.stay;
    this.tag = spec.tag ?? null;
    this.stage = spec.stage ?? 3;
    this.head = spec.head ?? (spec.kind === "kid" ? 3.6 : stillHead(this.stage));
    this.stillUrl = spec.still;
    const w = V.sheets?.actors[spec.id]?.anims.walk;
    if (w?.stride) this.stride = w.stride;
    el.style.setProperty("--head", V.px(this.head * 0.899) + "px");
    this.place();
  }
  get hasSheets(): boolean {
    // a chick or a young chicken is drawn as its own picture; only the grown ones have walking sheets
    return !!this.V.sheets?.actors[this.id] && (this.kind === "kid" || this.stage >= 3);
  }
  /** A new picture or growth stage (the chicken grew up). */
  look(still: string | undefined, stage: number, head?: number) {
    this.stillUrl = still;
    this.stage = stage;
    this.head = head ?? stillHead(stage);
    this.cur = null;
    this.el.style.setProperty("--head", this.V.px(this.head * 0.899) + "px");
  }
  set(anim: Anim, dir?: Dir) {
    if (anim !== this.anim) {
      this.t0 = performance.now();
      this.anim = anim;
    }
    if (dir) this.dir = dir;
  }
  place() {
    const [u, v] = this.V.aff.toS(this.pos[0], this.pos[1]);
    this.el.style.left = u * 100 + "%";
    this.el.style.top = v * 100 + "%";
    this.el.style.zIndex = String(Math.round(v * 10000));
    if (this.tag) {
      this.tag.style.left = u * 100 + "%";
      this.tag.style.top = v * 100 + "%";
      this.tag.style.zIndex = this.el.style.zIndex;
    }
  }
  draw(now: number) {
    const A = this.V.sheets;
    if (!this.hasSheets || !A) {
      // no walking sprites: the still picture, bobbing a little (a small hop while it walks)
      if (this.stillUrl && this.cur !== this.stillUrl) {
        this.cur = this.stillUrl;
        this.spr.style.backgroundImage = `url("${this.stillUrl}")`;
        this.spr.style.backgroundSize = "100% 100%";
        this.spr.style.transformOrigin = `${FEET_X_ART}% ${FEET_Y_ART}%`;
      }
      const walking = this.anim === "walk" && !this.V.reduced;
      const bob = this.V.reduced ? 0 : walking ? -Math.abs(Math.sin(this.phase * Math.PI * 2)) * 7 : Math.sin(now / 520 + this.pos[0]) * 1.6;
      // the bird's feet on the actor's feet (the art stands a little higher in its picture), grown to its stage
      const sheetFeet = this.V.sheets ? (this.V.sheets.feet[1] / this.V.sheets.frame[1]) * 100 : 91;
      const k = this.kind === "ga" ? STILL_K[Math.min(Math.max(this.stage, 1), 4) - 1] : 1;
      this.spr.style.transform = `translateY(${bob.toFixed(1)}px) translateY(${(sheetFeet - FEET_Y_ART).toFixed(1)}%) scale(${k}) scaleX(${this.flip ? -1 : 1})`;
      return;
    }
    let s = this.V.sheet(this.id, this.anim, this.dir);
    if (!s || !s.ready) {
      s = this.V.sheet(this.id, "idle", this.dir);
      if (!s || !s.ready) s = this.V.sheet(this.id, "idle", "s");
      if (!s || !s.ready) return;
    }
    let f: number;
    if (this.anim === "walk" && s.loop) f = Math.floor((((this.phase % 1) + 1) % 1) * s.frames) % s.frames;
    else {
      f = Math.floor(((now - this.t0) / 1000) * s.fps);
      if (s.loop) f %= s.frames;
      else if (f >= s.frames) {
        f = s.frames - 1;
        if (this.onEnd) {
          const cb = this.onEnd;
          this.onEnd = null;
          cb();
        }
      }
    }
    if (this.V.reduced) f = 0;
    if (this.cur !== s.url) {
      this.spr.style.transform = "";
      this.spr.style.transformOrigin = "";
      this.spr.style.backgroundImage = `url("${s.url}")`;
      this.spr.style.backgroundSize = `${s.frames * 100}% 100%`;
      this.cur = s.url;
    }
    this.spr.style.backgroundPositionX = s.frames > 1 ? (f / (s.frames - 1)) * 100 + "%" : "0%";
  }
  walkPath(path: Pt[], speed?: number): Promise<void> {
    this.path = path.slice();
    this.busy = true;
    this.max = speed || this.base;
    this.onEnd = null;
    return new Promise((res) => (this.arrive = res));
  }
  /** Where the actor wants to go this instant, plus a soft push away from the others (nobody stands inside somebody else). */
  steer(dt: number): number {
    let want: Pt = [0, 0];
    if (this.path.length) {
      while (this.path.length > 1 && dist(this.pos, this.path[0]) < 0.5) this.path.shift();
      const t = this.path[0];
      const d = dist(this.pos, t);
      const lastPt = this.path.length === 1;
      if (lastPt && d < 0.07) {
        this.path = [];
        this.max = this.base;
        this.busy = false;
        const cb = this.arrive;
        this.arrive = null;
        cb?.();
      } else {
        const sp = lastPt ? Math.min(this.max, Math.max(0.3, d * 2.4)) : this.max;
        want = [((t[0] - this.pos[0]) / d) * sp, ((t[1] - this.pos[1]) / d) * sp];
      }
    }
    if (!this.stay)
      for (const o of Object.values(this.V.actors)) {
        if (o === this) continue;
        const d = dist(this.pos, o.pos);
        const withKid = this.kind === "kid" || o.kind === "kid";
        // an oval of room: chickens stand wider apart than deep (their name tags hang under them)
        // ... and wide and deep enough that the two name plates do not touch
        const [sx, sy] = this.V.unitPx();
        const rx = Math.max(withKid ? 2.4 : 4.6, (((this.plateW + o.plateW) / 2 + GAP) * 1.15) / sx);
        const ry = Math.max(withKid ? 2.4 : 2.8, (Math.max(this.plateH, o.plateH) + GAP) * 1.15 / sy);
        const e = Math.hypot((this.pos[0] - o.pos[0]) / rx, (this.pos[1] - o.pos[1]) / ry);
        if (e < 1 && d > 1e-3) {
          const k = (1 - e) * 3 * (this.path.length && !o.stay ? 0.5 : 1);
          want[0] += ((this.pos[0] - o.pos[0]) / d) * k;
          want[1] += ((this.pos[1] - o.pos[1]) / d) * k;
        }
      }
    let ax = want[0] - this.vel[0];
    let ay = want[1] - this.vel[1];
    const al = Math.hypot(ax, ay);
    const lim = this.acc * dt;
    if (al > lim) {
      ax *= lim / al;
      ay *= lim / al;
    }
    this.vel[0] += ax;
    this.vel[1] += ay;
    const sp = Math.hypot(this.vel[0], this.vel[1]);
    if (sp < 0.02 && !this.path.length) {
      this.vel = [0, 0];
      return 0;
    }
    this.pos[0] += this.vel[0] * dt;
    this.pos[1] += this.vel[1] * dt;
    return sp;
  }
  tick(dt: number) {
    if (this.V.reduced) return;
    const sp = this.steer(dt);
    if (sp > 0.18) {
      const deg = (Math.atan2(this.vel[1], this.vel[0]) * 180) / Math.PI;
      if (this.anim !== "walk") this.set("walk", dirFor(deg));
      else this.dir = dirFor(deg, this.dir);
      if (Math.abs(this.vel[0]) > 0.15) this.flip = this.vel[0] < 0;
      const before = this.phase;
      this.phase += phaseStep(sp, dt, this.stride, this.ref);
      if (Math.floor(before * 2) !== Math.floor(this.phase * 2)) {
        const [u, v] = this.V.aff.toS(this.pos[0], this.pos[1]);
        this.V.puffs.push({ u, v, t: 0, big: this.kind === "kid" });
      }
      this.still = 0;
    } else if (this.anim === "walk") {
      this.set("idle");
      this.phase = 0;
    }
    this.place();
    if (this.path.length || this.busy) return;
    this.still += dt;
    if (this.kind === "kid") {
      if (this.still > 1.6 && this.dir !== "s" && this.anim === "idle") this.set("idle", "s");
      return;
    }
    this.behave(dt);
  }
  /** Chickens live on their own: short walks, pecking, looking about; they step aside when the student passes. */
  behave(dt: number) {
    const V = this.V;
    const kid = V.actors.kid;
    if (!this.stay && kid && kid.path.length && dist(kid.pos, this.pos) < 2.4) {
      const d = dist(kid.pos, this.pos) || 1;
      const away: Pt = [(this.pos[0] - kid.pos[0]) / d, (this.pos[1] - kid.pos[1]) / d];
      const side: Pt = [-kid.vel[1], kid.vel[0]];
      const sl = Math.hypot(side[0], side[1]) || 1;
      const sgn = away[0] * side[0] + away[1] * side[1] >= 0 ? 1 : -1;
      const t: Pt = [this.pos[0] + (away[0] * 0.6 + (side[0] / sl) * sgn) * 2.0, this.pos[1] + (away[1] * 0.6 + (side[1] / sl) * sgn) * 2.0];
      if (V.freeW(t)) {
        void this.walkPath([t], 3.2).then(() => {
          this.wait = 0.6 + Math.random();
        });
        return;
      }
    }
    this.wait -= dt;
    if (this.wait > 0) return;
    const has = (n: string) => !!V.sheets?.actors[this.id]?.anims[n];
    if (this.stay) {
      this.set("idle", (["s", "se", "sw", "s", "e", "w"] as Dir[])[Math.floor(Math.random() * 6)]);
      this.wait = 2.5 + Math.random() * 4;
      return;
    }
    const r = Math.random();
    if (r < 0.35 && has("peck")) {
      this.busy = true;
      this.set("peck");
      this.onEnd = () => {
        this.busy = false;
        this.set("idle");
        this.wait = 0.5 + Math.random() * 2;
      };
    } else if (r < 0.55) {
      this.set("idle", (["s", "se", "sw", "e", "w", "ne", "nw"] as Dir[])[Math.floor(Math.random() * 7)]);
      this.wait = 1 + Math.random() * 2.5;
    } else if (r < 0.75) {
      // a stroll somewhere else in the village, round whatever is in the way
      const t = V.randomMapPoint(this);
      if (!t) {
        this.wait = 0.8;
        return;
      }
      void this.walkPath(smooth(V.grid.route(this.pos.slice() as Pt, t), 0.4), 1.5 + Math.random() * 0.6).then(() => {
        this.wait = 0.6 + Math.random() * 2.5;
      });
    } else {
      // a few steps nearby, with a little curve on the way: chickens never quite walk straight
      const fast = r > 0.93;
      const len = fast ? 2.5 + Math.random() * 2 : 1.5 + Math.random() * 3;
      let t: Pt | null = null;
      for (let k = 0; k < 10 && !t; k++) {
        const a = Math.random() * Math.PI * 2;
        const c: Pt = [this.pos[0] + Math.cos(a) * len, this.pos[1] + Math.sin(a) * len * 0.8];
        if (V.freeW(c) && V.grid.lineFree(this.pos, c) && V.plateFree(this, c)) t = c;
      }
      if (!t) {
        this.wait = 0.8;
        return;
      }
      const m: Pt = [(this.pos[0] + t[0]) / 2 + (Math.random() - 0.5) * 0.9, (this.pos[1] + t[1]) / 2 + (Math.random() - 0.5) * 0.9];
      void this.walkPath(smooth([this.pos.slice() as Pt, m, t], 0.3), fast ? 3.0 : 1.2 + Math.random() * 0.6).then(() => {
        this.wait = 0.4 + Math.random() * 2.2;
      });
    }
  }
}

/** the longest the student takes to reach a place before it opens */
const GO_MS = 1500;

interface SheetRef {
  url: string;
  frames: number;
  fps: number;
  loop: boolean;
  ready: boolean;
  dir: string;
}

export class VillageEngine {
  L: Layout;
  sheets: ActorsData | null;
  world: HTMLElement;
  scene: HTMLElement;
  aff: Affine;
  grid: Grid;
  actors: Record<string, Actor> = {};
  puffs: Puff[] = [];
  reduced: boolean;
  /** time of the last camera drag (a tap right after a drag is not a tap on the ground) */
  justDragged = 0;
  private base: string;
  private raf = 0;
  private last = 0;
  private cache: Record<string, { im: HTMLImageElement; ok: boolean }> = {};
  private stops: (() => void)[] = [];
  private dead = false;
  private extra: HTMLElement[] = [];
  private prioN = 0;
  /** place signs as boxes in world px (re-measured now and then) */
  private signBoxes: Box[] = [];
  private measuredAt = -1e9;

  constructor(private o: EngineOptions) {
    this.L = o.layout;
    this.sheets = o.sheets;
    this.world = o.world;
    this.scene = o.scene;
    this.base = o.base;
    this.reduced = o.reduced ?? (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches);
    this.aff = makeAffine(this.L.affine);
    this.grid = new Grid(this.L);
    this.world.style.setProperty("--ratio", String(this.L.size[0] / this.L.size[1]));
    this.buildPicture();
    this.fitSizes();
    const onResize = () => this.fitSizes();
    addEventListener("resize", onResize);
    this.stops.push(() => removeEventListener("resize", onResize));
    this.stops.push(startAmbient({ canvas: o.fx, steam: o.steam, layout: this.L, puffs: this.puffs, reduced: this.reduced }));
    this.camera();
    this.raf = requestAnimationFrame((t) => this.loop(t));
  }

  // ---- sizes
  get worldW() {
    return this.world.clientWidth;
  }
  /** world units -> CSS px */
  px(units: number): number {
    return units * this.L.pxPerUnit * (this.worldW / this.L.size[0]);
  }
  private fitSizes() {
    const A = this.sheets;
    const fr = A ? A.frame : [416, 416];
    const ft = A ? A.feet : [208, 380];
    const ppu = (A && A.pxPerUnit) || this.L.pxPerUnit;
    this.world.style.setProperty("--frame-w", this.px(fr[0] / ppu) + "px");
    this.world.style.setProperty("--frame-h", this.px(fr[1] / ppu) + "px");
    this.world.style.setProperty("--unit", this.px(1) + "px");
    this.world.style.setProperty("--feet-x", (ft[0] / fr[0]) * 100 + "%");
    this.world.style.setProperty("--feet-y", (ft[1] / fr[1]) * 100 + "%");
    for (const a of Object.values(this.actors)) a.el.style.setProperty("--head", this.px(a.head * 0.899) + "px");
  }

  // ---- the painted picture, the cut-outs and the places
  private buildPicture() {
    const L = this.L;
    for (const t of L.bg ?? []) {
      const im = document.createElement("img");
      im.className = "lg-bgt";
      im.alt = "";
      im.draggable = false;
      im.src = this.base + t.file;
      im.style.left = t.box[0] * 100 + "%";
      im.style.top = t.box[1] * 100 + "%";
      im.style.width = (t.box[2] - t.box[0]) * 100 + "%";
      im.style.height = (t.box[3] - t.box[1]) * 100 + "%";
      this.o.bgHost.append(im);
      this.extra.push(im);
    }
    for (const oc of L.occ ?? []) {
      const im = document.createElement("img");
      im.className = "lg-occ" + (/^tree|^bush/.test(oc.name) ? " lg-sway" : "");
      im.alt = "";
      im.decoding = "async";
      im.draggable = false;
      im.src = `${this.base}occ/${oc.name}.webp`;
      im.style.left = oc.box[0] * 100 + "%";
      im.style.top = oc.box[1] * 100 + "%";
      im.style.width = (oc.box[2] - oc.box[0]) * 100 + "%";
      im.style.height = (oc.box[3] - oc.box[1]) * 100 + "%";
      im.style.zIndex = String(Math.round(oc.base * 10000));
      im.style.animationDelay = -Math.random() * 6 + "s";
      this.o.occHost.append(im);
      this.extra.push(im);
    }
    this.placeSigns();
  }
  /** Elements with data-sign sit on layout.signs[key]. Call again after React adds or removes places. */
  placeSigns() {
    this.world.querySelectorAll<HTMLElement>("[data-sign]").forEach((el) => {
      const p = this.L.signs[el.dataset.sign ?? ""];
      if (!p) return;
      el.style.left = p[0] * 100 + "%";
      el.style.top = p[1] * 100 + "%";
    });
  }

  // ---- where one can walk
  walkable = (p: Pt): boolean => this.grid.walkable(p);
  private onPicture(p: Pt): boolean {
    const [u, v] = this.aff.toS(p[0], p[1]);
    return u > 0.05 && u < 0.95 && v > 0.22 && v < 0.95;
  }
  freeW = (p: Pt): boolean => this.walkable(p) && this.onPicture(p);
  /** Somewhere free near the chickens' home (the yard), now and then a little further out. */
  randomHomePoint(r = 9): Pt {
    const L = this.L;
    for (let k = 0; k < 40; k++) {
      const a = Math.random() * Math.PI * 2;
      const d = Math.sqrt(Math.random()) * r;
      const p: Pt = [L.home[0] + Math.cos(a) * d * 1.6, L.home[1] + Math.sin(a) * d * 0.8];
      if (this.walkable(p)) return p;
    }
    return [L.home[0], L.home[1]];
  }
  /** Anywhere in the village a chicken might stroll to: mostly along the paths, sometimes on the grass, always on the picture. */
  randomMapPoint(who?: Actor): Pt | null {
    const P = this.L.paths ?? [];
    const [bx0, by0, bx1, by1] = this.L.bounds;
    for (let k = 0; k < 40; k++) {
      let p: Pt;
      if (P.length && Math.random() < 0.6) {
        const pl = P[Math.floor(Math.random() * P.length)];
        const s = Math.floor(Math.random() * (pl.length - 1));
        const t = Math.random();
        p = [pl[s][0] + (pl[s + 1][0] - pl[s][0]) * t + (Math.random() - 0.5) * 3, pl[s][1] + (pl[s + 1][1] - pl[s][1]) * t + (Math.random() - 0.5) * 3];
      } else p = [bx0 + Math.random() * (bx1 - bx0), by0 + Math.random() * (by1 - by0)];
      if (this.walkable(p) && this.onPicture(p) && !Object.values(this.actors).some((o) => o !== who && crowded(o.pos, p, o.kind === "kid")) && (!who || this.plateFree(who, p))) return p;
    }
    return null;
  }

  // ---- sprites
  sheet(id: string, anim: string, dir: string): SheetRef | null {
    const a = this.sheets?.actors[id]?.anims[anim];
    if (!a) return null;
    const d = a.dirs.includes(dir) ? dir : a.dirs.includes("s") ? "s" : a.dirs[0];
    const url = `${this.base}actors/${id}-${anim}-${d}.webp`;
    if (!this.cache[url]) {
      const im = new Image();
      const entry = { im, ok: false };
      this.cache[url] = entry;
      im.onload = () => (entry.ok = true);
      im.src = url;
    }
    return { url, frames: a.frames, fps: a.fps, loop: a.loop, ready: this.cache[url].ok, dir: d };
  }

  // ---- actors
  addActor(el: HTMLElement, spec: ActorSpec): Actor {
    this.actors[spec.key]?.el.style.removeProperty("left");
    const a = new Actor(this, el, spec);
    a.prio = spec.kind === "kid" ? 0 : ++this.prioN;
    this.actors[spec.key] = a;
    return a;
  }
  /** Somewhere free for a new chicken: `pref` when nobody stands there, else the nearest open spot round the yard (nobody stands on anybody). */
  seat(pref: Pt | undefined, n = 0): Pt {
    const ok = (p: Pt) => this.freeW(p) && !Object.values(this.actors).some((o) => crowded(o.pos, p, o.kind === "kid")) && this.plateFree(null, p);
    if (pref && ok(pref)) return pref;
    const [hx, hy] = this.L.home;
    // later chickens start looking further out, each round the yard at its own angle, so a crowd does not form in the middle
    for (let r = 4 + n * 0.8; r < 48; r += 1.8)
      for (let k = 0; k < 18; k++) {
        const a = (k / 18) * Math.PI * 2 + n * 2.4;
        const p: Pt = [hx + Math.cos(a) * r * 1.6, hy + Math.sin(a) * r * 0.8];
        if (ok(p)) return p;
      }
    return pref ?? this.randomHomePoint();
  }
  /** A chicken grew or changed picture. */
  setLook(key: string, still: string | undefined, stage: number, head?: number) {
    const a = this.actors[key];
    if (a && (a.stillUrl !== still || a.stage !== stage)) a.look(still, stage, head);
  }
  removeActor(key: string) {
    delete this.actors[key];
  }
  setActorId(key: string, id: string) {
    const a = this.actors[key];
    if (a) {
      a.id = id;
      a.cur = null;
    }
  }
  setStay(key: string, stay: boolean) {
    const a = this.actors[key];
    if (a) a.stay = stay;
  }

  private loop(now: number) {
    if (this.dead) return;
    const dt = Math.min(0.05, (now - (this.last || now)) / 1000);
    this.last = now;
    this.relax(dt);
    for (const a of Object.values(this.actors)) {
      a.tick(dt);
      a.draw(now);
    }
    this.layoutPlates(performance.now());
    this.raf = requestAnimationFrame((t) => this.loop(t));
  }

  // ---- name plates: each hangs under its own actor; two plates (or a plate and a sign) never overlap
  /** CSS px per world unit, across and down */
  unitPx(): [number, number] {
    const [W, H] = this.wh();
    return [Math.abs(this.L.affine.ax) * W || 1, Math.abs(this.L.affine.ay) * H || 1];
  }
  private wh(): [number, number] {
    return [this.world.clientWidth || 1, this.world.clientHeight || 1];
  }
  /** The box (world px) of an actor's name plate when it stands at `p`: it hangs under the feet. */
  plateBox(a: Actor, p: Pt = a.pos, full = true): Box {
    const [W, H] = this.wh();
    const [u, v] = this.aff.toS(p[0], p[1]);
    const w = full ? a.plateW : a.miniW;
    const h = full ? a.plateH : a.miniH;
    const cx = u * W;
    const cy = v * H + 5;
    return [cx - w / 2, cy, cx + w / 2, cy + h];
  }
  /** The box (world px) of an actor's body (sprite) when it stands at `p`. */
  bodyBox(a: Actor, p: Pt = a.pos): Box {
    const [W, H] = this.wh();
    const [u, v] = this.aff.toS(p[0], p[1]);
    return [u * W + a.body[0], v * H + a.body[1], u * W + a.body[2], v * H + a.body[3]];
  }
  /** Would `who` (or a newcomer, when null) standing at `p` keep its plate clear of every other plate, sign and body? */
  plateFree(who: Actor | null, p: Pt): boolean {
    this.measure();
    const [W, H] = this.wh();
    const [u, v] = this.aff.toS(p[0], p[1]);
    const w = who?.plateW ?? 120;
    const h = who?.plateH ?? 38;
    const b: Box = [u * W - w / 2, v * H + 5, u * W + w / 2, v * H + 5 + h];
    if (this.signBoxes.some((s) => boxHit(b, s, GAP))) return false;
    return !Object.values(this.actors).some((o) => o !== who && (boxHit(b, this.plateBox(o), GAP) || boxHit(b, this.bodyBox(o), 2)));
  }
  /** The body of `a` relative to its feet, from the picture on screen (the middle of the frame: its edges are empty). */
  private measureBody(a: Actor) {
    const wr = this.world.getBoundingClientRect();
    const r = a.el.getBoundingClientRect();
    if (r.width <= 0) return;
    const [W, H] = this.wh();
    const [u, v] = this.aff.toS(a.pos[0], a.pos[1]);
    const fx = u * W;
    const fy = v * H;
    const l = r.left - wr.left;
    const t = r.top - wr.top;
    const trim = r.width * 0.2;
    a.body = [l + trim - fx, t + r.height * 0.12 - fy, l + r.width - trim - fx, Math.min(0, t + r.height - fy)];
  }
  /** Sizes of the plates and the signs, now and then (they only change with the language or the window). */
  private measure(now = performance.now()) {
    if (now - this.measuredAt < 150) return;
    this.measuredAt = now;
    for (const a of Object.values(this.actors)) {
      if (!a.tag) continue;
      const w = a.tag.offsetWidth;
      const h = a.tag.offsetHeight;
      if (w <= 0) continue;
      this.measureBody(a);
      if (a.mini) {
        a.miniW = w;
        a.miniH = h;
      } else {
        a.plateW = w;
        a.plateH = h;
      }
    }
    const wr = this.world.getBoundingClientRect();
    this.signBoxes = [...this.world.querySelectorAll<HTMLElement>(".lg-place .lg-sign, .lg-burnt")]
      .map((el) => el.getBoundingClientRect())
      .filter((r) => r.width > 0)
      .map((r): Box => [r.left - wr.left, r.top - wr.top, r.right - wr.left, r.bottom - wr.top]);
  }
  /** Every frame: keep each plate inside the view, and shrink the lower-priority one to its level badge where two would touch. */
  private layoutPlates(now: number) {
    this.measure(now);
    const sc = this.scene;
    const left = sc.scrollLeft;
    const vw = sc.clientWidth;
    const placed: Box[] = [];
    const narrow = vw < 560; // a phone: badges only, the names are on the chicken's own page
    const bodies = new Map(Object.values(this.actors).map((o) => [o, this.bodyBox(o)] as const));
    let me: Actor | null = null;
    const clash = (b: Box, m: number) =>
      placed.some((q) => boxHit(b, q, m)) || this.signBoxes.some((s) => boxHit(b, s, m)) || [...bodies].some(([o, bb]) => o !== me && boxHit(b, bb, Math.min(m, 2)));
    for (const a of Object.values(this.actors).sort((x, y) => x.prio - y.prio)) {
      if (!a.tag) continue;
      me = a;
      const shifted = (full: boolean): { box: Box; dx: number } => {
        const b = this.plateBox(a, a.pos, full);
        let dx = 0;
        if (b[2] - b[0] < vw - 12) {
          if (b[0] < left + 6 && b[2] > left) dx = left + 6 - b[0];
          else if (b[2] > left + vw - 6 && b[0] < left + vw) dx = left + vw - 6 - b[2];
        }
        return { box: [b[0] + dx, b[1], b[2] + dx, b[3]], dx };
      };
      const full = shifted(true);
      let mini = a.mini;
      if (narrow && a.kind === "ga") mini = true;
      else if (!a.mini) mini = clash(full.box, 2);
      else mini = now - a.miniAt < 700 || clash(full.box, GAP + 4);
      if (mini !== a.mini) {
        a.mini = mini;
        a.miniAt = now;
        a.tag.classList.toggle("lg-mini", mini);
      }
      const cur = mini ? shifted(false) : full;
      // even the badge would touch something: out of sight until there is room
      const gone = mini && clash(cur.box, 1);
      if (gone !== a.gone) {
        a.gone = gone;
        a.tag.classList.toggle("lg-gone", gone);
      }
      if (!gone) placed.push(cur.box);
      if (Math.abs(cur.dx - a.dx) > 0.5) {
        a.dx = cur.dx;
        a.tag.style.setProperty("--dx", cur.dx.toFixed(1) + "px");
      }
    }
  }

  /** Chickens whose plates would touch (each other, the student's, or a sign) are eased apart at once. */
  private relax(dt: number) {
    if (this.reduced) return;
    this.measure();
    const [W, H] = this.wh();
    const k = Math.min(1, dt * 8);
    const movable = (x: Actor) => x.kind === "ga" && !x.stay;
    const move = (x: Actor, dx: number, dy: number): boolean => {
      const [u, v] = this.aff.toS(x.pos[0], x.pos[1]);
      const p = this.aff.toW(u + dx / W, v + dy / H);
      if (!this.freeW(p)) return false;
      x.pos = p;
      return true;
    };
    /** push `a` (and `b` when it is a chicken too) so that boxes ba and bb part; the shorter way out first, the other if that is blocked */
    const part = (a: Actor, ba: Box, b: Actor | null, bb: Box) => {
      if (!boxHit(ba, bb, GAP)) return;
      const ma = movable(a);
      const mb = !!b && movable(b);
      if (!ma && !mb) return;
      const ox = Math.min(ba[2], bb[2]) - Math.max(ba[0], bb[0]) + GAP;
      const oy = Math.min(ba[3], bb[3]) - Math.max(ba[1], bb[1]) + GAP;
      const sx = ba[0] + ba[2] < bb[0] + bb[2] ? -1 : 1;
      const sy = ba[1] + ba[3] < bb[1] + bb[3] ? -1 : 1;
      const sa = ma && mb ? 0.5 : ma ? 1 : 0;
      const axes: [number, number, number][] = ox < oy ? [[sx, 0, ox], [0, sy, oy], [-sx, 0, ox], [0, -sy, oy]] : [[0, sy, oy], [sx, 0, ox], [0, -sy, oy], [-sx, 0, ox]];
      for (const [ax, ay, pen] of axes) {
        const s = pen * k + 0.6;
        let moved = false;
        if (sa) moved = move(a, ax * s * sa, ay * s * sa) || moved;
        if (sa < 1 && b) moved = move(b, -ax * s * (1 - sa), -ay * s * (1 - sa)) || moved;
        if (moved) return;
      }
    };
    const all = Object.values(this.actors);
    for (let i = 0; i < all.length; i++) {
      const a = all[i];
      for (let j = i + 1; j < all.length; j++) {
        part(a, this.plateBox(a), all[j], this.plateBox(all[j]));
        // a plate hangs off the body of the neighbour: ease apart as well
        part(a, this.plateBox(a, a.pos, !a.mini), all[j], this.bodyBox(all[j]));
        part(all[j], this.plateBox(all[j], all[j].pos, !all[j].mini), a, this.bodyBox(a));
      }
      if (movable(a)) for (const s of this.signBoxes) part(a, this.plateBox(a), null, s);
    }
  }
  // ---- public moves
  walkToPoint(w: Pt, who = "kid", speed?: number): Promise<void> {
    const a = this.actors[who];
    if (!a || this.reduced) return Promise.resolve();
    return a.walkPath(smooth(this.grid.route(a.pos.slice() as Pt, w), 0.4), speed);
  }
  walkTo(sign: string, who = "kid", speed?: number): Promise<void> {
    const d = this.L.doorsW[sign];
    return d ? this.walkToPoint(d, who, speed) : Promise.resolve();
  }
  jump(key: string): Promise<void> {
    return new Promise((res) => {
      const a = this.actors[key];
      if (!a || this.reduced || !this.sheets?.actors[a.id]?.anims.jump) return res();
      a.busy = true;
      a.path = [];
      a.set("jump", "s");
      a.onEnd = () => {
        a.busy = false;
        a.set("idle", "s");
        a.wait = 2;
        res();
      };
    });
  }
  wave(key = "kid"): Promise<void> {
    return new Promise((res) => {
      const a = this.actors[key];
      if (!a || this.reduced || !this.sheets?.actors[a.id]?.anims.wave) return res();
      a.set("wave", "s");
      a.onEnd = () => {
        a.set("idle", "s");
        res();
      };
    });
  }
  /** A tapped chicken without a jump sprite hops instead. */
  hop(key: string): Promise<void> {
    const a = this.actors[key];
    if (!a || this.reduced) return Promise.resolve();
    if (this.sheets?.actors[a.id]?.anims.jump) return this.jump(key);
    return new Promise((res) => {
      a.spr.animate?.([{ transform: `translateY(0) scaleX(${a.flip ? -1 : 1})` }, { transform: `translateY(-26px) scaleX(${a.flip ? -1 : 1})` }, { transform: `translateY(0) scaleX(${a.flip ? -1 : 1})` }], { duration: 420, easing: "ease-out" });
      setTimeout(res, 430);
    });
  }
  /** The student gets to a door in at most `GO_MS`: runs there, and what is left is skipped. */
  private skipper: (() => void) | null = null;
  /** A second tap while the student is on the way: stands at the door at once. */
  skipWalk() {
    this.skipper?.();
  }
  /** A place: the student runs to its door (never longer than a moment) and the view leans in (`lean`: when the place is a page). The caller opens the page after this resolves. */
  async goPlace(sign: string, lean = true): Promise<void> {
    const d = this.L.doorsW[sign];
    const kid = this.actors.kid;
    if (!d || this.reduced) return;
    if (kid) {
      const acc = kid.acc;
      await new Promise<void>((res) => {
        let over = false;
        const end = () => {
          if (over) return;
          over = true;
          clearTimeout(timer);
          if (kid.path.length || kid.busy) {
            // still on the way: stand at the door now
            kid.path = [];
            kid.busy = false;
            kid.vel = [0, 0];
            kid.pos = [d[0], d[1]];
            kid.max = kid.base;
            const cb = kid.arrive;
            kid.arrive = null;
            cb?.();
            this.centreOn?.(d, false);
          }
          kid.acc = acc;
          this.skipper = null;
          res();
        };
        const timer = setTimeout(end, GO_MS);
        this.skipper = end;
        kid.acc = 60;
        void this.walkTo(sign, "kid", 17).then(end);
      });
    }
    if (!lean) return;
    const [u, v] = this.aff.toS(d[0], d[1]);
    this.world.style.transformOrigin = `${u * 100}% ${v * 100}%`;
    this.world.classList.add("lg-enter");
    await new Promise((r) => setTimeout(r, 420));
  }
  screenToWorld = (u: number, v: number): Pt => this.aff.toW(u, v);
  walkableAt = (u: number, v: number): boolean => this.walkable(this.aff.toW(u, v));

  // ---- the view over the village: starts on the yard, follows the student, drag (or swipe) to look around
  centreOn!: (p: Pt, smoothly?: boolean) => void;
  private camera() {
    const sc = this.scene;
    const world = this.world;
    let user = 0;
    let dragging: { x: number; y: number; l: number; t: number; moved: boolean } | null = null;
    const centreOn = (p: Pt, smoothly?: boolean) => {
      const [u, v] = this.aff.toS(p[0], p[1]);
      const x = u * world.clientWidth - sc.clientWidth / 2;
      const y = v * world.clientHeight - sc.clientHeight * 0.55;
      if (typeof sc.scrollTo === "function") sc.scrollTo({ left: x, top: y, behavior: smoothly && !this.reduced ? "smooth" : "auto" });
    };
    this.centreOn = centreOn;
    centreOn(this.L.home, false);
    const onResize = () => centreOn(this.actors.kid ? this.actors.kid.pos : this.L.home, false);
    const down = (e: PointerEvent) => {
      if (e.button !== 0 || (e.target as HTMLElement).closest("button, a, input, .lg-say, .lg-hud")) return;
      dragging = { x: e.clientX, y: e.clientY, l: sc.scrollLeft, t: sc.scrollTop, moved: false };
    };
    const move = (e: PointerEvent) => {
      if (!dragging) return;
      const dx = e.clientX - dragging.x;
      const dy = e.clientY - dragging.y;
      if (Math.abs(dx) + Math.abs(dy) > 6) dragging.moved = true;
      if (dragging.moved) {
        sc.scrollLeft = dragging.l - dx;
        sc.scrollTop = dragging.t - dy;
        user = performance.now();
        sc.classList.add("lg-grab");
      }
    };
    const up = () => {
      if (dragging?.moved) this.justDragged = performance.now();
      dragging = null;
      sc.classList.remove("lg-grab");
    };
    const wheel = () => (user = performance.now());
    addEventListener("resize", onResize);
    sc.addEventListener("pointerdown", down);
    addEventListener("pointermove", move);
    addEventListener("pointerup", up);
    sc.addEventListener("wheel", wheel, { passive: true });
    let raf = 0;
    // while the student walks, keep them in the middle part of the view (unless the person is looking around)
    const follow = () => {
      const kid = this.actors.kid;
      if (kid && kid.path.length && performance.now() - user > 1500) {
        const [u, v] = this.aff.toS(kid.pos[0], kid.pos[1]);
        const kx = u * world.clientWidth - sc.scrollLeft;
        const ky = v * world.clientHeight - sc.scrollTop;
        const mx = sc.clientWidth * 0.3;
        const my = sc.clientHeight * 0.28;
        let dx = 0;
        let dy = 0;
        if (kx < mx) dx = kx - mx;
        else if (kx > sc.clientWidth - mx) dx = kx - (sc.clientWidth - mx);
        if (ky < my) dy = ky - my;
        else if (ky > sc.clientHeight - my) dy = ky - (sc.clientHeight - my);
        if (dx || dy) {
          sc.scrollLeft += dx * 0.12;
          sc.scrollTop += dy * 0.12;
        }
      }
      raf = requestAnimationFrame(follow);
    };
    raf = requestAnimationFrame(follow);
    this.stops.push(() => {
      cancelAnimationFrame(raf);
      removeEventListener("resize", onResize);
      sc.removeEventListener("pointerdown", down);
      removeEventListener("pointermove", move);
      removeEventListener("pointerup", up);
      sc.removeEventListener("wheel", wheel);
    });
  }

  destroy() {
    this.dead = true;
    cancelAnimationFrame(this.raf);
    this.stops.forEach((s) => s());
    this.extra.forEach((n) => n.remove());
    this.actors = {};
  }
}
