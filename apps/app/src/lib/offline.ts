/**
 * Offline course storage (§3.3, §5.5). An enrolled course is downloaded whole (pack.json + every asset) so the
 * player works without a network. The player always asks the store first.
 */
import { assetUrl, coverUrl, fetchMedia, type Api, type AssetRef, type CoursePack } from "../api";
import { ApiError } from "../api/types";
import { sha256Hex } from "./hash";
import { packAssets } from "./packAssets";
import { needsNewerApp } from "./version";

/** Small storage interface; Cache Storage today (works in the Tauri webview too), a native store later. */
export interface CourseStore {
  getPack(courseId: string, version: number): Promise<ArrayBuffer | null>;
  putPack(courseId: string, version: number, bytes: ArrayBuffer): Promise<void>;
  /** Assets are stored by content (AssetRef.sha256), so a file shared by two versions or courses is kept once. */
  getAsset(courseId: string, version: number, asset: AssetRef): Promise<Blob | null>;
  putAsset(courseId: string, version: number, asset: AssetRef, blob: Blob): Promise<void>;
  getCover(courseId: string): Promise<Blob | null>;
  putCover(courseId: string, blob: Blob): Promise<void>;
  getManifest(courseId: string, version: number): Promise<Manifest | null>;
  putManifest(courseId: string, version: number, m: Manifest): Promise<void>;
  remove(courseId: string): Promise<void>;
}

export interface Manifest {
  /** every asset of the pack is stored */
  complete: boolean;
  total: number;
  stored: number;
  /** assets that could not be fetched (404, hash mismatch) */
  missing: string[];
  /** sha256 of every asset of the pack; lets remove() drop the blobs no other course or version still uses */
  assets?: string[];
}

// ---------------------------------------------------------------- implementations
export function memoryStore(): CourseStore {
  const m = new Map<string, ArrayBuffer | Blob | Manifest>();
  const k = (c: string, v: number | string, p: string) => `${c}/${v}/${p}`;
  return {
    async getPack(c, v) {
      return (m.get(k(c, v, "pack")) as ArrayBuffer) ?? null;
    },
    async putPack(c, v, b) {
      m.set(k(c, v, "pack"), b);
    },
    async getAsset(_c, _v, a) {
      return (m.get("sha/" + a.sha256) as Blob) ?? null;
    },
    async putAsset(_c, _v, a, b) {
      m.set("sha/" + a.sha256, b);
    },
    async getCover(c) {
      return (m.get(k(c, 0, "cover")) as Blob) ?? null;
    },
    async putCover(c, b) {
      m.set(k(c, 0, "cover"), b);
    },
    async getManifest(c, v) {
      return (m.get(k(c, v, "manifest")) as Manifest) ?? null;
    },
    async putManifest(c, v, x) {
      m.set(k(c, v, "manifest"), x);
    },
    async remove(c) {
      const drop = new Set<string>();
      for (const key of [...m.keys()]) {
        if (!key.startsWith(c + "/")) continue;
        if (key.endsWith("/manifest")) (m.get(key) as Manifest).assets?.forEach((s) => drop.add(s));
        m.delete(key);
      }
      for (const [key, v] of m) if (key.endsWith("/manifest")) (v as Manifest).assets?.forEach((s) => drop.delete(s));
      drop.forEach((s) => m.delete("sha/" + s));
    },
  };
}

const CACHE = "mentor-courses-v1";
const MAX_COVERS = 120;
const ORIGIN = "https://offline.mentor.invalid";

/** Cache Storage keyed by synthetic URLs. */
export function cacheStore(): CourseStore {
  const url = (c: string, v: number | string, p: string) => `${ORIGIN}/${encodeURIComponent(c)}/${v}/${p.split("/").map(encodeURIComponent).join("/")}`;
  const shaUrl = (sha: string) => `${ORIGIN}/sha/${sha}`;
  const open = () => caches.open(CACHE);
  const get = async (u: string) => (await (await open()).match(u)) ?? null;
  const put = async (u: string, body: Blob | ArrayBuffer | string, type: string) => (await open()).put(u, new Response(body, { headers: { "Content-Type": type } }));
  return {
    async getPack(c, v) {
      return (await get(url(c, v, "pack.json")))?.arrayBuffer() ?? null;
    },
    putPack: (c, v, b) => put(url(c, v, "pack.json"), b, "application/json"),
    async getAsset(c, v, a) {
      const hit = await get(shaUrl(a.sha256));
      if (hit) return hit.blob();
      // Older copies were keyed by course/version/path: verify, move under the content key, drop the old entry.
      const old = url(c, v, "assets/" + a.path);
      const legacy = await get(old);
      if (!legacy) return null;
      const blob = await legacy.blob();
      if ((await sha256Hex(await blob.arrayBuffer())) !== a.sha256) return null;
      await put(shaUrl(a.sha256), blob, blob.type || "application/octet-stream");
      await (await open()).delete(old);
      return blob;
    },
    putAsset: (_c, _v, a, b) => put(shaUrl(a.sha256), b, b.type || "application/octet-stream"),
    async getCover(c) {
      return (await get(url(c, 0, "cover")))?.blob() ?? null;
    },
    async putCover(c, b) {
      await put(url(c, 0, "cover"), b, b.type || "image/webp");
      // covers of courses merely seen in lists are kept too: stay small
      const cache = await open();
      const covers = (await cache.keys()).filter((r) => r.url.endsWith("/0/cover"));
      for (const r of covers.slice(0, Math.max(0, covers.length - MAX_COVERS))) await cache.delete(r);
    },
    async getManifest(c, v) {
      const r = await get(url(c, v, "manifest.json"));
      return r ? ((await r.json()) as Manifest) : null;
    },
    putManifest: (c, v, m) => put(url(c, v, "manifest.json"), JSON.stringify(m), "application/json"),
    async remove(c) {
      const cache = await open();
      const prefix = `${ORIGIN}/${encodeURIComponent(c)}/`;
      const drop = new Set<string>();
      const shasOf = async (req: Request) => ((await (await cache.match(req))?.json().catch(() => null)) as Manifest | null)?.assets ?? [];
      for (const req of await cache.keys()) {
        if (!req.url.startsWith(prefix)) continue;
        if (req.url.endsWith("/manifest.json")) (await shasOf(req)).forEach((s) => drop.add(s));
        await cache.delete(req);
      }
      // a blob stays while another course or version still lists it
      for (const req of await cache.keys()) if (req.url.endsWith("/manifest.json")) (await shasOf(req)).forEach((s) => drop.delete(s));
      for (const s of drop) await cache.delete(shaUrl(s));
    },
  };
}

export const defaultStore = (): CourseStore => (typeof caches !== "undefined" ? cacheStore() : memoryStore());
let shared: CourseStore | null = null;
/** The app-wide store (lazy so tests that never touch it do not need Cache Storage). */
export const courseStore = (): CourseStore => (shared ??= defaultStore());
export const setCourseStore = (s: CourseStore | null) => (shared = s);

// ---------------------------------------------------------------- download
export type DownloadApi = Pick<Api, "getPackBytes" | "getAssetBlob">;
export interface DownloadProgress {
  done: number;
  total: number;
}

export class PackIntegrityError extends Error {
  constructor(what: string) {
    super(`sha256 mismatch: ${what}`);
    this.name = "PackIntegrityError";
  }
}

/** The pack asks for a newer app than this one: it may hold block types this app cannot show, so it is not opened. */
export class PackTooNewError extends Error {
  constructor(readonly minVersion: string) {
    super(`pack needs app >= ${minVersion}`);
    this.name = "PackTooNewError";
  }
}

const dec = new TextDecoder();
const parsePack = (b: ArrayBuffer) => {
  const pack = JSON.parse(dec.decode(b)) as CoursePack;
  if (needsNewerApp(pack.min_app_version)) throw new PackTooNewError(pack.min_app_version);
  return pack;
};

/** pack.json from the network, checked against the expected sha256 (catalog `pack_sha256`) when known. */
export async function fetchPack(api: DownloadApi, token: string, courseId: string, version: number, expectedSha?: string | null): Promise<{ bytes: ArrayBuffer; pack: CoursePack }> {
  const bytes = await api.getPackBytes(token, courseId, version);
  if (expectedSha && (await sha256Hex(bytes)) !== expectedSha) throw new PackIntegrityError("pack.json");
  return { bytes, pack: parsePack(bytes) };
}

/**
 * Download pack.json and every asset into the store. Assets are fetched a few at a time and verified against the
 * sha256 in the pack; one that fails (missing file, bad hash) is recorded in the manifest and skipped, so the
 * rest of the course still works offline. A broken pack.json throws.
 */
export async function downloadCourse(
  deps: { api: DownloadApi; token: string; store: CourseStore; onProgress?: (p: DownloadProgress) => void },
  courseId: string,
  version: number,
  expectedSha?: string | null,
  prefetched?: { bytes: ArrayBuffer; pack: CoursePack },
): Promise<Manifest> {
  const { api, token, store } = deps;
  const { bytes, pack } = prefetched ?? (await fetchPack(api, token, courseId, version, expectedSha));
  await store.putPack(courseId, version, bytes);

  const assets = packAssets(pack);
  const missing: string[] = [];
  let stored = 0;
  let done = 0;
  const report = () => deps.onProgress?.({ done, total: assets.length });
  report();

  const one = async (a: AssetRef) => {
    try {
      if (await store.getAsset(courseId, version, a)) {
        stored++;
        return;
      }
      const blob = await api.getAssetBlob(token, courseId, version, a.path);
      if ((await sha256Hex(await blob.arrayBuffer())) !== a.sha256) throw new PackIntegrityError(a.path);
      await store.putAsset(courseId, version, a, blob);
      stored++;
    } catch (e) {
      if (e instanceof ApiError && e.code === "unauthorized") throw e;
      missing.push(a.path);
    } finally {
      done++;
      report();
    }
  };
  const queue = [...assets];
  await Promise.all(
    Array.from({ length: Math.min(3, queue.length) }, async () => {
      for (let a = queue.shift(); a; a = queue.shift()) await one(a);
    }),
  );

  const manifest: Manifest = { complete: missing.length === 0, total: assets.length, stored, missing, assets: [...new Set(assets.map((a) => a.sha256))] };
  await store.putManifest(courseId, version, manifest);
  return manifest;
}

/** Keep the cover for lists that must show it offline. Failures are ignored (the cover is decoration). */
export async function cacheCover(token: string, store: CourseStore, courseId: string): Promise<void> {
  try {
    if (await store.getCover(courseId)) return;
    const url = coverUrl(token, courseId);
    if (!url) return;
    const res = await fetchMedia(url);
    if (res.ok) await store.putCover(courseId, await res.blob());
  } catch {
    /* offline or no cover */
  }
}

// ---------------------------------------------------------------- load for the player
export interface LoadedPack {
  pack: CoursePack;
  source: "cache" | "network";
  /** URL for an asset: the cached blob when we have it, otherwise the (token) network URL. */
  url(path: string): string;
  /** how many assets came from the cache */
  cachedAssets: number;
  dispose(): void;
}

/** Cache first: the pack and every stored asset come from the store; only a miss touches the network. */
export async function loadPack(
  deps: { api: DownloadApi; token: string; store: CourseStore },
  courseId: string,
  version: number,
  expectedSha?: string | null,
): Promise<LoadedPack> {
  const { api, token, store } = deps;
  const cached = await store.getPack(courseId, version);
  let pack: CoursePack;
  let source: LoadedPack["source"];
  if (cached) {
    pack = parsePack(cached);
    source = "cache";
  } else {
    pack = (await fetchPack(api, token, courseId, version, expectedSha)).pack;
    source = "network";
  }

  const blobs = new Map<string, string>();
  await Promise.all(
    packAssets(pack).map(async (a) => {
      const b = await store.getAsset(courseId, version, a);
      if (b) blobs.set(a.path, URL.createObjectURL(b));
    }),
  );
  return {
    pack,
    source,
    cachedAssets: blobs.size,
    url: (path) => blobs.get(path) ?? assetUrl(token, courseId, version, path),
    dispose: () => blobs.forEach((u) => URL.revokeObjectURL(u)),
  };
}

export type DownloadState = { kind: "none" } | { kind: "downloading"; done: number; total: number } | { kind: "ready" } | { kind: "partial"; missing: number } | { kind: "error" };

export async function downloadState(store: CourseStore, courseId: string, version: number): Promise<DownloadState> {
  const m = await store.getManifest(courseId, version);
  if (!m) return { kind: "none" };
  return m.complete ? { kind: "ready" } : { kind: "partial", missing: m.missing.length };
}
