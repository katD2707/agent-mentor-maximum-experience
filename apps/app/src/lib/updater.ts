/**
 * Desktop app updates, driven from the page: the Rust side (`src-tauri/src/updater.rs`) checks the channel feed,
 * downloads and verifies the bundle; this side only sequences it and decides when a restart is polite. The web
 * build never uses this (its service worker updates the page on the next launch).
 */
export interface UpdateInfo {
  version: string;
  notes: string | null;
}
export type UpdateStatus =
  | { kind: "none" }
  | { kind: "downloading"; version: string; percent: number | null }
  | { kind: "ready"; version: string }
  | { kind: "installing"; version: string }
  | { kind: "failed" };
/** What a check found: nothing newer, a version (its download has started), or the check itself failed. */
export type CheckResult = { kind: "latest" } | { kind: "found"; version: string } | { kind: "error" };
export type Channel = "stable" | "beta";

type Call = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;
type Listen = (handler: (p: { downloaded: number; total: number | null }) => void) => Promise<() => void>;
const nativeCall: Call = async (cmd, args) => (await import("@tauri-apps/api/core")).invoke(cmd, args);
const nativeProgress: Listen = async (handler) => (await import("@tauri-apps/api/event")).listen<{ downloaded: number; total: number | null }>("update-progress", (e) => handler(e.payload)) as Promise<() => void>;

export const CHECK_EVERY_MS = 6 * 60 * 60 * 1000;
export const IDLE_MS = 60 * 1000;

// ---------------------------------------------------------------- channel (settings: "try new versions early")
const CHANNEL_KEY = "mentor.updateChannel";
export function getChannel(): Channel {
  try {
    return localStorage.getItem(CHANNEL_KEY) === "beta" ? "beta" : "stable";
  } catch {
    return "stable";
  }
}
export function setChannel(c: Channel): void {
  try {
    localStorage.setItem(CHANNEL_KEY, c);
  } catch {
    /* ignore */
  }
}

// ---------------------------------------------------------------- shared status (the notice and the settings row read the same one)
let current: UpdateStatus = { kind: "none" };
const listeners = new Set<() => void>();
export const getUpdateStatus = (): UpdateStatus => current;
export const setUpdateStatus = (s: UpdateStatus): void => {
  current = s;
  listeners.forEach((l) => l());
};
export const subscribeUpdate = (l: () => void): (() => void) => {
  listeners.add(l);
  return () => void listeners.delete(l);
};

export const percentOf = (downloaded: number, total: number | null): number | null => (total && total > 0 ? Math.min(100, Math.floor((downloaded * 100) / total)) : null);

/** Check, then download in the background. A failed check (offline, no feed) is silent in the notice and reported to the caller;
 * a failed download shows. */
export async function fetchUpdate(set: (s: UpdateStatus) => void, call: Call = nativeCall, opts: { channel?: Channel; listen?: Listen; onChecked?: (r: CheckResult) => void } = {}): Promise<CheckResult> {
  let info: UpdateInfo | null;
  try {
    info = (await call("update_check", { channel: opts.channel ?? "stable" })) as UpdateInfo | null;
  } catch {
    set({ kind: "none" });
    opts.onChecked?.({ kind: "error" });
    return { kind: "error" };
  }
  if (!info) {
    set({ kind: "none" });
    opts.onChecked?.({ kind: "latest" });
    return { kind: "latest" };
  }
  opts.onChecked?.({ kind: "found", version: info.version });
  set({ kind: "downloading", version: info.version, percent: null });
  let unlisten: (() => void) | null = null;
  try {
    unlisten = await (opts.listen ?? nativeProgress)((p) => set({ kind: "downloading", version: info.version, percent: percentOf(p.downloaded, p.total) }));
  } catch {
    /* no progress events (not in the desktop shell): the notice just shows no bar */
  }
  try {
    await call("update_download");
    set({ kind: "ready", version: info.version });
  } catch {
    set({ kind: "failed" });
  }
  unlisten?.();
  return { kind: "found", version: info.version };
}

/** A check from the shared status: never starts a second one while a download, a ready update or an install is pending. */
export async function checkNow(onChecked?: (r: CheckResult) => void): Promise<CheckResult> {
  const s = current;
  if (s.kind === "downloading" || s.kind === "ready" || s.kind === "installing") {
    const r: CheckResult = { kind: "found", version: s.version };
    onChecked?.(r);
    return r;
  }
  return fetchUpdate(setUpdateStatus, nativeCall, { channel: getChannel(), onChecked });
}

export async function installUpdate(version: string, set: (s: UpdateStatus) => void, call: Call = nativeCall): Promise<void> {
  set({ kind: "installing", version });
  try {
    await call("update_install"); // Windows: the installer takes over and the app exits here
  } catch {
    set({ kind: "failed" });
  }
}

/** A lesson or a practice run is open: never restart under the learner. */
export const isBusyRoute = (path: string): boolean => /^\/khoa-hoc\/[^/]+\/hoc/.test(path) || /^\/luyen-tap\/[^/]+/.test(path);

/** Restart only from a calm moment: off the lesson/practice screens, and the window hidden or untouched for a minute. */
export const canRestart = (o: { path: string; hidden: boolean; idleMs: number }): boolean => !isBusyRoute(o.path) && (o.hidden || o.idleMs >= IDLE_MS);
