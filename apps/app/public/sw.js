/* Mentor service worker (web): offline shell, updates on the next launch, Web Push and notification taps. */
const BUILD = "__BUILD_ID__"; // stamped per build by vite.config.ts, so a new build changes this file and browsers notice it
const SHELL = "mentor-shell-" + BUILD;
const SHELL_FILES = ["./", "favicon.svg", "manifest.webmanifest"];

// A new build installs quietly in the background and waits: no skipWaiting, so it takes over on the next launch
// (when no tab runs the old one) and never swaps code under a lesson in progress.
self.addEventListener("install", (e) => e.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES))));
self.addEventListener("activate", (e) =>
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("mentor-shell-") && k !== SHELL).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  ),
);

// Offline shell: the page itself is network-first (the cached copy only when offline), hashed build files are
// cache-first. API calls and everything cross-origin are left alone.
self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          if (res.ok) caches.open(SHELL).then((c) => c.put("./", copy));
          return res;
        })
        .catch(() => caches.match("./").then((hit) => hit || Response.error())),
    );
  } else if (url.pathname.includes("/assets/")) {
    e.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            const copy = res.clone();
            if (res.ok) caches.open(SHELL).then((c) => c.put(req, copy));
            return res;
          }),
      ),
    );
  }
});

// an app path only: "/khoa-hoc/<id>?lesson=<id>", "/luyen-tap", ... Anything else (an old "/chat?..." link) is the hub.
function route(link) {
  if (typeof link !== "string" || !link.startsWith("/") || link.startsWith("//")) return "/";
  if (/^\/(khoa-hoc|khoa|luyen-tap|hoi-dap|tien-do)(\/|\?|$)/.test(link)) return link;
  return "/";
}

self.addEventListener("push", (event) => {
  let d = {};
  try {
    d = event.data ? event.data.json() : {};
  } catch (_) {
    /* no payload */
  }
  const id = d.reminder_id || d.id || "";
  event.waitUntil(
    self.registration.showNotification(d.title || "Mentor", {
      body: d.body || "",
      tag: id ? "mentor-" + id : "mentor",
      icon: "favicon.svg",
      data: { id: d.reminder_id || null, deepLink: route(d.deep_link || d.url) },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  const link = route(data.deepLink);
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      const c = list.find((x) => "focus" in x) || null;
      if (c) {
        c.postMessage({ type: "reminder-open", id: data.id || null, deepLink: link });
        return c.focus();
      }
      const sep = link.includes("?") ? "&" : "?";
      const url = self.registration.scope + "#" + link + (data.id ? sep + "reminder=" + encodeURIComponent(data.id) : "");
      return self.clients.openWindow(url);
    }),
  );
});
