# 003 — Replace the hand-rolled toast stack with Sonner

- **Status**: DONE
- **Commit**: n/a (not a git repository; audited 2026-11-03)
- **Severity**: MEDIUM
- **Category**: Interruptibility, Missed opportunities
- **Estimated scope**: 2 files (`src/components/toast.tsx`, `src/app/globals.css`) plus the `sonner` dependency

## Problem

```tsx
// src/components/toast.tsx:21-23 — current
const id = Date.now() + Math.random();
setToasts((t) => [...t.slice(-3), { id, text, kind }]);
setTimeout(() => dismiss(id), kind === "error" ? 8000 : 4500);
```

Toasts mount and unmount with no motion (they teleport), the stack reflows abruptly when one leaves, there is no swipe-to-dismiss and no pause on hover, and timers run while the tab is hidden. Toasts are "occasional" UI: the standard enter/exit budget applies.

## Target

- `sonner` pinned to an exact version, `<Toaster position="bottom-right" visibleToasts={4} />`, durations 4500 ms (errors 8000 ms).
- Keep the public API `useToast()(text, kind?)`, so no caller changes. Kinds map to `toast.success` / `toast.error` / `toast`.
- Sonner animates enter/exit with interruptible CSS transitions, translates by `%` and dismisses swipes by velocity; do not override its keyframes. Theme it with the app tokens through `--normal-bg`, `--normal-border`, `--normal-text`, and an accent stripe per kind.
- Reduced motion: `[data-sonner-toast] { transform: none !important; }` inside `@media (prefers-reduced-motion: reduce)` while keeping its opacity transition.
- Rich notification toasts (mascot, title, body, action buttons) use `toast.custom()` on the same Toaster.

## Steps

1. `pnpm add sonner@<exact>` in `apps/web`.
2. Rewrite `ToastProvider` to render `<Toaster>` and provide `push(text, kind)` that calls Sonner.
3. Delete the `.toasts` / `.toast` CSS (globals.css:1277-1302) and add the token mapping.

## Boundaries

- Keep the `useToast` signature `(text: string, kind?: "info" | "ok" | "error") => void`.

## Verification

- **Feel check**: trigger three toasts quickly (Settings → "Sao chép" three times): each new toast pushes the stack smoothly, none restarts from zero; hover pauses the timer; a flick right dismisses.
- **Done when**: `rg 'className="toasts"' src` returns nothing and existing callers compile unchanged.
