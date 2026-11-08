/** Teacher authoring contract (prefix /api/teacher). Names follow the gateway; see lib/teacher/outline.ts for the ops. */
import type { CoursePack } from "./course";

export type CourseStatus = "reading" | "needs_retake" | "outline_ready" | "building" | "review" | "published" | "revising";

/** Course difficulty: the agent suggests, the teacher confirms (CONTRACTS section 14). */
export type CourseLevel = "basic" | "intermediate" | "advanced";

export interface TeacherVersion {
  version: number;
  status: "draft" | "review" | "published" | string;
  students: number;
  level_suggested?: CourseLevel | null;
  level_confirmed?: CourseLevel | null;
}

export interface TeacherCourseSummary {
  id: string;
  title: string;
  status: CourseStatus;
  status_line_vi: string;
  status_line_en: string;
  cover_sha256?: string | null;
  /** only the mock sets this: a bundled image for the cover so the list has a picture without the gateway */
  cover_url?: string | null;
  updated_at: string;
  latest_version: number;
  versions: TeacherVersion[];
  build?: { done: number; total: number } | null;
  /** what students see (latest published) */
  level?: CourseLevel | null;
  /** of the working version (the open draft, else the latest published): the agent's guess and the teacher's pick */
  level_suggested?: CourseLevel | null;
  level_confirmed?: CourseLevel | null;
}

export interface OutlineLesson {
  id: string;
  title: string;
  est_minutes: number;
  grounded: boolean;
}
export interface OutlineChapter {
  id: string;
  title: string;
  lessons: OutlineLesson[];
}
export interface Outline {
  title: string;
  chapters: OutlineChapter[];
}

export interface RetakeItem {
  ref: string; // "<source_file>#<page>"
  source_file: string;
  page: number;
  reasons: string[];
  message_vi: string;
  message_en: string;
  thumb_url?: string | null;
}

export type BuildState = "waiting" | "writing" | "media" | "video" | "done" | "failed";
export interface BuildLesson {
  id: string;
  title: string;
  state: BuildState;
  note?: string | null;
}

export interface ChatMessage {
  id: string;
  role: "teacher" | "agent";
  kind: "text" | "outline" | "retake" | "build" | "notice";
  text?: string | null;
  text_en?: string | null;
  created_at: string;
}

export interface TeacherCourseDetail {
  course: TeacherCourseSummary;
  status: CourseStatus;
  outline: Outline | null;
  retake: RetakeItem[];
  build: { lessons: BuildLesson[] };
  chat: ChatMessage[];
  /** Newest app version students can have (gateway RELEASED_APP_VERSION); a draft needing more gets a notice in review. */
  released_app_version?: string;
}

/** Exactly the shapes of services/course-builder outline.py apply_outline_edits. */
export type OutlineOp =
  | { op: "rename"; id: string; title: string }
  | { op: "update"; id: string; summary?: string; est_minutes?: number; key_ideas?: string[] }
  | { op: "reorder"; ids: string[]; parent: string | null }
  | { op: "delete"; id: string }
  | { op: "add_lesson"; chapter: string; title: string; after?: string; index?: number; summary?: string; est_minutes?: number; key_ideas?: string[] }
  | { op: "add_chapter"; title: string; after?: string; index?: number }
  | { op: "move_lesson"; id: string; chapter: string; index?: number; after?: string }
  | { op: "merge"; ids: string[]; title?: string };

/** Where a comment points. text: character offsets in the block's text; time: seconds; point: fraction (0-1) of the image width and height. */
export type CommentAnchor =
  | { kind: "text"; start: number; end: number; quote: string }
  | { kind: "time"; t: number }
  | { kind: "point"; x: number; y: number };

export type CommentStatus = "open" | "applying" | "applied" | "failed";

export interface TeacherComment {
  id: string;
  block_id: string;
  anchor: CommentAnchor;
  body: string;
  status: CommentStatus;
  note?: string | null;
}

export interface CommentInput {
  block_id: string;
  anchor: CommentAnchor;
  body: string;
}

export type UploadProgress = (done: number, total: number) => void;

export interface TeacherApi {
  upload(token: string, files: File[], note?: string, onProgress?: UploadProgress): Promise<{ course_id: string; job_id: string }>;
  addMaterials(token: string, courseId: string, files: File[], replace?: string, onProgress?: UploadProgress): Promise<{ job_id: string }>;
  listCourses(token: string, since?: string): Promise<TeacherCourseSummary[]>;
  getCourse(token: string, courseId: string): Promise<TeacherCourseDetail>;
  chat(token: string, courseId: string, text: string): Promise<ChatMessage[]>;
  putOutline(token: string, courseId: string, ops: OutlineOp[]): Promise<Outline>;
  build(token: string, courseId: string): Promise<void>;
  getPack(token: string, courseId: string, version: number): Promise<CoursePack>;
  postComment(token: string, courseId: string, version: number, c: CommentInput): Promise<{ id: string; status: CommentStatus }>;
  listComments(token: string, courseId: string, version: number): Promise<TeacherComment[]>;
  publish(token: string, courseId: string, version: number): Promise<void>;
  /** PUT /courses/{id}/versions/{v}/level. On a published version a different level lands in the next draft (`new_version`). */
  setLevel(token: string, courseId: string, version: number, level: CourseLevel): Promise<{ version: number; new_version: boolean }>;
  /** POST /courses/{id}/versions: a new draft v+1 of a published course. Returns its number. */
  newVersion(token: string, courseId: string): Promise<number>;
  /** Retake thumbnail as an <img> src. */
  thumbSrc(token: string, url: string | null | undefined): string;
}
