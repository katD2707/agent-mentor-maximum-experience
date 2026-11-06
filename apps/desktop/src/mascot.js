// Copied from packages/mentor-mascot/mascot.js by scripts/sync-mascot.mjs. Do not edit here.
// <mentor-mascot>: the Mentor speech-bubble character. Framework-free custom element, no dependencies.
// The body is the brand tile (rounded square, one tight corner as the speech tail); the face lives on it.
// SSR-safe: importing on a server touches no DOM globals; define() is guarded.

const STATES = ['idle', 'listening', 'thinking', 'talking', 'happy', 'celebrate', 'sleepy', 'calm', 'wave'];
const ONE_SHOT = { celebrate: 1, wave: 1 };
const BLINKS = { idle: 1, listening: 1, thinking: 1, talking: 1, calm: 1 };
const EO = 'cubic-bezier(0.23, 1, 0.32, 1)';
const UP = 'cubic-bezier(0.2, 0.7, 0.3, 1)'; // leaving the ground: fast, then decelerating
const DOWN = 'cubic-bezier(0.6, 0, 0.8, 0.5)'; // falling: gravity accelerates

// Which drawn variant is visible in which state (variants cross-fade, so changes blend).
const SHOW = {
  eo: 'idle listening thinking talking calm wave', // open eyes
  eh: 'happy celebrate', // smiling eyes
  ec: 'sleepy', // closed eyes
  ms: 'idle listening', // small smile
  mb: 'happy celebrate wave', // open smile
  mtw: 'talking',
  md: 'thinking',
  mc: 'calm',
  mz: 'sleepy',
  spw: 'happy',
  zw: 'sleepy',
};
// Poses: transforms per state, reached with transitions (interruptible, never snapping).
const POSE = {
  listening: { tilt: 'rotate(-5deg)', face: 'translate(-1px,1px)', eye: 'scale(1.08)', bl: 'translateY(-1.6px)', br: 'translateY(-1.6px)' },
  thinking: { tilt: 'rotate(3deg)', face: 'translate(2px,-2.5px)', eye: 'scale(.94,.9)', bl: 'translateY(.4px)', br: 'translateY(-2.4px) rotate(-8deg)' },
  talking: { bl: 'translateY(-.6px)', br: 'translateY(-.6px)' },
  happy: { bl: 'translateY(-1.4px)', br: 'translateY(-1.4px)', cheeks: 'none' },
  celebrate: { bl: 'translateY(-2px)', br: 'translateY(-2px)', cheeks: 'none' },
  wave: { tilt: 'rotate(-3deg)', bl: 'translateY(-1.4px)', br: 'translateY(-1.4px)', cheeks: 'none' },
  calm: { face: 'translateY(1px)', eye: 'scale(.9,.74)', bl: 'translateY(.3px) rotate(-5deg)', br: 'translateY(.3px) rotate(5deg)' },
  sleepy: { tilt: 'rotate(-4deg)', face: 'translateY(2px)', bl: 'translateY(1.4px)', br: 'translateY(1.4px)' },
};
const CHEEK_OPACITY = { happy: 0.9, celebrate: 1, wave: 0.9 };
// Looping CSS animations run only in these states (paused, never removed, so leaving a state cannot snap).
const RUN = { '.mt': 'talking', '.dot': 'thinking', '.sp': 'happy', '.z': 'sleepy', '.deep': 'sleepy calm' };

const sel = (states, rule) => states.split(' ').map((s) => `[data-s=${s}] ${rule}`).join(',');

function buildCss() {
  let css = `
:host{--_body:var(--mascot-body,#2f6f62);--_ink:var(--mascot-ink,#fff);--_cheek:var(--mascot-cheek,#ff9f8c);
--_spark:var(--mascot-spark,#e4a11b);display:inline-block;inline-size:var(--mascot-size,40px);block-size:var(--mascot-size,40px);
vertical-align:middle;flex:none;position:relative;contain:layout style}
@media (prefers-color-scheme:dark){:host{--_body:var(--mascot-body,#6fbfab);--_ink:var(--mascot-ink,#0d1f1a);
--_cheek:var(--mascot-cheek,#ffb4a3);--_spark:var(--mascot-spark,#f0c060)}}
:host([theme=light]){--_body:var(--mascot-body,#2f6f62);--_ink:var(--mascot-ink,#fff);--_cheek:var(--mascot-cheek,#ff9f8c);
--_spark:var(--mascot-spark,#e4a11b)}
:host([theme=dark]){--_body:var(--mascot-body,#6fbfab);--_ink:var(--mascot-ink,#0d1f1a);--_cheek:var(--mascot-cheek,#ffb4a3);
--_spark:var(--mascot-spark,#f0c060)}
:host([hidden]){display:none}
svg{display:block;width:100%;height:100%;overflow:visible;--sw:2.8;--d:320ms;--ease:cubic-bezier(.45,0,.25,1)}
svg[data-sm]{--sw:4.4}
*{transform-box:fill-box;transform-origin:center}
.hop,.breath,.deep,.tilt{transform-box:view-box;transform-origin:32px 62px}
.flip,.face{transform-box:view-box;transform-origin:32px 32px}
.hand{transform-box:view-box;transform-origin:11px 30px;opacity:0;transform:translate(8px,5px)}
[data-tail=left] .flip{transform:scaleX(-1)}
.body,.hand{fill:var(--_body)}
.eo,.mb,.mt,.dot,.mz{fill:var(--_ink)}
.st{fill:none;stroke:var(--_ink);stroke-width:var(--sw);stroke-linecap:round;stroke-linejoin:round}
.brows .st{stroke-width:calc(var(--sw) * .85)}
.cheeks{fill:var(--_cheek);opacity:0;transform:scale(.7)}
.sp{fill:var(--_spark);animation:twinkle 2.4s ease-in-out infinite paused}
.sp2{animation-delay:-.8s}.sp3{animation-delay:-1.6s}
.bs{fill:var(--_spark);opacity:0}
.z{fill:none;stroke:var(--_body);stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round;opacity:0;
animation:zfloat 3.6s cubic-bezier(.3,0,.4,1) infinite paused}
.z2{animation-delay:-1.2s}.z3{animation-delay:-2.4s}
.p{transition:transform var(--d) var(--ease),opacity var(--d) ease}
.v{opacity:0;transition:opacity 180ms ease,transform 280ms ${EO}}
.mouth .v{transform:scale(.6)}
.breath{animation:breath 4.2s ease-in-out infinite alternate}
.deep{animation:deep 5.6s ease-in-out infinite alternate paused}
.mt{transform-origin:50% 0;animation:talk .96s linear infinite paused}
.dot{animation:dot 1.2s ease-in-out infinite paused}
.dot2{animation-delay:.16s}.dot3{animation-delay:.32s}
[data-s=calm]{--d:600ms}
[data-sm] .brows,[data-sm] .cheeks,[data-sm] .zw .z2,[data-sm] .zw .z3,[data-sm] .sp3,[data-sm] .bs4,[data-sm] .bs5{display:none}
[data-sm] .md{transform:scale(1.3)}
@keyframes breath{to{transform:scale(1.008,1.03)}}
@keyframes deep{to{transform:scale(1.012,1.045)}}
@keyframes talk{0%,100%{transform:scale(1,.22)}16%{transform:scale(1,.9)}30%{transform:scale(.92,.42)}
48%{transform:scale(1.04,1)}62%{transform:scale(.94,.3)}80%{transform:scale(1,.72)}}
@keyframes dot{0%,60%,100%{transform:none;opacity:.45}30%{transform:translateY(-2px);opacity:1}}
@keyframes dotfade{0%,60%,100%{opacity:.4}30%{opacity:1}}
@keyframes twinkle{0%,100%{transform:scale(.45) rotate(-20deg);opacity:0}45%{transform:scale(1) rotate(10deg);opacity:1}}
@keyframes zfloat{0%{transform:translate(0,5px) scale(.55);opacity:0}25%{opacity:1}
85%{opacity:0}100%{transform:translate(7px,-7px) scale(1.05);opacity:0}}
[data-rm] *{animation:none!important}
[data-rm] .dot{animation:dotfade 1.6s ease-in-out infinite!important}
[data-rm] .dot2{animation-delay:.2s!important}[data-rm] .dot3{animation-delay:.4s!important}
[data-rm] .z{opacity:1}[data-rm] .z2,[data-rm] .z3{display:none}
[data-rm] .p,[data-rm] .v{transition:opacity 200ms linear}
[data-rm] .bs{transition:opacity 200ms linear}[data-rm][data-s=celebrate] .bs{opacity:1}
[data-h] *,[data-h] .dot{animation-play-state:paused!important}
`;
  for (const [cls, states] of Object.entries(SHOW)) css += sel(states, `.${cls}`) + '{opacity:1;transform:none}\n';
  for (const [state, parts] of Object.entries(POSE)) {
    for (const [part, t] of Object.entries(parts)) css += `[data-s=${state}] .${part}{transform:${t}}\n`;
  }
  for (const [state, o] of Object.entries(CHEEK_OPACITY)) css += `[data-s=${state}] .cheeks{opacity:${o}}\n`;
  for (const [s, states] of Object.entries(RUN)) css += sel(states, s) + '{animation-play-state:running}\n';
  return css + 'svg[data-sm][data-s=thinking] .md{transform:scale(1.3)}';
}

// Geometry on a 64-unit grid: the body fills 2..62, corner radius 18 (brand tile ratio), tail corner 4.
const BODY = {
  right: 'M20 2H44A18 18 0 0 1 62 20V58A4 4 0 0 1 58 62H20A18 18 0 0 1 2 44V20A18 18 0 0 1 20 2Z',
  none: 'M20 2H44A18 18 0 0 1 62 20V44A18 18 0 0 1 44 62H20A18 18 0 0 1 2 44V20A18 18 0 0 1 20 2Z',
};
const STAR = 'M0-5Q.7-.7 5 0Q.7 .7 0 5Q-.7 .7-5 0Q-.7-.7 0-5Z';
const stars = (cls, list) =>
  list.map(([x, y, k], i) => `<g transform="translate(${x} ${y}) scale(${k})"><path class="${cls} ${cls}${i + 1}" d="${STAR}"/></g>`).join('');
const eye = (x, side) => `<g class="eye p ${side}"><g class="lid"><rect class="v eo" x="${x - 3.8}" y="21" width="7.6" height="12" rx="3.8"/></g>
<path class="v eh st" d="M${x - 4.2} 29Q${x} 22.6 ${x + 4.2} 29"/><path class="v ec st" d="M${x - 4.4} 27.5Q${x} 31 ${x + 4.4} 27.5"/></g>`;

const SVG = `<svg viewBox="0 0 64 64" aria-hidden="true" focusable="false" data-s="idle"><g class="scene">
<g class="zw v"><g transform="translate(51 2)">${[1, 2, 3].map((i) => `<path class="z z${i}" d="M-2.6-2.6H2.6L-2.6 2.6H2.6"/>`).join('')}</g></g>
<g class="hop"><g class="breath"><g class="deep"><g class="tilt p">
<g class="flip"><g class="hand"><rect x="-5" y="-8" width="10" height="16" rx="5" transform="translate(2.5 19.5) rotate(-38)"/></g><path class="body" d="${BODY.right}"/></g>
<g class="face p">
<g class="cheeks p"><ellipse cx="14.5" cy="38" rx="4.6" ry="2.7"/><ellipse cx="49.5" cy="38" rx="4.6" ry="2.7"/></g>
<g class="brows"><path class="brow st p bl" d="M19.6 16.4Q23 14.8 26.4 16.4"/><path class="brow st p br" d="M37.6 16.4Q41 14.8 44.4 16.4"/></g>
${eye(23, 'el')}${eye(41, 'er')}
<g class="mouth">
<path class="v ms st" d="M26.5 41.5Q32 46 37.5 41.5"/>
<path class="v mb" d="M24.5 39.6H39.5Q39.5 48.6 32 48.6Q24.5 48.6 24.5 39.6Z"/>
<g class="v mtw"><path class="mt" d="M26.6 40.6H37.4Q37.4 47.6 32 47.6Q26.6 47.6 26.6 40.6Z"/></g>
<g class="v md"><circle class="dot dot1" cx="25.6" cy="43" r="2.3"/><circle class="dot dot2" cx="32" cy="43" r="2.3"/><circle class="dot dot3" cx="38.4" cy="43" r="2.3"/></g>
<path class="v mc st" d="M27.6 42.4Q32 44.8 36.4 42.4"/>
<ellipse class="v mz" cx="32" cy="43.4" rx="2.4" ry="1.9"/>
</g></g></g></g></g></g>
<g class="spw v">${stars('sp', [
  [61, 1, 1.1],
  [2, 4, 0.75],
  [67, 24, 0.6],
])}</g>
<g class="burst">${stars('bs', [
  [62, 0, 1.2],
  [0, 2, 0.9],
  [69, 22, 0.75],
  [-5, 28, 0.65],
  [33, -4, 0.7],
])}</g>
</g></svg>`;

let sharedSheet = null;
const Base = typeof HTMLElement === 'undefined' ? class {} : HTMLElement;

export class MentorMascot extends Base {
  static get observedAttributes() {
    return ['state', 'size', 'label', 'tail', 'motion'];
  }

  constructor() {
    super();
    const root = this.attachShadow({ mode: 'open' });
    const css = buildCss();
    if (typeof CSSStyleSheet !== 'undefined' && 'replaceSync' in CSSStyleSheet.prototype && 'adoptedStyleSheets' in root) {
      if (!sharedSheet) {
        sharedSheet = new CSSStyleSheet();
        sharedSheet.replaceSync(css);
      }
      root.adoptedStyleSheets = [sharedSheet];
      root.innerHTML = SVG;
    } else {
      root.innerHTML = `<style>${css}</style>${SVG}`;
    }
    const q = (s) => root.querySelector(s);
    this._svg = q('svg');
    this._scene = q('.scene');
    this._hop = q('.hop');
    this._hand = q('.hand');
    this._body = q('.body');
    this._lids = root.querySelectorAll('.lid');
    this._bursts = root.querySelectorAll('.bs');
    this._cur = null;
    this._anims = new Set(); // WAAPI animations we own (paused when hidden)
    this._oneShot = null;
    this._blinkTimer = 0;
    this._visible = true;
    this._onVis = () => this._syncPause();
    this._onRm = () => this._syncMotion();
  }

  connectedCallback() {
    this._mq = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
    this._mq?.addEventListener?.('change', this._onRm);
    document.addEventListener('visibilitychange', this._onVis);
    if ('IntersectionObserver' in window) {
      this._io = new IntersectionObserver((es) => {
        this._visible = es[es.length - 1].isIntersecting;
        this._syncPause();
      });
      this._io.observe(this);
    }
    this._syncLabel();
    this._syncSize();
    this._syncTail();
    this._syncMotion();
    this._apply();
    this._syncPause();
  }

  disconnectedCallback() {
    this._mq?.removeEventListener?.('change', this._onRm);
    document.removeEventListener('visibilitychange', this._onVis);
    this._io?.disconnect();
    clearTimeout(this._blinkTimer);
  }

  attributeChangedCallback(name) {
    if (!this.isConnected) return;
    if (name === 'state') this._apply();
    else if (name === 'size') this._syncSize();
    else if (name === 'label') this._syncLabel();
    else if (name === 'tail') this._syncTail();
    else if (name === 'motion') this._syncMotion();
  }

  get state() {
    const s = this.getAttribute('state');
    return STATES.includes(s) ? s : 'idle';
  }
  set state(v) {
    this.setAttribute('state', v);
  }
  get size() {
    return Number(this.getAttribute('size')) || 40;
  }
  set size(v) {
    this.setAttribute('size', String(v));
  }

  /** Switch state. For one-shots (celebrate, wave) the promise resolves when the move ends. */
  play(state) {
    if (ONE_SHOT[this._cur] && state === this._cur) this._cur = null; // replay the same one-shot
    if (this.getAttribute('state') === state) this._apply();
    else this.setAttribute('state', state);
    // Listen after applying: an interrupted previous one-shot reports synchronously above.
    return ONE_SHOT[state] && this._oneShot
      ? new Promise((resolve) => this.addEventListener('mascot-done', (e) => resolve(e.detail), { once: true }))
      : Promise.resolve({ state, interrupted: false });
  }

  get _rm() {
    const m = this.getAttribute('motion');
    return m === 'reduce' || (m !== 'full' && !!this._mq?.matches);
  }

  _syncLabel() {
    const label = this.getAttribute('label');
    if (label === '') {
      this.setAttribute('aria-hidden', 'true');
      this.removeAttribute('role');
      this.removeAttribute('aria-label');
    } else {
      this.removeAttribute('aria-hidden');
      this.setAttribute('role', 'img');
      this.setAttribute('aria-label', label || 'Mentor');
    }
  }

  _syncSize() {
    const n = Number(this.getAttribute('size'));
    if (n > 0) this.style.setProperty('--mascot-size', `${n}px`);
    else this.style.removeProperty('--mascot-size');
    this._svg.toggleAttribute('data-sm', n > 0 && n < 32);
  }

  _syncTail() {
    const t = this.getAttribute('tail');
    this._body.setAttribute('d', t === 'none' ? BODY.none : BODY.right);
    this._svg.dataset.tail = t === 'left' ? 'left' : 'right';
  }

  _syncMotion() {
    this._svg.toggleAttribute('data-rm', this._rm);
    this._scheduleBlink();
  }

  _syncPause() {
    const hidden = document.hidden || !this._visible;
    this._svg.toggleAttribute('data-h', hidden);
    for (const a of this._anims) hidden ? a.pause() : a.play();
    this._scheduleBlink();
  }

  _anim(el, frames, opts) {
    const a = el.animate(frames, opts);
    this._anims.add(a);
    const drop = () => this._anims.delete(a);
    a.addEventListener('finish', drop);
    a.addEventListener('cancel', drop);
    if (this._svg.hasAttribute('data-h')) a.pause();
    return a;
  }

  // Cancel a running move and glide back to rest from wherever it is (no snap).
  _settle(el, extra) {
    const running = [...this._anims].filter((a) => a.effect?.target === el);
    if (!running.length) return;
    const cs = getComputedStyle(el);
    const from = { transform: cs.transform === 'none' ? 'none' : cs.transform };
    if (extra) from.opacity = cs.opacity;
    running.forEach((a) => a.cancel());
    if (this._rm) return;
    const to = { transform: el === this._hand ? 'translate(8px,5px)' : 'none' };
    if (extra) to.opacity = 0;
    this._anim(el, [from, to], { duration: 240, easing: EO });
  }

  _apply() {
    const s = this.state;
    if (s === this._cur) return;
    const prev = this._cur;
    this._cur = s;

    // A one-shot that is cut short still reports, so callers awaiting it are released.
    if (this._oneShot) {
      const { state, anim } = this._oneShot;
      this._oneShot = null;
      anim.cancel();
      this._emitDone(state, true);
    }
    this._settle(this._hop);
    this._settle(this._hand, true);
    this._bursts.forEach((b) => this._anims.forEach((a) => a.effect?.target === b && a.cancel()));

    if (this._rm && prev) {
      // Reduced motion: dip the whole figure, swap the pose while dim, fade back. Fades only.
      this._anim(this._scene, [{ opacity: 1 }, { opacity: 0.15, offset: 0.4 }, { opacity: 1 }], { duration: 320, easing: 'linear' });
      setTimeout(() => this._cur === s && (this._svg.dataset.s = s), 130);
    } else {
      this._svg.dataset.s = s;
    }
    this._enter(s, prev);
    this._scheduleBlink();
  }

  _enter(s) {
    const rm = this._rm;
    const f = (t, e) => (e ? { transform: t, easing: e } : { transform: t });
    if (s === 'happy' && !rm) {
      this._anim(this._hop, [f('none', EO), f('scale(1.05,.93)', UP), f('translateY(-5px) scale(.97,1.04)', DOWN), f('scale(1.03,.97)', EO), f('none')], {
        duration: 640,
      });
    }
    if (!ONE_SHOT[s]) return;
    let anim;
    if (rm) {
      anim = this._anim(this._scene, [{ opacity: 1 }, { opacity: 1 }], { duration: 1400 }); // a pausable clock
    } else if (s === 'celebrate') {
      anim = this._anim(
        this._hop,
        [
          { transform: 'none', easing: EO },
          { transform: 'scale(1.08,.9)', offset: 0.1, easing: UP },
          { transform: 'translateY(-9px) scale(.95,1.07)', offset: 0.25, easing: DOWN },
          { transform: 'scale(1.08,.92)', offset: 0.38, easing: UP },
          { transform: 'translateY(-5px) scale(.98,1.03)', offset: 0.5, easing: DOWN },
          { transform: 'scale(1.04,.96)', offset: 0.6, easing: EO },
          { transform: 'none', offset: 0.72 },
          { transform: 'none' },
        ],
        { duration: 1700 },
      );
      this._bursts.forEach((sp, i) =>
        this._anim(
          sp,
          [
            { transform: 'scale(.2) rotate(-60deg)', opacity: 0, easing: EO },
            { transform: 'scale(1.25) rotate(0deg)', opacity: 1, offset: 0.35 },
            { transform: 'scale(.9) rotate(25deg)', opacity: 1, offset: 0.7 },
            { transform: 'scale(.5) rotate(45deg)', opacity: 0 },
          ],
          { duration: 1100, delay: 200 + i * 60, fill: 'backwards' },
        ),
      );
    } else {
      anim = this._anim(
        this._hop,
        [
          { transform: 'none' },
          { transform: 'rotate(-4deg)', offset: 0.2 },
          { transform: 'rotate(2deg)', offset: 0.45 },
          { transform: 'rotate(-3deg)', offset: 0.65 },
          { transform: 'none', offset: 0.85 },
          { transform: 'none' },
        ],
        { duration: 1500, easing: 'ease-in-out' },
      );
      const w = (k, o, offset) => ({ transform: `translate(${8 * k}px,${5 * k}px) rotate(${o}deg)`, opacity: k ? 0 : 1, offset });
      this._anim(this._hand, [w(1, 0), w(0, -10, 0.14), w(0, 16, 0.3), w(0, -10, 0.46), w(0, 16, 0.62), w(0, -4, 0.76), w(1, 0, 0.92), w(1, 0)], {
        duration: 1500,
        easing: 'ease-in-out',
      });
    }
    this._oneShot = { state: s, anim };
    anim.addEventListener('finish', () => {
      if (this._oneShot?.anim !== anim) return;
      this._oneShot = null;
      this._emitDone(s, false);
      if (this._cur === s) this.setAttribute('state', 'idle');
    });
  }

  _emitDone(state, interrupted) {
    this.dispatchEvent(new CustomEvent('mascot-done', { detail: { state, interrupted }, bubbles: true, composed: true }));
  }

  _scheduleBlink() {
    clearTimeout(this._blinkTimer);
    if (!BLINKS[this._cur] || this._rm || this._svg.hasAttribute('data-h')) return;
    const calm = this._cur === 'calm';
    const wait = (calm ? 4500 : 2600) + Math.random() * (calm ? 4000 : 3800);
    this._blinkTimer = setTimeout(() => {
      if (!this.isConnected) return;
      const dur = calm ? 300 : 160;
      const blink = (delay) =>
        this._lids.forEach((l) =>
          this._anim(l, [{ transform: 'scaleY(1)' }, { transform: 'scaleY(.1)', offset: 0.45 }, { transform: 'scaleY(1)' }], {
            duration: dur,
            delay,
            easing: 'ease-in-out',
          }),
        );
      blink(0);
      if (!calm && Math.random() < 0.18) blink(dur + 90);
      this._scheduleBlink();
    }, wait);
  }
}

/** Register the element (idempotent, no-op on the server). Returns the constructor or undefined. */
export function defineMentorMascot(tag = 'mentor-mascot') {
  if (typeof window === 'undefined' || !window.customElements) return undefined;
  const existing = window.customElements.get(tag);
  if (existing) return existing;
  const ctor = tag === 'mentor-mascot' ? MentorMascot : class extends MentorMascot {};
  window.customElements.define(tag, ctor);
  return ctor;
}

defineMentorMascot();
