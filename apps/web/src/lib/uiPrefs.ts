"use client";

/**
 * Per-device UI preferences (localStorage; no server endpoint fits these): text size and sounds.
 * `textScale` is applied app-wide (pages, pop-up) by setting the root font-size; all CSS uses rem.
 */
import { useSyncExternalStore } from "react";

export const TEXT_SCALE_MIN = 0.85;
export const TEXT_SCALE_MAX = 1.4;
export const TEXT_SCALE_KEY = "mentor-text-scale";
export const SOUNDS_KEY = "mentor-sounds";

export function clampScale(n: number): number {
  if (!Number.isFinite(n)) return 1;
  return Math.round(Math.min(TEXT_SCALE_MAX, Math.max(TEXT_SCALE_MIN, n)) * 100) / 100;
}

/** Root font-size as a percentage string, e.g. 1.15 -> "115%". */
export function scaleToPercent(n: number): string {
  return `${Math.round(clampScale(n) * 100)}%`;
}

export function applyTextScale(root: { style: { fontSize: string } }, n: number): void {
  const pct = scaleToPercent(n);
  root.style.fontSize = pct === "100%" ? "" : pct;
}

/** Inline <head> script: applies the stored size before first paint. */
export const TEXT_SCALE_SCRIPT = `try{var s=parseFloat(localStorage.getItem("${TEXT_SCALE_KEY}"));if(s>=0.85&&s<=1.4&&s!==1)document.documentElement.style.fontSize=Math.round(s*100)+"%"}catch(e){}`;

type Key = "textScale" | "sounds";
const listeners = new Set<() => void>();

function storage(): Storage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

export function readTextScale(st: Pick<Storage, "getItem"> | null = storage()): number {
  try {
    const raw = st?.getItem(TEXT_SCALE_KEY);
    return raw ? clampScale(parseFloat(raw)) : 1;
  } catch {
    return 1;
  }
}

export function readSounds(st: Pick<Storage, "getItem"> | null = storage()): boolean {
  try {
    return st?.getItem(SOUNDS_KEY) === "1";
  } catch {
    return false;
  }
}

export function setTextScale(n: number): void {
  const v = clampScale(n);
  try {
    if (v === 1) storage()?.removeItem(TEXT_SCALE_KEY);
    else storage()?.setItem(TEXT_SCALE_KEY, String(v));
  } catch {
    // ignore
  }
  if (typeof document !== "undefined") applyTextScale(document.documentElement, v);
  listeners.forEach((l) => l());
}

export function setSounds(on: boolean): void {
  try {
    if (on) storage()?.setItem(SOUNDS_KEY, "1");
    else storage()?.removeItem(SOUNDS_KEY);
  } catch {
    // ignore
  }
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  const onStorage = (e: StorageEvent) => {
    if (e.key === TEXT_SCALE_KEY || e.key === SOUNDS_KEY) {
      if (e.key === TEXT_SCALE_KEY && typeof document !== "undefined") applyTextScale(document.documentElement, readTextScale());
      l();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(l);
    window.removeEventListener("storage", onStorage);
  };
}

/** `useUiPref("textScale")` -> number, `useUiPref("sounds")` -> boolean (default off). */
export function useUiPref(key: "textScale"): number;
export function useUiPref(key: "sounds"): boolean;
export function useUiPref(key: Key): number | boolean {
  const num = useSyncExternalStore(subscribe, () => (key === "textScale" ? readTextScale() : 0), () => (key === "textScale" ? 1 : 0));
  const bool = useSyncExternalStore(subscribe, () => (key === "sounds" ? readSounds() : false), () => false);
  return key === "textScale" ? num : bool;
}
