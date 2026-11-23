/** Keeping the village readable: signs not cut by the edge. (Chickens stand apart in the engine; their name tags hang right under them in a layer over the scenery.) */

export interface R {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

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

/** Runs the keeper every 220 ms while the village is on screen; returns the stop function. */
export function keepVillageReadable(host: { world: HTMLElement; scene: HTMLElement }): () => void {
  const { world, scene } = host;
  const rect = (el: Element): R => {
    const b = el.getBoundingClientRect();
    return { left: b.left, top: b.top, right: b.right, bottom: b.bottom };
  };
  let nudged = false;

  const tick = () => {
    const vw = scene.clientWidth;
    // signs cut by the edge: once, at the start
    const signs = [...world.querySelectorAll<HTMLElement>(".lg-place .lg-sign")];
    const signRects = signs.map(rect).filter((r) => r.right - r.left > 0);
    if (!nudged && signRects.length) {
      nudged = true;
      const d = signRects.map((r) => nudgeIntoView(r, vw)).find((x) => x !== 0);
      if (d) scene.scrollLeft += d;
    }
  };
  const id = setInterval(tick, 220);
  const first = setTimeout(tick, 400);
  return () => {
    clearInterval(id);
    clearTimeout(first);
  };
}
