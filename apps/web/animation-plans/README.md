# Animation plans (apps/web)

Audit of 2026-11-03 (improve-animations, standard effort). The web app had almost no motion: a few
transitions with built-in curves, a global reduced-motion rule that removed all feedback, a toast stack
with no enter/exit, and spinners for every load. These plans fix the corrective findings and lay the
foundations for the interaction layer (CONTRACTS.md section 9: mascot, chat cards, nudges), which W
implemented in the same pass.

| # | Plan | Severity | Status |
|---|---|---|---|
| 001 | [Motion tokens + reduced-motion rewrite](001-motion-tokens-and-reduced-motion.md) | MEDIUM | DONE |
| 002 | [Press feedback, drawer curve, scrim fade](002-press-feedback-and-drawer.md) | MEDIUM | DONE |
| 003 | [Sonner toasts](003-sonner-toasts.md) | MEDIUM | DONE |
| 004 | [Dialog entrance](004-dialog-entrance.md) | LOW | DONE |
| 005 | [Skeletons + transform progress bars](005-skeletons-and-progress.md) | LOW | DONE |
| 006 | [Chat entrances, tool timeline, animated lists](006-chat-entrances.md) | MEDIUM | DONE |

Order: 001 first (tokens everything else uses), then 002-005 in any order, then 006 (needs `motion`).

## Vetted findings

| # | Severity | Category | Location | Finding | Fix |
|---|---|---|---|---|---|
| 1 | MEDIUM | Accessibility | globals.css:672 | Reduced motion set `transition/animation: none` on `*`, removing all feedback | Fades stay, movement goes (001) |
| 2 | MEDIUM | Cohesion | globals.css | No easing/duration tokens; bare `ease` / `0.15s` | Tokens (001) |
| 3 | MEDIUM | Physicality | globals.css:194 | No press feedback on any button | `scale(0.97)` on `:active`, 140 ms (002) |
| 4 | MEDIUM | Easing | globals.css:641 | Drawer used built-in `ease`; scrim popped | `--ease-drawer` 260 ms, scrim fade (002) |
| 5 | MEDIUM | Interruptibility | toast.tsx:21 | Toasts teleported, stack jumped, no swipe/pause | Sonner (003) |
| 6 | LOW | Performance | globals.css:1168 | Progress bar animated `width` | `scaleX` (005) |

Missed opportunities: dialog entrances (004), skeleton loading (005), the chat tool timeline and list
insert/remove (006), plus the interaction layer itself (mascot states, cards, celebrations, nudges).
