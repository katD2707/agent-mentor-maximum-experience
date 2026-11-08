# @mentor/mentor-mascot

`<mentor-mascot>`: "Mực", the app's guide (an original purple ink drop holding a pencil). One dependency-free ES
module with TypeScript types. It is the single source of truth for the character; the design mockups
(`survey/mockups/mascot.js`) are a throwaway preview of it.

- Lives on every screen at a fixed spot, idles (bobs, blinks, looks around), and parks itself where no
  link, button or input is underneath. It re-checks after scrolling and DOM changes.
- **Tap or click**: opens a small chat window anchored to Mực ("Bạn cần mình hướng dẫn gì?"). It shows a typing
  state, then the answer from your `ask` function. A "Chỉ cho mình" list underneath names the visible
  `data-guide` areas, so keyboard and screen-reader users never need to drag.
- **Hold, then drag** onto any area: the nearest ancestor with `data-guide="<key>"` under the drop point is softly
  highlighted, Mực stands beside it and a speech bubble shows `guides[key][lang]`. Unknown areas get a friendly
  "chỗ này mình chưa biết". After a tap elsewhere, "Hiểu rồi", Escape or about 6 s, Mực runs to a random free spot.
- The element never calls an API itself.

## Use

```html
<mentor-mascot lang="vi"></mentor-mascot>
<script type="module" src="./mascot.js"></script>
```

```js
const m = document.querySelector("mentor-mascot");
m.guides = { courses: { vi: "Các khóa em đang học.", en: "Your courses." } };
m.ask = async (question, lang) => (await fetch("/v1/guide", { method: "POST", body: JSON.stringify({ question, lang }) }).then(r => r.json())).answer;
```

Mark up the app:

```html
<section data-guide="courses" data-guide-label="Khóa học">...</section>
```

`data-guide-label` is the chip text in the chat list (default: the key, capitalised). Nested areas work: the
innermost `data-guide` wins. Add `data-mascot-avoid` to anything else Mực must not stand on.

## API

| Member | Description |
|---|---|
| `ask: (q: string, lang: "vi"\|"en") => Promise<string>` | Set by the host. Rejection, empty answer or 45 s timeout shows a friendly fallback. Without it the chat says it cannot answer yet. |
| `guides: Record<string, {vi: string, en: string}>` | Explanations by `data-guide` key. Assign a new object to update. |
| `lang` / attribute `lang` | `"vi"` (default) or `"en"`. Falls back to `<html lang>`. Switching re-renders open UI. |
| `avoid: string` | CSS selector for things to stay off. Default covers links, buttons, inputs, `[role=button]`, `[data-mascot-avoid]`. |
| `openChat()`, `closeChat()` | Programmatic chat. |
| `guide(key)` | Explain the first visible area with that key (same flow as a drop). |
| `say(text, ms?)` | Short speech bubble, e.g. a first-run greeting. |
| `relocate()` | Call after a route change; moves only if Mực now sits on something interactive. |
| attribute `theme="light\|dark"` | Force a palette. Default follows `prefers-color-scheme`. |
| attribute `motion="reduce"` | Force fade-only motion. Default follows `prefers-reduced-motion`. |

Events (bubble, composed): `mascot-ask` (`detail: {question, lang}`), `mascot-guide` (`detail: key`),
`mascot-guide-unknown` (`detail: {key: string|null}`).

## Styling

Custom properties inherit into the shadow DOM, so the app's tokens apply: `--tim` (accent, highlight, focus ring),
`--ink` (text), `--paper` (chat background), `--rule` (borders), `--font-ui`. Overrides: `--mascot-size` (height,
default 64px), `--mascot-z` (9995), `--mascot-a`, `--mascot-b` (body gradient), `--mascot-shoe`, `--mascot-accent`,
`--mascot-bubble` (speech bubble fill, white text), `--mascot-ink`, `--mascot-paper`, `--mascot-rule`, `--mascot-soft`.

## Accessibility

Mực is a focusable button (`aria-haspopup="dialog"`). Enter or Space opens the chat and focuses the input; Escape
closes any bubble and returns focus. Guides picked from the list stay until dismissed (no timeout) and the bubble
is a `role="status"`. With `prefers-reduced-motion` there is no running or hopping: Mực fades out and in at the new
spot and all animation stops. Pointer events cover mouse and touch; it works at 360px wide.

## React (Next.js or Vite)

```tsx
"use client";
import { useEffect, useRef } from "react";
import type { MentorMascot, MascotGuides } from "@mentor/mentor-mascot/mascot";

export function Guide({ guides, lang }: { guides: MascotGuides; lang: "vi" | "en" }) {
  const ref = useRef<MentorMascot>(null);
  useEffect(() => {
    import("@mentor/mentor-mascot/mascot.js"); // registers the element in the browser only
  }, []);
  useEffect(() => {
    const m = ref.current;
    if (!m) return;
    m.guides = guides;
    m.ask = async (question, l) => {
      const r = await fetch("/api/guide", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question, lang: l }) });
      return (await r.json()).answer;
    };
    const onGuide = (e: CustomEvent<string>) => track("mascot_guide", { key: e.detail });
    m.addEventListener("mascot-guide", onGuide);
    return () => m.removeEventListener("mascot-guide", onGuide);
  }, [guides]);
  return <mentor-mascot ref={ref} lang={lang} />;
}
```

Render `<Guide>` once in the root layout, after the page content. On route changes call
`ref.current?.relocate()`. Set properties from an effect (not JSX attributes) in React 18; React 19 also accepts them as props.

## Demo

Serve this folder (ES modules need http, not file://) and open `demo.html`:
`npx serve packages/mentor-mascot`.
