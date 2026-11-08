/** Hand-written mirror of packages/mentor-schemas/src/mentor_schemas/course.py (names kept). */
import type { AgeBand, Lang } from "./types";

export type Media = "video" | "reading" | "quiz" | "audio" | "interactive";

export interface AssetRef {
  path: string;
  mime: string;
  sha256: string;
  bytes: number;
}

export type QuizType = "SINGLE_CHOICE" | "TRUE_FALSE_GROUP" | "SHORT_ANSWER" | "PICTURE_CHOICE" | "TAP_COUNT";

export interface QuizOption {
  id: string;
  text?: string | null;
  image?: AssetRef | null;
  audio?: AssetRef | null;
}

export interface TrueFalseStatement {
  id: string;
  text: string;
}

export interface TapTarget {
  image: AssetRef;
  total: number;
}

/**
 * answer_key by type:
 *   SINGLE_CHOICE / PICTURE_CHOICE  {correct_option_id}
 *   TRUE_FALSE_GROUP                {statements: {a: true, ...}}
 *   SHORT_ANSWER                    {accepted: string[], tolerance?: number}
 *   TAP_COUNT                       {count}
 */
export interface QuizItem {
  id: string;
  type: QuizType;
  stem: string;
  stem_audio?: AssetRef | null;
  stem_image?: AssetRef | null;
  options: QuizOption[];
  statements: TrueFalseStatement[];
  tap?: TapTarget | null;
  answer_key: Record<string, unknown>;
  hint?: string | null;
  explanation: string;
  option_feedback: Record<string, string>;
  skill_ids: string[];
  difficulty: number;
}

export interface TextBlock {
  id: string;
  kind: "text";
  md: string;
  audio?: AssetRef | null;
}
export interface CalloutBlock {
  id: string;
  kind: "callout";
  variant: "remember" | "definition" | "example" | "tip" | "mistake";
  title?: string | null;
  md: string;
  audio?: AssetRef | null;
}
export interface ImageBlock {
  id: string;
  kind: "image";
  image: AssetRef;
  alt: string;
  caption?: string | null;
  audio?: AssetRef | null;
  /** credit of a picture taken from the web; absent for pictures we drew */
  attribution?: ImageAttribution | null;
}
export interface ImageAttribution {
  provider?: string | null;
  title?: string | null;
  author?: string | null;
  license?: string | null;
  license_url?: string | null;
  source_url?: string | null;
}
export interface VideoBlock {
  id: string;
  kind: "video";
  video: AssetRef;
  poster?: AssetRef | null;
  captions?: AssetRef | null;
  duration_s: number;
  title?: string | null;
}
export interface AudioBlock {
  id: string;
  kind: "audio";
  audio: AssetRef;
  transcript: string;
}
export interface QuizBlock {
  id: string;
  kind: "quiz";
  title?: string | null;
  items: QuizItem[];
}
export type Block = TextBlock | CalloutBlock | ImageBlock | VideoBlock | AudioBlock | QuizBlock;

export interface Lesson {
  id: string;
  title: string;
  est_minutes: number;
  summary?: string | null;
  key_ideas: string[];
  blocks: Block[];
}
export interface Chapter {
  id: string;
  title: string;
  lessons: Lesson[];
}

export interface CoursePack {
  schema_version: 1;
  course_id: string;
  version: number;
  min_app_version: string;
  language: Lang;
  age_band: AgeBand;
  title: string;
  chapters: Chapter[];
}

export interface VersionInfo {
  version: number;
  status: "draft" | "review" | "published";
  created_at: string;
  published_at?: string | null;
  pack_sha256?: string | null;
  pack_bytes?: number | null;
  note?: string | null;
}

/** "coming_soon": a placeholder overview with a lesson tree and no content; it cannot be added. Absent means "live". */
export type CatalogStatus = "live" | "coming_soon";

/** Difficulty the teacher confirmed when publishing (or set for a placeholder); null for older courses. */
export type Level = "basic" | "intermediate" | "advanced";

export interface CourseMeta {
  schema_version: 1;
  id: string;
  title: string;
  subject: string;
  age_band: AgeBand;
  language: Lang;
  teacher_id: string;
  teacher_name: string;
  description_short: string;
  outcomes: string[];
  cover: string;
  media: Media[];
  lessons_count: number;
  est_minutes: number;
  latest_published?: number | null;
  versions: VersionInfo[];
  status?: CatalogStatus;
  level?: Level | null;
}

export interface CatalogEntry {
  id: string;
  title: string;
  subject: string;
  age_band: AgeBand;
  language: Lang;
  teacher_name: string;
  description_short: string;
  outcomes: string[];
  cover_sha256: string;
  media: Media[];
  lessons_count: number;
  est_minutes: number;
  version: number;
  pack_sha256: string;
  pack_bytes: number;
  published_at: string | null;
  status?: CatalogStatus;
  level?: Level | null;
  /** enrollment count (GET /catalog/query and /search only) */
  students?: number;
}

export interface Catalog {
  schema_version: 1;
  generated_at: string;
  courses: CatalogEntry[];
}

/** Light tree of a course (chapters, lessons, key ideas) returned with CourseMeta by GET /courses/{id}. */
export interface TreeLesson {
  id: string;
  title: string;
  est_minutes: number;
  summary?: string | null;
  key_ideas: string[];
  media?: Media[];
}
export interface TreeChapter {
  id: string;
  title: string;
  lessons: TreeLesson[];
}
export interface CourseDetail extends CourseMeta {
  tree: TreeChapter[];
}

// ---- enrollments and progress (§3.3)
export interface QuizResult {
  item_id: string;
  correct: boolean;
  seconds: number;
}

export interface ProgressBody {
  lesson_id: string;
  block_id: string;
  completed_block_ids: string[];
  quiz?: QuizResult;
}

export interface Progress extends ProgressBody {
  updated_at?: string;
}

export interface Enrollment {
  course_id: string;
  pinned_version: number;
  enrolled_at: string;
  /** a newer published version exists; the learner stays pinned (never auto-switch) */
  update_available?: boolean;
  progress: Progress | null;
  /** last result per quiz item (from GET /enrollments); the mock does not have it */
  quiz?: Record<string, { correct: boolean; seconds: number; attempts: number }>;
}

// ---- catalog query (hs-03): GET /catalog/query and GET /search/suggest (CONTRACTS.md section 11)
export type FacetKey = "band" | "subject" | "language" | "level" | "duration" | "media" | "status" | "teacher";
export type DurationBucket = "short" | "medium" | "long";
export type CatalogSort = "rel" | "new" | "pop" | "dur";
export interface CatalogQuery {
  q?: string;
  filters?: Partial<Record<FacetKey, string[]>>;
  sort?: CatalogSort;
  /** only for sort=dur */
  dir?: "asc" | "desc";
  page?: number;
  page_size?: number;
}
export interface CatalogItem extends CatalogEntry {
  students: number;
  score?: number;
}
export interface FacetOption {
  v: string;
  n: number;
}
export interface CatalogPage {
  query: string;
  mode: "hybrid" | "lexical";
  total: number;
  page: number;
  pages: number;
  page_size: number;
  items: CatalogItem[];
  facets: Record<FacetKey, FacetOption[]>;
  did_you_mean: string | null;
}
export interface Suggestions {
  courses: { id: string; title: string }[];
  subjects: string[];
  teachers: string[];
  did_you_mean: string | null;
}

export interface SearchHit extends CatalogEntry {
  score?: number;
}
export interface SearchResult {
  results: SearchHit[];
  /** nothing matched in the learner's age band but something matches in another */
  suggested_all_ages: boolean;
}

/** GET /enrollments item as the gateway sends it (CONTRACTS.md section 11). The app works with `Enrollment`. */
export interface WireEnrollment {
  course_id: string;
  version: number;
  latest_version: number;
  update_available: boolean;
  enrolled_at: string;
  updated_at?: string | null;
  last_lesson_id?: string | null;
  last_block_id?: string | null;
  completed_block_ids: string[];
  progress_pct: number;
  quiz?: Record<string, { correct: boolean; seconds: number; attempts: number }>;
}

export function fromWire(w: WireEnrollment): Enrollment {
  const started = !!w.last_lesson_id || w.completed_block_ids.length > 0;
  return {
    course_id: w.course_id,
    pinned_version: w.version,
    enrolled_at: w.enrolled_at,
    update_available: w.update_available,
    quiz: w.quiz,
    progress: started ? { lesson_id: w.last_lesson_id ?? "", block_id: w.last_block_id ?? "", completed_block_ids: w.completed_block_ids, updated_at: w.updated_at ?? undefined } : null,
  };
}
