/**
 * Motion tokens for JS (mirrors the CSS tokens in globals.css) and the reduced-motion hook.
 * Rule of the house: under `prefers-reduced-motion: reduce` everything becomes a short fade, and confetti is off.
 */
import { useSyncExternalStore } from "react";

/** Strong ease-out for UI entrances (same as --ease-out). */
export const EASE_OUT = [0.23, 1, 0.32, 1] as const;
/** On-screen movement (same as --ease-in-out). */
export const EASE_IN_OUT = [0.77, 0, 0.175, 1] as const;

export const DUR = { press: 0.14, fast: 0.16, base: 0.22, slow: 0.28 } as const;

/** Apple-style spring with a little life, for cards and list rows. */
export const SPRING = { type: "spring", duration: 0.38, bounce: 0.18 } as const;
/** The fade every animation collapses to under reduced motion. */
export const FADE = { duration: 0.18, ease: "easeOut" } as const;

const QUERY = "(prefers-reduced-motion: reduce)";

type MatchMediaHost = { matchMedia?: (q: string) => MediaQueryList } | undefined;

/** Store for useSyncExternalStore; `host` is injectable for tests. */
export function createReducedMotionStore(host: () => MatchMediaHost) {
  return {
    subscribe(cb: () => void): () => void {
      const mql = host()?.matchMedia?.(QUERY);
      if (!mql) return () => {};
      mql.addEventListener("change", cb);
      return () => mql.removeEventListener("change", cb);
    },
    getSnapshot(): boolean {
      return host()?.matchMedia?.(QUERY).matches ?? false;
    },
  };
}

const store = createReducedMotionStore(() => (typeof window === "undefined" ? undefined : window));

/** Current reduced-motion preference (false on the server), live-updating when the OS setting changes. */
export function prefersReducedMotion(): boolean {
  return store.getSnapshot();
}

/** React hook: true when the learner asked the OS for reduced motion. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(store.subscribe, store.getSnapshot, () => false);
}

/**
 * Enter/exit props for a Motion element that rises into place. Reduced motion: opacity only.
 * Exit is faster than entry (the system response snaps).
 */
export function rise(reduce: boolean, opts: { y?: number; scale?: number; x?: number } = {}) {
  const { y = 8, scale = 0.98, x = 0 } = opts;
  if (reduce) {
    return {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0, transition: FADE },
      transition: FADE,
    };
  }
  return {
    initial: { opacity: 0, y, x, scale },
    animate: { opacity: 1, y: 0, x: 0, scale: 1 },
    exit: { opacity: 0, scale: 0.98, transition: { duration: DUR.fast, ease: EASE_OUT } },
    transition: SPRING,
  };
}
