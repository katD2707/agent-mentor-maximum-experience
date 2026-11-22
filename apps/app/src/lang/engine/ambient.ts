import type { Layout } from "./geometry";

export interface Puff {
  u: number;
  v: number;
  t: number;
  big: boolean;
}

/**
 * Ambient life on one canvas over the village (pointer events pass through): pink petals on the wind, butterflies on the
 * lawn, now and then a few birds, and the dust kicked up by footsteps. The steam over the warm spring is placed here too.
 * Returns a function that stops everything.
 */
export function startAmbient(opts: { canvas: HTMLCanvasElement | null; steam: HTMLElement | null; layout: Layout; puffs: Puff[]; reduced: boolean }): () => void {
  const { canvas: cv, steam: tpl, layout: L, puffs, reduced } = opts;
  const made: HTMLElement[] = [];
  if (tpl && L.steam)
    L.steam.forEach((p, i) => {
      const st = i ? (tpl.cloneNode(true) as HTMLElement) : tpl;
      st.style.left = p[0] * 100 + "%";
      st.style.top = p[1] * 100 + "%";
      if (i) {
        tpl.after(st);
        made.push(st);
      }
    });
  const cleanSteam = () => made.forEach((n) => n.remove());
  if (reduced || !cv) return cleanSteam;
  const cx = cv.getContext("2d");
  if (!cx) return cleanSteam;

  let W = 0;
  let H = 0;
  let dpr = 1;
  const size = () => {
    dpr = Math.min(2, devicePixelRatio || 1);
    W = cv.clientWidth;
    H = cv.clientHeight;
    cv.width = W * dpr;
    cv.height = H * dpr;
  };
  size();
  addEventListener("resize", size);

  const PET = ["#ffc0d6", "#ffd6e4", "#ffe3ec", "#fff4f8"];
  const petal = () => ({ x: Math.random() * W * 1.1, y: -10 - Math.random() * H * 0.3, vx: 10 + Math.random() * 18, vy: 16 + Math.random() * 16, r: 3 + Math.random() * 3, a: Math.random() * 6, va: 1 + Math.random() * 2, c: PET[Math.floor(Math.random() * 4)] });
  const petals = Array.from({ length: 14 }, () => ({ ...petal(), y: Math.random() * H }));
  const BF = ["#ffd94a", "#ffffff", "#b99cff"];
  const flies = Array.from({ length: 3 }, (_, i) => ({ x: Math.random() * W, y: H * (0.6 + Math.random() * 0.35), tx: 0, ty: 0, t: Math.random() * 10, c: BF[i % 3], k: 0 }));
  const birds: { x: number; y: number; t: number }[] = [];
  let birdT = 6 + Math.random() * 8;
  let prev = performance.now();
  let raf = 0;
  let stopped = false;

  function frame(now: number) {
    if (stopped || !cx) return;
    const dt = Math.min(0.05, (now - prev) / 1000);
    prev = now;
    cx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cx.clearRect(0, 0, W, H);
    const s = W / 1600;
    for (const p of petals) {
      p.x += (p.vx + Math.sin(now / 900 + p.a) * 14) * dt * s;
      p.y += p.vy * dt * s;
      p.a += p.va * dt;
      if (p.y > H + 10 || p.x > W + 20) Object.assign(p, petal());
      cx.save();
      cx.translate(p.x, p.y);
      cx.rotate(p.a);
      cx.scale(1, Math.abs(Math.cos(p.a * 1.3)) * 0.7 + 0.3);
      cx.fillStyle = p.c;
      cx.beginPath();
      cx.ellipse(0, 0, p.r * s * 1.6, p.r * s, 0, 0, Math.PI * 2);
      cx.fill();
      cx.restore();
    }
    for (const b of flies) {
      b.t += dt;
      if (!b.k || Math.hypot(b.tx - b.x, b.ty - b.y) < 6) {
        b.tx = Math.random() * W;
        b.ty = H * (0.55 + Math.random() * 0.4);
        b.k = 1;
      }
      const dx = b.tx - b.x;
      const dy = b.ty - b.y;
      const d = Math.hypot(dx, dy) || 1;
      b.x += (dx / d) * 38 * s * dt + Math.sin(b.t * 3) * 0.6;
      b.y += (dy / d) * 38 * s * dt + Math.cos(b.t * 4.4) * 0.8;
      const w = Math.abs(Math.sin(b.t * 18)) * 7 * s + 1.5 * s;
      cx.fillStyle = b.c;
      cx.strokeStyle = "rgba(58,36,24,.55)";
      cx.lineWidth = 1;
      for (const sd of [-1, 1]) {
        cx.beginPath();
        cx.ellipse(b.x + sd * w * 0.6, b.y, w, 5 * s, sd * 0.4, 0, Math.PI * 2);
        cx.fill();
        cx.stroke();
      }
      cx.fillStyle = "#3a2418";
      cx.fillRect(b.x - 1, b.y - 4 * s, 2, 8 * s);
    }
    for (let i = puffs.length - 1; i >= 0; i--) {
      const p = puffs[i];
      p.t += dt;
      if (p.t > 0.55) {
        puffs.splice(i, 1);
        continue;
      }
      const k = p.t / 0.55;
      const r = (p.big ? 7 : 5) * s * (0.6 + k * 1.2);
      cx.fillStyle = `rgba(214, 186, 140, ${0.38 * (1 - k)})`;
      for (const sd of [-1, 1]) {
        cx.beginPath();
        cx.ellipse(p.u * W + sd * r * 0.9, p.v * H - r * 0.2 - k * 4 * s, r, r * 0.55, 0, 0, Math.PI * 2);
        cx.fill();
      }
    }
    birdT -= dt;
    if (birdT < 0) {
      const y = H * (0.03 + Math.random() * 0.07);
      for (let i = 0; i < 3; i++) birds.push({ x: -30 - i * 26, y: y + (i % 2) * 10, t: Math.random() * 3 });
      birdT = 14 + Math.random() * 14;
    }
    for (let i = birds.length - 1; i >= 0; i--) {
      const b = birds[i];
      b.x += 70 * s * dt;
      b.t += dt * 7;
      if (b.x > W + 40) {
        birds.splice(i, 1);
        continue;
      }
      const f = Math.sin(b.t) * 5 * s;
      cx.strokeStyle = "rgba(58,60,90,.7)";
      cx.lineWidth = 2 * s;
      cx.lineCap = "round";
      cx.beginPath();
      cx.moveTo(b.x - 9 * s, b.y + f);
      cx.quadraticCurveTo(b.x - 4 * s, b.y - 3 * s, b.x, b.y);
      cx.quadraticCurveTo(b.x + 4 * s, b.y - 3 * s, b.x + 9 * s, b.y + f);
      cx.stroke();
    }
    if (!document.hidden) raf = requestAnimationFrame(frame);
    else
      document.addEventListener(
        "visibilitychange",
        () =>
          requestAnimationFrame((t) => {
            prev = t;
            frame(t);
          }),
        { once: true },
      );
  }
  raf = requestAnimationFrame(frame);
  return () => {
    stopped = true;
    cancelAnimationFrame(raf);
    removeEventListener("resize", size);
    cleanSteam();
  };
}
