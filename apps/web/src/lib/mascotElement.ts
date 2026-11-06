/**
 * Loads the `<mentor-mascot>` custom element (packages/mentor-mascot, owner M; vendored by scripts/sync-mascot.mjs)
 * on the client only, with a dynamic import so it stays out of the server bundle.
 * Until it is defined, <Mascot> renders the brand mark instead, so nothing depends on the element being there.
 */
import { useSyncExternalStore } from "react";

export const MASCOT_TAG = "mentor-mascot";

let loading: Promise<boolean> | null = null;
const listeners = new Set<() => void>();

function defined(): boolean {
  return typeof window !== "undefined" && !!window.customElements?.get(MASCOT_TAG);
}

async function importAndDefine(): Promise<boolean> {
  if (defined()) return true;
  try {
    const mod = (await import("@/vendor/mentor-mascot.js")) as { defineMentorMascot?: () => void };
    mod.defineMentorMascot?.();
  } catch (e) {
    console.warn("mentor-mascot not available, using the brand mark", e);
  }
  return defined();
}

/** Starts loading once; resolves to whether the element is usable. */
export function loadMascotElement(): Promise<boolean> {
  if (typeof window === "undefined") return Promise.resolve(false);
  loading ??= importAndDefine().then((ok) => {
    for (const l of listeners) l();
    return ok;
  });
  return loading;
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  void loadMascotElement();
  return () => listeners.delete(cb);
}

/** True once the custom element is defined (false during SSR and before the module loads). */
export function useMascotElement(): boolean {
  return useSyncExternalStore(subscribe, defined, () => false);
}
