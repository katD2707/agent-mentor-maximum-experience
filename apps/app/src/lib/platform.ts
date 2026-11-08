/** Where the app runs: the Tauri desktop shell or a browser. Native calls are loaded on demand so the web build never needs them. */
export const isTauri = (): boolean => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export interface OpenReminder {
  id: string | null;
  deepLink: string;
}

/** Desktop: the Rust side shows the toast (works while the window is hidden in the tray). */
export async function nativeShow(n: { id: string; title: string; body: string; deepLink: string }): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("show_reminder", { id: n.id, title: n.title, body: n.body, deepLink: n.deepLink });
}

/** Desktop: a toast was clicked (Rust shows the window and sends this event). Returns the unlisten function. */
export async function nativeOnOpen(handler: (o: OpenReminder) => void): Promise<() => void> {
  const { listen } = await import("@tauri-apps/api/event");
  return listen<{ id: string | null; deepLink: string }>("reminder-open", (e) => handler({ id: e.payload.id, deepLink: e.payload.deepLink }));
}

// ---------------------------------------------------------------- web
const swUrl = () => `${import.meta.env.BASE_URL}sw.js`;

export const webSupported = (): boolean => typeof navigator !== "undefined" && "serviceWorker" in navigator && typeof Notification !== "undefined" && window.isSecureContext;

export async function registerWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!webSupported()) return null;
  try {
    return await navigator.serviceWorker.register(swUrl());
  } catch {
    return null;
  }
}

export async function webShow(n: { id: string; title: string; body: string; deepLink: string }): Promise<void> {
  if (!webSupported() || Notification.permission !== "granted") return;
  const reg = (await navigator.serviceWorker.getRegistration()) ?? (await registerWorker());
  if (!reg) return;
  await reg.showNotification(n.title, { body: n.body, tag: `mentor-${n.id}`, icon: "favicon.svg", data: { id: n.id, deepLink: n.deepLink } });
}

/** Web: the service worker tells an open tab that a notification was clicked. */
export function webOnOpen(handler: (o: OpenReminder) => void): () => void {
  if (!("serviceWorker" in navigator)) return () => undefined;
  const fn = (e: MessageEvent) => {
    const d = e.data as { type?: string; id?: string | null; deepLink?: string } | null;
    if (d?.type === "reminder-open") handler({ id: d.id ?? null, deepLink: d.deepLink ?? "/" });
  };
  navigator.serviceWorker.addEventListener("message", fn);
  return () => navigator.serviceWorker.removeEventListener("message", fn);
}

export async function hasPushSubscription(): Promise<boolean> {
  if (!webSupported() || !("PushManager" in window)) return false;
  try {
    const reg = await navigator.serviceWorker.getRegistration();
    return !!(await reg?.pushManager.getSubscription());
  } catch {
    return false;
  }
}

const b64 = (s: string): Uint8Array<ArrayBuffer> => {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const raw = atob((s + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
};

export type NotifyState = "unsupported" | "default" | "denied" | "granted";
export const notifyState = (): NotifyState => (webSupported() ? Notification.permission : "unsupported");

/** From a click in Settings: ask permission and, when the gateway has VAPID keys, subscribe this browser to Web Push. */
export async function enableWebNotifications(
  getKey: () => Promise<{ enabled: boolean; public_key: string | null }>,
  send: (sub: { endpoint: string; keys: { p256dh: string; auth: string } }) => Promise<void>,
): Promise<NotifyState> {
  if (!webSupported()) return "unsupported";
  const perm = await Notification.requestPermission();
  if (perm !== "granted") return perm;
  const reg = (await registerWorker()) && (await navigator.serviceWorker.ready);
  if (!reg || !("PushManager" in window)) return perm;
  try {
    const k = await getKey();
    if (!k.enabled || !k.public_key) return perm;
    const sub = (await reg.pushManager.getSubscription()) ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(k.public_key) }));
    const j = sub.toJSON() as { endpoint?: string; keys?: { p256dh?: string; auth?: string } };
    if (j.endpoint && j.keys?.p256dh && j.keys.auth) await send({ endpoint: j.endpoint, keys: { p256dh: j.keys.p256dh, auth: j.keys.auth } });
  } catch {
    /* permission stays granted: local reminders still work while the app is open */
  }
  return perm;
}
