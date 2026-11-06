# 002 — Press feedback on buttons, drawer curve and scrim fade

- **Status**: DONE
- **Commit**: n/a (not a git repository; audited 2026-11-03)
- **Severity**: MEDIUM
- **Category**: Physicality & origin, Easing & duration
- **Estimated scope**: 1 file (`src/app/globals.css`), ~30 lines
- **Depends on**: 001 (tokens)

## Problem

1. No pressable element gives press feedback. `.btn` (globals.css:194) changes background on hover only, so a click on a slow action ("Lưu cài đặt", approval buttons) looks ignored for the ~180 ms of latency.
2. The mobile sidebar drawer uses the weak built-in curve:

```css
/* src/app/globals.css:641 — current */
transition: transform 0.2s ease;
```

3. The scrim (`.scrim`, globals.css:648) appears and disappears in one frame: a hard dark flash behind a sliding drawer.

## Target

```css
.btn {
  transition: background-color var(--dur-fast) ease, border-color var(--dur-fast) ease, color var(--dur-fast) ease,
    transform var(--dur-press) var(--ease-out);
}
.btn:active:not(:disabled) { transform: scale(0.97); }
.btn-icon:active:not(:disabled) { transform: scale(0.94); }
@media (prefers-reduced-motion: reduce) { .btn:active:not(:disabled) { transform: none; } }

/* drawer */
.sidebar { transition: transform 260ms var(--ease-drawer); }

/* scrim fades in; @starting-style needs no JS */
.scrim { opacity: 1; transition: opacity var(--dur-base) ease; }
@starting-style { .scrim { opacity: 0; } }
```

Enter-to-send never triggers `:active`, so keyboard sends stay instant.

## Repo conventions to follow

- Buttons: `.btn`, `.btn-primary`, `.btn-ghost`, `.btn-sm`, `.btn-icon` at globals.css:194-265.

## Steps

1. Add the transition + `:active` rules to `.btn` / `.btn-icon`.
2. Change the sidebar transition inside `@media (max-width: 860px)` to `transform 260ms var(--ease-drawer)`.
3. Add the scrim opacity transition with `@starting-style`.
4. Add the reduced-motion override (no scale, colours keep crossfading).

## Boundaries

- Motion properties only; no markup changes. No `transition: all`.

## Verification

- **Feel check**: click and hold any button: it shrinks within ~140 ms and returns on release. Narrow the window below 860px, open the menu: the drawer decelerates hard at the end, the scrim fades in rather than flashing. Slow DevTools animations to 10% to confirm scrim and drawer start together.
- **Done when**: every `.btn` has visible press feedback; reduced motion shows none.
