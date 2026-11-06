# 006 — Chat: mentor reply entrance, tool timeline, approvals and notification lists

- **Status**: DONE
- **Commit**: n/a (not a git repository; audited 2026-11-03)
- **Severity**: MEDIUM
- **Category**: Purpose & frequency, Missed opportunities, Interruptibility
- **Estimated scope**: 4 files (`Message.tsx`, `ChatView.tsx`, `ApprovalCard.tsx`, `globals.css`); uses `motion` (motion.dev)

## Problem

- `src/components/chat/Message.tsx:31-40`: tool steps render as a flat list with a spinner; rows appear and the spinner swaps to a check in one frame, so the learner cannot see progress happening.
- Mentor replies, approval cards (`ChatView.tsx:149`) and notification rows (`ChatView.tsx:349`) teleport in and out; removing a notification makes the list jump.
- Frequency: the learner's own bubble appears on every send (tens per day, keyboard-initiated). It must stay instant.

## Target

- **User bubbles: no animation** (keyboard action). Composer typing: no animation.
- **Mentor bubble (first appearance only)**: opacity 0→1, `translateY(6px)`→0, 220 ms `var(--ease-out)` as a CSS animation on mount; nothing on text deltas. History replay renders without entrance (`data-replay`).
- **Typing indicator** while the reply has no text yet: three dots, `transform: translateY` + opacity, 1.2 s `ease-in-out` infinite, 150 ms phase offset; reduced motion: opacity pulse only.
- **Tool timeline**: vertical rail with dots; a new step rises from `y: 4` with opacity (Motion `AnimatePresence initial={false}`), the running dot pulses (`scale 1→1.25`, 1.2 s, ease-in-out, transform only), finishing swaps the dot for a check that pops `scale 0.6→1` in 160 ms (never from 0).
- **Approvals & notifications**: Motion `AnimatePresence` + `layout="position"` on rows so removals close the gap; enter `opacity 0, y 8, scale 0.98` → rest with spring `{ type: "spring", duration: 0.35, bounce: 0.15 }`; exit opacity + `x: 12`, 160 ms.
- Reduced motion: every Motion transition becomes `{ duration: 0.18 }` opacity only, no `layout`.

## Steps

1. Add `motion` (exact pinned version; 12.x includes hardware-accelerated `x`/`y`/`scale` shorthands for opacity/transform via WAAPI when possible).
2. Build `useReducedMotion` in `src/lib/motion.ts` and shared variants (`rise`, `fade`, `spring`).
3. Apply to the components above, keeping semantic lists (`ul/li`) and `aria-live` regions unchanged.

## Boundaries

- Never animate on `text_delta`. Never animate the learner's sent bubble or the composer.
- Keep scroll pinning (`useLayoutEffect` in ChatView) working: entrances use transform only, so `scrollHeight` is final immediately.

## Verification

- **Feel check**: in mock mode send "lịch": tool steps appear one by one with a pulsing dot, the approval card rises in, approving settles it without a jump. Dismiss a notification: rows below glide up. Reduced motion: fades only.
- **Done when**: sending feels instant; nothing in the log restarts animation while streaming.
