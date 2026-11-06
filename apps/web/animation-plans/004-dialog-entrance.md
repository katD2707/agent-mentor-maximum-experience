# 004 — Give native dialogs (setup guide, confirm, history, phone upload) an entrance

- **Status**: DONE
- **Commit**: n/a (not a git repository; audited 2026-11-03)
- **Severity**: LOW
- **Category**: Missed opportunities
- **Estimated scope**: 1 file (`src/app/globals.css`), ~30 lines

## Problem

All modals are native `<dialog>` elements opened with `showModal()` (`src/components/ui.tsx:83`, `src/components/SetupGuide.tsx:105`, `HistoryDialog.tsx`, `MobileUploadDialog.tsx`). They appear in one frame and the backdrop snaps to dark. The setup guide is the first thing a new learner sees after onboarding (rare, first-time moment: some delight is allowed).

## Target

Pure CSS with `@starting-style`. Modals are centred, so `transform-origin: center` is correct (exempt from the origin rule):

```css
.dialog[open] {
  animation: dialog-in var(--dur-slow) var(--ease-out);
}
.dialog::backdrop { background: rgb(0 0 0 / 40%); }
.dialog[open]::backdrop { animation: backdrop-in var(--dur-base) ease; }
@keyframes dialog-in { from { opacity: 0; transform: translateY(8px) scale(0.97); } }
@keyframes backdrop-in { from { opacity: 0; } }
@media (prefers-reduced-motion: reduce) {
  .dialog[open] { animation-name: fade-in; }
}
@keyframes fade-in { from { opacity: 0; } }
```

A keyframe (not a transition) is acceptable here: a dialog opens once per user action and cannot be re-triggered mid-flight; exit stays instant (native close), which is the "system snaps" half of asymmetric timing. Never `scale(0)`.

Setup-guide steps: fade up 6px with a 40 ms stagger, first 6 items only (`nth-child(-n+6)`), 260 ms `var(--ease-out)`, `animation-fill-mode: both`.

## Steps

1. Add the rules above next to the `/* ---------- Dialog ---------- */` block (globals.css:1097).
2. Add the setup-guide stagger under `.setup-step`.

## Verification

- **Feel check**: Settings → "Mở hướng dẫn thiết lập": the panel rises 8px and settles under 300 ms, steps follow in a quick cascade that never blocks clicking. Reduced motion: fade only.
- **Done when**: every dialog fades/rises in.
