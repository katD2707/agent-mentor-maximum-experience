/**
 * Bridge to the Tauri desktop pop-up (apps/desktop). Everything here is a no-op in a normal browser.
 *
 * The desktop app loads this web app's `/popup` route in a frameless panel window. Tauri injects
 * `window.__TAURI_INTERNALS__` into that webview, and a runtime capability limited to the web origin
 * allows exactly the `desktop_*` commands below (see apps/desktop/src-tauri/src/lib.rs).
 */
import { useSyncExternalStore } from "react";

type Invoke = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;

interface TauriWindow {
  __TAURI__?: { core?: { invoke?: Invoke } };
  __TAURI_INTERNALS__?: { invoke?: Invoke };
}

const FLAG_KEY = "mentor-desktop";

function tauriInvoke(): Invoke | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as TauriWindow;
  return w.__TAURI__?.core?.invoke ?? w.__TAURI_INTERNALS__?.invoke ?? null;
}

/** Running inside the Tauri pop-up (IPC available). */
export function inTauri(): boolean {
  return tauriInvoke() !== null;
}

/** Desktop pop-up mode: inside Tauri, or a browser preview opened with `?desktop=1` (kept for the tab). */
export function isDesktopMode(): boolean {
  if (typeof window === "undefined") return false;
  if (inTauri()) return true;
  try {
    if (new URLSearchParams(window.location.search).get("desktop") === "1") {
      window.sessionStorage.setItem(FLAG_KEY, "1");
      return true;
    }
    return window.sessionStorage.getItem(FLAG_KEY) === "1";
  } catch {
    return false;
  }
}

/** Where a signed-in, onboarded user lands: the compact chat in desktop mode, else the full chat. */
export function homePath(desktop = isDesktopMode()): string {
  return desktop ? "/popup" : "/chat";
}

const noopSubscribe = () => () => {};

/** `isDesktopMode()` for rendering (false during SSR/hydration, then the real value). */
export function useDesktopMode(): boolean {
  return useSyncExternalStore(noopSubscribe, isDesktopMode, () => false);
}

/** Calls a desktop command; resolves to undefined outside Tauri or when the command fails. */
export async function desktopInvoke(cmd: string, args?: Record<string, unknown>): Promise<unknown> {
  const invoke = tauriInvoke();
  if (!invoke) return undefined;
  try {
    return await invoke(cmd, args);
  } catch (e) {
    console.warn(`desktop ${cmd} failed`, e);
    return undefined;
  }
}

export type DesktopSessionState = "loading" | "anon" | "onboarding" | "active" | "error";

/** Tell the desktop shell whether to show the bubble (signed in) or keep the login panel. */
export function reportSession(state: DesktopSessionState): void {
  void desktopInvoke("desktop_session", { state });
}

/** Something the learner did not ask for just now arrived; the bubble shows a badge if the panel is closed. */
export function reportUnread(kind: "notification" | "approval_request" | "turn_done"): void {
  void desktopInvoke("desktop_unread", { kind });
}

/** Collapse the panel back to the bubble. */
export function hidePanel(): void {
  void desktopInvoke("desktop_hide_panel");
}

/** Open a URL in the system browser (http/https only; the shell validates again). */
export function openExternal(url: string): void {
  void desktopInvoke("desktop_open_url", { url });
}

/**
 * CONTRACTS 9 desktop bridge: show a nudge as a speech balloon next to the bubble (or a native toast when the
 * bubble is hidden). The shell reports clicks back as the `mentor://nudge-action` event.
 */
export interface DesktopNudge {
  id: string;
  kind: string;
  title: string;
  body: string;
  actions: { id: string; label: string }[];
  mascot: string;
}

/** Where the shell put it (K): on screen, queued, a replay, a native toast, the open panel (show it inline), or off. */
export type NudgeRoute = "balloon" | "queued" | "duplicate" | "toast" | "panel" | "off";

/** Once per WebSocket notification (a bundle: once, with the main id). Undefined outside Tauri or on error. */
export async function forwardNudge(n: DesktopNudge): Promise<NudgeRoute | undefined> {
  const r = await desktopInvoke("desktop_nudge", { ...n });
  return typeof r === "string" ? (r as NudgeRoute) : undefined;
}

/**
 * What the chat is doing, for the bubble (K): `thinking` from a sent message until turn_done, `sleepy` in quiet
 * hours or while the sandbox sleeps, `calm` in crisis/safety turns (blocks playful states), else `idle`;
 * `celebrate` plays once on a celebration card.
 */
export type DesktopMascot = "idle" | "thinking" | "sleepy" | "calm" | "celebrate";

export function desktopMascotFor(i: {
  crisis: boolean;
  quiet: boolean;
  sleeping: boolean;
  inFlight: boolean;
  celebrating: boolean;
}): DesktopMascot {
  if (i.crisis) return "calm";
  if (i.celebrating) return "celebrate";
  if (i.inFlight) return "thinking";
  if (i.quiet || i.sleeping) return "sleepy";
  return "idle";
}

export function reportMascot(state: DesktopMascot): void {
  void desktopInvoke("desktop_mascot", { state });
}

export const NUDGE_ACTION_EVENT = "mentor://nudge-action";

type TauriEvent<T> = { event: string; id: number; payload: T };
interface TauriEventWindow {
  __TAURI__?: { event?: { listen?: <T>(event: string, cb: (e: TauriEvent<T>) => void) => Promise<() => void> } };
  __TAURI_INTERNALS__?: {
    invoke?: Invoke;
    transformCallback?: (cb: (e: unknown) => void, once?: boolean) => number;
  };
}

/**
 * Listens to a Tauri event from the remote panel page without @tauri-apps/api: the global API when the shell
 * injects it (`withGlobalTauri`), else the raw event plugin IPC. Resolves to an unlisten function; a no-op
 * outside Tauri or when the capability does not allow listening.
 */
export async function listenDesktop<T>(event: string, cb: (payload: T) => void): Promise<() => void> {
  if (typeof window === "undefined") return () => {};
  const w = window as unknown as TauriEventWindow;
  try {
    const listen = w.__TAURI__?.event?.listen;
    if (listen) return await listen<T>(event, (e) => cb(e.payload));
    const internals = w.__TAURI_INTERNALS__;
    if (internals?.invoke && internals.transformCallback) {
      const handler = internals.transformCallback((e) => cb((e as TauriEvent<T>).payload));
      const eventId = await internals.invoke("plugin:event|listen", { event, target: { kind: "Any" }, handler });
      return () => void internals.invoke?.("plugin:event|unlisten", { event, eventId }).catch(() => {});
    }
  } catch (e) {
    console.warn(`desktop listen ${event} failed`, e);
  }
  return () => {};
}
