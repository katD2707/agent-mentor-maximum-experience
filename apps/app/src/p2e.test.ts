import { Blob as NodeBlob } from "node:buffer"; // jsdom's Blob is not understood by Response
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, setMediaToken, setMediaTokenSource, type CoursePack } from "./api";
import { cacheCover, cacheStore, downloadCourse, memoryStore, type DownloadApi } from "./lib/offline";
import { flushOutbox, loadEnrollments, readOutbox, saveProgress, writeMirror } from "./lib/enrollments";
import { sha256Hex } from "./lib/hash";
import { recoverMediaUrl, retryMedia } from "./api/media";

/** Minimal Cache Storage: put/match/delete/keys by URL, enough for cacheStore(). */
function fakeCaches() {
  const stores = new Map<string, Map<string, Response>>();
  return {
    async open(name: string) {
      const m = stores.get(name) ?? new Map<string, Response>();
      stores.set(name, m);
      return {
        async match(r: string | Request) {
          return m.get(typeof r === "string" ? r : r.url)?.clone();
        },
        async put(r: string | Request, res: Response) {
          m.set(typeof r === "string" ? r : r.url, res);
        },
        async delete(r: string | Request) {
          return m.delete(typeof r === "string" ? r : r.url);
        },
        async keys() {
          return [...m.keys()].map((url) => ({ url }) as Request);
        },
      };
    },
  };
}

const enc = new TextEncoder();
async function packOf(version: number, files: Record<string, string>) {
  const refs = await Promise.all(Object.entries(files).map(async ([path, body]) => ({ path, mime: "image/png", sha256: await sha256Hex(enc.encode(body)), bytes: body.length })));
  const pack: CoursePack = {
    schema_version: 1,
    course_id: "c1",
    version,
    min_app_version: "0.1.0",
    language: "vi",
    age_band: "g10_12",
    title: "T",
    chapters: [{ id: "ch", title: "Ch", lessons: [{ id: "l1", title: "L", est_minutes: 1, key_ideas: [], blocks: refs.map((r, i) => ({ id: `b${i}`, kind: "image" as const, image: r, alt: "" })) }] }],
  };
  const bytes = enc.encode(JSON.stringify(pack)).buffer as ArrayBuffer;
  const dl: DownloadApi = {
    getPackBytes: vi.fn(async () => bytes.slice(0)),
    getAssetBlob: vi.fn(async (_t: string, _c: string, _v: number, path: string) => new NodeBlob([files[path]], { type: "image/png" }) as unknown as Blob),
  };
  return { pack, dl, refs };
}

describe("offline cache keyed by sha256", () => {
  let caches: ReturnType<typeof fakeCaches>;
  beforeEach(() => {
    caches = fakeCaches();
    vi.stubGlobal("caches", caches);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("a new version re-uses the files it shares with the old one", async () => {
    const store = cacheStore();
    const v1 = await packOf(1, { "a.png": "AAAA", "b.png": "BBBB" });
    await downloadCourse({ api: v1.dl, token: "t", store }, "c1", 1);
    expect(v1.dl.getAssetBlob).toHaveBeenCalledTimes(2);
    // v2 keeps the bytes of a.png under another path and replaces b.png
    const v2 = await packOf(2, { "x/a.png": "AAAA", "b2.png": "CCCC" });
    const m = await downloadCourse({ api: v2.dl, token: "t", store }, "c1", 2);
    expect(v2.dl.getAssetBlob).toHaveBeenCalledTimes(1);
    expect(m.complete).toBe(true);
    expect(await (await store.getAsset("c1", 2, v2.refs[0]))!.text()).toBe("AAAA");
  });

  it("migrates a copy stored under the old course/version/path key, and does not trust one that fails its hash", async () => {
    const cache = await caches.open("mentor-courses-v1");
    const { refs } = await packOf(1, { "a.png": "AAAA" });
    const old = "https://offline.mentor.invalid/c1/1/assets/a.png";
    await cache.put(old, new Response("AAAA", { headers: { "Content-Type": "image/png" } }));
    const store = cacheStore();
    expect(await (await store.getAsset("c1", 1, refs[0]))!.text()).toBe("AAAA");
    expect(await cache.match(old)).toBeUndefined(); // moved, not copied
    expect(await cache.match(`https://offline.mentor.invalid/sha/${refs[0].sha256}`)).toBeDefined();
    await cache.put("https://offline.mentor.invalid/c1/1/assets/z.png", new Response("EVIL"));
    expect(await store.getAsset("c1", 1, { ...refs[0], path: "z.png", sha256: "f".repeat(64) })).toBeNull();
  });

  it("remove() keeps blobs another course still uses and drops the rest", async () => {
    const store = cacheStore();
    const a = await packOf(1, { "a.png": "AAAA", "only1.png": "ONE" });
    await downloadCourse({ api: a.dl, token: "t", store }, "c1", 1);
    const b = await packOf(1, { "a.png": "AAAA" });
    await downloadCourse({ api: b.dl, token: "t", store }, "c2", 1);
    await store.remove("c1");
    expect(await store.getAsset("c2", 1, b.refs[0])).not.toBeNull(); // shared
    expect(await store.getAsset("c1", 1, a.refs[1])).toBeNull(); // only c1 used it
    expect(await store.getManifest("c1", 1)).toBeNull();
  });

  it("keeps the cover of a course seen in a list, enrolled or not", async () => {
    const store = memoryStore();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("IMG", { status: 200 })));
    vi.stubEnv("VITE_API_MOCK", "0");
    await cacheCover("tok", store, "seen-in-list");
    expect(await (await store.getCover("seen-in-list"))!.text()).toBe("IMG");
    vi.stubEnv("VITE_API_MOCK", "1");
  });
});

describe("progress outbox", () => {
  const body = (blocks: string[], block = "b1") => ({ lesson_id: "l1", block_id: block, completed_block_ids: blocks });
  const enrolment = { course_id: "c1", pinned_version: 1, enrolled_at: "2026-11-01T00:00:00Z", progress: null };
  beforeEach(() => writeMirror("u1", [enrolment]));
  afterEach(() => vi.restoreAllMocks());

  it("keeps progress that could not be sent and replays it later, quiz results included, in order", async () => {
    const put = vi.spyOn(api, "putProgress").mockRejectedValue(new ApiError(0, "network"));
    await saveProgress("t", "u1", "c1", body(["b0"]));
    await saveProgress("t", "u1", "c1", { ...body(["b0", "b1"], "b2"), quiz: { item_id: "q1", correct: true, seconds: 3 } });
    await saveProgress("t", "u1", "c1", { ...body(["b0", "b1"], "b2"), quiz: { item_id: "q2", correct: false, seconds: 5 } });
    expect(readOutbox("u1").c1.quizzes.map((q) => q.item_id)).toEqual(["q1", "q2"]);

    put.mockReset();
    put.mockResolvedValue({} as never);
    await flushOutbox("t", "u1"); // e.g. the `online` event, or app start
    expect(put.mock.calls.map((c) => (c[2] as { quiz?: { item_id: string } }).quiz?.item_id)).toEqual(["q1", "q2"]);
    expect(put.mock.calls[0][2]).toMatchObject({ block_id: "b2", completed_block_ids: ["b0", "b1"] });
    expect(readOutbox("u1")).toEqual({});
  });

  it("sends only the latest position when no quiz is waiting, and keeps what was not acknowledged", async () => {
    const put = vi.spyOn(api, "putProgress").mockRejectedValue(new ApiError(0, "network"));
    await saveProgress("t", "u1", "c1", body(["b0"], "b0"));
    await saveProgress("t", "u1", "c1", body(["b0", "b1"], "b1"));
    put.mockReset();
    put.mockResolvedValue({} as never);
    await flushOutbox("t", "u1");
    expect(put).toHaveBeenCalledTimes(1);
    expect(put.mock.calls[0][2]).toMatchObject({ block_id: "b1" });

    put.mockReset();
    put.mockRejectedValue(new ApiError(0, "network"));
    await saveProgress("t", "u1", "c1", { ...body(["b1"]), quiz: { item_id: "q1", correct: true, seconds: 1 } });
    await saveProgress("t", "u1", "c1", { ...body(["b1"]), quiz: { item_id: "q2", correct: true, seconds: 1 } });
    put.mockReset();
    put.mockResolvedValueOnce({} as never).mockRejectedValue(new ApiError(0, "network"));
    await flushOutbox("t", "u1");
    expect(readOutbox("u1").c1.quizzes.map((q) => q.item_id)).toEqual(["q2"]);
  });

  it("drops the entry when the server says the course is no longer enrolled", async () => {
    vi.spyOn(api, "putProgress").mockRejectedValueOnce(new ApiError(0, "network")).mockRejectedValue(new ApiError(404, "not_found"));
    await saveProgress("t", "u1", "c1", body(["b0"]));
    await flushOutbox("t", "u1");
    expect(readOutbox("u1")).toEqual({});
  });

  it("loading the list never shows older progress than the learner made", async () => {
    vi.spyOn(api, "putProgress").mockRejectedValue(new ApiError(0, "network"));
    await saveProgress("t", "u1", "c1", body(["b0", "b1"], "b1"));
    vi.spyOn(api, "listEnrollments").mockResolvedValue([{ ...enrolment, progress: { lesson_id: "l1", block_id: "b0", completed_block_ids: ["b0"] } }]);
    const { list } = await loadEnrollments("t", "u1");
    expect(list[0].progress).toMatchObject({ block_id: "b1", completed_block_ids: ["b0", "b1"] });
  });
});

describe("media token recovery", () => {
  beforeEach(() => vi.stubEnv("VITE_API_MOCK", "0"));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.stubEnv("VITE_API_MOCK", "1");
    setMediaTokenSource(null);
    setMediaToken(null);
  });
  const url = "http://localhost:8000/api/courses/c1/versions/1/assets/a.mp4?t=old";

  it("on 401 mints a new media token and returns the URL carrying it, once for concurrent callers", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 401 })));
    const mint = vi.fn(async () => "fresh");
    setMediaTokenSource(mint);
    const [a, b] = await Promise.all([recoverMediaUrl(url), recoverMediaUrl(url)]);
    expect(a).toBe("http://localhost:8000/api/courses/c1/versions/1/assets/a.mp4?t=fresh");
    expect(b).toBe(a);
    expect(mint).toHaveBeenCalledTimes(1);
  });

  it("does nothing for other failures, blob URLs, or when no one is signed in", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    setMediaTokenSource(async () => "fresh");
    expect(await recoverMediaUrl(url)).toBeNull();
    expect(await recoverMediaUrl("blob:http://x/1")).toBeNull();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 401 })));
    setMediaTokenSource(null);
    expect(await recoverMediaUrl(url)).toBeNull();
  });

  it("retryMedia swaps the src once, then gives up", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 401 })));
    setMediaTokenSource(async () => "fresh");
    const img = document.createElement("img");
    img.src = url;
    const giveUp = vi.fn();
    retryMedia(img, giveUp);
    await vi.waitFor(() => expect(img.src).toContain("t=fresh"));
    expect(giveUp).not.toHaveBeenCalled();
    retryMedia(img, giveUp); // failed again: no second round
    expect(giveUp).toHaveBeenCalledTimes(1);
  });

  it("retryMedia recovers again from a later expiry once the element has loaded", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 401 })));
    let n = 0;
    setMediaTokenSource(async () => `fresh${++n}`);
    const img = document.createElement("img");
    img.src = url;
    retryMedia(img);
    await vi.waitFor(() => expect(img.src).toContain("t=fresh1"));
    img.dispatchEvent(new Event("load")); // the new token worked; much later it expires too
    retryMedia(img);
    await vi.waitFor(() => expect(img.src).toContain("t=fresh2"));
  });
});
