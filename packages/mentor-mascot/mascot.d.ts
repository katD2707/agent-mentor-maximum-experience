// Types for <mentor-mascot> (mascot.js). Includes React 19 JSX support.

export type MascotLang = "vi" | "en";

/** Explanation of one UI area, keyed by the value of its `data-guide` attribute. */
export type MascotGuides = Record<string, { vi: string; en: string }>;

/** Answers a how-to-use-the-app question. Set by the host app; the element never calls an API itself. */
export type MascotAsk = (question: string, lang: MascotLang) => Promise<string>;

/** One step of a tour: a data-guide area (text from `guides` unless given) or, without a key, a message from Mực itself. */
export interface MascotTourStep {
  key?: string;
  title?: { vi: string; en: string };
  text?: { vi: string; en: string };
}
export type MascotTourResult = "done" | "skipped" | "none";

export interface MascotAskDetail {
  question: string;
  lang: MascotLang;
}
/** `mascot-guide` detail is the `data-guide` key that was explained. */
export type MascotGuideEvent = CustomEvent<string>;
/** `mascot-guide-unknown` detail carries the unmapped key, or null when the drop point had no data-guide ancestor. */
export type MascotGuideUnknownEvent = CustomEvent<{ key: string | null }>;
export type MascotAskEvent = CustomEvent<MascotAskDetail>;

export interface MentorMascotAttributes {
  /** UI language. Falls back to `<html lang>`, then "vi". */
  lang?: MascotLang;
  /** Force a palette instead of following `prefers-color-scheme`. CSS custom properties still win. */
  theme?: "light" | "dark";
  /** `reduce` forces fade-only motion (no running). Default: follow `prefers-reduced-motion`. */
  motion?: "reduce";
}

export declare class MentorMascot extends HTMLElement {
  /** Host-provided answer function. Without it the chat says it cannot answer yet. */
  ask: MascotAsk | null;
  /** Host-provided explanations. Replace the whole object to update. */
  guides: MascotGuides;
  /** CSS selector of elements Mực should not stand on. Default covers links, buttons and form controls. */
  avoid: string;
  lang: MascotLang;

  openChat(): void;
  closeChat(): void;
  /** Explain the first visible element with data-guide="<key>". Resolves when Mực has run off again. */
  guide(key: string): Promise<void>;
  /** Show a short speech bubble (greetings, tips). */
  say(text: string, ms?: number): void;
  /** Re-check the spot after a route change; moves only if Mực sits on something interactive. */
  relocate(): void;
  /** Host callback behind the chat's "Show me this page again" chip (shown only while set). */
  replay: (() => void) | null;
  /**
   * Walk through areas one at a time (first visit of a screen). Steps whose key is not on screen are left out. The page
   * cannot scroll meanwhile and outside taps only nudge the bubble; "Got it, next" moves on, Skip or Escape leaves.
   * Resolves "none" when nothing could be shown or Mực was busy.
   */
  tour(steps: MascotTourStep[]): Promise<MascotTourResult>;
  /** End a running tour now. */
  stopTour(): void;

  addEventListener(type: "mascot-ask", listener: (ev: MascotAskEvent) => unknown, options?: boolean | AddEventListenerOptions): void;
  addEventListener(type: "mascot-guide", listener: (ev: MascotGuideEvent) => unknown, options?: boolean | AddEventListenerOptions): void;
  addEventListener(type: "mascot-guide-unknown", listener: (ev: MascotGuideUnknownEvent) => unknown, options?: boolean | AddEventListenerOptions): void;
  addEventListener<K extends keyof HTMLElementEventMap>(
    type: K,
    listener: (this: MentorMascot, ev: HTMLElementEventMap[K]) => unknown,
    options?: boolean | AddEventListenerOptions,
  ): void;
  addEventListener(type: string, listener: EventListenerOrEventListenerObject, options?: boolean | AddEventListenerOptions): void;
}

/** Registers the element (idempotent; no-op on the server). The module also calls it on import in a browser. */
export declare function defineMentorMascot(tag?: string): typeof MentorMascot | undefined;

declare global {
  interface HTMLElementTagNameMap {
    "mentor-mascot": MentorMascot;
  }
  interface HTMLElementEventMap {
    "mascot-ask": MascotAskEvent;
    "mascot-guide": MascotGuideEvent;
    "mascot-guide-unknown": MascotGuideUnknownEvent;
  }
}

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "mentor-mascot": React.DetailedHTMLProps<React.HTMLAttributes<MentorMascot>, MentorMascot> & MentorMascotAttributes;
    }
  }
}
