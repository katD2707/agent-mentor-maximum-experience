import { describe, expect, it, vi } from "vitest";
import { ApiError, type CoursePack, type Progress, type QuizItem } from "./api";
import { makeMockCourseApi } from "./api/mock-course-api";
import { dienPack, taoPack } from "./api/mock-courses";
import { checkAnswer, checkShortAnswer, canSubmit, parseNumber } from "./lib/quiz";
import { allBlockIds, isFinished, lessonOrdinal, lessonPercent, pickToday, progressPercent, resumePosition, stars, stepsOf } from "./lib/courseProgress";
import { downloadCourse, loadPack, memoryStore, PackIntegrityError, type DownloadApi } from "./lib/offline";
import { packAssets } from "./lib/packAssets";
import { sha256Hex } from "./lib/hash";
import { renderMd } from "./lib/md";

const item = (id: string, pack: CoursePack = dienPack): QuizItem => {
  const all = pack.chapters.flatMap((c) => c.lessons).flatMap((l) => l.blocks);
  for (const b of all) if (b.kind === "quiz") for (const q of b.items) if (q.id === id) return q;
  throw new Error(id);
};

describe("answer checking", () => {
  it("SINGLE_CHOICE and PICTURE_CHOICE compare the option id and report the right one", () => {
    const single = item("l2-q1");
    expect(checkAnswer(single, { kind: "choice", id: "B" })).toEqual({ correct: true, correctOptionId: "B" });
    expect(checkAnswer(single, { kind: "choice", id: "A" })).toEqual({ correct: false, correctOptionId: "B" });
    const pic = item("l1-q2", taoPack);
    expect(checkAnswer(pic, { kind: "choice", id: "B" }).correct).toBe(true);
    expect(checkAnswer(pic, { kind: "choice", id: "C" }).correct).toBe(false);
  });

  it("TRUE_FALSE_GROUP needs every statement right and lists the wrong ones", () => {
    const tf = item("l2-q2");
    expect(checkAnswer(tf, { kind: "tf", values: { a: false, b: true, c: false } }).correct).toBe(true);
    const v = checkAnswer(tf, { kind: "tf", values: { a: true, b: true, c: false } });
    expect(v).toEqual({ correct: false, wrong: ["a"] });
    // a blank statement counts as wrong
    expect(checkAnswer(tf, { kind: "tf", values: { b: true } }).wrong).toEqual(["a", "c"]);
    expect(canSubmit(tf, { kind: "tf", values: { b: true } })).toBe(false);
    expect(canSubmit(tf, { kind: "tf", values: { a: false, b: true, c: false } })).toBe(true);
  });

  it("SHORT_ANSWER accepts listed forms, decimal commas and a relative tolerance", () => {
    const q = item("l2-q3"); // accepted ["1e5", "100000"], tolerance 0.01
    expect(checkAnswer(q, { kind: "text", value: "100000" }).correct).toBe(true);
    expect(checkAnswer(q, { kind: "text", value: " 1e5 " }).correct).toBe(true);
    expect(checkAnswer(q, { kind: "text", value: "100 000" }).correct).toBe(true);
    expect(checkAnswer(q, { kind: "text", value: "100500" }).correct).toBe(true); // within 1%
    expect(checkAnswer(q, { kind: "text", value: "102000" }).correct).toBe(false);
    expect(checkAnswer(q, { kind: "text", value: "" }).correct).toBe(false);
    expect(checkShortAnswer("0,5", ["0.5"])).toBe(true);
    expect(checkShortAnswer("Hà Nội", ["hà nội"])).toBe(true);
    expect(checkShortAnswer("0.51", ["0.5"])).toBe(false); // no tolerance given: exact
    expect(parseNumber("4·10^4")).toBe(40000);
    expect(parseNumber("abc")).toBeNull();
  });

  it("TAP_COUNT compares the tapped count", () => {
    const tap = item("l1-q1", taoPack); // count 5
    expect(checkAnswer(tap, { kind: "count", value: 5 }).correct).toBe(true);
    expect(checkAnswer(tap, { kind: "count", value: 4 }).correct).toBe(false);
    expect(canSubmit(tap, { kind: "count", value: 0 })).toBe(false);
  });
});

const progress = (over: Partial<Progress> = {}): Progress => ({ lesson_id: "l2", block_id: "l2-b3", completed_block_ids: [], ...over });

describe("progress and resume", () => {
  it("progress percent is completed blocks over all blocks in the pinned pack", () => {
    const all = allBlockIds(dienPack);
    expect(all).toHaveLength(2 + 8 + 1);
    expect(progressPercent(dienPack, null)).toBe(0);
    expect(progressPercent(dienPack, progress({ completed_block_ids: ["l1-b1", "l1-b2"] }))).toBe(18);
    expect(progressPercent(dienPack, progress({ completed_block_ids: [...all, "gone-block"] }))).toBe(100); // ids not in the pack are ignored
  });

  it("without the pack it falls back to lessons before the current one", () => {
    expect(progressPercent(null, progress({ lesson_id: "l2" }), 4, ["l1", "l2", "l3", "l4"])).toBe(25);
    expect(progressPercent(null, progress({ lesson_id: "l1" }), 4, ["l1", "l2", "l3", "l4"])).toBe(0);
  });

  it("lesson percent and finished", () => {
    const l2 = dienPack.chapters[0].lessons[1];
    expect(lessonPercent(l2, new Set(["l2-b1", "l2-b2"]))).toBe(25);
    expect(isFinished(dienPack, progress({ completed_block_ids: allBlockIds(dienPack) }))).toBe(true);
    expect(isFinished(dienPack, progress())).toBe(false);
  });

  it("resumes at the saved block, in the saved lesson", () => {
    expect(resumePosition(dienPack, progress({ lesson_id: "l2", block_id: "l2-b5" }))).toEqual({ lessonId: "l2", blockId: "l2-b5" });
  });

  it("falls back when the saved block or lesson no longer exists (new pack version)", () => {
    expect(resumePosition(dienPack, progress({ lesson_id: "l2", block_id: "removed" }))).toEqual({ lessonId: "l2", blockId: "l2-b1" });
    const done = dienPack.chapters[0].lessons[0].blocks.map((b) => b.id);
    expect(resumePosition(dienPack, progress({ lesson_id: "gone", block_id: "x", completed_block_ids: done }))).toEqual({ lessonId: "l2", blockId: "l2-b1" });
    expect(resumePosition(dienPack, null)).toEqual({ lessonId: "l1", blockId: "l1-b1" });
  });

  it("lesson ordinal, stars, today pick and kid steps", () => {
    expect(lessonOrdinal(["l1", "l2", "l3"], progress({ lesson_id: "l3" }))).toEqual({ n: 3, total: 3 });
    expect(lessonOrdinal(["l1", "l2"], null)).toEqual({ n: 1, total: 2 });
    expect([0, 38, 50, 100].map(stars)).toEqual([0, 2, 3, 5]);

    const e = (course_id: string, updated_at?: string) => ({ course_id, pinned_version: 1, enrolled_at: "", progress: updated_at ? { ...progress(), updated_at } : null });
    expect(pickToday([e("a"), e("b", "2026-11-02"), e("c", "2026-11-05")])?.course_id).toBe("c");
    expect(pickToday([e("a"), e("b", "2026-11-02")], new Set(["b"]))?.course_id).toBe("a");
    expect(pickToday([e("a")], new Set(["a"]))).toBeNull();

    // quiz blocks become one step per question
    const steps = stepsOf(taoPack.chapters[0].lessons[0]);
    expect(steps.map((s) => s.blockId)).toEqual(["l1-b1", "l1-b2", "l1-b3", "l1-b4"]);
  });
});

// ---------------------------------------------------------------- offline
const enc = new TextEncoder();

/** A tiny pack with two real assets, hashed for real, served by a fake API that counts calls. */
async function fixture(opts: { badAsset?: boolean; missing?: boolean } = {}) {
  const files: Record<string, Uint8Array> = { "images/a.png": enc.encode("AAAA"), "images/b.png": enc.encode("BBBBBB") };
  const ref = async (path: string) => ({ path, mime: "image/png", sha256: await sha256Hex(files[path]), bytes: files[path].byteLength });
  const pack: CoursePack = {
    schema_version: 1,
    course_id: "c1",
    version: 1,
    min_app_version: "0.1.0",
    language: "vi",
    age_band: "g10_12",
    title: "T",
    chapters: [
      {
        id: "ch",
        title: "Ch",
        lessons: [
          {
            id: "l1",
            title: "L",
            est_minutes: 5,
            key_ideas: [],
            blocks: [
              { id: "b1", kind: "image", image: await ref("images/a.png"), alt: "a" },
              { id: "b2", kind: "image", image: await ref("images/b.png"), alt: "b" },
              { id: "b3", kind: "image", image: await ref("images/a.png"), alt: "a again" },
            ],
          },
        ],
      },
    ],
  };
  if (opts.badAsset) files["images/a.png"] = enc.encode("tampered");
  const bytes = enc.encode(JSON.stringify(pack)).buffer as ArrayBuffer;
  const sha = await sha256Hex(bytes);
  const api: DownloadApi = {
    getPackBytes: vi.fn(async () => bytes.slice(0)),
    getAssetBlob: vi.fn(async (_t: string, _c: string, _v: number, path: string) => {
      if (opts.missing && path === "images/b.png") throw new ApiError(404, "not_found");
      return new Blob([files[path] as BlobPart], { type: "image/png" });
    }),
  };
  return { api, sha, pack };
}

describe("offline cache", () => {
  it("packAssets lists every asset once", async () => {
    const { pack } = await fixture();
    expect(packAssets(pack).map((a) => a.path)).toEqual(["images/a.png", "images/b.png"]);
  });

  it("downloads pack + assets, then the player loads from the cache without touching the network", async () => {
    const { api, sha } = await fixture();
    const store = memoryStore();
    const progress: number[] = [];
    const m = await downloadCourse({ api, token: "t", store, onProgress: (p) => progress.push(p.done) }, "c1", 1, sha);
    expect(m).toMatchObject({ complete: true, total: 2, stored: 2, missing: [] });
    expect(progress.at(-1)).toBe(2);
    expect(api.getAssetBlob).toHaveBeenCalledTimes(2);

    vi.mocked(api.getPackBytes).mockClear();
    vi.mocked(api.getAssetBlob).mockClear();
    URL.createObjectURL = vi.fn(() => "blob:cached");
    URL.revokeObjectURL = vi.fn();
    const loaded = await loadPack({ api, token: "t", store }, "c1", 1, sha);
    expect(loaded.source).toBe("cache");
    expect(loaded.cachedAssets).toBe(2);
    expect(loaded.url("images/a.png")).toBe("blob:cached");
    expect(api.getPackBytes).not.toHaveBeenCalled();
    expect(api.getAssetBlob).not.toHaveBeenCalled();
  });

  it("works with the network gone once downloaded", async () => {
    const { api, sha } = await fixture();
    const store = memoryStore();
    await downloadCourse({ api, token: "t", store }, "c1", 1, sha);
    const dead: DownloadApi = { getPackBytes: vi.fn().mockRejectedValue(new ApiError(0, "network")), getAssetBlob: vi.fn().mockRejectedValue(new ApiError(0, "network")) };
    URL.createObjectURL = vi.fn(() => "blob:x");
    const loaded = await loadPack({ api: dead, token: "t", store }, "c1", 1);
    expect(loaded.pack.title).toBe("T");
    expect(loaded.source).toBe("cache");
  });

  it("a cache miss goes to the network and falls back to the token URL for assets", async () => {
    vi.stubEnv("VITE_API_MOCK", "0"); // real URLs, not the bundled mock files
    const { api, sha } = await fixture();
    const loaded = await loadPack({ api, token: "tok", store: memoryStore() }, "c1", 1, sha);
    expect(loaded.source).toBe("network");
    expect(loaded.cachedAssets).toBe(0);
    expect(loaded.url("images/a.png")).toMatch(/\/courses\/c1\/versions\/1\/assets\/images\/a\.png\?t=tok$/);
    vi.stubEnv("VITE_API_MOCK", "1");
  });

  it("rejects a pack whose sha256 does not match", async () => {
    const { api } = await fixture();
    const store = memoryStore();
    await expect(downloadCourse({ api, token: "t", store }, "c1", 1, "f".repeat(64))).rejects.toBeInstanceOf(PackIntegrityError);
    expect(await store.getPack("c1", 1)).toBeNull();
    await expect(loadPack({ api, token: "t", store }, "c1", 1, "f".repeat(64))).rejects.toBeInstanceOf(PackIntegrityError);
  });

  it("skips an asset that is missing or fails its hash and reports a partial download", async () => {
    const bad = await fixture({ badAsset: true });
    const m1 = await downloadCourse({ api: bad.api, token: "t", store: memoryStore() }, "c1", 1, bad.sha);
    expect(m1.complete).toBe(false);
    expect(m1.missing).toEqual(["images/a.png"]);

    const gone = await fixture({ missing: true });
    const m2 = await downloadCourse({ api: gone.api, token: "t", store: memoryStore() }, "c1", 1, gone.sha);
    expect(m2).toMatchObject({ complete: false, stored: 1, missing: ["images/b.png"] });
  });

  it("remove() drops everything of a course", async () => {
    const { api, sha } = await fixture();
    const store = memoryStore();
    await downloadCourse({ api, token: "t", store }, "c1", 1, sha);
    await store.remove("c1");
    expect(await store.getPack("c1", 1)).toBeNull();
    expect(await store.getManifest("c1", 1)).toBeNull();
  });
});

describe("markdown and math", () => {
  it("renders KaTeX for $…$, $$…$$ and \\(…\\)", () => {
    const html = renderMd("Với $k = 9$ và \\(r\\).\n\n$$E = k\\frac{q}{r^2}$$");
    expect(html.match(/class="katex"/g)?.length).toBeGreaterThanOrEqual(2);
    expect(html).toContain("katex-display");
    expect(html).not.toContain("MATHPH");
  });

  it("leaves money-like dollars alone and escapes raw HTML, images and bad links", () => {
    expect(renderMd("Giá $5 và $6")).not.toContain("katex");
    const html = renderMd(["<script>alert(1)</script>", "![x](http://e/x.png) [a](javascript:alert(1)) [ok](https://example.com)"].join("\n\n"));
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("javascript:");
    expect(html).toContain('href="https://example.com"');
  });
});

describe("coming-soon placeholders (mock API)", () => {
  const api = makeMockCourseApi(() => ({ id: "u", role: "student", username: "u", display_name: "U", age_band: "g1_5", birth_year: 2018, language: null, theme: "system", quiet_until: null }));

  it("show up in the catalog and course page with a lesson tree, and cannot be added", async () => {
    const cat = await api.getCatalog("t", { all: true });
    const soon = cat.courses.filter((c) => c.status === "coming_soon");
    expect(soon.length).toBeGreaterThanOrEqual(3);
    expect(soon[0].published_at).toBeNull();
    const detail = await api.getCourse("t", soon[0].id);
    expect(detail.status).toBe("coming_soon");
    expect(detail.tree.flatMap((c) => c.lessons).length).toBe(soon[0].lessons_count);
    await expect(api.enroll("t", soon[0].id)).rejects.toMatchObject({ status: 409, code: "coming_soon" });
  });

  it("are found by search", async () => {
    const r = await api.search("t", "Toán 2", { all: true });
    expect(r.results.some((h) => h.status === "coming_soon")).toBe(true);
  });
});
