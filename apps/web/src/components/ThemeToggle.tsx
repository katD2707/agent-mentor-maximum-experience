"use client";

import { useSyncExternalStore } from "react";
import { Icon } from "./Icon";

type Theme = "system" | "light" | "dark";
const KEY = "mentor-theme";
const listeners = new Set<() => void>();

function read(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

function write(t: Theme) {
  try {
    if (t === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, t);
  } catch {
    // ignore
  }
  if (t === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** Inline script for <head>: applies the stored theme before first paint. */
export const THEME_SCRIPT = `try{var t=localStorage.getItem("${KEY}");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}`;

const LABEL: Record<Theme, string> = { system: "Theo hệ thống", light: "Sáng", dark: "Tối" };
const NEXT: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
const ICON: Record<Theme, "auto" | "sun" | "moon"> = { system: "auto", light: "sun", dark: "moon" };

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const theme = useSyncExternalStore(subscribe, read, () => "system" as Theme);
  return (
    <button
      type="button"
      className={compact ? "btn btn-ghost btn-icon btn-sm" : "btn btn-ghost btn-sm"}
      onClick={() => write(NEXT[theme])}
      aria-label={`Giao diện: ${LABEL[theme]}. Bấm để đổi sang ${LABEL[NEXT[theme]]}`}
      title={`Giao diện: ${LABEL[theme]}`}
    >
      <Icon name={ICON[theme]} size={16} />
      {!compact && <span>{LABEL[theme]}</span>}
    </button>
  );
}
