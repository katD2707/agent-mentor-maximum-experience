# 001 — Add motion tokens and replace the reduced-motion kill switch

- **Status**: DONE
- **Commit**: n/a (apps/web is not inside a git repository; audited 2026-11-03)
- **Severity**: MEDIUM
- **Category**: Accessibility, Cohesion & tokens
- **Estimated scope**: 1 file (`src/app/globals.css`), ~40 lines

## Problem

There are no easing or duration tokens; the few transitions use bare keywords
(`0.15s`, `0.2s ease`, `0.3s ease`). And reduced motion removes *all* feedback,
including opacity/colour changes that aid comprehension:

```css
/* src/app/globals.css:672 — current */
@media (prefers-reduced-motion: reduce) {
  * {
    transition: none !important;
    animation: none !important;
  }
}
```

Reduced motion means "no movement", not "no feedback": the switch thumb, the
toast fade, the dialog fade should still crossfade. With this rule every new
animation added later (toasts, cards, dialogs) silently becomes a hard cut.

## Target

Tokens on `:root` (only once; the dark-mode blocks do not need copies):

```css
:root {
  --ease-out: cubic-bezier(0.23, 1, 0.32, 1);
  --ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);
  --ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);
  --dur-press: 140ms;
  --dur-fast: 160ms;
  --dur-base: 220ms;
  --dur-slow: 280ms;
}
```

Reduced motion keeps opacity/colour transitions and drops movement. Components
own their reduced-motion branch (a CSS `@media` rule next to the component, or
the JS `useReducedMotion` hook for Motion components). The global rule only
neutralises keyframe *movement* and smooth scrolling:

```css
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  .spinner { animation-duration: 1.6s; } /* a frozen spinner reads as "stuck"; keep it turning, slower */
}
```

Each transform-based rule in the file gets a sibling reduced-motion rule that
removes the transform but keeps `opacity`.

## Repo conventions to follow

- All styles live in `src/app/globals.css`; tokens sit in the first `:root { … }` block (line 2).
- Exemplar of a token in use: `border-radius: var(--radius-sm);` in `.btn` (globals.css:202).

## Steps

1. Add the seven tokens above to the first `:root` block in `src/app/globals.css`.
2. Replace the block at globals.css:672 with the target block.
3. Replace `transition: background 0.15s;` (switch, ~line 373) with `transition: background-color var(--dur-fast) ease;` and `transition: transform 0.15s;` (~line 384) with `transition: transform var(--dur-fast) var(--ease-out);`.
4. Add `@media (prefers-reduced-motion: reduce) { .switch input::after { transition: none; } }`.

## Boundaries

- Do NOT change colours, spacing or markup.
- Do NOT add dependencies.
- If line numbers drifted, find the blocks by their selectors; stop if they no longer exist.

## Verification

- **Mechanical**: `pnpm exec tsc --noEmit` passes (CSS-only change).
- **Feel check**: DevTools → Rendering → emulate `prefers-reduced-motion: reduce`. The settings switch thumb jumps without sliding but its colour still crossfades; the chat status spinner still turns, slowly.
- **Done when**: `grep -n "transition: none !important" src/app/globals.css` returns nothing and the tokens exist.
