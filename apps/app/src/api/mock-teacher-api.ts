import { ApiError } from "./types";
import type { CoursePack } from "./course";
import type {
  BuildLesson,
  ChatMessage,
  CommentStatus,
  CourseLevel,
  CourseStatus,
  Outline,
  RetakeItem,
  TeacherApi,
  TeacherComment,
  TeacherCourseDetail,
  TeacherCourseSummary,
  TeacherVersion,
} from "./teacher";
import { bayesPack, dienPack, mockCoverUrl, taoPack } from "./mock-courses";
import { applyOutlineOps, OutlineEditError, lessonCount } from "../lib/teacher/outline";

/**
 * In-browser mock of the teacher API. Progress is driven by the clock: every call first moves each course along
 * (reading -> outline -> building lesson by lesson -> review; comments open -> applying -> applied), so a screen that
 * polls sees things happen. State is kept in localStorage.
 */
export const mockTiming = {
  /** upload takes this long (progress reported in steps) */
  upload: 1400,
  /** reading the files */
  read: 7000,
  /** one lesson: writing, pictures, video */
  writing: 1800,
  media: 1600,
  video: 1800,
  /** a comment: waits, is applied */
  commentOpen: 1500,
  commentApply: 4500,
};
const lessonMs = () => mockTiming.writing + mockTiming.media + mockTiming.video;

const KEY = "mentor.mock.teacher";

interface MComment extends TeacherComment {
  at: number;
  version: number;
}
interface MCourse {
  id: string;
  title: string;
  status: CourseStatus;
  stageAt: number;
  updatedAt: number;
  files: string[];
  outline: Outline | null;
  retake: RetakeItem[];
  /** after a re-read: which retake refs it fixes, and the status to go back to */
  readFix?: { fixes: string[]; after: "needs_retake" | "outline_ready" };
  build: BuildLesson[];
  buildAt?: number;
  chat: ChatMessage[];
  versions: TeacherVersion[];
  /** what students see: the confirmed level of the latest published version */
  level?: CourseLevel | null;
  packs: Record<string, CoursePack>;
  comments: MComment[];
  seq: number;
}
export interface DB {
  courses: MCourse[];
}

const iso = (t: number) => new Date(t).toISOString();
let msgSeq = 0;
const msg = (_c: MCourse, role: ChatMessage["role"], kind: ChatMessage["kind"], text: string | null, at: number): ChatMessage => ({ id: `m${at}-${++msgSeq}`, role, kind, text, created_at: iso(at) });

// ------------------------------------------------------------------ fixtures
const TEMPLATE: Outline = {
  title: "",
  chapters: [
    { id: "ch-1", title: "Chương 1. Lực điện", lessons: [{ id: "dien-tich-dinh-luat-cu-long", title: "Điện tích, định luật Cu-lông", est_minutes: 20, grounded: true }] },
    {
      id: "ch-2",
      title: "Chương 2. Điện trường",
      lessons: [
        { id: "cuong-do-dien-truong", title: "Cường độ điện trường", est_minutes: 20, grounded: true },
        { id: "duong-suc-dien", title: "Đường sức điện", est_minutes: 20, grounded: true },
        { id: "dien-truong-deu", title: "Điện trường đều", est_minutes: 15, grounded: true },
      ],
    },
    {
      id: "ch-3",
      title: "Chương 3. Điện thế và tụ điện",
      lessons: [
        { id: "the-nang-dien", title: "Thế năng điện", est_minutes: 20, grounded: true },
        { id: "dien-the", title: "Điện thế, hiệu điện thế", est_minutes: 20, grounded: true },
        { id: "tu-dien", title: "Tụ điện", est_minutes: 20, grounded: true },
      ],
    },
  ],
};

const pageSvg = (kind: "blur" | "dark") =>
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    kind === "blur"
      ? '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 70 94"><defs><filter id="b"><feGaussianBlur stdDeviation="2.4"/></filter></defs><rect width="70" height="94" fill="#fff"/><g filter="url(#b)" fill="#7B7795"><rect x="8" y="10" width="50" height="5"/><rect x="8" y="22" width="54" height="3"/><rect x="8" y="30" width="46" height="3"/><rect x="8" y="38" width="52" height="3"/><rect x="8" y="50" width="30" height="22"/><rect x="8" y="80" width="50" height="3"/></g></svg>'
      : '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 70 94"><defs><linearGradient id="d" x1="0" y1="0" x2="1" y2="1"><stop offset=".35" stop-color="#fff" stop-opacity="0"/><stop offset=".6" stop-color="#1F1B3A" stop-opacity=".92"/></linearGradient></defs><rect width="70" height="94" fill="#fff"/><g fill="#7B7795"><rect x="8" y="10" width="50" height="5"/><rect x="8" y="22" width="54" height="3"/><rect x="8" y="30" width="46" height="3"/><rect x="8" y="38" width="52" height="3"/></g><rect width="70" height="94" fill="url(#d)"/></svg>',
  );

function retakePages(file: string): RetakeItem[] {
  return [
    { ref: `${file}#3`, source_file: file, page: 3, reasons: ["blurry"], message_vi: "Ảnh bị mờ, không đọc được chữ", message_en: "Blurry photo, the text is unreadable", thumb_url: pageSvg("blur") },
    { ref: `${file}#7`, source_file: file, page: 7, reasons: ["too_dark", "cropped"], message_vi: "Thiếu sáng, mất nửa trang dưới", message_en: "Too dark, half the page is missing", thumb_url: pageSvg("dark") },
  ];
}

/** A pack for an outline: every lesson reuses the content of one of the fixture lessons (ids made unique). */
export function packFromOutline(id: string, o: Outline): CoursePack {
  const src = dienPack.chapters.flatMap((c) => c.lessons);
  let n = 0;
  return {
    ...JSON.parse(JSON.stringify({ ...dienPack, chapters: [] })),
    course_id: id,
    version: 1,
    title: o.title,
    chapters: o.chapters.map((ch) => ({
      id: ch.id,
      title: ch.title,
      lessons: ch.lessons.map((l) => {
        const s = JSON.parse(JSON.stringify(src[n++ % src.length])) as CoursePack["chapters"][0]["lessons"][0];
        const pre = `${l.id}-`;
        const rename = new Map<string, string>();
        s.blocks.forEach((b) => (rename.set(b.id, pre + b.id), (b.id = pre + b.id)));
        s.blocks.forEach((b) => b.kind === "quiz" && b.items.forEach((it) => (it.id = pre + it.id)));
        return { ...s, id: l.id, title: l.title, est_minutes: l.est_minutes };
      }),
    })),
  };
}

const outlineOf = (p: CoursePack): Outline => ({
  title: p.title,
  chapters: p.chapters.map((c) => ({ id: c.id, title: c.title, lessons: c.lessons.map((l) => ({ id: l.id, title: l.title, est_minutes: l.est_minutes, grounded: true })) })),
});

function seed(now: number): DB {
  const base = () => ({ updatedAt: now, stageAt: now, seq: 0, comments: [] as MComment[], build: [] as BuildLesson[], retake: [] as RetakeItem[] });
  const chem: MCourse = {
    ...base(),
    id: "hoa-10-lien-ket",
    title: "Hóa 10: Liên kết hóa học",
    status: "reading",
    files: ["lien-ket-hoa-hoc.pptx"],
    outline: null,
    chat: [],
    versions: [],
    packs: {},
    readFix: undefined,
  };
  chem.chat = [msg(chem, "teacher", "text", "Slide 32 trang, Hóa 10, chương Liên kết hóa học. Cho lớp 10A1.", now - 4 * 60000)];

  const phys: MCourse = {
    ...base(),
    id: "vat-li-11-dien-truong",
    title: "Vật lí 11: Điện trường",
    status: "needs_retake",
    files: ["sach-vat-li-11.pdf"],
    outline: { ...TEMPLATE, title: "Vật lí 11: Điện trường" },
    retake: retakePages("sach-vat-li-11.pdf"),
    chat: [],
    versions: [],
    packs: {},
  };
  phys.chat = [
    msg(phys, "teacher", "text", "24 ảnh sách Vật lí 11, chương Điện trường. Cho lớp 11A2, các em học trung bình.", now - 50 * 60000),
    msg(phys, "agent", "text", "Mình chưa đọc được 2 trang. Các trang còn lại vẫn ổn, cấu trúc bên dưới đã dùng hết. Bạn chụp lại 2 trang này, mình sẽ bổ sung vào.", now - 40 * 60000),
    msg(phys, "agent", "retake", null, now - 40 * 60000),
    msg(phys, "agent", "text", "Mình chia thành 3 chương, 7 bài, mỗi bài khoảng 20 phút. Bạn sửa thẳng vào đây nếu chưa ưng.", now - 40 * 60000),
    msg(phys, "agent", "outline", null, now - 40 * 60000),
  ];

  const math: MCourse = {
    ...base(),
    id: taoPack.course_id,
    title: "Toán 1: Các số đến 10",
    status: "review",
    files: ["toan-1.pdf"],
    outline: outlineOf(taoPack),
    chat: [],
    versions: [{ version: 1, status: "draft", students: 0, level_suggested: "basic", level_confirmed: null }],
    packs: { "1": JSON.parse(JSON.stringify(taoPack)) },
  };
  math.chat = [msg(math, "agent", "notice", "Khóa đã soạn xong, chờ bạn xem lại.", now - 20 * 60000)];

  const bayes: MCourse = {
    ...base(),
    id: bayesPack.course_id,
    title: "Xác suất thống kê: Suy luận Bayes",
    status: "published",
    files: ["bayes.pdf"],
    outline: outlineOf(bayesPack),
    chat: [],
    versions: [{ version: 1, status: "published", students: 38, level_suggested: "advanced", level_confirmed: "advanced" }],
    level: "advanced",
    packs: { "1": JSON.parse(JSON.stringify(bayesPack)) },
  };
  return { courses: [chem, phys, math, bayes] };
}

// ------------------------------------------------------------------ storage + clock
let mem: DB | null = null;
export function load(): DB {
  if (mem) return mem;
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return (mem = JSON.parse(raw) as DB);
  } catch {
    /* fresh seed */
  }
  return (mem = seed(Date.now()));
}
function save(db: DB) {
  try {
    localStorage.setItem(KEY, JSON.stringify(db));
  } catch {
    /* ignore */
  }
}
/** Tests and "clear site data" start over. */
export function resetMockTeacher() {
  mem = null;
}

function finishReading(c: MCourse, now: number) {
  if (!c.outline) {
    c.outline = { ...TEMPLATE, title: c.title };
    const many = c.files.length >= 3;
    if (many) c.retake = retakePages(c.files[0]);
    c.chat.push(msg(c, "agent", "text", many ? "Mình chưa đọc được 2 trang. Các trang còn lại vẫn ổn, cấu trúc bên dưới đã dùng hết. Bạn chụp lại 2 trang này, mình sẽ bổ sung vào." : "Mình đã đọc xong tài liệu.", now));
    if (many) c.chat.push(msg(c, "agent", "retake", null, now));
    c.chat.push(msg(c, "agent", "text", `Mình chia thành ${TEMPLATE.chapters.length} chương, ${lessonCount(TEMPLATE)} bài, mỗi bài khoảng 20 phút. Bạn sửa thẳng vào đây nếu chưa ưng.`, now));
    c.chat.push(msg(c, "agent", "outline", null, now));
    c.status = many ? "needs_retake" : "outline_ready";
  } else {
    const fix = c.readFix ?? { fixes: [], after: "outline_ready" as const };
    c.retake = c.retake.filter((r) => !fix.fixes.includes(r.ref));
    c.status = c.retake.length ? "needs_retake" : "outline_ready";
    if (fix.fixes.length) c.chat.push(msg(c, "agent", "text", c.retake.length ? `Đã bổ sung trang vừa chụp vào khóa. Còn ${c.retake.length} trang cần chụp lại.` : "Đã bổ sung các trang vừa chụp vào khóa. Bạn xem lại cấu trúc rồi bấm Soạn nhé.", now));
  }
  c.readFix = undefined;
  c.stageAt = c.updatedAt = now;
}

function applyFix(c: MCourse, m: MComment) {
  const pack = c.packs[String(m.version)];
  if (!pack) return;
  for (const l of pack.chapters.flatMap((x) => x.lessons)) {
    const b = l.blocks.find((x) => x.id === m.block_id);
    if (!b) continue;
    if (m.anchor.kind === "text" && (b.kind === "text" || b.kind === "callout")) {
      const q = m.anchor.quote;
      b.md = b.md.includes(q) ? b.md.replace(q, `~~${q}~~ **${q}** (đã viết lại rõ hơn)`) : `${b.md}\n\n**Đã viết lại theo nhận xét.**`;
      m.note = "Đã viết lại đoạn này. Chữ gạch là bản cũ.";
    } else if (m.anchor.kind === "time") {
      const t = m.anchor.t;
      const f = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
      m.note = `Đã dựng lại đoạn ${f(Math.max(0, t - 6))}–${f(t + 6)}, chậm hơn một nửa.`;
    } else if (m.anchor.kind === "point") m.note = "Đã vẽ lại hình quanh chỗ bạn ghim.";
    else m.note = "Đã sửa.";
    return;
  }
  m.note = "Đã sửa.";
}

/** Move every course along to `now`. */
export function tick(db: DB, now: number) {
  for (const c of db.courses) {
    if (c.status === "reading" && now - c.stageAt >= mockTiming.read) finishReading(c, c.stageAt + mockTiming.read);
    if (c.status === "building" && c.buildAt !== undefined) {
      const elapsed = now - c.buildAt;
      const per = lessonMs();
      const idx = Math.floor(elapsed / per);
      const within = elapsed - idx * per;
      c.build.forEach((l, i) => {
        l.state = i < idx ? "done" : i > idx ? "waiting" : within < mockTiming.writing ? "writing" : within < mockTiming.writing + mockTiming.media ? "media" : "video";
      });
      if (idx >= c.build.length) {
        c.build.forEach((l) => (l.state = "done"));
        c.status = "review";
        const at = c.buildAt + c.build.length * per;
        c.stageAt = c.updatedAt = at;
        c.packs["1"] = packFromOutline(c.id, c.outline!);
        c.versions = [{ version: 1, status: "draft", students: 0, level_suggested: suggestLevel(c.outline!), level_confirmed: null }];
        c.chat.push(msg(c, "agent", "notice", "Khóa đã soạn xong, chờ bạn xem lại.", at));
      }
    }
    for (const m of c.comments) {
      if (m.status === "open" && now - m.at >= mockTiming.commentOpen) m.status = "applying";
      if (m.status === "applying" && now - m.at >= mockTiming.commentApply) {
        m.status = "applied";
        applyFix(c, m);
        c.updatedAt = now;
      }
    }
  }
}

function view(db: DB, now = Date.now()) {
  tick(db, now);
  save(db);
  return db;
}

const LINE: Record<CourseStatus, [string, string]> = {
  reading: ["Đang đọc tài liệu, thường mất 5–10 phút", "Reading the files, usually takes 5–10 minutes"],
  needs_retake: ["Cấu trúc đã xong, có trang chưa đọc được", "Outline is ready, some pages are unreadable"],
  outline_ready: ["Đề xuất cấu trúc khóa học, chờ bạn xem", "An outline is proposed, waiting for your review"],
  building: ["Đang soạn từng bài", "Composing the lessons"],
  review: ["Đã soạn xong, chờ bạn xem lại", "Composed, ready for your review"],
  published: ["Đã xuất bản", "Published"],
  revising: ["Đang sửa bản mới", "Editing a new version"],
};

/** The mock's stand-in for the builder's suggestion: longer outlines read as harder. */
function suggestLevel(o: Outline): CourseLevel {
  const n = o.chapters.reduce((m, ch) => m + ch.lessons.length, 0);
  return n <= 4 ? "basic" : n <= 9 ? "intermediate" : "advanced";
}

function workingVersion(c: MCourse): TeacherVersion | undefined {
  const open = c.versions.filter((v) => v.status !== "published");
  const pool = open.length ? open : c.versions;
  return pool.reduce<TeacherVersion | undefined>((a, v) => (!a || v.version > a.version ? v : a), undefined);
}

function levelOf(c: MCourse) {
  const w = workingVersion(c);
  return { level: c.level ?? null, level_suggested: w?.level_suggested ?? null, level_confirmed: w?.level_confirmed ?? (w?.status === "published" ? (c.level ?? null) : null) };
}

function summary(c: MCourse): TeacherCourseSummary {
  const total = c.build.length;
  const lineVi = c.status === "needs_retake" ? `Cấu trúc ${lessonCount(c.outline!)} bài đã xong, ${c.retake.length} trang chưa đọc được` : LINE[c.status][0];
  const lineEn = c.status === "needs_retake" ? `Outline of ${lessonCount(c.outline!)} lessons is ready, ${c.retake.length} pages unreadable` : LINE[c.status][1];
  return {
    id: c.id,
    title: c.title,
    status: c.status,
    status_line_vi: lineVi,
    status_line_en: lineEn,
    cover_sha256: null,
    cover_url: mockCoverUrl(c.id),
    updated_at: iso(c.updatedAt),
    latest_version: c.versions.reduce((m, v) => Math.max(m, v.version), 0),
    versions: c.versions.map((v) => ({ ...v })),
    ...levelOf(c),
    build: c.status === "building" || total ? { done: c.build.filter((l) => l.state === "done").length, total } : null,
  };
}

function get(db: DB, id: string): MCourse {
  const c = db.courses.find((x) => x.id === id);
  if (!c) throw new ApiError(404, "not_found");
  return c;
}
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function nameOf(files: File[]): string {
  const imgs = files.filter((f) => f.type.startsWith("image/") || /\.(jpe?g|png|heic|webp)$/i.test(f.name));
  if (imgs.length >= 2) return `Khóa mới từ ${files.length} ảnh`;
  const n = files[0]?.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ").trim();
  return n ? n.charAt(0).toUpperCase() + n.slice(1) : "Khóa mới";
}

async function simulateUpload(files: File[], onProgress?: (d: number, t: number) => void) {
  const total = Math.max(1, files.reduce((n, f) => n + f.size, 0));
  const steps = 10;
  for (let i = 1; i <= steps; i++) {
    await wait(mockTiming.upload / steps);
    onProgress?.(Math.round((total * i) / steps), total);
  }
}

/** Understands "gộp bài 5 và 6", "xóa bài 3", "thêm bài X"; anything else is noted without a change. */
function interpret(o: Outline, text: string): { ops: Parameters<typeof applyOutlineOps>[1]; reply: string } {
  const flat = o.chapters.flatMap((c) => c.lessons);
  const lesson = (n: string) => flat[Number(n) - 1];
  let m = /(?:g[ộo]p|merge)\s+(?:b[àa]i|lessons?)?\s*(\d+)\s*(?:v[àa]|and|,|&)\s*(?:b[àa]i\s*)?(\d+)/i.exec(text);
  if (m && lesson(m[1]) && lesson(m[2])) return { ops: [{ op: "merge", ids: [lesson(m[1]).id, lesson(m[2]).id] }], reply: `Đã gộp bài ${m[1]} và bài ${m[2]}.` };
  m = /(?:x[óo]a|delete|remove)\s+(?:b[àa]i|lesson)?\s*(\d+)/i.exec(text);
  if (m && lesson(m[1])) return { ops: [{ op: "delete", id: lesson(m[1]).id }], reply: `Đã xóa bài ${m[1]}.` };
  m = /(?:th[êe]m|add)\s+(?:b[àa]i|lesson)\s+(.+)/i.exec(text);
  if (m) return { ops: [{ op: "add_lesson", chapter: o.chapters[o.chapters.length - 1].id, title: m[1].trim() }], reply: `Đã thêm bài "${m[1].trim()}" vào chương cuối.` };
  return { ops: [], reply: "Mình đã ghi nhận. Mình sẽ cân nhắc yêu cầu này khi soạn từng bài." };
}

export const mockTeacherApi: TeacherApi = {
  async upload(_token, files, note, onProgress) {
    await simulateUpload(files, onProgress);
    const db = load();
    const now = Date.now();
    const title = nameOf(files);
    let id = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "khoa";
    id = `${id}-${now.toString(36)}`;
    const c: MCourse = {
      id,
      title,
      status: "reading",
      stageAt: now,
      updatedAt: now,
      files: files.map((f) => f.name),
      outline: null,
      retake: [],
      build: [],
      chat: [],
      versions: [],
      packs: {},
      comments: [],
      seq: 0,
    };
    c.chat.push(msg(c, "teacher", "text", `${files.length} tệp${note ? `. ${note}` : ""}`, now));
    db.courses.unshift(c);
    save(db);
    return { course_id: id, job_id: `job-${now}` };
  },
  async addMaterials(_token, id, files, replace, onProgress) {
    await simulateUpload(files, onProgress);
    const db = view(load());
    const c = get(db, id);
    const now = Date.now();
    c.status = "reading";
    c.stageAt = c.updatedAt = now;
    c.readFix = { fixes: replace ? [replace] : [], after: "outline_ready" };
    c.files.push(...files.map((f) => f.name));
    c.chat.push(msg(c, "teacher", "text", replace ? `Chụp lại ${replace.replace(/^.*#/, "trang ")}` : `Thêm ${files.length} tệp`, now));
    save(db);
    return { job_id: `job-${now}` };
  },
  async listCourses() {
    await wait(60);
    return view(load()).courses.map(summary);
  },
  async getCourse(_token, id) {
    await wait(60);
    const c = get(view(load()), id);
    const detail: TeacherCourseDetail = {
      course: summary(c),
      status: c.status,
      outline: clone(c.outline),
      retake: clone(c.retake),
      build: { lessons: clone(c.build) },
      chat: clone(c.chat),
    };
    return detail;
  },
  async chat(_token, id, text) {
    await wait(120);
    const db = view(load());
    const c = get(db, id);
    const now = Date.now();
    const mine = msg(c, "teacher", "text", text, now);
    let reply: string;
    if ((c.status === "needs_retake" || c.status === "outline_ready") && c.outline) {
      const r = interpret(c.outline, text);
      try {
        if (r.ops.length) c.outline = applyOutlineOps(c.outline, r.ops);
        reply = r.reply;
      } catch (e) {
        reply = e instanceof OutlineEditError ? "Mình chưa sửa được yêu cầu này, bạn thử nói cách khác nhé." : "Có lỗi xảy ra.";
      }
    } else reply = "Mình đang soạn khóa nên chưa sửa cấu trúc được. Bạn nhận xét trong màn xem lại sau khi soạn xong nhé.";
    const agent = msg(c, "agent", "text", reply, now + 1);
    c.chat.push(mine, agent);
    c.updatedAt = now;
    save(db);
    return [mine, agent];
  },
  async putOutline(_token, id, ops) {
    await wait(60);
    const db = view(load());
    const c = get(db, id);
    if (!c.outline || (c.status !== "needs_retake" && c.status !== "outline_ready")) throw new ApiError(409, "unknown");
    try {
      c.outline = applyOutlineOps(c.outline, ops);
    } catch (e) {
      if (e instanceof OutlineEditError) throw new ApiError(422, "unknown");
      throw e;
    }
    c.updatedAt = Date.now();
    save(db);
    return clone(c.outline);
  },
  async build(_token, id) {
    await wait(80);
    const db = view(load());
    const c = get(db, id);
    if (!c.outline || (c.status !== "needs_retake" && c.status !== "outline_ready")) throw new ApiError(409, "unknown");
    const now = Date.now();
    c.build = c.outline.chapters.flatMap((ch) => ch.lessons).map((l) => ({ id: l.id, title: l.title, state: "waiting" as const }));
    c.buildAt = now;
    c.status = "building";
    c.stageAt = c.updatedAt = now;
    c.chat.push(msg(c, "teacher", "text", "Soạn theo cấu trúc này", now), msg(c, "agent", "build", `Đang soạn ${c.build.length} bài. Bạn có thể đóng app, xong mình sẽ báo để bạn xem lại.`, now));
    tick(db, now);
    save(db);
  },
  async getPack(_token, id, v) {
    await wait(60);
    const c = get(view(load()), id);
    const p = c.packs[String(v)];
    if (!p) throw new ApiError(404, "not_found");
    return clone(p);
  },
  async postComment(_token, id, v, input) {
    await wait(60);
    const db = view(load());
    const c = get(db, id);
    if (!c.packs[String(v)]) throw new ApiError(404, "not_found");
    const now = Date.now();
    const m: MComment = { id: `c${++c.seq}-${now.toString(36)}`, block_id: input.block_id, anchor: input.anchor, body: input.body, status: "open", at: now, version: v };
    c.comments.push(m);
    save(db);
    return { id: m.id, status: m.status as CommentStatus };
  },
  async listComments(_token, id, v) {
    await wait(40);
    const c = get(view(load()), id);
    return c.comments.filter((m) => m.version === v).map(({ at: _a, version: _v, ...m }) => (void _a, void _v, { ...m }));
  },
  async publish(_token, id, v) {
    await wait(80);
    const db = view(load());
    const c = get(db, id);
    const ver = c.versions.find((x) => x.version === v);
    if (!ver) throw new ApiError(404, "not_found");
    if (ver.status !== "published" && !ver.level_confirmed) throw new ApiError(409, "unknown") // level_unconfirmed;
    ver.status = "published";
    c.level = ver.level_confirmed ?? c.level;
    c.status = "published";
    c.updatedAt = Date.now();
    save(db);
  },
  async setLevel(_token, id, v, level) {
    await wait(60);
    const db = view(load());
    const c = get(db, id);
    let ver = c.versions.find((x) => x.version === v);
    if (!ver) throw new ApiError(404, "not_found");
    let created = false;
    if (ver.status === "published") {
      if (level === (ver.level_confirmed ?? c.level)) return { version: v, new_version: false };
      const open = c.versions.filter((x) => x.status !== "published");
      if (open.length) ver = open.reduce((a, b) => (b.version > a.version ? b : a));
      else {
        const next = v + 1;
        ver = { version: next, status: "draft", students: 0, level_suggested: ver.level_suggested ?? null, level_confirmed: ver.level_confirmed ?? c.level ?? null };
        c.versions.push(ver);
        c.packs[String(next)] = { ...clone(c.packs[String(v)]), version: next };
        c.status = "revising";
        created = true;
      }
    }
    ver.level_confirmed = level;
    c.updatedAt = Date.now();
    save(db);
    return { version: ver.version, new_version: created };
  },
  async newVersion(_token, id) {
    await wait(80);
    const db = view(load());
    const c = get(db, id);
    const latest = c.versions.reduce((m, v) => Math.max(m, v.version), 0);
    if (!latest || c.versions.find((v) => v.version === latest)?.status !== "published") throw new ApiError(409, "unknown");
    const next = latest + 1;
    const cur = c.versions.find((v) => v.version === latest);
    c.versions.push({ version: next, status: "draft", students: 0, level_suggested: cur?.level_suggested ?? null, level_confirmed: cur?.level_confirmed ?? c.level ?? null });
    c.packs[String(next)] = { ...clone(c.packs[String(latest)]), version: next };
    c.status = "revising";
    c.updatedAt = Date.now();
    save(db);
    return next;
  },
  thumbSrc: (_t, url) => url ?? "",
};
