"use client";

import { animate } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { EASE_OUT } from "@/lib/motion";

/**
 * A number that counts up to `value`: from 0 on first show, from the previous value on updates. Writes the text
 * node directly (no React render per frame). `run` false (reduced motion, history) shows the value at once.
 */
export function CountUp({ value, run, delay = 0 }: { value: number; run: boolean; delay?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  // First paint only; afterwards the effect owns the text node (React never rewrites an unchanged text child).
  const [first] = useState(() => (run ? 0 : value));
  const shown = useRef(first);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!run || shown.current === value) {
      el.textContent = String(value);
      shown.current = value;
      return;
    }
    const controls = animate(shown.current, value, {
      duration: 0.9,
      delay,
      ease: EASE_OUT,
      onUpdate: (v) => {
        shown.current = Math.round(v);
        el.textContent = String(shown.current);
      },
    });
    return () => controls.stop();
  }, [value, run, delay]);
  return <span ref={ref}>{first}</span>;
}
