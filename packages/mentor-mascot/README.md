# mentor-mascot

`<mentor-mascot>` is the Mentor character: the green brand tile, the rounded square with one tight corner as a
speech tail, given a face. It is a framework-free custom element in a single ES module with inline SVG and CSS in
shadow DOM. It has no dependencies and makes no network calls. About 20 KB unminified.

Proposed name: **Mầm** ("sprout"). It is short, ungendered, green like the brand, and about growth, which is what
learning is. The product stays "Mentor"; the name is only for the character, if wanted.

## API

```html
<script type="module" src="./mascot.js"></script>
<mentor-mascot state="idle" size="56"></mentor-mascot>
```

| Attribute | Values | Default |
|---|---|---|
| `state` | `idle` `listening` `thinking` `talking` `happy` `celebrate` `sleepy` `calm` `wave` (unknown values fall back to `idle`) | `idle` |
| `size` | px, square. Below 32 the face drops brows, cheeks and extra sparkles, and strokes get thicker | 40 |
| `label` | accessible name (`role="img"`); `""` makes it decorative (`aria-hidden`) | `Mentor` |
| `tail` | `right`, `left` (mirrors the body, and the waving hand moves to the other side), `none` | `right` |
| `theme` | `light` / `dark` force a palette; omitted follows `prefers-color-scheme` | — |
| `motion` | `reduce` forces fade-only mode, `full` ignores the OS setting; omitted follows `prefers-reduced-motion` | — |

- Properties: `el.state` and `el.size` reflect to attributes.
- `el.play(state)` sets the state. For `celebrate` and `wave` it resolves with `{state, interrupted}` when the move
  ends. Playing the same one-shot again restarts it.
- Event `mascot-done`: `detail = {state, interrupted}`. It bubbles and is composed. It fires when `celebrate` or
  `wave` ends; the element then sets `state="idle"` itself. If another state cuts the move short, it fires with
  `interrupted: true` and the new state stays.
- Exports: `MentorMascot` (class) and `defineMentorMascot(tag?)`. Importing the module in a browser registers the
  element. On the server it does nothing and touches no DOM globals.

Colors are CSS custom properties on the element (or any ancestor):

| Property | Light default | Dark default |
|---|---|---|
| `--mascot-body` | `#2f6f62` (`--accent`) | `#6fbfab` |
| `--mascot-ink` (face) | `#ffffff` (`--accent-text`) | `#0d1f1a` |
| `--mascot-cheek` | `#ff9f8c` | `#ffb4a3` |
| `--mascot-spark` | `#e4a11b` | `#f0c060` |
| `--mascot-size` | used when there is no `size` attribute | |

## States

| State | What it does | Use |
|---|---|---|
| `idle` | Blinks at random 2.6–6.4 s intervals (sometimes a double blink) and breathes (4.2 s, ±3 %) | resting |
| `listening` | Tilts 5°, raises the brows, widens the eyes slightly | user is typing or speaking |
| `thinking` | Eyes glance up and right, one brow lifts, the mouth becomes three "typing" dots | waiting for the model |
| `talking` | An irregular 0.96 s open/close cycle of a smiling mouth | streaming a reply |
| `happy` | One squash-and-stretch hop on entry, smiling eyes, cheeks, slow sparkle twinkle | a good answer, done tasks |
| `celebrate` | One-shot, 1.7 s: two hops with a sparkle burst, then `mascot-done` and back to idle | milestones (never in crisis context) |
| `sleepy` | Eyes closed, slower and deeper breathing, `z` rising from the tail side | quiet hours, sandbox asleep |
| `calm` | Softened eyes, brows gently lifted at the inner ends, slow breathing, slow rare blinks, 600 ms pose changes. No bounce, no sparkles | serious or sensitive topics, crisis turns |
| `wave` | One-shot, 1.5 s: a small mitten waves from the side away from the tail while the body rocks | greeting, first open |

## Motion rules

- **Blending.** Every pose (tilt, eye and brow position, face offset) is a CSS transition, so a new state
  retargets from wherever the old one was. Drawn variants (eyes, mouths) cross-fade. Loops are paused rather than
  removed, so nothing jumps when a state ends. One-shot moves use the Web Animations API; when a move is cut short,
  the element reads the current transform and glides back to rest in 240 ms instead of snapping.
- **Easing.** Poses use ease-in-out (`cubic-bezier(.45,0,.25,1)`, 320 ms; 600 ms in `calm`). Entrances use a
  strong ease-out. Hops take off with ease-out and fall with ease-in, as gravity would.
- **Reduced motion** (OS setting or `motion="reduce"`): no blinking, breathing, hops or floating `z`.
  A state change dims the figure, swaps the pose while it is dim, and fades back (320 ms). The thinking dots keep a
  slow opacity pulse so "working" is still visible. One-shots hold for 1.4 s and still fire `mascot-done`.
- **Pausing.** All loops and moves pause while `document.hidden` is true or the element is off-screen
  (IntersectionObserver), and the blink timer stops. A one-shot started while hidden finishes once the element is
  visible again.
- **Cost.** Only `transform` and `opacity` animate, on a 64-unit SVG. There is one timer (the blink); no
  requestAnimationFrame loop.

## Design rationale

- **The bubble becomes the mascot.** The body is the brand tile: 18/64 corner radius (the `.brand-mark` ratio) and
  one 4-unit corner as the speech tail. The desktop bubble can swap its "M" for the character without changing
  silhouette, color or docking behavior.
- **Warm and smart, not childish.** It has a small vocabulary: two upright pill eyes (the two stems of the "M"),
  short brows, and one mouth line. There are no limbs, hair, clothes, ears or accessories, so it carries no gender,
  age or culture. Blush and the hand appear only in happy moments, so the resting face stays composed.
- **Thinking speaks the bubble's language.** The thinking mouth is the familiar typing indicator: a speech bubble
  that is "composing".
- **Calm is designed, not just slower.** It has softened eyes, slightly lifted inner brows (attentive and kind, not
  worried), slow breathing, and no humor or bounce, as section 9 of CONTRACTS.md requires for crisis context.
- **Legibility.** At 24 px the face reduces to eyes and mouth with thicker strokes; at 56 px brows return. Sparkles
  and `z` stay within 8 units of the box (7 px at 56 px), so they fit inside the desktop window's 8 px margin.

## Integration

**Next.js (apps/web).** Import it from a client component; the import is SSR-safe, but the element only upgrades
in the browser.

```tsx
"use client";
import "../../../../packages/mentor-mascot/mascot.js"; // or a tsconfig path alias
import type { MentorMascot } from "../../../../packages/mentor-mascot/mascot";
const ref = useRef<MentorMascot>(null);
<mentor-mascot ref={ref} state={busy ? "thinking" : "idle"} size={24} label="" onmascot-done={() => setMascot("idle")} />
```

- Follow the app theme (including `data-theme`) by setting `mentor-mascot { --mascot-body: var(--accent);
  --mascot-ink: var(--accent-text); }` in `globals.css`. The shadow DOM cannot see `:root[data-theme]` by itself.
- When `celebrate` or `wave` ends, the element sets `state="idle"` itself. If React keeps `state="celebrate"` in its
  props, replaying needs `ref.current.play("celebrate")`, or set your own state to `idle` in `onmascot-done`.
- The module must be served as a file the bundler can see. If Next refuses files outside the app, add the package
  to `transpilePackages` or copy it, as desktop does.

**Tauri (apps/desktop).** Copy `mascot.js` next to `bubble.html` and load it with
`<script type="module" src="mascot.js"></script>`; WebView2 is Chromium, so `adoptedStyleSheets` and WAAPI work.
Put `<mentor-mascot size="56" tail="right" label="">` inside the button in place of the "M" glyph. Make the
button background transparent so the mascot body is the tile, and keep the button's focus ring and badge. Map
`body[data-side=left]` to `tail="left"`. For the tile shadow on the transparent window, use
`filter: drop-shadow(...)` on the element instead of `box-shadow`. The bubble's existing dark-mode `--accent`
values match the mascot defaults.

## Demo

`demo.html` shows every state at 24, 40, 72 and 160 px on light and dark, all states in a grid (click a cell to
replay it), and the desktop-bubble and chat-avatar contexts. Browsers refuse ES modules over `file://`, so serve
the folder: `python -m http.server 8765` in this directory, then open `http://localhost:8765/demo.html`.
URL parameters: `?state=thinking&tail=left&motion=reduce`.
