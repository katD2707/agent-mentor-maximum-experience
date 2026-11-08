/** Background download of enrolled courses (§5.5). One download per (course, version); progress is observable. */
import { api, type CourseDetail } from "../api";
import { cacheCover, courseStore, downloadCourse, downloadState, PackIntegrityError, type DownloadState } from "./offline";

type Listener = (s: DownloadState) => void;

const states = new Map<string, DownloadState>();
const listeners = new Map<string, Set<Listener>>();
const inflight = new Set<string>();
const k = (id: string, v: number) => `${id}@${v}`;

function set(id: string, v: number, s: DownloadState) {
  states.set(k(id, v), s);
  listeners.get(k(id, v))?.forEach((fn) => fn(s));
}

export function subscribeDownload(id: string, v: number, fn: Listener): () => void {
  const key = k(id, v);
  if (!listeners.has(key)) listeners.set(key, new Set());
  listeners.get(key)!.add(fn);
  return () => listeners.get(key)?.delete(fn);
}

/** Current state: live (in-flight or finished this session), else from what the store holds. */
export async function currentDownloadState(id: string, v: number): Promise<DownloadState> {
  return states.get(k(id, v)) ?? (await downloadState(courseStore(), id, v));
}

/** Start (or join) the download of pack + assets + cover. Never throws; failures show as state "error". */
export async function startDownload(token: string, id: string, v: number, expectedSha?: string | null): Promise<void> {
  const key = k(id, v);
  if (inflight.has(key)) return;
  const store = courseStore();
  const existing = await downloadState(store, id, v);
  if (existing.kind === "ready") {
    set(id, v, existing);
    return;
  }
  inflight.add(key);
  set(id, v, { kind: "downloading", done: 0, total: 0 });
  try {
    void cacheCover(token, store, id);
    const m = await downloadCourse({ api, token, store, onProgress: (p) => set(id, v, { kind: "downloading", ...p }) }, id, v, expectedSha);
    set(id, v, m.complete ? { kind: "ready" } : { kind: "partial", missing: m.missing.length });
  } catch (e) {
    set(id, v, { kind: "error" });
    if (e instanceof PackIntegrityError) await store.remove(id);
  } finally {
    inflight.delete(key);
  }
}

export const packShaFor = (info: CourseDetail | null | undefined, version: number): string | null => info?.versions.find((x) => x.version === version)?.pack_sha256 ?? null;
