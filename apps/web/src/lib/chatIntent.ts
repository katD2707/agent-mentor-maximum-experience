/**
 * Hand-off from other screens (the setup guide) to the chat: put a prompt in the message box, or open the
 * phone-upload QR. Queued in sessionStorage so it survives the navigation to /chat; an event tells an already
 * mounted chat to pick it up at once.
 */
import { useEffect, useRef } from "react";

export type ChatIntent = { kind: "prefill"; text: string } | { kind: "mobile-upload" };

const KEY = "mentor-chat-intent";
const EVENT = "mentor:chat-intent";

export function queueChatIntent(intent: ChatIntent): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(intent));
  } catch {
    return;
  }
  window.dispatchEvent(new Event(EVENT));
}

function takeChatIntent(): ChatIntent | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    sessionStorage.removeItem(KEY);
    const v = JSON.parse(raw) as ChatIntent;
    if (v.kind === "prefill" && typeof v.text === "string") return v;
    if (v.kind === "mobile-upload") return v;
  } catch {
    // ignore malformed or unavailable storage
  }
  return null;
}

/** Calls `handler` with a queued intent on mount and whenever a new one is queued. */
export function useChatIntent(handler: (intent: ChatIntent) => void): void {
  const ref = useRef(handler);
  useEffect(() => {
    ref.current = handler;
  });
  useEffect(() => {
    const run = () => {
      const i = takeChatIntent();
      if (i) ref.current(i);
    };
    run();
    window.addEventListener(EVENT, run);
    return () => window.removeEventListener(EVENT, run);
  }, []);
}
