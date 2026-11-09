// <mentor-mascot>: "Mực", the in-app guide (an original purple ink drop holding a pencil).
// Dependency-free ES module, SSR-safe (importing on a server touches no DOM globals).
// Tap it for a small chat window; hold and drag it onto any area to hear what that area does.
// The element never calls an API: the host sets `ask` and `guides`. See README.md.

const STR = {
  vi: {
    label: "Mực, trợ lý hướng dẫn",
    title: "Bạn cần mình hướng dẫn gì?",
    placeholder: "Gõ câu hỏi về cách dùng app",
    send: "Gửi",
    close: "Đóng",
    show: "Chỉ cho mình",
    showHint: "Hoặc chọn một chỗ để mình giải thích:",
    tip: "Mẹo: nhấn giữ rồi kéo mình tới bất kỳ chỗ nào.",
    unknown: "Chỗ này mình chưa biết. Bạn thử kéo mình sang chỗ khác nhé!",
    gotIt: "Hiểu rồi",
    noAsk: "Mình chưa trả lời câu hỏi được lúc này. Bạn thử kéo mình tới chỗ cần hỏi nhé.",
    failed: "Mình chưa trả lời được lúc này. Bạn thử lại sau nhé.",
    thinking: "Mực đang trả lời",
    you: "Bạn",
    mascot: "Mực",
    says: "Mực nói",
    next: "Hiểu rồi, tiếp",
    skip: "Bỏ qua",
    replay: "Chỉ lại trang này",
    step: "Bước {n} trên {total}",
  },
  en: {
    label: "Mực, your guide",
    title: "What can I show you?",
    placeholder: "Ask how to use the app",
    send: "Send",
    close: "Close",
    show: "Show me",
    showHint: "Or pick a spot and I'll explain it:",
    tip: "Tip: hold me and drag me onto anything.",
    unknown: "I don't know this spot yet. Try dragging me somewhere else!",
    gotIt: "Got it",
    noAsk: "I can't answer questions right now. Try dragging me onto the thing you're wondering about.",
    failed: "I couldn't answer just now. Please try again in a bit.",
    thinking: "Mực is answering",
    you: "You",
    mascot: "Mực",
    says: "Mực says",
    next: "Got it, next",
    skip: "Skip",
    replay: "Show me this page again",
    step: "Step {n} of {total}",
  },
};

// Interactive things Mực should not stand on.
const DEFAULT_AVOID =
  'a[href], button, input, textarea, select, summary, label, video, iframe, [role="button"], [role="link"], [role="tab"], [contenteditable="true"], [tabindex]:not([tabindex="-1"]), [data-mascot-avoid]';

const SVG =
  '<svg class="svg" viewBox="0 0 80 100" aria-hidden="true" focusable="false">' +
  '<defs><linearGradient id="g" x1="0" y1="0" x2=".35" y2="1"><stop offset="0" stop-color="var(--_a)"/><stop offset="1" stop-color="var(--_b)"/></linearGradient></defs>' +
  '<ellipse class="shadow" cx="40" cy="97" rx="20" ry="3" fill="rgba(0,0,0,.16)"/>' +
  '<g class="legL"><rect x="28.5" y="76" width="5.5" height="14" rx="2.75" fill="var(--_b)"/><ellipse cx="30" cy="92" rx="6.8" ry="3.8" fill="var(--_shoe)"/></g>' +
  '<g class="legR"><rect x="46" y="76" width="5.5" height="14" rx="2.75" fill="var(--_b)"/><ellipse cx="50" cy="92" rx="6.8" ry="3.8" fill="var(--_shoe)"/></g>' +
  '<g class="armL"><path d="M17 58 Q9 62 8 70" stroke="var(--_b)" stroke-width="5" fill="none" stroke-linecap="round"/><circle cx="8" cy="71" r="3.7" fill="var(--_b)"/></g>' +
  '<g class="body"><path d="M40 4 C47 18 68 33 68 56 A28 28 0 0 1 12 56 C12 33 33 18 40 4 Z" fill="url(#g)"/>' +
  '<ellipse cx="28" cy="35" rx="4.5" ry="8.5" fill="#fff" opacity=".38" transform="rotate(28 28 35)"/><circle cx="25" cy="25" r="1.8" fill="#fff" opacity=".45"/></g>' +
  '<g class="eyes"><ellipse cx="31" cy="50" rx="7" ry="8" fill="#fff"/><ellipse cx="49" cy="50" rx="7" ry="8" fill="#fff"/>' +
  '<g class="pupils"><circle cx="32" cy="51" r="4.1" fill="#1F1B3A"/><circle cx="50" cy="51" r="4.1" fill="#1F1B3A"/>' +
  '<circle cx="33.6" cy="49.2" r="1.5" fill="#fff"/><circle cx="51.6" cy="49.2" r="1.5" fill="#fff"/></g></g>' +
  '<ellipse cx="22.5" cy="61" rx="4.6" ry="2.8" fill="#FF8FB1" opacity=".8"/><ellipse cx="57.5" cy="61" rx="4.6" ry="2.8" fill="#FF8FB1" opacity=".8"/>' +
  '<path class="smile" d="M35 63 Q40 68.5 45 63" stroke="#1F1B3A" stroke-width="2.4" fill="none" stroke-linecap="round"/>' +
  '<ellipse class="mouth" cx="40" cy="65.2" rx="3.7" ry="3.3" fill="#3A1830"/>' +
  '<g class="armR"><path d="M63 58 Q71 55 73 48" stroke="var(--_b)" stroke-width="5" fill="none" stroke-linecap="round"/>' +
  '<g transform="rotate(-24 74.5 40)"><rect x="72" y="28" width="5" height="16" rx="1" fill="#FFD84D"/><rect x="72" y="25.5" width="5" height="4" rx="1.3" fill="#FF8FB1"/>' +
  '<rect x="72" y="29.2" width="5" height="1.4" fill="#C9C3D9"/><path d="M72 44 L74.5 49.5 L77 44 Z" fill="#F2C9A0"/><path d="M73.7 47.6 L74.5 49.5 L75.3 47.6 Z" fill="#1F1B3A"/></g>' +
  '<circle cx="73" cy="47.5" r="3.7" fill="var(--_b)"/></g>' +
  "</svg>";

const CSS = `
:host {
  --_a: var(--mascot-a, #8E7CF2);
  --_b: var(--mascot-b, #4B2EBF);
  --_shoe: var(--mascot-shoe, #2B2740);
  --_accent: var(--mascot-accent, var(--tim, #5B4CC4));
  --_bubble: var(--mascot-bubble, #5B4CC4);
  --_ink: var(--mascot-ink, var(--ink, #1F1B3A));
  --_paper: var(--mascot-paper, var(--paper, #FFFFFF));
  --_rule: var(--mascot-rule, var(--rule, #DDD8F0));
  --_soft: var(--mascot-soft, #F3F0FF);
  --_h: var(--mascot-size, 64px);
  position: fixed; inset: 0; display: block; z-index: var(--mascot-z, 9995);
  pointer-events: none; contain: layout style;
  font: 500 15px/1.45 var(--font-ui, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif);
  color: var(--_ink);
}
@media (prefers-color-scheme: dark) {
  :host(:not([theme="light"])) {
    --_a: var(--mascot-a, #B3A6FF); --_b: var(--mascot-b, #6C57E6); --_shoe: var(--mascot-shoe, #0F0D1F);
    --_ink: var(--mascot-ink, var(--ink, #F1EEFF)); --_paper: var(--mascot-paper, var(--paper, #1D1A33));
    --_rule: var(--mascot-rule, var(--rule, #3A3560)); --_soft: var(--mascot-soft, #2A2548);
  }
}
:host([theme="dark"]) {
  --_a: var(--mascot-a, #B3A6FF); --_b: var(--mascot-b, #6C57E6); --_shoe: var(--mascot-shoe, #0F0D1F);
  --_ink: var(--mascot-ink, var(--ink, #F1EEFF)); --_paper: var(--mascot-paper, var(--paper, #1D1A33));
  --_rule: var(--mascot-rule, var(--rule, #3A3560)); --_soft: var(--mascot-soft, #2A2548);
}
:host([hidden]) { display: none; }
* { box-sizing: border-box; }

.m {
  position: absolute; left: 0; top: 0; width: calc(var(--_h) * .8); height: var(--_h);
  padding: 0; margin: 0; border: 0; background: none; cursor: grab; pointer-events: auto;
  touch-action: none; user-select: none; -webkit-user-select: none; -webkit-tap-highlight-color: transparent;
}
.m:focus-visible { outline: 3px solid var(--_accent); outline-offset: 6px; border-radius: 40%; }
.m.dragging { cursor: grabbing; }
.flip { display: block; width: 100%; height: 100%; }
.m.left .flip { transform: scaleX(-1); }
.fig { display: block; width: 100%; height: 100%; transform-origin: 50% 92%; transition: transform .2s cubic-bezier(.2,.8,.2,1); }
.svg { display: block; width: 100%; height: 100%; overflow: visible; filter: drop-shadow(0 4px 5px rgba(0,0,0,.16)); transition: filter .2s; }
.svg g { transform-box: fill-box; }

.m:not(.dragging):not(.running):not(.hopping) .fig { animation: bob 3.2s ease-in-out infinite; }
@keyframes bob { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-4px) scaleY(1.02); } }
.eyes { transform-origin: 50% 55%; transition: transform .07s; }
.m.blink .eyes { transform: scaleY(.12); }
.pupils { transition: transform .45s cubic-bezier(.2,.8,.2,1); }
.m.thinking .pupils { transform: translate(1px, -3px); }
.legL, .legR { transform-origin: 50% 0%; }
.armR { transform-origin: 0% 95%; transition: transform .25s cubic-bezier(.2,.8,.2,1); }
.armL { transform-origin: 100% 10%; transition: transform .25s; }
.shadow { transform-origin: 50% 50%; transition: transform .2s, opacity .2s; }
.m.waving .armR, .m.thinking .armR { animation: wave .45s ease-in-out infinite alternate; }
.m.thinking .armR { animation-duration: .22s; }
@keyframes wave { from { transform: rotate(-38deg); } to { transform: rotate(14deg); } }
.m.pointing .armR { transform: rotate(-32deg); }
.m.pointing .armL { transform: rotate(-12deg); }
.mouth { transform-origin: 50% 50%; opacity: 0; }
.m.talking .mouth { opacity: 1; animation: talk .17s ease-in-out infinite alternate; }
.m.talking .smile { opacity: 0; }
@keyframes talk { from { transform: scaleY(.3); } to { transform: scaleY(1.05); } }
.m.dragging .fig { transform: scale(1.14,1.06) rotate(-5deg); }
.m.dragging .svg { filter: drop-shadow(0 16px 14px rgba(0,0,0,.28)); }
.m.dragging .shadow { transform: scale(.6); opacity: .3; }
.m.dragging .legL { animation: dangle .6s ease-in-out infinite alternate; }
.m.dragging .legR { animation: dangle .6s ease-in-out infinite alternate-reverse; }
.m.dragging .armL, .m.dragging .armR { transform: rotate(-24deg); }
@keyframes dangle { from { transform: rotate(14deg); } to { transform: rotate(-10deg); } }
.m.running .fig { transform: rotate(9deg) translateY(-2px); }
.m.running .legL { animation: step .2s linear infinite alternate; }
.m.running .legR { animation: step .2s linear infinite alternate-reverse; }
.m.running .armL { animation: swing .2s linear infinite alternate; }
@keyframes step { from { transform: rotate(30deg); } to { transform: rotate(-30deg); } }
@keyframes swing { from { transform: rotate(-30deg); } to { transform: rotate(25deg); } }

/* soft highlight of the explained area; never intercepts pointers */
.hl {
  position: absolute; pointer-events: none; border-radius: 16px;
  border: 2px solid var(--_accent);
  background: color-mix(in srgb, var(--_accent) 10%, transparent);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--_accent) 18%, transparent);
  animation: fade .25s ease-out both;
}
.hl.live { transition: left .1s, top .1s, width .1s, height .1s; border-style: dashed; }
@keyframes fade { from { opacity: 0; } to { opacity: 1; } }

/* first-visit tour: the page dims around the part being explained, and a clear layer takes every tap and scroll
   so the highlight never drifts; the only way on is the bubble's button */
.hl.dim { border: 0; background: none; box-shadow: 0 0 0 200vmax rgba(18, 14, 38, .55); border-radius: 18px; }
.catch { position: absolute; inset: 0; pointer-events: auto; touch-action: none; overscroll-behavior: contain; }
.bubble .tt { font-weight: 700; font-size: 1.04em; }
.bubble .n { margin-left: 8px; font-size: .8em; font-weight: 600; opacity: .72; font-variant-numeric: tabular-nums; }
.acts { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.skip {
  min-height: 36px; padding: 0 8px; border: 0; background: none; color: inherit; cursor: pointer; opacity: .85;
  font: 600 13px/1 inherit; font-family: inherit; text-decoration: underline; text-underline-offset: 3px;
}
.skip:hover { opacity: 1; }
.bubble.nudge { animation: nudge .42s ease-in-out; }
@keyframes nudge { 20% { transform: translateX(-6px); } 40% { transform: translateX(6px); } 60% { transform: translateX(-4px); } 80% { transform: translateX(3px); } }

/* floating surfaces: guide bubble and chat window */
.f {
  position: absolute; pointer-events: auto; border-radius: 18px;
  width: max-content; max-width: min(320px, calc(100% - 24px));
  animation: pop .24s cubic-bezier(.2,.9,.3,1.3) both;
}
.f::after {
  content: ""; position: absolute; width: 12px; height: 12px; background: var(--_bg);
  border: 1px solid var(--_bd); transform: rotate(45deg);
}
.f[data-side="above"]::after { bottom: -7px; left: calc(var(--ax) - 6px); border-width: 0 1px 1px 0; }
.f[data-side="below"]::after { top: -7px; left: calc(var(--ax) - 6px); border-width: 1px 0 0 1px; }
.f[data-side="left"]::after { right: -7px; top: calc(var(--ax) - 6px); border-width: 1px 1px 0 0; }
.f[data-side="right"]::after { left: -7px; top: calc(var(--ax) - 6px); border-width: 0 0 1px 1px; }
@keyframes pop { from { transform: scale(.9) translateY(6px); opacity: 0; } to { transform: none; opacity: 1; } }

.bubble { --_bg: var(--_bubble); --_bd: var(--_bubble); background: var(--_bubble); color: #fff; padding: 14px 16px; display: grid; gap: 10px;
  box-shadow: 0 12px 28px -14px rgba(0,0,0,.5); }
.bubble p { margin: 0; }
.bubble .say { font-weight: 600; }
.ok, .chip {
  min-height: 36px; padding: 0 14px; border: 0; border-radius: 999px; cursor: pointer;
  background: #fff; color: #3A2299; font: 600 13.5px/1 inherit; font-family: inherit;
}
.ok { justify-self: end; font-weight: 700; }
.ok:hover { background: #EEEAFD; }
.bubble button:focus-visible { outline: 3px solid #fff; outline-offset: 2px; }

.chat {
  --_bg: var(--_paper); --_bd: var(--_rule);
  width: min(340px, calc(100% - 24px)); max-width: none;
  background: var(--_paper); color: var(--_ink); border: 1px solid var(--_rule);
  box-shadow: 0 18px 40px -18px rgba(20,12,60,.45);
  display: grid; grid-template-rows: auto minmax(0,1fr) auto auto; max-height: min(70%, 480px); overflow: hidden;
}
.head { display: flex; align-items: center; gap: 8px; padding: 12px 8px 8px 16px; }
.head h2 { margin: 0; flex: 1; font-size: 15px; font-weight: 700; line-height: 1.3; }
.x { width: 32px; height: 32px; border-radius: 50%; border: 0; background: transparent; color: inherit; cursor: pointer; font-size: 20px; line-height: 1; }
.x:hover { background: var(--_soft); }
.log { overflow: auto; padding: 4px 16px 8px; display: grid; gap: 8px; align-content: start; min-height: 0; overscroll-behavior: contain; }
.log p { margin: 0; padding: 8px 12px; border-radius: 14px; background: var(--_soft); white-space: pre-wrap; overflow-wrap: anywhere; }
.log p.me { justify-self: end; background: var(--_bubble); color: #fff; }
.log p.tip { background: none; padding: 0; font-size: 13px; opacity: .75; }
.log .dots { display: flex; gap: 4px; padding: 12px; width: max-content; }
.dots i { width: 7px; height: 7px; border-radius: 50%; background: var(--_accent); animation: dot 1s infinite ease-in-out; }
.dots i:nth-child(2) { animation-delay: .15s; } .dots i:nth-child(3) { animation-delay: .3s; }
@keyframes dot { 0%,80%,100% { transform: translateY(0); opacity: .45; } 40% { transform: translateY(-4px); opacity: 1; } }
.show { padding: 0 16px 8px; display: grid; gap: 6px; }
.show[hidden] { display: none; }
.show b { font-size: 12.5px; font-weight: 700; }
.show span { font-size: 12.5px; opacity: .75; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chat .chip { background: var(--_soft); color: var(--_ink); border: 1px solid var(--_rule); min-height: 34px; }
.chat .chip:hover { border-color: var(--_accent); }
.chat .chip.replay { font-weight: 700; border-color: var(--_accent); }
.form { display: flex; gap: 8px; padding: 8px 12px 12px; border-top: 1px solid var(--_rule); }
.form input {
  flex: 1; min-width: 0; height: 40px; padding: 0 12px; border-radius: 12px; border: 1px solid var(--_rule);
  background: var(--_paper); color: var(--_ink); font: inherit; font-size: 16px;
}
.form input:focus-visible { outline: 2px solid var(--_accent); outline-offset: 1px; }
.form button {
  height: 40px; padding: 0 14px; border: 0; border-radius: 12px; cursor: pointer;
  background: var(--_bubble); color: #fff; font: inherit; font-weight: 700;
}
.form button:disabled, .form input:disabled { opacity: .55; cursor: default; }
.chat button:focus-visible { outline: 2px solid var(--_accent); outline-offset: 2px; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
  .f, .hl { animation: fade .2s both !important; }
  .bubble.nudge { animation: flash .6s ease-out !important; }
}
@keyframes flash { from { box-shadow: 0 0 0 4px #FFD84D; } }
:host([motion="reduce"]) *, :host([motion="reduce"]) *::before, :host([motion="reduce"]) *::after { animation: none !important; transition: none !important; }
:host([motion="reduce"]) .f, :host([motion="reduce"]) .hl { animation: fade .2s both !important; }
`;

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
// never hang on an animation: settle by timer too
const settle = async (anim, ms) => {
  await Promise.race([anim.finished.catch(() => {}), wait(ms)]);
  try { anim.cancel(); } catch (e) { /* already finished */ }
};
const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), Math.max(lo, hi));
const humanize = (k) => { const s = String(k).replace(/[-_.]+/g, " ").trim(); return s.charAt(0).toUpperCase() + s.slice(1); };

const Base = typeof HTMLElement === "undefined" ? class {} : HTMLElement;

export class MentorMascot extends Base {
  static get observedAttributes() { return ["lang"]; }

  constructor() {
    super();
    this._ask = null;
    this._guides = {};
    this._avoid = DEFAULT_AVOID;
    this._lang = null;
    this._pos = { x: 0, y: 0 };
    this._drag = null;
    this._busy = false;
    this._mode = null; // null | "chat" | "bubble"
    this._float = null;
    this._timers = new Set();
    this._ready = false;
    this._replay = null;
    this._tour = null;
  }

  // ------------------------------------------------------------ public API
  get ask() { return this._ask; }
  set ask(fn) { this._ask = typeof fn === "function" ? fn : null; }
  get guides() { return this._guides; }
  set guides(map) { this._guides = map && typeof map === "object" ? map : {}; if (this._mode === "chat") this._fillAreas(); }
  /** CSS selector of interactive elements Mực avoids when picking a spot. */
  get avoid() { return this._avoid; }
  set avoid(sel) { this._avoid = typeof sel === "string" && sel ? sel : DEFAULT_AVOID; }
  get lang() {
    const l = this._lang || this.getAttribute("lang") || (typeof document !== "undefined" && document.documentElement.lang) || "vi";
    return String(l).toLowerCase().startsWith("en") ? "en" : "vi";
  }
  set lang(v) { this.setAttribute("lang", v === "en" ? "en" : "vi"); }

  openChat() { if (this._ready) this._openChat(false); }
  closeChat() { if (this._mode === "chat") this._closeFloat(); }
  /** Explain the first visible element carrying data-guide="<key>". Resolves when Mực is back to idle. */
  guide(key) {
    if (!this._ready) return Promise.resolve();
    const el = this._visibleAreas().find((a) => a.key === key);
    return this._explain(el ? el.el : null, true);
  }
  /** Show a short message in a speech bubble (for hosts: greetings, tips). */
  say(text, ms = 6000) {
    if (!this._ready) return;
    this._closeFloat();
    this._showBubble(this._p(String(text), "say"), null);
    this._talk(text);
    this._armDismiss(ms);
  }
  /** Re-check the current spot (call after route changes). Moves only if Mực sits on something interactive. */
  relocate() { this._checkSpot(); }
  /** Host callback behind the chat's "Show me this page again" chip; the chip only shows while it is set. */
  get replay() { return this._replay; }
  set replay(fn) { this._replay = typeof fn === "function" ? fn : null; if (this._mode === "chat") this._fillAreas(); }
  /**
   * Walk through parts of the page one at a time (a screen's first visit). A step is { key } (a data-guide key, its text
   * from `guides`), optionally with { title } and/or { text } ({ vi, en } each); a step whose key is not on screen is left
   * out. While it runs the page cannot scroll and taps outside only nudge the bubble: the person moves on with
   * "Got it, next" or leaves with Skip / Escape. Resolves "done", "skipped", or "none" when there was nothing to show
   * or Mực was busy.
   */
  tour(steps) {
    if (!this._ready || this._tour || this._busy || this._drag) return Promise.resolve("none");
    const areas = Array.from(document.querySelectorAll("[data-guide]"));
    const list = [];
    for (const s of Array.isArray(steps) ? steps : []) {
      if (!s) continue;
      let el = null;
      if (s.key) {
        el = areas.find((n) => n.getAttribute("data-guide") === s.key && this._visible(n)) || null;
        if (!el || list.some((o) => o.el && (o.el.contains(el) || el.contains(o.el)))) continue;
      }
      const text = s.text || (s.key && this._guides[s.key]);
      if (!text || !(text.vi || text.en)) continue;
      list.push({ el, text, title: s.title || null });
    }
    if (!list.length) return Promise.resolve("none");
    this._closeFloat();
    return new Promise((resolve) => {
      const a = document.activeElement;
      this._tour = { steps: list, i: 0, y: window.scrollY, resolve, focus: a && a !== document.body ? a : null, token: 0 };
      this._busy = true;
      this._lockPage(true);
      const c = document.createElement("div");
      c.className = "catch";
      c.addEventListener("pointerdown", (e) => { e.preventDefault(); this._nudge(); });
      c.addEventListener("wheel", (e) => { e.preventDefault(); this._nudge(); }, { passive: false });
      c.addEventListener("touchmove", (e) => e.preventDefault(), { passive: false });
      this.shadowRoot.insertBefore(c, this._m);
      this._catch = c;
      this._tourStep();
    });
  }
  /** End a running tour now (e.g. the host navigated away). */
  stopTour() { if (this._tour) this._endTour("skipped"); }

  // ------------------------------------------------------------ lifecycle
  connectedCallback() {
    for (const p of ["ask", "guides", "avoid", "lang", "replay"]) {
      if (Object.prototype.hasOwnProperty.call(this, p)) { const v = this[p]; delete this[p]; this[p] = v; }
    }
    if (!this.shadowRoot) {
      const root = this.attachShadow({ mode: "open" });
      const style = document.createElement("style");
      style.textContent = CSS;
      root.appendChild(style);
    }
    if (this._ready) return;
    this._ready = true;
    this._rm = window.matchMedia("(prefers-reduced-motion: reduce)");
    const root = this.shadowRoot;
    const m = (this._m = document.createElement("button"));
    m.type = "button";
    m.className = "m";
    m.setAttribute("aria-haspopup", "dialog");
    m.setAttribute("aria-expanded", "false");
    m.innerHTML = '<span class="flip"><span class="fig">' + SVG + "</span></span>";
    root.appendChild(m);
    this._syncLabel();

    m.addEventListener("pointerdown", (e) => this._onDown(e));
    m.addEventListener("pointermove", (e) => this._onMove(e));
    m.addEventListener("pointerup", (e) => this._onUp(e));
    m.addEventListener("pointercancel", () => this._onCancel());
    m.addEventListener("lostpointercapture", (e) => { if (this._drag && this._drag.on) this._onUp(e); });
    m.addEventListener("click", (e) => e.preventDefault());
    m.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this._toggleChat(true); }
    });

    this._onKey = (e) => {
      if (this._tour) {
        if (e.key === "Escape") { e.preventDefault(); this._endTour("skipped"); }
        else if (e.key === "Tab" && this._float) {
          // keep focus on the bubble's buttons: the page behind is out of reach until the tour ends
          const btns = Array.from(this._float.querySelectorAll("button"));
          const i = btns.indexOf(this.shadowRoot.activeElement);
          e.preventDefault();
          btns[(i + (e.shiftKey ? -1 : 1) + btns.length) % btns.length].focus({ preventScroll: true });
        }
        return;
      }
      if (e.key !== "Escape" || !this._mode) return;
      const kb = this._mode === "chat" || this._keyboardGuide;
      this._closeFloat();
      if (kb) m.focus({ preventScroll: true });
    };
    this._onDocDown = (e) => {
      if (this._mode !== "bubble" || e.composedPath().includes(this)) return;
      this._closeFloat(); // does not swallow the tap: it still reaches the page
    };
    this._onResize = () => {
      this._place(...Object.values(this._clampPos(this._pos.x, this._pos.y)));
      if (this._tour) {
        // resized or turned mid-tour: lay the same step out again for the new size
        this._clear(this._redoT);
        this._redoT = this._later(() => { if (this._tour) { this._clearStep(); this._tourStep(); } }, 180);
        return;
      }
      if (this._explaining) this._closeFloat();
      else if (this._float) this._placeFloat();
      this._scheduleCheck();
    };
    this._onScroll = () => { if (!this._lockScroll) this._scheduleCheck(); };
    document.addEventListener("keydown", this._onKey);
    document.addEventListener("pointerdown", this._onDocDown, true);
    window.addEventListener("resize", this._onResize);
    window.addEventListener("scroll", this._onScroll, { passive: true, capture: true });
    this._mo = new MutationObserver(() => this._scheduleCheck());
    this._mo.observe(document.body, { childList: true, subtree: true });

    requestAnimationFrame(() => {
      const p = this._defaultSpot();
      this._place(p.x, p.y);
      m.animate([{ opacity: 0, transform: "translateY(16px) scale(.8)" }, { opacity: 1, transform: "none" }], { duration: this._rm.matches ? 1 : 420, easing: "cubic-bezier(.2,.9,.3,1.3)" });
      this._idleLoop();
    });
  }

  disconnectedCallback() {
    if (!this._ready) return;
    if (this._tour) this._endTour("skipped");
    this._ready = false;
    document.removeEventListener("keydown", this._onKey);
    document.removeEventListener("pointerdown", this._onDocDown, true);
    window.removeEventListener("resize", this._onResize);
    window.removeEventListener("scroll", this._onScroll, { capture: true });
    if (this._mo) this._mo.disconnect();
    this._timers.forEach((t) => clearTimeout(t));
    this._timers.clear();
    this._closeFloat();
    if (this._m) this._m.remove();
  }

  attributeChangedCallback(name) {
    if (name !== "lang" || !this._ready) return;
    this._syncLabel();
    if (this._tour && this._float) { const a = this._floatAvoid; this._float.remove(); this._float = null; this._showStep(a); }
    if (this._mode === "chat") this._renderChatStatic();
  }

  // ------------------------------------------------------------ helpers
  _t(k) { return STR[this.lang][k]; }
  _syncLabel() { this._m.setAttribute("aria-label", this._t("label")); }
  _later(fn, ms) { const t = setTimeout(() => { this._timers.delete(t); fn(); }, ms); this._timers.add(t); return t; }
  _clear(t) { if (t) { clearTimeout(t); this._timers.delete(t); } }
  _W() { return this.clientWidth || document.documentElement.clientWidth; }
  _H() { return this.clientHeight || window.innerHeight; }
  _size() { return { w: this._m.offsetWidth, h: this._m.offsetHeight }; }
  _place(x, y) { this._pos = { x, y }; this._m.style.left = Math.round(x) + "px"; this._m.style.top = Math.round(y) + "px"; }
  _clampPos(x, y) { const { w, h } = this._size(); return { x: clamp(x, 8, this._W() - w - 8), y: clamp(y, 8, this._H() - h - 8) }; }
  _rect() { const { w, h } = this._size(); const { x, y } = this._pos; return { left: x, top: y, right: x + w, bottom: y + h, width: w, height: h }; }
  _p(text, cls) { const p = document.createElement("p"); if (cls) p.className = cls; p.textContent = text; return p; }
  _visible(n) {
    if (!n || (n.checkVisibility && !n.checkVisibility({ checkVisibilityCSS: true }))) return false;
    const r = n.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  // ------------------------------------------------------------ free spots (avoid interactive elements)
  _avoidRects() {
    const out = [];
    let nodes = [];
    try { nodes = document.querySelectorAll(this._avoid); } catch (e) { nodes = []; }
    const W = this._W(), H = this._H();
    nodes.forEach((n) => {
      if (n === this || this.contains(n) || !this._visible(n)) return;
      const r = n.getBoundingClientRect();
      if (r.bottom < 0 || r.top > H || r.right < 0 || r.left > W) return;
      out.push(r);
    });
    return out;
  }
  _hit(a, b, pad) { return !(a.right + pad <= b.left || b.right + pad <= a.left || a.bottom + pad <= b.top || b.bottom + pad <= a.top); }
  _freeSpots(exclude) {
    const { w, h } = this._size(), mg = 12, W = this._W(), H = this._H();
    const av = this._avoidRects();
    if (exclude) av.push(exclude);
    const cands = [];
    const bottom = H - h - mg;
    for (let y = bottom; y >= mg; y -= 26) { cands.push({ x: W - w - mg, y }); cands.push({ x: mg, y }); }
    for (let x = mg; x <= W - w - mg; x += 34) cands.push({ x, y: bottom });
    return cands.filter((c) => {
      const r = { left: c.x, top: c.y, right: c.x + w, bottom: c.y + h };
      return !av.some((a) => this._hit(r, a, 6));
    });
  }
  _defaultSpot() {
    const free = this._freeSpots();
    const W = this._W(), H = this._H();
    if (!free.length) { const { w, h } = this._size(); return this._clampPos(W - w - 12, H - h - 12); }
    free.sort((a, b) => (W - a.x) + (H - a.y) - ((W - b.x) + (H - b.y)));
    return free[0];
  }
  _randomSpot(exclude) {
    const free = this._freeSpots(exclude).filter((c) => Math.hypot(c.x - this._pos.x, c.y - this._pos.y) > 110);
    return free.length ? free[Math.floor(Math.random() * free.length)] : this._defaultSpot();
  }
  _scheduleCheck() {
    this._clear(this._checkT);
    this._checkT = this._later(() => this._checkSpot(), 450);
  }
  _checkSpot() {
    if (!this._ready || this._busy || this._drag || this._mode) return;
    const r = this._rect();
    if (this._avoidRects().some((a) => this._hit(r, a, 4))) this._moveTo(this._defaultSpot(), "hop");
  }

  // ------------------------------------------------------------ motion
  async _moveTo(dest, mode) {
    const m = this._m;
    const from = { ...this._pos };
    const to = this._clampPos(dest.x, dest.y);
    const dx = to.x - from.x, dy = to.y - from.y, dist = Math.hypot(dx, dy);
    if (dist < 2) return;
    if (this._rm.matches || this.getAttribute("motion") === "reduce") {
      await settle(m.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 140, fill: "forwards" }), 180);
      this._place(to.x, to.y);
      await settle(m.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 160 }), 200);
      return;
    }
    if (Math.abs(dx) > 4) m.classList.toggle("left", dx < 0);
    const run = mode === "run";
    const duration = run ? Math.min(2000, Math.max(520, dist / 0.5)) : 440;
    const arc = run ? -Math.min(70, dist * 0.18) : -Math.min(46, 18 + dist * 0.08);
    m.classList.add(run ? "running" : "hopping");
    this._place(to.x, to.y);
    const a = m.animate(
      [
        { transform: `translate(${-dx}px, ${-dy}px)` },
        { transform: `translate(${-dx / 2}px, ${-dy / 2 + arc}px)`, offset: 0.5 },
        { transform: "translate(0, 0)" },
      ],
      { duration, easing: run ? "cubic-bezier(.35,.1,.3,1)" : "cubic-bezier(.3,.7,.4,1)" }
    );
    await settle(a, duration + 120);
    m.classList.remove("running", "hopping");
    m.querySelector(".fig").animate([{ transform: "scale(1.12,.86)" }, { transform: "scale(.96,1.05)" }, { transform: "none" }], { duration: 260, easing: "ease-out" });
  }
  _talk(text) {
    const m = this._m;
    m.classList.add("talking");
    this._clear(this._talkT);
    this._talkT = this._later(() => m.classList.remove("talking"), Math.min(4200, Math.max(1200, String(text).length * 45)));
  }
  _idleLoop() {
    const m = this._m;
    const blink = () => {
      m.classList.add("blink");
      this._later(() => m.classList.remove("blink"), 140);
      this._later(blink, 2600 + Math.random() * 3200);
    };
    const look = () => {
      const p = m.querySelector(".pupils");
      if (!this._busy && !this._drag && !this._mode) {
        p.style.transform = `translate(${(Math.random() * 3 - 1.5).toFixed(1)}px, ${(Math.random() * 2 - 1).toFixed(1)}px)`;
        this._later(() => { p.style.transform = ""; }, 1300);
      }
      this._later(look, 6000 + Math.random() * 5000);
    };
    this._later(blink, 1800);
    this._later(look, 4000);
  }

  // ------------------------------------------------------------ floating surfaces
  _closeFloat() {
    this._clear(this._dismissT);
    this._clear(this._talkT);
    const wasExplaining = this._explaining;
    if (this._float) { this._float.remove(); this._float = null; }
    this._mode = null;
    this._keyboardGuide = false;
    const m = this._m;
    if (m) {
      m.classList.remove("waving", "talking", "pointing", "thinking");
      m.setAttribute("aria-expanded", "false");
    }
    if (this._hl) { this._hl.remove(); this._hl = null; }
    if (wasExplaining) this._finishExplain();
  }
  _mount(node, mode, avoid) {
    if (this._float) { this._float.remove(); this._float = null; }
    this.shadowRoot.appendChild(node);
    this._float = node;
    this._floatAvoid = avoid || null;
    this._mode = mode;
    this._placeFloat();
  }
  _placeFloat() {
    const n = this._float;
    if (!n) return;
    const mg = 12, gap = 16, W = this._W(), H = this._H();
    const bw = n.offsetWidth, bh = n.offsetHeight;
    const a = this._rect(), cx = a.left + a.width / 2, cy = a.top + a.height / 2;
    const avoid = this._floatAvoid;
    const cX = (x) => clamp(x, mg, W - bw - mg), cY = (y) => clamp(y, mg, H - bh - mg);
    const opts = [
      { side: "above", x: cX(cx - bw * 0.7), y: a.top - bh - gap },
      { side: "below", x: cX(cx - bw * 0.7), y: a.bottom + gap },
      { side: "left", x: a.left - bw - gap, y: cY(cy - bh * 0.7) },
      { side: "right", x: a.right + gap, y: cY(cy - bh * 0.7) },
    ];
    if (n.classList.contains("chat")) { const o = opts.splice(2, 2); opts.push(...o); }
    const fits = (o) => o.x >= mg && o.y >= mg && o.x + bw <= W - mg && o.y + bh <= H - mg;
    const overlap = (o) => {
      if (!avoid) return 0;
      const w = Math.max(0, Math.min(o.x + bw, avoid.right) - Math.max(o.x, avoid.left));
      const h = Math.max(0, Math.min(o.y + bh, avoid.bottom) - Math.max(o.y, avoid.top));
      return w * h;
    };
    let best = null;
    opts.filter(fits).forEach((o) => { const s = overlap(o); if (!best || s < best.s) best = { ...o, s }; });
    if (!best) {
      const above = a.top > H - a.bottom;
      best = above ? { side: "above", x: cX(cx - bw * 0.7), y: cY(a.top - bh - 6) } : { side: "below", x: cX(cx - bw * 0.7), y: cY(a.bottom + 6) };
    }
    n.style.left = best.x + "px";
    n.style.top = best.y + "px";
    n.dataset.side = best.side;
    const ax = best.side === "above" || best.side === "below" ? cx - best.x : cy - best.y;
    const len = best.side === "above" || best.side === "below" ? bw : bh;
    n.style.setProperty("--ax", clamp(ax, 20, len - 20) + "px");
  }
  _showBubble(content, avoid, withOk) {
    const b = document.createElement("div");
    b.className = "f bubble";
    b.setAttribute("role", "status");
    b.setAttribute("aria-label", this._t("says"));
    b.append(content);
    if (withOk) {
      const ok = document.createElement("button");
      ok.type = "button";
      ok.className = "ok";
      ok.textContent = this._t("gotIt");
      ok.addEventListener("click", () => { const kb = this._keyboardGuide; this._closeFloat(); if (kb) this._m.focus({ preventScroll: true }); });
      b.append(ok);
    }
    this._mount(b, "bubble", avoid);
    this._m.classList.add("waving");
    return b;
  }
  _armDismiss(ms) {
    this._clear(this._dismissT);
    this._dismissT = this._later(() => { if (this._mode === "bubble") this._closeFloat(); }, ms);
  }

  // ------------------------------------------------------------ chat
  _toggleChat(fromKeyboard) {
    if (this._mode === "chat") { this._closeFloat(); return; }
    this._openChat(fromKeyboard);
  }
  _openChat(fromKeyboard) {
    if (this._busy) return;
    this._closeFloat();
    const c = document.createElement("div");
    c.className = "f chat";
    c.setAttribute("role", "dialog");
    c.setAttribute("aria-labelledby", "ct");
    c.innerHTML =
      '<div class="head"><h2 id="ct"></h2><button type="button" class="x"></button></div>' +
      '<div class="log" aria-live="polite"></div>' +
      '<div class="show" hidden><b></b><span></span><div class="chips"></div></div>' +
      '<form class="form"><input type="text" autocomplete="off" enterkeyhint="send"><button type="submit"></button></form>';
    this._chat = c;
    c.querySelector(".x").addEventListener("click", () => { this._closeFloat(); this._m.focus({ preventScroll: true }); });
    c.querySelector("form").addEventListener("submit", (e) => { e.preventDefault(); this._submit(); });
    this._mount(c, "chat", null);
    this._renderChatStatic();
    this._log = c.querySelector(".log");
    this._log.append(this._p(this._t("tip"), "tip"));
    this._m.setAttribute("aria-expanded", "true");
    this._m.classList.add("waving");
    this._talk(this._t("title"));
    this._fillAreas();
    this._placeFloat();
    if (fromKeyboard || !window.matchMedia("(pointer: coarse)").matches) c.querySelector("input").focus({ preventScroll: true });
  }
  _renderChatStatic() {
    const c = this._chat;
    if (!c) return;
    c.querySelector("h2").textContent = this._t("title");
    const x = c.querySelector(".x");
    x.textContent = "×";
    x.setAttribute("aria-label", this._t("close"));
    const input = c.querySelector("input");
    input.placeholder = this._t("placeholder");
    input.setAttribute("aria-label", this._t("placeholder"));
    c.querySelector(".form button").textContent = this._t("send");
    const tip = c.querySelector(".tip");
    if (tip) tip.textContent = this._t("tip");
    this._fillAreas();
  }
  _visibleAreas() {
    const seen = new Set(), out = [];
    const H = this._H(), W = this._W();
    document.querySelectorAll("[data-guide]").forEach((el) => {
      const key = el.getAttribute("data-guide");
      if (!key || seen.has(key) || !this._guides[key] || !this._visible(el)) return;
      const r = el.getBoundingClientRect();
      if (r.bottom < 0 || r.top > H || r.right < 0 || r.left > W) return;
      seen.add(key);
      out.push({ key, el, label: el.getAttribute("data-guide-label") || humanize(key) });
    });
    return out.slice(0, 8);
  }
  _fillAreas() {
    const c = this._chat;
    if (!c || this._mode !== "chat") return;
    const box = c.querySelector(".show"), chips = box.querySelector(".chips");
    const areas = this._visibleAreas();
    box.hidden = areas.length === 0 && !this._replay;
    box.querySelector("b").textContent = this._t("show");
    box.querySelector("span").textContent = this._t("showHint");
    chips.replaceChildren();
    if (this._replay) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip replay";
      b.textContent = this._t("replay");
      b.addEventListener("click", () => { const fn = this._replay; this._closeFloat(); if (fn) fn(); });
      chips.append(b);
    }
    areas.forEach((a) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = a.label;
      b.addEventListener("click", () => { this._closeFloat(); this._explain(a.el, true); });
      chips.append(b);
    });
    this._placeFloat();
  }
  async _submit() {
    const c = this._chat;
    if (!c || this._asking) return;
    const input = c.querySelector("input");
    const q = input.value.trim();
    if (!q) return;
    input.value = "";
    const lang = this.lang;
    this._log.append(this._p(q, "me"));
    this.dispatchEvent(new CustomEvent("mascot-ask", { detail: { question: q, lang }, bubbles: true, composed: true }));
    this._asking = true;
    input.disabled = true;
    c.querySelector(".form button").disabled = true;
    const dots = document.createElement("div");
    dots.className = "dots";
    dots.setAttribute("role", "status");
    dots.innerHTML = '<span class="sr"></span><i></i><i></i><i></i>';
    dots.firstChild.textContent = this._t("thinking");
    this._log.append(dots);
    this._m.classList.add("thinking");
    this._scrollLog();
    let answer;
    try {
      if (!this._ask) answer = this._t("noAsk");
      else {
        answer = await Promise.race([Promise.resolve(this._ask(q, lang)), wait(45000).then(() => { throw new Error("timeout"); })]);
        answer = String(answer == null ? "" : answer).trim() || this._t("failed");
      }
    } catch (e) {
      answer = this._t("failed");
    }
    this._asking = false;
    dots.remove();
    if (this._chat !== c) return; // closed while waiting
    this._m.classList.remove("thinking");
    this._log.append(this._p(answer, "bot"));
    input.disabled = false;
    c.querySelector(".form button").disabled = false;
    this._talk(answer);
    this._scrollLog();
    this._placeFloat();
    if (!window.matchMedia("(pointer: coarse)").matches) input.focus({ preventScroll: true });
  }
  _scrollLog() { this._log.scrollTop = this._log.scrollHeight; this._placeFloat(); }

  // ------------------------------------------------------------ drag and drop
  _under(x, y) {
    const root = this.getRootNode();
    const stack = (root.elementsFromPoint ? root : document).elementsFromPoint(x, y);
    return stack.find((n) => n !== this && n !== document.documentElement && n !== document.body) || null;
  }
  _areaAt(x, y) {
    const t = this._under(x, y);
    return t ? t.closest("[data-guide]") : null;
  }
  _setHint(el) {
    if (!el) { if (this._hl) { this._hl.remove(); this._hl = null; } return; }
    if (!this._hl) {
      this._hl = document.createElement("div");
      this._hl.className = "hl live";
      this.shadowRoot.insertBefore(this._hl, this._m);
    }
    this._setBox(this._hl, this._clip(el.getBoundingClientRect(), 6));
  }
  _setBox(n, r) { Object.assign(n.style, { left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px" }); }
  _clip(r, pad) {
    const W = this._W(), H = this._H();
    const left = Math.max(4, r.left - pad), top = Math.max(4, r.top - pad);
    const right = Math.min(W - 4, r.right + pad), bottom = Math.min(H - 4, r.bottom + pad);
    return { left, top, right, bottom, width: right - left, height: bottom - top };
  }
  _beginDrag() {
    const d = this._drag;
    if (!d || d.on) return;
    d.on = true;
    this._clear(d.hold);
    this._closeFloat();
    this._m.classList.add("dragging");
  }
  _onDown(e) {
    if (e.button !== 0 || this._busy) return;
    e.preventDefault();
    this._drag = { sx: e.clientX, sy: e.clientY, t: performance.now(), ox: e.clientX - this._pos.x, oy: e.clientY - this._pos.y, on: false, moved: 0, id: e.pointerId };
    try { this._m.setPointerCapture(e.pointerId); } catch (err) { /* synthetic pointer */ }
    this._drag.hold = this._later(() => this._beginDrag(), 250);
  }
  _onMove(e) {
    const d = this._drag;
    if (!d) return;
    d.moved = Math.max(d.moved, Math.hypot(e.clientX - d.sx, e.clientY - d.sy));
    if (!d.on && d.moved > 8) this._beginDrag();
    if (!d.on) return;
    const p = this._clampPos(e.clientX - d.ox, e.clientY - d.oy);
    this._place(p.x, p.y);
    this._setHint(this._areaAt(e.clientX, e.clientY));
  }
  _onUp(e) {
    const d = this._drag;
    if (!d) return;
    this._drag = null;
    this._clear(d.hold);
    try { this._m.releasePointerCapture(d.id); } catch (err) { /* already released */ }
    if (d.on) {
      this._m.classList.remove("dragging");
      this._setHint(null);
      if (d.moved < 8) return; // held without moving: just put down
      this._explain(this._areaAt(e.clientX, e.clientY), false, { x: e.clientX, y: e.clientY });
      return;
    }
    if (performance.now() - d.t < 400 && d.moved < 8) this._toggleChat(false);
  }
  _onCancel() {
    const d = this._drag;
    if (!d) return;
    this._clear(d.hold);
    this._drag = null;
    this._m.classList.remove("dragging");
    this._setHint(null);
  }

  // ------------------------------------------------------------ explain an area
  _standBeside(r) {
    const { w, h } = this._size(), mg = 10, W = this._W(), H = this._H();
    const room = { right: W - r.right, left: r.left, below: H - r.bottom, above: r.top };
    const cy = clamp(r.top + r.height / 2 - h / 2, mg, H - h - mg);
    const cx = clamp(r.left + r.width / 2 - w / 2, mg, W - w - mg);
    for (const side of Object.keys(room).sort((a, b) => room[b] - room[a])) {
      if (side === "right" && room.right >= w + 2 * mg) return { x: r.right + mg, y: cy };
      if (side === "left" && room.left >= w + 2 * mg) return { x: r.left - w - mg, y: cy };
      if (side === "below" && room.below >= h + 2 * mg) return { x: cx, y: r.bottom + mg };
      if (side === "above" && room.above >= h + 2 * mg) return { x: cx, y: r.top - h - mg };
    }
    return this._clampPos(r.right - w - mg, r.bottom - h - mg); // huge target: stand inside its corner
  }

  async _explain(el, keyboard, dropPoint) {
    if (this._busy) return;
    this._busy = true;
    this._closeFloat();
    this._keyboardGuide = !!keyboard;
    const key = el && el.getAttribute("data-guide");
    const entry = key && this._guides[key];
    const text = entry && entry[this.lang];
    if (!el || !entry || !text) {
      // unknown area: stay where dropped, say so kindly
      this._explaining = true;
      this._endTarget = null;
      this._showBubble(this._p(this._t("unknown"), "say"), null, !!keyboard);
      this._talk(this._t("unknown"));
      this.dispatchEvent(new CustomEvent("mascot-guide-unknown", { detail: { key: key || null }, bubbles: true, composed: true }));
      this._armDismiss(5000);
      return;
    }
    this._explaining = true;
    this._lockScroll = true;
    let r = el.getBoundingClientRect();
    if (r.top < 8 || r.bottom > this._H()) {
      el.scrollIntoView({ block: "center", behavior: this._rm.matches ? "auto" : "smooth" });
      await wait(this._rm.matches ? 30 : 450);
      r = el.getBoundingClientRect();
    }
    this._lockScroll = false;
    if (!this._explaining) return;
    const vr = this._clip(r, 8);
    const hl = document.createElement("div");
    hl.className = "hl";
    this._setBox(hl, vr);
    this.shadowRoot.insertBefore(hl, this._m);
    if (this._hl) this._hl.remove();
    this._hl = hl;
    this._endTarget = vr;
    await this._moveTo(this._standBeside(vr), "hop");
    if (!this._explaining) return;
    const me = this._rect();
    this._m.classList.toggle("left", vr.left + vr.width / 2 < me.left + me.width / 2);
    this._m.classList.add("pointing");
    this._showBubble(this._p(text), vr, true);
    this._m.classList.remove("waving");
    this._m.classList.add("pointing");
    this._talk(text);
    this.dispatchEvent(new CustomEvent("mascot-guide", { detail: key, bubbles: true, composed: true }));
    if (keyboard) this._float.querySelector(".ok").focus({ preventScroll: true });
    else this._armDismiss(Math.max(6000, text.length * 55));
  }
  // ------------------------------------------------------------ tour (first visit of a screen)
  async _tourStep() {
    const t = this._tour;
    if (!t) return;
    const token = ++t.token;
    const live = () => this._tour === t && t.token === token;
    const s = t.steps[t.i];
    let vr = null;
    if (s.el) {
      let r = s.el.getBoundingClientRect();
      if (r.top < 8 || r.bottom > this._H()) {
        s.el.scrollIntoView({ block: "center", behavior: this._rm.matches ? "auto" : "smooth" }); // the lock stops people, not code
        await wait(this._rm.matches ? 30 : 450);
        if (!live()) return;
        r = s.el.getBoundingClientRect();
      }
      vr = this._clip(r, 8);
      const hl = document.createElement("div");
      hl.className = "hl dim";
      this._setBox(hl, vr);
      this.shadowRoot.insertBefore(hl, this._m);
      this._hl = hl;
      await this._moveTo(this._standBeside(vr), "hop");
      if (!live()) return;
      const me = this._rect();
      this._m.classList.toggle("left", vr.left + vr.width / 2 < me.left + me.width / 2);
      this._m.classList.add("pointing");
    } else {
      this._m.classList.add("waving"); // a step about Mực itself (the hello): wave where it stands
    }
    this._showStep(vr || this._rect());
  }
  _showStep(avoid) {
    const t = this._tour;
    const s = t.steps[t.i], n = t.steps.length, last = t.i >= n - 1, L = this.lang;
    const text = s.text[L] || s.text.vi || s.text.en;
    const b = document.createElement("div");
    b.className = "f bubble";
    b.setAttribute("role", "dialog");
    b.setAttribute("aria-label", this._t("says"));
    const title = s.title && (s.title[L] || s.title.vi);
    if (title || n > 1) {
      const h = this._p(title || "", "tt");
      if (n > 1) {
        const c = document.createElement("span");
        c.className = "n";
        c.setAttribute("aria-hidden", "true");
        c.textContent = `${t.i + 1}/${n}`;
        const sr = document.createElement("span");
        sr.className = "sr";
        sr.textContent = this._t("step").replace("{n}", t.i + 1).replace("{total}", n);
        h.append(c, sr);
      }
      b.append(h);
    }
    b.append(this._p(text));
    const ok = document.createElement("button");
    ok.type = "button";
    ok.className = "ok";
    ok.textContent = last ? this._t("gotIt") : this._t("next");
    ok.addEventListener("click", () => (last ? this._endTour("done") : this._nextStep()));
    if (last) b.append(ok);
    else {
      const acts = document.createElement("div");
      acts.className = "acts";
      const skip = document.createElement("button");
      skip.type = "button";
      skip.className = "skip";
      skip.textContent = this._t("skip");
      skip.addEventListener("click", () => this._endTour("skipped"));
      acts.append(skip, ok);
      b.append(acts);
    }
    this._mount(b, "bubble", avoid);
    this._talk(text);
    ok.focus({ preventScroll: true });
  }
  _nextStep() {
    const t = this._tour;
    if (!t) return;
    this._clearStep();
    do t.i++; while (t.i < t.steps.length && t.steps[t.i].el && !this._visible(t.steps[t.i].el));
    if (t.i >= t.steps.length) this._endTour("done");
    else this._tourStep();
  }
  _clearStep() {
    if (this._float) { this._float.remove(); this._float = null; }
    this._mode = null;
    if (this._hl) { this._hl.remove(); this._hl = null; }
    this._clear(this._talkT);
    this._m.classList.remove("waving", "talking", "pointing");
  }
  _nudge() {
    const b = this._float;
    if (!b) return;
    b.classList.remove("nudge");
    void b.offsetWidth;
    b.classList.add("nudge");
    const ok = b.querySelector(".ok");
    if (ok) ok.focus({ preventScroll: true });
  }
  // the page stays put during a tour so the highlight never drifts off its part
  _lockPage(on) {
    const s = document.documentElement.style;
    if (on) {
      this._saved = { o: s.overflow, g: s.scrollbarGutter };
      if (window.innerWidth > document.documentElement.clientWidth) s.scrollbarGutter = "stable"; // keep the bar's room
      s.overflow = "hidden";
    } else if (this._saved) {
      s.overflow = this._saved.o;
      s.scrollbarGutter = this._saved.g;
      this._saved = null;
    }
  }
  async _endTour(result) {
    const t = this._tour;
    if (!t) return;
    this._tour = null;
    t.token = -1;
    this._clear(this._redoT);
    this._clearStep();
    if (this._catch) { this._catch.remove(); this._catch = null; }
    this._lockPage(false);
    t.resolve(result);
    if (!this._ready) { this._busy = false; return; }
    if (Math.abs(window.scrollY - t.y) > 4) {
      // the tour scrolled to show its parts: put the page back where the person left it
      window.scrollTo({ top: t.y, behavior: this._rm.matches ? "auto" : "smooth" });
      await wait(this._rm.matches ? 30 : 420);
    }
    if (t.focus && document.contains(t.focus) && t.focus.focus) t.focus.focus({ preventScroll: true });
    if (this._ready) await this._moveTo(this._randomSpot(null), "run");
    this._busy = false;
  }

  async _finishExplain() {
    this._explaining = false;
    const avoid = this._endTarget;
    this._endTarget = null;
    await wait(this._rm.matches ? 0 : 160);
    if (!this._ready) return;
    await this._moveTo(this._randomSpot(avoid), "run");
    this._busy = false;
  }
}

/** Register the element (idempotent, no-op on the server). Returns the constructor or undefined. */
export function defineMentorMascot(tag = "mentor-mascot") {
  if (typeof window === "undefined" || !window.customElements) return undefined;
  const existing = window.customElements.get(tag);
  if (existing) return existing;
  window.customElements.define(tag, MentorMascot);
  return MentorMascot;
}

defineMentorMascot();
