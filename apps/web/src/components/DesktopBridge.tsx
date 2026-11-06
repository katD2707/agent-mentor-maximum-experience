"use client";

import { useEffect } from "react";
import { hidePanel, inTauri, isDesktopMode, openExternal, reportSession, type DesktopSessionState } from "@/lib/desktop";
import { useSession } from "./session";

/**
 * Glue between the web app and the Tauri pop-up shell (apps/desktop). Renders nothing and does
 * nothing in a normal browser tab. In the desktop panel it:
 * - reports the session state, so the shell shows the bubble only when signed in;
 * - collapses the panel on Esc (unless a dialog is open);
 * - opens new-tab and cross-origin links in the system browser instead of inside the panel.
 */
export function DesktopBridge() {
  const { status, me } = useSession();

  useEffect(() => {
    if (isDesktopMode()) document.documentElement.dataset.desktop = "1";
  }, []);

  const state: DesktopSessionState =
    status === "ready" ? (me?.onboarding_state === "active" ? "active" : me ? "onboarding" : "loading") : status;
  useEffect(() => {
    if (inTauri()) reportSession(state);
  }, [state]);

  useEffect(() => {
    if (!inTauri()) return;

    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape" || e.defaultPrevented || e.isComposing) return;
      if (document.querySelector("dialog[open]")) return; // the dialog handles its own Esc
      hidePanel();
    }

    function onClick(e: MouseEvent) {
      if (e.defaultPrevented || e.button !== 0) return;
      const a = (e.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!a) return;
      let url: URL;
      try {
        url = new URL(a.href, window.location.href);
      } catch {
        return;
      }
      if (url.protocol !== "http:" && url.protocol !== "https:") return;
      const newTab = a.target === "_blank" || e.ctrlKey || e.shiftKey || e.metaKey;
      if (!newTab && url.origin === window.location.origin) return; // normal in-panel navigation
      e.preventDefault();
      openExternal(url.href);
    }

    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("click", onClick, true);
    };
  }, []);

  return null;
}
