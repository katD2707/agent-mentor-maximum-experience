"use client";

/**
 * Which conversation the chat shows in this tab/window: `null` = today's main chat, else `c-<id>`.
 * Kept in sessionStorage (each pop-up webview and tab has its own) with an event so a mounted chat switches at once.
 */
import { useSyncExternalStore } from "react";

const KEY = "mentor-active-conversation";
const EVENT = "mentor:conversation";

export function getActiveConversation(): string | null {
  try {
    return sessionStorage.getItem(KEY) || null;
  } catch {
    return null;
  }
}

export function setActiveConversation(id: string | null): void {
  try {
    if (id) sessionStorage.setItem(KEY, id);
    else sessionStorage.removeItem(KEY);
  } catch {
    // ignore
  }
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  return () => window.removeEventListener(EVENT, cb);
}

export function useActiveConversation(): string | null {
  return useSyncExternalStore(subscribe, getActiveConversation, () => null);
}

// ---- jump to a message (search hits) ----

/** A message the chat should scroll to once it is on screen. `date` set = an earlier day of the main chat. */
export interface MessageFocus {
  ts: string;
  date: string | null;
}

const FOCUS_KEY = "mentor-focus-message";
export const FOCUS_MESSAGE_EVENT = "mentor:focus-message";

const FOCUS_TTL_MS = 30_000;

/**
 * Survives the route change to /chat and the chat remounting on a conversation switch (sessionStorage), and pokes a
 * chat that is already mounted. It stays pending until a chat actually scrolls to it (`clearMessageFocus`).
 */
export function requestMessageFocus(f: MessageFocus): void {
  try {
    sessionStorage.setItem(FOCUS_KEY, JSON.stringify({ ...f, at: Date.now() }));
  } catch {
    // ignore: the conversation still opens, just without the scroll
  }
  window.dispatchEvent(new Event(FOCUS_MESSAGE_EVENT));
}

export function peekMessageFocus(): MessageFocus | null {
  try {
    const raw = sessionStorage.getItem(FOCUS_KEY);
    if (!raw) return null;
    const f = JSON.parse(raw) as MessageFocus & { at?: number };
    if (!f.at || Date.now() - f.at > FOCUS_TTL_MS) {
      sessionStorage.removeItem(FOCUS_KEY);
      return null;
    }
    return { ts: f.ts, date: f.date };
  } catch {
    return null;
  }
}

export function clearMessageFocus(): void {
  try {
    sessionStorage.removeItem(FOCUS_KEY);
  } catch {
    // ignore
  }
}

/** Scrolls `root`'s message with this timestamp into view and flashes it; false while it is not rendered yet. */
export function scrollToMessage(root: ParentNode | null, ts: string): boolean {
  const el = root?.querySelector<HTMLElement>(`[data-ts="${CSS.escape(ts)}"]`);
  if (!el) return false;
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
  el.classList.add("msg-found");
  window.setTimeout(() => el.classList.remove("msg-found"), 2400);
  return true;
}

/** Events other parts of the UI use to ask the chat for something. */
export const NEW_CONVERSATION_EVENT = "mentor:new-conversation";
export const OPEN_CONVERSATIONS_EVENT = "mentor:open-conversations";
export const OPEN_SEARCH_EVENT = "mentor:open-search";
export const OPEN_SHORTCUTS_EVENT = "mentor:open-shortcuts";
