import { G, GUIDE_DEFS, GUIDE_TOURS, HELLO, type GuideDef, type GuideText, type TourStepRef } from "./data";

/**
 * The chicken guide (ported from mockups/ga-guide.js): a small chicken that stands in a free spot of the screen. One tap
 * opens its help; hold and drag it onto anything to get that explained; the first visit of a screen walks through its main
 * parts once. Focus rings that script puts on the chicken only show for keyboard users (data-input="kbd" on <html>).
 */
export interface GuideOptions {
  /** screen key: login | first | village | ... (a key of GUIDE_TOURS, and the `page` of GUIDE_DEFS) */
  screen: string;
  /** the chicken's name and picture */
  name: string;
  image: string;
  lang: () => "vi" | "en";
  adult: () => boolean;
  kid: () => boolean;
  /** first-visit tours are shown once per person and screen */
  seen: () => boolean;
  markSeen: () => void;
  defs?: GuideDef[];
  tours?: Record<string, TourStepRef[]>;
  /** where the chicken may not stand (CSS selector) */
  avoid?: string;
  /** parked: stands in a fixed corner dock (default: every screen but the village, login and first run, where it roams) */
  park?: boolean;
  /** a timed exam or a lesson is running: no tour now */
  quiet?: () => boolean;
}
export interface GuideHandle {
  el: HTMLButtonElement;
  startTour(): boolean;
  /** re-render whatever is open (the language changed) */
  refresh(): void;
  destroy(): void;
}

type Res = { kind: "guide"; el: Element; g: GuideText } | { kind: "tour"; el: Element | null; g: GuideText } | { kind: "empty" };
interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}
interface Step {
  el: Element | null;
  g: GuideText;
}

const AVOID_DEFAULT = '.cg-dock, .lg-hud, .lg-tray, .lg-place, .lg-sheet, .lg-toast, .lg-actor .lg-hit, a[href], button:not(.cg), input, textarea, select, [role="button"], [tabindex="0"]';

/** Screens whose first-visit tour already ran in this page session: each tip shows once, even if the saved flag is lost. */
const toured = new Set<string>();
/** "Xem lại từ đầu": every screen may walk its tour again. */
export const resetToured = () => toured.clear();

/** Screens where the chicken walks about; on every other screen it waits in the corner dock, out of the content. */
export const ROAMING = new Set(["village"]);
/** A timed exam or a lesson is on screen: the guide stays out of the way and gives no tour. */
export const examOrLesson = () => !!document.querySelector("[data-exam], .lp");

export function createGuide(o: GuideOptions): GuideHandle {
  const park = o.park ?? !ROAMING.has(o.screen);
  const quiet = o.quiet ?? examOrLesson;
  const root = document.documentElement;
  const RM = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : ({ matches: false } as MediaQueryList);
  const defs = o.defs ?? GUIDE_DEFS;
  const tours = o.tours ?? GUIDE_TOURS;
  const AVOID = o.avoid ?? AVOID_DEFAULT;
  const tr = (vi: string, en: string) => (o.lang() === "en" ? en : vi);
  const wait = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
  const settle = async (anim: Animation | undefined, ms: number) => {
    if (!anim) return wait(Math.min(ms, 30));
    await Promise.race([anim.finished.catch(() => undefined), wait(ms)]);
    try {
      anim.cancel();
    } catch {
      /* already done */
    }
  };
  const pageGuides = () => defs.filter((g) => !g.page || g.page === o.screen);

  // keyboard or pointer: focus rings put there by script only show for keyboard users
  const onKeyInput = (e: KeyboardEvent) => {
    if (e.key === "Tab" || e.key.startsWith("Arrow") || e.key === "Enter" || e.key === " ") root.dataset.input = "kbd";
  };
  const onPtrInput = () => {
    root.dataset.input = "ptr";
  };
  document.addEventListener("keydown", onKeyInput, true);
  document.addEventListener("pointerdown", onPtrInput, true);

  const NAME = o.name;
  const el = document.createElement("button");
  el.type = "button";
  el.className = park ? "cg parked" : "cg";
  el.setAttribute("aria-expanded", "false");
  el.innerHTML = `<span class="cg-flip"><span class="cg-fig"><span class="cg-img" aria-hidden="true"><img alt="" src="${o.image}"></span></span></span>`;
  const label = () => el.setAttribute("aria-label", tr(`${NAME}, người hướng dẫn`, `${NAME}, your guide`));
  label();
  document.body.appendChild(el);

  let pos = { x: 0, y: 0 };
  let bubble: HTMLElement | null = null;
  let tail: HTMLElement | null = null;
  let spot: HTMLElement | null = null;
  let catcher: HTMLElement | null = null;
  let hinted: Element | null = null;
  let current: { kind: "help" | "explain" | "say"; render?: () => void; avoid?: Rect | null; close: () => void } | null = null;
  let busy = false;
  let drag: { sx: number; sy: number; t: number; ox: number; oy: number; on: boolean; moved: number; id: number; hold?: ReturnType<typeof setTimeout> } | null = null;
  let lastFocus: HTMLElement | null = null;
  let tour: { steps: Step[]; i: number; y: number } | null = null;
  let dustTimer: ReturnType<typeof setInterval> | null = null;
  const timers: ReturnType<typeof setTimeout>[] = [];
  let dead = false;

  const vw = () => document.documentElement.clientWidth;
  const vh = () => window.innerHeight;
  const size = () => ({ w: el.offsetWidth || 56, h: el.offsetHeight || 72 });
  const place = (x: number, y: number) => {
    pos = { x, y };
    el.style.left = Math.round(x) + "px";
    el.style.top = Math.round(y) + "px";
  };
  const clampPos = (x: number, y: number) => {
    const { w, h } = size();
    return { x: Math.min(Math.max(8, x), Math.max(8, vw() - w - 8)), y: Math.min(Math.max(8, y), Math.max(8, vh() - h - 8)) };
  };
  const rectOf = (): Rect => ({ left: pos.x, top: pos.y, right: pos.x + size().w, bottom: pos.y + size().h, width: size().w, height: size().h });
  const hit = (a: Rect | DOMRect, b: Rect | DOMRect, pad: number) => !(a.right + pad <= b.left || b.right + pad <= a.left || a.bottom + pad <= b.top || b.bottom + pad <= a.top);
  const visible = (n: Element | null): n is Element => {
    if (!n || n.closest("[hidden]")) return false;
    const r = n.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  function avoidRects(): DOMRect[] {
    const out: DOMRect[] = [];
    document.querySelectorAll(AVOID).forEach((n) => {
      if (n.closest(".cg, .cg-bubble")) return;
      if (!visible(n)) return;
      const r = n.getBoundingClientRect();
      if (r.bottom < 0 || r.top > vh() || r.right < 0 || r.left > vw()) return;
      out.push(r);
    });
    return out;
  }
  const topLimit = () => 8 + 10;
  function candidates() {
    const { w, h } = size();
    const m = 14;
    const out: { x: number; y: number }[] = [];
    const top = topLimit();
    const bottom = vh() - h - m;
    for (let y = bottom; y >= top; y -= 26) {
      out.push({ x: vw() - w - m, y });
      out.push({ x: m, y });
    }
    for (let x = m; x <= vw() - w - m; x += 34) out.push({ x, y: bottom });
    return out;
  }
  function freeSpots(exclude?: Rect | null) {
    const av: (Rect | DOMRect)[] = avoidRects();
    if (exclude) av.push(exclude);
    const { w, h } = size();
    return candidates().filter((c) => {
      const r = { left: c.x, top: c.y, right: c.x + w, bottom: c.y + h, width: w, height: h };
      return !av.some((a) => hit(r, a, 6));
    });
  }
  function defaultSpot() {
    const { w, h } = size();
    if (park) return clampPos(vw() - w - 14, vh() - h - 14);
    const free = freeSpots();
    if (free.length) {
      free.sort((a, b) => vw() - a.x + (vh() - a.y) - (vw() - b.x + (vh() - b.y)));
      return free[0];
    }
    return clampPos(vw() - w - 14, vh() - h - 14);
  }
  function randomSpot(exclude?: Rect | null) {
    if (park) return defaultSpot();
    const free = freeSpots(exclude).filter((c) => Math.hypot(c.x - pos.x, c.y - pos.y) > 110);
    if (!free.length) return defaultSpot();
    return free[Math.floor(Math.random() * free.length)];
  }
  const POSKEY = `mentor.guide.pos.${o.screen}`;
  function savePos() {
    if (park) return;
    try {
      localStorage.setItem(POSKEY, JSON.stringify({ fx: pos.x / vw(), fy: pos.y / vh() }));
    } catch {
      /* ignore */
    }
  }
  function restorePos() {
    if (park) return defaultSpot();
    try {
      const s = JSON.parse(localStorage.getItem(POSKEY) || "null") as { fx: number; fy: number } | null;
      if (s && isFinite(s.fx) && isFinite(s.fy)) {
        const p = clampPos(s.fx * vw(), s.fy * vh());
        const { w, h } = size();
        const r = { left: p.x, top: p.y, right: p.x + w, bottom: p.y + h, width: w, height: h };
        if (!avoidRects().some((a) => hit(r, a, 4))) return p;
      }
    } catch {
      /* fall through */
    }
    return defaultSpot();
  }

  // ---- motion
  function stopDust() {
    if (dustTimer) clearInterval(dustTimer);
    dustTimer = null;
  }
  function startDust(dx: number) {
    stopDust();
    dustTimer = setInterval(() => {
      const r = el.getBoundingClientRect();
      const d = document.createElement("i");
      d.className = "cg-dust";
      d.style.left = r.left + r.width / 2 - 5 + (dx > 0 ? -10 : 10) + "px";
      d.style.top = r.bottom - 9 + "px";
      d.style.setProperty("--dx", (dx > 0 ? -12 : 12) + "px");
      document.body.appendChild(d);
      setTimeout(() => d.remove(), 650);
    }, 110);
  }
  async function moveTo(dest: { x: number; y: number }, mode: "hop" | "run") {
    const from = { ...pos };
    const to = clampPos(dest.x, dest.y);
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const dist = Math.hypot(dx, dy);
    if (dist < 2) return;
    if (RM.matches) {
      place(to.x, to.y);
      return;
    }
    if (Math.abs(dx) > 4) el.classList.toggle("face-left", dx < 0);
    const run = mode === "run";
    const duration = run ? Math.min(2000, Math.max(520, dist / 0.5)) : 440;
    const arc = run ? -Math.min(70, dist * 0.18) : -Math.min(46, 18 + dist * 0.08);
    el.classList.add(run ? "is-running" : "is-hopping");
    if (run && !o.adult()) startDust(dx); // teachers and university students get no dust trail
    place(to.x, to.y);
    const a = el.animate?.([{ transform: `translate(${-dx}px, ${-dy}px)` }, { transform: `translate(${-dx / 2}px, ${-dy / 2 + arc}px)`, offset: 0.5 }, { transform: "translate(0, 0)" }], { duration, easing: run ? "cubic-bezier(.35,.1,.3,1)" : "cubic-bezier(.3,.7,.4,1)" });
    await settle(a, duration + 120);
    stopDust();
    el.classList.remove("is-running", "is-hopping");
    el.querySelector(".cg-fig")?.animate?.([{ transform: "scale(1.12, .86)" }, { transform: "scale(.96, 1.05)" }, { transform: "none" }], { duration: 260, easing: "ease-out" });
  }

  // ---- bubbles
  function removeBubble() {
    bubble?.remove();
    tail?.remove();
    bubble = tail = null;
  }
  function placeBubble(avoid?: Rect | null) {
    if (!bubble || !tail) return;
    const m = 12;
    const gap = 34;
    const W = vw();
    const H = vh();
    const bw = bubble.offsetWidth;
    const bh = bubble.offsetHeight;
    const a = rectOf();
    const cx = a.left + a.width / 2;
    const cy = a.top + a.height / 2;
    const clampX = (x: number) => Math.min(Math.max(m, x), W - bw - m);
    const clampY = (y: number) => Math.min(Math.max(m, y), H - bh - m);
    const opts = [
      { side: "above", x: clampX(cx - bw * 0.75), y: a.top - bh - gap },
      { side: "left", x: a.left - bw - gap, y: clampY(cy - bh * 0.7) },
      { side: "right", x: a.right + gap, y: clampY(cy - bh * 0.7) },
      { side: "below", x: clampX(cx - bw * 0.75), y: a.bottom + gap },
    ];
    const fits = (p: { x: number; y: number }) => p.x >= m && p.y >= m && p.x + bw <= W - m && p.y + bh <= H - m;
    const overlap = (p: { x: number; y: number }) => {
      if (!avoid) return 0;
      const w = Math.max(0, Math.min(p.x + bw, avoid.right) - Math.max(p.x, avoid.left));
      const h = Math.max(0, Math.min(p.y + bh, avoid.bottom) - Math.max(p.y, avoid.top));
      return w * h;
    };
    let best: { side: string; x: number; y: number; s: number; alt?: boolean } | null = null;
    for (const p of opts.filter(fits)) {
      const s = overlap(p);
      if (!best || s < best.s) best = { ...p, s };
    }
    // every place beside the guide would cover what it is explaining: stand clear above or below the target itself
    if (avoid && (!best || best.s > 0)) {
      const alts = [
        { side: "above", x: clampX(cx - bw * 0.75), y: avoid.top - bh - 14, alt: true },
        { side: "below", x: clampX(cx - bw * 0.75), y: avoid.bottom + 14, alt: true },
      ];
      for (const p of alts.filter(fits)) {
        const s = overlap(p);
        if (!best || s < best.s) best = { ...p, s };
      }
    }
    if (!best) best = { side: "above", x: clampX(cx - bw / 2), y: clampY(a.top - bh - gap), s: 0 };
    bubble.style.left = best.x + "px";
    bubble.style.top = best.y + "px";
    const t = best.alt
      ? [Math.min(Math.max(cx - 23, best.x + 14), best.x + bw - 40), best.side === "above" ? best.y + bh - 2 : best.y - 26]
      : ({ above: [cx - 23, a.top - 28], below: [cx - 23, a.bottom + 4], left: [a.left - 40, cy - 22], right: [a.right - 6, cy - 22] } as Record<string, number[]>)[best.side];
    tail.style.left = Math.min(Math.max(4, t[0]), W - 50) + "px";
    tail.style.top = Math.min(Math.max(4, t[1]), H - 28) + "px";
  }
  function showBubble(html: string, avoid?: Rect | null) {
    removeBubble();
    bubble = document.createElement("div");
    bubble.className = "cg-bubble";
    bubble.setAttribute("role", "dialog");
    bubble.setAttribute("aria-label", tr(`${NAME} nói`, `${NAME} says`));
    bubble.innerHTML = html;
    tail = document.createElement("div");
    tail.className = "cg-tail";
    tail.setAttribute("aria-hidden", "true");
    tail.innerHTML = "<i></i><i></i><i></i>";
    document.body.appendChild(tail);
    document.body.appendChild(bubble);
    placeBubble(avoid);
  }
  let talkT: ReturnType<typeof setTimeout> | undefined;
  const talk = (text: string) => {
    el.classList.add("is-talking");
    clearTimeout(talkT);
    talkT = setTimeout(() => el.classList.remove("is-talking"), Math.min(4200, Math.max(1200, text.length * 45)));
  };
  function speakAloud(text: string) {
    if (!o.kid() || !("speechSynthesis" in window)) return;
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = o.lang() === "en" ? "en-US" : "vi-VN";
      u.rate = 0.95;
      speechSynthesis.speak(u);
    } catch {
      /* no voice */
    }
  }
  const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string);

  // ---- help bubble: one tap on the guide
  function picks() {
    const seen: Element[] = [];
    const out: { g: GuideDef; n: Element }[] = [];
    for (const g of pageGuides()) {
      if (out.length >= 4) break;
      const n = Array.from(document.querySelectorAll(g.sel)).find((x) => visible(x));
      if (!n || seen.some((s) => s === n || s.contains(n) || n.contains(s))) continue;
      seen.push(n);
      out.push({ g, n });
    }
    return out;
  }
  function openHelp() {
    closeAll(false);
    const list = picks();
    const render = () => {
      const lang = o.lang();
      const chips = (tours[o.screen] ? `<button type="button" data-replay>${tr("Chỉ lại trang này", "Show me this page again")}</button>` : "") + list.map((p, i) => `<button type="button" data-pick-i="${i}">${esc(p.g[lang].t)}</button>`).join("");
      showBubble(`<p class="cg-say">${tr("Cần mình chỉ chỗ nào? Nhấn giữ rồi kéo mình đến đó nhé!", "Need help with something? Hold and drag me there!")}</p>` + (chips ? `<div class="cg-chips" role="group" aria-label="${tr("Hoặc chọn nhanh", "Or pick one")}">${chips}</div>` : ""));
      bubble?.querySelectorAll<HTMLElement>("[data-pick-i]").forEach((b) =>
        b.addEventListener("click", () => {
          const p = list[Number(b.dataset.pickI)];
          closeAll(false);
          void explain({ kind: "guide", el: p.n, g: p.g });
        }),
      );
      bubble?.querySelector("[data-replay]")?.addEventListener("click", () => {
        closeAll(false);
        startTour();
      });
    };
    render();
    talk(tr("Cần mình chỉ chỗ nào?", "Need help with something?"));
    el.classList.add("is-waving");
    el.setAttribute("aria-expanded", "true");
    current = {
      kind: "help",
      render,
      close: () => {
        removeBubble();
        el.classList.remove("is-waving", "is-talking");
        el.setAttribute("aria-expanded", "false");
      },
    };
  }

  // ---- what the guide was dropped on
  const labelOf = (n: Element) => {
    const t = n.getAttribute("aria-label") || ((n as HTMLElement).innerText || "").trim().replace(/\s+/g, " ") || n.getAttribute("placeholder") || n.getAttribute("title") || (n as HTMLInputElement).value || "";
    return t.length > 42 ? t.slice(0, 40).trim() + "…" : t;
  };
  function resolve(t: Element | null): Res {
    if (!t || t === document.documentElement || t === document.body) return { kind: "empty" };
    if (t.closest(".cg, .cg-bubble, .cg-tail")) return { kind: "empty" };
    let best: { el: Element; g: GuideText | null } | null = null;
    const consider = (m: Element | null, g: GuideText | null) => {
      if (!m || m === document.body) return;
      if (!best || (best.el !== m && best.el.contains(m))) best = { el: m, g };
    };
    consider(t.closest("[data-guide]"), null);
    for (const g of pageGuides()) consider(t.closest(g.sel), g);
    const b = best as { el: Element; g: GuideText | null } | null;
    if (b) {
      if (!b.g) {
        const n = b.el as HTMLElement;
        const nm = labelOf(n);
        b.g = { vi: { t: n.dataset.guideTitle || nm, d: n.dataset.guide || "" }, en: { t: n.dataset.guideTitleEn || n.dataset.guideTitle || nm, d: n.dataset.guideEn || n.dataset.guide || "" } };
      }
      return { kind: "guide", el: b.el, g: b.g };
    }
    const f = t.closest('button, a[href], input, textarea, select, summary, label, [role="button"], [role="radio"]');
    if (f && visible(f)) {
      const nm = labelOf(f) || tr("nút này", "this control");
      return { kind: "guide", el: f, g: { vi: { t: nm, d: `Đây là “${nm}”. Bấm vào để dùng.` }, en: { t: nm, d: `This is “${nm}”. Tap it to use it.` } } };
    }
    return { kind: "empty" };
  }

  // ---- explain a feature, then run off
  function standBeside(r: Rect) {
    const { w, h } = size();
    const m = 10;
    const W = vw();
    const H = vh();
    const room = { right: W - r.right, left: r.left, below: H - r.bottom, above: r.top - topLimit() };
    const cy = Math.min(Math.max(r.top + r.height / 2 - h / 2, topLimit()), H - h - m);
    const cx = Math.min(Math.max(r.left + r.width / 2 - w / 2, m), W - w - m);
    const order = (Object.keys(room) as (keyof typeof room)[]).sort((a, b) => room[b] - room[a]);
    for (const side of order) {
      if (side === "right" && room.right >= w + 2 * m) return { x: r.right + m, y: cy };
      if (side === "left" && room.left >= w + 2 * m) return { x: r.left - w - m, y: cy };
      if (side === "below" && room.below >= h + 2 * m) return { x: cx, y: r.bottom + m };
      if (side === "above" && room.above >= h + 2 * m) return { x: cx, y: r.top - h - m };
    }
    return clampPos(r.right - w - m, r.bottom - h - m);
  }
  function clipToView(r: DOMRect, pad: number): Rect {
    const left = Math.max(4, r.left - pad);
    const top = Math.max(4, r.top - pad);
    const right = Math.min(vw() - 4, r.right + pad);
    const bottom = Math.min(vh() - 4, r.bottom + pad);
    return { left, top, right, bottom, width: right - left, height: bottom - top };
  }
  async function explain(res: Res) {
    if (res.kind === "empty") {
      busy = true;
      openExplain(null, { vi: { t: "", d: "Chỗ này chưa có gì để hướng dẫn. Thử kéo mình vào một nút hoặc một ô nhé." }, en: { t: "", d: "Nothing to explain here. Try dragging me onto a button or a box." } });
      return;
    }
    busy = true;
    if (!tour || tour.i === 0) lastFocus = document.activeElement && document.activeElement !== document.body ? (document.activeElement as HTMLElement) : el;
    if (!res.el) {
      makeCatcher();
      el.classList.add("is-waving");
      openExplain(rectOf(), res.g);
      return;
    }
    const target = res.el;
    let r = target.getBoundingClientRect();
    if (r.top < topLimit() || r.bottom > vh() || r.left < 0 || r.right > vw()) {
      target.scrollIntoView?.({ block: "center", inline: "center", behavior: RM.matches ? "auto" : "smooth" });
      await wait(RM.matches ? 30 : 450);
      r = target.getBoundingClientRect();
    }
    // a chicken on the map: light up the bird and its name tag together, as an oval, not the box of its tap area
    const who = target.matches(".lg-actor .lg-hit") ? (target.closest(".lg-actor") as HTMLElement | null)?.dataset.id : null;
    const plate = who ? document.querySelector(`.lg-plate[data-for="${who}"]`) : null;
    if (plate) {
      const p = plate.getBoundingClientRect();
      r = new DOMRect(Math.min(r.left, p.left), Math.min(r.top, p.top), Math.max(r.right, p.right) - Math.min(r.left, p.left), Math.max(r.bottom, p.bottom) - Math.min(r.top, p.top));
    }
    const vr = clipToView(r, plate ? 14 : 8);
    spot = document.createElement("div");
    spot.className = "cg-spot" + (plate ? " round" : "");
    Object.assign(spot.style, { left: vr.left + "px", top: vr.top + "px", width: vr.width + "px", height: vr.height + "px" });
    makeCatcher();
    document.body.appendChild(spot);
    await moveTo(standBeside(vr), "hop");
    const me = rectOf();
    el.classList.toggle("face-left", vr.left + vr.width / 2 < me.left + me.width / 2);
    openExplain(vr, res.g);
  }
  // A clear layer over the page while the guide explains. Alone, a tap ends the explanation. In a tour the only way on is the
  // button: taps and scrolls are swallowed and the bubble gives a little nudge instead.
  function makeCatcher() {
    catcher = document.createElement("div");
    catcher.className = "cg-catch";
    catcher.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      if (tour) nudge();
      else void closeExplain();
    });
    catcher.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        if (tour) nudge();
        else void closeExplain();
      },
      { passive: false },
    );
    catcher.addEventListener("touchmove", (e) => e.preventDefault(), { passive: false });
    document.body.appendChild(catcher);
  }
  function nudge() {
    if (!bubble) return;
    bubble.classList.remove("cg-nudge");
    void bubble.offsetWidth;
    bubble.classList.add("cg-nudge");
    bubble.querySelector<HTMLElement>(".cg-ok")?.focus({ preventScroll: true });
  }
  function openExplain(avoid: Rect | null, g: GuideText) {
    const t = tour;
    const n = t ? t.steps.length : 0;
    const last = !t || t.i >= n - 1;
    const render = () => {
      const c = g[o.lang()];
      const count = t && n > 1 ? `<span class="cg-n">${t.i + 1}/${n}</span>` : "";
      const ok = `<button type="button" class="cg-ok">${last ? tr("Hiểu rồi", "Got it") : tr("Hiểu rồi, tiếp", "Got it, next")}</button>`;
      showBubble((c.t ? `<p class="cg-t">${esc(c.t)}${count}</p>` : "") + `<p class="cg-d">${esc(c.d)}</p>` + (t && !last ? `<div class="cg-acts"><button type="button" class="cg-skip">${tr("Bỏ qua", "Skip")}</button>${ok}</div>` : ok), avoid);
      bubble?.querySelector(".cg-ok")?.addEventListener("click", () => (last ? void closeExplain() : nextStep()));
      bubble?.querySelector(".cg-skip")?.addEventListener("click", () => void closeExplain());
    };
    render();
    const c = g[o.lang()];
    talk(c.d);
    speakAloud((c.t ? c.t + ". " : "") + c.d);
    current = { kind: "explain", render, avoid, close: () => undefined };
    bubble?.querySelector<HTMLElement>(".cg-ok")?.focus({ preventScroll: true });
  }
  function teardownExplain() {
    current = null;
    removeBubble();
    spot?.remove();
    catcher?.remove();
    spot = catcher = null;
    el.classList.remove("is-talking", "is-waving");
    try {
      speechSynthesis.cancel();
    } catch {
      /* no voice */
    }
  }
  async function closeExplain() {
    if (!current || current.kind !== "explain") return;
    const avoid = current.avoid;
    teardownExplain();
    await wrapUp(avoid);
  }
  async function wrapUp(avoid: Rect | null | undefined) {
    const t = tour;
    tour = null;
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus({ preventScroll: true });
    if (t && Math.abs(window.scrollY - t.y) > 4) {
      window.scrollTo({ top: t.y, behavior: RM.matches ? "auto" : "smooth" });
      await wait(RM.matches ? 30 : 420);
      avoid = null;
    }
    await wait(RM.matches ? 0 : 160);
    if (dead) return;
    await moveTo(randomSpot(avoid), "run");
    savePos();
    busy = false;
  }

  // ---- tour
  function tourSteps(): Step[] {
    const out: Step[] = [];
    for (const s of tours[o.screen] ?? []) {
      if (out.length >= 3) break;
      if (s === HELLO) {
        const adult = o.adult();
        out.push({
          el: null,
          g: {
            vi: { t: `${adult ? "Chào bạn" : "Chào em"}, mình là ${NAME}!`, d: `Lần đầu ${adult ? "bạn" : "em"} mở một trang, mình sẽ chỉ nhanh vài chỗ chính. Sau đó cần gì cứ bấm vào mình.` },
            en: { t: `Hi, I'm ${NAME}!`, d: "The first time you open a page I'll point out its main parts. After that, tap me whenever you need help." },
          },
        });
        continue;
      }
      const g = typeof s === "string" ? defs.find((x) => x.sel === s) ?? G(s, "", "", "", "") : s;
      const n = Array.from(document.querySelectorAll(g.sel)).find((x) => visible(x));
      if (n && g.vi.d && !out.some((p) => p.el && (p.el.contains(n) || n.contains(p.el)))) out.push({ el: n, g });
    }
    return out.some((s) => s.el) ? out : [];
  }
  function startTour(): boolean {
    if (quiet()) return false;
    const steps = tourSteps();
    if (!steps.length) return false;
    closeAll(false);
    tour = { steps, i: 0, y: window.scrollY };
    void explain({ kind: "tour", el: steps[0].el, g: steps[0].g });
    return true;
  }
  function nextStep() {
    if (!tour) return;
    teardownExplain();
    let s: Step | undefined;
    do s = tour.steps[++tour.i];
    while (s && s.el && !visible(s.el));
    if (!s) {
      void wrapUp(null);
      return;
    }
    void explain({ kind: "tour", el: s.el, g: s.g });
  }
  function closeAll(andRun: boolean) {
    if (current && current.kind === "explain") {
      if (andRun) void closeExplain();
      else {
        teardownExplain();
        tour = null;
        busy = false;
      }
      return;
    }
    current?.close();
    current = null;
  }

  // ---- pointer: tap vs hold-and-drag
  function setHint(n: Element | null) {
    if (hinted === n) return;
    hinted?.classList.remove("cg-hint");
    hinted = n;
    hinted?.classList.add("cg-hint");
  }
  function underPointer(x: number, y: number) {
    el.style.pointerEvents = "none";
    const t = document.elementFromPoint?.(x, y) ?? null;
    el.style.pointerEvents = "";
    return t;
  }
  function beginDrag() {
    if (!drag || drag.on) return;
    drag.on = true;
    clearTimeout(drag.hold);
    closeAll(false);
    el.classList.remove("is-waving");
    el.classList.add("is-dragging");
  }
  const onDown = (e: PointerEvent) => {
    if (e.button !== 0 || busy) return;
    e.preventDefault();
    drag = { sx: e.clientX, sy: e.clientY, t: performance.now(), ox: e.clientX - pos.x, oy: e.clientY - pos.y, on: false, moved: 0, id: e.pointerId };
    try {
      el.setPointerCapture(e.pointerId);
    } catch {
      /* not capturable */
    }
    drag.hold = setTimeout(beginDrag, 250);
  };
  const onMove = (e: PointerEvent) => {
    if (!drag) return;
    drag.moved = Math.max(drag.moved, Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy));
    if (!drag.on && drag.moved > 6) beginDrag();
    if (!drag.on) return;
    const p = clampPos(e.clientX - drag.ox, e.clientY - drag.oy);
    place(p.x, p.y);
    const res = resolve(underPointer(e.clientX, e.clientY));
    setHint(res.kind === "guide" ? res.el : null);
  };
  const onUp = (e: PointerEvent) => {
    if (!drag) return;
    const d = drag;
    drag = null;
    clearTimeout(d.hold);
    try {
      el.releasePointerCapture(d.id);
    } catch {
      /* not captured */
    }
    if (d.on) {
      el.classList.remove("is-dragging");
      setHint(null);
      if (d.moved < 6) return;
      void explain(resolve(underPointer(e.clientX, e.clientY)));
      return;
    }
    if (performance.now() - d.t < 250 && d.moved < 6) toggleHelp();
  };
  const onCancel = () => {
    if (!drag) return;
    clearTimeout(drag.hold);
    drag = null;
    el.classList.remove("is-dragging");
    setHint(null);
  };
  function toggleHelp() {
    if (current && current.kind === "help") closeAll(false);
    else openHelp();
  }
  el.addEventListener("pointerdown", onDown);
  el.addEventListener("pointermove", onMove);
  el.addEventListener("pointerup", onUp);
  el.addEventListener("pointercancel", onCancel);
  el.addEventListener("lostpointercapture", (e) => {
    if (drag && drag.on) onUp(e as PointerEvent);
  });
  el.addEventListener("click", (e) => e.preventDefault());
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggleHelp();
    }
  });
  const onEsc = (e: KeyboardEvent) => {
    if (e.key !== "Escape" || !current) return;
    if (current.kind === "explain") void closeExplain();
    else {
      closeAll(false);
      el.focus({ preventScroll: true });
    }
  };
  const onOutside = (e: PointerEvent) => {
    if (!current || current.kind === "explain") return;
    if ((e.target as Element).closest(".cg, .cg-bubble")) return;
    closeAll(false);
  };
  document.addEventListener("keydown", onEsc);
  document.addEventListener("pointerdown", onOutside, true);
  let redo: ReturnType<typeof setTimeout> | undefined;
  const onResize = () => {
    if (tour) {
      clearTimeout(redo);
      redo = setTimeout(() => {
        if (!tour || !current || current.kind !== "explain") return;
        teardownExplain();
        const s = tour.steps[tour.i];
        void explain({ kind: "tour", el: s.el, g: s.g });
      }, 180);
    } else if (current && current.kind === "explain") closeAll(false);
    const q = clampPos(pos.x, pos.y);
    place(q.x, q.y);
    if (bubble) placeBubble(current?.avoid);
  };
  addEventListener("resize", onResize);

  // idle life: nothing to animate beyond the CSS bob, so only the first placement and the first-visit tour
  const p0 = restorePos();
  place(p0.x, p0.y);
  el.animate?.([{ opacity: 0, transform: "translateY(16px) scale(.8)" }, { opacity: 1, transform: "none" }], { duration: RM.matches ? 1 : 420, easing: "cubic-bezier(.2,.9,.3,1.3)" });

  // first visit of this screen: walk through it once, as soon as the person isn't busy (typing, a dialog open, dragging)
  if (tours[o.screen] && !o.seen()) {
    let tries = 0;
    const free = () => {
      const a = document.activeElement as HTMLElement | null;
      const typing = a && (a.matches("input, textarea, select, [contenteditable]") || a.isContentEditable);
      const open = document.querySelector('.lg-sheet, [role="dialog"]:not(.cg-bubble)');
      return !current && !drag && !busy && !typing && !open && document.visibilityState === "visible";
    };
    const attempt = () => {
      if (dead || o.seen()) return;
      if (quiet()) {
        if (++tries < 20) timers.push(setTimeout(attempt, 1500));
        return;
      }
      if (!free() || !tourSteps().length) {
        if (++tries < 20) timers.push(setTimeout(attempt, 1500));
        return;
      }
      if (toured.has(o.screen)) return; // already walked through in this session (storage may not keep it)
      toured.add(o.screen);
      o.markSeen();
      startTour();
    };
    timers.push(setTimeout(attempt, 1400));
  }

  return {
    el,
    startTour,
    refresh() {
      label();
      current?.render?.();
    },
    destroy() {
      dead = true;
      timers.forEach(clearTimeout);
      clearTimeout(talkT);
      clearTimeout(redo);
      stopDust();
      teardownExplain();
      closeAll(false);
      setHint(null);
      document.removeEventListener("keydown", onKeyInput, true);
      document.removeEventListener("pointerdown", onPtrInput, true);
      document.removeEventListener("keydown", onEsc);
      document.removeEventListener("pointerdown", onOutside, true);
      removeEventListener("resize", onResize);
      el.remove();
    },
  };
}
