# 005 — Skeleton loaders instead of spinners; progress bars on transform

- **Status**: DONE
- **Commit**: n/a (not a git repository; audited 2026-11-03)
- **Severity**: LOW
- **Category**: Performance, Missed opportunities
- **Estimated scope**: 3 files (`src/components/ui.tsx`, `src/components/SetupGuide.tsx`, `src/app/globals.css`)

## Problem

1. Every page load shows a spinner line (`src/components/ui.tsx:7-12`, `Loading`). Content-area spinners make the layout jump when content arrives; a skeleton shaped like the content keeps the layout stable and reads as faster.
2. The setup progress bar animates `width` (layout):

```css
/* src/app/globals.css:1163-1168 — current */
.setup-progress-bar > span { … transition: width 0.3s ease; }
```

## Target

- `Loading` keeps its props and its `role="status"` + `aria-live` label (visually hidden) but renders 3 skeleton lines (`.skeleton-line`, widths 92% / 78% / 56%) unless `full` is set (full screen keeps a small spinner + visible label: there is no layout to predict).
- Shimmer: a pseudo-element translating `-100%` → `100%` (`transform` only), 1.4 s `linear` infinite (constant motion = linear). Reduced motion: no shimmer, static tint.
- Progress bars: the inner span is `width: 100%`, `transform-origin: left`, `transform: scaleX(p)`, `transition: transform var(--dur-slow) var(--ease-out)`.

## Steps

1. Add `.skeleton`, `.skeleton-line` CSS and the shimmer keyframes.
2. Change `Loading` as described.
3. Convert `.setup-progress-bar > span` to scaleX and update `SetupGuide.tsx` inline `style={{ width }}` to `style={{ transform: \`scaleX(${p})\` }}`.

## Verification

- **Feel check**: open Memory / Plans in mock mode: lines shimmer in place, then content replaces them without the header jumping. Reduced motion: static lines.
- **Done when**: `rg "transition: width" src` returns nothing.
