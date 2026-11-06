// Types for <mentor-mascot> (mascot.js). React 19 / TypeScript JSX support included.

export type MascotState =
  | "idle"
  | "listening"
  | "thinking"
  | "talking"
  | "happy"
  | "celebrate"
  | "sleepy"
  | "calm"
  | "wave";

/** States that play once, fire `mascot-done`, then return to `idle`. */
export type MascotOneShot = "celebrate" | "wave";

export interface MascotDoneDetail {
  state: MascotOneShot;
  /** true when another state cut the one-shot short (the element then does NOT return to idle). */
  interrupted: boolean;
}
export type MascotDoneEvent = CustomEvent<MascotDoneDetail>;

export interface MentorMascotAttributes {
  /** Unknown values fall back to `idle`. Default `idle`. */
  state?: MascotState;
  /** Rendered size in px (square). Below 32 the face is simplified. Default 40 (or `--mascot-size`). */
  size?: number | string;
  /** Accessible name. Default "Mentor". Empty string makes it decorative (aria-hidden). */
  label?: string;
  /** Which bottom corner is the speech tail. Default `right`. */
  tail?: "right" | "left" | "none";
  /** Force a palette instead of following `prefers-color-scheme`. CSS custom properties still win. */
  theme?: "light" | "dark";
  /** `reduce` forces the fade-only mode; `full` ignores `prefers-reduced-motion`. Default: follow the OS. */
  motion?: "reduce" | "full";
}

export declare class MentorMascot extends HTMLElement {
  state: MascotState;
  size: number;
  /** Set `state`; for one-shots the promise resolves with the `mascot-done` detail. */
  play(state: MascotState): Promise<MascotDoneDetail | { state: MascotState; interrupted: false }>;
  addEventListener<K extends keyof HTMLElementEventMap>(
    type: K,
    listener: (this: MentorMascot, ev: HTMLElementEventMap[K]) => unknown,
    options?: boolean | AddEventListenerOptions,
  ): void;
  addEventListener(type: "mascot-done", listener: (ev: MascotDoneEvent) => unknown, options?: boolean | AddEventListenerOptions): void;
  addEventListener(type: string, listener: EventListenerOrEventListenerObject, options?: boolean | AddEventListenerOptions): void;
}

/** Registers the element (idempotent; no-op on the server). The module also calls it on import in a browser. */
export declare function defineMentorMascot(tag?: string): typeof MentorMascot | undefined;

declare global {
  interface HTMLElementTagNameMap {
    "mentor-mascot": MentorMascot;
  }
  interface HTMLElementEventMap {
    "mascot-done": MascotDoneEvent;
  }
}

type MascotJsxProps = MentorMascotAttributes & {
  ref?: import("react").Ref<MentorMascot>;
  id?: string;
  class?: string;
  className?: string;
  style?: import("react").CSSProperties;
  slot?: string;
  hidden?: boolean;
  /** React 19 attaches `on<event>` props on custom elements as listeners for `<event>`. */
  "onmascot-done"?: (e: MascotDoneEvent) => void;
};

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "mentor-mascot": MascotJsxProps;
    }
  }
}
