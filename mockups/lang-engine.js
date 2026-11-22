/* Làng gà scene engine: the rendered village (assets/ga/lang/), characters that walk around it, and the ambient life.
   Data (scripts, so the page also works from file://):
     assets/ga/lang/layout.js   window.LANG_LAYOUT: picture size, signs, doors, the walk graph, the yard, occluders
     assets/ga/lang/actors.js   window.LANG_ACTORS: sprite sheets per actor / animation / direction (8 directions)
   Markup it drives, inside #world:
     .actor[data-actor=<id>]    a character; its .spr gets the sprite sheet, its .shadow sits under the feet
     [data-sign=<key>]          positioned on layout.signs[key];  [data-node=<id>] on a place = where the student walks to
   API: Village.ready (Promise), Village.walkTo(nodeId) (Promise), Village.jump(actorId) (Promise), Village.goPlace(el, url)
*/
(function () {
  const BASE = "assets/ga/lang/";
  const RM = matchMedia("(prefers-reduced-motion: reduce)");
  const DIRS = ["e", "ne", "n", "nw", "w", "sw", "s", "se"];
  const V = (window.Village = { actors: {} });
  let L, A, world, aff, raf = 0, last = 0;

  // ---------- world <-> picture (0..1): the ground is flat and the camera orthographic, so the map is affine per axis
  function affine() {
    const { ax, bx, ay, by } = L.affine;
    return { ax, bx, ay, by, toS: (x, y) => [ax * x + bx, ay * y + by], toW: (u, v) => [(u - bx) / ax, (v - by) / ay] };
  }
  const worldW = () => world.clientWidth;
  const px = (units) => units * L.pxPerUnit * (worldW() / L.size[0]);   // world units -> CSS px

  function inPoly(x, y, poly) {
    let c = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, yi] = poly[i], [xj, yj] = poly[j];
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
    }
    return c;
  }

  // ---------- where one can walk: a grid over the village (0.5 world units), blocked by water, buildings, trunks,
  // fences (layout.block) except where a bridge crosses (layout.allow); paths are found with A* and then straightened
  const CELL = 0.5; let G = null;
  function buildGrid() {
    const [x0, y0, x1, y1] = L.bounds, nx = Math.ceil((x1 - x0) / CELL), ny = Math.ceil((y1 - y0) / CELL);
    const free = new Uint8Array(nx * ny).fill(1);
    const boxes = (polys) => polys.map((p) => ({ p, minx: Math.min(...p.map((q) => q[0])), maxx: Math.max(...p.map((q) => q[0])), miny: Math.min(...p.map((q) => q[1])), maxy: Math.max(...p.map((q) => q[1])) }));
    const B = boxes(L.block), AL = boxes(L.allow || []);
    const hit = (bs, x, y) => bs.some((b) => x >= b.minx && x <= b.maxx && y >= b.miny && y <= b.maxy && inPoly(x, y, b.p));
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const x = x0 + (i + 0.5) * CELL, y = y0 + (j + 0.5) * CELL;
      if (hit(B, x, y) && !hit(AL, x, y)) free[j * nx + i] = 0;
    }
    // the dirt paths (and the yard): walking there is cheap, so people keep to them as they would
    const road = new Uint8Array(nx * ny), r = (L.pathW || 2) / 2;
    const mark = (x, y) => { const i = Math.floor((x - x0) / CELL), j = Math.floor((y - y0) / CELL); if (i >= 0 && j >= 0 && i < nx && j < ny) road[j * nx + i] = 1; };
    for (const pl of L.paths || []) for (let k = 0; k + 1 < pl.length; k++) {
      const [ax, ay] = pl[k], [bx, by] = pl[k + 1], n = Math.ceil(Math.hypot(bx - ax, by - ay) / (CELL * 0.5));
      for (let t = 0; t <= n; t++) {
        const cx = ax + ((bx - ax) * t) / n, cy = ay + ((by - ay) * t) / n;
        for (let dy = -r; dy <= r; dy += CELL * 0.5) for (let dx = -r; dx <= r; dx += CELL * 0.5) if (dx * dx + dy * dy <= r * r) mark(cx + dx, cy + dy);
      }
    }
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      if (inPoly(x0 + (i + 0.5) * CELL, y0 + (j + 0.5) * CELL, L.yard)) road[j * nx + i] = 1;
    }
    G = { x0, y0, nx, ny, free, road };
  }
  const cellOf = (p) => [Math.floor((p[0] - G.x0) / CELL), Math.floor((p[1] - G.y0) / CELL)];
  const ok = (i, j) => i >= 0 && j >= 0 && i < G.nx && j < G.ny && G.free[j * G.nx + i] === 1;
  const centre = (i, j) => [G.x0 + (i + 0.5) * CELL, G.y0 + (j + 0.5) * CELL];
  V.walkable = (p) => { const [i, j] = cellOf(p); return ok(i, j); };
  function nearestFree(p) {
    const [ci, cj] = cellOf(p);
    for (let r = 0; r < 12; r++) for (let dj = -r; dj <= r; dj++) for (let di = -r; di <= r; di++) {
      if (Math.max(Math.abs(di), Math.abs(dj)) !== r) continue;
      if (ok(ci + di, cj + dj)) return [ci + di, cj + dj];
    }
    return null;
  }
  const onRoad = (p) => { const [i, j] = cellOf(p); return ok(i, j) && G.road[j * G.nx + i] === 1; };
  function lineFree(a, b) {  // every cell on the line free, and on the road if the line starts and ends on it
    const n = Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / (CELL * 0.5)), keepRoad = onRoad(a) && onRoad(b);
    for (let k = 0; k <= n; k++) {
      const t = k / Math.max(n, 1), [i, j] = cellOf([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
      if (!ok(i, j) || (keepRoad && !G.road[j * G.nx + i])) return false;
    }
    return true;
  }
  function route(from, to) {
    const s = nearestFree(from), g = nearestFree(to); if (!s || !g) return [to];
    const N = G.nx * G.ny, key = (i, j) => j * G.nx + i, gs = new Float32Array(N).fill(1e9), came = new Int32Array(N).fill(-1), closed = new Uint8Array(N);
    const open = [[0, s[0], s[1]]]; gs[key(...s)] = 0; const gk = key(...g);
    const h = (i, j) => Math.hypot(i - g[0], j - g[1]);
    while (open.length) {
      let bi = 0; for (let k = 1; k < open.length; k++) if (open[k][0] < open[bi][0]) bi = k;
      const [, i, j] = open.splice(bi, 1)[0], k0 = key(i, j);
      if (closed[k0]) continue; closed[k0] = 1; if (k0 === gk) break;
      for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) {
        if (!di && !dj) continue; const ni = i + di, nj = j + dj; if (!ok(ni, nj)) continue;
        if (di && dj && (!ok(i + di, j) || !ok(i, j + dj))) continue;   // no squeezing through diagonal gaps
        const k1 = key(ni, nj), ng = gs[k0] + (di && dj ? 1.414 : 1) * (G.road[k1] ? 1 : 2.6);   // grass costs more than the road
        if (ng < gs[k1]) { gs[k1] = ng; came[k1] = k0; open.push([ng + h(ni, nj), ni, nj]); }
      }
    }
    if (came[gk] < 0 && gk !== key(...s)) return [to];
    const cells = []; for (let k = gk; k >= 0; k = came[k]) { cells.unshift(centre(k % G.nx, Math.floor(k / G.nx))); if (k === key(...s)) break; }
    // straighten: keep a point only when the straight line from the last kept one is blocked
    const pts = [from.slice()]; let last = from.slice();
    for (let k = 1; k < cells.length; k++) if (!lineFree(last, cells[k])) { last = cells[k - 1]; pts.push(last); }
    pts.push(V.walkable(to) ? to : cells[cells.length - 1]);
    return pts;
  }
  // somewhere free near the chickens' home (the yard), now and then a little further out
  function randomHomePoint(r = 9) {
    for (let k = 0; k < 40; k++) {
      const a = Math.random() * Math.PI * 2, d = Math.sqrt(Math.random()) * r;
      const p = [L.home[0] + Math.cos(a) * d * 1.6, L.home[1] + Math.sin(a) * d * 0.8];
      if (V.walkable(p)) return p;
    }
    return L.home.slice();
  }
  const randomYardPoint = () => randomHomePoint();
  // anywhere in the village a chicken might stroll to: mostly along the paths, sometimes out on the grass,
  // always somewhere that shows on the picture
  const onPicture = (p) => { const [u, v] = aff.toS(p[0], p[1]); return u > 0.05 && u < 0.95 && v > 0.22 && v < 0.95; };
  function randomMapPoint() {
    const P = L.paths || [], [bx0, by0, bx1, by1] = L.bounds || [-20, -10, 20, 30];
    for (let k = 0; k < 40; k++) {
      let p;
      if (P.length && Math.random() < 0.6) {
        const pl = P[Math.floor(Math.random() * P.length)], s = Math.floor(Math.random() * (pl.length - 1)), t = Math.random();
        p = [pl[s][0] + (pl[s + 1][0] - pl[s][0]) * t + (Math.random() - 0.5) * 3, pl[s][1] + (pl[s + 1][1] - pl[s][1]) * t + (Math.random() - 0.5) * 3];
      } else p = [bx0 + Math.random() * (bx1 - bx0), by0 + Math.random() * (by1 - by0)];
      if (V.walkable(p) && onPicture(p) && !Object.values(V.actors).some((o) => dist(o.pos, p) < 2.6)) return p;
    }
    return null;
  }
  // ---------- sprites
  const cache = {};
  function sheet(id, anim, dir) {
    const a = A && A.actors[id] && A.actors[id].anims[anim]; if (!a) return null;
    const d = a.dirs.includes(dir) ? dir : a.dirs.includes("s") ? "s" : a.dirs[0];
    const url = `${BASE}actors/${id}-${anim}-${d}.webp`;
    if (!cache[url]) { const im = new Image(); im.src = url; cache[url] = { im, ok: false }; im.onload = () => (cache[url].ok = true); }
    return { url, frames: a.frames, fps: a.fps, loop: a.loop, ready: cache[url].ok, dir: d };
  }
  // heading (degrees in world space: 0 = east, 90 = away from the camera) -> one of the 8 sprite directions, with
  // hysteresis: the sprite only turns once the heading is clearly nearer another direction (no flicker on curves)
  const DIR_ANG = { e: 0, ne: 45, n: 90, nw: 135, w: 180, sw: -135, s: -90, se: -45 };
  const angDiff = (a, b) => { let d = a - b; while (d > 180) d -= 360; while (d < -180) d += 360; return Math.abs(d); };
  const dirFor = (deg, cur) => (cur && angDiff(deg, DIR_ANG[cur]) < 31 ? cur : DIRS[((Math.round(deg / 45) % 8) + 8) % 8]);
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  // a route through the path graph becomes a smooth curve (Catmull-Rom), resampled every `step` world units
  function smooth(pts, step = 0.35) {
    if (pts.length < 3) return pts.slice(1);
    const P = [pts[0], ...pts, pts[pts.length - 1]], out = [];
    for (let i = 1; i < P.length - 2; i++) {
      const p0 = P[i - 1], p1 = P[i], p2 = P[i + 1], p3 = P[i + 2], n = Math.max(2, Math.ceil(dist(p1, p2) / step));
      for (let k = 1; k <= n; k++) {
        const t = k / n, t2 = t * t, t3 = t2 * t;
        out.push([0, 1].map((j) => 0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2 + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3)));
      }
    }
    return out;
  }
  // gait: top speed and acceleration (world units/s, /s^2); stride = ground covered by one walk cycle, so the feet
  // keep pace with the ground instead of sliding
  // `ref` is the speed the walk cycle was drawn for: going faster lengthens the stride a little as well as
  // quickening the step, so a brisk walk does not turn into a frantic shuffle
  const GAIT = { kid: { max: 4.2, acc: 12, stride: 1.45, ref: 2.5 }, ga: { max: 2.1, acc: 9, stride: 0.62, ref: 1.0 } };
  const puffs = [];   // dust kicked up by footsteps, drawn by the ambient canvas
  const freeW = (p) => V.walkable(p) && onPicture(p);   // chickens may go anywhere in the village

  class Actor {
    constructor(el) {
      this.el = el; this.id = el.dataset.actor; this.kind = el.classList.contains("kid") ? "kid" : "ga";
      this.spr = el.querySelector(".spr"); this.shadow = el.querySelector(".shadow");
      this.pos = ((el.dataset.pos ? el.dataset.pos.split(",").map(Number) : null) || randomYardPoint()).slice();
      this.vel = [0, 0]; this.dir = "s"; this.anim = "idle"; this.t0 = performance.now(); this.path = []; this.phase = 0;
      const g = GAIT[this.kind]; this.base = g.max; this.max = g.max; this.acc = g.acc; this.stride = g.stride; this.ref = g.ref;
      const w = A && A.actors[this.id] && A.actors[this.id].anims.walk; if (w && w.stride) this.stride = w.stride;   // measured on the sprites
      this.stay = el.dataset.stay === "1";   // stands still (e.g. while it has something to say)
      this.head = Number(el.dataset.head || (this.kind === "kid" ? 3.6 : 3.0));   // height of the drawing, world units
      this.wait = 1 + Math.random() * 3; this.busy = false; this.cur = null; this.still = 0;
      el.style.setProperty("--head", px(this.head * 0.899) + "px");
      this.place();
    }
    set(anim, dir) {
      if (anim !== this.anim) { this.t0 = performance.now(); this.anim = anim; }
      if (dir) this.dir = dir;
    }
    place() {
      const [u, v] = aff.toS(this.pos[0], this.pos[1]);
      this.el.style.left = u * 100 + "%"; this.el.style.top = v * 100 + "%"; this.el.style.zIndex = Math.round(v * 10000);
    }
    draw(now) {
      if (!A) {  // no sprite sheets yet: the single animated sprite of the old village
        if (!this.cur && this.el.dataset.legacy) { this.cur = "legacy"; this.spr.style.backgroundImage = `url("assets/ga/${this.el.dataset.legacy}")`; this.spr.style.backgroundSize = "100% 100%"; }
        return;
      }
      let s = sheet(this.id, this.anim, this.dir);
      if (!s || !s.ready) { s = sheet(this.id, "idle", this.dir); if (!s || !s.ready) s = sheet(this.id, "idle", "s"); if (!s || !s.ready) return; }
      let f;
      if (this.anim === "walk" && s.loop) f = Math.floor((((this.phase % 1) + 1) % 1) * s.frames) % s.frames;   // in step with the ground
      else {
        f = Math.floor(((now - this.t0) / 1000) * s.fps);
        if (s.loop) f %= s.frames; else if (f >= s.frames) { f = s.frames - 1; if (this.onEnd) { const cb = this.onEnd; this.onEnd = null; cb(); } }
      }
      if (RM.matches) f = 0;
      if (this.cur !== s.url) { this.spr.style.backgroundImage = `url("${s.url}")`; this.spr.style.backgroundSize = `${s.frames * 100}% 100%`; this.cur = s.url; }
      this.spr.style.backgroundPositionX = s.frames > 1 ? (f / (s.frames - 1)) * 100 + "%" : "0%";
    }
    walkPath(path, speed) {
      this.path = path.slice(); this.busy = true; this.max = speed || this.base; this.onEnd = null;
      return new Promise((res) => (this.arrive = res));
    }
    steer(dt) {
      let want = [0, 0];
      if (this.path.length) {
        while (this.path.length > 1 && dist(this.pos, this.path[0]) < 0.5) this.path.shift();   // look ahead along the curve
        const t = this.path[0], d = dist(this.pos, t), lastPt = this.path.length === 1;
        if (lastPt && d < 0.07) {
          this.path = []; this.max = this.base; this.busy = false;
          const cb = this.arrive; this.arrive = null; cb && cb();
        } else {
          const sp = lastPt ? Math.min(this.max, Math.max(0.3, d * 2.4)) : this.max;   // ease in to the stop
          want = [((t[0] - this.pos[0]) / d) * sp, ((t[1] - this.pos[1]) / d) * sp];
        }
      }
      // give each other room: a soft push, so nobody stands inside somebody else (the speaking chicken stands firm,
      // and whoever walks past it goes round it)
      if (!this.stay) for (const o of Object.values(V.actors)) {
        if (o === this) continue;
        const d = dist(this.pos, o.pos), r = this.kind === "kid" || o.kind === "kid" ? 2.4 : 2.0;   // room for the name tags too
        if (d < r && d > 1e-3) { const k = ((r - d) / r) * (this.path.length && !o.stay ? 0.9 : 2.2); want[0] += ((this.pos[0] - o.pos[0]) / d) * k; want[1] += ((this.pos[1] - o.pos[1]) / d) * k; }
      }
      // accelerate towards what is wanted, limited: starts and stops take a moment, turns are curves
      let ax = want[0] - this.vel[0], ay = want[1] - this.vel[1]; const al = Math.hypot(ax, ay), lim = this.acc * dt;
      if (al > lim) { ax *= lim / al; ay *= lim / al; }
      this.vel[0] += ax; this.vel[1] += ay;
      const sp = Math.hypot(this.vel[0], this.vel[1]);
      if (sp < 0.02 && !this.path.length) { this.vel = [0, 0]; return 0; }
      this.pos[0] += this.vel[0] * dt; this.pos[1] += this.vel[1] * dt;
      return sp;
    }
    tick(dt) {
      if (RM.matches) return;
      const sp = this.steer(dt);
      if (sp > 0.18) {
        const deg = (Math.atan2(this.vel[1], this.vel[0]) * 180) / Math.PI;
        if (this.anim !== "walk") { this.set("walk", dirFor(deg)); } else this.dir = dirFor(deg, this.dir);
        const before = this.phase; this.phase += (sp * dt) / (this.stride * Math.max(1, Math.sqrt(sp / this.ref)));
        if (Math.floor(before * 2) !== Math.floor(this.phase * 2)) {   // a foot lands: a little dust
          const [u, v] = aff.toS(this.pos[0], this.pos[1]); puffs.push({ u, v, t: 0, big: this.kind === "kid" });
        }
        this.still = 0;
      } else if (this.anim === "walk") { this.set("idle"); this.phase = 0; }
      this.place();
      if (this.path.length || this.busy) return;
      this.still += dt;
      if (this.kind === "kid") { if (this.still > 1.6 && this.dir !== "s" && this.anim === "idle") this.set("idle", "s"); return; }   // turns to us
      this.behave(dt);
    }
    // chickens live on their own: short walks, pecking, looking about; they step aside when the student passes
    behave(dt) {
      const kid = V.actors.kid;
      if (!this.stay && kid && kid.path.length && dist(kid.pos, this.pos) < 2.4) {
        const d = dist(kid.pos, this.pos) || 1, away = [(this.pos[0] - kid.pos[0]) / d, (this.pos[1] - kid.pos[1]) / d];
        const side = [-kid.vel[1], kid.vel[0]], sl = Math.hypot(...side) || 1, sgn = away[0] * side[0] + away[1] * side[1] >= 0 ? 1 : -1;
        const t = [this.pos[0] + (away[0] * 0.6 + (side[0] / sl) * sgn) * 2.0, this.pos[1] + (away[1] * 0.6 + (side[1] / sl) * sgn) * 2.0];
        if (freeW(t)) { this.walkPath([t], 3.2).then(() => { this.wait = 0.6 + Math.random(); }); return; }
      }
      this.wait -= dt;
      if (this.wait > 0) return;
      const has = (n) => A && A.actors[this.id] && A.actors[this.id].anims[n];
      if (this.stay) { this.set("idle", ["s", "se", "sw", "s", "e", "w"][Math.floor(Math.random() * 6)]); this.wait = 2.5 + Math.random() * 4; return; }
      const r = Math.random();
      if (r < 0.35 && has("peck")) {
        this.busy = true; this.set("peck"); this.onEnd = () => { this.busy = false; this.set("idle"); this.wait = 0.5 + Math.random() * 2; };
      } else if (r < 0.55) { this.set("idle", ["s", "se", "sw", "e", "w", "ne", "nw"][Math.floor(Math.random() * 7)]); this.wait = 1 + Math.random() * 2.5; }
      else if (r < 0.75) {   // a stroll somewhere else in the village, round whatever is in the way
        const t = randomMapPoint();
        if (!t) { this.wait = 0.8; return; }
        this.walkPath(smooth(route(this.pos.slice(), t), 0.4), 1.5 + Math.random() * 0.6).then(() => { this.wait = 0.6 + Math.random() * 2.5; });
      } else {   // a few steps nearby
        const fast = r > 0.93, len = fast ? 2.5 + Math.random() * 2 : 1.5 + Math.random() * 3;
        let t = null;
        for (let k = 0; k < 10 && !t; k++) {
          const a = Math.random() * Math.PI * 2, c = [this.pos[0] + Math.cos(a) * len, this.pos[1] + Math.sin(a) * len * 0.8];
          if (freeW(c) && lineFree(this.pos, c) && !Object.values(V.actors).some((o) => o !== this && dist(o.pos, c) < 2.4)) t = c;
        }
        if (!t) { this.wait = 0.8; return; }
        // a little curve on the way, as chickens never quite walk straight
        const m = [(this.pos[0] + t[0]) / 2 + (Math.random() - 0.5) * 0.9, (this.pos[1] + t[1]) / 2 + (Math.random() - 0.5) * 0.9];
        this.walkPath(smooth([this.pos.slice(), m, t], 0.3), fast ? 3.0 : 1.2 + Math.random() * 0.6).then(() => { this.wait = 0.4 + Math.random() * 2.2; });
      }
    }
  }

  function loop(now) {
    const dt = Math.min(0.05, (now - (last || now)) / 1000); last = now;
    for (const a of Object.values(V.actors)) { a.tick(dt); a.draw(now); }
    raf = requestAnimationFrame(loop);
  }
  // ---------- public
  // walk to a place (its door, layout.doorsW[key]) or to a point, round whatever is in the way
  V.walkTo = (key, who = "kid") => { const d = L.doorsW[key]; return d ? V.walkToPoint(d, who) : Promise.resolve(); };
  V.walkToPoint = (w, who = "kid") => { const a = V.actors[who]; if (!a || RM.matches) return Promise.resolve(); return a.walkPath(smooth(route(a.pos.slice(), w), 0.4)); };
  V.jump = (id) => new Promise((res) => {
    const a = V.actors[id];
    if (!a || RM.matches || !(A && A.actors[id] && A.actors[id].anims.jump)) return res();
    a.busy = true; a.path = []; a.set("jump", "s"); a.onEnd = () => { a.busy = false; a.set("idle", "s"); a.wait = 2; res(); };
  });
  V.wave = (who = "kid") => new Promise((res) => {
    const a = V.actors[who];
    if (!a || RM.matches || !(A && A.actors[a.id] && A.actors[a.id].anims.wave)) return res();
    a.set("wave", "s"); a.onEnd = () => { a.set("idle", "s"); res(); };
  });
  V.setActorId = (who, id) => { const a = V.actors[who]; if (a) { a.id = id; a.cur = null; } };
  // a place: the student walks to its door, the view leans in, then the page opens
  V.goPlace = async (el, url) => {
    const key = el.dataset.sign;
    if (key && L.doorsW[key] && !RM.matches) {
      await V.walkTo(key);
      const [u, v] = aff.toS(...L.doorsW[key]);
      world.style.transformOrigin = `${u * 100}% ${v * 100}%`; world.classList.add("enter"); await new Promise((r) => setTimeout(r, 420));
    }
    location.href = url;
  };
  V.screenToWorld = (u, v) => aff.toW(u, v);
  V.walkableAt = (u, v) => V.walkable(aff.toW(u, v));

  // ---------- ambient life
  function ambient() {
    // steam over the warm spring
    const tpl = document.querySelector(".steam");
    if (tpl && L.steam) L.steam.forEach((p, i) => { const st = i ? tpl.cloneNode(true) : tpl; st.style.left = p[0] * 100 + "%"; st.style.top = p[1] * 100 + "%"; if (i) tpl.after(st); });
    if (RM.matches) return;
    // petals, butterflies and the odd bird on one canvas over the village (pointer events pass through)
    const cv = document.getElementById("fx"); if (!cv) return;
    const cx = cv.getContext("2d"); let W = 0, H = 0, dpr = 1;
    const size = () => { dpr = Math.min(2, devicePixelRatio || 1); W = cv.clientWidth; H = cv.clientHeight; cv.width = W * dpr; cv.height = H * dpr; };
    size(); addEventListener("resize", size);
    const petals = [], flies = [], birds = [];
    const PET = ["#ffc0d6", "#ffd6e4", "#ffe3ec", "#fff4f8"];
    function petal() { return { x: Math.random() * W * 1.1, y: -10 - Math.random() * H * 0.3, vx: 10 + Math.random() * 18, vy: 16 + Math.random() * 16, r: 3 + Math.random() * 3, a: Math.random() * 6, va: 1 + Math.random() * 2, c: PET[Math.floor(Math.random() * 4)] }; }
    for (let i = 0; i < 14; i++) { const p = petal(); p.y = Math.random() * H; petals.push(p); }
    const BF = ["#ffd94a", "#ffffff", "#b99cff"];
    for (let i = 0; i < 3; i++) flies.push({ x: Math.random() * W, y: H * (0.6 + Math.random() * 0.35), tx: 0, ty: 0, t: Math.random() * 10, c: BF[i % 3], k: 0 });
    let birdT = 6 + Math.random() * 8;
    let prev = performance.now();
    function frame(now) {
      const dt = Math.min(0.05, (now - prev) / 1000); prev = now;
      cx.setTransform(dpr, 0, 0, dpr, 0, 0); cx.clearRect(0, 0, W, H);
      const s = W / 1600;
      for (const p of petals) {  // pink petals drifting on the wind, turning
        p.x += (p.vx + Math.sin(now / 900 + p.a) * 14) * dt * s; p.y += p.vy * dt * s; p.a += p.va * dt;
        if (p.y > H + 10 || p.x > W + 20) Object.assign(p, petal());
        cx.save(); cx.translate(p.x, p.y); cx.rotate(p.a); cx.scale(1, Math.abs(Math.cos(p.a * 1.3)) * 0.7 + 0.3);
        cx.fillStyle = p.c; cx.beginPath(); cx.ellipse(0, 0, p.r * s * 1.6, p.r * s, 0, 0, Math.PI * 2); cx.fill(); cx.restore();
      }
      for (const b of flies) {  // butterflies: wander between flowers on the lawn, flapping
        b.t += dt;
        if (!b.k || Math.hypot(b.tx - b.x, b.ty - b.y) < 6) { b.tx = Math.random() * W; b.ty = H * (0.55 + Math.random() * 0.4); b.k = 1; }
        const dx = b.tx - b.x, dy = b.ty - b.y, d = Math.hypot(dx, dy) || 1;
        b.x += (dx / d) * 38 * s * dt + Math.sin(b.t * 3) * 0.6; b.y += (dy / d) * 38 * s * dt + Math.cos(b.t * 4.4) * 0.8;
        const w = Math.abs(Math.sin(b.t * 18)) * 7 * s + 1.5 * s;
        cx.fillStyle = b.c; cx.strokeStyle = "rgba(58,36,24,.55)"; cx.lineWidth = 1;
        for (const sd of [-1, 1]) { cx.beginPath(); cx.ellipse(b.x + sd * w * 0.6, b.y, w, 5 * s, sd * 0.4, 0, Math.PI * 2); cx.fill(); cx.stroke(); }
        cx.fillStyle = "#3a2418"; cx.fillRect(b.x - 1, b.y - 4 * s, 2, 8 * s);
      }
      for (let i = puffs.length - 1; i >= 0; i--) {  // footstep dust: two soft puffs that grow and fade
        const p = puffs[i]; p.t += dt; if (p.t > 0.55) { puffs.splice(i, 1); continue; }
        const k = p.t / 0.55, r = (p.big ? 7 : 5) * s * (0.6 + k * 1.2);
        cx.fillStyle = `rgba(214, 186, 140, ${0.38 * (1 - k)})`;
        for (const sd of [-1, 1]) { cx.beginPath(); cx.ellipse(p.u * W + sd * r * 0.9, p.v * H - r * 0.2 - k * 4 * s, r, r * 0.55, 0, 0, Math.PI * 2); cx.fill(); }
      }
      birdT -= dt;  // now and then a few birds cross the sky
      if (birdT < 0) { const y = H * (0.03 + Math.random() * 0.07); for (let i = 0; i < 3; i++) birds.push({ x: -30 - i * 26, y: y + (i % 2) * 10, t: Math.random() * 3 }); birdT = 14 + Math.random() * 14; }
      for (let i = birds.length - 1; i >= 0; i--) {
        const b = birds[i]; b.x += 70 * s * dt; b.t += dt * 7; if (b.x > W + 40) { birds.splice(i, 1); continue; }
        const f = Math.sin(b.t) * 5 * s; cx.strokeStyle = "rgba(58,60,90,.7)"; cx.lineWidth = 2 * s; cx.lineCap = "round";
        cx.beginPath(); cx.moveTo(b.x - 9 * s, b.y + f); cx.quadraticCurveTo(b.x - 4 * s, b.y - 3 * s, b.x, b.y); cx.quadraticCurveTo(b.x + 4 * s, b.y - 3 * s, b.x + 9 * s, b.y + f); cx.stroke();
      }
      if (!document.hidden) requestAnimationFrame(frame); else document.addEventListener("visibilitychange", () => requestAnimationFrame((t) => { prev = t; frame(t); }), { once: true });
    }
    requestAnimationFrame(frame);
  }

  // ---------- the view over the village: starts on the yard, follows the student, drag (or swipe) to look around
  function camera() {
    const sc = document.getElementById("scene"); if (!sc) return;
    const kid = V.actors.kid; let user = 0, dragging = null;
    const centreOn = (p, smooth) => {
      const [u, v] = aff.toS(p[0], p[1]);
      const x = u * world.clientWidth - sc.clientWidth / 2, y = v * world.clientHeight - sc.clientHeight * 0.55;
      sc.scrollTo({ left: x, top: y, behavior: smooth && !RM.matches ? "smooth" : "auto" });
    };
    centreOn(L.home, false); addEventListener("resize", () => centreOn(kid ? kid.pos : L.home, false));
    sc.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || e.target.closest("button, a, input, .say, .hud")) return;
      dragging = { x: e.clientX, y: e.clientY, l: sc.scrollLeft, t: sc.scrollTop, moved: false };
    });
    addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const dx = e.clientX - dragging.x, dy = e.clientY - dragging.y;
      if (Math.abs(dx) + Math.abs(dy) > 6) dragging.moved = true;
      if (dragging.moved) { sc.scrollLeft = dragging.l - dx; sc.scrollTop = dragging.t - dy; user = performance.now(); sc.classList.add("grab"); }
    });
    addEventListener("pointerup", () => { if (dragging && dragging.moved) V.justDragged = performance.now(); dragging = null; sc.classList.remove("grab"); });
    sc.addEventListener("wheel", () => (user = performance.now()), { passive: true });
    // while the student walks, keep them in the middle part of the view (unless the person is looking around)
    (function follow() {
      if (kid && kid.path.length && performance.now() - user > 1500) {
        const [u, v] = aff.toS(kid.pos[0], kid.pos[1]), kx = u * world.clientWidth - sc.scrollLeft, ky = v * world.clientHeight - sc.scrollTop;
        const mx = sc.clientWidth * 0.3, my = sc.clientHeight * 0.28;
        let dx = 0, dy = 0;
        if (kx < mx) dx = kx - mx; else if (kx > sc.clientWidth - mx) dx = kx - (sc.clientWidth - mx);
        if (ky < my) dy = ky - my; else if (ky > sc.clientHeight - my) dy = ky - (sc.clientHeight - my);
        if (dx || dy) { sc.scrollLeft += dx * 0.12; sc.scrollTop += dy * 0.12; }
      }
      requestAnimationFrame(follow);
    })();
    V.centreOn = centreOn;
  }

  // ---------- build
  V.ready = new Promise((resolve) => {
    function start() {
      L = window.LANG_LAYOUT; A = window.LANG_ACTORS || null; world = document.getElementById("world");
      if (!L || !world) return;
      world.style.setProperty("--ratio", String(L.size[0] / L.size[1]));   // the picture's shape decides the world's
      aff = affine(); buildGrid();
      // the painted picture, in a few tiles
      const bgw = document.getElementById("bg") || world;
      for (const t of L.bg || []) {
        const im = document.createElement("img"); im.className = "bgt"; im.alt = ""; im.src = BASE + t.file;
        im.style.left = t.box[0] * 100 + "%"; im.style.top = t.box[1] * 100 + "%"; im.style.width = (t.box[2] - t.box[0]) * 100 + "%"; im.style.height = (t.box[3] - t.box[1]) * 100 + "%";
        bgw.append(im);
      }
      // occluders: cut-outs drawn over characters that stand behind them
      const occ = document.getElementById("occ") || world;
      for (const o of L.occ || []) {
        const im = document.createElement("img"); im.className = "occ" + (/^tree|^bush/.test(o.name) ? " sway" : ""); im.alt = ""; im.decoding = "async";
        im.src = `${BASE}occ/${o.name}.webp`; im.style.left = o.box[0] * 100 + "%"; im.style.top = o.box[1] * 100 + "%";
        im.style.width = (o.box[2] - o.box[0]) * 100 + "%"; im.style.height = (o.box[3] - o.box[1]) * 100 + "%"; im.style.zIndex = Math.round(o.base * 10000);
        im.style.animationDelay = -Math.random() * 6 + "s"; occ.append(im);
      }
      // signs and places
      document.querySelectorAll("[data-sign]").forEach((el) => {
        const p = L.signs[el.dataset.sign]; if (!p) return; el.style.left = p[0] * 100 + "%"; el.style.top = p[1] * 100 + "%";
      });
      // characters
      document.querySelectorAll("#world .actor[data-actor]").forEach((el) => { const a = new Actor(el); V.actors[el.dataset.who || a.id] = a; });
      const fitSizes = () => {
        const fr = A ? A.frame : [416, 416], ft = A ? A.feet : [208, 380];
        world.style.setProperty("--frame-w", px(fr[0] / A_ppu()) + "px"); world.style.setProperty("--frame-h", px(fr[1] / A_ppu()) + "px");
        world.style.setProperty("--feet-x", (ft[0] / fr[0]) * 100 + "%"); world.style.setProperty("--feet-y", (ft[1] / fr[1]) * 100 + "%");
        for (const a of Object.values(V.actors)) a.el.style.setProperty("--head", px(a.head * 0.899) + "px");
      };
      const A_ppu = () => (A && A.pxPerUnit) || L.pxPerUnit;
      fitSizes(); addEventListener("resize", fitSizes);
      ambient(); camera();
      // one loop for every character (with reduced motion it still runs, so the first frame shows once loaded, but
      // nobody walks and every animation holds its first frame)
      raf = requestAnimationFrame(loop);
      resolve(V);
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
  });
})();
