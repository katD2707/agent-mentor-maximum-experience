/* Mentor service worker: Web Push only (CONTRACTS 9, Built N). No caching, no fetch handler.
 *
 * Registered from Settings when the learner turns browser notifications on (never on page load), as
 * /sw.js?api=<API base>. The gateway sends a push only when no chat socket is open; titles and bodies are
 * generic because lock screens are public, and `answer:` actions are left out. Notifications are always silent.
 */

const API = new URL(self.location.href).searchParams.get("api") || "/api";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let d = {};
  try {
    d = event.data ? event.data.json() : {};
  } catch {
    d = {};
  }
  const id = d.id !== undefined && d.id !== null ? String(d.id) : "";
  const actions = (Array.isArray(d.actions) ? d.actions : [])
    .filter((a) => a && typeof a.id === "string" && !a.id.startsWith("answer:"))
    .slice(0, 2)
    .map((a) => ({ action: a.id, title: String(a.label || a.id) }));
  const url = typeof d.url === "string" && d.url.startsWith("/") ? d.url : id ? `/chat?notification=${encodeURIComponent(id)}` : "/chat";
  event.waitUntil(
    self.registration.showNotification(d.title || "Mentor", {
      body: d.body || "",
      tag: id ? `mentor-${id}` : "mentor",
      silent: true, // the mentor never makes a sound
      data: { id, url },
      actions,
    }),
  );
});

async function focusOrOpen(url, id) {
  const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  const same = wins.find((c) => new URL(c.url).origin === self.location.origin);
  if (same) {
    // An open tab shows it in its notification centre without reloading.
    same.postMessage({ type: "mentor:notification", id });
    return same.focus();
  }
  return self.clients.openWindow(url);
}

self.addEventListener("notificationclick", (event) => {
  const n = event.notification;
  const { id, url } = n.data || {};
  const action = event.action;
  n.close();
  if (action && action !== "open" && id) {
    const post = fetch(`${API.replace(/\/+$/, "")}/notifications/${encodeURIComponent(id)}/action`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ action }),
    }).catch(() => undefined);
    // A focus session shows up as a card: bring the chat forward for it. Snooze and done need no window.
    event.waitUntil(action === "start_focus" ? post.then(() => focusOrOpen(url || "/chat", id)) : post);
    return;
  }
  event.waitUntil(focusOrOpen(url || "/chat", id));
});
