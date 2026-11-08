import { ApiError, type Api, type User } from "./types";
import type { Catalog, CatalogEntry, CatalogItem, CourseDetail, Enrollment, SearchHit } from "./course";
import { queryEntries, suggestFrom } from "./catalogEngine";
import { FIXTURES, mockAssetUrl, treeOf } from "./mock-courses";
import { SOON } from "./mock-soon";
import { packAssets } from "../lib/packAssets";
import { sha256Hex } from "../lib/hash";
import { fold } from "../lib/text";

const delay = () => new Promise((r) => setTimeout(r, 90));
const enc = new TextEncoder();

/** Real hashes for the fixtures, computed once: asset refs are patched in place, then pack.json is hashed. */
interface Built {
  bytes: ArrayBuffer;
  sha: string;
}
let built: Promise<Map<string, Built>> | null = null;
function build(): Promise<Map<string, Built>> {
  built ??= (async () => {
    const out = new Map<string, Built>();
    for (const { pack, meta } of FIXTURES) {
      for (const a of packAssets(pack)) {
        const url = mockAssetUrl(pack.course_id, a.path);
        if (!url) continue;
        try {
          const b = await (await fetch(url)).arrayBuffer();
          a.sha256 = await sha256Hex(b);
          a.bytes = b.byteLength;
        } catch {
          /* leave the placeholder hash; the asset just will not verify */
        }
      }
      const bytes = enc.encode(JSON.stringify(pack)).buffer as ArrayBuffer;
      const sha = await sha256Hex(bytes);
      out.set(pack.course_id, { bytes, sha });
      meta.versions[0].pack_sha256 = sha;
      meta.versions[0].pack_bytes = bytes.byteLength;
    }
    return out;
  })();
  return built;
}

/** Mock enrollment counts ("x học sinh đang học"); placeholders have none. */
const STUDENTS: Record<string, number> = { "toan-1-dem-tao": 412, "vat-li-11-dien-truong": 286, "xac-suat-bayes": 94 };

type Entry = CatalogItem & { _text: string };

async function entries(): Promise<Entry[]> {
  const b = await build();
  const soon: Entry[] = SOON.map(({ meta, tree }) => ({
    id: meta.id,
    title: meta.title,
    subject: meta.subject,
    age_band: meta.age_band,
    language: meta.language,
    teacher_name: meta.teacher_name,
    description_short: meta.description_short,
    outcomes: meta.outcomes,
    cover_sha256: "0".repeat(64),
    media: meta.media,
    lessons_count: meta.lessons_count,
    est_minutes: meta.est_minutes,
    version: 0,
    pack_sha256: "",
    pack_bytes: 0,
    published_at: null,
    status: "coming_soon",
    level: meta.level ?? null,
    students: 0,
    _text: fold([meta.title, meta.subject, meta.description_short, ...meta.outcomes, ...tree.flatMap((c) => [c.title, ...c.lessons.map((l) => l.title)])].join(" \n ")),
  }));
  const live: Entry[] = FIXTURES.map(({ meta, pack }) => ({
    id: meta.id,
    title: meta.title,
    subject: meta.subject,
    age_band: meta.age_band,
    language: meta.language,
    teacher_name: meta.teacher_name,
    description_short: meta.description_short,
    outcomes: meta.outcomes,
    cover_sha256: "0".repeat(64),
    media: meta.media,
    lessons_count: meta.lessons_count,
    est_minutes: meta.est_minutes,
    version: 1,
    pack_sha256: b.get(meta.id)!.sha,
    pack_bytes: b.get(meta.id)!.bytes.byteLength,
    published_at: meta.versions[0].published_at ?? "",
    level: meta.level ?? null,
    students: STUDENTS[meta.id] ?? 0,
    _text: fold(
      [meta.title, meta.subject, meta.description_short, ...meta.outcomes, ...pack.chapters.flatMap((c) => [c.title, ...c.lessons.flatMap((l) => [l.title, l.summary ?? "", ...l.key_ideas])])].join(" \n "),
    ),
  }));
  return [...live, ...soon];
}
const strip = ({ _text, ...e }: Entry): CatalogItem => (void _text, e);
const plain = ({ students, ...e }: CatalogItem): CatalogEntry => (void students, e);

export function makeMockCourseApi(userOf: (token: string) => User) {
  const key = (token: string) => `mentor.mock.enroll.${userOf(token).id}`;
  const write = (token: string, list: Enrollment[]) => {
    try {
      localStorage.setItem(key(token), JSON.stringify(list));
    } catch {
      /* ignore */
    }
  };
  const read = (token: string): Enrollment[] => {
    try {
      const raw = localStorage.getItem(key(token));
      if (raw) return JSON.parse(raw) as Enrollment[];
    } catch {
      /* fall through */
    }
    // first visit: start with the courses of the learner's own age band, with some progress made
    const band = userOf(token).age_band ?? "g10_12";
    const mine = FIXTURES.filter((f) => f.meta.age_band === band);
    const list = (mine.length ? mine : FIXTURES.filter((f) => f.meta.age_band === "g10_12")).map(({ meta, pack }): Enrollment => {
      const lessons = pack.chapters[0].lessons;
      const at = Math.min(1, lessons.length - 1);
      const l = lessons[at];
      const done = lessons.slice(0, at).flatMap((x) => x.blocks.map((b) => b.id));
      return { course_id: meta.id, pinned_version: 1, enrolled_at: "2026-11-01T08:00:00Z", progress: { lesson_id: l.id, block_id: l.blocks[0].id, completed_block_ids: done } };
    });
    write(token, list);
    return list;
  };
  const fixture = (id: string) => {
    const f = FIXTURES.find((x) => x.meta.id === id);
    if (!f) throw new ApiError(404, "not_found");
    return f;
  };

  const course: Pick<Api, "mediaToken" | "getCatalog" | "getCourse" | "search" | "queryCatalog" | "suggest" | "listEnrollments" | "enroll" | "putProgress" | "unenroll" | "getPackBytes" | "getAssetBlob"> = {
    async mediaToken() {
      return "mock-media";
    },
    async getCatalog(token, opts) {
      await delay();
      const band = opts?.all ? null : (opts?.age_band ?? userOf(token).age_band);
      const courses = (await entries()).filter((e) => !band || e.age_band === band).map((e) => plain(strip(e)));
      return { schema_version: 1, generated_at: new Date().toISOString(), courses } satisfies Catalog;
    },
    async getCourse(token, id) {
      await delay();
      userOf(token);
      await build();
      const s = SOON.find((x) => x.meta.id === id);
      if (s) return { ...s.meta, tree: s.tree } satisfies CourseDetail;
      const f = fixture(id);
      return { ...f.meta, tree: treeOf(f.pack) } satisfies CourseDetail;
    },
    async search(token, q, opts) {
      await delay();
      const words = fold(q).split(/\s+/).filter(Boolean);
      const run = async (band: string | null): Promise<SearchHit[]> => {
        const scored = (await entries())
          .filter((e) => !band || e.age_band === band)
          .map((e) => {
            const title = fold(e.title);
            let score = 0;
            const matched: string[] = [];
            for (const w of words) {
              if (!e._text.includes(w)) continue;
              matched.push(w);
              score += title.includes(w) ? 3 : 1;
            }
            return { e, score, ok: words.length > 0 && matched.length === words.length, matched };
          })
          .filter((x) => x.ok)
          .sort((a, b) => b.score - a.score);
        return scored.map((x) => ({ ...strip(x.e), score: x.score }));
      };
      const band = opts?.all ? null : (opts?.age_band ?? userOf(token).age_band);
      const results = await run(band);
      return { results, suggested_all_ages: results.length === 0 && band ? (await run(null)).length > 0 : false };
    },
    async queryCatalog(token, query) {
      await delay();
      userOf(token);
      return queryEntries((await entries()).map(strip), query);
    },
    async suggest(token, q) {
      await delay();
      userOf(token);
      return suggestFrom((await entries()).map(strip), q);
    },
    async listEnrollments(token) {
      await delay();
      return read(token);
    },
    async enroll(token, courseId) {
      await delay();
      if (SOON.some((x) => x.meta.id === courseId)) throw new ApiError(409, "coming_soon");
      fixture(courseId);
      const list = read(token);
      let e = list.find((x) => x.course_id === courseId);
      if (!e) {
        e = { course_id: courseId, pinned_version: 1, enrolled_at: new Date().toISOString(), progress: null };
        write(token, [...list, e]);
      }
      return e;
    },
    async putProgress(token, courseId, body) {
      await delay();
      const list = read(token);
      const e = list.find((x) => x.course_id === courseId);
      if (!e) throw new ApiError(404, "not_found");
      e.progress = { lesson_id: body.lesson_id, block_id: body.block_id, completed_block_ids: body.completed_block_ids, updated_at: new Date().toISOString() };
      write(token, list);
      return e;
    },
    async unenroll(token, courseId) {
      await delay();
      write(token, read(token).filter((x) => x.course_id !== courseId));
    },
    async getPackBytes(token, courseId, version) {
      await delay();
      userOf(token);
      const b = (await build()).get(fixture(courseId).meta.id);
      if (!b || version !== 1) throw new ApiError(404, "not_found");
      return b.bytes.slice(0);
    },
    async getAssetBlob(token, courseId, _version, path) {
      userOf(token);
      const url = mockAssetUrl(courseId, path);
      if (!url) throw new ApiError(404, "not_found");
      try {
        return await (await fetch(url)).blob();
      } catch {
        throw new ApiError(0, "network");
      }
    },
  };
  return course;
}
