/** Keeping the village readable: name tags that do not pile up, the market icon clear of the signs, signs not cut by the edge. */

export interface R {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export const overlaps = (a: R, b: R, pad = 0) => !(a.right + pad <= b.left || b.right + pad <= a.left || a.bottom + pad <= b.top || b.bottom + pad <= a.top);

/** Scroll shift (px, positive = scroll right) that brings a sign cut by the left or right edge fully into view; 0 when whole, out of view, or too far. */
export function nudgeIntoView(r: R, vw: number, margin = 14, max = 170): number {
  if (r.right > vw - margin && r.left < vw - margin) {
    const d = r.right - (vw - margin);
    return d <= max ? d : 0;
  }
  if (r.left < margin && r.right > margin) {
    const d = r.left - margin;
    return -d <= max ? d : 0;
  }
  return 0;
}

/** How far (px, >= 0, upwards) each name tag has to lift so that none sits on another. The nearest (lowest) tag stays; the others stack above it. */
export function spreadTags(rects: R[], gap = 3, cap = 64): number[] {
  const out = rects.map(() => 0);
  const placed: R[] = [];
  const order = rects.map((_, i) => i).sort((a, b) => rects[b].bottom - rects[a].bottom || rects[a].left - rects[b].left);
  for (const i of order) {
    const r = rects[i];
    let dy = 0;
    for (let k = 0; k < 6 && dy < cap; k++) {
      const cur = { ...r, top: r.top - dy, bottom: r.bottom - dy };
      const o = placed.find((p) => overlaps(cur, p, gap));
      if (!o) break;
      dy += cur.bottom - o.top + gap;
    }
    dy = Math.min(dy, cap);
    out[i] = dy;
    placed.push({ ...r, top: r.top - dy, bottom: r.bottom - dy });
  }
  return out;
}

/** Where the market icon (height `h`) may sit: its usual top, or just below whichever sign it would cover. */
export function marketTop(baseTop: number, h: number, left: number, right: number, signs: R[], vh: number, gap = 10): number {
  let y = baseTop;
  for (let k = 0; k < 4; k++) {
    const hit = signs.find((s) => overlaps({ left, right, top: y, bottom: y + h }, s, 4));
    if (!hit) break;
    y = hit.bottom + gap;
  }
  return Math.min(y, Math.max(baseTop, vh - h - 8));
}

/** Is the picture box of an actor mostly under a canopy that is drawn in front of it? */
export function mostlyCovered(spr: R, canopies: { box: R; front: boolean }[]): boolean {
  const area = (spr.right - spr.left) * (spr.bottom - spr.top);
  if (area <= 0) return false;
  const cx = (spr.left + spr.right) / 2;
  const cy = spr.top + (spr.bottom - spr.top) * 0.55;
  return canopies.some((c) => {
    if (!c.front || cx < c.box.left || cx > c.box.right || cy < c.box.top || cy > c.box.bottom) return false;
    const w = Math.min(spr.right, c.box.right) - Math.max(spr.left, c.box.left);
    const h = Math.min(spr.bottom, c.box.bottom) - Math.max(spr.top, c.box.top);
    return w > 0 && h > 0 && (w * h) / area > 0.6;
  });
}

/** Runs the keepers every 220 ms while the village is on screen; returns the stop function. */
export function keepVillageReadable(host: { world: HTMLElement; scene: HTMLElement; market: HTMLElement | null }): () => void {
  const { world, scene, market } = host;
  const lifts = new WeakMap<HTMLElement, number>();
  const rect = (el: Element): R => {
    const b = el.getBoundingClientRect();
    return { left: b.left, top: b.top, right: b.right, bottom: b.bottom };
  };
  let ghost: HTMLElement | null = null;
  let nudged = false;
  const baseTop = market ? parseFloat(getComputedStyle(market).top) || 74 : 74;

  const tick = () => {
    const vw = scene.clientWidth;
    const vh = window.innerHeight;
    // signs cut by the edge: once, at the start
    const signs = [...world.querySelectorAll<HTMLElement>(".lg-place .lg-sign")];
    const signRects = signs.map(rect).filter((r) => r.right - r.left > 0);
    if (!nudged && signRects.length) {
      nudged = true;
      const d = signRects.map((r) => nudgeIntoView(r, vw)).find((x) => x !== 0);
      if (d) scene.scrollLeft += d;
    }
    // market icon clear of the signs
    if (market) {
      const b = market.getBoundingClientRect();
      const y = marketTop(baseTop, b.height || 120, b.left, b.right, signRects, vh);
      market.style.top = `${Math.round(y)}px`;
    }
    // name tags that do not pile up
    const plates = [...world.querySelectorAll<HTMLElement>(".lg-actor .lg-plate")].filter((p) => p.offsetParent !== null);
    const rects = plates.map((p) => {
      const r = rect(p);
      const l = lifts.get(p) ?? 0;
      return { ...r, top: r.top + l, bottom: r.bottom + l };
    });
    const dys = spreadTags(rects);
    plates.forEach((p, i) => {
      if ((lifts.get(p) ?? 0) !== dys[i]) {
        lifts.set(p, dys[i]);
        p.style.setProperty("--py", `${-dys[i]}px`);
      }
    });
    // the kid never vanishes behind a canopy: the name tag is drawn again above everything
    const kid = world.querySelector<HTMLElement>(".lg-actor.is-kid");
    const kp = kid?.querySelector<HTMLElement>(".lg-plate");
    const spr = kid?.querySelector<HTMLElement>(".lg-spr");
    if (kid && kp && spr) {
      const z = parseInt(kid.style.zIndex || "0", 10);
      const canopies = [...world.querySelectorAll<HTMLElement>(".lg-occ")].map((c) => ({ box: rect(c), front: parseInt(c.style.zIndex || "0", 10) > z }));
      if (mostlyCovered(rect(spr), canopies)) {
        if (!ghost) {
          ghost = document.createElement("span");
          ghost.className = "lg-plate lg-ghost";
          ghost.setAttribute("aria-hidden", "true");
          world.append(ghost);
        }
        if (ghost.innerHTML !== kp.innerHTML) ghost.innerHTML = kp.innerHTML;
        const w = world.getBoundingClientRect();
        const r = rect(kp);
        ghost.style.left = `${r.left - w.left}px`;
        ghost.style.top = `${r.top - w.top}px`;
        ghost.hidden = false;
        kp.style.visibility = "hidden";
      } else {
        if (ghost) ghost.hidden = true;
        kp.style.visibility = "";
      }
    }
  };
  const id = setInterval(tick, 220);
  const first = setTimeout(tick, 400);
  return () => {
    clearInterval(id);
    clearTimeout(first);
    ghost?.remove();
  };
}
