/**
 * Deep links the planner and reminders hand out (CONTRACTS.md section 12): `/khoa-hoc/<course>?lesson=<lesson>`,
 * `/khoa-hoc/<course>`, `/luyen-tap`. Turns one into a route the app has. Anything unknown goes to the hub, so a link
 * from an old server (`/chat?...`) or a hostile one never lands on a missing screen.
 */
export interface DeepTarget {
  /** route inside the HashRouter, with its query */
  to: string;
  /** set when the link came from a tapped reminder (`?reminder=<id>` is added by the service worker) */
  reminderId: string | null;
}

const ID = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/;
const FIXED = new Set(["/", "/khoa-hoc", "/khoa-hoc/tim-kiem", "/luyen-tap", "/hoi-dap", "/tien-do", "/dau-truong", "/phong-tu-hoc", "/thu-vien"]);
/** Làng gà routes with one id (CONTRACTS-LANGGA.md section 4): coop, mock test, arena paper. */
const WITH_ID = /^\/(chuong|kiem-tra|dau-truong|thu-vien\/paper)\/([^/]+)$/;

export function resolveDeepLink(link: string | null | undefined): DeepTarget {
  const hub: DeepTarget = { to: "/", reminderId: null };
  if (!link) return hub;
  let raw = link.trim();
  const hash = raw.indexOf("#");
  if (hash >= 0) raw = raw.slice(hash + 1); // a full app URL: keep only the route after `#`
  if (!raw.startsWith("/") || raw.startsWith("//")) return hub;
  let url: URL;
  try {
    url = new URL(raw, "http://app.invalid");
  } catch {
    return hub;
  }
  const reminderRaw = url.searchParams.get("reminder");
  const reminderId = reminderRaw && ID.test(reminderRaw) ? reminderRaw : null;
  const path = url.pathname.replace(/\/+$/, "") || "/";
  if (path === "/luyen-tap") {
    // a notes review reminder (CONTRACTS 16.4): the practice screen starts that session
    const notes = url.searchParams.get("notes");
    return { to: notes && ID.test(notes) ? `/luyen-tap?notes=${encodeURIComponent(notes)}` : path, reminderId };
  }
  if (FIXED.has(path)) return { to: path, reminderId };
  const idRoute = WITH_ID.exec(path);
  if (idRoute) {
    const id = decodeURIComponent(idRoute[2]);
    return ID.test(id) ? { to: `/${idRoute[1]}/${encodeURIComponent(id)}`, reminderId } : { to: "/", reminderId };
  }
  // the old research links of servers and reminders from before the Library: same places under /thu-vien
  if (path === "/nghien-cuu") return { to: "/thu-vien", reminderId };
  const paper = /^\/nghien-cuu\/paper\/([^/]+)$/.exec(path);
  if (paper) {
    const id = decodeURIComponent(paper[1]);
    return ID.test(id) ? { to: `/thu-vien/paper/${encodeURIComponent(id)}`, reminderId } : { to: "/thu-vien", reminderId };
  }
  const m = /^\/khoa-hoc\/([^/]+)(\/hoc)?$/.exec(path);
  if (!m) return { to: "/", reminderId };
  const course = decodeURIComponent(m[1]);
  if (!ID.test(course)) return { to: "/", reminderId };
  const lessonRaw = url.searchParams.get("lesson");
  const lesson = lessonRaw && ID.test(lessonRaw) ? lessonRaw : null;
  if (lesson) return { to: `/khoa-hoc/${encodeURIComponent(course)}/hoc?lesson=${encodeURIComponent(lesson)}`, reminderId };
  return { to: `/khoa-hoc/${encodeURIComponent(course)}${m[2] ?? ""}`, reminderId };
}

/** The same link without the `reminder` marker (what the address shows after the tap was handled). */
export function withReminder(link: string, reminderId: string): string {
  const { to } = resolveDeepLink(link);
  return `${to}${to.includes("?") ? "&" : "?"}reminder=${encodeURIComponent(reminderId)}`;
}
