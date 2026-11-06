/**
 * Confetti for rare, earned moments (a celebration card, a finished goal). Off under reduced motion, and the
 * caller must never fire it in a crisis turn (CONTRACTS 9). canvas-confetti is loaded on first use only.
 */
import { prefersReducedMotion } from "./motion";

/** Brand-adjacent colours: accent greens, a warm yellow, a soft coral. Read in light and dark. */
const COLORS = ["#2f6f62", "#6fbfab", "#f0c060", "#f2a49c", "#9cc4f0"];

export interface ConfettiOptions {
  /** Viewport-relative origin (0..1), e.g. the centre of the card that triggered it. */
  origin?: { x: number; y: number };
  /** "burst" = card celebration; "pop" = a smaller reward for a ticked goal. */
  size?: "burst" | "pop";
}

/** Origin for confetti at the centre of an element. */
export function originOf(el: Element | null): { x: number; y: number } | undefined {
  if (!el || typeof window === "undefined") return undefined;
  const r = el.getBoundingClientRect();
  return { x: (r.left + r.width / 2) / window.innerWidth, y: (r.top + r.height / 2) / window.innerHeight };
}

export async function fireConfetti(opts: ConfettiOptions = {}): Promise<void> {
  if (typeof window === "undefined" || prefersReducedMotion()) return;
  const { default: confetti } = await import("canvas-confetti");
  const origin = opts.origin ?? { x: 0.5, y: 0.6 };
  const base = { origin, colors: COLORS, disableForReducedMotion: true, zIndex: 9999, ticks: 180, scalar: 0.9 };
  if (opts.size === "pop") {
    void confetti({ ...base, particleCount: 40, spread: 55, startVelocity: 26, gravity: 1.1 });
    return;
  }
  void confetti({ ...base, particleCount: 70, spread: 70, startVelocity: 38 });
  window.setTimeout(() => {
    void confetti({ ...base, particleCount: 40, spread: 100, startVelocity: 28, decay: 0.92 });
  }, 140);
}
