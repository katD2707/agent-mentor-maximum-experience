import type { BuildState, CommentStatus, CourseStatus, TeacherCourseSummary, TeacherVersion } from "../../api/teacher";

export type Tone = "" | "ok" | "wait" | "err";

/** What the tag on a course row says, and the translation key + params for it. */
export interface StatusTag {
  tone: Tone;
  key: string;
  params?: Record<string, number>;
}

export function latestPublished(c: Pick<TeacherCourseSummary, "versions">): TeacherVersion | null {
  const pub = c.versions.filter((v) => v.status === "published");
  return pub.length ? pub.reduce((a, b) => (b.version > a.version ? b : a)) : null;
}

export function statusTag(c: TeacherCourseSummary): StatusTag {
  switch (c.status) {
    case "reading":
      return { tone: "wait", key: "gv.status.reading" };
    case "needs_retake":
      return { tone: "err", key: "gv.status.needsRetake" };
    case "outline_ready":
      return { tone: "", key: "gv.status.outlineReady" };
    case "building":
      return c.build && c.build.total > 0 ? { tone: "wait", key: "gv.status.buildingN", params: { done: c.build.done, total: c.build.total } } : { tone: "wait", key: "gv.status.building" };
    case "review":
      return { tone: "", key: "gv.status.review" };
    case "published": {
      const v = latestPublished(c);
      return { tone: "ok", key: "gv.status.published", params: { version: v?.version ?? c.latest_version, students: v?.students ?? 0 } };
    }
    case "revising":
      return { tone: "wait", key: "gv.status.revising", params: { version: c.latest_version } };
  }
}

/** Route a row opens. Reading has nothing to open yet. */
export function courseRoute(c: Pick<TeacherCourseSummary, "id" | "status" | "latest_version">): string | null {
  const id = encodeURIComponent(c.id);
  switch (c.status) {
    case "reading":
      return null;
    case "needs_retake":
    case "outline_ready":
    case "building":
      return `/khoa/${id}`;
    case "review":
    case "revising":
    case "published":
      return `/khoa/${id}/duyet?v=${c.latest_version}`;
  }
}

/** Per lesson build state -> label key, tone and whether it is the one being worked on. */
export function buildStateInfo(s: BuildState): { key: string; tone: "done" | "now" | "wait" | "err" } {
  switch (s) {
    case "done":
      return { key: "gv.build.done", tone: "done" };
    case "writing":
      return { key: "gv.build.writing", tone: "now" };
    case "media":
      return { key: "gv.build.media", tone: "now" };
    case "video":
      return { key: "gv.build.video", tone: "now" };
    case "failed":
      return { key: "gv.build.failed", tone: "err" };
    default:
      return { key: "gv.build.waiting", tone: "wait" };
  }
}

/** A comment is "đang sửa" until the agent applied it. */
export function commentStatusInfo(s: CommentStatus): { key: string; fixed: boolean; failed: boolean } {
  return { key: `gv.cstatus.${s === "applied" ? "applied" : s === "failed" ? "failed" : "working"}`, fixed: s === "applied", failed: s === "failed" };
}
export const commentPending = (s: CommentStatus) => s === "open" || s === "applying";

/** Statuses that mean "the agent finished a step and the teacher has something to do". */
const ATTENTION: ReadonlySet<CourseStatus> = new Set<CourseStatus>(["needs_retake", "outline_ready", "review"]);

export interface JobDone {
  id: string;
  title: string;
  status: CourseStatus;
}

/** Courses whose status just changed into a "your turn" status since the last look (not on the very first look). */
export function finishedJobs(prev: ReadonlyMap<string, CourseStatus> | null, list: readonly TeacherCourseSummary[]): JobDone[] {
  if (!prev) return [];
  const out: JobDone[] = [];
  for (const c of list) {
    const was = prev.get(c.id);
    if (was !== undefined && was !== c.status && ATTENTION.has(c.status)) out.push({ id: c.id, title: c.title, status: c.status });
  }
  return out;
}

export const statusMap = (list: readonly TeacherCourseSummary[]): Map<string, CourseStatus> => new Map(list.map((c) => [c.id, c.status]));
