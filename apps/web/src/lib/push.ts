/**
 * Web Push opt-in (CONTRACTS 9, Built N). Permission is asked only from a click in Settings, never on load,
 * and never inside the desktop pop-up (the shell has its own native toasts).
 */
import { API_BASE, getApi } from "./api";

/** base64url (VAPID public key) → bytes for PushManager.subscribe. */
export function urlBase64ToUint8Array(b64: string): Uint8Array<ArrayBuffer> {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    typeof Notification !== "undefined"
  );
}

/** Absolute API base for the service worker (it posts nudge actions itself). */
export function swUrl(apiBase: string = API_BASE, origin: string = window.location.origin): string {
  const abs = /^https?:\/\//.test(apiBase) ? apiBase : origin + (apiBase.startsWith("/") ? apiBase : `/${apiBase}`);
  return `/sw.js?api=${encodeURIComponent(abs.replace(/\/+$/, ""))}`;
}

/** A short, non-identifying device label shown in the gateway's device list, e.g. "Chrome · Windows". */
export function deviceLabel(ua: string = typeof navigator === "undefined" ? "" : navigator.userAgent): string {
  const browser = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Trình duyệt";
  const os = /Windows/.test(ua) ? "Windows" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Mac OS X/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : "";
  return os ? `${browser} · ${os}` : browser;
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  const reg = await navigator.serviceWorker.getRegistration("/");
  return (await reg?.pushManager.getSubscription()) ?? null;
}

export type EnableResult = "enabled" | "denied" | "dismissed" | "unavailable";

/** Call from a click handler only. */
export async function enablePush(): Promise<EnableResult> {
  if (!pushSupported()) return "unavailable";
  const key = await getApi().getVapidPublicKey();
  if (!key.enabled || !key.public_key) return "unavailable";
  const perm = await Notification.requestPermission();
  if (perm === "denied") return "denied";
  if (perm !== "granted") return "dismissed";
  const reg = await navigator.serviceWorker.register(swUrl(), { scope: "/" });
  await navigator.serviceWorker.ready;
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key.public_key) }));
  await getApi().subscribePush(sub.toJSON(), deviceLabel());
  return "enabled";
}

/** Removes this browser only (other devices keep their subscription). */
export async function disablePush(): Promise<void> {
  const sub = await currentSubscription();
  const endpoint = sub?.endpoint;
  await sub?.unsubscribe();
  if (endpoint) await getApi().unsubscribePush(endpoint);
}
