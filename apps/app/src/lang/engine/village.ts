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
  /** height of the drawing, world units */
  head?: number;
  /** still picture for an actor without sprite sheets */
  still?: string;
}

type Anim = "idle" | "walk" | "peck" | "jump" | "wave";

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
    this.head = spec.head ?? (spec.kind === "kid" ? 3.6 : 3.0);
    this.stillUrl = spec.still;
    const w = V.sheets?.actors[spec.id]?.anims.walk;
    if (w?.stride) this.stride = w.stride;
    el.style.setProperty("--head", V.px(this.head * 0.899) + "px");
    this.place();
  }
  get hasSheets(): boolean {
    return !!this.V.sheets?.actors[this.id];
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
  }
  draw(now: number) {
    const A = this.V.sheets;
    if (!this.hasSheets || !A) {
      // no walking sprites: the still picture, bobbing a little (a small hop while it walks)
      if (this.stillUrl && this.cur !== this.stillUrl) {
        this.cur = this.stillUrl;
        this.spr.style.backgroundImage = `url("${this.stillUrl}")`;
        this.spr.style.backgroundSize = "100% 100%";
        this.spr.style.backgroundPositionY = "4%";
      }
      if (this.V.reduced) return;
      const walking = this.anim === "walk";
      const bob = walking ? -Math.abs(Math.sin(this.phase * Math.PI * 2)) * 7 : Math.sin(now / 520 + this.pos[0]) * 1.6;
      this.spr.style.transform = `translateY(${bob.toFixed(1)}px) scaleX(${this.flip ? -1 : 1})`;
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
        const r = this.kind === "kid" || o.kind === "kid" ? 2.4 : 2.0;
        if (d < r && d > 1e-3) {
          const k = ((r - d) / r) * (this.path.length && !o.stay ? 0.9 : 2.2);
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
      const t = V.randomMapPoint();
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
        if (V.freeW(c) && V.grid.lineFree(this.pos, c) && !Object.values(V.actors).some((o) => o !== this && dist(o.pos, c) < 2.4)) t = c;
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
  randomMapPoint(): Pt | null {
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
      if (this.walkable(p) && this.onPicture(p) && !Object.values(this.actors).some((o) => dist(o.pos, p) < 2.6)) return p;
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
    this.actors[spec.key] = a;
    return a;
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
    for (const a of Object.values(this.actors)) {
      a.tick(dt);
      a.draw(now);
    }
    this.raf = requestAnimationFrame((t) => this.loop(t));
  }

  // ---- public moves
  walkToPoint(w: Pt, who = "kid"): Promise<void> {
    const a = this.actors[who];
    if (!a || this.reduced) return Promise.resolve();
    return a.walkPath(smooth(this.grid.route(a.pos.slice() as Pt, w), 0.4));
  }
  walkTo(sign: string, who = "kid"): Promise<void> {
    const d = this.L.doorsW[sign];
    return d ? this.walkToPoint(d, who) : Promise.resolve();
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
  /** A place: the student walks to its door and the view leans in. The caller opens the page after this resolves. */
  async goPlace(sign: string): Promise<void> {
    const d = this.L.doorsW[sign];
    if (d && !this.reduced) {
      await this.walkTo(sign);
      const [u, v] = this.aff.toS(d[0], d[1]);
      this.world.style.transformOrigin = `${u * 100}% ${v * 100}%`;
      this.world.classList.add("lg-enter");
      await new Promise((r) => setTimeout(r, 420));
    }
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
