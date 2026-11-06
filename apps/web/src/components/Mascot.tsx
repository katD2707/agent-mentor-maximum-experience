"use client";

import { useEffect, useRef, useState } from "react";
import { ONE_SHOT_MS } from "@/lib/mascot";
import { useMascotElement } from "@/lib/mascotElement";
import type { MascotState } from "@/lib/types";
import type { MascotDoneEvent, MentorMascot } from "@/vendor/mentor-mascot";

/**
 * The mentor's face. Uses M's `<mentor-mascot>` element when it is loaded, else the brand mark with a light CSS
 * rendition of the same state (so every surface works before and without the element).
 * `label` set = meaningful image (role="img"); omitted = decorative.
 */
export function Mascot({
  state,
  size = 40,
  label,
  tail,
  className,
  onDone,
}: {
  state: MascotState;
  size?: number;
  label?: string;
  tail?: "left" | "right" | "none";
  className?: string;
  /**
   * A one-shot (`celebrate`, `wave`) ended. `interrupted` = another state cut it short (the element then keeps
   * the new state instead of returning to `idle`).
   */
  onDone?: (state: MascotState, interrupted: boolean) => void;
}) {
  const ready = useMascotElement();
  const ref = useRef<MentorMascot>(null);
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  }, [onDone]);

  // Custom element: forward its mascot-done event.
  useEffect(() => {
    const el = ref.current;
    if (!ready || !el) return;
    const h = (e: MascotDoneEvent) => done.current?.(e.detail?.state ?? state, e.detail?.interrupted === true);
    el.addEventListener("mascot-done", h);
    return () => el.removeEventListener("mascot-done", h as EventListener);
  }, [ready, state]);

  // Fallback mark: simulate the one-shot ending so callers behave the same.
  useEffect(() => {
    if (ready) return;
    const ms = state === "celebrate" || state === "wave" ? ONE_SHOT_MS[state] : undefined;
    if (!ms) return;
    const t = window.setTimeout(() => done.current?.(state, false), ms);
    return () => window.clearTimeout(t);
  }, [ready, state]);

  if (ready) {
    return <mentor-mascot ref={ref} state={state} size={size} label={label ?? ""} tail={tail} className={className} />;
  }
  return (
    <span
      className={`mascot-fallback${className ? ` ${className}` : ""}`}
      data-state={state}
      style={{ ["--mascot-size" as string]: `${size}px` }}
      role={label ? "img" : undefined}
      aria-label={label || undefined}
      aria-hidden={label ? undefined : true}
    >
      <span className="mascot-fallback-mark">M</span>
      {state === "thinking" && (
        <span className="mascot-fallback-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
      )}
      {state === "sleepy" && (
        <span className="mascot-fallback-z" aria-hidden="true">
          z
        </span>
      )}
    </span>
  );
}

/** Greeting mascot for hero spots (login, onboarding): waves once, then rests. Decorative. */
export function HeroMascot({ size = 64 }: { size?: number }) {
  const [state, setState] = useState<MascotState>("wave");
  return (
    <div className="hero-mascot">
      <Mascot state={state} size={size} onDone={() => setState("idle")} />
    </div>
  );
}
