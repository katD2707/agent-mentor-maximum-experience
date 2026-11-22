import type { CatalogSort, CourseDetail, Enrollment, TreeLesson } from "../../../api";
import { FIND_FACETS, type FindFacet, type FindQuery } from "../../api/chuong";

/** Pure helpers of the chicken's page (lg-03), kept apart from the components so they test without a DOM. */

// ---- growth: the four stages (lv 1 / 2-4 / 5-9 / 10+), one definition in subjects.ts
export { STAGE_AT, stageOf as stageIndex } from "../../subjects";

// ---- the course list
export type CourseState = "new" | "now" | "fin";
export interface Row {
  id: string;
  title: string;
  lessons: TreeLesson[];
  /** lessons before this index are done; the lesson at it is "now" */
  at: number;
  finished: boolean;
  percent: number;
  state: CourseState;
}

export function rowOf(info: CourseDetail, enrollment: Enrollment, finished: boolean, percent: number): Row {
  const lessons = info.tree.flatMap((c) => c.lessons);
  const idx = enrollment.progress ? lessons.findIndex((l) => l.id === enrollment.progress?.lesson_id) : -1;
  const at = finished ? lessons.length : Math.max(0, idx);
  const state: CourseState = finished ? "fin" : enrollment.progress ? "now" : "new";
  return { id: info.id, title: info.title, lessons, at, finished, percent, state };
}

/** The course the big button works on: the one in progress, else the first not started, else the first. */
export function activeIndex(rows: Row[]): number {
  let i = rows.findIndex((r) => r.state === "now");
  if (i < 0) i = rows.findIndex((r) => r.state === "new");
  return Math.max(0, i);
}

export type LessonState = "done" | "now" | "later";
export const lessonState = (row: Row, i: number): LessonState => (i < row.at ? "done" : i === row.at && !row.finished ? "now" : row.finished ? "done" : "later");

export const ladderBand = (age: string | null | undefined): "kid" | "school" | "uni" => (age === "g1_5" ? "kid" : age === "uni" ? "uni" : "school");

// ---- the "Tìm thêm khóa" board: its state lives in the address (?tim=1&q=&c=&page=&sort=&level=...)
export interface FindState extends FindQuery {
  /** the course whose preview is open */
  c: string | null;
}

export const emptyFind = (): FindState => ({ q: "", sort: "rel", page: 1, c: null, f: { level: [], language: [], duration: [], media: [] } });

export function parseFind(p: URLSearchParams): FindState {
  const s = emptyFind();
  s.q = (p.get("q") ?? "").trim();
  const sort = p.get("sort");
  s.sort = sort === "new" || sort === "pop" || sort === "dur" ? (sort as CatalogSort) : "rel";
  const page = Number(p.get("page"));
  s.page = Number.isInteger(page) && page > 1 ? page : 1;
  s.c = p.get("c") || null;
  for (const k of FIND_FACETS) s.f[k] = p.getAll(k).filter(Boolean);
  return s;
}

/** Write the board's state into a copy of `base` (the page's other parameters, such as `khoa`, stay). */
export function writeFind(base: URLSearchParams, s: FindState, open = true): URLSearchParams {
  const p = new URLSearchParams(base);
  for (const k of ["tim", "q", "c", "page", "sort", ...FIND_FACETS]) p.delete(k);
  if (open) p.set("tim", "1");
  if (s.q) p.set("q", s.q);
  if (s.c) p.set("c", s.c);
  if (s.page > 1) p.set("page", String(s.page));
  if (s.sort !== "rel") p.set("sort", s.sort);
  for (const k of FIND_FACETS) for (const v of s.f[k]) p.append(k, v);
  return p;
}

export const activeFilters = (s: FindQuery): number => FIND_FACETS.reduce((n, k) => n + s.f[k].length, 0);

export function toggleFacet(s: FindState, k: FindFacet, v: string): FindState {
  const cur = s.f[k];
  return { ...s, page: 1, f: { ...s.f, [k]: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v] } };
}

/** True when the board should be open: a search, a page, a filter or the preview asks for it. */
export const findIsOpen = (p: URLSearchParams): boolean => p.has("tim") || p.has("q") || p.has("c") || p.has("page");
